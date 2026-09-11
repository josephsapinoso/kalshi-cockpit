# ADR 0141 — A plan diff cannot price an index; only a timing can

Date: 2026-09-10
Status: accepted
Amends: ADR 0086 (the candidate scan gets a covering index), whose *conclusion*
stands and whose *stated test* does not.
Relates to: ADR 0135 (the read budget), ADR 0134 (the ladder scan keys on the
confirmed stamp)

## Context

ADR 0086 needed to justify adding an index to `odds_snapshots`, the
highest-volume table in the system, against a standing refusal. It did that by
quoting the refusal and adopting its test, verbatim:

> A second index on `(odds_event_id, commence_ms)` was added on 2026-08-26 and
> removed the same hour, **because it changed no plan.** … It would have cost
> write amplification on the highest-volume table in the system to buy nothing,
> which is what an index that changes no plan always is.
>
> That refusal is correct and stands. Its stated test — *does the plan change?*
> — is the one applied here … The precedent is not "this repo does not index
> `odds_snapshots`"; it is **"this repo does not buy an index that changes no
> plan"**.

ADR 0086's own index was a good buy and nothing here disturbs it: it made a
seek selective and removed a sort, and §"The objection" priced the write side
at 3 ms → 7 ms per sweep with n = 15. **The decision was right. The test it
generalised was not**, and because ADR 0086 promoted that test from a one-off
note to a repo precedent, the error acquired the authority of an accepted ADR.

On 2026-09-10 that precedent cost the desk an outage in front of the operator.

## What the test misses

`EXPLAIN QUERY PLAN` reports how a table will be **reached** — SCAN or SEARCH,
which index, which join order. It does not report how many rows the reaching
will touch, and for an aggregate the gap between those two things is unbounded.

`CANDIDATE_SQL`'s fixture subquery takes `MIN(commence_ms)` grouped by event.

    with    idx_odds_event_commence   SEARCH ... (odds_event_id=?)
    without idx_odds_event_commence   SEARCH ... (odds_event_id=?)

Identical, and the 2026-08-26 note read them correctly. But `idx_odds_event` is
`(odds_event_id, market, fetched_ms DESC)` — `commence_ms` is absent, so the
minimum can only be found by reading **every row of the group** and fetching
the column from the table: about 1,400 rows per event on live. With
`commence_ms` as the second column the minimum is the first entry of the group
and the search stops there. One plan line; three orders of magnitude of rows.

## Measurement

Live, via `scripts/inspect_live_db.py parlay-candidates-timing`, while
`/api/parlays` was answering 503 `read_budget_exceeded` at 25 s:

    whole candidate scan                        73,526 ms   (494 rows)
    odds_snapshots MIN(commence_ms) GROUP BY    26,719 ms   (703 rows)
    fair_prices rows inside the scan window            848  of 10,112,298

848 rows in the window and 73 seconds to return them, so the row count was
never the cost. Reproduced on a throwaway local database at live's shape
(800 events × 1,400 rows), warm, best of three: **503.9 ms without, 167.5 ms
with**, the two plans differing only in the index name.

Shipped as schema v39 and re-measured on live the same day:

    odds_snapshots MIN GROUP BY    26,719 ms  ->    327.9 ms      81x
    whole candidate scan           73,526 ms  ->  11,712 ms      6.3x

## Decision

**An index is bought or refused on a timing, never on a plan diff.**

1. A plan diff can prove an index **is** used. It cannot prove one is
   worthless. To retire an index, time the query; to add one, time the query.
   The plan is a hypothesis about *why* a timing came out as it did.
2. `SEARCH` is not a synonym for fast. It means an index located a starting
   point; everything after the starting point is invisible in the plan.
3. Where a plan and a timing disagree, the timing decides.

ADR 0086's precedent is narrowed accordingly: *this repo does not buy an index
that changes no plan* becomes **this repo does not buy an index that does not
pay for itself, and the currency is milliseconds**. Its own index remains
justified under the narrower rule, because §"The objection" already priced both
sides of it in time rather than in plan shape.

The tells that a plan diff is about to mislead, for whoever next reaches for
one: an aggregate over a column not in the index (`MIN`, `MAX`, `SUM`), an
`ORDER BY … LIMIT` on a column not in the index, or a `SEARCH` whose equality
is on a low-cardinality column so each "seek" lands on a large group. In each,
the access method is identical and the work is not.

## What this costs

The write-amplification objection stands and is paid deliberately, which is the
half a benefit-only argument leaves out. `idx_odds_event_commence` measured
~52 bytes per row locally — about **190 MB** against live's 3,696,485 rows, on a
box with 2.0 GB of RAM, no swap, and a 5.43 GB database whose page cache tops
out near 1.49 GB.

It is bought anyway, on ADR 0086's own reasoning rather than in spite of it:
the index **reduces** page traffic for the query it serves. It stops pulling
~1,400 table pages per event into the cache that is the binding resource on
this machine. Resident bytes up by the size of the index; bytes moved per
request down by orders of magnitude.

## Guards

`tests/test_odds_event_commence_index.py` pins the index **and, separately, the
recorded reason for it**. That separation is the point of this ADR in test
form: the index was removed once by someone reasoning carefully from a plan
diff, and if the timing that refutes that reasoning is ever deleted, the same
argument becomes available again and reads as sound.

`tests/test_ladder_query_is_indexed.py::TestEachHalfIsLoadBearing::test_a_second_odds_index_must_carry_a_MEASUREMENT_not_a_plan_diff`
is the inverted guard — it used to assert the index did not exist.

## What this does not establish

- **Nothing about any other index in the schema.** Every existing refusal keeps
  whatever justification it already has; this does not licence adding indexes,
  it changes what evidence is required to add or remove one.
- **Nothing about the cold-start problem.** A fresh machine has an empty page
  cache regardless of indexing; that is
  `scripts/warm_read_path.py` and a separate measurement.
- **Nothing about `MATCH_CANDIDATE_SQL`**, ADR 0086's own subject, which was
  measured on its own terms and is untouched.
- **It does not claim the local 3× predicts the live 81×.** It does not — and
  the reason is recorded because it generalises: the local box was CPU-bound
  with the table in memory, live is I/O-bound against a 5.19 GB file. When a
  benchmark and production differ in which resource binds, the benchmark gives
  a direction and a floor, never a magnitude.
