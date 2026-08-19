"""`link_discovered_events` says where its time went, but only when it is slow.

**What this establishes.** That the function emits one `link slow` line when it
exceeds `LINK_SLOW_REPORT_MS`, that the line carries the candidate-query cost
and call count, the unmatched-write cost and the link-write cost, that the
parts do not exceed the total, and that a fast call emits **nothing**.

**What it does not.** It does not establish that the three named costs are the
only places time can go -- that is exactly why the line carries an `other`
term rather than assuming the parts are exhaustive. It does not measure the
prop path separately, which lands in `other`. And it says nothing about *why*
any of them are slow.

**Why it exists.** `leg_price_link_ms` was measured on live 2026-08-19 swinging
2.1s to 20.7s **between adjacent passes on identical input** -- 531 events
discovered and 81 linked in both states -- while the walk, store, judge and
persist legs stayed flat. That is the third level of the same argument: one
number cannot say which of several costs moved, and on this incident the outer
legs and then the pricing split each answered in one pass what days of
reasoning had not.

**The conditionality is the design, not a shortcut.** The outer legs report on
every pass because a zero is informative there. Here the informative case is
the outlier, and this runs on the 15s cadence: an unconditional line would be
~5,700 a day against the 100-line `flyctl logs` buffer that the pass line
itself is rationed for.
"""

from __future__ import annotations

import logging

import pytest

from backend import runner
from backend.kalshi.discovery import DiscoveredEvent
from backend.runner import LINK_SLOW_REPORT_MS, link_discovered_events
from backend.store import db


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "link.db")
    yield c
    c.close()


def one_game() -> list[DiscoveredEvent]:
    """One game event, enough to make the loop body actually run.

    An empty slate skips the loop entirely, so every timer inside it stays at
    zero and any assertion about how those timers relate to each other passes
    without exercising a single line of the code under test. That is how the
    overlap check below was found to be vacuous: it was broken deliberately and
    stayed green.

    It does not need to *match* -- an unmatched event still runs the candidate
    query and the unmatched write, which is two of the three timers, and the
    third is the one an unmatched row cannot reach.
    """
    return [
        DiscoveredEvent(
            event_ticker="KXTEST-26AUG19",
            series_ticker="KXTEST",
            league="baseball_mlb",
            sport_key="baseball_mlb",
            market_type="moneyline",
            title="Nowhere vs Nobody",
            commence_ms=1_787_000_000_000,
            markets=(),
        )
    ]


class TestTheThresholdIsWhereTheClustersSeparate:
    def test_it_sits_between_the_measured_states(self) -> None:
        """Not a round number picked for looking tidy.

        Live measured the fast state at 2.0-2.4s across 29 consecutive passes
        and the slow state at 12.7s and up. A threshold inside either cluster
        would either spam or stay silent through the thing it exists to catch.
        """
        assert 2_400 < LINK_SLOW_REPORT_MS < 12_700


class TestAFastCallSaysNothing:
    def test_no_line_below_the_threshold(self, conn, caplog) -> None:
        """The half that keeps the log readable.

        A guard that fires on every pass is not a guard, it is 5,700 lines a
        day pushing the pass line out of a 100-line buffer.
        """
        with caplog.at_level(logging.WARNING, logger="backend.runner"):
            link_discovered_events(conn, [], now=1_787_000_000_000)
        assert "link slow" not in caplog.text


class TestASlowCallNamesItsParts:
    @pytest.fixture
    def slow(self, monkeypatch):
        """Force the call over the threshold without waiting for it.

        Patches the module-level constant rather than sleeping for eight real
        seconds: what is under test is that the branch fires and what it says,
        not the wall clock that trips it.
        """
        monkeypatch.setattr(runner, "LINK_SLOW_REPORT_MS", 0)

    def test_it_emits_exactly_one_line(self, conn, caplog, slow) -> None:
        with caplog.at_level(logging.WARNING, logger="backend.runner"):
            link_discovered_events(conn, [], now=1_787_000_000_000)
        assert caplog.text.count("link slow") == 1

    @pytest.mark.parametrize(
        "phrase",
        ["candidates", "calls", "unmatched writes", "link writes", "other",
         "discovered", "linked"],
    )
    def test_the_line_carries_every_term(
        self, conn, caplog, slow, phrase: str
    ) -> None:
        """Each term is asserted by name.

        `other` is the one that matters most and is easiest to drop: without
        it the three named costs read as exhaustive, and the prop path -- which
        is not timed separately -- would be silently attributed to whichever
        neighbour the reader assumed.
        """
        with caplog.at_level(logging.WARNING, logger="backend.runner"):
            link_discovered_events(conn, [], now=1_787_000_000_000)
        assert phrase in caplog.text

    def test_the_named_parts_do_not_exceed_the_total(
        self, conn, caplog, slow
    ) -> None:
        """Overlapping timers would double-count and mislead.

        `other` is computed as the remainder, so if the three named timers
        overlapped each other or the total, `other` would go negative -- which
        is the visible symptom this asserts against.
        """
        import re

        with caplog.at_level(logging.WARNING, logger="backend.runner"):
            link_discovered_events(conn, one_game(), now=1_787_000_000_000)
        assert "1 discovered" in caplog.text, (
            "the loop body did not run, so this asserts nothing"
        )
        other = re.search(r"other (-?\d+)ms", caplog.text)
        assert other is not None, caplog.text
        assert int(other.group(1)) >= 0, (
            f"`other` is negative ({other.group(1)}ms), so the named timers "
            "overlap each other or the total"
        )
