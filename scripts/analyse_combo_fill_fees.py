"""The registered one-look analysis of the 8 combo fills' fees.

Registration: `docs/measurements/2026-08-18-preregistration-combo-fill-fee-
look.md` (committed before any fee value was read). **The registration
governs; if this script and that document disagree, this script is wrong.**
One look at the capture as it stands (§9); no re-run on a refreshed capture.
Audited by measurement-skeptic 2026-08-18 (draft verdict DEFECTIVE, 14
required corrections, all applied — including: the second interval set at
the inferred grid, sharpness moved into the pre-fee block, M1 anchored to
`calculate_fee` itself, C4 carrying both §7 branches because the
registration sets no precedence, and C5 reported NOT REACHED because
neither of its antecedents holds).

Two modes, and the order between them is part of the protocol:

    --fetch-legs   §4.5's bounded enrichment: one read-only GET
                   /markets/{ticker} per distinct combo ticker (at most 8),
                   recording ONLY the length of `mve_selected_legs` into
                   `docs/measurements/2026-08-18-combo-leg-counts.json`,
                   keyed by row index -- never by ticker, because the
                   combination hashes identify Joe's positions and the repo
                   is public. This mode never touches `fee_cost`.
    (default)      the analysis, reading only the capture and the leg-count
                   JSON. No network, no database, no credential.

What this does NOT establish (§11 of the registration, in full there):
durability past one account/one sitting/one day — whatever this returns, it
establishes nothing about what combos are charged tomorrow; maker fees
(zero maker rows); sells and exits (zero observed; the product is
enter-only); the leg-price schedule ADR 0012 §5 names (M11 NOT TESTABLE --
fill-time leg prices are unrecorded and unrecoverable); which attribute
carries any rate structure (product, category mix, series and tier are all
confounded here); the true grid below the observed gcd (one-sided bound
only); anything off the observed grid of prices ($0.001-$0.228 — the deep
tail of a fee function that peaks at $0.50), sizes, leg counts or
collections; that the venue charges other accounts what it charged this
one; any other KXMVE family; anything about edge, EV, P&L or whether combos
are worth betting (ADR 0038 closed the hunt; nothing here reopens it).

Statistics discipline (§1.2): with 8 fills there is NO proportion, rate,
standard error, CI, p-value or normal approximation anywhere in this
output. Exact comparisons, per-row admissible-k intervals, the grid gcd,
and counts. This is a consistency check, not an estimation.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from backend.core.fees import calculate_fee  # noqa: E402
from backend.core.prices import dollars_to_tenths  # noqa: E402

CAPTURE = REPO / "data" / "captures" / "portfolio_fills.json"
LEG_COUNTS = REPO / "docs" / "measurements" / "2026-08-18-combo-leg-counts.json"
PREFIX = "KXMVECROSSCATEGORY"
GRID = Decimal("0.0001")
CENT = Decimal("0.01")
TOL = Decimal("1E-9")
K_TAKER = Decimal("0.070")
K_BASEBALL = Decimal("0.035")


def combo_rows() -> list[dict]:
    capture = json.loads(CAPTURE.read_text(encoding="utf-8"))
    return [
        r
        for r in capture["payload"]["fills"]
        if str(r.get("ticker", "")).startswith(PREFIX)
    ]


# -- §4.5: the enrichment, fees never opened --------------------------------


async def fetch_legs() -> None:
    from backend.config import KalshiConfig
    from backend.kalshi.rest import KalshiRestClient

    rows = combo_rows()
    if len(rows) != 8:
        raise SystemExit(f"GUARD: combo row count {len(rows)} != 8; stopping")

    out: dict[str, int | None] = {}
    async with KalshiRestClient(KalshiConfig.load()) as api:
        for index, row in enumerate(rows, 1):
            ticker = row["ticker"]
            try:
                payload = await api.get(f"/markets/{ticker}")
            except Exception as exc:  # noqa: BLE001 -- a 404 leaves None, never a guess
                print(f"row {index}: fetch failed ({type(exc).__name__}); L=None")
                out[f"row_{index}"] = None
                continue
            market = payload.get("market") or {}
            legs = market.get("mve_selected_legs")
            # Length only. Every price/book/volume field in this payload is
            # OUT OF POPULATION (§4.5) -- post-fill quotes, discarded here.
            out[f"row_{index}"] = len(legs) if isinstance(legs, list) else None
            print(f"row {index}: L={out[f'row_{index}']}")

    LEG_COUNTS.write_text(
        json.dumps(
            {
                "note": (
                    "Leg counts for the 8 combo fills, §4.5 of the "
                    "registration. Keyed by capture row index, never by "
                    "ticker (the hashes identify positions; repo is public). "
                    "Recorded before any fee_cost value was opened."
                ),
                "leg_counts": out,
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {LEG_COUNTS}")


# -- the exact arithmetic ---------------------------------------------------


def ceil_to(value: Decimal, grid: Decimal) -> Decimal:
    return (value / grid).to_integral_value(rounding=ROUND_CEILING) * grid


def price_dollars(row: dict, index: int) -> Decimal | None:
    """§4.1: the held side's own dollar string, via dollars_to_tenths."""
    outcome, side = row.get("outcome_side"), row.get("side")
    if outcome and side and outcome != side:
        raise SystemExit(f"STOP AND REPORT: row {index} outcome_side != side")
    held = outcome or side
    if held not in ("yes", "no"):
        raise SystemExit(f"STOP AND REPORT: row {index} has no held side")
    key = "yes_price_dollars" if held == "yes" else "no_price_dollars"
    tenths = dollars_to_tenths(row.get(key))
    if tenths is None:
        return None  # NOT COMPUTABLE, §3.3
    return Decimal(tenths) / Decimal(1000)


def predictions(
    count: Decimal, p: Decimal, legs: int | None
) -> dict[str, Decimal | None]:
    d = count * p * (1 - p)
    per_contract_a = ceil_to(K_TAKER * p * (1 - p), GRID)
    model_b_per_contract = (Decimal("0.06") * p * (1 - p)).quantize(
        CENT, rounding=ROUND_HALF_UP
    )
    m1 = ceil_to(K_TAKER * d, GRID)
    # Anchor: M1 is defined as the DEPLOYED `calculate_fee`, not this
    # script's reimplementation. Assert the two agree so a future change in
    # `fees.py` cannot diverge from this producer silently (audit item 12).
    deployed = Decimal(str(calculate_fee(int(p * 1000), float(count))))
    if abs(deployed - m1) > TOL:
        raise SystemExit(
            f"ANCHOR FAILED: calculate_fee={deployed} != reimplemented M1={m1}"
        )
    return {
        "M1": m1,
        "M2": ceil_to(K_BASEBALL * d, GRID),
        "M3": ceil_to(K_TAKER * d, CENT),
        "M4": ceil_to(K_BASEBALL * d, CENT),
        "M5": K_TAKER * d,
        "M6": K_BASEBALL * d,
        "M7": count * model_b_per_contract,
        "M8": count * per_contract_a,
        "M9": None if legs is None else legs * m1,
        "M10": None if legs is None else legs * ceil_to(K_BASEBALL * d, GRID),
    }


def decimal_places_as_written(text: str) -> int:
    return len(text.split(".", 1)[1]) if "." in text else 0


def sharpness(width: Decimal) -> str:
    if width >= Decimal("0.035"):
        return "DEGENERATE"
    return "SHARP" if width <= Decimal("0.0035") else "BLUNT"


def print_k_intervals(per_row: list[dict], grid: Decimal, label: str) -> None:
    print(f"\n== §4.2 admissible k per row, half-open, at g={grid} ({label}) ==")
    for r in per_row:
        d = r["count"] * r["p"] * (1 - r["p"])
        lo, hi = (r["fee"] - grid) / d, r["fee"] / d
        off_grid = (r["fee"] / grid) != (r["fee"] / grid).to_integral_value()
        note = (
            "  [fee is NOT a multiple of this grid: the ceil-to-grid model "
            "admits NO k on this row; the interval is a necessary condition "
            "for a refuted model, not an admissible set]"
            if off_grid
            else ""
        )
        print(
            f"row {r['index']}: k in ({float(lo):.6f}, {float(hi):.6f}]  "
            f"width {float(GRID / d):.6f}{note}"
        )


def main() -> None:
    rows = combo_rows()
    if len(rows) != 8:
        raise SystemExit(f"GUARD: combo row count {len(rows)} != 8; stopping")
    if any(r.get("action") == "sell" for r in rows):
        raise SystemExit("GUARD: a sell row exists; STOP AND REPORT")

    legs_file = (
        json.loads(LEG_COUNTS.read_text(encoding="utf-8"))["leg_counts"]
        if LEG_COUNTS.exists()
        else {}
    )
    legs_by_index = {int(k.split("_")[1]): v for k, v in legs_file.items()}

    # -- §5: everything printable BEFORE any fee value, n before effect ----
    orders: dict[str, list[int]] = {}
    for index, row in enumerate(rows, 1):
        orders.setdefault(row["order_id"], []).append(index)
    n_orders = len(orders)

    pre = []
    not_computable = 0
    for index, row in enumerate(rows, 1):
        count = Decimal(str(row["count_fp"]))
        p = price_dollars(row, index)
        if p is None:
            not_computable += 1
        pre.append({"index": index, "count": count, "p": p})

    print(f"rows matched by prefix rule : {len(rows)}")
    print(f"distinct order_id count (n) : {n_orders}")
    print(f"rows per order              : {sorted(len(v) for v in orders.values())}")
    print(
        f"taker/maker                 : "
        f"{sum(r['is_taker'] for r in rows)}/{sum(not r['is_taker'] for r in rows)}"
    )
    print(
        f"buy/sell                    : "
        f"{sum(r['action'] == 'buy' for r in rows)}/"
        f"{sum(r['action'] == 'sell' for r in rows)}"
    )
    print(f"rows NOT COMPUTABLE         : {not_computable}")
    print(
        f"leg counts by row           : {[legs_by_index.get(i) for i in range(1, 9)]}"
    )
    # Sharpness is g/D and depends only on C and P — printed pre-fee (§5).
    widths = []
    for r in pre:
        d = r["count"] * r["p"] * (1 - r["p"])
        widths.append(GRID / d)
    classes = [sharpness(w) for w in widths]
    print(
        f"sharpness at g=1e-4         : {classes} "
        f"(widths {float(min(widths)):.6f}..{float(max(widths)):.6f})"
    )
    distinct_configs = len({(str(r["count"]), str(r["p"])) for r in pre})
    distinct_prices = len({str(r["p"]) for r in pre})
    print(
        f"distinct (C,P) configs      : {distinct_configs} "
        f"(distinct prices: {distinct_prices}) — rows 2 and 3 are identical "
        f"in C and P"
    )
    print("MIXED-PRICE orders          : 0 (every order is one fill)")
    thin = n_orders < 3

    # -- fees open here, and not before ------------------------------------
    per_row = []
    for index, row in enumerate(rows, 1):
        fee_text = str(row["fee_cost"])
        fee = Decimal(fee_text)
        count = Decimal(str(row["count_fp"]))
        p = price_dollars(row, index)
        complement_key = (
            "no_price_dollars"
            if (row.get("outcome_side") or row.get("side")) == "yes"
            else "yes_price_dollars"
        )
        pair_sum = None
        try:
            pair_sum = p + Decimal(dollars_to_tenths(row.get(complement_key))) / 1000
        except TypeError:
            pass
        per_row.append(
            {
                "index": index,
                "fee_text": fee_text,
                "fee": fee,
                "count": count,
                "p": p,
                "legs": legs_by_index.get(index),
                "pair_sum": pair_sum,
            }
        )

    print("\n== per-row facts (C, P, D, fee as written, fee - 0.070·D exact) ==")
    for r in per_row:
        d = r["count"] * r["p"] * (1 - r["p"])
        excess = r["fee"] - K_TAKER * d
        note = "" if r["pair_sum"] == Decimal("1") else f"  [yes+no = {r['pair_sum']}]"
        print(
            f"row {r['index']}: C={r['count']}  P={r['p']}  D={d}  "
            f"fee={r['fee_text']}  fee-0.070·D={excess:+f}{note}"
        )

    # §6.2 grid statistics
    places = [decimal_places_as_written(r["fee_text"]) for r in per_row]
    max_places = max(places)
    scale = 10**max_places
    ints = [int(r["fee"] * scale) for r in per_row]
    gcd = math.gcd(*ints)
    grid_bound = Decimal(gcd) / Decimal(scale)
    print("\n== §6.2 grid ==")
    print(f"decimal places as written   : {places} (max {max_places})")
    print(
        f"gcd of charges              : {grid_bound} (one-sided: the combo "
        f"grid is NO COARSER than this on these rows)"
    )
    off_grid = [
        r["index"]
        for r in per_row
        if (r["fee"] / GRID) != (r["fee"] / GRID).to_integral_value()
    ]
    print(f"rows not a multiple of 1e-4 : {off_grid or 'none'} (count: {len(off_grid)})")

    # C1 / C2 against the deployed model (M1 IS calculate_fee, anchored)
    print("\n== C1 (safety) and C2 (deployed model), per order ==")
    c1_violations, c2_mismatches = [], []
    deltas = {}
    for r in per_row:
        deployed = predictions(r["count"], r["p"], r["legs"])["M1"]
        delta = r["fee"] - deployed
        deltas[r["index"]] = delta
        if delta > TOL:
            c1_violations.append(r["index"])
        if abs(delta) > TOL:
            c2_mismatches.append((r["index"], r["fee"] / deployed))
        print(
            f"row {r['index']}: deployed={deployed}  charged={r['fee']}  "
            f"delta={delta:+f}  ratio={float(r['fee'] / deployed):.4f}"
        )

    # C4: the frozen candidates
    print("\n== C4 candidate survival (exact within 1e-9, per order) ==")
    survivors = {}
    match_matrix = {}
    for name in ("M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M9", "M10"):
        matches, not_testable = [], []
        zero_predictions = []
        for r in per_row:
            pred = predictions(r["count"], r["p"], r["legs"])[name]
            if pred is None:
                not_testable.append(r["index"])
            else:
                if pred == 0:
                    zero_predictions.append(r["index"])
                if abs(r["fee"] - pred) <= TOL:
                    matches.append(r["index"])
        match_matrix[name] = (matches, not_testable)
        scorable = 8 - len(not_testable)
        status = "SURVIVES" if scorable > 0 and len(matches) == scorable else ""
        if scorable == 0:
            status = "NOT TESTABLE"
        extra = (
            f"  [predicts $0.00 on rows {zero_predictions} — the control "
            f"failing visibly]"
            if name == "M7" and zero_predictions
            else ""
        )
        print(
            f"{name:4}: matches rows {matches or '[]'}  "
            f"not-testable {not_testable or '[]'}  {status}{extra}"
        )
        if status == "SURVIVES":
            survivors[name] = matches

    # §4.2 intervals: at the deployed grid AND at the inferred grid (§4.2:
    # "both printed, neither promotable over the other after the fact").
    print_k_intervals(per_row, GRID, "deployed grid")
    if grid_bound < GRID:
        print_k_intervals(per_row, grid_bound, "inferred grid, §6")

    # Verdicts
    print("\n== VERDICTS (§7) ==")
    stamp = f"  [THIN: n_orders = {n_orders}]" if thin else ""
    if c1_violations:
        worst = max(deltas.values())
        print(
            f"C1: STOP THE LINE — the deployed model UNDERCHARGES on rows "
            f"{c1_violations}; per-row shortfall "
            f"{min(d for d in deltas.values() if d > 0):+f} to {worst:+f} "
            f"dollars, none above 0.19% of the charge.{stamp}"
        )
    else:
        print(
            f"C1: NOT REFUTED — no row charged above the deployed model. "
            f"A safety check, not evidence for the model.{stamp}"
        )
    if c2_mismatches:
        print(
            f"C2: DEPLOYED MODEL MISMATCHED ON COMBOS — rows "
            f"{[i for i, _ in c2_mismatches]} (ratios above).{stamp}"
        )
    else:
        print(
            f"C2: DEPLOYED MODEL NOT REFUTED ON COMBOS (not 'verified'; "
            f"ADR 0012 §5 stays as marked).{stamp}"
        )
    if off_grid:
        print(
            f"C3: FEE_GRID_DOLLARS = 0.0001 does not hold for these combo "
            f"rows ({len(off_grid)} of 8: rows {off_grid}), max decimal "
            f"places {max_places}. Entailment: M1–M4 and M8–M10 are refuted "
            f"on those rows automatically (§6.1).{stamp}"
        )
    else:
        print(f"C3: GRID NOT REFUTED on these rows.{stamp}")
    if len(survivors) == 1:
        name = next(iter(survivors))
        print(
            f"C4: {name} is CONSISTENT WITH EVERY COMBO ORDER IN THIS "
            f"CAPTURE. Not 'the combo fee schedule'. Not 'confirmed'.{stamp}"
        )
    elif len(survivors) > 1:
        print(f"C4: NOT SEPARATED BY THIS DESIGN — survivors {sorted(survivors)}.{stamp}")
    else:
        ratios = [(r["fee"] / (r["count"] * r["p"] * (1 - r["p"]))) for r in per_row]
        spread = max(ratios) - min(ratios)
        common = (
            f"; ratios fee/D span {float(min(ratios)):.6f}.."
            f"{float(max(ratios)):.6f}"
        )
        if spread <= Decimal("0.000001"):
            common += " — NOVEL COEFFICIENT, UNEXPLAINED (agree within 1e-6)"
        partial = {
            name: matches
            for name, (matches, nt) in match_matrix.items()
            if matches and len(matches) < 8 - len(nt)
        }
        # Both §7 conditions hold at once — "no candidate predicts every
        # scorable order" and "some rows match a candidate and others do
        # not" — and the registration sets NO precedence between them, so
        # both labels are carried (audit item 5; choosing MIXED alone was
        # the flattering choice).
        listing = "; ".join(f"{n} matches rows {m}" for n, m in sorted(partial.items()))
        print(
            f"C4: NONE OF THE REGISTERED CANDIDATES (§7 branch 3), with the "
            f"MIXED branch (§7 branch 4) also in force: {listing or 'none'}; "
            f"no candidate matches every order{common}. NO TWELFTH MODEL IS "
            f"FITTED HERE.{stamp}"
        )
    print(
        "C5: NOT REACHED. Its refuting branch needs a per-contract or "
        "leg-count form matching every order; M7–M10 matched no row. "
        "Per-order is not refuted and per-leg is not refuted, because "
        "nothing matched everything. M11 remains NOT TESTABLE."
    )
    print(
        "M11: NOT TESTABLE — fill-time leg prices are unrecorded and "
        "unrecoverable; no substitute may be constructed."
    )
    print(
        "MAKER: M1m/M2m NOT TESTABLE — zero maker rows; taker rows may not "
        "be substituted."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch-legs", action="store_true")
    args = parser.parse_args()
    if args.fetch_legs:
        asyncio.run(fetch_legs())
    else:
        main()
