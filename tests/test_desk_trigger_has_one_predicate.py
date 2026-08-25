"""The desk trigger is one predicate with several callers, not several copies.

`odds/timing.py` states this rule in its own voice, at `firing_for_slot`:

    **One predicate, two callers, on purpose.** [...] Those two answers must be
    the same answer -- the window panel tells a human when to look, and a panel
    that computed "next sweep" by its own reasoning would eventually disagree
    with the loop, with no way to tell from the page which of them was wrong.

`covers_commence` exists for the same reason. **The desk trigger was the one
place the rule was never applied.** Before 2026-08-25 it had four sites:

1. `decide_sweeps` -- an inline `desk_window is not None and
   desk_window_contains(...)`,
2. `window_status` -- a second, differently-spelled copy with its own tuple
   unpack and its own equal-hours re-check,
3. `first_window_open_of_day` -- a third spelling again, and
4. `scripts/run_loop.py`, which **did not pass `desk_window` at all**.

(4) is the one that had already gone wrong. `window_status` predicts desk buys
in `next_call_ms` and `first_window_open_ms`; called without the argument it
predicts none, so the loop was logging a cadence it did not itself follow --
exactly the "two paths, and the screen is the one that gets believed" failure
the module's own docstring describes.

Extracted now rather than later because the desk is about to stop being a clock
and start following attention. Changing the meaning of a rule that exists in
four hand-synced copies is how three of them get updated.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Nothing about whether the desk window's hours are right.** That is
  configuration (`ODDS_DESK_WINDOW_UTC`) and a cost decision, not a predicate.
- **Nothing about `decide_sweeps` actually firing.** `test_sweep_timing.py`
  owns the desk trigger's behaviour; this file owns the claim that every site
  asks the same function.
- **Nothing about `run_loop` at runtime.** The assertion is over source text --
  there is no fixture that boots the loop -- so it proves the argument is passed
  and not that the resulting readout is correct.
- **Nothing about future callers.** A fifth site could still inline the logic.
  The grep below refuses the two spellings that existed; it cannot refuse one
  nobody has written yet.
"""

from __future__ import annotations

from pathlib import Path

from backend.odds.timing import (
    desk_is_open,
    desk_next_open_ms,
    next_desk_open_ms,
)

ROOT = Path(__file__).resolve().parents[1]
TIMING = ROOT / "backend" / "odds" / "timing.py"
RUN_LOOP = ROOT / "scripts" / "run_loop.py"

HOUR = 3_600_000
#: 2026-08-25T18:00:00Z — inside the deployed 16-04 window.
INSIDE = 1_787_680_800_000
#: 2026-08-25T12:00:00Z — outside it.
OUTSIDE = INSIDE - 6 * HOUR

WINDOW = (16, 4)


class TestTheOpenPredicate:
    def test_it_answers_inside_the_window(self):
        assert desk_is_open(WINDOW, INSIDE) is True

    def test_it_answers_outside_the_window(self):
        assert desk_is_open(WINDOW, OUTSIDE) is False

    def test_no_configured_window_is_shut_rather_than_an_error(self):
        """`None` means no desk trigger is configured. Not the same fact as
        "the desk is shut", and the same answer here — but a caller must not
        have to know that, which is why the `None` handling lives in the
        predicate rather than at four call sites."""
        assert desk_is_open(None, INSIDE) is False

    def test_equal_hours_are_refused_rather_than_read_as_all_day(self):
        """`desk_window_contains` owns this rule and states the cost: an all-day
        desk at four sports is ~1,150 credits/day against a 700 cap. The point
        here is that `desk_is_open` inherits it instead of re-deriving it."""
        assert desk_is_open((16, 16), INSIDE) is False


class TestTheNextOpenPredicate:
    def test_it_returns_now_when_the_desk_is_already_open(self):
        assert desk_next_open_ms(WINDOW, INSIDE) == INSIDE

    def test_it_agrees_with_the_function_it_wraps(self):
        assert desk_next_open_ms(WINDOW, OUTSIDE) == next_desk_open_ms(
            OUTSIDE, start_hour=WINDOW[0], end_hour=WINDOW[1]
        )

    def test_an_unconfigured_desk_returns_none_not_a_timestamp(self):
        """`None`, never `from_ms` and never a far-future stamp.

        A caller merging this into a "next call" answer has to be able to leave
        it out of a `min()`. A sentinel timestamp would silently win or silently
        lose depending on which one was chosen, and both are wrong in a way
        nothing would report. Unreadable resolves to `None`.
        """
        assert desk_next_open_ms(None, OUTSIDE) is None
        assert desk_next_open_ms((16, 16), OUTSIDE) is None


class TestEveryCallerAsksTheSameFunction:
    """Source-text guards. The behaviour is `test_sweep_timing.py`'s."""

    def test_no_inline_desk_window_contains_call_survives(self):
        """Mutation observed red: restore any of the three inline copies.

        `desk_window_contains` still has exactly one caller — `desk_is_open` —
        and `next_desk_open_ms` exactly one — `desk_next_open_ms`. A second
        caller of either is a fourth spelling of the rule.
        """
        source = TIMING.read_text(encoding="utf-8")
        # `desk_window_contains`: its own `def`, the call inside
        # `next_desk_open_ms` (which is the open-now shortcut, not a copy of the
        # trigger), and the call inside `desk_is_open`. Nothing else.
        assert source.count("desk_window_contains(") == 3, (
            "a fourth reference means the trigger has been inlined again"
        )
        # `next_desk_open_ms`: its own `def` and the call inside
        # `desk_next_open_ms`.
        assert source.count("next_desk_open_ms(") == 2, (
            "a third reference means the reopen time has been inlined again"
        )

    def test_the_loop_passes_the_desk_window_to_window_status(self):
        """The defect (4), pinned.

        Mutation observed red: delete the `desk_window=` argument — the loop
        goes back to predicting a cadence it does not follow, and nothing else
        in the suite notices.
        """
        source = RUN_LOOP.read_text(encoding="utf-8")
        start = source.index("return window_status(")
        # To the call's own closing paren, at its own indentation -- not to the
        # first `)`, which belongs to `db.now_ms()` two lines in. A slice that
        # stops early would pass this assertion by never containing the
        # argument, which is the wrong kind of failure for a guard.
        call = source[start : source.index("\n            )", start)]
        assert "desk_window=odds_config.desk_window_utc" in call

    def test_the_loop_uses_the_same_config_value_the_runner_does(self):
        """Not a second setting, and not a literal. `decide_sweeps` is handed
        `config.desk_window_utc` in `runner.py`; a loop reading anything else
        would be the same class of divergence one layer up."""
        runner = (ROOT / "backend" / "runner.py").read_text(encoding="utf-8")
        assert "desk_window=config.desk_window_utc" in runner
