"""Read-only inspector for the live SQLite database, invoked by path.

    flyctl ssh console -a kalshi-cockpit \\
      -C "python /app/scripts/inspect_live_db.py credits-tail"

Why this file exists
--------------------
`flyctl ssh console` against `kalshi-cockpit` is permitted **only to invoke a
committed, reviewed script by path**. No interactive session, no filesystem
browsing, and nothing that carries its own source in the command line. The
point of the rule is that every line that runs against the money box was
reviewable in git before it ran, and a permission pattern matches a command
prefix -- it cannot see inside the quotes -- so the rule is a convention the
agent keeps and Joe audits, not something the grant enforces.

Until this file shipped, the live box had no script that could answer a
question, so the only way to ask one was to smuggle the code in with the
question. That is the drift this replaces. It is deliberately **one** artefact
with a **fixed whitelist of named queries**: reviewed once, safe forever,
because a caller can only choose a name, never supply SQL.

Two structural properties, not conventions
------------------------------------------
**Read-only is enforced by the connection**, not by the queries being
well-behaved: the database is opened with `mode=ro`, so SQLite itself refuses
a write. A future edit that adds an `UPDATE` fails at runtime rather than
succeeding quietly.

**No caller-supplied value ever reaches the SQL text.** Every query is a fixed
string constant; every number a caller can influence -- the tail length, the
day boundary, the recommendation pin, the row cap -- is a bound parameter.
There is no table name, column name, or predicate assembled from input.

`scripts/` is copied into the image at `Dockerfile:66`, so a new query here is
usable only from the **next deploy** onward.

What this does not establish
----------------------------
- **Nothing about causation.** It reports rows. `credits-tail` showing a low
  `remaining_reported` is consistent with the budget having latched shut, and
  also with the plan genuinely being near its ceiling; the row does not say
  which, and this script does not model `CreditBudget` at all. Read
  `backend/odds/budget.py:202-223` for the refusal order and decide there.
- **Nothing about completeness.** `credits-day` counts the rows that were
  written. A sweep refused before the request went out writes no `api_credits`
  row by design (see the `odds_sweep_log` comment in `schema.sql`), so a low
  count is an absence of *calls*, not evidence of an outage. `sweep-log` is
  the table that distinguishes those two, which is why it is a separate query.
- **Nothing about correctness of the values.** `remaining_reported` is what
  The Odds API's header said; this script does not reconcile it against our
  own tally. `BudgetState.drift` does that, and it is not computed here.
- **Nothing about the population beyond the pin.** The `*-for-pull` queries
  restrict to `recommendations.id <= --pin` so the population is byte-identical
  to `docs/measurements/2026-08-10-clean-shortfall-pull.json`. Rows created
  after that pin exist and are deliberately excluded; the counts here are not
  "how many games there are".
- **It is not a measurement harness.** It prints no aggregates that a finding
  should be built on without re-deriving them: no rates, no per-bucket splits,
  no significance. `SUM(cost)` and `MIN`/`MAX` are the only arithmetic, and
  they exist to bound a search, not to support a conclusion.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Sequence

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


# ---------------------------------------------------------------------------
# The whitelist. Every SQL string below is a constant.
# ---------------------------------------------------------------------------

_CREDIT_COLUMNS = (
    "called_ms, endpoint, sport_key, cost, remaining_reported, used_reported"
)

_SQL_CREDITS_TAIL = (
    f"SELECT {_CREDIT_COLUMNS} FROM api_credits ORDER BY called_ms DESC"
)

_SQL_CREDITS_DAY_ROWS = (
    f"SELECT {_CREDIT_COLUMNS} FROM api_credits "
    "WHERE called_ms >= ? AND called_ms < ? ORDER BY called_ms"
)

_SQL_CREDITS_DAY_TOTALS = (
    "SELECT COUNT(*) AS rows_in_day, COALESCE(SUM(cost), 0) AS total_cost "
    "FROM api_credits WHERE called_ms >= ? AND called_ms < ?"
)

_SQL_CREDITS_MONTH = (
    "SELECT COUNT(*) AS rows_month_to_date, "
    "COALESCE(SUM(cost), 0) AS total_cost, "
    "MIN(remaining_reported) AS min_remaining_reported, "
    "MAX(remaining_reported) AS max_remaining_reported, "
    "MIN(used_reported) AS min_used_reported, "
    "MAX(used_reported) AS max_used_reported "
    "FROM api_credits WHERE called_ms >= ?"
)

_SQL_SWEEP_LOG_GROUPS = (
    "SELECT outcome, COUNT(*) AS n, MIN(pass_ms) AS min_pass_ms, "
    "MAX(pass_ms) AS max_pass_ms FROM odds_sweep_log "
    "GROUP BY outcome ORDER BY outcome"
)

_SQL_SWEEP_LOG_TAIL = (
    "SELECT id, pass_ms, sport_key, outcome, detail, quotes_stored "
    "FROM odds_sweep_log ORDER BY pass_ms DESC, id DESC"
)

# The pinned population: recommendations up to `--pin`, and the Kalshi rows
# they reach. Identical to the population in the clean-shortfall pull, so the
# `result` column joins onto it row for row.
_PINNED_TICKERS = (
    "SELECT ticker FROM recommendations WHERE id <= :pin"
)

_SQL_RESULTS_FOR_PULL = (
    "SELECT ticker, event_ticker, series_ticker, yes_side_team, market_type, "
    "status, result FROM kalshi_markets "
    f"WHERE ticker IN ({_PINNED_TICKERS}) ORDER BY ticker"
)

_SQL_EVENTS_FOR_PULL = (
    "SELECT event_ticker, series_ticker, commence_ms, close_ms, status "
    "FROM kalshi_events WHERE event_ticker IN ("
    "SELECT event_ticker FROM kalshi_markets "
    f"WHERE ticker IN ({_PINNED_TICKERS})) ORDER BY event_ticker"
)

_SQL_CLOSING_LINES_FOR_PULL = (
    "SELECT id, ticker, horizon_hours, observed_ms, yes_bid_tenths, "
    "yes_ask_tenths FROM closing_lines "
    f"WHERE ticker IN ({_PINNED_TICKERS}) ORDER BY ticker, horizon_hours"
)

_SQL_SERIES = (
    "SELECT series_ticker, league FROM kalshi_series ORDER BY series_ticker"
)


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


def _q_credits_tail(conn: sqlite3.Connection, args) -> list[Section]:
    section = _fetch(
        conn,
        _SQL_CREDITS_TAIL,
        (),
        title=f"api_credits: last {args.tail} rows, newest first",
        cap=args.limit,
        requested=args.tail,
    )
    return [_derive_iso(section, "called_ms", "called_iso")]


def _q_credits_day(conn: sqlite3.Connection, args) -> list[Section]:
    if not args.date:
        raise ValueError(
            "credits-day needs --date YYYYMMDD. It is not defaulted to today: "
            "the question this query answers is about a specific past day, and "
            "a guessed date would answer a different one silently."
        )
    start_ms, end_ms = _day_bounds(args.date, args.day_start_hour)
    rows = _fetch(
        conn,
        _SQL_CREDITS_DAY_ROWS,
        (start_ms, end_ms),
        title=f"api_credits: budget day {args.date} (starts {args.day_start_hour:02d}:00Z)",
        cap=args.limit,
    )
    totals = _fetch(
        conn,
        _SQL_CREDITS_DAY_TOTALS,
        (start_ms, end_ms),
        title="api_credits: row count and summed cost for that day",
        cap=args.limit,
    )
    return [
        _window_section("budget day window", start_ms, end_ms),
        _derive_iso(rows, "called_ms", "called_iso"),
        totals,
    ]


def _q_credits_month(conn: sqlite3.Connection, args) -> list[Section]:
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_ms = _month_start_ms(now_ms)
    totals = _fetch(
        conn,
        _SQL_CREDITS_MONTH,
        (start_ms,),
        title="api_credits: month to date",
        cap=args.limit,
    )
    return [_window_section("calendar month window (UTC)", start_ms, None), totals]


def _q_sweep_log(conn: sqlite3.Connection, args) -> list[Section]:
    groups = _fetch(
        conn,
        _SQL_SWEEP_LOG_GROUPS,
        (),
        title="odds_sweep_log: count and pass_ms range by outcome",
        cap=args.limit,
    )
    groups = _derive_iso(groups, "min_pass_ms", "min_pass_iso")
    groups = _derive_iso(groups, "max_pass_ms", "max_pass_iso")
    tail = _fetch(
        conn,
        _SQL_SWEEP_LOG_TAIL,
        (),
        title=f"odds_sweep_log: last {args.tail} rows, newest first",
        cap=args.limit,
        requested=args.tail,
    )
    return [groups, _derive_iso(tail, "pass_ms", "pass_iso")]


def _q_results_for_pull(conn: sqlite3.Connection, args) -> list[Section]:
    return [
        _fetch(
            conn,
            _SQL_RESULTS_FOR_PULL,
            {"pin": args.pin},
            title=f"kalshi_markets for recommendations.id <= {args.pin}",
            cap=args.limit,
        )
    ]


def _q_events_for_pull(conn: sqlite3.Connection, args) -> list[Section]:
    return [
        _fetch(
            conn,
            _SQL_EVENTS_FOR_PULL,
            {"pin": args.pin},
            title=f"kalshi_events reached by recommendations.id <= {args.pin}",
            cap=args.limit,
        )
    ]


def _q_closing_lines_for_pull(conn: sqlite3.Connection, args) -> list[Section]:
    return [
        _fetch(
            conn,
            _SQL_CLOSING_LINES_FOR_PULL,
            {"pin": args.pin},
            title=f"closing_lines for recommendations.id <= {args.pin}",
            cap=args.limit,
        )
    ]


def _q_series(conn: sqlite3.Connection, args) -> list[Section]:
    return [
        _fetch(
            conn,
            _SQL_SERIES,
            (),
            title="kalshi_series: ticker and league",
            cap=args.limit,
        )
    ]


@dataclass(frozen=True)
class QueryDef:
    description: str
    run: Callable[[sqlite3.Connection, Any], list[Section]]


QUERIES: dict[str, QueryDef] = {
    "credits-tail": QueryDef(
        "The last N api_credits rows (-n, default 5), newest first, each "
        "called_ms also rendered ISO-8601 UTC. Answers: what remaining_reported "
        "did the most recent response carry?",
        _q_credits_tail,
    ),
    "credits-day": QueryDef(
        "Every api_credits row in one budget day (--date YYYYMMDD, boundary "
        "--day-start-hour, default 10), plus the row count and summed cost.",
        _q_credits_day,
    ),
    "credits-month": QueryDef(
        "Month-to-date summed cost, and MIN/MAX of remaining_reported and "
        "used_reported, over the UTC calendar month.",
        _q_credits_month,
    ),
    "sweep-log": QueryDef(
        "odds_sweep_log: COUNT and pass_ms range grouped by outcome, then the "
        "last N rows in full (-n, default 5).",
        _q_sweep_log,
    ),
    "results-for-pull": QueryDef(
        "kalshi_markets (incl. result) for the pinned recommendation "
        "population (--pin, default 1564). ~120 rows.",
        _q_results_for_pull,
    ),
    "events-for-pull": QueryDef(
        "kalshi_events reached through the pinned markets. ~60 rows.",
        _q_events_for_pull,
    ),
    "closing-lines-for-pull": QueryDef(
        "closing_lines for the pinned tickers. ~240 rows.",
        _q_closing_lines_for_pull,
    ),
    "series": QueryDef(
        "kalshi_series: series_ticker and league. ~10 rows.",
        _q_series,
    ),
}


def resolve_query(name: str) -> QueryDef:
    """Look a query up on the whitelist, raising if it is not there.

    Deliberately not `argparse(choices=...)`. With `choices`, this function
    would be unreachable in production and a test exercising it would be
    testing dead code; here the rejection is on the only path a caller has.
    """
    try:
        return QUERIES[name]
    except KeyError as exc:
        raise UnknownQuery(
            f"unknown query {name!r}. Known queries: "
            + ", ".join(sorted(QUERIES))
        ) from exc


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
    return json.dumps(
        {
            "query": query,
            "db": db_path,
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


def _build_parser() -> argparse.ArgumentParser:
    listing = "\n".join(
        f"  {name:<24}{QUERIES[name].description}" for name in sorted(QUERIES)
    )
    parser = argparse.ArgumentParser(
        prog="inspect_live_db.py",
        description=(
            "Read-only inspector for the live cockpit database. Choose one of "
            "the named queries below; there is no free-form SQL argument."
        ),
        epilog="queries:\n" + listing,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("query", metavar="QUERY", help="one of the names listed below")
    parser.add_argument(
        "--db", default=DEFAULT_DB, help=f"database path (default {DEFAULT_DB})"
    )
    parser.add_argument(
        "-n",
        "--tail",
        type=int,
        default=5,
        help="rows for the tail queries (default 5)",
    )
    parser.add_argument("--date", help="budget day for credits-day, as YYYYMMDD")
    parser.add_argument(
        "--day-start-hour",
        type=int,
        default=DEFAULT_DAY_START_HOUR,
        help=f"UTC hour the budget day starts (default {DEFAULT_DAY_START_HOUR})",
    )
    parser.add_argument(
        "--pin",
        type=int,
        default=1564,
        help="recommendations.id ceiling for the *-for-pull queries (default 1564)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_ROW_CAP,
        help=f"hard row cap per section (default {DEFAULT_ROW_CAP})",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        query = resolve_query(args.query)
    except UnknownQuery as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        conn = connect_readonly(args.db)
    except sqlite3.OperationalError as exc:
        print(f"cannot open {args.db} read-only: {exc}", file=sys.stderr)
        return 3

    try:
        sections = query.run(conn, args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        conn.close()

    render = render_json if args.json else render_text
    print(render(args.query, args.db, sections))
    return 0


# ---------------------------------------------------------------------------
# This file refused to run until 2026-08-10, because its authoring lane died on
# a session limit before writing a single test and an unverified reader pointed
# at `/data/cockpit.db` is exactly what this repo's mutation rule exists for.
#
# The refusal is lifted by `tests/test_inspect_live_db.py`, which builds its
# database by executing `backend/store/schema.sql` verbatim -- so a query naming
# a column the live box does not have fails locally -- and which observed every
# guard here go red under a named mutation: `mode=ro` widened to `mode=rwc`; the
# unknown-query raise softened to `QUERIES.get`; the cap's `+1` truncation probe
# removed; `>` widened to `>=` at exactly the cap; the `effective == cap` clause
# dropped so a query's own `-n` reported as truncation; the `0 rows` branch
# deleted; `_iso(None)` folded to the epoch; and `--pin` opened up. The mutation
# is written beside each test.
#
# What is still NOT established is in that file's docstring, and the shortest
# version of it is: a green suite says these eight queries are well-formed and
# their guards fire. It says nothing about what the live database contains.
# ---------------------------------------------------------------------------


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
