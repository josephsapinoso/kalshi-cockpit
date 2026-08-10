"""Follow-up to `census_band_reachability.py`: interrogate the ONE hit.

The census found a single `KXWNBAGAME` event offering both halves of the
registered price pair pre-game. One event is exactly the shape that has
misled this project before, so this script tries to break it:

  1. **Is the pre-game boundary even right for this series?** `KXWNBAGAME`
     event tickers carry no clock hour, so the ADR 0006 s1 3h-lag check that
     passed 85/85 on `KXMLBGAME` cannot run. Validate `commence_ms` instead
     against the SPORTSBOOK's own `commence_ms` for the linked event, which is
     an independent source for the true tip-off.
  2. **Is the book alive?** Print the full quote path for the market, so a
     frozen quote repeated for hours is visible as one.
  3. **Is the market settled or one-sided?** Print status, result, both bids.
  4. **Would the two halves have been simultaneously available?** A pair that
     needs one leg at 06:00 and the other at 22:00 is not one instant.

Read-only. `mode=ro`. No network, no orders, no money.

WHAT THIS DOES NOT ESTABLISH
  - **Top-of-book displayed size is NOT fill probability.** The quote path
    prints the size resting at the one level that makes our ask. A maker
    displaying it and cancelling on any incoming order produces the same path.
    No quote record separates that from real liquidity; one small order does.
  - **This script interrogates ONE event, chosen because it was the only hit.**
    That is a legitimate way to try to break a finding and an illegitimate way
    to support one. Nothing it prints can promote an n=1 cell into evidence --
    at best it fails to destroy it.
  - "Distinct ask levels > 1" rules out a book frozen for the whole window. It
    does **not** establish that the book was live at any particular instant,
    and it cannot see a quote that appeared and vanished between two polls.
  - The sportsbook `commence_ms` check validates the 3h `occurrence_datetime`
    lag only for events that are LINKED. Unlinked events are unvalidatable, not
    validated -- the printed count says which is which and both must be quoted.
  - The simultaneity query groups on exact `observed_ms`. It therefore measures
    co-occurrence **in one polling sweep**, not tradeable co-availability.
  - `status` and `result` come from the mutable `kalshi_markets` row and
    describe the market at the last discovery sweep, not at `observed_ms`.
  - One event, one week of one August.
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timedelta, timezone

COMMENCE_OFFSET_MS = 3 * 60 * 60 * 1000
LOW_LO, LOW_HI, LOW_SKIP = 60, 150, 100
HIGH_LO, HIGH_HI, HIGH_SKIP = 270, 390, 300


def utc(ms):
    return "n/a" if ms is None else datetime.fromtimestamp(
        ms / 1000, tz=timezone.utc
    ).strftime("%Y-%m-%d %H:%M:%SZ")


def et(ms):
    return "n/a" if ms is None else (
        datetime.fromtimestamp(ms / 1000, tz=timezone.utc) - timedelta(hours=4)
    ).strftime("%Y-%m-%d %H:%M ET")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True)
    ap.add_argument("--event", required=True)
    ap.add_argument("--series", required=True)
    a = ap.parse_args()
    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row

    # ---- 1. the boundary ----
    ev = con.execute(
        "SELECT * FROM kalshi_events WHERE event_ticker = ?", (a.event,)
    ).fetchone()
    print("=" * 78)
    print(f"EVENT  {a.event}")
    print("=" * 78)
    print(f"  title        : {ev['title']}")
    print(f"  status       : {ev['status']}")
    print(f"  commence_ms  : {utc(ev['commence_ms'])}   ({et(ev['commence_ms'])})")
    true_start = ev["commence_ms"] - COMMENCE_OFFSET_MS
    print(f"  -3h => start : {utc(true_start)}   ({et(true_start)})")
    print(f"  close_ms     : {utc(ev['close_ms'])}")

    link = con.execute(
        """
        SELECT l.odds_event_id, MIN(o.commence_ms) AS book_start, COUNT(*) AS n_snap,
               MIN(o.home_team) AS home, MIN(o.away_team) AS away
          FROM event_links l JOIN odds_snapshots o ON o.odds_event_id = l.odds_event_id
         WHERE l.kalshi_event_ticker = ?
        """,
        (a.event,),
    ).fetchone()
    if link and link["book_start"]:
        delta_min = (link["book_start"] - true_start) / 60000.0
        print(f"\n  INDEPENDENT CHECK -- sportsbook commence for the linked event:")
        print(f"    {link['away']} @ {link['home']}   {utc(link['book_start'])} "
              f"({et(link['book_start'])}), {link['n_snap']} snapshots")
        print(f"    sportsbook start MINUS (kalshi commence - 3h) = {delta_min:+.0f} min")
        print(f"    -> the 3h lag {'HOLDS' if abs(delta_min) < 30 else 'DOES NOT HOLD'} "
              f"for this event")
    else:
        print("\n  INDEPENDENT CHECK: event is NOT linked to any odds snapshot -- "
              "the 3h lag CANNOT be validated for this event from the record.")

    # Series-wide: same check across every linked event of the series.
    rows = con.execute(
        """
        SELECT e.event_ticker,
               e.commence_ms - ? AS derived_start,
               (SELECT MIN(o.commence_ms) FROM odds_snapshots o
                 JOIN event_links l2 ON l2.odds_event_id = o.odds_event_id
                WHERE l2.kalshi_event_ticker = e.event_ticker) AS book_start
          FROM kalshi_events e WHERE e.series_ticker = ?
        """,
        (COMMENCE_OFFSET_MS, a.series),
    ).fetchall()
    checked = [r for r in rows if r["book_start"] is not None]
    agree = [r for r in checked if abs(r["book_start"] - r["derived_start"]) < 30 * 60_000]
    print(f"\n  SERIES-WIDE 3h-lag validation for {a.series}: "
          f"{len(agree)} agree / {len(checked)} checked  (of {len(rows)} events; "
          f"{len(rows) - len(checked)} unlinked and therefore unvalidatable)")
    for r in checked:
        if r not in agree:
            print(f"    ! {r['event_ticker']}: book {utc(r['book_start'])} vs "
                  f"derived {utc(r['derived_start'])}")

    # ---- 2/3. the quote path ----
    print(f"\n  QUOTE PATH (pre-game rows only; ask = 1000 - no_bid, tenths of a cent)")
    mk = con.execute(
        "SELECT ticker, status, result, volume_24h, open_interest "
        "FROM kalshi_markets WHERE event_ticker = ? ORDER BY ticker",
        (a.event,),
    ).fetchall()
    for m in mk:
        print(f"\n  -- {m['ticker']}   status={m['status']} result={m['result']} "
              f"volume_24h={m['volume_24h']} open_interest={m['open_interest']}")
        qs = con.execute(
            "SELECT observed_ms, source, yes_bid_tenths, yes_bid_qty, no_bid_tenths, no_bid_qty "
            "FROM kalshi_quotes WHERE ticker = ? ORDER BY observed_ms", (m["ticker"],)
        ).fetchall()
        pre = [q for q in qs if q["observed_ms"] < true_start]
        asks = [None if q["no_bid_tenths"] is None else 1000 - q["no_bid_tenths"] for q in pre]
        low = [i for i, v in enumerate(asks) if v is not None and LOW_LO <= v <= LOW_HI and v != LOW_SKIP]
        high = [i for i, v in enumerate(asks) if v is not None and HIGH_LO <= v <= HIGH_HI and v != HIGH_SKIP]
        distinct = len({v for v in asks if v is not None})
        print(f"     pre-game quotes: {len(pre)}   distinct ask levels: {distinct}   "
              f"(a frozen book would show 1)")
        print(f"     LOW-band instants: {len(low)}   HIGH-band instants: {len(high)}")
        if pre:
            print(f"     first {utc(pre[0]['observed_ms'])} -> last {utc(pre[-1]['observed_ms'])} "
                  f"({(true_start - pre[-1]['observed_ms'])/60000.0:.0f} min before start)")
            step = max(1, len(pre) // 14)
            print(f"     {'observed':>22} {'ask':>7} {'ask size':>12} {'yes_bid':>8} "
                  f"{'no_bid':>7} {'src':>5}")
            for q in pre[::step]:
                ask = None if q["no_bid_tenths"] is None else 1000 - q["no_bid_tenths"]
                print(f"     {utc(q['observed_ms']):>22} "
                      f"{('n/a' if ask is None else f'{ask/10:.1f}c'):>7} "
                      f"{(q['no_bid_qty'] if q['no_bid_qty'] is not None else -1):>12,.2f} "
                      f"{str(q['yes_bid_tenths']):>8} {str(q['no_bid_tenths']):>7} {q['source']:>5}")

    # ---- 4. simultaneity ----
    print(f"\n  SIMULTANEITY: instants where SOME market of this event was in the LOW band")
    print(f"  and SOME market of this event was in the HIGH band at the same observed_ms")
    sim = con.execute(
        """
        WITH q AS (
          SELECT q.observed_ms AS t, 1000 - q.no_bid_tenths AS ask, q.no_bid_qty AS sz, q.ticker
            FROM kalshi_quotes q JOIN kalshi_markets m ON m.ticker = q.ticker
           WHERE m.event_ticker = ? AND q.no_bid_tenths IS NOT NULL AND q.observed_ms < ?
        )
        SELECT t,
               MAX(CASE WHEN ask BETWEEN ? AND ? AND ask <> ? THEN 1 ELSE 0 END) AS lo,
               MAX(CASE WHEN ask BETWEEN ? AND ? AND ask <> ? THEN 1 ELSE 0 END) AS hi
          FROM q GROUP BY t HAVING lo = 1 AND hi = 1
        """,
        (a.event, true_start, LOW_LO, LOW_HI, LOW_SKIP, HIGH_LO, HIGH_HI, HIGH_SKIP),
    ).fetchall()
    print(f"    simultaneous instants: {len(sim)}")
    if sim:
        print(f"    from {utc(sim[0]['t'])} to {utc(sim[-1]['t'])}")
    con.close()


if __name__ == "__main__":
    main()
