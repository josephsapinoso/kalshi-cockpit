"""Kalshi spread (run-line / point-spread) markets: the one subtitle reader.

A spread market's `yes_sub_title` is the whole join key in prose:
`"St. Louis wins by over 2.5 runs"` names the team and the margin, and
`floor_strike` publishes the same margin as a number. This module is the ONE
place that prose is read — the runner's pricing path and the parlay desk's
reader both import it, so there are never two parsers for one wire format
(the rule `analyse_combo_domination` follows by loading its sibling by path).

The sportsbook side needs no parser: The Odds API publishes `spreads`
outcomes as `{name: team, point: ±N.5}`. The join identity, stated once:
Kalshi's "T wins by over S" YES == the book's `(T, point = -S)` — the
favorite laying S. The complementary book outcome `(other team, +S)` is the
same market's NO side.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- That the subtitle grammar is stable. The regex is pinned against every
  spread rung in the captured events fixture; a new Kalshi phrasing fails to
  parse and the caller refuses that market rather than guessing.
- Anything about totals. `"Combined score over N"` is a different market
  with a different subtitle, deliberately out of scope (ADR 0070).
"""

from __future__ import annotations

import re
from typing import Optional

#: `DiscoveredEvent.market_type` for a spread event, as
#: `discovery._SUFFIX_TO_MARKET_TYPE` spells it ("SPREAD" -> "spread").
MARKET_TYPE_SPREAD = "spread"

#: The margin units Kalshi has actually been observed publishing. Anchored
#: both ends. Deliberately a whitelist rather than `\w+`: an unrecognised unit
#: is a subtitle grammar this code has never seen, and guessing at it is how a
#: hockey line gets read as a baseball one.
#:
#: **This list is seasonal scope, not a closed set.** MLB ("runs") and the
#: basketball leagues ("points") are what the record contains; NHL ("goals")
#: and soccer will enter scope and parse to `None` here until they are added,
#: which is silent zero supply, not an error. `_SPREAD_UNIT_SHAPE` below
#: separates that case from a genuinely unparseable subtitle so a caller can
#: count it by name (2026-08-24 code review, finding 8).
_KNOWN_UNITS = r"runs?|points?"

#: `"St. Louis wins by over 2.5 runs"` / `"Indiana wins by over 18.5 points"`.
_SPREAD_SUBTITLE = re.compile(
    rf"^(?P<team>.+?) wins by over (?P<margin>\d+(?:\.\d+)?) (?P<unit>{_KNOWN_UNITS})$"
)

#: The same grammar with the unit left open. A subtitle that matches this but
#: not `_SPREAD_SUBTITLE` is the venue speaking our grammar in a unit we have
#: not whitelisted -- a fact about our scope, not about the payload.
_SPREAD_UNIT_SHAPE = re.compile(
    r"^(?P<team>.+?) wins by over (?P<margin>\d+(?:\.\d+)?) (?P<unit>\S+)$"
)


def parse_spread_subtitle(subtitle: Optional[str]) -> Optional[tuple[str, float]]:
    """`"St. Louis wins by over 2.5 runs"` -> `("St. Louis", 2.5)`, else None.

    `None` for anything the grammar does not cover — the caller must refuse
    the market, never fall back to the title or the strike alone. A parsed
    margin should be cross-checked against `kalshi_markets.strike`
    (`floor_strike` on the wire): the two publish one number twice, and a
    disagreement means one of them is not what this code thinks it is.
    Callers do that through :func:`spread_margin_agrees`, not by hand.
    """
    if not subtitle:
        return None
    matched = _SPREAD_SUBTITLE.match(subtitle.strip())
    if not matched:
        return None
    return matched.group("team"), float(matched.group("margin"))


def unrecognised_spread_unit(subtitle: Optional[str]) -> Optional[str]:
    """The unit of a subtitle that fits the grammar but not the whitelist.

    `"Boston wins by over 1.5 goals"` -> `"goals"`. `None` when the subtitle
    parses fine, or when it does not fit the grammar at all.

    Exists so a caller can count "a league whose unit we do not read" apart
    from "a subtitle we could not parse" and apart from "the books quote no
    price here". Without the split, NHL entering seasonal scope looks exactly
    like a quiet night, while the doubled `h2h,spreads` credit spend carries
    on regardless.
    """
    if not subtitle:
        return None
    text = subtitle.strip()
    if _SPREAD_SUBTITLE.match(text):
        return None
    shaped = _SPREAD_UNIT_SHAPE.match(text)
    return shaped.group("unit") if shaped else None


def spread_margin_agrees(margin: float, strike: Optional[float]) -> bool:
    """Whether the subtitle's margin and `floor_strike` are the same number.

    One number published twice. A disagreement means one of the two is not
    what this code thinks it is, and the caller must refuse the market:
    trusting either copy silently is how a 2.5-run line prices a 1.5-run
    market.
    """
    if strike is None:
        return False
    return float(margin) == float(strike)


def spread_book_point(margin: float) -> float:
    """The sportsbook `point` that Kalshi's `"T wins by over S"` YES is.

    **The join identity, in one place.** Kalshi sells only the favorite's
    cover, and the book publishes that same side as `(T, point = -S)` — the
    favorite laying S. The complementary book outcome `(other team, +S)` is
    the same Kalshi market's NO side, which is not a buyable leg.

    Trivial arithmetic, and that is the point: it was written out twice (the
    runner's pricing path and the parlay desk's reader) and a sign convention
    duplicated is a sign convention that can drift. 2026-08-24 code review,
    finding 9.
    """
    return -float(margin)
