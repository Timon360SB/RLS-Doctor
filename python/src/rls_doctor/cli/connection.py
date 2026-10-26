"""Approved profile reuse; credentials remain scoped to the caller's memory."""

import os

import typer

from rls_doctor.core.database_connection import inspection_dsn, validate_database_host
from rls_doctor.core.errors import DoctorError
from rls_doctor.core.profiles import DatabaseProfile
from rls_doctor.reports.console import Language, word


def profile_dsn(
    profile: DatabaseProfile,
    language: Language,
    *,
    approved: bool = False,
    interactive: bool = True,
) -> str:
    validate_database_host(profile.host)
    if not approved and interactive:
        approved = typer.confirm(
            word(
                language,
                f"Read only access-control catalogs on {profile.host}?",
                f"Прочитать только каталоги прав на {profile.host}?",
            ),
            default=False,
        )
    if not approved:
        raise DoctorError(
            "DATABASE_APPROVAL_REQUIRED",
            "Explicitly approve catalog-only access before connecting.",
        )
    raw = os.environ.get(profile.connection_env)
    if not raw and interactive:
        password = typer.prompt(
            word(
                language,
                "Database password (hidden; not saved)",
                "Пароль базы (ввод скрыт; не сохраняется)",
            ),
            hide_input=True,
            show_default=False,
            default="",
        )
        raw = profile.connection(password)
    if not raw:
        raise DoctorError(
            "MISSING_CREDENTIAL", "Set the profile's database environment reference privately."
        )
    dsn = inspection_dsn(raw, profile.host, approved=True)
    profile.check_connection(dsn)
    return dsn
