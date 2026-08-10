"""Watch the live board for a market that makes round-two's fills possible.

Round two (`docs/measurements/2026-08-10-preregistration-fee-rate-attribution-round-two.md`)
is registered, funded and **unrun**: on 2026-08-10 the cheapest `KXMLBGAME`
game-winner ask on the board was 28c against a required 6c-14c band. The stored
record says the band DOES occur -- 8.0c, 12.0c and 13.0c were all observed -- so
the blocker is timing, not availability.

This polls Kalshi's **free, unauthenticated** market-data endpoints and reports
when a cell's band is actually fillable. No credentials, no Odds API credits, no
orders, no money. It is a notifier, not a trader.

WHAT THIS DOES NOT DO
  - It does not place, prepare, or stage an order. `ORDERS_ARE_DRY_RUNS` is
    True and ADR 0018 makes arming a code change; a watcher that could trade
    would route around that.
  - It does not choose the market. The registration's rule is "scan in default
    order, take the FIRST qualifying market, no re-scanning, no waiting for a
    better price." This prints candidates in the API's own event order so a
    human applies that rule; it deliberately does NOT sort by attractiveness.
  - It does not decide whether the band is *ever* reachable. That is the census
    already at the top of `tasks/NEXT.md`.
  - It reads `yes_ask_dollars` / `yes_ask_size_fp` off `/markets`, which is
    top-of-book only. Depth beyond the best level is not consulted.

WHY THE SKIPPED PRICES
  10c and 30c are excluded by the registration, not by taste: at those prices a
  cell lands exactly on the $0.0001 fee grid under both candidate rates, so the
  fill discriminates no rounding rule -- the flaw that made round one's ATP cell
  unable to test anything.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from typing import Optional

import httpx

BASE = "https://api.elections.kalshi.com/trade-api/v2"

# Kalshi renamed its price fields to `_dollars` / `_fp`; the integer-cent names
# still exist on the payload and are now always None. Reading the old ones
# would look like "no market has a price" forever.
ASK_FIELD = "yes_ask_dollars"
SIZE_FIELD = "yes_ask_size_fp"


@dataclass(frozen=True)
class Cell:
    """One registered cell: which series, what ask band, how much size."""

    name: str
    series: tuple[str, ...]
    lo_c: float
    hi_c: float
    skip_c: tuple[float, ...]
    min_size: int
    note: str

    def matches(self, ask_c: Optional[float], size: Optional[float]) -> bool:
        if ask_c is None or size is None:
            return False
        if any(abs(ask_c - s) < 1e-9 for s in self.skip_c):
            return False
        return self.lo_c <= ask_c <= self.hi_c and size >= self.min_size


# D1 and D2 share a market: D1 buys 1, D2 buys 20 in the SAME market 60s later,
# so the min size is D2's requirement plus D1's contract.
CELLS = (
    Cell(
        "D1+D2",
        ("KXMLBGAME",),
        6.0,
        14.0,
        (10.0,),
        21,
        "buy 1, then 20 in the SAME market 60s later",
    ),
    Cell(
        "D3",
        ("KXMLBTOTAL", "KXMLBSPREAD"),
        27.0,
        39.0,
        (30.0,),
        1,
        "buy 1 -- a baseball series that is NOT the game winner",
    ),
    Cell(
        "D4",
        ("KXATPDOUBLES",),
        27.0,
        39.0,
        (30.0,),
        1,
        "buy 1 -- tennis doubles",
    ),
)


async def open_events(client: httpx.AsyncClient, series: str) -> list[str]:
    """Open event tickers for one series, in the API's own order.

    `/events` rather than `/markets`: `tasks/lessons.md` records that
    paginating `/markets` returns ~99.8% `KXMVE` with no volume.
    """
    out: list[str] = []
    cursor: Optional[str] = None
    while True:
        params: dict[str, object] = {
            "series_ticker": series,
            "status": "open",
            "limit": 200,
        }
        if cursor:
            params["cursor"] = cursor
        body = await _get(client, "/events", params)
        if "events" not in body:
            raise RuntimeError(f"/events lost its `events` key for {series}")
        out.extend(e["event_ticker"] for e in body["events"])
        cursor = body.get("cursor") or None
        if not cursor:
            return out


# Unauthenticated market data is free but rate limited: an untuned sweep over
# ~40 events 429s partway through. A watcher that dies mid-board reports "no
# qualifying market" while never having looked at the rest of it -- an absence
# that is really a truncation, which is this repo's most-repeated defect shape.
REQUEST_GAP_S = 0.25
MAX_RETRIES = 4


async def _get(client: httpx.AsyncClient, path: str, params: dict) -> dict:
    """GET with backoff. Raises after MAX_RETRIES rather than returning empty."""
    delay = 1.0
    for attempt in range(MAX_RETRIES):
        await asyncio.sleep(REQUEST_GAP_S)
        r = await client.get(f"{BASE}{path}", params=params)
        if r.status_code == 429:
            if attempt == MAX_RETRIES - 1:
                r.raise_for_status()
            await asyncio.sleep(delay)
            delay *= 2
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError("unreachable")


async def markets(client: httpx.AsyncClient, event_ticker: str) -> list[dict]:
    """Every market for one event. `?event_ticker=` ignores `limit` and returns all."""
    body = await _get(client, "/markets", {"event_ticker": event_ticker})
    if "markets" not in body:
        raise RuntimeError(f"/markets lost its `markets` key for {event_ticker}")
    return body["markets"]


def as_cents(v: object) -> Optional[float]:
    try:
        return round(float(str(v)) * 100.0, 4)
    except (TypeError, ValueError):
        return None


async def sweep(client: httpx.AsyncClient) -> list[str]:
    """One pass over every cell. Returns human-readable hits, in board order."""
    hits: list[str] = []
    seen_series: dict[str, list[str]] = {}
    for cell in CELLS:
        for series in cell.series:
            if series not in seen_series:
                try:
                    seen_series[series] = await open_events(client, series)
                except httpx.HTTPStatusError as exc:
                    print(f"  ! {series}: HTTP {exc.response.status_code}")
                    seen_series[series] = []
            for event in seen_series[series]:
                for m in await markets(client, event):
                    if m.get("status") != "active":
                        continue
                    ask = as_cents(m.get(ASK_FIELD))
                    try:
                        size = float(str(m.get(SIZE_FIELD)))
                    except (TypeError, ValueError):
                        size = None
                    if cell.matches(ask, size):
                        hits.append(
                            f"{cell.name:6} {m['ticker']:44} ask {ask:>6.1f}c  "
                            f"size {size:>10,.0f}   [{cell.note}]"
                        )
    return hits


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--interval", type=int, default=300, help="seconds between sweeps")
    ap.add_argument("--once", action="store_true", help="one sweep, then exit")
    args = ap.parse_args()

    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            try:
                hits = await sweep(client)
            except Exception as exc:
                # A truncated sweep must NOT print "no qualifying market" --
                # that is an absence caused by our own failure, and it reads
                # identically to a real one.
                print(f"SWEEP INCOMPLETE -- {type(exc).__name__}: {exc}")
                print("  the board was NOT fully checked; this is not a 'no'.")
                if args.once:
                    raise SystemExit(2)
                await asyncio.sleep(args.interval)
                continue

            if hits:
                print("\n*** ROUND-TWO BAND IS FILLABLE RIGHT NOW ***")
                for h in hits:
                    print("  " + h)
                print(
                    "\nRule: take the FIRST qualifying market in board order. "
                    "Limit order, check the shares field, no re-scanning.\n"
                )
            else:
                print("no qualifying market on the board")

            if args.once:
                return
            await asyncio.sleep(args.interval)


if __name__ == "__main__":
    asyncio.run(main())
