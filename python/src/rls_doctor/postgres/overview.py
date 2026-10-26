"""Bounded multi-table catalog diagnosis in one read-only snapshot."""

import re
import time
from typing import Any

import psycopg

from rls_doctor.postgres.inspector import (
    _ROLE_SQL,
    InspectorError,
    _database,
    _inspect_connection,
    _with_database,
)

_TABLES = """
SELECT c.relname AS name FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname=%s AND c.relkind IN ('r','p')
AND c.relname ~ '^[a-zA-Z_][a-zA-Z0-9_]{0,62}$'
ORDER BY c.relname LIMIT %s
"""


def inspect_schema(dsn: str, schema: str, role: str, limit: int = 30) -> dict[str, Any]:
    """No table rows, policy expressions, user functions or runtime SELECTs."""
    if (
        any(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", name) is None for name in (schema, role))
        or not 1 <= limit <= 50
    ):
        raise InspectorError(
            "INVALID_IDENTIFIER", "Use simple schema/role names and a limit from 1 to 50."
        )

    def operation(connection: psycopg.Connection[dict[str, Any]]) -> dict[str, Any]:
        database = _database(connection)
        if connection.execute(_ROLE_SQL, (role,)).fetchone() is None:
            raise InspectorError(
                "ROLE_NOT_FOUND", "The selected role was not found in the PostgreSQL catalog."
            )
        if (
            connection.execute(
                "SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname=%s", (schema,)
            ).fetchone()
            is None
        ):
            raise InspectorError(
                "SCHEMA_NOT_FOUND", "The selected schema was not found in the PostgreSQL catalog."
            )
        names = connection.execute(_TABLES, (schema, limit + 1)).fetchall()
        tables = []
        deadline = time.monotonic() + 30
        for name in names[:limit]:
            if time.monotonic() >= deadline:
                raise InspectorError(
                    "OVERVIEW_TIME_LIMIT",
                    "Overview time budget exceeded; retry with a smaller limit.",
                )
            detail = _inspect_connection(connection, schema, name["name"], role, False)
            codes = {c["code"] for c in detail["conclusions"]}
            blocked = bool(
                codes
                & {
                    "SCHEMA_USAGE_MISSING",
                    "SELECT_PRIVILEGE_MISSING",
                    "NO_PERMISSIVE_SELECT_POLICY",
                }
            )
            review = bool(codes & {"RLS_DISABLED", "RLS_BYPASSED", "SELECT_COLUMN_SCOPED"})
            tables.append(
                {
                    "resource": schema + "." + name["name"],
                    "configuration": "BLOCKED"
                    if blocked
                    else "REVIEW"
                    if review
                    else "NO_BASIC_BLOCKER",
                    "schema_usage": detail["privileges"]["schema_usage"],
                    "table_select": detail["privileges"]["table_select"],
                    "rls_enabled": detail["table"]["rls_enabled"],
                    "rls_applies": detail["table"]["rls_applies_to_requested_role"],
                    "policy_count": len(detail["policies"]),
                    "findings": [
                        c
                        for c in detail["conclusions"]
                        if c["code"]
                        not in {
                            "CATALOG_CONFIGURATION",
                            "EXECUTED_ROLE_UNCONFIRMED",
                            "ROW_VISIBILITY_UNKNOWN",
                            "PREDICATES_UNEVALUATED",
                            "SELECT_POLICY_COMPOSITION",
                            "RLS_APPLIES",
                        }
                    ],
                    "runtime_visibility": "UNKNOWN",
                }
            )
        priority = {"BLOCKED": 0, "REVIEW": 1, "NO_BASIC_BLOCKER": 2}
        tables.sort(key=lambda item: (priority[item["configuration"]], item["resource"]))
        return {
            "result": "UNKNOWN",
            "analysis_mode": "schema_catalog_overview",
            "database": database,
            "schema": schema,
            "requested_role": role,
            "tables": tables,
            "truncated": len(names) > limit,
            "limit": limit,
            "summary": {key: sum(t["configuration"] == key for t in tables) for key in priority},
            "limitations": [
                (
                    "Only supported simple-name ordinary/partitioned tables in the "
                    "selected schema are included."
                ),
                (
                    "One bounded read-only repeatable-read snapshot; no user rows, "
                    "application queries or policy expressions were read."
                ),
                (
                    "NO_BASIC_BLOCKER is not proof of row visibility or security. "
                    "Arbitrary policy predicates and executed application roles remain "
                    "unverified."
                ),
                (
                    "Partition entry points, views, functions and other schemas need "
                    "separate review."
                ),
            ],
        }

    return _with_database(dsn, operation)
