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

**The exit condition above has now been met, and NEITHER MODEL IS TRUE.**
-----------------------------------------------------------------------
Measured 2026-08-10 and 2026-08-14 against 11 real taker fills
(``/portfolio/fills``) plus 59 settlement records (``/portfolio/settlements``).
Full result and its audit:
``docs/measurements/2026-08-14-fee-rate-attribution-round-three-result.md``.
Re-derive with ``scripts/reconcile_observed_fees.py``.

**The coefficient is not a venue constant.** On 9 fills across ``KXMLBGAME``
and ``KXMLBSPREAD`` -- 6 markets, 5 events, 2 dates, ``C in {0.27, 1, 10, 20}``,
``P in {13, 27, 48, 52}c``, all taker, all buy-yes, all pre-game -- the charged
fee is exactly ``ceil(k * C * P * (1-P))`` to **$0.0001, per order**, with ``k``
pinned to ``(0.034969, 0.035008]``. On the 2 non-baseball fills in the same
window (``KXATPDOUBLES`` 20 @ 15c, ``KXWNBAGAME`` 1 @ 28c) the same form holds
with ``k`` pinned to ``(0.069961, 0.070000]``. The intervals are disjoint. No
single function of ``(C, P)`` fits both groups, because fee-per-contract is
non-monotone in ``P(1-P)``.

**THE LARGER DEFECT BELOW IS GRANULARITY, NOT THE COEFFICIENT.** ``_model_a``
rounds to the cent; Kalshi charges single-game fees to $0.0001 as of 2026-08.
``calculate_fee`` currently overcharges these fills by **2.03x-2.90x on baseball
and 1.12x-1.41x on non-baseball**. Changing ``TAKER_COEFFICIENT`` alone leaves
baseball ~1.45x wrong at 27c, and ``_model_b`` would often win the ``max()``
anyway. **Fix granularity first, and separately.**

**What this does NOT establish, and no reader may infer any of it:**

1. **Which market attribute carries the split.** Sport, series, and a per-market
   liquidity or maker-programme tier all fit these rows identically; the two
   high-rate observations are the only fills in their series. The
   pre-registration's §10 forbids pooling across categories.
2. **Durability.** The ``k = 0.035`` observations span **four days**. This
   account's settlement record shows 11 of 11 single-game fees from 2025-11-27
   to 2026-02-09 charged at ``k = 0.07`` rounded to the **whole cent** -- so the
   sports schedule was revised at least once in the preceding six months, and a
   promotional or temporary MLB rate is **not excluded**. There is no MLB
   observation under the old schedule.
3. Any rate at 16-26c, above 52c, at sizes 2-19 or above 20, on the **maker**
   side, in-game, on a baseball series other than these two, or on combos.

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

from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP
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

# The grid Kalshi rounds the charge onto. **Was `_ONE_CENT` until 2026-08-14**,
# which reproduced 11 of 11 single-game settlements dated 2025-11-27 to
# 2026-02-09 and **0 of 11 fills dated 2026-08-10 or later**. The schedule was
# revised in between; this is the current grid, measured, not sourced.
#
# `_ONE_CENT` is kept above because `_model_b` is still expressed on it -- see
# the note on that function -- and because the old grid is the evidence that a
# revision happened.
FEE_GRID_DOLLARS = Decimal("0.0001")
_PRICE_MAX_DEC = Decimal(PRICE_MAX)


def _price_dollars(price_tenths: int) -> Decimal:
    """Exact dollar price from integer tenths of a cent. 240 -> 0.24."""
    return Decimal(price_tenths) / _PRICE_MAX_DEC


def _exact_count(contracts: float) -> Optional[Decimal]:
    """The contract count as an exact Decimal, or None for garbage.

    Through `str`, never `Decimal(float)` directly: `Decimal(0.27)` carries
    the float's binary noise (0.2700000000000000155...) into arithmetic that
    is then quantized on a $0.0001 grid the venue actually charges on.
    Fractional counts are REAL positions (0.27 observed on this account) and
    are accepted exactly -- defect D1 of the 2026-08-18 fee calibration chose
    accept-exact over refuse, because `fills.fee_predicted` is NOT NULL and a
    refusal would cost the mirror a real fill on an endpoint that drops
    history. Only unreadable garbage (NaN, inf) refuses.
    """
    try:
        count = Decimal(str(contracts))
    except (InvalidOperation, ValueError):
        return None
    if not count.is_finite():
        return None
    return count


def _model_a(price_tenths: int, contracts: Decimal, maker: bool) -> Decimal:
    """Single coefficient, rounded up to `FEE_GRID_DOLLARS` on the whole order.

    **This is the observed model**, not a candidate. On 11 real taker fills the
    charged fee is exactly `ceil(k * C * P * (1-P))` to $0.0001 per order. The
    only thing still hedged is `k`: baseball measured `(0.034969, 0.035008]`,
    the two non-baseball fills `(0.069961, 0.070000]`, and `TAKER_COEFFICIENT`
    stays at the **higher** of the two deliberately -- see `calculate_fee`.
    """
    coefficient = MAKER_COEFFICIENT if maker else TAKER_COEFFICIENT
    price = _price_dollars(price_tenths)
    raw = coefficient * contracts * price * (Decimal(1) - price)
    return raw.quantize(FEE_GRID_DOLLARS, rounding=ROUND_CEILING)


def _model_a_pre_july_2026(price_tenths: int, contracts: int, maker: bool) -> Decimal:
    """The superseded whole-cent form, retained as evidence, not for pricing.

    Reproduces 11 of 11 single-game settlements from 2025-11-27 to 2026-02-09 at
    `k = 0.07`, and 0 of 11 fills from 2026-08-10 on. Kept so that "the schedule
    changed" is a claim this module can still demonstrate rather than assert.
    **No production caller. Do not price with it.**
    """
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
        "model_a_per_order_roundup": float(
            _model_a(price_tenths, _exact_count(contracts), maker)
        ),
        "model_b_per_contract_nearest": float(_model_b(price_tenths, contracts, maker)),
    }


def calculate_fee(
    price_tenths: int, contracts: float, maker: bool = False
) -> Optional[float]:
    """Return the Kalshi fee for an order, in dollars.

    Returns the **measured** model (`_model_a`): `ceil(k * C * P * (1-P))` to
    $0.0001, per order. See the module docstring for the 11 fills that pin it.

    **`TAKER_COEFFICIENT` stays at 0.07 and that is deliberate, not an
    oversight.** Baseball measured `k = 0.035`, but *which* market attribute
    carries that split is unresolved -- sport, series, and a per-market
    liquidity tier all fit the observations identically -- and the whole
    `k = 0.035` record spans **four days** on a venue whose schedule demonstrably
    changed within the preceding six months. So this function charges the
    **higher** measured rate everywhere. On the observed fills that is exact on
    non-baseball and exactly 2.00x on baseball: never under, which is the
    direction the module has always chosen, and now overstating by a known
    factor rather than an unknown one.

    Hardcoding 0.035 needs a second MLB observation window >= 3-4 weeks after
    2026-08-14, and a series argument this signature does not take.

    Args:
        price_tenths: Execution price in integer tenths of a cent, 1-999.
            Prices of 0 or 1000 are settled outcomes, not quotes, and incur no
            fee. Note this differs from the original module, which took whole
            cents -- roughly a quarter of Kalshi markets use deci-cent ticks,
            so whole cents would misprice the fee on those markets.
        contracts: Number of contracts in the order. Fractional counts are
            real (0.27 observed on this account) and are computed EXACTLY,
            via `Decimal(str(...))` -- defect D1: the old `contracts: int`
            hint invited `int(0.27)` at a call site, which is 0, which is a
            real position's fee reported as free. NaN/inf refuse with None.
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
    count = _exact_count(contracts)
    if count is None:
        return None
    if count <= 0:
        return 0.0
    if not is_valid_price(price_tenths):
        return None

    # **The hedge is retired.** This was `max(fee_candidates(...).values())`
    # until 2026-08-14. Model B -- per-category multiplier, rounded to the
    # NEAREST CENT per contract -- is refuted: it matches **0 of 11** real
    # fills, and it is wrong in *form*, not just in granularity, because the
    # observed charge lands on a $0.0001 grid that per-contract cent rounding
    # cannot produce. Keeping a refuted model inside a `max()` is not caution;
    # it is a wrong number wearing conservatism's clothes. It kept the charge at
    # 1.12x-2.53x the truth *after* the granularity fix, because B won three of
    # the eleven rows outright.
    #
    # `fee_candidates` still reports B, because the harness's job is to show a
    # refuted model failing. Pricing no longer consults it.
    return float(_model_a(price_tenths, count, maker))


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
#
# **"Kalshi charges whole cents" WAS true of the traded path and IS NO LONGER.**
# This comment used to read: *"11 of 11 single-game fees are whole cents. That
# is the path this tool trades, so the premise above holds where the constant is
# used."* Measured 2026-08-10 against 55 settled positions, it was correct then.
#
# Corrected 2026-08-14 against 11 real taker fills
# (`docs/measurements/2026-08-14-fee-rate-attribution-round-three-result.md`,
# reproducible via `scripts/reconcile_observed_fees.py`):
#
#   - **0 of 11 fills is a whole cent.** Single-game fees are now charged to
#     $0.0001 -- e.g. $0.0069, $0.0088, $0.0142, $0.0792.
#   - The old whole-cent observations are all dated **2025-11-27 to
#     2026-02-09** (NFL, NBA). Every $0.0001 observation is dated
#     **2026-08-10 or later**. The split by date is clean, both ways, 11 and 11.
#   - So **Kalshi revised the sports fee schedule between those dates**, and
#     what changed was the granularity as well as -- on baseball -- the rate.
#
# **The value stays at 1e-9, and the reason has inverted.** It used to stay
# because the traded path was whole cents and the tolerance had nothing to
# absorb. It now stays because the model below is *wrong* on every observed
# fill, and a tolerance wide enough to hide that is a tolerance wide enough to
# hide anything. Loosening it to absorb $0.001 would wave through a 10% error on
# a one-contract fill -- the defect this comment exists to describe.
#
# **The known limit, recorded rather than fixed:** a correct combo model would
# also trip `fee_model_verified`. The fix is a combo-aware fee model, not a
# looser tolerance. Note that as of 2026-08-14 the condition cannot fire at all
# -- the `fills` table has no live producer and the gate is pinned `met=False`
# (`backend/gate.py:639-658`), which is why nothing here caught the revision.
# See `TestTheFeeMatchToleranceIsFloatNoiseOnly`.
FEE_MATCH_TOLERANCE_DOLLARS = 1e-9
