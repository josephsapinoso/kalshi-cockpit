# ADR 0102 — The cold-open watcher decides from fresh facts, on two clocks

**Status:** Accepted; ordinal 0102 taken at the merge boundary.
**Date:** 2026-09-03.
**Amends:** the 2026-08-28 half of ticket #35 that gated `RefreshWhenPriced`
on `anAutomaticBuyIsComing(actionable)`; the `LOOP_STALL_MS = 180_000`
constant in `frontend/src/lib/nextOddsWindow.ts` (retired). Leaves ADR 0071
§2.6 (the feed follows attention over an hourly floor) exactly where it is.

## 1. The defect, as measured

`RefreshWhenPriced` is the cold-open self-heal on `/picks` and `/slate`: it
polls `/api/window` and `router.refresh()`es when `fixtures_fresh` rises above
what the render saw. Since 2026-08-28 it was gated on `automaticBuyIsComing`,
computed **on the server render** by `anAutomaticBuyIsComing`, which reads
`readNextWindow` and returns false for `loop_stalled`. `loop_stalled` fired
when `now_ms - last_look_ms > 180_000`.

The 180s was written for the fast cadence — "the observed live cadence is a
quote pass every ~18s" — and that cadence runs only while a window is open.
Idle, the loop sleeps `RUNNER_INTERVAL_S` = 900s (median 926.8s full-to-full
across 6,066 live passes). So on a cold open after a quiet hour the render's
snapshot said *stalled*, the component returned before setting a timer, and
the screen said *"It will not change by itself until you reload it"* — while
the page's own heartbeat (`Nav.tsx` → `recordAttention`) had the loop awake
within `DEFAULT_WAKE_POLL_S` (5s) and the buy landing a median ~3s later.

Measured on live 2026-09-03: of 26 visits inside the pass log, **8 opened with
the last look over 180s old; all 8 had nothing fresh at open; 0 of the 11
opens with fresh fixtures were called stalled.** 53% of cold opens lost the
watcher, and the watcher exists for cold opens. Exhibit: 2026-09-02T13:28Z, a
13-second visit, buy at +0.6s, 0 → 150 fresh fixtures, screen said it would
not change.

**Root cause in one sentence:** the predicate was computed from a snapshot
taken *before the page's own heartbeat existed*, so it asked whether a buy was
scheduled using facts that predate the thing that schedules the buy. And the
one constant conflated two questions — "is the loop alive" and "is a buy
coming because this page is open" — at a threshold 4.8× shorter than the
loop's normal sleep.

## 2. What was decided

### 2.1 Two questions, two clocks

**"Is the loop alive"** is a question about a cadence, and the cadence is a
fact the server has and the browser does not. `/api/window` now publishes
`loop_idle_interval_ms` — `RUNNER_INTERVAL_S` read as `docker/entrypoint.sh`
reads it, with the entrypoint's own default (`ENTRYPOINT_RUNNER_INTERVAL_S =
900`, pinned against the entrypoint and `.env.example`). `readNextWindow`
calls the loop stalled only when the silence exceeds
`LOOP_STALL_IDLE_INTERVALS` (= 2) of that interval. Two, because one sleep at
worst-case jitter (`1.15 × I`) plus one pass at its deadline (600s) is 1635s
at I = 900 — inside two intervals — so silence past two means at least one
whole pass was missed under the worst case the loop permits itself. The
inequality is a test over the Python constants, not a comment. **With the
cadence unknown (`null`), no silence is a stall**: unreadable resolves to a
refusal to claim, not to 180 and not to 900.

**"Is a buy coming because this page is open"** cannot be answered by the
render. `readWatch` answers it **client-side, from fresh facts, on every
poll**, and it carries the tighter stall test the render cannot have: a
visible page heartbeats every `HEARTBEAT_INTERVAL_MS` (60s, now one exported
constant imported by `Nav.tsx`), each heartbeat wakes the loop within ~5s, and
a woken pass writes a look. Silence in `last_look_ms` spanning
`WATCHED_STALL_MS` = 3 heartbeats of **continuous visibility** is three wakes
with no look — a stall, on a clock the 2026-08-25 wedge trips at three
minutes. Both operands are durations (browser-visible-for vs
server-silent-for), so clock skew never enters the verdict. Not 60s: the first
look after a heartbeat can land early and the next heartbeat is a minute away,
and a heartbeat landing mid-way through a long full pass pushes the look
~107s out; 60s would false-alarm on a healthy loop most of the time.

### 2.2 What `readWatch` does with a reading

With the horizon `now + watch_remaining_ms` (the five minutes left on the
watch): `due_now` → watch; `scheduled` → watch iff inside the horizon;
`slice_spent` → **watch iff `floor_next_buy_ms` is inside the horizon** —
off-switch (a) of the ticket, since the floor buys while the page is open
(2026-08-29) and a floor buy due in two minutes is a buy this watcher will see
land; `budget_spent` → nothing due; `nothing_to_schedule` → nothing due,
*once the facts include this page* (§2.3). Every terminal verdict carries a
sentence and, where one exists, the next buy time for the caller to format.

### 2.3 The settle rule — off-switch (b)

`desk_wants`' attended branch has no twelve-hour horizon: while a page is
open every stored fixture is bought on the ten-minute cadence. So a fixture
13 hours out is "nothing to schedule" to the idle desk and "due now" to the
attended one, and `/api/window` read before this page's heartbeat commits
says the first. The reading is not wrong — it is honest about the desk
*without this page in it* — but taking it as final would repeat the
server-render defect with fresher facts. `readWatch` therefore defers any
"nothing is coming" verdict while `desk_is_attended === false` and the page
has been visible under `HEARTBEAT_SETTLE_MS` (15s, three leading-edge
polls). `slice_spent` and `budget_spent` are **not** deferred: a heartbeat
changes neither. The honest reading of `nothing_to_schedule` is therefore:
final when the facts include the page, provisional when they do not — and
that is pinned rather than reworded.

### 2.4 Leading edge

The first poll fires on mount, then every `LEADING_POLL_MS` (3s ≤ the loop's
5s wake poll) for `LEADING_EDGE_MS` (30s), then `POLL_MS` (10s). A
`setInterval` had no first tick until 10s, and observed visits of 4, 5, 7 and
13s could not reach it though the data healed in 3–13s.

### 2.5 The render hands over the baseline and nothing else

`/picks` and `/slate` pass `renderedFresh` only. The `automaticBuyIsComing`
prop survives in the type as `@deprecated`, optional and **never read** —
`ParlayCards` still passes it and is not this lane's file; a test pins that
the identifier appears exactly once in the component's code. The give-up
sentence now distinguishes "watched a due buy for five minutes and nothing
landed" from "the timetable never answered", which the old component
conflated.

### 2.6 `Nav.tsx`

The window-chip poll is gated on `document.visibilityState` exactly as the
heartbeat is, and resumes on `visibilitychange`. Both intervals are
`HEARTBEAT_INTERVAL_MS`.

## 3. What this does not establish

- **That the effect runs.** No React runner; `readWatch` is executed with
  node and the component is pinned at source. Timers, `router.refresh()`, and
  hidden-tab behaviour are browser facts.
- **That the heartbeat reached the server.** The fast clock assumes a visible
  page is waking the loop. If `recordAttention` fails silently, three minutes
  of visible silence reads as a stall on a loop nobody woke. The old give-up
  message had the same exposure.
- **That a stall shorter than two idle intervals is visible on the slow
  clock.** It is not. `RefreshOddsPanel`, `StaleOddsExit` and `WindowBanner`
  are server-rendered and have only the slow clock, so a mid-window wedge
  reads as asleep on those surfaces until ~30 minutes; the watcher on
  `/picks` and `/slate` is what sees it at three.
- **That the API's cadence is the loop's.** Both read `RUNNER_INTERVAL_S`
  from one environment with one default, which the deployed entrypoint
  guarantees; a developer running `run_loop.py --interval 300` by hand with
  the variable unset gets a screen that waits longer than it needs to before
  calling a fault. The error is in the safe direction.
- **Anything about the 8-of-26 figure generalising.** One day of visits, and
  the fraction depends on how Joe's opens fall against the loop's sleeps.

## 4. Considered and not taken

- **Raising the constant past 900s.** Blinds every surface to a dead loop
  for a quarter-hour and still conflates the two questions.
- **A tighter slow-clock threshold when `desk_is_attended` is true** (the
  loop should look every ~107s while attended, so 180s of attended silence
  is a stall). Rejected for a narrow false-alarm path: `desk_is_attended`
  holds for the 5-minute TTL after the last heartbeat, so a tab hidden for
  3–5 minutes and then navigated within ~10s of returning would render a
  fault sentence on a server component that never re-renders. The fast clock
  lives where visibility is known — in the browser — instead.
- **Publishing the threshold itself rather than the cadence.** The cadence is
  the fact; the multiplier is a decision, and it belongs beside its
  derivation.

## 5. Not fixed here, recorded so it is not re-found

- `frontend/src/lib/sweepTone.ts` has `LOOK_SILENT_MS = 2 * 900_000` — the
  same two-interval threshold, reached independently, with the 900 hardcoded
  as a second spelling. It should read `loop_idle_interval_ms`. Not this
  lane's file.
- `ParlayCards.tsx`'s `Freshness` block still passes
  `automaticBuyIsComing={anAutomaticBuyIsComing(actionable)}`; inert now,
  to be dropped by its own lane.
- `backend/odds/attention.py`'s docstring says "`Nav.tsx` polls every 60s",
  which is still true.

## 6. Tests

`tests/test_watcher_decides_from_fresh_facts.py` (new): `readWatch` under
node across the cold open, the settle rule, the slice fall-through, both
stall clocks; the cross-language inequalities; `loop_idle_interval_ms_from_env`
and its wire field; the component's leading edge, inert prop and terminal
states; the Nav gate. `tests/test_stale_exit.py`: every stall case now names
the cadence, an idle gap of one interval is pinned *not* a stall, an unknown
cadence never stalls, and the watcher pins assert `readWatch` over the retired
prop gate. `tests/test_parlay_auto_refresh.py`: the trigger, the bound and
the Picks mount re-pinned to the new spellings.

Mutation record, each restored by reversing the exact edit:
`LOOP_STALL_IDLE_INTERVALS = 1` → 2 red; mount-time `void look()` deleted →
1 red (after the pin was sharpened — the bare string survived because the
visibility handler also calls it); chip guard removed → 1 red; `ValueError →
0` → 1 red; settle rule forced false → 2 red; prop gate reinstated → 2 red;
visible clause dropped from the fast clock → 13 red, the exhibit among them;
unknown cadence falling back to 180s → 1 red; `slice_spent` always
"nothing due" → 1 red.
