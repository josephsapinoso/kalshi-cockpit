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

**Exposure is fee-inclusive**, because the cap is spent that way. `size_position`
bounds `contracts * effective_price` and `effective_price` includes the fee, so a
sum of bare stake accumulated about 2% less than it consumed. `count` and
`limit_price_tenths` are between them everything `calculate_fee` takes, so the
fee needed no column of its own -- what it needed was for the sum to stop being
SQL, since the fee is a maximum across candidate models with a per-order
rounding step. See `exposure_contribution`.

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

from ..core.fees import calculate_fee
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

# The only fill assumption this project has. Named rather than implied: a dry
# run never rests in a book, so "did it fill" has no observed answer, and any
# answer is a policy. `docs/adr/0010` sets out why this one is defensible and
# where it is optimistic.
#
# It says: filled in full, at the order's own limit, because `POST /api/orders`
# refuses when the resting size at our price is smaller than the order -- so
# every order this project writes is a marketable limit inside the depth we
# just observed. `assumed_filled_count` is therefore `count` on every row today,
# which is a measured `0 of N differ` rather than a coincidence to rely on: the
# two are separate columns so the day a partial-fill policy exists, neither
# changes meaning.
DEPTH_CAPPED_TAKER = "depth_capped_taker"

# Every order this project places is a dry run, and the decision lives here
# rather than at the two call sites that used to hardcode it.
#
# It is load-bearing in a way a literal `True` hides: it selects which
# **exposure population** an order sizes against. The order endpoint's advisory
# read and `reserve_order`'s authoritative check must agree about that, and two
# hardcoded booleans in two files are free to stop agreeing -- at which point an
# order is sized against one budget and admitted against another.
ORDERS_ARE_DRY_RUNS = True

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
            "request_body_json, dry_run, idempotency_key, fill_assumption, "
            "assumed_filled_count"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                # Written with the intent, not at settlement, because it
                # describes how this order will be *read* and that has to be
                # fixed before the outcome is known. Deciding it afterwards is
                # how a record gets scored under whichever assumption suits it.
                DEPTH_CAPPED_TAKER,
                int(order.count),
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

    - **It compares like with like, and that is what makes it able to fire.**
      The exposure read below takes this call's own `dry_run`, so a paper order
      is checked against paper positions and a live order against live ones.
      It used to count `dry_run = 0` unconditionally, which meant a paper order
      contributed nothing to the sum it was checked against and this refusal
      could not fire in production at all. It can now -- on paper, which is the
      point: a money guard that has never executed is not defence in depth.
      Paper exposure is only safe to count because `backend/settlement.py`
      releases it; see ADR 0010.

    - **It still says nothing about live risk.** Paper positions are not
      capital. The two populations are never pooled, so a live order's budget is
      untouched by however much fictional exposure is outstanding.
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
            exposure = current_exposure_dollars(conn, dry_run=dry_run)
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


def exposure_contribution(
    count: int, price_tenths: Optional[int]
) -> Optional[float]:
    """What one open order commits, fee included. `None` if it cannot be read.

    **This is the only arithmetic for exposure in the project.** It used to be
    two: a Python expression for the ticket's "this would take you to $X" and a
    SQL `SUM` for the cap that later refuses it, pinned against each other by a
    test. They agreed. They also both left the fee out, and the test agreed with
    that too -- which is what a test comparing two paths can never catch.

    **Fee-inclusive, and that is the fix.** `core.sizing.size_position` spends
    the cap at `effective_price`, which includes the fee, while exposure summed
    the bare stake. So the cap was consumed at one price and accumulated at
    another, and the gap ran about 2% of stake -- a 1c fee on a 50c contract.
    Small, one-directional, and in the unsafe direction: every order left the
    portfolio slightly more exposed than the number the next order sized
    against.

    No migration was needed for it, contrary to what this module used to say.
    `limit_price_tenths` already holds the post-snap price of our own side and
    `count` sits beside it, which is everything `calculate_fee` takes.

    **Taker rates, always.** Every order this project sends is marketable, and
    where that were ever untrue the taker fee is the larger of the two, which is
    the direction a cap should err in.

    `None`, never `0.0`, when the price is unreadable or untradeable --
    `calculate_fee` returns `None` there for exactly this reason, and a caller
    that substituted zero would report an open order as a free position.
    """
    if price_tenths is None:
        return None
    fee = calculate_fee(int(price_tenths), int(count))
    if fee is None:
        return None
    return count * int(price_tenths) / float(PRICE_MAX) + fee


def order_exposure_dollars(order: OrderRequest) -> Optional[float]:
    """What one order contributes to exposure, before it is written.

    Calls `exposure_contribution` on the same two values `_insert_intent`
    stores, so the ticket's projection and the cap that later refuses it are
    the same number by construction rather than by agreement.
    """
    return exposure_contribution(order.count, order.fill_price_tenths)


def current_exposure_dollars(
    conn: sqlite3.Connection, *, dry_run: bool = False
) -> Optional[float]:
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

    **`dry_run` selects the population, and the two are never pooled.** An
    order sizes against exposure of its own kind: a paper order against paper
    positions, a live order against live ones. One implementation, parameterised
    -- not a second function, which is how this project came to have two
    definitions of exposure that agreed only because both returned zero.

    Paper exposure counts at all only because `backend/settlement.py` now closes
    paper positions (ADR 0010). ADR 0008 was right to refuse it while nothing
    did: exposure that can only ratchet up is a cap that can only close, which
    is an off switch. What it buys is that `max_exposure_dollars` **binds in
    production**, on paper, before it ever guards real money -- this repo has
    twice shipped a money guard that could not fire and read as defence in
    depth.

    Pooling them would be unsafe in the direction that matters: the first live
    order would size against a budget already consumed by fictional positions,
    and be refused for a fictional reason.
    """
    placeholders = ", ".join("?" for _ in TERMINAL_STATUSES)
    try:
        # Rows, not a `SUM`. The fee is the maximum across candidate models with
        # a per-order rounding step, which SQL cannot express -- and a second
        # expression of it in SQL is exactly the duplicate this function was
        # created to delete. The row count is bounded by the cap itself, so
        # summing in Python costs nothing worth measuring.
        rows = conn.execute(
            f"""
            SELECT o.id, o.count, o.limit_price_tenths
            FROM orders o
            WHERE o.dry_run = ?
              AND o.status NOT IN ({placeholders})
              -- Settling the position releases its capital. Joined on
              -- `order_id`, which is what schema v4 added: the old form matched
              -- on `ticker`, so one settlement released **every** order on that
              -- market. Correct while there was one order per ticker and wrong
              -- the moment there were two -- and two is ordinary, because a
              -- quote pass re-recommends a market minutes later.
              AND NOT EXISTS (
                  SELECT 1 FROM settlements s WHERE s.order_id = o.id
              )
            """,
            # `dry_run` binds before the statuses because its `?` comes first in
            # the WHERE clause. Positional binding does not check names, so the
            # wrong order here compares a status string against an integer
            # column and silently returns 0.0 -- a readable, plausible, unlimited
            # budget.
            (1 if dry_run else 0, *TERMINAL_STATUSES),
        ).fetchall()
    except Exception:                                   # noqa: BLE001
        logger.exception("could not read current exposure")
        return None

    total = 0.0
    for row in rows:
        contribution = exposure_contribution(row["count"], row["limit_price_tenths"])
        if contribution is None:
            # One unreadable row refuses the whole sum. Skipping it would
            # report a smaller exposure than the truth and hand the next order
            # room it does not have -- the same shape as an unreadable price
            # resolving to zero, one level up.
            logger.error(
                "order %s has no usable price (count=%r, limit_price_tenths=%r), "
                "so exposure cannot be summed. Refusing rather than treating an "
                "unreadable order as a free position.",
                row["id"], row["count"], row["limit_price_tenths"],
            )
            return None
        total += contribution
    return total
