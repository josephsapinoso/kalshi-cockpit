"""`backend/core/hedge.py` — what hedging a held parlay locks in (ADR 0077).

What these tests establish: the equalising hedge pays the same whichever way the
last leg goes, to the tenth of a cent; the floor is always the worse branch; the
fee is charged and rounded against you; depth and bankroll bound what is
reported as *available* without hiding what the full hedge would cost; every one
of the six refusals fires on its own condition and returns a reason rather than a
number; a book that quotes both sides for a dollar or less is read as bad data;
and a lock that is large relative to the stake is **deliberately not**
suppressed.

What they do not establish: that taking a lock is correct, that the guarantee is
exact (H4 is untested, so every figure is an upper bound), or anything at all
about a ticket with more than one leg still live.
"""

from __future__ import annotations

import pytest

from backend.core.correlation import Leg
from backend.core.hedge import (
    CROSSED_BOOK,
    FEE_UNREADABLE,
    MAX_DECIMAL_ODDS,
    MIN_DECIMAL_ODDS,
    MARKET_CLOSED,
    NO_ASK,
    NO_DEPTH,
    REFUSAL_REASONS,
    STALE_QUOTE,
    UNREADABLE_TICKET,
    Derisk,
    HedgeQuote,
    Lock,
    Refusal,
    derisk,
    hedge_lock,
    ticket_refusal,
)
from backend.core.prices import is_valid_price

NOW_MS = 1_700_000_000_000
MAX_AGE_MS = 30_000

#: $10 staked to return $100 -- 10x, an ordinary parlay, and a round payout so
#: the equalising hedge is exactly 100 contracts with no rounding to reason
#: about.
STAKE = 10_000
RETURN = 100_000


def quote(
    *,
    ask_tenths=450,
    depth=500.0,
    observed_ms=NOW_MS,
    status="active",
    leg_ask_tenths=None,
):
    return HedgeQuote(
        ticker="KXMLBGAME-26AUG26CINSF-CIN",
        side="no",
        ask_tenths=ask_tenths,
        depth_at_ask=depth,
        observed_ms=observed_ms,
        status=status,
        leg_ask_tenths=leg_ask_tenths,
    )


def lock(**kwargs):
    return hedge_lock(
        stake_tenths=kwargs.pop("stake_tenths", STAKE),
        return_tenths=kwargs.pop("return_tenths", RETURN),
        quote=kwargs.pop("quote", quote()),
        now_ms=kwargs.pop("now_ms", NOW_MS),
        max_quote_age_ms=kwargs.pop("max_quote_age_ms", MAX_AGE_MS),
        affordable_contracts=kwargs.pop("affordable_contracts", 1_000),
    )


class TestTheEqualisingHedge:
    def test_both_branches_pay_the_same_to_the_tenth_of_a_cent(self):
        result = lock()
        assert isinstance(result, Lock)
        rung = result.equalising
        assert rung.contracts == 100
        assert rung.if_leg_wins_tenths == rung.if_leg_loses_tenths

    def test_the_locked_amount_is_return_minus_stake_minus_cost(self):
        result = lock()
        rung = result.equalising
        assert rung.floor_tenths == RETURN - STAKE - rung.cost_tenths

    def test_the_floor_is_the_worse_of_the_two_branches(self):
        # 101 contracts overshoots: the win branch pays for a contract that
        # buys no extra settlement value, so the branches separate.
        result = lock(return_tenths=100_500)
        rung = result.equalising
        # 100 contracts leaves $0.50 of payout unhedged; 101 overshoots by
        # half a contract and still ends up with the higher floor. Pinning
        # the count is what makes the search over BOTH neighbours observable
        # -- dropping the ceiling candidate stayed GREEN without it.
        assert rung.contracts == 101
        assert rung.floor_tenths == min(
            rung.if_leg_wins_tenths, rung.if_leg_loses_tenths
        )

    def test_the_chosen_size_maximises_the_floor_over_its_neighbours(self):
        # The ladder does not carry n+-1, so comparing against `result.ladder`
        # would pass without ever entering the loop. The neighbours are built
        # directly, and the vacuity guard below is why that matters.
        from backend.core.hedge import _rung

        result = lock(return_tenths=333_330)
        best = result.equalising
        compared = 0
        for n in (best.contracts - 1, best.contracts + 1):
            neighbour = _rung(
                n,
                ask_tenths=450,
                stake_tenths=STAKE,
                return_tenths=333_330,
                depth_contracts=500,
                affordable_contracts=1_000,
            )
            assert neighbour is not None
            assert neighbour.floor_tenths <= best.floor_tenths
            compared += 1
        assert compared == 2

    def test_the_same_inputs_give_the_same_answer(self):
        assert lock().equalising == lock().equalising


class TestTheFee:
    def test_cost_exceeds_the_bare_contract_price(self):
        rung = lock().equalising
        assert rung.fee_tenths > 0
        assert rung.cost_tenths == rung.contracts * 450 + rung.fee_tenths

    def test_the_fee_is_rounded_against_you(self):
        from backend.core.fees import calculate_fee

        rung = lock().equalising
        exact = calculate_fee(450, rung.contracts)
        assert rung.fee_tenths >= exact * 1000

    def test_an_unreadable_fee_refuses_rather_than_pricing_a_free_hedge(self, monkeypatch):
        # `calculate_fee` returns None on an untradeable price, which
        # `quote.refusal` already rules out -- so this branch is unreachable
        # through the front door and is reached the only way it can be. A cost
        # with no fee in it is the shape that manufactures a lock out of
        # nothing, which is what the branch exists to stop.
        monkeypatch.setattr(
            "backend.core.hedge.calculate_fee", lambda *a, **k: None
        )
        result = lock()
        assert isinstance(result, Refusal)
        assert result.reason == FEE_UNREADABLE

    def test_a_hedge_that_costs_more_than_it_can_pay_locks_a_loss(self):
        # An ask of 99c against a $1 settlement: the hedge cannot lock a gain,
        # and the module says so with a negative floor rather than refusing.
        result = lock(quote=quote(ask_tenths=990))
        assert result.equalising.floor_tenths < 0
        assert result.is_guaranteed_profit is False


class TestRefusals:
    def test_every_reason_is_declared(self):
        for value in (
            FEE_UNREADABLE,
            NO_ASK,
            NO_DEPTH,
            STALE_QUOTE,
            MARKET_CLOSED,
            CROSSED_BOOK,
            UNREADABLE_TICKET,
        ):
            assert value in REFUSAL_REASONS

    def test_an_empty_book_refuses_rather_than_pricing_a_free_contract(self):
        result = lock(quote=quote(ask_tenths=None))
        assert isinstance(result, Refusal)
        assert result.reason == NO_ASK

    @pytest.mark.parametrize("settled", [0, 1000])
    def test_a_settled_price_is_not_a_quote(self, settled):
        result = lock(quote=quote(ask_tenths=settled))
        assert isinstance(result, Refusal)
        assert result.reason == NO_ASK

    def test_the_ask_test_agrees_with_is_valid_price_over_the_whole_grid(self):
        # The producer/consumer agreement `tasks/lessons.md` asks for: this
        # module's own predicate may not drift from the one every other money
        # path applies.
        for ask in range(0, 1001):
            refusal = quote(ask_tenths=ask).refusal(
                now_ms=NOW_MS, max_quote_age_ms=MAX_AGE_MS
            )
            refused_for_price = refusal is not None and refusal.reason == NO_ASK
            assert refused_for_price == (not is_valid_price(ask)), ask

    def test_a_price_with_no_size_behind_it_is_not_a_hedge(self):
        result = lock(quote=quote(depth=0.0))
        assert isinstance(result, Refusal)
        assert result.reason == NO_DEPTH

    def test_unknown_depth_refuses_rather_than_assuming_none(self):
        result = lock(quote=quote(depth=None))
        assert isinstance(result, Refusal)
        assert result.reason == NO_DEPTH

    def test_a_stale_quote_refuses(self):
        result = lock(now_ms=NOW_MS + MAX_AGE_MS + 1)
        assert isinstance(result, Refusal)
        assert result.reason == STALE_QUOTE

    def test_a_quote_with_no_observation_time_cannot_be_aged(self):
        result = lock(quote=quote(observed_ms=None))
        assert isinstance(result, Refusal)
        assert result.reason == STALE_QUOTE

    @pytest.mark.parametrize(
        "status", ["closed", "settled", "finalized", "determined", "SETTLED"]
    )
    def test_a_market_the_venue_is_done_with_refuses(self, status):
        result = lock(quote=quote(status=status))
        assert isinstance(result, Refusal)
        assert result.reason == MARKET_CLOSED

    def test_both_sides_for_a_dollar_is_read_as_bad_data(self):
        result = lock(quote=quote(ask_tenths=450, leg_ask_tenths=500))
        assert isinstance(result, Refusal)
        assert result.reason == CROSSED_BOOK

    def test_a_real_book_with_a_spread_prices_normally(self):
        result = lock(quote=quote(ask_tenths=450, leg_ask_tenths=580))
        assert isinstance(result, Lock)

    def test_a_refusal_carries_a_sentence_and_not_only_a_code(self):
        result = lock(quote=quote(ask_tenths=None))
        assert isinstance(result, Refusal)
        assert len(result.detail.split()) >= 5


class TestTheTypedTicket:
    def test_a_misplaced_decimal_point_is_refused(self):
        # $10 staked to return $1,000,000: two decimal points out, and every
        # number downstream would be arithmetically correct.
        result = lock(return_tenths=RETURN * 10_000)
        assert isinstance(result, Refusal)
        assert result.reason == UNREADABLE_TICKET

    def test_the_odds_ceiling_is_where_it_says_it_is(self):
        # The boundary is pinned rather than left where an inequality happens
        # to fall: the first version of the test above sat exactly ON it and
        # passed for the wrong reason.
        at_ceiling = int(STAKE * MAX_DECIMAL_ODDS)
        assert ticket_refusal(STAKE, at_ceiling) is None
        assert ticket_refusal(STAKE, at_ceiling + 1).reason == UNREADABLE_TICKET

    def test_the_odds_floor_is_where_it_says_it_is(self):
        at_floor = int(STAKE * MIN_DECIMAL_ODDS)
        assert ticket_refusal(STAKE, at_floor) is None
        assert ticket_refusal(STAKE, at_floor - 1).reason == UNREADABLE_TICKET

    def test_a_return_below_the_stake_is_refused_in_its_own_words(self):
        # Two guards reach this input -- the explicit comparison and the odds
        # floor -- so the reason code alone cannot tell them apart, and a
        # mutation removing the comparison stayed GREEN until this asserted
        # the sentence instead. The words are the thing the comparison
        # uniquely produces, and the words are what Joe reads.
        refusal = ticket_refusal(10_000, 9_000)
        assert refusal.reason == UNREADABLE_TICKET
        assert "not above the stake" in refusal.detail

    @pytest.mark.parametrize("bad", [0, -1])
    def test_a_stake_of_zero_or_less_is_refused(self, bad):
        assert ticket_refusal(bad, 100_000).reason == UNREADABLE_TICKET

    def test_an_ordinary_ticket_passes(self):
        assert ticket_refusal(STAKE, RETURN) is None

    def test_the_six_leg_card_that_prompted_the_desk_passes(self):
        # $4.99 to return $333.33 -- 66.8x, the real slip behind ADR 0070.
        assert ticket_refusal(4_990, 333_330) is None


class TestRuleOneIsAppliedToTheBookAndNotToTheSizeOfTheLock:
    """A large lock is what hedging a longshot looks like, not a bug.

    Deliberately asserts an ABSENCE. If a future session adds a lock-to-stake
    suppression, this test goes red and the ADR has to be reopened -- which is
    the point, because such a rule would silence exactly the case the feature
    exists for.
    """

    def test_a_lock_thirty_times_the_stake_is_reported_not_suppressed(self):
        result = lock(
            stake_tenths=4_990,
            return_tenths=333_330,
            quote=quote(ask_tenths=450, depth=5_000.0),
            affordable_contracts=5_000,
        )
        assert isinstance(result, Lock)
        assert result.is_guaranteed_profit
        assert result.best_available.floor_tenths > 30 * 4_990


class TestDepthAndBankroll:
    def test_depth_bounds_what_is_reported_as_available(self):
        result = lock(quote=quote(depth=40.0))
        assert result.best_available.contracts <= 40
        assert result.equalising.contracts == 100

    def test_bankroll_bounds_what_is_reported_as_available(self):
        result = lock(affordable_contracts=25)
        assert result.best_available.contracts <= 25

    def test_an_unaffordable_full_hedge_still_reports_what_it_would_cost(self):
        result = lock(affordable_contracts=5)
        assert result.equalising.contracts == 100
        assert result.equalising.affordable is False

    def test_nothing_affordable_reports_no_best_rung_rather_than_a_zero(self):
        result = lock(affordable_contracts=0)
        assert result.best_available is None
        assert result.is_guaranteed_profit is False

    def test_the_alert_predicate_reads_the_reachable_rung_not_the_full_one(self):
        # A full hedge would lock a gain; only one contract is affordable, and
        # one contract does not. `is_guaranteed_profit` must follow the rung
        # that could actually be bought.
        full = lock()
        assert full.is_guaranteed_profit

        capped = lock(affordable_contracts=1)
        assert capped.equalising.floor_tenths > 0
        assert capped.best_available.contracts == 1
        assert capped.best_available.floor_tenths < 0
        assert capped.is_guaranteed_profit is False


class TestDerisk:
    def _legs(self, n: int, *, same_game: bool = False):
        return [
            Leg(
                label=f"leg{i}",
                probability=0.7,
                event_key="same" if same_game else f"game{i}",
                league="baseball_mlb",
                commence_ms=NOW_MS,
            )
            for i in range(n)
        ]

    def call(self, legs, **kwargs):
        return derisk(
            stake_tenths=STAKE,
            return_tenths=RETURN,
            quote=kwargs.pop("quote", quote()),
            live_legs=legs,
            now_ms=NOW_MS,
            max_quote_age_ms=MAX_AGE_MS,
            affordable_contracts=1_000,
        )

    def test_it_reports_no_floor_because_there_is_none(self):
        result = self.call(self._legs(3))
        assert isinstance(result, Derisk)
        assert not hasattr(result, "floor_tenths")
        assert not hasattr(result, "is_guaranteed_profit")

    def test_the_notional_value_is_the_return_times_the_joint(self):
        result = self.call(self._legs(2))
        assert result.joint_probability == pytest.approx(0.49, abs=0.02)
        assert result.notional_value_tenths == int(
            round(RETURN * result.joint_probability)
        )

    def test_two_legs_in_one_game_withhold_the_joint_and_keep_the_ladder(self):
        result = self.call(self._legs(2, same_game=True))
        assert result.joint_probability is None
        assert result.notional_value_tenths is None
        assert result.joint_refusal is not None
        assert result.ladder

    def test_no_readable_leg_price_says_so_rather_than_going_quiet(self):
        # The caller hands over an empty leg set when it could not read a
        # price for every live leg. A missing joint with no reason attached
        # renders as an absence, which reads as zero.
        result = self.call([])
        assert isinstance(result, Derisk)
        assert result.joint_probability is None
        assert result.notional_value_tenths is None
        assert result.joint_refusal is not None
        assert result.ladder

    def test_it_refuses_the_same_books_a_lock_refuses(self):
        result = self.call(self._legs(2), quote=quote(ask_tenths=None))
        assert isinstance(result, Refusal)
        assert result.reason == NO_ASK
