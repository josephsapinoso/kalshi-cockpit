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

**NHL `goals` is read since #430 (2026-11-12), on the lines where the
overtime rule cannot matter.** Kalshi's `KXNHLTOTAL` `rules_secondary`:
"Goals scored during regulation and overtime count as normal. If the game is
decided by a shootout, the shootout result will be recorded as one goal
awarded to the winning team." DraftKings, one of the ten feed books, says the
same in its house rules filed with the Massachusetts Gaming Commission
(`DraftKings-House-Rules-8.1.24.pdf`, Ice Hockey, p. 95-96): "In the event of
the game being decided by a penalty shootout, one goal will be added to the
winning team's score and the game total for settlement purposes", "All
markets include overtime/shootout, unless otherwise stated", and its
pre-game "2 Way OU" is listed under "Pre-Game Markets Including Overtime
(and shootout)". DraftKings is not a sharp book, though, and the sharp
anchor (`core/devig.py`) draws on Pinnacle, Matchbook and Betfair, none of
whose rules was read (Pinnacle's help articles returned 404 that day).

So only the lines that settle alike under BOTH rules are priced. Overtime is
played only from a tied regulation score, which is an even total `2k`, and
it adds exactly one goal. On a line `N.5` that changes the result only when
`N = 2k`: 4.5 (2-2), 6.5 (3-3), 8.5 (4-4). On 3.5, 5.5 and 7.5 a game is
over or under the line at the end of regulation and overtime cannot move
it. :func:`total_line_depends_on_overtime` names the even-floor lines and
the parser refuses them, so all three callers (runner, parlay reader,
alt-line check) refuse them alike.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- That the subtitle grammar is stable. A new Kalshi phrasing fails to parse
  and the caller refuses that market rather than guessing.
- Anything about `TEAMTOTAL` (`market_type = "team_total"`). Its subtitle
  names a team AND a line -- two joins in one string -- and the book side is
  a fourth feed key (`team_totals`, another credit per region on every
  call). Out of scope; nothing here reads it.
- How any sharp book settles an NHL total, or which of a book's markets
  (overtime included or regulation only) The Odds API serves as `totals`.
  That is why the even-floor lines are refused rather than priced. Reopening
  them needs a sharp book's rule read, or a live comparison of the sharp
  books' devigged Under at 6.5 against DraftKings' (a regulation-only book
  would be several points richer there and agree at 5.5).
- Anything about the NHL puck line. `spreads._KNOWN_UNITS` still refuses
  `goals`; its settlement was not read.
- That a Kalshi total and a sportsbook total settle alike in every case. The
  rules text names no overtime exclusion, which agrees with a book's full-game
  total. It differs on a postponed game: college football, NBA and men's
  college basketball resolve "to a fair price" where a book voids, NHL does
  the same for a game not started within 48 hours, and the NFL rules text
  read on 2026-11-12 carries no postponement clause at all.
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
#: `goals` joined on #430 with the settlement rules read on both sides
#: (module docstring).
_KNOWN_UNITS = r"runs?|points?|goals?"

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
    if total_line_depends_on_overtime(subtitle):
        return None
    return float(matched.group("line"))


def total_line_depends_on_overtime(subtitle: Optional[str]) -> bool:
    """Whether a goals total sits where overtime can decide it (#430).

    `"Over 6.5 goals scored"` -> True (3-3 after regulation goes over only in
    overtime or the shootout); `"Over 5.5 goals scored"` -> False. Always
    False for runs and points, whose overtime rule is not in question here.
    A caller that sees `parse_total_subtitle` return None for a subtitle this
    calls True should count it apart from a parse failure.
    """
    if not subtitle:
        return False
    matched = _TOTAL_SUBTITLE.match(subtitle.strip())
    if not matched or not matched.group("unit").startswith("goal"):
        return False
    whole = float(matched.group("line")) // 1
    return whole % 2 == 0


def unrecognised_total_unit(subtitle: Optional[str]) -> Optional[str]:
    """The unit of a subtitle that fits the grammar but not the whitelist.

    `"Over 9.5 corners scored"` -> `"corners"`. `None` when the subtitle parses
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
