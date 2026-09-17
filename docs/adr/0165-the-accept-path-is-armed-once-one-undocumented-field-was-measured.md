# ADR 0165 — The accept path is built, and armed once one undocumented field was measured

Status: accepted
Date: 2026-09-17

Follows ADR 0164, which built the asking half. Implements Joe's **B = (ii)**
from #59. Does not supersede ADR 0115 — an RFQ acceptance lifts a maker's
resting bid, which is paying an ask, not making an offer.

## Context

ADR 0164 gave the desk a price on a combination. It could not take it. Joe
asked for the other half in three words: *"build the accept path."*

The venue's contract, established from Kalshi's reference:

    PUT /communications/rfqs/{rfq_id}/quotes/{quote_id}/accept
    body {"accepted_side": "yes" | "no"}     -> 204 No Content

A 204 is **not a fill**. The maker then has a confirmation window — 3 seconds
on a combination, which is a High Volatility Market, against 30 elsewhere —
and **only `executed` means money moved** — this ADR originally said
`confirmed`/`executed`, and the first live probe disproved it (Amendment 1).
There is no `quote_confirmed` WebSocket event, so REST polling is the only
way to see any of it.

### The one thing that is not settled

`accepted_side` names a side, and **no REST page says whose**. The reference
defines it as "the side that was accepted". Kalshi's FIX page says it
outright — *"BUY accepts the maker's NO quote and SELL accepts the maker's
YES quote"* — and that reading matches the derived-ask identity this repo
uses everywhere (`yes_ask = complement(no_bid)`).

On the quote captured 2026-09-17 (`no_bid 0.8920`, `yes_bid 0.0760`):

| reading | what Joe buys |
|---|---|
| `accepted_side: "no"` — ours | **YES at 10.8c** |
| `accepted_side: "yes"` | **NO at 92.4c** |

**Nine times the spend, on the opposite contract.** A green test suite cannot
tell these apart, because both are the code doing exactly what it was told.

## Decision

**1. Built, and `RFQ_ACCEPTS_ARE_DRY_RUNS = True` until measured.** The route
ran end to end and sent nothing. Arming was Joe's, the way
`MANUAL_ORDERS_ARE_DRY_RUNS` was (ADR 0112 §5), and its precondition was
named: one minimum-size accept read back out of `GET /portfolio/fills`,
checking side and price against `1 - no_bid_dollars`. That was **#61**, and
it was answered and spent the same afternoon — **see Amendment 1.**

**2. The screen refuses rather than offering a dead button.** `accepts_are_armed`
travels with the *price*, so the control says what it does before it is
tapped. A button labelled "Take it" that silently does nothing is this repo's
named failure — one predicate with two spellings — and it has run three times.

**3. No typed ceiling (B = (ii), Joe's own correction from (i)).** An RFQ
hands you the maker's price after you ask, so a number typed in advance is a
guess at it. The guard is instead that **the server reads the price from its
own record of the quote**: not from the request, which carries no price, and
not from a fresh venue read, which could have moved. What is accepted is what
was displayed.

**4. The RFQ is now held open by default.** Withdrawing destroys the venue's
copy of every quote, so a screen that shows a price and then asks for
confirmation must keep the request alive in between. `hold_open=False`
remains for a price nobody intends to take.

**5. An accept is never retried.** Kalshi assigns `client_order_id` after
execution, so unlike `OrderRequest` there is no client-generated idempotency
key and nothing to deduplicate against. Therefore:

- The intent row is written **before** the venue call, so a lost response
  leaves a trail that can be resolved by reading.
- A failure in flight is reported as an **UNKNOWN**, not a refusal: *"it may
  still have reached Kalshi."* Calling it a failure would send Joe to place
  the bet a second time.
- A second tap on an accepted quote is **409**, not a replay.
- The refusal state offers **no retry button**, alone among this screen's
  states.

**6. `outcome_status` is NULL when unobserved.** What a maker's
non-confirmation looks like to a REST reader is not documented; `cancelled`
is a guess, and a guess must not reach the permanent record.

## Consequences

- Joe could not yet complete a combination purchase in the cockpit at the
  time of this decision — one line and one decision away, which is #61.
  **Amendment 1 closed both.**
- Schema **v46**: six nullable columns on `combo_rfq_quotes`. `accept_dry_run`
  is nullable rather than `DEFAULT 1` — NULL means "no acceptance attempted",
  and a default of 1 would claim a dry-run acceptance happened on every row
  already on disk.
- **The fee is not in the quoted price.** Kalshi's target cost includes taker
  fees by default, so contracts received are fewer than `target_cost / price`.
  Ground truth stays the `fee` on the fill, per the house rule.
- `check 8` (`depth_at_ask`) is still wrong for combinations and still
  untouched: it guards the order-book path, which this does not use.
- **Whether an executed combo lands in `/portfolio/orders` and
  `/portfolio/positions` is undocumented** — only fills are stated, joined on
  `rfq_creator_order_id`. Verify on the first real accept, because the
  `manual_orders` bookkeeping assumes order rows exist.


## Amendment 1 — armed, 2026-09-17

Joe answered #61 with **(a)** the same afternoon: *"a, arm it and fire the
probe."* The probe was fired and `RFQ_ACCEPTS_ARE_DRY_RUNS = False`.

**The question is settled by a trade, not by a document.** One contract on a
combination quoted at YES 0.4c against NO 99.6c — ~250x apart, so the answer
could not be ambiguous, and the downside bounded at about $1 before anything
was sent:

    sent accepted_side = "no"  against a maker NO bid of 0.9960
    accepted -> confirmed (~100ms) -> executed (~1.14s later)
    fill: side "yes", buy, yes_price_dollars "0.0040"
    balance 5.7899 -> 5.7856      total cost $0.0043

`ACCEPT_SIDE_FOR_BUYING_YES = "no"` is now measured, and decision 1 above is
discharged. `docs/measurements/2026-09-17-accepted-side-names-the-makers-side.md`.

### The first probe found a bug in this ADR's own code

An earlier run went `accepted` -> `confirmed` in 32ms and then `cancelled`
1.7s later, with no fill and no balance change. It had stopped watching at
`confirmed` and withdrawn the RFQ.

**`QUOTE_FILLED_STATUSES` included `confirmed`**, so the desk would have
reported a completed trade that never completed. Corrected to `("executed",)`
only, with a test that pins a confirmed-then-nothing quote as *not* filled.

Confirmation is the maker agreeing. **Execution is a separate step about a
second behind it**, and a quote can die in between. This is the shape this
repo keeps relearning: a state whose name sounds final is not evidence of the
thing it sounds like.

Whether withdrawing the RFQ *caused* the first cancellation, or merely
coincided with that RFQ's own ~2-second expiry, is **not established** — the
second run did not withdraw and did execute, and one trial each way is not a
controlled comparison. The product path no longer withdraws after accepting,
on the weaker ground that there is no reason to.

### What arming does and does not mean

- Joe can now buy a combination end to end in the cockpit. That was the
  request this whole line of work started from.
- It does **not** mean the path is proven at size: one contract at 0.4c is
  the entire live record, and nothing here speaks to slippage or partial
  fills on a quote worth real money.
- The ceiling-free design (B = (ii)) is unchanged: the server accepts the
  price it recorded showing him, and a second tap on the same quote is 409.
