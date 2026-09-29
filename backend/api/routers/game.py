"""`/api/game/*`: the same-game parlay builder (#202).

Same `register()` shape as every module here (`routers/__init__.py`); the
logic lives in `backend/game_builder.py` and this file is only the wire.

`GET .../legs` reads the venue (the collection list, then each event's
markets) and the desk's own consensus, and writes nothing. `POST .../mint`
creates a real market on the exchange -- no money moves, it is what the
Kalshi app does when anyone ticks legs -- so it is auth-gated like every
mutating route and records a `parlay_lookups` row for every attempt that
reaches the venue.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from ...config import AppConfig, ConfigError, StalenessConfig
from ...game_builder import list_game_legs, mint_game_combo
from ...parlays import LookupRefused
from ...store import db


class GameMintLeg(BaseModel):
    """One ticked leg. Side is validated in words by the builder, not here:
    a pydantic 422 is a list of machine paths, and this is read by a person."""

    market_ticker: str
    event_ticker: str
    side: str


class GameMintRequest(BaseModel):
    """The ticked legs, and nothing else. Fewer than two is refused in words
    by the builder (with no venue call), not by a length constraint here."""

    legs: list[GameMintLeg]


def register(
    app: FastAPI,
    *,
    app_config: AppConfig,
    staleness: StalenessConfig,
    combo_api,
    get_conn,
    require_auth,
) -> None:
    """Attach the two same-game handlers."""

    def _api():
        try:
            return combo_api()
        except ConfigError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"no Kalshi credentials on this instance: {exc}",
            ) from exc

    @app.get("/api/game/{event_ticker}/legs")
    async def game_legs(event_ticker: str, conn=Depends(get_conn)) -> dict:
        """Every leg Kalshi offers on one game, each with the desk's own
        consensus chance or `null` and a reason.

        **The order is fixed and never a function of any chance or price**
        (ADR 0071). **No combined chance is returned**: the desk has no model
        of how same-game legs move together.
        """
        api = _api()
        try:
            return await list_game_legs(
                conn,
                game_event_ticker=event_ticker,
                now_ms=db.now_ms(),
                max_odds_age_ms=staleness.max_odds_age_s * 1000,
                api=api,
            )
        except LookupRefused as exc:
            raise HTTPException(
                status_code=exc.status_code, detail=exc.detail
            ) from exc

    @app.post(
        "/api/game/{event_ticker}/mint", dependencies=[Depends(require_auth)]
    )
    async def game_mint(event_ticker: str, request: GameMintRequest) -> dict:
        """Mint the ticked legs as one combination on Kalshi.

        Refused in words, before any venue call, on fewer than two legs, two
        legs on one event that allows one, both sides of one market, or a leg
        that is not on this game. Returns the minted market's ticker for
        `<AskTheMarket>`; it prices nothing and commits no money.
        """
        api = _api()
        # Its own writable connection, like every mutating route: `get_conn`
        # is read-only and this records a `parlay_lookups` row.
        write_conn = db.open_db(app_config.db_path)
        try:
            return await mint_game_combo(
                write_conn,
                game_event_ticker=event_ticker,
                legs=[leg.model_dump() for leg in request.legs],
                now_ms=db.now_ms(),
                api=api,
            )
        except LookupRefused as exc:
            raise HTTPException(
                status_code=exc.status_code, detail=exc.detail
            ) from exc
        finally:
            write_conn.close()
