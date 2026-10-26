"""User journeys and privacy; mocks are not live database evidence."""

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from psycopg.conninfo import conninfo_to_dict
from typer.testing import CliRunner

from rls_doctor.cli.main import app
from rls_doctor.core.profiles import DatabaseProfile, save_profile
from rls_doctor.postgres.inspector import InspectorError


def saved(tmp_path: Path) -> Path:
    path = tmp_path / "project.json"
    save_profile(
        DatabaseProfile(
            project_id=str(uuid4()),
            host="db.example.com",
            port=5432,
            database="postgres",
            user="reader",
            table="public.documents",
            role="authenticated",
        ),
        path,
    )
    return path


def detail(*args: Any) -> dict[str, Any]:
    return {"policies": [], "conclusions": [], "limitations": []}


@pytest.mark.parametrize("language", ["en", "ru"])
def test_connect_fields_preserve_password_quoting_and_never_persist_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, language: str
) -> None:
    import rls_doctor.cli.project as wizard

    monkeypatch.delenv("RLS_DOCTOR_DATABASE_URL", raising=False)
    password = r"PRIVATE p'a\ss=;"
    seen = []

    def checked(raw: str, host: str, **kwargs: Any) -> str:
        values = conninfo_to_dict(raw)
        assert values["password"] == password and values["sslmode"] == "verify-full"
        assert values["port"] == "6543" and host == "db.example.com"
        seen.append(values)
        return raw

    monkeypatch.setattr(wizard, "inspection_dsn", checked)
    monkeypatch.setattr(
        wizard,
        "discover_database",
        lambda *a: {
            "tables": [{"schema": "public", "name": "documents"}],
            "roles": [{"name": "authenticated"}],
            "truncated": False,
        },
    )
    monkeypatch.setattr(wizard, "inspect_table", detail)
    path = tmp_path / "project.json"
    result = CliRunner().invoke(
        app,
        ["connect", "--profile", str(path), "--language", language],
        input="db.example.com\ny\n6543\npostgres\nreader\n\n" + password + "\n1\n1\n\n",
    )
    assert result.exit_code == 0, result.output
    assert len(seen) == 1
    assert "PRIVATE" not in result.output + path.read_text()


def test_field_correction_keeps_valid_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rls_doctor.cli.project as wizard

    monkeypatch.delenv("RLS_DOCTOR_DATABASE_URL", raising=False)

    def checked(raw: str, *args: Any, **kwargs: Any) -> str:
        values = conninfo_to_dict(raw)
        assert values["port"] == "5432" and values["dbname"] == "postgres"
        assert values["sslmode"] == "disable"
        return raw

    monkeypatch.setattr(wizard, "inspection_dsn", checked)
    monkeypatch.setattr(
        wizard,
        "discover_database",
        lambda *a: {
            "tables": [{"schema": "public", "name": "documents"}],
            "roles": [{"name": "authenticated"}],
            "truncated": False,
        },
    )
    monkeypatch.setattr(wizard, "inspect_table", detail)
    result = CliRunner().invoke(
        app,
        ["connect", "--profile", str(tmp_path / "p.json")],
        input="127.0.0.1\ny\n70000\n5432\ninvalid name\npostgres\nreader\nPRIVATE\n1\n1\n\n",
    )
    assert result.exit_code == 0, result.output
    assert result.output.count("Database hostname or IP") == 1
    assert "PRIVATE" not in result.output


def test_start_reuses_credentials_and_exports_selected_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rls_doctor.cli.start as menu

    path = saved(tmp_path)
    original = path.read_bytes()
    opened = []

    def opened_once(*args: Any, **kwargs: Any) -> str:
        opened.append(1)
        return "PRIVATE_DSN"

    monkeypatch.setattr(menu, "profile_dsn", opened_once)
    monkeypatch.setattr(menu, "inspect_table", detail)
    monkeypatch.setattr(
        menu,
        "discover_database",
        lambda *a: {
            "tables": [{"schema": "custom", "name": "orders"}],
            "roles": [{"name": "anon"}],
            "truncated": False,
        },
    )
    inspected = []

    def overview(dsn: str, schema: str, role: str) -> dict[str, Any]:
        inspected.append((schema, role))
        return {
            "result": "UNKNOWN",
            "analysis_mode": "schema_catalog_overview",
            "schema": schema,
            "requested_role": role,
            "tables": [],
            "truncated": False,
        }

    monkeypatch.setattr(menu, "inspect_schema", overview)
    destination = tmp_path / "report.json"
    result = CliRunner().invoke(
        app,
        ["start", "--profile", str(path)],
        input="1\n3\n1\n1\n5\n2\n4\n" + str(destination) + "\n0\n",
    )
    assert result.exit_code == 0, result.output
    assert opened == [1] and inspected == [("custom", "anon")]
    assert path.read_bytes() == original
    report = json.loads(destination.read_text())
    assert report["result"] == "UNKNOWN" and report["diagnosis_id"]
    assert "PRIVATE" not in destination.read_text() + result.output
    assert "обзор схемы" in result.output


def test_start_exit_and_language_switch_need_no_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rls_doctor.cli.start as menu

    monkeypatch.setattr(menu, "profile_dsn", lambda *a, **kw: pytest.fail("No connection needed"))
    result = CliRunner().invoke(app, ["start", "--profile", str(saved(tmp_path))], input="5\n0\n")
    assert result.exit_code == 0 and "Ваша база" in result.output


def test_start_once_preserves_unknown_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import rls_doctor.cli.start as menu

    monkeypatch.setattr(menu, "profile_dsn", lambda *a, **kw: "PRIVATE_DSN")
    monkeypatch.setattr(menu, "inspect_table", detail)
    result = CliRunner().invoke(app, ["start", "--once", "--profile", str(saved(tmp_path))])
    assert result.exit_code == 2 and "UNKNOWN" in result.output


def test_start_failure_explained_and_menu_survives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rls_doctor.cli.start as menu

    monkeypatch.setattr(menu, "profile_dsn", lambda *a, **kw: "PRIVATE_DSN")

    def reject(*args: Any) -> None:
        raise InspectorError(
            "POSTGRES_INSPECTION_FAILED", "Fixed message.", "42501", phase="catalog"
        )

    monkeypatch.setattr(menu, "inspect_table", reject)
    result = CliRunner().invoke(app, ["start", "--profile", str(saved(tmp_path))], input="1\n0\n")
    assert result.exit_code == 0 and "42501" in result.output
    assert "PRIVATE" not in result.output


def test_no_args_noninteractive_shows_help(monkeypatch: pytest.MonkeyPatch) -> None:
    import rls_doctor.cli.main as cli

    monkeypatch.setattr(cli, "run_start", lambda *a, **kw: pytest.fail("Must not prompt"))
    result = CliRunner().invoke(app, [])
    assert result.exit_code == 0 and "start" in result.output and "overview" in result.output


def test_overview_json_requires_approval(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import rls_doctor.cli.connection as connection

    monkeypatch.setattr(connection, "inspection_dsn", lambda *a, **kw: pytest.fail("No DNS"))
    result = CliRunner().invoke(
        app, ["overview", "--profile", str(saved(tmp_path)), "--format", "json"]
    )
    assert result.exit_code == 3
    assert json.loads(result.output)["error"]["code"] == "DATABASE_APPROVAL_REQUIRED"


def test_overview_json_export_matches_stdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rls_doctor.cli.main as cli

    monkeypatch.setattr(cli, "profile_dsn", lambda *a, **kw: "PRIVATE_DSN")
    monkeypatch.setattr(
        cli,
        "inspect_schema",
        lambda *a: {"result": "UNKNOWN", "tables": [], "analysis_mode": "schema_catalog_overview"},
    )
    destination = tmp_path / "report.json"
    result = CliRunner().invoke(
        app,
        [
            "overview",
            "--profile",
            str(saved(tmp_path)),
            "--format",
            "json",
            "--approve-read-only",
            "--output",
            str(destination),
        ],
    )
    assert result.exit_code == 2
    assert json.loads(result.output) == json.loads(destination.read_text())
    assert "PRIVATE" not in result.output


@pytest.mark.parametrize(
    "options", [["--schema", "public;DROP"], ["--role", "reader;DROP"], ["--limit", "51"]]
)
def test_overview_rejects_invalid_scope_before_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, options: list[str]
) -> None:
    import rls_doctor.cli.main as cli

    monkeypatch.setattr(
        cli, "profile_dsn", lambda *a, **kw: pytest.fail("Reject before connection")
    )
    result = CliRunner().invoke(app, ["overview", "--profile", str(saved(tmp_path)), *options])
    assert result.exit_code in {2, 3}


def test_profile_approval_precedes_secret_prompt_and_dns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rls_doctor.cli.connection as connection
    from rls_doctor.core.errors import DoctorError
    from rls_doctor.core.profiles import load_profile

    monkeypatch.setattr(connection.typer, "confirm", lambda *a, **kw: False)
    monkeypatch.setattr(
        connection.typer, "prompt", lambda *a, **kw: pytest.fail("No secret before approval")
    )
    monkeypatch.setattr(
        connection, "inspection_dsn", lambda *a, **kw: pytest.fail("No DNS before approval")
    )
    with pytest.raises(DoctorError) as caught:
        connection.profile_dsn(load_profile(saved(tmp_path)), "en")
    assert caught.value.code == "DATABASE_APPROVAL_REQUIRED"


def test_start_once_cancel_is_not_success(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app, ["start", "--once", "--profile", str(saved(tmp_path))], input=""
    )
    assert result.exit_code == 3 and "DATABASE_CANCELLED" in result.output


def test_start_reconnect_forgets_previous_dsn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rls_doctor.cli.start as menu

    opened = []

    def open_profile(*args: Any, **kwargs: Any) -> str:
        opened.append(len(opened))
        return "PRIVATE_" + str(len(opened))

    seen = []

    def inspect(dsn: str, *args: Any) -> dict[str, Any]:
        seen.append(dsn)
        return detail()

    monkeypatch.setattr(menu, "profile_dsn", open_profile)
    monkeypatch.setattr(menu, "inspect_table", inspect)
    result = CliRunner().invoke(
        app, ["start", "--profile", str(saved(tmp_path))], input="1\n6\n1\n0\n"
    )
    assert result.exit_code == 0 and len(opened) == 2
    assert seen == ["PRIVATE_1", "PRIVATE_2"] and "PRIVATE" not in result.output


def test_start_overwrite_refusal_keeps_existing_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rls_doctor.cli.start as menu

    monkeypatch.setattr(menu, "profile_dsn", lambda *a, **kw: "PRIVATE")
    monkeypatch.setattr(menu, "inspect_table", detail)
    destination = tmp_path / "report.json"
    destination.write_text("KEEP")
    result = CliRunner().invoke(
        app,
        ["start", "--profile", str(saved(tmp_path))],
        input="1\n4\n" + str(destination) + "\n0\n",
    )
    assert result.exit_code == 0 and destination.read_text() == "KEEP"
    assert "REPORT_EXISTS" in result.output


def test_first_start_creates_profile_without_requesting_password_twice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rls_doctor.cli.project as wizard

    monkeypatch.setenv("RLS_DOCTOR_DATABASE_URL", "PRIVATE")
    monkeypatch.setattr(
        wizard,
        "inspection_dsn",
        lambda *a, **kw: (
            "host=db.example.com port=5432 dbname=postgres user=reader "
            "sslmode=verify-full password=PRIVATE"
        ),
    )
    monkeypatch.setattr(
        wizard,
        "discover_database",
        lambda *a: {
            "tables": [{"schema": "public", "name": "documents"}],
            "roles": [{"name": "authenticated"}],
            "truncated": False,
        },
    )
    monkeypatch.setattr(wizard, "inspect_table", detail)
    path = tmp_path / "project.json"
    result = CliRunner().invoke(
        app, ["start", "--profile", str(path)], input="db.example.com\ny\n1\n1\n\n0\n"
    )
    assert result.exit_code == 0 and path.exists()
    assert "PRIVATE" not in path.read_text() + result.output
    assert "diagnosis" in result.output.lower()
