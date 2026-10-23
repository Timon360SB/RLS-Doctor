"""Bounded safe YAML with a small, explicit PostgREST operator vocabulary."""

from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import Field, ValidationError, model_validator

from rls_doctor.core.config import EnvName
from rls_doctor.core.errors import DoctorError
from rls_doctor.core.io import read_document
from rls_doctor.core.models import Identifier, StrictModel

Scalar = str | int | bool | None


class ScenarioEnvironment(StrictModel):
    type: Literal["local_supabase"] = "local_supabase"


class ScenarioRequest(StrictModel):
    method: Literal["GET"] = "GET"
    resource: Identifier
    schema_name: Identifier = Field(default="public", alias="schema")
    columns: list[Identifier] | None = Field(default=None, min_length=1, max_length=64)


class Identity(StrictModel):
    type: Literal["anon", "authenticated"] = "anon"
    token_env: EnvName | None = None
    expected_role: Literal["anon", "authenticated"] | None = None

    @model_validator(mode="after")
    def validate_token_reference(self) -> "Identity":
        if (self.type == "authenticated") != (self.token_env is not None):
            raise ValueError("Authenticated identities require a token environment reference")
        return self


class Filter(StrictModel):
    eq: Scalar = None
    neq: Scalar = None
    gt: Scalar = None
    gte: Scalar = None
    lt: Scalar = None
    lte: Scalar = None
    is_: Literal["null", "true", "false"] | None = Field(default=None, alias="is")

    @model_validator(mode="after")
    def exactly_one(self) -> "Filter":
        if len(self.model_fields_set) != 1:
            raise ValueError("Exactly one filter operator is required")
        field = next(iter(self.model_fields_set))
        value = getattr(self, field)
        if (
            value is None
            or isinstance(value, str)
            and (len(value) > 256 or any(c in value for c in "\r\n\x00"))
        ):
            raise ValueError("Invalid filter value")
        return self

    def parameter(self) -> str:
        key = next(iter(self.model_fields_set))
        value = getattr(self, key)
        if isinstance(value, bool):
            value = str(value).lower()
        return f"{'is' if key == 'is_' else key}.{value}"


class RecordExpectation(StrictModel):
    column: Identifier
    value: Annotated[str, Field(max_length=256)] | int | bool


class Expectations(StrictModel):
    status: int = Field(default=200, ge=100, le=599)
    row_count: int | None = Field(default=None, ge=0, le=10000)
    contains: list[RecordExpectation] = Field(default_factory=list, max_length=64)
    excludes: list[RecordExpectation] = Field(default_factory=list, max_length=64)
    error_class: Literal["none", "authorization", "permission", "http"] | None = None


class Scenario(StrictModel):
    version: Literal[1]
    name: Annotated[str, Field(pattern=r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")]
    environment: ScenarioEnvironment = Field(default_factory=ScenarioEnvironment)
    request: ScenarioRequest
    identity: Identity = Field(default_factory=Identity)
    filters: dict[Identifier, Filter] = Field(default_factory=dict, max_length=32)
    expect: Expectations

    @model_validator(mode="after")
    def reject_reserved_parameters(self) -> "Scenario":
        if set(self.filters) & {"select", "limit", "offset", "order", "and", "or", "on_conflict"}:
            raise ValueError("Reserved PostgREST query parameters cannot be used as filters")
        if self.request.resource == "rpc":
            raise ValueError("User-authored RPC scenarios are unsupported")
        return self


class UniqueSafeLoader(yaml.SafeLoader):
    """Reject YAML aliases, duplicate keys, and hidden merged settings."""

    def compose_node(self, parent: yaml.Node | None, index: int) -> yaml.Node | None:
        if self.check_event(yaml.AliasEvent):
            raise ValueError("YAML aliases are unsupported")
        return super().compose_node(parent, index)

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[object, object]:
        result: dict[object, object] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in result or key == "<<":
                raise ValueError("Duplicate YAML keys are unsupported")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def load_scenario(path: Path) -> Scenario:
    try:
        data = yaml.load(read_document(path), Loader=UniqueSafeLoader)
        return Scenario.model_validate(data)
    except (OSError, ValueError, yaml.YAMLError, ValidationError, RecursionError, TypeError):
        raise DoctorError(
            "INVALID_SCENARIO", "Invalid scenario: use strict GET-only local YAML (maximum 64 KiB)."
        ) from None
