"""Every file a session may need to read must be openable by the Read tool.

CLAUDE.md's opening paragraph instructs each session to read `tasks/NEXT.md`
and `tasks/lessons.md` at session start. The Read tool refuses any file over
262,144 bytes. Both files crossed that ceiling, so the instruction became
impossible to obey and sessions coped by reading only the head — which is this
repo's own "built but never called" defect applied to its own memory.

**The same ceiling applies to source, and on 2026-09-03 two tracked source
files were already past it** — `backend/api/routes.py` (333,958 bytes) and
`scripts/inspect_live_db.py` (263,058) — with nothing guarding either. A
session told to check `routes.py:5,200` could not open the file at all. The
guard here now covers every tracked file with a source suffix, enumerated via
`git ls-files` so untracked scratch never trips it.

Two deliberate carve-outs, both named so they can be argued with:

- `tasks/archive/**` is excluded. Its files are written to be *grepped*
  rather than read whole — `tasks/lessons.md`'s header says the archive
  "reconstructs the pre-split file byte for byte" and the index names which
  archive file to open — and every one is under the ceiling today anyway
  (largest 135,833 bytes). If one ever grows past it, grep still works.
- `backend/api/routes.py` is on a **ratcheted exemption**: it may shrink and
  may not grow. The fix is a module split — `create_app` is one function
  holding ~45 handlers as closures — not a trim, and a split is not a guard's
  business. The exemption records the size at exemption time and fails on any
  byte of growth, and it fails again the moment the file is under the ceiling
  so the exemption cannot outlive its reason.

What it does NOT establish: that the files are *useful*, that the archive is
complete, or that anything in them is true. It checks one thing — that a file
a session may be told to read is physically openable.

Size is measured on the working tree, because that is what the Read tool
opens. `.gitattributes` gives `*.py` `eol=lf`, so the ratchet's recorded size
is the same on this Windows checkout and on Linux CI; `text=auto` files (the
`.md` set) check out CRLF on Windows and are therefore *larger* here than in
CI — Windows is the stricter environment, and it is the one sessions run on.

Mutations observed red (2026-09-03): the ratchet with its recorded size set
one byte below the file's actual size (333,957 against 333,958); the general
check with `READ_TOOL_LIMIT_BYTES` lowered to 250,000 so
`scripts/inspect_live_db.py` (then 256,349 bytes) tripped it, and again with
the limit set to 1 so every tracked source file did; the stale-exemption check
with the exemption re-pointed at this test file, which is under the ceiling.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# The Read tool's hard ceiling. A file at or above this cannot be opened at all.
READ_TOOL_LIMIT_BYTES = 262_144

SESSION_START_FILES = ("tasks/NEXT.md", "tasks/lessons.md")

# Tracked files with one of these suffixes are meant to be read whole. Data
# (`docs/measurements/*.json*`, `tests/fixtures/*.json`) is not, and is not
# covered.
SOURCE_SUFFIXES = (".py", ".ts", ".tsx", ".sql", ".toml", ".yml", ".md")

# Written to be grepped, never read whole; see the module docstring.
EXCLUDED_PREFIXES = ("tasks/archive/",)

# path -> size in bytes at exemption time. An exempted file may shrink and may
# not grow. Do not add to this: an exemption exists only where the fix is a
# module split rather than a trim, and that has been true of exactly one file.
RATCHETED_EXEMPTIONS: dict[str, int] = {
    # 2026-09-03. `create_app` runs from ~line 495 to ~5,859 and holds ~45
    # route handlers as closures; another lane owns the split.
    "backend/api/routes.py": 333_958,
}


def tracked_files() -> list[str]:
    """Every path git tracks, as forward-slash paths relative to the repo root.

    `git ls-files -z` rather than a filesystem walk: an untracked scratch file,
    a build artefact or a virtualenv must never trip a guard about what a
    session can read from the repository.
    """
    out = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    ).stdout
    return [p.decode("utf-8") for p in out.split(b"\0") if p]


def tracked_source_files() -> list[str]:
    return [
        p
        for p in tracked_files()
        if p.endswith(SOURCE_SUFFIXES) and not p.startswith(EXCLUDED_PREFIXES)
    ]


def _size(relative_path: str) -> int:
    return (REPO_ROOT / relative_path).stat().st_size


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


class TestTrackedSourceCanBeRead:
    def test_the_enumeration_is_not_empty_and_sees_this_file(self) -> None:
        """A guard over an empty list passes vacuously; this pins that it is not.

        If `git` were absent or `cwd` wrong, `tracked_files` would raise or
        return nothing, and the guard below would be decoration.
        """
        files = tracked_source_files()
        assert len(files) > 100, f"only {len(files)} tracked source files found"
        assert "tests/test_session_files_are_readable.py" in files

    def test_every_tracked_source_file_is_under_the_read_tool_limit(self) -> None:
        offenders = {
            p: _size(p)
            for p in tracked_source_files()
            if p not in RATCHETED_EXEMPTIONS and _size(p) >= READ_TOOL_LIMIT_BYTES
        }
        assert not offenders, (
            "These tracked source files are at or over the "
            f"{READ_TOOL_LIMIT_BYTES:,}-byte Read-tool ceiling, so no session can "
            "open them at all:\n"
            + "\n".join(f"  {p}  {n:,} bytes" for p, n in sorted(offenders.items()))
            + "\n\nWhat to do: for a module, split it along a seam a caller "
            "already uses (a new `scripts/` module must ALSO be added to the "
            "`.dockerignore` allowlist, or it will not reach the live box -- see "
            "that file's comments); for prose, move the historical part into an "
            "existing `docs/` file it can cite by path, or into "
            "`tasks/archive/` if it is a session file. Do not delete content, "
            "and do not add to RATCHETED_EXEMPTIONS -- that list is for a file "
            "whose only fix is a module split, and it is meant to hold one."
        )

    @pytest.mark.parametrize("relative_path", sorted(RATCHETED_EXEMPTIONS))
    def test_an_exempted_file_has_not_grown(self, relative_path: str) -> None:
        recorded = RATCHETED_EXEMPTIONS[relative_path]
        assert relative_path in tracked_files(), (
            f"{relative_path} is exempted but not tracked; remove the exemption"
        )
        size = _size(relative_path)
        assert size <= recorded, (
            f"{relative_path} is {size:,} bytes, up from the {recorded:,} recorded "
            "when it was exempted from the Read-tool ceiling. The exemption exists "
            "because the fix is a MODULE SPLIT, not a trim, and it is a ratchet: "
            "the file may shrink and may not grow by a byte. Put the new code in "
            "a module a session can open, or split this one first. Do not raise "
            "the recorded number."
        )

    @pytest.mark.parametrize("relative_path", sorted(RATCHETED_EXEMPTIONS))
    def test_an_exemption_does_not_outlive_its_reason(self, relative_path: str) -> None:
        """Once the file is under the ceiling the exemption must go.

        Otherwise the general check never covers it again, and the recorded
        size becomes a licence to grow back to it.
        """
        size = _size(relative_path)
        assert size >= READ_TOOL_LIMIT_BYTES, (
            f"{relative_path} is {size:,} bytes -- under the "
            f"{READ_TOOL_LIMIT_BYTES:,}-byte ceiling. Remove it from "
            "RATCHETED_EXEMPTIONS so the general guard covers it from here on."
        )
