"""Resting bids on a combination market -- the only way into an enter-only book.

ADR 0084. Every real order this project had sent before this was
immediate-or-cancel: it filled against visible depth or it died, and nothing
outlived the request. That is unusable on a combination, because **no
combination book this repo has read carried a resting YES bid -- 40 of 40**
(ADR 0012 section 5). There is no offer to hit. The only way in is to become
the offer: rest a limit bid at a price Joe chooses and wait for someone to take
it.

Measured before this module existed (2026-08-30, the probe in
`scripts/probe_resting_combo_order.py`): a combination accepts a resting GTC
bid -- 201, `remaining_count 1.00`, status `resting` -- and gives it back on
cancel with `reduced_by 1.00`. So this is built on an observation, not on the
assumption that a combination behaves like a football game.

THREE BOUNDARIES, AND NONE OF THEM IS ETIQUETTE
-----------------------------------------------
- **`gate.py` may never read this table.** A resting bid is Joe's discretion,
  not evidence; the live-trading interlock counts neither. Same boundary
  `manual_orders` has, for the same reason (ADR 0063).
- **Separate from `manual_orders`.** Those rows are all IOC and therefore all
  finished; `manual-orders-audit` counts them as such. A row that can still be
  working would make every count in that census ambiguous.
- **This module moves no money between exchange shards.** Kalshi requires
  collateral to be preallocated on the shard a market trades on, and a
  cross-shard transfer runs in up to three non-atomic steps that are not
  rolled back on failure. The desk reads the shard balance and REFUSES in
  words; the transfer is the operator's to make.

WHAT THIS MODULE DOES NOT ESTABLISH
-----------------------------------
- **That a resting bid ever fills.** No combination book this repo has read had
  a resting YES bid, which is the same fact that makes a bid necessary and
  makes it unlikely to be taken. A bid that never fills costs nothing and
  proves nothing.
- **What a fill would cost in fees.** ADR 0046 keeps the combination fee model
  unverified, and Kalshi's 2026-08-22 changelog puts the combo maker multiplier
  at 0.5 rather than the standard 0.25 -- unreconciled with `core/fees.py`.
- **That the price Joe picks is a good one.** It is his number. The card's fair
  value is shown beside it and the desk ranks nothing by their difference
  (ADR 0071 section 2.5).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from ..kalshi.rest import EXCHANGE_INDEX_COMBOS

#: Live orders may be placed only when this is False, and flipping it is a code
#: change with a commit behind it -- the `MANUAL_ORDERS_ARE_DRY_RUNS`
#: convention (ADR 0063), for the same reason: an environment variable is a
#: thing somebody can nudge at 2am.
#:
#: **Starts True.** A resting order is the first order shape in this repo that
#: can fill while nobody is watching, so it rehearses dry before it is armed.
COMBO_ORDERS_ARE_DRY_RUNS = True

#: The most a single resting bid may commit, in tenths of a cent.
#:
#: The same $3.00 ceiling `MANUAL_ORDER_MAX_SPEND_TENTHS` sets, and deliberately
#: the same number rather than a new one: it is the top of the range Joe named
#: for a parlay stake, and a resting bid is the same bet through a different
#: door. A second, larger ceiling reachable through a new route would be the
#: cap being raised by accident.
COMBO_ORDER_MAX_SPEND_TENTHS = 3_000

#: The structural ceiling in contracts, not the binding one. The spend cap
#: above binds; this stops a market priced at a tenth of a cent turning $3 into
#: thirty thousand contracts, which is a different kind of order even when the
#: money is small. Matches `manual_orders.COMBO_MAX_CONTRACTS`.
COMBO_ORDER_MAX_CONTRACTS = 250

STATUS_PENDING = "pending"
STATUS_RESTING = "resting"
STATUS_FILLED = "filled"
STATUS_PARTIALLY_FILLED = "partially_filled"
STATUS_CANCELLED = "cancelled"
STATUS_REJECTED = "rejected"
STATUS_DRY_RUN = "dry_run"

#: Statuses that can no longer change on their own. Anything outside this set
#: is still working and still counts against exposure.
TERMINAL_STATUSES = frozenset(
    {STATUS_FILLED, STATUS_CANCELLED, STATUS_REJECTED, STATUS_DRY_RUN}
)


class ComboOrderRefused(Exception):
    """A refusal with words a screen can print. Never a bare 500."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class ShardFunds:
    """What one exchange shard can actually pay for.

    **The unscoped balance is the SUM across shards and cannot pay for
    anything.** Measured 2026-08-30: the account read $21.4120 in total while
    the combinations shard held $0.0100, and a 2c order was refused
    `insufficient_balance`. A preflight that trusted the total would send an
    order the venue was always going to reject, after Joe had typed a price and
    tapped confirm.
    """

    exchange_index: int
    available_tenths: Optional[int]

    @property
    def is_readable(self) -> bool:
        return self.available_tenths is not None


def read_shard_funds(payload: Any, *, exchange_index: int) -> ShardFunds:
    """The spendable balance on one shard, from a `/portfolio/balance` payload.

    **Unreadable resolves to `None`, never to `0`.** A zero here reads as "this
    shard is empty", which is a fact; an unparsed payload is not that fact, and
    the caller must refuse rather than tell Joe his money is gone.
    """
    rows = None
    if isinstance(payload, dict):
        rows = payload.get("balance_breakdown")
    if not isinstance(rows, list):
        return ShardFunds(exchange_index=exchange_index, available_tenths=None)
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("exchange_index") != exchange_index:
            continue
        raw = row.get("balance")
        try:
            # Dollars as a 4dp string, the shape the venue sends. Tenths of a
            # cent is the project's unit, so dollars x 1000.
            return ShardFunds(
                exchange_index=exchange_index,
                available_tenths=int(round(float(raw) * 1000)),
            )
        except (TypeError, ValueError):
            return ShardFunds(exchange_index=exchange_index, available_tenths=None)
    # The shard is absent from the breakdown. That is an unknown, not a zero:
    # the venue lists the shards it chooses to and a missing row has never been
    # observed to mean "empty".
    return ShardFunds(exchange_index=exchange_index, available_tenths=None)


def contracts_for_stake(stake_tenths: int, price_tenths: int) -> int:
    """How many contracts a stake buys at a chosen price, rounded DOWN.

    Down, always: rounding up spends more than Joe typed, and the difference
    lands on the one screen where a number he did not choose is a number he did
    not agree to.
    """
    if price_tenths <= 0:
        raise ComboOrderRefused(422, "a price of zero buys nothing.")
    return int(stake_tenths // price_tenths)


def check_affordable(
    *, contracts: int, price_tenths: int, funds: ShardFunds
) -> None:
    """Refuse, in words naming the shard, before anything reaches the venue.

    The refusal exists because the venue's own is useless to a person: a bare
    `insufficient_balance` on a $2 bet against a $21 account reads as a bug in
    the desk. It is not -- the money is on a different shard -- and only the
    desk is in a position to say so.
    """
    cost_tenths = contracts * price_tenths
    if cost_tenths > COMBO_ORDER_MAX_SPEND_TENTHS:
        raise ComboOrderRefused(
            422,
            f"that bid commits ${cost_tenths / 1000:.2f} and the desk's "
            f"ceiling for one order is "
            f"${COMBO_ORDER_MAX_SPEND_TENTHS / 1000:.2f}. Nothing was sent.",
        )
    if contracts <= 0:
        raise ComboOrderRefused(
            422,
            "that stake buys no whole contracts at that price. Raise the "
            "stake or lower the price.",
        )
    if contracts > COMBO_ORDER_MAX_CONTRACTS:
        raise ComboOrderRefused(
            422,
            f"that is {contracts} contracts and the ceiling is "
            f"{COMBO_ORDER_MAX_CONTRACTS}. Nothing was sent.",
        )
    if not funds.is_readable:
        raise ComboOrderRefused(
            502,
            "the balance on the exchange shard this combination trades on "
            "could not be read, so the desk cannot tell whether this bid is "
            "payable. Nothing was sent.",
        )
    if funds.available_tenths < cost_tenths:
        raise ComboOrderRefused(
            422,
            f"this bid needs ${cost_tenths / 1000:.2f} on exchange shard "
            f"{funds.exchange_index}, which holds "
            f"${funds.available_tenths / 1000:.2f}. Kalshi keeps collateral "
            f"per shard and will not move it for an order, so the money has "
            f"to be allocated to that shard first "
            f"(kalshi.com/account/exchange-indexes). Nothing was sent.",
        )


def open_exposure_tenths(conn) -> int:
    """What the resting bids already out there would cost if all were taken.

    **Pending counts.** A pending row means a request left this process and its
    outcome is unknown; treating it as zero is how the same money gets
    committed twice.
    """
    total = 0
    for row in conn.execute(
        "SELECT count, limit_price_tenths, status FROM combo_orders "
        "WHERE status NOT IN (?, ?, ?, ?)",
        (STATUS_FILLED, STATUS_CANCELLED, STATUS_REJECTED, STATUS_DRY_RUN),
    ):
        total += int(row["count"]) * int(row["limit_price_tenths"])
    return total


def record_intent(
    conn,
    *,
    now_ms: int,
    ticker: str,
    card_key: str,
    legs: Sequence[tuple[str, str]],
    exchange_index: int,
    contracts: int,
    price_tenths: int,
    fair_joint: Optional[float],
    cancel_after_ms: Optional[int],
    request_body: dict,
    dry_run: bool,
) -> int:
    """Write the row BEFORE the request leaves, and return its id.

    Reserve-then-check, the same shape `manual_orders` uses: a row that exists
    before the network call cannot be lost by a timeout, and the one outcome
    this table must never have is a real resting order on the exchange with
    nothing here naming it. An order nobody recorded is an order nobody can
    cancel.
    """
    cursor = conn.execute(
        "INSERT INTO combo_orders (client_order_id, placed_ms, ticker, "
        "card_key, selected_legs, exchange_index, count, limit_price_tenths, "
        "fair_joint, cancel_after_ms, status, request_body_json, dry_run) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            request_body.get("client_order_id") or str(uuid.uuid4()),
            now_ms, ticker, card_key,
            json.dumps([
                {"event_ticker": e, "market_ticker": m} for e, m in legs
            ]),
            exchange_index, contracts, price_tenths, fair_joint,
            cancel_after_ms,
            STATUS_DRY_RUN if dry_run else STATUS_PENDING,
            json.dumps(request_body, sort_keys=True),
            1 if dry_run else 0,
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def record_outcome(
    conn,
    row_id: int,
    *,
    status: str,
    kalshi_order_id: Optional[str] = None,
    response_body: Optional[dict] = None,
    error_text: Optional[str] = None,
) -> None:
    conn.execute(
        "UPDATE combo_orders SET status = ?, kalshi_order_id = ?, "
        "response_body_json = ?, error_text = ? WHERE id = ?",
        (
            status, kalshi_order_id,
            None if response_body is None else json.dumps(response_body, sort_keys=True),
            error_text, row_id,
        ),
    )
    conn.commit()


def record_cancel(
    conn,
    row_id: int,
    *,
    now_ms: int,
    reduced_by: Optional[float],
    reason: str,
) -> None:
    conn.execute(
        "UPDATE combo_orders SET status = ?, cancelled_ms = ?, "
        "cancel_reduced_by = ?, cancel_reason = ? WHERE id = ?",
        (STATUS_CANCELLED, now_ms, reduced_by, reason, row_id),
    )
    conn.commit()


def working_orders(conn, *, now_ms: Optional[int] = None) -> list[dict]:
    """Every bid that is or might still be working, newest first."""
    rows = conn.execute(
        "SELECT * FROM combo_orders WHERE status NOT IN (?, ?, ?, ?) "
        "ORDER BY placed_ms DESC",
        (STATUS_FILLED, STATUS_CANCELLED, STATUS_REJECTED, STATUS_DRY_RUN),
    ).fetchall()
    return [dict(r) for r in rows]


def due_for_cancel(conn, *, now_ms: int) -> list[dict]:
    """Working bids whose earliest leg has started.

    **The deadline is the first kickoff, not a duration.** A resting bid that
    fills after a leg is under way is a bet on a game in progress at a price
    computed before it began -- and the desk's whole claim is that its fair
    value came from pre-game consensus. A clock-based expiry would let that
    happen whenever the clock happened to be generous.

    `cancel_after_ms IS NULL` is excluded rather than treated as due: a missing
    deadline is an unknown, and cancelling on an unknown would silently retire
    orders nobody asked to retire.
    """
    rows = conn.execute(
        "SELECT * FROM combo_orders WHERE status NOT IN (?, ?, ?, ?) "
        "AND cancel_after_ms IS NOT NULL AND cancel_after_ms <= ? "
        "ORDER BY placed_ms",
        (STATUS_FILLED, STATUS_CANCELLED, STATUS_REJECTED, STATUS_DRY_RUN, now_ms),
    ).fetchall()
    return [dict(r) for r in rows]


def status_from_response(payload: Any) -> tuple[str, Optional[str]]:
    """The venue's create response, read into a status and an order id.

    V2 sends no `status` field, so it is derived from the counts -- the same
    reading `kalshi/orders.status_from_counts` performs for IOC, with one
    difference that is the whole point of this module: a remaining count is
    RESTING here rather than unfilled. On an IOC a remainder means the order
    died with work undone; on a GTC it means the order is alive.
    """
    if not isinstance(payload, dict):
        return STATUS_REJECTED, None
    order_id = payload.get("order_id")
    try:
        filled = float(payload.get("fill_count", payload.get("fill_count_fp", 0)) or 0)
        remaining = float(
            payload.get("remaining_count", payload.get("remaining_count_fp", 0)) or 0
        )
    except (TypeError, ValueError):
        return STATUS_REJECTED, order_id
    if remaining > 0 and filled > 0:
        return STATUS_PARTIALLY_FILLED, order_id
    if remaining > 0:
        return STATUS_RESTING, order_id
    if filled > 0:
        return STATUS_FILLED, order_id
    return STATUS_REJECTED, order_id
