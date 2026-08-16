"""The four invariants the registration asserts before any result is believed.

`docs/measurements/2026-08-09-preregistration-clv-signal-test.md` §3 and §A7
fix these, and the registration says why each exists: they are *chosen so a
wrong implementation gives a different answer*. Two pin the standard error, two
pin the partial-slope arithmetic, and §A7 records that the first three together
still do not catch the defect the control exists to prevent -- only A3-d does.

Everything here is synthetic. No repository data reaches this file, and no test
below is permitted to be relaxed to make an implementation pass.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.analysis.signal_test import (
    FULL_PASS_THROUGH,
    MIN_CLUSTERS_TO_DECLARE,
    NO_SIGNAL_UPPER_LIMIT,
    Fit,
    Observation,
    SignalTestRefused,
    coverage,
    fit,
    verdict,
)


def _obs(cluster, edge, clv, half=1.0):
    return Observation(
        cluster_key=str(cluster),
        edge_tenths=float(edge),
        clv_tenths=float(clv),
        half_spread_tenths=None if half is None else float(half),
    )


class TestSingletonClustersReproduceClassicalOLS:
    """§3, anchor one. With `G == N` the sandwich collapses to the classical form.

    Mutation: drop the `G/(G-1)` factor. At G = 60 that is a 0.8% error --
    small enough to look like floating point and large enough to move a
    boundary, which is exactly why the registration pins it as an equality
    rather than as a range.
    """

    def test_the_two_standard_errors_agree(self):
        rng = np.random.default_rng(11)
        n = 60
        x = rng.normal(0, 10, n)
        w = rng.normal(0, 3, n)
        y = 3 + 0.6 * x + 2 * w + rng.normal(0, 2, n)
        rows = [_obs(i, x[i], y[i], w[i]) for i in range(n)]

        f = fit(rows)
        assert f.n_clusters == n
        # The collapse is exact only up to the G/(G-1) factor the registration
        # keeps, so compare the corrected classical error.
        corrected = f.se_classical * np.sqrt(n / (n - 1))
        assert f.se_cluster == pytest.approx(corrected, rel=0.06)

    def test_the_correction_factor_is_exactly_G_over_G_minus_1(self):
        """Pins `G/(G-1)` against an independently computed HC0 sandwich.

        The registration says singleton clusters "reproduce the classical OLS
        standard error exactly". That is true only up to two differences the
        phrase hides: with `G == N` the sandwich is the **heteroskedasticity-
        robust** (HC0) form, not the homoskedastic one, and it carries
        `G/(G-1)` where classical OLS carries `n/(n-k)`. At `n = 8, k = 3`
        those are 1.14 and 1.60 -- so the classical error is the LARGER of the
        two, and an earlier version of this test asserted the inequality
        backwards.

        Computing HC0 here independently and multiplying by `sqrt(G/(G-1))`
        pins the factor exactly rather than approximately, which is what the
        registration is actually asking for.

        Mutation: `meat *= 1.0`. This fails by 7% at n = 8 and by 0.2% at
        n = 300 -- small enough to look like floating point, large enough to
        move a boundary. That is why it is an equality.
        """
        rng = np.random.default_rng(12)
        n = 8
        x = rng.normal(0, 10, n)
        w = rng.normal(0, 3, n)
        y = 0.5 * x + 1.5 * w + rng.normal(0, 1, n)
        f = fit([_obs(i, x[i], y[i], w[i]) for i in range(n)])

        X = np.column_stack([np.ones(n), x, w])
        xtx_inv = np.linalg.pinv(X.T @ X)
        resid = y - X @ (xtx_inv @ X.T @ y)
        meat = sum(np.outer(X[i] * resid[i], X[i] * resid[i]) for i in range(n))
        hc0 = float(np.sqrt((xtx_inv @ meat @ xtx_inv)[1, 1]))

        assert f.se_cluster == pytest.approx(hc0 * np.sqrt(n / (n - 1)), rel=1e-12)
        assert f.se_cluster != pytest.approx(hc0, rel=1e-6)


class TestDuplicatingEveryRowChangesNothing:
    """§3, anchor two. The naive estimator returns `stderr / sqrt(k)` here.

    This states the old bug as an invariant: duplicating rows *within* the same
    clusters adds no independent information, so a correct cluster-robust error
    is unmoved. The classical error is not, which is what makes the test
    discriminating rather than tautological.
    """

    @pytest.mark.parametrize("k", [2, 5])
    def test_beta_and_cluster_se_are_bit_identical(self, k):
        rng = np.random.default_rng(13)
        n = 40
        x = rng.normal(0, 10, n)
        w = rng.normal(0, 3, n)
        y = 3 + 0.6 * x + 2 * w + rng.normal(0, 2, n)
        base = [_obs(i % 8, x[i], y[i], w[i]) for i in range(n)]

        one = fit(base)
        many = fit(base * k)

        assert many.n_clusters == one.n_clusters
        assert many.beta_hat == pytest.approx(one.beta_hat, rel=1e-12)
        assert many.se_cluster == pytest.approx(one.se_cluster, rel=1e-10)

    def test_the_classical_error_does_shrink(self):
        """The control that makes the invariant above meaningful.

        If the classical error were also unmoved, the test would pass on an
        estimator that ignored clustering entirely.
        """
        rng = np.random.default_rng(14)
        n = 40
        x = rng.normal(0, 10, n)
        w = rng.normal(0, 3, n)
        y = 0.6 * x + 2 * w + rng.normal(0, 2, n)
        base = [_obs(i % 8, x[i], y[i], w[i]) for i in range(n)]
        assert fit(base * 4).se_classical < fit(base).se_classical * 0.6


class TestAConstantControlCollapsesOntoTheSimpleSlope:
    """§A7 invariant A3-c. Pins the rank-deficiency handling.

    The registration is explicit that this is **necessary but not sufficient**:
    an estimator that ignores the control entirely also passes. What it does
    catch is a naive `inv(X'X)`, which raises `Singular matrix` on this input --
    which is why `fit` uses `pinv`.
    """

    def test_beta_equals_the_simple_regression_slope(self):
        rng = np.random.default_rng(15)
        n = 500
        x = rng.normal(0, 10, n)
        y = 3 + 0.6 * x + 2 * 5.0 + rng.normal(0, 2, n)
        rows = [_obs(i % 50, x[i], y[i], 5.0) for i in range(n)]

        f = fit(rows)
        simple = float(np.cov(x, y, bias=True)[0, 1] / np.var(x))
        assert f.beta_hat == pytest.approx(simple, rel=1e-10)

    def test_it_does_not_raise_on_the_collinear_column(self):
        rows = [_obs(i % 4, i, 2 * i, 5.0) for i in range(40)]
        fit(rows)  # must not raise


class TestACorrelatedControlIsActuallyUsed:
    """§A7 invariant A3-d. **This is the one that catches C2's contamination.**

    With `w = 0.5x + noise` and `y = 3 + 0.6x + 2w` exactly, a correct
    estimator returns `beta = 0.600`. An estimator that accepts the control and
    never uses it returns **1.625** -- an error of 2.7x in the *inflating*
    direction, which is precisely the shape correction C2 describes and the
    reason the whole design carries a control at all.

    Mutation: drop the `half_spread` column from `X`. This test then fails by
    2.7x while all three tests above stay green.
    """

    def test_beta_and_gamma_recover_their_true_values(self):
        rng = np.random.default_rng(16)
        n = 500
        x = rng.normal(0, 10, n)
        w = 0.5 * x + rng.normal(0, 5, n)
        y = 3 + 0.6 * x + 2 * w  # no noise

        f = fit([_obs(i % 50, x[i], y[i], w[i]) for i in range(n)])
        assert f.beta_hat == pytest.approx(0.6, abs=1e-9)
        assert f.gamma_hat == pytest.approx(2.0, abs=1e-9)
        assert f.alpha_hat == pytest.approx(3.0, abs=1e-9)

    def test_ignoring_the_control_would_give_a_materially_different_answer(self):
        """Proves the invariant above is discriminating, not decorative."""
        rng = np.random.default_rng(16)
        n = 500
        x = rng.normal(0, 10, n)
        w = 0.5 * x + rng.normal(0, 5, n)
        y = 3 + 0.6 * x + 2 * w
        naive = float(np.cov(x, y, bias=True)[0, 1] / np.var(x))
        assert naive > 1.5  # ~1.625, against a true 0.600


class TestTheDecisionRuleIsTheRegisteredOne:
    """§6 as amended by §A3. Both declaring branches read the LOWER limit."""

    def _fit(self, beta, se, g, multiplier=2.0):
        return Fit(
            beta_hat=beta,
            gamma_hat=0.0,
            alpha_hat=0.0,
            se_cluster=se,
            se_classical=se,
            n_rows=g * 10,
            n_clusters=g,
            multiplier=multiplier,
        )

    def test_below_the_floor_nothing_can_be_declared(self):
        """The registration: a look at `G < 300` "may not declare SIGNAL, BUG
        or NO SIGNAL", however extreme the estimate.

        Mutation: remove the floor check. A huge beta at G = 10 then reads
        SIGNAL, which is the failure the floor exists to prevent and which an
        earlier draft ADR proposed doing deliberately at G = 186.
        """
        for beta in (-5.0, 0.0, 0.5, 5.0):
            f = self._fit(beta, 0.01, g=MIN_CLUSTERS_TO_DECLARE - 1)
            assert verdict(f) == "UNRESOLVED"

    def test_signal_needs_the_lower_limit_above_zero_not_the_point_estimate(self):
        """Mutation: test `beta_hat > 0`. A beta of 0.5 with se 0.4 then reads
        SIGNAL while its interval comfortably contains zero.
        """
        g = MIN_CLUSTERS_TO_DECLARE
        assert verdict(self._fit(0.5, 0.4, g)) != "SIGNAL"
        assert verdict(self._fit(0.5, 0.1, g)) == "SIGNAL"

    def test_bug_needs_the_lower_limit_above_one(self):
        """§A3's correction. A point estimate above 1.0 whose interval still
        contains 1.0 is a FLAG, not a BUG -- the old rule classified a true
        beta of exactly 1.0 as BUG half the time.
        """
        g = MIN_CLUSTERS_TO_DECLARE
        assert verdict(self._fit(1.1, 0.2, g)) == "SIGNAL"
        assert verdict(self._fit(2.0, 0.2, g)) == "BUG, NOT SIGNAL"

    def test_no_signal_needs_the_upper_limit_below_the_registered_threshold(self):
        g = MIN_CLUSTERS_TO_DECLARE
        assert verdict(self._fit(0.0, 0.05, g)) == "NO SIGNAL"
        assert verdict(self._fit(0.0, 0.5, g)) == "UNRESOLVED"

    def test_the_registered_constants_are_not_quietly_moved(self):
        """An earlier ADR draft proposed 0.64 and a floor of 186. Both are
        amendments to the registration, not code changes.
        """
        assert MIN_CLUSTERS_TO_DECLARE == 300
        assert NO_SIGNAL_UPPER_LIMIT == 0.40
        assert FULL_PASS_THROUGH == 1.0


class TestAMissingHalfSpreadIsRefusedNotImputed:
    """P1. A missing quote is not a zero spread.

    Mutation: default `half_spread_tenths` to 0.0. The control then has less
    variance than it should, the C2 contamination is partly restored, and the
    run reports a `beta` the registration says may not be computed.
    """

    def test_rows_without_a_half_spread_are_excluded_from_the_fit(self):
        rows = [_obs(i % 5, i, 2 * i, 1.0 + (i % 3)) for i in range(30)]
        rows += [_obs(99, 5, 5, None) for _ in range(5)]
        f = fit(rows)
        assert f.n_rows == 30

    def test_coverage_reports_the_fraction(self):
        rows = [_obs(1, 1, 1, 1.0)] * 9 + [_obs(2, 1, 1, None)]
        assert coverage(rows) == pytest.approx(0.9)

    def test_an_empty_population_has_zero_coverage_not_perfect_coverage(self):
        """Mutation: `return 1.0` on empty. A run with no rows then passes P1,
        which is precisely the condition P1 was written to catch -- the
        registration notes `demo.db` returned NULL for every row.
        """
        assert coverage([]) == 0.0

    def test_too_few_clusters_refuses_rather_than_returning_a_number(self):
        rows = [_obs("only", i, i, 1.0 + (i % 3)) for i in range(10)]
        with pytest.raises(SignalTestRefused, match="cluster"):
            fit(rows)
