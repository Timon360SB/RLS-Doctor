"""Detailed setup creates executable typed isolation scenarios without leaking values."""

from pathlib import Path

import httpx
import psycopg
import pytest
from typer.testing import CliRunner

from rls_doctor.cli.main import app
from rls_doctor.cli.scenario_wizard import scalar, selected_columns
from rls_doctor.cli.wizard import initialize
from rls_doctor.core.config import load_config
from rls_doctor.core.errors import DoctorError
from rls_doctor.replay.scenarios import load_scenario


def run_wizard(path: Path, extra: list[str], language: str = "en", *, count: str = "1"):
    values = ["", "", "", "", "", count, *extra, "n", "n", "y"]
    return CliRunner().invoke(
        app,
        ["init", "--interactive", "--advanced", "--directory", str(path), "--language", language],
        input="\n".join(values) + "\n",
    )


@pytest.mark.parametrize("language", ["en", "ru"])
def test_detailed_isolation_is_offline_private_and_typed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, language: str
) -> None:
    def forbidden(*args, **kwargs):
        pytest.fail("Detailed setup must not connect")

    monkeypatch.setattr(httpx, "Client", forbidden)
    monkeypatch.setattr(psycopg, "connect", forbidden)
    result = run_wizard(
        tmp_path,
        [
            "id,state",
            "y",
            "state",
            "eq",
            "text",
            "SYNTHETIC_FILTER_VALUE",
            "n",
            "y",
            "id",
            "text",
            "SYNTHETIC_OWN_RECORD",
            "n",
            "y",
            "id",
            "text",
            "SYNTHETIC_OTHER_RECORD",
            "n",
            "none",
        ],
        language,
    )
    assert result.exit_code == 0, result.stdout
    scenario = load_scenario(tmp_path / "documents.yaml")
    assert scenario.request.columns == ["id", "state"]
    assert scenario.filters["state"].eq == "SYNTHETIC_FILTER_VALUE"
    assert scenario.expect.contains[0].value == "SYNTHETIC_OWN_RECORD"
    assert scenario.expect.excludes[0].value == "SYNTHETIC_OTHER_RECORD"
    assert scenario.expect.error_class == "none"
    assert "SYNTHETIC_" not in result.stdout
    assert load_config(tmp_path / "rls-doctor.toml").environment.approved_local is False
    assert load_config(tmp_path / "rls-doctor.toml").environment.confirm_identity is False


def test_reserved_and_duplicate_filters_retry_without_losing_answers(tmp_path: Path) -> None:
    result = run_wizard(
        tmp_path,
        [
            "id",
            "y",
            "select",
            "state",
            "eq",
            "text",
            "todo",
            "y",
            "state",
            "archived",
            "is",
            "false",
            "n",
            "n",
            "n",
            "skip",
        ],
    )
    assert result.exit_code == 0, result.stdout
    scenario = load_scenario(tmp_path / "documents.yaml")
    assert scenario.filters["state"].eq == "todo"
    assert scenario.filters["archived"].is_ == "false"
    assert len(scenario.filters) == 2


def test_duplicate_or_contradictory_record_is_reentered(tmp_path: Path) -> None:
    result = run_wizard(
        tmp_path,
        [
            "state",
            "n",
            "y",
            "id",
            "integer",
            "1",
            "n",
            "y",
            "id",
            "integer",
            "1",
            "integer",
            "2",
            "n",
            "skip",
        ],
    )
    assert result.exit_code == 0, result.stdout
    scenario = load_scenario(tmp_path / "documents.yaml")
    assert scenario.request.columns == ["state", "id"]
    assert scenario.expect.contains[0].value == 1
    assert scenario.expect.excludes[0].value == 2
    assert type(scenario.expect.contains[0].value) is int


def test_token_like_value_is_rejected_without_echo_or_storage(tmp_path: Path) -> None:
    private = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJwcml2YXRlIn0.c2lnbmF0dXJlX3ByaXZhdGU"
    result = run_wizard(
        tmp_path,
        [
            "id",
            "n",
            "y",
            "id",
            "text",
            private,
            "SYNTHETIC_RECORD",
            "n",
            "n",
            "skip",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert private not in result.stdout
    assert private not in (tmp_path / "documents.yaml").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "value,kind,expected",
    [("001", "text", "001"), ("12", "integer", 12), ("false", "boolean", False)],
)
def test_scalar_types_remain_distinct(value: str, kind: str, expected: object) -> None:
    parsed = scalar(value, kind)
    assert parsed == expected and type(parsed) is type(expected)


@pytest.mark.parametrize(
    "value", ["id,id", "id,invalid-name", "", ",", ",".join("c" + str(n) for n in range(65))]
)
def test_invalid_projection_is_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        selected_columns(value)


def test_wildcard_projection() -> None:
    assert selected_columns("*") is None


def test_advanced_requires_interactive_and_does_not_create_files(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["init", "--advanced", "--directory", str(tmp_path)])
    assert result.exit_code == 3 and "INIT_MODE" in result.stdout
    assert not list(tmp_path.iterdir())


def test_cancel_detailed_setup_creates_no_files(tmp_path: Path) -> None:
    path = tmp_path / "cancelled"
    result = CliRunner().invoke(
        app, ["init", "--interactive", "--advanced", "--directory", str(path)], input="\n" * 6
    )
    assert result.exit_code == 0 and not path.exists()


def test_oversized_scenario_does_not_create_partial_config(tmp_path: Path) -> None:
    path = tmp_path / "oversized"
    with pytest.raises(DoctorError) as caught:
        initialize(path, ("version=1", "x" * 65537))
    assert caught.value.code == "INIT_LIMIT"
    assert not path.exists()


@pytest.mark.parametrize("probe", ["y", "n"])
def test_existing_probe_requires_explicit_opt_in(tmp_path: Path, probe: str) -> None:
    inputs = ["", "", "", "", "", "1", "id", "n", "n", "n", "skip", probe, "n", "y"]
    result = CliRunner().invoke(
        app,
        ["init", "--interactive", "--advanced", "--directory", str(tmp_path)],
        input="\n".join(inputs) + "\n",
    )
    assert result.exit_code == 0, result.stdout
    config = load_config(tmp_path / "rls-doctor.toml")
    assert config.environment.confirm_identity is (probe == "y")
    assert config.environment.approved_local is False
