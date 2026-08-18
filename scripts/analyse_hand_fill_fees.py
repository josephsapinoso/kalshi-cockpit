"""The hand-fill fee calibration: the registered producer, and nothing else.

Implements `docs/measurements/2026-08-18-preregistration-hand-fill-fee-
calibration.md` verbatim. The registration governs: if this script and that
document disagree, this script is wrong. Output order, cuts, exclusions,
sharpness classes, the OLD/NEW split, the six frozen candidate models and the
decision branches are all fixed there, before any value file was opened.

Read-only. No network, no database, no credential. Reads exactly two files:

    data/captures/portfolio_fills.json
    data/captures/portfolio_settlements.json

Both gitignored (a real account's history; this repo publishes on push). The
output prints series prefixes, counts, prices, fees and dates only -- no
fill_id, order_id, trade_id, subaccount_number, user_id, and no ticker suffix
identifying a position's side -- so it is safe to paste into the record.

WHAT THIS ESTABLISHES, AND WHAT IT DOES NOT
--------------------------------------------
Establishes: whether each captured charge matches the deployed model exactly
(C1/C1b); whether the out-of-sample fills admit the previously measured
coefficients (C2/C3); whether any settlement charged more than its fills (C4,
the design's one-sided power against H4); and the registered decomposition of
the pooled realised fee rate (C5).

Does NOT establish: maker fees, sells, combos, durability past this 8-day
window, which attribute carries the rate split, H4 in the confirming
direction, or anything about edge or P&L. Registration §11 is the full list
and the result document must carry it.

One caveat the skeptic's audit added (2026-08-18) and which overturns the
naive reading of §6: **the per-position falsifier is a one-sided upper-bound
identity** -- `fee = ceil(k_true·D)` implies `fee/stake <= k·(1-P) + slack`
for ANY assigned `k >= k_true`, so the falsifier cannot fire for a row whose
coefficient was assigned too HIGH. Its only non-vacuous content is rows
tested against the LOWER coefficient. The §6 evidence that actually
discriminates is the mix-implied coefficient agreeing with `k_required`,
printed below; the falsifier count alone proves nothing.

Exact Decimal throughout. `0.07*20*0.15*0.85` in binary floats ceils to a
false residual that reads as a novel schedule -- that already happened once
(round-three §S12b) and is why no float touches money here.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FILLS = REPO / "data" / "captures" / "portfolio_fills.json"
SETTLEMENTS = REPO / "data" / "captures" / "portfolio_settlements.json"

sys.path.insert(0, str(REPO))

GRID = Decimal("0.0001")
CENT = Decimal("0.01")
ONE = Decimal(1)

# §3: the OLD/NEW boundary is a RULE; the count 13 checks the rule.
SPLIT_ISO = "2026-08-14T23:59:59"
EXPECTED_OLD = 13

# §4.2: sharpness classes, fixed before the look.
SHARP_WIDTH = Decimal("0.0035")      # 10% of 0.035
DEGENERATE_WIDTH = Decimal("0.035")  # interval spans both candidates

K_LOW = Decimal("0.035")
K_HIGH = Decimal("0.070")


def series_of(ticker: str) -> str:
    return ticker.split("-")[0]


def model_deployed(c: Decimal, p: Decimal) -> Decimal:
    """§4.4: exact-Decimal reimplementation of `fees._model_a`, taker branch.

    Reimplemented rather than imported because the deployed entry point takes
    an integer count and the capture contains fractional ones -- that gap is
    side-check D1, reported separately, not silently papered over here.
    """
    return (K_HIGH * c * p * (ONE - p)).quantize(GRID, rounding=ROUND_CEILING)


def per_order(k, c, p, q, rounding):
    return (k * c * p * (ONE - p)).quantize(q, rounding=rounding)


def per_contract(k, c, p, q, rounding):
    return c * (k * p * (ONE - p)).quantize(q, rounding=rounding)


# §8: the candidate set, frozen at these six. No seventh may be added.
MODELS = {
    "k035 order ceil 1e-4": (K_LOW, per_order, GRID, ROUND_CEILING),
    "k070 order ceil 1e-4": (K_HIGH, per_order, GRID, ROUND_CEILING),
    "k035 contract ceil 1e-4": (K_LOW, per_contract, GRID, ROUND_CEILING),
    "k070 contract ceil 1e-4": (K_HIGH, per_contract, GRID, ROUND_CEILING),
    "k035 order half-up 1e-4": (K_LOW, per_order, GRID, ROUND_HALF_UP),
    "k070 order ceil CENT": (K_HIGH, per_order, CENT, ROUND_CEILING),
}


def load(path: Path, key: str) -> list[dict]:
    if not path.exists():
        sys.exit(f"missing {path}; regenerate with scripts/capture_fills_fixture.py")
    return json.loads(path.read_text())["payload"][key]


def side_price(f: dict) -> Decimal:
    """§4.1: the price of the side actually taken, from its own dollar string."""
    side = f.get("side")
    key = "yes_price_dollars" if side == "yes" else "no_price_dollars"
    return Decimal(f[key])


def interval(fee: Decimal, d: Decimal) -> tuple[Decimal, Decimal]:
    """§4.2: admissible k in ((fee - grid)/D, fee/D], half-open."""
    return (fee - GRID) / d, fee / d


def contains(lo: Decimal, hi: Decimal, k: Decimal) -> bool:
    return lo < k <= hi


def main() -> int:
    fills = sorted(load(FILLS, "fills"), key=lambda f: f["ts"])
    settlements = load(SETTLEMENTS, "settlements")

    print("HAND-FILL FEE CALIBRATION -- one look at the frozen capture")
    print("registration: docs/measurements/"
          "2026-08-18-preregistration-hand-fill-fee-calibration.md")
    print()

    # -- §3 population, exclusions, and the split guard ---------------------
    makers = [f for f in fills if not f.get("is_taker")]
    sells = [f for f in fills if f.get("action") == "sell"]
    if sells:
        print(f"STOP-AND-REPORT: {len(sells)} sell fill(s) observed. The sell")
        print("wire shape is unverified (A4); these are excluded from every")
        print("entry-fee claim and the capture should be preserved for a")
        print("fresh registration.")
    population = [
        f for f in fills if f.get("is_taker") and f.get("action") != "sell"
    ]

    old = [f for f in population if f["created_time"][:19] <= SPLIT_ISO]
    new = [f for f in population if f["created_time"][:19] > SPLIT_ISO]
    print(f"fills captured: {len(fills)}   takers, buys (population): "
          f"{len(population)}   makers: {len(makers)}   sells: {len(sells)}")
    print(f"OLD (<= 2026-08-14): {len(old)}   NEW (> 2026-08-14): {len(new)}")
    if len(old) != EXPECTED_OLD:
        print(f"\nGUARD FIRED: OLD count is {len(old)}, registered expectation "
              f"is {EXPECTED_OLD}. STOPPING before any classification (§3).")
        return 1

    # multi-fill orders: the group is the unit (§3). Counted here; ids never
    # printed.
    orders: dict[str, list[dict]] = {}
    for f in population:
        orders.setdefault(str(f.get("order_id")), []).append(f)
    multi = [g for g in orders.values() if len(g) > 1]
    print(f"orders: {len(orders)}   multi-fill orders: {len(multi)}")
    units: list[list[dict]] = list(orders.values())

    # -- §5: n before any effect size --------------------------------------
    by_series: dict[str, list[list[dict]]] = {}
    for group in units:
        by_series.setdefault(series_of(group[0]["ticker"]), []).append(group)
    print("\nrows per series (unit = order):")
    for ser, groups in sorted(by_series.items()):
        print(f"  {ser:<16} n={len(groups)}")

    total_fill_fees = sum(Decimal(f["fee_cost"]) for f in population)
    largest_fee = max(Decimal(f["fee_cost"]) for f in population)
    print(f"\nlargest single fill's share of total fill fees: "
          f"{largest_fee / total_fill_fees:.1%}  "
          f"(largest {largest_fee}, total {total_fill_fees})")

    # -- Q(a): C1 / C1b against the deployed model --------------------------
    print("\n" + "=" * 74)
    print("Q(a) -- charged fee vs DEPLOYED model "
          "(ceil to $0.0001 of 0.070*C*P*(1-P))")
    print("=" * 74)
    overcharged_by_venue = []   # C1 falsifiers: venue charged MORE than model
    mismatched = []             # C1b falsifiers: any difference
    tol = Decimal("1e-9")
    for group in units:
        fee = sum(Decimal(f["fee_cost"]) for f in group)
        d = sum(
            Decimal(f["count_fp"]) * side_price(f) * (ONE - side_price(f))
            for f in group
        )
        c = sum(Decimal(f["count_fp"]) for f in group)
        p = side_price(group[0])
        predicted = (K_HIGH * d).quantize(GRID, rounding=ROUND_CEILING)
        delta = fee - predicted
        if abs(delta) > tol:
            mismatched.append((group, fee, predicted))
        if delta > tol:
            overcharged_by_venue.append((group, fee, predicted))
        ser = series_of(group[0]["ticker"])
        print(f"  {group[0]['created_time'][:10]}  {ser:<16} C={c:<7} P={p:<7}"
              f" charged={fee:<9} deployed={predicted:<9} "
              f"{'MATCH' if abs(delta) <= tol else f'ratio {fee/predicted:.3f}x' if predicted else 'n/a'}")

    print()
    if overcharged_by_venue:
        print(f"C1 FALSIFIED -- STOP THE LINE: {len(overcharged_by_venue)} "
              f"fill(s) charged MORE than the deployed model predicts.")
    else:
        print("C1 holds: no fill was charged more than the deployed model.")
    if mismatched:
        print(f"C1b MISMATCHED on {len(mismatched)} of {len(units)} units "
              f"(deployed model is not exactly right).")
    else:
        print(f"C1b holds on {len(units)} of {len(units)}: deployed model "
              f"exactly right on this capture.")

    # -- D1 side-check: the deployed entry point vs fractional counts -------
    print("\nD1 side-check: `calculate_fee` takes an integer count; the capture")
    print("contains fractional counts. Behaviour when handed the observed values:")
    from backend.core.fees import calculate_fee
    from backend.core.prices import dollars_to_tenths
    fractional = [f for f in population if Decimal(f["count_fp"]) % 1 != 0]
    for f in fractional:
        c_frac = float(Decimal(f["count_fp"]))
        tenths = dollars_to_tenths(str(side_price(f)))
        as_given = calculate_fee(tenths, c_frac)  # duck-typed float
        as_int = calculate_fee(tenths, int(c_frac))
        print(f"  count={f['count_fp']:<7} calculate_fee(count)={as_given}   "
              f"calculate_fee(int(count))={as_int}   charged={f['fee_cost']}")
    if not fractional:
        print("  (no fractional-count fills in the population)")

    # -- Q(b): admissible-k intervals, sharpness, C2/C3 on NEW --------------
    print("\n" + "=" * 74)
    print("Q(b) -- per-unit admissible k (intervals, never points)")
    print("=" * 74)
    classified = []
    for group in units:
        fee = sum(Decimal(f["fee_cost"]) for f in group)
        d = sum(
            Decimal(f["count_fp"]) * side_price(f) * (ONE - side_price(f))
            for f in group
        )
        width = GRID / d
        if width >= DEGENERATE_WIDTH:
            klass = "DEGENERATE"
        elif width <= SHARP_WIDTH:
            klass = "SHARP"
        else:
            klass = "BLUNT"
        lo, hi = interval(fee, d)
        is_new = group[0]["created_time"][:19] > SPLIT_ISO
        classified.append((group, lo, hi, klass, is_new))
        ser = series_of(group[0]["ticker"])
        print(f"  {'NEW' if is_new else 'old'}  {ser:<16} {klass:<11}"
              f" k in ({lo:.7f}, {hi:.7f}]"
              f"  contains: 0.035={'Y' if contains(lo, hi, K_LOW) else 'N'}"
              f" 0.070={'Y' if contains(lo, hi, K_HIGH) else 'N'}")

    counts = {k: sum(1 for *_r, kl, _n in classified if kl == k)
              for k in ("SHARP", "BLUNT", "DEGENERATE")}
    print(f"\nsharpness: {counts}")

    def verdict(rows, k, label):
        rows = [r for r in rows if r[3] != "DEGENERATE"]
        if not rows:
            print(f"{label}: NOT TESTABLE (zero admissible new fills).")
            return
        misses = [r for r in rows if not contains(r[1], r[2], k)]
        sharp = [r for r in rows if r[3] == "SHARP"]
        sharp_misses = [r for r in sharp if not contains(r[1], r[2], k)]
        print(f"{label}: {len(rows) - len(misses)}/{len(rows)} intervals "
              f"contain {k}  (SHARP alone: "
              f"{len(sharp) - len(sharp_misses)}/{len(sharp)})")
        for group, lo, hi, klass, _ in misses:
            f0 = group[0]
            print(f"  MISS: {series_of(f0['ticker']):<16} {klass} "
                  f"C={f0['count_fp']} P={side_price(f0)} "
                  f"k in ({lo:.7f}, {hi:.7f}]")

    new_mlb = [r for r in classified if r[4]
               and series_of(r[0][0]["ticker"]).startswith("KXMLB")]
    new_other = [r for r in classified if r[4]
                 and not series_of(r[0][0]["ticker"]).startswith("KXMLB")]
    print()
    verdict(new_mlb, K_LOW, "C2 (NEW KXMLB* vs 0.035)")
    verdict(new_other, K_HIGH, "C3 (NEW non-KXMLB* vs 0.070)")
    novel = [r for r in classified
             if r[3] != "DEGENERATE"
             and not contains(r[1], r[2], K_LOW)
             and not contains(r[1], r[2], K_HIGH)]
    print(f"intervals containing NEITHER coefficient: {len(novel)}"
          + ("  -> NOVEL / UNEXPLAINED (no seventh model is fitted here)"
             if novel else ""))

    # frozen six-model match table, per unit, reported not re-tested
    print("\nfrozen candidate models -- matches per model over the population:")
    for name, (k, fn, q, rounding) in MODELS.items():
        hits = 0
        for group in classified:
            fee = sum(Decimal(f["fee_cost"]) for f in group[0])
            v = sum(
                fn(k, Decimal(f["count_fp"]), side_price(f), q, rounding)
                for f in group[0]
            )
            if v == fee:
                hits += 1
        print(f"  {name:<26} {hits}/{len(classified)}")

    # per-series intervals and derived clusters (§4.3)
    print("\nper-series admissible k (SINGLETON = one unit, no cluster claim):")
    per_series: dict[str, tuple[Decimal, Decimal, int]] = {}
    for ser, groups in sorted(by_series.items()):
        lo, hi = Decimal(0), Decimal(10)
        for group in groups:
            fee = sum(Decimal(f["fee_cost"]) for f in group)
            d = sum(
                Decimal(f["count_fp"]) * side_price(f) * (ONE - side_price(f))
                for f in group
            )
            glo, ghi = interval(fee, d)
            lo, hi = max(lo, glo), min(hi, ghi)
        per_series[ser] = (lo, hi, len(groups))
        tag = "SINGLETON" if len(groups) == 1 else f"n={len(groups)}"
        inverted = "  ** INVERTED -- mixed rates inside the series **" if lo > hi else ""
        print(f"  {ser:<16} {tag:<10} k in ({lo:.7f}, {hi:.7f}]{inverted}")

    clusters: list[list[str]] = []
    for ser, (lo, hi, _) in sorted(per_series.items(), key=lambda kv: kv[1][0]):
        for group in clusters:
            glo = max(per_series[s][0] for s in group)
            ghi = min(per_series[s][1] for s in group)
            if lo <= ghi and hi >= glo:
                group.append(ser)
                break
        else:
            clusters.append([ser])
    print(f"clusters: {len(clusters)}")
    for group in clusters:
        lo = max(per_series[s][0] for s in group)
        hi = min(per_series[s][1] for s in group)
        n = sum(per_series[s][2] for s in group)
        print(f"  k in ({lo:.7f}, {hi:.7f}]  n={n}  {', '.join(group)}")

    # §5.4 attribution: two series inside one sport disagreeing?
    print("\n§5.4 attribution: which attribute carries the split is decided by")
    print("the table above only if two series INSIDE one sport land in")
    print("different clusters; otherwise NOT SEPARATED BY THIS DESIGN.")

    # -- Q(c): C4, settlements vs summed fill fees --------------------------
    print("\n" + "=" * 74)
    print("Q(c) -- settlement fee_cost vs summed fill fees (one-sided H4 power)")
    print("=" * 74)
    summed: dict[str, Decimal] = {}
    for f in fills:
        summed[f["ticker"]] = (
            summed.get(f["ticker"], Decimal(0)) + Decimal(f["fee_cost"])
        )
    greater = equal = differ_less = uncompared = 0
    for s in sorted(settlements, key=lambda r: r["settled_time"]):
        if s["ticker"] not in summed:
            uncompared += 1
            continue
        sf, ff = Decimal(s["fee_cost"]), summed[s["ticker"]]
        if sf > ff:
            greater += 1
            print(f"  C4 FALSIFIER: {series_of(s['ticker']):<16} "
                  f"settlement={sf} > fills={ff}")
        elif sf == ff:
            equal += 1
        else:
            differ_less += 1
            print(f"  note: {series_of(s['ticker']):<16} settlement={sf} "
                  f"< fills={ff}")
    print(f"\ncompared: {greater + equal + differ_less}   equal: {equal}   "
          f"settlement>fills: {greater}   settlement<fills: {differ_less}   "
          f"no fills captured: {uncompared}")
    if greater:
        print("C4 REFUTED: settlement is not free. ADR 0027's worst branch.")
    else:
        print("C4: no settlement charged more than its fills. Registered in")
        print("advance as NON-DISCRIMINATING for H4 -- may NOT be written as")
        print("'H4 closed' or 'settlement appears free'.")

    # -- §6: the 4.03% decomposition, in the registered print order ---------
    print("\n" + "=" * 74)
    print("§6 -- pooled realised fee rate, decomposed (settlement rows)")
    print("=" * 74)
    rows = []
    two_sided = 0
    unreadable = 0
    for s in settlements:
        yc, nc = Decimal(s.get("yes_count_fp") or 0), Decimal(s.get("no_count_fp") or 0)
        if yc > 0 and nc > 0:
            two_sided += 1
            continue
        if yc > 0:
            stake_str, count = s.get("yes_total_cost_dollars"), yc
        elif nc > 0:
            stake_str, count = s.get("no_total_cost_dollars"), nc
        else:
            unreadable += 1
            continue
        if stake_str is None:
            unreadable += 1
            continue
        stake = Decimal(stake_str)
        if stake <= 0 or count <= 0:
            unreadable += 1
            continue
        price = stake / count
        rows.append((series_of(s["ticker"]), stake, price,
                     Decimal(s["fee_cost"])))
    print(f"n = {len(rows)}   two-sided (excluded, counted): {two_sided}   "
          f"unreadable (excluded, counted): {unreadable}")
    if rows:
        total_fee = sum(r[3] for r in rows)
        total_stake = sum(r[1] for r in rows)
        largest = max(rows, key=lambda r: r[3])
        print(f"largest contributor's share of fees: "
              f"{largest[3] / total_fee:.1%} ({largest[0]}, fee {largest[3]})")
        print("stake-weighted price distribution (per position):")
        for ser, stake, price, fee in sorted(rows, key=lambda r: r[2]):
            print(f"  {ser:<16} P={price:.4f}  stake={stake:<9} fee={fee}")
        wmean_1mp = sum(r[1] * (ONE - r[2]) for r in rows) / total_stake
        n_slack = len(rows) * GRID / total_stake
        print(f"weightedmean(1-P) = {wmean_1mp:.4f}")
        k_required = (total_fee / total_stake - n_slack) / wmean_1mp
        print(f"k_required = {k_required:.4f}")
        print(f"rate = {total_fee / total_stake:.4%}")

        # The discriminating statistic (added post-look at the skeptic's
        # direction, R2 of the audit -- a summary of already-printed rows, no
        # new cut and no new model): the coefficient the observed MIX implies,
        # weighted by each position's stake*(1-P) -- the exact weight in the
        # k_required identity. Assignment is the asserted PREFIX rule
        # (KXMLB* -> 0.035, else 0.070), which on this capture coincides with
        # the derived clusters.
        w_total = sum(r[1] * (ONE - r[2]) for r in rows)
        w_mlb = sum(r[1] * (ONE - r[2]) for r in rows if r[0].startswith("KXMLB"))
        mix_k = (K_LOW * w_mlb + K_HIGH * (w_total - w_mlb)) / w_total
        stake_mlb = sum(r[1] for r in rows if r[0].startswith("KXMLB"))
        fee_mlb = sum(r[3] for r in rows if r[0].startswith("KXMLB"))
        print(f"mix-implied coefficient (stake*(1-P)-weighted, prefix rule) = "
              f"{mix_k:.4f}")
        print(f"baseball shares: {stake_mlb / total_stake:.2%} of stake, "
              f"{fee_mlb / total_fee:.2%} of fees, "
              f"{w_mlb / w_total:.2%} of stake*(1-P), "
              f"{sum(1 for r in rows if r[0].startswith('KXMLB'))} of "
              f"{len(rows)} positions")

        print("\nper-position falsifiers (fee/stake > k(1-P) + slack, at the")
        print("coefficient the PREFIX RULE assigns to the series). CAVEAT:")
        print("this is a one-sided identity -- it cannot fire for a row whose")
        print("coefficient was assigned too high; see the module docstring.")
        fired = 0
        for ser, stake, price, fee in rows:
            k = K_LOW if ser.startswith("KXMLB") else K_HIGH
            bound = k * (ONE - price) + GRID / stake
            if fee / stake > bound:
                fired += 1
                print(f"  {ser:<16} fee/stake={fee / stake:.4%} > "
                      f"bound={bound:.4%}  (P={price:.4f})")
        if not fired:
            print("  none -- C5 holds: the rate is fully accounted for by")
            print("  k(1-P) at the assigned coefficients plus ceil slack.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
