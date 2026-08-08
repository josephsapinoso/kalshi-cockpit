"""Credit accounting and allocation for The Odds API.

The free tier is **500 credits a month** and a call costs
`len(markets) x len(regions)`. Requesting h2h + spreads + totals across `us` and
`eu` is therefore **6 credits per sport per sweep**. An unmetered poll loop over
four leagues drains the entire month in a bit over a day.

So spending is metered here, and the meter has two properties that matter:

**It reconciles against the server, not against our own optimism.** Every
response carries `x-requests-remaining`; we record it alongside what we
predicted the call would cost. If our arithmetic drifts from theirs, the drift
is visible in the `api_credits` table rather than discovered when the quota
runs out mid-slate.

**It refuses rather than warns.** `can_afford` returning False blocks the call.
A budget that logs a warning and proceeds is not a budget.

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

    @property
    def remaining_today(self) -> int:
        return max(0, self.daily_budget - self.spent_today)

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
    ):
        self.conn = conn
        self.daily_budget = daily_budget
        self.day_start_hour = day_start_hour

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
        """Whether a call of `cost` credits is within today's budget.

        Also refuses when the server says we have less than the call costs,
        even if our own tally disagrees -- their count is authoritative.
        """
        state = self.state(now_ms)
        if state.remaining_reported is not None and state.remaining_reported < cost:
            logger.warning(
                "refusing %d-credit call: the API reports only %d credits left "
                "this period",
                cost, state.remaining_reported,
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
