"""Sports market discovery: find the games we can actually price.

Turns the raw `/events` walk into classified, persistable rows — which league,
which market type, when the game starts, and which side each contract pays on.

Everything here is driven by fields observed in a real captured payload
(`tests/fixtures/events_sports_nested.json`, 2026-08-06), not by parsing
tickers. Three of those fields do the heavy lifting and are worth stating
plainly, because each one replaced a heuristic that would have been wrong:

**`product_metadata.competition_scope`** distinguishes a game from a future
directly. `"Game"` means one fixture. No inference from close dates, no
title regex.

**`occurrence_datetime` is the game start.** `close_time` is not: on
`KXMLBGAME-26AUG092020HOUSD` the game is 2026-08-10T03:20Z while `close_time`
is 2026-08-13T00:20Z, three days later. Matching on `close_time` would have
mis-joined every fixture against the sportsbook feed.

**`yes_sub_title` names the side the YES contract pays on.** But note
`no_sub_title` is *not* the opposing team — on the moneyline above, both read
`"Houston"`. Only `yes_sub_title` is meaningful, and the opposing side must
come from the other market in the same event.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from ..core.prices import dollars_to_tenths, parse_quantity

logger = logging.getLogger(__name__)

JUNK_PREFIX = "KXMVE"

# Series suffix -> our market type. The suffix is a reliable signal *within*
# a sports series; it is not used to determine whether the series is
# game-level (competition_scope does that).
_SUFFIX_TO_MARKET_TYPE = {
    "GAME": "moneyline",
    "SPREAD": "spread",
    "TOTAL": "total",
    "TEAMTOTAL": "team_total",
}

# `product_metadata.competition_scope` values that mean "resolves on a single
# fixture". This is NOT just "Game": spreads and totals are per-fixture markets
# too, and they are precisely what teaser and key-number pricing need.
#
# Observed in the real capture: Game, Spread, Point Total, Future, Awards.
# An earlier version of this module tested `scope == "game"` and silently
# discarded every spread and total in the universe. Values are lowercased
# before comparison.
FIXTURE_SCOPES: frozenset[str] = frozenset(
    {"game", "spread", "point total", "team total"}
)

# Scopes that are explicitly NOT per-fixture. Listed rather than inferred so
# that a scope we have never seen fails the drift test in tests/test_discovery.py
# instead of being quietly bucketed either way.
NON_FIXTURE_SCOPES: frozenset[str] = frozenset(
    {"future", "awards", "season", "series", "tournament"}
)

# Leagues we can price, mapped to their The Odds API sport key. A league absent
# here is out of scope -- not because Kalshi lacks markets, but because we have
# no consensus to devig against. Adding one is a config change.
#
# Keys are `product_metadata.competition` **exactly as Kalshi spells it**. Do
# not tidy these strings. An earlier version guessed "Womens Pro Basketball"
# and "College Football"; Kalshi actually says "Pro Basketball (W)" and
# "NCAA Football", and both leagues silently vanished from the Board.
IN_SCOPE_LEAGUES: dict[str, str] = {
    "Pro Baseball": "baseball_mlb",
    "Pro Football": "americanfootball_nfl",
    "NCAA Football": "americanfootball_ncaaf",
    "Pro Basketball (M)": "basketball_nba",
    "Pro Basketball (W)": "basketball_wnba",
    "Pro Hockey": "icehockey_nhl",
}

_SERIES_RE = re.compile(r"^KX([A-Z0-9]+?)(GAME|SPREAD|TEAMTOTAL|TOTAL)$")


def parse_ms(value: Any) -> Optional[int]:
    """ISO-8601 to epoch milliseconds, UTC. Unreadable returns None, never 0."""
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.astimezone(timezone.utc).timestamp() * 1000)
    except (ValueError, TypeError):
        return None


@dataclass(frozen=True)
class SeriesInfo:
    """What a series ticker plus its metadata tells us."""

    series_ticker: str
    league: Optional[str]          # Kalshi's `competition`, e.g. "Pro Baseball"
    sport_key: Optional[str]       # The Odds API key, None when out of scope
    market_type: Optional[str]     # moneyline | spread | total | team_total
    is_game_level: bool

    @property
    def in_scope(self) -> bool:
        """Priceable: a game-level market in a league we can devig against."""
        return (
            self.is_game_level
            and self.sport_key is not None
            and self.market_type is not None
        )


def classify_series(event: dict) -> SeriesInfo:
    """Classify one event's series from its metadata and ticker suffix."""
    series_ticker = event.get("series_ticker") or ""
    metadata = event.get("product_metadata") or {}
    league = (metadata.get("competition") or "").strip() or None
    scope = (metadata.get("competition_scope") or "").strip()

    match = _SERIES_RE.match(series_ticker)
    market_type = _SUFFIX_TO_MARKET_TYPE.get(match.group(2)) if match else None

    # Prefer the metadata. Fall back to the suffix only when metadata is
    # absent, and say so -- a silent fallback is how a classifier drifts from
    # the data it claims to read.
    normalised_scope = scope.lower()
    if normalised_scope in FIXTURE_SCOPES:
        is_game_level = True
    elif normalised_scope in NON_FIXTURE_SCOPES:
        is_game_level = False
    elif normalised_scope:
        # A scope we have never seen. Treat it as not-per-fixture (the safe
        # direction: we decline to price rather than pricing something we do
        # not understand) but say so loudly, because it may be a market type
        # we want. The drift test in tests/test_discovery.py fails on this too.
        is_game_level = False
        logger.warning(
            "%s has unrecognised competition_scope %r -- excluded from pricing. "
            "If this is a per-fixture market, add it to FIXTURE_SCOPES.",
            series_ticker, scope,
        )
    else:
        is_game_level = market_type is not None
        if series_ticker:
            logger.debug(
                "%s has no competition_scope; falling back to the ticker suffix",
                series_ticker,
            )

    return SeriesInfo(
        series_ticker=series_ticker,
        league=league,
        sport_key=IN_SCOPE_LEAGUES.get(league) if league else None,
        market_type=market_type,
        is_game_level=is_game_level,
    )


def event_commence_ms(event: dict) -> Optional[int]:
    """When the game actually starts.

    From `occurrence_datetime` on the event's markets, **not** `close_time`.
    Kalshi keeps markets open for days after a fixture to handle postponements,
    so `close_time` can be 3+ days past the game.

    Returns None when no market carries one -- and None must block the match
    rather than defaulting to anything, because a wrong start time silently
    joins the wrong fixture.
    """
    for market in event.get("markets") or []:
        ms = parse_ms(market.get("occurrence_datetime"))
        if ms is not None:
            return ms
    return None


@dataclass(frozen=True)
class DiscoveredMarket:
    ticker: str
    event_ticker: str
    series_ticker: str
    market_type: str
    title: str
    yes_side: Optional[str]      # the team/outcome YES pays on
    strike: Optional[float]      # spread/total line
    close_ms: Optional[int]
    status: Optional[str]
    volume_24h: float
    open_interest: float
    price_structure: Optional[str]

    # The quote carried on the same payload. Only the two published BIDS are
    # kept: asks are derived (`1 - opposing bid`) and storing a derived number
    # beside a quoted one invites a reader to treat them alike.
    #
    # Carried here rather than re-read from the raw dict by the caller, because
    # a second parse of the same bytes means a second set of field-name
    # assumptions -- which is exactly how `apply_snapshot` came to read
    # `data["yes"]` while Kalshi sent `yes_dollars_fp`. One reader, one place to
    # be wrong, one fixture that pins it.
    #
    # `None` means unreadable and callers must refuse rather than substitute:
    # 0 is a legitimate price on a settled market.
    yes_bid_tenths: Optional[int] = None
    no_bid_tenths: Optional[int] = None
    # Size resting at each side's ASK -- what you could actually lift. Kalshi
    # publishes `yes_ask_size_fp` directly; the size at the no ask is the resting
    # yes bid, since a no ask is derived from it.
    yes_ask_size: Optional[float] = None
    no_ask_size: Optional[float] = None


@dataclass(frozen=True)
class DiscoveredEvent:
    event_ticker: str
    series_ticker: str
    league: str
    sport_key: str
    market_type: str
    title: str
    commence_ms: int
    markets: tuple[DiscoveredMarket, ...]

    @property
    def teams(self) -> tuple[str, ...]:
        """Distinct sides named by the event's markets.

        For a moneyline this is the two teams -- the matching key. Built from
        `yes_sub_title` across markets, because `no_sub_title` repeats the YES
        side rather than naming the opponent.
        """
        seen: list[str] = []
        for market in self.markets:
            if market.yes_side and market.yes_side not in seen:
                seen.append(market.yes_side)
        return tuple(seen)


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_markets(event: dict, market_type: str) -> tuple[DiscoveredMarket, ...]:
    out: list[DiscoveredMarket] = []
    for market in event.get("markets") or []:
        ticker = market.get("ticker") or ""
        if ticker.startswith(JUNK_PREFIX):
            continue
        strike = market.get("floor_strike")
        out.append(
            DiscoveredMarket(
                ticker=ticker,
                event_ticker=event.get("event_ticker") or "",
                series_ticker=event.get("series_ticker") or "",
                market_type=market_type,
                title=market.get("title") or "",
                yes_side=(market.get("yes_sub_title") or "").strip() or None,
                strike=float(strike) if strike is not None else None,
                close_ms=parse_ms(market.get("close_time")),
                status=market.get("status"),
                volume_24h=_float(market.get("volume_24h_fp")),
                open_interest=_float(market.get("open_interest_fp")),
                price_structure=market.get("price_level_structure"),
                # Field names verified against tests/fixtures/
                # events_sports_nested.json, not against memory. Prices arrive
                # as dollar STRINGS ("0.4500"), so `dollars_to_tenths` parses
                # them and returns None on anything it cannot read.
                yes_bid_tenths=dollars_to_tenths(market.get("yes_bid_dollars")),
                no_bid_tenths=dollars_to_tenths(market.get("no_bid_dollars")),
                yes_ask_size=parse_quantity(market.get("yes_ask_size_fp")),
                no_ask_size=parse_quantity(market.get("yes_bid_size_fp")),
            )
        )
    return tuple(out)


def discover_from_events(events: Iterable[dict]) -> list[DiscoveredEvent]:
    """Classify a walk of `/events` into priceable game events.

    Everything rejected is rejected for a stated reason and counted, so
    "we found nothing" can be told apart from "we filtered everything".
    """
    discovered: list[DiscoveredEvent] = []
    rejected: dict[str, int] = {
        "not_game_level": 0,
        "league_out_of_scope": 0,
        "no_commence_time": 0,
        "no_markets": 0,
    }

    for event in events:
        if (event.get("event_ticker") or "").startswith(JUNK_PREFIX):
            continue

        info = classify_series(event)
        if not info.is_game_level:
            rejected["not_game_level"] += 1
            continue
        if info.sport_key is None or info.market_type is None:
            rejected["league_out_of_scope"] += 1
            continue

        commence_ms = event_commence_ms(event)
        if commence_ms is None:
            rejected["no_commence_time"] += 1
            logger.warning(
                "%s is game-level but carries no occurrence_datetime; cannot be "
                "matched against a sportsbook fixture",
                event.get("event_ticker"),
            )
            continue

        markets = build_markets(event, info.market_type)
        if not markets:
            rejected["no_markets"] += 1
            continue

        discovered.append(
            DiscoveredEvent(
                event_ticker=event.get("event_ticker") or "",
                series_ticker=info.series_ticker,
                league=info.league or "",
                sport_key=info.sport_key,
                market_type=info.market_type,
                title=event.get("title") or "",
                commence_ms=commence_ms,
                markets=markets,
            )
        )

    logger.info(
        "discovery: %d priceable events; rejected %s",
        len(discovered),
        ", ".join(f"{k}={v}" for k, v in rejected.items() if v),
    )
    return discovered


def coverage_by_league(events: list[DiscoveredEvent]) -> dict[str, dict]:
    """Per-league summary, for the Board and for scope decisions."""
    summary: dict[str, dict] = {}
    for event in events:
        entry = summary.setdefault(
            event.league,
            {
                "sport_key": event.sport_key,
                "events": 0,
                "markets": 0,
                "market_types": set(),
                "volume_24h": 0.0,
            },
        )
        entry["events"] += 1
        entry["markets"] += len(event.markets)
        entry["market_types"].add(event.market_type)
        entry["volume_24h"] += sum(m.volume_24h for m in event.markets)

    for entry in summary.values():
        entry["market_types"] = sorted(entry["market_types"])
    return summary
