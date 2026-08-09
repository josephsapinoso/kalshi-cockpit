"""Run the chain on two interleaved cadences. This accumulates the record.

    .venv\\Scripts\\python.exe scripts\\run_loop.py --db data/live.db --interval 900

**A full pass**, every `--interval` seconds, does three things:

1. **Ingest and price** -- discovery, an odds sweep inside the credit budget,
   linking, devig, and a `recommendations` row per candidate.
2. **Score** -- fetch closing lines for games that have now started and score
   the recommendations waiting on them.
3. **Alert** -- the window, any surfaced opportunity, the daily digest.

All in one pass because they share a Kalshi client and because scoring is
useless without recording and recording is pointless without scoring.

**A quote pass**, every `--fast-interval` seconds *while the window is open*,
does only the first half of (1): Kalshi discovery, the quotes it carries, and a
re-price against the odds already stored. It spends no credit, fetches no
closing lines, and still alerts, because a quote pass is exactly when a new
opportunity appears.

Choosing the intervals
----------------------
The slow one is bounded by **odds credits, not Kalshi**. The free tier is ~500 a
month and one sweep costs `markets x regions` = 6, so roughly 16 credits a day
= two sweeps. The budget refuses over-spend rather than failing, so a short
interval does not overspend -- it just produces passes that record Kalshi quotes
and skip the odds leg. **900s (15 min) is a sensible default.**

The fast one is bounded by the Kalshi quote limit, which is 30 seconds. That is
the whole reason this file grew a second cadence: a row is bettable only while
*both* its inputs are fresh, and on a single 900s cadence the tighter of the two
made every row bettable for thirty seconds after each pass -- roughly a minute a
day, from a tool this repo documented everywhere as actionable for half an hour.
Nothing was wrong with either limit; nothing computed their product.

Both intervals are checked at startup and the loop **refuses to run** rather
than warn, because each failure looks exactly like a quiet slate:

- Too slow, and `odds/timing.py`'s thirty-minute sweep slot is stepped over, so
  the odds never arrive at all (`sweep_window_survives_interval`).
- Too fast on the quote side, and rows expire between passes anyway, so the
  extra requests buy nothing (`quote_refresh_survives_interval`).

The loop dies loudly after `MAX_CONSECUTIVE_FAILURES`, which takes the
container with it. See `backend/scheduler.py`.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
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
from backend.runner import run_once, run_quote_pass  # noqa: E402
from backend.scheduler import (  # noqa: E402
    DEFAULT_FAST_INTERVAL_S,
    JITTER,
    QUOTE_PASS_DURATION_BUDGET_S,
    LoopFailed,
    LoopState,
    Tempo,
    quote_refresh_survives_interval,
    run_forever,
)
from backend.gate import (  # noqa: E402
    GATE_PROGRESS_WINDOW_MS,
    log_gate_progress,
)
from backend.scoring import run_scoring_pass  # noqa: E402
from backend.settlement import run_settlement_pass  # noqa: E402
from backend.store import db  # noqa: E402


class CombinedPass:
    """One pass's recording, scoring and alerting counts, reported as one line.

    Merged deliberately: separate log lines invite reading one and not the
    other, and "76 recommendations" beside "0 scored" is the pair that matters.
    Scoring counts are prefixed `clv_` so no field name can collide, and the
    alert counts say `alerts_deduped` as well as `alerts_sent` -- a quiet
    channel because everything was already announced and a quiet channel
    because the notifier is broken are different states.

    `kind` says which cadence produced the line. A quote pass reports no `clv_`
    counts at all, and without the label that reads as "scoring found nothing"
    rather than "scoring did not run" -- the same confusion `sweep_decision`
    exists to prevent one column over.
    """

    def __init__(self, recording, scoring=None, alerts=None, *, kind="full",
                 seconds=0.0, settlement=None):
        self.recording = recording
        self.scoring = scoring
        self.settlement = settlement
        self.alerts = alerts
        self.kind = kind
        self.seconds = seconds

    def as_dict(self) -> dict:
        merged = {"pass": self.kind, "took_s": round(self.seconds, 1)}
        merged.update(self.recording.as_dict())
        if self.scoring is not None:
            merged.update({f"clv_{k}": v for k, v in self.scoring.as_dict().items()})
        # Prefixed, like the scoring counts, so `settled: 0` cannot be misread
        # as a recording number. Two passes reporting into one line need their
        # own namespaces or the reader has to know which is which.
        if self.settlement is not None:
            merged.update(
                {f"settle_{k}": v for k, v in self.settlement.as_dict().items()}
            )
        if self.alerts is not None:
            merged.update(
                {k: v for k, v in self.alerts.as_dict().items() if v}
            )
        return merged


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/live.db")
    parser.add_argument(
        "--interval", type=float, default=900.0, help="seconds between full passes"
    )
    parser.add_argument(
        "--fast-interval", type=float, default=DEFAULT_FAST_INTERVAL_S,
        help=(
            "seconds between quote passes while the window is open. Bounded by "
            "MAX_KALSHI_QUOTE_AGE_S, not by the odds budget -- Kalshi is "
            "unmetered."
        ),
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

    # The other half of the same question, and the one that was never asked.
    # The odds sweep opens a fifteen-minute window; the Kalshi quote inside it
    # is good for thirty seconds. A fast interval that cannot beat that limit
    # spends requests to produce rows that expire between passes anyway -- and
    # an expired row is indistinguishable from a slate with nothing on it.
    staleness_check = StalenessConfig.load()
    if not quote_refresh_survives_interval(
        args.fast_interval,
        jitter=JITTER,
        max_kalshi_quote_age_s=staleness_check.max_kalshi_quote_age_s,
    ):
        log.error(
            "--fast-interval %.0fs cannot keep a row bettable: with %.0f%% jitter "
            "and a %.0fs allowance for the pass itself the worst-case gap between "
            "confirmations is %.1fs, past the %ds MAX_KALSHI_QUOTE_AGE_S limit. "
            "Raising the limit is the wrong fix -- 30s is correct for a venue "
            "quoted by sub-200ms market makers. Use %.0fs or less.",
            args.fast_interval, JITTER * 100, QUOTE_PASS_DURATION_BUDGET_S,
            args.fast_interval * (1 + JITTER) + QUOTE_PASS_DURATION_BUDGET_S,
            staleness_check.max_kalshi_quote_age_s,
            (staleness_check.max_kalshi_quote_age_s - QUOTE_PASS_DURATION_BUDGET_S)
            / (1 + JITTER) - 1,
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
        tempo = Tempo(
            slow_interval_s=args.interval, fast_interval_s=args.fast_interval
        )

        async def one_pass() -> CombinedPass:
            # One stamp for the whole pass, shared with the alerter: it finds
            # the rows this pass wrote by `created_ms = stamp`, and a second
            # clock reading would miss every one of them.
            stamp = db.now_ms()
            started = time.monotonic()
            kind = tempo.pass_kind(stamp)

            if kind == "full":
                counts = await run_once(
                    conn, kalshi, odds, budget,
                    config=odds_config, risk=risk, suppression=suppression,
                    now=stamp,
                )
                scoring = await run_scoring_pass(conn, kalshi)
                # Full pass only. A settled market stays settled, so asking
                # every fifteen seconds during an open window would spend
                # requests to be told the same thing -- and the fast cadence
                # exists to keep quotes inside 30s, which this does not touch.
                settlement = await run_settlement_pass(conn, kalshi)
            else:
                # Kalshi only. No credit, no candlesticks -- the point is to
                # re-confirm the quote behind every row before its 30s runs out,
                # and neither of those touches that.
                counts = await run_quote_pass(
                    conn, kalshi, risk=risk, suppression=suppression, now=stamp,
                )
                scoring = None
                settlement = None

            window = window_status(
                conn, budget=budget, now_ms=db.now_ms(),
                max_odds_age_ms=suppression.max_odds_age_ms,
                sweep_cost=odds_config.credits_per_sweep_per_sport,
            )
            # Alerting on a quote pass too, deliberately. A quote pass is when a
            # price moves inside the window, so it is exactly when a new
            # opportunity appears -- and the dedupe lives in `notifications`, so
            # a row already announced is not announced again.
            alerts = await alerter.after_pass(
                pass_ms=stamp, counts=counts, window=window,
                sweeps_this_pass=counts.odds_sweeps,
            )
            if kind == "full":
                await alerter.daily_digest(
                    now_ms=stamp,
                    day_start_ms=budget.day_start_ms(stamp),
                    gate_required=gate_config.min_scored_recommendations,
                )
                log_gate_progress(
                    conn,
                    since_ms=stamp - GATE_PROGRESS_WINDOW_MS,
                    required=gate_config.min_scored_recommendations,
                )

            # Set after the pass, from stored state, so the next cadence follows
            # what this pass actually achieved. A sweep that just fired means
            # the window is open and the loop should speed up now, not in
            # fifteen minutes.
            tempo.window_open = window.is_open
            elapsed = time.monotonic() - started
            tempo.observe_pass_duration(
                elapsed,
                max_kalshi_quote_age_s=staleness.max_kalshi_quote_age_s,
                kind=kind,
            )
            if kind == "full":
                tempo.completed_full_pass(stamp)
            else:
                tempo.completed_quote_pass(stamp)

            return CombinedPass(
                counts, scoring, alerts, kind=kind, seconds=elapsed,
                settlement=settlement,
            )

        log.info(
            "starting loop: full pass every %.0fs, quote pass every %.0fs while "
            "the window is open, db=%s discord=%s. The gate needs 300 "
            "independent games; nothing is surfaced until the record supports it.",
            args.interval, args.fast_interval, args.db,
            "on" if discord.enabled else "off",
        )
        try:
            await run_forever(
                one_pass,
                interval_s=tempo.interval_s,
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
            log.info(
                "loop state at exit: %s tempo: %s", state.as_dict(), tempo.as_dict()
            )

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
