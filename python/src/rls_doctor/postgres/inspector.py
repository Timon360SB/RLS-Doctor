"""Inspect catalog facts for an explicitly selected role and table.

The caller must validate/approve the DSN against the local database allowlist.
Neither DSNs nor database exception text are included in returned diagnostics.
Only PostgreSQL 16, 17, and 18 have been selected for this initial implementation.
Policy expressions are deliberately never fetched: even a literal inside a policy
can contain a secret. Presence flags and direct auth-function dependencies are
enough to identify the boundary of this static inspection.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import psycopg
from psycopg.rows import dict_row

SUPPORTED_MAJORS = frozenset({16, 17, 18})


class InspectorError(Exception):
    """An inspection error containing only a fixed message and safe SQLSTATE."""

    def __init__(self, code: str, message: str, sqlstate: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.sqlstate = sqlstate


_DATABASE_SQL = """
SELECT pg_catalog.current_setting('server_version_num')::integer AS server_version_num,
       pg_catalog.current_setting('transaction_read_only') = 'on' AS read_only,
       r.rolname AS inspector_role, r.rolsuper AS inspector_superuser,
       r.rolbypassrls AS inspector_bypassrls
FROM pg_catalog.pg_roles AS r WHERE r.rolname = CURRENT_USER
"""

_ROLE_SQL = """
SELECT oid, rolname AS name, rolsuper AS superuser,
       rolbypassrls AS bypass_rls, rolinherit AS inherit
FROM pg_catalog.pg_roles WHERE rolname = %s
"""

_TABLE_SQL = """
SELECT c.oid, n.oid AS schema_oid, n.nspname AS schema, c.relname AS name,
       c.relkind AS kind, c.relrowsecurity AS rls_enabled,
       c.relforcerowsecurity AS rls_forced, c.relowner AS owner_oid,
       o.rolname AS owner
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
JOIN pg_catalog.pg_roles AS o ON o.oid = c.relowner
WHERE n.nspname = %s AND c.relname = %s
"""

_PRIVILEGES_SQL = """
SELECT pg_catalog.has_schema_privilege(%s::oid, %s::oid, 'USAGE') AS schema_usage,
       pg_catalog.has_table_privilege(%s::oid, %s::oid, 'SELECT') AS table_select,
       pg_catalog.has_any_column_privilege(%s::oid, %s::oid, 'SELECT') AS any_column_select,
       pg_catalog.pg_has_role(%s::oid, %s::oid, 'USAGE') AS owner_privileges_inherited
"""

_COLUMNS_SQL = """
SELECT a.attname AS name,
       pg_catalog.has_column_privilege(%s::oid, a.attrelid, a.attnum, 'SELECT') AS select
FROM pg_catalog.pg_attribute AS a
WHERE a.attrelid = %s::oid AND a.attnum > 0 AND NOT a.attisdropped
ORDER BY a.attnum
"""

# No expression text leaves PostgreSQL. Dependency flags identify direct auth.*
# calls only; functions called by other functions cannot be inferred here.
_POLICIES_SQL = """
SELECT p.polname AS name, p.polcmd AS command_code, p.polpermissive AS permissive,
       p.polqual IS NOT NULL AS has_using,
       p.polwithcheck IS NOT NULL AS has_with_check,
       ARRAY(SELECT CASE WHEN policy_role = 0 THEN 'PUBLIC'
                         ELSE pg_catalog.pg_get_userbyid(policy_role)::text END
             FROM pg_catalog.unnest(p.polroles) AS policy_role
             ORDER BY 1) AS roles,
       EXISTS (SELECT 1 FROM pg_catalog.unnest(p.polroles) AS policy_role
               WHERE CASE WHEN policy_role = 0 THEN true
                     ELSE pg_catalog.pg_has_role(%s::oid, policy_role, 'USAGE') END
              ) AS applies_to_role,
       ARRAY(SELECT DISTINCT fn.proname::text
             FROM pg_catalog.pg_depend AS dep
             JOIN pg_catalog.pg_proc AS fn ON fn.oid = dep.refobjid
             JOIN pg_catalog.pg_namespace AS ns ON ns.oid = fn.pronamespace
             WHERE dep.classid = 'pg_catalog.pg_policy'::pg_catalog.regclass
               AND dep.objid = p.oid
               AND dep.refclassid = 'pg_catalog.pg_proc'::pg_catalog.regclass
               AND ns.nspname = 'auth' AND fn.proname IN ('uid', 'jwt', 'role')
             ORDER BY 1) AS direct_auth_function_dependencies
FROM pg_catalog.pg_policy AS p WHERE p.polrelid = %s::oid ORDER BY p.polname
"""

_COMMANDS = {"*": "ALL", "r": "SELECT", "a": "INSERT", "w": "UPDATE", "d": "DELETE"}


def _fact(code: str, evidence: str, summary: str, basis: str) -> dict[str, str]:
    return {"code": code, "evidence": evidence, "summary": summary, "basis": basis}


def _database(connection: psycopg.Connection[dict[str, Any]]) -> dict[str, Any]:
    row = connection.execute(_DATABASE_SQL).fetchone()
    if row is None or not row["read_only"]:
        raise InspectorError("READ_ONLY_REQUIRED", "The inspection transaction is not read-only.")
    major = row["server_version_num"] // 10000
    if major not in SUPPORTED_MAJORS:
        raise InspectorError(
            "UNSUPPORTED_POSTGRES_VERSION", "Inspection supports PostgreSQL 16, 17, and 18 only."
        )
    return {**row, "server_major": major, "supported": True}


def _with_database[T](dsn: str, operation: Callable[[psycopg.Connection[dict[str, Any]]], T]) -> T:
    """Establish fixed defensive settings before running our catalog queries."""
    failure: InspectorError | None = None
    try:
        # Keyword arguments override conflicting DSN parameters. The caller's DSN
        # must already be allowlisted; local forwarding remains an operator risk.
        with psycopg.connect(
            dsn,
            connect_timeout=5,
            options=(
                "-c default_transaction_read_only=on -c statement_timeout=5000 "
                "-c lock_timeout=1000 -c search_path=pg_catalog"
            ),
            row_factory=dict_row,
        ) as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            return operation(connection)
    except psycopg.Error as error:
        # Never copy str(error), detail, hint, query, host, username, or DSN.
        state = error.sqlstate
        if state is not None and (len(state) != 5 or not state.isascii() or not state.isalnum()):
            state = None
        failure = InspectorError(
            "POSTGRES_INSPECTION_FAILED",
            "PostgreSQL catalog inspection failed. "
            "Check the approved local endpoint and catalog permissions.",
            state,
        )
    # Raise outside the except block so an unsafe database exception is not chained.
    assert failure is not None
    raise failure


def doctor_database(dsn: str) -> dict[str, Any]:
    """Check the approved database connection and supported read-only context."""

    def operation(connection: psycopg.Connection[dict[str, Any]]) -> dict[str, Any]:
        database = _database(connection)
        conclusions = [
            _fact(
                "READ_ONLY_TRANSACTION",
                "OBSERVED",
                "Catalog inspection uses a read-only transaction.",
                "transaction_read_only",
            ),
            _fact(
                "POSTGRES_VERSION_SUPPORTED",
                "OBSERVED",
                "The server major version is supported by this inspector.",
                "server_version_num",
            ),
        ]
        if database["inspector_superuser"] or database["inspector_bypassrls"]:
            conclusions.append(
                _fact(
                    "ELEVATED_INSPECTOR_ROLE",
                    "OBSERVED",
                    "The catalog connection has superuser or BYPASSRLS privileges; "
                    "use a less privileged inspector where possible.",
                    "pg_roles",
                )
            )
        return {
            "database": database,
            "conclusions": conclusions,
            "limitations": [
                "No user rows or policy predicates were evaluated.",
                "Loopback endpoint validation cannot detect forwarding to remote infrastructure.",
            ],
        }

    return _with_database(dsn, operation)


def _conclusions(
    table: dict[str, Any],
    role: dict[str, Any],
    privileges: dict[str, Any],
    policies: list[dict[str, Any]],
) -> tuple[bool, list[dict[str, str]]]:
    """Derive limited SELECT conclusions from catalog facts, never row results."""
    results = [
        _fact(
            "CATALOG_CONFIGURATION",
            "OBSERVED",
            "Table, role, policy, and SQL privilege metadata were read from PostgreSQL catalogs.",
            "pg_class, pg_roles, pg_policy and privilege inquiry functions",
        ),
        _fact(
            "EXECUTED_ROLE_UNCONFIRMED",
            "UNVERIFIED",
            "The requested role has not been confirmed in an executed application request.",
            "Caller-supplied inspection role",
        ),
    ]
    if not privileges["schema_usage"]:
        results.append(
            _fact(
                "SCHEMA_USAGE_MISSING",
                "INFERRED",
                "The selected role lacks schema USAGE required to resolve this table "
                "in a normal SELECT.",
                "has_schema_privilege",
            )
        )
    if not privileges["any_column_select"]:
        results.append(
            _fact(
                "SELECT_PRIVILEGE_MISSING",
                "INFERRED",
                "The selected role has no table-level or column-level SELECT privilege "
                "on this table.",
                "has_table_privilege and has_any_column_privilege",
            )
        )
    elif not privileges["table_select"]:
        results.append(
            _fact(
                "SELECT_COLUMN_SCOPED",
                "INFERRED",
                "SELECT privileges are column-scoped; compare the exact requested columns "
                "with the inspected grants.",
                "has_column_privilege",
            )
        )

    bypass = (
        role["superuser"]
        or role["bypass_rls"]
        or (privileges["owner_privileges_inherited"] and not table["rls_forced"])
    )
    rls_applies = bool(table["rls_enabled"] and not bypass)
    if not table["rls_enabled"]:
        results.append(
            _fact(
                "RLS_DISABLED",
                "OBSERVED",
                "Row-level security is disabled for this table.",
                "pg_class.relrowsecurity",
            )
        )
    elif bypass:
        results.append(
            _fact(
                "RLS_BYPASSED",
                "INFERRED",
                "The selected role bypasses RLS through superuser, BYPASSRLS, or effective "
                "owner privileges without FORCE RLS.",
                "Role attributes, pg_has_role(USAGE), and relforcerowsecurity",
            )
        )
    else:
        results.append(
            _fact(
                "RLS_APPLIES",
                "INFERRED",
                "Normal SELECT access by the selected role is subject to row-level security.",
                "RLS enabled; role has no applicable bypass",
            )
        )
        applicable = [
            p for p in policies if p["applies_to_role"] and p["command"] in {"ALL", "SELECT"}
        ]
        permissive = [p for p in applicable if p["permissive"]]
        if not permissive:
            results.append(
                _fact(
                    "NO_PERMISSIVE_SELECT_POLICY",
                    "INFERRED",
                    "No applicable permissive SELECT policy exists; RLS uses a "
                    "default-deny SELECT basis for this role.",
                    "pg_policy command, role membership and permissive flags",
                )
            )
        else:
            results.append(
                _fact(
                    "SELECT_POLICY_COMPOSITION",
                    "INFERRED",
                    "Applicable permissive SELECT policies combine with OR, then applicable "
                    "restrictive policies combine with AND.",
                    "PostgreSQL policy composition; predicate values are not evaluated",
                )
            )
            results.append(
                _fact(
                    "PREDICATES_UNEVALUATED",
                    "UNVERIFIED",
                    "Policy predicates, JWT/session settings, function execution, and actual "
                    "row visibility remain unverified.",
                    "Read-only catalog inspection does not execute application SELECTs",
                )
            )
    results.append(
        _fact(
            "ROW_VISIBILITY_UNKNOWN",
            "UNVERIFIED",
            "No row result was observed. An empty HTTP result alone cannot identify "
            "RLS as its cause.",
            "Explicit local replay with synthetic fixtures is required",
        )
    )
    return rls_applies, results


def inspect_table(dsn: str, schema: str, table: str, role: str) -> dict[str, Any]:
    """Inspect a table for an explicit role on a prevalidated local DSN.

    Views, foreign tables, materialized views, and other relation kinds are
    intentionally unsupported; they require their own authorization semantics.
    Names are parameters, including role names; no SET ROLE or user SQL runs.
    """
    if any(
        not isinstance(name, str) or not name or "\x00" in name for name in (schema, table, role)
    ):
        raise InspectorError(
            "INVALID_IDENTIFIER",
            "Schema, table, and role names must be nonempty and contain no NUL characters.",
        )

    def operation(connection: psycopg.Connection[dict[str, Any]]) -> dict[str, Any]:
        database = _database(connection)
        role_info = connection.execute(_ROLE_SQL, (role,)).fetchone()
        if role_info is None:
            raise InspectorError(
                "ROLE_NOT_FOUND", "The selected role was not found in the PostgreSQL catalog."
            )
        table_info = connection.execute(_TABLE_SQL, (schema, table)).fetchone()
        if table_info is None:
            raise InspectorError(
                "TABLE_NOT_FOUND", "The selected relation was not found in the PostgreSQL catalog."
            )
        if table_info["kind"] not in {"r", "p"}:
            raise InspectorError(
                "UNSUPPORTED_RELATION",
                "Only ordinary and partitioned tables are supported; "
                "view and foreign-table behavior is not inferred.",
            )
        role_oid, table_oid = role_info["oid"], table_info["oid"]
        privileges = connection.execute(
            _PRIVILEGES_SQL,
            (
                role_oid,
                table_info["schema_oid"],
                role_oid,
                table_oid,
                role_oid,
                table_oid,
                role_oid,
                table_info["owner_oid"],
            ),
        ).fetchone()
        assert privileges is not None
        privileges["columns"] = connection.execute(_COLUMNS_SQL, (role_oid, table_oid)).fetchall()
        policy_rows = connection.execute(_POLICIES_SQL, (role_oid, table_oid)).fetchall()
        policies = []
        for row in policy_rows:
            row["command"] = _COMMANDS[row.pop("command_code")]
            row["predicates_redacted"] = True
            policies.append(row)
        applies, conclusions = _conclusions(table_info, role_info, privileges, policies)
        public_table = {
            key: value
            for key, value in table_info.items()
            if key not in {"oid", "schema_oid", "owner_oid"}
        }
        public_table["rls_applies_to_requested_role"] = applies
        public_role = {key: value for key, value in role_info.items() if key != "oid"}
        return {
            "database": database,
            "table": public_table,
            "role": public_role,
            "privileges": privileges,
            "policies": policies,
            "conclusions": conclusions,
            "limitations": [
                "Only the explicitly named ordinary or partitioned table "
                "and supplied role are inspected.",
                "The supplied role is not proof of the role executed by PostgREST.",
                "Policy expression text is not collected; policy predicates and data visibility "
                "are not evaluated.",
                "Auth dependency flags include only direct auth.uid, auth.jwt, and auth.role "
                "function references; hidden dependencies remain unknown.",
                "Views, functions, inheritance/partition entry points, session settings, "
                "JWT claims, and other referenced objects need separate runtime verification.",
                "Column-scoped privileges must be compared with the exact requested columns.",
            ],
        }

    return _with_database(dsn, operation)
