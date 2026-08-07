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

What *changes* is that `kalshi_equivalent` is no longer the only way to express
a combination on Kalshi, and the honest comparison now has three columns: the
book's parlay, separate Kalshi contracts, and Kalshi's own combo. The third
needs a live quote — see `combos.lookup_combo`, which will not create a market
without being told to.

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

Building the same combination on Kalshi
---------------------------------------
You can replicate a parlay by buying each leg as a separate contract, and
`kalshi_equivalent` prices that. It is a *different bet* — legs settle
independently, so you can win two of three rather than losing everything — and
it pays a fee per leg. It is offered as a comparison, not as an equivalence.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Sequence

from .correlation import Leg, independence_error, joint_probability_all
from .fees import settlement_fee
from .prices import probability_to_tenths

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
        """Plain language, leading with the hold.

        The hold is the number that generalises: a bettor who learns that
        three-leg parlays at their book hold 24% has learned something durable,
        whereas "this one is -18% EV" is about one ticket.
        """
        hold_pct = self.hold * 100
        if self.is_positive_ev:
            return (
                f"Fair price {decimal_to_american(self.fair_decimal):+d}, book "
                f"offers {decimal_to_american(self.offered_decimal):+d}. "
                f"+{self.ev_per_dollar * 100:.1f}% EV. Rare -- verify the legs "
                f"are correctly matched before acting."
            )
        return (
            f"The book holds {hold_pct:.1f}% on this parlay. Fair price is "
            f"{decimal_to_american(self.fair_decimal):+d} against the offered "
            f"{decimal_to_american(self.offered_decimal):+d}, so this is "
            f"{self.ev_per_dollar * 100:.1f}% EV. Don't."
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


@dataclass(frozen=True)
class KalshiEquivalent:
    """Buying each leg separately on Kalshi. A different bet, priced for comparison."""

    legs: tuple[Leg, ...]
    total_cost_dollars: float
    total_fee_dollars: float
    all_win_probability: float
    payout_if_all_win: float
    expected_value_dollars: float
    fee_share_of_stake: float

    @property
    def note(self) -> str:
        return (
            "Not the same bet: on Kalshi the legs settle independently, so "
            "partial success pays partially rather than nothing. It also pays "
            f"a fee per leg -- {self.fee_share_of_stake:.1%} of stake here, "
            f"and fees peak at 50c."
        )


def kalshi_equivalent(
    legs: Sequence[Leg],
    *,
    contracts_per_leg: int = 100,
    correlation_overrides: Optional[dict[tuple[str, str], float]] = None,
) -> KalshiEquivalent:
    """Cost and EV of replicating a combination as separate Kalshi contracts.

    Priced at each leg's *fair* value, which is optimistic — in practice you
    pay the derived ask, which is worse. The comparison is meant to show the
    shape of the alternative, not to be a tradeable quote.
    """
    total_cost = 0.0
    total_fee = 0.0
    expected = 0.0

    for leg in legs:
        tenths = probability_to_tenths(leg.probability)
        cost = contracts_per_leg * (tenths / 1000.0)
        fee = settlement_fee(tenths, contracts_per_leg)
        if fee is None:
            raise ValueError(
                f"{leg.label}: probability {leg.probability} maps to {tenths} "
                f"tenths, which is not a tradeable price. A leg priced at a "
                f"settled outcome cannot be bought."
            )
        total_cost += cost
        total_fee += fee
        # Each leg is its own bet: EV is per-leg, not joint.
        expected += contracts_per_leg * leg.probability - cost - fee

    joint = joint_probability_all(legs, overrides=correlation_overrides)

    return KalshiEquivalent(
        legs=tuple(legs),
        total_cost_dollars=total_cost + total_fee,
        total_fee_dollars=total_fee,
        all_win_probability=joint,
        payout_if_all_win=contracts_per_leg * len(legs) * 1.0,
        expected_value_dollars=expected,
        fee_share_of_stake=total_fee / total_cost if total_cost else 0.0,
    )
