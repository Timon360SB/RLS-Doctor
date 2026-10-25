"""Real PostgreSQL version checks using owned disposable Docker containers."""

import argparse
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import psycopg
from e2e import ROOT, run_integration_suite
from psycopg.conninfo import make_conninfo
from rls_doctor.core.credentials import credentials
from rls_doctor.core.errors import DoctorError


def docker_executable() -> str:
    found = shutil.which("docker")
    if found:
        return found
    for path in (
        Path("D:/Docker/Desktop/resources/bin/docker.exe"),
        Path(os.environ.get("ProgramFiles", "C:/Program Files"))
        / "Docker/Docker/resources/bin/docker.exe",
    ):
        if path.is_file():
            return str(path)
    raise DoctorError("DOCKER_MISSING", "Docker CLI is required for the compatibility checks.")


def command(
    executable: str, args: list[str], *, timeout: int = 300
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [executable, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def check_version(executable: str, version: str) -> dict[str, object]:
    if version not in {"16", "17", "18"}:
        raise DoctorError("POSTGRES_MATRIX_VERSION", "Choose PostgreSQL 16, 17 or 18.")
    port = 55400 + int(version)
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            raise DoctorError(
                "POSTGRES_MATRIX_PORT",
                "A compatibility-test port is already occupied; no existing service was changed.",
            )
    identity = uuid4().hex
    name = "rls-doctor-pg" + version + "-" + identity[:12]
    image = "docker.io/library/postgres:" + version
    password = secrets.token_hex(32)
    dsn = make_conninfo(
        host="127.0.0.1",
        hostaddr="127.0.0.1",
        port=str(port),
        dbname="postgres",
        user="postgres",
        password=password,
        connect_timeout="2",
    )
    print(
        "Starting disposable PostgreSQL " + version + " (first run may download the image)...",
        flush=True,
    )
    # Container environment gets the password by variable name; it never appears in arguments.
    with credentials({"POSTGRES_PASSWORD": password, "RLS_DOCTOR_ALLOW_FIXTURE_SETUP": "1"}):
        owned_started = False
        try:
            started = command(
                executable,
                [
                    "run",
                    "-d",
                    "--name",
                    name,
                    "--label",
                    "rls-doctor.compatibility=" + identity,
                    "--memory",
                    "512m",
                    "--publish",
                    f"127.0.0.1:{port}:5432",
                    "--env",
                    "POSTGRES_PASSWORD",
                    image,
                ],
            )
            if started.returncode or not re.fullmatch(r"[a-f0-9]{64}\s*", started.stdout):
                raise DoctorError(
                    "POSTGRES_MATRIX_START",
                    "Could not start the disposable PostgreSQL container; raw logs suppressed.",
                )
            owned_started = True
            deadline = time.monotonic() + 90
            actual = None
            while time.monotonic() < deadline:
                try:
                    with psycopg.connect(dsn) as connection:
                        actual = connection.execute(
                            "SELECT current_setting('server_version_num')::int"
                        ).fetchone()[0]
                    break
                except psycopg.Error:
                    time.sleep(1)
            if actual is None or actual // 10000 != int(version):
                raise DoctorError(
                    "POSTGRES_MATRIX_READY",
                    "PostgreSQL did not become ready with the expected major version.",
                )
            evidence = run_integration_suite(dsn)
            metadata = command(
                executable,
                ["image", "inspect", image, "--format", "{{json .RepoDigests}}"],
                timeout=20,
            )
            digests = json.loads(metadata.stdout) if metadata.returncode == 0 else []
            print(
                "PASS PostgreSQL " + str(actual) + ": " + str(evidence["passed"]) + " real tests",
                flush=True,
            )
            return {
                "major": int(version),
                "server_version_num": actual,
                "image": image,
                "digests": digests,
                "evidence": evidence,
            }
        finally:
            # Remove only this run's object, after checking its unique ownership label.
            inspect = command(
                executable,
                [
                    "inspect",
                    "--format",
                    '{{index .Config.Labels "rls-doctor.compatibility"}}',
                    name,
                ],
                timeout=20,
            )
            if inspect.returncode != 0 and owned_started:
                raise DoctorError(
                    "POSTGRES_MATRIX_CLEANUP",
                    "Could not verify cleanup of the owned compatibility container.",
                )
            if inspect.returncode == 0:
                if inspect.stdout.strip() != identity:
                    raise DoctorError(
                        "POSTGRES_MATRIX_OWNERSHIP",
                        "Container ownership label differs; no cleanup was performed.",
                    )
                removed = command(executable, ["rm", "--force", "--volumes", name], timeout=60)
                if removed.returncode:
                    raise DoctorError(
                        "POSTGRES_MATRIX_CLEANUP",
                        "Owned temporary container cleanup failed; inspect "
                        "compatibility containers manually.",
                    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--versions", nargs="+", choices=["16", "17", "18"], default=["16", "18"])
    args = parser.parse_args()
    executable = docker_executable()
    engine = command(executable, ["info", "--format", "{{.OSType}}"], timeout=30)
    if engine.returncode or engine.stdout.strip() != "linux":
        raise DoctorError(
            "DOCKER_NOT_READY", "Start Docker's Linux engine before the compatibility checks."
        )
    results = [check_version(executable, version) for version in dict.fromkeys(args.versions)]
    destination = ROOT / ".rls-doctor" / "postgres-matrix.json"
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps({"versions": results}, indent=2), encoding="utf-8")
    print("Saved version/digest/count evidence: " + str(destination))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DoctorError as error:
        print("ERROR " + error.code)
        raise SystemExit(3) from None
    except Exception:
        print("ERROR PostgreSQL compatibility check failed; unsafe details suppressed.")
        raise SystemExit(3) from None
