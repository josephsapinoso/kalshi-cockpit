"""The loop that keeps the record growing.

The runner records one pass. Nothing called it twice, and the gate needs **300
independent games** — roughly three weeks of unbroken recording at fifteen
games a day. So the loop is not a convenience: it is the thing that makes the
project's central question answerable at all, and every hour it is not running
is an hour added to the earliest possible answer.

Failing loudly
--------------
A background loop that swallows its exceptions is the worst possible shape for
this system. The cockpit keeps serving, the Board keeps rendering yesterday's
prices, the health check passes, and the whole thing looks like a quiet market.
That is precisely the failure `docker/entrypoint.sh` exists to prevent for the
two server processes, and the loop deserves the same treatment.

So: a pass that raises is logged with its traceback and retried, because
transient failures are normal — an odds sweep can 502, Kalshi can rate-limit.
But `MAX_CONSECUTIVE_FAILURES` in a row **re-raises**, which kills the process,
which trips `wait -n` in the entrypoint, which takes the container down and
lets the platform restart it clean. Repeated failure is not a state to sit in
quietly.

The interval is jittered for the ordinary reason: a fleet of machines restarting
together would otherwise sweep in lockstep, and the odds budget is small enough
that a thundering herd is a real way to lose a day's credits in a minute.

Two cadences, because two resources have nothing in common
----------------------------------------------------------
The 900s interval exists for The Odds API's free tier and for nothing else.
Kalshi REST is unmetered, and the Kalshi quote is the *tighter* of the two
freshness limits at 30s against the consensus's 900s. Running both legs on the
odds cadence therefore produced a row that was bettable for thirty seconds after
each pass -- about a minute a day of actionability, from a system every document
in this repo described as actionable for half an hour.

So `Tempo` runs the loop fast while the window is open and slow when it is not,
and `run_forever` takes a callable interval so the cadence can follow that
state. The fast passes touch Kalshi only.
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# Consecutive failures before the loop gives up and takes the process with it.
# Not 1: a single 502 from a sportsbook aggregator is not a reason to restart a
# container. Not 50: by then the record has a hole in it that nothing will
# report, because a gap in observations looks exactly like a quiet slate.
MAX_CONSECUTIVE_FAILURES = 5

# Fraction of the interval to jitter by.
JITTER = 0.15


class LoopFailed(RuntimeError):
    """Raised after too many consecutive failed passes. Ends the process."""


@dataclass
class LoopState:
    """What the loop has done. Readable from outside for health reporting.

    `last_success_ms` is the field that matters. "The process is alive" and
    "the data is fresh" are different claims, and only this one supports the
    second.
    """

    passes_attempted: int = 0
    passes_succeeded: int = 0
    consecutive_failures: int = 0
    last_success_ms: Optional[int] = None
    last_error: Optional[str] = None
    last_counts: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "passes_attempted": self.passes_attempted,
            "passes_succeeded": self.passes_succeeded,
            "consecutive_failures": self.consecutive_failures,
            "last_success_ms": self.last_success_ms,
            "last_error": self.last_error,
            "last_counts": self.last_counts,
        }


def next_delay(interval_s: float, rng: Optional[random.Random] = None) -> float:
    """Interval with proportional jitter, never negative."""
    r = rng or random
    return max(1.0, interval_s * (1.0 + r.uniform(-JITTER, JITTER)))


# ---------------------------------------------------------------------------
# Two cadences
# ---------------------------------------------------------------------------

# How long a pass itself is allowed to take, on top of the sleep, before the
# fast cadence stops keeping a row inside the Kalshi limit. A quote pass
# paginates `/events`, writes ~1,500 quote rows and re-prices the linked ones.
#
# An allowance, not a measurement, and it is checked against the real thing:
# `Tempo.observe_pass_duration` warns when an actual pass exceeds it, because
# the number that decides whether this works is the *gap between confirmations*
# -- sleep plus pass -- and only one half of that is chosen here.
QUOTE_PASS_DURATION_BUDGET_S = 8.0

# The fast cadence, used only while the window is open. 15s against a 30s
# Kalshi limit: with 15% jitter and the 8s allowance above, the worst-case gap
# between confirmations is 25.3s, inside 30s with room for a slow pass.
DEFAULT_FAST_INTERVAL_S = 15.0


def quote_refresh_survives_interval(
    interval_s: float,
    *,
    jitter: float,
    max_kalshi_quote_age_s: float,
    pass_duration_s: float = QUOTE_PASS_DURATION_BUDGET_S,
) -> bool:
    """Whether polling this often actually keeps a row inside the quote limit.

    **The composition, written down as a number a test can read.** This repo has
    now been bitten twice by several individually defensible limits multiplying
    into one unusable window, and the second time it was this exact quantity:
    `MAX_KALSHI_QUOTE_AGE_S = 30`, `MAX_ODDS_AGE_S = 900`, loop interval 900s,
    product = thirty seconds of actionability twice a day. Every module held one
    of the three and none of them held the product.

    The gap between two confirmations of the same row is the sleep *plus* the
    pass, so both go in. If that gap exceeds the limit the fast cadence is
    decoration: it costs requests and rows and the row still expires between
    passes, and nothing would report that -- an expired row looks exactly like a
    row nobody wanted.

    Deliberately not `<=`. A gap exactly equal to the limit leaves a row
    unbettable at the instant it is re-confirmed.
    """
    worst_case_gap_s = interval_s * (1.0 + jitter) + pass_duration_s
    return worst_case_gap_s < max_kalshi_quote_age_s


@dataclass
class Tempo:
    """Which cadence to run at, and which kind of pass is due.

    Two decisions, kept together because they are the same decision seen from
    two sides:

    - **How often to look.** Fast while the window is open, because the Kalshi
      quote behind every row expires in 30s. Slow when it is not, because there
      is nothing to keep fresh and Kalshi has no reason to be polled 4,300 times
      a day for it.
    - **What to do when we look.** A *full* pass on the slow interval -- odds
      sweep, closing lines, digest -- and a *quote* pass in between, which
      touches Kalshi and nothing else. A full pass every 15s would fetch
      candlesticks for every started game ninety times an hour to no purpose.

    `last_full_ms` is recorded by the caller **after** a full pass succeeds, so
    a full pass that raises is retried rather than being counted as done and
    followed by fifteen minutes of quote passes.

    State lives here rather than in `run_forever` because it is policy, not
    looping, and because a pure object is testable without a clock.
    """

    slow_interval_s: float
    fast_interval_s: float = DEFAULT_FAST_INTERVAL_S
    window_open: bool = False
    last_full_ms: Optional[int] = None
    slow_passes: int = 0
    fast_passes: int = 0
    quote_passes_overrun: int = 0
    full_passes_overrun_in_window: int = 0

    def interval_s(self) -> float:
        """The sleep to take next. Passed to `run_forever` as a callable."""
        return self.fast_interval_s if self.window_open else self.slow_interval_s

    def pass_kind(self, now_ms: int) -> str:
        """`"full"` or `"quote"`.

        The first pass of a process is always full: a fresh container has no
        odds stored, so a quote pass would price nothing and the window could
        never open in the first place.
        """
        if self.last_full_ms is None:
            return "full"
        due_ms = self.last_full_ms + self.slow_interval_s * 1000
        return "quote" if now_ms < due_ms else "full"

    def completed_full_pass(self, now_ms: int) -> None:
        self.last_full_ms = now_ms
        self.slow_passes += 1

    def completed_quote_pass(self, now_ms: int) -> None:
        self.fast_passes += 1

    def observe_pass_duration(
        self,
        seconds: float,
        *,
        max_kalshi_quote_age_s: float,
        kind: str,
    ) -> bool:
        """Whether a pass that took this long still fits the fast cadence.

        The startup check uses an *allowance* for how long a pass takes. This
        uses what one actually took. A quote pass slow enough to break the
        composition turns the fast cadence into wasted requests, and the symptom
        -- rows expiring between passes -- is indistinguishable from a quiet
        board, so it has to be said out loud rather than inferred.

        **`kind` is not optional, and the first live pass is why.** This warned
        on *every* pass against the *fast* interval, and the first full pass on
        the live instance -- 167 events discovered, 1,426 markets quoted, 228
        rows joined for CLV, 14.9s, entirely normal -- tripped it while the
        window was closed and no quote pass was running at all. Full passes
        happen every 900s forever, so the counter Joe was told to watch would
        have been ~96 routine entries a day and could never have surfaced the
        one condition it exists for. That is this repo's own rule: if most
        inputs trigger it, it is a state, not an exception, and logging it as an
        exception destroys the log's value as a diagnostic.

        The two questions, which are not the same question:

        - **quote pass** -- "is the fast cadence decoration?" A quote pass runs
          on the 15s interval, so its duration goes straight into the gap
          between confirmations. This is the diagnostic.
        - **full pass** -- "does the once-per-window full pass push rows past
          the limit while they are bettable?" Structural rather than
          surprising: one gap in sixty, every window. Counted separately, and
          only while the window is open, because outside it nothing is bettable
          and the arithmetic describes a cadence that is not running.
        """
        ok = quote_refresh_survives_interval(
            self.fast_interval_s,
            jitter=JITTER,
            max_kalshi_quote_age_s=max_kalshi_quote_age_s,
            pass_duration_s=seconds,
        )
        if ok:
            return True

        gap_s = self.fast_interval_s * (1 + JITTER) + seconds

        if kind == "quote":
            self.quote_passes_overrun += 1
            logger.warning(
                "a QUOTE pass took %.1fs; with a %.0fs fast interval and %.0f%% "
                "jitter the worst-case gap between confirmations is %.1fs, past "
                "the %.0fs Kalshi quote limit. The fast cadence is not keeping "
                "rows inside the limit -- they expire between passes, and an "
                "expired row looks exactly like a row nobody wanted.",
                seconds, self.fast_interval_s, JITTER * 100, gap_s,
                max_kalshi_quote_age_s,
            )
            return False

        if self.window_open:
            self.full_passes_overrun_in_window += 1
            logger.info(
                "a full pass took %.1fs inside an open window, so the one "
                "confirmation gap spanning it is %.1fs against a %.0fs limit -- "
                "rows read as expired around each full pass. Expected once per "
                "window; only a QUOTE pass overrun means the fast cadence is "
                "failing.",
                seconds, gap_s, max_kalshi_quote_age_s,
            )
        return False

    def as_dict(self) -> dict[str, Any]:
        return {
            "window_open": self.window_open,
            "slow_passes": self.slow_passes,
            "fast_passes": self.fast_passes,
            # Named for the population each counts. One aggregate covering both
            # read as "the fast cadence is failing" while counting full passes
            # doing exactly what they are supposed to.
            "passes_over_quote_budget": self.quote_passes_overrun,
            "full_passes_over_limit_in_window": self.full_passes_overrun_in_window,
        }


async def run_forever(
    do_pass: Callable[[], Any],
    *,
    interval_s: float | Callable[[], float],
    state: Optional[LoopState] = None,
    max_passes: Optional[int] = None,
    max_consecutive_failures: int = MAX_CONSECUTIVE_FAILURES,
    sleep=asyncio.sleep,
    rng: Optional[random.Random] = None,
    now_ms: Optional[Callable[[], int]] = None,
) -> LoopState:
    """Run `do_pass` on an interval until it fails too many times in a row.

    `do_pass` is an async callable returning anything with an `as_dict()`, or
    any object at all -- the loop only records it. Injecting it (rather than
    importing the runner here) keeps this module testable without a network,
    a database, or a clock.

    `interval_s` may be a **callable**, evaluated after each pass rather than
    once at the top. The cadence depends on whether anything is currently
    bettable, which is a fact that changes during the run -- see `Tempo`. A
    fixed float still works and is what most callers pass.

    `max_passes` exists for tests and for a `--once` style invocation. Without
    it the loop runs until the process is killed or it gives up.
    """
    from .store.db import now_ms as default_now

    clock = now_ms or default_now
    state = state or LoopState()

    while max_passes is None or state.passes_attempted < max_passes:
        state.passes_attempted += 1
        try:
            result = await do_pass()
        except Exception as exc:                          # noqa: BLE001
            state.consecutive_failures += 1
            state.last_error = f"{type(exc).__name__}: {exc}"
            # `exception` rather than `error`, so the traceback reaches the log.
            # A loop failure with no traceback is a bug report with no address.
            logger.exception(
                "pass %d failed (%d consecutive)",
                state.passes_attempted, state.consecutive_failures,
            )
            if state.consecutive_failures >= max_consecutive_failures:
                raise LoopFailed(
                    f"{state.consecutive_failures} consecutive failed passes; "
                    f"last error: {state.last_error}. Ending the process rather "
                    f"than serving prices that are no longer being updated."
                ) from exc
        else:
            state.passes_succeeded += 1
            state.consecutive_failures = 0
            state.last_error = None
            state.last_success_ms = clock()
            state.last_counts = (
                result.as_dict() if hasattr(result, "as_dict") else {}
            )
            logger.info(
                "pass %d ok: %s", state.passes_attempted, state.last_counts
            )

        if max_passes is not None and state.passes_attempted >= max_passes:
            break
        # Read after the pass, not before: the pass is what changes the state
        # the cadence depends on. Reading it first would spend a whole slow
        # interval before noticing that the sweep this pass just fired had
        # opened the window.
        current = interval_s() if callable(interval_s) else interval_s
        await sleep(next_delay(current, rng))

    return state
