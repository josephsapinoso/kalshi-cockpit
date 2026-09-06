"""Shared plumbing for the `inspect_live_db` family: no queries live here.

This module is imported by `inspect_live_db.py` and by every domain module
beside it. It holds the output model (`Section`), the two functions that turn
a bound query into one (`_fetch`, `_bind`), the millisecond-to-ISO derivation
every query applies to its clocks, the budget-day arithmetic the credit
queries share, and the connection and renderers `main` uses.

**It is not runnable and is not invoked over ssh.** The ssh ruling invokes
`inspect_live_db.py` by path; this file reaches the live box only because it
is on `.dockerignore`'s allowlist, and
`tests/test_inspect_live_db_modules.py` derives that requirement from the
entrypoint's own import list rather than trusting anyone to remember it.

Every constraint the entrypoint's docstring states holds here unchanged:
read-only is enforced by the connection, no caller-supplied value reaches any
SQL text, and nothing in this family imports from `backend`.
"""

from __future__ import annotations

import json
import math
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Sequence


# The live volume. `cockpit.db`, not `kalshi.db` -- the repo-root `kalshi.db`
# is a local scratch file and the two names have been confused before.
DEFAULT_DB = "/data/cockpit.db"

# A mistake must not be able to dump the whole database into a transcript.
DEFAULT_ROW_CAP = 2000

# Matches `budget_day_start_utc_hour`. The sports day rolls at 10:00 UTC so a
# late West Coast game shares a budget bucket with the rest of its night.
DEFAULT_DAY_START_HOUR = 10

_MS_PER_DAY = 86_400_000


class UnknownQuery(Exception):
    """Raised for a query name that is not on the whitelist.

    A named exception rather than a `None` return, because the failure mode
    being prevented is a typo'd query name that produces empty output and
    reads as "nothing to report".
    """


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------


@dataclass
class Section:
    """One labelled result block: columns, rows, and how many there were.

    `row_count` is carried explicitly rather than left to `len(rows)` at the
    render site so that both renderers state it and neither can accidentally
    print an empty block that reads as success.
    """

    title: str
    columns: tuple[str, ...]
    rows: list[tuple[Any, ...]] = field(default_factory=list)
    truncated: bool = False
    cap: Optional[int] = None

    @property
    def row_count(self) -> int:
        return len(self.rows)


def _iso(ms: Optional[int]) -> Optional[str]:
    """Render epoch milliseconds as an ISO-8601 UTC stamp, or `None`.

    `None` in, `None` out -- never the epoch. A missing timestamp rendered as
    `1970-01-01T00:00:00Z` is a fabricated observation, and this project has
    already been bitten once by an absence borrowing a present value's
    representation.
    """
    if ms is None:
        return None
    return (
        datetime.fromtimestamp(ms / 1000, timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _fetch(
    conn: sqlite3.Connection,
    sql: str,
    params: Sequence[Any] | dict[str, Any],
    *,
    title: str,
    cap: int,
    requested: Optional[int] = None,
) -> Section:
    """Run one fixed SQL string under the row cap and report truncation.

    The cap is applied by appending `LIMIT ?` and binding `effective + 1`: if
    the extra row comes back, more rows existed and the caller is told so. A
    cap that silently trimmed would turn "there are 40,000 of these" into
    "there are 2,000 of these", which is the shape of error this repo's
    measurement rules exist to catch.

    `requested` is a query's own N (e.g. `credits-tail -n 5`). When the
    query's own N binds, that is the caller getting what they asked for and no
    truncation is reported; when the hard cap binds, it is.
    """
    effective = cap if requested is None else min(requested, cap)
    effective = max(0, effective)
    # sqlite3 refuses to mix named and positional placeholders in one
    # statement, so the cap's placeholder has to match the query's style.
    suffix = f" LIMIT {_LIMIT_TOKEN}" if isinstance(params, dict) else " LIMIT ?"
    cur = conn.execute(sql + suffix, _bind(params, effective + 1))
    rows = cur.fetchall()
    columns = tuple(d[0] for d in cur.description)
    truncated = len(rows) > effective and effective == cap
    return Section(
        title=title,
        columns=columns,
        rows=[tuple(r) for r in rows[:effective]],
        truncated=truncated,
        cap=cap,
    )


# Named-parameter queries need the cap bound by name too. The token and the
# key are derived from one string so the two halves cannot drift apart.
_LIMIT_KEY = "__limit"
_LIMIT_TOKEN = f":{_LIMIT_KEY}"


def _bind(
    params: Sequence[Any] | dict[str, Any], limit: int
) -> Sequence[Any] | dict[str, Any]:
    """Append the cap to positional params, or add it to named ones."""
    if isinstance(params, dict):
        out = dict(params)
        out[_LIMIT_KEY] = limit
        return out
    return list(params) + [limit]


def _derive_iso(section: Section, ms_column: str, iso_column: str) -> Section:
    """Add an ISO rendering of a millisecond column already in the output.

    This adds no data. Every ISO column here is a second view of a column the
    query already selected, which is why it does not breach the rule that this
    script prints no column outside the named set.
    """
    if ms_column not in section.columns:
        raise KeyError(f"{ms_column!r} is not in {section.columns!r}")
    idx = section.columns.index(ms_column)
    section.columns = (
        section.columns[: idx + 1] + (iso_column,) + section.columns[idx + 1 :]
    )
    section.rows = [
        row[: idx + 1] + (_iso(row[idx]),) + row[idx + 1 :] for row in section.rows
    ]
    return section


def _day_bounds(date_yyyymmdd: str, day_start_hour: int) -> tuple[int, int]:
    """The half-open [start, end) millisecond bounds of one budget day."""
    try:
        day = datetime.strptime(date_yyyymmdd, "%Y%m%d")
    except ValueError as exc:
        raise ValueError(
            f"--date must be YYYYMMDD, got {date_yyyymmdd!r}"
        ) from exc
    start = day.replace(
        hour=day_start_hour, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
    )
    start_ms = int(start.timestamp() * 1000)
    return start_ms, start_ms + _MS_PER_DAY


def _month_start_ms(now_ms: int) -> int:
    """UTC calendar month start. The Odds API's month, not our sports day."""
    dt = datetime.fromtimestamp(now_ms / 1000, timezone.utc)
    return int(
        dt.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        ).timestamp()
        * 1000
    )


def _window_section(title: str, start_ms: int, end_ms: Optional[int]) -> Section:
    """A one-row block naming the time window a query actually used.

    Printed because the window is derived from flags and the reader must be
    able to check it without re-deriving the arithmetic in their head.
    """
    columns = ("start_ms", "start_iso")
    row: tuple[Any, ...] = (start_ms, _iso(start_ms))
    if end_ms is not None:
        columns += ("end_ms", "end_iso")
        row += (end_ms, _iso(end_ms))
    return Section(title=title, columns=columns, rows=[row])


def _quantile(sorted_values: list[float], q: float) -> Optional[float]:
    """Nearest-rank quantile. `None` on an empty list, never 0.0."""
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    idx = max(0, min(len(sorted_values) - 1,
                     int(math.ceil(q * len(sorted_values))) - 1))
    return sorted_values[idx]


# ---------------------------------------------------------------------------
# Connection and rendering
# ---------------------------------------------------------------------------


def connect_readonly(db_path: str) -> sqlite3.Connection:
    """Open the database read-only, enforced by SQLite rather than by us.

    `mode=ro` makes any write raise `sqlite3.OperationalError: attempt to
    write a readonly database`. That is the property that makes this file
    reviewable once: a later edit cannot turn it into a writer by accident,
    only by changing this line.
    """
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def _cell(value: Any) -> str:
    """NULL is printed as NULL. An empty string is a value; absence is not."""
    if value is None:
        return "NULL"
    return str(value)


def render_text(query: str, db_path: str, sections: list[Section]) -> str:
    out: list[str] = [f"# {query}  ({db_path})", ""]
    for section in sections:
        out.append(section.title)
        out.append("-" * len(section.title))
        if section.row_count == 0:
            # Never an empty block. Absence gets its own words, because an
            # empty region of a transcript reads as success.
            out.append("0 rows")
            out.append("")
            continue
        cells = [[_cell(v) for v in row] for row in section.rows]
        widths = [
            max(len(section.columns[i]), *(len(r[i]) for r in cells))
            for i in range(len(section.columns))
        ]
        out.append(
            "  ".join(c.ljust(widths[i]) for i, c in enumerate(section.columns))
        )
        out.append("  ".join("-" * w for w in widths))
        for row in cells:
            out.append("  ".join(c.ljust(widths[i]) for i, c in enumerate(row)))
        noun = "row" if section.row_count == 1 else "rows"
        out.append(f"{section.row_count} {noun}")
        if section.truncated:
            out.append(
                f"TRUNCATED at the --limit row cap of {section.cap}. More rows "
                f"exist and are not shown; re-run with a higher --limit."
            )
        out.append("")
    return "\n".join(out)


def render_json(query: str, db_path: str, sections: list[Section]) -> str:
    # Server clock. A capture with no stamp made the presence result's E0
    # rest on file mtime and git chronology (2026-09-04 result doc, §4).
    now_ms = int(time.time() * 1000)
    return json.dumps(
        {
            "query": query,
            "db": db_path,
            "generated_at_ms": now_ms,
            "generated_at": _iso(now_ms),
            "sections": [
                {
                    "title": s.title,
                    "columns": list(s.columns),
                    "rows": [list(r) for r in s.rows],
                    "row_count": s.row_count,
                    # Explicit rather than inferable from `rows == []`. A
                    # consumer that forgets to check length must still see it.
                    "empty": s.row_count == 0,
                    "truncated": s.truncated,
                    "row_cap": s.cap,
                }
                for s in sections
            ],
        },
        indent=2,
        default=str,
    )
