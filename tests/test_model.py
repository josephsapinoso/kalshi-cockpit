"""Quant tests.

The claim this module has to keep honest is that the model is a *disagreement
detector*, not an oracle. So the tests that matter most are the ones asserting
it refuses to claim an edge it has not demonstrated — `TestVerdicts`.
"""

from __future__ import annotations

import math
import random

import pytest

from backend.model.backtest import (
    BacktestGame,
    PairedComparison,
    backtest,
    brier,
    calibration_error,
    calibration_split,
    fit_calibrator_on_holdout,
    walk_forward,
)
from backend.core.correlation import (
    CorrelationUnreachable,
    Leg,
    equicorrelated_joint,
    equicorrelation_floor,
    implied_correlation,
)
from backend.model.elo import (
    DEFAULT_RATING,
    EloModel,
    GameResult,
    LeagueConfig,
    PlattCalibrator,
)
from backend.model.margins import (
    KEY_NUMBERS,
    MAX_TRANSLATION_POINTS,
    MIN_GAMES_FOR_EMPIRICAL,
    MIN_GAMES_FOR_SD,
    PUBLISHED_SD,
    PUBLISHED_TOTAL_SD,
    MarginDistribution,
    _normal_survival,
    default_distribution,
    fit_by_spread,
    spread_bucket_for,
    wong_candidate,
)
from backend.model.synthetic import (
    NFL_MARGIN_SD,
    synthetic_bucket_observations,
    synthetic_margins,
)


def game(home="A", away="B", hs=24, as_=17, **kw):
    return GameResult(
        home_team=home, away_team=away, home_score=hs, away_score=as_,
        played_ms=0, **kw,
    )


@pytest.fixture
def nfl():
    return EloModel(config=LeagueConfig.for_league("americanfootball_nfl"))


class TestRatings:
    def test_unseen_teams_start_at_the_default(self, nfl):
        assert nfl.rating("Nobody") == DEFAULT_RATING

    def test_a_win_raises_the_winner_and_lowers_the_loser(self, nfl):
        nfl.update(game())
        assert nfl.rating("A") > DEFAULT_RATING
        assert nfl.rating("B") < DEFAULT_RATING

    def test_rating_changes_are_zero_sum(self, nfl):
        home_delta, away_delta = nfl.update(game())
        assert home_delta == pytest.approx(-away_delta)

    def test_home_advantage_favours_the_home_side(self, nfl):
        assert nfl.expected_home_win(game()) > 0.5

    def test_beating_a_stronger_team_moves_the_rating_more(self):
        weak = EloModel(config=LeagueConfig.for_league("baseball_mlb"))
        weak.ratings["Strong"] = 1800.0
        weak.ratings["Average"] = 1500.0

        upset, _ = weak.update(game(home="Underdog", away="Strong", hs=5, as_=4))
        expected, _ = weak.update(game(home="Underdog", away="Average", hs=5, as_=4))
        assert upset > expected

    def test_confidence_counts_games_seen(self, nfl):
        for _ in range(3):
            nfl.update(game())
        assert nfl.confidence("A") == 3
        assert nfl.confidence("Never played") == 0


class TestAdjustments:
    def test_extra_rest_helps_the_rested_side(self, nfl):
        rested = nfl.expected_home_win(game(home_rest_days=10, away_rest_days=6))
        level = nfl.expected_home_win(game(home_rest_days=6, away_rest_days=6))
        assert rested > level

    def test_travel_penalises_the_visitor(self, nfl):
        far = nfl.expected_home_win(game(away_travel_km=4000))
        near = nfl.expected_home_win(game(away_travel_km=100))
        assert far > near

    def test_adjustments_are_inspectable_separately(self, nfl):
        """So an adjustment carrying no signal can be removed rather than left
        quietly producing a number."""
        home, away = nfl.effective_ratings(game())
        assert home == pytest.approx(DEFAULT_RATING + nfl.config.home_advantage)
        assert away == pytest.approx(DEFAULT_RATING)


class TestLeagueConfigs:
    def test_baseball_uses_a_much_smaller_k_than_football(self):
        """One of 162 games says far less than one of 17."""
        mlb = LeagueConfig.for_league("baseball_mlb")
        nfl = LeagueConfig.for_league("americanfootball_nfl")
        assert mlb.k_factor < nfl.k_factor / 3

    def test_baseball_ignores_margin_of_victory(self):
        """An 11-run blowout says almost nothing more than a 2-run win."""
        assert not LeagueConfig.for_league("baseball_mlb").use_margin_of_victory

    def test_college_football_regresses_hardest(self):
        """Wildly uneven schedules make its ratings least stable."""
        ncaaf = LeagueConfig.for_league("americanfootball_ncaaf")
        nfl = LeagueConfig.for_league("americanfootball_nfl")
        assert ncaaf.season_regression > nfl.season_regression

    def test_an_unknown_league_gets_defaults_not_an_error(self):
        assert LeagueConfig.for_league("underwater_basketweaving").k_factor > 0


class TestSeasonRegression:
    def test_ratings_move_toward_the_mean(self, nfl):
        nfl.ratings["Strong"] = 1800.0
        nfl.ratings["Weak"] = 1200.0
        nfl.regress_to_mean()
        assert 1500 < nfl.rating("Strong") < 1800
        assert 1200 < nfl.rating("Weak") < 1500

    def test_a_new_season_triggers_regression(self, nfl):
        nfl.update(game(season="2025"))
        before = nfl.rating("A")
        nfl.update(game(season="2026", hs=0, as_=0))
        assert nfl.rating("A") != before


class TestMarginOfVictoryDamping:
    def test_blowouts_by_heavy_favourites_are_damped(self, nfl):
        """Without damping a good team beating a bad one badly inflates its
        rating without limit, because blowouts are MORE likely when the gap is
        already large."""
        nfl.ratings["Great"] = 1900.0
        nfl.ratings["Awful"] = 1100.0
        favoured, _ = nfl.update(game(home="Great", away="Awful", hs=45, as_=0))

        even = EloModel(config=LeagueConfig.for_league("americanfootball_nfl"))
        level, _ = even.update(game(home="X", away="Y", hs=45, as_=0))

        assert favoured < level


class TestCalibration:
    def test_refuses_to_fit_on_a_tiny_sample(self):
        """Two parameters on a handful of games is a calibrator made of noise —
        and unlike an uncalibrated model it LOOKS principled."""
        calibrator = PlattCalibrator().fit([0.6] * 10, [True] * 10)
        assert calibrator.fitted_on == 0
        assert calibrator.a == 1.0

    def test_corrects_a_systematically_overconfident_model(self):
        rng = random.Random(4)
        predictions, outcomes = [], []
        for _ in range(400):
            true_p = rng.uniform(0.35, 0.65)
            # Overconfident: pushed away from 0.5.
            predictions.append(min(0.99, max(0.01, 0.5 + (true_p - 0.5) * 2.2)))
            outcomes.append(rng.random() < true_p)

        calibrator = PlattCalibrator().fit(predictions, outcomes)
        assert calibrator.fitted_on == 400
        # Shrinking the logit slope is exactly what fixes overconfidence.
        assert calibrator.a < 1.0

    def test_calibration_is_monotone(self):
        calibrator = PlattCalibrator(a=0.8, b=0.1)
        values = [calibrator.calibrate(p) for p in (0.1, 0.3, 0.5, 0.7, 0.9)]
        assert values == sorted(values)


class TestScoring:
    def test_brier_rewards_confident_correct_predictions(self):
        assert brier([0.9], [True]) < brier([0.6], [True])

    def test_brier_punishes_confident_wrong_predictions(self):
        assert brier([0.9], [False]) > brier([0.6], [False])

    def test_calibration_error_ignores_thin_bins(self):
        """A bin of three games contributes noise, not information."""
        predictions = [0.5] * 50 + [0.95] * 3
        outcomes = [True] * 25 + [False] * 25 + [False] * 3
        assert calibration_error(predictions, outcomes) < 0.05


class TestWalkForward:
    def test_predictions_use_only_prior_games(self):
        """Training on the full history then scoring it produces a model that
        has seen the outcomes it predicts. It looks excellent and is worthless.
        """
        model = EloModel(config=LeagueConfig.for_league("baseball_mlb"))
        games = [game(home="A", away="B", hs=5, as_=3) for _ in range(150)]
        results = walk_forward(games, model, burn_in=100)

        assert len(results) == 50
        # A has been winning throughout, so later predictions must be higher
        # than earlier ones -- proof the model learned as it went.
        assert results[-1].model_probability > results[0].model_probability

    def test_burn_in_discards_the_default_rating_period(self):
        model = EloModel(config=LeagueConfig.for_league("baseball_mlb"))
        games = [game() for _ in range(120)]
        assert len(walk_forward(games, model, burn_in=100)) == 20


class TestVerdicts:
    """The model must refuse to claim an edge it has not demonstrated."""

    def _games(self, n, model_p, market_p, home_wins_rate, seed=1):
        rng = random.Random(seed)
        return [
            BacktestGame(
                game=game(hs=1 if rng.random() < home_wins_rate else 0, as_=0),
                model_probability=model_p,
                closing_probability=market_p,
            )
            for _ in range(n)
        ]

    def test_a_small_backtest_gets_no_verdict(self):
        result = backtest(self._games(50, 0.6, 0.55, 0.6), min_games=200)
        assert "below the 200 minimum" in result.verdict

    def test_a_model_that_never_disagrees_has_produced_nothing(self):
        """Matching Vegas at 68% is not an edge."""
        result = backtest(self._games(300, 0.68, 0.68, 0.68), min_games=200)
        assert result.n_disagreements == 0
        assert "already knows" in result.verdict

    def test_a_marginal_gap_is_reported_as_noise(self):
        rng = random.Random(9)
        games = [
            BacktestGame(
                game=game(hs=1 if rng.random() < 0.55 else 0, as_=0),
                model_probability=0.60,
                closing_probability=0.55,
            )
            for _ in range(250)
        ]
        result = backtest(games, min_games=200)
        assert "noise band" in result.verdict
        assert "research flag only" in result.verdict

    def test_a_model_worse_than_the_close_is_told_not_to_size(self):
        games = [
            BacktestGame(
                game=game(hs=0, as_=1),          # home always loses
                model_probability=0.75,           # model always says home
                closing_probability=0.30,         # market says away
            )
            for _ in range(250)
        ]
        result = backtest(games, min_games=200)
        assert result.beats_close is False
        assert "should not influence sizing" in result.verdict

    def test_the_disagreement_threshold_excludes_devig_noise(self):
        """Below ~3 points the difference is inside the spread between devig
        methods, so it says nothing about the game."""
        games = self._games(250, 0.56, 0.55, 0.55)
        assert backtest(games, min_disagreement=0.03, min_games=200).n_disagreements == 0


class TestBeatsCloseAgreesWithItsOwnVerdict:
    """`beats_close` used to be `model_accuracy > market_accuracy`, bare.

    It sat in the same dataclass as a verdict that correctly reported "inside
    the noise band, no demonstrated edge". Two paths from the same inputs, and
    the boolean is the one a caller branches on. This is
    `tasks/lessons.md`, 2026-08-07, in Python instead of SQL.
    """

    def _games(self, n, model_p, market_p, home_wins_rate, seed=1):
        rng = random.Random(seed)
        return [
            BacktestGame(
                game=game(hs=1 if rng.random() < home_wins_rate else 0, as_=0),
                model_probability=model_p,
                closing_probability=market_p,
            )
            for _ in range(n)
        ]

    @pytest.mark.parametrize("seed", range(12))
    def test_the_boolean_and_the_prose_never_disagree(self, seed):
        """The invariant. `True` if and only if the verdict claims an edge.

        Swept across seeds because the failure was data-dependent: the old code
        and the verdict agreed whenever the gap happened to be large, and
        diverged exactly on the marginal cases that matter.
        """
        result = backtest(
            self._games(250, 0.62, 0.55, 0.58, seed=seed), min_games=200
        )
        claims_edge = "Worth confirming on a held-out season" in result.verdict
        assert result.beats_close is claims_edge, (
            f"beats_close={result.beats_close} but verdict says: {result.verdict}"
        )

    def test_a_positive_gap_inside_the_noise_band_is_not_beating_the_close(self):
        """The specific case the old boolean got wrong.

        Built to an exact tally rather than by sampling, so the arithmetic is
        checkable: 55 games the model called right and the market called wrong,
        45 the reverse, 150 they agreed on. Gap is +4.0 points and the band is
        ±8.0, so the model is nominally ahead and cannot be shown to be.

        `model_accuracy > market_accuracy` is True here. That was the old
        implementation, sitting beside a verdict reading "No demonstrated edge".
        """
        games = []
        # Discordant: model says home (0.60), market says away (0.45).
        games += [
            BacktestGame(game=game(hs=1, as_=0), model_probability=0.60,
                         closing_probability=0.45)
            for _ in range(55)                       # model right, market wrong
        ]
        games += [
            BacktestGame(game=game(hs=0, as_=1), model_probability=0.60,
                         closing_probability=0.45)
            for _ in range(45)                       # market right, model wrong
        ]
        # Concordant: both say home, and the disagreement still clears 0.03 so
        # these stay in the comparison.
        games += [
            BacktestGame(game=game(hs=i % 2, as_=1 - i % 2), model_probability=0.60,
                         closing_probability=0.52)
            for i in range(150)
        ]

        result = backtest(games, min_games=200)
        assert result.comparison is not None
        assert result.n_disagreements == 250
        assert (result.comparison.model_right_market_wrong,
                result.comparison.market_right_model_wrong) == (55, 45)

        assert result.comparison.model_accuracy > result.comparison.market_accuracy, (
            "the old implementation returned True on exactly this"
        )
        assert result.gap_points == pytest.approx(4.0)
        assert result.noise_band_points == pytest.approx(8.0)
        assert not result.comparison.distinguishable
        assert result.beats_close is False
        assert "No demonstrated edge" in result.verdict

    def test_no_verdict_means_no_boolean_either(self):
        """Below `min_games` the verdict declines to rule, so the flag must too.

        The old code computed `beats_close` regardless, so a 50-game backtest
        could report True beside a verdict saying "No verdict".
        """
        result = backtest(self._games(50, 0.75, 0.40, 0.9), min_games=200)
        assert "No verdict" in result.verdict
        assert result.beats_close is None

    def test_the_numbers_behind_the_verdict_are_exposed(self):
        """A boolean a reader cannot check is a boolean they must trust."""
        result = backtest(self._games(250, 0.62, 0.55, 0.58), min_games=200)
        assert result.gap_points is not None
        assert result.noise_band_points is not None
        assert f"{result.noise_band_points:.1f}" in result.verdict


class TestThePairedComparisonUsesMcNemar:
    """`sqrt(0.25/n)` is the null for ONE proportion, not for a difference.

    Model and market are scored on the *same* games. Games where both were right
    or both were wrong say nothing about which is better; only discordant pairs
    do. The two formulas coincide at 25% discordance, and above it the old one
    is too narrow — the direction that manufactures significance.
    """

    def _paired(self, b, c, both_right, both_wrong):
        """Build a comparison with an exactly specified discordance."""
        return PairedComparison(
            n=b + c + both_right + both_wrong,
            model_right_market_wrong=b,
            market_right_model_wrong=c,
            model_accuracy=(b + both_right) / (b + c + both_right + both_wrong),
            market_accuracy=(c + both_right) / (b + c + both_right + both_wrong),
        )

    def test_the_two_formulas_coincide_at_25_percent_discordance(self):
        """The definitional crossover, where the old code was exactly right."""
        n = 400
        comparison = self._paired(b=50, c=50, both_right=150, both_wrong=150)
        assert comparison.discordant / n == pytest.approx(0.25)

        old = 100 * math.sqrt(0.25 / n)
        assert comparison.stderr_points == pytest.approx(old, rel=1e-12)

    def test_the_old_formula_is_too_narrow_above_25_percent(self):
        """Near-pick'em games push discordance well past 25%."""
        n = 400
        comparison = self._paired(b=120, c=120, both_right=80, both_wrong=80)
        assert comparison.discordant / n == pytest.approx(0.60)

        old = 100 * math.sqrt(0.25 / n)
        assert comparison.stderr_points > old
        # sqrt(0.60)/sqrt(0.25) = 1.55x wider.
        assert comparison.stderr_points / old == pytest.approx(1.549, abs=0.01)

    def test_the_old_formula_is_too_wide_below_25_percent(self):
        """Stated for completeness: the error is not conservative in general."""
        n = 400
        comparison = self._paired(b=20, c=20, both_right=180, both_wrong=180)
        assert comparison.stderr_points < 100 * math.sqrt(0.25 / n)

    def test_perfect_agreement_leaves_no_gap_to_test(self):
        """Zero discordant pairs means zero gap. Both sides must be zero."""
        comparison = self._paired(b=0, c=0, both_right=200, both_wrong=100)
        assert comparison.gap_points == pytest.approx(0.0)
        assert comparison.stderr_points == pytest.approx(0.0)
        assert not comparison.distinguishable

    def test_the_gap_is_the_discordant_difference_over_n(self):
        """Definitional: accuracy difference reduces to (b - c)/n exactly."""
        comparison = self._paired(b=90, c=40, both_right=120, both_wrong=150)
        assert comparison.gap_points == pytest.approx(
            100.0 * (90 - 40) / comparison.n
        )


class TestMargins:
    def test_football_key_numbers_are_three_and_seven(self):
        assert 3 in KEY_NUMBERS["americanfootball_nfl"]
        assert 7 in KEY_NUMBERS["americanfootball_nfl"]

    def test_baseball_has_no_key_numbers(self):
        assert "baseball_mlb" not in KEY_NUMBERS

    def test_a_thin_sample_falls_back_to_smooth_and_says_so(self):
        distribution = MarginDistribution("americanfootball_nfl").fit([3, 7, 3, 10])
        assert not distribution.is_empirical


class TestAThinSampleCannotManufactureCertainty:
    """The width must not be estimated from a sample too thin to estimate it.

    `is_empirical` routes thin data away from the counts path and into a normal
    approximation. If `fit` has already overwritten `sd` from that same thin
    sample, the guard routes around bad data into a fallback built from the bad
    data. At `n = 1` the old denominator `max(1, n - 1)` gave variance 0, so
    `sd = 0`, so a cover probability of exactly 1.0 — and quarter-Kelly on a
    certainty stakes the entire bankroll off one game.
    """

    def test_a_single_observation_does_not_produce_a_zero_width(self):
        """The specific input that produced a certainty."""
        distribution = MarginDistribution("americanfootball_nfl").fit([7])
        assert distribution.n == 1
        assert distribution.sd > 0
        assert not distribution.sd_is_measured
        assert distribution.sd == pytest.approx(PUBLISHED_SD["americanfootball_nfl"])

    def test_a_single_observation_does_not_produce_a_certainty(self):
        """The consequence, asserted separately from the cause.

        Under the old code this returned exactly 1.0 for any line the single
        observation cleared, and exactly 0.0 for any it did not.
        """
        distribution = MarginDistribution("americanfootball_nfl").fit([7])
        for line in (-21.5, -7.5, -0.5, 0.0, 3.5, 14.5):
            p = distribution.probability_cover(line, predicted_margin=7.0)
            assert 0.0 < p < 1.0, f"line {line} produced the certainty {p}"

    def test_the_width_is_measured_once_the_sample_can_support_it(self):
        """The guard must not be so blunt that it never lets real data speak."""
        rng = random.Random(5)
        margins = [round(rng.gauss(0.0, 13.0)) for _ in range(MIN_GAMES_FOR_SD * 4)]
        distribution = MarginDistribution("americanfootball_nfl").fit(margins)

        assert distribution.sd_is_measured
        assert distribution.sd == pytest.approx(13.0, abs=2.0)
        assert distribution.sd != pytest.approx(
            PUBLISHED_SD["americanfootball_nfl"], abs=1e-9
        ), "a measured width must not coincidentally be the published one"

    def test_a_degenerate_sample_keeps_the_published_width(self):
        """300 identical margins is a large sample and still zero spread.

        Sample size alone is not the guard -- `n >= MIN_GAMES_FOR_SD` passes
        here and the estimate is still 0.
        """
        distribution = MarginDistribution("americanfootball_nfl").fit([8] * 300)
        assert distribution.n == 300
        assert distribution.sd > 0
        assert not distribution.sd_is_measured

    def test_a_zero_width_distribution_cannot_be_constructed(self):
        """The backstop, independent of `fit`."""
        with pytest.raises(ValueError, match="must be positive"):
            MarginDistribution("americanfootball_nfl", sd=0.0)
        with pytest.raises(ValueError, match="must be positive"):
            MarginDistribution("americanfootball_nfl", sd=-1.0)

    def test_normal_survival_refuses_a_zero_width_rather_than_returning_one(self):
        """It used to return 1.0 or 0.0 here, which reads as defensive and is not.

        A certainty is the most dangerous number this module can emit, and the
        caller cannot tell a real one from a degenerate fit.
        """
        with pytest.raises(ValueError, match="positive width"):
            _normal_survival(0.0, mu=5.0, sigma=0.0)

    def test_every_spread_bucket_gets_a_usable_width(self, caplog):
        """`fit_by_spread` fits tiny buckets, which is where this originated.

        The thin buckets stay -- their absence would hide the coverage gap --
        but none of them may carry a zero width.
        """
        rng = random.Random(7)
        observations = [(-8.0, 8 + rng.choice([3, -3, 7, -7, 0])) for _ in range(400)]
        observations.append((-2.0, 5))          # a one-game bucket
        observations.extend([(+3.0, -1), (+3.0, 4)])   # a two-game bucket

        fitted = fit_by_spread("americanfootball_nfl", observations)

        assert any(d.n < MIN_GAMES_FOR_SD for d in fitted.values()), (
            "the thin buckets must survive, or this test proves nothing"
        )
        for bucket, distribution in fitted.items():
            assert distribution.sd > 0, f"bucket {bucket:+g} has zero width"
            p = distribution.probability_cover(-3.5, predicted_margin=4.0)
            assert 0.0 < p < 1.0, f"bucket {bucket:+g} produced the certainty {p}"

    def test_a_measured_width_is_distinguishable_from_a_published_one(self):
        """`sd_is_measured` exists for the same reason `is_empirical` does.

        A consumer must be able to tell a number that came from data from one
        that came from a source, without inspecting `n`.
        """
        assert not default_distribution("baseball_mlb").sd_is_measured
        rng = random.Random(9)
        fitted = MarginDistribution("baseball_mlb").fit(
            [round(rng.gauss(0.0, 3.0)) for _ in range(200)]
        )
        assert fitted.sd_is_measured

    def test_an_empirical_fit_preserves_the_key_number_spikes(self):
        """A normal approximation smooths these away and makes the one
        documented book-side edge invisible."""
        rng = random.Random(3)
        margins = []
        for _ in range(MIN_GAMES_FOR_EMPIRICAL * 3):
            # Deliberately lumpy, like real football.
            margins.append(rng.choice([3, 3, 3, 7, 7, 10, 14, 1, 4, 6, 17, 21]))

        distribution = MarginDistribution("americanfootball_nfl").fit(margins)
        assert distribution.is_empirical
        mass = distribution.key_number_mass()
        assert mass[3] > mass[14], "3 should carry more mass than 14"

    def test_cover_probability_rises_as_the_line_rises(self):
        """Receiving points is easier than laying them.

        This test previously asserted the opposite, matching a `margin > line`
        comparison in the module. Both were wrong in the same direction, so the
        suite passed while every spread price was inverted.
        """
        distribution = default_distribution("americanfootball_nfl")
        laying = distribution.probability_cover(-7.5, predicted_margin=0.0)
        receiving = distribution.probability_cover(+7.5, predicted_margin=0.0)
        assert receiving > laying

    def test_an_even_line_on_an_even_game_is_a_coin_flip(self):
        """Anchors the sign convention to a value with only one right answer."""
        distribution = default_distribution("americanfootball_nfl")
        assert distribution.probability_cover(0.0, predicted_margin=0.0) == pytest.approx(0.5)

    def test_a_favourite_covers_its_own_line_about_half_the_time(self):
        """A -7.5 line predicting a 7.5-point win is, by construction, even."""
        distribution = default_distribution("americanfootball_nfl")
        assert distribution.probability_cover(
            -7.5, predicted_margin=7.5
        ) == pytest.approx(0.5)

    def test_a_league_wide_fit_reports_how_far_it_would_be_dragged(self):
        """The number that separates a usable empirical fit from a decorative one."""
        rng = random.Random(11)
        distribution = MarginDistribution("americanfootball_nfl").fit(
            [rng.choice([3, -3, 7, -7, 10, -10, 1, -1]) for _ in range(600)]
        )
        assert distribution.translation_points(8.0) > MAX_TRANSLATION_POINTS

    def test_a_bucketed_fit_is_barely_dragged_at_all(self):
        rng = random.Random(12)
        observations = [
            (-8.0, 8 + rng.choice([3, -3, 7, -7, 0, 4, -4]))
            for _ in range(600)
        ]
        buckets = fit_by_spread("americanfootball_nfl", observations)
        distribution = buckets[-8.0]
        assert distribution.is_empirical
        assert distribution.translation_points(8.0) <= MAX_TRANSLATION_POINTS

    def test_signed_margins_survive_the_fit(self):
        """Storing only absolute margins forces a symmetry that is false for
        any set of favourites -- which is exactly what a teaser is priced on."""
        distribution = MarginDistribution("americanfootball_nfl").fit([8] * 300)
        assert distribution.mean == pytest.approx(8.0)
        assert distribution.probability_cover(-3.5, predicted_margin=8.0) == 1.0
        assert distribution.probability_cover(-10.5, predicted_margin=8.0) == 0.0

    def test_default_distributions_are_flagged_as_not_empirical(self):
        """So no consumer mistakes a published standard deviation for data."""
        assert not default_distribution("americanfootball_nfl").is_empirical


class TestSyntheticMargins:
    """Guards on the generator, because a generator that is wrong in a
    plausible direction manufactures edges in everything downstream."""

    def test_the_mean_lands_on_the_spread(self):
        margins = synthetic_margins(-8.0, 2000, seed=1)
        assert sum(margins) / len(margins) == pytest.approx(8.0, abs=1.0)

    def test_the_spread_of_outcomes_is_realistic_too(self):
        """The bug this module was written for: an earlier generator hit the
        mean exactly while making an eight-point favourite win 96% of games,
        which fabricated a +28% Wong teaser out of nothing."""
        margins = synthetic_margins(-8.0, 2000, seed=2)
        mean = sum(margins) / len(margins)
        sd = math.sqrt(sum((m - mean) ** 2 for m in margins) / (len(margins) - 1))
        assert sd == pytest.approx(NFL_MARGIN_SD, abs=1.5)

    def test_an_eight_point_favourite_wins_about_three_quarters(self):
        """The single number that catches a wrong variance."""
        margins = synthetic_margins(-8.0, 2000, seed=3)
        win_rate = sum(1 for m in margins if m > 0) / len(margins)
        assert 0.68 < win_rate < 0.80

    def test_key_numbers_carry_more_mass_than_their_neighbours(self):
        distribution = MarginDistribution("americanfootball_nfl").fit(
            synthetic_margins(-3.0, 4000, seed=4)
        )
        for key in (3, 7):
            assert (
                distribution.probability_of_exact_margin(key)
                > distribution.probability_of_exact_margin(key + 2)
            ), f"{key} should outweigh {key + 2}"

    def test_no_game_ends_level(self):
        assert 0 not in synthetic_margins(-3.0, 2000, seed=5)

    def test_bucket_observations_fit_without_drag(self):
        buckets = fit_by_spread(
            "americanfootball_nfl",
            synthetic_bucket_observations([-8.0, 2.0], n_per_bucket=1200),
        )
        for spread in (-8.0, 2.0):
            distribution = buckets[spread_bucket_for(spread)]
            assert distribution.is_empirical
            assert distribution.translation_points(-spread) <= MAX_TRANSLATION_POINTS


class TestWongTeasers:
    """The two windows that cross both 7 and 3 on a 6-point teaser."""

    @pytest.mark.parametrize("line", [-7.5, -8.0, -8.5, 1.5, 2.0, 2.5])
    def test_the_classic_windows_qualify(self, line):
        assert wong_candidate(line)

    @pytest.mark.parametrize("line", [-3.5, -10.5, -6.5, 0.5, 3.5, 7.5])
    def test_lines_outside_the_windows_do_not(self, line):
        assert not wong_candidate(line)

    def test_only_six_point_teasers_qualify(self):
        """Everything else is an ordinary teaser, which is a bad bet dressed
        up as a strategy."""
        assert not wong_candidate(-8.0, points=10.0)


class TestPushesAreRefundsNotLosses:
    """On an integer line the margin can land exactly on it and the stake is
    returned. Counting those as losses understates cover probability by the
    whole key-number mass — ~15% at 3 and ~9% at 7 in the NFL, the two lines
    this module exists to model.

    Measured on an NFL-shaped fit: cover on a -3 line went from 0.3190 to
    0.3624, a **4.3 point** understatement, on a premise whose entire claimed
    advantage is under one point.

    It hid because every teaser test used -7.5 and -2.5. Half-point lines cannot
    push, so the bug was invisible in exactly the tests that exercised the code.
    """

    def _nfl(self):
        rng = random.Random(7)
        pool = ([3] * 15 + [7] * 9 + [10] * 6 + [14] * 4 + [6] * 5 + [4] * 5
                + [1] * 5 + [17] * 3 + [21] * 3 + [2] * 4 + [8] * 4 + [13] * 3)
        margins = [rng.choice(pool) * rng.choice([1, -1]) for _ in range(4000)]
        return MarginDistribution("americanfootball_nfl").fit(margins)

    def test_an_integer_line_has_real_push_probability(self):
        d = self._nfl()
        assert d.probability_push(-3.0) > 0.05, "the mass at 3 vanished"
        assert d.probability_push(-7.0) > 0.03

    def test_a_half_point_line_can_never_push(self):
        """No integer equals 3.5. This falls out of discretising rather than
        from a special case, which is why it is asserted."""
        d = self._nfl()
        assert d.probability_push(-3.5) == 0.0
        assert d.probability_push(-7.5) == 0.0

    def test_buying_the_hook_is_worth_less_than_the_push_it_avoids(self):
        """The discriminating comparison.

        A -3 bet wins on 4+, pushes on 3. A -3.5 bet wins on 4+ and LOSES on 3.
        So conditional on resolving, -3 must be the better bet. Under the old
        code both returned the same number, because the push was silently
        bucketed as a loss on both.
        """
        d = self._nfl()
        assert d.probability_cover(-3.0) > d.probability_cover(-3.5)

    def test_pushes_leave_the_denominator_not_just_the_numerator(self):
        """`wins / (wins + losses)`, not `wins / n`.

        If pushes were only removed from the numerator the probability would be
        understated by exactly the push mass — the original bug wearing a
        different shape.
        """
        d = self._nfl()
        cover = d.probability_cover(-3.0)
        push = d.probability_push(-3.0)

        wins = sum(
            c for m, c in d.counts.items()
            if round(m + (0.0 - d.mean)) > 3.0
        )
        assert cover == pytest.approx(wins / (d.n * (1 - push)), rel=1e-6)

    def test_the_definitional_anchor_still_holds(self):
        """A team predicted to win by exactly its own line is a coin flip.

        Fixed by definition, and it is what caught the original inverted sign
        convention. Re-asserted here because push handling changes the
        denominator and could plausibly break it.
        """
        d = default_distribution("americanfootball_nfl")
        assert d.probability_cover(-7.5, predicted_margin=7.5) == pytest.approx(0.5)


class TestTotalsUseTheirOwnStandardDeviation:
    """`probability_total_over` priced totals on the MARGIN standard deviation.

    Margin is a difference of two team scores and total is their sum, so the
    correlation between the teams' scoring enters with opposite sign and the two
    spreads differ in every league — MLB 3.2 against 4.3, NBA 12 against 17.
    Using the margin SD understates total variance by 25–40%, which pushes every
    probability away from 0.5 and makes every total look mispriced against the
    book. One wrong symbol, applied to an entire market type.
    """

    def test_the_published_total_sd_exceeds_the_margin_sd_in_every_league(self):
        for league, total_sd in PUBLISHED_TOTAL_SD.items():
            assert total_sd > PUBLISHED_SD[league], league

    def test_a_total_is_not_priced_on_the_margin_spread(self):
        d = default_distribution("basketball_nba")
        on_total = d.probability_total_over(225.0, predicted_total=220.0)
        on_margin = d.probability_total_over(
            225.0, predicted_total=220.0, total_sd=d.sd
        )
        assert on_total != pytest.approx(on_margin, abs=1e-4)
        # The narrower (margin) SD pushes the probability further from 0.5.
        assert abs(on_margin - 0.5) > abs(on_total - 0.5)

    def test_a_measured_value_overrides_the_published_one(self):
        d = default_distribution("baseball_mlb")
        assert d.probability_total_over(
            9.0, predicted_total=8.5, total_sd=1.0
        ) != pytest.approx(d.probability_total_over(9.0, predicted_total=8.5))


class TestTheCalibratorSeesOnlyThePast:
    """It was fitted on the chronologically LAST 30% and applied to the earlier
    70% — so the calibrator had seen outcomes from games played *after* the
    predictions it was correcting.

    That is lookahead of the flattering kind: a calibrator tuned on the future
    of the very series it corrects will always look well-behaved on that series,
    which is exactly the impression a backtest is supposed to earn rather than
    assume.
    """

    def _series(self, n=400):
        """Predictions whose calibration error REVERSES halfway through.

        A split that takes the wrong half produces a visibly different
        calibrator, which is what makes the direction testable at all. With a
        stationary series both halves fit the same curve and nothing
        discriminates.
        """
        rng = random.Random(3)
        out = []
        for i in range(n):
            overconfident = i < n // 2
            p = 0.85 if overconfident else 0.55
            won = rng.random() < (0.55 if overconfident else 0.55)
            out.append(
                BacktestGame(
                    game=game(hs=1 if won else 0, as_=0),
                    model_probability=p,
                    closing_probability=0.55,
                )
            )
        return out

    def test_the_split_takes_the_earliest_games(self):
        series = self._series()
        calibration, evaluation = calibration_split(series, calibration_fraction=0.3)

        assert len(calibration) == 120
        assert calibration[0] is series[0], "did not start at the beginning"
        assert evaluation[0] is series[120]
        assert calibration[-1] is series[119]

    def test_calibration_and_evaluation_do_not_overlap(self):
        """The whole point of a split. Any shared game re-introduces the leak."""
        series = self._series()
        calibration, evaluation = calibration_split(series)
        assert not ({id(g) for g in calibration} & {id(g) for g in evaluation})

    def test_the_calibrator_reflects_the_early_regime_not_the_late_one(self):
        """The discriminating assertion.

        The first half is wildly overconfident (0.85 predictions winning 55%);
        the second is honest. A calibrator fitted on the early half must shrink
        the slope hard. One fitted on the late half — the old behaviour — sees
        nothing to correct.
        """
        series = self._series()
        early = fit_calibrator_on_holdout(series, calibration_fraction=0.3)

        late_games = series[int(len(series) * 0.7):]
        late = PlattCalibrator().fit(
            [g.model_probability for g in late_games],
            [g.home_won for g in late_games],
        )
        assert early.a != pytest.approx(late.a, abs=0.05), (
            "the calibrator is being fitted on the tail, not the head"
        )

    def test_an_empty_series_returns_an_unfitted_calibrator(self):
        assert fit_calibrator_on_holdout([]).fitted_on == 0


class TestEquicorrelationStaysPositiveSemiDefinite:
    """Below `-1/(n-1)` an equicorrelation matrix is not PSD, and the repair
    silently answers for a *different* correlation than the one asked about.

    `implied_correlation`'s residual therefore went flat across that region --
    every rho below the floor maps to the same repaired matrix -- so brentq
    returned an arbitrary point from a range of equally-good roots and reported
    it as a measurement. Same shape as the Shin `z <= _EPS` short-circuit this
    project already fixed once.
    """

    def _legs(self, n):
        return [
            Leg(f"L{i}", 0.5, f"event-{i}", "americanfootball_nfl", i * 86_400_000)
            for i in range(n)
        ]

    def test_the_floor_matches_the_eigenvalue_bound(self):
        """Fixed by algebra, not taste: eigenvalues are `1+(n-1)rho` and `1-rho`."""
        assert equicorrelation_floor(2) == -1.0
        assert equicorrelation_floor(3) == pytest.approx(-0.5)
        assert equicorrelation_floor(4) == pytest.approx(-1 / 3)

    def test_three_legs_cannot_all_be_strongly_anti_correlated(self):
        """A opposing B and B opposing C forces A and C to agree."""
        with pytest.raises(ValueError, match="positive semi-definite floor"):
            equicorrelated_joint(self._legs(3), -0.9)

    def test_two_legs_may_be_perfectly_anti_correlated(self):
        """The floor is -1 for a pair, so this must NOT refuse."""
        assert equicorrelated_joint(self._legs(2), -0.95) >= 0.0

    def test_implied_correlation_never_searches_below_the_floor(self):
        """A bracket extending past the floor is a bracket with a flat region.

        Asserted through behaviour: the default bounds reach -0.95, which is
        below the three-leg floor of -0.5, and this must still return a real
        root rather than an arbitrary point from the flat part.
        """
        legs = self._legs(3)
        joint = equicorrelated_joint(legs, 0.25)
        recovered = implied_correlation(legs, joint)
        assert recovered == pytest.approx(0.25, abs=0.05)


class TestTheUnreachableRangeMessageIsArithmeticallyRight:
    """`residual = joint(rho) - target`, so the joint reachable at each end is
    `target + residual`. The message printed `target - residual`, wrong at both
    ends -- a diagnostic that produced a range not containing the observed
    joint, actively misleading the reader it was written for.
    """

    def test_the_reported_range_brackets_what_is_actually_reachable(self):
        legs = [
            Leg("A", 0.6, "e1", "nfl", 0),
            Leg("B", 0.5, "e2", "nfl", 86_400_000),
        ]
        low, high = 0.5, 0.6
        reachable_low = equicorrelated_joint(legs, low)
        reachable_high = equicorrelated_joint(legs, high)

        with pytest.raises(CorrelationUnreachable) as excinfo:
            implied_correlation(legs, 0.301, bounds=(low, high))

        message = str(excinfo.value)
        assert f"{reachable_low:.4f}" in message
        assert f"{reachable_high:.4f}" in message
