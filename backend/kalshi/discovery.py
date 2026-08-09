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
from .grid import PriceGrid, read_price_grid

logger = logging.getLogger(__name__)

# (series_ticker, scope) pairs already reported, for the life of the **process**.
# Kalshi carries the same scope on every market in a series, so without this one
# unknown scope produces one warning per market.
#
# It used to be cleared at the top of every pass, so that a long-running runner
# could not warn once at boot and then go quiet. Both halves of that were
# individually defended in prose and together they produced the thing the dedupe
# existed to prevent: measured on the live instance 2026-08-08, **98 of the 100
# lines in the log buffer** were this one warning, re-emitted every pass -- and a
# quote pass runs every 15s while the window is open. It buried the boot lines
# (`[migrate] ...`, `API starting: ...`) so completely that neither could be read
# from production at all.
#
# The split that resolves it: the warning names a *developer action item* ("add
# it to FIXTURE_SCOPES"), which cannot change within a process and is worth
# saying once; the *number* of unknown scopes is an operational state and is
# reported on every pass by the `discovery:` summary line, always, even at zero.
# Silence therefore never means "the problem went away" -- the count says so.
# See tasks/lessons.md on rejection logs dominated by their majority case.
#
# **That fix was right and its cardinality was wrong.** "Say it once" was written
# believing "once" meant ~94 lines, which is what `flyctl logs` showed. Measured
# against the live exchange 2026-08-09 (`scripts/measure_unknown_scopes.py`) the
# real population is **962 (series, scope) pairs over 317 scopes**, emitted in
# ~90ms. The 94 was not the population; it was the ~10% of a burst that Fly's
# log pipeline did not drop. So the first pass of every fresh process still
# overran the 100-line buffer nine times over, still buried the boot lines, and
# additionally destroyed unrelated neighbouring lines as collateral -- the
# `discovery:` summary emitted immediately afterwards never arrived either.
#
# One warning per process now, aggregated, emitted from `discover_from_events`
# rather than per event from `classify_series`. The action item is per *scope*,
# not per (series, scope) -- `FIXTURE_SCOPES` is keyed by scope string -- and a
# scope in a league this project cannot devig against is not an action item at
# all, so those are counted rather than named. 962 lines becomes one.
_WARNED_SCOPES: set[tuple[str, str]] = set()

# Unknown (series, scope) pairs seen in the pass currently running, mapped to the
# league each was seen under. Cleared per pass, unlike `_WARNED_SCOPES`, because
# it feeds the count. The league is carried so the warning can separate "a market
# type we might want" from "a scope in a league we do not price".
_UNKNOWN_SCOPES_THIS_PASS: dict[tuple[str, str], str] = {}

# Cap on how many scopes one warning names. A developer action item that runs to
# hundreds of entries is not actionable, and the point of this line is that it
# must not itself become the flood it replaced.
_MAX_SCOPES_NAMED = 40

# The same three pieces, one axis over: leagues nobody has classified.
#
# `competition_scope` had an aggregated warning and a drift test. `competition`
# had neither, so `"Pro Football Preseason"` -- one string away from the
# `"Pro Football"` in `IN_SCOPE_LEAGUES` -- dropped 48 events and 726 markets in
# total silence. See `OUT_OF_SCOPE_LEAGUES`.
#
# Deduped on the **league** rather than on `(series, league)`, unlike the scope
# warning, because the action item is per league: "classify this value". Kalshi
# lists one league across many series (`KXNFLGAME`, `KXNFLSPREAD`,
# `KXNFLTOTAL`), so a per-pair key would say the same thing three times and grow
# with the number of market types Kalshi ships. The series are still carried, on
# the line, as the evidence for where the value was seen.
_WARNED_LEAGUES: set[str] = set()

# league -> series tickers it was seen on, for the pass currently running.
# Cleared per pass because it feeds the count on the `discovery:` line; the
# naming is per process. Same split as `_WARNED_SCOPES` /
# `_UNKNOWN_SCOPES_THIS_PASS`, for the same reason: a developer action item
# cannot change within a process, an operational count changes every pass.
_UNKNOWN_LEAGUES_THIS_PASS: dict[str, set[str]] = {}

# Cap on how many leagues one warning names, for the same reason as
# `_MAX_SCOPES_NAMED`. It bites: measured against the live exchange on
# 2026-08-09, ~100 leagues carry game-level markets and are unclassified, so the
# uncapped line would be a flood folded into one record.
_MAX_LEAGUES_NAMED = 40

# The last `discovery:` summary actually logged, as the tuple that line renders.
#
# The summary prints unconditionally on a full pass and, on a quote pass, only
# when it differs from this. Both halves are load-bearing and neither works
# alone.
#
# Printing every pass was right at one cadence and wrong at the next. It was
# written when a pass meant 900s -- 96 lines a day, and the argument for
# unconditional printing is that a pass saying nothing about unknown scopes must
# be distinguishable from a pass that found none. Then the odds budget went from
# 16 credits a day to 400, the window stopped closing, and quote passes began
# running every ~22s: the same line, bit-identical (`166 priceable events;
# unknown_scopes=965`), roughly 3,900 times a day. The 100-line `flyctl logs`
# buffer covers about twelve minutes of that.
#
# So this is the 962-line scope burst again, one order of magnitude slower and
# arrived at from the opposite direction -- not a loop that forgot to
# deduplicate, but a correct per-pass line meeting a cadence forty times faster
# than the one it was sized for. **A logging rate is a function of the caller,
# and a line that is cheap at one cadence is a flood at another.**
#
# Change-detection alone would reintroduce exactly the ambiguity the
# unconditional print exists to prevent: silence would once again fail to
# distinguish "nothing new" from "discovery did not run". The full pass is the
# heartbeat that rules that out -- at least one line every 900s, whatever
# happens -- and the change check carries anything that moves in between.
_LAST_SUMMARY: Optional[tuple] = None

# Series already reported as game-level with no `occurrence_datetime`. Same
# hazard as the scope warning one branch away: it was per event and undeduped,
# so a day on which Kalshi omits the field across a league floods the stream
# exactly as the scope warning did. It has never fired on live, which is
# precisely why it was easy to miss.
_WARNED_NO_COMMENCE: set[str] = set()

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

# Period markets: they DO resolve on a single fixture, and they are still not
# priceable here. A 1st-quarter spread is one game, one line -- but the
# consensus this project devigs against is game-level, so there is no reference
# price to compare a quarter against and no way to tell a real edge from a
# missing one. See docs/adr/0013.
#
# They are listed separately from `NON_FIXTURE_SCOPES` rather than dropped into
# it because the two are excluded for different reasons, and a future reader
# deciding whether to price one needs to know which reason applies: a future is
# excluded because it is not a fixture, and no data source changes that; a
# quarter is excluded because of what *we* subscribe to, which a period-level
# odds feed would change.
#
# Kalshi's exact spelling, lowercased -- read from the live warning on
# 2026-08-09, not guessed. Guessing scope spellings is what silently discarded
# every spread and total in the universe; see tasks/lessons.md, "Test that the
# filter's *exclusions* are decisions".
PERIOD_SCOPES: frozenset[str] = frozenset(
    f"{ordinal} quarter {market}"
    for ordinal in ("1st", "2nd", "3rd", "4th")
    for market in ("spread", "total", "winner")
)

# Every scope this project has classified as "excluded, deliberately".
#
# This is what makes the unrecognised-scope warning mean *"nobody has looked at
# this value"* rather than *"we looked and said no"*. The warning names a
# developer action item, and an action item that reprints every boot for a
# decision already taken trains the reader to stop reading it -- which is the
# state the whole aggregation work on `_WARNED_SCOPES` exists to avoid.
#
# Adding to this set must never be the reflex for silencing the warning. The
# warning firing for an unclassified value is the safety property; only a scope
# somebody has actually looked at belongs here.
EXCLUDED_SCOPES: frozenset[str] = NON_FIXTURE_SCOPES | PERIOD_SCOPES

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

# Leagues that carry game-level markets and are excluded **on purpose**, with the
# reason per entry. `EXCLUDED_SCOPES` for the other axis.
#
# This map changes nothing about what gets priced -- `sport_key` still comes from
# `IN_SCOPE_LEAGUES` alone. What it changes is that an absent league is an
# unanswered question rather than an answered one, so the warning below can mean
# *"nobody has looked at this value"* instead of *"we looked and said no"*.
#
# It exists because the accident it prevents happened, twice, one value apart.
# The comment on `IN_SCOPE_LEAGUES` records the first: "Womens Pro Basketball"
# and "College Football" were guessed, Kalshi says "Pro Basketball (W)" and
# "NCAA Football", and both leagues vanished from the Board in silence. The
# second is the entry at the top of this map -- `"Pro Football"` is in scope and
# Kalshi spells preseason `"Pro Football Preseason"`, which is a different
# string, so **48 events and 726 markets** were dropped with no warning, no
# counter and no red test (measured against the live exchange, 2026-08-09).
#
# The scope axis had an aggregated warning and a drift test against the captured
# payloads. The league axis had neither, and a comment explaining one instance of
# a hazard is not evidence the hazard was handled everywhere.
#
# **Adding an entry here must never be the reflex for silencing the warning.**
# The warning firing on an unclassified value is the safety property. On the live
# exchange roughly a hundred leagues carry game-level markets and are dropped;
# they are deliberately left unclassified and loud, because nobody has looked at
# them and a one-line reason copy-pasted a hundred times would say so falsely.
# Only a league somebody has actually decided about belongs here.
OUT_OF_SCOPE_LEAGUES: dict[str, str] = {
    # **This is a decision Joe owns, and it is recorded, not taken here.**
    #
    # For excluding: preseason football is a different generating process.
    # Starters play limited snaps, outcomes turn on roster and playing-time
    # decisions that no power rating contains, and the sportsbook consensus this
    # project devigs is itself thinner and later-forming there. Including it
    # mixes two populations in one evidence record.
    #
    # Against excluding: it is real volume in August, when the in-scope slate is
    # thin -- a measured 19-game day, MLB and WNBA only -- and the gate's counter
    # needs independent games.
    #
    # What makes it a decision rather than a toggle: rows written before and
    # after the switch would not be poolable, and **nothing in the schema marks
    # which population a row came from**. `recommendations` stores `ticker` only;
    # the sole league cut in the analysis path joins
    # `recommendations.ticker -> kalshi_markets.series_ticker ->
    # kalshi_series.league` (`backend/analysis/clv.py`), and `KXNFLGAME`,
    # `KXNFLSPREAD` and `KXNFLTOTAL` each carry *both* league strings --
    # preseason and regular season, same series, same `competition_scope`
    # ("Game"), differing only in `product_metadata.competition`. Worse,
    # `kalshi_series.league` is written on first insert and never updated
    # (`upsert_discovered`'s `ON CONFLICT` sets `last_seen_ms` only), so that one
    # row would freeze on whichever population was seen first and silently
    # relabel every row on both sides of the switch, retroactively. See
    # `tests/fixtures/events_nfl_preseason.json`, which pins exactly that shape.
    "Pro Football Preseason": (
        "a different generating process from the regular season -- limited "
        "starter snaps, roster-decision outcomes no power rating carries, and a "
        "thinner consensus to devig. Excluded so the evidence record holds one "
        "population. Including it is Joe's call and needs a population column "
        "first: the series ticker cannot split it, because KXNFLGAME carries "
        "both leagues."
    ),
    # ADR 0001: out of scope for v1, and named there. Not permanent -- both are
    # config, not code.
    "MLS": (
        "the long tail of soccer: thin, and each league needs its own alias "
        "table before it can be matched at all. ADR 0001."
    ),
    "CFL": (
        "spread markets only, and no Odds API consensus subscribed for it. "
        "ADR 0001 lists it as observed, not in scope."
    ),
    "League of Legends": (
        "esports -- no sportsbook consensus worth devigging against on The Odds "
        "API. ADR 0001."
    ),
    "Valorant": (
        "esports -- no sportsbook consensus worth devigging against on The Odds "
        "API. ADR 0001."
    ),
    "CS2": (
        "esports -- no sportsbook consensus worth devigging against on The Odds "
        "API. ADR 0001."
    ),
    "Dota 2": (
        "esports -- no sportsbook consensus worth devigging against on The Odds "
        "API. ADR 0001."
    ),
}

# Leagues already classified either way. A value outside this set is what the
# warning below is for.
CLASSIFIED_LEAGUES: frozenset[str] = frozenset(IN_SCOPE_LEAGUES) | frozenset(
    OUT_OF_SCOPE_LEAGUES
)

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
    elif normalised_scope in EXCLUDED_SCOPES:
        # Known, and decided against -- a future, an award, or a period market.
        # Silent on purpose: the decision is recorded in `EXCLUDED_SCOPES` and
        # docs/adr/0013, so repeating it in the log every boot says nothing.
        is_game_level = False
    elif normalised_scope:
        # A scope we have never seen. Treat it as not-per-fixture (the safe
        # direction: we decline to price rather than pricing something we do
        # not understand) but say so loudly, because it may be a market type
        # we want. The drift test in tests/test_discovery.py fails on this too.
        is_game_level = False
        # Counted every pass, named once per process -- but the naming happens in
        # `discover_from_events`, as a single aggregated line. Warning here, per
        # event, is what produced a 962-line burst; see `_WARNED_SCOPES`.
        _UNKNOWN_SCOPES_THIS_PASS[(series_ticker, scope)] = league or ""
    else:
        is_game_level = market_type is not None
        if series_ticker:
            logger.debug(
                "%s has no competition_scope; falling back to the ticker suffix",
                series_ticker,
            )

    # A league nobody has classified, on a market we would otherwise price.
    #
    # Gated on `is_game_level` deliberately. Kalshi puts a `competition` on
    # elections, companies and crypto too -- 352 distinct values live, of which
    # roughly a hundred carry a game-level market. `House` and `Tesla Inc.` are
    # not an unanswered question about league scope, and naming them would make
    # the line unreadable, which is the failure the aggregation exists to
    # prevent. The question this warning asks is "should this league be devigged
    # against?", and that question only exists where there is a fixture to price.
    #
    # Counted every pass, named once per process, and the naming happens in
    # `discover_from_events` as a single aggregated line -- never here, per
    # event. Warning per event is what produced the 962-line burst on the scope
    # axis; see `_WARNED_SCOPES`.
    if is_game_level and league and league not in CLASSIFIED_LEAGUES:
        _UNKNOWN_LEAGUES_THIS_PASS.setdefault(league, set()).add(series_ticker)

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
    # Which limit prices this market will accept, parsed from `price_ranges`.
    # `price_structure` above is the *label* for the same thing and must not be
    # branched on -- Kalshi introduces new structures over time, and a client
    # reading the bands is compatible with all of them.
    #
    # `None` means the grid was unreadable, and the order path refuses on it.
    # There is no default: assuming whole cents is what made a 50.5c ask rest
    # at 50c and never fill. See `kalshi/grid.py`.
    price_grid: Optional[PriceGrid] = None

    # Kalshi's own settled outcome, `None` while it is not known. See
    # `read_market_result` for why `None` and `"no"` must not be confused.
    #
    # On today's exchange this is `None` for every market discovery sees: the
    # `/events?status=open` walk carries only `active` markets. It is read here
    # anyway because the alternative -- a field the parser does not look at --
    # is how a payload change goes unnoticed, and because a market that settles
    # early inside a still-open event is a shape this project has not disproved.
    # `market_results.py` is what actually fills the column.
    result: Optional[str] = None


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


# The only `status` that means a market's outcome is known, and the two values
# `result` then takes. Both measured against `tests/fixtures/markets_settled.json`
# rather than documented: 42 of 42 markets returned by `?status=settled` report
# `finalized`, and `finalized` is itself rejected as a filter with HTTP 400.
#
# `backend/settlement.py` holds the same two facts for the paper-P&L path, where
# it needs to *raise* rather than return `None`. They are two readers of one wire
# format, which this project has been burned by before, so
# `tests/test_market_results.py` asserts they agree on all 44 captured markets --
# neither can drift alone without a red test.
SETTLED_STATUS = "finalized"
RESULTS = frozenset({"yes", "no"})

# The payload states the outcome twice. Cross-checked because it costs nothing
# and is the only independent reading available.
SETTLEMENT_VALUE = {"yes": "1.0000", "no": "0.0000"}


def read_market_result(market: dict) -> Optional[str]:
    """A market's settled outcome, or `None` if it is not known and trustworthy.

    **`None` is not `"no"`.** Kalshi sends `result` as the empty string on every
    market whose outcome is unpublished -- all 245 markets in the nested-events
    capture and all 168 live game markets probed on 2026-08-09 read `""` -- so a
    reader that treated a falsy `result` as a loss would record a loss for every
    open market on the exchange. That is the `unreadable-never-zero` rule of
    `tasks/lessons.md` in its most expensive form: this column is destined for
    calibration, where a fabricated `no` is not a refused trade but a permanent
    wrong answer.

    Three states collapse to `None` here, deliberately, because discovery must
    not fail a whole pass over one odd market: not settled yet, settled but
    self-contradictory, and a status this parser does not recognise. The strict
    sibling `settlement.read_outcome` raises on the latter two instead, and its
    refusals are counted where they can be seen. Use that one when a payload
    arriving unreadable is news; use this one where the answer is simply absent.
    """
    if market.get("status") != SETTLED_STATUS:
        return None

    result = market.get("result")
    if result not in RESULTS:
        return None

    value = market.get("settlement_value_dollars")
    if value is not None and value != SETTLEMENT_VALUE[result]:
        # The payload contradicts itself, so neither reading is trustworthy.
        return None

    return result


def build_market(
    market: dict,
    *,
    market_type: str,
    event_ticker: str = "",
    series_ticker: str = "",
) -> DiscoveredMarket:
    """Parse one Kalshi market object. **The only reader of these field names.**

    Split out from `build_markets` so the order path's quote refresh
    (`kalshi/quotes.py`) parses `GET /markets/{ticker}` through this exact
    function rather than a second one. Two parsers for one wire format is how
    `apply_snapshot` came to read `data["yes"]` while the socket sent
    `yes_dollars_fp` -- and the refresh sits on the money path, where a quote
    that silently parses to `None` is a refusal and one that silently parses to
    the wrong field is a fill at a price nobody checked.

    `event_ticker` and `series_ticker` are passed in because the nested
    `/events` payload carries them on the *event*. The single-market payload
    carries `event_ticker` on the market itself, so it is used as a fallback
    rather than being required.
    """
    strike = market.get("floor_strike")
    return DiscoveredMarket(
        ticker=market.get("ticker") or "",
        event_ticker=event_ticker or (market.get("event_ticker") or ""),
        series_ticker=series_ticker,
        market_type=market_type,
        title=market.get("title") or "",
        yes_side=(market.get("yes_sub_title") or "").strip() or None,
        strike=float(strike) if strike is not None else None,
        close_ms=parse_ms(market.get("close_time")),
        status=market.get("status"),
        volume_24h=_float(market.get("volume_24h_fp")),
        open_interest=_float(market.get("open_interest_fp")),
        price_structure=market.get("price_level_structure"),
        result=read_market_result(market),
        # Field names verified against tests/fixtures/events_sports_nested.json
        # and tests/fixtures/market_single.json, not against memory. Prices
        # arrive as dollar STRINGS ("0.4500"), so `dollars_to_tenths` parses
        # them and returns None on anything it cannot read.
        yes_bid_tenths=dollars_to_tenths(market.get("yes_bid_dollars")),
        no_bid_tenths=dollars_to_tenths(market.get("no_bid_dollars")),
        yes_ask_size=parse_quantity(market.get("yes_ask_size_fp")),
        no_ask_size=parse_quantity(market.get("yes_bid_size_fp")),
        price_grid=read_price_grid(market),
    )


def build_markets(event: dict, market_type: str) -> tuple[DiscoveredMarket, ...]:
    return tuple(
        build_market(
            market,
            market_type=market_type,
            event_ticker=event.get("event_ticker") or "",
            series_ticker=event.get("series_ticker") or "",
        )
        for market in (event.get("markets") or [])
        if not (market.get("ticker") or "").startswith(JUNK_PREFIX)
    )


def reset_scope_warnings() -> None:
    """Forget which unknown scopes have been reported.

    **Not called by `discover_from_events`** -- deliberately. Calling it per pass
    is what put 98 copies of the same warning into every pass on live and made
    the boot lines unreadable; see the comment on `_WARNED_SCOPES`.

    It exists for tests, which share one process and would otherwise depend on
    the order they run in: whichever test warns about a series first would be the
    only one that sees the warning. An autouse fixture calls it between tests.

    It clears **every** per-process warning set, not only the scope one. A second
    set was added later for `no occurrence_datetime`, and a third for unclassified
    leagues; a reset that knows about two of three is worse than no reset: the
    covered cases stay deterministic while the uncovered one silently acquires an
    order dependency, so the failure appears in whichever test happens to be
    collected second.
    """
    global _LAST_SUMMARY
    _WARNED_SCOPES.clear()
    _WARNED_NO_COMMENCE.clear()
    _WARNED_LEAGUES.clear()
    _LAST_SUMMARY = None


def _warn_about_new_unknown_scopes() -> None:
    """Name every newly-seen unrecognised scope, once, in a single line.

    Called at the end of a pass rather than per event. Emits nothing when the
    pass introduced no scope the process has not already named, which is every
    pass after the first -- the set of Kalshi series does not change between
    passes. The per-pass *count* is on the `discovery:` line regardless, so
    silence here still cannot be read as "the problem went away".

    In-scope leagues are named and out-of-scope ones are counted, because the
    action item is "should this be in FIXTURE_SCOPES?" and that question is only
    live for a league this project can devig against. Measured on the live
    exchange, 56 of 317 unknown scopes sit in a priceable league and every one
    of them is a future, an award or a period/prop market -- so the count that
    matters is the one that would go from 0 to 1 if Kalshi renamed `Game`.

    The ones already looked at are in `EXCLUDED_SCOPES` and never reach here.
    This line is for a value **nobody has classified**, which is why it stays
    loud: adding a scope to `EXCLUDED_SCOPES` to quieten it is a decision, and
    a decision leaves a record (docs/adr/0013) rather than a silence.
    """
    new_pairs = {
        pair: league
        for pair, league in _UNKNOWN_SCOPES_THIS_PASS.items()
        if pair not in _WARNED_SCOPES
    }
    if not new_pairs:
        return
    _WARNED_SCOPES.update(new_pairs)

    # scope -> (series seen under it, whether any is in a league we can price)
    by_scope: dict[str, list[str]] = {}
    priceable: set[str] = set()
    for (series, scope), league in sorted(new_pairs.items()):
        by_scope.setdefault(scope, []).append(series)
        if league in IN_SCOPE_LEAGUES:
            priceable.add(scope)

    def render(scope: str) -> str:
        series = by_scope[scope]
        extra = f" +{len(series) - 1}" if len(series) > 1 else ""
        return f"{scope!r} ({series[0]}{extra})"

    named = sorted(priceable)
    truncated = max(0, len(named) - _MAX_SCOPES_NAMED)
    shown = ", ".join(render(s) for s in named[:_MAX_SCOPES_NAMED]) or "none"
    if truncated:
        shown += f", and {truncated} more"

    logger.warning(
        "%d unrecognised competition_scope value(s) across %d series -- excluded "
        "from pricing. Named once per process; the per-pass count is "
        "`unknown_scopes` on the discovery summary line. In leagues this project "
        "can price (%d scopes, the only ones that could need adding to "
        "FIXTURE_SCOPES): %s. In leagues out of scope: %d further scopes, not an "
        "action item.",
        len(by_scope),
        len(new_pairs),
        len(priceable),
        shown,
        len(by_scope) - len(priceable),
    )


def _warn_about_new_unclassified_leagues() -> None:
    """Name every newly-seen unclassified league, once, in a single line.

    The `competition` twin of `_warn_about_new_unknown_scopes`, built on the same
    three pieces and called from the same place, at the end of a pass rather than
    per event. It exists because the scope axis had this defence and the league
    axis had none: `"Pro Football Preseason"` is one string away from the
    `"Pro Football"` in `IN_SCOPE_LEAGUES` and dropped 48 events and 726 markets
    with no warning, no counter and no red test.

    Two deliberate differences from its twin, both about keeping the line short
    enough to read:

    - Only leagues carrying a **game-level** market reach here (the gate is in
      `classify_series`). Kalshi puts a `competition` on elections and equities;
      those are not an unanswered question about league scope.
    - Dedupe is per league, not per (series, league), because "classify this
      value" is one action item however many series carry it.

    Emits nothing when the pass introduced no league the process has not already
    named, which is every pass after the first. The per-pass *count* is on the
    `discovery:` line regardless, at zero as well, so silence here still cannot
    be read as "the problem went away".

    The ones already looked at are in `IN_SCOPE_LEAGUES` or
    `OUT_OF_SCOPE_LEAGUES` and never reach here. This line is for a value
    **nobody has classified**, which is why it stays loud: adding a league to
    `OUT_OF_SCOPE_LEAGUES` to quieten it is a decision, and a decision leaves a
    reason beside the entry rather than a silence.

    It says "unclassified" where the scope line says "unrecognised", on purpose.
    Two axes fail the same way and a reader -- or a grep -- must be able to tell
    which one fired without reading the rest of the sentence.
    """
    new_leagues = {
        league: series
        for league, series in _UNKNOWN_LEAGUES_THIS_PASS.items()
        if league not in _WARNED_LEAGUES
    }
    if not new_leagues:
        return
    _WARNED_LEAGUES.update(new_leagues)

    def render(league: str) -> str:
        series = sorted(new_leagues[league])
        extra = f" +{len(series) - 1}" if len(series) > 1 else ""
        return f"{league!r} ({series[0]}{extra})"

    # Widest first, so truncation drops the leagues costing the fewest series
    # rather than the ones late in the alphabet.
    named = sorted(new_leagues, key=lambda lg: (-len(new_leagues[lg]), lg))
    truncated = max(0, len(named) - _MAX_LEAGUES_NAMED)
    shown = ", ".join(render(lg) for lg in named[:_MAX_LEAGUES_NAMED])
    if truncated:
        shown += f", and {truncated} more"

    logger.warning(
        "%d unclassified competition (league) value(s) across %d series carry "
        "game-level markets and are dropped from pricing with no decision "
        "recorded. Named once per process; the per-pass count is "
        "`unknown_leagues` on the discovery summary line. Classify each in "
        "IN_SCOPE_LEAGUES (with an Odds API sport key) or in "
        "OUT_OF_SCOPE_LEAGUES (with the reason): %s",
        len(new_leagues),
        sum(len(series) for series in new_leagues.values()),
        shown,
    )


def discover_from_events(
    events: Iterable[dict], *, always_log_summary: bool = True
) -> list[DiscoveredEvent]:
    """Classify a walk of `/events` into priceable game events.

    Everything rejected is rejected for a stated reason and counted, so
    "we found nothing" can be told apart from "we filtered everything".

    `always_log_summary=False` is for the quote cadence, which runs every ~22s
    while the window is open: the `discovery:` line is then emitted only when
    its numbers change. Full passes leave it True and so remain the heartbeat
    that keeps silence unambiguous. See `_LAST_SUMMARY`.

    It defaults to True so every existing caller -- `run_chain.py`, the tests --
    keeps the behaviour it had. A default that quietened output would silence
    the one-shot scripts, where every pass is the only pass.
    """
    # The *counts* are per-pass; the warnings are per-process. Only these are
    # cleared. See `_WARNED_SCOPES` and `_WARNED_LEAGUES`.
    _UNKNOWN_SCOPES_THIS_PASS.clear()
    _UNKNOWN_LEAGUES_THIS_PASS.clear()
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
            # Once per series per process, not once per event. Every event in a
            # series shares whatever data-entry gap caused this, so the undeduped
            # form is a flood waiting for the day Kalshi omits the field across a
            # league -- the same shape as the scope warning, one branch away.
            # `no_commence_time` on the `discovery:` line carries the count.
            if info.series_ticker not in _WARNED_NO_COMMENCE:
                _WARNED_NO_COMMENCE.add(info.series_ticker)
                logger.warning(
                    "%s is game-level but carries no occurrence_datetime; cannot "
                    "be matched against a sportsbook fixture. Named once per "
                    "series; see no_commence_time on the discovery summary line "
                    "for the per-pass count. First seen on %s.",
                    info.series_ticker, event.get("event_ticker"),
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

    _warn_about_new_unknown_scopes()
    _warn_about_new_unclassified_leagues()

    # `unknown_scopes` and `unknown_leagues` are printed unconditionally,
    # including at zero, and that is the point of them: they are what replaces a
    # per-pass warning stream, so a pass that says nothing about an unknown value
    # must be distinguishable from a pass that found none. A dropped zero would
    # put the reader back where the warnings left them -- unable to tell silence
    # from absence.
    #
    # This line is emitted *after* the warnings above for the same reason those
    # warnings are now one line each: on 2026-08-09 this summary was itself lost
    # from the live log stream, sitting immediately behind a 962-line burst. A
    # line whose job is to be readable must not be queued behind a flood.
    global _LAST_SUMMARY
    summary = (
        len(discovered),
        len(_UNKNOWN_SCOPES_THIS_PASS),
        len(_UNKNOWN_LEAGUES_THIS_PASS),
        ", ".join(f"{k}={v}" for k, v in rejected.items() if v) or "none",
    )
    if always_log_summary or summary != _LAST_SUMMARY:
        _LAST_SUMMARY = summary
        logger.info(
            "discovery: %d priceable events; unknown_scopes=%d; "
            "unknown_leagues=%d; rejected %s",
            *summary,
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
