"""Fee model tests.

Every assertion here states a claim about Kalshi's economics that some decision
downstream depends on. If one of these breaks, a strategy is being priced
against a fee curve that isn't real.

Expected values are expressed through the real helpers or computed inline from
the documented formula rather than hardcoded as magic numbers, so a coefficient
change shows up as a failure with a readable diff instead of a wall of numbers.

**One deliberate exception:** `TestModelARoundingIsCeilingNotNearest` hardcodes
values *observed on real fills*. Those are ground truth, not restatements of the
formula, and computing them from the formula would make the test agree with the
code by construction -- which is the failure mode this whole file exists to
avoid.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, ROUND_HALF_UP

import pytest

from backend.core import fees
from backend.core.prices import PRICE_MAX, cents_to_tenths

_CENT = Decimal("0.01")
_ROUNDING_RULES = (ROUND_CEILING, ROUND_HALF_UP, ROUND_HALF_EVEN, ROUND_FLOOR)


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
        """Pins the *scale* of the formula, and nothing about the rounding.

        0.07 x 100 x 0.50 x 0.50 = 1.75, which is exactly on a cent boundary, so
        ceil, floor, half-up and half-even all return it. See
        `TestModelARoundingIsCeilingNotNearest` for the anchors that actually
        discriminate -- this one cannot, and was for a while the only anchor
        this file had.
        """
        assert float(fees._model_a(cents_to_tenths(50), 100, maker=False)) == 1.75


def _model_a_raw(coefficient: Decimal, price_tenths: int, contracts: int) -> Decimal:
    """The Model A fee *before* rounding, from the documented formula.

    Written out here rather than imported so the tests below can ask the
    question the lesson in `tasks/lessons.md` demands -- "what would the wrong
    implementation give at this input?" -- for coefficients and rounding rules
    the module does not implement.
    """
    price = Decimal(price_tenths) / Decimal(PRICE_MAX)
    return coefficient * Decimal(contracts) * price * (Decimal(1) - price)


class TestModelARoundingIsCeilingNotNearest:
    """Anchors chosen where the candidate rounding rules *disagree*.

    The break-even bar in CLAUDE.md (52.00% taker, not the 51.75% the published
    coefficient alone gives) is a consequence of this rounding rule, so the rule
    needs a test that can distinguish it from the alternatives. The at-the-money
    anchor above cannot: 1.75 is exactly on a cent boundary.

    This is `tasks/lessons.md` 2026-08-07 ("Four audits, one failure shape"):
    `clv_tenths(500, 500, "no") == 0` passed under both the right and the wrong
    sign convention because 50c is precisely where the error vanishes. Same
    shape, same file, different quantity.

    **Provenance of the hardcoded values.** Measured 2026-08-10 against real
    settled single-game positions: Model A (0.0700, ceil, per-order) reproduced
    **11 of 11 to the cent**, and the identified coefficient interval is
    (0.069771, 0.070129] -- which contains 0.0700 and excludes both 0.06 and
    0.0175. Only observed prices and sizes appear below; no account data, since
    this repo publishes on push.
    """

    # (price_tenths, contracts, dollars Kalshi actually charged)
    OBSERVED = (
        (968, 20, Decimal("0.05")),   # raw $0.043366 -- ceil, not nearest
        (980, 20, Decimal("0.03")),   # raw $0.027440 -- ceil, not floor
        (160, 59, Decimal("0.56")),   # raw $0.555072 -- Model A, though B was dearer
    )

    @pytest.mark.parametrize("price_tenths,contracts,charged", OBSERVED)
    def test_model_a_reproduces_the_fee_kalshi_actually_charged(
        self, price_tenths, contracts, charged
    ):
        assert fees._model_a(price_tenths, contracts, maker=False) == charged

    def test_a_remainder_below_half_a_cent_is_still_rounded_up(self):
        """The discriminating anchor, and proof that it discriminates.

        20 contracts at 96.8c: raw $0.0433664. Kalshi charged **$0.05**. Every
        rounding rule other than ceiling gives $0.04, so this single observation
        separates ceiling from all three alternatives -- which is exactly what
        the 50c anchor could not do.
        """
        raw = _model_a_raw(fees.TAKER_COEFFICIENT, 968, 20)
        by_rule = {rule: raw.quantize(_CENT, rounding=rule) for rule in _ROUNDING_RULES}

        assert by_rule[ROUND_CEILING] == Decimal("0.05")
        assert by_rule[ROUND_HALF_UP] == Decimal("0.04")
        assert by_rule[ROUND_HALF_EVEN] == Decimal("0.04")
        assert by_rule[ROUND_FLOOR] == Decimal("0.04")

        assert fees._model_a(968, 20, maker=False) == Decimal("0.05")

    def test_the_at_the_money_anchor_agrees_under_every_rounding_rule(self):
        """States the defect, so the anchor above is not quietly dropped again.

        At 50c on 100 contracts all four candidate rules return $1.75. A test
        written there pins the coefficient and says nothing about rounding.
        Asserted as a *pair* with the discriminating input, because "these two
        anchors must behave differently" is the property; either half alone
        reads as coverage.
        """
        at_the_money = _model_a_raw(fees.TAKER_COEFFICIENT, cents_to_tenths(50), 100)
        agreed = {at_the_money.quantize(_CENT, rounding=r) for r in _ROUNDING_RULES}
        assert agreed == {Decimal("1.75")}, "the old anchor cannot discriminate"

        discriminating = _model_a_raw(fees.TAKER_COEFFICIENT, 968, 20)
        spread = {discriminating.quantize(_CENT, rounding=r) for r in _ROUNDING_RULES}
        assert len(spread) > 1, "and the replacement must"

    def test_a_sub_half_cent_fee_is_still_charged_as_a_whole_cent(self):
        """Ceiling means the fee can never round away to nothing.

        One contract at 99c is raw $0.000693 -- under nearest-cent rounding that
        is a **zero fee**, and a zero fee on the money path is the fabricated
        edge `calculate_fee` returns None to avoid. The rounding rule is load
        bearing at the cheap end, not just a tie-break.
        """
        raw = _model_a_raw(fees.TAKER_COEFFICIENT, cents_to_tenths(99), 1)
        assert raw < Decimal("0.005"), "otherwise this input proves nothing"
        assert raw.quantize(_CENT, rounding=ROUND_HALF_UP) == Decimal("0")

        assert fees._model_a(cents_to_tenths(99), 1, maker=False) == Decimal("0.01")

    def test_the_coefficient_is_inside_the_identified_interval(self):
        """0.0700, bracketed by the 11 fills rather than by a secondary source.

        The interval excludes Model B's 0.06 and the maker coefficient 0.0175,
        so a silent swap to either is a failure here rather than a slow drift in
        every EV figure downstream.
        """
        assert Decimal("0.069771") < fees.TAKER_COEFFICIENT <= Decimal("0.070129")
        assert not (
            Decimal("0.069771") < fees.SPORTS_MULTIPLIER <= Decimal("0.070129")
        )
        assert not (
            Decimal("0.069771") < fees.MAKER_COEFFICIENT <= Decimal("0.070129")
        )

    def test_the_sports_multiplier_would_have_underpaid_a_real_fill(self):
        """The interval's consequence, stated on observed money.

        Applying 0.06 with the same per-order ceiling to the three observed
        fills gives $0.04 / $0.03 / $0.48 against the $0.05 / $0.03 / $0.56
        Kalshi charged. Two of three are wrong, and both in the direction that
        makes a bet look better than it is.
        """
        with_006 = [
            _model_a_raw(fees.SPORTS_MULTIPLIER, tenths, n).quantize(
                _CENT, rounding=ROUND_CEILING
            )
            for tenths, n, _ in self.OBSERVED
        ]
        charged = [c for _, _, c in self.OBSERVED]
        assert with_006 == [Decimal("0.04"), Decimal("0.03"), Decimal("0.48")]
        assert sum(with_006) < sum(charged)

    def test_kalshi_charged_the_model_a_value_where_model_b_was_dearer(self):
        """The one observed fill where the two candidate models disagree.

        59 contracts at 16c: Model A $0.56, Model B $0.59, **charged $0.56**.
        `calculate_fee` still returns $0.59, because the conservative maximum is
        a deliberate overstatement until the model is resolved -- so this test
        records a 3c overcharge on a real fill as *expected* behaviour, and is
        the anchor that will fail the day the hedge is retired.
        """
        candidates = fees.fee_candidates(160, 59)
        assert candidates["model_a_per_order_roundup"] == 0.56
        assert candidates["model_b_per_contract_nearest"] == 0.59
        assert fees.calculate_fee(160, 59) == 0.59
        assert fees.calculate_fee(160, 59) > 0.56, "the hedge overstates, on purpose"

    def test_model_b_rounds_a_sub_half_cent_per_contract_down_to_nothing(self):
        """Model B's per-contract rounding is nearest, and that can reach zero.

        At 96.8c the per-contract fee is $0.00186, which rounds to zero, so
        Model B charges **$0.00** for the whole order. Only the conservative
        `max()` stops a zero fee reaching the money path there -- which is the
        same fabricated-edge hazard `calculate_fee` returns None for.
        """
        assert fees._model_b(968, 20, maker=False) == Decimal("0")
        assert fees.calculate_fee(968, 20) == 0.05


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

    def test_the_tolerance_is_not_loosened_to_accommodate_combo_pricing(self):
        """The known limit recorded beside the constant, asserted.

        Measured 2026-08-10 on 55 settled positions: single-game fees are whole
        cents (11 of 11), but KXMVE combo fees are charged to the **tenth of a
        cent** (32 of 43 are not whole cents). So a combo-pricing model would
        trip this tolerance on correct output.

        The tempting fix is to widen the tolerance to $0.001. That would wave
        through a 10% error on a one-contract fill -- the same defect that made
        the old $0.005 useless, one order of magnitude down. This test fails if
        anyone tries it; the fix is a combo-aware fee model instead.
        """
        one_tenth_of_a_cent = 0.001
        assert one_tenth_of_a_cent > fees.FEE_MATCH_TOLERANCE_DOLLARS

    def test_an_exact_match_still_reconciles(self):
        """Not so tight that float representation alone trips it.

        A correct model produces the same dollars the fill reports, and the two
        may travel through different float paths to get there.
        """
        predicted = fees.calculate_fee(cents_to_tenths(50), 100)
        assert predicted is not None
        actual = float(f"{predicted:.10f}")
        assert abs(actual - predicted) <= fees.FEE_MATCH_TOLERANCE_DOLLARS
