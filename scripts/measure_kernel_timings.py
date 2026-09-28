"""Time the two numeric kernels on this machine: devig and the Gaussian copula.

    .venv\\Scripts\\python.exe scripts/measure_kernel_timings.py [--reps 5]

Why this file exists
--------------------
ADR 0188 asks whether any part of the stack is compute-bound enough for a
faster language to matter. Every bottleneck already in `docs/measurements/`
is SQLite, disk or network; the only numeric kernels on the runtime path are
`core/devig.py` (two `brentq` solves per book per market) and
`core/correlation.py:joint_probability_all` (a 200,000-draw Monte Carlo).
This times both on the shapes the recorder feeds them, so "would Rust save
anything here" has a number instead of an opinion.

It also times the numerical alternative to the Monte Carlo. That is scipy's
multivariate-normal CDF (Genz), which computes the same orthant probability
the draws estimate. It is closed-form at 2 legs, and randomized quasi-Monte
Carlo to 1e-5 absolute at 3+ legs, so it is exact only at 2. The harness
prints how far the two disagree. This is evidence for ADR 0188 §4, not a
change: nothing here touches the pricing path.

**Both sides are timed end to end.** The Monte Carlo timing covers
`joint_probability_all`: the matrix, the thresholds and the draws. The Genz
timing covers the same path: the matrix, `norm.ppf`, building the
distribution, and `cdf`. The first version timed only the `cdf` call. That
left ~0.2 ms of setup outside its timer and read as ~200x at 2 legs, where
the like-for-like ratio is ~15x (measurement-skeptic, 2026-09-28).

Laptop-only. It reads no database and no network, and it must not ship to
the image (`.dockerignore`'s `scripts/*` excludes it by default).

What this does not establish
----------------------------
- **Nothing about the live box.** Fly's `shared-cpu-2x` is not this laptop;
  the timings bound the kernels' cost, they do not measure it in production.
  `inspect_live_proc.py --diff` is the live reading.
- **The market shapes are synthetic.** 145 two-way markets x 20 books
  matches the recorder's measured scale (~290 fair prices a pass, 12-31
  books), not any particular slate. Prices are drawn with a fixed seed.
- **The copula legs are synthetic too.** Each leg is 0.55 with pairwise
  correlations of 0.2-0.3 supplied as overrides; a real ladder's legs and
  correlations differ, and a leg count above 6 is never timed.
  The ladder passes no overrides, so its real correlations are the defaults
  (0.02-0.05), not 0.2-0.3.
- **"The Genz CDF agrees" holds only at these inputs.** The printed
  disagreement is between two estimators of one quantity at the timed
  shapes. The four rows share one Monte Carlo seed, so they are not four
  independent checks. It says nothing about the rows the ladder and the hedge
  actually price.
- **The ratio shrinks as legs are added.** Past 6 legs it falls toward ~2.5x
  at 12 (an unrecorded probe). The ladder's maximum is 6.
- **Timings are one machine's spread, not bounds.** A fourth run can land
  outside the ranges three runs gave.
"""

from __future__ import annotations

import argparse
import random
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from scipy.stats import multivariate_normal, norm  # noqa: E402

from backend.core.correlation import (  # noqa: E402
    Leg,
    correlation_matrix,
    joint_probability_all,
)
from backend.core.devig import consensus_devig  # noqa: E402

MARKETS = 145
BOOKS = 20
LEG_COUNTS = (2, 3, 4, 6)
# Pairs of legs given a measured-looking correlation; everything else is a
# different fixture on the same day in the same league.
OVERRIDES = {("l0", "l1"): 0.3, ("l2", "l3"): 0.2, ("l4", "l5"): 0.25}


def _market(rng: random.Random) -> dict[str, list[float]]:
    books = {}
    for j in range(BOOKS):
        p = rng.uniform(0.3, 0.7)
        margin = rng.uniform(1.02, 1.07)
        books[f"book{j}"] = [1 / (p * margin), 1 / ((1 - p) * margin)]
    return books


def time_devig(reps: int) -> list[float]:
    """Wall ms for one pass's worth of `consensus_devig`, once per rep."""
    rng = random.Random(20260928)
    markets = [_market(rng) for _ in range(MARKETS)]
    out = []
    for _ in range(reps):
        start = time.perf_counter()
        for quotes in markets:
            consensus_devig(("home", "away"), quotes)
        out.append((time.perf_counter() - start) * 1000)
    return out


def _legs(n: int) -> tuple[list[Leg], dict]:
    legs = [Leg(f"l{i}", 0.55, f"E{i}", "nba", 0) for i in range(n)]
    names = {leg.label for leg in legs}
    overrides = {k: v for k, v in OVERRIDES.items() if set(k) <= names}
    return legs, overrides


def time_copula(n: int, reps: int) -> tuple[list[float], float]:
    """Wall ms per `joint_probability_all` call, and the value it returned."""
    legs, overrides = _legs(n)
    out = []
    value = float("nan")
    for _ in range(reps):
        start = time.perf_counter()
        value = joint_probability_all(legs, overrides=overrides)
        out.append((time.perf_counter() - start) * 1000)
    return out, value


def genz_joint(legs: list[Leg], overrides: dict) -> float:
    """The same orthant probability by scipy's CDF, from the same legs.

    Mirrors `joint_probability_all` step for step, so the two timings charge
    both methods for the same setup.
    """
    matrix = correlation_matrix(legs, overrides=overrides)
    thresholds = norm.ppf([leg.probability for leg in legs])
    dist = multivariate_normal(mean=np.zeros(len(legs)), cov=matrix, seed=20260807)
    return float(dist.cdf(thresholds))


def time_genz(n: int, reps: int) -> tuple[list[float], float]:
    """Wall ms per `genz_joint` call, end to end, and the value it returned."""
    legs, overrides = _legs(n)
    out = []
    value = float("nan")
    for _ in range(reps):
        start = time.perf_counter()
        value = genz_joint(legs, overrides)
        out.append((time.perf_counter() - start) * 1000)
    return out, value


def _summary(ms: list[float]) -> str:
    return f"median {statistics.median(ms):8.2f} ms  (min {min(ms):.2f}, max {max(ms):.2f})"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reps", type=int, default=5)
    args = parser.parse_args(argv)

    devig_ms = time_devig(args.reps)
    per_book_us = statistics.median(devig_ms) * 1000 / (MARKETS * BOOKS)
    print(f"devig  {MARKETS} markets x {BOOKS} books   {_summary(devig_ms)}"
          f"  = {per_book_us:.1f} us per book")
    print()
    print(f"{'legs':>4}  {'monte carlo (200k draws)':<46}  {'genz cdf, end to end':<46}"
          f"  {'mc':>8}  {'genz':>8}  {'diff pts':>8}")
    for n in LEG_COUNTS:
        mc_ms, mc = time_copula(n, args.reps)
        ex_ms, ex = time_genz(n, args.reps)
        print(f"{n:>4}  {_summary(mc_ms):<46}  {_summary(ex_ms):<46}"
              f"  {mc:8.5f}  {ex:8.5f}  {(mc - ex) * 100:+8.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
