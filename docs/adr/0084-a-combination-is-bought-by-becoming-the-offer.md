# ADR 0084 — A combination is bought by becoming the offer

Date: 2026-08-30
Status: accepted

## Context

Joe asked for something the desk could not do: pick a parlay card, choose a
price, and have the purchase happen in the cockpit rather than by re-selecting
legs by hand in the Kalshi app.

The desk already had a buy control (`ManualTicket`, ADR 0073) and it was
unreachable on a combination for a structural reason. It renders only on
`status === "priced"`, and it sends an **immediate-or-cancel** order at the
live ask. A combination has no live ask: **no combination book this repo has
read carried a resting YES bid — 40 of 40, across three runs on two dates**
(ADR 0012 §5). So `Price on Kalshi` came back `book_empty` every time, the buy
control never rendered, and had it rendered, an IOC against an empty book would
have filled nothing and died.

Kalshi's derived-ask identity is why the app can still show a number: the list
ask is the complement of a resting NO bid, not a quoted offer. You can enter
and you cannot exit.

## What was measured first

Nothing here was designed on the assumption that a combination behaves like an
ordinary market. `scripts/probe_resting_combo_order.py` was written and run
against the live account on 2026-08-30, and it cost less than a cent.

**A combination accepts a resting bid.** A 1-contract GTC buy at 0.5c returned
`201`, `remaining_count 1.00`, and the orders list showed it `resting`. It was
then cancelled: `reduced_by 1.00`, `fill_count 0.00`. Nothing filled, nothing
was spent.

Three mechanics were discovered on the way, each of which the desk now gets
right because it was observed rather than assumed:

1. **Kalshi shards its matching engines and collateral does not follow an
   order across them.** The docs state it: *"Programmatic traders must
   preallocate collateral on a given exchange shard before order placement."*
   The account held $21.41 and a 2c bid was refused `insufficient_balance`,
   because the combinations shard held $0.01:

       shard 0   $21.4020   everything else, including WNBA
       shard 1   $0.0100    Exotics — the KXMVE combinations this desk mints
       shard 2   $0.0000    Crypto
       shard 3   $0.0000    Sports: tennis and baseball only, moved 2026-08-24

2. **The cancel carries its shard as a query parameter.** Without it the venue
   returned `404 not_found` for an order the orders list showed as `resting`
   that same second; `?exchange_index=1` returned 200. The endpoint has no
   ticker to auto-route from.

3. **The query string stays out of the signature.** A hand-rolled probe helper
   that folded it in got `401 INCORRECT_API_KEY_SIGNATURE`. The production
   client already excluded it; a test now pins that, because query parameters
   reach the order path for the first time here.

A fourth observation is recorded and **not** acted on: the same order shape on
a shard-3 baseball market is refused `user_not_found`, an error Kalshi
documents nowhere. The account reads a balance on that shard but cannot place
an order there. Sports moved to shard 3 six days before this was written, which
is why the account's 33 older sports orders are all on shard 0.

## Decision

**The desk buys a combination by resting Joe's own bid at his own price.**

- `POST /api/parlays/bid` prices the card through the existing lookup path —
  the same `price_card_on_kalshi` the price button calls, so leg validation,
  collection choice, minting and the venue's leg echo have exactly one
  definition — then rests a `good_till_canceled` limit buy on the ticker that
  came back.
- **The price is Joe's and is never moved towards fair value in either
  direction.** The card's fair value renders beside the field as a reference.
  Ranking by the consensus-vs-Kalshi gap remains forbidden (ADR 0071 §2.5);
  showing it on the row it belongs to remains fine.
- **The stake ceiling is the one the hand-bet path already has** —
  `$3.00`, the top of the range Joe named. One ceiling, not two: a second,
  larger ceiling reachable through a new route is the cap being raised by
  accident.
- **The affordability check reads the shard's balance, never the account
  total.** A caller trusting $21.41 believes a $2 bet is affordable while the
  shard that would pay for it holds a penny. The refusal names the shard, the
  amount on it, and where to fix it.
- **The bid is withdrawn automatically when the first leg kicks off.**
  `backend/bid_watch.py` reads `cancel_after_ms` every minute. Cancelling is
  the safe direction: the worst case of an unnecessary cancel is a bet placed
  again by hand; the worst case of a fill after kickoff is a position on a
  game in progress that a combination gives no way to exit.
- **`COMBO_ORDERS_ARE_DRY_RUNS` ships `True`.** This is the first order shape
  in the repo that can fill while nobody is watching, so it rehearses dry and
  arming it is a one-line commit of its own — the `MANUAL_ORDERS_ARE_DRY_RUNS`
  convention (ADR 0063).

### What the tool will not do

**It does not move money between exchange shards.** The endpoint exists
(`POST /portfolio/intra_exchange_instance_transfer`) and Kalshi also offers a
standing target allocation that rebalances every ten seconds. Both are the
operator's to set, at https://kalshi.com/account/exchange-indexes, for two
reasons: a transfer is a financial movement rather than a bet, and Kalshi's own
docs warn a cross-shard transfer runs *"in up to three non-atomic steps"* whose
completed steps are not undone on failure.

## Boundaries

- **`gate.py` may never read `combo_orders`.** A resting bid is Joe's
  discretion, not evidence; the live-trading interlock counts neither. The same
  boundary `manual_orders` has (ADR 0063).
- **`combo_orders` is separate from `manual_orders`.** Those rows are all IOC
  and therefore all finished, and `manual-orders-audit` counts them as such. A
  row that can still be working would make every count in that census
  ambiguous.
- **No fee-net figure is computed anywhere on this path.** ADR 0046 leaves the
  combination fee model unverified, and Kalshi's 2026-08-22 changelog puts the
  combo maker multiplier at **0.5** against `core/fees.py`'s 0.25 —
  unreconciled, and now written down.

## What this does not establish

- **That a bid will ever fill.** The same emptiness that makes a resting bid
  the only way in makes it unlikely to be taken. No screen on this path
  promises otherwise: the word is "resting", and every surface that shows it
  says *nobody has to take it*.
- **That the shard map is stable.** It is Kalshi's and it is moving. The desk
  reads `exchange_index` off the market each time rather than trusting the
  constant, because the docs call that field the authoritative source of truth
  and baseball moved shards six days before this shipped.
- **That the parlay is a good bet.** ADR 0038 closed the hunt; this is a
  betting desk feature (ADR 0071), and the card's fair value is what the
  sportsbook consensus implies, not a claim that Kalshi is wrong.
