# ADR 0172 — A price too fine to print is not nobody quoting

**Status:** Accepted
**Date:** 2026-09-18
**Ticket:** #73 (build, no decision needed), from the sharp-bettor pass over the
RFQ path
**Supersedes nothing. Amends nothing.** `_exact_tenths`'s refusal is unchanged
and stays.

---

## 1. The defect

A combination market carries `price_level_structure:
center_deci_edge_centi_cent` — it ticks in **hundredths** of a cent below 1c and
above 99c. This repo's money convention is integer tenths of a cent
(`core/prices.py`), so a maker quoting `"0.0055"` names a real, tradeable price
that the desk **cannot represent**.

`_exact_tenths` refused it rather than rounding, and that is correct and is not
what changed here: rounding `"0.0055"` to 6 tenths would print a price the venue
never offered, on the path that spends.

What was wrong is what happened next. `parse_quotes` logged the refusal and
`continue`d, so the refusal existed only in a log line nobody reads. If every
quote was refused, `_words` reached its empty branch and the screen said:

> "Nobody quoted this combination within a few seconds."

**Makers did quote.** Those are two different facts and the second is the
actionable one — the price is readable in the Kalshi app, so the answer is "go
and look", not "try again later".

This bites hardest on cheap longshot combinations, which is exactly where the
centi-cent region is. The one live combination trade this repo has made was at
**0.40c**, one tick inside it.

It is also this repo's named recurring failure — a screen stating something the
server does not match — on the newest armed surface, and the fifth time it has
run.

## 2. The decision

**Three outcomes on the price surface, not two.**

- `parse_quotes` returns a **`QuoteRead`**: the quotes, plus the ids it refused,
  split by reason (`refused_finer_than_tenths`, `refused_unreadable`).
- `_read_tenths` returns `(tenths, reason)`. `_exact_tenths` survives as a
  one-line wrapper, so the precision rule lives in **one** place and cannot
  drift between the parser and the classifier.
- The payload gains `status: "priced_too_finely"` and `refused_too_fine: int`.
- `_words` gains a branch for it, and mentions the drop **even when there is a
  price**, because a refused centi-cent quote near 0c would have sorted first —
  a screen showing a price in silence can be showing the second-cheapest number.

### Two things that are decisions, not details

**The refusals carry quote ids, not counts.** `await_quotes` polls the same RFQ
every `QUOTE_POLL_S` for `QUOTE_WAIT_S`, and a quote refused on one pass is
refused on every pass. A count would multiply by the number of reads and tell
Joe six makers answered when one did. Real quotes are already accumulated across
polls into `seen` for the same reason — a maker can answer late or cancel — and
the refusals are unioned by id beside them.

This is ADR 0169's `record_quotes` correction inherited rather than re-learned:
an id assigned by someone else is the only thing that makes "seen twice" one
thing.

**`quoted` outranks `priced_too_finely`.** If even one quote is representable
there is a price to show, so the status stays `quoted` and the refusals go in
the words. The reverse precedence would hide a takeable price behind a
complaint.

**`unreadable` is deliberately NOT actionable.** A garbage price, or a `no_bid`
of `0.0000` (whose complement is a settled outcome, not an offer), is not a
price too precise to print. Telling Joe to go and look for it would send him
after something that is not there, so those refusals are counted separately and
say nothing to the reader.

## 3. What did NOT change, and one of them is a defect left standing

- **The frontend needed no logic change.** `Quotes()` already renders
  `value.words` on `status === "no_quotes" || quotes.length === 0`, so the new
  branch reaches the screen through the existing path. Only the TypeScript type
  moved, which keeps `tsc` honest about the third status.
- **`_exact_tenths`'s refusal.** Unchanged. The desk still never rounds a price
  onto the money path.
- **`combo_rfqs.status` in the database still records `no_quotes` for an RFQ
  whose makers all quoted too finely**, and that is the same false record in the
  durable store rather than on the screen. Its `CHECK (status IN ('asked',
  'quoted', 'no_quotes', 'error'))` has no third value, and SQLite cannot widen
  a CHECK without rebuilding the table — a schema bump and a migration.
  **Deliberately deferred to its own ticket rather than folded into a "smallest
  build", because it contaminates any later measurement of how often a
  combination goes unquoted.** Named here so it is a known gap and not a
  discovery.

## 4. Verification

`68 passed` across `tests/test_combo_rfq.py` and
`tests/test_combo_rfq_route.py`. **Eight mutations, all red:**

| | mutation | result |
|---|---|---|
| M1 | the words branch folded back into "nobody quoted" | red, 5 failed |
| M2 | a too-fine price classified as merely unreadable | red, 6 failed |
| M3 | `parse_quotes` files every refusal under unreadable | red, 6 failed |
| M4 | an untradeable price counted as too fine | red, 1 failed |
| M5 | the refusal not mentioned when there IS a price | red, 2 failed |
| M6 | the status never becomes `priced_too_finely` | red, 2 failed |
| M7 | `priced_too_finely` outranks `quoted` | red, 1 failed |
| M8 | the poll loop overwrites instead of unioning | red, 1 failed |

**M8 was green on the first pass, and that is the finding worth keeping.** The
test asserted that the loop polled more than once and that the count was 1 —
and with `too_fine = set(read.…)` instead of `|=` the count is **still** 1,
because a constant fake returns the same refused row on every read. The
mutation was behaviour-preserving against that fixture, so the test was
decoration. Pinning the union needs successive reads to **differ**: the
replacement serves a different refused quote per poll, where replacing reports 1
and the truth is 2.

M4 also had to be re-aimed: its first pattern matched `unreadable.add(row_id)`
in two places, and a mutation script that silently patches the wrong one of two
matches proves nothing.

## 5. What this does not establish

- **Nothing about how often a real maker quotes in centi-cents.** One live trade
  at 0.40c is an existence proof for the region, not a rate. If it turns out to
  be common, the right response is a different price representation, not a
  better sentence.
- **Nothing about whether such a quote would have filled.** The desk refuses the
  price before anyone can act on it, so the only honest claim the screen makes is
  that a price existed and is not shown here.
- **Nothing about the database row**, per §3.
- **Nothing about the wording being Joe's.** The copy is derived from the facts
  the ticket states, and the ticket says no decision is needed. It replaces a
  sentence that was false; it has not been ratified.
