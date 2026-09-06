"""The odds feed: what it bought, when it swept, and how fresh it was.

Queries: `credits-tail`, `credits-day`, `credits-month`, `sweep-log`,
`prune-frontier`, `window-freshness`, `book-rows`, `visit-freshness`.

One domain, read in one direction: money out (`api_credits`), passes taken
(`odds_sweep_log`), rows kept (`kalshi_quotes` and its prune frontier), and
the age of the consensus a visitor to the desk was actually shown
(`fixture_freshness` recomputed at a stated instant, joined to
`desk_attention`). The credit ceiling and the staleness a visit met are the
same question asked at two ends of one pipe, which is why they share a file.

**Every SQL string in this module is a constant.** No caller-supplied value
reaches the SQL text; every number a caller can influence is a bound
parameter. This module is imported by `inspect_live_db.py`, is never run
directly, and inherits every disclaimer in that file's docstring.
"""

from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from inspect_live_db_common import (
    Section,
    _MS_PER_DAY,
    _day_bounds,
    _derive_iso,
    _fetch,
    _iso,
    _month_start_ms,
    _quantile,
    _window_section,
)


# ---------------------------------------------------------------------------
# The whitelist. Every SQL string below is a constant.
# ---------------------------------------------------------------------------

# `trigger` is quoted because it is a SQLite keyword, and it is selected because
# the sweep banner's predicate turns on it: a row counts as a *served* sweep only
# when `endpoint LIKE '%/odds' AND cost > 0 AND COALESCE(trigger, '') != 'manual'`
# (`backend/odds/timing.py`, `_SERVED_SWEEP`). Without this column the output
# cannot tell a hand refresh from a scheduled sweep, so a day whose only `/odds`
# rows were taps reads exactly like a day that swept -- an instrument blind to
# the one clause under investigation. See `tasks/lessons.md`.
_CREDIT_COLUMNS = (
    'called_ms, endpoint, sport_key, markets, regions, cost, '
    'remaining_reported, used_reported, "trigger"'
)
# `markets` and `regions` are here for the same reason `trigger` is, and the
# omission had the same shape. `cost` is `len(markets) * len(regions)`, so a row
# recording 6 credits was bought under three markets and one recording 2 under
# one -- but reading the *cost* to infer the *config* is an inference, and the
# row carries both directly. When `ODDS_MARKETS` changed from three markets to
# `h2h` on 2026-08-16, the only available confirmation that the deployed image
# had picked it up was the machine's environment, which says what the process
# was started with rather than what it sent. These two columns say what was
# sent. `"trigger"` stays quoted because it is a SQL keyword; the other two are
# not.

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


# The prune's own retention window, duplicated here rather than imported: this
# script is deliberately stdlib-only so the code that runs against the money box
# carries no import graph. `tests/test_inspect_live_db.py` asserts it still
# equals `retention.DEFAULT_QUOTE_RETENTION_MS`, so the duplication is checked
# rather than trusted.
_QUOTE_RETENTION_MS = 3 * 24 * 60 * 60 * 1000

# **The prune frontier: how far `prune_quotes` has actually got.**
#
# `quotes_pruned` is persisted nowhere -- it exists only in a `PassCounts` field
# that reaches the process log, and `flyctl logs` drops lines. So on 2026-08-20
# the window-gate registration's observation 1 ("no prune inside an open
# window") had no durable reading at all and had to be reported at log strength.
# This is that reading.
#
# **`COALESCE(confirmed_ms, observed_ms)`, matching `retention.py:206` exactly.**
# The obvious `MIN(observed_ms)` is wrong and wrong in the direction that
# flatters: ADR 0055 made the table a change log, so a market whose price has
# not moved in three days keeps one row with an ancient `observed_ms` and a
# current `confirmed_ms`. That row survives every prune, and a frontier computed
# on `observed_ms` therefore sits still through a prune that deleted 40,000
# rows -- reading as "no prune ran" when one did.
#
# The `NOT IN (SELECT ticker FROM recommendations)` half matters for the same
# reason: rows the prune is not allowed to touch are not part of its frontier.
#
# How to use it. `frontier_iso` advances only when a prune actually deletes, so
# comparing it either side of a window says whether one ran inside. When the
# backlog is 0 the frontier also tracks `cutoff_iso`, and then
# `frontier + retention` dates the last prune on its own.
#
# `backlog_rows` is the denominator, and it is the check to make first: if it is
# 0 the prune would delete nothing whenever it ran, and a zero prune inside a
# window says nothing about any gate.
_SQL_PRUNE_FRONTIER = (
    "SELECT "
    "  (SELECT MIN(COALESCE(confirmed_ms, observed_ms)) FROM kalshi_quotes"
    "     WHERE ticker NOT IN (SELECT ticker FROM recommendations))"
    "    AS frontier_ms, "
    "  :cutoff AS cutoff_ms, "
    "  (SELECT COUNT(*) FROM kalshi_quotes"
    "     WHERE COALESCE(confirmed_ms, observed_ms) < :cutoff"
    "       AND ticker NOT IN (SELECT ticker FROM recommendations))"
    "    AS backlog_rows, "
    "  (SELECT COUNT(*) FROM kalshi_quotes"
    "     WHERE ticker NOT IN (SELECT ticker FROM recommendations))"
    "    AS prunable_rows, "
    "  (SELECT COUNT(*) FROM kalshi_quotes) AS total_rows"
)


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


def _q_prune_frontier(conn: sqlite3.Connection, args) -> list[Section]:
    """How far `prune_quotes` has got, and whether it still has anything to do.

    `now` is stamped here and printed, because a frontier is a claim about a
    moment and the moment is half the reading.

    What this does not establish
    ----------------------------
    - **Not when the last prune ran**, on its own, while `backlog_rows > 0`. A
      backlogged prune deletes a bounded batch and stops, so the frontier lags
      the cutoff by an unknown amount and only *changes* are interpretable.
      Take it either side of the window you care about.
    - **Nothing about `unmatched_items`**, which has its own retention, its own
      budget and its own frontier. This reads the quotes prune only.
    """
    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    section = _fetch(
        conn,
        _SQL_PRUNE_FRONTIER,
        {"cutoff": now - _QUOTE_RETENTION_MS},
        title=(
            f"prune frontier at {_iso(now)} "
            f"(retention {_QUOTE_RETENTION_MS // 86_400_000}d)"
        ),
        cap=args.limit,
    )
    section = _derive_iso(section, "frontier_ms", "frontier_iso")
    return [_derive_iso(section, "cutoff_ms", "cutoff_iso")]


# ---------------------------------------------------------------------------
# window-freshness: `fixture_freshness` recomputed at a stated instant
# ---------------------------------------------------------------------------

# The same shape as `backend/odds/timing.py::fixture_freshness`, with ONE
# deliberate addition: `fetched_ms <= :at`, so the query can be pinned at a
# past instant. At `--at now` the predicate is vacuous (no fetch is in the
# future) and the two are the same query. Ages here are `:at - oldest`, where
# oldest is the production measure -- within each fixture's most recent sweep,
# the oldest contributing book's own `last_update`, falling back to our fetch
# time. The production function's known approximation is inherited unchanged:
# it does NOT drop books that fail to quote every outcome, so a fixture can
# read staler here than the runner will find it.
_SQL_FRESHNESS_AT_FIXTURES = (
    "WITH latest AS ("
    "  SELECT odds_event_id, MAX(fetched_ms) AS m FROM odds_snapshots"
    "  WHERE market = 'h2h' AND fetched_ms <= :at AND commence_ms >= :at"
    "  GROUP BY odds_event_id"
    ") "
    "SELECT o.odds_event_id, o.sport_key,"
    "       MIN(o.commence_ms) AS commence_ms,"
    "       l.m AS fetched_ms,"
    "       COUNT(DISTINCT o.bookmaker) AS books,"
    "       MIN(COALESCE(o.book_updated_ms, o.fetched_ms)) AS oldest_ms,"
    "       MAX(COALESCE(o.book_updated_ms, o.fetched_ms)) AS newest_ms,"
    "       :at - MIN(COALESCE(o.book_updated_ms, o.fetched_ms)) AS age_ms "
    "FROM odds_snapshots o JOIN latest l"
    "  ON o.odds_event_id = l.odds_event_id AND o.fetched_ms = l.m "
    "WHERE o.market = 'h2h' "
    "GROUP BY o.odds_event_id "
    "ORDER BY age_ms"
)

# The same latest-sweep population, grouped by book instead of fixture. The
# window indicator takes MIN over books per fixture, so ONE book whose
# `last_update` the aggregator has not advanced drags every fixture it quotes
# toward "stale". This section is what names that book.
_SQL_FRESHNESS_AT_BOOKS = (
    "WITH latest AS ("
    "  SELECT odds_event_id, MAX(fetched_ms) AS m FROM odds_snapshots"
    "  WHERE market = 'h2h' AND fetched_ms <= :at AND commence_ms >= :at"
    "  GROUP BY odds_event_id"
    ") "
    "SELECT o.bookmaker,"
    "       COUNT(DISTINCT o.odds_event_id) AS fixtures,"
    "       MIN(COALESCE(o.book_updated_ms, o.fetched_ms)) AS oldest_ms,"
    "       MAX(COALESCE(o.book_updated_ms, o.fetched_ms)) AS newest_ms,"
    "       :at - MIN(COALESCE(o.book_updated_ms, o.fetched_ms)) AS worst_age_ms "
    "FROM odds_snapshots o JOIN latest l"
    "  ON o.odds_event_id = l.odds_event_id AND o.fetched_ms = l.m "
    "WHERE o.market = 'h2h' "
    "GROUP BY o.bookmaker "
    "ORDER BY worst_age_ms DESC"
)


def _parse_at_ms(value: Optional[str]) -> int:
    """`--at` as epoch milliseconds. Digits pass through; ISO-8601 is parsed.

    A malformed value raises ValueError (exit 2 via main) rather than falling
    back to "now": a typo'd instant answered with the present would read as a
    retrospective measurement and be one silently taken today.
    """
    if value is None:
        return int(datetime.now(timezone.utc).timestamp() * 1000)
    if value.isdigit():
        return int(value)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            f"--at {value!r} is neither epoch milliseconds nor ISO-8601"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def _fixture_ages_at(
    conn: sqlite3.Connection, at_ms: int, *, cap: int, title: str
) -> Section:
    """The per-fixture consensus ages the window indicator computes at `at_ms`.

    One function, two readers: `window-freshness` prints it, and
    `visit-freshness` reads it once per visit. A second copy of the SQL would
    be a second definition of "how old were the prices", which is the drift
    this file's `_ACTIONABLE_PREDICATE` comment records.
    """
    return _fetch(
        conn, _SQL_FRESHNESS_AT_FIXTURES, {"at": at_ms}, title=title, cap=cap
    )


def _q_window_freshness(conn: sqlite3.Connection, args) -> list[Section]:
    """`fixture_freshness` at `--at`, per fixture and then per book.

    What this does not establish
    ----------------------------
    - **Not what the loop read at that instant.** Rows written or pruned since
      then change the answer; a retrospective read is honest only while the
      sweeps around the instant are still in `odds_snapshots`. Compare
      `fetched_ms` against the sweep log before believing an age.
    - **Nothing about why a stamp is old** -- a stale `last_update` cannot
      separate "the book has not repriced" from "the aggregator has not
      re-crawled it" (2026-08-11 repeat-poll result).
    """
    at_ms = _parse_at_ms(args.at)
    fixtures = _fixture_ages_at(
        conn,
        at_ms,
        cap=args.limit,
        title=f"fixture_freshness at {_iso(at_ms)}: per fixture, freshest first",
    )
    for col, iso in (
        ("commence_ms", "commence_iso"),
        ("fetched_ms", "fetched_iso"),
        ("oldest_ms", "oldest_iso"),
    ):
        fixtures = _derive_iso(fixtures, col, iso)
    books = _fetch(
        conn,
        _SQL_FRESHNESS_AT_BOOKS,
        {"at": at_ms},
        title=(
            f"same population by book at {_iso(at_ms)}: worst own-stamp age "
            "across the fixtures each book quotes, stalest first"
        ),
        cap=args.limit,
    )
    books = _derive_iso(books, "oldest_ms", "oldest_iso")
    return [fixtures, books]


# The h2h rows ONE book contributed to the exact population `window-freshness`
# reads -- the latest sweep per not-yet-commenced fixture at `:at`. Written to
# answer the question the dropout diagnosis had to leave conditional: a book
# quoting both outcomes *contributes* to the runner's consensus, so its stale
# stamp ages `odds_age_ms` and every row suppresses with the window; a book
# quoting one outcome is dropped by `book_quotes_for_event` and its stamp gates
# only the window flag, in which case the bounded sleeps skipped passes that
# could have confirmed live rows.
_SQL_BOOK_ROWS = (
    "WITH latest AS ("
    "  SELECT odds_event_id, MAX(fetched_ms) AS m FROM odds_snapshots"
    "  WHERE market = 'h2h' AND fetched_ms <= :at AND commence_ms >= :at"
    "  GROUP BY odds_event_id"
    ") "
    "SELECT o.bookmaker, o.odds_event_id, o.outcome_name, o.price_decimal,"
    "       o.book_updated_ms, o.fetched_ms "
    "FROM odds_snapshots o JOIN latest l"
    "  ON o.odds_event_id = l.odds_event_id AND o.fetched_ms = l.m "
    "WHERE o.market = 'h2h' AND (:book IS NULL OR o.bookmaker = :book) "
    "ORDER BY o.bookmaker, o.odds_event_id, o.outcome_name"
)


def _q_book_rows(conn: sqlite3.Connection, args) -> list[Section]:
    """A book's h2h rows in the window-freshness population at `--at`.

    Two rows per fixture means the book quotes both outcomes and contributes
    to the runner's consensus; one row means `book_quotes_for_event` drops it.
    Without `--book` every book's rows are listed, which on a live slate is
    ~30 books x 2 outcomes x the slate and still inside the default cap.

    What this does not establish
    ----------------------------
    - **Nothing about other markets.** h2h only, matching the freshness
      population; a book can be two-sided on h2h and absent on spreads.
    - **Nothing about the price's quality** -- presence, not correctness.
    """
    at_ms = _parse_at_ms(args.at)
    who = f"{args.book!r}" if args.book else "every book"
    section = _fetch(
        conn,
        _SQL_BOOK_ROWS,
        {"at": at_ms, "book": args.book},
        title=(
            f"h2h rows from {who} in the latest-sweep population "
            f"at {_iso(at_ms)}"
        ),
        cap=args.limit,
    )
    section = _derive_iso(section, "book_updated_ms", "book_updated_iso")
    return [_derive_iso(section, "fetched_ms", "fetched_iso")]


# ---------------------------------------------------------------------------
# visit-freshness: what the desk showed at each visit, read from the record
# ---------------------------------------------------------------------------
#
# Joe stopped opening the desk and gave one reason: "the prices are stale when
# I look". Attended odds buys fell 75 -> 5 a day over five days while the
# 300-credit attention slice sat ~7% used, so the staleness is NOT the slice
# ceiling. The hypothesis this query exists to test (2026-09-02): attention
# buys fire only while a page is open; the floor is hourly and only for a
# sport with a fixture inside twelve hours (`timing.py::desk_wants`); an
# unpaced first buy waits for the 900s full pass. So a cold open is allowed,
# by design, to show books up to ~60 minutes old plus up to ~15 minutes of
# bootstrap latency -- and a man who opens the desk once a day meets that
# worst case every time.
#
# Both halves of the instrument existed and nothing joined them:
# `desk_attention` holds the visits (append-only, one row per heartbeat,
# `Nav.tsx` every 60s) and `window-freshness --at` recomputes the consensus
# age at any instant. Until this query no inspector read `desk_attention`.

#: A gap between heartbeats longer than this ends a visit.
#:
#: Copied from `backend/odds/attention.py::DEFAULT_ATTENTION_TTL_MS` -- this
#: script imports nothing from `backend` (see `_ACTIONABLE_PREDICATE`) -- and
#: pinned equal by `tests/test_inspect_live_db.py`. It is the code's own
#: definition of the desk going shut: `is_attended` holds while the newest
#: stamp is inside the TTL, so a gap past it is an interval in which the loop
#: itself judged nobody was looking, and the stamp that ends it is a cold
#: open. Five heartbeat intervals, so an ordinary missed poll does not split a
#: visit in two.
_VISIT_GAP_MS = 300_000

#: The limit a consensus is refused as stale past, in seconds.
#:
#: `backend/config.py::StalenessConfig.load` reads `MAX_ODDS_AGE_S` with this
#: default (pinned equal by the tests). The same variable is read here from
#: the same environment the box runs the loop in, so the limit a visit is
#: measured against is the one the deployed loop applied.
_STALE_LIMIT_DEFAULT_S = 900
_STALE_LIMIT_ENV = "MAX_ODDS_AGE_S"

#: `--since` default: a week, because the question is about a five-day fall.
_VISIT_SINCE_DEFAULT_DAYS = 7

#: `path` is v34 (2026-09-05, question E) and is NULL for every stamp
#: written before it, which is most of the record. It is descriptive
#: only -- the loop never reads it -- so it is reported and never used
#: to cluster, filter or attribute a buy.
_SQL_ATTENTION_STAMPS = (
    "SELECT seen_ms, path FROM desk_attention WHERE seen_ms >= ? "
    "ORDER BY seen_ms"
)

# `trigger = 'attention'` is the spend a heartbeat causes and the only spend
# the slice counts (`timing.py::ATTENTION`). A floor or scheduled buy carries
# NULL and is deliberately not credited to the visit.
_SQL_FIRST_ATTENTION_BUY = (
    "SELECT called_ms, sport_key FROM api_credits "
    "WHERE trigger = 'attention' AND called_ms >= ? AND called_ms <= ? "
    "ORDER BY called_ms, id LIMIT 1"
)
_SQL_ATTENTION_BUYS_IN = (
    "SELECT COUNT(*) AS n FROM api_credits "
    "WHERE trigger = 'attention' AND called_ms >= ? AND called_ms <= ?"
)
_SQL_REFUSALS_IN = (
    "SELECT COUNT(*) AS n FROM odds_sweep_log "
    "WHERE outcome = 'refused' AND pass_ms >= ? AND pass_ms <= ?"
)


def _stale_limit_ms() -> int:
    """`MAX_ODDS_AGE_S` from the environment, in ms, defaulting as config does."""
    raw = os.environ.get(_STALE_LIMIT_ENV, "").strip()
    seconds = int(raw) if raw else _STALE_LIMIT_DEFAULT_S
    return seconds * 1000


def _cluster_visits(stamps: Sequence[int], gap_ms: int) -> list[list[int]]:
    """Runs of heartbeats with no gap over `gap_ms` between neighbours.

    Strictly over: a gap of exactly the TTL is the last instant at which
    `is_attended` still answers "open", so it must not open a visit here
    either. The two definitions have to agree at the boundary or a visit the
    loop bought for is counted here as two.
    """
    visits: list[list[int]] = []
    for ms in stamps:
        if visits and ms - visits[-1][-1] <= gap_ms:
            visits[-1].append(ms)
        else:
            visits.append([ms])
    return visits


@dataclass(frozen=True)
class _AgeReading:
    """What `_fixture_ages_at` said at one instant, reduced to a row's worth.

    `age_ms` is the **median** fixture age -- half the upcoming slate was at
    least this old. `age_min_ms` is the freshest fixture, which is what the
    window indicator's "open until" runs from. `None` throughout when no
    upcoming fixture was in the record at that instant: nothing to be stale.
    """

    fixtures: Optional[int]
    fresh: Optional[int]
    age_ms: Optional[int]
    age_min_ms: Optional[int]
    age_max_ms: Optional[int]
    sports_upcoming: Optional[str]
    sports_open: Optional[str]


def _read_ages(section: Section, *, limit_ms: int) -> _AgeReading:
    """Reduce a per-fixture freshness section to one reading.

    A truncated section is a cut population: the query orders by age so the
    minimum survives the cut, and everything else is unreadable -- `None`, not
    the count of the rows that happened to fit.
    """
    cols = section.columns
    age_i, sport_i = cols.index("age_ms"), cols.index("sport_key")
    if not section.rows:
        return _AgeReading(0, 0, None, None, None, None, None)
    ages = sorted(int(r[age_i]) for r in section.rows)
    if section.truncated:
        return _AgeReading(None, None, None, ages[0], None, None, None)
    fresh_rows = [r for r in section.rows if int(r[age_i]) <= limit_ms]
    median = _quantile(ages, 0.5)
    return _AgeReading(
        fixtures=len(ages),
        fresh=len(fresh_rows),
        age_ms=None if median is None else int(median),
        age_min_ms=ages[0],
        age_max_ms=ages[-1],
        sports_upcoming=",".join(sorted({str(r[sport_i]) for r in section.rows})),
        sports_open=",".join(sorted({str(r[sport_i]) for r in fresh_rows})),
    )


def _parse_since_ms(value: Optional[str], day_start_hour: int) -> int:
    if value is None:
        now_ms = int(time.time() * 1000)
        return now_ms - _VISIT_SINCE_DEFAULT_DAYS * _MS_PER_DAY
    try:
        return _day_bounds(value, day_start_hour)[0]
    except ValueError as exc:
        raise ValueError(
            f"--since must be YYYYMMDD, got {value!r}"
        ) from exc


_VISIT_COLUMNS = (
    "visit",
    "start_ms",
    "end_ms",
    "duration_s",
    "heartbeats",
    "first_fixtures",
    "first_fresh",
    "first_age_ms",
    "first_age_min_ms",
    "first_age_max_ms",
    "last_age_ms",
    "last_fresh",
    "attention_latency_ms",
    "first_attention_sport",
    "attention_buys",
    "refused_sweeps",
    "sports_upcoming",
    "sports_open",
    # Which screens the visit touched, newest-heartbeat-first, and how
    # many stamps carried no path at all. `paths_null` is not a zero:
    # it counts stamps from before v34 or from a client that sent none,
    # and a visit that is all-NULL is unreadable rather than pathless.
    "paths",
    "paths_null",
)


def _visit_paths(visit: list[int], path_at: dict) -> str:
    """The distinct screens a visit touched, most recent first.

    Order is by last heartbeat on that path rather than by count: the
    question this column answers is "what was he looking at", and a
    screen left open while he read it accumulates stamps without being
    the thing he moved to. Empty string when every stamp is NULL --
    which is unreadable, not "no screen", and `paths_null` beside it
    says how many.
    """
    ordered: list[str] = []
    for ms in reversed(visit):
        got = path_at.get(ms)
        if got and got not in ordered:
            ordered.append(got)
    return ", ".join(ordered)


def _q_visit_freshness(conn: sqlite3.Connection, args) -> list[Section]:
    """One row per desk visit: how stale the slate was when it opened.

    A visit is a run of `desk_attention` heartbeats with no gap over
    `--gap-ms` (default `_VISIT_GAP_MS`, the attention TTL). Per visit:

    - `first_age_ms` / `first_age_min_ms` / `first_age_max_ms`: the median,
      freshest and stalest upcoming-fixture consensus age at the FIRST stamp,
      computed by `_fixture_ages_at` -- the same query `window-freshness --at`
      prints -- pinned at that stamp, not at now. `first_fresh` of
      `first_fixtures` were inside the staleness limit.
    - `last_age_ms` / `last_fresh`: the same reading at the LAST stamp, which
      is what the visit bought itself by staying.
    - `attention_latency_ms`: ms from the first stamp to the first
      `api_credits` row with `trigger = 'attention'` inside the visit, `None`
      when the visit caused no buy at all. "Inside" runs to the last stamp
      plus the gap, because a buy the last heartbeat triggered can land after
      it; visits are more than the gap apart, so no buy is counted twice.
    - `refused_sweeps`: `odds_sweep_log` rows with `outcome = 'refused'` in
      the same span -- **the daily cap** saying no while he looked, and ONLY
      the daily cap. `REFUSED` is written only behind `budget.refusal_reason`
      in `backend/odds/client.py`; a slice-spent sport is demoted to the
      hourly floor and reaches this log only as `skipped`. So a zero here says
      nothing about the attention slice: source any "the slice was not the
      cause" sentence to `credits-day` by trigger, never to this column
      (`docs/measurements/2026-09-02-visit-freshness-first-read.md` §2, B1).
    - `sports_upcoming` / `sports_open`: sports with an upcoming fixture in
      the record at the first stamp, and the subset with at least one fixture
      inside the limit -- i.e. whose window the indicator would have shown
      open. An empty string is "none open"; `None` is "no upcoming fixture
      in the record at all", which is a different fact.

    The summary gives the visit count, the median first-stamp age, the share
    of visits with no attention buy, and the share whose first-stamp median
    age exceeded the limit (`MAX_ODDS_AGE_S`, read from the environment as
    `config.py` reads it) beside the sharper share with nothing fresh at all.

    What this does not establish
    ----------------------------
    - **n = 1.** One operator, one instance, one week. A share here is a
      description of Joe's visits, not a rate anything generalises from.
    - **It is a self-report joined to a record, not a measurement of the
      report.** "Stale when I look" is his sentence; this says what the record
      showed at the instants a browser said he was looking. A page open on a
      second monitor stamps exactly like a page being read
      (`attention.py`'s own caveat).
    - **Direction.** "Stale, so he stopped" and "stopped, so it is stale" are
      both consistent with any row here, because attention buys require an
      open page: a shorter visit buys fewer sweeps and mechanically makes the
      NEXT visit's first stamp staler. The table cannot separate cause from
      consequence, only say whether the worst case the design permits is the
      one he actually met.
    - **Nothing about why a stamp is old** -- inherited from
      `window-freshness`: a stale `last_update` cannot separate "the book has
      not repriced" from "the aggregator has not re-crawled it".
    - **`first_age_ms` (the MEDIAN fixture) is not a measure of the feed and
      is rendered on no screen.** `_fixture_ages_at` applies no commence
      horizon, and an age is a BOOK STAMP, so one bookmaker whose
      `last_update` has stopped advancing pins the median to wall clock and
      makes it immune to the feed buying -- which the first live read showed
      on 17 of 45 visits. **Lead with `first_age_min_ms` and `first_fresh`;
      quote `first_age_ms` only beside that separating check.** The three
      demonstrations, and why the largest contributor's share cannot be read
      off this table, are §3 of
      `docs/measurements/2026-09-02-visit-freshness-first-read.md` (B2).
    - **The latency is attributed by time window, not causally.** A buy
      already in flight when the page opened is attributed to the visit
      identically, and sub-second latencies are not the documented 5 s
      wake-poll mechanism. The tail matters and the median hides it.
    - **The last visit may be right-censored** by the query instant: its
      duration, heartbeats and last-stamp reading are truncated if the page
      was still open when the query ran.
    - **`sports_open` is a freshness fact, not the floor's 12 h test.** The
      floor's horizon is `DESK_FLOOR_HORIZON_MS` against `min(commences)`,
      and this instrument records no commence time, so it cannot say whether
      a no-buy visit was one the floor had correctly declined.
    - **Retrospective ages are durable.** There is no `DELETE FROM
      odds_snapshots` anywhere in `backend/`; `retention.prune_quotes` and
      `prune-frontier` concern `kalshi_quotes`. An old week reads as it was.

    Unreadable is `None`, never `0`: an age with no upcoming fixture, a
    latency with no buy, a truncated population's count.
    """
    gap_ms = args.gap_ms if args.gap_ms is not None else _VISIT_GAP_MS
    if gap_ms <= 0:
        raise ValueError(f"--gap-ms must be positive, got {gap_ms}")
    since_ms = _parse_since_ms(args.since, args.day_start_hour)
    limit_ms = _stale_limit_ms()

    seen = [
        (int(r[0]), r[1])
        for r in conn.execute(_SQL_ATTENTION_STAMPS, (since_ms,))
    ]
    stamps = [ms for ms, _ in seen]
    # Clustering is unchanged and still uses the timestamps alone: the
    # path must not decide where a visit begins or ends.
    path_at = dict(seen)
    visits = _cluster_visits(stamps, gap_ms)

    rows: list[tuple[Any, ...]] = []
    for n, visit in enumerate(visits, start=1):
        start, end = visit[0], visit[-1]
        span_end = end + gap_ms
        first = _read_ages(
            _fixture_ages_at(conn, start, cap=args.limit, title="first"),
            limit_ms=limit_ms,
        )
        last = _read_ages(
            _fixture_ages_at(conn, end, cap=args.limit, title="last"),
            limit_ms=limit_ms,
        )
        buy = conn.execute(_SQL_FIRST_ATTENTION_BUY, (start, span_end)).fetchone()
        buys = conn.execute(_SQL_ATTENTION_BUYS_IN, (start, span_end)).fetchone()
        refused = conn.execute(_SQL_REFUSALS_IN, (start, span_end)).fetchone()
        rows.append(
            (
                n,
                start,
                end,
                (end - start) // 1000,
                len(visit),
                first.fixtures,
                first.fresh,
                first.age_ms,
                first.age_min_ms,
                first.age_max_ms,
                last.age_ms,
                last.fresh,
                None if buy is None else int(buy[0]) - start,
                None if buy is None else buy[1],
                int(buys[0]),
                int(refused[0]),
                first.sports_upcoming,
                first.sports_open,
                _visit_paths(visit, path_at),
                sum(1 for ms in visit if path_at.get(ms) is None),
            )
        )

    cap = max(0, args.limit)
    per_visit = Section(
        title=(
            f"desk_attention visits since {_iso(since_ms)} (gap over "
            f"{gap_ms} ms opens a visit): one row per visit, oldest first"
        ),
        columns=_VISIT_COLUMNS,
        rows=rows[:cap],
        truncated=len(rows) > cap,
        cap=cap,
    )
    per_visit = _derive_iso(per_visit, "start_ms", "start_iso")
    per_visit = _derive_iso(per_visit, "end_ms", "end_iso")

    summary_rows: list[tuple[Any, ...]] = [
        ("visits", len(visits)),
        ("heartbeats", len(stamps)),
        ("visit_gap_ms", gap_ms),
        ("stale_limit_ms", limit_ms),
    ]
    if not visits:
        summary_rows.append(
            ("note", f"no visits since {_iso(since_ms)}: nothing to summarise")
        )
    else:
        col = {name: i for i, name in enumerate(_VISIT_COLUMNS)}
        readable = [r for r in rows if r[col["first_age_ms"]] is not None]
        first_ages = sorted(r[col["first_age_ms"]] for r in readable)
        first_mins = sorted(r[col["first_age_min_ms"]] for r in readable)
        latencies = sorted(
            r[col["attention_latency_ms"]]
            for r in rows
            if r[col["attention_latency_ms"]] is not None
        )
        no_buy = sum(1 for r in rows if r[col["attention_latency_ms"]] is None)
        over = sum(1 for r in readable if r[col["first_age_ms"]] > limit_ms)
        nothing_fresh = sum(1 for r in readable if r[col["first_fresh"]] == 0)
        n_all, n_read = len(rows), len(readable)
        summary_rows += [
            ("visits_with_readable_first_age", n_read),
            ("median_first_age_ms", _quantile(first_ages, 0.5)),
            ("median_first_age_min_ms", _quantile(first_mins, 0.5)),
            ("visits_no_attention_buy", no_buy),
            ("share_no_attention_buy", round(no_buy / n_all, 3)),
            ("median_attention_latency_ms", _quantile(latencies, 0.5)),
            ("visits_first_age_over_limit", over),
            (
                "share_first_age_over_limit",
                None if n_read == 0 else round(over / n_read, 3),
            ),
            ("visits_nothing_fresh_at_open", nothing_fresh),
            (
                "share_nothing_fresh_at_open",
                None if n_read == 0 else round(nothing_fresh / n_read, 3),
            ),
        ]
    summary = Section(
        title="visit-freshness summary (shares are of visits, n = 1 operator)",
        columns=("measure", "value"),
        rows=summary_rows,
    )
    return [
        _window_section("visit window", since_ms, None),
        per_visit,
        summary,
    ]
