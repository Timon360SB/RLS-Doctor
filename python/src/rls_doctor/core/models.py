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


class ResponseMetadata(StrictModel):
    status: int | None = Field(ge=100, le=599)
    row_count: int | None = Field(ge=0, le=9007199254740991)
    error_kind: Literal["http", "network"] | None


class ContextMetadata(StrictModel):
    authorization_present: bool
    apikey_present: bool


class DiagnosticEvent(StrictModel):
    schema_version: Literal["1.0"]
    event_id: str
    timestamp: str
    request: RequestMetadata
    response: ResponseMetadata
    context: ContextMetadata
    duration_ms: int = Field(ge=0, le=86400000)


def event_validator() -> Draft202012Validator:
    schema = json.loads(
        files("rls_doctor.schemas").joinpath("diagnostic-event-v1.schema.json").read_text()
    )
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
        event_validator().validate(data)
        return DiagnosticEvent.model_validate(data)
    except Exception:
        # JSON Schema errors contain arbitrary input values; never format them.
        raise DoctorError("INVALID_EVENT", "Event does not satisfy diagnostic schema v1.") from None


def load_event(path: Path) -> DiagnosticEvent:
    try:
        data = json.loads(read_document(path))
    except (OSError, ValueError):
        raise DoctorError("INVALID_EVENT", "Cannot read a valid event (maximum 64 KiB).") from None
    return parse_event(data)
