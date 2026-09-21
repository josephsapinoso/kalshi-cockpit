"""`scout-watch-log` -- the reader for the table #126 writes.

What these tests establish
--------------------------
That the query returns each budget day's decisions ordered so the FIRST row of
a day is what bound first, that `cycle_count` survives to the output, and that
`detail` is printed verbatim rather than parsed into a category.

What they do NOT establish
--------------------------
- **Nothing about live.** Every row is seeded here.
- **Nothing about completeness.** The writer swallows its own failures so it
  can never fail the decision it records, so the table can undercount; no test
  here can see that, and the query's docstring says so.
"""

from __future__ import annotations

import sqlite3

from scripts.inspect_live_db import QUERIES
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
    path = tmp_path / "watchlog.db"
    conn = db.init_db(path)
    for budget_day_ms, first_ms, last_ms, cycles, outcome, detail in rows:
        conn.execute(
            "INSERT INTO scout_watch_log (budget_day_ms, first_ms, last_ms, "
            "cycle_count, outcome, detail) VALUES (?, ?, ?, ?, ?, ?)",
            (budget_day_ms, first_ms, last_ms, cycles, outcome, detail),
        )
    conn.commit()
    conn.close()
    return path


def _run(path, **kw):
    conn = db.connect(path)
    try:
        return QUERIES["scout-watch-log"].run(conn, _args(**kw))
    finally:
        conn.close()


def _data_section(sections):
    """The decisions section -- the one after the window header."""
    return sections[1]


def _col(section, name):
    """Rows are TUPLES, not mappings -- index by the declared column name so a
    reordered SELECT cannot silently move an assertion onto another column."""
    i = section.columns.index(name)
    return [r[i] for r in section.rows]


class TestWhatBoundFirstIsReadableFromTheOrdering:
    def test_the_first_row_of_a_day_is_the_earliest_decision(self, tmp_path):
        """`budget_day DESC, first_ms ASC`.

        This ordering IS the answer to "which ceiling bound first", so it is
        not a display preference. Seeded deliberately out of order.
        """
        import time

        now = int(time.time() * 1000)
        day = now - (now % DAY)
        path = _seeded(tmp_path, [
            # inserted latest-first, so a naive rowid order would invert it
            (day, day + 9_000, day + 9_000, 1, "refused_budget", "tokens"),
            (day, day + 1_000, day + 1_000, 4, "no_candidate", "quiet"),
        ])

        sec = _data_section(_run(path))
        assert _col(sec, "outcome") == ["no_candidate", "refused_budget"]
        firsts = _col(sec, "first_ms")
        assert firsts[0] < firsts[1]

    def test_cycle_count_reaches_the_output(self, tmp_path):
        """A ceiling that bound once and one that bound all evening must be
        distinguishable -- the difference between a brake working and a brake
        stuck."""
        import time

        now = int(time.time() * 1000)
        day = now - (now % DAY)
        path = _seeded(tmp_path, [
            (day, day + 1_000, day + 80_000, 137, "refused_budget", "tokens"),
        ])

        sec = _data_section(_run(path))
        assert _col(sec, "cycle_count") == [137]

    def test_detail_is_printed_verbatim(self, tmp_path):
        """Not parsed into a category. For `refused_budget` it is
        `AgentBudget.refusal_reason`'s own sentence; re-deriving which ceiling
        it named would be a second implementation of that ladder."""
        import time

        now = int(time.time() * 1000)
        day = now - (now % DAY)
        sentence = (
            "511051 of 500000 Anthropic tokens already recorded today"
        )
        path = _seeded(tmp_path, [
            (day, day + 1, day + 1, 1, "refused_budget", sentence),
        ])

        sec = _data_section(_run(path))
        assert _col(sec, "detail") == [sentence]


class TestTheWindowIsBounded:
    def test_a_day_outside_the_window_is_not_returned(self, tmp_path):
        import time

        now = int(time.time() * 1000)
        day = now - (now % DAY)
        path = _seeded(tmp_path, [
            (day, day + 1, day + 1, 1, "no_candidate", "inside"),
            (day - 40 * DAY, day - 40 * DAY, day - 40 * DAY, 1,
             "no_candidate", "outside"),
        ])

        sec = _data_section(_run(path, days=3))
        assert _col(sec, "detail") == ["inside"]
