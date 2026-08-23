"""Read the `unmatched_items` queue -- the work list alias files get filled from.

    .venv\\Scripts\\python.exe scripts\\list_unmatched.py [--db data/cockpit.db]

`backend/match/linker.py` writes one row per work item the linker could not
resolve (ADR 0056): what failed (`identifier`, with the team names as seen in
`detail`), on which side (`kalshi` | `odds`), the league if known, a free-text
sentence saying why, when it was first and most recently seen, and how many
passes have seen it. Until this script existed, nothing in the repo read that
queue -- the fifth built-but-never-called instance. NCAAF season starts
~2026-08-27 and will fill it with real names; this is the instrument for
turning those rows into alias entries.

Duplicates are already grouped by the schema itself: `idx_unmatched_item` makes
`(side, identifier, league, detail, reason)` the row's identity and the writer
upserts, so `seen_count` IS the duplicate count and no aggregation happens here.

The connection is opened `mode=ro` so the instrument cannot mutate the queue it
reads. An empty queue prints an explicit "0 unmatched items"; a database that
cannot be opened or lacks the table refuses with a nonzero exit, because
"nothing to do" and "could not look" must never print the same thing.

What this does NOT establish
----------------------------
- **Not that the queue is being worked.** `resolved` is set by no code path;
  rows shown here are open work, and this script only makes them visible.
- **Not the true sighting count.** `seen_count` is exact only from schema v14
  forward; the migration's first value is a floor, and retention trims rows
  whose `last_seen_ms` has aged out, so an item can vanish and later reappear
  with its count reset.
- **Not that a listed item is a bug.** "Coverage is thin" and "coverage is
  broken" both land here; only reading the `reason` sentence tells them apart.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# The local path convention comes from `backend/config.py` (`DB_PATH`,
# default `data/cockpit.db`) -- the database the runner writes when it runs
# here. On the deployed instance the volume mounts at `/data/cockpit.db`;
# pass that with --db when running via `flyctl ssh console`.
DEFAULT_DB = "data/cockpit.db"

_COLUMNS = (
    "side", "league", "identifier", "detail",
    "seen_count", "first_seen", "last_seen", "reason",
)


def connect_readonly(db_path: str) -> sqlite3.Connection:
    """A connection that cannot write, enforced by SQLite rather than promised.

    `mode=ro` in the URI makes every mutating statement fail with "attempt to
    write a readonly database" -- the same guard `scripts/inspect_live_db.py`
    uses. An instrument pointed at the live queue must not be one typo away
    from editing it. `as_posix()` because backslashes are not URI separators.
    """
    return sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)


def _stamp(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M"
    )


def fetch_open_items(conn: sqlite3.Connection) -> tuple[list[dict], int]:
    """The open work items, newest sighting first, plus the resolved count.

    Ordered by `last_seen_ms` DESC because the item still being seen is the one
    an alias entry would fix right now; an item no pass has re-derived lately
    may already be gone from the slate.
    """
    rows = conn.execute(
        "SELECT side, identifier, league, detail, reason, seen_count, "
        "first_seen_ms, last_seen_ms FROM unmatched_items "
        "WHERE resolved = 0 ORDER BY last_seen_ms DESC, id"
    ).fetchall()
    resolved = conn.execute(
        "SELECT COUNT(*) FROM unmatched_items WHERE resolved != 0"
    ).fetchone()[0]
    items = [
        {
            "side": r[0],
            "identifier": r[1],
            "league": r[2] if r[2] is not None else "-",
            "detail": r[3] if r[3] is not None else "-",
            "reason": r[4],
            "seen_count": str(r[5]),
            "first_seen": _stamp(r[6]),
            "last_seen": _stamp(r[7]),
        }
        for r in rows
    ]
    return items, resolved


def render(items: list[dict], resolved: int, db_path: str) -> str:
    """The queue as a text table, or an explicit statement that it is empty."""
    tail = f" ({resolved} resolved not shown)" if resolved else ""
    if not items:
        return (
            f"0 unmatched items in {db_path}{tail}\n"
            "The linker resolved everything it saw, or has not run against "
            "this database.\n"
        )

    widths = {
        col: max(len(col), *(len(item[col]) for item in items))
        for col in _COLUMNS
    }
    full_width = sum(widths.values()) + 2 * (len(_COLUMNS) - 1)
    header = "  ".join(col.ljust(widths[col]) for col in _COLUMNS).rstrip()
    lines = [header, "-" * full_width]
    lines.extend(
        "  ".join(item[col].ljust(widths[col]) for col in _COLUMNS).rstrip()
        for item in items
    )
    lines.append("")
    lines.append(f"{len(items)} unmatched items in {db_path}{tail}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB)
    args = parser.parse_args(argv)

    try:
        conn = connect_readonly(args.db)
        try:
            items, resolved = fetch_open_items(conn)
        finally:
            conn.close()
    except sqlite3.OperationalError as exc:
        # Refusal, not an empty report: a missing file or a pre-v14 database
        # with no `unmatched_items` table is "could not look", and printing
        # anything resembling a count here would make unreadable look empty.
        print(f"cannot read {args.db}: {exc}", file=sys.stderr)
        return 2

    print(render(items, resolved, args.db), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
