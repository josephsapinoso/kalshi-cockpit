"""Teasers — the one book-side edge with a documented basis.

A teaser moves every leg's spread in your favour by a fixed number of points in
exchange for a reduced payout. Ordinarily that trade is bad, in the same way a
parlay is bad: the book prices the points at more than they are worth.

The exception is the **Wong teaser**, and it exists because football margins are
lumpy. Roughly 15% of NFL games end with a margin of exactly 3 and 9% at exactly
7. A 6-point teaser applied to a favourite of −7.5 to −8.5 crosses *both* of
those numbers, and so does an underdog of +1.5 to +2.5 teased up. Those two
windows buy far more probability than six generic points, and that gap is the
edge.

Everything outside those windows is an ordinary teaser — a bad bet dressed up
as a strategy — and this module says so rather than quietly pricing it.

Why this needs `model/margins.py`
---------------------------------
A normal approximation smooths the spikes away and prices a point through 3
identically to a point through 11, which makes the entire effect invisible. So
teaser pricing **requires an empirical margin distribution**, and refuses when
it only has a smooth one. That refusal is the module working, not a gap.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Sequence

from ..model.margins import (
    MAX_TRANSLATION_POINTS,
    MarginDistribution,
    wong_candidate,
)
from .correlation import Leg, joint_probability_all

logger = logging.getLogger(__name__)

# Standard 6-point two-team teaser pricing at most US books. Roughly -120,
# meaning you risk $120 to win $100.
STANDARD_TWO_TEAM_DECIMAL = 1.833


class TeaserUnpriceable(ValueError):
    """Raised when the inputs cannot support an honest teaser price."""


@dataclass(frozen=True)
class TeasedLeg:
    team: str
    original_line: float
    points: float
    predicted_margin: float
    cover_probability: float
    event_key: str
    league: str
    commence_ms: int

    @property
    def teased_line(self) -> float:
        """Teasing always moves the line toward the bettor."""
        return self.original_line + self.points

    @property
    def crosses_key_numbers(self) -> tuple[int, ...]:
        low, high = sorted((self.original_line, self.teased_line))
        return tuple(k for k in (3, 7, 10, 14) if low < k < high or low < -k < high)

    @property
    def is_wong(self) -> bool:
        return wong_candidate(self.original_line, self.points)


@dataclass(frozen=True)
class TeaserValuation:
    legs: tuple[TeasedLeg, ...]
    fair_probability: float
    offered_decimal: float
    ev_per_dollar: float
    all_legs_are_wong: bool
    key_numbers_crossed: tuple[int, ...]

    @property
    def is_positive_ev(self) -> bool:
        return self.ev_per_dollar > 0

    @property
    def verdict(self) -> str:
        if not self.all_legs_are_wong:
            offenders = [leg.team for leg in self.legs if not leg.is_wong]
            return (
                f"Not a Wong teaser -- {', '.join(offenders)} "
                f"{'is' if len(offenders) == 1 else 'are'} outside the "
                f"-7.5/-8.5 and +1.5/+2.5 windows, so the points bought do not "
                f"cross both 3 and 7. This is an ordinary teaser: "
                f"{self.ev_per_dollar * 100:+.1f}% EV. Don't."
            )
        if self.is_positive_ev:
            return (
                f"Wong teaser crossing {self.key_numbers_crossed}. "
                f"{self.ev_per_dollar * 100:+.1f}% EV at the offered price. "
                f"This is the documented case -- confirm the lines are live "
                f"before acting, since the windows move."
            )
        return (
            f"Wong-shaped, crossing {self.key_numbers_crossed}, but priced "
            f"through: {self.ev_per_dollar * 100:+.1f}% EV. The edge exists "
            f"only when the book has not already adjusted for it."
        )


def build_leg(
    distribution: MarginDistribution,
    *,
    team: str,
    original_line: float,
    points: float,
    predicted_margin: float,
    event_key: str,
    league: str,
    commence_ms: int,
) -> TeasedLeg:
    """Price one teased leg from the empirical margin distribution.

    Two refusals, both about the same thing -- a teaser is only priceable if the
    key numbers are where the data says they are:

    1. A non-empirical distribution. A smooth fit prices the crossing of 3 and 7
       like any other points, which is exactly the information the teaser
       depends on.
    2. A distribution that would have to be dragged more than
       `MAX_TRANSLATION_POINTS` to reach this game. Translating relocates the
       spikes, so a league-wide fit slid onto an eight-point favourite prices a
       3-spike sitting at 11. That is not merely imprecise, it is worse than the
       normal approximation, because it looks like evidence.
    """
    if not distribution.is_empirical:
        raise TeaserUnpriceable(
            f"{distribution.league}: the margin distribution is not empirical "
            f"(fitted on {distribution.n} games). A smooth approximation prices "
            f"a point through 3 the same as a point through 11, which makes the "
            f"whole basis of a teaser invisible. Fit on real results first."
        )

    drag = distribution.translation_points(predicted_margin)
    if drag > MAX_TRANSLATION_POINTS:
        bucket = (
            "it is a league-wide fit"
            if distribution.spread_bucket is None
            else f"its bucket is centred on {distribution.spread_bucket:+g}"
        )
        raise TeaserUnpriceable(
            f"{team}: pricing a predicted margin of {predicted_margin:+.1f} "
            f"against a distribution with mean {distribution.mean:+.1f} drags "
            f"the fitted shape {drag:.1f} points, past the "
            f"{MAX_TRANSLATION_POINTS:g}-point limit -- {bucket}. That moves "
            f"the spikes at 3 and 7 to {3 + drag:.0f} and {7 + drag:.0f}, so "
            f"the empirical fit would price this game worse than a normal "
            f"curve while looking like data. Fit per spread bucket "
            f"(`margins.fit_by_spread`) and price from the matching one."
        )

    teased = original_line + points
    probability = distribution.probability_cover(
        teased, predicted_margin=predicted_margin
    )
    return TeasedLeg(
        team=team,
        original_line=original_line,
        points=points,
        predicted_margin=predicted_margin,
        cover_probability=probability,
        event_key=event_key,
        league=league,
        commence_ms=commence_ms,
    )


def value_teaser(
    legs: Sequence[TeasedLeg],
    *,
    offered_decimal: float = STANDARD_TWO_TEAM_DECIMAL,
    correlation_overrides: Optional[dict[tuple[str, str], float]] = None,
) -> TeaserValuation:
    """Value a multi-leg teaser.

    Legs go through the same correlation machinery as a parlay, so two legs of
    the same fixture are refused rather than multiplied.
    """
    if len(legs) < 2:
        raise ValueError("a teaser needs at least two legs")

    correlation_legs = [
        Leg(
            label=leg.team,
            probability=leg.cover_probability,
            event_key=leg.event_key,
            league=leg.league,
            commence_ms=leg.commence_ms,
        )
        for leg in legs
    ]
    fair = joint_probability_all(correlation_legs, overrides=correlation_overrides)

    crossed: set[int] = set()
    for leg in legs:
        crossed.update(leg.crosses_key_numbers)

    return TeaserValuation(
        legs=tuple(legs),
        fair_probability=fair,
        offered_decimal=offered_decimal,
        ev_per_dollar=fair * offered_decimal - 1.0,
        all_legs_are_wong=all(leg.is_wong for leg in legs),
        key_numbers_crossed=tuple(sorted(crossed)),
    )


def find_wong_candidates(
    available_lines: Sequence[tuple[str, float]], *, points: float = 6.0
) -> list[tuple[str, float]]:
    """Filter a slate to the legs that fit the Wong windows.

    `available_lines` is (team, spread). This is the screen that turns a full
    board into the two or three legs worth looking at, and it is deliberately
    strict: the whole documented effect lives in those narrow windows.
    """
    return [
        (team, line) for team, line in available_lines if wong_candidate(line, points)
    ]
