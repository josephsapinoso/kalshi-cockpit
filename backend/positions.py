"""The one writer of held combos: a fill becomes a position (ADR 0192).

Every row in `parlay_positions` / `parlay_position_legs` is written from
here. This module decides:

- what the stake is;
- whether a fractional fill can be held;
- which legs the holding has;
- which fill produced it, and whose price its stake is.

It records that provenance on the row (`fill_source`, `fill_ref`,
`stake_basis`, `stake_basis_reason`, schema v60), so `/hedge` no longer
rebuilds it by matching `(combo_ticker, placed_ms)` against the order and
quote tables on every read. `hedge.record_position` is the insert underneath,
and this module is its caller.

Four writers come through here:
- the hand-bet order path (`manual_order._record_combo_position`, S2, #265);
- the RFQ accept;
- the slip Joe types on `/hedge`;
- a holding adopted off the venue.

Rows written before schema v60 carry no provenance and resolve exactly as
before, through ADR 0160's read-time join.

What this module does NOT establish:
- that a stored `venue_fill` stake is what Kalshi finally charged after
  fees. No fee is in any stake here; ADR 0145's fee is added at read time.
- anything about rows written before v60. Those carry NULL in all four
  columns and are never backfilled (ADR 0192 §2.6).
"""

from __future__ import annotations

import logging
import math
import sqlite3
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

import backend.hedge as held_parlays
import backend.parlays as parlays
from backend.core.hedge import SETTLEMENT_TENTHS
from backend.store import combo_rfqs as store

logger = logging.getLogger(__name__)

#: `parlay_positions.fill_source`: the four ways a held combo comes to exist.
FILL_MANUAL_ORDER = "manual_order"
FILL_RFQ_QUOTE = "rfq_quote"
FILL_HAND = "hand"
FILL_ADOPTED = "adopted"


def _quote_size(quote: Mapping[str, Any]) -> Optional[float]:
    # Imported late: `combo_rfq` imports this module, and its `_quote_size` is
    # the one validator of a maker's quoted size. Reused, not re-written.
    from backend.combo_rfq import _quote_size as quote_size

    return quote_size(quote)


def holdable_count(count: Optional[float]) -> bool:
    """Whether a venue-reported count can be held exactly in the table.

    A settlement is a whole 1000 tenths a contract, so `count x 1000` must be
    whole tenths: 2.5 can be held, 2.5005 cannot. The second is refused and
    said out loud, never rounded (ADR 0151's direction, ADR 0192 §2.4).
    `None`, zero, negative and non-finite counts are not holdings at all.
    """
    if count is None:
        return False
    try:
        value = float(count)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(value) or value <= 0:
        return False
    exact_return = value * SETTLEMENT_TENTHS
    return abs(exact_return - round(exact_return)) <= 1e-6


#: The permanent note on a combination bought through the hand-bet path.
#: Pinned by `test_combo_exit_copy_names_the_cost_on_every_surface.py`: it
#: names what an exit costs, not how often one exists (Joe's rule, #60/#64).
ORDER_PATH_NOTE = (
    "Recorded automatically from the hand-bet path. A combination can "
    "be sold back, though selling back may cost more than holding it "
    "to the outcome; a hedge is the exit the desk watches, not the "
    "only one that exists."
)


@dataclass(frozen=True)
class OrderFill:
    """What `record_order_fill` did. `refused` is the ticket check's own
    sentence when the position was refused for its SIZE or PRICE (a tiny
    fraction whose stake rounds to the return, or to zero) -- a different
    fact from legs that could not be recovered, so the screen must not say
    the second when the first happened (kalshi-platform review of #265)."""

    position_id: Optional[int]
    refused: Optional[str] = None


def record_order_fill(
    conn: sqlite3.Connection,
    *,
    manual_order_id: int,
    ticker: str,
    filled: float,
    sent_price_tenths: int,
    now_ms: int,
    placed_ms: int,
) -> OrderFill:
    """A combination bought through `POST /api/manual-orders` (step 13).

    **The stake is decided by `hedge.stake_basis_for`, the function ADR
    0160's read-time join calls**, applied to this order's own
    `manual_orders` row, read by id. The stored figure is therefore exactly
    what `/hedge` would have computed on read:
    - the venue's average fill price x the venue's count, stored as
      `venue_fill`, when that row proves it;
    - otherwise the price the desk SENT, stored as `as_recorded` with the
      reason (`no_venue_price`, `side_convention_unresolved`, and so on).

    This supersedes ADR 0160 §2.1 for rows written from here on (ADR 0192
    §2.3).

    `filled` is the venue's count. A fraction the table can hold is recorded
    at that count (§2.4). A finer one is refused here as well as by the
    caller.

    Returns an `OrderFill`: the id, or `None` with `refused` set when the
    ticket check refused the size or price, or `None` alone when the legs
    could not be recovered. **Nothing here raises**: the order is placed and
    the money is spent.
    """
    try:
        if not holdable_count(filled):
            logger.error(
                "manual order %d on %s: count %r cannot be held exactly; "
                "no position", manual_order_id, ticker, filled,
            )
            return OrderFill(None, f"a fill of {filled} contracts cannot be held exactly")
        lookup = parlays.priced_lookup_for(conn, ticker)
        if lookup is None:
            return OrderFill(None)
        parsed = parlays.legs_for_position(lookup["selected_legs"])
        if parsed is None:
            return OrderFill(None)
        count = float(filled)
        return_tenths = int(round(count * SETTLEMENT_TENTHS))
        # The sent figure, rounded once to the nearest tenth -- the only
        # rounding, as on the RFQ path. A whole count gives the exact product
        # the order path always wrote.
        sent_stake = int(round(count * int(sent_price_tenths)))
        order = conn.execute(
            "SELECT side, venue_fill_count, venue_avg_fill_price_tenths "
            "FROM manual_orders WHERE id = ? AND dry_run = 0",
            (int(manual_order_id),),
        ).fetchone()
        basis = held_parlays.stake_basis_for(
            {
                "source": "kalshi_combo",
                "combo_ticker": ticker,
                "placed_ms": placed_ms,
                "stake_tenths": sent_stake,
                "return_tenths": return_tenths,
                "note": None,
            },
            order,
        )
        note = ORDER_PATH_NOTE
        if parsed.labels_are_tickers:
            note += (
                " Leg names are market tickers -- this combination was priced "
                "before the desk began recording leg labels, and inventing "
                "them was refused."
            )
        position_id = held_parlays.record_position(
            conn,
            now_ms=now_ms,
            source="kalshi_combo",
            label=held_parlays.position_label(lookup["card_key"], ticker),
            stake_tenths=basis.stake_tenths,
            return_tenths=return_tenths,
            legs=parsed.legs,
            placed_ms=placed_ms,
            combo_ticker=ticker,
            parlay_lookup_id=int(lookup["id"]),
            note=note,
            fill_source=FILL_MANUAL_ORDER,
            fill_ref=int(manual_order_id),
            stake_basis=basis.basis,
            stake_basis_reason=basis.reason,
        )
        return OrderFill(position_id)
    except held_parlays.PositionRefused as exc:
        # Reachable since fractions are held: 0.01 of a contract at 95c rounds
        # to a stake equal to its return, which the ticket check refuses.
        logger.error(
            "manual order %d on %s: position refused: %s",
            manual_order_id, ticker, exc.refusal.detail,
        )
        return OrderFill(None, exc.refusal.detail)
    except Exception:  # noqa: BLE001 -- the order is placed; bookkeeping may not raise
        logger.exception(
            "manual order %d on %s: the position could not be written",
            manual_order_id, ticker,
        )
        return OrderFill(None)


def record_rfq_accept(
    conn: sqlite3.Connection,
    *,
    rfq_id: str,
    quote: sqlite3.Row,
    now_ms: int,
    venue: Optional[Any] = None,
) -> Optional[int]:
    """Put a combination bought by RFQ under `/hedge`'s watch.

    Moved here from `combo_rfq._record_accepted_position` by ADR 0192. The
    stake, size and fractional rules are unchanged (ADRs 0169 and 0178); the
    only addition is the provenance written with the row.

    Returns the new position's id, or **`None` when the position could not be
    built honestly**. `None` is never an error the caller may hide: it means
    the money moved and nothing is watching it, so `_accept_words` says so on
    the screen. **Nothing here raises.** The trade is done and the money is
    spent, and a bookkeeping failure must not turn a completed purchase into a
    500 that tells Joe nothing happened.

    **The size is the VENUE's whenever the venue said one** (issue #74, ADR
    0178). When `read_venue_fill`'s answer is usable, the holding and the
    stake are Kalshi's own count and average price, stored as `venue_fill`.
    Otherwise the quote's ask times its size is stored as `as_recorded`. The
    reason says which case applies:
    - `rfq_accept`: the venue was never asked;
    - `rfq_fill_unmatched`: the venue was asked and its answer cannot be used.

    These are the words `hedge._rfq_stake_basis` used to derive on every
    read. `venue` is `combo_rfq.VenueFill` or `None`, read by attribute
    because `combo_rfq` imports this module.
    """
    try:
        ask = store.rfq_row(conn, rfq_id)
        if ask is None:
            logger.error("rfq %s: no ask row, so no position was built", rfq_id)
            return None
        parsed = parlays.legs_for_position(ask["selected_legs"])
        if parsed is None:
            logger.error("rfq %s: legs unreadable, so no position", rfq_id)
            return None

        # Kalshi's own record first. `VenueFill.usable` is true only for an
        # outcome that names a fill this acceptance provably caused, with
        # both numbers present -- every refusal leaves them None and falls
        # through to the quote, which is the behaviour that shipped before.
        from_venue = venue is not None and venue.usable
        if from_venue:
            contracts = float(venue.count)
            price = int(venue.avg_price_tenths)
        else:
            contracts = _quote_size(quote)
            if contracts is None:
                logger.error(
                    "rfq %s: quote carries no usable size, so no position", rfq_id
                )
                return None

            price = quote["yes_ask_tenths"]
            if price is None:
                logger.error(
                    "rfq %s: quote carries no price, so no position", rfq_id
                )
                return None

        # A settlement is a whole 1000 tenths a contract, so a size carrying
        # more than two decimals cannot be reproduced exactly in the unit the
        # table stores. Refused rather than rounded, for the reason
        # `stake_basis_for`'s `fractional_venue_fill_count` refuses the same
        # shape on the order path: a size a later audit cannot reproduce is
        # not a size to build a money figure on.
        exact_return = contracts * SETTLEMENT_TENTHS
        if abs(exact_return - round(exact_return)) > 1e-6:
            logger.error(
                "rfq %s: quote size %r is finer than a tenth, so no position",
                rfq_id, contracts,
            )
            return None

        # Rounded, and it is the only rounding here: the ask is per contract
        # and the size is fractional, so the product is not integral in
        # general. Half a tenth of a cent, once, on the entry figure.
        stake_tenths = int(round(contracts * int(price)))
        if from_venue:
            note = (
                "Recorded automatically from a maker's quote you took on the "
                "Parlays screen, at Kalshi's own record of the fill: "
                f"{contracts:g} contracts at the average price it charged, "
                "before fees."
            )
            basis, reason = held_parlays.STAKE_BASIS_VENUE_FILL, None
        else:
            note = (
                "Recorded automatically from a maker's quote you took on the "
                "Parlays screen. The stake is the price you accepted times "
                "the size quoted, before fees -- Kalshi's own record of the "
                "fill was asked for and did not answer for this combination."
            )
            basis = held_parlays.STAKE_BASIS_AS_RECORDED
            reason = "rfq_accept" if venue is None else "rfq_fill_unmatched"
        if parsed.labels_are_tickers:
            note += (
                " Leg names are market tickers -- this combination was priced "
                "before the desk began recording leg labels, and inventing "
                "them was refused."
            )
        return held_parlays.record_position(
            conn,
            now_ms=now_ms,
            source="kalshi_combo",
            label=held_parlays.position_label(ask["card_key"], str(ask["ticker"])),
            stake_tenths=stake_tenths,
            return_tenths=int(round(exact_return)),
            legs=parsed.legs,
            # Both halves of ADR 0160's join key are still written, from one
            # variable. The stored basis makes the join unnecessary for this
            # row, but a pre-v60 reader, or an audit, can still form it.
            placed_ms=now_ms,
            combo_ticker=str(ask["ticker"]),
            # No `parlay_lookup_id`: `combo_rfqs` does not carry one, and
            # re-deriving it by ticker would join whichever lookup last
            # minted that ticker, which is not necessarily the one asked.
            note=note,
            fill_source=FILL_RFQ_QUOTE,
            fill_ref=int(quote["id"]),
            stake_basis=basis,
            stake_basis_reason=reason,
        )
    except Exception:  # noqa: BLE001 -- the trade is done; bookkeeping may not raise
        logger.exception(
            "rfq %s: the position for a filled accept could not be written", rfq_id
        )
        return None


def record_hand_entry(
    conn: sqlite3.Connection,
    *,
    now_ms: int,
    source: str,
    label: str,
    stake_tenths: int,
    return_tenths: int,
    legs: Sequence[Mapping[str, Any]],
    book: Optional[str] = None,
    placed_ms: Optional[int] = None,
    combo_ticker: Optional[str] = None,
    parlay_lookup_id: Optional[int] = None,
    note: Optional[str] = None,
) -> int:
    """A ticket Joe typed on `/hedge` (`POST /api/hedge/positions`).

    Raises `hedge.PositionRefused` exactly as before: a typed ticket is
    refused while he can still correct it. The stake is his figure, and its
    basis is stored with one of two reasons:
    - `not_a_kalshi_combo` for a sportsbook slip;
    - `hand_recorded_position` for a Kalshi combination typed without the
      order's ticker and time. The form sends neither.

    **When the request DOES carry both halves of the join key, no basis is
    stored.** The read-time join then resolves the row as it always has.
    Storing `hand_recorded_position` there would hide an order the join can
    find, so the stored basis says only what the read would have said.
    """
    basis: Optional[str] = held_parlays.STAKE_BASIS_AS_RECORDED
    reason: Optional[str]
    if source != "kalshi_combo":
        reason = "not_a_kalshi_combo"
    elif not combo_ticker or placed_ms is None:
        reason = "hand_recorded_position"
    else:
        basis, reason = None, None
    return held_parlays.record_position(
        conn,
        now_ms=now_ms,
        source=source,
        label=label,
        stake_tenths=stake_tenths,
        return_tenths=return_tenths,
        legs=legs,
        book=book,
        placed_ms=placed_ms,
        combo_ticker=combo_ticker,
        parlay_lookup_id=parlay_lookup_id,
        note=note,
        fill_source=FILL_HAND,
        fill_ref=None,
        stake_basis=basis,
        stake_basis_reason=reason,
    )


def record_adopted(
    conn: sqlite3.Connection,
    *,
    now_ms: int,
    label: str,
    stake_tenths: int,
    return_tenths: int,
    legs: Sequence[Mapping[str, Any]],
    combo_ticker: str,
    note: str,
) -> int:
    """A Kalshi holding `hedge.adopt_venue_combo` brought under watch (#148).

    The stake is the venue's own `market_exposure_dollars`, stored as
    `venue_exposure` with `adopted_from_positions`. That is the basis
    `stake_basis_for` gives any row whose note carries
    `ADOPTED_NOTE_MARKER`. The caller holds the write lock (`BEGIN
    IMMEDIATE`) and handles `PositionRefused`, so this raises as
    `record_position` does.
    """
    return held_parlays.record_position(
        conn,
        now_ms=now_ms,
        source="kalshi_combo",
        label=label,
        stake_tenths=stake_tenths,
        return_tenths=return_tenths,
        legs=legs,
        combo_ticker=combo_ticker,
        note=note,
        fill_source=FILL_ADOPTED,
        fill_ref=None,
        stake_basis=held_parlays.STAKE_BASIS_VENUE_EXPOSURE,
        stake_basis_reason="adopted_from_positions",
    )
