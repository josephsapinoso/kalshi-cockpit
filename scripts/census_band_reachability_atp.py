"""Fourth pass: is `KXATPDOUBLES` anywhere in the record, and when is the
WNBA low band actually on the board?

Q1 asked whether tennis is in the stored record *at all*. `kalshi_quotes` is
not the only place it could be: the account has a settled `KXATPDOUBLES`
position from the round-one fee calibration, so the series can be present in
`orders`/`fills`/`settlements` while being absent from discovery. Absence from
discovery and absence from the account are different facts and this separates
them.

The second half answers the operability question the round-two failure turned
on: a band that only exists at 04:00 UTC is not a band a human can fill. Report
the lead time of every low-band pre-game instant.

Read-only. `mode=ro`. No network, no orders, no money.

WHAT THIS DOES NOT ESTABLISH
  - **Top-of-book displayed size is NOT fill probability.** The depth lines
    below report what a maker chose to display at the level that makes our ask.
    A quote shown and pulled on any incoming order is indistinguishable here
    from real resting size. No quote record separates them; one small order
    does.
  - **Absence from the record is not absence from Kalshi.** A zero row count
    for a series means discovery never stored it. `KXATPDOUBLES` returning 0
    everywhere says the tool cannot price tennis from disk -- it does NOT say
    the series has no markets, and any ATP decision needs a live board read.
  - **The `orders` / `fills` / `settlements` arm of the search is VACUOUS on
    the current deployment and must not be reported as a passing check.** Those
    tables hold zero rows in total, so "0 rows matching KXATP%" could not have
    come out any other way. Nothing in production writes them; the round-one
    ATP fills live at Kalshi and never enter the local tables. See §S11 of
    `docs/measurements/2026-08-10-fee-model-fill-calibration-result.md`.
  - The lead-time and ET-hour histograms describe when a price was OBSERVED,
    which is a fact about the polling schedule as much as about the board. An
    hour with few instants will show few hits regardless of availability;
    normalise by instants per hour before reading any pattern into it.
  - Lead time is measured from `commence_ms - 3h`. That offset is validated
    per series elsewhere and is assumed here.
  - One week of one August, and only two series are examined.
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timedelta, timezone

COMMENCE_OFFSET_MS = 3 * 60 * 60 * 1000
LOW_LO, LOW_HI, LOW_SKIP = 60, 150, 100


def utc(ms):
    return "n/a" if ms is None else datetime.fromtimestamp(
        ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%MZ")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True)
    a = ap.parse_args()
    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row

    print("=" * 78)
    print("Q1(b)  WHERE COULD TENNIS BE HIDING?")
    print("=" * 78)
    print("  kalshi_series rows (the discovery universe, whether or not priced):")
    for r in con.execute(
        "SELECT series_ticker, league, has_game_markets, category FROM kalshi_series "
        "ORDER BY series_ticker"
    ):
        print(f"    {r['series_ticker']:<20}{str(r['league']):<10}"
              f"has_game_markets={str(r['has_game_markets']):<6}{str(r['category'])}")
    for tbl, col in (("kalshi_events", "event_ticker"), ("kalshi_markets", "ticker"),
                     ("orders", "ticker"), ("fills", "ticker"), ("settlements", "ticker"),
                     ("recommendations", "ticker")):
        try:
            n = con.execute(
                f"SELECT COUNT(*) FROM {tbl} WHERE {col} LIKE 'KXATP%'"
            ).fetchone()[0]
            tot = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            print(f"  {tbl:<18} rows matching 'KXATP%': {n:<6} (of {tot:,} total)")
        except sqlite3.Error as exc:
            print(f"  {tbl:<18} not queryable: {exc}")

    print()
    print("=" * 78)
    print("OPERABILITY  -- lead time of every LOW-band pre-game instant, by series")
    print("=" * 78)
    for series in ("KXWNBAGAME", "KXMLBGAME"):
        rows = con.execute(
            """
            SELECT q.observed_ms AS t, q.no_bid_qty AS sz, m.ticker, m.event_ticker AS ev,
                   e.commence_ms - ? AS start
              FROM kalshi_quotes q
              JOIN kalshi_markets m ON m.ticker = q.ticker
              JOIN kalshi_events  e ON e.event_ticker = m.event_ticker
             WHERE m.series_ticker = ? AND q.no_bid_tenths IS NOT NULL
               AND e.commence_ms IS NOT NULL
               AND (1000 - q.no_bid_tenths) BETWEEN ? AND ?
               AND (1000 - q.no_bid_tenths) <> ?
               AND q.observed_ms < e.commence_ms - ?
             ORDER BY q.observed_ms
            """,
            (COMMENCE_OFFSET_MS, series, LOW_LO, LOW_HI, LOW_SKIP, COMMENCE_OFFSET_MS),
        ).fetchall()
        print(f"\n  {series}: {len(rows)} low-band pre-game instants, "
              f"{len({r['ev'] for r in rows})} events, {len({r['ticker'] for r in rows})} markets")
        if not rows:
            continue
        leads = sorted((r["start"] - r["t"]) / 60000.0 for r in rows)
        print(f"    lead time before tip (min): min {leads[0]:.0f}  median "
              f"{leads[len(leads)//2]:.0f}  max {leads[-1]:.0f}")
        for band, lo, hi in (("<= 60 min", 0, 60), ("60-180 min", 60, 180),
                             ("3-12 h", 180, 720), ("> 12 h", 720, 1e9)):
            n = sum(1 for x in leads if lo < x <= hi)
            print(f"      {band:<12}{n:>6} instants")
        # Wall-clock hours in US Eastern, since a human has to be awake.
        hours = {}
        for r in rows:
            h = (datetime.fromtimestamp(r["t"] / 1000, tz=timezone.utc)
                 - timedelta(hours=4)).hour
            hours[h] = hours.get(h, 0) + 1
        print("    observation hour (ET) -> instants: "
              + ", ".join(f"{h:02d}h:{n}" for h, n in sorted(hours.items())))
        szs = sorted(r["sz"] for r in rows if r["sz"] is not None)
        if szs:
            print(f"    depth at the low-band ask: n {len(szs)}  min {szs[0]:,.2f}  "
                  f"median {szs[len(szs)//2]:,.2f}  max {szs[-1]:,.2f}")
            for thr in (1, 10, 21):
                print(f"      share with >= {thr:>2} contracts: "
                      f"{100*sum(1 for s in szs if s >= thr)/len(szs):.0f}%")
        print(f"    first instant {utc(rows[0]['t'])}, last {utc(rows[-1]['t'])} "
              f"(last poll in DB: {utc(con.execute('SELECT MAX(observed_ms) FROM kalshi_quotes').fetchone()[0])})")
    con.close()


if __name__ == "__main__":
    main()
