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

# Below this, the sample cannot estimate a standard deviation at all and the
# published value is kept instead.
#
# Deliberately a **separate, much lower** threshold from
# `MIN_GAMES_FOR_EMPIRICAL`, because the two answer different questions. That
# one asks "can this sample show me the *shape*, spikes and all?" — which needs
# hundreds of games. This one asks "can it tell me the *width*?" — which is one
# number and needs far fewer.
#
# Collapsing them is what created the defect this constant exists to close: the
# non-empirical branch fell back to a normal approximation whose sigma had just
# been overwritten from the same thin sample it was falling back *from*. At
# `n = 1` the old `max(1, n - 1)` denominator gave variance 0, hence `sd = 0`,
# hence a cover probability of exactly 1.0 or 0.0 — a certainty, which in Kelly
# sizing is an unbounded bet off a single observation.
MIN_GAMES_FOR_SD = 30

# Published per-league standard deviations of final margin. Sourced values, not
# measured here, which is why anything using them reports `sd_is_measured` as
# False. Kept at module scope so `fit` has something to fall back *to*.
PUBLISHED_SD: dict[str, float] = {
    "americanfootball_nfl": 13.5,
    "americanfootball_ncaaf": 17.0,
    "basketball_nba": 12.0,
    "basketball_wnba": 12.5,
    "baseball_mlb": 3.2,
    "icehockey_nhl": 1.9,
}
DEFAULT_PUBLISHED_SD = 12.0


# How far a distribution may be translated before its key numbers have moved so
# much that the empirical shape is worse than useless. Two points is about the
# most a power-rating model should ever disagree with a closing spread; beyond
# that the caller is sliding a league-wide distribution onto one game.
MAX_TRANSLATION_POINTS = 2.0


def published_sd(league: str) -> float:
    """The published margin standard deviation for a league.

    The fallback is a football-ish 12.0, which is wildly wrong for baseball or
    hockey — so an unknown league is logged rather than absorbed. A silently
    wrong width prices every spread in that league.
    """
    if league not in PUBLISHED_SD:
        logger.warning(
            "%s: no published margin standard deviation; using %.1f, which is "
            "a football-shaped guess and wrong for a low-scoring sport.",
            league, DEFAULT_PUBLISHED_SD,
        )
    return PUBLISHED_SD.get(league, DEFAULT_PUBLISHED_SD)


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
    # `None` means "use the league's published value". Resolved in __post_init__
    # so `sd` is always a positive float afterwards. It is never 0: a zero width
    # makes every probability a certainty.
    sd: Optional[float] = None
    # The closing spread this distribution was fitted for, if it was fitted per
    # bucket. `None` means league-wide, which cannot be slid onto one game.
    spread_bucket: Optional[float] = None
    # Whether `sd` was estimated from data or inherited from `PUBLISHED_SD`.
    # Same purpose as `is_empirical`: a consumer must be able to tell a measured
    # number from a sourced one without inspecting `n`.
    sd_is_measured: bool = False

    def __post_init__(self) -> None:
        if self.sd is None:
            self.sd = published_sd(self.league)
        if self.sd <= 0:
            raise ValueError(
                f"{self.league}: standard deviation must be positive, got "
                f"{self.sd}. A zero-width distribution makes every cover "
                f"probability exactly 1.0 or 0.0."
            )

    @property
    def is_empirical(self) -> bool:
        """Whether there is enough data to trust the observed shape."""
        return self.n >= MIN_GAMES_FOR_EMPIRICAL

    @property
    def has_key_numbers(self) -> bool:
        return bool(KEY_NUMBERS.get(self.league))

    def fit(self, margins: Iterable[int]) -> "MarginDistribution":
        """Fit counts, mean and — only if the sample can support it — `sd`.

        The standard deviation is **not** overwritten from a sample too thin to
        estimate it. That is the whole subtlety: the `is_empirical` guard routes
        thin data away from the counts path and into a normal approximation, so
        if `fit` had already replaced `sd` with a thin-sample estimate, the guard
        would be routing around bad data into a fallback built from the same bad
        data. One observation would yield `sd = 0` and a certainty.
        """
        values = [int(m) for m in margins]
        if not values:
            raise ValueError("no margins provided")

        self.counts = Counter(values)
        self.n = len(values)
        self.mean = sum(values) / self.n

        measured: Optional[float] = None
        if self.n >= MIN_GAMES_FOR_SD:
            variance = sum((v - self.mean) ** 2 for v in values) / (self.n - 1)
            measured = math.sqrt(variance)

        if measured is not None and measured > 0:
            self.sd = measured
            self.sd_is_measured = True
        else:
            # Either too few games, or a degenerate sample where every margin is
            # identical. Both are reasons to keep the published width, and
            # neither is a reason to claim zero spread.
            self.sd = published_sd(self.league)
            self.sd_is_measured = False
            logger.warning(
                "%s: %s, so the published standard deviation %.1f is kept "
                "rather than estimated. Spread and total prices from this "
                "distribution carry a sourced width, not a measured one.",
                self.league,
                (
                    f"fitted on {self.n} games, below the {MIN_GAMES_FOR_SD} "
                    f"needed to estimate a width"
                    if measured is None
                    else f"all {self.n} margins are identical"
                ),
                self.sd,
            )

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
    """P(X > x) for a normal. Uses erf rather than a table.

    Refuses on a non-positive width rather than returning `1.0` or `0.0`. That
    branch used to exist and read as defensive, but a certainty is the single
    most dangerous number this module can emit: quarter-Kelly on `p = 1.0` sizes
    the whole bankroll, and the caller has no way to tell a real certainty from
    a degenerate fit. Clamp what you trust, refuse what you are validating.
    """
    if sigma <= 0:
        raise ValueError(
            f"normal survival needs a positive width, got sigma={sigma}. "
            f"A zero-width distribution yields a certainty, not a probability."
        )
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

    Explicitly **not** fitted, so `is_empirical` is False, `sd_is_measured` is
    False, and every consumer knows it is getting a smooth approximation with
    the key numbers absent. Present so the rest of the system can be built and
    tested before a historical results feed exists.
    """
    return MarginDistribution(league=league)
