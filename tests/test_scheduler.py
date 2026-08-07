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

from backend.scheduler import (
    JITTER,
    MAX_CONSECUTIVE_FAILURES,
    LoopFailed,
    LoopState,
    next_delay,
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
