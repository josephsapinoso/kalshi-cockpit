"""Asking the market what a combination costs, and recording the answer.

The orchestration behind `POST /api/parlays/rfq`. `backend/kalshi/rfq.py` is
the wire; this is the desk's use of it.

**Why this exists.** `price_card_on_kalshi` mints a combination and reads its
order book. For a combination that book is empty *by design between RFQs*, so
the desk spent six weeks telling Joe "no one is offering to sell this
combination" about markets that makers were actively pricing. This module asks
the makers.

Two design choices worth defending
----------------------------------
**It asks only about a combination this desk already minted and recorded.**
The caller names a ticker, and everything else -- the collection, the legs,
the fair value -- is read from that ticker's own `parlay_lookups` row rather
than accepted from the request. A money-adjacent route that takes the legs and
the fair value from its caller is one where the screen decides what the server
believes. The lookup already happened; its record is the authority.

**It re-reads the order book at ask time, and stores both numbers.** Not
because the book is expected to carry anything -- it is expected to be empty --
but because "the book said nothing and the makers said 59.3c" is the only
evidence that the two surfaces disagree, and storing it costs one call that is
free. Without it, proving the RFQ path is worth having needs a whole separate
experiment.

What this does not do
---------------------
- **It does not buy.** Creating an RFQ obligates nothing; acceptance is the
  spend and lands separately with its own arming decision.
- **It does not rank or recommend.** It returns the quotes cheapest-first
  because a reader needs an order, beside the fair value the card already
  computed. It draws no conclusion about whether the gap is worth taking --
  `beta = -0.141` says an ordering by that gap would be actively misleading
  (ADR 0071 s2.5).
- **It does not promise a fill.** A maker has a 3-second confirmation window
  and may decline.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
from typing import Optional

from backend.core.prices import probability_to_tenths
from backend.kalshi.orderbook import OrderBook
from backend.kalshi.rest import EXCHANGE_INDEX_COMBOS
from backend.kalshi.rfq import RfqQuote, RfqRefused, create_rfq, delete_rfq, read_quotes
from backend.parlays import LookupRefused, _cost_per_contract
from backend.store import combo_rfqs as store

logger = logging.getLogger(__name__)

#: How long to wait for makers, and how often to look.
#:
#: The one RFQ this repo has fired drew three quotes within **107ms** and they
#: were still `open` forty seconds later. So this window is not tuned to the
#: measurement -- it is deliberately several times longer than the only
#: latency ever observed, because the cost of waiting a second longer is a
#: second, and the cost of stopping early is telling Joe nobody answered when
#: somebody did. **n = 1.** If a later reading shows makers routinely slower,
#: this is the number to move, and it should move on evidence.
QUOTE_WAIT_S = 4.0
QUOTE_POLL_S = 0.4


async def _book_ask_tenths(api, ticker: str) -> Optional[int]:
    """What the public book would sell one contract for, or None.

    None is the expected answer on a combination and means the book carried no
    resting NO bid -- not that the read failed, and never zero. A failure here
    is swallowed to None as well, deliberately: this number is *context* stored
    beside the quotes, and losing the whole price because a free context read
    timed out would be the tail wagging the dog.
    """
    try:
        book = OrderBook(ticker=ticker)
        book.apply_snapshot(await api.orderbook(ticker, depth=10), None, 0)
        return book.best_yes_ask
    except Exception as exc:  # noqa: BLE001 -- context, not the answer
        logger.warning("rfq: could not read %s's book for context (%s)", ticker, exc)
        return None


def _recorded_lookup(conn: sqlite3.Connection, ticker: str) -> sqlite3.Row:
    """The most recent `parlay_lookups` row that minted this ticker.

    Refuses rather than guessing. A combination the desk has no record of
    minting is one whose legs and fair value would have to come from the
    request, and that is the shape this module exists to avoid.
    """
    row = conn.execute(
        """
        SELECT * FROM parlay_lookups
         WHERE minted_market_ticker = ?
         ORDER BY requested_ms DESC
         LIMIT 1
        """,
        (ticker,),
    ).fetchone()
    if row is None:
        raise LookupRefused(
            404,
            f"This desk has no record of minting {ticker}. Price the card "
            "first -- the RFQ is asked about a combination the desk already "
            "built, so that its legs and fair value come from the record "
            "rather than from the screen.",
        )
    return row


async def ask_market_to_price(
    conn: sqlite3.Connection,
    *,
    market_ticker: str,
    target_cost_dollars: str,
    now_ms: int,
    api,
) -> dict:
    """Fire one RFQ, capture what comes back, and withdraw it.

    **The RFQ is withdrawn before returning**, which is right while nothing
    can accept a quote: an RFQ left open consumes one of the venue's 100 open
    slots for a price nobody can take. When the confirm step lands it takes
    over the lifecycle -- the quotes vanish at delete, so accepting requires
    holding the RFQ open across the second tap.
    """
    lookup = _recorded_lookup(conn, market_ticker)
    legs = json.loads(lookup["selected_legs"] or "[]")
    if not legs:
        raise LookupRefused(
            409,
            f"The record for {market_ticker} carries no legs, so there is "
            "nothing to ask a price for.",
        )

    book_ask = await _book_ask_tenths(api, market_ticker)

    try:
        rfq_id = await create_rfq(
            api,
            market_ticker=market_ticker,
            collection_ticker=lookup["collection_ticker"],
            legs=legs,
            target_cost_dollars=target_cost_dollars,
        )
    except RfqRefused as exc:
        raise LookupRefused(
            502,
            f"Kalshi would not take the price request: {exc}. Nothing was "
            "asked and no money moved.",
        ) from exc

    # Recorded the instant it exists, before any quote can arrive: the RFQ is
    # live on the venue now, and a failure below must not lose the fact that
    # we asked.
    store.record_rfq(
        conn,
        rfq_id=rfq_id,
        requested_ms=now_ms,
        card_key=lookup["card_key"],
        ticker=market_ticker,
        collection_ticker=lookup["collection_ticker"],
        legs=legs,
        exchange_index=EXCHANGE_INDEX_COMBOS,
        target_cost_dollars=target_cost_dollars,
        fair_joint=lookup["fair_joint_conservative"],
        book_yes_ask_tenths=book_ask,
    )
    conn.commit()

    seen: dict[str, RfqQuote] = {}
    deadline = time.monotonic() + QUOTE_WAIT_S
    try:
        while time.monotonic() < deadline:
            try:
                for quote in await read_quotes(api, rfq_id):
                    seen[quote.quote_id] = quote
            except Exception as exc:  # noqa: BLE001 -- keep polling, record at the end
                logger.warning("rfq %s: quote read failed (%s)", rfq_id, exc)
            await asyncio.sleep(QUOTE_POLL_S)
    finally:
        # **The load-bearing order is READ-then-delete, and the poll loop
        # above is what enforces it** -- not the two statements below.
        #
        # This comment claimed that writing to disk before deleting was the
        # critical ordering. It is not: `seen` is already in memory here, so
        # swapping these two changes nothing, and the mutation meant to prove
        # it stayed green. Corrected rather than defended.
        #
        # What *does* lose every price is withdrawing the RFQ before or during
        # the loop, because the venue drops its copy of the quotes at delete
        # (measured 2026-09-17: a re-read returned zero) and there is no
        # second chance to fetch them. `test_a_delete_before_the_read_loses_
        # every_price` pins that, and the fake models the venue by serving
        # nothing once deleted.
        #
        # Writing first is still the right habit -- it keeps the disk copy
        # ahead of the irreversible call -- but it is a habit, not a guard,
        # and saying so is the point.
        store.record_quotes(
            conn, rfq_id=rfq_id, quotes=seen.values(), captured_ms=now_ms
        )
        conn.commit()
        await delete_rfq(api, rfq_id)
        store.mark_deleted(conn, rfq_id=rfq_id, deleted_ms=now_ms)
        conn.commit()

    quotes = sorted(seen.values(), key=lambda q: q.yes_ask_tenths)
    fair = lookup["fair_joint_conservative"]
    return {
        "status": "quoted" if quotes else "no_quotes",
        "rfq_id": rfq_id,
        "market_ticker": market_ticker,
        "target_cost_dollars": target_cost_dollars,
        "fair": {"conservative": fair},
        # What the public book said at the same instant. Expected to be null.
        "book_yes_ask_tenths": book_ask,
        # Display strings are rendered HERE, through `_cost_per_contract`,
        # for the reason every price in this repo is: money is integer tenths
        # of a cent and there is one renderer. A second implementation in
        # TypeScript is how two surfaces start disagreeing about what 59.3c
        # means on a market that ticks in deci-cents.
        "fair_display": (
            None if fair is None
            else _cost_per_contract(probability_to_tenths(fair))
        ),
        "quotes": [
            {
                "quote_id": q.quote_id,
                "yes_ask_tenths": q.yes_ask_tenths,
                "no_bid_tenths": q.no_bid_tenths,
                "contracts": q.contracts,
                "ask_display": _cost_per_contract(q.yes_ask_tenths),
            }
            for q in quotes
        ],
        "words": _words(quotes, book_ask=book_ask),
    }


def _words(quotes: list[RfqQuote], *, book_ask: Optional[int]) -> str:
    """What the screen says. States facts; draws no conclusion.

    **It must not call a quote cheap, good, or an edge.** The gap between a
    quote and the card's fair value is the consensus-vs-Kalshi gap under
    another name, and `beta = -0.141` means ranking by it puts the least
    trustworthy rows first (ADR 0071 s2.5). The screen may show the two
    numbers; it may not order the world by their difference.
    """
    if not quotes:
        return (
            "Nobody quoted this combination within a few seconds. That is a "
            "fact about this moment, not a verdict on the bet -- makers "
            "answer some requests and not others, and asking again is free. "
            "Nothing was bought and nothing is resting."
        )
    spread = quotes[-1].yes_ask_tenths - quotes[0].yes_ask_tenths
    book_line = (
        "Its public order book showed nothing at the same instant, which is "
        "the normal resting state of a combination -- the price lives in the "
        "quotes above, not in the book."
        if book_ask is None
        else "Its public order book also carried an ask at the same instant."
    )
    spread_line = (
        f" The {len(quotes)} makers were {spread / 10:.1f} cents apart, so "
        "which one you take is worth real money."
        if len(quotes) > 1 and spread
        else ""
    )
    return (
        f"{len(quotes)} maker(s) answered.{spread_line} {book_line} "
        "A quote is an offer, not a fill: the maker still has a few seconds "
        "to confirm and may decline."
    )
