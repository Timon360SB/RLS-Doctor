"""Validate local-test tokens before sending them to the replay endpoint."""

import json
from typing import Any

import httpx
import jwt

from rls_doctor.core.config import LocalEnvironment, read_secret
from rls_doctor.core.errors import DoctorError


def bounded_response(
    client: httpx.Client, url: str, headers: dict[str, str], limit: int = 1048576
) -> tuple[int, object, str | None]:
    """Read bounded local fixture output in memory; never retain response bodies."""
    with client.stream("GET", url, headers={**headers, "Accept-Encoding": "identity"}) as response:
        if 300 <= response.status_code < 400:
            raise DoctorError("REDIRECT_BLOCKED", "Local endpoint redirected; replay stopped.")
        if response.headers.get("content-encoding", "identity").lower() != "identity":
            raise DoctorError(
                "RESPONSE_ENCODING", "Compressed diagnostic responses are unsupported."
            )
        body = bytearray()
        for chunk in response.iter_bytes(chunk_size=16384):
            if len(body) + len(chunk) > limit:
                raise DoctorError(
                    "RESPONSE_LIMIT", "Local response exceeded the diagnostic memory limit."
                )
            body.extend(chunk)
        try:
            data: object = json.loads(body)
        except (ValueError, UnicodeError):
            data = None
        return response.status_code, data, response.headers.get("content-range")


def bounded_json(
    client: httpx.Client, url: str, headers: dict[str, str], limit: int = 1048576
) -> tuple[int, object]:
    status, data, _ = bounded_response(client, url, headers, limit)
    return status, data


def verify_test_token(
    token: str, env: LocalEnvironment, client: httpx.Client, role: str = "authenticated"
) -> dict[str, Any]:
    """Require a local signature, expiration, role and issuer; reject service keys."""
    try:
        header = jwt.get_unverified_header(token)
        algorithm = header.get("alg")
        options: jwt.types.Options = {"require": ["exp", "iat", "role"]}
        if algorithm == "HS256":
            key: Any = read_secret(env.jwt_secret_env)
            claims = jwt.decode(
                token,
                key,
                algorithms=["HS256"],
                options=options,
                audience=env.jwt_audience if role == "authenticated" else None,
                issuer=env.origin() + "/auth/v1" if role == "authenticated" else None,
            )
        elif algorithm in ("ES256", "RS256") and role == "authenticated":
            status, data = bounded_json(
                client, env.origin() + "/auth/v1/.well-known/jwks.json", {}, 65536
            )
            if (
                status != 200
                or not isinstance(data, dict)
                or not isinstance(data.get("keys"), list)
            ):
                raise ValueError
            matching = [
                k for k in data["keys"] if isinstance(k, dict) and k.get("kid") == header.get("kid")
            ]
            if len(matching) != 1:
                raise ValueError
            key = jwt.PyJWK.from_dict(matching[0], algorithm=algorithm).key
            claims = jwt.decode(
                token,
                key,
                algorithms=[algorithm],
                options=options,
                audience=env.jwt_audience,
                issuer=env.origin() + "/auth/v1",
            )
        else:
            raise ValueError
        if claims.get("role") != role:
            raise ValueError
        if role == "authenticated" and not isinstance(claims.get("sub"), str):
            raise ValueError
        return dict(claims)
    except DoctorError:
        raise
    except Exception:
        raise DoctorError(
            "INVALID_TEST_TOKEN",
            "Test token failed local signature, expiry, issuer, audience or role validation.",
        ) from None


def local_headers(
    env: LocalEnvironment, client: httpx.Client, token_env: str | None
) -> tuple[dict[str, str], dict[str, Any] | None]:
    apikey = read_secret(env.anon_key_env)
    if apikey.startswith("sb_secret_"):
        raise DoctorError("PRIVILEGED_KEY", "Use only a local anonymous or publishable API key.")
    headers = {"apikey": apikey}
    if apikey.count(".") == 2:
        verify_test_token(apikey, env, client, "anon")
        headers["Authorization"] = "Bearer " + apikey
    elif not apikey.startswith("sb_publishable_"):
        raise DoctorError("INVALID_API_KEY", "Unrecognized local anonymous API key format.")
    if token_env is None:
        return headers, None
    token = read_secret(token_env)
    claims = verify_test_token(token, env, client)
    headers["Authorization"] = "Bearer " + token
    return headers, claims
