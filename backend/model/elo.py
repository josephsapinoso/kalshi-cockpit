"""Elo power ratings — the Michael Kent role, and its honest ceiling.

**This model is a disagreement detector, not an oracle.** Published Elo
implementations reach roughly 57% against the spread in NFL and 68% straight-up
in NBA. That second number sounds impressive until you notice it *matches*
Vegas over the same period. Matching the market is not an edge; it is a
well-calibrated restatement of what the market already knows.

So the model earns its place in exactly one way: when it disagrees with the
consensus by more than its own error bars, that disagreement is information the
devig pipeline does not have — because it comes from game results rather than
from the same sportsbook prices being devigged. Two independent estimates
agreeing is corroboration. One estimate counted twice is not.

Scoring
-------
`model/backtest.py` scores this against the **closing line**, never against
accuracy. A model that predicts winners at 68% and never disagrees with the
close has produced nothing. The question is whether its disagreements are
right.

Until it clears that bar it does not size bets. It flags a market for the Scout
to research, and nothing more.

Design notes
------------
Ratings are per-league and never comparable across leagues — an NFL 1600 and an
MLB 1600 mean different things, because the K-factor, home advantage, and
score-to-rating scale are all fitted per sport. The code refuses cross-league
comparisons rather than producing a plausible-looking number.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

DEFAULT_RATING = 1500.0

# Rating points per 400 is the classic Elo scale: a 400-point gap implies a
# 10:1 expected win ratio.
_SCALE = 400.0


@dataclass(frozen=True)
class LeagueConfig:
    """Per-league parameters. Never share these across sports.

    Defaults are starting points from published implementations, not fitted
    values. `fit_k_factor` exists because the right K depends on how much
    signal a single game carries, and that differs enormously: an NFL game is
    1/17th of a season, an MLB game 1/162nd.
    """

    league: str
    k_factor: float = 20.0
    # Home advantage in rating points. ~65 is the long-standing NFL figure;
    # baseball is much smaller.
    home_advantage: float = 55.0
    # Fraction of the way back to the mean between seasons. Rosters change;
    # last season's rating is evidence, not truth.
    season_regression: float = 0.25
    # Scale a rating update by margin of victory. Off for sports where margin
    # is noisy or capped.
    use_margin_of_victory: bool = True
    # Rating points per day of extra rest, and per 1000km travelled.
    rest_bonus_per_day: float = 4.0
    travel_penalty_per_1000km: float = 8.0

    @classmethod
    def for_league(cls, league: str) -> "LeagueConfig":
        presets = {
            # A single NFL game is a large share of the season, so K is high and
            # home advantage is the classic ~65.
            "americanfootball_nfl": dict(
                k_factor=20.0, home_advantage=65.0, season_regression=0.33
            ),
            # 162 games: each one says little, so K is small. Margin of victory
            # is deliberately off -- an 11-run blowout says almost nothing more
            # than a 2-run win about which team is better.
            "baseball_mlb": dict(
                k_factor=4.0, home_advantage=24.0, season_regression=0.30,
                use_margin_of_victory=False,
            ),
            "basketball_nba": dict(
                k_factor=20.0, home_advantage=100.0, season_regression=0.25
            ),
            "basketball_wnba": dict(
                k_factor=22.0, home_advantage=90.0, season_regression=0.30
            ),
            "icehockey_nhl": dict(
                k_factor=8.0, home_advantage=50.0, season_regression=0.30,
                use_margin_of_victory=False,
            ),
            # Wildly uneven schedules make college ratings unstable; regress hard.
            "americanfootball_ncaaf": dict(
                k_factor=25.0, home_advantage=65.0, season_regression=0.50
            ),
        }
        return cls(league=league, **presets.get(league, {}))


@dataclass
class GameResult:
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    played_ms: int
    season: Optional[str] = None
    home_rest_days: Optional[float] = None
    away_rest_days: Optional[float] = None
    away_travel_km: Optional[float] = None

    @property
    def home_won(self) -> bool:
        return self.home_score > self.away_score

    @property
    def margin(self) -> int:
        return self.home_score - self.away_score

    @property
    def is_draw(self) -> bool:
        return self.home_score == self.away_score


@dataclass
class EloModel:
    """Per-league Elo ratings, updated from results."""

    config: LeagueConfig
    ratings: dict[str, float] = field(default_factory=dict)
    games_seen: dict[str, int] = field(default_factory=dict)
    _current_season: Optional[str] = None

    def rating(self, team: str) -> float:
        return self.ratings.get(team, DEFAULT_RATING)

    def confidence(self, team: str) -> int:
        """Games this team's rating is based on.

        A rating from three games is a prior with noise attached. Callers use
        this to refuse to act on ratings that have not seen enough football.
        """
        return self.games_seen.get(team, 0)

    # -- prediction --------------------------------------------------------

    def effective_ratings(self, game: GameResult) -> tuple[float, float]:
        """Ratings adjusted for home field, rest, and travel.

        Separated from `expected_home_win` so a backtest can inspect *why* a
        prediction moved — an adjustment that turns out to carry no signal
        should be removed, not left in producing a number.
        """
        home = self.rating(game.home_team) + self.config.home_advantage
        away = self.rating(game.away_team)

        if game.home_rest_days is not None and game.away_rest_days is not None:
            differential = game.home_rest_days - game.away_rest_days
            home += differential * self.config.rest_bonus_per_day

        if game.away_travel_km is not None:
            away -= (
                game.away_travel_km / 1000.0
            ) * self.config.travel_penalty_per_1000km

        return home, away

    def expected_home_win(self, game: GameResult) -> float:
        """Probability the home team wins, before calibration.

        **Raw Elo output is not a calibrated probability.** It is a monotone
        function of a rating difference that happens to live in [0, 1]. Pass it
        through `PlattCalibrator` before it is allowed near a bet.
        """
        home, away = self.effective_ratings(game)
        return 1.0 / (1.0 + math.pow(10.0, (away - home) / _SCALE))

    # -- learning ----------------------------------------------------------

    def update(self, game: GameResult) -> tuple[float, float]:
        """Apply one result. Returns the rating changes (home, away).

        A draw scores 0.5 for both sides. Sports without draws never hit that
        path, and the ones with them would otherwise need a special case at
        every call site.
        """
        if game.season is not None and game.season != self._current_season:
            if self._current_season is not None:
                self.regress_to_mean()
            self._current_season = game.season

        expected = self.expected_home_win(game)
        actual = 0.5 if game.is_draw else (1.0 if game.home_won else 0.0)

        k = self.config.k_factor
        if self.config.use_margin_of_victory and not game.is_draw:
            k *= self._margin_multiplier(game, expected)

        delta = k * (actual - expected)

        self.ratings[game.home_team] = self.rating(game.home_team) + delta
        self.ratings[game.away_team] = self.rating(game.away_team) - delta
        for team in (game.home_team, game.away_team):
            self.games_seen[team] = self.games_seen.get(team, 0) + 1

        return delta, -delta

    def _margin_multiplier(self, game: GameResult, expected: float) -> float:
        """Scale the update by margin, damped for already-strong favourites.

        Without the damping, a good team beating a bad team badly inflates its
        rating without limit — an autocorrelation problem, because blowouts are
        *more likely* when the rating gap is already large. The denominator is
        the standard FiveThirtyEight correction.
        """
        margin = abs(game.margin)
        rating_diff = abs(
            self.effective_ratings(game)[0] - self.effective_ratings(game)[1]
        )
        winner_favoured = rating_diff if (
            (game.home_won and expected >= 0.5) or (not game.home_won and expected < 0.5)
        ) else -rating_diff
        return math.log(margin + 1.0) * (2.2 / (winner_favoured * 0.001 + 2.2))

    def regress_to_mean(self) -> None:
        """Pull every rating toward the league mean between seasons."""
        factor = self.config.season_regression
        if not 0.0 <= factor <= 1.0:
            raise ValueError(f"season_regression must be in [0, 1], got {factor}")
        for team, rating in self.ratings.items():
            self.ratings[team] = rating + (DEFAULT_RATING - rating) * factor
        logger.info(
            "%s: regressed %d ratings %.0f%% toward the mean",
            self.config.league, len(self.ratings), factor * 100,
        )

    def fit(self, games: Iterable[GameResult]) -> "EloModel":
        """Train on a chronological sequence of results.

        Order matters and is not checked here — passing shuffled games produces
        ratings that quietly incorporate the future. `backtest.py` enforces the
        ordering, which is where it belongs.
        """
        for game in games:
            self.update(game)
        return self


@dataclass
class PlattCalibrator:
    """Maps raw model scores to calibrated probabilities.

    Elo's logistic is a *scale*, not a calibration. A model can rank teams
    perfectly and still be systematically overconfident, and overconfidence
    feeds straight into Kelly sizing as a bet that is too large. Fitting
    `sigmoid(a * logit(p) + b)` on held-out games corrects the slope and
    intercept without touching the ranking.
    """

    a: float = 1.0
    b: float = 0.0
    fitted_on: int = 0

    def calibrate(self, probability: float) -> float:
        clamped = min(max(probability, 1e-6), 1 - 1e-6)
        logit = math.log(clamped / (1 - clamped))
        return 1.0 / (1.0 + math.exp(-(self.a * logit + self.b)))

    def fit(
        self,
        predictions: list[float],
        outcomes: list[bool],
        *,
        iterations: int = 200,
        learning_rate: float = 0.05,
    ) -> "PlattCalibrator":
        """Fit by gradient descent on log loss.

        Refuses below 50 observations. Fitting two parameters on a handful of
        games produces a calibrator that is itself noise, and unlike an
        uncalibrated model it *looks* principled.
        """
        if len(predictions) != len(outcomes):
            raise ValueError("predictions and outcomes must be the same length")
        if len(predictions) < 50:
            logger.warning(
                "refusing to fit a calibrator on %d observations; needs >= 50. "
                "Returning identity.", len(predictions),
            )
            return PlattCalibrator(a=1.0, b=0.0, fitted_on=0)

        logits = [
            math.log(min(max(p, 1e-6), 1 - 1e-6) / (1 - min(max(p, 1e-6), 1 - 1e-6)))
            for p in predictions
        ]
        targets = [1.0 if o else 0.0 for o in outcomes]
        a, b = 1.0, 0.0
        n = len(logits)

        for _ in range(iterations):
            grad_a = grad_b = 0.0
            for logit, target in zip(logits, targets):
                predicted = 1.0 / (1.0 + math.exp(-(a * logit + b)))
                error = predicted - target
                grad_a += error * logit
                grad_b += error
            a -= learning_rate * grad_a / n
            b -= learning_rate * grad_b / n

        return PlattCalibrator(a=a, b=b, fitted_on=n)
