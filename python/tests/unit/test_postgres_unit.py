"""Pure catalog-analysis and database-boundary tests; no database is simulated as live."""

from __future__ import annotations

import json
import runpy
from pathlib import Path
from typing import Any

import psycopg
import pytest

from rls_doctor.postgres import InspectorError, doctor_database, inspect_table, inspector


def facts(
    *,
    enabled: bool = True,
    forced: bool = False,
    owner: bool = False,
    superuser: bool = False,
    bypass: bool = False,
    table_select: bool = True,
    any_select: bool = True,
    schema_usage: bool = True,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return (
        {"rls_enabled": enabled, "rls_forced": forced},
        {"superuser": superuser, "bypass_rls": bypass},
        {
            "owner_privileges_inherited": owner,
            "schema_usage": schema_usage,
            "table_select": table_select,
            "any_column_select": any_select,
        },
    )


def codes(conclusions: list[dict[str, str]]) -> set[str]:
    return {item["code"] for item in conclusions}


def policy(
    *, permissive: bool = True, applies: bool = True, command: str = "SELECT"
) -> dict[str, Any]:
    return {"command": command, "permissive": permissive, "applies_to_role": applies}


def test_default_deny_includes_restrictive_only_and_ignores_other_commands() -> None:
    for policies in (
        [],
        [policy(permissive=False)],
        [policy(command="INSERT")],
        [policy(applies=False)],
    ):
        applies, conclusions = inspector._conclusions(*facts(), policies)
        assert applies
        assert "NO_PERMISSIVE_SELECT_POLICY" in codes(conclusions)
        assert "ROW_VISIBILITY_UNKNOWN" in codes(conclusions)


@pytest.mark.parametrize("role_flags", [{"superuser": True}, {"bypass": True}])
def test_force_rls_does_not_override_superuser_or_bypass(role_flags: dict[str, bool]) -> None:
    applies, conclusions = inspector._conclusions(*facts(forced=True, **role_flags), [])
    assert not applies
    assert "RLS_BYPASSED" in codes(conclusions)


def test_owner_inheritance_and_force_rls() -> None:
    assert not inspector._conclusions(*facts(owner=True), [])[0]
    assert inspector._conclusions(*facts(owner=True, forced=True), [])[0]


def test_column_grants_do_not_become_blanket_denial() -> None:
    _, conclusions = inspector._conclusions(*facts(table_select=False), [])
    assert "SELECT_COLUMN_SCOPED" in codes(conclusions)
    assert "SELECT_PRIVILEGE_MISSING" not in codes(conclusions)
    _, conclusions = inspector._conclusions(*facts(table_select=False, any_select=False), [])
    assert "SELECT_PRIVILEGE_MISSING" in codes(conclusions)


def test_schema_usage_and_rls_are_separate() -> None:
    applies, conclusions = inspector._conclusions(*facts(enabled=False, schema_usage=False), [])
    assert not applies
    assert {"SCHEMA_USAGE_MISSING", "RLS_DISABLED"} <= codes(conclusions)


def test_composition_is_an_inference_and_predicate_outcome_stays_unverified() -> None:
    _, conclusions = inspector._conclusions(*facts(), [policy(), policy(permissive=False)])
    by_code = {item["code"]: item for item in conclusions}
    assert by_code["SELECT_POLICY_COMPOSITION"]["evidence"] == "INFERRED"
    assert by_code["PREDICATES_UNEVALUATED"]["evidence"] == "UNVERIFIED"
    assert by_code["EXECUTED_ROLE_UNCONFIRMED"]["evidence"] == "UNVERIFIED"


class FakeCursor:
    def __init__(self, value: Any) -> None:
        self.value = value

    def fetchone(self) -> Any:
        return self.value

    def fetchall(self) -> Any:
        return self.value


class FakeConnection:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = iter(responses)
        self.queries: list[tuple[str, Any]] = []

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def execute(self, query: str, params: Any = None) -> FakeCursor:
        self.queries.append((query, params))
        if query == "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY":
            return FakeCursor(None)
        return FakeCursor(next(self.responses))


def database_row(version: int = 170006) -> dict[str, Any]:
    return {
        "server_version_num": version,
        "read_only": True,
        "inspector_role": "postgres",
        "inspector_superuser": True,
        "inspector_bypassrls": False,
    }


def test_inspection_uses_parameters_redacts_predicates_and_never_fetches_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dangerous_name = "target'; SELECT secret FROM private_table; --"
    connection = FakeConnection(
        [
            database_row(),
            {"oid": 10, "name": "reader", "superuser": False, "bypass_rls": False, "inherit": True},
            {
                "oid": 20,
                "schema_oid": 21,
                "schema": "public",
                "name": dangerous_name,
                "kind": "r",
                "rls_enabled": True,
                "rls_forced": False,
                "owner_oid": 30,
                "owner": "owner",
            },
            {
                "schema_usage": True,
                "table_select": True,
                "any_column_select": True,
                "owner_privileges_inherited": False,
            },
            [{"name": "id", "select": True}],
            [
                {
                    "name": "own_rows",
                    "command_code": "r",
                    "permissive": True,
                    "has_using": True,
                    "has_with_check": False,
                    "roles": ["PUBLIC"],
                    "applies_to_role": True,
                    "direct_auth_function_dependencies": ["uid"],
                }
            ],
        ]
    )
    connection_options: dict[str, Any] = {}

    def connect(dsn: str, **kwargs: Any) -> FakeConnection:
        connection_options.update(kwargs)
        return connection

    monkeypatch.setattr(inspector.psycopg, "connect", connect)
    report = inspect_table("host=127.0.0.1 password=not_saved", "public", dangerous_name, "reader")
    serialized = json.dumps(report)
    assert "not_saved" not in serialized
    assert report["policies"][0]["predicates_redacted"] is True
    assert report["policies"][0]["command"] == "SELECT"
    assert "oid" not in report["role"]
    for query, _ in connection.queries:
        assert dangerous_name not in query
        assert "pg_get_expr" not in query
        assert "private_table" not in query
    assert (inspector._TABLE_SQL, ("public", dangerous_name)) in connection.queries
    assert "default_transaction_read_only=on" in connection_options["options"]
    assert "statement_timeout=5000" in connection_options["options"]
    assert connection_options["connect_timeout"] == 5


def test_database_error_does_not_expose_or_chain_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    def connect(*args: Any, **kwargs: Any) -> Any:
        raise psycopg.OperationalError("password=hunter2 host=production secret-query-value")

    monkeypatch.setattr(inspector.psycopg, "connect", connect)
    with pytest.raises(InspectorError) as caught:
        doctor_database("password=also-secret")
    assert "hunter2" not in str(caught.value)
    assert "also-secret" not in str(caught.value)
    assert caught.value.code == "POSTGRES_INSPECTION_FAILED"
    assert caught.value.__context__ is None


def test_integration_setup_connection_error_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def connect(*args: Any, **kwargs: Any) -> Any:
        raise psycopg.OperationalError("password=integration-secret is rejected")

    monkeypatch.setattr(inspector.psycopg, "connect", connect)
    monkeypatch.setenv(
        "RLS_DOCTOR_INTEGRATION_DSN",
        "host=127.0.0.1 port=55432 dbname=postgres user=postgres password=integration-secret",
    )
    monkeypatch.setenv("RLS_DOCTOR_ALLOW_FIXTURE_SETUP", "1")
    integration_file = Path(__file__).resolve().parents[1] / "integration" / "test_postgres.py"
    setup = runpy.run_path(str(integration_file))["local_database"].__wrapped__()
    with pytest.raises(pytest.fail.Exception) as caught:
        next(setup)
    assert "integration-secret" not in str(caught.value)
    assert caught.value.__context__ is None


@pytest.mark.parametrize("version", [150009, 190000])
def test_unsupported_postgres_fails_explicitly(version: int) -> None:
    with pytest.raises(InspectorError, match="16, 17, and 18") as caught:
        inspector._database(FakeConnection([database_row(version)]))  # type: ignore[arg-type]
    assert caught.value.code == "UNSUPPORTED_POSTGRES_VERSION"


@pytest.mark.parametrize("name", ["", "bad\x00name"])
def test_invalid_identifiers_rejected_before_connect(name: str) -> None:
    with pytest.raises(InspectorError) as caught:
        inspect_table("unused", "public", name, "reader")
    assert caught.value.code == "INVALID_IDENTIFIER"
