"""Explicit numeric-loopback allowlists; no DNS, redirects or ambient proxies."""

import ipaddress
import os
import tomllib
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from psycopg.conninfo import conninfo_to_dict, make_conninfo
from pydantic import Field, ValidationError, model_validator

from rls_doctor.core.errors import DoctorError
from rls_doctor.core.io import read_document
from rls_doctor.core.models import Identifier, StrictModel

EnvName = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{0,95}$")]


def validate_local_url(url: str, ports: list[int]) -> str:
    try:
        parts = urlsplit(url)
        if (
            parts.scheme != "http"
            or parts.username is not None
            or parts.password is not None
            or parts.path not in ("", "/")
            or parts.query
            or parts.fragment
            or parts.port not in ports
            or not ipaddress.ip_address(parts.hostname or "").is_loopback
            or "%" in url
            or "\\" in url
        ):
            raise ValueError
    except ValueError:
        raise DoctorError(
            "UNSAFE_ENDPOINT", "Use an explicitly allowed numeric loopback HTTP origin."
        ) from None
    return url.rstrip("/")


def validate_database_dsn(dsn: str, allowed_ports: list[int]) -> str:
    """Pin libpq to a numeric local address and reject service/options overrides."""
    try:
        parsed = conninfo_to_dict(dsn)
        values = {key: str(value) for key, value in parsed.items() if value is not None}
        if set(values) - {
            "host",
            "hostaddr",
            "port",
            "dbname",
            "user",
            "password",
            "connect_timeout",
        }:
            raise ValueError
        host = values.get("host", "")
        if not ipaddress.ip_address(host).is_loopback:
            raise ValueError
        if int(values.get("port", "0")) not in allowed_ports:
            raise ValueError
        if (
            values.get("hostaddr", host) != host
            or not values.get("dbname")
            or not values.get("user")
        ):
            raise ValueError
        values["hostaddr"] = host
        values["connect_timeout"] = "5"
        return make_conninfo(**values)
    except Exception:
        raise DoctorError(
            "UNSAFE_DATABASE", "Database DSN must name an approved numeric loopback host and port."
        ) from None


class LocalEnvironment(StrictModel):
    approved_local: bool = False
    api_url: str = "http://127.0.0.1:54321"
    allowed_api_ports: list[int] = Field(
        default_factory=lambda: [54321], min_length=1, max_length=8
    )
    allowed_db_ports: list[int] = Field(default_factory=lambda: [54322], min_length=1, max_length=8)
    resources: list[Identifier] = Field(
        default_factory=lambda: ["documents"], min_length=1, max_length=64
    )
    anon_key_env: EnvName = "RLS_DOCTOR_LOCAL_ANON_KEY"
    database_url_env: EnvName = "RLS_DOCTOR_DATABASE_URL"
    jwt_secret_env: EnvName = "RLS_DOCTOR_LOCAL_JWT_SECRET"
    jwt_audience: Literal["authenticated"] = "authenticated"
    confirm_identity: bool = True

    @model_validator(mode="after")
    def check_ports(self) -> "LocalEnvironment":
        if any(not 1 <= p <= 65535 for p in self.allowed_api_ports + self.allowed_db_ports):
            raise ValueError("Invalid local port")
        validate_local_url(self.api_url, self.allowed_api_ports)
        return self

    def origin(self) -> str:
        if not self.approved_local:
            raise DoctorError(
                "LOCAL_APPROVAL_REQUIRED",
                "Set approved_local=true only for a disposable local stack.",
            )
        return validate_local_url(self.api_url, self.allowed_api_ports)

    def database_dsn(self) -> str:
        self.origin()
        return validate_database_dsn(read_secret(self.database_url_env), self.allowed_db_ports)


class ProjectConfig(StrictModel):
    version: Literal[1] = 1
    environment: LocalEnvironment = Field(default_factory=LocalEnvironment)


def read_secret(name: str) -> str:
    value = os.environ.get(name)
    if not value or len(value) > 16384 or any(c in value for c in "\r\n\x00"):
        raise DoctorError(
            "MISSING_CREDENTIAL",
            "A required local-test credential environment variable is missing or invalid.",
        )
    return value


def load_config(path: Path) -> ProjectConfig:
    try:
        return ProjectConfig.model_validate(tomllib.loads(read_document(path)))
    except DoctorError:
        raise
    except (OSError, ValueError, ValidationError):
        raise DoctorError(
            "INVALID_CONFIG", "Cannot read a valid local project TOML configuration."
        ) from None
