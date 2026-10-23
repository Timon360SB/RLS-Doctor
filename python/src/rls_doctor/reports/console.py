"""Human-readable output; arbitrary exception strings are never rendered."""

import json
from typing import Any

from rich.console import Console


def render(report: dict[str, Any], format: str = "console") -> None:
    console = Console(highlight=False, markup=False)
    if format == "json":
        console.print(json.dumps(report, indent=2, ensure_ascii=True), soft_wrap=True)
        return
    console.print("RLS DOCTOR v0.1.0")
    console.print(f"Result: {report.get('result', 'UNKNOWN')}")
    for field in ("resource", "method"):
        if field in report:
            console.print(f"{field}: {report[field]}")
    if "identity" in report:
        console.print("Identity: " + json.dumps(report["identity"]))
    if report.get("http"):
        console.print("HTTP: " + json.dumps(report["http"]))
    for check in report.get("checks", []):
        console.print(f"  {check['result']}: {check['check']}")
        if "expected" in check:
            console.print(f"    expected: {check['expected']}; observed: {check['observed']}")
    for fact in report.get("findings", report.get("conclusions", [])):
        console.print(f"  {fact['evidence']}: {fact['summary']}")
    if report.get("inspector"):
        console.print("Postgres inspector: " + json.dumps(report["inspector"], indent=2))
    elif "policies" in report:
        console.print(json.dumps(report, indent=2))
    for item in report.get("recommendations", []):
        console.print("Next: " + item)
    for item in report.get("limitations", []):
        console.print("Limit: " + item)
    if "error" in report:
        console.print("Error: " + str(report["error"]["message"]))
