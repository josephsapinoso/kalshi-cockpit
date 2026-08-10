"""Third pass: the pair at SERIES level, and Cell N's rows stress-tested.

Two things the first two passes left open.

**(a) The escape is a within-SERIES pair, not a within-event one.** s.B3(c) of
the round-two registration pairs a low-price cell with a same-series high-price
cell so that price is the only thing that varies. The event-level count is
therefore too strict. But "the series reached 13c in one game on Monday and 35c
in another on Friday" is too loose: you can only buy what is on the board when
you are at the board. The honest statistic is the number of **instants at which
the series simultaneously showed both halves**, and the number of distinct
**event-pairs** that could have supplied them.

**(b) Cell N's 31-39c MLB rows have not been checked for the trap.** A price is
not fillable because it is in the table. Break the qualifying rows down by
market status, book two-sidedness, source, and -- since a measurement has to be
executed by a human at a keyboard -- how close to first pitch they occurred.

Read-only. `mode=ro`. No network, no orders, no money.

WHAT THIS DOES NOT ESTABLISH
  - **Top-of-book displayed size is NOT fill probability.** A maker showing
    2,914 contracts at 13c who cancels on any incoming order produces exactly
    this output. Simultaneity, depth and a tight spread do not distinguish that
    world from real resting liquidity, and no quote record can. The separating
    observation is one small order.
  - **An "instant" is not an observation.** The instant count is polling
    uptime. On the 2026-08-10 run, 64% of 696 instants came from a single
    observation day and 261 polling sessions covered all of them. The sample
    size is game-days (4), events (55) and markets (330) -- never 696.
  - Simultaneity is simultaneity **on the polling grid**. Two prices sharing an
    `observed_ms` were seen in one sweep; they were not necessarily lift-able
    together, and a price present between polls is invisible either way.
  - It says nothing about which SIDE of a pair is mispriced, or about edge. It
    reports that two prices coexisted, not that either is wrong.
  - `market_status` and `result` are the CURRENT values from the mutable
    `kalshi_markets` row, not the values at `observed_ms`. A market that
    finalized after a pre-game quote still reads `finalized` beside it. The
    pre-game time filter, not the status column, is what excludes settled-market
    artefacts.
  - Cell N's stress test reports the span between a market's first and last
    qualifying observation. That span is **not** a continuous window -- gaps
    inside it are not detected.
  - One week of one August. Nothing about another month or a thinner slate.
"""

from __future__ import annotations

import argparse
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone

COMMENCE_OFFSET_MS = 3 * 60 * 60 * 1000
LOW_LO, LOW_HI, LOW_SKIP = 60, 150, 100
HIGH_LO, HIGH_HI, HIGH_SKIP = 270, 390, 300
CELLN_LO, CELLN_HI, CELLN_SIZE = 310, 390, 10.0


def utc(ms):
    return "n/a" if ms is None else datetime.fromtimestamp(
        ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%MZ")


def slate(ms):
    return (datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
            - timedelta(hours=4)).strftime("%Y-%m-%d")


PULL = """
SELECT q.observed_ms AS t, q.ticker, q.no_bid_tenths AS nb, q.no_bid_qty AS sz,
       q.yes_bid_tenths AS yb, q.source AS src,
       m.event_ticker AS ev, m.status AS mstatus, m.result AS mresult,
       e.commence_ms - ? AS start
  FROM kalshi_quotes q
  JOIN kalshi_markets m ON m.ticker = q.ticker
  JOIN kalshi_events  e ON e.event_ticker = m.event_ticker
 WHERE m.series_ticker = ? AND q.no_bid_tenths IS NOT NULL
   AND e.commence_ms IS NOT NULL
"""


def load(con, series):
    rows = []
    for r in con.execute(PULL, (COMMENCE_OFFSET_MS, series)):
        if r["t"] >= r["start"]:
            continue  # in-play, reported elsewhere
        rows.append(
            dict(t=r["t"], ticker=r["ticker"], ask=1000 - r["nb"], sz=r["sz"],
                 yb=r["yb"], src=r["src"], ev=r["ev"], mstatus=r["mstatus"],
                 mresult=r["mresult"], start=r["start"])
        )
    return rows


def series_pair(con, series):
    print("=" * 78)
    print(f"SERIES-LEVEL PAIR SIMULTANEITY -- {series}, PRE-GAME ONLY")
    print("=" * 78)
    rows = load(con, series)
    n_inst = len({r["t"] for r in rows})
    print(f"  n pre-game observations: {len(rows):,} across {n_inst:,} distinct polling "
          f"instants and {len({r['ev'] for r in rows})} events")

    lo_at = defaultdict(set)
    hi_at = defaultdict(set)
    for r in rows:
        a = r["ask"]
        if LOW_LO <= a <= LOW_HI and a != LOW_SKIP:
            lo_at[r["t"]].add(r["ev"])
        if HIGH_LO <= a <= HIGH_HI and a != HIGH_SKIP:
            hi_at[r["t"]].add(r["ev"])
    both_t = sorted(set(lo_at) & set(hi_at))
    # THE WITHIN-EVENT STATISTIC. This replaced a `cross` count that reported
    # "of which the two halves came from different events" via
    #   (lo|hi) - (lo&hi) or len(lo|hi) > 1
    # That expression is not WRONG -- its first clause is redundant (if two
    # non-empty sets differ, their union already has >= 2 members), so it
    # reduces to `len(lo|hi) > 1`, which is the correct test. It is USELESS.
    # With ~40 events showing a low ask and ~55 showing a high ask at every
    # instant, `len(union) > 1` is true by construction; on the 2026-08-10 run
    # it duly returned 696 of 696. A statistic that cannot come out any other
    # way in this population is not evidence, and printing it under a label
    # that sounds like a test is how a reader gets misled.
    #
    # The informative question is the STRONGER one: does a SINGLE event supply
    # both halves at the same instant? That is a real claim about the shape of
    # the book, and it can fail -- `KXWNBAGAME` fails it (0 simultaneous
    # instants; one market drifting across time, counted as "both" only by an
    # event-level tally that ignores when).
    within = [t for t in both_t if lo_at[t] & hi_at[t]]
    print(f"  instants showing a LOW-band ask anywhere in the series : {len(lo_at):,}")
    print(f"  instants showing a HIGH-band ask anywhere in the series: {len(hi_at):,}")
    print(f"  instants showing BOTH simultaneously                   : {len(both_t):,}"
          f"  ({100*len(both_t)/max(n_inst,1):.1f}% of instants)")
    print(f"    of which a SINGLE EVENT supplied both halves         : {len(within):,}"
          f"  ({100*len(within)/max(len(both_t),1):.1f}% of the simultaneous instants)")
    if within:
        ev_both = set()
        for t in within:
            ev_both |= lo_at[t] & hi_at[t]
        print(f"    distinct events that ever supplied both halves      : {len(ev_both)}")
    if both_t:
        print(f"    window: {utc(both_t[0])} -> {utc(both_t[-1])}")
        by_slate = defaultdict(int)
        for t in both_t:
            by_slate[slate(t)] += 1
        print("    per-slate (by observation date, not game date):")
        for s in sorted(by_slate):
            print(f"      {s}  {by_slate[s]:>6} instants")
        big = max(by_slate.items(), key=lambda kv: kv[1])
        print(f"    largest contributor: {big[0]} with {big[1]}/{len(both_t)} "
              f"({100*big[1]/len(both_t):.0f}%)")
        lo_evs, hi_evs = set(), set()
        for t in both_t:
            lo_evs |= lo_at[t]
            hi_evs |= hi_at[t]
        print(f"    distinct events supplying the LOW half : {len(lo_evs)}  {sorted(lo_evs)[:6]}")
        print(f"    distinct events supplying the HIGH half: {len(hi_evs)}")
    # The depth at each half, at those simultaneous instants only.
    for name, lo, hi, skip in (("LOW", LOW_LO, LOW_HI, LOW_SKIP),
                               ("HIGH", HIGH_LO, HIGH_HI, HIGH_SKIP)):
        szs = sorted(r["sz"] for r in rows
                     if r["t"] in set(both_t) and lo <= r["ask"] <= hi and r["ask"] != skip
                     and r["sz"] is not None)
        if szs:
            print(f"    depth at {name:<4} half over those instants: n {len(szs)}  "
                  f"min {szs[0]:,.2f}  median {szs[len(szs)//2]:,.2f}  max {szs[-1]:,.2f}")
            print(f"      share with >= 1 contract: "
                  f"{100*sum(1 for s in szs if s >= 1)/len(szs):.0f}%")
    print()


def cell_n_stress(con, series):
    print("=" * 78)
    print(f"CELL N STRESS TEST -- {series}, pre-game ask in [31c,39c], size >= 10")
    print("=" * 78)
    rows = [r for r in load(con, series) if CELLN_LO <= r["ask"] <= CELLN_HI]
    ok = [r for r in rows if r["sz"] is not None and r["sz"] >= CELLN_SIZE]
    print(f"  qualifying observations: {len(ok):,} of {len(rows):,} in the price band")
    status = defaultdict(int)
    for r in ok:
        status[(r["mstatus"], r["mresult"], r["yb"] is None or r["yb"] == 0, r["src"])] += 1
    print(f"  {'status':>10} {'result':>7} {'one-sided':>10} {'src':>6} {'n':>8}")
    for k, v in sorted(status.items(), key=lambda kv: -kv[1]):
        print(f"  {str(k[0]):>10} {str(k[1]):>7} {str(k[2]):>10} {k[3]:>6} {v:>8,}")
    # How close to first pitch -- a band only reachable at 3am is not operable.
    lead = sorted((r["start"] - r["t"]) / 60000.0 for r in ok)
    print(f"  minutes before first pitch: min {lead[0]:.0f}  p10 {lead[len(lead)//10]:.0f}  "
          f"median {lead[len(lead)//2]:.0f}  max {lead[-1]:.0f}")
    within = [x for x in lead if x <= 180]
    print(f"  observations within 3h of first pitch: {len(within):,} "
          f"({100*len(within)/len(lead):.0f}%)")
    ev_within = {r["ev"] for r in ok if (r["start"] - r["t"]) / 60000.0 <= 180}
    print(f"  events qualifying within 3h of first pitch: {len(ev_within)}")
    # Per-event: how long the window lasted.
    dur = []
    per_ev = defaultdict(list)
    for r in ok:
        per_ev[r["ev"]].append(r["t"])
    for ev, ts in per_ev.items():
        dur.append((max(ts) - min(ts)) / 60000.0)
    dur.sort()
    print(f"  per-event span of the qualifying window (min): min {dur[0]:.0f}  "
          f"median {dur[len(dur)//2]:.0f}  max {dur[-1]:.0f}   (n_events {len(dur)})")
    print()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True)
    ap.add_argument("--pair-series", action="append", default=[])
    ap.add_argument("--cell-n-series", default="KXMLBGAME")
    a = ap.parse_args()
    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    for s in a.pair_series:
        series_pair(con, s)
    cell_n_stress(con, a.cell_n_series)
    con.close()


if __name__ == "__main__":
    main()
