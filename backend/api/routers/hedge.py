"""`/api/hedge`: the parlays Joe already holds, and what a hedge would do.

Moved verbatim from `backend/api/routes.py` on 2026-09-04; see
`backend/api/routers/__init__.py` for the `register()` shape and why. ADR 0078
is the design: no model, no tokens, no credits, no `recommendations` row --
`gate.py` may never read `parlay_positions`.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from ... import hedge as held_parlays
from ...combo_rfq import ask_makers_to_buy_back
from ...config import AppConfig, ConfigError, StalenessConfig
from ...parlays import LookupRefused
from ...store import db
from ..schemas import ClosePositionRequest, HeldPositionRequest, ResolveLegRequest


class AdoptComboRequest(BaseModel):
    """`POST /api/hedge/positions/adopt`'s body: the ticker, nothing else.

    Everything the position needs beyond that -- contracts, exposure, legs --
    comes from the venue's own read (`held_parlays.adopt_venue_combo`), never
    from the request.
    """

    ticker: str = Field(min_length=1, max_length=120)


def register(
    app: FastAPI,
    *,
    app_config: AppConfig,
    staleness: StalenessConfig,
    live_quotes,
    get_conn,
    require_auth,
    read_combo_book=None,
    combo_api=None,
) -> None:
    """Attach the five hedge handlers to `app`, in their original order.

    `read_combo_book` is threaded straight through to `held_parlays.
    build_payload` (#95) and defaults to `None`, same as there -- this
    router does not decide what it is, only carries it. Wiring the real
    reader (`KalshiRestClient.orderbook`, built lazily by `combo_api()`) is
    #128, at the call site below main owns (`backend/api/routes.py`), not
    here.

    `combo_api` is `create_app`'s shared Kalshi REST client factory -- the
    SAME client, and so the same rate limiter, the armed order path and the
    buy-side RFQ route use (#96 defect 3: an RFQ write bills the shard-1
    write budget shared with orders, so it goes through the one limiter
    rather than a second). `None` only in tests that build this router
    alone; the sell-quote route then answers 503.
    """

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
            read_combo_book=read_combo_book,
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
        """Stop watching a ticket. Nothing is deleted; the row keeps its history.

        `source='manual'`: this is Joe's tap, and the row says so. The other
        writer is the watcher's `close_settled_combinations` (`'venue'`).
        """
        write_conn = db.open_db(app_config.db_path)
        try:
            moved = held_parlays.close_position(
                write_conn,
                position_id=position_id,
                now_ms=db.now_ms(),
                status=request.status,
                source="manual",
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

    @app.post(
        "/api/hedge/positions/{position_id}/sell-quote",
        dependencies=[Depends(require_auth)],
    )
    async def ask_what_makers_would_pay(position_id: int) -> dict:
        """Ask Kalshi's makers what they would pay for a combination Joe holds.

        Joe's answer (A) to #63: both exit prices on `/hedge`, read-only, no
        selling from the desk. This is the RFQ one (#96); the public book's
        is on every `/api/hedge` read (#95).

        **A tap, never the loop** (#96 defect 2): `hedge_watch` runs
        `build_payload` every 60 s unattended, and an RFQ fired from there
        would be ~1,440 a day on the shard-1 write budget the order path
        shares. Auth-gated and outward-facing: it creates a real RFQ, and
        withdraws it before answering. **No money moves** -- nothing on this
        route accepts, and the accept route refuses an exit ask's quotes.

        The body is empty on purpose. The position id is the whole request;
        the ticker, the size and the legs come from our row and the venue.
        """
        if combo_api is None:
            raise HTTPException(
                status_code=503,
                detail="This instance cannot reach Kalshi. Nothing was asked.",
            )
        try:
            api = combo_api()
        except ConfigError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"no Kalshi credentials on this instance: {exc}",
            ) from exc
        write_conn = db.open_db(app_config.db_path)
        try:
            return await ask_makers_to_buy_back(
                write_conn,
                position_id=position_id,
                now_ms=db.now_ms(),
                api=api,
            )
        except LookupRefused as exc:
            raise HTTPException(
                status_code=exc.status_code, detail=exc.detail
            ) from exc
        finally:
            write_conn.close()

    @app.post(
        "/api/hedge/positions/adopt", dependencies=[Depends(require_auth)]
    )
    async def adopt_venue_combo(request: AdoptComboRequest) -> dict:
        """Put a KXMVE combination the venue shows Joe holds under `/hedge`'s
        watch, in one tap. #148.

        `unrecorded_at_venue` (served on every `/api/hedge` read) tells him
        "Record it below" for a combination like this; `RecordParlay.tsx` has
        no field for a combination ticker, so that instruction could not be
        followed until this route existed. The body is the ticker alone --
        contracts, exposure and the legs all come from the venue's own read
        (`held_parlays.adopt_venue_combo`), never from the request.

        Reaches the venue once, for the market's legs (`GET
        /markets/{ticker}`), through the same shared Kalshi client the order
        path and the buy/sell RFQ routes use. Refuses (4xx, named reason)
        before that call for everything checkable from this row's own
        tables: a non-KXMVE ticker, a ticker outside the latest complete
        positions poll, and a ticker an open position already claims.
        """
        if combo_api is None:
            raise HTTPException(
                status_code=503,
                detail="This instance cannot reach Kalshi. Nothing was adopted.",
            )
        try:
            api = combo_api()
        except ConfigError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"no Kalshi credentials on this instance: {exc}",
            ) from exc
        write_conn = db.open_db(app_config.db_path)
        try:
            position_id = await held_parlays.adopt_venue_combo(
                write_conn,
                api=api,
                ticker=request.ticker,
                now_ms=db.now_ms(),
            )
        except LookupRefused as exc:
            raise HTTPException(
                status_code=exc.status_code, detail=exc.detail
            ) from exc
        finally:
            write_conn.close()
        return {"position_id": position_id, "status": "recorded"}
