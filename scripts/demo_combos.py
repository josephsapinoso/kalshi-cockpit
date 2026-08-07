"""Kalshi's combo product, and what its price tells you.

Run:  python -m scripts.demo_combos

Reads the captured fixtures, so it needs no credentials and no network.
Add --live to walk the real API (still read-only; no lookup, no market created).
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from backend.core.correlation import (
    CorrelationRefused,
    CorrelationUnreachable,
    Leg,
    implied_correlation,
    joint_probability_all,
)
from backend.kalshi.combos import (
    ComboScope,
    liquidity,
    parse_collection,
    same_game_collections,
)

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
NOW = 1_754_800_000_000


def rule(title: str) -> None:
    print(f"\n{'=' * 76}\n{title}\n{'=' * 76}")


def load_fixture_collections():
    captured = json.loads(
        (FIXTURES / "combo_collections.json").read_text(encoding="utf-8")
    )
    return [parse_collection(entry) for entry in captured.values()]


async def load_live_collections():
    from backend.config import KalshiConfig
    from backend.kalshi.combos import fetch_collections
    from backend.kalshi.rest import KalshiRestClient

    cfg = KalshiConfig.load()
    async with KalshiRestClient(cfg) as api:
        return await fetch_collections(api)


def main(collections, summary) -> None:
    rule("1. The correction: Kalshi does have a combo product")
    print("  This project was built on 'Kalshi has no parlay product', drawn")
    print("  from the true observation that /markets is ~99.8% KXMVE with no")
    print("  volume. KXMVE is Multi-Variate Event -- the combo builder in the")
    print("  app. The junk is the pre-generated markets, not the product.\n")
    if summary:
        print(f"  {summary['n_collections']:>6,} collections")
        print(f"  {summary['n_legs']:>6,} legs available to combine")

    rule("2. What can be combined")
    by_scope: dict[ComboScope, list] = {}
    for collection in collections:
        by_scope.setdefault(collection.scope, []).append(collection)
    for scope, entries in sorted(by_scope.items(), key=lambda kv: kv[0].value):
        print(f"\n  {scope.value.upper()}")
        for entry in entries[:3]:
            print(f"    {entry.series_ticker:<32} size>={entry.size_min} "
                  f"legs={len(entry.legs)}")
            print(f"      {entry.title[:66]}")

    same_game = same_game_collections(collections)
    if same_game:
        fixture, collection = next(iter(same_game.items()))
        rule(f"3. A same-game collection: {fixture}")
        print(f"  {collection.collection_ticker}")
        print(f"  leg types: {', '.join(collection.leg_series)}")
        print(f"\n  {collection.functional_description[:150]}")
        print("\n  These are legs of ONE fixture -- exactly the case")
        print("  core/correlation.py refuses to price from marginals alone.")

    rule("4. Liquidity, reported honestly")
    report = liquidity(collections)
    print(f"  {report.verdict}\n")
    for series, (legs, quoted) in list(report.by_series.items())[:8]:
        print(f"    {series:<34} {legs:>6} legs, {quoted:>4} quoted")

    rule("5. Why the combo PRICE is worth more than the combo")
    legs = [
        Leg(label="Lakers win", probability=0.60, event_key="E1",
            league="basketball_nba", commence_ms=NOW),
        Leg(label="Over 224.5", probability=0.50, event_key="E1",
            league="basketball_nba", commence_ms=NOW),
    ]
    print("  Two legs of one game. Marginals 0.60 and 0.50.\n")
    try:
        joint_probability_all(legs)
    except CorrelationRefused as exc:
        print(f"  Priced from marginals -> CorrelationRefused")
        print(f"    {str(exc)[:180]}...")

    print("\n  But a quoted combo price IS a joint probability, so it inverts")
    print("  to the correlation the module declined to guess:\n")
    print(f"    {'combo quote':>12}  {'implied rho':>12}  {'reading':<38}")
    for quote in (0.24, 0.28, 0.30, 0.33, 0.36, 0.42):
        try:
            rho = implied_correlation(legs, quote)
            if abs(rho) < 0.03:
                reading = "independent"
            elif rho > 0:
                reading = "win and over land together"
            else:
                reading = "win and over fight each other"
            print(f"    {quote:>12.2f}  {rho:>+12.3f}  {reading:<38}")
        except CorrelationUnreachable as exc:
            print(f"    {quote:>12.2f}  {'--':>12}  {str(exc)[:38]}")

    print("\n  Naive multiplication says 0.30. A quote of 0.36 means Kalshi")
    print("  prices these legs as meaningfully positively correlated -- and a")
    print("  parlay bought on the independence assumption would be overpaying")
    print("  for a joint it valued at 0.30 while the market says 0.36.")

    rule("6. What is still unknown")
    print("  - No combo PRICE was fetched. Getting one needs POST .../lookup,")
    print("    which creates a market on the exchange. No money moves, but it")
    print("    is an outward-facing write, so combos.lookup_combo refuses")
    print("    without allow_market_creation=True.")
    print("  - Liquidity was measured out of season and is therefore weak")
    print("    evidence. Re-run in season before concluding anything.")
    print("  - Kalshi's combo fee structure is unverified, and the per-leg fee")
    print("    on a combo may differ from a single contract.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="walk the real API")
    args = parser.parse_args()

    if args.live:
        loaded = asyncio.run(load_live_collections())
        info = {"n_collections": len(loaded),
                "n_legs": sum(len(c.legs) for c in loaded)}
    else:
        loaded = load_fixture_collections()
        info = json.loads(
            (FIXTURES / "combo_collections_summary.json").read_text(encoding="utf-8")
        )

    main(loaded, info)
    print()
