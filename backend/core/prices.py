"""Canonical price representation: integer tenths of a cent.

Ported from ``kalshi_orderbook_monitor/prices.py``, essentially unchanged. It
was already right, and it was right for a reason worth restating.

Kalshi prices in fractions of a cent. Roughly a quarter of tradeable markets use
``deci_cent`` or ``tapered_deci_cent`` tick structures, and the API quotes prices
as dollar strings like ``"0.2400"``. Storing whole cents would silently misprice
those markets by up to half a cent -- against a total edge that is often only 4c,
and a round-trip fee of ~3.5c. That error is the same order as the entire thesis.

So the canonical internal unit is **tenths of a cent**, an integer in 0..1000:

    $1.00   = 1000 tenths = 100c
    $0.2400 =  240 tenths =  24c
    $0.0010 =    1 tenth  =   0.1c

Validated against live data before adopting: 152 order book levels sampled across
five markets spanning both tick structures produced **zero** prices off the
tenths grid, with an observed range of 1..962.

Two rules:

1. **Parse with Decimal and round explicitly.** Checked empirically: for the
   4-decimal strings Kalshi currently sends, ``int(float(s) * 1000)`` happens to
   be correct for all 999 values. That is luck, not a guarantee -- it depends on
   the float error landing on the right side of a truncation boundary, and it
   would break silently if Kalshi widened to 5 decimals. Decimal with an
   explicit ``ROUND_HALF_UP`` quantize does not rely on that.
2. **Quantities are floats, not ints.** Kalshi returns fractional sizes
   (``"17.38"``, ``"0.41"``); 42 of 152 sampled levels were fractional.

A third rule this project adds, from ``tasks/lessons.md``: **unreadable must
never resolve to zero.** Every parser here returns ``None`` on bad input rather
than a plausible-looking default, and callers are expected to refuse rather than
substitute. A price that silently became 0 is a free contract in the risk model.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional, Union

# A contract settles at $1.00, so prices span 0..1000 tenths of a cent.
PRICE_MAX = 1000
TENTHS_PER_CENT = 10

_TENTHS = Decimal(PRICE_MAX)


def dollars_to_tenths(value: Union[str, float, Decimal, None]) -> Optional[int]:
    """Convert a Kalshi dollar price (``"0.2400"``) to integer tenths of a cent.

    Returns None for unparseable input rather than raising -- a single bad level
    should not abort a whole snapshot. The caller decides whether a missing
    price is fatal; this function does not guess on its behalf.

    **The promise was not kept for three inputs.** `Decimal("nan")` and
    `Decimal("Infinity")` construct *successfully*, so the `except` never fired
    and the failure surfaced later at `int()` or `quantize` -- `"nan"` raised
    `ValueError`, `"Infinity"` and `"1e400"` raised `InvalidOperation`. A parser
    documented as returning None on bad input, raising three different
    exceptions from inside a snapshot loop, is worse than one that never
    promised: the caller wrote no handler because the docstring said it needed
    none.

    **Negatives return None too.** A price is a probability in dollars, so it
    cannot be below zero; `"-0.50"` used to parse cleanly to `-500` tenths and
    flow into the risk path as a real price. Refusing is right here rather than
    clamping, because this is a value being validated, not one being trusted.
    """
    if value is None:
        return None
    try:
        as_decimal = Decimal(str(value))
    except Exception:
        return None
    # `is_finite()` covers NaN and both infinities, which `Decimal` accepts.
    if not as_decimal.is_finite() or as_decimal < 0:
        return None
    try:
        return int(
            (as_decimal * _TENTHS).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
    except (InvalidOperation, ValueError, OverflowError):
        # A finite but absurd magnitude ("1e400" parses finite in some builds)
        # still cannot be quantized. Same contract: unreadable resolves to None.
        return None


def parse_quantity(value: Union[str, float, int, None]) -> Optional[float]:
    """Parse a Kalshi quantity string (``"17.38"``) to a float. May be negative."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def tenths_to_dollars(tenths: Union[int, float]) -> float:
    """Convert tenths of a cent to dollars, for money math."""
    return tenths / float(PRICE_MAX)


def tenths_to_cents(tenths: Union[int, float]) -> float:
    """Convert tenths of a cent to cents. May be fractional (241 -> 24.1)."""
    return tenths / float(TENTHS_PER_CENT)


def cents_to_tenths(cents: Union[int, float]) -> int:
    """Convert cents to tenths of a cent. For migrating cent-denominated code."""
    return int(round(cents * TENTHS_PER_CENT))


def format_price(tenths: Optional[Union[int, float]]) -> str:
    """Human-readable price. Whole cents render without a decimal point.

    240 -> "24c",  241 -> "24.1c",  1 -> "0.1c",  None -> "--"
    """
    if tenths is None:
        return "--"
    cents = tenths_to_cents(tenths)
    if abs(cents - round(cents)) < 1e-9:
        return f"{int(round(cents))}c"
    return f"{cents:.1f}c"


def format_probability(probability: Optional[float]) -> str:
    """A probability as a percentage. **Never with a cent suffix.**

    0.5385 -> "53.8%",  0.5 -> "50%",  None -> "--"

    A fair value is a probability, not a price. Rendered through
    :func:`format_price` it came out as ``53.8c`` and sat immediately left of a
    real ask at the same type size, which is the one place a left-to-right scan
    reads the wrong number as the thing you pay.

    Derived from the **same integer tenths** ``format_price`` uses, so the two
    renderings can never disagree by a rounding step: 0.5385 is 538 tenths, and
    538 tenths is ``53.8c`` as a price and ``53.8%`` as a probability. A
    separate ``f"{p * 100:.1f}%"`` would print ``53.9%`` beside a stored
    ``53.8c`` and there would be no way to tell which one had moved.
    """
    if probability is None:
        return "--"
    percent = tenths_to_cents(int(round(probability * PRICE_MAX)))
    if abs(percent - round(percent)) < 1e-9:
        return f"{int(round(percent))}%"
    return f"{percent:.1f}%"


def is_valid_price(tenths: Optional[Union[int, float]]) -> bool:
    """True if the price is a tradeable level, strictly inside 0 and $1.00.

    0 and 1000 are settled outcomes, not quotes.
    """
    return tenths is not None and 0 < tenths < PRICE_MAX


def complement(tenths: Union[int, float]) -> int:
    """The opposing side's price. YES ask = complement(best NO bid).

    Kalshi publishes YES bids and NO bids only; asks are derived because a YES
    and a NO contract together always settle at exactly $1.00. This identity is
    load-bearing: every EV calculation in this project buys at a *derived* ask,
    never at a mid, because the mid is not a price anyone will sell you.
    """
    return PRICE_MAX - int(tenths)


def probability_to_tenths(probability: float) -> int:
    """Convert a probability in [0, 1] to integer tenths of a cent.

    A contract's fair price in dollars *is* its probability, so this is the
    bridge between the devig/model layer and the price layer.
    """
    clamped = min(max(probability, 0.0), 1.0)
    return int(
        (Decimal(str(clamped)) * _TENTHS).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )


def tenths_to_probability(tenths: Union[int, float]) -> float:
    """Convert integer tenths of a cent to an implied probability in [0, 1]."""
    return tenths / float(PRICE_MAX)
