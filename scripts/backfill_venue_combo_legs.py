"""Read the legs, results and leg prices of combinations bought OFF the desk.

    python /app/scripts/backfill_venue_combo_legs.py --db /data/cockpit.db --dry-run --limit 400
    python /app/scripts/backfill_venue_combo_legs.py --db /data/cockpit.db --commit  --limit 400

Why this exists (ADR 0197, schema v69)
--------------------------------------
Joe tails parlays and buys them in the Kalshi app, so most of his settled
combinations reached this instance as a settlement with no leg list. He asked
what made the winning ones win (2026-11-11) and the record could not say what
any of them was made of. The portfolio poller now reads a few combinations'
legs every five minutes (`portfolio_poll.poll_venue_combo_legs`); this script
does the same three passes in bulk, and the one pass the poller does not do.

Three passes, in order, each bounded by `--limit`
-------------------------------------------------
1. **Legs.** `backend.venue_combo_legs.capture_legs`: the venue's own market
   for each combination with no legs anywhere, all legs or none.
2. **Results.** `capture_results`: each leg market's own `yes`/`no`, for the
   legs discovery never resolved. NULL-only.
3. **Prices.** For each leg, the candle ask at purchase and the close, exactly
   as `scripts/backfill_leg_prices.py` fills a held leg (its helpers are
   imported, not copied). The purchase instant is the combination's
   `venue_settlements.position_first_seen_ms`, and ONLY where
   `position_time_source = 'fill_created_time'`: a poll instant or a
   settlement time is not when he bought. Every UPDATE carries `IS NULL`.
   Each leg the pass finishes with is stamped `price_read_ms`, so a bounded
   run moves on instead of re-reading legs whose bars are gone.

   **Bars are read from the live endpoint, then from the venue's archive.**
   `/series/{s}/markets/{t}/candlesticks` keeps about 80 days (ADR 0016) and
   answered 404 on 2026-11-11 for a market that closed 2026-09-04;
   `/historical/markets/{t}/candlesticks` answered 200 for the same market
   and window. The archive's bar spells the close `close` where the live one
   spells it `close_dollars` (`tests/fixtures/candlesticks_historical_archive.json`),
   so `archive_bar` renames that one key and nothing else.

`--dry-run` reads the venue and prints the counts it WOULD write; `--commit`
writes. Both print counts only -- no ticker, no label, no price -- because the
box's stdout lands in a public log and operator data never enters the repo.

What it writes, and only that
-----------------------------
`venue_combo_legs` and `venue_combo_leg_refusals`. Never a money column,
never `closing_lines`, never a table `backend/gate.py` reads (ADR 0063).

What this does not establish
----------------------------
- Nothing about a combination the venue no longer serves (`not_found`).
- Nothing about a leg neither endpoint has bars for: its ask stays NULL.
- How far back the archive goes. One August market answered; that is one
  market, and `no_bars_ask` is the count of the ones that did not.
- Nothing about a leg's close where no odds fixture is linked to its event
  (`no_link`). Most legs here are in sports the desk does not follow, so
  expect that count to be large.
- That a bar's close equals the ask his fill crossed (it is the minute's).
- Who built any of these combinations. That is Joe's word, never this data.
- Nothing that needs a credential: every read here is unauthenticated.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import venue_combo_legs as vcl  # noqa: E402
from backend.analysis.clv import DEFAULT_HORIZON_HOURS, parse_candlestick  # noqa: E402
from backend.store.db import open_db  # noqa: E402
from scripts.backfill_leg_prices import (  # noqa: E402
    PUBLIC_REST_URL,
    PUBLIC_TIMEOUT_S,
    PublicCandles,
    ask_for_side,
    last_bar,
    observed_ms_of,
    true_commence_ms,
)

DEFAULT_LIMIT = 400

#: The only purchase clock the price pass trusts.
FILL_TIME_SOURCE = "fill_created_time"


class PublicMarkets:
    """Unauthenticated market reads: `path -> payload`, or None on a 404."""

    def __init__(self, client: Any, *, base_url: str = PUBLIC_REST_URL) -> None:
        self._client = client
        self._base = base_url.rstrip("/")

    async def __call__(self, path: str) -> Optional[dict]:
        response = None
        for attempt in range(5):
            response = await self._client.get(f"{self._base}{path}")
            if response.status_code == 429:
                await asyncio.sleep(0.5 * (attempt + 1))
                continue
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
        response.raise_for_status()
        return None


def archive_bar(bar: dict) -> dict:
    """An archive bar in the live endpoint's spelling.

    Only `yes_bid.close` and `yes_ask.close` are renamed to `close_dollars`,
    the one key `parse_candlestick` reads, and only where the live key is
    absent. Verified against a capture, not guessed: the parser's own
    docstring is about what guessing this key cost last time.
    """
    out = dict(bar)
    for side in ("yes_bid", "yes_ask"):
        block = bar.get(side)
        if isinstance(block, dict) and "close_dollars" not in block and "close" in block:
            out[side] = {**block, "close_dollars": block["close"]}
    return out


class CandlesWithArchive:
    """Live candlesticks first; the venue's archive when the live read is empty."""

    def __init__(self, client: Any, *, base_url: str = PUBLIC_REST_URL) -> None:
        self._live = PublicCandles(client, base_url=base_url)
        self._markets = PublicMarkets(client, base_url=base_url)
        self.archive_reads = 0

    async def candlesticks(
        self, series_ticker: str, ticker: str, *, start_ts: int, end_ts: int,
        period_interval: int,
    ) -> list[dict]:
        bars = await self._live.candlesticks(
            series_ticker, ticker, start_ts=start_ts, end_ts=end_ts,
            period_interval=period_interval,
        )
        if bars:
            return bars
        payload = await self._markets(
            f"/historical/markets/{ticker}/candlesticks"
            f"?start_ts={int(start_ts)}&end_ts={int(end_ts)}"
            f"&period_interval={int(period_interval)}"
        )
        archived = (payload or {}).get("candlesticks") or []
        if archived:
            self.archive_reads += 1
        return [archive_bar(bar) for bar in archived if isinstance(bar, dict)]


def legs_needing_prices(conn: sqlite3.Connection, *, limit: int) -> list[sqlite3.Row]:
    """Legs the price pass has not finished with, oldest purchase first.

    Oldest first because the venue's bars run out oldest first, and safe to
    order that way because a finished leg is stamped and leaves the queue.
    """
    return conn.execute(
        """
        SELECT l.id, l.ticker, l.side, l.event_ticker,
               l.ask_at_purchase_tenths, l.close_yes_bid_tenths,
               l.close_yes_ask_tenths, m.series_ticker,
               (SELECT MIN(s.position_first_seen_ms) FROM venue_settlements s
                 WHERE s.ticker = l.combo_ticker
                   AND s.position_time_source = ?) AS placed_ms,
               (SELECT MIN(s.settled_ms) FROM venue_settlements s
                 WHERE s.ticker = l.combo_ticker) AS settled_ms
        FROM venue_combo_legs l
        LEFT JOIN kalshi_markets m ON m.ticker = l.ticker
        WHERE l.price_read_ms IS NULL
        ORDER BY settled_ms IS NULL, settled_ms, l.id
        LIMIT ?
        """,
        (FILL_TIME_SOURCE, int(limit)),
    ).fetchall()


async def fill_prices(
    conn: sqlite3.Connection,
    candles: Any,
    *,
    limit: int,
    commit: bool,
    now_ms: int,
) -> dict[str, Any]:
    """The candle ask at purchase and the close, for legs not yet tried."""
    counts: dict[str, Any] = {
        "legs_considered": 0, "asks_written": 0, "closes_written": 0,
        "no_fill_time": 0, "series_from_ticker": 0, "no_link": 0,
        "not_started": 0, "no_bars_ask": 0, "no_bars_close": 0,
        "unreadable_ask": 0, "unreadable_close": 0, "errors": 0,
    }
    for row in legs_needing_prices(conn, limit=limit):
        counts["legs_considered"] += 1
        leg_id, ticker, side = int(row["id"]), str(row["ticker"]), str(row["side"])
        finished = True
        try:
            series = row["series_ticker"]
            if not series:
                counts["series_from_ticker"] += 1
                series = ticker.split("-", 1)[0]

            if row["ask_at_purchase_tenths"] is None:
                placed_ms = row["placed_ms"]
                if placed_ms is None:
                    counts["no_fill_time"] += 1
                else:
                    bar = await last_bar(candles, str(series), ticker, end_ms=int(placed_ms))
                    if bar is None:
                        counts["no_bars_ask"] += 1
                    else:
                        ask = ask_for_side(bar, side)
                        if ask is None:
                            counts["unreadable_ask"] += 1
                        else:
                            counts["asks_written"] += 1
                            if commit:
                                conn.execute(
                                    "UPDATE venue_combo_legs "
                                    "SET ask_at_purchase_tenths = ?, ask_source = 'candle' "
                                    "WHERE id = ? AND ask_at_purchase_tenths IS NULL",
                                    (int(ask), leg_id),
                                )

            if row["close_yes_bid_tenths"] is None and row["close_yes_ask_tenths"] is None:
                commence = true_commence_ms(conn, row["event_ticker"])
                if commence is None:
                    counts["no_link"] += 1
                else:
                    target = commence - int(DEFAULT_HORIZON_HOURS * 3_600_000)
                    if target > now_ms:
                        counts["not_started"] += 1
                        finished = False
                    else:
                        bar = await last_bar(candles, str(series), ticker, end_ms=target)
                        if bar is None:
                            counts["no_bars_close"] += 1
                        else:
                            yes_bid, yes_ask = parse_candlestick(bar)
                            if yes_bid is None and yes_ask is None:
                                counts["unreadable_close"] += 1
                            else:
                                counts["closes_written"] += 1
                                if commit:
                                    conn.execute(
                                        "UPDATE venue_combo_legs "
                                        "SET close_yes_bid_tenths = ?, close_yes_ask_tenths = ?, "
                                        "    close_observed_ms = ? "
                                        "WHERE id = ? AND close_yes_bid_tenths IS NULL "
                                        "  AND close_yes_ask_tenths IS NULL",
                                        (yes_bid, yes_ask, observed_ms_of(bar, target), leg_id),
                                    )
        except Exception:  # noqa: BLE001 -- one leg's failure must not end the run
            counts["errors"] += 1
            finished = False
        if commit:
            # A locked database must not end the pass (#428): the leg keeps
            # its place in the queue and the next pass reads it again.
            try:
                if finished:
                    conn.execute(
                        "UPDATE venue_combo_legs SET price_read_ms = ? WHERE id = ?",
                        (int(now_ms), leg_id),
                    )
                conn.commit()
            except sqlite3.OperationalError:
                conn.rollback()
                counts["write_errors"] = counts.get("write_errors", 0) + 1
    return counts


def coverage(conn: sqlite3.Connection) -> dict[str, int]:
    """Where the record stands, counts only: the before/after line."""
    def one(sql: str, *params: Any) -> int:
        return int(conn.execute(sql, params).fetchone()[0])

    like = f"{vcl.COMBO_PREFIX}%"
    return {
        "settled_combos": one(
            "SELECT COUNT(DISTINCT ticker) FROM venue_settlements WHERE ticker LIKE ?",
            like,
        ),
        "combos_with_venue_legs": one(
            "SELECT COUNT(DISTINCT combo_ticker) FROM venue_combo_legs"
        ),
        "combos_refused": one("SELECT COUNT(*) FROM venue_combo_leg_refusals"),
        "venue_legs": one("SELECT COUNT(*) FROM venue_combo_legs"),
        "venue_legs_with_ask": one(
            "SELECT COUNT(*) FROM venue_combo_legs WHERE ask_at_purchase_tenths IS NOT NULL"
        ),
        "venue_legs_result_unread": one(
            "SELECT COUNT(*) FROM venue_combo_legs l "
            "LEFT JOIN kalshi_markets m ON m.ticker = l.ticker "
            "WHERE l.venue_result IS NULL "
            "AND (m.result IS NULL OR LOWER(TRIM(m.result)) NOT IN ('yes', 'no'))"
        ),
    }


async def run_passes(
    conn: sqlite3.Connection,
    markets: Any,
    candles: Any,
    *,
    limit: int,
    commit: bool,
    now_ms: int,
) -> dict[str, Any]:
    before = coverage(conn)
    legs = await vcl.capture_legs(
        conn, markets, limit=limit, now_ms=now_ms, commit=commit
    )
    results = await vcl.capture_results(
        conn, markets, limit=limit, now_ms=now_ms, commit=commit
    )
    prices = await fill_prices(
        conn, candles, limit=limit, commit=commit, now_ms=now_ms
    )
    prices["bars_from_archive"] = int(getattr(candles, "archive_reads", 0))
    return {
        "mode": "commit" if commit else "dry-run",
        "before": before,
        "legs": legs,
        "results": results,
        "prices": prices,
        "after": coverage(conn),
    }


async def _run(args: argparse.Namespace) -> int:
    import httpx

    from backend.logging_setup import configure_logging

    configure_logging()
    conn = open_db(args.db, read_only=not args.commit)
    conn.row_factory = sqlite3.Row
    try:
        async with httpx.AsyncClient(timeout=PUBLIC_TIMEOUT_S) as client:
            report = await run_passes(
                conn, PublicMarkets(client), CandlesWithArchive(client),
                limit=args.limit, commit=args.commit,
                now_ms=int(time.time() * 1000),
            )
    finally:
        conn.close()
    print(json.dumps(report, indent=2))
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--db", required=True, help="path to cockpit.db (live: /data/cockpit.db)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="read the venue, write nothing")
    mode.add_argument("--commit", action="store_true", help="write the legs, results and prices")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                        help=f"rows each pass may consider (default {DEFAULT_LIMIT})")
    args = parser.parse_args(argv)
    if args.limit <= 0:
        parser.error("--limit must be positive")
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
