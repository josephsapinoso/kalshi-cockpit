"""Run the registered CLV signal test on a `clv-signal-pull` dump.

    flyctl ssh console -a kalshi-cockpit \\
      -C "python /app/scripts/inspect_live_db.py clv-signal-pull --json --limit 100000" > pull.json
    .venv\\Scripts\\python.exe scripts/run_signal_test.py pull.json

Registered in `docs/measurements/2026-08-09-preregistration-clv-signal-test.md`.
**This harness decides nothing, and as of ADR 0039 it no longer computes
anything either.** The population, the model, the cluster key, the multiplier,
the floor and all four verdict branches are fixed in the registration;
`backend/analysis/signal_test.py` implements the estimator,
`backend/analysis/clv_signal.py` implements the extraction and assembles a
`SignalReport`, and this file prints that report in the order §S1 requires.

**The whole point of that split is that `GET /api/signal` serves the same
object.** The number on the screen and the number this harness prints are one
computation, not two implementations that agree today.

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
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.analysis.clv_signal import (  # noqa: E402
    A82_MISMATCH_DISCLOSURE_THRESHOLD,
    SignalReport,
    build_report,
)
from backend.analysis.signal_test import (  # noqa: E402
    MIN_CLUSTERS_TO_DECLARE,
    MIN_HALF_SPREAD_COVERAGE,
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


def render(report: SignalReport) -> int:
    """Print a `SignalReport` in the registered §S1 order. Returns an exit code.

    Formatting only. Every number here was computed in `clv_signal`; if this
    function ever needs to do arithmetic to print something, the field belongs
    on the report instead -- otherwise the screen and the harness drift apart
    one derived quantity at a time, which is the failure this split exists to
    prevent.
    """
    print("# CLV signal test")
    print("# Registered: docs/measurements/2026-08-09-preregistration-clv-signal-test.md")
    print()

    if report.modal_config_only and report.strategy_config_versions:
        modal = max(report.strategy_config_versions.items(), key=lambda kv: kv[1])[0]
        print(f"§7 modal-config filter ON: keeping version {modal} only")
        print()

    # 1. n before effect size. Always.
    print("1. population")
    print("-" * 40)
    print(f"  rows in dump                 {report.n_raw}")
    print(f"  rows analysed                {report.n_analysed}")
    print(f"  G (clusters, registered key) {report.n_clusters}")
    print(f"  unclustered rows             {report.unclustered}")
    print(f"  §A8.2 matched                {report.matched}")
    print(f"  §A8.2 quote_mismatch         {report.quote_mismatch}   (RETAINED, not dropped)")
    print(f"  §A8.2 no_quote               {report.no_quote}")
    print(f"  P1 = matched / total         {report.p1:.4f}  (floor {MIN_HALF_SPREAD_COVERAGE})")
    print(f"  non-NULL half-spread cov     {report.non_null_coverage:.4f}  <- SUPERSEDED by §A8.2, not the gate")
    print(f"  strategy_config_version      {report.strategy_config_versions}")
    print()

    # §A8.2's mandated disclosure, printed by the harness so it cannot be
    # forgotten by a write-up. The wording is the amendment's, not a paraphrase.
    if report.disclosure_required:
        mismatch_fraction = (
            report.quote_mismatch / report.n_analysed if report.n_analysed else 0.0
        )
        print("§A8.2 DISCLOSURE REQUIRED -- this text must appear in the write-up")
        print("-" * 40)
        print(f"  quote_mismatch / total = {mismatch_fraction:.4f}, above "
              f"{A82_MISMATCH_DISCLOSURE_THRESHOLD}.")
        print("  The half-spread control is ATTENUATED on that fraction, and the")
        print("  residual bias in `beta` runs POSITIVE -- the flattering direction.")
        print()

    if not report.p1_passed:
        print("P1 FAILED. The primary analysis does not run.")
        print(f"  matched / total = {report.p1:.4f} is below the registered "
              f"floor {MIN_HALF_SPREAD_COVERAGE}.")
        print("  §A8.2 applies P1 to `matched / total`, NOT to non-NULL half-spread")
        print("  coverage; it calls that 'a strictly tighter gate than the one")
        print("  registered'. Reading the looser statistic here is how a run with")
        print("  half its controls joined off the wrong quote reports a beta.")
        print("  This is the registration's own precondition, not a judgement call:")
        print("  without the half-spread control the C2 confound is left in place")
        print("  and the slope is biased in the INFLATING direction.")
        return 1

    if report.fit is None:
        print(f"REFUSED: {report.refusal}")
        return 1

    f = report.fit

    # 2. the contamination, as a printed number rather than an argument
    print("2. the C2 confound, measured")
    print("-" * 40)
    print(f"  sd(half_spread_tenths)       {report.sd_half_spread:.4f}")
    print(f"  sd(edge_tenths)              {report.sd_edge:.4f}")
    print(f"  sd(clv_tenths)               {report.sd_clv:.4f}")
    print(f"  implied spurious slope       {report.implied_spurious_slope:.6f}   Var(half)/Var(edge)")
    print()

    # 4. the smallest resolvable beta, BEFORE beta_hat
    print("3. resolving power at this G, printed before the estimate")
    print("-" * 40)
    print(f"  always-valid multiplier      {f.multiplier:.4f}")
    print(f"  smallest resolvable beta     {report.smallest_resolvable_beta:.4f}")
    print()

    print("4. the estimate")
    print("-" * 40)
    print(f"  beta_hat                     {f.beta_hat:+.4f}")
    print(f"  gamma_hat (half-spread)      {f.gamma_hat:+.4f}")
    print(f"  se_cluster                   {f.se_cluster:.4f}")
    print(f"  se_classical                 {f.se_classical:.4f}   (NOT the one used)")
    print(f"  always-valid interval        [{f.lower:+.4f}, {f.upper:+.4f}]")
    print()

    print("5. verdict")
    print("-" * 40)
    print(f"  {report.verdict}")
    if f.n_clusters < MIN_CLUSTERS_TO_DECLARE:
        print(f"  G = {f.n_clusters} is below the registered floor of "
              f"{MIN_CLUSTERS_TO_DECLARE}.")
        print("  A look below the floor MAY NOT declare SIGNAL, BUG or NO SIGNAL.")
        print("  UNRESOLVED is a real answer and is not 'no signal'.")
    print()

    # 6. the per-group view. Downgrades only; never creates a finding.
    print("6. per-group view -- DIAGNOSTIC, CANNOT PRODUCE A FINDING")
    print("-" * 40)
    for group in report.by_market_type:
        if group.refusal is not None:
            print(f"  {group.name:<12} n={group.n_rows:5d} share={group.share:5.1%}  "
                  f"REFUSED: {group.refusal}")
        else:
            print(f"  {group.name:<12} n={group.n_rows:5d} G={group.n_clusters:4d} "
                  f"share={group.share:5.1%}  beta={group.beta_hat:+.4f}")
    if report.by_market_type:
        largest = max(report.by_market_type, key=lambda g: g.n_rows)
        print(f"  largest contributor: {largest.name} at {largest.share:.1%} of rows")
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
    report = build_report(
        rows, n_raw=n_raw, modal_config_only=args.modal_config_only
    )
    return render(report)


if __name__ == "__main__":
    raise SystemExit(main())
