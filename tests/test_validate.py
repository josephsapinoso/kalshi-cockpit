"""Measurement harness tests.

The most important test in this file is
`test_refuses_to_report_a_finding_on_pure_noise`. Every other guard in this
project protects money; this one protects the *conclusion*, and a measurement
harness that reports a finding from random data is worse than no harness at
all -- it launders noise into confidence.
"""

from __future__ import annotations

import math

import random

import pytest

from backend.analysis.validate import (
    EDGE_MONEY_TOLERANCE_TENTHS,
    Observation,
    check_edge_money_consistency,
    pooling_check,
    report,
    summarise,
    summarise_clv,
)


def obs(price_tenths, *, win=None, pnl=None, clv=None, group="all"):
    return Observation(
        entry_ask_tenths=price_tenths, group=group,
        settled_win=win, pnl_cents=pnl, clv_tenths=clv,
    )


class TestNoiseGuard:
    """Read n before the effect size."""

    def test_a_tiny_cell_is_never_distinguishable(self):
        """A two-market cell once produced a 74-point 'finding' that passed a
        significance test.

        **The fixture is chosen so the guard is load-bearing.** The previous one
        -- two wins at 50c -- is not distinguishable *even with the guard
        removed*, because at n=2 the null standard error is 0.35 and the gap is
        0.5. It never discriminated, so deleting the >=5-expected rule left the
        test green.

        Six observations at 10c with three wins does: expected wins is 0.6, well
        under 5, so the guard fires — and without it the null standard error is
        0.12 against a gap of 0.40, which clears two sigma comfortably and would
        be reported as a finding.
        """
        rows = [obs(100, win=True)] * 3 + [obs(100, win=False)] * 3
        summary = summarise(rows)
        bucket = next(b for b in summary.buckets if b.n)

        assert bucket.n == 6
        assert not bucket.normal_approx_valid, "the guard must fire here"
        assert not bucket.distinguishable

        # And the fixture genuinely tests something: without the guard this cell
        # clears two standard errors under the null.
        stderr = math.sqrt(0.1 * 0.9 / 6)
        assert abs(0.5 - 0.1) > 2 * stderr, (
            "fixture no longer discriminates -- it would pass with the guard "
            "deleted, which is how the original one failed to test anything"
        )

    def test_an_indistinguishable_cell_prints_noise_not_a_number(self):
        """A number there would be read as a result no matter the caveats."""
        summary = summarise([obs(500, win=True), obs(500, win=False)])
        bucket = next(b for b in summary.buckets if b.n)
        assert bucket.render_gap() == "(noise)"

    def test_standard_error_is_computed_under_the_null(self):
        """Using the observed rate makes an extreme result look more certain
        precisely because it is extreme."""
        # 40 observations at 50c, all winners. Observed rate 1.0 would give a
        # standard error of zero; under the null (p=0.5) it does not.
        summary = summarise([obs(500, win=True) for _ in range(40)])
        bucket = next(b for b in summary.buckets if b.n)
        assert bucket.stderr_points > 0

    def test_a_large_consistent_effect_is_distinguishable(self):
        """The guard must not refuse everything -- that would be useless."""
        rows = [obs(300, win=True) for _ in range(120)]
        rows += [obs(300, win=False) for _ in range(80)]
        summary = summarise(rows)
        bucket = next(b for b in summary.buckets if b.n)
        assert bucket.normal_approx_valid
        assert bucket.distinguishable

    def test_powered_tests_are_counted(self):
        """Run enough buckets and some clear two standard errors by chance."""
        rows = [obs(300, win=i % 2 == 0) for i in range(200)]
        rows += [obs(700, win=i % 2 == 0) for i in range(200)]
        assert summarise(rows).n_tests == 2


class TestRefusesNoise:
    """The test that protects the conclusion rather than the money."""

    def test_refuses_to_report_a_finding_on_pure_noise(self):
        """Coin flips priced at their true probability, swept across seeds.

        **The original asserted `not summary.distinguishable` on ONE seed.**
        Measured over 300 pure-noise runs, at least one cell clears two standard
        errors **31.0%** of the time — so that assertion was a statement about
        the seed, and would have failed on roughly one run in three had the seed
        ever changed. It passed because of luck, not because of a guard.

        The property that must hold on every seed is the family-wise one:
        whatever individual cells do, the report must not *claim evidence*. With
        the correction applied that happens 5.7% of the time, which is the
        nominal alpha and is what a 5%-level test is supposed to do. Asserting
        zero would be asserting a broken test, not a strict one.
        """
        cell_fired = claimed_evidence = 0
        trials = 100

        for seed in range(trials):
            rng = random.Random(seed)
            rows = []
            for _ in range(2000):
                price = rng.choice([150, 250, 350, 450, 550, 650, 750, 850])
                # Outcome drawn at exactly the implied probability: no edge.
                rows.append(obs(price, win=rng.random() < price / 1000))

            summary = summarise(rows)
            if summary.distinguishable:
                cell_fired += 1
            if summary.survives_multiple_comparisons:
                claimed_evidence += 1

        cell_rate = cell_fired / trials
        family_rate = claimed_evidence / trials

        # The fixture must actually exercise multiplicity, or the rest proves
        # nothing.
        assert cell_rate > 0.15, (
            f"individual cells fired on only {cell_rate:.0%} of pure-noise runs; "
            f"this fixture is not exercising the problem"
        )
        # And the correction must bring it back to roughly alpha.
        assert family_rate <= 0.15, (
            f"claimed evidence from pure noise on {family_rate:.0%} of runs"
        )
        assert family_rate < cell_rate / 2, (
            f"the family-wise correction barely helped: {cell_rate:.0%} of runs "
            f"had a 'significant' cell and {family_rate:.0%} still claimed "
            f"evidence"
        )

    def test_the_report_leads_with_the_family_wise_verdict(self):
        """A per-bucket finding means nothing without the count of tests.

        `n_tests` was printed in the header and never used to compute anything,
        leaving the multiplicity arithmetic to the reader — which is exactly
        what nobody does.
        """
        rng = random.Random(11)
        rows = [
            obs(p, win=rng.random() < p / 1000)
            for p in (rng.choice([250, 450, 650, 850]) for _ in range(1200))
        ]
        text = report(summarise(rows))
        assert "ACROSS ALL TESTS" in text
        assert text.index("ACROSS ALL TESTS") < text.index("BY PRICE PAID")

    def test_says_so_plainly_when_there_is_nothing_to_report(self):
        rows = [obs(500, win=i % 2 == 0) for i in range(400)]
        text = report(summarise(rows))
        assert "That is a result, and" in text


class TestBucketingOnThePricePaid:
    def test_buckets_key_on_the_entry_ask(self):
        """One bucket showed +25.4 points while losing $4.92 a market, because
        it was bucketed on the mid and transacted at the ask."""
        summary = summarise([obs(240), obs(260)])
        labelled = {b.label: b.n for b in summary.buckets if b.n}
        assert labelled == {"20-30c": 2}

    def test_out_of_range_prices_are_dropped_not_bucketed(self):
        assert summarise([obs(5), obs(995)]).n_total == 0


class TestPoolingCheck:
    """A pooled number is not a finding until the parts agree."""

    def _pooled_and_groups(self, group_a_wins, group_b_wins, n=200):
        pooled_rows, a_rows, b_rows = [], [], []
        for i in range(n):
            a = obs(300, win=i < group_a_wins, group="a")
            b = obs(300, win=i < group_b_wins, group="b")
            a_rows.append(a)
            b_rows.append(b)
            pooled_rows += [a, b]
        return (
            summarise(pooled_rows),
            [summarise(a_rows, "a"), summarise(b_rows, "b")],
        )

    def test_agreeing_subgroups_support_the_pooled_finding(self):
        pooled, groups = self._pooled_and_groups(120, 130)
        verdicts = pooling_check(pooled, groups)
        assert verdicts
        assert all(v.status == "supported" for v in verdicts)

    def test_an_opposing_subgroup_contradicts(self):
        """Simpson's paradox appeared three times in the previous project."""
        pooled, groups = self._pooled_and_groups(150, 20)
        verdicts = pooling_check(pooled, groups)
        assert any(v.status == "contradicted" for v in verdicts)

    def test_underpowered_subgroups_are_unresolved_not_refuted(self):
        """An earlier version marked eight genuine buckets as artifacts purely
        because the subgroups were small. 'Unresolved' and 'refuted' are
        different claims."""
        pooled_rows = [obs(300, win=i < 120, group="a") for i in range(200)]
        pooled = summarise(pooled_rows)
        tiny = [summarise([obs(300, win=True, group="a")], "a")]

        verdicts = pooling_check(pooled, tiny)
        assert verdicts
        assert all(v.status == "unpowered" for v in verdicts)
        assert "not refuted" in verdicts[0].detail


class TestEdgeMoneyConsistency:
    def test_a_large_edge_with_negative_money_is_flagged(self):
        rows = [obs(300, win=True, pnl=-5.0) for _ in range(120)]
        rows += [obs(300, win=False, pnl=-5.0) for _ in range(80)]
        warnings = check_edge_money_consistency(summarise(rows))
        assert warnings
        assert "price actually paid" in warnings[0].message

    def test_a_small_edge_with_negative_money_is_not_flagged(self):
        """Below the tolerance, fees explain it -- the entry fee peaks at
        1.75c/contract."""
        rng = random.Random(7)
        rows = [
            obs(500, win=rng.random() < 0.51, pnl=-0.5) for _ in range(400)
        ]
        warnings = check_edge_money_consistency(summarise(rows))
        assert not warnings

    def test_the_tolerance_sits_above_the_peak_fee(self):
        """1.75c/contract entry fee, so 3c is the right side of the line."""
        assert EDGE_MONEY_TOLERANCE_TENTHS >= 17.5


class TestCLV:
    def test_offers_no_verdict_below_the_required_sample(self):
        """CLV needs 200-300 before it means much. Saying so beats a number."""
        result = summarise_clv([obs(500, clv=40.0) for _ in range(30)])
        assert not result.distinguishable
        assert "Too few" in result.verdict

    def test_a_consistent_positive_result_at_scale_is_reported(self):
        rng = random.Random(11)
        rows = [obs(500, clv=rng.gauss(25.0, 30.0)) for _ in range(400)]
        result = summarise_clv(rows)
        assert result.distinguishable
        assert "beating the close" in result.verdict

    def test_noise_at_scale_is_not_reported_as_edge(self):
        rng = random.Random(12)
        rows = [obs(500, clv=rng.gauss(0.0, 40.0)) for _ in range(400)]
        result = summarise_clv(rows)
        assert not result.distinguishable
        assert "No demonstrated edge" in result.verdict

    def test_beat_close_rate_is_reported(self):
        rows = [obs(500, clv=v) for v in (10.0, 20.0, -5.0, 30.0)]
        assert summarise_clv(rows, required_n=1).beat_close_rate == pytest.approx(0.75)


class TestReport:
    def test_states_what_it_does_not_establish(self):
        """Every harness carries its own limitations."""
        text = report(summarise([obs(500, win=True) for _ in range(50)]))
        assert "WHAT THIS DOES NOT ESTABLISH" in text
        assert "CLV is not" in text
        assert "survivorship" in text
        assert "second horizon" in text

    def test_reports_how_many_tests_were_run(self):
        """1,190 category cells produce dozens of 'significant' results by
        chance."""
        rows = [obs(300, win=i % 2 == 0) for i in range(200)]
        assert "1 in 20" in report(summarise(rows))


class TestImpliedAndActualShareADenominator:
    """`gap = actual - implied`, so both halves must describe the same games.

    `implied` averaged the price over EVERY row in the bucket while `actual`
    divided wins by the settled subset. Settlement arrival is not random with
    respect to price — at any instant the settled set is whatever has finished,
    which correlates with start time and therefore with the kind of fixture — so
    the mismatch put a bias straight into `gap` and `stderr`, the two numbers
    the entire calibration check rests on.
    """

    def test_unsettled_rows_do_not_move_the_implied_price(self):
        """The discriminating case.

        Ten settled rows at 50c, plus ten unsettled rows at 90c. The settled
        games came in at exactly their price, so the gap is zero. Averaging the
        price over all twenty would drag `implied` to 70c and manufacture a
        -20 point 'finding' out of games that have not finished.
        """
        rows = [obs(500, win=i < 5) for i in range(10)]
        rows += [obs(900) for _ in range(10)]

        bucket = next(
            b for b in summarise(rows).buckets if b.low <= 500 < b.high
        )
        assert bucket.actual_rate == pytest.approx(0.5)
        assert bucket.implied_probability == pytest.approx(0.5)
        assert bucket.gap_points == pytest.approx(0.0)

    def test_with_everything_settled_the_answer_is_unchanged(self):
        """The fix must not move the number in the ordinary case."""
        rows = [obs(500, win=i < 5) for i in range(10)]
        bucket = next(
            b for b in summarise(rows).buckets if b.low <= 500 < b.high
        )
        assert bucket.implied_probability == pytest.approx(0.5)
        assert bucket.gap_points == pytest.approx(0.0)
