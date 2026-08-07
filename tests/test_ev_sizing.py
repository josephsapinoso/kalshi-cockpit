"""EV and sizing tests.

The assertions that matter most are the refusals. A sizing bug that produces
*too small* a bet costs a little edge; one that produces too large a bet, or
one against an unknown budget, is how an account gets emptied.
"""

from __future__ import annotations

import pytest

from backend.config import RiskConfig
from backend.core.ev import (
    breakeven_win_rate,
    edge_after_fees_tenths,
    effective_price,
    evaluate,
)
from backend.core.prices import cents_to_tenths
from backend.core.sizing import (
    full_kelly_fraction,
    size_position,
    verify_positive_after_fees,
)

RISK = RiskConfig(
    bankroll_dollars=1000.0,
    kelly_fraction=0.25,
    max_order_contracts=50,
    max_position_dollars=100.0,
    max_exposure_dollars=400.0,
    max_daily_loss_dollars=100.0,
    min_order_contracts=10,
)


class TestEV:
    def test_a_bet_at_its_fair_price_is_negative_after_fees(self):
        """The fee is the whole hurdle. Paying fair value loses exactly it."""
        result = evaluate(
            side="yes", ask_tenths=500, contracts=100, fair_probability=0.50
        )
        assert result.ev_dollars < 0
        assert result.ev_dollars == pytest.approx(-result.fee_dollars)

    def test_edge_must_exceed_the_fee_to_be_positive(self):
        marginal = evaluate(
            side="yes", ask_tenths=500, contracts=100, fair_probability=0.505
        )
        clear = evaluate(
            side="yes", ask_tenths=500, contracts=100, fair_probability=0.56
        )
        assert not marginal.is_positive
        assert clear.is_positive

    def test_breakeven_probability_sits_above_the_price(self):
        result = evaluate(
            side="yes", ask_tenths=500, contracts=100, fair_probability=0.55
        )
        assert result.breakeven_probability > 0.50

    def test_settled_prices_are_refused_not_valued_at_zero(self):
        """Valuing a bet on a settled market at zero hides the bug."""
        for settled in (0, 1000):
            with pytest.raises(ValueError):
                evaluate(
                    side="yes", ask_tenths=settled, contracts=10,
                    fair_probability=0.5,
                )

    def test_an_unknown_side_is_refused(self):
        with pytest.raises(ValueError):
            evaluate(side="maybe", ask_tenths=500, contracts=10, fair_probability=0.5)

    def test_ev_scales_with_size(self):
        small = evaluate(side="yes", ask_tenths=500, contracts=10, fair_probability=0.60)
        large = evaluate(side="yes", ask_tenths=500, contracts=100, fair_probability=0.60)
        assert large.ev_dollars > small.ev_dollars


class TestBreakevenMatchesTheVenueClaim:
    """The numbers that make Kalshi interesting at all, asserted directly.

    ~51.75% taker and ~50.44% maker at 50c, against 52.38% at a -110
    sportsbook. Kalshi lowers the bar; it does not clear it.
    """

    def test_taker_breakeven_at_fifty_cents_beats_a_sportsbook(self):
        rate = breakeven_win_rate(cents_to_tenths(50), contracts=100)
        assert rate < 0.5238, "should beat a -110 sportsbook"
        assert 0.50 < rate < 0.53

    def test_maker_is_cheaper_than_taker(self):
        taker = breakeven_win_rate(cents_to_tenths(50), contracts=100)
        maker = breakeven_win_rate(cents_to_tenths(50), contracts=100, maker=True)
        assert maker < taker


class TestEffectivePrice:
    def test_fee_is_amortised_into_the_price(self):
        """Sizing on the raw ask and subtracting the fee later overstates edge."""
        assert effective_price(500, contracts=100) > 0.50

    def test_larger_orders_amortise_the_rounding_better(self):
        """Under the per-order round-up model, size dilutes the penalty."""
        assert effective_price(370, 500) <= effective_price(370, 1)

    def test_edge_after_fees_is_negative_at_fair_value(self):
        assert edge_after_fees_tenths(
            ask_tenths=500, contracts=100, fair_probability=0.50
        ) < 0


class TestKelly:
    def test_no_edge_gives_no_stake(self):
        assert full_kelly_fraction(0.50, 0.50) == 0.0

    def test_negative_edge_never_returns_a_negative_size(self):
        """Negative Kelly means 'bet the other side' -- a different decision,
        not a negative number of contracts."""
        assert full_kelly_fraction(0.40, 0.50) == 0.0

    def test_more_edge_means_more_stake(self):
        assert full_kelly_fraction(0.60, 0.50) > full_kelly_fraction(0.55, 0.50)

    def test_a_coin_flip_at_half_price_stakes_half_the_bankroll(self):
        """The textbook case: p=0.5, b=1 gives f* = 0. p=0.75, b=1 gives 0.5."""
        assert full_kelly_fraction(0.75, 0.50) == pytest.approx(0.5)


class TestSizingRefusals:
    """The assertions that protect the account."""

    def test_unreadable_exposure_refuses(self):
        """'Cannot determine the budget' must never resolve to 'unlimited'."""
        result = size_position(
            side="yes", ask_tenths=500, fair_probability=0.60, risk=RISK,
            current_exposure_dollars=None,
        )
        assert result.refused
        assert result.contracts == 0
        assert "unreadable" in result.refusal_reason

    def test_the_daily_loss_kill_switch_refuses(self):
        result = size_position(
            side="yes", ask_tenths=500, fair_probability=0.60, risk=RISK,
            current_exposure_dollars=0.0, daily_pnl_dollars=-100.0,
        )
        assert result.refused
        assert "kill switch" in result.refusal_reason.lower()

    def test_a_settled_price_refuses(self):
        result = size_position(
            side="yes", ask_tenths=1000, fair_probability=0.60, risk=RISK,
            current_exposure_dollars=0.0,
        )
        assert result.refused

    def test_an_order_below_the_minimum_is_zeroed_not_rounded_up(self):
        """Rounding up would spend more than the caps allow -- the one
        direction a risk control must never move."""
        tiny = RiskConfig(
            bankroll_dollars=1000.0, kelly_fraction=0.25, max_order_contracts=50,
            max_position_dollars=2.0,  # room for ~4 contracts at 50c
            max_exposure_dollars=400.0, max_daily_loss_dollars=100.0,
            min_order_contracts=10,
        )
        result = size_position(
            side="yes", ask_tenths=500, fair_probability=0.70, risk=tiny,
            current_exposure_dollars=0.0,
        )
        assert result.contracts == 0
        assert result.refused
        assert result.binding_constraint == "below_min_order_contracts"


class TestSizingCaps:
    def test_no_edge_sizes_to_zero_without_refusing(self):
        """Not a refusal -- 'no bet here' is a normal answer."""
        result = size_position(
            side="yes", ask_tenths=500, fair_probability=0.50, risk=RISK,
            current_exposure_dollars=0.0,
        )
        assert result.contracts == 0
        assert not result.refused
        assert result.binding_constraint == "no_edge"

    def test_the_order_cap_binds_and_says_so(self):
        result = size_position(
            side="yes", ask_tenths=500, fair_probability=0.95, risk=RISK,
            current_exposure_dollars=0.0,
        )
        assert result.contracts == RISK.max_order_contracts
        assert result.binding_constraint == "max_order_contracts"

    def test_existing_exposure_reduces_the_size(self):
        fresh = size_position(
            side="yes", ask_tenths=500, fair_probability=0.70, risk=RISK,
            current_exposure_dollars=0.0,
        )
        loaded = size_position(
            side="yes", ask_tenths=500, fair_probability=0.70, risk=RISK,
            current_exposure_dollars=395.0,
        )
        assert loaded.contracts < fresh.contracts

    def test_quarter_kelly_is_a_quarter_of_full_kelly(self):
        result = size_position(
            side="yes", ask_tenths=500, fair_probability=0.60, risk=RISK,
            current_exposure_dollars=0.0,
        )
        assert result.kelly_fraction_used == pytest.approx(
            result.kelly_fraction_full * 0.25
        )

    def test_the_binding_constraint_is_always_reported(self):
        """A size of 10 is indistinguishable between 'Kelly said so' and
        'the cap said so', and those need different responses."""
        result = size_position(
            side="yes", ask_tenths=500, fair_probability=0.60, risk=RISK,
            current_exposure_dollars=0.0,
        )
        assert result.binding_constraint


class TestFinalVerification:
    """Sizing approximates the fee per contract; this re-checks at real size."""

    def test_a_clearly_positive_order_verifies(self):
        assert verify_positive_after_fees(
            side="yes", ask_tenths=500, contracts=50, fair_probability=0.60
        )

    def test_a_marginal_order_fails_verification(self):
        assert not verify_positive_after_fees(
            side="yes", ask_tenths=500, contracts=10, fair_probability=0.505
        )

    def test_zero_contracts_never_verifies(self):
        assert not verify_positive_after_fees(
            side="yes", ask_tenths=500, contracts=0, fair_probability=0.90
        )
