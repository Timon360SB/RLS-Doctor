"""Fixed diagnostic messages never interpolate untrusted input or exceptions."""


class DoctorError(Exception):
    """Expected operational error safe for console and JSON output."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)
