"""Position sizing: fractional Kelly, with caps that refuse rather than clamp.

Kelly maximises long-run growth **given a correct probability estimate**. Ours
is not correct — it is a conservative devig of a consensus that may itself be
stale. Full Kelly on an overestimated edge is how bankrolls die, so this sizes
at a fraction (default a quarter) and layers hard caps on top.

Three rules carried from `tasks/lessons.md`:

**Clamp what you trust; refuse what you're validating.** A size that exceeds a
cap is clamped down to the cap — that is a value we trust. A size computed from
*unreadable exposure* is refused outright. "Cannot determine the budget" must
never resolve to "unlimited".

**Minimum order size is a real risk control, not a nicety.** Under one
candidate fee model the fee rounds up on the whole order, so a scatter of tiny
orders pays the rounding penalty on every one. Below the minimum, the fee eats
the edge.

**Money is integer tenths of a cent in the risk path.** Float dollars produce
`7.350000000000001 > 7.35` rejections at exactly the wrong moment.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Optional

from ..config import RiskConfig
from .ev import effective_price, evaluate
from .prices import PRICE_MAX, is_valid_price, tenths_to_dollars

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SizingResult:
    """A sizing decision, with every constraint that shaped it recorded.

    `binding_constraint` is what actually determined the number. Without it,
    a sizing of 10 contracts is indistinguishable between "Kelly said so" and
    "the exposure cap said so", and those call for completely different
    responses.
    """

    contracts: int
    kelly_fraction_full: float      # unscaled Kelly, before the safety factor
    kelly_fraction_used: float      # after the safety factor
    stake_dollars: float
    binding_constraint: str
    refused: bool = False
    refusal_reason: Optional[str] = None

    @property
    def should_bet(self) -> bool:
        return not self.refused and self.contracts > 0


def full_kelly_fraction(fair_probability: float, price: float) -> float:
    """The unscaled Kelly fraction for a binary contract.

    A Kalshi contract costs `price` and returns $1.00 if it wins, so net odds
    are `b = (1 - price) / price`. Kelly is then `p - (1 - p) / b`.

    Returns 0.0 when the bet has no edge — negative Kelly means "bet the other
    side", which is a different decision and must not be expressed as a
    negative size here.
    """
    if not 0.0 < price < 1.0:
        return 0.0
    b = (1.0 - price) / price
    fraction = fair_probability - (1.0 - fair_probability) / b
    return max(0.0, fraction)


def size_position(
    *,
    side: str,
    ask_tenths: int,
    fair_probability: float,
    risk: RiskConfig,
    current_exposure_dollars: Optional[float],
    current_position_dollars: float = 0.0,
    daily_pnl_dollars: float = 0.0,
    maker: bool = False,
) -> SizingResult:
    """How many contracts to buy, or a refusal with a stated reason.

    `current_exposure_dollars` of `None` means exposure could not be read. That
    is a **refusal**, never an assumption of zero — treating unknown exposure as
    no exposure is how a risk cap silently becomes unlimited.
    """
    if not is_valid_price(ask_tenths):
        return _refuse(
            f"ask {ask_tenths} is not a tradeable price "
            f"(0 and {PRICE_MAX} are settled outcomes)"
        )

    if current_exposure_dollars is None:
        return _refuse(
            "current exposure is unreadable. Refusing to size a position "
            "against an unknown budget -- 'cannot determine' must not resolve "
            "to 'unlimited'."
        )

    if daily_pnl_dollars <= -abs(risk.max_daily_loss_dollars):
        return _refuse(
            f"daily loss limit reached ({daily_pnl_dollars:.2f} vs "
            f"-{risk.max_daily_loss_dollars:.2f}). Kill switch engaged."
        )

    # Size against the fee-inclusive price. Sizing on the raw ask and taking
    # the fee off afterwards overstates the edge, because the fee is part of
    # what you pay to acquire the position.
    price = effective_price(ask_tenths, contracts=1, maker=maker)
    if price >= 1.0:
        return _refuse(f"effective price {price:.4f} leaves nothing to win")

    full = full_kelly_fraction(fair_probability, price)
    if full <= 0.0:
        return SizingResult(
            contracts=0,
            kelly_fraction_full=full,
            kelly_fraction_used=0.0,
            stake_dollars=0.0,
            binding_constraint="no_edge",
        )

    used = full * risk.kelly_fraction
    stake = used * risk.bankroll_dollars

    # --- caps, in ascending order of how much they bind -------------------
    constraint = "kelly"

    room_in_position = max(0.0, risk.max_position_dollars - current_position_dollars)
    if stake > room_in_position:
        stake, constraint = room_in_position, "max_position_dollars"

    room_in_exposure = max(0.0, risk.max_exposure_dollars - current_exposure_dollars)
    if stake > room_in_exposure:
        stake, constraint = room_in_exposure, "max_exposure_dollars"

    contracts = int(stake // price) if price > 0 else 0

    if contracts > risk.max_order_contracts:
        contracts, constraint = risk.max_order_contracts, "max_order_contracts"

    # --- minimum order size ------------------------------------------------
    # Deliberately last, and it zeroes rather than rounds up. Rounding a
    # too-small order up to the minimum would spend more than the caps allow,
    # which is the one direction a risk control must never move.
    if 0 < contracts < risk.min_order_contracts:
        return SizingResult(
            contracts=0,
            kelly_fraction_full=full,
            kelly_fraction_used=used,
            stake_dollars=0.0,
            binding_constraint="below_min_order_contracts",
            refused=True,
            refusal_reason=(
                f"sized {contracts} contracts, below the {risk.min_order_contracts} "
                f"minimum. Fees round up on the whole order, so orders this "
                f"small pay a rounding penalty that exceeds the edge."
            ),
        )

    return SizingResult(
        contracts=contracts,
        kelly_fraction_full=full,
        kelly_fraction_used=used,
        stake_dollars=contracts * price,
        binding_constraint=constraint if contracts else "no_room",
    )


def _refuse(reason: str) -> SizingResult:
    logger.warning("sizing refused: %s", reason)
    return SizingResult(
        contracts=0,
        kelly_fraction_full=0.0,
        kelly_fraction_used=0.0,
        stake_dollars=0.0,
        binding_constraint="refused",
        refused=True,
        refusal_reason=reason,
    )


def verify_positive_after_fees(
    *,
    side: str,
    ask_tenths: int,
    contracts: int,
    fair_probability: float,
    maker: bool = False,
) -> bool:
    """Final check: is this specific order, at this size, actually +EV?

    Sizing uses a per-contract fee approximation; the real fee depends on the
    whole order. This re-evaluates at the size actually being sent, so an order
    that was marginal per-contract and negative in aggregate cannot slip
    through.
    """
    if contracts <= 0:
        return False
    result = evaluate(
        side=side,
        ask_tenths=ask_tenths,
        contracts=contracts,
        fair_probability=fair_probability,
        maker=maker,
    )
    return result.is_positive
