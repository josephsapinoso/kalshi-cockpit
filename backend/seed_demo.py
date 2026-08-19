"""Deterministic synthetic data, for development and for the public demo.

Serves two purposes that turn out to be the same job:

**Development outside market hours.** Sports markets are not always open, and
the odds budget is 500 credits a month. Building a UI against live data would
mean either waiting for a slate or burning credits on cosmetics.

**The public demo instance.** The repo is meant to go public, and a demo that
anyone can click through is worth far more than screenshots. `seed_demo` is
what lets the demo deploy run with **no credentials, no network, and no
execution path** while still looking like the real thing.

Everything is generated from a fixed seed, so the Board looks identical on
every run and a screenshot stays accurate. The numbers are drawn to resemble
what the engine actually produces -- which, importantly, means **mostly no
edge, a handful of suppressions, and only one or two surfaced bets**. A demo
showing a screen full of profitable opportunities would misrepresent the tool.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .analysis.clv import DEFAULT_HORIZON_HOURS
from .config import RiskConfig
from .core.devig import DevigError, consensus_devig, devig
from .core.suppression import SuppressionConfig, evaluate_suppression
from .runner import SHARP_BOOKS, write_fair_price
from .odds.budget import day_start_ms
from .odds.timing import first_window_open_of_day
from .engine import (
    Candidate,
    build_recommendation,
    ensure_strategy_config,
    persist_recommendation,
)
from .store import db
from .store.orders import DEPTH_CAPPED_TAKER

DEFAULT_SEED = 1337

# The caps the demo deploy actually runs under, restated here rather than
# loaded, and pinned to `fly.demo.toml` by
# `tests/test_demo_sizes_at_deployed_caps.py`.
#
# **This is a decision with a cost, so it is written down rather than left to
# look like an oversight.** Until 2026-08-18 this was a bare `RiskConfig()` --
# the dataclass defaults, a $1,000 bankroll -- and the public demo sized every
# card at a configuration no instance deploys. On the row the demo served, the
# card read `Buy 17` / `$8.85` where the deployed caps give **1 contract /
# $0.52**: 17x, on the URL that is the portfolio piece. The binding constraint
# was Kelly off the bankroll, not `MAX_POSITION_DOLLARS` -- $8.85 fits *under*
# the deployed $10 position cap, so no cap check could have caught it.
#
# The obvious repair is `RiskConfig.load()`, and it was rejected. This module's
# docstring promises "the Board looks identical on every run and a screenshot
# stays accurate", and `.load()` reads the environment: correct on Fly, back to
# the $1,000 defaults on any laptop with no env set. That is the same class of
# defect wearing the fix's clothes -- a demo whose numbers depend on where it
# was run.
#
# So the numbers are duplicated, deliberately, and the duplication is the thing
# under test. `test_the_seeded_caps_match_the_deployed_ones` fails if these and
# `fly.demo.toml` ever disagree, in either direction.
#
# `kelly_fraction` and `max_order_contracts` are stated too: they are strategy
# parameters rather than facts about the account, and leaving them to the
# dataclass is how the four dollar caps got left in the first place.
DEMO_RISK = RiskConfig(
    bankroll_dollars=100.0,
    kelly_fraction=0.25,
    max_order_contracts=50,
    max_position_dollars=10.0,
    max_exposure_dollars=40.0,
    max_daily_loss_dollars=10.0,
)

# A plausible mid-August slate: MLB in season, WNBA in season, NFL preseason
# listing ahead. Matches what the discovery spike actually found.
_FIXTURES = [
    ("KXMLBGAME", "Pro Baseball", "Houston", "San Diego", 1.80, 2.10),
    ("KXMLBGAME", "Pro Baseball", "New York Y", "Boston", 2.05, 1.85),
    ("KXMLBGAME", "Pro Baseball", "Los Angeles D", "San Francisco", 1.62, 2.45),
    ("KXMLBGAME", "Pro Baseball", "Chicago C", "Milwaukee", 2.20, 1.72),
    ("KXMLBGAME", "Pro Baseball", "Atlanta", "Philadelphia", 1.95, 1.95),
    ("KXWNBAGAME", "Pro Basketball (W)", "Las Vegas", "Seattle", 1.55, 2.60),
    ("KXWNBAGAME", "Pro Basketball (W)", "New York L", "Connecticut", 1.88, 1.98),
    ("KXNFLGAME", "Pro Football", "Kansas City", "Denver", 1.45, 2.85),
    ("KXNFLGAME", "Pro Football", "Philadelphia", "Dallas", 1.90, 1.98),
    # The two thin-book fixtures. Added because the demo's suppression
    # vocabulary and the live one were disjoint on precisely these codes: the
    # real record (1,564 rows, 2026-08-10) is dominated by `stale_odds`,
    # `too_few_books,no_market_width` and their composite, and the demo produced
    # `too_few_books` and `no_market_width` *never* while producing
    # `wide_market` -- which is 0 of 1,564 live -- sixty-five times.
    ("KXMLBGAME", "Pro Baseball", "Seattle", "Texas", 1.98, 1.92),
    ("KXWNBAGAME", "Pro Basketball (W)", "Phoenix", "Indiana", 1.70, 2.25),
]


@dataclass(frozen=True)
class SeededScenario:
    """One market, plus the deviation from fair that makes it interesting."""

    ticker: str
    event_ticker: str
    series: str
    league: str
    team: str
    opponent: str
    odds: tuple[float, float]
    ask_offset_tenths: int      # how far Kalshi sits from consensus fair
    quote_age_ms: int
    depth: float
    # `None` is a real state, not a missing value: `consensus_devig` reports no
    # width when fewer than two books contributed, and `no_market_width` exists
    # to refuse it rather than read it as perfect agreement. Every seeded
    # scenario carried a float until 2026-08-11, so the demo could not produce
    # the code at all.
    market_width: Optional[float]
    book_count: int
    # How long ago the books moved. Carried on the scenario rather than drawn
    # at the call site so the seeded `odds_snapshots` rows and the seeded
    # recommendation agree about it: a demo whose stored books say six minutes
    # while its Board says forty seconds is demonstrating a bug.
    odds_age_ms: int = 240_000


def _scenarios(rng: random.Random) -> list[SeededScenario]:
    """Build a slate whose shape resembles reality.

    Most candidates have no edge. A few are suppressed for concrete, different
    reasons. One or two are genuinely actionable. Anything more generous would
    be a misleading demo.
    """
    out: list[SeededScenario] = []
    # (offset, quote_age, depth, width, books, odds_age) -- one entry per
    # fixture, hand-chosen so each suppression rule is represented exactly once.
    # Odds ages sit inside the 15-minute freshness limit except for the last,
    # which demonstrates `stale_odds` -- the rule that closes the actionable
    # window, and the one a visitor is most likely to hit on the live tool.
    #
    # **The reason strings are never written here.** Every entry is a set of
    # *inputs*; `evaluate_suppression` decides the code, so a rule that is
    # renamed or re-thresholded moves the demo with it instead of leaving the
    # seeder asserting a vocabulary the engine has stopped using.
    shapes = [
        (-35, 3_000, 800.0, 0.012, 5, 120_000),    # surfaced: genuine ~3.5c edge
        (+40, 4_000, 600.0, 0.010, 5, 180_000),    # no edge -- Kalshi above fair
        (-260, 5_000, 400.0, 0.014, 4, 200_000),   # suspicious_edge
        (-38, 900_000, 700.0, 0.011, 5, 240_000),  # stale_kalshi_quote
        (-33, 3_500, 4.0, 0.013, 5, 150_000),      # insufficient_depth
        (-36, 4_500, 500.0, 0.220, 4, 300_000),    # wide_market
        (-8, 6_000, 300.0, 0.015, 5, 260_000),     # edge_within_method_noise
        (-30, 3_000, 900.0, 0.009, 6, 90_000),     # surfaced: genuine edge
        (-31, 3_000, 500.0, 0.010, 5, 1_500_000),  # stale_odds: window closed
        # One book, so `consensus_devig` could not measure a width. Fires
        # `too_few_books` AND `no_market_width` together -- the second-largest
        # composite in the live record (73 of 1,564) and a shape the demo could
        # not previously produce at all, which left `string_split` in
        # `mart_suppression_audit.sql` and `.split(",")` in `routes.py` exercised
        # only against single tokens.
        (-34, 3_200, 700.0, None, 1, 200_000),     # too_few_books + no_market_width
        # The same thinness on a slate whose books have also aged out. Three
        # codes in one string, which is the *largest* composite live (137 of
        # 1,564) and the shape that a `NOT IN ('stale_odds', ...)` predicate
        # silently fails to exclude.
        (-32, 3_400, 650.0, None, 1, 1_800_000),   # + stale_odds
    ]
    for (series, league, team, opp, o1, o2), shape in zip(_FIXTURES, shapes):
        offset, age, depth, width, books, odds_age = shape
        date_code = f"26AUG{rng.randint(8, 28):02d}"
        abbr = f"{team[:3].upper()}{opp[:3].upper()}"
        event_ticker = f"{series}-{date_code}{abbr}"
        out.append(
            SeededScenario(
                ticker=f"{event_ticker}-{team[:3].upper()}",
                event_ticker=event_ticker,
                series=series,
                league=league,
                team=team,
                opponent=opp,
                odds=(o1, o2),
                ask_offset_tenths=offset,
                quote_age_ms=age,
                depth=depth,
                market_width=width,
                book_count=books,
                odds_age_ms=odds_age,
            )
        )
    return out


# Real bookmaker keys, in the order `consensus_devig` prefers them. Named
# rather than invented: the demo is a portfolio piece, and a made-up book would
# be the one detail a reader who knows the space would notice.
_DEMO_BOOKS = (
    "pinnacle", "draftkings", "fanduel", "betmgm", "caesars", "betrivers",
)


def _seed_link_and_fair_price(
    conn, *, scenario, quotes_by_book, computed_ms: int
) -> tuple[int, Optional[int]]:
    """An `event_links` row and the `fair_prices` rows it anchors.

    **Seeded because a screen that reads them is now shipped.** Until
    `/api/slate` existed, `link_id` and `fair_price_id` were passed as `None`
    here and nothing rendered them, so the omission cost nothing. The Slate
    screen shows `market_width`, `book_count`, `anchored_on_sharp` and a
    per-book distribution, and every one of them would have been blank on the
    demo -- which is the only instance anyone can look at, and the one the
    `sharp-bettor` reviews are conducted against. A demo that renders a
    feature's entire content as "--" misrepresents the feature more completely
    than showing nothing at all would.

    **The consensus is computed from the seeded books rather than invented.**
    `consensus_devig` is the production function, run over the same quotes
    `_seed_books` wrote, so `market_width` and `book_count` on the demo are
    real consequences of the seeded prices. Transcribing plausible values
    instead would make the demo agree with live by coincidence and drift the
    moment either changes -- the failure `_LIVE_SUPPRESSION_MIX` above is
    written to avoid, in a different column.

    Returns `(link_id, fair_price_id_for_the_team_side, consensus_result)`.

    **The `DevigResult` comes back out, and that is not a convenience.** The
    caller prices the recommendation from it. Until 2026-08-19 the caller ran a
    *second*, single-pair `devig()` over `scenario.odds` and priced from that,
    while `fair_price_id` pointed here -- so every seeded row carried a
    `fair_probability` that disagreed with its own `p_conservative`, on all 11
    rows, by up to 0.35 probability points. Production cannot do this:
    `runner.py:936` passes the same `devig_result` it wrote to `fair_prices`.
    The mismatch was invisible until a screen rendered the four methods beside
    the fair value and their minimum contradicted it.
    """
    cursor = conn.execute(
        "INSERT INTO event_links (kalshi_event_ticker, odds_event_id, league, "
        "method, commence_skew_ms, linked_ms) VALUES (?, ?, ?, 'seeded', 0, ?)",
        (
            scenario.event_ticker,
            f"odds-{scenario.event_ticker}",
            scenario.league,
            computed_ms,
        ),
    )
    link_id = int(cursor.lastrowid)

    outcomes = [scenario.team, scenario.opponent]
    try:
        result, metadata = consensus_devig(
            outcomes, quotes_by_book, sharp_books=SHARP_BOOKS
        )
    except DevigError:
        # A scenario whose seeded prices cannot be devigged is a real state and
        # not a reason to abort the seed. The link still exists; the row simply
        # carries no fair price, which is what a live row in that condition
        # looks like.
        return link_id, None, None

    ids = write_fair_price(
        conn,
        link_id=link_id,
        devig_result=result,
        metadata=metadata,
        computed_ms=computed_ms,
    )
    return link_id, ids.get(scenario.team), result


def _seed_quote_history(conn, *, ticker: str, ask_tenths: int, stamp: int, rng) -> int:
    """A short run of `kalshi_quotes`, so the Slate's drift column has inputs.

    `kalshi_drift` needs at least two observations inside its window and reads
    the oldest and the newest. The demo previously wrote **no** `kalshi_quotes`
    rows at all, so every drift cell would have rendered `--` -- and `--` on a
    demo reads as "this feature does nothing" rather than "this instance has no
    history yet".

    Quotes are stored as the **NO bid**, and the YES ask is derived from it at
    read time by `ask_for_side`. Storing a YES ask directly would put a derived
    number in the column the derivation reads from, which is the one thing
    `store/schema.sql`'s header forbids: asks are derived, never stored.
    """
    stored = 0
    # Oldest first, walking toward the current ask, so the drift the screen
    # prints is a real difference between two stored observations rather than a
    # number the seeder chose. Direction alternates by ticker so the demo shows
    # both a drifting-up and a drifting-down market.
    drift = rng.choice((-18, -7, 6, 15))
    for index, minutes_ago in enumerate((45, 30, 15, 0)):
        # Walk the ask from `ask - drift` to `ask`, then store the NO bid that
        # implies it: yes_ask = 1000 - no_bid.
        step = ask_tenths - drift + int(round(drift * index / 3))
        step = max(10, min(990, step))
        conn.execute(
            "INSERT INTO kalshi_quotes (ticker, observed_ms, confirmed_ms, "
            "source, yes_bid_tenths, yes_bid_qty, no_bid_tenths, no_bid_qty) "
            "VALUES (?, ?, ?, 'rest', ?, ?, ?, ?)",
            (
                ticker,
                stamp - minutes_ago * 60_000,
                # Confirmed when observed. The demo writes a walk of distinct
                # prices, so no row here is ever a re-confirmation of the one
                # before it -- ADR 0055's unchanged path has nothing to model.
                stamp - minutes_ago * 60_000,
                max(10, step - 10),
                float(rng.randint(50, 500)),
                1000 - step,
                float(rng.randint(50, 500)),
            ),
        )
        stored += 1
    return stored


def _seed_books(conn, *, scenario, commence_ms: int, fetched_ms: int, rng) -> int:
    """Store the sportsbook quotes the consensus was built from.

    Seeded because the actionable window is measured from them. Without these
    rows `/api/window` correctly reports that no fixture has odds, and the demo
    would show a permanently closed window beside a Board full of prices --
    which is not what the live tool does, and is the sort of contradiction a
    demo exists to avoid.

    Each book's `book_updated_ms` is jittered *older* than the fixture's stated
    age, never newer. A consensus is only as fresh as its stalest book, so
    scattering the other side would make the seeded fixture read fresher than
    the number the Board prints beside it.
    """
    stored = 0
    # Returned alongside the count so the caller can devig exactly what was
    # written. Re-reading it from the database would work and would also be a
    # second query answering a question this function already knows.
    quotes_by_book: dict[str, list[float]] = {}
    for book in _DEMO_BOOKS[: scenario.book_count]:
        jitter = rng.randint(0, 20_000)
        for name, price in zip(
            (scenario.team, scenario.opponent), scenario.odds
        ):
            jittered = round(price * (1.0 + rng.uniform(-0.01, 0.01)), 3)
            conn.execute(
                "INSERT INTO odds_snapshots (fetched_ms, book_updated_ms, "
                "sport_key, odds_event_id, commence_ms, home_team, away_team, "
                "bookmaker, market, outcome_name, price_decimal) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'h2h', ?, ?)",
                (
                    fetched_ms, fetched_ms - jitter,
                    _SPORT_KEYS.get(scenario.league, "baseball_mlb"),
                    f"odds-{scenario.event_ticker}", commence_ms,
                    scenario.team, scenario.opponent, book, name,
                    jittered,
                ),
            )
            # Positional, matching `consensus_devig`'s contract: it pairs prices
            # to outcomes by index, so a dict keyed on name here would let the
            # two teams' probabilities swap silently and produce entirely
            # plausible numbers. Same hazard `book_quotes_for_event` names.
            quotes_by_book.setdefault(book, []).append(jittered)
            stored += 1
    return stored, quotes_by_book


# How often each *input condition* holds in `seed_history`, chosen so the codes
# `evaluate_suppression` writes resemble the live record rather than a vocabulary
# only the demo has ever spoken.
#
# The target is `docs/measurements/2026-08-10-clean-shortfall-pull.json`, 1,564
# rows off the money instance:
#
#     616  'stale_odds'
#     614   None
#     137  'stale_odds,too_few_books,no_market_width'
#      73  'too_few_books,no_market_width'
#      66  'stale_odds,suspicious_edge'
#       0  'wide_market'
#
# and the seeder previously produced the near-inverse: `wide_market` 65 times,
# `too_few_books` and `no_market_width` never, and **no composite at all** -- so
# the `unnest(string_split(suppressed_reason, ','))` in
# `warehouse/models/marts/mart_suppression_audit.sql` and the `.split(",")` at
# `backend/api/routes.py` were exercised only against single tokens. That gap
# has already produced one wrong answer: a preregistered `NOT IN (...)`
# predicate matched the wrong population because a composite is not any of its
# parts (`docs/measurements/2026-08-09-preregistration-clv-signal-test.md`).
#
# These are **rates on inputs, not on outputs**, deliberately. Naming the output
# distribution would mean naming the codes, and the codes are the engine's to
# decide -- the point of the fix is that a renamed or re-thresholded rule drags
# the demo along with it. The consequence is that the marginals only approximate
# the table above (three independent draws cannot reproduce an arbitrary joint),
# which is the right trade: a demo that *resembles* live through the real rules
# beats one that matches it by transcription.
#
# `wide_market` is absent from the drawn widths for the same reason it is absent
# live: every width drawn sits under `max_market_width`. The Board slate still
# carries exactly one, because that slate is a teaching set with each rule shown
# once, and one row is not sixty-five.
_LIVE_SUPPRESSION_MIX = {
    "stale_odds": 0.53,       # 616 + 137 + 66 of 1,564 carry it
    "thin_books": 0.15,       # 137 + 73 of 1,564 carry the thin-consensus pair
    "suspicious_edge": 0.08,  # 66 of 1,564, plus the composites it appears in
}


_SPORT_KEYS = {
    "Pro Baseball": "baseball_mlb",
    "Pro Basketball (W)": "basketball_wnba",
    "Pro Football": "americanfootball_nfl",
}


def seed_all(
    db_path: Path | str, *, seed: int = DEFAULT_SEED, now_ms: int | None = None
) -> dict[str, int]:
    """Populate a fresh database. Returns row counts, for verification."""
    rng = random.Random(seed)
    conn = db.init_db(db_path)
    # A fixed clock so the Board renders identically on every run -- otherwise
    # "quote 3s old" drifts and screenshots rot.
    stamp = now_ms if now_ms is not None else 1_754_800_000_000

    # Reset before seeding. Without this, restarting the demo server appends a
    # second copy of every row: the Board showed each fixture twice and the
    # counts read 18 for a nine-fixture slate. "Deterministic" has to mean the
    # database ends in the same state, not merely that the generator does.
    # Child tables first -- foreign keys are enforced.
    #
    # **The order was wrong and it could only fail on a database that had been
    # used.** `recommendations` came first, but `orders.recommendation_id`
    # references it, so re-seeding over a database carrying orders raised
    # `FOREIGN KEY constraint failed` on the very first DELETE. Every test builds
    # a fresh database and `seed_all` writes no orders itself, so the only way to
    # reach it was to run `seed_history` and then re-seed -- which is exactly
    # what a developer refreshing a local demo does, and nothing else does.
    #
    # Ordered by the actual reference graph, deepest child first:
    #   fills -> orders, settlements -> orders, orders -> recommendations,
    #   recommendations -> {closing_lines, fair_prices, event_links},
    #   fair_prices -> event_links, event_links -> kalshi_events.
    for table in (
        "fills", "settlements", "orders", "recommendations", "closing_lines",
        "fair_prices", "event_links", "unmatched_events", "kalshi_quotes",
        "odds_snapshots", "api_credits", "model_ratings", "lessons",
        "kalshi_markets", "kalshi_events", "kalshi_series", "strategy_configs",
    ):
        conn.execute(f"DELETE FROM {table}")
    conn.commit()

    risk = DEMO_RISK
    suppression = SuppressionConfig()
    version = ensure_strategy_config(
        conn,
        {"suppression": suppression.__dict__, "kelly_fraction": risk.kelly_fraction},
        "seeded demo configuration",
        now=stamp,
    )

    counts = {
        "markets": 0, "recommendations": 0, "surfaced": 0, "suppressed": 0,
        "odds_quotes": 0,
    }

    for index, scenario in enumerate(_scenarios(rng)):
        commence = stamp + (index + 2) * 3_600_000

        conn.execute(
            "INSERT OR IGNORE INTO kalshi_series (series_ticker, league, "
            "has_game_markets, first_seen_ms, last_seen_ms) VALUES (?, ?, 1, ?, ?)",
            (scenario.series, scenario.league, stamp, stamp),
        )
        conn.execute(
            "INSERT OR IGNORE INTO kalshi_events (event_ticker, series_ticker, "
            "title, category, commence_ms, close_ms, status, first_seen_ms, "
            "last_seen_ms) VALUES (?, ?, ?, 'Sports', ?, ?, 'open', ?, ?)",
            (
                scenario.event_ticker, scenario.series,
                f"{scenario.team} vs {scenario.opponent}",
                commence, commence + 4 * 3_600_000, stamp, stamp,
            ),
        )

        conn.execute(
            "INSERT OR IGNORE INTO kalshi_markets (ticker, event_ticker, "
            "series_ticker, title, yes_side_team, market_type, price_structure, "
            "close_ms, status, volume_24h, open_interest, first_seen_ms, "
            "last_seen_ms) VALUES (?, ?, ?, ?, ?, 'moneyline', 'linear_cent', "
            "?, 'open', ?, ?, ?, ?)",
            (
                scenario.ticker, scenario.event_ticker, scenario.series,
                f"{scenario.team} vs {scenario.opponent} Winner?", scenario.team,
                commence + 4 * 3_600_000,
                float(rng.randint(2_000, 40_000)), float(rng.randint(500, 9_000)),
                stamp, stamp,
            ),
        )
        counts["markets"] += 1
        stored_quotes, quotes_by_book = _seed_books(
            conn,
            scenario=scenario,
            commence_ms=commence,
            fetched_ms=stamp - scenario.odds_age_ms,
            rng=rng,
        )
        counts["odds_quotes"] += stored_quotes

        # The link and the fair price the Slate screen reads. Written after the
        # books because they are computed *from* them.
        link_id, fair_price_id, consensus = _seed_link_and_fair_price(
            conn,
            scenario=scenario,
            quotes_by_book=quotes_by_book,
            computed_ms=stamp,
        )

        # **Price the row off the consensus that was just written, not off a
        # second devig of its own.** These two lines used to run *above* the
        # market insert, over `scenario.odds` as a single pair, while
        # `fair_price_id` pointed at the multi-book consensus below -- so the
        # recommendation's `fair_probability` and its own `p_conservative`
        # disagreed on every seeded row. `runner.py:936` passes production the
        # same `DevigResult` it wrote; this now does too, and
        # `tests/test_seed_demo.py` fails if they ever come apart again.
        #
        # The fallback is the old single-pair devig, and it is the honest one:
        # it runs only where `consensus_devig` refused, which is exactly the
        # state in which there is no `fair_price_id` and so nothing to
        # contradict.
        fair = consensus or devig(
            [scenario.team, scenario.opponent], list(scenario.odds)
        )
        fair_p = fair.conservative_probability(scenario.team)
        ask = int(round(fair_p * 1000)) + scenario.ask_offset_tenths
        ask = max(10, min(990, ask))
        counts["kalshi_quotes"] = counts.get("kalshi_quotes", 0) + (
            _seed_quote_history(
                conn, ticker=scenario.ticker, ask_tenths=ask, stamp=stamp, rng=rng
            )
        )

        recommendation = build_recommendation(
            Candidate(
                ticker=scenario.ticker,
                side="yes",
                outcome_name=scenario.team,
                ask_tenths=ask,
                depth_at_ask=scenario.depth,
                kalshi_quote_age_ms=scenario.quote_age_ms,
                link_id=link_id,
                fair_price_id=fair_price_id,
                devig=fair,
                book_count=scenario.book_count,
                market_width=scenario.market_width,
                odds_age_ms=scenario.odds_age_ms,
                commence_skew_ms=rng.randint(-300_000, 300_000),
            ),
            risk=risk,
            suppression=suppression,
            strategy_config_version=version,
            # A clean book, stated rather than defaulted. The demo database has
            # no orders and no settlements, so all three are genuinely zero --
            # and after 2026-08-10 the sizer has no defaults to fall back on,
            # deliberately: an omission here would be indistinguishable from the
            # production omission that let a -$20,000 account place an order.
            current_exposure_dollars=0.0,
            current_position_dollars=0.0,
            daily_pnl_dollars=0.0,
            # One instant for the whole slate. A pass prices every candidate it
            # has and writes them together, so staggering these by a minute each
            # misrepresented how the record is actually made -- and, now that
            # the Board recomputes staleness from `created_ms`, it aged half the
            # demo out of the actionable list for no reason that exists in the
            # real system.
            created_ms=stamp,
        )
        persist_recommendation(conn, recommendation)
        counts["recommendations"] += 1
        if recommendation.surfaced:
            counts["surfaced"] += 1
        elif recommendation.suppressed_reason:
            counts["suppressed"] += 1

    # The spend behind those quotes. Without it the window panel would report
    # a full day's budget beside odds that were obviously fetched, and the two
    # halves of the same screen would contradict each other.
    #
    # **Both sweeps have to land inside the same budget day**, and an age
    # measured from `now` does not guarantee that: the budget day rolls at
    # 10:00Z, so a sweep five hours back falls into *yesterday* whenever the
    # seed runs between 10:00Z and 15:00Z. The panel then showed 6 of 16 spent
    # beside two sweeps' worth of odds -- the exact contradiction this block
    # exists to prevent, appearing for five hours out of twenty-four.
    #
    # So the older sweep is placed relative to the **day boundary** rather than
    # relative to now, which is also what a real instance's record looks like
    # at that hour: the previous day's sweeps have rolled off and today's are
    # all after 10:00Z.
    # **And the sweep must also land after a window it could have been served
    # in.** Pinning it to `day_start + 60_000` alone put the seeded spend at
    # 10:01Z, which no scheduler on this system would ever produce: windows open
    # 75 minutes before a cluster's first pitch, never at the accounting
    # boundary. The record was internally consistent about *budget* and
    # impossible about *schedule*, and the demo is the instance a reader is
    # invited to trust. It is also the instance on which the sweep banner's
    # states are exercised, and a sweep that predates every window makes the
    # pre-window state unreachable there.
    #
    # 900_000 is `MAX_ODDS_AGE_S = "900"` as deployed in both tomls. Passed
    # explicitly rather than read from config because a seed that changes shape
    # with the environment is not a fixture.
    # The floor moves up to the first window **only when that window has already
    # opened**. Seeding at 11:00Z against a 20:50Z window would otherwise write a
    # credit row dated nine hours in the future -- a worse record than the one
    # being corrected, and one that would make `last_sweep_ms` newer than
    # `now_ms` on a screen built to compare exactly those two. In that case the
    # seed keeps the old boundary floor and the strip renders its pre-window
    # state, which is now calm and correct rather than a false warning.
    day_start = day_start_ms(stamp)
    first_window = first_window_open_of_day(
        conn, day_start_ms=day_start, max_odds_age_ms=900_000
    )
    floor_ms = day_start + 60_000
    if first_window is not None and first_window <= stamp:
        floor_ms = first_window
    for sport, age_ms in (("baseball_mlb", 120_000), ("basketball_wnba", 5 * 3_600_000)):
        called_ms = min(max(stamp - age_ms, floor_ms), stamp)
        conn.execute(
            "INSERT INTO api_credits (called_ms, endpoint, sport_key, markets, "
            "regions, cost, remaining_reported, used_reported) "
            "VALUES (?, '/odds', ?, 'h2h,spreads,totals', 'us,eu', 6, 388, 112)",
            (called_ms, sport),
        )
    counts["odds_sweeps"] = 2

    # **The demo has to claim a live recorder, and since ADR 0055 that is a
    # separate fact from the quote rows.** Health reads a `meta` heartbeat now,
    # not the newest row in `kalshi_quotes`, so a seed that writes quotes and no
    # heartbeat reports a recorder that has never run -- which is what the demo
    # exists to *not* look like.
    db.set_recorder_heartbeat(conn, stamp)

    conn.commit()
    conn.close()
    return counts


def seed_history(
    db_path: Path | str,
    *,
    n: int = 420,
    seed: int = DEFAULT_SEED,
    now_ms: int | None = None,
) -> dict[str, int]:
    """Add a back-record of scored, settled recommendations.

    Needed because the analytical marts and their dbt tests are vacuous
    without history -- a test over an empty table passes for the wrong reason.

    **Outcomes are drawn at exactly the implied probability**, so the synthetic
    history contains *no edge whatsoever*. That is the honest choice: it means
    the demo shows the measurement harness correctly reporting "nothing here",
    which is what the harness is for. Seeding a profitable history would make
    the dashboards look impressive and would be a lie.
    """
    rng = random.Random(seed + 1)
    conn = db.init_db(db_path)
    stamp = now_ms if now_ms is not None else 1_754_800_000_000
    # The same defaults `seed_all` hashed into the seeded `strategy_configs`
    # row, so the history and the slate are one strategy rather than two.
    suppression = SuppressionConfig()

    version = conn.execute(
        "SELECT version FROM strategy_configs ORDER BY version DESC LIMIT 1"
    ).fetchone()
    version = int(version["version"]) if version else 1

    counts = {"recommendations": 0, "closing_lines": 0, "settlements": 0}

    for i in range(n):
        ticker = f"KXHIST-{i:04d}"
        created = stamp - (i + 1) * 3_600_000

        conn.execute(
            "INSERT OR IGNORE INTO kalshi_markets (ticker, first_seen_ms, "
            "last_seen_ms) VALUES (?, ?, ?)",
            (ticker, created, created),
        )

        ask = rng.choice([180, 250, 320, 410, 480, 520, 590, 660, 730, 820])
        side = "yes"
        # No edge: the outcome is a draw at the price paid.
        won = rng.random() < ask / 1000

        # The close drifts randomly around the entry. Zero mean = no CLV.
        close_mid = max(20, min(980, ask + rng.gauss(0, 45)))

        # Three independent input axes, then `evaluate_suppression` names the
        # codes. See `_LIVE_SUPPRESSION_MIX` for the rates and where they came
        # from. The composites fall out of the conjunction rather than being
        # spelled: `stale` and `thin` together produce
        # `stale_odds,too_few_books,no_market_width`, which is the largest
        # composite in the live record and a string this seeder could not
        # previously write at all.
        stale = rng.random() < _LIVE_SUPPRESSION_MIX["stale_odds"]
        thin = rng.random() < _LIVE_SUPPRESSION_MIX["thin_books"]
        outsized = rng.random() < _LIVE_SUPPRESSION_MIX["suspicious_edge"]

        quote_age_ms = rng.randint(1_000, 20_000)
        odds_age_ms = (
            rng.randint(1_000_000, 4_000_000) if stale
            else rng.randint(30_000, 800_000)
        )
        edge_tenths = rng.uniform(45.0, 90.0) if outsized else rng.gauss(5.0, 8.0)
        result = evaluate_suppression(
            config=suppression,
            kalshi_quote_age_ms=quote_age_ms,
            odds_age_ms=odds_age_ms,
            commence_skew_ms=rng.randint(-600_000, 600_000),
            depth_at_ask=800.0,
            contracts=20,
            # A thin consensus reports **no** width, not a zero one. Passing the
            # pair together is what keeps `inconsistent_consensus_metadata`
            # quiet, and getting it wrong here would be the seeder inventing a
            # producer state that cannot occur.
            market_width=None if thin else round(rng.uniform(0.005, 0.05), 4),
            book_count=1 if thin else rng.randint(4, 6),
            edge_tenths=edge_tenths,
            # The measured spread between the four devig methods on an even
            # moneyline, per `core/suppression.py`: 0.18 probability points.
            method_spread_probability=0.0018,
        )
        suppressed = result.reason
        contracts = 0 if suppressed else rng.randint(10, 30)

        cursor = conn.execute(
            "INSERT INTO recommendations (created_ms, strategy_config_version, "
            "ticker, side, entry_ask_tenths, fair_probability, edge_tenths, "
            "fee_predicted, ev_net_dollars, kelly_fraction, suggested_contracts, "
            # Seeded at the same value as `suggested_contracts`, because the
            # seeded history is meant to represent a record produced at the
            # reference profile. Omitting it would leave every seeded row
            # invisible to the gate -- silently, as "0 of 300" on a screen the
            # seeded history exists to populate. Same trap as
            # `clv_horizon_hours` below.
            "reference_contracts, "
            "kalshi_quote_age_ms, odds_age_ms, suppressed_reason, reason_text, "
            # `clv_horizon_hours` is not optional here even though the column
            # is nullable. The gate counts only rows scored at the current
            # primary horizon (ADR 0011), so a seeded row without it is
            # invisible to every screen the seeded history exists to populate --
            # and it would be invisible *silently*, as an empty Ledger rather
            # than an error.
            "clv_tenths, clv_scored_ms, clv_horizon_hours) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                created, version, ticker, side, ask, ask / 1000.0,
                # The same three numbers the suppression call was given, not a
                # second independent draw. They were re-rolled here, so a row
                # could read `stale_odds` beside a stored `odds_age_ms` of four
                # minutes -- the demo contradicting its own reason string, which
                # is the shape a reader would take to be a bug in the rule.
                edge_tenths, 0.15, 0.1, 0.01,
                contracts, contracts,
                quote_age_ms, odds_age_ms,
                suppressed, "seeded history",
                close_mid - ask, created + 7_200_000, DEFAULT_HORIZON_HOURS,
            ),
        )
        counts["recommendations"] += 1

        conn.execute(
            # The horizon comes from the constant, never a literal. A hardcoded
            # 1.0 here would have kept pointing at the old anchor after ADR 0011
            # moved it, so the seeded lines and the seeded scores would disagree
            # about which close they describe.
            "INSERT OR IGNORE INTO closing_lines (ticker, horizon_hours, "
            "observed_ms, yes_bid_tenths, yes_ask_tenths) VALUES (?, ?, ?, ?, ?)",
            (
                ticker, DEFAULT_HORIZON_HOURS, created + 3_600_000,
                int(close_mid) - 10, int(close_mid) + 10,
            ),
        )
        counts["closing_lines"] += 1

        # A settlement settles a **position**, so the seeded history needs the
        # paper order it closes. Since schema v4 `settlements.order_id` is
        # `NOT NULL`, and the previous form here -- `INSERT OR IGNORE` without
        # it -- inserted **nothing at all** while reporting a count, which is
        # `tasks/lessons.md` on `OR IGNORE` reproduced exactly: a constraint
        # failure converted into a plausible no-op. Plain `INSERT` below, so a
        # fixture that stops matching the schema fails loudly instead of
        # emptying the calibration mart in silence.
        contracts = 20
        order = conn.execute(
            "INSERT INTO orders (client_order_id, recommendation_id, "
            "submitted_ms, ticker, side, action, order_type, count, "
            "limit_price_tenths, status, request_body_json, dry_run, "
            "fill_assumption, assumed_filled_count) "
            "VALUES (?, ?, ?, ?, ?, 'buy', 'limit', ?, ?, 'dry_run', '{}', 1, "
            "?, ?)",
            (
                f"seed-{i:04d}", cursor.lastrowid, created, ticker, side,
                contracts, ask, DEPTH_CAPPED_TAKER, contracts,
            ),
        )
        pnl = (1000 - ask if won else -ask) * contracts / 1000 * 100
        conn.execute(
            "INSERT INTO settlements (order_id, ticker, settled_ms, result, "
            "contracts, pnl_cents, dry_run, fill_assumption) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
            (
                order.lastrowid, ticker, created + 10_800_000,
                "yes" if won else "no", contracts, int(pnl), DEPTH_CAPPED_TAKER,
            ),
        )
        counts["settlements"] += 1

    conn.commit()
    conn.close()
    return counts


def main() -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Seed a demo database.")
    parser.add_argument("--db", default="data/demo.db")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--anchor-now",
        action="store_true",
        help="Anchor the slate on the current clock instead of the fixed "
             "demo timestamp. The deployed demo uses this: the actionable "
             "window is measured against real time, so a frozen slate would "
             "render a permanently closed window beside live-looking prices. "
             "Off by default so local runs and tests stay reproducible.",
    )
    parser.add_argument(
        "--with-history",
        type=int,
        default=0,
        metavar="N",
        help="Also seed N scored, settled recommendations so the analytical "
             "marts have something to measure. Contains no edge by construction.",
    )
    args = parser.parse_args()

    anchor = db.now_ms() if args.anchor_now else None
    counts = seed_all(args.db, seed=args.seed, now_ms=anchor)
    if args.with_history:
        counts["history"] = seed_history(
            args.db, n=args.with_history, seed=args.seed, now_ms=anchor
        )

    print(json.dumps(counts, indent=2))
    print(f"\nSeeded {args.db}. No credentials, no network, no execution path.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
