# ADR 0042 — The budget-day boundary is not a liveness reference, and the sweep banner was firing by arithmetic

- **Status:** Accepted
- **Date:** 2026-08-17
- **Supersedes in part:** the reasoning paragraph in `WindowBanner.tsx`'s
  `SweepTrace` docstring, quoted in full below and corrected in place.
- **Related:** ADR 0038 (the hunt is closed; the recorder keeps running),
  ADR 0039 (`/api/signal`), ADR 0041 (the demo runs the deployed caps).

## The decision

Two changes, and the second one is the guard on the first.

1. The sweep strip's amber state now requires **both** that nothing has swept
   since the budget day opened **and** that a sweep window has actually opened.
   `GET /api/window` gains `first_window_open_ms` for the second half.
2. A `last_look_outcome` of `refused` warns **regardless** of whether a window
   has opened, and that clause is not optional.

The manual-refresh exclusion is **unchanged**. `scripts/inspect_live_db.py`
gains the `trigger` column it was blind to.

## The defect

`WindowBanner.tsx` decided its tone with:

```ts
const sweptThisDay =
  w.last_sweep_ms !== null && w.last_sweep_ms >= w.budget_day_start_ms;
const tone: Tone = silent ? "alarm" : sweptThisDay ? "calm" : "warn";
```

Amber was the **fallthrough**: anything not silent and not swept-today.

`budget_day_start_ms` is a **credits-accounting** boundary — 10:00 UTC, chosen
(`backend/odds/timing.py`, `DEFAULT_DAY_START_UTC_HOUR`) so that a West Coast
extra-innings game settles into the day it belongs to. A sweep **window** is
**kickoff-derived**: `[anchor − max_odds_age_ms − due_window_ms,
anchor − max_odds_age_ms]`, i.e. 75 to 15 minutes before the first pitch of a
cluster (`slots_for_sport`). **Nothing connects the two quantities.**

Between the boundary and the day's first window there is no window in which to
spend. "Nothing has swept since the budget day opened" is therefore not an
observation about the loop during that interval. It is arithmetic, and it was
rendered as a warning.

### Measured, on rows, before anything was built

Six budget days off the live database, gap from the 10:00Z boundary to the first
`api_credits` row satisfying the full served-sweep predicate:

| budget day | first served sweep | gap | manual rows |
|---|---|---|---|
| 2026-08-12 | 17:00:11Z | 7.00h | 0 |
| 2026-08-13 | 16:47:55Z | 6.80h | 0 |
| 2026-08-14 | 17:39:58Z | 7.67h | 0 |
| 2026-08-15 | 16:27:03Z | 6.45h | 0 |
| 2026-08-16 | 17:06:36Z | 7.11h | 0 |
| 2026-08-17 | none, as of 17:45Z | — | 0 |

Six for six. No day escaped.

**Two different quantities appear in this record and they must not be
conflated.** The table above is the gap to the first **served row**. The
predicate keys on the gap to **window open**, which is larger. On 2026-08-17 the
first window opened at 20:50Z against a 10:00Z boundary: **10.83 hours of amber
that day.** An earlier session handoff guessed "~11 hours"; an interim brief of
mine corrected that downward to "6.5–7.7h" and the correction was wrong, because
it was measuring the other quantity. Both numbers are real. The one relevant to
this decision is the larger one.

### The machine already knew

Throughout the amber period, `odds_sweep_log` was recording the correct
explanation every ~15 minutes:

```
667  2026-08-17T17:34:04Z  skipped
     "no sweep: next slot is baseball_mlb at 20:50Z-21:50Z for 7 game(s)
      from 22:05Z, sweeping 75-15 min before first kickoff"
```

The same `detail` string on all 25 most recent rows, back to 11:26Z. So the
scheduler's own log was calm and accurate while the screen a human reads was
amber. **The instruments disagreed, and the wrong one was the one on the phone.**

## Why this is a correctness fix and not polish

ADR 0038 closed the edge hunt but explicitly kept the recorder running, because
the `G = 300` look arrives on its own. That makes the recorder **the only
operationally load-bearing process left in the system**. Its sole human-facing
liveness indicator was uninformative for 7–11 hours of every day, on 100% of days
sampled.

The concrete failure: at 17:45Z on 2026-08-17, the old banner **could not
distinguish** "light slate, first window at 20:50Z" from "the loop died at
10:00Z". Both rendered identical amber. The failure it guards against — a loop
that looks and never spends — actually happened and ran 17 hours unnoticed.

The alarm-fatigue argument ("crying wolf trains the reader to ignore it") is
true but was **not** the deciding reason, and should not be cited as such: the
fatigued reader is largely hypothetical here, since Joe reads this screen himself
and knows what the amber means. The deciding reason is that the predicate asks
one subsystem's quantity to answer another subsystem's question.

## Why `refused` is in the predicate

The obvious form of this fix — *no window open yet, therefore calm* — introduces
a worse bug than it removes.

`slots_for_sport` is **unfiltered by budget**; its own docstring says so
(*"Every candidate slot for one sport, unfiltered by budget"*). So a day whose
credits were exhausted at 14:00Z still computes a first window at 20:50Z. The
naive predicate sees "window has not opened yet", renders calm, and the Board
goes quiet over a recorder that is dead for the rest of the day.

That trades a false positive for a **false negative on the exact failure the
strip exists to catch**. Strictly worse than leaving the bug in. **A liveness
guard may be noisy; it may not be silent.** `refused` is a live state, not a
theoretical one — two such rows exist in the live `odds_sweep_log`.

`tests/test_sweep_tone_predicate.py::TestTheGuardsAreReal` mutates the shipped
module to the naive shape and requires the refused day to go calm, so the clause
cannot be removed while the suite stays green.

### One claim in this lane was wrong and was corrected, not defended

The first draft asserted in `sweepTone.ts` that the `refused` test **must come
before** the window test, and wrote a mutation test to prove the ordering was
load-bearing. **The mutation refused to go red.** Both branches return `"warn"`
and the question is a disjunction, so swapping the two lines changes nothing.
The true requirement is weaker and more specific: `refused` must never be
**gated behind** the window test, i.e. the window test must not be written as an
early `return "calm"`. The source comment was corrected and the mutation test
rewritten to the shape that actually breaks.

This is recorded because a plausible-sounding claim about ordering, backed by a
test that was never observed red, is exactly the kind of thing a future session
would preserve while refactoring around it.

**It is deliberately not softened.** The sequencing claim originated in the
directing brief for this lane and was carried into the source comment unchecked;
the mutation refused to confirm it, and the record says so in those terms rather
than restating the original phrasing as nearly-right. The surviving requirement —
*never gated behind* — is narrower than what was asserted, and the difference is
the whole content.

## Who owned the extraction into `sweepTone.ts`

Splitting the verdict out of `WindowBanner.tsx` was **not** on this lane's
deliverable list, and it was raised as possible scope creep before merge. It is
recorded here as the **director's omission, not the implementer's expansion**:
the lane's acceptance criterion required fixtures that render opposite verdicts
under a disabling mutation, and that criterion was unsatisfiable with the
repo's existing source-text guards, which pass unchanged against an inverted
predicate. A criterion phrased as a test is a build instruction in disguise, and
under-specifying it does not move ownership to whoever discovers its cost. See
`tasks/lessons.md`, *"An acceptance criterion carries implicit scope"*.

## The manual-refresh exclusion stays, and it has never fired

`_SERVED_SWEEP` (`backend/odds/timing.py`) is, verbatim:

```
endpoint LIKE '%/odds' AND cost > 0 AND COALESCE(trigger, '') != 'manual'
```

**Quote the `COALESCE` form and not the paraphrase.** `backend/runner.py` stamps
`None` for scheduled firings deliberately, so every scheduled row has a NULL
`trigger`. Under the paraphrase `trigger != 'manual'` — which an interim brief in
this lane used — every NULL row fails the comparison and the banner would read
"swept never" for its entire life. The measurements above used the real
predicate and are unaffected, but the paraphrase would send a future reader down
a false trail.

The exclusion is correct and stays: a hand tap proves the **spend path** works
and says nothing about the **scheduler**, which is the thing under observation.
Counting it would relax a guard because the guard fires too often.

**It has never fired.** All-time, every `/odds` row with `cost > 0` has a NULL
`trigger`: one group, n = 111, spanning 2026-08-07T19:33Z to 2026-08-16T22:59Z.
Zero manual rows have ever been written. The exclusion is test-covered only —
this repo's "built but never called" shape, recorded here so it is not
rediscovered as a finding.

A copy change explaining the exclusion to a reader who had just tapped refresh
was authorised and then **dropped** on this evidence: it is a sentence about a
button nobody has ever pressed.

## The instrument was blind to its own predicate

`scripts/inspect_live_db.py`'s `_CREDIT_COLUMNS` did not select `trigger` — the
one clause deciding whether a row counts as a served sweep. A day whose only
`/odds` rows were manual taps would read, in that output, exactly like a day that
swept.

This is the shape that cost this project six days once already: `clv-coverage`
filtered on `clv_scored_ms IS NOT NULL` while an actionable row is written before
commence, so the class under investigation sat outside the denominator and
"actionable = 0" was believed as a measurement when it was a repetition of an
older one.

Fixed, and the measurements above were re-run with the column visible before this
decision was frozen. The direction of the error was favourable — a miscounted
manual tap would have made the gaps **longer** — so the finding was conservative,
which is why this is a repair and not a retraction.

## What was rejected

- **Persisting the slot time as a new `odds_sweep_log` column.** Argued from
  `schema.sql`'s *"Not re-derived here: a paraphrase of a reason is a second
  implementation of it"*. Rejected: calling `slots_for_sport` **is** the same
  implementation, not a paraphrase, and a value computed at request time with a
  fresh `now_ms` is more correct for a live banner than one frozen up to 15
  minutes ago. No migration, no `ALTER TABLE`.
- **Consuming `odds_sweep_log.outcome` beyond `refused`.** The three-value enum
  invites more branching. Only `refused` earns a branch, because only it denotes
  a state that will not resolve itself when the next window opens.
- **A new banner tone.** The pre-window state uses the existing `calm` styling.
  "Neutral" describes the meaning; adding a fourth visual state was out of scope
  and would have been restyling.
- **Relaxing the manual exclusion.** See above.

## What this does not establish

- Nothing here says the recorder is healthy. It says the banner now reports
  health and its absence on the right evidence.
- `first_window_open_ms` is computed from **stored fixtures**. A day on which
  `odds_snapshots` holds no upcoming kickoff yields `None`, which the banner
  reads as "nothing is owed today". That is correct but it is not independent
  confirmation that the loop is alive — `last_look_ms` going stale is, and that
  is a different field and a louder tone.
- The 6-of-6 measurement is six consecutive days on one venue in one season. It
  establishes that the state is routine, not that it is universal.
- H4 is still untested and the cost headroom is still an upper bound. Untouched
  by this.
