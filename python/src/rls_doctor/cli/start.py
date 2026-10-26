"One guided entry point for existing-database diagnosis; no Docker or scenarios."

from pathlib import Path
from typing import Any

import typer

from rls_doctor.cli.connection import profile_dsn
from rls_doctor.cli.project import choose, prepare_project
from rls_doctor.core.errors import DoctorError
from rls_doctor.core.profiles import load_profile
from rls_doctor.postgres.inspector import InspectorError, discover_database, inspect_table
from rls_doctor.postgres.overview import inspect_schema
from rls_doctor.reports.console import Language, render, word
from rls_doctor.reports.files import write_report
from rls_doctor.reports.investigation import investigate
from rls_doctor.reports.metadata import complete_report
from rls_doctor.reports.operational import database_error_details, enrich_error


def run_start(path: Path, language: Language, *, once: bool = False) -> int:
    """Approve once per session; secrets are neither printed nor serialized."""
    dsn: str | None = None
    last: dict[str, Any] | None = None
    if not path.exists() and not path.is_symlink():
        typer.echo(
            word(
                language,
                "First connection: have your database host, port, user and password ready.",
                "Первое подключение: подготовьте адрес, порт, пользователя и пароль базы.",
            )
        )
        prepared = prepare_project(path, language)
        profile, dsn = prepared.profile, prepared.dsn
        last = investigate(prepared.report)
        del prepared
        render(last, "console", language)
        if once:
            return 2
    else:
        profile = load_profile(path)
    if once:
        dsn = profile_dsn(profile, language)
        schema, table = profile.table.split(".")
        last = investigate(
            inspect_table(dsn, schema, table, profile.role, True)
            | {
                "result": "UNKNOWN",
                "resource": profile.table,
                "analysis_mode": "existing_database_catalogs",
            }
        )
        render(last, "console", language)
        return 2
    try:
        while True:
            typer.echo(
                "\n"
                + word(language, "Your database", "Ваша база")
                + f": {profile.host} / {profile.table} / {profile.role}"
            )
            for line in (
                word(language, "1. Diagnose selected table", "1. Проверить выбранную таблицу"),
                word(
                    language, "2. Overview of tables in this schema", "2. Обзор таблиц этой схемы"
                ),
                word(
                    language,
                    "3. Select another table or role",
                    "3. Выбрать другую таблицу или роль",
                ),
                word(
                    language, "4. Save last report as JSON", "4. Сохранить последний отчёт в JSON"
                ),
                word(language, "5. Switch to Russian", "5. Switch to English"),
                word(
                    language,
                    "6. Forget session password / reconnect",
                    "6. Забыть пароль сессии / переподключиться",
                ),
                word(language, "0. Exit", "0. Выход"),
            ):
                typer.echo(line)
            action = typer.prompt(word(language, "Choose", "Выберите"), default="1")
            if action == "0":
                return 0
            if action == "5":
                language = "ru" if language == "en" else "en"
                continue
            if action == "6":
                dsn = None
                typer.echo(
                    word(
                        language,
                        "Session credentials released; next check asks again.",
                        "Данные подключения отпущены; следующая проверка запросит их снова.",
                    )
                )
                continue
            if action not in {"1", "2", "3", "4"}:
                continue
            try:
                if action == "4":
                    if last is None:
                        typer.echo(
                            word(language, "Run a diagnosis first.", "Сначала выполните проверку.")
                        )
                        continue
                    default = ".rls-doctor/reports/" + last["diagnosis_id"] + ".json"
                    destination = Path(
                        typer.prompt(
                            word(language, "New report file", "Новый файл отчёта"), default=default
                        )
                    )
                    write_report(last, destination)
                    typer.echo(word(language, "JSON report saved.", "JSON-отчёт сохранён."))
                    continue
                if dsn is None:
                    dsn = profile_dsn(profile, language)
                if action == "3":
                    catalog = discover_database(dsn)
                    table = choose(
                        [t["schema"] + "." + t["name"] for t in catalog["tables"]],
                        word(language, "Table number", "Номер таблицы"),
                    )
                    role = choose(
                        [r["name"] for r in catalog["roles"]],
                        word(language, "Role number", "Номер роли"),
                    )
                    profile = profile.model_copy(update={"table": table, "role": role})
                    typer.echo(
                        word(
                            language,
                            "Selection applies to this session. Saved profile is unchanged.",
                            "Выбор действует в этой сессии. Сохранённый профиль не изменён.",
                        )
                    )
                    if catalog["truncated"]:
                        typer.echo(
                            word(
                                language,
                                "Catalog list truncated at 200; "
                                "explicit diagnose remains available.",
                                "Список ограничен 200 именами; доступна явная команда diagnose.",
                            )
                        )
                    continue
                schema, table = profile.table.split(".")
                if action == "2":
                    last = complete_report(inspect_schema(dsn, schema, profile.role))
                else:
                    last = investigate(
                        inspect_table(dsn, schema, table, profile.role, True)
                        | {
                            "result": "UNKNOWN",
                            "resource": profile.table,
                            "analysis_mode": "existing_database_catalogs",
                        }
                    )
                render(last, "console", language)
            except (DoctorError, InspectorError) as error:
                if isinstance(error, InspectorError) and error.phase == "connection":
                    dsn = None
                details = (
                    database_error_details(error)
                    if isinstance(error, InspectorError)
                    else enrich_error({"code": error.code, "message": str(error)})
                )
                last = complete_report({"result": "ERROR", "error": details})
                render(last, "console", language)
    finally:
        dsn = None
