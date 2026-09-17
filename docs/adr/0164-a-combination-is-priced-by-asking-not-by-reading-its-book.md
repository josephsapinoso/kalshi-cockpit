# ADR 0164 — A combination is priced by asking, not by reading its book

Status: accepted
Date: 2026-09-17

Supersedes the pricing surface chosen in ADR 0012 and ADR 0070 for
combinations. Does **not** supersede ADR 0115 (the bid path stays disarmed;
this is the opposite of resting an offer). Narrows ADR 0085's "the parlay desk
prices, it does not buy" — it still does not buy, but it can now find out the
price.

## Context

**Joe tried to buy a combination through the cockpit on 2026-09-17 and was
refused.** The screen told him: *"nothing is resting in its book — no one is
offering to sell this combination, so there is no price you could actually pay
right now."* He said he can buy combinations on kalshi.com and that the
cockpit is merely *faster*. He was right and the desk was wrong.

**Kalshi prices combinations by RFQ (Request for Quote).** You ask; makers
answer privately; you accept one. The trade prints to the public order book
*afterwards*. So a combination's book is empty **by design between requests**,
and `/communications/rfqs` appeared nowhere in this repo.

### What was measured, 2026-09-17

On the exact combination the desk refused (PITT / ATL / LV,
`KXMVECROSSCATEGORY-S20264E0CD4DDEA6-BBE0304F0C9`):

- Order book `{"no_dollars": [], "yes_dollars": []}`, read three times.
- **27 RFQs on that ticker that day**, filter verified honoured.
- Exchange-wide: **100 RFQs in 25 minutes across 79 combination tickers.**
- One RFQ fired with Joe's authorisation drew **at least three maker quotes
  within ~107ms**: best YES ask **$0.5930** against the card's own fair value
  of **$0.57805**, makers **3.80c apart**. Withdrawn, nothing accepted.

`docs/measurements/2026-09-17-a-combo-rfq-returns-a-real-takeable-price.md`.

### What this overturned

- `POST /api/manual-orders` **check 8** (`depth_at_ask`) tests the wrong
  surface for a combination. Zero lit depth is the normal state.
- The Parlays tap census (ADR 0156) counts lit-book presence and read to Joe
  as "this combination cannot be bought". It never supported that.
- **CLAUDE.md's "combinations are enter-only"** rests on `yes_dollars` empty
  on 40 of 40 books. That measured the lit book. **Exit via RFQ has never been
  tested, so the claim is unsupported — not refuted, unsupported.**
- The standing paradox — *0 of 61 combinations had an ask, yet 51 of 52 of
  Joe's fills were takers* — is explained. Those were RFQ executions printing
  to the book afterwards, not takes off a resting ask.

## Decision

**1. The desk asks.** `backend/kalshi/rfq.py` creates an RFQ, reads the quotes
it draws and withdraws it. `POST /api/parlays/rfq` orchestrates;
`<AskTheMarket>` renders where the dead end was.

**2. It asks only about a combination this desk already minted.** The caller
names a ticker and a target cost; the legs, the collection and the fair value
come from that ticker's own `parlay_lookups` row. A money-adjacent route that
takes the legs and the fair value from its caller is one where the screen
decides what the server believes.

**3. Quotes are recorded, because this is the only copy.** They vanish from
the venue the moment the RFQ is withdrawn — measured, a re-read returned zero.
`combo_rfqs` and `combo_rfq_quotes` (schema v45). The order book is read at
the same instant and stored beside them, so the two surfaces can be compared
later without a second experiment.

**4. Nothing accepts.** Creating an RFQ obligates nothing. Acceptance is the
spend and is **not built**; the screen says so in those words. Joe has chosen
its guard in advance — **option (ii): show the quote, second tap to confirm**,
no typed ceiling, because an RFQ hands you the price *after* you ask and a
ceiling typed in advance is guessing at a number you are about to be told.

**5. `rest_remainder` is pinned `False`.** Resting the unfilled remainder
would reintroduce the offer-making ADR 0115 removed on Joe's word.

**6. The screen may show the quote beside fair value and may never order by
their difference.** That gap is the consensus-vs-Kalshi gap under another
name and `beta = -0.141`. Tests pin "edge", "cheap" and "good price" absent.

### Two venue facts that cost time and are written down

- **`exchange_index=1` is required on every RFQ write.** Without it the create
  returns a Kalshi-JSON `404 not_found`, which reads as "retail keys cannot do
  this" and is not. `rest.py:78-84` recorded the identical failure for a
  shard-1 *cancel* on 2026-08-30; it was not generalised, and so it was paid
  for twice.
- **`market_ticker` and `rest_remainder` are required** on create, and the
  `mve_*` fields are *additional to* `market_ticker`. The API reference
  documents neither mve field; only the prose guide does.

## Consequences

- The empty-book branch is no longer a dead end, and the copy asserting
  nobody would sell was corrected in the same commit — copy naming a condition
  to wait for is falsified by fixing the condition.
- **Joe still cannot complete a purchase in the cockpit.** He can now learn
  the price without leaving it, which is most of the speed he asked for and
  not all of it. Accepting is the next slice and needs arming.
- Check 8 is still wrong for combinations and is **not** changed here. It
  guards the order-book path, which the RFQ path does not use; rewriting it
  belongs with the accept slice, where it will matter.
- A new outward-facing write exists on the live instance. It is auth-gated,
  demo-refused, and cannot spend.
- **The exit question is now open rather than settled.** "Enter-only" was
  never measured against the surface combinations actually trade on. Testing
  it needs a sell-side RFQ on a position Joe holds — his call, not a session's.
