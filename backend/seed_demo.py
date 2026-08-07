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

from .config import RiskConfig
from .core.devig import devig
from .core.suppression import SuppressionConfig
from .engine import (
    Candidate,
    build_recommendation,
    ensure_strategy_config,
    persist_recommendation,
)
from .store import db

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


def _scenarios(rng: random.Random) -> list[SeededScenario]:
    """Build a slate whose shape resembles reality.

    Most candidates have no edge. A few are suppressed for concrete, different
    reasons. One or two are genuinely actionable. Anything more generous would
    be a misleading demo.
    """
    out: list[SeededScenario] = []
    # (offset, quote_age, depth, width, books) -- one entry per fixture,
    # hand-chosen so each suppression rule is represented exactly once.
    shapes = [
        (-35, 3_000, 800.0, 0.012, 5),    # surfaced: genuine ~3.5c edge
        (+40, 4_000, 600.0, 0.010, 5),    # no edge -- Kalshi asks above fair
        (-260, 5_000, 400.0, 0.014, 4),   # suspicious_edge: too good to be true
        (-38, 900_000, 700.0, 0.011, 5),  # stale_kalshi_quote
        (-33, 3_500, 4.0, 0.013, 5),      # insufficient_depth
        (-36, 4_500, 500.0, 0.220, 4),    # wide_market
        (+15, 6_000, 300.0, 0.015, 5),    # no edge
        (-30, 3_000, 900.0, 0.009, 6),    # surfaced: genuine edge
        (-8, 3_000, 500.0, 0.010, 5),     # edge_within_method_noise
    ]
    for (series, league, team, opp, o1, o2), shape in zip(_FIXTURES, shapes):
        offset, age, depth, width, books = shape
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
            )
        )
    return out


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

    counts = {"markets": 0, "recommendations": 0, "surfaced": 0, "suppressed": 0}

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
                odds_age_ms=rng.randint(45_000, 400_000),
                commence_skew_ms=rng.randint(-300_000, 300_000),
            ),
            risk=risk,
            suppression=suppression,
            strategy_config_version=version,
            current_exposure_dollars=0.0,
            created_ms=stamp - index * 60_000,
        )
        persist_recommendation(conn, recommendation)
        counts["recommendations"] += 1
        if recommendation.surfaced:
            counts["surfaced"] += 1
        elif recommendation.suppressed_reason:
            counts["suppressed"] += 1

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

        cursor = conn.execute(
            "INSERT INTO recommendations (created_ms, strategy_config_version, "
            "ticker, side, entry_ask_tenths, fair_probability, edge_tenths, "
            "fee_predicted, ev_net_dollars, kelly_fraction, suggested_contracts, "
            "kalshi_quote_age_ms, odds_age_ms, suppressed_reason, reason_text, "
            "clv_tenths, clv_scored_ms) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                created, version, ticker, side, ask, ask / 1000.0,
                rng.gauss(5, 8), 0.15, 0.1, 0.01,
                0 if suppressed else rng.randint(10, 30),
                rng.randint(1000, 20000), rng.randint(30_000, 400_000),
                suppressed, "seeded history",
                close_mid - ask, created + 7_200_000,
            ),
        )
        counts["recommendations"] += 1

        conn.execute(
            "INSERT OR IGNORE INTO closing_lines (ticker, horizon_hours, "
            "observed_ms, yes_bid_tenths, yes_ask_tenths) VALUES (?, 1.0, ?, ?, ?)",
            (ticker, created + 3_600_000, int(close_mid) - 10, int(close_mid) + 10),
        )
        counts["closing_lines"] += 1

        contracts = 20
        pnl = (1000 - ask if won else -ask) * contracts / 1000 * 100
        conn.execute(
            "INSERT OR IGNORE INTO settlements (ticker, settled_ms, result, "
            "contracts, pnl_cents) VALUES (?, ?, ?, ?, ?)",
            (ticker, created + 10_800_000, "yes" if won else "no", contracts, int(pnl)),
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
        "--with-history",
        type=int,
        default=0,
        metavar="N",
        help="Also seed N scored, settled recommendations so the analytical "
             "marts have something to measure. Contains no edge by construction.",
    )
    args = parser.parse_args()

    counts = seed_all(args.db, seed=args.seed)
    if args.with_history:
        counts["history"] = seed_history(
            args.db, n=args.with_history, seed=args.seed
        )

    print(json.dumps(counts, indent=2))
    print(f"\nSeeded {args.db}. No credentials, no network, no execution path.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
