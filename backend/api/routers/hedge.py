"""`/api/hedge`: the parlays Joe already holds, and what a hedge would do.

Moved verbatim from `backend/api/routes.py` on 2026-09-04; see
`backend/api/routers/__init__.py` for the `register()` shape and why. ADR 0078
is the design: no model, no tokens, no credits, no `recommendations` row --
`gate.py` may never read `parlay_positions`.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException

from ... import hedge as held_parlays
from ...config import AppConfig, StalenessConfig
from ...store import db
from ..schemas import ClosePositionRequest, HeldPositionRequest, ResolveLegRequest


def register(
    app: FastAPI,
    *,
    app_config: AppConfig,
    staleness: StalenessConfig,
    live_quotes,
    get_conn,
    require_auth,
) -> None:
    """Attach the four hedge handlers to `app`, in their original order."""

    @app.get("/api/hedge")
    async def hedge_positions(conn=Depends(get_conn)) -> dict:
        """Every parlay Joe holds, its legs' live prices, and what a hedge does.

        Unauthenticated like `/api/parlays` and for the same reason: it reads,
        it recommends nothing, and it is already behind `middleware.ts`. It
        reaches the venue for a live book per watched ticker -- Kalshi is
        unmetered, so this spends no credits and touches no LLM.

        In-play by construction, and that is the point: a hedge is only ever
        wanted while the game is running. Nothing here writes a
        `recommendations` row, so `runner`'s `dropped_game_started` drop and
        ADR 0006's evidence guard are untouched (ADR 0078 §4).
        """
        now = db.now_ms()
        # No credential guard here, deliberately. `LiveQuoteSource` builds its
        # client lazily, so an instance holding no Kalshi key fails inside
        # `fetch` rather than here -- and `hedge.read_books` already treats
        # every such failure as "this leg has no price this pass", which the
        # payload has words for. A second guard at this level would be a
        # branch no test could reach.
        return await held_parlays.build_payload(
            conn,
            now_ms=now,
            max_quote_age_ms=staleness.max_kalshi_quote_age_s * 1000,
            spendable_tenths=db.latest_balance_tenths(conn),
            fetch_quote=live_quotes().fetch,
        )

    @app.post("/api/hedge/positions", dependencies=[Depends(require_auth)])
    def record_held_position(request: HeldPositionRequest) -> dict:
        """Record a parlay Joe already holds.

        Auth-gated because it writes. It moves no money and reaches no venue --
        this is a note about a bet that has already been placed somewhere else.

        Money arrives in cents and is converted to tenths **here**, once, at
        the boundary. A ticket whose figures cannot carry the arithmetic is
        refused now, while he can still correct them, rather than in the sixth
        inning when the alert would have used them.
        """
        write_conn = db.open_db(app_config.db_path)
        try:
            position_id = held_parlays.record_position(
                write_conn,
                now_ms=db.now_ms(),
                source=request.source,
                label=request.label,
                stake_tenths=request.stake_cents * 10,
                return_tenths=request.return_cents * 10,
                legs=[leg.model_dump() for leg in request.legs],
                book=request.book,
                placed_ms=request.placed_ms,
                combo_ticker=request.combo_ticker,
                parlay_lookup_id=request.parlay_lookup_id,
                note=request.note,
            )
        except held_parlays.PositionRefused as exc:
            raise HTTPException(
                status_code=422, detail=exc.refusal.detail
            ) from exc
        finally:
            write_conn.close()
        return {"position_id": position_id, "status": "recorded"}

    @app.post(
        "/api/hedge/legs/{leg_id}/resolve", dependencies=[Depends(require_auth)]
    )
    def resolve_held_leg(leg_id: int, request: ResolveLegRequest) -> dict:
        """Joe's word on a leg the venue cannot settle for him.

        Required rather than convenient: a sportsbook leg has no Kalshi ticker,
        so `kalshi_markets.result` can never reach it, and without this route
        the lock case is unreachable for exactly the slips he asked about.

        `resolved_source` is fixed at `manual` here and is never taken from the
        request. The two sources are not equally good evidence and the column
        exists to keep them apart; a client that could claim `venue` would erase
        the distinction the moment somebody found it convenient.
        """
        write_conn = db.open_db(app_config.db_path)
        try:
            moved = held_parlays.resolve_leg(
                write_conn,
                leg_id=leg_id,
                outcome=request.outcome,
                now_ms=db.now_ms(),
                source="manual",
            )
        finally:
            write_conn.close()
        if not moved:
            # Either there is no such leg or it has already settled. Both are
            # "this write changed nothing", and 409 says that without claiming
            # to know which -- the check read one row count and can separate
            # neither (ADR 0072 Decision 1).
            raise HTTPException(
                status_code=409,
                detail=(
                    "That leg did not move. It has either already been settled "
                    "or it does not exist — a settled leg is a fact and is not "
                    "rewritten."
                ),
            )
        return {"leg_id": leg_id, "outcome": request.outcome, "source": "manual"}

    @app.post(
        "/api/hedge/positions/{position_id}/close",
        dependencies=[Depends(require_auth)],
    )
    def close_held_position(
        position_id: int, request: ClosePositionRequest
    ) -> dict:
        """Stop watching a ticket. Nothing is deleted; the row keeps its history."""
        write_conn = db.open_db(app_config.db_path)
        try:
            moved = held_parlays.close_position(
                write_conn,
                position_id=position_id,
                now_ms=db.now_ms(),
                status=request.status,
            )
        finally:
            write_conn.close()
        if not moved:
            raise HTTPException(
                status_code=409,
                detail=(
                    "That ticket did not move. It is either already closed or "
                    "it does not exist."
                ),
            )
        return {"position_id": position_id, "status": request.status}
