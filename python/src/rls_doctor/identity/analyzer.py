"""Observations and hypotheses are separate from assertion outcomes."""

from rls_doctor.core.models import DiagnosticEvent


def analyze_event(event: DiagnosticEvent, expected_role: str | None = None) -> list[dict[str, str]]:
    facts = [
        {
            "code": "HTTP_OBSERVED",
            "evidence": "OBSERVED",
            "summary": "HTTP metadata was captured; header presence does not prove identity.",
        }
    ]
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
    return facts
