"""The same-game parlay builder: every leg Kalshi offers on ONE game (#202).

Joe's #200 answer: build game-script (same-game) combinations, led by the
sports factors, price secondary. `/api/parlays/lookup` cannot carry that and
is not edited here, for four reasons measured at `backend/parlays.py`:
`card_key` must be one of the desk's own card shapes, every leg must already
be a pool candidate, a shared `odds_event_id` is a 409, and the joint runs
AFTER the mint, outside any `try`, and raises on same-game legs -- so the
market would be minted, the route would 500, and no `parlay_lookups` row
would be written. This module is the path beside it.

Two entry points:

- `list_game_legs` -- read-only. Every leg on the game's fixture that a
  catch-all combination collection accepts, grouped by series in a FIXED
  order (the order `SERIES_ORDER` names, then the player, then the strike,
  then the ticker). **Never by chance and never by any gap between a chance
  and a price** (ADR 0071: a per-row fact is transparency, an ordering is a
  claim). Each side of each leg carries the desk's own consensus chance, or
  `None` and a worded reason -- most props, first-half and quarter markets,
  team totals and touchdown scorers will be `None`, and they are SHOWN, not
  hidden, because the pick is made on the sports factors and the price is
  secondary.
- `mint_game_combo` -- the venue write. Refuses in words, BEFORE any venue
  call, on: fewer than two legs, two legs on one event that allows one, both
  sides of one market, a leg that is not on this game. Then mints under the
  collection the parlay desk already chooses, and writes a `parlay_lookups`
  row with `card_key = "game"` and a NULL fair joint -- exactly the row
  `POST /api/parlays/rfq` needs (`backend/combo_rfq.py:_recorded_lookup`).

**No combined chance is computed anywhere in this file, and none may be.**
The desk has no model of how same-game legs move together; a number here
would be invented. The makers' quote prices that in. The joint-probability
functions of `core.correlation` and `core.ladder` are deliberately not
imported, and `tests/test_game_builder.py` runs the mint with them stubbed to
raise.

What this does NOT establish
----------------------------
- That Kalshi will mint any particular combination. `_choose_collection`'s
  prefix fallback does not check the legs (its own docstring says why), so a
  refusal from the venue arrives as a recorded 502, not as a pre-check.
- That a market on the list is still open a minute later; the list is read
  live and cached only for the collection half.
- That the catch-all's `associated_events` is complete. Measured 2026-09-29:
  298 of 637 open catch-all combos share a fixture across legs; nobody has
  counted how many same-game combinations Kalshi would refuse.
- Anything about the price of a same-game combination. That is asked for, by
  RFQ, after the mint.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import sqlite3
from typing import Optional, Sequence

from .core.ladder import unusable_reason
from .core.leg_words import no_words_for
from .core.prices import (
    dollars_to_tenths_exact,
    format_price,
    is_valid_price,
    parse_quantity,
)
from .kalshi.combos import ComboCollection, ComboScope, echoed_legs, lookup_combo
from .kalshi.orderbook import OrderBook
from .store import game_script_cards
from .team_rest_reader import rest_for_games
from .parlay_check import (
    _leg_label,
    _missing_leg_reason,
    _percent_display,
    _reason_words,
    _titles_for,
)
from .parlays import (
    _FALLBACK_COLLECTION_PREFIXES,
    LookupRefused,
    _choose_collection,
    _collections,
    _commence_ms_for_tickers,
    _record_lookup,
    candidate_pool,
    invalidate_collections_cache,
    ladder_candidates,
)

logger = logging.getLogger(__name__)

#: The `parlay_lookups.card_key` this path writes. Not a `CARD_SHAPES` recipe:
#: the desk did not build this combination, Joe did.
CARD_KEY = "game"

#: The window the pool is read under. The widest the ladder offers, because
#: this page is opened for a game that may be days out and the pool's
#: kickoff bound is the only thing `horizon` changes.
HORIZON = "48h"

#: Series, as the suffix after the league prefix (`KXNFL` + `SPREAD`), in the
#: order the page lists them. Fixed, and deliberately not derived from any
#: price or chance. A series this list does not know sorts after it,
#: alphabetically -- never dropped.
SERIES_ORDER: tuple[str, ...] = (
    "GAME", "SPREAD", "TOTAL", "TEAMTOTAL",
    "1H", "1HSPREAD", "1HTOTAL",
    "1Q", "1QSPREAD", "1QTOTAL",
    "FIRSTTD", "FIRSTTDTEAM", "TD",
    "PASSYDS", "PASSTDS", "PASSINT", "RSHYDS", "RECYDS", "REC",
)

#: Plain words for a series, for the section heading. Kalshi's own phrasing
#: of each LEG rides on the leg; this is only what the group is called.
SERIES_LABELS: dict[str, str] = {
    "GAME": "Who wins",
    "SPREAD": "Winning margin",
    "TOTAL": "Total points",
    "TEAMTOTAL": "One team's points",
    "1H": "First half: who leads",
    "1HSPREAD": "First half: margin",
    "1HTOTAL": "First half: total points",
    "1Q": "First quarter: who leads",
    "1QSPREAD": "First quarter: margin",
    "1QTOTAL": "First quarter: total points",
    "FIRSTTD": "First touchdown scorer",
    "FIRSTTDTEAM": "Which team scores first",
    "TD": "Anytime touchdown",
    "PASSYDS": "Passing yards",
    "PASSTDS": "Passing touchdowns",
    "PASSINT": "Interceptions thrown",
    "RSHYDS": "Rushing yards",
    "RECYDS": "Receiving yards",
    "REC": "Receptions",
}

#: How many of a game's events are read at once, and how many at most. A game
#: has ~20 events on an NFL Sunday; the cap is a bound, not an expectation,
#: and a game past it is listed short WITH a stated count of what was left
#: out (`skipped_events`), never silently.
#:
#: **Why 2 (#205).** `GET /markets?event_ticker=A,B,...` does NOT batch:
#: measured 2026-09-29 with one public GET of 11 comma-joined real event
#: tickers (HTTP 200, `{"cursor":"","markets":[]}`) -- the comma list is read
#: as one literal ticker that matches nothing. So each event costs its own
#: request on `combo_api()`, the one 8-a-second client the armed order path and
#: the RFQ accept share. Two in flight is a small share of that limiter; six
#: let one page load queue ahead of an order sent at the same moment.
MARKET_READ_CONCURRENCY = 2
MAX_EVENTS_PER_GAME = 40
MARKET_READ_TIMEOUT_S = 10.0

#: The only status a market is offered under. Kalshi also returns
#: `initialized`, `inactive` and `paused` markets, which the venue refuses in a
#: combination (#205); a list of "not terminal" statuses offered them.
_OFFERED_STATUS = "active"

_GAME_TICKER = re.compile(r"^(KX[A-Z0-9]*GAME)-([A-Z0-9]+)$")
_EVENT_TICKER = re.compile(r"^(KX[A-Z0-9]+)-([A-Z0-9]+)$")

#: What the last listing of each game showed, so the mint can refuse a market
#: that was never on the page WITHOUT a venue call. Best-effort: absent or
#: stale, the mint falls back to the structural checks alone (the venue then
#: has the last word, and a refusal from it is recorded). In-process, lost on
#: restart, same lifetime as `parlays._collections_cache`.
_LISTING_TTL_MS = 30 * 60 * 1000
#: Bound on the games remembered (#205). Each entry is one game's markets and
#: the key is caller-supplied, so without a cap a crawl of game tickers grows
#: the process for good. Expired entries go first, then the oldest write.
_LISTING_MEMORY_MAX_GAMES = 64
_listing_memory: dict[str, tuple[int, dict[str, dict]]] = {}


def _remember_listing(game_event_ticker: str, now_ms: int, markets: dict) -> None:
    """Store a game's listing and evict down to `_LISTING_MEMORY_MAX_GAMES`."""
    _listing_memory.pop(game_event_ticker, None)  # re-insert = newest
    _listing_memory[game_event_ticker] = (now_ms, markets)
    for key in [
        k for k, (at_ms, _) in _listing_memory.items()
        if now_ms - at_ms > _LISTING_TTL_MS
    ]:
        del _listing_memory[key]
    while len(_listing_memory) > _LISTING_MEMORY_MAX_GAMES:
        del _listing_memory[next(iter(_listing_memory))]


def _refuse(status: int, words: str) -> LookupRefused:
    return LookupRefused(status, words)


def parse_game_ticker(event_ticker: str) -> tuple[str, str, str]:
    """`(league_prefix, series, fixture_suffix)` for a game event ticker.

    `KXNFLGAME-26SEP13ATLPIT` -> `("KXNFL", "KXNFLGAME", "26SEP13ATLPIT")`.
    Refuses anything that is not a game event: this page is per game, and a
    spread or prop ticker names one market family of it, not the game.
    """
    match = _GAME_TICKER.match((event_ticker or "").strip().upper())
    if match is None:
        raise _refuse(
            422,
            f"{event_ticker!r} is not a game's event ticker (it should look "
            "like KXNFLGAME-26SEP13ATLPIT). Nothing was read.",
        )
    series, suffix = match.group(1), match.group(2)
    return series[: -len("GAME")], series, suffix


def _kind_of(series: str, prefix: str) -> str:
    return series[len(prefix):] if series.startswith(prefix) else series


def _kind_rank(kind: str) -> tuple[int, str]:
    if kind in SERIES_ORDER:
        return (SERIES_ORDER.index(kind), "")
    return (len(SERIES_ORDER), kind)


def _is_catch_all(collection: ComboCollection) -> bool:
    return collection.scope in (
        ComboScope.MULTI_GAME, ComboScope.CROSS_SPORT, ComboScope.CROSS_CATEGORY
    ) and any(
        collection.collection_ticker.startswith(p)
        for p in _FALLBACK_COLLECTION_PREFIXES
    )


def fixture_events(
    collections: Sequence[ComboCollection], *, prefix: str, suffix: str
) -> tuple[Optional[ComboCollection], list]:
    """The catch-all collection with the most of this fixture's events, and
    those events (`ComboLeg`s).

    Legs with `detail_missing` are skipped: they carry no `size_max` and no
    `is_yes_only`, and a leg whose one-per-event and yes-only facts are
    unknown must not be offered as if they were known.
    """
    best: Optional[ComboCollection] = None
    best_legs: list = []
    for collection in sorted(
        (c for c in collections if _is_catch_all(c)),
        key=lambda c: (
            min(
                (i for i, p in enumerate(_FALLBACK_COLLECTION_PREFIXES)
                 if c.collection_ticker.startswith(p)),
                default=99,
            ),
            c.collection_ticker,
        ),
    ):
        legs = [
            leg for leg in collection.legs
            if not leg.detail_missing
            and leg.event_ticker.endswith("-" + suffix)
            and leg.series.startswith(prefix)
        ]
        if len(legs) > len(best_legs):
            best, best_legs = collection, legs
    return best, best_legs


def _player_of(market: dict) -> Optional[str]:
    """The player a prop names, from Kalshi's own text. `None` on a team
    market. Read off the part before the colon in `yes_sub_title`
    (`Aaron Rodgers: 125+`) or, for a scorer market whose sub-title is the
    bare name, the title (`Pat Freiermuth: 1st Touchdown`)."""
    for field in ("yes_sub_title", "title"):
        text = str(market.get(field) or "")
        if ":" in text:
            name = text.split(":", 1)[0].strip()
            if name:
                return name
    return None


def _strike_of(market: dict) -> Optional[float]:
    raw = market.get("floor_strike")
    try:
        return None if raw is None else float(raw)
    except (TypeError, ValueError):
        return None


async def _read_event_markets(api, event_ticker: str, gate: asyncio.Semaphore):
    """`(event_ticker, markets, None)` or `(event_ticker, None, words)`.

    A ticker that is not a plain event ticker is refused here, before any
    request: a comma in it would change what the request means (#205), and one
    bad element must stay a stated gap for that event alone.
    """
    if not _EVENT_TICKER.match(event_ticker or ""):
        return event_ticker, None, (
            f"{event_ticker!r} is not a readable event ticker, so its legs "
            "are not listed."
        )
    async with gate:
        try:
            markets = await asyncio.wait_for(
                api.markets_for_event(event_ticker), MARKET_READ_TIMEOUT_S
            )
        except Exception as exc:  # noqa: BLE001 -- one event failing is a stated gap
            logger.warning("game builder: %s unreadable (%s)", event_ticker, exc)
            return event_ticker, None, (
                f"Kalshi's markets for {event_ticker} could not be read "
                f"({type(exc).__name__}), so its legs are not listed."
            )
    return event_ticker, markets, None


def _price_sides(
    conn, legs: list[dict], *, now_ms: int, max_odds_age_ms: int
) -> None:
    """Fill each leg's `sides[...]` with the desk's chance or a worded reason.

    Same construction as `parlay_check`'s per-leg read: `candidate_pool` with
    `eligible_events=None` (a leg the venue lists is one it accepts; the
    eligibility cache would only ever hide one), `ladder_candidates` under the
    widest window, then `unusable_reason` and `p_conservative`. A leg absent
    from the pool is `None` and a reason, never `0`.
    """
    pool = candidate_pool(conn, now_ms=now_ms, max_odds_age_ms=max_odds_age_ms)
    pool = pool._replace(eligible_events=None)
    candidates, _excluded = ladder_candidates(
        conn, now_ms=now_ms, max_odds_age_ms=max_odds_age_ms,
        horizon=HORIZON, pool=pool,
    )
    by_key = {
        (c.kalshi_event_ticker, c.kalshi_market_ticker, c.side): c
        for c in candidates
    }
    missing = [
        leg["market_ticker"]
        for leg in legs
        for side in leg["allowed_sides"]
        if (leg["event_ticker"], leg["market_ticker"], side) not in by_key
    ]
    kickoffs = _commence_ms_for_tickers(conn, sorted(set(missing))) if missing else {}

    for leg in legs:
        for side in leg["allowed_sides"]:
            candidate = by_key.get((leg["event_ticker"], leg["market_ticker"], side))
            chance: Optional[float] = None
            code: Optional[str] = None
            if candidate is None:
                code = _missing_leg_reason(
                    kickoffs.get(leg["market_ticker"]),
                    now_ms=now_ms, horizon=HORIZON,
                )
            else:
                code = unusable_reason(candidate, max_odds_age_ms=max_odds_age_ms)
                if code is None:
                    chance = candidate.p_conservative
            leg["sides"][side] = {
                "chance": chance,
                "chance_display": _percent_display(chance),
                "unknown_reason": _reason_words(code),
                "unknown_reason_code": code,
            }


def _listed_side(market: dict, side: str) -> dict:
    """Kalshi's own listed ask for one side of a market, and the size at it.

    Read straight off the market object the listing already fetched (no extra
    Kalshi call), through `core.prices`. The YES side is `yes_ask_dollars` with
    `yes_ask_size_fp` behind it. The NO side is `no_ask_dollars`, and what is
    offered at that price is the YES BID's size (`yes_bid_size_fp`): a NO ask
    IS a resting YES bid, so there is no `no_bid_size_fp` and none is read
    (#276, chair's correction).

    An ask that is missing, unparseable, finer than a tenth of a cent, or not a
    tradeable level (0 or $1.00 is a settled outcome, not a quote) is `None`,
    never `0`; so is a size that is missing, unparseable, or negative. A size
    is never shown without an ask to attach it to.
    """
    ask_field = f"{side}_ask_dollars"
    size_field = "yes_ask_size_fp" if side == "yes" else "yes_bid_size_fp"
    ask, refused = dollars_to_tenths_exact(market.get(ask_field))
    if refused is not None or not is_valid_price(ask):
        ask = None
    size = parse_quantity(market.get(size_field)) if ask is not None else None
    if size is not None and not (math.isfinite(size) and size >= 0):
        size = None
    return {
        "ask_tenths": ask,
        "ask_display": format_price(ask) if ask is not None else None,
        "size": size,
        "size_display": f"{size:,.0f}" if size is not None else None,
    }


GAME_CONTEXT_SQL = (
    "SELECT l.odds_event_id, f.sport_key, f.commence_ms "
    "FROM event_links l "
    "JOIN odds_fixtures f ON f.odds_event_id = l.odds_event_id "
    "WHERE l.kalshi_event_ticker = ? "
    "ORDER BY f.commence_ms LIMIT 1"
)


def game_context(
    conn, game_event_ticker: str, other_event_tickers: Sequence[str] = ()
) -> dict:
    """The game's own name, kickoff, league and each team's rest (#293).

    One fixture per game, so one lookup serves every leg: `rest` is the same
    `{home, away}` shape `RestChip` reads on the parlay cards, and each leg
    carries it. **A per-row fact, never a sort key or a filter** (ADR 0071,
    0189); nothing reads it to order anything. Every field is `None` when the
    desk cannot identify the game -- never a guessed kickoff, never a zero --
    and a failed read logs and degrades to `None`, because a side fact must
    not take the listing down. Reads `kalshi_events` and `odds_fixtures` by
    key, never `odds_snapshots`.
    """
    game = game_event_ticker.strip().upper()
    out: dict = {
        "game_title": None, "kickoff_ms": None, "sport_key": None, "rest": None,
    }
    try:
        row = conn.execute(
            "SELECT title FROM kalshi_events WHERE event_ticker = ?", (game,)
        ).fetchone()
        if row is not None and row[0]:
            out["game_title"] = str(row[0])
        for ticker in (game, *other_event_tickers):
            fixture = conn.execute(GAME_CONTEXT_SQL, (ticker,)).fetchone()
            if fixture is not None:
                out["sport_key"] = fixture[1]
                out["kickoff_ms"] = fixture[2]
                out["rest"] = rest_for_games(
                    conn, {(fixture[0], fixture[2])}
                ).get(fixture[0])
                break
    except sqlite3.Error:
        logger.exception("game context read failed; the game carries nulls")
    return out


async def list_game_legs(
    conn,
    *,
    game_event_ticker: str,
    now_ms: int,
    max_odds_age_ms: int,
    api,
) -> dict:
    """Every leg Kalshi offers on this game, grouped, ordered, priced or not."""
    prefix, series, suffix = parse_game_ticker(game_event_ticker)
    game_event_ticker = game_event_ticker.strip().upper()

    collections = await _collections(api, now_ms=now_ms)
    collection, events = fixture_events(collections, prefix=prefix, suffix=suffix)
    if collection is None or not events:
        raise _refuse(
            404,
            "Kalshi's combination collections list nothing for this game "
            "right now, so no combination can be built on it. Props are "
            "listed only near kickoff. Nothing was created.",
        )

    skipped = max(0, len(events) - MAX_EVENTS_PER_GAME)
    events = events[:MAX_EVENTS_PER_GAME]
    gate = asyncio.Semaphore(MARKET_READ_CONCURRENCY)
    reads = await asyncio.gather(
        *(_read_event_markets(api, e.event_ticker, gate) for e in events)
    )
    by_event = {e.event_ticker: e for e in events}

    legs: list[dict] = []
    unreadable: list[dict] = []
    for event_ticker, markets, words in reads:
        if markets is None:
            unreadable.append({"event_ticker": event_ticker, "words": words})
            continue
        event = by_event[event_ticker]
        kind = _kind_of(event.series, prefix)
        cap = event.size_max if event.size_max and event.size_max > 0 else None
        for market in markets:
            ticker = str(market.get("ticker") or "")
            if not ticker or str(market.get("status") or "").lower() != _OFFERED_STATUS:
                continue
            legs.append({
                "market_ticker": ticker,
                "event_ticker": event_ticker,
                "series": event.series,
                "kind": kind,
                "title": str(market.get("title") or ticker),
                "yes_label": market.get("yes_sub_title") or None,
                # Kalshi's own `no_sub_title` equals the YES one (#275), so the
                # NO side is worded as its opposite per leg kind instead.
                "no_label": no_words_for(
                    series=event.series,
                    game_event_ticker=game_event_ticker,
                    yes_label=market.get("yes_sub_title"),
                ),
                "strike": _strike_of(market),
                "player": _player_of(market),
                "allowed_sides": ["yes"] if event.is_yes_only else ["yes", "no"],
                "size_max": cap,
                "one_per_event": cap == 1,
                "sides": {},
                # Kalshi's ask as the listing printed it, per allowed side,
                # stamped with when this listing was read (#276).
                "listed": {
                    "read_ms": now_ms,
                    **{
                        s: _listed_side(market, s)
                        for s in (["yes"] if event.is_yes_only else ["yes", "no"])
                    },
                },
            })

    _price_sides(conn, legs, now_ms=now_ms, max_odds_age_ms=max_odds_age_ms)
    context = game_context(conn, game_event_ticker, [e.event_ticker for e in events])
    for leg in legs:
        leg["rest"] = context["rest"]

    # **The fixed order. Nothing below reads `sides`, `chance`, or any price.**
    # Player before strike, so a prop series reads one player's ladder at a
    # time; team markets carry no player and keep strike order.
    legs.sort(key=lambda l: (
        _kind_rank(l["kind"]),
        l["player"] or "",
        l["strike"] is None, l["strike"] if l["strike"] is not None else 0.0,
        l["market_ticker"],
    ))
    groups: list[dict] = []
    for leg in legs:
        if not groups or groups[-1]["series"] != leg["series"]:
            groups.append({
                "series": leg["series"],
                "kind": leg["kind"],
                "label": SERIES_LABELS.get(leg["kind"], leg["kind"]),
                "one_per_event": leg["one_per_event"],
                "legs": [],
            })
        groups[-1]["legs"].append(leg)

    game_markets = sorted(
        l["market_ticker"] for l in legs if l["series"] == series
    )
    _remember_listing(
        game_event_ticker, now_ms,
        {l["market_ticker"]: {"event_ticker": l["event_ticker"],
                              "title": l["title"]}
         for l in legs},
    )
    return {
        "game_event_ticker": game_event_ticker,
        "fixture": suffix,
        "collection_ticker": collection.collection_ticker,
        "game_market_ticker": game_markets[0] if game_markets else None,
        "groups": groups,
        "leg_count": len(legs),
        "game_title": context["game_title"],
        "kickoff_ms": context["kickoff_ms"],
        "sport_key": context["sport_key"],
        "unreadable_events": unreadable,
        "skipped_events": skipped,
        "now_ms": now_ms,
    }


# -- the mint ---------------------------------------------------------------


def _validate_request(game: tuple[str, str, str], legs: Sequence[dict]) -> list[dict]:
    """The refusals that need no I/O. Returns the legs, normalised.

    Order matters only for which words a person sees first; every branch
    raises before a venue call because nothing above the venue call reaches
    one.
    """
    prefix, _series, suffix = game
    if len(legs) < 2:
        raise _refuse(
            422,
            "Tick at least two legs. A combination of one leg is just that "
            "bet on its own, and Kalshi will not mint it as a combination. "
            "Nothing was created.",
        )
    out: list[dict] = []
    seen: dict[str, str] = {}
    for raw in legs:
        market = str(raw.get("market_ticker") or "").strip().upper()
        event = str(raw.get("event_ticker") or "").strip().upper()
        side = str(raw.get("side") or "").strip().lower()
        event_match = _EVENT_TICKER.match(event)
        if (
            event_match is None
            or event_match.group(2) != suffix
            or not event_match.group(1).startswith(prefix)
            or not market.startswith(event + "-")
        ):
            raise _refuse(
                422,
                f"{market or 'A leg'} is not on this game's list, so it "
                "cannot go in this combination. Reload the game and tick "
                "from the list. Nothing was created.",
            )
        if side not in ("yes", "no"):
            raise _refuse(
                422, f"{market}: a leg's side is yes or no, not {side!r}. "
                "Nothing was created.",
            )
        if market in seen:
            if seen[market] != side:
                raise _refuse(
                    422,
                    f"{market} is ticked on both sides. A combination cannot "
                    "back a leg and bet against it at once. Nothing was "
                    "created.",
                )
            raise _refuse(
                422, f"{market} is ticked twice. Nothing was created."
            )
        seen[market] = side
        out.append({"market_ticker": market, "event_ticker": event, "side": side})
    # A team to win beside that same team's cover (#277). Kalshi refuses the
    # pair as `duplicated_legs` AFTER the mint call, so it is refused here, in
    # words, before any venue call. The detector is the one the scout cards
    # use, for DETECTION only: this path never drops the win leg and mints the
    # rest, because the ticker would then differ from what Joe ticked (#274 A).
    _kept, implied = game_script_cards.drop_implied_win_legs(out)
    if implied:
        win = implied[0]["market_ticker"]
        team = win.rsplit("-", 1)[-1]
        covers = [
            leg["market_ticker"] for leg in out
            if leg["side"] == "yes"
            and leg["event_ticker"].split("-")[0].endswith("SPREAD")
            and leg["market_ticker"].split("-")[-1].rstrip("0123456789") == team
        ]
        cover = covers[0] if covers else "its cover"
        raise _refuse(
            422,
            f"{win} (the team to win) and {cover} (the same team winning by a "
            "margin) are both ticked. Kalshi refuses that pair as duplicated "
            "legs, because winning by that margin already guarantees the win. "
            "Untick one of them. Nothing was created.",
        )
    return out


def _check_against_listing(legs: Sequence[dict], game_event_ticker: str, *, now_ms: int) -> None:
    """Refuse a market the last listing of this game never showed. No I/O.

    Skipped when nothing (or nothing fresh) is remembered: the structural
    checks and the venue then decide.
    """
    remembered = _listing_memory.get(game_event_ticker)
    if remembered is None or now_ms - remembered[0] > _LISTING_TTL_MS:
        return
    known = remembered[1]
    for leg in legs:
        facts = known.get(leg["market_ticker"])
        if facts is None or facts["event_ticker"] != leg["event_ticker"]:
            raise _refuse(
                422,
                f"{leg['market_ticker']} is not on this game's list, so it "
                "cannot go in this combination. Reload the game and tick "
                "from the list. Nothing was created.",
            )


def _check_event_limits(legs: Sequence[dict], events_by_ticker: dict) -> None:
    """One rung per event where Kalshi allows one (`size_max`), and yes-only
    events refuse a NO leg. Reads the collection's own per-event facts."""
    counts: dict[str, int] = {}
    for leg in legs:
        event = events_by_ticker.get(leg["event_ticker"])
        if event is None:
            raise _refuse(
                422,
                f"{leg['market_ticker']} is not on this game's list, so it "
                "cannot go in this combination. Nothing was created.",
            )
        if event.is_yes_only and leg["side"] == "no":
            raise _refuse(
                422,
                f"{leg['market_ticker']} can only be bought on the yes side "
                "in a combination. Nothing was created.",
            )
        counts[leg["event_ticker"]] = counts.get(leg["event_ticker"], 0) + 1
    for event_ticker, count in counts.items():
        cap = events_by_ticker[event_ticker].size_max
        if cap and cap > 0 and count > cap:
            raise _refuse(
                422,
                f"Kalshi lets a combination take {cap} leg"
                f"{'' if cap == 1 else 's'} from {event_ticker}, and "
                f"{count} are ticked. Pick one. Nothing was created.",
            )


def attach_combo_to_card(
    conn, *, game_event_ticker: str, legs: Sequence[tuple[str, str]], minted: str
) -> Optional[int]:
    """Stamp the minted combination onto the game's built card, when it IS it.

    `legs` is the minted set as `(market_ticker, side)`. The newest built card
    for the game is stamped only if its legs are exactly that set, so a
    hand-ticked mix of other legs never claims a card. Returns the card id or
    `None`. Kept so which cards Joe bet can be COUNTED later (ADR 0190); it is
    a record, never a rank, and a failure here must not lose the mint."""
    try:
        row = conn.execute(
            "SELECT id, legs_json FROM game_script_cards "
            "WHERE game_event_ticker = ? AND status = 'built' "
            "ORDER BY built_ms DESC, id DESC LIMIT 1",
            (game_event_ticker,),
        ).fetchone()
        if row is None:
            return None
        # Compared as the card is SHOWN: a win leg beside its own cover is
        # dropped on read (`drop_implied_win_legs`), so that is what Joe mints.
        shown, _ = game_script_cards.drop_implied_win_legs(json.loads(row[1]))
        card_legs = {(l["market_ticker"], l["side"]) for l in shown}
        if card_legs != set(legs):
            return None
        conn.execute(
            "UPDATE game_script_cards SET combo_ticker = ? WHERE id = ?",
            (minted, row[0]),
        )
        conn.commit()
        return int(row[0])
    except Exception:  # noqa: BLE001 -- a bookkeeping write never fails a mint
        logger.warning("game builder: card write-back failed", exc_info=True)
        return None


async def mint_game_combo(
    conn,
    *,
    game_event_ticker: str,
    legs: Sequence[dict],
    now_ms: int,
    api,
) -> dict:
    """Mint the ticked legs on Kalshi and record it for the RFQ path.

    Writes ONE `parlay_lookups` row per attempt that reaches the venue, with
    `card_key = "game"` and `fair_joint_conservative` NULL. Refusals before
    the venue write nothing: no market exists and no question was asked.
    """
    game = parse_game_ticker(game_event_ticker)
    game_event_ticker = game_event_ticker.strip().upper()
    ticked = _validate_request(game, legs)
    _check_against_listing(ticked, game_event_ticker, now_ms=now_ms)

    collections = await _collections(api, now_ms=now_ms)
    _collection, events = fixture_events(collections, prefix=game[0], suffix=game[2])
    _check_event_limits(ticked, {e.event_ticker: e for e in events})

    pairs = sorted((l["event_ticker"], l["market_ticker"]) for l in ticked)
    side_of = {(l["event_ticker"], l["market_ticker"]): l["side"] for l in ticked}
    wire_legs = [(e, m, side_of[(e, m)]) for e, m in pairs]

    chosen = _choose_collection(
        collections, {e for e, _ in pairs}, leg_count=len(pairs)
    )
    if chosen is None:
        _record_lookup(
            conn, now_ms=now_ms, card_key=CARD_KEY, stake_cents=0,
            legs=pairs, status="no_collection",
        )
        return {
            "status": "no_collection",
            "words": (
                "Kalshi lists no combination collection that accepts these "
                "legs right now. Nothing was created."
            ),
        }
    collection = chosen.collection
    unverified = not chosen.verified

    try:
        response = await lookup_combo(
            api, collection.collection_ticker, wire_legs,
            side="yes", allow_market_creation=True,
        )
    except Exception as exc:  # noqa: BLE001 -- recorded, then re-raised as words
        _record_lookup(
            conn, now_ms=now_ms, card_key=CARD_KEY, stake_cents=0, legs=pairs,
            status="error", collection_ticker=collection.collection_ticker,
            error=str(exc), collection_unverified=unverified,
        )
        if not unverified:
            invalidate_collections_cache()
        raise _refuse(502, f"Kalshi refused the combination: {exc}") from exc

    minted = response.get("market_ticker") or (
        (response.get("market") or {}).get("ticker")
    )
    if not minted:
        _record_lookup(
            conn, now_ms=now_ms, card_key=CARD_KEY, stake_cents=0, legs=pairs,
            status="error", collection_ticker=collection.collection_ticker,
            error=f"no market_ticker in response keys {sorted(response)}",
            collection_unverified=unverified,
        )
        raise _refuse(502, "Kalshi answered without naming the minted market.")

    echo = echoed_legs(wire_legs, response, side="yes")
    if echo.is_mismatch:
        _record_lookup(
            conn, now_ms=now_ms, card_key=CARD_KEY, stake_cents=0, legs=pairs,
            status="error", collection_ticker=collection.collection_ticker,
            minted=minted, error=f"leg echo mismatch: {echo.detail}",
            collection_unverified=unverified,
        )
        raise _refuse(
            502,
            "Kalshi minted a combination whose legs are not the ones asked "
            "for. Nothing is priced; the market exists and is recorded.",
        )

    # Leg detail for `/hedge`, which refuses a leg with no label. Kalshi's own
    # title from the listing when this game was listed; else the recorder's
    # copy; else the ticker, which `legs_for_position` flags as degraded.
    tickers = [m for _, m in pairs]
    remembered = _listing_memory.get(game_event_ticker, (0, {}))[1]
    titles = _titles_for(conn, tickers)
    for ticker in tickers:
        if ticker in remembered:
            titles[ticker] = remembered[ticker]["title"]
    kickoffs = _commence_ms_for_tickers(conn, tickers)
    leg_details = {
        (e, m): {
            "side": side_of[(e, m)],
            "label": _leg_label(m, side_of[(e, m)], titles),
            "commence_ms": kickoffs.get(m),
        }
        for e, m in pairs
    }

    # The book read is context, not the answer (a combination is priced by
    # asking), and it decides which of the two honest statuses the row gets.
    # A failed read must not lose the ticker: the market exists.
    ask_tenths = None
    no_bid = None
    depth = None
    detail: Optional[str] = None
    try:
        book = OrderBook(ticker=minted)
        book.apply_snapshot(await api.orderbook(minted, depth=10), None, now_ms)
        ask_tenths = book.best_yes_ask
        no_bid = book.best_no_bid
        depth = book.depth_at_ask("yes") if ask_tenths is not None else None
        if ask_tenths is None:
            detail = (
                f"yes_bid={book.best_yes_bid if book.best_yes_bid is not None else 'none'} "
                f"yes_levels={len(book.yes_bids)} no_levels={len(book.no_bids)}"
            )
    except Exception as exc:  # noqa: BLE001 -- recorded on the row
        detail = f"orderbook not read after mint: {exc}"

    status = "priced" if ask_tenths is not None else "book_empty"
    _record_lookup(
        conn, now_ms=now_ms, card_key=CARD_KEY, stake_cents=0, legs=pairs,
        status=status, collection_ticker=collection.collection_ticker,
        minted=minted, no_bid_tenths=no_bid, ask_tenths=ask_tenths, depth=depth,
        fair_joint=None, hold=None, error=detail,
        collection_unverified=unverified, leg_details=leg_details,
    )
    attach_combo_to_card(
        conn, game_event_ticker=game_event_ticker,
        legs=[(m, side_of[(e, m)]) for e, m in pairs], minted=minted,
    )
    return {
        "status": "minted",
        "book": "quoted" if ask_tenths is not None else "empty",
        "minted_market_ticker": minted,
        "legs": [
            {"market_ticker": m, "side": side_of[(e, m)],
             "label": leg_details[(e, m)]["label"]}
            for e, m in pairs
        ],
        "words": (
            "Kalshi created the combination. Nothing is priced yet: a "
            "combination is priced by asking the market makers, and asking "
            "commits you to nothing."
        ),
    }
