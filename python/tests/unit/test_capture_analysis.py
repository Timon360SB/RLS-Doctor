import json
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest
from typer.testing import CliRunner

from rls_doctor.cli.main import app


def event() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "event_id": "00000000-0000-4000-8000-000000000001",
        "timestamp": "2026-10-23T10:00:00Z",
        "duration_ms": 0,
        "request": {"method": "GET", "api": "rest", "resource": "documents", "filters": []},
        "response": {"status": 200, "row_count": 0, "error_kind": None},
        "context": {"authorization_present": False, "apikey_present": True},
    }


def invoke(tmp_path: Path, data: dict[str, Any], *args: str) -> Any:
    path = tmp_path / "event.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return CliRunner().invoke(app, ["analyze", str(path), *args])


def test_offline_analysis_needs_no_database_network_config_or_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Offline analysis must not open a network/database connection.")

    monkeypatch.setattr(httpx, "Client", forbidden)
    monkeypatch.setattr(psycopg, "connect", forbidden)
    for name in ("RLS_DOCTOR_LOCAL_ANON_KEY", "RLS_DOCTOR_DATABASE_URL", "RLS_DOCTOR_TEST_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    result = invoke(tmp_path, event(), "--expected-role", "authenticated", "--format", "json")
    assert result.exit_code == 2
    report = json.loads(result.stdout)
    assert report["result"] == "UNKNOWN"
    assert report["analysis_mode"] == "capture_only"
    assert report["identity"]["confirmed_role"] is None
    findings = {item["code"]: item for item in report["findings"]}
    assert findings["MISSING_EXPECTED_AUTH"]["evidence"] == "OBSERVED"
    assert findings["EMPTY_RESULT_AMBIGUOUS"]["evidence"] == "UNVERIFIED"


def test_header_presence_never_proves_authentication_or_a_pass(tmp_path: Path) -> None:
    data = event()
    data["context"]["authorization_present"] = True
    data["response"]["row_count"] = 1
    result = invoke(tmp_path, data, "--expected-role", "authenticated", "--format", "json")
    assert result.exit_code == 2
    report = json.loads(result.stdout)
    assert report["identity"]["confirmed_role"] is None
    findings = {item["code"]: item for item in report["findings"]}
    assert findings["AUTHORIZATION_CONTEXT_UNVERIFIED"]["evidence"] == "UNVERIFIED"
    assert "MISSING_EXPECTED_AUTH" not in findings
    assert "PASS" not in result.stdout


@pytest.mark.parametrize(
    ("status", "kind", "code"),
    [(None, "network", "NETWORK_FAILURE_OBSERVED"), (None, None, "HTTP_STATUS_UNAVAILABLE")],
)
def test_missing_status_does_not_invent_an_http_response_or_network_cause(
    tmp_path: Path, status: int | None, kind: str | None, code: str
) -> None:
    data = event()
    data["response"] = {"status": status, "row_count": None, "error_kind": kind}
    result = invoke(tmp_path, data, "--format", "json")
    assert result.exit_code == 2
    report = json.loads(result.stdout)
    codes = {item["code"] for item in report["findings"]}
    assert code in codes
    assert "HTTP_OBSERVED" not in codes
    assert report["http"]["status"] is None


@pytest.mark.parametrize("role", [None, "anon"])
def test_no_authenticated_expectation_does_not_invent_a_missing_auth_problem(
    tmp_path: Path, role: str | None
) -> None:
    args = ["--format", "json"]
    if role is not None:
        args += ["--expected-role", role]
    result = invoke(tmp_path, event(), *args)
    assert result.exit_code == 2
    report = json.loads(result.stdout)
    assert report["identity"]["expected_role"] == role
    assert all(item["code"] != "MISSING_EXPECTED_AUTH" for item in report["findings"])


def test_invalid_event_is_an_error_and_never_echoes_secrets(tmp_path: Path) -> None:
    data = event()
    data["Authorization"] = "Bearer PRIVATE_TOKEN_MUST_NOT_LEAK"
    result = invoke(tmp_path, data, "--format", "json")
    assert result.exit_code == 3
    assert json.loads(result.stdout)["error"]["code"] == "INVALID_EVENT"
    assert "PRIVATE_TOKEN" not in result.stdout


def test_console_explains_unknown_and_missing_file_is_an_error(tmp_path: Path) -> None:
    result = invoke(tmp_path, event(), "--expected-role", "authenticated")
    assert result.exit_code == 2
    assert "Result: UNKNOWN" in result.stdout
    assert "Offline metadata analysis" in result.stdout
    missing = CliRunner().invoke(
        app, ["analyze", str(tmp_path / "missing.json"), "--format", "json"]
    )
    assert missing.exit_code == 3
    assert json.loads(missing.stdout)["error"]["code"] == "INVALID_EVENT"
