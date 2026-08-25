"""The stale count carries an exit: a next-window time, a tap, and teaching.

Joe reported the pain directly (2026-08-22): the slate's refusal disclosure
rendered `stale_odds x 33` and nothing else, which reads as "33 bad bets"
with nothing to do about it. What it means is 33 *unpriced* rows -- the
sportsbook side of the comparison is past `MAX_ODDS_AGE_S`, i.e. the screen
is being read outside a scheduled odds window. The fix is an exit beside the
count, never a softer gate: staleness is a validity check, not a weighted
factor.

`frontend/src/lib/nextOddsWindow.ts` is the pure decision; this executes it
with node the way `test_refresh_urgency.py` executes the urgency read,
because a substring assertion passes unchanged on an inverted branch. The
source pins then check the slate page actually wires the exit -- the pure
function being right proves nothing if nothing calls it.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- Nothing about `/api/window`'s own numbers being right -- `next_sweep_ms`
  is `window_status().next_call_ms`, and `test_sweep_timing.py` owns that
  planner. This trusts the wire shape.
- Nothing about the refresh actually being served: the button posts to
  `/refresh-odds`, and the server-side gates (cooldown, the taps' daily
  slice, the odds budget) are `test_ondemand_refresh.py`'s to prove. This
  slice adds a caller, not a gate.
- Nothing about how the exit renders at any width; `scripts/check_mobile.py`
  owns overflow.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
LIB_TS = REPO / "frontend" / "src" / "lib" / "nextOddsWindow.ts"
SLATE_PAGE = REPO / "frontend" / "src" / "app" / "slate" / "page.tsx"
PARLAYS_PAGE = REPO / "frontend" / "src" / "app" / "parlays" / "page.tsx"
EXIT = REPO / "frontend" / "src" / "components" / "StaleOddsExit.tsx"
PARLAY_CARDS = REPO / "frontend" / "src" / "components" / "ParlayCards.tsx"
BUTTON = REPO / "frontend" / "src" / "components" / "RefreshOddsButton.tsx"

NODE = shutil.which("node")

_DRIVER = """
import {
  readNextWindow,
  isStaleOddsReason,
  slateIsUnpricedByTheClock,
} from "./nextOddsWindow.ts";
const args = JSON.parse(process.argv[2]);
const result =
  args.fn === "read"
    ? readNextWindow(args.facts)
    : args.fn === "cold"
      ? slateIsUnpricedByTheClock(args.rows, args.maxOddsAgeMs)
      : isStaleOddsReason(args.reason);
console.log(JSON.stringify(result === undefined ? null : result));
"""


def _run(payload: dict):
    driver = LIB_TS.parent / "_stale_exit_driver.mjs"
    driver.write_text(_DRIVER, encoding="utf-8")
    try:
        out = subprocess.run(
            [NODE, "--experimental-strip-types", str(driver), json.dumps(payload)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            cwd=str(LIB_TS.parent),
        )
    finally:
        driver.unlink(missing_ok=True)
    assert out.returncode == 0, f"node failed:\n{out.stdout}\n{out.stderr}"
    return json.loads(out.stdout.strip())


def read(facts):
    return _run({"fn": "read", "facts": facts})


def is_stale(reason):
    return _run({"fn": "stale", "reason": reason})


def cold(rows, max_odds_age_ms=900_000):
    return _run({"fn": "cold", "rows": rows, "maxOddsAgeMs": max_odds_age_ms})


FRESH_ROW = {"odds_age_now_ms": 60_000, "suppressed_reason": None}
REFUSED_STALE = {"odds_age_now_ms": 1_200_000, "suppressed_reason": "stale_odds"}
REFUSED_OTHER = {"odds_age_now_ms": 60_000, "suppressed_reason": "wide_market"}


def facts(
    now_ms=1_000_000,
    next_sweep_ms=None,
    sweeps_remaining_today=2,
    last_look_ms=None,
):
    """`last_look_ms=None` is the pre-stall default: unknown, never stopped.

    Every case written before 2026-08-25 relies on that -- the stall branch must
    not fire for a caller that never supplied the field.
    """
    return {
        "now_ms": now_ms,
        "next_sweep_ms": next_sweep_ms,
        "sweeps_remaining_today": sweeps_remaining_today,
        "last_look_ms": last_look_ms,
    }


requires_node = pytest.mark.skipif(
    NODE is None,
    reason=(
        "node is not on PATH. Skipped rather than xfailed: the guard is real "
        "where node exists (CI and both dev machines)."
    ),
)


@requires_node
class TestTheNextWindowReadingIsHonest:
    def test_a_scheduled_window_carries_its_real_time(self):
        """The happy path: a future `next_sweep_ms` comes back as the moment
        it is, for the page to format through DISPLAY_TIME_ZONE."""
        reading = read(facts(now_ms=1_000_000, next_sweep_ms=4_600_000))
        assert reading["kind"] == "scheduled"
        assert reading["open_ms"] == 4_600_000
        assert reading["now_ms"] == 1_000_000

    def test_a_window_already_wanted_says_now_not_a_past_time(self):
        """`next_call_ms` can be `now` (the pass will serve it); rendering
        that as a clock time would print a moment already gone."""
        reading = read(facts(now_ms=1_000_000, next_sweep_ms=1_000_000))
        assert reading["kind"] == "due_now"
        assert "open_ms" not in reading

    def test_no_window_and_no_budget_names_the_budget(self):
        """The honest no-window branch. Mutation observed red: delete the
        `sweeps_remaining_today <= 0` branch in readNextWindow -- the spent
        day falls through to the nothing-to-schedule sentence."""
        reading = read(facts(next_sweep_ms=None, sweeps_remaining_today=0))
        assert reading["kind"] == "budget_spent"
        assert "budget" in reading["sentence"]

    def test_no_window_with_budget_left_says_nothing_is_planned(self):
        reading = read(facts(next_sweep_ms=None, sweeps_remaining_today=3))
        assert reading["kind"] == "nothing_to_schedule"
        assert "budget is spent" not in reading["sentence"]

    def test_an_unreadable_timetable_refuses_in_words(self):
        """Unreadable resolves to a refusal, never 0 and never a fake time.
        Mutation observed red: make the null branch return
        `{kind: "scheduled", open_ms: 0, now_ms: 0}`."""
        reading = read(None)
        assert reading["kind"] == "unknown"
        assert "could not be read" in reading["sentence"]
        assert "open_ms" not in reading

    def test_no_wordy_branch_smuggles_a_time_in(self):
        """A sentence branch must carry no clock: the whole contract is that
        a time appears only when the scheduler actually planned one."""
        wordy = [
            read(None),
            read(facts(next_sweep_ms=None, sweeps_remaining_today=0)),
            read(facts(next_sweep_ms=None, sweeps_remaining_today=3)),
        ]
        for reading in wordy:
            assert "open_ms" not in reading
            assert not re.search(r"\d{1,2}:\d{2}", reading["sentence"])


@requires_node
class TestStaleOddsIsMatchedAsAWholeCode:
    def test_the_bare_code_matches(self):
        assert is_stale("stale_odds") is True

    def test_the_kalshi_clock_does_not(self):
        """The trap this function exists to avoid: `stale_kalshi_quote` is
        the *Kalshi* staleness check, which no odds refresh can fix -- a
        refresh button offered for it would be a button that lies. Mutation
        observed red: replace the split-and-compare with
        `reason.includes("stale")`."""
        assert is_stale("stale_kalshi_quote") is False

    def test_a_composite_reason_matches_across_the_comma(self):
        """`suppressed_reason` is comma-joined (joint_bound.py:280); the code
        can sit anywhere in it, with or without a space."""
        assert is_stale("wide_market,stale_odds") is True
        assert is_stale("wide_market, stale_odds") is True

    def test_nothing_matches_nothing(self):
        assert is_stale(None) is False
        assert is_stale("") is False


class TestThePageWiresTheExit:
    """The pure function being right proves nothing if nothing renders it."""

    def _exit_block(self) -> str:
        source = EXIT.read_text(encoding="utf-8")
        assert "function StaleOddsExit" in source, (
            "the stale-count exit component left StaleOddsExit.tsx"
        )
        return source.split("function StaleOddsExit", 1)[1].split(
            "\nfunction ", 1
        )[0]

    def test_both_screens_render_the_one_exit(self):
        """Extracted 2026-08-25 so the parlay desk could reuse it rather than
        word the same fact a second way. Mutation observed red: drop either
        import."""
        for page in (SLATE_PAGE, PARLAY_CARDS):
            source = page.read_text(encoding="utf-8")
            assert 'from "@/components/StaleOddsExit"' in source, page.name
            assert "<StaleOddsExit" in source, page.name
        assert "function StaleOddsExit" not in SLATE_PAGE.read_text(
            encoding="utf-8"
        ), "a second copy of the exit is back on the slate page"

    def test_the_disclosure_gates_the_exit_on_the_whole_code(self):
        """The summary must decide via isStaleOddsReason, not a substring.
        Mutation observed red: delete the `<StaleOddsExit` render from
        RefusalSummary."""
        source = SLATE_PAGE.read_text(encoding="utf-8")
        summary = source.split("function RefusalSummary", 1)[1].split(
            "\nfunction ", 1
        )[0]
        assert "isStaleOddsReason" in summary
        assert "<StaleOddsExit" in summary

    def test_the_exit_reads_the_schedulers_own_planning(self):
        block = self._exit_block()
        assert "readNextWindow" in block, (
            "the next-window line no longer comes from the shared reading; a "
            "second derivation of the schedule will disagree with the loop"
        )

    def test_the_exit_reuses_the_existing_refresh_path(self):
        """One refresh path (the receipt-not-a-brake lesson: the server-side
        spend gate stays the only gate, this is only a caller). Mutation
        observed red: swap the button for a bare <button>."""
        assert "<RefreshOddsButton" in self._exit_block()

    def test_the_tap_names_its_credit_cost_before_the_spend(self):
        """The ScoutDesk precedent: the button copy states the spend. The
        exit passes the server's own team_credits, and the shared button
        renders `{credits} credit(s)` inside the control."""
        assert "credits={sport.team_credits}" in self._exit_block()
        button = BUTTON.read_text(encoding="utf-8")
        assert "{credits} credit" in button

    def test_the_exit_is_a_real_control_in_neutral_ink(self):
        """44px target (min-h-11), pill like TonightStrip, and neither the
        warning ink nor the money ink -- a refresh affordance is neither
        (ADR 0061 section 3)."""
        block = self._exit_block()
        assert "min-h-11" in block
        assert "rounded-full" in block
        assert "accent-2" not in block
        assert "bg-accent" not in block

    def test_the_teaching_sentence_goes_through_the_glossary(self):
        """New term, one canonical definition: <Term k="stale"> in the exit,
        entry in lib/glossary.ts (test_glossary_coverage.py pins the entry's
        reachability and size from the other side)."""
        assert '<Term k="stale">' in self._exit_block()

    def test_the_clock_renders_through_the_pinned_formatters(self):
        """formatClock/formatUntil carry DISPLAY_TIME_ZONE
        (test_display_timezone.py); a hand-rolled Date here would render the
        device's zone."""
        block = self._exit_block()
        assert "formatClock(" in block
        assert "formatUntil(" in block
        assert "toLocale" not in block


@requires_node
class TestAWantedBuyIsNotAPromisedBuy:
    """The 2026-08-25 incident, in the branch that told the lie.

    The recording loop wedged for 15.5 minutes (passes every ~18s up to
    16:49:33Z, then nothing until 17:05:07Z, confirmed off
    `recorder.last_write_ms` rather than the log). Throughout,
    `next_sweep_ms <= now_ms` held and `due_now` said the next pass would serve
    it "usually within a minute". It did not, and the parlay desk sat blank the
    whole time saying the slate was empty.
    """

    def test_a_silent_loop_is_read_before_a_due_buy(self):
        """The precedence IS the guard: both conditions were true together, and
        whichever is checked first is the sentence the reader gets. Mutation
        observed red: move the stall check below the `next_sweep_ms` branch and
        this comes back `due_now`."""
        reading = read(
            facts(
                now_ms=10_000_000,
                next_sweep_ms=10_000_000,
                last_look_ms=10_000_000 - 15 * 60_000,
            )
        )
        assert reading["kind"] == "loop_stalled"
        assert "15 minutes" in reading["sentence"]
        assert "within a minute" not in reading["sentence"]

    def test_a_stall_outranks_a_scheduled_window_too(self):
        """A future window is no more served than a due one while nothing is
        running, and printing its time would be the same promise in a clock."""
        reading = read(
            facts(
                now_ms=10_000_000,
                next_sweep_ms=13_600_000,
                last_look_ms=10_000_000 - 15 * 60_000,
            )
        )
        assert reading["kind"] == "loop_stalled"
        assert "open_ms" not in reading

    def test_a_loop_that_looked_moments_ago_is_not_stalled(self):
        """The live cadence is a pass every ~18s. A reading that called that a
        stall would put a fault banner on every healthy screen."""
        reading = read(
            facts(
                now_ms=10_000_000,
                next_sweep_ms=10_000_000,
                last_look_ms=10_000_000 - 20_000,
            )
        )
        assert reading["kind"] == "due_now"

    def test_a_never_looked_database_is_unknown_not_stalled(self):
        """`last_look_ms` is null on a fresh volume -- the loop has not had a
        chance to look, which is not the same claim as having stopped.
        Unreadable resolves to a refusal to claim, never to a fault
        (`tasks/lessons.md`). Mutation observed red: treat null as 0 and every
        fresh deploy reports a 56-year stall."""
        reading = read(
            facts(now_ms=10_000_000, next_sweep_ms=10_000_000, last_look_ms=None)
        )
        assert reading["kind"] == "due_now"

    def test_the_stall_sentence_carries_no_clock_time(self):
        """Same contract as every other wordy branch: a time appears only when
        the scheduler actually planned one and something is running to serve
        it. A duration in minutes is not a clock time."""
        reading = read(
            facts(
                now_ms=10_000_000,
                next_sweep_ms=10_000_000,
                last_look_ms=10_000_000 - 15 * 60_000,
            )
        )
        assert not re.search(r"\d{1,2}:\d{2}", reading["sentence"])


@requires_node
class TestTheParlayDeskSaysWhyItIsEmpty:
    """`not_built_reason` counts *fresh* games and is silent about the rest.

    Joe read "needs 2 fresh games and the slate has 0" as "there is nothing on
    tonight" while twenty fixtures sat upcoming. The card sentence is correct;
    the page around it was missing the half that makes it legible.
    """

    def _cards(self) -> str:
        return PARLAY_CARDS.read_text(encoding="utf-8")

    def _freshness_block(self) -> str:
        """Just the component, not the tail of the file behind it.

        The unbounded split reached `kickoff()` and its `toLocaleTimeString`,
        so the no-hand-rolled-clock assertion below passed on the wrong text.
        """
        source = self._cards()
        assert "function Freshness" in source
        return source.split("function Freshness", 1)[1].split(
            "\nfunction ", 1
        )[0]

    def test_the_card_no_longer_claims_the_evening(self):
        """"tonight" is a claim about the next several hours; the refusal is
        about this minute, and today it was a fifteen-minute one."""
        source = self._cards()
        assert "Not built right now:" in source
        assert "Not built tonight" not in source

    def test_the_page_reads_the_timetable_and_tolerates_its_absence(self):
        """A timetable that will not answer must degrade to the page as it
        rendered before, never take the ladder down with it. Mutation observed
        red: drop the `.catch` and a failing `/api/window` throws through the
        server component."""
        source = PARLAYS_PAGE.read_text(encoding="utf-8")
        assert "fetchWindow" in source
        assert "fetchRefreshable" in source
        assert source.count(".catch(() => null)") == 2

    def test_the_freshness_block_needs_a_card_to_have_actually_failed(self):
        """A full desk routinely carries a handful of stale sides -- six, with
        all three cards built, on the afternoon this was written. A banner that
        fires on a working screen is one the reader learns to skip, so the
        trigger is the conjunction. Mutation observed red: drop the `unbuilt`
        half of the condition."""
        block = self._freshness_block()
        assert "stale === 0 || unbuilt === 0" in block
        assert "return null" in block

    def test_the_block_states_the_two_facts_the_card_cannot(self):
        """Upcoming vs fresh is what separates "no games" from "no prices";
        the sweep age is what makes the refusal checkable."""
        block = self._freshness_block()
        assert "fixtures_upcoming" in block
        assert "fixtures_fresh" in block
        assert "last_sweep_ms" in block
        assert "max_odds_age_s" in block

    def test_the_block_survives_an_unreadable_timetable(self):
        """It explains an outage; going missing during one is the worst
        possible time to go missing. Mutation observed red: early-return on
        `actionable === null`."""
        block = self._freshness_block()
        assert "actionable === null" not in block.split("return null", 1)[0]

    def test_the_block_invents_no_number_of_its_own(self):
        """Every figure is a field of ActionableWindow put in a sentence, and
        the two durations render through the pinned formatters rather than a
        hand-rolled division."""
        block = self._freshness_block()
        assert "formatAge(" in block
        assert "formatDuration(" in block
        assert "toLocale" not in block


@requires_node
class TestTheColdScreenIsNarrowerThanUrgency:
    """`slateIsUnpricedByTheClock` gates the auto-refresh, and it must be much
    harder to satisfy than `refreshIsUrgent`.

    Urgency decides where a panel sits. This decides whether the page
    re-renders **under whoever is reading it**, so the bar is "the clock cost
    this screen its whole answer", not "something on it is stale".
    """

    def test_one_stale_row_on_a_working_slate_is_not_cold(self):
        """The failure this predicate exists to prevent. `refreshIsUrgent`
        says True here and is right to; re-rendering would throw a reader off
        a game they were reading. Mutation observed red: swap `every` for
        `some` in the refusal check."""
        rows = [FRESH_ROW, REFUSED_STALE]
        # `refreshIsUrgent` says True on this same slate and is right to --
        # `test_refresh_urgency.py` asserts that half. The two predicates
        # disagreeing here is the design, not an inconsistency.
        assert cold(rows) is False

    def test_a_wholly_refused_stale_screen_is_cold(self):
        """Joe's 09:58 state: rows on the record, every one refused, the clock
        named in the refusal."""
        assert cold([REFUSED_STALE, REFUSED_STALE]) is True

    def test_a_screen_refused_for_other_reasons_is_not_cold(self):
        """Nothing usable, but no sweep would change it -- so watching for one
        would be a promise nothing can keep. Mutation observed red: drop the
        `some(...)` clause and return True on any fully-refused screen."""
        assert cold([REFUSED_OTHER, REFUSED_OTHER]) is False

    def test_a_mixed_refusal_screen_is_cold_if_the_clock_is_in_it(self):
        """Nothing usable and fresh prices could change part of it. The reader
        has no answer either way, so a re-render costs them nothing."""
        assert cold([REFUSED_OTHER, REFUSED_STALE]) is True

    def test_the_kalshi_clock_alone_is_not_cold(self):
        """`stale_kalshi_quote` is the *Kalshi* clock, which no odds sweep can
        fix. Read as a whole code through `isStaleOddsReason`, never a
        substring. Mutation observed red: use `.includes("stale")`."""
        rows = [{"odds_age_now_ms": 60_000, "suppressed_reason": "stale_kalshi_quote"}]
        assert cold(rows) is False

    def test_a_composite_refusal_naming_the_clock_counts(self):
        """`suppressed_reason` is comma-joined, so the code can sit anywhere."""
        rows = [{"odds_age_now_ms": 60_000,
                 "suppressed_reason": "wide_market,stale_odds"}]
        assert cold(rows) is True

    def test_an_over_age_row_counts_even_unrefused_by_the_clock(self):
        """A row past the limit the engine refused for something else is still
        evidence the consensus aged out."""
        rows = [{"odds_age_now_ms": 1_200_000, "suppressed_reason": "wide_market"}]
        assert cold(rows) is True

    def test_an_empty_slate_is_not_cold(self):
        """The page's own words: nothing recorded is a real result and is not
        the same as every candidate being refused, so watching an empty screen
        waits for rows that may not exist tonight.

        **No mutation is claimed here, and that is the finding.** An explicit
        `rows.length === 0` guard was written for this and survived its own
        deletion -- `every` over an empty array is vacuously true and the
        `some` returns false regardless. It was removed as decoration. This
        case still asserts the behaviour, which is what it was for.
        """
        assert cold([]) is False
