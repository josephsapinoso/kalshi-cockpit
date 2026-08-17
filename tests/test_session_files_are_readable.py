"""The files CLAUDE.md tells every session to read must be openable.

CLAUDE.md's opening paragraph instructs each session to read `tasks/NEXT.md`
and `tasks/lessons.md` at session start. The Read tool refuses any file over
262,144 bytes. Both files crossed that ceiling, so the instruction became
impossible to obey and sessions coped by reading only the head — which is this
repo's own "built but never called" defect applied to its own memory.

This guard fails the moment either file goes back over the line.

What it does NOT establish: that the files are *useful*, that the archive is
complete, or that anything in them is true. It checks one thing — that a
session-start instruction is physically executable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# The Read tool's hard ceiling. A file at or above this cannot be opened at all.
READ_TOOL_LIMIT_BYTES = 262_144

SESSION_START_FILES = ("tasks/NEXT.md", "tasks/lessons.md")


class TestSessionStartFilesCanBeRead:
    @pytest.mark.parametrize("relative_path", SESSION_START_FILES)
    def test_file_is_under_the_read_tool_limit(self, relative_path: str) -> None:
        path = REPO_ROOT / relative_path
        assert path.is_file(), f"{relative_path} is missing"

        size = path.stat().st_size
        assert size < READ_TOOL_LIMIT_BYTES, (
            f"{relative_path} is {size:,} bytes, over the {READ_TOOL_LIMIT_BYTES:,}"
            " byte Read-tool ceiling. CLAUDE.md tells every session to read it at"
            " session start; over this size that instruction cannot be obeyed."
            " Move older entries into tasks/archive/ — do not delete content."
        )
