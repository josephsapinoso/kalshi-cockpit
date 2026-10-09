"""Builder tests: correlation and parlay valuation.

The assertion that matters most is `test_same_game_legs_are_refused`. Assuming
independence on correlated legs overstates the parlay's chance of landing, and
it does so in the direction that makes a bad bet look priceable.
"""

from __future__ import annotations

import random

import pytest

from backend.core.correlation import (
    DEFAULT_CORRELATION,
    CorrelationRefused,
    Leg,
    Relationship,
    classify,
    correlation_matrix,
    independence_error,
    joint_probability_all,
)
from backend.core.parlay import (
    ParlayQuote,
    american_to_decimal,
    decimal_to_american,
    value_parlay,
)

DAY = 86_400_000
NOW = 1_754_800_000_000


def leg(label, p, event="E1", league="americanfootball_nfl", offset=0):
    return Leg(
        label=label, probability=p, event_key=event, league=league,
        commence_ms=NOW + offset,
    )


class TestClassification:
    def test_the_same_fixture_is_same_game(self):
        assert classify(leg("a", 0.5), leg("b", 0.5)) is Relationship.SAME_GAME

    def test_same_day_same_league(self):
        assert classify(
            leg("a", 0.5, event="E1"), leg("b", 0.5, event="E2", offset=3600_000)
        ) is Relationship.SAME_DAY_SAME_LEAGUE

    def test_same_day_cross_league(self):
        assert classify(
            leg("a", 0.5, event="E1"),
            leg("b", 0.5, event="E2", league="baseball_mlb", offset=3600_000),
        ) is Relationship.SAME_DAY_CROSS_LEAGUE

    def test_different_days_are_independent(self):
        assert classify(
            leg("a", 0.5, event="E1"), leg("b", 0.5, event="E2", offset=5 * DAY)
        ) is Relationship.INDEPENDENT

    def test_same_game_has_no_default_correlation(self):
        """Because the sign depends on the specific pair, so any default would
        be a guess dressed as a number."""
        assert Relationship.SAME_GAME not in DEFAULT_CORRELATION


class TestRefusal:
    """The central safety property of the Builder."""

    def test_same_game_legs_are_refused(self):
        with pytest.raises(CorrelationRefused) as exc:
            correlation_matrix([leg("Team wins", 0.55), leg("Over 44.5", 0.52)])
        assert "same fixture" in str(exc.value)
        assert "overstate" in str(exc.value)

    def test_the_refusal_explains_what_to_do(self):
        with pytest.raises(CorrelationRefused) as exc:
            joint_probability_all([leg("a", 0.5), leg("b", 0.5)])
        assert "overrides" in str(exc.value)

    def test_an_explicit_override_allows_same_game_pricing(self):
        """Supplying a measured correlation is the sanctioned path."""
        legs = [leg("Team wins", 0.55), leg("Over 44.5", 0.52)]
        joint = joint_probability_all(
            legs, overrides={("Team wins", "Over 44.5"): 0.35}
        )
        assert 0.0 < joint < 1.0

    def test_positive_correlation_raises_the_joint_probability(self):
        legs = [leg("a", 0.55), leg("b", 0.52)]
        naive = 0.55 * 0.52
        correlated = joint_probability_all(
            legs, overrides={("a", "b"): 0.40}
        )
        assert correlated > naive


class TestJointProbability:
    def test_independent_legs_reproduce_the_product(self):
        legs = [
            leg("a", 0.6, event="E1", offset=0),
            leg("b", 0.5, event="E2", offset=10 * DAY),
        ]
        assert joint_probability_all(legs) == pytest.approx(0.30, abs=1e-9)

    def test_mild_correlation_moves_the_answer_only_slightly(self):
        """Same-day legs are correlated, but not much."""
        legs = [
            leg("a", 0.6, event="E1"),
            leg("b", 0.5, event="E2", offset=3600_000),
        ]
        assert joint_probability_all(legs) == pytest.approx(0.30, abs=0.02)

    def test_independence_error_is_reported_in_points(self):
        legs = [leg("a", 0.6, event="E1"), leg("b", 0.5, event="E2", offset=3600_000)]
        # Positive correlation means naive multiplication UNDERstates a
        # both-win parlay, so the error is negative here.
        assert independence_error(legs) < 0

    def test_inconsistent_correlations_are_repaired_not_crashed(self):
        """Three legs each 0.9 correlated cannot all be true."""
        legs = [
            leg("a", 0.5, event="E1"),
            leg("b", 0.5, event="E2", offset=DAY * 3),
            leg("c", 0.5, event="E3", offset=DAY * 6),
        ]
        overrides = {("a", "b"): 0.95, ("b", "c"): 0.95, ("a", "c"): -0.95}
        assert 0.0 <= joint_probability_all(legs, overrides=overrides) <= 1.0

    def test_a_certainty_is_not_a_leg(self):
        for bad in (0.0, 1.0, -0.1, 1.5):
            with pytest.raises(ValueError):
                leg("x", bad)


class TestOddsConversion:
    @pytest.mark.parametrize(
        "american,decimal", [(100, 2.0), (-110, 1.909), (200, 3.0), (-200, 1.5)]
    )
    def test_american_to_decimal(self, american, decimal):
        assert american_to_decimal(american) == pytest.approx(decimal, abs=0.001)

    def test_round_trips(self):
        for american in (-350, -110, 100, 150, 600):
            assert decimal_to_american(american_to_decimal(american)) == american


class TestParlayValuation:
    def _three_leg(self, offered_american: int):
        """Three roughly coin-flip legs -- three -110 sides devigged to ~0.50.

        Fair price on these is about +700. Books typically pay +550, which is
        where the 20%-ish parlay hold comes from. An earlier version of this
        fixture used three favourites (0.55/0.52/0.60, fair +483) while quoting
        the coin-flip payout of +600, which made the book look generous -- the
        code was right and the test data was wrong.
        """
        legs = [
            leg("A", 0.50, event="E1", offset=0),
            leg("B", 0.50, event="E2", offset=8 * DAY),
            leg("C", 0.53, event="E3", offset=16 * DAY),
        ]
        return ParlayQuote(
            legs=tuple(legs), offered_decimal=american_to_decimal(offered_american)
        )

    def test_a_typical_book_parlay_is_clearly_negative(self):
        """The parlay is where a book makes back its margin: double-digit hold
        against 4-5% on the straight lines that compose it."""
        valuation = value_parlay(self._three_leg(+550))
        assert not valuation.is_positive_ev
        assert valuation.hold > 0.10

    def test_the_verdict_leads_with_the_hold(self):
        """The hold generalises; 'this ticket is -14% EV' does not."""
        verdict = value_parlay(self._three_leg(+550)).verdict
        assert verdict.startswith("Kalshi's ask is ")
        assert "; hold " in verdict

    def test_a_generous_price_is_recognised(self):
        valuation = value_parlay(self._three_leg(+900))
        assert valuation.is_positive_ev
        assert "; hold " in valuation.verdict

    def test_the_fair_price_is_longer_than_the_offered_one(self):
        """The direction that makes a parlay bad, asserted directly."""
        valuation = value_parlay(self._three_leg(+550))
        assert valuation.fair_decimal > valuation.offered_decimal

    def test_the_independence_error_is_always_reported(self):
        """For correlated legs it is frequently larger than the claimed edge."""
        assert value_parlay(self._three_leg(+550)).independence_error_points is not None

    def test_same_game_parlays_are_refused(self):
        quote = ParlayQuote(
            legs=(leg("Team wins", 0.55), leg("Over 44.5", 0.52)),
            offered_decimal=3.5,
        )
        with pytest.raises(CorrelationRefused):
            value_parlay(quote)

    def test_a_single_leg_is_not_a_parlay(self):
        with pytest.raises(ValueError):
            value_parlay(ParlayQuote(legs=(leg("A", 0.5),), offered_decimal=2.0))
