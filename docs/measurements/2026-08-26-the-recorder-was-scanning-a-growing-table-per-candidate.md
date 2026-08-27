# The recorder was scanning a growing table once per candidate, and it starved the API

**Date:** 2026-08-26, ~23:05Z
**Instance:** live, `git_sha 7a5acc3`, uptime 60+ minutes (no crash-loop
involvement — that was fixed and verified earlier the same day).
**How it was found:** trying to read `/api/parlays` on live to pick combos for
a different measurement. It returned **500**.

## What was observed

`/api/parlays` returned 500 after 30.4s. The live log said:

    Failed to proxy http://127.0.0.1:8000/api/parlays Error: socket hang up

A **timeout**, not an exception — Next's proxy giving up.

Every other route was degraded too, which is what ruled out a parlay-specific
regression:

| route | earlier today, quiet | 23:05Z |
|---|---|---|
| `/api/health` | 0.15s | 1.63s |
| `/api/window` | 0.32s | 17.75s |
| `/api/board` | 0.18s | 4.06s |
| `/api/slate` | 0.38s | 24.64s |
| `/api/parlays` | 2.32s | 30.4s → **500** |

The pass log named the load:

    pass 74  quote  took_s 43.6   leg_price_persist_ms 34166
    events_discovered 726   markets_quoted 8007
    fair_prices_written 290  recommendations 4  unchanged_confirmed 347

**Quote passes run on a 15-second cadence and were taking 35–74 seconds**, with
26–40s of that inside one leg. `tasks/NEXT.md` records those passes at
**3.0–3.2s**. Three processes share one vCPU, so a recorder that cannot finish
inside its own cadence starves every API route.

## The cause, confirmed by the planner rather than inferred

34 seconds to persist 290 fair prices and 4 recommendations is ~97ms per row,
which is not a write cost. `_review_and_persist` calls
`engine.persist_if_changed` **once per candidate** — ~351 of them — and that
function's first act is:

```sql
SELECT id, entry_ask_tenths, fair_probability FROM recommendations
WHERE ticker = ? AND side = ? ORDER BY created_ms DESC, id DESC LIMIT 1
```

`recommendations` carried three indexes: `created_ms`,
`(suppressed_reason, created_ms)`, and a partial on `clv_scored_ms`. **None on
`(ticker, side)`.** `EXPLAIN QUERY PLAN`:

    SCAN recommendations
    USE TEMP B-TREE FOR ORDER BY

A full scan **and** a temporary sort, ~350 times per pass, every 15 seconds,
against a table that grows and is never trimmed.

## The fix

```sql
CREATE INDEX IF NOT EXISTS idx_recs_ticker_side
    ON recommendations(ticker, side, created_ms DESC, id DESC);
```

    SEARCH recommendations USING INDEX idx_recs_ticker_side (ticker=? AND side=?)

The trailing columns are load-bearing and mutation-verified: an index on
`(ticker, side)` alone still satisfies the WHERE and then **sorts**, which on
this query is the more expensive half — it materialises every row for that
ticker before taking one.

No migration entry and no `SCHEMA_VERSION` bump: `init_db` applies `schema.sql`
unconditionally after `migrate`, so a `CREATE INDEX IF NOT EXISTS` reaches an
existing volume at the next boot. Same path `desk_attention`'s index took at
v21.

## Football was the trigger, not the cause

The cost is `rows × candidates`. Adding NCAAF roughly doubled discovery (~510
events historically → 726) and the candidate count with it, pushing a
long-standing quadratic from tolerable into pathological. The index would have
been worth adding a month ago; the football deploy is what made it urgent.

## What this corrects in the record

**The serving-path baseline taken at 17:00Z the same day is misleading, and by
its own stated caveat.** That document says the reading must be *"split by
whether a full pass was running"* — and then its numbers were quoted as "warm"
without that split. They were taken in a quiet window, between passes, with
MLB's odds window shut.

The honest picture is two different machines: **idle, the serving path is
fast; under a running pass, it is unusable.** The 17:00Z table measures the
first and says nothing about the second.

That also overturns this session's ranking a second time. The plan ranked the
`/api/slate` read-path N+1 first; the 17:00Z measurement demoted it to 0.38s
and promoted `/api/parlays`; this measurement says the thing a person actually
waits on is neither — it is a **write-path** N+1 in the recorder, starving both.

## What this does not establish

- **That live is now fast.** The plan change is a precondition. The re-read
  must happen on the box, under load, split by whether a pass is running.
- **That the shared vCPU is now sufficient.** Removing a quadratic is not the
  same as having headroom, and a full pass still costs 139s.
- **That 3.0–3.2s returns.** That figure predates football; the slate is
  larger now and some increase is real work.
- **Anything about the other four `_BASIS_SQL` full scans** on
  `recommendations` (`routes.py:967-999`, `:1171-1206`), which are read-path
  and were not measured here.
