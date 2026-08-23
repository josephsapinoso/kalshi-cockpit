"""The manual order path's store (ADR 0063).

A hand bet placed through the portal, recorded in its own table with its own
dry-run constant. Separate from `store/orders.py` on purpose and permanently:
the engine table feeds `gate.py`'s evidence populations and the exposure
predicate the automated path sizes against, and a hand row in that table
would count Joe's discretion into the interlock's own counters (ADR 0043
records the near-miss on `fills`). What IS shared is imported from
`store/orders.py` by name — the fee-inclusive `exposure_contribution`, the
`TERMINAL_STATUSES` convention, the exception types — so the two paths
cannot drift on arithmetic while staying separate on population.

WHAT THIS MODULE DOES NOT ESTABLISH
-----------------------------------
- Nothing about whether an order SHOULD go: the route runs the checks
  (lockout, daily loss, caps, depth, price ceiling); this records and
  bounds.
- Nothing about the venue's response shape: `MANUAL_ORDERS_ARE_DRY_RUNS`
  stays True until the C0 probe has observed a real create-order response
  (ADR 0063's blocking prerequisite P2) and Joe arms the path by code
  change.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any, Optional

from ..kalshi.orders import OrderOutcome, OrderRequest, canonical_body_json
from .orders import (
    DuplicateOrder,
    ExposureCapExceeded,
    OrderNotRecorded,
    TERMINAL_STATUSES,
    exposure_contribution,
)

logger = logging.getLogger(__name__)

# The manual path's own arming switch (ADR 0063). A code change, exactly as
# ORDERS_ARE_DRY_RUNS is for the engine path (ADR 0018's pattern): flipping
# it requires a commit and a deploy, and tests/test_manual_orders.py pins
# that no production call site passes anything else.
MANUAL_ORDERS_ARE_DRY_RUNS = True

STATUS_PENDING = "pending"

# After any completed manual purchase the buy control rests (ADR 0063's
# cool-off; no override). "Completed" means the order was actually carried
# to an outcome — including a dry run, so the friction is rehearsed exactly
# as it will bind live. A refusal spends nothing and cools nothing.
COOLOFF_MS = 10 * 60 * 1000


def find_by_idempotency_key(
    conn: sqlite3.Connection, idempotency_key: str
) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM manual_orders WHERE idempotency_key = ?",
        (idempotency_key,),
    ).fetchone()


def last_completed_ms(conn: sqlite3.Connection) -> Optional[int]:
    """When the most recent carried-to-outcome manual order was submitted.

    `pending` rows count too: a pending row means a request left this
    process and its outcome is unknown, which must cool the control rather
    than invite a second tap. Only `rejected` is excluded — nothing went out.
    """
    row = conn.execute(
        "SELECT MAX(submitted_ms) AS ms FROM manual_orders "
        "WHERE status != 'rejected'"
    ).fetchone()
    return int(row["ms"]) if row and row["ms"] is not None else None


def cooloff_until_ms(conn: sqlite3.Connection, *, now_ms: int) -> Optional[int]:
    """The instant the buy control unlocks, or None when it is free now."""
    last = last_completed_ms(conn)
    if last is None:
        return None
    release = last + COOLOFF_MS
    return release if release > now_ms else None


def current_manual_exposure_dollars(
    conn: sqlite3.Connection, *, dry_run: bool
) -> Optional[float]:
    """Fee-inclusive dollars committed by open manual orders of this kind.

    Same shape as `orders.current_exposure_dollars`: a row whose price
    cannot be read poisons the sum to `None` — "cannot determine the
    committed total" must never resolve to a smaller number. Terminal
    statuses stop counting; unknown statuses keep counting (the closed-set
    convention imported from the engine store).
    """
    rows = conn.execute(
        "SELECT count, limit_price_tenths FROM manual_orders "
        f"WHERE dry_run = ? AND status NOT IN ({','.join('?' * len(TERMINAL_STATUSES))})",
        (1 if dry_run else 0, *TERMINAL_STATUSES),
    ).fetchall()
    total = 0.0
    for row in rows:
        part = exposure_contribution(int(row["count"]), row["limit_price_tenths"])
        if part is None:
            return None
        total += part
    return total


def _insert_intent(
    conn: sqlite3.Connection,
    order: OrderRequest,
    *,
    dry_run: bool,
    submitted_ms: int,
    max_price_tenths: int,
    p_yes_bp: int,
    idempotency_key: Optional[str],
) -> int:
    cursor = conn.execute(
        "INSERT INTO manual_orders ("
        " client_order_id, submitted_ms, ticker, side, action, count,"
        " limit_price_tenths, max_price_tenths, p_yes_bp, status,"
        " request_body_json, dry_run, idempotency_key"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            order.client_order_id,
            submitted_ms,
            order.ticker,
            order.side,
            order.action,
            order.count,
            order.fill_price_tenths,
            max_price_tenths,
            p_yes_bp,
            STATUS_PENDING,
            canonical_body_json(order.to_api_dict()),
            1 if dry_run else 0,
            idempotency_key,
        ),
    )
    return int(cursor.lastrowid)


def reserve_manual_order(
    conn: sqlite3.Connection,
    order: OrderRequest,
    *,
    dry_run: bool,
    submitted_ms: int,
    max_exposure_dollars: float,
    max_price_tenths: int,
    p_yes_bp: int,
    idempotency_key: Optional[str] = None,
) -> int:
    """Record the manual order and check the cap in one write transaction.

    The same insert-then-check-under-BEGIN-IMMEDIATE shape as
    `orders.reserve_order`, whose docstring carries the full argument (two
    taps landing together must serialise on the write lock, and the exposure
    read after the insert is a fact rather than a prediction). The
    population checked is `manual_orders` only — the engine's paper and live
    exposure live in their own table and their own budget.
    """
    previous_isolation = conn.isolation_level
    conn.isolation_level = None
    try:
        try:
            conn.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as exc:
            raise OrderNotRecorded(
                f"could not take the write lock to record the manual order "
                f"for {order.ticker}: {exc}"
            ) from exc

        if idempotency_key is not None:
            existing = find_by_idempotency_key(conn, idempotency_key)
            if existing is not None:
                conn.execute("ROLLBACK")
                raise DuplicateOrder(existing)

        try:
            row_id = _insert_intent(
                conn,
                order,
                dry_run=dry_run,
                submitted_ms=submitted_ms,
                max_price_tenths=max_price_tenths,
                p_yes_bp=p_yes_bp,
                idempotency_key=idempotency_key,
            )
            exposure = current_manual_exposure_dollars(conn, dry_run=dry_run)
        except Exception:
            conn.execute("ROLLBACK")
            raise

        if exposure is None:
            conn.execute("ROLLBACK")
            raise OrderNotRecorded(
                f"manual exposure could not be read after inserting the order "
                f"for {order.ticker}; rolled back — 'cannot determine the "
                f"budget' must never resolve to 'unlimited'."
            )

        if exposure > max_exposure_dollars:
            conn.execute("ROLLBACK")
            raise ExposureCapExceeded(
                f"recording this order would take open manual exposure to "
                f"${exposure:.2f} against a ${max_exposure_dollars:.2f} cap. "
                f"Nothing was sent and the row was rolled back.",
                exposure_after=exposure,
                cap=max_exposure_dollars,
            )

        try:
            conn.execute("COMMIT")
        except sqlite3.Error as exc:
            raise OrderNotRecorded(
                f"could not commit the manual order for {order.ticker} "
                f"(client_order_id={order.client_order_id}): {exc}"
            ) from exc
        return row_id
    finally:
        conn.isolation_level = previous_isolation


def record_outcome(
    conn: sqlite3.Connection, row_id: int, outcome: OrderOutcome
) -> None:
    """Stamp the row with what came back. Must not unwind the order — by now
    the request has gone (same contract as `orders.record_outcome`)."""
    try:
        conn.execute(
            "UPDATE manual_orders SET status = ?, kalshi_order_id = ?, "
            "error_text = ? WHERE id = ?",
            (
                outcome.status,
                outcome.kalshi_order_id,
                outcome.error_text,
                int(row_id),
            ),
        )
        conn.commit()
    except sqlite3.Error as exc:
        raise OrderNotRecorded(
            f"manual order row {row_id} was placed and its outcome "
            f"({outcome.status}) could not be recorded: {exc}"
        ) from exc


def record_response(
    conn: sqlite3.Connection, row_id: int, response_body_json: str
) -> None:
    """Store the exact answer the caller got, for idempotent replay."""
    try:
        conn.execute(
            "UPDATE manual_orders SET response_body_json = ? WHERE id = ?",
            (response_body_json, int(row_id)),
        )
        conn.commit()
    except sqlite3.Error as exc:
        raise OrderNotRecorded(
            f"manual order row {row_id}'s response could not be stored for "
            f"replay: {exc}"
        ) from exc


def replay_response(row: sqlite3.Row) -> Optional[dict[str, Any]]:
    """The stored answer for a duplicate request, or None when the first
    attempt never got as far as answering — the caller must refuse rather
    than send a second order ("we do not know whether it went" must not
    resolve to "it did not")."""
    import json

    raw = row["response_body_json"] if "response_body_json" in row.keys() else None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None
