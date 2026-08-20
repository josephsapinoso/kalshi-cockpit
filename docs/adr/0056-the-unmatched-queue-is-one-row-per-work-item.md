# ADR 0056 — The unmatched queue is one row per work item, and the old table is drained rather than migrated

- **Status:** accepted, 2026-08-19
- **Supersedes:** nothing. Amends ADR 0054's `unmatched_events` half.
- **Related:** ADR 0055 (the same shape applied to `kalshi_quotes`), ADR 0054
  (the retention window this reuses)

## Context

`unmatched_events` is the linker's work queue: a row per Kalshi event it could
not match to a sportsbook fixture, carrying the team names as seen so a person
can fill in an alias file. It has never been read by production code. Nothing
joins it, no route serves it, no dbt model references it —
`store/publish.py` copies it to the parquet lake and the lake has no consumer.

The linker re-derives the same failures every pass and every derivation was
appended. Measured on live 2026-08-19:

```
total rows                     788,944
distinct work items              1,376        <- 573:1
distinct (side, ident, league)     983
rows ever marked resolved            0
```

The eight worst items had appeared **2,477 times each**, with exactly **one
distinct reason** apiece — so every one of those 2,476 repeats carried nothing
the first row did not.

**`resolved` is 0 on all 788,944 rows, and that is the finding rather than a
footnote.** This is a queue meant to be worked by hand, and nobody has ever
worked it. A queue three quarters of a million long is not a queue.

## Decision

### 1. The queue is `unmatched_items`, one row per work item

Identity is `(side, identifier, league, detail, reason)`. A sighting is an
upsert: `last_seen_ms` moves, `seen_count` increments, `first_seen_ms` is
written once and never again.

**`seen_count` is the point and disk is the side effect.** "Failed once while a
fixture was being renamed" and "has failed every pass for a week" are different
pieces of work. The append-only shape *contained* that distinction and could not
present it — it was the number of identical-looking rows, across three quarters
of a million of them.

A `UNIQUE` index makes duplication impossible rather than merely unlikely.

### 2. The `COALESCE` is load-bearing in two places, and they must agree

`league` and `detail` are nullable, and **SQLite treats NULLs as distinct in a
UNIQUE index**. A bare `(side, identifier, league, detail, reason)` index would
let every NULL-league item insert afresh on every pass — the exact behaviour
this removes, surviving behind an index that reads as though it prevents it.
So both the index and the upsert's conflict target use
`COALESCE(league, '')` / `COALESCE(detail, '')`.

### 3. Retention reads `last_seen_ms`, never `first_seen_ms`

An item still being seen is still open work however old it is. Pruning on
first-seen would delete an item the linker fails on every pass, and the next
pass would write it back with `seen_count` reset to 1 — a week-long failure
presenting as new, forever, while the pass line reported a healthy prune.

### 4. `unmatched_events` is NOT migrated. It is drained and then dropped.

This is the part that changed after measurement, and it is the part worth
reading.

The obvious implementation was a v14 schema migration: build the new shape,
`INSERT ... SELECT ... GROUP BY` to collapse the duplicates, drop the old table,
rename. It was built, tested, and **thrown away after being rehearsed against
live**:

```
GROUP BY over 788,944 rows          229.4 s
DROP TABLE (181,154 pages)          217.6 s
COUNT(*) over the same table          1.6 s   <- for scale
```

Migrations run inside `init_db`, at boot, before uvicorn. A four-to-eight minute
boot is an outage with Fly's health check watching — and a machine killed
part-way re-runs the step from the top on restart, because the version stamp is
written only after the step succeeds. That is a **crash loop on the one volume
that cannot be recreated**, which is the v11 failure this repo has already
survived once.

So no migration exists. `unmatched_items` is created empty by `schema.sql`
(`IF NOT EXISTS` covers both a fresh database and the live volume), the linker
writes there from the first pass, and the old table is left exactly where it is
— drained by `prune_legacy_unmatched` in the batched, budgeted, full-pass-only
machinery ADR 0054 already built and proved, then dropped **once it is empty**,
when the drop is free.

**`SCHEMA_VERSION` does not move.** Nothing about an existing database changes
except that one more table appears, which `executescript` does on its own.

## Consequences

- **Boot cost is zero.** No scan, no drop, no rename at startup, in any state.
- **The backlog is counted separately** from the steady-state prune, because the
  two mean opposite things: one should stay small forever, the other should
  reach zero and stay there. Summed, a draining backlog looks exactly like the
  steady state misbehaving.
- **Two similarly-named tables coexist** until the drain finishes. This is the
  real cost, and it is why `LEGACY_UNMATCHED_TABLE` is a named constant: the day
  it can be deleted, `grep` finds everything that goes with it.
- **`first_seen_ms` starts at "now" for every item**, because the old table's
  history is discarded rather than collapsed. The age of a failure is unknown
  for the first week. Small, one-time, and the alternative was the 229s scan.
- **The lake now receives `unmatched_items`.** Old partitions keep the old
  column names; nothing reads either.

## What this does NOT establish

- **Not that the queue will be worked.** Nothing sets `resolved` and no code
  path does. A readable queue is a precondition, not a result.
- **Not a latency improvement.** `record_unmatched` appeared once at 8,162 ms in
  a `link slow` line, on a box minutes from an OOM kill. **Every number taken
  from that box describes the starvation** — see the correction at the foot of
  `docs/measurements/2026-08-19-the-prune-loses-to-the-writer.md`, which is the
  same mistake made twice in one day. Fewer rows behind a smaller index should
  cost less; that is a prediction, and the pass line is where it gets checked.
- **Not that 229s and 218s are properties of the disk.** They were taken from a
  box concurrently serving quote passes at ~50% IO pressure, and the recorder's
  age rose from 5.9 s to 28 s while the rehearsal ran. They may overstate a
  quiet box considerably. **The decision deliberately does not depend on how
  much** — the design chosen is O(1) at boot whether the disk is fast or slow,
  which is the right shape when the number is uncertain rather than a reason to
  go and re-measure it.
- **Not that the drain will finish in any particular number of passes.**
  788,944 rows at `DELETE_BATCH = 20,000` is 40 batches. How many fit in a 30 s
  budget on this table has not been measured; the healthy-box quote prune
  cleared 440,000 in one, so one to three full passes is the expectation and
  not a result.
- **Not that 573:1 will hold.** It is a ratio between a table that grows without
  bound and a work list that does not, so it is a function of how long the table
  has been accumulating. It was ~548:1 four hours earlier in the same day.
