"""Read the `unmatched_items` queue -- the work list alias files get filled from.

    .venv\\Scripts\\python.exe scripts\\list_unmatched.py [--db data/cockpit.db]

    flyctl ssh console -a kalshi-cockpit \\
      -C "python /app/scripts/list_unmatched.py --db /data/cockpit.db --league 'Pro Football'"

**Why the second line exists, added 2026-09-07.** This script was written for
the laptop and left out of the image, so the live queue -- the only copy that
has ever held real names -- could not be read by it. The 2026-09-07 NFL
pre-flight needed exactly that reading and took it as ad-hoc SQL over
`flyctl ssh` instead, which is the thing `scripts/inspect_live_db.py`'s ruling
forbids in those words: *"nothing that carries its own source in the command
line"*. Naming the live path here is not documentation. It is what makes
`tests/test_has_callers.py::TestTheSshInvokedScriptsSurviveDockerignore`
**demand** the matching `!scripts/list_unmatched.py` line in `.dockerignore`,
so the file cannot be documented as live-invoked and absent from the image at
the same time -- the failure that has now happened five times.

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

Reading it across a fix: the count does not fall, the clock moves
------------------------------------------------------------------
**A row that stops failing is not removed, and this is the reading most likely
to be got backwards.** Nothing sets `resolved = 1` and nothing deletes on
success; `linker.py` only ever upserts, moving `last_seen_ms` forward and
incrementing `seen_count`. So when a link finally lands, its row simply stops
being re-derived and sits there, frozen, until
`retention.DEFAULT_UNMATCHED_RETENTION_MS` (**7 days**, measured on
`last_seen_ms`) prunes it.

So `32 unmatched items` before a fix and `32 unmatched items` an hour after it
is the **success** case, not a failure to link. What separates them is
`last_seen`: the rows still failing carry a stamp from the last pass, the rows
that were fixed carry the stamp of the pass that last failed on them and never
move again. `ORDER BY last_seen_ms DESC` puts the live ones on top for exactly
this reason.

This was written down on 2026-09-07 because the plan for the first NFL sweep
said *"expect the 32 rows to fall to ~16"*. They will not fall for a week.

What this does NOT establish
----------------------------
- **Not that the queue is being worked.** `resolved` is set by no code path;
  rows shown here are open work, and this script only makes them visible.
- **Not that a stale row was fixed.** A frozen `last_seen` says nobody has
  re-derived the item, and a link landing is only one reason for that -- the
  event closing, the series leaving the board, or the linker not running at all
  produce the same frozen stamp. It narrows the question; it does not close it.
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


def fetch_open_items(
    conn: sqlite3.Connection, league: str | None = None
) -> tuple[list[dict], int]:
    """The open work items, newest sighting first, plus the resolved count.

    Ordered by `last_seen_ms` DESC because the item still being seen is the one
    an alias entry would fix right now; an item no pass has re-derived lately
    may already be gone from the slate.

    `league` is an **exact** match on the competition string as the linker saw
    it (`'Pro Football'`, not `'nfl'` and not a prefix), and it is a bound
    parameter -- no caller-supplied text reaches the SQL, the same property
    `scripts/inspect_live_db.py` holds. `None` is every league, which is what
    every caller written before this argument existed gets.

    It exists because the live queue carries every league at once and the
    question asked of it is always about one: a `Pro Football` reading that
    arrives with several hundred baseball rows around it is a reading nobody
    takes. **The filter narrows the rows and not the counts' meaning** -- the
    resolved tally below is deliberately unfiltered, because it answers "is
    anything setting `resolved` yet?", which is a fact about the code and not
    about the league.
    """
    if league is None:
        rows = conn.execute(
            "SELECT side, identifier, league, detail, reason, seen_count, "
            "first_seen_ms, last_seen_ms FROM unmatched_items "
            "WHERE resolved = 0 ORDER BY last_seen_ms DESC, id"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT side, identifier, league, detail, reason, seen_count, "
            "first_seen_ms, last_seen_ms FROM unmatched_items "
            "WHERE resolved = 0 AND league = ? ORDER BY last_seen_ms DESC, id",
            (league,),
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


def render(
    items: list[dict], resolved: int, db_path: str, league: str | None = None
) -> str:
    """The queue as a text table, or an explicit statement that it is empty.

    **The filter is named in every line that carries a count**, including the
    empty one, because a cut that is not echoed turns "no rows for this league"
    into "the queue is empty" -- and those need opposite responses. It is the
    same rule `/api/slate` follows when it echoes `filter.league` rather than
    returning a short list that reads as a quiet night.
    """
    scope = "" if league is None else f" for league {league!r}"
    tail = f" ({resolved} resolved not shown)" if resolved else ""
    if not items:
        if league is not None:
            return (
                f"0 unmatched items{scope} in {db_path}{tail}\n"
                "Nothing open under that exact competition string. It is a "
                "case-sensitive exact match, not a prefix, so check the "
                "spelling against an unfiltered run before reading this as "
                "'the linker resolved everything'.\n"
            )
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
    lines.append(f"{len(items)} unmatched items{scope} in {db_path}{tail}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument(
        "--league",
        default=None,
        help=(
            "Exact competition string as the linker saw it, e.g. "
            "'Pro Football'. Case-sensitive, not a prefix. Omitted means "
            "every league."
        ),
    )
    args = parser.parse_args(argv)

    try:
        conn = connect_readonly(args.db)
        try:
            items, resolved = fetch_open_items(conn, args.league)
        finally:
            conn.close()
    except sqlite3.OperationalError as exc:
        # Refusal, not an empty report: a missing file or a pre-v14 database
        # with no `unmatched_items` table is "could not look", and printing
        # anything resembling a count here would make unreadable look empty.
        print(f"cannot read {args.db}: {exc}", file=sys.stderr)
        return 2

    print(render(items, resolved, args.db, args.league), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
