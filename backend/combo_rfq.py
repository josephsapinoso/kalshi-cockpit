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
import math
import sqlite3
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional

from backend.core.hedge import SETTLEMENT_TENTHS, combo_entry_fee_tenths
from backend.core.prices import (
    dollars_to_tenths,
    format_dollars,
    format_price,
    probability_to_tenths,
)
from backend.kalshi.discovery import parse_ms
from backend.kalshi.orderbook import OrderBook
from backend.kalshi.rest import EXCHANGE_INDEX_COMBOS
from backend.kalshi.rfq import (
    ACCEPT_SIDE_FOR_BUYING_YES,
    QUOTE_DEAD_STATUSES,
    QUOTE_FILLED_STATUSES,
    RfqQuote,
    RfqRefused,
    accept_quote,
    create_rfq,
    delete_rfq,
    floor_contracts_fp,
    held_position_fp,
    mve_legs,
    read_quote,
    read_quotes,
)
import backend.hedge as held_parlays
import backend.parlays as parlays
from backend.parlays import LookupRefused, _cost_per_contract
from backend.store import combo_rfqs as store
from backend.store.combo_orders import read_shard_funds

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
#: How much of the combinations shard an RFQ may ask to spend.
#:
#: **The reason written here until 2026-09-18 was refuted by this repo's own
#: captured payload.** It said Kalshi charges the taker fee *on top of* a
#: fee-inclusive target, so a target equal to the balance leaves nothing to
#: pay the fee with. Those two halves contradict each other, and
#: `tests/fixtures/combo_rfq_quotes.json` settles which is true: on an RFQ
#: fired at `target_cost_dollars = "5.0000"`, each maker sized `contracts` so
#: that `contracts x ask + fee <= target` at k = 0.070 --
#:
#:     no_bid 0.4070 -> P 0.5930 -> solved 8.19, quoted 8.19
#:     no_bid 0.3690 -> P 0.6310 -> solved 7.72, quoted 7.72
#:     (with no fee in the sizing: 8.43 and 7.92 -- refuted on both)
#:
#: So **the fee is fitted INSIDE the target by the maker**, and `target <=
#: available` is sufficient. n = 2 quotes on one RFQ at one target: consistent
#: and decisive against the old reason, not a census of maker behaviour.
#:
#: The 0.90 therefore costs Joe 10% of his usable size for an argument that
#: does not hold. A *small* margin is still defensible on our side -- our fee
#: estimate is 0.071 against the venue's 0.070, and the maker floors
#: `contracts` to two decimals -- but that is worth ~0.1%, not 10%, and it is
#: a different argument. The false sentence was on the screen and could not
#: wait for the number, which is CLAUDE.md's fix-and-copy-ship-together rule.
#:
#: **0.99 since 2026-09-23 -- issue #71, Joe answered (A) "shrink it to 99%".**
#: The 1% left is the two small real things above (fee estimate 0.071 vs
#: 0.070, the maker's two-decimal floor), not a fee allowance. On a $3.94
#: shard the wall moved from $3.54 to $3.90.
#:
#: **It is a wall, not a second size** -- issue #62, answered (A) by Joe on
#: 2026-09-18. Until then this silently TRIMMED the target, which made two
#: independent limits govern one quantity: the caller's figure and 90% of the
#: shard, swapping over at $5.5556 of balance with no change in symptom
#: because no screen printed the dollars. Now Joe types the size and this
#: refuses it before the makers are asked. A refusal he can read is worth
#: more than a number nobody chose.
SHARD_HEADROOM = 0.99

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
    hold_open: bool = True,
) -> dict:
    """Fire one RFQ, capture what comes back, and usually leave it standing.

    **`hold_open` defaults True and that is what makes a second tap possible.**
    Withdrawing an RFQ destroys the venue's copy of every quote, so a screen
    that shows a price and then asks Joe to confirm it must keep the request
    alive in between — otherwise the thing he confirms no longer exists.

    The cost of holding is one of the venue's 100 open RFQ slots, and the
    quotes observed on 2026-09-17 were still `open` forty seconds after they
    arrived. The cost of NOT holding is that the accept path cannot exist.

    Pass `hold_open=False` for a price you have no intention of taking.
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

    # **Ask for a price you could actually pay.**
    #
    # This route asked for a flat $5.00 until 2026-09-17, and Joe hit
    # `insufficient_balance` on the first combination cheap enough for it to
    # matter: a 2.7c quote against a $5 target is **173 contracts**, and he
    # had $3.94 on the shard. A quote is all-or-nothing at the size asked
    # for, so an unaffordable target does not part-fill -- it is refused
    # after 28 makers have done the work of answering.
    #
    # The shard is read, not assumed: combinations settle on their own
    # collateral pool and the account total is the wrong number. Unreadable
    # resolves to None and the caller's target stands, because refusing to
    # ask for a price over a balance we could not parse would be worse than
    # asking for one he might not be able to take.
    target = target_cost_dollars
    try:
        funds = read_shard_funds(
            await api.get("/portfolio/balance"),
            exchange_index=EXCHANGE_INDEX_COMBOS,
        )
        available = funds.available_tenths
    except Exception as exc:  # noqa: BLE001 -- context, not the answer
        logger.warning("rfq: could not read the shard balance (%s)", exc)
        available = None

    if available is not None:
        headroom_dollars = (available / 1000.0) * SHARD_HEADROOM
        if headroom_dollars < float(target):
            # **Refused here, and not trimmed.** Trimming turned Joe's figure
            # into a number nobody chose and hid the wall behind it. Refusing
            # costs him one re-type and costs the makers nothing -- which is
            # the whole point: the failure this replaced burned 28 makers'
            # answers before telling him (2026-09-17).
            # The words state the limit and do NOT explain it as a fee
            # allowance: the captured payload says the fee is fitted inside
            # the target by the maker, so "the rest is left for the fee" --
            # which this sentence said until 2026-09-18 -- was false, on the
            # screen that spends. The margin is 0.99 on Joe's answer to
            # issue #71; this refusal claims nothing about why.
            # FLOORED to the cent, never rounded: at 0.99 a $3.9359 shard
            # walls at $3.8965, and `:.2f` printed "$3.90" -- a figure this
            # same check then refuses. The number he is told he can ask for
            # must be one he can ask for.
            askable = math.floor(max(headroom_dollars, 0.0) * 100) / 100
            raise LookupRefused(
                400,
                f"The combinations shard cannot cover ${float(target):,.2f} "
                f"for this. The most this desk will ask for right now is "
                f"**${askable:,.2f}**, which is "
                f"{SHARD_HEADROOM:.0%} of what is on the shard. Ask for a "
                "smaller amount, or add funds to the combinations shard.",
            )

    try:
        handle = await create_rfq(
            api,
            market_ticker=market_ticker,
            collection_ticker=lookup["collection_ticker"],
            legs=legs,
            target_cost_dollars=target,
        )
    except RfqRefused as exc:
        raise LookupRefused(
            502,
            f"Kalshi would not take the price request: {exc}. Nothing was "
            "asked and no money moved.",
        ) from exc
    rfq_id = handle.rfq_id
    # **The target the VENUE holds, which is not always the one typed**
    # (#72). `create_rfq` reuses an open RFQ whose target is at least the
    # one wanted, and this desk holds RFQs open so the accept stays
    # reachable -- so asking at $1.00 and then at $5.00 returns the $1.00
    # request, with quotes sized for $1.00. Falls back to the requested
    # figure ONLY when the venue named none, which is the `contracts=`
    # ask; it never substitutes the request for an unread answer.
    held_target = handle.target_cost_dollars or target

    # Recorded the instant it exists, before any quote can arrive: the RFQ is
    # live on the venue now, and a failure below must not lose the fact that
    # we asked.
    # `INSERT ... ON CONFLICT DO NOTHING`, so re-asking on a reused RFQ keeps
    # the original row and its first-asked timestamp rather than rewriting it.
    store.record_rfq(
        conn,
        rfq_id=rfq_id,
        requested_ms=now_ms,
        card_key=lookup["card_key"],
        ticker=market_ticker,
        collection_ticker=lookup["collection_ticker"],
        legs=legs,
        exchange_index=EXCHANGE_INDEX_COMBOS,
        target_cost_dollars=target,
        fair_joint=lookup["fair_joint_conservative"],
        book_yes_ask_tenths=book_ask,
        purpose="buy",
    )
    conn.commit()

    seen: dict[str, RfqQuote] = {}
    # **Unioned by id across polls, not summed** (#73). The loop below reads
    # the same RFQ every `QUOTE_POLL_S`, so a quote refused once is refused
    # on every pass; adding the counts up would tell him six makers answered
    # when one did. `QuoteRead` carries ids for exactly this.
    too_fine: set[str] = set()
    deadline = time.monotonic() + QUOTE_WAIT_S
    try:
        while time.monotonic() < deadline:
            try:
                read = await read_quotes(api, rfq_id)
                too_fine |= read.refused_finer_than_tenths
                for quote in read.quotes:
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
            conn, rfq_id=rfq_id, quotes=seen.values(), captured_ms=now_ms,
            # The same union-by-id the payload reports (#73), so the
            # durable row and the screen cannot disagree about how many
            # makers answered.
            refused_too_fine=len(too_fine),
        )
        conn.commit()
        if not hold_open:
            await delete_rfq(api, rfq_id)
            store.mark_deleted(conn, rfq_id=rfq_id, deleted_ms=now_ms)
            conn.commit()

    quotes = sorted(seen.values(), key=lambda q: q.yes_ask_tenths)
    fair = lookup["fair_joint_conservative"]
    return {
        # **Three outcomes, not two** (#73). `priced_too_finely` is the case
        # where makers answered and every price was finer than a tenth of a
        # cent, which this desk refuses rather than rounds. It used to render
        # as `no_quotes`, i.e. "nobody quoted this combination" -- a false
        # sentence on the surface that spends, and the actionable one, since
        # the price is readable in the Kalshi app. It ranks BELOW `quoted`:
        # if even one quote is representable there is a price to show, and
        # the refusals go in the words instead.
        "status": (
            "quoted" if quotes
            else "priced_too_finely" if too_fine
            else "no_quotes"
        ),
        # How many distinct quotes were refused on precision. Unioned by id
        # across polls (see the loop above), so it is makers, not reads.
        "refused_too_fine": len(too_fine),
        "rfq_id": rfq_id,
        "market_ticker": market_ticker,
        "target_cost_dollars": held_target,
        # **These two are now equal by construction**, since the trim became
        # a refusal on 2026-09-18. The field stays because a real divergence
        # exists and is NOT this one: `create_rfq` reuses an open RFQ whenever
        # its existing target is at least the one wanted, so Joe can type
        # $5.00 against an RFQ the venue was asked at $1.00 -- and this
        # payload would report $5.00 for it. Surfacing that needs `create_rfq`
        # to return the target it actually used, which it does not. Issue #72.
        "target_cost_requested": target_cost_dollars,
        "fair": {"conservative": fair},
        # What the public book said at the same instant. Expected to be null.
        "book_yes_ask_tenths": book_ask,
        # **Rendered, so the screen can show BOTH surfaces** (issue #66).
        # Neither dominates: on 2026-09-17 the book beat the RFQ on two of
        # three positions and the RFQ was the only price on the third, so a
        # desk reading one surface sometimes takes the worse number. Null is
        # the expected value and means the book was empty, which is a
        # combination's resting state and not a fault.
        "book_ask_display": (
            None if book_ask is None else _cost_per_contract(book_ask)
        ),
        # When these prices were captured, so the screen can age them
        # (issue #67). A maker has about **three seconds** to stand behind a
        # quote on a combination against 30 elsewhere, so a price with no age
        # on it is a price the reader cannot tell is dead.
        "asked_ms": now_ms,
        # **Whether the button below this will actually spend.** Surfaced with
        # the price, not discovered after the tap: a control that says "Take
        # it" and then does nothing is this repo's named failure -- a screen
        # promising an action the server does not perform -- and it has
        # already run three times here.
        "accepts_are_armed": not RFQ_ACCEPTS_ARE_DRY_RUNS,
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
                # **What leaves the account if this quote is taken**, fee
                # included (issue #68, and #39's settled precedent on the
                # singles ticket). A per-contract price is not a stake, and
                # the button that spends was showing only the price.
                **_all_in(q),
            }
            for q in quotes
        ],
        "words": _words(
            quotes,
            book_ask=book_ask,
            refused_too_fine=len(too_fine),
            asked_at=held_target,
            requested=target_cost_dollars,
        ),
    }


def _all_in(quote: RfqQuote) -> dict:
    """What taking this quote costs in dollars, fee included, or nulls.

    `all_in_display` is the number the Take-it button prints. It is the
    contracts times the ask, **plus** Kalshi's combination taker fee, because
    the fee is charged on top of the contracts on a fee-inclusive target and
    a figure without it is not what leaves the account.

    The fee is `combo_entry_fee_tenths`'s modelled number at
    `COMBO_TAKER_COEFFICIENT` (0.071), the same one `/hedge` sinks on an open
    position -- one fee model, not two (ADR 0145).

    **Nulls when the size is unreadable**, never a price with the fee
    silently dropped: a quote with no size is a quote whose cost is not
    known, and the button says so rather than printing a smaller number.

    What this does not establish: that the venue will charge exactly this.
    The coefficient exceeds every implied k this repo has measured by
    construction, so the figure errs high -- and erring high on a cost shown
    before a tap is the safe direction, which is the opposite of the rule for
    a hedge lock.
    """
    contracts = quote.contracts
    if contracts is None:
        return {"all_in_tenths": None, "all_in_display": None, "fee_tenths": None}
    try:
        contracts = float(contracts)
    except (TypeError, ValueError):
        return {"all_in_tenths": None, "all_in_display": None, "fee_tenths": None}
    if not math.isfinite(contracts) or contracts <= 0:
        return {"all_in_tenths": None, "all_in_display": None, "fee_tenths": None}

    stake = int(round(contracts * quote.yes_ask_tenths))
    settled = int(round(contracts * SETTLEMENT_TENTHS))
    fee = combo_entry_fee_tenths(stake, settled) if settled > stake else None
    if fee is None:
        return {"all_in_tenths": None, "all_in_display": None, "fee_tenths": None}
    return {
        "all_in_tenths": stake + fee,
        "all_in_display": format_dollars(stake + fee),
        "fee_tenths": fee,
    }


def _words(
    quotes: list[RfqQuote],
    *,
    book_ask: Optional[int],
    refused_too_fine: int = 0,
    asked_at: Optional[str] = None,
    requested: Optional[str] = None,
) -> str:
    """What the screen says. States facts; draws no conclusion.

    **It must not call a quote cheap, good, or an edge.** The gap between a
    quote and the card's fair value is the consensus-vs-Kalshi gap under
    another name, and `beta = -0.141` means ranking by it puts the least
    trustworthy rows first (ADR 0071 s2.5). The screen may show the two
    numbers; it may not order the world by their difference.

    **`asked_at` and `requested` are said only when they DIFFER** (#72).
    They differ when an open RFQ was reused at a smaller target, which
    means the quotes below were sized for a number Joe did not type.
    Saying it unconditionally would train him to skip it, the way a
    staleness warning that could never be false did (ADR 0170 Amd 1).

    **`refused_too_fine` is a count of MAKERS, not of reads** -- the caller
    unions quote ids across the poll loop before passing it. It is a separate
    branch because "nobody quoted" and "someone quoted a price we cannot
    print" are different facts and only the second tells him where to look
    (#73).
    """
    # Prepended rather than appended: it changes what every price below
    # it means, so it cannot sit after them.
    reuse_line = ""
    if asked_at and requested and asked_at != requested:
        reuse_line = (
            f"These quotes answer a request for ${asked_at}, not the "
            f"${requested} you asked for -- an earlier request on this "
            "combination was still open, so the venue was never asked at "
            "the larger number. The sizes below are the ones it was "
            "asked at. "
        )

    if not quotes and refused_too_fine:
        # No hedge about whether they *would* have been takeable: the desk
        # refused the price before anyone could act on it, so the only honest
        # claim is that a price existed and this screen is not showing it.
        return reuse_line + (
            f"{refused_too_fine} maker(s) answered, and every price was finer "
            "than a tenth of a cent -- hundredths, which combinations quote "
            "near 0c and 100c. This desk refuses such a price rather than "
            "rounding it, because rounding would print a price the venue "
            "never offered. So there IS a price and it is not on this screen: "
            "the Kalshi app will show it. Nothing was bought and nothing is "
            "resting."
        )
    if not quotes:
        return reuse_line + (
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
    # Said even when there IS a price, because the cheapest quote on screen
    # may not be the cheapest quote that arrived -- a refused centi-cent
    # price near 0c would have sorted first.
    fine_line = (
        f" A further {refused_too_fine} priced finer than a tenth of a cent "
        "and is not shown; the Kalshi app will show it."
        if refused_too_fine
        else ""
    )
    return reuse_line + (
        f"{len(quotes)} maker(s) answered.{spread_line}{fine_line} {book_line} "
        "A quote is an offer, not a fill: the maker still has a few seconds "
        "to confirm and may decline."
    )


# ---------------------------------------------------------------------------
# Asking what makers would pay for a combination Joe HOLDS. Issue #96.
# ---------------------------------------------------------------------------


async def ask_makers_to_buy_back(
    conn: sqlite3.Connection,
    *,
    position_id: int,
    now_ms: int,
    api,
) -> dict:
    """Fire one sell-side RFQ on a held combination, record it, withdraw it.

    The exit half of Joe's answer to #63: **show both exit prices on
    `/hedge`, read-only, no selling from the desk.** The public book's bid
    is #95 (`hedge.combo_book_state`); this is the other surface, and the
    one that was the only exit on 2026-09-17's third position.

    **Everything about the ask comes from the venue or our own row, nothing
    from the request** -- which carries only a position id. The ticker is
    the position's recorded `combo_ticker`; the SIZE is the venue's own
    `position_fp`, floored to its 0.01 grid (`floor_contracts_fp`, defect
    1: never more than is held, and `parlay_positions` has no contracts
    column to read instead); the legs are the market's own
    (`mve_legs`), because an RFQ-accepted position recorded no lookup.

    **Withdrawn every time, in the `finally`, after the quotes are written.**
    There is no accept path for an exit (Joe's #63 answer), so holding the
    RFQ open buys nothing and costs one of the venue's 100 slots -- and, on
    the buy route, a 409 the next time he asks what a card costs.

    **Not called from `hedge_watch`**, which runs `build_payload` every 60 s
    unattended (defect 2): that would fire ~1,440 RFQs a day on the same
    shard-1 write budget the armed order path uses. It is a tap, through its
    own route. `tests/test_hedge_sell_quote.py` pins the absence.

    What this does not establish: that a bid would fill, or that it is good.
    Every best bid on 2026-09-17 sat below cost basis. A count at one
    moment, never a rate.
    """
    position = conn.execute(
        "SELECT id, source, combo_ticker, status FROM parlay_positions "
        "WHERE id = ?",
        (position_id,),
    ).fetchone()
    if position is None:
        raise LookupRefused(
            404, "There is no such ticket on this desk. Nothing was asked."
        )
    if position["status"] != "open":
        raise LookupRefused(
            409,
            "This ticket is no longer being watched, so the desk will not ask "
            "about it. Nothing was asked.",
        )
    ticker = position["combo_ticker"]
    if position["source"] != "kalshi_combo" or not ticker:
        raise LookupRefused(
            409,
            "This ticket was recorded by hand, so the desk has no Kalshi "
            "combination to ask about. Nothing was asked.",
        )
    ticker = str(ticker)

    try:
        rows = await api.positions()
    except Exception as exc:  # noqa: BLE001 -- the size is unknowable without it
        raise LookupRefused(
            502,
            f"Kalshi's positions could not be read ({exc}), so the size to ask "
            "about is unknown. Nothing was asked.",
        ) from exc
    position_fp = held_position_fp(rows, ticker)
    if position_fp is None:
        raise LookupRefused(
            409,
            "Kalshi does not show this combination among your open positions "
            "right now -- it may already have settled, which a combination "
            "does before its legs do. Nothing was asked.",
        )
    contracts_fp = floor_contracts_fp(position_fp)
    if contracts_fp is None:
        raise LookupRefused(
            409,
            f"Kalshi shows {position_fp} contracts held, which is not a size "
            "that can be asked about (under a hundredth of a contract, or "
            "not a YES holding). Nothing was asked.",
        )

    try:
        collection, legs = mve_legs(await api.get(f"/markets/{ticker}"))
    except RfqRefused as exc:
        raise LookupRefused(
            502, f"Kalshi's market for this combination is unreadable: {exc}. "
            "Nothing was asked.",
        ) from exc
    except Exception as exc:  # noqa: BLE001 -- transport; nothing was asked
        raise LookupRefused(
            502, f"Kalshi's market for this combination could not be read "
            f"({exc}). Nothing was asked.",
        ) from exc

    try:
        handle = await create_rfq(
            api,
            market_ticker=ticker,
            collection_ticker=collection,
            legs=legs,
            contracts_fp=contracts_fp,
        )
    except RfqRefused as exc:
        raise LookupRefused(
            409 if "already open" in str(exc) else 502,
            f"Kalshi would not take the question: {exc} Nothing was asked "
            "and no money moved.",
        ) from exc
    rfq_id = handle.rfq_id

    store.record_rfq(
        conn,
        rfq_id=rfq_id,
        requested_ms=now_ms,
        ticker=ticker,
        collection_ticker=collection,
        legs=legs,
        exchange_index=EXCHANGE_INDEX_COMBOS,
        purpose="exit",
        contracts_fp_requested=contracts_fp,
    )
    conn.commit()

    seen: dict[str, RfqQuote] = {}
    # Union by id across polls (#73's rule): a count of MAKERS, not reads.
    bid_too_fine: set[str] = set()
    deadline = time.monotonic() + QUOTE_WAIT_S
    try:
        while time.monotonic() < deadline:
            try:
                read = await read_quotes(api, rfq_id, keep_sell_only=True)
                bid_too_fine |= read.refused_bid_finer_than_tenths
                for quote in read.quotes:
                    seen[quote.quote_id] = quote
            except Exception as exc:  # noqa: BLE001 -- keep polling
                logger.warning("exit rfq %s: quote read failed (%s)", rfq_id, exc)
            await asyncio.sleep(QUOTE_POLL_S)
    finally:
        # READ, write, then withdraw: the venue drops its copy at delete.
        store.record_quotes(
            conn, rfq_id=rfq_id, quotes=seen.values(), captured_ms=now_ms,
            refused_too_fine=len(bid_too_fine),
        )
        conn.commit()
        await delete_rfq(api, rfq_id)
        store.mark_deleted(conn, rfq_id=rfq_id, deleted_ms=now_ms)
        conn.commit()

    bids = sorted(
        (q for q in seen.values() if q.yes_bid_tenths is not None),
        key=lambda q: -int(q.yes_bid_tenths or 0),
    )
    best = bids[0] if bids else None
    return {
        "status": (
            "bid" if bids
            else "bid_too_finely" if bid_too_fine
            else "no_bid"
        ),
        "position_id": position_id,
        "market_ticker": ticker,
        "rfq_id": rfq_id,
        # The venue's holding verbatim, and the floored size actually asked.
        "held_fp": position_fp,
        "asked_fp": contracts_fp,
        "asked_ms": now_ms,
        "makers_answered": len(seen),
        "refused_bid_too_fine": len(bid_too_fine),
        "best_bid_tenths": None if best is None else best.yes_bid_tenths,
        "best_bid_display": (
            None if best is None else _cost_per_contract(best.yes_bid_tenths)
        ),
        "bids": [
            {
                "quote_id": q.quote_id,
                "yes_bid_tenths": q.yes_bid_tenths,
                "bid_display": _cost_per_contract(q.yes_bid_tenths),
                "contracts": q.yes_bid_contracts,
            }
            for q in bids
        ],
        "words": _exit_words(
            makers=len(seen), bids=bids, bid_too_fine=len(bid_too_fine),
            asked_fp=contracts_fp,
        ),
    }


def _exit_words(
    *, makers: int, bids: list[RfqQuote], bid_too_fine: int, asked_fp: str
) -> str:
    """What the exit ask says. Facts only -- and never a frequency.

    **Joe's rule, twice (#60, #64): say what an exit COSTS, never how often
    one exists.** Four frequency clauses about combination exits have been
    written into this repo and withdrawn. So nothing here says bids are
    rare, common, usual or unusual; each sentence is about these makers, at
    this moment, on this ticket.

    It says the desk does not sell, because that is Joe's #63 answer and
    the one fact a reader needs before reading a bid as something to tap.
    """
    tail = (
        " The request was withdrawn; nothing was sold. This desk does not "
        "sell -- selling happens in the Kalshi app, at whatever makers bid "
        "then, less Kalshi's fee."
    )
    fine = (
        f" A further {bid_too_fine} bid at a price finer than a tenth of a "
        "cent, which this screen will not round; the Kalshi app shows it."
        if bid_too_fine
        else ""
    )
    if bids:
        best = bids[0]
        size = (
            f", for {best.yes_bid_contracts:g} contracts"
            if best.yes_bid_contracts is not None
            else ""
        )
        return (
            f"Asked about {asked_fp} contracts: {makers} maker(s) answered and "
            f"{len(bids)} bid to buy this back. Best bid "
            f"{format_price(best.yes_bid_tenths)} a contract{size}.{fine}"
            + tail
        )
    if bid_too_fine:
        return (
            f"Asked about {asked_fp} contracts: {bid_too_fine} maker(s) bid to "
            "buy this back at a price finer than a tenth of a cent, which "
            "this screen will not round. The Kalshi app shows it." + tail
        )
    if makers:
        return (
            f"Asked about {asked_fp} contracts: {makers} maker(s) answered and "
            "none bid to buy this back in these few seconds. That is a fact "
            "about this moment, not about the ticket; asking again is free."
            + tail
        )
    return (
        f"Asked about {asked_fp} contracts: no maker answered within a few "
        "seconds. That is a fact about this moment, not about the ticket; "
        "asking again is free." + tail
    )



# ---------------------------------------------------------------------------
# What the venue says it actually did. Issue #74, ADR 0178.
# ---------------------------------------------------------------------------

#: How many fills to ask for. Small on purpose: the targeted read is bounded
#: by the combination's own ticker, and the bare fallback below only needs
#: enough rows to see what landed in the last two minutes.
VENUE_FILL_LIMIT = 50

#: How far BEFORE the acceptance a fill may be stamped and still be this
#: acceptance's. Small, and small is the safe direction: too tight yields
#: `no_rows`, which keeps the recorded stake and says so; too loose would
#: attribute an EARLIER fill of the same combination to this trade and build
#: a money figure on someone else's bet -- the failure
#: `contract_count_disagrees` refuses on the order path. Five seconds covers
#: clock skew between this process's `now_ms` and Kalshi's own stamps; the
#: handshake itself resolves in about four seconds.
VENUE_FILL_SLACK_MS = 5_000

#: How far AFTER the acceptance the bare fallback read still calls a fill
#: interesting enough to name in the note. Evidence only -- nothing computes
#: with it -- so it is generous where the slack above is tight.
VENUE_FILL_WINDOW_MS = 120_000

#: The one re-read, and when it is taken. Execution is about 1.1s behind
#: confirmation and a fill's propagation to `/portfolio/fills` is unmeasured,
#: so a read that finds FEWER contracts than were quoted has two readings: a
#: genuine part-fill, or a read that landed mid-propagation. One re-read
#: separates them in the common case and costs nothing in the normal one,
#: because it is taken only on disagreement.
#:
#: **It is not a proof of completeness and must never be described as one.**
#: Nothing in this path can know that the venue has finished writing. What it
#: does is make the cheap explanation cheap to rule out.
VENUE_FILL_RECHECK_S = 0.75

#: The outcome vocabulary written to `combo_rfq_quotes.venue_fill_outcome`.
#: The refusals matter as much as the match -- see `store.record_venue_fill`.
VENUE_FILL_MATCHED = "matched"
VENUE_FILL_MATCHED_PARTIAL = "matched_partial"
VENUE_FILL_NO_ROWS = "no_rows"
VENUE_FILL_OTHER_TICKER = "not_under_combo_ticker"
VENUE_FILL_WRONG_SIDE = "unexpected_fill_side"
VENUE_FILL_UNPARSABLE = "unparsable"
VENUE_FILL_TOO_FINE = "finer_than_a_tenth"
VENUE_FILL_EXCEEDS_QUOTE = "count_exceeds_quote"
VENUE_FILL_READ_FAILED = "read_failed"

#: The outcomes whose count and price may be used for money.
VENUE_FILL_USABLE = (VENUE_FILL_MATCHED, VENUE_FILL_MATCHED_PARTIAL)


@dataclass(frozen=True)
class VenueFill:
    """What `/portfolio/fills` said, and which of the named states it was.

    `count` and `avg_price_tenths` are populated only when `outcome` is one of
    `VENUE_FILL_USABLE`; on every refusal they are `None`, never 0 -- the
    caller keeps the quote's own numbers and `/hedge` says which it used.
    """

    outcome: str
    note: Optional[str] = None
    count: Optional[float] = None
    avg_price_tenths: Optional[int] = None

    @property
    def usable(self) -> bool:
        return (
            self.outcome in VENUE_FILL_USABLE
            and self.count is not None
            and self.avg_price_tenths is not None
        )


def _fill_stamp_ms(row: dict) -> Optional[int]:
    """When the venue says a fill happened, or None. `parse_fill`'s rule."""
    stamp = parse_ms(row.get("created_time"))
    if stamp is None:
        ts = row.get("ts")
        stamp = int(ts) * 1000 if isinstance(ts, int) and ts > 0 else None
    return stamp


def _fill_count(value) -> Optional[float]:
    """A `count_fp` string to a count. None when unreadable, never 0."""
    if value is None:
        return None
    try:
        as_decimal = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not as_decimal.is_finite() or as_decimal <= 0:
        return None
    return float(as_decimal)


def _shape_note(rows: list) -> str:
    """Which documented fields the rows carried. The wire-shape half of #74.

    **A KXMVE fill has never been observed on this account.** The 25-fill
    capture behind `parse_fill` is single-market, and whether a combination's
    fill carries `is_taker` and `fee_cost` at all decides whether the fee
    model can ever be validated on this path. Recorded as text rather than
    acted on, because a field's absence is a fact to read later, not a
    condition to branch on now.
    """
    taker = sum(1 for r in rows if isinstance(r.get("is_taker"), bool))
    fee = sum(1 for r in rows if r.get("fee_cost") is not None)
    return f"rows={len(rows)} is_taker={taker} fee_cost={fee}"


def _aggregate_fills(rows: list, *, quoted: Optional[float]) -> VenueFill:
    """The venue's own size and average price for one acceptance.

    Every refusal below returns the quote's numbers to the caller by leaving
    `count` and `avg_price_tenths` empty, and names itself, because the name
    is what settles #74's question later.

    **Only a `yes` fill is read.** `accepted_side` names the MAKER's side, so
    buying YES sends `"no"` and the fill prints on ours -- measured
    2026-09-17, and the wrong reading of that would have bought the opposite
    contract at ~250x. A row on the other side is therefore not this
    purchase, and is refused rather than re-interpreted.
    """
    ours = [r for r in rows if r.get("side") == "yes"]
    if not ours:
        sides = sorted({str(r.get("side")) for r in rows})
        return VenueFill(
            VENUE_FILL_WRONG_SIDE, f"sides={','.join(sides)} {_shape_note(rows)}"
        )

    total = 0.0
    cost = 0.0
    for row in ours:
        count = _fill_count(row.get("count_fp"))
        price = dollars_to_tenths(row.get("yes_price_dollars"))
        if count is None or price is None:
            return VenueFill(VENUE_FILL_UNPARSABLE, _shape_note(ours))
        total += count
        cost += count * price
    if total <= 0:
        return VenueFill(VENUE_FILL_UNPARSABLE, _shape_note(ours))

    # The same refusal the write path and `fractional_venue_fill_count` make:
    # a settlement is a whole 1000 tenths a contract, so a size finer than a
    # hundredth cannot be reproduced in the unit `parlay_positions` stores.
    exact_return = total * SETTLEMENT_TENTHS
    if abs(exact_return - round(exact_return)) > 1e-6:
        return VenueFill(VENUE_FILL_TOO_FINE, f"count={total} {_shape_note(ours)}")

    if quoted is not None and total > quoted + 1e-9:
        # More contracts than the maker quoted cannot all be this acceptance,
        # so the rows in hand are not one bet and the count a stake would be
        # multiplied by is not this position's.
        return VenueFill(
            VENUE_FILL_EXCEEDS_QUOTE,
            f"count={total} quoted={quoted} {_shape_note(ours)}",
        )

    partial = quoted is not None and total < quoted - 1e-9
    return VenueFill(
        VENUE_FILL_MATCHED_PARTIAL if partial else VENUE_FILL_MATCHED,
        f"count={total} quoted={quoted} {_shape_note(ours)}",
        count=total,
        avg_price_tenths=int(round(cost / total)),
    )


async def read_venue_fill(
    api, *, ticker: str, accepted_ms: int, quoted: Optional[float]
) -> VenueFill:
    """Ask Kalshi what it actually did, and never let the answer block.

    **This is a MEASUREMENT before it is a correction, and the ticket it
    closes says so.** ADR 0169 recorded an RFQ position at the quote's own
    size on the ground that a maker's quote is all-or-nothing -- asserted in
    two modules, cited to nothing. The only executed acceptance this repo has
    was fired at `contracts = 1`, and its measurement doc says in terms that
    it speaks to no partial fill. If a quote can part-fill, the position is
    wrong in both size and stake and **nothing downstream can catch it**: the
    basis is `as_recorded`, so there is no reconciliation to fail.

    **"Whether a KXMVE fill reaches `/portfolio/fills` at all, under what
    ticker, is unresolved" was this module's own comment, and it was wrong.**
    `tests/fixtures/portfolio_fills_redacted.json` holds eight combination
    fills, every one under the COMBINATION's ticker in both `ticker` and
    `market_ticker`, `side: "yes"`, fractional `count_fp`, `fee_cost` present
    -- and `test_portfolio_poll.py` has been reconciling a fee against one of
    them since ADR 0073. The answer was on disk (ADR 0178 section 2).

    What those rows do NOT settle is **when** a fill becomes readable: they
    were captured days after the trades, execution runs ~1.1s behind
    confirmation, and propagation here is unmeasured. So an empty read is the
    expected case rather than an error, and it is recorded with its elapsed
    time so a month of them can say whether it is *too early* or *never*. The
    bare fallback read answers the other side of that: what DID land in the
    window, under whatever ticker. Both land in `venue_fill_outcome` and
    `venue_fill_note`.

    Raises nothing. The trade is done and the money is spent; a bookkeeping
    read must not be able to turn a completed purchase into an error.
    """
    floor_ms = accepted_ms - VENUE_FILL_SLACK_MS
    try:
        rows = await api.fills(ticker=ticker, limit=VENUE_FILL_LIMIT)
    except Exception as exc:  # noqa: BLE001 -- a read may not break a trade
        logger.warning("rfq fill read for %s failed (%s)", ticker, exc)
        return VenueFill(VENUE_FILL_READ_FAILED, str(exc)[:200])

    # The venue's `ticker` filter is trusted for what it returns, not for
    # what it leaves out: the rows are re-checked here so a parameter the
    # endpoint ignores cannot smuggle another market's fill into this stake.
    mine = [
        r for r in rows
        if r.get("ticker") == ticker and (_fill_stamp_ms(r) or 0) >= floor_ms
    ]
    if mine:
        found = _aggregate_fills(mine, quoted=quoted)
        if found.outcome != VENUE_FILL_MATCHED_PARTIAL:
            return found
        # Fewer contracts than were quoted. One re-read, then take whichever
        # answer saw more -- see `VENUE_FILL_RECHECK_S` for why this is not a
        # completeness proof.
        await asyncio.sleep(VENUE_FILL_RECHECK_S)
        try:
            again = await api.fills(ticker=ticker, limit=VENUE_FILL_LIMIT)
        except Exception as exc:  # noqa: BLE001 -- the first answer still stands
            logger.warning("rfq fill re-read for %s failed (%s)", ticker, exc)
            return found
        mine = [
            r for r in again
            if r.get("ticker") == ticker and (_fill_stamp_ms(r) or 0) >= floor_ms
        ]
        second = _aggregate_fills(mine, quoted=quoted) if mine else found
        if second.usable and found.usable and (second.count or 0) > (found.count or 0):
            return second
        return found

    # Nothing under the combination's own ticker. What DID land in the window
    # is the evidence for "under what ticker", and it is the whole reason this
    # second call exists.
    try:
        recent = await api.fills(limit=VENUE_FILL_LIMIT)
    except Exception as exc:  # noqa: BLE001
        logger.warning("rfq bare fill read failed (%s)", exc)
        return VenueFill(VENUE_FILL_NO_ROWS, f"bare read failed: {str(exc)[:120]}")
    near = sorted({
        str(r.get("ticker")) for r in recent
        if abs((_fill_stamp_ms(r) or 0) - accepted_ms) <= VENUE_FILL_WINDOW_MS
    })
    if not near:
        return VenueFill(VENUE_FILL_NO_ROWS, f"bare rows={len(recent)}")
    return VenueFill(VENUE_FILL_OTHER_TICKER, ("seen=" + ",".join(near))[:200])


# ---------------------------------------------------------------------------
# Accepting. The spend.
# ---------------------------------------------------------------------------

#: **The arming switch for the accept path. ARMED 2026-09-17, on Joe's word
#: and on a measurement, in that order.**
#:
#: It was True until the question below was settled, and the question was
#: never about this code. `accepted_side` names the maker's side being
#: lifted -- so buying YES means sending `"no"` -- and that is stated
#: outright only on Kalshi's FIX page. The REST reference says "the side that
#: was accepted" without saying whose, and on a real quote the two readings
#: were **buy YES at 0.40c or buy NO at 99.60c**.
#:
#: **Settled by one bounded accept (#61 option (a)), and it went our way:**
#:
#:     sent accepted_side="no" against a maker NO bid of 99.60c
#:     accepted 17:53:28.0 -> confirmed 17:53:28.1 -> executed 17:53:29.25
#:     fill: side "yes", action "buy", yes_price_dollars "0.0040"
#:     balance 5.7899 -> 5.7856   ($0.0043, price plus fee)
#:
#: `docs/measurements/2026-09-17-accepted-side-names-the-makers-side.md`.
#:
#: **The first attempt did not execute and that is why this constant has a
#: story.** It stopped watching at `confirmed` and withdrew the RFQ; the
#: quote was cancelled 1.7s later with no fill. Confirmation is the maker
#: agreeing, execution is a separate step about a second behind it, and
#: `QUOTE_FILLED_STATUSES` said `confirmed` was a fill until that run.
RFQ_ACCEPTS_ARE_DRY_RUNS = False

#: How long to watch for the maker's confirmation, and how often.
#:
#: A combination is a High Volatility Market: the maker has **3 seconds** to
#: confirm and 1 more to execute, against 30/15 elsewhere. Ten seconds is
#: therefore generous by design -- the whole handshake resolves in about four
#: -- because the failure being avoided is reporting "no fill" on a trade that
#: did happen. Polling at 500ms rather than waiting once, so a fast confirm is
#: seen as fast.
#:
#: **There is no `quote_confirmed` WebSocket event**, so REST polling is the
#: only way to observe the confirmed state. Documented, not chosen.
CONFIRM_WATCH_S = 10.0
CONFIRM_POLL_S = 0.5


async def accept_quote_for_joe(
    conn: sqlite3.Connection,
    *,
    rfq_id: str,
    quote_id: str,
    now_ms: int,
    api,
    dry_run: bool = RFQ_ACCEPTS_ARE_DRY_RUNS,
) -> dict:
    """Lift one maker's bid, then watch for the confirmation.

    **The second tap of B = (ii).** Joe has already seen this exact quote; no
    ceiling is typed, because an RFQ hands you the price after you ask and a
    number typed in advance would be a guess at it.

    The price accepted is read from OUR record of the quote, never from the
    request and never from a fresh venue read. Two reasons, and the second is
    the one that bites: the price must be the price he was shown, and once the
    RFQ is withdrawn our copy is the only record of what that was.
    """
    quote = store.quote_row(conn, rfq_id=rfq_id, quote_id=quote_id)
    if quote is None:
        raise LookupRefused(
            404,
            "That quote is not in this desk's record, so there is nothing to "
            "accept. Ask for a price again -- a quote cannot be re-fetched "
            "once its request is withdrawn.",
        )
    if quote["accepted_ms"] is not None:
        # Not an idempotent replay: there is no key to deduplicate against, so
        # a second accept is a second real trade. Refusing is the only safe
        # answer, and the words say what to do instead.
        raise LookupRefused(
            409,
            "This quote was already accepted at "
            f"{quote['accepted_ms']}. It is not re-sent, because an RFQ "
            "acceptance carries no idempotency key and a retry would be a "
            "second real trade. Read its outcome rather than tapping again.",
        )

    # **An exit ask's quote is never accepted here** (#96). Since v56 the
    # quote table also holds answers to "what would makers pay for this
    # combination I hold" -- rows whose buy-side price may be NULL. This
    # path BUYS YES, and Joe's answer to #63 was "no selling from the desk",
    # so a quote from an exit ask, or one with no price to buy at, is
    # refused before any intent is written or anything is sent.
    rfq = store.rfq_row(conn, rfq_id)
    if (rfq is not None and rfq["purpose"] == "exit") or quote["yes_ask_tenths"] is None:
        raise LookupRefused(
            409,
            "That quote answered a question about selling a combination you "
            "hold, not buying one, and this desk does not sell. Nothing was "
            "sent and no money moved.",
        )

    side = ACCEPT_SIDE_FOR_BUYING_YES
    expected = quote["yes_ask_tenths"]

    # Intent first, outcome second. See `record_accept_intent`.
    store.record_accept_intent(
        conn, rfq_id=rfq_id, quote_id=quote_id, accepted_side=side,
        expected_ask_tenths=expected, accepted_ms=now_ms, dry_run=dry_run,
    )
    conn.commit()

    try:
        sent = await accept_quote(
            api, rfq_id=rfq_id, quote_id=quote_id,
            accepted_side=side, dry_run=dry_run,
        )
    except Exception as exc:  # noqa: BLE001 -- refusal or unknown, split below
        logger.error("rfq %s: accept of %s failed (%s)", rfq_id, quote_id, exc)
        store.record_accept_outcome(
            conn, rfq_id=rfq_id, quote_id=quote_id,
            outcome_status=None, outcome_ms=now_ms,
        )
        conn.commit()

        # **A venue REFUSAL and an UNKNOWN are different, and saying "go check
        # the app" about both is how a safety message stops being read.**
        #
        # Joe hit `insufficient_balance` on 2026-09-17 -- an HTTP 400 with the
        # venue's own reason -- and was told the acceptance might have gone
        # through. It could not have: a 4xx carrying a decision is the
        # exchange declining, and nothing was placed. "It may still have
        # reached Kalshi" belongs to a timeout or a dropped connection, where
        # the request really may have landed.
        refused = _venue_refusal_words(exc)
        if refused is not None:
            raise LookupRefused(400, refused) from exc

        raise LookupRefused(
            502,
            f"The acceptance could not be completed ({exc}). **It may still "
            "have reached Kalshi** -- this was not a refusal, so the request "
            "may have landed, and an RFQ acceptance carries no idempotency "
            "key, so this desk will not re-send it. Check the position in the "
            "Kalshi app before tapping anything again.",
        ) from exc

    status: Optional[str] = None
    if sent["sent"]:
        deadline = time.monotonic() + CONFIRM_WATCH_S
        while time.monotonic() < deadline:
            try:
                row = await read_quote(api, rfq_id=rfq_id, quote_id=quote_id)
            except Exception as exc:  # noqa: BLE001 -- keep watching
                logger.warning("rfq %s: status read failed (%s)", rfq_id, exc)
                await asyncio.sleep(CONFIRM_POLL_S)
                continue
            status = row.get("status") or None
            if status in QUOTE_FILLED_STATUSES or status in QUOTE_DEAD_STATUSES:
                break
            await asyncio.sleep(CONFIRM_POLL_S)

    store.record_accept_outcome(
        conn, rfq_id=rfq_id, quote_id=quote_id,
        outcome_status=status, outcome_ms=now_ms,
    )
    conn.commit()

    filled = status in QUOTE_FILLED_STATUSES

    # Only a real fill writes a position. A dry run spent nothing, so there is
    # nothing to watch, and `confirmed` is not a fill -- the first live accept
    # went `accepted` -> `confirmed` -> `cancelled` with no money moving.
    position_id: Optional[int] = None
    venue: Optional[VenueFill] = None
    if filled and not dry_run:
        # Ask the venue what it did, BEFORE the position is written, so the
        # holding is recorded at Kalshi's own size where Kalshi will say.
        # Nothing here can block the trade: `read_venue_fill` raises nothing,
        # every refusal is a named outcome on the permanent row, and a
        # position is written either way -- at the quote's numbers, with
        # `/hedge` saying which it used. Issue #74, ADR 0178.
        ask = store.rfq_row(conn, rfq_id)
        ticker = None if ask is None else ask["ticker"]
        if ticker:
            began = time.monotonic()
            venue = await read_venue_fill(
                api,
                ticker=str(ticker),
                accepted_ms=now_ms,
                quoted=_quote_size(quote),
            )
            elapsed_ms = int((time.monotonic() - began) * 1000)
            try:
                store.record_venue_fill(
                    conn, rfq_id=rfq_id, quote_id=quote_id, read_ms=now_ms,
                    outcome=venue.outcome,
                    # The delay travels with the outcome because the open
                    # question behind a `no_rows` is whether the fill had
                    # reached the endpoint yet, and a row with no elapsed
                    # time cannot distinguish "too early" from "never".
                    note=f"{venue.note or ''} elapsed={elapsed_ms}ms".strip(),
                    count=venue.count if venue.usable else None,
                    avg_price_tenths=(
                        venue.avg_price_tenths if venue.usable else None
                    ),
                )
                conn.commit()
            except sqlite3.Error:
                logger.exception(
                    "rfq %s: the venue's fill could not be recorded", rfq_id
                )
        position_id = _record_accepted_position(
            conn, rfq_id=rfq_id, quote=quote, now_ms=now_ms, venue=venue,
        )
        conn.commit()

    return {
        "status": status or "unknown",
        "filled": filled,
        "dry_run": dry_run,
        "position_id": position_id,
        "rfq_id": rfq_id,
        "quote_id": quote_id,
        "accepted_side": side,
        # What Kalshi's own record said, or None when it was never asked --
        # a dry run, or an acceptance that did not fill. Served so the screen
        # and any later audit read one answer rather than two.
        "venue_fill_outcome": None if venue is None else venue.outcome,
        "expected_ask_tenths": expected,
        "expected_ask_display": (
            None if expected is None else _cost_per_contract(expected)
        ),
        "words": _accept_words(
            status, filled=filled, dry_run=dry_run, position_id=position_id
        ),
    }


def _quote_size(quote: sqlite3.Row) -> Optional[float]:
    """The maker's quoted size, or None when it cannot be one. Never 0.

    Read by `read_venue_fill` to tell a part-fill from a full one, and by
    `_record_accepted_position` as the fallback holding. Validated rather
    than trusted for the reason the writer gives: `contracts` is a REAL
    column and a combination really is held in fractions.
    """
    value = quote["contracts"]
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    return value


def _record_accepted_position(
    conn: sqlite3.Connection,
    *,
    rfq_id: str,
    quote: sqlite3.Row,
    now_ms: int,
    venue: Optional[VenueFill] = None,
) -> Optional[int]:
    """Put a combination bought by RFQ under `/hedge`'s watch.

    **The newest armed door was the one the record could not see.** Until
    this existed, `accept_quote_for_joe` wrote `combo_rfqs` intent and
    outcome rows and nothing else: a combination bought here created no
    position, `/hedge` could not watch it, and the desk reported its own
    purchase back to Joe through `VenueCoverageBanner` as a Kalshi holding
    nobody had recorded. A bet the tool places and does not record can never
    be scored against the closing line either.

    Returns the new position's id, or **`None` when the position could not be
    built honestly** -- `None` is never an error the caller may hide: it means
    the money moved and nothing is watching it, so `_accept_words` says so on
    the screen. Nothing here raises. The trade is done and the money is spent;
    a bookkeeping failure must not turn a completed purchase into a 500 that
    tells Joe nothing happened.

    **The size is the VENUE's, whenever the venue said one** (issue #74, ADR
    0178). `read_venue_fill` has already asked `/portfolio/fills` what this
    acceptance actually did; when its answer is usable, the holding and the
    stake are built from Kalshi's own count and average price, and `/hedge`
    reports the stake as `venue_fill`.

    **The quote's own `contracts` is the FALLBACK, and it is an assertion.**
    ADR 0169 took it on the ground that a maker's quote is all-or-nothing at
    the size asked for -- stated in two modules and cited to nothing. The only
    executed accept this repo had when that was written was fired with
    `contracts = 1` on the RFQ, not against a maker's quoted size, and its
    measurement doc says in terms that it speaks to no partial fill.
    `rest_remainder: False` on create governs the requester's remainder, not
    the maker's fill. It is a REAL column and a combination really is held in
    fractions (8.22 and 60.97 contracts are two of Joe's), so it is validated
    rather than trusted: absent, non-finite or non-positive resolves to
    `None`, never to zero or to one.

    **What this still does NOT establish, when the fallback is used: that the
    stake is what Kalshi charged.** The stake written there is the accepted
    quote's ask times its size. The one executed accept this repo has
    measured filled at exactly its quoted price
    (`docs/measurements/2026-09-17-accepted-side-names-the-makers-side.md`),
    which is n = 1 and not a rule. No fee is included on either branch (ADR
    0145's `combo_entry_fee_tenths` is sunk at read time, as on the order
    path). `/hedge` resolves such a position as `as_recorded` with the reason
    `rfq_accept` when the venue was never asked and `rfq_fill_unmatched` when
    it was asked and did not answer for this combination -- and the screen
    says which. See `hedge.stake_basis_for`.
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
        else:
            note = (
                "Recorded automatically from a maker's quote you took on the "
                "Parlays screen. The stake is the price you accepted times "
                "the size quoted, before fees -- Kalshi's own record of the "
                "fill was asked for and did not answer for this combination."
            )
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
            label=(ask["card_key"] or ask["ticker"]),
            stake_tenths=stake_tenths,
            return_tenths=int(round(exact_return)),
            legs=parsed.legs,
            # Both halves of `/hedge`'s join key, from one variable, as the
            # order path does it. There is no `manual_orders` row to join TO
            # -- that is the point of the `rfq_accept` reason -- but the key
            # still says this was bought through the desk rather than typed
            # in by hand, which is the distinction issue #56 bought.
            placed_ms=now_ms,
            combo_ticker=str(ask["ticker"]),
            # No `parlay_lookup_id`: `combo_rfqs` does not carry one, and
            # re-deriving it by ticker would join whichever lookup last
            # minted that ticker, which is not necessarily the one asked.
            note=note,
        )
    except Exception:  # noqa: BLE001 -- the trade is done; bookkeeping may not raise
        logger.exception(
            "rfq %s: the position for a filled accept could not be written", rfq_id
        )
        return None


def _venue_refusal_words(exc: Exception) -> Optional[str]:
    """Plain words for an exchange that declined, or None if it never answered.

    **The distinction is the point.** A 4xx carrying a reason is the venue
    saying no, and nothing was placed; a timeout, a 5xx or a dropped socket is
    a request that may have landed. Only the second deserves "check the app",
    and spending that warning on the first teaches Joe to ignore it.

    Returns None for anything that is not an unambiguous refusal, which routes
    the caller to the cautious branch: unreadable resolves to the careful
    answer, not the convenient one.
    """
    status = getattr(exc, "status_code", None)
    if status is None or not (400 <= int(status) < 500):
        return None
    body = str(getattr(exc, "body", "") or exc)

    if "insufficient_balance" in body:
        return (
            "Kalshi refused this: not enough money on the combinations shard "
            "for the size that was quoted. **Nothing was placed and nothing "
            "was charged.** A quote is all-or-nothing at the size asked for, "
            "so either ask for a price at a smaller amount, or add funds to "
            "that shard."
        )
    if "expired" in body or "not_found" in body:
        return (
            "That quote is gone -- a maker price lives for a few seconds and "
            "this one expired before the tap landed. **Nothing was placed "
            "and nothing was charged.** Ask for a price again."
        )
    return (
        f"Kalshi refused this acceptance ({body[:180]}). **Nothing was placed "
        "and nothing was charged** -- the exchange declined rather than "
        "failing to answer."
    )


def _accept_words(
    status: Optional[str],
    *,
    filled: bool,
    dry_run: bool,
    position_id: Optional[int] = None,
) -> str:
    """What the screen says about an acceptance.

    Never claims a fill it has not seen, and never calls a maker's
    non-confirmation a failure at Joe's end.

    **A fill that produced no position says so.** `position_id is None` after
    a real fill means the money moved and `/hedge` is not watching it, which
    Joe can only act on if he is told -- silence there would read exactly like
    a bet under watch.
    """
    if dry_run:
        return (
            "Nothing was sent: the accept path is not armed yet. Everything "
            "up to the moment of spending ran, and the intent is on the "
            "record. Arming it is one line and one decision."
        )
    if filled:
        words = (
            "The maker confirmed and the trade went through. The price you "
            "accepted is the price above; what Kalshi actually charged, fees "
            "included, is on the fill and is the number to trust."
        )
        if position_id is None:
            words += (
                " **This one is not on the watch list.** The position could "
                "not be built from the record, so Parlays will not track it "
                "-- add it by hand on the hedge screen if you want it watched."
            )
        return words
    if status in QUOTE_DEAD_STATUSES:
        return (
            "The maker did not confirm, so nothing was bought and nothing is "
            "owed. That is a normal outcome -- they have about three seconds "
            "to stand behind a quote on a combination -- and not a fault at "
            "this end. Ask for a price again if you still want it."
        )
    return (
        "Your acceptance was sent and the outcome is NOT yet known -- the "
        "quote is neither confirmed nor cancelled as far as this desk can "
        "see. It will not be sent again, because an acceptance carries no "
        "idempotency key and a retry would be a second real trade. Check the "
        "Kalshi app before doing anything else."
    )
