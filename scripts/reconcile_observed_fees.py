"""Reconcile every observed Kalshi fee on this account against candidate models.

Re-derives, from the captured payloads and nothing else, the figures that
`docs/measurements/2026-08-14-fee-rate-attribution-round-three-result.md`
reports. It exists because the first version of that document printed a
reconciliation table with **no committed producer** and a cross-reference to a
section that did not exist -- a table with no provenance is a hand-constructed
payload wearing a measurement's name.

Read-only. Touches no network, no database, no credential. It reads two files:

    data/captures/portfolio_fills.json         (13 taker fills)
    data/captures/portfolio_settlements.json   (59 settled positions)

Both are **gitignored** -- they carry a `user_id` and this account's trading
history, and `kalshi-cockpit` publishes on push. Regenerate them with
`scripts/capture_fills_fixture.py`. This script prints only prices, counts,
series prefixes and fees; no ticker suffix identifying a position's side, no id
of any kind. Its output is safe to paste into the record.

WHY `Decimal` AND NOT FLOAT, STATED BECAUSE IT ALREADY BIT
-----------------------------------------------------------
`0.07 * 20 * 0.15 * 0.85` is exactly `0.1785`. In binary floats it evaluates to
`0.17850000000000002`, which `ceil`s to `0.1786` and turns an exact match into
an unexplained residual. The first pass of this analysis did exactly that and
reported the `KXATPDOUBLES` row as matching **no** candidate model -- which
reads as a novel fee schedule, the most interesting possible result, produced
entirely by the tool. See `tasks/lessons.md`, 2026-08-14.

WHAT THIS ESTABLISHES, AND WHAT IT DOES NOT
--------------------------------------------
**Establishes.** The functional form of the charged fee on the observations
present, the admissible coefficient interval per group, and that the deployed
`calculate_fee` disagrees with every one of them.

**Does NOT establish, and no output below may be read as any of these:**

1. **Which market attribute carries the rate split.** As of 2026-08-14 the
   clusters are 3 series each -- `KXMLBGAME`/`KXMLBSPREAD`/`KXMLBKS` low against
   `KXWNBAGAME`/`KXATPDOUBLES`/`KXPGATOUR` high -- so a per-series explanation
   now needs six independent lookups that happen to sort by sport, which is
   unparsimonious rather than refuted. A per-market liquidity tier is weakened
   too: the high group includes a 10,206-deep WNBA market and the low group a
   19,749-deep prop. **Neither is excluded.** The pre-registration's §10 forbids
   pooling across categories, so "non-baseball is 0.070" remains a claim about
   the three series observed, not about non-baseball.
2. **Durability.** Every `k = 0.035` observation lies inside **2026-08-10 to
   2026-08-14**. The settlement section below shows this account's own record
   changing granularity between 2026-02-09 and 2026-08-10, so the sports
   schedule was revised at least once in the preceding six months and a
   promotional or temporary rate is not excluded.
3. **Anything off the observed grid** -- maker fees, in-play fills, sizes
   between 2 and 19 or above 20, prices outside {13, 15, 27, 28, 48, 51, 52}c,
   any baseball series other than the three seen, or combos.
4. **H4.** Settlement `fee_cost` matching the summed fill fees is consistent
   with there being no settlement charge, and equally consistent with the field
   being entry-only and a settlement charge living elsewhere. Separating those
   needs the account balance. See ADR 0027.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FILLS = REPO / "data" / "captures" / "portfolio_fills.json"
SETTLEMENTS = REPO / "data" / "captures" / "portfolio_settlements.json"

DECI_CENT = Decimal("0.0001")
CENT = Decimal("0.01")

# **No hardcoded grouping.** An earlier version listed the two baseball series
# seen at the time; a third (`KXMLBKS`) then landed in "other" and the pooled
# interval came back INVERTED -- lo > hi -- which is the correct alarm for
# mixing two rates, but only after the list had already gone stale.
#
# Groups are now DERIVED: each series gets its own admissible interval, and
# series whose intervals overlap are clustered. That reports the split the data
# shows instead of the split a constant asserts, and it is why the sport/series
# question stays open in the output rather than being assumed away.


def series_of(ticker: str) -> str:
    return ticker.split("-")[0]


def raw(k: Decimal, contracts: Decimal, price: Decimal) -> Decimal:
    return k * contracts * price * (Decimal(1) - price)


def per_order(k, c, p, q, rounding):
    return raw(k, c, p).quantize(q, rounding=rounding)


def per_contract(k, c, p, q, rounding):
    return c * raw(k, Decimal(1), p).quantize(q, rounding=rounding)


MODELS = {
    "k035 order ceil 1e-4": (Decimal("0.035"), per_order, DECI_CENT, ROUND_CEILING),
    "k070 order ceil 1e-4": (Decimal("0.070"), per_order, DECI_CENT, ROUND_CEILING),
    "k035 contract ceil 1e-4": (Decimal("0.035"), per_contract, DECI_CENT, ROUND_CEILING),
    "k070 contract ceil 1e-4": (Decimal("0.070"), per_contract, DECI_CENT, ROUND_CEILING),
    "k035 order half-up 1e-4": (Decimal("0.035"), per_order, DECI_CENT, ROUND_HALF_UP),
    "k070 order ceil CENT": (Decimal("0.070"), per_order, CENT, ROUND_CEILING),
}


def load(path: Path, key: str) -> list[dict]:
    if not path.exists():
        sys.exit(
            f"missing {path}.\n"
            "Regenerate with: .venv\\Scripts\\python.exe scripts\\capture_fills_fixture.py"
        )
    return json.loads(path.read_text())["payload"][key]


def admissible_k(rows: list[tuple[Decimal, Decimal, Decimal]]) -> tuple[Decimal, Decimal]:
    """Intersect the per-observation intervals a ceiling charge admits.

    A charge `f` produced by `ceil(k*base)` to a grid of `g` means
    `f - g < k*base <= f`, so `k` lies in `((f-g)/base, f/base]`. Intersecting
    over observations is what turns a coefficient guess into an interval.
    """
    lo, hi = Decimal(0), Decimal(10)
    for contracts, price, fee in rows:
        base = contracts * price * (Decimal(1) - price)
        lo = max(lo, (fee - DECI_CENT) / base)
        hi = min(hi, fee / base)
    return lo, hi


def main() -> int:
    fills = sorted(load(FILLS, "fills"), key=lambda f: f["ts"])
    settlements = load(SETTLEMENTS, "settlements")

    print("=" * 78)
    print("FILLS -- charged fee vs candidate models")
    print("=" * 78)
    header = f"{'series':<14}{'n':>7}{'P':>7}{'charged':>10}  " + "".join(
        f"{name.split()[0] + '/' + name.split()[1][:3]:>13}" for name in MODELS
    )
    print(header)

    by_series: dict[str, list] = {}
    unexplained = 0
    for f in fills:
        c = Decimal(f["count_fp"])
        p = Decimal(f["yes_price_dollars"])
        actual = Decimal(f["fee_cost"])
        ser = series_of(f["ticker"])
        by_series.setdefault(ser, []).append((c, p, actual))

        cells = []
        matched = False
        for name, (k, fn, q, rounding) in MODELS.items():
            v = fn(k, c, p, q, rounding)
            if v == actual:
                matched = True
                cells.append("MATCH")
            else:
                cells.append(f"{v:.6f}")
        if not matched:
            unexplained += 1
        print(
            f"{ser.replace('KX', ''):<14}{c:>7}{p:>7}{actual:>10}  "
            + "".join(f"{x:>13}" for x in cells)
        )

    print(f"\nfills with no matching candidate: {unexplained} of {len(fills)}")

    print("\n" + "=" * 78)
    print("ADMISSIBLE COEFFICIENT, PER SERIES -- grouping derived, not assumed")
    print("=" * 78)
    per_series = {}
    for ser, rows in sorted(by_series.items()):
        lo, hi = admissible_k(rows)
        per_series[ser] = (lo, hi, len(rows))
        print(f"  {ser.replace('KX', ''):<14} n={len(rows):<3} "
              f"k in ({lo:.7f}, {hi:.7f}]")

    # Single-linkage clustering on the interval graph. With two well-separated
    # rates this is unambiguous, and a third rate would surface as a third
    # cluster rather than as an inverted pooled interval -- which is exactly
    # how the stale hardcoded grouping failed when `KXMLBKS` first landed.
    clusters: list[list[str]] = []
    for ser, (lo, hi, _) in sorted(per_series.items(), key=lambda kv: kv[1][0]):
        for group in clusters:
            glo = max(per_series[s2][0] for s2 in group)
            ghi = min(per_series[s2][1] for s2 in group)
            if lo <= ghi and hi >= glo:
                group.append(ser)
                break
        else:
            clusters.append([ser])

    print(f"\n  clusters found: {len(clusters)}")
    for group in clusters:
        lo = max(per_series[s2][0] for s2 in group)
        hi = min(per_series[s2][1] for s2 in group)
        n = sum(per_series[s2][2] for s2 in group)
        print(f"    k in ({lo:.7f}, {hi:.7f}]  n={n:<3} "
              f"{', '.join(s2.replace('KX', '') for s2 in group)}")

    rate_of = {s2: i for i, group in enumerate(clusters) for s2 in group}
    if len(clusters) == 2:
        ahi = min(per_series[s2][1] for s2 in clusters[0])
        blo = max(per_series[s2][0] for s2 in clusters[1])
        print(f"\n  disjoint: True   ratio floor: {blo / ahi:.3f}x")
    print("  WHICH ATTRIBUTE separates the clusters is NOT decided here.")
    print("  Sport, series and a per-market tier all fit. See ADR 0028.")

    print("\n" + "=" * 78)
    print("IS THE SPLIT A FUNCTION OF (count, price) ALONE?")
    print("=" * 78)
    print("If fee-per-contract is non-monotone in P(1-P), then NO shape, exponent,")
    print("size, price or notional model can fit all rows -- the split needs an")
    print("attribute outside (C, P). This is stronger than refuting three named")
    print("hypotheses one at a time.\n")
    pts = sorted(
        ((p * (Decimal(1) - p), fee / c, c, f"rate{rate_of[ser]}")
         for ser, rows in by_series.items() for c, p, fee in rows),
        key=lambda t: t[0],
    )
    for shape, per_c, c, grp in pts:
        print(f"  P(1-P)={shape:.6f}   fee/contract={per_c:.7f}   n={c:<6} {grp}")

    # Per-order rounding makes fee/contract jitter by up to one grid unit
    # divided by the count, so a bare "is it sorted" test flags rounding as
    # inversion. Only an inversion LARGER than that jitter is evidence.
    inversions = []
    for i, (sa, fa, ca, ga) in enumerate(pts):
        for sb, fb, cb, gb in pts[i + 1:]:
            if sb <= sa:
                continue
            slack = DECI_CENT / ca + DECI_CENT / cb
            if fa - fb > slack:
                inversions.append((sa, fa, ga, sb, fb, gb))

    print(f"\n  strict inversions (beyond per-order rounding slack): {len(inversions)}")
    for sa, fa, ga, sb, fb, gb in inversions:
        print(f"    P(1-P)={sa:.4f} charges {fa:.7f}/contract ({ga}) but the LARGER")
        print(f"    P(1-P)={sb:.4f} charges only {fb:.7f}/contract ({gb})")
    if inversions:
        print("\n  => fee-per-contract is NOT monotone in P(1-P), by more than rounding.")
        print("     No shape, exponent, size, price or notional model of (C, P) alone")
        print("     can fit these rows. The split requires an attribute outside (C, P).")
    else:
        print("\n  => no strict inversion; a (C, P) model is NOT excluded by this test.")

    print("\n" + "=" * 78)
    print("IS THE SPLIT TEMPORAL? -- interleaving of the rate clusters")
    print("=" * 78)
    for f in fills:
        ser = series_of(f["ticker"])
        print(f"  {f['ts']}  rate{rate_of[ser]}  {ser.replace('KX', '')}")
    seq = [rate_of[series_of(f["ticker"])] for f in fills]
    runs = sum(1 for a, b in zip(seq, seq[1:]) if a != b)
    print(f"\n  group changes along the time axis: {runs}")
    print("  A single schedule move in time would give exactly 1 change.")
    print(f"  => temporal explanation {'REFUTED' if runs > 1 else 'NOT refuted'}")

    print("\n" + "=" * 78)
    print("SETTLEMENTS -- granularity by date, single-game only (KXMVE excluded)")
    print("=" * 78)
    print("KXMVE combos are excluded because rest.py strips them before anything")
    print("reaches the traded path; they were always charged sub-cent.\n")
    single = [s for s in settlements if not series_of(s["ticker"]).startswith("KXMVE")]
    for s in sorted(single, key=lambda r: r["settled_time"]):
        fee = Decimal(s["fee_cost"])
        gran = "whole cent" if fee % CENT == 0 else "** sub-cent **"
        print(f"  {s['settled_time'][:10]}  {series_of(s['ticker']).replace('KX', ''):<14}"
              f"{s['fee_cost']:>11}  {gran}")

    print("\n" + "=" * 78)
    print("SETTLEMENT fee_cost vs SUM of that position's fill fees")
    print("=" * 78)
    print("Licenses the registration's §6.2 substitute channel. Does NOT settle H4")
    print("-- see the module docstring, item 4.\n")
    summed: dict[str, Decimal] = {}
    for f in fills:
        summed[f["ticker"]] = summed.get(f["ticker"], Decimal(0)) + Decimal(f["fee_cost"])
    compared = 0
    for s in sorted(settlements, key=lambda r: r["settled_time"]):
        if s["ticker"] in summed:
            compared += 1
            sf, ff = Decimal(s["fee_cost"]), summed[s["ticker"]]
            print(f"  {series_of(s['ticker']).replace('KX', ''):<14}"
                  f"settlement={sf}  fills={ff}  {'SAME' if sf == ff else 'DIFFER'}")
    print(f"\n  positions with both channels: {compared}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
