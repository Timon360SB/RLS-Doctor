"""Explicit disposable sample-app setup and installed-package integration check."""

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import httpx
import psycopg
import yaml
from lab import practice_lock
from package_check import check_distributions, require_command
from rls_doctor.core.config import LocalEnvironment
from rls_doctor.core.credentials import (
    create_identity,
    credential_values,
    credentials,
    find_cli,
    local_status,
)
from rls_doctor.core.errors import DoctorError
from rls_doctor.core.models import parse_event
from rls_doctor.identity.validation import verify_test_token
from rls_doctor.replay.scenarios import Scenario

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "examples/task-board"
WORKDIR = ROOT / ".rls-doctor/task-board"
IDS = [f"20000000-0000-4000-8000-{number:012d}" for number in (1, 2, 3)]


def require(ok: bool, code: str) -> None:
    if not ok:
        raise DoctorError(code, "Sample-app check failed; private details suppressed.")


def prepare() -> None:
    """Copy reviewed setup into the fixed ignored directory without overwriting edits."""
    files = [SOURCE / "supabase/config.toml", SOURCE / "supabase/seed.sql"]
    files += sorted((SOURCE / "supabase/migrations").glob("*.sql"))
    for source in files:
        target = WORKDIR / source.relative_to(SOURCE)
        if target.exists() and target.read_bytes() != source.read_bytes():
            raise DoctorError(
                "SAMPLE_FILES_CHANGED",
                "Sample setup files were modified. No files or database were reset; review edits.",
            )
    for source in files:
        target = WORKDIR / source.relative_to(SOURCE)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(source.read_bytes())


def scenario(identity: str, own: list[str], other: list[str]) -> dict[str, Any]:
    value = {
        "version": 1,
        "name": "task_board_" + identity,
        "request": {"schema": "task_board", "resource": "tasks", "columns": ["id"]},
        "identity": {
            "type": identity,
            **({"token_env": "RLS_DOCTOR_TEST_TOKEN"} if identity == "authenticated" else {}),
        },
        "expect": {
            "status": 200,
            "row_count": len(own),
            "contains": [{"column": "id", "value": value} for value in own],
            "excludes": [{"column": "id", "value": value} for value in other],
        },
    }
    Scenario.model_validate(value)
    return value


def check_report(data: dict[str, Any], count: int, role: str) -> None:
    require(data.get("result") == "PASS", "SAMPLE_REPLAY_RESULT")
    require(data.get("resource") == "task_board.tasks", "SAMPLE_REPLAY_RESOURCE")
    require(data.get("http", {}).get("status") == 200, "SAMPLE_REPLAY_HTTP")
    require(data.get("http", {}).get("row_count") == count, "SAMPLE_REPLAY_COUNT")
    require(data.get("identity", {}).get("confirmed_role") == role, "SAMPLE_REPLAY_ROLE")
    inspector = data.get("inspector")
    require(isinstance(inspector, dict), "SAMPLE_INSPECTOR_MISSING")
    table = inspector.get("table", {})
    require(
        table.get("schema") == "task_board"
        and table.get("name") == "tasks"
        and table.get("rls_enabled") is True,
        "SAMPLE_INSPECTOR_TABLE",
    )


def safe(text: str, private: list[str]) -> None:
    require(
        not any(secret and secret in text for secret in [*private, "SYNTHETIC_TASK_"]),
        "SAMPLE_PRIVATE_OUTPUT",
    )


def run() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Approve synthetic sample setup/checks")
    mode.add_argument("--stop", action="store_true", help="Stop this sample only, preserving data")
    args = parser.parse_args()
    cli = find_cli()
    if args.stop:
        require_command([cli, "stop", "--workdir", str(WORKDIR)])
        print("Sample app stopped; local data preserved.")
        return 0
    print("Explicit sample setup: separate ports 56321/56322, three synthetic tasks.", flush=True)
    print("Creates two local Auth users and assigns only these task rows. No reset.", flush=True)
    prepare()
    require_command([cli, "start", "--workdir", str(WORKDIR)])
    env = LocalEnvironment(
        approved_local=True,
        api_url="http://127.0.0.1:56321",
        allowed_api_ports=[56321],
        allowed_db_ports=[56322],
        resources=["tasks"],
    )
    values = credential_values(local_status(WORKDIR), env)
    artifacts = check_distributions()
    python = (
        artifacts.parent
        / "python-env"
        / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    )
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    node = shutil.which("node")
    require(bool(npm and node), "SAMPLE_TOOLS")
    assert npm and node
    run_dir = Path(tempfile.mkdtemp(prefix="run-", dir=WORKDIR))
    consumer = run_dir / "app"
    consumer.mkdir()
    for name in ("package.json", "package-lock.json", "app.mjs"):
        shutil.copyfile(SOURCE / name, consumer / name)
    require_command([npm, "ci", "--ignore-scripts", "--no-audit", "--no-fund"], cwd=consumer)
    sdk = next(artifacts.glob("*.tgz"))
    require_command(
        [npm, "install", "--offline", "--ignore-scripts", "--no-audit", "--no-fund", str(sdk)],
        cwd=consumer,
    )
    # This config holds references only. Credentials stay in environment scopes.
    config_path = run_dir / "rls-doctor.toml"
    config_path.write_text(
        "version = 1\n[environment]\napproved_local = true\n"
        'api_url = "http://127.0.0.1:56321"\nallowed_api_ports = [56321]\n'
        'allowed_db_ports = [56322]\nresources = ["tasks"]\nconfirm_identity = true\n',
        encoding="utf-8",
    )
    results: list[dict[str, Any]] = []
    with credentials(values):
        with httpx.Client(timeout=10, trust_env=False, follow_redirects=False) as client:
            tokens = [create_identity(env, approved=True, client=client) for _ in range(2)]
            subjects = [verify_test_token(token, env, client)["sub"] for token in tokens]
        require(all(subjects) and subjects[0] != subjects[1], "SAMPLE_IDENTITIES")
        with psycopg.connect(env.database_dsn()) as connection:
            for row_id, subject in zip(IDS, [subjects[0], subjects[0], subjects[1]], strict=True):
                changed = connection.execute(
                    "UPDATE task_board.tasks SET owner_id = %s WHERE id = %s", (subject, row_id)
                )
                require(changed.rowcount == 1, "SAMPLE_SEED_MISMATCH")
        private = [*values.values(), *tokens, *subjects]
        checked = require_command(
            [
                str(python),
                "-m",
                "rls_doctor.cli.main",
                "doctor",
                "--config",
                str(config_path),
                "--format",
                "json",
                "--output",
                str(run_dir / "doctor.json"),
            ],
            cwd=consumer,
        )
        safe(checked.stdout, private)
        doctor = json.loads(checked.stdout)
        require(doctor.get("result") == "PASS", "SAMPLE_DOCTOR")
        require(
            json.loads((run_dir / "doctor.json").read_text(encoding="utf-8")) == doctor,
            "SAMPLE_DOCTOR_FILE",
        )
        print("PASS installed doctor without any public application table")
        cases = [
            ("alice", tokens[0], IDS[:2], IDS[2:]),
            ("bob", tokens[1], IDS[2:], IDS[:2]),
            ("anonymous", None, [], IDS),
        ]
        for label, token, own, other in cases:
            case_dir = run_dir / label
            case_dir.mkdir()
            # Each process gets a fresh capture directory outside source files.
            capture_dir = consumer / "captures"
            with credentials(
                {
                    "RLS_DOCTOR_LOCAL_API_URL": env.origin(),
                    "RLS_DOCTOR_APPROVE_SAMPLE": "1",
                    "RLS_DOCTOR_SAMPLE_IDS": json.dumps(own),
                    **({"RLS_DOCTOR_TEST_TOKEN": token} if token else {}),
                },
                clear=("RLS_DOCTOR_TEST_TOKEN",) if token is None else (),
            ):
                app = require_command([node, "app.mjs"], cwd=consumer)
                safe(app.stdout, private)
                summary = json.loads(app.stdout)
                require(summary.get("result") == "PASS", "SAMPLE_APP_RESULT")
                require(summary.get("row_count") == len(own), "SAMPLE_APP_COUNT")
                event = Path(summary["event_file"])
                require(event.resolve().parent == capture_dir.resolve(), "SAMPLE_EVENT_PATH")
                event_text = event.read_text(encoding="utf-8")
                safe(event_text, private)
                data = parse_event(json.loads(event_text))
                require(data.request.resource == "tasks", "SAMPLE_CAPTURE_RESOURCE")
                saved_event = case_dir / "event.json"
                saved_event.write_text(event_text, encoding="utf-8")
                role = "authenticated" if token else "anon"
                path = case_dir / "tasks.yaml"
                path.write_text(yaml.safe_dump(scenario(role, own, other)), encoding="utf-8")
                validation = require_command(
                    [
                        str(python),
                        "-m",
                        "rls_doctor.cli.main",
                        "validate",
                        str(saved_event),
                        "--format",
                        "json",
                    ],
                    cwd=consumer,
                )
                safe(validation.stdout, private)
                require(json.loads(validation.stdout).get("result") == "PASS", "SAMPLE_CONTRACT")
                replayed = require_command(
                    [
                        str(python),
                        "-m",
                        "rls_doctor.cli.main",
                        "session",
                        "--config",
                        str(config_path),
                        "--workdir",
                        str(WORKDIR),
                        "--scenario",
                        str(path),
                        "--event",
                        str(saved_event),
                        "--run",
                        "--format",
                        "json",
                        "--output",
                        str(case_dir / "report.json"),
                    ],
                    cwd=consumer,
                )
                safe(replayed.stdout, private)
                report = json.loads(replayed.stdout)
                check_report(report, len(own), role)
                require(report.get("event_id") == str(data.event_id), "SAMPLE_EVENT_LINK")
                require(
                    json.loads((case_dir / "report.json").read_text(encoding="utf-8")) == report,
                    "SAMPLE_REPORT_FILE",
                )
                capture_dir.rename(case_dir / "captures")
                results.append({"case": label, "result": "PASS", "row_count": len(own)})
                print(
                    f"PASS installed app + capture + CLI + replay + inspection: {label}; "
                    f"expected rows {len(own)}, observed {report['http']['row_count']}"
                )
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "result": "PASS",
                "cases": results,
                "source": "maintained-synthetic-sample",
                "independent_adoption": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print("Sample reports: " + str(run_dir))
    print("No publication; no independent adoption or clean-machine claim.")
    return 0


def main() -> int:
    with practice_lock(WORKDIR):
        return run()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyboardInterrupt, EOFError):
        print("Sample check cancelled; stack remains running. Use --stop later.")
        raise SystemExit(3) from None
    except DoctorError as error:
        print("ERROR " + error.code + ": " + str(error))
        raise SystemExit(3) from None
    except Exception:
        print("ERROR sample check failed; private details suppressed. Check tools and Docker.")
        raise SystemExit(3) from None
