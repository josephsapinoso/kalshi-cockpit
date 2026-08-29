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

The floor, and why it moved
---------------------------
**`G < 713`, not `G < 300`, since Amendment 2 §B4 (2026-08-29).** The power
check's level-test section carried its own amendment trigger -- *"`sigma` is
therefore a reportable quantity at every interim look, and if it comes in above
30 tenths this document must be amended to raise the floor"* -- and the trigger
fired: `sd(clv_tenths)` came in at 30.1481 pooled and **31.6915 on the modal
population the declaration is made on**. Solving the power check's own
expression, unchanged, for the power check's own 3.8-tenth target:

    always_valid_multiplier(713, tuning=300, alpha=0.05) * 31.6915 / sqrt(713)
        = 3.2002 * 31.6915 / 26.702 = 3.7982  <= 3.8

Two things follow that a reader has to hold together:

- **`tuning` stays at 300** (§B6(4)). It is the Robbins mixture parameter, not
  the floor, and it appears in every interval this registration has published.
  Re-tuning it to 713 would silently restate the 2026-08-16 and 2026-08-25
  intervals. `BOUNDARY_TUNING` exists so the two numbers cannot be confused
  again -- they were one constant here until the floor moved.
- **The floor is a RATCHET.** It is fixed once, at 713. A later look measuring
  a *smaller* `sigma` does not lower it; a later look measuring a larger one
  raises it again, by a further dated amendment written before that look
  declares. A floor recomputed from whatever noise a look happens to see is a
  threshold chosen after the data, which is the exact freedom the registration
  exists to remove.

What this module does not establish
------------------------------------
- **Nothing at `G < 713`.** `verdict()` returns `UNRESOLVED` below the floor and
  will not return `SIGNAL` or `NO SIGNAL` there, however extreme the estimate.
  The floor is not a significance threshold -- the always-valid boundary handles
  that -- it is the point below which the test cannot resolve any plausible
  value of `beta`.
- **Nothing about whether nominal `G` is the right unit.** `effective_clusters`
  reports the Kish count on leverage and §B7 makes it a **mandatory reportable,
  never a threshold**: at the 2026-08-25 look `G = 311` nominal was `4.26`
  effective, one WNBA game carrying 43.80% of the leverage alone. Restating the
  floor in `G_eff` after seeing that it is small would be a post-hoc estimator
  change, so it is not done. A `G` printed without its `G_eff` is the thing this
  module now makes impossible, and that is all it is.
- **Nothing about causation.** A positive `beta` says the engine's edge number
  predicts closing-line movement. It does not say the edge is tradeable, that it
  survives fees, or that it would have been fillable at the quoted size.
- **Nothing about a population it was not given.** This module fits what it is
  handed. Whether those rows are the registered §2 population is decided by the
  extraction query and asserted by `tests/test_preregistration_population.py`,
  not here.
- **Nothing about a group's own slope.** §A4's leave-one-group-out branch is
  implemented here and is **strictly one-way**: it turns SIGNAL or NO SIGNAL
  into UNRESOLVED and can never raise a verdict. No group result is a finding.
- **`beta_hat` alone is never a verdict.** Every consumer must read
  `se_cluster`, `G`, `G_eff` and the boundary. The one-number habit is what the
  always-valid multiplier exists to defeat.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

import numpy as np

from ..gate import always_valid_multiplier

# The registered floor for a declaring look, and the registered NO-SIGNAL
# threshold. Both live in the registration; they are named here so a reader can
# see them without a second file, and pinned by tests so they cannot drift.
#
# **713 IS A RATCHET, raised from 300 by Amendment 2 §B4 on 2026-08-29.** It is
# fixed once, at 713, and it DOES NOT FALL if a later look happens to measure a
# smaller `sigma`; a larger `sigma` raises it again in a further dated
# amendment, written before that look declares anything. Recomputing a floor
# from the noise a look happens to see is choosing a threshold after the data.
#
# Do not lower this to make a verdict reachable. The registration governs where
# it and this file disagree, and it says 713.
MIN_CLUSTERS_TO_DECLARE = 713
NO_SIGNAL_UPPER_LIMIT = 0.40
FULL_PASS_THROUGH = 1.0

# **The Robbins mixture parameter, and NOT the floor.** §B6(4): `tuning` sets
# where the always-valid boundary is most efficient and it appears in every
# interval this registration has ever published, so re-tuning it to 713 would
# silently restate the widths of the 2026-08-16 and 2026-08-25 intervals -- the
# one thing Amendment 2 forbids. It was the *same constant* as the floor until
# the floor moved, which is precisely how that restatement would have happened
# without anyone choosing it.
BOUNDARY_TUNING = 300

# §A4's testability threshold for the leave-one-group-out downgrade, and it is
# **deliberately still 300**. Amendment 2 §B6(1) raises "every occurrence of
# `G >= 300` **as the declaring floor**"; this is not that. It is the size of
# population left after a group is removed, below which the recomputation has
# nothing to compare against. Raising it to 713 would make FEWER groups testable
# and therefore make a downgrade RARER -- the flattering direction -- so it
# stays where §A4 wrote it.
MIN_CLUSTERS_FOR_LOGO_TEST = 300

# §A4: a group whose removal would leave `G < 300` cannot be tested and is not
# grounds for downgrade, but above this leverage share the write-up **must
# state, in those words**, that the pooled result is one group's result.
ONE_GROUP_LEVERAGE_SHARE = 0.50

# §B4's ratchet check, reportable at every look (§B6(5)): `sd(clv_tenths)` on
# the modal-version population. Above this the floor is raised again by a
# further dated amendment BEFORE the next declaring look. This constant is the
# value the current floor of 713 was computed at, not a trigger for code to act
# on by itself -- a floor change is an amendment, never an edit here.
RATCHET_SIGMA_TENTHS = 31.6915

# Relative floor below which the residualised regressor is treated as having no
# variance at all. It is not a tuning knob: `1e-24` is far below any real
# residual and far above the `~1e-30` a perfectly constant regressor produces
# from `pinv`'s rounding, so nothing measurable is ever discarded by it and
# nothing unmeasurable is ever reported as a leverage share.
RESIDUAL_DUST = 1e-24

# §P1's floor. The value is unchanged by §A8.2; what changed is the statistic it
# is applied to -- `matched / total`, not the fraction of rows carrying a
# half-spread. The name predates the amendment and is kept because it is
# imported by name elsewhere; read `coverage`'s docstring before using it.
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
    # §B7's two mandatory reportables, and they are REQUIRED FIELDS on purpose.
    # A default would let a caller construct a `Fit` carrying `G` and no
    # effective count, which is the state the 2026-08-24 screen was in when it
    # printed "311 of 300 games" -- a nominal count with nothing beside it
    # saying that 311 was 4.26 games' worth of evidence. `None` is the reading
    # for "the regressor has no residual variance", never 0 and never `G`.
    g_eff: Optional[float]
    largest_cluster_leverage_share: Optional[float]

    @property
    def lower(self) -> float:
        """Always-valid lower limit. The SIGNAL branch reads this, not `beta_hat`."""
        return self.beta_hat - self.multiplier * self.se_cluster

    @property
    def upper(self) -> float:
        return self.beta_hat + self.multiplier * self.se_cluster


def coverage(rows: Sequence[Observation]) -> float:
    """Fraction carrying a half-spread. **NOT P1 — superseded by §A8.2.**

    This was P1's statistic as originally registered. §A8.2 replaced it:

        "P1's 0.90 floor now applies to `matched / total`, not to non-NULL
        half-spread coverage. That is a strictly tighter gate than the one
        registered."

    The difference is not cosmetic and it has already bitten once. This function
    cannot distinguish a control recovered from the *right* quote from one
    recovered from the wrong one -- both are non-NULL. On the 2026-08-16 record
    the two statistics read **1.0000 and 0.5054**, and the harness gated on this
    one, so a look that §A8.2 would have refused reported a `beta_hat`. See
    `docs/measurements/2026-08-16-quote-join-bias-result.md`.

    **P1 lives in `scripts/run_signal_test.py:a82_counts`**, which needs `side`
    and `entry_ask_tenths` -- columns an `Observation` deliberately does not
    carry, because the fit has no business seeing them. This function is
    retained as the `no_quote` sub-statistic, which is still worth printing.

    Returns 0.0 on an empty input rather than raising or returning 1.0. An
    empty population has no coverage; reporting perfect coverage for it would
    let a run with no rows pass the precondition that exists to catch exactly
    that.
    """
    if not rows:
        return 0.0
    return sum(1 for r in rows if r.half_spread_tenths is not None) / len(rows)


def usable_rows(rows: Sequence[Observation]) -> list[Observation]:
    """The rows the fit actually sees. A missing quote is not a zero spread."""
    return [r for r in rows if r.half_spread_tenths is not None]


def residualised_edge(rows: Sequence[Observation]) -> np.ndarray:
    """`x_tilde` -- `edge_tenths` residualised on `half_spread_tenths` and the
    intercept, over the usable rows in the order `usable_rows` returns them.

    §A4 names this quantity and says why it is the one that matters: it is
    *"the quantity that actually weights the partial slope"*. By Frisch-Waugh
    the partial slope on `edge` in the three-variable model is exactly the
    simple slope of `clv` on `x_tilde`, so `x_tilde**2` is a row's weight in
    `beta_hat` -- the raw `edge**2` is not, because part of `edge` is the
    control's job.

    `pinv` for the same reason `fit` uses it: ADR 0006 measures the pre-game
    half-spread at 1.00c at every percentile, so the control can be collinear
    with the intercept, and `inv` would raise where the honest answer is that a
    control with no variance residualises nothing.

    **Dust is snapped to exact zero, and it has to be.** A constant `edge`
    residualises to residuals of order `1e-15` rather than to zeros, and their
    squares are positive -- so every downstream leverage share would come back
    as a real number computed entirely from floating-point error, and `G_eff`
    would read as a clean equal-weight `G`. That is the one wrong answer this
    statistic must never give, because it is indistinguishable from the honest
    equal-leverage case. Below `RESIDUAL_DUST` of the regressor's own scale the
    residual is not small, it is absent, and the leverage is unreadable.
    """
    usable = usable_rows(rows)
    if not usable:
        return np.zeros(0)
    edge = np.array([r.edge_tenths for r in usable], dtype=float)
    controls = np.column_stack(
        [
            np.ones(len(usable)),
            np.array([r.half_spread_tenths for r in usable], dtype=float),
        ]
    )
    coefficients = np.linalg.pinv(controls.T @ controls) @ controls.T @ edge
    residual = edge - controls @ coefficients
    scale = float(edge @ edge)
    if float(residual @ residual) <= RESIDUAL_DUST * max(scale, 1.0):
        return np.zeros(len(usable))
    return residual


def cluster_leverage(rows: Sequence[Observation]) -> dict[str, float]:
    """Each cluster's `sum_i (x_tilde_i)**2`, the weight it carries on `beta`.

    Keys are cluster keys; the values are unnormalised. Empty when no row is
    usable, which is a different statement from every cluster carrying zero.
    """
    usable = usable_rows(rows)
    weights: dict[str, float] = defaultdict(float)
    for row, x in zip(usable, residualised_edge(rows)):
        weights[row.cluster_key] += float(x) * float(x)
    return dict(weights)


def effective_clusters(rows: Sequence[Observation]) -> Optional[float]:
    """`G_eff` -- Kish's effective sample size over the per-cluster leverage.

        G_eff = (sum_c w_c)**2 / sum_c w_c**2 ,   w_c = sum_{i in c} x_tilde_i**2

    **Which formula, and why this one.** §B7 names the statistic *"inverse
    Herfindahl on leverage"*; Kish's effective sample size for weights `w` is
    `(sum w)^2 / sum w^2`, which is identically `1 / sum_c s_c**2` once the
    weights are put on shares `s_c = w_c / sum w`. They are the same number, so
    the audit's `4.26` at nominal `G = 311` is reproducible from this function.
    Kish's is the form written here because it needs no normalisation step and
    therefore cannot silently divide by a zero total.

    **It equals `G` exactly when every cluster carries equal leverage**, which
    is the assumption `sqrt(G)` in the power check is a function of. A `G_eff`
    that always came back equal to `G` would mean the leverage was never
    computed -- the failure this function exists to make visible.

    **Returns `None`, never `0` and never `G`, when the total leverage is zero**
    -- a constant regressor has no residual variance and therefore no leverage
    to concentrate. Unreadable resolves to `None`; a caller refuses rather than
    substitutes.

    This is a **reportable, not a threshold** (§B7). Nothing in `verdict()`
    reads it. Restating the floor in `G_eff` after seeing that `G_eff` is small
    would be choosing an estimator from the answer.
    """
    weights = list(cluster_leverage(rows).values())
    total = sum(weights)
    if total <= 0.0:
        return None
    return (total * total) / sum(w * w for w in weights)


def largest_cluster_leverage_share(rows: Sequence[Observation]) -> Optional[float]:
    """The biggest single cluster's share of the leverage. `None` if unreadable.

    §A9(5) and the repo rule: the largest contributor's share goes on the same
    line as the aggregate. On the 2026-08-25 record this was 0.4380 -- one WNBA
    game -- and the harness printed a row-count share of a group that is not
    registered instead.
    """
    weights = list(cluster_leverage(rows).values())
    total = sum(weights)
    if total <= 0.0:
        return None
    return max(weights) / total


def fit(rows: Iterable[Observation], *, tuning: int = BOUNDARY_TUNING) -> Fit:
    """Fit the registered model and compute the cluster-robust error.

    Rows without a half-spread are dropped here, having already been counted by
    `coverage`. They are never imputed: a missing quote is not a zero spread,
    and filling one in would delete the C2 confound by arithmetic.
    """
    rows = list(rows)
    usable = usable_rows(rows)
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
        # Computed here rather than left to the caller, so that every `Fit`
        # that exists anywhere -- primary, pooled, per-group -- carries its own
        # effective count. A reportable a caller has to remember to ask for is
        # a reportable that goes missing on the look that matters.
        g_eff=effective_clusters(usable),
        largest_cluster_leverage_share=largest_cluster_leverage_share(usable),
    )


@dataclass(frozen=True)
class LeaveOneGroupOut:
    """One pre-registered group's §A4 row: its weight, and the fit without it.

    `leverage_share` is *"its share of `sum_i (x_tilde_i)^2`"*, which §A4
    requires *"Reported beside `beta_hat`, **always**"* -- not only when a
    downgrade fires, and not only when a declaration is being made.

    `testable` is false when removing the group would leave `G` below
    `MIN_CLUSTERS_FOR_LOGO_TEST`. §A4: those groups *"cannot be tested"* and are
    **not** grounds for downgrade, because there is nothing left to compare
    against and treating that as a downgrade would foreclose SIGNAL whenever one
    group is most of the sample.
    """

    name: str
    n_rows: int
    n_clusters: int
    leverage_share: Optional[float]
    clusters_remaining: int
    testable: bool
    beta_hat: Optional[float]
    lower: Optional[float]
    upper: Optional[float]
    refusal: Optional[str]

    @property
    def one_group_result(self) -> bool:
        """§A4's mandatory sentence trigger: untestable and above half the
        leverage means *the pooled result is one group's result*."""
        return (
            not self.testable
            and self.leverage_share is not None
            and self.leverage_share > ONE_GROUP_LEVERAGE_SHARE
        )


def leave_one_group_out(
    rows: Sequence[Observation],
    groups: Sequence[tuple[str, Sequence[bool]]],
    *,
    min_clusters_remaining: int = MIN_CLUSTERS_FOR_LOGO_TEST,
    tuning: int = BOUNDARY_TUNING,
) -> list[LeaveOneGroupOut]:
    """§A4's downgrade test, computed. One row per pre-registered group.

    `groups` is `(name, membership_mask)` with one mask entry per row of `rows`,
    in order. Membership is decided by the caller because it needs
    `suppressed_reason` and `entry_ask_tenths`, which an `Observation`
    deliberately does not carry -- the fit has no business seeing them. **Which
    groups exist is fixed by §A4 and no others may be introduced after the data
    is read**; this function does not choose them, it evaluates them.

    Groups are **non-exclusive**: a composite row belongs to every group whose
    code it carries, so the masks overlap and are meant to.

    **Removal only reduces `G` when it empties a cluster.** The pre-audit
    reasoning that the test was near-vacuous at `G = 311` against a floor of 300
    -- only a group of <= 11 clusters could be removed -- was wrong in the
    flattering direction: `too_few_books` spans 190 clusters and its removal
    leaves 271. The test is live and is computed, never argued away.

    Leverage shares are taken against the leverage of the population **as
    passed**, so the rows sum to 1 across the record but not across groups.
    `None` when the total leverage is zero, never 0.0.
    """
    rows = list(rows)
    usable = usable_rows(rows)
    usable_mask = [r.half_spread_tenths is not None for r in rows]

    row_leverage = [float(x) * float(x) for x in residualised_edge(rows)]
    total_leverage = sum(row_leverage)

    out: list[LeaveOneGroupOut] = []
    for name, mask in groups:
        mask = list(mask)
        if len(mask) != len(rows):
            raise SignalTestRefused(
                f"group {name!r} carries {len(mask)} mask entries for "
                f"{len(rows)} rows; a misaligned mask is a different population"
            )
        # Masks are over every row; leverage and `G` are over the usable ones,
        # because those are the rows the fit and therefore `beta` sees.
        usable_group = [m for m, u in zip(mask, usable_mask) if u]
        share: Optional[float] = None
        if total_leverage > 0.0:
            share = sum(
                lev for lev, m in zip(row_leverage, usable_group) if m
            ) / total_leverage

        in_group = {r.cluster_key for r, m in zip(usable, usable_group) if m}
        remaining_rows = [r for r, m in zip(rows, mask) if not m]
        remaining_clusters = {
            r.cluster_key for r in usable_rows(remaining_rows)
        }
        remaining = len(remaining_clusters)

        if remaining < min_clusters_remaining:
            out.append(
                LeaveOneGroupOut(
                    name=name,
                    n_rows=sum(1 for m in mask if m),
                    n_clusters=len(in_group),
                    leverage_share=share,
                    clusters_remaining=remaining,
                    testable=False,
                    beta_hat=None,
                    lower=None,
                    upper=None,
                    refusal=(
                        f"removal leaves G = {remaining}, below "
                        f"{min_clusters_remaining}; §A4 says this is UNTESTABLE "
                        f"and is not grounds for downgrade"
                    ),
                )
            )
            continue

        try:
            refitted = fit(remaining_rows, tuning=tuning)
        except SignalTestRefused as exc:
            out.append(
                LeaveOneGroupOut(
                    name=name,
                    n_rows=sum(1 for m in mask if m),
                    n_clusters=len(in_group),
                    leverage_share=share,
                    clusters_remaining=remaining,
                    testable=False,
                    beta_hat=None,
                    lower=None,
                    upper=None,
                    refusal=str(exc),
                )
            )
            continue

        out.append(
            LeaveOneGroupOut(
                name=name,
                n_rows=sum(1 for m in mask if m),
                n_clusters=len(in_group),
                leverage_share=share,
                clusters_remaining=remaining,
                testable=True,
                beta_hat=refitted.beta_hat,
                lower=refitted.lower,
                upper=refitted.upper,
                refusal=None,
            )
        )
    return out


@dataclass(frozen=True)
class VerdictResult:
    """The registered verdict, and the §6 verdict it came from.

    Both are carried because a downgrade is a *finding about the parts
    disagreeing* and vanishes if only the final string survives. `downgraded_by`
    names the group in §A4's own words: *"The write-up names the group that
    caused the downgrade."*
    """

    verdict: str
    section6_verdict: str
    downgraded_by: Optional[str]


def section6_verdict(f: Fit) -> str:
    """§6 on the pooled fit alone. **This is not the registered verdict.**

    §6 as amended by §A3. **Both declaring branches read the always-valid LOWER
    limit**, not `beta_hat`. The original rule compared a bare point estimate
    against the ceiling of 1.0, which at the registration's own `se ~= 0.115`
    classifies a true `beta` of exactly 1.0 as BUG half the time -- the design
    foreclosing its own SIGNAL branch. Only a lower limit above 1.0 rules out
    full pass-through from below, which is the sole evidential state in which
    "the engine understates its own edge" is established rather than guessed.

    The order matters: BUG is tested before SIGNAL, because the BUG region is a
    subset of the region where the lower limit clears zero.

    §A4 can still downgrade what this returns, which is why `verdict()` and not
    this function is what a caller reports.
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


def verdict(f: Fit, downgrades: Sequence[LeaveOneGroupOut]) -> VerdictResult:
    """The registered verdict: §6, then §A4's leave-one-group-out downgrade.

    **`downgrades` is a required argument, and that is the whole point of this
    signature.** Until 2026-08-29 this function took a `Fit` alone and returned
    §6's string; Amendment 2 §B8(a) records that as an unimplemented branch and
    §B9 forbids a declaration at `G >= 713` until it executes in code. A default
    of `()` would have kept every existing caller working and left the guard
    exactly as absent as it was -- the repo's "built but never called" pattern
    with a nicer signature. A caller with no groups must say so by passing `()`.

    §A4, verbatim, and this implements those two sentences and no others:

        - a **SIGNAL** verdict is downgraded to **UNRESOLVED** if any such
          recomputation returns `beta_hat <= 0`;
        - a **NO SIGNAL** verdict is downgraded to **UNRESOLVED** if any such
          recomputation returns an always-valid upper limit at or above 0.40.

    Three properties, each a place a variant would have been easy to invent:

    - **Strictly one-way.** It turns SIGNAL or NO SIGNAL into UNRESOLVED. It
      never raises a verdict and never turns UNRESOLVED into anything, so
      running it can only ever make declaring harder.
    - **`BUG, NOT SIGNAL` is not downgraded**, because §A4 does not name it. It
      is a defect report rather than a claim of edge, and inventing a branch the
      registration did not write would be an amendment made in code.
    - **Only `testable` groups count.** §A4: a group whose removal leaves `G`
      below the threshold *"cannot be tested"* and is *"not grounds for
      downgrade"*. Its leverage share is still reported, and above 0.50 the
      write-up owes the sentence `LeaveOneGroupOut.one_group_result` flags.

    The test is on the **claim** -- does the sign survive, does the ruling-out
    survive -- not on statistical significance. §A4 fixes that in advance and
    says why: losing significance after discarding a quarter of the data is a
    power artefact, whereas a point estimate crossing zero when one group is
    removed is the parts disagreeing.
    """
    base = section6_verdict(f)
    testable = [d for d in downgrades if d.testable]

    if base == "SIGNAL":
        for d in testable:
            if d.beta_hat is not None and d.beta_hat <= 0.0:
                return VerdictResult("UNRESOLVED", base, d.name)
    elif base == "NO SIGNAL":
        for d in testable:
            if d.upper is not None and d.upper >= NO_SIGNAL_UPPER_LIMIT:
                return VerdictResult("UNRESOLVED", base, d.name)

    return VerdictResult(base, base, None)
