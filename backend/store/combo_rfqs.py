"""Recording what the market said when asked to price a combination.

**This table is the only copy.** A combination's price is never public: makers
quote privately to the requester, and those quotes disappear from
`GET /communications/quotes?rfq_user_filter=self` the instant the RFQ is
deleted (measured 2026-09-17 -- a re-read returned zero). Nothing downstream
may re-fetch a quote. A quote not written here is gone, and with it the only
evidence of what the desk was actually offered.

That is a sharper obligation than `parlay_lookups` carries. A book read can be
taken again; a quote cannot.

What this module does not do
----------------------------
- **It does not decide.** No "best" column, no EV, no ranking beyond storing
  the price each maker named. The one RFQ this repo has fired had makers 3.80
  cents apart, which is a fact worth recording and not a signal worth acting
  on.
- **It does not spend.** Recording an ask is not placing a bet; acceptance is
  a separate call with its own arming decision.
- **It never fails a purchase.** Every write here is best-effort from the
  caller's point of view -- see `ADR 0125`'s lesson, where a bookkeeping
  writer wrapped in a bare `except` meant nothing raised when it broke. The
  difference here: failures are **logged loudly and counted**, not swallowed
  silently, because a silent bookkeeping failure on the only copy of a price
  is indistinguishable from "no maker answered".
"""
from __future__ import annotations

import json
import logging
import sqlite3
from typing import Iterable, Optional, Sequence

from backend.kalshi.rfq import RfqQuote

logger = logging.getLogger(__name__)

#: Statuses `combo_rfqs.status` may hold, matching the CHECK in `schema.sql`.
#:
#: `quoted` and `no_quotes` are deliberately different rows rather than a
#: count of zero. "We asked and nobody answered" is a measurement about the
#: market; "we asked and never read the answer" is a bug in us, and a single
#: `asked` status with `quote_count = 0` cannot tell them apart.
STATUS_ASKED = "asked"
STATUS_QUOTED = "quoted"
STATUS_NO_QUOTES = "no_quotes"
#: Makers answered and every price was finer than a tenth of a cent, so
#: the desk refused them all rather than rounding one onto the money path
#: (ADR 0172, schema v49). A THIRD case, not a flavour of `no_quotes`:
#: the comment above distinguishes "the market did not answer" from "we
#: never read the answer", and this is a third thing again -- the market
#: answered and we could not represent what it said.
STATUS_PRICED_TOO_FINELY = "priced_too_finely"
STATUS_ERROR = "error"


def record_rfq(
    conn: sqlite3.Connection,
    *,
    rfq_id: str,
    requested_ms: int,
    ticker: str,
    collection_ticker: str,
    legs: Sequence[dict],
    exchange_index: int,
    card_key: Optional[str] = None,
    target_cost_dollars: Optional[str] = None,
    contracts_requested: Optional[int] = None,
    fair_joint: Optional[float] = None,
    book_yes_ask_tenths: Optional[int] = None,
    status: str = STATUS_ASKED,
    error_text: Optional[str] = None,
) -> None:
    """Write the ask itself, before any quote is read.

    Written FIRST and separately from the quotes, for the reason
    `lookup_combo` learned the hard way: the RFQ is already live on the venue
    by the time a quote could arrive, so a failure while reading quotes must
    not lose the fact that we asked. An `asked` row with no quotes is a
    readable state; a missing row is not.

    `book_yes_ask_tenths` is what the ORDER BOOK said at the same instant.
    NULL is the expected value and means the book was empty -- the normal
    resting state of a combination, not a fault. It is stored so the two
    surfaces can be compared later without running a second experiment.
    """
    # **`ON CONFLICT(rfq_id) DO NOTHING`, never `INSERT OR IGNORE`.**
    # They read as synonyms and are not: `OR IGNORE` swallows *every*
    # constraint failure, so a row with a bad `status` or a missing NOT NULL
    # column silently writes nothing and the caller is told it recorded the
    # ask. On the only copy of a price, a write that vanishes without raising
    # is the worst available failure. This form ignores exactly the
    # re-ask-the-same-RFQ collision it is there for and lets the CHECK raise.
    # Caught by `test_an_unknown_status_is_refused_by_the_schema`, which was
    # green against `OR IGNORE` for the wrong reason.
    conn.execute(
        """
        INSERT INTO combo_rfqs (
            rfq_id, requested_ms, card_key, ticker, collection_ticker,
            selected_legs, exchange_index, target_cost_dollars,
            contracts_requested, fair_joint, book_yes_ask_tenths,
            quote_count, status, error_text
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        ON CONFLICT(rfq_id) DO NOTHING
        """,
        (
            rfq_id, requested_ms, card_key, ticker, collection_ticker,
            json.dumps(list(legs)), exchange_index, target_cost_dollars,
            contracts_requested, fair_joint, book_yes_ask_tenths,
            status, error_text,
        ),
    )


def record_quotes(
    conn: sqlite3.Connection,
    *,
    rfq_id: str,
    quotes: Iterable[RfqQuote],
    captured_ms: int,
    refused_too_fine: int = 0,
) -> int:
    """Persist the quotes and stamp the RFQ's outcome. Returns rows touched.

    `ON CONFLICT(rfq_id, quote_id) DO UPDATE`, and the update is the safety
    property, not a tidiness one.

    **This was `DO NOTHING` until 2026-09-18, on the reasoning that "a quote
    seen twice is one quote".** That is true within one poll loop and false
    across two asks: `ask_market_to_price` holds the RFQ open by default, and
    `create_rfq` REUSES an open RFQ, so a second "Ask again" on the same
    combination returns the same `quote_id`s -- and the wire payload carries
    an `updated_ts` distinct from `created_ts`, i.e. a maker re-prices a quote
    in place.

    With `DO NOTHING` the screen rendered the fresh price (it comes from
    memory) while this table -- **the only copy `accept_quote_for_joe` reads,
    and the thing that is supposed to guarantee "the price accepted is the
    price he was shown"** -- kept the first one. The accept call carries no
    price, so the venue would have charged its current number against a
    recorded stake taken from a stale one, with no typed ceiling anywhere to
    catch the difference (B = (ii)). Spelled as `DO UPDATE` rather than
    `INSERT OR REPLACE` for the reason given in `record_rfq`.

    `accepted_ms` and the outcome columns are deliberately NOT in the update
    list: they are the acceptance's own record, and a later poll must never be
    able to reopen a quote that has already been accepted.

    **What this does not fix.** Whether Kalshi actually mutates a quote in
    place is inferred from `updated_ts` existing on the captured payload, not
    measured. This change is safe either way -- if quotes never move, every
    update is a no-op write of identical values.

    **`quote_count` is set from the table, not from `len(quotes)`.** Those
    differ exactly when a write failed, which is the case this count exists to
    make visible -- deriving it from the argument would report success for
    rows that never landed.

    **`refused_too_fine` cannot come from the table, and that asymmetry is
    deliberate** (#77). A refused quote never becomes an `RfqQuote` and so
    never becomes a row -- that is the whole reason the status was wrong --
    so the caller passes the count it unioned by quote id across the poll
    loop. It defaults to 0 so that every other writer and every test keeps
    its current meaning, and 0 with no stored quotes is still `no_quotes`.
    """
    written = 0
    for quote in quotes:
        cur = conn.execute(
            """
            INSERT INTO combo_rfq_quotes (
                rfq_id, quote_id, captured_ms, maker_id,
                yes_ask_tenths, no_bid_tenths, yes_bid_tenths, contracts,
                status, created_ts
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(rfq_id, quote_id) DO UPDATE SET
                captured_ms    = excluded.captured_ms,
                maker_id       = excluded.maker_id,
                yes_ask_tenths = excluded.yes_ask_tenths,
                no_bid_tenths  = excluded.no_bid_tenths,
                yes_bid_tenths = excluded.yes_bid_tenths,
                contracts      = excluded.contracts,
                status         = excluded.status,
                created_ts     = excluded.created_ts
            WHERE combo_rfq_quotes.accepted_ms IS NULL
            """,
            (
                rfq_id, quote.quote_id, captured_ms, quote.maker_id,
                quote.yes_ask_tenths, quote.no_bid_tenths,
                quote.yes_bid_tenths, quote.contracts,
                quote.status, quote.created_ts,
            ),
        )
        written += cur.rowcount or 0

    stored = conn.execute(
        "SELECT COUNT(*) FROM combo_rfq_quotes WHERE rfq_id = ?", (rfq_id,)
    ).fetchone()[0]
    # **Three outcomes, and the precedence matches the payload's** (ADR
    # 0172): a stored quote means there was a price to show, so `quoted`
    # outranks `priced_too_finely`. The reverse would file a takeable
    # price under a complaint.
    if stored:
        status = STATUS_QUOTED
    elif refused_too_fine:
        status = STATUS_PRICED_TOO_FINELY
    else:
        status = STATUS_NO_QUOTES
    conn.execute(
        "UPDATE combo_rfqs SET quote_count = ?, refused_too_fine = ?, "
        "status = ? WHERE rfq_id = ?",
        # NULL, not 0, when nothing was refused on an ask that predates
        # any refusal being counted -- see the column comment. 0 here is
        # a real observation: this ask refused nobody.
        (stored, int(refused_too_fine), status, rfq_id),
    )
    return written


def mark_deleted(conn: sqlite3.Connection, *, rfq_id: str, deleted_ms: int) -> None:
    """Stamp when the RFQ was withdrawn.

    Worth its own column because it bounds the window in which a quote could
    still have been accepted. After this instant the quotes are unreachable at
    the venue, so a later "why didn't we take it" has a hard answer.
    """
    conn.execute(
        "UPDATE combo_rfqs SET deleted_ms = ? WHERE rfq_id = ?",
        (deleted_ms, rfq_id),
    )


def mark_error(
    conn: sqlite3.Connection, *, rfq_id: str, error_text: str
) -> None:
    """Record that reading or handling this RFQ failed."""
    conn.execute(
        "UPDATE combo_rfqs SET status = ?, error_text = ? WHERE rfq_id = ?",
        (STATUS_ERROR, error_text, rfq_id),
    )


def quotes_for(conn: sqlite3.Connection, rfq_id: str) -> list[sqlite3.Row]:
    """What we captured, cheapest YES ask first.

    The read the confirm step uses. It reads OUR record rather than the venue
    because the venue's copy may already be gone -- and because the price a
    reader is confirming must be the price they were shown, not a re-read that
    may have moved underneath them.
    """
    return list(
        conn.execute(
            """
            SELECT * FROM combo_rfq_quotes
             WHERE rfq_id = ?
             ORDER BY yes_ask_tenths ASC, captured_ms ASC
            """,
            (rfq_id,),
        )
    )


# ---------------------------------------------------------------------------
# The acceptance. This is the half that spends.
# ---------------------------------------------------------------------------


def record_accept_intent(
    conn: sqlite3.Connection,
    *,
    rfq_id: str,
    quote_id: str,
    accepted_side: str,
    expected_ask_tenths: Optional[int],
    accepted_ms: int,
    dry_run: bool,
) -> None:
    """Write that we are ABOUT to accept, before the venue is called.

    **The ordering is the guard, and it is not the usual one.** Most of this
    repo records after the fact. Here the record goes first, because the RFQ
    path has **no client-generated idempotency key** -- Kalshi assigns
    `client_order_id` after execution, so unlike `OrderRequest` there is
    nothing to deduplicate a retry against. An accept whose response is lost
    is therefore an UNKNOWN that must be resolved by reading the venue, never
    by sending it again.

    A row that says "we were about to accept this" and carries no outcome is
    exactly the trail that makes that resolution possible. No row at all is
    indistinguishable from never having tried.

    `expected_ask_tenths` is what the screen showed when Joe tapped. Stored so
    that a fill at some other number is a detectable fact afterwards rather
    than an argument.
    """
    conn.execute(
        """
        UPDATE combo_rfq_quotes
           SET accepted_ms = ?, accepted_side = ?, expected_ask_tenths = ?,
               accept_dry_run = ?
         WHERE rfq_id = ? AND quote_id = ?
        """,
        (
            accepted_ms, accepted_side, expected_ask_tenths,
            1 if dry_run else 0, rfq_id, quote_id,
        ),
    )


def record_accept_outcome(
    conn: sqlite3.Connection,
    *,
    rfq_id: str,
    quote_id: str,
    outcome_status: Optional[str],
    outcome_ms: int,
) -> None:
    """What the quote's status was when last read after accepting.

    `None` is a legitimate value and means the venue no longer listed the
    quote — which is an observation, not a failure, and is stored as NULL
    rather than as a guessed `cancelled`. What a maker's non-confirmation
    looks like to a REST reader is **not documented**; inventing a status
    here would put a guess on the permanent record.
    """
    conn.execute(
        """
        UPDATE combo_rfq_quotes
           SET outcome_status = ?, outcome_ms = ?
         WHERE rfq_id = ? AND quote_id = ?
        """,
        (outcome_status, outcome_ms, rfq_id, quote_id),
    )


def record_venue_fill(
    conn: sqlite3.Connection,
    *,
    rfq_id: str,
    quote_id: str,
    read_ms: int,
    outcome: str,
    note: Optional[str] = None,
    count: Optional[float] = None,
    avg_price_tenths: Optional[int] = None,
) -> None:
    """What `/portfolio/fills` said about this acceptance. Schema v50, #74.

    **The refusals are written as carefully as the matches**, and that is the
    point of the column rather than a nicety. Whether a KXMVE combination's
    fill reaches `/portfolio/fills` at all, and under what ticker, is
    unresolved by this repo -- `combo_rfq.py` said so itself -- and a record
    that stored only the fills it managed to attribute could never answer it.
    A row reading `not_under_combo_ticker` with the tickers it DID see is the
    finding; a row reading `no_rows` on every acceptance for a month is a
    different finding; and neither is distinguishable from "nobody asked" if
    the refusal is not stored.

    `count` and `avg_price_tenths` stay `None` on every outcome but `matched`.
    Never 0: a zero count is the venue saying nothing filled, and this path
    cannot tell that from not having looked.
    """
    conn.execute(
        """
        UPDATE combo_rfq_quotes
           SET venue_fill_read_ms = ?, venue_fill_outcome = ?,
               venue_fill_note = ?, venue_fill_count = ?,
               venue_avg_fill_price_tenths = ?
         WHERE rfq_id = ? AND quote_id = ?
        """,
        (read_ms, outcome, note, count, avg_price_tenths, rfq_id, quote_id),
    )


def rfq_row(conn: sqlite3.Connection, rfq_id: str) -> Optional[sqlite3.Row]:
    """The ask a quote belongs to, or None.

    Read by the accept path to build the position a fill creates. The
    combination's ticker and its legs live on the ASK, not on the quote, and
    `selected_legs` is stored in `parlay_lookups`' own shape on purpose, so
    `parlays.legs_for_position` parses it with no second parser.
    """
    return conn.execute(
        "SELECT * FROM combo_rfqs WHERE rfq_id = ?", (rfq_id,)
    ).fetchone()


def quote_row(
    conn: sqlite3.Connection, *, rfq_id: str, quote_id: str
) -> Optional[sqlite3.Row]:
    """One captured quote, or None.

    The accept path reads the price from HERE, not from the request and not
    from a fresh venue read: the price being accepted must be the price that
    was shown, and our copy is the only record of what that was once the RFQ
    is withdrawn.
    """
    return conn.execute(
        "SELECT * FROM combo_rfq_quotes WHERE rfq_id = ? AND quote_id = ?",
        (rfq_id, quote_id),
    ).fetchone()
