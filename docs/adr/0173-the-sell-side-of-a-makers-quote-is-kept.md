# ADR 0173 — The sell side of a maker's quote is kept

**Status:** Accepted
**Date:** 2026-09-18
**Schema:** v48 (`combo_rfq_quotes.yes_bid_tenths`)
**Ticket:** #76 slice 1, which follows #63 — Joe answered **(A)** on 2026-09-18:
show both exit prices on each open combination, read-only, no Sell button.
**Amends nothing. Retracts nothing.**

---

## 1. The defect, and it is an omission rather than a mistake

`parse_quotes` read `no_bid_dollars` and **discarded `yes_bid_dollars`.**

An RFQ has no side field. A maker answers with both of their bids, so
`yes_bid_dollars` is literally **what they would pay Joe for the side he
holds** — the exit. `RfqQuote` had no field for it and `combo_rfq_quotes` had
no column, so the number existed on the wire and in no record at any layer.

The consequence is already on the record. The 2026-09-17 sell-side
measurement — **16 of 44 quotes carried a YES bid, on 3 of 3 held positions,
every one at the full size asked**
(`docs/measurements/2026-09-17-combinations-can-be-exited.md`) — had to be
taken with a throwaway script, and **could not be re-derived from anything the
recorder had kept.** That measurement refuted "combinations are enter-only",
a claim this repo had carried for weeks. The field that refuted it was being
parsed and thrown away in the same file the whole time.

## 2. The decision

**`RfqQuote.yes_bid_tenths: Optional[int]`, parsed through the same
`_read_tenths` as every other price, stored on the row (schema v48), and
never derived.**

### `None`, never zero

A maker who names no YES bid and a maker who bids nothing are different facts,
and `0` is a settled outcome rather than a price — `complement(0)` reasoning
applies to this side too. The column is nullable with **no default and no
backfill**, so every quote written before v48 reads as "no YES bid recorded",
which is the truth about it. **No backfill is possible even in principle:** a
delete discards the quotes at the venue and no stored copy of the original
payload exists.

Both quotes in `tests/fixtures/combo_rfq_quotes.json` — a real capture — carry
`yes_bid_dollars: "0.0000"`, so the settled-outcome branch is exercised by the
committed fixture rather than only by a constructed one.

### Not derived, and this is the venue's most-repeated correction run backwards

`yes_ask_tenths` is **derived**: `complement(no_bid)`, because a YES and a NO
settle together at $1.00. `yes_bid_tenths` is a bid on the YES side
**directly**, so there is no complement to take, and `yes_bid` and
`complement(no_bid)` are two different numbers separated by the maker's own
spread. A mutation that reads one as the other fails six tests.

### The sell side never costs a price Joe can act on

Two guards, both deliberate:

- An **untradeable or unreadable** `yes_bid` sets the field to `None` and
  **keeps the quote.** This side is extra information; losing a buy price over
  it would be a strictly worse screen.
- A **centi-cent** `yes_bid` is refused without counting into
  `refused_finer_than_tenths`. That count drives ADR 0172's sentence about
  whether the desk could show him a price to **buy**, and a maker declining to
  price the side he does *not* hold is not a failure to price the one he does.
  Folding them together would make the screen say no maker could be shown
  while the buy price sat right there.

## 3. What this slice deliberately does NOT do

**A quote carrying ONLY a YES bid is still dropped.** `parse_quotes` requires a
readable `no_bid` to derive `yes_ask_tenths`, which is non-optional on the
dataclass and `NOT NULL` on the row.

Ticket #76 lists "a quote surviving with either side present" as part of slice
1, and it is **not done**, for a stated reason rather than an oversight:
relaxing that invariant changes what the **armed accept path** can be handed —
`accept_quote` spends, and a quote with no ask is one it must refuse rather
than mis-price — and it is only *needed* once a sell-side RFQ is actually
fired. **Nothing fires one.** It belongs with slice 3, which does.

**Slice 2 (the public-book bid on `/api/hedge`) is not in this ADR**, and two
findings from starting it are recorded here because they change its design:

1. **`parlay_positions` has no contract count.** `_record_combo_position`
   writes `stake_tenths = contracts * fill_price_tenths` and keeps neither
   factor, so a per-contract book bid **cannot be turned into what the
   position would fetch**, and #76's "show cost basis beside the bids" has no
   denominator. The count is reachable — `stake_basis_for` already reads the
   order row and already validates `venue_fill_count` — but carrying it out
   means adding a field to `StakeBasis`, which every stake on the screen goes
   through.
2. **`/api/hedge` is polled, and it is already the slowest desk route.**
   Measured tonight on a box up 2.7 hours: **2,090 ms median**, against 101 ms
   for `/api/window` and 712 ms for `/api/parlays`. `read_books` is sequential
   by design, and slice 2 adds one venue read per open combination to every
   build. That is a real cost on the screen Joe actually uses, and it deserves
   a timing rather than an assumption.

## 4. Verification

**134 passed** across `test_combo_rfq.py`, `test_combo_rfq_store.py`,
`test_combo_rfq_route.py` and `test_combo_rfq_accept.py`. **Six mutations, all
red:**

| | mutation | result |
|---|---|---|
| M1 | the sell side is discarded again | red |
| M2 | a settled-outcome `yes_bid` is kept as a price | red |
| M4 | the sell side is read as `complement(no_bid)` | red, 6 failed |
| M5 | a too-fine sell side is counted as `too_fine` | red |
| M6 | the store drops the column from the INSERT | red |
| M7 | the store never updates the column on a requote | red |

**M6 and M7 were GREEN on the first pass, and that is the finding.** Nothing
read `yes_bid_tenths` back out of the database, so a column written nowhere
would have looked exactly like one that worked — the shape of the four modules
this repo built and never called. Four store round-trip tests were added,
including one that a requote can **clear** a sell side that is gone: the stale
value is the dangerous one, because it is the number a screen would tell Joe he
could sell at.

**A seventh mutation was dropped rather than fixed, and the distinction
matters.** `yes_bid = _read_tenths(...)[0] or 0` — substituting zero for an
unreadable price, the exact thing `tasks/lessons.md` forbids — stayed green,
and re-checking showed why: zero then fails `is_valid_price` and resolves back
to `None`, so the mutation is **behaviour-preserving by construction**, not
undetected. The guard it aimed at is the one M2 already proves is load-bearing.
A mutation that cannot change behaviour is not evidence of a weak test, and
recording it as one would have been wrong.

## 5. What this does not establish

- **Nothing about a sell-side RFQ.** This desk has never fired one through the
  product. A YES bid arriving in a payload now survives to the record; asking
  for one is slice 3.
- **Nothing about how often a maker bids the side Joe holds.** 16 of 44 on one
  day across three positions is a count, not a rate, and both quotes in the
  committed fixture carry no usable YES bid at all.
- **Nothing about whether an exit is a GOOD exit.** Every best bid measured on
  2026-09-17 sat *below* Joe's cost basis (7.60 vs 10.20, 4.70 vs 5.70, 0.14 vs
  0.38). An exit existing is not an exit being good, and this ADR adds a number
  to the record, not a reason to take it.
- **Nothing about ADR 0078.** Hedging a leg and selling the combination are
  different actions at different costs. The hedge remains the exit the desk
  watches.
