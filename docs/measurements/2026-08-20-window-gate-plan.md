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

---

## Second pre-flight, 13:35Z 2026-08-20 — how each observation will be read

Taken 1h51m before the window opens, so nothing below was chosen after seeing
an in-window result. Everything here is re-verified live rather than inherited
from the 03:57Z pre-flight, which had a synthetic clock.

### The box is on the build under test and has not restarted

`/api/health` at 13:34Z: `build.git_sha` `5656133f34d9…`, `status` `ok`, one
machine `7812601a239428`. The loop's own pass counter reached **37** at 13:20Z
against a 03:54Z deploy — 9h26m at ~15.3 min a pass, which is the count a
process that never restarted would have. **The 12-hour stability watch matures
at ~15:54Z, inside the window**, and is still a separate observation.

`recorder.age_ms` was 817,336 (13.6 min) at 13:34Z. The window is closed and
the loop is on its slow cadence; this is the idle number, not a fault.

### The null result is ruled out, on all three of its routes

The registration's "no window opens at all" escape has three ways to happen —
empty slate, day budget spent, month budget spent. None holds:

```
slate    odds_sweep_log:2656 @13:20:20Z  "next slot is baseball_mlb at
         15:26Z-16:26Z for 6 game(s) from 16:41Z"      <- read off live, not the plan
day      api_credits for budget day 20260820 (starts 10:00Z): 0 rows, cost 0
month    1302 of ~20,000 spent August to date; a sweep costs 2
```

The slot arithmetic checks out against the rule in its own `detail` string:
16:41Z − 75 min = 15:26Z, 16:41Z − 15 min = 16:26Z.

### `odds_sweep_log` is the instrument for observations 2, 3 and 4

Verified rather than assumed, because the handoff's description was loose.
The table is **one row per sweep *decision***, not one per pass — `sport_key`
is nullable and a pass that fires several sports writes several rows. But
`fetch_and_store_odds` writes a row on **every** outcome including "nothing"
(`backend/runner.py:1793`), and the live ids are contiguous one-per-pass across
the whole quiet stretch (2645–2656 for the twelve passes 10:31Z–13:20Z). So
**`SELECT DISTINCT pass_ms` is the durable pass grid** and no log is needed for
observations 2, 3 or 4. Use `DISTINCT`, never `COUNT(*)`.

The pre-window cadence, read off that grid at 13:34Z, twelve consecutive gaps:

```
966 944 830 963 874 913 887 925 1034 909 877   (seconds)
```

All within ±15% of 900s, which is the registered jitter. Observation 4's "before"
arm is behaving so far.

### Observation 1 has a denominator, and it is not the one the plan implies

Two things had to be true for a zero prune inside the window to mean anything.
Both were checked, and the first was **not** what the plan assumed.

**A full pass really does land inside an open window.** `Tempo.pass_kind`
(`backend/scheduler.py`) returns `"full"` whenever
`now >= last_full_ms + slow_interval_s`, and that test does not consult
`window_open` at all. So the fast cadence does not suppress full passes — it
just runs ~60 quote passes between them. Expect **~4 full passes inside the
60-minute window**, each of which reaches the prune. If instead the window
contained no full pass, observation 1 would have been vacuous and would have
read as a pass. It is not vacuous.

**The prune still has work every time it runs.** Out-of-window full passes
today:

```
10:32  1975    11:34  3950    12:34  4074    13:06  2037
10:48  1975    12:04  3950    12:51  2037
```

and every quote pass in the same stretch reports `quotes_pruned: 0`, which is
the control. So a 0 on a *full* pass inside the window is a real observation
and not an artifact of an empty backlog.

### How observation 1 will actually be evidenced, and its known weakness

**`quotes_pruned` is persisted nowhere.** Confirmed by search, not assumed:
the only references are `PassCounts` (`backend/runner.py:267`), the log-field
list (`:329`), the assignment (`:2359`), and tests. No table, no API field.

**The handoff's suggested fallback is wrong and must not be used.** It proposed
the oldest `observed_ms` in `kalshi_quotes` as a proxy that "jumps if a prune
ran". `prune_quotes` selects on `COALESCE(confirmed_ms, observed_ms)`
(`backend/store/retention.py:206`), deliberately — ADR 0055 made the table a
change log, so a row can carry a three-day-old `observed_ms` and a current
`confirmed_ms`, and the prune keeps it. `MIN(observed_ms)` can therefore sit
still through a prune that deleted tens of thousands of rows. The prune
frontier is `MIN(COALESCE(confirmed_ms, observed_ms))` over tickers **not** in
`recommendations`, and no whitelisted query in `inspect_live_db.py` exposes it.
Adding one needs a deploy, a deploy restarts the box, and a restart would reset
the 12-hour stability watch riding on the same build. **Not worth it for one
observation; registered as a gap, and the query is being added for the *next*
window instead.**

So observation 1 is read from the process log, and **asymmetrically**:

- a `quotes_pruned` > 0 on a pass stamped 15:26Z–16:26Z **falsifies fix 1**.
  `flyctl logs` drops lines, but a line that appears was really emitted, so
  this direction is sound.
- the **absence** of such a line does **not** confirm fix 1. It is consistent
  with the gate holding and equally consistent with the log having dropped the
  line.

To make the absence worth something, the log arm is paired with the durable
grid: `odds_sweep_log` names every pass in the window, so a full pass whose
prune line is missing from the log can be *identified* rather than assumed
away. A window in which every full pass is present in the log with
`quotes_pruned: 0` is the strongest reading available today, and it is still
weaker than the other three observations. It will be reported at that strength
and **not** inferred from the fact that 2, 3 and 4 passed.

### What this second pre-flight does not establish

Nothing about the fix. Every number above is either the state of the box
before the window or a property of the code read in the repo. Observations 1–4
are still untaken at the time of writing.
