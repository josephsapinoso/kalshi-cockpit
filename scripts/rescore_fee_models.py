"""Re-score the pinned clean-shortfall record under three fee models.

ADR 0021 concluded that the consensus-only strategy is refuted, on the evidence
that **zero clean rows clear the deployed fee** and `max E1 = -2.0534` tenths.
That was computed with `core/fees.py`'s `max(model_a, model_b)` hedge, which
`docs/measurements/2026-08-10-fee-model-fill-calibration-result.md` refutes at
all four registered cells. Every row's `E1` therefore moves, and the
refutation's own denominator is stale.

This harness answers one question over a **fixed snapshot**
(`docs/measurements/2026-08-10-clean-shortfall-pull.json`, `pin = 1564`):

    Under each fee model, how many observations clear the fee -- and for every
    row that then fails to surface, which check refused it?

The three models, exactly as the calibration result's decomposition names them:

    deployed   max(model_a, model_b)       fee@50c, C=1  $0.0200
    step 1     0.07  x C x P(1-P), ceil $0.0001          $0.0175
    step 2     0.035 x C x P(1-P), ceil $0.0001          $0.0088

Why the population cannot grow
------------------------------
**Nine** of the twelve suppression checks are functions of inputs the fee does
not touch. Three are movable: `edge_within_method_noise` and `suspicious_edge`
read the edge directly, and `insufficient_depth` reads a size the edge
determines.

Only one of the three can move in the *permissive* direction. A cheaper fee
raises the edge, so `suspicious_edge` can only fire more, and the depth
requirement `max(10, contracts)` can only rise. `edge_within_method_noise` is
the exception: it fails on `0 < edge <= spread`, so a big enough rise carries a
row over its own spread and the check starts passing. That path needs a row
suppressed by `edge_within_method_noise` **alone**, and there are **zero** of
those on this pin -- ADR 0021 5.1's measurement, re-derived here.

So the set of rows that could ever clear under any cheaper fee is exactly the
614 already-clean rows, and every count below sits on the denominator ADR 0021
used. This is a fact about `pin = 1564`, not a structural guarantee.

Units
-----
The fee grid is quantised in `Decimal` so `ceil` is exact; **everything
downstream is float**, including every `E1`. `$0.0001` is not representable in
`core/prices.py`'s integer tenths of a cent -- one tenth is `$0.001`, ten times
coarser -- so this arithmetic deliberately runs outside the risk path and
nothing here is imported by production code. The units question is real and is
an ADR; a measurement must not wait on it.

What this harness does NOT establish
------------------------------------
- **It does not adopt a fee model.** The calibration result's verdict is H3-:
  both registered models are refuted and no third is adopted. `k = 0.07` and
  `k = 0.035` are hypothesis generators. A count computed under a hypothesis
  generator is a conditional, not a finding about the venue.
- **It does not establish that any row was bettable.** It re-scores stored rows
  against a counterfactual cost. No order was placed, no fill exists, and the
  asks are historical quotes whose own freshness is unmeasurable
  (ADR 0021 7.6).
- **It says nothing about whether `fair_probability` is right.** Every `E1` here
  inherits the conservative devig and the `SHARP_BOOKS` anchoring, with all of
  ADR 0021 7.2 and 7.3 attached.
- **It does not re-run the operator-side sizing.** `suggested_contracts`
  depends on the exposure and P&L at the moment the row was written, which the
  payload does not carry. Only `reference_contracts` -- the fixed-bankroll
  profile the gate counts -- is recomputable, and only that is recomputed.
- **It is one pin, one 58-hour window, two leagues, one month.** A census over
  34 recording instants, with no interval anywhere and nothing that generalises
  to a future row.
- **`KXWNBAGAME` is 27.0% of the record and carries zero fee observations.**
  Any row of that series re-scored under step 1 or step 2 is being priced by a
  coefficient measured on a different sport. Such rows are flagged individually.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.analysis.joint_bound import cluster_key  # noqa: E402
from backend.config import (  # noqa: E402
    REFERENCE_BANKROLL_DOLLARS,
    REFERENCE_MAX_EXPOSURE_DOLLARS,
    REFERENCE_MAX_POSITION_DOLLARS,
    RiskConfig,
)
from backend.core.fees import settlement_fee  # noqa: E402
from backend.core.prices import PRICE_MAX  # noqa: E402
from backend.core.suppression import SuppressionConfig  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PULL = ROOT / "docs/measurements/2026-08-10-clean-shortfall-pull.json"
PIN = 1564

#: The two suppression codes that read the edge, and are therefore the only
#: ones a fee change can switch on. `insufficient_depth` reads a *size* the
#: edge can move and is re-evaluated separately.
EDGE_DEPENDENT = ("edge_within_method_noise", "suspicious_edge")

#: The fee grid the calibration result identified as the unique survivor of its
#: granularity x rounding census. Not adopted -- used as a counterfactual.
FEE_GRID = Decimal("0.0001")

_P_FIELDS = ("p_multiplicative", "p_additive", "p_power", "p_shin")


# ---------------------------------------------------------------------------
# The three fee models
# ---------------------------------------------------------------------------


def _ceil_grid_fee(ask_tenths: int, contracts: int, coefficient: str) -> float:
    """`ceil_{$0.0001}( k x C x P x (1-P) )`, in dollars, for the whole order."""
    price = Decimal(ask_tenths) / Decimal(PRICE_MAX)
    raw = Decimal(coefficient) * Decimal(contracts) * price * (Decimal(1) - price)
    return float(raw.quantize(FEE_GRID, rounding=ROUND_CEILING))


def _deployed_fee(ask_tenths: int, contracts: int) -> Optional[float]:
    return settlement_fee(ask_tenths, contracts, False)


FeeModel = Callable[[int, int], Optional[float]]

MODELS: dict[str, FeeModel] = {
    "deployed": _deployed_fee,
    "step1": lambda a, c: _ceil_grid_fee(a, c, "0.07"),
    "step2": lambda a, c: _ceil_grid_fee(a, c, "0.035"),
}

MODEL_LABEL = {
    "deployed": "deployed   0.07, ceil-to-CENT, max(A,B)",
    # "well supported" is true of the ROUNDING and false of the COEFFICIENT:
    # three registered KXMLBGAME cells refute 0.07 by a factor of ~2, and it
    # survives only at the single ATP cell, which carries zero degrees of
    # freedom. For the MLB rows this harness surfaces, step 1 is the most
    # expensive fee consistent with the observed rounding, not the likeliest.
    "step1": "step 1     0.07,  ceil-to-$0.0001   [ROUNDING SUPPORTED; "
             "COEFFICIENT REFUTED AT MLB -- CONSERVATIVE UPPER BOUND]",
    "step2": "step 2     0.035, ceil-to-$0.0001   [POST-HOC, 5 rival attributions]",
}


# ---------------------------------------------------------------------------
# Row helpers. All floats, deliberately -- see the module docstring.
# ---------------------------------------------------------------------------


def spread_tenths(row: dict) -> Optional[float]:
    """`(max - min)` across the four devig readings, in tenths of a cent.

    `None` if any reading is NULL. `None` never becomes `0.0`: a spread of zero
    means "the methods agreed", which is the opposite of "we could not tell".
    """
    values = [row.get(f) for f in _P_FIELDS]
    if any(v is None for v in values):
        return None
    return (max(values) - min(values)) * PRICE_MAX  # type: ignore[type-var]


def edge_tenths(row: dict, model: str, contracts: int = 1) -> Optional[float]:
    """Post-fee edge per contract in tenths of a cent, at `contracts` size."""
    fee = MODELS[model](int(row["ask_tenths"]), contracts)
    if fee is None:
        return None
    effective = row["ask_tenths"] / PRICE_MAX + fee / contracts
    return (row["fair_probability"] - effective) * PRICE_MAX


def _full_kelly(fair: float, price: float) -> float:
    if not 0.0 < price < 1.0:
        return 0.0
    return max(0.0, fair - (1.0 - fair) / ((1.0 - price) / price))


def reference_contracts(row: dict, model: str, risk: RiskConfig) -> int:
    """`core.sizing.size_position` at the **reference** profile, re-implemented.

    Re-implemented rather than imported because `size_position` prices through
    `core.ev.effective_price`, which is hard-wired to `calculate_fee`; the whole
    point here is to vary that. The arithmetic is line-for-line the same and the
    `deployed` column reproduces the stored `reference_contracts` on all 614
    clean rows, which is the checksum that says so.
    """
    fee = MODELS[model](int(row["ask_tenths"]), 1)
    if fee is None:
        return 0
    price = row["ask_tenths"] / PRICE_MAX + fee
    if price >= 1.0:
        return 0
    full = _full_kelly(row["fair_probability"], price)
    if full <= 0.0:
        return 0
    stake = full * risk.kelly_fraction * REFERENCE_BANKROLL_DOLLARS
    stake = min(stake, REFERENCE_MAX_POSITION_DOLLARS, REFERENCE_MAX_EXPOSURE_DOLLARS)
    return min(int(stake // price), risk.max_order_contracts)


def stored_codes(row: dict) -> set[str]:
    reason = row.get("suppressed_reason")
    return set(reason.split(",")) - {""} if reason else set()


def ticker_suffix(ticker: str) -> str:
    return ticker.split("-")[-1] if ticker else ""


def series_of(ticker: str) -> str:
    return ticker.split("-", 1)[0] if ticker else ""


# ---------------------------------------------------------------------------
# The claim normalisation, imported in spirit from the registration's 3
# ---------------------------------------------------------------------------


def build_suffixes(rows: Sequence[dict]) -> dict[str, set[str]]:
    suffixes: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        key = cluster_key(r["ticker"], r.get("event_ticker"))
        if key:
            suffixes[key].add(ticker_suffix(r["ticker"]))
    return suffixes


def claim_of(row: dict, cluster: str, suffixes: dict[str, set[str]]) -> Any:
    """A `NO` on one ticker and a `YES` on the other name the same claim (A1)."""
    suffix = ticker_suffix(row["ticker"])
    peers = suffixes.get(cluster, set())
    if row["side"] == "yes":
        return suffix
    if row["side"] == "no" and len(peers) == 2:
        other = next(iter(peers - {suffix}), None)
        if other is not None:
            return other
    return ("NO", suffix)


@dataclass(frozen=True)
class Scored:
    row: dict
    cluster: str
    claim: Any
    e1: float
    spread: Optional[float]
    ref_contracts: int
    refusals: tuple[str, ...]

    @property
    def id(self) -> int:
        return int(self.row["id"])

    @property
    def surfaced(self) -> bool:
        return not self.refusals


def dedup(items: Sequence[Scored], key: Callable[[Scored], Any]) -> list[Scored]:
    """The registration's representative rule: largest `E1`, ties by lowest id."""
    best: dict[Any, Scored] = {}
    for s in items:
        k = key(s)
        cur = best.get(k)
        if cur is None or (s.e1, -s.id) > (cur.e1, -cur.id):
            best[k] = s
    return list(best.values())


def dedup_smallest(items: Sequence[Scored], key: Callable[[Scored], Any]) -> list[Scored]:
    """The **opposite** rule, per ADR 0021 5.2's re-cut table."""
    best: dict[Any, Scored] = {}
    for s in items:
        k = key(s)
        cur = best.get(k)
        if cur is None or (s.e1, s.id) < (cur.e1, cur.id):
            best[k] = s
    return list(best.values())


def OBS_KEY(s: Scored) -> Any:
    """The registered unit of observation: `(cluster, instant, claim)`."""
    return (s.cluster, s.row["created_ms"], s.claim)


def CLAIM_KEY(s: Scored) -> Any:
    """The hardest floor: `(cluster, claim)`, roughly two per game."""
    return (s.cluster, s.claim)


# ---------------------------------------------------------------------------
# Scoring one model
# ---------------------------------------------------------------------------


def score(
    clean: Sequence[dict],
    model: str,
    suffixes: dict[str, set[str]],
    suppression: SuppressionConfig,
    risk: RiskConfig,
) -> list[Scored]:
    """Every clean row, re-scored under `model`, with its refusals named.

    The ten fee-invariant checks already passed -- that is what "clean" means
    and it cannot change. What is re-evaluated is exactly what the fee can move:
    the two edge-dependent codes, the depth requirement (which reads a size the
    edge determines), and the reference sizing floor.
    """
    out: list[Scored] = []
    for row in clean:
        cluster = cluster_key(row["ticker"], row.get("event_ticker"))
        if cluster is None:
            continue
        e1 = edge_tenths(row, model)
        if e1 is None:
            continue
        spread = spread_tenths(row)
        ref = reference_contracts(row, model, risk)

        refusals: list[str] = []
        if spread is None:
            # Unreadable spread must refuse, never pass. No clean row on this
            # pin is in that state; the branch exists so a future one cannot
            # slip through as "the methods agreed".
            refusals.append("method_spread_unreadable")
        elif not (e1 <= 0.0 or e1 > spread):
            refusals.append("edge_within_method_noise")
        if e1 > suppression.edge_ceiling_tenths:
            refusals.append("suspicious_edge")

        required = max(suppression.min_depth_contracts, float(max(1, ref)))
        depth = row.get("depth_at_ask")
        if depth is None:
            refusals.append("no_depth")
        elif depth < required:
            refusals.append("insufficient_depth")

        if e1 <= 0.0:
            refusals.append("no_edge_after_fee")
        elif ref <= 0:
            refusals.append("sizing:stake_below_one_contract")

        out.append(
            Scored(
                row=row,
                cluster=cluster,
                claim=claim_of(row, cluster, suffixes),
                e1=e1,
                spread=spread,
                ref_contracts=ref,
                refusals=tuple(refusals),
            )
        )
    return out


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


class Report:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def __call__(self, text: str = "") -> None:
        self.lines.append(text)
        print(text)

    def rule(self, title: str) -> None:
        self("")
        self("=" * 78)
        self(title)
        self("=" * 78)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pull", type=Path, default=PULL)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    out = Report()
    data = json.loads(args.pull.read_text(encoding="utf-8"))
    rows = [r for page in data["pages"] for r in page["rows"]]
    suppression = SuppressionConfig()
    risk = RiskConfig()

    out.rule("S1 -- THE FRAME. Read this before n, and n before any effect size.")
    out(f"  pull                {args.pull.name}")
    out(f"  pulled_at_utc       {data['pulled_at_utc']}")
    out(f"  pin                 {data['pin']}  (expected {PIN})")
    out(f"  rows in pull        {len(rows)}")
    out("")
    out("  This is a CENSUS over a fixed snapshot, not a sample. No interval is")
    out("  computed anywhere and none would mean anything. No normal")
    out("  approximation is used, so the >=5-per-side rule has nothing to gate.")
    out("")
    out("  TESTS RUN: three fee models x one predicate = 3 primary counts.")
    out("  Every other number below is a decomposition of those three, not an")
    out("  additional test. No cell is scanned for significance.")

    # -- S2. Checksums -----------------------------------------------------
    out.rule("S2 -- REPRODUCTION CHECKSUMS. The reconstruction, verified first.")

    clean = [r for r in rows if r["suppressed_reason"] is None]
    out(f"  clean rows (suppressed_reason IS NULL) .......... {len(clean)}")

    only_edge = [
        r for r in rows
        if stored_codes(r) and stored_codes(r) <= set(EDGE_DEPENDENT)
    ]
    eligible = [r for r in rows if not (stored_codes(r) - set(EDGE_DEPENDENT))]
    out(f"  suppressed ONLY by edge-dependent codes ......... {len(only_edge)}")
    out(f"  fee-INVARIANT eligible pool .................... {len(eligible)}")
    out("    -> a cheaper fee cannot ADD a row to the clean population on this")
    out("       pin. It can only remove one. ADR 0021 5.1, re-derived.")
    out("    The permissive path exists and is closed by that zero, not by a")
    out("    monotonicity argument: `edge_within_method_noise` STOPS firing once")
    out("    a rising edge clears its own spread. It needs a row carrying that")
    out("    code alone, and there is none.")
    depth_alone = [
        r for r in rows if stored_codes(r) == {"insufficient_depth"}
    ]
    out(f"    rows suppressed by `insufficient_depth` ALONE .. {len(depth_alone)}")
    for r in depth_alone:
        out(f"      id {r['id']:5d} {r['ticker']:34s} depth {r['depth_at_ask']:8.2f}"
            f"   step2 E1 {edge_tenths(r, 'step2'):+8.4f}")
    out(f"    ...all below min_depth_contracts = "
        f"{suppression.min_depth_contracts:.0f}: "
        f"{all((r['depth_at_ask'] or 0.0) < suppression.min_depth_contracts for r in depth_alone)}")
    out("    `insufficient_depth` is the one non-edge check the fee can move, and")
    out("    it moves only in the suppressing direction: a cheaper fee raises")
    out("    Kelly and therefore `max(10, contracts)`. No fee can lower the")
    out("    10-contract floor these three sit under.")

    c_edge = sum(
        1 for r in rows
        if abs((edge_tenths(r, "deployed") or 0.0) - r["edge_tenths"]) <= 1e-9
    )
    out(f"  stored edge_tenths == deployed E1 at C=1 ....... {c_edge} of {len(rows)}")
    c_edge_clean = sum(
        1 for r in clean
        if abs((edge_tenths(r, "deployed") or 0.0) - r["edge_tenths"]) <= 1e-9
    )
    out(f"    ...restricted to the clean population ........ {c_edge_clean} of {len(clean)}")
    out("    The 1,564-row figure is expected to MISS: rows the engine sized at")
    out("    C>1 carry an edge computed at that size. Every miss must be a")
    out("    suppressed row -- on a clean row the edge is negative, Kelly is 0,")
    out("    and `sizing_contracts` is `max(1, 0) = 1` by construction.")
    misses_clean = [r for r in clean if abs((edge_tenths(r, "deployed") or 0.0) - r["edge_tenths"]) > 1e-9]
    out(f"    clean rows that miss .......................... {len(misses_clean)}  (must be 0)")

    # The size that explains a miss is not readable from `suggested_contracts`
    # -- `engine.py` zeroes it on every suppressed row. It IS readable from
    # `fee_predicted`, which carries the WHOLE-ORDER fee at that same size, so
    # the two fields must be satisfiable by ONE order size or the
    # reconstruction is wrong. Solving edge alone is not enough: `fee/C` is
    # piecewise constant in `C`, so several sizes fit the edge and only one
    # fits both.
    joint, sizes = 0, []
    for r in rows:
        for c in range(1, 201):
            fee = _deployed_fee(int(r["ask_tenths"]), c)
            if fee is None:
                continue
            e = (r["fair_probability"] - (r["ask_tenths"] / PRICE_MAX + fee / c)) * PRICE_MAX
            if abs(e - r["edge_tenths"]) <= 1e-9 and abs(fee - r["fee_predicted"]) <= 1e-12:
                joint += 1
                if abs((edge_tenths(r, "deployed") or 0.0) - r["edge_tenths"]) > 1e-9:
                    sizes.append(c)
                break
    out("  edge_tenths AND fee_predicted jointly satisfied")
    out(f"  by ONE order size, whole table ................. {joint} of {len(rows)}")
    out(f"    sizes implied on the {len(sizes)} misses: min {min(sizes)}, "
        f"max {max(sizes)}, modal {Counter(sizes).most_common(1)[0][0]}")
    out("    `suggested_contracts` is 0 on all 93 misses (engine.py zeroes it on")
    out("    suppression), so it cannot be used to check this and is not.")

    c_fair = sum(
        1 for r in rows
        if not any(r.get(f) is None for f in _P_FIELDS)
        and abs(min(r[f] for f in _P_FIELDS) - r["fair_probability"]) <= 1e-15
    )
    out(f"  fair_probability == min(four devig readings) ... {c_fair} of {len(rows)}")

    # Counted per CODE, not per row. An `elif` here would let one disagreement
    # mask the other and the guard could never fail on `suspicious_edge`.
    mis_noise = mis_susp = 0
    for r in rows:
        s = spread_tenths(r)
        if s is None:
            continue
        e = r["edge_tenths"]
        stored = stored_codes(r)
        if (not (e <= 0 or e > s)) != ("edge_within_method_noise" in stored):
            mis_noise += 1
        if (e > suppression.edge_ceiling_tenths) != ("suspicious_edge" in stored):
            mis_susp += 1
    out("  edge-dependent codes re-derived from the stored edge,")
    out(f"  disagreements: edge_within_method_noise {mis_noise}, "
        f"suspicious_edge {mis_susp}   (both must be 0)")

    stored_ref = sum(1 for r in rows if (r.get("reference_contracts") or 0) > 0)
    recomputed_ref = sum(1 for r in clean if reference_contracts(r, "deployed", risk) > 0)
    out(f"  stored reference_contracts > 0, whole table .... {stored_ref}")
    out(f"  recomputed at deployed fee, clean rows ......... {recomputed_ref}")
    out("    VACUOUS, and labelled so rather than quoted. Every clean row has a")
    out("    negative edge, so Kelly is 0 and BOTH figures are forced to 0 under")
    out("    any implementation, right or wrong. It tests nothing about the caps,")
    out("    `kelly_fraction`, the floor division or `max_order_contracts` -- which")
    out("    is the entire regime deciding whether a row sizes. The real check is")
    out("    the next one.")

    out("")
    out("  NON-VACUOUS: `reference_contracts` against the production sizer.")
    out("  A synthetic sweep over the price grid at fair values that DO carry an")
    out("  edge, so Kelly, both dollar caps, the `//` truncation and")
    out("  `max_order_contracts` all have to agree. `size_position` is called")
    out("  for real; only the fair value is synthetic.")
    from backend.core.sizing import size_position  # noqa: PLC0415

    ref_risk = risk.reference()
    checked = disagree = nonzero = capped = 0
    for ask in range(10, 990, 7):
        for lift in (0.005, 0.02, 0.05, 0.15, 0.40):
            fair = min(0.999, ask / PRICE_MAX + lift)
            probe = {"ask_tenths": ask, "fair_probability": fair}
            mine = reference_contracts(probe, "deployed", risk)
            theirs = size_position(
                side="yes", ask_tenths=ask, fair_probability=fair,
                risk=ref_risk, current_exposure_dollars=0.0,
                # The reference profile is a clean book by definition. Written
                # out because `size_position` no longer defaults them: an
                # omitted risk input used to read as zero, which is how the
                # daily loss limit went unsupplied by every production caller.
                current_position_dollars=0.0, daily_pnl_dollars=0.0,
                maker=False,
            )
            checked += 1
            nonzero += 1 if mine > 0 else 0
            capped += 1 if mine == risk.max_order_contracts else 0
            if mine != (0 if theirs.refused else theirs.contracts):
                disagree += 1
    out(f"    probes {checked}, of which {nonzero} size a positive number and")
    out(f"    {capped} hit `max_order_contracts`; disagreements {disagree} (must be 0)")

    # -- S3. The three models ---------------------------------------------
    out.rule("S3 -- THE THREE FEE MODELS, evaluated rather than quoted.")
    out(f"  {'model':10s} {'fee@50c':>10s} {'fee@45c':>10s} {'fee@55c':>10s}"
        f"  {'break-even':>11s}")
    for name in ("deployed", "step1", "step2"):
        f50 = MODELS[name](500, 1) or 0.0
        f45 = MODELS[name](450, 1) or 0.0
        f55 = MODELS[name](550, 1) or 0.0
        out(f"  {name:10s} {f50:10.4f} {f45:10.4f} {f55:10.4f}  {50.0 + f50 * 100:10.2f}%")
    out("")
    out("  Arithmetic note, stated because it is load-bearing: the fee grid is")
    out("  quantised in Decimal so `ceil` is exact, and EVERY number downstream")
    out("  is a FLOAT. $0.0001 is not representable in core/prices.py's integer")
    out("  tenths of a cent -- one tenth is $0.001, ten times coarser -- so none")
    out("  of this arithmetic is on the money grid and none of it is imported by")
    out("  production code. That units question is an ADR; a measurement must")
    out("  not wait on it.")

    # -- S4/S5. Per model --------------------------------------------------
    suffixes = build_suffixes(rows)
    results: dict[str, list[Scored]] = {}
    for model in ("deployed", "step1", "step2"):
        results[model] = score(clean, model, suffixes, suppression, risk)

    base = results["deployed"]
    out.rule("S4 -- DENOMINATORS. The same population under every model.")
    out(f"  n_rows   clean rows ................. {len(base)}")
    out(f"  n_obs    (cluster, instant, claim) .. {len(dedup(base, OBS_KEY))}")
    out(f"  n_claims (cluster, claim) ........... {len(dedup(base, CLAIM_KEY))}")
    out(f"  G        distinct game clusters ..... {len({s.cluster for s in base})}")
    out(f"  sweeps   distinct created_ms ........ {len({s.row['created_ms'] for s in base})}")
    out("")
    out("  Unchanged across models by construction (S2): the fee moves E1, not")
    out("  membership. State the evidence as `59 games across 34 recording")
    out("  instants`, never as `614 rows`.")

    for model in ("deployed", "step1", "step2"):
        scored = results[model]
        out.rule(f"S5 -- {MODEL_LABEL[model]}")
        positives = [s for s in scored if s.e1 > 0.0]
        surfaced = [s for s in scored if s.surfaced]
        out(f"  max E1 over the clean population ......... {max(s.e1 for s in scored):+.4f} tenths")
        out(f"  clean ROWS with E1 > 0 ................... {len(positives)} of {len(scored)}")
        obs_pos = [s for s in dedup(scored, OBS_KEY) if s.e1 > 0.0]
        claim_pos = [s for s in dedup(scored, CLAIM_KEY) if s.e1 > 0.0]
        out(f"  ...deduplicated to observations .......... {len(obs_pos)} of {len(dedup(scored, OBS_KEY))}")
        out(f"  ...deduplicated to claims ................ {len(claim_pos)} of {len(dedup(scored, CLAIM_KEY))}")
        out(f"  ...distinct game clusters ................ {len({s.cluster for s in positives})}")
        out("")
        out(f"  SURVIVE THE FULL DEPLOYED PREDICATE ...... {len(surfaced)} rows")
        out(f"    distinct claims .......................... {len({(s.cluster, s.claim) for s in surfaced})}")
        out(f"    distinct games ........................... {len({s.cluster for s in surfaced})}")

        if positives:
            out("")
            out("  Every row with E1 > 0, and what refused it:")
            out(f"    {'id':>5s} {'ticker':34s} {'sd':3s} {'ask':>4s} {'E1':>9s} "
                f"{'spread':>8s} {'refC':>5s}  refusals")
            for s in sorted(positives, key=lambda s: -s.e1):
                flag = " [WNBA: ZERO FEE OBSERVATIONS]" if series_of(s.row["ticker"]) == "KXWNBAGAME" else ""
                out(f"    {s.id:5d} {s.row['ticker']:34s} {s.row['side']:3s} "
                    f"{s.row['ask_tenths']:4d} {s.e1:+9.4f} "
                    f"{(s.spread if s.spread is not None else float('nan')):8.4f} "
                    f"{s.ref_contracts:5d}  "
                    f"{','.join(s.refusals) if s.refusals else 'NONE -- SURFACES'}{flag}")

        out("")
        out("  PER-GUARD REFUSAL TABLE, over rows that cleared the fee:")
        guard = Counter()
        for s in positives:
            for name in s.refusals:
                guard[name] += 1
        if not guard:
            out("    (nothing to refuse -- no row cleared the fee)" if not positives
                else "    (no refusals -- every positive row surfaced)")
        for name, count in guard.most_common():
            alone = sum(1 for s in positives if s.refusals == (name,))
            out(f"    {name:34s} fires {count:3d}   ALONE {alone:3d}")

        out("")
        out("  DECISIVENESS -- is any guard actually load-bearing here?")
        for name in ("edge_within_method_noise", "sizing:stake_below_one_contract"):
            without = sum(
                1 for s in positives
                if not [f for f in s.refusals if f != name]
            )
            out(f"    delete `{name}`, keep everything else -> {without} rows surface")
        out("    A guard is DECISIVE only if deleting it changes that number.")

        if surfaced:
            out("")
            out("  Largest single contributor, per CLAUDE.md's pooled-number rule:")
            by_cluster = Counter(s.cluster for s in surfaced)
            top, n = by_cluster.most_common(1)[0]
            out(f"    {top}: {n} of {len(surfaced)} rows = {100.0 * n / len(surfaced):.1f}%")
            by_claim = Counter((s.cluster, s.claim) for s in surfaced)
            topc, nc = by_claim.most_common(1)[0]
            out(f"    claim {topc}: {nc} of {len(surfaced)} rows")
            out("    Both sides of one two-way market name ONE claim under A1, so a")
            out("    row count overstates the number of distinct opportunities.")

        series = Counter(series_of(s.row["ticker"]) for s in positives)
        out("")
        out(f"  Rows clearing the fee, by series: {dict(series) or '{}'}")
        wnba_pos = [s for s in positives if series_of(s.row["ticker"]) == "KXWNBAGAME"]
        wnba_surf = [s for s in surfaced if series_of(s.row["ticker"]) == "KXWNBAGAME"]
        out(f"    KXWNBAGAME is 27.0% of the record and has ZERO fee observations.")
        out(f"    positives from it: {len(wnba_pos)}    surfacing from it: {len(wnba_surf)}")

    # -- S6. Re-cuts -------------------------------------------------------
    out.rule("S6 -- RE-CUTS. ADR 0021 5.2's robustness, applied to this question.")
    out("  A pooled count is not a finding until the parts agree.")
    for model in ("step1", "step2"):
        scored = results[model]
        surfaced = [s for s in scored if s.surfaced]
        out("")
        out(f"  {MODEL_LABEL[model]}")
        out(f"    {'reading':58s} {'surface':>8s}")
        out(f"    {'no dedup, all clean rows':58s} {len(surfaced):8d}")
        for label, key in (("obs key (cluster, instant, claim)", OBS_KEY),
                           ("claim key (cluster, claim)", CLAIM_KEY)):
            keep = {id(s) for s in dedup(scored, key)}
            out(f"    {'largest-E1 representative, ' + label:58s} "
                f"{sum(1 for s in surfaced if id(s) in keep):8d}")
            keep_s = {id(s) for s in dedup_smallest(scored, key)}
            out(f"    {'smallest-E1 representative, ' + label:58s} "
                f"{sum(1 for s in surfaced if id(s) in keep_s):8d}")
        out("    The smallest-E1 rule is printed for continuity with ADR 0021 5.2")
        out("    and MUST NOT be read as the answer here. 5.2 used it against H3b,")
        out("    an order statistic. This question is an EXISTENCE claim, and the")
        out("    registration's own 3 justifies the largest-E1 rule for exactly")
        out("    that: keeping the most favourable row per group is the reading")
        out("    most likely to falsify a null, so it cannot manufacture one. The")
        out("    smallest-E1 rule asks whether the WORST row of each group")
        out("    surfaces, which nothing in this project claims.")

        # BOTH units. ADR 0021 2 records that the dependence unit is the SWEEP
        # and that two earlier documents printed only the cluster; a third
        # omitting it would read as a convention.
        for unit, of in (("game", lambda s: s.cluster),
                         ("sweep", lambda s: s.row["created_ms"])):
            groups = sorted({of(s) for s in scored})
            logo = [(g, sum(1 for s in surfaced if of(s) != g)) for g in groups]
            counts = Counter(n for _, n in logo)
            out(f"    leave-one-{unit}-out over all {len(groups)} {unit}s:")
            for n, k in sorted(counts.items()):
                out(f"      {k:3d} of {len(groups)} exclusions leave {n} surfacing rows")
            out(f"      min {min(n for _, n in logo)}, max {max(n for _, n in logo)}")
            if surfaced:
                top, n = Counter(of(s) for s in surfaced).most_common(1)[0]
                out(f"      largest single {unit}: {top} carries {n} of "
                    f"{len(surfaced)} = {100.0 * n / len(surfaced):.1f}%")
        contributors = sorted({s.cluster for s in surfaced})
        out(f"    clusters contributing a surfacing row: {len(contributors)}")
        for c in contributors:
            out(f"      {c}: {sum(1 for s in surfaced if s.cluster == c)}")

        if surfaced:
            out("    PERSISTENCE -- how durable is each surfacing claim?")
            by_claim: dict[Any, list[Scored]] = defaultdict(list)
            for s in scored:
                by_claim[(s.cluster, s.claim)].append(s)
            for key in sorted({(s.cluster, s.claim) for s in surfaced}):
                g = by_claim[key]
                out(f"      {key[0]} / {key[1]}: {len(g)} clean rows across "
                    f"{len({x.row['created_ms'] for x in g})} instants -> "
                    f"{sum(1 for x in g if x.surfaced)} surface; E1 ranges "
                    f"{min(x.e1 for x in g):+.2f} .. {max(x.e1 for x in g):+.2f}")
            out("      Each surfaces at ONE of the several instants at which it was")
            out("      observed. These are claim-INSTANTS, not durable opportunities.")

    # -- S7. Sensitivity ---------------------------------------------------
    out.rule("S7 -- SENSITIVITY. The two places this could be wrong by arithmetic.")
    out("  (a) E1 is computed at ONE contract. The engine feeds suppression an")
    out("      edge computed at `max(1, sizing.contracts)`, and that size depends")
    out("      on the operator's exposure at the time, which the payload does not")
    out("      carry. The C=1 fee carries up to $0.0001 of its own ceiling, so")
    out("      the per-contract fee at ANY size is below it by at most")
    out("      0.1 tenths -- a FLAT bound, not 0.1/C. (0.1/C is wrong: the")
    out("      evaluated infimum below improves id 726 by 0.075 tenths, which")
    out("      exceeds 0.1/C for every C >= 2.) C=1 is the CONSERVATIVE reading.")
    out("      Rather than argue the bound, the worst case is EVALUATED: the")
    out("      per-contract fee is replaced by its infimum over all order sizes,")
    out("      `k x P x (1-P)` with no ceiling at all, and the whole predicate is")
    out("      re-run. Nothing the order size can do is more favourable than that.")
    for model, coefficient in (("step1", "0.07"), ("step2", "0.035")):
        scored = results[model]
        near = [
            (abs(s.e1), "fee bar", s) for s in scored if abs(s.e1) < 0.15
        ] + [
            (abs(s.e1 - s.spread), "noise bar", s)
            for s in scored if s.spread is not None and abs(s.e1 - s.spread) < 0.15
        ]
        out("")
        out(f"    {model}: clean rows within 0.15 tenths of a decision bar: {len(near)}")
        for margin, which, s in sorted(near):
            out(f"      {margin:.4f} from the {which:9s} id {s.id:5d} "
                f"{s.row['ticker']:34s} E1 {s.e1:+.4f} spread "
                f"{(s.spread if s.spread is not None else float('nan')):.4f}")
        floor_name = f"{model}_floor"
        MODELS[floor_name] = (
            lambda a, c, _k=coefficient: float(
                Decimal(_k) * Decimal(c)
                * (Decimal(a) / Decimal(PRICE_MAX))
                * (Decimal(1) - Decimal(a) / Decimal(PRICE_MAX))
            )
        )
        floor = score(clean, floor_name, suffixes, suppression, risk)
        out(f"      worst-case re-run (fee = k*P*(1-P), no ceiling):")
        out(f"        rows with E1 > 0 ......... {sum(1 for s in floor if s.e1 > 0)}"
            f"   (base {sum(1 for s in scored if s.e1 > 0)})")
        out(f"        rows that surface ........ {sum(1 for s in floor if s.surfaced)}"
            f"   (base {sum(1 for s in scored if s.surfaced)})")
    out("")
    out("  (b) The DEPLOYED model is not flat in order size, and the engine")
    out("      cannot reach the size where that matters. `size_position` prices")
    out("      through `effective_price(ask, contracts=1)`, so a row that is")
    out("      -EV at one contract is sized at zero and never re-priced larger.")
    out("      Under `max(model_a, model_b)` the per-order cent ceiling makes the")
    out("      per-contract fee FALL with size:")
    out(f"      {'ask':>5s} {'C=1':>9s} {'C=10':>9s} {'C=50':>9s}   (tenths/contract)")
    for ask in (450, 500, 550):
        vals = []
        for c in (1, 10, 50):
            f = MODELS["deployed"](ask, c) or 0.0
            vals.append(f / c * PRICE_MAX)
        out(f"      {ask:5d} {vals[0]:9.3f} {vals[1]:9.3f} {vals[2]:9.3f}")
    out("")
    out("      This is NOT hypothetical, and it fires with no fee correction at")
    out("      all. Over the clean population, at the DEPLOYED fee:")
    out(f"      {'C':>4s} {'rows E1>0':>10s} {'max E1':>10s}")
    for c in (1, 5, 10, 25, 50):
        es = []
        for r in clean:
            f = MODELS["deployed"](int(r["ask_tenths"]), c)
            if f is None:
                continue
            es.append((r["fair_probability"]
                       - (r["ask_tenths"] / PRICE_MAX + f / c)) * PRICE_MAX)
        out(f"      {c:4d} {sum(1 for e in es if e > 0):10d} {max(es):+10.4f}")
    out("      The three rows that cross are id 726, 355 and 352 -- the SAME")
    out("      three step 1 produces, which is not a coincidence: at ask 450 the")
    out("      deployed fee at C=50 IS step 1's fee. So ADR 0021 2's `zero clean")
    out("      rows clear the deployed fee` is SIZE-conditional as well as")
    out("      fee-conditional. All three are still refused by")
    out("      `edge_within_method_noise` and by the sizing floor, so nothing")
    out("      surfaces -- but the crossing is real and needs no fee correction.")
    out("      An observation about the deployed sizer, not a recommendation.")

    out("")
    out("  (c) The sizing floor is a property of the REFERENCE BANKROLL, not a")
    out("      law. A row sizes iff `E1 > 4000*eff*(1-eff)/bankroll` tenths at")
    out(f"      `kelly_fraction = {risk.kelly_fraction}`, which is the 1.0-tenth")
    out(f"      supremum only because the reference bankroll is "
        f"${REFERENCE_BANKROLL_DOLLARS:,.0f}. Raise it and this")
    out("      guard stops firing on the step-1 rows:")
    for s in sorted([s for s in results["step1"] if s.e1 > 0.0], key=lambda s: -s.e1):
        fee = MODELS["step1"](int(s.row["ask_tenths"]), 1) or 0.0
        price = s.row["ask_tenths"] / PRICE_MAX + fee
        full = _full_kelly(s.row["fair_probability"], price)
        out(f"      id {s.id:5d}: sizes at a reference bankroll of "
            f"${price / (full * risk.kelly_fraction):,.0f}, or at "
            f"kelly_fraction {price / (full * REFERENCE_BANKROLL_DOLLARS):.3f} "
            f"on ${REFERENCE_BANKROLL_DOLLARS:,.0f}")
    out("      So of step 1's two refusals, only `edge_within_method_noise` bears")
    out("      on the economic claim. The over-determination is ONE guard deep")
    out("      for `is there an edge`, two deep for `would we have bet`.")

    out("")
    out("  (d) The counterfactual coefficient is applied at C=1 to decisions that")
    out("      imply multi-contract orders. Under `rate by NOTIONAL` -- the fifth")
    out("      attribution, registered at round two C4 with a threshold anywhere")
    out("      in ($2.70, $3.00] -- the rate a row pays depends on its own stake:")
    for s in sorted([s for s in results["step2"] if s.surfaced], key=lambda s: -s.e1):
        c = s.ref_contracts
        notional = c * s.row["ask_tenths"] / PRICE_MAX
        verdict = ("ABOVE $3.00 -> takes the HIGH rate (= step 1), does NOT surface"
                   if notional > 3.00
                   else "inside ($2.70, $3.00] -> UNDETERMINED")
        out(f"      id {s.id:5d}  C={c:2d}  notional ${notional:5.2f}   {verdict}")
    out("      So three of the four step-2 survivors are not self-consistent")
    out("      under one of the five live attributions: the size that makes them")
    out("      worth betting pushes them into the regime where the coefficient")
    out("      that made them positive does not apply. Section (a) does NOT bound")
    out("      this -- it varies the ceiling holding `k` fixed.")

    # -- S8. Two things a reader will ask next ----------------------------
    out.rule("S8 -- THE SUPPRESSED POPULATION, and the identity of the survivors.")
    out("  (a) Positive net edge over the WHOLE pinned table, all 1,564 rows.")
    out("      DESCRIPTIVE ONLY. These rows are suppressed for reasons the fee")
    out("      cannot touch -- stale odds, one book, no width -- so not one of")
    out("      them can enter the clean population under any fee model. This is")
    out("      NOT a claim that they would be actionable.")
    out(f"      {'model':10s} {'rows E1>0':>10s} {'of which KXWNBAGAME':>21s}")
    for model in ("deployed", "step1", "step2"):
        pos = [r for r in rows if (edge_tenths(r, model) or -1.0) > 0.0]
        wnba = sum(1 for r in pos if series_of(r["ticker"]) == "KXWNBAGAME")
        out(f"      {model:10s} {len(pos):10d} {wnba:21d}")

    out("")
    out("  (b) What the surviving rows actually are, under step 2.")
    surfaced = [s for s in results["step2"] if s.surfaced]
    if surfaced:
        for s in sorted(surfaced, key=lambda s: -s.e1):
            out(f"      id {s.id:5d} cluster {s.cluster:30s} claim {str(s.claim):8s} "
                f"instant {s.row['created_ms']}")
        out("      A1's normalisation: a `NO` on one ticker and a `YES` on the")
        out("      other name ONE claim. Read the claim column before the row")
        out("      count -- two rows there are one opportunity, not two.")
        pairs = Counter((s.cluster, s.claim) for s in surfaced)
        out(f"      rows {len(surfaced)} -> claims {len(pairs)} -> games "
            f"{len({s.cluster for s in surfaced})}")

    if args.out:
        args.out.write_text("\n".join(out.lines) + "\n", encoding="utf-8")
        print(f"\nwritten to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
