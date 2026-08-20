# The window gate — design and registration

Written 2026-08-20 ~03:40Z, **before** the code was changed, so the expected
observations cannot be chosen after seeing the log. Next window at the time of
writing: `baseball_mlb` 15:26Z-16:26Z, twelve hours out.

## What is wrong

Two faults, one root: **the loop decides using a `window_open` flag that was
last written at the end of the previous pass.**

`scripts/run_loop.py:543` assigns `tempo.window_open = window.is_open` after the
pass body. `:577` reads it before. Verified in the code at 03:30Z 2026-08-20,
not inherited.

### Fault 1 — the prune runs inside open windows

Measured 2026-08-19: `15:32:14 full took_s 94.3 quotes_pruned 40000`, window
open since 15:21Z. A 94-second stall inside the minutes the 15s cadence exists
to serve.

**There are two ways in, and the handoff named only one.**

- **Stale flag.** The window opened during the previous sleep. `tempo.window_open`
  still says closed. This is the measured incident — open at 15:21Z, pass at
  15:32:14.
- **Opened mid-pass.** `run_once` runs `run_ingest_pass` — which fires the odds
  sweep — and *then* prunes (`backend/runner.py:2331`, `:2346`). The sweep is
  what makes odds fresh, and fresh odds is the definition of `is_open`
  (`backend/odds/timing.py:758`). So a full pass that opens a window prunes
  inside the first ~40-94s of it, every time. **A check at the top of the pass
  cannot see this**, because at the top the window genuinely was closed.

The second is likely the more frequent, since full passes are the ones that
fire sweeps. Reading at the top of the pass would have shipped a fix that
misses the dominant case, which is why the decision is read at the prune.

### Fault 2 — a window opening inside a 900s sleep is invisible until it ends

Not a reorder. `tempo.pass_kind` picks the cadence at the top of a pass; with
the window closed, `Tempo.interval_s` returns `slow_interval_s` (900s) and the
loop sleeps. A window opening inside that sleep is not noticed until it ends.
Worst case after a restart: a pass at 15:25:50Z sleeps to 15:40:50Z and nearly
fifteen minutes of an open window are lost. Confirmed live at 20:39Z 2026-08-19
— a deploy restarted the box mid-window and only full passes ran until the next
one latched.

## The design

### Fix 1 — read the window where the decision is made

`run_once` takes `window_open` as `bool | Callable[[], bool]` and evaluates it
immediately before the prune. `run_loop` passes a callable closing over the
same `window_status(...)` expression the alerter uses.

**Why a callable and not a fresh bool computed in `one_pass`.** A bool computed
before the pass cannot catch the mid-pass case. Computing the window *inside*
`run_once` instead would need `max_odds_age_ms`, and `run_once` only has
`suppression.max_odds_age_ms` — the second spelling that ADR 0019 section 6
exists to prevent, and that `run_loop:484` deliberately does not use. The
callable keeps one spelling and moves the read to the right instant.

This cannot change the cadence: it touches no field `Tempo.interval_s` reads.

### Fix 2 — bound the sleep by the next window-open time

`ActionableWindow` already carries `next_call_ms`: when the next `/odds` call
is actually wanted, computed through `firing_for_slot`, the same predicate the
loop fires on. Firing that call is what makes odds fresh, which is what opens
the window. So it is already the answer, from the planner rather than a second
schedule.

`Tempo` gains `next_wake_ms`, set beside `window_open` from
`window.next_call_ms`, and a clock (injected, defaulting to `db.now_ms`) so
`interval_s()` keeps its no-argument contract with `run_forever`.

    if window_open:            -> fast_interval_s          (unchanged)
    if next_wake_ms is None    -> slow_interval_s          (no sweep planned)
    if next_wake_ms <= now     -> slow_interval_s          (see below)
    else                       -> clamp(until, fast, slow)

**`next_wake_ms <= now` falls back to the slow interval deliberately, and this
is the guard that matters.** `window_status` sets `next_call_ms = now_ms` when a
slot is firing right now. If the pass that just ran served it, the window is now
open and the first branch takes over. If it *refused* it — budget exhausted —
then the refusal will repeat, and a floor-length sleep would spin the loop at
15s against Kalshi with the window closed, which is the 4,300-polls-a-day
`Tempo` exists to prevent. Treating "already due" as no useful bound removes
that failure entirely.

The `fast_interval_s` floor bounds the remaining case: a bound a fraction of a
second away arrives at most one fast interval late, never sooner than the loop's
own designed maximum rate.

The ceiling is `slow_interval_s`, so a window six hours out changes nothing.

### The check that had to pass first

A quote pass passes `allow_bootstrap=False` (`backend/runner.py:2470`), so an
early wake landing on a quote pass could in principle wake to a sweep it is not
allowed to serve — which would make the whole fix inert.

It cannot. Bootstrap candidates are sports **not in** `fixtures`
(`backend/odds/timing.py:1175-1188`), and `plan_sweep_slots` — the source of
`next_slot` and therefore of `next_call_ms` — is fed from that same `fixtures`
mapping. A sport with a slot is never a bootstrap candidate. Every wake this fix
schedules targets a slot the quote cadence is permitted to serve. Verified in
the code, not assumed.

`run_quote_pass` does reach `fetch_and_store_odds` (`backend/runner.py:2467`),
so a quote pass can open a window. Also verified rather than assumed.

## What I expect to see, registered before deploying

At the 15:26Z `baseball_mlb` window:

1. **No `quotes_pruned` above 0 on any pass stamped between 15:26Z and 16:26Z.**
   This is the falsifier for fix 1. A non-zero prune inside the window means the
   gate still does not hold.
2. **The first pass after 15:26Z lands within `fast_interval_s + jitter` of
   15:26Z**, not up to 900s after it. This is the falsifier for fix 2.
3. **`window_open` latches true within one pass of 15:26Z**, and quote passes
   begin at the 15s cadence.
4. **Between now and 15:26Z, passes stay on the 900s cadence.** If the loop
   wakes early while the window is closed and no slot is due, fix 2's guard has
   failed and it is burning Kalshi requests. Check `slow_passes` /`fast_passes`
   in the exit-state line and the pass timestamps.

**What would falsify the whole thing without being a bug in it:** no window
opens at 15:26Z at all, because the slate is empty or the budget is spent. Then
observations 1-3 have no denominator and this is untested, not confirmed. Check
`next_sweep_ms` and `sweeps_remaining_today` on `/api/health` before reading a
quiet window as a pass.

## What this does not establish

- Nothing about whether the surfaced rows are correct. This is a scheduling
  fix; it changes when the loop looks, never what it concludes.
- Nothing about the ~585 MB holder, `unmatched_events` growth, or the health
  flap. Those stay open.
- The 12-hour stability watch riding on the same deploy is a *separate*
  observation and must not be reported as evidence for either fix.

---

## Pre-flight, 03:57Z 2026-08-20 — taken after deploy, before the window

Deployed `5656133` to live, `/api/health` `build.git_sha` confirms it. Health
`ok`, one machine, 1 of 1 checks passing.

**The denominator exists.** The registration's null result — "no window opens at
15:26Z at all" — is ruled out. Computed on the live database through the repo's
own `plan_sweep_slots`, not from the handoff:

```
now 08-20 03:57:41Z
  baseball_mlb     fire 15:26:00Z -> 16:26:00Z   games 6
  baseball_mlb     fire 21:21:00Z -> 22:21:00Z   games 3
  basketball_wnba  fire 22:45:00Z -> 23:45:00Z   games 3
```

Earliest stored MLB fixture is 16:41:00Z, 9 events. So observations 1-3 have a
population to be measured against.

**What the deployed cadence will do**, simulated with the real `Tempo` against
the real 15:26:00Z open:

```
 03:57:41Z   900.0s   slow (unchanged)
 04:12:41Z   900.0s   slow (unchanged)
 ...         45 passes at the slow interval, unchanged
 15:12:41Z   694.8s   BOUNDED
 15:24:15Z    90.6s   BOUNDED
 15:25:46Z    15.0s   BOUNDED
 15:26:01Z            first pass after the open, +1.4s
```

Three bounded passes, inside the registered 2-4. Worst case with every sleep
stretched the full +15%: **+0.0s**. Mean case **+1.4s**.

**This is a simulation of the deployed logic, not an observation of it.** It
uses the real `Tempo` and the real slot times but a synthetic clock, so it
establishes that the arithmetic is right and establishes nothing about the
process actually running. Observations 1-4 still have to be taken off the live
log after 16:26Z. In particular it cannot see: a pass overrunning its sleep, the
sweep being refused, the box restarting, or the prune behaving differently under
memory pressure than it does in a test.

For contrast, the pre-fix behaviour at this same alignment would have put the
first post-open pass at 15:27:41Z, 101s late — and that is the *lucky* case. The
old 900s grid's offset is set by whenever the process last restarted, so the
loss ranged from ~0 to 900s, up to a quarter of a 60-minute window.
