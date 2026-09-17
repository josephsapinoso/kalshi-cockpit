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
    yes_ask_tenths: int
    #: The maker's resting NO bid, the quantity actually quoted to us.
    no_bid_tenths: int
    #: Contracts the maker will do at that price, or None if unreadable.
    contracts: Optional[float]
    status: str
    created_ts: str


def _exact_tenths(dollars: Any) -> Optional[int]:
    """Dollars to tenths of a cent, refusing anything that would round.

    `dollars_to_tenths` rounds half-up, which is right for a snapshot loop and
    wrong here. A combination market carries
    `price_level_structure: center_deci_edge_centi_cent` -- **hundredths** of a
    cent below 1c and above 99c -- so a real quote at `"0.0055"` is a price
    this project's integer-tenths convention cannot represent. Rounding it to
    6 tenths would invent a price the venue never offered, on the money path.

    Unreadable resolves to None and the caller drops the quote with a log,
    never to a rounded stand-in. Clamp what you trust; refuse what you are
    validating.
    """
    tenths = dollars_to_tenths(dollars)
    if tenths is None:
        return None
    try:
        exact = Decimal(str(dollars)) * 1000
    except (InvalidOperation, ValueError):
        return None
    if exact != Decimal(tenths):
        logger.warning(
            "rfq: refusing quote price %r -- finer than tenths of a cent "
            "(this market ticks in centi-cents at the edges)", dollars,
        )
        return None
    return tenths


def parse_quotes(payload: dict, *, rfq_id: Optional[str] = None) -> tuple[RfqQuote, ...]:
    """Wire payload -> quotes, cheapest YES ask first.

    Filters to `rfq_id` when given, because `rfq_user_filter=self` returns
    quotes on *every* RFQ we have open, not just the one being awaited.

    A row that cannot be read is **dropped with a warning, not defaulted**: a
    quote with an unparseable price is not a quote at zero.
    """
    out: list[RfqQuote] = []
    for row in payload.get("quotes") or ():
        if rfq_id is not None and row.get("rfq_id") != rfq_id:
            continue
        no_bid = _exact_tenths(row.get("no_bid_dollars"))
        if no_bid is None:
            continue
        ask = complement(no_bid)
        # 0 and 1000 are settled outcomes, not quotes. A maker bidding $0.00 on
        # NO is not offering YES at $1.00; it is not offering anything.
        if not is_valid_price(ask) or not is_valid_price(no_bid):
            logger.warning(
                "rfq: dropping quote %s -- no_bid %s gives an untradeable ask",
                row.get("id"), row.get("no_bid_dollars"),
            )
            continue
        try:
            contracts = float(row["no_contracts_fp"])
        except (KeyError, TypeError, ValueError):
            contracts = None
        out.append(
            RfqQuote(
                quote_id=str(row.get("id") or ""),
                rfq_id=str(row.get("rfq_id") or ""),
                maker_id=str(row.get("creator_id") or ""),
                market_ticker=str(row.get("market_ticker") or ""),
                yes_ask_tenths=ask,
                no_bid_tenths=no_bid,
                contracts=contracts,
                status=str(row.get("status") or ""),
                created_ts=str(row.get("created_ts") or ""),
            )
        )
    # Cheapest first. An ORDER, not a recommendation: the makers on the one
    # RFQ this repo has fired were 3.80 cents apart, so which row a reader
    # sees first is worth real money, while nothing here says to take it.
    out.sort(key=lambda q: q.yes_ask_tenths)
    return tuple(out)


async def create_rfq(
    api: KalshiRestClient,
    *,
    market_ticker: str,
    collection_ticker: str,
    legs: Sequence[dict],
    target_cost_dollars: Optional[str] = None,
    contracts: Optional[int] = None,
) -> str:
    """Ask the market to price a combination. Returns the RFQ id.

    **This obligates nothing.** Only accepting a quote binds the requester;
    Kalshi's docs are explicit and this repo has exercised create-and-delete
    without money moving.

    Exactly one of `target_cost_dollars` or `contracts` -- the venue accepts
    either, and refusing both here turns an ambiguous request into a clear
    error rather than letting the venue pick.
    """
    if (target_cost_dollars is None) == (contracts is None):
        raise RfqRefused(
            "name exactly one of target_cost_dollars or contracts; "
            f"got {target_cost_dollars!r} and {contracts!r}"
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
    else:
        body["contracts"] = contracts

    try:
        created = await api.request("POST", _RFQS, params=_SHARD, json_body=body)
    except Exception as exc:  # noqa: BLE001 -- re-raised with the venue's words
        raise RfqRefused(f"Kalshi would not create the RFQ: {exc}") from exc

    rfq = created.get("rfq") if isinstance(created.get("rfq"), dict) else created
    rfq_id = rfq.get("id") or created.get("id")
    if not rfq_id:
        raise RfqRefused(f"Kalshi returned no RFQ id: {created!r}")
    return str(rfq_id)


async def read_quotes(api: KalshiRestClient, rfq_id: str) -> tuple[RfqQuote, ...]:
    """Quotes answering *our* RFQ, cheapest first.

    `rfq_user_filter=self` is the documented way and needs no user id. The
    older `rfq_creator_user_id` is deprecated, and `communications_id` is not
    the user id -- passing it gets a 403 that reads like a permissions problem
    and is not one.
    """
    payload = await api.request(
        "GET", _QUOTES, params={"rfq_user_filter": "self", "limit": 500}
    )
    return parse_quotes(payload, rfq_id=rfq_id)


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
