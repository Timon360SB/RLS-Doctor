"""CLI exit codes: 0 PASS, 1 FAIL, 2 UNKNOWN, 3 operational ERROR."""

import re
from pathlib import Path
from typing import Annotated, Any, Literal

import httpx
import typer

from rls_doctor.core.config import load_config
from rls_doctor.core.errors import DoctorError
from rls_doctor.core.models import load_event
from rls_doctor.identity.validation import bounded_json, local_headers
from rls_doctor.postgres.inspector import InspectorError, doctor_database, inspect_table
from rls_doctor.replay.runner import replay as run_replay
from rls_doctor.replay.scenarios import load_scenario
from rls_doctor.reports.capture import capture_report
from rls_doctor.reports.console import render

app = typer.Typer(
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    help="Explicit local Supabase request and authorization diagnostics.",
)
Format = Literal["console", "json"]
ConfigPath = Annotated[
    Path, typer.Option("--config", "-c", help="Local project TOML configuration.")
]
OutputFormat = Annotated[Format, typer.Option("--format", help="Console or machine-readable JSON.")]

CONFIG_TEMPLATE = """version = 1
[environment]
approved_local = false
api_url = "http://127.0.0.1:54321"
allowed_api_ports = [54321]
allowed_db_ports = [54322]
resources = ["documents", "blocked_documents", "no_grant_documents", "leaky_documents"]
anon_key_env = "RLS_DOCTOR_LOCAL_ANON_KEY"
database_url_env = "RLS_DOCTOR_DATABASE_URL"
jwt_secret_env = "RLS_DOCTOR_LOCAL_JWT_SECRET"
confirm_identity = true
"""
SCENARIO_TEMPLATE = """version: 1
name: document_owner_access
environment:
  type: local_supabase
request:
  method: GET
  resource: documents
identity:
  type: authenticated
  token_env: RLS_DOCTOR_TEST_TOKEN
expect:
  status: 200
  row_count: 1
"""


def finish(report: dict[str, Any], format: Format) -> None:
    render(report, format)
    raise typer.Exit(
        {"PASS": 0, "FAIL": 1, "UNKNOWN": 2, "ERROR": 3}.get(report.get("result", "UNKNOWN"), 2)
    )


def fail(exc: Exception, format: Format) -> None:
    if isinstance(exc, (DoctorError, InspectorError)):
        code, message = exc.code, str(exc)
    elif isinstance(exc, httpx.HTTPError):
        code, message = (
            "LOCAL_HTTP_ERROR",
            "Cannot complete the local HTTP request; check your disposable stack.",
        )
    else:
        code, message = (
            "EXECUTION_ERROR",
            "Diagnostic execution failed; no untrusted error details were retained.",
        )
    finish({"result": "ERROR", "error": {"code": code, "message": message}}, format)


@app.command()
def init(directory: Annotated[Path, typer.Option("--directory")] = Path(".")) -> None:
    """Create examples without overwriting existing files; replay stays disabled."""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        paths = [directory / "rls-doctor.toml", directory / "documents.yaml"]
        if any(p.exists() or p.is_symlink() for p in paths):
            raise DoctorError(
                "INIT_EXISTS", "Example files already exist; choose another directory."
            )
        for path, content in zip(paths, (CONFIG_TEMPLATE, SCENARIO_TEMPLATE), strict=True):
            with path.open("x", encoding="utf-8") as handle:
                handle.write(content)
        typer.echo(
            "Created local config and scenario. Review fixtures before enabling approved_local."
        )
    except Exception as exc:
        fail(exc, "console")


@app.command()
def validate(event: Path, format: OutputFormat = "console") -> None:
    """Validate a captured diagnostic event using shared schema v1."""
    try:
        parsed = load_event(event)
    except Exception as exc:
        fail(exc, format)
        return
    finish(
        {
            "result": "PASS",
            "event_id": parsed.event_id,
            "schema_version": parsed.schema_version,
            "resource": parsed.request.resource,
            "checks": [{"check": "event_contract", "result": "PASS"}],
        },
        format,
    )


@app.command()
def analyze(
    event: Path,
    expected_role: Annotated[
        Literal["anon", "authenticated"] | None,
        typer.Option("--expected-role", help="Intended role; captured headers do not verify it."),
    ] = None,
    format: OutputFormat = "console",
) -> None:
    """Analyze a sanitized capture offline; runtime access remains UNKNOWN (exit 2)."""
    try:
        report = capture_report(load_event(event), expected_role)
    except Exception as exc:
        fail(exc, format)
        return
    finish(report, format)


@app.command()
def doctor(config: ConfigPath = Path("rls-doctor.toml"), format: OutputFormat = "console") -> None:
    """Check approved local API, PostgreSQL version and required test roles."""
    try:
        env = load_config(config).environment
        database = doctor_database(env.database_dsn())
        with httpx.Client(timeout=5, trust_env=False, follow_redirects=False) as client:
            headers, _ = local_headers(env, client, None)
            status, identity = bounded_json(
                client, env.origin() + "/rest/v1/rpc/rls_doctor_identity", headers
            )
        role_checks = [
            inspect_table(env.database_dsn(), "public", resource, role)
            for role in ("anon", "authenticated")
            for resource in env.resources[:1]
        ]
        result = (
            "PASS"
            if status == 200
            and isinstance(identity, dict)
            and identity.get("role") == "anon"
            and database["database"]["supported"]
            and role_checks
            else "UNKNOWN"
        )
        report = {
            "result": result,
            "database": database,
            "http_status": status,
            "limitations": ["Only approved disposable local fixtures are supported."],
        }
    except Exception as exc:
        fail(exc, format)
        return
    finish(report, format)


@app.command()
def inspect(
    table: str,
    role: Annotated[str, typer.Option()] = "authenticated",
    config: ConfigPath = Path("rls-doctor.toml"),
    format: OutputFormat = "console",
) -> None:
    """Read catalog metadata for schema.table; never query user rows."""
    try:
        parts = table.split(".")
        if len(parts) != 2 or any(
            not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]{0,62}", p) for p in [*parts, role]
        ):
            raise DoctorError("INVALID_IDENTIFIER", "Use simple schema.table and role identifiers.")
        env = load_config(config).environment
        if parts[1] not in env.resources:
            raise DoctorError(
                "RESOURCE_NOT_ALLOWED", "Table is not in the local resource allowlist."
            )
        report = inspect_table(env.database_dsn(), parts[0], parts[1], role)
        report["result"] = "UNKNOWN"
        report["resource"] = table
    except Exception as exc:
        fail(exc, format)
        return
    finish(report, format)


@app.command()
def replay(
    scenario: Path,
    config: ConfigPath = Path("rls-doctor.toml"),
    format: OutputFormat = "console",
    event: Annotated[Path | None, typer.Option(help="Optional sanitized captured event.")] = None,
    inspect_db: Annotated[
        bool, typer.Option("--inspect", help="Also read local PostgreSQL catalogs.")
    ] = False,
) -> None:
    """Execute an explicit synthetic GET scenario with verified local identity."""
    try:
        report = run_replay(
            load_scenario(scenario),
            load_config(config),
            load_event(event) if event else None,
            inspect=inspect_db,
        )
    except Exception as exc:
        fail(exc, format)
        return
    finish(report, format)


if __name__ == "__main__":
    app()
