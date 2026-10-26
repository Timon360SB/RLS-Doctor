"""Network I/O is limited to approved local GET requests and a fixture identity probe."""

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

import httpx

from rls_doctor.core.config import ProjectConfig
from rls_doctor.core.errors import DoctorError
from rls_doctor.core.models import DiagnosticEvent
from rls_doctor.identity.analyzer import analyze_event
from rls_doctor.identity.validation import bounded_json, bounded_response, local_headers
from rls_doctor.postgres.inspector import InspectorError, inspect_table
from rls_doctor.replay.assertions import aggregate, compare, error_class
from rls_doctor.replay.scenarios import Scenario
from rls_doctor.reports.operational import database_error_details


def complete_result(count: int | None, content_range: str | None) -> bool:
    """Only a consistent full page establishes absence or total row expectations."""
    if count is None:
        return False
    if count == 0:
        return content_range == "*/0"
    match = re.fullmatch(r"0-([0-9]+)/([0-9]+)", content_range or "")
    return match is not None and int(match[1]) == count - 1 and int(match[2]) == count


def replay(
    scenario: Scenario,
    config: ProjectConfig,
    event: DiagnosticEvent | None = None,
    *,
    inspect: bool = False,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    env = config.environment
    origin = env.origin()
    resource = scenario.request.resource
    if resource not in env.resources:
        raise DoctorError(
            "RESOURCE_NOT_ALLOWED",
            "Scenario resource is not in the approved local resource allowlist.",
        )
    if event is not None and event.request.resource != resource:
        raise DoctorError("EVENT_MISMATCH", "Event and scenario refer to different resources.")
    expected_role = scenario.identity.expected_role or scenario.identity.type
    report: dict[str, Any] = {
        "report_version": "1.0",
        "run_id": str(uuid4()),
        "timestamp": datetime.now(UTC).isoformat(),
        "resource": f"{scenario.request.schema_name}.{resource}",
        "method": "GET",
        "identity": {
            "declared_role": scenario.identity.type,
            "expected_role": expected_role,
            "verified_claim_role": None,
            "confirmed_role": None,
        },
        "http": None,
        "inspector": None,
        "checks": [],
        "findings": [],
        "recommendations": [
            "Verify fixture ownership, filters and applicable policies in the local stack."
        ],
        "limitations": [
            "A captured event cannot recreate original values.",
            "No arbitrary SQL predicate evaluation or security certification.",
            "Local loopback can still be forwarded; verify the actual stack.",
        ],
    }
    if event is not None:
        report["event_id"] = event.event_id
        report["captured_at"] = event.timestamp
        report["findings"].extend(analyze_event(event, expected_role))
    with httpx.Client(
        timeout=5, follow_redirects=False, trust_env=False, transport=transport
    ) as client:
        headers, claims = local_headers(env, client, scenario.identity.token_env)
        headers["Accept-Profile"] = scenario.request.schema_name
        if claims is not None:
            report["identity"]["verified_claim_role"] = claims["role"]
        if env.confirm_identity:
            probe_status, probe = bounded_json(
                client,
                origin + "/rest/v1/rpc/rls_doctor_identity",
                {**headers, "Accept-Profile": "public"},
            )
            if (
                probe_status == 200
                and isinstance(probe, dict)
                and probe.get("role") in ("anon", "authenticated")
            ):
                actual_role = probe["role"]
                if claims is not None and probe.get("uid") != claims.get("sub"):
                    raise DoctorError(
                        "IDENTITY_MISMATCH",
                        "Trusted local identity probe disagreed with the verified test subject.",
                    )
                report["identity"]["confirmed_role"] = actual_role
                report["findings"].append(
                    {
                        "code": "LOCAL_ROLE_CONFIRMED",
                        "evidence": "OBSERVED",
                        "summary": "Trusted fixture probe confirmed the local database role.",
                    }
                )
            else:
                report["findings"].append(
                    {
                        "code": "ROLE_UNCONFIRMED",
                        "evidence": "UNVERIFIED",
                        "summary": "Local identity probe unavailable; database role is unknown.",
                    }
                )
        params = {
            "select": ",".join(scenario.request.columns) if scenario.request.columns else "*",
            "limit": "1000",
        }
        params.update({column: rule.parameter() for column, rule in scenario.filters.items()})
        headers["Prefer"] = "count=exact"
        status, payload, content_range = bounded_response(
            client, origin + "/rest/v1/" + resource + "?" + urlencode(params), headers
        )
        count = (
            len(payload)
            if isinstance(payload, list) and all(isinstance(row, dict) for row in payload)
            else None
        )
        code = payload.get("code") if isinstance(payload, dict) else None
        report["http"] = {
            "status": status,
            "row_count": count,
            "error_class": error_class(status, payload),
            "error_code": code
            if isinstance(code, str) and re.fullmatch(r"(?:[0-9A-Z]{5}|PGRST[0-9]{3})", code)
            else None,
        }
        report["checks"] = compare(scenario.expect, status, payload)
        if 200 <= status < 300:
            complete = complete_result(count, content_range)
            if not complete:
                report["checks"].append({"check": "result_completeness", "result": "UNKNOWN"})
                report["limitations"].append(
                    "Response completeness could not be established from Content-Range."
                )
    confirmed = report["identity"]["confirmed_role"]
    if confirmed == "anon" and expected_role == "authenticated":
        report["findings"].append(
            {
                "code": "UNEXPECTED_ANONYMOUS_CONTEXT",
                "evidence": "OBSERVED",
                "summary": "The local request executed anonymously while a user role was expected.",
            }
        )
    report["checks"].append(
        {
            "check": "executed_role",
            "result": "UNKNOWN"
            if confirmed is None
            else ("PASS" if confirmed == expected_role else "FAIL"),
        }
    )
    if count == 0 and status == 200:
        report["findings"].append(
            {
                "code": "EMPTY_RESULT_AMBIGUOUS",
                "evidence": "UNVERIFIED",
                "summary": "Zero rows observed; filters, missing rows and RLS are possible causes.",
            }
        )
    if count is not None and count >= 1000:
        report["checks"].append({"check": "result_completeness", "result": "UNKNOWN"})
        report["limitations"].append(
            "Replay reached the 1000-row cap; full result size is unknown."
        )
    if inspect:
        try:
            report["inspector"] = inspect_table(
                env.database_dsn(),
                scenario.request.schema_name,
                resource,
                confirmed or scenario.identity.type,
            )
        except InspectorError as error:
            report["inspector"] = {"result": "ERROR", "error": database_error_details(error)}
            report["checks"].append({"check": "postgres_inspection", "result": "ERROR"})
    report["result"] = aggregate(report["checks"])
    return report
