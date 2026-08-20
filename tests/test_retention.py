"""Retention drops only what no reader can reach.

`backend/store/retention.py` is the first code in this project that deletes a
row. The tables it trims had no bound at all: `kalshi_quotes` reached 6.9M rows
behind a 476 MiB index on a 1 GiB machine, and the unmatched queue 788,944 rows
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

from backend.config import OddsConfig
from backend.store import retention

# Enough of an `OddsConfig` for `run_once` to reach its prune gate. The pass
# itself is monkeypatched out -- nothing here calls The Odds API.
_ODDS_CONFIG = OddsConfig(
    api_key="test-odds-key",
    base_url="https://example.invalid",
    daily_credit_budget=16,
    regions=["us"],
    markets=["h2h"],
)

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
            -- ADR 0055. Left NULL by `add_quote` on purpose: that is what
            -- every row written before the ADR looks like, so these tests
            -- exercise the COALESCE fallback, and the cases where the two
            -- columns disagree get their own class below.
            confirmed_ms INTEGER,
            source TEXT NOT NULL DEFAULT 'rest'
        );
        CREATE TABLE recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL
        );
        -- ADR 0056: one row per work item. Built with the identity columns and
        -- the unique index rather than the two this module reads, because a
        -- fixture that omits the constraint cannot show a prune interacting
        -- with it -- and the interaction is the whole risk. Two sightings of
        -- one item are one row here, exactly as on live.
        CREATE TABLE unmatched_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_seen_ms INTEGER NOT NULL,
            last_seen_ms INTEGER NOT NULL,
            seen_count INTEGER NOT NULL DEFAULT 1,
            side TEXT NOT NULL,
            identifier TEXT NOT NULL,
            league TEXT,
            detail TEXT,
            reason TEXT NOT NULL,
            resolved INTEGER NOT NULL DEFAULT 0
        );
        CREATE UNIQUE INDEX idx_unmatched_item ON unmatched_items(
            side, identifier, COALESCE(league, ''), COALESCE(detail, ''), reason);
        """
    )
    return c


def add_unmatched(
    conn, identifier: str, *, last_seen_days: float,
    first_seen_days: float | None = None, resolved: int = 0,
) -> None:
    """One work item, last seen `last_seen_days` ago.

    `first_seen_days` defaults to the same instant. Where the two differ is
    exactly where the prune's choice of column shows, so the tests that care
    pass both.
    """
    if first_seen_days is None:
        first_seen_days = last_seen_days
    conn.execute(
        "INSERT INTO unmatched_items (first_seen_ms, last_seen_ms, side, "
        "identifier, league, detail, reason, resolved) "
        "VALUES (?, ?, 'kalshi', ?, NULL, NULL, 'no_counterpart', ?)",
        (
            int(NOW - first_seen_days * _MS_PER_DAY),
            int(NOW - last_seen_days * _MS_PER_DAY),
            identifier,
            resolved,
        ),
    )
    conn.commit()


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
        """0 of 743,428 live rows were resolved, so sparing them spares nothing."""
        add_unmatched(conn, "OPEN", last_seen_days=30, resolved=0)
        add_unmatched(conn, "DONE", last_seen_days=30, resolved=1)

        removed = retention.prune_unmatched(conn, now=NOW)

        assert removed == 2
        assert conn.execute(
            "SELECT COUNT(*) FROM unmatched_items").fetchone()[0] == 0


class TestItReportsWhatItDid:
    def test_a_prune_that_finds_nothing_returns_zero_not_none(self, conn):
        """Zero is an answer; `None` would be indistinguishable from a crash."""
        result = retention.prune(conn, now=NOW)

        assert result.quotes_deleted == 0
        assert result.unmatched_deleted == 0
        assert result.total == 0

    def test_both_tables_are_counted_separately(self, conn):
        add_quote(conn, "OLD", age_days=10)
        add_unmatched(conn, "OLD", last_seen_days=30)

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

        If the prunes shared one deadline, the quotes prune would consume it
        every pass for as long as its backlog lasted and the unmatched queue
        would never be reached -- growing unbounded behind a rule that looked
        like it covered it.

        **Three since ADR 0056**, not two: `prune_legacy_unmatched` drains the
        old append-only table and gets its own budget for the same reason. The
        count is asserted exactly rather than as a minimum, so adding a fourth
        prune has to come here and state that it meant to.
        """
        import inspect

        source = inspect.getsource(retention.prune)
        quotes_at = source.index("prune_quotes")
        unmatched_at = source.index("prune_unmatched")
        after = source[unmatched_at:]

        assert "budget_s=budget_s" in after, (
            "prune_unmatched no longer receives a full budget of its own"
        )
        assert source.count("budget_s=budget_s") == 3, (
            "each prune must get the full budget, not one shared deadline -- "
            "a quote backlog would starve the unmatched queue"
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
        assert "callable(window_open)" in source, (
            "the full pass no longer checks window_open before pruning; a "
            "~40s prune inside a bettable window is the incident retention "
            "was written to prevent"
        )
        gate = source.index("callable(window_open)")
        call = source.index("retention.prune(")
        assert gate < call, (
            "the prune runs before the window check, so the check cannot "
            "prevent it"
        )

    async def test_the_window_is_read_after_the_sweep_not_before(
        self, monkeypatch, conn
    ):
        """The decision is read at the prune, not at the top of the pass.

        This is the half a reordering cannot fix and the half that is probably
        more common. `run_ingest_pass` fires the odds sweep; the sweep is what
        makes odds fresh; fresh odds *is* `ActionableWindow.is_open`. So a full
        pass that opens a window opened it moments earlier, in itself. A flag
        sampled before the pass -- or, as shipped, at the end of the *previous*
        pass -- still says closed, and the prune runs through the first ~40-94s
        of a bettable window.

        Asserting the call order rather than just the outcome, because a gate
        that happens to be `True` for the wrong reason passes an outcome test.
        """
        from backend import runner
        from backend.store import retention

        order: list[str] = []

        async def fake_ingest(*args, **kwargs):
            order.append("ingest")
            return [], runner.PassCounts()

        def fake_prune(*args, **kwargs):
            order.append("prune")
            return retention.PruneResult()

        def fake_pricing(*args, **kwargs):
            return kwargs["counts"]

        def window_is_open():
            order.append("asked")
            return True

        monkeypatch.setattr(runner, "run_ingest_pass", fake_ingest)
        monkeypatch.setattr(runner, "run_pricing_pass", fake_pricing)
        monkeypatch.setattr(runner.retention, "prune", fake_prune)

        await runner.run_once(
            conn, None, None, None,
            config=_ODDS_CONFIG,
            window_open=window_is_open,
        )

        assert order == ["ingest", "asked"], (
            f"expected the window to be read after ingest and the prune to be "
            f"skipped; got {order}"
        )

    async def test_a_closed_window_still_prunes(self, monkeypatch, conn):
        """The gate has to let the prune through, or retention never runs."""
        from backend import runner
        from backend.store import retention

        order: list[str] = []

        async def fake_ingest(*args, **kwargs):
            order.append("ingest")
            return [], runner.PassCounts()

        def fake_prune(*args, **kwargs):
            order.append("prune")
            return retention.PruneResult()

        monkeypatch.setattr(runner, "run_ingest_pass", fake_ingest)
        monkeypatch.setattr(runner, "run_pricing_pass", lambda *a, **k: k["counts"])
        monkeypatch.setattr(runner.retention, "prune", fake_prune)

        await runner.run_once(
            conn, None, None, None,
            config=_ODDS_CONFIG,
            window_open=lambda: False,
        )

        assert order == ["ingest", "prune"]

    def test_the_loop_hands_the_prune_a_fresh_read_not_a_stored_flag(self):
        """One source of truth for 'is this minute bettable' -- and one *clock*.

        This used to assert `window_open=tempo.window_open`, on the reasoning
        that the prune and the cadence should read the same state. The reasoning
        was right and the object was wrong: `tempo.window_open` is assigned at
        `run_loop.py`'s end-of-pass hook and read at the *start* of the next
        pass, so it is the same source at a different time -- which is exactly
        the different clock the old docstring warned about. Measured
        2026-08-19: `15:32:14 full took_s 94.3 quotes_pruned 40000`, window open
        since 15:21Z.
        """
        from pathlib import Path

        source = Path("scripts/run_loop.py").read_text(encoding="utf-8")
        assert "window_open=lambda: window_now().is_open" in source, (
            "run_loop no longer hands run_once a callable that reads the window "
            "at the prune, so the prune is back on a stale flag and runs during "
            "windows"
        )
        assert "window_open=tempo.window_open" not in source, (
            "run_loop is passing the stored end-of-previous-pass flag again; "
            "that is the 2026-08-19 incident"
        )


class TestTheBudgetBuysMoreThanOneBatch:
    """The budget has to clear the table's growth, not just bound the stall.

    Throughput is `batches x DELETE_BATCH x passes-outside-a-window`. A budget
    below one batch's cost silently pins that to a single batch, and on live
    that was 1.58M rows/day against ~1.30M/day of growth -- a margin that runs
    out at 7.75 open hours/day, with 4.33 measured and two major leagues out of
    season. The failure is quiet: `quotes_pruned` reports a healthy number
    every pass while the table grows.
    """

    def test_the_budget_exceeds_one_measured_batch(self):
        """A batch cost ~20s on live; the budget must clear it to buy a second."""
        assert retention.DEFAULT_BUDGET_S > 20.0, (
            "the budget no longer clears one batch's measured ~20s cost, so it "
            "buys exactly one batch per pass and the prune falls behind growth "
            "as soon as the season adds window hours"
        )

    def test_a_budget_of_two_batches_deletes_two_batches(self, monkeypatch, conn):
        """The arithmetic above is only true if the loop actually continues."""
        monkeypatch.setattr(retention, "DELETE_BATCH", 3)
        for i in range(12):
            add_quote(conn, f"OLD{i}", age_days=10)

        # Batches here are instant, so any positive budget runs to exhaustion;
        # the claim under test is that the loop is not capped at one batch.
        removed = retention.prune_quotes(conn, now=NOW, budget_s=30)

        assert removed == 12, (
            "the prune stopped before exhausting a backlog it had budget for"
        )
