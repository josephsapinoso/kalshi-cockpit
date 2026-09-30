"""Run the registered CLV signal test on a `clv-signal-pull` dump.

    flyctl ssh console -a kalshi-cockpit \\
      -C "python /app/scripts/inspect_live_db.py clv-signal-pull --json --limit 100000 --i-accept-the-cache-flush" > pull.json
    .venv\\Scripts\\python.exe scripts/run_signal_test.py pull.json

The pull refuses without `--i-accept-the-cache-flush` (exit 4): it walks a
10M-row table and flushes the desk's page cache. The §7(1) stopping-rule cut is
computed from that same pull, with no second read of the live instance:

    .venv\\Scripts\\python.exe scripts/run_signal_test.py pull.json --through-clusters 1000

`--through-clusters N` keeps every row scored at or before T*, the earliest
`clv_scored_ms` at which N distinct modal-version games have been scored. A
scoring batch sharing T*'s millisecond is never split, so the cut's real `G`
can exceed N and is printed. It refuses if the cut's modal version differs from
the full record's, and refuses a dump pulled before `clv_scored_ms` was
selected.

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
- **Nothing at `G < 713`.** Every such run prints UNRESOLVED. That is a real
  answer, it is not "no signal", and it may not be reported as one. The floor
  was 300 until Amendment 2 §B4 raised it on 2026-08-29, after the power
  check's own trigger fired at `sd(clv_tenths) = 31.6915` on the modal
  population. It is a ratchet: it does not fall if a later look measures less.
- **Nothing about whether nominal `G` is the right unit.** Section 3 prints
  `G_eff` -- Kish's effective count on leverage, `4.26` against a nominal 311
  at the 2026-08-25 look -- and §B7 keeps it a **reportable, not a threshold**.
  Nothing in this harness or in `verdict()` compares it to anything.
- **No group in section 6 is a finding.** §A4's leave-one-group-out branch can
  turn SIGNAL or NO SIGNAL into UNRESOLVED and can never raise a verdict.
- **`G` is the modal config version's cluster count, not the record's.** §P4 and
  §7 make the modal version the primary population whenever more than one is
  present, and `build_report` applies that itself as of 2026-08-25. A `G` quoted
  from a pooled run is not the registered `G`: on the 2026-08-25 record the two
  are 216 and 311, either side of the floor.
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
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.analysis.clv_signal import (  # noqa: E402
    A82_MISMATCH_DISCLOSURE_THRESHOLD,
    SignalReport,
    build_report,
)
from backend.analysis.signal_test import (  # noqa: E402
    MIN_CLUSTERS_FOR_LOGO_TEST,
    MIN_CLUSTERS_TO_DECLARE,
    MIN_HALF_SPREAD_COVERAGE,
    ONE_GROUP_LEVERAGE_SHARE,
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


@dataclass(frozen=True)
class Cut:
    """A §7(1) stopping-rule cut of a dump."""

    rows: list[dict[str, Any]]
    t_star_ms: int
    g_at_t_star: int  # distinct modal-version clusters in the cut; may exceed N
    modal_version: Any
    full_modal_version: Any
    n_null_scored: int  # rows with clv_scored_ms NULL, excluded from the cut
    n_after: int  # scored rows later than T*, excluded


def _modal(rows: list[dict[str, Any]]) -> Any:
    # Same rule as `clv_signal.build_report`: most rows wins.
    return Counter(r["strategy_config_version"] for r in rows).most_common(1)[0][0]


def cut_through_clusters(rows: list[dict[str, Any]], n: int) -> Cut:
    """Rows scored at or before T*, the time the Nth modal-version game is scored.

    Registration §7(1): collection ends at "G = 1000 independent games scored at
    horizon 0.0", counted on the modal `strategy_config_version` (§P4). Whole
    scoring batches are kept (`<= T*`), so G can exceed N.

    Refuses rather than guesses: a dump with no `clv_scored_ms` column, fewer
    than N modal clusters, or a cut whose modal version differs from the full
    record's (then the cut would be a different registered population).
    """
    if n < 1:
        raise RefusedInput("--through-clusters must be at least 1")
    if not rows:
        raise RefusedInput("--through-clusters: the dump has no rows")
    if "clv_scored_ms" not in rows[0]:
        raise RefusedInput(
            "--through-clusters needs `clv_scored_ms`, which this dump lacks "
            "(pulled before the column was selected). Re-take the pull; T* is "
            "not guessed from `created_ms`."
        )
    full_modal = _modal(rows)
    null_scored = sum(1 for r in rows if r["clv_scored_ms"] is None)
    scored = [r for r in rows if r["clv_scored_ms"] is not None]

    first_seen: dict[str, int] = {}
    for r in scored:
        if r["strategy_config_version"] != full_modal:
            continue
        key = str(r["cluster_key"])
        t = int(r["clv_scored_ms"])
        if key not in first_seen or t < first_seen[key]:
            first_seen[key] = t
    if len(first_seen) < n:
        raise RefusedInput(
            f"--through-clusters {n}: the record has only {len(first_seen)} "
            f"modal-version clusters scored. The stopping rule has not been reached."
        )
    t_star = sorted(first_seen.values())[n - 1]
    kept = [r for r in scored if int(r["clv_scored_ms"]) <= t_star]
    cut_modal = _modal(kept)
    if cut_modal != full_modal:
        raise RefusedInput(
            f"REFUSED: the cut's modal strategy_config_version ({cut_modal!r}) "
            f"differs from the full record's ({full_modal!r}). The cut is not "
            f"the registered §P4 population; do not read it."
        )
    g = len({
        str(r["cluster_key"]) for r in kept
        if r["strategy_config_version"] == cut_modal
    })
    return Cut(
        rows=kept, t_star_ms=t_star, g_at_t_star=g, modal_version=cut_modal,
        full_modal_version=full_modal, n_null_scored=null_scored,
        n_after=len(scored) - len(kept),
    )


def render_cut(cut: Cut, n: int) -> None:
    t = datetime.fromtimestamp(cut.t_star_ms / 1000, tz=timezone.utc)
    print(f"# §7(1) CUT --through-clusters {n}")
    print(f"  T* (earliest clv_scored_ms reaching {n} modal clusters)  "
          f"{t.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]}Z ({cut.t_star_ms})")
    print(f"  actual G at T* (modal version; may exceed {n})  {cut.g_at_t_star}")
    print(f"  cut modal version            {cut.modal_version}")
    print(f"  full record modal version    {cut.full_modal_version}   "
          f"(equal: {cut.modal_version == cut.full_modal_version})")
    print(f"  rows kept / after T* / clv_scored_ms NULL   "
          f"{len(cut.rows)} / {cut.n_after} / {cut.n_null_scored}")
    print()


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

    if report.modal_config_applied:
        print(
            f"§P4/§7 APPLIED: the record carries "
            f"{len(report.strategy_config_versions)} strategy_config_versions, "
            f"so the primary runs on the modal one "
            f"(version {report.modal_config_version}) alone and G counts only "
            f"those games."
        )
        print(
            f"  {report.n_non_modal_dropped} non-modal rows are excluded from "
            f"the primary and reported as the distribution below."
        )
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

    # §B6(5)'s ratchet check, printed as its own block rather than as a number
    # in a row, because the consequence of it being true is an amendment to the
    # registration and not a line in a table. A look that does not print this
    # has not checked the floor it is declaring against.
    print("§B4 RATCHET CHECK -- sd(clv_tenths) on the modal population")
    print("-" * 40)
    print(f"  sd(clv_tenths)               {report.sd_clv:.4f}")
    print(f"  floor {MIN_CLUSTERS_TO_DECLARE} was computed at    "
          f"{report.ratchet_sigma_tenths}")
    if report.sigma_exceeds_ratchet:
        print("  EXCEEDS. The floor must be RAISED AGAIN by a further dated")
        print("  amendment to the registration, written BEFORE the next look")
        print("  declares anything. It is never lowered and never edited here.")
    else:
        print(f"  does not exceed. The floor stays at {MIN_CLUSTERS_TO_DECLARE}."
              f" It is a RATCHET: a")
        print("  smaller sigma does not lower it.")
    print()

    # 4. the smallest resolvable beta, BEFORE beta_hat
    print("3. resolving power at this G, printed before the estimate")
    print("-" * 40)
    print(f"  always-valid multiplier      {f.multiplier:.4f}")
    print(f"  smallest resolvable beta     {report.smallest_resolvable_beta:.4f}")
    # §B7. Printed here, in the resolving-power block, because that is what it
    # qualifies: `sqrt(G)` in the power check is the right denominator only when
    # the clusters carry equal weight, and these two numbers say whether they do.
    print(f"  G (nominal)                  {f.n_clusters}")
    print(f"  G_eff (Kish, on leverage)    "
          f"{'unreadable' if f.g_eff is None else f'{f.g_eff:.2f}'}"
          f"   REPORTABLE, NOT a threshold (§B7)")
    print(f"  largest cluster's leverage   "
          f"{'unreadable' if f.largest_cluster_leverage_share is None else f'{f.largest_cluster_leverage_share:.4f}'}")
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
    if report.downgraded_by is not None:
        print(f"  §A4 DOWNGRADE: section 6 alone returned "
              f"{report.section6_verdict}.")
        print(f"  Removing the pre-registered group '{report.downgraded_by}' did")
        print("  not leave the claim standing, so the verdict is UNRESOLVED.")
        print("  The rule is one-way: it can never raise a verdict.")
    print()

    # 6a. §A4's table. The leverage share is required "beside beta_hat, always"
    # -- not only when a downgrade fires and not only at a declaring look.
    print("6a. §A4 pre-registered groups -- LEAVE-ONE-GROUP-OUT DOWNGRADE")
    print("-" * 40)
    print(f"  {'group':<26}{'n':>6}{'clus':>6}{'leverage':>10}{'G left':>8}"
          f"{'beta':>10}{'upper':>10}")
    for g in report.a4_groups:
        lev = "  n/a" if g.leverage_share is None else f"{g.leverage_share:.4f}"
        if not g.testable:
            print(f"  {g.name:<26}{g.n_rows:>6}{g.n_clusters:>6}{lev:>10}"
                  f"{g.clusters_remaining:>8}{'UNTESTABLE':>20}")
        else:
            print(f"  {g.name:<26}{g.n_rows:>6}{g.n_clusters:>6}{lev:>10}"
                  f"{g.clusters_remaining:>8}{g.beta_hat:>+10.4f}"
                  f"{g.upper:>+10.4f}")
    print(f"  UNTESTABLE = removal leaves G < {MIN_CLUSTERS_FOR_LOGO_TEST}. §A4: "
          f"not grounds for downgrade.")
    # §A4's mandatory sentence, printed by the harness so a write-up cannot
    # forget it. The wording is the amendment's, not a paraphrase.
    for g in report.one_group_results:
        print(f"  §A4 DISCLOSURE REQUIRED -- '{g.name}' carries "
              f"{g.leverage_share:.4f} of the leverage, above "
              f"{ONE_GROUP_LEVERAGE_SHARE}, and cannot be tested.")
        print("  The write-up must state that THE POOLED RESULT IS ONE GROUP'S")
        print("  RESULT.")
    print()

    # 6. the per-group view. Downgrades only; never creates a finding.
    print("6b. per-market-type view -- DIAGNOSTIC, CANNOT PRODUCE A FINDING")
    print("-" * 40)
    for group in report.by_market_type:
        if group.refusal is not None:
            print(f"  {group.name:<12} n={group.n_rows:5d} share={group.share:5.1%}  "
                  f"REFUSED: {group.refusal}")
        else:
            print(f"  {group.name:<12} n={group.n_rows:5d} G={group.n_clusters:4d} "
                  f"share={group.share:5.1%}  beta={group.beta_hat:+.4f}")
    if report.by_market_type:
        # **A row-count share of an unregistered grouping, and it is labelled
        # as such.** §A9(5) asks for the largest *registered group's leverage*
        # share; that is section 6a's table and section 3's headline figure.
        # This line was read as the registered reportable at the 2026-08-25
        # audit -- it printed 91.4% where the leverage share of the same
        # grouping was 97.8% -- so it now says what it is.
        largest = max(report.by_market_type, key=lambda g: g.n_rows)
        print(f"  largest by ROW COUNT: {largest.name} at {largest.share:.1%} of "
              f"rows -- NOT the §A9(5) reportable; see 3 and 6a for leverage.")
    print()

    print("7. what this does not establish")
    print("-" * 40)
    for line in (
        "A positive beta says the edge number predicts closing-line movement.",
        "It does not say the movement is tradeable, survives fees, or was fillable.",
        "market_type is NOT a registered cut; section 6b is a diagnostic only.",
        "G is on the registration's cluster key COALESCE(event_ticker, ticker),",
        "  which is NOT the gate's ADR 0029 key. The two differ materially.",
        "G_eff is a REPORTABLE and not a threshold (§B7). Nothing above compares",
        "  it to anything, and restating the floor in it after seeing it is small",
        "  would be choosing an estimator from the answer.",
        "No group in 6a is a finding. §A4's rule is one-way: it turns SIGNAL or",
        "  NO SIGNAL into UNRESOLVED and can never raise a verdict.",
    ):
        print(f"  {line}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("dump", type=Path)
    # `--modal-config-only` is RETIRED, 2026-08-25. It made §P4 -- a registered
    # rule that offers no choice -- an opt-in, and the default is what
    # `GET /api/signal` took when it declared NO SIGNAL on 2026-08-24 over four
    # pooled config versions. `build_report` now applies the rule itself, so
    # there is nothing left for a flag to turn on. See
    # `docs/measurements/2026-08-25-clv-signal-declaring-look-refused.md`.
    parser.add_argument(
        "--through-clusters", type=int, default=None, metavar="N",
        help="§7(1) stopping-rule cut: keep rows scored at or before the time "
             "the Nth modal-version cluster was scored",
    )
    args = parser.parse_args(argv)

    rows, n_raw = load(args.dump)
    if args.through_clusters is not None:
        try:
            cut = cut_through_clusters(rows, args.through_clusters)
        except RefusedInput as exc:
            print(str(exc), file=sys.stderr)
            return 2
        render_cut(cut, args.through_clusters)
        rows = cut.rows
        n_raw = len(rows)
    return render(build_report(rows, n_raw=n_raw))


if __name__ == "__main__":
    raise SystemExit(main())
