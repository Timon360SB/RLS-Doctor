"""UTF-8 JSON report files with bounded size and atomic no-overwrite publication."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from rls_doctor.core.errors import DoctorError


def available(path: Path | None) -> None:
    """Reject existing destinations before any diagnostic/network work."""
    if path is not None and (path.exists() or path.is_symlink()):
        raise DoctorError("REPORT_EXISTS", "Report destination already exists; choose a new file.")


def write_report(report: dict[str, Any], path: Path) -> None:
    """Publish a complete generated report, never replace another file."""
    available(path)
    data = (json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")
    if len(data) > 1048576:
        raise DoctorError("REPORT_LIMIT", "Report exceeds the 1 MiB file limit; no file was saved.")
    temporary: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            prefix=".rls-doctor-report-", suffix=".tmp", dir=path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        # Hard-link creation is atomic and refuses a destination created meanwhile.
        os.link(temporary, path)
    except FileExistsError:
        raise DoctorError(
            "REPORT_EXISTS", "Report destination already exists; choose a new file."
        ) from None
    except OSError:
        raise DoctorError(
            "REPORT_WRITE_FAILED",
            "Cannot save report; check the folder, permissions and filesystem hard-link support.",
        ) from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
