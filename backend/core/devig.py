"""Removing the bookmaker's margin to recover a fair probability.

A bookmaker's implied probabilities sum to more than 1. The excess is the
overround (the vig), and devigging is the act of scaling it back out. There is
no single correct way to do it, because the true allocation of margin across
outcomes is unobservable.

**The spread between methods depends sharply on the shape of the line**, and
measuring it changed how much this matters. On a near-even MLB moneyline
(2.10 / 1.80, 3.2% hold) the four methods agree to within **0.18 percentage
points**. On a lopsided line (1.11 / 7.50) they spread **2.03 points** -- more
than three times Kalshi's entire 0.6-point fee advantage over a -110
sportsbook.

So method choice is a modelling detail on even lines and a potential source of
entirely fictitious edge on longshots. That compounds with the fee curve, which
is *also* at its worst in percentage terms on cheap contracts. Two independent
reasons to distrust a longshot edge, both measured rather than assumed.

All four methods are computed, all four are stored, and money decisions use the
**most conservative** of them.

The four methods
----------------
**Multiplicative** divides each raw probability by the booksum. Simple, and the
usual default, but it assumes margin is spread proportionally -- which
overstates longshots, because books load more margin onto them.

**Additive** subtracts the excess equally across outcomes. Corrects the
favourite-longshot bias in the opposite direction, and can drive a heavy
longshot's probability negative.

**Power** solves for `k` with `sum(p_i**k) == 1`. Sits between the two and
keeps every result inside (0, 1) by construction. The best general default when
you must pick one.

**Shin** models the margin as the book's protection against insider betting,
solving for an implied insider fraction `z`. Well-founded in the literature and
usually the closest to sharp closing lines on two-outcome markets.

Conservative selection
----------------------
`conservative_probability` returns the **lowest** fair probability across
methods for the side being bought. Lower fair probability means less edge, so
this is the reading least likely to talk you into a bet. Combined with buying
at the derived ask (never the mid) and subtracting fees, that is three
independent layers of pessimism -- deliberately, because every error in the
previous project made results look better than they were.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Optional, Sequence

from scipy.optimize import brentq

logger = logging.getLogger(__name__)

# Below this, floating-point noise dominates and every method agrees anyway.
_MIN_OVERROUND = 1e-9
_EPS = 1e-12


class DevigError(ValueError):
    """The input cannot be devigged. Raised rather than returning a guess."""


def implied_probabilities(decimal_odds: Sequence[float]) -> list[float]:
    """Raw implied probabilities from decimal odds. Vig still included."""
    if not decimal_odds:
        raise DevigError("no odds provided")
    for odds in decimal_odds:
        if odds <= 1.0:
            raise DevigError(
                f"decimal odds {odds} imply a probability >= 1. Almost always "
                f"American odds in a decimal field -- and it reads as enormous edge."
            )
    return [1.0 / o for o in decimal_odds]


def overround(probs: Sequence[float]) -> float:
    """How much the book's probabilities exceed 1. This is the margin."""
    return sum(probs) - 1.0


def _validate(probs: Sequence[float]) -> None:
    if len(probs) < 2:
        raise DevigError(f"need at least 2 outcomes, got {len(probs)}")
    if any(p <= 0 for p in probs):
        raise DevigError(f"all probabilities must be positive, got {list(probs)}")
    if sum(probs) <= 1.0:
        # A book with no margin, or crossed odds. Not devigged -- if the sum is
        # already at or below 1 there is nothing to remove, and scaling *up*
        # would invent probability.
        raise DevigError(
            f"booksum is {sum(probs):.4f} <= 1, so there is no margin to remove. "
            f"Scaling up would invent probability rather than recover it."
        )


def multiplicative(probs: Sequence[float]) -> list[float]:
    """Divide out the booksum. Overstates longshots."""
    _validate(probs)
    total = sum(probs)
    return [p / total for p in probs]


def additive(probs: Sequence[float]) -> list[float]:
    """Subtract the excess equally.

    Can push a heavy longshot negative -- the result is clamped to a tiny
    positive and logged, because a negative probability is a signal that this
    method does not fit this market, not something to silently zero.
    """
    _validate(probs)
    excess = overround(probs) / len(probs)
    out = []
    for p in probs:
        adjusted = p - excess
        if adjusted <= 0:
            logger.debug(
                "additive devig drove %.4f negative (excess %.4f); clamping. "
                "This method does not fit this market.",
                p, excess,
            )
            adjusted = _EPS
        out.append(adjusted)
    return out


def power(probs: Sequence[float]) -> list[float]:
    """Solve for `k` with `sum(p**k) == 1`. Stays inside (0, 1) by construction."""
    _validate(probs)

    def residual(k: float) -> float:
        return sum(p**k for p in probs) - 1.0

    try:
        # k > 1 shrinks every p (each is < 1), so the sum decreases in k. The
        # root is bracketed between no adjustment and a very heavy one.
        k = brentq(residual, 1.0, 100.0, xtol=1e-12, maxiter=200)
    except (ValueError, RuntimeError) as exc:
        raise DevigError(f"power devig failed to converge: {exc}") from exc
    return [p**k for p in probs]


def shin(probs: Sequence[float]) -> list[float]:
    """Shin's insider-trading model. Solves for the insider fraction `z`.

    Degenerates to multiplicative as `z -> 0`, which is the natural sanity
    check: no insiders means margin is proportional.
    """
    _validate(probs)
    total = sum(probs)

    def recovered(z: float) -> list[float]:
        # No special case at z = 0. An earlier version short-circuited to
        # p/total there, which is a *different* formula that sums to exactly
        # 1 -- so residual(0) was 0, brentq returned z = 0 immediately, and
        # Shin silently returned multiplicative for every market. The formula
        # below is well-defined at z = 0 (it gives p/sqrt(total), summing to
        # sqrt(total) > 1), which is what makes the root-find meaningful.
        return [
            (math.sqrt(z * z + 4.0 * (1.0 - z) * p * p / total) - z) / (2.0 * (1.0 - z))
            for p in probs
        ]

    def residual(z: float) -> float:
        return sum(recovered(z)) - 1.0

    try:
        # z is a proportion of informed money, so it lives in [0, 1). The upper
        # bracket stays clear of the singularity at z = 1.
        z = brentq(residual, 0.0, 0.9999, xtol=1e-12, maxiter=200)
    except (ValueError, RuntimeError):
        # No root in range -- fall back to multiplicative, which is Shin's own
        # z -> 0 limit, and say so rather than silently substituting.
        logger.debug("shin devig found no root; falling back to its z->0 limit")
        return multiplicative(probs)

    return recovered(z)


@dataclass(frozen=True)
class DevigResult:
    """All four readings for one market, plus the conservative selection."""

    outcomes: tuple[str, ...]
    raw_probabilities: tuple[float, ...]
    multiplicative: tuple[float, ...]
    additive: tuple[float, ...]
    power: tuple[float, ...]
    shin: tuple[float, ...]
    overround: float

    def all_methods(self) -> dict[str, tuple[float, ...]]:
        return {
            "multiplicative": self.multiplicative,
            "additive": self.additive,
            "power": self.power,
            "shin": self.shin,
        }

    def index_of(self, outcome: str) -> int:
        try:
            return self.outcomes.index(outcome)
        except ValueError as exc:
            raise DevigError(
                f"{outcome!r} is not one of {list(self.outcomes)}"
            ) from exc

    def conservative_probability(self, outcome: str) -> float:
        """The **lowest** fair probability across methods for this outcome.

        Lower fair probability means less edge, so this is the reading least
        likely to talk you into a bet.
        """
        i = self.index_of(outcome)
        return min(values[i] for values in self.all_methods().values())

    def method_spread(self, outcome: str) -> float:
        """Max minus min across methods, in probability points.

        **This is a suppression input, not a curiosity.** When the four methods
        disagree by more than the edge being claimed, the "edge" is a statement
        about method choice rather than about the market.
        """
        i = self.index_of(outcome)
        values = [v[i] for v in self.all_methods().values()]
        return max(values) - min(values)


def devig(
    outcomes: Sequence[str], decimal_odds: Sequence[float]
) -> DevigResult:
    """Devig one market every way, keeping all of them."""
    if len(outcomes) != len(decimal_odds):
        raise DevigError(
            f"{len(outcomes)} outcomes but {len(decimal_odds)} prices"
        )
    probs = implied_probabilities(decimal_odds)
    _validate(probs)

    return DevigResult(
        outcomes=tuple(outcomes),
        raw_probabilities=tuple(probs),
        multiplicative=tuple(multiplicative(probs)),
        additive=tuple(additive(probs)),
        power=tuple(power(probs)),
        shin=tuple(shin(probs)),
        overround=overround(probs),
    )


def consensus_devig(
    outcomes: Sequence[str],
    quotes_by_book: dict[str, Sequence[float]],
    *,
    sharp_books: Optional[frozenset[str]] = None,
) -> tuple[DevigResult, dict]:
    """Devig each book separately, then take the consensus.

    Devigging each book *before* averaging is the right order: books carry
    different margins, so averaging raw prices first would blend a 2% book with
    a 6% book and produce a fair line that belongs to neither.

    Prefers sharp books when any are present -- they take size from
    professionals and move first. Returns the consensus alongside metadata the
    suppression layer needs: how many books, which ones, and how far apart they
    were.
    """
    if not quotes_by_book:
        raise DevigError("no books provided")

    usable: dict[str, DevigResult] = {}
    for book, odds in quotes_by_book.items():
        try:
            usable[book] = devig(outcomes, odds)
        except DevigError as exc:
            logger.debug("skipping %s: %s", book, exc)

    if not usable:
        raise DevigError("no book produced a usable fair price")

    sharp = {b: r for b, r in usable.items() if sharp_books and b in sharp_books}
    selected = sharp or usable

    n = len(outcomes)
    averaged = {
        method: tuple(
            sum(r.all_methods()[method][i] for r in selected.values()) / len(selected)
            for i in range(n)
        )
        for method in ("multiplicative", "additive", "power", "shin")
    }

    # Width across books on the first outcome, using multiplicative as a
    # common yardstick. A wide market means the fair line is untrustworthy.
    first_values = [r.multiplicative[0] for r in selected.values()]
    market_width = max(first_values) - min(first_values) if len(first_values) > 1 else 0.0

    consensus = DevigResult(
        outcomes=tuple(outcomes),
        raw_probabilities=tuple(
            sum(r.raw_probabilities[i] for r in selected.values()) / len(selected)
            for i in range(n)
        ),
        multiplicative=averaged["multiplicative"],
        additive=averaged["additive"],
        power=averaged["power"],
        shin=averaged["shin"],
        overround=sum(r.overround for r in selected.values()) / len(selected),
    )

    metadata = {
        "book_count": len(selected),
        "books_used": sorted(selected),
        "anchored_on_sharp": bool(sharp),
        "market_width": market_width,
        "books_rejected": sorted(set(quotes_by_book) - set(usable)),
    }
    return consensus, metadata
