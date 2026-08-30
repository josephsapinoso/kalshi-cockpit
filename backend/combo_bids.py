"""Place a resting bid on a card's combination, at a price Joe chooses.

ADR 0084. The one control on the parlay desk that commits money to a
combination, and the reason it has to be a RESTING bid rather than a buy:
a combination book carries no resting YES bid on 40 of 40 books this repo has
read (ADR 0012 section 5), so there is nothing to buy from. The desk places a
limit BUY that waits for a seller instead of taking one that is already there.

**Built on the lookup path rather than beside it.** The route prices the card
first -- the same `price_card_on_kalshi` the "Price on Kalshi" button calls --
which re-checks every leg server-side, chooses the collection, mints or finds
the market, verifies the venue's leg echo, and writes the `parlay_lookups` row.
Only then does this place a bid on the ticker that came back. Duplicating any
of that would be a second definition of "which market is this card", and the
first thing to drift would be the one that spends money.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **That the bid will fill.** The same emptiness that makes a resting bid
  necessary makes it unlikely to be taken. Nothing here promises a fill and the
  screen must not either.
- **What a fill would cost.** ADR 0046 leaves the combination fee model
  unverified, and Kalshi's 2026-08-22 changelog puts the combo maker multiplier
  at 0.5 against `core/fees.py`'s 0.25. Unreconciled, so no net figure is
  computed anywhere in this module.
- **That the price is good.** It is Joe's number. The card's fair value sits
  beside it and nothing ranks by the gap (ADR 0071 section 2.5).
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional, Sequence

from .kalshi.grid import parse_price_grid
from .kalshi.orders import OrderRequest
from .kalshi.rest import EXCHANGE_INDEX_COMBOS
from .parlays import LookupRefused, price_card_on_kalshi
from .store import combo_orders as store_bids
from .store.combo_orders import (
    ComboOrderRefused,
    check_affordable,
    contracts_for_stake,
    read_shard_funds,
    record_intent,
    record_outcome,
    status_from_response,
)

logger = logging.getLogger(__name__)


async def place_resting_bid(
    conn,
    *,
    card_key: str,
    requested_legs: Sequence[tuple[str, str]],
    price_tenths: int,
    stake_tenths: int,
    now_ms: int,
    max_odds_age_ms: int,
    api,
) -> dict:
    """Price the card, then rest a bid on its combination at Joe's price.

    Order of operations is the safety property. The venue is touched three
    times before anything is committed -- price the card (which mints), read
    the market for its grid and shard, read the balance ON that shard -- and
    every refusal that can be reached is reached before the order request is
    built.
    """
    priced = await price_card_on_kalshi(
        conn,
        card_key=card_key,
        stake_cents=max(1, stake_tenths // 10),
        requested_legs=requested_legs,
        now_ms=now_ms,
        max_odds_age_ms=max_odds_age_ms,
        api=api,
    )
    ticker = priced.get("minted_market_ticker")
    if not ticker:
        # `no_collection` and `legs_not_combinable` never mint a market, so
        # there is nothing to rest a bid on. The lookup's own words are better
        # than anything this layer could invent, so they are passed through.
        raise ComboOrderRefused(
            422,
            priced.get("words")
            or "the desk could not find a combination for these legs. "
               "Nothing was created and nothing was sent.",
        )

    # -- the market: its price grid and, decisively, its exchange shard -------
    #
    # **Taken from the MINT response, not re-read.** The first version of this
    # called `GET /markets/{ticker}` here and it produced a 500 in front of Joe
    # on 2026-08-30: that endpoint returns 404 `not_found` for a combination
    # minted seconds earlier. The catalogue lags the mint -- while the
    # orderbook endpoint answers for the same ticker immediately, which is why
    # the lookup path never noticed. The mint response already carries
    # `price_ranges`, `price_level_structure` and `exchange_index`, so the
    # second read was redundant as well as racy.
    #
    # **The shard is read, never assumed to be `EXCHANGE_INDEX_COMBOS`.** That
    # constant is what the combinations shard was on 2026-08-30; Kalshi moved
    # baseball to a new shard six days before that and calls `exchange_index`
    # on the market "the authoritative source of truth". A desk that hardcoded
    # the shard would cancel into the wrong one the day it moves, and a cancel
    # that cannot find its order is the failure this path exists to avoid.
    market = priced.get("minted_market")
    if not isinstance(market, dict):
        # A lookup that minted a market without describing it. Refusing is the
        # only honest move: the grid decides which prices the venue accepts and
        # the shard decides whether the bid can ever be cancelled, and guessing
        # either is how an order rests forever at a price nobody can hit.
        raise ComboOrderRefused(
            502,
            f"Kalshi created the combination ({ticker}) but did not describe "
            f"it, so neither its price grid nor the exchange shard it trades "
            f"on is known. Nothing was sent -- try again in a moment.",
        )
    try:
        grid = parse_price_grid(
            market.get("price_ranges"),
            structure=market.get("price_level_structure"),
        )
    except Exception as exc:                                     # noqa: BLE001
        # `GridUnavailable` is not an internal error, it is the venue changing
        # a field name. Refusing in words beats a 500 on the screen.
        raise ComboOrderRefused(
            502,
            f"the combination's price grid could not be read ({exc}), so the "
            f"desk does not know which prices Kalshi will accept. Nothing was "
            f"sent.",
        ) from exc
    exchange_index = market.get("exchange_index")
    if not isinstance(exchange_index, int):
        raise ComboOrderRefused(
            502,
            "Kalshi did not say which exchange shard this combination trades "
            "on. A bid placed without it could not be cancelled afterwards, "
            "so nothing was sent.",
        )

    # -- can this shard pay for it -------------------------------------------
    contracts = contracts_for_stake(stake_tenths, price_tenths)
    funds = read_shard_funds(
        await api.balance(exchange_index=exchange_index),
        exchange_index=exchange_index,
    )
    check_affordable(
        contracts=contracts, price_tenths=price_tenths, funds=funds
    )

    try:
        request = OrderRequest(
            ticker=ticker,
            side="yes",
            action="buy",
            count=contracts,
            limit_price_tenths=price_tenths,
            price_grid=grid,
            time_in_force="good_till_canceled",
            client_order_id=str(uuid.uuid4()),
        )
    except Exception as exc:                                     # noqa: BLE001
        raise ComboOrderRefused(422, str(exc)) from exc

    # **The earliest leg's kickoff, from the card that was just priced.** A
    # resting bid that fills after a leg is under way is a bet on a game in
    # progress at a price computed before it started.
    cancel_after_ms = _earliest_commence_ms(priced)

    row_id = record_intent(
        conn,
        now_ms=now_ms,
        ticker=ticker,
        card_key=card_key,
        legs=list(requested_legs),
        exchange_index=exchange_index,
        contracts=contracts,
        price_tenths=request.api_price_tenths,
        fair_joint=(priced.get("fair") or {}).get("conservative"),
        cancel_after_ms=cancel_after_ms,
        request_body=request.to_api_dict(),
        dry_run=store_bids.COMBO_ORDERS_ARE_DRY_RUNS,
    )

    # Read through the module rather than bound at import: one source of
    # truth for the switch, and a rehearsal can flip it without the
    # value it flips having already been copied into this frame.
    if store_bids.COMBO_ORDERS_ARE_DRY_RUNS:
        return {
            "status": "dry_run",
            "order_row_id": row_id,
            "ticker": ticker,
            "exchange_index": exchange_index,
            "contracts": contracts,
            "price_tenths": request.api_price_tenths,
            "words": (
                f"Dry run: this would rest a bid for {contracts} contracts at "
                f"{request.api_price_tenths / 10:.1f}c on {ticker}. Nothing "
                f"was sent to the exchange."
            ),
        }

    try:
        response = await api.request(
            "POST", "/portfolio/events/orders", json_body=request.to_api_dict()
        )
    except Exception as exc:                                     # noqa: BLE001
        # The row stays `pending` on purpose. A request that left this process
        # and did not come back may or may not be resting on the exchange, and
        # `pending` is the only honest status for that -- it keeps counting
        # against exposure and shows on the screen as something to check.
        record_outcome(
            conn, row_id, status=store_bids.STATUS_PENDING, error_text=str(exc)
        )
        raise ComboOrderRefused(
            502,
            f"The bid was sent and the exchange did not answer ({exc}). It may "
            f"be resting: check the orders panel and the Kalshi app before "
            f"sending another.",
        ) from exc

    status, kalshi_order_id = status_from_response(response)
    record_outcome(
        conn, row_id, status=status, kalshi_order_id=kalshi_order_id,
        response_body=response if isinstance(response, dict) else None,
    )
    return {
        "status": status,
        "order_row_id": row_id,
        "kalshi_order_id": kalshi_order_id,
        "ticker": ticker,
        "exchange_index": exchange_index,
        "contracts": contracts,
        "price_tenths": request.api_price_tenths,
        "words": _words_for(status, contracts, request.api_price_tenths),
    }


def _words_for(status: str, contracts: int, price_tenths: int) -> str:
    """What happened, in words that promise nothing about a fill."""
    cost = contracts * price_tenths / 1000.0
    if status == store_bids.STATUS_RESTING:
        return (
            f"Your BUY order is waiting: {contracts} contracts at "
            f"{price_tenths / 10:.1f}c, ${cost:.2f} if it all fills. If the "
            f"parlay hits, each contract pays $1.00 -- "
            f"${contracts:.2f} back. You are the buyer; the order fills only "
            f"when someone sells to you at that price, and on a combination "
            f"nobody may. Until it fills you hold nothing -- it shows in "
            f"Kalshi under Orders, not Positions. It is withdrawn "
            f"automatically when the first game starts."
        )
    if status == store_bids.STATUS_FILLED:
        return (
            f"Filled immediately: {contracts} contracts at "
            f"{price_tenths / 10:.1f}c, ${cost:.2f}. Someone was already "
            f"offering at or under your price."
        )
    if status == store_bids.STATUS_PARTIALLY_FILLED:
        return (
            f"Partly filled at {price_tenths / 10:.1f}c; the rest is resting. "
            f"The orders panel has what is still working."
        )
    return (
        "The exchange did not accept the bid. Nothing is resting; the record "
        "has the response."
    )


def _earliest_commence_ms(priced: dict) -> Optional[int]:
    """The first kickoff among the card's legs, or `None`.

    `None` when the priced payload does not carry the legs' clocks -- and a
    `None` here means the bid gets NO automatic cancel, which
    `due_for_cancel` refuses to treat as due. That is the conservative
    direction: a bid nobody cancels is visible in the orders panel and can be
    cancelled by hand, while a bid cancelled on an unknown deadline vanishes
    for a reason nobody can reconstruct.
    """
    legs = priced.get("legs")
    if not isinstance(legs, list):
        return None
    stamps = [
        leg.get("commence_ms")
        for leg in legs
        if isinstance(leg, dict) and isinstance(leg.get("commence_ms"), int)
    ]
    return min(stamps) if stamps else None
