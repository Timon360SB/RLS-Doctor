"""Bounded non-secret project profiles; passwords are never serialized."""

import hashlib
import ipaddress
import json
import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from psycopg.conninfo import conninfo_to_dict, make_conninfo
from pydantic import Field, model_validator

from rls_doctor.core.errors import DoctorError
from rls_doctor.core.io import read_document
from rls_doctor.core.models import Identifier, StrictModel
from rls_doctor.reports.files import write_report


def api_origin(value: str) -> str:
    try:
        u = urlsplit(value)
        if u.username or u.password or u.path not in ("", "/") or u.query or u.fragment:
            raise ValueError
        if not u.hostname or not re.fullmatch(r"[A-Za-z0-9.:-]+", u.hostname):
            raise ValueError
        if u.scheme != "https":
            if u.scheme != "http" or not ipaddress.ip_address(u.hostname).is_loopback:
                raise ValueError
        port = u.port
        if port is not None and not 1 <= port <= 65535:
            raise ValueError
        host = u.hostname.lower()
        if ":" in host:
            host = "[" + ipaddress.ip_address(host).compressed + "]"
        suffix = (
            "" if port is None or (u.scheme, port) in {("https", 443), ("http", 80)} else f":{port}"
        )
        return f"{u.scheme}://{host}{suffix}"
    except Exception:
        raise DoctorError(
            "PROJECT_API_ORIGIN", "Use an HTTPS API origin without paths or secrets."
        ) from None


class DatabaseProfile(StrictModel):
    version: int = Field(default=1, ge=1, le=1)
    project_id: str
    host: str = Field(min_length=1, max_length=253, pattern=r"^[A-Za-z0-9.:-]+$")
    port: int = Field(ge=1, le=65535)
    database: Identifier
    user: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_.-]{0,127}$")
    table: str = Field(pattern=r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}\.[a-zA-Z_][a-zA-Z0-9_]{0,62}$")
    role: Identifier
    connection_env: str = Field(
        default="RLS_DOCTOR_DATABASE_URL", pattern=r"^[A-Z][A-Z0-9_]{0,95}$"
    )
    api_origin: str | None = None
    sslmode: Literal["disable", "verify-full"] = "verify-full"
    sslrootcert: str = Field(default="system", min_length=1, max_length=4096)

    @model_validator(mode="after")
    def validate_values(self) -> "DatabaseProfile":
        UUID(self.project_id)
        if self.api_origin is not None and api_origin(self.api_origin) != self.api_origin:
            raise ValueError("Non-canonical origin")
        return self

    @property
    def origin_sha256(self) -> str | None:
        return hashlib.sha256(self.api_origin.encode()).hexdigest() if self.api_origin else None

    def connection(self, password: str) -> str:
        return make_conninfo(
            host=self.host,
            port=self.port,
            dbname=self.database,
            user=self.user,
            password=password,
            sslmode=self.sslmode,
            **({"sslrootcert": self.sslrootcert} if self.sslmode == "verify-full" else {}),
        )

    def check_connection(self, dsn: str) -> None:
        values = conninfo_to_dict(dsn)
        expected = {
            "host": self.host,
            "port": str(self.port),
            "dbname": self.database,
            "user": self.user,
        }
        expected["sslmode"] = self.sslmode
        if self.sslmode == "verify-full":
            actual_ca = str(values.get("sslrootcert", "system"))
            saved_ca = self.sslrootcert
            if actual_ca != "system":
                actual_ca = str(Path(actual_ca).resolve())
            if saved_ca != "system":
                saved_ca = str(Path(saved_ca).resolve())
            if actual_ca != saved_ca:
                raise DoctorError(
                    "PROJECT_CONNECTION_MISMATCH",
                    "CA configuration differs from the saved project.",
                )
        if any(values.get(key) != value for key, value in expected.items()):
            raise DoctorError(
                "PROJECT_CONNECTION_MISMATCH",
                "Connection does not match the saved project endpoint/database/user.",
            )


def load_profile(path: Path) -> DatabaseProfile:
    try:
        return DatabaseProfile.model_validate_json(read_document(path))
    except Exception:
        raise DoctorError(
            "PROJECT_PROFILE_INVALID", "Cannot read a valid non-secret project profile."
        ) from None


def save_profile(profile: DatabaseProfile, path: Path) -> None:
    # Round-trip strict validation, then atomic no-overwrite publication.
    safe = DatabaseProfile.model_validate_json(profile.model_dump_json())
    write_report(json.loads(safe.model_dump_json()), path)
