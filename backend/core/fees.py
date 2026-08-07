"""Kalshi trading fee model.

Kalshi charges a probability-weighted fee that peaks at the 50c contract and
decays symmetrically toward both ends of the board. **A bet held to settlement
pays this fee once.** Trading pays it twice (buy + sell). Settlement is not a
trade, which is why the maths is friendlier for betting than for trading.

Ported from ``kalshi_orderbook_monitor/fees.py`` with two deliberate changes,
both documented below: the price argument is now integer **tenths of a cent**
rather than whole cents, and the public entry point returns the most expensive
of several plausible fee models rather than committing to one.

Provenance, and why this module hedges
--------------------------------------
Kalshi's official fee schedule at ``kalshi.com/docs/kalshi-fee-schedule.pdf``
returns HTTP 429 to automated fetches. It did so when the original module was
written and it still does. So the coefficients come from secondary sources --
and as of the July 2026 revision **those sources disagree with each other**:

  Model A (pm.wiki, predictreport.io, thelines.com):
      fee = roundup_to_cent( 0.07 x C x P x (1 - P) )
      -- one coefficient for all categories, rounded UP on the whole ORDER.

  Model B (predictionhunt.com, reporting the July 2026 revision):
      fee_per_contract = round_to_nearest_cent( 0.06 x P x (1 - P) )
      fee = C x fee_per_contract
      -- a per-CATEGORY multiplier (~0.06 for sports), rounded to NEAREST
         cent PER CONTRACT.

These are not a rounding detail apart. At 50c on 100 contracts Model A charges
$1.75 and Model B charges $2.00, because per-contract rounding lifts 1.5c to
2c. At 20c the ordering reverses: A charges $1.12 and B charges $1.00. Neither
dominates, and the gap between them is the same order of magnitude as the edge
this project is hunting.

**So ``calculate_fee`` returns the maximum across all candidate models.** An
overstated fee makes a marginal bet look worse than it is, which costs you a
bet you might have won. An understated fee makes a losing bet look profitable,
which costs you money and -- worse -- corrupts the measurement record that the
whole project depends on. The asymmetry is not close.

Closing this out
----------------
This hedge is temporary and self-resolving. Every fill returned by
``/portfolio/fills`` reports the fee Kalshi actually charged. ``fee_candidates``
exists so that the calibration harness can compare each model against real
fills and identify which one is true. Once a model is confirmed on a
statistically adequate sample, replace this with that model and delete the
hedge. Until then, treat any ``fee_predicted != fee_actual`` as stop-the-line.

Consequences worth internalising before trusting any backtest
-------------------------------------------------------------
- The fee peaks at the 50c contract and is symmetric: a 10c contract and a 90c
  contract cost the same. In *percentage* terms cheap contracts are therefore
  the most expensive. Buying longshots because you can hold more of them is the
  worst corner of the fee curve.
- Under Model A, rounding applies to the whole order, so fees are meaningfully
  cheaper per contract on larger orders. This is why a minimum order size is a
  real risk control and not a nicety -- see ``core.sizing``.
- A round trip pays the fee twice. Near 50c that is ~3.5c, which exceeds the
  2-5c edges this venue offers. Any strategy whose entire edge is a 3c spread
  is net-negative before it starts. Holding to settlement avoids this.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from typing import Optional

from .prices import PRICE_MAX, is_valid_price

# Model A: single coefficient, per-order round-up. Maker is one quarter of taker.
TAKER_COEFFICIENT = Decimal("0.07")
MAKER_COEFFICIENT = Decimal("0.0175")

# Model B: per-category multiplier, per-contract round-to-nearest. The sports
# multiplier is the one that matters here; other categories are not modelled.
SPORTS_MULTIPLIER = Decimal("0.06")
SPORTS_MAKER_MULTIPLIER = SPORTS_MULTIPLIER / Decimal(4)

_ONE_CENT = Decimal("0.01")
_PRICE_MAX_DEC = Decimal(PRICE_MAX)


def _price_dollars(price_tenths: int) -> Decimal:
    """Exact dollar price from integer tenths of a cent. 240 -> 0.24."""
    return Decimal(price_tenths) / _PRICE_MAX_DEC


def _model_a(price_tenths: int, contracts: int, maker: bool) -> Decimal:
    """Single coefficient, rounded up to the cent on the whole order."""
    coefficient = MAKER_COEFFICIENT if maker else TAKER_COEFFICIENT
    price = _price_dollars(price_tenths)
    raw = coefficient * Decimal(contracts) * price * (Decimal(1) - price)
    return raw.quantize(_ONE_CENT, rounding=ROUND_CEILING)


def _model_b(price_tenths: int, contracts: int, maker: bool) -> Decimal:
    """Sports multiplier, rounded to the nearest cent per individual contract.

    The per-contract rounding is what makes this model expensive on large
    orders and cheap on small ones: a sub-half-cent per-contract fee rounds to
    zero, while anything above rounds up to a full cent each.
    """
    multiplier = SPORTS_MAKER_MULTIPLIER if maker else SPORTS_MULTIPLIER
    price = _price_dollars(price_tenths)
    per_contract = (multiplier * price * (Decimal(1) - price)).quantize(
        _ONE_CENT, rounding=ROUND_HALF_UP
    )
    return per_contract * Decimal(contracts)


def fee_candidates(
    price_tenths: int, contracts: int, maker: bool = False
) -> dict[str, float]:
    """Every plausible fee model, in dollars, keyed by name.

    Used by the fill-calibration harness to work out which model Kalshi is
    actually running. Not for pricing decisions -- use :func:`calculate_fee`.
    """
    if contracts <= 0 or not is_valid_price(price_tenths):
        return {"model_a_per_order_roundup": 0.0, "model_b_per_contract_nearest": 0.0}

    return {
        "model_a_per_order_roundup": float(_model_a(price_tenths, contracts, maker)),
        "model_b_per_contract_nearest": float(_model_b(price_tenths, contracts, maker)),
    }


def calculate_fee(price_tenths: int, contracts: int, maker: bool = False) -> Optional[float]:
    """Return the Kalshi fee for an order, in dollars.

    Returns the **most expensive** plausible model. See the module docstring
    for why, and for how this hedge gets retired.

    Args:
        price_tenths: Execution price in integer tenths of a cent, 1-999.
            Prices of 0 or 1000 are settled outcomes, not quotes, and incur no
            fee. Note this differs from the original module, which took whole
            cents -- roughly a quarter of Kalshi markets use deci-cent ticks,
            so whole cents would misprice the fee on those markets.
        contracts: Number of contracts in the order.
        maker: True for a resting (maker) order, False for a marketable
            (taker) order.

    Returns:
        Fee in dollars (>= 0.0), or **None** when the price is not tradeable.

    `None`, not `0.0`, and that distinction is the module's most important
    behaviour. An earlier version returned `0.0` for an unreadable or settled
    price, which is this project's own "unreadable must never resolve to zero"
    rule broken in the one place it costs the most: a zero fee on a zero-cost
    ask produces an edge of +55c out of nothing, and a fabricated edge that
    large is exactly what the suppression layer exists to catch -- except it
    arrives already looking legitimate. Callers must refuse rather than
    substitute.
    """
    if contracts <= 0:
        return 0.0
    if not is_valid_price(price_tenths):
        return None

    return max(fee_candidates(price_tenths, contracts, maker).values())


def calculate_fee_cents(
    price_tenths: int, contracts: int, maker: bool = False
) -> Optional[int]:
    """Same as :func:`calculate_fee` but returns whole cents, or None."""
    fee = calculate_fee(price_tenths, contracts, maker)
    return None if fee is None else int(round(fee * 100))


def round_trip_fee(entry_tenths: int, exit_tenths: int, contracts: int) -> float:
    """Total taker fees for entering and exiting a position, in dollars.

    Use this when deciding whether an edge survives costs on a strategy that
    trades out rather than holding. A bet held to settlement pays
    :func:`calculate_fee` once, not this.
    """
    return calculate_fee(entry_tenths, contracts) + calculate_fee(exit_tenths, contracts)


def breakeven_edge_cents(price_tenths: int, contracts: int) -> float:
    """Minimum favourable price move (in cents/contract) to break even on a round trip.

    Answers "how many cents does this trade have to move my way before fees
    stop eating it?" Assumes entry and exit at roughly the same price level,
    which is the right approximation for thin edges.
    """
    if contracts <= 0:
        return 0.0
    total_fee_dollars = round_trip_fee(price_tenths, price_tenths, contracts)
    return total_fee_dollars * 100.0 / contracts


def settlement_fee(
    price_tenths: int, contracts: int, maker: bool = False
) -> Optional[float]:
    """Total fees for a bet held to settlement, in dollars, or None.

    This is the number that matters for this project. Settlement is not a
    trade, so there is exactly one fee: the one paid on entry. Named
    explicitly so no call site has to remember that.

    Returns `None` on an untradeable price, for the reason in
    :func:`calculate_fee` -- a zero fee there manufactures an edge.
    """
    return calculate_fee(price_tenths, contracts, maker)


# How far `fee_actual` may sit from `fee_predicted` before the gate calls it a
# mismatch.
#
# **Float noise only, not a business tolerance.** Kalshi charges whole cents and
# `calculate_fee` returns dollars, so a correct model matches the fill exactly;
# any real difference means the formula is wrong. The previous value was `0.005`
# -- half a cent, absolute -- which on a one-contract fill let a model be **50%
# wrong** and still pass the check the gate treats as stop-the-line. The
# tolerance was larger than the quantity being checked.
#
# Absolute rather than relative on purpose: the failure mode is a wrong formula,
# which shows up at every size, and a relative tolerance would forgive exactly
# the small fills where the fee is largest as a share of stake.
FEE_MATCH_TOLERANCE_DOLLARS = 1e-9
