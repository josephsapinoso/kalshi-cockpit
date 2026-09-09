# ADR 0123 — The fee alarm is wired, and it is one-sided: it fires only when Kalshi charges MORE than we predict

Status: accepted
Date: 2026-09-09

Executes the open gap named in ADR 0120. Does not amend ADR 0058 (which keeps
the flat taker coefficient off the record-writing path) or ADR 0043 (which
keeps hand fills out of the gate); both are load-bearing here and are why the
alarm has the shape it does.

## Context

`Alerter.check_fee` compares a real fill's charged fee against `core/fees.py`
and shouts when they disagree. **It had no caller from the day it was
written.** Its docstring justified that: `ORDERS_ARE_DRY_RUNS = True`, so no
order had ever been placed and there was no fill to reconcile.

**That justification expired on 2026-09-08.** It is still true of the engine
path and is now false of the desk: the hand-bet path is armed
(`MANUAL_ORDERS_ARE_DRY_RUNS = False`) and real fills landed. Fills existed and
nothing compared their charged fee to anything — **silently**.

It matters more than a missing alarm usually would. `TAKER_COEFFICIENT` is
knowingly held at 0.070 while nine observations pin the true coefficient near
0.035 (ADR 0028), on the grounds that which attribute carries the split is
unresolved. The alarm that would notice the fee schedule moving under the armed
money path was the one not wired.

## Decision

**Reconcile every newly-mirrored fill in `backend/portfolio_poll.py`, at the
point the venue's charged fee arrives.** No schema change was needed:
`fills.fee_actual` is already the ground truth, written by the poller itself
from `/portfolio/fills` with `source = 'venue_hand'` for a hand bet.

### The alarm is ONE-SIDED, and this is the decision that needed making

It fires only when `actual - predicted > FEE_MATCH_TOLERANCE_DOLLARS`.

**A two-sided test would fire on every MLB hand fill, forever, by deliberate
policy.** ADR 0058 keeps the flat 0.070 coefficient on the record-writing path
while the venue charges ~0.035, so cell R of the 2026-08-14 attribution
(`KXMLBGAME`, 1 @ 52c) was charged **$0.0088** against a **$0.0175**
prediction. That is a 2.00× overstatement that the repo has decided to keep.
An alarm that must be muted on its first day is worse than no alarm, and this
repo has a 36-red-push scar about exactly that.

**What survives is the event that actually matters.** An undercharge breaks
`calculate_fee`'s stated never-under property, and it means every EV figure is
**optimistic** — we believed we had edge we did not pay for. That is the
"stop the line" message the notifier already carried. Overcharging is the safe
direction: it makes the desk too conservative, which costs opportunity, not
money.

On the entire observed record the alarm is silent — W: $0.0142 charged vs
$0.0142 predicted, exactly; baseball 2.00× over; combos under the ceiling — and
it fires only when the schedule moves against us.

### The prediction is per-instrument, and refuses rather than guessing

`calculate_fee` for singles (the live model: `fees.py` returns `_model_a`
alone, "the hedge is retired", while `_model_a_pre_july_2026` says "No
production caller. Do not price with it"), called **without** `fee_multiplier`
to match what `poll_fills` already stores in `fills.fee_predicted` per ADR
0058.

`combo_taker_fee` for `KXMVE`, because `_model_a` is **refuted** on
combinations: ADR 0046 records all 8 observed combo fills charged strictly
above `0.070·C·P·(1−P)`. This is not academic. On the combo fill in the
committed fixture (227.27 @ 0.1c, charged **$0.015930**) the flat model
predicts **$0.0159** — an undercharge, a live alarm on a real recorded fill —
while the ceiling predicts $0.0162 and is correctly silent.

An instrument it cannot price yields no prediction and is not reconciled. A
NULL `fee_actual` refuses too: the fill is recorded and simply not compared,
because a zero substituted there would alert on every unpolled fill. That is
the repo's rule — unreadable resolves to `None`, never `0`.

### Tolerance is borrowed, not invented

`FEE_MATCH_TOLERANCE_DOLLARS` is the same constant the gate's
`ABS(fee_actual - fee_predicted) > ?` already uses. Both sides land on the
measured `FEE_GRID_DOLLARS` ($0.0001), so a correct model matches a charge
**exactly** and only float dust needs absorbing. Its own comment makes the
argument: *"a tolerance wide enough to hide that is a tolerance wide enough to
hide anything."*

### One alert per day, not per fill

`check_fee` keys `failure:{kind}:{day}`. The call site fires **once per pass**
with the largest undercharge — *"a wrong fee model is wrong on every fill, and
one alert saying 'stop the line' is the whole message."* Verified against the
real `Alerter` and the real `notifications` table: three mismatching fills in
one poll plus a fourth an hour later produce **one** notifier call and **one**
row; a poll 26 hours later produces a second.

## Consequences

- `backend/portfolio_poll.py` (+344/−11) and `tests/test_portfolio_poll.py`
  (+364), 24 new tests. Expected values come from **real observed charges**
  (the 2026-08-14 fee-rate attribution cells W and R, plus a combination fill
  from the committed fixture), not from numbers the test invented.
- **14 mutations, 14 red.** Two pin the units, one pins the one-sidedness, one
  pins the day key, one pins the NULL refusal, one pins that only *newly
  stored* rows are reconciled.
- **`scripts/run_loop.py:1048` now passes the `alerter_factory`.** Without it
  the reconciliation would run and reach nobody — this repo's four-times-caught
  defect, and it would have been instance five in the same session that wrote
  ADR 0120 about it. The factory shape follows `watch_hedges_forever`: an
  `Alerter` binds a connection and the poller owns the only one it may use.
- **The alert copy now renders four decimal places.** `${predicted:.2f}` turned
  a real $0.0142-vs-$0.0162 divergence into "predicted $0.01, charged $0.02",
  deleting the direction and the size — the whole message — from a message
  whose subject is "stop the line". Sports fees have been charged to $0.0001
  since 2026-08.
- **`reconcile_fill_fees` is enrolled in `IO_CALLS`**
  (`tests/test_poller_holds_no_lock_across_io.py`), and enrolling it
  immediately found a real ordering defect: the guard counts an awaited
  enrolled call as a writer, and the alarm shares the poller's connection, so
  `Alerter._claim`'s INSERT sat between it and `await poll_positions(...)` —
  a Kalshi round trip — with no commit between. `_claim` commits internally,
  which is exactly why it was invisible. A `conn.commit()` after the
  reconciliation closes it.

  **That guard is a list, not a sweep**, so it could only find this once the
  name was added. Recorded at both ends: a new awaited call that talks off this
  box must be enrolled in the same commit.

### Units: dollars, end to end, no conversion

The repo's integer-tenths convention genuinely stops at the fee.
`fills.fee_actual` is REAL dollars — *"the one money field in this module not
stored in tenths"* — `calculate_fee` returns dollars, and `check_fee` renders
dollars. Every field and local is named `*_dollars` and a block comment says a
tenths value here would be 1000× high. Two of the fourteen mutations exist
solely to pin it.

## What this does not decide

- **Whether `core/fees.py` is correct.** The test is one-sided, so every
  "silent" case is consistent with a prediction that is far too high — and on
  baseball it demonstrably is, by policy.
- **Whether the flat coefficient should become combo-aware.** ADR 0046's
  tripwire is live on the committed record: that combo fill is charged $0.00003
  *above* what the deployed flat coefficient predicts. Nothing in production
  consumes that today. It is a partner decision, not a patch.
- **The gate is untouched.** `_fee_model_verified` filters `source = 'engine'`,
  so no `venue_hand` reconciliation can move the interlock in either direction
  (ADR 0043). Said in the docstring so nobody reads this as a gate input.
- **Delivery.** Whether Discord accepts the embed is `test_discord.py`'s
  question, and whether the deployed loop is running is the live box's.
