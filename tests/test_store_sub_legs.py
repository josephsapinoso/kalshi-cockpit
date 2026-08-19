"""`leg_store_ms` is split in two, and both halves are always reported.

**What this establishes.** That a pass reports `leg_store_upsert_ms` and
`leg_store_quotes_ms`; that they are reported at zero rather than omitted; that
`run_kalshi_pass` actually assigns them; that they account for `leg_store_ms`
rather than leaving work untimed; and -- the half source inspection cannot
reach -- that a slow `store_quotes_from_discovery` lands on `quotes` and not on
`upsert`.

**What it does not.** It does not establish that either half is fast, or that
this is the right cut: both calls write to more than one table and a cost could
sit inside one of them for a reason neither name captures. It measures wall
clock, so on a contended box a half reads slow because the process was
descheduled. And it drives an empty slate, so it says nothing about how either
half scales with the number of markets -- which is the very thing the split was
added to find out.

**Why it exists.** On 2026-08-19 the candidate-query fix took `leg_price_ms`
from 12-20s to ~0.6s, and `leg_store_ms` became the largest leg of the quote
pass -- 10-19s of an 18-35s pass against a 15s cadence, with the scheduler
warning that quote rows now expire between confirmations. One total cannot say
which of the two calls moved, and the two point at different diagnoses:

    upsert  ~7,100 upserts across three tables the slate bounds
    quotes  ~5,960 appends into kalshi_quotes, which has millions of rows

`quotes` climbing is insert cost rising with the table -- the same shape as the
`_match_candidates` scan resolved hours earlier. `upsert` climbing is not, and
would be fixed nothing like the same way. Guessing between them is what cost
four sessions on the pricing leg; timing them settled it in one pass.
"""

from __future__ import annotations

import inspect
import time

from backend import runner
from backend.runner import PassCounts, run_kalshi_pass
from backend.store import db

SUB_LEGS = ("leg_store_upsert_ms", "leg_store_quotes_ms")


class _EmptyKalshi:
    """Yields no events. The slate is not what these tests are about."""

    async def events(self, **kwargs):
        return
        yield  # pragma: no cover -- makes this an async generator


async def _empty_pass(tmp_path, name="store_sub_legs.db") -> PassCounts:
    conn = db.init_db(tmp_path / name)
    counts = PassCounts()
    try:
        await run_kalshi_pass(
            conn,
            _EmptyKalshi(),
            now=1_787_000_000_000,
            counts=counts,
            series_tickers=None,
        )
    finally:
        conn.close()
    return counts


class TestBothHalvesAreReportedEvenWhenZero:
    """Absence and zero need opposite responses, so zero must be printed.

    A missing key means the half was never timed; a zero means it ran and is
    not the problem. `as_dict` drops falsy values unless the key is in
    `ALWAYS_REPORT`, and the skeptic fields were already lost to exactly that
    filter, in exactly this state.
    """

    def test_a_pass_that_did_nothing_still_names_both(self) -> None:
        reported = PassCounts().as_dict()
        for leg in SUB_LEGS:
            assert leg in reported, (
                f"`{leg}` vanishes from a pass line at zero, so 'this half is "
                "fast' cannot be told from 'this half was never timed'"
            )
            assert reported[leg] == 0

    def test_the_total_is_still_reported_beside_the_parts(self) -> None:
        """Reporting parts and dropping the whole makes the sum uncheckable.

        A log line is the only place these are ever read, so the check that the
        parts account for the whole has to be possible from the line alone.
        """
        assert "leg_store_ms" in PassCounts().as_dict()

    def test_a_timed_half_reports_its_own_number(self) -> None:
        counts = PassCounts(leg_store_upsert_ms=1100, leg_store_quotes_ms=9200)
        reported = counts.as_dict()

        assert reported["leg_store_upsert_ms"] == 1100
        assert reported["leg_store_quotes_ms"] == 9200


class TestTheCodeActuallyFillsThemIn:
    """Fields existing is not the same as the pass assigning them.

    Without this, the guards above pass against two permanently-zero columns
    that look exactly like two fast halves.
    """

    def test_the_kalshi_pass_assigns_both_halves(self) -> None:
        source = inspect.getsource(runner.run_kalshi_pass)
        for leg in SUB_LEGS:
            assert f"counts.{leg} =" in source, (
                f"`run_kalshi_pass` no longer records `{leg}`; the column will "
                "read 0 forever and be mistaken for a fast half"
            )

    async def test_a_real_pass_returns_counts_carrying_both(self, tmp_path):
        """The half source inspection cannot reach: the pass actually runs."""
        counts = await _empty_pass(tmp_path)

        for leg in SUB_LEGS:
            assert hasattr(counts, leg), leg
        assert counts.leg_store_ms >= 0


class TestTheHalvesAccountForTheWhole:
    async def test_the_two_sum_to_the_total(self, tmp_path):
        """Catches new work added between the two boundaries without a timer.

        Work inserted between `upsert_discovered` and
        `store_quotes_from_discovery` would otherwise be attributed to
        whichever neighbour encloses it, or fall outside both and be silently
        missing from the split -- the failure this file exists to prevent.
        """
        counts = await _empty_pass(tmp_path, name="store_sum.db")
        parts = counts.leg_store_upsert_ms + counts.leg_store_quotes_ms

        # Slack for two independent int() truncations.
        assert parts <= counts.leg_store_ms + 4, (
            f"halves sum to {parts}ms, more than the {counts.leg_store_ms}ms "
            "total -- the boundaries overlap"
        )
        assert parts >= counts.leg_store_ms - 4, (
            f"halves sum to {parts}ms but the total is {counts.leg_store_ms}ms "
            "-- some work in the store leg is outside both timers"
        )

    async def test_slow_quote_writes_land_on_quotes_and_not_on_upsert(
        self, tmp_path, monkeypatch
    ):
        """The boundary that would send the next session to the wrong call.

        Verified by making one half slow and watching which number moves --
        not by reading where the timer is written. If `quotes` were inside the
        `upsert` window, an insert cost rising with `kalshi_quotes` would read
        as a slow upsert, and the fix for those two is not the same fix.
        """
        real = runner.store_quotes_from_discovery

        def slow(*args, **kwargs):
            time.sleep(0.25)
            return real(*args, **kwargs)

        monkeypatch.setattr(runner, "store_quotes_from_discovery", slow)
        counts = await _empty_pass(tmp_path, name="slow_quotes.db")

        assert counts.leg_store_quotes_ms >= 250, (
            f"a 250ms quote write landed as {counts.leg_store_quotes_ms}ms on "
            "the quotes half"
        )
        assert counts.leg_store_upsert_ms < 250, (
            f"the upsert half absorbed the quote-write cost "
            f"({counts.leg_store_upsert_ms}ms), so a table-size effect on "
            "kalshi_quotes will read as a slow upsert"
        )
        assert counts.leg_store_ms >= 250

    async def test_slow_upserts_land_on_upsert_and_not_on_quotes(
        self, tmp_path, monkeypatch
    ):
        """The mirror, so the test above cannot pass by both halves being wide.

        A single-sided check is satisfied by a timer that starts too early and
        stops too late; running the same experiment from the other end is what
        makes the boundary claim real rather than directional.
        """
        real = runner.upsert_discovered

        def slow(*args, **kwargs):
            time.sleep(0.25)
            return real(*args, **kwargs)

        monkeypatch.setattr(runner, "upsert_discovered", slow)
        counts = await _empty_pass(tmp_path, name="slow_upsert.db")

        assert counts.leg_store_upsert_ms >= 250, (
            f"a 250ms upsert landed as {counts.leg_store_upsert_ms}ms on the "
            "upsert half"
        )
        assert counts.leg_store_quotes_ms < 250, (
            f"the quotes half absorbed the upsert cost "
            f"({counts.leg_store_quotes_ms}ms)"
        )
