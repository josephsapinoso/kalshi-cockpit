"""The NFL budget-day simulator, pinned against the figure already in the record.

**This file exists because the simulator published 116 when the answer was 124.**
It reimplemented `SweepSlot.is_due` as `fire_from <= now < fire_until`, where
production's is `fire_from <= now <= fire_until` (`backend/odds/timing.py:281`).
The strict `<` drops the seventh call of every window. The script's own banner
printed "7 calls per full window" three lines above a body that produced six,
and nobody read across.

`tests/test_sweep_timing.py::test_a_full_window_is_seven_calls_and_the_number_is
_written_down` already existed to stop a six being quoted -- it pins the
multiplier inside the planner. It could not catch this, because the defect was
in a *consumer* that restated the predicate instead of calling it. So the rule
this file enforces is narrower and sharper: **the simulator must agree with the
number this repo has already published**, and the arithmetic `7 x clusters` must
appear in its output rather than being asserted only in prose.

What these tests do NOT establish: anything about what a day costs. The
simulator models demand -- what the planner asks for -- with no credit ledger
and no network. See its module docstring and
`docs/measurements/2026-09-08-nfl-sunday-credit-convergence.md`.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

sim = importlib.import_module("scripts.simulate_nfl_sunday_credits")


@pytest.fixture(scope="module")
def season() -> list[int]:
    return sim.kickoffs()


@pytest.fixture(scope="module")
def all_days(season) -> list[dict]:
    """Every NFL budget day, simulated ONCE.

    The simulator replans on every step, so a season sweep is ~7s. Three tests
    needed one and the first draft of this file ran three sweeps, taking 35s to
    assert three cheap properties -- exactly the shape `tasks/NEXT.md` warns
    about (a 71-second copula asserting a dictionary length).
    """
    return [sim.simulate_day(d, season) for d in sorted({sim._budget_day(k) for k in season})]


def _day(date: str) -> int:
    return sim._budget_day(sim._ms(f"{date}T12:00:00Z"))


class TestTheSundayFigureAgreesWithTheRecord:
    """124 is published in two places already; a third must not disagree quietly."""

    def test_the_2026_09_13_budget_day_asks_for_124_credits(self, season):
        """The value, pinned. `docs/measurements/2026-09-06-nfl-week-1-credit-headroom.md`
        Amendment 1 and `test_a_full_window_is_seven_calls...`'s docstring both
        say 124; this is the third derivation and it must land on the same number.
        """
        row = sim.simulate_day(_day("2026-09-13"), season)
        assert row["credits"] == 124, (
            f"the simulator says {row['credits']} where the record says 124. "
            "Either the record is wrong or this script is; do not publish until "
            "you know which."
        )
        assert row["calls"] == 31
        assert (row["window_calls"], row["floor_calls"]) == (21, 10)

    def test_three_clusters_and_the_night_game_shares_their_budget_day(self, season):
        """The convergence itself: the 00:20Z nighter is before the 10:00Z roll."""
        row = sim.simulate_day(_day("2026-09-13"), season)
        assert row["slots"] == 3
        assert row["slot_detail"] == ["09-13 17:00Z", "09-13 20:25Z", "09-14 00:20Z"]


class TestTheWindowIsSevenCallsWhereverItIsCounted:
    """The assertion that would have caught the defect on the day it was written.

    A fully-interior cluster -- one whose whole 60-minute window sits inside the
    budget day with no other cluster overlapping it -- must produce exactly
    `7 x clusters` window calls. Under the strict-`<` bug it produced six each.
    """

    def test_a_single_cluster_day_asks_for_exactly_seven_window_calls(self, all_days):
        one_slot = [r for r in all_days if r["slots"] == 1]
        assert one_slot, "no single-cluster day in the season to test against"
        row = one_slot[0]
        assert row["window_calls"] == 7, (
            f"a lone cluster asked for {row['window_calls']} window calls, not 7. "
            "Six is the count of REFRESHES; seven is the count of CALLS."
        )

    def test_the_banner_arithmetic_and_the_body_agree(self, season):
        """The self-contradiction that was printed and not read.

        The header computes calls-per-window from the constants; the body counts
        them. On a day of non-overlapping clusters the two must multiply out.
        """
        from backend.odds.timing import DUE_WINDOW_MS, refresh_interval_ms

        per_window = DUE_WINDOW_MS // refresh_interval_ms(sim.MAX_ODDS_AGE_MS) + 1
        assert per_window == 7

        row = sim.simulate_day(_day("2026-09-13"), season)
        assert row["window_calls"] == per_window * row["slots"]


class TestTheSeasonWorstIsAFiveClusterDay:
    """Reported because a four-cluster answer was published first and was wrong."""

    def test_the_slot_distribution_has_five_cluster_days_in_it(self, all_days):
        counts = [r["slots"] for r in all_days]
        assert max(counts) == 5, (
            f"largest cluster count is {max(counts)}; the one-shot-plan version "
            "of this script reported 4 because it never replanned"
        )
        assert counts.count(5) == 6
