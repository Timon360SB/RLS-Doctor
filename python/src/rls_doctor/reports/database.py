"""Combine capture evidence and catalogs without inventing a runtime link."""

from typing import Any

from rls_doctor.core.errors import DoctorError
from rls_doctor.core.models import DiagnosticEvent
from rls_doctor.core.profiles import DatabaseProfile
from rls_doctor.identity.analyzer import analyze_event


def validate_capture_table(
    event: DiagnosticEvent, table: str, profile: DatabaseProfile | None = None
) -> None:
    if event.request.resource != table.split(".")[-1]:
        raise DoctorError(
            "EVENT_RESOURCE_MISMATCH",
            "Captured resource does not match the selected table; choose the intended event/table.",
        )

    if event.schema_version == "1.1":
        if profile is None:
            raise DoctorError(
                "PROJECT_PROFILE_REQUIRED", "Bound events require their saved project profile."
            )
        if (
            event.binding is None
            or event.binding.project_id != profile.project_id
            or event.binding.origin_sha256 != profile.origin_sha256
            or event.request.schema_name != table.split(".")[0]
        ):
            raise DoctorError(
                "EVENT_PROJECT_MISMATCH",
                "Event project/API origin/schema does not match the selected profile and table.",
            )


def database_capture_report(
    event: DiagnosticEvent,
    table: str,
    role: str,
    inspector: dict[str, Any],
    profile: DatabaseProfile | None = None,
) -> dict[str, Any]:
    """Matching resource names are necessary, but do not prove database/schema identity."""
    validate_capture_table(event, table, profile)
    return {
        "report_version": "1.0",
        "analysis_mode": "existing_database_and_capture",
        "result": "UNKNOWN",
        "resource": table,
        "event_id": event.event_id,
        "timestamp": event.timestamp,
        "captured_at": event.timestamp,
        "method": event.request.method,
        "identity": {
            "expected_role": role,
            "confirmed_role": None,
            "authorization_present": event.context.authorization_present,
            "auth_check": event.auth_check,
            "apikey_present": event.context.apikey_present,
        },
        "http": event.response.model_dump(),
        "request_metadata": {
            "filters": [item.model_dump() for item in event.request.filters],
            "schema": event.request.schema_name,
            "columns": event.request.columns,
        },
        "linkage": {
            "resource_name_matches": True,
            "configuration_matches": event.schema_version == "1.1" and profile is not None,
            "database_schema_and_role_confirmed": False,
            "evidence": "UNVERIFIED",
        },
        "inspector": inspector,
        "findings": [
            *analyze_event(event, role),
            {
                "code": "CAPTURE_DATABASE_LINK_UNVERIFIED",
                "evidence": "UNVERIFIED",
                "summary": (
                    "Project configuration matches; actual database routing "
                    "and executed role remain unverified."
                    if event.schema_version == "1.1"
                    else "Resource names match, but database/schema/role linkage "
                    "remains unverified."
                ),
            },
        ],
        "recommendations": [
            "Confirm the application's database endpoint, exposed schema and executed role "
            "independently; matching resource names alone do not establish the link.",
            (
                "Compare the captured filter columns/operators and HTTP result "
                "with catalog findings. Filter values and customer rows are not "
                "inspected; only supported policy shapes are classified."
            ),
        ],
        "limitations": [
            "The saved HTTP metadata describes an earlier application request; "
            "no request was replayed.",
            "No customer rows, raw policy expressions, database identity probes "
            "or application queries were read/run by this diagnosis.",
            "Catalogs describe the time of inspection, "
            "not necessarily the time of the captured request.",
            "Captured row_count is Content-Range metadata, "
            "not parsed response rows or proof of RLS.",
        ],
    }
