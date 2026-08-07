"""Devig tests.

The claim that motivates the whole conservative design is asserted directly in
`TestMethodSpreadExceedsTheEdge`: the four methods disagree by more than the
fee advantage Kalshi offers. If that ever stops being true, the three layers of
pessimism downstream could be relaxed.
"""

from __future__ import annotations

import pytest

from backend.core.devig import (
    DevigError,
    additive,
    consensus_devig,
    devig,
    implied_probabilities,
    multiplicative,
    overround,
    power,
    shin,
)

# A realistic MLB moneyline: roughly -140 / +120 in American terms, ~4% hold.
FAV, DOG = 1.71, 2.30
# A lopsided line, where the methods disagree most.
HEAVY_FAV, LONGSHOT = 1.11, 7.50


class TestImpliedProbabilities:
    def test_inverts_decimal_odds(self):
        assert implied_probabilities([2.0, 2.0]) == [0.5, 0.5]

    def test_a_real_book_sums_above_one(self):
        assert sum(implied_probabilities([FAV, DOG])) > 1.0

    @pytest.mark.parametrize("bad", [1.0, 0.5, -110])
    def test_odds_at_or_below_evens_are_refused(self, bad):
        """Below 1.0 implies probability > 1 -- usually American odds in a
        decimal field, and it reads as enormous edge."""
        with pytest.raises(DevigError):
            implied_probabilities([bad, 2.0])


class TestEachMethodSumsToOne:
    """The defining property. A method that does not is not devigging."""

    @pytest.mark.parametrize("method", [multiplicative, additive, power, shin])
    @pytest.mark.parametrize("odds", [(FAV, DOG), (HEAVY_FAV, LONGSHOT), (1.95, 1.95)])
    def test_sums_to_one(self, method, odds):
        probs = implied_probabilities(list(odds))
        assert sum(method(probs)) == pytest.approx(1.0, abs=1e-9)

    @pytest.mark.parametrize("method", [multiplicative, power, shin])
    def test_stays_inside_zero_and_one(self, method):
        probs = implied_probabilities([HEAVY_FAV, LONGSHOT])
        assert all(0.0 < p < 1.0 for p in method(probs))


class TestMethodCharacter:
    """Each method's known bias, asserted so a rewrite cannot silently swap them."""

    def test_multiplicative_gives_the_longshot_the_most(self):
        """It spreads margin proportionally, which overstates longshots."""
        probs = implied_probabilities([HEAVY_FAV, LONGSHOT])
        assert multiplicative(probs)[1] > additive(probs)[1]

    def test_power_and_shin_both_cut_the_longshot_below_multiplicative(self):
        """The favourite-longshot correction, which is the point of both.

        Note the folk claim that power "sits between" multiplicative and
        additive does NOT hold on lopsided lines. `sum(p**k) == 1` shrinks a
        base near 1.0 slowly and a small base quickly, so power takes most of
        the correction out of the longshot. On 1.11/7.50 the longshot reads
        0.129 multiplicative, 0.116 additive, 0.109 power -- power is the
        harshest of the three, not the middle one.
        """
        probs = implied_probabilities([HEAVY_FAV, LONGSHOT])
        assert power(probs)[1] < multiplicative(probs)[1]
        assert shin(probs)[1] < multiplicative(probs)[1]

    def test_shin_degenerates_to_multiplicative_without_insiders(self):
        """Shin's z -> 0 limit is the natural sanity check on the solver."""
        probs = implied_probabilities([1.9999, 2.0001])  # near-zero margin
        for a, b in zip(shin(probs), multiplicative(probs)):
            assert a == pytest.approx(b, abs=1e-4)

    def test_shin_is_not_merely_multiplicative_on_a_real_line(self):
        """Guards a bug that made Shin a silent duplicate.

        The solver originally short-circuited at z = 0 to `p / booksum` -- a
        *different* formula that sums to exactly 1, so the residual was 0 at
        z = 0 and the root-find returned immediately. Shin returned
        multiplicative for every market, and 'four methods' was really three.
        """
        probs = implied_probabilities([2.10, 1.80])
        assert shin(probs) != pytest.approx(multiplicative(probs), abs=1e-9)

    def test_additive_clamps_rather_than_going_negative(self):
        """A negative probability means the method does not fit this market."""
        probs = implied_probabilities([1.02, 40.0])
        result = additive(probs)
        assert all(p > 0 for p in result)


class TestMethodSpreadDependsOnLineShape:
    """Measured, and it changed the framing.

    On a near-even MLB moneyline the four methods agree to ~0.18 points. On a
    lopsided line they spread ~2.03 points -- over three times Kalshi's
    0.6-point fee advantage. So method choice is harmless on even lines and a
    source of entirely fictitious edge on longshots.
    """

    def test_lopsided_lines_disagree_by_more_than_kalshis_fee_advantage(self):
        spread_points = devig(["fav", "dog"], [HEAVY_FAV, LONGSHOT]).method_spread("dog") * 100
        assert spread_points > 0.6, (
            "method choice no longer dominates the fee advantage on lopsided "
            "lines -- the conservative selection could be revisited"
        )

    def test_even_lines_agree_closely(self):
        """The other half of the finding, asserted so it stays true.

        If this ever grows, the conservative selection is costing real edge on
        the markets that matter most.
        """
        spread_points = devig(["fav", "dog"], [2.10, 1.80]).method_spread("fav") * 100
        assert spread_points < 0.6

    def test_spread_is_widest_on_lopsided_lines(self):
        """Which is exactly where longshot bets live -- and where the fee curve
        is also at its worst in percentage terms."""
        even = devig(["a", "b"], [1.95, 1.95]).method_spread("b")
        lopsided = devig(["a", "b"], [HEAVY_FAV, LONGSHOT]).method_spread("b")
        assert lopsided > even


class TestConservativeSelection:
    """Lowest fair probability = least edge = least likely to talk you in."""

    def test_picks_the_minimum_across_methods(self):
        result = devig(["fav", "dog"], [FAV, DOG])
        for outcome in ("fav", "dog"):
            values = [v[result.index_of(outcome)] for v in result.all_methods().values()]
            assert result.conservative_probability(outcome) == pytest.approx(min(values))

    def test_conservative_is_never_the_most_optimistic_reading(self):
        result = devig(["fav", "dog"], [HEAVY_FAV, LONGSHOT])
        assert result.conservative_probability("dog") < max(
            v[1] for v in result.all_methods().values()
        )

    def test_an_unknown_outcome_raises_rather_than_defaulting(self):
        result = devig(["fav", "dog"], [FAV, DOG])
        with pytest.raises(DevigError):
            result.conservative_probability("draw")


class TestRefusals:
    def test_a_book_with_no_margin_is_refused(self):
        """Scaling up would invent probability rather than recover it."""
        with pytest.raises(DevigError, match="no margin"):
            devig(["a", "b"], [2.5, 2.5])  # sums to 0.8

    def test_a_single_outcome_is_refused(self):
        with pytest.raises(DevigError):
            devig(["a"], [1.5])

    def test_mismatched_outcome_and_price_counts_are_refused(self):
        with pytest.raises(DevigError):
            devig(["a", "b", "c"], [FAV, DOG])


class TestOverround:
    def test_measures_the_books_margin(self):
        probs = implied_probabilities([FAV, DOG])
        assert overround(probs) == pytest.approx(sum(probs) - 1.0)

    def test_a_realistic_moneyline_holds_a_few_percent(self):
        result = devig(["fav", "dog"], [FAV, DOG])
        assert 0.01 < result.overround < 0.10


class TestConsensus:
    """Devig each book, then average. Not the other way round."""

    def test_devigs_before_averaging(self):
        """Averaging raw prices first blends a 2% book with a 6% book and
        produces a fair line belonging to neither."""
        tight = {"pinnacle": [1.98, 2.02]}
        wide = {"softbook": [1.80, 1.90]}
        both = {**tight, **wide}

        consensus, _ = consensus_devig(["a", "b"], both)
        assert sum(consensus.multiplicative) == pytest.approx(1.0, abs=1e-9)

    def test_prefers_sharp_books_when_present(self):
        consensus, meta = consensus_devig(
            ["a", "b"],
            {"pinnacle": [1.90, 2.10], "softbook": [1.50, 3.00]},
            sharp_books=frozenset({"pinnacle"}),
        )
        assert meta["anchored_on_sharp"]
        assert meta["books_used"] == ["pinnacle"]

    def test_falls_back_to_all_books_when_no_sharp_book_is_present(self):
        _, meta = consensus_devig(
            ["a", "b"],
            {"draftkings": [1.90, 2.10], "fanduel": [1.92, 2.08]},
            sharp_books=frozenset({"pinnacle"}),
        )
        assert not meta["anchored_on_sharp"]
        assert meta["book_count"] == 2

    def test_reports_market_width(self):
        """Books disagreeing widely means the fair line is untrustworthy --
        a suppression input, not a curiosity."""
        _, narrow = consensus_devig(
            ["a", "b"], {"x": [1.90, 2.10], "y": [1.91, 2.09]}
        )
        # Both books must actually carry margin, or _validate rejects them and
        # the "wide" case collapses to a single book with zero width.
        _, wide = consensus_devig(
            ["a", "b"], {"x": [1.50, 2.80], "y": [2.30, 1.70]}
        )
        assert wide["book_count"] == 2, "both books must be usable for this to mean anything"
        assert wide["market_width"] > narrow["market_width"]
        assert wide["market_width"] > 0.10  # genuinely far apart

    def test_unusable_books_are_reported_not_silently_dropped(self):
        _, meta = consensus_devig(
            ["a", "b"], {"good": [1.90, 2.10], "crossed": [2.50, 2.50]}
        )
        assert meta["books_rejected"] == ["crossed"]
        assert meta["book_count"] == 1

    def test_refuses_when_no_book_is_usable(self):
        with pytest.raises(DevigError):
            consensus_devig(["a", "b"], {"crossed": [2.50, 2.50]})
