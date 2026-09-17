# `accepted_side` names the maker's side — settled by one 0.4-cent trade

Date: 2026-09-17
Authorised by Joe the same day: *"a, arm it and fire the probe"* (#61 option (a)).

## The question

Kalshi's accept call takes `accepted_side`, and **no REST page says whose side
it names**. The reference defines it as "the side that was accepted". Only the
FIX page says it outright: *"BUY accepts the maker's NO quote."*

On a real quote the two readings are not close:

| reading | what Joe buys |
|---|---|
| `"no"` lifts the maker's NO bid — ours | **YES at 0.40c** |
| `"no"` means "I want NO" | **NO at 99.60c** |

A green test suite cannot separate these: both are the code doing what it was
told. Only a trade can.

## Method

One accept, on `KXMVECROSSCATEGORY-SHARD1-S20264D4910BB8C7-D9825147886`,
sized `contracts = 1`.

Target chosen so the answer could not be ambiguous and the downside was known
before anything was sent: that combination was quoted at **YES 0.4c against NO
99.6c**, so the two readings are ~250× apart and one contract bounds a wrong
answer to about $1 against a $5.79 balance. Size was fixed in `contracts`
rather than a dollar target, because a dollar target lets the venue choose the
size.

## Result — our reading is correct

```
sent   accepted_side = "no"   against a maker NO bid of 0.9960
accepted_ts   17:53:28.0
confirmed_ts  17:53:28.107672     (maker agreed, ~100ms)
executed_ts   17:53:29.250712     (~1.14s after confirmation)
status        executed

fill: side "yes", action "buy", yes_price_dollars "0.0040", is_taker true
balance 5.7899 -> 5.7856          = $0.0043 (price 0.40c plus ~0.03c fee)
```

**`accepted_side = "no"` buys YES.** `ACCEPT_SIDE_FOR_BUYING_YES = "no"` is
confirmed against the venue, not inferred from FIX.

## The first attempt, which did not execute — and was worth more than the second

An earlier run on the same market, minutes before:

```
accepted_ts   17:50:29.539
confirmed_ts  17:50:29.571
cancelled_ts  17:50:31.250        status: cancelled
no fill · position unchanged · balance unchanged
```

It watched only until `confirmed`, treated that as done, and then withdrew the
RFQ. **`QUOTE_FILLED_STATUSES` included `confirmed` at the time**, so the desk
would have told Joe the trade went through on a trade that never happened.

Two things follow, and both are now in the code:

1. **Only `executed` is a fill.** Confirmation is the maker agreeing;
   execution is a separate step about **1.1 seconds** behind it, and a quote
   can be cancelled in between.
2. **Do not withdraw an RFQ you have just accepted.** Whether the withdrawal
   caused the cancellation or merely coincided with the RFQ's own ~2-second
   expiry is **not established** — the second run simply did not withdraw, and
   executed. One trial each way is not a controlled comparison and this
   document does not claim one.

## What this does NOT establish

- **Not that the accept path is safe at size.** One contract at 0.4c. Nothing
  here speaks to slippage, partial fills, or a maker's behaviour on a quote
  worth real money.
- **Not the fee model.** $0.0003 on a $0.0040 contract is one observation at
  the extreme bottom of the price range, where the fee formula is least
  representative. ADR 0046 stands.
- **Not that execution always follows confirmation in ~1.1s.** n = 1. The
  watch window is 10s against that, deliberately generous.
- **Not what a maker's non-confirmation looks like.** Still undocumented, and
  the one cancellation observed followed a *confirmation*, which is a
  different thing.
- **Nothing about `/portfolio/orders` or `/portfolio/positions`.** The fill
  appeared in `/portfolio/fills` as documented; the other two were not checked
  for this trade.

## Cost of the whole exercise

**$0.0043.** Two accepts, one executed. Joe now holds one more contract of a
combination he already held.
