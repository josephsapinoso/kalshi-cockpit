"""`scout-briefings` (#125): unattended convenings vs Joe's taps, by day.

#118's "Done when" item 3 asks for a reading of what unattended scouting
did. Before this ticket, `grep` over `scripts/` returned ZERO readers of
`scout_briefings` -- `/api/scout` serves the last 50 rows but its `SELECT`
(`backend/api/routers/scout.py:325-330`) never reads `trigger`, so no served
surface could tell an unattended convening (`trigger = 'auto'`,
`backend/scout_watch.py`, ADR 0180) from one Joe tapped
(`trigger = 'tap'`) -- which is the whole point of the v51 column
(`backend/store/schema.sql`).

WHAT THIS FILE DOES NOT ESTABLISH
----------------------------------
- **Nothing about the live database's contents.** Every row here is inserted
  by this file, exactly like every other member of the
  `inspect_live_db` test family (see `tests/test_inspect_live_db.py`'s own
  module docstring).
- **Nothing about pre-flight refusals.** `_q_scout_briefings`'s own docstring
  (`scripts/inspect_live_db_parlays.py`) states why `refusal_reason` cannot
  report the ceilings that refuse a convening before it starts -- those
  `return`/`raise` before any `INSERT`. This file's refusal test seeds only
  the ONE shape that IS reachable: a row that reaches `status = 'refused'`
  from inside an already-started desk run.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.inspect_live_db import (
    CHEAP,
    QUERIES,
    _day_bounds,
)
from scripts.inspect_live_db_parlays import (
    _SCOUT_BRIEFINGS_DEFAULT_DAYS,
    _SCOUT_BRIEFINGS_MAX_DAYS,
    _SQL_SCOUT_BRIEFINGS_BY_DAY,
    _SQL_SCOUT_BRIEFINGS_REFUSALS,
    _SQL_SCOUT_BRIEFINGS_STATUS,
    _q_scout_briefings,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "backend" / "store" / "schema.sql"

DAY_START_HOUR = 10
# Ten days before whenever the suite runs, so it is always inside the
# `days=45` window the tests below ask for. This used to be a fixed date,
# 2026-08-10, "comfortably inside" the window when it was written on
# 2026-09-21. On 2026-09-24 PREV_DAY fell out of the 45-day window and three
# tests went red on CI. A fixed date in a test whose query is relative to
# the clock is a timer.
_DAY_DT = datetime.now(timezone.utc) - timedelta(days=10)
DAY = _DAY_DT.strftime("%Y%m%d")
PREV_DAY = (_DAY_DT - timedelta(days=1)).strftime("%Y%m%d")


def _bounds(date: str) -> tuple[int, int]:
    return _day_bounds(date, DAY_START_HOUR)


@pytest.fixture
def db(tmp_path) -> Path:
    """Schema-built database with no rows -- `scout_briefings` is seeded per test."""
    path = tmp_path / "cockpit.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    return path


def _insert(conn: sqlite3.Connection, **kwargs) -> None:
    """One `scout_briefings` row. Every NOT NULL column gets a default."""
    row = {
        "ticker": "KXNFLGAME-25SEP21DENKC",
        "event_title": "Broncos at Chiefs",
        "league": "Pro Football",
        "home_team": "Chiefs",
        "away_team": "Broncos",
        "commence_ms": 1_000_000,
        "completed_ms": kwargs.get("requested_ms", 0) + 5_000,
        "status": "complete",
        "refusal_reason": None,
        "staff_json": None,
        "briefing_json": None,
        "sharp_json": None,
        "model": "claude-sonnet-5",
        "trigger": "tap",
    }
    row.update(kwargs)
    conn.execute(
        "INSERT INTO scout_briefings "
        "(ticker, event_title, league, home_team, away_team, commence_ms, "
        " requested_ms, completed_ms, status, refusal_reason, staff_json, "
        " briefing_json, sharp_json, model, trigger) "
        "VALUES (:ticker, :event_title, :league, :home_team, :away_team, "
        " :commence_ms, :requested_ms, :completed_ms, :status, "
        " :refusal_reason, :staff_json, :briefing_json, :sharp_json, :model, "
        " :trigger)",
        row,
    )


class _Args:
    """Stand-in for `argparse.Namespace` -- carries only what `_q_scout_briefings` reads."""

    def __init__(self, *, days=None, day_start_hour=DAY_START_HOUR, limit=2000):
        self.days = days
        self.day_start_hour = day_start_hour
        self.limit = limit


class TestScoutBriefings:
    """The registry pin: `scout-briefings` is a real, cheap, whitelisted query."""

    def test_scout_briefings_is_registered_and_cheap(self):
        """Mutation: delete the `"scout-briefings"` entry from `QUERIES` --
        red (KeyError). Cost is CHEAP: a bounded `requested_ms >= ?` seek
        over a table that grows by at most a handful of rows a day, per the
        ticket's own cost note."""
        assert "scout-briefings" in QUERIES
        assert QUERIES["scout-briefings"].cost == CHEAP

    def test_auto_and_tap_separate_by_budget_day(self, db):
        """**The done-when test.** Rows straddling a budget-day boundary land
        in the right day AND the right column.

        Seeded: one `auto` row just before the 10:00Z boundary (falls in
        `PREV_DAY`), one `tap` and one `auto` row at/after it (both fall in
        `DAY`). Section A must report `PREV_DAY: auto=1, tap=0` and
        `DAY: auto=1, tap=1` -- never a combined total, never a ratio.

        Mutation: swap `'auto'`/`'tap'` inside the `CASE WHEN` of
        `_SQL_SCOUT_BRIEFINGS_BY_DAY` -- the counts below flip and this goes
        red.
        """
        start_ms, _ = _bounds(DAY)
        conn = sqlite3.connect(db)
        _insert(conn, requested_ms=start_ms - 1, trigger="auto")  # PREV_DAY
        _insert(conn, requested_ms=start_ms, trigger="tap")  # DAY, at boundary
        _insert(conn, requested_ms=start_ms + 60_000, trigger="auto")  # DAY
        conn.commit()
        conn.close()

        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            sections = _q_scout_briefings(conn, _Args(days=45))
        finally:
            conn.close()

        by_day = next(s for s in sections if s.title.startswith("A."))
        assert by_day.columns == ("budget_day", "auto_count", "tap_count")
        by_day_map = {r[0]: (r[1], r[2]) for r in by_day.rows}

        assert by_day_map[PREV_DAY] == (1, 0)
        assert by_day_map[DAY] == (1, 1)

    def test_never_a_total_or_ratio_column(self, db):
        """The ticket forbids a total or a ratio column in section A.

        Mutation: add `auto_count + tap_count AS total` to
        `_SQL_SCOUT_BRIEFINGS_BY_DAY` -- red, a third data column appears.
        """
        start_ms, _ = _bounds(DAY)
        conn = sqlite3.connect(db)
        _insert(conn, requested_ms=start_ms, trigger="auto")
        conn.commit()
        conn.close()

        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            sections = _q_scout_briefings(conn, _Args(days=45))
        finally:
            conn.close()

        by_day = next(s for s in sections if s.title.startswith("A."))
        assert by_day.columns == ("budget_day", "auto_count", "tap_count")

    def test_status_breakdown_within_each_trigger(self, db):
        """Section B: (budget_day, trigger, status) -> count.

        Mutation: drop `trigger` from `_SQL_SCOUT_BRIEFINGS_STATUS`'s
        `GROUP BY` -- red, `failed`/`auto` and `failed`/`tap` collapse into
        one row and the per-trigger count below is wrong.
        """
        start_ms, _ = _bounds(DAY)
        conn = sqlite3.connect(db)
        _insert(conn, requested_ms=start_ms, trigger="auto", status="failed")
        _insert(conn, requested_ms=start_ms + 1000, trigger="tap", status="failed")
        _insert(conn, requested_ms=start_ms + 2000, trigger="tap", status="complete")
        conn.commit()
        conn.close()

        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            sections = _q_scout_briefings(conn, _Args(days=45))
        finally:
            conn.close()

        status = next(s for s in sections if s.title.startswith("B."))
        assert status.columns == ("budget_day", "trigger", "status", "n")
        counts = {(r[1], r[2]): r[3] for r in status.rows if r[0] == DAY}
        assert counts[("auto", "failed")] == 1
        assert counts[("tap", "failed")] == 1
        assert counts[("tap", "complete")] == 1

    def test_refusal_reason_is_printed_verbatim(self, db):
        """A `status = 'refused'` row (the only shape reachable inside this
        table -- see module docstring) carries its exact `refusal_reason`
        text through unparsed.

        Mutation: `SUBSTR(refusal_reason, 1, 10)` in
        `_SQL_SCOUT_BRIEFINGS_REFUSALS` -- red, the reason is truncated.
        """
        start_ms, _ = _bounds(DAY)
        reason = "the desk's own mid-run ceiling fired: too many staff calls"
        conn = sqlite3.connect(db)
        _insert(
            conn,
            requested_ms=start_ms,
            trigger="auto",
            status="refused",
            refusal_reason=reason,
            completed_ms=start_ms + 500,
        )
        conn.commit()
        conn.close()

        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            sections = _q_scout_briefings(conn, _Args(days=45))
        finally:
            conn.close()

        refusals = next(s for s in sections if s.title.startswith("C."))
        reason_idx = refusals.columns.index("refusal_reason")
        assert [r[reason_idx] for r in refusals.rows] == [reason]

    def test_no_refusal_reason_means_an_empty_section_not_a_fabricated_zero(
        self, db
    ):
        """A day with only clean convenings emits no row in section C at
        all -- not a row with `refusal_reason = 0` or `''`.
        """
        start_ms, _ = _bounds(DAY)
        conn = sqlite3.connect(db)
        _insert(conn, requested_ms=start_ms, trigger="tap", status="complete")
        conn.commit()
        conn.close()

        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            sections = _q_scout_briefings(conn, _Args(days=45))
        finally:
            conn.close()

        refusals = next(s for s in sections if s.title.startswith("C."))
        assert refusals.rows == []

    def test_days_flag_is_bounded_by_the_hard_ceiling(self, db):
        """`--days` past `_SCOUT_BRIEFINGS_MAX_DAYS` is clamped, not honoured.

        A row `_SCOUT_BRIEFINGS_MAX_DAYS + 5` days back must NOT appear even
        when the caller asks for far more days than that.

        Mutation: replace the `min(..., _SCOUT_BRIEFINGS_MAX_DAYS)` clamp in
        `_q_scout_briefings` with the requested value alone -- red, the old
        row appears.
        """
        import time

        now_ms = int(time.time() * 1000)
        too_old_ms = now_ms - (_SCOUT_BRIEFINGS_MAX_DAYS + 5) * 86_400_000
        conn = sqlite3.connect(db)
        _insert(conn, requested_ms=too_old_ms, trigger="auto")
        conn.commit()
        conn.close()

        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            sections = _q_scout_briefings(
                conn, _Args(days=_SCOUT_BRIEFINGS_MAX_DAYS * 100)
            )
        finally:
            conn.close()

        by_day = next(s for s in sections if s.title.startswith("A."))
        assert by_day.rows == []

    def test_default_days_matches_the_ticket_constant(self):
        assert _SCOUT_BRIEFINGS_DEFAULT_DAYS == 7
