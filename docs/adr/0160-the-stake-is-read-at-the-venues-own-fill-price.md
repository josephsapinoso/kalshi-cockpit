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

---

## Amendment 1 (2026-09-16) — the card says which price it is on, so the type declares it

**§5's last bullet is superseded, and §5 is not rewritten.** Its reasoning was
correct for the world it was written in: nothing rendered `stake_basis` or
`stake_basis_reason`, so declaring them on `frontend/src/lib/api.ts` would
have declared a field for an auditor, which is what `Rung.floor_tenths` is
and why it stays undeclared. That bullet ended by naming the open question —
*whether the hedge card should SAY which price its stake is on is a question
for Joe, not a build* — and opened issue #53 for it. This amendment records
his answer and what changed because of it. Nothing else in this ADR moves:
the read-time join, the join key, the nine refusals, the no-backfill decision
and the option-A scope are all untouched.

### A1.1 The answer, and the principle he gave with it

Joe answered `53A` on 2026-09-16 and the ticket is closed with his answer
quoted:

- a **`venue_fill`** ticket renders **nothing extra** — the stake is what
  Kalshi charged and there is nothing to say about it;
- an **`as_recorded`** ticket carries **one small line naming the specific
  refusal**, in his language rather than the enum's, not a generic caveat.

His reason is the load-bearing part, and it is why the words go on the less
certain ticket: **a warning that fires only on the good case reads as a check
that passed.** The inverse is a defect this repo has already shipped once —
`ParlayCards` rendered a note only when `anchored_on_sharp === true` and said
nothing at all when no sharp book backed the leg (fixed 2026-09-15) — so the
render condition is the sentence's own presence, never a comparison against
`"venue_fill"` in the component. `stakeBasisNote` returns `null` for exactly
one input, and a missing basis is **not** that input: a payload that never
went through `build_payload` does not know whose price its stake is, and
silence is what a checked ticket looks like.

### A1.2 What the build is

- `frontend/src/lib/stakeBasisGloss.ts` (new) — nine sentences, one per
  refusal, plus the sentence for a reason this build predates. The precedent
  is `lib/suppressionGloss.ts`: a named vocabulary from the backend, glossed
  in plain English on the screen, pinned in both directions by a Python test
  that reads both sources. It parts company with that module in one place and
  deliberately: an unknown code there glosses to `null` because the code
  itself renders beside it, whereas here the sentence is the only thing on the
  row, so an unknown reason renders the unnamed sentence **with the code
  verbatim** rather than nothing.
- `frontend/src/lib/api.ts` — `stake_basis` and `stake_basis_reason` are now
  declared on `HeldPosition`. `stake_basis_reason` is typed `string`, not a
  union of the nine names, because a server running a reason this build
  predates is a real state and a union would only move the lie to compile
  time. This is the §5 reversal, and the README's rule now bites in the
  direction it was written for.
- `frontend/src/components/HedgePositions.tsx` — `StakeBasisLine`, one small
  line under the ticket's stake figure.
- `tests/test_the_hedge_card_names_the_fallback_reason.py` — seventeen tests.
  The vocabularies are pinned in both directions with a count as the vacuity
  anchor, and the asymmetry is **executed** under node rather than asserted as
  source text, because a substring assertion passes unchanged on a function
  that is exactly inverted and an inverted function is the whole defect.

### A1.3 The Discord push is deliberately left alone

Both embeds that state a position's stake (`hedge_lock` and `position_state`,
`backend/notify/discord.py`) already carry `NOTES["upper_bound"]` in their
footer, and §4 of this ADR made that sentence conditional: *the stake it
subtracts is Kalshi's own fill price where the venue reported one, and the
price the desk sent where it did not*. So the push states **both** branches on
**every** ticket. That is less precise than the screen and it is not the
defect Joe's principle is about: the failure he named is asymmetry — a line
that appears only on the good case — and an embed that says the same thing
whichever branch applies has none. Two further reasons: the embed's job is to
get him to `/hedge`, which is where the per-ticket resolution now is; and a
second copy of a nine-entry vocabulary is a second thing to keep in step, and
copy drift between the screen and the push is a bill this repo has paid
before (ADR 0072 Decision 3 exists because of it).

If a push ever states a stake **without** that footer, this decision is void
and the line has to travel with it.

### A1.4 What this amendment does not establish

- **That the sentences are right.** They are a session's rendering of Joe's
  answer, not ratified copy; the test guards what they may never say
  (ceiling, floor, conservative, at least, can only be, guaranteed, exact) and
  that each is one short line, not that any is well written.
- **That anything renders.** Source text and a node-executed function, no
  browser — the same limit every guard on this screen has.
- **Nothing about the hedge figure's accuracy.** Naming whose price the stake
  is narrows none of the four error terms; §6 stands unchanged.

### A1.5 Verification

Full suite green from the lane worktree. Nine mutations were applied to the
guarded code and every one turned the suite red — including the two that
matter most: rendering the line only when `stake_basis === "as_recorded"` (the
`ParlayCards` defect in its other direction, which leaves an unresolved ticket
silent) and returning `null` from `stakeBasisNote` for an unknown reason.
Each mutated file was restored from a byte backup and verified md5-identical
afterwards; `git checkout` was not used, because it erases uncommitted work.
---

## Amendment 2 (2026-09-17) — a ticket with no join key was never looked up, and says so

**§3's table gains a tenth row and nothing else in this ADR moves.** The
read-time join, the join key, the no-backfill decision, the NO-side refusal
and Amendment 1's asymmetry are all untouched; the order path is untouched
again, and no schema version is claimed. What changes is that one reason was
carrying two different facts.

Ticket: issue #56, answered `56A` by Joe on 2026-09-17.

### A2.1 The defect

`no_order_row` fired in two situations that are not the same:

- the join key **could not be formed** — a Kalshi combination Joe typed into
  `/hedge` himself, where `combo_ticker` and `placed_ms` are both absent
  because `record_position`'s hand-record caller takes them from a request the
  form does not put them in. Nothing was ever looked up. Nothing is missing.
- the join key **was formed and matched nothing** — a row off the order path
  whose `manual_orders` row is gone, or a dry run. A search ran and came up
  empty, which is a gap in the books.

On live, five of seventeen open positions were the first wearing the second's
sentence, which reported a search that had never run. That is a false alarm on
29% of the screen, and the cost is not the wording: **a genuine gap had
nowhere to stand out.** Four of the five carry labels Joe wrote himself
("Three totals", "Safe", "Next 3 hours"), so the state is recognisably his own
entry and not a failure.

The option he was offered to leave it (B) is recorded in the ticket and
refused: the line is not false, but it describes our records rather than his
bet, and a reader has to know the schema to take it that way.

### A2.2 The decision

**A tenth reason, `hand_recorded_position`, for a position whose join key
cannot be formed. `no_order_row` keeps the case it was written for and its
sentence is unchanged.**

It is **derived, not stored**. `_order_key` already returns `None` for exactly
this state, so the marker IS the join — the same argument §2.1 used to refuse
a write-time basis column, applied to the marker rather than the number. No
`SCHEMA_VERSION`, no migration, no backfill, and the undo is deleting one
branch.

The split is on the **whole key**, not on `combo_ticker` alone. A ticker with
no `placed_ms` is reachable — `HeldPositionRequest` admits `combo_ticker` and
`RecordParlay` never sends one, but `curl` can — and half a key runs no lookup
either, so it is hand-recorded too. This is a deliberate and known divergence
from `scripts/inspect_live_db_parlays.py`'s `combo-position-orphans`, which
splits its two sections on `combo_ticker IS NULL` and asks the weaker question
"does any order name this ticker". That instrument is not extended and not
changed: it answers an audit's question, this answers a screen's, and the two
differ only on a row neither the form nor the order path can produce.

### A2.3 The sentence

Joe's own wording from the ticket, kept:

> You recorded this one by hand, so the stake above is the figure you typed in
> — not Kalshi's record of what it charged.

It may not report a lookup, and a test refuses the phrases that would. The
`no_order_row` sentence is **deliberately not softened**: with the five false
alarms moved off it, it now fires only on a real gap and has to keep reading
like one, which is also pinned.

### A2.4 What this does not establish

- **Nothing about the hedge figure.** §6 stands word for word: at least four
  error terms of mixed sign, and naming whose price the stake is narrows none
  of them. Renaming a refusal narrows less than that.
- **That any of the five positions is correctly recorded.** It says only that
  nothing was searched for, which is what the code can prove. Whether the
  stake Joe typed matches what Kalshi charged him is unreadable from here and
  is E2 on an `as_recorded` row, exactly as before.
- **That a `no_order_row` row is a lost write.** It now means the key was
  formed and matched nothing, which a hand-typed `combo_ticker` naming a real
  market also produces. `combo-position-orphans`' own "cannot tell which"
  caveat applies unchanged.
- **That anything renders.** Source text, a node-executed `stakeBasisNote`,
  and `tsc`; no browser, the same limit every guard on this screen has.

### A2.5 Verification

`tests/test_stake_basis_is_the_venue_fill.py` (27) and
`tests/test_the_hedge_card_names_the_fallback_reason.py` (19) green, `tsc`
exit 0 from the lane. Four mutations were applied to the guarded code and
every one turned the suite red: the `_order_key` branch removed from
`stake_basis_for` so both facts share `no_order_row` again (the pre-fix
behaviour), the `hand_recorded_position` entry deleted from the gloss, the
hand-recorded sentence given wording that reports a search, and the
`no_order_row` sentence softened into the hand-recorded one -- the last
because a guard over a sentence this ADR promises NOT to change is the one
most likely to be decoration. Each file was
restored from a byte backup and verified md5-identical afterwards; `git
checkout` was not used, because it erases uncommitted work.
