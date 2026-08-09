"""Credit accounting and allocation for The Odds API.

The plan is the **20K tier: 20,000 credits a month** (bought 2026-08-09,
replacing the 500/month free tier). A call costs `len(markets) x len(regions)`,
so h2h + spreads + totals across `us` and `eu` is **6 credits per sport per
sweep**. An unmetered poll loop over four leagues still drains the month in
under a week.

**Why the tier changed, because it is the reason any of this matters.** On the
free tier the meter allowed ~2 sweeps a day, each opening a 15-minute window of
usable odds, against a full pass every 900s. The live instance measured the
consequence directly: `stale_odds` was 256 of 265 suppressions in 24h, and
`actionable` was 0 of the 300 games the gate needs. The budget was not a
safeguard on a working system, it *was* the binding constraint.

So spending is metered here, and the meter has three properties that matter:

**It reconciles against the server, not against our own optimism.** Every
response carries `x-requests-remaining`; we record it alongside what we
predicted the call would cost. If our arithmetic drifts from theirs, the drift
is visible in the `api_credits` table rather than discovered when the quota
runs out mid-slate.

**It refuses rather than warns.** `can_afford` returning False blocks the call.
A budget that logs a warning and proceeds is not a budget.

**It caps the month as well as the day.** `spent_this_month` was computed from
the first version of this module and never checked by anything -- a number on a
dashboard, not a guard. That was survivable while every call cost 6 credits and
the daily cap bounded the month by arithmetic. It stops being survivable the
moment a caller can spend 10x per call, which is what the historical endpoints
do (`10 x markets x regions`), so a single backfill loop could spend the month
between two daily resets without the daily cap ever objecting.

**Allocation is not decided here.** It used to be: `plan_sweep` ranked sports
by soonest kickoff and returned everything the budget allowed, so the day's
credits went on the first pass that had any -- which on 2026-08-07 meant 19:32Z,
because that is when a deploy happened. Choosing *which* sport is the easy half
of the problem and choosing *when* is the half that decides whether a pick is
ever bettable, so both now live together in `odds.timing`. What is left here is
the meter: what a call costs, what has been spent, and whether it can go ahead.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Sequence

from .timing import DEFAULT_DAY_START_UTC_HOUR, day_start_ms

logger = logging.getLogger(__name__)

# The Odds API's month resets on the calendar month in UTC.
_MS_PER_DAY = 86_400_000


def _utc_month_start_ms(now_ms: int) -> int:
    dt = datetime.fromtimestamp(now_ms / 1000, timezone.utc)
    start = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return int(start.timestamp() * 1000)


def sweep_cost(markets: Sequence[str], regions: Sequence[str]) -> int:
    """Credits for one `/odds` call. The Odds API charges markets x regions."""
    return max(1, len(markets) * len(regions))


@dataclass(frozen=True)
class BudgetState:
    daily_budget: int
    spent_today: int
    spent_this_month: int
    remaining_reported: Optional[int]
    used_reported: Optional[int] = None
    monthly_budget: Optional[int] = None

    @property
    def remaining_today(self) -> int:
        return max(0, self.daily_budget - self.spent_today)

    @property
    def remaining_this_month(self) -> Optional[int]:
        """`None` when no monthly ceiling is configured, never a fabricated 0.

        An absent ceiling and an exhausted one are different states and must not
        share a representation -- `tasks/lessons.md`, the zero that means "no
        measurement" passing every threshold.
        """
        if self.monthly_budget is None:
            return None
        return max(0, self.monthly_budget - self.spent_this_month)

    @property
    def drift(self) -> Optional[int]:
        """Our month-to-date tally minus the server's own count of what we used.

        Non-zero drift means our cost model disagrees with theirs. Worth
        surfacing: it is the difference between "we have 200 credits" and
        "we ran out on Saturday morning".

        **This previously returned `spent_this_month` and called it drift** --
        it never computed a difference at all, so the reconciliation this module
        presents as its central safety property could not signal, no matter how
        far the two counts diverged. It also could not be caught by inspection,
        because a plausible number was always there.

        Reconciled against `x-requests-used`, not against `remaining`: the
        remaining count needs a monthly allowance to subtract from, and that
        allowance is a plan detail we would have to hardcode and keep correct.
        `used` is what they say we spent, which is exactly what our tally
        claims. `None` when the server has told us nothing to compare against --
        an unknown, not a zero.
        """
        if self.used_reported is None:
            return None
        return self.spent_this_month - self.used_reported


class CreditBudget:
    """Meters spending against `api_credits`, refusing calls that breach it.

    The **day** here is a sports day, not a calendar one -- it rolls at
    `day_start_hour` UTC, 10:00 by default. UTC midnight is 8pm ET / 5pm PT,
    which falls in the middle of the US evening slate: it would put the first
    half of one night's games in one budget bucket and the second half in the
    next, so a late West Coast game competes for credits with the following
    afternoon. The *month* stays on the calendar, because that boundary belongs
    to The Odds API and reconciliation depends on agreeing with theirs.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        daily_budget: int,
        *,
        day_start_hour: int = DEFAULT_DAY_START_UTC_HOUR,
        monthly_budget: Optional[int] = None,
    ):
        self.conn = conn
        self.daily_budget = daily_budget
        self.day_start_hour = day_start_hour
        self.monthly_budget = monthly_budget

    def day_start_ms(self, now_ms: int) -> int:
        return day_start_ms(now_ms, hour=self.day_start_hour)

    def state(self, now_ms: int) -> BudgetState:
        day = self.conn.execute(
            "SELECT COALESCE(SUM(cost), 0) AS c FROM api_credits WHERE called_ms >= ?",
            (self.day_start_ms(now_ms),),
        ).fetchone()["c"]
        month = self.conn.execute(
            "SELECT COALESCE(SUM(cost), 0) AS c FROM api_credits WHERE called_ms >= ?",
            (_utc_month_start_ms(now_ms),),
        ).fetchone()["c"]
        latest = self.conn.execute(
            "SELECT remaining_reported, used_reported FROM api_credits "
            "WHERE remaining_reported IS NOT NULL ORDER BY called_ms DESC LIMIT 1"
        ).fetchone()
        return BudgetState(
            daily_budget=self.daily_budget,
            monthly_budget=self.monthly_budget,
            spent_today=int(day),
            spent_this_month=int(month),
            remaining_reported=(
                int(latest["remaining_reported"]) if latest else None
            ),
            used_reported=(
                int(latest["used_reported"])
                if latest and latest["used_reported"] is not None
                else None
            ),
        )

    def can_afford(self, cost: int, now_ms: int) -> bool:
        """Whether a call of `cost` credits is within budget -- day and month.

        Three ceilings, checked cheapest-to-recover-from last. The server's
        count wins over ours wherever they disagree, because theirs is the one
        that stops answering.

        The monthly check is not redundant with the daily one. The daily cap
        bounds the month only if you multiply it by the days remaining, which
        nothing did; and it cannot bound a caller that spends 10x per call
        inside a single day. It is also not redundant with `remaining_reported`:
        that is the *plan's* limit, while this is ours, and the gap between them
        is the headroom deliberately reserved for another lane (historical
        backfill) that would otherwise be starved by whoever spends first.
        """
        state = self.state(now_ms)
        if state.remaining_reported is not None and state.remaining_reported < cost:
            logger.warning(
                "refusing %d-credit call: the API reports only %d credits left "
                "this period",
                cost, state.remaining_reported,
            )
            return False
        remaining_month = state.remaining_this_month
        if remaining_month is not None and remaining_month < cost:
            logger.warning(
                "refusing %d-credit call: %d of %d monthly credits already "
                "spent. The daily cap cannot see this.",
                cost, state.spent_this_month, self.monthly_budget,
            )
            return False
        if state.remaining_today < cost:
            logger.warning(
                "refusing %d-credit call: %d of %d daily credits already spent",
                cost, state.spent_today, self.daily_budget,
            )
            return False
        return True

    def record(
        self,
        *,
        called_ms: int,
        endpoint: str,
        cost: int,
        sport_key: Optional[str] = None,
        markets: Optional[Sequence[str]] = None,
        regions: Optional[Sequence[str]] = None,
        remaining_reported: Optional[int] = None,
        used_reported: Optional[int] = None,
    ) -> None:
        """Record a call. Called for every request, successful or not.

        A failed call still costs credits on some error classes, so recording
        only successes would understate spend in exactly the situation where
        the count matters most.
        """
        self.conn.execute(
            "INSERT INTO api_credits (called_ms, endpoint, sport_key, markets, "
            "regions, cost, remaining_reported, used_reported) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                called_ms,
                endpoint,
                sport_key,
                ",".join(markets) if markets else None,
                ",".join(regions) if regions else None,
                cost,
                remaining_reported,
                used_reported,
            ),
        )
        self.conn.commit()

        if remaining_reported is not None and remaining_reported < 50:
            logger.warning(
                "The Odds API reports %d credits remaining this period",
                remaining_reported,
            )
