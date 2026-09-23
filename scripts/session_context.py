"""Print the session-start brief for a SessionStart hook. Read-only.

    .venv\\Scripts\\python.exe scripts/session_context.py

Why this exists
----------------
Joe was opening a fresh session only to type "read NEXT.md and start". The
project's `.claude/settings.json` runs this on `startup`, `clear` and
`compact`, and whatever it prints lands in the new session's context, so the
state is already loaded before the first prompt. `/go`
(`.claude/commands/go.md`) is still what starts the work; a hook cannot make
a session act unprompted.

What it prints: `tasks/NEXT.md` from the top through the end of its latest
dated entry (the header, the SESSION START box, one entry), then the top
`LESSONS_ENTRIES` entries of `tasks/lessons.md`. A dated entry is a line
starting `## 20`, the same heading shape both files already use.

WHAT THIS DOES NOT ESTABLISH
-----------------------------
- **It is not the whole state.** Older NEXT.md entries, the archive, the
  GitHub queue (#3, #80) and the live instance are not read. The SESSION
  START box it prints tells the session to read those itself.
- **It trusts the heading shape.** An entry whose heading does not start
  `## 20` is folded into the one above it; nothing here checks the dates are
  in order.
- **The size cap truncates silently past `MAX_CHARS`** except for the one
  marker line it appends, so an oversized latest entry is cut, not refused:
  a hook that fails prints nothing, which is worse than a cut brief.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LESSONS_ENTRIES = 2
MAX_CHARS = 60_000
ENTRY_PREFIX = "## 20"


def head_through_entries(text: str, entries: int) -> str:
    """Everything up to (not including) the dated heading after the first `entries`."""
    lines = text.splitlines(keepends=True)
    seen = 0
    for i, line in enumerate(lines):
        if line.startswith(ENTRY_PREFIX):
            seen += 1
            if seen > entries:
                return "".join(lines[:i])
    return text


def build(root: Path = ROOT, max_chars: int = MAX_CHARS) -> str:
    parts = []
    for rel, entries in (("tasks/NEXT.md", 1), ("tasks/lessons.md", LESSONS_ENTRIES)):
        path = root / rel
        try:
            text = path.read_bytes().decode("utf-8")
        except OSError:
            parts.append(f"=== {rel}: unreadable, read it by hand ===\n")
            continue
        parts.append(f"=== {rel} (head, latest {entries}) ===\n")
        parts.append(head_through_entries(text, entries).rstrip() + "\n\n")
    out = "".join(parts)
    if len(out) > max_chars:
        out = out[:max_chars] + f"\n[truncated at {max_chars} chars; read the files directly]\n"
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(build())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
