"""Fill each held leg's OWN Kalshi price at purchase and its close, from candlesticks.

    python /app/scripts/backfill_leg_prices.py --db /data/cockpit.db --dry-run --limit 400
    python /app/scripts/backfill_leg_prices.py --db /data/cockpit.db --commit  --limit 400

Why this exists (ADR 0194, schema v65, #322)
--------------------------------------------
Until v65 the record kept the price of the whole combination and nothing about
any leg inside it, so it could never say which KIND of leg loses more often
than its price says -- the question Joe asked on 2026-10-02 ("track them and
learn from them"). The forward path writes each leg's ask at the moment the
desk prices or checks a card (`ask_source = 'lookup'`). This script fills the
history the forward path never saw, from the one place a past Kalshi quote can
still be read: candlesticks, which the venue keeps for about 80 days (ADR
0016:318). The oldest held legs are from 2026-08-18, so the window closes
around 2026-11-06; after that the NULLs are permanent and honest.

What it writes, and only that
-----------------------------
- `ask_at_purchase_tenths` + `ask_source = 'candle'`: the close of the last
  one-minute bar ending at or before `parlay_positions.placed_ms`, for the
  side held -- the YES ask for a YES leg, `1000 - yes_bid` for a NO leg
  (`store.db.derive_no_ask`, the same reflection the desk pays). A bar is a
  minute, so this is the price to within the minute, not the tick the fill
  crossed; `ask_source` says so, and the forward path's `lookup` value is the
  finer one.
- `close_yes_bid_tenths`, `close_yes_ask_tenths`, `close_observed_ms`: the
  last bar before the leg's TRUE start minus `DEFAULT_HORIZON_HOURS`, where
  the true start is the odds fixture's commence reached through
  `event_links` -> `odds_fixtures` (never `kalshi_events`, whose clock runs
  three hours late; `backend/scoring.py`). A leg with no link keeps NULL and
  is counted, never guessed from the leg's own `commence_ms`.
- Every UPDATE carries `... IS NULL` in its WHERE clause. A value the forward
  path wrote is never overwritten; re-running is a no-op on filled rows.
- Nothing is written to `closing_lines`. `score_recommendations` scores every
  ticker with a line there, and a held leg's row would enter the gate's CLV
  population (ADR 0063 keeps the gate blind to what Joe holds).

`--dry-run` reads the venue and prints the counts it WOULD write; `--commit`
writes. Both print counts only -- no ticker, no price, no row -- because the
box's stdout lands in transcripts and operator data never enters the repo.

What this does not establish
----------------------------
- Nothing about any leg whose bars the venue no longer keeps (`no_bars_*`).
- Nothing about a leg with no `placed_ms` (a hand-typed slip) or no link.
- Nothing about a market whose series ticker had to be read off the ticker's
  prefix (`series_from_ticker`): the venue's series for it was never captured.
- That a bar's close equals the ask the fill crossed. It is the minute's
  close; `scripts/reconcile_candle_ask.py` is the harness for that identity.
- Nothing that needs a credential. The venue is read unauthenticated
  (`PublicCandles`), so the script runs from an `ssh console` shell that
  holds no key, and from `.github/workflows/instrument.yml`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.analysis.clv import DEFAULT_HORIZON_HOURS, parse_candlestick  # noqa: E402
from backend.store.db import derive_no_ask, open_db  # noqa: E402

# The same window the scorer asks for: one-minute bars, looking back a
# quarter of an hour, so a market with no print on the target minute still
# yields the most recent quote before it (`backend/scoring.py`).
WINDOW_MINUTES = 15
CANDLE_INTERVAL_MINUTES = 1
DEFAULT_LIMIT = 400


@dataclass
class Counts:
    mode: str = "dry-run"
    legs_considered: int = 0
    asks_written: int = 0
    closes_written: int = 0
    no_placed_ms: int = 0
    series_from_ticker: int = 0
    no_link: int = 0
    not_started: int = 0
    no_bars_ask: int = 0
    no_bars_close: int = 0
    unreadable_ask: int = 0
    unreadable_close: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def legs_needing_prices(conn: sqlite3.Connection, *, limit: int) -> list[sqlite3.Row]:
    """Held legs with a ticker and at least one of the v65 columns still NULL.

    Newest first, bounded: the venue's retention runs out oldest-first, so a
    bounded run that starts at the newest end leaves the perishable rows for
    last -- which is backwards for a one-off. Callers that want the oldest
    first pass `--oldest-first`; the default matches how every other bounded
    instrument in `scripts/` orders, so a partial run reads the same way.
    """
    return conn.execute(
        """
        SELECT l.id, l.ticker, l.side, p.placed_ms,
               l.ask_at_purchase_tenths, l.close_yes_bid_tenths, l.close_yes_ask_tenths,
               m.series_ticker, COALESCE(m.event_ticker, l.event_ticker) AS event_ticker
        FROM parlay_position_legs l
        JOIN parlay_positions p ON p.id = l.position_id
        LEFT JOIN kalshi_markets m ON m.ticker = l.ticker
        WHERE l.ticker IS NOT NULL
          AND (l.ask_at_purchase_tenths IS NULL
               OR (l.close_yes_bid_tenths IS NULL AND l.close_yes_ask_tenths IS NULL))
        ORDER BY l.id DESC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()


def true_commence_ms(conn: sqlite3.Connection, event_ticker: Optional[str]) -> Optional[int]:
    """The odds fixture's commence for a Kalshi event, through `event_links`.

    `odds_fixtures` is the trigger-maintained one-row-per-game schedule, so
    this is one indexed read, not a walk of `odds_snapshots`. `None` when the
    event was never linked -- the caller counts it; it never falls back to
    `kalshi_events`' clock, which is three hours late.
    """
    if not event_ticker:
        return None
    row = conn.execute(
        """
        SELECT MIN(f.commence_ms)
        FROM event_links e
        JOIN odds_fixtures f ON f.odds_event_id = e.odds_event_id
        WHERE e.kalshi_event_ticker = ?
        """,
        (event_ticker,),
    ).fetchone()
    value = row[0] if row else None
    return int(value) if value is not None else None


def series_for(row: sqlite3.Row, counts: Counts) -> str:
    """The series ticker the candlestick endpoint needs.

    `kalshi_markets.series_ticker` when discovery captured the market; else the
    prefix before the ticker's first hyphen, which is Kalshi's convention for
    the `KX...` series this desk trades, counted so the report says how many
    rows rested on the convention rather than the capture.
    """
    series = row["series_ticker"]
    if series:
        return str(series)
    counts.series_from_ticker += 1
    return str(row["ticker"]).split("-", 1)[0]


def ask_for_side(bar: dict, side: str) -> Optional[int]:
    """The price a buyer of `side` would have paid at that bar's close."""
    yes_bid, yes_ask = parse_candlestick(bar)
    if side == "yes":
        return yes_ask
    if side == "no":
        return derive_no_ask(yes_bid)
    raise ValueError(f"side must be 'yes' or 'no', got {side!r}")


async def last_bar(api: Any, series: str, ticker: str, *, end_ms: int) -> Optional[dict]:
    """The most recent one-minute bar ending at or before `end_ms`."""
    end_ts = int(end_ms) // 1000
    start_ts = end_ts - WINDOW_MINUTES * 60
    candles = await api.candlesticks(
        series,
        ticker,
        start_ts=start_ts,
        end_ts=end_ts,
        period_interval=CANDLE_INTERVAL_MINUTES,
    )
    return candles[-1] if candles else None


def observed_ms_of(bar: dict, fallback_ms: int) -> int:
    observed = bar.get("end_period_ts")
    if isinstance(observed, (int, float)):
        return int(observed) * 1000
    return int(fallback_ms)


async def fill(
    conn: sqlite3.Connection,
    api: Any,
    *,
    limit: int = DEFAULT_LIMIT,
    commit: bool = False,
    now_ms: Optional[int] = None,
) -> Counts:
    """Read bars for every leg that needs one; write only with `commit`."""
    counts = Counts(mode="commit" if commit else "dry-run")
    now = int(now_ms if now_ms is not None else time.time() * 1000)
    for row in legs_needing_prices(conn, limit=limit):
        counts.legs_considered += 1
        leg_id = int(row["id"])
        ticker = str(row["ticker"])
        side = str(row["side"])
        try:
            series = series_for(row, counts)

            if row["ask_at_purchase_tenths"] is None:
                placed_ms = row["placed_ms"]
                if placed_ms is None:
                    counts.no_placed_ms += 1
                else:
                    bar = await last_bar(api, series, ticker, end_ms=int(placed_ms))
                    if bar is None:
                        counts.no_bars_ask += 1
                    else:
                        ask = ask_for_side(bar, side)
                        if ask is None:
                            counts.unreadable_ask += 1
                        else:
                            counts.asks_written += 1
                            if commit:
                                conn.execute(
                                    "UPDATE parlay_position_legs "
                                    "SET ask_at_purchase_tenths = ?, ask_source = 'candle' "
                                    "WHERE id = ? AND ask_at_purchase_tenths IS NULL",
                                    (int(ask), leg_id),
                                )

            if row["close_yes_bid_tenths"] is None and row["close_yes_ask_tenths"] is None:
                commence = true_commence_ms(conn, row["event_ticker"])
                if commence is None:
                    counts.no_link += 1
                else:
                    target = commence - int(DEFAULT_HORIZON_HOURS * 3_600_000)
                    if target > now:
                        counts.not_started += 1
                    else:
                        bar = await last_bar(api, series, ticker, end_ms=target)
                        if bar is None:
                            counts.no_bars_close += 1
                        else:
                            yes_bid, yes_ask = parse_candlestick(bar)
                            if yes_bid is None and yes_ask is None:
                                counts.unreadable_close += 1
                            else:
                                counts.closes_written += 1
                                if commit:
                                    conn.execute(
                                        "UPDATE parlay_position_legs "
                                        "SET close_yes_bid_tenths = ?, close_yes_ask_tenths = ?, "
                                        "    close_observed_ms = ? "
                                        "WHERE id = ? AND close_yes_bid_tenths IS NULL "
                                        "  AND close_yes_ask_tenths IS NULL",
                                        (yes_bid, yes_ask, observed_ms_of(bar, target), leg_id),
                                    )
        except Exception as exc:  # noqa: BLE001 - one leg's failure must not end the run
            counts.errors.append(f"leg {leg_id}: {type(exc).__name__}")
    if commit:
        conn.commit()
    return counts


#: Kalshi's public REST base. Candlesticks answer 200 with no headers
#: (`scripts/measure_candlestick_retention.py`, verified 2026-08-09), so this
#: script never loads the private key: it reads nothing a credential guards,
#: and an `ssh console` shell on the box carries no key in its environment
#: (`docker/entrypoint.sh` materialises it for the app process only). The
#: same reader shape as `scripts/reconcile_candle_ask.py`'s.
PUBLIC_REST_URL = "https://api.elections.kalshi.com/trade-api/v2"
PUBLIC_TIMEOUT_S = 30.0


class PublicCandles:
    """Unauthenticated candlestick reads, one shared client, sequential."""

    def __init__(self, client: Any, *, base_url: str = PUBLIC_REST_URL) -> None:
        self._client = client
        self._base = base_url.rstrip("/")

    async def candlesticks(
        self, series_ticker: str, ticker: str, *, start_ts: int, end_ts: int,
        period_interval: int,
    ) -> list[dict]:
        path = f"/series/{series_ticker}/markets/{ticker}/candlesticks"
        params = {"start_ts": start_ts, "end_ts": end_ts, "period_interval": period_interval}
        for attempt in range(5):
            response = await self._client.get(f"{self._base}{path}", params=params)
            if response.status_code == 429:
                await asyncio.sleep(0.5 * (attempt + 1))
                continue
            if response.status_code == 404:
                return []  # history the venue no longer has: counted as no bar
            response.raise_for_status()
            return response.json().get("candlesticks") or []
        response.raise_for_status()
        return []


async def _run(args: argparse.Namespace) -> int:
    import httpx

    from backend.logging_setup import configure_logging

    configure_logging()
    conn = open_db(args.db, read_only=not args.commit)
    conn.row_factory = sqlite3.Row
    try:
        async with httpx.AsyncClient(timeout=PUBLIC_TIMEOUT_S) as client:
            api = PublicCandles(client)
            counts = await fill(conn, api, limit=args.limit, commit=args.commit)
    finally:
        conn.close()
    print(json.dumps(counts.as_dict(), indent=2))
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--db", required=True, help="path to cockpit.db (live: /data/cockpit.db)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="read bars, write nothing")
    mode.add_argument("--commit", action="store_true", help="write the NULL columns")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                        help=f"legs to consider, newest first (default {DEFAULT_LIMIT})")
    args = parser.parse_args(argv)
    if args.limit <= 0:
        parser.error("--limit must be positive")
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
