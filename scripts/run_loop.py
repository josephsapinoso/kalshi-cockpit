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
= two sweeps. The budget refuses over-spend rather than failing, so a short
interval does not overspend -- it just produces passes that record Kalshi
quotes and skip the odds leg.

That is not wasted: a pass with no fresh odds still stores Kalshi quotes and
still scores closing lines for games that have started. But there is no reason
to run it every minute. **900s (15 min) is a sensible default**, giving ~96
passes a day of which two carry fresh odds.

There is now an upper bound as well, and it is enforced rather than documented.
`odds/timing.py` marks each sweep due for a thirty-minute window before a
cluster of kickoffs; a loop whose worst-case gap between passes exceeds that
window steps over the slot and never sweeps at all -- which looks exactly like
a quiet slate. The loop refuses to start rather than run in that state.

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

from backend.config import (  # noqa: E402
    GateConfig,
    KalshiConfig,
    OddsConfig,
    RiskConfig,
    StalenessConfig,
)
from backend.core.suppression import SuppressionConfig  # noqa: E402
from backend.kalshi.rest import KalshiRestClient  # noqa: E402
from backend.logging_setup import configure_logging  # noqa: E402
from backend.notify.alerts import Alerter  # noqa: E402
from backend.notify.discord import DiscordConfig, DiscordNotifier  # noqa: E402
from backend.odds.budget import CreditBudget  # noqa: E402
from backend.odds.client import OddsClient  # noqa: E402
from backend.odds.timing import (  # noqa: E402
    DUE_WINDOW_MS,
    sweep_window_survives_interval,
    window_status,
)
from backend.runner import run_once  # noqa: E402
from backend.scheduler import (  # noqa: E402
    JITTER,
    LoopFailed,
    LoopState,
    run_forever,
)
from backend.scoring import run_scoring_pass  # noqa: E402
from backend.store import db  # noqa: E402


class CombinedPass:
    """One pass's recording, scoring and alerting counts, reported as one line.

    Merged deliberately: separate log lines invite reading one and not the
    other, and "76 recommendations" beside "0 scored" is the pair that matters.
    Scoring counts are prefixed `clv_` so no field name can collide, and the
    alert counts say `alerts_deduped` as well as `alerts_sent` -- a quiet
    channel because everything was already announced and a quiet channel
    because the notifier is broken are different states.
    """

    def __init__(self, recording, scoring, alerts=None):
        self.recording = recording
        self.scoring = scoring
        self.alerts = alerts

    def as_dict(self) -> dict:
        merged = dict(self.recording.as_dict())
        merged.update({f"clv_{k}": v for k, v in self.scoring.as_dict().items()})
        if self.alerts is not None:
            merged.update(
                {k: v for k, v in self.alerts.as_dict().items() if v}
            )
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

    # Refuse, do not warn. A loop that steps over every sweep slot records the
    # same Kalshi quotes, scores the same closing lines, and never once opens a
    # window a human could bet in -- and reports nothing unusual while doing it.
    if not sweep_window_survives_interval(args.interval, jitter=JITTER):
        log.error(
            "--interval %.0fs is too long: with %.0f%% jitter the worst-case gap "
            "between passes is %.0fs, wider than the %.0fs window a sweep is due "
            "for. Every sweep would be stepped over and the tool would never be "
            "actionable. Use %.0fs or less.",
            args.interval, JITTER * 100, args.interval * (1 + JITTER),
            DUE_WINDOW_MS / 1000, (DUE_WINDOW_MS / 1000) / (1 + JITTER) - 1,
        )
        return 2

    conn = db.init_db(args.db)
    kalshi_config = KalshiConfig.load()
    odds_config = OddsConfig.load()
    risk = RiskConfig.load()
    gate_config = GateConfig.load()
    staleness = StalenessConfig.load()
    suppression = SuppressionConfig()
    budget = CreditBudget(
        conn,
        daily_budget=odds_config.daily_credit_budget,
        day_start_hour=odds_config.budget_day_start_utc_hour,
    )
    state = LoopState()

    discord_config = DiscordConfig.from_env()
    if discord_config is None:
        log.warning(
            "DISCORD_BOT_TOKEN/DISCORD_CHANNEL_ID are unset, so nothing will "
            "reach a phone. The odds window is open for %ds twice a day; "
            "without an alert nobody is looking when it happens.",
            staleness.max_odds_age_s,
        )

    async with KalshiRestClient(kalshi_config) as kalshi, \
            OddsClient(odds_config, budget) as odds, \
            DiscordNotifier(discord_config) as discord:

        alerter = Alerter(conn, discord)

        async def one_pass() -> CombinedPass:
            # One stamp for the whole pass, shared with the alerter: it finds
            # the rows this pass wrote by `created_ms = stamp`, and a second
            # clock reading would miss every one of them.
            stamp = db.now_ms()
            counts = await run_once(
                conn, kalshi, odds, budget,
                config=odds_config, risk=risk, suppression=suppression,
                now=stamp,
            )
            scoring = await run_scoring_pass(conn, kalshi)

            window = window_status(
                conn, budget=budget, now_ms=db.now_ms(),
                max_odds_age_ms=suppression.max_odds_age_ms,
                sweep_cost=odds_config.credits_per_sweep_per_sport,
            )
            alerts = await alerter.after_pass(
                pass_ms=stamp, counts=counts, window=window,
                sweeps_this_pass=counts.odds_sweeps,
            )
            await alerter.daily_digest(
                now_ms=stamp,
                day_start_ms=budget.day_start_ms(stamp),
                gate_required=gate_config.min_scored_recommendations,
            )
            return CombinedPass(counts, scoring, alerts)

        log.info(
            "starting loop: interval=%.0fs db=%s discord=%s. The gate needs 300 "
            "independent games; nothing is surfaced until the record supports it.",
            args.interval, args.db, "on" if discord.enabled else "off",
        )
        try:
            await run_forever(
                one_pass,
                interval_s=args.interval,
                state=state,
                max_passes=args.max_passes,
            )
        except LoopFailed as exc:
            # The last thing this process does. The loop dying is precisely the
            # failure the Board cannot show -- it keeps serving the record it
            # already has, which reads as a calm market.
            await alerter.failure("Recording loop died", str(exc), now_ms=db.now_ms())
            raise
        finally:
            log.info("loop state at exit: %s", state.as_dict())

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
