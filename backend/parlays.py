"""Read ladder candidates for the parlay desk, and word its payload (ADR 0070).

The desk sells six cards — six cuts of ONE pool of devigged consensus legs,
one leg per game, priced at FAIR value. `core.ladder.CARD_SHAPES` owns which
cuts exist; nothing here knows how many there are.
Kalshi's actual quote for a combination exists only after a lookup mints the
market, so everything here is the consensus side of the comparison; the quoted
side arrives via the lookup path and is labelled as Kalshi's, never blended.

WHAT THIS MODULE DOES NOT ESTABLISH
-----------------------------------
- **That a card is a good bet.** The fair joint is what the books' consensus
  implies; the venue's combination product is enter-only on every book this
  repo has ever read, and its fee model is unverified. Those sentences travel
  in the payload verbatim.
- **An edge.** No breakeven, no EV, no size appears in any payload built here
  (pinned by `tests/test_parlays_api.py`'s key-walk). ADR 0038's closed hunt
  and the gate are untouched: nothing here writes `recommendations` or feeds
  `gate.py`.

Money strings render server-side, per `lib/api.ts`'s no-arithmetic rule: the
stake picker is a set of preset stakes each priced here, not a client-side
calculator.
"""

from __future__ import annotations

import json
import logging
from typing import NamedTuple, Optional, Sequence

from backend.core.correlation import Leg
from backend.core.ladder import (
    CARD_SHAPES,
    Card,
    CandidateLeg,
    Ladder,
    UNUSABLE_REASONS,
    build_ladder,
    joint_for,
    unusable_reason,
    usable_legs,
)
from backend.core.parlay import ParlayQuote, value_parlay
from backend.core.prices import format_dollars, format_price, format_probability
from backend.kalshi.combos import (
    ComboScope, echoed_legs, fetch_collections, lookup_combo,
)
from backend.kalshi.orderbook import OrderBook
from backend.kalshi.props import norm
from backend.kalshi.spreads import (
    parse_spread_subtitle,
    spread_book_point,
    spread_margin_agrees,
)
from backend.match.linker import load_aliases, resolve_outcome
from backend.odds.client import PROP_BASE_MARKETS
from backend.store.db import ask_for_side

logger = logging.getLogger(__name__)

#: Preset stakes, in cents. Served pre-priced so the client never does money
#: arithmetic.
#:
#: **Re-sized 2026-08-26 to the operator's own stated range, replacing someone
#: else's.** These were $1/$5/$10/$20 defaulting to $5, framed by ADR 0070 s2.7
#: around the cousin's $4.99 ticket -- the bet that prompted the desk, but not a
#: bet Joe has ever placed. Asked directly, in his words: *"I bet .25 cents to 2
#: or 3 bucks on parlays right now."*
#:
#: So three of the four presets were amounts he would never stake and the
#: default sat above his ceiling, which means every payout figure on the card
#: was priced for somebody else's bet. ADR 0071 s2.1 is the reason that
#: matters: the desk exists to inform bets that are happening anyway, and a
#: stake row he would not choose informs nothing.
#:
#: **This is a display range, not a limit.** Nothing here caps an order: the
#: per-bet ceiling is derived from the observed balance (ADR 0045) and the
#: manual path's own contract ceiling binds separately. Widening these back out
#: costs nothing if his betting changes -- ask him rather than inferring it
#: from a larger balance.
STAKE_PRESETS_CENTS: tuple[int, ...] = (25, 50, 100, 300)
DEFAULT_STAKE_CENTS = 100

#: A market whose status says the venue is done with it cannot be a leg.
_TERMINAL_STATUSES = frozenset({"closed", "settled", "finalized", "determined"})

NOTES: dict[str, str] = {
    "chance": (
        "Chance every leg hits, by the books' consensus — not an edge. A "
        "parlay multiplies chances down: six 65% legs land together about "
        "8% of the time."
    ),
    "fair_value": (
        "Costs shown are FAIR value — what the combination is worth if "
        "Kalshi charged exactly the consensus chance. Kalshi's own price "
        "for a combo exists only once it is built in the app, and it will "
        "differ."
    ),
    "enter_only": (
        "Kalshi combos are enter-only in every order book this tool has "
        "ever read (40 of 40): you can buy in, but nobody is bidding to "
        "buy you out. Plan to hold to settlement."
    ),
    "fee": (
        "Kalshi's combo fee model is unverified. Every combo fill ever "
        "measured here charged at least 0.070 x contracts x price x "
        "(1 - price), and some charged slightly more."
    ),
}


def _prop_rungs(markets) -> dict[tuple[str, float], object]:
    """`(normalised player, strike) -> Kalshi market`, for one prop event.

    Built once per event rather than scanned per fair row: a single strikeouts
    event carries dozens of rungs, and the team arms below are linear scans
    that would multiply out against them.

    **The key is the runner's own** (`runner.py:1469`) minus the market key,
    which the event already fixes. `strike` is Kalshi's published
    `floor_strike` and `point` is the book's line; they are the same number by
    identity (`kalshi/props.py`), so nothing is converted on either side. Any
    arithmetic here — a `+ 0.5` — would be a second definition of the rung.

    `norm` is imported from `kalshi.props` rather than reimplemented so the
    accent fold ("José Ramírez" against "Jose Ramirez") is inherited, not
    written twice.
    """
    index: dict[tuple[str, float], object] = {}
    for m in markets:
        if m["market_type"] != "prop":
            continue
        if m["player_name"] is None or m["strike"] is None:
            continue
        index.setdefault((norm(m["player_name"]), float(m["strike"])), m)
    return index


def _live_age_ms(row, *, now_ms: int) -> Optional[int]:
    """The consensus's LIVE age: time since devig plus its stalest input.

    `None` when `oldest_book_age_ms` was never recorded (pre-v20 row) — the
    age is unmeasurable and the ladder refuses the leg, never ages it zero.
    """
    oldest = row["oldest_book_age_ms"]
    if oldest is None:
        return None
    return (now_ms - row["computed_ms"]) + oldest


#: The two team markets, and the five MLB prop keys a leg may come from.
#:
#: **These duplicate the literals in the ladder query on purpose.** That query
#: has to stay a literal triple-quoted string -- `tests/test_ladder_query_is_
#: indexed.py` extracts it by regex, and an f-string both breaks the extraction
#: and risks losing the `market=?` index seek that keeps `/api/parlays` off a
#: full scan of ~6.9M `fair_prices` rows. A drift test asserts the two agree
#: rather than a shared constant being interpolated into the SQL.
_TEAM_MARKETS: frozenset[str] = frozenset({"h2h", "spreads"})
_PROP_MARKETS: frozenset[str] = frozenset(PROP_BASE_MARKETS)


#: How far back `ladder_candidates` reads `fair_prices` at all.
#:
#: `fair_prices` is never pruned and passed ~6.9M rows by 2026-08-24, and this
#: query is paid twice per lookup tap (once for the ladder, once to re-derive
#: the card server-side). Every row older than this is discarded downstream
#: anyway: `build_ladder` refuses a leg whose consensus is staler than
#: `max_odds_age_ms` (deployed in minutes), and the pre-game bound already
#: excludes anything whose game has started. So this floor changes no output,
#: it only stops the scan reading the whole history to throw it away.
#:
#: **Derived from the freshness rule rather than set beside it, since
#: 2026-08-30.** It was a flat 24 hours, chosen so the floor could never be a
#: second staleness limit in a second place -- a real hazard this repo has
#: paid for. The cost of that choice was measured on live and is not small:
#:
#:     fair_prices rows in the 24h window   541,222
#:     rows the scan returns                    350
#:     whole candidate scan               25,324.7 ms
#:     the odds_snapshots GROUP BY beside it  451.5 ms
#:
#: `/api/parlays` took over 30s while `/api/board` took ~2s, and the plan
#: (`inspect_live_db parlay-candidates-timing`) shows why: SQLite reads half a
#: million rows through `idx_fair_market_computed`, joins each, sorts them all
#: through a temp B-tree for the window function, and keeps 350.
#:
#: A MULTIPLE of `max_odds_age_ms` answers both concerns at once. There is
#: still exactly one staleness quantity -- this is a function of it, not a
#: rival to it -- and "the scan can never be tighter than the freshness rule"
#: now holds by construction (4x >= 1x) instead of by a comparison somebody
#: has to keep making.
#:
#: **Eight, not one, because the excluded census is load-bearing** -- and the
#: number was chosen by a test rather than by taste. At exactly 1x a row that
#: had just gone stale would never enter the scan at all, so `stale_consensus`
#: would read 0 and an empty ladder would say "the slate has 0 fresh games"
#: with nothing explaining where they went: a refusal naming a predicate it
#: did not apply, which `tasks/lessons.md` records twice. 4x was tried first
#: and `test_a_stale_consensus_is_refused_and_counted` went red -- it seeds a
#: leg exactly one hour stale, which a one-hour window puts on the boundary.
#: 8x is two hours at the deployed `MAX_ODDS_AGE_S`, so the census keeps an
#: hour of headroom behind the case the suite actually pins.
#:
#: Still a 12x cut in what the scan reads: ~541,000 rows to ~45,000.
_CANDIDATE_SCAN_FLOOR_MULTIPLE = 8

#: The floor when the caller names no freshness rule at all. Two hours, which
#: is what the multiple gives at the deployed `MAX_ODDS_AGE_S` of 900s --
#: stated so a `None` caller cannot silently scan a single millisecond.
_CANDIDATE_SCAN_MIN_MS = 2 * 3_600_000


#: The clock the desk is read on. **Must equal `DISPLAY_TIME_ZONE` in
#: `frontend/src/lib/api.ts`**, and `test_parlays_api.py` pins the two
#: together: a card scoped to "tonight" by one clock and captioned with the
#: other is the "two definitions of today in one process" failure this repo
#: has already paid for once, in the odds budget.
DESK_TIME_ZONE = "America/Los_Angeles"


#: When a sports day rolls over, local. **4am, not midnight**, and the hour is
#: the whole point: a 22:30 kickoff belongs to tonight's slate and finishes
#: around 01:30, so a midnight boundary would cut the card in half at exactly
#: the hour Joe is most likely to be reading it. Nothing kicks off between 1am
#: and 4am in any league this desk carries, so the rollover lands in a gap
#: rather than through a slate. It is the same convention a book's "day" uses.
DESK_DAY_ROLLOVER_HOUR = 4


def end_of_desk_day_ms(now_ms: int) -> int:
    """End of the current sports day, epoch ms — the parlay scope bound.

    **Joe's rule, in his words: "I'd want to see my parlays finish out by the
    time the evening games end."** So a card may only combine games that kick
    off before tonight's slate is over. The bound is on KICKOFF, not on
    settlement, and kickoff is the right end to measure: the last game of a
    night finishes after midnight by definition, and bounding on settlement
    would drop exactly the evening games he means to bet.

    **A rollover bound rather than a fixed number of hours.** "Within 24 hours"
    read at 9am Thursday reaches into Friday's slate, which is the thing being
    removed; read at 11pm it reaches half of Saturday. The boundary a bettor
    actually has is the end of the night, and the night ends at
    `DESK_DAY_ROLLOVER_HOUR`.

    So this returns the next 4am strictly after `now_ms`: read at 15:00 Friday
    it is 04:00 Saturday, and read at 00:30 Saturday it is still 04:00 Saturday
    -- the same slate, because 00:30 is Friday night.

    Computed through `zoneinfo`, so DST is the library's problem rather than an
    arithmetic assumption.
    """
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(DESK_TIME_ZONE)
    local = datetime.fromtimestamp(now_ms / 1000, tz)
    rollover = local.replace(
        hour=DESK_DAY_ROLLOVER_HOUR, minute=0, second=0, microsecond=0
    )
    if rollover <= local:
        rollover = (rollover + timedelta(days=1)).replace(
            hour=DESK_DAY_ROLLOVER_HOUR, minute=0, second=0, microsecond=0
        )
    return int(rollover.timestamp() * 1000)


#: The candidate scan, as a module constant so an instrument can time and
#: EXPLAIN **this** statement rather than a copy of it that drifted.
#: `scripts/inspect_live_db.py parlay-candidates-timing` imports it; a
#: second transcription in that file is how a plan gets measured for SQL
#: nobody runs.
CANDIDATE_SQL = """
        SELECT computed_ms, market, outcome_name, outcome_point,
               outcome_description,
               p_multiplicative, p_additive, p_power, p_shin,
               p_conservative, oldest_book_age_ms, link_id,
               market_width, book_count, books_used, anchored_on_sharp,
               kalshi_event_ticker, odds_event_id,
               commence_ms, home_team, away_team, sport_key,
               event_title
        FROM (
        SELECT f.computed_ms, f.market, f.outcome_name, f.outcome_point,
               f.outcome_description,
               f.p_multiplicative, f.p_additive, f.p_power, f.p_shin,
               f.p_conservative, f.oldest_book_age_ms, f.link_id,
               f.market_width, f.book_count, f.books_used, f.anchored_on_sharp,
               l.kalshi_event_ticker, l.odds_event_id,
               o.commence_ms, o.home_team, o.away_team, o.sport_key,
               e.title AS event_title,
               -- **The freshest row per identity, chosen in SQL.** This used
               -- to be done in Python, below, after `fetchall()` had brought
               -- the whole 24-hour window into the process: 463,866 rows and
               -- ~557 MB on a 2 GB box that sits at ~1.03 GB at rest, for a
               -- result the dedup then reduced to a few thousand. Repeated
               -- visits OOM-killed uvicorn, and because `entrypoint.sh` uses
               -- `wait -n`, killing that child tore down the container and
               -- restarted the recorder too -- so opening one tab took the
               -- whole site down. Measured at about 91 seconds of outage.
               --
               -- The partition is byte-for-byte the Python key, INCLUDING
               -- `outcome_description`. That column is NULL on team markets
               -- and load-bearing on props, where `outcome_name` is only
               -- "Over"/"Under": without it two pitchers in one game quoted
               -- at the same rung collapse onto one row. SQL `PARTITION BY`
               -- groups NULLs together, which is what a Python dict key of
               -- `None` does, so the two agree on exactly this point.
               --
               -- `f.rowid` breaks ties. The Python `setdefault` kept whichever
               -- row SQLite happened to return first among equal
               -- `computed_ms`, which was arbitrary but not random; this is
               -- arbitrary and STABLE, so two calls a millisecond apart cannot
               -- offer different legs for the same rung.
               ROW_NUMBER() OVER (
                   PARTITION BY f.link_id, f.market, f.outcome_name,
                                f.outcome_description, f.outcome_point
                   ORDER BY f.computed_ms DESC, f.rowid DESC
               ) AS rn
        FROM fair_prices f
        JOIN event_links l ON l.id = f.link_id
        JOIN kalshi_events e ON e.event_ticker = l.kalshi_event_ticker
        JOIN (
            SELECT odds_event_id, MIN(commence_ms) AS commence_ms,
                   home_team, away_team, sport_key
            FROM odds_snapshots
            -- **Restricted to LINKED events, and this cannot change the
            -- answer.** The outer query inner-joins on `l.odds_event_id`, so
            -- an event absent from `event_links` was going to be discarded
            -- anyway -- the subquery was grouping the entire history of the
            -- table to build rows it then threw away.
            --
            -- Measured 2026-08-26: without it the plan reads
            -- `SCAN odds_snapshots` on every request, and `/api/parlays`
            -- answered in 15s while every other route was sub-second. With it,
            -- plus `idx_odds_event_commence`, the plan is
            -- `SEARCH odds_snapshots (odds_event_id=?)`.
            --
            -- **Deliberately NOT filtered on `commence_ms` here**, which would
            -- be the obvious way to cut it further. `MIN(commence_ms)` is the
            -- fixture's earliest recorded start, and filtering rows before
            -- taking the MIN would let a RESCHEDULED fixture through whose
            -- true earliest start is in the past. Rare, and a silent wrong
            -- answer is worse than a slower right one.
            WHERE odds_event_id IN (SELECT odds_event_id FROM event_links)
            GROUP BY odds_event_id
        ) o ON o.odds_event_id = l.odds_event_id
        WHERE f.market IN ('h2h', 'spreads', 'pitcher_strikeouts',
                          'batter_total_bases', 'batter_hits',
                          'batter_home_runs', 'batter_rbis')
          AND f.computed_ms >= ?
          AND o.commence_ms IS NOT NULL AND o.commence_ms > ?
        )
        WHERE rn = 1
        ORDER BY computed_ms DESC
        """


def ladder_candidates(
    conn, *, now_ms: int, max_odds_age_ms: Optional[int] = None
) -> tuple[list[CandidateLeg], dict[str, int]]:
    """Every buyable YES side with a fresh-enough-to-consider consensus.

    Pre-game only AND tonight only, by the sportsbook's clock
    (`MIN(odds_snapshots.commence_ms)` per fixture — the scorer's own
    definition; Kalshi's `commence_ms` runs three hours late and is never read
    here). The upper bound is `end_of_desk_day_ms`: a parlay settles when its
    last leg does, and Joe's rule is that his finish out with the evening
    games. Freshest `fair_prices` row per
    (link, market, outcome, point). Freshness itself is judged in
    `build_ladder`; this function only refuses what can never be a leg.

    `max_odds_age_ms` is not a filter here — it only widens the scan floor so
    the query can never be tighter than the freshness rule the caller will
    apply. Pass the same value you pass `build_ladder`.
    """
    horizon_ms = max(
        _CANDIDATE_SCAN_FLOOR_MULTIPLE * (max_odds_age_ms or 0),
        _CANDIDATE_SCAN_MIN_MS,
    )
    rows = conn.execute(
        CANDIDATE_SQL, (now_ms - horizon_ms, now_ms)
    ).fetchall()

    excluded: dict[str, int] = {}

    def count(reason: str) -> None:
        excluded[reason] = excluded.get(reason, 0) + 1

    # Freshest row per identity. The SQL above now guarantees one row per
    # identity already, so this loop drops nothing -- it is kept deliberately,
    # as the belt to the query's braces. If the window function is ever
    # removed or its partition edited, the route degrades to slow rather than
    # to WRONG, and `TestTheLadderIsBoundedInSql` is what fails loudly.
    # It also still builds the key tuple that every loop below unpacks.
    freshest: dict[tuple, object] = {}
    for row in rows:
        # `outcome_description` is load-bearing and NULL on team markets.
        # On a prop, `outcome_name` is only "Over"/"Under", so without the
        # player two pitchers in one game quoted at the same rung collapse
        # onto one key and `setdefault` silently keeps whichever arrived
        # first. Same defect `odds_snapshots.outcome_description` exists to
        # prevent one table upstream.
        key = (
            row["link_id"],
            row["market"],
            row["outcome_name"],
            row["outcome_description"],
            row["outcome_point"],
        )
        freshest.setdefault(key, row)

    # The book's outcome names per link — what `resolve_outcome` matches
    # a Kalshi side against. Spread rows' outcomes are the same two teams,
    # so one list per link serves both market kinds.
    #
    # **Team markets only.** A prop row's `outcome_name` is the literal
    # "Over"/"Under", which is not a team and must never be offered to the
    # alias resolver -- the one function in this path whose whole contract is
    # that it refuses to guess. Props match on player and strike instead and
    # never consult this dict.
    outcomes_by_link: dict[int, list[str]] = {}
    for (link_id, market, outcome, _player, _point), _row in freshest.items():
        if market not in _TEAM_MARKETS:
            continue
        if outcome not in outcomes_by_link.setdefault(link_id, []):
            outcomes_by_link[link_id].append(outcome)

    # Kalshi's buyable markets per linked event: moneylines on the game
    # event, spread rungs on the spread event (each links separately).
    markets_by_event: dict[str, list] = {}
    for row in freshest.values():
        event_ticker = row["kalshi_event_ticker"]
        if event_ticker in markets_by_event:
            continue
        markets_by_event[event_ticker] = conn.execute(
            "SELECT ticker, title, yes_side_team, player_name, market_type, "
            "strike, status "
            "FROM kalshi_markets WHERE event_ticker = ? "
            "AND ("
            "  (market_type IN ('moneyline', 'spread') "
            "   AND yes_side_team IS NOT NULL)"
            "  OR (market_type = 'prop' AND player_name IS NOT NULL "
            "      AND strike IS NOT NULL)"
            ")",
            (event_ticker,),
        ).fetchall()

    alias_cache: dict[str, object] = {}
    candidates: list[CandidateLeg] = []
    tonight_ms = end_of_desk_day_ms(now_ms)
    # `None` when the cache is cold or stale, and then nothing is filtered on
    # it -- see `combo_eligible_events`. A parlay desk that hides every game
    # because a background walk failed is worse than one that offers a card
    # the venue then refuses in words.
    eligible_events = combo_eligible_events(conn, now_ms=now_ms)

    for (link_id, market, outcome, player, point), row in freshest.items():
        # **Tonight only.** A parlay settles when its last leg does, so a card
        # mixing tonight's game with one on Saturday cannot pay out until
        # Saturday -- and Joe's rule is that his parlays finish out by the
        # time the evening games end.
        #
        # It also happens to fix a venue problem, and the coincidence is worth
        # naming so nobody "simplifies" this away later: Kalshi's combination
        # collections only carry the imminent slate. Measured 2026-08-28, all
        # three catch-alls enumerate the same 2,365 legs, of which 64 are NCAAF
        # and every one is inside two days. Cards built a week out returned
        # HTTP 400 `invalid_parameters` -- real markets, individually priceable,
        # that the venue will not combine. This bound keeps the desk inside
        # what Kalshi will actually price, without needing to ask it.
        #
        # Counted, never silently dropped: a thin page must be able to say why
        # it is thin.
        if row["commence_ms"] is not None and row["commence_ms"] > tonight_ms:
            count("kickoff_after_tonight")
            continue
        # **Kalshi trades far more games than it will combine.** Measured
        # 2026-08-28: all three catch-all collections carry the same 2,365
        # legs, and a card whose legs are outside that list comes back HTTP
        # 400 `invalid_parameters` after the tap. The tonight bound above
        # happens to keep the desk inside that window today, but the two are
        # independent -- if Kalshi narrows its combo horizon, only this check
        # notices.
        if (
            eligible_events is not None
            and row["kalshi_event_ticker"] not in eligible_events
        ):
            count("kalshi_will_not_combine")
            continue
        # **`odds_snapshots.sport_key`, not `event_links.league`.** They are
        # different vocabularies for the same partition and only one of them
        # names an alias file.
        #
        # `event_links.league` holds Kalshi's `product_metadata.competition`
        # verbatim -- measured on this repo's own database: 'Pro Baseball',
        # 'Pro Basketball (W)', 'Pro Football'. The alias files are named for
        # The Odds API's sport keys: `baseball_mlb.yaml`,
        # `americanfootball_nfl.yaml`. So `load_aliases("Pro Baseball")` looked
        # for a file that has never existed, and `load_aliases` returns an
        # EMPTY `TeamAliases` for a missing file rather than raising -- by
        # design, because most leagues need no overrides.
        #
        # The two together mean **the parlay ladder ran with zero team aliases
        # from the day it was built**, silently, on a screen that offers money
        # decisions. The linker itself was always correct
        # (`runner.py` loads aliases from `event.sport_key`); only this reader
        # was wrong, which is why nothing upstream noticed.
        #
        # The same string is what the client renders, so this also stops a leg
        # reading "Pro Baseball" where the rest of the app says "MLB":
        # `frontend/src/lib/leagueLabel.ts` keys on sport keys and renders an
        # unknown key verbatim.
        league = row["sport_key"]
        if league not in alias_cache:
            alias_cache[league] = load_aliases(league)
        aliases = alias_cache[league]

        # Which Kalshi market's YES is this outcome?
        #
        # A spread combo leg must be a BUYABLE YES side, and Kalshi only
        # sells the favorite's cover ("T wins by over S" = the book's
        # (T, -S)); the +S side is that market's NO, not a leg. So spread
        # rows with a positive point are structurally not candidates —
        # skipped without a count, the way a NO-side h2h row never enters
        # `outcomes_by_link` as a pick.
        matched = None
        label = f"{outcome} to win"
        if market in _PROP_MARKETS:
            # Kalshi sells the ladder rung as YES = Over (`runner.py:1524`).
            # The Under is that market's NO, not a leg — skipped without a
            # count, exactly as the +S spread side is below.
            if outcome != "Over":
                continue
            if player is None or point is None:
                count("prop_row_missing_player_or_line")
                continue
            matched = _prop_rungs(
                markets_by_event.get(row["kalshi_event_ticker"], [])
            ).get((norm(player), float(point)))
            if matched is not None:
                # Kalshi's own phrasing, for the reason the spread arm gives
                # one branch down. `title` reads "Anthony Kay: 6+ strikeouts?"
                # -- it names the statistic, which `yes_sub_title`
                # ("Anthony Kay: 6+") does not, and a card that can mix five
                # prop series cannot afford that ambiguity.
                raw = (matched["title"] or "").strip()
                if not raw:
                    count("prop_title_unreadable")
                    matched = None
                else:
                    label = raw.rstrip("?").strip()
        elif market == "spreads":
            point_val = float(point) if point is not None else None
            if point_val is None or point_val >= 0:
                continue
            for m in markets_by_event.get(row["kalshi_event_ticker"], []):
                if m["market_type"] != "spread" or m["strike"] is None:
                    continue
                parsed = parse_spread_subtitle(m["yes_side_team"])
                if parsed is None:
                    continue
                # The subtitle's own margin, cross-checked against
                # `floor_strike`, then converted to the book's point through
                # the ONE identity (`spreads.spread_book_point`). Reading the
                # strike alone -- what this did until 2026-08-24 -- skips the
                # cross-check the runner performs, so a market whose subtitle
                # had drifted away from its strike could still match a fair
                # row that was priced from the subtitle.
                if not spread_margin_agrees(parsed[1], m["strike"]):
                    count("spread_margin_disagrees")
                    continue
                if spread_book_point(parsed[1]) != point_val:
                    continue
                resolved = resolve_outcome(
                    parsed[0], outcomes_by_link.get(link_id, []), aliases
                )
                if resolved == outcome:
                    matched = m
                    # The subtitle verbatim — Kalshi's own phrasing is the
                    # clearest label a rung has ("St. Louis wins by over
                    # 1.5 runs").
                    label = m["yes_side_team"]
                    break
        else:
            for m in markets_by_event.get(row["kalshi_event_ticker"], []):
                if m["market_type"] != "moneyline":
                    continue
                resolved = resolve_outcome(
                    m["yes_side_team"], outcomes_by_link.get(link_id, []), aliases
                )
                if resolved == outcome:
                    matched = m
                    break
        if matched is None:
            count("prop_no_kalshi_rung" if market in _PROP_MARKETS
                  else "no_kalshi_market")
            continue
        if (matched["status"] or "").lower() in _TERMINAL_STATUSES:
            count("market_closed")
            continue

        # **A leg whose fair probability is not positive is a bug, not a long
        # shot** -- CLAUDE.md rule 1, and its "unreadable resolves to None,
        # never 0" convention pointed at a probability.
        #
        # The joint is a product (`running *= leg.p_conservative`), so ONE such
        # leg zeroes the whole card, and `_stake_row` then divides a stake by
        # it. That is not hypothetical: on 2026-08-28 it raised
        # `ZeroDivisionError` on live, took `/api/parlays` down to "Backend
        # unreachable", and -- because `build_ladder_payload` is called from
        # `score_settle_and_alert` -- killed the tail of every scheduler pass
        # with it: parlay cards, the daily digest and `log_gate_progress` all
        # stopped running.
        #
        # Refused here rather than clamped, because a devig that returns 0.0
        # for a market Kalshi is still quoting has not produced a small
        # number; it has failed, and the count is what makes that visible.
        if row["p_conservative"] is None or row["p_conservative"] <= 0.0:
            count("fair_probability_not_positive")
            continue

        title = row["event_title"] or (
            f"{row['away_team']} @ {row['home_team']}"
            if row["away_team"] and row["home_team"]
            else row["kalshi_event_ticker"]
        )
        candidates.append(
            CandidateLeg(
                label=label,
                event_title=title,
                kalshi_event_ticker=row["kalshi_event_ticker"],
                kalshi_market_ticker=matched["ticker"],
                odds_event_id=row["odds_event_id"],
                league=league,
                commence_ms=row["commence_ms"],
                market=market,
                # A prop has no team, and the player never stands in for one.
                team=None if market in _PROP_MARKETS else outcome,
                point=point,
                # **Kalshi's spelling, not the book's.** The two genuinely
                # disagree on diacritics -- `norm` folds them so the join
                # succeeds -- and what the card shows must be what Joe will
                # read in the Kalshi app, the same reason `label` is Kalshi's
                # title. `matched` is the Kalshi rung, so this is that name.
                player=(
                    matched["player_name"] if market in _PROP_MARKETS else None
                ),
                p_conservative=row["p_conservative"],
                p_by_method={
                    "multiplicative": row["p_multiplicative"],
                    "additive": row["p_additive"],
                    "power": row["p_power"],
                    "shin": row["p_shin"],
                },
                odds_age_now_ms=_live_age_ms(row, now_ms=now_ms),
                market_width=row["market_width"],
                book_count=row["book_count"],
                books_used_json=row["books_used"],
                anchored_on_sharp=bool(row["anchored_on_sharp"]),
            )
        )

    return candidates, excluded


# ---------------------------------------------------------------------------
# Serialisation -- every display string is worded here, server-side.
# ---------------------------------------------------------------------------


def _percent(p: float) -> str:
    """A probability as a percentage, through the ONE renderer.

    Was `f"{p * 100:.1f}%"` until 2026-08-24. `core.prices.format_probability`
    exists precisely because that expression rounds off the float while every
    other surface in the product rounds off the stored integer tenths, so the
    same fair value could print `53.9%` here and `53.8c` two screens away with
    nothing to say which had moved. Its own docstring names this failure.
    """
    return format_probability(p)


def american_odds(probability: float) -> Optional[int]:
    """A probability as American odds, or `None` if it cannot be one.

    **The number Joe needs where the bet can actually be placed.** A
    combination on Kalshi is priced in cents on a $1 contract; a sportsbook
    quotes American odds. The desk's whole remaining job on a parlay is to say
    what it is worth, and saying it in cents to someone about to be quoted
    "+450" leaves the comparison to mental arithmetic at the worst moment.

    This is BREAK-EVEN, not a target. At exactly these odds the bet is fair
    against the consensus and its expected profit is zero -- and a sportsbook's
    margin means a real quote is usually worse. The caller renders it with
    words that say so; a bare number here would read as a recommendation, which
    ADR 0071 section 2.5 forbids the desk from making.

    `None` outside `(0, 1)`: a probability of 0 or 1 has no odds, and the
    repo's rule is that an unrepresentable value refuses rather than clamps.
    """
    if not 0.0 < probability < 1.0:
        return None
    if probability > 0.5:
        # The favourite side: what you must stake to win 100.
        return -int(round(100.0 * probability / (1.0 - probability)))
    return int(round(100.0 * (1.0 - probability) / probability))


def _american_display(probability: float) -> Optional[str]:
    odds = american_odds(probability)
    if odds is None:
        return None
    return f"+{odds}" if odds > 0 else str(odds)


def _cost_per_contract(tenths: float) -> str:
    """`15` -> `"1.5c per $1 contract"`, through the ONE price renderer.

    The suffix is the parlay desk's own: a combination contract settles at $1
    like any other, and saying so is what stops `1.5c` reading as the price of
    the whole ticket.
    """
    return f"{format_price(tenths)} per $1 contract"


def _dollars(cents: float) -> str:
    """Cents -> a dollar string, through the ONE dollar renderer.

    The rule it used to state inline — cents kept up to $1,000, dropped above
    it — now lives in `core.prices.format_dollars`, which the hedge surfaces
    also render through. Same reason `_percent` was moved to
    `format_probability` on 2026-08-24: two implementations of one rendering
    rule drift, and the drift is invisible because each one is correct on its
    own screen.

    This takes cents and `format_dollars` takes tenths of a cent, which is the
    only reason the wrapper survives at all: the parlay desk's stake presets
    are cent-denominated (`STAKE_PRESETS_CENTS`) and converting the whole
    surface is a change with no benefit attached.
    """
    return format_dollars(cents * 10.0)


#: What a stake buys when the joint cannot be divided by. The app's existing
#: idiom for "could not be computed" -- the ledger renders an uncomputable
#: settlement the same way, and says in its own copy that it is "never counted
#: as $0.00".
_UNCOMPUTABLE = "\u2014"


def _stake_row(stake_cents: int, joint: float) -> dict:
    """What a stake buys at FAIR value: `contracts = stake / fair_cost`,
    each contract settling $1 — the venue's own combo mechanics.

    **The zero guard is a backstop, not the fix.** `ladder_candidates` refuses
    a leg whose `p_conservative` is not positive, so a card reaching here with
    `joint <= 0` should be impossible. It was not impossible on 2026-08-28:
    this line raised `ZeroDivisionError` on live, and because the ladder is
    built inside the scheduler pass as well as by the route, it took out the
    page AND the tail of every pass.

    So the guard stays even though the upstream refusal makes it unreachable,
    for the reason the outage itself demonstrates: this function is called
    from two places and one of them is a loop that must not die. It renders
    the dash rather than a number, because a fabricated contract count on a
    card nobody can price is the failure CLAUDE.md rule 1 names.
    """
    if joint <= 0:
        return {
            "stake_cents": stake_cents,
            "stake_display": _dollars(stake_cents),
            "contracts_display": _UNCOMPUTABLE,
            "payout_display": _UNCOMPUTABLE,
            "is_default": stake_cents == DEFAULT_STAKE_CENTS,
        }
    contracts = stake_cents / (joint * 100.0)
    return {
        "stake_cents": stake_cents,
        "stake_display": _dollars(stake_cents),
        "contracts_display": _contracts_display(contracts),
        "payout_display": _dollars(contracts * 100.0),
        "is_default": stake_cents == DEFAULT_STAKE_CENTS,
    }


def _contracts_display(contracts: float) -> str:
    return f"~{contracts:,.0f}" if contracts >= 10 else f"~{contracts:.1f}"


def _at_stake(
    stake_cents: int, *, ask_tenths: int, depth: Optional[float]
) -> dict:
    """What a stake buys at Kalshi's QUOTED ask -- bounded by what is resting.

    **This is CLAUDE.md rule 1 applied to a payout.** `stake / ask` alone
    rendered "$5.00 -> ~333 contracts -> $333.33" on a book with about
    eighteen contracts resting: 315 of those 333 do not exist. On an
    enter-only market a lone stale NO bid at 1.5c produces exactly the giant
    apparent number the rule says to suppress, and putting it in the payout
    slot is the most flattering place it could possibly go.

    So the payout is computed off `min(wanted, depth)`, and when the stake is
    capped the words say by how much. Nothing here is an edge or an EV: cost
    and payout are what the venue would charge and pay, which is the same
    pair the fair-value side of the card already states.

    **`depth is None` is not reachable from `price_card_on_kalshi` today**,
    and the branch is kept anyway. `OrderBook.depth_at_ask` reads the same
    dict `best_no_bid` maxes over and `_parse_levels` drops any level with
    `quantity <= 0`, so a derived ask always has a positive size behind it —
    the two cannot disagree. That is an invariant of a *sibling module*,
    though, not of this function's signature: `depth` is typed `Optional`
    because `depth_at_ask` returns `Optional`, and a caller honouring that
    type must not get a payout invented for it. Unreadable resolves to a
    refusal, never to a number (`tasks/lessons.md`). Covered by a direct unit
    call rather than a route test, because the route genuinely cannot produce
    it — see `tests/test_parlay_lookup.py`.
    """
    row: dict = {"stake_display": _dollars(stake_cents)}
    wanted = stake_cents / (ask_tenths / 10.0)
    if depth is None:
        row["contracts_display"] = None
        row["cost_display"] = None
        row["payout_display"] = None
        row["depth_note"] = (
            "Kalshi's book does not say how many contracts are resting at "
            "that price, so there is no way to say what this stake would "
            "actually fill. No payout is shown rather than one you may not "
            "be able to buy."
        )
        return row

    fillable = min(wanted, float(depth))
    row["contracts_display"] = _contracts_display(fillable)
    row["cost_display"] = _dollars(fillable * ask_tenths / 10.0)
    row["payout_display"] = _dollars(fillable * 100.0)
    row["depth_note"] = (
        None if fillable >= wanted
        else (
            f"Only {_contracts_display(float(depth))} contracts are resting "
            f"at that price, so {row['stake_display']} cannot all be spent "
            f"here -- {row['cost_display']} of it buys the book out. The rest "
            "has nothing to buy unless someone else offers."
        )
    )
    return row


def _method_spread_points(leg: CandidateLeg) -> Optional[float]:
    """How far the four devig readings sit apart, in percentage points.

    The same figure `DispersionStrip` shows as its always-visible summary, and
    for the same reason: it bounds how seriously any single reading deserves to
    be taken. `None` on fewer than two solvable readings -- one reading is not
    perfect agreement, it is one reading.
    """
    values = [v for v in leg.p_by_method.values() if v is not None]
    if len(values) < 2:
        return None
    return (max(values) - min(values)) * 100


def _prefix_chances(legs: Sequence[CandidateLeg]) -> list[dict]:
    """The chance that the first N legs ALL land, for N = 1..len(legs).

    The picture behind `NOTES["chance"]`, drawn from this card's own legs in
    the ladder's own order rather than from an illustration.

    **This is the plain product, and the card's headline is not.** The headline
    joint runs a seeded Gaussian copula that adds a small same-day correlation
    nudge; the difference between the two is `independence_error_points`, which
    the payload already states and which the chart repeats underneath itself.
    Re-running the copula at every prefix would be `len(legs)` more
    200,000-sample Monte-Carlo runs per card -- measured at ~85ms each -- for a
    difference in hundredths of a point. The honest move is the cheap number
    with its error named, not the expensive number with its cost hidden.

    Rendered percent strings ride along, so the client plots the geometry and
    prints nothing it computed itself.
    """
    out: list[dict] = []
    running = 1.0
    for index, leg in enumerate(legs, start=1):
        running *= leg.p_conservative
        out.append(
            {
                "legs": index,
                "chance": running,
                "chance_percent_display": _percent(running),
            }
        )
    return out


def _serialise_leg(leg: CandidateLeg, facts: Optional[dict] = None) -> dict:
    """One leg, with the provenance behind its number.

    Until 2026-08-26 this returned the fair percent and nothing else -- one
    number standing in for three separate choices (which devig method, which
    books, how far the field spreads) on a screen that offers money decisions.
    The slate row has carried all three since ADR 0051; the parlay card had
    none of them.

    **Fair beside COST is lawful here and nowhere else** (ADR 0070 s2.3): a
    parlay's hold is the product being displayed. The two render in unlike
    units on purpose -- ask through `format_price` (`34.2c`), fair through
    `format_probability` (`60.2%`) -- because `core/prices.py:130-143` records
    that a fair value set in the same type as a real ask is the one place a
    left-to-right scan reads the wrong number as the thing you pay.

    **No edge, EV, breakeven or size appears here**, and
    `tests/test_parlays_api.py` walks the keys to keep it that way.
    """
    facts = facts or dict(_NO_FACTS)
    # A spread leg has no `recommendations` row by construction, so "no
    # verdict" means the checks did not run rather than that they passed.
    skeptic = facts["skeptic"]
    if skeptic == "absent" and leg.market == "spreads":
        skeptic = "not_on_this_path"
    return {
        "ticker": leg.kalshi_market_ticker,
        # The lookup tap echoes both tickers back, so the server can refuse
        # a card the slate has drifted away from.
        "event_ticker": leg.kalshi_event_ticker,
        "event_title": leg.event_title,
        "team": leg.team,
        #: The player on a prop leg, `None` on a team market. Never a
        #: substitute for `team`, which stays `None` on a prop.
        "player": leg.player,
        "label": leg.label,
        "league": leg.league,
        "commence_ms": leg.commence_ms,
        "market": leg.market,
        "point": leg.point,
        "fair_percent_display": _percent(leg.p_conservative),
        # --- What Kalshi charges, beside what the consensus says it is worth.
        "ask_display": facts["ask_display"],
        "depth_at_ask": facts["depth_at_ask"],
        "quote_age_ms": facts["quote_age_ms"],
        # --- Where the fair number came from.
        "method_spread_display": (
            f"{_method_spread_points(leg):.1f} pts"
            if _method_spread_points(leg) is not None
            else None
        ),
        "book_count": leg.book_count,
        "books_used": json.loads(leg.books_used_json or "[]"),
        "market_width_display": (
            f"{leg.market_width * 100:.1f} pts"
            if leg.market_width is not None
            else None
        ),
        # Neutral wording is the caller's job, and the reason is arithmetic:
        # a sharp anchor selects AT MOST THREE books, so it is a thinner fair
        # value rather than a better one (CLAUDE.md).
        "anchored_on_sharp": leg.anchored_on_sharp,
        "odds_age_ms": leg.odds_age_now_ms,
        # --- What the twelve mechanical checks said, or why they are silent.
        "skeptic": skeptic,
        "suppressed_reason": facts["suppressed_reason"],
        # --- What the scout desk knows about this leg's game (Joe's ruling,
        # 2026-08-30: the Scout gates eligibility and FLAGS, and never moves
        # the price). These are words about a fixture, never an input to one
        # of the numbers above, and never a sort key -- ADR 0071 section 2.5.
        "scout": facts["scout"],
        "scout_headline": facts["scout_headline"],
        "scout_flags": facts["scout_flags"],
        "scout_age_ms": facts["scout_age_ms"],
        # The market ticker the existing briefing was filed against, so the
        # card can link to it. `None` when nothing has been filed for this
        # game -- which is the ordinary case at five convenings a day.
        "scout_ticker": facts["scout_ticker"],
    }


def _serialise_card(card: Card, facts: Optional[dict] = None) -> dict:
    if card.not_built_reason is not None:
        return {
            "key": card.key,
            "title": card.title,
            # On an unbuilt card too: six cards on one screen, and a card
            # the reader cannot name is worse than one they can.
            "what_it_is": card.what_it_is,
            "legs": [],
            "not_built_reason": card.not_built_reason,
            "joint": None,
            "at_stakes": [],
        }

    joint = card.joint
    assert joint is not None  # Card.__post_init__ guarantees it
    low, high = joint.method_range
    return {
        "key": card.key,
        "title": card.title,
        "what_it_is": card.what_it_is,
        "legs": [
            _serialise_leg(leg, (facts or {}).get(leg.kalshi_market_ticker))
            for leg in card.legs
        ],
        "not_built_reason": None,
        "joint": {
            # The headline is the CONSERVATIVE joint: each leg at the lowest
            # of four devig methods, compounded. The range beside it is the
            # same joint under each single method -- the honest band.
            "conservative_percent_display": _percent(joint.conservative),
            # The raw joint beside its rendered forms. The bid control needs a
            # NUMBER to place a price field's reference against, and parsing
            # one back out of "25.1%" is how a screen and a server end up
            # disagreeing by a rounding step on the page that spends money.
            "conservative": joint.conservative,
            "method_range_display": (
                f"{_percent(low)}–{_percent(high)}"
                if low is not None and high is not None
                else None
            ),
            "fair_cost_display": _cost_per_contract(joint.conservative * 1000),
            # **The price to demand where the bet can actually be placed**
            # (ADR 0085). 61 of 61 open combinations on Kalshi carried no
            # quoted ask on 2026-08-30, so the desk prices this parlay far
            # more reliably than it can buy it -- and a sportsbook quotes
            # American odds, not cents on a $1 contract.
            #
            # Break-even, and the words beside it say so. At exactly this
            # price the bet is fair against the consensus and its expected
            # profit is zero.
            "price_to_beat_display": _american_display(joint.conservative),
            # For the chart: the plain product at each prefix. The headline
            # above is the correlation-adjusted joint, and `correlation_note`
            # states the gap between them.
            "prefixes": _prefix_chances(card.legs),
            "correlation_note": (
                "Same-night games move together a little; the headline "
                "already charges for that "
                f"({joint.independence_error_points:+.2f} points vs "
                "treating the legs as independent)."
            ),
        },
        "at_stakes": [
            _stake_row(cents, joint.conservative) for cents in STAKE_PRESETS_CENTS
        ],
    }


#: What a leg's desk facts look like when nothing could be read. Every field
#: absent rather than zeroed -- an ask of 0 is a free contract and a book count
#: of 0 is "no consensus", and neither is what "we did not look" means.
_NO_FACTS: dict = {
    "ask_tenths": None,
    "ask_display": None,
    "depth_at_ask": None,
    "quote_age_ms": None,
    "skeptic": "absent",
    "suppressed_reason": None,
    # --- What the scout desk knows about this leg's GAME. See `_leg_scouting`.
    "scout": "absent",
    "scout_headline": None,
    "scout_flags": [],
    "scout_age_ms": None,
    "scout_ticker": None,
}

#: A board tile in this state means the desk looked and found nothing to say.
#: Every other state is a thing Joe should see -- including the two that are
#: absences rather than findings, which is the whole reason `BoardTile` has
#: four states instead of a boolean (`agents/scout_desk.py`).
_SCOUT_TILE_CLEAR = "clear"


def _leg_scouting(conn, tickers: Sequence[str]) -> dict[str, dict]:
    """The newest scout briefing for each leg's GAME, keyed by leg ticker.

    **A briefing is about a fixture; `scout_briefings.ticker` is a MARKET.**
    The desk is convened from `/api/scout/{ticker}` on whatever market ticker
    happened to be in front of Joe, so a briefing filed against the moneyline
    describes the same game as a prop or spread on that fixture. Matching leg
    ticker to briefing ticker directly would show a game as unscouted while its
    own briefing sat in the table -- so the join is through
    `kalshi_markets.event_ticker`, which is what "the same game" actually means
    here, and which `idx_markets_event` already indexes.

    **This spends nothing.** It reads briefings that exist; it never convenes
    the desk. That matters more than it looks: `AGENT_MAX_SEARCHES_PER_DAY`
    allows **five convenings a day** (`fly.live.toml` -- it binds before the
    24-call cap), so a ladder of six cards could not have its legs scouted
    automatically even once. Any convening stays a deliberate tap.

    **No number crosses from here into a price.** The fields returned are a
    state, a headline, and tiles -- prose, by the same structural rule that
    keeps `DeskBriefing` numeric-free. ADR 0071 §2.5's ordering ban applies
    with full force: a scout flag may be SHOWN on a leg and must never rank
    one.
    """
    if not tickers:
        return {}
    unique = sorted(set(tickers))
    placeholders = ",".join("?" * len(unique))
    rows = conn.execute(
        f"""
        SELECT leg_ticker, status, requested_ms, completed_ms, briefing_json,
               scout_ticker
        FROM (
          SELECT m.ticker           AS leg_ticker,
                 b.ticker           AS scout_ticker,
                 b.status, b.requested_ms, b.completed_ms, b.briefing_json,
                 ROW_NUMBER() OVER (
                   PARTITION BY m.ticker ORDER BY b.requested_ms DESC, b.id DESC
                 ) AS rn
          FROM kalshi_markets m
          JOIN kalshi_markets sm ON sm.event_ticker = m.event_ticker
          JOIN scout_briefings b ON b.ticker = sm.ticker
          WHERE m.ticker IN ({placeholders})
        ) WHERE rn = 1
        """,
        unique,
    ).fetchall()
    return {row["leg_ticker"]: row for row in rows}


def _scout_facts(row, *, now_ms: int) -> dict:
    """One briefing row, read into the five `scout_*` fields.

    The states are the briefing's own, not a re-derivation:

        briefed         complete or partial, and the master filed a headline
        filed_nothing   complete, but the desk had nothing to say
        briefing        still running
        refused         a ceiling turned it away -- budget, searches, tokens
        failed          it died

    `partial` maps to `briefed` rather than to a fourth visible state: a
    briefing with one staff scout missing is still a briefing, and its own
    `conflicts`/`unanswered` fields are where that thinness is already said.
    Inventing a separate chip for it would put the same fact in two places and
    let them disagree.
    """
    facts: dict = {
        "scout": "absent",
        "scout_headline": None,
        "scout_flags": [],
        "scout_age_ms": None,
        "scout_ticker": row["scout_ticker"],
    }
    status = row["status"]
    stamp = row["completed_ms"] or row["requested_ms"]
    if stamp:
        facts["scout_age_ms"] = max(0, now_ms - int(stamp))

    if status == "running":
        facts["scout"] = "briefing"
        return facts
    if status in ("failed", "refused"):
        facts["scout"] = status
        return facts

    try:
        briefing = json.loads(row["briefing_json"] or "null")
    except (TypeError, ValueError):
        briefing = None
    if not isinstance(briefing, dict):
        # Recorded complete with unreadable content. `None` resolves to a
        # refusal to claim, never to "nothing found" -- the convention rule.
        facts["scout"] = "failed"
        return facts

    headline = briefing.get("headline")
    facts["scout_headline"] = headline if isinstance(headline, str) else None
    tiles = briefing.get("board")
    flags = []
    if isinstance(tiles, list):
        for tile in tiles:
            if not isinstance(tile, dict):
                continue
            if tile.get("state") == _SCOUT_TILE_CLEAR:
                continue
            flags.append({
                "category": tile.get("category"),
                "state": tile.get("state"),
                "note": tile.get("note"),
            })
    facts["scout_flags"] = flags
    facts["scout"] = "briefed" if (facts["scout_headline"] or flags) else (
        "filed_nothing"
    )
    return facts


def leg_facts(conn, tickers: Sequence[str], *, now_ms: int) -> dict[str, dict]:
    """Kalshi's own price and the skeptic's verdict, for the SELECTED legs.

    **Two queries for the whole ladder, and the scope is the design.** These
    facts are attached after `build_ladder` has chosen its legs -- at most six
    per card across six cards, deduped to roughly fifteen tickers -- not to the
    ~200 candidates the pool holds. Enriching the pool would put a per-row read
    on a path that already runs every pass, which is the N+1 shape
    `/api/slate` is separately being cured of.

    The ask is DERIVED (`1000 - best NO bid`) through `ask_for_side`, the one
    definition in this codebase, so an empty book resolves to `None` rather
    than to the endpoint. A leg whose book is one-sided has no price you could
    pay, and saying so is the point.

    `skeptic` is three-valued, and the third value is why this is not a
    boolean:

        checked            a `recommendations` row exists; its verdict stands
        not_on_this_path   a SPREAD leg. ADR 0070 keeps spread rows off the
                           recommendations path entirely ("Fair rows only, no
                           recommendations", `runner.py:1882-1884`), so the
                           checks did not run and never will on this row
        absent             a moneyline or PROP the engine has not priced

    Rendering `not_on_this_path` as a blank would read as "the checks passed",
    which is the flattering misreading of a measurement that never happened.

    **A PROP leg is on the recommendations path, and spreads are the only
    exception.** `_price_prop_event` builds a `Candidate` per side and pushes
    it through `_priced_or_counted` (`runner.py:1554-1575`) exactly as the
    moneyline path does, so on a prop `checked` and `absent` carry their
    ordinary meanings. `absent` is common there and is not a defect: the far
    rung of a ladder gets `dropped_no_kalshi_quote` when `is_valid_price`
    refuses a 0/1000-tenth endpoint (`runner.py:1546-1548`).

    So do NOT generalise the `market == "spreads"` test below to
    `market != "h2h"`. That would stamp `not_on_this_path` on prop legs the
    skeptic genuinely did check -- the same misreading as the blank, pointing
    the other way: a measurement that *did* happen, reported as one that never
    ran. `tests/test_parlay_leg_facts.py` pins both directions.
    """
    if not tickers:
        return {}
    unique = sorted(set(tickers))
    placeholders = ",".join("?" * len(unique))

    quotes = {
        row["ticker"]: row
        for row in conn.execute(
            f"""
            SELECT ticker, observed_ms, confirmed_ms, yes_bid_tenths,
                   no_bid_tenths, no_bid_qty
            FROM (
              SELECT ticker, observed_ms, confirmed_ms, yes_bid_tenths,
                     no_bid_tenths, no_bid_qty,
                     ROW_NUMBER() OVER (
                       PARTITION BY ticker ORDER BY observed_ms DESC
                     ) AS rn
              FROM kalshi_quotes
              WHERE ticker IN ({placeholders})
            ) WHERE rn = 1
            """,
            unique,
        ).fetchall()
    }

    suppressed = {
        row["ticker"]: row["suppressed_reason"]
        for row in conn.execute(
            f"""
            SELECT ticker, suppressed_reason FROM (
              SELECT ticker, suppressed_reason,
                     ROW_NUMBER() OVER (
                       PARTITION BY ticker ORDER BY created_ms DESC
                     ) AS rn
              FROM recommendations
              WHERE ticker IN ({placeholders}) AND side = 'yes'
            ) WHERE rn = 1
            """,
            unique,
        ).fetchall()
    }

    scouting = _leg_scouting(conn, unique)

    out: dict[str, dict] = {}
    for ticker in unique:
        facts = dict(_NO_FACTS)
        # A fresh list per leg. `dict(_NO_FACTS)` is a shallow copy, so every
        # leg would otherwise append into one shared `scout_flags`.
        facts["scout_flags"] = []
        scout_row = scouting.get(ticker)
        if scout_row is not None:
            facts.update(_scout_facts(scout_row, now_ms=now_ms))
        quote = quotes.get(ticker)
        if quote is not None:
            ask = ask_for_side(quote, "yes")
            facts["ask_tenths"] = ask
            facts["ask_display"] = format_price(ask) if ask is not None else None
            facts["depth_at_ask"] = quote["no_bid_qty"]
            # `confirmed_ms` when present: a quote re-observed and unchanged is
            # current, not stale, and ADR 0055 only writes a row when it moves.
            seen = quote["confirmed_ms"] or quote["observed_ms"]
            facts["quote_age_ms"] = max(0, now_ms - seen) if seen else None
        if ticker in suppressed:
            facts["skeptic"] = "checked"
            facts["suppressed_reason"] = suppressed[ticker]
        out[ticker] = facts
    return out


def serialise_ladder(
    ladder: Ladder, *, generated_ms: int, facts: Optional[dict] = None
) -> dict:
    return {
        "generated_ms": generated_ms,
        "cards": [_serialise_card(card, facts) for card in ladder.cards],
        "excluded": ladder.excluded,
        "notes": dict(NOTES),
    }


# ---------------------------------------------------------------------------
# "Price on Kalshi" -- the lookup path (ADR 0070, Slice C).
# ---------------------------------------------------------------------------


class LookupRefused(Exception):
    """A lookup that must not proceed, with the HTTP status and the words."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


#: Collections that accept arbitrary sports legs, tried in order when no
#: enumerated collection covers the card's exact events. The 2026-08-23
#: capture posted NFL legs to `KXMVESPORTSMULTIGAMEEXTENDED-R` and Kalshi
#: minted the market under a `KXMVECROSSCATEGORY` shard, so prefix matching
#: is the honest granularity here.
_FALLBACK_COLLECTION_PREFIXES = (
    "KXMVESPORTSMULTIGAMEEXTENDED",
    "KXMVECROSSCATEGORY",
)

#: `fetch_collections` walks up to 25 pages; a per-tap fetch would spend
#: seconds and rate budget on a list that changes rarely. Cached in-process
#: for an hour -- module state, same lifetime as the API process.
_COLLECTIONS_TTL_MS = 3_600_000
_collections_cache: dict = {"at_ms": 0, "items": None}


def invalidate_collections_cache() -> None:
    """Drop the cached collection list.

    Called when a lookup fails against a collection this cache named. The
    `-R` suffix on collection tickers ROTATES (NEXT.md, 2026-08-23) and the
    fallback is prefix-matched rather than pinned, so a rotation turns every
    tap into a 502 against a ticker that no longer exists -- for up to an
    hour, with no recovery short of restarting the process. A failure is the
    only evidence available that the list has moved, so it is what clears it.
    """
    _collections_cache["items"] = None
    _collections_cache["at_ms"] = 0


async def _collections(api, *, now_ms: int):
    """The collection list, cached. Raises `LookupRefused` when it cannot.

    **An empty result is never cached.** `fetch_collections` returning `[]` is
    indistinguishable at this layer from a transient walk failure, and caching
    it hands the screen "Kalshi lists no combination collection" -- a confident
    statement about the venue -- for the full hour. Unreadable resolves to a
    refusal, never to a fact (`tasks/lessons.md`).
    """
    cache = _collections_cache
    if (
        cache["items"] is not None
        and now_ms - cache["at_ms"] <= _COLLECTIONS_TTL_MS
    ):
        return cache["items"]
    try:
        items = await fetch_collections(api)
    except Exception as exc:  # noqa: BLE001 -- every transport failure is one refusal
        # A cold-cache failure used to escape this function and leave FastAPI
        # to render a bare 500, with no `parlay_lookups` row -- the caller
        # cannot record what it never learned about. Now it is the same shape
        # as every other refusal on this path.
        raise LookupRefused(
            502,
            "Kalshi's list of combination collections could not be read "
            f"({exc}). Nothing was created.",
        ) from exc
    if items:
        cache["items"] = items
        cache["at_ms"] = now_ms
    return items


class _Chosen(NamedTuple):
    """A collection, and whether anything is known about it accepting the legs.

    Two values, not one, because until 2026-08-27 the caller could not tell the
    two apart and neither could the record. `verified=False` means the prefix
    fallback picked it and the legs were never checked against anything.
    """

    collection: object
    verified: bool


def _choose_collection(
    collections, leg_event_tickers: set[str], *, leg_count: int = 0
):
    """The collection to mint under: coverage first, then the catch-all
    collections by prefix, else nothing (refused in words).

    Returns `None`, or a `_Chosen` saying which of the two routes was taken.

    **The fallback does not check the legs, and that is deliberate rather than
    an oversight.** `_FALLBACK_COLLECTION_PREFIXES` records that the 2026-08-23
    capture posted NFL legs to `KXMVESPORTSMULTIGAMEEXTENDED-R` and Kalshi
    minted the market anyway -- so a catch-all's enumerated leg list understates
    what it accepts, and refusing on non-coverage would refuse taps that work.
    Nobody has measured how often the fallback fires or how often Kalshi then
    accepts it; `parlay_lookups.collection_unverified` exists to find out.

    **What IS refused here is `size_min`, and only that.** Reading the
    committed capture: all three catch-all collections carry `size_min 2`,
    `size_max 0` and `is_all_yes False`. So `size_max = 0` is an unbounded
    sentinel and `is_all_yes False` means *unrestricted*, not yes-only -- a
    guard on either would have refused every tap this desk can make, which is
    an outage rather than a check. `size_min` is the one that means what it
    reads like. `leg_count` defaults to 0 so a caller that does not pass it
    gets the old behaviour rather than a silent refusal.
    """
    eligible = [
        c for c in collections
        if c.scope in (ComboScope.MULTI_GAME, ComboScope.CROSS_SPORT,
                       ComboScope.CROSS_CATEGORY)
    ]
    if leg_count:
        # Server-side, because `PriceOnKalshi.tsx`'s `legs.length < 2` is the
        # only other size guard and CLAUDE.md is explicit that the server never
        # trusts the UI to have disabled a button.
        eligible = [c for c in eligible if leg_count >= (c.size_min or 0)]
    covering = [
        c for c in eligible
        if leg_event_tickers <= {leg.event_ticker for leg in c.legs}
    ]
    if covering:
        return _Chosen(
            min(covering, key=lambda c: (len(c.legs), c.collection_ticker)),
            True,
        )
    for prefix in _FALLBACK_COLLECTION_PREFIXES:
        matches = sorted(
            (c for c in eligible if c.collection_ticker.startswith(prefix)),
            key=lambda c: c.collection_ticker,
        )
        if matches:
            return _Chosen(matches[0], False)
    return None


#: How stale the cached eligibility list may be before the ladder stops
#: trusting it. Two hours is three misses of the hourly refresh -- loose
#: enough that one failed walk does not change the screen, tight enough that a
#: list from yesterday never does.
COMBO_ELIGIBILITY_TTL_MS = 7_200_000


def store_combo_eligibility(conn, event_tickers, *, now_ms: int) -> int:
    """Replace the cached eligible-leg list. Returns how many were written.

    **Refuses to write an empty list**, and that refusal is the whole safety
    property: `fetch_collections` returning nothing is indistinguishable here
    from a transient walk failure, and persisting it would tell the ladder that
    Kalshi combines nothing -- emptying the parlay desk until the next refresh
    happened to succeed. Same rule as `_collections`'s in-process cache, one
    layer down. Unreadable resolves to a refusal to claim, never to a fact.
    """
    tickers = {t for t in event_tickers if t}
    if not tickers:
        return 0
    conn.execute("DELETE FROM combo_eligible_events")
    conn.executemany(
        "INSERT INTO combo_eligible_events (event_ticker, refreshed_ms) "
        "VALUES (?, ?)",
        [(t, now_ms) for t in sorted(tickers)],
    )
    conn.commit()
    return len(tickers)


def combo_eligible_events(conn, *, now_ms: int) -> Optional[set[str]]:
    """The cached eligible legs, or `None` when they cannot be trusted.

    `None` means **unknown** -- never "empty". A caller must not filter on
    `None`; it is the state where the desk shows everything and says nothing,
    which is the honest behaviour when the cache is cold (a fresh volume, a
    deploy, three failed refreshes in a row).
    """
    row = conn.execute(
        "SELECT MAX(refreshed_ms) AS at_ms FROM combo_eligible_events"
    ).fetchone()
    if row is None or row["at_ms"] is None:
        return None
    if now_ms - int(row["at_ms"]) > COMBO_ELIGIBILITY_TTL_MS:
        return None
    return {
        r["event_ticker"]
        for r in conn.execute(
            "SELECT event_ticker FROM combo_eligible_events"
        ).fetchall()
    }


#: How often the loop re-walks Kalshi's collections. An hour against a
#: `COMBO_ELIGIBILITY_TTL_MS` of two: the cache survives one missed refresh
#: without changing what the desk shows, so a single failed walk is invisible
#: rather than a visible wobble in the parlay page.
COMBO_ELIGIBILITY_REFRESH_MS = 3_600_000


def combo_eligibility_is_due(conn, *, now_ms: int) -> bool:
    """Whether the cached list is old enough to be worth a walk.

    Separate from `refresh_combo_eligibility` so the caller can decide without
    paying for a client, and so the "at most hourly" rule is one predicate the
    loop and its test both read rather than a comparison spelled inline.
    """
    row = conn.execute(
        "SELECT MAX(refreshed_ms) AS at_ms FROM combo_eligible_events"
    ).fetchone()
    if row is None or row["at_ms"] is None:
        return True
    return now_ms - int(row["at_ms"]) >= COMBO_ELIGIBILITY_REFRESH_MS


async def refresh_combo_eligibility(conn, api, *, now_ms: int) -> Optional[int]:
    """Walk Kalshi's collections and cache which events it will combine.

    Returns the number stored, or `None` if the walk failed or was refused.

    **Every failure is swallowed, deliberately.** This runs inside the
    scheduler pass, and the pass must not die for a cache refresh whose only
    consequence is that a screen filters less. `2026-08-28` is the whole
    argument: one unpriceable parlay leg raised `ZeroDivisionError` inside
    `score_settle_and_alert` and stopped the daily digest, the parlay cards and
    `log_gate_progress` with it. A network walk is a far likelier thing to
    throw than an arithmetic bug.
    """
    try:
        collections = await fetch_collections(api)
    except Exception:  # noqa: BLE001 -- advisory cache; never breaks a pass
        logger.warning("combo eligibility refresh failed", exc_info=True)
        return None
    return store_combo_eligibility(
        conn, _combinable_events(collections), now_ms=now_ms
    )


def _combinable_events(collections) -> set[str]:
    """Every event ticker that appears as a leg in ANY eligible collection.

    **The union, deliberately, and it is a different question from
    `_choose_collection`'s.** That one asks "does one collection carry all of
    these legs" and falls back when the answer is no, because the 2026-08-23
    capture showed a catch-all's enumerated list *understating* what it
    accepts -- Kalshi minted NFL legs the chosen collection did not list. That
    evidence is real and this does not overturn it.

    What it distinguishes is the case that evidence does not cover: a leg that
    appears in **no** collection at all. "Not in the one we picked" and "not in
    anything Kalshi combines" are different claims, and only the second can be
    refused without contradicting the capture.

    Measured 2026-08-28, and it is why this exists: `KXMVECROSSCATEGORY-R`,
    `KXMVECROSSCATEGORY-SHARD1-R` and `KXMVESPORTSMULTIGAMEEXTENDED-R` carry
    the **same 2,365 legs**, of which 64 are NCAAF and every one of those is
    inside two days. Three live taps on NCAAF cards dated a week out covered
    1 of 6, 1 of 6 and 1 of 3 legs, and Kalshi answered HTTP 400
    `invalid_parameters` to all three. Kalshi trades those games as singles
    and will not combine them. `parlay_lookups` separates perfectly on
    `collection_unverified`: 3 of 3 unverified taps errored, 0 of 9 verified
    ones did.
    """
    return {
        leg.event_ticker
        for c in collections
        if c.scope in (ComboScope.MULTI_GAME, ComboScope.CROSS_SPORT,
                       ComboScope.CROSS_CATEGORY)
        for leg in c.legs
    }


def _record_lookup(conn, *, now_ms, card_key, stake_cents, legs, status,
                   collection_ticker=None, minted=None, no_bid_tenths=None,
                   ask_tenths=None, depth=None, fair_joint=None, hold=None,
                   error=None, collection_unverified=False) -> None:
    """Every lookup is recorded, every outcome -- it minted a real market."""
    conn.execute(
        "INSERT INTO parlay_lookups (requested_ms, card_key, stake_cents, "
        "selected_legs, collection_ticker, status, minted_market_ticker, "
        "book_no_bid_tenths, derived_yes_ask_tenths, book_depth, "
        "fair_joint_conservative, hold, error, collection_unverified) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            now_ms, card_key, stake_cents,
            json.dumps([
                {"event_ticker": e, "market_ticker": m} for e, m in legs
            ]),
            collection_ticker, status, minted, no_bid_tenths, ask_tenths,
            depth, fair_joint, hold, error,
            1 if collection_unverified else 0,
        ),
    )
    conn.commit()


def resolve_requested_legs(
    candidates: Sequence[CandidateLeg],
    *,
    card_key: str,
    requested_legs: Sequence[tuple[str, str]],
    max_odds_age_ms: int,
) -> list[CandidateLeg]:
    """The legs the reader tapped, checked one at a time, or a refusal.

    **This replaces a set-equality check, and the reason is a bug Joe hit on
    2026-08-30.** The old rule was `served == requested`: the ladder was
    rebuilt at tap time and the card's legs had to be byte-identical to the
    ones the page had rendered. But the ladder re-derives its ranking from the
    freshest consensus on every request, so a quote pass landing between the
    render and the tap swapped a marginal leg and the tap was refused --
    telling him to refresh, which started the same race again. On a degraded
    box, where the page took ~15s to render and passes ran ~40s, the window in
    which a card was still "the same card" was shorter than the time it takes
    to read it, and the button could not be used at all.

    **The legs the client echoes ARE the card the reader tapped.** What has to
    be true is not that the desk would still pick them -- it is that each one
    is still a leg the desk would serve: on the slate, pre-game, fresh, and
    carrying a usable probability. That is a per-leg question and this asks
    it per leg.

    Bounded on purpose, because a lookup MINTS A REAL MARKET on the exchange:

    - every requested leg must be in the current usable candidate pool, so a
      client cannot name an arbitrary ticker and have it created;
    - at most one leg per fixture, which is the ladder's own guard and the
      reason `CorrelationRefused` is unreachable (a same-game parlay needs a
      correlation this repo has not measured, ADR 0012 section 5);
    - the count must fit the named card's recipe, so "safe" cannot be used to
      mint a nine-leg combination.

    Refuses in words naming the leg and the reason, never "the slate moved".
    """
    requested = list(dict.fromkeys(requested_legs))
    if not requested:
        raise LookupRefused(400, "no legs were sent to price.")

    recipe = next((r for r in CARD_SHAPES if r.key == card_key), None)
    if recipe is None:
        raise LookupRefused(404, f"no card named {card_key!r}")
    if not recipe.min_legs <= len(requested) <= recipe.max_legs:
        raise LookupRefused(
            409,
            f"the {recipe.title} card takes {recipe.min_legs}-"
            f"{recipe.max_legs} legs and {len(requested)} were sent. Nothing "
            "was created.",
        )

    by_key = {
        (leg.kalshi_event_ticker, leg.kalshi_market_ticker): leg
        for leg in candidates
    }
    selected: list[CandidateLeg] = []
    refusals: list[str] = []
    for event_ticker, market_ticker in requested:
        leg = by_key.get((event_ticker, market_ticker))
        if leg is None:
            # Absent from the pool entirely. `ladder_candidates` is pre-game
            # and tonight-only, so the overwhelmingly likely reason is that
            # the game has started -- but "likely" is not "measured", and the
            # sentence says what is known rather than guessing which.
            refusals.append(
                f"{market_ticker} is no longer on the desk's slate (its game "
                "has started, or it is past tonight's last game)"
            )
            continue
        reason = unusable_reason(leg, max_odds_age_ms=max_odds_age_ms)
        if reason is not None:
            refusals.append(
                f"{market_ticker}: {UNUSABLE_REASONS[reason]}"
            )
            continue
        selected.append(leg)

    if refusals:
        raise LookupRefused(
            409,
            "these legs cannot be priced right now, so nothing was created: "
            + "; ".join(refusals)
            + ". Reload the desk to see what it is offering instead.",
        )

    fixtures = {leg.odds_event_id for leg in selected}
    if len(fixtures) != len(selected):
        raise LookupRefused(
            409,
            "two of these legs are on the same game. The desk does not price "
            "same-game combinations: their correlation is not measured, and "
            "multiplying them as independent would overstate the chance. "
            "Nothing was created.",
        )
    return selected


def _minted_market_facts(response) -> Optional[dict]:
    """The three fields a bid needs from the mint response, and nothing else.

    **Narrow rather than verbatim, for two reasons.** The venue's market object
    carries an `event_ticker`, and `test_the_caveats_travel_with_the_price`
    walks every key in this payload asserting none begins with "ev" -- the ADR
    0046 guard against a fee-net EV field appearing near a combination price.
    It is a false positive on the word "event" and the guard is still right.

    The second reason survives the first: this payload reaches a browser, and
    forwarding a venue object whole means every field Kalshi adds later ships
    to the client without anyone deciding it should.

    `None` when the mint described nothing -- the caller refuses rather than
    guessing a grid or a shard.
    """
    market = response.get("market") if isinstance(response, dict) else None
    if not isinstance(market, dict):
        return None
    return {
        "price_ranges": market.get("price_ranges"),
        "price_level_structure": market.get("price_level_structure"),
        "exchange_index": market.get("exchange_index"),
    }


async def price_card_on_kalshi(
    conn,
    *,
    card_key: str,
    stake_cents: int,
    requested_legs: Sequence[tuple[str, str]],
    now_ms: int,
    max_odds_age_ms: int,
    api,
) -> dict:
    """Mint (or find) the card's combo on Kalshi and price it off its book.

    **The legs the client echoes are what gets priced**, each one re-checked
    server-side against the current candidate pool (`resolve_requested_legs`).
    A lookup mints a real market, so it must price the card the user tapped --
    and until 2026-08-30 this function read that requirement backwards: it
    rebuilt the ladder and refused unless the desk would still *select* the
    same legs, which a single quote pass landing mid-tap was enough to break.
    The quoted cost comes from the
    minted market's ORDER BOOK (derived YES ask = 1000 - best resting NO
    bid), never the `/markets` list row (ADR 0012, E2/E3: leg echo, list-vs-
    book skew to 30.5c). An empty book is an honest refusal, not a price --
    and the 2026-08-23 capture shows a freshly minted combo's book IS empty
    on both sides, so that refusal is the expected first answer.

    No fee-net EV anywhere (ADR 0046): the hold is fee-free arithmetic
    (`1 - fair x offered decimal`) and the fee sentence travels beside it.
    """
    candidates, _ = ladder_candidates(
        conn, now_ms=now_ms, max_odds_age_ms=max_odds_age_ms
    )
    # **The ladder is deliberately NOT rebuilt here.** It was, and rebuilding
    # it was the defect: a card the desk cannot compose *this second* is not a
    # reason to refuse legs that are each still buyable, and the "Next 3
    # hours" cut alone turns that into a refusal every time an hour passes.
    # It also cost a 200,000-sample copula per card on a path that needs one
    # joint -- `joint_for(selected)` computes exactly the one being priced.
    selected = resolve_requested_legs(
        candidates,
        card_key=card_key,
        requested_legs=requested_legs,
        max_odds_age_ms=max_odds_age_ms,
    )
    served = {(l.kalshi_event_ticker, l.kalshi_market_ticker) for l in selected}

    # `sorted`, not `list`: `served` is a set, so its iteration order varies
    # by hash seed across processes. That order is what goes on the wire to
    # Kalshi and into `selected_legs`, which makes the audit table's rows
    # incomparable between restarts for no reason at all.
    legs = sorted(served)
    try:
        collections = await _collections(api, now_ms=now_ms)
    except LookupRefused as exc:
        # Recorded, then re-raised unchanged. The audit table's docstring
        # promises a row for every outcome, and a failure to read the
        # collection list is an outcome.
        _record_lookup(
            conn, now_ms=now_ms, card_key=card_key, stake_cents=stake_cents,
            legs=legs, status="error", error=exc.detail,
        )
        raise
    chosen = _choose_collection(
        collections, {event for event, _ in served}, leg_count=len(legs),
    )
    collection = chosen.collection if chosen else None
    unverified = bool(chosen) and not chosen.verified
    if collection is None:
        _record_lookup(
            conn, now_ms=now_ms, card_key=card_key, stake_cents=stake_cents,
            legs=legs, status="no_collection",
        )
        return {
            "status": "no_collection",
            "words": (
                "Kalshi lists no combination collection that accepts these "
                "legs right now. Nothing was created."
            ),
        }

    # **Refused before the POST, not after Kalshi says 400.** A leg in no
    # collection's list is one the venue does not combine at all, which is a
    # fact the screen can state in its own words instead of surfacing
    # `{"error":{"code":"invalid_parameters"}}` at a reader who cannot act on
    # it. Joe hit exactly this on 2026-08-28 with a card of Sep 3-5 NCAAF
    # games: real Kalshi markets, priced fine as singles, absent from every
    # combination collection.
    #
    # **Only when the union is non-empty.** `parse_collection` returns a
    # collection with zero legs when the wire omits the detail block --
    # `backend/kalshi/combos.py` records four whole collections doing that --
    # so an empty union is a failed read, not a venue that combines nothing.
    # Refusing every card on it would be an outage wearing a guard's clothes,
    # and the repo's rule is that unreadable resolves to a refusal to claim,
    # never to a fact.
    combinable = _combinable_events(collections)
    if combinable:
        absent = sorted({event for event, _ in served} - combinable)
        if absent:
            # **`no_collection` in the table, `legs_not_combinable` on the
            # wire, and the mismatch is deliberate.** `parlay_lookups` carries
            # `CHECK (status IN ('priced','book_empty','no_collection',
            # 'error'))`, so a new status here would fire the guard and then
            # crash the INSERT -- turning a clean refusal into a 500, which is
            # strictly worse than the HTTP 400 this replaces. SQLite cannot
            # ALTER a CHECK, so widening it is a table rebuild; that is a
            # migration and it is not worth bundling into an undeployed batch.
            #
            # The distinction is not lost: it goes in `error`, which is free
            # text and unconstrained. `no_collection` is also honestly true of
            # this row -- no collection accepts these legs -- it is simply
            # less specific than what the screen is told.
            _record_lookup(
                conn, now_ms=now_ms, card_key=card_key,
                stake_cents=stake_cents, legs=legs,
                status="no_collection",
                collection_ticker=collection.collection_ticker,
                collection_unverified=unverified,
                error="legs_not_combinable: " + ", ".join(absent),
            )
            n, total = len(absent), len(served)
            return {
                "status": "legs_not_combinable",
                "words": (
                    f"Kalshi will not combine {n} of these {total} games. It "
                    "trades them on their own, but they are not in any of its "
                    "combination collections, so this card cannot be priced "
                    "as one bet. Nothing was created. "
                    + ", ".join(absent)
                ),
                "absent_event_tickers": absent,
            }

    try:
        response = await lookup_combo(
            api, collection.collection_ticker, legs,
            side="yes", allow_market_creation=True,
        )
    except Exception as exc:  # noqa: BLE001 -- recorded, then re-raised as words
        _record_lookup(
            conn, now_ms=now_ms, card_key=card_key, stake_cents=stake_cents,
            legs=legs, status="error",
            collection_ticker=collection.collection_ticker, error=str(exc),
            collection_unverified=unverified,
        )
        # **Only when coverage picked it.** The flush is for a rotated `-R`
        # suffix making a cached list stale, and on that theory throwing the
        # list away is right. It is the wrong theory for a collection the
        # prefix fallback chose without checking the legs: there the list was
        # fine and the legs were the problem, so flushing discards a good
        # fetch and re-buys it on the next tap. Without the flush at all, one
        # rotation means an hour of 502s -- so it is narrowed, not removed.
        if not unverified:
            invalidate_collections_cache()
        raise LookupRefused(
            502, f"Kalshi refused the combination: {exc}"
        ) from exc

    minted = response.get("market_ticker") or (
        (response.get("market") or {}).get("ticker")
    )
    if not minted:
        _record_lookup(
            conn, now_ms=now_ms, card_key=card_key, stake_cents=stake_cents,
            legs=legs, status="error",
            collection_ticker=collection.collection_ticker,
            error=f"no market_ticker in response keys {sorted(response)}",
            collection_unverified=unverified,
        )
        raise LookupRefused(
            502, "Kalshi answered without naming the minted market."
        )

    # **What Kalshi says it minted, against what was asked for.** Until
    # 2026-08-27 nothing read this, so a market minted over the wrong legs --
    # the other team, say -- would have been priced and shown as the card. It
    # cannot prevent the mint, which has already happened by the time the
    # response exists; it is the difference between a wrong bet shown as right
    # and a refusal that says so.
    #
    # `unreadable` is NOT treated as agreement. It is recorded and the tap
    # proceeds, because the market exists either way and refusing would lose a
    # real ticker off the audit table for a field Kalshi merely stopped
    # sending. A mismatch is different and does refuse.
    echo = echoed_legs(legs, response, side="yes")
    if echo.verdict != "match":
        logger.warning(
            "combo leg echo %s on %s: %s", echo.verdict, minted, echo.detail
        )
    if echo.is_mismatch:
        _record_lookup(
            conn, now_ms=now_ms, card_key=card_key, stake_cents=stake_cents,
            legs=legs, status="error",
            collection_ticker=collection.collection_ticker, minted=minted,
            error=f"leg echo mismatch: {echo.detail}",
            collection_unverified=unverified,
        )
        raise LookupRefused(
            502,
            "Kalshi minted a combination whose legs are not the ones asked "
            "for. Nothing is priced; the market exists and is recorded.",
        )

    # Inside its own try: the market is ALREADY MINTED by the time this runs,
    # so an httpx timeout / 429 / 5xx here loses a real ticker off the audit
    # table -- the one outcome where a missing row costs something, because
    # nothing else in this repo records that the combination now exists.
    try:
        book_payload = await api.orderbook(minted, depth=10)
        book = OrderBook(ticker=minted)
        book.apply_snapshot(book_payload, None, now_ms)
    except Exception as exc:  # noqa: BLE001 -- recorded WITH the ticker, then worded
        _record_lookup(
            conn, now_ms=now_ms, card_key=card_key, stake_cents=stake_cents,
            legs=legs, status="error",
            collection_ticker=collection.collection_ticker, minted=minted,
            error=f"orderbook after mint: {exc}",
            collection_unverified=unverified,
        )
        raise LookupRefused(
            502,
            f"Kalshi created the market ({minted}) but its order book could "
            f"not be read ({exc}). Nothing is priced; the combination exists "
            "and can be looked at in the Kalshi app.",
        ) from exc

    # **Over the legs being priced, not over the card as the ladder would
    # build it now.** Those were the same set until 2026-08-30 because the
    # lookup refused whenever they differed; now that a reader's own legs are
    # priced, a joint taken from `card.joint` would be a fair value for a
    # different combination than the one Kalshi just minted.
    joint = joint_for(selected)
    # The derived-ask identity, through the ONE implementation. `1000 -
    # best_no_bid` was written out by hand here; `OrderBook.best_yes_ask` is
    # the same arithmetic via `complement`, and the venue's most-repeated
    # correction does not need a second copy.
    best_no_bid = book.best_no_bid
    ask_tenths = book.best_yes_ask

    if ask_tenths is None:
        _record_lookup(
            conn, now_ms=now_ms, card_key=card_key, stake_cents=stake_cents,
            legs=legs, status="book_empty",
            collection_ticker=collection.collection_ticker, minted=minted,
            fair_joint=joint.conservative, collection_unverified=unverified,
        )
        return {
            "status": "book_empty",
            "minted_market_ticker": minted,
            # **Carried on THIS branch above all others.** An empty book is
            # the expected first answer on a freshly minted combination, so
            # this is the path a bid actually travels -- and it is where the
            # 404 race bit on 2026-08-30. See the note on the `priced` return.
            "minted_market": _minted_market_facts(response),
            # The legs' clocks, for the same auto-cancel deadline the priced
            # branch supplies. Without them a bid placed off an empty book
            # would carry no deadline and never be withdrawn at kickoff.
            "legs": [
                {
                    "market_ticker": leg.kalshi_market_ticker,
                    "commence_ms": leg.commence_ms,
                }
                for leg in selected
            ],
            "fair": {"conservative": joint.conservative},
            "words": (
                "Kalshi created the market, but nothing is resting in its "
                "book -- no one is offering to sell this combination, so "
                "there is no price you could actually pay right now. Every "
                "freshly minted combo book this tool has read looked exactly "
                "like this; the app may show a number, but a number nobody "
                "will trade at is not a cost. Try again shortly, or build it "
                "in the Kalshi app and compare its quote to the fair value "
                "on the card."
            ),
        }

    depth = book.depth_at_ask("yes")
    valuation = value_parlay(
        ParlayQuote(
            legs=tuple(
                Leg(
                    label=l.kalshi_market_ticker,
                    probability=l.p_conservative,
                    event_key=l.odds_event_id,
                    league=l.league,
                    commence_ms=l.commence_ms,
                )
                for l in selected
            ),
            offered_decimal=1000.0 / ask_tenths,
        )
    )
    _record_lookup(
        conn, now_ms=now_ms, card_key=card_key, stake_cents=stake_cents,
        legs=legs, status="priced",
        collection_ticker=collection.collection_ticker, minted=minted,
        no_bid_tenths=best_no_bid, ask_tenths=ask_tenths, depth=depth,
        fair_joint=joint.conservative, hold=valuation.hold,
        collection_unverified=unverified,
    )

    return {
        "status": "priced",
        "minted_market_ticker": minted,
        "quoted": {
            # Derived from the book, stated so the screen can say so: the
            # ask is the complement of the best resting NO bid.
            "ask_display": _cost_per_contract(ask_tenths),
            "depth_display": (
                None if depth is None
                else f"about {depth:g} contracts resting at that price"
            ),
            "at_stake": _at_stake(stake_cents, ask_tenths=ask_tenths, depth=depth),
        },
        "fair": {
            "conservative_percent_display": _percent(joint.conservative),
            "fair_cost_display": _cost_per_contract(joint.conservative * 1000),
            # The raw joint beside its rendered forms, for the ONE caller that
            # needs a number rather than a string: a resting bid freezes the
            # fair value it was placed against (ADR 0084), and re-deriving it
            # later would record a different instant under the same name --
            # the contamination ADR 0082's snapshot exists to prevent.
            "conservative": joint.conservative,
        },
        # **The legs' clocks, for the auto-cancel deadline.** A resting bid is
        # cancelled when the earliest leg starts, and the alternative to
        # carrying the stamps here is a second `ladder_candidates` scan on the
        # one path that spends money.
        # Deliberately market ticker and clock only. An `event_ticker` here
        # trips `test_the_caveats_travel_with_the_price`, which walks every key
        # in this payload asserting none starts with "ev" -- the ADR 0046 guard
        # against a fee-net EV field appearing anywhere near a combination
        # price. It is a false positive on the word "event" and the guard is
        # still right: the client already knows its own legs, so the field
        # bought nothing and the check stays strict.
        "legs": [
            {
                "market_ticker": leg.kalshi_market_ticker,
                "commence_ms": leg.commence_ms,
            }
            for leg in selected
        ],
        # **The venue's own market object from the MINT response, verbatim.**
        #
        # Carried because the alternative was a race that cost a 500 in front
        # of Joe on 2026-08-30: the bid path re-read `GET /markets/{ticker}`
        # for the price grid and the exchange shard, and that endpoint returns
        # 404 `not_found` for a combination minted seconds earlier -- the
        # catalogue lags the mint, even though the orderbook endpoint answers
        # for the same ticker immediately (this function has just used it).
        #
        # The mint response already carries `price_ranges`,
        # `price_level_structure` and `exchange_index`, so the second read was
        # redundant as well as racy. Passing it through means the bid is
        # priced and routed from the same payload that created the market.
        "minted_market": _minted_market_facts(response),
        "hold_display": f"{valuation.hold * 100:.1f}%",
        "verdict": valuation.verdict,
        "notes": {
            "enter_only": NOTES["enter_only"],
            "fee": NOTES["fee"],
        },
    }


def build_ladder_payload(conn, *, now_ms: int, max_odds_age_ms: int) -> dict:
    candidates, excluded = ladder_candidates(
        conn, now_ms=now_ms, max_odds_age_ms=max_odds_age_ms
    )
    ladder = build_ladder(
        candidates, max_odds_age_ms=max_odds_age_ms, now_ms=now_ms
    )
    merged = dict(ladder.excluded)
    for reason, n in excluded.items():
        merged[reason] = merged.get(reason, 0) + n
    # The selected legs, not the candidate pool: at most six per card across
    # six cards, deduped. `leg_facts` is two queries for the whole ladder.
    selected = [
        leg.kalshi_market_ticker for card in ladder.cards for leg in card.legs
    ]
    return serialise_ladder(
        Ladder(cards=ladder.cards, excluded=merged),
        generated_ms=now_ms,
        facts=leg_facts(conn, selected, now_ms=now_ms),
    )
