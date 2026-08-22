"""Fetching closing lines and scoring recommendations on CLV.

`analysis/clv.py` has had `score_recommendations` since the evidence layer was
built, and **nothing ever called it**. It scores rows that already have a
`closing_lines` entry, and nothing ever wrote one -- so no recommendation could
ever be scored, and the gate's 300-observation counter was structurally pinned
at zero however long the runner ran. This module is the missing half.

Which clock is "the close"
--------------------------
The reference instant is the **sportsbook's** commence time, not Kalshi's.

Kalshi's `occurrence_datetime` runs exactly 3 hours late (measured across MLB
and WNBA, see `match/linker.py`). Using it here would not merely be untidy: a
"one hour before close" reading taken against a clock that is three hours late
lands **two hours after the game actually started**. That is a quote taken while
the outcome is partly known, which is the precise contamination this module's
horizon exists to avoid -- and it would have produced a strong, entirely fake
CLV signal, because a price that has already moved toward the result looks like
a price we beat.

So the true start is read back through `event_links` from the odds fixture,
whose commence time agrees with the ticker and with reality.

Two horizons, one scored
------------------------
Closing lines are stored at both the primary and control horizons, because
`horizons_agree` compares them and a finding that moves between horizons was
convergence. Only the **primary** horizon is scored into `clv_tenths`:
`score_recommendations` fills in whatever is unscored, so calling it at two
horizons would leave the column a silent mixture of both with no way to tell
which row came from which.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from .analysis.clv import (
    CONTROL_HORIZON_HOURS,
    DEFAULT_HORIZON_HOURS,
    ClosingLine,
    parse_candlestick,
    score_recommendations,
    store_closing_line,
)
from .store.db import now_ms

logger = logging.getLogger(__name__)

# How wide a candlestick window to request around each horizon target. One
# minute of resolution, looking back a quarter of an hour, so a market with no
# print exactly on the target still yields the most recent quote before it.
WINDOW_MINUTES = 15
CANDLE_INTERVAL_MINUTES = 1


@dataclass
class ScoringCounts:
    markets_considered: int = 0
    not_started_yet: int = 0
    lines_stored: int = 0
    candles_missing: int = 0
    unreadable_quotes: int = 0
    scored: int = 0
    skipped_no_mid: int = 0
    skipped_entry_after_close: int = 0
    # How many (recommendation, closing line) pairs the join produced at
    # all. Zero here means no unscored recommendation shares a ticker and
    # horizon with a stored line -- a different problem from every pair
    # being skipped, and indistinguishable without this.
    rows_joined: int = 0
    errors: list[str] = field(default_factory=list)

    # Always reported, even at zero. `scored: 0` alone cannot distinguish "the
    # join matched nothing" from "everything matched and was skipped", and those
    # need completely different fixes. Hiding a zero skip-count made a live pass
    # unreadable: 14 closing lines stored, 0 scored, and no way to tell which
    # branch it took.
    ALWAYS_REPORT = (
        "scored",
        "skipped_no_mid",
        "skipped_entry_after_close",
        "rows_joined",
    )

    def as_dict(self) -> dict[str, Any]:
        return {
            k: v
            for k, v in self.__dict__.items()
            if v or k in self.ALWAYS_REPORT
        }


def markets_awaiting_scoring(conn, *, now: int) -> list[dict[str, Any]]:
    """Markets whose game has started and that still need a closing line.

    Two sources, unioned. The first is unscored `recommendations` -- unchanged
    from before. The second is Joe's own settled bets (`venue_settlements`),
    added 2026-08-22 so his hand-placed positions get CLV too: a market only
    reaches this branch once it has a `kalshi_markets` row (discovery found
    it) and an `event_links` row (the matcher linked it) -- most hand-bet
    tickers refuse right there, which is expected and honest, not a bug to
    chase (the partner's ruling on the re-scoped CLV item).

    The commence time comes from the linked **odds** fixture in both branches.
    See the module docstring -- taking it from `kalshi_events` would place
    every reading two hours into the game.

    The venue-settlements branch stops once ANY `closing_lines` row exists for
    the ticker, at any horizon -- unlike the recommendations branch, there is
    no `clv_scored_ms` to flip, so without this stop-predicate a hand-bet
    ticker would be re-fetched every pass forever.

    A market is only returned once its true start has passed, because a closing
    line does not exist until then. Rows for games still ahead are counted as
    `not_started_yet`, which is a normal state and not a failure.
    """
    rows = conn.execute(
        """
        SELECT DISTINCT r.ticker,
               m.series_ticker,
               o.commence_ms AS true_commence_ms
        FROM recommendations r
        JOIN event_links l   ON l.id = r.link_id
        JOIN kalshi_markets m ON m.ticker = r.ticker
        JOIN (
            SELECT odds_event_id, MIN(commence_ms) AS commence_ms
            FROM odds_snapshots GROUP BY odds_event_id
        ) o ON o.odds_event_id = l.odds_event_id
        WHERE r.clv_scored_ms IS NULL
          AND m.series_ticker IS NOT NULL

        UNION

        SELECT DISTINCT v.ticker,
               m.series_ticker,
               o.commence_ms AS true_commence_ms
        FROM venue_settlements v
        JOIN kalshi_markets m ON m.ticker = v.ticker
        JOIN event_links l   ON l.kalshi_event_ticker = m.event_ticker
        JOIN (
            SELECT odds_event_id, MIN(commence_ms) AS commence_ms
            FROM odds_snapshots GROUP BY odds_event_id
        ) o ON o.odds_event_id = l.odds_event_id
        WHERE m.series_ticker IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM closing_lines c WHERE c.ticker = v.ticker
          )
        """
    ).fetchall()

    return [
        {
            "ticker": r["ticker"],
            "series_ticker": r["series_ticker"],
            "true_commence_ms": int(r["true_commence_ms"]),
            "started": int(r["true_commence_ms"]) <= now,
        }
        for r in rows
    ]


async def fetch_closing_line(
    kalshi_client,
    *,
    series_ticker: str,
    ticker: str,
    true_commence_ms: int,
    horizon_hours: float,
) -> Optional[ClosingLine]:
    """Read the quote `horizon_hours` before the true start.

    The window **ends** at the target instant, so the last candle returned is
    the most recent quote at or before it. That is deliberate: it means no
    candle timestamp has to be parsed to pick the right one, and therefore no
    guess is made about a field name this project has never captured. The
    timestamp is read opportunistically for `observed_ms` and falls back to the
    requested target, which is the honest description of what was asked for.

    Returns `None` when the window is empty -- a market with no quotes in that
    minute range. The caller counts that rather than substituting a price.
    """
    target_ms = true_commence_ms - int(horizon_hours * 3_600_000)
    # Kalshi's candlestick endpoint takes epoch SECONDS. Converted here and not
    # propagated -- every other timestamp in this codebase is milliseconds.
    end_ts = target_ms // 1000
    start_ts = end_ts - WINDOW_MINUTES * 60

    candles = await kalshi_client.candlesticks(
        series_ticker,
        ticker,
        start_ts=start_ts,
        end_ts=end_ts,
        period_interval=CANDLE_INTERVAL_MINUTES,
    )
    if not candles:
        return None

    last = candles[-1]
    yes_bid, yes_ask = parse_candlestick(last)
    observed = last.get("end_period_ts")
    observed_ms = int(observed) * 1000 if isinstance(observed, (int, float)) else target_ms

    return ClosingLine(
        ticker=ticker,
        horizon_hours=horizon_hours,
        observed_ms=observed_ms,
        yes_bid_tenths=yes_bid,
        yes_ask_tenths=yes_ask,
    )


async def run_scoring_pass(
    conn,
    kalshi_client,
    *,
    now: Optional[int] = None,
    primary_horizon: float = DEFAULT_HORIZON_HOURS,
    control_horizon: float = CONTROL_HORIZON_HOURS,
    max_markets: Optional[int] = None,
) -> ScoringCounts:
    """Fetch closing lines for started games, then score at the primary horizon.

    Failures on one market are recorded and the pass continues. A single market
    whose candlesticks 404 must not stop the other thirty from being scored --
    an observation lost is indistinguishable from one never generated.
    """
    stamp = now if now is not None else now_ms()
    counts = ScoringCounts()

    pending = markets_awaiting_scoring(conn, now=stamp)
    counts.markets_considered = len(pending)
    ready = [m for m in pending if m["started"]]
    counts.not_started_yet = len(pending) - len(ready)
    if max_markets is not None:
        ready = ready[:max_markets]

    for market in ready:
        for horizon in (primary_horizon, control_horizon):
            try:
                line = await fetch_closing_line(
                    kalshi_client,
                    series_ticker=market["series_ticker"],
                    ticker=market["ticker"],
                    true_commence_ms=market["true_commence_ms"],
                    horizon_hours=horizon,
                )
            except Exception as exc:                      # noqa: BLE001
                counts.errors.append(f"{market['ticker']}@{horizon}h: {exc}")
                continue

            if line is None:
                counts.candles_missing += 1
                continue
            if line.mid_tenths is None:
                # One side unreadable. Stored anyway -- `score_recommendations`
                # skips it and counts it, and a stored row with a NULL side is
                # evidence that the market was thin at that moment, which a
                # missing row is not.
                counts.unreadable_quotes += 1
            store_closing_line(conn, line)
            counts.lines_stored += 1

    # Primary horizon only. Scoring at both would make `clv_tenths` a mixture
    # with no column saying which horizon produced which row.
    scored = score_recommendations(conn, horizon_hours=primary_horizon, scored_ms=stamp)
    counts.scored = scored.get("scored", 0)
    counts.skipped_no_mid = scored.get("skipped_no_mid", 0)
    counts.skipped_entry_after_close = scored.get("skipped_entry_after_close", 0)
    counts.rows_joined = scored.get("rows_joined", 0)

    logger.info("scoring pass: %s", counts.as_dict())
    return counts
