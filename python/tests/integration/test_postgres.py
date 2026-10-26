"""Real PostgreSQL catalog/behavior tests on explicitly approved disposable local DBs.

Setup is deliberately separate from diagnostics and creates synthetic objects.
Opt in with RLS_DOCTOR_INTEGRATION_DSN and RLS_DOCTOR_ALLOW_FIXTURE_SETUP=1.
An administrative test connection is required to create/drop disposable roles.
No integration claim is made when these tests are skipped.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from rls_doctor.postgres import InspectorError, doctor_database, inspect_table, inspector

pytestmark = pytest.mark.integration


class LocalDatabase(dict[str, Any]):
    """Prevent pytest failure argument rendering from printing test credentials."""

    def __repr__(self) -> str:
        return "<approved disposable local PostgreSQL fixture>"


@pytest.fixture(scope="module")
def local_database() -> Iterator[dict[str, Any]]:
    dsn = os.environ.get("RLS_DOCTOR_INTEGRATION_DSN")
    if not dsn or os.environ.get("RLS_DOCTOR_ALLOW_FIXTURE_SETUP") != "1":
        pytest.skip(
            "Explicit disposable local PostgreSQL DSN and fixture setup approval are required."
        )
    try:
        params = conninfo_to_dict(dsn)
    except psycopg.Error:
        pytest.fail("Integration DSN is invalid; its value has been suppressed.", pytrace=False)
    if (
        params.get("host") not in {"127.0.0.1", "::1"}
        or params.get("hostaddr", params.get("host")) != params.get("host")
        or "service" in params
        or not params.get("port", "").isdigit()
    ):
        pytest.fail(
            "Integration fixtures require an explicit numeric loopback host and port.",
            pytrace=False,
        )
    # Explicit hostaddr prevents PGHOSTADDR from redirecting this test connection.
    params["hostaddr"] = params["host"]
    pinned_dsn = psycopg.conninfo.make_conninfo(**params)
    suffix = uuid4().hex[:12]
    schema = f"rls_doctor_test_{suffix}"
    names = {
        name: f"rlsd_{name}_{suffix}"
        for name in (
            "reader",
            "limited",
            "group",
            "noinherit",
            "owner",
            "owner_member",
            "bypass",
        )
    }
    connection = None
    try:
        connection = psycopg.connect(pinned_dsn, autocommit=True, connect_timeout=5)
    except psycopg.Error:
        pass
    if connection is None:
        # Raise outside the database exception handler to avoid unsafe chaining.
        pytest.fail(
            "Cannot connect to the approved disposable local database; "
            "connection details have been suppressed.",
            pytrace=False,
        )
    if not connection.execute(
        "SELECT rolsuper FROM pg_catalog.pg_roles WHERE rolname = CURRENT_USER"
    ).fetchone()[0]:
        connection.close()
        pytest.skip("Disposable role fixture setup requires a local PostgreSQL superuser.")
    created_roles: list[str] = []
    schema_created = False
    try:
        for kind, name in names.items():
            attribute = "BYPASSRLS" if kind == "bypass" else "NOBYPASSRLS"
            inherit = "NOINHERIT" if kind == "noinherit" else "INHERIT"
            connection.execute(
                sql.SQL("CREATE ROLE {} NOLOGIN {} {}").format(
                    sql.Identifier(name), sql.SQL(attribute), sql.SQL(inherit)
                )
            )
            created_roles.append(name)
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        schema_created = True
        for name in names.values():
            connection.execute(
                sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                    sql.Identifier(schema), sql.Identifier(name)
                )
            )
        for member in ("reader", "noinherit"):
            connection.execute(
                sql.SQL("GRANT {} TO {}").format(
                    sql.Identifier(names["group"]), sql.Identifier(names[member])
                )
            )
        connection.execute(
            sql.SQL("GRANT {} TO {}").format(
                sql.Identifier(names["owner"]), sql.Identifier(names["owner_member"])
            )
        )
        for table in (
            "default_deny",
            "composition",
            "membership",
            "column_grants",
            "owner_case",
            "sensitive",
        ):
            relation = sql.Identifier(schema, table)
            connection.execute(sql.SQL("CREATE TABLE {} (id integer, note text)").format(relation))
            connection.execute(
                sql.SQL("INSERT INTO {} VALUES (1, 'synthetic'), (2, 'synthetic')").format(relation)
            )
            connection.execute(sql.SQL("ALTER TABLE {} ENABLE ROW LEVEL SECURITY").format(relation))
            connection.execute(
                sql.SQL("GRANT SELECT ON {} TO {}, {}").format(
                    relation, sql.Identifier(names["group"]), sql.Identifier(names["bypass"])
                )
            )
        for table in ("composition", "column_grants"):
            connection.execute(
                sql.SQL("CREATE POLICY public_read ON {} FOR SELECT TO PUBLIC USING (true)").format(
                    sql.Identifier(schema, table)
                )
            )
        connection.execute(
            sql.SQL(
                "CREATE POLICY restrict_second ON {} AS RESTRICTIVE "
                "FOR SELECT TO PUBLIC USING (id = 1)"
            ).format(sql.Identifier(schema, "composition"))
        )
        connection.execute(
            sql.SQL("CREATE POLICY group_read ON {} FOR SELECT TO {} USING (true)").format(
                sql.Identifier(schema, "membership"), sql.Identifier(names["group"])
            )
        )
        connection.execute(
            sql.SQL("GRANT SELECT ON {} TO {}").format(
                sql.Identifier(schema, "membership"), sql.Identifier(names["noinherit"])
            )
        )
        connection.execute(
            sql.SQL("GRANT SELECT (id) ON {} TO {}").format(
                sql.Identifier(schema, "column_grants"), sql.Identifier(names["limited"])
            )
        )
        connection.execute(
            sql.SQL("ALTER TABLE {} OWNER TO {}").format(
                sql.Identifier(schema, "owner_case"), sql.Identifier(names["owner"])
            )
        )
        connection.execute(
            sql.SQL(
                "CREATE POLICY sensitive_predicate ON {} FOR SELECT "
                "USING (note = 'synthetic-policy-secret-9102')"
            ).format(sql.Identifier(schema, "sensitive"))
        )
        connection.execute(
            sql.SQL("CREATE VIEW {} AS SELECT id FROM {}").format(
                sql.Identifier(schema, "unsupported_view"), sql.Identifier(schema, "composition")
            )
        )
        yield LocalDatabase(dsn=pinned_dsn, schema=schema, roles=names, connection=connection)
    finally:
        if schema_created:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        for name in reversed(created_roles):
            connection.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(name)))
        connection.close()


def inspect(fixture: dict[str, Any], table: str, role: str = "reader") -> dict[str, Any]:
    return inspect_table(fixture["dsn"], fixture["schema"], table, fixture["roles"][role])


def codes(report: dict[str, Any]) -> set[str]:
    return {fact["code"] for fact in report["conclusions"]}


def row_count(fixture: dict[str, Any], table: str, role: str) -> int:
    # This explicit test helper queries synthetic fixture rows; the inspector does not.
    connection = fixture["connection"]
    with connection.transaction():
        connection.execute(
            sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(fixture["roles"][role]))
        )
        return int(
            connection.execute(
                sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(fixture["schema"], table))
            ).fetchone()[0]
        )


def test_real_readonly_transaction_rejects_writes(local_database: dict[str, Any]) -> None:
    report = doctor_database(local_database["dsn"])
    assert report["database"]["read_only"]
    assert report["database"]["server_major"] in {16, 17, 18}

    def attempt_write(connection: psycopg.Connection[Any]) -> None:
        connection.execute(
            sql.SQL("CREATE TABLE {} (id integer)").format(
                sql.Identifier(local_database["schema"], "readonly_must_not_exist")
            )
        )

    with pytest.raises(InspectorError) as caught:
        inspector._with_database(local_database["dsn"], attempt_write)
    assert caught.value.sqlstate == "25006"


def test_real_missing_select_grant_and_default_deny(local_database: dict[str, Any]) -> None:
    missing = inspect(local_database, "default_deny", "limited")
    assert "SELECT_PRIVILEGE_MISSING" in codes(missing)
    denied = inspect(local_database, "default_deny")
    assert denied["privileges"]["table_select"]
    assert "NO_PERMISSIVE_SELECT_POLICY" in codes(denied)
    assert row_count(local_database, "default_deny", "reader") == 0


def test_real_permissive_restrictive_composition(local_database: dict[str, Any]) -> None:
    report = inspect(local_database, "composition")
    assert "SELECT_POLICY_COMPOSITION" in codes(report)
    assert {policy["permissive"] for policy in report["policies"]} == {True, False}
    assert all(policy["roles"] == ["PUBLIC"] for policy in report["policies"])
    assert row_count(local_database, "composition", "reader") == 1


def test_real_role_inheritance_controls_policy_applicability(
    local_database: dict[str, Any],
) -> None:
    inherited = inspect(local_database, "membership", "reader")
    unavailable = inspect(local_database, "membership", "noinherit")
    assert inherited["policies"][0]["applies_to_role"]
    assert not unavailable["policies"][0]["applies_to_role"]
    assert row_count(local_database, "membership", "reader") == 2
    assert row_count(local_database, "membership", "noinherit") == 0


def test_real_owner_membership_force_and_bypass(local_database: dict[str, Any]) -> None:
    report = inspect(local_database, "owner_case", "owner_member")
    assert report["privileges"]["owner_privileges_inherited"]
    assert "RLS_BYPASSED" in codes(report)
    connection = local_database["connection"]
    connection.execute(
        sql.SQL("ALTER TABLE {} FORCE ROW LEVEL SECURITY").format(
            sql.Identifier(local_database["schema"], "owner_case")
        )
    )
    try:
        forced = inspect(local_database, "owner_case", "owner_member")
        assert forced["table"]["rls_applies_to_requested_role"]
        assert row_count(local_database, "owner_case", "owner_member") == 0
        bypassed = inspect(local_database, "owner_case", "bypass")
        assert "RLS_BYPASSED" in codes(bypassed)
        assert row_count(local_database, "owner_case", "bypass") == 2
    finally:
        connection.execute(
            sql.SQL("ALTER TABLE {} NO FORCE ROW LEVEL SECURITY").format(
                sql.Identifier(local_database["schema"], "owner_case")
            )
        )


def test_real_column_grants_are_not_blanket_denial(local_database: dict[str, Any]) -> None:
    report = inspect(local_database, "column_grants", "limited")
    assert "SELECT_COLUMN_SCOPED" in codes(report)
    assert "SELECT_PRIVILEGE_MISSING" not in codes(report)
    assert report["privileges"]["columns"] == [
        {"name": "id", "select": True},
        {"name": "note", "select": False},
    ]
    connection = local_database["connection"]
    with connection.transaction():
        connection.execute(
            sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(local_database["roles"]["limited"]))
        )
        assert (
            len(
                connection.execute(
                    sql.SQL("SELECT id FROM {}").format(
                        sql.Identifier(local_database["schema"], "column_grants")
                    )
                ).fetchall()
            )
            == 2
        )
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with connection.transaction():
            connection.execute(
                sql.SQL("SET LOCAL ROLE {}").format(
                    sql.Identifier(local_database["roles"]["limited"])
                )
            )
            connection.execute(
                sql.SQL("SELECT note FROM {}").format(
                    sql.Identifier(local_database["schema"], "column_grants")
                )
            )


def test_real_policy_literal_never_enters_report(local_database: dict[str, Any]) -> None:
    report = inspect(local_database, "sensitive")
    assert "synthetic-policy-secret-9102" not in json.dumps(report)
    assert report["policies"][0]["has_using"]
    assert report["policies"][0]["predicates_redacted"]


def test_real_view_semantics_are_explicitly_unsupported(local_database: dict[str, Any]) -> None:
    with pytest.raises(InspectorError) as caught:
        inspect(local_database, "unsupported_view")
    assert caught.value.code == "UNSUPPORTED_RELATION"


def test_real_disabled_rls_is_reported_without_default_deny(local_database: dict[str, Any]) -> None:
    connection = local_database["connection"]
    relation = sql.Identifier(local_database["schema"], "default_deny")
    connection.execute(sql.SQL("ALTER TABLE {} DISABLE ROW LEVEL SECURITY").format(relation))
    try:
        report = inspect(local_database, "default_deny", "reader")
        assert not report["table"]["rls_enabled"]
        assert "RLS_DISABLED" in codes(report)
        assert "NO_PERMISSIVE_SELECT_POLICY" not in codes(report)
        assert row_count(local_database, "default_deny", "reader") == 2
    finally:
        connection.execute(sql.SQL("ALTER TABLE {} ENABLE ROW LEVEL SECURITY").format(relation))


def test_real_schema_overview_prioritizes_blockers(local_database: dict[str, Any]) -> None:
    from rls_doctor.postgres.overview import inspect_schema

    report = inspect_schema(
        local_database["dsn"], local_database["schema"], local_database["roles"]["reader"]
    )
    by_name = {t["resource"].split(".")[1]: t for t in report["tables"]}
    assert report["result"] == "UNKNOWN"
    assert by_name["default_deny"]["configuration"] == "BLOCKED"
    assert by_name["composition"]["configuration"] == "NO_BASIC_BLOCKER"
    assert all(t["runtime_visibility"] == "UNKNOWN" for t in report["tables"])
    assert "synthetic-policy-secret-9102" not in json.dumps(report)
    assert not report["truncated"]
    assert report["tables"][0]["configuration"] == "BLOCKED"


def test_real_schema_overview_limit_and_missing_schema(local_database: dict[str, Any]) -> None:
    from rls_doctor.postgres.overview import inspect_schema

    report = inspect_schema(
        local_database["dsn"], local_database["schema"], local_database["roles"]["reader"], limit=1
    )
    assert report["truncated"] and len(report["tables"]) == 1
    with pytest.raises(InspectorError) as caught:
        inspect_schema(
            local_database["dsn"],
            "rlsd_missing_" + uuid4().hex[:12],
            local_database["roles"]["reader"],
        )
    assert caught.value.code == "SCHEMA_NOT_FOUND"
