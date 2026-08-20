"""H4 Look 1: the registered subtraction, computed exactly as pre-registered.

Consumes one `h4-settlement-balance` JSON pull (`inspect_live_db.py`) and
applies `docs/measurements/2026-08-20-preregistration-h4-settlement-fee.md`
verbatim: cluster at 1800s gaps, endpoints nearest-either-side within 900s,
exclusions E1-E6 counted, residual `r_c = D_c - P_c` in integer tenths,
`tau_c = 1 + n_win_c`, classification in the registration's fixed order,
aggregate verdict per its section 6.

Written BEFORE the Look 1 data was pulled (the registration's 30-minute
gap), so the analysis code cannot have been shaped by the numbers.

What this does not establish
----------------------------
- Everything in the registration's section 9: no zero, no p-value, no claim
  below the printed upper bound `U`, nothing about a fee of the venue's own
  `k*C*P*(1-P)` shape (identically $0 at settlement), and no separation of
  a settlement charge from a deferred entry-fee debit (C7).
- One interpretation the registration leaves implicit is made explicit
  here and applied conservatively: E1 (a void or unchased `market_result`)
  is registered per settlement, but a void row's cash effect still lands in
  its cluster's balance step, so a cluster containing any E1 row has an
  undefined `P_c` and is excluded WHOLE, counted under E1. The result file
  must state this.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# The registration's constants, restated from the file, not tunable.
GAP_MS = 1_800_000          # cluster cut: consecutive settled_ms gap > 1800s
HALF_MS = 900_000           # endpoint search half-window
BANKING_DOLLARS_PER_CONTRACT = 0.05   # section 6.1
DECIDING_SCALE_DOLLARS = 0.0063       # ADR 0027's headroom, section 6
# This file's registration was committed 2026-08-20T23:13:27Z (`4e0a025`).
REGISTRATION_COMMIT_MS = 1_787_267_607_000
# Study start, hard-coded to match `inspect_live_db.py`'s _H4_STUDY_START_MS.
# E5's boundary check: a cluster interval reaching before this instant could
# contain a pre-study settlement the pull does not show.
STUDY_START_MS = 1_787_044_503_594


def sections_by_letter(payload: dict) -> dict:
    out = {}
    for section in payload["sections"]:
        letter = section["title"].split(".", 1)[0].strip()
        rows = [dict(zip(section["columns"], r)) for r in section["rows"]]
        out[letter] = rows
    return out


def clusters_of(settlements: list[dict]) -> list[list[dict]]:
    ordered = sorted(settlements, key=lambda s: s["settled_ms"])
    clusters: list[list[dict]] = []
    for row in ordered:
        if clusters and row["settled_ms"] - clusters[-1][-1]["settled_ms"] <= GAP_MS:
            clusters[-1].append(row)
        else:
            clusters.append([row])
    return clusters


def analyze(payload: dict) -> dict:
    data = sections_by_letter(payload)
    settlements, balance, fills, polls = (
        data.get("A", []), data.get("B", []), data.get("C", []), data.get("D", [])
    )

    exclusions: dict[str, list] = {k: [] for k in ("E1", "E2", "E3", "E4", "E5", "E6")}
    results = []
    for cluster in clusters_of(settlements):
        lo = cluster[0]["settled_ms"]
        hi = cluster[-1]["settled_ms"]
        label = {
            "settlement_ids": [s["id"] for s in cluster],
            "tickers": sorted({s["ticker"] for s in cluster}),
            "min_settled_ms": lo,
            "max_settled_ms": hi,
            "n_settlements": len(cluster),
            "kind": "combo" if any(
                str(s["ticker"]).startswith("KXMVE") for s in cluster
            ) else "single",
            "seen_before_registration": int(hi < REGISTRATION_COMMIT_MS),
        }

        # E1 -- any void/unchased result makes P_c undefined for the whole
        # cluster (see module docstring).
        if any(s["market_result"] not in ("yes", "no") for s in cluster):
            exclusions["E1"].append(label)
            continue

        # Endpoints, nearest-either-side within 900s (registration section 3).
        pre = [b for b in balance
               if lo - HALF_MS <= b["observed_ms"] < lo]
        post = [b for b in balance
                if hi < b["observed_ms"] <= hi + HALF_MS]
        if not pre or not post:
            exclusions["E4"].append({**label, "why": "missing endpoint snapshot"})
            continue
        b_pre = max(pre, key=lambda b: b["observed_ms"])
        b_post = min(post, key=lambda b: b["observed_ms"])
        if b_pre["balance_tenths"] is None or b_post["balance_tenths"] is None:
            exclusions["E4"].append({**label, "why": "NULL balance_tenths"})
            continue

        interval = (b_pre["observed_ms"], b_post["observed_ms"])

        # E2 -- a fill inside the balance interval.
        confound_fills = [f for f in fills
                          if interval[0] <= f["filled_ms"] <= interval[1]]
        if confound_fills:
            exclusions["E2"].append({**label, "fill_ids": [f["id"] for f in confound_fills]})
            continue

        # E3 -- a failed balance poll inside the cluster's query window.
        bad_polls = [p for p in polls
                     if lo - HALF_MS <= p["polled_ms"] <= hi + HALF_MS
                     and not p["ok"]]
        if bad_polls:
            exclusions["E3"].append({**label, "bad_polls": len(bad_polls)})
            continue

        # E5 -- another settlement (not in the cluster) inside the interval.
        # Post-study rows are all in section A; pre-study rows cannot reach
        # the interval unless it starts before study start, checked here.
        intruders = [s for s in settlements
                     if s["id"] not in label["settlement_ids"]
                     and interval[0] <= s["settled_ms"] <= interval[1]]
        if intruders or interval[0] < STUDY_START_MS:
            exclusions["E5"].append({**label, "intruder_ids": [s["id"] for s in intruders]})
            continue

        # E6 -- latency guard: the balance must have stopped moving by the
        # window edge (B_post equals the LAST in-window snapshot's balance).
        in_post_window = [b for b in balance
                          if hi < b["observed_ms"] <= hi + HALF_MS
                          and b["balance_tenths"] is not None]
        last_in_window = max(in_post_window, key=lambda b: b["observed_ms"])
        if last_in_window["balance_tenths"] != b_post["balance_tenths"]:
            exclusions["E6"].append(label)
            continue

        wins = [s for s in cluster if s["side"] == s["market_result"]]
        p_c = sum(round(1000 * float(s["contracts"])) for s in wins)
        d_c = b_post["balance_tenths"] - b_pre["balance_tenths"]
        r_c = d_c - p_c
        n_c = sum(round(float(s["contracts"])) for s in cluster)
        tau_c = 1 + len(wins)
        fee_sum = sum(s["fee_cost_tenths"] or 0 for s in cluster)

        # Classification, registration section 6, first match wins.
        if abs(r_c) > 50 * n_c:                      # $0.05 = 50 tenths
            verdict = "BANKING-CONTAMINATED"
        elif p_c > 0 and abs(r_c) >= 0.5 * p_c:
            verdict = "UNDECIDABLE-CREDIT-CHANNEL"
        elif r_c > tau_c:
            verdict = "ANOMALY"
        elif r_c < -tau_c:
            verdict = "CHARGE"
            if abs(r_c + fee_sum) <= tau_c:
                verdict = "CHARGE/AMBIGUOUS-DEFERRED-ENTRY"
        else:
            verdict = "NO-CHARGE-AT-TOLERANCE"

        results.append({
            **label,
            "b_pre": b_pre, "b_post": b_post,
            "P_c_tenths": p_c, "D_c_tenths": d_c, "r_c_tenths": r_c,
            "r_c_dollars": r_c / 1000, "tau_c_tenths": tau_c,
            "n_win": len(wins), "W_contracts": sum(
                round(float(s["contracts"])) for s in wins
            ),
            "N_contracts": n_c, "fee_sum_tenths": fee_sum,
            "classification": verdict,
        })

    return {"eligible_clusters": results, "excluded": exclusions}


def main(argv: list[str]) -> int:
    payload = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    out = analyze(payload)
    print(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
