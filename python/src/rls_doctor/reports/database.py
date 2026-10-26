"""Combine capture evidence and catalogs without inventing a runtime link."""

from typing import Any

from rls_doctor.core.errors import DoctorError
from rls_doctor.core.models import DiagnosticEvent
from rls_doctor.identity.analyzer import analyze_event


def validate_capture_table(event: DiagnosticEvent, table: str) -> None:
    if event.request.resource != table.split(".")[-1]:
        raise DoctorError(
            "EVENT_RESOURCE_MISMATCH",
            "Captured resource does not match the selected table; choose the intended event/table.",
        )


def database_capture_report(
    event: DiagnosticEvent, table: str, role: str, inspector: dict[str, Any]
) -> dict[str, Any]:
    """Matching resource names are necessary, but do not prove database/schema identity."""
    validate_capture_table(event, table)
    return {
        "report_version": "1.0",
        "analysis_mode": "existing_database_and_capture",
        "result": "UNKNOWN",
        "resource": table,
        "event_id": event.event_id,
        "timestamp": event.timestamp,
        "method": event.request.method,
        "identity": {
            "expected_role": role,
            "confirmed_role": None,
            "authorization_present": event.context.authorization_present,
            "apikey_present": event.context.apikey_present,
        },
        "http": event.response.model_dump(),
        "request_metadata": {"filters": [item.model_dump() for item in event.request.filters]},
        "linkage": {
            "resource_name_matches": True,
            "database_schema_and_role_confirmed": False,
            "evidence": "UNVERIFIED",
        },
        "inspector": inspector,
        "findings": [
            *analyze_event(event, role),
            {
                "code": "CAPTURE_DATABASE_LINK_UNVERIFIED",
                "evidence": "UNVERIFIED",
                "summary": "Resource names match, but the event does not identify its database, "
                "schema or executed role. The selected catalogs are not a proven root cause.",
            },
        ],
        "recommendations": [
            "Confirm the application's database endpoint, exposed schema and executed role "
            "independently; matching resource names alone do not establish the link.",
            "Compare the captured filter columns/operators and HTTP result with catalog findings. "
            "Filter values, selected columns, policy predicates "
            "and customer rows are not inspected.",
        ],
        "limitations": [
            "The saved HTTP metadata describes an earlier application request; "
            "no request was replayed.",
            "No customer rows, policy expressions, identity probes "
            "or application queries were read/run.",
            "Catalogs describe the time of inspection, "
            "not necessarily the time of the captured request.",
            "Captured row_count is Content-Range metadata, "
            "not parsed response rows or proof of RLS.",
        ],
    }
