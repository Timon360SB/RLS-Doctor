"""Common generated-report metadata, separate from captured-request time."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def complete_report(report: dict[str, Any]) -> dict[str, Any]:
    """Enrich generated reports in place; never touch profile or event documents."""
    report.setdefault("report_version", "1.0")
    if "diagnosis_id" not in report:
        report["diagnosis_id"] = str(uuid4())
    if "diagnosed_at" not in report:
        report["diagnosed_at"] = datetime.now(UTC).isoformat()
    return report
