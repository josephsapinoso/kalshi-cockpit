"""The registered census: does the recorded hand-bet price equal the venue's?

    flyctl ssh console -a kalshi-cockpit \\
      -C "python /app/scripts/census_recorded_fill_vs_venue.py --db /data/cockpit.db"

Registration: `docs/measurements/2026-09-10-preregistration-recorded-fill-vs-
venue-charge.md` and its Amendment 1 (2026-09-11). **This is the one look
§9 / §A8 allow**, taken at the first session after the population reached
ten real manual orders. Running it again is a new look and needs a dated
amendment recording that this one was seen. It opens the database read-only
and writes nothing.

WHAT IT PRINTS, AND ONLY THAT
-----------------------------
The registration's §6.1 / §A5 column list is exhaustive and this script adds
nothing to it: `submitted_ms`, `ticker`, stratum, `side`, `count`,
`sent_tenths`, `venue_tenths`, `sent_minus_venue_tenths` (signed),
`multi_fill`, `venue_source`, plus the two endpoints side by side where a row
carries both (A7.4) and the side-convention classification (A4.3). Counts per
stratum: `n_joined`, `unjoined_zero_fill`, `unjoined_unknown`, `n_equal`,
`n_sent_above`, `n_sent_below`, `max_abs_sent_minus_venue_tenths`,
`sum_abs_sent_minus_venue_tenths`, `n_multi_fill`, the `venue_source`
counts, and the snapshot instant beside every one of them.

**No mean, no proportion, no sd, no interval, no p-value, at any n, ever.**
`sum / n` is a mean and is not printed; `n_equal / n_joined` is a rate and is
not printed. The per-row table is ordered by `submitted_ms` ascending and by
nothing else. No top-N, no "worst fill", no maximum-row callout.

**Forbidden and not read:** `p_yes_bp`, `venue_avg_fee_dollars` (A5 -- the
fee question was measured on 2026-09-09 and reading the column here would
reopen it), `venue_settlements`, `settlements`, `closing_lines`, `clv_*`,
realised P&L, any win/loss marker. `tests/test_census_recorded_fill_vs_venue.py`
asserts that over the SQL text.

THE POPULATION (§3 as amended by A4.1)
--------------------------------------
    manual_orders rows where dry_run = 0 AND kalshi_order_id IS NOT NULL
    joined to fills on fills.venue_order_id = manual_orders.kalshi_order_id,
    OR carrying venue_avg_fill_price_tenths (post-v40 create response)

`V`, the venue price (A4.2): the count-weighted mean of `fills.price_tenths`
over the order's fills is PRIMARY (`venue_source = fills`); the create
response's `venue_avg_fill_price_tenths` is the FALLBACK, used only when the
join returns nothing (`venue_source = create_response`). Rows on the fallback
are flagged and counted separately and never enter the H1 counts.
`unjoined_zero_fill` is a post-v40 row whose `venue_fill_count` is 0.0 -- the
IOC matched no one, not a coverage gap. `unjoined_unknown` is every other row
with no venue price. **The refusal branch (A4.4): if `unjoined_unknown >
n_joined`, the join measures poller coverage, not the recorder; this script
then prints the coverage counts and computes NO comparison at all.**

The `fills` read is bounded to the population's order ids (`IN (...)`), never
a scan of the history; `fills` holds only the mirror's hand fills and is
small, and this is the registration's live-read constraint honoured.

The side-convention artifact (A4.3): a row where `V` is within 10 tenths of
`1000 - sent` and more than 10 from `sent` is `side_convention_ambiguous` and
is NOT counted as H1 falsified; a row where both readings are within 10
tenths (near 50c) is `side_convention_undecidable`. Everything else is
`comparable`, and only comparable rows enter `n_equal` / `n_sent_above` /
`n_sent_below`.

WHAT THIS DOES NOT ESTABLISH (§11, as corrected by A9)
------------------------------------------------------
- **Nothing about whether the bets were good.** The 2026-08-29 registration's
  §6f cut execution quality as a metric about Joe; this is a property of the
  code, printed as a census of the recorder.
- **Nothing at any n this population will reach that is an estimate.** It is
  a census: every row, no summary statistic, no rate of anything.
- **Nothing about the hedge lock's correctness or the direction it errs in.**
  The census pins E2 and only E2 of the at-least-four error terms in A6; it
  says nothing about E1 (settlement charge, H4 untested), E3 (entry fee) or
  E4 (the flat 0.070 hedge fee).
- **Nothing about fees.** The column exists on the row and is not read.
- **Nothing about which of the two venue-price sources is correct**, except
  in the one branch A7.4 opens; `fills` is primary by a documented side
  convention, not by having been shown right.
- **Nothing about the side convention of `average_fill_price` for a
  `side = 'no'` order.** A4.3 classifies the artifact; it does not resolve it.
- **Nothing for or against ADR 0143** (A7.2): the persistence arm was decided
  on retention before this look, in either direction.
- **Nothing that authorises a change to money-touching code** (§8.4, §11.9).
- **Nothing about the contract-count factor** of the stake (A9 §13).
- **`sent_tenths` is `limit_price_tenths`**, the ask the desk SENT (A1.1),
  written at intent time -- not a fill report. That is the whole reason the
  comparison exists.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inspect_live_db_common import Section, _iso, render_text  # noqa: E402

#: Population shell: X1 (`dry_run = 0`) and X2 (`kalshi_order_id IS NOT NULL`).
#: Ordered by `submitted_ms` ascending and by nothing else (§6.1). No
#: `p_yes_bp`, no `venue_avg_fee_dollars`.
SQL_POPULATION = (
    "SELECT id, submitted_ms, ticker, side, count, limit_price_tenths, "
    "kalshi_order_id, venue_fill_count, venue_avg_fill_price_tenths "
    "FROM manual_orders "
    "WHERE dry_run = 0 AND kalshi_order_id IS NOT NULL "
    "ORDER BY submitted_ms ASC, id ASC"
)

#: The venue side, bounded to the population's order ids. `price_tenths` is
#: already OUR side's price -- `portfolio_poll.parse_fill` reads
#: `yes_price`/`no_price` by the fill's own side (A4.2).
SQL_FILLS_FOR = (
    "SELECT venue_order_id, COUNT(*) AS n_fills, SUM(count) AS qty, "
    "SUM(count * price_tenths) AS qty_price "
    "FROM fills WHERE venue_order_id IN ({placeholders}) "
    "GROUP BY venue_order_id"
)

SIDE_TOLERANCE_TENTHS = 10  # A4.3, fixed at registration
ENDPOINT_TOLERANCE_TENTHS = 1  # A7.4, the declared half-up rounding


def stratum(ticker: str) -> str:
    return "S1" if ticker.startswith("KXMVE") else "S2"


def classify(sent: int, venue: float) -> str:
    """A4.3. `comparable` is the only class that enters the H1 counts."""
    near = abs(venue - sent) <= SIDE_TOLERANCE_TENTHS
    flipped = abs(venue - (1000 - sent)) <= SIDE_TOLERANCE_TENTHS
    if flipped and not near:
        return "side_convention_ambiguous"
    if flipped and near:
        return "side_convention_undecidable"
    return "comparable"


def read_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    population = [dict(r) for r in conn.execute(SQL_POPULATION)]
    if not population:
        return []
    ids = [r["kalshi_order_id"] for r in population]
    placeholders = ",".join("?" * len(ids))
    fills = {
        r["venue_order_id"]: dict(r)
        for r in conn.execute(SQL_FILLS_FOR.format(placeholders=placeholders), ids)
    }
    rows: list[dict[str, Any]] = []
    for r in population:
        f = fills.get(r["kalshi_order_id"])
        fills_venue: Optional[float] = None
        n_fills = 0
        if f is not None and f["qty"]:
            fills_venue = f["qty_price"] / f["qty"]
            n_fills = int(f["n_fills"])
        create_venue = r["venue_avg_fill_price_tenths"]
        fill_count = r["venue_fill_count"]
        if fills_venue is not None:
            source, venue = "fills", fills_venue
        elif create_venue is not None:
            source, venue = "create_response", float(create_venue)
        elif fill_count is not None and float(fill_count) == 0.0:
            source, venue = "zero_fill", None
        else:
            source, venue = "unknown", None
        sent = r["limit_price_tenths"]
        diff = None if (venue is None or sent is None) else sent - venue
        klass = None
        if venue is not None and sent is not None:
            klass = classify(int(sent), venue)
        endpoints = None
        if fills_venue is not None and create_venue is not None:
            endpoints = int(abs(fills_venue - float(create_venue)) > ENDPOINT_TOLERANCE_TENTHS)
        rows.append({
            "submitted_ms": r["submitted_ms"],
            "ticker": r["ticker"],
            "stratum": stratum(r["ticker"]),
            "side": r["side"],
            "count": r["count"],
            "sent_tenths": sent,
            "venue_tenths": None if venue is None else round(venue, 1),
            "sent_minus_venue_tenths": None if diff is None else round(diff, 1),
            "multi_fill": int(n_fills > 1),
            "venue_source": source,
            "fills_venue_tenths": None if fills_venue is None else round(fills_venue, 1),
            "create_venue_tenths": create_venue,
            "endpoints_disagree": endpoints,
            "classification": klass,
        })
    return rows


ROW_COLUMNS = (
    "submitted_ms", "submitted_iso", "ticker", "stratum", "side", "count",
    "sent_tenths", "venue_tenths", "sent_minus_venue_tenths", "multi_fill",
    "venue_source", "fills_venue_tenths", "create_venue_tenths",
    "endpoints_disagree", "classification",
)

COUNT_COLUMNS = (
    "stratum", "snapshot_iso", "n_rows", "n_joined", "unjoined_zero_fill",
    "unjoined_unknown", "n_source_fills", "n_source_create_response",
    "n_multi_fill", "n_both_endpoints", "n_endpoints_disagree",
    "n_side_convention_ambiguous", "n_side_convention_undecidable",
    "n_comparable", "n_equal", "n_sent_above", "n_sent_below",
    "max_abs_sent_minus_venue_tenths", "sum_abs_sent_minus_venue_tenths",
)


def counts_for(rows: list[dict[str, Any]], label: str, snapshot_ms: int) -> tuple:
    joined = [r for r in rows if r["venue_source"] in ("fills", "create_response")]
    # H1 is adjudicated on `fills` only (A4.2); fallback rows never enter it.
    comparable = [
        r for r in joined
        if r["venue_source"] == "fills" and r["classification"] == "comparable"
        and r["sent_minus_venue_tenths"] is not None
    ]
    diffs = [r["sent_minus_venue_tenths"] for r in comparable]
    both = [r for r in rows if r["endpoints_disagree"] is not None]
    return (
        label,
        _iso(snapshot_ms),
        len(rows),
        len(joined),
        sum(1 for r in rows if r["venue_source"] == "zero_fill"),
        sum(1 for r in rows if r["venue_source"] == "unknown"),
        sum(1 for r in rows if r["venue_source"] == "fills"),
        sum(1 for r in rows if r["venue_source"] == "create_response"),
        sum(r["multi_fill"] for r in rows),
        len(both),
        sum(r["endpoints_disagree"] for r in both),
        sum(1 for r in joined if r["classification"] == "side_convention_ambiguous"),
        sum(1 for r in joined if r["classification"] == "side_convention_undecidable"),
        len(comparable),
        sum(1 for d in diffs if d == 0),
        sum(1 for d in diffs if d > 0),
        sum(1 for d in diffs if d < 0),
        max((abs(d) for d in diffs), default=None),
        round(sum(abs(d) for d in diffs), 1) if diffs else None,
    )


def refusal_fires(rows: list[dict[str, Any]]) -> bool:
    """A4.4: `unjoined_unknown > n_joined` -- coverage, not the recorder."""
    unknown = sum(1 for r in rows if r["venue_source"] == "unknown")
    joined = sum(1 for r in rows if r["venue_source"] in ("fills", "create_response"))
    return unknown > joined


def sections(rows: list[dict[str, Any]], snapshot_ms: int) -> list[Section]:
    out: list[Section] = []
    out.append(Section(
        title=(
            "A. the population at the snapshot instant: manual_orders with "
            "dry_run = 0 and a kalshi_order_id (X1, X2). One look (A8)."
        ),
        columns=("snapshot_ms", "snapshot_iso", "n_real_orders", "trigger_met_at_10"),
        rows=[(snapshot_ms, _iso(snapshot_ms), len(rows), int(len(rows) >= 10))],
    ))
    per_ticker: dict[str, list[int]] = {}
    for r in rows:
        per_ticker.setdefault(r["ticker"], []).append(r["submitted_ms"])
    out.append(Section(
        title=(
            "B. orders per ticker, in order of first submission (never by "
            "count) -- a population that is one ticker repeated is visible here"
        ),
        columns=("ticker", "stratum", "n_orders", "first_submitted_iso"),
        rows=[
            (t, stratum(t), len(ms), _iso(min(ms)))
            for t, ms in sorted(per_ticker.items(), key=lambda kv: min(kv[1]))
        ],
    ))
    refused = refusal_fires(rows)
    coverage_title = (
        "C. counts per stratum and pooled, beside the snapshot instant. "
        "S1 = KXMVE combinations: on a one-level book an IOC at that level "
        "cannot improve, so sent == venue there is a statement about depth, "
        "not about the recorder (A5). No mean, no rate, ever."
    )
    if refused:
        coverage_title = (
            "C. REFUSAL BRANCH (A4.4): unjoined_unknown > n_joined, so the join "
            "measures poller coverage, not the recorder. Coverage counts only; "
            "NO comparison is computed."
        )
    count_rows = [
        counts_for([r for r in rows if r["stratum"] == "S1"], "S1 (KXMVE)", snapshot_ms),
        counts_for([r for r in rows if r["stratum"] == "S2"], "S2 (single markets)", snapshot_ms),
        counts_for(rows, "pooled", snapshot_ms),
    ]
    if refused:
        keep = COUNT_COLUMNS.index("n_source_create_response") + 1
        out.append(Section(
            title=coverage_title,
            columns=COUNT_COLUMNS[:keep],
            rows=[row[:keep] for row in count_rows],
        ))
        return out
    out.append(Section(title=coverage_title, columns=COUNT_COLUMNS, rows=count_rows))
    out.append(Section(
        title=(
            "D. every row, ordered by submitted_ms ascending and by nothing "
            "else. sent_tenths is the ask the desk SENT (limit_price_tenths); "
            "venue_tenths is V per A4.2; the two endpoints sit side by side "
            "where a row carries both (A7.4)."
        ),
        columns=ROW_COLUMNS,
        rows=[
            tuple(
                _iso(r["submitted_ms"]) if c == "submitted_iso" else r[c]
                for c in ROW_COLUMNS
            )
            for r in rows
        ],
    ))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/cockpit.db")
    args = ap.parse_args()
    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        snapshot_ms = int(time.time() * 1000)
        rows = read_rows(conn)
    finally:
        conn.close()
    print(render_text("recorded-fill-vs-venue-census", args.db, sections(rows, snapshot_ms)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
