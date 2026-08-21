"""A17: the channel-only diagnostic, computed exactly as pre-registered.

Consumes one `h4-balance-spans` JSON pull (`inspect_live_db.py`, sections
A-E) and applies Amendment 3 (A17) of
`docs/measurements/2026-08-20-preregistration-h4-settlement-fee.md`
verbatim: winners from section E, exclusions D1-D4 counted with reasons,
spans as adjacent section-B snapshot pairs `(s_j, s_{j+1}]`, A12.2's
arithmetic in integer tenths, HIT-STRICT and HIT-WIDE per A17.4, verdict
per A17.5 (BLIND / CARRIES CREDITS (STRICT|WIDE) / UNTESTED).

Written BEFORE the diagnostic pull was taken (A17.6's 30-minute gap), so
the analysis code cannot have been shaped by the numbers.

What this does not establish
----------------------------
- **Nothing about H4 or the venue.** A17.1: this tests the *instrument* --
  whether the cash-balance channel carries payouts at the resolution this
  study reads it. Both verdicts leave `settlement_fee()` untested, and the
  words "zero", "no settlement fee" and "H4 confirmed" are prohibited in
  any write-up of its output (section 6, carried into A17.5).
- **No standard error, no p-value** (A17.3): the estimand is an existential
  over a finite enumerated record; the denominator is printed to size the
  chance Claim D was given, never used inferentially.
- **The transfer confound is not excluded** (A17.10): a deposit can mimic a
  hit and a withdrawal can mask one. The lead/lag printed on every hit is
  the registered bound, not an exclusion.
- **A refused (truncated) pull is not a look** (A17.6): a pull whose
  sections report `truncated: true` is a technical failure to re-attempt
  with a higher `--limit`, and this module refuses it rather than analysing
  a silently capped record.

One interpretation the registration leaves implicit is made explicit here
and applied conservatively: A17.2's D4 reads failed polls on the CLOSED
interval `[s_j, s_{j+1}]` -- a failed balance poll at exactly an endpoint
instant makes the endpoint suspect, and a successful snapshot and a failed
poll cannot be the same event. The result file must state this.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# A17's constants, restated from the registration, not tunable.
WIDE_NEIGHBOURHOOD_MS = 24 * 3_600_000   # A17.4: +/-24h, one venue day
TAU_WIDE_TENTHS = 2                      # A17.4: tau_i, fixed


class TruncatedPull(RuntimeError):
    """A capped section: the pull is a technical failure, not a look."""


def sections_by_letter(payload: dict) -> dict:
    out = {}
    for section in payload["sections"]:
        letter = section["title"].split(".", 1)[0].strip()
        if section.get("truncated"):
            raise TruncatedPull(
                f"section {letter} is truncated; re-pull with a higher "
                "--limit. A capped record must not be analysed (A17.6: a "
                "technical failure is not a look)."
            )
        rows = [dict(zip(section["columns"], r)) for r in section["rows"]]
        out[letter] = rows
    return out


def payout_tenths(contracts) -> int:
    """A12.2: round(1000 x contracts), $1.00 per winning contract."""
    return round(1000 * contracts)


def analyze(payload: dict) -> dict:
    data = sections_by_letter(payload)
    snapshots = sorted(data.get("B", []), key=lambda b: b["observed_ms"])
    polls = data.get("D", [])
    all_settlements = data.get("E", [])

    # --- spans: adjacent snapshot pairs (s_j, s_j+1], A12.2 --------------
    spans = []
    for j in range(len(snapshots) - 1):
        lo, hi = snapshots[j], snapshots[j + 1]
        spans.append({
            "index": j,
            "lo_ms": lo["observed_ms"],
            "hi_ms": hi["observed_ms"],
            "lo_balance": lo["balance_tenths"],
            "hi_balance": hi["balance_tenths"],
        })

    # --- winners (for P_j) and the eligible population, section E --------
    def is_winner(row) -> bool:
        return (
            row["market_result"] in ("yes", "no")
            and row["side"] == row["market_result"]
        )

    winners = [s for s in all_settlements if is_winner(s)]

    def containing_span(settled_ms: int):
        for span in spans:
            if span["lo_ms"] < settled_ms <= span["hi_ms"]:
                return span
        return None

    # Per-span P_j / n_win_j / tau_j / D_j (A12.2 arithmetic, tenths).
    for span in spans:
        inside = [w for w in winners
                  if span["lo_ms"] < w["settled_ms"] <= span["hi_ms"]]
        contained = [s for s in all_settlements
                     if span["lo_ms"] < s["settled_ms"] <= span["hi_ms"]]
        span["p_j"] = sum(payout_tenths(w["contracts"]) for w in inside)
        span["n_win_j"] = len(inside)
        span["tau_j"] = 1 + span["n_win_j"]
        span["n_settlements"] = len(contained)
        unreadable = (span["lo_balance"] is None
                      or span["hi_balance"] is None)
        span["d_j"] = (None if unreadable
                       else span["hi_balance"] - span["lo_balance"])
        # D4's poll check, closed interval (module docstring).
        span["failed_polls"] = [
            p["polled_ms"] for p in polls
            if p["ok"] == 0 and span["lo_ms"] <= p["polled_ms"] <= span["hi_ms"]
        ]

    coverage_only_pairs = sum(
        1 for span in spans if span["n_settlements"] == 0
    )  # A16: coverage, never observations

    # --- D1-D4 enumeration over section E --------------------------------
    exclusions = {"D1": [], "D2": [], "D3": [], "D4": []}
    ineligible_contracts = []   # winners failing A17.2's contracts > 0 bar
    eligible = []
    for row in all_settlements:
        ident = {"id": row["id"], "ticker": row["ticker"],
                 "settled_ms": row["settled_ms"]}
        if row["market_result"] not in ("yes", "no"):
            exclusions["D1"].append(ident)
            continue
        if row["side"] != row["market_result"]:
            exclusions["D2"].append(ident)
            continue
        if not (row["contracts"] and row["contracts"] > 0):
            ineligible_contracts.append(ident)
            continue
        span = containing_span(row["settled_ms"])
        if span is None:
            exclusions["D3"].append(ident)
            continue
        if span["failed_polls"] or span["d_j"] is None:
            why = ("failed poll in span" if span["failed_polls"]
                   else "NULL balance endpoint")
            exclusions["D4"].append({**ident, "why": why})
            continue
        eligible.append((row, span))

    # --- HIT-STRICT / HIT-WIDE per eligible winner (A17.4) ---------------
    winner_rows = []
    for row, span in eligible:
        p_i = payout_tenths(row["contracts"])
        strict = span["p_j"] > 0 and abs(span["d_j"] - span["p_j"]) <= span["tau_j"]

        wide_hits = []
        scanned = 0
        for k in spans:
            if k["d_j"] is None:
                continue
            near = (abs(k["lo_ms"] - row["settled_ms"]) <= WIDE_NEIGHBOURHOOD_MS
                    and abs(k["hi_ms"] - row["settled_ms"]) <= WIDE_NEIGHBOURHOOD_MS)
            if not near:
                continue
            scanned += 1
            if abs(k["d_j"] - p_i) <= TAU_WIDE_TENTHS:
                wide_hits.append({
                    "span_index": k["index"],
                    "d_k": k["d_j"],
                    # lead/lag, A17.4: where the step sits relative to the
                    # settlement. Negative = the step closed before it.
                    "lead_lag_ms_lo": k["lo_ms"] - row["settled_ms"],
                    "lead_lag_ms_hi": k["hi_ms"] - row["settled_ms"],
                })

        winner_rows.append({
            "id": row["id"],
            "ticker": row["ticker"],
            "settled_ms": row["settled_ms"],
            "contracts": row["contracts"],
            "p_i": p_i,
            "span_index": span["index"],
            "d_j": span["d_j"],
            "p_j": span["p_j"],
            "tau_j": span["tau_j"],
            "r_j": span["d_j"] - span["p_j"],
            "hit_strict": strict,
            "hit_wide": bool(wide_hits) or strict,
            "wide_deltas_scanned": scanned,
            "wide_hits": wide_hits,
        })

    # --- verdict, A17.5 ---------------------------------------------------
    if not winner_rows:
        verdict = "UNTESTED (no covered winner)"
    elif any(w["hit_strict"] for w in winner_rows):
        verdict = "CARRIES CREDITS (STRICT)"
    elif any(w["hit_wide"] for w in winner_rows):
        verdict = "CARRIES CREDITS (WIDE)"
    else:
        verdict = "BLIND"

    return {
        # A17.12: the denominator prints first, before any hit flag.
        "eligible_winner_count": len(winner_rows),
        "verdict": verdict,
        "exclusion_counts": {k: len(v) for k, v in exclusions.items()},
        "exclusions": exclusions,
        "ineligible_contracts": ineligible_contracts,
        "total_adjacent_pairs": len(spans),
        "coverage_only_pairs": coverage_only_pairs,
        "winners": winner_rows,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: analyze_h4_channel_diagnostic.py <spans_pull.json>",
              file=sys.stderr)
        return 2
    payload = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    print(json.dumps(analyze(payload), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
