"""The CLV pass-through coefficient `beta`, and its cluster-robust error.

Registered in `docs/measurements/2026-08-09-preregistration-clv-signal-test.md`.
**Nothing here decides anything the registration does not already decide.** The
model, the population, the cluster key, the multiplier and all four verdict
branches are fixed in that file; this module is an implementation of them, and a
disagreement between the two is a bug in this file.

The model
---------
    clv_tenths = alpha + beta * edge_tenths + gamma * half_spread_tenths + e

`beta` is the estimand: tenths of realised closing-line value per tenth of
claimed edge. It is dimensionless. `beta = 0` means the engine's edge number
carries no information about where the market goes.

**`half_spread_tenths` is a control and its presence is the whole design.**
Correction C2 of the registration: `edge_tenths` and `clv_tenths` are both
measured against the ask, so the half-spread enters both and induces a positive
slope **with no signal present at all**. Omitting it does not make the test
conservative; it makes it wrong in the flattering direction. A run that cannot
supply it does not fall back to a two-variable fit -- it refuses. That is P1.

Why the standard error is not the classical one
-----------------------------------------------
Rows are not independent. A prop ladder on one game moves together, and one
event contributes dozens of rows that share a fixture, a consensus and a clock.
Classical OLS errors treat those as independent observations and understate the
true error by roughly the square root of the average cluster size -- here about
7, so a naive `se` is ~2.6x too small and every interval built on it is fiction.

The sandwich, exactly as registered:

    Var(beta_hat) = (X'X)^-1 [ G/(G-1) * sum_c (X_c' e_c)(X_c' e_c)' ] (X'X)^-1

`G/(G-1)` and nothing else. There is no `(n-1)/(n-k)` term, deliberately: the
registration fixed this form, and adding a second finite-sample correction
because it is conventional elsewhere would change the published number without
an amendment.

What this module does not establish
------------------------------------
- **Nothing at `G < 300`.** `verdict()` returns `UNRESOLVED` below the floor and
  will not return `SIGNAL` or `NO SIGNAL` there, however extreme the estimate.
  The floor is not a significance threshold -- the always-valid boundary handles
  that -- it is the point below which the test cannot resolve any plausible
  value of `beta`.
- **Nothing about causation.** A positive `beta` says the engine's edge number
  predicts closing-line movement. It does not say the edge is tradeable, that it
  survives fees, or that it would have been fillable at the quoted size.
- **Nothing about a population it was not given.** This module fits what it is
  handed. Whether those rows are the registered §2 population is decided by the
  extraction query and asserted by `tests/test_preregistration_population.py`,
  not here.
- **`beta_hat` alone is never a verdict.** Every consumer must read
  `se_cluster`, `G`, and the boundary. The one-number habit is what the
  always-valid multiplier exists to defeat.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

import numpy as np

from ..gate import always_valid_multiplier

# The registered floor for a declaring look, and the registered NO-SIGNAL
# threshold. Both live in the registration; they are named here so a reader can
# see them without a second file, and pinned by tests so they cannot drift.
MIN_CLUSTERS_TO_DECLARE = 300
NO_SIGNAL_UPPER_LIMIT = 0.40
FULL_PASS_THROUGH = 1.0

# §P1: below this fraction of rows carrying a half-spread, the primary analysis
# does not run.
MIN_HALF_SPREAD_COVERAGE = 0.90

ALPHA = 0.05


class SignalTestRefused(Exception):
    """Raised when a precondition fails, rather than returning a number.

    A refusal is louder than a caveat. The failure this prevents is a run that
    quietly fits two variables because the third was missing, and reports a
    `beta` that the registration says may not be computed at all.
    """


@dataclass(frozen=True)
class Observation:
    cluster_key: str
    edge_tenths: float
    clv_tenths: float
    half_spread_tenths: Optional[float]


@dataclass(frozen=True)
class Fit:
    """A fitted model and everything needed to read it honestly."""

    beta_hat: float
    gamma_hat: float
    alpha_hat: float
    se_cluster: float
    se_classical: float
    n_rows: int
    n_clusters: int
    multiplier: float

    @property
    def lower(self) -> float:
        """Always-valid lower limit. The SIGNAL branch reads this, not `beta_hat`."""
        return self.beta_hat - self.multiplier * self.se_cluster

    @property
    def upper(self) -> float:
        return self.beta_hat + self.multiplier * self.se_cluster


def coverage(rows: Sequence[Observation]) -> float:
    """Fraction carrying a half-spread. P1's statistic.

    Returns 0.0 on an empty input rather than raising or returning 1.0. An
    empty population has no coverage; reporting perfect coverage for it would
    let a run with no rows pass the precondition that exists to catch exactly
    that.
    """
    if not rows:
        return 0.0
    return sum(1 for r in rows if r.half_spread_tenths is not None) / len(rows)


def fit(rows: Iterable[Observation], *, tuning: int = MIN_CLUSTERS_TO_DECLARE) -> Fit:
    """Fit the registered model and compute the cluster-robust error.

    Rows without a half-spread are dropped here, having already been counted by
    `coverage`. They are never imputed: a missing quote is not a zero spread,
    and filling one in would delete the C2 confound by arithmetic.
    """
    rows = list(rows)
    usable = [r for r in rows if r.half_spread_tenths is not None]
    if len(usable) < 3:
        raise SignalTestRefused(
            f"{len(usable)} usable row(s); the model has three parameters"
        )

    y = np.array([r.clv_tenths for r in usable], dtype=float)
    X = np.column_stack(
        [
            np.ones(len(usable)),
            np.array([r.edge_tenths for r in usable], dtype=float),
            np.array([r.half_spread_tenths for r in usable], dtype=float),
        ]
    )

    xtx = X.T @ X
    # `pinv`, not `inv`: if `half_spread` is constant -- ADR 0006 measures the
    # pre-game spread at 1.00c at every percentile including the maximum -- the
    # column is collinear with the intercept and `inv` raises. `pinv` returns
    # the minimum-norm solution, `gamma_hat` comes back ~0, and `beta_hat` is
    # unaffected, which is the honest behaviour: a control with no variance
    # controls for nothing and should not abort the fit.
    xtx_inv = np.linalg.pinv(xtx)
    coefficients = xtx_inv @ X.T @ y
    residuals = y - X @ coefficients

    keys = [r.cluster_key for r in usable]
    unique = sorted(set(keys))
    g = len(unique)
    if g < 2:
        raise SignalTestRefused(f"{g} cluster(s); the sandwich needs at least 2")

    index = {k: i for i, k in enumerate(unique)}
    meat = np.zeros((X.shape[1], X.shape[1]))
    scores = np.zeros((g, X.shape[1]))
    for row, key, resid in zip(X, keys, residuals):
        scores[index[key]] += row * resid
    for s in scores:
        meat += np.outer(s, s)
    meat *= g / (g - 1)

    covariance = xtx_inv @ meat @ xtx_inv

    dof = max(1, len(usable) - X.shape[1])
    sigma2 = float(residuals @ residuals) / dof
    classical = np.sqrt(np.diag(sigma2 * xtx_inv))

    return Fit(
        beta_hat=float(coefficients[1]),
        gamma_hat=float(coefficients[2]),
        alpha_hat=float(coefficients[0]),
        se_cluster=float(np.sqrt(covariance[1, 1])),
        se_classical=float(classical[1]),
        n_rows=len(usable),
        n_clusters=g,
        multiplier=always_valid_multiplier(g, tuning=tuning, alpha=ALPHA),
    )


def verdict(f: Fit) -> str:
    """One of SIGNAL / BUG, NOT SIGNAL / NO SIGNAL / UNRESOLVED.

    §6 as amended by §A3. **Both declaring branches read the always-valid LOWER
    limit**, not `beta_hat`. The original rule compared a bare point estimate
    against the ceiling of 1.0, which at the registration's own `se ~= 0.115`
    classifies a true `beta` of exactly 1.0 as BUG half the time -- the design
    foreclosing its own SIGNAL branch. Only a lower limit above 1.0 rules out
    full pass-through from below, which is the sole evidential state in which
    "the engine understates its own edge" is established rather than guessed.

    The order matters: BUG is tested before SIGNAL, because the BUG region is a
    subset of the region where the lower limit clears zero.
    """
    if f.n_clusters < MIN_CLUSTERS_TO_DECLARE:
        return "UNRESOLVED"
    if f.lower > FULL_PASS_THROUGH:
        return "BUG, NOT SIGNAL"
    if f.lower > 0.0:
        return "SIGNAL"
    if f.upper < NO_SIGNAL_UPPER_LIMIT:
        return "NO SIGNAL"
    return "UNRESOLVED"
