# ADR 0130 — The manual hedge form is for what the wiring cannot reach

Status: accepted
Date: 2026-09-09

**This document carries no ordinal on purpose.** The number is taken in the
merge commit after `git fetch`, per `docs/adr/README.md`, and
`tests/test_parallel_lanes_do_not_collide.py` fails while a `DRAFT-` file sits
on the integration branch. That failure is the mechanism, not a defect.

Settles **P1** of
`docs/measurements/2026-09-08-parlay-positions-check-amendment-registration.md`
§7. Does not amend ADR 0078 (the hedge route, screen, watcher and arithmetic
stand unchanged), does not amend ADR 0125 (the wiring is correct), does not
touch ADR 0073's combination ceiling, moves no money, and leaves `gate.py`'s
boundary intact — it still never reads `parlay_positions` or
`parlay_position_legs` (ADR 0063, ADR 0078 §4).

## Context

**The form used to be justified by a measurement that no longer exists.**

`POST /api/hedge/positions`, reached from `RecordParlay.tsx` on seven surfaces,
was the only writer of `parlay_positions` until 2026-09-09. A check set in
`tasks/NEXT.md` said that if the table was still empty after NFL Week 1, the
transcribe-it-yourself entry design was refuted. The registration above
vacated that check's deletion clause, and then two things happened on one day:

1. **ADR 0125 wired the desk's own fills.** A filled, non-dry-run combination
   bought through `POST /api/manual-orders` now writes its own
   `parlay_positions` row. A combination bought through the desk needs no
   second tap.
2. **Joe killed the adoption successor** (Amendment 2 §A2.0, his words: *"kill
   the adoption successor"*), on the registrar's own recommendation and the
   arithmetic in Amendment 1 §A1.6 — the successor was powered only in the
   branch where the desk failed at its stated purpose.

So there is no adoption rate, there will not be one, and **the form now needs a
justification that is not a count.** That is what P1 asked for and what this
decides. Amendment 2 §A2.1 states the standing consequence: the form is not
refuted and will not be refuted by that registration's lineage, which is not
the same as vindicated — no adoption evidence exists in either direction.

**Two facts narrow the job, and both were established on 2026-09-09.**

- **The silent-failure case is now detectable.** ADR 0125's writer runs inside
  a bare `except` (`backend/api/routes.py:3850-3866`) — correct, because
  bookkeeping must never fail a purchase that has already spent money, and
  therefore the write can fail with nothing raised.
  `scripts/inspect_live_db.py combo-position-gaps` is the only detector that
  failure mode has. Pointed at live it found the `manual_orders` id=4 orphan;
  after the authorised write it reports one settled pair and no open gap.
- **Settlement reconciliation works, so the form is not needed for it.**
  Reported by the executing session: `venue_settlements` carries 62 `KXMVE`
  rows of 90, including both 2026-09-08 combinations with contracts, entry
  price and fee. A minted combination ticker **does** settle and the desk
  **does** record it. This closes what `tasks/NEXT.md` item 6 listed as
  unobserved.

## Decision

**The manual hedge form is kept, and it is justified by the holdings the wiring
cannot reach — not by how often it is used.**

### 1. It is the only entry for a combination bought outside the desk

ADR 0125's writer fires on one condition: a filled, non-dry-run `manual_orders`
row. A combination bought in the Kalshi app has no such row, so nothing writes
its position and `/hedge` never hears of it.

This is not a hypothetical corner. The committed census constants
(`backend/parlays.py:129-131`) record 52 combination positions over
2026-08-18 → 2026-09-05 with 51 entered as taker fills, and the cockpit's own
first fills were 2026-09-08 — so **historically nearly all of Joe's
combinations were bought outside the desk.** Whether that persists is not
known and, by Amendment 2 §A2.8 hole 2, is now not going to be measured.

A `KXMVE` combination is enter-only — `yes_dollars` empty on 40 of 40 books
this repo has read, zero resting YES bids over 36 levels (ADR 0012 §5) — so a
holding with no `parlay_positions` row is a position with **no exit screen at
all.** That is precisely the harm ADR 0078 Decision 1 exists to prevent, and it
is why the form's value does not depend on its frequency.

### 2. It is the repair path when the wiring fails, and that is now a supported workflow

Detection is `combo-position-gaps`; repair is the form. Before 2026-09-09
neither half existed, so "the wiring might fail silently" was an argument
nobody could act on. It is now a two-step operation that has been run once
end to end.

**The form is therefore load-bearing even in the limit where Joe buys every
combination through the desk**, because the wiring's own failure mode routes
back through it.

### 3. The `sportsbook` arm is retained as capacity, and is not part of the justification

`parlay_positions.source` keeps its two-value `CHECK`. But Joe's 2026-09-08
correction was that by "sportsbook" he had meant Kalshi's own sportsbook, and
he does not want a control for logging bets placed at a third-party book. That
arm is also permanently unmeasurable — `fills` cannot see a third-party slip,
so it has no denominator and can never have one (registration §8, §3.2).

**Nothing in this ADR rests on it.** Removing the option is not proposed and
would be a separate decision; justifying the form by it would be justifying a
feature by a case its owner has said he does not want.

### 4. The form is not measured for adoption, and is not deleted on a count

No count of `parlay_positions`, on any date, over any window, is evidence about
whether this form or ADR 0078's route is wanted. Amendment 2 §A2.2 marks §8's
three branches VOID and unreachable; §A2.3 closes the deletion question rather
than deferring it.

**Removing the form requires a new decision from Joe with a stated reason,
recorded as an ADR.** Not a measurement, not a low usage number, and not the
passage of time.

### 5. It does not grow features to drive adoption

ADR 0071 settles that the desk *"does not manufacture action"*. A form kept for
a residual population is finished when it serves that population correctly; it
is not a surface to be promoted, prefilled toward an answer, or nudged.

This also preserves what P2 built. The no-default control — `?? ""`, an
unselected required `source` that refuses submission — was shipped so an
observation window would be clean, and that window is void. **It stays, on its
own terms:** the instrument must not answer the operator's question for him.
Amendment 2 §A2.8 hole 3 records that any comment justifying it by the dead
measurement should be re-based on this paragraph when next touched.

## Consequences

- **P1 is settled**, so the registration's last live precondition is discharged
  — for a successor that will not be written. P3 is moot with it.
- **`/hedge`, its route, screen, watcher, arithmetic and both tables survive**,
  and are more load-bearing than when ADR 0078 was written: Joe is buying
  combinations through the desk, and enter-only means the hedge is still the
  only exit.
- **The form's cost is accepted knowingly**: seven surfaces, the no-default
  control, `schemas.py`'s validation and the guards in
  `tests/test_recording_a_bet_is_reachable.py`. Amendment 2 §A2.8 hole 1 names
  the trade — a feature that can only be killed by decision tends not to be
  killed.
- **`combo-position-gaps` becomes an operational habit rather than a one-off.**
  It carries no verdict on anything and never has; it answers *is a live
  position unwatched right now?*
- Nothing here moves the gate, the odds budget, `beta`, or ADR 0038's closed
  hunt.

## What this does not decide

- **Whether adoption or calibration is worth measuring by some other design.**
  A different estimand, unit or instrument is not foreclosed; what is
  foreclosed is the killed lineage. Any new design starts from its own
  registration and its own power check.
- **Anything about provenance columns on `parlay_positions`.** Amendment 1
  §A1.3.3 required one; **Joe dropped it on 2026-09-09** (*"drop the provenance
  column"*, Amendment 2 §A2.7). It is **not owed, not queued and not deferred**,
  and nothing in this ADR leans on being able to tell a hand-written row from a
  wiring-written one. The single row that needs attributing is attributed by id
  in Amendment 2 §A2.7.3, and §A2.7.4 states the condition any future
  registration needing authorship must meet — add the column **before** its
  window opens, because attribution cannot be recovered afterwards.
- **How often the form is actually used.** Not measured, and by Amendment 2
  §A2.8 hole 2 not going to be. This ADR keeps it under acknowledged
  uncertainty about its own usage rather than asserting the usage is known.
- **Whether every combination settles, or how quickly.** The 62-of-90 figure
  establishes that a minted `KXMVE` ticker **can** settle and **is** recorded,
  demonstrated on both 2026-09-08 combinations. It is not a rate, not a
  latency, and not a claim about all combinations.
- **Anything about the disarmed bid path** (ADR 0115). It rests offers, Joe
  pays the ask, and nothing here re-arms it or argues for it.
- **Anything about hedging advice.** ADR 0078 reports and does not advise; with
  several legs live there is no figure and the screen says so. Untouched.
