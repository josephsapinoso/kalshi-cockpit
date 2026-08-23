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
BUTTON = REPO / "frontend" / "src" / "components" / "RefreshOddsButton.tsx"

NODE = shutil.which("node")

_DRIVER = """
import { readNextWindow, isStaleOddsReason } from "./nextOddsWindow.ts";
const args = JSON.parse(process.argv[2]);
const result =
  args.fn === "read"
    ? readNextWindow(args.facts)
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


def facts(now_ms=1_000_000, next_sweep_ms=None, sweeps_remaining_today=2):
    return {
        "now_ms": now_ms,
        "next_sweep_ms": next_sweep_ms,
        "sweeps_remaining_today": sweeps_remaining_today,
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
        source = SLATE_PAGE.read_text(encoding="utf-8")
        assert "function StaleOddsExit" in source, (
            "the stale-count exit component left the slate page"
        )
        return source.split("function StaleOddsExit", 1)[1].split(
            "\nfunction ", 1
        )[0]

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
