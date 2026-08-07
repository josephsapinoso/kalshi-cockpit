"""Measurement harness. Refuses to report what it cannot distinguish from noise.

Ported from the previous project's `validate_no_bias.py`, which exists because
every earlier version of the same measurement was wrong in a way that
**flattered the result**. That directionality is not a coincidence: a
measurement bug that made things look worse would have been chased down
immediately, so the surviving bugs are the encouraging ones.

Three guards, each earned:

**1. Read `n` before the effect size.** A two-market cell produced a 74-point
"finding" that passed a significance test. Standard error is computed under the
**null** (at the implied rate, not the observed one), and a cell prints the
literal string ``(noise)`` rather than a number when the normal approximation
does not apply or the gap sits inside two standard errors. Printing a P&L there
invites reading it as a result.

**2. A pooled number is not a finding until the parts agree.** Simpson's
paradox appeared three times in the previous project. Every pooled result is
partitioned across subgroups into *supported*, *contradicted*, or
**unpowered** -- and that third category is the subtle one. An earlier version
marked eight genuine buckets as artifacts purely because the subgroups were too
small to confirm them. "Unresolved" and "refuted" are different claims.

**3. Edge and money must agree in sign.** Bucketed on the price actually paid,
never the mid. One bucket showed a +25.4 point edge *while losing $4.92 a
market*, because it was bucketed on the mid and transacted at the ask. The
threshold for complaining is 3c rather than 1c, deliberately: the entry fee
peaks at 1.75c/contract, so a small positive edge with negative money is fees
working correctly. Above 3c no fee explains it, which means bucketing has
drifted off the transaction price again.

What this harness does NOT establish
------------------------------------
- **It cannot tell you the edge is real, only that it is not obviously fake.**
  Surviving these guards is necessary, not sufficient.
- **Closing-line value is not profit.** It is the fastest honest proxy
  available, and it can be positive while the account shrinks.
- **Candlestick quotes are unsized.** A price you could not have filled counts
  the same here as one you could.
- **Settled markets are a survivorship-flavoured sample.** Markets that never
  developed liquidity are absent.
- **One horizon is one snapshot.** Re-run at a second horizon; if the result
  moves, it was convergence, not edge.
- **Counting tests matters.** Run enough buckets and some will clear two
  standard errors by chance. `n_tests` is reported for exactly this reason.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

# Buckets on the price ACTUALLY PAID, in tenths of a cent. Never the mid.
BUCKETS: tuple[tuple[int, int], ...] = (
    (10, 100), (100, 200), (200, 300), (300, 400), (400, 500),
    (500, 600), (600, 700), (700, 800), (800, 900), (900, 990),
)

# Normal-approximation validity. Below this the arithmetic still produces a
# number, and the number is meaningless.
MIN_EXPECTED_PER_SIDE = 5

# Above this gap, no fee can explain edge and money disagreeing.
EDGE_MONEY_TOLERANCE_TENTHS = 30.0


@dataclass(frozen=True)
class Observation:
    """One scored recommendation."""

    entry_ask_tenths: int
    group: str = "all"          # league, config version -- whatever we pool over
    clv_tenths: Optional[float] = None
    settled_win: Optional[bool] = None
    pnl_cents: Optional[float] = None


@dataclass(frozen=True)
class BucketResult:
    low: int
    high: int
    n: int
    implied_probability: float
    actual_rate: Optional[float]
    gap_points: Optional[float]
    stderr_points: Optional[float]
    mean_pnl_cents: Optional[float]
    mean_clv_tenths: Optional[float]
    normal_approx_valid: bool
    distinguishable: bool

    @property
    def label(self) -> str:
        return f"{self.low // 10}-{self.high // 10}c"

    def render_gap(self) -> str:
        """A cell we cannot distinguish from noise prints `(noise)`, not a number.

        This is the whole point of the class. A number here would be read as a
        result no matter how many caveats surround it.
        """
        if not self.distinguishable or self.gap_points is None:
            return "(noise)"
        return f"{self.gap_points:+.1f}"


# Two-sided at two standard errors is alpha ~= 0.0455 under normality. The same
# figure `mart_multiple_comparisons` uses, deliberately -- the SQL and the Python
# must not disagree about what "significant" means.
PER_TEST_ALPHA = 0.0455


@dataclass(frozen=True)
class Summary:
    buckets: tuple[BucketResult, ...]
    n_total: int
    n_tests: int
    group: str = "all"

    @property
    def distinguishable(self) -> tuple[BucketResult, ...]:
        return tuple(b for b in self.buckets if b.distinguishable)

    @property
    def expected_by_chance(self) -> float:
        return self.n_tests * PER_TEST_ALPHA

    @property
    def family_wise_p(self) -> Optional[float]:
        """P(at least this many findings from nothing), across all the cells.

        **`n_tests` was counted, printed, and never used.** Eight powered cells
        at alpha 0.0455 produce at least one "significant" bucket about 30% of
        the time from pure noise, so a per-cell guard alone cannot support the
        conclusion drawn across the grid -- which is the lesson this project
        already wrote down after `mart_multiple_comparisons`, applied in SQL and
        not in the Python that runs the same check.

        Computed exactly rather than approximated: with a handful of tests the
        normal approximation to the binomial is itself invalid, which would be a
        conspicuous place to take a shortcut.
        """
        if not self.n_tests:
            return None
        findings = len(self.distinguishable)
        below = sum(
            math.comb(self.n_tests, k)
            * (PER_TEST_ALPHA ** k)
            * ((1 - PER_TEST_ALPHA) ** (self.n_tests - k))
            for k in range(findings)
        )
        return max(0.0, min(1.0, 1.0 - below))

    @property
    def survives_multiple_comparisons(self) -> bool:
        """Whether the findings beat what chance produces across this many tests.

        A single distinguishable cell in a grid of ten is what it almost always
        is: the one that got lucky.
        """
        p = self.family_wise_p
        return p is not None and bool(self.distinguishable) and p <= 0.05

    @property
    def family_wise_verdict(self) -> str:
        p = self.family_wise_p
        findings = len(self.distinguishable)
        if p is None:
            return "no powered tests yet"
        if not findings:
            return f"no findings across {self.n_tests} tests"
        if p > 0.20:
            return (
                f"NOT EVIDENCE: {findings} finding(s) from {self.n_tests} tests. "
                f"Pure chance produces this or more {p * 100:.0f}% of the time."
            )
        if p > 0.05:
            return (
                f"WEAK: {findings} finding(s) from {self.n_tests} tests "
                f"(p={p:.3f}). Not distinguishable from luck."
            )
        return (
            f"{findings} finding(s) from {self.n_tests} tests (p={p:.3f}). More "
            f"than chance predicts — confirm at a second horizon before "
            f"believing it."
        )


def _bucket_of(price_tenths: int) -> Optional[tuple[int, int]]:
    for low, high in BUCKETS:
        if low <= price_tenths < high:
            return (low, high)
    return None


def summarise(observations: Iterable[Observation], group: str = "all") -> Summary:
    """Bucket by the price paid and apply the noise guard to each cell."""
    by_bucket: dict[tuple[int, int], list[Observation]] = {b: [] for b in BUCKETS}
    for obs in observations:
        bucket = _bucket_of(obs.entry_ask_tenths)
        if bucket is not None:
            by_bucket[bucket].append(obs)

    results: list[BucketResult] = []
    total = 0
    tests = 0

    for (low, high), rows in by_bucket.items():
        n = len(rows)
        total += n
        if n == 0:
            continue

        settled = [r for r in rows if r.settled_win is not None]

        # The implied probability is the mean price actually paid, expressed as
        # a probability. This is the null hypothesis: the market is right.
        #
        # **Computed over the SETTLED rows only**, the same population `actual`
        # is computed over. It used to average across every row in the bucket
        # while `actual` divided by the settled subset, so the two halves of
        # `gap` described different sets of games. Settlement arrival is not
        # random with respect to price -- at any instant the settled subset is
        # whatever has finished, which correlates with start time and therefore
        # with the kind of fixture -- so that mismatch put a bias directly into
        # `gap` and into `stderr`, the two numbers the whole calibration check
        # rests on.
        implied = (
            sum(r.entry_ask_tenths for r in settled) / len(settled) / 1000.0
            if settled
            else sum(r.entry_ask_tenths for r in rows) / n / 1000.0
        )

        actual: Optional[float] = None
        gap: Optional[float] = None
        stderr: Optional[float] = None
        valid = False
        distinguishable = False

        if settled:
            wins = sum(1 for r in settled if r.settled_win)
            actual = wins / len(settled)
            gap = (actual - implied) * 100

            # Standard error under the NULL -- at the implied rate, not the
            # observed one. Using the observed rate makes an extreme result
            # look more certain precisely because it is extreme.
            p = min(max(implied, 1e-9), 1 - 1e-9)
            stderr = 100.0 * math.sqrt(p * (1 - p) / len(settled))

            valid = (
                len(settled) * p >= MIN_EXPECTED_PER_SIDE
                and len(settled) * (1 - p) >= MIN_EXPECTED_PER_SIDE
            )
            distinguishable = valid and abs(gap) > 2 * stderr
            if valid:
                tests += 1

        pnls = [r.pnl_cents for r in rows if r.pnl_cents is not None]
        clvs = [r.clv_tenths for r in rows if r.clv_tenths is not None]

        results.append(
            BucketResult(
                low=low, high=high, n=n,
                implied_probability=implied,
                actual_rate=actual,
                gap_points=gap,
                stderr_points=stderr,
                mean_pnl_cents=(sum(pnls) / len(pnls)) if pnls else None,
                mean_clv_tenths=(sum(clvs) / len(clvs)) if clvs else None,
                normal_approx_valid=valid,
                distinguishable=distinguishable,
            )
        )

    return Summary(
        buckets=tuple(results), n_total=total, n_tests=tests, group=group
    )


# ---------------------------------------------------------------------------
# Guard 2: pooling
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PoolingVerdict:
    bucket: str
    status: str          # supported | contradicted | unpowered
    detail: str


def pooling_check(
    pooled: Summary, by_group: Sequence[Summary]
) -> tuple[PoolingVerdict, ...]:
    """Check every pooled finding against its subgroups.

    Three outcomes, and the third is the one that matters:

    - **supported**: a subgroup is also distinguishable, with the same sign.
    - **contradicted**: a subgroup is distinguishable with the *opposite* sign.
      That is a pooling artifact, not a finding.
    - **unpowered**: no subgroup reaches significance either way. The pooled
      result is **unresolved, not refuted** -- an earlier version of this check
      called all eight buckets of a real run artifacts purely because the
      subgroups were small.
    """
    verdicts: list[PoolingVerdict] = []

    for bucket in pooled.distinguishable:
        same_bucket = [
            b
            for summary in by_group
            for b in summary.buckets
            if (b.low, b.high) == (bucket.low, bucket.high)
        ]
        powered = [b for b in same_bucket if b.distinguishable]

        if not powered:
            verdicts.append(
                PoolingVerdict(
                    bucket.label, "unpowered",
                    f"no subgroup reaches significance ({len(same_bucket)} groups "
                    f"present). Unresolved, not refuted -- the groups are too small.",
                )
            )
            continue

        pooled_sign = math.copysign(1, bucket.gap_points or 0)
        opposing = [
            b for b in powered
            if math.copysign(1, b.gap_points or 0) != pooled_sign
        ]
        if opposing:
            verdicts.append(
                PoolingVerdict(
                    bucket.label, "contradicted",
                    f"{len(opposing)} subgroup(s) are significant with the "
                    f"opposite sign. That is a pooling artifact, not a finding.",
                )
            )
        else:
            verdicts.append(
                PoolingVerdict(
                    bucket.label, "supported",
                    f"{len(powered)} subgroup(s) agree in sign.",
                )
            )

    return tuple(verdicts)


# ---------------------------------------------------------------------------
# Guard 3: edge and money must agree
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConsistencyWarning:
    bucket: str
    gap_points: float
    mean_pnl_cents: float
    message: str


def check_edge_money_consistency(summary: Summary) -> tuple[ConsistencyWarning, ...]:
    """Flag buckets where a measured edge and realised money disagree in sign.

    The tolerance is deliberately 3c rather than 1c. The entry fee peaks at
    1.75c/contract, so a small positive edge with negative money is fees
    working correctly. Above 3c no fee can explain it -- which means the
    bucketing has drifted off the transaction price again, exactly as it did
    when a +25.4-point bucket lost $4.92 a market.
    """
    warnings: list[ConsistencyWarning] = []
    for bucket in summary.buckets:
        if bucket.gap_points is None or bucket.mean_pnl_cents is None:
            continue
        if not bucket.distinguishable:
            continue
        if bucket.gap_points > EDGE_MONEY_TOLERANCE_TENTHS / 10 and bucket.mean_pnl_cents < 0:
            warnings.append(
                ConsistencyWarning(
                    bucket.label, bucket.gap_points, bucket.mean_pnl_cents,
                    f"{bucket.label}: edge {bucket.gap_points:+.1f} points but "
                    f"P&L {bucket.mean_pnl_cents:+.2f}c. No fee explains a gap "
                    f"this large -- check that the bucket is keyed on the price "
                    f"actually paid, not the mid.",
                )
            )
    return tuple(warnings)


# ---------------------------------------------------------------------------
# CLV
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CLVResult:
    n: int
    mean_tenths: float
    stderr_tenths: float
    beat_close_rate: float
    distinguishable: bool
    required_n: int

    @property
    def verdict(self) -> str:
        if self.n < self.required_n:
            return (
                f"{self.n} of {self.required_n} scored. Too few to say anything -- "
                f"CLV needs 200-300 before it means much, and 500-1,000 before it "
                f"predicts well."
            )
        if not self.distinguishable:
            return "Indistinguishable from zero. No demonstrated edge."
        direction = "beating" if self.mean_tenths > 0 else "losing to"
        return (
            f"{direction} the close by {abs(self.mean_tenths) / 10:.2f}c per bet "
            f"on {self.n} observations."
        )


def summarise_clv(
    observations: Iterable[Observation], *, required_n: int = 300
) -> CLVResult:
    """Aggregate closing-line value.

    CLV is continuous, so the guard is a standard error of the mean rather than
    the binomial form used for settled outcomes. `required_n` defaults to the
    live gate's floor: below it, no verdict is offered at all.
    """
    values = [o.clv_tenths for o in observations if o.clv_tenths is not None]
    n = len(values)
    if n == 0:
        return CLVResult(0, 0.0, 0.0, 0.0, False, required_n)

    mean = sum(values) / n
    if n > 1:
        variance = sum((v - mean) ** 2 for v in values) / (n - 1)
        stderr = math.sqrt(variance / n)
    else:
        stderr = float("inf")

    beat = sum(1 for v in values if v > 0) / n

    return CLVResult(
        n=n,
        mean_tenths=mean,
        stderr_tenths=stderr,
        beat_close_rate=beat,
        # Two standard errors AND enough observations. Either alone is not
        # enough: a tiny sample can clear two standard errors by luck.
        distinguishable=(n >= required_n and abs(mean) > 2 * stderr),
        required_n=required_n,
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def report(
    pooled: Summary,
    by_group: Sequence[Summary] = (),
    clv: Optional[CLVResult] = None,
) -> str:
    """Human-readable report. Indistinguishable cells print `(noise)`."""
    lines: list[str] = []
    add = lines.append

    add("=" * 78)
    add(f"MEASUREMENT REPORT -- {pooled.n_total} observations, "
        f"{pooled.n_tests} powered tests")
    add("=" * 78)

    # First, before any individual bucket. `n_tests` used to be counted here and
    # then never used, so a reader saw "8 powered tests" and a significant cell
    # and had to do the multiplicity arithmetic themselves -- which is precisely
    # what nobody does. Eight cells produce at least one two-sigma hit about 30%
    # of the time from nothing.
    add("")
    add("ACROSS ALL TESTS  (read this before any bucket below)")
    add(f"  {pooled.family_wise_verdict}")
    if pooled.n_tests:
        add(f"  expected by chance: {pooled.expected_by_chance:.2f} "
            f"finding(s) from {pooled.n_tests} tests")

    if clv is not None:
        add("")
        add("CLOSING LINE VALUE")
        add(f"  {clv.verdict}")
        if clv.n:
            add(f"  mean {clv.mean_tenths / 10:+.2f}c  "
                f"stderr {clv.stderr_tenths / 10:.2f}c  "
                f"beat close {clv.beat_close_rate:.0%}")

    add("")
    add("BY PRICE PAID  (bucketed on the ask, never the mid)")
    add(f"  {'bucket':<10}{'n':>6}{'implied':>10}{'actual':>9}"
        f"{'gap':>9}{'P&L':>9}{'CLV':>9}")
    add("  " + "-" * 60)
    for bucket in pooled.buckets:
        pnl = f"{bucket.mean_pnl_cents:+.2f}" if bucket.mean_pnl_cents is not None else "--"
        clv_cell = (
            f"{bucket.mean_clv_tenths / 10:+.2f}"
            if bucket.mean_clv_tenths is not None else "--"
        )
        actual = f"{bucket.actual_rate:.3f}" if bucket.actual_rate is not None else "--"
        add(
            f"  {bucket.label:<10}{bucket.n:>6}{bucket.implied_probability:>10.3f}"
            f"{actual:>9}{bucket.render_gap():>9}{pnl:>9}{clv_cell:>9}"
        )

    if not pooled.distinguishable:
        add("")
        add("  No bucket is distinguishable from noise. That is a result, and")
        add("  the correct one to report when it is true.")

    if by_group and pooled.distinguishable:
        add("")
        add("POOLING CHECK")
        for verdict in pooling_check(pooled, by_group):
            add(f"  {verdict.bucket:<10}{verdict.status.upper():<15}{verdict.detail}")

    warnings = check_edge_money_consistency(pooled)
    if warnings:
        add("")
        add("EDGE / MONEY DISAGREEMENT")
        for warning in warnings:
            add(f"  {warning.message}")

    add("")
    add("WHAT THIS DOES NOT ESTABLISH")
    add("  Surviving these guards is necessary, not sufficient. CLV is not")
    add("  profit. Candlestick quotes are unsized. Settled markets are a")
    add("  survivorship-flavoured sample. One horizon is one snapshot -- re-run")
    add(f"  at a second horizon. {pooled.n_tests} tests were run; at two standard")
    add("  errors, roughly 1 in 20 clears by chance.")
    add("=" * 78)

    return "\n".join(lines)
