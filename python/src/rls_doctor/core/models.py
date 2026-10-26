"""Strict event model backed by the packaged canonical JSON Schema."""

import json
import re
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from typing import Annotated, Literal

from jsonschema import Draft202012Validator, FormatChecker
from pydantic import BaseModel, ConfigDict, Field

from rls_doctor.core.errors import DoctorError
from rls_doctor.core.io import read_document

Identifier = Annotated[str, Field(pattern=r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")]
Evidence = Literal["OBSERVED", "INFERRED", "UNVERIFIED"]
Outcome = Literal["PASS", "FAIL", "UNKNOWN", "ERROR"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


class FilterMetadata(StrictModel):
    column: Identifier
    operator: Literal["eq", "neq", "gt", "gte", "lt", "lte", "is"]


class RequestMetadata(StrictModel):
    method: Literal["GET"]
    api: Literal["rest"]
    resource: Identifier
    filters: list[FilterMetadata] = Field(max_length=64)
    schema_name: Identifier | None = Field(default=None, alias="schema")
    columns: list[Identifier] | None = Field(default=None, max_length=64)


class ResponseMetadata(StrictModel):
    status: int | None = Field(ge=100, le=599)
    row_count: int | None = Field(ge=0, le=9007199254740991)
    error_kind: Literal["http", "network"] | None


class ContextMetadata(StrictModel):
    authorization_present: bool
    apikey_present: bool


class ProjectBinding(StrictModel):
    project_id: str
    origin_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class DiagnosticEvent(StrictModel):
    schema_version: Literal["1.0", "1.1"]
    event_id: str
    timestamp: str
    request: RequestMetadata
    response: ResponseMetadata
    context: ContextMetadata
    duration_ms: int = Field(ge=0, le=86400000)
    binding: ProjectBinding | None = None
    auth_check: Literal[
        "not_checked", "no_authorization", "verified_user", "rejected", "unavailable"
    ] = "not_checked"


def event_validator(version: str = "1.0") -> Draft202012Validator:
    if version not in {"1.0", "1.1"}:
        raise ValueError("Unsupported event version")
    filename = (
        "diagnostic-event-v1.schema.json"
        if version == "1.0"
        else "diagnostic-event-v1.1.schema.json"
    )
    schema = json.loads(files("rls_doctor.schemas").joinpath(filename).read_text())
    checker = FormatChecker()

    @checker.checks("date-time", raises=(ValueError, TypeError))
    def valid_timestamp(value: object) -> bool:
        if not isinstance(value, str):
            return True
        return (
            bool(
                re.fullmatch(
                    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", value
                )
            )
            and datetime.fromisoformat(value).tzinfo is not None
        )

    return Draft202012Validator(schema, format_checker=checker)


def parse_event(data: object) -> DiagnosticEvent:
    """Reject incompatible or extra fields without echoing their values."""
    try:
        version = str(data.get("schema_version")) if isinstance(data, dict) else ""
        event_validator(version).validate(data)
        return DiagnosticEvent.model_validate(data)
    except Exception:
        # JSON Schema errors contain arbitrary input values; never format them.
        raise DoctorError(
            "INVALID_EVENT", "Event does not satisfy a supported diagnostic schema (1.0 or 1.1)."
        ) from None


def load_event(path: Path) -> DiagnosticEvent:
    try:
        data = json.loads(read_document(path))
    except (OSError, ValueError):
        raise DoctorError("INVALID_EVENT", "Cannot read a valid event (maximum 64 KiB).") from None
    return parse_event(data)
