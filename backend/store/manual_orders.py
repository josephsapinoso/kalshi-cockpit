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
- Nothing about the venue's response shape. This module records and bounds
  an order; it does not model what comes back.
- Nothing about whether the consensus snapshot below is RIGHT. It records
  what the desk was showing; `beta = -0.141` says agreement with that
  consensus is not evidence of correctness, and ADR 0071 forbids ranking by
  it. The snapshot is a per-row fact, not a score.
- Nothing about coverage. A snapshot is absent far more often than it is
  present -- every combination, every ticker the runner never priced -- and
  `consensus_absent_reason` counts the absences rather than explaining them
  away. Any later measurement must print the covered fraction beside any
  number derived from these columns.

**`MANUAL_ORDERS_ARE_DRY_RUNS` IS FALSE.** Armed 2026-08-26 by code change
(ADR 0073), after ADR 0063's blocking prerequisite P2 was discharged -- the
C0 probe observed a real create-order response on 2026-08-23
(`tests/fixtures/create_order_responses.json`). Until 2026-08-29 the four
lines above said the constant "stays True", fifty lines up from the
assignment that sets it False; the value was right and the paragraph
introducing the module was three days stale, which is the reading order a
newcomer actually takes. What still bounds a real order is enumerated at
the assignment itself, below.

The engine path is untouched and stays dry: `store/orders.py`'s
`ORDERS_ARE_DRY_RUNS` is still True, `gate.py` still never reads this
table, and nothing here moves the live-trading interlock's populations.
"""

from __future__ import annotations

import logging
import math
import sqlite3
from dataclasses import dataclass
from typing import Any, Optional

from ..core.prices import probability_to_tenths
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
#
# ARMED 2026-08-26, on Joe's word, in his own message: "I already got money in
# kalshi. Flip it, commit and deploy." Both of ADR 0063's blocking
# prerequisites were discharged first -- the daily-loss switch reads
# `venue_settlements` (ADR 0064), and the C0 probe observed a real create-order
# response on 2026-08-23 (`tests/fixtures/create_order_responses.json`) -- and
# ADR 0018's second barrier, a REST client on the placer, was wired in
# `b2f2d14` rather than left for this commit to remember.
#
# **This is the line that spends money.** From here `POST /api/manual-orders`
# sends a real immediate-or-cancel order to the exchange. What still bounds it,
# all server-side and none of it waivable from a client: MANUAL_ORDERS_ENABLED
# plus `instance_mode == "live"`, the desk lockout, the ten-minute cool-off,
# the daily-loss switch over the venue's own settlement record, caps derived
# from the observed balance and never typed, the price ceiling refused rather
# than re-priced, the depth check, the netting refusal on any existing
# position, MANUAL_ORDER_MAX_CONTRACTS below, and the reserve-then-check write
# that records the intent BEFORE the request leaves.
#
# The engine's path is untouched and stays dry: `ORDERS_ARE_DRY_RUNS` is still
# True, `gate.py` still never reads this table, and nothing here moves the
# live-trading interlock's populations.
#
# To disarm, set this back to True and deploy. One line, revertible on its own,
# which is why it landed in a commit of its own.
MANUAL_ORDERS_ARE_DRY_RUNS = False

STATUS_PENDING = "pending"

# **The binding ceiling is MONEY, not contracts, since 2026-08-26.**
#
# Both of these were 1 contract (ADR 0063 §3, ADR 0073 §5). At a combination
# priced near a cent that is a bet of about $0.015 -- and the operator, asked
# directly, bets **25c to $3 on parlays**. A one-contract ceiling did not make
# his bet small; it made the door decorative, which is the state ADR 0073 §1
# already caught this path in once ("a feature and the one path that invokes
# it are two deliverables").
#
# A spend cap is the better bound and not merely the more convenient one:
#
# - **The risk it bounds is denominated in money.** A contract cap lets one
#   bet be $0.015 and another $0.90, on the same number.
# - **It bounds the fee-model error BETTER than the contract cap did.** ADR
#   0073 §5 justified one contract by saying it "makes an error in that hedge
#   cost a fraction of a cent instead of scaling with size" -- but the combo
#   fee is `k · C · P · (1-P)`, proportional to spend, not to count. Capping
#   spend caps the error directly; capping count capped it only through
#   whatever the price happened to be.
#
# A constant rather than config, for the reason the dry-run switch is one:
# raising it is a decision with a commit behind it, not an environment
# variable somebody can nudge. It binds independently of
# `MANUAL_ORDERS_ARE_DRY_RUNS`, so it is rehearsed dry exactly as it binds
# live.
#
# **This overrides ADR 0063 §3's trigger, on the owner's word, and the
# override is recorded rather than quiet** -- that trigger said the ceiling
# rises "only when observed `fee_actual` matches `fee_predicted` on real
# fills", and no fill through this door has been checked. See ADR 0075.
MANUAL_ORDER_MAX_SPEND_TENTHS = 3_000  # $3.00 -- the top of his stated range

# The structural ceiling, in contracts. **Not the binding one** -- the spend
# cap above is, and this exists so the authorisation loop terminates and so a
# market priced at a tenth of a cent cannot turn $3 into thirty thousand
# contracts. A count that large is a different kind of order (it moves a thin
# book on its own) even when the money is small.
MANUAL_ORDER_MAX_CONTRACTS = 500

# Combination (`KXMVE`) markets keep a tighter structural ceiling. The book is
# enter-only on every combination this repo has ever read (ADR 0012 §5) and
# the deepest resting bid ever measured was 18 units, so a count far past that
# could not fill anyway and would only be an order the venue rejects in parts.
COMBO_MAX_CONTRACTS = 250

# The combination prefix, and the ONE predicate that reads it.
#
# `kalshi/discovery.JUNK_PREFIX` is the same string and is why no combination
# ever reaches `kalshi_markets`, and therefore why none can ever reach
# `recommendations` or `fair_prices`. The route's size ceiling, fee choice,
# acknowledgement refusal and market read all go through `is_combo_ticker`,
# and so does the consensus snapshot below, so those five cannot disagree
# about what a combination is.
COMBO_PREFIX = "KXMVE"


def is_combo_ticker(ticker: Optional[str]) -> bool:
    """A combination (multivariate-event) market, by ticker prefix."""
    if ticker is None:
        return False
    return ticker.strip().upper().startswith(COMBO_PREFIX)


def max_spend_dollars() -> float:
    """The spend ceiling in dollars, converted in exactly one place.

    Money is integer tenths of a cent everywhere in the risk path
    (`core/prices.py`); this is the single boundary where that becomes a float
    for comparison against the balance-derived cap.
    """
    return MANUAL_ORDER_MAX_SPEND_TENTHS / 1000.0

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


# ---------------------------------------------------------------------------
# What the desk was showing at the tap (ADR 0082).
# ---------------------------------------------------------------------------
#
# **Why the reasons are a closed vocabulary rather than free text.** The audit
# has to be able to count them (`inspect_live_db.py manual-orders-audit`), and
# a message that varies by ticker cannot be grouped. Each value below is a
# different fact about the record and they must not be collapsed:
#
#   combo_ticker           there IS no devigged consensus. Discovery drops the
#                          KXMVE prefix, so no `kalshi_markets` row exists, so
#                          no recommendation and no fair price can. Expected,
#                          and the dominant case on a parlay night.
#   no_priced_row          the runner never priced this (ticker, side). An
#                          unlinked event, a market type it does not cover, or
#                          a bet taken on something no pass ever reached.
#   unreadable_fair_value  the recommendation's `fair_probability` is absent or
#                          outside [0, 1]. Refused rather than clamped --
#                          `probability_to_tenths` clamps, so passing garbage
#                          through it would produce a confident 0 or 1000.
#   lookup_failed          the read itself raised. The order still went; this
#                          is the only value that means "we had a bug", and it
#                          is recorded rather than swallowed so it can be seen.
#
# There is deliberately no reason for "the fair value is present but the
# `fair_prices` row behind it is gone". That is thin provenance, not an
# absence: the value is still the one the desk showed, and it is written with
# `consensus_book_count` NULL. Calling it absent would discard a real
# observation to tidy up a NULL.
ABSENT_COMBO = "combo_ticker"
ABSENT_NO_PRICED_ROW = "no_priced_row"
ABSENT_UNREADABLE_FAIR_VALUE = "unreadable_fair_value"
ABSENT_LOOKUP_FAILED = "lookup_failed"


@dataclass(frozen=True)
class ConsensusSnapshot:
    """The devigged consensus as it stood when the intent was written.

    Frozen values, never a foreign key. `fair_prices` is mutable and
    retention-eligible, so an id into it answers "what does that table say
    now", which is a different question from "what did the desk show him".
    The two id fields are carried anyway because the lookup already had them
    and a breadcrumb costs nothing -- but they may dangle, and no reader may
    treat them as the record.

    Money is integer tenths of a cent, on the same 0-1000 scale as
    `limit_price_tenths`. `edge_tenths` is signed.

    An instance with `fair_tenths is None` is an ABSENCE and always carries an
    `absent_reason`; the invariant is checked in `__post_init__` so a caller
    cannot write a silent hole, and a NULL fair value in the table always has
    a stated cause.
    """

    fair_tenths: Optional[int] = None
    edge_tenths: Optional[int] = None
    book_count: Optional[int] = None
    anchored_on_sharp: Optional[int] = None
    computed_ms: Optional[int] = None
    fair_price_id: Optional[int] = None
    link_id: Optional[int] = None
    absent_reason: Optional[str] = None

    def __post_init__(self) -> None:
        if (self.fair_tenths is None) != (self.absent_reason is not None):
            raise ValueError(
                "a consensus snapshot is either a value with no reason or an "
                "absence with one; "
                f"fair_tenths={self.fair_tenths!r} "
                f"absent_reason={self.absent_reason!r} is neither"
            )


#: An absence with no cause recorded is not reachable through the dataclass,
#: so this is the shape every refusal below builds.
def _absent(reason: str) -> "ConsensusSnapshot":
    return ConsensusSnapshot(absent_reason=reason)


def _fair_tenths(probability: Any) -> Optional[int]:
    """A conservative devig probability as integer tenths, or `None`.

    **The bounds check is the whole of this function and it is not
    decoration.** `probability_to_tenths` CLAMPS to [0, 1], so a corrupted or
    out-of-range value would come back as a confident 0 or 1000 tenths -- a
    settled outcome, written down as a live consensus. Refusing is the rule
    (`CLAUDE.md`: unreadable resolves to `None`, never 0).
    """
    if probability is None:
        return None
    try:
        value = float(probability)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        return None
    return probability_to_tenths(value)


def _rounded_tenths(value: Any) -> Optional[int]:
    """A REAL tenths column as a signed integer, or `None` if unreadable.

    `recommendations.edge_tenths` is REAL and this column is INTEGER, so the
    copy loses sub-tenth precision. That is the right trade for a money row --
    a tenth of a cent is already a tenth of the smallest thing the venue
    quotes -- and it is stated here rather than discovered by someone
    comparing the two tables and finding them off by 0.4.
    """
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return int(round(number))


def _read_consensus(
    conn: sqlite3.Connection, *, ticker: str, side: str
) -> ConsensusSnapshot:
    """The freshest priced row for this (ticker, side), as a frozen copy.

    **May raise. `consensus_snapshot` is the one callers use.** Split in two
    on purpose: the refusal has to be provable by making this function throw,
    and a single function that catches its own exceptions cannot be made to.

    The source is `recommendations` joined to `fair_prices`, which is
    *literally what the Slate row rendered* -- `/api/slate` selects the same
    join, and `SlateRow.tsx` is the control that opens this door. Reading the
    desk's own row rather than re-deriving the consensus through
    `ticker -> kalshi_markets.event_ticker -> event_links -> fair_prices`
    means there is no second implementation of the matcher to drift from the
    first.

    The predicate and the ORDER BY are the same shape as
    `engine.persist_if_changed`'s hot read, so `idx_recs_ticker_side` covers
    it and this is a seek rather than a scan of a growing table -- which
    matters because it runs inside the request that spends money.

    No age cutoff, and that is deliberate. A ticker names one fixture, so an
    old row is the same market rather than a different game; how stale it was
    is `submitted_ms - consensus_computed_ms`, recorded rather than judged
    here. A freshness threshold chosen at the write site would bake one
    session's opinion into the record permanently and irreversibly.
    """
    if is_combo_ticker(ticker):
        return _absent(ABSENT_COMBO)

    row = conn.execute(
        "SELECT r.fair_probability, r.edge_tenths, r.fair_price_id, "
        "       r.link_id, f.book_count, f.anchored_on_sharp, f.computed_ms "
        "FROM recommendations r "
        "LEFT JOIN fair_prices f ON f.id = r.fair_price_id "
        "WHERE r.ticker = ? AND r.side = ? "
        "ORDER BY r.created_ms DESC, r.id DESC LIMIT 1",
        (ticker, side),
    ).fetchone()
    if row is None:
        return _absent(ABSENT_NO_PRICED_ROW)

    fair_tenths = _fair_tenths(row["fair_probability"])
    if fair_tenths is None:
        return _absent(ABSENT_UNREADABLE_FAIR_VALUE)

    def _int_or_none(value: Any) -> Optional[int]:
        return None if value is None else int(value)

    return ConsensusSnapshot(
        fair_tenths=fair_tenths,
        edge_tenths=_rounded_tenths(row["edge_tenths"]),
        book_count=_int_or_none(row["book_count"]),
        anchored_on_sharp=_int_or_none(row["anchored_on_sharp"]),
        computed_ms=_int_or_none(row["computed_ms"]),
        fair_price_id=_int_or_none(row["fair_price_id"]),
        link_id=_int_or_none(row["link_id"]),
    )


def consensus_snapshot(
    conn: sqlite3.Connection, *, ticker: str, side: str
) -> ConsensusSnapshot:
    """`_read_consensus`, wrapped so it can never block or fail a bet.

    **This is additive recording and nothing else.** The order path's
    behaviour is what it was before the snapshot existed: if this read raises
    or finds nothing, the order still goes and the columns are NULL.
    `BaseException` is deliberately NOT caught -- a `KeyboardInterrupt` or a
    cancellation is the process being torn down, and relabelling that as a
    missing fair value would hide a shutdown inside a data column.

    Pinned by `tests/test_manual_orders.py::TestTheSnapshotCanNeverBlockABet`,
    which makes `_read_consensus` throw and asserts the order still succeeds
    with every snapshot column NULL.
    """
    try:
        return _read_consensus(conn, ticker=ticker, side=side)
    except Exception:                                   # noqa: BLE001
        logger.exception(
            "the consensus snapshot for %s %s could not be read; the order "
            "proceeds and the row records the absence rather than a zero.",
            ticker, side,
        )
        return _absent(ABSENT_LOOKUP_FAILED)


def _insert_intent(
    conn: sqlite3.Connection,
    order: OrderRequest,
    *,
    dry_run: bool,
    submitted_ms: int,
    max_price_tenths: int,
    p_yes_bp: int,
    idempotency_key: Optional[str],
    consensus: ConsensusSnapshot,
) -> int:
    """Write the intent, with what the desk was showing frozen beside it.

    **`limit_price_tenths` is already the ask at the tap and is not
    duplicated.** It is `OrderRequest.fill_price_tenths` -- the live derived
    ask for OUR side, snapped to the venue's grid, and bounded by the typed
    ceiling because check 7 of the route refuses rather than re-prices. A
    second "ask at tap time" column would be the same number under two names,
    and this repo's recurring failure is two spellings of one fact.
    """
    cursor = conn.execute(
        "INSERT INTO manual_orders ("
        " client_order_id, submitted_ms, ticker, side, action, count,"
        " limit_price_tenths, max_price_tenths, p_yes_bp, status,"
        " request_body_json, dry_run, idempotency_key,"
        " consensus_fair_tenths, consensus_edge_tenths, consensus_book_count,"
        " consensus_anchored_on_sharp, consensus_computed_ms,"
        " consensus_fair_price_id, consensus_link_id, consensus_absent_reason"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
            consensus.fair_tenths,
            consensus.edge_tenths,
            consensus.book_count,
            consensus.anchored_on_sharp,
            consensus.computed_ms,
            consensus.fair_price_id,
            consensus.link_id,
            consensus.absent_reason,
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

    **The consensus snapshot is read here, before the lock, and cannot change
    what this function does.** Before, so the write window stays as small as
    it was -- the runner may be holding the lock and a tap has to wait for it.
    Here rather than at the route, because "at intent-write time" has to mean
    the same instant as the insert, and because the value must be resolved
    server-side from the ticker: the client never sends it and could not be
    trusted with it if it did. `consensus_snapshot` swallows its own failures,
    so the worst case is seven NULL value columns and a stated reason.
    """
    consensus = consensus_snapshot(conn, ticker=order.ticker, side=order.side)
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
                consensus=consensus,
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
