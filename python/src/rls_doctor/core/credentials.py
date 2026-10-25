"""Local-only credential onboarding; values never enter files or diagnostics."""

import contextlib
import json
import os
import secrets
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from rls_doctor.core.config import LocalEnvironment, validate_database_dsn, validate_local_url
from rls_doctor.core.errors import DoctorError
from rls_doctor.identity.validation import local_headers, verify_test_token


def find_cli() -> str:
    executable = shutil.which("supabase")
    if executable:
        return executable
    # The Windows demo installs a pinned native CLI in npm's cache, not global PATH.
    cache = os.environ.get("npm_config_cache")
    if not cache and os.environ.get("LOCALAPPDATA"):
        cache = str(Path(os.environ["LOCALAPPDATA"]) / "npm-cache")
    if cache:
        for candidate in sorted(
            Path(cache).glob("_npx/*/node_modules/@supabase/cli-windows-x64/bin/supabase.exe")
        ):
            return str(candidate)
    raise DoctorError(
        "SUPABASE_CLI_MISSING",
        "Install Supabase CLI 2.121.0 or run the Windows demo launcher first.",
    )


def local_status(workdir: Path) -> dict[str, Any]:
    if not (workdir / "supabase/config.toml").is_file():
        raise DoctorError(
            "SUPABASE_PROJECT_MISSING",
            "Choose the local project folder containing supabase/config.toml.",
        )
    try:
        result = subprocess.run(
            [find_cli(), "status", "--workdir", str(workdir.resolve()), "--output", "json"],
            capture_output=True,
            timeout=20,
            check=False,
        )
        if result.returncode != 0 or len(result.stdout) > 65536:
            raise ValueError
        status: object = json.loads(result.stdout)
        if not isinstance(status, dict):
            raise ValueError
        # Drop unused CLI fields (including privileged keys) at this boundary.
        allowed = {"API_URL", "DB_URL", "ANON_KEY", "PUBLISHABLE_KEY", "JWT_SECRET"}
        return {key: value for key, value in status.items() if key in allowed}
    except DoctorError:
        raise
    except (OSError, ValueError, subprocess.SubprocessError):
        raise DoctorError(
            "LOCAL_STACK_STATUS_FAILED",
            "Cannot read local Supabase status. Start this project's local stack and retry.",
        ) from None


def credential_values(status: dict[str, Any], env: LocalEnvironment) -> dict[str, str]:
    """Match endpoints before installing the allowlisted credential values."""
    expected = env.origin()  # approval is mandatory before any credential use
    api = status.get("API_URL")
    dsn = status.get("DB_URL")
    if not isinstance(api, str) or validate_local_url(api, env.allowed_api_ports) != expected:
        raise DoctorError(
            "LOCAL_PROJECT_MISMATCH",
            "Supabase API address differs from the approved configuration.",
        )
    if not isinstance(dsn, str):
        raise DoctorError("LOCAL_STACK_STATUS_FAILED", "Local database details are unavailable.")
    values = {
        env.anon_key_env: status.get("ANON_KEY") or status.get("PUBLISHABLE_KEY"),
        env.database_url_env: validate_database_dsn(dsn, env.allowed_db_ports),
    }
    if status.get("JWT_SECRET"):
        values[env.jwt_secret_env] = status["JWT_SECRET"]
    names = [env.anon_key_env, env.database_url_env, env.jwt_secret_env]
    if len(set(names)) != len(names) or any(not name.startswith("RLS_DOCTOR_") for name in names):
        raise DoctorError(
            "SESSION_VARIABLE_NAMES",
            "Session credential names must be distinct RLS_DOCTOR_ variables.",
        )
    if any(
        not isinstance(v, str) or not v or len(v) > 16384 or any(c in v for c in "\r\n\x00")
        for v in values.values()
    ):
        raise DoctorError(
            "LOCAL_STACK_STATUS_FAILED", "Local credential metadata is missing or invalid."
        )
    return {name: str(value) for name, value in values.items()}


@contextlib.contextmanager
def credentials(values: dict[str, str], *, clear: tuple[str, ...] = ()) -> Iterator[None]:
    """Restore the caller's environment on success, failure and cancellation."""
    previous = {name: os.environ.get(name) for name in {*values, *clear}}
    try:
        for name in clear:
            os.environ.pop(name, None)
        os.environ.update(values)
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def create_identity(env: LocalEnvironment, *, approved: bool, client: httpx.Client) -> str:
    """Setup-only Auth signup, never a write replay or a table/policy mutation."""
    if not approved:
        raise DoctorError(
            "TEST_IDENTITY_APPROVAL",
            "Creating a synthetic local Auth user requires explicit approval.",
        )
    headers, _ = local_headers(env, client, None)
    url = env.origin() + "/auth/v1/signup"
    with client.stream(
        "POST",
        url,
        headers={**headers, "Accept-Encoding": "identity"},
        follow_redirects=False,
        json={
            "email": f"rls-doctor-{uuid4()}@example.invalid",
            "password": secrets.token_urlsafe(32),
        },
    ) as response:
        if (
            response.status_code != 200
            or response.headers.get("content-encoding", "identity") != "identity"
        ):
            raise DoctorError(
                "TEST_IDENTITY_SETUP_FAILED",
                "Local test signup failed. Check local Auth signup settings; "
                "no raw response was retained.",
            )
        body = bytearray()
        for chunk in response.iter_bytes(chunk_size=16384):
            if len(body) + len(chunk) > 65536:
                raise DoctorError(
                    "RESPONSE_LIMIT", "Local Auth response exceeded the memory limit."
                )
            body.extend(chunk)
        try:
            data = json.loads(body)
            token = data.get("access_token") if isinstance(data, dict) else None
            if not isinstance(token, str) or len(token) > 16384:
                raise ValueError
        except (ValueError, UnicodeError):
            raise DoctorError(
                "TEST_IDENTITY_SETUP_FAILED",
                "No local test session returned. Email confirmation may be "
                "required; no settings were changed.",
            ) from None
    verify_test_token(token, env, client)
    return token
