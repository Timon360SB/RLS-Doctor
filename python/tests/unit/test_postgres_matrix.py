"""Compatibility checks may only clean up their own labelled containers."""

import importlib.util
import os
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from rls_doctor.core.errors import DoctorError


@pytest.fixture()
def matrix(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    root = Path(__file__).resolve().parents[3]
    monkeypatch.syspath_prepend(str(root / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "postgres_matrix_test", root / "scripts/postgres_matrix.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def setup_fake(
    matrix: ModuleType, monkeypatch: pytest.MonkeyPatch, *, owned: bool = True
) -> list[list[str]]:
    calls: list[list[str]] = []
    identity = ""

    class Socket:
        def __enter__(self) -> "Socket":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def connect_ex(self, address: object) -> int:
            return 1

    monkeypatch.setattr(matrix.socket, "socket", Socket)

    class Connection:
        def __enter__(self) -> "Connection":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def execute(self, query: str) -> Any:
            return SimpleNamespace(fetchone=lambda: (160001,))

    monkeypatch.setattr(matrix.psycopg, "connect", lambda *a, **k: Connection())
    monkeypatch.setattr(
        matrix,
        "run_integration_suite",
        lambda dsn: {
            "passed": 8,
            "collected": 8,
            "skipped": 0,
            "failed": 0,
            "exit_code": 0,
        },
    )

    def command(exe: str, args: list[str], **kwargs: object) -> Any:
        nonlocal identity
        calls.append(args)
        if args[0] == "run":
            identity = args[args.index("--label") + 1].split("=", 1)[1]
            assert os.environ["POSTGRES_PASSWORD"] not in " ".join(args)
            return SimpleNamespace(returncode=0, stdout="a" * 64)
        if args[0] == "inspect":
            return SimpleNamespace(returncode=0, stdout=identity if owned else "unrelated-run")
        if args[:2] == ["image", "inspect"]:
            return SimpleNamespace(returncode=0, stdout='["postgres@sha256:synthetic"]')
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(matrix, "command", command)
    return calls


def test_only_owned_temporary_container_is_removed(
    matrix: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = setup_fake(matrix, monkeypatch)
    monkeypatch.setenv("POSTGRES_PASSWORD", "PRIVATE_ORIGINAL")
    result = matrix.check_version("docker", "16")
    assert result["evidence"]["passed"] == 8
    assert result["server_version_num"] == 160001
    removals = [args for args in calls if args[0] == "rm"]
    assert len(removals) == 1 and removals[0][-1].startswith("rls-doctor-pg16-")
    assert os.environ["POSTGRES_PASSWORD"] == "PRIVATE_ORIGINAL"


def test_foreign_container_is_never_removed(
    matrix: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = setup_fake(matrix, monkeypatch, owned=False)
    with pytest.raises(DoctorError) as caught:
        matrix.check_version("docker", "16")
    assert caught.value.code == "POSTGRES_MATRIX_OWNERSHIP"
    assert not any(args[0] == "rm" for args in calls)


def test_owned_container_is_cleaned_after_test_failure(
    matrix: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = setup_fake(matrix, monkeypatch)

    def failed(dsn: str) -> None:
        raise DoctorError("POSTGRES_INTEGRATION_FAILED", "Synthetic test failure.")

    monkeypatch.setattr(matrix, "run_integration_suite", failed)
    with pytest.raises(DoctorError):
        matrix.check_version("docker", "16")
    assert any(args[0] == "rm" for args in calls)
