# The live instance was switched off between visits, and the cause is a subtraction

**Date:** 2026-08-26
**Status:** diagnosed to the line; fix in the same commit.
**How it was found:** while taking a first latency reading for the "the site
is slow" work item. It was not found by reading code, and no test was failing.

## What was observed

Three reads against the deployed instance, `git_sha 26a8d70`, minutes apart:

```
15:01Z   /api/health   200   TTFB 0.123s, 0.142s, 0.166s   (three samples)
15:03Z   /api/health   200   TTFB 37.09s
```

Between them, `flyctl status` reported the machine `stopped`. The event log:

```
06:51:15Z  started
07:51:02Z  stopped   exit_code=0, oom_killed=false, requested_stop=false
           runner: "machine exited with exit code 0, not restarting"
08:03:06Z  starting  (proxy)   <- woken by the 37s request above
08:03:07Z  started
```

Uptime ~60 minutes, then off until an HTTP request arrived. `fly.live.toml`
sets `auto_stop_machines = "off"` and `min_machines_running = 1`; neither
applies, for the reason in link 5.

**It happened again while this document was being written**, which is what
turns one observation into a cadence:

```
06:51:15Z started -> 07:51:02Z stopped    59.8 min
08:03:07Z started -> 09:00:48Z stopped    57.7 min
```

Both stops carry the identical `exit_code=0, oom_killed=false,
requested_stop=false`. Two intervals is not a distribution and no rate is
claimed here; what the second occurrence establishes is that the first was not
a one-off, and that nothing self-heals -- the machine was still stopped 25
minutes after the second exit, with no request to wake it.

## The chain, in five links

**1. A missing bid arrives as a real zero.** Kalshi publishes bids only; asks
are derived. `backend/store/db.py::derive_yes_ask` returned `None` for a
`None` bid — and a number for a `0` bid. The venue reports an empty side as
`no_bid_dollars = 0.0000`, and `core/prices.dollars_to_tenths` correctly parses
that to `0`. So the **absence arrives as a legitimate value** and
`1000 - 0 = 1000` tenths comes back as an ask.

The function's own docstring said the absence "must not collapse to a number."
It did not collapse; it was never null to begin with.

**2. The team pricing path took it.** `backend/runner.py:1859` guarded on
`ask is None` only.

**3. The engine refused, correctly, by raising.**
`backend/core/ev.py:134-139` — *"ask 1000 tenths is not a tradeable price
(0 and 1000 are settled outcomes). Refusing rather than pricing it at a zero
fee, which fabricates an edge."* Nothing between it and the pass caught it, so
**one market failed the whole pass.**

**4. Five failed passes ended the process.** `backend/scheduler.py:500` raises
`LoopFailed` after `MAX_CONSECUTIVE_FAILURES`. At 900s per full pass that is
75 minutes of wall clock, against ~60 minutes of observed uptime — consistent.

```
backend.scheduler.LoopFailed: 5 consecutive failed passes; last error:
ValueError: ask 1000 tenths is not a tradeable price ...
```

**5. The container exited 0, so Fly did not restart it.**
`docker/entrypoint.sh` tore down as designed — its own comment says the
teardown exists *"so the platform restarts it cleanly"* — and called
`shutdown`, which ended `exit 0`. Fly's restart policy is on-failure:

```
[entrypoint] CHAIN RUNNER exited -- the record has stopped growing. Restarting.
INFO Main child exited normally with code: 0
runner: machine exited with exit code 0, not restarting
```

`min_machines_running = 1` does not govern a container that exited
successfully. The machine stayed stopped until `auto_start_machines` woke it
on the next request, at a measured **23–37 seconds** of cold start.

## Why nothing alarmed

`.github/workflows/heartbeat.yml` runs every 15 minutes and probes
`/api/health`. **That probe starts the machine.** By the time the check read
anything, the container was up and `status` was `ok`, so the monitor reported
health — and had been keeping the instance alive on a 15-minute cadence while
doing it. The observer was changing the state it measured.

This is the third occurrence of the derived-extreme defect and the second time
a monitor missed it. `tasks/lessons.md` already carries the pattern from
2026-08-26: *a derived value inherits its source's absence as an extreme.*

## What it cost

Unquantified, and deliberately not estimated here. What is certain: the
recorder writes nothing while the machine is stopped, so the evidence record
has holes bounded below by the observed 12-minute gap and above by however
long nobody opened the page. `loop_failures` (schema v22) cannot help — it is
written by a process that is not running.

## The fix, in four parts

| | Change | File |
|---|---|---|
| 1 | The derived ask runs back through `is_valid_price` and returns `None` at either endpoint | `backend/store/db.py` |
| 2 | A refusal from the pricing engine is counted (`dropped_unpriceable`) and skipped, never propagated | `backend/runner.py` |
| 3 | The failure teardown exits **non-zero**; the signal trap still exits 0 | `docker/entrypoint.sh` |
| 4 | The heartbeat reads the Fly Machines API **before** probing HTTP, so a stopped machine is seen rather than woken | `.github/workflows/heartbeat.yml` |

Part 1 is the source. Part 2 is the containment — the pass must survive the
*next* refusal, whatever produces it. Part 3 is what makes the platform's
restart actually happen. Part 4 is what makes the next occurrence audible.

**Part 1 is the fix that should have been made twice already.** The same rule
was patched at two call sites first:

1. `runner.py`'s prop path, 2026-08-15, after a `ValueError` aborted a whole
   pricing pass. Its comment predicted the team path would never trip it
   *"because a game moneyline does not reach 0 or 1000 while it is still
   pre-game and open."* **That prediction is what failed here.**
2. `routes.py::_tradeable_ask`, 2026-08-26, after the manual ticket rendered
   "YES 0c" on a live combination.

A rule enforced at the call site is a rule the next call site does not have.

## What this does not establish

- **That this was the only crash.** `LoopFailed` reports the *last* error only.
  A second cause could be behind this one. The stated check is an hour of
  machine events with no `exit_code=0` stop after deploy.
- **Why a market had no NO bid at all.** The derivation is now honest about it;
  which markets they were, and whether that is ordinary illiquidity or a
  discovery-scope problem, is a separate question. `dropped_unpriceable` is the
  instrument that will answer it.
- **Anything about serving latency.** The 37s figure is a cold start, not a
  slow request. The serving path still has no baseline; every latency document
  in this directory is about the recording loop.
- **That the demo instance is affected.** `fly.demo.toml` sets
  `auto_stop_machines = "stop"` and runs no chain runner. Its cold starts are
  by design.
