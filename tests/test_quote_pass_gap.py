"""The quote pass times the two pieces that sat outside every leg.

**What this establishes.** That a quote pass reports `leg_series_ms` and
`leg_sweep_ms`; that they are reported at zero rather than omitted; that
`run_quote_pass` assigns them; that a slow `priceable_series` lands on `series`
and not inside the walk; and that `sweep` is timed even when no sweep happens,
so a refused sweep and an untimed one are distinguishable.

**What it does not.** It does not establish that the legs are now exhaustive.
`took_s` is measured by the scheduler around the whole call, and these tests do
not run the scheduler, so nothing here proves the six numbers close the gap on
live -- only that the two known pieces are no longer invisible. It does not
establish that either piece is slow: on 2026-08-19 nobody had measured them at
all, which is the entire reason they are here. And it drives an empty slate, so
it says nothing about scaling.

**Why it exists.** On 2026-08-19, with the box on `a482fea`, the four legs of a
quote pass summed to **18.8s of a 34.1s pass**. Across 61 consecutive passes the
median shortfall was **3.9s** and the worst was **15.3s** -- so roughly a fifth
of the pass was attributed to nothing at all, on a 15s cadence the pass was
already overrunning.

`tests/test_pass_leg_timings.py` predicted this in writing: *"anything a caller
does between them is in `took_s` and in none of these fields ... read it as
'time went somewhere none of these four legs covers'."* It was right, and the
honest response to a documented blind spot that has started to matter is to
light it up rather than to keep reading around it.
"""

from __future__ import annotations

import inspect
import time

from backend import runner
from backend.runner import PassCounts, run_quote_pass
from backend.store import db

GAP_LEGS = ("leg_series_ms", "leg_sweep_ms")


class _EmptyKalshi:
    """Yields no events. The slate is not what these tests are about."""

    async def events(self, **kwargs):
        return
        yield  # pragma: no cover -- makes this an async generator


async def _quote_pass(tmp_path, name="quote_gap.db") -> PassCounts:
    conn = db.init_db(tmp_path / name)
    try:
        return await run_quote_pass(
            conn, _EmptyKalshi(), now=1_787_000_000_000
        )
    finally:
        conn.close()


class TestBothPiecesAreReportedEvenWhenZero:
    """A refused sweep and an untimed sweep must not look the same.

    `decide_sweeps` says "not yet" on about 39 passes in 40, so `leg_sweep_ms`
    is legitimately ~0 almost always. That is exactly the state in which
    `as_dict`'s falsy filter would drop the key -- and then a sweep leg that had
    silently stopped being timed would be indistinguishable from the normal
    case, forever.
    """

    def test_a_pass_that_did_nothing_still_names_both(self) -> None:
        reported = PassCounts().as_dict()
        for leg in GAP_LEGS:
            assert leg in reported, (
                f"`{leg}` vanishes from a pass line at zero, so 'this piece is "
                "fast' cannot be told from 'this piece was never timed'"
            )
            assert reported[leg] == 0

    def test_a_timed_piece_reports_its_own_number(self) -> None:
        counts = PassCounts(leg_series_ms=140, leg_sweep_ms=3900)
        reported = counts.as_dict()

        assert reported["leg_series_ms"] == 140
        assert reported["leg_sweep_ms"] == 3900


class TestTheCodeActuallyFillsThemIn:
    def test_the_quote_pass_assigns_both(self) -> None:
        source = inspect.getsource(runner.run_quote_pass)
        for leg in GAP_LEGS:
            assert f"counts.{leg} =" in source, (
                f"`run_quote_pass` no longer records `{leg}`; the column will "
                "read 0 forever and be mistaken for a piece that is not the "
                "problem"
            )

    async def test_a_real_quote_pass_carries_both(self, tmp_path) -> None:
        """The half source inspection cannot reach: the pass actually runs."""
        counts = await _quote_pass(tmp_path)

        for leg in GAP_LEGS:
            assert hasattr(counts, leg), leg
            assert getattr(counts, leg) >= 0


class TestTheBoundariesAreWhereTheyClaimToBe:
    async def test_a_slow_series_lookup_lands_on_series(
        self, tmp_path, monkeypatch
    ) -> None:
        """Verified by making it slow and watching which number moves.

        `priceable_series` is evaluated as an *argument* to `run_kalshi_pass`,
        so before this timer existed its cost fell outside `leg_walk_ms` --
        outside every leg -- while looking for all the world like part of the
        walk. That is the specific misreading this boundary prevents.
        """
        real = runner.priceable_series

        def slow(*args, **kwargs):
            time.sleep(0.25)
            return real(*args, **kwargs)

        monkeypatch.setattr(runner, "priceable_series", slow)
        counts = await _quote_pass(tmp_path, name="slow_series.db")

        assert counts.leg_series_ms >= 250, (
            f"a 250ms series lookup landed as {counts.leg_series_ms}ms"
        )
        assert counts.leg_walk_ms < 250, (
            f"the walk absorbed the series lookup ({counts.leg_walk_ms}ms), so "
            "a growing scan over kalshi_events would read as a slow HTTP walk"
        )

    async def test_the_series_lookup_is_not_inside_the_store_leg(
        self, tmp_path, monkeypatch
    ) -> None:
        """The other neighbour, so the check above cannot pass by being wide.

        A single-sided boundary test is satisfied by a timer that runs long in
        the direction nobody checked.
        """
        real = runner.priceable_series

        def slow(*args, **kwargs):
            time.sleep(0.25)
            return real(*args, **kwargs)

        monkeypatch.setattr(runner, "priceable_series", slow)
        counts = await _quote_pass(tmp_path, name="slow_series_2.db")

        assert counts.leg_store_ms < 250, (
            f"the store leg absorbed the series lookup "
            f"({counts.leg_store_ms}ms)"
        )
        assert counts.leg_price_ms < 250, (
            f"the pricing leg absorbed the series lookup "
            f"({counts.leg_price_ms}ms)"
        )
