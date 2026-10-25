"""Sample checks preserve isolation, modified setup and actual replay evidence."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from rls_doctor.core.errors import DoctorError
from rls_doctor.replay.scenarios import Scenario


@pytest.fixture()
def sample(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    root = Path(__file__).resolve().parents[3]
    monkeypatch.syspath_prepend(str(root / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "task_board_test", root / "scripts/task_board_check.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_setup_is_separate_and_preserves_operator_edits(
    sample: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sample, "WORKDIR", tmp_path)
    sample.prepare()
    config = (tmp_path / "supabase/config.toml").read_text(encoding="utf-8")
    assert 'project_id = "rls-doctor-task-board"' in config
    assert "56321" in config and "56322" in config
    assert "55321" not in config and "54321" not in config
    target = tmp_path / "supabase/seed.sql"
    target.write_text("-- operator change", encoding="utf-8")
    with pytest.raises(DoctorError) as caught:
        sample.prepare()
    assert caught.value.code == "SAMPLE_FILES_CHANGED"
    assert target.read_text(encoding="utf-8") == "-- operator change"


def test_scenario_asserts_membership_not_only_count(sample: ModuleType) -> None:
    scenario = Scenario.model_validate(
        sample.scenario("authenticated", sample.IDS[:2], sample.IDS[2:])
    )
    assert scenario.request.schema_name == "task_board"
    assert scenario.expect.row_count == 2
    assert len(scenario.expect.contains) == 2
    assert len(scenario.expect.excludes) == 1


@pytest.mark.parametrize(
    "change", ["result", "count", "role", "http", "inspector", "resource", "schema", "rls"]
)
def test_report_must_show_intended_actual_evidence(sample: ModuleType, change: str) -> None:
    report = {
        "result": "PASS",
        "resource": "task_board.tasks",
        "http": {"status": 200, "row_count": 2},
        "identity": {"confirmed_role": "authenticated"},
        "inspector": {"table": {"schema": "task_board", "name": "tasks", "rls_enabled": True}},
    }
    sample.check_report(report, 2, "authenticated")
    if change == "result":
        report["result"] = "UNKNOWN"
    elif change == "count":
        report["http"]["row_count"] = 3
    elif change == "http":
        report["http"]["status"] = 403
    elif change == "role":
        report["identity"]["confirmed_role"] = "anon"
    elif change == "resource":
        report["resource"] = "public.tasks"
    elif change == "schema":
        report["inspector"]["table"]["schema"] = "public"
    elif change == "rls":
        report["inspector"]["table"]["rls_enabled"] = False
    else:
        report["inspector"] = None
    with pytest.raises(DoctorError):
        sample.check_report(report, 2, "authenticated")


@pytest.mark.parametrize("value", ["PRIVATE_PASSWORD", "PRIVATE_JWT", "SYNTHETIC_TASK_ALICE_TITLE"])
def test_private_outputs_are_blocked(sample: ModuleType, value: str) -> None:
    with pytest.raises(DoctorError) as caught:
        sample.safe(value, ["PRIVATE_PASSWORD", "PRIVATE_JWT"])
    assert value not in str(caught.value)
