# Can an RFQ quote partially fill? — two questions, and only one of them was ever open

Date: 2026-09-18
Issue: #74 (measurement half). Settles ADR 0169 Amendment 1.
Population: every `executed`, non-dry-run RFQ acceptance the live database holds.

## The answer

The question splits in two, and conflating them is what made ADR 0169's
sentence wrong while its *practice* was right.

**1. Can a requester accept fewer contracts than the quote offers?**
**YES by rule, NO on the endpoint this repo uses.** Kalshi's rulebook says it
outright — *"A Requestor may either accept the Quote for its full size, or
accept some number of contracts in the quote less than the full size"* (Rule
5.3(b)(c)) — and FIX exposes it as an optional `OrderQty`. But the REST accept
body this repo sends has **exactly one property, `accepted_side`**, and no
quantity field at all. A REST accept is therefore for the whole quote,
structurally. So ADR 0169 §1's phrase *"all-or-nothing at the size asked
for"* is **false as a statement about the venue and true as a statement about
our call.**

**2. Can that accepted quantity then execute short?**
**The documentation is SILENT, and the record says it never has.** No page in
the REST reference, the FIX RFQ page, the RFQ guide, the WebSocket
`communications` schema or the Fills schema says an accepted quote can fill
for fewer contracts than accepted — and none says it cannot. Against that
silence, this repo's own record now answers with **eleven of eleven executed
acceptances filling at exactly the quoted size, at exactly the quoted price,
as exactly one fill row, 1.1–3.9 seconds after the accept.**

**ADR 0169's decision to size the position from the quote stands and is now
measured. Its stated ground needs an amendment**, because "a maker's quote is
all-or-nothing at the size asked for" is contradicted by the rulebook on the
acceptance half and is undocumented on the execution half. The defensible
sentence is narrower: *the REST accept carries no quantity, so it is for the
full quote; and eleven of eleven executed acceptances have filled whole.*

**No venue call was needed for the measurement.** The question was answerable
from rows the repo already had, because `/portfolio/fills` is not sitting
unread — see §1.

## 1. The record already contained the answer

The ticket's premise was that `/portfolio/fills` "is sitting unread". It is
not. `backend/portfolio_poll.py:poll_fills` calls `client.fills(limit=200)` on
the five-minute portfolio cadence and mirrors every record into the local
`fills` table (`INSERT OR IGNORE`, one row per `fill_id`,
`source = 'venue_hand'`). The venue's own fill for every RFQ acceptance has
been landing in the database all along — it was never *joined* to the
acceptance that caused it.

Four places hold fill-shaped data; two of them bear on this question:

| table | what it holds | bears on partial fills? |
|---|---|---|
| `fills` | the venue's own `/portfolio/fills` records: `count` (REAL), `price_tenths`, `venue_order_id`, `filled_ms` | **yes — the venue's side** |
| `combo_rfq_quotes` | the maker's quote: `contracts` (REAL, read from `no_contracts_fp`), `yes_ask_tenths`, `expected_ask_tenths`, `accepted_ms`, `outcome_status` | **yes — the quoted side** |
| `manual_orders` (`venue_fill_count`, `venue_avg_fill_price_tenths`, `venue_avg_fee_dollars`; ADR 0143, schema v40) | the order path only. An RFQ acceptance places no ordinary Kalshi order and writes no `manual_orders` row — which is exactly why ADR 0169 needed an eleventh `stake_basis` reason | no |
| `parlay_positions` | the desk's own record of the holding, sized from the quote (`stake_basis = 'rfq_accept'`) | no — it is the number under test, not evidence about it |

The two that bear on it are joinable, but **nothing in the schema links them
directly**, so the join below is ticker plus a time window. §5 says what that
costs and how to remove it.

## 2. What Kalshi's documentation actually says

### 2a. Partial acceptance is permitted by rule and unreachable over REST

KalshiEX LLC Rulebook v1.29, Rule 5.3(b)(c) (and verbatim in the CFTC
self-certification filing "Pre-Execution Communications and RFQ Orders",
2026-01-30, Appendix A):

> A Requester may choose to accept one side of a Quote, provided that (i) in
> the case of a Fully Collateralized Contract, the Requester has sufficient
> collateral to match at the specified price and quantity and (ii) full
> execution would not result in any position limit violations. **A Requestor
> may either accept the Quote for its full size, or accept some number of
> contracts in the quote less than the full size.** Upon acceptance, a message
> specifying the accepted side of the Quote **and the number of contracts
> accepted** will be sent back to the Quoter […]

The same rule constrains the maker the other way: *"This Quote must be for the
same size as the RFQ."* The RFQ guide agrees — *"Quotes are for the full RFQ
size […] Quoters do not specify a size; each quote is implicitly for the full
RFQ amount."*

Three surfaces, three different amounts of access to that right:

| surface | partial acceptance |
|---|---|
| Rulebook | permitted, in terms |
| FIX `AcceptQuote` (35=UA) | optional tag `38 OrderQty`, "Contracts to accept […] Supports 0.01-contract increments" |
| WebSocket `quote_accepted` | reports `contracts_accepted_fp`; the doc's own example shows **50.00 accepted of 100.00 offered** |
| **REST `PUT …/quotes/{id}/accept` — what this repo calls** | **no quantity field exists.** The request body's only property is `accepted_side` (enum yes/no), required; the response is `204` with no body and no echo of an accepted count |

So on our path the accept is for the full quote **because the API gives no way
to say otherwise**, not because the venue forbids a smaller one. That is a
stronger guarantee than ADR 0169 claimed and a different one.

### 2b. Partial execution: silent, and the only written path to an answer is an inference across two rules

- **The quote status enum has no partial state**, on both the current and
  deprecated REST lookups: `open, accepted, confirmed, executed, cancelled`.
  No `partially_executed`, no `filled`. (This independently confirms the repo's
  `QUOTE_STATUS_*` list and that `confirmed` is not `executed`.)
- **FIX `QuoteStatusReport` (297)** is the same: `ACCEPTED, REJECTED, PENDING,
  CANCELLED`. Tags `134`/`135` are the sizes *offered*, not accepted.
- **The `quote_executed` WebSocket message carries no contract count at all** —
  only ids, `market_ticker`, `executed_ts` and an `order_id` described as
  *"Your order ID resulting from the quote execution. Use this to match with
  fill messages."* The venue's own design forces you to read the executed
  quantity out of fills. That is *consistent* with a variable fill size; it
  does not state one.
- **`/portfolio/fills` never mentions RFQ, quotes or block trades.** `order_id`
  is a required field described only as *"Unique identifier for the order that
  resulted in this fill"* — nothing says it is absent or synthetic for an RFQ
  fill, and nothing says one acceptance yields one fill row rather than
  several.
- **The RFQ guide's "Common errors" table** lists `invalid_parameters`,
  `RFQ_CLOSED`, `INSUFFICIENT_BALANCE`, `409 Conflict` — **no short-fill or
  failed-fill case.**

The one chain that does bear on it, and it is an inference rather than a
statement. Rule 5.3(b)(d)–(e): on confirmation the platform starts a timer and
then *"sequentially enter[s] orders into the order book […] according to the
direction, size, and price of the confirmed Quote"*, with **worse time
priority than all existing resting orders**, and *"each of these orders
behaves identically to a standard order in the order book."* Rule 5.10(a) then
says of any standard order: *"If an Order is only partially filled, the
unfilled portion of that Order will remain in the order book as a resting
order at the limit price specified."*

Chaining those two gives *a short fill is possible in principle, and its
residue would rest on the public book*. **Neither rule says the RFQ pair is
all-or-none and neither says it can fill short**; the chain is a reading, and
it is recorded here as a reading. It matters because a resting residue is the
one behaviour ADR 0115 removed on Joe's word — he pays the ask and does not
make offers — so if it can happen, it is worth more than a size discrepancy.
**Unverified. See §6.**

### 2c. `rest_remainder` — the REST page and the FIX page define it differently

ADR 0169 Amendment 1 says `rest_remainder: False` *"governs the requester's
remainder, not the maker's fill."* That is right for REST and only half the
story:

| where | tag / field | description, verbatim |
|---|---|---|
| REST `CreateRFQRequest` (required) | `rest_remainder` | "Whether to rest the remainder of the RFQ after execution" |
| REST `CreateQuoteRequest` (required) | `rest_remainder` | "Whether to rest the remainder of the quote after execution" |
| FIX `QuoteRequest` (35=R), requester | `21015` | "Rest the quote remainder after execution (default: N)" |
| **FIX `Quote` (35=S), maker** | `21015` | **"Allow partial fills (default: N)"** |

That last line is **the only occurrence of the phrase "partial fill" anywhere
in Kalshi's RFQ documentation**, REST or FIX. It sits on the *maker's* submit
message, it is not reconciled with the "rest the remainder" wording used
everywhere else for the same tag, and **no page defines what "the remainder"
is** — the un-accepted portion of a partially accepted quote, or an unmatched
portion of the entered order. The changelog entry that introduced it (FIX
v1.0.23, 2026-05-05) uses the "rest the remainder" wording and not "allow
partial fills".

Two things follow for this desk. First, the tag's default is **N** on both
sides, so whatever it means, the non-resting, non-partial behaviour is the
default and this repo's pinned `False` is that default. Second, **it is the
maker's flag as much as ours**, so "we pinned it False" does not by itself
foreclose a maker-side partial. This is a documentation divergence of exactly
the shape that cost this repo a session over `accepted_side`, and it is
written down here so the next reader does not pay for it again.

## 3. The measurement

Two bounded read-only queries against the live database (`mode=ro`), joining
`combo_rfq_quotes` to `combo_rfqs` for the ticker, then to `fills` on that
ticker in a window starting 5 s before the acceptance.

**Population.** `combo_rfq_quotes` holds **12** rows with `accepted_ms` set and
`accept_dry_run = 0`. Eleven carry `outcome_status = 'executed'`; one carries
`outcome_status` NULL and is §4. This is a **census of the whole population**,
not a sample of it.

The 0.4-cent probe of 2026-09-17T17:53Z
(`docs/measurements/2026-09-17-accepted-side-names-the-makers-side.md`) is
**not among those twelve rows** — the earliest recorded acceptance is
2026-09-17T19:33Z — so it was fired outside the route that writes this table.
It is neither counted nor double-counted below. **The ticket's premise that
"the only executed accept this repo has" was that one probe was already stale
when it was written**: eleven more had gone through
`POST /api/parlays/rfq/accept` by the time it was read.

**Window.** 2026-09-17T20:43:56Z to 2026-09-18T08:15:09Z — about eleven and a
half hours, one contract family (`KXMVECROSSCATEGORY`), every acceptance
buying YES via `accepted_side = "no"`.

**Result, stated as differences rather than as positions.** Per-trade tickers,
sizes and prices are Joe's holdings and stay out of this public repo; the
question needs only the *difference* between what was quoted and what was
filled, and that is published whole.

```
n = 11 executed, non-dry-run acceptances   (a census, not a sample)

quoted size  -  filled size        0 on 11 of 11   (exact, to 0.01 contracts)
quoted ask   -  fill price         0 on 11 of 11   (exact, in tenths of a cent)
fill rows per acceptance           1 on 11 of 11
accept -> fill lag                 1,090 ms to 3,904 ms   (11 of 11 inside 4 s)
```

Counts, not rates. Eleven of eleven is a count; it is not "100%", and no
percentage is computed over eleven rows.

**The test is not degenerate at size one.** The eleven quoted sizes span
**1.51 to 227.27 contracts** and the eleven quoted asks span **2 to 534 tenths
of a cent**. Amendment 1's specific objection — that the only evidence was one
acceptance fired at `contracts = 1`, where there is almost no room to
part-fill — does not apply to this population. Nine of the eleven were quoted
above 1.8 contracts and the largest above two hundred.

**Fractional sizes are the norm, so a partial fill had no need to be tidy.**
The venue quotes and fills in hundredths (`no_contracts_fp`, `count_fp`), and
97 of the 116 `KXMVE` rows in `fills` carry a fractional count. A fill of
14.02 against a quoted 15.09 would have been unremarkable to the schema. It
was 15.09.

**One venue order, one fill, always.** Across all 150 rows in `fills`, **no
non-NULL `venue_order_id` appears on more than one fill row.** Not one order in
the record has ever been broken into pieces. (18 of the 116 `KXMVE` fills carry
no `venue_order_id`; they predate the column being kept and are outside this
population.)

## 4. The twelfth acceptance filled for nothing, not for less

The one acceptance without `outcome_status = 'executed'` is the
2026-09-17T19:33Z RFQ, quoted at **173.01 contracts** against a $5.00 target
when the combinations shard held less than that. It produced **no fill row at
all**. The code's own account of that event (`backend/combo_rfq.py:205`) is
that the venue returned `insufficient_balance` and refused the acceptance
whole, after 28 makers had answered.

That is the sharper version of the same finding, and the rulebook predicts it:
partial acceptance is conditioned on the requester having *"sufficient
collateral to match at the specified price and quantity"*, and Kalshi refused
rather than filling what the collateral would cover. A venue that part-fills
had an obvious opportunity here and did not take it.

Its `outcome_status` is NULL — *never read back*, a state and not a zero — so
this paragraph rests on the refusal recorded in code and on the absence of any
fill, not on a status the venue confirmed.

## 5. What the build half of #74 should do differently

The measurement did not need a venue call. **The recording still does**, and
the docs name a better link than the one used here:

- The RFQ guide says fills from a quote execution are matched on
  **`creator_order_id`** (maker) or **`rfq_creator_order_id`** (requester),
  both private fields on the Quote object. `backend/kalshi/rfq.py` parses
  neither. Keeping `rfq_creator_order_id` turns this document's
  ticker-plus-time-window join into an **identifier** join, and
  `GET /portfolio/fills` accepts an `order_id` query parameter directly.
- `quote_executed` on the WebSocket also hands back the `order_id`
  *"resulting from the quote execution"*, for the same purpose.
- The quote object carries a second, unexplained size field: verbatim in
  `tests/fixtures/combo_rfq_quotes.json`, alongside `no_contracts_fp`
  (`"8.19"`, which this repo reads) there is **`contracts_fp` (`"0.00"`)**,
  which nothing reads and no page explains. On an `open` quote it is zero.
  Whether it becomes the executed quantity on an `executed` quote is
  **unknown and unchecked**; if it does, it answers this question with no join
  at all. Worth one read on the next acceptance. Not a claim here.

## WHAT THIS DOES NOT ESTABLISH

- **Not that an accepted quote CANNOT execute short.** Eleven of eleven filled
  whole. A venue that permits short execution would also show eleven of eleven
  whole fills whenever the makers had the size, and every one of these was
  small — every request was for $5.00 or less. **The recorded behaviour is
  measured; the venue's rule is not.** ADR 0169 may cite this as *eleven of
  eleven, at these sizes, in this window*, and may not restate it as "a quote
  is all-or-nothing".
- **The reverse, for the acceptance half: the venue's rule is documented and
  it contradicts the ADR's wording.** Partial acceptance is permitted by Rule
  5.3(b)(c) and reachable over FIX. What protects this repo is the REST body's
  missing quantity field, which is a property of the endpoint and could change
  in a release. It is not a property of the market.
- **Nothing at real size.** The population is $5.00-or-less requests fired
  within twelve hours on one contract family, all buying YES. A quote worth
  real money, a maker under pressure, or a size that exhausts a maker's
  appetite is untested, and the first such fill is worth more than these
  eleven.
- **The join is circumstantial, not an identifier.** A fill row carries no
  `quote_id` and no `rfq_id`; the accept returns 204 with no body; and the repo
  discards the one field that would link them (§5). Nothing ties an acceptance
  to its fill here except same ticker, 1–4 s later, at the quoted size and the
  quoted price. On sizes like 227.27 and 12.65 that coincidence is not a
  serious rival, but a fill inside the window from another source would be
  misattributed.
- **Nothing about a resting residue.** §2b's two-rule chain implies a
  short-filled RFQ order would rest on the public book. **That was not
  observed, not tested, and is not asserted** — there were no short fills to
  leave a residue. It is the consequence that would matter most if the
  execution half ever answers yes, and it is why §6 exists.
- **Nothing about the fee.** The prices compared are contract prices. A quoted
  ask matching a fill price says nothing about what Kalshi charged on top;
  ADR 0145's E3 and ADR 0027's H4 are untouched.
- **Nothing about `stake_basis`.** That the fill price equalled
  `expected_ask_tenths` on eleven of eleven is what ADR 0160's `venue_fill`
  upgrade would be *for*, but this measurement wrote nothing, and reading the
  venue's number at read time is a build decision (#74's other half), not a
  finding here.
- **Not a rate, and not predictive of the next fill.** n = 11. There is no
  denominator that turns eleven of eleven into a probability, and the next
  acceptance is not covered by it.
- **One documentation discrepancy left unresolved.** The RFQ guide gives
  High-Volatility Markets a 3-second confirmation window; rulebook v1.29 and
  the 2026-01-30 CFTC filing say 1 second. This repo says 3 s / 1 s. Noted,
  not settled, and nothing here depends on it.
- **No operator data.** Per-trade tickers, per-trade sizes and prices,
  balances and account identifiers are deliberately absent; only
  quoted-minus-filled differences, aggregate ranges and row counts are
  published. Nothing above identifies a position.

## 6. The one thing left open

Whether a short execution would leave a **resting order on the public book**
(§2b). It is an inference from Rule 5.3(b)(e) plus Rule 5.10(a), it has never
been observed, and it is the only branch of this question whose answer would
change what the desk is willing to do rather than only what it records — a
resting offer is the behaviour ADR 0115 removed on Joe's word. It cannot be
settled from the docs and it cannot be settled by a read; it needs either a
short fill to occur, or a Kalshi answer. **It is not resolved by this
document and no plan should assume either way.**

## Method, for replay

Two bounded read-only queries on the live box via
`flyctl ssh console -a kalshi-cockpit`, with
`sqlite3.connect("file:/data/cockpit.db?mode=ro", uri=True)`. Every query was
bounded: `combo_rfq_quotes` (392 rows), `combo_rfqs` (15) and `fills` (150) are
small tables, the acceptance list was `LIMIT 40`, and each per-acceptance fill
lookup was `WHERE ticker = ? AND filled_ms BETWEEN ? AND ?` with `LIMIT 10`.
Nothing touched `dbstat`, no large table was scanned, and **no RFQ, quote
acceptance, order or write of any kind was issued.**

Documentation read for §2: the REST reference (accept-rfq-quote, accept-quote,
create-rfq, create-quote, get-rfq-quote, get-quote, get-rfq, confirm-rfq-quote,
get-fills, get-multivariate-event-collection), the RFQ guide, the
`communications` WebSocket schema, the FIX RFQ-messages and order-entry pages,
the changelog in full, KalshiEX LLC Rulebook v1.29, and the 2026-01-30 CFTC
self-certification filing for RFQ orders.
