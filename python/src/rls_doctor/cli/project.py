"Guided existing-database setup. Discovery is read-only; profiles contain no DSN."

import ipaddress
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

import typer
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from rls_doctor.core.database_connection import inspection_dsn, validate_database_host
from rls_doctor.core.errors import DoctorError
from rls_doctor.core.profiles import DatabaseProfile, api_origin, save_profile
from rls_doctor.postgres.inspector import discover_database, inspect_table
from rls_doctor.reports.console import Language, word
from rls_doctor.reports.files import available


def choose(items: list[str], label: str) -> str:
    if not items:
        raise DoctorError("PROJECT_CATALOG_EMPTY", "No supported catalog entries were found.")
    for index, item in enumerate(items, 1):
        typer.echo(f"  {index}. {item}")
    while True:
        value = int(typer.prompt(label, type=int))
        if 1 <= value <= len(items):
            return items[value - 1]
        typer.echo(f"1..{len(items)}")


@dataclass
class ConnectedProject:
    profile: DatabaseProfile
    dsn: str = field(repr=False)
    report: dict[str, Any] = field(repr=False)


def connection_fields(host: str, language: Language) -> str:
    """Build a DSN in memory from separate fields, with verified remote TLS."""
    while True:
        raw_port = typer.prompt(word(language, "Database port", "Порт базы"), default="5432")
        if raw_port.isascii() and raw_port.isdigit() and len(raw_port) <= 5:
            port = int(raw_port)
            if 1 <= port <= 65535:
                break
        typer.echo(word(language, "Use a port from 1 to 65535.", "Порт должен быть от 1 до 65535."))
    values: dict[str, Any] = {"host": host, "port": port}
    for key, en, ru, pattern, default in (
        ("dbname", "Database name", "Имя базы", r"[A-Za-z_][A-Za-z0-9_]{0,62}", "postgres"),
        (
            "user",
            "Connection user",
            "Пользователь подключения",
            r"[A-Za-z_][A-Za-z0-9_.-]{0,127}",
            "postgres",
        ),
    ):
        while True:
            value = typer.prompt(word(language, en, ru), default=default)
            if re.fullmatch(pattern, value):
                values[key] = value
                break
            typer.echo(
                word(
                    language,
                    "Use a simple name, not a connection string.",
                    "Нужно простое имя, а не строка подключения.",
                )
            )
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = False
    values["sslmode"] = "disable" if loopback else "verify-full"
    if not loopback:
        typer.echo(
            word(
                language,
                "TLS certificate verification is required for this host.",
                "Для этого сервера обязательна проверка TLS-сертификата.",
            )
        )
        while True:
            ca = typer.prompt(
                word(
                    language,
                    "Trusted CA file (Enter for system trust)",
                    "Доверенный CA-файл (Enter — системные сертификаты)",
                ),
                default="system",
            )
            if ca == "system" or Path(ca).is_file():
                values["sslrootcert"] = ca
                break
            typer.echo(
                word(
                    language,
                    "CA file was not found; correct this field.",
                    "CA-файл не найден; исправьте путь.",
                )
            )
    values["password"] = typer.prompt(
        word(
            language,
            "Database password (hidden; not saved)",
            "Пароль базы (ввод скрыт; не сохраняется)",
        ),
        hide_input=True,
        show_default=False,
        default="",
    )
    return make_conninfo(**values)


def connect_project(
    path: Path, language: Language, *, connection_string: bool = False
) -> dict[str, Any]:
    return prepare_project(path, language, connection_string=connection_string).report


def prepare_project(
    path: Path, language: Language, *, connection_string: bool = False
) -> ConnectedProject:
    if path.exists() or path.is_symlink():
        raise DoctorError(
            "PROJECT_PROFILE_EXISTS",
            "Profile exists; use diagnose or choose a different --profile path.",
        )
    available(path)
    typer.echo(
        word(
            language,
            "Connect your database: only access-control catalogs will be read.",
            "Подключение своей базы: будут прочитаны только служебные каталоги прав.",
        )
    )
    host = typer.prompt(word(language, "Database hostname or IP", "Адрес базы данных"))
    validate_database_host(host)
    # No DNS until explicit host confirmation, including when credentials exist in the environment.
    if not typer.confirm(
        word(
            language,
            f"Approve catalog-only access on {host}?",
            f"Разрешить чтение каталогов на {host}?",
        ),
        default=False,
    ):
        raise DoctorError("DATABASE_APPROVAL_REQUIRED", "Catalog access was not approved.")
    raw = os.environ.get("RLS_DOCTOR_DATABASE_URL")
    if not raw:
        if connection_string:
            raw = typer.prompt(
                word(
                    language,
                    "PostgreSQL connection string (hidden)",
                    "Строка PostgreSQL (ввод скрыт)",
                ),
                hide_input=True,
                show_default=False,
            )
        else:
            typer.echo(
                word(
                    language,
                    (
                        "Enter the settings from your database provider. Supabase API keys are "
                        "not database passwords."
                    ),
                    (
                        "Введите настройки подключения вашего провайдера. API-ключ Supabase — "
                        "это не пароль базы."
                    ),
                )
            )
            raw = connection_fields(host, language)
    dsn = inspection_dsn(raw, host, approved=True)
    catalog = discover_database(dsn)
    typer.echo(
        word(
            language,
            "Read-only catalog access confirmed. No table rows were read.",
            "Чтение каталогов подтверждено. Строки таблиц не читались.",
        )
    )
    if catalog["truncated"]:
        typer.echo(
            word(
                language,
                "Showing the first 200 names; explicit diagnose remains available.",
                "Показаны первые 200 имён; доступна явная команда diagnose.",
            )
        )
    table = choose(
        [f"{t['schema']}.{t['name']}" for t in catalog["tables"]],
        word(language, "Table number", "Номер таблицы"),
    )
    role = choose(
        [r["name"] for r in catalog["roles"]], word(language, "Role number", "Номер роли")
    )
    origin = typer.prompt(
        word(
            language,
            "Supabase API origin (optional, Enter to skip)",
            "Адрес Supabase API (необязательно, Enter — пропустить)",
        ),
        default="",
    )
    while origin:
        try:
            origin = api_origin(origin)
            break
        except DoctorError:
            typer.echo(
                word(
                    language,
                    "Use HTTPS origin only; no paths, keys or query parameters.",
                    "Нужен только HTTPS-адрес без пути, ключей и параметров.",
                )
            )
            origin = typer.prompt(
                word(language, "API origin or Enter", "Адрес API или Enter"), default=""
            )
    values = {key: str(value) for key, value in conninfo_to_dict(dsn).items()}
    try:
        profile = DatabaseProfile(
            project_id=str(uuid4()),
            host=host,
            port=int(values["port"]),
            database=values["dbname"],
            user=values["user"],
            table=table,
            role=role,
            api_origin=origin or None,
            sslmode="verify-full" if values.get("sslmode") == "verify-full" else "disable",
            sslrootcert=(
                str(Path(values["sslrootcert"]).resolve())
                if values.get("sslrootcert", "system") != "system"
                else "system"
            ),
        )
    except Exception:
        raise DoctorError(
            "PROJECT_PROFILE_INVALID", "Profile requires simple database/user identifiers."
        ) from None
    schema, name = table.split(".")
    report = inspect_table(dsn, schema, name, role, True)
    # Save only after successful inspection; existing files are never replaced.
    save_profile(profile, path)
    typer.echo(
        word(
            language,
            "Non-secret profile saved. Password and DSN were not saved.",
            "Профиль сохранён. Пароль и строка подключения не сохранялись.",
        )
    )
    typer.echo(f'rls-doctor diagnose --profile "{path}"')
    if origin:
        typer.echo(word(language, "SDK binding options:", "Параметры привязки SDK:"))
        typer.echo(f"projectId: '{profile.project_id}', allowedOrigin: '{origin}'")
    return ConnectedProject(
        profile,
        dsn,
        report
        | {
            "result": "UNKNOWN",
            "resource": table,
            "analysis_mode": "existing_database_catalogs",
        },
    )


def follow_up(report: dict[str, Any], language: Language) -> dict[str, Any]:
    "Ask coarse operator observations only; never request row values or secrets."
    typer.echo(
        word(
            language,
            (
                "Guided investigation: answer only yes/no/unknown. Do not enter row "
                "values or tokens."
            ),
            (
                "Пошаговое расследование: только да/нет/неизвестно. Не вводите "
                "строки данных или токены."
            ),
        )
    )
    questions = [
        (
            "data_exists",
            "Did you independently verify that the expected row exists?",
            "Вы отдельно проверили, что ожидаемая строка существует?",
        ),
        (
            "filters_reviewed",
            "Did you compare the application's actual filter values?",
            "Вы сравнили фактические значения фильтров приложения?",
        ),
        (
            "role_reviewed",
            "Did you independently confirm the application's executed database role?",
            "Вы отдельно подтвердили исполняемую роль базы для приложения?",
        ),
    ]
    answers: dict[str, str] = {}
    for key, en, ru in questions:
        typer.echo(word(language, en, ru))
        selected = choose(
            [
                word(language, "Yes", "Да"),
                word(language, "No", "Нет"),
                word(language, "Unknown", "Неизвестно"),
            ],
            word(language, "Answer number", "Номер ответа"),
        )
        answers[key] = {
            word(language, "Yes", "Да"): "yes",
            word(language, "No", "Нет"): "no",
            word(language, "Unknown", "Неизвестно"): "unknown",
        }[selected]
    report["operator_checks"] = {
        "answers": answers,
        "evidence": "UNVERIFIED",
        "source": "operator_statement_not_database_observation",
    }
    if answers["data_exists"] != "yes":
        en = (
            "First establish that the intended row exists in the selected "
            "environment. An absent row cannot be made visible by changing an "
            "RLS policy."
        )
        ru = (
            "Сначала установите наличие нужной строки в выбранной среде. "
            "Изменение RLS не сделает отсутствующую строку видимой."
        )
    elif answers["filters_reviewed"] != "yes":
        en = (
            "Next compare the actual filter values privately with the expected"
            " row. The event intentionally contains no filter values."
        )
        ru = (
            "Далее отдельно сравните значения фильтров с нужной строкой. "
            "Значения фильтров намеренно отсутствуют в событии."
        )
    elif answers["role_reviewed"] != "yes":
        en = (
            "Next establish the application's actual role in your trusted "
            "runtime; Auth session validity does not establish the PostgreSQL "
            "role."
        )
        ru = (
            "Далее подтвердите фактическую роль приложения в доверенной среде:"
            " действительная Auth-сессия не подтверждает роль PostgreSQL."
        )
    else:
        en = (
            "Review the identified policy shapes and unrecognized "
            "function/context dependencies. Operator answers do not establish "
            "a root cause; capture fresh evidence after changes."
        )
        ru = (
            "Проверьте распознанные условия и неизвестные зависимости "
            "функций/контекста. Ответы оператора не доказывают причину; после "
            "изменений запишите новые сведения."
        )
    report["investigation"].append(
        {"code": "OPERATOR_NEXT_STEP", "state": "NEEDS_EVIDENCE", "en": en, "ru": ru}
    )
    return report
