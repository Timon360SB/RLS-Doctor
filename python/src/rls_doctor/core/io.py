"""Bound untrusted event/config/scenario files before decoding or parsing."""

from pathlib import Path


def read_document(path: Path, limit: int = 65536) -> str:
    if not path.is_file():
        raise ValueError("A regular input file is required")
    with path.open("rb") as handle:
        contents = handle.read(limit + 1)
    if len(contents) > limit:
        raise ValueError("Input file limit exceeded")
    return contents.decode("utf-8")
