"""Prepare a disposable Windows demo shell; credentials never enter parent shell/files."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from e2e import OTHER, OWN, ROOT, require, setup_fixture
from rls_doctor.core.config import ProjectConfig
from rls_doctor.core.errors import DoctorError
from rls_doctor.replay.scenarios import Scenario


def write_session_files(directory: Path, config: ProjectConfig) -> None:
    """Write only config references and synthetic expectations, never credentials."""
    lines = ["version = 1", "[environment]"]
    for name, value in config.environment.model_dump().items():
        lines.append(f"{name} = {json.dumps(value)}")
    with (directory / "rls-doctor.toml").open("x", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")

    for name, resource, identity, expectation, filters in [
        (
            "own-row",
            "documents",
            {"type": "authenticated", "token_env": "RLS_DOCTOR_TEST_TOKEN"},
            {
                "status": 200,
                "row_count": 1,
                "contains": [{"column": "id", "value": OWN}],
                "excludes": [{"column": "id", "value": OTHER}],
            },
            {},
        ),
        (
            "missing-auth",
            "documents",
            {"type": "anon", "expected_role": "authenticated"},
            {"status": 200, "row_count": 1},
            {},
        ),
        (
            "default-deny",
            "blocked_documents",
            {"type": "authenticated", "token_env": "RLS_DOCTOR_TEST_TOKEN"},
            {"status": 200, "row_count": 1},
            {},
        ),
        (
            "missing-grant",
            "no_grant_documents",
            {"type": "authenticated", "token_env": "RLS_DOCTOR_TEST_TOKEN"},
            {"status": 403, "error_class": "permission"},
            {},
        ),
        (
            "tenant-isolation",
            "leaky_documents",
            {"type": "authenticated", "token_env": "RLS_DOCTOR_TEST_TOKEN"},
            {
                "status": 200,
                "row_count": 1,
                "excludes": [{"column": "id", "value": OTHER}],
            },
            {},
        ),
        (
            "nonexistent-row",
            "documents",
            {"type": "authenticated", "token_env": "RLS_DOCTOR_TEST_TOKEN"},
            {"status": 200, "row_count": 0},
            {"id": {"eq": str(uuid4())}},
        ),
    ]:
        data: dict[str, Any] = {
            "version": 1,
            "name": name.replace("-", "_"),
            "request": {"resource": resource},
            "identity": identity,
            "expect": expectation,
            "filters": filters,
        }
        Scenario.model_validate(data)
        with (directory / f"{name}.yaml").open("x", encoding="utf-8") as handle:
            yaml.safe_dump(data, handle, sort_keys=False)


def read_local_status() -> dict[str, Any]:
    executable = shutil.which("supabase")
    require(executable is not None, "SUPABASE_CLI_MISSING")
    process = subprocess.run(
        [executable, "status", "--workdir", "fixtures", "--output", "json"],
        cwd=ROOT,
        capture_output=True,
        timeout=20,
        check=False,
    )
    require(process.returncode == 0, "LOCAL_STACK_STATUS_FAILED")
    require(len(process.stdout) <= 65536, "STATUS_LIMIT")
    status = json.loads(process.stdout)
    require(isinstance(status, dict), "INVALID_LOCAL_STATUS")
    return status


def main() -> int:
    require(not sys.argv[1:], "NO_ARGUMENTS_EXPECTED")
    require(sys.stdin.isatty(), "INTERACTIVE_TERMINAL_REQUIRED")
    require(os.environ.get("RLS_DOCTOR_ALLOW_FIXTURE_SETUP") == "1", "SETUP_CONSENT_REQUIRED")
    shell = shutil.which("pwsh") or shutil.which("powershell")
    require(shell is not None, "POWERSHELL_MISSING")
    config, _ = setup_fixture(read_local_status())
    base = ROOT / ".rls-doctor"
    base.mkdir(exist_ok=True)
    session = Path(tempfile.mkdtemp(prefix="manual-session-", dir=base))
    write_session_files(session, config)
    print("Disposable local fixture session ready. Credentials exist only in this child shell.")
    print("Working directory: repository root. Synthetic scenario files: " + str(session))
    print(
        "In PowerShell, set: $rlsConfig = Join-Path "
        "$env:RLS_DOCTOR_MANUAL_SESSION 'rls-doctor.toml'"
    )
    print("Then: uv run --project python rls-doctor doctor --config $rlsConfig")
    print(
        "Use 'exit' to close the session. Do not print environment variables or start a transcript."
    )
    print("Do not rerun fixture setup in another terminal while using this session.")
    sys.stdout.flush()
    child = subprocess.run(
        [shell, "-NoLogo", "-NoProfile"],
        cwd=ROOT,
        env={**os.environ, "RLS_DOCTOR_MANUAL_SESSION": str(session)},
        check=False,
    )
    print("Session closed. Synthetic files remain; the parent shell has no new credentials.")
    return child.returncode


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DoctorError as error:
        print("ERROR " + error.code, file=sys.stderr)
        sys.exit(3)
    except (Exception, KeyboardInterrupt):
        print("ERROR manual session failed; unsafe details suppressed.", file=sys.stderr)
        sys.exit(3)
