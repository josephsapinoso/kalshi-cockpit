"""`/api/leg-verdicts`: the leg scout's own routes (#151/#152, ADR 0186).

`POST` resolves each requested leg server-side -- the ask for the side being
bought, kickoff, and the game's desk briefing all come from the database,
never from the request body, so no price can be smuggled in from the
browser. A leg with a fresh cached verdict is served without spending; a leg
the day cannot afford comes back `refused` and writes nothing; everything
else gets a `running` row and a background call, shaped exactly like
`backend/api/routers/scout.py::send_scout_desk` -> `_run_scout_desk`.

`GET` only reads `leg_verdicts`. It spends nothing and convenes nothing.

**This is the API's other caller of the billed path**, beside
`routers/scout.py`. `request_leg_verdicts` re-checks
`AgentBudget.refusal_reason` per leg before writing a `running` row, and
`build_client` is referenced only inside the background task
`backend.leg_verdicts._run_leg_verdict` consumes -- the exact shape
`tests/test_has_callers.py`'s `BILLED_PATH_CALL_SITES` already expects of
`backend/agents/leg_verdict.py`'s own entry.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from ...agents.base import AgentConfig
from ...agents.budget import AgentBudget
from ...agents.leg_verdict import (
    LEG_VERDICT_MAX_SEARCHES,
    LEG_VERDICT_TOKEN_RESERVATION,
)
from ...config import LegVerdictConfig
from ...leg_verdicts import (
    RUNNING_PATIENCE_MS,
    LegContext,
    LegRefusal,
    _row_to_response,
    _run_leg_verdict,
    cached_verdict,
    insert_running_row,
    read_verdicts,
    resolve_leg,
)
from ...store import db

logger = logging.getLogger(__name__)

#: `POST /api/leg-verdicts`: at most this many legs in one request -- the
#: whole point of a ladder card, never a slate-wide sweep.
MAX_LEGS_PER_REQUEST = 8


class LegRequest(BaseModel):
    """One `(ticker, side)`. `extra="forbid"` is the whole security property
    of this route: an `ask` field here would let the browser name its own
    price, and this model refuses it with a 422 before any handler code
    runs."""

    model_config = ConfigDict(extra="forbid")

    ticker: str
    side: str


class LegVerdictsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trigger: str
    card_key: Optional[str] = None
    legs: list[LegRequest] = Field(default_factory=list, max_length=MAX_LEGS_PER_REQUEST)


def _refusal_item(ticker: str, side: str, reason: str) -> dict:
    return {
        "ticker": ticker,
        "side": side,
        "state": "refused",
        "id": None,
        "verdict": None,
        "reason": None,
        "ask_display_at_verdict": None,
        "age_ms": None,
        "refusal_reason": reason,
    }


_MS_PER_HOUR = 60 * 60 * 1000


def _running_verdicts(conn, now_ms: int) -> int:
    """Leg verdicts still in flight: `running` and younger than the patience
    window `cached_verdict` uses, so a row whose process died stops holding
    budget at the same moment it stops being served as pending."""
    return int(
        conn.execute(
            "SELECT COUNT(*) FROM leg_verdicts "
            "WHERE status = 'running' AND requested_ms > ?",
            (now_ms - RUNNING_PATIENCE_MS,),
        ).fetchone()[0]
    )


def _budget_refusal_message(budget: AgentBudget, now_ms: int) -> str:
    """Plain words for a budget refusal (#154), replacing `refusal_reason`'s
    operator text -- "500000 of 500000 Anthropic tokens already recorded
    today" -- with something Joe's rule for this feature (#151) allows:
    everyday sentences, no jargon.

    Any non-`None` `budget.refusal_reason` -- the calls, tokens, searches or
    per-pass ceiling -- means today's allowance is spent; the operator text
    still reaches the server log, because `budget.refusal_reason` logs it
    itself before returning. `backend/agents/budget.py` is untouched: the
    scout desk and the logs still read its own text, and this function only
    runs at this route's one call site.

    N is hours from `now_ms` to the *next* `AgentBudget.day_start_ms`
    boundary, rounded UP -- never a hard-coded 10:00 UTC, so a configured
    `day_start_hour` still gets the right answer. Hours-until, not a clock
    time, so no timezone guess is shown to Joe.
    """
    next_boundary_ms = budget.day_start_ms(now_ms) + 24 * _MS_PER_HOUR
    remaining_ms = next_boundary_ms - now_ms
    if remaining_ms < _MS_PER_HOUR:
        when = "in under an hour"
    else:
        hours = -(-remaining_ms // _MS_PER_HOUR)  # ceil division, no float
        when = f"in about {hours} hours"
    return f"The scouts have used today's allowance. They're back {when}."


def register(app: FastAPI, *, app_config, get_conn, require_auth) -> None:
    """Attach the two leg-verdict handlers to `app`."""

    @app.post(
        "/api/leg-verdicts",
        dependencies=[Depends(require_auth)],
        status_code=202,
    )
    async def request_leg_verdicts(request: LegVerdictsRequest) -> dict:
        """Resolve each leg server-side; serve a cached verdict or send one.

        Auth required, 202 always: the answer for each leg is one of
        `cached` (served now, no call), `pending` (a call is running --
        either just started or already in flight), or `refused` (spends
        nothing). Never a synchronous verdict: the seat searches the web and
        can take tens of seconds, and a phone tap must not hold a request
        open that long -- the same honesty rule `send_scout_desk` follows.
        """
        if request.trigger not in ("price_tap", "leg_buys_open", "card_button"):
            raise HTTPException(
                status_code=422,
                detail="trigger must be 'price_tap', 'leg_buys_open' or "
                       "'card_button'.",
            )
        for leg in request.legs:
            if leg.side not in ("yes", "no"):
                raise HTTPException(
                    status_code=422,
                    detail=f"a leg's side is 'yes' or 'no', not {leg.side!r}.",
                )

        config = LegVerdictConfig.load()
        if not config.enabled:
            raise HTTPException(
                status_code=503,
                detail="The leg scout is not enabled on this instance "
                       "(LEG_VERDICT_ENABLED is false).",
            )
        agent_config = AgentConfig.from_env()
        if agent_config is None:
            raise HTTPException(
                status_code=503,
                detail="No ANTHROPIC_API_KEY configured, so the leg scout "
                       "cannot be paid. This is a configuration state, not "
                       "a refusal.",
            )

        write_conn = db.open_db(app_config.db_path)
        try:
            now = db.now_ms()
            budget = AgentBudget.from_config(write_conn, agent_config)
            results: list[dict] = []
            for leg in request.legs:
                ticker, side = leg.ticker, leg.side
                resolved = resolve_leg(write_conn, ticker, side, now)
                if isinstance(resolved, LegRefusal):
                    results.append(_refusal_item(ticker, side, resolved.reason))
                    continue
                ctx: LegContext = resolved

                cached = cached_verdict(
                    write_conn,
                    ticker,
                    side,
                    ask_tenths=ctx.ask_tenths,
                    commence_ms=ctx.commence_ms,
                    config=config,
                    now_ms=now,
                )
                if cached is not None:
                    results.append(_row_to_response(cached, now_ms=now))
                    continue

                # Checked BEFORE writing anything, the same order
                # `send_scout_desk` uses: a leg the day cannot afford answers
                # immediately and spends nothing. Verdicts still in flight --
                # this request's earlier legs included, same connection --
                # count at an estimate, because their tokens and searches
                # are recorded only when they settle (#156).
                in_flight = _running_verdicts(write_conn, now)
                reason = budget.refusal_reason(
                    1,
                    now,
                    searches_worst_case=LEG_VERDICT_MAX_SEARCHES * (1 + in_flight),
                    reserved_tokens=LEG_VERDICT_TOKEN_RESERVATION * in_flight,
                )
                if reason is not None:
                    results.append(
                        _refusal_item(
                            ticker, side, _budget_refusal_message(budget, now)
                        )
                    )
                    continue

                row_id = insert_running_row(
                    write_conn,
                    ctx,
                    card_key=request.card_key,
                    model=agent_config.model,
                    trigger=request.trigger,
                    now_ms=now,
                )
                asyncio.create_task(
                    _run_leg_verdict(app_config.db_path, row_id, agent_config, ctx)
                )
                results.append(
                    {
                        "ticker": ticker,
                        "side": side,
                        "state": "pending",
                        "id": row_id,
                        "verdict": None,
                        "reason": None,
                        "ask_display_at_verdict": ctx.ask_display,
                        "age_ms": 0,
                        "refusal_reason": None,
                    }
                )
        finally:
            write_conn.close()
        return {"legs": results}

    @app.get("/api/leg-verdicts")
    def get_leg_verdicts(
        leg: list[str] = Query(default=[]), conn=Depends(get_conn)
    ) -> dict:
        """The newest verdict for each `leg=TICKER:side` pair, or `"none"`.

        Read-only: spends nothing, convenes nothing. `leg` is repeated once
        per requested leg (`?leg=T1:yes&leg=T2:no`); a value that does not
        parse as `TICKER:SIDE` with `side` in `{yes, no}` is 422 rather than
        silently dropped, the same "no guessing" rule the store applies to
        every other unreadable field.
        """
        parsed: list[tuple[str, str]] = []
        for raw in leg:
            ticker, sep, side = raw.rpartition(":")
            if not sep or side not in ("yes", "no") or not ticker:
                raise HTTPException(
                    status_code=422,
                    detail=f"{raw!r} is not TICKER:yes or TICKER:no.",
                )
            parsed.append((ticker, side))
        return {"legs": read_verdicts(conn, parsed, now_ms=db.now_ms())}
