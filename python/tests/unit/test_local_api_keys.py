"""Supabase CLI legacy API keys are distinct from Auth access tokens."""

import time

import httpx
import jwt
import pytest

from rls_doctor.core.config import LocalEnvironment
from rls_doctor.core.errors import DoctorError
from rls_doctor.identity.validation import local_headers, verify_test_token

SECRET = "synthetic-local-api-key-signing-secret-32-bytes"


def legacy_key(**overrides: object) -> str:
    # Supabase CLI v2.121.0 generateGoJwt: iss, role and exp; no iat.
    claims: dict[str, object] = {
        "iss": "supabase-demo",
        "role": "anon",
        "exp": int(time.time()) + 600,
    }
    claims.update(overrides)
    return jwt.encode(claims, SECRET, algorithm="HS256")


@pytest.fixture()
def environment(monkeypatch: pytest.MonkeyPatch) -> LocalEnvironment:
    monkeypatch.setenv("RLS_DOCTOR_LOCAL_JWT_SECRET", SECRET)
    return LocalEnvironment(approved_local=True)


def no_http(request: httpx.Request) -> httpx.Response:
    pytest.fail("Local API-key validation must not send an HTTP request.")


def test_cli_legacy_anon_key_without_iat_is_accepted(
    environment: LocalEnvironment, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = legacy_key()
    monkeypatch.setenv(environment.anon_key_env, key)
    with httpx.Client(transport=httpx.MockTransport(no_http)) as client:
        headers, claims = local_headers(environment, client, None)
    assert headers == {"apikey": key, "Authorization": "Bearer " + key}
    assert claims is None


@pytest.mark.parametrize(
    "case", ["expired", "missing_exp", "missing_role", "service_role", "signature"]
)
def test_invalid_legacy_key_is_rejected_without_leaking_credentials(
    environment: LocalEnvironment, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    claims: dict[str, object] = {
        "iss": "supabase-demo",
        "role": "anon",
        "exp": int(time.time()) + 600,
    }
    if case.startswith("missing_"):
        del claims[case.removeprefix("missing_")]
    elif case == "expired":
        claims["exp"] = 0
    elif case == "service_role":
        claims["role"] = "service_role"
    key = jwt.encode(
        claims,
        SECRET if case != "signature" else "different-synthetic-signing-secret-at-least-32-bytes",
        algorithm="HS256",
    )
    monkeypatch.setenv(environment.anon_key_env, key)
    with httpx.Client(transport=httpx.MockTransport(no_http)) as client:
        with pytest.raises(DoctorError) as error:
            local_headers(environment, client, None)
    assert error.value.code == "INVALID_TEST_TOKEN"
    assert key not in str(error.value)
    assert SECRET not in str(error.value)


def test_authenticated_access_token_still_requires_iat(environment: LocalEnvironment) -> None:
    encoded = legacy_key(
        role="authenticated",
        iss=environment.origin() + "/auth/v1",
        aud="authenticated",
        sub="11111111-1111-4111-8111-111111111111",
    )
    with httpx.Client(transport=httpx.MockTransport(no_http)) as client:
        with pytest.raises(DoctorError) as error:
            verify_test_token(encoded, environment, client)
    assert error.value.code == "INVALID_TEST_TOKEN"


def test_publishable_key_uses_anonymous_headers(
    environment: LocalEnvironment, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = "sb_publishable_SYNTHETIC_LOCAL_KEY"
    monkeypatch.setenv(environment.anon_key_env, key)
    with httpx.Client(transport=httpx.MockTransport(no_http)) as client:
        headers, claims = local_headers(environment, client, None)
    assert headers == {"apikey": key}
    assert claims is None
