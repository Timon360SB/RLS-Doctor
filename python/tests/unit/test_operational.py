import json
from datetime import datetime
from uuid import UUID

import psycopg
import pytest
import typer
from typer.testing import CliRunner

from rls_doctor.cli.main import app, fail
from rls_doctor.core.database_connection import inspection_dsn
from rls_doctor.core.errors import DoctorError
from rls_doctor.postgres import inspector
from rls_doctor.postgres.inspector import InspectorError
from rls_doctor.reports.metadata import complete_report


@pytest.mark.parametrize(
    "state,category",
    [
        ("42501", "insufficient_privilege"),
        ("28P01", "authentication_rejected"),
        ("28000", "authorization_rejected"),
        ("3D000", "database_missing"),
        ("57014", "query_cancelled"),
        ("55P03", "lock_unavailable"),
        ("53300", "connection_limit"),
        ("57P03", "server_not_ready"),
    ],
)
def test_sqlstate_is_preserved_with_safe_actions(
    state: str, category: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(typer.Exit) as caught:
        fail(
            InspectorError("POSTGRES_INSPECTION_FAILED", "Fixed message", state, phase="catalog"),
            "json",
        )
    report = json.loads(capsys.readouterr().out)
    assert caught.value.exit_code == 3
    assert report["error"]["sqlstate"] == state
    assert report["error"]["diagnostic"]["category"] == category
    assert report["error"]["diagnostic"]["evidence"] == "OBSERVED"
    assert report["error"]["diagnostic"]["next_steps"]
    UUID(report["diagnosis_id"])
    assert datetime.fromisoformat(report["diagnosed_at"]).tzinfo is not None


def test_connection_failure_never_guesses_tls_or_bad_password(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def reject(*args: object, **kwargs: object) -> object:
        raise psycopg.OperationalError("PRIVATE_PASSWORD certificate rejected by PRIVATE_HOST")

    monkeypatch.setattr(inspector.psycopg, "connect", reject)
    with pytest.raises(InspectorError) as caught:
        inspector.doctor_database("PRIVATE_DSN")
    assert caught.value.__context__ is None
    with pytest.raises(typer.Exit):
        fail(caught.value, "json")
    output = capsys.readouterr().out
    report = json.loads(output)
    assert report["error"]["phase"] == "connection"
    assert "sqlstate" not in report["error"]
    assert report["error"]["diagnostic"]["category"] == "connection_failure"
    assert report["error"]["diagnostic"]["evidence"] == "UNVERIFIED"
    assert "PRIVATE" not in output


def test_dns_failure_is_separate_and_has_no_raw_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    import socket

    def reject(*args: object, **kwargs: object) -> object:
        raise socket.gaierror(-2, "PRIVATE_DNS_VALUE")

    monkeypatch.setattr(socket, "getaddrinfo", reject)
    with pytest.raises(DoctorError) as caught:
        inspection_dsn(
            "host=db.example.com port=5432 dbname=app user=reader password=PRIVATE_PASSWORD",
            "db.example.com",
            approved=True,
        )
    assert caught.value.code == "DATABASE_DNS_FAILED"
    assert caught.value.__context__ is None
    assert "PRIVATE" not in str(caught.value)


@pytest.mark.parametrize(
    "extra,detail",
    [
        ("sslmode=require", "verified_tls_required"),
        ("sslrootcert=NOT_A_REAL_CA_FILE", "ca_file_unavailable"),
        ("options=-c", "unsupported_options"),
    ],
)
def test_configuration_detail_is_fixed_and_precedes_dns(
    extra: str, detail: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import socket

    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: pytest.fail("Reject before DNS"))
    with pytest.raises(DoctorError) as caught:
        inspection_dsn(
            "host=db.example.com port=5432 dbname=app user=reader password=PRIVATE " + extra,
            "db.example.com",
            approved=True,
        )
    assert caught.value.code == "DATABASE_CONNECTION_CONFIG"
    assert caught.value.detail_code == detail
    assert "PRIVATE" not in str(caught.value)


def test_invalid_sqlstate_is_never_exported(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(typer.Exit):
        fail(
            InspectorError("POSTGRES_INSPECTION_FAILED", "Fixed message", "PRIVATE_SQLSTATE"),
            "json",
        )
    output = capsys.readouterr().out
    assert "PRIVATE" not in output
    assert "sqlstate" not in json.loads(output)["error"]


def test_report_metadata_is_stable_and_capture_time_is_distinct() -> None:
    report = {"result": "UNKNOWN", "captured_at": "2020-01-01T00:00:00Z"}
    complete_report(report)
    original = report.copy()
    complete_report(report)
    assert report == original
    assert report["diagnosed_at"] != report["captured_at"]


def test_russian_error_guidance_does_not_send_user_to_fixture_setup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rls_doctor.cli.main as cli

    def reject(*args: object, **kwargs: object) -> object:
        raise InspectorError(
            "POSTGRES_INSPECTION_FAILED", "Fixed message", "42501", phase="catalog"
        )

    monkeypatch.setenv("RLS_DOCTOR_DATABASE_URL", "PRIVATE_DSN")
    monkeypatch.setattr(cli, "inspection_dsn", lambda *a, **kw: "checked")
    monkeypatch.setattr(cli, "inspect_table", reject)
    result = CliRunner().invoke(
        app,
        [
            "diagnose",
            "public.orders",
            "--host",
            "db.example.com",
            "--approve-read-only",
            "--language",
            "ru",
        ],
    )
    assert result.exit_code == 3
    assert "42501" in result.stdout
    assert "недостаточных правах" in result.stdout
    assert "тестовых строк" not in result.stdout
    assert "PRIVATE" not in result.stdout


@pytest.mark.parametrize("state", ["P0001", "08006", "XX000"])
def test_unknown_sqlstate_is_not_described_as_missing(
    state: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(typer.Exit):
        fail(
            InspectorError("POSTGRES_INSPECTION_FAILED", "Fixed message", state, phase="catalog"),
            "json",
        )
    report = json.loads(capsys.readouterr().out)
    assert report["error"]["sqlstate"] == state
    assert report["error"]["diagnostic"]["category"] == "database_error"
    assert "No SQLSTATE" not in report["error"]["diagnostic"]["next_steps"][0]


def test_numeric_loopback_unsupported_mode_is_not_reported_as_remote_tls_requirement() -> None:
    with pytest.raises(DoctorError) as caught:
        inspection_dsn(
            "host=127.0.0.1 port=5432 dbname=app user=reader sslmode=require",
            "127.0.0.1",
            approved=True,
        )
    assert caught.value.detail_code == "unsupported_tls_mode"


def test_uri_in_host_argument_is_not_echoed_for_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    import rls_doctor.cli.main as cli

    monkeypatch.setattr(cli, "inspection_dsn", lambda *a, **kw: pytest.fail("No connection"))
    result = CliRunner().invoke(
        app,
        [
            "diagnose",
            "public.orders",
            "--host",
            "postgresql://u:PRIVATE_PASSWORD@db.example.com/db",
        ],
    )
    assert result.exit_code == 3
    assert "PRIVATE_PASSWORD" not in result.stdout
    assert "Read only access-control" not in result.stdout


def test_profile_host_matching_is_case_insensitive() -> None:
    from uuid import uuid4

    from rls_doctor.core.profiles import DatabaseProfile

    profile = DatabaseProfile(
        project_id=str(uuid4()),
        host="DB.EXAMPLE.COM",
        port=5432,
        database="postgres",
        user="reader",
        table="public.orders",
        role="authenticated",
    )
    profile.check_connection(
        "host=db.example.com port=5432 dbname=postgres user=reader "
        "sslmode=verify-full sslrootcert=system"
    )
