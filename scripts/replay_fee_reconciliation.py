"""Replay the shipped fee reconciliation over stored hand fills, read-only.

    .venv\\Scripts\\python.exe scripts\\replay_fee_reconciliation.py [--db PATH]

Imports `predict_fill_fee` / `reconcile_fill` from `backend.portfolio_poll`
rather than reimplementing the comparison, so what this prints is what the
poller does. Opens the database read-only and writes nothing.

**What this harness does NOT establish.**

- **Not whether `core/fees.py` is correct.** The alarm is one-sided (it fires
  only on an undercharge), so a silent row is equally consistent with a
  prediction that is far too high -- and on baseball it is, by ADR 0058 policy,
  exactly 2.00x. A silent replay is not evidence the fee model is right.
- **Not `calculate_fee`'s never-under property.** That property is REFUTED on
  combinations (`core/fees.py:91-107`, ADR 0046) and `calculate_fee` is not the
  model used there; combos are reconciled against the `combo_taker_fee`
  ceiling. Never cite a silent combo row as support for `calculate_fee`.
- **Rows are fills, and the measured model rounds per ORDER**
  (`core/fees.py:62`). Where several fills answer one order, evaluating per
  fill sums several ceilings against one charge, biasing `predicted` UPWARD --
  further toward silence on a one-sided test. The `ords` column is the distinct
  `venue_order_id` count per group so the inflation is visible rather than
  argued; when `ords == n` there is none.
- **Not the whole betting history.** `/portfolio/fills` retains roughly three
  months (`backend/store/schema.sql:1650`), so this is the mirror's window.
  The window is printed; read it before the counts.
- **Not the workload the poller runs.** Production reconciles only *newly
  stored* rows and dedupes alerts per day, so a bulk replay is not that shape.

**Headroom, and why the denominator is not the row count.** A row is only
informative if the alarm could fire on it at all. Two populations cannot fire
without an implausible schedule move: combinations, priced by a ceiling that
exceeds every observed charge *by construction* (`core/fees.py:352-357`), and
anything the venue charges at k = 0.035 while this repo predicts at 0.070 (ADR
0058 keeps that 2.00x deliberately). Counting those rows in the denominator
overstates what was tested, so the summary prints the count of rows where
`predicted == charged` and calls that the informative denominator.

**Read `implied k`, not `worst$`.** The fee scales with `C*P*(1-P)`, so an
absolute dollar gap is not comparable across rows of different size, and on a
row whose charge lands on the $0.0001 grid the smallest non-zero gap the
statistic can take IS $0.0001 -- the instrument's floor, not a near miss.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.portfolio_poll import (  # noqa: E402
    ParsedFill,
    predict_fill_fee,
    reconcile_fill,
)

#: Headroom above which a row cannot realistically fire. Derived per row from
#: `(predicted - actual) / actual`, NOT from a list of tickers.
#:
#: **The first version of this was a hardcoded prefix list and it was wrong on
#: its first run.** It named the three MLB prefixes as the ones carrying ADR
#: 0058's 2.00x, and the very first replay turned up `KXEARNINGSMENTIONKLAR` at
#: a ratio of 0.5000 -- the same 2x, on a non-sports earnings market. A
#: hand-maintained list of "the ones that are fine" is the wrong shape for this
#: question: it has to be right about a population nobody has enumerated, and
#: when it is wrong it is wrong in the direction of overstating how much was
#: tested. Headroom is a property of the row and needs no such list.
NEGLIGIBLE_HEADROOM = 0.001   # one part in a thousand: at the $0.0001 grid this
                              # is the "predicted == charged" band
MATERIAL_HEADROOM = 0.05      # 5%: above this a schedule move smaller than the
                              # headroom cannot surface at all


def _parsed(row: dict) -> ParsedFill:
    return ParsedFill(
        kalshi_fill_id=str(row.get("kalshi_fill_id") or row.get("venue_fill_id") or ""),
        ticker=row["ticker"],
        filled_ms=row["filled_ms"],
        count=row["count"],
        price_tenths=row["price_tenths"],
        is_taker=bool(row.get("is_taker", 1)),
        fee_actual=row.get("fee_actual"),
        venue_order_id=row.get("venue_order_id"),
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/cockpit.db")
    ap.add_argument("--source", default="venue_hand")
    args = ap.parse_args()

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = [
        dict(r)
        for r in conn.execute(
            "select * from fills where source=? order by filled_ms", (args.source,)
        )
    ]
    conn.close()

    if not rows:
        print(f"no fills with source={args.source!r}")
        return 1

    # The window, printed before any count -- three months of retention is not
    # a betting history.
    lo, hi = rows[0]["filled_ms"], rows[-1]["filled_ms"]
    days = {time.strftime("%Y-%m-%d", time.gmtime(r["filled_ms"] / 1000)) for r in rows}
    print(f"window: {time.strftime('%Y-%m-%d', time.gmtime(lo / 1000))} .. "
          f"{time.strftime('%Y-%m-%d', time.gmtime(hi / 1000))}  "
          f"({len(days)} distinct days)")
    print(f"n = {len(rows)} fills, source={args.source}\n")

    groups: dict[str, dict] = {}
    refused: list[tuple[str, str | None]] = []

    for row in rows:
        parsed = _parsed(row)
        rec = reconcile_fill(parsed)
        prefix = parsed.ticker.split("-")[0]
        if rec is None:
            refused.append((parsed.ticker, predict_fill_fee(parsed).refusal))
            continue
        g = groups.setdefault(
            prefix,
            {"n": 0, "orders": set(), "fired": 0, "worst": None, "ratios": [],
             "k": [], "headroom": [], "teeth": 0, "zero_fee": 0},
        )
        g["n"] += 1
        g["orders"].add(parsed.venue_order_id or f"fill:{parsed.kalshi_fill_id}")
        if rec.is_mismatch:
            g["fired"] += 1
        d = rec.undercharge_dollars
        g["worst"] = d if g["worst"] is None else max(g["worst"], d)
        # A ZERO charge is its own bucket, not a headroom of zero.
        #
        # The first version of this divided by `actual` and fell back to 0.0
        # when actual was 0 -- which classified a zero-fee fill as "predicted
        # equals charged", i.e. as one of the informative rows. It is the
        # opposite: nothing can be charged less than zero, so a zero-fee row
        # can never make `actual > predicted` true and carries UNBOUNDED
        # headroom. Counting it as informative inflates the denominator in the
        # flattering direction, which is the error this whole partition exists
        # to avoid. It also poisons the group means: `KXEARNINGSMENTIONKLAR`
        # showed implied k = 0.035017, which read as a second k = 0.035 series
        # and is really one fill at k = 0.070034 averaged with a zero.
        if not rec.actual_dollars:
            g["zero_fee"] += 1
            continue
        headroom = (rec.predicted_dollars - rec.actual_dollars) / rec.actual_dollars
        g["headroom"].append(headroom)
        if headroom <= NEGLIGIBLE_HEADROOM:
            g["teeth"] += 1
        # Ratio, not dollars: the fee scales with C*P*(1-P), so an absolute gap
        # is not comparable across rows of different size.
        if rec.predicted_dollars:
            g["ratios"].append(rec.actual_dollars / rec.predicted_dollars)
        p = parsed.price_tenths / 1000.0
        denom = parsed.count * p * (1.0 - p)
        if denom > 0 and parsed.fee_actual is not None:
            g["k"].append(parsed.fee_actual / denom)

    priced = sum(g["n"] for g in groups.values())
    fired = sum(g["fired"] for g in groups.values())
    teeth = sum(g["teeth"] for g in groups.values())
    zero_fee = sum(g["zero_fee"] for g in groups.values())

    print(f"reconciled {priced}   refused {len(refused)}   WOULD ALERT {fired}")
    print(f"  {zero_fee} were charged NOTHING -- unbounded headroom, they can "
          f"never alert.")
    print(f"  {priced - teeth - zero_fee} carry headroom above "
          f"{NEGLIGIBLE_HEADROOM:.1%} and cannot fire without a schedule move "
          f"at least that large.")
    print(f"  THE INFORMATIVE DENOMINATOR IS {teeth} -- the rows where "
          f"predicted == charged and the test has teeth.\n")

    hdr = (f"  {'prefix':22s} {'n':>4} {'ords':>5} {'$0':>3} {'teeth':>5} "
           f"{'alert':>5} {'worst$':>10} {'ratio':>8} {'implied k':>10}  headroom")
    print(hdr)
    for prefix, g in sorted(groups.items(), key=lambda kv: -kv[1]["n"]):
        ratio = sum(g["ratios"]) / len(g["ratios"]) if g["ratios"] else float("nan")
        kk = sum(g["k"]) / len(g["k"]) if g["k"] else float("nan")
        hr = sum(g["headroom"]) / len(g["headroom"]) if g["headroom"] else 0.0
        note = (
            "zero -- the test has teeth here"
            if hr <= NEGLIGIBLE_HEADROOM
            else ("MATERIAL" if hr >= MATERIAL_HEADROOM else "small")
        )
        print(
            f"  {prefix:22s} {g['n']:4d} {len(g['orders']):5d} "
            f"{g['zero_fee']:3d} {g['teeth']:5d} "
            f"{g['fired']:5d} {g['worst']:+10.6f} {ratio:8.4f} {kk:10.6f}  "
            f"{hr:+7.1%} {note}"
        )

    if refused:
        seen: dict[str, list[str]] = {}
        for ticker, why in refused:
            seen.setdefault(str(why), []).append(ticker)
        print(f"\nrefused ({len(refused)}):")
        for why, tickers in seen.items():
            print(f"  [{len(tickers)}] {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
