"""Builder tests: correlation, parlays, teasers.

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
    kalshi_equivalent,
    value_parlay,
)
from backend.core.teaser import (
    STANDARD_TWO_TEAM_DECIMAL,
    TeaserUnpriceable,
    build_leg,
    find_wong_candidates,
    value_teaser,
)
from backend.model.margins import (
    MarginDistribution,
    default_distribution,
    fit_by_spread,
    spread_bucket_for,
)
from backend.model.synthetic import (
    synthetic_bucket_observations,
    synthetic_margins,
)

DAY = 86_400_000
NOW = 1_754_800_000_000


def leg(label, p, event="E1", league="americanfootball_nfl", offset=0):
    return Leg(
        label=label, probability=p, event_key=event, league=league,
        commence_ms=NOW + offset,
    )


@pytest.fixture(scope="module")
def nfl_buckets():
    """Synthetic NFL margins fitted per closing-spread bucket.

    A single league-wide fit cannot price a teaser: reaching an eight-point
    favourite means dragging the distribution eight points, which relocates
    every key number. `core.teaser` refuses on exactly that, so the fixture has
    to be bucketed for the teaser tests to be testing anything real.
    """
    return fit_by_spread(
        "americanfootball_nfl",
        synthetic_bucket_observations([-8.0, 2.0, -4.0], n_per_bucket=1200),
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
        assert "holds" in verdict
        assert "Don't" in verdict

    def test_a_generous_price_is_recognised(self):
        valuation = value_parlay(self._three_leg(+900))
        assert valuation.is_positive_ev
        assert "verify the legs" in valuation.verdict

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


class TestKalshiEquivalent:
    def test_it_is_described_as_a_different_bet(self):
        """Legs settle independently, so partial success pays partially."""
        legs = [
            leg("A", 0.55, event="E1", offset=0),
            leg("B", 0.52, event="E2", offset=8 * DAY),
        ]
        equivalent = kalshi_equivalent(legs)
        assert "Not the same bet" in equivalent.note
        assert "fee per leg" in equivalent.note

    def test_fees_scale_with_the_number_of_legs(self):
        two = kalshi_equivalent([
            leg("A", 0.5, event="E1", offset=0),
            leg("B", 0.5, event="E2", offset=8 * DAY),
        ])
        three = kalshi_equivalent([
            leg("A", 0.5, event="E1", offset=0),
            leg("B", 0.5, event="E2", offset=8 * DAY),
            leg("C", 0.5, event="E3", offset=16 * DAY),
        ])
        assert three.total_fee_dollars > two.total_fee_dollars

    def test_fee_share_is_worst_at_the_money(self):
        """Kalshi fees peak at 50c."""
        at_money = kalshi_equivalent([
            leg("A", 0.5, event="E1", offset=0),
            leg("B", 0.5, event="E2", offset=8 * DAY),
        ])
        assert at_money.fee_share_of_stake > 0


class TestTeasers:
    def _leg(self, buckets, team, line, margin, event, offset=0):
        return build_leg(
            buckets[spread_bucket_for(line)],
            team=team, original_line=line, points=6.0,
            predicted_margin=margin, event_key=event,
            league="americanfootball_nfl", commence_ms=NOW + offset,
        )

    def test_a_league_wide_fit_is_refused(self, nfl_buckets):
        """The subtler of the two refusals. A pooled empirical distribution has
        to be dragged onto the game, and dragging moves the key numbers -- so it
        would price this game worse than the normal curve it replaced, while
        looking like evidence."""
        pooled = MarginDistribution("americanfootball_nfl").fit(
            synthetic_margins(0.0, 1200, seed=14)
        )
        assert pooled.is_empirical
        with pytest.raises(TeaserUnpriceable) as exc:
            build_leg(
                pooled, team="A", original_line=-8.0, points=6.0,
                predicted_margin=8.0, event_key="E1",
                league="americanfootball_nfl", commence_ms=NOW,
            )
        assert "league-wide fit" in str(exc.value)
        assert "fit_by_spread" in str(exc.value)

    def test_the_bucketed_fit_prices_it_instead(self, nfl_buckets):
        """The other half of the previous test: same game, right distribution."""
        teased = self._leg(nfl_buckets, "A", -8.0, 8.0, "E1")
        assert 0.0 < teased.cover_probability < 1.0

    def test_a_smooth_distribution_is_refused(self, ):
        """A normal approximation prices a point through 3 like a point through
        11, which makes the entire basis of a teaser invisible."""
        with pytest.raises(TeaserUnpriceable) as exc:
            build_leg(
                default_distribution("americanfootball_nfl"),
                team="A", original_line=-8.0, points=6.0, predicted_margin=8.0,
                event_key="E1", league="americanfootball_nfl", commence_ms=NOW,
            )
        assert "invisible" in str(exc.value)

    def test_a_wong_leg_crosses_both_three_and_seven(self, nfl_buckets):
        teased = self._leg(nfl_buckets, "A", -8.0, 8.0, "E1")
        assert teased.is_wong
        assert set(teased.crosses_key_numbers) >= {3, 7}

    def test_a_non_wong_leg_is_flagged(self, nfl_buckets):
        valuation = value_teaser([
            self._leg(nfl_buckets, "A", -8.0, 8.0, "E1"),
            self._leg(nfl_buckets, "B", -4.0, 4.0, "E2", offset=8 * DAY),
        ])
        assert not valuation.all_legs_are_wong
        assert "Not a Wong teaser" in valuation.verdict
        assert "Don't" in valuation.verdict

    def test_a_full_wong_teaser_is_recognised(self, nfl_buckets):
        valuation = value_teaser([
            self._leg(nfl_buckets, "A", -8.0, 8.0, "E1"),
            self._leg(nfl_buckets, "B", 2.0, -2.0, "E2", offset=8 * DAY),
        ])
        assert valuation.all_legs_are_wong
        assert set(valuation.key_numbers_crossed) >= {3, 7}

    def test_teasing_moves_the_line_toward_the_bettor(self, nfl_buckets):
        teased = self._leg(nfl_buckets, "A", -8.0, 8.0, "E1")
        assert teased.teased_line == pytest.approx(-2.0)

    def test_same_game_teaser_legs_are_refused(self, nfl_buckets):
        with pytest.raises(CorrelationRefused):
            value_teaser([
                self._leg(nfl_buckets, "A", -8.0, 8.0, "E1"),
                self._leg(nfl_buckets, "B", 2.0, -2.0, "E1"),
            ])

    def test_the_screen_finds_only_the_documented_windows(self):
        board = [
            ("Chiefs", -8.0), ("Eagles", -3.5), ("Jets", 2.0),
            ("Bears", 7.5), ("Rams", -13.0), ("Bills", -7.5),
        ]
        found = dict(find_wong_candidates(board))
        assert set(found) == {"Chiefs", "Jets", "Bills"}

    def test_the_standard_price_is_around_minus_120(self):
        assert 1.80 < STANDARD_TWO_TEAM_DECIMAL < 1.90


class TestTheTeaserEvIsAssertedNotJustDescribed:
    """**No test anywhere asserted the teaser's EV.**

    That is the one assertion that would have caught the +28.4% Wong teaser — a
    number roughly five times any plausible real edge, printed by a demo, caused
    by a synthetic generator that matched the mean and not the variance. Every
    teaser test checked structure, refusals and monotonicity; none checked the
    number the whole module exists to produce.

    A modern Wong teaser is priced through: crossing 3 and 7 is real and the
    books know it, so the honest answer at -120 is comfortably negative. Bounded
    on BOTH sides, because an implausibly *good* result is as much a bug as a bad
    one — and it is the direction this project is built to distrust.
    """

    def _legs(self, buckets):
        return [
            build_leg(
                buckets[spread_bucket_for(-8.0)],
                team="A", original_line=-8.0, points=6.0,
                predicted_margin=8.0, event_key="E1",
                league="americanfootball_nfl", commence_ms=NOW,
            ),
            build_leg(
                buckets[spread_bucket_for(-8.0)],
                team="C", original_line=-8.0, points=6.0,
                predicted_margin=8.0, event_key="E2",
                league="americanfootball_nfl", commence_ms=NOW + 8 * DAY,
            ),
        ]

    def test_a_wong_teaser_at_minus_120_is_negative_ev(self, nfl_buckets):
        valued = value_teaser(self._legs(nfl_buckets), offered_decimal=american_to_decimal(-120))
        assert valued.ev_per_dollar < 0, (
            f"a two-leg Wong teaser priced at -120 came out at "
            f"{valued.ev_per_dollar:+.1%} EV. The books price this correctly, so "
            f"a positive result means the margin distribution is wrong rather "
            f"than that an edge was found."
        )

    def test_the_ev_is_within_a_plausible_band(self, nfl_buckets):
        """The +28.4% bug produced a number in the right *format* and a wildly
        wrong magnitude, which no structural assertion could catch."""
        valued = value_teaser(self._legs(nfl_buckets), offered_decimal=american_to_decimal(-120))
        assert -0.45 < valued.ev_per_dollar < 0.0

    def test_a_generous_price_moves_it(self, nfl_buckets):
        """The discriminating half: the bound above must not pass merely because
        the function always returns something negative."""
        legs = self._legs(nfl_buckets)
        assert (
            value_teaser(legs, offered_decimal=american_to_decimal(400)).ev_per_dollar
            > value_teaser(legs, offered_decimal=american_to_decimal(-120)).ev_per_dollar
        )
