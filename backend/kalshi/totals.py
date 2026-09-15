"""Kalshi game-total (over/under) markets: the one subtitle reader.

A total market's `yes_sub_title` is the join key in prose: `"Over 8.5 runs
scored"` names the line, and `floor_strike` publishes the same line as a
number. This module is the ONE place that prose is read -- the runner's
pricing path and the parlay desk's reader both import it, the same rule
`backend/kalshi/spreads.py` follows, so there are never two parsers for one
wire format.

The sportsbook side needs no parser: The Odds API publishes `totals`
outcomes as `{name: "Over" | "Under", point: N.5}`. The join identity,
stated once: Kalshi's `"Over N.5 <unit> scored"` YES == the book's
`("Over", point = N.5)`; the book's `("Under", N.5)` is the same Kalshi
market's NO side. No negation (the spread identity) and no half-point shift
(the prop identity, where Kalshi says `N+` and `floor_strike` is already
`N - 0.5`): `floor_strike` on a total IS the book's point.

Measured, not assumed: every `KXMLBTOTAL` and `KXWNBATOTAL` rung in
`tests/fixtures/events_sports_nested.json` (33 + 27) parses here and its
line equals its own `floor_strike`; `strike_type` is `"greater"` on all of
them (`tests/test_totals_pricing.py`).

WHAT THIS DOES NOT ESTABLISH
----------------------------
- That the subtitle grammar is stable. A new Kalshi phrasing fails to parse
  and the caller refuses that market rather than guessing.
- Anything about `TEAMTOTAL` (`market_type = "team_total"`). Its subtitle
  names a team AND a line -- two joins in one string -- and the book side is
  a fourth feed key (`team_totals`, another credit per region on every
  call). Out of scope; nothing here reads it.
- Which unit NFL totals are published in. The whitelist below is what the
  record contains: `runs` (MLB) and `points` (WNBA). NFL is expected to say
  `points` -- the same expectation the spread parser carried until its NFL
  census -- and an NFL total in any other unit parses to `None` and is
  counted by name (`dropped_unknown_total_unit`), never guessed.
"""

from __future__ import annotations

import re
from typing import Optional

#: `DiscoveredEvent.market_type` for a total event, as
#: `discovery._SUFFIX_TO_MARKET_TYPE` spells it ("TOTAL" -> "total").
MARKET_TYPE_TOTAL = "total"

#: The `fair_prices.market` / `odds_snapshots.market` key the books publish
#: game totals under. One spelling, imported by both callers.
TOTALS_MARKET = "totals"

#: The units Kalshi has actually been observed publishing on a total. The
#: same seasonal-scope whitelist as `spreads._KNOWN_UNITS`, for the same
#: reason: an unrecognised unit is a grammar this code has never seen, and
#: `unrecognised_total_unit` lets a caller count it apart from a parse
#: failure so a whole league producing zero supply is not a quiet night.
_KNOWN_UNITS = r"runs?|points?"

#: `"Over 8.5 runs scored"` / `"Over 180.5 points scored"`.
_TOTAL_SUBTITLE = re.compile(
    rf"^Over (?P<line>\d+(?:\.\d+)?) (?P<unit>{_KNOWN_UNITS}) scored$"
)

#: The same grammar with the unit left open.
_TOTAL_UNIT_SHAPE = re.compile(
    r"^Over (?P<line>\d+(?:\.\d+)?) (?P<unit>\S+) scored$"
)


def parse_total_subtitle(subtitle: Optional[str]) -> Optional[float]:
    """`"Over 8.5 runs scored"` -> `8.5`, else None.

    `None` for anything the grammar does not cover -- the caller must refuse
    the market, never fall back to the title or the strike alone. A parsed
    line should be cross-checked against `kalshi_markets.strike`
    (`floor_strike` on the wire) through :func:`total_line_agrees`.
    """
    if not subtitle:
        return None
    matched = _TOTAL_SUBTITLE.match(subtitle.strip())
    if not matched:
        return None
    return float(matched.group("line"))


def unrecognised_total_unit(subtitle: Optional[str]) -> Optional[str]:
    """The unit of a subtitle that fits the grammar but not the whitelist.

    `"Over 5.5 goals scored"` -> `"goals"`. `None` when the subtitle parses
    fine, or when it does not fit the grammar at all.
    """
    if not subtitle:
        return None
    text = subtitle.strip()
    if _TOTAL_SUBTITLE.match(text):
        return None
    shaped = _TOTAL_UNIT_SHAPE.match(text)
    return shaped.group("unit") if shaped else None


def total_line_agrees(line: float, strike: Optional[float]) -> bool:
    """Whether the subtitle's line and `floor_strike` are the same number.

    One number published twice. A disagreement means one copy is not what
    this code thinks it is, and the caller must refuse the market.
    """
    if strike is None:
        return False
    return float(line) == float(strike)


def total_book_point(line: float) -> float:
    """The sportsbook `point` that Kalshi's `"Over L ... scored"` YES is.

    **The join identity, in one place.** It is the identity function, and
    that is worth a name: the spread identity negates and the prop identity
    would shift by a half-point, so a reader who knows those two and guesses
    at this one gets it wrong two ways out of three. Both callers (the
    runner's pricing arm and the parlay desk's reader) import this rather
    than comparing by hand, exactly as they do `spread_book_point`.
    """
    return float(line)
