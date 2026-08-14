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
from backend.core.fees import calculate_fee
from backend.core.prices import PRICE_MAX, cents_to_tenths
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

    **51.75% taker** and 50.44% maker at 50c and size, against 52.38% at a -110
    sportsbook. Kalshi lowers the bar; it does not clear it.

    **This class has now been wrong in both directions, and the history is the
    point.** It first claimed 51.75% behind a band (`0.50 < rate < 0.53`) three
    hundred times wider than the error it was meant to pin. That was corrected
    to 52.00% on the grounds that `calculate_fee` charged the conservative
    maximum across candidate models, so the applied bar sat a quarter-point
    above the published-coefficient figure.

    **2026-08-14: it is 51.75% again, and NOT because the correction was wrong.**
    The max-of-models hedge was retired -- Model B matches 0 of 11 real taker
    fills and is refuted -- so the applied bar is now the measured model's, which
    at `k = 0.070` on a $0.0001 grid is exactly what the published coefficient
    gives. The previous version of this test said, in as many words: *"If these
    ever coincide, either the hedge was dropped or the fee model changed, and
    both are worth failing a test over."* Both happened. It failed. It was right
    to.

    **The bar the code applies is still an overstatement, and by a known
    factor.** Baseball measured `k = 0.035`, which would put the bar at
    **50.88%**; `TAKER_COEFFICIENT` stays at 0.070 because which attribute
    carries that split is unresolved and the record spans four days. So:
    50.88% true on baseball, 51.75% applied, 52.38% at a sportsbook.
    """

    def test_the_taker_breakeven_is_exactly_51_75_percent(self):
        """Pinned to the value, not to a band.

        A range wide enough to contain both the claimed and the actual number
        cannot tell you which one the code implements. That defect is what let
        the original error survive for years.
        """
        rate = breakeven_win_rate(cents_to_tenths(50), contracts=100)
        assert rate == pytest.approx(0.5175, abs=0.0001)

    def test_it_is_no_longer_above_the_published_coefficient_figure(self):
        """The discriminating assertion, inverted from its previous form.

        It used to assert `rate > 0.5175`, to catch the hedge being dropped
        silently. The hedge is now deliberately gone, so the same guard has to
        point the other way: if the bar climbs back above the published figure,
        a refuted model has been re-admitted to the money path.
        """
        rate = breakeven_win_rate(cents_to_tenths(50), contracts=100)
        assert rate == pytest.approx(0.5175, abs=0.0001), (
            "above the published-coefficient figure means a max-of-models "
            "hedge is back; below it means k was lowered without an ADR"
        )

    def test_the_applied_bar_still_overstates_the_measured_baseball_rate(self):
        """The gap between what is charged and what was measured, pinned.

        Baseball fills measured `k = 0.035`. This asserts the applied bar sits
        *above* the bar that rate implies -- i.e. the module is still
        overstating, which is the direction it has always chosen -- and pins how
        far, so that closing the gap is a visible decision rather than a drift.
        """
        applied = breakeven_win_rate(cents_to_tenths(50), contracts=100)
        measured_baseball = 0.508750
        assert applied > measured_baseball
        assert applied - measured_baseball == pytest.approx(0.00875, abs=0.0001)

    def test_taker_breakeven_at_fifty_cents_beats_a_sportsbook(self):
        rate = breakeven_win_rate(cents_to_tenths(50), contracts=100)
        assert rate < 0.5238, "should beat a -110 sportsbook"
        # The headroom, stated: 0.63 points at the applied rate. It was 0.38
        # while a refuted model was inflating the fee. On baseball's measured
        # rate it would be 1.50 -- none of which is an edge, only a lower bar.
        assert 0.5238 - rate == pytest.approx(0.0063, abs=0.0002)

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
            current_exposure_dollars=None, current_position_dollars=0.0, daily_pnl_dollars=0.0,
        )
        assert result.refused
        assert result.contracts == 0
        assert "unreadable" in result.refusal_reason

    def test_the_daily_loss_kill_switch_refuses(self):
        """**Kept, and deliberately not enough.**

        This test supplies `daily_pnl_dollars=-100.0` itself, so it can only
        ever establish that the comparison is right -- which it is, and was
        throughout. It could never go red for the reason that mattered, because
        *does anything supply this?* is not the question it asks, and for the
        project's life nothing did. The pair that covers both halves is this
        test plus `tests/test_has_callers.py::
        test_every_production_call_site_supplies_the_parameter`, with
        `tests/test_quote_refresh.py::TestTheDailyLossLimitReachesTheOrderPath`
        driving the real route against P&L written to the database.
        """
        result = size_position(
            side="yes", ask_tenths=500, fair_probability=0.60, risk=RISK,
            current_exposure_dollars=0.0, current_position_dollars=0.0,
            daily_pnl_dollars=-100.0,
        )
        assert result.refused
        assert "kill switch" in result.refusal_reason.lower()
        assert result.binding_constraint == "max_daily_loss_dollars", (
            "a refusal that reports `refused` says nothing about what refused. "
            "The Ticket renders this field as 'Bound by', and 'the kill switch "
            "is engaged' and 'the database is unreadable' need opposite "
            "responses from whoever is holding the phone."
        )

    def test_unreadable_daily_pnl_refuses_rather_than_assuming_no_losses(self):
        """The class of bug, not the instance.

        `daily_pnl_dollars` defaulted to `0.0` until 2026-08-10, which is the
        maximally permissive value a loss limit can be handed: "no information"
        read as "no losses". It has no default now, and `None` -- which is what
        every reader in this project returns when it cannot read -- refuses.
        """
        result = size_position(
            side="yes", ask_tenths=500, fair_probability=0.60, risk=RISK,
            current_exposure_dollars=0.0, current_position_dollars=0.0,
            daily_pnl_dollars=None,
        )
        assert result.refused
        assert result.contracts == 0
        assert result.binding_constraint == "daily_pnl_unreadable"
        assert "unreadable" in result.refusal_reason

    def test_unreadable_position_refuses_rather_than_assuming_none_is_held(self):
        result = size_position(
            side="yes", ask_tenths=500, fair_probability=0.60, risk=RISK,
            current_exposure_dollars=0.0, current_position_dollars=None,
            daily_pnl_dollars=0.0,
        )
        assert result.refused
        assert result.contracts == 0
        assert result.binding_constraint == "position_unreadable"

    @pytest.mark.parametrize(
        "omitted", ["current_position_dollars", "daily_pnl_dollars"]
    )
    def test_omitting_a_risk_input_is_an_error_rather_than_a_zero(self, omitted):
        """The strongest form of the fix, and the reason it is worth the churn.

        `None` refusing is a runtime control. A parameter with no default is a
        *call-site* one: the omission that shipped this bug -- four production
        call sites, none of which mentioned these arguments at all -- is now
        impossible to write. A refusal at runtime would still have to be
        observed by somebody; a `TypeError` cannot be deployed.
        """
        args = dict(
            side="yes", ask_tenths=500, fair_probability=0.60, risk=RISK,
            current_exposure_dollars=0.0, current_position_dollars=0.0,
            daily_pnl_dollars=0.0,
        )
        del args[omitted]
        with pytest.raises(TypeError, match=omitted):
            size_position(**args)

    def test_a_settled_price_refuses(self):
        result = size_position(
            side="yes", ask_tenths=1000, fair_probability=0.60, risk=RISK,
            current_exposure_dollars=0.0, current_position_dollars=0.0, daily_pnl_dollars=0.0,
        )
        assert result.refused

    def test_a_cap_leaving_room_for_under_one_contract_zeroes_rather_than_rounding(
        self,
    ):
        """Rounding up would spend more than the caps allow -- the one
        direction a risk control must never move."""
        tiny = RiskConfig(
            bankroll_dollars=1000.0, kelly_fraction=0.25, max_order_contracts=50,
            max_position_dollars=0.30,  # under the cost of one 50c contract
            max_exposure_dollars=400.0, max_daily_loss_dollars=100.0,
        )
        result = size_position(
            side="yes", ask_tenths=500, fair_probability=0.70, risk=tiny,
            current_exposure_dollars=0.0, current_position_dollars=0.0, daily_pnl_dollars=0.0,
        )
        assert result.contracts == 0
        assert result.binding_constraint == "max_position_dollars"


class TestSmallOrdersNeedNoMinimum:
    """Why `min_order_contracts` was deleted rather than lowered.

    It existed because Model A rounds the fee up on the whole order, so a small
    order pays a rounding penalty a large one amortises away. The penalty is
    real. **The sizer was already paying it**: `effective_price` charges the fee
    a single contract would pay, and that is the most expensive per-contract fee
    any size pays. So the minimum was refusing +EV orders rather than preventing
    -EV ones -- and below roughly a $250 bankroll it closed the 50c band, where
    this strategy trades, silently, by returning a plausible zero.

    These assert the property that makes the deletion safe rather than the
    deletion itself. If a future fee model ever charges a large order MORE per
    contract than a single one, the first test goes red and the sizer needs a
    real whole-order check. A guard would be the wrong shape here: under both
    current fee models it could never fire, and this repo has learned that a
    guard which cannot fire reads as protection while providing none.
    """

    def test_per_contract_cost_never_rises_with_order_size(self):
        """The whole basis for sizing at the one-contract fee.

        Exhaustive, not sampled: every tradeable price, sizes 1-200, maker and
        taker. A sampled version would miss exactly the rounding boundary that
        would break it.
        """
        for maker in (False, True):
            for price_tenths in range(1, PRICE_MAX):
                one = calculate_fee(price_tenths, 1, maker)
                for contracts in range(1, 201):
                    per = calculate_fee(price_tenths, contracts, maker) / contracts
                    assert per <= one + 1e-12, (
                        f"{contracts} contracts at {price_tenths} tenths costs "
                        f"{per:.6f}/contract against {one:.6f} for one. Sizing "
                        f"prices at the one-contract fee, so this order can be "
                        f"sized positive and settle negative."
                    )

    @pytest.mark.parametrize("ask_tenths", [100, 200, 300, 500, 800, 900])
    def test_any_order_kelly_sizes_above_zero_is_positive_after_the_whole_fee(
        self, ask_tenths
    ):
        """The property the deleted minimum was reaching for, stated directly.

        Sized at all -> +EV at that size. Checked at the *marginal* fair value
        where Kelly first turns positive, because that is where a wrong
        implementation and a right one differ. A comfortable edge passes under
        either, which is what makes the obvious version of this test useless.
        """
        marginal = effective_price(ask_tenths, contracts=1)
        fair = marginal + 0.001
        result = size_position(
            side="yes", ask_tenths=ask_tenths, fair_probability=fair, risk=RISK,
            current_exposure_dollars=0.0, current_position_dollars=0.0, daily_pnl_dollars=0.0,
        )
        assert result.contracts > 0, "a positive edge must size to something"
        assert verify_positive_after_fees(
            side="yes", ask_tenths=ask_tenths, contracts=result.contracts,
            fair_probability=fair,
        )

    def test_a_single_contract_is_allowed_and_is_positive(self):
        """The case the old minimum refused outright.

        One contract at 20c pays the largest per-contract fee on the board --
        0.88c above the large-order limit -- and is still +EV, because the sizer
        priced it at exactly that fee.
        """
        broke = RiskConfig(
            bankroll_dollars=100.0, kelly_fraction=0.25, max_order_contracts=50,
            max_position_dollars=10.0, max_exposure_dollars=40.0,
            max_daily_loss_dollars=10.0,
        )
        result = size_position(
            side="yes", ask_tenths=200, fair_probability=0.30, risk=broke,
            current_exposure_dollars=0.0, current_position_dollars=0.0, daily_pnl_dollars=0.0,
        )
        assert result.contracts >= 1
        assert not result.refused
        assert verify_positive_after_fees(
            side="yes", ask_tenths=200, contracts=result.contracts,
            fair_probability=0.30,
        )


class TestSizingCaps:
    def test_no_edge_sizes_to_zero_without_refusing(self):
        """Not a refusal -- 'no bet here' is a normal answer."""
        result = size_position(
            side="yes", ask_tenths=500, fair_probability=0.50, risk=RISK,
            current_exposure_dollars=0.0, current_position_dollars=0.0, daily_pnl_dollars=0.0,
        )
        assert result.contracts == 0
        assert not result.refused
        assert result.binding_constraint == "no_edge"

    def test_the_order_cap_binds_and_says_so(self):
        result = size_position(
            side="yes", ask_tenths=500, fair_probability=0.95, risk=RISK,
            current_exposure_dollars=0.0, current_position_dollars=0.0, daily_pnl_dollars=0.0,
        )
        assert result.contracts == RISK.max_order_contracts
        assert result.binding_constraint == "max_order_contracts"

    def test_existing_exposure_reduces_the_size(self):
        fresh = size_position(
            side="yes", ask_tenths=500, fair_probability=0.70, risk=RISK,
            current_exposure_dollars=0.0, current_position_dollars=0.0, daily_pnl_dollars=0.0,
        )
        loaded = size_position(
            side="yes", ask_tenths=500, fair_probability=0.70, risk=RISK,
            current_exposure_dollars=395.0, current_position_dollars=0.0, daily_pnl_dollars=0.0,
        )
        assert loaded.contracts < fresh.contracts

    def test_quarter_kelly_is_a_quarter_of_full_kelly(self):
        result = size_position(
            side="yes", ask_tenths=500, fair_probability=0.60, risk=RISK,
            current_exposure_dollars=0.0, current_position_dollars=0.0, daily_pnl_dollars=0.0,
        )
        assert result.kelly_fraction_used == pytest.approx(
            result.kelly_fraction_full * 0.25
        )

    def test_the_binding_constraint_is_always_reported(self):
        """A size of 10 is indistinguishable between 'Kelly said so' and
        'the cap said so', and those need different responses."""
        result = size_position(
            side="yes", ask_tenths=500, fair_probability=0.60, risk=RISK,
            current_exposure_dollars=0.0, current_position_dollars=0.0, daily_pnl_dollars=0.0,
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
