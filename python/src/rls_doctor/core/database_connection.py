"""Explicit existing-database catalog connection, separate from local replay."""

import ipaddress
import os
import re
import socket
from pathlib import Path

from psycopg.conninfo import conninfo_to_dict, make_conninfo

from rls_doctor.core.errors import DoctorError


def validate_database_host(host: str) -> None:
    """Reject URI/credential strings before a host is echoed for approval; no DNS."""
    valid = bool(host) and len(host) <= 253 and "%" not in host
    if valid:
        try:
            ipaddress.ip_address(host)
        except ValueError:
            valid = (
                re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?", host) is not None
            )
    if not valid:
        raise DoctorError(
            "DATABASE_CONNECTION_CONFIG",
            "Use only a hostname/IP here. Enter ports and credentials privately in the DSN.",
            detail_code="configuration",
        )


def inspection_dsn(raw: str, expected_host: str, *, approved: bool) -> str:
    """Pin the approved host and require verified TLS outside numeric loopback."""
    if not approved:
        raise DoctorError(
            "DATABASE_APPROVAL_REQUIRED", "Approve catalog-only access before connecting."
        )
    reason = "configuration"
    failure: DoctorError | None = None
    try:
        if not raw or len(raw) > 16384 or any(c in raw for c in "\r\n\x00"):
            raise ValueError
        values = {
            key: str(value) for key, value in conninfo_to_dict(raw).items() if value is not None
        }
        reason = "unsupported_options"
        if set(values) - {"host", "port", "dbname", "user", "password", "sslmode", "sslrootcert"}:
            raise ValueError
        host = values.get("host", "")
        reason = "host_mismatch"
        if not host or host.lower() != expected_host.lower():
            raise ValueError
        reason = "configuration"
        if any(c in host for c in ",/\\%\r\n\x00"):
            raise ValueError
        reason = "missing_fields"
        if (
            not values.get("dbname")
            or not values.get("user")
            or not 1 <= int(values.get("port", "0")) <= 65535
        ):
            raise ValueError
        reason = "configuration"
        try:
            address = ipaddress.ip_address(host)
            loopback = address.is_loopback
        except ValueError:
            if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?", host):
                raise ValueError from None
            loopback = False
        mode = values.get("sslmode", "disable" if loopback else "verify-full")
        reason = "unsupported_tls_mode" if loopback else "verified_tls_required"
        if mode not in ({"disable", "verify-full"} if loopback else {"verify-full"}):
            raise ValueError
        values["sslmode"] = mode
        if mode == "verify-full":
            ca = values.get("sslrootcert", "system")
            reason = "ca_file_unavailable"
            if ca != "system" and not Path(ca).is_file():
                raise ValueError
            values["sslrootcert"] = ca
        values["sslcertmode"] = "disable"
        values["sslkeylogfile"] = os.devnull
        values["gssencmode"] = "disable"
        values["gssdelegation"] = "0"
    except Exception:
        failure = DoctorError(
            "DATABASE_CONNECTION_CONFIG",
            "Connection must match the approved host and include database/user/port. "
            "Remote access requires verify-full TLS and a trusted CA; service/options overrides "
            "and multi-host connections are unsupported. No connection details were retained.",
            detail_code=reason,
        )
    if failure is not None:
        raise failure
    # Resolve only after approval and all configuration/TLS checks.
    try:
        candidates = socket.getaddrinfo(host, int(values["port"]), type=socket.SOCK_STREAM)
    except OSError:
        candidates = []
    if not candidates:
        raise DoctorError(
            "DATABASE_DNS_FAILED",
            "Cannot resolve the approved database hostname.",
            detail_code="name_resolution",
        )
    candidates.sort(key=lambda item: item[0] != socket.AF_INET)
    values["hostaddr"] = str(ipaddress.ip_address(candidates[0][4][0]))
    values["connect_timeout"] = "5"
    return make_conninfo(**values)
