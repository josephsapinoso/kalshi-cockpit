"""Expected value of a Kalshi bet, at the price you would actually pay.

Two rules, both of which the previous project broke and paid for:

**Buy at the derived ask, never the mid.** Kalshi publishes YES bids and NO
bids; the ask is `1000 - opposing_bid`. One bucket in the previous project
showed a **+25.4 point edge while losing $4.92 a market**, because it was
bucketed on the mid and transacted at the ask. Every function here takes an ask.

**Net of fees, at the size actually being bet.** Fees round up on the whole
order under one candidate model, so EV per contract depends on how many
contracts. A per-contract EV computed independently of size is wrong for every
size except the one it was computed at.

A bet held to settlement pays **one** fee, not a round trip. That is the venue's
real advantage and it is why `settlement_fee` is the right call here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .fees import settlement_fee
from .prices import PRICE_MAX, is_valid_price, tenths_to_dollars


@dataclass(frozen=True)
class EVResult:
    """What a bet is worth, and everything needed to audit that number."""

    side: str
    ask_tenths: int
    contracts: int
    fair_probability: float

    gross_edge_tenths: float   # fair price minus what you pay, per contract
    fee_dollars: float
    cost_dollars: float        # total outlay including fee
    ev_dollars: float          # expected profit, net of fee
    breakeven_probability: float

    @property
    def is_positive(self) -> bool:
        return self.ev_dollars > 0

    @property
    def ev_per_contract_dollars(self) -> float:
        return self.ev_dollars / self.contracts if self.contracts else 0.0

    @property
    def roi(self) -> float:
        """Expected return on outlay. The comparable number across prices."""
        return self.ev_dollars / self.cost_dollars if self.cost_dollars else 0.0


def evaluate(
    *,
    side: str,
    ask_tenths: int,
    contracts: int,
    fair_probability: float,
    maker: bool = False,
) -> EVResult:
    """Expected value of buying `contracts` of `side` at `ask_tenths`.

    `fair_probability` is the probability that **this side** wins, and should
    normally be the conservative (lowest) devig reading -- see `core.devig`.

    Raises on an untradeable price rather than returning a zero-EV result: a
    price of 0 or 1000 is a settled outcome, and silently valuing a bet on a
    settled market at zero would hide the bug rather than surface it.
    """
    if side not in ("yes", "no"):
        raise ValueError(f"side must be 'yes' or 'no', got {side!r}")
    if not is_valid_price(ask_tenths):
        raise ValueError(
            f"ask {ask_tenths} is not a tradeable price. 0 and {PRICE_MAX} are "
            f"settled outcomes, not quotes."
        )
    if contracts <= 0:
        raise ValueError(f"contracts must be positive, got {contracts}")
    if not 0.0 <= fair_probability <= 1.0:
        raise ValueError(
            f"fair_probability {fair_probability} is outside [0, 1]"
        )

    price = tenths_to_dollars(ask_tenths)
    fee = settlement_fee(ask_tenths, contracts, maker)
    if fee is None:
        raise ValueError(
            f"no fee could be computed for ask {ask_tenths} tenths. Refusing "
            f"rather than treating it as free."
        )

    # Each contract settles at $1.00 if the side wins, $0 otherwise.
    payoff = contracts * fair_probability
    outlay = contracts * price
    ev = payoff - outlay - fee

    # The probability at which this bet exactly breaks even, fee included. It
    # is strictly above the raw price -- the fee is what separates them, and
    # that gap is the real hurdle.
    breakeven = (outlay + fee) / contracts

    return EVResult(
        side=side,
        ask_tenths=ask_tenths,
        contracts=contracts,
        fair_probability=fair_probability,
        gross_edge_tenths=(fair_probability * PRICE_MAX) - ask_tenths,
        fee_dollars=fee,
        cost_dollars=outlay + fee,
        ev_dollars=ev,
        breakeven_probability=breakeven,
    )


def effective_price(ask_tenths: int, contracts: int, *, maker: bool = False) -> float:
    """Price per contract in dollars, with the fee amortised in.

    This is the number Kelly should size against. Sizing on the raw ask and
    then subtracting the fee afterwards overstates the edge, because the fee is
    part of what you pay to acquire the position.

    Raises on an untradeable price rather than computing from a zero fee. The
    combination that motivates this: an ask of 0 tenths used to yield a 0.0 fee
    and an effective price of $0.00, which reports a breakeven win rate of 0%
    and an edge of +55c on a coin flip. Nothing downstream could tell that from
    a real opportunity.
    """
    if contracts <= 0:
        raise ValueError(f"contracts must be positive, got {contracts}")
    if not is_valid_price(ask_tenths):
        raise ValueError(
            f"ask {ask_tenths} tenths is not a tradeable price (0 and "
            f"{PRICE_MAX} are settled outcomes). Refusing rather than pricing "
            f"it at a zero fee, which fabricates an edge."
        )
    fee = settlement_fee(ask_tenths, contracts, maker)
    if fee is None:
        raise ValueError(f"no fee could be computed for ask {ask_tenths} tenths")
    return tenths_to_dollars(ask_tenths) + fee / contracts


def breakeven_win_rate(ask_tenths: int, contracts: int, *, maker: bool = False) -> float:
    """How often this bet must win to break even, fee included.

    At 50c this is the number that makes the venue interesting: ~51.75% as a
    taker and ~50.44% as a maker, against 52.38% at a -110 sportsbook. Kalshi
    lowers the bar; it does not clear it.
    """
    return effective_price(ask_tenths, contracts, maker=maker)


def edge_after_fees_tenths(
    *, ask_tenths: int, contracts: int, fair_probability: float, maker: bool = False
) -> float:
    """Edge per contract in tenths of a cent, after fees.

    The headline number on the Board. Positive means the fair price exceeds
    what you pay including the fee.
    """
    effective = effective_price(ask_tenths, contracts, maker=maker)
    return (fair_probability - effective) * PRICE_MAX
