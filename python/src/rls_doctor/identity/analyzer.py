"""Observations and hypotheses are separate from assertion outcomes."""

from rls_doctor.core.models import DiagnosticEvent


def analyze_event(event: DiagnosticEvent, expected_role: str | None = None) -> list[dict[str, str]]:
    if event.response.status is not None:
        code = "HTTP_OBSERVED"
        summary = "HTTP metadata was captured; header presence does not prove identity."
    elif event.response.error_kind == "network":
        code = "NETWORK_FAILURE_OBSERVED"
        summary = "The SDK classified a network failure without an HTTP status."
    else:
        code = "HTTP_STATUS_UNAVAILABLE"
        summary = "No HTTP status was captured; the failure type is unknown."
    facts = [
        {
            "code": code,
            "evidence": "OBSERVED",
            "summary": summary,
        }
    ]
    if event.context.authorization_present:
        facts.append(
            {
                "code": "AUTHORIZATION_CONTEXT_UNVERIFIED",
                "evidence": "UNVERIFIED",
                "summary": (
                    "An authorization header was present; identity and executed role are unknown."
                ),
            }
        )
    if expected_role == "authenticated" and not event.context.authorization_present:
        facts.append(
            {
                "code": "MISSING_EXPECTED_AUTH",
                "evidence": "OBSERVED",
                "summary": "Expected user authorization header was absent on the captured request.",
            }
        )
    if event.response.status == 200 and event.response.row_count == 0:
        facts.append(
            {
                "code": "EMPTY_RESULT_AMBIGUOUS",
                "evidence": "UNVERIFIED",
                "summary": "Zero rows may reflect filters, missing data or RLS; cause is unknown.",
            }
        )
    auth_checks = {
        "verified_user": (
            "AUTH_USER_VERIFIED",
            "OBSERVED",
            (
                "Supabase Auth accepted a user session in the opt-in check; no "
                "user ID was retained and PostgreSQL role remains unverified."
            ),
        ),
        "rejected": (
            "AUTH_USER_REJECTED",
            "OBSERVED",
            "Supabase Auth rejected authorization in the opt-in check.",
        ),
        "unavailable": (
            "AUTH_CHECK_UNAVAILABLE",
            "UNVERIFIED",
            "The opt-in Auth check could not establish a user session.",
        ),
    }
    if event.auth_check in auth_checks:
        code, evidence, summary = auth_checks[event.auth_check]
        facts.append({"code": code, "evidence": evidence, "summary": summary})
    return facts
