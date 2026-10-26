import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from rls_doctor.cli.main import app
from rls_doctor.core.errors import DoctorError
from rls_doctor.core.models import parse_event
from rls_doctor.core.profiles import DatabaseProfile, api_origin, load_profile, save_profile
from rls_doctor.reports.database import validate_capture_table
from rls_doctor.reports.investigation import investigate


def profile() -> DatabaseProfile:
    return DatabaseProfile(
        project_id=str(uuid4()),
        host="db.example.com",
        port=5432,
        database="postgres",
        user="reader",
        table="public.documents",
        role="authenticated",
        api_origin="https://app.example.com",
    )


def bound_event(p: DatabaseProfile) -> dict[str, Any]:
    return {
        "schema_version": "1.1",
        "event_id": str(uuid4()),
        "timestamp": "2026-10-26T00:00:00Z",
        "duration_ms": 1,
        "request": {
            "method": "GET",
            "api": "rest",
            "resource": "documents",
            "filters": [],
            "schema": "public",
            "columns": ["id", "owner_id"],
        },
        "response": {"status": 200, "row_count": 0, "error_kind": None},
        "context": {"authorization_present": True, "apikey_present": True},
        "binding": {"project_id": p.project_id, "origin_sha256": p.origin_sha256},
        "auth_check": "verified_user",
    }


def test_profile_roundtrip_has_no_secret_and_refuses_overwrite(tmp_path: Path) -> None:
    p = profile()
    path = tmp_path / "project.json"
    save_profile(p, path)
    assert load_profile(path) == p
    with pytest.raises(DoctorError):
        save_profile(p, path)
    raw = json.loads(path.read_text())
    assert not ({"password", "dsn", "token"} & raw.keys())
    raw["password"] = "PRIVATE"
    path.unlink()
    path.write_text(json.dumps(raw))
    with pytest.raises(DoctorError) as e:
        load_profile(path)
    assert "PRIVATE" not in str(e.value)


@pytest.mark.parametrize("field,value", [("project_id", str(uuid4())), ("origin_sha256", "0" * 64)])
def test_event_binding_mismatch_rejected(field: str, value: str) -> None:
    p = profile()
    data = bound_event(p)
    data["binding"][field] = value
    with pytest.raises(DoctorError) as e:
        validate_capture_table(parse_event(data), p.table, p)
    assert e.value.code == "EVENT_PROJECT_MISMATCH"


def test_bound_schema_and_profile_required() -> None:
    p = profile()
    event = parse_event(bound_event(p))
    with pytest.raises(DoctorError):
        validate_capture_table(event, p.table)
    with pytest.raises(DoctorError):
        validate_capture_table(event, "private.documents", p)
    validate_capture_table(event, p.table, p)


@pytest.mark.parametrize(
    "value",
    [
        "http://example.com",
        "https://user:PRIVATE@example.com",
        "https://example.com/?token=PRIVATE",
    ],
)
def test_profile_rejects_secret_or_insecure_origin(value: str) -> None:
    with pytest.raises(DoctorError) as e:
        api_origin(value)
    assert "PRIVATE" not in str(e.value)


def test_profile_rejects_other_database_before_inspection() -> None:
    p = profile()
    with pytest.raises(DoctorError):
        p.check_connection(
            "host=db.example.com port=5432 dbname=other user=reader password=PRIVATE"
        )


def test_guided_connect_saves_profile_only_after_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rls_doctor.cli.project as wizard

    monkeypatch.setenv("RLS_DOCTOR_DATABASE_URL", "PRIVATE")
    monkeypatch.setattr(
        wizard,
        "inspection_dsn",
        lambda *a, **kw: (
            "host=db.example.com port=5432 dbname=postgres user=reader password=PRIVATE"
        ),
    )
    monkeypatch.setattr(
        wizard,
        "discover_database",
        lambda *a: {
            "tables": [{"schema": "public", "name": "documents"}],
            "roles": [{"name": "authenticated"}],
            "truncated": False,
        },
    )
    monkeypatch.setattr(
        wizard, "inspect_table", lambda *a: {"policies": [], "conclusions": [], "limitations": []}
    )
    path = tmp_path / "profile.json"
    result = CliRunner().invoke(
        app,
        ["connect", "--profile", str(path), "--language", "ru"],
        input="db.example.com\ny\n1\n1\nhttps://app.example.com\n",
    )
    assert result.exit_code == 0, result.output
    assert load_profile(path).table == "public.documents"
    assert "PRIVATE" not in result.output + path.read_text()


def test_connect_cancellation_never_resolves_dns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rls_doctor.cli.project as wizard

    monkeypatch.setattr(wizard, "inspection_dsn", lambda *a, **kw: pytest.fail("No connection"))
    path = tmp_path / "profile.json"
    result = CliRunner().invoke(
        app, ["connect", "--profile", str(path)], input="db.example.com\nn\n"
    )
    assert result.exit_code == 3
    assert not path.exists()


def test_investigation_separates_configuration_auth_and_empty_result() -> None:
    p = profile()
    event = parse_event(bound_event(p))
    report = investigate(
        {
            "linkage": {"configuration_matches": True},
            "conclusions": [{"code": "SELECT_PRIVILEGE_MISSING"}],
            "policies": [
                {
                    "applies_to_role": True,
                    "command": "SELECT",
                    "condition_shapes": [
                        {"scope": "USING", "shape": "AUTH_UID_EQUALS_COLUMN", "column": "owner_id"}
                    ],
                }
            ],
        },
        event,
    )
    codes = {s["code"]: s["state"] for s in report["investigation"]}
    assert codes["ACCESS_CONFIGURATION_BLOCKER"] == "ESTABLISHED"
    assert codes["REQUEST_AUTHORIZATION"] == "CHECKED"
    assert codes["OWNER_CONDITION"] == "NEEDS_EVIDENCE"
    assert codes["EMPTY_RESULT"] == "NEEDS_EVIDENCE"
    assert report["diagnosis_id"] and report["diagnosed_at"] != event.timestamp


def test_schema_11_is_shared_and_strict() -> None:
    root = Path(__file__).resolve().parents[3]
    assert (root / "schemas/diagnostic-event-v1.1.schema.json").read_bytes() == (
        root / "python/src/rls_doctor/schemas/diagnostic-event-v1.1.schema.json"
    ).read_bytes()
    p = profile()
    data = bound_event(p)
    data["binding"]["token"] = "PRIVATE"
    with pytest.raises(DoctorError) as e:
        parse_event(data)
    assert "PRIVATE" not in str(e.value)


@pytest.mark.parametrize(
    "origin,canonical",
    [
        ("https://EXAMPLE.com:443/", "https://example.com"),
        ("http://127.0.0.1:80", "http://127.0.0.1"),
    ],
)
def test_profile_origin_matches_javascript_url_normalization(origin: str, canonical: str) -> None:
    assert api_origin(origin) == canonical


def test_profile_reuse_only_prompts_for_hidden_password(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rls_doctor.cli.main as cli

    p = profile()
    path = tmp_path / "project.json"
    save_profile(p, path)
    monkeypatch.delenv("RLS_DOCTOR_DATABASE_URL", raising=False)

    def checked(raw: str, host: str, **kwargs: Any) -> str:
        assert "PRIVATE_PASSWORD" in raw
        assert host == p.host
        return raw

    monkeypatch.setattr(cli, "inspection_dsn", checked)
    monkeypatch.setattr(
        cli, "inspect_table", lambda *a: {"policies": [], "conclusions": [], "limitations": []}
    )
    result = CliRunner().invoke(
        app, ["diagnose", "--profile", str(path), "--approve-read-only"], input="PRIVATE_PASSWORD\n"
    )
    assert result.exit_code == 2
    assert "PRIVATE_PASSWORD" not in result.stdout + path.read_text()
    assert "connection string" not in result.stdout.lower()


@pytest.mark.parametrize("data_answer", ["2", "3"])
def test_follow_up_never_promotes_operator_statement_to_proof(data_answer: str) -> None:
    import typer

    from rls_doctor.cli.project import follow_up

    menu = typer.Typer()
    results: list[dict[str, Any]] = []

    @menu.command()
    def run() -> None:
        results.append(follow_up({"result": "UNKNOWN", "investigation": []}, "en"))

    result = CliRunner().invoke(menu, [], input=f"{data_answer}\n3\n3\n")
    assert result.exit_code == 0
    assert results[0]["result"] == "UNKNOWN"
    assert results[0]["operator_checks"]["evidence"] == "UNVERIFIED"
    assert "row exists" in results[0]["investigation"][-1]["en"]


@pytest.mark.parametrize(
    "restrictive,other_true,denied",
    [(True, True, True), (False, True, False), (False, False, True)],
)
def test_constant_policy_composition_does_not_confuse_or_and(
    restrictive: bool, other_true: bool, denied: bool
) -> None:
    policies = [
        {
            "applies_to_role": True,
            "command": "SELECT",
            "permissive": not restrictive,
            "condition_shapes": [{"scope": "USING", "shape": "ALWAYS_FALSE"}],
        }
    ]
    if other_true:
        policies.append(
            {
                "applies_to_role": True,
                "command": "SELECT",
                "permissive": True,
                "condition_shapes": [{"scope": "USING", "shape": "ALWAYS_TRUE"}],
            }
        )
    report = investigate(
        {"conclusions": [], "table": {"rls_applies_to_requested_role": True}, "policies": policies}
    )
    assert ("RLS_CONSTANT_DENIAL" in report["configuration_blockers"]) is denied


def test_profile_cannot_silently_weaken_tls() -> None:
    p = profile()
    with pytest.raises(DoctorError):
        p.check_connection(
            "host=db.example.com port=5432 dbname=postgres user=reader sslmode=disable"
        )


@pytest.mark.parametrize("allow", [False, True])
def test_bound_projection_is_compared_with_selected_role_column_grants(allow: bool) -> None:
    p = profile()
    event = parse_event(bound_event(p))
    report = investigate(
        {
            "linkage": {"configuration_matches": True},
            "conclusions": [],
            "privileges": {
                "columns": [{"name": "id", "select": True}, {"name": "owner_id", "select": allow}]
            },
        },
        event,
    )
    assert ("REQUESTED_COLUMN_SELECT_MISSING" in report["configuration_blockers"]) is (not allow)
