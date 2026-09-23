# ADR 0169 — A combination bought by RFQ is recorded, and `/hedge` names where its stake came from

Date: 2026-09-18
Status: Accepted
Issue: #69 (build, no decision needed). Amends ADR 0160 (Amendment 2's split),
extends ADR 0164/0165 (the RFQ path).

## Context

`POST /api/parlays/rfq/accept` has been armed since 2026-09-17
(`RFQ_ACCEPTS_ARE_DRY_RUNS = False`, ADR 0165 Amendment 1, Joe's #61 answer).
It is the newest surface on the desk that spends real money on one tap.

`accept_quote_for_joe` wrote two things: `record_accept_intent` before the
venue call and `record_accept_outcome` after it, both `UPDATE
combo_rfq_quotes`. It wrote no position. `record_position` had exactly two
callers — `routers/hedge.py:73` (a slip Joe types in by hand) and
`routes.py` `_record_combo_position` (the order path) — and the RFQ accept was
neither.

So a combination bought through this door:

- was not watched by `/hedge`, which can only watch `parlay_positions`;
- was reported back to Joe by `VenueCoverageBanner` as *a Kalshi combination
  at the venue that is not recorded here* — the desk flagging its own
  purchase as a mystery;
- could never be scored against the closing line, because nothing held its
  entry.

ADR 0071 makes the record a byproduct rather than a target. It is still the
thing that makes CLV measurable, and a bet the tool places and does not
record is one the tool can never learn from.

## Decision

### 1. An `executed` acceptance writes the position

`_record_accepted_position` runs after the outcome is recorded, only when
`filled and not dry_run`.

- **`executed` only.** `QUOTE_FILLED_STATUSES` is `(executed,)` and stays so.
  The first live accept went `accepted` → `confirmed` in 32 ms and
  `cancelled` 1.7 s later with no money moving; a position written on
  confirmation would have been a holding that never existed.
- **The ticker and legs come from the ask**, not the quote.
  `combo_rfqs.selected_legs` is stored in `parlay_lookups`' own shape
  precisely so `parlays.legs_for_position` parses it with no second parser.
- **The size is the quote's own `contracts`**, because a maker's quote is
  all-or-nothing at the size asked for: an executed quote filled at that size
  or did not fill.
- **Both halves of `/hedge`'s join key are set** (`combo_ticker`,
  `placed_ms`, from the one `now_ms`), so this reads as *bought through the
  desk* rather than *typed in by hand* — the distinction issue #56 bought.

### 2. Four refusals, and none of them resolves to a plausible number

The size is validated rather than trusted. Absent, non-finite, non-positive,
or finer than a tenth of a cent → no position. The last needs saying: a
settlement is a whole 1000 tenths a contract, so a size carrying more than two
decimals cannot be reproduced in the unit the table stores. It is refused, not
rounded, in the same direction as `fractional_venue_fill_count` on the order
path. Unreadable legs and a missing ask row refuse the same way.

**`None` is never an error the caller may hide.** It means the money moved and
nothing is watching it, so the accept's own words say
*“This one is not on the watch list”* — silence would read exactly like a bet
under watch.

**Nothing on this path raises.** The trade is done and the money is spent; a
bookkeeping failure must not turn a completed purchase into a 500 that tells
Joe nothing happened.

### 3. An eleventh `stake_basis` reason, `rfq_accept`

This is the half the ticket did not anticipate, and it is the reason the
slice is not just the writer.

An RFQ position has **no `manual_orders` row by construction**, and its join
key *is* formed. Left alone, ADR 0160's `stake_basis_for` would have returned
`no_order_row` — which Amendment 2 defines as *the key was formed and matched
nothing, which is a bookkeeping gap*. The desk would have reported a designed
state as a defect, on every RFQ position, for as long as the path exists.
That is exactly the conflation issue #56 removed nine days ago, reappearing
on a second path.

`stake_bases` therefore takes a second read — bounded by the same two lists
as the order read, so it cannot widen into a scan as `combo_rfq_quotes` grows
— and asks which keys an executed, non-dry-run acceptance answers.

It resolves **`as_recorded`, not `venue_fill`**. The stake is the accepted
quote's ask times its size, before fees. The one executed accept this repo
has measured filled at exactly its quoted price
(`docs/measurements/2026-09-17-accepted-side-names-the-makers-side.md`), which
is **n = 1 and is not made into a rule here**. Upgrading this to `venue_fill`
needs the venue's own fill for an RFQ, which nothing reads yet.

Joe's sentence, in the gloss: *“You bought this by taking a maker's quote,
which places no ordinary Kalshi order — the stake above is the price you
accepted times the size quoted, before fees.”*

### 4. What this does not establish

- **Nothing about what Kalshi charged.** See above; that is the whole reason
  for `as_recorded`.
- **Nothing about a real venue's lifecycle.** The fake answers the statuses it
  is given. That `executed` is the only filling status is pinned by the
  2026-09-17 measurements, not by these tests.
- **Nothing about the fee.** No entry fee is included in the written stake,
  as on the order path; ADR 0145's `combo_entry_fee_tenths` is sunk at read
  time and E3 is unchanged by this.
- **No backfill.** Any RFQ fill before this ships has no position and does
  not get one — the same refusal ADR 0160 made, for the same reason.

## Mutations

Every guard was disabled and the suite watched. Twelve run, eleven red; the
survivor is recorded rather than quietly removed.

| # | mutation | result |
|---|---|---|
| M1 | never write the position (the ticket's own) | RED — 7 failed |
| M2 | write on `confirmed` as well as `executed` | RED |
| M3 | write on a dry run too | RED |
| M4 | guess a missing quote size as one contract | RED |
| M5 | round a size finer than a tenth instead of refusing | RED |
| M6 | let a bookkeeping failure raise into the completed trade | RED¹ |
| M7 | stay silent when a fill could not be recorded | RED |
| M8 | drop the `rfq_accept` reason (report a gap) | RED |
| M9 | let a dry-run acceptance explain a stake | RED |
| M10 | let a quote that never executed explain a stake | RED |
| M11a | let one acceptance explain every position on screen | RED¹ |
| M11b | drop the `key in wanted` filter alone | **GREEN** |
| M12 | claim the stake IS the venue's number | RED — 3 failed |

¹ Green on the first run. M6 was undefended because every existing refusal
test returned `None` politely rather than raising; a quote priced at 1000
tenths makes `ticket_refusal` reject the ticket and drives the `except`.
M11a was undefended because the only crossed-key test changed the ticker,
which the SQL filter caught before the loop — the real claim needed a second
position on the same screen with no acceptance behind it.

**M11b is decoration and the code now says so.** The filter drops only keys
that match no open position, and such a key is never looked up below, so
removing it changes nothing. It mirrors the order read's identical line to
keep the two halves of the function reading the same way. The claim that
matters — one acceptance explains *one* position, not the screenful — is
M11a, and it is tested.

## Consequences

- `record_position` has three callers. `_order_key`'s docstring said two.
- The vocabulary anchor moved from ten reasons to eleven, and
  `tests/test_the_hedge_card_names_the_fallback_reason.py` now names both
  additions and their decisions. A twelfth needs the same.
- `/api/parlays/rfq/accept` returns `position_id`, which the screen does not
  render yet; the words carry the only part Joe needs.
- The open question this leaves: whether an RFQ fill's true charge is
  readable from `/portfolio/fills`, which would upgrade `rfq_accept` to
  `venue_fill` and close E2 on this path as ADR 0160 closed it on the other.
  Not opened as a ticket — it is a measurement with no decision in it.

---

## Amendment 1 — 2026-09-18, same day: "all-or-nothing at the size asked for" is asserted, not measured

A `kalshi-platform` review of this commit found that §1's ground for taking
the size from the quote — *a maker's quote is all-or-nothing at the size
asked for, so an `executed` quote filled at that size or did not fill* — is
**stated in two docstrings and measured nowhere.**

The only executed accept this repo has was fired with `contracts = 1` on the
**RFQ**, not against a maker's own quoted size, and its measurement document
says in terms: *"Nothing here speaks to slippage, partial fills."*
`rest_remainder: False` on create governs the **requester's** remainder, not
the maker's fill.

If a quote can part-fill, the position this ADR writes is wrong in both size
and stake, `/hedge` sizes a hedge against a holding Joe does not have, and
**nothing downstream can ever catch it** — the stake basis is `as_recorded`,
so there is no reconciliation to fail.

The fix is small and settles three things at once: one
`GET /portfolio/fills?ticker=...` after `executed`, before the position is
written. It measures the partial-fill question, records the venue's own size
and price, and upgrades `rfq_accept` to `venue_fill` — the basis ADR 0160
already prefers everywhere else.

**This ADR's closing paragraph left that as "a measurement with no decision
in it" and did not ticket it. That was wrong**: the decision is what to record
when the venue's fill disagrees with the quote, and until it is taken this
path records the quote and calls it the holding. It is now **#74**.

Nothing in §1–§3 is retracted. What changes is that §1's size is a *claim
about the venue* carrying no measurement behind it, and it is labelled as one
here rather than left reading as established.

---

## Amendment 2 — 2026-09-18: the question is two questions; the decision stands and the ground is narrower

Amendment 1 said §1's size claim was asserted rather than measured, and
ticketed the measurement as **#74**. That measurement has now been taken:
`docs/measurements/2026-09-18-can-an-rfq-quote-partially-fill.md`.

**It splits into two questions, and conflating them is what made §1's sentence
wrong while its practice was right.**

**1. Can a requester accept fewer contracts than the quote offers? YES by rule,
NO on the endpoint this repo uses.** Kalshi's rulebook says it outright — Rule
5.3(b)(c), *"A Requestor may either accept the Quote for its full size, or
accept some number of contracts in the quote less than the full size"* — and
FIX exposes it as an optional `OrderQty`. But the REST accept body
`accept_quote` sends has **exactly one property, `accepted_side`**
(`backend/kalshi/rfq.py`, verified against the source), and no quantity field
exists. So a REST accept is for the whole quote **structurally, not because the
venue forbids less**.

**2. Can that accepted quantity then execute short? The documentation is
SILENT.** Nothing in the REST reference, the FIX RFQ page, the RFQ guide, the
WebSocket `communications` schema or the Fills schema says an accepted quote
can fill for fewer contracts — and nothing says it cannot. The status enum has
no partial state and `quote_executed` carries no contract count at all.

**Against that silence, the record now answers: 11 of 11.** Every `executed`,
non-dry-run acceptance the live database holds — a census of the whole
population, not a sample — filled at exactly the quoted size, at exactly the
quoted price, as exactly one fill row, 1.1–3.9 s after the accept. Quoted sizes
span 1.51 to 227.27 contracts, so it is not degenerate at size 1. And across
every row of `fills`, no `venue_order_id` appears on more than one fill row:
no order in this record has ever been split.

### What changes here

**§1's decision — size the position from the quote — stands, and is now
measured rather than assumed.** What is retracted is only its *stated ground*.
Replace *"a maker's quote is all-or-nothing at the size asked for"* with:

> **The REST accept carries no quantity, so it is for the full quote; and 11 of
> 11 executed acceptances have filled whole.**

That is narrower in both halves, and both halves are checkable.

**#74's build half is still worth building**, and for a better reason than
Amendment 1 gave: not because the size is unknown, but because `rfq_accept`
should become `venue_fill`, and because 11 of 11 is a census of one contract
family over eleven and a half hours, not a property.

**The measurement also names a better link than the time-window join it had to
use.** The RFQ guide matches quote-execution fills on `rfq_creator_order_id`
(requester) / `creator_order_id` (maker), private fields on the Quote object
that `parse_quotes` reads **neither** of, and `GET /portfolio/fills` accepts
`order_id` as a query parameter. Keeping `rfq_creator_order_id` turns a
ticker-plus-window join into an identifier join. There is also an unexplained
second size field, `contracts_fp`, on the captured payload beside
`no_contracts_fp`; nothing reads it and no page explains it.

### And a second REST-vs-FIX divergence, the same shape as `accepted_side`

Amendment 1's reading of `rest_remainder` is half right. REST says it rests the
remainder after execution. FIX tag 21015 says the same on the **requester's**
QuoteRequest — but on the **maker's** Quote it reads **"Allow partial fills
(default: N)"**, the only occurrence of "partial fill" anywhere in Kalshi's RFQ
documentation, defaulting to N on both sides.

**That is the second time a REST page declined to say something the FIX page
states outright, on this same endpoint, in two days.** The first cost a session
and nearly a 250x mis-buy (`accepted_side`). The durable rule: **on the RFQ
path, read the FIX page before believing the REST reference is complete.**

### One thing left open, and it is a question for Joe

Rule 5.3(b)(e) says the RFQ pair enters the book as ordinary limit orders that
*"behave identically to a standard order"*, and Rule 5.10(a) says a partially
filled standard order **rests on the book at its limit price**. Chained, a
short-filled RFQ order would leave **a resting offer** — the one behaviour
ADR 0115 removed on Joe's word, because he pays the ask and does not make
offers. It is an inference across two rules, never observed, and not decidable
from the documentation or from any read of the existing record. Ticketed
rather than resolved here.

**Question for Joe: accepting a quote might leave a resting offer on the book —
guard it, or accept the risk? — #78**

**#78 answered 2026-09-23: (a) accept the risk.** No guard at accept time.
Joe's reasoning: 11 of 11 executed accepts filled whole, and the venue's own
default is against partial fills. ADR 0183 §2.
