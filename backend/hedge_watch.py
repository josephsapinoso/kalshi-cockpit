"""The watcher: a held ticket's legs, read while the game is running.

ADR 0074. `hedge.py` can answer "what would a hedge do right now" whenever
somebody asks. This is the thing that asks when nobody is looking, which is the
whole difference between a screen and an alert.

Why a separate task and not the quote pass
------------------------------------------
The quote pass is budgeted 8 seconds (`QUOTE_PASS_DURATION_BUDGET_S`) so a
Kalshi quote can stay inside its 30-second freshness limit, and it already runs
~4.2s on live. ADR 0072 Decision 5 recorded what happens when work is added
there on the reasoning that it is cheap: `build_ladder` was argued free because
it is pure, and it cost 400ms per pass. **"Pure" is a claim about effects, not
about cost** -- and `Tempo.observe_pass_duration` warns on an overrun rather
than failing, so the degradation would have been silent.

This is `poll_portfolio_forever`'s shape instead: its own task, its own
connection, its own cadence, and its own failures. It cannot slow the recorder
down because it is not on the recorder's clock.

What it costs
-------------
**Nothing metered.** One Kalshi orderbook read per watched ticker per cycle, and
Kalshi is unmetered -- no `api_credits` row is written and
`ODDS_ATTENTION_DAILY_CREDITS` is untouched. No Anthropic client is reachable
from this module or anything it imports on this path. The watched set is bounded
by how many tickets one person holds and how many of their legs are still live.

The cadence follows whether there is anything to watch
------------------------------------------------------
Fast while an open ticket has a pending leg whose fixture has started; slow
otherwise. A game re-prices fastest in its closing minutes, which is exactly
when a hedge is decided, and a ticket for tomorrow night does not move at all.

**Kalshi's own `commence_ms` is not read for this** and could not be:
`runner.py` records that `occurrence_datetime` runs three hours late and "would
call the seventh inning 'not started'". The leg carries the sportsbook's kickoff
instead, recorded when the ticket was, and a leg with no kickoff at all is
treated as watchable -- an unknown start must not resolve to "not yet", which
would silence the alert for the whole game.

What this module does NOT establish
-----------------------------------
- **That an alert is worth acting on.** It reports a figure; ADR 0074 Decision 2
  is why it never reports a moment.
- **That the record is complete.** It watches what Joe typed in. A ticket he did
  not record is invisible, and no amount of polling finds it.
- **That a lock survived until he read it.** The push says what was available
  when the check ran; the screen is what says what is available now.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from . import hedge as held_parlays
from .notify.alerts import Alerter
from .odds.timing import DEFAULT_DAY_START_UTC_HOUR, day_start_ms
from .store import db as store_db

logger = logging.getLogger(__name__)

#: How often to re-read the books while a watched game is running.
#:
#: Sixty seconds against a market that re-prices every pitch is a compromise,
#: and it is the honest one: the alert is not a race. What it announces is a
#: figure that was available a minute ago, and the screen is what serves the
#: current one. A faster cycle would buy a fresher number for a decision nobody
#: makes in under a minute -- Joe reads the push, opens the Kalshi app and
#: types an order -- while multiplying reads against a shared Fly IP.
WATCH_INTERVAL_S = 60.0

#: How often to look when nothing is in progress. Cheap enough to be frequent
#: and slow enough not to be noise: the only thing it can discover is that a
#: fixture has started or a ticket was recorded from the screen.
IDLE_INTERVAL_S = 600.0


def anything_in_progress(conn, *, now_ms: int) -> bool:
    """Whether an open ticket has a pending leg whose game has started.

    A leg with no recorded kickoff counts as started. **An unknown start must
    not resolve to "not yet"** -- that is this repo's "unreadable never resolves
    to zero" rule pointed at a clock, and getting it wrong would sleep through
    the entire game rather than fail loudly.
    """
    row = conn.execute(
        """
        SELECT COUNT(*)
          FROM parlay_position_legs l
          JOIN parlay_positions p ON p.id = l.position_id
         WHERE p.status = 'open'
           AND l.outcome = 'pending'
           AND l.ticker IS NOT NULL
           AND (l.commence_ms IS NULL OR l.commence_ms <= ?)
        """,
        (now_ms,),
    ).fetchone()
    return bool(row and int(row[0]) > 0)


async def watch_once(
    conn,
    alerter: Alerter,
    *,
    now_ms: int,
    max_quote_age_ms: int,
    fetch_quote,
    day_start_hour: int = DEFAULT_DAY_START_UTC_HOUR,
) -> dict:
    """One cycle: settle what the venue has settled, re-price, alert on locks.

    Settling first is load-bearing rather than tidy. A lock exists only when
    every OTHER leg has already won, so a leg the venue called ten minutes ago
    and nobody has read is the difference between "several legs live" and "one
    leg live" -- between a de-risk and a figure worth a push.
    """
    settled = held_parlays.resolve_from_venue(conn, now_ms=now_ms)
    screen = await held_parlays.build_payload(
        conn,
        now_ms=now_ms,
        max_quote_age_ms=max_quote_age_ms,
        spendable_tenths=store_db.latest_balance_tenths(conn),
        fetch_quote=fetch_quote,
    )
    result = await alerter.hedge_locks(
        screen,
        now_ms=now_ms,
        day_start_ms=day_start_ms(now_ms, hour=day_start_hour),
    )
    return {
        "legs_settled": settled,
        "positions": len(screen["positions"]),
        **result.as_dict(),
    }


async def watch_hedges_forever(
    db_path,
    alerter_factory,
    *,
    fetch_quote,
    max_quote_age_ms: int,
    watch_interval_s: float = WATCH_INTERVAL_S,
    idle_interval_s: float = IDLE_INTERVAL_S,
    day_start_hour: int = DEFAULT_DAY_START_UTC_HOUR,
    sleep=asyncio.sleep,
    clock=time.time,
    max_cycles: Optional[int] = None,
) -> None:
    """The watcher as a long-running task beside the chain runner.

    **A failed cycle is logged and the loop continues.** A wedged venue, a
    revoked credential or a Discord outage must degrade this to "no hedge
    alerts" and must never take down the process that is recording evidence --
    the same ruling `Alerter` already carries, one layer out. Only
    `CancelledError` exits, because the caller cancelling is the one legitimate
    way this loop ends.

    **Its own connection**, for `poll_portfolio_forever`'s reason: a concurrent
    task on the pass's handle would interleave two transactions on one
    connection, and a second connection in the same process is what WAL is for.

    `alerter_factory` is passed rather than an `Alerter`, because an `Alerter`
    binds a connection and this function owns the only one it may use.
    `sleep`, `clock` and `max_cycles` exist for tests; production passes none.
    """
    conn = store_db.connect(db_path)
    try:
        alerter = alerter_factory(conn)
        cycles = 0
        while max_cycles is None or cycles < max_cycles:
            cycles += 1
            now_ms = int(clock() * 1000)
            busy = False
            try:
                busy = anything_in_progress(conn, now_ms=now_ms)
                if busy:
                    summary = await watch_once(
                        conn,
                        alerter,
                        now_ms=now_ms,
                        max_quote_age_ms=max_quote_age_ms,
                        fetch_quote=fetch_quote,
                        day_start_hour=day_start_hour,
                    )
                    if summary["alerts_sent"] or summary["legs_settled"]:
                        logger.info("hedge watch: %s", summary)
            except asyncio.CancelledError:
                raise
            except Exception:                                    # noqa: BLE001
                # Deliberately broad, and deliberately not re-raised. See the
                # docstring: this task existing is what makes hedge alerts
                # possible, and it existing tomorrow matters more than any one
                # cycle succeeding today.
                logger.exception("hedge watch cycle failed")
            await sleep(watch_interval_s if busy else idle_interval_s)
    finally:
        conn.close()
