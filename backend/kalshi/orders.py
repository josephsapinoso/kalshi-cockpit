"""Order construction, validation and placement.

This is the only module in the project that can lose money, so it is built to
refuse rather than to cope.

The rule that earned itself
---------------------------
`api_price_cents()` rounds a **buy down** and a **sell up** — always away from
paying more — and then **raises rather than clamps** if the result lands off the
1–99 grid. That second half is the important half. In the predecessor project
the same function clamped, and a self-announcing API rejection (`no_price=-390`,
which the exchange would have bounced) turned into a live buy at 99c. Clamping
converted a loud failure into a silent maximum-cost fill.

So: **clamp what you trust, refuse what you are validating.** A price derived
from our own book is trusted; a price about to be sent to the exchange with real
money behind it is being validated.

Dry run is the same code path
-----------------------------
A dry run builds the identical request body, generates the identical
`client_order_id`, and writes the identical row — it just does not POST. That
means the thing verified in dry run is the thing that later executes, rather
than a parallel implementation that drifts. `orders.request_body_json` stores
the exact bytes either way, so a dry run is comparable to a live order field by
field.

What this module does not decide
--------------------------------
Whether a bet is a good idea. Sizing is `core/sizing.py`, the edge is
`engine.py`, and whether execution is permitted at all is `gate.py`. This module
takes a decision that has already been made and turns it into a correct,
idempotent, recorded API call — or refuses.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ..core.fees import calculate_fee
from ..core.prices import PRICE_MAX, is_valid_price
from .rest import KalshiRestClient

logger = logging.getLogger(__name__)

# Kalshi accepts whole-cent limit prices on the 1..99 grid. 0 and 100 are
# settled outcomes, not quotes.
API_PRICE_MIN = 1
API_PRICE_MAX = 99


class OrderRefused(ValueError):
    """Raised when an order must not be sent.

    Deliberately not a subclass of anything the REST layer catches. A refusal
    here is a decision, not a transient failure, and retrying it is wrong.
    """


def api_price_cents(price_tenths: int, action: str) -> int:
    """Convert a price in tenths to the whole cents Kalshi's API accepts.

    Rounds **away from paying more**: a buy rounds down, a sell rounds up.

    Raises if the result is off the 1–99 grid rather than clamping onto it.
    Clamping here once turned an API rejection into a live buy at 99c.
    """
    if action not in {"buy", "sell"}:
        raise OrderRefused(f"action must be 'buy' or 'sell', not {action!r}")

    if action == "buy":
        cents = price_tenths // 10
    else:
        cents = -(-price_tenths // 10)     # ceiling division

    if not API_PRICE_MIN <= cents <= API_PRICE_MAX:
        raise OrderRefused(
            f"{price_tenths} tenths rounds to {cents}c for a {action}, which is "
            f"outside Kalshi's {API_PRICE_MIN}-{API_PRICE_MAX} grid. Refusing "
            f"rather than clamping: clamping an out-of-range price is how an "
            f"order the exchange would have rejected becomes a live fill at the "
            f"worst price on the book."
        )
    return cents


@dataclass(frozen=True)
class OrderRequest:
    """A validated order, ready to send.

    Validation happens in `__post_init__` so an invalid `OrderRequest` cannot
    exist. There is no path where a caller holds one of these and still has to
    remember to check it.
    """

    ticker: str
    side: str                      # yes | no
    action: str                    # buy | sell
    count: int
    limit_price_tenths: int
    recommendation_id: Optional[int] = None
    client_order_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if self.side not in {"yes", "no"}:
            raise OrderRefused(f"side must be 'yes' or 'no', not {self.side!r}")
        if self.action not in {"buy", "sell"}:
            raise OrderRefused(f"action must be 'buy' or 'sell', not {self.action!r}")
        if self.count <= 0:
            raise OrderRefused(f"count must be positive, got {self.count}")
        if not self.ticker:
            raise OrderRefused("ticker is required")
        if not is_valid_price(self.limit_price_tenths):
            raise OrderRefused(
                f"limit price {self.limit_price_tenths} tenths is not tradeable "
                f"(0 and {PRICE_MAX} are settled outcomes, not quotes)"
            )
        # Validate the grid conversion now, so an order that cannot be sent
        # fails at construction rather than at the API boundary.
        api_price_cents(self.limit_price_tenths, self.action)

    @property
    def api_price(self) -> int:
        return api_price_cents(self.limit_price_tenths, self.action)

    @property
    def worst_case_cost_dollars(self) -> float:
        """What this costs if it fills completely, fee included.

        The stake uses the API price actually being sent, since the rounding is
        in our favour and quoting the un-rounded number would overstate it.

        The **fee** uses the un-rounded `limit_price_tenths`, deliberately. The
        fee curve peaks at 50c, so computing it at the rounded price understates
        it for an ask just below the peak -- and a field called `worst_case` must
        not round a cost down.
        """
        stake = self.count * self.api_price / 100.0
        fee = max(
            calculate_fee(self.api_price * 10, self.count) or 0.0,
            calculate_fee(self.limit_price_tenths, self.count) or 0.0,
        )
        return stake + fee

    def to_api_dict(self) -> dict[str, Any]:
        """The exact body Kalshi expects.

        `client_order_id` is the idempotency key. It is generated before the
        request so a timeout-then-retry cannot double-fill: the exchange
        recognises the repeat and returns the original order.
        """
        body: dict[str, Any] = {
            "ticker": self.ticker,
            "client_order_id": self.client_order_id,
            "side": self.side,
            "action": self.action,
            "count": self.count,
            "type": "limit",
        }
        # Kalshi names the limit field per side.
        if self.side == "yes":
            body["yes_price"] = self.api_price
        else:
            body["no_price"] = self.api_price
        return body


# An observer so every component sees exposure it did not create. Ported from
# the predecessor project, where the absence of it meant the risk check and the
# order path could disagree about what was outstanding.
OrderObserver = Callable[["OrderOutcome"], None]


@dataclass(frozen=True)
class OrderOutcome:
    """What happened, in a shape that is identical for dry runs and live orders."""

    request: OrderRequest
    status: str                    # dry_run | resting | filled | rejected
    dry_run: bool
    request_body: dict[str, Any]
    kalshi_order_id: Optional[str] = None
    error_text: Optional[str] = None

    @property
    def request_body_json(self) -> str:
        # Sorted keys so a dry-run body and a live body are comparable as text.
        return json.dumps(self.request_body, sort_keys=True)


class OrderPlacer:
    """Places orders, or records what it would have placed.

    `dry_run=True` is the default. An execution path that defaults to live is
    one typo away from a real fill.
    """

    def __init__(
        self,
        rest: Optional[KalshiRestClient] = None,
        *,
        dry_run: bool = True,
        observers: Optional[list[OrderObserver]] = None,
    ) -> None:
        self._rest = rest
        self.dry_run = dry_run
        self._observers: list[OrderObserver] = list(observers or [])

        if not dry_run and rest is None:
            raise OrderRefused(
                "a live OrderPlacer needs a REST client. Refusing to construct "
                "one that would silently no-op every order."
            )

    def subscribe(self, observer: OrderObserver) -> None:
        self._observers.append(observer)

    def _notify(self, outcome: OrderOutcome) -> None:
        for observer in self._observers:
            try:
                observer(outcome)
            except Exception:
                # An observer that raises must not unwind an order that has
                # already been placed -- the money has moved either way, and
                # losing the record is worse than losing the notification.
                logger.exception("order observer failed for %s", outcome.request.ticker)

    async def place(self, request: OrderRequest) -> OrderOutcome:
        """Send the order, or record the dry run.

        Both paths build the body identically, so what a dry run verifies is
        what a live order sends.
        """
        body = request.to_api_dict()

        if self.dry_run:
            logger.info(
                "DRY RUN %s %s %s x%d @ %dc (client_order_id=%s)",
                request.action, request.count, request.ticker, request.count,
                request.api_price, request.client_order_id,
            )
            outcome = OrderOutcome(
                request=request, status="dry_run", dry_run=True, request_body=body
            )
            self._notify(outcome)
            return outcome

        try:
            response = await self._rest.post("/portfolio/orders", json_body=body)
        except Exception as exc:
            # A failed POST is not necessarily a failed order -- the request may
            # have reached Kalshi before the connection dropped. The
            # client_order_id is what makes the retry safe, so it is recorded
            # with the failure rather than discarded.
            logger.error(
                "order POST failed for %s (client_order_id=%s): %s. Retry with "
                "the SAME client_order_id -- Kalshi will return the original "
                "order rather than creating a second one.",
                request.ticker, request.client_order_id, exc,
            )
            outcome = OrderOutcome(
                request=request, status="rejected", dry_run=False,
                request_body=body, error_text=str(exc),
            )
            self._notify(outcome)
            return outcome

        order = (response or {}).get("order", {})
        outcome = OrderOutcome(
            request=request,
            status=order.get("status", "resting"),
            dry_run=False,
            request_body=body,
            kalshi_order_id=order.get("order_id"),
        )
        self._notify(outcome)
        return outcome
