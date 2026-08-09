"""How many *distinct* games the sweep schedule reaches on a real slate.

`scripts/measure_slot_coverage.py` exists because two one-off readings of one
day disagreed: a handoff note said the schedule leaves the gate starved, and a
recount said the same day's slate generated six slots covering 18 of 19 games.
The tests below pin the recount to a captured slate so it cannot drift, and pin
the one thing that is easy to get wrong and impossible to see in the output --
**a game two slots both reach is one game, not two.**

Kickoffs are loaded from verbatim ESPN captures (`tests/fixtures/espn_*.json`),
never from hand-written payloads and never over the network. ESPN emits `date`
without seconds (`2026-08-09T16:15Z`), which is exactly the sort of detail a
hand-written fixture would have smoothed away.

What these tests do NOT establish
---------------------------------
That the live runner would produce this coverage. It plans from
`odds_snapshots`, so a sport never swept has no stored fixtures and no slots at
all; the script hands `plan_sweep_slots` every league unconditionally and
therefore measures the **ceiling**. Nor do they establish that a covered game
was quotable -- ESPN's schedule is not The Odds API's -- or that a covered game
is worth betting, which is the question the whole project exists to answer.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from conftest import load_fixture
from backend.kalshi.discovery import IN_SCOPE_LEAGUES
from backend.odds.timing import MIN_SLOT_SEPARATION_MS
from scripts.measure_slot_coverage import (
    ESPN_SCOREBOARD_PATHS,
    SEPARATION_HOURS,
    SWEEP_COST_CREDITS,
    Game,
    measure_coverage,
    parse_scoreboard,
    planning_anchor_ms,
)

HOUR = 3_600_000

# The date both captures were taken for. Every number asserted below is a
# property of this one slate; see the module docstring in the script.
SLATE_DATE = "20260809"


def ms(iso: str) -> int:
    return int(
        datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp() * 1000
    )


@pytest.fixture
def mlb_games() -> list[Game]:
    return parse_scoreboard("baseball_mlb", load_fixture("espn_scoreboard_mlb_20260809.json"))


@pytest.fixture
def wnba_games() -> list[Game]:
    return parse_scoreboard(
        "basketball_wnba", load_fixture("espn_scoreboard_wnba_20260809.json")
    )


@pytest.fixture
def slate(mlb_games, wnba_games) -> list[Game]:
    return mlb_games + wnba_games


@pytest.fixture
def anchor_ms() -> int:
    return planning_anchor_ms(SLATE_DATE)


class TestTheCaptureItself:
    """A truncated or re-scoped re-capture must fail loudly, not silently make
    every assertion below vacuous."""

    def test_the_captured_mlb_scoreboard_carries_a_full_days_slate(self, mlb_games):
        assert len(mlb_games) == 15

    def test_the_captured_wnba_scoreboard_carries_a_full_days_slate(self, wnba_games):
        assert len(wnba_games) == 4

    def test_every_captured_kickoff_falls_on_the_date_it_was_captured_for(self, slate):
        # ESPN's `dates=` parameter is US-Eastern, so a late West Coast game can
        # land on the following UTC day. Anything outside this range means the
        # capture is of a different slate than the assertions assume.
        assert all(
            ms("2026-08-09T00:00:00") <= g.commence_ms < ms("2026-08-10T12:00:00")
            for g in slate
        )

    def test_espn_omits_seconds_from_its_kickoff_field(self):
        # The detail a hand-written payload would have smoothed away, asserted
        # against the raw capture so a parser that requires seconds fails here.
        payload = load_fixture("espn_scoreboard_wnba_20260809.json")
        assert all(
            len(e["date"]) == len("2026-08-09T16:15Z") for e in payload["events"]
        )


class TestDistinctGamesAreCountedOnce:
    """The whole point. `SweepSlot.games_covered` is a per-slot count and two
    slots over adjacent clusters both reach the games between them."""

    def test_a_game_covered_by_two_slots_is_counted_once(self, wnba_games, anchor_ms):
        result = measure_coverage(wnba_games, now_ms=anchor_ms)

        assert len(result.covered) == len(set(wnba_games)) == 4

        # Asserted second so the line above owns the failure when the count is
        # wrong. This one guards the *fixture*: on a slate whose slots never
        # overlap, the assertion above passes for free and the test states
        # nothing. Verified by returning a tuple instead of a set -- the count
        # above goes to 6 and this stays true.
        double_counted = sum(s.games_covered for s in result.slots)
        assert double_counted > len(result.covered), (
            "this slate has no overlapping slots, so it cannot test the claim"
        )

    def test_one_slot_covers_exactly_what_that_slot_claims(
        self, wnba_games, anchor_ms
    ):
        # With a single slot there is no overlap to collapse, so the set must
        # reproduce `SweepSlot.games_covered` exactly. That pins the condition
        # this script applies to the one `slots_for_sport` applies -- if they
        # ever diverge, the distinct count above is measuring a different rule
        # than the scheduler uses.
        result = measure_coverage(wnba_games, now_ms=anchor_ms, slots_available=1)

        assert len(result.slots) == 1
        assert len(result.covered) == result.slots[0].games_covered


class TestTheAugustSlate:
    """The recount that contradicted the handoff note, frozen."""

    def test_the_captured_slate_generates_six_slots_at_the_deployed_separation(
        self, slate, anchor_ms
    ):
        result = measure_coverage(slate, now_ms=anchor_ms)

        assert len(slate) == 19
        assert len(result.slots) == 6
        assert result.credits == 6 * SWEEP_COST_CREDITS == 36

    def test_eighteen_of_nineteen_games_are_covered(self, slate, anchor_ms):
        result = measure_coverage(slate, now_ms=anchor_ms)
        assert len(result.covered) == 18

    def test_the_one_missed_game_is_the_days_first_kickoff(self, slate, anchor_ms):
        result = measure_coverage(slate, now_ms=anchor_ms)
        missed = [g for g in slate if g not in result.covered]

        assert len(missed) == 1
        assert missed[0].name == "CIN @ WSH"
        assert missed[0].commence_ms == ms("2026-08-09T16:15:00")
        # It is missed because it loses the greedy contest to the 17:35Z cluster
        # and then sits inside that slot's two-hour separation window -- not
        # because no window could close before it.
        assert missed[0].commence_ms == min(g.commence_ms for g in slate)

    def test_a_one_hour_separation_recovers_the_whole_slate_for_two_more_sweeps(
        self, slate, anchor_ms
    ):
        base = measure_coverage(slate, now_ms=anchor_ms)
        loose = measure_coverage(slate, now_ms=anchor_ms, min_separation_ms=HOUR)

        assert len(loose.slots) == 8
        assert loose.credits == 48
        assert len(loose.covered) == 19
        assert len(loose.slots) - len(base.slots) == 2


class TestSensitivity:
    def test_loosening_the_separation_never_reduces_coverage(self, slate, anchor_ms):
        # Monotone by construction: a smaller separation can only admit slots
        # the larger one excluded, and an extra slot can only add games. A
        # violation means selection is not what it is documented to be.
        results = [
            measure_coverage(
                slate, now_ms=anchor_ms, min_separation_ms=int(h * HOUR)
            )
            for h in SEPARATION_HOURS
        ]
        covered = [len(r.covered) for r in results]
        slots = [len(r.slots) for r in results]

        assert SEPARATION_HOURS == tuple(sorted(SEPARATION_HOURS, reverse=True))
        assert covered == sorted(covered)
        assert slots == sorted(slots)


class TestParsing:
    def test_an_unreadable_kickoff_is_dropped_rather_than_placed_at_the_epoch(self):
        # Unreadable resolves to None, never 0. A game silently placed at the
        # epoch sits before every slot and reads as a permanent miss -- an
        # invented finding, which is worse than a dropped row.
        payload = load_fixture("espn_scoreboard_wnba_20260809.json")
        broken = dict(payload)
        broken["events"] = [dict(e) for e in payload["events"]]
        broken["events"][0]["date"] = "not a timestamp"

        parsed = parse_scoreboard("basketball_wnba", broken)

        assert len(parsed) == len(payload["events"]) - 1
        assert all(g.commence_ms > 0 for g in parsed)


class TestScheduleInputs:
    def test_every_in_scope_league_has_an_espn_scoreboard_path(self):
        # A league added to IN_SCOPE_LEAGUES without a path here would be
        # silently absent from every slate, which reads as "that sport had no
        # games" -- the failure this harness exists to remove.
        assert set(ESPN_SCOREBOARD_PATHS) == set(IN_SCOPE_LEAGUES.values())

    def test_the_planning_anchor_is_the_budget_day_start_not_the_current_instant(
        self,
    ):
        # Planning from "now" answers "how many slots are left", which shrinks
        # through the day; run at 23:00Z it would report an empty schedule
        # because the games have started. The measurement has to be the same
        # number whenever it is asked.
        assert planning_anchor_ms(SLATE_DATE) == ms("2026-08-09T10:00:00")

    def test_the_deployed_separation_is_read_from_timing_not_retyped(self):
        assert MIN_SLOT_SEPARATION_MS == int(SEPARATION_HOURS[0] * HOUR)
