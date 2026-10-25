"""Guided local fixture demo. Credentials stay in process memory; no raw logs."""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from e2e import ROOT, setup_fixture
from manual_session import write_session_files
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rls_doctor.core.errors import DoctorError
from rls_doctor.replay.runner import replay
from rls_doctor.replay.scenarios import load_scenario

CASES = [
    ("own-row", "Доступ к своей строке", "Own-row access", "PASS"),
    ("tenant-isolation", "Обнаружение чужой строки", "Detect another user's row", "FAIL"),
    ("missing-auth", "Запрос без авторизации", "Missing authorization", "FAIL"),
    ("default-deny", "Нет разрешающей политики", "No allowing policy", "FAIL"),
    ("missing-grant", "Нет права SELECT", "Missing SELECT grant", "PASS"),
    ("nonexistent-row", "Строка не существует", "Nonexistent row", "PASS"),
]


def text(ru: str, en: str, language: str) -> str:
    return ru if language == "ru" else en


def command(cli: str, action: str, *, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            cli,
            action,
            "--workdir",
            "fixtures",
            *(["--output", "json"] if action == "status" else []),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def summary(report: dict[str, Any], language: str) -> list[tuple[str, str]]:
    """Display observed values only, never raw report fields/rows or fixture secrets."""
    checks = report.get("checks", [])
    contains = [c for c in checks if c["check"].startswith("contains")]
    excludes = [c for c in checks if c["check"].startswith("excludes")]
    http = report.get("http") or {}
    role = report.get("identity", {}).get("confirmed_role")
    expected_count = next((c.get("expected") for c in checks if c["check"] == "row_count"), None)
    expected_status = next((c.get("expected") for c in checks if c["check"] == "http_status"), None)
    passed = report.get("result") == "PASS"
    result = text(
        "Совпадает с ожиданием" if passed else "Ожидание не выполнено",
        "Matches expectation" if passed else "Expectation not met",
        language,
    )
    if report.get("result") in {"UNKNOWN", "ERROR"}:
        result = text("Проверка не завершена", "Check incomplete", language)
    observed = text("Нет ответа API", "No API response", language)
    count = http.get("row_count")
    count_ru = str(count) if count is not None else "не применимо"
    count_en = str(count) if count is not None else "not applicable"
    if http:
        observed = f"HTTP {http['status']}; " + text(
            f"строк: {count_ru}; роль: {role or 'не подтверждена'}",
            f"rows: {count_en}; role: {role or 'unconfirmed'}",
            language,
        )
    expectation = f"HTTP {expected_status}; " + text(
        f"строк: {expected_count}" if expected_count is not None else "ожидаемый отказ доступа",
        f"rows: {expected_count}" if expected_count is not None else "expected access denial",
        language,
    )
    evidence = []
    if contains:
        evidence.append(
            text("своя строка", "own row", language)
            + ": "
            + (
                text("найдена", "present", language)
                if all(c["result"] == "PASS" for c in contains)
                else text("ожидание нарушено", "expectation violated", language)
            )
        )
    if excludes:
        evidence.append(
            text("чужая строка", "other user's row", language)
            + ": "
            + (
                text("не получена", "not returned", language)
                if all(c["result"] == "PASS" for c in excludes)
                else (
                    text("получена", "returned", language)
                    if any(c["result"] == "FAIL" for c in excludes)
                    else text("не установлено", "unverified", language)
                )
            )
        )
    next_step = text(
        "Сравните ожидания, владельцев строк, GRANT и SELECT-политику.",
        "Compare expectations, row ownership, grants and SELECT policies.",
        language,
    )
    if any(c["result"] == "FAIL" for c in excludes):
        next_step = text(
            "Проверьте ограничение по владельцу в SELECT-политике тестовой таблицы.",
            "Check the owner restriction in the fixture table's SELECT policy.",
            language,
        )
    meaning = (
        text(
            "Ответ соответствует заданному ожиданию; это не общая оценка безопасности.",
            "The response matches this expectation; this is not a general security assessment.",
            language,
        )
        if passed
        else text(
            "Фактический доступ отличается от ожидаемого. Причину нужно проверить отдельно.",
            "Observed access differs from the expectation. Verify the cause separately.",
            language,
        )
    )
    if role == "anon" and report.get("identity", {}).get("expected_role") == "authenticated":
        meaning = text(
            "Запрос выполнен анонимно вместо ожидаемой авторизации.",
            "The request ran anonymously instead of as an authenticated user.",
            language,
        )
        next_step = text(
            "Проверьте передачу пользовательского токена в запросе.",
            "Check that the request sends the user's token.",
            language,
        )
    if passed:
        next_step = text(
            "Перейдите к примеру обнаружения проблемы в меню.",
            "Choose a problem-detection example from the menu.",
            language,
        )
    if report.get("result") in {"UNKNOWN", "ERROR"}:
        meaning = text(
            "Доказательств недостаточно: поведение не подтверждено.",
            "Evidence is incomplete; behavior is not confirmed.",
            language,
        )
    rows = [
        (text("Ожидалось", "Expected", language), expectation),
        (text("Получено · наблюдение", "Observed", language), observed),
        (text("Результат", "Result", language), result + f" ({report.get('result', 'UNKNOWN')})"),
    ]
    rows.append((text("Что это означает", "Meaning", language), meaning))
    if evidence:
        rows.append((text("Проверка строк", "Row assertions", language), "; ".join(evidence)))
    if http.get("row_count") == 0 and http.get("status") == 200:
        rows.append(
            (
                text("Не установлено", "Unverified", language),
                text(
                    "Пустой ответ сам по себе не доказывает запрет RLS: возможны "
                    "фильтры или отсутствие строки.",
                    "An empty response alone does not prove RLS denial: filters or "
                    "missing rows can cause it.",
                    language,
                ),
            )
        )
    rows.append((text("Следующий шаг", "Next step", language), next_step))
    return rows


def show_report(console: Console, report: dict[str, Any], language: str) -> None:
    table = Table(show_header=False, box=None, padding=(0, 2))
    for label, value in summary(report, language):
        table.add_row(label, value)
    console.print(table)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", choices=["en", "ru"], default="en")
    parser.add_argument("--check", action="store_true", help="Run all demo scenarios without menu")
    parser.add_argument("--stop", action="store_true", help="Stop only this fixture stack")
    args = parser.parse_args()
    language = args.language
    console = Console(highlight=False, markup=False)
    cli = shutil.which("supabase")
    if cli is None:
        console.print(
            text(
                "Не найден Supabase CLI. Запустите demo.cmd.",
                "Supabase CLI not found. Run demo.cmd.",
                language,
            )
        )
        return 3
    if args.stop:
        stopped = command(cli, "stop", timeout=120)
        console.print(
            text(
                "Окружение остановлено."
                if stopped.returncode == 0
                else "Не удалось остановить окружение. Проверьте Docker.",
                "Environment stopped."
                if stopped.returncode == 0
                else "Could not stop the environment. Check Docker.",
                language,
            )
        )
        return 0 if stopped.returncode == 0 else 3
    console.print(
        Panel(
            text(
                "RLS Doctor — демонстрация\nСравним ожидаемый доступ с фактическим "
                "на локальных тестовых данных.\nЭто проверка инструмента, а не "
                "вашего приложения.",
                "RLS Doctor — guided demo\nCompare expected access with observed "
                "behavior using local synthetic data.\nThis checks the tool, not "
                "your application.",
                language,
            )
        )
    )
    if not args.check:
        console.print(
            text(
                "Подготовка создаст временных пользователей и обновит тестовые "
                "строки.\nЗакройте другие ручные сессии этой среды. Данные Docker "
                "останутся до остановки.",
                "Setup creates temporary users and updates fixture rows.\nClose "
                "other manual sessions for this stack. Docker data remains until "
                "stopped.",
                language,
            )
        )
        answer = (
            console.input(text("Подготовить демо? [д/н]: ", "Prepare demo? [y/n]: ", language))
            .strip()
            .lower()
        )
        if answer not in {"д", "да", "y", "yes"}:
            return 0
    os.environ["RLS_DOCTOR_ALLOW_FIXTURE_SETUP"] = "1"
    with console.status(
        text(
            "Запускаю окружение. Первая загрузка может занять несколько минут…",
            "Starting environment. First download may take several minutes…",
            language,
        )
    ):
        started = command(cli, "start")
    if started.returncode != 0:
        console.print(
            text(
                "Среда не запустилась. Проверьте Docker, интернет и порты "
                "54321/54322; повторите demo.cmd.",
                "Startup failed. Check Docker, internet and ports 54321/54322; retry demo.cmd.",
                language,
            )
        )
        return 3
    status = command(cli, "status", timeout=20)
    if status.returncode != 0:
        raise DoctorError("LOCAL_STACK_STATUS_FAILED", "Local stack unavailable.")
    config, _ = setup_fixture(json.loads(status.stdout))
    base = ROOT / ".rls-doctor"
    base.mkdir(exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="demo-", dir=base))
    write_session_files(directory, config)
    console.print(
        text(
            "Готово. Ключи подготовлены автоматически и не записаны в файлы.",
            "Ready. Credentials prepared automatically and kept out of files.",
            language,
        )
    )

    def run_case(index: int) -> bool:
        name, ru, en, wanted = CASES[index]
        console.print("\n" + text(ru, en, language))
        scenario = load_scenario(directory / f"{name}.yaml")
        report = replay(scenario, config, inspect=True)
        show_report(console, report, language)
        if wanted == "FAIL":
            console.print(
                text(
                    "В этом примере намеренно задана проблема. Ожидается обнаружение "
                    "нарушения (FAIL).",
                    "This fixture deliberately contains a problem. Detecting a "
                    "mismatch (FAIL) is expected.",
                    language,
                )
            )
        return report["result"] == wanted

    if args.check:
        matched = [run_case(i) for i in range(len(CASES))]
        console.print(
            text(
                f"Сценарии демо: {sum(matched)}/{len(matched)}. "
                "Это проверка примеров, не полный E2E.",
                f"Demo scenarios: {sum(matched)}/{len(matched)} match expected outcomes. "
                "This is not full E2E.",
                language,
            )
        )
        return 0 if all(matched) else 1
    while True:
        console.print("\n" + text("Выберите проверку:", "Choose a check:", language))
        for i, (_, ru, en, _) in enumerate(CASES, 1):
            console.print(f"{i}. {text(ru, en, language)}")
        console.print(
            text(
                "7. Все сценарии\n8. Остановить окружение и выйти\n0. Выйти, "
                "оставив окружение запущенным",
                "7. All scenarios\n8. Stop environment and exit\n0. Exit, keep environment running",
                language,
            )
        )
        choice = console.input("> ").strip()
        if choice == "0":
            console.print(
                text(
                    "Среда продолжает работать. Для остановки: demo.cmd -Stop",
                    "Environment still running. To stop: demo.cmd -Stop",
                    language,
                )
            )
            return 0
        if choice == "8":
            stopped = command(cli, "stop", timeout=120)
            console.print(
                text(
                    "Окружение остановлено."
                    if stopped.returncode == 0
                    else "Остановка не завершена. Повторите demo.cmd -Stop.",
                    "Environment stopped."
                    if stopped.returncode == 0
                    else "Stop failed. Retry demo.cmd -Stop.",
                    language,
                )
            )
            return 0 if stopped.returncode == 0 else 3
        if choice == "7":
            matched = [run_case(i) for i in range(len(CASES))]
            console.print(
                text(
                    f"Ожидаемые результаты: {sum(matched)}/{len(matched)}.",
                    f"Expected outcomes: {sum(matched)}/{len(matched)}.",
                    language,
                )
            )
        elif choice in {str(i) for i in range(1, 7)}:
            run_case(int(choice) - 1)
        else:
            console.print(text("Введите число от 0 до 8.", "Enter a number from 0 to 8.", language))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyboardInterrupt, EOFError):
        print("\nDemo closed / Демо закрыто. Stop / Остановить: demo.cmd -Stop")
    except DoctorError as error:
        print(f"Check could not finish / Проверка не завершена: {error.code}")
        print("Restart demo / Перезапустите: demo.cmd. Check Docker / Проверьте Docker.")
        raise SystemExit(3) from None
    except Exception:
        print("Demo could not finish / Демо не завершено. Check Docker and retry demo.cmd.")
        print("Raw details suppressed / Технические данные скрыты: они могут содержать ключи.")
        raise SystemExit(3) from None
