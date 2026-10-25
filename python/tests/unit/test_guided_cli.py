"""Guided setup and presentation must preserve safety and diagnostic evidence."""

import io
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from rich.console import Console
from typer.testing import CliRunner

from rls_doctor.cli.main import app
from rls_doctor.core.config import load_config
from rls_doctor.replay.scenarios import load_scenario
from rls_doctor.reports import console as presentation


def answers(*, approval: str = "n", save: str = "y", api: str = "") -> str:
    return "\n".join([api, "", "", "", "", "", approval, save]) + "\n"


@pytest.mark.parametrize("language", ["en", "ru"])
def test_guided_setup_is_offline_disabled_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, language: str
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Configuration must not connect to any service")

    monkeypatch.setattr(httpx, "Client", forbidden)
    monkeypatch.setenv("RLS_DOCTOR_TEST_TOKEN", "PRIVATE_TOKEN")
    result = CliRunner().invoke(
        app,
        ["init", "--interactive", "--directory", str(tmp_path), "--language", language],
        input=answers(),
    )
    assert result.exit_code == 0, result.stdout
    config = load_config(tmp_path / "rls-doctor.toml")
    scenario = load_scenario(tmp_path / "documents.yaml")
    assert config.environment.approved_local is False
    assert config.environment.confirm_identity is False
    assert config.environment.resources == ["documents"]
    assert scenario.identity.type == "authenticated"
    assert scenario.identity.token_env == "RLS_DOCTOR_TEST_TOKEN"
    assert scenario.expect.row_count == 1
    assert "PRIVATE_TOKEN" not in result.stdout
    assert all("PRIVATE_TOKEN" not in p.read_text(encoding="utf-8") for p in tmp_path.iterdir())


def test_approval_requires_explicit_yes_and_existing_files_are_preserved(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app, ["init", "--interactive", "--directory", str(tmp_path)], input=answers(approval="y")
    )
    assert result.exit_code == 0
    assert load_config(tmp_path / "rls-doctor.toml").environment.approved_local
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    again = runner.invoke(app, ["init", "--interactive", "--directory", str(tmp_path)])
    assert again.exit_code == 3 and "INIT_EXISTS" in again.stdout
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}


def test_cancel_does_not_create_files(tmp_path: Path) -> None:
    destination = tmp_path / "new"
    result = CliRunner().invoke(
        app, ["init", "--interactive", "--directory", str(destination)], input=answers(save="n")
    )
    assert result.exit_code == 0
    assert not destination.exists()


@pytest.mark.parametrize(
    "api",
    [
        "https://127.0.0.1:54321",
        "http://example.com:54321",
        "http://localhost:54321",
        "http://127.0.0.1:54321/rest/v1",
    ],
)
def test_unsafe_destination_cannot_be_approved(tmp_path: Path, api: str) -> None:
    # EOF after rejection aborts without files; even a later yes cannot save unsafe input.
    result = CliRunner().invoke(
        app,
        ["init", "--interactive", "--directory", str(tmp_path)],
        input="\n".join([api, "", "", "", "", ""]) + "\n",
    )
    assert result.exit_code == 0
    assert not list(tmp_path.iterdir())
    assert "numeric loopback" in result.stdout


def report() -> dict[str, Any]:
    return {
        "result": "UNKNOWN",
        "analysis_mode": "capture_only",
        "identity": {"expected_role": "authenticated", "confirmed_role": None},
        "http": {"status": 200, "row_count": 0},
        "findings": [
            {
                "code": "EMPTY_RESULT_AMBIGUOUS",
                "evidence": "UNVERIFIED",
                "summary": "Zero rows may reflect filters, missing data or RLS; cause is unknown.",
            }
        ],
        "limitations": ["Offline metadata analysis: no network request ran."],
    }


@pytest.mark.parametrize("language", ["en", "ru"])
def test_json_contract_is_independent_of_language(
    monkeypatch: pytest.MonkeyPatch, language: str
) -> None:
    output = io.StringIO()
    monkeypatch.setattr(presentation, "Console", lambda **kw: Console(file=output, width=50))
    data = report()
    presentation.render(data, "json", language)
    assert json.loads(output.getvalue()) == data


@pytest.mark.parametrize("language", ["en", "ru"])
def test_console_keeps_unknown_role_and_empty_result_uncertainty(
    monkeypatch: pytest.MonkeyPatch, language: str
) -> None:
    output = io.StringIO()
    monkeypatch.setattr(presentation, "Console", lambda **kw: Console(file=output, width=110))
    data = report()
    presentation.render(data, language=language)
    rendered = output.getvalue()
    assert "UNKNOWN" in rendered and "UNVERIFIED" in rendered
    assert "PASS" not in rendered
    assert "EMPTY_RESULT_AMBIGUOUS" in rendered
    assert ("Confirmed role" if language == "en" else "Подтверждённая роль") in rendered
    assert ("cause is unknown" if language == "en" else "причина не установлена") in rendered


def test_doctor_does_not_call_opted_out_identity_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rls_doctor.cli.main as cli

    CliRunner().invoke(
        app, ["init", "--interactive", "--directory", str(tmp_path)], input=answers(approval="y")
    )
    monkeypatch.setenv(
        "RLS_DOCTOR_DATABASE_URL", "postgresql://reader:synthetic@127.0.0.1:54322/postgres"
    )
    monkeypatch.setattr(
        cli,
        "doctor_database",
        lambda dsn: {
            "database": {"supported": True},
            "required_roles": {"anon": True, "authenticated": True},
        },
    )
    monkeypatch.setattr(cli, "inspect_table", lambda *args: {"conclusions": []})

    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Disabled probe must not issue fixture RPC or claim API availability")

    monkeypatch.setattr(httpx, "Client", forbidden)
    result = CliRunner().invoke(
        app, ["doctor", "--config", str(tmp_path / "rls-doctor.toml"), "--format", "json"]
    )
    assert result.exit_code == 2
    data = json.loads(result.stdout)
    assert data["result"] == "UNKNOWN" and data["http_status"] is None
    assert "unverified" in " ".join(data["limitations"])


def test_console_does_not_dump_unexpected_nested_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    output = io.StringIO()
    monkeypatch.setattr(presentation, "Console", lambda **kw: Console(file=output, width=100))
    data = report()
    data["inspector"] = {
        "table": {"rls_enabled": True},
        "policies": [],
        "private_debug": "PRIVATE_PASSWORD",
        "conclusions": [],
    }
    data["debug"] = "PRIVATE_TOKEN"
    presentation.render(data)
    assert "PRIVATE" not in output.getvalue()
    assert "RLS enabled" in output.getvalue()


def test_replay_catalog_caveats_keep_their_source_context(monkeypatch: pytest.MonkeyPatch) -> None:
    output = io.StringIO()
    monkeypatch.setattr(presentation, "Console", lambda **kw: Console(file=output, width=150))
    data = report()
    data["identity"]["confirmed_role"] = "authenticated"
    data["http"]["row_count"] = 2
    data["inspector"] = {
        "policies": [],
        "conclusions": [
            {
                "code": "EXECUTED_ROLE_UNCONFIRMED",
                "evidence": "UNVERIFIED",
                "summary": "The requested role has not been confirmed by catalog inspection alone.",
            },
            {
                "code": "ROW_VISIBILITY_UNKNOWN",
                "evidence": "UNVERIFIED",
                "summary": "No row result was observed.",
            },
        ],
    }
    original = json.loads(json.dumps(data))
    presentation.render(data)
    rendered = output.getvalue()
    assert "see the request role above" in rendered
    assert "come from REST replay" in rendered
    assert "No row result was observed" not in rendered
    assert data == original  # presentation must never rewrite machine evidence


def test_cli_version_is_available_without_configuration() -> None:
    from rls_doctor import __version__

    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "RLS Doctor " + __version__


def test_doctor_selects_public_schema_for_the_fixed_trusted_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rls_doctor.cli.main as cli
    from rls_doctor.core.config import LocalEnvironment, ProjectConfig

    config = ProjectConfig(environment=LocalEnvironment(approved_local=True))
    monkeypatch.setattr(cli, "load_config", lambda path: config)
    monkeypatch.setenv(
        "RLS_DOCTOR_DATABASE_URL", "postgresql://reader:synthetic@127.0.0.1:54322/postgres"
    )
    monkeypatch.setattr(
        cli,
        "doctor_database",
        lambda dsn: {
            "database": {"supported": True},
            "required_roles": {"anon": True, "authenticated": True},
        },
    )
    monkeypatch.setattr(cli, "inspect_table", lambda *a: {"conclusions": []})
    monkeypatch.setattr(cli, "local_headers", lambda *a: ({}, None))
    original_client = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("accept-profile") != "public":
            return httpx.Response(404, json={"code": "PGRST202"})
        return httpx.Response(200, json={"role": "anon", "uid": None})

    monkeypatch.setattr(
        httpx, "Client", lambda **kw: original_client(**kw, transport=httpx.MockTransport(handler))
    )
    result = CliRunner().invoke(app, ["doctor", "--format", "json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["result"] == "PASS"


@pytest.mark.parametrize(
    "index,bad",
    [
        (0, "https://example.com"),
        (1, "0"),
        (2, "invalid.table.name"),
        (3, "service_role"),
        (4, "999"),
        (5, "-2"),
    ],
)
def test_wizard_retries_only_the_invalid_field(tmp_path: Path, index: int, bad: str) -> None:
    fields = ["", "", "", "", "", ""]
    fields.insert(index, bad)
    result = CliRunner().invoke(
        app,
        ["init", "--interactive", "--directory", str(tmp_path)],
        input="\n".join([*fields, "n", "y"]) + "\n",
    )
    assert result.exit_code == 0
    assert load_config(tmp_path / "rls-doctor.toml").environment.approved_local is False
    labels = [
        "Local API URL",
        "Local PostgreSQL port",
        "Test table (schema.table)",
        "Test identity (anon/authenticated)",
        "Expected HTTP status",
        "Expected number of rows",
    ]
    for current, label in enumerate(labels):
        assert result.stdout.count(label) == (2 if current == index else 1)


def test_http_error_wizard_does_not_expect_rows_by_default(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app, ["init", "--interactive", "--directory", str(tmp_path)], input="\n\n\n\n403\n\nn\ny\n"
    )
    assert result.exit_code == 0
    scenario = load_scenario(tmp_path / "documents.yaml")
    assert scenario.expect.status == 403 and scenario.expect.row_count is None


def test_doctor_reports_missing_roles_without_reading_app_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rls_doctor.cli.main as cli
    from rls_doctor.core.config import LocalEnvironment, ProjectConfig

    env = LocalEnvironment(approved_local=True, confirm_identity=False, resources=["tasks"])
    monkeypatch.setattr(cli, "load_config", lambda path: ProjectConfig(environment=env))
    monkeypatch.setenv(
        "RLS_DOCTOR_DATABASE_URL", "postgresql://reader:synthetic@127.0.0.1:54322/postgres"
    )
    monkeypatch.setattr(
        cli,
        "doctor_database",
        lambda dsn: {
            "database": {"supported": True},
            "required_roles": {"anon": True, "authenticated": False},
        },
    )
    monkeypatch.setattr(
        cli, "inspect_table", lambda *args: pytest.fail("Doctor must not assume public.tasks")
    )
    result = CliRunner().invoke(app, ["doctor", "--format", "json"])
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert {item["check"]: item["result"] for item in data["checks"]}[
        "role_authenticated"
    ] == "FAIL"
