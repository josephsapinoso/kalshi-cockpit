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
class PairedComparison:
    """Model versus market on the **same** games, which makes it a paired test.

    Why this is its own object: `beats_close` and the verdict string used to be
    computed by two separate paths from the same inputs. One said
    `disagreement_accuracy > market_accuracy` with no noise guard at all; the
    other correctly reported "inside the noise band, no demonstrated edge". They
    could disagree, and eventually would, and the boolean is the one a caller
    branches on. Everything below is derived from this one object so that cannot
    happen. See `tasks/lessons.md`, 2026-08-07.

    **Why not `sqrt(0.25/n)`.** That is the null standard error of a *single*
    proportion. This is the difference of two accuracies measured on the same
    games, so the games where both were right or both were wrong carry no
    information about which is better — only the discordant ones do. McNemar's
    test uses exactly those:

        gap = (b - c) / n          stderr = sqrt(b + c) / n

    where `b` is games the model got right and the market got wrong, and `c` the
    reverse. The two forms coincide at a discordance rate of 25%; above it the
    old one is **too narrow**, which is the direction that manufactures
    significance. Near-pick'em games push discordance well past 25%.
    """

    n: int
    model_right_market_wrong: int
    market_right_model_wrong: int
    model_accuracy: float
    market_accuracy: float

    @property
    def discordant(self) -> int:
        return self.model_right_market_wrong + self.market_right_model_wrong

    @property
    def gap_points(self) -> float:
        """Model accuracy minus market accuracy, in percentage points."""
        return (self.model_accuracy - self.market_accuracy) * 100.0

    @property
    def stderr_points(self) -> float:
        """McNemar standard error of the gap, in percentage points."""
        if not self.n:
            return 0.0
        return 100.0 * math.sqrt(self.discordant) / self.n

    @property
    def noise_band_points(self) -> float:
        return 2.0 * self.stderr_points

    @property
    def distinguishable(self) -> bool:
        """Whether the gap clears two standard errors. Not whether it is positive."""
        return abs(self.gap_points) > self.noise_band_points


@dataclass(frozen=True)
class BacktestResult:
    n: int
    accuracy: float
    brier_score: float
    calibration_error: float
    n_disagreements: int
    disagreement_accuracy: Optional[float]
    market_accuracy_on_same_games: Optional[float]
    # Tri-state, and the distinction is the point:
    #   None  -- cannot be assessed (too few games, or no disagreements)
    #   False -- NOT DEMONSTRATED, which includes "inside the noise band"
    #   True  -- beat the close by more than two standard errors
    # "Not demonstrated" and "does not beat" are different claims, and this field
    # only ever asserts the strong one. It is derived from `comparison`, never
    # computed alongside it.
    beats_close: Optional[bool]
    verdict: str
    comparison: Optional[PairedComparison] = None
    # The numbers behind the verdict, so a reader is never asked to trust a
    # boolean without being able to check it.
    gap_points: Optional[float] = None
    noise_band_points: Optional[float] = None


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

    comparison = _compare(disagreements)

    # Derived from the comparison, not computed beside it. Below `min_games` the
    # verdict declines to rule, so this must decline too -- a boolean saying
    # True next to a verdict saying "no verdict" is the failure this replaces.
    beats_close: Optional[bool] = None
    if comparison is not None and len(games) >= min_games:
        beats_close = comparison.distinguishable and comparison.gap_points > 0

    return BacktestResult(
        n=len(games),
        accuracy=accuracy,
        brier_score=brier(predictions, outcomes),
        calibration_error=calibration_error(predictions, outcomes),
        n_disagreements=len(disagreements),
        disagreement_accuracy=comparison.model_accuracy if comparison else None,
        market_accuracy_on_same_games=comparison.market_accuracy if comparison else None,
        beats_close=beats_close,
        verdict=_verdict(len(games), comparison, min_games),
        comparison=comparison,
        gap_points=comparison.gap_points if comparison else None,
        noise_band_points=comparison.noise_band_points if comparison else None,
    )


def _compare(disagreements: Sequence[BacktestGame]) -> Optional[PairedComparison]:
    """Tally the paired outcomes. `None` when there is nothing to compare."""
    if not disagreements:
        return None

    model_right_market_wrong = 0
    market_right_model_wrong = 0
    model_hits = 0
    market_hits = 0

    for game in disagreements:
        model_right = (game.model_probability >= 0.5) == game.home_won
        market_right = (game.closing_probability >= 0.5) == game.home_won
        model_hits += model_right
        market_hits += market_right
        if model_right and not market_right:
            model_right_market_wrong += 1
        elif market_right and not model_right:
            market_right_model_wrong += 1

    n = len(disagreements)
    return PairedComparison(
        n=n,
        model_right_market_wrong=model_right_market_wrong,
        market_right_model_wrong=market_right_model_wrong,
        model_accuracy=model_hits / n,
        market_accuracy=market_hits / n,
    )


def _verdict(n: int, comparison: Optional[PairedComparison], min_games: int) -> str:
    """State plainly whether this model has earned the right to size a bet.

    Reads every number off `comparison`, so the prose and `beats_close` cannot
    tell different stories.
    """
    if n < min_games:
        return (
            f"{n} games, below the {min_games} minimum. No verdict — a backtest "
            f"this small measures the seasons it happened to cover."
        )
    if comparison is None:
        return (
            "The model never meaningfully disagreed with the close. It has "
            "learned what the market already knows, which is not an edge."
        )

    head = (
        f"On {comparison.n} disagreements the model was "
        f"{comparison.model_accuracy:.1%} against the market's "
        f"{comparison.market_accuracy:.1%}"
    )
    band = (
        f"±{comparison.noise_band_points:.1f} point noise band "
        f"({comparison.discordant} discordant games)"
    )

    if not comparison.distinguishable:
        return (
            f"{head} — a {comparison.gap_points:+.1f} point gap, inside the "
            f"{band}. No demonstrated edge. Use as a research flag only."
        )
    if comparison.gap_points > 0:
        return (
            f"{head} ({comparison.gap_points:+.1f} points, outside the {band}). "
            f"Worth confirming on a held-out season before it sizes anything."
        )
    return (
        f"The model was WORSE than the close on its own disagreements "
        f"({comparison.model_accuracy:.1%} vs {comparison.market_accuracy:.1%}, "
        f"{comparison.gap_points:+.1f} points, outside the {band}). It should "
        f"not influence sizing."
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
    backtested: Sequence[BacktestGame], *, calibration_fraction: float = 0.3
) -> PlattCalibrator:
    """Fit calibration on the EARLIEST games, leaving the rest for evaluation.

    Fitting on the same games used to score is how a model becomes perfectly
    calibrated on paper and overconfident in practice.

    **This used to fit on the chronologically LAST 30%** and then correct the
    earlier 70% — so the calibrator had seen the outcomes of games played after
    the predictions it was adjusting. That is lookahead, and it is the specific
    kind that flatters: a calibrator tuned on the future of the very series it
    corrects will always look well-behaved on that series.

    `backtested` is assumed to be in chronological order, which is what
    `walk_forward` returns. The split is by position rather than by timestamp
    for that reason; a caller that reorders the list defeats this silently, so
    do not.

    Returns the `evaluation` slice's counterpart via `calibration_split` when a
    caller needs the two halves explicitly.
    """
    if not backtested:
        return PlattCalibrator()
    calibration, _ = calibration_split(
        backtested, calibration_fraction=calibration_fraction
    )
    return PlattCalibrator().fit(
        [g.model_probability for g in calibration],
        [g.home_won for g in calibration],
    )


def calibration_split(
    backtested: Sequence[BacktestGame], *, calibration_fraction: float = 0.3
) -> tuple[Sequence[BacktestGame], Sequence[BacktestGame]]:
    """`(calibration, evaluation)` — earliest games first, in that order.

    Exposed so a caller can score on the evaluation half rather than on
    everything. Scoring the calibration games again is not fatal, but it does
    quietly reintroduce the overlap this split exists to remove.
    """
    split = max(1, int(len(backtested) * calibration_fraction))
    return backtested[:split], backtested[split:]
