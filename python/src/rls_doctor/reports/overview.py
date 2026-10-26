"""Compact localized schema overview; data remains unchanged."""

from typing import Any

from rich.console import Console
from rich.table import Table
from rich.text import Text


def render_overview(report: dict[str, Any], language: str) -> None:
    ru = language == "ru"
    console = Console(markup=False, highlight=False)
    console.print("RLS Doctor — " + ("обзор схемы" if ru else "schema overview"))
    console.print(Text(str(report["schema"]) + " / " + str(report["requested_role"])))
    console.print(("Диагностика: " if ru else "Diagnosis: ") + str(report.get("diagnosis_id", "")))
    console.print(("Время: " if ru else "Time: ") + str(report.get("diagnosed_at", "")))
    labels = {
        "BLOCKED": "Препятствие доступа" if ru else "Access blocker",
        "REVIEW": "Требует проверки" if ru else "Review configuration",
        "NO_BASIC_BLOCKER": "Базовых препятствий нет" if ru else "No basic blocker",
    }
    codes = {
        "SCHEMA_USAGE_MISSING": "Нет USAGE схемы" if ru else "Schema USAGE missing",
        "SELECT_PRIVILEGE_MISSING": "Нет SELECT" if ru else "SELECT missing",
        "NO_PERMISSIVE_SELECT_POLICY": "Нет разрешающей SELECT-политики"
        if ru
        else "No permissive SELECT policy",
        "RLS_DISABLED": "RLS выключен" if ru else "RLS disabled",
        "RLS_BYPASSED": "Роль обходит RLS" if ru else "Role bypasses RLS",
        "SELECT_COLUMN_SCOPED": "Права только на столбцы" if ru else "Column-scoped SELECT",
    }
    table = Table(show_header=True)
    for title in (
        ("Таблица", "Настройки", "Причина") if ru else ("Table", "Configuration", "Reason")
    ):
        table.add_column(title)
    for item in report["tables"]:
        table.add_row(
            Text(item["resource"]),
            Text(labels[item["configuration"]]),
            Text("; ".join(codes.get(f["code"], f["code"]) for f in item["findings"]) or "—"),
        )
    console.print(table)
    if not report["tables"]:
        console.print(
            "Поддерживаемых таблиц в выбранной схеме нет."
            if ru
            else "No supported tables in this schema."
        )
    if report["truncated"]:
        console.print(
            "Список ограничен. Остальные таблицы проверяйте через diagnose."
            if ru
            else "List truncated. Diagnose remaining tables individually."
        )
    console.print(
        (
            "Результат: UNKNOWN. Видимость строк не проверялась. Отсутствие "
            "базового препятствия не означает корректность политик."
        )
        if ru
        else (
            "Result: UNKNOWN. Row visibility was not tested. No basic blocker does "
            "not establish policy correctness."
        )
    )
    console.print(
        (
            "Далее: выберите таблицу с препятствием и выполните diagnose "
            "schema.table --profile PATH --guide."
        )
        if ru
        else (
            "Next: select a table with a blocker and run diagnose schema.table "
            "--profile PATH --guide."
        )
    )
