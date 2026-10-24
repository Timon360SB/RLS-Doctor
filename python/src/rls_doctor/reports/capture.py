"""Offline capture reports describe metadata without claiming server-side identity."""

from typing import Any, Literal

from rls_doctor.core.models import DiagnosticEvent
from rls_doctor.identity.analyzer import analyze_event


def capture_report(
    event: DiagnosticEvent, expected_role: Literal["anon", "authenticated"] | None = None
) -> dict[str, Any]:
    """Capture metadata alone cannot establish replay outcomes or an RLS cause."""
    recommendations = [
        "Compare the captured resource and filter operators with the intended request.",
        "Use an explicit synthetic local replay and catalog inspection to test access behavior.",
    ]
    if expected_role == "authenticated" and not event.context.authorization_present:
        recommendations.insert(
            0, "Check whether the application supplies the intended user session to this request."
        )
    return {
        "report_version": "1.0",
        "analysis_mode": "capture_only",
        "result": "UNKNOWN",
        "event_id": event.event_id,
        "timestamp": event.timestamp,
        "resource": event.request.resource,
        "method": event.request.method,
        "identity": {
            "expected_role": expected_role,
            "authorization_present": event.context.authorization_present,
            "apikey_present": event.context.apikey_present,
            "confirmed_role": None,
        },
        "http": {
            "status": event.response.status,
            "row_count": event.response.row_count,
            "error_kind": event.response.error_kind,
        },
        "findings": analyze_event(event, expected_role),
        "recommendations": recommendations,
        "limitations": [
            "Offline metadata analysis: no network request, replay or database inspection ran.",
            "Header presence does not prove identity, token validity or the executed role.",
            "Row count comes from captured Content-Range metadata, never a parsed response body.",
            "This event alone cannot establish a root cause or application security conclusion.",
        ],
    }
