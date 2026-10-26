"""Schema overview bounds and snapshot routing."""

from types import SimpleNamespace
from typing import Any

import pytest

from rls_doctor.postgres import InspectorError, overview


class Catalog:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def execute(self, query: str, params: Any = None) -> Any:
        self.calls.append((query, params))
        if query == overview._ROLE_SQL:
            return SimpleNamespace(fetchone=lambda: {"name": "reader"})
        if "pg_namespace WHERE" in query:
            return SimpleNamespace(fetchone=lambda: {"exists": 1})
        return SimpleNamespace(fetchall=lambda: [{"name": "a"}, {"name": "b"}])


def test_one_snapshot_uses_parameterized_schema_and_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    catalog = Catalog()
    snapshots = []

    def snapshot(dsn: str, operation: Any) -> Any:
        snapshots.append(1)
        return operation(catalog)

    monkeypatch.setattr(overview, "_with_database", snapshot)
    monkeypatch.setattr(overview, "_database", lambda *a: {"read_only": True})

    def detail(*args: Any) -> dict[str, Any]:
        return {
            "conclusions": [],
            "privileges": {"schema_usage": True, "table_select": True},
            "table": {"rls_enabled": True, "rls_applies_to_requested_role": True},
            "policies": [],
        }

    monkeypatch.setattr(overview, "_inspect_connection", detail)
    report = overview.inspect_schema("PRIVATE", "public", "reader", 1)
    assert snapshots == [1] and report["truncated"]
    assert len(report["tables"]) == 1 and report["result"] == "UNKNOWN"
    assert catalog.calls[-1] == (overview._TABLES, ("public", 2))
    assert "public" not in overview._TABLES


def test_overview_deadline_fails_without_claiming_partial_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(overview, "_with_database", lambda dsn, op: op(Catalog()))
    monkeypatch.setattr(overview, "_database", lambda *a: {"read_only": True})
    times = iter([0, 31])
    monkeypatch.setattr(overview.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(
        overview, "_inspect_connection", lambda *a: pytest.fail("Budget already exhausted")
    )
    with pytest.raises(InspectorError) as caught:
        overview.inspect_schema("PRIVATE", "public", "reader")
    assert caught.value.code == "OVERVIEW_TIME_LIMIT"
