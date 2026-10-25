"""Isolated practice database and real CLI walkthrough; setup is explicit."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx
import psycopg
import yaml
from e2e import OTHER, OWN, ROOT, run_integration_suite
from manual_session import write_session_files
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from rich.console import Console
from rich.table import Table
from rls_doctor.core.config import LocalEnvironment, ProjectConfig
from rls_doctor.core.credentials import (
    create_identity,
    credential_values,
    credentials,
    find_cli,
    local_status,
)
from rls_doctor.core.errors import DoctorError
from rls_doctor.core.models import parse_event
from rls_doctor.identity.validation import verify_test_token
from rls_doctor.reports.console import Language, render, word

LAB = ROOT / ".rls-doctor" / "practice"
TABLES = ["documents", "blocked_documents", "no_grant_documents", "leaky_documents"]


@contextmanager
def practice_lock(directory: Path | None = None) -> Iterator[None]:
    """Hold an OS lock; closing/crashing releases it without a stale PID file."""
    location = directory if directory is not None else LAB
    location.mkdir(parents=True, exist_ok=True)
    with (location / ".session.lock").open("a+b") as handle:
        # Windows byte-range locking needs a byte. File contents carry no secrets.
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise DoctorError(
                "LAB_SESSION_BUSY",
                "Practice session is already open or its lock is unavailable. "
                "Close the other lab window and retry; do not delete the lock file. "
                "Учебная сессия уже открыта или блокировка недоступна. "
                "Закройте другое окно лаборатории и повторите запуск.",
            ) from None
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def prepare_files() -> None:
    """Create only the fixed ignored lab; never overwrite operator changes."""
    source = ROOT / "fixtures/supabase"
    config = (source / "config.toml").read_text(encoding="utf-8")
    config = config.replace(
        'project_id = "rls-doctor-fixtures"', 'project_id = "rls-doctor-practice"'
    )
    for old, new in [(54321, 55321), (54322, 55322), (54320, 55320)]:
        config = config.replace(str(old), str(new))
    files = {"config.toml": config, "seed.sql": (source / "seed.sql").read_text(encoding="utf-8")}
    files["seed.sql"] = (
        files["seed.sql"]
        .replace("Synthetic document A", "Lab: Alice project plan")
        .replace("Synthetic document B", "Lab: Bob project notes")
    )
    for migration in (source / "migrations").glob("*.sql"):
        files["migrations/" + migration.name] = migration.read_text(encoding="utf-8")
    for name, content in files.items():
        path = LAB / "supabase" / name
        if path.exists() and path.read_text(encoding="utf-8") != content:
            raise DoctorError(
                "LAB_FILES_CHANGED",
                "Practice setup files differ; no files or database were "
                "reset. Use the existing lab or review your changes.",
            )
    for name, content in files.items():
        path = LAB / "supabase" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(content, encoding="utf-8", newline="\n")


def execute(
    arguments: list[str], *, input: str | None = None, timeout: int = 120
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        cwd=ROOT,
        input=input,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


class Practice:
    def __init__(
        self, config: ProjectConfig, tokens: list[str], private: list[str], directory: Path
    ):
        self.config = config
        self.tokens = tokens
        self.private = private
        self.directory = directory
        self.config_path = directory / "rls-doctor.toml"

    def safe(self, output: str) -> None:
        if any(secret and secret in output for secret in self.private):
            raise DoctorError("LAB_SECRET_OUTPUT", "Unexpected credential output was blocked.")

    def capture(self) -> dict[str, Any]:
        with credentials({"RLS_DOCTOR_LOCAL_API_URL": self.config.environment.origin()}):
            child = execute(["node", "examples/node-basic/live-event.mjs"], timeout=30)
        if child.returncode or len(child.stdout) > 65536:
            raise DoctorError("LAB_CAPTURE_FAILED", "Live SDK capture failed; raw logs suppressed.")
        self.safe(child.stdout)
        event = json.loads(child.stdout)
        parse_event(event)
        (self.directory / "event.json").write_text(child.stdout, encoding="utf-8")
        bad = {**event, "schema_version": "999.0"}
        (self.directory / "invalid-event.json").write_text(json.dumps(bad), encoding="utf-8")
        return event

    def call(self, args: list[str], *, token: str | None = None) -> tuple[int, dict[str, Any]]:
        with credentials({"RLS_DOCTOR_TEST_TOKEN": token or self.tokens[0]}):
            child = execute(
                [sys.executable, "-m", "rls_doctor.cli.main", *args, "--format", "json"]
            )
        self.safe(child.stdout)
        try:
            data = json.loads(child.stdout)
            if not isinstance(data, dict):
                raise ValueError
        except (ValueError, UnicodeError):
            raise DoctorError(
                "LAB_CLI_OUTPUT",
                "CLI did not return a structured report; unsafe details suppressed.",
            ) from None
        return child.returncode, data

    def check(self, key: str) -> tuple[int, dict[str, Any]]:
        cfg = ["--config", str(self.config_path)]
        if key == "doctor":
            return self.call(["doctor", *cfg])
        if key in {"validate", "analyze", "invalid-event"}:
            self.capture()
            action = "analyze" if key == "analyze" else "validate"
            filename = "invalid-event.json" if key == "invalid-event" else "event.json"
            args = [action, str(self.directory / filename)]
            if action == "analyze":
                args += ["--expected-role", "authenticated"]
            return self.call(args)
        if key == "inspect":
            return self.call(["inspect", "public.no_grant_documents", *cfg])
        if key == "disabled":
            return self.call(["doctor", "--config", str(self.directory / "disabled.toml")])
        if key == "unsafe":
            return self.call(["doctor", "--config", str(self.directory / "unsafe.toml")])
        if key == "unsupported":
            return self.call(["replay", str(self.directory / "unsupported.yaml"), *cfg])
        scenario = "own-row" if key == "invalid-token" else key
        return self.call(
            ["replay", str(self.directory / f"{scenario}.yaml"), *cfg, "--inspect"],
            token="invalid-local-token"
            if key == "invalid-token"
            else self.tokens[1]
            if key == "second-user"
            else None,
        )

    def regression(self) -> None:
        # Setup-only administrative access in the fixed, separately created lab.
        if self.config.environment.origin() != "http://127.0.0.1:55321":
            raise DoctorError("LAB_ENDPOINT", "Regression setup is restricted to the practice lab.")
        params = conninfo_to_dict(self.config.environment.database_dsn())
        if params.get("port") != "55322":
            raise DoctorError(
                "LAB_ENDPOINT", "Regression setup requires the practice database port."
            )
        params["user"] = "supabase_admin"
        with credentials({"RLS_DOCTOR_ALLOW_FIXTURE_SETUP": "1"}):
            run_integration_suite(make_conninfo(**params))

    def session(self, language: Language, *, once: bool = False) -> int:
        args = [
            sys.executable,
            "-m",
            "rls_doctor.cli.main",
            "session",
            "--config",
            str(self.config_path),
            "--workdir",
            str(LAB),
            "--language",
            language,
        ]
        if once:
            child = execute([*args, "--run"])
            self.safe(child.stdout)
            return child.returncode
        # Credentials are inherited by this child only; never exported to a parent shell.
        return subprocess.run(args, cwd=ROOT, check=False).returncode


CASES = [
    ("doctor", "Check connection", "Проверка подключения", 0),
    (
        "validate",
        "Capture SDK request and validate",
        "Захват SDK и проверка события",
        0,
    ),
    ("analyze", "Offline event analysis", "Офлайн-анализ события", 2),
    ("own-row", "Alice: own row only", "Алиса: только своя строка", 0),
    ("second-user", "Bob: own row only", "Боб: только своя строка", 0),
    ("missing-auth", "Missing authorization", "Нет авторизации", 1),
    ("default-deny", "No allowing policy", "Нет разрешающей политики", 1),
    ("missing-grant", "Expected SELECT denial", "Ожидаемый отказ SELECT", 0),
    (
        "tenant-isolation",
        "Detect another user's row",
        "Обнаружение чужой строки",
        1,
    ),
    (
        "nonexistent-row",
        "Nonexistent row ambiguity",
        "Неоднозначный пустой ответ",
        0,
    ),
    (
        "inspect",
        "Inspect missing privilege",
        "Анализ отсутствующего права",
        2,
    ),
    (
        "invalid-token",
        "Reject invalid token",
        "Отклонение неверного токена",
        3,
    ),
    (
        "invalid-event",
        "Reject invalid event",
        "Отклонение неверного события",
        3,
    ),
    (
        "disabled",
        "Replay approval required",
        "Требуется разрешение локального запуска",
        3,
    ),
    (
        "unsafe",
        "Reject remote address",
        "Отклонение удалённого адреса",
        3,
    ),
    ("unsupported", "Reject PATCH replay", "Отклонение PATCH-запроса", 3),
]


def expected_evidence(key: str, code: int, report: dict[str, Any]) -> bool:
    expected = next(c[3] for c in CASES if c[0] == key)
    if code != expected:
        return False
    if key in {
        "own-row",
        "second-user",
        "missing-auth",
        "default-deny",
        "tenant-isolation",
        "nonexistent-row",
        "missing-grant",
    }:
        status, count = {
            "own-row": (200, 1),
            "second-user": (200, 1),
            "missing-auth": (200, 0),
            "default-deny": (200, 0),
            "tenant-isolation": (200, 2),
            "nonexistent-row": (200, 0),
            "missing-grant": (403, None),
        }[key]
        if (
            report.get("http", {}).get("status") != status
            or report.get("http", {}).get("row_count") != count
        ):
            return False
        checks = {c["check"]: c["result"] for c in report.get("checks", [])}
        required = {
            "tenant-isolation": {
                "row_count": "FAIL",
                "excludes_1": "FAIL",
                "executed_role": "PASS",
            },
            "missing-auth": {"executed_role": "FAIL", "row_count": "FAIL"},
            "default-deny": {"row_count": "FAIL", "executed_role": "PASS"},
        }
        return all(checks.get(name) == value for name, value in required.get(key, {}).items())
    if key in {"invalid-token", "invalid-event", "disabled", "unsafe", "unsupported"}:
        wanted = {
            "invalid-token": "INVALID_TEST_TOKEN",
            "invalid-event": "INVALID_EVENT",
            "disabled": "LOCAL_APPROVAL_REQUIRED",
            "unsafe": "UNSAFE_ENDPOINT",
            "unsupported": "INVALID_SCENARIO",
        }[key]
        return report.get("error", {}).get("code") == wanted
    if key == "inspect":
        return any(
            f.get("code") == "SELECT_PRIVILEGE_MISSING" for f in report.get("conclusions", [])
        )
    if key == "analyze":
        return (
            report.get("analysis_mode") == "capture_only"
            and report.get("identity", {}).get("confirmed_role") is None
        )
    return True


def setup(config: ProjectConfig, directory: Path) -> Practice:
    env = config.environment
    tokens = []
    subjects = []
    with httpx.Client(timeout=10, trust_env=False, follow_redirects=False) as client:
        for _ in range(2):
            token = create_identity(env, approved=True, client=client)
            tokens.append(token)
            subjects.append(verify_test_token(token, env, client)["sub"])
    with psycopg.connect(env.database_dsn()) as connection:
        for table in TABLES:
            count = connection.execute(
                sql.SQL("SELECT count(*) FROM public.{}").format(sql.Identifier(table))
            ).fetchone()
            if count != (2,):
                raise DoctorError(
                    "LAB_DATA_CHANGED", "Practice row counts differ; no lab reset was performed."
                )
            for row, subject in zip((OWN, OTHER), subjects, strict=True):
                result = connection.execute(
                    sql.SQL("UPDATE public.{} SET owner_id=%s WHERE id=%s").format(
                        sql.Identifier(table)
                    ),
                    (subject, row),
                )
                if result.rowcount != 1:
                    raise DoctorError(
                        "LAB_DATA_CHANGED", "Synthetic fixture row missing; setup rolled back."
                    )
    write_session_files(directory, config)
    own = yaml.safe_load((directory / "own-row.yaml").read_text(encoding="utf-8"))
    (directory / "documents.yaml").write_text(yaml.safe_dump(own), encoding="utf-8")
    own["name"] = "second_user"
    own["expect"]["contains"][0]["value"] = OTHER
    own["expect"]["excludes"][0]["value"] = OWN
    (directory / "second-user.yaml").write_text(yaml.safe_dump(own), encoding="utf-8")
    cfg = (directory / "rls-doctor.toml").read_text(encoding="utf-8")
    (directory / "disabled.toml").write_text(
        cfg.replace("approved_local = true", "approved_local = false"), encoding="utf-8"
    )
    (directory / "unsafe.toml").write_text(
        cfg.replace("http://127.0.0.1:55321", "http://example.invalid:55321"), encoding="utf-8"
    )
    own["request"]["method"] = "PATCH"
    (directory / "unsupported.yaml").write_text(yaml.safe_dump(own), encoding="utf-8")
    private = [
        *tokens,
        os.environ[env.anon_key_env],
        os.environ.get(env.jwt_secret_env, ""),
        env.database_dsn(),
    ]
    return Practice(config, tokens, private, directory)


def run() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", choices=["en", "ru"], default="en")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    language: Language = args.language
    console = Console(markup=False, highlight=False)
    console.print(
        word(
            language,
            "Practice database: two synthetic users, four tables, eight "
            "documents. API 55321 / DB 55322. No real application data.",
            "Учебная база: два тестовых пользователя, четыре таблицы, "
            "восемь документов. API 55321 / БД 55322. Рабочих данных нет.",
        )
    )
    console.print(
        word(
            language,
            "Preparation starts only this lab, creates new Auth users "
            "and reassigns its synthetic rows. Do not run a second lab "
            "session concurrently. Users remain until local stack reset.",
            "Подготовка запускает только эту базу, создаёт "
            "Auth-пользователей и назначает им тестовые строки. Не "
            "запускайте две учебные сессии одновременно. Пользователи "
            "останутся до сброса среды.",
        )
    )
    console.print(
        word(
            language,
            "Full checks also create and remove temporary regression "
            "roles/schema only in this lab.",
            "Полная проверка также создаёт и удаляет временные "
            "роли/схему регрессий только в этой базе.",
        )
    )
    if not args.check and console.input(
        word(
            language,
            "Prepare practice database? [y/n]: ",
            "Подготовить учебную базу? [д/н]: ",
        )
    ).strip().lower() not in {"y", "yes", "д", "да"}:
        return 0
    pnpm = shutil.which("pnpm.cmd") or shutil.which("pnpm")
    if not pnpm:
        raise DoctorError("PNPM_MISSING", "Install pnpm 11.25.0 and reopen the terminal.")
    with console.status(
        word(
            language,
            "Preparing SDK and isolated database…",
            "Подготовка SDK и отдельной базы…",
        )
    ):
        for command in ([pnpm, "install", "--frozen-lockfile"], [pnpm, "build"]):
            if execute(command, timeout=300).returncode:
                raise DoctorError(
                    "LAB_BUILD_FAILED",
                    "Dependency install or SDK build failed; check tools/internet and retry.",
                )
        prepare_files()
        if execute([find_cli(), "start", "--workdir", str(LAB)], timeout=900).returncode:
            raise DoctorError(
                "LAB_START_FAILED",
                "Practice startup failed. Check Docker and ports "
                "55320-55322; raw startup logs suppressed.",
            )
    env = LocalEnvironment(
        approved_local=True,
        api_url="http://127.0.0.1:55321",
        allowed_api_ports=[55321],
        allowed_db_ports=[55322],
        resources=TABLES,
    )
    values = credential_values(local_status(LAB), env)
    import tempfile

    directory = Path(tempfile.mkdtemp(prefix="run-", dir=LAB))
    with credentials(values):
        practice = setup(ProjectConfig(environment=env), directory)
        with credentials({"RLS_DOCTOR_TEST_TOKEN": practice.tokens[0]}):
            console.print(
                word(
                    language,
                    "Ready. No keys need copying. Config/scenarios: ",
                    "Готово. Ключи копировать не нужно. Конфигурация/сценарии: ",
                )
                + str(directory)
            )

            def all_checks() -> bool:
                results = []
                table = Table(title=word(language, "Practice checklist", "Проверки учебной базы"))
                table.add_column(word(language, "Check", "Проверка"))
                table.add_column(word(language, "Expected / Actual", "Ожидалось / Получено"))
                table.add_column(word(language, "Match", "Совпадает"))
                for key, en, ru, expected in CASES:
                    code, report = practice.check(key)
                    matched = expected_evidence(key, code, report)
                    results.append(matched)
                    table.add_row(
                        word(language, en, ru),
                        f"{expected} / {code}",
                        word(language, "OK", "Да")
                        if matched
                        else word(language, "MISMATCH", "Нет"),
                    )
                session_ok = practice.session(language, once=True) == 0
                results.append(session_ok)
                table.add_row(
                    word(language, "Managed session", "Управляемая сессия"),
                    "0 / " + ("0" if session_ok else word(language, "error", "ошибка")),
                    word(language, "OK", "Да") if session_ok else word(language, "MISMATCH", "Нет"),
                )
                practice.regression()
                results.append(True)
                table.add_row(
                    word(language, "PostgreSQL regression suite", "Регрессионные тесты PostgreSQL"),
                    "0 / 0",
                    word(language, "OK", "Да"),
                )
                console.print(table)
                (directory / "checklist.json").write_text(
                    json.dumps({"checks": len(results), "matched": sum(results)}, indent=2),
                    encoding="utf-8",
                )
                return all(results)

            if args.check:
                return 0 if all_checks() else 1
            while True:
                console.print("\n" + word(language, "Choose a check:", "Выберите проверку:"))
                for i, (_, en, ru, _) in enumerate(CASES, 1):
                    console.print(f"{i}. {word(language, en, ru)}")
                console.print(
                    word(
                        language,
                        "17. Managed session menu\n18. Run all checks\n19. Export JSON "
                        "replay report\n20. Run PostgreSQL regressions\n"
                        "0. Exit (database stays running)",
                        "17. Меню управляемой сессии\n18. Все проверки\n19. Сохранить "
                        "JSON-отчёт\n20. Регрессионные тесты PostgreSQL\n"
                        "0. Выход (база продолжит работать)",
                    )
                )
                choice = console.input("> ").strip()
                if choice == "0":
                    console.print(
                        word(
                            language,
                            "Stop database: lab.cmd -Stop",
                            "Остановить базу: lab.cmd -Stop",
                        )
                    )
                    return 0
                if choice == "17":
                    practice.session(language)
                elif choice == "18":
                    all_checks()
                elif choice == "20":
                    practice.regression()
                    console.print(
                        word(
                            language,
                            "PASS real PostgreSQL inspector integration suite",
                            "PASS: регрессионные тесты инспектора на настоящем PostgreSQL",
                        )
                    )
                elif choice == "19":
                    _, report = practice.check("own-row")
                    output = json.dumps(report, ensure_ascii=False, indent=2)
                    practice.safe(output)
                    path = directory / "report.json"
                    path.write_text(output, encoding="utf-8")
                    console.print(str(path))
                elif choice in {str(i) for i in range(1, len(CASES) + 1)}:
                    key, en, ru, wanted = CASES[int(choice) - 1]
                    console.print(
                        word(language, en, ru)
                        + " | "
                        + word(language, "Expected exit: ", "Ожидаемый код: ")
                        + str(wanted)
                    )
                    code, report = practice.check(key)
                    render(report, language=language)
                    console.print(
                        word(language, "Expected / Actual: ", "Ожидалось / Получено: ")
                        + f"{wanted} / {code}. "
                        + (
                            word(language, "MATCH", "СОВПАДАЕТ")
                            if expected_evidence(key, code, report)
                            else word(language, "MISMATCH", "НЕ СОВПАДАЕТ")
                        )
                    )
                else:
                    console.print(word(language, "Choose 0–20.", "Введите число 0–20."))


def main() -> int:
    with practice_lock():
        return run()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyboardInterrupt, EOFError):
        print("Lab closed / Учебная сессия закрыта. Stop / Остановить: lab.cmd -Stop")
    except DoctorError as error:
        print(
            f"Practice setup/check incomplete / Подготовка или проверка не завершена: {error.code}"
        )
        print(str(error))
        raise SystemExit(3) from None
    except Exception:
        print(
            "Practice setup/check failed; credential-bearing details "
            "suppressed. Check Docker and retry lab.cmd."
        )
        raise SystemExit(3) from None
