"""The parlay census, per its registration. One look, on a pulled copy.

Registered at `docs/measurements/2026-09-05-parlay-census-registration.md`,
Amendment 1. **This file transcribes that document; it decides nothing.** Every
predicate, edge, threshold and verdict boundary below is fixed there, and a
change to any of them is an amendment made in the registration, dated, before
the next read.

**One verdict-bearing test exists: H1, Arm D — were the combination positions
entered as taker?** Everything else printed here is descriptive and may never
be promoted to a verdict without a new registration. Arm D is printed FIRST, so
no money figure is on screen when the verdict-bearing cell is read.

**It reads a pulled, read-only COPY, never the live box.** Running SQL on the
box would contend with the loop's writer, which this repo has an ADR and two
measurements about. Pull with:

    flyctl ssh sftp get /data/kalshi.db  <local>.db   -a kalshi-cockpit

and the `-wal` / `-shm` beside it if they exist. The copy is opened
`file:<path>?mode=ro` and never `immutable=1`: an immutable open ignores WAL
state and would silently read a stale page set.

**Stdlib only, and that is structural rather than stylistic.** Importing
nothing from `backend` makes the registration's *"`lookup_combo` is never
called, for any ticker, for any reason"* true by construction — no client is
built and no write path exists in this process. Same argument ADR 0078 makes
for `core/hedge.py`.

**The torn-snapshot precondition is a refusal, not a warning.** In-window row
counts are recomputed here and compared against counts read on the box at
capture time and passed in with `--box-counts`. The window is closed in the
past and cannot grow, so they must match exactly; a mismatch REFUSES the
measurement and writes the refusal to the result file. A refusal is a record.

What this cannot establish is in §12 of the registration and is not repeated
here. The one line worth carrying: `n_eff` for any outcome statistic is
unknown, bounded [1, 52], because the leg-sharing graph is not computable.

Usage:

    .venv\\Scripts\\python.exe scripts/measure_parlay_census.py <copy.db> \\
        --box-counts fills=NN,settlements=NN,lookups=NN \\
        --out docs/measurements/data/2026-09-05-parlay-census.json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

# --- Fixed by the registration. Do not edit here; amend the registration. ----

#: §4.1. Closed before the analyzer existed.
W_START = 1787011200000        # 2026-08-18T00:00:00Z
W_END = 1788566400000          # 2026-09-05T00:00:00Z, exclusive

#: §8. The null, and the two-sided level.
H1_NULL = 0.5
H1_ALPHA = 0.05

#: §8, downgrade 1. Above this share of unreadable taker status the arm is
#: REFUSED — unreadable resolves to unmeasurable, never to maker.
MAX_UNREADABLE_SHARE = 0.20

#: §8, downgrade 2.
MAX_CLUSTER_SHARE = 0.25
MIN_G_EFF = 10.0

#: §6. Bucket edges on the price actually paid, in tenths of a cent.
BUCKET_EDGES = (20, 50, 150, 400, 999)


# --- §4.2, transcribed -------------------------------------------------------

SQL_POSITIONS = """
SELECT f.ticker              AS ticker,
       COUNT(*)              AS n_fills_observed,
       MIN(f.filled_ms)      AS first_fill_ms,
       MAX(f.filled_ms)      AS last_fill_ms,
       MAX(f.is_taker)       AS any_fill_taker,
       MIN(f.is_taker)       AS all_fills_taker,
       SUM(f.count)          AS contracts_filled,
       SUM(f.count * f.price_tenths) AS cost_tenths_from_fills,
       GROUP_CONCAT(DISTINCT f.source)   AS sources,
       SUM(f.venue_order_id IS NOT NULL) AS n_fills_with_venue_order,
       SUM(f.is_taker IS NULL)           AS n_fills_taker_null
FROM fills f
WHERE f.ticker LIKE 'KXMVE%'
  AND f.filled_ms >= ?
  AND f.filled_ms <  ?
GROUP BY f.ticker
"""

SQL_SETTLEMENT = """
SELECT market_result, settled_ms, side, contracts, entry_price_tenths,
       fee_cost_tenths, n_fills_in_position, event_ticker,
       is_taker AS settlement_is_taker, position_time_source,
       estimate_match_status
FROM venue_settlements WHERE ticker = ?
"""


def iso(ms):
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat()


# --- Exact binomial, stdlib only ---------------------------------------------

def _log_comb(n: int, k: int) -> float:
    import math

    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def binom_two_sided_p(k: int, n: int, p: float = H1_NULL) -> float:
    """Exact two-sided binomial p-value, by the method-of-small-p-values."""
    import math

    if n == 0:
        return 1.0
    probs = [math.exp(_log_comb(n, i) + i * math.log(p) + (n - i) * math.log(1 - p))
             for i in range(n + 1)]
    observed = probs[k]
    tol = observed * (1 + 1e-9)
    return min(1.0, sum(q for q in probs if q <= tol))


def clopper_pearson(k: int, n: int, alpha: float = H1_ALPHA):
    """Exact interval, by bisection on the binomial tail. No scipy."""
    import math

    if n == 0:
        return (0.0, 1.0)

    def tail_le(p, kk):            # P(X <= kk | p)
        if p <= 0:
            return 1.0
        if p >= 1:
            return 0.0 if kk < n else 1.0
        return sum(math.exp(_log_comb(n, i) + i * math.log(p)
                            + (n - i) * math.log(1 - p))
                   for i in range(kk + 1))

    def bisect(f, target):
        lo, hi = 0.0, 1.0
        for _ in range(200):
            mid = (lo + hi) / 2
            if f(mid) > target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    lower = 0.0 if k == 0 else bisect(lambda p: tail_le(p, k - 1), 1 - alpha / 2)
    upper = 1.0 if k == n else bisect(lambda p: tail_le(p, k), alpha / 2)
    return (lower, upper)


def critical_values(n: int):
    """The largest `k` whose interval lies wholly below 0.5, and the smallest
    wholly above. Recomputed by the instrument, never by hand (§8)."""
    upheld = None
    for k in range(n + 1):
        if clopper_pearson(k, n)[1] < H1_NULL:
            upheld = k
    refuted = None
    for k in range(n, -1, -1):
        if clopper_pearson(k, n)[0] > H1_NULL:
            refuted = k
    return upheld, refuted


def g_eff(counts) -> float:
    """Kish effective cluster count, weighted by position count (§8)."""
    total = sum(counts)
    if total == 0:
        return 0.0
    return (total ** 2) / sum(c * c for c in counts)


def arm_d(rows):
    """H1. The only verdict-bearing cell in this measurement."""
    readable, unreadable = [], []
    for r in rows:
        # §5.2: an incomplete fill record cannot carry taker status.
        partial = (
            r["n_fills_in_position"] is not None
            and r["n_fills_in_position"] != r["n_fills_observed"]
        )
        # §5.3: any disagreement with the settlement drops the position.
        disagrees = (
            r["settlement_is_taker"] is not None
            and r["any_fill_taker"] is not None
            and int(r["settlement_is_taker"]) != int(r["any_fill_taker"])
        )
        null_taker = r["any_fill_taker"] is None or r["n_fills_taker_null"]
        if partial or disagrees or null_taker:
            unreadable.append({
                "ticker": r["ticker"],
                "fill_record_partial": bool(partial),
                "settlement_disagrees": bool(disagrees),
                "taker_null": bool(null_taker),
            })
        else:
            readable.append(r)

    n = len(readable)
    k = sum(1 for r in readable if int(r["any_fill_taker"]) == 1)
    k_strict = sum(1 for r in readable if int(r["all_fills_taker"]) == 1)
    share_unreadable = (
        len(unreadable) / (n + len(unreadable)) if (n + len(unreadable)) else 0.0
    )

    by_day = defaultdict(list)
    for r in readable:
        by_day[iso(r["first_fill_ms"])[:10]].append(r)
    sizes = [len(v) for v in by_day.values()]

    out = {
        "n": n,
        "k_any_fill_taker": k,
        "k_all_fills_taker": k_strict,
        "unreadable_count": len(unreadable),
        "unreadable_share": round(share_unreadable, 4),
        "unreadable_detail": unreadable,
        "p_taker": (k / n) if n else None,
        "exact_interval": clopper_pearson(k, n) if n else None,
        "p_value_two_sided": binom_two_sided_p(k, n) if n else None,
        "critical_values": critical_values(n) if n else None,
        "c_day_clusters": {d: len(v) for d, v in sorted(by_day.items())},
        "largest_cluster_share": (max(sizes) / n) if n and sizes else None,
        "g_eff": round(g_eff(sizes), 3) if sizes else None,
        # **Not the registered tool-placed flag.** This counts a non-null
        # `venue_order_id`, which the venue sets on Joe's app-placed orders
        # too; the registered flag (Amendment 1, Correction 2) is the join to
        # `combo_orders.kalshi_order_id`. Kept under an honest name because it
        # is still worth printing, and renamed because the first run's result
        # file had to disclose that a reader would take it for the flag.
        "positions_with_any_venue_order_id": sum(
            1 for r in readable if r["n_fills_with_venue_order"]
        ),
        "source_split": dict(Counter(
            (r["sources"] or "?") for r in readable
        )),
    }

    # §8: coverage first, and it refuses rather than downgrades.
    if share_unreadable > MAX_UNREADABLE_SHARE:
        out["verdict"] = "REFUSED - COVERAGE"
        return out

    # **A `key` separate from the sentence.** The first version of this
    # compared `verdict.split()[-1]`, which is "POPULATION" for the refute
    # string and therefore never equalled "REFUTED" -- so both downgrades below
    # fired on every refuting result and printed UNRESOLVED over it. Found on
    # the first run, by Rule 1's own instruction to check the instrument before
    # believing a large contradiction. A verdict compared by parsing its own
    # prose is a verdict that changes when the prose does.
    def _classify(kk: int, nn: int) -> str:
        up, ref = critical_values(nn)
        if up is not None and kk <= up:
            return "UPHELD"
        if ref is not None and kk >= ref:
            return "REFUTED"
        return "UNRESOLVED"

    key = _classify(k, n)
    verdict = {
        "UPHELD": "ADR 0085 UPHELD",
        "REFUTED": "ADR 0085 REFUTED ON THIS POPULATION",
        "UNRESOLVED": "UNRESOLVED",
    }[key]

    # Downgrade 2, then 3. Each can only weaken.
    concentrated = (
        (out["largest_cluster_share"] or 0) >= MAX_CLUSTER_SHARE
        or (out["g_eff"] or 0) < MIN_G_EFF
    )
    loo_crosses = False
    loo_detail = {}
    for day, members in by_day.items():
        kept = [r for r in readable if r not in members]
        if not kept:
            continue
        kk = sum(1 for r in kept if int(r["any_fill_taker"]) == 1)
        v = _classify(kk, len(kept))
        loo_detail[day] = {"n": len(kept), "k": kk, "verdict": v}
        if key != "UNRESOLVED" and v != key:
            loo_crosses = True
    out["leave_one_day_out"] = loo_detail
    out["leave_one_day_out_crosses"] = loo_crosses
    out["concentrated"] = concentrated
    if key != "UNRESOLVED" and (concentrated or loo_crosses):
        verdict = "UNRESOLVED - CONCENTRATION"
    # §5.3: the two definitions must agree on which side they land.
    if key != "UNRESOLVED" and n:
        strict_v = _classify(k_strict, n)
        out["strict_definition_verdict"] = strict_v
        if strict_v != key:
            verdict = "UNRESOLVED"
            out["mixed_definition_disagreement"] = True
    out["verdict"] = verdict
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("db", help="path to the PULLED read-only copy")
    ap.add_argument("--box-counts", default="",
                    help="fills=NN,settlements=NN,lookups=NN read on the box")
    ap.add_argument("--pulled-files", default="",
                    help="comma-separated names actually pulled (db, wal, shm)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    conn = sqlite3.connect(f"file:{Path(args.db).as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    positions = [dict(r) for r in conn.execute(SQL_POSITIONS, (W_START, W_END))]
    for p in positions:
        s = conn.execute(SQL_SETTLEMENT, (p["ticker"],)).fetchone()
        p.update(dict(s) if s else {
            k: None for k in (
                "market_result", "settled_ms", "side", "contracts",
                "entry_price_tenths", "fee_cost_tenths", "n_fills_in_position",
                "event_ticker", "settlement_is_taker", "position_time_source",
                "estimate_match_status")
        })
    positions.sort(key=lambda r: r["first_fill_ms"])

    counts = {
        "fills": conn.execute(
            "SELECT COUNT(*) FROM fills WHERE ticker LIKE 'KXMVE%' "
            "AND filled_ms >= ? AND filled_ms < ?", (W_START, W_END)
        ).fetchone()[0],
        "settlements": len([p for p in positions if p["settled_ms"] is not None]),
        "lookups": conn.execute(
            "SELECT COUNT(*) FROM parlay_lookups WHERE requested_ms >= ? "
            "AND requested_ms < ?", (W_START, W_END)
        ).fetchone()[0],
    }

    declared = {}
    for pair in filter(None, args.box_counts.split(",")):
        key, _, val = pair.partition("=")
        declared[key.strip()] = int(val)
    mismatches = {k: {"copy": v, "box": declared[k]}
                  for k, v in counts.items()
                  if k in declared and declared[k] != v}

    result = {
        "registration": "docs/measurements/2026-09-05-parlay-census-registration.md",
        "amendment": 1,
        "read_utc": datetime.now(timezone.utc).isoformat(),
        "window": {"start_ms": W_START, "end_ms": W_END,
                   "start": iso(W_START), "end": iso(W_END)},
        "pulled_files": [f for f in args.pulled_files.split(",") if f],
        "copy_counts": counts,
        "box_counts": declared,
        "torn_snapshot_mismatches": mismatches,
    }

    if mismatches:
        result["verdict"] = "REFUSED - TORN SNAPSHOT"
        result["arm_d"] = None
        print("REFUSED - TORN SNAPSHOT", json.dumps(mismatches, indent=2))
    else:
        # Arm D FIRST, before any money figure reaches the screen (§11.2).
        d = arm_d(positions)
        result["arm_d"] = d
        print("=" * 70)
        print("ARM D (H1) - the only verdict-bearing cell")
        print("=" * 70)
        for key in ("n", "k_any_fill_taker", "k_all_fills_taker",
                    "unreadable_count", "unreadable_share", "p_taker",
                    "exact_interval", "critical_values", "largest_cluster_share",
                    "g_eff", "concentrated", "leave_one_day_out_crosses"):
            print(f"  {key:26s} {d.get(key)}")
        print(f"\n  VERDICT: {d['verdict']}\n")

    result["positions"] = positions
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, default=str) + "\n",
                   encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
