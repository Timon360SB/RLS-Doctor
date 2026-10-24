import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from rls_doctor.core.config import LocalEnvironment, ProjectConfig, load_config
from rls_doctor.core.errors import DoctorError
from rls_doctor.replay.scenarios import load_scenario

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture()
def manual(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "manual_session_test", ROOT / "scripts/manual_session.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generated_files_load_and_contain_no_credentials(
    manual: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secrets = {
        "RLS_DOCTOR_LOCAL_ANON_KEY": "PRIVATE_API_KEY_SHOULD_NOT_BE_WRITTEN",
        "RLS_DOCTOR_LOCAL_JWT_SECRET": "PRIVATE_SIGNING_SECRET_SHOULD_NOT_BE_WRITTEN",
        "RLS_DOCTOR_TEST_TOKEN": "PRIVATE_ACCESS_TOKEN_SHOULD_NOT_BE_WRITTEN",
        "RLS_DOCTOR_DATABASE_URL": "PRIVATE_DATABASE_PASSWORD_SHOULD_NOT_BE_WRITTEN",
    }
    for name, value in secrets.items():
        monkeypatch.setenv(name, value)
    config = ProjectConfig(
        environment=LocalEnvironment(
            approved_local=True,
            resources=[
                "documents",
                "blocked_documents",
                "no_grant_documents",
                "leaky_documents",
            ],
        )
    )
    manual.write_session_files(tmp_path, config)
    assert load_config(tmp_path / "rls-doctor.toml") == config
    scenarios = {p.stem: load_scenario(p) for p in tmp_path.glob("*.yaml")}
    assert set(scenarios) == {
        "own-row",
        "missing-auth",
        "default-deny",
        "missing-grant",
        "tenant-isolation",
        "nonexistent-row",
    }
    assert scenarios["own-row"].expect.contains[0].value == manual.OWN
    assert scenarios["tenant-isolation"].expect.excludes[0].value == manual.OTHER
    assert scenarios["missing-grant"].expect.status == 403
    assert scenarios["missing-auth"].identity.expected_role == "authenticated"
    assert scenarios["nonexistent-row"].expect.row_count == 0
    for file in tmp_path.iterdir():
        content = file.read_text(encoding="utf-8")
        assert all(secret not in content for secret in secrets.values())


def test_existing_session_files_are_never_overwritten(manual: ModuleType, tmp_path: Path) -> None:
    path = tmp_path / "rls-doctor.toml"
    path.write_text("preserve-existing-content", encoding="utf-8")
    with pytest.raises(FileExistsError):
        manual.write_session_files(tmp_path, ProjectConfig())
    assert path.read_text(encoding="utf-8") == "preserve-existing-content"


@pytest.mark.parametrize("success", [False, True])
def test_local_status_keeps_sensitive_output_in_memory(
    manual: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    success: bool,
) -> None:
    monkeypatch.setattr(manual.shutil, "which", lambda _: "supabase.exe")
    status = {"API_URL": "http://127.0.0.1:54321", "JWT_SECRET": "PRIVATE_STATUS_SECRET"}

    def run(args: list[str], **kwargs: object) -> SimpleNamespace:
        assert args[1:] == ["status", "--workdir", "fixtures", "--output", "json"]
        assert kwargs["capture_output"] is True
        return SimpleNamespace(
            returncode=0 if success else 1,
            stdout=json.dumps(status).encode(),
            stderr=b"PRIVATE_SUBPROCESS_ERROR",
        )

    monkeypatch.setattr(manual.subprocess, "run", run)
    if success:
        assert manual.read_local_status() == status
    else:
        with pytest.raises(DoctorError) as error:
            manual.read_local_status()
        assert error.value.code == "LOCAL_STACK_STATUS_FAILED"
        assert "PRIVATE" not in str(error.value)
    captured = capsys.readouterr()
    assert "PRIVATE" not in captured.out + captured.err


def test_session_requires_consent_before_fixture_or_shell(
    manual: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["manual_session.py"])
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.delenv("RLS_DOCTOR_ALLOW_FIXTURE_SETUP", raising=False)
    monkeypatch.setattr(manual, "setup_fixture", lambda _: pytest.fail("No setup without consent"))
    with pytest.raises(DoctorError) as error:
        manual.main()
    assert error.value.code == "SETUP_CONSENT_REQUIRED"


def test_child_shell_receives_session_but_parent_environment_does_not(
    manual: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "argv", ["manual_session.py"])
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setenv("RLS_DOCTOR_ALLOW_FIXTURE_SETUP", "1")
    monkeypatch.delenv("RLS_DOCTOR_MANUAL_SESSION", raising=False)
    monkeypatch.setattr(manual, "ROOT", tmp_path)
    monkeypatch.setattr(manual.shutil, "which", lambda _: "pwsh.exe")
    monkeypatch.setattr(manual, "read_local_status", lambda: {})
    monkeypatch.setattr(
        manual,
        "setup_fixture",
        lambda _: (ProjectConfig(environment=LocalEnvironment(approved_local=True)), []),
    )

    def run(args: list[str], **kwargs: object) -> SimpleNamespace:
        assert args == ["pwsh.exe", "-NoLogo", "-NoProfile"]
        assert kwargs["cwd"] == tmp_path
        env = kwargs["env"]
        assert isinstance(env, dict)
        session = Path(env["RLS_DOCTOR_MANUAL_SESSION"])
        assert (session / "own-row.yaml").is_file()
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(manual.subprocess, "run", run)
    assert manual.main() == 0
    assert "RLS_DOCTOR_MANUAL_SESSION" not in manual.os.environ
