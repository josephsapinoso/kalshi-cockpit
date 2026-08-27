# 0077 — A cold open buys odds on the pass it woke, not on the next full pass

**Date:** 2026-08-27
**Status:** Accepted.
**Owner of the decision:** Joe, asked what to work on next and given the choice
between four open items. He picked this one.
**Touches nothing decided by** ADR 0071 §2.6 (the feed follows attention — this
does not change *what* is bought or *how often*, only whether the first buy of
a budget day has to wait for a full pass), ADR 0038, or the gate.

## 1. Three facts agreed, and none of them was wrong on its own

**`last_sweeps` is scoped to the budget day.** `decide_sweeps` reads
`last_sweep_by_sport(conn, since_ms=budget.day_start_ms(now_ms))`. So at every
10:00Z roll every sport goes back to having nothing pacing it, and `desk_wants`
reaches its bootstrap branch for all of them.

**`run_quote_pass` passed `allow_bootstrap=False`, hardcoded.** Correct about
the cadence: with no `last`, every pass wants every uncovered sport, so on the
15s quote cadence a *failing* sport would retry every 15s until the day's
credits were gone.

**`pass_kind` returns `"quote"` for any pass inside `last_full_ms + 900s`.** An
early wake — the thing `ArrivalWatch` was built in ADR-less form on 2026-08-25
to produce when someone opens the desk — lands there by construction.

Together: someone opens the desk after the day roll, the loop wakes within 5s,
runs a quote pass, and **that pass cannot buy anything**. They wait for the full
pass, up to 900s. Meanwhile `window_status` calls `desk_wants` with the default
`allow_bootstrap=True` and tells them a sweep is due **now**.

**Measured, not reasoned.** Budget day 20260827 rolled at 10:00:00Z. Its first
credit was spent at **10:13:56Z** — read off `api_credits` on the live volume.
Fourteen minutes.

## 2. The decision

`run_quote_pass` takes `allow_bootstrap`, **still defaulting to `False`**, and
`scripts/run_loop.py` raises it only for a pass that **follows an early wake**.

`scheduler.one_shot_wake(state)` turns `LoopState.woken_early` — the running
total `run_forever` already keeps — into a per-pass answer: *did an early wake
ask for the pass that is running now?*

**An event, not a state, and that is the entire safety argument.**
`attention.is_attended` is true for the whole 300s TTL while a quote pass runs
every 15s, so gating on it would reintroduce the hazard whole. A wake is at most
one per heartbeat (~60s from the page). `backend/odds/attention.py`'s
`ArrivalWatch` already draws this distinction for the same reason.

**Consumed on read**, so one wake cannot authorise two bootstraps. **Seeded from
the counter rather than from zero**, and read rather than incremented by one:
`woken_early` can move more than once between passes, and differencing would
leave a backlog of wakes each authorising a further bootstrap after the person
had gone.

### What actually bounds the spend

1. **One success ends it.** A bootstrap sweep is stamped `attention`, `desk` or
   `bootstrap` — never `manual` — so `_SERVED_SWEEP` counts it, `last_sweeps`
   paces the sport, and the flag changes no answer for the rest of the budget
   day.
2. **While sweeps are failing**, the one-shot caps the retry at one per
   heartbeat instead of one per 15s pass. Failing specifically: `_SERVED_SWEEP`
   requires `http_status < 400`, so an erroring sweep never starts pacing itself
   — which is why the flag, and not the pacing, is the bound in that case.

**It is NOT fully bounded by the attention slice, and a draft of this said it
was.** `desk_wants`' bootstrap branch fires with `trigger=ATTENTION` when
attended, which the slice caps. But `decide_sweeps` has a **second** bootstrap
path — a sport with no stored fixtures at all — also gated on this flag, which
stamps `trigger=BOOTSTRAP`; `attention_credits_spent_today` counts only
`ATTENTION`. That path is bounded by (1), (2) and the daily budget. The claim
was corrected rather than the path left unexamined, and it is now pinned by
`TestTheSecondBootstrapPathIsGatedByTheSameFlag`.

## 3. What was deliberately not changed

**`pass_kind` still returns `"quote"` after an early wake.** Making a wake force
a full pass was the other candidate fix and is rejected: a full pass measured
**86.4s** on live this morning, against a quote pass's few seconds, and it would
run on every cold open. The cheap pass was already the right pass — it just was
not allowed to buy.

**`window_status` still asks the optimistic question.** It calls `desk_wants`
without `allow_bootstrap`, so it can still say "now" when a quote pass would
have said "not yet". That is left open on purpose: the screen cannot see
`Tempo.last_full_ms`, which lives in the loop process, so it cannot know whether
the next pass is a full one. What this change buys is that for **a reader** the
promise comes true in seconds rather than in up to 900 — someone reading the
screen has heartbeated, so a wake is coming, so a bootstrap is coming. The
residual is asserted by `TestWhatIsStillNotGuaranteed` rather than claimed
closed, so it fails loudly if someone changes it without rewriting the reasoning.

This is why the "wide test blast radius" the backlog warned about did not
materialise. `desk_wants` and `pass_kind` are untouched, and the nine named
assertions in `test_scheduler.py` and `test_desk_follows_attention.py` that pin
their current behaviour on purpose all still pass unmodified.

## 4. How it was verified

**Eleven mutations observed red**, including flipping the default, swallowing
the flag before the planner, gating on attention instead of the wake, ungating
the second bootstrap path, and excluding `bootstrap` from `_SERVED_SWEEP`.

**Two came back GREEN and the code was moved rather than the tests kept.** The
predicate started life as a closure inside `run_loop.main`, so its tests
re-implemented its four lines against a real `LoopState`. They passed — and then
stayed green while the *real* predicate was mutated to drop its consume and to
difference by one. **A faithful re-implementation is a description, not a
constraint**: it is satisfied by the code as written and by any other code too.
`one_shot_wake` was moved beside `LoopState`, which is where it belongs anyway
since it reads a field that module owns, and both mutations then bit.

That is the same lesson as ADR 0076 §4 one turn later and in a new dress, which
is why it is recorded twice: the first instance was asserting a *ledger* instead
of a behaviour, this one is asserting a *copy* instead of the original. Both are
tests that cannot fail for the reason they exist.
