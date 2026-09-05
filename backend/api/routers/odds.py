"""`/api/odds/*`: what the refresh button may buy, and the buy itself.

Moved verbatim from `backend/api/routes.py` on 2026-09-04; see
`backend/api/routers/__init__.py` for the `register()` shape and why.
`refresh_odds` is the one authenticated route whose whole purpose is to spend
money at a third party, which is why every field of `OddsRefreshRequest` is
re-validated against `odds_snapshots` here rather than trusted.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI

from ...config import AppConfig, OddsConfig
from ...odds import ondemand
from ...odds.budget import CreditBudget, sweep_cost
from ...odds.client import prop_market_keys
from ...store import db
from ..schemas import OddsRefreshRequest


def register(
    app: FastAPI,
    *,
    app_config: AppConfig,
    odds: OddsConfig,
    get_conn,
    require_auth,
) -> None:
    """Attach the two odds handlers to `app`, in their original order."""

    @app.get("/api/odds/refreshable")
    def refreshable(conn=Depends(get_conn)) -> dict:
        """What the refresh button may buy, and what each purchase costs.

        Its own route rather than fields on `/api/slate` or `/api/board`. Those
        two payloads are pinned by four tests that stop anything on them
        becoming a composite, and a fixture list keyed for *spending* has no
        business travelling beside rows keyed for *reading* -- they answer
        different questions and would gain each other's callers.

        **The costs come from the deployed market and region lists**, computed
        here through `sweep_cost`, which is the same function the planner
        reserves with and the client bills against. A screen that arithmetics
        its own `6` passes happily while the deployment says otherwise, which is
        exactly how the prop bill was estimated at ten a fixture and came in at
        twenty.

        Read-only and unauthenticated-in-itself: it names prices and fixtures,
        both of which are already on `/api/slate`. The spend is behind
        `POST /api/odds/refresh`, which requires the token.
        """
        now = db.now_ms()
        horizon_ms = 24 * 3_600_000
        rows = conn.execute(
            "SELECT DISTINCT o.sport_key, o.odds_event_id, o.commence_ms, "
            "o.home_team, o.away_team FROM odds_snapshots o "
            "WHERE o.commence_ms >= ? AND o.commence_ms <= ? "
            "ORDER BY o.commence_ms",
            (now, now + horizon_ms),
        ).fetchall()

        team_credits = sweep_cost(odds.markets, odds.regions)
        prop_credits = sweep_cost(prop_market_keys(), odds.regions)
        # The same construction the POST refuses with, never a second count.
        budget_state = CreditBudget(
            conn,
            daily_budget=odds.daily_credit_budget,
            monthly_budget=odds.monthly_credit_budget,
            day_start_hour=odds.budget_day_start_utc_hour,
        ).state(now)
        by_sport: dict[str, list[dict]] = {}
        for row in rows:
            by_sport.setdefault(row["sport_key"], []).append(
                {
                    "odds_event_id": row["odds_event_id"],
                    "commence_ms": row["commence_ms"],
                    # The books' own names, so the button and the row a person
                    # is looking at say the same thing. Kalshi's title would be
                    # a different string for the same game.
                    "title": f"{row['away_team']} at {row['home_team']}",
                }
            )

        return {
            "sports": [
                {
                    "sport_key": sport,
                    "team_credits": team_credits,
                    # What a *prop* tap costs in total: the fixture's props plus
                    # the team call that finds it. `fetch_and_store_props` is
                    # only ever reached from a served team sweep, so quoting the
                    # prop half alone would understate every tap.
                    "prop_credits": team_credits + prop_credits,
                    "fixtures": fixtures,
                }
                for sport, fixtures in sorted(by_sport.items())
            ],
            # Surfaced so a screen can say what it is protecting rather than
            # only reporting a refusal after the fact.
            "manual_daily_credits": ondemand.DEFAULT_MANUAL_DAILY_CREDITS,
            # The spend so far, through the same file and the same arithmetic
            # `submit` refuses against, so the panel can say "12 of 150 left"
            # instead of restating the ceiling. Over-counts by design: a tap is
            # counted when it is accepted, served or not.
            "manual_credits_spent_today": ondemand.manual_spent_today(
                ondemand.inbox_path(app_config.db_path),
                now,
                day_start_hour=odds.budget_day_start_utc_hour,
            ),
            # The whole day's budget beside the taps' slice of it. `remaining`
            # is `BudgetState.remaining_today` -- computed by the planner since
            # the beginning and exposed nowhere until now, which left the panel
            # quoting a constant where a person was deciding whether to spend.
            "day_credits_spent": budget_state.spent_today,
            "day_credits_budget": budget_state.daily_budget,
            "day_credits_remaining": budget_state.remaining_today,
            "cooldown_ms": ondemand.DEFAULT_COOLDOWN_MS,
            "note": (
                "A refresh buys a fresh price. It does not make a row bettable "
                "and cannot produce an edge that was not there."
            ),
        }

    @app.post("/api/odds/refresh", dependencies=[Depends(require_auth)])
    def refresh_odds(request: OddsRefreshRequest, conn=Depends(get_conn)) -> dict:
        """Buy fresh sportsbook odds now, because someone is looking at the screen.

        **Why a screen needs this at all.** `_live_ages` re-checks the stored
        consensus against *now* on every read, so `actionable` goes false
        `MAX_ODDS_AGE_S` after the sweep that priced the row -- whatever the row
        looked like when it was written. The rolling refresh (ADR 0030) holds
        that open across a planned kickoff cluster, which is the hour before
        first pitch and nothing else. Open the cockpit two hours out and the
        whole slate is struck through on a clock rather than on a price. This is
        the button that answers that, and it is the only path by which a person
        rather than the planner causes a credit to be spent.

        **It does not fetch anything.** This process opens the database
        read-only and is not the process that holds the odds client -- see
        `docker/entrypoint.sh`, which runs the API and the chain runner
        separately. The request is written to a file the runner reads on its
        ~15s cadence, so the answer here is *accepted*, never *served*. Saying
        "refreshed" in this response would be a claim about a call that has not
        been made yet and may still be refused on budget.

        Every ceiling is `ondemand.submit`'s, and the budget one is read through
        `CreditBudget` -- the same implementation the planner spends against,
        never a second count of the day.

        202, not 200: the work is accepted for later. A refusal is 200 with
        `accepted: false` and the reason in words, because a cooldown or a
        ceiling is a normal answer to a reasonable tap and a 4xx would have the
        UI render it as a fault.
        """
        now = db.now_ms()
        horizon_ms = 24 * 3_600_000
        fixtures = conn.execute(
            "SELECT DISTINCT odds_event_id FROM odds_snapshots "
            "WHERE sport_key = ? AND commence_ms >= ? AND commence_ms <= ?",
            (request.sport_key, now, now + horizon_ms),
        ).fetchall()
        known = {row["odds_event_id"] for row in fixtures}
        if not known:
            # Not 404. The sport may be perfectly real and simply have no
            # fixture inside the day -- refusing with the reason is more use on
            # a phone than a status code, and it is the same shape as every
            # other refusal this endpoint returns.
            return {
                "accepted": False,
                "detail": (
                    f"no {request.sport_key} fixture is stored inside the next "
                    f"24 hours, so a refresh would buy a slate with nothing to "
                    f"price against"
                ),
                "estimated_credits": 0,
                "retry_after_ms": 0,
            }
        if request.odds_event_id is not None and request.odds_event_id not in known:
            return {
                "accepted": False,
                "detail": (
                    f"fixture {request.odds_event_id} is not a stored upcoming "
                    f"{request.sport_key} game. Props are billed per fixture, "
                    f"so this refuses rather than paying to find out."
                ),
                "estimated_credits": 0,
                "retry_after_ms": 0,
            }

        cost = ondemand.manual_cost(
            team_cost=sweep_cost(odds.markets, odds.regions),
            prop_cost_per_event=sweep_cost(prop_market_keys(), odds.regions),
            odds_event_id=request.odds_event_id,
        )
        budget = CreditBudget(
            conn,
            daily_budget=odds.daily_credit_budget,
            monthly_budget=odds.monthly_credit_budget,
            day_start_hour=odds.budget_day_start_utc_hour,
        )
        submission = ondemand.submit(
            ondemand.inbox_path(app_config.db_path),
            sport_key=request.sport_key,
            odds_event_id=request.odds_event_id,
            now_ms=now,
            estimated_credits=cost,
            budget_refusal=budget.refusal_reason(cost, now),
            day_start_hour=odds.budget_day_start_utc_hour,
        )
        return {
            "accepted": submission.accepted,
            "detail": submission.detail,
            "estimated_credits": submission.estimated_credits,
            "retry_after_ms": submission.retry_after_ms,
        }
