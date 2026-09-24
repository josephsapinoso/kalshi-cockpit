"""Request-for-Quote: how a Kalshi combination is actually bought.

**The surface this repo read for its first six weeks was the wrong one.** A
KXMVE combination's public order book is empty *by design between RFQs*:
liquidity on a combo is summoned on request and prints to the book afterwards.
`lookup_combo` read `GET /markets/{t}/orderbook`, found nothing, and told Joe
"no one is offering to sell this combination" -- on a market where three makers
answered a request within 107ms. See
`docs/measurements/2026-09-17-a-combo-rfq-returns-a-real-takeable-price.md`.

The lifecycle, and which step costs money
-----------------------------------------
1. **Create** an RFQ naming the combination and a size or a target cost.
   Obligates nothing. Kalshi's docs are explicit that only acceptance binds.
2. **Makers quote**, privately. Each quote is visible only to its maker and to
   the requester, which is why no price for a combination is readable from any
   public endpoint.
3. **Accept** one quote. *This is the spend.*
4. The maker **confirms** inside a window. Combinations are High Volatility
   Markets: **3 seconds to confirm, 1 second to execute**, against 30s/15s
   elsewhere. A maker may simply not confirm, so acceptance is not a fill.

Three things measured the hard way on 2026-09-17
------------------------------------------------
- **`exchange_index=1` is required on every write.** Without it the create
  returns a Kalshi-JSON `404 not_found` -- not a CloudFront HTML 404, which is
  what a genuinely absent route gives. `rest.py:78-84` recorded this exact
  failure for a shard-1 *cancel* on 2026-08-30 and it cost that session an
  afternoon; it cost this one a wrong diagnosis ("retail keys cannot do this").
- **`market_ticker` and `rest_remainder` are required** on create, and the
  `mve_*` fields are *additional to* `market_ticker`, never instead of it. The
  API reference documents neither mve field; only the prose guide does.
- **Quotes vanish when the RFQ is deleted.** A re-read after `DELETE` returned
  zero. A quote is live state: capture it as it arrives or it is gone. Nothing
  downstream may assume a quote can be re-fetched.

What this module does NOT do
----------------------------
- **It does not accept.** Acceptance is the money call and lands with its own
  arming decision; nothing here reaches it.
- **It does not decide.** No ranking, no "best bet", no EV. It returns the
  quotes the venue returned, sorted by price because a reader needs an order,
  and says nothing about whether any of them is worth taking. `beta = -0.141`
  is why (ADR 0071 s2.5).
- **It does not promise a fill.** A quote is an offer with a 3-second
  confirmation window behind it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Optional, Sequence

from backend.core.prices import complement, dollars_to_tenths, is_valid_price
from backend.kalshi.rest import EXCHANGE_INDEX_COMBOS, KalshiRestClient

logger = logging.getLogger(__name__)

#: Every RFQ write routes to the combination shard explicitly. Never inferred
#: from the ticker -- `rest.py` says the split keeps moving and the market's
#: own `exchange_index` is the authority. Combinations have been shard 1 at
#: every reading, and a write without this returns 404 `not_found`.
_SHARD = {"exchange_index": EXCHANGE_INDEX_COMBOS}

_RFQS = "/communications/rfqs"
_QUOTES = "/communications/quotes"

#: Kalshi's cap on simultaneously open RFQs, from the API reference. Stated so
#: a caller that ever loops has a documented bound to respect rather than
#: discovering it as a 409.
MAX_OPEN_RFQS = 100

#: The maker's confirmation window on a High Volatility Market, in seconds.
#: Combinations are HVMs. Documented, not measured here -- no acceptance has
#: ever been attempted by this repo.
HVM_CONFIRM_WINDOW_S = 3.0


class RfqRefused(RuntimeError):
    """The venue would not create the RFQ, or the request was unusable.

    Carries the venue's own words where there are any. Never raised for "no
    maker answered": that is a legitimate, empty, non-error outcome.
    """


@dataclass(frozen=True)
class RfqQuote:
    """One maker's private offer on a combination.

    `yes_ask_tenths` is the number a buyer pays, and it is **derived**:
    Kalshi publishes bids, and a maker's resting NO bid *is* the YES ask,
    because a YES and a NO settle together at exactly $1.00. Same identity as
    `OrderBook.best_yes_ask`, through the same `complement`, so there is one
    implementation of the venue's most-repeated correction.
    """

    quote_id: str
    rfq_id: str
    maker_id: str
    market_ticker: str
    #: What one contract of YES costs, in integer tenths of a cent.
    #:
    #: **`None` only on a sell-side read** (`parse_quotes(keep_sell_only=
    #: True)`, #96): a maker answering a sell-side ask may bid for YES and
    #: name no NO bid at all (`no_bid_dollars: "0.0000"`), which is a quote
    #: with an exit and no entry. Captured 2026-09-24 on a held combination,
    #: 2 of 17 quotes (`tests/fixtures/combo_rfq_quotes_sell_side.json`) --
    #: and they carried the best bid on the RFQ. The buy path never passes
    #: that flag, so every quote it sees still has an int here.
    yes_ask_tenths: Optional[int]
    #: The maker's resting NO bid, the quantity actually quoted to us.
    #: `None` exactly when `yes_ask_tenths` is.
    no_bid_tenths: Optional[int]
    #: **What the maker would PAY for one YES contract -- the exit** (#76).
    #:
    #: An RFQ has no side field, so a maker answers with both of their bids
    #: and `yes_bid_dollars` is literally what they would pay Joe for the
    #: side he holds. Measured 2026-09-17: sell-side RFQs on all three
    #: combinations he holds drew bids, 16 of 44 quotes carried a YES bid on
    #: 3 of 3 positions, every one at the full size asked
    #: (`docs/measurements/2026-09-17-combinations-can-be-exited.md`). This
    #: field was DISCARDED until #76, so the exit was unreadable at every
    #: layer.
    #:
    #: **Not derived, unlike `yes_ask_tenths`.** The ask is the complement of
    #: a NO bid because a YES and a NO settle together at $1.00. This is a
    #: bid on the YES side directly, so there is no complement to take, and
    #: `yes_bid` and `complement(no_bid)` are two different numbers with the
    #: spread between them.
    #:
    #: **`None` means the maker named no YES bid, or named one this desk
    #: cannot represent.** Never zero: a maker bidding nothing and a maker
    #: not quoting a side are different facts, and zero is a settled
    #: outcome, not a price.
    yes_bid_tenths: Optional[int]
    #: Contracts the maker will do at that price, or None if unreadable.
    #: The BUY side's size (`no_contracts_fp`), and so `None` on a sell-only
    #: quote, which carries no such field.
    contracts: Optional[float]
    status: str
    created_ts: str
    #: Contracts behind the YES bid -- the EXIT's size (`yes_contracts_fp`,
    #: #96). A different wire field from `contracts`: on the 2026-09-24
    #: capture a quote carried `no_contracts_fp`, `yes_contracts_fp`, both,
    #: or only the bare `contracts_fp`, depending on which sides the maker
    #: named. `None` when the maker named no bid or the field is unreadable.
    yes_bid_contracts: Optional[float] = None


#: Why a row's price could not become a number, when it could not.
#:
#: Two refusals that look identical in a log and are **not** the same fact
#: for the reader. `UNREADABLE` means we do not know that a maker offered
#: anything. `FINER_THAN_TENTHS` means a maker offered a real, tradeable
#: price and this desk cannot represent it -- which is actionable, because he
#: can go and read it in the Kalshi app. Collapsing the second into "nobody
#: quoted" is issue #73.
REFUSED_UNREADABLE = "unreadable"
REFUSED_FINER_THAN_TENTHS = "finer_than_tenths"


def _read_tenths(dollars: Any) -> tuple[Optional[int], Optional[str]]:
    """Dollars to tenths of a cent, refusing anything that would round.

    Returns `(tenths, None)` on success and `(None, reason)` on a refusal,
    where `reason` is one of the two constants above. Exactly one member is
    not None.

    `dollars_to_tenths` rounds half-up, which is right for a snapshot loop and
    wrong here. A combination market carries
    `price_level_structure: center_deci_edge_centi_cent` -- **hundredths** of a
    cent below 1c and above 99c -- so a real quote at `"0.0055"` is a price
    this project's integer-tenths convention cannot represent. Rounding it to
    6 tenths would invent a price the venue never offered, on the money path.

    Unreadable resolves to None and the caller drops the quote with a log,
    never to a rounded stand-in. Clamp what you trust; refuse what you are
    validating.

    **The reason is returned rather than only logged** because the caller
    needs to tell the reader which of the two happened. It used to be logged
    and nowhere else, so every refusal rendered as "nobody quoted".
    """
    tenths = dollars_to_tenths(dollars)
    if tenths is None:
        return None, REFUSED_UNREADABLE
    try:
        exact = Decimal(str(dollars)) * 1000
    except (InvalidOperation, ValueError):
        return None, REFUSED_UNREADABLE
    if exact != Decimal(tenths):
        logger.warning(
            "rfq: refusing quote price %r -- finer than tenths of a cent "
            "(this market ticks in centi-cents at the edges)", dollars,
        )
        return None, REFUSED_FINER_THAN_TENTHS
    return tenths, None


def _exact_tenths(dollars: Any) -> Optional[int]:
    """`_read_tenths`'s price alone, for callers that do not classify."""
    return _read_tenths(dollars)[0]


@dataclass(frozen=True)
class QuoteRead:
    """One read of the quotes answering an RFQ, and what it had to refuse.

    **The refusals carry quote ids, not counts**, and that is the whole
    design. `await_quotes` polls the same RFQ every few seconds, so a quote
    refused on one pass is refused on every pass: a count would multiply by
    the number of polls and tell the reader six makers answered when one did.
    A set of ids is the number of distinct quotes however often it is read.

    Same correction as ADR 0169's `record_quotes` fix, for the same reason --
    an id the venue assigns is the only thing that makes "seen twice" one
    thing. That fix learned it the expensive way; this one inherits it.
    """

    quotes: tuple[RfqQuote, ...]
    #: Ids of quotes whose price was real and finer than a tenth of a cent.
    #: A maker DID quote; this desk cannot say what. Actionable (#73).
    refused_finer_than_tenths: frozenset[str] = frozenset()
    #: Ids of quotes dropped for any other reason -- unparseable, or a price
    #: that is a settled outcome rather than an offer. Not actionable.
    refused_unreadable: frozenset[str] = frozenset()
    #: Ids of quotes whose YES BID -- the exit -- was a real price finer than
    #: a tenth of a cent (#96 defect 5). The SELL side's own refusal, kept
    #: apart from `refused_finer_than_tenths` (the buy side's) because they
    #: drive different sentences: this one says a maker offered to buy the
    #: position back at a price this screen cannot print. Recorded on every
    #: read, buy or sell; only the sell-side reader says anything about it.
    refused_bid_finer_than_tenths: frozenset[str] = frozenset()


def parse_quotes(
    payload: dict,
    *,
    rfq_id: Optional[str] = None,
    keep_sell_only: bool = False,
) -> QuoteRead:
    """Wire payload -> quotes, cheapest YES ask first, plus the refusals.

    Filters to `rfq_id` when given, because `rfq_user_filter=self` returns
    quotes on *every* RFQ we have open, not just the one being awaited.

    A row that cannot be read is **dropped with a warning, not defaulted**: a
    quote with an unparseable price is not a quote at zero. It is also
    **counted**, by id and by reason, because a drop the reader never hears
    about renders as "nobody quoted".

    **`keep_sell_only`** is the sell-side read (#96). A maker answering an
    ask about a combination Joe HOLDS may bid for YES and name no NO bid --
    `no_bid_dollars: "0.0000"` -- and the buy-side rule drops such a quote
    whole, because it offers nothing to buy. On the 2026-09-24 capture that
    rule discarded the best exit on the RFQ. With the flag, a quote whose
    buy side is unusable but whose YES bid is a real price is KEPT, with
    `yes_ask_tenths = no_bid_tenths = None`, and the list is ordered best
    bid first. The buy path never passes it, and on its reads this function
    behaves exactly as it did.
    """
    out: list[RfqQuote] = []
    too_fine: set[str] = set()
    unreadable: set[str] = set()
    bid_too_fine: set[str] = set()
    for row in payload.get("quotes") or ():
        if rfq_id is not None and row.get("rfq_id") != rfq_id:
            continue
        row_id = str(row.get("id") or "")
        # **The sell side, kept rather than discarded** (#76). Absent on many
        # quotes, so its refusal reason is deliberately NOT counted into
        # `too_fine`: that count drives a sentence about whether the desk
        # could show Joe a price to BUY, and a maker declining to bid on the
        # side he does not hold is not a failure to price the one he does.
        # It goes into its own set instead (#96 defect 5): a real exit price
        # too fine to print is a named refusal, never a silent None.
        # `None` is the honest value; it never becomes zero.
        yes_bid, bid_reason = _read_tenths(row.get("yes_bid_dollars"))
        if bid_reason == REFUSED_FINER_THAN_TENTHS:
            bid_too_fine.add(row_id)
        no_bid, reason = _read_tenths(row.get("no_bid_dollars"))
        ask: Optional[int] = None
        buy_side_usable = False
        if no_bid is None:
            buy_refusal = too_fine if reason == REFUSED_FINER_THAN_TENTHS else unreadable
        else:
            ask = complement(no_bid)
            # 0 and 1000 are settled outcomes, not quotes. A maker bidding
            # $0.00 on NO is not offering YES at $1.00; it is not offering
            # anything. Not `refused_finer_than_tenths` either: telling the
            # reader to go and look for it in the app would be wrong.
            buy_side_usable = is_valid_price(ask) and is_valid_price(no_bid)
            buy_refusal = unreadable
        if not buy_side_usable:
            sell_side_usable = yes_bid is not None and is_valid_price(yes_bid)
            if not (keep_sell_only and sell_side_usable):
                logger.warning(
                    "rfq: dropping quote %s -- no_bid %s gives an untradeable ask",
                    row.get("id"), row.get("no_bid_dollars"),
                )
                buy_refusal.add(row_id)
                continue
            # A sell-only quote: an exit with no entry. Both buy-side
            # numbers are None, never a stand-in.
            ask = None
            no_bid = None
        try:
            contracts = float(row["no_contracts_fp"])
        except (KeyError, TypeError, ValueError):
            contracts = None
        try:
            yes_bid_contracts: Optional[float] = float(row["yes_contracts_fp"])
        except (KeyError, TypeError, ValueError):
            yes_bid_contracts = None
        if yes_bid is not None and not is_valid_price(yes_bid):
            # 0 and 1000 again: a maker "bidding" a settled outcome is not
            # offering to buy. Dropped to None, and the QUOTE survives --
            # this side is extra information, never the reason to lose a
            # price Joe can act on.
            logger.warning(
                "rfq: quote %s has an untradeable yes_bid %s; keeping the "
                "quote without a sell side", row.get("id"),
                row.get("yes_bid_dollars"),
            )
            yes_bid = None
        if yes_bid is None:
            yes_bid_contracts = None
        out.append(
            RfqQuote(
                quote_id=str(row.get("id") or ""),
                rfq_id=str(row.get("rfq_id") or ""),
                maker_id=str(row.get("creator_id") or ""),
                market_ticker=str(row.get("market_ticker") or ""),
                yes_ask_tenths=ask,
                no_bid_tenths=no_bid,
                yes_bid_tenths=yes_bid,
                contracts=contracts,
                status=str(row.get("status") or ""),
                created_ts=str(row.get("created_ts") or ""),
                yes_bid_contracts=yes_bid_contracts,
            )
        )
    # Cheapest first. An ORDER, not a recommendation: the makers on the one
    # RFQ this repo has fired were 3.80 cents apart, so which row a reader
    # sees first is worth real money, while nothing here says to take it.
    # On a sell-side read, best BID first, for the same reason from the
    # other side; a quote with no bid sorts after every quote with one.
    if keep_sell_only:
        out.sort(key=lambda q: (q.yes_bid_tenths is None, -(q.yes_bid_tenths or 0)))
    else:
        out.sort(key=lambda q: q.yes_ask_tenths)
    return QuoteRead(
        quotes=tuple(out),
        refused_finer_than_tenths=frozenset(too_fine),
        refused_unreadable=frozenset(unreadable),
        refused_bid_finer_than_tenths=frozenset(bid_too_fine),
    )


async def open_rfq_for(
    api: KalshiRestClient, market_ticker: str
) -> Optional[dict]:
    """Our own still-open RFQ row on this market, if there is one.

    **Needed because this desk holds RFQs open across the second tap.** Kalshi
    allows one live RFQ per market per requester and answers a second create
    with `409 already_exists`, so asking twice about the same combination --
    exactly what a reader does when the first answer scrolls off -- fails
    unless the existing request is found.

    Returns the whole row, not just the id, because the caller has to see the
    size it was created at. An RFQ asked at a target the account can no
    longer pay is not reusable: its quotes are for a size that will be
    refused.

    `None` when nothing is open, which sends the caller back to creating one.
    """
    try:
        payload = await api.request(
            "GET", _RFQS,
            params={"market_ticker": market_ticker, "limit": 100},
        )
    except Exception as exc:  # noqa: BLE001 -- recovery path, not the answer
        logger.warning("rfq: could not list RFQs on %s (%s)", market_ticker, exc)
        return None
    for row in payload.get("rfqs") or ():
        if row.get("market_ticker") != market_ticker:
            continue
        if row.get("status") == "open" and row.get("id"):
            return row
    return None


def _is_reusable(existing: dict, wanted_target: Optional[str]) -> bool:
    """Whether an open RFQ can stand in for the one we were about to create.

    **It cannot if it was asked at a bigger size than we can now pay.** Joe's
    balance fell during a session and three RFQs created at the old flat
    $5.00 target stayed open, quoting 173 contracts against $3.94 -- reusing
    one hands back a price that is guaranteed to be refused on accept, which
    is worse than the 409 it was fixed to avoid.

    Reuse is still the default when the sizes are compatible, because
    replacing means deleting, and deleting destroys quotes that may be on
    screen with a confirm pending.

    An unreadable target resolves to **not reusable**: a fresh RFQ costs one
    call, and a stale one costs a refused trade.

    **Only a dollar-target ask reaches this** (#96 defect 4). It used to
    answer `True` for `wanted_target is None` -- three lines under the rule
    above -- so a `contracts=` ask would silently reuse whatever RFQ was open,
    priced for a different size. `create_rfq` now refuses a size-based ask
    that meets `already_exists` before it gets here, and this answers False
    for None rather than restating a case it no longer sees.
    """
    if wanted_target is None:
        return False
    try:
        return float(existing.get("target_cost_dollars") or 0) <= float(wanted_target)
    except (TypeError, ValueError):
        return False


@dataclass(frozen=True)
class RfqHandle:
    """An RFQ we can read quotes from, and the target it ACTUALLY holds.

    **The target is the whole reason this is not just an id** (#72).
    `create_rfq` reuses an open RFQ whenever its target is at least the
    one wanted, and this desk holds RFQs open so a second tap can accept
    a quote. So Joe asks at $1.00, asks again at $5.00, and the second
    ask silently returns the $1.00 request -- with quotes sized for
    $1.00. Returning the id alone left the caller reporting the number he
    typed, which the venue had never been asked at.

    `target_cost_dollars` is what the VENUE holds, verbatim, or `None`
    for a `contracts=` ask, which carries no dollar target at all.
    Never the requested figure standing in for it: a field that reports
    the request when it cannot read the truth is the defect, not the fix.
    """

    rfq_id: str
    #: What the venue was asked for, as the venue states it. `None` when
    #: unknown or not applicable -- never a guess.
    target_cost_dollars: Optional[str]
    #: True when this is an RFQ that already existed. The quotes behind
    #: it were priced for ITS target, not necessarily for this ask.
    reused: bool = False


async def create_rfq(
    api: KalshiRestClient,
    *,
    market_ticker: str,
    collection_ticker: str,
    legs: Sequence[dict],
    target_cost_dollars: Optional[str] = None,
    contracts: Optional[int] = None,
    contracts_fp: Optional[str] = None,
) -> RfqHandle:
    """Ask the market to price a combination.

    Returns an `RfqHandle`: the id, **and the target the venue actually
    holds**, which is not always the one asked for (see `RfqHandle`).

    **This obligates nothing.** Only accepting a quote binds the requester;
    Kalshi's docs are explicit and this repo has exercised create-and-delete
    without money moving.

    Exactly one of `target_cost_dollars`, `contracts` or `contracts_fp` --
    the venue accepts each, and refusing two here turns an ambiguous request
    into a clear error rather than letting the venue pick.

    `contracts_fp` is the fixed-point STRING form (`"2.01"`), the size a
    sell-side ask needs because holdings are fractional (#96 defect 1).
    Measured 2026-09-24: the venue took `contracts_fp: "2.01"` on create,
    held `contracts_fp: "2.01"` on the row, and all 18 makers quoted 2.01.

    **A size-based ask that meets `already_exists` is REFUSED, never reused**
    (#96 defect 4). The 409 means one of ours is open on this market, and it
    was asked at some other size -- or is a buy-side ask a Take-it tap may be
    holding open -- so reusing it returns quotes priced for another request,
    and deleting it could destroy a quote on screen. The refusal says so.
    """
    sizes = [x for x in (target_cost_dollars, contracts, contracts_fp) if x is not None]
    if len(sizes) != 1:
        raise RfqRefused(
            "name exactly one of target_cost_dollars, contracts or "
            f"contracts_fp; got {target_cost_dollars!r}, {contracts!r} and "
            f"{contracts_fp!r}"
        )
    if not legs:
        raise RfqRefused("an RFQ needs at least one leg")

    body: dict[str, Any] = {
        # Required, and omitting it was the first wrong diagnosis on
        # 2026-09-17: the 404 read as "retail keys cannot do this".
        "market_ticker": market_ticker,
        # Required. False: we are asking for a price, not leaving a resting
        # order behind. Joe pays the ask and does not make offers (ADR 0115),
        # so resting a remainder would reintroduce exactly what he removed.
        "rest_remainder": False,
        "mve_collection_ticker": collection_ticker,
        "mve_selected_legs": list(legs),
    }
    if target_cost_dollars is not None:
        body["target_cost_dollars"] = target_cost_dollars
    elif contracts_fp is not None:
        body["contracts_fp"] = contracts_fp
    else:
        body["contracts"] = contracts

    try:
        created = await api.request("POST", _RFQS, params=_SHARD, json_body=body)
    except Exception as exc:  # noqa: BLE001 -- one recoverable case, then raise
        # **`already_exists` is not a failure, it is our own open request.**
        # Kalshi allows one live RFQ per market per requester, and this desk
        # holds them open so a second tap can accept a quote. So a repeat ask
        # on the same combination lands here, and the right answer is to hand
        # back the RFQ that already exists rather than to refuse -- or to
        # delete it, which would destroy the quotes it is holding.
        already_exists = "already_exists" in str(getattr(exc, "body", "") or exc)
        if already_exists and target_cost_dollars is None:
            # A size-based ask (#96 defect 4): see the docstring. Neither
            # reused nor deleted -- the open one is not this ask's.
            raise RfqRefused(
                "an RFQ of ours is already open on this combination "
                "(already_exists) -- asked at another size, or held open by a "
                "buy-side ask. It was neither reused nor withdrawn; asking "
                "again once it closes is free."
            ) from exc
        if already_exists:
            existing = await open_rfq_for(api, market_ticker)
            if existing is not None:
                if _is_reusable(existing, target_cost_dollars):
                    logger.info(
                        "rfq: reusing our open RFQ %s on %s (its target "
                        "%s, asked for %s)",
                        existing.get("id"), market_ticker,
                        existing.get("target_cost_dollars"),
                        target_cost_dollars,
                    )
                    # **The venue's own figure, not the one we asked
                    # for.** These differ exactly when the reuse was at a
                    # SMALLER target, which is the case #72 exists for:
                    # the quotes behind this id are sized for the number
                    # below, and a screen reporting the requested one
                    # tells Joe he is about to spend what he typed.
                    held = existing.get("target_cost_dollars")
                    return RfqHandle(
                        rfq_id=str(existing["id"]),
                        target_cost_dollars=(
                            str(held) if held is not None else None
                        ),
                        reused=True,
                    )
                # Too big to pay for. Withdraw it and ask again at the size
                # we can afford -- its quotes are worthless either way,
                # because accepting one of them would be refused.
                logger.info(
                    "rfq: replacing open RFQ %s on %s (asked at %s, we can "
                    "pay %s)",
                    existing.get("id"), market_ticker,
                    existing.get("target_cost_dollars"), target_cost_dollars,
                )
                await delete_rfq(api, str(existing["id"]))
                try:
                    created = await api.request(
                        "POST", _RFQS, params=_SHARD, json_body=body
                    )
                except Exception as retry_exc:  # noqa: BLE001
                    raise RfqRefused(
                        f"Kalshi would not create the RFQ after withdrawing "
                        f"an oversized one: {retry_exc}"
                    ) from retry_exc
                rfq = (created.get("rfq") if isinstance(created.get("rfq"), dict)
                       else created)
                new_id = rfq.get("id") or created.get("id")
                if not new_id:
                    raise RfqRefused(f"Kalshi returned no RFQ id: {created!r}")
                # Freshly created at OUR target, so the two agree here.
                return RfqHandle(
                    rfq_id=str(new_id),
                    target_cost_dollars=target_cost_dollars,
                )
        raise RfqRefused(f"Kalshi would not create the RFQ: {exc}") from exc

    rfq = created.get("rfq") if isinstance(created.get("rfq"), dict) else created
    rfq_id = rfq.get("id") or created.get("id")
    if not rfq_id:
        raise RfqRefused(f"Kalshi returned no RFQ id: {created!r}")
    return RfqHandle(
        rfq_id=str(rfq_id), target_cost_dollars=target_cost_dollars
    )


async def read_quotes(
    api: KalshiRestClient, rfq_id: str, *, keep_sell_only: bool = False
) -> QuoteRead:
    """Quotes answering *our* RFQ, cheapest first, with the refusals beside them.

    `rfq_user_filter=self` is the documented way and needs no user id. The
    older `rfq_creator_user_id` is deprecated, and `communications_id` is not
    the user id -- passing it gets a 403 that reads like a permissions problem
    and is not one.

    `keep_sell_only` is passed through to `parse_quotes`; only the exit ask
    (#96) sets it.
    """
    payload = await api.request(
        "GET", _QUOTES, params={"rfq_user_filter": "self", "limit": 500}
    )
    return parse_quotes(payload, rfq_id=rfq_id, keep_sell_only=keep_sell_only)


# ---------------------------------------------------------------------------
# Sizing and describing a sell-side ask (#96). Pure; shared by the exit route
# and `scripts/capture_sell_side_rfq.py`.
# ---------------------------------------------------------------------------


def held_position_fp(rows: Sequence[dict], ticker: str) -> Optional[str]:
    """The `position_fp` string for `ticker` among `/portfolio/positions` rows.

    `None` when the ticker is not there -- which, on a combination, is also
    what a venue-settled position looks like (it leaves the positions read
    before its legs settle; `tasks/lessons.md` 2026-09-22). The caller
    refuses; it never substitutes a recorded size.
    """
    for row in rows:
        if row.get("ticker") == ticker or row.get("market_ticker") == ticker:
            fp = row.get("position_fp")
            return None if fp is None else str(fp)
    return None


def floor_contracts_fp(position_fp: Any) -> Optional[str]:
    """A fixed-point holding (`'8.226'`) floored to the venue's 0.01 grid.

    **Floored, never rounded** (#96 defect 1): `'8.226'` asks for `'8.22'`,
    never `'8.23'` -- asking makers to buy more than is held. Returns the
    string the venue takes as `contracts_fp`, or `None` when the holding is
    unreadable, negative (a NO holding, which this ask does not describe) or
    under one hundredth of a contract. Never `'0.00'`.
    """
    try:
        value = Decimal(str(position_fp))
    except (InvalidOperation, ValueError):
        return None
    if not value.is_finite() or value < 0:
        return None
    floored = (value * 100).to_integral_value(rounding="ROUND_FLOOR") / 100
    if floored <= 0:
        return None
    return f"{floored:.2f}"


def mve_legs(market_payload: dict) -> tuple[str, list[dict]]:
    """`(mve_collection_ticker, mve_selected_legs)` off `GET /markets/{ticker}`.

    Read from the VENUE's own market, never from a request or a stored card:
    a held combination may have been bought through a tap that recorded no
    lookup, and the market row is the authority on what it is made of. The
    envelope is `{"market": {...}}`; the bare shape is accepted too. Missing
    either field refuses -- an RFQ without the legs the venue expects is a
    4xx dressed as ours.
    """
    market = (
        market_payload.get("market")
        if isinstance(market_payload.get("market"), dict)
        else market_payload
    )
    collection = market.get("mve_collection_ticker")
    legs = market.get("mve_selected_legs")
    if not collection or not isinstance(legs, list) or not legs:
        raise RfqRefused(
            "the market carries no mve_collection_ticker / mve_selected_legs; "
            f"keys: {sorted(market)}"
        )
    return str(collection), [dict(leg) for leg in legs]


async def delete_rfq(api: KalshiRestClient, rfq_id: str) -> None:
    """Withdraw an RFQ. Best-effort: a failure here is logged, never raised.

    The caller is typically in a `finally` after showing a price, and an
    undeleted RFQ closes on its own. Raising would turn a tidy-up failure into
    a failed price lookup, which is the wrong trade.

    **Deleting discards the quotes**: they disappear from
    `rfq_user_filter=self` immediately. Never delete before capturing.
    """
    try:
        await api.request("DELETE", f"{_RFQS}/{rfq_id}", params=_SHARD)
    except Exception as exc:  # noqa: BLE001 -- tidy-up, not the caller's problem
        logger.warning("rfq: could not delete %s (%s); it will close on its own",
                       rfq_id, exc)


# ---------------------------------------------------------------------------
# Accepting a quote. THIS IS THE SPEND.
# ---------------------------------------------------------------------------
#
# Everything above asks. This section commits money, and it carries one
# unresolved question that is worth more than the rest of the file.

#: **Which side to name when Joe is BUYING the YES side of a combination.**
#:
#: A quote carries both a `yes_bid_dollars` and a `no_bid_dollars` -- what the
#: maker would pay for each side. `accepted_side` says which of the maker's
#: bids you are lifting, so **buying YES means accepting the maker's NO bid**,
#: which is the derived-ask identity this repo uses everywhere else:
#: `yes_ask = complement(no_bid)`.
#:
#: **DOCUMENTED for FIX, INFERRED for REST, and the inference is expensive if
#: it is wrong.** Kalshi's FIX page states it outright -- "For AcceptQuote,
#: BUY accepts the maker's NO quote and SELL accepts the maker's YES quote" --
#: but the REST reference defines `accepted_side` only as "the side that was
#: accepted (yes or no)", which does not say whose side. On the quote captured
#: 2026-09-17 (`no_bid 0.8920`, `yes_bid 0.0760`) the two readings are buying
#: YES at 10.8c versus buying NO at 92.4c: **roughly nine times the intended
#: spend, on the wrong contract.**
#:
#: So this constant is not used by anything that sizes a bet until one real,
#: minimum-size accept has been read back out of `GET /portfolio/fills` and
#: the side and price confirmed. `accept_quote` refuses to run unarmed, and
#: the arming decision names this measurement as its precondition.
ACCEPT_SIDE_FOR_BUYING_YES = "no"
ACCEPT_SIDE_FOR_BUYING_NO = "yes"

#: Quote lifecycle, complete, from the venue's reference.
#:
#: `accepted` is NOT a fill: the maker still has to confirm, and on a
#: combination (a High Volatility Market) the window is **3 seconds**, against
#: 30 elsewhere. `confirmed` and then `executed` are the states that mean
#: money moved. A 204 on the accept call means "your acceptance was received",
#: nothing more, and treating it as a fill is the single most dangerous
#: misreading available on this path.
QUOTE_STATUS_OPEN = "open"
QUOTE_STATUS_ACCEPTED = "accepted"
QUOTE_STATUS_CONFIRMED = "confirmed"
QUOTE_STATUS_EXECUTED = "executed"
QUOTE_STATUS_CANCELLED = "cancelled"

#: The states in which money has definitely moved.
#:
#: **`confirmed` is NOT one of them, and this constant said it was until the
#: first live probe on 2026-09-17.** That probe watched a quote go
#: `accepted` -> `confirmed` in 32ms and then `cancelled` 1.7 seconds later,
#: with no fill, no position change and no balance change:
#:
#:     accepted_ts  17:50:29.539
#:     confirmed_ts 17:50:29.571
#:     cancelled_ts 17:50:31.250   status: cancelled
#:
#: A confirmation is the maker agreeing; **execution is a separate step with
#: its own timer** (1 second on a High Volatility Market) and it can fail to
#: happen after a confirmation. Treating `confirmed` as a fill would have
#: told Joe "the trade went through" about a trade that did not.
#:
#: The lesson is the one this repo keeps relearning: a state that *sounds*
#: final is not evidence of the thing it sounds like. Only `executed` is.
QUOTE_FILLED_STATUSES = (QUOTE_STATUS_EXECUTED,)

#: The states in which it definitely has not.
QUOTE_DEAD_STATUSES = (QUOTE_STATUS_CANCELLED,)


class QuoteAcceptRefused(RuntimeError):
    """The acceptance was not sent, or the venue would not take it.

    **Never raised once an accept has reached the venue.** A request that was
    sent and whose response was lost is an UNKNOWN, not a refusal, and the
    caller must go and read the quote's status rather than retry: the RFQ path
    has no client-generated idempotency key (Kalshi assigns
    `client_order_id` after the fact), so a retry is a second real order.
    """


async def accept_quote(
    api: KalshiRestClient,
    *,
    rfq_id: str,
    quote_id: str,
    accepted_side: str,
    dry_run: bool,
) -> dict:
    """Lift one maker's bid. **Spends real money when `dry_run` is False.**

    Returns `{"sent": bool, "accepted_side": str}`. There is no fill in the
    response and there cannot be: the venue answers **204 No Content**, and
    the maker's confirmation happens afterwards. Read the quote's status to
    learn what became of it.

    `dry_run` is passed explicitly rather than read from config here, so that
    every caller has to state which it means and no default can arm this by
    omission.
    """
    if accepted_side not in ("yes", "no"):
        raise QuoteAcceptRefused(
            f"accepted_side must be 'yes' or 'no', got {accepted_side!r}"
        )
    if dry_run:
        logger.info(
            "rfq: DRY RUN, not accepting quote %s on rfq %s (side %s)",
            quote_id, rfq_id, accepted_side,
        )
        return {"sent": False, "accepted_side": accepted_side}

    # The nested form. The flat `PUT /communications/quotes/{id}/accept` still
    # works and is marked deprecated, with worse rate limits.
    path = f"{_RFQS}/{rfq_id}/quotes/{quote_id}/accept"
    # `exchange_index` is INFERRED here, not documented -- the accept spec
    # lists no such parameter. But it lists none on create or delete either,
    # and both measurably require it. Query params are not signed
    # (`SIGN_QUERY_STRING = False`), so adding it cannot break the signature,
    # and the failure it prevents is a 404 on a trade Joe is waiting for.
    await api.request("PUT", path, params=_SHARD, json_body={
        "accepted_side": accepted_side,
    })
    return {"sent": True, "accepted_side": accepted_side}


async def read_quote(api: KalshiRestClient, *, rfq_id: str, quote_id: str) -> dict:
    """One quote's current row, or `{}` if the venue no longer lists it.

    The only way to learn whether a maker confirmed: there is no
    `quote_confirmed` WebSocket event, so the confirmed state is visible
    solely as REST `status` / `confirmed_ts`.

    An empty dict is deliberately not an error. A quote that has vanished is
    a real outcome and the caller decides what it means; the one thing this
    must never do is invent a status.
    """
    payload = await api.request(
        "GET", _QUOTES,
        params={"rfq_user_filter": "self", "rfq_id": rfq_id, "limit": 500},
    )
    for row in payload.get("quotes") or ():
        if row.get("id") == quote_id:
            return row
    return {}
