"""Opening the desk cold buys odds now, not in up to fifteen minutes.

THE DEFECT, AND IT WAS THREE FACTS AGREEING
-------------------------------------------
`decide_sweeps` reads `last_sweep_by_sport(conn, since_ms=budget.day_start_ms)`,
so **`last_sweeps` is scoped to the budget day**. At every 10:00Z roll every
sport goes back to having nothing pacing it, and `desk_wants` reaches its
bootstrap branch for all of them.

`run_quote_pass` passed `allow_bootstrap=False`, hardcoded. So a quote pass
dropped every sport.

`pass_kind` returns `"quote"` for any pass inside `last_full_ms + 900s`. An
early wake -- the thing `ArrivalWatch` exists to produce when someone opens the
desk -- lands there by construction.

Together: someone opens the desk after the day roll, the loop wakes within 5s,
runs a quote pass, and that pass cannot buy anything. They wait for the full
pass, up to 900s. Meanwhile `window_status` calls `desk_wants` with the default
`allow_bootstrap=True` and tells them a sweep is due **now**.

MEASURED, NOT REASONED
----------------------
Budget day 20260827 rolled at 10:00:00Z. Its first credit was spent at
**10:13:56Z** -- from `api_credits` on the live volume. Fourteen minutes.

THE FIX, AND WHY IT IS A ONE-SHOT
---------------------------------
`run_quote_pass` takes `allow_bootstrap` (still defaulting to `False`), and
`scripts/run_loop.py` raises it only for a pass that **follows an early wake**.

Not `is_attended`, and that distinction is the whole safety argument.
Attention is a *state*, true for the whole 300s TTL; a quote pass runs every
15s. Gating on the state would let a sport whose sweep keeps failing retry
every 15s until the day's credits were gone -- precisely the hazard the
hardcoded `False` was written against, and `test_desk_follows_attention.py`
pins that hazard on `desk_wants` itself. A wake is an *event*: at most one per
heartbeat, and it stops mattering the moment one sweep succeeds, because
`last_sweeps` then paces the sport.

WHAT THESE TESTS DO NOT ESTABLISH
---------------------------------
- **That the wake itself fires.** `test_scheduler.py` owns `sleep_until` and
  `ArrivalWatch`; these take an early wake as given and test what the pass does
  with it.
- **That the screen and the pass now agree in every state.** They agree for a
  reader -- someone reading the screen has heartbeated, so a wake is coming --
  and `window_status` still cannot see `Tempo.last_full_ms`, which lives in the
  other process. The residual is asserted below rather than claimed closed.
- **Anything about credits actually being spent.** `decide_sweeps` still
  answers to `budget.refusal_reason` and the attention slice; nothing here
  widens a cap.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from backend.odds.timing import desk_wants
from backend.runner import run_quote_pass
from backend.scheduler import LoopState, one_shot_wake

NOW = 1_787_800_000_000
HOUR = 3_600_000
REFRESH_MS = 600_000
SPORT = "baseball_mlb"
SOON = {SPORT: (NOW + 6 * HOUR,)}


def _source(name: str) -> str:
    root = Path(__file__).resolve().parents[1]
    where = root / "scripts" / name if name.endswith("run_loop.py") else root / name
    return where.read_text(encoding="utf-8")


class TestTheQuotePassCanBeToldToBootstrap:
    def test_it_still_refuses_by_default(self):
        """The safety that was hardcoded is now a default, and a default is
        only as good as the fact that nobody has to remember it.

        Mutation observed red: flip the default to `True`. Every caller that
        does not pass the argument -- tests, `scripts/`, the demo -- would then
        bootstrap on the 15s cadence, which is the failure this whole guard
        exists for.
        """
        assert (
            inspect.signature(run_quote_pass).parameters["allow_bootstrap"]
            .default is False
        )

    def test_the_flag_is_not_swallowed_on_the_way_to_the_planner(self):
        """`run_quote_pass` used to hardcode `False` at the `fetch_and_store_odds`
        call. A parameter accepted and then ignored is the shape of a feature
        that ships as source and never runs.

        Mutation observed red: pin the call back to `allow_bootstrap=False`.
        """
        body = inspect.getsource(run_quote_pass)
        call = body.index("fetch_and_store_odds(")
        assert "allow_bootstrap=allow_bootstrap," in body[call:call + 600]
        assert "allow_bootstrap=False," not in body[call:call + 600]


class TestTheDayRollIsWhatMakesThisReachable:
    """`desk_wants` is unchanged; these say why the flag matters at all."""

    def test_a_sport_with_no_sweep_this_budget_day_is_dropped_without_it(self):
        assert desk_wants(
            SOON, now_ms=NOW, attended=True, last_sweeps={},
            refresh_interval_ms=REFRESH_MS, allow_bootstrap=False,
        ) == {}

    def test_and_is_bought_now_with_it(self):
        assert desk_wants(
            SOON, now_ms=NOW, attended=True, last_sweeps={},
            refresh_interval_ms=REFRESH_MS, allow_bootstrap=True,
        ) == {SPORT: NOW}

    def test_one_served_sweep_ends_the_bootstrap_for_the_rest_of_the_day(self):
        """The bound on the whole mechanism, and the reason a one-shot per
        heartbeat cannot run away: once a sweep lands, the sport is paced by
        `refresh_interval_ms` and the flag stops changing any answer."""
        paced = {SPORT: NOW - 60_000}
        assert desk_wants(
            SOON, now_ms=NOW, attended=True, last_sweeps=paced,
            refresh_interval_ms=REFRESH_MS, allow_bootstrap=True,
        ) == desk_wants(
            SOON, now_ms=NOW, attended=True, last_sweeps=paced,
            refresh_interval_ms=REFRESH_MS, allow_bootstrap=False,
        )


class TestTheSecondBootstrapPathIsGatedByTheSameFlag:
    """`decide_sweeps` has TWO bootstrap paths and only one of them goes
    through `desk_wants`.

    The other fires for a sport with **no stored sportsbook fixtures at all**
    and stamps `trigger=BOOTSTRAP`. Raising `allow_bootstrap` opens both, so
    both have to be bounded -- and this one is *not* covered by the attention
    slice, because `attention_credits_spent_today` counts only `ATTENTION`.
    An earlier draft of `run_quote_pass`'s docstring claimed the slice bounded
    the whole mechanism; it does not, and the claim was corrected rather than
    the path left unexamined.

    What bounds it: the flag itself, the one-shot, and the fact that a
    *successful* sweep enters `last_sweeps` and the path's own
    `sport not in last_sweeps` clause then closes it for the budget day.
    """

    def test_it_is_gated_on_the_flag(self):
        """Mutation observed red: drop the `if allow_bootstrap else []`.

        Without the gate, raising the flag for a wake would be beside the
        point -- this path would fire on every quote pass regardless.
        """
        source = _source("backend/odds/timing.py")
        assert ") if allow_bootstrap else []" in source

    def test_a_served_sweep_counts_however_it_was_triggered(self):
        """The bound that ends a bootstrap after one success. `_SERVED_SWEEP`
        excludes exactly one trigger -- `manual` -- so a `bootstrap`- or
        `attention`-stamped sweep enters `last_sweeps` and paces its sport.

        Mutation observed red: exclude `bootstrap` from `_SERVED_SWEEP` too.
        A bootstrap that did not count as served would never start pacing, so
        the sport would be re-bought on every wake for the whole day.
        """
        from backend.odds.timing import ATTENTION, BOOTSTRAP, MANUAL, _SERVED_SWEEP

        assert f"!= '{MANUAL}'" in _SERVED_SWEEP
        for trigger in (ATTENTION, BOOTSTRAP):
            assert f"!= '{trigger}'" not in _SERVED_SWEEP

    def test_a_failed_sweep_does_not_count_as_served(self):
        """The reason the one-shot is needed at all: an erroring sweep never
        enters `last_sweeps`, so nothing paces the retry but the flag."""
        from backend.odds.timing import _SERVED_SWEEP

        assert "http_status" in _SERVED_SWEEP and "400" in _SERVED_SWEEP


class TestTheLoopRaisesItOnlyForAWake:
    """**These call the real `one_shot_wake`, and the first version did not.**

    It was a closure inside `run_loop.main`, so the tests re-implemented its
    four lines against a real `LoopState`. They passed, and then stayed GREEN
    under two mutations of the actual predicate -- removing the consume, and
    differencing by one instead of reading the counter. A faithful
    re-implementation is a description, not a constraint; it is satisfied by
    the code as written and by any other code too. The function was moved
    beside `LoopState` so this class could reach it.
    """

    def test_a_pass_with_no_wake_behind_it_does_not_bootstrap(self):
        ask = one_shot_wake(LoopState())
        assert ask() is False
        assert ask() is False

    def test_the_pass_after_a_wake_does(self):
        state = LoopState()
        ask = one_shot_wake(state)
        state.woken_early += 1
        assert ask() is True

    def test_it_is_consumed_so_one_wake_cannot_buy_two_passes(self):
        """Mutation observed red: `return state.woken_early > 0`.

        The property that separates this from `is_attended`. Without it, a desk
        left open would bootstrap on every 15s quote pass for the whole 300s
        TTL -- and a failing sport never advances `last_sweeps`, so it would
        keep doing so until the credits were gone.
        """
        state = LoopState()
        ask = one_shot_wake(state)
        state.woken_early += 1
        assert ask() is True
        assert ask() is False, "one wake authorised more than one bootstrap"

    def test_each_further_wake_authorises_exactly_one_more(self):
        state = LoopState()
        ask = one_shot_wake(state)
        authorised = 0
        for _ in range(5):
            state.woken_early += 1
            authorised += sum(1 for _ in range(4) if ask())
        assert authorised == 5

    def test_a_burst_of_wakes_during_one_pass_still_authorises_one(self):
        """Mutation observed red: `seen[0] += 1` instead of reading the counter.

        `woken_early` can move more than once between passes -- the loop polls
        every 5s and a page heartbeats every 60s, so a long sleep can end early,
        run a pass, and be woken again. Differencing by one leaves a backlog of
        wakes, each authorising a further bootstrap after the person has gone.
        """
        state = LoopState()
        ask = one_shot_wake(state)
        state.woken_early += 3
        assert ask() is True
        assert ask() is False

    def test_it_starts_from_the_state_it_was_given_not_from_zero(self):
        """A loop restarting its predicate mid-run must not inherit a wake that
        was already served. `seen` is seeded from the counter, not from 0."""
        state = LoopState()
        state.woken_early = 7
        assert one_shot_wake(state)() is False

    def test_the_loop_actually_asks_it(self):
        """Mutation observed red: pass `allow_bootstrap=False` at the call site.

        The tests above are about a predicate; this is the wire. A correct
        predicate nobody consults is the "built but never called" failure this
        repo has four modules' worth of.
        """
        source = _source("run_loop.py")
        call = source.index("run_quote_pass(")
        assert "allow_bootstrap=follows_early_wake()," in source[call:call + 1600]

    def test_the_loop_does_not_reach_for_attention_instead(self):
        """Mutation observed red: swap in `attention.is_attended(...)`.

        The tempting one-liner, and it reintroduces the hazard whole: attention
        is true for 300s and a quote pass runs every 15s.
        """
        source = _source("run_loop.py")
        call = source.index("run_quote_pass(")
        assert "is_attended" not in source[call:call + 1600]


class TestWhatIsStillNotGuaranteed:
    """Stated as a test rather than as prose, so it cannot quietly stop being
    true. `window_status` calls `desk_wants` with the default
    `allow_bootstrap=True` while the quote pass may pass `False`.

    That is deliberate and it is not closed by this change. The screen cannot
    see `Tempo.last_full_ms` -- it lives in the loop process -- so it cannot
    know whether the next pass is a full one. What the fix buys is that for
    *a reader* the promise comes true in seconds rather than in up to 900:
    someone reading the screen has heartbeated, so a wake is coming, so a
    bootstrap is coming.
    """

    def test_the_screen_still_asks_the_optimistic_question(self):
        source = _source("backend/odds/timing.py")
        start = source.index("def window_status(")
        block = source[start:start + 12_000]
        call = block.index("wants = desk_wants(")
        assert "allow_bootstrap" not in block[call:call + 500], (
            "window_status now passes allow_bootstrap explicitly -- good, but "
            "this test and the docstring above it describe the old state and "
            "must be rewritten rather than deleted"
        )
