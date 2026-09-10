"""What a Kalshi player-prop market is, in one place.

Kalshi runs a ladder per player per game -- `KXMLBKS-26AUG151310CWSDET-CWSAKAY18-2`
is *Anthony Kay: 2+ strikeouts*, and the same event carries `-3`, `-4`, `-5` and
so on. This module holds the four facts the rest of the codebase needs about
that shape, and holds them **once**, because the alternative is what this repo
has been burned by twice: two readers of one wire format, drifting apart in
silence.

`scripts/probe_prop_dispersion.py` proved these on a live slate before any of it
was wired into production -- 227 of 227 subtitles parsed, 0 player collisions --
and now imports from here rather than keeping its own copy.

THE JOIN, AND WHY IT NEEDS NO ARITHMETIC
----------------------------------------
Kalshi's `N+` is the sportsbooks' `Over N-0.5`. That identity was originally
*derived* -- `threshold = point + 0.5` -- which is a computation, and a
computation on a money path is a thing that can be wrong.

It does not have to be derived. Kalshi publishes `floor_strike` on every prop
market and it is **already** `N - 0.5`: the `2+` market above carries
`floor_strike = 1.5`, which is exactly the `point` a book quotes on the same
line. Measured on `tests/fixtures/events_mlb_props_nested.json`: 259 of 259
markets, zero exceptions, across a pitcher series and a batter series.

So the join key is `kalshi_markets.strike == odds_snapshots.outcome_point`, a
direct equality between two numbers each source published itself. Nothing is
added, nothing is rounded, and `tests/test_discovery.py` pins the identity so
that a Kalshi change to `floor_strike` turns a test red instead of quietly
shifting every prop comparison by one rung.

**Key on (player, point), never on team.** A player name is unique within an MLB
slate, so this removes the team-abbreviation mapping problem entirely rather
than solving it. A name that does collide across two games is *reported*, never
silently resolved.

WHAT THIS MODULE DOES NOT DECIDE
--------------------------------
- **Not whether a prop is worth betting.** `tasks/NEXT.md` records that at the
  deployed fee coefficient the prop probe found zero clearing rows with a real
  consensus. Nothing here changes a fee or surfaces a row.
- **Not which books are trustworthy.** Eight books quote props and none of them
  is Pinnacle or Betfair, so `anchored_on_sharp` is 0 across the whole
  population by construction -- correct, and not a defect to paper over.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

# ---------------------------------------------------------------------------
# The five MLB prop series, mapped to the Odds API market key that quotes the
# same quantity.
#
# **This is the allowlist, and the series ticker is deliberately the thing it
# keys on.** The obvious alternative -- `product_metadata.competition_scope` --
# does not work here, and the reason is worth stating rather than rediscovering:
# Kalshi scopes a prop ladder by the *statistic*, one string per series.
# `KXMLBKS` events carry `"Strikeouts"`; `KXMLBTB` carries `"Total Bases"`
# (captured 2026-08-15). Admitting props on the scope axis would therefore need
# one capture per series, and guessing the other three spellings is precisely
# what silently dropped WNBA and NCAAF from the universe once already -- see
# `IN_SCOPE_LEAGUES` in `discovery.py`.
#
# The series ticker is what we actually know, so it is what the gate reads.
# ---------------------------------------------------------------------------
MLB_PROP_SERIES: dict[str, str] = {
    "KXMLBKS": "pitcher_strikeouts",
    "KXMLBTB": "batter_total_bases",
    "KXMLBHIT": "batter_hits",
    "KXMLBHR": "batter_home_runs",
    "KXMLBRBI": "batter_rbis",
}

# ---------------------------------------------------------------------------
# The three NFL yardage ladders. **Measured, not guessed, and STAGED rather
# than live** -- see `PROP_SERIES` below for why this is not simply merged in.
#
# Captured 2026-09-10 into `tests/fixtures/events_nfl_props_nested.json`
# (`scripts/capture_nfl_prop_fixture.py`, unauthenticated, no credits). The
# capture existed to find out whether NFL needed a second subtitle grammar and
# a second join rule. It needs neither:
#
#     series          markets   SUBTITLE parsed   floor_strike == N - 0.5
#     KXNFLPASSYDS        253       253 / 253            253 / 253
#     KXNFLRECYDS       1,160     1,160 / 1,160        1,160 / 1,160
#     KXNFLRSHYDS         616       616 / 616            616 / 616
#
# 2,029 of 2,029 on both counts, across three magnitudes (hundreds of passing
# yards, tens of rushing). So the MLB grammar `"Player: N+"` and the MLB join
# identity are properties of Kalshi's prop ladder, not of baseball, and this
# module needed **no new parser** -- which is the finding, and is why nothing
# below this line adds one.
#
# `competition` is `"Pro Football"` and `competition_scope` is the statistic
# (`"Passing Yards"`, `"Receiving Yards"`, `"Rushing Yards"`); every market
# carries `occurrence_datetime` and `strike_type = "greater"`.
#
# The Odds API keys were read from the vendor's own market table on
# 2026-09-10, not recalled: a wrong key does not error, it buys nothing.
# ---------------------------------------------------------------------------
NFL_PROP_SERIES: dict[str, str] = {
    "KXNFLPASSYDS": "player_pass_yds",
    "KXNFLRECYDS": "player_reception_yds",
    "KXNFLRSHYDS": "player_rush_yds",
}

# ---------------------------------------------------------------------------
# Prop series that carry **no strike**, and therefore join to nothing.
#
# `KXNFLFIRSTTD` is a player-per-market list -- `yes_sub_title` is a bare
# `"Kyren Williams"`, `floor_strike` is absent on 362 of 362 markets, and
# `strike_type` is `"structured"` rather than `"greater"`. `parse_subtitle`
# returns `None` on every one of them, which is the correct refusal and not a
# defect to loosen the regex around: there is no rung, so there is nothing for
# `kalshi_markets.strike == odds_snapshots.outcome_point` to match on.
#
# `KXNFLANYTD` had **0 open events** at capture, so nothing about its shape is
# established here. It is listed because `tasks/NEXT.md` named it, and an
# absent series must not be mistaken for a measured one.
#
# The Odds API does quote both (`player_1st_td`, `player_anytime_td`) as
# Yes/No rather than Over/Under. Admitting them would need a join that does not
# run on a strike -- a different mechanism, and its own decision.
# ---------------------------------------------------------------------------
PROP_SERIES_NO_STRIKE: frozenset[str] = frozenset({"KXNFLFIRSTTD", "KXNFLANYTD"})

# ---------------------------------------------------------------------------
# THE LIVE ALLOWLIST. **MLB only, deliberately, until the odds path thaws.**
#
# `NFL_PROP_SERIES` is correct and tested and is still not merged here, because
# this dict is read by two things that would then disagree:
#
#   1. `is_prop_series` -> `discovery.py:390`, which decides what gets ADMITTED
#      into `kalshi_markets`. Adding NFL here starts writing ~2,000 prop
#      markets a slate to a database already growing at 326.6 MB/day.
#   2. `PROP_SERIES.get` -> `runner.py:1697`, which maps a series to the book
#      market it is priced against. The books are fetched by
#      `odds/client.prop_market_keys()`, a FLAT list whose length is the price
#      of a prop event -- one credit per key per region. NFL keys added there
#      would be requested on every MLB event too, taking a five-key event to
#      eight for three keys that return nothing.
#
# So the buy side has to become sport-aware in the same edit, and
# `backend/odds/` is frozen until 10:00Z 2026-09-14 (`tasks/NEXT.md` item 1).
# Enabling NFL props is therefore ONE edit here plus a sport-aware
# `prop_market_keys()`, and neither half is safe alone: admitted-but-unbought
# props are rows nobody prices, and bought-but-unadmitted props are credits
# spent on markets nothing reads.
#
#     PROP_SERIES = {**MLB_PROP_SERIES, **NFL_PROP_SERIES}
#
# One open question the MLB record does NOT answer for NFL: whether the
# `_alternate` feeds are needed. MLB refuses them because 35,448 alternate
# rungs carried zero Unders, so they cannot be devigged. But Kalshi's NFL
# ladder is `N+` milestones, which is exactly what the vendor says the
# alternate feeds cover -- so the primary may quote one line where Kalshi
# prices twenty rungs. Unmeasured. Measure before spending.
# ---------------------------------------------------------------------------
PROP_SERIES: dict[str, str] = dict(MLB_PROP_SERIES)

# `market_type` for everything in `PROP_SERIES`. The fifth value the column
# takes, beside moneyline / spread / total / team_total.
MARKET_TYPE_PROP = "prop"

# The `competition_scope` strings that have actually been **read from a
# payload**, lowercased. Only two, because only two series were captured, and a
# guessed third would be indistinguishable from a measured one to every future
# reader of this file.
#
# Nothing branches on this set -- `PROP_SERIES` is the gate. It exists so the
# scope drift test in `tests/test_discovery.py` stays meaningful over the prop
# fixture instead of being given a blanket exemption.
PROP_SCOPES: frozenset[str] = frozenset({"strikeouts", "total bases"})

# Requested alongside the primary feeds. A book quotes one primary line per
# player (`Over 3.5`) while Kalshi prices the whole ladder, so matching
# primaries alone compares one rung in seven: measured at 48 of 263 Kalshi
# markets on the 2026-08-14 slate, against ~222 with the alternates.
ALTERNATE_SUFFIX = "_alternate"

#: `"Clay Holmes: 4+"` -> `("Clay Holmes", 4)`. Proven on 227 of 227 live
#: subtitles by the scoping probe, and on 259 of 259 in the captured fixture.
SUBTITLE = re.compile(r"^(?P<player>.+?):\s*(?P<threshold>\d+)\+\s*$")


def parse_subtitle(subtitle: Optional[str]) -> Optional[tuple[str, int]]:
    """`yes_sub_title` -> `(player, threshold)`, or `None` when unreadable.

    `None`, never a partial guess and never a zero. A subtitle this cannot read
    is a market shape nobody has seen, and the caller's job is to refuse it and
    count it -- not to substitute a player name from the title and carry on.
    That rule is the repo's, and it is in `tasks/lessons.md` because breaking it
    is what turns an unparsed field into a confident wrong answer.

    The threshold is returned for reporting and for the collision key. It is
    **not** what joins to a book: see the module docstring -- the join runs on
    `floor_strike`, which Kalshi publishes as `threshold - 0.5` itself.
    """
    matched = SUBTITLE.match(subtitle or "")
    if not matched:
        return None
    return matched.group("player").strip(), int(matched.group("threshold"))


def norm(name: str) -> str:
    """Casefold, fold diacritics, strip punctuation. `José` matches `Jose`.

    Deliberately narrow. It removes case, diacritics and punctuation -- the
    three things the two sources genuinely disagree about -- and nothing else:
    no nickname table, no fuzzy distance, no dropping of suffixes like `Jr`. A
    matcher that guesses is a matcher that pairs two different players and
    produces an entirely plausible edge.

    THE DIACRITIC FOLD IS NOT COSMETIC, AND IT WAS SILENTLY DROPPING STARS
    ---------------------------------------------------------------------
    Until 2026-08-17 this stripped diacritics by **deleting** them, because
    `[^a-z0-9 ]` does not match `á` -- so `José Ramírez` normalised to
    `jos ramrez`. That is not a spelling either source uses, so it matched
    nothing and the player fell out of the join in silence.

    The two sources genuinely disagree here, measured on the live record:

        Kalshi     411 prop players,  28 carry diacritics  (6.8%)
        Odds API   335 prop players,   2 carry diacritics  (0.6%)

    The Odds API strips them; Kalshi keeps them. Folding rather than deleting
    recovers **18 players** -- 297 joined names becomes 315 -- and they are not
    marginal names: Ronald Acuña Jr., José Ramírez, Julio Rodríguez, Eugenio
    Suárez, Teoscar Hernández, Jeremy Peña. Prop liquidity concentrates on
    exactly these hitters, so the defect was removing the most tradeable rows in
    the series and leaving no trace that it had.

    **Folding can in principle merge two distinct players** (`Peña` and `Pena`
    as different people). That is the correct failure mode for this module and
    is unchanged by the fix: the module's rule is that a collision is
    *reported*, never silently resolved, and callers key on `(player, point)`
    and check uniqueness. Deleting the character had the same collision risk
    while also matching nobody.
    """
    decomposed = unicodedata.normalize("NFKD", name)
    folded = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9 ]", "", folded.lower()).strip()


def base_market(key: str) -> str:
    """`pitcher_strikeouts_alternate` -> `pitcher_strikeouts`.

    Primary and alternate feeds quote the same quantity at different lines, so
    they must land in the same bucket. Kept apart, one player would appear twice
    with two "consensuses" built from disjoint book sets, and each would look
    like an independent confirmation of the other.
    """
    return key[: -len(ALTERNATE_SUFFIX)] if key.endswith(ALTERNATE_SUFFIX) else key


def is_prop_series(series_ticker: Optional[str]) -> bool:
    """Whether this series is one of the five prop ladders."""
    return (series_ticker or "") in PROP_SERIES
