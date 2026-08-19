"""Retention drops only what no reader can reach.

`backend/store/retention.py` is the first code in this project that deletes a
row. The tables it trims had no bound at all: `kalshi_quotes` reached 6.9M rows
behind a 476 MiB index on a 1 GiB machine, and `unmatched_events` 506,655 rows
of which zero had ever been resolved. That cost a filled volume on 2026-08-16
and, because every quote pass inserts into that index, a store leg that grew
from 0.17s at 279k rows to 14.0s at 6.9M.

The risk a retention rule carries is not that it deletes too little. These
tests are therefore weighted towards what must **survive**.

What these tests do not establish
---------------------------------
That the live database's readers are the ones enumerated in the module
docstring. That was checked by reading every `kalshi_quotes` caller on
2026-08-19 and is asserted here only for `recommendations`, the one the SQL
actually references. A reader added later that reaches past the retention
window will not fail these tests -- it will find no rows, which is why the
module says the window must be raised here first.

Nor that a prune is fast on a table of live size. Every fixture here is tiny;
the batching exists for a lock-duration reason that a small table cannot
exercise.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.store import retention

_MS_PER_DAY = 24 * 60 * 60 * 1000
NOW = 1_787_000_000_000


@pytest.fixture()
def conn():
    """The two pruned tables plus the one the quote rule consults."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(
        """
        CREATE TABLE kalshi_quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            observed_ms INTEGER NOT NULL,
            source TEXT NOT NULL DEFAULT 'rest'
        );
        CREATE TABLE recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL
        );
        CREATE TABLE unmatched_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            observed_ms INTEGER NOT NULL,
            resolved INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    return c


def add_quote(conn, ticker: str, age_days: float) -> None:
    conn.execute(
        "INSERT INTO kalshi_quotes (ticker, observed_ms) VALUES (?, ?)",
        (ticker, int(NOW - age_days * _MS_PER_DAY)),
    )
    conn.commit()


def tickers(conn) -> list[str]:
    return [r["ticker"] for r in conn.execute(
        "SELECT ticker FROM kalshi_quotes ORDER BY id")]


class TestWhatMustSurvive:
    """The half of a retention rule that can lose data."""

    def test_a_recommended_tickers_history_survives_any_age(self, conn):
        """CLV work reaches back through `recommendations.ticker`.

        This is the whole reason the rule is not a plain age cut. A market
        recommended once must keep the run of quotes around it, or the closing
        line it would be scored against is gone.
        """
        conn.execute("INSERT INTO recommendations (ticker) VALUES ('KEEP')")
        conn.commit()
        add_quote(conn, "KEEP", age_days=400)

        retention.prune_quotes(conn, now=NOW)

        assert tickers(conn) == ["KEEP"], (
            "a quote for a ticker that produced a recommendation was deleted; "
            "clv_signal.py joins through exactly that ticker"
        )

    def test_quotes_inside_the_window_survive_even_unrecommended(self, conn):
        """`slate.kalshi_drift_tenths` reads an hour of any ticker."""
        add_quote(conn, "FRESH", age_days=0.5)

        retention.prune_quotes(conn, now=NOW)

        assert tickers(conn) == ["FRESH"]

    def test_the_boundary_is_kept_not_dropped(self, conn):
        """A row exactly at the cutoff is inside the window.

        Stated as a test because `<` and `<=` are indistinguishable in review
        and differ by one pass's worth of rows at the moment a reader is
        reaching for the oldest thing it is promised.
        """
        cutoff_row_age = retention.DEFAULT_QUOTE_RETENTION_MS
        conn.execute(
            "INSERT INTO kalshi_quotes (ticker, observed_ms) VALUES ('EDGE', ?)",
            (NOW - cutoff_row_age,),
        )
        conn.commit()

        retention.prune_quotes(conn, now=NOW)

        assert tickers(conn) == ["EDGE"]


class TestWhatIsRemoved:
    def test_an_old_unrecommended_quote_goes(self, conn):
        add_quote(conn, "GONE", age_days=10)

        removed = retention.prune_quotes(conn, now=NOW)

        assert removed == 1
        assert tickers(conn) == []

    def test_it_keeps_deleting_past_one_batch(self, monkeypatch, conn):
        """The batch size is a lock-duration limit, not a row limit.

        A single `DELETE ... LIMIT n` removes n rows and reports success. If
        the loop that repeats it were dropped, retention would silently trim
        `DELETE_BATCH` rows per pass against millions of surplus ones and the
        table would keep growing while the counter said it was working.
        """
        monkeypatch.setattr(retention, "DELETE_BATCH", 2)
        for i in range(7):
            add_quote(conn, f"OLD{i}", age_days=10)

        removed = retention.prune_quotes(conn, now=NOW)

        assert removed == 7
        assert tickers(conn) == []

    def test_unmatched_is_pruned_regardless_of_resolved(self, conn):
        """0 of 506,655 live rows were resolved, so sparing them spares nothing."""
        conn.execute(
            "INSERT INTO unmatched_events (observed_ms, resolved) VALUES (?, 0)",
            (NOW - 30 * _MS_PER_DAY,),
        )
        conn.execute(
            "INSERT INTO unmatched_events (observed_ms, resolved) VALUES (?, 1)",
            (NOW - 30 * _MS_PER_DAY,),
        )
        conn.commit()

        removed = retention.prune_unmatched(conn, now=NOW)

        assert removed == 2
        assert conn.execute(
            "SELECT COUNT(*) FROM unmatched_events").fetchone()[0] == 0


class TestItReportsWhatItDid:
    def test_a_prune_that_finds_nothing_returns_zero_not_none(self, conn):
        """Zero is an answer; `None` would be indistinguishable from a crash."""
        result = retention.prune(conn, now=NOW)

        assert result.quotes_deleted == 0
        assert result.unmatched_deleted == 0
        assert result.total == 0

    def test_both_tables_are_counted_separately(self, conn):
        add_quote(conn, "OLD", age_days=10)
        conn.execute(
            "INSERT INTO unmatched_events (observed_ms) VALUES (?)",
            (NOW - 30 * _MS_PER_DAY,),
        )
        conn.commit()

        result = retention.prune(conn, now=NOW)

        assert result.quotes_deleted == 1
        assert result.unmatched_deleted == 1


class TestItRunsOnTheSlowCadenceOnly:
    """A prune on the quote cadence would be the incident it prevents.

    Retention takes the write lock the quote inserts need. At 15s, during an
    open window, that is a multi-million-row delete competing with the pass it
    exists to speed up.
    """

    def test_the_quote_pass_does_not_prune(self):
        import inspect

        from backend import runner

        source = inspect.getsource(runner.run_quote_pass)
        assert "retention.prune" not in source, (
            "run_quote_pass now prunes; retention holds the write lock the "
            "15s inserts need and must stay on the full pass"
        )

    def test_the_full_pass_does_prune(self):
        import inspect

        from backend import runner

        source = inspect.getsource(runner.run_once)
        assert "retention.prune" in source, (
            "the full pass no longer prunes, so both tables are unbounded "
            "again -- the volume filled on 2026-08-16 for this reason"
        )


class TestThePruneCannotHoldThePass:
    """Batching bounds the lock; only the budget bounds the pass.

    These are different quantities and conflating them cost a live stall. The
    prune runs *inside* the pass, so a loop that deletes until nothing matches
    blocks the recorder for the whole backlog no matter how small each batch
    is. Measured on the first live run, 2026-08-19: 1.25M rows removed at
    ~60k/minute with 1.8M still pending, and `recorder.age_ms` climbing one
    second per second throughout -- no quotes recorded at all while it ran.
    """

    def test_it_stops_at_the_budget_and_leaves_the_rest(self, monkeypatch, conn):
        """A backlog drains over passes rather than in one stall."""
        monkeypatch.setattr(retention, "DELETE_BATCH", 1)
        for i in range(50):
            add_quote(conn, f"OLD{i}", age_days=10)

        # A budget of zero still does one batch: the deadline is checked after
        # a delete, never instead of one, so the prune always makes progress.
        removed = retention.prune_quotes(conn, now=NOW, budget_s=0)

        assert removed == 1, "the budget stopped the prune before it did any work"
        assert conn.execute(
            "SELECT COUNT(*) FROM kalshi_quotes").fetchone()[0] == 49, (
            "the prune ran past its budget; on live this blocked the recorder "
            "for the whole backlog"
        )

    def test_a_generous_budget_still_finishes_the_job(self, conn):
        """The budget must not turn a small steady-state prune into a dribble."""
        for i in range(5):
            add_quote(conn, f"OLD{i}", age_days=10)

        removed = retention.prune_quotes(conn, now=NOW, budget_s=60)

        assert removed == 5
        assert tickers(conn) == []

    def test_unmatched_gets_its_own_budget_not_the_remainder(self):
        """A quote backlog must not starve the other table indefinitely.

        If both prunes shared one deadline, the quotes prune would consume it
        every pass for as long as its backlog lasted and `unmatched_events`
        would never be reached -- growing unbounded behind a rule that looked
        like it covered it.
        """
        import inspect

        source = inspect.getsource(retention.prune)
        quotes_at = source.index("prune_quotes")
        unmatched_at = source.index("prune_unmatched")
        after = source[unmatched_at:]

        assert "budget_s=budget_s" in after, (
            "prune_unmatched no longer receives a full budget of its own"
        )
        assert source.count("budget_s=budget_s") == 2, (
            "the two prunes must each get the full budget, not one shared "
            "deadline -- a quote backlog would starve unmatched_events"
        )
        assert quotes_at < unmatched_at


class TestRetentionYieldsToABettableWindow:
    """The prune costs ~40s of a full pass, and it has no deadline.

    `budget_s` is checked between batches and one batch measures ~20s against
    the live table, so a 5s budget really costs ~40s across the two tables --
    full passes went 50s to 87s when this shipped, 2026-08-19. Between windows
    that is free. While one is open it is exactly the confirmation gap the fast
    cadence exists to close, spent on housekeeping that could equally happen an
    hour later.

    The budget and this rule are not redundant: the budget bounds a stall that
    is happening anyway, this decides whether it happens now.
    """

    def test_the_full_pass_skips_the_prune_while_a_window_is_open(self):
        import inspect

        from backend import runner

        source = inspect.getsource(runner.run_once)
        assert "if window_open:" in source, (
            "the full pass no longer checks window_open before pruning; a "
            "~40s prune inside a bettable window is the incident retention "
            "was written to prevent"
        )
        gate = source.index("if window_open:")
        call = source.index("retention.prune(")
        assert gate < call, (
            "the prune runs before the window check, so the check cannot "
            "prevent it"
        )

    def test_the_loop_passes_the_schedulers_own_window_state(self):
        """One source of truth for 'is this minute bettable'.

        A prune reading a different clock from the cadence could prune during
        exactly the minutes the cadence had sped up for.
        """
        from pathlib import Path

        source = Path("scripts/run_loop.py").read_text(encoding="utf-8")
        assert "window_open=tempo.window_open" in source, (
            "run_loop no longer hands run_once the scheduler's window state, "
            "so the prune falls back to the default and runs during windows"
        )
