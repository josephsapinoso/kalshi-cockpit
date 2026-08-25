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
does the first half of (1): Kalshi discovery, the quotes it carries, and a
re-price against stored odds. It fetches no closing lines and runs no digest,
and it still alerts, because a quote pass is exactly when a new opportunity
appears.

**It also carries the odds refresh, and no longer "spends no credit".** A slot
re-buys its odds every `refresh_interval_ms` for as long as it is due, and that
cannot ride the full pass: a refresh is only considered when a pass runs, so the
worst-case age is the interval plus one pass gap -- `600 + 900 = 1500s` on the
slow cadence against a 900s limit, versus `600 + 15 = 615s` here. What bounds the
spend is the interval, not this one; the pass asks every tick and is told "not
yet" on all but one in forty. See `docs/adr/0030-the-odds-refresh-rolls.md`.

Choosing the intervals
----------------------
The slow one is bounded by **odds credits, not Kalshi**. One sweep costs
`markets x regions` = 6. On the old 500/month free tier that meant ~16 credits a
day -- two sweeps, two fifteen-minute windows, and a measured `stale_odds` on
256 of 265 suppressed rows because a full pass every 900s writes rows all day
against odds that are fresh for half an hour of it. The 20K tier (2026-08-09)
lifts the daily cap to 400, at which point the *scheduler* binds instead: each
sport has at most twelve useful slots a day (`MIN_SLOT_SEPARATION_MS`), so six
in-scope leagues cannot spend more than ~432 a day however large the budget is.

The budget refuses over-spend rather than failing, so a short interval does not
overspend -- it just produces passes that record Kalshi quotes and skip the odds
leg. **900s (15 min) is a sensible default**, and since the rolling refresh moved
the odds leg onto the fast cadence this interval no longer bounds how fresh the
consensus is at all. It bounds discovery, closing lines, settlement and the
digest.

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
import contextlib
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import (  # noqa: E402
    GateConfig,
    KalshiConfig,
    MarketResultConfig,
    OddsConfig,
    RiskConfig,
    StalenessConfig,
    assert_kalshi_quote_age_limits_agree,
    assert_odds_age_limits_agree,
    assert_risk_day_start_agrees,
)
from backend.core.suppression import SuppressionConfig  # noqa: E402
from backend.kalshi.rest import KalshiRestClient  # noqa: E402
from backend.logging_setup import configure_logging  # noqa: E402
from backend.notify.alerts import Alerter, FAILURE_LOOP_DIED  # noqa: E402
from backend.notify.discord import DiscordConfig, DiscordNotifier  # noqa: E402
from backend.odds.budget import CreditBudget  # noqa: E402
from backend.portfolio_poll import poll_portfolio_forever  # noqa: E402
from backend.odds.client import OddsClient  # noqa: E402
from backend.odds import ondemand  # noqa: E402
from backend.odds.timing import (  # noqa: E402
    DEFAULT_DAY_START_UTC_HOUR,
    DUE_WINDOW_MS,
    ManualRefresh,
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
from backend.market_results import run_market_result_pass  # noqa: E402
from backend.scoring import run_scoring_pass  # noqa: E402
from backend.settlement import run_settlement_pass  # noqa: E402
from backend.store import db  # noqa: E402


@contextlib.contextmanager
def counts_survive_a_late_failure(log, kind: str, counts):
    """Say what the pass achieved before letting the exception through.

    A pass records first and then scores, settles and alerts. If it dies in the
    second half, `run_forever` logs a traceback -- which says *where* it broke
    and nothing about what had already been written. "Did the sweep fire before
    it died" is the first question anyone asks of a failed pass, and the answer
    was on disk the whole time.

    This is the one job `run_pricing_pass` did by logging its counts inline,
    and it did it on every *successful* pass too -- four milliseconds before
    `pass N ok` printed a superset of the same dict, at the quote cadence,
    against a 100-line `flyctl logs` buffer.

    Re-raises. The loop's failure counting is what decides whether the process
    lives, and swallowing here would make a dead pass look like a quiet slate.
    """
    try:
        yield
    except Exception:
        log.error(
            "%s pass died after recording. Counts at the point it broke: %s",
            kind, counts.as_dict(),
        )
        raise


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
                 seconds=0.0, settlement=None, market_results=None):
        self.recording = recording
        self.scoring = scoring
        self.settlement = settlement
        self.market_results = market_results
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
        # `outcome_` and not `settle_`: these two count different populations --
        # settlement closes paper *positions*, this records the result of every
        # *market* discovered, bet or not -- and one prefix over both would read
        # as one number disagreeing with itself.
        if self.market_results is not None:
            merged.update(
                {f"outcome_{k}": v for k, v in self.market_results.as_dict().items()}
            )
        if self.alerts is not None:
            merged.update(
                {k: v for k, v in self.alerts.as_dict().items() if v}
            )
        return merged


# Where the cockpit API answers inside the container. `docker/entrypoint.sh`
# starts uvicorn on exactly this address and polls this exact endpoint to decide
# the backend came up, so this reuses the established loopback contract rather
# than inventing a second one.
HEALTH_URL = os.getenv("API_ORIGIN", "http://127.0.0.1:8000").rstrip("/") + "/api/health"

# Deliberately short: this runs on every pass, and a health endpoint needing
# more than two seconds on loopback is itself the symptom.
HEALTH_TIMEOUT_S = 2.0

# `main` binds its own `log` as a local, so a module-level function cannot see
# it. Same name and same logger, taken at import.
_log = logging.getLogger("run_loop")


async def probe_hub_running(client) -> Optional[bool]:
    """Is the quote hub running? `None` when the question could not be asked.

    The WebSocket lives in the uvicorn process and the notifier lives in this
    one, so there is no in-process way to read it. `Alerter.check_feed` records
    why the obvious local alternative -- the age of the newest `kalshi_quotes`
    row -- is blind to the feed entirely.

    **Unreadable resolves to `None`, never to `False`.** A timeout, a 500 and a
    missing field all mean "the state is unknown", which is a different alert
    from "the hub is down"; reporting a dead feed because a probe timed out is
    the flattering-in-reverse version of the same defect. See `tasks/lessons.md`.
    """
    try:
        response = await client.get(HEALTH_URL, timeout=HEALTH_TIMEOUT_S)
        if response.status_code >= 400:
            _log.warning("health probe returned HTTP %d", response.status_code)
            return None
        value = response.json().get("live_quotes_available")
    except Exception:                                          # noqa: BLE001
        _log.warning("health probe failed", exc_info=True)
        return None
    # A missing key is unknown, not false. An older image that does not publish
    # the field must not be reported to a phone as a dead feed.
    return None if value is None else bool(value)


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
    # Loaded once, here, rather than inside the pass: a bad value announces at
    # ERROR and falls back to the default, and doing that on every pass would
    # be 96 identical ERROR lines a day -- the exact failure the pass itself was
    # just fixed for. It cannot raise; see `MarketResultConfig`.
    market_result_config = MarketResultConfig.load()
    suppression = SuppressionConfig()

    # The on-demand refresh inbox, and this process's watermark into it.
    #
    # **Initialised to now, not to zero.** A restart therefore ignores every tap
    # that predates it rather than replaying the file's whole retained tail as
    # new work -- which on a crash loop would re-buy the same fixtures once per
    # restart. A tap lost to a restart costs the person another tap; a tap
    # replayed costs credits nobody asked for, and only the first is
    # recoverable by the person holding the phone.
    refresh_inbox = ondemand.inbox_path(args.db)
    served_after = [db.now_ms()]

    def take_refresh_requests(stamp: int) -> list[ManualRefresh]:
        """Taps this pass should serve, and move the watermark past them.

        `ondemand.take` does not modify the file -- the API is its only writer
        -- so nothing but this watermark stops a request being served on every
        pass until it ages out. It is moved *before* the pass spends, so a pass
        that dies mid-sweep does not leave the request to be bought again.
        """
        due = ondemand.take(refresh_inbox, now_ms=stamp, after_ms=served_after[0])
        if not due:
            return []
        served_after[0] = max(r.requested_ms for r in due)
        log.info(
            "serving %d on-demand odds refresh(es): %s",
            len(due),
            ", ".join(
                f"{r.sport_key}"
                + (f"/props:{r.odds_event_id}" if r.odds_event_id else "")
                for r in due
            ),
        )
        return [
            ManualRefresh(sport_key=r.sport_key, odds_event_id=r.odds_event_id)
            for r in due
        ]

    # Two limits on one quantity. ADR 0019 section 6. Raises rather than warns:
    # the loop is the process that spends odds credits against this window, and
    # a divergence here is invisible from outside -- the phone would show one
    # schedule while the loop ran another.
    assert_odds_age_limits_agree(
        suppression_max_odds_age_ms=suppression.max_odds_age_ms,
        staleness=staleness,
    )
    # Its twin. This process already refused to start above when
    # `--fast-interval` cannot beat `MAX_KALSHI_QUOTE_AGE_S` -- that check reads
    # the env value while the suppression it then applies to every candidate
    # reads the hardcoded one, so without this the cadence check and the
    # gauntlet can be sized against two different limits.
    assert_kalshi_quote_age_limits_agree(
        suppression_max_kalshi_quote_age_ms=suppression.max_kalshi_quote_age_ms,
        staleness=staleness,
    )
    # The risk day, and this is the process that had it wrong: `runner.py:625`
    # read the daily realised P&L with no `day_start_hour` at all, so the kill
    # switch that suppresses every row on the slate ran on the hardcoded
    # constant while the order endpoint ran on the configured hour. That is now
    # passed at both entry points below; this refuses to start if the default
    # those signatures still carry has stopped matching what is deployed.
    assert_risk_day_start_agrees(
        default_day_start_hour=DEFAULT_DAY_START_UTC_HOUR, odds=odds_config,
    )
    budget = CreditBudget(
        conn,
        daily_budget=odds_config.daily_credit_budget,
        monthly_budget=odds_config.monthly_credit_budget,
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
            DiscordNotifier(discord_config) as discord, \
            httpx.AsyncClient(timeout=HEALTH_TIMEOUT_S) as health_client:

        alerter = Alerter(conn, discord)
        tempo = Tempo(
            slow_interval_s=args.interval, fast_interval_s=args.fast_interval
        )

        # The portfolio poller, beside the chain rather than inside a pass.
        # Its cadence is REGISTERED (calibration registration §7.6 as amended:
        # mirror 12h, balance 5min) and is not derived from this loop's tempo
        # -- the two schedules answer different questions and coupling them
        # would let a tempo change silently amend a protocol. It shares this
        # process's Kalshi client and opens its own DB connection, because a
        # concurrent task on the pass's connection would interleave two
        # transactions on one handle.
        #
        # Why it must live here at all: both portfolio endpoints have been
        # observed to DROP history (fills ~3 months; settlements lost 55
        # records inside eight days, 2026-08-18), and this process is the only
        # one that is always up. A poll that does not happen does not delay
        # the record -- it loses it. A failed cycle logs to poll_log and the
        # task continues; the registration's gap tripwires read poll_log, so
        # the loop surviving is what makes its own failures measurable.
        portfolio_task = asyncio.create_task(
            poll_portfolio_forever(args.db, kalshi),
            name="portfolio-poll",
        )

        def window_now():
            """The window as of *this instant*, from one expression.

            **One source, and it is the environment's.** ADR 0019 section 6.
            `staleness.max_odds_age_s * 1000` rather than
            `suppression.max_odds_age_ms`: the startup assertion guarantees they
            are equal today, and writing it once means they cannot drift if that
            assertion is ever relaxed.

            A function rather than a value because the answer changes *during* a
            pass -- the odds sweep inside `run_once` is what makes odds fresh,
            and fresh odds is the whole definition of `is_open`. Every caller
            asks at the moment it needs to know.

            **`desk_window` was missing here until 2026-08-25**, so this call
            answered a different question from the one the loop's own
            `decide_sweeps` asks four lines of config away: `window_status`
            predicts desk buys in `next_call_ms` and `first_window_open_ms`, and
            without the argument it predicted none. The loop was therefore
            logging a cadence it did not follow. It is the same value
            `run_once` hands `decide_sweeps` -- `OddsConfig.desk_window_utc` --
            because `timing.py`'s standing rule is one predicate and two
            callers, and this was the third.
            """
            return window_status(
                conn, budget=budget, now_ms=db.now_ms(),
                max_odds_age_ms=staleness.max_odds_age_s * 1000,
                sweep_cost=odds_config.credits_per_sweep_per_sport,
                desk_window=odds_config.desk_window_utc,
            )

        async def score_settle_and_alert(kind, counts, stamp, started):
            """Everything after the recording half of a pass.

            Split out only to name a failure boundary. Past this point an
            exception has already-written `recommendations` rows behind it, and
            the counts describing them are worth saying out loud before the
            traceback -- see `one_pass`.
            """
            scoring = settlement = market_results = None
            if kind == "full":
                scoring = await run_scoring_pass(conn, kalshi)
                # Full pass only. A settled market stays settled, so asking
                # every fifteen seconds during an open window would spend
                # requests to be told the same thing -- and the fast cadence
                # exists to keep quotes inside 30s, which this does not touch.
                settlement = await run_settlement_pass(conn, kalshi)
                # Same cadence and the same reason, and one request per event
                # rather than per market. This is the only writer of
                # `kalshi_markets.result`, which was NULL for every row of the
                # project's life. It is also the only *anything* for that
                # column: nothing reads it yet, so this gives calibration its
                # inputs rather than making calibration possible -- see
                # `backend/market_results.py`.
                market_results = await run_market_result_pass(
                    conn, kalshi, config=market_result_config
                )

            # **One source, and it is the environment's.** ADR 0019 section 6.
            # This used to pass `suppression.max_odds_age_ms` -- a hardcoded
            # 900_000 -- while `routes.py` passed `staleness.max_odds_age_s *
            # 1000` to the same function. Same planner, different inputs, so
            # the docstring at `routes.py` promising "not a second
            # implementation... the screen is the one that gets believed" was
            # defending against the wrong layer. Sharing an implementation does
            # not share its arguments.
            #
            # The startup assertion above guarantees these are equal today; this
            # makes them the same expression, so they cannot drift even if that
            # assertion is ever relaxed.
            window = window_now()
            # Alerting on a quote pass too, deliberately. A quote pass is when a
            # price moves inside the window, so it is exactly when a new
            # opportunity appears -- and the dedupe lives in `notifications`, so
            # a row already announced is not announced again.
            alerts = await alerter.after_pass(
                pass_ms=stamp, counts=counts, window=window,
                sweeps_this_pass=counts.odds_sweeps,
            )

            # **The failure checks run on every pass, beside the good news.**
            # Here rather than behind `if kind == "full"` on purpose: a feed
            # dies at a moment, not at a cadence, and the quote pass is the
            # frequent one. Both dedupe to once per kind per day in
            # `notifications`, so a per-pass call costs one INSERT that
            # conflicts.
            #
            # `markets_quoted` is the denominator that keeps this quiet
            # overnight -- it is what `store_quotes_from_discovery` actually
            # wrote this pass, so zero means there was nothing to feed rather
            # than nothing arriving. Without it the watchdog buzzes every night
            # and the channel gets muted, which is worse than no channel.
            await alerter.check_feed(
                now_ms=stamp,
                hub_running=await probe_hub_running(health_client),
                markets_priced=counts.markets_quoted,
            )
            # `budget.state(stamp).remaining_today`, not `budget.remaining_today()`
            # -- `remaining_today` is a PROPERTY on `BudgetState`, which
            # `CreditBudget.state()` returns. The wrong spelling shipped to
            # live on 2026-08-18 and raised AttributeError on every pass; see
            # `tasks/lessons.md`. `state()` runs two SUMs over `api_credits`
            # once per pass, which is the same cost `decide_sweeps` already
            # pays each pass.
            await alerter.check_credits(
                now_ms=stamp,
                remaining_today=budget.state(stamp).remaining_today,
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
            # And when the next one opens, so a closed-window sleep is bounded
            # by it. Without this the loop picks 900s at the top of a pass and a
            # window opening inside that sleep is invisible until it ends -- up
            # to fifteen minutes of an open window lost after a restart,
            # observed 20:39Z 2026-08-19. `next_call_ms` is the planner's own
            # answer, through `firing_for_slot`, the same predicate the loop
            # fires on; computing a second schedule here is how the screen and
            # the control come to disagree.
            tempo.next_wake_ms = window.next_call_ms
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
                settlement=settlement, market_results=market_results,
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
                    # Retention is skipped while a window is open, and this
                    # is a **callable** so the answer is read at the prune
                    # rather than here.
                    #
                    # It used to pass `tempo.window_open`, which is assigned at
                    # the *end* of a pass and read at the *start* of the next
                    # one. That let the prune through two ways. The stale flag
                    # is the measured one -- `15:32:14 full took_s 94.3
                    # quotes_pruned 40000` on 2026-08-19 with the window open
                    # since 15:21Z. The other is worse and a pre-pass read
                    # cannot catch it: `run_once` fires the odds sweep and
                    # *then* prunes, so a full pass that opens a window prunes
                    # inside the first ~40-94s of it, every time.
                    window_open=lambda: window_now().is_open,
                )
            else:
                # Kalshi, plus the odds refresh that keeps an already-open
                # window from shutting. Still no candlesticks and no digest --
                # the point is to re-confirm the quote behind every row before
                # its 30s runs out, and to re-buy the consensus behind it before
                # its 900s does.
                #
                # **This pass can now spend credits, which it could not before.**
                # It is paced by `refresh_interval_ms` inside `decide_sweeps`,
                # not by this interval: the pass asks on every tick and is told
                # "not yet" on all but one in forty. It is bounded above by the
                # same `budget.refusal_reason` as every other call, and it
                # cannot bootstrap -- see `run_quote_pass`, which owns both
                # arguments.
                counts = await run_quote_pass(
                    conn, kalshi, odds_client=odds, budget=budget,
                    config=odds_config,
                    risk=risk, suppression=suppression, now=stamp,
                    # Taps, read here rather than inside the pass so the pass
                    # keeps exactly one way to be told to spend. `served_after`
                    # is this process's watermark and moves only forward, which
                    # is what makes a request served once: the inbox file is
                    # written by the API and never by us -- see
                    # `backend/odds/ondemand.py` for why it is single-writer.
                    manual=take_refresh_requests(stamp),
                    # Passed explicitly rather than derived, and that is still
                    # true now the pass takes an `OddsConfig`: this is the site
                    # that would silently fall back to the constant. It runs ~96
                    # times a day against the full pass's ~1, so it is the
                    # majority of the slates the kill switch is applied to.
                    day_start_hour=odds_config.budget_day_start_utc_hour,
                )

            with counts_survive_a_late_failure(log, kind, counts):
                return await score_settle_and_alert(kind, counts, stamp, started)

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
            await alerter.failure(FAILURE_LOOP_DIED, str(exc), now_ms=db.now_ms())
            raise
        finally:
            # The poller dies with the loop, by design: the entrypoint restarts
            # the whole container when the runner exits, and a poller outliving
            # a dead runner would hold the DB and the client half-alive.
            portfolio_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await portfolio_task
            log.info(
                "loop state at exit: %s tempo: %s", state.as_dict(), tempo.as_dict()
            )

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
