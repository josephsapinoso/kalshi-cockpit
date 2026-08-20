# ADR 0057 — The window gate is read when it is used, and a closed-window sleep is bounded by the next window

**Date** 2026-08-20
**Status** Accepted, deployed, live verification pending the 15:26Z window
**Supersedes** nothing. **Amends** the reasoning behind ADR 0054's retention gate.

## Context

The loop runs two cadences: a full pass every 900s, and a quote pass every 15s
*while a window is open*. "Open" means sportsbook odds are fresh enough for a
pick to survive the staleness check — `ActionableWindow.is_open` is
`fixtures_fresh > 0` (`backend/odds/timing.py:758`).

Both cadence decisions were made from `Tempo.window_open`, a stored flag
assigned at `scripts/run_loop.py:543` **after** a pass and read at `:577`
**before** the next one. Two distinct faults fell out of that, and earlier
handoffs recorded them as one item — "one fix, its own ADR". They are not one
fix. They have different blast radii: the first cannot change the cadence, the
second can. They shipped as separate commits.

### Fault 1 — the prune ran inside bettable windows

ADR 0054 put a retention window on the recording tables and deliberately skipped
the prune while a window is open: `budget_s` is checked between batches, one
batch costs ~20s against the live table, and a 5s budget really costs ~40s
across two tables. Between windows that is free; inside one it is exactly the
confirmation gap the fast cadence exists to close.

The gate was there and it did not hold. Measured 2026-08-19:
`15:32:14 full took_s 94.3 quotes_pruned 40000`, window open since 15:21Z.

**There were two ways in, and only one was in the record.**

- **Stale flag.** The window opened during the previous sleep, so the flag still
  said closed. This is the measured incident.
- **Opened mid-pass.** `run_once` calls `run_ingest_pass` — which fires the odds
  sweep — and *then* prunes. The sweep is what makes odds fresh, and fresh odds
  *is* `is_open`. So a full pass that opens a window prunes inside the first
  ~40–94s of it, **every time**. Full passes are the ones that fire sweeps, so
  this is plausibly the more frequent of the two.

A fix that read the window at the top of the pass — which is what the handoff
described — would have closed the measured case and left the likely-dominant one
open, while looking verified.

### Fault 2 — a window opening inside a 900s sleep was invisible until it ended

`Tempo.pass_kind` picks the cadence at the top of a pass. With the window closed
`interval_s()` returned `slow_interval_s` and the loop slept 900s. Nothing
re-examined the world during that sleep. A pass landing at 15:25:50Z against a
15:26Z window slept to 15:40:50Z. Observed live at 20:39Z 2026-08-19: a deploy
restarted the box mid-window and only full passes ran until the next one
latched.

## Decision

### 1. The prune asks at the prune

`run_once`'s `window_open` becomes `bool | Callable[[], bool]`, evaluated
immediately before `retention.prune`. `run_loop` passes
`lambda: window_now().is_open`.

A callable rather than a fresh bool computed in `one_pass`, for two reasons.
Only a callable reaches the mid-pass case. And computing the window *inside*
`run_once` would have to spell the staleness limit `suppression.max_odds_age_ms`
— the second spelling ADR 0019 §6 exists to prevent, and the one `run_loop`
deliberately does not use. The callable keeps one spelling and moves the read to
the right instant.

A plain `bool` still works and is what the tests pass.

### 2. A closed-window sleep is bounded by the next window-open time

`Tempo` gains `next_wake_ms`, set beside `window_open` from
`ActionableWindow.next_call_ms`.

`next_call_ms` is already the answer, and it comes from the planner: it is
computed through `firing_for_slot`, the same predicate the loop fires on. Firing
that call is what makes odds fresh, which is what opens a window. Computing a
second schedule inside `Tempo` is how a control and a screen come to disagree.

    window_open              -> fast_interval_s        (unchanged)
    next_wake_ms is None     -> slow_interval_s        (no sweep planned)
    next_wake_ms <= now      -> slow_interval_s        (see below)
    otherwise                -> clamp(until / (1 + JITTER), fast, slow)

**"Already due" falling back to the slow interval is the load-bearing guard.**
`window_status` sets `next_call_ms = now_ms` whenever a slot is firing right
now. If the pass that just ran *served* it, the window is open and the first
branch takes over. If it *refused* it — budget spent — the refusal repeats, and
a floor-length sleep would spin the loop at 15s against Kalshi with the window
shut. That is the 4,300 polls a day `Tempo`'s own docstring exists to prevent.
Treating "already due" as no useful bound removes the failure instead of
bounding it.

**The `(1 + JITTER)` divisor is not cosmetic.** `run_forever` sleeps
`next_delay(interval)`, which multiplies by up to `1 + JITTER` (0.15).
Unadjusted, a 900s bound stretches to 1035s and overshoots the open by 135s —
most of what this fix is for. Dividing puts the worst case *on* the open and the
typical case early. Early is free: the bound recomputes against the time
actually left and converges in two to four passes, because each sleep consumes
~87% of the remaining gap. The test pins that from **both** sides — below two
passes means the bound is not applied at all, above four means extra Kalshi
polls in front of every window.

The floor is `fast_interval_s`: never faster than the rate the loop is designed
for at its busiest.

## The check that had to pass first, and did

A quote pass passes `allow_bootstrap=False`. An early wake landing on a quote
pass that could not serve the sweep would make the entire fix inert while
looking correct.

It cannot happen. Bootstrap candidates are sports **not in** `fixtures`
(`backend/odds/timing.py:1175-1188`), and `plan_sweep_slots` — the source of
`next_slot` and therefore of `next_call_ms` — is fed from that same `fixtures`
mapping. A sport with a slot is never a bootstrap candidate, so every wake this
schedules targets a slot the quote cadence may serve. `run_quote_pass` does
reach `fetch_and_store_odds` (`backend/runner.py:2467`), so a quote pass can
open a window at all. Both read in the code, not assumed.

## Consequences

- The prune moves entirely into the gaps between windows. It has no deadline;
  a bettable minute does.
- Two to four extra quote passes run in the ~15 minutes before each window,
  against Kalshi, which is unmetered. No extra odds credits: `decide_sweeps`
  answers "not yet" until `fire_from_ms`.
- Full-pass frequency is unchanged. `pass_kind` is still time-based on
  `last_full_ms + slow_interval_s`, so the extra wakes are all quote passes.
- `Tempo` now needs a clock. It is injected and defaults lazily to
  `store.db.now_ms`, so the object stays testable without one.

## What this does not establish

- **Nothing is verified live yet.** Both faults were confirmed from the code and
  from 2026-08-19 log lines; the fix is verified only by tests. The registered
  live observations are in `docs/measurements/2026-08-20-window-gate-plan.md`,
  written before the code changed, and the 15:26Z `baseball_mlb` window is the
  first chance to take them.
- Nothing about whether surfaced rows are *correct*. This changes when the loop
  looks, never what it concludes.
- The 12-hour stability watch rides on the same deploy and is a **separate**
  observation. It must not be reported as evidence for either fix.
- `unmatched_events` growth, the ~585 MB holder, and the health flap are
  untouched and stay open.
