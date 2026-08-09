"""Does a candle's published `yes_ask` equal the ask this project derives?

`docs/adr/0016` §3.3 calls this "one free verification, before anything else",
and it gates Phase 0 of the backfill -- the free, perishable half that harvests
Kalshi bars before a single Odds API credit is spent.

The stake. Live, this project never reads a published ask. It derives one:

    yes_ask = 1000 - best_no_bid        (`store.db.derive_yes_ask`)
    no_ask  = 1000 - best_yes_bid       (`store.db.derive_no_ask`)

A candlestick bar instead *publishes* `yes_ask` directly. ADR 0016 marks input 5
(YES `ask_tenths`) as "⚠ different construction -- published ask vs
derived-from-bid". If the two disagree by even a tick, every backfilled entry
price is wrong in the direction that decides whether a 4c edge exists, because
the entry price **is** the derived ask (CLAUDE.md: bucket by the price you would
actually pay, never the mid -- the predecessor's +25.4 point "edge" that lost
$4.92 a market was bucketed on the mid).

How this differs from the ADR's design -- READ THIS BEFORE CITING THE RESULT
---------------------------------------------------------------------------
§3.3 specifies an **offline** reconciliation: "the live database already holds
`kalshi_quotes` with real bids at known instants. Pull the candle for the same
minute and compare." That is not runnable here. The local `data/demo.db` is
synthetic and its `kalshi_quotes` table has zero rows, and the live database
lives on a Fly volume this harness has no access to.

So this harness reconciles the same identity a different way: it captures a
**fresh quote and the candle covering that same moment in one pass**. It reads
each market's order book, waits for the bars spanning that read to complete,
re-reads the book, and compares.

The two are not the same evidence, and the difference bounds how far the result
generalises:

| | ADR §3.3 (offline) | This harness (same-pass) |
|---|---|---|
| Quotes | months of stored history | one instant, today |
| Regime | whatever the live poller happened to see | whatever is quoting right now |
| Instants per market | many | one |
| Establishes | agreement across the retention window | agreement at one instant, today |

A same-pass run cannot show that the identity held on 2026-06-01. It can show
whether the identity is **the same construction at all** -- which is the actual
question §3.3 asks, since a construction difference (a rounding convention, an
off-by-a-tick, a different source book) would be a property of the endpoint, not
of the day. A time-varying disagreement would escape this design; a structural
one cannot.

The bracketing protocol, and why a naive comparison would be meaningless
-----------------------------------------------------------------------
A candle is **OHLC over an interval**; a quote is an **instant**. Comparing a
bar's close against a book read at some other moment tests the market's
volatility, not the endpoint's construction. Observed while writing this: an
in-play MLB market's `yes_bid.close` moved 0.77 -> 0.61 -> 0.67 -> 0.73 over four
consecutive one-minute bars.

So a market only enters the comparison when the quote is shown to have been
**constant** across the bars being compared, by two independent sources:

1. The order book is read at `t0` and again at `t1`, and both best bids are
   unchanged. (Two reads cannot rule out a move-and-return, which is why source
   2 exists.)
2. Every bracketed bar has `open == high == low == close` on both `yes_bid` and
   `yes_ask`, and agrees with every other bracketed bar. Kalshi's own data
   asserting the level never moved inside the interval.

A bar is *bracketed* only if its whole interval `(end-60, end]` falls strictly
between the two book reads, so neither read can sit inside the interval it is
being compared against.

**On reading `high`/`low`/`open`.** ADR 0016 input 8 bans those fields --
correctly -- for *reconstructing a price*, because they look forward inside the
bar. This harness reads them for a different purpose: as a constancy test in a
live reconciliation, where there is no `T` and nothing is being reconstructed.
Only `close` is ever compared. The ban is not being weakened; a backfill must
still read `close` alone.

What is compared
----------------
Per comparable market, three claims -- but only the first is an independent test:

- **TEST** (ADR input 5): `bar.yes_ask.close == derive_yes_ask(book_no_bid)`
- **CONTROL**: `bar.yes_bid.close == book_yes_bid`. `yes_bid` is published on
  both sides, so this is the same quantity by two routes. If the control fails,
  the bracketing or the timing is broken and the TEST result means nothing --
  a failed TEST beside a passing CONTROL is the only reading that indicts the
  ask.
- **DERIVED NO ASK** (ADR input 6): `1000 - bar.yes_bid.close ==
  derive_no_ask(book_yes_bid)`. Algebraically implied by the control, not
  independent of it, and reported only so the ADR's input 6 row has a number.

Two strata, reported separately and never pooled
------------------------------------------------
- **game** -- `KXMLBGAME` / `KXNFLGAME` / `KXWNBAGAME` moneylines, the backfill's
  actual population. Every one observed ticks `linear_cent`.
- **deci** -- markets whose `price_level_structure` is `deci_cent` or
  `tapered_deci_cent`, drawn from the general universe because no game series
  carries one. §3.3 names a deci-cent rounding convention as a specific hazard,
  and it cannot be tested inside the backfill's own population.

Run:

    .venv\\Scripts\\python.exe scripts\\reconcile_candle_ask.py
    .venv\\Scripts\\python.exe scripts\\reconcile_candle_ask.py --max-game 200

    # deci-cent series tick so seldom that a 2-minute bracket sees ~1% of them
    .venv\\Scripts\\python.exe scripts\\reconcile_candle_ask.py \\
        --strata deci --max-deci 150 --max-pages 12 --bars 15

Takes ~4 minutes by default: most of it is waiting for two one-minute bars to
close. `--bars 15` makes it ~17.

Read-only. Places no orders. **Spends no Odds API credits and never calls The
Odds API.** Never paginates `/markets`. Never loads the private key -- every
endpoint used answers 200 unauthenticated (verified 2026-08-09).

What this harness does NOT establish
------------------------------------
- **Agreement at horizons it did not sample.** One instant, today. It says
  nothing about whether the identity held at any point inside the ~80-day
  retention window, which is what a backfill would actually read.
- **Agreement for markets outside the liquidity range it happened to hit.** The
  run prints the sampled `volume_fp` range; anything outside it is untested.
- **Agreement in a moving book.** The constancy filter admits only markets whose
  quote stood still. That is deliberate -- a moving book cannot separate a
  construction difference from a price change -- but it means the result covers
  quiet books, which is the pre-game regime the backfill targets and *not* the
  in-play regime.
- **That `depth_at_ask` is recoverable.** It is not, at any price. ADR 0016 §3.2
  settles that from the captured fixture and nothing here revisits it.
- **That the backfill's other 6 contaminated inputs are safe.** This verifies
  input 5 and touches input 6. Inputs 7, 8, 9, 10, 25, 27 and 28 are untouched.
- **That the identity will hold tomorrow.** Kalshi can change a construction
  without notice, exactly as it can change the retention window.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Both parsers are imported rather than reimplemented, on purpose. A local
# `1000 - no_bid` would test this script's arithmetic instead of the code the
# money path runs, and a local `close_dollars` read would repeat the bug
# `parse_candlestick`'s docstring records -- it read `close`, returned None for
# every candle ever fetched, and pinned the live CLV counter at zero.
from backend.analysis.clv import parse_candlestick  # noqa: E402
from backend.core.prices import dollars_to_tenths, parse_quantity  # noqa: E402
from backend.kalshi.rest import (  # noqa: E402
    ORDERBOOK_KEY,
    MalformedOrderbookResponse,
)
from backend.store.db import derive_no_ask, derive_yes_ask  # noqa: E402

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
HTTP_TIMEOUT_S = 60.0
PAGE_LIMIT = 200

# Kalshi's documented read limit is ~10/s; sit under it. Being throttled
# mid-pass would stagger the `t0` reads and widen the bracket, which is the one
# thing this protocol cannot tolerate.
CONCURRENCY = 6

# The backfill's population: game-level moneylines in leagues this project can
# devig against.
GAME_SERIES = ("KXMLBGAME", "KXNFLGAME", "KXWNBAGAME")
DECI_STRUCTURES = frozenset({"deci_cent", "tapered_deci_cent"})

BAR_SECONDS = 60
# Bars to bracket. More than one so constancy is asserted over a longer window;
# they are not independent observations and n counts markets, not bars.
#
# It also decides which markets can be measured at all, which is why it is a
# flag. **Kalshi does not emit a bar for every minute of every market**: over a
# 2-minute window, 101 of 166 sampled game markets and 80 of 80 deci-cent
# markets returned no bar despite quoting two-sided books. Deci-cent markets
# live in long-dated political and science series that can go many minutes
# between ticks, so a 2-minute bracket cannot see them at all. A longer window
# costs only wall-clock, and a quiet market is *more* likely to pass the
# constancy filter over it, not less.
DEFAULT_BARS = 2
# Slack after the last bar closes, before asking for it. A bar that has not been
# published yet returns as absent, which would read as "no data for this
# market" rather than "asked too early".
PUBLISH_BUFFER_S = 20


@dataclass
class Book:
    """Best bids on both sides at one instant. Asks are never read from here."""

    ticker: str
    observed_ms: int
    yes_bid_tenths: Optional[int]
    no_bid_tenths: Optional[int]
    yes_bid_qty: Optional[float]
    no_bid_qty: Optional[float]

    @property
    def two_sided(self) -> bool:
        return self.yes_bid_tenths is not None and self.no_bid_tenths is not None

    def same_quote_as(self, other: "Book") -> bool:
        return (
            self.yes_bid_tenths == other.yes_bid_tenths
            and self.no_bid_tenths == other.no_bid_tenths
        )


@dataclass
class Bar:
    """One candlestick. `close` is the only field a backfill may read."""

    end_period_ts: int
    yes_bid: dict[str, Optional[int]] = field(default_factory=dict)
    yes_ask: dict[str, Optional[int]] = field(default_factory=dict)

    def flat(self, group: str) -> bool:
        """Did this level never move inside the interval?

        `None` is not flat. A bar with no `yes_ask` sub-object is a bar that
        says nothing about the ask, and must not pass a constancy test by
        having four equal absences.
        """
        values = getattr(self, group)
        close = values.get("close")
        if close is None:
            return False
        return all(values.get(k) == close for k in ("open", "high", "low"))


def best_bid(levels: Any) -> tuple[Optional[int], Optional[float]]:
    """Highest bid on one side of `orderbook_fp`, as (tenths, quantity).

    Levels arrive ascending as `[[price_string, size_string], ...]`, so the best
    bid is the last -- but this takes the max rather than the last, because an
    ordering assumption that is usually true is how a wrong price gets read
    silently.

    An empty side returns `(None, None)`, never `(0, 0.0)`. No NO bid means
    nobody will sell you YES at any price; that is not a free fill, and
    CLAUDE.md's rule is that unreadable resolves to None so the caller refuses.
    """
    if not isinstance(levels, list) or not levels:
        return None, None
    best_tenths: Optional[int] = None
    best_qty: Optional[float] = None
    for level in levels:
        if not isinstance(level, (list, tuple)) or len(level) < 2:
            continue
        tenths = dollars_to_tenths(level[0])
        if tenths is None:
            continue
        if best_tenths is None or tenths > best_tenths:
            best_tenths = tenths
            best_qty = parse_quantity(level[1])
    return best_tenths, best_qty


def parse_bar(payload: dict) -> Bar:
    """One wire candle to a `Bar`, in tenths.

    **`close` comes from `analysis.clv.parse_candlestick`** -- the same function
    `scoring.fetch_closing_line` uses -- so the value compared here is the value
    a backfill would actually read. `open`/`high`/`low` have no production
    reader and are parsed locally for the constancy test only.

    `price` (last trade) is deliberately never read: ADR 0016 input 9 -- on a
    settled market it has already converged on the outcome.
    """
    bar = Bar(end_period_ts=int(payload.get("end_period_ts") or 0))
    bid_close, ask_close = parse_candlestick(payload)
    bar.yes_bid["close"] = bid_close
    bar.yes_ask["close"] = ask_close
    for group in ("yes_bid", "yes_ask"):
        sub = payload.get(group)
        target = getattr(bar, group)
        if not isinstance(sub, dict):
            continue
        for name in ("open", "high", "low"):
            target[name] = dollars_to_tenths(sub.get(f"{name}_dollars"))
    return bar


class Reader:
    """Unauthenticated Kalshi reads, rate limited, one shared client."""

    def __init__(self, client: httpx.AsyncClient):
        self._client = client
        self._sem = asyncio.Semaphore(CONCURRENCY)

    async def get(self, path: str, **params: Any) -> dict:
        async with self._sem:
            for attempt in range(5):
                response = await self._client.get(
                    f"{BASE_URL}{path}",
                    params={k: v for k, v in params.items() if v is not None},
                )
                if response.status_code != 429:
                    response.raise_for_status()
                    return response.json()
                await asyncio.sleep(0.5 * (2**attempt))
            response.raise_for_status()
            return {}

    async def orderbook(self, ticker: str) -> Book:
        """Best bids for one market.

        The envelope is `orderbook_fp` and the sides are `yes_dollars` /
        `no_dollars` -- **not** the socket's names. A missing envelope raises
        rather than returning an empty book, matching
        `KalshiRestClient.orderbook`: an empty book is a legitimate state on
        this venue and a renamed field is not, and the two must not share a
        return value.
        """
        payload = await self.get(f"/markets/{ticker}/orderbook", depth=10)
        observed_ms = int(time.time() * 1000)
        book = payload.get(ORDERBOOK_KEY)
        if book is None:
            raise MalformedOrderbookResponse(
                f"{ticker}: no {ORDERBOOK_KEY!r} key (got {sorted(payload)})"
            )
        yes_tenths, yes_qty = best_bid(book.get("yes_dollars"))
        no_tenths, no_qty = best_bid(book.get("no_dollars"))
        return Book(ticker, observed_ms, yes_tenths, no_tenths, yes_qty, no_qty)

    async def candles(
        self, series: str, ticker: str, start_ts: int, end_ts: int
    ) -> list[Bar]:
        """One-minute bars. Timestamps are epoch SECONDS on this endpoint."""
        payload = await self.get(
            f"/series/{series}/markets/{ticker}/candlesticks",
            start_ts=start_ts,
            end_ts=end_ts,
            period_interval=1,
        )
        return [parse_bar(c) for c in (payload.get("candlesticks") or [])]

    async def events(self, series: Optional[str], cursor: Optional[str]) -> dict:
        return await self.get(
            "/events",
            status="open",
            limit=PAGE_LIMIT,
            with_nested_markets="true",
            series_ticker=series,
            cursor=cursor,
        )


async def sample_game(reader: Reader, limit: int) -> list[dict]:
    """Game-series moneylines, spread across the liquidity range.

    Queried per series rather than by walking `/events` unfiltered: six unfiltered
    pages returned 8,250 markets and **zero** game markets, because sports sits
    deep in the cursor. `/markets` is never paginated (CLAUDE.md).
    """
    out: list[dict] = []
    for series in GAME_SERIES:
        payload = await reader.events(series, None)
        for event in payload.get("events") or []:
            for market in event.get("markets") or []:
                ticker = market.get("ticker") or ""
                if ticker.startswith("KXMVE"):
                    continue
                out.append({"ticker": ticker, "series": series, "market": market})
    return spread_by_volume(out, limit)


async def sample_deci(reader: Reader, limit: int, max_pages: int) -> list[dict]:
    """Deci-cent markets from the general universe.

    No game series carries one, so §3.3's rounding-convention hazard is
    untestable inside the backfill's own population and has to be borrowed from
    elsewhere on the exchange. Reported as its own stratum, never pooled.
    """
    out: list[dict] = []
    cursor: Optional[str] = None
    for _ in range(max_pages):
        payload = await reader.events(None, cursor)
        events = payload.get("events") or []
        if not events:
            break
        for event in events:
            series = event.get("series_ticker") or ""
            if series.startswith("KXMVE"):
                continue
            for market in event.get("markets") or []:
                ticker = market.get("ticker") or ""
                if ticker.startswith("KXMVE"):
                    continue
                if market.get("price_level_structure") not in DECI_STRUCTURES:
                    continue
                out.append({"ticker": ticker, "series": series, "market": market})
        cursor = payload.get("cursor") or None
        if not cursor:
            break
    return spread_by_volume(out, limit)


def spread_by_volume(rows: list[dict], limit: int) -> list[dict]:
    """Take `limit` rows spread evenly across the volume range, not the top.

    Sampling the fattest books would answer the question only where it is
    easiest, and the write-up has to be able to state the liquidity range the
    result covers.
    """
    if not rows or limit <= 0:
        return []
    rows = sorted(rows, key=lambda r: parse_quantity(r["market"].get("volume_fp")) or 0.0)
    if len(rows) <= limit:
        return rows
    step = len(rows) / limit
    return [rows[min(len(rows) - 1, int(i * step))] for i in range(limit)]


@dataclass
class Comparison:
    ticker: str
    stratum: str
    structure: str
    volume: float
    book_yes_bid: Optional[int]
    book_no_bid: Optional[int]
    derived_yes_ask: Optional[int]
    derived_no_ask: Optional[int]
    bar_yes_bid_close: Optional[int]
    bar_yes_ask_close: Optional[int]
    bars_used: int
    verdict: str
    ask_delta: Optional[int] = None
    bid_delta: Optional[int] = None


def compare(
    row: dict, t0: Book, t1: Book, bars: list[Bar]
) -> Comparison:
    """One market's verdict. `verdict` names why it was excluded, if it was."""
    market = row["market"]
    result = Comparison(
        ticker=row["ticker"],
        stratum=row["stratum"],
        structure=market.get("price_level_structure") or "",
        volume=parse_quantity(market.get("volume_fp")) or 0.0,
        book_yes_bid=t0.yes_bid_tenths,
        book_no_bid=t0.no_bid_tenths,
        derived_yes_ask=derive_yes_ask(t0.no_bid_tenths),
        derived_no_ask=derive_no_ask(t0.yes_bid_tenths),
        bar_yes_bid_close=None,
        bar_yes_ask_close=None,
        bars_used=len(bars),
        verdict="",
    )
    if not bars:
        result.verdict = "no_bars"
        return result

    closes_bid = {b.yes_bid.get("close") for b in bars}
    closes_ask = {b.yes_ask.get("close") for b in bars}
    result.bar_yes_bid_close = next(iter(closes_bid)) if len(closes_bid) == 1 else None
    result.bar_yes_ask_close = next(iter(closes_ask)) if len(closes_ask) == 1 else None

    if not t0.two_sided or not t1.two_sided:
        # Kept as its own state rather than folded into "moved": a one-sided
        # book is what the absence probe below is looking for.
        result.verdict = "one_sided_book"
        return result
    if not t0.same_quote_as(t1):
        result.verdict = "book_moved"
        return result
    if not all(b.flat("yes_bid") and b.flat("yes_ask") for b in bars):
        result.verdict = "bar_not_flat"
        return result
    if len(closes_bid) != 1 or len(closes_ask) != 1:
        result.verdict = "bars_disagree"
        return result
    if result.bar_yes_bid_close is None or result.bar_yes_ask_close is None:
        result.verdict = "bar_missing_level"
        return result

    result.bid_delta = result.bar_yes_bid_close - (t0.yes_bid_tenths or 0)
    assert result.derived_yes_ask is not None
    result.ask_delta = result.bar_yes_ask_close - result.derived_yes_ask
    result.verdict = "compared"
    return result


async def one_market(
    reader: Reader, row: dict, start_ts: int, end_ts: int
) -> Optional[Comparison]:
    """Fetch the bars for a market already read at `t0`/`t1` and compare."""
    try:
        bars = await reader.candles(row["series"], row["ticker"], start_ts, end_ts)
    except httpx.HTTPStatusError:
        bars = []
    bars = [b for b in bars if start_ts < b.end_period_ts <= end_ts]
    return compare(row, row["t0"], row["t1"], bars)


async def read_books(reader: Reader, rows: list[dict], key: str) -> None:
    """Read every book as near-simultaneously as the rate limit allows."""

    async def one(row: dict) -> None:
        try:
            row[key] = await reader.orderbook(row["ticker"])
        except (httpx.HTTPStatusError, MalformedOrderbookResponse) as exc:
            row[key] = None
            row.setdefault("errors", []).append(f"{key}: {exc}")

    await asyncio.gather(*(one(r) for r in rows))


def summarise(results: list[Comparison], stratum: str) -> dict:
    """One stratum's numbers. `n` first, effect size after."""
    rows = [r for r in results if r.stratum == stratum]
    compared = [r for r in rows if r.verdict == "compared"]
    verdicts: dict[str, int] = {}
    for row in rows:
        verdicts[row.verdict] = verdicts.get(row.verdict, 0) + 1
    volumes = sorted(r.volume for r in compared)
    ask_agree = sum(1 for r in compared if r.ask_delta == 0)
    bid_agree = sum(1 for r in compared if r.bid_delta == 0)
    ask_deltas: dict[str, int] = {}
    for row in compared:
        if row.ask_delta:
            key = str(row.ask_delta)
            ask_deltas[key] = ask_deltas.get(key, 0) + 1
    return {
        "stratum": stratum,
        "n_sampled": len(rows),
        "n_compared": len(compared),
        "verdicts": verdicts,
        "ask_agree": ask_agree,
        "bid_agree_control": bid_agree,
        "ask_delta_histogram_tenths": ask_deltas,
        "structures": sorted({r.structure for r in compared}),
        "volume_fp_range": (
            [volumes[0], statistics.median(volumes), volumes[-1]] if volumes else []
        ),
    }


def print_summary(summary: dict) -> None:
    print(f"\n  stratum: {summary['stratum']}")
    print(f"    n sampled                 {summary['n_sampled']}")
    print(f"    n compared (the real n)   {summary['n_compared']}")
    print(f"    excluded by              {summary['verdicts']}")
    if not summary["n_compared"]:
        print("    nothing comparable — no claim available for this stratum.")
        return
    n = summary["n_compared"]
    print(
        f"    CONTROL bar.yes_bid.close == book yes_bid   "
        f"{summary['bid_agree_control']}/{n}"
    )
    print(
        f"    TEST    bar.yes_ask.close == 1000-no_bid    "
        f"{summary['ask_agree']}/{n}"
    )
    if summary["ask_delta_histogram_tenths"]:
        print(f"    ask mismatches (tenths)  {summary['ask_delta_histogram_tenths']}")
    print(f"    structures               {summary['structures']}")
    if summary["volume_fp_range"]:
        low, mid, high = summary["volume_fp_range"]
        print(f"    volume_fp min/med/max    {low:.0f} / {mid:.0f} / {high:.0f}")


async def run(args: argparse.Namespace) -> int:
    limits = httpx.Limits(max_connections=CONCURRENCY * 2)
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_S, limits=limits) as client:
        reader = Reader(client)

        print("discovering...")
        game: list[dict] = []
        deci: list[dict] = []
        if "game" in args.strata:
            game = await sample_game(reader, args.max_game)
            for row in game:
                row["stratum"] = "game"
        if "deci" in args.strata:
            deci = await sample_deci(reader, args.max_deci, args.max_pages)
            for row in deci:
                row["stratum"] = "deci"
        rows = game + deci
        print(f"  sampled {len(game)} game + {len(deci)} deci-cent markets")
        if not rows:
            print("  nothing to sample.")
            return 1

        print("t0: reading order books...")
        await read_books(reader, rows, "t0")
        t0_done = time.time()

        # The bracket. Bars covering `(bar_start, bar_end]` must begin strictly
        # after the last `t0` read and end strictly before the first `t1` read,
        # so no book read sits inside an interval it is compared against. The
        # first boundary after `t0_done` may already be mid-bar, so skip it.
        bar_start = (int(t0_done) // BAR_SECONDS + 1) * BAR_SECONDS
        bar_end = bar_start + args.bars * BAR_SECONDS
        wait = bar_end + PUBLISH_BUFFER_S - time.time()
        print(
            f"  bracketing bars ({bar_start}, {bar_end}] — "
            f"waiting {wait:.0f}s for them to close and publish"
        )
        if wait > 0:
            await asyncio.sleep(wait)

        print("t1: re-reading order books...")
        await read_books(reader, rows, "t1")

        print("fetching candles...")
        usable = [r for r in rows if r.get("t0") and r.get("t1")]
        results = await asyncio.gather(
            *(one_market(reader, r, bar_start, bar_end) for r in usable)
        )
        results = [r for r in results if r is not None]

    print(f"\n{'=' * 70}")
    print("CANDLE yes_ask vs DERIVED ask — same-pass reconciliation")
    print(f"{'=' * 70}")
    print(f"  book reads bracket bars ({bar_start}, {bar_end}], 1-minute interval")
    print(f"  markets read at t0 and t1: {len(usable)} of {len(rows)}")

    summaries = [summarise(results, s) for s in ("game", "deci")]
    for summary in summaries:
        print_summary(summary)

    compared = [r for r in results if r.verdict == "compared"]
    control_ok = all(r.bid_delta == 0 for r in compared)
    ask_ok = all(r.ask_delta == 0 for r in compared)

    any_bars = any(r.bars_used for r in results)

    print(f"\n{'-' * 70}")
    # The control that measure_candlestick_retention.py learned the hard way.
    # `rest.candlesticks` reads `payload.get("candlesticks") or []`, so a
    # renamed envelope key returns an empty list that is indistinguishable from
    # "this market has no history" -- and every market sampled here is open and
    # currently quoting, so it MUST have bars. Zero everywhere is a fault in
    # this script or in the endpoint, never a finding.
    if not any_bars:
        print("  BROKEN PROBE: not one sampled market returned a bar, and every")
        print("  one of them is open and quoting right now. That is a wrong wire")
        print("  key, a wrong `period_interval` (it is MINUTES), or a wrong")
        print("  window — not a reconciliation result. Conclude nothing.")
        verdict = "broken_probe"
    elif not compared:
        print("  NO COMPARABLE MARKETS. This establishes nothing either way.")
        print("  Bars were returned, so the endpoint is answering; no book stood")
        print("  still long enough to compare. Re-run when books are quieter.")
        verdict = "inconclusive"
    elif not control_ok:
        print("  BROKEN PROBE: the CONTROL failed — `bar.yes_bid.close` does not")
        print("  match the book's own published yes_bid on a quote both sources")
        print("  agree never moved. That is a fault in the bracketing or in this")
        print("  script, not a finding about the ask. Ignore the TEST row.")
        verdict = "broken_probe"
    elif ask_ok:
        print("  AGREE. On every comparable market, the candle's published")
        print("  `yes_ask.close` equals `1000 - best_no_bid` — the same ask the")
        print("  live path derives. ADR 0016 input 5 behaves as input 6 does.")
        print("  Scope: one instant, quiet books, today. See the docstring.")
        verdict = "agree"
    else:
        bad = [r for r in compared if r.ask_delta != 0]
        print(f"  DISAGREE on {len(bad)} of {len(compared)} comparable markets,")
        print("  with the CONTROL passing — so this is the ask construction, not")
        print("  timing. ADR 0016's backfill price axis is wrong as designed.")
        print("  Do not soften this. Phase 0 does not proceed on it.")
        for row in bad[:10]:
            print(
                f"    {row.ticker:<42} bar_ask={row.bar_yes_ask_close} "
                f"derived={row.derived_yes_ask} delta={row.ask_delta}"
            )
        verdict = "disagree"

    # The one-sided census: what does a bar publish for `yes_ask` when there is
    # no NO bid at all? Live, `derive_yes_ask` returns None and the caller
    # refuses. A bar that names a number there would silently invent an entry
    # price for every unquoted market in the backfill.
    one_sided = [r for r in results if r.verdict == "one_sided_book"]
    with_ask = [r for r in one_sided if r.bar_yes_ask_close is not None]
    print(f"\n  one-sided books seen: {len(one_sided)}")
    if one_sided:
        print(
            f"    of which the bar still published a yes_ask: {len(with_ask)}"
            f"  {sorted({r.bar_yes_ask_close for r in with_ask})}"
        )
        print(
            "    (live, `derive_yes_ask` returns None here and the caller "
            "refuses; a backfill reading the bar would not)"
        )

    payload = {
        "captured_ms": int(time.time() * 1000),
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "bracket": {
            "bar_start_ts": bar_start,
            "bar_end_ts": bar_end,
            "bars": args.bars,
        },
        "verdict": verdict,
        "control_passed": control_ok,
        "n_comparisons_made": len(compared) * 2,
        "summaries": summaries,
        "one_sided_books": len(one_sided),
        "one_sided_with_published_ask": len(with_ask),
        "rows": [vars(r) for r in results],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"\n  wrote {out}")

    return 0 if verdict in ("agree", "disagree") else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="ADR 0016 §3.3, re-scoped.")
    parser.add_argument("--max-game", type=int, default=60)
    parser.add_argument("--max-deci", type=int, default=30)
    parser.add_argument(
        "--bars",
        type=int,
        default=DEFAULT_BARS,
        help="one-minute bars to bracket. Raise it for illiquid strata that go "
        "minutes between bars; the run waits this many minutes.",
    )
    parser.add_argument(
        "--strata",
        nargs="+",
        default=["game", "deci"],
        choices=["game", "deci"],
    )
    parser.add_argument(
        "--max-pages", type=int, default=6, help="pages walked to find deci-cent markets"
    )
    parser.add_argument(
        "--out",
        default="docs/measurements/2026-08-09-candle-ask-reconciliation.json",
    )
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
