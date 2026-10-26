"""Fixed operational advice. Never inspect raw database exception text."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rls_doctor.postgres.inspector import InspectorError


@dataclass(frozen=True)
class Advice:
    category: str
    title: tuple[str, str]
    action: tuple[str, str]
    evidence: str = "OBSERVED"


CONFIG = {
    "configuration": Advice(
        "configuration",
        ("Connection settings are invalid.", "Некорректные настройки подключения."),
        (
            "Review the PostgreSQL DSN privately; use supported host/port/database/user fields.",
            "Проверьте строку PostgreSQL локально: адрес, порт, базу и пользователя.",
        ),
    ),
    "unsupported_options": Advice(
        "unsupported_options",
        (
            "Unsupported connection options were refused.",
            "Неподдерживаемые параметры подключения отклонены.",
        ),
        (
            "Remove service/options/hostaddr overrides and multi-host settings.",
            "Уберите service/options/hostaddr и настройки нескольких серверов.",
        ),
    ),
    "host_mismatch": Advice(
        "host_mismatch",
        (
            "The DSN does not match the approved host.",
            "Адрес в строке подключения не совпал с разрешённым.",
        ),
        (
            (
                "Choose the matching profile or correct the host privately before "
                "approving a new connection."
            ),
            (
                "Выберите соответствующий профиль или исправьте адрес до нового "
                "подтверждения подключения."
            ),
        ),
    ),
    "missing_fields": Advice(
        "missing_fields",
        (
            "Required connection fields are missing or invalid.",
            "Обязательные параметры подключения отсутствуют или неверны.",
        ),
        (
            "Specify the database, user and numeric port explicitly.",
            "Явно укажите базу, пользователя и числовой порт.",
        ),
    ),
    "verified_tls_required": Advice(
        "verified_tls_required",
        (
            "Verified TLS is required for this endpoint.",
            "Для этого адреса требуется TLS с проверкой сертификата.",
        ),
        (
            (
                "Use sslmode=verify-full and an operator-trusted CA; keep "
                "server-name verification enabled."
            ),
            "Используйте sslmode=verify-full и доверенный CA с проверкой имени сервера.",
        ),
    ),
    "ca_file_unavailable": Advice(
        "ca_file_unavailable",
        ("The trusted CA file is unavailable.", "Файл доверенного CA недоступен."),
        (
            (
                "Check the configured CA path and file permissions, or use system "
                "roots if appropriate."
            ),
            "Проверьте путь CA и права чтения файла либо подходящие системные сертификаты.",
        ),
    ),
    "connection_timeout": Advice(
        "connection_timeout",
        ("The database connection timed out.", "Время ожидания подключения к базе истекло."),
        (
            "Check server availability, port and network routing, then retry.",
            "Проверьте доступность сервера, порт и сеть, затем повторите.",
        ),
    ),
    "password_required": Advice(
        "password_required",
        ("The connection requires a password.", "Для подключения требуется пароль."),
        (
            "Supply the password using the hidden prompt or a private credential reference.",
            "Введите пароль в скрытом поле или используйте приватное окружение.",
        ),
    ),
}
CONFIG["unsupported_tls_mode"] = Advice(
    "unsupported_tls_mode",
    ("The selected TLS mode is unsupported.", "Выбран неподдерживаемый режим TLS."),
    (
        "Use verify-full, or disable only for explicitly approved numeric loopback.",
        "Используйте verify-full либо disable только для явно разрешённого числового loopback.",
    ),
)

SQLSTATES = {
    "42501": Advice(
        "insufficient_privilege",
        (
            "PostgreSQL reported insufficient privileges.",
            "PostgreSQL сообщил о недостаточных правах.",
        ),
        (
            (
                "Review catalog/schema permissions for the inspecting account; the"
                " exact object is not exported."
            ),
            (
                "Проверьте права учётной записи на каталоги и схему; имя объекта "
                "ошибки не выгружается."
            ),
        ),
    ),
    "28P01": Advice(
        "authentication_rejected",
        ("PostgreSQL rejected password authentication.", "PostgreSQL отклонил проверку пароля."),
        (
            "Check the saved username and private password source; do not publish credentials.",
            "Сверьте пользователя профиля и приватный источник пароля; значения не публикуйте.",
        ),
    ),
    "28000": Advice(
        "authorization_rejected",
        ("PostgreSQL rejected authorization.", "PostgreSQL отклонил авторизацию."),
        (
            "Review the permitted account and server authentication configuration.",
            "Проверьте разрешённую учётную запись и настройки авторизации сервера.",
        ),
    ),
    "3D000": Advice(
        "database_missing",
        ("The selected database does not exist.", "Выбранная база данных не существует."),
        (
            "Verify the database name in the selected profile/connection.",
            "Сверьте имя базы в выбранном профиле или подключении.",
        ),
    ),
    "57014": Advice(
        "query_cancelled",
        ("PostgreSQL cancelled a diagnostic query.", "PostgreSQL отменил диагностический запрос."),
        (
            "Review statement timeout/cancellation and server load before retrying.",
            "Проверьте отмену, лимит времени запроса и нагрузку сервера перед повтором.",
        ),
    ),
    "55P03": Advice(
        "lock_unavailable",
        (
            "PostgreSQL could not obtain a required lock.",
            "PostgreSQL не смог получить необходимую блокировку.",
        ),
        (
            (
                "Retry after conflicting schema changes finish; do not remove the "
                "diagnostic lock timeout."
            ),
            (
                "Повторите после завершения конкурирующих изменений схемы; "
                "сохраняйте лимит ожидания блокировки."
            ),
        ),
    ),
    "53300": Advice(
        "connection_limit",
        ("The server connection limit was reached.", "Достигнут лимит подключений сервера."),
        (
            "Review the connection pool and active sessions before retrying.",
            "Проверьте пул подключений и активные сессии перед повтором.",
        ),
    ),
    "57P03": Advice(
        "server_not_ready",
        (
            "The database server is not ready for connections.",
            "Сервер базы пока не готов принимать подключения.",
        ),
        (
            "Check startup/recovery status and retry when the server is ready.",
            "Проверьте запуск или восстановление сервера и повторите после готовности.",
        ),
    ),
}
CODES = {
    "SCHEMA_NOT_FOUND": Advice(
        "schema_missing",
        ("The selected schema was not found.", "Выбранная схема не найдена."),
        (
            "Check the database/profile and choose an existing schema.",
            "Проверьте базу и профиль, выберите существующую схему.",
        ),
    ),
    "OVERVIEW_TIME_LIMIT": Advice(
        "overview_time_limit",
        ("Schema overview exceeded its time budget.", "Обзор схемы превысил лимит времени."),
        (
            "Retry overview with a smaller --limit or diagnose one table.",
            "Уменьшите --limit обзора либо проверьте одну таблицу через diagnose.",
        ),
        "OBSERVED",
    ),
    "DATABASE_DNS_FAILED": Advice(
        "name_resolution",
        (
            "The approved hostname could not be resolved.",
            "Не удалось определить IP разрешённого сервера.",
        ),
        (
            "Check hostname spelling and DNS/network availability, then retry.",
            "Проверьте написание адреса и доступность DNS/сети, затем повторите.",
        ),
    ),
    "MISSING_CREDENTIAL": Advice(
        "missing_credential",
        (
            "A required credential reference is unavailable.",
            "Не найден обязательный источник учётных данных.",
        ),
        (
            "Use the hidden prompt or configure the selected environment reference privately.",
            "Используйте скрытый ввод или задайте выбранную переменную окружения приватно.",
        ),
    ),
    "DATABASE_APPROVAL_REQUIRED": Advice(
        "approval_required",
        ("Catalog access has not been approved.", "Чтение каталогов не подтверждено."),
        (
            (
                "Review the destination, then confirm interactively or use "
                "--approve-read-only for automation."
            ),
            (
                "Сверьте адрес и подтвердите подключение либо используйте "
                "--approve-read-only для автоматизации."
            ),
        ),
    ),
    "PROJECT_CONNECTION_MISMATCH": Advice(
        "profile_mismatch",
        (
            "Connection settings differ from the saved profile.",
            "Настройки подключения отличаются от сохранённого профиля.",
        ),
        (
            "Match host, port, database, user and TLS/CA settings, or select the intended profile.",
            "Сверьте адрес, порт, базу, пользователя, TLS и CA либо выберите нужный профиль.",
        ),
    ),
    "PROJECT_PROFILE_INVALID": Advice(
        "profile_invalid",
        (
            "A project profile could not be created or read.",
            "Не удалось создать или прочитать профиль проекта.",
        ),
        (
            (
                "Select a valid profile or run connect with a new --profile path; "
                "never add passwords to profiles."
            ),
            (
                "Выберите корректный профиль или запустите connect с новым "
                "--profile; пароли в профиль не добавляйте."
            ),
        ),
    ),
    "TABLE_NOT_FOUND": Advice(
        "table_missing",
        ("The selected table was not found.", "Выбранная таблица не найдена."),
        (
            "Review schema/table names and possible renames in the selected database.",
            "Сверьте схему, таблицу и возможные переименования в выбранной базе.",
        ),
    ),
    "ROLE_NOT_FOUND": Advice(
        "role_missing",
        ("The selected database role was not found.", "Выбранная роль базы не найдена."),
        (
            "Choose an existing role; an Auth user is not itself a PostgreSQL role.",
            (
                "Выберите существующую роль; пользователь Auth сам по себе не "
                "является ролью PostgreSQL."
            ),
        ),
    ),
    "EXECUTION_ERROR": Advice(
        "execution_unverified",
        ("The diagnostic operation did not finish.", "Диагностическая операция не завершилась."),
        (
            (
                "Check the supported setup and retry; report the diagnostic ID and"
                " fixed error code if it persists."
            ),
            (
                "Проверьте поддерживаемую конфигурацию и повторите; при повторении"
                " сообщите ID диагностики и код ошибки."
            ),
        ),
        "UNVERIFIED",
    ),
}
CONNECTION_UNKNOWN = Advice(
    "connection_failure",
    (
        "A database connection could not be established; the exact cause is unverified.",
        "Подключиться к базе не удалось; точная причина не подтверждена.",
    ),
    (
        (
            "Check endpoint/port, network, certificate trust and private "
            "credentials. No SQLSTATE was available to distinguish them."
        ),
        (
            "Проверьте адрес/порт, сеть, доверие сертификату и приватные "
            "учётные данные. SQLSTATE для различения причин не получен."
        ),
    ),
    "UNVERIFIED",
)
CATALOG_UNKNOWN = Advice(
    "catalog_failure",
    (
        "Catalog inspection failed; no specific cause was established.",
        "Чтение каталогов завершилось ошибкой; конкретная причина не установлена.",
    ),
    (
        "Check catalog permissions and the supported server version, then retry.",
        "Проверьте права на каталоги и поддерживаемую версию сервера, затем повторите.",
    ),
    "UNVERIFIED",
)


CODES.update(
    {
        "PROJECT_REQUIRED": Advice(
            "project_required",
            ("No database project was selected.", "Проект базы не выбран."),
            (
                "Run connect, or provide schema.table and --host.",
                "Запустите connect либо укажите schema.table и --host.",
            ),
        ),
        "PROJECT_PROFILE_REQUIRED": Advice(
            "profile_required",
            (
                "This bound capture requires its saved profile.",
                "Для этого привязанного события нужен сохранённый профиль.",
            ),
            (
                "Select the profile whose project ID/API origin matches this capture.",
                "Выберите профиль с соответствующими ID проекта и адресом API.",
            ),
        ),
        "PROJECT_PROFILE_EXISTS": Advice(
            "profile_exists",
            ("The profile already exists.", "Профиль уже существует."),
            (
                "Use diagnose to reuse it, or choose a new --profile path for setup.",
                (
                    "Используйте diagnose для повторной проверки либо новый путь "
                    "--profile для настройки."
                ),
            ),
        ),
        "EVENT_PROJECT_MISMATCH": Advice(
            "event_project_mismatch",
            (
                "The capture does not match the selected project/schema.",
                "Событие не соответствует выбранному проекту или схеме.",
            ),
            (
                "Compare the project ID, API origin and schema; select the matching profile/event.",
                (
                    "Сверьте ID проекта, адрес API и схему; выберите соответствующие "
                    "профиль и событие."
                ),
            ),
        ),
        "EVENT_RESOURCE_MISMATCH": Advice(
            "event_resource_mismatch",
            (
                "The captured resource differs from the selected table.",
                "Ресурс события отличается от выбранной таблицы.",
            ),
            (
                "Select the event/table you intended to diagnose.",
                "Выберите нужные событие и таблицу для диагностики.",
            ),
        ),
        "DATABASE_CANCELLED": Advice(
            "cancelled",
            ("The diagnostic operation was cancelled.", "Диагностическая операция отменена."),
            (
                "Retry when ready; no runtime access outcome was established.",
                "Повторите, когда будете готовы; результат доступа не установлен.",
            ),
        ),
        "UNSUPPORTED_RELATION": Advice(
            "unsupported_relation",
            ("This relation type is unsupported.", "Этот тип объекта не поддерживается."),
            (
                (
                    "Select an ordinary/partitioned table; view/function authorization"
                    " needs separate analysis."
                ),
                (
                    "Выберите обычную или секционированную таблицу; доступ через "
                    "view/функции требует отдельного анализа."
                ),
            ),
        ),
        "UNSUPPORTED_POSTGRES_VERSION": Advice(
            "unsupported_version",
            ("This PostgreSQL version is unsupported.", "Эта версия PostgreSQL не поддерживается."),
            (
                (
                    "Use a supported PostgreSQL 16/17/18 instance; do not infer "
                    "results for untested versions."
                ),
                (
                    "Используйте поддерживаемую PostgreSQL 16/17/18; результаты других"
                    " версий не подтверждены."
                ),
            ),
        ),
        "READ_ONLY_REQUIRED": Advice(
            "read_only_unverified",
            (
                "Read-only inspection could not be established.",
                "Не удалось подтвердить режим только чтения.",
            ),
            (
                (
                    "Use an endpoint supporting normal transactions and the fixed "
                    "defensive startup settings."
                ),
                (
                    "Используйте подключение с поддержкой обычных транзакций и "
                    "фиксированных защитных настроек."
                ),
            ),
        ),
        "INVALID_IDENTIFIER": Advice(
            "invalid_identifier",
            (
                "The schema/table/role identifier is unsupported.",
                "Имя схемы, таблицы или роли не поддерживается.",
            ),
            (
                "Use simple schema.table and role names containing letters, digits or underscores.",
                "Используйте простые schema.table и имя роли: буквы, цифры и подчёркивание.",
            ),
        ),
    }
)
UNKNOWN_SQLSTATE = Advice(
    "database_error",
    (
        "SQLSTATE is available; its specific diagnostic cause is unverified.",
        "SQLSTATE получен; конкретная причина требует отдельной проверки.",
    ),
    (
        (
            "Use the SQLSTATE in your private server investigation; raw "
            "messages and object details were omitted."
        ),
        (
            "Используйте SQLSTATE для проверки сервера; сырые сообщения и "
            "сведения об объектах не сохранены."
        ),
    ),
    "UNVERIFIED",
)


def safe_sqlstate(value: object) -> str | None:
    return value if isinstance(value, str) and re.fullmatch(r"[0-9A-Z]{5}", value) else None


def advice_for(error: dict[str, Any]) -> Advice | None:
    state = safe_sqlstate(error.get("sqlstate"))
    if state is not None:
        return SQLSTATES.get(state, UNKNOWN_SQLSTATE)
    detail = error.get("detail_code")
    if isinstance(detail, str) and detail in CONFIG:
        return CONFIG[detail]
    code = error.get("code")
    if isinstance(code, str) and code in CODES:
        return CODES[code]
    if error.get("code") == "DATABASE_CONNECTION_CONFIG":
        return CONFIG["configuration"]
    if error.get("code") == "POSTGRES_INSPECTION_FAILED":
        return CONNECTION_UNKNOWN if error.get("phase") == "connection" else CATALOG_UNKNOWN
    return None


def enrich_error(error: dict[str, Any]) -> dict[str, Any]:
    advice = advice_for(error)
    if advice is not None:
        error["diagnostic"] = {
            "category": advice.category,
            "evidence": advice.evidence,
            "summary": advice.title[0],
            "next_steps": [advice.action[0]],
        }
    return error


def database_error_details(exc: InspectorError) -> dict[str, Any]:
    """Only the inspector's fixed message and allowlisted protocol metadata leave I/O."""
    error: dict[str, Any] = {"code": exc.code, "message": str(exc)}
    state = safe_sqlstate(exc.sqlstate)
    if state is not None:
        error["sqlstate"] = state
    if exc.phase in {"connection", "catalog"}:
        error["phase"] = exc.phase
    if exc.detail_code in CONFIG:
        error["detail_code"] = exc.detail_code
    return enrich_error(error)
