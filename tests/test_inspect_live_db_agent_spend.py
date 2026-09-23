"""`agent-spend` -- when each AGENT_MAX_* ceiling was crossed (#137).

What these tests establish
--------------------------
That the query's running sums accumulate call-by-call within a budget day in
the same shape `backend/agents/budget.py:state` computes them (COUNT(*) for
calls, COALESCE(SUM(...), 0) + COALESCE(SUM(...), 0) for tokens,
COALESCE(SUM(...), 0) for searches); that a NULL usage row is counted as
unmetered rather than folded into either sum as a silent zero; and that
`--days` bounds which rows the running sums are built from at all.

What they do NOT establish
---------------------------
- **Nothing about live.** Every row is seeded here, against a schema-built
  tmp database. This test never opens the live box.
- **Nothing about which ceiling refused.** That decision is
  `backend/agents/budget.py:refusal_reason`'s; this query prints the totals
  it was made from, not a re-derivation of the decision.
"""

from __future__ import annotations

from scripts.inspect_live_db import CHEAP, QUERIES
from backend.store import db


DAY = 86_400_000


def _args(**kw):
    class A:
        limit = 100
        days = 7
        day_start_hour = 10

    a = A()
    for k, v in kw.items():
        setattr(a, k, v)
    return a


def _seeded(tmp_path, rows):
    """rows: (called_ms, agent, model, input_tokens, output_tokens, web_searches)"""
    path = tmp_path / "agentspend.db"
    conn = db.init_db(path)
    for called_ms, agent, model, in_tok, out_tok, searches in rows:
        conn.execute(
            "INSERT INTO agent_calls (called_ms, agent, model, input_tokens, "
            "output_tokens, web_searches) VALUES (?, ?, ?, ?, ?, ?)",
            (called_ms, agent, model, in_tok, out_tok, searches),
        )
    conn.commit()
    conn.close()
    return path


def _run(path, **kw):
    conn = db.connect(path)
    try:
        return QUERIES["agent-spend"].run(conn, _args(**kw))
    finally:
        conn.close()


def _data_section(sections):
    """The per-call section -- the one after the window header."""
    return sections[1]


def _col(section, name):
    """Rows are TUPLES -- index by declared column name so a reordered
    SELECT cannot silently move an assertion onto another column."""
    i = section.columns.index(name)
    return [r[i] for r in section.rows]


class TestRunningSumsAccumulatePerBudgetDay:
    def test_calls_tokens_and_searches_build_up_call_by_call(self, tmp_path):
        """Three calls, same budget day: each row's running totals are a
        prefix sum over the calls up to and including it -- not the day's
        final total repeated on every row, and not per-call values."""
        import time

        now = int(time.time() * 1000)
        day = now - (now % DAY) + 11 * 3_600_000  # inside the 10:00Z day
        path = _seeded(tmp_path, [
            (day + 1_000, "scout", "sonnet", 1_000, 500, 2),
            (day + 2_000, "scout", "sonnet", 2_000, 1_000, 3),
            (day + 3_000, "skeptic", "opus", 500, 500, 0),
        ])

        sec = _data_section(_run(path))
        assert _col(sec, "calls_running") == [1, 2, 3]
        assert _col(sec, "tokens_running") == [1_500, 4_500, 5_500]
        assert _col(sec, "web_searches_running") == [2, 5, 5]

    def test_seeded_out_of_order_still_accumulates_earliest_first(self, tmp_path):
        """Insert order must not matter -- the window function orders by
        called_ms, not by rowid."""
        import time

        now = int(time.time() * 1000)
        day = now - (now % DAY) + 11 * 3_600_000
        path = _seeded(tmp_path, [
            (day + 9_000, "scout", "sonnet", 100, 100, 1),
            (day + 1_000, "scout", "sonnet", 10, 10, 1),
        ])

        sec = _data_section(_run(path))
        # earliest call first in the displayed order too (budget_day DESC,
        # called_ms ASC), and its running total is its OWN value, not the
        # day's eventual total.
        assert _col(sec, "called_ms") == [day + 1_000, day + 9_000]
        assert _col(sec, "tokens_running") == [20, 220]


class TestANullUsageRowIsUnmetered:
    def test_a_null_row_leaves_the_sum_unchanged_and_is_counted_separately(
        self, tmp_path
    ):
        """The guard this test exists to catch: a NULL usage row folded into
        the sum as a silent zero is indistinguishable from a call that
        genuinely spent nothing. It must instead leave the running sum where
        it was and be counted in unmetered_running."""
        import time

        now = int(time.time() * 1000)
        day = now - (now % DAY) + 11 * 3_600_000
        path = _seeded(tmp_path, [
            (day + 1_000, "scout", "sonnet", 1_000, 500, 2),
            (day + 2_000, "scout", "sonnet", None, None, None),  # never settled
            (day + 3_000, "scout", "sonnet", 3_000, 1_500, 4),
        ])

        sec = _data_section(_run(path))
        tokens = _col(sec, "tokens_running")
        searches = _col(sec, "web_searches_running")
        unmetered = _col(sec, "unmetered_running")
        calls = _col(sec, "calls_running")

        # the NULL row (index 1) leaves both sums at their value from the
        # row before it -- not zero, not the pre-NULL value plus 0 that
        # would happen to print the same in this fabricated case, but the
        # actual unchanged accumulator.
        assert tokens[1] == tokens[0] == 1_500
        assert searches[1] == searches[0] == 2
        # every call still counts, including the unmetered one
        assert calls == [1, 2, 3]
        # the unmetered count is a running total of its own, incrementing at
        # the NULL row and staying there afterwards
        assert unmetered == [0, 1, 1]
        # and once metered calls resume, the sums pick back up from where
        # they left off -- the NULL contributed nothing, not a permanent gap
        assert tokens[2] == 1_500 + 4_500
        assert searches[2] == 2 + 4


class TestTheWindowIsBounded:
    def test_a_day_outside_the_window_is_not_returned(self, tmp_path):
        import time

        now = int(time.time() * 1000)
        day = now - (now % DAY) + 11 * 3_600_000
        path = _seeded(tmp_path, [
            (day + 1_000, "scout", "sonnet", 10, 10, 0),
            (day - 40 * DAY, "scout", "sonnet", 999, 999, 9),
        ])

        sec = _data_section(_run(path, days=3))
        assert _col(sec, "called_ms") == [day + 1_000]

    def test_a_row_outside_the_window_does_not_leak_into_the_running_sum(
        self, tmp_path
    ):
        """The guard this test exists to catch: dropping the --days bound
        (or widening it silently) would let an old call's tokens bleed into
        a day's running total that should start from zero."""
        import time

        now = int(time.time() * 1000)
        day = now - (now % DAY) + 11 * 3_600_000
        path = _seeded(tmp_path, [
            (day - 40 * DAY, "scout", "sonnet", 50_000, 50_000, 20),
            (day + 1_000, "scout", "sonnet", 10, 10, 0),
        ])

        sec = _data_section(_run(path, days=3))
        assert _col(sec, "tokens_running") == [20]


class TestTheQueryIsRegisteredCheap:
    def test_agent_spend_is_registered_cost_cheap(self):
        assert QUERIES["agent-spend"].cost == CHEAP


class TestTheBudgetDayTurnsAtItsStartHour:
    """The guard: a raw call is labelled by `called_ms - offset`. With `+`
    the day turns at 14:00Z instead of 10:00Z, and budget day 20260922 --
    the day #137 exists to read -- is split in two."""

    def test_calls_either_side_of_10z_land_in_different_days(self, tmp_path):
        import time

        now = int(time.time() * 1000)
        ten_z = now - ((now - 10 * 3_600_000) % DAY) - DAY  # yesterday 10:00Z
        path = _seeded(tmp_path, [
            (ten_z - 60_000, "scout", "sonnet", 7, 0, 0),    # 09:59Z: day before
            (ten_z + 60_000, "scout", "sonnet", 10, 0, 0),   # 10:01Z
            (ten_z + 5 * 3_600_000, "scout", "sonnet", 20, 0, 0),  # 15:00Z
        ])

        sec = _data_section(_run(path, days=3))
        days = _col(sec, "budget_day")
        tokens = _col(sec, "tokens_running")
        by_ms = dict(zip(_col(sec, "called_ms"), zip(days, tokens)))
        before, after, later = (
            by_ms[ten_z - 60_000], by_ms[ten_z + 60_000],
            by_ms[ten_z + 5 * 3_600_000],
        )
        assert before[0] != after[0]
        # 10:01Z and 15:00Z are one budget day, and its sum builds across both
        assert after[0] == later[0]
        assert (after[1], later[1]) == (10, 30)


class TestTheWindowStartsOnADayBoundary:
    def test_the_oldest_day_in_the_window_is_whole(self, tmp_path):
        """--days 2 covers today and yesterday from their 10:00Z starts; a
        call at yesterday 10:01Z is inside, so the oldest day's running sum
        is not truncated by a window that began mid-day."""
        import time

        now = int(time.time() * 1000)
        today_start = now - ((now - 10 * 3_600_000) % DAY)
        yesterday_start = today_start - DAY
        path = _seeded(tmp_path, [
            (yesterday_start + 60_000, "scout", "sonnet", 5, 0, 0),
            (yesterday_start - 60_000, "scout", "sonnet", 999, 0, 0),
        ])

        sec = _data_section(_run(path, days=2))
        assert _col(sec, "called_ms") == [yesterday_start + 60_000]
