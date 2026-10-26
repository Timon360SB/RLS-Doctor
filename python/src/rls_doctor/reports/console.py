"""Readable diagnostic evidence; JSON remains language-independent."""

import json
from typing import Any, Literal

from rich.console import Console
from rich.table import Table
from rich.text import Text

from rls_doctor import __version__
from rls_doctor.reports.operational import advice_for

Language = Literal["en", "ru"]


def word(language: Language, en: str, ru: str) -> str:
    return ru if language == "ru" else en


FACTS_RU = {
    "AUTH_USER_VERIFIED": (
        "Supabase Auth подтвердил пользовательскую сессию; ID не сохранён."
        " Роль PostgreSQL не установлена."
    ),
    "AUTH_USER_REJECTED": "Supabase Auth отклонил авторизацию при явной проверке.",
    "AUTH_CHECK_UNAVAILABLE": "Явная проверка Auth не установила действительную сессию.",
    "HTTP_OBSERVED": "Получены метаданные HTTP; наличие заголовка не подтверждает личность.",
    "NETWORK_FAILURE_OBSERVED": "SDK зафиксировал сетевую ошибку без HTTP-статуса.",
    "HTTP_STATUS_UNAVAILABLE": "HTTP-статус не получен; тип ошибки не установлен.",
    "AUTHORIZATION_CONTEXT_UNVERIFIED": (
        "Заголовок авторизации был; личность и роль не подтверждены."
    ),
    "MISSING_EXPECTED_AUTH": "Ожидалась авторизация пользователя, но заголовок отсутствовал.",
    "EMPTY_RESULT_AMBIGUOUS": (
        "Пустой ответ: возможны фильтры, отсутствие строки или RLS; причина не установлена."
    ),
    "LOCAL_ROLE_CONFIRMED": "Доверенная проверка локальной среды подтвердила исполняемую роль.",
    "ROLE_UNCONFIRMED": "Исполняемая роль не подтверждена: проверка локальной среды недоступна.",
    "UNEXPECTED_ANONYMOUS_CONTEXT": "Запрос выполнен анонимно, хотя ожидалась роль пользователя.",
    "POSTGRES_VERSION_SUPPORTED": "Основная версия PostgreSQL поддерживается инспектором.",
    "ELEVATED_INSPECTOR_ROLE": (
        "Подключение инспектора имеет повышенные права; по возможности ограничьте их."
    ),
    "CATALOG_CONFIGURATION": (
        "Метаданные таблицы, ролей, политик и прав прочитаны из каталогов PostgreSQL."
    ),
    "EXECUTED_ROLE_UNCONFIRMED": (
        "Роль для анализа задана пользователем; это не подтверждение роли запроса."
    ),
    "SCHEMA_USAGE_MISSING": (
        "У выбранной роли нет USAGE для схемы, необходимого для обычного SELECT."
    ),
    "SELECT_PRIVILEGE_MISSING": "У выбранной роли нет SELECT ни для таблицы, ни для её столбцов.",
    "SELECT_COLUMN_SCOPED": (
        "SELECT разрешён только для отдельных столбцов; сравните их с запросом."
    ),
    "RLS_DISABLED": "Для таблицы отключён RLS.",
    "RLS_BYPASSED": (
        "Выбранная роль обходит RLS из-за прав суперпользователя, BYPASSRLS или владельца."
    ),
    "RLS_APPLIES": "Обычный SELECT выбранной роли подчиняется RLS.",
    "NO_PERMISSIVE_SELECT_POLICY": (
        "Нет применимой разрешающей SELECT-политики для выбранной роли."
    ),
    "SELECT_POLICY_COMPOSITION": "Применимые политики объединяются по правилам PostgreSQL.",
    "PREDICATES_UNEVALUATED": (
        "Выражения политик не вычислялись; их влияние на строки не установлено."
    ),
    "CAPTURE_DATABASE_LINK_UNVERIFIED": (
        "Имена таблиц совпадают, но база, схема и роль исходного запроса не подтверждены. "
        "Факты каталогов сами по себе не устанавливают причину этого запроса."
    ),
    "ROW_VISIBILITY_UNKNOWN": "По метаданным нельзя установить видимость конкретных строк.",
}

CHECKS = {
    "api_identity": ("Local API identity confirmed", "Контекст локального API подтверждён"),
    "role_anon": ("Database role anon exists", "В БД есть роль anon"),
    "role_authenticated": ("Database role authenticated exists", "В БД есть роль authenticated"),
    "http_status": ("HTTP status", "HTTP-статус"),
    "row_count": ("Row count", "Число строк"),
    "error_class": ("Error class", "Класс ошибки"),
    "executed_role": (
        "Executed role matches expectation",
        "Исполняемая роль соответствует ожиданию",
    ),
    "result_completeness": ("Complete response", "Полнота ответа"),
    "postgres_inspection": ("Database inspection", "Анализ базы"),
    "event_contract": ("Event format", "Формат события"),
}


def scalar(value: Any, language: Language) -> str:
    if value is None:
        return word(language, "unknown / not applicable", "не установлено / не применимо")
    if isinstance(value, bool):
        return word(language, "yes" if value else "no", "да" if value else "нет")
    if isinstance(value, (str, int, float)):
        return str(value)
    return word(language, "see JSON details", "подробности в JSON")


def render(report: dict[str, Any], format: str = "console", language: Language = "en") -> None:
    console = Console(highlight=False, markup=False)
    if format == "json":
        console.print(json.dumps(report, indent=2, ensure_ascii=True), soft_wrap=True)
        return
    if report.get("analysis_mode") == "schema_catalog_overview":
        from rls_doctor.reports.overview import render_overview

        render_overview(report, language)
        return
    console.print(f"RLS DOCTOR v{__version__}")
    result = report.get("result", "UNKNOWN")
    console.print(word(language, "Result: ", "Результат: ") + str(result))
    meaning = {
        "PASS": (
            "This check matches its expectation; it is not a security certification.",
            "Проверка соответствует ожиданию; это не общая оценка безопасности.",
        ),
        "FAIL": (
            "Observed behavior differs from the expectation. Review the failed checks below.",
            "Поведение отличается от ожидания. Ниже показаны нарушенные проверки.",
        ),
        "UNKNOWN": (
            "Evidence is incomplete. A runtime outcome or root cause is not established.",
            "Доказательств недостаточно. Поведение запроса или причина не установлены.",
        ),
        "ERROR": (
            "The check did not finish. Resolve the setup or execution error and retry.",
            "Проверка не завершена. Исправьте ошибку настройки или выполнения и повторите.",
        ),
    }.get(result, ("Evidence is incomplete.", "Доказательств недостаточно."))
    console.print(word(language, *meaning))

    if report.get("analysis_mode") == "existing_database_and_capture":
        console.print(
            word(
                language,
                "Application request: saved metadata; no request was replayed.",
                "Запрос приложения: сохранённые метаданные; повторного запроса не было.",
            )
        )
    table = Table(show_header=False, box=None, padding=(0, 2))
    for key, en, ru in (
        ("run_id", "Run", "Проверка"),
        ("diagnosis_id", "Diagnosis", "Диагностика"),
        ("diagnosed_at", "Diagnosis time", "Время диагностики"),
        ("event_id", "Event", "Событие"),
        ("timestamp", "Run time", "Время запуска"),
        ("captured_at", "Request captured", "Запрос записан"),
        ("resource", "Resource", "Ресурс"),
        ("method", "Method", "Метод"),
    ):
        if key == "timestamp" and report.get("captured_at") == report.get("timestamp"):
            continue
        if key in report:
            table.add_row(Text(word(language, en, ru)), Text(scalar(report[key], language)))
    identity = report.get("identity") or {}
    for key, en, ru in (
        ("expected_role", "Expected role", "Ожидаемая роль"),
        ("confirmed_role", "Confirmed role", "Подтверждённая роль"),
    ):
        if key in identity:
            table.add_row(Text(word(language, en, ru)), Text(scalar(identity[key], language)))
    http = report.get("http") or {}
    if http or "http_status" in report:
        table.add_row(
            Text("HTTP"), Text(scalar(http.get("status", report.get("http_status")), language))
        )
    if "row_count" in http:
        table.add_row(
            Text(word(language, "Observed rows", "Получено строк")),
            Text(scalar(http["row_count"], language)),
        )
    existing_database = report.get("analysis_mode") in {
        "existing_database_catalogs",
        "existing_database_and_capture",
    }
    inspector = report.get("inspector") or (report if "policies" in report else {})
    catalog = inspector.get("table") or {}
    if inspector.get("role", {}).get("name"):
        table.add_row(
            Text(word(language, "Selected database role", "Выбранная роль базы")),
            Text(inspector["role"]["name"]),
        )
    for key, en, ru in (
        ("rls_enabled", "RLS enabled", "RLS включён"),
        ("rls_forced", "FORCE RLS", "FORCE RLS"),
    ):
        if key in catalog:
            table.add_row(Text(word(language, en, ru)), Text(scalar(catalog[key], language)))
    if inspector and "policies" in inspector:
        table.add_row(
            Text(word(language, "Policies inspected", "Политик прочитано")),
            Text(str(len(inspector.get("policies", [])))),
        )
    privileges = inspector.get("privileges") or {}
    for key, en, ru in (
        ("schema_usage", "Schema USAGE", "USAGE схемы"),
        ("table_select", "Table SELECT", "SELECT таблицы"),
        ("any_column_select", "Any column SELECT", "SELECT хотя бы одного столбца"),
    ):
        if key in privileges:
            table.add_row(Text(word(language, en, ru)), Text(scalar(privileges[key], language)))
    console.print(table)

    database = report.get("database") or inspector.get("database") or {}
    if isinstance(database.get("database"), dict):
        database = database["database"]
    if "server_major" in database:
        console.print("PostgreSQL: " + str(database["server_major"]))
    checks = report.get("checks", [])
    if checks:
        comparisons = Table(title=word(language, "Expectation comparison", "Сравнение с ожиданием"))
        for en, ru in (
            ("Check", "Проверка"),
            ("Expected", "Ожидалось"),
            ("Observed", "Получено"),
            ("Result", "Результат"),
        ):
            comparisons.add_column(word(language, en, ru))
        for check in checks:
            name = check["check"]
            label = CHECKS.get(name, (name, name))
            if name.startswith("contains_"):
                label = ("Required test record present", "Нужная тестовая запись присутствует")
            elif name.startswith("excludes_"):
                label = ("Excluded test record present", "Запрещённая тестовая запись присутствует")
            expected = check.get("expected")
            observed = check.get("observed")
            if name == "executed_role":
                expected = identity.get("expected_role")
                observed = identity.get("confirmed_role")
            comparisons.add_row(
                Text(word(language, *label)),
                Text(scalar(expected, language)),
                Text(scalar(observed, language)),
                Text(check["result"]),
            )
        console.print(comparisons)

    facts = (
        [
            *report.get("findings", []),
            *report.get("conclusions", []),
            *inspector.get("conclusions", []),
        ]
        if inspector is not report
        else report.get("conclusions", [])
    )
    database_check = report.get("database") or {}
    if isinstance(database_check, dict):
        facts = [*facts, *database_check.get("conclusions", [])]
    for evidence, en, ru in (
        ("OBSERVED", "Observed facts", "Наблюдаемые факты"),
        ("INFERRED", "Derived conclusions", "Выводы из фактов"),
        ("UNVERIFIED", "Not established / possible causes", "Не установлено / возможные причины"),
    ):
        selected = [f for f in facts if f.get("evidence") == evidence]
        if selected:
            console.print("\n" + word(language, en, ru) + f" ({evidence})")
            for fact in selected:
                detail = fact.get("summary", "")
                if language == "ru":
                    detail = FACTS_RU.get(fact.get("code", ""), detail)
                if (
                    report.get("event_id")
                    and not existing_database
                    and report.get("analysis_mode") != "capture_only"
                ):
                    capture_context = {
                        "HTTP_OBSERVED": (
                            "HTTP metadata belongs to the captured request; the HTTP "
                            "summary above is a separate local replay.",
                            "HTTP-метаданные относятся к исходному событию; сводка HTTP "
                            "выше относится к отдельному локальному replay.",
                        ),
                        "AUTHORIZATION_CONTEXT_UNVERIFIED": (
                            "The captured header does not verify the original identity. "
                            "The confirmed role above belongs only to the local replay.",
                            "Заголовок в событии не подтверждает исходную личность. "
                            "Подтверждённая роль выше относится только к локальному replay.",
                        ),
                    }
                    if fact.get("code") in capture_context:
                        detail = word(language, *capture_context[fact["code"]])
                if inspector is not report and inspector and http and not existing_database:
                    catalog_limits = {
                        "EXECUTED_ROLE_UNCONFIRMED": (
                            "Catalog inspection alone cannot verify runtime identity; "
                            "see the request role above.",
                            "Каталоги сами по себе не подтверждают личность запроса; "
                            "роль запроса показана выше.",
                        ),
                        "ROW_VISIBILITY_UNKNOWN": (
                            "Catalog inspection does not read rows; row counts and "
                            "record assertions above come from REST replay.",
                            "Инспектор не читает строки; число строк и проверки записей "
                            "выше получены через REST replay.",
                        ),
                        "PREDICATES_UNEVALUATED": (
                            "Policy expressions and hidden dependencies were not "
                            "evaluated; replay covers only the explicit test scenario.",
                            "Выражения политик и скрытые зависимости не вычислялись; "
                            "replay проверяет только заданный сценарий.",
                        ),
                    }
                    if fact.get("code") in catalog_limits:
                        detail = word(language, *catalog_limits[fact["code"]])
                console.print(Text("  • " + detail + " [" + fact.get("code", "") + "]"))
    codes = {fact.get("code") for fact in facts}
    actions: list[tuple[str, str]] = []
    if codes & {"MISSING_EXPECTED_AUTH", "UNEXPECTED_ANONYMOUS_CONTEXT"}:
        actions.append(
            (
                "Check that this request receives the intended user's session.",
                "Проверьте передачу сессии нужного пользователя в этот запрос.",
            )
        )
    if "SELECT_PRIVILEGE_MISSING" in codes:
        actions.append(
            (
                "Review SELECT grants for the requested role; an RLS policy "
                "does not grant SQL privileges.",
                "Проверьте GRANT SELECT для выбранной роли: RLS-политика не выдаёт SQL-права.",
            )
        )
    if "NO_PERMISSIVE_SELECT_POLICY" in codes:
        actions.append(
            (
                "Review an applicable permissive SELECT policy for the selected role.",
                "Проверьте применимую разрешающую SELECT-политику для выбранной роли.",
            )
        )
    if "CAPTURE_DATABASE_LINK_UNVERIFIED" in codes:
        actions.append(
            (
                "Confirm the application's database endpoint, exposed schema and executed role; "
                "the event does not establish this link.",
                "Сверьте адрес базы приложения, схему API и исполняемую роль: "
                "событие не подтверждает эту связь.",
            )
        )
    if "EMPTY_RESULT_AMBIGUOUS" in codes:
        actions.append(
            (
                "Independently verify matching data, filters and "
                "identity before attributing zero rows to RLS.",
                "Отдельно проверьте наличие подходящих данных, фильтры и "
                "личность: пустой ответ ещё не доказывает RLS.",
            )
        )
    if any(
        c.get("check", "").startswith("excludes_") and c.get("result") == "FAIL" for c in checks
    ):
        actions.append(
            (
                "Review the owner restriction in the SELECT policy and the "
                "synthetic fixture ownership.",
                "Проверьте ограничение по владельцу в SELECT-политике и владельцев тестовых строк.",
            )
        )
    error = report.get("error") or inspector.get("error")
    operational_advice = advice_for(error) if error else None
    if error:
        nested_error = not report.get("error") and inspector.get("error")
        error_label = (
            word(language, "Database inspection error: ", "Ошибка инспектора БД: ")
            if nested_error
            else word(language, "Error: ", "Ошибка: ")
        )
        console.print(Text(error_label + error["code"]))
        console.print(
            Text(
                word(language, *operational_advice.title)
                if operational_advice
                else error["message"]
            )
        )
        if error.get("sqlstate"):
            console.print(Text("SQLSTATE: " + error["sqlstate"]))
    session_hints = {
        "PROJECT_PROFILE_EXISTS": (
            "Run diagnose with this profile, or choose a new --profile path for setup.",
            "Запустите diagnose с этим профилем или выберите новый путь --profile для настройки.",
        ),
        "PROJECT_REQUIRED": (
            "Run rls-doctor connect to select your database, table and role.",
            "Запустите rls-doctor connect для выбора базы, таблицы и роли.",
        ),
        "EVENT_PROJECT_MISMATCH": (
            "Choose the profile used by this capture; compare project ID, API origin and schema.",
            "Выберите профиль этого события; сверьте ID проекта, адрес API и схему.",
        ),
        "PROJECT_CONNECTION_MISMATCH": (
            "Use the saved host, database and username; a different database needs a new profile.",
            (
                "Используйте адрес, базу и пользователя профиля; для другой базы "
                "создайте отдельный профиль."
            ),
        ),
        "REPORT_EXISTS": (
            "Choose a new --output filename; existing files are never overwritten.",
            "Выберите новое имя --output: существующие файлы не перезаписываются.",
        ),
        "REPORT_WRITE_FAILED": (
            "Use a writable local folder on a filesystem supporting hard links.",
            "Укажите доступную локальную папку на файловой системе с поддержкой жёстких ссылок.",
        ),
        "SESSION_OUTPUT_MODE": (
            "Add --run when saving a session report with --output.",
            "Для сохранения отчёта session через --output добавьте --run.",
        ),
        "SUPABASE_CLI_MISSING": (
            "Install Supabase CLI or run demo.cmd once, then retry session.",
            "Установите Supabase CLI или один раз запустите demo.cmd, затем повторите session.",
        ),
        "SUPABASE_PROJECT_MISSING": (
            "Set --workdir to the folder containing supabase/config.toml.",
            "Укажите в --workdir папку, содержащую supabase/config.toml.",
        ),
        "LOCAL_STACK_STATUS_FAILED": (
            "Start the selected local Supabase stack; do not share raw status output.",
            "Запустите выбранный локальный Supabase; не публикуйте вывод status с ключами.",
        ),
        "LOCAL_PROJECT_MISMATCH": (
            "Review the configured API address and --workdir; no alternate API was used.",
            "Сверьте адрес API в конфигурации и --workdir; другой API не использовался.",
        ),
        "TEST_IDENTITY_REQUIRED": (
            "Use a valid local test token or explicitly approve one synthetic Auth user.",
            "Используйте локальный тестовый токен или явно разрешите "
            "создание тестового Auth-пользователя.",
        ),
        "TEST_IDENTITY_SETUP_FAILED": (
            "Check local Auth signup/email-confirmation settings; no settings were changed.",
            "Проверьте регистрацию и подтверждение почты в локальной Auth; настройки не менялись.",
        ),
        "SESSION_VARIABLE_NAMES": (
            "Use separate RLS_DOCTOR_ credential variable names in the configuration.",
            "Задайте в конфигурации отдельные имена переменных с префиксом RLS_DOCTOR_.",
        ),
    }
    session_hint = session_hints.get(error["code"]) if error else None
    recommendations = report.get("recommendations", [])
    if report.get("investigation"):
        console.print("\n" + word(language, "Investigation", "Расследование"))
        for index, step in enumerate(report["investigation"], 1):
            state = step["state"]
            label = {
                "ESTABLISHED": ("established", "установлено"),
                "CHECKED": ("checked", "проверено"),
                "NEEDS_EVIDENCE": ("needs evidence", "нужны сведения"),
            }.get(state, (state, state))
            console.print(Text(f"{index}. [{word(language, *label)}] " + step[language]))
    console.print("\n" + word(language, "Next steps", "Следующие действия"))
    for en, ru in actions:
        console.print(Text("  • " + word(language, en, ru)))
    if operational_advice:
        console.print(Text(word(language, *operational_advice.action)))
    elif session_hint:
        console.print(Text(word(language, *session_hint)))
    elif error:
        console.print(
            word(
                language,
                "Review the fixed error code and the selected command's input settings.",
                "Сверьте код ошибки и параметры выбранной команды.",
            )
        )
    elif language == "ru" and existing_database:
        console.print(
            "Сверьте выбранную роль, права схемы и таблицы, применимые политики "
            "и фактический контекст запроса приложения."
        )
    elif language == "ru":
        console.print(
            "Проверьте ожидаемую роль, владельцев тестовых строк, фильтры, GRANT и SELECT-политики."
        )
        if error:
            console.print(
                "Проверьте пути конфигурации и переменные локальных учётных "
                "данных; не публикуйте их значения."
            )
    elif recommendations:
        for item in recommendations:
            console.print(Text("  • " + item))
    else:
        console.print(
            word(
                language,
                "Review failed checks and catalog findings; use --format json "
                "for structured details.",
                "Сравните проверки и факты каталога; --format json показывает "
                "структурированные подробности.",
            )
        )
    console.print("\n" + word(language, "Diagnostic limits", "Ограничения диагностики"))
    if error:
        console.print(
            word(
                language,
                (
                    "The operation did not fully complete; the error alone does not "
                    "establish the application's access-control cause."
                ),
                "Операция не завершена полностью; сама ошибка не устанавливает причину доступа.",
            )
        )
        if operational_advice and operational_advice.evidence == "UNVERIFIED":
            console.print(
                word(
                    language,
                    (
                        "The specific failure cause is unverified. Raw errors and secrets "
                        "were not retained."
                    ),
                    "Причина сбоя не подтверждена. Сырые ошибки и секреты не сохранены.",
                )
            )
    if language == "en":
        for item in [
            *report.get("limitations", []),
            *(inspector.get("limitations", []) if inspector is not report else []),
        ]:
            console.print(Text("  • " + item))
    elif not error:
        console.print(
            "Наличие заголовка не подтверждает роль. Пустой ответ не доказывает запрет RLS."
        )
        console.print(
            "Выражения политик не вычисляются; по отчёту нельзя объявить приложение безопасным."
        )
        if existing_database:
            console.print(
                "Прочитаны только каталоги выбранной базы. Строки таблицы, "
                "запросы приложения и пробники личности не выполнялись."
            )
            if report.get("event_id"):
                console.print(
                    "HTTP относится к сохранённому запросу; повторного запроса не было. "
                    "Настройки базы могли измениться после записи события."
                )
        if report.get("analysis_mode") == "capture_only":
            console.print(
                "Офлайн-анализ: сеть, воспроизведение запроса и база данных не использовались."
            )
    console.print(
        word(
            language,
            "Technical details: add --format json.",
            "Технические подробности: добавьте --format json.",
        )
    )
