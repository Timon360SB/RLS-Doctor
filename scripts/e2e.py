"""Real local Supabase checks. Setup writes require explicit disposable-fixture consent.

Read `supabase status --workdir fixtures --output json` from stdin, never a file.
No captured requests, secrets, rows or raw subprocess errors are printed.
"""

import contextlib
import io
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import psycopg
from psycopg import sql
from rls_doctor.core.config import (
    LocalEnvironment,
    ProjectConfig,
    validate_database_dsn,
)
from rls_doctor.core.errors import DoctorError
from rls_doctor.core.models import parse_event
from rls_doctor.postgres.inspector import inspect_table
from rls_doctor.replay.runner import replay
from rls_doctor.replay.scenarios import Scenario

ROOT = Path(__file__).resolve().parents[1]
OWN = "10000000-0000-4000-8000-000000000001"
OTHER = "10000000-0000-4000-8000-000000000002"
TABLES = ["documents", "blocked_documents", "no_grant_documents", "leaky_documents"]


def require(condition: bool, code: str) -> None:
    if not condition:
        raise DoctorError(code, "Disposable fixture verification failed.")


def setup_fixture(status: dict[str, Any]) -> tuple[ProjectConfig, list[tuple[str, str]]]:
    """Prepare only approved disposable fixtures; keep credentials in process memory."""
    require(
        os.environ.get("RLS_DOCTOR_ALLOW_FIXTURE_SETUP") == "1",
        "SETUP_CONSENT_REQUIRED",
    )
    env = LocalEnvironment(approved_local=True, api_url=status["API_URL"], resources=TABLES)
    origin = env.origin()
    dsn = validate_database_dsn(status["DB_URL"], env.allowed_db_ports)
    os.environ[env.anon_key_env] = status.get("ANON_KEY") or status["PUBLISHABLE_KEY"]
    os.environ[env.database_url_env] = dsn
    if status.get("JWT_SECRET"):
        os.environ[env.jwt_secret_env] = status["JWT_SECRET"]
    users: list[tuple[str, str]] = []
    with httpx.Client(timeout=10, trust_env=False, follow_redirects=False) as client:
        for _ in range(2):
            result = client.post(
                origin + "/auth/v1/signup",
                headers={"apikey": os.environ[env.anon_key_env]},
                json={
                    "email": f"rls-doctor-{uuid4()}@example.invalid",
                    "password": secrets.token_urlsafe(32),
                },
            )
            require(result.status_code == 200, "AUTH_SIGNUP_FAILED")
            data = result.json()
            require(isinstance(data.get("access_token"), str), "AUTH_SESSION_MISSING")
            users.append((data["user"]["id"], data["access_token"]))
    # Setup-only synthetic ownership update. The diagnostic runner never writes.
    with psycopg.connect(dsn) as connection:
        for table in TABLES:
            for row_id, user in zip((OWN, OTHER), users, strict=True):
                connection.execute(
                    sql.SQL("UPDATE public.{} SET owner_id = %s WHERE id = %s").format(
                        sql.Identifier(table)
                    ),
                    (user[0], row_id),
                )
    os.environ["RLS_DOCTOR_TEST_TOKEN"] = users[0][1]
    return ProjectConfig(environment=env), users


def require_case_evidence(
    report: dict[str, Any],
    name: str,
    wanted: str,
    observed_status: int | None = None,
    observed_count: int | None = None,
    evidence_checks: dict[str, str] | None = None,
) -> None:
    """An expected failing diagnosis must fail for the intended observed reason."""
    require(report["result"] == wanted, name.upper())
    if observed_status is not None:
        require(report["http"]["status"] == observed_status, name.upper() + "_HTTP_EVIDENCE")
    if observed_count is not None:
        require(report["http"]["row_count"] == observed_count, name.upper() + "_ROW_EVIDENCE")
    for check, result in (evidence_checks or {}).items():
        matching = [item for item in report["checks"] if item["check"] == check]
        require(
            len(matching) == 1 and matching[0]["result"] == result,
            name.upper() + "_CHECK_EVIDENCE",
        )


def integration_child() -> None:
    """Emit counts only; the parent never retains pytest diagnostics as artifacts."""
    import pytest

    class Evidence:
        collected = 0
        passed = 0
        skipped = 0
        failed = 0

        def pytest_collection_finish(self, session: pytest.Session) -> None:
            self.collected = len(session.items)

        def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
            if report.when == "call" and report.passed:
                self.passed += 1
            if report.skipped:
                self.skipped += 1
            if report.failed:
                self.failed += 1

    evidence = Evidence()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        result = pytest.main(["python/tests/integration", "-q", "--tb=no"], plugins=[evidence])
    print(
        json.dumps(
            {
                "exit_code": int(result),
                "collected": evidence.collected,
                "passed": evidence.passed,
                "skipped": evidence.skipped,
                "failed": evidence.failed,
            }
        )
    )


def run_integration_suite(dsn: str) -> None:
    """Require actual executed passes, including when pytest exits zero after skips."""
    child = subprocess.run(
        [sys.executable, "-c", "from scripts.e2e import integration_child; integration_child()"],
        cwd=ROOT,
        env={**os.environ, "RLS_DOCTOR_INTEGRATION_DSN": dsn},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    require(child.returncode == 0, "POSTGRES_INTEGRATION_FAILED")
    try:
        summary = json.loads(child.stdout)
    except (ValueError, UnicodeError):
        raise DoctorError(
            "POSTGRES_INTEGRATION_EVIDENCE", "Integration execution evidence is unavailable."
        ) from None
    keys = ("exit_code", "collected", "passed", "skipped", "failed")
    require(
        isinstance(summary, dict)
        and all(type(summary.get(key)) is int for key in keys)
        and summary["exit_code"] == 0
        and summary["collected"] > 0
        and summary["passed"] == summary["collected"]
        and summary["skipped"] == 0
        and summary["failed"] == 0,
        "POSTGRES_INTEGRATION_INCOMPLETE",
    )


def fixture_integration_dsn(dsn: str) -> str:
    """Use the fixture admin only for creating disposable PostgreSQL test roles.

    Supabase's ordinary postgres login is deliberately not a superuser. This
    opt-in test harness uses the local admin; diagnostics keep the ordinary DSN.
    """
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    require(os.environ.get("RLS_DOCTOR_ALLOW_FIXTURE_SETUP") == "1", "SETUP_CONSENT_REQUIRED")
    params = conninfo_to_dict(validate_database_dsn(dsn, [54322]))
    require(params.get("user") == "postgres", "UNEXPECTED_FIXTURE_DATABASE_USER")
    params["user"] = "supabase_admin"
    params["hostaddr"] = params["host"]
    return make_conninfo(**params)


def main() -> None:
    require(sys.argv[1:] == ["--status-stdin"], "STATUS_STDIN_REQUIRED")
    raw = sys.stdin.read(65537)
    require(len(raw) <= 65536, "STATUS_LIMIT")
    config, users = setup_fixture(json.loads(raw))
    env = config.environment
    origin = env.origin()
    dsn = env.database_dsn()

    # Capture an actual supabase-js request, then validate the real event in Python.
    process = subprocess.run(
        ["node", "examples/node-basic/live-event.mjs"],
        cwd=ROOT,
        env={**os.environ, "RLS_DOCTOR_LOCAL_API_URL": origin},
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    require(process.returncode == 0, "LIVE_CAPTURE_FAILED")
    event = parse_event(json.loads(process.stdout))
    require(event.response.status == 200, "LIVE_CAPTURE_STATUS")
    print("PASS actual supabase-js GET -> Capture SDK -> JSON Schema -> Python")

    def case(
        name: str,
        resource: str = "documents",
        identity: str = "authenticated",
        expect: dict[str, object] | None = None,
        filters: dict[str, object] | None = None,
        wanted: str = "PASS",
        observed_status: int | None = None,
        observed_count: int | None = None,
        evidence_checks: dict[str, str] | None = None,
    ) -> None:
        identity_data: dict[str, object] = {"type": identity}
        if identity == "authenticated":
            identity_data["token_env"] = "RLS_DOCTOR_TEST_TOKEN"
        scenario = Scenario.model_validate(
            {
                "version": 1,
                "name": name,
                "request": {"resource": resource},
                "identity": identity_data,
                "filters": filters or {},
                "expect": expect
                or {
                    "status": 200,
                    "row_count": 1,
                    "contains": [{"column": "id", "value": OWN}],
                    "excludes": [{"column": "id", "value": OTHER}],
                },
            }
        )
        report = replay(scenario, config, event if resource == "documents" else None, inspect=True)
        require_case_evidence(
            report, name, wanted, observed_status, observed_count, evidence_checks
        )
        serialized = json.dumps(report)
        require(
            all(
                secret not in serialized
                for secret in (users[0][1], users[1][1], os.environ[env.anon_key_env])
            ),
            "REPORT_SECRET_LEAK",
        )
        print("PASS " + name)

    case("own_row_and_other_user_denial")
    os.environ["RLS_DOCTOR_TEST_TOKEN"] = users[1][1]
    case(
        "second_test_user",
        expect={
            "status": 200,
            "row_count": 1,
            "contains": [{"column": "id", "value": OTHER}],
            "excludes": [{"column": "id", "value": OWN}],
        },
    )
    os.environ["RLS_DOCTOR_TEST_TOKEN"] = users[0][1]
    case("missing_auth", identity="anon", expect={"status": 200, "row_count": 0})
    case(
        "default_deny",
        resource="blocked_documents",
        expect={"status": 200, "row_count": 1},
        wanted="FAIL",
        observed_status=200,
        observed_count=0,
        evidence_checks={"http_status": "PASS", "row_count": "FAIL", "executed_role": "PASS"},
    )
    case(
        "missing_grant",
        resource="no_grant_documents",
        expect={"status": 403, "error_class": "permission"},
    )
    case(
        "tenant_isolation_leak",
        resource="leaky_documents",
        wanted="FAIL",
        observed_status=200,
        observed_count=2,
        evidence_checks={
            "http_status": "PASS",
            "row_count": "FAIL",
            "contains_1": "PASS",
            "excludes_1": "FAIL",
            "executed_role": "PASS",
        },
    )
    case(
        "nonexistent_row_ambiguity",
        filters={"id": {"eq": str(uuid4())}},
        expect={"status": 200, "row_count": 0},
    )
    os.environ["RLS_DOCTOR_TEST_TOKEN"] = "invalid-local-token"
    try:
        case("invalid_token")
    except DoctorError as exc:
        require(exc.code == "INVALID_TEST_TOKEN", "INVALID_TOKEN_CLASS")
    else:
        raise DoctorError("INVALID_TOKEN_ACCEPTED", "Invalid token was accepted.")
    print("PASS invalid test token rejected before transmission")
    inspected = inspect_table(dsn, "public", "no_grant_documents", "authenticated")
    require(
        any(f["code"] == "SELECT_PRIVILEGE_MISSING" for f in inspected["conclusions"]),
        "MISSING_GRANT_INSPECTION",
    )

    # Run real PostgreSQL regression suite using credentials only in child env.
    run_integration_suite(fixture_integration_dsn(dsn))
    print("PASS real PostgreSQL inspector integration suite")


if __name__ == "__main__":
    try:
        main()
    except DoctorError as error:
        print("ERROR " + error.code, file=sys.stderr)
        sys.exit(3)
    except Exception:
        print(
            "ERROR local fixture setup or E2E execution failed; unsafe details suppressed.",
            file=sys.stderr,
        )
        sys.exit(3)
