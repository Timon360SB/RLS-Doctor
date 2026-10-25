"""Guided configuration: no secrets, network access, or database writes."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import typer
import yaml

from rls_doctor.core.config import LocalEnvironment, ProjectConfig, validate_local_url
from rls_doctor.core.errors import DoctorError
from rls_doctor.replay.scenarios import Scenario, ScenarioRequest
from rls_doctor.reports.console import Language, word


def ask[T](label: str, default: str | int, parse: Callable[[str], T], error: str) -> T:
    """Keep valid earlier answers; display only a fixed safe validation message."""
    while True:
        raw = typer.prompt(label, default=str(default), type=str)
        try:
            return parse(raw)
        except (ValueError, DoctorError):
            typer.echo(error)


def api_origin(value: str) -> str:
    value = value.strip()
    port = urlsplit(value).port
    if port is None:
        raise ValueError
    return validate_local_url(value, [port])


def table_name(value: str) -> tuple[str, str]:
    schema, resource = value.strip().split(".")
    request = ScenarioRequest.model_validate({"schema": schema, "resource": resource})
    if resource == "rpc":
        raise ValueError
    return request.schema_name, request.resource


def identity_role(value: str) -> str:
    value = value.strip().lower()
    if value not in {"anon", "authenticated"}:
        raise ValueError
    return value


def integer(value: str, minimum: int, maximum: int) -> int:
    result = int(value)
    if not minimum <= result <= maximum:
        raise ValueError
    return result


def row_count(value: str) -> int | None:
    if value.strip().lower() in {"skip", "-", "пропустить"}:
        return None
    return integer(value, 0, 10000)


def guided_files(language: Language) -> tuple[str, str]:
    """Collect synthetic scenario expectations; approval remains off by default."""

    def say(en: str, ru: str) -> str:
        return word(language, en, ru)

    typer.echo(
        say(
            "Configure a disposable local test project. No connection or "
            "database changes will run.",
            "Настроим одноразовый локальный тестовый проект. Подключений и "
            "изменений базы не будет.",
        )
    )
    typer.echo(
        say(
            "Do not enter tokens, passwords or production data.",
            "Не вводите токены, пароли или рабочие данные.",
        )
    )
    api = ask(
        say("Local API URL", "Адрес локального API"),
        "http://127.0.0.1:54321",
        api_origin,
        say(
            "Use a numeric loopback HTTP URL with an explicit port.",
            "Используйте HTTP-адрес с числовым loopback-IP и явным портом.",
        ),
    )
    port = ask(
        say("Local PostgreSQL port", "Порт локального PostgreSQL"),
        54322,
        lambda value: integer(value, 1, 65535),
        say("Enter a port from 1 to 65535.", "Введите порт от 1 до 65535."),
    )
    schema, resource = ask(
        say("Test table (schema.table)", "Тестовая таблица (схема.таблица)"),
        "public.documents",
        table_name,
        say(
            "Use simple schema.table identifiers; RPC is unsupported.",
            "Введите простые имена схема.таблица; RPC не поддерживается.",
        ),
    )
    role = ask(
        say("Test identity (anon/authenticated)", "Тестовая роль (anon/authenticated)"),
        "authenticated",
        identity_role,
        say("Choose anon or authenticated.", "Выберите anon или authenticated."),
    )
    status = ask(
        say("Expected HTTP status", "Ожидаемый HTTP-статус"),
        200,
        lambda value: integer(value, 100, 599),
        say("Enter an HTTP status from 100 to 599.", "Введите HTTP-статус от 100 до 599."),
    )
    count = ask(
        say(
            "Expected number of rows (skip = no comparison)",
            "Ожидаемое число строк (пропустить = не сравнивать)",
        ),
        say("skip", "пропустить") if status >= 400 else "1",
        row_count,
        say("Enter 0–10000 or skip.", "Введите число 0–10000 или пропустить."),
    )
    identity: dict[str, Any] = {"type": role}
    if role == "authenticated":
        identity["token_env"] = "RLS_DOCTOR_TEST_TOKEN"
    scenario = Scenario.model_validate(
        {
            "version": 1,
            "name": "local_access_check",
            "request": {"schema": schema, "resource": resource},
            "identity": identity,
            "expect": {"status": status, "row_count": count},
        }
    )
    api_port = urlsplit(api).port
    assert api_port is not None
    env = LocalEnvironment(
        api_url=api,
        allowed_api_ports=[api_port],
        allowed_db_ports=[port],
        resources=[resource],
        confirm_identity=False,
    )
    typer.echo(say("Review the destination and expectations:", "Проверьте адрес и ожидания:"))
    typer.echo(
        f"  {api} | PostgreSQL: {port} | {schema}.{resource} | {role} | HTTP {status} | "
        + (str(count) if count is not None else say("rows not compared", "строки не сравниваются"))
    )
    typer.echo(
        say(
            "Only proceed with synthetic data and local credentials. "
            "Loopback can be forwarded; verify the actual stack.",
            "Используйте только синтетические данные и локальные ключи. "
            "Loopback может перенаправляться: проверьте саму среду.",
        )
    )
    env.approved_local = typer.confirm(
        say(
            "Approve this destination as disposable local test infrastructure?",
            "Разрешить этот адрес как одноразовую локальную тестовую среду?",
        ),
        default=False,
    )
    if not typer.confirm(
        say("Save configuration and scenario?", "Сохранить конфигурацию и сценарий?"), default=True
    ):
        raise typer.Abort()
    config = ProjectConfig(environment=env)
    lines = ["version = 1", "[environment]"]
    lines += [f"{k} = {json.dumps(v)}" for k, v in config.environment.model_dump().items()]
    # scenario values are synthetic expectations only; no credentials are requested.
    scenario_text = yaml.safe_dump(
        scenario.model_dump(by_alias=True, exclude_none=True), sort_keys=False
    )
    return "\n".join(lines) + "\n", scenario_text


def initialize(directory: Path, contents: tuple[str, str]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    paths = [directory / "rls-doctor.toml", directory / "documents.yaml"]
    if any(p.exists() or p.is_symlink() for p in paths):
        raise DoctorError("INIT_EXISTS", "Example files already exist; choose another directory.")
    for path, content in zip(paths, contents, strict=True):
        with path.open("x", encoding="utf-8") as handle:
            handle.write(content)
