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
    BOUNDARY_TUNING,
    FULL_PASS_THROUGH,
    MIN_CLUSTERS_FOR_LOGO_TEST,
    MIN_CLUSTERS_TO_DECLARE,
    NO_SIGNAL_UPPER_LIMIT,
    RATCHET_SIGMA_TENTHS,
    Fit,
    LeaveOneGroupOut,
    Observation,
    SignalTestRefused,
    coverage,
    effective_clusters,
    fit,
    leave_one_group_out,
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
            # A synthetic `Fit` still has to carry these, because they are
            # required fields on `Fit` -- a caller must not be able to build a
            # `G` with no effective count beside it. They are `None` here
            # because this class supplies no rows to compute leverage from, and
            # `verdict()` does not read them: `G_eff` is a reportable, never a
            # threshold.
            g_eff=None,
            largest_cluster_leverage_share=None,
        )

    def test_below_the_floor_nothing_can_be_declared(self):
        """The registration: a look at `G < 713` "may not declare SIGNAL, BUG
        or NO SIGNAL", however extreme the estimate.

        Mutation: remove the floor check. A huge beta at G = 10 then reads
        SIGNAL, which is the failure the floor exists to prevent and which an
        earlier draft ADR proposed doing deliberately at G = 186.
        """
        for beta in (-5.0, 0.0, 0.5, 5.0):
            f = self._fit(beta, 0.01, g=MIN_CLUSTERS_TO_DECLARE - 1)
            assert verdict(f, ()).verdict == "UNRESOLVED"

    def test_nothing_can_be_declared_at_the_old_floor_of_300(self):
        """**The 2026-08-24 screen's number, refused by the constant itself.**

        `NO SIGNAL, 311 of 300 games` was displayed and audited and refused, and
        the constant that permitted it stayed at 300 for four more days. This
        test is the one that goes red if it is put back: every estimate extreme
        enough to declare, at every `G` from 300 up to one short of 713, must
        still come back UNRESOLVED.

        Mutation observed red: `MIN_CLUSTERS_TO_DECLARE = 300`. The 300, 311 and
        712 cases then declare SIGNAL / NO SIGNAL / BUG on cue.
        """
        for g in (MIN_CLUSTERS_FOR_LOGO_TEST, 311, MIN_CLUSTERS_TO_DECLARE - 1):
            # A slope so far from zero that only the floor can be refusing it.
            assert verdict(self._fit(0.5, 0.001, g), ()).verdict == "UNRESOLVED"
            # And the shape the live screen actually printed: a tight interval
            # ruling out 0.40 from below.
            assert verdict(self._fit(-0.0756, 0.0246, g), ()).verdict == "UNRESOLVED"
            assert verdict(self._fit(2.0, 0.001, g), ()).verdict == "UNRESOLVED"

    def test_signal_needs_the_lower_limit_above_zero_not_the_point_estimate(self):
        """Mutation: test `beta_hat > 0`. A beta of 0.5 with se 0.4 then reads
        SIGNAL while its interval comfortably contains zero.
        """
        g = MIN_CLUSTERS_TO_DECLARE
        assert verdict(self._fit(0.5, 0.4, g), ()).verdict != "SIGNAL"
        assert verdict(self._fit(0.5, 0.1, g), ()).verdict == "SIGNAL"

    def test_bug_needs_the_lower_limit_above_one(self):
        """§A3's correction. A point estimate above 1.0 whose interval still
        contains 1.0 is a FLAG, not a BUG -- the old rule classified a true
        beta of exactly 1.0 as BUG half the time.
        """
        g = MIN_CLUSTERS_TO_DECLARE
        assert verdict(self._fit(1.1, 0.2, g), ()).verdict == "SIGNAL"
        assert verdict(self._fit(2.0, 0.2, g), ()).verdict == "BUG, NOT SIGNAL"

    def test_no_signal_needs_the_upper_limit_below_the_registered_threshold(self):
        g = MIN_CLUSTERS_TO_DECLARE
        assert verdict(self._fit(0.0, 0.05, g), ()).verdict == "NO SIGNAL"
        assert verdict(self._fit(0.0, 0.5, g), ()).verdict == "UNRESOLVED"

    def test_the_registered_constants_are_not_quietly_moved(self):
        """An earlier ADR draft proposed 0.64 and a floor of 186. Both are
        amendments to the registration, not code changes.

        **713 since Amendment 2 §B4**, and it is a ratchet: it does not fall if
        a later look measures a smaller `sigma`. 0.40 and `tuning = 300` are
        left standing by that amendment in those words (§B5, §B6(4)).
        """
        assert MIN_CLUSTERS_TO_DECLARE == 713
        assert NO_SIGNAL_UPPER_LIMIT == 0.40
        assert FULL_PASS_THROUGH == 1.0
        assert MIN_CLUSTERS_FOR_LOGO_TEST == 300
        assert RATCHET_SIGMA_TENTHS == 31.6915

    def test_the_boundary_tuning_did_not_move_with_the_floor(self):
        """§B6(4): `tuning` is the Robbins mixture parameter, **not the floor**.

        The two were one constant until 2026-08-29, so raising the floor would
        have re-tuned the boundary as a side effect -- silently restating the
        widths of the 2026-08-16 and 2026-08-25 published intervals, which
        Amendment 2 forbids in those words.

        Mutation observed red: `def fit(..., tuning=MIN_CLUSTERS_TO_DECLARE)`.
        The multiplier at G = 199 then moves and the published `-0.1412`
        interval in `tests/test_clv_signal.py` no longer reproduces.
        """
        assert BOUNDARY_TUNING == 300
        assert BOUNDARY_TUNING != MIN_CLUSTERS_TO_DECLARE
        rows = [
            _obs(i // 4, (i % 17) - 8, ((i % 13) - 6) * 0.5, 1.0 + (i % 5))
            for i in range(400)
        ]
        assert fit(rows).multiplier == pytest.approx(
            fit(rows, tuning=BOUNDARY_TUNING).multiplier
        )


class TestGEffIsComputedNotAssumed:
    """§B7's mandatory reportable: the effective cluster count on leverage.

    `G = 311` was **4.26** effective clusters at the 2026-08-25 look -- two games
    carrying half the weight on `beta` and one WNBA game carrying 43.80% alone.
    A `G_eff` that always came back equal to `G` would mean the leverage was
    never computed, which is the failure these tests exist to catch.
    """

    def _spread(self, n_clusters, per=4):
        """Equal leverage: every cluster gets the same regressor values.

        The half-spread varies **between** clusters and not within one, so it
        cannot be a linear function of `edge` -- a control collinear with the
        regressor residualises it to nothing, and every leverage share would
        then be unreadable rather than equal.
        """
        rows = []
        for c in range(n_clusters):
            for j in range(per):
                rows.append(_obs(c, (j - 1.5) * 10.0, (j - 1.5) * 3.0, 1.0 + c % 3))
        return rows

    def test_equal_leverage_gives_g_eff_equal_to_g(self):
        """The calibration case. Kish's count equals the nominal count exactly
        when every cluster carries the same weight -- which is the assumption
        `sqrt(G)` in the power check is a function of."""
        rows = self._spread(40)
        assert effective_clusters(rows) == pytest.approx(40.0)
        assert fit(rows).g_eff == pytest.approx(40.0)

    def test_one_dominant_cluster_collapses_g_eff(self):
        """The observed case, in miniature. One cluster carries a regressor two
        orders of magnitude wider than the rest, and `G_eff` must fall to near
        1 while nominal `G` stays at 40.

        Mutation observed red: return `float(len(weights))` from
        `effective_clusters`. `G_eff` then reads 40.00 against a leverage share
        of 0.99 on one game -- the exact reading the 2026-08-24 screen gave.
        """
        rows = self._spread(39)
        for j in range(4):
            rows.append(_obs("dominant", (j - 1.5) * 1000.0, (j - 1.5) * 5.0, 1.0 + j))
        f = fit(rows)
        assert f.n_clusters == 40
        assert f.g_eff is not None and f.g_eff < 1.5
        # Equal leverage would put every cluster at 1/40 = 0.025. This one holds
        # nearly all of it, which is the reading the audit found on the record.
        assert f.largest_cluster_leverage_share > 0.95

    def test_a_constant_regressor_reads_none_not_zero_and_not_g(self):
        """Unreadable resolves to `None`. A regressor with no residual variance
        has no leverage to concentrate, and reporting 0 -- or `G` -- would be a
        claim about concentration that was never measured."""
        rows = [_obs(i // 3, 5.0, float(i % 7), 1.0 + (i % 3)) for i in range(30)]
        assert effective_clusters(rows) is None
        assert fit(rows).g_eff is None


class TestTheA4DowngradeExecutes:
    """§A4's leave-one-group-out rule, and it is strictly one-way.

    Amendment 2 §B8(a) records that this branch was unimplemented and had never
    executed, and §B9 forbids a declaration at `G >= 713` until it does. Both
    directions are exercised below: a group whose removal flips the claim, and
    one whose removal leaves it standing.
    """

    def _logo(self, name, *, beta=None, upper=None, testable=True):
        return LeaveOneGroupOut(
            name=name,
            n_rows=10,
            n_clusters=5,
            leverage_share=0.1,
            clusters_remaining=400,
            testable=testable,
            beta_hat=beta,
            lower=None,
            upper=upper,
            refusal=None,
        )

    def _fit(self, beta, se, g=MIN_CLUSTERS_TO_DECLARE, multiplier=2.0):
        return Fit(
            beta_hat=beta,
            gamma_hat=0.0,
            alpha_hat=0.0,
            se_cluster=se,
            se_classical=se,
            n_rows=g * 10,
            n_clusters=g,
            multiplier=multiplier,
            g_eff=None,
            largest_cluster_leverage_share=None,
        )

    def test_no_signal_is_downgraded_when_a_group_removal_reaches_the_threshold(self):
        """§A4: NO SIGNAL falls to UNRESOLVED if any recomputation returns an
        always-valid upper limit **at or above** 0.40.

        Mutation observed red: drop the NO SIGNAL branch from `verdict`. The
        verdict then stays NO SIGNAL with a group whose removal puts the upper
        limit at 0.55.
        """
        base = self._fit(0.0, 0.05)
        assert verdict(base, ()).verdict == "NO SIGNAL"
        decided = verdict(base, [self._logo("too_few_books", upper=0.55)])
        assert decided.verdict == "UNRESOLVED"
        assert decided.section6_verdict == "NO SIGNAL"
        assert decided.downgraded_by == "too_few_books"

    def test_no_signal_stands_when_no_group_removal_reaches_the_threshold(self):
        """The other branch, and the one today's data is in: seven testable
        groups, largest upper limit +0.0286, nothing fires.

        Mutation observed red: compare against `> -1.0` instead of the
        threshold. Every group then downgrades and the verdict is never
        declarable -- a guard that fires on everything is as useless as one that
        fires on nothing.
        """
        base = self._fit(0.0, 0.05)
        decided = verdict(
            base,
            [
                self._logo("suspicious_edge", upper=0.0198),
                self._logo("gridA[800,990)", upper=0.0286),
                self._logo("wide_market", upper=-0.0018),
            ],
        )
        assert decided.verdict == "NO SIGNAL"
        assert decided.section6_verdict == "NO SIGNAL"
        assert decided.downgraded_by is None

    def test_the_boundary_is_at_or_above_not_strictly_above(self):
        """§A4 says "at or above 0.40". An upper limit landing exactly on the
        threshold downgrades."""
        base = self._fit(0.0, 0.05)
        exact = verdict(base, [self._logo("g", upper=NO_SIGNAL_UPPER_LIMIT)])
        assert exact.verdict == "UNRESOLVED"
        just_below = verdict(base, [self._logo("g", upper=0.3999)])
        assert just_below.verdict == "NO SIGNAL"

    def test_signal_is_downgraded_when_a_group_removal_flips_the_sign(self):
        """§A4: SIGNAL falls to UNRESOLVED if any recomputation returns
        `beta_hat <= 0`. The test is on the **claim** -- does the sign survive --
        not on significance, because losing significance after discarding a
        quarter of the data is a power artefact."""
        base = self._fit(0.5, 0.1)
        assert verdict(base, ()).verdict == "SIGNAL"
        decided = verdict(base, [self._logo("suspicious_edge", beta=-0.01)])
        assert decided.verdict == "UNRESOLVED"
        assert decided.downgraded_by == "suspicious_edge"

    def test_signal_stands_when_every_group_removal_keeps_the_sign(self):
        base = self._fit(0.5, 0.1)
        decided = verdict(
            base,
            [self._logo("a", beta=0.3), self._logo("b", beta=0.01)],
        )
        assert decided.verdict == "SIGNAL"
        assert decided.downgraded_by is None

    def test_an_untestable_group_is_never_grounds_for_downgrade(self):
        """§A4 in those words: a group whose removal leaves `G` below the
        threshold *"cannot be tested"* and is *"not grounds for downgrade"* --
        otherwise SIGNAL is foreclosed whenever one group is most of the sample,
        the same defect §A3 fixes.

        Mutation observed red: drop the `d.testable` filter. The untestable row
        below carries an upper limit of 0.99 and immediately downgrades.
        """
        base = self._fit(0.0, 0.05)
        decided = verdict(
            base, [self._logo("too_few_books", upper=0.99, testable=False)]
        )
        assert decided.verdict == "NO SIGNAL"
        assert decided.downgraded_by is None

    def test_the_rule_can_never_raise_a_verdict(self):
        """One-way, in §A4's own words. An UNRESOLVED base stays UNRESOLVED
        whatever the groups say, and a group with a huge positive slope cannot
        manufacture SIGNAL."""
        base = self._fit(0.0, 0.5)
        assert verdict(base, ()).verdict == "UNRESOLVED"
        decided = verdict(base, [self._logo("a", beta=9.0, upper=0.001)])
        assert decided.verdict == "UNRESOLVED"
        assert decided.downgraded_by is None

    def test_a_group_whose_removal_empties_too_many_clusters_is_untestable(self):
        """Computed rather than asserted: `leave_one_group_out` decides
        testability from the clusters actually left, and **removal only reduces
        `G` when it empties a cluster**. The pre-audit reasoning that only a
        group of <= 11 clusters could be removed at `G = 311` was wrong in the
        flattering direction.
        """
        rows = [
            _obs(i // 2, (i % 11) - 5, ((i % 7) - 3) * 2.0, 1.0 + (i % 4))
            for i in range(60)
        ]
        # 30 clusters. Removing rows spread across every cluster empties none.
        spread = [i % 2 == 0 for i in range(60)]
        # Removing every row of the first ten clusters empties exactly ten.
        whole = [i // 2 < 10 for i in range(60)]
        results = {
            r.name: r
            for r in leave_one_group_out(
                rows,
                [("spread", spread), ("whole", whole)],
                min_clusters_remaining=25,
            )
        }
        assert results["spread"].clusters_remaining == 30
        assert results["spread"].testable is True
        assert results["whole"].clusters_remaining == 20
        assert results["whole"].testable is False
        assert "UNTESTABLE" in results["whole"].refusal

    def test_a_misaligned_mask_is_refused_rather_than_silently_truncated(self):
        """A mask of the wrong length describes a different population, and
        `zip` would have silently truncated to the shorter one."""
        rows = [_obs(i // 2, i, i * 0.5, 1.0) for i in range(20)]
        with pytest.raises(SignalTestRefused):
            leave_one_group_out(rows, [("short", [True] * 5)])


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
