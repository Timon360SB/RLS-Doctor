import gzip
import json
import time
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from rls_doctor.core.config import LocalEnvironment, ProjectConfig
from rls_doctor.core.errors import DoctorError
from rls_doctor.identity.validation import bounded_json, verify_test_token
from rls_doctor.replay.assertions import aggregate, compare
from rls_doctor.replay.runner import replay
from rls_doctor.replay.scenarios import Expectations, Scenario

SECRET = "unit-only-test-signing-secret-at-least-32-bytes"
SUBJECT = "11111111-1111-4111-8111-111111111111"


def token(**overrides: object) -> str:
    claims: dict[str, object] = {
        "iss": "http://127.0.0.1:54321/auth/v1",
        "aud": "authenticated",
        "role": "authenticated",
        "sub": SUBJECT,
        "iat": int(time.time()),
        "exp": int(time.time()) + 600,
    }
    claims.update(overrides)
    return jwt.encode(claims, SECRET, algorithm="HS256")


def scenario(**kwargs: Any) -> Scenario:
    data = {
        "version": 1,
        "name": "owner",
        "request": {"resource": "documents"},
        "identity": {"type": "authenticated", "token_env": "RLS_DOCTOR_TEST_TOKEN"},
        "expect": {
            "status": 200,
            "row_count": 1,
            "contains": [{"column": "id", "value": 42}],
            "excludes": [{"column": "id", "value": 43}],
        },
    }
    data.update(kwargs)
    return Scenario.model_validate(data)


@pytest.fixture()
def config(monkeypatch: pytest.MonkeyPatch) -> ProjectConfig:
    monkeypatch.setenv("RLS_DOCTOR_LOCAL_ANON_KEY", "sb_publishable_SYNTHETIC_UNIT_KEY")
    monkeypatch.setenv("RLS_DOCTOR_LOCAL_JWT_SECRET", SECRET)
    monkeypatch.setenv("RLS_DOCTOR_TEST_TOKEN", token())
    return ProjectConfig(environment=LocalEnvironment(approved_local=True))


def response(
    request: httpx.Request, rows: object = None, *, status: int = 200, role: str = "authenticated"
) -> httpx.Response:
    if "/rpc/" in request.url.path:
        return httpx.Response(
            200, json={"role": role, "uid": SUBJECT if role == "authenticated" else None}
        )
    return httpx.Response(
        status,
        json=[{"id": 42, "private": "TABLE_SECRET"}] if rows is None else rows,
        headers={"Content-Range": "0-0/1" if rows is None else "*/0"},
    )


def test_replay_compares_and_never_serializes_rows(config: ProjectConfig) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return response(request)

    report = replay(scenario(), config, transport=httpx.MockTransport(handler))
    assert report["result"] == "PASS"
    assert report["identity"]["confirmed_role"] == "authenticated"
    assert all(r.method == "GET" for r in seen)
    rendered = json.dumps(report)
    assert all(
        secret not in rendered for secret in (SECRET, token(), "TABLE_SECRET", "SYNTHETIC_UNIT_KEY")
    )


def test_empty_result_fails_expectation_without_claiming_rls(config: ProjectConfig) -> None:
    report = replay(scenario(), config, transport=httpx.MockTransport(lambda r: response(r, [])))
    assert report["result"] == "FAIL"
    assert (
        next(f for f in report["findings"] if f["code"] == "EMPTY_RESULT_AMBIGUOUS")["evidence"]
        == "UNVERIFIED"
    )


def test_absence_of_foreign_row_is_a_real_assertion() -> None:
    checks = compare(
        Expectations.model_validate({"status": 200, "excludes": [{"column": "id", "value": 43}]}),
        200,
        [{"id": 42}, {"id": 43}],
    )
    assert aggregate(checks) == "FAIL"
    assert aggregate(compare(Expectations(row_count=0), 200, "bad")) == "UNKNOWN"


@pytest.mark.parametrize(
    "claims",
    [
        {"role": "service_role"},
        {"iss": "https://production.supabase.co/auth/v1"},
        {"aud": "wrong"},
        {"exp": 0},
    ],
)
def test_rejects_wrong_or_expired_token_before_http(
    config: ProjectConfig, monkeypatch: pytest.MonkeyPatch, claims: dict[str, object]
) -> None:
    monkeypatch.setenv("RLS_DOCTOR_TEST_TOKEN", token(**claims))
    seen: list[object] = []
    with pytest.raises(DoctorError):
        replay(scenario(), config, transport=httpx.MockTransport(lambda r: seen.append(r)))  # type: ignore[arg-type]
    assert seen == []


def test_rejects_bad_signature(config: ProjectConfig, monkeypatch: pytest.MonkeyPatch) -> None:
    bad = token()[:-8] + "00000000"
    monkeypatch.setenv("RLS_DOCTOR_TEST_TOKEN", bad)
    with pytest.raises(DoctorError):
        replay(scenario(), config, transport=httpx.MockTransport(lambda r: response(r)))


def test_redirect_never_follows_or_leaks(config: ProjectConfig) -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(302, headers={"Location": "https://evil.example/TOPSECRET"})

    with pytest.raises(DoctorError) as exc:
        replay(scenario(), config, transport=httpx.MockTransport(handler))
    assert exc.value.code == "REDIRECT_BLOCKED"
    assert len(seen) == 1
    assert "TOPSECRET" not in str(exc.value)


def test_missing_identity_probe_never_false_pass(config: ProjectConfig) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return (
            httpx.Response(404, json={"message": "TOPSECRET"})
            if "/rpc/" in request.url.path
            else response(request)
        )

    report = replay(scenario(), config, transport=httpx.MockTransport(handler))
    assert report["result"] == "UNKNOWN"
    assert report["identity"]["confirmed_role"] is None


def test_probe_role_mismatch_and_incomplete_response(config: ProjectConfig) -> None:
    with pytest.raises(DoctorError) as exc:
        replay(
            scenario(), config, transport=httpx.MockTransport(lambda r: response(r, role="anon"))
        )
    assert exc.value.code == "IDENTITY_MISMATCH"

    def incomplete(request: httpx.Request) -> httpx.Response:
        return (
            response(request)
            if "/rpc/" in request.url.path
            else httpx.Response(200, json=[{"id": 42}])
        )

    assert (
        replay(scenario(), config, transport=httpx.MockTransport(incomplete))["result"] == "UNKNOWN"
    )


def test_jwks_uses_only_local_get_and_verifies_signature(config: ProjectConfig) -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    jwk = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(key.public_key()))
    jwk["kid"] = "local-test"
    encoded = jwt.encode(
        jwt.decode(token(), SECRET, algorithms=["HS256"], audience="authenticated"),
        key,
        algorithm="ES256",
        headers={"kid": "local-test"},
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://127.0.0.1:54321/auth/v1/.well-known/jwks.json"
        return httpx.Response(200, json={"keys": [jwk]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert verify_test_token(encoded, config.environment, client)["sub"] == SUBJECT


def test_http_permission_class_and_data_unknown() -> None:
    assert (
        aggregate(
            compare(
                Expectations.model_validate({"status": 403, "error_class": "permission"}),
                403,
                {"code": "42501", "message": "PRIVATE"},
            )
        )
        == "PASS"
    )
    assert (
        aggregate(
            compare(
                Expectations.model_validate({"status": 401, "error_class": "authorization"}),
                401,
                {},
            )
        )
        == "PASS"
    )


@pytest.mark.parametrize("content_range", ["100-100/1", "0-0/0", "0-1/1", "*/1", "1-1/1", "0-0/*"])
def test_impossible_or_partial_ranges_never_pass(config: ProjectConfig, content_range: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/rpc/" in request.url.path:
            return response(request)
        return httpx.Response(200, json=[{"id": 42}], headers={"Content-Range": content_range})

    assert replay(scenario(), config, transport=httpx.MockTransport(handler))["result"] == "UNKNOWN"


def test_server_ignoring_row_limit_never_passes(config: ProjectConfig) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/rpc/" in request.url.path:
            return response(request)
        return httpx.Response(
            200, json=[{"id": 42}] * 1001, headers={"Content-Range": "0-1000/1001"}
        )

    run = scenario(expect={"status": 200, "row_count": 1001})
    assert replay(run, config, transport=httpx.MockTransport(handler))["result"] == "UNKNOWN"


def test_malformed_row_array_has_unknown_result(config: ProjectConfig) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/rpc/" in request.url.path:
            return response(request)
        return httpx.Response(200, json=["PRIVATE_VALUE"], headers={"Content-Range": "0-0/1"})

    report = replay(
        scenario(expect={"status": 200}), config, transport=httpx.MockTransport(handler)
    )
    assert report["result"] == "UNKNOWN"
    assert "PRIVATE_VALUE" not in json.dumps(report)


@pytest.mark.parametrize("encoding", [False, True])
def test_response_memory_and_encoding_boundaries(encoding: bool) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if encoding:
            return httpx.Response(
                200, content=gzip.compress(b"TOPSECRET"), headers={"Content-Encoding": "gzip"}
            )
        return httpx.Response(200, content=b"TOPSECRET" * 1000)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(DoctorError) as exc:
            bounded_json(client, "http://127.0.0.1:54321", {}, limit=32)
    assert exc.value.code == ("RESPONSE_ENCODING" if encoding else "RESPONSE_LIMIT")
    assert "TOPSECRET" not in str(exc.value)


def test_custom_table_schema_does_not_redirect_the_trusted_public_probe(
    config: ProjectConfig,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/rpc/" in request.url.path:
            if request.headers.get("accept-profile") != "public":
                return httpx.Response(404, json={"code": "PGRST202"})
            return response(request)
        assert request.headers["accept-profile"] == "private"
        return response(request)

    report = replay(
        scenario(request={"resource": "documents", "schema": "private"}),
        config,
        transport=httpx.MockTransport(handler),
    )
    assert report["result"] == "PASS"
    assert report["identity"]["confirmed_role"] == "authenticated"


@pytest.mark.parametrize("language", ["en", "ru"])
def test_inspection_failure_keeps_http_evidence_and_safe_sqlstate(
    config: ProjectConfig,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    language: Any,
) -> None:
    import importlib

    from rls_doctor.postgres.inspector import InspectorError
    from rls_doctor.reports.console import render

    runner = importlib.import_module("rls_doctor.replay.runner")

    def reject(*args: object, **kwargs: object) -> object:
        raise InspectorError(
            "POSTGRES_INSPECTION_FAILED", "Fixed message", "42501", phase="catalog"
        )

    monkeypatch.setenv(
        "RLS_DOCTOR_DATABASE_URL",
        "host=127.0.0.1 port=54322 dbname=postgres user=reader password=PRIVATE_PASSWORD",
    )
    monkeypatch.setattr(runner, "inspect_table", reject)
    report = replay(scenario(), config, inspect=True, transport=httpx.MockTransport(response))
    assert report["result"] == "ERROR"
    assert report["http"]["status"] == 200 and report["http"]["row_count"] == 1
    assert report["inspector"]["error"]["sqlstate"] == "42501"
    assert report["inspector"]["error"]["diagnostic"]["category"] == "insufficient_privilege"
    render(report, language=language)
    output = capsys.readouterr().out
    assert "42501" in output
    assert "PRIVATE_PASSWORD" not in output
    assert "TABLE_SECRET" not in output
    assert "Policies inspected" not in output
    assert "Политик прочитано" not in output
