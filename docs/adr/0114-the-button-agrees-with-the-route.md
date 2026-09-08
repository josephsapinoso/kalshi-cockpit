# ADR 0114 — The buy button agrees with the route, and the removed cap comes off the screen

Status: accepted
Date: 2026-09-08

## Context

ADR 0112 and its Amendment 1 removed, on Joe's explicit word, every ceiling
the desk placed on the size of a hand bet: the per-bet cap (~$2.14, 10% of the
observed balance), the `$3.00` spend cap, the daily-loss switch, the cool-off,
the typed order token, and finally the total-exposure ceiling. `POST
/api/manual-orders` obeyed the same day.

**The screen did not.**

`GET /api/manual/market/{ticker}` serves `authorised_contracts` per side, and
`ManualTicket.tsx` disables the Confirm button above it:

```
(ceiling === null || contracts <= ceiling)
```

That number was computed by `_manual_cap_dollars`, which returned

```
min($3.00 spend cap, 10% of the observed Kalshi balance)
```

— both of the caps Joe had removed by name. On a 90c market it authorised
**three** contracts. The route would have accepted **two hundred and fifty**.

Three further consequences followed from the same root:

1. Two 422 refusals on the money path told him *"what bounds the BET is the
   $3.00 spend cap, checked below"*. Nothing was checked below. The desk
   promised a brake it did not have, in the message a real-money refusal hands
   him.
2. `authorised_contracts` was `None` whenever the account balance had never
   been observed, which the ticket renders as a refusal. Commit `ebbb809` made
   POST accept exactly that state — so the fix that removed the exposure
   ceiling **widened** the mismatch it was part of closing.
3. The ticket's own copy called every bound *"your per-bet cap"*, which by then
   was the one thing none of them was.

This is the failure this repo has now named four times — *one predicate with
two spellings, and the screen believing the wrong one* — running in the
direction it had not run before. The three earlier instances were a screen
promising buying that was not happening. This one **refused betting that was
permitted**, on the only path that spends real money, for the thirteen days
between the caps coming off and this ADR.

It was found the same evening `manual_orders` took its first two rows.

## Decision

**`authorised_contracts` is built from the constraints the POST route actually
applies to size, and from nothing else.** Those are:

| | bound | why it is not a cap of ours |
|---|---|---|
| check 4 | the structural ceiling for the ticker class — `COMBO_MAX_CONTRACTS` (250) or `MANUAL_ORDER_MAX_CONTRACTS` (500) | structural, and ADR 0073's reason is the EXIT, not the bet |
| check 8 | the depth resting at the ask | an IOC for more than the book holds part-fills at best |
| check 9a | what the market's own exchange shard can pay for | **the venue's rule.** Kalshi keeps collateral per shard and will not move it for an order |
| — | the price grid, via `OrderRequest` refusing an off-grid count | the venue's tick structure |

`_manual_cap_dollars` is deleted. `max_spend_dollars` is no longer imported by
the route.

**If a ceiling of ours ever reappears in that function it is a restored brake,
and ADR 0112 §5 reserves that to Joe.**

### The wire says WHICH bound produced it

`authorised_binding` is new on each side: `structural`, `depth`, `shard`,
`price_grid`, `shard_unreadable`, `no_ask`, `no_price_grid`.

This is not decoration, and `_manual_cap_dollars`'s own docstring is the
argument for keeping it — *"a refusal that does not say which bound it hit
sends the reader to fix the wrong thing."* Waiting for the book to thicken and
moving money between Kalshi shards are different remedies with different costs.
The ticket renders each in plain words, because Joe has asked to be taught the
terms rather than handed them.

### Unreadable still refuses, and it refuses the same way POST does

An unreadable shard balance, or a market that does not say which shard it
settles on, yields `None` and the ticket renders a refusal — because check 9a
would 502 or 422 on exactly those states. `0` is a real shard, so an absent
`exchange_index` is an unknown and never a guess.

The shard balance is read **once per ticket, not per side**: the collateral
belongs to the market, not to the side. A failed call is caught rather than
allowed to 503 a read-only screen; the ticket still renders the ask and the
depth, and says why the count is missing.

## Consequences

**The button now lets him bet at a size the desk previously refused**, up to
what the book and his shard can carry. That is the intended state — ADR 0112
§4 says the cockpit will not stop him at any size his Kalshi collateral can pay
for — and it is worth stating plainly rather than burying: this change makes it
possible to lose more money in one tap than yesterday. It does so by removing a
brake that was already supposed to be gone, not by deciding anything new.

**The screen and the route can no longer drift apart by construction**, because
they are computed from the same three bounds rather than reconciled once by
hand. `test_the_count_is_never_more_than_the_route_would_take` drives both
surfaces and would catch it from either direction.

**One extra Kalshi call per ticket open**, for the shard balance. No odds
credits are involved — this is the exchange API, not the odds feed — so it
touches nothing in the credit budget frozen until 2026-09-14.

### Two tests were re-pointed, and both had preserved the error

`test_a_combination_keeps_a_tighter_structural_ceiling` asserted the string
`"spend cap"` was **present** in the combination refusal, and
`test_the_per_bet_cap_names_itself_when_it_binds` asserted `"your per-bet cap,
not your typed amount"` was present in the ticket. Both went green every day
the copy was false. This is precisely the failure `backend/parlays.py:105-111`
records about `"40 of 40"`: **the binding preserved the error instead of
catching it.**

Both now pin the dead phrase **absent** and the true bound present. Neither was
deleted, because the claim underneath each is still worth holding: a refusal
must name what actually stops him, and a silently trimmed order must say what
trimmed it.

The second guard permits a correction note to quote the phrase it strikes —
the comment above the ceiling quotes `"your per-bet cap"` to say what it
replaced — so the rendered sentence is pinned rather than the bare phrase. Same
allowance `tests/test_combo_book_depth_claims.py` makes, for the same reason.

### Verified by disabling

Restoring the old bound as `authorised = min(authorised, int(3000 // ask))`
turns **five** of the seven new tests red, including the agreement property.
Green with it, red without it.

## What this does not do

- It does not touch the engine. `orders.reserve_order` still caps it, on
  ADR 0112 §3's scoping, and `ORDERS_ARE_DRY_RUNS` is still `True`.
- It does not touch `gate.py`, which still never reads `manual_orders`.
- It does not touch anything under `backend/odds/`, frozen until 10:00Z on
  2026-09-14.
- It decides nothing about whether Joe should fund shard 0. That is still his,
  and the refusal now names the shortfall and the reallocation link.
