# 0109 — A failing bootstrap backs off rather than draining the day

**Status:** accepted, 2026-09-06. Built three days before the NFL season opens.

> Ordinal taken at commit time after `git fetch`, per `docs/adr/README.md`, with
> `git worktree list` showing no other lane running.

## Context

`decide_sweeps` bootstraps a sport that Kalshi lists but for which we hold **no
stored sportsbook fixtures at all** — there is nothing to schedule against, so
nothing about it can be priced. This is the path every new season opens through,
and NFL takes it on 2026-09-09.

Two docstrings described its bounds, and both were individually true:

- `decide_sweeps`: bootstrap is *"capped at one sport per pass, and at one
  attempt per sport per budget day: a sport the sportsbook simply does not cover
  would otherwise bootstrap on every pass and drain the day's credits in an
  hour."*
- `runner`: *"a **failing** sport would retry every 15s until the budget was
  gone — failing, because `_SERVED_SWEEP` requires `http_status < 400`, so an
  erroring sweep never enters `last_sweeps` and never starts pacing itself."*

**Together they mean the daily cap bound only on success.** The cap is the
candidate filter's `sport not in last_sweeps`; `last_sweeps` is built from
`_SERVED_SWEEP`; that predicate requires `http_status < 400`. So a sport whose
sweep kept erroring was never removed from the candidate list and was retried on
every pass of the day — which is precisely the hazard the first docstring names
in its own next clause.

Simulated over a whole budget day with every call returning 401 (2026-09-06,
against the real planner, zero credits):

```
heartbeat  60s (page open):  175 calls   700 of 700 credits   in 2h 54m
heartbeat 900s (idle loop):   96 calls   384 of 700
```

Three properties make this worse than it first reads:

1. It is stamped `BOOTSTRAP`, and `attention_credits_spent_today` counts only
   `ATTENTION` — **the 300-credit attention slice does not cap it.**
2. At the daily cap `decide_sweeps` returns `fire=()` and **every sport stops**
   until the next 10:00Z boundary. One sport the feed cannot answer for takes
   the whole desk down for the rest of the day.
3. The page-open heartbeat is the fast one, so **the failure is worst exactly
   when someone is looking.**

## Decision

**A sport whose last sweep failed waits `BOOTSTRAP_RETRY_BACKOFF_MS` (30 min)
before another bootstrap attempt.**

A new `last_failed_sweep_by_sport(conn, since_ms)` reads
`api_credits` for `endpoint LIKE '%/odds' AND COALESCE(http_status, 0) >= 400`,
over the **same budget-day start** as `last_sweeps`, so "has it swept today" and
"has it failed today" cannot disagree about which day it is.

### Why a backoff and not a per-day attempt cap

A hard cap bounds the spend and then **gives up**: the sport stays dark for the
rest of the budget day even after the upstream recovers, trading one failure
mode for another. On a season opener that is the wrong trade — the whole point
of the day is to start recording.

A backoff bounds the spend *and* keeps recovering. At 30 minutes one sport costs
at most 2 attempts an hour — **8 credits an hour, 192 a day against the 700** —
and a transient outage clears within half an hour of the upstream healing.

### Why not exponential

Exponential backoff's advantage is cheapness over a long outage, and the flat
rate is already affordable. What it costs is a recovery time that depends on how
long the failure has already lasted, which is the property that makes an
outage's end hard to predict from the outside. **A number a reader can hold is
worth more here than an optimal one.**

### Why the hold is named

A held sport is appended to the pass's refusal list, so it reaches `/api/window`
as `last_look_detail` and `WindowBanner` prints it on `/board`:

```
baseball_mlb bootstrap held for 20min more: its last sweep failed at
14:31Z and a failing bootstrap is not paced by anything else
```

A backoff that said nothing would be the one refusal with no reader — the shape
this module has had to fix four times (the attention-slice fall-through). The
wait is given in minutes so a reader knows whether to come back.

## Consequences

- **A transport failure is deliberately not counted.** `fetch_odds` raises
  before recording when the request never completes, so it costs no credits and
  writes no row. A call that spent nothing needs no backoff to bound its spend.
- **`COALESCE(http_status, 0)`, not a bare comparison.** Every pre-v21 row has
  NULL here because the column did not exist, and those rows were *served*
  sweeps — so the default must be a success value.
- **The successful path is untouched.** One attempt per sport per budget day
  still holds; the first sweep of a new season still fires on the first pass.
- **Six tests**, `TestAFailingBootstrapCannotDrainTheDay`, and all six were
  mutated and observed red.

### The test that could not fail, and what it taught

The guard on the `http_status` filter was first written against a sport with
**no credit row at all** — so `last_failures` was empty whether or not the
filter was present. Dropping the filter left it green, and the mutation harness
caught it.

The separating case is a call that **succeeded but is not a served sweep**: a
tap stamps `trigger = 'manual'`, which `_SERVED_SWEEP` excludes, so a tapped
sport is *still a bootstrap candidate* — and an unfiltered `last_failures` would
hold it for half an hour on the strength of a call that worked.

This is `tasks/lessons.md` 2026-09-06 for the third time in one session: **an
assertion whose fixture cannot distinguish the two cases.** Choose the fixture
by asking what the guard reads, then constructing the case where the two
readings differ.

The day-long spend test carries a **lower** bound (`attempts >= 24`) as well as
the upper ones, for the same reason: every bound that matters is an upper bound,
so a backoff that refused the sport outright would satisfy all of them with
`attempts == 0` — passing loudly while having broken the desk's ability to open
a new season. Measured: exactly 48 attempts, 192 credits.

## What this does not do

- **It does not make the cap unreachable.** The kickoff-window loop is still
  gated only by the 700 (see `CLAUDE.md`); this closes one uncapped path, not
  the general question.
- **It does not alarm.** A sport failing all day is visible in the pass detail
  and in `odds_sweep_log`, and nothing pages anyone.
- **It is not tuned.** 30 minutes was chosen for legibility against a 700-credit
  day, not fitted to any observed outage — the record contains no bootstrap
  failure to fit to.
