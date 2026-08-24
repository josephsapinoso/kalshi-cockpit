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

#: `"St. Louis wins by over 2.5 runs"` / `"Indiana wins by over 18.5 points"`.
#: Anchored both ends; the unit is captured but unused — naming it keeps the
#: pattern honest about what it accepts.
_SPREAD_SUBTITLE = re.compile(
    r"^(?P<team>.+?) wins by over (?P<margin>\d+(?:\.\d+)?) (?P<unit>runs?|points?)$"
)


def parse_spread_subtitle(subtitle: Optional[str]) -> Optional[tuple[str, float]]:
    """`"St. Louis wins by over 2.5 runs"` -> `("St. Louis", 2.5)`, else None.

    `None` for anything the grammar does not cover — the caller must refuse
    the market, never fall back to the title or the strike alone. A parsed
    margin should be cross-checked against `kalshi_markets.strike`
    (`floor_strike` on the wire): the two publish one number twice, and a
    disagreement means one of them is not what this code thinks it is.
    """
    if not subtitle:
        return None
    matched = _SPREAD_SUBTITLE.match(subtitle.strip())
    if not matched:
        return None
    return matched.group("team"), float(matched.group("margin"))
