"""Practice setup is isolated and failing examples need their intended evidence."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from rls_doctor.core.errors import DoctorError


@pytest.fixture()
def lab(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    root = Path(__file__).resolve().parents[3]
    monkeypatch.syspath_prepend(str(root / "scripts"))
    spec = importlib.util.spec_from_file_location("practice_test", root / "scripts/lab.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_practice_files_use_separate_ports_and_preserve_changes(
    lab: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(lab, "LAB", tmp_path)
    lab.prepare_files()
    config = (tmp_path / "supabase/config.toml").read_text(encoding="utf-8")
    assert 'project_id = "rls-doctor-practice"' in config
    assert "55321" in config and "55322" in config
    assert "54321" not in config and "54322" not in config
    path = tmp_path / "supabase/seed.sql"
    path.write_text("-- operator changes", encoding="utf-8")
    with pytest.raises(DoctorError, match="no files or database were reset"):
        lab.prepare_files()
    assert path.read_text(encoding="utf-8") == "-- operator changes"


@pytest.mark.parametrize(
    "http", [{"status": 403, "row_count": None}, {"status": 200, "row_count": 0}]
)
def test_any_failure_is_not_accepted_as_a_leak(lab: ModuleType, http: dict[str, object]) -> None:
    assert not lab.expected_evidence("tenant-isolation", 1, {"http": http, "checks": []})


def test_actual_leak_requires_count_and_exclusion_evidence(lab: ModuleType) -> None:
    report = {
        "http": {"status": 200, "row_count": 2},
        "checks": [
            {"check": "row_count", "result": "FAIL"},
            {"check": "excludes_1", "result": "FAIL"},
            {"check": "executed_role", "result": "PASS"},
        ],
    }
    assert lab.expected_evidence("tenant-isolation", 1, report)
    report["checks"][1]["result"] = "PASS"
    assert not lab.expected_evidence("tenant-isolation", 1, report)


def test_privilege_inspection_requires_missing_select_finding(lab: ModuleType) -> None:
    assert not lab.expected_evidence("inspect", 2, {"conclusions": []})
    assert lab.expected_evidence(
        "inspect", 2, {"conclusions": [{"code": "SELECT_PRIVILEGE_MISSING"}]}
    )


def test_private_output_is_blocked(lab: ModuleType, tmp_path: Path) -> None:
    practice = lab.Practice(None, [], ["PRIVATE_TOKEN"], tmp_path)
    with pytest.raises(DoctorError) as caught:
        practice.safe("unexpected PRIVATE_TOKEN")
    assert "PRIVATE_TOKEN" not in str(caught.value)


def test_lab_lock_excludes_second_session_and_releases_after_error(
    lab: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(lab, "LAB", tmp_path)
    with pytest.raises(RuntimeError, match="deliberate interruption"):
        with lab.practice_lock():
            with pytest.raises(DoctorError) as caught:
                with lab.practice_lock():
                    pytest.fail("Second practice session acquired the same lock")
            assert caught.value.code == "LAB_SESSION_BUSY"
            raise RuntimeError("deliberate interruption")
    # A remaining file is harmless: the OS lock, not file existence, gates entry.
    assert (tmp_path / ".session.lock").exists()
    with lab.practice_lock():
        pass


def test_lab_lock_is_cross_process_and_survives_abrupt_exit(
    lab: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess
    import sys

    monkeypatch.setattr(lab, "LAB", tmp_path)
    scripts = Path(lab.__file__).parent
    setup = (
        f"import sys, os; sys.path.insert(0, {str(scripts)!r}); "
        f"import lab; from pathlib import Path; lab.LAB = Path({str(tmp_path)!r})\n"
    )
    blocked = setup + (
        "try:\n"
        "    with lab.practice_lock(): sys.exit(9)\n"
        "except lab.DoctorError as error:\n"
        "    sys.exit(0 if error.code == 'LAB_SESSION_BUSY' else 8)\n"
    )
    with lab.practice_lock():
        child = subprocess.run([sys.executable, "-c", blocked], capture_output=True, timeout=15)
        assert child.returncode == 0
    crashed = setup + "with lab.practice_lock(): os._exit(0)\n"
    child = subprocess.run([sys.executable, "-c", crashed], capture_output=True, timeout=15)
    assert child.returncode == 0
    with lab.practice_lock():
        pass


def test_lock_can_scope_separate_sample_projects(lab: ModuleType, tmp_path: Path) -> None:
    with lab.practice_lock(tmp_path / "first"):
        with lab.practice_lock(tmp_path / "second"):
            with pytest.raises(DoctorError):
                with lab.practice_lock(tmp_path / "first"):
                    pytest.fail("First project is already locked")
