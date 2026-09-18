# ADR 0178 — An RFQ acceptance reads the venue's own fill

**Status:** Accepted
**Date:** 2026-09-18
**Schema:** v50 — five nullable columns on `combo_rfq_quotes`
(`venue_fill_read_ms`, `venue_fill_outcome`, `venue_fill_note`,
`venue_fill_count`, `venue_avg_fill_price_tenths`)
**Ticket:** #74 (build, no decision needed), from the venue review of `b92d6ec`
and `523fbda`
**Amends:** ADR 0169, whose "the quote's own size" is now the fallback
**Extends:** ADR 0160, which made `/hedge` resolve every stake at read time and
could not reach this path

---

## 1. What was asserted, and by what

`_record_accepted_position` recorded a combination bought by RFQ at the
**quote's** `contracts` and ask, on this ground:

> **The size is the quote's own `contracts`**, on the ground that a maker's
> quote is all-or-nothing at the size asked for — an `executed` quote filled at
> that size or did not fill.

`backend/kalshi/rfq.py` says the same thing. Neither cites a measurement, and
there is none: the only executed acceptance this repo had when that was written
was fired at `contracts = 1` on the RFQ, not against a maker's quoted size, and
its own measurement doc says in terms that it speaks to no partial fill.
`rest_remainder: False` on create governs the **requester's** remainder, not the
maker's fill.

**If a quote can part-fill, the failure is silent and permanent.** The position
would be wrong in both size and stake; `/hedge` would size a hedge against a
holding Joe does not have; and nothing downstream could catch it, because the
stake basis was `as_recorded` — there is no reconciliation to fail. That is the
shape ADR 0160 was written to remove everywhere else, and this was the one armed
path it never reached.

## 2. The premise that was wrong, and it was wrong in our favour

`backend/combo_rfq.py` carried, and `tasks/NEXT.md` restated, that *whether a
KXMVE combo fill reaches `/portfolio/fills` at all, and under what ticker, is
unresolved by the repo*.

**A fixture this repo commits already answers the ticker half.**
`tests/fixtures/portfolio_fills_redacted.json` holds **eight combination
fills**, captured 2026-08-18. Every one of them:

- carries the **combination's own ticker** in both `ticker` and `market_ticker`
  (`KXMVECROSSCATEGORY-…`), not its legs';
- is `side: "yes"`, `action: "buy"`, `is_taker: true`;
- has a fractional `count_fp` (`227.27`, `4.15`, `909.09`) and a `fee_cost`.

`tests/test_portfolio_poll.py` has been reconciling a fee against one of them
since ADR 0073. Per CLAUDE.md's own record — *0 of 61 combos had an ask, yet 51
of 52 of Joe's fills were takers, and those were RFQ executions* — these are
very probably RFQ fills already.

So the build did not need to discover the endpoint; it needed to read it. The
lesson is `tasks/lessons.md`'s, twice over: a stated blocker is an inference
until it quotes the source, and the answer is often already on disk.

**What the capture does not settle, and this build therefore measures:**

1. **Latency.** Those rows were captured days after the trades. Execution runs
   about 1.1 s behind confirmation and propagation to `/portfolio/fills` is
   unmeasured, so a read taken seconds after `executed` may legitimately find
   nothing. An empty read is recorded, with the elapsed time, rather than
   treated as an error.
2. **Partial fills.** Still unobserved on any path. The build makes the first
   one visible instead of invisible.

## 3. What is built

On an `executed` acceptance that is not a dry run, before the position is
written, `read_venue_fill` asks `GET /portfolio/fills?ticker=<combination>`.

- **The rows are re-checked against the ticker** the caller asked for. The
  venue's filter is trusted for what it returns, not for what it leaves out.
- **Only a `yes` fill is read.** `accepted_side` names the **maker's** side, so
  buying YES sends `"no"` and the fill prints on ours — measured 2026-09-17. A
  row on the other side is refused, never re-interpreted; the wrong reading of
  that convention buys the opposite contract at ~250x.
- **Only fills stamped at or after the acceptance** (less five seconds of clock
  skew) count. Too tight yields `no_rows`, which keeps the recorded stake and
  says so; too loose would attribute an **earlier** fill of the same
  combination to this trade.
- **More contracts than were quoted is refused** (`count_exceeds_quote`). They
  cannot all be this acceptance, so the rows in hand are not one bet — the
  `contract_count_disagrees` proof, on a second path.
- **A short read is re-read once**, 0.75 s later, and the fuller answer wins. A
  read that lands mid-propagation is indistinguishable from a part-fill, and
  this makes the cheap explanation cheap to rule out. **It is not a proof of
  completeness and is not described as one anywhere in the code.**

The position is then written at the venue's count and average price when the
answer is usable, and at the quote's numbers when it is not. **Either way a
position is written.** The trade is done and the money is spent; a bookkeeping
read may not turn a completed purchase into an error that tells Joe nothing
happened. `read_venue_fill` raises nothing.

## 4. The refusals are the record

`venue_fill_outcome` is written on **every** executed acceptance, and it names
seven refusals as carefully as it names the match: `matched`,
`matched_partial`, `no_rows`, `not_under_combo_ticker`,
`unexpected_fill_side`, `unparsable`, `finer_than_a_tenth`,
`count_exceeds_quote`, `read_failed`.

**A column that recorded only successes could never settle the question it was
added for.** A month of `no_rows` with an `elapsed=` beside each one is a
finding about latency. A single `not_under_combo_ticker` naming a leg's ticker
is a finding about the venue's model. Neither is distinguishable from "nobody
asked" if the refusal is not stored — which is why `venue_fill_read_ms` NULL is
load-bearing and means exactly that.

When the combination's own ticker comes back empty, one **bare** read follows
and the tickers it saw within two minutes of the acceptance are written to
`venue_fill_note`. That second call exists only to separate *too early* from
*under another name*.

## 5. `/hedge` gains a twelfth reason

`stake_basis_for` now resolves an RFQ position three ways instead of one:

| reason | means |
|---|---|
| `rfq_accept` | the venue was **never asked** — every acceptance before v50 |
| `rfq_fill_unmatched` | the venue **was** asked and did not name this bet |
| `venue_fill` (no reason) | Kalshi's own count and average price |

The count must reproduce the position's `return_tenths` exactly, by the same
identity the order path checks. `rfq_accept`'s sentence used to say *what
Kalshi charged is not read on this path*; after this build that is true only of
rows written before it, which is why the two reasons are separate words rather
than one.

## 6. No backfill

The two acceptances this repo has predate the step and keep NULL in all five
columns, which is the truth about them. `/portfolio/fills` has a **measured
retention window of about three months with no measured lower bound**
(`KalshiRestClient.fills`), the quotes themselves are gone from the venue, and a
value invented for those rows would enter the one record that says what the
venue charged. Same rule as v48's `yes_bid_tenths`.

## 7. What this does not establish

- **Nothing about whether a quote can part-fill.** It makes the first one
  visible. No part-fill has been observed, and the code must not be cited as
  evidence that one can happen or that one cannot.
- **Nothing about the fee.** `fee_cost` is present on all eight captured
  combination fills and is deliberately not read here: it is REAL dollars, its
  rounding onto integer tenths is undecided, and ADR 0145's modelled
  `combo_entry_fee_tenths` is still what `/hedge` sinks at read time. Deciding
  it here would be a money change made in passing — the same refusal ADR 0160
  makes about `venue_avg_fee_dollars`.
- **Nothing about latency yet.** The instrument is in place; the reading is the
  next acceptance, and `venue_fill_outcome` plus the `elapsed=` note is where it
  will land.
- **Nothing about the RFQ path's own correctness.** The tests here use a fake
  venue and a captured fill; what a real RFQ execution looks like on
  `/portfolio/fills` has still never been seen.
