import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from rls_doctor.cli.main import app


def saved_event(tmp_path: Path, *, resource: str = "documents", auth: bool = False) -> Path:
    path = tmp_path / "event.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "event_id": "00000000-0000-4000-8000-000000000001",
                "timestamp": "2026-10-26T10:00:00Z",
                "duration_ms": 0,
                "request": {
                    "method": "GET",
                    "api": "rest",
                    "resource": resource,
                    "filters": [{"column": "owner_id", "operator": "eq"}],
                },
                "response": {"status": 200, "row_count": 0, "error_kind": None},
                "context": {"authorization_present": auth, "apikey_present": True},
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def catalogs(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    import rls_doctor.cli.main as cli

    monkeypatch.setenv("RLS_DOCTOR_DATABASE_URL", "PRIVATE_DSN")
    monkeypatch.setattr(cli, "inspection_dsn", lambda *a, **kw: "checked")
    result: dict[str, Any] = {
        "table": {"rls_enabled": True},
        "policies": [],
        "conclusions": [
            {
                "code": "SELECT_PRIVILEGE_MISSING",
                "evidence": "OBSERVED",
                "summary": "Missing SELECT",
            }
        ],
        "limitations": [],
    }
    monkeypatch.setattr(cli, "inspect_table", lambda *a: result)
    return result


def run(path: Path, *args: str) -> Any:
    return CliRunner().invoke(
        app,
        [
            "diagnose",
            "public.documents",
            "--host",
            "db.example.com",
            "--approve-read-only",
            "--event",
            str(path),
            *args,
        ],
    )


@pytest.mark.parametrize("auth", [False, True])
def test_combines_independent_evidence_without_claiming_causality(
    tmp_path: Path, catalogs: dict[str, Any], auth: bool
) -> None:
    result = run(saved_event(tmp_path, auth=auth), "--format", "json")
    assert result.exit_code == 2
    report = json.loads(result.stdout)
    assert report["analysis_mode"] == "existing_database_and_capture"
    assert report["inspector"]["conclusions"][0]["code"] == "SELECT_PRIVILEGE_MISSING"
    assert report["identity"]["confirmed_role"] is None
    assert report["http"]["row_count"] == 0
    assert report["request_metadata"]["filters"] == [{"column": "owner_id", "operator": "eq"}]
    assert report["linkage"]["database_schema_and_role_confirmed"] is False
    codes = {f["code"] for f in report["findings"]}
    assert "CAPTURE_DATABASE_LINK_UNVERIFIED" in codes
    assert ("MISSING_EXPECTED_AUTH" in codes) is (not auth)
    assert "PRIVATE_DSN" not in result.stdout
    assert not any("Offline metadata analysis" in item for item in report["limitations"])


@pytest.mark.parametrize("language", ["en", "ru"])
def test_console_never_labels_capture_as_replay(
    tmp_path: Path, catalogs: dict[str, Any], language: str
) -> None:
    result = run(saved_event(tmp_path), "--language", language)
    assert result.exit_code == 2
    assert "MISSING_EXPECTED_AUTH" in result.stdout
    assert "SELECT_PRIVILEGE_MISSING" in result.stdout
    assert "CAPTURE_DATABASE_LINK_UNVERIFIED" in result.stdout
    assert "separate local replay" not in result.stdout
    assert "REST replay" not in result.stdout
    assert "тестовых строк" not in result.stdout
    assert "локальному replay" not in result.stdout


@pytest.mark.parametrize("invalid", [False, True])
def test_bad_event_is_rejected_before_dns_or_catalog_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, invalid: bool
) -> None:
    import rls_doctor.cli.main as cli

    path = saved_event(tmp_path, resource="other")
    if invalid:
        path.write_text('{"password":"PRIVATE_SECRET"}', encoding="utf-8")

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("Invalid/mismatching event must not open a connection")

    monkeypatch.setattr(cli, "inspection_dsn", forbidden)
    monkeypatch.setattr(cli, "inspect_table", forbidden)
    result = run(path, "--format", "json")
    assert result.exit_code == 3
    assert json.loads(result.stdout)["error"]["code"] == (
        "INVALID_EVENT" if invalid else "EVENT_RESOURCE_MISMATCH"
    )
    assert "PRIVATE_SECRET" not in result.stdout


def test_combined_report_exports_without_overwriting(
    tmp_path: Path, catalogs: dict[str, Any]
) -> None:
    event = saved_event(tmp_path)
    output = tmp_path / "report.json"
    first = run(event, "--format", "json", "--output", str(output))
    assert first.exit_code == 2
    original = output.read_bytes()
    assert json.loads(original)["linkage"]["evidence"] == "UNVERIFIED"
    second = run(event, "--format", "json", "--output", str(output))
    assert second.exit_code == 3
    assert output.read_bytes() == original
