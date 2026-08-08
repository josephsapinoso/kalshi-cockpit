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
- Only **moneyline** (`h2h`). Spreads and totals are stored by ingest and
  ignored by pricing, because they need per-`outcome_point` grouping and the
  model's margin distribution to price, and shipping them half-done would put
  rows in the evidence record that nothing can score.
- No orders. `suggested_contracts` is advice; the execution path is separate
  and stays behind the gate.
- Exposure is read from recorded fills, which is currently always zero because
  the order endpoint does not persist. That is a true zero, not an unreadable
  one -- see `current_exposure_dollars`.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Sequence

from .config import OddsConfig, RiskConfig
from .core.devig import DevigError, consensus_devig
from .core.suppression import SuppressionConfig
from .engine import (
    Candidate,
    build_recommendation,
    ensure_strategy_config,
    persist_if_changed,
)
from .kalshi.discovery import DiscoveredEvent, discover_from_events
from .match.linker import (
    MatchCandidate,
    TeamAliases,
    link_event,
    load_aliases,
    record_link,
    record_unmatched,
    resolve_outcome,
)
from .odds.budget import sweep_cost
from .odds.client import store_quotes
from .odds.timing import SweepDecision, decide_sweeps
from .store import db
from .store.db import ask_for_side, now_ms

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
    unchanged_skipped: int = 0
    dropped_no_books: int = 0
    dropped_no_kalshi_quote: int = 0
    dropped_unresolved_outcome: int = 0
    # Why the pass did or did not spend an odds credit, in words. A pass that
    # skips the sweep silently looks exactly like one that swept and found
    # nothing, and those two need opposite responses.
    sweep_decision: str = ""
    errors: list[str] = field(default_factory=list)

    # Always printed even when zero. "surfaced: 0" is the headline result of a
    # pass -- it is the answer this whole tool exists to produce, and hiding it
    # because it is falsy would make "found nothing" look like "did not check".
    ALWAYS_REPORT = ("recommendations", "surfaced", "suppressed", "sweep_decision")

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
        "SELECT bookmaker, outcome_name, price_decimal, book_updated_ms, fetched_ms "
        "FROM odds_snapshots "
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
    )


def write_fair_price(
    conn,
    *,
    link_id: int,
    devig_result,
    metadata: dict,
    computed_ms: int,
    market: str = MONEYLINE,
) -> dict[str, int]:
    """Persist one `fair_prices` row per outcome. Returns outcome -> row id.

    One row per outcome rather than one per market, because the conservative
    probability is *per side*: it is the lowest across methods for the side
    being bought, and the lowest for one team is not one minus the lowest for
    the other.
    """
    ids: dict[str, int] = {}
    methods = devig_result.all_methods()
    for index, outcome in enumerate(devig_result.outcomes):
        cursor = conn.execute(
            "INSERT INTO fair_prices (computed_ms, link_id, market, outcome_name, "
            "outcome_point, p_multiplicative, p_additive, p_power, p_shin, "
            "p_conservative, overround, market_width, book_count, books_used, "
            "anchored_on_sharp) "
            "VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                computed_ms, link_id, market, outcome,
                methods["multiplicative"][index], methods["additive"][index],
                methods["power"][index], methods["shin"][index],
                devig_result.conservative_probability(outcome),
                devig_result.overround, metadata.get("market_width"),
                metadata.get("book_count", 0),
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


def current_exposure_dollars(conn) -> float:
    """Open exposure from recorded fills, net of settlements.

    Returns a genuine `0.0` when nothing has been filled, which is the state
    today because the order endpoint does not yet persist. That is a legitimate
    zero and not an unreadable one -- "no fills" is a fact, unlike "the fills
    table could not be read". `size_position` refuses on `None`, so returning
    zero here is a claim, and it is a true one.
    """
    row = conn.execute(
        "SELECT COALESCE(SUM(f.count * f.price_tenths), 0) AS cost "
        "FROM fills f "
        "WHERE NOT EXISTS ("
        "  SELECT 1 FROM settlements s WHERE s.ticker = f.ticker"
        ")"
    ).fetchone()
    return float(row["cost"] or 0) / 1000.0


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

    for event in events:
        if event.sport_key not in cache:
            cache[event.sport_key] = load_aliases(event.sport_key)
        aliases = cache[event.sport_key]

        result = link_event(
            kalshi_event_ticker=event.event_ticker,
            kalshi_teams=event.teams,
            kalshi_commence_ms=event.commence_ms,
            candidates=_match_candidates(
                conn, event.sport_key, since_ms=now - 86_400_000
            ),
            aliases=aliases,
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
                # The team names as seen, because this queue exists to be
                # turned into alias-file entries by hand.
                detail=" vs ".join(event.teams) or event.title,
                reason=result.reason or "no_counterpart",
            )

    return linked


def run_pricing_pass(
    conn,
    events: Sequence[DiscoveredEvent],
    *,
    risk: Optional[RiskConfig] = None,
    suppression: Optional[SuppressionConfig] = None,
    now: Optional[int] = None,
    counts: Optional[PassCounts] = None,
) -> PassCounts:
    """Devig what is stored and write recommendations. Touches no network.

    Both sides of every moneyline are judged, not just the one that looks cheap.
    A candidate with no edge is the normal answer and is still recorded: it is a
    scored observation on the closing line, which is what makes 300 of them
    reachable without placing 300 bets.
    """
    stamp = now if now is not None else now_ms()
    risk = risk or RiskConfig()
    suppression = suppression or SuppressionConfig()
    counts = counts or PassCounts()

    version = ensure_strategy_config(
        conn,
        {
            "suppression": suppression.__dict__,
            "kelly_fraction": risk.kelly_fraction,
            "prices": "moneyline only",
            # Part of the config so a change to the recording rule mints a new
            # strategy version and the record segments on it, rather than
            # silently mixing two regimes in one dataset.
            "record": "skip consecutive identical (ask, fair) per side",
        },
        "chain runner configuration",
        now=stamp,
    )
    exposure = current_exposure_dollars(conn)

    alias_cache: dict[str, TeamAliases] = {}
    linked = link_discovered_events(conn, events, now=stamp, alias_cache=alias_cache)
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

        books = book_quotes_for_event(conn, odds_event_id, now=stamp)
        if books is None:
            counts.dropped_no_books += 1
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
                    created_ms=stamp,
                )
                if persist_if_changed(conn, recommendation) is None:
                    # Same ask, same fair value as the last row for this side.
                    # Re-recording it would add a row and no information.
                    counts.unchanged_skipped += 1
                    continue

                counts.recommendations += 1
                if recommendation.surfaced:
                    counts.surfaced += 1
                elif recommendation.suppressed_reason:
                    counts.suppressed += 1

    logger.info("pricing pass: %s", counts.as_dict())
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
) -> tuple[int, int, SweepDecision]:
    """Sweep only when the window it opens will be worth having.

    On a free tier of ~16 credits a day against a `markets x regions` cost of 6
    this is two calls, and each one makes the slate bettable for exactly
    `max_odds_age_ms`. `decide_sweeps` spends them just before a cluster of
    kickoffs rather than on whichever pass happened to run first; the decision,
    including the decision *not* to sweep, comes back so the pass can report it.
    """
    decision = decide_sweeps(
        conn,
        in_scope=soonest_by_sport(events),
        budget=budget,
        cost=sweep_cost(config.markets, config.regions),
        now_ms=now,
        max_odds_age_ms=max_odds_age_ms,
    )
    logger.info("sweep decision: %s", decision.detail)

    sweeps = stored = 0
    for firing in decision.fire:
        quotes = await odds_client.fetch_odds(firing.sport_key, now_ms=now)
        if not quotes:
            # Over budget, or nothing on the slate. Both are normal operating
            # states, which is why `fetch_odds` returns [] rather than raising.
            continue
        sweeps += 1
        stored += store_quotes(conn, quotes)
    return sweeps, stored, decision


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

    # `events()` is an async *generator* -- it paginates lazily -- so it is
    # consumed rather than awaited.
    raw_events = [e async for e in kalshi_client.events(with_nested_markets=True)]
    events = discover_from_events(raw_events)
    upsert_discovered(conn, events, now=stamp)
    counts.markets_quoted = store_quotes_from_discovery(conn, events, now=stamp)

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
) -> PassCounts:
    """One full pass: ingest, then price. The unit the scheduler repeats."""
    stamp = now if now is not None else now_ms()
    suppression = suppression or SuppressionConfig()
    events, counts = await run_ingest_pass(
        conn, kalshi_client, odds_client, budget, config=config, now=stamp,
        suppression=suppression,
    )
    return run_pricing_pass(
        conn, events, risk=risk, suppression=suppression, now=stamp, counts=counts
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
                "INSERT INTO kalshi_markets (ticker, event_ticker, series_ticker, "
                "title, yes_side_team, market_type, strike, price_structure, "
                "close_ms, status, volume_24h, open_interest, first_seen_ms, "
                "last_seen_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(ticker) DO UPDATE SET "
                "last_seen_ms = excluded.last_seen_ms, status = excluded.status, "
                "volume_24h = excluded.volume_24h, "
                "open_interest = excluded.open_interest",
                (
                    market.ticker, market.event_ticker, market.series_ticker,
                    market.title, market.yes_side, market.market_type,
                    market.strike, market.price_structure, market.close_ms,
                    market.status, market.volume_24h, market.open_interest,
                    now, now,
                ),
            )
    conn.commit()
