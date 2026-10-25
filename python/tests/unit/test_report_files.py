"""Direct report saving keeps outcome codes, machine stdout and existing files."""

import json
import os
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from rls_doctor.cli.main import app, finish
from rls_doctor.core.errors import DoctorError
from rls_doctor.reports import files


@pytest.mark.parametrize("result,code", [("PASS", 0), ("FAIL", 1), ("UNKNOWN", 2), ("ERROR", 3)])
def test_saved_report_preserves_exit_and_machine_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], result: str, code: int
) -> None:
    path = tmp_path / "new" / "report.json"
    report = {"result": result, "summary": "Проверка UTF-8"}
    with pytest.raises(typer.Exit) as caught:
        finish(report, "json", "ru", path)
    assert caught.value.exit_code == code
    assert json.loads(capsys.readouterr().out) == report
    assert json.loads(path.read_bytes().decode("utf-8")) == report
    assert not list(path.parent.glob("*.tmp"))
    if os.name != "nt":
        assert path.stat().st_mode & 0o077 == 0


def test_existing_file_is_never_overwritten(tmp_path: Path) -> None:
    path = tmp_path / "report.json"
    path.write_text("existing contents", encoding="utf-8")
    with pytest.raises(DoctorError) as caught:
        files.write_report({"result": "PASS"}, path)
    assert caught.value.code == "REPORT_EXISTS"
    assert path.read_text(encoding="utf-8") == "existing contents"


def test_racing_destination_is_preserved_and_temporary_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "report.json"
    link = os.link

    def race(source: Path, target: Path) -> None:
        target.write_text("other writer", encoding="utf-8")
        link(source, target)

    monkeypatch.setattr(files.os, "link", race)
    with pytest.raises(DoctorError) as caught:
        files.write_report({"result": "PASS"}, path)
    assert caught.value.code == "REPORT_EXISTS"
    assert path.read_text(encoding="utf-8") == "other writer"
    assert [p.name for p in tmp_path.iterdir()] == ["report.json"]


def test_failed_publish_has_no_partial_file_or_raw_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def reject(*args: object) -> None:
        raise OSError("PRIVATE_PASSWORD")

    monkeypatch.setattr(files.os, "link", reject)
    with pytest.raises(DoctorError) as caught:
        files.write_report({"result": "PASS"}, tmp_path / "report.json")
    assert caught.value.code == "REPORT_WRITE_FAILED"
    assert "PRIVATE_PASSWORD" not in str(caught.value)
    assert not list(tmp_path.iterdir())


def test_size_limit_creates_no_file(tmp_path: Path) -> None:
    with pytest.raises(DoctorError) as caught:
        files.write_report({"value": "x" * 1048576}, tmp_path / "report.json")
    assert caught.value.code == "REPORT_LIMIT"
    assert not list(tmp_path.iterdir())


def test_cli_error_is_saved_without_exposing_invalid_input(tmp_path: Path) -> None:
    event = tmp_path / "bad-event.json"
    event.write_text('{"jwt":"PRIVATE_JWT"}', encoding="utf-8")
    output = tmp_path / "result.json"
    result = CliRunner().invoke(
        app, ["validate", str(event), "--output", str(output), "--format", "json"]
    )
    assert result.exit_code == 3
    assert json.loads(output.read_text(encoding="utf-8")) == json.loads(result.stdout)
    assert "PRIVATE_JWT" not in result.stdout + output.read_text(encoding="utf-8")


def test_existing_output_rejected_before_database_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rls_doctor.cli.main as cli

    path = tmp_path / "report.json"
    path.write_text("preserve", encoding="utf-8")
    monkeypatch.setattr(cli, "load_config", lambda *args: pytest.fail("No config/network read"))
    result = CliRunner().invoke(app, ["doctor", "--output", str(path), "--format", "json"])
    assert result.exit_code == 3
    assert json.loads(result.stdout)["error"]["code"] == "REPORT_EXISTS"
    assert path.read_text(encoding="utf-8") == "preserve"
