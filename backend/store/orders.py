"""Persisting orders, and reading exposure back out of them.

`kalshi/orders.py` builds and sends an order. This module writes it down. They
are separate because the exchange module must not import sqlite3, and because
the two answer different questions: one is "what did we send", the other is
"what are we exposed to".

Write before send, always
-------------------------
`record_intent` runs **before** the POST, not after it. The reason is
`client_order_id`: it is the idempotency key, and it is worth nothing unless it
is durable before the request leaves the process.

The failure it exists for is a POST that times out *after* Kalshi accepted it.
There is now an order in the book and no response in hand, and the only safe
recovery is to re-send with the same `client_order_id` — Kalshi returns the
original rather than creating a second one. Recording after the response means
the one case the key was invented for is exactly the case where the key is lost.

The cost is stated rather than hidden: a process that dies between the insert
and the POST leaves a `pending` row for an order that was never sent, and that
row counts as exposure until someone reconciles it against
`GET /portfolio/orders`. That is the conservative direction. "We might have an
open order" must never resolve to "we do not".

`limit_price_tenths` is **our** price, not the price on the wire
----------------------------------------------------------------
V2 quotes the YES leg only, so buying NO at 40.5c is sent as a YES ask of
59.5c. Exposure is `count * limit_price_tenths`, which is money at risk, so the
column has to hold what we pay — 405, not 595. Storing the wire price would
compute a NO position's exposure as its complement: overstated below 50c and
**understated above it**, which is the direction that lets the cap wave through
a position larger than it allows.

Nothing is lost by not storing the wire price. `request_body_json` holds the
exact bytes, including `price`, so the sent value is recoverable byte for byte
and there is one column per meaning rather than two that can drift.

What this module does not do
----------------------------
- **It does not write `fills`.** No order has ever been placed, so there is no
  fill to write, and `fills` needs `fee_predicted`/`fee_model_used` from the
  engine rather than from an order response.
- **It does not make placement idempotent.** The `UNIQUE` constraint on
  `client_order_id` stops a duplicate *row*; it does not stop a duplicate
  *order*, because each request mints a fresh id. Two taps are two orders. That
  is harmless while every order is a dry run and must be closed before the gate
  opens.
- **It does not serialise two orders against one exposure reading.** The caller
  reads exposure, sizes against it, then inserts. Two concurrent requests can
  each size against the same snapshot. Closing it means holding the read and
  the insert in one write transaction.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Optional

from ..core.prices import PRICE_MAX
from ..kalshi.orders import OrderOutcome, OrderRequest, canonical_body_json

logger = logging.getLogger(__name__)

# The row's state between the insert and the response. Not emitted by
# `kalshi/orders.py` -- it exists only in the table, and only for the window in
# which we have sent something and do not yet know what happened.
STATUS_PENDING = "pending"

# Statuses that are **finished and cost nothing**. Everything else counts
# towards exposure, including anything added later and anything unrecognised.
#
# Written as the closed set rather than the open one on purpose. The previous
# version listed the statuses that *do* count -- `('pending','resting','filled')`
# -- which silently omitted `partially_filled` (a filled leg and a resting leg,
# both at risk) and `unrecognised_response`. That second one is the whole
# argument: it means "the response could not be read, so this order may have
# filled", and an enumeration of what counts drops it to zero. A new status
# added to `kalshi/orders.py` a year from now defaults to counting, which is the
# direction that refuses an order rather than permitting one.
TERMINAL_STATUSES = ("unfilled", "rejected", "canceled")

# V2 expresses a market order by omitting `price`. This repo never omits it --
# `OrderRequest` cannot be constructed without a tradeable limit -- so every row
# this module writes is a limit order.
ORDER_TYPE_LIMIT = "limit"


class OrderNotRecorded(RuntimeError):
    """The order could not be written down, so it must not be sent."""


def record_intent(
    conn: sqlite3.Connection,
    order: OrderRequest,
    *,
    dry_run: bool,
    submitted_ms: int,
) -> int:
    """Write the order we are about to place. Returns the row id.

    Raises `OrderNotRecorded` rather than returning a sentinel. There is no
    value this can return that means "not recorded" and is safe to place an
    order on: the evidence record is the entire product of this project, and an
    order missing from it is a position nobody can reconcile, cancel or score.

    A plain `INSERT`, never `INSERT OR IGNORE`. A collision on
    `client_order_id` is a genuine event -- two orders sharing an idempotency
    key -- and `OR IGNORE` would suppress it along with the `NOT NULL`
    violations that say the row is incomplete. See `tasks/lessons.md`.
    """
    body = order.to_api_dict()
    try:
        cursor = conn.execute(
            "INSERT INTO orders ("
            "client_order_id, recommendation_id, submitted_ms, ticker, side, "
            "action, order_type, count, limit_price_tenths, status, "
            "request_body_json, dry_run"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                order.client_order_id,
                order.recommendation_id,
                int(submitted_ms),
                order.ticker,
                order.side,
                order.action,
                ORDER_TYPE_LIMIT,
                int(order.count),
                # Our side, post-snap. See the module docstring.
                int(order.fill_price_tenths),
                STATUS_PENDING,
                canonical_body_json(body),
                1 if dry_run else 0,
            ),
        )
        conn.commit()
    except sqlite3.Error as exc:
        raise OrderNotRecorded(
            f"could not record the order for {order.ticker} "
            f"(client_order_id={order.client_order_id}): {exc}"
        ) from exc

    row_id = cursor.lastrowid
    if row_id is None:
        raise OrderNotRecorded(
            f"the insert for {order.ticker} reported no row id, so the order "
            f"cannot be updated with its outcome"
        )
    return int(row_id)


def record_outcome(
    conn: sqlite3.Connection, order_row_id: int, outcome: OrderOutcome
) -> None:
    """Stamp the placed order with what came back.

    Raises on failure. The **caller** decides what that means, and the answer
    differs by when it happens: a failed `record_intent` stops the order, while
    a failed `record_outcome` must not, because by then the request has already
    gone. The row is already on disk in `pending` with the idempotency key,
    which is the state reconciliation was designed to read.
    """
    try:
        conn.execute(
            "UPDATE orders SET status = ?, kalshi_order_id = ?, error_text = ? "
            "WHERE id = ?",
            (
                outcome.status,
                outcome.kalshi_order_id,
                outcome.error_text,
                int(order_row_id),
            ),
        )
        conn.commit()
    except sqlite3.Error as exc:
        raise OrderNotRecorded(
            f"order row {order_row_id} was placed and its outcome "
            f"({outcome.status}) could not be recorded: {exc}"
        ) from exc


def order_exposure_dollars(order: OrderRequest) -> float:
    """What one order contributes to exposure.

    Exists so a ticket can say "this would take you to $X" using the **same
    arithmetic** the sum below applies, rather than a second expression written
    beside it. The two cannot literally share an implementation -- one is
    Python and one is SQL -- so `TestOneOrderSumsToWhatItContributes` asserts
    they agree on a row that has actually been through `record_intent`.

    Fee-exclusive, matching the column. `size_position` spends the cap at the
    fee-*inclusive* price, so exposure accumulates slightly less than it
    consumed -- roughly 2% of stake at a 1c fee on a 50c contract. Correcting
    it needs a fee column on `orders`; it is recorded rather than migrated,
    because the cap it distorts is one no live order has ever reached.
    """
    return order.count * order.fill_price_tenths / float(PRICE_MAX)


def current_exposure_dollars(conn: sqlite3.Connection) -> Optional[float]:
    """Money currently at risk, or `None` if it cannot be read.

    **This is the only definition of exposure in the project**, and until now
    there were two. `runner.py` summed `fills` net of `settlements`; the order
    endpoint summed live `orders`. Both were vacuous while no table had a row,
    so they had never disagreed -- but they answer different questions and
    would have diverged the moment orders were written, with the runner sizing
    recommendations against one number and the endpoint sizing the resulting
    order against another.

    `orders` is the right table for a **pre-trade** cap. A resting order can
    fill at any moment, so capital committed to one is committed; counting
    fills alone would let a hundred resting orders each size against zero
    exposure, which is the classic way to be a hundred times over the limit
    while every individual check passed. Counting the order at its **limit**
    price rather than its fill price over-states it slightly -- a fill is never
    worse than the limit -- and a risk cap should over-state.

    `fills` is left to do the job its schema comment describes: measuring
    `fee_actual` against `fee_predicted`. It is not a second exposure source.

    `None` is a refusal, never zero. An exposure that cannot be read and an
    exposure of zero look identical to a cap check, and only one of them is
    safe to act on -- "cannot determine the budget" must not resolve to
    "unlimited".

    **Dry runs are excluded, and that is a limitation rather than a detail.**
    Every order this project has placed is a dry run, so this returns `0.0` in
    production today and `max_exposure_dollars` still does not bind there.
    Counting paper orders would make it bind, and would be worse: nothing
    settles a paper position, so paper exposure could only ratchet up until the
    endpoint refused everything with no way to release it. A cap that can only
    close is an off switch. The prerequisite for paper exposure is a paper
    settlement path, not a change here.
    """
    placeholders = ", ".join("?" for _ in TERMINAL_STATUSES)
    try:
        row = conn.execute(
            f"""
            SELECT
                COALESCE(SUM(o.count * o.limit_price_tenths / 1000.0), 0.0)
                    AS at_risk,
                -- `SUM` skips NULLs, so a row with no price would contribute
                -- nothing and read as an order costing zero dollars. Counted
                -- separately so it refuses instead.
                COALESCE(SUM(CASE WHEN o.limit_price_tenths IS NULL
                                  THEN 1 ELSE 0 END), 0) AS unpriced
            FROM orders o
            WHERE o.dry_run = 0
              AND o.status NOT IN ({placeholders})
              -- Settling the market releases the capital. Carried over from
              -- the implementation this replaces, including its approximation:
              -- `settlements` has no order reference, so every order on a
              -- ticker is released together. Nothing writes that table yet, so
              -- today this term releases nothing.
              AND NOT EXISTS (
                  SELECT 1 FROM settlements s WHERE s.ticker = o.ticker
              )
            """,
            TERMINAL_STATUSES,
        ).fetchone()
    except Exception:                                   # noqa: BLE001
        logger.exception("could not read current exposure")
        return None

    if row is None or row["at_risk"] is None or row["unpriced"] is None:
        return None
    if row["unpriced"]:
        logger.error(
            "%d live order(s) carry no limit price, so exposure cannot be "
            "summed. Refusing rather than treating an unreadable price as a "
            "free position.",
            row["unpriced"],
        )
        return None
    return float(row["at_risk"])
