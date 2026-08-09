"""How much does the Kalshi half-spread *vary*? The number the CLV test needs.

Why this exists
---------------
`docs/measurements/2026-08-09-preregistration-clv-signal-test.md` §C2 identifies
a real algebraic confound in the CLV signal test:

    clv  = close_mid - ask  = (close_mid - entry_mid) - half_spread
    edge = fair - ask - fee = (fair - entry_mid)      - half_spread - fee

so `Cov(edge, clv)` carries `+Var(half_spread)`, and a strictly positive slope
arises from mechanics with zero predictive power. **The algebra is correct.** Its
*magnitude* was assumed, not measured: the document takes `sd(half_spread) = 4`
tenths against `sd(edge_tenths) = 10` tenths, obtains a spurious slope of ~0.16,
calls it "the largest finding in this document", and builds prerequisite P1 on
it -- a hard block on the primary analysis if half-spread coverage is under 90%.

`Var(half_spread)` is the whole term. If the half-spread is near-constant on the
population the test scores, the term is ~0 and P1 blocks for a confound that is
not there. This harness measures it.

ADR 0006 §4 already reported `spread mean/median/p90/p99/max = 1.00c` pre-game
on 20 games. That is 20 games on one night, at whole-cent reporting, pooled over
both leagues -- and it is a *mean*, which is not the missing quantity. What is
missing is dispersion, on the window the recorder actually operates in.

Two arms, because they answer different questions
-------------------------------------------------
**Arm B -- the panel, and the primary.** For settled games in in-scope leagues,
one-minute candlesticks over the final `--window-minutes` before the true start.
That is the window the recorder works in: `odds.timing.slots_for_sport` fires a
sweep at `anchor - max_odds_age_ms` and covers games out to `anchor + 3h`
(`COVERAGE_MS`), and `runner.record_recommendations` re-derives every row while
the 900s odds window is open. So rows are written about markets roughly 0-3
hours from their own kickoff, not about markets days out.

**Arm A -- the live cross-section, and the control.** Every in-scope market open
right now, stratified by time to kickoff. It exists to answer the question Arm B
cannot: is the near-kickoff tightness a property of the market, or of the
harness? A cross-section that is wide days out and tight near kickoff shows the
probe can see a wide spread when one exists. A probe that reports "tight"
everywhere is broken, and would kill a real confound on the strength of it.

Arm A is also where the derived-ask identity is *verified*, on live books that
publish both `no_bid_dollars` and `yes_ask_dollars`:

    half_spread_tenths = ((1000 - no_bid_tenths) - yes_bid_tenths) / 2

(`core.prices.complement`, `store.db.derive_yes_ask`). Arm B's candlesticks
publish `yes_ask` directly and cannot check it, so Arm A's violation count is
what licenses Arm B's column.

Resolution
----------
Every price on both arms arrives as a **4-decimal dollar string** and is parsed
by `core.prices.dollars_to_tenths` -- the same reader the recorder uses -- so
deci-cent ticks survive. A whole-cent measurement here would report exactly the
1.00c constant that is in question, which is the single most likely way to get a
wrong answer. The market's own `price_ranges` step is read alongside, because a
spread that never goes below one tick is censored, not constant.

Run
---
    .venv\\Scripts\\python.exe scripts\\measure_halfspread_dispersion.py
    .venv\\Scripts\\python.exe scripts\\measure_halfspread_dispersion.py \\
        --days 4 --window-minutes 180 --json out.json

Read-only, unauthenticated, no private key, no orders, no deploy. **Spends no
Odds API credits and never calls The Odds API.**

What this harness does NOT establish
------------------------------------
- **It does not measure the selected population.** The confound that matters is
  `Var(half_spread)` among the rows the CLV test scores. Isolating "markets
  where Kalshi disagrees with the sportsbook consensus" requires the consensus,
  which costs Odds API credits, which this harness is forbidden to spend. What
  it does instead is report the distribution within every free stratum -- league,
  price, time to kickoff, market type -- so a selected subset can only be wider
  than the unselected one if it concentrates inside a stratum that is itself
  wider. That is evidence about the ceiling, not a measurement of the cut.
- **`n` is three numbers and only the first is independent.** Games, markets,
  market-minutes. A game's two moneyline markets settle on one final score and
  180 minutes of one market is one market. All three are printed, and every
  distribution is repeated with one median per game so a single long-quoted
  market cannot carry a percentile.
- **A candlestick close is a minute-end snapshot, and unsized.** A one-minute bar
  hides everything that happened inside the minute, and a quote nobody could
  transact counts the same as one that could. `yes_ask.low - yes_bid.high` is
  reported beside the close for exactly this reason.
- **It is censored from below by the price grid.** On a `linear_cent` market the
  narrowest observable spread is one cent, so a half-spread of 5 tenths is a
  floor and not a statement about what makers would quote if they could quote
  finer. The floor fraction is printed for that reason.
- **It is a few days of one August slate**, in whatever leagues were open. Not a
  season, and not a claim about NBA, NHL, or the NFL regular season.
- **It says nothing in-play.** Pre-game only. ADR 0006 measured in-play and found
  the tail fattens once the game starts.
- **The true start is inferred, not published.** `occurrence_datetime` on a game
  market equals `expected_expiration_time` -- the expected *end* (ADR 0006 §1) --
  so the start is taken as three hours earlier, and only where those two fields
  are in fact equal. Games that run long or short shift the time strata by tens
  of minutes. The strata are directional, not precise.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.core.prices import dollars_to_tenths, parse_quantity  # noqa: E402
from backend.kalshi.discovery import classify_series, parse_ms  # noqa: E402

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
HTTP_TIMEOUT_S = 60.0
SLEEP_S = 0.35
MAX_RETRIES = 6
PAGE_LIMIT = 200

# Series probed, one request each. A full `/events?status=open` walk is 40+
# pages and ~8,000 events (measured 2026-08-09), far too expensive to repeat;
# asking per series is ~18 requests. This list is *candidates only* --
# `classify_series` decides what is in scope, so a league Kalshi renames drops
# out here rather than being silently miscounted. (It matters today: Kalshi
# spells NFL preseason `Pro Football Preseason`, which is not a key in
# `discovery.IN_SCOPE_LEAGUES`, so preseason is out of scope for the recorder.)
LEAGUE_PREFIXES = ("MLB", "NFL", "NCAAF", "NBA", "WNBA", "NHL")
SUFFIXES = ("GAME", "SPREAD", "TOTAL")

# `occurrence_datetime` on a `KX*GAME` market is the expected *end* of the game,
# not its start -- ADR 0006 §1 established this against the time encoded in the
# ticker, and `tasks/lessons.md` records it. Three hours is right for MLB and
# WNBA game markets by coincidence of game length and is wrong for period
# series, which is why the subtraction below is applied only where
# `occurrence_datetime == expected_expiration_time` actually holds.
GAME_LENGTH_MS = 3 * 60 * 60 * 1000

# Grid A from the pre-registration §4, in tenths, reused verbatim rather than
# re-derived: these are the fee-flat edges at one contract, and the point of
# fixing them in advance is that they cannot be re-chosen after the data is seen.
GRID_A = ((10, 200), (200, 800), (800, 990))

# Minutes-to-kickoff strata. 0-15 is singled out because ADR 0011 scores CLV
# against a candlestick within 15 minutes of kickoff, so that is the window the
# scored population is actually observed in.
TIME_BUCKETS = ((0, 15), (15, 60), (60, 180), (180, 720), (720, 2880), (2880, 10**9))

# `sd(edge_tenths)` values the spurious slope is reported against. 10 is the
# pre-registration's own central assumption; the others bracket it, because the
# slope is a ratio and a reader deserves to see how hard it leans on a
# denominator nobody has measured either.
SIGMA_EDGE_TENTHS = (5.0, 10.0, 15.0, 20.0)


def _get(client: httpx.Client, path: str, **params: Any) -> dict:
    """GET with backoff. Kalshi's documented read limit is ~10/s."""
    response = None
    for attempt in range(MAX_RETRIES):
        response = client.get(f"{BASE_URL}{path}", params=params)
        if response.status_code != 429:
            response.raise_for_status()
            return response.json()
        backoff = SLEEP_S * (2 ** (attempt + 1))
        print(f"    429; backing off {backoff:.1f}s", file=sys.stderr)
        time.sleep(backoff)
    if response is not None:
        response.raise_for_status()
    return {}


def series_events(client: httpx.Client, series: str, status: str) -> list[dict]:
    """Events for one series at one status, following the cursor.

    Returns `[]` on a 404, which is what an out-of-season series looks like. Any
    other HTTP error propagates: "the endpoint broke" and "this league is not
    playing" must not arrive as the same empty list.
    """
    out: list[dict] = []
    cursor: Optional[str] = None
    for _ in range(20):
        params: dict[str, Any] = {
            "status": status,
            "with_nested_markets": "true",
            "series_ticker": series,
            "limit": PAGE_LIMIT,
        }
        if cursor:
            params["cursor"] = cursor
        try:
            payload = _get(client, "/events", **params)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return []
            raise
        out.extend(payload.get("events") or [])
        cursor = payload.get("cursor") or None
        if not cursor:
            break
        time.sleep(SLEEP_S)
    return out


def tick_tenths(market: dict) -> Optional[int]:
    """The market's finest price step in tenths of a cent, or None.

    Read from `price_ranges` -- Kalshi's own words: *"this is the source of
    truth for valid prices"* -- never from the `price_level_structure` label,
    which the API documentation explicitly says not to branch on.

    This is the number that decides whether a constant 1.00c spread is a
    measurement or a floor. A step finer than a tenth returns None rather than
    rounding to zero: a grid this project cannot represent is one it must not
    silently claim to have measured.
    """
    steps: list[int] = []
    for band in market.get("price_ranges") or []:
        step = dollars_to_tenths(band.get("step"))
        if step is None or step <= 0:
            return None
        steps.append(step)
    return min(steps) if steps else None


def true_start_ms(market: dict) -> Optional[int]:
    """When the game actually starts, or None.

    ADR 0006's condition applied rather than assumed: subtract a game length
    only where `occurrence_datetime` demonstrably *is* the expected end. Where
    the two fields disagree, the field is taken at face value -- a series with a
    different convention must not quietly shift the time strata, and `KXMLBF5`
    is a series with a different convention.
    """
    occurrence = parse_ms(market.get("occurrence_datetime"))
    expiration = parse_ms(market.get("expected_expiration_time"))
    if occurrence is None:
        return None
    if expiration is not None and occurrence == expiration:
        return occurrence - GAME_LENGTH_MS
    return occurrence


# ---------------------------------------------------------------------------
# Arm A -- the live cross-section
# ---------------------------------------------------------------------------


def read_live_market(
    market: dict,
    *,
    event: dict,
    league: str,
    market_type: str,
    in_scope: bool,
    series: str,
    now_ms: int,
) -> Optional[dict]:
    """One live book's half-spread, or None if it cannot be read.

    Unreadable resolves to None and the caller counts it, never to a plausible
    zero. A market with a bid of exactly 0 on one side *is* readable and is kept
    -- 0 is a legal price -- but flagged `two_sided=False`, because a NO bid of
    $0.00 means nobody is offering YES at any price and the derived ask of $1.00
    is a fiction rather than a quote. Both populations are reported; the gap
    between them is itself a finding, since a fictional ask carries a fictional
    half-spread straight into the confound.
    """
    yes_bid = dollars_to_tenths(market.get("yes_bid_dollars"))
    no_bid = dollars_to_tenths(market.get("no_bid_dollars"))
    if yes_bid is None or no_bid is None:
        return None

    yes_ask = 1000 - no_bid
    no_ask = 1000 - yes_bid

    # The identity check, against data Kalshi publishes beside the bids. Cheap,
    # and it is what makes the half-spread column an observation rather than an
    # assumption. A field Kalshi did not send is "not checked", not a violation.
    quoted_yes_ask = dollars_to_tenths(market.get("yes_ask_dollars"))
    quoted_no_ask = dollars_to_tenths(market.get("no_ask_dollars"))
    identity_checked = quoted_yes_ask is not None and quoted_no_ask is not None
    identity_ok = identity_checked and (
        quoted_yes_ask == yes_ask and quoted_no_ask == no_ask
    )

    start = true_start_ms(market)
    return {
        "ticker": market.get("ticker") or "",
        "event_ticker": event.get("event_ticker") or "",
        "series": series,
        "league": league,
        "in_scope": in_scope,
        "market_type": market_type,
        "structure": market.get("price_level_structure"),
        "tick_tenths": tick_tenths(market),
        "yes_bid_tenths": yes_bid,
        "yes_ask_tenths": yes_ask,
        "spread_tenths": yes_ask - yes_bid,
        "half_spread_tenths": (yes_ask - yes_bid) / 2.0,
        "two_sided": yes_bid > 0 and no_bid > 0,
        "identity_checked": identity_checked,
        "identity_ok": identity_ok,
        "minutes_to_start": (
            (start - now_ms) / 60000.0 if start is not None else None
        ),
        "volume_24h": parse_quantity(market.get("volume_24h_fp")) or 0.0,
        "observed_ms": now_ms,
    }


def live_cross_section(client: httpx.Client) -> tuple[list[dict], dict]:
    """Every candidate series' open markets, read once."""
    rows: list[dict] = []
    counts: dict[str, int] = defaultdict(int)
    now_ms = int(time.time() * 1000)
    for prefix in LEAGUE_PREFIXES:
        for suffix in SUFFIXES:
            series = f"KX{prefix}{suffix}"
            events = series_events(client, series, "open")
            time.sleep(SLEEP_S)
            for event in events:
                info = classify_series(event)
                if not info.is_game_level or info.market_type is None:
                    counts["rejected_not_game_level"] += 1
                    continue
                in_scope = info.sport_key is not None
                counts["events_in_scope" if in_scope else "events_out_of_scope"] += 1
                for market in event.get("markets") or []:
                    counts["markets_seen"] += 1
                    row = read_live_market(
                        market,
                        event=event,
                        league=info.league or "",
                        market_type=info.market_type,
                        in_scope=in_scope,
                        series=series,
                        now_ms=now_ms,
                    )
                    if row is None:
                        counts["unreadable_quote"] += 1
                        continue
                    rows.append(row)
    return rows, dict(counts)


# ---------------------------------------------------------------------------
# Arm B -- the candlestick panel
# ---------------------------------------------------------------------------


def candlestick_rows(
    client: httpx.Client,
    *,
    series: str,
    market: dict,
    event_ticker: str,
    league: str,
    market_type: str,
    start_ms: int,
    window_minutes: int,
    drops: dict[str, int],
) -> tuple[list[dict], str]:
    """One market's final `window_minutes` before kickoff, one row per minute.

    Returns `(rows, outcome)` where `outcome` is one of `ok`, `http_error`,
    `no_bars`. Those are kept apart deliberately: a 404 is "we could not look"
    and an empty list is "Kalshi looked and has nothing", and collapsing them
    would report an outage as a market with no book -- the
    unreadable-must-never-resolve-to-zero rule applied to a measurement.

    **Every dropped bar is counted into `drops`, by reason.** If this function
    reports a constant spread, the first question is whether its own filter
    removed everything that was not constant, and an uncounted drop makes that
    question unanswerable.
    """
    end_ts = start_ms // 1000
    start_ts = end_ts - window_minutes * 60
    try:
        payload = _get(
            client,
            f"/series/{series}/markets/{market.get('ticker')}/candlesticks",
            start_ts=start_ts,
            end_ts=end_ts,
            period_interval=1,
        )
    except httpx.HTTPStatusError:
        return [], "http_error"

    bars = payload.get("candlesticks") or []
    if not bars:
        return [], "no_bars"

    tick = tick_tenths(market)
    rows: list[dict] = []
    for bar in bars:
        drops["bars_seen"] += 1
        ask = dollars_to_tenths((bar.get("yes_ask") or {}).get("close_dollars"))
        bid = dollars_to_tenths((bar.get("yes_bid") or {}).get("close_dollars"))
        if ask is None or bid is None:
            drops["dropped_missing_side"] += 1
            continue
        # A bar with no book on one side reports 0 or 1000, which is not a
        # quote. Refused rather than counted as a 100c spread -- ADR 0006's
        # `max 100.00c` figure is exactly this artefact, and it belongs in a
        # rejection count, not in a percentile. Each reason is counted
        # separately because they are different facts: an empty side is a
        # liquidity event, a crossed book is a wire-format problem, and pooling
        # them would hide the second behind the first.
        if bid <= 0:
            drops["dropped_no_yes_bid"] += 1
            continue
        if ask >= 1000:
            drops["dropped_no_no_bid"] += 1
            continue
        if ask <= bid:
            drops["dropped_crossed_or_locked"] += 1
            continue
        if ask - bid > (tick or 10):
            drops["kept_wider_than_one_tick"] += 1
        ask_low = dollars_to_tenths((bar.get("yes_ask") or {}).get("low_dollars"))
        bid_high = dollars_to_tenths((bar.get("yes_bid") or {}).get("high_dollars"))
        end_ms = int(bar.get("end_period_ts") or 0) * 1000
        rows.append(
            {
                "ticker": market.get("ticker") or "",
                "event_ticker": event_ticker,
                "series": series,
                "league": league,
                "in_scope": True,
                "market_type": market_type,
                "structure": market.get("price_level_structure"),
                "tick_tenths": tick,
                "yes_bid_tenths": bid,
                "yes_ask_tenths": ask,
                "spread_tenths": ask - bid,
                "half_spread_tenths": (ask - bid) / 2.0,
                "narrowest_spread_tenths": (
                    ask_low - bid_high
                    if ask_low is not None and bid_high is not None
                    else None
                ),
                "two_sided": True,
                "identity_checked": False,
                "identity_ok": False,
                "minutes_to_start": (start_ms - end_ms) / 60000.0,
                "volume": parse_quantity(bar.get("volume_fp")) or 0.0,
                "observed_ms": end_ms,
            }
        )
    return rows, "ok"


def panel(
    client: httpx.Client, *, days: int, window_minutes: int, now_ms: int
) -> tuple[list[dict], dict]:
    """Settled in-scope games from the last `days`, final window before start."""
    rows: list[dict] = []
    counts: dict[str, int] = defaultdict(int)
    horizon_ms = now_ms - days * 24 * 60 * 60 * 1000

    for prefix in LEAGUE_PREFIXES:
        series = f"KX{prefix}GAME"
        events = series_events(client, series, "settled")
        time.sleep(SLEEP_S)
        for event in events:
            info = classify_series(event)
            if not info.is_game_level or info.market_type is None:
                continue
            if info.sport_key is None:
                counts["events_league_out_of_scope"] += 1
                continue
            markets = event.get("markets") or []
            starts = [true_start_ms(m) for m in markets]
            known = [s for s in starts if s is not None]
            if not known:
                counts["events_no_start_time"] += 1
                continue
            start = min(known)
            if start < horizon_ms or start > now_ms:
                counts["events_outside_horizon"] += 1
                continue
            counts["events_probed"] += 1
            for market in markets:
                got, outcome = candlestick_rows(
                    client,
                    series=series,
                    market=market,
                    event_ticker=event.get("event_ticker") or "",
                    league=info.league or "",
                    market_type=info.market_type,
                    start_ms=start,
                    window_minutes=window_minutes,
                    drops=counts,
                )
                counts[f"markets_{outcome}"] += 1
                rows.extend(got)
                time.sleep(SLEEP_S)
    return rows, dict(counts)


def candlestick_can_see_width(
    client: httpx.Client, live_rows: list[dict], *, sample: int = 25
) -> dict:
    """Does a candlestick reproduce a wide spread the live book is showing?

    **This is the control the primary result stands on.** Arm B reports a
    constant one-tick spread on thousands of market-minutes. A reader's first
    duty is to suspect the instrument: a candlestick reader that silently
    normalised every bar to one tick would produce exactly that number, and it
    would be indistinguishable from a real finding.

    So: take the live markets currently quoting *wider* than one tick, pull the
    most recent one-minute bar for each, and check that the bar reports the same
    width. A match means the instrument can see width and did not see any in the
    pre-game window. A mismatch invalidates Arm B outright.

    Wide markets are plentiful and free to find -- they are the ones days away
    from kickoff, which is why Arm A exists.

    **The pass condition is width, not equality.** A one-minute bar closes up to
    sixty seconds before the live book is read, so on a moving market the two
    can legitimately differ by a tick or several; demanding exact equality would
    fail the control for the book doing its job. What the control has to rule
    out is a reader that *cannot represent* a spread wider than one tick, and
    that is answered by whether the bar is wider than one tick when the live
    book is. Exact agreement is reported beside it as information, not as the
    criterion.
    """
    candidates = sorted(
        (
            row
            for row in live_rows
            if row["two_sided"]
            and row["tick_tenths"]
            and row["spread_tenths"] > row["tick_tenths"]
        ),
        key=lambda r: -r["spread_tenths"],
    )[:sample]

    checks: list[dict] = []
    for row in candidates:
        # Re-read the live book immediately before the bars, so the two
        # observations are seconds apart rather than minutes. The cross-section
        # above can be several minutes old by the time this runs, and a stale
        # comparison would manufacture a disagreement out of the clock.
        try:
            fresh = _get(client, f"/markets/{row['ticker']}")
        except httpx.HTTPStatusError:
            continue
        time.sleep(SLEEP_S)
        market = fresh.get("market") or {}
        yes_bid = dollars_to_tenths(market.get("yes_bid_dollars"))
        no_bid = dollars_to_tenths(market.get("no_bid_dollars"))
        if yes_bid is None or no_bid is None or yes_bid <= 0 or no_bid <= 0:
            continue
        live_spread = (1000 - no_bid) - yes_bid

        now = int(time.time())
        try:
            payload = _get(
                client,
                f"/series/{row['series']}/markets/{row['ticker']}/candlesticks",
                start_ts=now - 900,
                end_ts=now,
                period_interval=1,
            )
        except httpx.HTTPStatusError:
            continue
        time.sleep(SLEEP_S)
        bars = payload.get("candlesticks") or []
        if not bars:
            continue
        last = bars[-1]
        ask = dollars_to_tenths((last.get("yes_ask") or {}).get("close_dollars"))
        bid = dollars_to_tenths((last.get("yes_bid") or {}).get("close_dollars"))
        if ask is None or bid is None:
            continue
        tick = row["tick_tenths"] or 10
        checks.append(
            {
                "ticker": row["ticker"],
                "live_spread_tenths": live_spread,
                "candle_spread_tenths": ask - bid,
                "bar_age_s": now - int(last.get("end_period_ts") or now),
                "exact": (ask - bid) == live_spread,
                # The criterion: the bar is wider than one tick when the live
                # book is. Anything else means the reader cannot see width.
                "shows_width": (ask - bid) > tick and live_spread > tick,
            }
        )

    return {
        "checked": len(checks),
        "shows_width": sum(1 for c in checks if c["shows_width"]),
        "exact_match": sum(1 for c in checks if c["exact"]),
        "max_candle_spread_tenths": max(
            (c["candle_spread_tenths"] for c in checks), default=None
        ),
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def percentile(values: list[float], q: float) -> Optional[float]:
    """Nearest-rank percentile. `q` in [0, 100]. None on an empty sample."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(q / 100.0 * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def describe(values: list[float]) -> dict:
    """The distribution, with `n` first because `n` is read first."""
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "mean": statistics.fmean(values),
        "sd": statistics.pstdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "p50": percentile(values, 50),
        "p90": percentile(values, 90),
        "p99": percentile(values, 99),
        "max": max(values),
        "distinct": len(set(values)),
    }


def spurious_slope(sd_half_spread: float) -> dict[str, float]:
    """`Var(half_spread) / Var(edge)` -- the pre-registration's own formula."""
    return {
        f"{sigma:g}": (sd_half_spread**2) / (sigma**2)
        for sigma in SIGMA_EDGE_TENTHS
    }


def selection_bound(values: list[float]) -> dict:
    """The worst spurious slope any selection of this population could produce.

    This is the answer to the one question the harness cannot measure. The CLV
    test scores a *selected* subset -- rows written where Kalshi disagrees with a
    sportsbook consensus -- and identifying that subset costs Odds API credits.
    So instead of guessing at the cut, bound it: the half-spread takes a small
    number of observed values, and **no reweighting of a two-point support can
    exceed `(max - min) / 2`**, achieved by an even split on the extremes. Any
    selection at all, however adversarial, is under that.

    Reported beside it: the slope at *inflated* wide fractions, because the
    even-split worst case is absurd when the wide value is a fraction of a
    percent of the population, and a bound nobody believes does not persuade.
    """
    if not values:
        return {}
    low, high = min(values), max(values)
    observed_wide = sum(1 for v in values if v > low) / len(values)
    worst_sd = (high - low) / 2.0

    def sd_at(fraction: float) -> float:
        return math.sqrt(fraction * (1 - fraction)) * (high - low)

    return {
        "support": sorted(set(values)),
        "observed_wide_fraction": observed_wide,
        "worst_case_sd": worst_sd,
        "worst_case_slope_by_sd_edge": spurious_slope(worst_sd),
        "slope_if_wide_fraction_were": {
            f"{f:g}": spurious_slope(sd_at(f))["10"]
            for f in (0.01, 0.05, 0.10, 0.25, 0.50)
        },
    }


def time_bucket(minutes: Optional[float]) -> str:
    if minutes is None:
        return "unknown"
    if minutes < 0:
        return "started"
    for low, high in TIME_BUCKETS:
        if low <= minutes < high:
            return f"{low}-{high}m" if high < 10**9 else f"{low}m+"
    return "started"


def price_bucket(ask_tenths: int) -> str:
    for low, high in GRID_A:
        if low <= ask_tenths < high:
            return f"[{low},{high})"
    return "off-grid"


def stratify(rows: list[dict], key) -> dict[str, dict]:
    groups: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        groups[str(key(row))].append(row["half_spread_tenths"])
    return {name: describe(values) for name, values in sorted(groups.items())}


def analyse(rows: list[dict]) -> dict:
    """Everything the write-up needs, computed once so the two cannot disagree."""
    if not rows:
        return {"n_observations": 0, "n_markets": 0, "n_games": 0}

    per_observation = [row["half_spread_tenths"] for row in rows]

    by_market: dict[str, list[float]] = defaultdict(list)
    by_game: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        by_market[row["ticker"]].append(row["half_spread_tenths"])
        by_game[row["event_ticker"] or row["ticker"]].append(
            row["half_spread_tenths"]
        )

    # One value per unit, so a market quoted for 180 minutes is one market and a
    # game's two moneyline sides are one game. The median rather than the mean:
    # a market that blows out for a single minute should move a percentile, not
    # a level.
    per_market = [statistics.median(v) for v in by_market.values()]
    per_game = [statistics.median(v) for v in by_game.values()]
    within_market = [statistics.pstdev(v) for v in by_market.values() if len(v) > 1]

    ticks = [row["tick_tenths"] for row in rows if row["tick_tenths"] is not None]
    at_floor = [
        row
        for row in rows
        if row["tick_tenths"] is not None
        and row["spread_tenths"] <= row["tick_tenths"]
    ]
    checked = [row for row in rows if row["identity_checked"]]
    violations = [row for row in checked if not row["identity_ok"]]

    overall = describe(per_observation)
    return {
        "n_observations": len(rows),
        "n_markets": len(by_market),
        "n_games": len(by_game),
        "overall": overall,
        "per_market": describe(per_market),
        "per_game": describe(per_game),
        "within_market_sd": describe(within_market),
        "spurious_slope_by_sd_edge": spurious_slope(overall.get("sd", 0.0)),
        "spurious_slope_per_game_by_sd_edge": spurious_slope(
            describe(per_game).get("sd", 0.0)
        ),
        "selection_bound": selection_bound(per_observation),
        "identity": {
            "checked": len(checked),
            "violations": len(violations),
            "violating_tickers": sorted({r["ticker"] for r in violations})[:20],
        },
        "tick": {
            "distinct_tenths": sorted(set(ticks)),
            "structures": sorted({str(r["structure"]) for r in rows}),
            "at_floor": len(at_floor),
            "at_floor_fraction": len(at_floor) / len(rows),
        },
        "by_league": stratify(rows, lambda r: r["league"]),
        "by_market_type": stratify(rows, lambda r: r["market_type"]),
        "by_price_bucket": stratify(rows, lambda r: price_bucket(r["yes_ask_tenths"])),
        "by_time_to_start": stratify(rows, lambda r: time_bucket(r["minutes_to_start"])),
        "by_two_sided": stratify(rows, lambda r: r["two_sided"]),
        # The tail, named rather than counted. "0.27% were wider" is a number a
        # reader has to take on trust; the tickers and the minutes are checkable,
        # and they are how someone later can tell a real wide quote from an
        # artefact of one bad market.
        "widest": [
            {
                "ticker": r["ticker"],
                "half_spread_tenths": r["half_spread_tenths"],
                "yes_bid_tenths": r["yes_bid_tenths"],
                "yes_ask_tenths": r["yes_ask_tenths"],
                "minutes_to_start": r["minutes_to_start"],
            }
            for r in sorted(rows, key=lambda r: -r["half_spread_tenths"])[:15]
        ],
        "markets_ever_wider_than_one_tick": len(
            {
                r["ticker"]
                for r in rows
                if r["tick_tenths"] is not None
                and r["spread_tenths"] > r["tick_tenths"]
            }
        ),
    }


def _fmt(stats: dict) -> str:
    if not stats.get("n"):
        return "n=0"
    return (
        f"n={stats['n']:<7} mean={stats['mean']:6.2f} sd={stats['sd']:6.2f} "
        f"min={stats['min']:5.1f} p50={stats['p50']:5.1f} p90={stats['p90']:6.1f} "
        f"p99={stats['p99']:6.1f} max={stats['max']:7.1f} "
        f"distinct={stats['distinct']}"
    )


def report(title: str, result: dict) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")
    if not result.get("n_observations"):
        print("  n=0 -- nothing measured. That is a broken-probe result, not a "
              "finding about spreads.")
        return
    print(
        f"  n: {result['n_games']} games, {result['n_markets']} markets, "
        f"{result['n_observations']} observations"
    )
    print("     (games is the independent count; observations is not)")

    print("\n  half-spread, tenths of a cent:")
    print(f"    per observation   {_fmt(result['overall'])}")
    print(f"    one per market    {_fmt(result['per_market'])}")
    print(f"    one per game      {_fmt(result['per_game'])}")
    print(f"    within-market sd  {_fmt(result['within_market_sd'])}")

    tick = result["tick"]
    print(f"\n  price grid: step(tenths)={tick['distinct_tenths']} "
          f"structures={tick['structures']}")
    print(f"  at the tick floor (spread <= one step): {tick['at_floor']} "
          f"({tick['at_floor_fraction']:.1%}) -- censored from below")
    print(f"  markets ever quoting wider than one tick: "
          f"{result['markets_ever_wider_than_one_tick']} of "
          f"{result['n_markets']}")

    ident = result["identity"]
    if ident["checked"]:
        print(f"\n  derived-ask identity yes_ask == 1000 - no_bid: "
              f"{ident['checked']} checked, {ident['violations']} violations")
        if ident["violations"]:
            print("  IDENTITY VIOLATED. Every half-spread above is untrustworthy; "
                  "investigate before quoting one.")
    else:
        print("\n  derived-ask identity: not checkable here (candlesticks publish "
              "yes_ask directly). See the live cross-section.")

    print("\n  spurious slope Var(half_spread)/Var(edge), by assumed sd(edge) in "
          "tenths:")
    for name, value in result["spurious_slope_by_sd_edge"].items():
        per_game = result["spurious_slope_per_game_by_sd_edge"][name]
        print(f"    sd(edge)={name:<5} per-observation {value:8.4f}   "
              f"per-game {per_game:8.4f}")

    bound = result.get("selection_bound") or {}
    if bound:
        print("\n  selection bound -- the worst spurious slope ANY cut of this "
              "population could give:")
        print(f"    support (tenths): {bound['support']}   "
              f"observed wide fraction: {bound['observed_wide_fraction']:.4%}")
        print(f"    worst-case sd (even split on the extremes): "
              f"{bound['worst_case_sd']:.2f} tenths -> slope "
              f"{bound['worst_case_slope_by_sd_edge']['10']:.4f} at sd(edge)=10")
        print("    slope at sd(edge)=10 if the wide fraction were:")
        for fraction, slope in bound["slope_if_wide_fraction_were"].items():
            print(f"      {float(fraction):>5.0%}  {slope:.4f}")

    for label, key in (
        ("by league", "by_league"),
        ("by market type", "by_market_type"),
        ("by price bucket (Grid A, on the derived ask)", "by_price_bucket"),
        ("by minutes to kickoff", "by_time_to_start"),
        ("by two-sided book", "by_two_sided"),
    ):
        print(f"\n  {label}:")
        for name, stats in result[key].items():
            print(f"    {name:<24} {_fmt(stats)}")


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Half-spread dispersion, free.")
    parser.add_argument("--days", type=int, default=3,
                        help="how far back to take settled games for the panel")
    parser.add_argument("--window-minutes", type=int, default=180,
                        help="minutes before the true start to measure")
    parser.add_argument("--skip-live", action="store_true")
    parser.add_argument("--json", default=None, help="write the full result here")
    args = parser.parse_args(list(argv) if argv is not None else None)

    started = datetime.now(timezone.utc)
    print(f"started {started.isoformat()}  days={args.days} "
          f"window={args.window_minutes}m")

    now_ms = int(time.time() * 1000)
    results: dict[str, Any] = {
        "started": started.isoformat(),
        "days": args.days,
        "window_minutes": args.window_minutes,
    }

    with httpx.Client(timeout=HTTP_TIMEOUT_S) as client:
        panel_rows, panel_counts = panel(
            client, days=args.days, window_minutes=args.window_minutes,
            now_ms=now_ms,
        )
        print(f"\npanel counts: {panel_counts}")
        results["panel_counts"] = panel_counts

        live_rows: list[dict] = []
        if not args.skip_live:
            live_rows, live_counts = live_cross_section(client)
            print(f"live counts: {live_counts}")
            results["live_counts"] = live_counts
            results["instrument_control"] = candlestick_can_see_width(
                client, live_rows
            )

    if not panel_rows and not live_rows:
        print("\nNothing measured. Broken probe, not a finding.")
        return 1

    results["panel"] = analyse(panel_rows)
    results["panel_final_15m"] = analyse(
        [r for r in panel_rows if 0 <= r["minutes_to_start"] < 15]
    )
    live_pre_game = [
        r for r in live_rows
        if r["in_scope"]
        and r["minutes_to_start"] is not None
        and r["minutes_to_start"] > 0
    ]
    results["live_pre_game_in_scope"] = analyse(live_pre_game)
    results["live_pre_game_moneyline"] = analyse(
        [r for r in live_pre_game if r["market_type"] == "moneyline"]
    )
    results["live_out_of_scope_leagues"] = analyse(
        [r for r in live_rows if not r["in_scope"]]
    )

    report(
        "PRIMARY (Arm B) -- settled in-scope games, final "
        f"{args.window_minutes} minutes before the true start, 1-minute bars. "
        "This is the window `runner.record_recommendations` operates in.",
        results["panel"],
    )
    report(
        "PRIMARY, narrowed -- the final 15 minutes only. ADR 0011 scores CLV "
        "against a candlestick inside this window.",
        results["panel_final_15m"],
    )
    report(
        "CONTROL (Arm A) -- every in-scope market open right now, any time to "
        "kickoff. Shows whether the probe can see a wide spread when one exists.",
        results["live_pre_game_in_scope"],
    )
    report(
        "CONTROL, moneyline only -- the market type "
        "`runner.record_recommendations` writes rows about.",
        results["live_pre_game_moneyline"],
    )
    report(
        "CONTEXT -- leagues Kalshi lists that `discovery.IN_SCOPE_LEAGUES` "
        "excludes. Not the population; printed so the exclusion is visible.",
        results["live_out_of_scope_leagues"],
    )

    control = results.get("instrument_control")
    if control:
        print(f"\n{'=' * 78}\nINSTRUMENT CONTROL -- can a candlestick show a wide "
              f"spread at all?\n{'=' * 78}")
        print(f"  {control['shows_width']} of {control['checked']} live "
              f"wider-than-one-tick markets came back wider than one tick in "
              f"their latest 1-minute bar")
        print(f"  exact match (bar is up to 60s older than the book): "
              f"{control['exact_match']} of {control['checked']}")
        print(f"  widest bar seen: {control['max_candle_spread_tenths']} tenths")
        if not control["checked"]:
            print("  CONTROL DID NOT RUN -- no live market was quoting wider "
                  "than one tick. Arm B's zero is unverified.")
        elif control["shows_width"] < control["checked"]:
            print("  CONTROL FAILED. A bar came back at one tick while the live "
                  "book was wider. Arm B's numbers are not trustworthy.")
        else:
            print("  Control passed: the reader can represent width, and found "
                  "none in the pre-game window.")

    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=1), encoding="utf-8")
        print(f"\nwrote {args.json}")

    print("\nWhat this bounds: the `Var(half_spread)` term in the CLV signal "
          "test's C2 confound, on the unselected pre-game population. It does "
          "not measure the selected one -- see the module docstring.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
