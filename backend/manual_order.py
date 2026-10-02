"""Joe's hand bet, checked and sent: `POST /api/manual-orders`'s body.

ADR 0192 §2.7 (S3, #266). Until 2026-10-01 this lived inside
`routes.create_app` as a closure over the app's config and clients, so the
one armed order path could be exercised only through `TestClient`. It moved
here **byte for byte**: every check (0-13), every refusal sentence, the IOC
send, the outcome writes, the position step and the response wording. No
check was added, removed or loosened (ADR 0112 §3-§4). The only edits were
mechanical -- closure helpers became the module functions below, the clock
is a parameter (`now_ms`), and `_is_combo(ticker)` is spelled as the
predicate it delegated to.

The route in `routes.py` is a thin adapter that passes this app's ports:
`live_quotes` (the venue read: quotes, shard balance, positions) and
`combo_api` (the shared REST client the placer sends through). Both are
passed as the zero-argument factories they are in `create_app`, not as
built objects, because building either raises `ConfigError` on a keyless
instance and the checks catch that at their own step -- calling them early
would move a refusal out of the durable refusal record.

Refusals are still `HTTPException`. That is deliberate, not an oversight:
check bodies raise it and the refusal recorder catches it, and translating
to a domain exception would have edited every check on the path that
spends -- the one thing S3 promised not to do.

**What this does not establish.** Moving the code proves nothing about the
venue; the checks are exactly as strong as they were. `tests/test_manual_
order_direct.py` drives this function without `TestClient` to pin that the
seam is real.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

from . import bets as bets_module
from . import estimates as bet_estimates
from . import positions
from .config import ConfigError
from .core.fees import combo_taker_fee
from .core.prices import PRICE_MAX, format_price, is_valid_price
from .kalshi.orders import OrderPlacer, OrderRefused, OrderRequest
from .kalshi.quotes import QuoteUnavailable
from .kalshi.rest import parse_position_fp
from .parlays import (
    COMBO_EXIT_RFQ_BIDS_BELOW_BASIS,
    COMBO_EXIT_RFQ_DATE,
    COMBO_EXIT_RFQ_POSITIONS,
    COMBO_EXIT_RFQ_POSITIONS_WITH_BID,
)
from .portfolio_poll import log_poll_attempt, store_positions_snapshot
from .store import db
from .store import manual_orders as manual_store
from .store.combo_orders import read_shard_funds
from .store.manual_orders import (
    COMBO_MAX_CONTRACTS,
    MANUAL_ORDER_MAX_CONTRACTS,
)
from .store.orders import DuplicateOrder

logger = logging.getLogger(__name__)


def reachable_refusal(app_config, manual_config) -> Optional[str]:
    """None when the path may answer, else the refusal text.

    BOTH halves are server-side (CLAUDE.md: a public URL must not be one
    config bug from the order path): the demo instance refuses on its
    mode regardless of any env leak, and live refuses until the flag is
    deliberately set.
    """
    if app_config.is_demo:
        return (
            "the manual order path does not exist on the demo instance, "
            "by construction."
        )
    if not manual_config.enabled:
        return (
            "the manual order path is not enabled on this instance "
            "(MANUAL_ORDERS_ENABLED). Enabling it is a deliberate act, "
            "not a default."
        )
    return None


def tradeable_ask(ask_tenths: Optional[int]) -> Optional[int]:
    """A derived ask, or `None` when it is not a price anyone can pay.

    Asks are derived — `yes_ask = 1000 - best_no_bid` — so an EMPTY book
    does not produce "no ask", it produces the endpoints: a missing NO bid
    reads as a resting bid of 100c and hands back a 0c YES ask. 0 and 1000
    are settled outcomes, not quotes (`is_valid_price` refuses both), and
    this is exactly the shape of every combination market on the venue
    right now: `no_bid_dollars = 1.0000`, depth 0.0, a YES ask that renders
    as **0c**.

    Observed on live 2026-08-26 while driving the ticket for the first
    time. The order path was already safe — `OrderRequest` refuses the
    price on the grid — but the SCREEN read "YES 0c", which is a free
    contract on the most illiquid product the venue lists, and CLAUDE.md
    rule 1 is that a large apparent edge is a bug until proven otherwise.
    The honest render is no ask at all, which the ticket already has words
    for.
    """
    if ask_tenths is None or not is_valid_price(ask_tenths):
        return None
    return ask_tenths


def worst_case_dollars(
    order: OrderRequest, *, combo: bool
) -> Optional[float]:
    """What this order costs if it fills completely, fee included.

    `OrderRequest.worst_case_cost_dollars` for everything but a combo.
    On a combo the same arithmetic runs through `combo_taker_fee`, whose
    coefficient sits above every combo charge this repo has observed
    (ADR 0073) -- because `calculate_fee` undercharged four of the eight
    combo fills on the record, and a per-bet cap checked against an
    understated cost is not a cap.

    The fee is taken at the larger of the sent and un-snapped prices, for
    the reason `worst_case_cost_dollars` gives: the curve peaks at 50c,
    so a snapped-down price understates a fee just below the peak.

    `None` when the fee is unreadable -- the caller refuses; it never
    substitutes zero.
    """
    if not combo:
        return order.worst_case_cost_dollars
    stake = order.count * order.fill_price_tenths / float(PRICE_MAX)
    sent = combo_taker_fee(order.fill_price_tenths, order.count)
    asked = combo_taker_fee(order.limit_price_tenths, order.count)
    if sent is None or asked is None:
        return None
    return stake + max(sent, asked)


async def place_manual_order(
    conn,
    request,
    *,
    app_config,
    manual_config,
    risk,
    odds,
    live_quotes: Callable,
    combo_api: Callable,
    now_ms: Optional[Callable[[], int]] = None,
) -> dict:
    """A hand bet through the portal (ADR 0063). Every safeguard is
    server-side and none is waivable from the client:

    0.  reachability (live instance AND the explicit flag) — 403
    1.  idempotency replay — the first answer, again
    2.  the desk lockout — 423, same shape as the estimate route
    3.  the cool-off after the last completed purchase — 423
    4.  KXMVE bounds — 422 without `combo_acknowledged`, 422 above one
        contract (ADR 0073; enter-only book, ADR 0012 §5, and a hedged
        fee because ADR 0046's model undercharges there). The path's own
        1-contract ceiling (ADR 0063) is checked here too.
    5.  daily-loss kill switch over the venue's own record — 422
        (ADR 0064; None refuses, never zeroes)
    6.  caps derived from the observed balance — 422 when unobserved
    7.  live quote; ask over the typed ceiling — 422 ("the ask moved")
    8.  depth at the ask — 422
    9.  per-bet cap on the fee-inclusive worst case — 422 (the combo
        hedge prices a KXMVE order; an unreadable fee refuses)
    10. any existing venue position on this ticker — 422 (the wire's
        per-row position shape has never been observed, so holding
        ANYTHING here refuses; Kalshi nets, and a buy that closes a
        position must not be recorded as opening one)
    11. reserve-then-check under the write lock, in `manual_orders`
    12. place IOC at the ceiling-bounded ask via the shared OrderPlacer
    """
    # Every refusal below is recorded durably before it propagates
    # (schema v29, `manual_order_refusals`): reservation happens at
    # check 11, so until 2026-08-30 every earlier refusal left zero
    # trace and the desk could not say which of its own brakes fired.
    # `refusal_ctx` is the check pointer -- updated at the top of
    # each numbered check, so a raise mid-check is attributed to the
    # check that was running rather than parsed out of the message.
    # Resolved per call, not bound at import, so a test that patches
    # `db.now_ms` still reaches this path (kalshi-platform review of #266).
    now_ms = now_ms or db.now_ms
    refusal_ctx: dict = {"check": 0, "name": "reachability"}
    try:
        # 0.
        unreachable = reachable_refusal(app_config, manual_config)
        if unreachable is not None:
            raise HTTPException(status_code=403, detail=unreachable)

        # 1.
        refusal_ctx.update(check=1, name="idempotency_replay")
        existing = manual_store.find_by_idempotency_key(
            conn, request.idempotency_key
        )
        if existing is not None:
            stored = manual_store.replay_response(existing)
            if stored is None:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"this idempotency key was used by an order whose "
                        f"outcome was never stored (row {existing['id']}, "
                        f"status {existing['status']!r}). Check the record "
                        f"before retrying with a fresh key — 'we do not know "
                        f"whether it went' must not resolve to 'it did not'."
                    ),
                )
            stored["replayed"] = True
            return stored

        now = now_ms()

        # 2.
        refusal_ctx.update(check=2, name="desk_lockout")
        lockout_release = bet_estimates.lockout_until(conn, now_ms=now)
        if lockout_release is not None:
            release_iso = datetime.fromtimestamp(
                lockout_release / 1000, timezone.utc
            ).strftime("%H:%M UTC on %Y-%m-%d")
            raise HTTPException(
                status_code=423,
                detail=(
                    f"You said not tonight. The desk is locked until "
                    f"{release_iso}, and there is no early unlock — that is "
                    f"the point."
                ),
            )

        # 3. REMOVED 2026-09-08 on Joe's word --
        # `docs/adr/0112-the-caps-come-off-the-hand-bet-path.md` §1,
        # answer 3 ("none"). The 10-minute cool-off between completed
        # purchases is gone. He was told first what it would cost him: he
        # averages ~2.3 fills per sitting, so it was a brake that would
        # have fired on most sittings rather than a rare one.
        #
        # `manual_store.cooloff_until_ms` is deliberately NOT deleted. It
        # is a pure read over `manual_orders` with its own tests, it is
        # what a future session would have to rebuild to restore this, and
        # ADR §5 says restoring it needs Joe rather than a session's
        # judgement. An uncalled reader is cheap; a rebuilt brake he did
        # not ask for is not. `test_manual_orders.py` pins it uncalled
        # from this route so "built but never called" stays deliberate
        # here rather than becoming another instance of the pattern.
        #
        # The check NUMBERS below are unchanged. Renumbering would have
        # silently re-pointed every `manual_order_refusals.check` row
        # already on the live box, and the durable refusal record is
        # read by `inspect_live_db`; check 3 simply no longer occurs.

        ticker = request.ticker.strip().upper()

        # 4.
        refusal_ctx.update(check=4, name="structural_ceilings")
        combo = manual_store.is_combo_ticker(ticker)
        if combo and not request.combo_acknowledged:
            # The third of the three sentences carrying the exit census,
            # and the last one still typed. Sourced from
            # `parlays.COMBO_EXIT_CENSUS_*` on 2026-09-06 for the reason
            # the other two were: `str(40) in detail` cannot tell a typed
            # digit from a sourced one, so the digits could have outlived
            # the measurement with CI green.
            #
            # **And on 2026-09-10 the claim DID move, which is what that
            # sourcing was for.** "You can enter and you cannot exit" was
            # a universal, and two `KXMVECROSSCATEGORY-SHARD1` books were
            # read that day carrying resting YES bids. ADR 0085
            # Amendment 1 §A1.4 pins against SOFTENING an exit claim that
            # still holds; it does not require repeating one that has
            # been falsified, and this is a real-money refusal path where
            # a false sentence is worse than a weaker true one. The
            # replacement keeps the warning's force by naming the size --
            # the exit that exists is a dollar of it -- and still claims
            # no rate, which Arm D measures on 2026-09-13. Guarded by
            # `tests/test_manual_orders.py::test_no_census_number_in_the_
            # combo_acknowledgement_refusal_is_typed_rather_than_sourced`.
            raise HTTPException(
                status_code=422,
                detail=(
                    f"combination (KXMVE) markets need the acknowledgement "
                    f"before this door opens: on "
                    f"{COMBO_EXIT_RFQ_DATE}, "
                    f"{COMBO_EXIT_RFQ_POSITIONS_WITH_BID} of "
                    f"{COMBO_EXIT_RFQ_POSITIONS} combinations this desk "
                    f"held drew a bid for the side held when the makers "
                    f"were asked, every one at the full size asked — so "
                    f"you can sell it back. The catch is the price, not "
                    f"the door: all "
                    f"{COMBO_EXIT_RFQ_BIDS_BELOW_BASIS} of those best "
                    f"bids were BELOW what had been paid, so selling "
                    f"back may cost more than holding to the outcome "
                    f"(ADR 0164). The fee model also "
                    f"undercharges on combos (ADR 0046); a hedged coefficient "
                    f"prices this order and it is not a measurement of what "
                    f"Kalshi charges. Send `combo_acknowledged` only if that "
                    f"is the bet you mean to make."
                ),
            )
        # **The STRUCTURAL ceilings, not the binding one.** What bounds the
        # bet is money (check 9); these stop a market priced at a tenth of a
        # cent turning a few dollars into a count that moves a thin book on
        # its own.
        #
        # **The reason this ceiling used to give was false, corrected
        # 2026-09-08.** It said "the deepest resting bid this repo has ever
        # measured on one was 18 units (ADR 0012 §5), so a far larger count
        # could not fill anyway." Three things were wrong with that. (1) ADR
        # 0012 carries no such figure; its only "18" is the denominator of
        # `same-game 17/18`, a rate the ADR itself withdraws. (2) The real
        # source is
        # `docs/measurements/2026-08-18-combo-book-presence-inseason-result.md`,
        # which says "the deepest resting order **here** was 18.00 units" —
        # scoped by that "here" to one run of 11 rows. Every copy downstream
        # dropped the word and promoted it to "ever measured". (3) Repo-wide
        # it is wrong by ~38x: the committed captures carry resting NO bids
        # of 683, 413, 369, 311, 309 and 300 units (E3 and E2, 2026-08-09),
        # and the NO bid is the side whose complement is the ask you buy at.
        #
        # So the count ceiling no longer claims a fill bound it cannot
        # support. What survives — and is the true, load-bearing claim — is
        # the EXIT: `yes_dollars` is empty on 40/40 books ever read, 36
        # levels, zero resting YES bids. That is why a combination is held
        # tighter than a single market. It is not that you cannot get in.
        if combo and request.contracts > COMBO_MAX_CONTRACTS:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"a combination order is capped at "
                    f"{COMBO_MAX_CONTRACTS} contracts on this path, against "
                    f"an order for {request.contracts}. The cap is a "
                    f"structural ceiling, not a measured fill limit: no "
                    f"combination book this tool has read has ever carried a "
                    f"resting YES bid (40 of 40), so a combination is easy "
                    f"to enter and may be impossible to exit at size. "
                    f"Nothing below bounds the SIZE of your bet except "
                    f"the depth resting at the ask and what your exchange "
                    f"shard can pay for — the venue's rule, not a cap of "
                    f"ours."
                ),
            )
        if request.contracts > MANUAL_ORDER_MAX_CONTRACTS:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"this path is capped at {MANUAL_ORDER_MAX_CONTRACTS} "
                    f"contracts, against an order for {request.contracts}. "
                    f"That is a structural ceiling, not the bet size: "
                    f"no ceiling of ours bounds the bet at all any more. "
                    f"What is left is the depth resting at the ask and "
                    f"what your exchange shard can pay for."
                ),
            )

        # 5. THE COUNTER STAYS; THE SWITCH IS REMOVED. Joe's answers 2 and
        # 4 together, 2026-09-08 --
        # `docs/adr/0112-the-caps-come-off-the-hand-bet-path.md` §1. He
        # removed the daily-loss KILL SWITCH and, in the same interview,
        # kept the desk counting his Kalshi losses including the ones he
        # places in the venue's own app. Those are not in tension: the
        # figure is information, and ADR 0071 makes information this
        # product's job. So the read stays and no longer refuses.
        #
        # It also no longer refuses when it cannot be read. That refusal
        # (ADR 0064, "'cannot read the losses' must never resolve to 'no
        # losses'") existed to protect the switch, and its own words say
        # so -- "so the daily-loss switch cannot be applied". With no
        # switch it guards nothing, and keeping it would refuse a bet Joe
        # has asked nothing to refuse. ADR 0064's rule is untouched
        # everywhere it still governs a decision; `None` still means
        # unreadable here and is never coerced to 0.
        refusal_ctx.update(check=5, name="daily_loss_counter")
        daily_pnl = bets_module.venue_daily_realised_pnl_dollars(
            conn, now_ms=now, day_start_hour=odds.budget_day_start_utc_hour
        )

        # 6. NARROWED, not removed, and the narrowing is the careful part.
        # This refused unless all three derived caps were available.
        # **All three are now gone** -- the per-bet cap (check 9) and the
        # daily-loss line (check 5) on 2026-09-08 under ADR 0112, and the
        # total-exposure ceiling later the same day under its Amendment 1,
        # when Joe removed the one brake he had not previously been asked
        # about: "remove the exposure ceiling too."
        #
        # So check 6 REFUSES NOTHING and is kept only to derive `risk_now`,
        # which the recorded row still carries. A bet placed with no brake
        # should stay legible later as "this was N times the ceiling that
        # used to exist", and that is impossible if the ceiling is never
        # computed. An unobserved balance no longer refuses: there is no
        # longer a guard whose precondition it was, and refusing on a
        # precondition for nothing is how a removed cap comes back by
        # accident.
        #
        # `orders.reserve_order` still caps the ENGINE. Same scoping as
        # ADR 0112 §3.
        refusal_ctx.update(check=6, name="derived_caps_for_the_record")
        risk_now = risk
        if risk.underived:
            risk_now = risk.with_observed_balance(db.latest_balance_tenths(conn))

        refusal_ctx.update(check=7, name="live_quote_and_ceiling")
        try:
            quote = await live_quotes().fetch(ticker, observed_ms=now)
        except ConfigError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except QuoteUnavailable as exc:
            raise HTTPException(
                status_code=404 if exc.permanent else 503, detail=str(exc)
            ) from exc
        ask = tradeable_ask(quote.ask_tenths(request.side))
        refusal_ctx["ask_tenths"] = ask
        if ask is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"no live ask on the {request.side} side — there is no "
                    f"price to buy at. An empty book does not report 'no ask'; "
                    f"it reports the endpoint (a 0c or 100c derived ask), and "
                    f"neither is a price anyone can pay."
                ),
            )
        if ask > request.max_price_tenths:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"the live ask is {format_price(ask)}, above your "
                    f"{format_price(request.max_price_tenths)} ceiling. "
                    f"Refused, never re-priced — raise the ceiling only if "
                    f"you still want it at the new price."
                ),
            )
        if quote.price_grid is None:
            raise HTTPException(
                status_code=503,
                detail=(
                    "the live payload carried no readable price grid; "
                    "refusing rather than assuming whole cents."
                ),
            )

        # 8.
        refusal_ctx.update(check=8, name="depth_at_ask")
        depth = quote.depth_at_ask(request.side)
        if depth is None or depth < request.contracts:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"only {0 if depth is None else int(depth)} contracts "
                    f"rest at the ask against an order for "
                    f"{request.contracts}. An IOC for more than the book "
                    f"holds part-fills at best."
                ),
            )

        # 9. Build at the live ask (bounded by the ceiling above), IOC.
        refusal_ctx.update(check=9, name="per_bet_cap")
        try:
            order = OrderRequest(
                ticker=ticker,
                side=request.side,
                action="buy",
                count=request.contracts,
                limit_price_tenths=ask,
                price_grid=quote.price_grid,
                time_in_force="immediate_or_cancel",
            )
        except OrderRefused as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        # 9a. **WHICH POCKET THE MONEY IS IN.** Added 2026-09-08, after
        # Joe read his own allocation off Kalshi: shard 1 (Combos)
        # $22.24, shard 0 (Default) $0.00. Every single-market bet draws
        # on shard 0 and would have been refused by the VENUE with a bare
        # `insufficient_balance` -- which, against a $22 account, reads as
        # a broken cockpit rather than as "your money is in the other
        # pocket". The combination path solved this in ADR 0084 and the
        # reasoning was never carried across; `combo_orders.check_
        # affordable`'s docstring says it outright: only the desk is in a
        # position to say so.
        #
        # **This is not a brake and does not reinstate one.** ADR 0112
        # removed the desk's own ceilings; this refuses only what the
        # venue was always going to refuse, one round trip earlier and in
        # words that name the fix. Nothing here bounds a bet Kalshi would
        # have accepted.
        #
        # The shard is read off the MARKET (`quote.exchange_index`), never
        # inferred from the ticker prefix: Kalshi's docs call that field
        # the authoritative source of truth and say ticker formats move.
        # Unreadable refuses rather than defaulting to 0 -- 0 is a real
        # shard, and guessing it is how a "payable" order dies at the
        # venue after he has typed a price and confirmed.
        refusal_ctx.update(check=9, name="shard_collateral")
        shard = quote.exchange_index
        if shard is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "this market does not say which exchange shard it "
                    "settles on, so the desk cannot tell whether you have "
                    "the collateral for it. Refusing rather than guessing "
                    "— Kalshi keeps money per shard and will not move it "
                    "for an order. Nothing was sent."
                ),
            )
        try:
            shard_payload = await live_quotes().shard_balance(
                exchange_index=shard
            )
        except QuoteUnavailable as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        funds = read_shard_funds(shard_payload, exchange_index=shard)
        if not funds.is_readable:
            raise HTTPException(
                status_code=502,
                detail=(
                    f"the balance on exchange shard {shard} could not be "
                    f"read, so the desk cannot tell whether this bet is "
                    f"payable. Refusing — an unreadable balance must "
                    f"never resolve to a spendable one. Nothing was sent."
                ),
            )
        cost_tenths = order.count * order.limit_price_tenths
        if funds.available_tenths < cost_tenths:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"this bet needs ${cost_tenths / 1000:.2f} on exchange "
                    f"shard {shard}, which holds "
                    f"${funds.available_tenths / 1000:.2f}. Kalshi keeps "
                    f"collateral per shard and will not move it for an "
                    f"order, so it has to be moved there first — on "
                    f"kalshi.com/account/exchange-indexes, where the "
                    f"transfer control appears only while 'Disable "
                    f"balance management' is on. This is the venue's "
                    f"rule, not a cap of yours. Nothing was sent."
                ),
            )

        # **THE PER-BET CAP IS REMOVED.** Joe, 2026-09-08: "remove the cap.
        # i will decide." Both ceilings go, because both were caps on the
        # size of his bet and he was answering about both -- 10% of the
        # observed balance (ADR 0045) and `MANUAL_ORDER_MAX_SPEND_TENTHS`.
        # See `docs/adr/0112-the-caps-come-off-the-hand-bet-path.md`, and
        # §4 of it in particular: after this the cockpit will not stop him
        # at any size his Kalshi collateral can pay for. That is the
        # intended outcome and restoring it needs Joe, not a session.
        #
        # `worst_case` is still computed and still recorded, because the
        # number is the transparency ADR 0071 asks for even when nothing
        # acts on it -- and because a future census of what he actually
        # bet is unreadable without it.
        #
        # The unreadable-fee refusal went with the cap rather than
        # surviving it. Its own message said why it existed: "so its
        # worst-case cost cannot be checked against your per-bet cap."
        # With no cap it guarded nothing, and it would have refused a bet
        # on the strength of a bound that no longer exists. `None` is
        # still `None` here and is never read as zero -- it is recorded
        # as unknown, which is the honest value.
        worst_case = worst_case_dollars(order, combo=combo)

        # 10. A LIVE positions read, not the 12-hour mirror. The per-row
        refusal_ctx.update(check=10, name="netting_guard")
        #     shape was observed 2026-08-30 (`position_fp`, a fixed-point
        #     string, fractional — see `rest.positions()`), so the guard
        #     compares the quantity the venue reports instead of refusing on
        #     ticker alone: until then a market Joe had EXITED still refused
        #     re-entry, because the bare endpoint returns zero-quantity rows
        #     for every market ever traded. A row too unreadable to name a
        #     ticker, or naming this ticker with a quantity that will not
        #     parse, still refuses — unreadable resolves to a refusal, never
        #     to zero.
        #
        #     **And the read is stamped, because it is a real one.**
        #     `poll_log` means "the venue was asked and this is what it
        #     said", and this asked the venue — so throwing the observation
        #     away (which this route did until 2026-08-29) left the
        #     open-positions count claiming to be older than the newest read
        #     actually taken. What the stamp does NOT establish, and the
        #     reason it supplements `portfolio_poll.poll_positions` and never
        #     substitutes for it: it is taken BEFORE the order, so it does
        #     not include the bet being placed, and it fires only when Joe
        #     bets — a night with no taps leaves no row here at all. It is
        #     also not derived from anything local; a synthetic row would
        #     poison three registered tripwires and the daily-loss kill
        #     switch, which `odds/sweeplog.py` refuses for the same reason.
        positions_read_ms = now_ms()
        try:
            position_rows = await live_quotes().portfolio_positions()
        except (ConfigError, QuoteUnavailable) as exc:
            await _stamp_positions_read(
                app_config.db_path,
                now_ms=positions_read_ms,
                ok=False,
                error=repr(exc),
            )
            raise HTTPException(
                status_code=503,
                detail=(
                    f"could not read your open positions, so 'this buy does "
                    f"not close an existing position' cannot be verified: "
                    f"{exc}. Kalshi nets — refusing rather than guessing."
                ),
            ) from exc
        await _stamp_positions_read(
            app_config.db_path,
            now_ms=positions_read_ms,
            ok=True,
            row_count=len(position_rows),
            rows=position_rows,
        )
        for row in position_rows:
            row_ticker = row.get("ticker") if isinstance(row, dict) else None
            if row_ticker is None:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "a position row came back too unreadable to name a "
                        "ticker, so 'this buy does not close an existing "
                        "position' cannot be verified. Refusing rather than "
                        "guessing."
                    ),
                )
            if row_ticker != ticker:
                continue
            quantity = parse_position_fp(row.get("position_fp"))
            if quantity is None:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "the venue reports a row for this market but its "
                        "quantity would not parse, so whether you already "
                        "hold a position here cannot be verified. Refusing "
                        "rather than guessing."
                    ),
                )
            if quantity != 0:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "you already hold a position this order could net "
                        "against. Kalshi nets buys against opposite "
                        "holdings, and this record must not book a close as "
                        "an open. Manage the existing position in the "
                        "Kalshi app first."
                    ),
                )

        # 11. ADR 0018's SECOND barrier, wired here rather than left for the
        refusal_ctx.update(check=11, name="placer_arming")
        #     arming commit to remember: `OrderPlacer.__init__` refuses when
        #     `dry_run` is False and no REST client was passed, so flipping
        #     the constant alone produces a 503 and not an order. The client
        #     is the app's one shared `KalshiRestClient` (`combo_api`), built
        #     on first use and closed in the lifespan — never a second one
        #     per request, which would cost a PEM re-parse and an SSL setup
        #     on the request that spends money.
        #
        #     Built ONLY when the path is armed. `combo_api()` calls
        #     `KalshiConfig.load()`, which raises on a keyless instance, and
        #     a dry run must keep working everywhere it works today.
        placer_rest = None
        if not manual_store.MANUAL_ORDERS_ARE_DRY_RUNS:
            try:
                placer_rest = combo_api()
            except ConfigError as exc:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        f"the manual path is armed but this instance holds "
                        f"no Kalshi credentials: {exc}. Nothing was sent."
                    ),
                ) from exc
        try:
            placer = OrderPlacer(
                rest=placer_rest,
                dry_run=manual_store.MANUAL_ORDERS_ARE_DRY_RUNS,
            )
        except OrderRefused as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    except HTTPException as exc:
        # Forensics beside the refusal, never in its way: the
        # recorder runs on a throwaway connection, falls back to a
        # journal line, and swallows its own errors -- and even a
        # recorder that blows up entirely must leave the 4xx
        # standing, not convert it into a 500.
        try:
            await run_in_threadpool(
                manual_store.record_refusal_durably,
                app_config.db_path,
                created_ms=now_ms(),
                check_number=refusal_ctx["check"],
                check_name=refusal_ctx["name"],
                http_status=exc.status_code,
                detail=str(exc.detail),
                ticker=request.ticker.strip().upper(),
                side=request.side,
                requested_contracts=request.contracts,
                max_price_tenths=request.max_price_tenths,
                idempotency_key=request.idempotency_key,
                ask_tenths=refusal_ctx.get("ask_tenths"),
            )
        except Exception:  # noqa: BLE001 -- the refusal outranks its record
            logger.exception("refusal recording raised; the 4xx stands")
        raise

    submitted_ms = now_ms()
    try:
        row_id = await run_in_threadpool(
            _write_manual_intent,
            app_config.db_path,
            order,
            dry_run=placer.dry_run,
            submitted_ms=submitted_ms,
            max_price_tenths=request.max_price_tenths,
            idempotency_key=request.idempotency_key,
        )
    except DuplicateOrder as exc:
        stored = manual_store.replay_response(exc.row)
        if stored is None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "a concurrent tap reserved this key and its outcome "
                    "is not stored yet. Nothing further was sent."
                ),
            ) from exc
        stored["replayed"] = True
        return stored
    # The `ExposureCapExceeded` branch was removed 2026-09-08 with the cap
    # itself (ADR 0112 Amendment 1). `reserve_manual_order` cannot raise it
    # any more; `orders.reserve_order` still can, and `/api/orders` still
    # catches it.
    except Exception as exc:                        # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail=(
                f"the order was not sent, because it could not be "
                f"written down first: {exc}."
            ),
        ) from exc

    # 12.
    outcome = await placer.place(order)
    try:
        await run_in_threadpool(
            _write_manual_outcome, app_config.db_path, row_id, outcome
        )
    except Exception:                               # noqa: BLE001
        logger.exception(
            "manual order row %d for %s was placed (%s) and could not "
            "be updated; it stays pending.",
            row_id, ticker, outcome.status,
        )

    # 13. THE EXIT THE DESK WATCHES, WIRED TO THE ENTRY. `/hedge` watches
    # `parlay_positions`, which this path never wrote. (A combination CAN
    # be sold back by RFQ or into a resting book bid, which was measured
    # 2026-09-17; the hedge is the exit the desk watches, not the only one
    # that exists. This comment called a combination enter-only until
    # 2026-10-01.) Two real
    # combination fills landed on 2026-09-08 and that table was empty for
    # the entire life of both positions.
    #
    # Only on a real fill of a real order: a dry run bought nothing, and
    # `fill_count` is the quantity the VENUE says is held rather than the
    # quantity asked for, so a part-filled IOC is watched at its true
    # size. `unrecognised_response` deliberately records nothing -- the
    # quantity is unknown there, and a position invented at the requested
    # size would be a fabricated holding in the one table whose job is to
    # tell him what he owns.
    position_id = None
    position_note = None
    filled = outcome.fill_count
    # `fill_count` is a float off the wire (`fill_count_fp`-shaped). Until
    # 2026-09-15 this was `int(filled)`, which TRUNCATES: 2.5 became 2,
    # understating the holding, so the stake, so the `/hedge` figure --
    # the flattering direction, refused by policy (ADR 0151). From then
    # until ADR 0192 (#265, 2026-10-01) any fraction was refused. Now a
    # fraction the table can hold exactly (2.5) is recorded at the
    # venue's count, as the RFQ path has done since ADR 0178. Only a
    # count finer than that (`count x 1000` not whole tenths) records no
    # position, and the screen says so -- never rounded.
    unholdable_fill = (
        filled is not None and filled > 0
        and not positions.holdable_count(filled)
    )
    if combo and not outcome.dry_run and unholdable_fill:
        logger.error(
            "manual order row %d filled on combo %s with a count %r finer "
            "than the table can hold; no hedge position recorded rather "
            "than a rounded one.", row_id, ticker, filled,
        )
        position_note = (
            f"This combination is NOT being watched for a hedge — the venue "
            f"reported a fill of {filled} contracts, a fraction finer than "
            f"the desk can record, and it will not round it into a holding. "
            f"Record it by hand on /hedge with the count Kalshi shows."
        )
    elif combo and not outcome.dry_run and filled is not None and filled > 0:
        refused = None
        try:
            recorded = await run_in_threadpool(
                _record_combo_position,
                app_config.db_path,
                manual_order_id=row_id,
                ticker=ticker,
                filled=float(filled),
                fill_price_tenths=order.fill_price_tenths,
                now_ms=now_ms(),
                placed_ms=submitted_ms,
            )
            position_id, refused = recorded.position_id, recorded.refused
        except Exception:                           # noqa: BLE001
            # Never into the order path: the money is already spent and a
            # bookkeeping failure must not report the purchase as failed.
            logger.exception(
                "manual order row %d filled on combo %s and its hedge "
                "position could not be recorded.", row_id, ticker,
            )
        if position_id is None and refused is not None:
            # The legs were fine; the SIZE or PRICE could not be held
            # (a tiny fraction whose stake rounds to its return). Saying
            # "legs could not be recovered" here would send him looking
            # for the wrong fault (kalshi-platform review of #265).
            position_note = (
                "This combination is NOT being watched for a hedge — the "
                f"desk could not record it as a ticket: {refused} Record "
                "it by hand on /hedge with what Kalshi shows."
            )
        elif position_id is None:
            # Said out loud, on the screen. Silence here is the exact
            # failure being fixed -- he would believe the desk was
            # watching a position it had never heard of.
            position_note = (
                "This combination is NOT being watched for a hedge — its "
                "legs could not be recovered, so record it by hand on "
                "/hedge. You can also sell a combination back, though "
                "selling back may cost more than holding it to the "
                "outcome; the hedge is the exit the desk watches, not "
                "the only one that exists."
            )
        else:
            position_note = (
                "Recorded on /hedge as position "
                f"{position_id} — its legs are being watched for a hedge."
            )

    body = {
        "status": outcome.status,
        "dry_run": outcome.dry_run,
        "manual_order_id": row_id,
        "client_order_id": order.client_order_id,
        "ticker": ticker,
        "side": request.side,
        "contracts": request.contracts,
        "limit_price_display": format_price(order.fill_price_tenths),
        "max_price_display": format_price(request.max_price_tenths),
        # "at most", never "costs $X": MLB's k is half the coefficient
        # charged, so the point figure would overstate — and never a
        # payout figure, which would assume untested H4 (ADR 0027).
        # `None` since 2026-09-08: the cap that used to refuse an
        # unreadable fee is gone (check 9), so this can now legitimately
        # be unknown and must say so rather than crash on the format or
        # print "$0.00", which would read as a free bet.
        "worst_case_cost_display": (
            "unknown — the fee on this order could not be computed"
            if worst_case is None
            else f"${worst_case:.2f}"
        ),
        "kalshi_order_id": outcome.kalshi_order_id,
        "error_text": outcome.error_text,
        # `None`, not a future timestamp: nothing rests after this order
        # any more, and a screen told to unlock at a time is a screen that
        # locks until then.
        "cooloff_until_ms": None,
        # Read at check 5 and carried here rather than discarded: the
        # switch is gone, the counting is not.
        "venue_daily_pnl_dollars": daily_pnl,
        # `None` on anything that is not a filled live combination.
        # `hedge_position_id` is None WITH a note when the fill happened
        # and the position could not be built -- the two must stay
        # separable, because "not a combo" and "a combo nothing is
        # watching" are opposite facts and only one of them is a problem.
        "hedge_position_id": position_id,
        "hedge_position_note": position_note,
        "note": (
            "Dry run — the manual path is not armed. Arming is a code "
            "change (ADR 0063); the C0 probe it waited on was taken "
            "2026-08-23. This is exactly the body a live order would "
            "send."
            if outcome.dry_run
            else (
                "LIVE ORDER sent immediate-or-cancel. If the status is "
                "unrecognised_response, the order MAY have been placed "
                "— check the Kalshi app before retrying."
            )
        ),
        "replayed": False,
    }

    try:
        await run_in_threadpool(
            _write_manual_response, app_config.db_path, row_id, body
        )
    except Exception:                               # noqa: BLE001
        logger.exception(
            "manual order row %d could not store its response; a "
            "duplicate tap will refuse rather than replay.", row_id,
        )

    return body


async def _stamp_positions_read(
    db_path,
    *,
    now_ms: int,
    ok: bool,
    row_count: Optional[int] = None,
    rows: Optional[list] = None,
    error: Optional[str] = None,
) -> None:
    """Record step 10's live positions read in `poll_log`, and keep its rows.

    The read is real -- `live_quotes().portfolio_positions()` asks the venue --
    so `poll_log`'s own meaning ("the venue was asked and this is what it
    said") is satisfied by it and by nothing local. It is written through the
    same `log_poll_attempt` the poller uses, with the same endpoint name, so
    `bets.open_positions` and the registration's gap tripwires read one
    population and not two.

    **That sentence became wholly true on 2026-09-05 and was half-true
    before** (ADR 0107 sections 5 and 9). `poll_log` has two writers of
    positions reads. Until this edit only the poller kept the rows it counted,
    so a reader taking "the newest successful positions poll" would find this
    route's stamp carrying `row_count = N` with no rows under it, and refuse
    the money figure for up to five minutes after every hand bet -- at the one
    moment the desk is open. The rows now go to `store_positions_snapshot`
    inside the same transaction, which also sets `poll_log.mirrored = 1`, and
    `bets.open_positions` selects on that marker rather than on recency alone.

    `rows=None` is not the same as `rows=[]`. `None` means the caller is not
    offering any (a failed read; a caller written before this parameter
    existed) and nothing is mirrored; `[]` is the venue saying the account
    holds nothing, which is a real observation and is stored as a marked
    snapshot with zero rows. That distinction is the whole reason the marker
    exists -- no count can tell "kept nothing" from "kept, and there was
    nothing".

    **What it does NOT establish**, restated here because a reader who finds
    this row in the table will not have step 10's comment in front of them:

    - It is taken **before** the order is sent, so its `row_count` cannot
      include the bet being placed. A row stamped at 20:14 next to a fill at
      20:14 is the count as it was a moment earlier, not after.
    - It fires **only when Joe taps**. A night with no bets leaves no row
      here, so this can never be the thing that keeps the count fresh -- it
      supplements `portfolio_poll.poll_positions` and does not substitute for
      it. If the poller stops, the count goes stale exactly as it should.
    - Failures are stamped too, matching the poller's convention: a failure
      that writes nothing is invisible and reads like a quiet evening. A
      failed read keeps **nothing** and is left unmarked: the venue answered
      with an error, so there is no observation to mirror, and marking it
      would tell the reader rows were kept when none were.

    **Never blocks the order.** The stamp is bookkeeping about a read that
    already happened; losing it must not cost Joe a bet, so a write failure
    is logged and swallowed. The order path's own refusals are unaffected --
    this function is called after the read and never decides anything. That
    now covers the mirror too: if `store_positions_snapshot` raises, the whole
    write is lost together and the bet still goes through. Losing both is the
    right failure -- an unmarked stamp is a state `bets.open_positions`
    already knows how to refuse, while a marked stamp with no rows would be a
    lie it would believe.
    """
    def _write() -> None:
        conn = db.open_db(db_path)
        try:
            poll_log_id = log_poll_attempt(
                conn,
                now_ms=now_ms,
                endpoint="positions",
                ok=ok,
                row_count=row_count,
                error=error,
            )
            if ok and rows is not None:
                store_positions_snapshot(
                    conn, poll_log_id=poll_log_id, now_ms=now_ms, rows=rows
                )
            conn.commit()
        finally:
            conn.close()

    try:
        await run_in_threadpool(_write)
    except Exception:                                   # noqa: BLE001
        logger.exception(
            "the live positions read at %d could not be stamped in poll_log; "
            "the order path is unaffected", now_ms,
        )


def _write_manual_intent(db_path, order, **kwargs) -> int:
    """The manual row, reserved under its own write lock (ADR 0063)."""
    conn = db.open_db(db_path)
    try:
        return manual_store.reserve_manual_order(conn, order, **kwargs)
    finally:
        conn.close()


def _write_manual_outcome(db_path, row_id: int, outcome) -> None:
    conn = db.open_db(db_path)
    try:
        manual_store.record_outcome(conn, row_id, outcome)
    finally:
        conn.close()


def _write_manual_response(db_path, row_id: int, body: dict) -> None:
    conn = db.open_db(db_path)
    try:
        manual_store.record_response(
            conn, row_id, json.dumps(body, sort_keys=True)
        )
    finally:
        conn.close()


def _record_combo_position(
    db_path,
    *,
    manual_order_id: int,
    ticker: str,
    filled: float,
    fill_price_tenths: int,
    now_ms: int,
    placed_ms: int,
) -> "positions.OrderFill":
    """Put a combination bought through the desk under `/hedge`'s watch.

    **The exit the desk watches, wired to the entry.** Until 2026-09-09 the
    only writer of `parlay_positions` was `POST /api/hedge/positions`, a
    separate tap on a separate screen. On 2026-09-08 the desk took two real
    combination fills and the table stayed empty for the whole life of both.

    Since ADR 0192 (2026-10-01, #265) the rules live in
    `positions.record_order_fill`, and this only opens the connection.
    Writing there changes two things:
    - The stake is the venue's own average fill price whenever this order's
      `manual_orders` row proves it, and the sent price otherwise. Which one
      is stored with the row (`stake_basis`). This supersedes ADR 0160 §2.1
      for new rows.
    - A fractional fill the table can hold is recorded at the venue's count.

    Returns `positions.OrderFill`. An id of `None` is never an error the
    caller may hide: it means the money moved and nothing is watching it, so
    the caller says so on the screen -- with the ticket check's own reason
    when `refused` carries one. Nothing here raises into the order path.
    """
    conn = db.open_db(db_path)
    try:
        return positions.record_order_fill(
            conn,
            manual_order_id=manual_order_id,
            ticker=ticker,
            filled=filled,
            sent_price_tenths=fill_price_tenths,
            now_ms=now_ms,
            placed_ms=placed_ms,
        )
    finally:
        conn.close()
