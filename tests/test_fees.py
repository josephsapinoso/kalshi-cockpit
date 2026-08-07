"""Fee model tests.

Every assertion here states a claim about Kalshi's economics that some decision
downstream depends on. If one of these breaks, a strategy is being priced
against a fee curve that isn't real.

Expected values are expressed through the real helpers or computed inline from
the documented formula rather than hardcoded as magic numbers, so a coefficient
change shows up as a failure with a readable diff instead of a wall of numbers.
"""

from __future__ import annotations

import pytest

from backend.core import fees
from backend.core.prices import PRICE_MAX, cents_to_tenths


class TestFeeShape:
    """The curve's shape is what makes cheap contracts expensive."""

    def test_fee_peaks_at_fifty_cents(self):
        at_50 = fees.calculate_fee(cents_to_tenths(50), 100)
        assert at_50 > fees.calculate_fee(cents_to_tenths(49), 100)
        assert at_50 > fees.calculate_fee(cents_to_tenths(51), 100)
        assert at_50 > fees.calculate_fee(cents_to_tenths(20), 100)
        assert at_50 > fees.calculate_fee(cents_to_tenths(80), 100)

    @pytest.mark.parametrize("cheap_cents", [5, 10, 20, 35])
    def test_fee_is_symmetric_about_fifty_cents(self, cheap_cents):
        """A 10c contract and a 90c contract cost the same in absolute terms.

        Which means the cheap one costs far more as a percentage of stake --
        the reason buying longshots is the worst corner of the fee curve.
        """
        cheap = fees.calculate_fee(cents_to_tenths(cheap_cents), 100)
        dear = fees.calculate_fee(cents_to_tenths(100 - cheap_cents), 100)
        assert cheap == dear

    def test_cheap_contracts_cost_more_as_a_share_of_stake(self):
        """The claim that motivates avoiding longshots, asserted directly."""
        contracts = 100

        def fee_share(price_cents: int) -> float:
            tenths = cents_to_tenths(price_cents)
            stake = contracts * (tenths / PRICE_MAX)
            return fees.calculate_fee(tenths, contracts) / stake

        assert fee_share(10) > fee_share(50) > fee_share(90)

    def test_an_untradeable_price_returns_none_not_zero(self):
        """0 and 1000 tenths are settled outcomes, not quotes -- so there is no
        fee to compute, and `None` is the only honest answer.

        This previously returned `0.0`, which is the project's "unreadable must
        never resolve to zero" rule broken where it costs most. A zero fee on a
        zero-cost ask makes `effective_price` $0.00, `breakeven_win_rate` 0%,
        and `edge_after_fees_tenths` **+55c on a coin flip** -- a fabricated
        edge that arrives already looking legitimate.
        """
        assert fees.calculate_fee(0, 100) is None
        assert fees.calculate_fee(PRICE_MAX, 100) is None

    def test_the_fabricated_edge_is_now_refused_at_the_source(self):
        """The consequence the None is protecting against, asserted directly."""
        from backend.core.ev import edge_after_fees_tenths

        with pytest.raises(ValueError):
            edge_after_fees_tenths(
                ask_tenths=0, contracts=100, fair_probability=0.55
            )

    def test_non_positive_contracts_incur_no_fee(self):
        assert fees.calculate_fee(cents_to_tenths(50), 0) == 0.0
        assert fees.calculate_fee(cents_to_tenths(50), -10) == 0.0


class TestConservativeSelection:
    """calculate_fee must return the most expensive plausible model.

    The two candidate models genuinely disagree and neither dominates. An
    understated fee makes a losing bet look profitable and poisons the
    measurement record; an overstated one only costs a marginal bet.
    """

    def test_returns_the_maximum_across_candidates(self):
        for price_cents in range(1, 100):
            tenths = cents_to_tenths(price_cents)
            candidates = fees.fee_candidates(tenths, 100)
            assert fees.calculate_fee(tenths, 100) == max(candidates.values())

    def test_neither_candidate_model_dominates(self):
        """Documents the disagreement that forces the hedge.

        If this ever passes trivially -- one model always winning -- the hedge
        has become unnecessary and should be replaced with the real model.
        """
        at_50 = fees.fee_candidates(cents_to_tenths(50), 100)
        at_20 = fees.fee_candidates(cents_to_tenths(20), 100)

        # Per-contract rounding lifts 1.5c/contract to 2c at the money.
        assert at_50["model_b_per_contract_nearest"] > at_50["model_a_per_order_roundup"]
        # Away from the money the single-coefficient model is dearer.
        assert at_20["model_a_per_order_roundup"] > at_20["model_b_per_contract_nearest"]

    def test_candidates_are_zero_for_untradeable_prices(self):
        for value in fees.fee_candidates(0, 100).values():
            assert value == 0.0
        for value in fees.fee_candidates(PRICE_MAX, 100).values():
            assert value == 0.0


class TestModelA:
    """Claims that hold within the single-coefficient, per-order-roundup model.

    Tested against the model directly rather than through calculate_fee,
    because the conservative max() mixes two models and these identities only
    hold inside one of them.
    """

    def test_maker_is_one_quarter_of_taker(self):
        assert fees.MAKER_COEFFICIENT == fees.TAKER_COEFFICIENT / 4

    def test_larger_orders_are_cheaper_per_contract(self):
        """Rounding up applies to the whole order, so it amortises.

        This is why a minimum order size is a genuine risk control: a scatter
        of tiny orders pays the rounding penalty on every one of them.
        """
        tenths = cents_to_tenths(37)
        small = float(fees._model_a(tenths, 1, maker=False)) / 1
        large = float(fees._model_a(tenths, 500, maker=False)) / 500
        assert large < small

    def test_matches_the_documented_formula_at_the_money(self):
        # 0.07 x 100 x 0.50 x 0.50 = 1.75, already whole cents.
        assert float(fees._model_a(cents_to_tenths(50), 100, maker=False)) == 1.75


class TestDeciCentPrecision:
    """The reason this module takes tenths rather than whole cents."""

    def test_deci_cent_prices_produce_distinct_fees(self):
        """Rounding 24.1c to 24c would silently misprice a quarter of markets."""
        assert fees.calculate_fee(241, 1000) != fees.calculate_fee(240, 1000)


class TestSettlementVersusRoundTrip:
    """A bet held to settlement pays ONE fee. This is the venue's whole appeal."""

    def test_settlement_pays_a_single_fee(self):
        tenths = cents_to_tenths(50)
        assert fees.settlement_fee(tenths, 100) == fees.calculate_fee(tenths, 100)

    def test_round_trip_pays_twice(self):
        tenths = cents_to_tenths(50)
        assert fees.round_trip_fee(tenths, tenths, 100) == pytest.approx(
            2 * fees.calculate_fee(tenths, 100)
        )

    def test_round_trip_at_the_money_exceeds_a_typical_edge(self):
        """~3.5c+ per contract at 50c -- larger than the 2-5c edges on offer.

        The load-bearing consequence: any strategy whose entire edge is a few
        cents of spread is net-negative before it starts.
        """
        assert fees.breakeven_edge_cents(cents_to_tenths(50), 100) >= 3.5


class TestTheFeeMatchToleranceIsFloatNoiseOnly:
    """The gate calls a fee mismatch stop-the-line, so the tolerance decides
    whether that condition can ever fire.

    It was `0.005` -- half a cent, absolute. Kalshi charges whole cents, so on a
    one-contract fill a model predicting 1c against an actual 1.5c is **50%
    wrong** and the difference is 0.005, which is not `> 0.005`. The tolerance
    was larger than the quantity being checked, and the gate's most serious
    condition could not detect the error it exists for.
    """

    def test_the_tolerance_cannot_absorb_a_whole_cent(self):
        """The property, stated against the smallest real unit.

        Kalshi's fees are whole cents. A tolerance that admits a full cent
        admits any error the model can plausibly make.
        """
        assert fees.FEE_MATCH_TOLERANCE_DOLLARS < 0.01

    def test_the_old_tolerance_would_have_passed_a_50_percent_error(self):
        """Documents the specific failure so the value is not casually raised."""
        predicted, actual = 0.01, 0.015
        assert abs(actual - predicted) <= 0.005, "the old tolerance passed this"
        assert abs(actual - predicted) > fees.FEE_MATCH_TOLERANCE_DOLLARS, (
            "and the current one must not"
        )

    def test_an_exact_match_still_reconciles(self):
        """Not so tight that float representation alone trips it.

        A correct model produces the same dollars the fill reports, and the two
        may travel through different float paths to get there.
        """
        predicted = fees.calculate_fee(cents_to_tenths(50), 100)
        assert predicted is not None
        actual = float(f"{predicted:.10f}")
        assert abs(actual - predicted) <= fees.FEE_MATCH_TOLERANCE_DOLLARS
