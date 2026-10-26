"""Fixed diagnostic messages never interpolate untrusted input or exceptions."""


class DoctorError(Exception):
    """Expected operational error safe for console and JSON output."""

    def __init__(self, code: str, message: str, *, detail_code: str | None = None) -> None:
        self.code = code
        self.detail_code = detail_code
        super().__init__(message)
