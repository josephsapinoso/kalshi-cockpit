# 0161 — The ANALYZE line is retired, and its park is deleted

Date: 2026-09-16
Status: accepted
Scope: `tasks/NEXT.md` (the park is removed from the Open list). **No code
change, no schema change, no migration.** `SCHEMA_VERSION` stays 44 and v45
stays unallocated.

Ticket: issue #51, answered `51A` by Joe on 2026-09-16 and closed with his
answer quoted. This decides the first bullet of ADR 0159's "What this does not
decide" — *whether `ANALYZE` ships*. ADR 0159 is **not edited**; it was right
about its own scope and this is the successor that closes the question it left
open.

---

## 1. What is retired

`ANALYZE` will not be run on live as a consequence of the ADR 0159 line of
work, and the conditional park that carried it —

    unpark only if a route-latency read shows a desk route over the 25 s read
    budget AND the plan implicates `fair_prices`

— is deleted from `tasks/NEXT.md` rather than carried into another session.

The **finding** behind it is untouched and needs nothing: live has no table
statistics at all (`sqlite_stat1` ABSENT, read on the box 2026-09-16), so
every query plan on the machine is chosen from SQLite's built-in guesses.
That is banked in ADR 0159 and is a true and useful fact. Retiring the line
means nobody is on the hook to act on it.

## 2. The reason — and it is deliberately NOT the latency read

`docs/measurements/2026-09-16-desk-route-latency-warm-box.md` timed thirteen
desk routes and three league chips and found medians of 75 ms to 1,727 ms
against a 25,000 ms budget. **That is not the reason, and it must not be cited
as one.** Its own §D records why: it measured a warm box, which is the one
regime where the budget was known in advance not to fire, and the budget has
in fact been reached twice — once by a plan defect since fixed, once by a
page-cache eviction that is structural and unfixed. The park's first conjunct
was never exercised. A measurement-skeptic pass refused the deletion on
exactly that ground and the refusal was correct.

The reason is ADR 0159's own live rehearsal, `:230`:

    CANDIDATE_SQL   1,177.0 ms -> 1,157.5 ms   1.02x   plan UNCHANGED

`parlays.CANDIDATE_SQL` is the statement behind `/api/parlays` — the desk's
slowest route and the one with a real 503 at the read budget (2026-09-10).
`ANALYZE` moved it by 2% and did not change its plan at all.

**Why this line is usable when its neighbours are not.** ADR 0159:239-247
disowns its own rehearsal's magnitudes: the arms were timed roughly thirty
minutes apart, and the sibling bench records the same query reading 1,283 ms
and 3,904 ms on cache residency alone — a 3.04x swing that brackets the 3.37x
the rehearsal claimed for the census. A **plan-unchanged, ratio-≈1.0** result
does not inherit that defect, because it is not a magnitude claim: cache noise
moves a duration, it does not make SQLite choose the same plan twice. ADR 0159
itself relies on this same line for a different conclusion — that ADR 0134's
`MULTI-INDEX OR` survives `ANALYZE`.

So the second conjunct is what fails, and it fails on evidence that survives a
cold box, a Saturday NCAAF slate and a page-cache eviction alike.

## 3. What the 3.37x was, and why it does not buy the line back

The rehearsal measured `ANALYZE` at 3.37x on the bounded
`fair-prices-by-market` census. Two reasons that does not reopen this:

- **It is inside its own instrument's noise band** (§2 above), so it is a
  direction, not a magnitude.
- **Even taken at face value it applies to an instrument, not a screen.**
  `fair-prices-by-market` is run a handful of times a week by a session, and
  ADR 0159 already made it 322x faster by bounding it. Nothing Joe taps is
  waiting on the remaining factor.

## 4. The caveat, recorded here because the park is gone

**This retires the tuning work. It does not solve the cold-start 503, and
nothing in this ADR should be read as saying that path is healthy.**

`/api/parlays` returned 503 `read_budget_exceeded` on 2026-09-10 after two
full-table `GROUP BY`s over `fair_prices` evicted the page cache;
`ladder_candidates` then took **74.8 s** cold in the container — 3x the budget
— against 2.15 s warm. The condition is structural: `scripts/warm_read_path.py`
records 2.0 GB of RAM with no swap, a 5.43 GB database and a page cache topping
out near 1.49 GB, so **at most ~27% of the file can ever be resident**, and
"every restart is a coin flip on a 503, and restarts are not rare."

`ANALYZE` was never a candidate fix for that — the plan is already right, the
pages are simply not in memory. A deleted park is not evidence of health, and
this section exists so that a later reader who finds no open item does not
infer one.

## 5. What this does not decide

- **Whether `ANALYZE` should ever run on any table.** A successor may propose
  it on its own merits; it must interleave its arms (ADR 0159:247 states the
  shape) and must not cite this ADR as prior approval.
- **Anything about the ~27% residency ceiling**, the 2 GB box, or the
  cold-start 503. §4 is a caveat, not a plan.
- **Whether `ANALYZE` would help the Saturday NCAAF slate.** The
  `/api/slate?league=americanfootball_ncaaf` chip read 1,098 ms then 3,951 ms
  on consecutive Wednesday reads and that 3.6x is unexplained at n = 2. If it
  becomes a problem the first question is the window size, not the statistics.

## 6. Guard

None, and that is the honest answer. This ADR deletes a line from a
session-notes file; there is no code to pin and inventing a test that asserts
the absence of a sentence in `tasks/NEXT.md` would be decoration — the file is
rewritten every session by design, which is the whole reason CLAUDE.md workflow
step 7 exists and why this decision is an ADR and a closed ticket rather than a
line in that file.

What carries the decision forward is: this ADR, issue #51 closed with Joe's
answer quoted, and `docs/measurements/2026-09-16-desk-route-latency-warm-box.md`
§D, which records the refused conclusion so the next session to run a latency
read does not repeat it.
