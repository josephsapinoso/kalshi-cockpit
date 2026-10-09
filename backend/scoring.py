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

Two arms, one set of lines
--------------------------
Since 2026-09-01 the pass scores a second population against the same closing
lines: Joe's own decoupled calls in `bet_estimates` (ticket #11), through
`score_bet_estimate_calls`. It costs no extra fetch -- every market a call can
be logged against is already in the closing-line set, because the digest that
offers the call is built from the same `recommendations JOIN event_links` that
this module's first branch walks.

**What that arm cannot establish is stated in its own docstring and is not
repeated here in a form that could drift from it.** In one line: it scores a
stated probability against the market's close, never against the outcome, so it
measures disagreement with Kalshi and not correctness.
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from .analysis.clv import (
    CONTROL_HORIZON_HOURS,
    DEFAULT_HORIZON_HOURS,
    ClosingLine,
    parse_candlestick,
    score_bet_estimate_calls,
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
    #: Lines fetched successfully and then refused by the DATABASE on write.
    #:
    #: Its own counter rather than a line in `errors`, because it is the only
    #: one of these that means *the observation existed and we lost it*. A
    #: 404 from candlesticks is history the venue no longer has; a failed store
    #: is history we held and dropped, and an unrecorded close is gone for good
    #: once candlesticks age out. Mixing the two in one list made a lock storm
    #: read like a bad night for the candle endpoint.
    lines_unstored: int = 0
    scored: int = 0
    skipped_no_mid: int = 0
    skipped_entry_after_close: int = 0
    # How many (recommendation, closing line) pairs the join produced at
    # all. Zero here means no unscored recommendation shares a ticker and
    # horizon with a stored line -- a different problem from every pair
    # being skipped, and indistinguishable without this.
    rows_joined: int = 0
    #: The decoupled-call arm (ticket #11), counted separately from the
    #: recommendation arm on purpose. They read the same `closing_lines` rows
    #: and write different tables, so one pooled `scored` would hide an arm
    #: that had stopped working behind an arm that had not.
    calls_scored: int = 0
    calls_skipped_no_mid: int = 0
    calls_skipped_entry_after_close: int = 0
    calls_rows_joined: int = 0
    #: The third population (ADR 0194 s2.2, #323): combination legs Joe holds.
    #: Counted apart from `lines_stored` on purpose -- a leg's close goes on
    #: its own row, never into `closing_lines`, so folding the two together
    #: would hide an arm that had stopped behind one that had not.
    leg_closes_stored: int = 0
    leg_rows_closed: int = 0
    leg_closes_unreadable: int = 0
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
        # Same argument, same four shapes, for the call arm. `calls_scored: 0`
        # alone cannot distinguish "no call is waiting" from "every call was
        # refused", and at n=1 in the whole record the second is the state
        # that needs seeing.
        "calls_scored",
        "calls_skipped_no_mid",
        "calls_skipped_entry_after_close",
        "calls_rows_joined",
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

    **A third population, since #323 / ADR 0194: the legs of a combination Joe
    holds** (`parlay_position_legs` rows with a ticker and no close yet). Each
    returned dict says which population(s) a ticker is in:

        awaits_closing_line   the first two branches -- the pass stores a
                              `closing_lines` row, as it always has
        awaits_leg_close      the leg branch -- the pass stores the close ON
                              THE LEG ROW and **never** in `closing_lines`
                              (ADR 0194 s2.3: a held leg's row there would
                              enter the gate's CLV population)

    A ticker in both is returned once. The leg branch reads the true start
    from `odds_fixtures` through `event_links` -- one row per game, the
    trigger-maintained schedule -- and never from `odds_snapshots`, so it
    adds no aggregate over that table; and never from `kalshi_events`, whose
    clock runs three hours late. `tests/test_scoring.py::TestCombinationLegs`
    pins its plan onto `idx_parlay_position_legs_ticker`.
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
            FROM odds_snapshots
            WHERE odds_event_id IN (SELECT odds_event_id FROM event_links)
            GROUP BY odds_event_id
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
            FROM odds_snapshots
            WHERE odds_event_id IN (SELECT odds_event_id FROM event_links)
            GROUP BY odds_event_id
        ) o ON o.odds_event_id = l.odds_event_id
        WHERE m.series_ticker IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM closing_lines c WHERE c.ticker = v.ticker
          )
        """
    ).fetchall()

    merged: dict[str, dict[str, Any]] = {}
    for r in rows:
        merged[r["ticker"]] = {
            "ticker": r["ticker"],
            "series_ticker": r["series_ticker"],
            "true_commence_ms": int(r["true_commence_ms"]),
            "started": int(r["true_commence_ms"]) <= now,
            "awaits_closing_line": True,
            "awaits_leg_close": False,
        }

    for r in conn.execute(LEG_CLOSE_SQL).fetchall():
        entry = merged.get(r["ticker"])
        if entry is None:
            merged[r["ticker"]] = {
                "ticker": r["ticker"],
                "series_ticker": r["series_ticker"],
                "true_commence_ms": int(r["true_commence_ms"]),
                "started": int(r["true_commence_ms"]) <= now,
                "awaits_closing_line": False,
                "awaits_leg_close": True,
            }
        else:
            entry["awaits_leg_close"] = True
    return list(merged.values())


#: ADR 0194 s2.2: held combination legs still without a close. `IS NOT NULL`
#: on the ticker is what lets the planner use the partial index
#: `idx_parlay_position_legs_ticker`. The start is `odds_fixtures`' (one row
#: per game), never `kalshi_events`'. MIN per ticker: an event can carry more
#: than one `event_links` row, and the earliest recorded start is the same
#: reschedule-protecting choice the other branches make.
LEG_CLOSE_SQL = """
    SELECT pl.ticker,
           m.series_ticker,
           MIN(f.commence_ms) AS true_commence_ms
    FROM parlay_position_legs pl
    JOIN kalshi_markets m ON m.ticker = pl.ticker
    JOIN event_links l    ON l.kalshi_event_ticker = m.event_ticker
    JOIN odds_fixtures f  ON f.odds_event_id = l.odds_event_id
    WHERE pl.ticker IS NOT NULL
      AND pl.close_yes_bid_tenths IS NULL
      AND pl.close_yes_ask_tenths IS NULL
      AND m.series_ticker IS NOT NULL
    GROUP BY pl.ticker, m.series_ticker
"""


def store_leg_close(conn, line: ClosingLine) -> int:
    """Write a close onto every still-open leg row for the line's ticker.

    **Never `store_closing_line`** (ADR 0194 s2.3). A ticker can sit in more
    than one leg row (two positions, or two bets on one card); every row whose
    close is still NULL takes it, and a row that already has one is left alone.
    Returns how many rows were written.
    """
    cursor = conn.execute(
        "UPDATE parlay_position_legs "
        "SET close_yes_bid_tenths = ?, close_yes_ask_tenths = ?, "
        "    close_observed_ms = ? "
        "WHERE ticker = ? AND close_yes_bid_tenths IS NULL "
        "  AND close_yes_ask_tenths IS NULL",
        (line.yes_bid_tenths, line.yes_ask_tenths, line.observed_ms, line.ticker),
    )
    conn.commit()
    return cursor.rowcount


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
        # A leg-only ticker needs the primary horizon alone: its close is one
        # number on the leg row, with no control horizon to compare against.
        horizons = (
            (primary_horizon, control_horizon)
            if market["awaits_closing_line"]
            else (primary_horizon,)
        )
        for horizon in horizons:
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
            if market["awaits_leg_close"] and horizon == primary_horizon:
                if line.yes_bid_tenths is None and line.yes_ask_tenths is None:
                    # Same rule as the backfill: a bar with neither side is
                    # not a close, so the legs keep NULL and it is counted.
                    counts.leg_closes_unreadable += 1
                else:
                    try:
                        written = store_leg_close(conn, line)
                    except Exception as exc:              # noqa: BLE001
                        with contextlib.suppress(Exception):
                            conn.rollback()
                        counts.errors.append(
                            f"{market['ticker']}@{horizon}h: leg close "
                            f"store failed: {exc}"
                        )
                    else:
                        counts.leg_closes_stored += 1
                        counts.leg_rows_closed += written
            if not market["awaits_closing_line"]:
                continue
            if line.mid_tenths is None:
                # One side unreadable. Stored anyway -- `score_recommendations`
                # skips it and counts it, and a stored row with a NULL side is
                # evidence that the market was thin at that moment, which a
                # missing row is not.
                counts.unreadable_quotes += 1
            # **The store is inside the guard, and until 2026-08-31 it was
            # not.** The docstring above already promised that one market's
            # failure must not stop the other thirty; the `try` delivered that
            # for the FETCH and left the write outside it. So a
            # `database is locked` on one line -- which happened four to five
            # times a day (ADR 0091) -- escaped `run_scoring_pass`, killed the
            # whole pass, and abandoned every market still in the loop.
            #
            # That is the expensive direction. A closing line not stored is
            # not deferred, it is lost: candlesticks age out, and the game
            # only closes once.
            #
            # ADR 0091 fixed the biggest lock HOLDER. This makes the loop
            # survive the next one, whatever it turns out to be -- the two are
            # different repairs and neither substitutes for the other.
            try:
                store_closing_line(conn, line)
            except Exception as exc:                      # noqa: BLE001
                # Rolled back so the next iteration starts clean: a connection
                # left mid-transaction fails every subsequent store in the
                # pass, which would turn one lost line into all of them.
                with contextlib.suppress(Exception):
                    conn.rollback()
                counts.lines_unstored += 1
                counts.errors.append(
                    f"{market['ticker']}@{horizon}h: store failed: {exc}"
                )
                continue
            counts.lines_stored += 1

    # Primary horizon only. Scoring at both would make `clv_tenths` a mixture
    # with no column saying which horizon produced which row.
    scored = score_recommendations(conn, horizon_hours=primary_horizon, scored_ms=stamp)
    counts.scored = scored.get("scored", 0)
    counts.skipped_no_mid = scored.get("skipped_no_mid", 0)
    counts.skipped_entry_after_close = scored.get("skipped_entry_after_close", 0)
    counts.rows_joined = scored.get("rows_joined", 0)

    # Joe's own calls, on the same lines and the same horizon (ticket #11).
    #
    # **This arm needs no new closing line and that is the point.** `/api/slate`
    # is `recommendations JOIN event_links`, and `markets_awaiting_scoring`'s
    # first branch is that same join -- so every market reachable from the
    # window-open digest is already in the closing-line set by construction,
    # its line fetched before a call on it could be logged. Measured on live
    # 2026-09-01 at the 1h horizon: 136/136 WNBA, 578/604 MLB, 16/16 started
    # NCAAF. A third UNION branch is only needed if logging is ever offered
    # outside the slate.
    #
    # Primary horizon only, for the reason the line above it gives: scoring at
    # both would make `call_clv_tenths` a mixture with no column saying which
    # horizon produced which row.
    calls = score_bet_estimate_calls(
        conn, horizon_hours=primary_horizon, scored_ms=stamp
    )
    counts.calls_scored = calls.get("scored", 0)
    counts.calls_skipped_no_mid = calls.get("skipped_no_mid", 0)
    counts.calls_skipped_entry_after_close = calls.get(
        "skipped_entry_after_close", 0
    )
    counts.calls_rows_joined = calls.get("rows_joined", 0)

    logger.info("scoring pass: %s", counts.as_dict())
    return counts
