"""Ordered diagnostic decisions over independent evidence, never guessed causes."""

from typing import Any

from rls_doctor.core.models import DiagnosticEvent
from rls_doctor.reports.metadata import complete_report


def investigate(report: dict[str, Any], event: DiagnosticEvent | None = None) -> dict[str, Any]:
    inspector = report.get("inspector", report)
    codes = {c["code"] for c in inspector.get("conclusions", [])}
    applicable = [
        p
        for p in inspector.get("policies", [])
        if p.get("applies_to_role") and p.get("command") in {"ALL", "SELECT"}
    ]

    def using_shape(policy: dict[str, Any]) -> str | None:
        return next(
            (c["shape"] for c in policy.get("condition_shapes", []) if c["scope"] == "USING"), None
        )

    permissive = [p for p in applicable if p.get("permissive")]
    constant_denial = inspector.get("table", {}).get("rls_applies_to_requested_role") and (
        any(not p.get("permissive") and using_shape(p) == "ALWAYS_FALSE" for p in applicable)
        or bool(permissive)
        and all(using_shape(p) == "ALWAYS_FALSE" for p in permissive)
    )
    if constant_denial:
        codes.add("RLS_CONSTANT_DENIAL")
    denied_columns: list[str] = []
    unknown_columns: list[str] = []
    if (
        event is not None
        and event.request.columns
        and report.get("linkage", {}).get("configuration_matches")
    ):
        grants = {
            c["name"]: c["select"] for c in inspector.get("privileges", {}).get("columns", [])
        }
        if grants:
            denied_columns = [c for c in event.request.columns if c in grants and not grants[c]]
            unknown_columns = [c for c in event.request.columns if c not in grants]
        if denied_columns:
            codes.add("REQUESTED_COLUMN_SELECT_MISSING")
    steps: list[dict[str, str]] = []

    def step(code: str, state: str, en: str, ru: str) -> None:
        steps.append({"code": code, "state": state, "en": en, "ru": ru})

    blockers = codes & {
        "SCHEMA_USAGE_MISSING",
        "SELECT_PRIVILEGE_MISSING",
        "NO_PERMISSIVE_SELECT_POLICY",
        "RLS_CONSTANT_DENIAL",
        "REQUESTED_COLUMN_SELECT_MISSING",
    }
    if blockers:
        step(
            "ACCESS_CONFIGURATION_BLOCKER",
            "ESTABLISHED",
            (
                "The selected role has an access configuration blocker. Review the"
                " listed grants/policies before investigating row filters."
            ),
            (
                "Для выбранной роли найдено препятствие доступа. Сначала проверьте"
                " указанные права и политики, затем фильтры строк."
            ),
        )
    else:
        step(
            "ACCESS_CONFIGURATION",
            "CHECKED",
            (
                "No basic grant/default-deny blocker was found for the selected "
                "role. This does not confirm row visibility."
            ),
            (
                "Базовых препятствий GRANT/default-deny для выбранной роли не "
                "найдено. Видимость строк этим не подтверждается."
            ),
        )
    if denied_columns:
        step(
            "REQUESTED_COLUMN_SELECT_MISSING",
            "ESTABLISHED",
            "The selected role lacks SELECT for requested columns: "
            + ", ".join(denied_columns)
            + (
                ". Review column grants or the projection; original runtime role "
                "remains unverified."
            ),
            "Выбранной роли недоступен SELECT запрошенных столбцов: "
            + ", ".join(denied_columns)
            + (". Проверьте права столбцов или проекцию; роль исходного запроса не подтверждена."),
        )
    if unknown_columns:
        step(
            "REQUESTED_COLUMNS_NOT_FOUND",
            "NEEDS_EVIDENCE",
            "Captured columns are absent from the selected current table: "
            + ", ".join(unknown_columns)
            + ". Check schema routing and renames.",
            "Столбцы события отсутствуют в выбранной текущей таблице: "
            + ", ".join(unknown_columns)
            + ". Проверьте схему API и переименования.",
        )
    if constant_denial:
        step(
            "RLS_CONSTANT_DENIAL",
            "ESTABLISHED",
            (
                "A constant-false restrictive policy, or all constant-false "
                "permissive policies, prevents rows for the selected role at "
                "inspection time. This does not prove the captured request used "
                "that role/database."
            ),
            (
                "Постоянно ложная ограничивающая политика либо все постоянно "
                "ложные разрешающие политики не допускают строки для выбранной "
                "роли сейчас. Это не доказывает роль и базу исходного запроса."
            ),
        )
    if codes & {"RLS_DISABLED", "RLS_BYPASSED"}:
        step(
            "RLS_NOT_ENFORCED",
            "ESTABLISHED",
            (
                "RLS does not constrain ordinary SELECT for the selected "
                "role/table. Review disabled RLS or the selected role's bypass "
                "privileges before investigating row isolation."
            ),
            (
                "RLS не ограничивает обычный SELECT выбранной роли/таблицы. "
                "Проверьте отключённый RLS или права обхода выбранной роли перед "
                "анализом изоляции строк."
            ),
        )
    if event is not None:
        if report.get("linkage", {}).get("configuration_matches"):
            step(
                "PROJECT_BINDING",
                "CHECKED",
                (
                    "Project ID, API origin fingerprint and schema match the saved "
                    "configuration; runtime database routing still needs independent "
                    "confirmation."
                ),
                (
                    "ID проекта, отпечаток адреса API и схема совпали с профилем; "
                    "фактическую маршрутизацию базы нужно подтвердить отдельно."
                ),
            )
        else:
            step(
                "PROJECT_BINDING",
                "NEEDS_EVIDENCE",
                (
                    "Use a bound v1.1 capture and matching profile; a table name alone"
                    " does not link a request to this database."
                ),
                (
                    "Используйте событие v1.1 и соответствующий профиль: имя таблицы "
                    "не связывает запрос с этой базой."
                ),
            )
        auth = event.auth_check
        if not event.context.authorization_present:
            step(
                "REQUEST_AUTHORIZATION",
                "ESTABLISHED",
                (
                    "The captured request had no authorization header. Check how the "
                    "application supplies its session."
                ),
                (
                    "В сохранённом запросе отсутствовал заголовок авторизации. "
                    "Проверьте передачу сессии приложением."
                ),
            )
        elif auth == "rejected":
            step(
                "REQUEST_AUTHORIZATION",
                "ESTABLISHED",
                (
                    "Supabase Auth rejected this authorization during the opt-in "
                    "check. Reauthenticate and capture a new request."
                ),
                (
                    "Supabase Auth отклонил авторизацию при явной проверке. Войдите "
                    "заново и запишите новый запрос."
                ),
            )
        elif auth == "verified_user":
            step(
                "REQUEST_AUTHORIZATION",
                "CHECKED",
                (
                    "Supabase Auth accepted a user session at check time. This does "
                    "not confirm the PostgreSQL role or an earlier auth.uid value."
                ),
                (
                    "Supabase Auth подтвердил пользовательскую сессию в момент "
                    "проверки. Это не подтверждает роль PostgreSQL или прежнее "
                    "значение auth.uid."
                ),
            )
        else:
            step(
                "REQUEST_AUTHORIZATION",
                "NEEDS_EVIDENCE",
                (
                    "Enable opt-in Auth verification for a new capture; header "
                    "presence alone does not establish a valid user session."
                ),
                (
                    "Включите явную проверку Auth для нового события: наличие "
                    "заголовка не подтверждает действительную сессию."
                ),
            )
    for policy in inspector.get("policies", []):
        if not policy.get("applies_to_role") or policy.get("command") not in {"ALL", "SELECT"}:
            continue
        for condition in policy.get("condition_shapes", []):
            if condition["scope"] != "USING":
                continue
            shape = condition["shape"]
            if shape == "AUTH_UID_EQUALS_COLUMN":
                step(
                    "OWNER_CONDITION",
                    "NEEDS_EVIDENCE",
                    "An applicable policy compares auth.uid() with column "
                    + condition["column"]
                    + (
                        ". Independently check that the intended user's identity matches "
                        "the row owner; no row was read."
                    ),
                    "Применимая политика сравнивает auth.uid() со столбцом "
                    + condition["column"]
                    + (
                        ". Отдельно проверьте соответствие пользователя владельцу строки; "
                        "строки не читались."
                    ),
                )
            elif shape == "ALWAYS_FALSE":
                step(
                    "FALSE_POLICY_CONDITION",
                    "ESTABLISHED",
                    (
                        "An applicable USING condition is constant false. Consider all "
                        "applicable permissive/restrictive policies together."
                    ),
                    (
                        "Применимое условие USING постоянно ложно. Учитывайте совокупность"
                        " всех разрешающих и ограничивающих политик."
                    ),
                )
            elif shape == "ALWAYS_TRUE":
                step(
                    "TRUE_POLICY_CONDITION",
                    "CHECKED",
                    (
                        "An applicable USING condition is constant true; that policy alone"
                        " does not restrict rows. Other policies and privileges still "
                        "apply."
                    ),
                    (
                        "Применимое USING постоянно истинно: само это условие не "
                        "ограничивает строки. Другие политики и SQL-права продолжают "
                        "действовать."
                    ),
                )
            elif shape == "UNRECOGNIZED":
                step(
                    "POLICY_CONDITION",
                    "NEEDS_EVIDENCE",
                    (
                        "A policy condition is outside the supported structural shapes. "
                        "Review its functions/context privately; no SQL text or literals "
                        "were exported."
                    ),
                    (
                        "Условие политики вне поддерживаемых форм. Проверьте его функции и"
                        " контекст локально; текст SQL и значения не выгружались."
                    ),
                )
    if event is not None and event.response.status == 200 and event.response.row_count == 0:
        step(
            "EMPTY_RESULT",
            "NEEDS_EVIDENCE",
            (
                "Compare the intended data and actual filter values privately. "
                "Empty Content-Range metadata cannot distinguish absent data, "
                "filters and RLS."
            ),
            (
                "Отдельно сравните наличие нужных данных и значения фильтров. "
                "Пустой Content-Range не различает отсутствие данных, фильтры и "
                "RLS."
            ),
        )
    report["investigation"] = steps
    complete_report(report)
    report["configuration_blockers"] = sorted(blockers)
    return report
