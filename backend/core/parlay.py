"""Parlay pricing — using Kalshi and consensus to value the *book's* offer.

A correction, because this module was built on a false premise
--------------------------------------------------------------
This originally opened with "Kalshi has no parlay product", justified by the
predecessor finding that `/markets` is ~99.8% `KXMVE` with no volume. **That is
wrong.** `KXMVE` is Multi-Variate Event — Kalshi's combo builder, 1,389 live
collections and 13,806 legs at last count, including same-game parlays across
game, spread, total and player props. See `kalshi/combos.py`.

What survives the correction is this module's *usefulness*, for two reasons.
First, sportsbook parlays still need pricing and still hold 20–30%, so valuing
them against devigged consensus remains the right tool for the question "should
I take this ticket". Second, at capture time not one of those 13,806 Kalshi legs
had an active quoter — measured out of season, so weak evidence, but it means
the Kalshi combo is not yet a demonstrated alternative.

What *changes* is that separate Kalshi contracts are no longer the only way to
express a combination on Kalshi: Kalshi's own combo needs a live quote — see
`combos.lookup_combo`. (`kalshi_equivalent`, the separate-contracts pricer, was
deleted with the `/api/builder/*` routes, #332.)

So this module keeps its framing: **the devigged consensus is the fair-price
engine, and the thing being priced is the sportsbook's parlay.**

The honest expectation is that the answer is almost always "don't". Book
parlays typically hold 20-30% against a 4-5% hold on the straight lines that
compose them — the parlay is where a book makes its margin back. Saying that
clearly, with the number attached, is the useful output. A tool that only ever
surfaced the rare good parlay would be silent 99% of the time and give no sense
of *why*.

Two things this module refuses to do:

- Price same-game legs from marginals. `core.correlation` raises instead.
- Report a parlay as +EV without showing the independence error alongside,
  because for correlated legs that error is frequently larger than the entire
  claimed edge.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from .correlation import Leg, independence_error, joint_probability_all

logger = logging.getLogger(__name__)


def american_to_decimal(american: int) -> float:
    """American odds to decimal. Parlays are almost always quoted American."""
    if american == 0:
        raise ValueError("0 is not valid American odds")
    if american > 0:
        return 1.0 + american / 100.0
    return 1.0 + 100.0 / abs(american)


def decimal_to_american(decimal: float) -> int:
    if decimal <= 1.0:
        raise ValueError(f"decimal odds {decimal} must exceed 1.0")
    if decimal >= 2.0:
        return round((decimal - 1.0) * 100)
    return round(-100.0 / (decimal - 1.0))


@dataclass(frozen=True)
class ParlayQuote:
    """What a book offers on a combination."""

    legs: tuple[Leg, ...]
    offered_decimal: float

    @property
    def offered_american(self) -> int:
        return decimal_to_american(self.offered_decimal)


@dataclass(frozen=True)
class ParlayValuation:
    legs: tuple[Leg, ...]
    fair_probability: float
    naive_probability: float
    independence_error_points: float
    fair_decimal: float
    offered_decimal: float
    hold: float                # the book's margin on this specific parlay
    ev_per_dollar: float
    correlation_was_supplied: bool

    @property
    def is_positive_ev(self) -> bool:
        return self.ev_per_dollar > 0

    @property
    def verdict(self) -> str:
        """The per-row fact in cents, with no verdict word.

        Kalshi's ask against the books' fair value, and the hold -- the numbers
        the tiles already carry. No verdict word: ADR 0071 section 2.1 (the
        desk informs, it does not abstain on his behalf) and ADR 0046 (a
        fee-net figure on a combination overstates by construction). The hold
        is the number that generalises across tickets.
        """
        ask_cents = 100.0 / self.offered_decimal
        fair_cents = 100.0 / self.fair_decimal
        return (
            f"Kalshi's ask is {ask_cents:.1f}c against the books' fair value "
            f"of {fair_cents:.1f}c; hold {self.hold * 100:.1f}%."
        )


def value_parlay(
    quote: ParlayQuote,
    *,
    correlation_overrides: Optional[dict[tuple[str, str], float]] = None,
) -> ParlayValuation:
    """Value one parlay against devigged consensus.

    Raises `CorrelationRefused` on same-game legs without an override, rather
    than returning a number that assumes independence.
    """
    legs = tuple(quote.legs)
    if len(legs) < 2:
        raise ValueError("a parlay needs at least two legs")

    fair_probability = joint_probability_all(
        legs, overrides=correlation_overrides
    )
    naive = 1.0
    for leg in legs:
        naive *= leg.probability

    fair_decimal = 1.0 / fair_probability
    # Hold: how much of the fair payout the book keeps.
    hold = 1.0 - (fair_probability * quote.offered_decimal)
    ev_per_dollar = fair_probability * quote.offered_decimal - 1.0

    return ParlayValuation(
        legs=legs,
        fair_probability=fair_probability,
        naive_probability=naive,
        independence_error_points=independence_error(
            legs, overrides=correlation_overrides
        ),
        fair_decimal=fair_decimal,
        offered_decimal=quote.offered_decimal,
        hold=hold,
        ev_per_dollar=ev_per_dollar,
        correlation_was_supplied=bool(correlation_overrides),
    )
