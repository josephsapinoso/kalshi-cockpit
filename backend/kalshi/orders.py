"""Order construction, validation and placement.

This is the only module in the project that can lose money, so it is built to
refuse rather than to cope.

The rule that earned itself
---------------------------
Prices are moved onto the market's own grid **away from paying more** — a bid
snaps down, an ask snaps up — and then the request **raises rather than clamps**
if the result lands off the tradeable range. That second half is the important
half. In the predecessor project the equivalent function clamped, and a
self-announcing API rejection (`no_price=-390`, which the exchange would have
bounced) turned into a live buy at 99c. Clamping converted a loud failure into a
silent maximum-cost fill.

So: **clamp what you trust, refuse what you are validating.** A price derived
from our own book is trusted; a price about to be sent to the exchange with real
money behind it is being validated.

Two things changed here on 2026-08-08
-------------------------------------
**1. Prices snap to the market's grid, not to whole cents.** The old code
floored every limit to an integer cent. That is always a *legal* price — Kalshi:
"whole-cent prices are valid in every structure" — which is what made it
invisible. On a market with a half-cent grid it turned a 50.5c ask into a bid at
50c: an order that rests forever, never fills, and lands in the paper record as
a bet that was placed. Since the record is the entire product, an order that
cannot fill is worse than one that is refused. `kalshi/grid.py` reads
`price_ranges` per market, which Kalshi documents as the source of truth.

Measured before believing the size of it: 1,426 game markets on 2026-08-08 were
`linear_cent` to a market, so the snap is a no-op on today's slate and no fill is
being lost right now. It was 60 half-cent game markets two days earlier, and a
market's structure can change while it is open, so reading the grid is the only
behaviour that is right on both days.

**2. The order goes to `/portfolio/events/orders` (V2).** The legacy
`/portfolio/orders` takes `yes_price`/`no_price` as **integer cents**, so it
cannot express a sub-cent price at all — fix (1) is unreachable without this.
Kalshi's own documentation now lists only the V2 path and says the legacy one
"will be deprecated no earlier than May 6, 2026"; it no longer appears in the
API reference index at all.

V2 quotes everything from the **YES leg**: `side` is `bid` (buy YES) or `ask`
(sell YES), and buying NO at `p` is selling YES at `1 - p`. That conversion is
done here, once, and the rounding rule survives it unchanged — in YES-book terms
a `bid` always snaps down and an `ask` always snaps up.

What is verified, and what is not
---------------------------------
The **request** shape is taken from Kalshi's published OpenAPI spec, and the
`price_ranges` parser is pinned by real captured bytes (1,426 markets).

**The response shape is no longer unobserved, and this paragraph said it was
until 2026-08-26.** It read "no order has ever been placed by this project",
which was written when it was true and left standing after it stopped being
true: Joe ran the C0 probe on 2026-08-23 (`scripts/probe_create_order.py`,
capture `data/captures/create_order_probe_20260823T041018Z.json`) and four
real orders were created on the live venue -- 201, 409, 201, 201. The create
response is **flat**: no `order` envelope, exactly as `_read_response`'s own
note below records, and `tests/fixtures/create_order_responses.json` is
hand-written from that capture.

What is still true, and is the sentence that was doing the work: **the app's
own order path has never sent an order.** Both doors are dry by their
constants, and the probe deliberately bypasses `KalshiRestClient.post` (see
its docstring), so nothing here has been exercised end to end against the
venue.

That is stated here because the previous version of this file had the same gap
and hid it: it read `response["order"]["status"]` with a default of `"resting"`.
V2 emits no `order` envelope and no `status` field, so *every* live order would
have been recorded as resting with a null order id — a plausible default over an
unread response, which is the single failure this repo has been caught by most
often. Status is now **derived from the fill counts**, and a response that does
not carry them is recorded as `unrecognised_response` rather than as anything
that reads like success.

One thing the V2 response gives us for free: `average_fee_paid`, per contract,
volume-weighted. The fee model in `core/fees.py` is still a conservative hedge
between two disagreeing sources because reading the true fee needs a real fill —
this is where that reading will arrive, in the order response itself, without a
separate `/portfolio/fills` poll.

Dry run is the same code path
-----------------------------
A dry run builds the identical request body, generates the identical
`client_order_id`, and writes the identical row — it just does not POST. That
means the thing verified in dry run is the thing that later executes, rather
than a parallel implementation that drifts. `orders.request_body_json` stores
the exact bytes either way, so a dry run is comparable to a live order field by
field.

That paragraph was aspirational until 2026-08-08: **nothing wrote the row.** The
module said "writes the identical row" while `orders` had never held one, so the
one property the dry run existed to establish — that it is byte-comparable to a
live order — could not be checked against anything. `store/orders.py` is the
writer, and it runs *before* the POST rather than after it, because
`client_order_id` is only an idempotency key if it survives a lost response.

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
from decimal import Decimal
from typing import Any, Callable, Optional

from ..core.fees import calculate_fee
from ..core.prices import PRICE_MAX, complement, is_valid_price
from .grid import DOWN, UP, GridUnavailable, PriceGrid
from .rest import KalshiRestClient

logger = logging.getLogger(__name__)

# Kalshi's V2 order path. The legacy `/portfolio/orders` is deprecated, absent
# from the current API reference, and cannot express a sub-cent price.
ORDERS_PATH = "/portfolio/events/orders"

# V2 quotes the YES leg only: `bid` buys YES, `ask` sells YES.
BOOK_SIDE_BID = "bid"
BOOK_SIDE_ASK = "ask"

# Both are **required** by the V2 schema. The legacy request carried neither,
# which is why the previous version of this file sent a plain limit order and
# `tasks/NEXT.md` had to record that the depth refusal "claimed a fill guarantee
# the order does not have".
#
# `good_till_canceled` keeps the existing behaviour — a resting limit order —
# rather than quietly introducing fill-or-kill semantics along with an endpoint
# change. There is still no cancel path in this repo, and that remains true and
# worth fixing; it is not made worse here.
TIME_IN_FORCE_GTC = "good_till_canceled"
# Cancels *our* taker order if it would trade against our own resting order.
# The alternative (`maker`) cancels the resting side instead, which on a venue
# where we may later quote both sides would silently retire liquidity we placed.
SELF_TRADE_PREVENTION_TAKER = "taker_at_cross"


class OrderRefused(ValueError):
    """Raised when an order must not be sent.

    Deliberately not a subclass of anything the REST layer catches. A refusal
    here is a decision, not a transient failure, and retrying it is wrong.
    """


def book_side_for(side: str, action: str) -> str:
    """Our (side, action) to the YES-book side V2 wants.

    Buying NO is economically selling YES, so the four combinations collapse to
    two. Written as an explicit table rather than a boolean expression because
    this is a sign convention, and `tasks/lessons.md` records two separate
    occasions where a sign convention and the test written beside it were wrong
    together.
    """
    mapping = {
        ("yes", "buy"): BOOK_SIDE_BID,
        ("no", "sell"): BOOK_SIDE_BID,
        ("yes", "sell"): BOOK_SIDE_ASK,
        ("no", "buy"): BOOK_SIDE_ASK,
    }
    try:
        return mapping[(side, action)]
    except KeyError:
        raise OrderRefused(
            f"cannot express {action!r} {side!r} on the YES book. `side` must be "
            f"'yes' or 'no' and `action` 'buy' or 'sell'."
        ) from None


def yes_book_price_tenths(side: str, price_tenths: int) -> int:
    """The price for our side, expressed on the YES book.

    A NO price of `p` is a YES price of `1 - p`. `complement` is the same
    function the derived-ask identity uses, so there is one definition of this
    reflection in the codebase rather than two that can drift.
    """
    return int(price_tenths) if side == "yes" else complement(price_tenths)


def price_dollars(price_tenths: int) -> str:
    """Tenths of a cent to the fixed-point dollar string V2 expects.

    Four decimal places, matching every `*_dollars` field Kalshi sends. Built
    with `Decimal` rather than an f-string over a float, for the reason
    `core/prices.py` gives about parsing: the float happens to be right for
    today's values and that is luck, not a guarantee.
    """
    return str((Decimal(int(price_tenths)) / Decimal(PRICE_MAX)).quantize(Decimal("0.0001")))


@dataclass(frozen=True)
class OrderRequest:
    """A validated order, ready to send.

    Validation happens in `__post_init__` so an invalid `OrderRequest` cannot
    exist. There is no path where a caller holds one of these and still has to
    remember to check it.

    `price_grid` has **no default**. An order cannot be priced without knowing
    which prices the market accepts, and a default grid would silently restore
    whole-cent flooring on exactly the markets where it is wrong.
    """

    ticker: str
    side: str                      # yes | no -- the side we take
    action: str                    # buy | sell
    count: int
    limit_price_tenths: int        # price for our side, before snapping
    price_grid: PriceGrid
    recommendation_id: Optional[int] = None
    client_order_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    time_in_force: str = TIME_IN_FORCE_GTC
    self_trade_prevention: str = SELF_TRADE_PREVENTION_TAKER

    def __post_init__(self) -> None:
        if self.side not in {"yes", "no"}:
            raise OrderRefused(f"side must be 'yes' or 'no', not {self.side!r}")
        if self.action not in {"buy", "sell"}:
            raise OrderRefused(f"action must be 'buy' or 'sell', not {self.action!r}")
        if self.count <= 0:
            raise OrderRefused(f"count must be positive, got {self.count}")
        if not self.ticker:
            raise OrderRefused("ticker is required")
        if not isinstance(self.price_grid, PriceGrid):
            raise OrderRefused(
                "an order needs the market's price grid. Kalshi rejects any "
                "price off it, and assuming whole cents is how a sub-cent ask "
                "becomes an order that rests forever and never fills."
            )
        if not is_valid_price(self.limit_price_tenths):
            raise OrderRefused(
                f"limit price {self.limit_price_tenths} tenths is not tradeable "
                f"(0 and {PRICE_MAX} are settled outcomes, not quotes)"
            )
        if self.time_in_force not in {
            "fill_or_kill", "good_till_canceled", "immediate_or_cancel"
        }:
            raise OrderRefused(f"time_in_force {self.time_in_force!r} is not a V2 value")
        if self.self_trade_prevention not in {"taker_at_cross", "maker"}:
            raise OrderRefused(
                f"self_trade_prevention {self.self_trade_prevention!r} is not a V2 value"
            )
        # Snap now, so an order that cannot be sent fails at construction rather
        # than at the API boundary.
        self.api_price_tenths

    @property
    def book_side(self) -> str:
        return book_side_for(self.side, self.action)

    @property
    def api_price_tenths(self) -> int:
        """The YES-book limit price actually sent, snapped to this market's grid.

        A bid snaps down and an ask snaps up — always away from paying more,
        which holds for both sides because buying NO *is* an ask.
        """
        unsnapped = yes_book_price_tenths(self.side, self.limit_price_tenths)
        direction = DOWN if self.book_side == BOOK_SIDE_BID else UP
        try:
            snapped = self.price_grid.snap_tenths(unsnapped, direction)
        except GridUnavailable as exc:
            raise OrderRefused(str(exc)) from exc
        if not is_valid_price(snapped):
            raise OrderRefused(
                f"{self.limit_price_tenths} tenths on our {self.side} side snaps "
                f"to a YES price of {snapped} tenths, which is a settled outcome "
                f"rather than a quote. Refusing rather than clamping onto the "
                f"edge of the book: clamping an out-of-range price is how an "
                f"order the exchange would have rejected becomes a live fill at "
                f"the worst price available."
            )
        return snapped

    @property
    def api_price_dollars(self) -> str:
        return price_dollars(self.api_price_tenths)

    @property
    def fill_price_tenths(self) -> int:
        """What one contract of *our* side costs at the price being sent.

        The YES-book price reflected back to the side we actually take, so the
        cost arithmetic below never has to know which leg V2 quoted.
        """
        return yes_book_price_tenths(self.side, self.api_price_tenths)

    @property
    def worst_case_cost_dollars(self) -> float:
        """What this costs if it fills completely, fee included.

        The stake uses the price actually being sent, since the snap is in our
        favour and quoting the un-snapped number would overstate it.

        The **fee** uses the un-snapped `limit_price_tenths` as well as the sent
        price, and takes the larger. The fee curve peaks at 50c, so computing it
        at a snapped-down price understates it for an ask just below the peak --
        and a field called `worst_case` must not round a cost down.
        """
        stake = self.count * self.fill_price_tenths / float(PRICE_MAX)
        fee = max(
            calculate_fee(self.fill_price_tenths, self.count) or 0.0,
            calculate_fee(self.limit_price_tenths, self.count) or 0.0,
        )
        return stake + fee

    def to_api_dict(self) -> dict[str, Any]:
        """The exact body Kalshi's V2 endpoint expects.

        `client_order_id` is the idempotency key. It is generated before the
        request so a timeout-then-retry cannot double-fill: the exchange
        recognises the repeat and returns the original order.

        `count` is a fixed-point **string**. V2 supports fractional contracts to
        0.01, and sending an integer where a string is specified is the kind of
        type mismatch that produces a 400 nobody can reproduce from a log.
        """
        return {
            "ticker": self.ticker,
            "client_order_id": self.client_order_id,
            "side": self.book_side,
            "count": f"{self.count}.00",
            "price": self.api_price_dollars,
            "time_in_force": self.time_in_force,
            "self_trade_prevention_type": self.self_trade_prevention,
        }


# An observer so every component sees exposure it did not create. Ported from
# the predecessor project, where the absence of it meant the risk check and the
# order path could disagree about what was outstanding.
OrderObserver = Callable[["OrderOutcome"], None]

# Statuses this module emits. Derived from the V2 fill counts rather than read
# from a `status` field, because V2 does not send one.
STATUS_DRY_RUN = "dry_run"
STATUS_RESTING = "resting"
STATUS_PARTIALLY_FILLED = "partially_filled"
STATUS_FILLED = "filled"
STATUS_UNFILLED = "unfilled"
STATUS_REJECTED = "rejected"
STATUS_UNRECOGNISED = "unrecognised_response"


def canonical_body_json(body: dict[str, Any]) -> str:
    """The request body as text, with sorted keys.

    One definition, because two callers need it at different times and must
    agree: `store/orders.py` writes the row *before* the POST and only has the
    body, while `OrderOutcome` renders it *after* and has the outcome. If those
    two serialised differently, a stored dry run and a live order would stop
    being comparable as text, which is the only reason `request_body_json`
    exists.
    """
    return json.dumps(body, sort_keys=True)


def _fp(value: Any) -> Optional[float]:
    """A fixed-point count string (`"10.00"`) to a float, or None."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class OrderOutcome:
    """What happened, in a shape that is identical for dry runs and live orders."""

    request: OrderRequest
    status: str
    dry_run: bool
    request_body: dict[str, Any]
    kalshi_order_id: Optional[str] = None
    error_text: Optional[str] = None
    fill_count: Optional[float] = None
    remaining_count: Optional[float] = None
    # Volume-weighted, per contract, and only present once something filled.
    # This is the measured fee `core/fees.py` is hedging against for want of a
    # real fill -- see the module docstring.
    average_fill_price_dollars: Optional[str] = None
    average_fee_paid_dollars: Optional[str] = None
    response_body: Optional[dict[str, Any]] = None

    @property
    def request_body_json(self) -> str:
        # Sorted keys so a dry-run body and a live body are comparable as text.
        return canonical_body_json(self.request_body)


def status_from_counts(
    fill_count: Optional[float], remaining_count: Optional[float]
) -> str:
    """What the fill counts say happened.

    V2 sends no `status` field, so this is arithmetic on two documented numbers
    rather than a guess at a third. The unreadable case returns
    `unrecognised_response` and never `resting`: an order whose response we
    could not parse may well have filled, and recording it as a resting order
    would put a fill in the book and nothing in the record.
    """
    if fill_count is None or remaining_count is None:
        return STATUS_UNRECOGNISED
    if fill_count > 0 and remaining_count > 0:
        return STATUS_PARTIALLY_FILLED
    if fill_count > 0:
        return STATUS_FILLED
    if remaining_count > 0:
        return STATUS_RESTING
    # Nothing filled and nothing left: an IOC or FOK that matched no one.
    return STATUS_UNFILLED


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
                "DRY RUN %s %s x%d @ %s (%s, client_order_id=%s)",
                request.book_side, request.ticker, request.count,
                request.api_price_dollars, request.price_grid.describe(),
                request.client_order_id,
            )
            outcome = OrderOutcome(
                request=request, status=STATUS_DRY_RUN, dry_run=True,
                request_body=body,
            )
            self._notify(outcome)
            return outcome

        try:
            response = await self._rest.post(ORDERS_PATH, json_body=body)
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
                request=request, status=STATUS_REJECTED, dry_run=False,
                request_body=body, error_text=str(exc),
            )
            self._notify(outcome)
            return outcome

        outcome = self._read_response(request, body, response)
        self._notify(outcome)
        return outcome

    def _read_response(
        self,
        request: OrderRequest,
        body: dict[str, Any],
        response: Optional[dict[str, Any]],
    ) -> OrderOutcome:
        """Parse a V2 create-order response, or say plainly that it could not.

        **This shape was OBSERVED on 2026-08-23** by the C0 probe
        (docs/runbooks/c0-create-order-probe.md): four real orders against
        one KXNCAAFGAME ticker, and every field this function reads appeared
        exactly as transcribed -- a flat payload (no `order` wrapper),
        fixed-point count strings, dollar strings for the averaged fill
        price and fee. `tests/test_create_order_response_shapes.py` pins the
        shape via a synthetic fixture hand-written from that capture (the
        raw capture is operator data and stays local).

        The refusal posture stays anyway: one ticker, one day, one series,
        so every unreadable field still produces `unrecognised_response` and
        a loud log rather than a plausible default -- the previous version
        defaulted a missing status to `resting`, which under V2 would have
        been *every* order.
        """
        payload = response if isinstance(response, dict) else {}
        order_id = payload.get("order_id")
        fill_count = _fp(payload.get("fill_count"))
        remaining_count = _fp(payload.get("remaining_count"))
        status = status_from_counts(fill_count, remaining_count)

        error_text = None
        if status == STATUS_UNRECOGNISED or not order_id:
            status = STATUS_UNRECOGNISED
            error_text = (
                f"could not read the order response (keys: {sorted(payload)}). "
                f"The order may have been placed -- check /portfolio/orders for "
                f"client_order_id={request.client_order_id} before retrying."
            )
            logger.error("%s: %s", request.ticker, error_text)

        return OrderOutcome(
            request=request,
            status=status,
            dry_run=False,
            request_body=body,
            kalshi_order_id=order_id,
            error_text=error_text,
            fill_count=fill_count,
            remaining_count=remaining_count,
            average_fill_price_dollars=payload.get("average_fill_price"),
            average_fee_paid_dollars=payload.get("average_fee_paid"),
            response_body=payload or None,
        )
