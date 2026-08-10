"""Watch the live board for the markets round THREE's five cells need.

Round three
(`docs/measurements/2026-08-10-preregistration-fee-rate-attribution-round-three.md`,
plus **Correction A**) is registered and funded -- Joe authorised **$5.00** on
2026-08-10, hard expiry **2026-08-31 (UTC)** -- and **unrun**. Five orders are
placed **by hand, on a phone**: the order path is disarmed and arming it is a
code change (ADR 0018), so nothing here touches it.

This polls Kalshi's **free, unauthenticated** market-data endpoints and reports
which cells are placeable right now. No credentials, no Odds API credits, no
orders, no money. It is a notifier, not a trader.

WHAT REPLACED WHAT, AND WHY
---------------------------
This file previously watched **round two**'s bands. Round two is **dead on
reachability**: `KXMLBGAME` printed 0 of 51,286 pre-game observations below 20c
against a required 6-14c band, cheapest 26.0c. A watcher pointed at a band the
record says cannot occur reports "no qualifying market" forever, and that
absence reads identically to a quiet board. The cells below are round three's.

WHAT THIS DOES NOT DO
  - It does not place, prepare, or stage an order.
  - It does not choose the market. The registration's rule (§3) is "scan in the
    app's default order, take the FIRST qualifying market, no re-scanning, no
    comparison between candidates, no waiting for a better price." This prints
    the **first** qualifying market per cell in the API's own event order, and
    deliberately does NOT sort by attractiveness or show rival candidates'
    prices -- displaying a menu would invite exactly the comparison §3 forbids.
  - It reads top-of-book only (`yes_ask_dollars` / `yes_ask_size_fp` off
    `/markets`). Depth behind the best level is not in the payload.
  - **It cannot tell you whether an order would FILL.** Every number it prints
    is a *displayed* ask at a *displayed* size, and §0.4e of the registration
    states that no quote record separates real resting size from a maker who
    pulls on any incoming order. That separation is the one thing the round
    exists to buy, and it costs an order.
  - It does not run Q-W (§1.3), the query that activates cell `W`. See below.

CELL `W` IS NOT WATCHED BY DEFAULT, AND THAT IS NOT A FAILED ACTIVATION
-----------------------------------------------------------------------
`W` is placed **only if** Q-W (§1.3) passes against the stored record. Q-W reads
`kalshi_quotes` over 2026-08-07..2026-08-10 and **the record lives on the live
volume** (`/data/cockpit.db`); the laptop's `kalshi.db` is empty. So this script
cannot decide `W`, and it must not pretend to.

`--wnba-series NAME` enables the `W` watch and is to be passed **only after an
agent session has run Q-W and reported which series it selected**. Absent that
flag the output says `W: UNRESOLVED (Q-W not run)` -- which is **not** the same
as §1.3's "no series passed, `W` IS NOT REGISTERED". Unreadable resolves to
`None`, never to a decision; §Power's four-cell enumeration governs only when
Q-W has actually been run and actually failed.

PRE-GAME IS ENFORCED HERE, NOT LEFT TO THE OPERATOR
---------------------------------------------------
P8 requires every fill to be pre-game, and the placement card's four-point
check ends "the game has not started". Kalshi markets stay `status: active`
in-play, so status alone cannot express this. True start is
`occurrence_datetime - 3h` -- Kalshi's `occurrence_datetime` runs exactly three
hours late, measured across MLB and tennis (`backend/match/linker.py:47`,
ADR 0006). A market whose `occurrence_datetime` is missing or unparseable is
**excluded and counted**, never assumed pre-game: a wrong start time silently
places an in-play order that voids its cell.

WHY THE SKIPPED PRICES
  The excluded ticks are excluded by the registration, not by taste: at those
  prices a cell lands exactly on the $0.0001 fee grid under both candidate
  rates, so the fill discriminates no rounding rule -- the flaw that made round
  one's ATP cell unable to test anything.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import httpx

BASE = "https://api.elections.kalshi.com/trade-api/v2"

# Kalshi renamed its price fields to `_dollars` / `_fp`; the integer-cent names
# still exist on the payload and are now always None. Reading the old ones
# would look like "no market has a price" forever.
ASK_FIELD = "yes_ask_dollars"
SIZE_FIELD = "yes_ask_size_fp"

# Kalshi's `occurrence_datetime` runs exactly 3 hours late. Measured across MLB
# and tennis; see `backend/match/linker.py:47` and ADR 0006.
OCCURRENCE_OFFSET_MS = 3 * 60 * 60 * 1000


@dataclass(frozen=True)
class Cell:
    """One registered cell: which series, what ask band, how much size.

    `lo_c`/`hi_c` are INCLUSIVE and are on the **displayed ask you cross**,
    never a mid (§1.1). `skip_c` are the registered exclusions.
    """

    name: str
    series: tuple[str, ...]
    lo_c: float
    hi_c: float
    skip_c: tuple[float, ...]
    min_size: int
    note: str

    def matches(self, ask_c: Optional[float], size: Optional[float]) -> bool:
        """Band, exclusions and displayed depth. Pre-game is checked separately.

        `None` for either input is a refusal, not a miss: an unreadable price
        must never be compared against a band.
        """
        if ask_c is None or size is None:
            return False
        if any(abs(ask_c - s) < 1e-9 for s in self.skip_c):
            return False
        return self.lo_c <= ask_c <= self.hi_c and size >= self.min_size


# The five registered cells (§1.1), plus the two mechanical refinements the
# registration fixes in advance: `R`'s two-pass scan (§3/§C5) and the
# `S1`+`S2` shared-market preference (§3 "Registered substitutions").
#
# Order matters and is the order Joe places them in (Appendix placement card).
CELLS: tuple[Cell, ...] = (
    Cell(
        "S1",
        ("KXMLBSPREAD",),
        6.0,
        15.0,
        (10.0,),
        1,
        "buy 1 -- MLB run line, low price",
    ),
    Cell(
        "S2",
        ("KXMLBSPREAD",),
        6.0,
        13.0,
        (10.0,),
        20,
        "buy 20, 60s after S1 -- record the balance before and after",
    ),
    Cell(
        "S1+S2",
        ("KXMLBSPREAD",),
        6.0,
        13.0,
        (10.0,),
        21,
        "PREFERRED: one market serves both -- buy 1, then 20 here 60s later",
    ),
    Cell(
        "S3",
        ("KXMLBSPREAD",),
        27.0,
        39.0,
        (30.0,),
        1,
        "buy 1 -- MLB run line, mid price (within-series control)",
    ),
    Cell(
        "R-pass1",
        ("KXMLBGAME",),
        47.0,
        52.0,
        (50.0,),
        1,
        "buy 1 -- PREFERRED R: at 47-52c the LOW prediction is exactly $0.0088",
    ),
    Cell(
        "R-pass2",
        ("KXMLBGAME",),
        27.0,
        52.0,
        (30.0, 40.0, 50.0),
        1,
        "buy 1 -- R fallback, only after a FULL pass-1 scan finds nothing",
    ),
)

# `W`'s band is fixed (§1.1) but its series is whatever Q-W selected, so the
# cell is built at runtime from `--wnba-series`.
W_BAND = (27.0, 39.0)
W_SKIP = (30.0,)


def wnba_cell(series: str) -> Cell:
    return Cell(
        "W",
        (series,),
        W_BAND[0],
        W_BAND[1],
        W_SKIP,
        1,
        f"buy 1 -- WNBA, ONLY because Q-W selected {series}",
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


def parse_iso_ms(v: object) -> Optional[int]:
    """Epoch ms from an ISO-8601 stamp, or `None`.

    `None` in, `None` out, and an unparseable stamp is also `None` -- never a
    substituted zero, which would render as 1970 and read as "long since
    started", i.e. it would silently exclude every market instead of the one it
    could not read.
    """
    if not isinstance(v, str) or not v:
        return None
    try:
        parsed = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def true_start_ms(market: dict) -> Optional[int]:
    """When the game actually starts, from this market's `occurrence_datetime`.

    Kalshi's stamp runs exactly 3 hours late, so the real first pitch is the
    stamp minus three hours. `None` when the stamp is absent or unparseable,
    and the caller must refuse rather than assume.
    """
    stamp = parse_iso_ms(market.get("occurrence_datetime"))
    if stamp is None:
        return None
    return stamp - OCCURRENCE_OFFSET_MS


def is_pregame(market: dict, now_ms: int) -> Optional[bool]:
    """`True` pre-game, `False` started, `None` when the start time is unreadable.

    Three-valued on purpose. Collapsing `None` into `False` would be safe here
    but would hide how often the payload omits the stamp; collapsing it into
    `True` would place an in-play order. The caller excludes `None` AND counts
    it, so a board that suddenly stops carrying the field is visible rather
    than silently empty.
    """
    start = true_start_ms(market)
    if start is None:
        return None
    return now_ms < start


def minutes_to_start(market: dict, now_ms: int) -> Optional[float]:
    start = true_start_ms(market)
    if start is None:
        return None
    return (start - now_ms) / 60000.0


# A market this close to first pitch is still pre-game and still qualifies --
# but the four-point check takes time, and a fill that lands after first pitch
# VOIDS its cell under P8. Observed live on 2026-08-10: the first qualifying
# `S1` market was 2 minutes from first pitch.
#
# This is a DISPLAY warning and nothing more. It must never filter: §3 says take
# the FIRST qualifying market in board order, and "qualifying" is band, depth
# and not-started. Dropping a qualifying market would silently redefine "first"
# and that is a change to the registration, which an operator aid may not make.
IMMINENT_START_MINUTES = 15.0


@dataclass(frozen=True)
class Hit:
    """The first qualifying market for one cell, plus how many others there were.

    `others` is a COUNT and never a list of prices. §3 forbids comparison
    between candidates; a count tells Joe the board is not one deep without
    offering him a menu to pick from.
    """

    cell: str
    ticker: str
    ask_c: float
    size: float
    mins_to_start: Optional[float]
    note: str
    others: int

    @property
    def is_imminent(self) -> bool:
        return (
            self.mins_to_start is not None
            and self.mins_to_start < IMMINENT_START_MINUTES
        )

    def render(self) -> str:
        mins = (
            f"{self.mins_to_start:>6.0f}m to start"
            if self.mins_to_start is not None
            else "  start unknown"
        )
        flag = "  <-- STARTS SOON" if self.is_imminent else ""
        extra = f"   (+{self.others} more qualified; take THIS one)" if self.others else ""
        return (
            f"{self.cell:8} {self.ticker:44} ask {self.ask_c:>6.1f}c  "
            f"size {self.size:>10,.0f}  {mins}{flag}\n"
            f"         {self.note}{extra}"
        )


@dataclass
class SweepResult:
    hits: list[Hit]
    no_start_time: int
    in_play_skipped: int
    events_scanned: int


async def sweep(
    client: httpx.AsyncClient,
    cells: tuple[Cell, ...],
    now_ms: int,
) -> SweepResult:
    """One full pass over every cell, in board order.

    Every cell is scanned even when an earlier one matched: they are different
    orders in the same session, not alternatives.
    """
    hits: list[Hit] = []
    no_start = 0
    in_play = 0
    seen_series: dict[str, list[str]] = {}
    market_cache: dict[str, list[dict]] = {}

    for cell in cells:
        first: Optional[Hit] = None
        others = 0
        for series in cell.series:
            if series not in seen_series:
                seen_series[series] = await open_events(client, series)
            for event in seen_series[series]:
                if event not in market_cache:
                    market_cache[event] = await markets(client, event)
                for m in market_cache[event]:
                    if m.get("status") != "active":
                        continue
                    pregame = is_pregame(m, now_ms)
                    if pregame is None:
                        no_start += 1
                        continue
                    if not pregame:
                        in_play += 1
                        continue
                    ask = as_cents(m.get(ASK_FIELD))
                    try:
                        size: Optional[float] = float(str(m.get(SIZE_FIELD)))
                    except (TypeError, ValueError):
                        size = None
                    if not cell.matches(ask, size):
                        continue
                    if first is None:
                        assert ask is not None and size is not None
                        first = Hit(
                            cell=cell.name,
                            ticker=m["ticker"],
                            ask_c=ask,
                            size=size,
                            mins_to_start=minutes_to_start(m, now_ms),
                            note=cell.note,
                            others=0,
                        )
                    else:
                        others += 1
        if first is not None:
            hits.append(
                Hit(
                    cell=first.cell,
                    ticker=first.ticker,
                    ask_c=first.ask_c,
                    size=first.size,
                    mins_to_start=first.mins_to_start,
                    note=first.note,
                    others=others,
                )
            )

    # `no_start` and `in_play` are summed across cells, so a market excluded
    # while scanning three `KXMLBSPREAD` cells counts three times. It is a
    # health signal about the payload, not a market count, and the label says so.
    return SweepResult(
        hits=hits,
        no_start_time=no_start,
        in_play_skipped=in_play,
        events_scanned=sum(len(v) for v in seen_series.values()),
    )


def report(result: SweepResult, wnba_series: Optional[str]) -> str:
    """Everything the operator needs, including what was NOT established."""
    lines: list[str] = []
    found = {h.cell for h in result.hits}

    if result.hits:
        lines.append("*** PLACEABLE RIGHT NOW ***")
        for h in result.hits:
            lines.append("  " + h.render())
    else:
        lines.append("no qualifying market on the board for any cell")

    # `R` is the cell gate G1 makes fatal, and the only one with no depth or
    # time-of-day citation behind it. Its absence is the round's likeliest
    # failure and must not be buried under four green lines.
    if "R-pass1" not in found and "R-pass2" not in found:
        lines.append("")
        lines.append("  !! R IS NOT PLACEABLE. R's absence is fatal to the round (gate G1).")
    elif "R-pass1" in found:
        lines.append("")
        lines.append("  R: pass 1 (47-52c) is available -- use it, not pass 2.")

    if "S1+S2" in found:
        lines.append("  S1+S2: one market serves both. Prefer it over separate S1 and S2.")

    imminent = [h.cell for h in result.hits if h.is_imminent]
    if imminent:
        lines.append("")
        lines.append(
            f"  ! STARTS SOON (<{IMMINENT_START_MINUTES:.0f}m): {', '.join(imminent)}.\n"
            "    Still pre-game and still the registered pick -- the scan rule takes the\n"
            "    FIRST qualifying market and this is it. But a fill landing after first\n"
            "    pitch VOIDS the cell (P8), and the four-point check takes time.\n"
            "    Either place it now, deliberately, or re-run later for a fresh board."
        )

    if wnba_series is None:
        lines.append("")
        lines.append(
            "  W: UNRESOLVED (Q-W not run). NOT the same as 'W is not registered' --\n"
            "     Q-W needs the live record, and no agent has reported a result."
        )

    lines.append("")
    lines.append(
        f"  scanned {result.events_scanned} open events; "
        f"skipped {result.in_play_skipped} in-play, "
        f"{result.no_start_time} with no readable start time (sums over cells)"
    )
    lines.append(
        "  Every figure above is a DISPLAYED ask at a DISPLAYED size. "
        "It is not evidence\n  that an order would fill -- that is what the round buys."
    )
    return "\n".join(lines)


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--interval", type=int, default=300, help="seconds between sweeps")
    ap.add_argument("--once", action="store_true", help="one sweep, then exit")
    ap.add_argument(
        "--wnba-series",
        default=None,
        help=(
            "Enable the cell-W watch in this series. Pass ONLY the series Q-W "
            "(§1.3) selected. Omit it and W reports UNRESOLVED."
        ),
    )
    args = ap.parse_args()

    cells = CELLS
    if args.wnba_series:
        cells = CELLS + (wnba_cell(args.wnba_series),)

    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            try:
                result = await sweep(client, cells, now_ms)
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

            stamp = datetime.fromtimestamp(now_ms / 1000, timezone.utc).isoformat()
            print(f"\n=== {stamp} ===")
            print(report(result, args.wnba_series))

            if args.once:
                return
            await asyncio.sleep(args.interval)


if __name__ == "__main__":
    asyncio.run(main())
