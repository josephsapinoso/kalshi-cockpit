"""What the strikeout distribution claims, stated as tests.

The module is arithmetic, so the temptation is to test it by comparing numbers
to numbers computed the same way -- which pins a typo and nothing else. Every
class below instead asserts a *property* that would have to hold of any correct
implementation, and two of them (`TestTheCompoundIsWiderThanABinomial`,
`TestMeanIsPreserved`) are the identities that tie the output back to the
parameters a caller supplied. If a future replacement of the `BF` shape breaks
one of those, it is wrong regardless of how plausible its numbers look.

Mutation-verified 2026-08-17 per CLAUDE.md -- each guard was disabled and the
test watched to go red. Results in `TestTheGuardsWereWatchedToFail`'s docstring.
"""

from __future__ import annotations

import math

import pytest

from backend.model.strikeouts import (
    MASS_TOLERANCE,
    MAX_BATTERS_FACED,
    MIN_BATTERS_FACED,
    StrikeoutDistribution,
    batters_faced_pmf,
    distribution,
    ladder_probabilities,
)

# A league-average-ish starter. Not a measurement -- these are round numbers
# chosen so the tests exercise a realistic region of the parameter space, and
# nothing here should be quoted as a rate.
BF = 22.0
SD = 5.0
RATE = 0.22

# The rungs Kalshi actually published for one pitcher on 2026-08-15, as
# `floor_strike`, straight out of `tests/fixtures/events_mlb_props_nested.json`.
LADDER = (1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5, 13.5, 14.5)


def _mean(pmf) -> float:
    return sum(k * p for k, p in enumerate(pmf))


def _variance(pmf) -> float:
    mu = _mean(pmf)
    return sum((k - mu) ** 2 * p for k, p in enumerate(pmf))


class TestTheMassIsOne:
    """A pmf that does not sum to 1 prices every rung of the ladder wrong at
    once, and does it while looking internally consistent -- the rungs would
    still be monotone, still be ordered, and still be plausible."""

    def test_the_strikeout_pmf_sums_to_one(self):
        dist = distribution(BF, SD, RATE)
        assert dist is not None
        assert abs(sum(dist.pmf) - 1.0) <= MASS_TOLERANCE

    def test_the_batters_faced_pmf_sums_to_one_after_truncation(self):
        """Renormalised *after* truncation, not before.

        Normalising the untruncated normal and then clipping would leave the
        support short of 1 by the tail mass -- small at these parameters, which
        is what makes it dangerous: it would never be large enough to notice and
        would bias every probability downward.
        """
        weights = batters_faced_pmf(BF, SD)
        assert weights is not None
        assert abs(sum(weights) - 1.0) <= MASS_TOLERANCE

    def test_every_probability_is_a_probability(self):
        dist = distribution(BF, SD, RATE)
        assert dist is not None
        assert all(0.0 <= p <= 1.0 for p in dist.pmf)


class TestMeanIsPreserved:
    """`E[K] == E[BF] * p`, exactly, by the tower rule.

    This is the tie between the two numbers a caller supplies and the number
    that reaches the money path. It is also the invariant that survives a change
    of `BF` shape: swap the discretised normal for the left-skewed distribution
    the module docstring says reality has, and this must still hold. A
    replacement that breaks it has changed the answer, not the shape.
    """

    def test_expected_strikeouts_equal_expected_batters_times_the_rate(self):
        dist = distribution(BF, SD, RATE)
        assert dist is not None
        weights = batters_faced_pmf(BF, SD)
        # Against the *realised* mean of the truncated, discretised pmf rather
        # than against `BF` itself. Truncation and rounding move the mean, and
        # asserting against the nominal parameter would either fail or force a
        # tolerance loose enough to hide a real error.
        realised_bf = _mean(weights)
        assert dist.mean == pytest.approx(realised_bf * RATE, abs=1e-9)

    def test_the_truncation_moves_the_mean_by_less_than_the_price_grid(self):
        """The support is wide enough that the previous test is not excusing a
        real distortion. If this fails, the parameters have drifted toward a
        bound and the *nominal* mean a caller passed is no longer what the model
        is using -- the flattering kind of silent.

        **The tolerance is the money grid, not a round number.** Truncating the
        left tail at zero is asymmetric, so the realised mean sits fractionally
        above `BF` -- measured at `+7.7e-5` batters at these parameters. The
        question a tolerance has to answer is not "is that small" but "could it
        move a price", and this repo already fixes the smallest price that
        exists: one tenth of a cent, `0.001` in probability
        (`backend/core/prices.py`). A mean shift of `d` batters moves `E[K]` by
        `d * k_per_bf`, so requiring that below half a tick is the tightest
        bound that is about money rather than about floating point.

        At `BF=22, SD=5` the shift is ~30x inside it. A parameter set that
        pushed within one sd of a bound would not be.
        """
        weights = batters_faced_pmf(BF, SD)
        assert weights is not None
        half_a_deci_cent = 0.0005
        drift_in_strikeouts = abs(_mean(weights) - BF) * RATE
        assert drift_in_strikeouts < half_a_deci_cent, (
            f"truncation moved E[K] by {drift_in_strikeouts:.2e}, which is more "
            f"than half the smallest price this repo can express. The nominal "
            f"`expected_bf` is no longer what the model is pricing."
        )


class TestTheCompoundIsWiderThanABinomial:
    """The whole reason this is a compound and not one Binomial.

    By the law of total variance, and exactly:

        Var(K) = E[BF] * p * (1-p)  +  p^2 * Var(BF)

    The second term is the workload uncertainty. Dropping it -- pricing at the
    mean `BF` -- shrinks the tails, and the tails are where `10+` lives. A model
    that is over-confident at `10+` produces its biggest apparent edges exactly
    where the ladder has least volume to correct it, which is the shape of every
    bug this repo's first rule is about.
    """

    def test_variance_matches_the_law_of_total_variance(self):
        dist = distribution(BF, SD, RATE)
        weights = batters_faced_pmf(BF, SD)
        assert dist is not None and weights is not None

        expected = _mean(weights) * RATE * (1 - RATE) + RATE**2 * _variance(weights)
        assert _variance(dist.pmf) == pytest.approx(expected, abs=1e-9)

    def test_it_is_strictly_wider_than_the_binomial_at_the_mean(self):
        """The comparison stated directly, so the claim is visible without
        rearranging the identity above in your head."""
        dist = distribution(BF, SD, RATE)
        assert dist is not None
        at_the_mean = BF * RATE * (1 - RATE)
        assert _variance(dist.pmf) > at_the_mean

    def test_a_certain_workload_collapses_to_the_binomial(self):
        """The other end of the same claim: as `sd_bf` goes to zero the extra
        term vanishes and the compound *is* the Binomial. Without this, a
        implementation that inflated the variance by an unrelated constant would
        pass the test above."""
        dist = distribution(20.0, 1e-6, RATE)
        assert dist is not None
        assert _variance(dist.pmf) == pytest.approx(20 * RATE * (1 - RATE), abs=1e-6)


class TestTheLadderIsOneOpinion:
    """Fourteen markets, one distribution. The properties that makes true."""

    def test_the_rungs_are_monotone_non_increasing(self):
        dist = distribution(BF, SD, RATE)
        assert dist is not None
        prices = ladder_probabilities(dist, LADDER)
        assert all(a >= b for a, b in zip(prices, prices[1:])), prices

    def test_the_result_is_positionally_aligned_with_the_input(self):
        """Not sorted. A caller holding markets in the order the Kalshi API
        returned them must be able to `zip` the two, and silently sorting would
        pair every price with the wrong market while still looking monotone
        when printed on its own."""
        dist = distribution(BF, SD, RATE)
        assert dist is not None
        shuffled = (7.5, 1.5, 4.5)
        prices = ladder_probabilities(dist, shuffled)
        assert prices == tuple(dist.probability_over(s) for s in shuffled)
        assert prices[0] < prices[1], "a sorted result would hide this"

    def test_the_whole_ladder_is_strictly_inside_zero_and_one(self):
        """At realistic parameters no rung is a certainty. A rung that priced at
        exactly 0 or 1 would be an arithmetic underflow presenting as an
        infinite edge against any Kalshi quote at all."""
        dist = distribution(BF, SD, RATE)
        assert dist is not None
        for price in ladder_probabilities(dist, LADDER):
            assert 0.0 < price < 1.0


class TestTheFloorStrikeNeedsNoArithmetic:
    """`props.py` establishes that Kalshi publishes `floor_strike` as `N - 0.5`.

    So `P(K > 1.5)` must equal `P(K >= 2)`. The point is not that the two agree
    -- it is that the module offers the caller a path that never performs the
    `N -> N - 0.5` conversion, because that conversion on a money path is a
    thing that can be off by one rung across an entire ladder.
    """

    @pytest.mark.parametrize("n", [1, 2, 3, 5, 8, 12])
    def test_probability_over_the_published_strike_equals_at_least_n(self, n):
        dist = distribution(BF, SD, RATE)
        assert dist is not None
        assert dist.probability_over(n - 0.5) == pytest.approx(dist.at_least(n))

    def test_an_integer_floor_strike_is_still_answered_correctly(self):
        """Strictly above, as the settlement rule says. If Kalshi ever published
        an integer strike, `P(K > 2)` must exclude `K == 2` -- a `>=` here would
        be wrong by one whole rung and would only be noticed on the day the wire
        format changed."""
        dist = distribution(BF, SD, RATE)
        assert dist is not None
        assert dist.probability_over(2.0) == pytest.approx(dist.at_least(3))

    def test_at_least_zero_is_certain(self):
        dist = distribution(BF, SD, RATE)
        assert dist is not None
        assert dist.at_least(0) == 1.0
        assert dist.at_least(-1) == 1.0

    def test_a_strike_past_the_support_is_impossible_not_an_error(self):
        dist = distribution(BF, SD, RATE)
        assert dist is not None
        assert dist.at_least(MAX_BATTERS_FACED + 5) == 0.0
        assert dist.probability_over(MAX_BATTERS_FACED + 0.5) == 0.0


class TestUnreadableResolvesToNone:
    """The repo's rule, applied at the model's boundary.

    Every case below is a number a caller could plausibly arrive with -- a rate
    parsed as a percentage, a workload that came back empty, a `NaN` that
    propagated from an upstream division. None of them may produce a price.
    Substituting a default here would put a confident number on the money path
    with nothing downstream able to tell it apart from a real one.
    """

    @pytest.mark.parametrize(
        "rate",
        [
            0.0,            # a pitcher who strikes nobody out is a parse failure
            1.0,            # ... and so is one who strikes out everybody
            22.0,           # the rate given as a percentage, or as K/9
            -0.1,
            float("nan"),
            float("inf"),
            None,
        ],
    )
    def test_an_unreadable_rate_refuses(self, rate):
        assert distribution(BF, SD, rate) is None

    @pytest.mark.parametrize(
        "expected_bf",
        [0.0, -5.0, float("nan"), float("inf"), None, MAX_BATTERS_FACED + 1.0],
    )
    def test_an_unreadable_workload_refuses(self, expected_bf):
        assert distribution(expected_bf, SD, RATE) is None
        assert batters_faced_pmf(expected_bf, SD) is None

    @pytest.mark.parametrize("sd", [0.0, -1.0, float("nan"), float("inf"), None])
    def test_an_unreadable_spread_refuses(self, sd):
        assert distribution(BF, sd, RATE) is None
        assert batters_faced_pmf(BF, sd) is None

    def test_it_refuses_rather_than_returning_a_flat_distribution(self):
        """The specific wrong answer worth naming. A uniform pmf over the
        support would sum to 1, be monotone on the ladder, and pass every
        structural test in this file -- while being an opinion about nothing."""
        assert distribution(BF, 0.0, RATE) is None


class TestItSurvivesTheEdgesOfItsOwnSupport:
    """Numerical, not statistical. These are the inputs that would raise or
    overflow rather than mislead, and a raise on the money path at 19:00 on a
    Friday is its own kind of failure."""

    def test_a_workload_at_the_upper_bound_still_gives_a_proper_pmf(self):
        """The whole support exercised at its widest, at `p = 0.5` where the
        binomial terms are largest.

        **This does not check that `_binomial_pmf` works in log space**, and an
        earlier version of this docstring said it did. The direct
        `comb(n, k) * p**k` form does not overflow until `n = 1030` and agrees
        with the log form to `5.5e-15` here, so substituting it leaves this file
        entirely green -- verified by mutation, recorded in
        `TestTheGuardsWereWatchedToFail`. What this test actually holds is that
        the pmf is proper and finite at the edge of the support, which is the
        property a caller depends on and which the renormalisation mutation does
        break.
        """
        dist = distribution(float(MAX_BATTERS_FACED) - 1, 2.0, 0.5)
        assert dist is not None
        assert abs(sum(dist.pmf) - 1.0) <= MASS_TOLERANCE
        assert all(math.isfinite(p) for p in dist.pmf)

    def test_a_tiny_rate_does_not_underflow_to_an_improper_pmf(self):
        dist = distribution(BF, SD, 1e-9)
        assert dist is not None
        assert abs(sum(dist.pmf) - 1.0) <= MASS_TOLERANCE
        assert dist.pmf[0] == pytest.approx(1.0, abs=1e-6)

    def test_a_workload_near_the_lower_bound_still_normalises(self):
        dist = distribution(1.0, 1.0, RATE)
        assert dist is not None
        assert abs(sum(dist.pmf) - 1.0) <= MASS_TOLERANCE

    def test_the_support_includes_a_scratched_start(self):
        """`MIN_BATTERS_FACED` is 0 deliberately: a pitcher announced and then
        scratched faces nobody, and a support starting at 1 would make a real
        outcome unreachable."""
        weights = batters_faced_pmf(BF, SD)
        assert weights is not None
        assert len(weights) == MAX_BATTERS_FACED - MIN_BATTERS_FACED + 1


class TestTheDistributionCarriesItsOwnAssumptions:
    """A probability separated from the parameters that produced it is the
    failure `tasks/lessons.md` records: the number outlives its caveats, and a
    ladder priced off a stale rate is indistinguishable from a fresh one."""

    def test_the_parameters_ride_along_with_the_pmf(self):
        dist = distribution(BF, SD, RATE)
        assert dist is not None
        assert (dist.expected_bf, dist.sd_bf, dist.k_per_bf) == (BF, SD, RATE)

    def test_it_is_frozen(self):
        dist = distribution(BF, SD, RATE)
        assert dist is not None
        with pytest.raises(Exception):
            dist.k_per_bf = 0.5  # type: ignore[misc]


class TestTheGuardsWereWatchedToFail:
    """Mutation record, 2026-08-17. Green proves nothing on its own.

    Six guards in `strikeouts.py` were disabled in turn and the suite re-run.
    **Five went red. One stayed green, and that one is the useful entry.**

    - `batters_faced_pmf` returning the un-renormalised weights:
      **RED, 24 of 49** -- both mass tests, both mean tests, both variance
      tests, all three ladder tests and every `floor_strike` case. An improper
      pmf is visible from almost every direction, which is the right shape for
      the defect that would silently misprice a whole ladder. Reverted.
    - `probability_over` changed from `k > floor_strike` to `k >= floor_strike`:
      **RED, exactly 1** -- `test_an_integer_floor_strike_is_still_answered_
      correctly`. Green on all six half-integer cases, because at a half-integer
      strike the two operators cannot disagree. That is precisely why the
      integer case is in the file: the six realistic parametrisations detect
      nothing here. Reverted.
    - `distribution` collapsed to a single Binomial at `round(expected_bf)`:
      **RED, 3** -- both variance tests and the mean identity. **Green on every
      mass, monotonicity, ladder and refusal test.** The structural tests cannot
      see the defect this module's whole design is about; only the identities
      can. Reverted.
    - `ladder_probabilities` given `sorted(floor_strikes)`:
      **RED, 1** -- `test_the_result_is_positionally_aligned_with_the_input`.
      Reverted.
    - The `0 < k_per_bf < 1` bound widened to `k_per_bf > 0`:
      **RED, 2** -- the `1.0` and `22.0` cases of
      `test_an_unreadable_rate_refuses`. The failure is a `math.log1p(-p)`
      domain error, i.e. a raise; the bound is what turns it into a refusal.
      Reverted.
    - `_binomial_pmf` rewritten as `comb(n, k) * p**k * (1-p)**(n-k)`:
      **GREEN, all 49.** The claim that the log-space form prevents an overflow
      at this support was wrong and is now corrected in `_binomial_pmf`'s
      docstring -- the direct form first raises at `n = 1030` against a support
      capped at 70, and the two agree to `5.5e-15`. **No test in this file
      distinguishes them**, and none is being added to: an assertion that the
      implementation uses `lgamma` would pin a technique rather than a
      behaviour. The log form is kept as unconditional headroom, and the
      limitation is recorded here instead of being closed. Same disposition as
      the per-module granularity note in `tests/test_has_callers.py`.

    This class holds no assertion. It is the record, kept beside the tests it
    describes rather than in a commit message nobody will find.
    """

    def test_the_record_above_is_the_content_of_this_class(self):
        assert TestTheGuardsWereWatchedToFail.__doc__


class TestAgainstAKnownAnswer:
    """One number computed a different way, so the whole file is not comparing
    the implementation to itself.

    With `sd_bf` collapsed the compound is a plain Binomial, and `P(K >= 1)` is
    `1 - (1-p)^n` -- closed form, no summation, derivable on paper.
    """

    def test_it_agrees_with_the_closed_form_binomial(self):
        dist = distribution(20.0, 1e-6, 0.25)
        assert dist is not None
        assert dist.at_least(1) == pytest.approx(1 - 0.75**20, abs=1e-6)

    def test_it_agrees_on_the_far_tail_too(self):
        """The tail is where a summation bug hides: `P(K >= 20)` is one term,
        `p^20`, and it is small enough that an error in it moves no other
        assertion in this file."""
        dist = distribution(20.0, 1e-6, 0.25)
        assert dist is not None
        assert dist.at_least(20) == pytest.approx(0.25**20, rel=1e-4)


class TestTheDataclassIsNotConstructedBehindTheFactory:
    """`StrikeoutDistribution` can be built directly, and a caller that does so
    bypasses every refusal in `distribution`. That is allowed -- it is how the
    tests above build degenerate cases -- so the risk is named here rather than
    pretended away: **production code must call `distribution`.** Pinned by
    `tests/test_has_callers.py` once this module has a production caller.
    """

    def test_a_hand_built_distribution_is_not_validated(self):
        hand_built = StrikeoutDistribution(
            pmf=(0.5, 0.5), expected_bf=1.0, sd_bf=1.0, k_per_bf=0.5
        )
        assert hand_built.at_least(1) == 0.5
