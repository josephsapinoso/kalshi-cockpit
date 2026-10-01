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

**Slice S1 (#264)** moves three writers here: the RFQ accept, the slip Joe
types on `/hedge`, and a holding adopted off the venue. The hand-bet order
path (`routes._record_combo_position`) still writes through
`hedge.record_position` directly and stores no provenance until S2 (#265).
Its rows resolve exactly as before, through ADR 0160's read-time join.

What this module does NOT establish:
- that a stored `venue_fill` stake is what Kalshi finally charged after
  fees. No fee is in any stake here; ADR 0145's fee is added at read time.
- anything about rows written before v60. Those carry NULL in all four
  columns and are never backfilled (ADR 0192 §2.6).
"""

from __future__ import annotations

import logging
import sqlite3
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
