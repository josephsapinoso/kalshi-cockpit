"""Read-only census: is any registered price band actually FILLABLE pre-game?

Answers Q1-Q4 of LANE 1's second assignment against a stored `cockpit.db`.

WHAT THIS DOES
  Opens the SQLite record `mode=ro` and reports, per series and per event, the
  distribution of the **derived ask you would pay** -- `yes_ask = 1000 -
  best_no_bid`, tenths of a cent (`backend/core/prices.py`, `schema.sql:142`) --
  split into a PRE-GAME arm and an IN-PLAY arm, plus displayed size at that ask.

SAFETY
  - No network. No Kalshi call, no Odds API credit, no order, no deploy.
  - No writes: the connection is `file:...?mode=ro`, and nothing is inserted.

WHAT THIS DOES NOT ESTABLISH
  - **Top-of-book displayed size is NOT fill probability.** This is the one
    that governs, and every other caveat is smaller. Two worlds produce
    identical output here: real resting liquidity, and a maker showing 2,914
    contracts at 13c who cancels the instant an order arrives. Depth,
    persistence, a two-sided book and a tight spread are all consistent with
    both. **No quote record can separate them.** The separating observation is
    one small order. Nothing this script prints is evidence about what would
    fill.
  - It does not observe depth beyond the best level. `no_bid_qty` is the
    displayed size resting at the one level that makes our ask; size behind it
    is not in the record, and it is never reconciled against an orderbook
    snapshot.
  - It cannot speak to seasonality. The record is one week of one August.
  - Availability is measured on the polling grid. A price that appeared and
    vanished between two polls is invisible, so any persistence or coverage
    figure derived from this output is an **upper bound**.
  - Instants are not independent observations. Hundreds of them come from one
    polling session on one day; report game-days, events and markets as the
    sample size, never the instant count.
  - It does not decide whether a band SHOULD be registered or amended. It
    reports reachability only, and a series chosen as the best of a multi-series
    scan carries that selection.

THE TRAPS IT GUARDS -- AND THE ONE IT ONLY APPEARS TO
  1. **An empty NO book derives an ask of 1000, not 0.** Rows with
     `no_bid_tenths IS NULL` are dropped, never coerced. A `no_bid_tenths = 0`
     row derives 100.0c, which is a real (worthless) ask, not a cheap one --
     it is kept but flagged, because it is the shape that would fake a "1000"
     read if the sign were ever flipped.
  2. **Sub-15c prices in the previous census existed only after the outcome was
     known.** The protection against that is the PRE-GAME TIME BOUNDARY below,
     and only that.
  3. **`market_status` and `result` are printed but CANNOT do trap-checking,
     and must not be read as though they could.** `kalshi_markets` holds one
     mutable row per ticker, so both columns describe the market at the last
     discovery sweep -- not at `observed_ms`. A market that finalized hours
     after a legitimately pre-game quote reports `finalized` beside it. On the
     2026-08-10 run, 3,994 of 5,030 `KXMLBSPREAD` low-band rows read
     `finalized` and every one of them was a genuine pre-game observation. The
     columns are printed for context only. The one honest use of `status` is
     the reverse cut: rows on a market still `active` at pull time are the
     subset whose outcome was unknown when the record was read.

THE PRE-GAME BOUNDARY
  `observed_ms < commence_ms - 3h`. `kalshi_events.commence_ms` is Kalshi's
  `occurrence_datetime`, which runs **exactly 3 hours late** (ADR 0006 s1,
  `gate.py:899`). The 3h is subtracted to recover the true scheduled start, so
  "pre-game" here means "before first pitch/tip", with no extra cushion.
  `--validate-offset` re-checks that assumption per series against the ET clock
  time embedded in the event ticker, because it was validated for KXMLBGAME and
  must not be assumed for a new series.

USAGE
  python scripts/census_band_reachability.py --db /data/cockpit.db
  python scripts/census_band_reachability.py --db kalshi.db --series KXWNBAGAME
"""

from __future__ import annotations

import argparse
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

# Kalshi's `occurrence_datetime` runs exactly 3h late. ADR 0006 s1.
COMMENCE_OFFSET_MS = 3 * 60 * 60 * 1000

# The two halves of the registered escape, in tenths of a cent.
LOW_LO, LOW_HI, LOW_SKIP = 60, 150, 100  # 6-15c excluding 10c
HIGH_LO, HIGH_HI, HIGH_SKIP = 270, 390, 300  # 27-39c excluding 30c

# Cell N (Amendment B s.B7): C = 10 at 31-39c, so >= 10 contracts must be shown.
CELLN_LO, CELLN_HI, CELLN_SIZE = 310, 390, 10.0


def pct(sorted_vals: list[float], p: float) -> Optional[float]:
    """Nearest-rank percentile. Returns None on an empty list, never 0."""
    if not sorted_vals:
        return None
    idx = max(0, min(len(sorted_vals) - 1, int(round(p / 100.0 * (len(sorted_vals) - 1)))))
    return sorted_vals[idx]


def fmt(v: Optional[float], unit: str = "c") -> str:
    return "n/a" if v is None else f"{v / 10.0:.1f}{unit}"


def utc(ms: Optional[int]) -> str:
    if ms is None:
        return "n/a"
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def slate_of(true_start_ms: int) -> str:
    """The US slate a game belongs to: its ET calendar date."""
    return (datetime.fromtimestamp(true_start_ms / 1000, tz=timezone.utc) - timedelta(hours=4)).strftime(
        "%Y-%m-%d"
    )


def connect(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


# --------------------------------------------------------------------------
# Q1: what is actually in the record
# --------------------------------------------------------------------------

SERIES_CENSUS = """
SELECT COALESCE(m.series_ticker, 'NULL')      AS series,
       COUNT(*)                               AS quote_rows,
       COUNT(DISTINCT q.ticker)               AS markets,
       COUNT(DISTINCT m.event_ticker)         AS events,
       MIN(q.observed_ms)                     AS first_ms,
       MAX(q.observed_ms)                     AS last_ms
  FROM kalshi_quotes q
  LEFT JOIN kalshi_markets m ON m.ticker = q.ticker
 GROUP BY series
 ORDER BY quote_rows DESC
"""


def q1_series_scope(con: sqlite3.Connection) -> None:
    print("=" * 78)
    print("Q1  SERIES PRESENT IN kalshi_quotes")
    print("=" * 78)
    rows = con.execute(SERIES_CENSUS).fetchall()
    total = sum(r["quote_rows"] for r in rows)
    print(f"{'series':<18}{'quote rows':>12}{'markets':>9}{'events':>8}   window (UTC)")
    for r in rows:
        print(
            f"{r['series']:<18}{r['quote_rows']:>12,}{r['markets']:>9}{r['events']:>8}   "
            f"{utc(r['first_ms'])} -> {utc(r['last_ms'])}"
        )
    print(f"{'TOTAL':<18}{total:>12,}")
    # Events without a single quote are invisible above; name them.
    ev = con.execute(
        """
        SELECT COALESCE(e.series_ticker, 'NULL') AS series, COUNT(*) AS n
          FROM kalshi_events e
         WHERE NOT EXISTS (SELECT 1 FROM kalshi_markets m
                            WHERE m.event_ticker = e.event_ticker
                              AND EXISTS (SELECT 1 FROM kalshi_quotes q WHERE q.ticker = m.ticker))
         GROUP BY series ORDER BY n DESC
        """
    ).fetchall()
    if ev:
        print("\nevents stored with ZERO quote rows (present but never priced):")
        for r in ev:
            print(f"  {r['series']:<18}{r['n']:>6}")
    print()


# --------------------------------------------------------------------------
# The shared per-observation pull
# --------------------------------------------------------------------------

QUOTES = """
SELECT q.ticker,
       q.observed_ms,
       q.source,
       q.no_bid_tenths,
       q.no_bid_qty,
       q.yes_bid_tenths,
       m.event_ticker,
       m.market_type,
       m.status        AS market_status,
       m.result        AS market_result,
       e.commence_ms,
       e.status        AS event_status
  FROM kalshi_quotes q
  JOIN kalshi_markets m ON m.ticker = q.ticker
  JOIN kalshi_events  e ON e.event_ticker = m.event_ticker
 WHERE m.series_ticker = ?
"""


class Obs:
    """One quote row, with the ask we would actually pay derived from it."""

    __slots__ = (
        "ticker",
        "event",
        "observed_ms",
        "true_start_ms",
        "ask",
        "size",
        "pregame",
        "market_status",
        "market_result",
        "market_type",
        "source",
        "one_sided",
    )

    def __init__(self, r: sqlite3.Row):
        self.ticker = r["ticker"]
        self.event = r["event_ticker"]
        self.observed_ms = r["observed_ms"]
        self.market_status = r["market_status"]
        self.market_result = r["market_result"]
        self.market_type = r["market_type"]
        self.source = r["source"]
        # Unreadable resolves to None, never 0.
        nb = r["no_bid_tenths"]
        self.ask = None if nb is None else 1000 - nb
        self.size = r["no_bid_qty"]
        # A book with no YES bid at all is one-sided; its NO side can sit at an
        # arbitrary level with nothing on the other side to discipline it.
        self.one_sided = r["yes_bid_tenths"] is None or r["yes_bid_tenths"] == 0
        cm = r["commence_ms"]
        self.true_start_ms = None if cm is None else cm - COMMENCE_OFFSET_MS
        self.pregame = (
            None if self.true_start_ms is None else self.observed_ms < self.true_start_ms
        )


def load(con: sqlite3.Connection, series: str) -> list[Obs]:
    return [Obs(r) for r in con.execute(QUOTES, (series,))]


# --------------------------------------------------------------------------
# The 3h offset re-validation, per series
# --------------------------------------------------------------------------

TICKER_TIME = re.compile(r"-(\d{2})([A-Z]{3})(\d{2})(\d{2})")


def validate_offset(con: sqlite3.Connection, series: str) -> None:
    """Re-check the 3h `occurrence_datetime` lag against the ticker's own clock.

    Kalshi event tickers embed the ET start as `-YYMMMDDHH`. If subtracting 3h
    from `commence_ms` lands on that hour, the offset holds for this series.
    Assumed for KXMLBGAME by a prior lane; NEVER assumed for a new series.
    """
    rows = con.execute(
        "SELECT event_ticker, commence_ms FROM kalshi_events "
        "WHERE series_ticker = ? AND commence_ms IS NOT NULL",
        (series,),
    ).fetchall()
    ok = bad = unparsed = 0
    examples: list[str] = []
    for r in rows:
        m = TICKER_TIME.search(r["event_ticker"])
        if not m:
            unparsed += 1
            continue
        hh = int(m.group(4))
        # ET is UTC-4 in August.
        got = datetime.fromtimestamp(
            (r["commence_ms"] - COMMENCE_OFFSET_MS) / 1000, tz=timezone.utc
        ) - timedelta(hours=4)
        if got.hour == hh:
            ok += 1
        else:
            bad += 1
            if len(examples) < 5:
                examples.append(f"{r['event_ticker']} ticker {hh:02d}h vs derived {got.hour:02d}h")
    print(f"  3h-offset re-validation: {ok} agree / {bad} disagree / {unparsed} unparsed "
          f"(n={len(rows)} events with commence_ms)")
    for e in examples:
        print(f"    ! {e}")


# --------------------------------------------------------------------------
# Q2/Q3: per-event minimum pre-game ask, and the within-series price pair
# --------------------------------------------------------------------------


def in_band(ask: int, lo: int, hi: int, skip: int) -> bool:
    return lo <= ask <= hi and ask != skip


def band_census(con: sqlite3.Connection, series: str, market_types: Optional[set[str]]) -> None:
    label = series + ("" if market_types is None else f"  [market_type in {sorted(market_types)}]")
    print("=" * 78)
    print(f"CENSUS  {label}")
    print("=" * 78)
    validate_offset(con, series)

    obs = load(con, series)
    if market_types is not None:
        obs = [o for o in obs if o.market_type in market_types]
    if not obs:
        print("  NO ROWS. Nothing to census.\n")
        return

    readable = [o for o in obs if o.ask is not None]
    dropped_null = len(obs) - len(readable)
    undated = [o for o in readable if o.pregame is None]
    pre = [o for o in readable if o.pregame is True]
    live = [o for o in readable if o.pregame is False]

    print(f"  n rows        : {len(obs):,}  ({dropped_null:,} dropped: no_bid_tenths NULL "
          f"-> derived ask would be 1000, resolves to None)")
    print(f"  n pre-game    : {len(pre):,}   over {len({o.event for o in pre})} events, "
          f"{len({o.ticker for o in pre})} markets")
    print(f"  n in-play     : {len(live):,}   over {len({o.event for o in live})} events")
    print(f"  n undated     : {len(undated):,}   (commence_ms NULL -- cannot be classified)")

    for arm_name, arm in (("PRE-GAME", pre), ("IN-PLAY", live)):
        if not arm:
            print(f"\n  {arm_name}: no rows.")
            continue
        per_event: dict[str, int] = {}
        for o in arm:
            if o.event not in per_event or o.ask < per_event[o.event]:
                per_event[o.event] = o.ask
        mins = sorted(per_event.values())
        allv = sorted(o.ask for o in arm)
        print(f"\n  {arm_name}  --  n events = {len(mins)}, n observations = {len(allv):,}")
        print(f"    per-event MINIMUM ask : min {fmt(mins[0])}  p10 {fmt(pct(mins,10))}  "
              f"p25 {fmt(pct(mins,25))}  median {fmt(pct(mins,50))}  "
              f"p75 {fmt(pct(mins,75))}  max {fmt(mins[-1])}")
        print(f"    ALL observations      : min {fmt(allv[0])}  p1 {fmt(pct(allv,1))}  "
              f"p5 {fmt(pct(allv,5))}  p25 {fmt(pct(allv,25))}  median {fmt(pct(allv,50))}")
        # A pooled number is not a finding until the parts agree.
        by_slate: dict[str, list[int]] = defaultdict(list)
        for ev, mn in per_event.items():
            starts = [o.true_start_ms for o in arm if o.event == ev]
            by_slate[slate_of(starts[0])].append(mn)
        print(f"    per-slate view ({len(by_slate)} slates), per-event minimum:")
        for s in sorted(by_slate):
            v = sorted(by_slate[s])
            print(f"      {s}  n_events {len(v):>3}   min {fmt(v[0])}  median {fmt(pct(v,50))}  max {fmt(v[-1])}")
        big = max(by_slate.items(), key=lambda kv: len(kv[1]))
        print(f"    largest contributor: {big[0]} with {len(big[1])}/{len(mins)} events "
              f"({100*len(big[1])/len(mins):.0f}%)")

    # ---- the within-series pair, PRE-GAME only ----
    print(f"\n  BAND PAIR, PRE-GAME ONLY  (low {LOW_LO/10:.0f}-{LOW_HI/10:.0f}c excl "
          f"{LOW_SKIP/10:.0f}c ; high {HIGH_LO/10:.0f}-{HIGH_HI/10:.0f}c excl {HIGH_SKIP/10:.0f}c)")
    low_ev: dict[str, list[Obs]] = defaultdict(list)
    high_ev: dict[str, list[Obs]] = defaultdict(list)
    for o in pre:
        if in_band(o.ask, LOW_LO, LOW_HI, LOW_SKIP):
            low_ev[o.event].append(o)
        if in_band(o.ask, HIGH_LO, HIGH_HI, HIGH_SKIP):
            high_ev[o.event].append(o)
    both = sorted(set(low_ev) & set(high_ev))
    n_ev_pre = len({o.event for o in pre})
    print(f"    events with a LOW-band pre-game ask : {len(low_ev)} / {n_ev_pre}")
    print(f"    events with a HIGH-band pre-game ask: {len(high_ev)} / {n_ev_pre}")
    print(f"    events offering BOTH                : {len(both)} / {n_ev_pre}")
    if low_ev:
        sizes = sorted(o.size for evl in low_ev.values() for o in evl if o.size is not None)
        print(f"    displayed size at LOW-band ask  : n {len(sizes)}  min {sizes[0]:.0f}  "
              f"median {pct(sizes,50):.0f}  max {sizes[-1]:.0f}")
    if high_ev:
        sizes = sorted(o.size for evl in high_ev.values() for o in evl if o.size is not None)
        print(f"    displayed size at HIGH-band ask : n {len(sizes)}  min {sizes[0]:.0f}  "
              f"median {pct(sizes,50):.0f}  max {sizes[-1]:.0f}")
    for ev in both[:10]:
        print(f"      BOTH: {ev}")

    # ---- the trap check: every sub-15c PRE-GAME observation, itemised ----
    cheap = sorted(
        (o for o in pre if o.ask < LOW_HI),
        key=lambda o: o.ask,
    )
    print(f"\n  SUB-{LOW_HI/10:.0f}c PRE-GAME OBSERVATIONS: n = {len(cheap)}")
    if cheap:
        print(f"    {'ask':>6} {'size':>8} {'mkt status':>11} {'res':>4} {'1-sided':>8} "
              f"{'src':>5}  {'min from start':>15}  ticker")
        for o in cheap[:40]:
            mins_from = (o.observed_ms - o.true_start_ms) / 60000.0
            print(f"    {fmt(o.ask):>6} {(o.size if o.size is not None else -1):>8.0f} "
                  f"{str(o.market_status):>11} {str(o.market_result):>4} "
                  f"{str(o.one_sided):>8} {o.source:>5}  {mins_from:>15.0f}  {o.ticker}")
    # And the in-play arm's cheapest, reported separately so the two never mix.
    cheap_live = sorted((o for o in live if o.ask < LOW_HI), key=lambda o: o.ask)
    print(f"  sub-{LOW_HI/10:.0f}c IN-PLAY observations (reported separately): n = {len(cheap_live)}")
    if cheap_live:
        settled = sum(1 for o in cheap_live if o.market_status in ("finalized", "settled", "closed"))
        onesided = sum(1 for o in cheap_live if o.one_sided)
        print(f"    of which settled/finalized/closed: {settled}   one-sided book: {onesided}")

    # The cheapest pre-game asks regardless of band, so the floor is visible even
    # when the band is empty -- an empty band and a distant floor are different
    # findings and must not read the same.
    floor = sorted(pre, key=lambda o: o.ask)[:15]
    if floor:
        print(f"\n  CHEAPEST 15 PRE-GAME ASKS (the floor, whether or not any band contains it)")
        print(f"    {'ask':>6} {'size':>10} {'status':>10} {'1-sided':>8} "
              f"{'min from start':>15}  ticker")
        for o in floor:
            print(f"    {fmt(o.ask):>6} {(o.size if o.size is not None else -1):>10.0f} "
                  f"{str(o.market_status):>10} {str(o.one_sided):>8} "
                  f"{(o.observed_ms - o.true_start_ms)/60000.0:>15.0f}  {o.ticker}")
    print()


# --------------------------------------------------------------------------
# Units of `no_bid_qty`: settled, and DELIBERATELY NOT re-tested here.
# --------------------------------------------------------------------------
#
# `no_bid_qty` is a CONTRACT quantity, and it admits fractional values.
#
# THE ANCHOR, and it is outside the data this script reads:
#   Round one's fee calibration, fill F3 -- `KXATPDOUBLES`, C = 20, P = 0.15,
#   Kalshi's reported `fee_cost` $0.178500. And
#       0.07 * 20 * 0.15 * 0.85 = 0.178500     exactly.
#   The arithmetic only closes if `C = 20` means twenty contracts, so the
#   quantity family is a contract count. The same run's unregistered fill has
#   `count_fp = 0.27`, so it admits fractions.
#   See `docs/measurements/2026-08-10-fee-model-fill-calibration-result.md`.
#
# THERE WAS A `depth_units_check()` HERE. IT WAS DELETED, NOT REPAIRED, and the
# reason is recorded so it is not reinvented:
#
#   It cross-checked `max(no_bid_qty)` against `kalshi_markets.open_interest`
#   to decide whether the size column was a contract count or a 10^4-scaled
#   integer. But `no_bid_qty` traces to `yes_ask_size_fp`
#   (`backend/kalshi/discovery.py:634`, stored via `runner.py:914`) and
#   `open_interest` to `open_interest_fp` (`backend/kalshi/discovery.py:625`).
#   Both are read by a plain `float()` with no unscaling: the SAME `_fp`
#   family. Their ratio is therefore INVARIANT under any common rescaling --
#   which is precisely the transformation the test existed to detect. **The
#   guard could not fail.** CLAUDE.md: a guard that cannot fail is decoration.
#
#   Its printed inference was also backwards. It claimed "a fraction below 1
#   proves the column is a CONTRACT count". A fractional value *disproves* an
#   integer count; it cannot prove one. (The record holds 9,676 distinct
#   non-integer sizes -- 6.87, 8.86, 12.8, ... -- so the column is a
#   fraction-admitting quantity, which is what the F3 anchor independently says.)
#
#   `tasks/lessons.md`: "Never anchor a convention test on a fixed point of the
#   transformation." This was that lesson recurring in the same shape.


# --------------------------------------------------------------------------
# Q4: Cell N reachability -- 31-39c with >= 10 displayed
# --------------------------------------------------------------------------


def cell_n(con: sqlite3.Connection, series: str) -> None:
    print("=" * 78)
    print(f"Q4  CELL N REACHABILITY -- {series}, derived ask in "
          f"[{CELLN_LO/10:.0f}c, {CELLN_HI/10:.0f}c], displayed size >= {CELLN_SIZE:.0f}")
    print("=" * 78)
    obs = [o for o in load(con, series) if o.ask is not None and o.pregame is True]
    n_ev = len({o.event for o in obs})
    print(f"  n pre-game events in record: {n_ev}   n pre-game observations: {len(obs):,}")

    in_price = [o for o in obs if CELLN_LO <= o.ask <= CELLN_HI]
    with_size = [o for o in in_price if o.size is not None and o.size >= CELLN_SIZE]
    ev_price = {o.event for o in in_price}
    ev_size = {o.event for o in with_size}
    instants_price = {(o.event, o.observed_ms) for o in in_price}
    instants_size = {(o.event, o.observed_ms) for o in with_size}

    print(f"  price only  : {len(ev_price)}/{n_ev} events ({100*len(ev_price)/max(n_ev,1):.0f}%), "
          f"{len(in_price):,} observations, {len(instants_price):,} event-instants")
    print(f"  price+depth : {len(ev_size)}/{n_ev} events ({100*len(ev_size)/max(n_ev,1):.0f}%), "
          f"{len(with_size):,} observations, {len(instants_size):,} event-instants")
    missing_size = sum(1 for o in in_price if o.size is None)
    print(f"  (of the price-only rows, {missing_size:,} carry no displayed size at all "
          f"-> excluded, not counted as zero)")

    if in_price:
        sizes = sorted(o.size for o in in_price if o.size is not None)
        print(f"  displayed size at a 31-39c pre-game ask: n {len(sizes):,}  "
              f"min {sizes[0]:.0f}  p10 {pct(sizes,10):.0f}  median {pct(sizes,50):.0f}  "
              f"p90 {pct(sizes,90):.0f}  max {sizes[-1]:.0f}")
        share_ge10 = 100.0 * sum(1 for s in sizes if s >= CELLN_SIZE) / len(sizes)
        print(f"  share of those with size >= {CELLN_SIZE:.0f}: {share_ge10:.1f}%")

    # per-slate, so the pooled number is checkable
    by_slate: dict[str, set[str]] = defaultdict(set)
    tot_slate: dict[str, set[str]] = defaultdict(set)
    for o in obs:
        tot_slate[slate_of(o.true_start_ms)].add(o.event)
    for o in with_size:
        by_slate[slate_of(o.true_start_ms)].add(o.event)
    print("  per-slate (events with a qualifying price+depth instant / events pre-game):")
    for s in sorted(tot_slate):
        print(f"    {s}   {len(by_slate.get(s, set())):>3} / {len(tot_slate[s]):>3}")
    if by_slate:
        big = max(by_slate.items(), key=lambda kv: len(kv[1]))
        print(f"  largest contributor: {big[0]} with {len(big[1])}/{len(ev_size)} qualifying events "
              f"({100*len(big[1])/max(len(ev_size),1):.0f}%)")

    # Guard: are the qualifying instants concentrated in one market or spread out?
    per_market = defaultdict(int)
    for o in with_size:
        per_market[o.ticker] += 1
    if per_market:
        top = sorted(per_market.items(), key=lambda kv: -kv[1])[:5]
        print(f"  distinct markets with a qualifying instant: {len(per_market)}; top 5 by instants:")
        for t, c in top:
            print(f"    {c:>6}  {t}")
    print()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True, help="path to cockpit.db (opened mode=ro)")
    ap.add_argument("--series", action="append", help="series to census (repeatable)")
    ap.add_argument("--cell-n-series", default="KXMLBGAME")
    ap.add_argument(
        "--game-types",
        default="moneyline",
        help="comma-separated market_type filter for the band census, or ALL",
    )
    args = ap.parse_args()

    con = connect(args.db)
    q1_series_scope(con)
    print("market_type mix per series censused:")
    for r in con.execute(
        "SELECT series_ticker, COALESCE(market_type,'NULL') mt, COUNT(*) n "
        "FROM kalshi_markets GROUP BY 1,2 ORDER BY 1,3 DESC"
    ):
        print(f"  {r['series_ticker']:<18}{r['mt']:<14}{r['n']:>6}")
    print()

    mt = None if args.game_types.upper() == "ALL" else set(args.game_types.split(","))
    present = {r[0] for r in con.execute(
        "SELECT DISTINCT series_ticker FROM kalshi_markets WHERE series_ticker IS NOT NULL"
    )}
    for s in args.series or []:
        if s not in present:
            print("=" * 78)
            print(f"CENSUS  {s}:  ABSENT from kalshi_markets. Cannot be censused from the record.")
            print("=" * 78 + "\n")
            continue
        band_census(con, s, mt)

    if args.cell_n_series in present:
        cell_n(con, args.cell_n_series)
    else:
        print(f"Q4: {args.cell_n_series} absent from the record.")
    con.close()


if __name__ == "__main__":
    main()
