"""Negative demonstrations and skipped integration tests cannot become E2E passes."""

import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from rls_doctor.core.errors import DoctorError

SPEC = importlib.util.spec_from_file_location(
    "rls_doctor_e2e", Path(__file__).resolve().parents[3] / "scripts" / "e2e.py"
)
assert SPEC is not None and SPEC.loader is not None
e2e = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(e2e)


def leak_report(status: int = 200, count: int | None = 2) -> dict[str, Any]:
    return {
        "result": "FAIL",
        "http": {"status": status, "row_count": count},
        "checks": [
            {"check": "http_status", "result": "PASS"},
            {"check": "row_count", "result": "FAIL"},
            {"check": "contains_1", "result": "PASS"},
            {"check": "excludes_1", "result": "FAIL"},
            {"check": "executed_role", "result": "PASS"},
        ],
    }


LEAK_CHECKS = {
    "http_status": "PASS",
    "row_count": "FAIL",
    "contains_1": "PASS",
    "excludes_1": "FAIL",
    "executed_role": "PASS",
}


@pytest.mark.parametrize("status", [403, 404, 500])
def test_unrelated_http_failure_is_not_evidence_of_tenant_leak(status: int) -> None:
    with pytest.raises(DoctorError, match="Disposable fixture verification failed"):
        e2e.require_case_evidence(
            leak_report(status, None), "tenant_leak", "FAIL", 200, 2, LEAK_CHECKS
        )


def test_expected_failure_requires_observed_foreign_row_and_confirmed_role() -> None:
    e2e.require_case_evidence(leak_report(), "tenant_leak", "FAIL", 200, 2, LEAK_CHECKS)
    report = leak_report(count=0)
    with pytest.raises(DoctorError):
        e2e.require_case_evidence(report, "tenant_leak", "FAIL", 200, 2, LEAK_CHECKS)
    report = leak_report()
    report["checks"][-1]["result"] = "UNKNOWN"
    with pytest.raises(DoctorError):
        e2e.require_case_evidence(report, "tenant_leak", "FAIL", 200, 2, LEAK_CHECKS)
    report = leak_report()
    report["checks"][3]["result"] = "PASS"
    with pytest.raises(DoctorError):
        e2e.require_case_evidence(report, "tenant_leak", "FAIL", 200, 2, LEAK_CHECKS)


def test_default_deny_requires_zero_rows_and_row_count_mismatch() -> None:
    checks = {"http_status": "PASS", "row_count": "FAIL", "executed_role": "PASS"}
    e2e.require_case_evidence(leak_report(count=0), "default_deny", "FAIL", 200, 0, checks)
    with pytest.raises(DoctorError):
        e2e.require_case_evidence(leak_report(count=2), "default_deny", "FAIL", 200, 0, checks)


@pytest.mark.parametrize(
    ("summary", "returncode", "accepted"),
    [
        ({"exit_code": 0, "collected": 8, "passed": 8, "skipped": 0, "failed": 0}, 0, True),
        ({"exit_code": 0, "collected": 8, "passed": 0, "skipped": 8, "failed": 0}, 0, False),
        ({"exit_code": 0, "collected": 8, "passed": 7, "skipped": 1, "failed": 0}, 0, False),
        ({"exit_code": 0, "collected": 0, "passed": 0, "skipped": 0, "failed": 0}, 0, False),
        ({"exit_code": 1, "collected": 8, "passed": 7, "skipped": 0, "failed": 1}, 0, False),
        ({"exit_code": 0, "collected": 8, "passed": 8, "skipped": 0, "failed": 0}, 1, False),
    ],
)
def test_integration_requires_executed_tests_without_skips(
    monkeypatch: pytest.MonkeyPatch,
    summary: dict[str, int],
    returncode: int,
    accepted: bool,
) -> None:
    def result(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], returncode, json.dumps(summary), "")

    monkeypatch.setattr(e2e.subprocess, "run", result)
    if accepted:
        assert e2e.run_integration_suite("synthetic-local-dsn") == summary
    else:
        with pytest.raises(DoctorError):
            e2e.run_integration_suite("synthetic-local-dsn")


@pytest.mark.parametrize("skipped", [False, True])
def test_integration_child_emits_only_execution_counts(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], skipped: bool
) -> None:
    def run(*args: Any, **kwargs: Any) -> int:
        evidence = kwargs["plugins"][0]
        evidence.pytest_collection_finish(SimpleNamespace(items=[object()]))
        evidence.pytest_runtest_logreport(
            SimpleNamespace(
                when="setup" if skipped else "call",
                passed=not skipped,
                skipped=skipped,
                failed=False,
            )
        )
        print("synthetic-pytest-detail-that-must-not-escape")
        return 0

    monkeypatch.setattr(pytest, "main", run)
    e2e.integration_child()
    captured = capsys.readouterr()
    assert "synthetic-pytest-detail" not in captured.out + captured.err
    assert json.loads(captured.out) == {
        "exit_code": 0,
        "collected": 1,
        "passed": int(not skipped),
        "skipped": int(skipped),
        "failed": 0,
    }


def test_fixture_setup_requires_explicit_consent_before_accessing_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RLS_DOCTOR_ALLOW_FIXTURE_SETUP", raising=False)
    with pytest.raises(DoctorError) as error:
        e2e.setup_fixture({})
    assert error.value.code == "SETUP_CONSENT_REQUIRED"
