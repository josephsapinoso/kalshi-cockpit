"""Run one pass of the chain and print what each stage produced.

    .venv\\Scripts\\python.exe scripts\\run_chain.py --db data/live.db
    .venv\\Scripts\\python.exe scripts\\run_chain.py --db data/live.db --no-odds

**This spends Odds API credits.** One sweep costs `markets x regions` -- 6 on
the default config -- against a free tier of roughly 16 a day, so two sweeps is
the daily allowance. `--no-odds` runs discovery and pricing against whatever
odds are already stored, which costs nothing and is the right way to check the
chain works before letting it spend.

Reading the output
------------------
Every stage reports, including the drops, because a runner that prints only
successes looks identical whether it priced forty games or lost thirty-nine at
the link step. If `recommendations` is 0, the field above it that is also 0
says where it stopped:

    events_discovered   nothing priceable on Kalshi -- check the calendar
    events_linked       discovery worked, matching did not -- read
                        `unmatched_items`, which names the teams as seen
    dropped_no_books    linked, but no stored odds for that fixture -- the
                        sweep did not cover it, or the budget refused
    dropped_no_kalshi_quote   no readable bid on the market
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import (  # noqa: E402
    KalshiConfig,
    OddsConfig,
    RiskConfig,
    configured_day_start_utc_hour,
)
from backend.core.suppression import SuppressionConfig  # noqa: E402
from backend.kalshi.discovery import discover_from_events  # noqa: E402
from backend.kalshi.rest import KalshiRestClient  # noqa: E402
from backend.logging_setup import configure_logging  # noqa: E402
from backend.odds.budget import CreditBudget  # noqa: E402
from backend.odds.client import OddsClient  # noqa: E402
from backend.runner import (  # noqa: E402
    PassCounts,
    run_ingest_pass,
    run_pricing_pass,
    store_quotes_from_discovery,
    upsert_discovered,
)
from backend.store import db  # noqa: E402
from backend.store.db import now_ms  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/live.db")
    parser.add_argument(
        "--no-odds",
        action="store_true",
        help="Skip the odds sweep and price against stored odds. Spends nothing.",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    # Not `logging.basicConfig`. The Odds API takes its key as a query
    # parameter and httpx logs full URLs at INFO, so plain logging setup puts a
    # live credential in the terminal and in Fly's log stream.
    configure_logging(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    conn = db.init_db(args.db)
    kalshi_config = KalshiConfig.load()

    stamp = now_ms()

    async with KalshiRestClient(kalshi_config) as kalshi:
        if args.no_odds:
            # Discovery only. `/events` is walked here rather than by
            # `run_ingest_pass` so it is walked exactly ONCE -- doing both
            # paginated the whole universe twice, about a dozen extra requests
            # for bytes already in hand.
            raw = [e async for e in kalshi.events(with_nested_markets=True)]
            events = discover_from_events(raw)
            upsert_discovered(conn, events, now=stamp)
            counts = PassCounts()
            counts.markets_quoted = store_quotes_from_discovery(
                conn, events, now=stamp
            )
        else:
            odds_config = OddsConfig.load()
            budget = CreditBudget(
                conn,
                daily_budget=odds_config.daily_credit_budget,
                monthly_budget=odds_config.monthly_credit_budget,
                day_start_hour=odds_config.budget_day_start_utc_hour,
            )
            async with OddsClient(odds_config, budget) as odds:
                events, counts = await run_ingest_pass(
                    conn, kalshi, odds, budget, config=odds_config, now=stamp,
                    suppression=SuppressionConfig(),
                )

    counts = run_pricing_pass(
        conn, events,
        risk=RiskConfig.load(),
        # SuppressionConfig carries its thresholds as dataclass defaults rather
        # than from the environment, so the recorded `strategy_config_version`
        # changes only when the code does.
        suppression=SuppressionConfig(),
        now=stamp, counts=counts,
        # Read directly rather than off an `OddsConfig`, because `--no-odds`
        # builds none and `OddsConfig.load` demands the API key this branch
        # deliberately does not need. Same single parse either way, so this
        # script's kill-switch day cannot differ from the loop's.
        day_start_hour=configured_day_start_utc_hour(),
    )

    print(json.dumps(counts.as_dict(), indent=2))
    if counts.recommendations == 0:
        print(
            "\nNo recommendations. Read the stage counts above -- the first "
            "one that is zero is where the chain stopped.",
            file=sys.stderr,
        )
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
