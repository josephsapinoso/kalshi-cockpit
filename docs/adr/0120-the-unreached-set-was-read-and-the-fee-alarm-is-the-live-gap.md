# ADR 0120 — The unreached set was finally read, and only one entry in it costs anything today

Status: accepted
Date: 2026-09-09

## Context

`tests/test_reachable_callers.py` walks the deployed closure from real entry
points and computes which definitions are reachable. Its docstring records
that on **2026-09-05 the walk left 54 of 1,086 definitions unreached**, and it
declines, deliberately, to assert that the unreached set is dead:

> a walk that over-approximates reachability cannot also be the authority on
> death

That was the right call and it had an unintended consequence: **the list is a
finding for a human, and no human read it.** Meanwhile this repo caught its
fourth confirmed "built but never called" defect by hand, and nearly recorded
a fifth that turned out to be something else (ADR 0119). The instrument for
finding these cheaply already existed and was sitting uncollected.

It was run on 2026-09-09 through its own machinery, and every entry triaged.

## What the walk says now

| | 2026-09-05 | 2026-09-09 |
|---|---|---|
| unreached | 54 | **55** |
| definitions in the deployed closure | 1,086 | **1,099** |

The baseline **reproduces in shape but not in number**, and the drift is
partly datable: `1cb51af` (2026-09-08, ADR 0112) removed the hand-bet brakes
from `backend/api/routes.py`, newly orphaning three `manual_orders` readers.
The exact 09-05 → today delta was not computed — it needs the walk re-run
against `c8ae35a` in a throwaway worktree, and the sweep was read-only.

Note for anyone re-running it: **1,086 is unique *names*, not raw definitions**
(1,215 raw across 99 files). Comparing the wrong quantity will look like a
large regression.

## Findings

All 55 fall into four buckets, and the headline is how few are the dangerous
kind:

- **(d) walk false positives** — reached by a mechanism the walk cannot see.
  `logging.Filter.filter` and `formatException` are framework protocol
  methods. `combo_orders.working_orders` **is live** — called at
  `backend/api/routers/parlays.py:369` under an aliased import
  (`working_orders as working_combo_bids`), and the walk matches names, not
  bindings.
- **(b) deliberate records and rejected branches** — the largest group, and
  most already say so in their own docstrings: the retired fee models
  `_model_a_pre_july_2026` / `_model_b` ("retained as evidence, not for
  pricing"), `loop_failures_since` ("no production caller, and it is kept
  deliberately"), `attention.seen_at_least_once_since` ("the instrument, not a
  trigger input"), and `manual_orders.cooloff_until_ms`, whose caller-side
  comment at `backend/api/routes.py:3304-3310` says it is *"deliberately NOT
  deleted… pinned uncalled from this route so 'built but never called' stays
  deliberate here."* That is the pattern working as intended.
- **(a) genuinely dead** — small and cheap: `AgentUnavailable`,
  `round_trip_fee`, `breakeven_edge_cents`, `cents_to_tenths` (its migration
  finished), `PriceBand.contains`, `PriceGrid.is_on_grid`,
  `KalshiRestClient.delete`.
- **(c) a real capability that does not run** — the ones that matter, below.

### The one that costs something today: the fee-mismatch alarm

`Alerter.check_fee` (`backend/notify/alerts.py:1139`) → `fee_mismatch`
(`backend/notify/discord.py:610`). Uncalled, and its docstring justified that:
*"`ORDERS_ARE_DRY_RUNS = True` means this instance has never placed an order,
so there is no fill to reconcile."*

**That justification expired on 2026-09-08.** It remains true of the engine
path and is now false of the desk: the hand-bet path is armed
(`MANUAL_ORDERS_ARE_DRY_RUNS = False`, `MANUAL_ORDERS_ENABLED = "true"` at
`fly.live.toml:150`) and real fills landed (ADR 0113). **Fills exist and
nothing compares their charged fee to `core/fees.py`, and the absence is
silent.**

It matters more than a missing alarm usually would: `TAKER_COEFFICIENT` is
knowingly held at **0.070** while nine observations pin k near **0.035** (ADR
0028), on the grounds that which attribute carries the split is unresolved.
The alarm that would notice the schedule moving under the armed path is
precisely the one not wired.

**The prerequisite was checked rather than assumed, and it is already met.**
The question was whether the venue's charged fee is persisted per fill at all,
as opposed to a prediction, Joe's typed estimate, or the price paid. It is —
just not where you would look first:

- `manual_orders` does **not** hold it. `OrderOutcome` parses Kalshi's
  `average_fee_paid` at order time (`backend/kalshi/orders.py:566`) and
  `record_outcome` (`backend/store/manual_orders.py:628-649`) drops it;
  `response_body_json` is a dict this repo constructs, not the venue's reply.
  The engine's `orders` table has the same shape and the same hole.
- **`fills.fee_actual` is the ground truth** (`backend/store/schema.sql:878`,
  comment: "fee_actual is ground truth from Kalshi"), written by
  `backend/portfolio_poll.py:245` from `/portfolio/fills`, with
  `source = 'venue_hand'` marking a hand bet. It joins to the order row on
  `kalshi_order_id = fills.venue_order_id`.

**So wiring the alarm needs no schema change** — it needs a caller that
computes the prediction for a fill and compares. That is why it became work in
this session rather than an open question.

### The other (c) items, and why none is urgent

- **The CLV validation layer runs from nothing.** `clv.load_observations`,
  `clv.horizons_agree`, `validate.summarise`, `validate.summarise_clv`. Every
  referrer is a test or `backend/model/backtest.py`, itself imported only by
  `tests/test_model.py` — orphan of an orphan, and not in the deployed
  closure. So two CLAUDE.md measurement rules have no *running*
  implementation: "bucket by the price you would actually pay" is what
  `summarise` does, and "re-run at a second horizon" is exactly
  `horizons_agree`. **Mitigated, not ignored:** the beta fits went through
  `analysis/clv_signal.py` + `analysis/signal_test.py`, which are reached, and
  the signal is settled negative for planning, so nothing is being decided on
  the missing checks.
- **Teaser and margin pricing — 15 definitions, and the screen already admits
  it.** `core/teaser.py` and most of `backend/model/margins.py`. What runs is
  only the screen half: `GET /api/builder/wong-screen` calls
  `find_wong_candidates`. The route's own copy says pricing *"needs an
  empirical margin distribution fitted per spread bucket; without one the
  Builder refuses rather than guessing"*. **Absence is loud**, in every
  response. Disclosed, not hidden.
- **Same-game correlation cannot be obtained on the live desk.**
  `implied_correlation` is operator-invoked only
  (`scripts/measure_combo_correlation.py`). Consequence: same-game combos stay
  permanently refused on the screen and only a human at a terminal can change
  that.
- **Nothing reads the venue's working orders.** `KalshiRestClient.orders` has
  zero call sites. **Inert today** — the bid path is disarmed (ADR 0115) so
  there should be nothing resting. It becomes a real, silent gap the day the
  one-line re-arm happens.
- `discovery.coverage_by_league` — "for the Board and for scope decisions",
  called by nothing. Small.

### The near-miss, and it is the important methodological finding

`OrderBook.is_quotable` (`backend/kalshi/orderbook.py:327`) is reached only by
`KalshiWebSocket.quotable_books`, which is reached by nothing. Its docstring
claimed *"the order endpoint checks this independently of whatever the UI
decided to render."* **The endpoint does check independently — but not through
here.** `backend/live.py:293` reads `book.invalid` directly, and staleness is
enforced from stored quote ages via `StalenessConfig`, with
`MAX_KALSHI_QUOTE_AGE_S = "30"` deployed at `fly.live.toml:539` and
`backend/gate.py:830` refusing past it.

So the order path is guarded and nothing is at risk. What was wrong was **a
docstring asserting a call chain that does not exist** — the same mechanism
that manufactured the four earlier false beliefs, and the reason this one was
nearly miscounted as a fifth.

## Decision

1. **Read the unreached set on a schedule, not by accident.** It is the
   cheapest instrument for this repo's most expensive recurring defect and it
   already exists. This ADR is the first reading; the next belongs in a
   session that has cause, not in a calendar.
2. **The two stale docstrings are corrected in place**, because a wrong
   justification is worse than none — it stops the next reader looking:
   - `is_quotable` now states it has no production caller, names where the
     real guard lives, and says **do not restore the claim of a caller**.
   - `check_fee` now states that its dry-run justification expired on
     2026-09-08 and that the gap is open and carried in `tasks/NEXT.md`.
3. **Nothing was deleted.** The (a) bucket is seven small functions and
   deleting them buys nothing this session; they are recorded here so the next
   reader does not re-triage them.

## What this does not decide

- **Whether the fee alarm gets wired**, or how. That waits on where the
  charged fee is persisted, and it is an open item.
- **Whether the walk should become a guard.** It should not, on its own
  reasoning — over-approximate reachability cannot be an authority on death.
  What could change is *what is enrolled* in `MUST_HAVE_CALLERS`, which is a
  separate decision nobody has taken.
- The exact 09-05 → 09-09 membership delta. Three additions are named; which
  names left the set is unestablished.
