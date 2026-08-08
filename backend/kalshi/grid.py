"""The set of limit prices a market will actually accept.

Kalshi's rule, in its own words
-------------------------------
Each market publishes `price_ranges`, an array of `{start, end, step}` bands in
fixed-point dollars, and the documentation is unusually direct about its status:

    "This is the source of truth for valid prices: any price on the grid is
    valid, and any off-grid price is rejected. Consume it dynamically per
    market and snap order and quote prices to the relevant band's step."

    "price_level_structure -- a human-readable label for the grid. Do not key
    pricing logic off this name; new structures are introduced over time, and a
    client that reads price_ranges is automatically compatible with all of them."

So this module reads `price_ranges` and treats `price_level_structure` as a
label to log, never as a branch. The label is carried anyway, because a log line
saying `center_half_edge_half_cent` is worth far more to a human than three
bands of decimal strings.

What this replaces, and why it mattered
---------------------------------------
The order path used to floor every limit price to a whole cent. That is always a
*legal* price -- Kalshi: "whole-cent prices are valid in every structure" -- so
it could never be rejected, which is exactly what made it hard to see. On a
market with a half-cent grid, an ask of 50.5c became a bid at 50c: an order that
rests forever, never fills, and enters the paper record as a bet that was placed.
The record is the entire product here, and a systematically unfillable order
biases it toward whichever side happens to sit on a whole cent.

Measured, so the size of the problem is not overstated
------------------------------------------------------
`scripts/capture_price_grids.py`, run 2026-08-08 against the live exchange:
**1,426 game markets, 1 distinct grid, `linear_cent` on every one.** So on the
universe this project actually prices, the snapper is currently a no-op on every
market, and no fill is being lost today.

That is a fact about the slate, not about the exchange, and it must not be
promoted into "sub-cent game markets do not exist" -- the mistake
`tasks/lessons.md` records against `KXMVE`. `.claude/skills/kalshi-api/SKILL.md`
counted 60 `center_half_edge_half_cent` game markets on 2026-08-06, and Kalshi
publishes a `price_level_structure_updated` lifecycle event, so a market's grid
can change *while it is open*. Reading the grid per market is the only thing that
is correct on both days.

Units
-----
Bands are held in integer **micro-dollars** (1e-6), because that is the finest
precision Kalshi's fixed-point dollar strings carry and integers cannot drift.
The project's canonical unit remains tenths of a cent (`core/prices.py`), which
is 1,000 micro-dollars; `snap_tenths` refuses rather than rounds if a grid point
is finer than that, since a price we cannot represent is one we must not send.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

logger = logging.getLogger(__name__)

MICROS_PER_DOLLAR = 1_000_000
MICROS_PER_TENTH = 1_000

# Snap directions, named for what they protect rather than for the arithmetic.
DOWN = "down"
UP = "up"


class GridUnavailable(ValueError):
    """The market's price grid could not be read, so no price can be snapped.

    Separate from `orders.OrderRefused` on purpose: this says *"we do not know
    what this exchange will accept"*, which is a different fact from *"this
    order is wrong"*. The order path converts it into a refusal, because the
    correct response to not knowing is not to send.

    There is deliberately **no default grid.** Falling back to whole cents when
    `price_ranges` is missing would restore the exact bug this module exists to
    remove, and would do it silently on the day Kalshi renames the field --
    `tasks/lessons.md`, "unreadable must never resolve to zero", applied to a
    grid instead of a price.
    """


def _micros(value: Any) -> Optional[int]:
    """A fixed-point dollar string to integer micro-dollars, or None."""
    if value is None:
        return None
    try:
        as_decimal = Decimal(str(value))
    except (InvalidOperation, ValueError, ArithmeticError):
        return None
    if not as_decimal.is_finite() or as_decimal < 0:
        return None
    scaled = as_decimal * MICROS_PER_DOLLAR
    if scaled != scaled.to_integral_value():
        # Finer than Kalshi's own maximum precision. Refusing beats rounding a
        # bound we are about to validate prices against.
        return None
    return int(scaled)


@dataclass(frozen=True)
class PriceBand:
    """One `{start, end, step}` band, inclusive of both ends."""

    start_micros: int
    end_micros: int
    step_micros: int

    def contains(self, micros: int) -> bool:
        return self.start_micros <= micros <= self.end_micros

    def floor(self, micros: int) -> Optional[int]:
        """The greatest grid point in this band that is <= `micros`."""
        if micros < self.start_micros:
            return None
        capped = min(micros, self.end_micros)
        steps = (capped - self.start_micros) // self.step_micros
        return self.start_micros + steps * self.step_micros

    def ceil(self, micros: int) -> Optional[int]:
        """The least grid point in this band that is >= `micros`, or None.

        There is deliberately **one** bound check, at the end. An `if micros >
        self.end_micros: return None` at the top reads as defensive and is
        redundant with it -- verified by disabling: removing the top check left
        every test green, because the bound below already caught the same
        inputs. Two checks where one fires is the shape `tasks/lessons.md` calls
        "a guard that cannot fire is indistinguishable from one that is
        working", so the unreachable one is deleted rather than kept for
        comfort.

        The surviving check is load-bearing on a band whose `end` is not a whole
        number of steps above `start`. `floor` keeps its own guard for a
        different reason: without it, a price below the band floor-divides to a
        *negative* step count and returns a point outside the band entirely.
        """
        target = max(micros, self.start_micros)
        offset = target - self.start_micros
        steps = -(-offset // self.step_micros)          # ceiling division
        point = self.start_micros + steps * self.step_micros
        return point if point <= self.end_micros else None


@dataclass(frozen=True)
class PriceGrid:
    """Every price one market will accept.

    Frozen and tuple-backed so it can live on a frozen `DiscoveredMarket`
    without making it unhashable.
    """

    bands: tuple[PriceBand, ...]
    structure: Optional[str] = None

    def snap_tenths(self, price_tenths: int, direction: str) -> int:
        """Move `price_tenths` onto the grid, in `direction`, or refuse.

        `DOWN` for a bid and `UP` for an ask -- always away from paying more.
        The caller chooses the direction because only the caller knows which
        side of the book it is on; getting it wrong here would be a sign error
        that produces entirely plausible prices, which is the failure mode
        `tasks/lessons.md` names twice.

        Raises rather than clamping when the price lies outside every band. A
        price off the end of the grid is one the exchange would reject, and
        turning a rejection into the nearest legal price is precisely how a
        `no_price=-390` became a live buy at 99c in the predecessor project.
        """
        if direction not in (DOWN, UP):
            raise GridUnavailable(
                f"direction must be {DOWN!r} or {UP!r}, not {direction!r}"
            )

        micros = int(price_tenths) * MICROS_PER_TENTH
        if direction == DOWN:
            candidates = [b.floor(micros) for b in self.bands]
            usable = [c for c in candidates if c is not None and c <= micros]
            snapped = max(usable) if usable else None
        else:
            candidates = [b.ceil(micros) for b in self.bands]
            usable = [c for c in candidates if c is not None and c >= micros]
            snapped = min(usable) if usable else None

        if snapped is None:
            raise GridUnavailable(
                f"{price_tenths} tenths ({price_tenths / 10:.1f}c) has no grid "
                f"point {direction} on this market's {self.describe()}. "
                f"Refusing rather than clamping onto the nearest legal price: "
                f"a price the exchange would reject is a signal, and clamping "
                f"deletes it."
            )

        if snapped % MICROS_PER_TENTH != 0:
            # Reachable only on a grid finer than a tenth of a cent -- Kalshi's
            # `center_centi_edge_centi_cent`, used by combo markets. Refusing is
            # honest: the project's canonical unit cannot name this price, and a
            # money path must not quietly send a different one.
            raise GridUnavailable(
                f"this market's grid puts a price at {snapped} micro-dollars, "
                f"finer than the tenth-of-a-cent unit this project represents "
                f"prices in. Refusing rather than rounding a price we are about "
                f"to send."
            )
        return snapped // MICROS_PER_TENTH

    def is_on_grid(self, price_tenths: int) -> bool:
        micros = int(price_tenths) * MICROS_PER_TENTH
        return any(
            b.contains(micros) and b.floor(micros) == micros for b in self.bands
        )

    def describe(self) -> str:
        label = self.structure or "unlabelled"
        bands = ", ".join(
            f"{b.start_micros / MICROS_PER_DOLLAR:.4f}-"
            f"{b.end_micros / MICROS_PER_DOLLAR:.4f}"
            f"@{b.step_micros / MICROS_PER_DOLLAR:.4f}"
            for b in self.bands
        )
        return f"grid {label} [{bands}]"


def parse_price_grid(
    raw_ranges: Any, *, structure: Optional[str] = None
) -> PriceGrid:
    """`price_ranges` from a market payload to a `PriceGrid`, or raise.

    Every failure raises `GridUnavailable` rather than returning an empty or
    default grid. An empty grid would refuse every price, which looks like a
    working guard; a default grid would accept whole cents only, which looks
    like the old behaviour. Both hide a wire-format change, and this repo has
    twice shipped a parser that returned "nothing here" when the truth was "the
    field was renamed".
    """
    if raw_ranges is None:
        raise GridUnavailable(
            "market payload carried no 'price_ranges'. That field is Kalshi's "
            "source of truth for which limit prices are accepted; without it we "
            "do not know what this market will take, and assuming whole cents "
            "is how a sub-cent ask becomes an order that never fills."
        )
    if not isinstance(raw_ranges, (list, tuple)) or not raw_ranges:
        raise GridUnavailable(
            f"'price_ranges' is {type(raw_ranges).__name__} "
            f"{raw_ranges!r}, not a non-empty array of bands."
        )

    bands: list[PriceBand] = []
    for index, raw in enumerate(raw_ranges):
        if not isinstance(raw, dict):
            raise GridUnavailable(f"band {index} is not an object: {raw!r}")
        start = _micros(raw.get("start"))
        end = _micros(raw.get("end"))
        step = _micros(raw.get("step"))
        if start is None or end is None or step is None:
            raise GridUnavailable(
                f"band {index} has an unreadable start/end/step: {raw!r}. "
                f"Refusing rather than skipping it -- a grid missing one band "
                f"silently refuses every price inside it."
            )
        if step <= 0 or end <= start:
            raise GridUnavailable(
                f"band {index} is degenerate (start={start}, end={end}, "
                f"step={step} micro-dollars)."
            )
        bands.append(PriceBand(start_micros=start, end_micros=end, step_micros=step))

    return PriceGrid(bands=tuple(bands), structure=structure)


def read_price_grid(market: dict) -> Optional[PriceGrid]:
    """Parse a market payload's grid, or `None` if it cannot be read.

    The ingest-boundary form: unreadable resolves to `None` so a discovery walk
    of ~1,400 markets is not aborted by one malformed band, and the **order
    path** refuses on the `None`. That split is the repo's standing rule --
    parsers return `Optional`, callers refuse -- and it is why this returns None
    while `parse_price_grid` raises.
    """
    try:
        return parse_price_grid(
            market.get("price_ranges"),
            structure=market.get("price_level_structure"),
        )
    except GridUnavailable as exc:
        logger.warning(
            "no usable price grid for %s: %s", market.get("ticker"), exc
        )
        return None
