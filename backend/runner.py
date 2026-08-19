"""The chain runner: the loop that actually records evidence.

Every stage below already existed and was tested in isolation. Nothing joined
them, so `persist_recommendation` was called only by `seed_demo.py` and the test
suite, `odds_snapshots` had a writer and no reader, and `fair_prices` had
neither. The measurement layer was correct and completely idle: the gate wants
300 independent games and the record contained zero.

That matters on a calendar rather than a backlog. 300 independent games at
roughly fifteen a day is three weeks of unbroken recording, so every day not
recording is a day added to the earliest date this project can answer its own
question.

The chain
---------
Two passes, deliberately separable:

**Ingest** (`run_ingest_pass`) touches the network -- discovery, an odds sweep
inside the credit budget, and an orderbook read for the markets that survived
linking. Kalshi REST is cheap and The Odds API is not: the free tier is ~16
credits a day and one sweep costs `markets x regions`, so linking happens
*before* quoting and the sweep is planned against the budget rather than
attempted and refused. *When* to spend those two calls is `odds/timing.py`'s
decision, not this module's: a sweep makes the slate bettable for fifteen
minutes, so it is worth almost nothing unless those fifteen minutes sit just
before a kickoff.

**Pricing** (`run_pricing_pass`) touches nothing external. It reads what ingest
stored, devigs it, and writes recommendations. Keeping it offline is what makes
the whole chain testable against captured payloads instead of a live slate --
the rule this project already has, and the one that was skipped for the
WebSocket path with the result that it stayed dead through 611 passing tests.

What this does not do yet
-------------------------
- **Spreads and totals** are stored by ingest and ignored by pricing. They need
  the model's margin distribution to price, and shipping them half-done would
  put rows in the evidence record that nothing can score.

  MLB **player props** are priced, since 2026-08-15. They needed the
  per-`outcome_point` grouping spreads also need, but not the margin
  distribution: a prop is a two-sided Over/Under on one published line, so the
  same devig the moneyline uses applies unchanged once the rows are grouped by
  (player, line) instead of by event. **This does not mean an edge exists** --
  at the deployed fee coefficient the scoping probe found zero prop rows
  clearing against a real consensus. They are priced so they can be scored on
  CLV against Kalshi's own close, which is the only thing that can say whether
  a gap against soft books was ever real.
- No orders. `suggested_contracts` is advice; the execution path is separate
  and stays behind the gate.
- Exposure is read from live **orders**, through the same
  `store.orders.current_exposure_dollars` the order endpoint uses, so the
  number a recommendation is sized against and the number the resulting order
  is sized against cannot disagree. It is zero in production today because
  every order placed so far has been a dry run.
- **Pre-game only.** A fixture whose sportsbook kickoff has passed is dropped
  rather than priced. Comparing a stored pre-game consensus against a Kalshi
  price that has absorbed two innings produces edges an order of magnitude
  wider in both directions, and none of those rows can ever be scored.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Collection, Iterable, Optional, Sequence

from .agents.review import ReviewCandidate, review_surfaced
from .config import (
    REFERENCE_BANKROLL_DOLLARS,
    REFERENCE_MAX_DAILY_LOSS_DOLLARS,
    REFERENCE_MAX_EXPOSURE_DOLLARS,
    REFERENCE_MAX_POSITION_DOLLARS,
    OddsConfig,
    RiskConfig,
)
from .core.devig import DevigError, consensus_devig
from .core.prices import is_valid_price
from .core.suppression import ALL_CHECK_NAMES, SuppressionConfig
from .engine import (
    Candidate,
    build_recommendation,
    ensure_strategy_config,
    persist_if_changed,
)
from .kalshi.discovery import DiscoveredEvent, discover_from_events
from .kalshi.props import (
    ALTERNATE_SUFFIX,
    MARKET_TYPE_PROP,
    PROP_SERIES,
    base_market,
    norm,
)
from .match.linker import (
    EXACT_ALIAS_PAIR,
    LinkedFixture,
    MatchCandidate,
    TeamAliases,
    fixture_segment,
    link_event,
    link_prop_event,
    load_aliases,
    record_link,
    record_unmatched,
    resolve_outcome,
)
from .odds.budget import sweep_cost
from .odds.client import (
    PROP_BASE_MARKETS,
    PROP_MARKETS,
    OddsQuote,
    prop_market_keys,
    store_quotes,
)
from .odds.sweeplog import NO_DATA, SERVED, SKIPPED, record_sweep_outcome
from .odds.timing import (
    DEFAULT_DAY_START_UTC_HOUR,
    MANUAL,
    SCHEDULED,
    ManualRefresh,
    SweepDecision,
    SweepSlot,
    decide_sweeps,
)
from .store import db, retention
from .store.db import ask_for_side, now_ms
from .settlement import daily_realised_pnl_dollars, open_position_dollars
from .store.orders import ORDERS_ARE_DRY_RUNS, current_exposure_dollars

logger = logging.getLogger(__name__)

# The market this runner prices. Stored ingest is broader; see the module
# docstring for why pricing is narrower.
MONEYLINE = "h2h"

# Books that take size from professionals and move first. Passed to
# `consensus_devig`, which anchors on them when any are present.
SHARP_BOOKS = frozenset({"pinnacle", "betfair_ex_eu", "betfair_ex_uk", "matchbook"})

# How far a book's own timestamp may sit ahead of ours before it is reported.
# A second or two is ordinary clock drift between hosts; minutes is a signal
# that the timestamps -- which every freshness decision reads -- are wrong.
CLOCK_SKEW_TOLERANCE_MS = 5_000


@dataclass
class PassCounts:
    """What each stage produced. Every stage reports, including the drops.

    A runner that reports only successes looks identical whether it priced forty
    games or silently dropped thirty-nine of them at the link step. The
    `*_dropped` fields exist so a pass that produces nothing says *where* it
    stopped.
    """

    events_discovered: int = 0
    events_linked: int = 0
    events_unmatched: int = 0
    odds_sweeps: int = 0
    odds_quotes_stored: int = 0
    markets_quoted: int = 0
    fair_prices_written: int = 0
    recommendations: int = 0
    surfaced: int = 0
    suppressed: int = 0
    # Not "skipped". An unchanged decision is re-derived and the existing row is
    # stamped with this pass's ages, which is what keeps it inside the 30s
    # Kalshi limit while the market has not moved. See
    # `engine.confirm_recommendation`.
    unchanged_confirmed: int = 0
    dropped_no_books: int = 0
    dropped_no_kalshi_quote: int = 0
    dropped_unresolved_outcome: int = 0
    dropped_game_started: int = 0
    # How many rows the Skeptic was asked about, and how many it refused. Both
    # are structurally zero while `surfaced` is zero, which is the whole history
    # of this project so far -- reported anyway, because the day they are not is
    # the day the agent fleet starts costing money and blocking bets, and that
    # should be visible in the pass log rather than inferred from a Discord
    # digest.
    skeptic_reviewed: int = 0
    skeptic_blocked: int = 0
    # Surfaced rows the fleet was NOT asked about, because the per-pass or
    # per-day Anthropic ceiling refused the call (`agents/budget.py`). These are
    # suppressed rather than surfaced, so this is a count of bets the tool
    # declined for a cost reason rather than a market one -- the one number that
    # says a ceiling is set too low, and the only place it is visible.
    skeptic_unreviewed: int = 0
    # Why the pass did or did not spend an odds credit, in words. A pass that
    # skips the sweep silently looks exactly like one that swept and found
    # nothing, and those two need opposite responses.
    sweep_decision: str = ""
    # Where the pass's wall clock went, in milliseconds, one field per leg.
    #
    # **This exists because `took_s` alone sent two sessions after the wrong
    # leg.** A quote pass melting the box was diagnosed first as the inserts
    # and then as the parse -- both refuted by measurement -- before the HTTP
    # walk was found (ADR 0053). Narrowing the walk then took it from ~15s to
    # 2.3s and the pass still took 23.6s, because a single total cannot say
    # which of four legs moved. Every one of those diagnoses cost a session and
    # each was settled in minutes once the leg was timed, so the timing is now
    # part of what a pass reports rather than something a future session
    # reconstructs over SSH.
    #
    # Reported even when zero, for the reason `ALWAYS_REPORT` already gives
    # about the skeptic fields: a *missing* key cannot be told from a leg that
    # ran instantly, and those need opposite responses -- one means the leg was
    # never timed, the other that it is not the problem.
    leg_walk_ms: int = 0
    leg_parse_ms: int = 0
    leg_store_ms: int = 0
    leg_price_ms: int = 0
    # `leg_price_ms` split, because on 2026-08-19 it became the whole quote
    # pass -- 12-20s of a 17-32s pass on a 15s cadence -- and a single total
    # cannot say which of four phases moved. Exactly the reason the outer legs
    # exist, one level down. The four sum to `leg_price_ms` up to rounding.
    #
    # `setup` is the three per-pass reads (strategy config, exposure, daily
    # P&L); `link` is `link_discovered_events`; `judge` is the devig loop;
    # `persist` is review-and-write. **`persist` includes the Anthropic round
    # trip**, so a slow fleet lands there and not on `judge` -- keeping the
    # arithmetic separable from the network, which is the whole point of
    # splitting it.
    leg_price_setup_ms: int = 0
    leg_price_link_ms: int = 0
    leg_price_judge_ms: int = 0
    leg_price_persist_ms: int = 0
    # Rows retention removed this pass. Reported even at zero, because a
    # prune that has stopped finding anything and a prune that has stopped
    # running produce the same silence, and the tables that had no bound at
    # all until 2026-08-19 are the ones where that distinction matters.
    quotes_pruned: int = 0
    unmatched_pruned: int = 0
    errors: list[str] = field(default_factory=list)

    # Always printed even when zero. "surfaced: 0" is the headline result of a
    # pass -- it is the answer this whole tool exists to produce, and hiding it
    # because it is falsy would make "found nothing" look like "did not check".
    #
    # The two skeptic fields are here for the reason their own comment above
    # gives, which the filter used to defeat: they were declared "reported
    # anyway" and then dropped by `if v` in exactly the state -- zero -- that the
    # comment was written about. Measured on live 2026-08-08: the pass line
    # carried neither key, so "the fleet has never run" could only be *inferred*
    # from `surfaced: 0` rather than read. The distinguishing case is the one
    # that matters for money: `skeptic_reviewed: 2` with `skeptic_blocked`
    # missing cannot be told from a fleet that reviewed two rows and blocked
    # nothing, and blocking is the half that stops a bet.
    ALWAYS_REPORT = (
        "recommendations",
        "surfaced",
        "suppressed",
        "skeptic_reviewed",
        "skeptic_blocked",
        "skeptic_unreviewed",
        "sweep_decision",
        "leg_walk_ms",
        "leg_parse_ms",
        "leg_store_ms",
        "leg_price_ms",
        "leg_price_setup_ms",
        "leg_price_link_ms",
        "leg_price_judge_ms",
        "leg_price_persist_ms",
        "quotes_pruned",
        "unmatched_pruned",
    )

    def as_dict(self) -> dict[str, Any]:
        return {
            k: v
            for k, v in self.__dict__.items()
            if v or k in self.ALWAYS_REPORT
        }


# ---------------------------------------------------------------------------
# The missing read path
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BookConsensusInput:
    """Stored odds, reshaped into what `consensus_devig` takes."""

    outcomes: tuple[str, ...]
    quotes_by_book: dict[str, list[float]]
    oldest_book_age_ms: int
    books_dropped: tuple[str, ...]
    # Books that reported no `last_update`, so their age is measured from our
    # fetch and is therefore a lower bound. Reported rather than absorbed: an
    # unknown-age quote presenting as seconds old is the direction that
    # manufactures edge, on the field freshness suppression reads.
    books_with_estimated_age: tuple[str, ...] = ()
    # The fixture's kickoff as **the sportsbook** gives it. Kalshi's runs three
    # hours late, so its own commence time cannot answer "has this started?" --
    # it says no for the first three innings.
    commence_ms: Optional[int] = None


def book_quotes_for_event(
    conn, odds_event_id: str, *, now: int, market: str = MONEYLINE
) -> Optional[BookConsensusInput]:
    """Latest stored odds for one fixture, grouped by book.

    Reads **one sweep**, not the union of all of them. `MAX(fetched_ms)` scopes
    the read to a single consistent snapshot; mixing sweeps would pair a
    two-minute-old Pinnacle price with an hour-old DraftKings one and call the
    disagreement `market_width`, which is a suppression input. A stale book must
    look stale, not wide.

    Books that do not quote every outcome are dropped and named. `consensus_devig`
    would raise on a short price list, and one book missing a leg is a normal
    operating state rather than a failure of the fixture.

    Returns `None` when there is nothing stored -- the caller counts that as a
    drop rather than substituting an empty consensus.
    """
    latest = conn.execute(
        "SELECT MAX(fetched_ms) AS m FROM odds_snapshots "
        "WHERE odds_event_id = ? AND market = ?",
        (odds_event_id, market),
    ).fetchone()
    if latest is None or latest["m"] is None:
        return None

    rows = conn.execute(
        "SELECT bookmaker, outcome_name, price_decimal, book_updated_ms, "
        "fetched_ms, commence_ms FROM odds_snapshots "
        "WHERE odds_event_id = ? AND market = ? AND fetched_ms = ?",
        (odds_event_id, market, latest["m"]),
    ).fetchall()
    if not rows:
        return None

    # Outcome order is fixed once, from first appearance, and every book is
    # indexed against it. `consensus_devig` pairs prices to outcomes positionally,
    # so an inconsistent order silently swaps the two teams' probabilities --
    # a mistake that produces entirely plausible numbers.
    outcomes: list[str] = []
    for row in rows:
        if row["outcome_name"] not in outcomes:
            outcomes.append(row["outcome_name"])

    by_book: dict[str, dict[str, float]] = {}
    ages: dict[str, int] = {}
    estimated: set[str] = set()
    for row in rows:
        book = row["bookmaker"]
        by_book.setdefault(book, {})[row["outcome_name"]] = float(row["price_decimal"])
        # Staleness is measured from the BOOK's own update, not our fetch. The
        # fallback to `fetched_ms` is optimistic, so a missing `last_update` is
        # a reason for suspicion rather than a clean bill of health.
        if row["book_updated_ms"] is None:
            estimated.add(book)
        basis = (
            row["book_updated_ms"]
            if row["book_updated_ms"] is not None
            else row["fetched_ms"]
        )
        age = now - int(basis)
        # Deliberately NOT floored at zero. A book stamped in the future would
        # clamp to "0ms old" and sail through every freshness check looking
        # maximally fresh -- the flattering direction, and indistinguishable
        # from a genuinely current price. Kept signed so the caller can see it.
        ages[book] = max(ages[book], age) if book in ages else age

    quotes_by_book: dict[str, list[float]] = {}
    dropped: list[str] = []
    for book, priced in by_book.items():
        if all(o in priced for o in outcomes):
            quotes_by_book[book] = [priced[o] for o in outcomes]
        else:
            dropped.append(book)

    if not quotes_by_book:
        return None

    # The OLDEST contributing book, not the average. The consensus is only as
    # fresh as the stalest price inside it.
    oldest = max(ages[b] for b in quotes_by_book)

    ahead = sorted(b for b in quotes_by_book if ages[b] < -CLOCK_SKEW_TOLERANCE_MS)
    if ahead:
        # Not clamped away. Beyond a second or two this is not NTP jitter, it
        # means the timestamps cannot be trusted at all -- and every freshness
        # decision downstream is made from them.
        logger.warning(
            "%s: %d book(s) stamped in the future by more than %dms (%s). "
            "Freshness for this fixture is unreliable.",
            odds_event_id, len(ahead), CLOCK_SKEW_TOLERANCE_MS, ", ".join(ahead),
        )

    return BookConsensusInput(
        outcomes=tuple(outcomes),
        quotes_by_book=quotes_by_book,
        oldest_book_age_ms=oldest,
        books_dropped=tuple(sorted(dropped)),
        books_with_estimated_age=tuple(sorted(estimated & set(quotes_by_book))),
        commence_ms=int(rows[0]["commence_ms"]),
    )


@dataclass(frozen=True)
class PropLine:
    """One rung of one player's ladder, ready to devig.

    `point` is the sportsbook's own line and is what joins to a Kalshi market:
    Kalshi publishes `floor_strike` as the same number for the same rung, so no
    conversion sits between the two. `player` is stored as the book spells it;
    `player_key` is `props.norm()`ed and is what the join compares.
    """

    base_market: str
    player: str
    player_key: str
    point: float
    books: BookConsensusInput


# The two sides of every prop.
#
# `consensus_devig` pairs prices to outcomes **positionally**, and this constant
# is what makes that safe: the outcome tuple handed to the devig and the price
# list built for each book are both generated by iterating it, so they cannot
# disagree. Reversing it is therefore a no-op, and that was *measured* rather
# than assumed -- a mutation reversing it leaves the whole suite green, which is
# recorded here instead of being papered over with a test that pretends
# otherwise.
#
# What is genuinely unsafe is building the two lists from different orders. That
# is what `TestTheDevigKeepsOverAndUnderTheRightWayRound` pins, and it fails
# loudly.
#
# Fixed as a constant rather than read from whichever outcome the API returned
# first, which is what the team path has to do -- see `book_quotes_for_event`,
# where the order is pinned by first appearance because the outcomes are team
# names nobody can enumerate in advance.
PROP_SIDES = ("Over", "Under")


def prop_quotes_for_event(
    conn, odds_event_id: str, *, now: int
) -> list[PropLine]:
    """Stored prop odds for one fixture, one entry per (player, point).

    **Why this cannot be `book_quotes_for_event` with a different `market`.**
    That function groups every row of one market key into a single outcome list.
    On `h2h` those rows are the two teams and that is exactly right. On
    `pitcher_strikeouts` they are every rung of every pitcher in the game, so
    the same call would build one "consensus" over a hundred unrelated prices
    and devig it. The grouping key, not the filter, is what differs.

    Primary and `_alternate` feeds are folded onto one base market. They quote
    the same quantity at different lines; kept apart, a player would appear
    twice with two consensuses built from disjoint book sets, and each would
    look like independent confirmation of the other.

    A book quoting only one side is dropped, and that is the dominant loss:
    measured at 174 of 222 matched keys on 2026-08-14, because the alternate
    feeds are mostly Over-only. Recovering them means estimating a book's
    overround from its own two-sided primary line, which is an assumption and
    needs registering as one -- so it is not done here, and the drop is
    counted rather than quietly absorbed.

    Reads **one sweep** via `MAX(fetched_ms)`, for the reason the team path
    does: mixing sweeps would pair a fresh price with an hour-old one and call
    the disagreement `market_width`, which is a suppression input.
    """
    latest = conn.execute(
        "SELECT MAX(fetched_ms) AS m FROM odds_snapshots "
        "WHERE odds_event_id = ? AND market IN "
        "(SELECT value FROM json_each(?))",
        (odds_event_id, json.dumps(sorted(PROP_MARKETS))),
    ).fetchone()
    if latest is None or latest["m"] is None:
        return []

    rows = conn.execute(
        "SELECT bookmaker, market, outcome_name, outcome_description, "
        "outcome_point, price_decimal, book_updated_ms, fetched_ms, commence_ms "
        "FROM odds_snapshots WHERE odds_event_id = ? AND fetched_ms = ? "
        "AND market IN (SELECT value FROM json_each(?))",
        (odds_event_id, latest["m"], json.dumps(sorted(PROP_MARKETS))),
    ).fetchall()
    if not rows:
        return []

    # (base_market, player_key, point) -> the pieces of one ladder rung.
    grouped: dict[tuple[str, str, float], dict] = {}
    for row in rows:
        player = row["outcome_description"]
        point = row["outcome_point"]
        side = row["outcome_name"]
        if not player or point is None or side not in PROP_SIDES:
            # Unreadable resolves to nothing. A prop row missing its player or
            # its line is not a prop we can join; substituting either would
            # attach a price to a market it does not describe.
            continue

        key = (base_market(row["market"]), norm(player), float(point))
        entry = grouped.setdefault(
            key,
            {
                "player": player,
                "by_book": {},
                "ages": {},
                "estimated": set(),
                "commence_ms": int(row["commence_ms"]),
            },
        )
        entry["by_book"].setdefault(row["bookmaker"], {})[side] = float(
            row["price_decimal"]
        )

        # Staleness from the BOOK's own update, never our fetch. The fallback is
        # optimistic, so a missing `last_update` is a reason for suspicion
        # rather than a clean bill of health -- and it is deliberately not
        # floored at zero, so a book stamped in the future stays visible instead
        # of clamping to maximally fresh.
        if row["book_updated_ms"] is None:
            entry["estimated"].add(row["bookmaker"])
        basis = (
            row["book_updated_ms"]
            if row["book_updated_ms"] is not None
            else row["fetched_ms"]
        )
        age = now - int(basis)
        previous = entry["ages"].get(row["bookmaker"])
        entry["ages"][row["bookmaker"]] = (
            age if previous is None else max(previous, age)
        )

    lines: list[PropLine] = []
    for (market_key, player_key, point), entry in sorted(grouped.items()):
        quotes_by_book: dict[str, list[float]] = {}
        dropped: list[str] = []
        for book, priced in entry["by_book"].items():
            if all(side in priced for side in PROP_SIDES):
                quotes_by_book[book] = [priced[side] for side in PROP_SIDES]
            else:
                dropped.append(book)
        if not quotes_by_book:
            continue

        lines.append(
            PropLine(
                base_market=market_key,
                player=entry["player"],
                player_key=player_key,
                point=point,
                books=BookConsensusInput(
                    outcomes=PROP_SIDES,
                    quotes_by_book=quotes_by_book,
                    # The OLDEST contributing book. A consensus is only as
                    # fresh as the stalest price inside it.
                    oldest_book_age_ms=max(
                        entry["ages"][b] for b in quotes_by_book
                    ),
                    books_dropped=tuple(sorted(dropped)),
                    books_with_estimated_age=tuple(
                        sorted(entry["estimated"] & set(quotes_by_book))
                    ),
                    commence_ms=entry["commence_ms"],
                ),
            )
        )
    return lines


def write_fair_price(
    conn,
    *,
    link_id: int,
    devig_result,
    metadata: dict,
    computed_ms: int,
    market: str = MONEYLINE,
    outcome_description: Optional[str] = None,
    outcome_point: Optional[float] = None,
) -> dict[str, int]:
    """Persist one `fair_prices` row per outcome. Returns outcome -> row id.

    One row per outcome rather than one per market, because the conservative
    probability is *per side*: it is the lowest across methods for the side
    being bought, and the lowest for one team is not one minus the lowest for
    the other.

    `outcome_description` and `outcome_point` are what make a prop row
    identifiable. On a team market both stay `None`: `outcome_name` alone names
    the side. On a prop, `outcome_name` is only `"Over"` or `"Under"`, so
    without the player and the line every rung of every ladder in a game would
    write two indistinguishable rows -- and the `{outcome: id}` mapping this
    returns would collapse the whole event to the last one written.
    """
    ids: dict[str, int] = {}
    methods = devig_result.all_methods()

    # **Never default an unreadable count to 0.** `book_count` used to be written
    # as `metadata.get("book_count", 0)`. No live path could reach that default --
    # `consensus_devig` always sets the key -- and `0` happened to be the safe
    # direction, because it trips `too_few_books`. Both of those are why it
    # survived, and neither is a reason to keep it: the column is NOT NULL and
    # feeds a suppression threshold, so a silently substituted zero would be a
    # measurement claim rather than an absence. See ADR 0019 and the standing
    # rule in `tasks/lessons.md`.
    if "book_count" not in metadata:
        raise KeyError(
            "consensus metadata has no 'book_count'; refusing to substitute 0 "
            "for a count that decides the too_few_books suppression"
        )
    book_count = metadata["book_count"]

    for index, outcome in enumerate(devig_result.outcomes):
        cursor = conn.execute(
            "INSERT INTO fair_prices (computed_ms, link_id, market, outcome_name, "
            "outcome_description, outcome_point, p_multiplicative, p_additive, "
            "p_power, p_shin, p_conservative, overround, market_width, "
            "book_count, books_used, anchored_on_sharp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                computed_ms, link_id, market, outcome,
                outcome_description, outcome_point,
                methods["multiplicative"][index], methods["additive"][index],
                methods["power"][index], methods["shin"][index],
                devig_result.conservative_probability(outcome),
                devig_result.overround, metadata.get("market_width"),
                book_count,
                json.dumps(metadata.get("books_used", [])),
                1 if metadata.get("anchored_on_sharp") else 0,
            ),
        )
        ids[outcome] = int(cursor.lastrowid)
    conn.commit()
    return ids


def latest_kalshi_quote(conn, ticker: str):
    """The most recent stored quote for a market, or `None`."""
    return conn.execute(
        "SELECT * FROM kalshi_quotes WHERE ticker = ? "
        "ORDER BY observed_ms DESC LIMIT 1",
        (ticker,),
    ).fetchone()


# ---------------------------------------------------------------------------
# Pricing pass -- no network
# ---------------------------------------------------------------------------


def _match_candidates(conn, sport_key: str, *, since_ms: int) -> list[MatchCandidate]:
    """Distinct sportsbook fixtures seen for a sport, as link candidates."""
    rows = conn.execute(
        "SELECT DISTINCT odds_event_id, commence_ms, home_team, away_team "
        "FROM odds_snapshots WHERE sport_key = ? AND commence_ms >= ?",
        (sport_key, since_ms),
    ).fetchall()
    return [
        MatchCandidate(
            odds_event_id=r["odds_event_id"],
            commence_ms=int(r["commence_ms"]),
            home_team=r["home_team"],
            away_team=r["away_team"],
        )
        for r in rows
    ]


def _linked_fixtures(conn, *, since_ms: int) -> list[LinkedFixture]:
    """Links a prop event may inherit: one per already-matched game event.

    Read from `event_links` rather than from this pass's results, so a prop
    still resolves on a pass where its game event was linked earlier and had
    nothing new to say. The link is `INSERT OR IGNORE`d, so re-reading it costs
    nothing and misses nothing.

    **Only `exact_alias_pair` rows are offered.** A prop inheriting from another
    prop would be a link with no team-name evidence anywhere underneath it --
    correct today by luck, and self-confirming the moment a wrong prop link is
    written. Every inherited link must trace back to one that passed the
    bijection.

    `commence_skew_ms` is `odds - kalshi` at the moment the game was linked, so
    adding it back to the game's own commence recovers the sportsbook's start
    time without re-reading `odds_snapshots`.
    """
    rows = conn.execute(
        "SELECT el.kalshi_event_ticker AS ticker, el.odds_event_id AS odds_id, "
        "ke.commence_ms + el.commence_skew_ms AS odds_commence_ms "
        "FROM event_links el "
        "JOIN kalshi_events ke ON ke.event_ticker = el.kalshi_event_ticker "
        "WHERE el.method = ? AND ke.commence_ms >= ?",
        (EXACT_ALIAS_PAIR, since_ms),
    ).fetchall()

    fixtures: list[LinkedFixture] = []
    for row in rows:
        fixture = fixture_segment(row["ticker"])
        if fixture is None or row["odds_commence_ms"] is None:
            # Unreadable resolves to nothing, never to a default. A link whose
            # ticker or commence cannot be read is one a prop must not inherit.
            continue
        fixtures.append(
            LinkedFixture(
                fixture=fixture,
                odds_event_id=row["odds_id"],
                odds_commence_ms=int(row["odds_commence_ms"]),
            )
        )
    return fixtures


# The threshold a `link slow` line is emitted above. 8s because the fast state
# measured 2.0-2.4s across 29 consecutive live passes and the slow state 12.7s
# and up, so this sits in the empty gap between two well-separated clusters
# rather than at a round number. A pass at 8s would be news either way.
LINK_SLOW_REPORT_MS = 8_000


def link_discovered_events(
    conn,
    events: Sequence[DiscoveredEvent],
    *,
    now: int,
    alias_cache: Optional[dict[str, TeamAliases]] = None,
) -> dict[str, tuple[int, Optional[int]]]:
    """Link each discovered event to a sportsbook fixture.

    Returns `event_ticker -> (link_id, commence_skew_ms)` for the ones that
    resolved. Everything else goes to `unmatched_events` with a reason, because
    a matcher that silently drops what it cannot resolve looks identical to one
    with nothing to do.
    """
    cache = alias_cache if alias_cache is not None else {}
    linked: dict[str, tuple[int, Optional[int]]] = {}
    # Timed inside the function, and reported only when it is slow.
    #
    # `leg_price_link_ms` was measured on live 2026-08-19 swinging **2.1s ->
    # 20.7s between adjacent passes on identical input** -- 531 discovered, 81
    # linked, in both states -- while every other leg stayed flat. One total
    # cannot say which of this function's three costs moved, which is the same
    # argument that produced the outer legs and then the pricing split. Two
    # levels of that argument have already paid for themselves on this one
    # incident.
    #
    # **Conditional, unlike the legs above, and deliberately so.** This runs on
    # the 15s cadence and the legs are on every pass because a *zero* is
    # informative there. Here the informative case is the outlier: a line per
    # pass would be ~5,700 a day against the 100-line `flyctl logs` buffer that
    # the pass line itself is rationed for. Below the threshold the fast state
    # is already fully described by `leg_price_link_ms`.
    # **Per pass, keyed by sport, exactly as `alias_cache` beside it already
    # is.** `_match_candidates` was called once per *event* -- 456 times on the
    # live slate -- with arguments that vary only by `sport_key`, because
    # `since_ms` is derived from the pass's single `now`. Every call after the
    # first for a sport re-ran an identical `SELECT DISTINCT` over
    # `odds_snapshots`, a table that grows by ~900 rows per odds sweep.
    #
    # Measured on live 2026-08-19 before this cache, on a slow pass:
    #
    #     link slow: 11057ms total; candidates 10779ms over 456 calls,
    #     unmatched writes 117ms, link writes 1ms, other 159ms
    #
    # **97.5% of the leg, in one repeated query.** The growing table is also
    # why the cost drifts: the same 456 calls cost ~2s when `odds_snapshots`
    # is small and ~11-20s once a window has been sweeping into it.
    #
    # One snapshot per pass is also *more* correct than re-reading, not less:
    # every event on a slate now links against the same candidate set, where
    # before an event late in the loop could see fixtures an earlier one could
    # not.
    candidate_cache: dict[str, list[MatchCandidate]] = {}
    link_started = time.perf_counter()
    candidates_ms = 0.0
    unmatched_ms = 0.0
    record_ms = 0.0
    candidate_calls = 0

    # **Games first, then props, and the order is load-bearing.** A prop event
    # inherits the link its own game earned, so a single-pass loop would resolve
    # a prop against whatever happened to be linked before it in the list and
    # silently refuse the rest. Sorting by market type makes the dependency a
    # property of the code rather than of the order Kalshi returned events in.
    games = [e for e in events if e.market_type != MARKET_TYPE_PROP]
    props = [e for e in events if e.market_type == MARKET_TYPE_PROP]

    for event in games:
        if event.sport_key not in cache:
            cache[event.sport_key] = load_aliases(event.sport_key)
        aliases = cache[event.sport_key]

        if event.sport_key not in candidate_cache:
            _t = time.perf_counter()
            candidate_cache[event.sport_key] = _match_candidates(
                conn, event.sport_key, since_ms=now - 86_400_000
            )
            candidates_ms += (time.perf_counter() - _t) * 1000
            candidate_calls += 1
        candidates = candidate_cache[event.sport_key]

        result = link_event(
            kalshi_event_ticker=event.event_ticker,
            kalshi_teams=event.teams,
            kalshi_commence_ms=event.commence_ms,
            candidates=candidates,
            aliases=aliases,
        )
        if result.matched:
            _t = time.perf_counter()
            link_id = record_link(conn, result, event.league, now)
            record_ms += (time.perf_counter() - _t) * 1000
            linked[event.event_ticker] = (link_id, result.commence_skew_ms)
        else:
            _t = time.perf_counter()
            record_unmatched(
                conn,
                observed_ms=now,
                side="kalshi",
                identifier=event.event_ticker,
                league=event.league,
                # The team names as seen, because this queue exists to be
                # turned into alias-file entries by hand.
                detail=" vs ".join(event.teams) or event.title,
                reason=result.reason or "no_counterpart",
            )
            unmatched_ms += (time.perf_counter() - _t) * 1000

    if props:
        fixtures = _linked_fixtures(conn, since_ms=now - 86_400_000)
        for event in props:
            result = link_prop_event(
                kalshi_event_ticker=event.event_ticker,
                kalshi_commence_ms=event.commence_ms,
                linked_fixtures=fixtures,
            )
            if result.matched:
                link_id = record_link(conn, result, event.league, now)
                linked[event.event_ticker] = (link_id, result.commence_skew_ms)
            else:
                record_unmatched(
                    conn,
                    observed_ms=now,
                    side="kalshi",
                    identifier=event.event_ticker,
                    league=event.league,
                    # The event's title, not `teams` -- a prop's sides are
                    # player-rung strings, and " vs "-joining twelve of them
                    # produces a line nobody can read and no alias can fix.
                    detail=event.title,
                    reason=result.reason or "no_counterpart",
                )

    total_ms = (time.perf_counter() - link_started) * 1000
    if total_ms >= LINK_SLOW_REPORT_MS:
        logger.warning(
            "link slow: %dms total; candidates %dms over %d calls, "
            "unmatched writes %dms, link writes %dms, other %dms "
            "(%d discovered, %d linked)",
            int(total_ms), int(candidates_ms), candidate_calls,
            int(unmatched_ms), int(record_ms),
            int(total_ms - candidates_ms - unmatched_ms - record_ms),
            len(events), len(linked),
        )
    return linked


def _price_prop_event(
    conn,
    event: DiscoveredEvent,
    *,
    link_id: int,
    odds_event_id: str,
    skew_ms: Optional[int],
    stamp: int,
    counts: PassCounts,
    pending: list,
    risk,
    suppression,
    version: int,
    exposure: float,
    daily_pnl: float,
) -> None:
    """Price one prop event: one devig per (player, line), not one per event.

    **The join, and why it carries no arithmetic.** Kalshi's `N+` market is the
    books' `Over N-0.5`, and both sources publish that same `N-0.5` themselves --
    Kalshi as `floor_strike` (stored in `kalshi_markets.strike`), the books as
    `point`. So a Kalshi market meets its consensus on
    `(base market, normalised player, point)` and nothing is converted on either
    side. Keying on the player rather than the team is what removes the
    abbreviation-mapping problem entirely instead of solving it.

    **Kalshi YES is Over.** Buying YES on "Anthony Kay: 2+" is buying two or
    more, which is exactly the book's `Over 1.5`; NO is Under. That mapping is
    the whole reason a prop can use the two-sided machinery at all, and it is
    stated here because getting it backwards would produce entirely plausible
    probabilities for the opposite side.

    **What this does not claim.** A gap against a consensus is a gap, not an
    edge; only CLV against Kalshi's own close can say which side was right, and
    that is what recording these rows is for.

    **CORRECTED 2026-08-16 — this docstring used to say "eight books quote MLB
    props and none of them is Pinnacle or Betfair, so `anchored_on_sharp` is 0
    on every row here by construction". That is false on the deployed system.**
    `prop-bookmakers` on the live database returns **ten** books including
    **`pinnacle`** -- 406 prop quotes, 7 events, 3 market keys on one sweep --
    and `pinnacle` is in `SHARP_BOOKS`.

    The original claim came from `scripts/probe_prop_dispersion.py`, which
    requests **`"regions": "us"`** (line 149). Pinnacle is served by The Odds
    API under **`eu` only**. So "no sharp book quotes props" was a true
    statement about a us-only pull that was generalised into a claim about a
    deployed system running `ODDS_REGIONS=us,eu`. The probe never asked the
    question its finding was quoted as answering.

    **What is still open, and it is not a hedge.** `consensus_devig` anchors on
    a sharp book only where that book is in `quotes_by_book` for the rung, and
    `prop_quotes_for_event` admits a book only when it quotes **both** sides.
    Nothing yet establishes that Pinnacle is two-sided on any prop rung, so
    `anchored_on_sharp` may still be 0 in practice. The `prop-rungs` query
    answers it. **Do not write either "props are anchored" or "props are
    unanchored" until it has been run.**

    **The operational consequence is settled regardless.** Dropping `eu` from
    the prop call to halve its cost -- the saving `tasks/NEXT.md` was chasing
    -- would delete the only sharp book on the prop record. It is refused.
    """
    market_key = PROP_SERIES.get(event.series_ticker)
    if market_key is None:
        # Discovery admitted a prop series this module has no book market for.
        # A finding, not a crash, and not a silent skip.
        counts.errors.append(
            f"{event.event_ticker}: series {event.series_ticker} is a prop "
            f"but maps to no Odds API market key"
        )
        return

    lines = {
        (line.base_market, line.player_key, line.point): line
        for line in prop_quotes_for_event(conn, odds_event_id, now=stamp)
    }
    if not lines:
        counts.dropped_no_books += 1
        return

    # Devigged at most once per rung even when several Kalshi markets land on
    # one, so two rows can never carry two different "fair" numbers for one
    # consensus.
    devigged: dict[tuple, Optional[tuple]] = {}

    for market in event.markets:
        if market.market_type != MARKET_TYPE_PROP:
            continue
        if not market.player_name or market.strike is None:
            # An unparsed subtitle or a missing `floor_strike`. Counted, never
            # matched on a substituted value.
            counts.dropped_unresolved_outcome += 1
            continue

        key = (market_key, norm(market.player_name), float(market.strike))
        line = lines.get(key)
        if line is None:
            # The books quote no two-sided price at this rung. The dominant
            # case, and the reason is recorded in `prop_quotes_for_event`:
            # alternate feeds are mostly Over-only.
            counts.dropped_unresolved_outcome += 1
            continue

        books = line.books
        # The sportsbook's kickoff, never Kalshi's. Same rule as the team path:
        # a stored pre-game consensus against a Kalshi price that has absorbed
        # two innings is two different questions subtracted from each other, and
        # the row could never be scored against a close read before first pitch.
        if books.commence_ms is not None and books.commence_ms <= stamp:
            counts.dropped_game_started += 1
            continue

        if key not in devigged:
            # `None` records a rung that could not be devigged, so a second
            # Kalshi market on the same rung skips it rather than retrying and
            # appending the same error twice.
            try:
                result, metadata = consensus_devig(
                    books.outcomes, books.quotes_by_book, sharp_books=SHARP_BOOKS
                )
            except DevigError as exc:
                # A book set that cannot be devigged is a finding, not a crash.
                counts.errors.append(f"{market.ticker}: {exc}")
                devigged[key] = None
            else:
                fair_ids = write_fair_price(
                    conn,
                    link_id=link_id,
                    devig_result=result,
                    metadata=metadata,
                    computed_ms=stamp,
                    market=line.base_market,
                    outcome_description=line.player,
                    outcome_point=line.point,
                )
                counts.fair_prices_written += len(fair_ids)
                devigged[key] = (result, metadata, fair_ids)

        entry = devigged[key]
        if entry is None:
            continue
        devig_result, metadata, fair_ids = entry

        quote = latest_kalshi_quote(conn, market.ticker)
        if quote is None:
            counts.dropped_no_kalshi_quote += 1
            continue

        for side in ("yes", "no"):
            side_outcome = "Over" if side == "yes" else "Under"

            ask = ask_for_side(quote, side)
            # **`is_valid_price`, not just `is not None`, and a prop ladder is
            # why.** 0 and 1000 tenths are settled outcomes rather than quotes,
            # and `core/ev.effective_price` refuses them: an ask of 0 yields a
            # zero fee and an effective price of $0.00, which reports a
            # breakeven win rate of 0% and a fabricated edge.
            #
            # The team path checks only for `None` and has never tripped this,
            # because a game moneyline does not reach 0 or 1000 while it is
            # still pre-game and open. **A prop ladder reaches both routinely.**
            # Kalshi prices every rung from `2+` to `9+`, so the far end of a
            # ladder is a market nobody will trade: the NO bid sits at 1000 and
            # the derived YES ask is therefore 0.
            #
            # Measured, not predicted: this raised `ValueError` on the first
            # live pass that priced props (19:41:53Z, 2026-08-15), which aborted
            # the **whole** pricing pass -- moneyline rows included -- and would
            # have repeated every full pass, because a failed full pass is
            # retried rather than counted as done.
            if not is_valid_price(ask):
                counts.dropped_no_kalshi_quote += 1
                continue

            # Depth at the ask is the OPPOSING bid's size: a yes ask is derived
            # from the no bid, so that is the resting size you would lift.
            depth = quote["no_bid_qty"] if side == "yes" else quote["yes_bid_qty"]

            recommendation = build_recommendation(
                Candidate(
                    ticker=market.ticker,
                    side=side,
                    outcome_name=side_outcome,
                    ask_tenths=ask,
                    depth_at_ask=depth,
                    kalshi_quote_age_ms=stamp - int(quote["observed_ms"]),
                    link_id=link_id,
                    fair_price_id=fair_ids.get(side_outcome),
                    devig=devig_result,
                    book_count=metadata["book_count"],
                    market_width=metadata["market_width"],
                    odds_age_ms=books.oldest_book_age_ms,
                    commence_skew_ms=skew_ms,
                ),
                risk=risk,
                suppression=suppression,
                strategy_config_version=version,
                current_exposure_dollars=exposure,
                current_position_dollars=open_position_dollars(
                    conn, market.ticker, dry_run=ORDERS_ARE_DRY_RUNS
                ),
                daily_pnl_dollars=daily_pnl,
                created_ms=stamp,
            )
            pending.append(
                ReviewCandidate(
                    recommendation=recommendation,
                    prompt_kwargs=(
                        _skeptic_context(
                            market=market,
                            event=event,
                            outcome=side_outcome,
                            recommendation=recommendation,
                            devig_result=devig_result,
                            metadata=metadata,
                            books=books,
                        )
                        if recommendation.surfaced
                        else {}
                    ),
                )
            )


def _skeptic_context(
    *,
    market,
    event,
    outcome: str,
    recommendation,
    devig_result,
    metadata: dict,
    books: BookConsensusInput,
) -> dict[str, Any]:
    """The Skeptic's prompt inputs for one judged row.

    Read off the **recommendation** rather than recomputed from the candidate
    wherever both could answer: the agent must attack the row that would be
    sold, not a second derivation of it that could differ by a rounding step.
    """
    index = devig_result.index_of(outcome)
    return {
        "ticker": market.ticker,
        "market_title": market.title,
        "outcome_name": outcome,
        "event_title": event.title,
        "kalshi_ask_cents": recommendation.entry_ask_tenths / 10,
        "consensus_fair_cents": recommendation.fair_probability * 100,
        "edge_cents": recommendation.edge_tenths / 10,
        "quote_age_s": recommendation.kalshi_quote_age_ms / 1000,
        "odds_age_s": recommendation.odds_age_ms / 1000,
        "book_count": metadata["book_count"],
        "market_width_points": metadata["market_width"],
        "depth_at_ask": recommendation.depth_at_ask,
        "devig_methods": {
            name: values[index] for name, values in devig_result.all_methods().items()
        },
        # The SPORTSBOOK's kickoff. Kalshi's runs three hours late, and handing
        # an agent a start time three hours after the real one invites it to
        # reason about a game it thinks has not begun.
        "commence_iso": (
            None
            if books.commence_ms is None
            else datetime.fromtimestamp(
                books.commence_ms / 1000, tz=timezone.utc
            ).isoformat()
        ),
        "matched_sportsbook_teams": list(books.outcomes),
    }


def run_pricing_pass(
    conn,
    events: Sequence[DiscoveredEvent],
    *,
    risk: Optional[RiskConfig] = None,
    suppression: Optional[SuppressionConfig] = None,
    now: Optional[int] = None,
    counts: Optional[PassCounts] = None,
    review=review_surfaced,
    day_start_hour: int = DEFAULT_DAY_START_UTC_HOUR,
) -> PassCounts:
    """Devig what is stored and write recommendations. Touches no network.

    Both sides of every moneyline are judged, not just the one that looks cheap.
    A candidate with no edge is the normal answer and is still recorded: it is a
    scored observation on the closing line, which is what makes 300 of them
    reachable without placing 300 bets.

    **Judging and persisting are two phases, and the gap between them is the
    point.** The pass used to build a row and write it in the same breath. The
    Skeptic folds its verdict into `suppressed_reason`, so a row already on disk
    is orderable for the duration of one Anthropic round trip -- the endpoint
    reads the database, not this function's local variables. So every row is
    collected first, the surfaced ones are reviewed as one batch, verdicts are
    applied, and only then does anything reach the database.

    Persisting in a second loop is safe for the dedupe in `persist_if_changed`,
    which compares against the most recent stored row for a `(ticker, side)`:
    each pair is judged exactly once per pass, so no entry in the batch can be
    the thing another entry would have compared against.

    `day_start_hour` is the roll hour of the **risk** day -- the window
    `max_daily_loss_dollars` measures realised losses over. It is threaded in
    rather than defaulted because `api/routes.py:1546` passes the configured
    `OddsConfig.budget_day_start_utc_hour` and this pass did not, so the
    kill-switch day the runner sized every card against and the one the order
    endpoint admits it against came from two different sources in two different
    processes. `config.assert_risk_day_start_agrees` is what refuses to start
    when the default left in this signature has stopped matching the deployed
    value; see it for which way each divergence fails.

    `review` is a parameter and not just an import because it is the one leg of
    this function that leaves the process. Everything else here is arithmetic
    over a local database; this reaches Anthropic and is billed. A test that
    surfaces a row and forgets to substitute it would spend money on whichever
    machines happen to hold the key -- so the seam is in the signature, where it
    is visible, rather than resolved from module scope where it is not.
    """
    priced_started = time.perf_counter()
    stamp = now if now is not None else now_ms()
    risk = risk or RiskConfig()
    if risk.underived:
        # Production hands this `RiskConfig.load()`, which carries no dollar
        # quantities: derive them from the venue's observed balance, per pass
        # (ADR 0045). No observation -> the config stays underived, every
        # `suggested_contracts` refuses to size, and `reference_contracts` --
        # the column the gate counts -- is untouched because `reference()`
        # replaces the dollars with constants. The record cannot be disabled
        # by a missing balance read; the shown size can, loudly.
        derived = risk.with_observed_balance(db.latest_balance_tenths(conn))
        if derived is None:
            logger.warning(
                "no observed balance in venue_balance_snapshots; sizing will "
                "refuse this pass (reference sizing is unaffected)"
            )
        else:
            risk = derived
    suppression = suppression or SuppressionConfig()
    counts = counts or PassCounts()

    version = ensure_strategy_config(
        conn,
        {
            "suppression": suppression.__dict__,
            # The check **vocabulary**, not just the thresholds. ADR 0019.
            #
            # `suppression.__dict__` hashes field *values*, so adding, removing
            # or renaming a check changed no field and minted no version --
            # and `suppressed_reason` is half the `actionable` predicate, so
            # two check-vocabularies would pool into one dataset with nothing
            # recording the split. Same defect as the `max_order_contracts`
            # omission below, one level up: the rule is "everything the counted
            # column depends on", and the counted column depends on which
            # checks exist at least as much as on what they are set to.
            "suppression_checks": list(ALL_CHECK_NAMES),
            "kelly_fraction": risk.kelly_fraction,
            # Everything the **counted** column depends on, and nothing else.
            #
            # `reference_contracts` is what `gate.POPULATIONS` counts, and it is
            # sized from the reference profile plus these two strategy
            # parameters. A change to either moves the counter, so it has to
            # mint a new version or the record silently mixes two regimes --
            # ADR 0015 claimed it already did, and it did not: `kelly_fraction`
            # was here and `max_order_contracts` and the reference constants
            # were not. Found by `measurement-skeptic` auditing that claim.
            #
            # `bankroll_dollars` and the three dollar caps are deliberately
            # **excluded**. They cannot reach the counted column -- that is the
            # whole point of the reference profile -- and including them would
            # mint a new strategy version every time the running balance moved,
            # shredding the record into unpoolable fragments for a reason that
            # has nothing to do with strategy.
            "max_order_contracts": risk.max_order_contracts,
            "reference_profile": [
                REFERENCE_BANKROLL_DOLLARS,
                REFERENCE_MAX_POSITION_DOLLARS,
                REFERENCE_MAX_EXPOSURE_DOLLARS,
                REFERENCE_MAX_DAILY_LOSS_DOLLARS,
            ],
            # Changed 2026-08-15, when MLB player props joined the moneyline.
            # This string is part of the config precisely so that change mints a
            # new strategy version: prop rows and team rows are two populations,
            # devigged against different book sets (props have no sharp book at
            # all), and a record that mixed them under one version would be one
            # dataset describing two regimes.
            "prices": "moneyline + mlb player props",
            # Part of the config so a change to the recording rule mints a new
            # strategy version and the record segments on it, rather than
            # silently mixing two regimes in one dataset.
            "record": "skip consecutive identical (ask, fair) per side",
        },
        "chain runner configuration",
        now=stamp,
    )
    # The same population the resulting order will be admitted against.
    # Sizing a recommendation against a budget the order endpoint does not
    # use is how a card offers a size the server then refuses.
    exposure = current_exposure_dollars(conn, dry_run=ORDERS_ARE_DRY_RUNS)
    if exposure is None:
        # Raise rather than pass `None` down to `size_position`. It would
        # refuse -- correctly -- but it would refuse *every candidate on the
        # slate*, and each refusal would be persisted as a recommendation. The
        # record would then hold a hundred rows saying "not sized" for a reason
        # that has nothing to do with any of them, mixed in with the genuine
        # no-edge rows and told apart by nothing. The loop is built to die
        # loudly (`MAX_CONSECUTIVE_FAILURES`); this is what that is for.
        raise RuntimeError(
            "current exposure could not be read, so nothing on this slate can "
            "be sized. Refusing to record a pass -- a slate of refusals for a "
            "reason unrelated to the bets would be indistinguishable from a "
            "slate with no edge."
        )

    # The second budget the sizer spends, and until 2026-08-10 nothing supplied
    # it: `size_position`'s `daily_pnl_dollars` was keyword-only with a default
    # of `0.0`, so the daily loss limit was applied to a number this process
    # invented. Read once per pass, beside the exposure, for the same reason --
    # it is a property of the portfolio, not of any candidate.
    #
    # Raised rather than passed down as `None`, on the argument the exposure
    # read makes two lines up: `None` would refuse every candidate on the slate
    # and persist a hundred rows saying "not sized" for a reason that has
    # nothing to do with any of them.
    # `day_start_hour` is passed, not defaulted. Omitting it silently took
    # `DEFAULT_DAY_START_UTC_HOUR` while `api/routes.py:1546` took the
    # configured hour, so the kill switch that suppresses *every row on the
    # slate* (`core/sizing.py:186-191`) and the one that admits the resulting
    # order were measuring two different days the moment
    # `ODDS_BUDGET_DAY_START_UTC_HOUR` was set to anything but 10.
    daily_pnl = daily_realised_pnl_dollars(
        conn, now_ms=stamp, dry_run=ORDERS_ARE_DRY_RUNS,
        day_start_hour=day_start_hour,
    )
    if daily_pnl is None:
        raise RuntimeError(
            "the day's realised P&L could not be read, so the daily loss limit "
            "cannot be applied to anything on this slate. Refusing to record a "
            "pass -- 'cannot determine what I have lost today' must not resolve "
            "to 'nothing'."
        )

    setup_ms = int((time.perf_counter() - priced_started) * 1000)

    # Judged but not yet written. Surfaced rows carry the Skeptic's prompt
    # inputs; everything else carries an empty mapping, because nothing will
    # ask it anything.
    pending: list[ReviewCandidate] = []

    alias_cache: dict[str, TeamAliases] = {}
    link_started = time.perf_counter()
    linked = link_discovered_events(conn, events, now=stamp, alias_cache=alias_cache)
    link_ms = int((time.perf_counter() - link_started) * 1000)
    judge_started = time.perf_counter()
    counts.events_discovered += len(events)
    counts.events_linked += len(linked)
    counts.events_unmatched += len(events) - len(linked)

    by_ticker = {e.event_ticker: e for e in events}

    for event_ticker, (link_id, skew_ms) in linked.items():
        event = by_ticker[event_ticker]
        link_row = conn.execute(
            "SELECT odds_event_id FROM event_links WHERE id = ?", (link_id,)
        ).fetchone()
        if link_row is None:
            counts.errors.append(f"{event_ticker}: link {link_id} disappeared")
            continue
        odds_event_id = link_row["odds_event_id"]

        if event.market_type == MARKET_TYPE_PROP:
            # A separate path rather than a branch inside the loop below,
            # because the *grouping* differs, not the filter: one devig per
            # (player, line) against ["Over", "Under"], where a team event is
            # one devig per event against the two teams.
            _price_prop_event(
                conn,
                event,
                link_id=link_id,
                odds_event_id=odds_event_id,
                skew_ms=skew_ms,
                stamp=stamp,
                counts=counts,
                pending=pending,
                risk=risk,
                suppression=suppression,
                version=version,
                exposure=exposure,
                daily_pnl=daily_pnl,
            )
            continue

        books = book_quotes_for_event(conn, odds_event_id, now=stamp)
        if books is None:
            counts.dropped_no_books += 1
            continue

        # A game that has already started is not a candidate, it is a different
        # measurement. Measured on one live pass: 36 of 104 recorded rows were
        # for games in progress, and their edges ran -200.3 to +67.7 tenths
        # against -39.2 to -17.7 for the pre-game rows on the same slate. The
        # dispersion is the tell -- a stored pre-game consensus compared against
        # a Kalshi price that has absorbed two innings is not a mispricing, it
        # is two different questions subtracted from each other. Fourteen of
        # those rows were suppressed for `wide_market` or `suspicious_edge` and
        # twenty-two passed as ordinary no-edge observations, which is the
        # dangerous half: they enter the evidence record looking like evidence.
        #
        # Dropped rather than suppressed. They can never be scored at any
        # horizon -- the closing line is read before kickoff and these are
        # written after it -- so recording them would add rows that cannot
        # become evidence and would put two regimes in one dataset.
        #
        # The sportsbook's kickoff, never Kalshi's: Kalshi's `occurrence_datetime`
        # runs three hours late and would call the seventh inning "not started".
        if books.commence_ms is not None and books.commence_ms <= stamp:
            counts.dropped_game_started += 1
            continue

        try:
            devig_result, metadata = consensus_devig(
                books.outcomes, books.quotes_by_book, sharp_books=SHARP_BOOKS
            )
        except DevigError as exc:
            # A book set that cannot be devigged is a finding, not a crash.
            counts.errors.append(f"{event_ticker}: {exc}")
            continue

        fair_ids = write_fair_price(
            conn,
            link_id=link_id,
            devig_result=devig_result,
            metadata=metadata,
            computed_ms=stamp,
        )
        counts.fair_prices_written += len(fair_ids)

        aliases = alias_cache[event.sport_key]
        for market in event.markets:
            if market.market_type != "moneyline" or not market.yes_side:
                continue

            outcome = resolve_outcome(market.yes_side, books.outcomes, aliases)
            if outcome is None:
                counts.dropped_unresolved_outcome += 1
                continue

            quote = latest_kalshi_quote(conn, market.ticker)
            if quote is None:
                counts.dropped_no_kalshi_quote += 1
                continue

            for side in ("yes", "no"):
                # The side's own outcome: buying NO on the Houston market is
                # buying the opponent, so the fair probability to compare
                # against is the opponent's.
                side_outcome = (
                    outcome
                    if side == "yes"
                    else next((o for o in books.outcomes if o != outcome), None)
                )
                if side_outcome is None:
                    continue

                ask = ask_for_side(quote, side)
                if ask is None:
                    counts.dropped_no_kalshi_quote += 1
                    continue

                # Depth at the ask is the OPPOSING bid's size: a yes ask is
                # derived from the no bid, so that is the resting size you would
                # actually lift.
                depth = quote["no_bid_qty"] if side == "yes" else quote["yes_bid_qty"]

                recommendation = build_recommendation(
                    Candidate(
                        ticker=market.ticker,
                        side=side,
                        outcome_name=side_outcome,
                        ask_tenths=ask,
                        depth_at_ask=depth,
                        kalshi_quote_age_ms=stamp - int(quote["observed_ms"]),
                        link_id=link_id,
                        fair_price_id=fair_ids.get(side_outcome),
                        devig=devig_result,
                        book_count=metadata["book_count"],
                        market_width=metadata["market_width"],
                        odds_age_ms=books.oldest_book_age_ms,
                        commence_skew_ms=skew_ms,
                    ),
                    risk=risk,
                    suppression=suppression,
                    strategy_config_version=version,
                    current_exposure_dollars=exposure,
                    # Per market, because `max_position_dollars` is a per-market
                    # cap. Read inside the loop rather than hoisted: a slate is
                    # a hundred candidates over a few dozen tickers, the query
                    # is bounded by the exposure cap itself, and hoisting it
                    # would mean maintaining a second definition of "which
                    # orders still hold capital on this ticker".
                    current_position_dollars=open_position_dollars(
                        conn, market.ticker, dry_run=ORDERS_ARE_DRY_RUNS
                    ),
                    daily_pnl_dollars=daily_pnl,
                    created_ms=stamp,
                )
                pending.append(
                    ReviewCandidate(
                        recommendation=recommendation,
                        prompt_kwargs=(
                            _skeptic_context(
                                market=market,
                                event=event,
                                outcome=side_outcome,
                                recommendation=recommendation,
                                devig_result=devig_result,
                                metadata=metadata,
                                books=books,
                            )
                            if recommendation.surfaced
                            else {}
                        ),
                    )
                )

    # Deliberately does NOT log its counts. Every caller reports them and each
    # reports a superset: the loop's `pass N ok` carries these fields plus the
    # scoring, settlement and alert counts, and `run_chain.py` prints the same
    # dict as indented JSON. A line here was a second copy of the loop's, four
    # milliseconds earlier, at the quote cadence -- about a third of the log
    # volume for nothing, against a 100-line `flyctl logs` buffer.
    #
    # The one thing that copy did carry was a full pass that priced fine and
    # then died in scoring. `run_loop.py` reports the counts on that path
    # explicitly, which is where the knowledge of "there is more to come"
    # actually lives.
    # Timed around the review-and-persist leg too, not just the devig loop
    # above it: `review` leaves the process for Anthropic, so a pass that goes
    # slow because the fleet is slow must not read as "pricing is slow".
    judge_ms = int((time.perf_counter() - judge_started) * 1000)
    persist_started = time.perf_counter()
    priced = _review_and_persist(
        conn, pending, counts=counts, review=review, now=stamp
    )
    priced.leg_price_persist_ms = int((time.perf_counter() - persist_started) * 1000)
    # `priced is counts` -- `_review_and_persist` mutates and returns the same
    # object. So which of the two names these are assigned through does not
    # matter, and a comment here previously claimed it did. Left as `priced`
    # only because that is what the line below already used.
    priced.leg_price_setup_ms = setup_ms
    priced.leg_price_link_ms = link_ms
    priced.leg_price_judge_ms = judge_ms
    priced.leg_price_ms = int((time.perf_counter() - priced_started) * 1000)
    return priced


def _review_and_persist(
    conn,
    pending: Sequence[ReviewCandidate],
    *,
    counts: PassCounts,
    review,
    now: Optional[int] = None,
) -> PassCounts:
    """Phase two: attack the surfaced rows the budget affords, then write.

    The Skeptic sees only the rows that would be surfaced. That is a cost
    decision as much as a design one -- a live pass builds ~100 rows and nearly
    all of them have no edge, so reviewing the lot would buy a hundred "no"s a
    pass at 96 passes a day. It also means the bill today is exactly zero calls,
    because `surfaced` has never been anything but zero.

    **`surfaced == 0` is not a spend guard, and it was the only one.** See
    `agents/budget.py`. The connection and the clock are both handed down now
    because the meter's state lives on disk and its day is a sports day: the
    ceiling has to survive a restart, and the pass's own `now` has to be the one
    that decides which day a call lands in, or a pass straddling 10:00 UTC would
    bill against a boundary the rest of it did not use.
    """
    positions = [i for i, c in enumerate(pending) if c.recommendation.surfaced]
    outcome = review([pending[i] for i in positions], conn=conn, now=now)
    counts.skeptic_reviewed += outcome.reviewed
    counts.skeptic_blocked += outcome.blocked
    counts.skeptic_unreviewed += outcome.unreviewed

    # Positional, so it is worth stating what would happen if it stopped being
    # true: a short list would make `zip` drop the tail silently, and the
    # dropped rows would persist as surfaced without ever having been reviewed.
    # That is the one failure here that money could reach.
    #
    # Verified by disabling, 2026-08-11. Until then this raise had never been
    # driven by any test -- it was asserted as a consequence of another test's
    # mutation ("`runner._review_and_persist` *would* have raised") and never
    # actually fired, which by this repo's standard makes it decoration.
    # `tests/test_agent_budget.py::TestAGuardIsNotAGuardUntilItHasFired` now
    # drives it with a stub `review` that returns a short list; deleting these
    # four lines turns that test RED with the tail silently persisted.
    if len(outcome.recommendations) != len(positions):
        raise RuntimeError(
            f"the Skeptic returned {len(outcome.recommendations)} rows for "
            f"{len(positions)} surfaced candidates. Refusing to persist a slate "
            f"whose reviewed rows cannot be matched to their verdicts."
        )
    amended = dict(zip(positions, outcome.recommendations))

    for index, candidate in enumerate(pending):
        rec = amended.get(index, candidate.recommendation)

        if persist_if_changed(conn, rec) is None:
            # Same ask, same fair value as the last row for this side.
            # Re-recording it would add a row and no information -- but the
            # existing row is stamped with this pass's ages, so it stays as
            # fresh as the quote behind it actually is.
            counts.unchanged_confirmed += 1
            continue

        counts.recommendations += 1
        if rec.surfaced:
            counts.surfaced += 1
        elif rec.suppressed_reason:
            counts.suppressed += 1

    return counts


# ---------------------------------------------------------------------------
# Ingest pass -- network
# ---------------------------------------------------------------------------


def upcoming_by_sport(events: Sequence[DiscoveredEvent]) -> dict[str, list[int]]:
    """`sport_key -> commence times`, which is what `plan_sweep` prioritises on."""
    upcoming: dict[str, list[int]] = {}
    for event in events:
        upcoming.setdefault(event.sport_key, []).append(event.commence_ms)
    return upcoming


def soonest_by_sport(events: Sequence[DiscoveredEvent]) -> dict[str, int]:
    """`sport_key -> soonest Kalshi kickoff`, for the sports Kalshi lists.

    Kalshi's clock, three hours late, and deliberately not corrected. It is used
    only to say *which sports exist* and to rank bootstrap candidates, and a
    constant offset changes neither. Every timing decision anchors on the
    sportsbook's own kickoff instead -- see `odds/timing.py`.
    """
    soonest: dict[str, int] = {}
    for sport, commences in upcoming_by_sport(events).items():
        if commences:
            soonest[sport] = min(commences)
    return soonest


async def fetch_and_store_odds(
    conn,
    odds_client,
    budget,
    *,
    events: Sequence[DiscoveredEvent],
    config: OddsConfig,
    now: int,
    max_odds_age_ms: int = 900_000,
    allow_bootstrap: bool = True,
    manual: Sequence[ManualRefresh] = (),
) -> tuple[int, int, SweepDecision]:
    """Sweep only when the window it opens will be worth having, then hold it open.

    `decide_sweeps` spends credits just before a cluster of kickoffs rather than
    on whichever pass happened to run first, and *keeps spending* on a
    `refresh_interval_ms` cadence for as long as that cluster's slot is due. The
    decision, including the decision *not* to sweep, comes back so the pass can
    report it.

    **The second half of that sentence is new and is the point.** One buy per
    cluster made the slate bettable for exactly `max_odds_age_ms` and then left
    every row suppressed as `stale_odds` with the games still an hour out. The
    threshold was never the problem; nothing re-bought.

    `allow_bootstrap` is passed `False` by the quote cadence -- see
    `decide_sweeps`, which owns the reason.

    `manual` is the taps this pass should serve, already filtered for age by
    `ondemand.take`. They are handed to `decide_sweeps` rather than served
    around it, so a tap is charged against the same `credits_left` the planner
    spends from and refused by the same ceiling. A second spend path beside the
    planner is the shape of every credit accident in this file's history.

    **Every outcome is written to `odds_sweep_log`, including "nothing".** The
    decision used to be logged and nothing more, so a pass that looked and
    declined left no row anywhere and read exactly like a pass that never ran.
    """
    # The sports a prop ladder was actually discovered for, so a league with no
    # ladder is not reserved against for props it will never buy. Passed rather
    # than assumed: charging every sport would starve WNBA sweeps to protect a
    # baseball-only cost.
    # **Empty unless the deployment opts in**, which turns off the scheduled
    # prop purchase in the one place that matters: `decide_sweeps` reserves
    # against this set, and `fetch_and_store_props` refuses a firing whose sport
    # is not in it. One switch, both halves, so the reservation and the spend
    # cannot disagree -- which is the 2026-08-15 outage in miniature.
    #
    # Why off: props were 260 of a 13-game cluster's 266 credits and contribute
    # **no cluster** to the 300-game floor, because `gate.py:424-428` collapses a
    # prop event onto its game's `odds_event_id` by construction. See
    # `OddsConfig.buy_props_on_schedule`, which carries the full argument.
    #
    # A *tap* is unaffected. `FiringSweep.prop_event_ids` names its one fixture
    # explicitly and `fetch_and_store_props` honours a named set regardless of
    # this switch -- that is the whole point of the two-tier design, and it is
    # why the named-set path bypasses the guards rather than sharing them.
    prop_sports = (
        {
            e.sport_key
            for e in events
            if e.market_type == MARKET_TYPE_PROP and e.sport_key is not None
        }
        if config.buy_props_on_schedule
        else set()
    )
    decision = decide_sweeps(
        conn,
        in_scope=soonest_by_sport(events),
        budget=budget,
        cost=sweep_cost(config.markets, config.regions),
        now_ms=now,
        max_odds_age_ms=max_odds_age_ms,
        prop_cost_per_event=sweep_cost(prop_market_keys(), config.regions),
        prop_sports=prop_sports,
        allow_bootstrap=allow_bootstrap,
        manual=manual,
    )
    logger.info("sweep decision: %s", decision.detail)

    if not decision.fire:
        record_sweep_outcome(
            conn, pass_ms=now, outcome=SKIPPED, detail=decision.detail
        )

    sweeps = stored = 0
    for firing in decision.fire:
        # Asked *before* the call, not after. A call that succeeds and exhausts
        # the budget would make an after-the-fact check report "refused" for a
        # sweep that was served -- the flattering direction is the dangerous one
        # here, because it would explain away a real outage.
        affordable = budget.refusal_reason(firing.cost, now) is None

        # `trigger` reaches `api_credits` only for a tap. Everything else stays
        # NULL, which is what every row written before schema v9 is, and what
        # `_SERVED_SWEEP` counts as a sweep. Stamping `'scheduled'` on the
        # planner's rows instead would be the same behaviour with a migration
        # attached, and would make the exclusion depend on every future caller
        # remembering to label itself.
        stamp = MANUAL if firing.trigger == MANUAL else None
        quotes = await odds_client.fetch_odds(
            firing.sport_key, now_ms=now, trigger=stamp
        )
        if quotes:
            sweeps += 1
            n = store_quotes(conn, quotes)
            stored += n
            record_sweep_outcome(
                conn, pass_ms=now, sport_key=firing.sport_key,
                outcome=SERVED, detail=firing.detail, quotes_stored=n,
            )
            stored += await fetch_and_store_props(
                conn, odds_client, events=events, quotes=quotes,
                sport_key=firing.sport_key, now=now, slot=firing.slot,
                trigger=firing.trigger, only_events=firing.prop_event_ids,
                # The same set `decide_sweeps` reserved against, handed to the
                # code that spends. Passing it rather than re-deriving it is
                # what makes "reserved for" and "bought" one expression.
                scheduled_prop_sports=prop_sports,
            )
        elif affordable:
            # The call went out and the slate came back empty. A normal state,
            # and a completely different one from being refused -- which is why
            # `fetch_odds` returning `[]` is not enough on its own to say which
            # happened.
            record_sweep_outcome(
                conn, pass_ms=now, sport_key=firing.sport_key,
                outcome=NO_DATA,
                detail=(
                    f"the call went out and the sportsbook returned no "
                    f"fixtures for {firing.sport_key}"
                ),
            )
        # else: `fetch_odds` recorded the refusal itself, naming the ceiling
        # that bound. Recording a second row here would contradict it.
    return sweeps, stored, decision


async def fetch_and_store_props(
    conn,
    odds_client,
    *,
    events: Sequence[DiscoveredEvent],
    quotes: Sequence[OddsQuote],
    sport_key: str,
    now: int,
    slot: Optional[SweepSlot] = None,
    trigger: str = SCHEDULED,
    only_events: Sequence[str] = (),
    scheduled_prop_sports: Optional[Collection[str]] = None,
) -> int:
    """Buy player props for the fixtures a team sweep just paid for.

    **The cadence is inherited, not invented.** This runs only from the branch
    where a team sweep was *served*, so props are bought exactly as often as
    `decide_sweeps` decides to open a window -- once, just before a cluster of
    kickoffs -- and never on the ~22s quote cadence or on a pass that declined.
    A timer of its own would be a second answer to a question `odds/timing.py`
    already answers, and the two would drift.

    **Cost, and the estimate that was wrong.** Props are a per-event endpoint
    billed per market key per region. Both the primary and `_alternate` feeds
    are requested -- ten keys -- and the deployed config sets two regions, so an
    event costs **20**, not ten. This docstring previously said "roughly ten
    credits a fixture ... on a fifteen-game slate that is ~150 credits". Both
    figures were assumptions restated: the fixture count was assumed at 15 and
    the region count was never read. The first live pass spent **384 of 400 in a
    single pass** and refused every remaining sweep that day, team sweeps
    included. **Do not restate a cost here that has not been reconciled against
    `api_credits` and the provider's own `x-requests-used`.**

    **Which fixtures: the ones the slot was fired for.** `slot` carries the
    kickoff cluster this sweep was scheduled against, and `SweepSlot.covers` is
    the same predicate that produced its published `games_covered`. Buying for
    every pre-game fixture in the returned slate instead bought 27 where the
    slot covered 4.

    `slot` is `None` on a **bootstrap** firing, which by definition has no
    cluster to aim at. That buys no props, and the refusal is recorded rather
    than silent -- a pass that skipped and said nothing is indistinguishable
    from one that never ran.

    A residual over-buy remains and is deliberate: covered fixtures that Kalshi
    lists no ladder for are still bought. The exact set needs `event_links`,
    which is not written until the pricing pass, and inverting that order would
    make ingest depend on a stage that runs after it. It is bounded, and visible
    in `odds_sweep_log` because every event's outcome is recorded.

    **`only_events` is the second way to name a fixture set, and it exists
    because a tap has no slot.** An on-demand prop refresh is for one game the
    person is looking at, so the caller states it outright instead of deriving
    it from a kickoff cluster that was never planned. When given, it *replaces*
    the slot-derived set and both guards below step aside -- neither is about
    slots as such, they are both about never buying props for a fixture set
    nobody named. A named set is exactly what they were holding out for.

    It is still intersected with what the slate returned and still filtered to
    pre-game, because those two facts come from the books and the clock rather
    than from the caller, and a caller cannot make a started game pre-game by
    naming it.

    Returns the number of prop quotes stored.
    """
    named = [e for e in dict.fromkeys(only_events) if e]

    if not named and scheduled_prop_sports is not None:
        if sport_key not in scheduled_prop_sports:
            # The scheduled prop purchase is off for this sport, which since
            # 2026-08-16 is the default for every sport (ADR 0032). Checked
            # against **the same set `decide_sweeps` reserved against**, not
            # against the config flag directly: a spend that read one value
            # while the reservation read another is the shape of the
            # 2026-08-15 outage, where the planner authorised 6 credits and the
            # fetch spent 384.
            #
            # Recorded rather than silent. A pass that skipped and said nothing
            # is indistinguishable from one that never ran -- the founding
            # defect of `odds_sweep_log`.
            record_sweep_outcome(
                conn, pass_ms=now, sport_key=sport_key, outcome=SKIPPED,
                detail=(
                    f"props: scheduled prop buying is off for {sport_key}, so "
                    f"this window buys team lines only. A single fixture's "
                    f"ladder is still available on demand for the cost of one "
                    f"fixture rather than the whole slate."
                ),
            )
            return 0

    prop_events = [
        e
        for e in events
        if e.market_type == MARKET_TYPE_PROP and e.sport_key == sport_key
    ]
    if not prop_events:
        # Not silence: a slate where Kalshi lists no ladder is a real state, and
        # it must be distinguishable from a pass where the fetch was never
        # attempted. Buying props with no Kalshi counterpart is spending
        # credits on a comparison that has only one side.
        record_sweep_outcome(
            conn, pass_ms=now, sport_key=sport_key, outcome=SKIPPED,
            detail=(
                f"props: no prop series discovered for {sport_key}, so there "
                f"is nothing to compare a book's prop against"
            ),
        )
        return 0

    if slot is None and not named:
        # A bootstrap firing has no kickoff cluster, so there is no set of
        # fixtures this sweep was *for*. Buying the whole slate is what spent
        # 384 of 400 in one pass; buying nothing is the conservative reading,
        # and the next scheduled slot for this sport will buy properly.
        record_sweep_outcome(
            conn, pass_ms=now, sport_key=sport_key, outcome=SKIPPED,
            detail=(
                f"props: {sport_key} swept without a planned slot (bootstrap), "
                f"so there is no covered fixture set to buy props for"
            ),
        )
        return 0

    if trigger != SCHEDULED and not named:
        # A refresh re-buys the team lines that keep an open window from
        # shutting. Props do not go stale on the same clock as a moneyline and,
        # far more to the point, they are billed per event per market key per
        # region: re-buying them every `refresh_interval_ms` would multiply the
        # single largest line item in this file by the number of refreshes in a
        # slot. The opening call bought them; this one does not buy them again.
        #
        # Checked here rather than at the call site so no future caller can
        # forget it. The same argument as `slot is None` above, one trigger
        # along.
        record_sweep_outcome(
            conn, pass_ms=now, sport_key=sport_key, outcome=SKIPPED,
            detail=(
                f"props: {sport_key} was a {trigger} of an already-open window, "
                f"and props ride the opening call only"
            ),
        )
        return 0

    # Pre-game only, for the reason `run_pricing_pass` drops in-play rows: a
    # prop priced after first pitch cannot be scored against a closing line that
    # was read before it. And covered by *this slot* -- `fetch_odds` returns the
    # whole slate, which is not the same thing as the fixtures this sweep was
    # fired for.
    wanted = set(named)
    pre_game = sorted(
        {
            q.odds_event_id
            for q in quotes
            if q.commence_ms > now
            and (
                q.odds_event_id in wanted
                if named
                # `slot` is not None here: the guard above returns unless one of
                # the two ways of naming a fixture set was supplied.
                else slot.covers(q.commence_ms)
            )
        }
    )
    if not pre_game:
        record_sweep_outcome(
            conn, pass_ms=now, sport_key=sport_key, outcome=SKIPPED,
            detail=(
                (
                    f"props: fixture {', '.join(named)} is not in the slate the "
                    f"sweep returned, or has already started"
                )
                if named
                else (
                    "props: no fixture this slot covers is still pre-game "
                    f"({slot.reason})"
                )
            ),
        )
        return 0

    markets = prop_market_keys()
    prop_quotes = await odds_client.fetch_props(
        sport_key, pre_game, now_ms=now, markets=markets,
        trigger=MANUAL if trigger == MANUAL else None,
    )
    if not prop_quotes:
        # `fetch_props` records its own refusal naming the ceiling that bound,
        # so a second row here would contradict it. This branch is the other
        # case: the calls went out and the books quote no props.
        return 0

    n = store_quotes(conn, prop_quotes)
    record_sweep_outcome(
        conn, pass_ms=now, sport_key=sport_key, outcome=SERVED,
        detail=(
            # `slot covers N` beside `bought M` is the pair that makes the
            # 2026-08-15 defect visible from the log alone: it read "27 pre-game
            # fixtures" with nothing to compare 27 against. A tap gets the same
            # pair against the set it named.
            f"props: bought {len(pre_game)} of "
            f"{len(named) if named else slot.games_covered} "
            f"{'requested' if named else 'covered'} fixture(s) in the slate, "
            f"{len(prop_events)} Kalshi prop events, {len(markets)} market keys"
        ),
        quotes_stored=n,
    )
    return n


def store_quotes_from_discovery(
    conn, events: Sequence[DiscoveredEvent], *, now: int
) -> int:
    """Store the quote carried on the discovery payload itself.

    **No extra request.** `/events?with_nested_markets=true` already returns
    `yes_bid_dollars`, `no_bid_dollars` and `yes_ask_size_fp` on every market, so
    a separate orderbook call per ticker would be a second round trip for data
    already in hand -- and, worse, a second wire format to guess at. The nested
    payload is pinned by `tests/fixtures/events_sports_nested.json`; the REST
    orderbook response is not captured anywhere, and writing a parser against an
    uncaptured format is what left the WebSocket path dead.

    A market with neither bid readable is skipped rather than stored as zeros.
    """
    stored = 0
    for event in events:
        for market in event.markets:
            if market.yes_bid_tenths is None and market.no_bid_tenths is None:
                continue
            # Sizes cross over, and it is worth spelling out rather than
            # trusting the reader to re-derive it at a glance:
            #
            #   a YES ask is `1 - no_bid`, so it is filled by the resting NO bid
            #   => size at the yes ask IS the no-bid size
            #   a NO ask is `1 - yes_bid`, filled by the resting YES bid
            #   => size at the no ask IS the yes-bid size
            #
            # The columns store bid sizes; `DiscoveredMarket` names ask sizes,
            # because an ask size is what a buyer can actually lift.
            conn.execute(
                "INSERT INTO kalshi_quotes (ticker, observed_ms, seq, source, "
                "yes_bid_tenths, yes_bid_qty, no_bid_tenths, no_bid_qty) "
                "VALUES (?, ?, NULL, 'rest', ?, ?, ?, ?)",
                (
                    market.ticker, now,
                    market.yes_bid_tenths, market.no_ask_size,
                    market.no_bid_tenths, market.yes_ask_size,
                ),
            )
            stored += 1
    conn.commit()
    return stored


#: How far back a series may have last been seen and still be walked on a quote
#: pass. Two full passes: one full-pass interval is the cadence at which the
#: set is refreshed, so a single-interval window would drop every series in the
#: gap between a full pass writing and the next quote pass reading.
#:
#: Deliberately not "forever". A series that stops listing games -- a season
#: ending -- would otherwise be walked every 15 seconds for the rest of the
#: instance's life, which is the same unbounded-growth shape as the query that
#: took the box down on 2026-08-18.
PRICEABLE_SERIES_WINDOW_MS = 2 * 900_000


def priceable_series(conn, *, now: int) -> list[str]:
    """Series that recently carried a priceable event, for the narrowed walk.

    **Read from `kalshi_events`, which holds only priceable events.**
    `upsert_discovered` is fed `discover_from_events`' output, so anything in
    that table already survived scope classification -- there is no second
    definition of "priceable" here that could drift from discovery's.

    **Not read from `event_links`**, which was the first instinct and is wrong:
    a link exists only where a fixture *matched* a sportsbook event, so the set
    would collapse to the handful of game-level series that happen to be linked
    right now and silently stop quoting every prop, spread and total series.
    The narrowed walk must cover what discovery can price, not what matching
    happened to join.

    Returns `[]` on a fresh volume, and the caller treats that as "walk
    everything" rather than "walk nothing".
    """
    rows = conn.execute(
        "SELECT DISTINCT series_ticker FROM kalshi_events "
        "WHERE last_seen_ms >= ? ORDER BY series_ticker",
        (now - PRICEABLE_SERIES_WINDOW_MS,),
    ).fetchall()
    return [r["series_ticker"] for r in rows]


async def run_kalshi_pass(
    conn,
    kalshi_client,
    *,
    now: int,
    counts: PassCounts,
    log_discovery_summary: bool = True,
    series_tickers: Optional[Sequence[str]] = None,
) -> list[DiscoveredEvent]:
    """Discovery and the quotes it carries. Kalshi only; spends no odds credit.

    Split out because it is the whole of a *quote pass* and only part of an
    ingest pass. Kalshi REST is unmetered and The Odds API is not, so this leg
    can run every twenty seconds while the other can run twice a day, and
    keeping one implementation of it is what stops the two cadences drifting
    into two slightly different notions of what a quote is.

    The two cadences do differ in one thing, and it is a property of the
    cadence rather than of the work: how often the `discovery:` summary is worth
    printing. A quote pass passes False, so that line is emitted only when its
    numbers change; the full pass always prints and is the heartbeat. See
    `_LAST_SUMMARY` in `kalshi/discovery.py`.

    **`series_tickers` narrows the walk, and it is what stops this taking the
    instance down.** ADR 0053. The unnarrowed walk paginates the whole open
    catalogue -- 11,160 events and 96,326 nested markets, measured 2026-08-19 --
    to find ~510 priceable ones, and on the quote cadence it ran every 15s. It
    took 27-77s on the live shared vCPU, starved uvicorn of the CPU, and cost
    18 unbroken minutes of downtime. Measured the same day against the real API:

        full walk          15.21s   11,160 events, 96,326 markets
        19 scoped walks     3.13s      573 events,  6,917 markets   (4.9x)

    with **every** priceable event still found -- the coverage check is in
    `docs/measurements/2026-08-19-quote-pass-cost-attribution.md`, and the
    saving is bytes transferred rather than requests made.

    `None` means the full walk, which is what the *full* pass must keep doing:
    a narrowed walk can only ever re-see series it already knows, so something
    has to look at the whole catalogue or a newly-listed league is invisible
    forever. Passing an **empty** sequence also walks everything, deliberately
    -- an empty set means "nothing known yet", i.e. a fresh volume, and the
    honest response there is to go and look rather than to fetch nothing and
    report a quiet slate.
    """
    walk_started = time.perf_counter()
    if series_tickers:
        raw_events: list[dict] = []
        for series in series_tickers:
            raw_events.extend(
                [
                    e
                    async for e in kalshi_client.events(
                        with_nested_markets=True, series_ticker=series
                    )
                ]
            )
    else:
        # `events()` is an async *generator* -- it paginates lazily -- so it is
        # consumed rather than awaited.
        raw_events = [
            e async for e in kalshi_client.events(with_nested_markets=True)
        ]
    parse_started = time.perf_counter()
    counts.leg_walk_ms = int((parse_started - walk_started) * 1000)

    events = discover_from_events(
        raw_events, always_log_summary=log_discovery_summary
    )
    store_started = time.perf_counter()
    counts.leg_parse_ms = int((store_started - parse_started) * 1000)

    upsert_discovered(conn, events, now=now)
    counts.markets_quoted = store_quotes_from_discovery(conn, events, now=now)
    counts.leg_store_ms = int((time.perf_counter() - store_started) * 1000)
    return events


async def run_ingest_pass(
    conn,
    kalshi_client,
    odds_client,
    budget,
    *,
    config: OddsConfig,
    now: Optional[int] = None,
    counts: Optional[PassCounts] = None,
    suppression: Optional[SuppressionConfig] = None,
) -> tuple[list[DiscoveredEvent], PassCounts]:
    """Discover, store the carried quotes, and sweep odds when it is time.

    Returns the discovered events so the pricing pass can run on the same list
    without re-reading the network.

    The staleness limit comes from the same `SuppressionConfig` that will later
    reject a stale row, never from a constant of its own. The sweep exists to
    open exactly that window; two numbers for one quantity drift, and the
    tighter one wins in silence.
    """
    stamp = now if now is not None else now_ms()
    counts = counts or PassCounts()
    suppression = suppression or SuppressionConfig()

    events = await run_kalshi_pass(conn, kalshi_client, now=stamp, counts=counts)

    sweeps, stored, decision = await fetch_and_store_odds(
        conn, odds_client, budget, events=events, config=config, now=stamp,
        max_odds_age_ms=suppression.max_odds_age_ms,
    )
    counts.odds_sweeps = sweeps
    counts.odds_quotes_stored = stored
    counts.sweep_decision = decision.detail

    return events, counts


async def run_once(
    conn,
    kalshi_client,
    odds_client,
    budget,
    *,
    config: OddsConfig,
    risk: Optional[RiskConfig] = None,
    suppression: Optional[SuppressionConfig] = None,
    now: Optional[int] = None,
    window_open: bool = False,
) -> PassCounts:
    """One full pass: ingest, then price. The unit the scheduler repeats.

    The risk day comes off `config` rather than being a parameter of its own, so
    this caller cannot forget it: `OddsConfig` is already required here, and the
    hour it carries is the one `api/routes.py` uses for the same kill switch.
    """
    stamp = now if now is not None else now_ms()
    suppression = suppression or SuppressionConfig()
    events, counts = await run_ingest_pass(
        conn, kalshi_client, odds_client, budget, config=config, now=stamp,
        suppression=suppression,
    )
    # **Here and not in the quote pass.** Retention competes for the same write
    # lock as the inserts it exists to keep fast, so running it on the 15s
    # cadence would put a multi-million-row delete inside exactly the minutes a
    # bettable window is open. Once per slow interval is enough: the tables
    # grow by one pass's worth at a time, and the window this trims to is days.
    # **Not while a window is open**, and the budget is why that is a
    # separate rule rather than a redundant one. `budget_s` is checked
    # between batches and one batch measures ~20s against the live table,
    # so a 5s budget really costs ~40s across the two tables -- measured
    # 2026-08-19, full passes going 50s -> 87s. That is affordable between
    # windows and is exactly the gap the fast cadence exists to close
    # while one is open. Retention has no deadline; a bettable minute does.
    if window_open:
        pruned = retention.PruneResult()
    else:
        pruned = retention.prune(conn, now=stamp)
    counts.quotes_pruned = pruned.quotes_deleted
    counts.unmatched_pruned = pruned.unmatched_deleted

    return run_pricing_pass(
        conn, events, risk=risk, suppression=suppression, now=stamp, counts=counts,
        day_start_hour=config.budget_day_start_utc_hour,
    )


# Said instead of an empty string, so a quote pass is never mistaken for a full
# pass that considered a sweep and declined. Those need opposite responses: one
# is working as designed, the other means the schedule has a problem.
QUOTE_PASS_SWEEP_DETAIL = "no sweep: quote refresh only (spends no odds credit)"


async def run_quote_pass(
    conn,
    kalshi_client,
    *,
    odds_client=None,
    budget=None,
    config: Optional[OddsConfig] = None,
    risk: Optional[RiskConfig] = None,
    suppression: Optional[SuppressionConfig] = None,
    now: Optional[int] = None,
    day_start_hour: int = DEFAULT_DAY_START_UTC_HOUR,
    manual: Sequence[ManualRefresh] = (),
) -> PassCounts:
    """Re-read Kalshi and re-price against the odds already stored.

    **Why this exists.** Two limits bound the actionable window and the tighter
    one decides it: the sportsbook consensus is good for `max_odds_age_ms`
    (900s) and the Kalshi quote for `max_kalshi_quote_age_ms` (30s). The loop
    wrote a row every 900s. So each row was bettable for **thirty seconds** and
    the tool was actionable for about a minute a day, not the fifteen minutes
    every document in this repo claimed. Neither limit is wrong; nothing
    computed their product.

    A quote pass is the cheap half of a full pass. It touches Kalshi, which is
    unmetered, and never The Odds API, which is the whole reason for the 900s
    interval. Run every ~20s while the window is open it keeps each row inside
    the 30s limit for the entire fifteen minutes the odds are good for, at a
    cost of zero credits.

    What it deliberately does not do: fetch closing lines, run the digest, or
    bootstrap a sport. `sweep_decision` says which of those applied rather than
    being left blank.

    **It now carries the odds refresh, and the arithmetic is why.** This pass
    used to spend nothing at all, and the docstring said so proudly: "this does
    not widen the window, fifteen minutes is set by `MAX_ODDS_AGE_S` and the
    credit budget". The budget half of that stopped being true on 2026-08-09
    (the 20K tier lifted the daily cap to 400 against a 6-credit sweep), which
    left the window narrow for no remaining reason.

    The refresh cannot ride the *full* pass instead, and this is the whole
    argument for putting a metered call on the cheap cadence. A refresh is only
    considered when a pass runs, so the worst-case age of the stored odds is
    `refresh_interval_ms + one pass interval`. On the 900s full cadence that is
    `600 + 900 = 1500s` against a 900s limit -- stale for two thirds of every
    cycle, which is the state we are trying to leave. On this cadence it is
    `600 + 15 = 615s`, comfortably inside. Running the full pass at 15s instead
    would fetch candlesticks for every started game 240 times an hour to no
    purpose, which is what split the cadences in the first place.

    What bounds the spend is `refresh_interval_ms`, not this interval: the pass
    asks on every tick and `decide_sweeps` answers "not yet" on all but one in
    forty. `budget.refusal_reason` is still checked before the call, so the
    ceiling that stops it is the same ceiling as everywhere else.

    **`manual` rides this cadence for the same reason the refresh does.** A tap
    is a person waiting on a screen, so serving it on the 900s full pass would
    mean up to fifteen minutes between the tap and the price. On this cadence it
    is at most one tick. It is passed straight through to `decide_sweeps`, which
    charges it against the same credits as everything else -- this pass does not
    read the inbox itself, because that would give the runner a second way to
    spend that no test of `fetch_and_store_odds` could see. `scripts/run_loop.py`
    reads it and holds the watermark.

    **Odds are refreshed only when all three of `odds_client`, `budget` and
    `config` are supplied.** They are optional so the many callers that only
    want a Kalshi re-price -- tests, `scripts/`, the demo -- keep working
    unchanged and, more importantly, keep being unable to spend money by
    accident. `scripts/run_loop.py` is what passes them.

    **`day_start_hour` is an explicit parameter here and is read off `config` in
    `run_once`.** This pass takes no `OddsConfig` -- it spends no credits, which
    is the point -- so there is nothing to derive the risk day from, and a
    default that silently disagrees with the order endpoint is exactly the
    defect being closed. `scripts/run_loop.py` passes the configured hour to
    both entry points; `config.assert_risk_day_start_agrees` refuses to start if
    the default left here has stopped matching what is deployed.
    """
    stamp = now if now is not None else now_ms()
    suppression = suppression or SuppressionConfig()
    counts = PassCounts(sweep_decision=QUOTE_PASS_SWEEP_DETAIL)
    # **The narrowed walk lives on this cadence and not on the full pass.** ADR
    # 0053: the full catalogue walk is 15.21s of transfer against 3.13s for the
    # scoped one, and at 15s intervals the difference is the whole CPU. The
    # full pass keeps walking everything, which is what finds a series this
    # list does not have yet.
    events = await run_kalshi_pass(
        conn, kalshi_client, now=stamp, counts=counts,
        log_discovery_summary=False,
        series_tickers=priceable_series(conn, now=stamp),
    )

    if odds_client is not None and budget is not None and config is not None:
        # Before pricing, not after: a refresh that landed this tick should be
        # what this tick's rows are priced against. Pricing first would publish
        # one pass's worth of rows against odds we had already replaced, and
        # that row would carry a staleness the database could not explain.
        sweeps, stored, decision = await fetch_and_store_odds(
            conn, odds_client, budget, events=events, config=config, now=stamp,
            max_odds_age_ms=suppression.max_odds_age_ms,
            allow_bootstrap=False,
            manual=manual,
        )
        counts.odds_sweeps = sweeps
        counts.odds_quotes_stored = stored
        counts.sweep_decision = decision.detail

    return run_pricing_pass(
        conn, events, risk=risk, suppression=suppression, now=stamp, counts=counts,
        day_start_hour=day_start_hour,
    )


def upsert_discovered(conn, events: Sequence[DiscoveredEvent], *, now: int) -> None:
    """Store series, events and markets. Idempotent across passes."""
    for event in events:
        conn.execute(
            "INSERT INTO kalshi_series (series_ticker, league, has_game_markets, "
            "first_seen_ms, last_seen_ms) VALUES (?, ?, 1, ?, ?) "
            "ON CONFLICT(series_ticker) DO UPDATE SET last_seen_ms = excluded.last_seen_ms",
            (event.series_ticker, event.league, now, now),
        )
        conn.execute(
            "INSERT INTO kalshi_events (event_ticker, series_ticker, title, "
            "category, commence_ms, close_ms, status, first_seen_ms, last_seen_ms) "
            "VALUES (?, ?, ?, 'Sports', ?, NULL, 'open', ?, ?) "
            "ON CONFLICT(event_ticker) DO UPDATE SET "
            "last_seen_ms = excluded.last_seen_ms, commence_ms = excluded.commence_ms",
            (
                event.event_ticker, event.series_ticker, event.title,
                event.commence_ms, now, now,
            ),
        )
        for market in event.markets:
            conn.execute(
                # `result` is COALESCEd, and that is the whole point of it being
                # here. Every market discovery sees is `active` with an empty
                # `result`, so `result = excluded.result` would erase, on the very
                # next pass, whatever `market_results.py` had just recorded --
                # silently, and only for markets whose event is still open, which
                # is the hardest possible version of that bug to notice.
                # An outcome is written once and never unwritten from this path.
                "INSERT INTO kalshi_markets (ticker, event_ticker, series_ticker, "
                "title, yes_side_team, market_type, strike, player_name, "
                "price_structure, close_ms, status, result, volume_24h, "
                "open_interest, first_seen_ms, last_seen_ms) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(ticker) DO UPDATE SET "
                "last_seen_ms = excluded.last_seen_ms, status = excluded.status, "
                "result = COALESCE(excluded.result, kalshi_markets.result), "
                "volume_24h = excluded.volume_24h, "
                "open_interest = excluded.open_interest",
                (
                    market.ticker, market.event_ticker, market.series_ticker,
                    market.title, market.yes_side, market.market_type,
                    market.strike, market.player_name,
                    market.price_structure, market.close_ms,
                    market.status, market.result, market.volume_24h,
                    market.open_interest, now, now,
                ),
            )
    conn.commit()
