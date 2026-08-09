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

from .analysis.clv import DEFAULT_HORIZON_HOURS
from .config import RiskConfig
from .core.devig import devig
from .core.suppression import SuppressionConfig
from .odds.budget import day_start_ms
from .engine import (
    Candidate,
    build_recommendation,
    ensure_strategy_config,
    persist_recommendation,
)
from .store import db
from .store.orders import DEPTH_CAPPED_TAKER

DEFAULT_SEED = 1337

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
    market_width: float
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
    for book in _DEMO_BOOKS[: scenario.book_count]:
        jitter = rng.randint(0, 20_000)
        for name, price in zip(
            (scenario.team, scenario.opponent), scenario.odds
        ):
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
                    round(price * (1.0 + rng.uniform(-0.01, 0.01)), 3),
                ),
            )
            stored += 1
    return stored


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
    for table in (
        "recommendations", "fills", "orders", "settlements", "closing_lines",
        "fair_prices", "event_links", "unmatched_events", "kalshi_quotes",
        "odds_snapshots", "api_credits", "model_ratings", "lessons",
        "kalshi_markets", "kalshi_events", "kalshi_series", "strategy_configs",
    ):
        conn.execute(f"DELETE FROM {table}")
    conn.commit()

    risk = RiskConfig()
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

        fair = devig([scenario.team, scenario.opponent], list(scenario.odds))
        fair_p = fair.conservative_probability(scenario.team)
        ask = int(round(fair_p * 1000)) + scenario.ask_offset_tenths
        ask = max(10, min(990, ask))

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
        counts["odds_quotes"] += _seed_books(
            conn,
            scenario=scenario,
            commence_ms=commence,
            fetched_ms=stamp - scenario.odds_age_ms,
            rng=rng,
        )

        recommendation = build_recommendation(
            Candidate(
                ticker=scenario.ticker,
                side="yes",
                outcome_name=scenario.team,
                ask_tenths=ask,
                depth_at_ask=scenario.depth,
                kalshi_quote_age_ms=scenario.quote_age_ms,
                link_id=None,
                fair_price_id=None,
                devig=fair,
                book_count=scenario.book_count,
                market_width=scenario.market_width,
                odds_age_ms=scenario.odds_age_ms,
                commence_skew_ms=rng.randint(-300_000, 300_000),
            ),
            risk=risk,
            suppression=suppression,
            strategy_config_version=version,
            current_exposure_dollars=0.0,
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
    day_start = day_start_ms(stamp)
    for sport, age_ms in (("baseball_mlb", 120_000), ("basketball_wnba", 5 * 3_600_000)):
        called_ms = max(stamp - age_ms, day_start + 60_000)
        conn.execute(
            "INSERT INTO api_credits (called_ms, endpoint, sport_key, markets, "
            "regions, cost, remaining_reported, used_reported) "
            "VALUES (?, '/odds', ?, 'h2h,spreads,totals', 'us,eu', 6, 388, 112)",
            (called_ms, sport),
        )
    counts["odds_sweeps"] = 2

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
        suppressed = rng.choice(
            [None, None, None, "stale_odds", "wide_market", "insufficient_depth"]
        )
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
                rng.gauss(5, 8), 0.15, 0.1, 0.01,
                contracts, contracts,
                rng.randint(1000, 20000), rng.randint(30_000, 400_000),
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
