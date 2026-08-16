"""Run the registered CLV signal test on a `clv-signal-pull` dump.

    flyctl ssh console -a kalshi-cockpit \\
      -C "python /app/scripts/inspect_live_db.py clv-signal-pull --json --limit 100000" > pull.json
    .venv\\Scripts\\python.exe scripts/run_signal_test.py pull.json

Registered in `docs/measurements/2026-08-09-preregistration-clv-signal-test.md`.
**This harness decides nothing.** The population, the model, the cluster key,
the multiplier, the floor and all four verdict branches are fixed in that file;
`backend/analysis/signal_test.py` implements them and this prints them in the
order §S1 requires.

Output order is itself registered, and the order is the point: `n`, `G` and the
P1 coverage come **before** any effect size, and the smallest resolvable `beta`
is printed **before** `beta_hat`. Reading the effect first is how a small cell
gets believed.

What this does not establish
----------------------------
- **Nothing at `G < 300`.** Every such run prints UNRESOLVED. That is a real
  answer, it is not "no signal", and it may not be reported as one.
- **Nothing about a dump it was not given.** Whether the rows are the registered
  §2 population is decided by the extraction query.
- **Nothing about causation.** A positive `beta` says the engine's edge number
  predicts closing-line movement, not that the movement is tradeable.
- **The per-group view can downgrade a verdict and can never create one**
  (§A4). It is printed as a diagnostic and carries no branch of its own.
- **`market_type` is not a registered cut.** It appears in the diagnostic block
  only, labelled, because the pooled figure on this record is not homogeneous
  and the repo rule requires the parts beside the aggregate.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.analysis.signal_test import (  # noqa: E402
    MIN_CLUSTERS_TO_DECLARE,
    MIN_HALF_SPREAD_COVERAGE,
    Observation,
    SignalTestRefused,
    coverage,
    fit,
    verdict,
)


class RefusedInput(Exception):
    """A dump this harness will not analyse."""


def _read(path: Path) -> str:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return fh.read()
    return path.read_text(encoding="utf-8")


def load(path: Path) -> tuple[list[dict[str, Any]], int]:
    """Rows from a `clv-signal-pull` dump, refusing a truncated one.

    A capped dump is ordered by `id`, so it is the project's earliest
    recommendations rather than a sample. A `beta` computed over one is a
    statement about the first N rows written, under superseded strategy
    configs.
    """
    payload = json.loads(_read(path))
    if payload.get("query") != "clv-signal-pull":
        raise RefusedInput(
            f"{path}: this is a {payload.get('query')!r} dump, not clv-signal-pull"
        )
    rows: list[dict[str, Any]] = []
    for section in payload["sections"]:
        if section.get("truncated"):
            raise RefusedInput(
                f"{path}: section {section['title']!r} was truncated. Re-take it "
                f"with a higher --limit; a prefix of the record is not a sample."
            )
        columns = section["columns"]
        rows.extend(dict(zip(columns, row)) for row in section["rows"])
    return rows, len(rows)


def _observations(rows: Sequence[dict[str, Any]]) -> list[Observation]:
    return [
        Observation(
            cluster_key=str(r["cluster_key"]),
            edge_tenths=float(r["edge_tenths"]),
            clv_tenths=float(r["clv_tenths"]),
            half_spread_tenths=(
                None if r["half_spread_tenths"] is None
                else float(r["half_spread_tenths"])
            ),
        )
        for r in rows
    ]


def _quote_disagrees(row: dict[str, Any]) -> bool:
    """§A8.2: the joined quote's derived ask differs from the stored entry ask.

    Counted separately from "no quote at all". A row with a quote that
    disagrees is not missing data -- it is a row whose control was recovered
    from a different observation than the one the recommendation was priced
    from, which is a different problem with a different remedy.
    """
    if row.get("no_bid_tenths") is None:
        return False
    return (1000 - row["no_bid_tenths"]) != row["entry_ask_tenths"]


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("dump", type=Path)
    parser.add_argument(
        "--modal-config-only",
        action="store_true",
        help="§7: restrict to the modal strategy_config_version",
    )
    args = parser.parse_args(argv)

    rows, n_raw = load(args.dump)
    print("# CLV signal test")
    print("# Registered: docs/measurements/2026-08-09-preregistration-clv-signal-test.md")
    print()

    versions = Counter(r["strategy_config_version"] for r in rows)
    if args.modal_config_only and versions:
        modal = versions.most_common(1)[0][0]
        rows = [r for r in rows if r["strategy_config_version"] == modal]
        print(f"§7 modal-config filter ON: keeping version {modal} only")
        print()

    obs = _observations(rows)
    clusters = {o.cluster_key for o in obs}
    unclustered = sum(1 for r in rows if r.get("unclustered"))
    cov = coverage(obs)

    # 1. n before effect size. Always.
    print("1. population")
    print("-" * 40)
    print(f"  rows in dump                 {n_raw}")
    print(f"  rows analysed                {len(rows)}")
    print(f"  G (clusters, registered key) {len(clusters)}")
    print(f"  unclustered rows             {unclustered}")
    print(f"  P1 half-spread coverage      {cov:.4f}  (floor {MIN_HALF_SPREAD_COVERAGE})")
    print(f"  rows with no quote at all    {sum(1 for r in rows if r['half_spread_tenths'] is None)}")
    print(f"  rows whose quote DISAGREES   {sum(1 for r in rows if _quote_disagrees(r))}")
    print(f"  strategy_config_version      {dict(sorted(versions.items()))}")
    print()

    if cov < MIN_HALF_SPREAD_COVERAGE:
        print("P1 FAILED. The primary analysis does not run.")
        print(f"  coverage {cov:.4f} is below the registered floor "
              f"{MIN_HALF_SPREAD_COVERAGE}.")
        print("  This is the registration's own precondition, not a judgement call:")
        print("  without the half-spread control the C2 confound is left in place")
        print("  and the slope is biased in the INFLATING direction.")
        return 1

    try:
        f = fit(obs)
    except SignalTestRefused as exc:
        print(f"REFUSED: {exc}")
        return 1

    # 2. the contamination, as a printed number rather than an argument
    import statistics

    usable = [o for o in obs if o.half_spread_tenths is not None]
    sd_half = statistics.pstdev([o.half_spread_tenths for o in usable])
    sd_edge = statistics.pstdev([o.edge_tenths for o in usable])
    sd_clv = statistics.pstdev([o.clv_tenths for o in usable])
    print("2. the C2 confound, measured")
    print("-" * 40)
    print(f"  sd(half_spread_tenths)       {sd_half:.4f}")
    print(f"  sd(edge_tenths)              {sd_edge:.4f}")
    print(f"  sd(clv_tenths)               {sd_clv:.4f}")
    spurious = (sd_half**2 / sd_edge**2) if sd_edge else float("nan")
    print(f"  implied spurious slope       {spurious:.6f}   Var(half)/Var(edge)")
    print()

    # 4. the smallest resolvable beta, BEFORE beta_hat
    print("3. resolving power at this G, printed before the estimate")
    print("-" * 40)
    print(f"  always-valid multiplier      {f.multiplier:.4f}")
    print(f"  smallest resolvable beta     {f.multiplier * f.se_cluster:.4f}")
    print()

    print("4. the estimate")
    print("-" * 40)
    print(f"  beta_hat                     {f.beta_hat:+.4f}")
    print(f"  gamma_hat (half-spread)      {f.gamma_hat:+.4f}")
    print(f"  se_cluster                   {f.se_cluster:.4f}")
    print(f"  se_classical                 {f.se_classical:.4f}   (NOT the one used)")
    print(f"  always-valid interval        [{f.lower:+.4f}, {f.upper:+.4f}]")
    print()

    v = verdict(f)
    print("5. verdict")
    print("-" * 40)
    print(f"  {v}")
    if f.n_clusters < MIN_CLUSTERS_TO_DECLARE:
        print(f"  G = {f.n_clusters} is below the registered floor of "
              f"{MIN_CLUSTERS_TO_DECLARE}.")
        print("  A look below the floor MAY NOT declare SIGNAL, BUG or NO SIGNAL.")
        print("  UNRESOLVED is a real answer and is not 'no signal'.")
    print()

    # 6. the per-group view. Downgrades only; never creates a finding.
    print("6. per-group view -- DIAGNOSTIC, CANNOT PRODUCE A FINDING")
    print("-" * 40)
    by_type: dict[str, list[Observation]] = defaultdict(list)
    for row, o in zip(rows, obs):
        by_type[row.get("market_type") or "(none)"].append(o)
    for name, group in sorted(by_type.items(), key=lambda kv: -len(kv[1])):
        share = len(group) / len(obs)
        try:
            gf = fit(group)
            print(f"  {name:<12} n={len(group):5d} G={gf.n_clusters:4d} "
                  f"share={share:5.1%}  beta={gf.beta_hat:+.4f}")
        except SignalTestRefused as exc:
            print(f"  {name:<12} n={len(group):5d} share={share:5.1%}  "
                  f"REFUSED: {exc}")
    largest = max(by_type.items(), key=lambda kv: len(kv[1]))
    print(f"  largest contributor: {largest[0]} at "
          f"{len(largest[1]) / len(obs):.1%} of rows")
    print()

    print("7. what this does not establish")
    print("-" * 40)
    for line in (
        "A positive beta says the edge number predicts closing-line movement.",
        "It does not say the movement is tradeable, survives fees, or was fillable.",
        "market_type is NOT a registered cut; section 6 is a diagnostic only.",
        "G is on the registration's cluster key COALESCE(event_ticker, ticker),",
        "  which is NOT the gate's ADR 0029 key. The two differ materially.",
    ):
        print(f"  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
