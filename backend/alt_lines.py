"""A devigged chance at ONE exact alternate line (#303 steps 2-3).

The desk prices one spread and one total per game: the books' current main
number. A friend's parlay sits on whatever number he took, and every other
line came back `not_served` or `stale_consensus`. The per-event odds endpoint
can return every line a book offers (`alternate_spreads`,
`alternate_totals`), stored by `odds/client.py` under those vendor keys. This
module turns the latest such fetch for one odds event into a chance at one
exact line.

**Alternate rows are read here and nowhere else.** They are never written to
`fair_prices` and never reach the main-line reads, which filter on
`market = 'spreads'` / `'totals'`.

How a line is priced
--------------------
Per book, a line counts only when BOTH sides are quoted: a spread is
(team A, p) with (team B, -p); a total is Over p with Under p. A one-sided
quote cannot be devigged -- there is no overround to remove -- so the book is
dropped and counted, never paired by guess. The survivors go through
`consensus_devig` (each book devigged first, then averaged) and the chance is
the lowest of the four methods for the side asked, per CLAUDE.md rule 2.

No sharp-book anchoring is applied: at an alternate line the number of
quoting books is small and varies, and a sharp-only subset would silently
turn a six-book reading into a one-book one. `books_used` says who spoke.

What this does not establish
----------------------------
* Nothing about whether the devigged chance beats Kalshi's price; this is a
  per-row fact, never an ordering (ADR 0071).
* Nothing about correlation between legs.
* Not a freshness guarantee: `age_ms` is the STALEST used book's own update
  time, and the caller decides what is too old.
* The point mapping to Kalshi's market wording is the caller's job, through
  `kalshi/spreads.spread_book_point` and `kalshi/totals.total_book_point`;
  `point` here is the sportsbook's own number.

**Unreadable resolves to `None` with a reason, never to 0.**
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from .core.devig import DevigError, consensus_devig
from .core.ladder import CandidateLeg
from .kalshi.spreads import (
    parse_spread_subtitle,
    spread_book_point,
    spread_margin_agrees,
)
from .kalshi.totals import parse_total_subtitle, total_book_point, total_line_agrees
from .match.linker import load_aliases, resolve_outcome

logger = logging.getLogger(__name__)

#: The market a caller names -> the vendor key it is stored under.
ALT_MARKET_KEYS: dict[str, str] = {
    "spreads": "alternate_spreads",
    "totals": "alternate_totals",
}

# Reason codes when no chance can be given.
NO_ALTERNATE_FETCH = "no_alternate_fetch"        # nothing stored for this event/market
NO_BOOK_AT_LINE = "no_book_at_line"              # no book quotes this point at all
NO_TWO_SIDED_BOOK = "no_two_sided_book"          # quoted, but only one-sided
DEVIG_FAILED = "devig_failed"
UNSUPPORTED_MARKET = "unsupported_market"
UNKNOWN_SIDE = "unknown_side"                    # a total's side is not Over/Under


@dataclass(frozen=True)
class AltLineChance:
    """The answer for one exact line. `chance is None` iff `reason` is set."""

    chance: Optional[float]
    reason: Optional[str]
    books_used: tuple[str, ...] = ()
    #: book -> why it was dropped ("one_sided" | "ambiguous_duplicate").
    books_dropped: dict[str, str] = field(default_factory=dict)
    #: now - the stalest used book's own update. `None` when nothing was used,
    #: or when a used book published no update time (unreadable, not zero).
    age_ms: Optional[int] = None
    fetched_ms: Optional[int] = None

    @property
    def one_sided_count(self) -> int:
        return sum(1 for r in self.books_dropped.values() if r == "one_sided")


def _none(reason: str, **kw) -> AltLineChance:
    return AltLineChance(chance=None, reason=reason, **kw)


def alt_line_chance(
    conn,
    odds_event_id: str,
    market: str,
    outcome_name: str,
    point: float,
    now_ms: int,
) -> AltLineChance:
    """Devigged chance of `outcome_name` at the sportsbook's `point`.

    `market` is `"spreads"` or `"totals"` (the main-line name; the alternate
    key is looked up). Spread: `outcome_name` is the team as the book spells
    it and `point` is that team's book point (a -6.5 cover is `-6.5`). Total:
    `outcome_name` is `"Over"` or `"Under"` and `point` is the line.
    """
    key = ALT_MARKET_KEYS.get(market)
    if key is None:
        return _none(UNSUPPORTED_MARKET)
    if market == "totals" and outcome_name not in ("Over", "Under"):
        return _none(UNKNOWN_SIDE)

    latest = conn.execute(
        "SELECT MAX(fetched_ms) AS m FROM odds_snapshots "
        "WHERE odds_event_id = ? AND market = ?",
        (odds_event_id, key),
    ).fetchone()
    if latest is None or latest["m"] is None:
        return _none(NO_ALTERNATE_FETCH)
    fetched_ms = int(latest["m"])

    rows = conn.execute(
        "SELECT bookmaker, outcome_name, outcome_point, price_decimal, "
        "book_updated_ms FROM odds_snapshots "
        "WHERE odds_event_id = ? AND market = ? AND fetched_ms = ?",
        (odds_event_id, key, fetched_ms),
    ).fetchall()

    # The complementary side, through the one identity each market already
    # has (no new arithmetic): a spread's other team sits at the negated
    # point; a total's other side sits at the same line.
    if market == "spreads":
        other_point = spread_book_point(point)
    else:
        other_point = total_book_point(point)
    other_total_name = "Under" if outcome_name == "Over" else "Over"

    by_book: dict[str, dict[str, list]] = {}
    for r in rows:
        if r["outcome_point"] is None:
            continue
        p = float(r["outcome_point"])
        if market == "spreads":
            if p == float(point) and r["outcome_name"] == outcome_name:
                side = "mine"
            elif p == other_point and r["outcome_name"] != outcome_name:
                side = "other"
            else:
                continue
        else:
            if p != float(point):
                continue
            if r["outcome_name"] == outcome_name:
                side = "mine"
            elif r["outcome_name"] == other_total_name:
                side = "other"
            else:
                continue
        by_book.setdefault(r["bookmaker"], {"mine": [], "other": []})[side].append(r)

    if not by_book:
        return _none(NO_BOOK_AT_LINE, fetched_ms=fetched_ms)

    dropped: dict[str, str] = {}
    quotes: dict[str, list[float]] = {}
    updated: dict[str, Optional[int]] = {}
    for book, sides in by_book.items():
        if not sides["mine"] or not sides["other"]:
            dropped[book] = "one_sided"
            continue
        if len(sides["mine"]) != 1 or len(sides["other"]) != 1:
            # Two prices for one outcome: no way to say which is current.
            dropped[book] = "ambiguous_duplicate"
            continue
        mine, other = sides["mine"][0], sides["other"][0]
        quotes[book] = [float(mine["price_decimal"]), float(other["price_decimal"])]
        updated[book] = (
            None if mine["book_updated_ms"] is None or other["book_updated_ms"] is None
            else min(int(mine["book_updated_ms"]), int(other["book_updated_ms"]))
        )

    if not quotes:
        return _none(NO_TWO_SIDED_BOOK, books_dropped=dropped, fetched_ms=fetched_ms)

    # Books may spell the other team differently; the devig only needs the
    # position, so a placeholder label is used for it.
    labels = [outcome_name, "\x00other"]
    try:
        consensus, meta = consensus_devig(labels, quotes)
    except DevigError as exc:
        logger.debug("alt line devig failed: %s", exc)
        return _none(DEVIG_FAILED, books_dropped=dropped, fetched_ms=fetched_ms)

    used = tuple(meta["books_used"])
    stamps = [updated[b] for b in used]
    age_ms = None if any(s is None for s in stamps) else now_ms - min(stamps)
    return AltLineChance(
        chance=consensus.conservative_probability(outcome_name),
        reason=None,
        books_used=used,
        books_dropped=dropped,
        age_ms=age_ms,
        fetched_ms=fetched_ms,
    )


# ---------------------------------------------------------------------------
# A Kalshi leg -> the book's line -> a CandidateLeg (#303 step 6)
# ---------------------------------------------------------------------------

#: Why a Kalshi leg could not be put to the alternate reading at all. Distinct
#: from the reasons above, which say why a line that WAS identified has no price.
NOT_A_LINE_MARKET = "not_a_line_market"      # moneyline, prop, or unknown market
UNREADABLE_LINE = "unreadable_line"          # subtitle grammar or strike cross-check failed
NO_ODDS_EVENT = "no_odds_event"              # no single event_links row for the Kalshi event
TEAM_UNRESOLVED = "team_unresolved"          # Kalshi's team did not resolve to a book name


@dataclass(frozen=True)
class AltLeg:
    """What the alternate reading says about one Kalshi leg.

    `candidate` is set only when the reading is usable as it stands; the
    caller still runs `core.ladder.unusable_reason` on it, so freshness has
    one spelling. `buyable` is True when the leg resolved to an exact book
    line on a known odds event -- a fresh alternate fetch could price it --
    whatever `reason` says about the reading on file now.
    """

    candidate: Optional[CandidateLeg]
    reason: Optional[str]
    odds_event_id: Optional[str] = None
    sport_key: Optional[str] = None
    buyable: bool = False
    reading: Optional[AltLineChance] = None


def alt_candidate_for_leg(
    conn,
    *,
    event_ticker: str,
    market_ticker: str,
    side: str,
    now_ms: int,
) -> AltLeg:
    """Price one Kalshi spread or total leg from the alternate lines on file.

    Every mapping step is one the main ladder already performs
    (`parlays.ladder_candidates`): the subtitle grammar, the strike
    cross-check, the one point identity, and `resolve_outcome` with the sport
    key's alias file. A step that cannot be done refuses with a reason; it is
    never guessed. A NO on a spread is the other team at +S, priced as its own
    side, never one minus the YES.
    """
    m = conn.execute(
        "SELECT ticker, title, yes_side_team, market_type, strike "
        "FROM kalshi_markets WHERE ticker = ?",
        (market_ticker,),
    ).fetchone()
    if m is None or m["market_type"] not in ("spread", "total"):
        return AltLeg(None, NOT_A_LINE_MARKET)
    if side not in ("yes", "no"):
        return AltLeg(None, UNKNOWN_SIDE)

    links = conn.execute(
        "SELECT odds_event_id FROM event_links WHERE kalshi_event_ticker = ?",
        (event_ticker,),
    ).fetchall()
    if len({r["odds_event_id"] for r in links}) != 1:
        return AltLeg(None, NO_ODDS_EVENT)
    odds_event_id = str(links[0]["odds_event_id"])

    game = conn.execute(
        "SELECT sport_key, commence_ms, home_team, away_team FROM odds_snapshots "
        "WHERE odds_event_id = ? ORDER BY fetched_ms DESC LIMIT 1",
        (odds_event_id,),
    ).fetchone()
    if game is None or game["commence_ms"] is None:
        return AltLeg(None, NO_ODDS_EVENT, odds_event_id=odds_event_id)
    sport_key = str(game["sport_key"])
    base = dict(odds_event_id=odds_event_id, sport_key=sport_key)

    if m["market_type"] == "spread":
        parsed = parse_spread_subtitle(m["yes_side_team"])
        if parsed is None or m["strike"] is None or not spread_margin_agrees(
            parsed[1], m["strike"]
        ):
            return AltLeg(None, UNREADABLE_LINE, **base)
        teams = [t for t in (game["home_team"], game["away_team"]) if t]
        favourite = resolve_outcome(parsed[0], teams, load_aliases(sport_key))
        others = [t for t in teams if t != favourite]
        if favourite is None or len(others) != 1:
            return AltLeg(None, TEAM_UNRESOLVED, **base)
        yes_point = spread_book_point(parsed[1])
        market, team = "spreads", favourite
        outcome, point = (
            (favourite, yes_point) if side == "yes" else (others[0], -yes_point)
        )
    else:
        line = parse_total_subtitle(m["yes_side_team"])
        if line is None or m["strike"] is None or not total_line_agrees(
            line, m["strike"]
        ):
            return AltLeg(None, UNREADABLE_LINE, **base)
        market, team = "totals", None
        outcome, point = ("Over" if side == "yes" else "Under"), total_book_point(line)

    reading = alt_line_chance(conn, odds_event_id, market, outcome, point, now_ms)
    leg_base = dict(base, buyable=True, reading=reading)
    if reading.chance is None:
        return AltLeg(None, reading.reason, **leg_base)

    candidate = CandidateLeg(
        label=m["yes_side_team"] or m["title"] or market_ticker,
        event_title=m["title"] or "",
        kalshi_event_ticker=event_ticker,
        kalshi_market_ticker=market_ticker,
        odds_event_id=odds_event_id,
        league=sport_key,
        commence_ms=int(game["commence_ms"]),
        market=market,
        team=team,
        point=point,
        p_conservative=reading.chance,
        # Only the conservative figure is carried; a method this reading did
        # not report is absent, never substituted (`JointEstimate.by_method`).
        p_by_method={},
        odds_age_now_ms=reading.age_ms,
        book_count=len(reading.books_used),
        books_used_json=json.dumps(list(reading.books_used)),
        anchored_on_sharp=False,
        side=side,
    )
    return AltLeg(candidate, None, **leg_base)
