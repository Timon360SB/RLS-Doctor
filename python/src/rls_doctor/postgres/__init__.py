"""Read-only PostgreSQL catalog inspection; no application rows are queried."""

from .inspector import InspectorError, doctor_database, inspect_table

__all__ = ["InspectorError", "doctor_database", "inspect_table"]
