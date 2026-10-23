"""Compare explicit expectations without copying test rows into reports."""

from typing import Any

from rls_doctor.replay.scenarios import Expectations


def error_class(status: int, payload: object) -> str:
    if status == 401:
        return "authorization"
    if isinstance(payload, dict) and payload.get("code") == "42501":
        return "permission"
    return "http" if status >= 400 else "none"


def compare(expect: Expectations, status: int, payload: object) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    def add(name: str, observed: object, expected: object, known: bool = True) -> None:
        checks.append(
            {
                "check": name,
                "result": ("PASS" if observed == expected else "FAIL") if known else "UNKNOWN",
                "expected": expected,
                "observed": observed if known else None,
            }
        )

    add("http_status", status, expect.status)
    rows = (
        payload if isinstance(payload, list) and all(isinstance(r, dict) for r in payload) else None
    )
    if expect.row_count is not None:
        add(
            "row_count", len(rows) if rows is not None else None, expect.row_count, rows is not None
        )
    for kind, rules in (("contains", expect.contains), ("excludes", expect.excludes)):
        for index, rule in enumerate(rules):
            known = rows is not None and all(rule.column in row for row in rows)
            present = rows is not None and any(
                type(row.get(rule.column)) is type(rule.value)
                and row.get(rule.column) == rule.value
                for row in rows
            )
            add(f"{kind}_{index + 1}", present, kind == "contains", known)
    if expect.error_class is not None:
        add("error_class", error_class(status, payload), expect.error_class)
    return checks


def aggregate(checks: list[dict[str, Any]]) -> str:
    results = {c["result"] for c in checks}
    return next((r for r in ("ERROR", "FAIL", "UNKNOWN") if r in results), "PASS")
