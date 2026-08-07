"""Correlation between legs — the thing that makes parlay maths wrong.

Multiplying leg probabilities is only valid when the legs are independent.
Almost nothing a bettor wants to combine is independent, and the error runs in
one direction: **assuming independence overstates the probability of correlated
legs winning together**, which makes a bad parlay look priceable.

Three regimes, and they differ by orders of magnitude:

**Same game.** Severe, and often obvious once stated. "Team A wins" and "over
the total" are positively correlated in football (a team scoring a lot tends to
win) and negatively in some baseball spots. This module **refuses** to price
same-game legs from marginals alone, because there is no defensible default —
the correlation depends on the specific pair, and a plausible-looking number
here is worse than no number.

**Same day, same league.** Mild but real. Shared weather, shared officiating
crews, shared travel patterns. Small enough to model with a scalar.

**Cross-sport.** Near-independent. Not exactly independent — a market-wide news
shock or a common bettor-flow effect touches everything — but close enough that
a small residual correlation is the honest treatment.

Joint probabilities use a **Gaussian copula**: map each marginal through the
normal quantile, impose the correlation there, and read back the joint. It
preserves each leg's marginal exactly while letting them co-move, which naive
multiplication cannot do at all.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence

import numpy as np
from scipy.stats import norm

logger = logging.getLogger(__name__)

# Fixed seed: a fair price that changes between two runs of the same input is
# not a price, and it makes every downstream test flaky.
_MC_SEED = 20260807
_MC_SAMPLES = 200_000


class Relationship(str, Enum):
    SAME_GAME = "same_game"
    SAME_DAY_SAME_LEAGUE = "same_day_same_league"
    SAME_DAY_CROSS_LEAGUE = "same_day_cross_league"
    INDEPENDENT = "independent"


# Defaults for the regimes we are willing to model. SAME_GAME is deliberately
# absent: there is no defensible default for it.
DEFAULT_CORRELATION: dict[Relationship, float] = {
    Relationship.SAME_DAY_SAME_LEAGUE: 0.05,
    Relationship.SAME_DAY_CROSS_LEAGUE: 0.02,
    Relationship.INDEPENDENT: 0.0,
}


class CorrelationRefused(ValueError):
    """Raised when legs cannot be combined without a correlation estimate."""


@dataclass(frozen=True)
class Leg:
    """One leg of a combination."""

    label: str
    probability: float
    event_key: str          # identifies the fixture -- same key means same game
    league: str
    commence_ms: int

    def __post_init__(self) -> None:
        if not 0.0 < self.probability < 1.0:
            raise ValueError(
                f"{self.label}: probability {self.probability} must be strictly "
                f"inside (0, 1). A certainty is not a leg."
            )


def classify(a: Leg, b: Leg, *, same_day_ms: int = 86_400_000) -> Relationship:
    """How two legs relate. Drives which correlation applies."""
    if a.event_key == b.event_key:
        return Relationship.SAME_GAME
    if abs(a.commence_ms - b.commence_ms) <= same_day_ms:
        return (
            Relationship.SAME_DAY_SAME_LEAGUE
            if a.league == b.league
            else Relationship.SAME_DAY_CROSS_LEAGUE
        )
    return Relationship.INDEPENDENT


def correlation_matrix(
    legs: Sequence[Leg],
    *,
    overrides: Optional[dict[tuple[str, str], float]] = None,
) -> np.ndarray:
    """Pairwise correlation matrix for a set of legs.

    Raises `CorrelationRefused` on a same-game pair with no override. That is
    the point of the module: the caller must supply a measured correlation for
    that specific pair or not price the combination at all.
    """
    overrides = overrides or {}
    n = len(legs)
    matrix = np.eye(n)

    for i in range(n):
        for j in range(i + 1, n):
            a, b = legs[i], legs[j]
            key = (a.label, b.label)
            reverse = (b.label, a.label)

            if key in overrides or reverse in overrides:
                rho = overrides.get(key, overrides.get(reverse))
            else:
                relationship = classify(a, b)
                if relationship is Relationship.SAME_GAME:
                    raise CorrelationRefused(
                        f"'{a.label}' and '{b.label}' are legs of the same "
                        f"fixture ({a.event_key}). Same-game legs are strongly "
                        f"correlated and the sign depends on the specific pair, "
                        f"so there is no defensible default. Supply a measured "
                        f"correlation via `overrides`, or price them separately. "
                        f"Multiplying the marginals would overstate the parlay's "
                        f"chance of landing."
                    )
                rho = DEFAULT_CORRELATION[relationship]

            matrix[i, j] = matrix[j, i] = rho

    return _nearest_positive_definite(matrix)


def _nearest_positive_definite(matrix: np.ndarray) -> np.ndarray:
    """Repair a correlation matrix that is not positive semi-definite.

    Hand-supplied pairwise correlations need not be jointly consistent — three
    legs each 0.9 correlated with each other cannot all be true. Clipping the
    negative eigenvalues finds the closest matrix that can be, rather than
    letting the copula fail obscurely later.
    """
    eigenvalues, eigenvectors = np.linalg.eigh(matrix)
    if (eigenvalues >= -1e-8).all():
        return matrix

    logger.warning(
        "supplied correlations were not jointly consistent (min eigenvalue "
        "%.4f); projecting to the nearest valid matrix", eigenvalues.min()
    )
    repaired = eigenvectors @ np.diag(np.clip(eigenvalues, 1e-8, None)) @ eigenvectors.T
    scale = np.sqrt(np.diag(repaired))
    return repaired / np.outer(scale, scale)


def joint_probability_all(
    legs: Sequence[Leg],
    *,
    overrides: Optional[dict[tuple[str, str], float]] = None,
    samples: int = _MC_SAMPLES,
) -> float:
    """P(every leg wins), under a Gaussian copula.

    With all correlations zero this reproduces the product of the marginals to
    within Monte Carlo error, which is the sanity check the tests assert.
    """
    if not legs:
        raise ValueError("no legs provided")
    if len(legs) == 1:
        return legs[0].probability

    matrix = correlation_matrix(legs, overrides=overrides)

    if np.allclose(matrix, np.eye(len(legs))):
        # Exact, and avoids sampling error on the common case.
        return float(np.prod([leg.probability for leg in legs]))

    rng = np.random.default_rng(_MC_SEED)
    draws = rng.multivariate_normal(
        mean=np.zeros(len(legs)), cov=matrix, size=samples, method="cholesky"
    )
    # A leg wins when its latent variable falls below its own quantile, which
    # preserves each marginal exactly.
    thresholds = norm.ppf([leg.probability for leg in legs])
    return float((draws < thresholds).all(axis=1).mean())


class CorrelationUnreachable(ValueError):
    """Raised when no correlation could produce an observed joint price."""


def equicorrelated_joint(
    legs: Sequence[Leg], rho: float, *, samples: int = _MC_SAMPLES
) -> float:
    """P(all legs win) when every pair carries the same correlation `rho`."""
    labels = [leg.label for leg in legs]
    overrides = {
        (labels[i], labels[j]): rho
        for i in range(len(labels))
        for j in range(i + 1, len(labels))
    }
    return joint_probability_all(legs, overrides=overrides, samples=samples)


def implied_correlation(
    legs: Sequence[Leg],
    joint_probability: float,
    *,
    bounds: tuple[float, float] = (-0.95, 0.95),
) -> float:
    """The equicorrelation implied by an observed joint price.

    This is the module's answer to its own refusal. `correlation_matrix` will
    not price same-game legs without a measured correlation, because the sign
    depends on the specific pair -- and this is how a measurement is obtained
    rather than guessed: given each leg's marginal and a *quoted* price for all
    of them landing together, invert the copula for the rho that reproduces it.

    Kalshi's combo product quotes exactly that joint, which makes its price a
    correlation observation rather than merely a number to beat.

    Raises `CorrelationUnreachable` when the joint is outside the Frechet
    bounds (no dependence structure of any kind could produce it, so the inputs
    disagree) or outside what `bounds` can reach (the implied dependence is more
    extreme than a single equicorrelation can express).
    """
    if not 0.0 < joint_probability < 1.0:
        raise CorrelationUnreachable(
            f"joint probability {joint_probability} must be strictly inside (0, 1)"
        )

    marginals = [leg.probability for leg in legs]
    # Frechet-Hoeffding: the joint can never exceed the smallest marginal, and
    # can never fall below sum(p) - (n - 1).
    upper = min(marginals)
    lower = max(0.0, sum(marginals) - (len(marginals) - 1))
    if not lower <= joint_probability <= upper:
        raise CorrelationUnreachable(
            f"a joint of {joint_probability:.4f} is outside the Frechet bounds "
            f"[{lower:.4f}, {upper:.4f}] for these marginals. No dependence "
            f"structure produces it, so the joint and the legs disagree -- "
            f"check that the legs are the ones actually being priced."
        )

    from scipy.optimize import brentq

    def residual(rho: float) -> float:
        return equicorrelated_joint(legs, rho) - joint_probability

    low, high = bounds
    residual_low, residual_high = residual(low), residual(high)
    if residual_low > 0 or residual_high < 0:
        raise CorrelationUnreachable(
            f"a joint of {joint_probability:.4f} implies a correlation outside "
            f"[{low}, {high}] (reachable range "
            f"{joint_probability - residual_low:.4f}.."
            f"{joint_probability - residual_high:.4f}). The dependence is "
            f"stronger than one equicorrelation can express -- price the pairs "
            f"separately rather than forcing a single number."
        )

    return float(brentq(residual, low, high, xtol=1e-4))


def independence_error(
    legs: Sequence[Leg],
    *,
    overrides: Optional[dict[tuple[str, str], float]] = None,
) -> float:
    """How much naive multiplication overstates the parlay, in points.

    Reported alongside every parlay price so the size of the assumption is
    visible rather than implicit.
    """
    naive = float(np.prod([leg.probability for leg in legs]))
    actual = joint_probability_all(legs, overrides=overrides)
    return (naive - actual) * 100
