"""Fifth pass: the low band across EVERY series in the record, not just the
three the assignment named.

The three candidate escapes were chosen before anyone looked. The record holds
eleven series; if the low price the design needs is routine somewhere else, the
choice of escape should know that. This does not propose one -- it reports
where the price occurs.

Bands are the REGISTERED ones and are not widened, shifted or re-tuned here.

Read-only. `mode=ro`. No network, no orders, no money.

WHAT THIS DOES NOT ESTABLISH
  - **Top-of-book displayed size is NOT fill probability.** The `ev_celln`
    column counts events whose displayed size cleared 10 contracts. Displayed
    size is what a maker chose to show; it is not a promise, and a quoting
    maker who pulls on any incoming order produces an identical column. No
    quote record separates the two. One small order does.
  - **This is a MULTI-SERIES SCAN, so its winner is a SELECTED MAXIMUM.**
    Eleven series x two bands is 22 cells. Whichever series tops this table was
    chosen after looking, and any figure quoted from it carries that selection.
    A cell resting on one or two events is noise until it is interrogated
    per-event, which this script does not do.
  - It reports event COUNTS, never simultaneity. "40 events reached the low
    band and 55 reached the high band" does **not** mean both were ever on the
    board at once -- `KXWNBAGAME` satisfies the event-level test with a single
    market that drifted down over hours, and has zero simultaneous instants.
    Use `census_band_reachability_pair.py` for that question.
  - `min_ask` is one observation. It carries no information about how long the
    price stood, whether size was behind it, or whether it recurred.
  - No trap-checking at all: no book two-sidedness, no spread, no frozen-quote
    check, no market-status breakdown. A price here may be an artefact and this
    script would not notice.
  - One week of one August, and only series that discovery actually stored.
    Absence from this table is absence from the record, not absence from Kalshi.
"""

from __future__ import annotations

import argparse
import sqlite3

COMMENCE_OFFSET_MS = 3 * 60 * 60 * 1000
LOW_LO, LOW_HI, LOW_SKIP = 60, 150, 100
HIGH_LO, HIGH_HI, HIGH_SKIP = 270, 390, 300

SQL = """
WITH pre AS (
  SELECT m.series_ticker AS s, m.event_ticker AS ev, q.observed_ms AS t,
         1000 - q.no_bid_tenths AS ask, q.no_bid_qty AS sz
    FROM kalshi_quotes q
    JOIN kalshi_markets m ON m.ticker = q.ticker
    JOIN kalshi_events  e ON e.event_ticker = m.event_ticker
   WHERE q.no_bid_tenths IS NOT NULL
     AND e.commence_ms IS NOT NULL
     AND q.observed_ms < e.commence_ms - :off
)
SELECT s,
       COUNT(DISTINCT ev)                                            AS events,
       COUNT(*)                                                      AS obs,
       MIN(ask)                                                      AS min_ask,
       COUNT(DISTINCT CASE WHEN ask BETWEEN :llo AND :lhi AND ask <> :lsk
                           THEN ev END)                              AS ev_low,
       SUM(CASE WHEN ask BETWEEN :llo AND :lhi AND ask <> :lsk
                THEN 1 ELSE 0 END)                                   AS obs_low,
       COUNT(DISTINCT CASE WHEN ask BETWEEN :hlo AND :hhi AND ask <> :hsk
                           THEN ev END)                              AS ev_high,
       COUNT(DISTINCT CASE WHEN ask BETWEEN 310 AND 390 AND sz >= 10
                           THEN ev END)                              AS ev_celln
  FROM pre
 GROUP BY s
 ORDER BY ev_low DESC, min_ask ASC
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True)
    a = ap.parse_args()
    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    print("PRE-GAME ONLY (observed_ms < commence_ms - 3h). Derived ask = 1000 - best NO bid.")
    print("low = 6-15c excl 10c ; high = 27-39c excl 30c ; cellN = 31-39c with size >= 10\n")
    print(f"{'series':<16}{'events':>7}{'pre-game obs':>14}{'min ask':>9}"
          f"{'ev w/ low':>11}{'obs low':>9}{'ev w/ high':>12}{'ev w/ cellN':>13}")
    for r in con.execute(SQL, dict(off=COMMENCE_OFFSET_MS, llo=LOW_LO, lhi=LOW_HI,
                                   lsk=LOW_SKIP, hlo=HIGH_LO, hhi=HIGH_HI, hsk=HIGH_SKIP)):
        print(f"{r['s']:<16}{r['events']:>7}{r['obs']:>14,}{r['min_ask']/10:>8.1f}c"
              f"{r['ev_low']:>11}{r['obs_low']:>9,}{r['ev_high']:>12}{r['ev_celln']:>13}")
    con.close()


if __name__ == "__main__":
    main()
