"""Real local Supabase checks. Setup writes require explicit disposable-fixture consent.

Read `supabase status --workdir fixtures --output json` from stdin, never a file.
No captured requests, secrets, rows or raw subprocess errors are printed.
"""

import json
import os
import secrets
import subprocess
import sys
from pathlib import Path
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


def main() -> None:
    require(sys.argv[1:] == ["--status-stdin"], "STATUS_STDIN_REQUIRED")
    require(
        os.environ.get("RLS_DOCTOR_ALLOW_FIXTURE_SETUP") == "1",
        "SETUP_CONSENT_REQUIRED",
    )
    raw = sys.stdin.read(65537)
    require(len(raw) <= 65536, "STATUS_LIMIT")
    status = json.loads(raw)
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
    config = ProjectConfig(environment=env)

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
        require(report["result"] == wanted, name.upper())
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
    )
    case(
        "missing_grant",
        resource="no_grant_documents",
        expect={"status": 403, "error_class": "permission"},
    )
    case("tenant_isolation_leak", resource="leaky_documents", wanted="FAIL")
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
    child_env = {**os.environ, "RLS_DOCTOR_INTEGRATION_DSN": dsn}
    child = subprocess.run(
        [sys.executable, "-m", "pytest", "python/tests/integration", "-q", "--tb=no"],
        cwd=ROOT,
        env=child_env,
        capture_output=True,
        text=True,
        check=False,
    )
    require(child.returncode == 0, "POSTGRES_INTEGRATION_FAILED")
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
