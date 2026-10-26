"""CLI exit codes: 0 PASS, 1 FAIL, 2 UNKNOWN, 3 operational ERROR."""

import os
import re
from pathlib import Path
from typing import Annotated, Any, Literal

import httpx
import typer

from rls_doctor import __version__
from rls_doctor.cli.session import run_session
from rls_doctor.cli.wizard import guided_files, initialize
from rls_doctor.core.config import load_config
from rls_doctor.core.database_connection import inspection_dsn
from rls_doctor.core.errors import DoctorError
from rls_doctor.core.models import load_event
from rls_doctor.identity.validation import bounded_json, local_headers
from rls_doctor.postgres.inspector import InspectorError, doctor_database, inspect_table
from rls_doctor.replay.runner import replay as run_replay
from rls_doctor.replay.scenarios import load_scenario
from rls_doctor.reports.capture import capture_report
from rls_doctor.reports.console import Language, render, word
from rls_doctor.reports.files import available, write_report

app = typer.Typer(
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    help="Read-only PostgreSQL/Supabase access diagnostics and optional local scenario checks.",
    epilog="Documentation: https://github.com/Timon360SB/RLS-Doctor#documentation",
)
Format = Literal["console", "json"]
ConfigPath = Annotated[
    Path, typer.Option("--config", "-c", help="Local project TOML configuration.")
]
OutputFormat = Annotated[Format, typer.Option("--format", help="Console or machine-readable JSON.")]
OutputLanguage = Annotated[
    Language, typer.Option("--language", help="Console language: en or ru; JSON stays unchanged.")
]

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


OutputPath = Annotated[
    Path | None,
    typer.Option("--output", help="Save generated JSON to a new UTF-8 file; never overwrite."),
]


def finish(
    report: dict[str, Any], format: Format, language: Language = "en", output: Path | None = None
) -> None:
    if output is not None:
        try:
            write_report(report, output)
        except Exception as exc:
            fail(exc, format, language)
            return
        if format == "console":
            typer.echo(word(language, "JSON report saved.", "JSON-отчёт сохранён."))
    render(report, format, language)
    raise typer.Exit(
        {"PASS": 0, "FAIL": 1, "UNKNOWN": 2, "ERROR": 3}.get(report.get("result", "UNKNOWN"), 2)
    )


def fail(
    exc: Exception, format: Format, language: Language = "en", output: Path | None = None
) -> None:
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
    finish(
        {"result": "ERROR", "error": {"code": code, "message": message}}, format, language, output
    )


@app.callback(invoke_without_command=True)
def entrypoint(
    version: Annotated[
        bool, typer.Option("--version", is_eager=True, help="Show installed CLI version.")
    ] = False,
) -> None:
    if version:
        typer.echo("RLS Doctor " + __version__)
        raise typer.Exit(0)


@app.command()
def init(
    directory: Annotated[Path, typer.Option("--directory")] = Path("."),
    interactive: Annotated[
        bool,
        typer.Option(
            "--interactive", help="Guided local project setup; no secrets or connections."
        ),
    ] = False,
    language: OutputLanguage = "en",
    advanced: Annotated[
        bool,
        typer.Option("--advanced", help="With --interactive: columns, filters and record checks."),
    ] = False,
) -> None:
    """Create configuration and a synthetic scenario without overwriting files."""
    try:
        if advanced and not interactive:
            raise DoctorError("INIT_MODE", "Use --interactive with --advanced.")
        if any(
            (directory / name).exists() or (directory / name).is_symlink()
            for name in ("rls-doctor.toml", "documents.yaml")
        ):
            raise DoctorError(
                "INIT_EXISTS", "Example files already exist; choose another directory."
            )
        contents = (
            guided_files(language, advanced=advanced)
            if interactive
            else (CONFIG_TEMPLATE, SCENARIO_TEMPLATE)
        )
        initialize(directory, contents)
        typer.echo(
            word(
                language,
                "Created rls-doctor.toml and documents.yaml. Review the local "
                "destination before replay.",
                "Созданы rls-doctor.toml и documents.yaml. Проверьте локальный "
                "адрес перед воспроизведением.",
            )
        )
        if interactive and not advanced:
            typer.echo(
                word(
                    language,
                    "Next: use 'rls-doctor session' with this config and the running "
                    "local Supabase --workdir. No keys need copying; see "
                    "docs/managed-session.md. No secrets were requested or saved.",
                    "Далее: используйте 'rls-doctor session' с этой конфигурацией "
                    "и --workdir работающего локального Supabase. Ключи копировать "
                    "не нужно; см. docs/managed-session.ru.md. Секреты не сохранялись.",
                )
            )
            typer.echo(
                word(
                    language,
                    "This configuration leaves the identity probe disabled. "
                    "Runtime role stays unconfirmed; replay may return UNKNOWN. "
                    "Count expectations alone do not prove isolation.",
                    "Пробник роли выключен в этой конфигурации. Исполняемая "
                    "роль не подтверждена: replay может вернуть UNKNOWN. Проверка "
                    "числа строк не доказывает изоляцию.",
                )
            )
        if interactive and advanced:
            typer.echo(
                word(
                    language,
                    "Next: run this scenario with 'rls-doctor session'. Prepare synthetic "
                    "rows/identity separately; probe opt-in does not install or validate "
                    "its implementation.",
                    "Далее: запустите сценарий через 'rls-doctor session'. Тестовые строки и "
                    "личность подготавливаются отдельно; выбор пробника не устанавливает "
                    "и не проверяет его код.",
                )
            )
    except (typer.Abort, KeyboardInterrupt):
        typer.echo(
            word(
                language,
                "Setup cancelled. No files created.",
                "Настройка отменена. Файлы не созданы.",
            )
        )
        raise typer.Exit(0) from None
    except Exception as exc:
        fail(exc, "console", language)


@app.command()
def validate(
    event: Path,
    format: OutputFormat = "console",
    language: OutputLanguage = "en",
    output: OutputPath = None,
) -> None:
    """Validate a captured diagnostic event using shared schema v1."""
    try:
        available(output)
        parsed = load_event(event)
    except Exception as exc:
        fail(exc, format, language, output)
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
        language,
        output,
    )


@app.command()
def analyze(
    event: Path,
    expected_role: Annotated[
        Literal["anon", "authenticated"] | None,
        typer.Option("--expected-role", help="Intended role; captured headers do not verify it."),
    ] = None,
    format: OutputFormat = "console",
    output: OutputPath = None,
    language: OutputLanguage = "en",
) -> None:
    """Analyze a sanitized capture offline; runtime access remains UNKNOWN (exit 2)."""
    try:
        available(output)
        report = capture_report(load_event(event), expected_role)
    except Exception as exc:
        fail(exc, format, language, output)
        return
    finish(report, format, language, output)


@app.command()
def doctor(
    config: ConfigPath = Path("rls-doctor.toml"),
    format: OutputFormat = "console",
    output: OutputPath = None,
    language: OutputLanguage = "en",
) -> None:
    """Check approved local API, PostgreSQL version and required test roles."""
    try:
        available(output)
        env = load_config(config).environment
        database = doctor_database(env.database_dsn())
        status: int | None = None
        identity: Any = None
        if env.confirm_identity:
            with httpx.Client(timeout=5, trust_env=False, follow_redirects=False) as client:
                headers, _ = local_headers(env, client, None)
                status, identity = bounded_json(
                    client,
                    env.origin() + "/rest/v1/rpc/rls_doctor_identity",
                    {**headers, "Accept-Profile": "public"},
                )
        roles = database["required_roles"]
        identity_confirmed = (
            status == 200 and isinstance(identity, dict) and identity.get("role") == "anon"
        )
        result = (
            "FAIL"
            if not all(roles.values())
            else "PASS"
            if identity_confirmed and database["database"]["supported"]
            else "UNKNOWN"
        )
        report = {
            "result": result,
            "database": database,
            "http_status": status,
            "checks": [
                {"check": "role_" + role, "result": "PASS" if exists else "FAIL"}
                for role, exists in roles.items()
            ]
            + [{"check": "api_identity", "result": "PASS" if identity_confirmed else "UNKNOWN"}],
            "limitations": ["Only approved disposable local fixtures are supported."]
            + (
                []
                if env.confirm_identity
                else [
                    "Identity probe is disabled; API availability and executed role are unverified."
                ]
            ),
        }
    except Exception as exc:
        fail(exc, format, language, output)
        return
    finish(report, format, language, output)


@app.command()
def inspect(
    table: str,
    role: Annotated[str, typer.Option()] = "authenticated",
    config: ConfigPath = Path("rls-doctor.toml"),
    format: OutputFormat = "console",
    output: OutputPath = None,
    language: OutputLanguage = "en",
) -> None:
    """Read catalog metadata for schema.table; never query user rows."""
    try:
        available(output)
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
        fail(exc, format, language, output)
        return
    finish(report, format, language, output)


@app.command()
def diagnose(
    table: str,
    host: Annotated[str, typer.Option("--host", help="Exact approved database hostname or IP.")],
    role: Annotated[
        str, typer.Option(help="Database role whose access settings to inspect.")
    ] = "authenticated",
    connection_env: Annotated[
        str,
        typer.Option(
            "--connection-env", help="Optional environment reference; never put a DSN in arguments."
        ),
    ] = "RLS_DOCTOR_DATABASE_URL",
    approve_read_only: Annotated[
        bool,
        typer.Option(
            "--approve-read-only", help="Explicitly approve catalog-only access to this host."
        ),
    ] = False,
    format: OutputFormat = "console",
    output: OutputPath = None,
    language: OutputLanguage = "en",
) -> None:
    """Diagnose an existing PostgreSQL/Supabase table without fixtures or scenarios."""
    try:
        available(output)
        parts = table.split(".")
        if len(parts) != 2 or any(
            not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]{0,62}", p) for p in [*parts, role]
        ):
            raise DoctorError("INVALID_IDENTIFIER", "Use simple schema.table and role identifiers.")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,95}", connection_env):
            raise DoctorError("DATABASE_ENV_NAME", "Use a valid environment reference name.")
        if not approve_read_only:
            if format == "json":
                raise DoctorError(
                    "DATABASE_APPROVAL_REQUIRED", "JSON mode requires --approve-read-only."
                )
            approve_read_only = typer.confirm(
                word(
                    language,
                    f"Read only access-control catalogs on {host} for {table} / {role}?",
                    f"Прочитать только каталоги прав на {host} для {table} / {role}?",
                ),
                default=False,
            )
            if not approve_read_only:
                raise DoctorError(
                    "DATABASE_APPROVAL_REQUIRED", "Catalog-only connection was not approved."
                )
        raw = os.environ.get(connection_env)
        if not raw:
            if format == "json":
                raise DoctorError(
                    "MISSING_CREDENTIAL",
                    "Set the selected database environment reference privately.",
                )
            raw = typer.prompt(
                word(
                    language,
                    "PostgreSQL connection string (hidden; not saved)",
                    "Строка подключения PostgreSQL (ввод скрыт; не сохраняется)",
                ),
                hide_input=True,
                show_default=False,
            )
        dsn = inspection_dsn(raw, host, approved=approve_read_only)
        report = inspect_table(dsn, parts[0], parts[1], role)
        report.update(result="UNKNOWN", resource=table, analysis_mode="existing_database_catalogs")
        report["limitations"].insert(
            0,
            "Existing database catalog diagnosis: no table rows, app queries "
            "or identity probes executed.",
        )
    except (typer.Abort, KeyboardInterrupt):
        fail(
            DoctorError(
                "DATABASE_CANCELLED", "Database diagnosis cancelled; no outcome established."
            ),
            format,
            language,
            output,
        )
        return
    except Exception as exc:
        fail(exc, format, language, output)
        return
    finish(report, format, language, output)


@app.command()
def replay(
    scenario: Path,
    config: ConfigPath = Path("rls-doctor.toml"),
    format: OutputFormat = "console",
    output: OutputPath = None,
    language: OutputLanguage = "en",
    event: Annotated[Path | None, typer.Option(help="Optional sanitized captured event.")] = None,
    inspect_db: Annotated[
        bool, typer.Option("--inspect", help="Also read local PostgreSQL catalogs.")
    ] = False,
) -> None:
    """Execute an explicit synthetic GET scenario with verified local identity."""
    try:
        available(output)
        report = run_replay(
            load_scenario(scenario),
            load_config(config),
            load_event(event) if event else None,
            inspect=inspect_db,
        )
    except Exception as exc:
        fail(exc, format, language, output)
        return
    finish(report, format, language, output)


@app.command()
def session(
    config: ConfigPath = Path("rls-doctor.toml"),
    workdir: Annotated[
        Path, typer.Option("--workdir", help="Local Supabase project folder.")
    ] = Path("."),
    scenario: Annotated[
        Path | None,
        typer.Option("--scenario", help="Explicit synthetic scenario; defaults beside config."),
    ] = None,
    event: Annotated[
        Path | None,
        typer.Option(
            "--event",
            help="Optional sanitized capture; replay values still come from the scenario.",
        ),
    ] = None,
    language: OutputLanguage = "en",
    format: OutputFormat = "console",
    output: OutputPath = None,
    run_once: Annotated[
        bool, typer.Option("--run", help="Run once without a menu; preserve replay exit code.")
    ] = False,
    create_test_user: Annotated[
        bool,
        typer.Option(
            "--create-test-user",
            help="Explicitly allow one synthetic local Auth signup if no test token exists.",
        ),
    ] = False,
) -> None:
    """Use local Supabase credentials in memory, with a diagnostic menu or one run."""
    try:
        available(output)
        code = run_session(
            config,
            workdir,
            scenario,
            language,
            run_once=run_once,
            create_user=create_test_user,
            output_format=format,
            event_path=event,
            output_path=output,
        )
    except (typer.Abort, KeyboardInterrupt):
        if format == "json" or run_once:
            fail(
                DoctorError(
                    "SESSION_CANCELLED", "Local session interrupted; no outcome was established."
                ),
                format,
                language,
                output,
            )
            return
        typer.echo(
            word(
                language,
                "Session cancelled. Docker remains running.",
                "Сессия отменена. Docker продолжает работать.",
            )
        )
        raise typer.Exit(0) from None
    except Exception as exc:
        fail(exc, format, language, output)
        return
    raise typer.Exit(code)


if __name__ == "__main__":
    app()
