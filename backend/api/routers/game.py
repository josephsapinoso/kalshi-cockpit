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

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from ...agents.base import AgentConfig, build_client
from ...agents.budget import AgentBudget
from ...agents.game_script import (
    CALL_FAILED_PREFIX,
    MAX_REQUESTED_LEGS,
    MIN_REQUESTED_LEGS,
    build_card,
    recheck_card,
)
from ...config import (
    AppConfig,
    ConfigError,
    StalenessConfig,
    configured_day_start_utc_hour,
)
from ...core.leg_words import no_words_for
from ...core.prices import format_price
from ...game_script_watch import is_unattended_refusal
from ...game_builder import (
    _read_event_markets,
    consensus_for_legs,
    game_context,
    list_game_legs,
    mint_game_combo,
    parse_game_ticker,
)
from ...kalshi.discovery import IN_SCOPE_LEAGUES
from ...kalshi.orderbook import OrderBook
from ...notify.credit_alert import screen_sentence
from ...odds.timing import day_start_ms
from ...parlays import LookupRefused, _commence_ms_for_tickers
from ...store import db, game_script_cards

logger = logging.getLogger(__name__)


#: Card builds run one at a time on the process: two taps at once must not both
#: pay (the burst that ran leg verdicts to 1,120,442 tokens on 2026-09-25).
#: Held from the dedupe check through the store write.
_CARD_BUILD_LOCK = asyncio.Lock()


class NoKickoffOnRecord(Exception):
    """The desk has no kickoff for this game, so no card can be filed. Nothing
    was spent."""


async def build_card_for_game(
    db_path,
    event_ticker: str,
    *,
    api,
    agent_config: AgentConfig,
    max_odds_age_ms: int,
    client=None,
    leg_count: Optional[int] = None,
) -> dict:
    """Build one game's card, or return the one it already has (#215, #217).

    **The one build path.** Joe's tap (`POST /api/game/{event}/card`) and the
    unattended watcher (`backend/game_script_watch.py`) both come through
    here, so both take `_CARD_BUILD_LOCK` and both reuse a `built` or
    `skipped` card rather than paying for a second. The lock is per process:
    the watcher runs in the loop process and the tap in the API process, so a
    tap and a watcher build of the SAME game in the same minute can both pay.
    The watcher builds at T-24h and the reuse check catches every later tap,
    so that overlap is one card's cost at worst, and it is stated, not fixed.

    `client` is for tests. `None`, what production passes, means this
    module's own literal `build_client(agent_config)`, the allowlisted site.

    `leg_count` (#379, Joe's tap only): the exact size he picked; `None`, what
    the watcher passes, keeps the 2-3 leg card.

    Raises `LookupRefused` (not a game ticker, or the venue refused the
    listing) and `NoKickoffOnRecord`; neither spends anything.
    """
    parse_game_ticker(event_ticker)
    async with _CARD_BUILD_LOCK:
        write_conn = db.open_db(db_path)
        try:
            now = db.now_ms()
            held = game_script_cards.latest_for_game(
                write_conn, event_ticker.strip().upper(),
                statuses=("built", "skipped"),
            )
            if held is not None:
                return {"card": held, "reused": True}
            listing = await list_game_legs(
                write_conn,
                game_event_ticker=event_ticker,
                now_ms=now,
                max_odds_age_ms=max_odds_age_ms,
                api=api,
            )
            game_market = listing.get("game_market_ticker")
            kickoff_ms = (
                _commence_ms_for_tickers(write_conn, [game_market]).get(game_market)
                if game_market else None
            )
            if kickoff_ms is None:
                raise NoKickoffOnRecord(
                    "The desk has no kickoff on record for this game, so a "
                    "card cannot be filed against it. Nothing was spent."
                )
            game_title = next(
                (
                    leg["title"]
                    for group in listing["groups"]
                    if group["kind"] == "GAME"
                    for leg in group["legs"]
                ),
                listing["game_event_ticker"],
            )
            budget = AgentBudget.from_config(write_conn, agent_config)
            result = await build_card(
                write_conn,
                client if client is not None else build_client(agent_config),
                agent_config,
                budget,
                game_event_ticker=listing["game_event_ticker"],
                sport_key=game_script_cards.sport_key_for(listing["game_event_ticker"]),
                kickoff_ms=kickoff_ms,
                game_title=game_title,
                kickoff_iso=datetime.fromtimestamp(
                    kickoff_ms / 1000, tz=timezone.utc
                ).strftime("%Y-%m-%dT%H:%MZ"),
                listing=listing,
                now_ms=now,
                leg_count=leg_count,
            )
            return {
                "card": game_script_cards.card_by_id(write_conn, result.card_id),
                "reused": False,
            }
        finally:
            write_conn.close()



async def recheck_card_for_game(
    db_path, card: dict, *, agent_config: AgentConfig, client=None
) -> str:
    """The T-2h drop-if re-check for one card (#289), called by the watcher
    only, never by a route: Joe answered (A) to #270, games he opened, so it
    is decided in `game_script_watch.decide_rechecks`, not tapped.

    `client` is for tests; `None` is this module's literal `build_client`.
    One metered call with one search, or a budget refusal that spends nothing.
    """
    write_conn = db.open_db(db_path)
    try:
        now = db.now_ms()
        return await recheck_card(
            write_conn,
            client if client is not None else build_client(agent_config),
            agent_config,
            AgentBudget.from_config(write_conn, agent_config),
            card=card,
            game_title=card["game_event_ticker"],
            kickoff_iso=datetime.fromtimestamp(
                card["kickoff_ms"] / 1000, tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%MZ"),
            now_ms=now,
        )
    finally:
        write_conn.close()

#: The line an NFL card carries about news that lands after it is built. The
#: 90 minutes is the one lineup time this repo cites (ADR 0190 section 6).
INACTIVES_LINE = (
    "Inactives come out 90 minutes before kickoff and are not covered."
)

#: NHL: the starting goalie is confirmed around warmups, not at a fixed
#: clock time before the game (town hall 2026-10-02, #284).
NHL_GOALIE_LINE = (
    "Starting goalies are confirmed around warmups, not at a fixed time, and "
    "are not covered."
)

#: Every other sport: no confirmation time is cited anywhere in this repo, so
#: none is invented (#284).
NO_FIXED_TIME_LINE = (
    "Lineups for this sport have no fixed confirmation time and are not "
    "covered. Check the lineup before you bet."
)


def lineup_line(sport_key: str) -> str:
    """The card's sentence about when lineups are confirmed, per sport.

    Only NFL (90 minutes before kickoff) and NHL (goalies, around warmups)
    carry a time we can cite; any other sport says it has no fixed time
    rather than borrowing the NFL's."""
    key = (sport_key or "").strip().lower()
    if key == "nfl":
        return INACTIVES_LINE
    if key == "nhl":
        return NHL_GOALIE_LINE
    return NO_FIXED_TIME_LINE

#: How many single-leg reads one list call may have in flight.
_ASK_READ_CONCURRENCY = 6


def kickoff_order(cards: list[dict]) -> list[dict]:
    """Cards in kickoff order and no other (ADR 0071). The game ticker only
    breaks a tie between two games kicking off together. **Nothing here reads
    a leg, an ask or a story**: an ordering is a claim, and the only one this
    list may make is the clock."""
    return sorted(cards, key=lambda c: (c["kickoff_ms"], c["game_event_ticker"]))


#: What the list says on a game the unattended watcher declined to build. The
#: stored reason names the dial, for the record; the screen says what to do.
#: Seen on Joe's phone 2026-10-10: every NCAAF game of a Saturday night
#: printing "AGENT_MAX_TOKENS_PER_DAY 9000000 x (1 - SCOUT_AUTO_TAP_TOKEN_SHARE
#: 0.75) = 2250000; the rest is kept for taps", hours after the watcher had
#: been switched off, with no sentence telling him the tap was his.
UNATTENDED_NO_CARD_LINE = (
    "The desk did not build this card by itself. Open the game and tap "
    "a card size (3, 5 or 8 legs) to make one."
)


#: What the list says on a game the desk holds no card row for at all: not
#: refused, not skipped -- nothing has been tried, because the watcher is off
#: (Joe's (A) to #349) and he has not tapped.
NO_ROW_NO_CARD_LINE = (
    "No card yet. Open the game and tap a card size (3, 5 or 8 legs) to make one."
)

#: The daily-ceiling sentences `AgentBudget.refusal_reason` writes start with
#: the spend and the ceiling ("2838176 of 2500000 Anthropic tokens ..."). Only
#: those lift at the day's roll; the per-pass sentence does not.
_DAILY_CEILING_SENTENCE = re.compile(r"^\d+ of \d+ ")

#: The zone Joe reads clocks in (`agents/game_script.GAME_DAY_TIME_ZONE`).
_RESET_ZONE = "America/Los_Angeles"

_HOUR_MS = 3_600_000


def budget_reset_clock(
    now_ms: int, day_start_hour: Optional[int] = None
) -> Optional[str]:
    """When the Anthropic day rolls, as Joe reads a clock ("3:00 AM PT"), or
    `None` when the hour cannot be read.

    **From the budget's own day start**, `configured_day_start_utc_hour()` --
    the one parse `AgentBudget.from_config` uses -- never a literal: the hour
    is an env dial, and a clock printed from a constant would go on being
    wrong the day it moved. `None` rather than a guess on a ConfigError."""
    from zoneinfo import ZoneInfo

    if day_start_hour is None:
        try:
            day_start_hour = configured_day_start_utc_hour()
        except ConfigError:
            return None
    reset = datetime.fromtimestamp(
        (day_start_ms(now_ms, hour=day_start_hour) + 24 * _HOUR_MS) / 1000,
        ZoneInfo(_RESET_ZONE),
    )
    return reset.strftime("%I:%M %p").lstrip("0") + " PT"


#: Which daily cap a `refusal_reason` sentence names, in the words the screen
#: uses for it. Matched on the sentence's own noun, in the order
#: `AgentBudget.refusal_reason` writes them. The stored sentence names the
#: dial for the record; this one never does (lesson 2026-10-10).
_CAP_PHRASES = (
    ("Anthropic tokens", "token"),
    ("web searches", "web-search"),
    ("Anthropic calls", "call"),
)

PER_PASS_REFUSAL_LINE = (
    "That asked the scouts for more at once than they are allowed in one go. "
    "Try again with fewer."
)


def plain_budget_refusal(
    reason: str,
    now_ms: int,
    day_start_hour: Optional[int] = None,
    *,
    stored_ms: Optional[int] = None,
) -> str:
    """The screen's sentence for an `AgentBudget.refusal_reason`: which daily
    cap refused ("token", "web-search" or "call" allowance) and when the day
    resets in Pacific time, in plain words and never a config name.

    **Reuses `budget_reset_clock`** (#358), so the clock comes from the
    budget's own day start. The per-pass ceiling lifts with a smaller batch,
    not at the roll, so it carries no clock. `stored_ms`, for a refusal read
    back from a row, drops the clock when the refusal belongs to an earlier
    budget day: "back at 3:00 AM" about yesterday's refusal would be wrong.
    The reason stored for the record is untouched by this function."""
    if reason.startswith("one pass may make"):
        return PER_PASS_REFUSAL_LINE
    cap = next((word for noun, word in _CAP_PHRASES if noun in reason), None)
    line = (
        f"The scouts have used today's {cap} allowance."
        if cap
        else "The scouts have used today's allowance."
    )
    hour = day_start_hour
    if hour is None:
        try:
            hour = configured_day_start_utc_hour()
        except ConfigError:
            return line
    if stored_ms is not None and stored_ms < day_start_ms(now_ms, hour=hour):
        return line
    clock = budget_reset_clock(now_ms, hour)
    if clock is None:
        return line
    remaining_ms = day_start_ms(now_ms, hour=hour) + 24 * _HOUR_MS - now_ms
    if remaining_ms < _HOUR_MS:
        when = "in under an hour"
    else:
        when = f"in about {-(-remaining_ms // _HOUR_MS)} hours"
    return f"{line} They're back at {clock}, {when}."


def no_card_line(card: dict, now_ms: Optional[int] = None) -> Optional[str]:
    """What a game with no built card says, in words, or `None` on a built one.

    A skipped or refused game is listed with this sentence, never dropped and
    never an empty row (#216). A refusal the unattended watcher wrote is told
    apart from a tap the daily ceiling refused: the first says the build is
    his to tap, the second repeats the budget's own plain sentence and, when
    that sentence is a daily ceiling, says when the day resets in Pacific time
    -- the one fact that sentence leaves out."""
    status = card["status"]
    if status == "built":
        return None
    if status == "none":
        return NO_ROW_NO_CARD_LINE
    reason = (card.get("reason") or "").strip() or "no reason was recorded"
    if status == "refused_budget":
        if is_unattended_refusal(reason):
            return UNATTENDED_NO_CARD_LINE
        line = f"No card today: {reason}"
        if _DAILY_CEILING_SENTENCE.match(reason):
            clock = budget_reset_clock(
                now_ms if now_ms is not None else db.now_ms()
            )
            if clock is not None:
                line += f". The day resets at {clock}."
        return line
    if status == "refused_invalid" and reason.startswith(CALL_FAILED_PREFIX):
        credit = screen_sentence(reason)
        if credit is not None:
            return f"No card yet: {credit} It will build once it's topped up."
        # A machine failure, retried on a later pass (#309): not the scout's
        # judgement, so never "No clean story".
        return f"No card yet: {reason}; it will be retried"
    return f"No clean story: {reason}"


#: The window the list reads for games with no card row.
TONIGHT_MS = 24 * _HOUR_MS

#: Kalshi's `occurrence_datetime` can sit hours off the sportsbook's kickoff
#: (CLAUDE.md: three hours late), so the index seek on the Kalshi clock is cut
#: wider than the window and the exact test is on the sportsbook's own
#: `odds_fixtures.commence_ms`.
_KALSHI_CLOCK_MARGIN_MS = 6 * _HOUR_MS

#: Tonight's game events, bounded and indexed: a seek on
#: `kalshi_events(commence_ms)`, a seek on `event_links` by its leading
#: `kalshi_event_ticker`, a primary-key seek on `odds_fixtures`. **Never a read
#: of `odds_snapshots` or `kalshi_quotes`** (the shape `parlays.py`
#: `commence_for_tickers_sql` was fixed to in 2026-08/09). Discovery rejects an
#: event with no `occurrence_datetime`, so every stored event has the clock the
#: seek uses. `tests/test_game_script_card_screen.py` pins the plan.
TONIGHTS_GAMES_SQL = (
    "SELECT e.event_ticker AS game_event_ticker, f.sport_key AS sport_key, "
    "       f.commence_ms AS commence_ms "
    "FROM kalshi_events e "
    "JOIN event_links l ON l.kalshi_event_ticker = e.event_ticker "
    "JOIN odds_fixtures f ON f.odds_event_id = l.odds_event_id "
    "WHERE e.commence_ms >= ? AND e.commence_ms <= ? "
    "  AND f.commence_ms > ? AND f.commence_ms <= ? "
    "  AND e.event_ticker LIKE 'KX%GAME-%'"
)


def tonights_games_params(now_ms: int) -> tuple:
    return (
        now_ms - _KALSHI_CLOCK_MARGIN_MS,
        now_ms + TONIGHT_MS + _KALSHI_CLOCK_MARGIN_MS,
        now_ms,
        now_ms + TONIGHT_MS,
    )


def tonights_games(conn, now_ms: int) -> dict[str, dict]:
    """In-scope game events kicking off within 24 h, from what the desk
    already holds: `{game_event_ticker: {kickoff_ms, sport_key}}`. A game
    linked to more than one fixture keeps the earliest kickoff."""
    sports = set(IN_SCOPE_LEAGUES.values())
    out: dict[str, dict] = {}
    for row in conn.execute(TONIGHTS_GAMES_SQL, tonights_games_params(now_ms)):
        ticker = row["game_event_ticker"]
        if row["sport_key"] not in sports:
            continue
        kickoff = int(row["commence_ms"])
        if ticker not in out or kickoff < out[ticker]["kickoff_ms"]:
            out[ticker] = {
                "kickoff_ms": kickoff,
                "sport_key": game_script_cards.sport_key_for(ticker),
            }
    return out


def no_row_card(game_event_ticker: str, info: dict) -> dict:
    """The list entry for a game nothing has been tried on: the fields a
    stored card carries, `status: "none"`, no legs, no story."""
    return {
        "id": None,
        "game_event_ticker": game_event_ticker,
        "sport_key": info["sport_key"],
        "kickoff_ms": info["kickoff_ms"],
        "built_ms": None,
        "status": "none",
        "story": None,
        "drop_if": None,
        "reason": None,
        "combo_ticker": None,
        "legs": [],
        "dropped_legs": [],
        "sources": None,
        "ticket_needs": None,
    }


def at_build_view(stored: Optional[dict]) -> Optional[dict]:
    """A leg's frozen `at_build` (#283) with its price worded, or `None` for a
    card built before that freeze existed (never an invented zero). The number
    stays an integer tenth; `ask_display` is the same figure in cents."""
    if not isinstance(stored, dict):
        return None
    ask = stored.get("ask_tenths")
    return {
        "ask_tenths": ask,
        "ask_display": format_price(ask) if ask is not None else None,
        "size": stored.get("size"),
        "read_ms": stored.get("read_ms"),
    }


async def _read_leg_asks(
    api, legs: list[dict], *, now_ms: int, game_event_ticker: str = ""
) -> list[dict]:
    """Kalshi's own single-leg ask for each card leg, read now.

    One `markets_for_event` per distinct event (the title) and one order book
    per leg (the ask, derived from the opposing bid, never quoted). A read
    that fails is `ask_tenths: None` with the reason in words -- never `0`,
    and it never takes the card down. **No number is combined**: each ask is
    one leg's, and only the makers' RFQ quote prices the link (ADR 0189)."""
    gate = asyncio.Semaphore(_ASK_READ_CONCURRENCY)
    events = sorted({leg["event_ticker"] for leg in legs})
    reads = await asyncio.gather(*(_read_event_markets(api, e, gate) for e in events))
    markets_by_ticker: dict[str, dict] = {}
    for _event, markets, _words in reads:
        for market in markets or []:
            markets_by_ticker[str(market.get("ticker") or "")] = market

    async def one(leg: dict) -> dict:
        market = markets_by_ticker.get(leg["market_ticker"], {})
        side = leg["side"]
        out = {
            "market_ticker": leg["market_ticker"],
            "event_ticker": leg["event_ticker"],
            "side": side,
            "title": str(market.get("title") or leg["market_ticker"]),
            # Kalshi's no_sub_title repeats the YES one (#275), so a NO leg is
            # worded as its opposite; the YES side keeps Kalshi's own words.
            "side_label": (
                no_words_for(
                    series=str(leg["event_ticker"]).split("-")[0],
                    game_event_ticker=game_event_ticker,
                    yes_label=market.get("yes_sub_title"),
                )
                if side == "no"
                else market.get("yes_sub_title") or None
            ),
            "ask_tenths": None,
            "ask_display": None,
            "ask_unread_reason": None,
            # When this ask was read, and the size at it (#285). `None` until
            # a book read succeeds: an unread leg claims no read time.
            "read_ms": None,
            "size_now": None,
            # The same leg's listed ask as it stood when the card was built
            # (#283), for the "when written" figure. Per leg, never combined.
            "at_build": at_build_view(leg.get("at_build")),
        }
        try:
            async with gate:
                payload = await asyncio.wait_for(
                    api.orderbook(leg["market_ticker"], depth=10), 10.0
                )
            book = OrderBook(ticker=leg["market_ticker"])
            book.apply_snapshot(payload, None, now_ms)
            ask = book.ask_for(side)
        except Exception as exc:  # noqa: BLE001 -- one leg failing is a stated gap
            out["ask_unread_reason"] = (
                "Kalshi's book for this leg could not be read "
                f"({type(exc).__name__})."
            )
            return out
        if ask is None:
            out["ask_unread_reason"] = (
                f"Nobody is offering the {side.upper()} side on Kalshi right now."
            )
        else:
            out["ask_tenths"] = ask
            out["ask_display"] = format_price(ask)
            out["read_ms"] = now_ms
            out["size_now"] = book.depth_at_ask(side)
        return out

    return list(await asyncio.gather(*(one(leg) for leg in legs)))


class GameMintLeg(BaseModel):
    """One ticked leg. Side is validated in words by the builder, not here:
    a pydantic 422 is a list of machine paths, and this is read by a person."""

    market_ticker: str
    event_ticker: str
    side: str


class GameCardRequest(BaseModel):
    """The optional body of the card route (#379): how many legs Joe picked.
    Outside 2..8 is a 422 before anything is read or spent."""

    leg_count: Optional[int] = Field(
        default=None, ge=MIN_REQUESTED_LEGS, le=MAX_REQUESTED_LEGS
    )


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
    """Attach the same-game handlers."""

    def _api():
        try:
            return combo_api()
        except ConfigError as exc:
            # The ConfigError text is the operator's (names the variable and
            # the fix); the screen gets the state only. Full text to the log.
            logger.warning("no Kalshi credentials on this instance: %s", exc)
            raise HTTPException(
                status_code=503,
                detail="No Kalshi credentials on this instance.",
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

    @app.get("/api/game-cards")
    async def game_cards(
        game_event_ticker: Optional[str] = None, conn=Depends(get_conn)
    ) -> dict:
        """The stored game-script cards, newest per game, in KICKOFF order (#216).

        With `game_event_ticker`, that one game's latest card (or an empty
        list). Without it, every game that has not kicked off, plus every in-scope game kicking
        off within 24 h that has no card row (`status: "none"`). **Skipped and
        refused games are in the list, each with its reason in `no_card_line`**;
        a built card carries each leg's title and Kalshi's own single-leg ask,
        read now. No combined figure exists in this payload (ADR 0189), and the
        order is `kickoff_order`, never a function of anything on a card.

        Reads only, behind `middleware.ts` like `/api/hedge`: the browser holds
        a session cookie and never the bearer, so a bearer dependency here
        could not be called. It touches the venue (single-leg books) and no
        model, so it spends nothing.
        """
        now = db.now_ms()
        tonight: dict[str, dict] = {}
        if game_event_ticker is not None:
            games = [game_event_ticker.strip().upper()]
        else:
            games = [
                r[0]
                for r in conn.execute(
                    "SELECT DISTINCT game_event_ticker FROM game_script_cards "
                    "WHERE kickoff_ms >= ?",
                    (now,),
                ).fetchall()
            ]
            tonight = tonights_games(conn, now)
        cards: list[dict] = []
        for game in games:
            # A built card beats a later refusal: a refusal never replaces a
            # card Joe could use.
            card = game_script_cards.latest_for_game(
                conn, game, statuses=("built",)
            ) or game_script_cards.latest_for_game(conn, game)
            if card is not None:
                cards.append(card)
        # A game kicking off in the next 24 h with no card row at all is
        # listed too (#358): the watcher is off, so the rows it wrote at T-24h
        # stop arriving and a list of stored cards alone goes empty on a night
        # with games. A game WITH a row of any kind is skipped by the `latest_for_game` test.
        for game, info in tonight.items():
            if game_script_cards.latest_for_game(conn, game) is None:
                cards.append(no_row_card(game, info))
        cards = kickoff_order(cards)
        # The game's own name ("Game 1: Chicago C vs San Diego"), from the
        # event row discovery keeps, so the heading is not a raw ticker.
        # `None` when discovery has no title; the screen falls back.
        titles: dict = {}
        if cards:
            marks = ",".join("?" * len(cards))
            titles = {
                r[0]: r[1]
                for r in conn.execute(
                    "SELECT event_ticker, title FROM kalshi_events "
                    f"WHERE event_ticker IN ({marks})",
                    [c["game_event_ticker"] for c in cards],
                ).fetchall()
            }
        for card in cards:
            card["game_title"] = titles.get(card["game_event_ticker"]) or None

        api = None
        if any(c["status"] == "built" for c in cards):
            try:
                api = combo_api()
            except ConfigError:
                api = None
        for card in cards:
            card["no_card_line"] = no_card_line(card, now)
            card["inactives_line"] = lineup_line(card["sport_key"])
            if card["status"] != "built":
                card["legs"] = []
            elif api is None:
                card["legs"] = [
                    {
                        **leg,
                        "title": leg["market_ticker"],
                        "side_label": None,
                        "ask_tenths": None,
                        "ask_display": None,
                        "ask_unread_reason": (
                            "This instance has no Kalshi credentials, so no "
                            "ask was read."
                        ),
                        "read_ms": None,
                        "size_now": None,
                        "at_build": at_build_view(leg.get("at_build")),
                    }
                    for leg in card["legs"]
                ]
            else:
                card["legs"] = await _read_leg_asks(
                    api, card["legs"], now_ms=now,
                    game_event_ticker=card["game_event_ticker"],
                )
        # Each team's rest before the game (#293): one fixture per card, the
        # same `{home, away}` the parlay cards carry. A fact per leg, never
        # read to order or filter anything.
        for card in cards:
            rest = (
                game_context(conn, card["game_event_ticker"])["rest"]
                if card["status"] == "built" else None
            )
            for leg in card["legs"]:
                leg["rest"] = rest
        # The books' chance for each leg (#312, Joe's (A) to #311): read now
        # through the game page's own lookup, so the two cannot disagree.
        # **Served after the order is fixed and read by nothing**: the model
        # never sees it (ADR 0190 section 3), the stored row never holds it,
        # and no card is sorted, filtered or marked by it.
        for card in cards:
            if card["status"] != "built" or not card["legs"]:
                continue
            chances = consensus_for_legs(
                conn, card["legs"], now_ms=now,
                max_odds_age_ms=staleness.max_odds_age_s * 1000,
            )
            for leg, chance in zip(card["legs"], chances):
                leg["books_chance"] = chance["chance"]
                leg["books_chance_display"] = chance["chance_display"]
                leg["books_chance_reason"] = chance["unknown_reason"]
        return {"now_ms": now, "cards": cards}

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

    @app.post(
        "/api/game/{event_ticker}/card", dependencies=[Depends(require_auth)]
    )
    async def game_card(
        event_ticker: str, request: Optional[GameCardRequest] = None
    ) -> dict:
        """Build one game-script card for this game, now (#215, ADR 0190).

        One metered call through the shared `AgentBudget`; the outcome is
        always one `game_script_cards` row and the row is what comes back:
        `built`, `skipped`, `refused_budget` (the ceiling is named) or
        `refused_invalid`. The model is shown no price or chance, and a bad
        answer is refused and stored, never re-asked. Nothing is minted and no
        money moves; a 409 (no kickoff on record) spends nothing.
        """
        agent_config = AgentConfig.from_env()
        if agent_config is None:
            raise HTTPException(
                status_code=503,
                detail="No ANTHROPIC_API_KEY configured, so the game-script "
                       "scout cannot be paid. This is a configuration state, "
                       "not a refusal.",
            )
        api = _api()
        try:
            return await build_card_for_game(
                app_config.db_path,
                event_ticker,
                api=api,
                agent_config=agent_config,
                max_odds_age_ms=staleness.max_odds_age_s * 1000,
                leg_count=request.leg_count if request else None,
            )
        except LookupRefused as exc:
            raise HTTPException(
                status_code=exc.status_code, detail=exc.detail
            ) from exc
        except NoKickoffOnRecord as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
