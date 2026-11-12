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

**Two phrasings, one meaning (#418, captured 2026-11-12).** MLB, WNBA and NHL
say `"Over N <unit> scored"`. NFL, college football, NBA and men's college
basketball say `"Over N points"` with no `scored`. Until that capture the
grammar required the word, so every total in those four leagues parsed to
`None`, was counted under the generic `dropped_unresolved_outcome`, and wrote
no fair price: 2,718 of the 2,952 open total markets that day, the rest being
NHL's `goals`. `tests/fixtures/events_totals_by_series.json` carries one event
per listed series and a count over all of them. YES was the Over on every one
(`strike_type = "greater"`, and the rules text says "more than N").

WHAT THIS DOES NOT ESTABLISH
----------------------------
- That the subtitle grammar is stable. A new Kalshi phrasing fails to parse
  and the caller refuses that market rather than guessing.
- Anything about `TEAMTOTAL` (`market_type = "team_total"`). Its subtitle
  names a team AND a line -- two joins in one string -- and the book side is
  a fourth feed key (`team_totals`, another credit per region on every
  call). Out of scope; nothing here reads it.
- Anything about NHL. Its unit is `goals`, which is not in the whitelist, so
  an NHL total parses to `None` and is counted by name
  (`dropped_unknown_total_unit`). Kalshi's rules text counts overtime goals
  and scores a shootout as one goal to the winner; no sportsbook's house rule
  has been read against that. Do not add `goals` to make the count go away.
- That a Kalshi total and a sportsbook total settle alike in every case. The
  rules text names no overtime exclusion, which agrees with a book's full-game
  total. It differs on a postponed game: college football, NBA and men's
  college basketball resolve "to a fair price" where a book voids, and the NFL
  rules text read on 2026-11-12 carries no postponement clause at all.
- That `strike_type` is `"greater"` and `cap_strike` is absent on a market
  this prices. Both were so on every captured market, and they are the
  venue's own statement that YES is above the line, but discovery does not
  carry either field, so nothing here can check them.
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

#: `"Over 8.5 runs scored"` / `"Over 180.5 points scored"` / `"Over 44.5
#: points"`. The trailing `scored` is optional because four leagues omit it
#: (#418). `Over` is not optional and never will be: it is what makes YES the
#: book's `Over`, and a subtitle that says anything else must not parse.
_TOTAL_SUBTITLE = re.compile(
    rf"^Over (?P<line>\d+(?:\.\d+)?) (?P<unit>{_KNOWN_UNITS})(?: scored)?$"
)

#: The same grammar with the unit left open.
_TOTAL_UNIT_SHAPE = re.compile(
    r"^Over (?P<line>\d+(?:\.\d+)?) (?P<unit>\S+)(?: scored)?$"
)


def parse_total_subtitle(subtitle: Optional[str]) -> Optional[float]:
    """`"Over 8.5 runs scored"` -> `8.5`, `"Over 44.5 points"` -> `44.5`,
    else None.

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


def total_line_is_half_point(line: float) -> bool:
    """Whether a total's line ends in `.5`, so it cannot land exactly.

    **A whole-number line is two different contracts.** At a sportsbook a
    total that lands exactly on the line is a push and both sides are
    refunded; the devig prices Over and Under as if that outcome did not
    exist. Kalshi has no push: `strike_type = "greater"` sends the exact
    landing to NO. So on a whole number the book's Under and Kalshi's NO are
    not the same bet, and a fair price carried across is wrong by the chance
    of the push. No strike was a whole number among the 2,952 open total
    markets counted on 2026-11-12, or the 60 MLB and WNBA rungs in the older
    fixture; this refuses the day one is.
    """
    return (float(line) * 2) % 2 == 1


def total_line_agrees(line: float, strike: Optional[float]) -> bool:
    """Whether the subtitle's line and `floor_strike` are the same number,
    and that number is a half point.

    One number published twice. A disagreement means one copy is not what
    this code thinks it is, and the caller must refuse the market. A whole
    number is refused here too (:func:`total_line_is_half_point`), so every
    reader that cross-checks the line also refuses the push case.
    """
    if strike is None:
        return False
    if not total_line_is_half_point(line):
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
