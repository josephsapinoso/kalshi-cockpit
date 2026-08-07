"""Backtesting the Quant — against the closing line, never against accuracy.

The distinction is the whole point. A model that predicts NFL winners at 68%
sounds strong until you notice the closing line predicts them at 68% too. It
has learned what the market already knows and produced nothing actionable.

So the score that matters is **closing-line performance**: when the model
disagrees with the close, is it right often enough to pay for the fee? Accuracy
and Brier score are reported alongside, because a model can beat the close by
being *lucky* on a few disagreements while being badly calibrated everywhere —
and badly calibrated probabilities feed directly into Kelly sizing.

The same noise guards apply here as everywhere else. A backtest is a
measurement, and measurements in this project are assumed to be flattering
until they survive.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from ..analysis.validate import Observation, summarise_clv
from .elo import EloModel, GameResult, PlattCalibrator

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BacktestGame:
    """One historical game with what the model and the market each thought."""

    game: GameResult
    model_probability: float
    closing_probability: Optional[float]   # devigged market close for the home side

    @property
    def home_won(self) -> bool:
        return self.game.home_won

    @property
    def disagreement(self) -> Optional[float]:
        """Model minus market, in probability points. The only interesting axis."""
        if self.closing_probability is None:
            return None
        return self.model_probability - self.closing_probability


@dataclass(frozen=True)
class BacktestResult:
    n: int
    accuracy: float
    brier_score: float
    calibration_error: float
    n_disagreements: int
    disagreement_accuracy: Optional[float]
    market_accuracy_on_same_games: Optional[float]
    beats_close: Optional[bool]
    verdict: str


def brier(predictions: Sequence[float], outcomes: Sequence[bool]) -> float:
    """Mean squared error of probabilistic predictions. Lower is better.

    Rewards being right *and* being appropriately confident, which is why it is
    reported next to accuracy: a model can improve accuracy while getting worse
    at Brier by becoming overconfident, and overconfidence is what oversizes
    bets.
    """
    if not predictions:
        return float("nan")
    return sum(
        (p - (1.0 if o else 0.0)) ** 2 for p, o in zip(predictions, outcomes)
    ) / len(predictions)


def calibration_error(
    predictions: Sequence[float], outcomes: Sequence[bool], *, bins: int = 10
) -> float:
    """Expected calibration error: mean |predicted − observed| across bins.

    Weighted by bin population, and bins with fewer than 10 observations are
    skipped rather than contributing noise — the same minimum-sample principle
    as everywhere else.
    """
    if not predictions:
        return float("nan")

    buckets: dict[int, list[tuple[float, bool]]] = {}
    for p, o in zip(predictions, outcomes):
        index = min(bins - 1, int(p * bins))
        buckets.setdefault(index, []).append((p, o))

    total_weight = 0
    weighted_error = 0.0
    for rows in buckets.values():
        if len(rows) < 10:
            continue
        mean_predicted = sum(p for p, _ in rows) / len(rows)
        observed = sum(1 for _, o in rows if o) / len(rows)
        weighted_error += abs(mean_predicted - observed) * len(rows)
        total_weight += len(rows)

    return weighted_error / total_weight if total_weight else float("nan")


def backtest(
    games: Sequence[BacktestGame],
    *,
    min_disagreement: float = 0.03,
    min_games: int = 200,
) -> BacktestResult:
    """Score a model. `min_disagreement` is how far apart counts as disagreeing.

    3 points is deliberate: below it, the difference is inside the spread
    between devig methods on an even line, so a "disagreement" that small is a
    statement about method choice rather than about the game.
    """
    if not games:
        raise ValueError("no games to backtest")

    predictions = [g.model_probability for g in games]
    outcomes = [g.home_won for g in games]

    accuracy = sum(
        1 for p, o in zip(predictions, outcomes) if (p >= 0.5) == o
    ) / len(games)

    # The part that matters: only games where the model said something the
    # market did not.
    disagreements = [
        g for g in games
        if g.disagreement is not None and abs(g.disagreement) >= min_disagreement
    ]

    disagreement_accuracy: Optional[float] = None
    market_accuracy: Optional[float] = None
    beats_close: Optional[bool] = None

    if disagreements:
        disagreement_accuracy = sum(
            1 for g in disagreements if (g.model_probability >= 0.5) == g.home_won
        ) / len(disagreements)
        market_accuracy = sum(
            1 for g in disagreements
            if (g.closing_probability >= 0.5) == g.home_won
        ) / len(disagreements)
        beats_close = disagreement_accuracy > market_accuracy

    return BacktestResult(
        n=len(games),
        accuracy=accuracy,
        brier_score=brier(predictions, outcomes),
        calibration_error=calibration_error(predictions, outcomes),
        n_disagreements=len(disagreements),
        disagreement_accuracy=disagreement_accuracy,
        market_accuracy_on_same_games=market_accuracy,
        beats_close=beats_close,
        verdict=_verdict(
            len(games), len(disagreements), disagreement_accuracy,
            market_accuracy, min_games,
        ),
    )


def _verdict(
    n: int,
    n_disagreements: int,
    model_accuracy: Optional[float],
    market_accuracy: Optional[float],
    min_games: int,
) -> str:
    """State plainly whether this model has earned the right to size a bet."""
    if n < min_games:
        return (
            f"{n} games, below the {min_games} minimum. No verdict — a backtest "
            f"this small measures the seasons it happened to cover."
        )
    if not n_disagreements:
        return (
            "The model never meaningfully disagreed with the close. It has "
            "learned what the market already knows, which is not an edge."
        )
    if model_accuracy is None or market_accuracy is None:
        return "No closing lines available to compare against."

    gap = (model_accuracy - market_accuracy) * 100
    # Binomial standard error under the null that the model is no better.
    stderr = 100 * math.sqrt(0.25 / n_disagreements)

    if abs(gap) <= 2 * stderr:
        return (
            f"On {n_disagreements} disagreements the model was "
            f"{model_accuracy:.1%} against the market's {market_accuracy:.1%} "
            f"— a {gap:+.1f} point gap, inside the ±{2 * stderr:.1f} point "
            f"noise band. No demonstrated edge. Use as a research flag only."
        )
    if gap > 0:
        return (
            f"On {n_disagreements} disagreements the model was "
            f"{model_accuracy:.1%} against the market's {market_accuracy:.1%} "
            f"(+{gap:.1f} points, outside the ±{2 * stderr:.1f} noise band). "
            f"Worth confirming on a held-out season before it sizes anything."
        )
    return (
        f"The model was WORSE than the close on its own disagreements "
        f"({model_accuracy:.1%} vs {market_accuracy:.1%}). It should not "
        f"influence sizing."
    )


def walk_forward(
    games: Sequence[GameResult],
    model: EloModel,
    *,
    closing_probabilities: Optional[Sequence[Optional[float]]] = None,
    burn_in: int = 100,
) -> list[BacktestGame]:
    """Predict each game using only games before it, then learn from it.

    **This ordering is the entire validity of the backtest.** Training on the
    full history and then scoring it produces a model that has seen the
    outcomes it is predicting, which reliably looks excellent and is worth
    nothing. `burn_in` discards the opening stretch where every rating is still
    the 1500 default.
    """
    out: list[BacktestGame] = []
    for index, game in enumerate(games):
        probability = model.expected_home_win(game)
        if index >= burn_in:
            closing = (
                closing_probabilities[index]
                if closing_probabilities is not None
                and index < len(closing_probabilities)
                else None
            )
            out.append(
                BacktestGame(
                    game=game,
                    model_probability=probability,
                    closing_probability=closing,
                )
            )
        model.update(game)
    return out


def fit_calibrator_on_holdout(
    backtested: Sequence[BacktestGame], *, holdout_fraction: float = 0.3
) -> PlattCalibrator:
    """Fit calibration on the tail, leaving the head for evaluation.

    Fitting on the same games used to score is how a model becomes perfectly
    calibrated on paper and overconfident in practice.
    """
    if not backtested:
        return PlattCalibrator()
    split = int(len(backtested) * (1 - holdout_fraction))
    holdout = backtested[split:]
    return PlattCalibrator().fit(
        [g.model_probability for g in holdout], [g.home_won for g in holdout]
    )
