"""One place that writes a throwaway Node driver next to the module it imports.

A driver has to sit beside its module because its relative imports must
resolve, so `tmp_path` is not an option. Two pytest-xdist workers running the
same test would then race on one fixed path (ENOENT on unlink, or one worker
running the other's file). The NAME is therefore unique per call:
`_driver_<pid>_<uuid4hex>.mjs`. `tests/test_no_fixed_name_driver_files.py`
fails on any test that goes back to a literal `_*.mjs` / `_*.ts` write.

Establishes: the file is removed on exit, including when the body raises.
Does not establish: anything about what the driver computes.
"""

from __future__ import annotations

import contextlib
import os
import uuid
from pathlib import Path
from typing import Iterator


def unique_name(suffix: str = ".mjs") -> str:
    return f"_driver_{os.getpid()}_{uuid.uuid4().hex}{suffix}"


@contextlib.contextmanager
def node_driver(
    directory: Path, source: str, suffix: str = ".mjs"
) -> Iterator[Path]:
    """Write `source` to a uniquely named file in `directory`; unlink on exit."""
    path = Path(directory) / unique_name(suffix)
    path.write_text(source, encoding="utf-8")
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)
