"""The loop, weighted toward how it fails.

A background loop that swallows exceptions is the worst shape this system can
take: the cockpit keeps serving, the health check passes, and the Board renders
yesterday's prices, which looks exactly like a quiet market. `entrypoint.sh`
already refuses to let a dead backend masquerade as a live one; these tests
hold the loop to the same standard.
"""

from __future__ import annotations

import random

import pytest

from backend.config import StalenessConfig
from backend.scheduler import (
    DEFAULT_FAST_INTERVAL_S,
    JITTER,
    MAX_CONSECUTIVE_FAILURES,
    QUOTE_PASS_DURATION_BUDGET_S,
    LoopFailed,
    LoopState,
    Tempo,
    next_delay,
    quote_refresh_survives_interval,
    run_forever,
)


class Recorder:
    """A `do_pass` that can be told when to fail."""

    def __init__(self, fail_on=(), result=None):
        self.calls = 0
        self.fail_on = set(fail_on)
        self.result = result

    async def __call__(self):
        self.calls += 1
        if self.calls in self.fail_on or self.fail_on == {"always"}:
            raise RuntimeError(f"pass {self.calls} exploded")
        return self.result


class Counts:
    def __init__(self, **kw):
        self._d = kw

    def as_dict(self):
        return self._d


async def _noop_sleep(_seconds):
    return None


class TestItKeepsRunning:
    async def test_it_runs_until_max_passes(self):
        do_pass = Recorder(result=Counts(recommendations=4))
        state = await run_forever(
            do_pass, interval_s=1, max_passes=3, sleep=_noop_sleep
        )
        assert do_pass.calls == 3
        assert state.passes_succeeded == 3
        assert state.last_counts == {"recommendations": 4}

    async def test_a_transient_failure_does_not_stop_the_loop(self):
        """An odds aggregator returning 502 is normal, not a reason to restart."""
        do_pass = Recorder(fail_on={2}, result=Counts(recommendations=1))
        state = await run_forever(
            do_pass, interval_s=1, max_passes=4, sleep=_noop_sleep
        )
        assert do_pass.calls == 4
        assert state.passes_succeeded == 3
        assert state.consecutive_failures == 0, "a later success must reset the count"

    async def test_success_after_failure_clears_the_error(self):
        do_pass = Recorder(fail_on={1}, result=Counts(recommendations=2))
        state = await run_forever(
            do_pass, interval_s=1, max_passes=2, sleep=_noop_sleep
        )
        assert state.last_error is None
        assert state.last_success_ms is not None


class TestItDiesLoudly:
    """Repeated failure must end the process, not be sat in quietly."""

    async def test_it_raises_after_too_many_consecutive_failures(self):
        do_pass = Recorder(fail_on={"always"})
        with pytest.raises(LoopFailed) as excinfo:
            await run_forever(
                do_pass, interval_s=1, max_passes=50, sleep=_noop_sleep
            )

        assert do_pass.calls == MAX_CONSECUTIVE_FAILURES
        # The message has to name the cause. A loop that dies saying only
        # "failed" is a restart with no diagnosis.
        assert "consecutive failed passes" in str(excinfo.value)
        assert "pass 5 exploded" in str(excinfo.value)

    async def test_the_original_exception_is_chained(self):
        """`raise ... from exc` keeps the traceback that actually explains it."""
        do_pass = Recorder(fail_on={"always"})
        with pytest.raises(LoopFailed) as excinfo:
            await run_forever(
                do_pass, interval_s=1, max_passes=50, sleep=_noop_sleep
            )
        assert isinstance(excinfo.value.__cause__, RuntimeError)

    async def test_intermittent_failure_never_reaches_the_limit(self):
        """Failing every other pass is degraded, not dead.

        This is the case a naive `total_failures >= N` counter would kill, and
        it would kill it during an ordinary flaky afternoon.
        """
        do_pass = Recorder(fail_on={1, 3, 5, 7, 9}, result=Counts(recommendations=1))
        state = await run_forever(
            do_pass, interval_s=1, max_passes=10, sleep=_noop_sleep
        )
        assert do_pass.calls == 10
        assert state.passes_succeeded == 5


class TestFreshnessIsSeparateFromLiveness:
    async def test_last_success_is_not_updated_by_a_failed_pass(self):
        """"The process is alive" and "the data is fresh" are different claims.

        `last_success_ms` is the only one that supports the second, so a failing
        pass must leave it alone -- otherwise a loop that has been erroring for
        an hour still reports fresh data.
        """
        do_pass = Recorder(fail_on={2, 3}, result=Counts(recommendations=1))
        state = LoopState()
        await run_forever(
            do_pass, interval_s=1, max_passes=3, state=state, sleep=_noop_sleep,
            now_ms=lambda: 1_000,
        )
        assert state.last_success_ms == 1_000
        assert state.passes_attempted == 3
        assert state.passes_succeeded == 1
        assert state.consecutive_failures == 2
        assert state.last_error is not None


class TestJitter:
    def test_the_delay_stays_within_the_jitter_band(self):
        rng = random.Random(4)
        for _ in range(200):
            d = next_delay(900.0, rng)
            assert 900 * (1 - JITTER) <= d <= 900 * (1 + JITTER)

    def test_a_short_interval_never_goes_negative_or_zero(self):
        rng = random.Random(4)
        assert all(next_delay(0.1, rng) >= 1.0 for _ in range(50))

    def test_delays_actually_differ(self):
        """Without jitter a restarted fleet sweeps in lockstep and the odds
        budget is small enough for that to lose a day's credits at once."""
        rng = random.Random(4)
        assert len({next_delay(900.0, rng) for _ in range(20)}) > 15


class TestTheComposedWindow:
    """The product of the limits, which is the number nobody was computing.

    `MAX_KALSHI_QUOTE_AGE_S = 30`, `MAX_ODDS_AGE_S = 900`, loop interval 900s.
    Each is defensible on its own and no module holds more than one of them, so
    the thing they multiply into -- thirty seconds of actionability after each
    pass -- was written down nowhere and contradicted by every document in the
    repo. These tests are where the composition now lives.
    """

    def test_the_shipped_defaults_keep_a_row_bettable(self):
        """The claim the fast cadence exists to make, asserted on real values.

        Not on invented ones. If someone raises `DEFAULT_FAST_INTERVAL_S` or
        lowers `MAX_KALSHI_QUOTE_AGE_S` past the point where polling stops
        helping, this fails -- which is the only way that change announces
        itself, because a row expiring between passes looks like a quiet board.
        """
        assert quote_refresh_survives_interval(
            DEFAULT_FAST_INTERVAL_S,
            jitter=JITTER,
            max_kalshi_quote_age_s=StalenessConfig().max_kalshi_quote_age_s,
        )

    def test_the_single_cadence_this_replaces_does_not(self):
        """The bug, stated as a test rather than as prose.

        900s against a 30s limit is the state the tool shipped in: two sweeps a
        day, each row bettable for half a minute, ~1 minute of actionability in
        24 hours.
        """
        assert not quote_refresh_survives_interval(
            900.0, jitter=JITTER, max_kalshi_quote_age_s=30
        )

    def test_the_pass_itself_counts_against_the_limit(self):
        """Sleep is only half the gap between two confirmations.

        An interval that fits with an instantaneous pass and not with a real one
        is an interval that does not fit. Written as a pair so a version that
        ignores `pass_duration_s` cannot pass both.
        """
        assert quote_refresh_survives_interval(
            25.0, jitter=0.0, max_kalshi_quote_age_s=30, pass_duration_s=0.0
        )
        assert not quote_refresh_survives_interval(
            25.0, jitter=0.0, max_kalshi_quote_age_s=30, pass_duration_s=8.0
        )

    def test_a_gap_exactly_equal_to_the_limit_is_refused(self):
        """At equality the row is unbettable at the instant it is re-confirmed."""
        assert not quote_refresh_survives_interval(
            30.0, jitter=0.0, max_kalshi_quote_age_s=30, pass_duration_s=0.0
        )

    def test_the_budget_leaves_real_headroom_at_the_default(self):
        """The allowance is stated, so it can be argued with rather than assumed."""
        worst = DEFAULT_FAST_INTERVAL_S * (1 + JITTER) + QUOTE_PASS_DURATION_BUDGET_S
        assert worst < StalenessConfig().max_kalshi_quote_age_s
        # Not merely inside it -- inside it with room for a pass that runs long.
        assert worst <= StalenessConfig().max_kalshi_quote_age_s - 4


class TestTempo:
    """Which cadence, and which kind of pass."""

    def test_the_first_pass_is_always_full(self):
        """A fresh container has no odds stored, so a quote pass prices nothing.

        Starting on the fast cadence would mean the window could never open in
        the first place -- the fast pass has nothing to refresh and the sweep
        that would give it something never fires.
        """
        tempo = Tempo(slow_interval_s=900.0)
        assert tempo.pass_kind(1_000) == "full"

    def test_quote_passes_fill_the_gap_between_full_ones(self):
        tempo = Tempo(slow_interval_s=900.0, fast_interval_s=15.0)
        tempo.completed_full_pass(1_000_000)

        assert tempo.pass_kind(1_000_000 + 15_000) == "quote"
        assert tempo.pass_kind(1_000_000 + 899_000) == "quote"
        assert tempo.pass_kind(1_000_000 + 900_000) == "full"

    def test_a_failed_full_pass_is_not_recorded_as_done(self):
        """Otherwise one bad sweep costs fifteen minutes of scoring and alerts.

        `completed_full_pass` is called by the caller *after* the awaits, so a
        pass that raises never reaches it and the next pass is full again.
        """
        tempo = Tempo(slow_interval_s=900.0)
        assert tempo.pass_kind(1_000) == "full"
        # ...pass raises, so nothing is recorded...
        assert tempo.pass_kind(1_060) == "full"

    def test_the_cadence_follows_the_window(self):
        tempo = Tempo(slow_interval_s=900.0, fast_interval_s=15.0)
        assert tempo.interval_s() == 900.0
        tempo.window_open = True
        assert tempo.interval_s() == 15.0

    def test_an_overrunning_quote_pass_is_reported_not_absorbed(self):
        """A quote pass slow enough to break the composition has to say so.

        The symptom -- rows expiring between passes despite the fast cadence --
        is indistinguishable from a board with nothing on it, so it cannot be
        left to be noticed.
        """
        tempo = Tempo(slow_interval_s=900.0, fast_interval_s=15.0)
        assert tempo.observe_pass_duration(2.0, max_kalshi_quote_age_s=30, kind="quote")
        assert tempo.quote_passes_overrun == 0

        assert not tempo.observe_pass_duration(
            20.0, max_kalshi_quote_age_s=30, kind="quote"
        )
        assert tempo.quote_passes_overrun == 1
        assert tempo.as_dict()["passes_over_quote_budget"] == 1

    def test_a_slow_full_pass_is_not_counted_against_the_quote_budget(self):
        """The counter has to count the population it is named for.

        Measured on the live instance's very first pass: a full pass discovering
        167 events, quoting 1,426 markets and joining 228 rows for CLV took
        14.9s -- entirely normal, on a 900s cadence -- and raised
        `passes_over_quote_budget` while the window was closed and no quote pass
        was running at all. Full passes happen forever, so the counter would
        have been ~96 routine entries a day, and the one condition it exists to
        surface could never have been seen in it.
        """
        tempo = Tempo(slow_interval_s=900.0, fast_interval_s=15.0)

        assert not tempo.observe_pass_duration(
            14.9, max_kalshi_quote_age_s=30, kind="full"
        )
        assert tempo.quote_passes_overrun == 0, (
            "a full pass raised the quote-cadence alarm. That counter is the "
            "only signal that the fast cadence has stopped working, and a "
            "population that trips it every 900s makes it unreadable."
        )
        assert tempo.as_dict()["passes_over_quote_budget"] == 0

    def test_a_slow_full_pass_counts_only_while_the_window_is_open(self):
        """Two questions, so two counters -- and the closed-window case is not
        a finding at all.

        With the window shut the fast cadence is not running: the sleep after
        this pass is 900s, so arithmetic about a 15s interval describes a
        cadence that does not exist. Open, it is a real but structural fact --
        one confirmation gap per window spans the full pass.
        """
        closed = Tempo(slow_interval_s=900.0, fast_interval_s=15.0)
        closed.observe_pass_duration(14.9, max_kalshi_quote_age_s=30, kind="full")
        assert closed.full_passes_overrun_in_window == 0

        openw = Tempo(slow_interval_s=900.0, fast_interval_s=15.0, window_open=True)
        openw.observe_pass_duration(14.9, max_kalshi_quote_age_s=30, kind="full")
        assert openw.full_passes_overrun_in_window == 1
        assert openw.as_dict()["full_passes_over_limit_in_window"] == 1
        assert openw.as_dict()["passes_over_quote_budget"] == 0

    def test_a_pass_inside_the_budget_counts_nothing_either_way(self):
        """A guard that fires on everything and one that fires on nothing look
        the same from the counter. Pin the negative case for both kinds."""
        tempo = Tempo(slow_interval_s=900.0, fast_interval_s=15.0, window_open=True)
        for kind in ("quote", "full"):
            assert tempo.observe_pass_duration(
                2.0, max_kalshi_quote_age_s=30, kind=kind
            )
        assert tempo.quote_passes_overrun == 0
        assert tempo.full_passes_overrun_in_window == 0


class TestTheSleepIsBoundedByTheNextWindow:
    """A window opening inside a 900s sleep used to be invisible until it ended.

    Not a reordering bug. `pass_kind` picks the cadence at the top of a pass,
    and with the window closed the loop then sleeps `slow_interval_s`. A pass
    landing at 15:25:50Z against a 15:26Z window slept to 15:40:50Z and lost
    nearly the whole thing -- observed live 20:39Z 2026-08-19, when a deploy
    restarted the box mid-window and only full passes ran until the next one
    latched.

    `next_wake_ms` is `ActionableWindow.next_call_ms`: when the next `/odds`
    call is wanted, from the planner rather than a second schedule.
    """

    NOW = 1_787_000_000_000

    def _tempo(self, **kw):
        return Tempo(
            slow_interval_s=900.0, fast_interval_s=15.0,
            clock=lambda: self.NOW, **kw,
        )

    def test_a_window_inside_the_sleep_shortens_it(self):
        """The whole point: 660s away, so do not sleep 900s past it."""
        tempo = self._tempo(next_wake_ms=self.NOW + 660_000)
        assert tempo.interval_s() == pytest.approx(660.0 / 1.15)

    def test_the_bound_survives_the_jitter_run_forever_adds(self):
        """`next_delay` multiplies by up to `1 + JITTER`.

        An unadjusted 900s bound would stretch to 1035s and overshoot the open
        by 135s, which is most of what this fix exists to prevent. The worst
        case must land on the open, not past it.
        """
        until_s = 600.0
        tempo = self._tempo(next_wake_ms=self.NOW + int(until_s * 1000))
        worst_case = tempo.interval_s() * (1.0 + JITTER)
        assert worst_case <= until_s + 1e-6, (
            f"worst-case sleep {worst_case:.1f}s overshoots the {until_s:.0f}s "
            f"until the window opens"
        )

    def test_a_window_further_out_than_the_slow_interval_changes_nothing(self):
        """A window six hours away must not make the loop poll faster."""
        tempo = self._tempo(next_wake_ms=self.NOW + 6 * 3_600_000)
        assert tempo.interval_s() == 900.0

    def test_no_planned_sweep_means_no_bound(self):
        """`next_slot` is None -- usually the budget is spent. Nothing is
        coming, so there is nothing to wake early for."""
        assert self._tempo(next_wake_ms=None).interval_s() == 900.0

    def test_an_already_due_wake_does_not_shorten_the_sleep(self):
        """The guard that matters, and it is a spin-prevention guard.

        `window_status` sets `next_call_ms = now_ms` whenever a slot is firing
        right now. If the pass that just ran served it the window is open and
        the open-window branch applies. If it was *refused* -- budget spent --
        the refusal repeats, and shortening here would run this loop at 15s
        against Kalshi with the window shut: the 4,300 polls a day `Tempo`
        exists to prevent.
        """
        assert self._tempo(next_wake_ms=self.NOW).interval_s() == 900.0
        assert self._tempo(next_wake_ms=self.NOW - 60_000).interval_s() == 900.0

    def test_the_bound_never_goes_below_the_fast_interval(self):
        """A bound a fraction of a second out arrives one fast interval late
        rather than spinning."""
        tempo = self._tempo(next_wake_ms=self.NOW + 200)
        assert tempo.interval_s() == 15.0

    def test_an_open_window_still_wins(self):
        """The bound is for the closed case only; it must not slow the fast
        cadence down when a window is actually open."""
        tempo = self._tempo(window_open=True, next_wake_ms=self.NOW + 600_000)
        assert tempo.interval_s() == 15.0

    def test_it_converges_on_the_window_rather_than_creeping_up_on_it(self):
        """Waking early is only free if it does not cost many extra passes.

        Each sleep consumes ~87% of the gap, so the remainder collapses fast.
        Pinned because the alternative -- a bound that shrinks slowly -- would
        put dozens of extra Kalshi polls in front of every window.
        """
        opens_at = self.NOW + 900_000
        now = self.NOW
        passes = 0
        while now < opens_at and passes < 20:
            tempo = Tempo(
                slow_interval_s=900.0, fast_interval_s=15.0,
                next_wake_ms=opens_at, clock=lambda now=now: now,
            )
            now += int(tempo.interval_s() * 1000)
            passes += 1
        assert 2 <= passes <= 4, (
            f"took {passes} passes to reach a window 900s out. Below 2 means "
            f"the loop never woke early at all and the bound is not applied; "
            f"above 4 means each one is an extra Kalshi poll with the window "
            f"shut"
        )

    def test_the_wake_time_is_published(self):
        """An early wake has to be legible in the log, or it reads as the loop
        firing at random with the window shut."""
        tempo = self._tempo(next_wake_ms=self.NOW + 60_000)
        assert tempo.as_dict()["next_wake_ms"] == self.NOW + 60_000

    def test_the_loop_sets_it_from_the_planners_own_answer(self):
        """Not a second schedule computed here.

        `next_call_ms` goes through `firing_for_slot`, the same predicate the
        loop fires on. A control and a screen that compute the same thing two
        ways eventually disagree.
        """
        from pathlib import Path

        source = Path("scripts/run_loop.py").read_text(encoding="utf-8")
        assert "tempo.next_wake_ms = window.next_call_ms" in source, (
            "run_loop no longer tells the scheduler when the next window "
            "opens, so a closed-window sleep is unbounded again and a window "
            "opening inside it is invisible for up to 900s"
        )


class TestACallableInterval:
    async def test_the_interval_is_read_after_each_pass(self):
        """The pass is what changes the state the cadence depends on.

        Reading the interval once at the top would spend a whole slow interval
        before noticing that the sweep this pass just fired had opened the
        window -- which is most of the window.
        """
        slept: list[float] = []

        async def record_sleep(seconds):
            slept.append(seconds)

        tempo = Tempo(slow_interval_s=900.0, fast_interval_s=15.0)

        calls = {"n": 0}

        async def do_pass():
            calls["n"] += 1
            # The first pass opens the window, exactly as a sweep would.
            tempo.window_open = True
            return Counts()

        await run_forever(
            do_pass, interval_s=tempo.interval_s, max_passes=2,
            sleep=record_sleep, rng=random.Random(1),
        )

        assert calls["n"] == 2
        # One sleep, between the two passes, and it used the fast interval that
        # the first pass had just made correct.
        assert len(slept) == 1
        assert 15 * (1 - JITTER) <= slept[0] <= 15 * (1 + JITTER)

    async def test_a_plain_float_still_works(self):
        slept: list[float] = []

        async def record_sleep(seconds):
            slept.append(seconds)

        await run_forever(
            Recorder(result=Counts()), interval_s=60.0, max_passes=2,
            sleep=record_sleep, rng=random.Random(1),
        )
        assert 60 * (1 - JITTER) <= slept[0] <= 60 * (1 + JITTER)
