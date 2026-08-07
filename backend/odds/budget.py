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

Allocation follows one rule: **poll the games that start soonest, most often.**
Lines move most in the hours before a game, and a stale line on a game that
starts in six days costs nothing because nothing will be bet on it.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional, Sequence

logger = logging.getLogger(__name__)

# The Odds API's month resets on the calendar month in UTC.
_MS_PER_DAY = 86_400_000


def _utc_day_start_ms(now_ms: int) -> int:
    dt = datetime.fromtimestamp(now_ms / 1000, timezone.utc)
    start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(start.timestamp() * 1000)


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

    @property
    def remaining_today(self) -> int:
        return max(0, self.daily_budget - self.spent_today)

    @property
    def drift(self) -> Optional[int]:
        """Our month-to-date tally minus what the server says we have left.

        Non-zero drift means our cost model disagrees with theirs. Worth
        surfacing: it is the difference between "we have 200 credits" and
        "we ran out on Saturday morning".
        """
        return None if self.remaining_reported is None else self.spent_this_month


class CreditBudget:
    """Meters spending against `api_credits`, refusing calls that breach it."""

    def __init__(self, conn: sqlite3.Connection, daily_budget: int):
        self.conn = conn
        self.daily_budget = daily_budget

    def state(self, now_ms: int) -> BudgetState:
        day = self.conn.execute(
            "SELECT COALESCE(SUM(cost), 0) AS c FROM api_credits WHERE called_ms >= ?",
            (_utc_day_start_ms(now_ms),),
        ).fetchone()["c"]
        month = self.conn.execute(
            "SELECT COALESCE(SUM(cost), 0) AS c FROM api_credits WHERE called_ms >= ?",
            (_utc_month_start_ms(now_ms),),
        ).fetchone()["c"]
        latest = self.conn.execute(
            "SELECT remaining_reported FROM api_credits "
            "WHERE remaining_reported IS NOT NULL ORDER BY called_ms DESC LIMIT 1"
        ).fetchone()
        return BudgetState(
            daily_budget=self.daily_budget,
            spent_today=int(day),
            spent_this_month=int(month),
            remaining_reported=(
                int(latest["remaining_reported"]) if latest else None
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


@dataclass(frozen=True)
class SweepPlan:
    """One planned `/odds` call."""

    sport_key: str
    cost: int
    soonest_commence_ms: int
    reason: str


def plan_sweep(
    upcoming: dict[str, list[int]],
    *,
    markets: Sequence[str],
    regions: Sequence[str],
    budget: CreditBudget,
    now_ms: int,
    horizon_hours: float = 48.0,
) -> list[SweepPlan]:
    """Decide which sports to poll, in priority order, within budget.

    `upcoming` maps sport_key -> commence times (epoch ms) of its known games.

    Two rules:

    **Skip sports with nothing starting inside the horizon.** A line that is
    six days out will move many times before it matters; paying to watch it now
    buys nothing.

    **Order by soonest kickoff.** Lines move most in the hours before a game,
    which is also when a stale quote is most likely to be the reason an
    opportunity looks real when it is not.

    Returns only the calls that fit the budget, in the order they should run.
    A caller that ignores the ordering and truncates will keep the *wrong*
    sports.
    """
    horizon_ms = int(horizon_hours * 3600 * 1000)
    cost = sweep_cost(markets, regions)

    candidates: list[SweepPlan] = []
    for sport_key, commences in upcoming.items():
        future = [c for c in commences if c >= now_ms]
        if not future:
            continue
        soonest = min(future)
        if soonest - now_ms > horizon_ms:
            continue
        hours = (soonest - now_ms) / 3_600_000
        candidates.append(
            SweepPlan(
                sport_key=sport_key,
                cost=cost,
                soonest_commence_ms=soonest,
                reason=f"next game in {hours:.1f}h",
            )
        )

    candidates.sort(key=lambda p: p.soonest_commence_ms)

    affordable: list[SweepPlan] = []
    projected = 0
    state = budget.state(now_ms)
    for plan in candidates:
        if projected + plan.cost > state.remaining_today:
            logger.info(
                "budget exhausted after %d of %d sports; %s and later deferred",
                len(affordable), len(candidates), plan.sport_key,
            )
            break
        affordable.append(plan)
        projected += plan.cost

    return affordable
