"""Guided reports preserve observed evidence and hide credentials/row values."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture()
def demo(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("demo_test", ROOT / "scripts/demo.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("language", ["ru", "en"])
def test_summary_uses_observations_without_private_values(demo: ModuleType, language: str) -> None:
    report = {
        "result": "FAIL",
        "http": {"status": 200, "row_count": 2},
        "identity": {"confirmed_role": "authenticated", "token": "PRIVATE_TOKEN"},
        "checks": [
            {"check": "http_status", "expected": 200, "observed": 200, "result": "PASS"},
            {"check": "row_count", "expected": 1, "observed": 2, "result": "FAIL"},
            {"check": "excludes_1", "expected": "PRIVATE_ROW", "result": "FAIL"},
        ],
        "unexpected": "PRIVATE_PASSWORD",
    }
    output = str(demo.summary(report, language))
    assert "FAIL" in output and "HTTP 200" in output
    assert "2" in output
    assert "PRIVATE" not in output
    assert ("получена" if language == "ru" else "returned") in output


@pytest.mark.parametrize("language", ["ru", "en"])
def test_empty_result_never_claims_rls_cause(demo: ModuleType, language: str) -> None:
    output = str(
        demo.summary(
            {
                "result": "PASS",
                "http": {"status": 200, "row_count": 0},
                "checks": [{"check": "row_count", "expected": 0, "result": "PASS"}],
            },
            language,
        )
    )
    assert ("Не установлено" if language == "ru" else "Unverified") in output
    assert ("не доказывает" if language == "ru" else "does not prove") in output


def test_incomplete_report_cannot_be_presented_as_completed(demo: ModuleType) -> None:
    output = str(demo.summary({"result": "UNKNOWN", "http": None}, "en"))
    assert "Check incomplete" in output
    assert "No API response" in output


def test_local_admin_dsn_is_fixture_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    from e2e import fixture_integration_dsn

    from rls_doctor.core.errors import DoctorError

    monkeypatch.delenv("RLS_DOCTOR_ALLOW_FIXTURE_SETUP", raising=False)
    local = "postgresql://postgres:synthetic@127.0.0.1:54322/postgres"
    with pytest.raises(DoctorError):
        fixture_integration_dsn(local)
    monkeypatch.setenv("RLS_DOCTOR_ALLOW_FIXTURE_SETUP", "1")
    from psycopg.conninfo import conninfo_to_dict

    params = conninfo_to_dict(fixture_integration_dsn(local))
    assert params["user"] == "supabase_admin"
    assert params["hostaddr"] == "127.0.0.1"
    with pytest.raises(DoctorError):
        fixture_integration_dsn("postgresql://postgres:synthetic@example.com:54322/postgres")
