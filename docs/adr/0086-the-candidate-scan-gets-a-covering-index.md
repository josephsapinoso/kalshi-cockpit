# ADR 0086 — The candidate scan gets a covering index, and the refusal that came before it stands

Date: 2026-08-30
Status: accepted
Relates to: ADR 0054 (quote retention), ADR 0055 (the prune ceiling)

## Context

`runner.MATCH_CANDIDATE_SQL` is the fixture-matching scan, run once per sport
per pricing pass:

    SELECT DISTINCT odds_event_id, commence_ms, home_team, away_team
    FROM odds_snapshots WHERE sport_key = ? AND commence_ms >= ?

with `since_ms = now - 24h`.

**`sport_key` is in no index.** `schema.sql` ships
`idx_odds_event(odds_event_id, market, fetched_ms DESC)` and
`idx_odds_commence(commence_ms)`, so SQLite seeks `idx_odds_commence` to the
24-hour floor and scans **every sport's** rows forward from there — a range
with no upper bound, because the predicate deliberately keeps every future
fixture — fetching each row from the table to test `sport_key`, then feeding
the survivors through a temp B-tree for the `DISTINCT`.

On 2026-08-30 that reached **27.7 s**. The pass took 104 s, the API's read
connections starved behind it, **the Fly health check on port 3000 failed at
22:06:03Z**, and `/api/market`, `/api/window` and `/api/scout` all returned
socket-hang-up in the same minute. From the outside that read as "the scout
desk returned 500". It was not a Scout bug.

The table is the fourth-largest btree on the live volume — **244 MB across
59,665 pages** — and has **no retention rule at all**.

## Decision

**Add `idx_odds_sport_commence(sport_key, commence_ms, odds_event_id,
home_team, away_team)` — the covering form, not the narrow one.** Schema v31.

The choice between the two is settled at plan level rather than by a stopwatch:

| index | query plan |
|---|---|
| baseline, as shipped | `SEARCH ... USING INDEX idx_odds_commence (commence_ms>?)` + `USE TEMP B-TREE FOR DISTINCT` |
| narrow `(sport_key, commence_ms)` | `SEARCH ... USING INDEX ... (sport_key=? AND commence_ms>?)` + `USE TEMP B-TREE FOR DISTINCT` |
| covering, five columns | `SEARCH ... USING COVERING INDEX ... (sport_key=? AND commence_ms>?)` |

The narrow form restricts the seek and leaves both remaining costs standing: a
table fetch per surviving row for the three projected columns, and the sort.
The covering form removes both, and the `DISTINCT` becomes a walk in index
order.

**That last line is the decision.** A plan without `USE TEMP B-TREE` is not a
faster version of one with it; it is a different algorithm, and it is the one
whose cost does not follow the table's growth.

Measured on 1.5M synthetic rows of the real shape (520,160 of them at or after
the floor, to keep 73 fixtures):

| shape | read warm p50 | sweep write p50, 900 rows | index |
|---|---|---|---|
| baseline | **394 ms** | 3 ms | — |
| narrow | **283 ms** | 4 ms | 47.0 MB |
| covering | **0 ms** | 7 ms | 52.8 MB |

All three return the same 73 fixtures, **compared as sets and not as counts**.
`docs/measurements/2026-08-30-the-candidate-scan-index.md`.

## Why this is not the index this repo already refused

`schema.sql` carries a refusal on this exact table, added and removed within
the hour on 2026-08-26:

> A second index on `(odds_event_id, commence_ms)` was added on 2026-08-26 and
> removed the same hour, **because it changed no plan.** … It would have cost
> write amplification on the highest-volume table in the system to buy nothing,
> which is what an index that changes no plan always is.

That refusal is correct and stands. Its stated test — *does the plan change?* —
is the one applied here, and here it changes twice over: the seek becomes
selective and the sort disappears. The precedent is not "this repo does not
index `odds_snapshots`"; it is **"this repo does not buy an index that changes
no plan"**, and the two are easy to confuse a year from now.

## The objection, and why it does not carry

`fly.live.toml`'s `[[vm]]` comment, written after the box OOM-killed its own
loop on 2026-08-19: *"A larger index eats a larger cache."*

Right objection, and the answer is not that the index is small. It is that
**this index reduces the page traffic of the query it serves.** Today the pass
drags ~520,000 table rows through a page cache measured at 27–135 MB against a
1.5 GB database, every time it looks; afterwards it walks a contiguous index
range and does not touch the table. Resident bytes go up by the size of the
index; bytes moved per pass go down by orders of magnitude.

The write cost is the other half and it is a number, not a worry: **3 ms → 7 ms
per 900-row sweep**, n = 15. Roughly double, and trivial against a read that was
394 ms every pass and 27.7 s on live under contention.

**The live index will be larger than the synthetic 52.8 MB** — synthetic team
names are short and uniform, real ones are not. `idx_odds_event` is 136 MB
against its 244 MB table with two TEXT columns; this has four. Expect it
bracketed between those, taking the volume from ~41% to ~46% of 5 GB. The real
figure is to be read with `db-sizes` after the first v31 boot; that is a
follow-up, not an assumption.

## The health-check grace period goes 40s → 120s

`docker/entrypoint.sh` runs `scripts/migrate_db.py` **before** uvicorn binds
port 3000, so every second the migration takes is a second before the first
health check can pass. Building this index is a full read of a 244 MB table
plus a sort, on a shared-cpu-1x box with 2 GB. It took 3.0 s on 266 MB of
synthetic rows on a laptop; **nobody has timed it on the real box**, and 40s
was not a margin — it was a number that happened to hold while migrations only
ever added columns.

A longer grace period hides nothing: `set -e` aborts the container on a failed
migration, and Fly notices an exited machine without waiting for a check. What
it delays is only the verdict on a machine that is still working.

`fly.demo.toml` stays at 40s deliberately. Its database is seeded and small, so
the build is fast there — and if a future migration is genuinely slow, demo is
where that should surface first.

## Consequences

- **`SCHEMA_VERSION` becomes 31**, with a `_MIGRATIONS` step.
  **`schema.sql` alone would in fact create this index on the live volume** —
  `executescript` runs on every open and `CREATE INDEX IF NOT EXISTS` is not a
  no-op on a database that lacks it. The step exists so that
  `scripts/migrate_db.py` verifies at boot, by name, that the index is actually
  there, and so the shape change carries a version stamp. That is stated
  explicitly because the first test written for it asserted the wrong thing —
  see below.
- **`MATCH_CANDIDATE_SQL` becomes a module constant in `backend/runner.py`.**
  The benchmark times it and the guard reads a plan from it, so there is one
  copy and no transcription. Same convention as `_SQL_PARLAY_CANDIDATES`, and
  for the same reason: a plan measured for SQL nobody runs reads as evidence.
- **The guard is a plan assertion, not a timing one.** `COVERING INDEX`
  present, `TEMP B-TREE` absent, in `tests/test_candidate_scan_plan.py`. A
  stopwatch on a shared machine is a flake; a plan is deterministic, and the
  plan is the property that was bought. The file also demonstrates the real
  failure mode — a column added to the projection and not to the index — by
  widening the statement and watching the covering read disappear.
- **A test that named the migration did not exercise it.** The first version of
  the migration guard wound a database back to v30, called `init_db`, and
  asserted the index was present. It passes with the v31 step deleted —
  observed, not reasoned — because `init_db` runs `migrate` and then
  `executescript(schema.sql)`, and the schema file creates the index anyway.
  Rewritten to call `migrate` directly, it goes red on exactly that mutation.
  Recorded here rather than quietly fixed: it is the same shape as the lesson
  already in `tasks/lessons.md` about tests that name a symbol.

## What this does NOT fix

**It makes a growing scan cheaper. It does not make it bounded.**
`odds_snapshots` has no retention rule — `store/retention.py` says so in its
own "what this does NOT do" — so every sweep adds rows the 24-hour predicate
will exclude but the table keeps forever. This changes the constant and leaves
the growth term alone. A retention window on this table, the `kalshi_quotes`
treatment from ADR 0054, remains open and this is not it.

It also says nothing about `fair_prices` (529 MB) or `kalshi_quotes` (451 MB),
the two larger unretained btrees on the same volume.
