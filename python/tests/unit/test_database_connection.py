"""Existing database access requires approval, exact host and verified remote TLS."""

import json
from pathlib import Path

import pytest
from psycopg.conninfo import conninfo_to_dict
from typer.testing import CliRunner

from rls_doctor.cli.main import app
from rls_doctor.core.database_connection import inspection_dsn
from rls_doctor.core.errors import DoctorError


def test_approval_precedes_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    import socket

    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **kw: pytest.fail("No DNS without approval")
    )
    with pytest.raises(DoctorError) as caught:
        inspection_dsn("PRIVATE_PASSWORD", "db.example.com", approved=False)
    assert caught.value.code == "DATABASE_APPROVAL_REQUIRED"
    assert "PRIVATE" not in str(caught.value)


def test_remote_tls_and_numeric_pin_are_fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    import socket

    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **kw: [(2, 1, 6, "", ("203.0.113.10", 5432))]
    )
    value = inspection_dsn(
        "host=db.example.com port=5432 dbname=app user=reader password=PRIVATE_PASSWORD",
        "db.example.com",
        approved=True,
    )
    parsed = conninfo_to_dict(value)
    assert parsed["sslmode"] == "verify-full" and parsed["sslrootcert"] == "system"
    assert parsed["hostaddr"] == "203.0.113.10"
    assert parsed["sslcertmode"] == "disable"
    assert parsed["gssdelegation"] == "0"


@pytest.mark.parametrize(
    "extra",
    [
        "sslmode=disable",
        "sslmode=require",
        "options=-c",
        "service=hidden",
        "hostaddr=203.0.113.99",
        "sslkeylogfile=private.log",
    ],
)
def test_unsafe_connection_overrides_are_rejected(
    extra: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import socket

    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: pytest.fail("Reject before DNS"))
    with pytest.raises(DoctorError) as caught:
        inspection_dsn(
            "host=db.example.com port=5432 dbname=app user=reader password=PRIVATE_PASSWORD "
            + extra,
            "db.example.com",
            approved=True,
        )
    assert caught.value.code == "DATABASE_CONNECTION_CONFIG"
    assert "PRIVATE_PASSWORD" not in str(caught.value)


def test_mismatched_host_is_rejected() -> None:
    with pytest.raises(DoctorError):
        inspection_dsn(
            "host=other.example.com port=5432 dbname=app user=reader",
            "db.example.com",
            approved=True,
        )


def test_json_requires_explicit_approval_before_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RLS_DOCTOR_DATABASE_URL", "PRIVATE_DSN")
    result = CliRunner().invoke(
        app, ["diagnose", "public.orders", "--host", "db.example.com", "--format", "json"]
    )
    assert result.exit_code == 3
    assert json.loads(result.stdout)["error"]["code"] == "DATABASE_APPROVAL_REQUIRED"
    assert "PRIVATE_DSN" not in result.stdout


def test_hidden_connection_input_is_not_echoed_or_saved(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import rls_doctor.cli.main as cli

    monkeypatch.delenv("RLS_DOCTOR_DATABASE_URL", raising=False)
    monkeypatch.setattr(cli, "inspection_dsn", lambda raw, host, **kw: "checked")
    monkeypatch.setattr(
        cli, "inspect_table", lambda *a: {"limitations": [], "policies": [], "conclusions": []}
    )
    output = tmp_path / "report.json"
    result = CliRunner().invoke(
        app,
        [
            "diagnose",
            "public.orders",
            "--host",
            "db.example.com",
            "--approve-read-only",
            "--output",
            str(output),
        ],
        input="PRIVATE_DSN\n",
    )
    assert result.exit_code == 2
    assert "PRIVATE_DSN" not in result.stdout + output.read_text(encoding="utf-8")
