# 0160 — The stake is read at the venue's own fill price, on the read

Written by lane B (`lane/stake-basis-venue-fill`) with no ordinal; **0160 was
taken at the merge commit after `git fetch`**, per `docs/adr/README.md`.
**No schema change, no `SCHEMA_VERSION` claimed** — schema stays v44 and v45
stays unallocated.

Date: 2026-09-16
Status: accepted
Scope: `backend/hedge.py` (the read), `backend/api/routes.py` (one false
comment), `backend/core/hedge.py` (one stale sentence in a docstring).
`parlay_positions` is **not** altered, **not** backfilled and **not**
rewritten; `_record_combo_position`, `manual_orders` and every order path are
untouched.

Ticket: issue #49, answered `49A` by Joe on 2026-09-16 and closed with his
answer quoted. This is the decision ADR 0143 §4 deferred.

---

## 1. The defect

Two prices exist for every hand bet and they are not the same number.

- **Sent price.** `manual_orders.limit_price_tenths`, written at INTENT time
  (`backend/store/manual_orders.py:648`) from `OrderRequest.fill_price_tenths`
  (`backend/kalshi/orders.py:299`) — "what one contract of *our* side costs at
  the price being sent". It is fixed before anything matches.
- **Fill price.** What Kalshi actually charged. Since schema v40 (ADR 0143,
  2026-09-11) `record_outcome` keeps `venue_fill_count`,
  `venue_avg_fill_price_tenths` and `venue_avg_fee_dollars` on the permanent
  `manual_orders` row.

**Nothing that ran read the second one.** Before this change the only readers
of `venue_avg_fill_price_tenths` in the tree were
`scripts/census_recorded_fill_vs_venue.py` — a spent, registered census — and
its tests. No route, no screen.

Meanwhile `_record_combo_position` writes

    stake_tenths = contracts * fill_price_tenths

from the SENT price, and `hedge.assess` computes the whole hedge figure from
`position["stake_tenths"]` on all ten open `parlay_positions` rows. The
comment above that line asserted the stored number was what he had paid. It
was not, and a comment saying why something is safe goes stale silently
(`tasks/lessons.md`; the memory note on justifications decaying toward
reassurance). It is corrected in the same commit.

**Measured magnitude, and what it is not.** The registered census
(`docs/measurements/2026-09-15-recorded-fill-vs-venue-charge-census-result.md`)
found sent equal to the venue's price on 11 of 12 joined rows and apart by
+22 tenths a contract on the twelfth, with the sent price ABOVE the venue's.
`n = 12`, one stratum (`S1`/`KXMVE`), every order `side = yes`, every joined
row single-fill, and on that book "sent equals venue" is close to mechanical
(§11.4 of the result). That look is **spent**. Nothing below is a rate,
nothing below generalises to the next fill, and none of it is the reason for
the change — Joe's answer is. It is the reason the correction is small on the
rows seen so far.

## 2. The decision

**Where the venue gave a price and the link to it is provable, the sunk stake
is the venue's price times the count the venue reported. Otherwise the
recorded figure stands and the position says which named reason applies.**

Three sub-decisions were open. Each is stated with its alternative.

### 2.1 The join happens at READ time. The written row is never touched.

`hedge.build_payload` resolves every open position's stake before it assesses
anything (`stake_bases`, `position_at_basis`), and hands `assess`,
`entry_fee_tenths` and `serialise_position` one mapping so the three cannot
disagree about which number they are on. `parlay_positions.stake_tenths` keeps
the sent price, forever.

The alternative was to resolve it at write time in `_record_combo_position`.
Rejected on four grounds:

- **`POST /api/manual-orders` is the ARMED path.** It sends real
  immediate-or-cancel orders at Joe's tap. A correction that runs there is a
  change to code that moves money; one that runs on the read is not, and the
  read can do everything the write could. Nothing on the order path changed.
- **`parlay_positions` has no key to the order.** There is no
  `manual_order_id` column and no column for the fallback marker, so
  recording the basis at write time needs a schema version — and the version
  buys nothing the read does not already have.
- **The precedent is already ours.** ADR 0145 sinks the entry fee beside the
  stake inside `assess` rather than writing it into `stake_tenths`, for the
  same reason: a derived correction belongs where it is derived.
- **It is reversible by deletion.** Nothing to unwind, because nothing was
  written.

What the read pays: one extra SELECT per `/hedge` build, bounded twice — by
the open positions' own tickers and by their own `placed_ms`, both as `IN`
lists. It cannot widen into a scan of the order history as `manual_orders`
grows. There is no index on that table and it held thirteen real rows on
2026-09-15; if it ever grows enough for the scan to matter, an index is the
fix and a version bump is its price.

### 2.2 The join key is `(combo_ticker, placed_ms)`, and it is exact.

Both halves come out of one request. `POST /api/manual-orders` takes
`submitted_ms` once, writes it on the `manual_orders` row through
`_write_manual_intent`, and passes the same variable to
`_record_combo_position` as `placed_ms`. The ticker alone would not do — the
same combination can be bought twice — and a join that is unique only by
today's luck is the kind this repo refuses.

Zero matching rows, or more than one, means the link is unreadable. An
unreadable link resolves to the figure already recorded, never to a plausible
one, and the reason says which of the two happened.

### 2.3 Forward-only. Nothing is backfilled.

Ten `parlay_positions` rows are open and their hedge figures are on Joe's
screen during live games. The correction reaches them — the read applies to
every row, old and new — but **no stored number changes**. That is the whole
distinction: rewriting history is a different act from changing what a reader
computes, and only the second one is reversible by deleting code.

A literal backfill (`UPDATE parlay_positions SET stake_tenths = ...`) was
considered and refused on three further grounds beyond reversibility:

- Seven of the thirteen real orders predate v40 and carry no venue price, so
  a backfill could only reach part of the table and would leave rows that
  look identical and are not.
- It would need the join key it does not have as a column, so it would have
  to re-derive the same `(ticker, submitted_ms)` match — at which point the
  read already does it, correctly, every time.
- It would move a money figure on a screen Joe is watching mid-game, with no
  announcement, in the direction that RAISES the displayed hedge outcome
  (the census's one disagreeing row had the sent price above the venue's).
  That is the flattering direction, and it is the one that needs a reason
  rather than a convenience.

If the stored rows are ever to be corrected, that is a separate, registered,
reversible act with its own ADR. It is not deferred work implied by this one.

## 3. The guards, and why each exists

`stake_basis_for` returns `venue_fill` only when the venue's number is
readable AND provably about this position. Every other branch returns the
recorded stake with a named reason — a vocabulary, not prose, because the
reader that most needs it is a later audit and a fact behind a parser is not
queryable.

| reason | why the venue's number is refused |
|---|---|
| `not_a_kalshi_combo` | a sportsbook slip has no order row; the stake is the figure Joe typed and always was |
| `no_order_row` | nothing joined — a hand-recorded ticket, a dry run, a position whose order row is gone |
| `ambiguous_order_rows` | more than one row answered the key; the link is unreadable |
| `side_convention_unresolved` | a `side = 'no'` order — see below |
| `no_venue_price` | pre-v40, or the outcome write failed; the venue told us nothing |
| `no_venue_fill_count` | same, for the count |
| `venue_fill_count_unusable` | a count that answered and cannot be a holding — zero (an IOC that matched no one), negative, not finite. A column that answered and a column that stayed silent are different facts |
| `fractional_venue_fill_count` | the route refuses to record a position at a rounded size (ADR 0151); this refuses to re-price one at a size it cannot reproduce |
| `contract_count_disagrees` | `int(venue_fill_count) * 1000` must equal the stored `return_tenths`, because `_record_combo_position` built the return from that same count. When it does not, the row found is about some other holding |

**The NO-side refusal is the one that was not in the brief and is not
optional.** `limit_price_tenths` is OUR side's price:
`OrderRequest.fill_price_tenths` reflects a NO onto the YES book through
`yes_book_price_tenths`. `venue_avg_fill_price_tenths` is
`average_fill_price` stored verbatim, with **no reflection applied**
(`store/manual_orders.py:_venue_price_tenths`). On a YES order the two are one
convention. On a NO order, which book the venue quoted has never been
established: the census's Amendment A4.3 wrote a classification rule for
exactly this artifact and it was **never exercised**, because all thirteen
real orders are YES, and the result doc lists "nothing about the side
convention of `average_fill_price` for a `side = 'no'` order" among what it
does not establish. Reading the venue's number there could halve or double
the stake. `ManualOrderRequest.side` admits `no`, so the case is reachable.
Unreadable resolves to a refusal, never to a plausible number — this is that
rule, applied to a convention rather than to a value.

Resolving it needs a real NO fill and a registration, not a session's
opinion.

## 4. The copy ships in the same commit

Two user-facing sentences asserted, unconditionally, that the figure subtracts
the price the desk SENT. Both are now false on a position resolved to
`venue_fill`, and a caveat that names a condition is falsified by fixing the
condition — so the fix and the copy ship together or the screen lies in the
interval (`tasks/lessons.md`; the rule
`test_no_screen_still_tells_him_that_closing_the_page_buys_more` was written
for).

- **`NOTES["upper_bound"]`**, on the hedge screen and in both Discord embeds.
  Its stake clause is now conditional — Kalshi's own fill price where the
  venue reported one, the sent price where it did not — and it names the
  condition that remains real: a bet placed before schema v40 (2026-09-11)
  has no venue price on its row. The census's three numbers, the date, "not
  a rate" and "nothing about the next fill" are all kept verbatim.
- **`estimate_grain`**, the per-ticket grain beside the figure (issue #43 A).
  A Kalshi combo whose stake IS the venue's charge does not carry E2 at all,
  so it falls through to E4 — the hedge fee at the flat 0.070 against a
  measured baseball k of about half that — which is then its largest measured
  term. A combo still on the sent price keeps the E2 sentence unchanged.

`tests/test_hedge_positions.py`'s copy guard is updated rather than weakened:
the dead universal joins `KILLED_LOCK_CLAIMS`, so it cannot come back, and
the two halves of the new conditional are pinned in its place. The killed
wording is listed in the file the guard scans and is reproduced in no comment
beside the copy itself (`tasks/lessons.md` 2026-09-16, tenth).

## 5. What is deliberately NOT done

- **`venue_avg_fee_dollars` stays out — this is option A, not option B.** It
  sits on the same row and nothing here reads it. It is REAL dollars, its
  rounding rule onto integer tenths is undecided, and deciding it in passing
  would be a money change nobody registered. The entry fee remains
  `combo_entry_fee_tenths`' modelled number at 0.071 (ADR 0145), now charged
  on whichever stake this decision produces.
  `tests/test_stake_basis_is_the_venue_fill.py` asserts the column appears in
  no code string in `backend/hedge.py`.
- **`fills` is not read.** The census names `fills.price_tenths` as the
  PRIMARY venue price and the create response as the FALLBACK; this reads
  only the `manual_orders` column. `fills` is retention-eligible at about
  three months and `manual_orders` is permanent, so the permanent column is
  the one a hedge screen can rely on. Whether the two ever disagree is an
  open question the census explicitly did not settle (`n_endpoints_disagree
  = 0` on six single-fill YES rows is not evidence either reader is right).
- **No `manual_order_id` column on `parlay_positions`.** It would make the
  link auditable in SQL rather than only re-derivable, and it is the obvious
  follow-up. It is a second decision and a schema version, and this ticket
  is one decision.
- **The frontend is untouched, and `api.ts` deliberately does not declare
  the two new fields.** `stake_basis` and `stake_basis_reason` ride on the
  `/api/hedge` payload so a reader — an auditor, a script, `curl` — can tell
  the two apart. They are not for a component, and the precedent for a
  payload field a component may not reach is already here:
  `Rung.floor_tenths` rides on the wire and `HedgeRung` in
  `frontend/src/lib/api.ts` does not declare it, so a component that reached
  for it would fail `tsc`. `docs/adr/README.md`'s rule — a type declaration
  changes in the same commit as the backend field that fills it — bites when
  the field is meant to be rendered, and neither of these is. **Whether the
  hedge card should SAY which price its stake is on is a question for Joe,
  not a build**, and it wants a ticket before anyone declares the type.

## 6. What this does not establish

- **That the hedge figure is now correct.** It carries at least four error
  terms and they do not share a sign (census registration Amendment 1 §A6, as
  amended by ADR 0145). This narrows E2 — the sent-price-vs-fill-price term —
  on the stake's own price and closes none of the others. The figure is still
  an estimate pinned in neither direction, and the words to refuse are still
  ceiling, floor, conservative, at least, can only be smaller/larger.
- **That E2 is now zero.** The venue's number is used where it is readable;
  on a pre-v40 row, a NO order or an unjoinable position the sent price is
  still what the figure is built on, and the position says so.
- **Anything about how often the two prices differ.** The census is spent and
  is a census of twelve rows in one stratum. No rate is computed anywhere in
  this change.
- **That the venue's `average_fill_price` is our side's price on a NO
  order.** The opposite — §3.
- **That the ten open rows' stored stakes are right.** They are the sent
  price, they stay the sent price, and that is now said out loud in the code
  that writes them.

## 7. Verification

`tests/test_stake_basis_is_the_venue_fill.py`, twenty-five tests, plus the
updated copy guard in `tests/test_hedge_positions.py`. Fourteen
mutations were applied to the guarded code and every one turned the suite red;
each file was restored from a byte backup and verified md5-identical
afterwards (never `git checkout` — it erases uncommitted work). The mutations
covered: the NO-side refusal, the missing-price refusal, the contract-count
proof, the ambiguity sentinel, the fractional-count refusal, the zero-count
refusal, the `dry_run = 0` filter, the payload wiring in `build_payload`, the
payload's basis field, the option-B fee guard, the killed sentence in
`routes.py`, the per-ticket grain's E2 branch, the caveat's dead universal,
and — for the no-backfill claim, which is an assertion about an absence — an
added `UPDATE parlay_positions` inside the read, which turned
`TestNothingIsBackfilled` red as it must.
