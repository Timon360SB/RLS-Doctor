"""Managed diagnostic session: local credentials stay in this process only."""

import os
from pathlib import Path
from typing import Literal

import httpx
import typer

from rls_doctor.core.config import ProjectConfig, load_config
from rls_doctor.core.credentials import (
    create_identity,
    credential_values,
    credentials,
    local_status,
)
from rls_doctor.core.errors import DoctorError
from rls_doctor.core.models import DiagnosticEvent, load_event
from rls_doctor.identity.validation import local_headers
from rls_doctor.postgres.inspector import inspect_table
from rls_doctor.replay.runner import replay
from rls_doctor.replay.scenarios import Scenario, load_scenario
from rls_doctor.reports.console import Language, render, word
from rls_doctor.reports.files import available, write_report


def run_session(
    config_path: Path,
    workdir: Path,
    scenario_path: Path | None,
    language: Language,
    *,
    run_once: bool,
    create_user: bool,
    output_format: Literal["console", "json"] = "console",
    event_path: Path | None = None,
    output_path: Path | None = None,
) -> int:
    if output_path is not None and not run_once:
        raise DoctorError(
            "SESSION_OUTPUT_MODE", "Use --run with --output; one file represents one run."
        )
    available(output_path)
    if output_format == "json" and not run_once:
        raise DoctorError(
            "SESSION_JSON_MODE",
            "Use --run with --format json; interactive menus require console output.",
        )

    def note(message: str) -> None:
        if output_format == "console":
            typer.echo(message)

    config = load_config(config_path)
    env = config.environment
    env.origin()  # reject unapproved config before running even the local CLI
    scenario = load_scenario(scenario_path or config_path.parent / "documents.yaml")
    if scenario.request.resource not in env.resources:
        raise DoctorError(
            "RESOURCE_NOT_ALLOWED", "Scenario table is not in the approved resource allowlist."
        )
    event = load_event(event_path) if event_path is not None else None
    if event is not None and event.request.resource != scenario.request.resource:
        raise DoctorError("EVENT_MISMATCH", "Event and scenario refer to different resources.")
    token_name = scenario.identity.token_env
    if token_name is not None and (
        not token_name.startswith("RLS_DOCTOR_")
        or token_name
        in {
            env.anon_key_env,
            env.database_url_env,
            env.jwt_secret_env,
        }
    ):
        raise DoctorError(
            "SESSION_VARIABLE_NAMES", "Test-token variable must be a separate RLS_DOCTOR_ name."
        )
    values = credential_values(local_status(workdir), env)
    with credentials(
        values, clear=(env.jwt_secret_env,) if env.jwt_secret_env not in values else ()
    ):
        note(
            word(
                language,
                "Local project matched. Credentials are in this process only; nothing was saved.",
                "Локальный проект совпадает. Ключи находятся только в памяти "
                "процесса; ничего не сохранено.",
            )
        )
        note(
            word(
                language,
                "Application rows and policies are not prepared. Auth signup needs approval. "
                "Exiting leaves Docker running.",
                "Строки и политики приложения не подготавливаются. Регистрация в Auth требует "
                "разрешения. После выхода Docker продолжит работать.",
            )
        )
        with httpx.Client(timeout=10, trust_env=False, follow_redirects=False) as client:
            local_headers(env, client, None)  # reject privileged or invalid API keys before signup
            if token_name and not os.environ.get(token_name):
                note(
                    word(
                        language,
                        "A new synthetic Auth user does not own your existing rows. It "
                        "remains until you remove it or reset the local stack. No "
                        "table data is prepared.",
                        "Новый тестовый Auth-пользователь не владеет существующими "
                        "строками. Он останется до удаления или сброса локальной "
                        "среды. Данные таблиц не подготавливаются.",
                    )
                )
                approved = create_user
                if not approved and not run_once:
                    approved = typer.confirm(
                        word(
                            language,
                            "Create one synthetic user in this disposable local Auth?",
                            "Создать одного синтетического пользователя в локальной тестовой Auth?",
                        ),
                        default=False,
                    )
                if not approved:
                    raise DoctorError(
                        "TEST_IDENTITY_REQUIRED",
                        "Supply an existing local test-token environment reference or "
                        "explicitly approve a synthetic Auth user.",
                    )
                token = create_identity(env, approved=True, client=client)
                # Nested scope restores an inherited token even if menu/replay raises.
                with credentials({token_name: token}):
                    return menu(
                        config,
                        scenario,
                        language,
                        run_once=run_once,
                        output_format=output_format,
                        event=event,
                        output_path=output_path,
                    )
            local_headers(
                env, client, token_name
            )  # local signature/issuer checks, not a role claim
        return menu(
            config,
            scenario,
            language,
            run_once=run_once,
            output_format=output_format,
            event=event,
            output_path=output_path,
        )


def menu(
    config: ProjectConfig,
    scenario: Scenario,
    language: Language,
    *,
    run_once: bool,
    output_format: Literal["console", "json"] = "console",
    event: DiagnosticEvent | None = None,
    output_path: Path | None = None,
) -> int:
    if not config.environment.confirm_identity and output_format == "console":
        typer.echo(
            word(
                language,
                "Identity probe disabled: executed database role remains "
                "unconfirmed; replay may return UNKNOWN.",
                "Пробник роли выключен: исполняемая роль БД не подтверждена; "
                "replay может вернуть UNKNOWN.",
            )
        )
    while True:
        if run_once:
            choice = "1"
        else:
            typer.echo(
                word(
                    language,
                    "\n1. Run scenario\n2. Inspect table configuration\n0. Exit session",
                    "\n1. Выполнить сценарий\n2. Проверить настройки таблицы\n0. Завершить сессию",
                )
            )
            choice = typer.prompt(">", default="0")
        if choice == "0":
            typer.echo(
                word(
                    language,
                    "Session closed. Docker remains running.",
                    "Сессия закрыта. Docker продолжает работать.",
                )
            )
            return 0
        if choice == "1":
            report = replay(scenario, config, event, inspect=True)
            if output_path is not None:
                write_report(report, output_path)
            render(report, output_format, language)
            if run_once:
                return {"PASS": 0, "FAIL": 1, "UNKNOWN": 2, "ERROR": 3}[report["result"]]
        elif choice == "2":
            report = inspect_table(
                config.environment.database_dsn(),
                scenario.request.schema_name,
                scenario.request.resource,
                scenario.identity.type,
            )
            report.update(
                result="UNKNOWN",
                resource=f"{scenario.request.schema_name}.{scenario.request.resource}",
            )
            render(report, output_format, language)
        else:
            typer.echo(word(language, "Choose 0, 1 or 2.", "Введите 0, 1 или 2."))
