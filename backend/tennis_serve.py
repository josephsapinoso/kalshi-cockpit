"""The runner's half of a tennis check: serve one `KIND_TENNIS` request (#445).

#439 design §2-§4, §6, §7. The API files the request (it opens the database
read-only); the runner, the one odds spender, serves it here and writes
`tennis_links` / `tennis_snapshots`. The next check reads those two tables.

Per request, in order, stopping at the first refusal:

1. `classify_series` on the leg's market (free; the check already did this,
   and it is repeated because a hand-edited inbox must not reach a buy).
2. `GET /events/{ticker}?with_nested_markets=true` on Kalshi (free, public),
   read by `read_event`.
3. The tour's active Odds API keys and each key's event list (both free), and
   `choose_link`: exactly one match by name, inside +/-36 h.
4. If that match has started by the book's clock, stop (free).
5. One per-event `h2h` buy, 1 credit, through `OddsClient.fetch_props` -- the
   same budget check, `api_credits` row (`trigger = 'manual'`) and parser as
   every other per-event buy -- stored in `tennis_snapshots` ONLY.

A free refusal stands `FREE_REFUSAL_TTL_MS`; a refusal after the paid call
stands `PAID_REFUSAL_TTL_MS`, so a match with no two-sided book is not re-bought
every two minutes.

What this does not establish
----------------------------
* That an empty answer from the paid call was an empty book rather than a
  transport failure. `fetch_props` logs and skips a transport error, and the
  two look the same here; both are recorded as `no_two_sided_book` for an hour,
  which is the direction that spends less.
* Anything about the chance. Devig happens when the check reads the rows
  (`backend.tennis.price_leg`); this module only decides whether a reading
  with at least one two-sided book exists.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from . import tennis
from .odds.client import MANUAL_TRIGGER, OddsAPIError, QuotaExhausted
from .odds.ondemand import KIND_TENNIS, RefreshRequest
from .store import tennis_readings as tr

logger = logging.getLogger(__name__)

#: The book's commence time has passed. The same word the check uses for a
#: started leg; the buy is not made.
GAME_STARTED = "game_started"
#: Kalshi or the odds vendor answered with an error on a free read.
READ_FAILED = "tennis_read_failed"
#: The paid call itself failed (a 4xx/5xx, which may still have billed).
ODDS_CALL_FAILED = "tennis_odds_call_failed"

H2H = ("h2h",)


@dataclass(frozen=True)
class Served:
    """What one request came to, for the runner's log line."""

    kalshi_event_ticker: str
    outcome: str            # "linked" or a refusal reason
    rows_stored: int = 0
    credits_spent: int = 0


def _refusal(
    req: RefreshRequest,
    reason: str,
    *,
    now_ms: int,
    paid: bool,
    detail: str = "",
    event: Optional[tennis.EventRead] = None,
    markets: Sequence[str] = (),
    link: Optional[tennis.LinkChoice] = None,
    sport_key: Optional[str] = None,
) -> tr.TennisLink:
    ttl = tr.PAID_REFUSAL_TTL_MS if paid else tr.FREE_REFUSAL_TTL_MS
    return _row(
        req, now_ms=now_ms, event=event, markets=markets, link=link,
        sport_key=sport_key, refusal_reason=reason, refusal_detail=detail or None,
        expires_ms=now_ms + ttl,
    )


def _row(
    req: RefreshRequest,
    *,
    now_ms: int,
    event: Optional[tennis.EventRead],
    markets: Sequence[str],
    link: Optional[tennis.LinkChoice],
    sport_key: Optional[str],
    refusal_reason: Optional[str] = None,
    refusal_detail: Optional[str] = None,
    expires_ms: Optional[int] = None,
) -> tr.TennisLink:
    players = event.players if event is not None and event.reason is None else ()
    ev = link.event if link is not None else None
    return tr.TennisLink(
        kalshi_event_ticker=req.kalshi_event_ticker or "",
        odds_event_id=(ev.get("id") if ev else None),
        sport_key=sport_key,
        market_a_ticker=markets[0] if len(markets) == 2 else None,
        player_a=players[0] if players else None,
        market_b_ticker=markets[1] if len(markets) == 2 else None,
        player_b=players[1] if players else None,
        occurrence_ms=event.occurrence_ms if event is not None else None,
        commence_ms=tennis.parse_utc_ms(ev.get("commence_time")) if ev else None,
        commence_skew_ms=link.commence_skew_ms if link is not None else None,
        linked_ms=now_ms,
        refusal_reason=refusal_reason,
        refusal_detail=refusal_detail,
        expires_ms=expires_ms,
    )


async def serve_one(
    conn: sqlite3.Connection,
    req: RefreshRequest,
    *,
    kalshi: Any,
    odds: Any,
    now_ms: int,
) -> Served:
    """Serve one request and write its `tennis_links` row (and any reading)."""
    ticker = req.kalshi_event_ticker or ""

    def done(row: tr.TennisLink, *, rows: int = 0, credits: int = 0) -> Served:
        tr.write_link(conn, row)
        return Served(ticker, row.refusal_reason or "linked", rows, credits)

    series = tennis.classify_series(req.market_ticker or "")
    if series.reason is not None:
        return done(_refusal(req, series.reason, now_ms=now_ms, paid=False))

    try:
        payload = await kalshi.get(f"/events/{ticker}", with_nested_markets="true")
    except Exception as exc:  # noqa: BLE001 -- any failure is a free refusal
        logger.warning("tennis: Kalshi event read failed for %s: %s", ticker, exc)
        return done(_refusal(
            req, READ_FAILED, now_ms=now_ms, paid=False,
            detail=f"Kalshi event read: {type(exc).__name__}",
        ))
    event = tennis.read_event(payload, req.market_ticker or "")
    if event.reason is not None:
        return done(_refusal(req, event.reason, now_ms=now_ms, paid=False, detail=event.detail))
    raw = payload.get("event") if isinstance(payload, dict) else None
    markets = [m.get("ticker") for m in (raw or {}).get("markets") or []]

    try:
        keys = await odds.fetch_active_sport_keys(
            now_ms=now_ms, prefix=f"tennis_{series.tier}_"
        )
        candidates: list[dict] = []
        key_of: dict[str, str] = {}
        for key in keys:
            for e in await odds.fetch_events(key, now_ms=now_ms):
                candidates.append(e)
                if isinstance(e.get("id"), str):
                    key_of[e["id"]] = key
    except QuotaExhausted:
        raise
    except (OddsAPIError, Exception) as exc:  # noqa: BLE001
        logger.warning("tennis: odds event list failed for %s: %s", ticker, exc)
        return done(_refusal(
            req, READ_FAILED, now_ms=now_ms, paid=False, event=event, markets=markets,
            detail=f"odds event list: {type(exc).__name__}",
        ))

    link = tennis.choose_link(event.players, event.occurrence_ms, candidates)
    if link.reason is not None:
        return done(_refusal(
            req, link.reason, now_ms=now_ms, paid=False, event=event, markets=markets,
            link=link, detail=f"{link.candidates} candidates across {len(keys)} keys",
        ))
    odds_event_id = link.event["id"]
    sport_key = key_of.get(odds_event_id)
    commence = tennis.parse_utc_ms(link.event.get("commence_time"))
    if commence is not None and commence <= now_ms:
        return done(_refusal(
            req, GAME_STARTED, now_ms=now_ms, paid=False, event=event,
            markets=markets, link=link, sport_key=sport_key,
        ))

    cost = req.estimated_credits
    refusal = odds.budget.refusal_reason(cost, now_ms)
    if refusal is not None:
        # The day cannot afford it. No row: this is not a fact about the
        # match, and the next check may try again once the day allows.
        logger.info("tennis: budget refuses %s: %s", ticker, refusal)
        return Served(ticker, "budget_refused")

    try:
        quotes = await odds.fetch_props(
            sport_key, [odds_event_id], now_ms=now_ms, markets=list(H2H),
            trigger=MANUAL_TRIGGER,
        )
    except QuotaExhausted:
        raise
    except OddsAPIError as exc:
        return done(_refusal(
            req, ODDS_CALL_FAILED, now_ms=now_ms, paid=True, event=event,
            markets=markets, link=link, sport_key=sport_key,
            detail=f"odds API answered {exc}",
        ), credits=cost)

    stored = tr.write_snapshots(conn, quotes)
    rows = tr.latest_reading_rows(conn, odds_event_id) if stored else []
    reading = tennis.price_leg(rows, event.players, "yes", event.players[0])
    if reading.reason == tennis.NO_TWO_SIDED_BOOK or not stored:
        return done(_refusal(
            req, tennis.NO_TWO_SIDED_BOOK, now_ms=now_ms, paid=True, event=event,
            markets=markets, link=link, sport_key=sport_key,
            detail=f"{stored} rows stored",
        ), rows=stored, credits=cost)
    return done(
        _row(req, now_ms=now_ms, event=event, markets=markets, link=link,
             sport_key=sport_key),
        rows=stored, credits=cost,
    )


async def serve(
    conn: sqlite3.Connection,
    requests: Sequence[RefreshRequest],
    *,
    kalshi: Any,
    odds: Any,
    now_ms: int,
) -> list[Served]:
    """Serve each tennis request once per match, oldest first.

    One failure does not stop the rest, except `QuotaExhausted`, which every
    other spender also lets reach the loop.
    """
    out: list[Served] = []
    seen: set[str] = set()
    for req in requests:
        if req.kind != KIND_TENNIS or not req.kalshi_event_ticker:
            continue
        if req.kalshi_event_ticker in seen:
            continue
        seen.add(req.kalshi_event_ticker)
        out.append(await serve_one(conn, req, kalshi=kalshi, odds=odds, now_ms=now_ms))
    return out
