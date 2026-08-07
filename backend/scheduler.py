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


async def run_forever(
    do_pass: Callable[[], Any],
    *,
    interval_s: float,
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
        await sleep(next_delay(interval_s, rng))

    return state
