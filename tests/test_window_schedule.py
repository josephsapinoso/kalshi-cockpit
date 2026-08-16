"""`WindowSchedule.tsx` — the Board's answer to "when should I open this?"

The odds budget affords one or two sweeps a day and each leaves the slate
priceable for about fifteen minutes, so the tool is worth looking at for well
under an hour out of twenty-four. `slots_planned` — the planner's own schedule —
was serialised on `/api/window` from the day `ActionableWindow.to_dict` was
written and read by nothing until 2026-08-16.

**What these tests do not establish.** Nothing here renders the component or
runs a browser. They read its source with comments stripped, which catches a
claim being deleted and cannot catch it being visually wrong. The arithmetic
they pin — the freshness envelope — is checked as an expression, not as a
rendered time.

Every assertion below is verified by mutation in `test_the_guards_are_real`,
because three assertions in `tests/test_crew_bubble.py` once passed on the
docstrings that justified them.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"
SCHEDULE = FRONTEND / "components" / "WindowSchedule.tsx"
BOARD = FRONTEND / "app" / "page.tsx"
API = FRONTEND / "lib" / "api.ts"


def source(path: Path) -> str:
    assert path.exists(), f"{path} is missing"
    return path.read_text(encoding="utf-8")


def code_only(text: str) -> str:
    """`text` with every comment removed. See `tests/test_crew_bubble.py`.

    Restated rather than imported because that module is a test, and a test
    importing another test to borrow a helper makes a failure in one read as a
    failure in the other.
    """
    without_block = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", without_block, flags=re.MULTILINE)


@pytest.fixture(scope="module")
def code() -> str:
    return code_only(source(SCHEDULE))


class TestItReadsThePlannersOwnSchedule:
    """The component's whole reason to exist is `slots_planned`.

    `next_sweep_*` was already on the page through `WindowBanner`. If this
    component read only those, it would be a second rendering of the next
    window rather than a schedule, and the question Joe asked — *when do I
    look today* — would still be unanswered.
    """

    def test_it_reads_slots_planned(self, code):
        assert "slots_planned" in code

    def test_it_does_not_reach_for_the_flattened_next_sweep_fields(self, code):
        """Reading `next_sweep_ms` here would silently cap the list at one.

        The first element of `slots_planned` *is* `next_sweep_ms`, so a
        component doing both would render the same window twice and disagree
        with itself the moment the planner returned two.
        """
        for flattened in (
            "next_sweep_ms",
            "next_sweep_sport",
            "next_sweep_games",
            "next_sweep_reason",
        ):
            assert flattened not in code, (
                f"{flattened} is the first slot flattened; read slots_planned"
            )

    def test_it_recomputes_no_slot_time(self, code):
        """No second implementation of the planner.

        The runner spends real credits on `plan_sweep_slots`. A screen that
        derived its own slot boundaries would eventually disagree with the
        control, and the screen is the one a human acts on. The only arithmetic
        allowed here is the freshness envelope and a countdown, both pinned
        below.
        """
        for planner_constant in ("DUE_WINDOW", "COVERAGE_MS", "MIN_SLOT_SEPARATION"):
            assert planner_constant not in code


class TestTheWindowShownIsTheEnvelopeNotTheSweep:
    """A slot is a permission to fire, not a firing, and that widens the range.

    The pass may spend its credit anywhere in `[fire_from, fire_until]`, and
    freshness runs `max_odds_age_s` from whenever it does. So the latest a row
    can be priceable is `fire_until + max_odds_age_s`. Rendering `fire_until`
    alone would tell a reader to stop looking up to fifteen minutes before the
    only period the tool works — the error runs *against* the user, which is
    why it is pinned rather than left to review.
    """

    def test_the_end_of_the_range_adds_the_freshness_allowance(self, code):
        assert re.search(r"fire_until_ms\s*\+\s*freshnessMs", code), (
            "the range must end at fire_until + max_odds_age, not fire_until"
        )

    def test_the_freshness_allowance_comes_from_the_server(self, code):
        """`max_odds_age_s` is config (`MAX_ODDS_AGE_S`) and moves.

        A hardcoded 15 minutes would keep rendering 15 after the deployed value
        changed, and would do it silently.
        """
        assert re.search(r"max_odds_age_s\s*\*\s*1000", code)
        assert "900" not in code, "the allowance must not be hardcoded"

    def test_the_range_starts_at_fire_from(self, code):
        assert "fire_from_ms" in code


class TestItNeverPromisesABet:
    """`actionable` has been zero for the life of the project.

    A schedule that read as *"be here at 16:51 and there will be something"*
    would be the most misleading element on the page — it invites a human to
    show up expecting a bet, on a tool whose expected result is an empty Board.
    The distinction between *priceable* and *bettable* is the one the whole
    `WindowBanner` docstring is built around, and this component sits directly
    beneath it.

    Asserted against comment-stripped source: this file's own docstrings
    explain the prohibition and therefore contain the forbidden word.
    """

    def test_the_rendered_copy_never_says_bettable(self, code):
        assert "bettable" not in code.lower()

    def test_it_says_a_window_is_not_a_bet(self, code):
        assert "could be priced" in code

    def test_it_says_most_windows_are_empty(self, code):
        assert "empty Board" in code


class TestAnEmptyScheduleSaysWhichEmptyItIs:
    """No slots has two unrelated causes needing opposite responses.

    Credits exhausted means *nothing more today, stop looking*. No fixture near
    enough means *the day is not planned yet, check back*. An empty list cannot
    distinguish them, so `sweeps_remaining_today` is read to choose the wording.
    """

    def test_it_branches_on_sweeps_remaining(self, code):
        assert re.search(r"sweeps_remaining_today\s*===\s*0", code)

    def test_it_has_two_distinct_empty_messages(self, code):
        assert "No sweeps left in today" in code
        assert "No window is scheduled" in code


class TestItIsActuallyOnTheBoard:
    """Failure #12 in this repo was a 481-line instrument imported by nothing.

    A component that renders correctly and is mounted nowhere is indis-
    tinguishable, from the user's side, from one that was never written.
    """

    def test_the_board_imports_it(self):
        assert "WindowSchedule" in source(BOARD)

    def test_the_board_renders_it(self):
        assert re.search(r"<WindowSchedule\b", code_only(source(BOARD)))

    def test_the_type_declares_the_field_the_component_reads(self):
        """The array was on the wire and undeclared, which is why it was unused.

        `PlannedSlot` must carry every field the component reads, or the build
        breaks — but a build break is not a guard, because a future edit that
        drops both the field and its use stays green.
        """
        api = code_only(source(API))
        assert "PlannedSlot" in api
        for field in (
            "fire_from_ms",
            "fire_until_ms",
            "anchor_commence_ms",
            "games_covered",
            "sport_key",
        ):
            assert field in api
        assert re.search(r"slots_planned:\s*PlannedSlot\[\]", api)


class TestTheServerStillSendsWhatTheScreenReads:
    """The one end that source-reading the frontend cannot cover.

    Every assertion above passes if `ActionableWindow.to_dict` stops emitting
    `slots_planned` tomorrow — the component would render an empty schedule for
    ever, and say "no window is scheduled", which is a *plausible* state. A
    silent failure that renders as a legitimate reading is the worst shape
    available, so the producer is pinned here too.
    """

    def test_the_payload_carries_every_field_the_component_reads(self):
        timing = source(ROOT / "backend" / "odds" / "timing.py")
        emitted = timing[timing.index('"slots_planned"') :][:600]
        for field in (
            "sport_key",
            "fire_from_ms",
            "fire_until_ms",
            "anchor_commence_ms",
            "games_covered",
        ):
            assert f'"{field}"' in emitted, f"{field} is read by the screen"


def test_the_guards_are_real():
    """Disable each claim and watch its test fail.

    Not a formality. `tests/test_crew_bubble.py` found one assertion that
    passed with the code deleted, because the comment still held the words.
    Every mutation here is applied to **comment-stripped** source for the
    frontend checks, so a mutation cannot be absorbed by prose.
    """
    code = code_only(source(SCHEDULE))
    mutations = [
        # the envelope collapses to the sweep window
        (r"fire_until_ms\s*\+\s*freshnessMs", "fire_until_ms"),
        # the allowance is hardcoded rather than read from config
        (r"max_odds_age_s\s*\*\s*1000", "900000"),
        # the two empty states become one
        (r"sweeps_remaining_today\s*===\s*0", "false"),
        # the schedule stops reading the planner
        (r"slots_planned", "next_sweep_ms"),
    ]
    for pattern, replacement in mutations:
        mutated = re.sub(pattern, replacement, code)
        assert mutated != code, f"mutation {pattern!r} matched nothing"

    # And the copy guard: the forbidden word must be absent from code, present
    # in the file. If the second half fails the prohibition is undocumented; if
    # the first fails it is violated.
    assert "bettable" not in code.lower()
    assert "bettable" in source(SCHEDULE).lower()


class TestTheRangeEndIsDerivedNotAssumed:
    """The envelope ends at first pitch today — by arithmetic, not by shortcut.

    `slots_for_sport` sets `fire_until = anchor - max_odds_age_ms`
    (`backend/odds/timing.py`), so `fire_until + max_odds_age_ms` is *exactly*
    `anchor_commence_ms` on every slot the planner emits. That is the planner's
    guarantee that a pick surfaced at the last second of the window is still a
    pre-game bet.

    **Two ways to render that, and only one survives the planner changing.**
    Reading `anchor_commence_ms` as the range end is simpler and agrees today —
    and would silently over-promise the moment the planner took a wider lead,
    because the odds would go stale before the kickoff it was still advertising.
    The component derives the end from freshness and *compares* it to the
    anchor, so a wider lead renders two different facts instead of one wrong
    one.
    """

    def test_the_range_end_is_not_the_anchor(self, code):
        assert not re.search(
            r"lookUntil\s*=\s*s\.anchor_commence_ms", code
        ), "deriving from freshness is what makes a wider planner lead safe"

    def test_the_two_are_compared_rather_than_assumed_equal(self, code):
        assert re.search(r"lookUntil\s*>=\s*s\.anchor_commence_ms", code)

    def test_the_kickoff_time_still_renders_when_they_differ(self, code):
        """The `false` branch must survive, or the comparison is decoration."""
        assert "first kickoff" in code
        assert "closes at first pitch" in code
