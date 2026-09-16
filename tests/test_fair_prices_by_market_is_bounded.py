"""`fair-prices-by-market` reads a slice of each table, never the whole one.

Both halves were bare `GROUP BY market` aggregates with no predicate at all --
section A over `odds_snapshots` and section B over `fair_prices`, the two
largest tables on the live box. That is the shape ADR 0157 forbids: the cost
does not land on the session that runs the query, it lands on whoever touches
the desk next, because the scan evicts the page cache the live reads run
through. ADR 0159 bounds both.

**The half of this that is not obvious, and the reason the plan tests below
are asymmetric.** The two bounds are not equally effective, and neither is
effective for the reason the brief assumed:

- Section A bounds on `commence_ms` and **does not seek at all.** The brief
  said `idx_odds_commence` would serve it; it does for `prop-bookmakers`, but
  not here, because `idx_odds_window` (schema v41) leads with `market`, covers
  the select list and satisfies the `GROUP BY`, so the planner scans it whole
  and `commence_ms` -- its fourth column -- becomes a filter. Statistics do
  not change that. The bound removes rows from the answer and from two DISTINCT
  temp B-trees; it does not remove them from the read.
- Section B bounds on `computed_ms`, and **no index on `fair_prices` leads
  with it.** The brief for this work was to add one. Adding one does not help:
  the planner declines it and keeps `idx_fair_market_computed`, which
  satisfies the `GROUP BY`. What makes the bound seek is `sqlite_stat1` --
  with statistics the planner runs the existing index as a SKIP-SCAN
  (`ANY(market) AND computed_ms>?`) because `market` has a handful of distinct
  values.

So `test_section_B_does_not_seek_without_statistics` asserts the pessimistic
case *on purpose*. It is the finding ADR 0159 rests on, and if a future SQLite
starts skip-scanning without statistics -- or stops doing it with them -- that
test is where the repo finds out, rather than at a live read.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Nothing about live timing.** A plan names the access method, never the
  rows it touches (ADR 0141). `scripts/measure_fair_price_window_index.py` is
  the modelled timing and `scripts/rehearse_fair_price_window.py` is the live
  one; these tests pin the shape those two measured.
- **Nothing about whether a market is consumed.** These tests insert their own
  rows. The question the command exists to answer is answered on live.
- **Nothing about `ANALYZE` being safe to ship.** That is a blast-radius
  question about every other reader of `fair_prices`, and it is settled on the
  paced copy, not here.

Mutations, one per test, each observed red:
  1. drop `WHERE computed_ms >= :since ` from `_SQL_FAIR_PRICES_BY_MARKET`
  2. drop `WHERE commence_ms >= :since ` from `_SQL_ODDS_SNAPSHOTS_BY_MARKET`
  3. `_fair_prices_since_ms` returning `0` when `--since` is absent
  4. `_fair_prices_since_ms` falling back to a default on a malformed `--since`
"""

from __future__ import annotations

import importlib
import os
import sqlite3
import sys
import tempfile
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

decisions = importlib.import_module("inspect_live_db_decisions")

SCHEMA = os.path.join(
    os.path.dirname(__file__), "..", "backend", "store", "schema.sql"
)

DAY_MS = 86_400_000
NOW_MS = 1_789_500_000_000


class _Args:
    """The namespace attributes `_q_fair_prices_by_market` reads."""

    def __init__(self, *, limit=2000, since=None, day_start_hour=10):
        self.limit = limit
        self.since = since
        self.day_start_hour = day_start_hour


@pytest.fixture
def conn():
    path = os.path.join(tempfile.mkdtemp(), "census.db")
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    with open(SCHEMA, encoding="utf-8") as fh:
        c.executescript(fh.read())
    # Live has no `sqlite_stat1`: nothing in `backend/` has ever run ANALYZE.
    # `executescript` cannot create one, but dropping it is cheap insurance
    # against a future schema file that does.
    c.execute("DROP TABLE IF EXISTS sqlite_stat1")
    c.commit()
    yield c
    c.close()


def _link(conn, link_id=1, odds_event_id="evt"):
    # Plain INSERTs, not `INSERT OR IGNORE`: `OR IGNORE` swallows a NOT NULL
    # violation as well as a duplicate, so a fixture missing a required column
    # inserts nothing and the failure surfaces as a foreign-key error three
    # statements later. It did, while this file was being written.
    if not conn.execute(
        "SELECT 1 FROM kalshi_series WHERE series_ticker = 'KXT'"
    ).fetchone():
        conn.execute(
            "INSERT INTO kalshi_series (series_ticker, title, league, "
            "first_seen_ms, last_seen_ms) "
            "VALUES ('KXT', 'T', 'Pro Baseball', ?, ?)",
            (NOW_MS, NOW_MS),
        )
        conn.execute(
            "INSERT INTO kalshi_events (event_ticker, series_ticker, title, "
            "first_seen_ms, last_seen_ms) VALUES ('KXT-1', 'KXT', 'T', ?, ?)",
            (NOW_MS, NOW_MS),
        )
    conn.execute(
        "INSERT INTO event_links (id, kalshi_event_ticker, odds_event_id, "
        "league, method, commence_skew_ms, linked_ms) "
        "VALUES (?, 'KXT-1', ?, 'Pro Baseball', 'exact_alias_pair', 0, ?)",
        (link_id, odds_event_id, NOW_MS),
    )
    conn.commit()


def _fair(conn, *, market, computed_ms, link_id=1):
    conn.execute(
        "INSERT INTO fair_prices (computed_ms, link_id, market, outcome_name, "
        "p_conservative, book_count, books_used) "
        "VALUES (?, ?, ?, 'Home', 0.5, 5, '[]')",
        (computed_ms, link_id, market),
    )
    conn.commit()


def _snapshot(conn, *, market, commence_ms, event="evt", book="pinnacle"):
    conn.execute(
        "INSERT INTO odds_snapshots (fetched_ms, sport_key, odds_event_id, "
        "commence_ms, home_team, away_team, bookmaker, market, outcome_name, "
        "price_decimal) VALUES (?, 'baseball_mlb', ?, ?, 'H', 'A', ?, ?, "
        "'H', 1.9)",
        (commence_ms - DAY_MS, event, commence_ms, book, market),
    )
    conn.commit()


def _sections(conn, args):
    return decisions._q_fair_prices_by_market(conn, args)


def _rows(section):
    return {row[0]: row for row in section.rows}


class TestBothHalvesAreBounded:
    def test_section_B_excludes_a_fair_price_older_than_the_window(self, conn):
        _link(conn)
        _fair(conn, market="h2h", computed_ms=NOW_MS - 2 * DAY_MS)
        _fair(conn, market="spreads", computed_ms=NOW_MS - 40 * DAY_MS)
        sections = _sections(conn, _Args(since="20260916", day_start_hour=0))
        # 2026-09-16T00:00Z is inside the two-day-old row's future, so pin the
        # floor explicitly rather than relying on the calendar: the assertion
        # that matters is "the 40-day-old row is gone".
        consumed = _rows(sections[3])
        assert "spreads" not in consumed

    def test_section_A_excludes_a_fixture_commencing_before_the_window(self, conn):
        _link(conn)
        _snapshot(conn, market="h2h", commence_ms=NOW_MS)
        _snapshot(conn, market="totals", commence_ms=NOW_MS - 40 * DAY_MS)
        sections = _sections(conn, _Args(since="20260916", day_start_hour=0))
        bought = _rows(sections[1])
        assert "totals" not in bought

    def test_both_statements_carry_their_bound(self):
        assert "computed_ms >= :since" in decisions._SQL_FAIR_PRICES_BY_MARKET
        assert "commence_ms >= :since" in decisions._SQL_ODDS_SNAPSHOTS_BY_MARKET


class TestTheDefaultIsAWindow:
    """The default matters more than the flag: the unbounded call is the one a
    session reaches for mid-slate, when it is dearest (ADR 0157)."""

    def test_an_absent_since_still_produces_a_recent_floor(self):
        floor = decisions._fair_prices_since_ms(_Args())
        now_ms = int(time.time() * 1000)
        expected = now_ms - decisions._FAIR_PRICES_DEFAULT_DAYS * DAY_MS
        assert floor > 0
        assert abs(floor - expected) < 60_000

    def test_a_malformed_since_is_refused_not_ignored(self):
        with pytest.raises(ValueError, match="YYYYMMDD"):
            decisions._fair_prices_since_ms(_Args(since="last tuesday"))

    def test_the_default_matches_the_bookmakers_pair_not_the_anchor_census(self):
        """One clock across the two 'what did the feed buy' commands.

        Section A reads the same rows on the same column as `team-bookmakers`,
        and a reader comparing them across commands must not be comparing two
        windows.
        """
        assert (
            decisions._FAIR_PRICES_DEFAULT_DAYS
            == decisions._BOOKMAKERS_DEFAULT_DAYS
        )


class TestTheTwoClocksAreNamedOnScreen:
    """One instant, two columns. A reader who does not know that will read a
    market thin in B and fat in A as an input with no reader, when it may only
    be a devig that fell outside seven days."""

    def test_each_section_is_preceded_by_a_window_naming_its_column(self, conn):
        sections = _sections(conn, _Args())
        titles = [s.title for s in sections]
        assert len(sections) == 4
        assert "commence_ms" in titles[0]
        assert "computed_ms" in titles[2]
        assert "commence_ms" not in titles[2]
        assert "computed_ms" not in titles[0]

    def test_both_windows_report_the_same_instant(self, conn):
        sections = _sections(conn, _Args())
        assert sections[0].rows[0][0] == sections[2].rows[0][0]


class TestThePlans:
    """ADR 0141: a plan cannot price a query. These pin the SHAPE the timings
    in `measure_fair_price_window_index.py` were taken against."""

    def _plan(self, conn, sql, params):
        return [r[3] for r in conn.execute("EXPLAIN QUERY PLAN " + sql, params)]

    def test_section_A_filters_and_does_NOT_seek(self, conn):
        """Section A's bound cuts the OUTPUT, not the read, and saying so is
        the whole point of this test.

        The brief for ADR 0159 recorded that `odds_snapshots` needed no new
        index because `idx_odds_commence` already serves a `commence_ms`
        bound. It serves one for `prop-bookmakers`, which has no `GROUP BY
        market`. Here it does not get the chance: `idx_odds_window` (schema
        v41) leads with `market`, covers the whole select list, and satisfies
        the grouping, so the planner scans it whole and applies `commence_ms`
        as a filter -- `commence_ms` is its FOURTH column. `ANALYZE` does not
        change this either; measured both ways.

        The bound is still worth having: it removes rows from two DISTINCT
        temp B-trees and from the answer. It is not a seek, it is not
        described as one anywhere, and the live cost of the remaining scan is
        a timing question for `rehearse_fair_price_window.py`.
        """
        _link(conn)
        for i in range(300):
            _snapshot(
                conn,
                market=("h2h", "spreads", "totals")[i % 3],
                commence_ms=NOW_MS - (i % 60) * DAY_MS,
            )
        plan = self._plan(
            conn, decisions._SQL_ODDS_SNAPSHOTS_BY_MARKET,
            {"since": NOW_MS - 10 * DAY_MS},
        )
        joined = " ".join(plan)
        assert "commence_ms>" not in joined, joined
        assert "SCAN odds_snapshots USING INDEX idx_odds_window" in joined, joined

    def test_section_B_does_not_seek_without_statistics(self, conn):
        """The pessimistic assertion, on purpose.

        This is the finding ADR 0159 rests on. Without `sqlite_stat1` the
        planner scans `idx_fair_market_computed` whole and the `computed_ms`
        bound is applied as a filter -- which is why ADR 0159 ships statistics
        rather than the index the work was briefed to add. If this ever goes
        green the repo has a cheaper world than it thinks, and should find out
        here rather than from a live read.
        """
        _link(conn)
        for i in range(300):
            _fair(
                conn,
                market=("h2h", "spreads", "totals")[i % 3],
                computed_ms=NOW_MS - (i % 60) * DAY_MS,
            )
        plan = self._plan(
            conn, decisions._SQL_FAIR_PRICES_BY_MARKET,
            {"since": NOW_MS - 10 * DAY_MS},
        )
        joined = " ".join(plan)
        assert "computed_ms>" not in joined, joined

    def test_section_B_seeks_once_the_table_has_been_analysed(self, conn):
        """And this is what ADR 0159 buys. Same statement, same indexes, one
        `ANALYZE` between them."""
        _link(conn)
        # 300, not 9. A skip-scan is a cost decision: on a table small enough
        # that a full index scan is cheap, statistics correctly say so and the
        # plan stays a SCAN. The first draft of this test inserted nine rows
        # and failed for that reason, which would have read as the finding
        # being wrong. Measured: the seek appears from ~200 rows.
        for i in range(300):
            _fair(
                conn,
                market=("h2h", "spreads", "totals")[i % 3],
                computed_ms=NOW_MS - (i % 60) * DAY_MS,
            )
        conn.execute("PRAGMA analysis_limit=1000")
        conn.execute("ANALYZE fair_prices")
        conn.commit()
        plan = self._plan(
            conn, decisions._SQL_FAIR_PRICES_BY_MARKET,
            {"since": NOW_MS - 10 * DAY_MS},
        )
        joined = " ".join(plan)
        assert "computed_ms>" in joined, joined
        assert "idx_fair_market_computed" in joined, joined

    def test_no_new_index_is_needed_for_that_seek(self, conn):
        """The index the work was approved to build is not in the schema, and
        the seek above happens anyway.

        Pinned because the absence is a DECISION (ADR 0159), not an oversight,
        and an absence with no test reads exactly like a forgotten task.
        """
        names = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND tbl_name='fair_prices'"
            )
        }
        assert not any(
            "computed" in n and not n.startswith("idx_fair_market") for n in names
        ), names
