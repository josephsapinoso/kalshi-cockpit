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
- **It does not write `fills` for a paper position, and nothing settles one.**
  `settlements` has no writer, so paper exposure could only ever accumulate.
  That is why dry runs are excluded from the sum rather than counted.

Two keys, because there are two parties to deduplicate against
--------------------------------------------------------------
`client_order_id` is minted here and sent to Kalshi. It stops **the exchange**
creating a second order when we re-send after a lost response.

`idempotency_key` comes from the client and the exchange never sees it. It stops
**us** creating a second order when the phone is tapped twice — which the first
key cannot do anything about, because each request minted a fresh one, so two
taps were two ids and two orders. A duplicate key is answered with the first
attempt's recorded response rather than with a second order.

Neither substitutes for the other and the failure they cover is different. It is
worth being concrete: a double-tap is two requests seconds apart with two
`client_order_id`s, which Kalshi will happily accept as two distinct orders.

What it does now do, having not before: **serialise two orders against one
exposure reading**. `reserve_order` writes the row and then checks the cap
against the portfolio *including* it, in one transaction, so a second request
blocks on the first's write lock and reads a total that contains it.
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


class DuplicateOrder(RuntimeError):
    """This idempotency key has already been used. Carries the existing row.

    Not an error in the sense of something going wrong -- it is the mechanism
    working. Two taps on a phone are one intent, and the second one has to be
    answered with the first one's outcome rather than with a second order.

    `response_body_json` is `None` when the original attempt never got as far as
    answering. That case is *not* safe to retry and the caller must not treat it
    as one: an order may be resting on the exchange under this row's
    `client_order_id`.
    """

    def __init__(self, row: sqlite3.Row):
        self.row = row
        self.response_body_json: Optional[str] = row["response_body_json"]
        super().__init__(
            f"order row {row['id']} already exists for this idempotency key "
            f"(status={row['status']}, client_order_id={row['client_order_id']})"
        )


class ExposureCapExceeded(RuntimeError):
    """Recording this order would put the portfolio over its exposure cap.

    Distinct from `OrderNotRecorded` because the two mean opposite things about
    the database: this one means the write *worked* and was deliberately rolled
    back, so there is no orphan row and no order was sent. A caller that
    conflated them would report a storage failure for a risk refusal.
    """

    def __init__(self, message: str, *, exposure_after: float, cap: float):
        super().__init__(message)
        self.exposure_after = exposure_after
        self.cap = cap


def find_by_idempotency_key(
    conn: sqlite3.Connection, key: str
) -> Optional[sqlite3.Row]:
    """The order already recorded under this key, if there is one.

    Read on the endpoint's read-only handle **before any other check runs**, and
    the ordering is the whole point rather than an optimisation. A retry after a
    lost response arrives seconds or minutes later, by which time the
    recommendation behind it has aged past the 30s quote limit -- so a replay
    placed after the freshness checks would answer "the price moved" to the one
    request that must be answered with the original outcome.

    Returns the row, not a boolean, because what the caller needs is the answer
    it gave last time.
    """
    return conn.execute(
        "SELECT * FROM orders WHERE idempotency_key = ?", (key,)
    ).fetchone()


def record_response(
    conn: sqlite3.Connection, order_row_id: int, body_json: str
) -> None:
    """Store the answer this order was given, for a later replay to return.

    Failing here is reported by the caller, never raised past it, for the same
    reason `record_outcome` is: by the time there is a response to store, the
    request has already gone. What is lost is the ability to *replay* the answer
    -- a subsequent duplicate tap will find the row with a NULL response and
    refuse rather than send a second order, which is the safe direction.
    """
    try:
        conn.execute(
            "UPDATE orders SET response_body_json = ? WHERE id = ?",
            (body_json, int(order_row_id)),
        )
        conn.commit()
    except sqlite3.Error as exc:
        raise OrderNotRecorded(
            f"order row {order_row_id} was placed and its response could not "
            f"be stored: {exc}"
        ) from exc


def record_intent(
    conn: sqlite3.Connection,
    order: OrderRequest,
    *,
    dry_run: bool,
    submitted_ms: int,
    idempotency_key: Optional[str] = None,
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

    Prefer `reserve_order` on the money path: this commits on its own, so the
    exposure read that sized the order and the row that consumes the budget
    land in two different transactions.
    """
    row_id = _insert_intent(
        conn, order, dry_run=dry_run, submitted_ms=submitted_ms,
        idempotency_key=idempotency_key,
    )
    try:
        conn.commit()
    except sqlite3.Error as exc:
        raise OrderNotRecorded(
            f"could not commit the order for {order.ticker} "
            f"(client_order_id={order.client_order_id}): {exc}"
        ) from exc
    return row_id


def _insert_intent(
    conn: sqlite3.Connection,
    order: OrderRequest,
    *,
    dry_run: bool,
    submitted_ms: int,
    idempotency_key: Optional[str] = None,
) -> int:
    """The insert alone, so a caller can decide when it becomes durable."""
    body = order.to_api_dict()
    try:
        cursor = conn.execute(
            "INSERT INTO orders ("
            "client_order_id, recommendation_id, submitted_ms, ticker, side, "
            "action, order_type, count, limit_price_tenths, status, "
            "request_body_json, dry_run, idempotency_key"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                idempotency_key,
            ),
        )
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


def reserve_order(
    conn: sqlite3.Connection,
    order: OrderRequest,
    *,
    dry_run: bool,
    submitted_ms: int,
    max_exposure_dollars: float,
    idempotency_key: Optional[str] = None,
) -> int:
    """Record the order and check the cap **in one write transaction**.

    The hole this closes: the endpoint read exposure, sized against it, then
    inserted on a different connection. Two requests arriving together each
    read the same snapshot, each sized as though the other did not exist, and
    both inserted -- so `max_exposure_dollars` bounded each order separately
    and bounded the portfolio not at all. Nothing about that is exotic; it is
    two taps on a phone, or a tap and a retry.

    **What makes it correct is the order of the two statements, not the word
    IMMEDIATE.** That is worth stating plainly because it is the opposite of
    what the code looks like it is saying. The insert comes first, so it takes
    the write lock, so the second connection blocks *before* it can read
    anything -- and the exposure it then reads includes the first order.
    Measured: swapping `IMMEDIATE` for a deferred `BEGIN` leaves the
    concurrency test green, and removing the post-insert check turns it red
    with both requests accepted, which is the defect exactly.

    `IMMEDIATE` stays anyway, and not as decoration. The natural next edit to
    this function is to read something before writing -- a position count, a
    daily-loss total -- and under a deferred transaction that read would
    succeed, the upgrade to a write would then fail with `SQLITE_BUSY`, and by
    that point the stale read has already happened. Taking the lock at the door
    makes the ordering of statements inside stop mattering.

    **The check runs after the insert, deliberately.** Reading exposure and
    then deciding whether to write is the same race one level in, decided by
    whether two statements in one transaction happen to interleave. Writing
    first and asking "what is the total *now*" makes the answer a fact about
    the database rather than a prediction about it, and rolling back is exact.

    The sizer's own exposure read stays where it is and stays advisory. That is
    the useful division: the sizer decides how big an order should be, this
    decides whether the portfolio can hold it, and only the second one has to
    be atomic.

    **The duplicate check is inside the same lock, and it has to be.** The
    endpoint looks the key up first on its read-only handle, which is what makes
    a replay cheap and what makes it survive a stale recommendation -- but that
    read cannot be the guarantee, because two taps landing together both miss
    it. Here the second request is already blocked at `BEGIN IMMEDIATE` behind
    the first's write lock, so by the time it looks, the first row exists. Same
    argument as the exposure check below it, for the same reason: the answer has
    to be a fact about the database rather than a prediction about it.

    The `UNIQUE` index is the third layer and is not redundant with either. It
    is what keeps the property true for `record_intent`, which commits on its
    own and does not pass through here at all.

    What this does **not** do, stated because the shape invites assuming
    otherwise:

    - **It cannot bind on a dry run.** `current_exposure_dollars` counts only
      `dry_run = 0`, so a dry-run row contributes nothing to the sum it is
      checked against. That is correct rather than a limitation -- a dry run
      commits no capital -- but it does mean this refusal has never fired in
      production and cannot until a live order exists.
    """
    previous_isolation = conn.isolation_level
    # Explicit transaction control. Left at the sqlite3 default, the module
    # opens its own deferred transaction before the INSERT and the `BEGIN
    # IMMEDIATE` below would either be swallowed or raise "cannot start a
    # transaction within a transaction", depending on the interpreter.
    conn.isolation_level = None
    try:
        try:
            conn.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as exc:
            raise OrderNotRecorded(
                f"could not take the write lock to record the order for "
                f"{order.ticker}: {exc}"
            ) from exc

        if idempotency_key is not None:
            existing = find_by_idempotency_key(conn, idempotency_key)
            if existing is not None:
                conn.execute("ROLLBACK")
                raise DuplicateOrder(existing)

        try:
            row_id = _insert_intent(
                conn, order, dry_run=dry_run, submitted_ms=submitted_ms,
                idempotency_key=idempotency_key,
            )
            exposure = current_exposure_dollars(conn)
        except Exception:
            conn.execute("ROLLBACK")
            raise

        if exposure is None:
            conn.execute("ROLLBACK")
            raise OrderNotRecorded(
                f"exposure could not be read after inserting the order for "
                f"{order.ticker}, so the cap cannot be applied. Rolled back: "
                f"'cannot determine the budget' must never resolve to "
                f"'unlimited'."
            )

        if exposure > max_exposure_dollars:
            conn.execute("ROLLBACK")
            raise ExposureCapExceeded(
                f"recording this order would take total exposure to "
                f"${exposure:.2f} against a ${max_exposure_dollars:.2f} cap. "
                f"Another order was recorded between this one being sized and "
                f"being written. Nothing was sent and the row was rolled back.",
                exposure_after=exposure,
                cap=max_exposure_dollars,
            )

        try:
            conn.execute("COMMIT")
        except sqlite3.Error as exc:
            raise OrderNotRecorded(
                f"could not commit the order for {order.ticker} "
                f"(client_order_id={order.client_order_id}): {exc}"
            ) from exc
        return row_id
    finally:
        conn.isolation_level = previous_isolation


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
