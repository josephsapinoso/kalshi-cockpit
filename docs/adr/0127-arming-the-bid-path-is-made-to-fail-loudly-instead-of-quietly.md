# ADR 0127 — Arming the bid path is made to fail loudly, instead of relying on a justification that expires quietly

Status: accepted
Date: 2026-09-09

Acts on the second half of ADR 0120's reachability finding. Does not amend
ADR 0115 (the bid path stays disarmed) and wires nothing.

## Context

ADR 0120's reachability walk found `KalshiRestClient.orders` is read by
nothing, so **nothing reconciles against the venue's own view of resting
orders.**

That is inert today, and for a good reason: `POST /api/parlays/bid` was
disarmed on 2026-09-08 (ADR 0115) because Joe pays the ask and does not make
offers. Nothing rests, so nothing needs reconciling.

**This repo has just been bitten by exactly that shape of argument.**
`Alerter.check_fee` had no caller and said why — no order had ever been placed,
so there was no fill to reconcile. The reasoning was correct, deliberate and
documented, which is what makes it the best version of the mistake. Then the
hand-bet path was armed on 2026-09-08, real fills landed, and the excuse
expired **in silence**: 40 hours of fills went unreconciled because a condition
changed and a comment did not (ADR 0123, `tasks/lessons.md` 2026-09-09).

The bid path is the same argument, one flag away from the same outcome. A
session that re-arms `COMBO_ORDERS_ARE_DRY_RUNS` gets no signal at all that the
venue's order view is unread.

## Decision

**Do not wire `KalshiRestClient.orders`.** Nothing rests. Building a caller for
a capability nobody needs is how the four "built but never called" instances
happened.

**Instead, convert the state into a trigger.**
`tests/test_bid_path_arming_requires_order_reconciliation.py` asserts the
conjunction:

    COMBO_ORDERS_ARE_DRY_RUNS or (a production reader of `.orders` exists)

It is green today because the flag is `True`
(`backend/store/combo_orders.py`). It goes **red the day someone flips that
flag** without landing a reconciler, and its failure message names ADR 0115,
states the re-arming convention, and says plainly what has to ship alongside.

"No order rests" is a **state**, and a state's justification rots. "Re-arm the
bid path and this goes red" is a **trigger**, and a trigger survives contact
with the future. That is the generalisable half of this decision and it is the
reason the ADR exists at all.

### Two things deliberately not done

- **`orders` is NOT enrolled in `MUST_HAVE_CALLERS`.** That list asserts
  unconditional requirements; this one is conditional on a flag. Enrolling it
  would fail today for the wrong reason — no caller exists, correctly.
- **The scanner does not reuse `test_has_callers.callers_of`'s bare-symbol
  match.** That matches `ast.alias(name="orders")`, which false-positives on
  `from ..store import orders as orders_store` in `routes.py` — an import with
  nothing to do with the REST method, and one that would have made the guard
  silently vacuous. It matches the call shape `<expr>.orders(...)` instead,
  which can only reach `KalshiRestClient.orders` because that is the repo's
  only `def orders(`. A companion test fails if a second one ever appears, and
  a not-vacuous check proves the AST pattern finds real calls using
  `KalshiRestClient.fills` as a known-positive control.

`production_sources()` and `_excluded_from_image()` **are** reused, so "is this
code that ships in the image" has one definition.

## Verification

`COMBO_ORDERS_ARE_DRY_RUNS` was flipped to `False` in place: the test went
**red** with the full message. Restored: **green**, 4/4. The 151 tests in
`test_has_callers.py` and `test_reachable_callers.py` are unaffected.

## The companion documentation fix

The same walk found `clv.horizons_agree` and `validate.summarise` are reached
by nothing — so two of CLAUDE.md's Measurement rules ("re-run at a second
horizon", "a pooled number is not a finding until the parts agree") have **no
running implementation**.

**They are not wired**, and that is the decision: the signal is settled
negative, no measurement will run through them, and wiring them serves no
decision. CLAUDE.md now says so instead of implying enforcement that does not
exist, and records the mitigation — the `beta` fits ran through
`analysis/clv_signal.py` and `analysis/signal_test.py`, which *are* reached.
Both rules stand as the standard a human analysis is held to.

## What this does not decide

- **Whether the bid path should ever be re-armed.** ADR 0115 owns that; Joe's
  word disarmed it and re-arming needs his.
- **What a reconciler should do** when it is eventually needed — only that one
  must exist before the flag flips.
- **Nothing about the engine path**, which is dry for its own reasons
  (ADR 0018) and has its own interlock.
