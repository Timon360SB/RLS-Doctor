"""Credential onboarding must never weaken local replay or expose secrets."""

import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from rls_doctor.cli.main import app
from rls_doctor.core import credentials as onboarding
from rls_doctor.core.config import LocalEnvironment, ProjectConfig
from rls_doctor.core.errors import DoctorError
from rls_doctor.replay.scenarios import Scenario

session = importlib.import_module("rls_doctor.cli.session")


def status() -> dict[str, Any]:
    return {
        "API_URL": "http://127.0.0.1:54321",
        "DB_URL": "postgresql://postgres:PRIVATE_PASSWORD@127.0.0.1:54322/postgres",
        "PUBLISHABLE_KEY": "sb_publishable_PRIVATE_KEY",
        "JWT_SECRET": "PRIVATE_SIGNING_KEY",
        "SERVICE_ROLE_KEY": "PRIVATE_SERVICE_KEY",
    }


@pytest.mark.parametrize(
    "change",
    [
        {"API_URL": "http://example.com:54321"},
        {"API_URL": "http://127.0.0.1:54325"},
        {"API_URL": "http://127.0.0.2:54321"},
        {"DB_URL": "postgresql://postgres:PRIVATE_PASSWORD@example.com:54322/postgres"},
        {"DB_URL": "postgresql://postgres:PRIVATE_PASSWORD@127.0.0.1:54325/postgres"},
    ],
)
def test_mismatched_or_remote_status_is_rejected_without_secret_errors(
    change: dict[str, Any],
) -> None:
    with pytest.raises(DoctorError) as caught:
        onboarding.credential_values({**status(), **change}, LocalEnvironment(approved_local=True))
    assert "PRIVATE" not in str(caught.value)


def test_only_required_status_fields_are_loaded() -> None:
    values = onboarding.credential_values(status(), LocalEnvironment(approved_local=True))
    assert set(values) == {
        "RLS_DOCTOR_LOCAL_ANON_KEY",
        "RLS_DOCTOR_DATABASE_URL",
        "RLS_DOCTOR_LOCAL_JWT_SECRET",
    }
    assert "PRIVATE_SERVICE_KEY" not in str(values)


def test_disabled_config_never_runs_supabase(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session, "load_config", lambda path: ProjectConfig())
    monkeypatch.setattr(session, "local_status", lambda path: pytest.fail("No CLI before approval"))
    result = CliRunner().invoke(app, ["session", "--run"])
    assert result.exit_code == 3 and "LOCAL_APPROVAL_REQUIRED" in result.stdout


def test_environment_is_restored_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RLS_DOCTOR_LOCAL_ANON_KEY", "original")
    monkeypatch.delenv("RLS_DOCTOR_TEST_TOKEN", raising=False)
    with (
        pytest.raises(RuntimeError),
        onboarding.credentials(
            {
                "RLS_DOCTOR_LOCAL_ANON_KEY": "temporary",
                "RLS_DOCTOR_TEST_TOKEN": "temporary-token",
            }
        ),
    ):
        assert os.environ["RLS_DOCTOR_LOCAL_ANON_KEY"] == "temporary"
        raise RuntimeError("synthetic failure")
    assert os.environ["RLS_DOCTOR_LOCAL_ANON_KEY"] == "original"
    assert "RLS_DOCTOR_TEST_TOKEN" not in os.environ


def configure(monkeypatch: pytest.MonkeyPatch, identity: str = "anon") -> None:
    config = ProjectConfig(
        environment=LocalEnvironment(approved_local=True, confirm_identity=False)
    )
    scenario = Scenario.model_validate(
        {
            "version": 1,
            "name": "test",
            "request": {"resource": "documents"},
            "identity": {
                "type": identity,
                **({"token_env": "RLS_DOCTOR_TEST_TOKEN"} if identity == "authenticated" else {}),
            },
            "expect": {"status": 200, "row_count": 0},
        }
    )
    monkeypatch.setattr(session, "load_config", lambda path: config)
    monkeypatch.setattr(session, "load_scenario", lambda path: scenario)
    monkeypatch.setattr(session, "local_status", lambda path: status())
    monkeypatch.setattr(session, "local_headers", lambda *args: ({}, None))
    monkeypatch.delenv("RLS_DOCTOR_TEST_TOKEN", raising=False)


@pytest.mark.parametrize("result,code", [("PASS", 0), ("FAIL", 1), ("UNKNOWN", 2), ("ERROR", 3)])
def test_once_preserves_diagnostic_exit_code_and_restores_secrets(
    monkeypatch: pytest.MonkeyPatch, result: str, code: int
) -> None:
    configure(monkeypatch)
    monkeypatch.setattr(session, "replay", lambda *args, **kwargs: {"result": result})
    monkeypatch.setenv("RLS_DOCTOR_DATABASE_URL", "original")
    response = CliRunner().invoke(app, ["session", "--run"])
    assert response.exit_code == code
    assert os.environ["RLS_DOCTOR_DATABASE_URL"] == "original"
    assert "PRIVATE" not in response.stdout


def test_signup_requires_explicit_consent_in_once_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    configure(monkeypatch, "authenticated")
    monkeypatch.setattr(
        session, "create_identity", lambda *a, **k: pytest.fail("No implicit signup")
    )
    result = CliRunner().invoke(app, ["session", "--run"])
    assert result.exit_code == 3 and "TEST_IDENTITY_REQUIRED" in result.stdout


def test_interactive_decline_never_creates_user(monkeypatch: pytest.MonkeyPatch) -> None:
    configure(monkeypatch, "authenticated")
    monkeypatch.setattr(session, "create_identity", lambda *a, **k: pytest.fail("Signup declined"))
    result = CliRunner().invoke(app, ["session"], input="n\n")
    assert result.exit_code == 3 and "TEST_IDENTITY_REQUIRED" in result.stdout


def test_explicit_signup_token_is_scoped_and_no_config_reread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure(monkeypatch, "authenticated")
    monkeypatch.setattr(session, "create_identity", lambda *a, **k: "PRIVATE_NEW_TOKEN")
    count = 0

    def load(path: Path) -> ProjectConfig:
        nonlocal count
        count += 1
        assert count == 1, "Never re-read mutable endpoints after credentials are bound"
        return ProjectConfig(
            environment=LocalEnvironment(approved_local=True, confirm_identity=False)
        )

    monkeypatch.setattr(session, "load_config", load)

    def replay(*args: Any, **kwargs: Any) -> dict[str, Any]:
        assert os.environ["RLS_DOCTOR_TEST_TOKEN"] == "PRIVATE_NEW_TOKEN"
        return {"result": "UNKNOWN"}

    monkeypatch.setattr(session, "replay", replay)
    result = CliRunner().invoke(app, ["session", "--run", "--create-test-user"])
    assert result.exit_code == 2 and "PRIVATE" not in result.stdout
    assert "RLS_DOCTOR_TEST_TOKEN" not in os.environ


def test_local_status_errors_never_echo_raw_cli_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "supabase").mkdir()
    (tmp_path / "supabase/config.toml").write_text('project_id = "synthetic"', encoding="utf-8")
    monkeypatch.setattr(onboarding, "find_cli", lambda: "supabase")
    monkeypatch.setattr(
        onboarding.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(
            returncode=1, stdout=b"PRIVATE_CLI_SECRET", stderr=b"PRIVATE_CLI_SECRET"
        ),
    )
    with pytest.raises(DoctorError) as caught:
        onboarding.local_status(tmp_path)
    assert "PRIVATE" not in str(caught.value)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(302, headers={"location": "https://example.com"}),
        httpx.Response(200, json={"access_token": "x" * 66000}),
        httpx.Response(200, json={"error": "PRIVATE_RESPONSE"}),
    ],
)
def test_signup_rejects_redirects_oversize_and_missing_session(
    response: httpx.Response, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(onboarding, "local_headers", lambda *a: ({"apikey": "synthetic"}, None))
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: response), follow_redirects=False
    ) as client:
        with pytest.raises(DoctorError) as caught:
            onboarding.create_identity(
                LocalEnvironment(approved_local=True), approved=True, client=client
            )
    assert "PRIVATE" not in str(caught.value)


def test_signup_never_sends_a_request_without_consent() -> None:
    with httpx.Client(
        transport=httpx.MockTransport(lambda req: pytest.fail("No request before consent"))
    ) as client:
        with pytest.raises(DoctorError):
            onboarding.create_identity(
                LocalEnvironment(approved_local=True), approved=False, client=client
            )


@pytest.mark.parametrize(
    "payload",
    [b"PRIVATE_NON_JSON", b"[]", b"x" * 65537],
    ids=["invalid-json", "wrong-shape", "oversized"],
)
def test_status_invalid_json_and_size_limits_are_private(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: bytes
) -> None:
    (tmp_path / "supabase").mkdir()
    (tmp_path / "supabase/config.toml").write_text("", encoding="utf-8")
    monkeypatch.setattr(onboarding, "find_cli", lambda: "supabase")
    monkeypatch.setattr(
        onboarding.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=payload, stderr=b"PRIVATE_STDERR"),
    )
    with pytest.raises(DoctorError) as caught:
        onboarding.local_status(tmp_path)
    assert "PRIVATE" not in str(caught.value)


def test_stale_signing_key_is_cleared_and_restored(monkeypatch: pytest.MonkeyPatch) -> None:
    configure(monkeypatch)
    current = status()
    del current["JWT_SECRET"]
    monkeypatch.setattr(session, "local_status", lambda path: current)
    monkeypatch.setenv("RLS_DOCTOR_LOCAL_JWT_SECRET", "PRIVATE_STALE_KEY")

    def replay(*args: Any, **kwargs: Any) -> dict[str, Any]:
        assert "RLS_DOCTOR_LOCAL_JWT_SECRET" not in os.environ
        return {"result": "UNKNOWN"}

    monkeypatch.setattr(session, "replay", replay)
    result = CliRunner().invoke(app, ["session", "--run"])
    assert result.exit_code == 2
    assert os.environ["RLS_DOCTOR_LOCAL_JWT_SECRET"] == "PRIVATE_STALE_KEY"
    assert "PRIVATE" not in result.stdout


def test_cancelled_menu_restores_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    configure(monkeypatch)
    monkeypatch.delenv("RLS_DOCTOR_LOCAL_ANON_KEY", raising=False)
    response = CliRunner().invoke(app, ["session"], input="")
    assert response.exit_code == 0
    assert "RLS_DOCTOR_LOCAL_ANON_KEY" not in os.environ
    assert "PRIVATE" not in response.stdout


@pytest.mark.parametrize("language", ["en", "ru"])
@pytest.mark.parametrize("outcome,code", [("PASS", 0), ("FAIL", 1), ("UNKNOWN", 2), ("ERROR", 3)])
def test_json_session_is_clean_and_preserves_exit_codes(
    monkeypatch: pytest.MonkeyPatch, language: str, outcome: str, code: int
) -> None:
    configure(monkeypatch)
    monkeypatch.setattr(session, "replay", lambda *a, **kw: {"result": outcome})
    result = CliRunner().invoke(
        app, ["session", "--run", "--format", "json", "--language", language]
    )
    assert result.exit_code == code
    assert json.loads(result.stdout) == {"result": outcome}
    assert "PRIVATE" not in result.stdout


def test_json_requires_unattended_mode_before_loading_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session, "local_status", lambda *a: pytest.fail("No credential loading"))
    result = CliRunner().invoke(app, ["session", "--format", "json"])
    assert result.exit_code == 3
    assert json.loads(result.stdout)["error"]["code"] == "SESSION_JSON_MODE"


def test_json_missing_identity_is_a_structured_error(monkeypatch: pytest.MonkeyPatch) -> None:
    configure(monkeypatch, "authenticated")
    result = CliRunner().invoke(app, ["session", "--run", "--format", "json"])
    assert result.exit_code == 3
    assert json.loads(result.stdout)["error"]["code"] == "TEST_IDENTITY_REQUIRED"


@pytest.mark.parametrize("format", ["console", "json"])
def test_json_interruption_is_not_reported_as_a_pass(
    monkeypatch: pytest.MonkeyPatch, format: str
) -> None:
    configure(monkeypatch)
    monkeypatch.delenv("RLS_DOCTOR_DATABASE_URL", raising=False)

    def interrupt(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise KeyboardInterrupt

    monkeypatch.setattr(session, "replay", interrupt)
    result = CliRunner().invoke(app, ["session", "--run", "--format", format])
    assert result.exit_code == 3
    if format == "json":
        assert json.loads(result.stdout)["error"]["code"] == "SESSION_CANCELLED"
    else:
        assert "SESSION_CANCELLED" in result.stdout
    assert "RLS_DOCTOR_DATABASE_URL" not in os.environ


def test_status_loader_returns_only_required_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "supabase").mkdir()
    (tmp_path / "supabase/config.toml").write_text("", encoding="utf-8")
    monkeypatch.setattr(onboarding, "find_cli", lambda: "supabase")
    data = {**status(), "UNNEEDED_DEBUG": "PRIVATE_DEBUG"}
    monkeypatch.setattr(
        onboarding.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps(data).encode(), stderr=b""),
    )
    filtered = onboarding.local_status(tmp_path)
    assert set(filtered) == {"API_URL", "DB_URL", "PUBLISHABLE_KEY", "JWT_SECRET"}
    assert "SERVICE_ROLE_KEY" not in filtered and "UNNEEDED_DEBUG" not in filtered


def capture_data(resource: str = "documents") -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "event_id": "00000000-0000-4000-8000-000000000001",
        "timestamp": "2026-10-25T00:00:00Z",
        "duration_ms": 1,
        "request": {
            "method": "GET",
            "api": "rest",
            "resource": resource,
            "filters": [{"column": "owner_id", "operator": "eq"}],
        },
        "response": {"status": 200, "row_count": 0, "error_kind": None},
        "context": {"authorization_present": True, "apikey_present": True},
    }


def test_invalid_capture_is_rejected_before_loading_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure(monkeypatch)
    monkeypatch.setattr(
        session, "local_status", lambda p: pytest.fail("No CLI for invalid capture")
    )
    event_path = tmp_path / "invalid.json"
    event_path.write_text('{"raw_token":"PRIVATE_EVENT_SECRET"}', encoding="utf-8")
    result = CliRunner().invoke(
        app, ["session", "--run", "--format", "json", "--event", str(event_path)]
    )
    assert result.exit_code == 3
    assert json.loads(result.stdout)["error"]["code"] == "INVALID_EVENT"
    assert "PRIVATE_EVENT_SECRET" not in result.stdout


def test_mismatched_capture_is_rejected_before_loading_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure(monkeypatch)
    monkeypatch.setattr(
        session, "local_status", lambda p: pytest.fail("No CLI for mismatched capture")
    )
    event_path = tmp_path / "other.json"
    event_path.write_text(json.dumps(capture_data("other_documents")), encoding="utf-8")
    result = CliRunner().invoke(
        app, ["session", "--run", "--format", "json", "--event", str(event_path)]
    )
    assert result.exit_code == 3
    assert json.loads(result.stdout)["error"]["code"] == "EVENT_MISMATCH"


def test_capture_is_attached_without_reconstructing_filter_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure(monkeypatch)
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(capture_data()), encoding="utf-8")

    def replay(scenario: Any, config: Any, event: Any, **kwargs: Any) -> dict[str, Any]:
        assert event.request.resource == "documents"
        assert not scenario.filters  # capture operators never become fabricated replay values
        return {"result": "UNKNOWN", "event_id": event.event_id}

    monkeypatch.setattr(session, "replay", replay)
    result = CliRunner().invoke(
        app, ["session", "--run", "--format", "json", "--event", str(event_path)]
    )
    assert result.exit_code == 2
    assert json.loads(result.stdout)["event_id"] == capture_data()["event_id"]
