"""Real fixture-only JSON session smoke. Never print status, keys or raw child logs."""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml
from rls_doctor.core.config import LocalEnvironment, ProjectConfig
from rls_doctor.core.credentials import credential_values, local_status
from rls_doctor.core.errors import DoctorError

ROOT = Path(__file__).resolve().parents[1]


def check(workdir: Path) -> None:
    resolved = workdir.resolve()
    destinations = {
        (ROOT / "fixtures").resolve(): (54321, 54322),
        (ROOT / ".rls-doctor/practice").resolve(): (55321, 55322),
    }
    if resolved not in destinations:
        raise DoctorError(
            "SESSION_CHECK_WORKDIR",
            "Use only the repository's disposable fixtures or practice stack.",
        )
    api_port, db_port = destinations[resolved]
    config = ProjectConfig(
        environment=LocalEnvironment(
            approved_local=True,
            api_url=f"http://127.0.0.1:{api_port}",
            allowed_api_ports=[api_port],
            allowed_db_ports=[db_port],
            resources=["documents"],
        )
    )
    status = local_status(resolved)
    credential_values(status, config.environment)  # validates the status destination
    private = [
        status.get(key)
        for key in ("ANON_KEY", "PUBLISHABLE_KEY", "JWT_SECRET", "DB_URL", "SERVICE_ROLE_KEY")
    ]
    base = ROOT / ".rls-doctor"
    base.mkdir(exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="session-json-check-", dir=base))

    def run(
        name: str,
        *,
        approve: bool = True,
        probe: bool = True,
        expected_count: int = 0,
        language: str = "en",
    ) -> tuple[int, dict[str, object]]:
        config.environment.approved_local = approve
        config.environment.confirm_identity = probe
        lines = ["version = 1", "[environment]"]
        lines += [
            f"{key} = {json.dumps(value)}" for key, value in config.environment.model_dump().items()
        ]
        config_path = directory / (name + ".toml")
        config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        scenario_path = directory / (name + ".yaml")
        scenario_path.write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "name": "anonymous_json_check",
                    "request": {"resource": "documents"},
                    "identity": {"type": "anon"},
                    "expect": {"status": 200, "row_count": expected_count},
                }
            ),
            encoding="utf-8",
        )
        child = subprocess.run(
            [
                sys.executable,
                "-m",
                "rls_doctor.cli.main",
                "session",
                "--run",
                "--format",
                "json",
                "--output",
                str(directory / (name + "-report.json")),
                "--config",
                str(config_path),
                "--scenario",
                str(scenario_path),
                "--workdir",
                str(resolved),
                "--language",
                language,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )
        if len(child.stdout) > 1048576 or any(
            isinstance(secret, str) and secret and secret in child.stdout + child.stderr
            for secret in private
        ):
            raise DoctorError(
                "SESSION_CHECK_OUTPUT",
                "Unexpected credential-bearing or oversized child output was blocked.",
            )
        try:
            report = json.loads(child.stdout)
            if not isinstance(report, dict):
                raise ValueError
        except (ValueError, UnicodeError):
            raise DoctorError(
                "SESSION_CHECK_JSON",
                "Session output was not one clean JSON object; raw logs suppressed.",
            ) from None
        saved = (directory / (name + "-report.json")).read_text(encoding="utf-8")
        if json.loads(saved) != report or any(
            isinstance(secret, str) and secret and secret in saved for secret in private
        ):
            raise DoctorError("SESSION_CHECK_FILE", "Saved report differs or contains credentials.")
        return child.returncode, report

    for outcome, code, options in [
        ("PASS", 0, {}),
        ("FAIL", 1, {"expected_count": 1}),
        ("UNKNOWN", 2, {"probe": False}),
        ("ERROR", 3, {"approve": False}),
    ]:
        result_code, report = run(outcome.lower(), **options)
        if result_code != code or report.get("result") != outcome:
            raise DoctorError(
                "SESSION_CHECK_RESULT",
                "Session result or exit code differs from the expected fixture outcome.",
            )
        if outcome == "ERROR":
            if report.get("error", {}).get("code") != "LOCAL_APPROVAL_REQUIRED":
                raise DoctorError(
                    "SESSION_CHECK_ERROR", "Expected the approval guard, not another error."
                )
        else:
            if (
                report.get("http", {}).get("status") != 200
                or report.get("http", {}).get("row_count") != 0
            ):
                raise DoctorError("SESSION_CHECK_HTTP", "Unexpected actual fixture response.")
        print("PASS clean JSON stdout/file session " + outcome + " / " + str(code))
    code, report = run("russian", language="ru")
    if code != 0 or report.get("result") != "PASS":
        raise DoctorError(
            "SESSION_CHECK_LANGUAGE", "Russian session did not preserve the JSON result."
        )
    print("PASS language-independent JSON session")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", type=Path, default=ROOT / "fixtures")
    try:
        check(parser.parse_args().workdir)
    except DoctorError as error:
        print("ERROR " + error.code, file=sys.stderr)
        raise SystemExit(3) from None
    except Exception:
        print("ERROR session JSON smoke failed; unsafe details suppressed.", file=sys.stderr)
        raise SystemExit(3) from None
