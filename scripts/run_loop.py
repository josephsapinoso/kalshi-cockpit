"""Run the chain on an interval. This is what accumulates the evidence record.

    .venv\\Scripts\\python.exe scripts\\run_loop.py --db data/live.db --interval 900

Each pass does two things:

1. **Ingest and price** -- discovery, an odds sweep inside the credit budget,
   linking, devig, and a `recommendations` row per candidate.
2. **Score** -- fetch closing lines for games that have now started and score
   the recommendations waiting on them.

Both in one pass because they share a Kalshi client and because scoring is
useless without recording and recording is pointless without scoring.

Choosing the interval
---------------------
The binding constraint is **odds credits, not Kalshi**. The free tier is ~500 a
month and one sweep costs `markets x regions` = 6, so roughly 16 credits a day
= two sweeps. `plan_sweep` refuses over budget rather than failing, so a short
interval does not overspend -- it just produces passes that record Kalshi
quotes and skip the odds leg.

That is not wasted: a pass with no fresh odds still stores Kalshi quotes and
still scores closing lines for games that have started. But there is no reason
to run it every minute. **900s (15 min) is a sensible default**, giving ~96
passes a day of which the first two carry fresh odds.

The loop dies loudly after `MAX_CONSECUTIVE_FAILURES`, which takes the
container with it. See `backend/scheduler.py`.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import KalshiConfig, OddsConfig, RiskConfig  # noqa: E402
from backend.core.suppression import SuppressionConfig  # noqa: E402
from backend.kalshi.rest import KalshiRestClient  # noqa: E402
from backend.logging_setup import configure_logging  # noqa: E402
from backend.odds.budget import CreditBudget  # noqa: E402
from backend.odds.client import OddsClient  # noqa: E402
from backend.runner import run_once  # noqa: E402
from backend.scheduler import LoopState, run_forever  # noqa: E402
from backend.scoring import run_scoring_pass  # noqa: E402
from backend.store import db  # noqa: E402


class CombinedPass:
    """One pass's recording and scoring counts, reported as one line.

    Merged deliberately: two separate log lines invite reading one and not the
    other, and "76 recommendations" beside "0 scored" is the pair that matters.
    Scoring counts are prefixed `clv_` so no field name can collide.
    """

    def __init__(self, recording, scoring):
        self.recording = recording
        self.scoring = scoring

    def as_dict(self) -> dict:
        merged = dict(self.recording.as_dict())
        merged.update({f"clv_{k}": v for k, v in self.scoring.as_dict().items()})
        return merged


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/live.db")
    parser.add_argument(
        "--interval", type=float, default=900.0, help="seconds between passes"
    )
    parser.add_argument(
        "--max-passes", type=int, default=None,
        help="stop after N passes. Mainly for a smoke test.",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    # Never `logging.basicConfig`: the Odds API key travels in a query string
    # and httpx logs full URLs. See backend/logging_setup.py.
    configure_logging(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("run_loop")

    conn = db.init_db(args.db)
    kalshi_config = KalshiConfig.load()
    odds_config = OddsConfig.load()
    risk = RiskConfig.load()
    suppression = SuppressionConfig()
    budget = CreditBudget(conn, daily_budget=odds_config.daily_credit_budget)
    state = LoopState()

    async with KalshiRestClient(kalshi_config) as kalshi, \
            OddsClient(odds_config, budget) as odds:

        async def one_pass() -> CombinedPass:
            counts = await run_once(
                conn, kalshi, odds, budget,
                config=odds_config, risk=risk, suppression=suppression,
            )
            scoring = await run_scoring_pass(conn, kalshi)
            return CombinedPass(counts, scoring)

        log.info(
            "starting loop: interval=%.0fs db=%s. The gate needs 300 "
            "independent games; nothing is surfaced until the record supports it.",
            args.interval, args.db,
        )
        try:
            await run_forever(
                one_pass,
                interval_s=args.interval,
                state=state,
                max_passes=args.max_passes,
            )
        finally:
            log.info("loop state at exit: %s", state.as_dict())

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
