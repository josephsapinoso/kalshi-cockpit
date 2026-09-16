# 0159 — The census is bounded, and the index it was approved to buy is refused

**Date:** 2026-09-16
**Status:** accepted
**Extends:** ADR 0157 (an instrument may not charge its cost to the desk), from
`prop-bookmakers` to `fair-prices-by-market`.
**Applies:** ADR 0141 (a plan diff cannot price an index; only a timing can) —
and this is the first time that rule has refused an index rather than bought
one.
**Schema:** none. See §"What is NOT in this ADR".

## Context

`fair-prices-by-market` is two bare `GROUP BY market` aggregates with no
predicate at all: section A over `odds_snapshots`, section B over
`fair_prices`. Those are the two largest tables on the box. That is the shape
ADR 0157 forbids — the cost does not land on the session that runs the query,
it lands on whoever touches the desk next, because the scan evicts the page
cache the live reads run through.

Joe approved the fix on 2026-09-15: *make it fast, at the cost of a one-time
index build on live of roughly three minutes.* The brief handed over was

> schema **v45** — an index on `fair_prices` that makes a time bound seekable
> — plus the migration in `db.py`, plus bounding both queries with a default
> window, plus the plan guards.

and it recorded, correctly, that none of `fair_prices`' three indexes leads
with `computed_ms`, so a `--since` added on its own would filter after the scan.

**The brief was right about the defect and wrong about the remedy, in both
halves.** ADR 0141 requires an index to be bought on a timing. The timing was
taken (`scripts/measure_fair_price_window_index.py`, 10,112,298 modelled rows
at live's shape, 8 MB page cache, seven-day window, round-robin, five rounds):

    arm                                  median      vs today    size on live
    unbounded, no statistics          17,270.0 ms       1.00x            —
    bounded, no statistics               883.0 ms      19.56x         free
    bounded + new index (computed_ms)    882.6 ms      19.57x       154 MB
    bounded + new index (covering)       957.9 ms      18.03x       255 MB
    bounded + ANALYZE, no new index      258.9 ms      66.70x         free
    bounded + new index + ANALYZE        239.9 ms      71.99x       154 MB
    bounded + covering + INDEXED BY       76.4 ms     226.01x       255 MB

Read the plans beside them and the shape is not a matter of degree:

    no statistics    SCAN fair_prices USING INDEX idx_fair_market_computed
    ANALYZE          SEARCH fair_prices USING INDEX idx_fair_market_computed
                            (ANY(market) AND computed_ms>?)

**The planner never chooses the new index.** With no statistics it prefers
`idx_fair_market_computed`, which satisfies the `GROUP BY`, and keeps
preferring it when the new index exists — so the 154 MB arm and the free arm
are the same number twice. With statistics it *still* prefers it, and now runs
it as a **skip-scan**: `market` has a handful of distinct values, so SQLite
seeks into each one and applies `computed_ms>?` as a range inside it.

What was missing was never an index. It was `sqlite_stat1`. **Nothing in
`backend/` has ever run `ANALYZE`**, so the live planner has no statistics for
any table and has been choosing plans from its built-in defaults since the
first boot.

## Decision

### 1. Both halves are bounded, default seven days

```sql
FROM fair_prices    WHERE computed_ms >= :since   GROUP BY market
FROM odds_snapshots WHERE commence_ms >= :since   GROUP BY market
```

`--since YYYYMMDD` moves the floor. Seven days, matching
`_BOOKMAKERS_DEFAULT_DAYS` rather than `sharp-anchor-census`' two: section A
reads the same rows on the same column as `team-bookmakers`, and a reader
comparing "what came back" against "what was consumed" across the two commands
must not be comparing two windows. Seven days also spans one weekly sports
cycle, so a market bought only on NFL Sunday is inside it on a Wednesday.

A malformed `--since` raises rather than falling back, per ADR 0157: a silently
ignored bound is an unbounded query wearing a flag.

### 2. One instant, two clocks — and the screen says so

Section B keys on `computed_ms` (when *we* devigged); section A keys on
`commence_ms` (when the *game* starts). This is not a tidiable inconsistency:
`fair_prices` has no other time column, and on `odds_snapshots` `fetched_ms`
leads no index while `commence_ms` leads one.

So a fixture can be inside A's window and outside B's. **Each section is now
preceded by its own window section naming its own column**, and the docstring's
"what this does not establish" gains the reading that would otherwise be wrong:
a market thin in B and fat in A may be an input with no reader — the finding
the command exists for — or may be a devig that fell outside seven days.

`first_ms` changes meaning with this, and that is written down rather than left
to be rediscovered: it used to be where the surviving record starts, and it is
now the window floor or the first row after it.

### 3. The index is refused

Not deferred, not parked. **Refused, on a measurement**, and Joe's approval of
it is spent rather than outstanding: he approved a fast census at the price of
an index, and the fast census is delivered without the index. 154 MB (or
255 MB) of resident pressure on a 2.0 GB box with no swap, in exchange for a
plan the planner declines to use, is not a cheaper version of the thing
approved — it is nothing, at full price.

**The write side was measured and is NOT part of the argument**, which is
worth saying because it is the objection anyone would reach for first. One
400-row pass, best of five: 2.52 ms with no new index, 2.83 ms with the
non-covering one, 2.53 ms with the larger covering one. The covering index
coming out *faster* than the smaller one is the tell — at n = 5 on a quiescent
desktop this did not separate from noise, so the refusal rests on the read
timing and the resident bytes, and the write amplification is left as an
unquantified cost rather than quoted as one.

The one configuration that beats statistics — a covering index plus
`INDEXED BY` — is also refused. It is 3.4x faster than the free arm and costs
255 MB on the box whose *binding resource is the page cache*, for a command run
a handful of times a week. ADR 0141's own reasoning bought
`idx_odds_event_commence` because it **reduced** page traffic for a continuous
read; this would increase resident bytes to speed up an occasional one.

### 4. Section A's bound is a filter, and is called one

`idx_odds_window` (schema v41) leads with `market`, covers section A's select
list and satisfies its `GROUP BY`, so the planner scans it whole and applies
`commence_ms` — its fourth column — as a filter. `ANALYZE` does not change
that; measured both ways. `idx_odds_commence` is never reached.

The bound is kept: it removes rows from the answer and from two DISTINCT temp
B-trees. It is **not** described as a seek anywhere, because the repo has
already paid for a flag that looked like a bound and was not
(ADR 0157 §"Found while verifying", `tasks/lessons.md` 2026-09-16 first).
Whether forcing `INDEXED BY idx_odds_commence` is an improvement is a timing
question on the real distribution, and
`scripts/rehearse_fair_price_window.py` runs both arms on the paced copy rather
than this ADR guessing.

## What is NOT in this ADR, and why there is no schema v45

**`ANALYZE` is not shipped here.** It is the purchase the measurement points
at, and it is a *global planner input* on a database whose two hottest readers
of `fair_prices` were tuned without it:

- `parlays.CANDIDATE_SQL` earned its `MULTI-INDEX OR` plan in ADR 0134
  (schema v37), on a statistics-free planner. That plan is what ended three OOM
  kills and a 4,600 ms `candidate_ms`.
- `runner.py`'s per-outcome dedupe lookup runs once per outcome, per pass.

A plan that good can be lost as easily as won, and no local benchmark can
settle it, because the thing at issue is live's real cardinality.
`scripts/rehearse_fair_price_window.py` makes a paced `sqlite3.backup` copy of
the live file (2,000 pages per 20 ms, the procedure ADR 0134's deploy used),
diffs the plan and times both of those statements before and after `ANALYZE`,
and prints a refusal if either regresses by more than 25%. **Statistics ship as
their own version, after that run, or they do not ship.**

So `SCHEMA_VERSION` stays at **44**, the next ADR is **0160**, and schema
**v45** stays unallocated. A version bump for a change that has not been
rehearsed would be the reservation problem in `docs/adr/README.md` — a global
counter claimed on an intention.

## Guards

`tests/test_fair_prices_by_market_is_bounded.py`, four mutations each observed
red:

| # | mutation | red |
|---|---|---|
| 1 | neuter `WHERE computed_ms >= :since` to a tautology | 2 tests |
| 2 | same on `commence_ms >= :since` | 1 test |
| 3 | `_fair_prices_since_ms` returning `0` with no `--since` | 1 test |
| 4 | that helper falling back instead of raising on a malformed value | 1 test |

Mutation 4 was first anchored on the `raise` line alone and silently hit
`_bookmakers_since_ms`, which has a byte-identical `try/except`; the suite
stayed green and the guard read as decoration. It is anchored on the whole
function body now. The mutations ran against a **backup copy** of the module,
not `git checkout` — a prior session lost uncommitted work in this same file
that way.

Two of the tests assert the pessimistic case deliberately:

- `test_section_B_does_not_seek_without_statistics` pins the finding this ADR
  rests on. If a future SQLite starts skip-scanning without statistics, the
  repo has a cheaper world than it thinks and finds out here.
- `test_section_A_filters_and_does_NOT_seek` pins §4, so "bounded" cannot
  quietly start being read as "seeks".

And `test_no_new_index_is_needed_for_that_seek` pins the **absence** of the
refused index, because an absence with no test reads exactly like a forgotten
task.

`tests/test_credit_and_input_queries.py` gains
`test_the_default_window_excludes_the_fixture_entirely`: its other cases now
name a floor, and without this one the default could stop being a window and
every one of them would still pass.

## What this does not decide

- **Whether `ANALYZE` ships.** §"What is NOT in this ADR". If the rehearsal is
  clean it is a one-line migration; if it is not, the census keeps the 19.6x
  the bound alone bought and that is the end of it.
- **Whether `ANALYZE` should run on any other table**, or on a schedule, or via
  `PRAGMA optimize` at connection close. Each is a wider blast radius than the
  one being rehearsed and none is touched.
- **Anything about live magnitudes.** Every number above is modelled at live's
  shape on a desktop; ADR 0141 §"What this does not establish" is why a
  benchmark that differs from production in which resource binds gives a
  direction and a floor and never a magnitude.
- **Whether the census is worth running.** This prices making it cheap.
