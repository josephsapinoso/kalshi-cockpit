"""Margin-of-victory distributions, and why key numbers exist.

A moneyline needs one number: the probability a team wins. A **spread** or a
**total** needs the whole distribution — the probability the margin lands above
a line — and that distribution is emphatically not smooth.

Football margins pile up on **3, 7, 10 and 14**, because scores are built from
field goals and touchdowns. Roughly 15% of NFL games end with a margin of
exactly 3 and 9% at exactly 7. That lumpiness is the entire basis of the Wong
teaser: moving a line from −8.5 to −2.5 crosses *both* 7 and 3, buying far more
probability than six generic points would.

A normal approximation gets this exactly wrong. It smooths the spikes away and
prices the 3 and the 7 like any other point, which makes the one genuinely
documented book-side edge invisible. So this module fits an **empirical**
distribution and falls back to a smooth one only when it says so.

Sign convention, stated once because getting it wrong is silent
---------------------------------------------------------------
`line` is the spread in ordinary betting notation, from the perspective of the
side being bet: **−7.5 means laying 7.5 points, +7.5 means receiving them.**
A bet covers when

    margin > −line

so a −7.5 favourite must win by 8+, and a +7.5 underdog survives anything short
of a 8-point loss. Cover probability therefore **rises** as the line rises.
An earlier version of this module compared `margin > line`, which inverted every
spread price while remaining entirely plausible-looking — and its test asserted
the inverted claim, so the whole thing passed.

What this module does not do
----------------------------
It gives no opinion on who wins — that is `elo.py`. It supplies P(margin > x)
given a predicted mean margin, and nothing else.

It also will not pretend a league-wide margin distribution can be slid sideways
to represent a specific game. See `translation_points` — spikes live at absolute
margins of 3 and 7, so translating a pooled distribution by eight points puts
them at 11 and 15, which is worse than not having them.
"""

from __future__ import annotations

import logging
import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

logger = logging.getLogger(__name__)

# Margins that occur far more often than a smooth distribution predicts.
# Football only: basketball and baseball margins are close to smooth.
KEY_NUMBERS: dict[str, tuple[int, ...]] = {
    "americanfootball_nfl": (3, 7, 10, 14, 6, 4),
    "americanfootball_ncaaf": (3, 7, 10, 14),
}

# Below this, an empirical distribution is mostly reproducing its own sampling
# noise and a smooth fit is more honest.
MIN_GAMES_FOR_EMPIRICAL = 200

# How far a distribution may be translated before its key numbers have moved so
# much that the empirical shape is worse than useless. Two points is about the
# most a power-rating model should ever disagree with a closing spread; beyond
# that the caller is sliding a league-wide distribution onto one game.
MAX_TRANSLATION_POINTS = 2.0


@dataclass
class MarginDistribution:
    """Empirical distribution of final margins for one league.

    `counts` holds **signed** margins. Storing only absolute values would force
    the sign to be reconstructed as symmetric about the mean, which is false for
    any distribution fitted on a set of favourites -- exactly the set a teaser
    is priced against.
    """

    league: str
    counts: Counter = field(default_factory=Counter)
    n: int = 0
    mean: float = 0.0
    sd: float = 13.5   # NFL-ish default; overwritten on fit
    # The closing spread this distribution was fitted for, if it was fitted per
    # bucket. `None` means league-wide, which cannot be slid onto one game.
    spread_bucket: Optional[float] = None

    @property
    def is_empirical(self) -> bool:
        """Whether there is enough data to trust the observed shape."""
        return self.n >= MIN_GAMES_FOR_EMPIRICAL

    @property
    def has_key_numbers(self) -> bool:
        return bool(KEY_NUMBERS.get(self.league))

    def fit(self, margins: Iterable[int]) -> "MarginDistribution":
        values = [int(m) for m in margins]
        if not values:
            raise ValueError("no margins provided")

        self.counts = Counter(values)
        self.n = len(values)
        self.mean = sum(values) / self.n
        variance = sum((v - self.mean) ** 2 for v in values) / max(1, self.n - 1)
        self.sd = math.sqrt(variance)

        if not self.is_empirical:
            logger.warning(
                "%s: fitted on %d games, below the %d needed for an empirical "
                "distribution. Falling back to a normal fit -- key numbers will "
                "be smoothed away.",
                self.league, self.n, MIN_GAMES_FOR_EMPIRICAL,
            )
        return self

    def probability_of_exact_margin(self, margin: int) -> float:
        """P(|margin| == x). Zero outside the observed support.

        Absolute, because a key number is a key number in either direction: a
        three-point loss is as common as a three-point win.
        """
        if not self.n:
            return 0.0
        magnitude = abs(int(margin))
        hits = self.counts.get(magnitude, 0)
        if magnitude:
            hits += self.counts.get(-magnitude, 0)
        return hits / self.n

    def translation_points(self, predicted_margin: float) -> float:
        """How far pricing at `predicted_margin` would drag the fitted shape.

        The key numbers sit at absolute margins of 3, 7, 10 and 14. Translating
        the distribution moves them, so a league-wide fit shifted onto an
        eight-point favourite puts its 3-spike at 11 and its 7-spike at 15. The
        result still looks like an empirical distribution and is wronger than
        the normal approximation it replaced.

        A per-bucket fit keeps this small: the shift is only the model's
        disagreement with the closing spread, typically a point or two.
        """
        if not self.is_empirical or not self.has_key_numbers:
            return 0.0
        return abs(predicted_margin - self.mean)

    def key_number_mass(self) -> dict[int, float]:
        """How much probability sits on each key number.

        This is the number that makes teasers work, and it should be *looked
        at* before any teaser is priced. If 3 and 7 are not carrying unusual
        mass in the fitted data, either the data is wrong or the sport is not
        football, and the teaser logic below does not apply.
        """
        keys = KEY_NUMBERS.get(self.league, ())
        return {k: self.probability_of_exact_margin(k) for k in keys}

    def probability_cover(self, line: float, *, predicted_margin: float = 0.0) -> float:
        """P(a bet at spread `line` covers), given a predicted mean margin.

        `line` is ordinary betting notation from the perspective of the side
        being bet: −7.5 lays 7.5 points, +7.5 receives them. The bet covers when
        `margin > −line`, so this **rises** as `line` rises.

        With enough data this counts actual outcomes, which preserves the
        spikes. Without it, a normal approximation — flagged via `is_empirical`,
        because it silently prices a half-point through 3 the same as a
        half-point through 11.
        """
        if not self.is_empirical:
            return _normal_survival(-line, mu=predicted_margin, sigma=self.sd)

        # Translate the fitted shape so its centre sits on our predicted margin.
        # `translation_points` reports what this costs; callers pricing key
        # numbers are expected to check it.
        shift = predicted_margin - self.mean
        threshold = -line
        hits = sum(
            count for margin, count in self.counts.items()
            if margin + shift > threshold
        )
        return hits / self.n

    def probability_total_over(self, line: float, *, predicted_total: float) -> float:
        """P(combined score > line). Totals are close to smooth, so normal."""
        return _normal_survival(line, mu=predicted_total, sigma=self.sd)


def _normal_survival(x: float, *, mu: float, sigma: float) -> float:
    """P(X > x) for a normal. Uses erf rather than a table."""
    if sigma <= 0:
        return 1.0 if mu > x else 0.0
    return 0.5 * math.erfc((x - mu) / (sigma * math.sqrt(2.0)))


# ---------------------------------------------------------------------------
# Teasers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TeaserLeg:
    """One leg of a teaser, before and after the points are applied."""

    team: str
    original_line: float
    teased_line: float
    predicted_margin: float

    @property
    def crosses(self) -> tuple[int, ...]:
        """Key numbers this leg moves through. The whole point of a Wong."""
        low, high = sorted((self.original_line, self.teased_line))
        return tuple(
            k for k in (3, 7, 10, 14) if low < k < high or low < -k < high
        )


def wong_candidate(original_line: float, points: float = 6.0) -> bool:
    """Whether a leg fits the classic Wong teaser window.

    Favourites of −7.5 to −8.5 teased down cross both 7 and 3; underdogs of
    +1.5 to +2.5 teased up do the same. Those two windows are the documented
    edge, and everything outside them is an ordinary teaser — which is to say
    a bad bet dressed up as a strategy.
    """
    if points != 6.0:
        return False
    return (-8.5 <= original_line <= -7.5) or (1.5 <= original_line <= 2.5)


def teaser_leg_probability(
    distribution: MarginDistribution,
    *,
    original_line: float,
    points: float,
    predicted_margin: float,
) -> tuple[float, TeaserLeg]:
    """Probability one teased leg covers, plus the leg for inspection.

    Teasing always moves the line in the bettor's favour: a favourite's line
    moves toward zero, an underdog's away from it.
    """
    # Teasing always adds points, whichever side you are on: a favourite's line
    # moves toward zero (-8 -> -2) and an underdog's away from it (+2 -> +8).
    teased = original_line + points
    leg = TeaserLeg(
        team="", original_line=original_line, teased_line=teased,
        predicted_margin=predicted_margin,
    )
    probability = distribution.probability_cover(
        teased, predicted_margin=predicted_margin
    )
    return probability, leg


def spread_bucket_for(spread: float, *, bucket_width: float = 2.0) -> float:
    """Which bucket a closing spread falls into.

    Exposed because a caller holding a live line needs to look up the matching
    distribution, and re-deriving the rule at the call site is how the two drift
    apart.
    """
    return round(float(spread) / bucket_width) * bucket_width


def fit_by_spread(
    league: str,
    observations: Sequence[tuple[float, int]],
    *,
    bucket_width: float = 2.0,
) -> dict[float, MarginDistribution]:
    """Fit one distribution per closing-spread bucket.

    `observations` is `(closing_spread, actual_margin)` from the same side's
    perspective throughout — spread −8 with margin +11 is a favourite laying 8
    that won by 11.

    This is what makes an empirical fit usable for a single game. A league-wide
    distribution has to be dragged eight points sideways to price an eight-point
    favourite, which relocates every key number; a bucketed one is already
    centred where it belongs, so the only translation left is the model's
    disagreement with the market. `translation_points` is what tells the two
    apart, and `core.teaser` refuses on the difference.

    Buckets below `MIN_GAMES_FOR_EMPIRICAL` are still returned, flagged
    non-empirical, so the coverage gap is visible rather than absent.
    """
    grouped: dict[float, list[int]] = {}
    for spread, margin in observations:
        bucket = spread_bucket_for(spread, bucket_width=bucket_width)
        grouped.setdefault(bucket, []).append(int(margin))

    fitted: dict[float, MarginDistribution] = {}
    for bucket, margins in sorted(grouped.items()):
        distribution = MarginDistribution(league=league, spread_bucket=bucket)
        distribution.fit(margins)
        fitted[bucket] = distribution

    thin = [b for b, d in fitted.items() if not d.is_empirical]
    if thin:
        logger.warning(
            "%s: %d of %d spread buckets are below %d games (%s). Teasers in "
            "those buckets will refuse rather than price.",
            league, len(thin), len(fitted), MIN_GAMES_FOR_EMPIRICAL,
            ", ".join(f"{b:+g}" for b in sorted(thin)),
        )
    return fitted


def default_distribution(league: str) -> MarginDistribution:
    """A distribution with published standard deviations and no empirical mass.

    Explicitly **not** fitted, so `is_empirical` is False and every consumer
    knows it is getting a smooth approximation with the key numbers absent.
    Present so the rest of the system can be built and tested before a
    historical results feed exists.
    """
    sds = {
        "americanfootball_nfl": 13.5,
        "americanfootball_ncaaf": 17.0,
        "basketball_nba": 12.0,
        "basketball_wnba": 12.5,
        "baseball_mlb": 3.2,
        "icehockey_nhl": 1.9,
    }
    return MarginDistribution(league=league, sd=sds.get(league, 12.0))
