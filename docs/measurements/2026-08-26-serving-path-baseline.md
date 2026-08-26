# The serving path, measured for the first time — and a registered trigger fires

**Date:** 2026-08-26
**Instance:** live, `git_sha e43f551`, warm (79 and 70 minutes uptime confirmed
on the two preceding images).
**Method:** `curl` from outside, over the public surface, with a
`cockpit_session` cookie minted from `APP_AUTH_TOKEN` — so this is the pipeline
a phone actually traverses (middleware → Next rewrite → uvicorn → SQLite), not
the loopback backend.
**n:** three consecutive samples per route, first sample cold.

## Why this had never been taken

Every latency document in this directory is about the **recording loop**.
`docker/entrypoint.sh` runs uvicorn with `--no-access-log`, so no request
duration exists in the log stream either. The serving path had no number of any
kind.

It could not have been taken honestly before today: until this morning the
machine was crash-looping and spent most of its time switched off
(`2026-08-26-live-was-off-between-visits.md`), so any reading would have been
dominated by cold starts.

## The reading

```
route            cold      warm      warm
/api/health     0.15s     0.15s     0.14s
/api/window     0.32s     0.32s     0.32s
/api/board      0.18s     0.18s     0.16s
/api/signal     1.53s     0.12s     0.11s    (300s in-process cache)
/api/slate      5.94s     0.41s     0.38s
/api/parlays    9.96s     2.32s     2.28s
```

## Two findings, and the first one overturns a plan

**1. `/api/parlays` is 2.3s WARM, and that crosses a trigger registered in
advance.** `tasks/NEXT.md`, written 2026-08-26 before any of this:

> The stated stop-work trigger was 1s on `/api/parlays`; it was not reached, so
> no payload cache was built.

It is now reached, 2.3× over. The cause was recorded in the same entry:
`_joint` runs a **200,000-sample Monte-Carlo copula five times per distinct leg
set**, and the memo that deduped it was local to `build_ladder` — so six cards
shared work within one build and every HTTP request started from nothing. The
loop path is gated on `counts.odds_sweeps > 0 or kind == "full"`; the HTTP path
had no equivalent.

**This reranked the planned work.** The plan for this session ranked the
`/api/slate` N+1 into `kalshi_quotes` first, on the strength of reading the
code. Warm, `/api/slate` is 0.38s. The N+1 is real and is not what a person
waits on.

**2. Cold is 15–30× warm, on identical statements.** That is the page cache,
not the query plan. A connection is opened per request and SQLite's default
cache is ~2 MB, against a hot index measured at 476 MiB
(`2026-08-19-live-oom-killed-itself.md`).

## What was changed on the strength of it

| | change | measured effect |
|---|---|---|
| 1 | The joint memo moved from a local dict to a bounded module-level cache | payload build **345ms → 2ms** on a warm cache, in-process |
| 2 | `cache_size` (16 MiB read / 4 MiB write) and `temp_store = MEMORY` | not yet re-measured on live |

**Change 1 is a memo, not the payload cache the trigger named, and the
substitution is deliberate.** A payload cache must guess an expiry, and between
refreshes it would serve stale leg ages, a stale ask and a stale freshness
verdict — on the one screen whose job is saying how old its inputs are.
`_joint_key` already carries every field `_joint` reads (its docstring says so
and a test pins it) and the copula is seeded, so an equal key is an equal
answer by construction. Nothing expires because nothing can go stale.

**Change 2 is deliberately modest and omits `mmap_size`.** This box has
OOM-killed itself once; page cache available was measured at ~130 MB steady and
~76 MB during a full pass, and `mmap_size` competes with that rather than
adding to it.

## What this does not establish

- **That live is now faster.** Change 1 is measured in-process on a seeded
  fixture; change 2 is not measured at all yet. The re-read has to happen on
  the box, and it has to be **split by whether a full pass was running** — a
  full pass costs 33–114s of saturated CPU every 900s on a shared vCPU, so an
  unsplit average would pool two different machines.
- **That the remaining query work is worthless.** The `/api/slate` N+1 and the
  unbounded `GROUP BY odds_snapshots` are real and get slower as the tables
  grow (`odds_snapshots` has no retention rule at all). They are simply not
  what a person waits on today, and the honest order is to re-measure before
  spending on them.
- **Anything about the first hit after a deploy.** Every deploy empties the
  page cache, so the cold column is what the first visitor pays after every
  release. Change 2 addresses the depth of that hole, not its existence.
- **n = 3 per route, one session, one time of day.** Enough to separate 2.3s
  from 0.38s; not enough to state a distribution, and no distribution is
  claimed.
