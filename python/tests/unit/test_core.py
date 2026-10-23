import copy
import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from rls_doctor.cli.main import app
from rls_doctor.core.config import LocalEnvironment, validate_database_dsn, validate_local_url
from rls_doctor.core.errors import DoctorError
from rls_doctor.core.models import load_event, parse_event
from rls_doctor.identity.analyzer import analyze_event
from rls_doctor.replay.scenarios import load_scenario

ROOT = Path(__file__).resolve().parents[3]
EVENT = {
    "schema_version": "1.0",
    "event_id": "00000000-0000-4000-8000-000000000001",
    "timestamp": "2026-10-23T10:00:00Z",
    "duration_ms": 0,
    "request": {"method": "GET", "api": "rest", "resource": "documents", "filters": []},
    "response": {"status": 200, "row_count": 0, "error_kind": None},
    "context": {"authorization_present": False, "apikey_present": True},
}


def test_event_contract_and_hypothesis() -> None:
    event = parse_event(EVENT)
    findings = analyze_event(event, "authenticated")
    assert (
        next(f for f in findings if f["code"] == "MISSING_EXPECTED_AUTH")["evidence"] == "OBSERVED"
    )
    assert (
        next(f for f in findings if f["code"] == "EMPTY_RESULT_AMBIGUOUS")["evidence"]
        == "UNVERIFIED"
    )


@pytest.mark.parametrize(
    "mutation",
    [
        {"schema_version": "2.0"},
        {"jwt": "TOPSECRET"},
        {"event_id": "TOPSECRET"},
        {"timestamp": "yesterday"},
        {"duration_ms": True},
        {"duration_ms": -1},
    ],
)
def test_event_rejections_do_not_echo_input(mutation: dict[str, object]) -> None:
    data = copy.deepcopy(EVENT)
    data.update(mutation)
    with pytest.raises(DoctorError) as exc:
        parse_event(data)
    assert "TOPSECRET" not in str(exc.value)


def test_packaged_schema_is_canonical() -> None:
    assert (ROOT / "schemas/diagnostic-event-v1.schema.json").read_bytes() == (
        ROOT / "python/src/rls_doctor/schemas/diagnostic-event-v1.schema.json"
    ).read_bytes()


def test_actual_typescript_producer_to_python_consumer() -> None:
    script = ROOT / "examples/node-basic/capture-event.mjs"
    assert (ROOT / "packages/capture-sdk/dist/index.js").exists(), "Build SDK before contract tests"
    process = subprocess.run(
        ["node", str(script)], cwd=ROOT, check=True, capture_output=True, text=True, timeout=15
    )
    event = parse_event(json.loads(process.stdout))
    assert event.request.resource == "documents"
    assert "secret" not in process.stdout.lower()


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:54321",
        "https://127.0.0.1:54321",
        "http://127.0.0.1:80",
        "http://127.0.0.1:54321@evil.com",
        "http://127.0.0.1:54321/path",
        "http://127.0.0.1:54321?secret=TOPSECRET",
        "http://127.0.0.1.evil:54321",
        "http://2130706433:54321",
        "http://127.0.0.1%2f@evil.com:54321",
        "http://[::1%25eth0]:54321",
    ],
)
def test_local_endpoint_guard(url: str) -> None:
    with pytest.raises(DoctorError):
        validate_local_url(url, [54321])


def test_numeric_loopback_and_approval() -> None:
    assert validate_local_url("http://[::1]:54321/", [54321]) == "http://[::1]:54321"
    with pytest.raises(DoctorError):
        LocalEnvironment().origin()


@pytest.mark.parametrize(
    "dsn",
    [
        "host=localhost port=54322 dbname=test user=test",
        "host=127.0.0.1 port=5432 dbname=test user=test",
        "host=127.0.0.1 hostaddr=8.8.8.8 port=54322 dbname=test user=test",
        "host=127.0.0.1 port=54322 dbname=test user=test options=TOPSECRET",
        "service=production",
        "host=127.0.0.1,8.8.8.8 port=54322 dbname=test user=test",
    ],
)
def test_database_endpoint_guard(dsn: str) -> None:
    with pytest.raises(DoctorError):
        validate_database_dsn(dsn, [54322])


def test_database_pins_hostaddr() -> None:
    assert "hostaddr=127.0.0.1" in validate_database_dsn(
        "host=127.0.0.1 port=54322 dbname=test user=test", [54322]
    )


def test_oversized_input_is_rejected_before_parsing(tmp_path: Path) -> None:
    path = tmp_path / "event.json"
    path.write_bytes(b"TOPSECRET" * 10000)
    with pytest.raises(DoctorError) as exc:
        load_event(path)
    assert "TOPSECRET" not in str(exc.value)


def test_init_validate_and_secret_free_cli(tmp_path: Path) -> None:
    runner = CliRunner()
    assert runner.invoke(app, ["init", "--directory", str(tmp_path)]).exit_code == 0
    assert runner.invoke(app, ["init", "--directory", str(tmp_path)]).exit_code == 3
    assert load_scenario(tmp_path / "documents.yaml").identity.type == "authenticated"
    event = tmp_path / "event.json"
    event.write_text(json.dumps({**EVENT, "Authorization": "Bearer TOPSECRET"}))
    result = runner.invoke(app, ["validate", str(event), "--format", "json"])
    assert result.exit_code == 3
    assert "TOPSECRET" not in result.stdout
    assert json.loads(result.stdout)["error"]["code"] == "INVALID_EVENT"


@pytest.mark.parametrize(
    "fragment",
    [
        "request: {method: POST, resource: documents}",
        "request: {method: GET, resource: ../rpc/delete}",
        "shell: TOPSECRET",
        "identity: {type: authenticated, token_env: BAD-NAME}",
        "filters: {id: {eq: 1, neq: 2}}",
        "filters: {limit: {eq: 99999}}",
        "request: {resource: rpc}",
        "version: 1\nversion: 2",
        "name: &alias safe\nexpect: *alias",
        "name: !!python/object/apply:os.system [TOPSECRET]",
    ],
)
def test_scenario_rejects_unsafe_yaml(tmp_path: Path, fragment: str) -> None:
    path = tmp_path / "scenario.yaml"
    path.write_text(
        "version: 1\nname: safe\nrequest: {resource: documents}\nexpect: {status: 200}\n" + fragment
    )
    with pytest.raises(DoctorError) as exc:
        load_scenario(path)
    assert "TOPSECRET" not in str(exc.value)
