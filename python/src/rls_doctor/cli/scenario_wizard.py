"""Optional detailed scenario questions; synthetic values never appear in previews."""

import re
from typing import Any

import typer

from rls_doctor.cli.wizard import ask
from rls_doctor.replay.scenarios import Filter, RecordExpectation, Scenario, ScenarioRequest
from rls_doctor.reports.console import Language, word


def choice(value: str, allowed: set[str]) -> str:
    result = value.strip().lower()
    if result not in allowed:
        raise ValueError
    return result


def selected_columns(value: str) -> list[str] | None:
    if value.strip() == "*":
        return None
    columns = [part.strip() for part in value.split(",")]
    request = ScenarioRequest(resource="documents", columns=columns)
    if len(columns) != len(set(columns)):
        raise ValueError
    return request.columns


def scalar(value: str, kind: str) -> str | int | bool:
    if not value or len(value) > 256 or any(char in value for char in "\r\n\x00"):
        raise ValueError
    if value.lower().startswith(
        ("bearer ", "basic ", "sb_secret_", "sb_publishable_")
    ) or re.fullmatch(r"[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}", value):
        raise ValueError
    if kind == "integer":
        return int(value)
    if kind == "boolean":
        return {"true": True, "false": False}[choice(value, {"true", "false"})]
    return value


def value_prompt(language: Language) -> str | int | bool:
    kind = ask(
        word(language, "Value type (text/integer/boolean)", "Тип значения (text/integer/boolean)"),
        "text",
        lambda raw: choice(raw, {"text", "integer", "boolean"}),
        word(language, "Choose text, integer or boolean.", "Выберите text, integer или boolean."),
    )
    return ask(
        word(language, "Synthetic value (hidden)", "Синтетическое значение (скрыто)"),
        "",
        lambda raw: scalar(raw, kind),
        word(
            language,
            "Use a valid synthetic scalar of 1–256 characters; no credentials or line breaks.",
            "Введите корректное тестовое значение длиной 1–256 символов без ключей и переносов.",
        ),
        hidden=True,
    )


def extend_scenario(base: Scenario, language: Language) -> Scenario:
    """Build the existing strict scenario contract without any connections or writes."""

    def say(en: str, ru: str) -> str:
        return word(language, en, ru)

    typer.echo(
        say(
            "Detailed checks: use synthetic values only. Values are hidden here and saved "
            "in the local YAML after confirmation. Assertion columns are included in the request.",
            "Подробные проверки: только синтетические значения. Ввод скрыт; после подтверждения "
            "значения сохранятся в локальный YAML. Столбцы проверок включаются в запрос.",
        )
    )
    data = base.model_dump(by_alias=True, exclude_none=True)
    columns = ask(
        say("Columns (comma-separated; * = all)", "Столбцы через запятую; * = все"),
        "id",
        selected_columns,
        say(
            "Use 1–64 unique simple column names, or *.", "Введите 1–64 разных простых имени или *."
        ),
    )

    def column(raw: str) -> str:
        result = raw.strip()
        ScenarioRequest(resource=base.request.resource, columns=[result])
        return result

    filters: dict[str, Any] = {}

    def filter_column(raw: str) -> str:
        result = column(raw)
        if result in filters:
            raise ValueError
        # Reuse the canonical reserved-parameter validation before asking for values.
        probe = {**data, "filters": {result: {"eq": "synthetic"}}}
        Scenario.model_validate(probe)
        return result

    for _ in range(32):
        if not typer.confirm(
            say("Add a request filter?", "Добавить фильтр запроса?"), default=False
        ):
            break
        name = ask(
            say("Filter column", "Столбец фильтра"),
            "id",
            filter_column,
            say(
                "Use a new non-reserved simple column name.",
                "Введите новое простое имя без служебных параметров.",
            ),
        )
        operator = ask(
            say("Operator (eq/neq/gt/gte/lt/lte/is)", "Оператор (eq/neq/gt/gte/lt/lte/is)"),
            "eq",
            lambda raw: choice(raw, {"eq", "neq", "gt", "gte", "lt", "lte", "is"}),
            say(
                "Choose one of the listed operators.", "Выберите один из перечисленных операторов."
            ),
        )
        if operator == "is":
            value: str | int | bool = ask(
                say("IS value (null/true/false)", "Значение IS (null/true/false)"),
                "null",
                lambda raw: choice(raw, {"null", "true", "false"}),
                say("Choose null, true or false.", "Выберите null, true или false."),
            )
        else:
            value = value_prompt(language)
        filters[name] = Filter.model_validate({operator: value}).model_dump(
            by_alias=True, exclude_unset=True
        )

    contains: list[RecordExpectation] = []
    excludes: list[RecordExpectation] = []

    def assertion_column(raw: str) -> str:
        result = column(raw)
        if columns is not None and result not in columns and len(columns) == 64:
            raise ValueError
        return result

    for kind, destination in (("contains", contains), ("excludes", excludes)):
        label = (
            say(
                "Add a record that MUST be present?",
                "Добавить запись, которая ДОЛЖНА быть доступна?",
            )
            if kind == "contains"
            else say(
                "Add a record that MUST be absent?",
                "Добавить запись, которая НЕ ДОЛЖНА быть доступна?",
            )
        )
        for _ in range(64):
            if not typer.confirm(label, default=False):
                break
            name = ask(
                say("Record identifier column", "Столбец идентификатора записи"),
                columns[0] if columns else "id",
                assertion_column,
                say(
                    "Use a simple column name; at most 64 projected columns.",
                    "Введите простое имя; в запросе не более 64 столбцов.",
                ),
            )
            while True:
                value = value_prompt(language)
                if not any(
                    rule.column == name and type(rule.value) is type(value) and rule.value == value
                    for rule in [*contains, *excludes]
                ):
                    break
                typer.echo(
                    say(
                        "That typed record is already checked. Enter a different synthetic value.",
                        "Такая запись уже проверяется. Введите другое тестовое значение.",
                    )
                )
            destination.append(RecordExpectation(column=name, value=value))
            if columns is not None and name not in columns:
                columns.append(name)

    error = ask(
        say(
            "Expected error class (skip/none/authorization/permission/http)",
            "Класс ошибки (skip/none/authorization/permission/http)",
        ),
        "skip",
        lambda raw: choice(raw, {"skip", "none", "authorization", "permission", "http"}),
        say("Choose one of the listed classes or skip.", "Выберите указанный класс или skip."),
    )
    data["request"]["columns"] = columns
    data["filters"] = filters
    data["expect"]["contains"] = [rule.model_dump() for rule in contains]
    data["expect"]["excludes"] = [rule.model_dump() for rule in excludes]
    if error != "skip":
        data["expect"]["error_class"] = error
    typer.echo(
        say("Detailed scenario summary (values hidden):", "Сводка сценария (значения скрыты):")
    )
    typer.echo(
        "  "
        + (", ".join(columns) if columns else "*")
        + say(
            f" | filters: {len(filters)} | contains: {len(contains)}",
            f" | фильтров: {len(filters)} | наличие: {len(contains)}",
        )
        + say(
            f" | excludes: {len(excludes)} | {error}", f" | отсутствие: {len(excludes)} | {error}"
        )
    )
    return Scenario.model_validate(data)
