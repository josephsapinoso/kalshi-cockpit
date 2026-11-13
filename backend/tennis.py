"""Pricing one tennis match-winner leg from a sportsbook h2h reading (#439 design, §1/§2/§3/§5).

Tennis sits outside discovery, so no `kalshi_markets` / `event_links` row exists
for it and the alternate-line path cannot be reused. These are the pure steps
that stand in for them. **No network, no sqlite**: callers (the on-demand
runner, #446) fetch and store; this module only reads what it is handed.

The steps
---------
1. `classify_series`: the series is `ticker.split("-")[0]` compared by EXACT
   equality. `KXATPMATCH` -> "atp", `KXWTAMATCH` -> "wta". A match-winner
   series with no Odds API key (Challenger, ITF, team events, exhibitions,
   doubles) is `tennis_no_sportsbook_tournament`; anything else is
   `tennis_not_match_winner`. `startswith` is never used: `KXATPMATCHX` or a
   future `KXATPMATCH...` series must not inherit the ATP key.
2. `read_event`: the two players, the occurrence time and which one the leg is,
   read from `event.markets` of the single-event payload (the top-level
   `markets` of that payload is an EMPTY list). Anything short of a clean
   two-player event is `tennis_unreadable_event`.
3. `choose_link`: the sportsbook event whose {home, away} equals Kalshi's two
   names as a set after normalisation, inside +/-36 h of occurrence. Exactly one
   or refuse; no fuzzy fallback ("Stan" vs "Stanislas" refuses, which fails
   safe).
5. `price_leg`: per-book devig matched to Kalshi's names BY NAME, never by
   home/away or order; worst of four methods for the side asked.

What this does not establish
----------------------------
* Nothing about whether the chance beats Kalshi's price. It is a per-row fact,
  never an ordering (ADR 0071).
* Nothing about the sportsbooks' retirement / walkover rules: Kalshi resolves
  after "a ball has been played", the books' rules were not read.
* Not freshness. Callers apply `unusable_reason` / `max_odds_age_ms`.
* The series refusal list is a reading of `kalshi_tennis_series_list.json`, not
  a claim that it is complete. A new series falls to `tennis_not_match_winner`.
* Link rate on the captures is 3 of 3 main-tour matches. n = 3 is not a rate.
* The two-sharp-book floor (see `price_leg`) is a design choice from ONE
  observed thin exchange (Pegula v Andreeva), not a measured threshold.
* `rows` for `price_leg` must already be the `h2h` market only. `h2h_lay` is an
  exchange LAY price and devigging it as a back price would be wrong; dropping
  it is the odds parser's job (`backend/odds/client.py`).

**Unreadable resolves to `None` with a reason, never to 0.**
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence

from .core.devig import DevigError, consensus_devig

logger = logging.getLogger(__name__)

# Refusal reasons (they become `tennis_links.refusal_reason`).
NO_SPORTSBOOK_TOURNAMENT = "tennis_no_sportsbook_tournament"
NOT_MATCH_WINNER = "tennis_not_match_winner"
UNREADABLE_EVENT = "tennis_unreadable_event"
NO_SPORTSBOOK_MATCH = "tennis_no_sportsbook_match"
AMBIGUOUS_MATCH = "tennis_ambiguous_match"
NO_TWO_SIDED_BOOK = "no_two_sided_book"
DEVIG_FAILED = "devig_failed"
UNKNOWN_SIDE = "unknown_side"

#: The priced series -> tour tier.
PRICED_SERIES: dict[str, str] = {"KXATPMATCH": "atp", "KXWTAMATCH": "wta"}

#: Match-winner series on Kalshi with no Odds API sport key. Read off
#: `tests/fixtures/kalshi_tennis_series_list.json`; not claimed complete.
NO_SPORTSBOOK_SERIES: frozenset[str] = frozenset({
    # Challenger
    "KXATPCHALLENGERMATCH", "KXCHALLENGERMATCH", "KXWTACHALLENGERMATCH",
    # ITF
    "KXITFMATCH", "KXITFWMATCH",
    # team events
    "KXDAVISCUPMATCH", "KXUNITEDCUPMATCH", "KXLAVERCUPMATCH",
    # exhibitions
    "KXSIXKINGSSLAMMATCH", "KXSIXKINGSMATCH", "KXEXHIBITIONMEN",
    "KXEXHIBITIONWOMEN", "KXTENNISEXHIBITION", "KXBATTLEOFSEXES",
    # doubles
    "KXATPDOUBLES", "KXWTADOUBLES", "KXITFDOUBLES", "KXITFWDOUBLES",
    "KXATPCHALLENGERDOUBLES", "KXMIXEDDOUBLESMATCH", "KXLAVERCUPDOUBLESMATCH",
})

#: The match window either side of Kalshi's occurrence time. The name pair
#: identifies the match; time only rules out a rematch days apart.
LINK_WINDOW_MS = 36 * 3_600_000

#: Sharp books needed (two-sided) before the consensus anchors on them.
MIN_SHARP_BOOKS = 2


# ---------------------------------------------------------------------------
# §1 classify
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SeriesClass:
    """`tier` is "atp"/"wta" iff `reason` is None."""

    tier: Optional[str]
    reason: Optional[str]


def classify_series(market_ticker: str) -> SeriesClass:
    """Which tour a ticker prices on, or why it does not. Exact equality only."""
    series = str(market_ticker or "").split("-")[0]
    tier = PRICED_SERIES.get(series)
    if tier is not None:
        return SeriesClass(tier, None)
    if series in NO_SPORTSBOOK_SERIES:
        return SeriesClass(None, NO_SPORTSBOOK_TOURNAMENT)
    return SeriesClass(None, NOT_MATCH_WINNER)


def scope_refusal(event: Mapping[str, Any]) -> Optional[str]:
    """A refusal reason unless the event is a whole-match (`Game`) market."""
    meta = event.get("product_metadata")
    scope = meta.get("competition_scope") if isinstance(meta, Mapping) else None
    return None if scope == "Game" else NOT_MATCH_WINNER


# ---------------------------------------------------------------------------
# §2 read the event
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EventRead:
    """Two players and the leg's own. `reason` set iff unreadable."""

    reason: Optional[str]
    players: tuple[str, ...] = ()          # (name of market 0, name of market 1)
    occurrence_ms: Optional[int] = None
    leg_index: Optional[int] = None        # which of `players` the leg's market is
    detail: str = ""

    @property
    def leg_player(self) -> Optional[str]:
        return None if self.leg_index is None else self.players[self.leg_index]


def _unreadable(detail: str) -> EventRead:
    return EventRead(UNREADABLE_EVENT, detail=detail)


def parse_utc_ms(text: Any) -> Optional[int]:
    """ISO-8601 with `Z` -> epoch ms; `None` when unreadable."""
    if not isinstance(text, str) or not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def read_event_object(event: Mapping[str, Any], leg_market_ticker: str) -> EventRead:
    """Read an event object (the `event` of the single-event response, or one
    element of a list response). Reads `event["markets"]`."""
    scope = scope_refusal(event)
    if scope is not None:
        return EventRead(scope, detail="competition_scope is not Game")
    markets = event.get("markets")
    if not isinstance(markets, list) or len(markets) != 2:
        return _unreadable("not exactly two markets")
    if event.get("mutually_exclusive") is not True:
        return _unreadable("not mutually_exclusive")
    if any(not isinstance(m, Mapping) or m.get("status") != "active" for m in markets):
        return _unreadable("a market is not active")
    stamps = [parse_utc_ms(m.get("occurrence_datetime")) for m in markets]
    if stamps[0] is None or stamps[0] != stamps[1]:
        return _unreadable("occurrence_datetime missing or unequal")
    ids = []
    for m in markets:
        strike = m.get("custom_strike")
        ids.append(strike.get("tennis_competitor") if isinstance(strike, Mapping) else None)
    if not all(ids) or ids[0] == ids[1]:
        return _unreadable("tennis_competitor ids missing or equal")
    names = [m.get("yes_sub_title") for m in markets]
    if not all(isinstance(n, str) and n.strip() for n in names):
        return _unreadable("yes_sub_title missing")
    if normalise_name(names[0]) == normalise_name(names[1]):
        return _unreadable("both players have the same name")
    found = [i for i, m in enumerate(markets) if m.get("ticker") == leg_market_ticker]
    if len(found) != 1:
        return _unreadable("leg market not found by exact ticker")
    return EventRead(
        None, players=(names[0], names[1]), occurrence_ms=stamps[0], leg_index=found[0]
    )


def read_event(single_event_payload: Mapping[str, Any], leg_market_ticker: str) -> EventRead:
    """Read `GET /events/{ticker}?with_nested_markets=true`.

    The markets are nested in `event`; the response's top-level `markets` is an
    empty list and is never read.
    """
    event = single_event_payload.get("event") if isinstance(single_event_payload, Mapping) else None
    if not isinstance(event, Mapping):
        return _unreadable("no event in payload")
    return read_event_object(event, leg_market_ticker)


# ---------------------------------------------------------------------------
# §3 names and the link
# ---------------------------------------------------------------------------

def normalise_name(name: str) -> str:
    """NFKD, strip accents, casefold, collapse whitespace and hyphens."""
    decomposed = unicodedata.normalize("NFKD", str(name))
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[\s\-]+", " ", stripped.casefold()).strip()


@dataclass(frozen=True)
class LinkChoice:
    """The one sportsbook event, or the reason there is not exactly one."""

    event: Optional[Mapping[str, Any]]
    reason: Optional[str]
    commence_skew_ms: Optional[int] = None   # book commence - Kalshi occurrence
    candidates: int = 0


def choose_link(
    kalshi_names: Sequence[str],
    occurrence_ms: int,
    odds_events: Sequence[Mapping[str, Any]],
) -> LinkChoice:
    """Exactly one event across the tour's keys with the same two names (as a
    set) within +/-36 h, else a refusal."""
    want = frozenset(normalise_name(n) for n in kalshi_names)
    if len(want) != 2:
        return LinkChoice(None, UNREADABLE_EVENT)
    hits: list[tuple[Mapping[str, Any], int]] = []
    seen: set[str] = set()
    for ev in odds_events:
        eid = ev.get("id")
        if eid is not None:
            # The same vendor event listed twice is one candidate, not two.
            if eid in seen:
                continue
            seen.add(eid)
        have = frozenset(
            normalise_name(ev.get(k) or "") for k in ("home_team", "away_team")
        )
        if have != want:
            continue
        commence = parse_utc_ms(ev.get("commence_time"))
        if commence is None or abs(commence - occurrence_ms) > LINK_WINDOW_MS:
            continue
        hits.append((ev, commence - occurrence_ms))
    if not hits:
        return LinkChoice(None, NO_SPORTSBOOK_MATCH, candidates=0)
    if len(hits) > 1:
        return LinkChoice(None, AMBIGUOUS_MATCH, candidates=len(hits))
    ev, skew = hits[0]
    return LinkChoice(ev, None, commence_skew_ms=skew, candidates=1)


# ---------------------------------------------------------------------------
# §5 devig
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TennisReading:
    """A chance for one leg. `chance is None` iff `reason` is set."""

    chance: Optional[float]
    reason: Optional[str]
    books_used: tuple[str, ...] = ()
    books_dropped: dict[str, str] = field(default_factory=dict)
    anchored_on_sharp: bool = False


def _refuse(reason: str, dropped: Optional[dict[str, str]] = None) -> TennisReading:
    return TennisReading(None, reason, books_dropped=dict(dropped or {}))


def price_leg(
    rows: Sequence[Mapping[str, Any]],
    kalshi_names: Sequence[str],
    side: str,
    market_player: str,
) -> TennisReading:
    """The chance of one tennis leg from stored h2h quotes.

    `rows`: one dict per book per outcome, `bookmaker`, `outcome_name`,
    `price_decimal` (the `h2h` market only). `market_player` is the Kalshi name
    the leg's market is on. Outcomes match Kalshi's names by normalised name.

    A book counts only when BOTH players are quoted exactly once; the rest are
    dropped and named in `books_dropped`. The consensus anchors on sharp books
    only when at least two are two-sided (one thin exchange is not an anchor:
    Pegula v Andreeva had betfair alone at a 12.7% overround). YES is the
    lowest of the four methods for `market_player`; NO is the OTHER player's
    own lowest, which equals 1 - max(YES), never 1 - min(YES).
    """
    if side not in ("yes", "no"):
        return _refuse(UNKNOWN_SIDE)
    if len(kalshi_names) != 2:
        return _refuse(UNREADABLE_EVENT)
    norm = [normalise_name(n) for n in kalshi_names]
    mine = normalise_name(market_player)
    if mine not in norm or norm[0] == norm[1]:
        return _refuse(UNREADABLE_EVENT)
    me_i = norm.index(mine)

    by_book: dict[str, list[list[float]]] = {}
    dropped: dict[str, str] = {}
    for r in rows:
        book = r.get("bookmaker")
        key = normalise_name(r.get("outcome_name") or "")
        slots = by_book.setdefault(book, [[], []])
        if key in norm:
            try:
                slots[norm.index(key)].append(float(r["price_decimal"]))
            except (KeyError, TypeError, ValueError):
                dropped[book] = "unreadable_price"
        else:
            dropped[book] = "unmatched_name"

    quotes: dict[str, list[float]] = {}
    for book, (a, b) in by_book.items():
        if book in dropped:
            continue
        if not a or not b:
            dropped[book] = "one_sided"
        elif len(a) != 1 or len(b) != 1:
            dropped[book] = "ambiguous_duplicate"
        else:
            quotes[book] = [a[0], b[0]]

    if not quotes:
        return _refuse(NO_TWO_SIDED_BOOK, dropped)

    # Imported here: the runner will import this module (#446), not the reverse.
    from .runner import SHARP_BOOKS

    sharp_two_sided = sum(1 for b in quotes if b in SHARP_BOOKS)
    sharp = SHARP_BOOKS if sharp_two_sided >= MIN_SHARP_BOOKS else None
    labels = [kalshi_names[0], kalshi_names[1]]
    try:
        consensus, meta = consensus_devig(labels, quotes, sharp_books=sharp)
    except DevigError as exc:
        logger.debug("tennis devig failed: %s", exc)
        return _refuse(DEVIG_FAILED, dropped)

    for b in meta.get("books_rejected", ()):
        dropped[b] = "devig_rejected"
    asked = labels[me_i] if side == "yes" else labels[1 - me_i]
    return TennisReading(
        chance=consensus.conservative_probability(asked),
        reason=None,
        books_used=tuple(meta["books_used"]),
        books_dropped=dropped,
        anchored_on_sharp=bool(meta["anchored_on_sharp"]),
    )
