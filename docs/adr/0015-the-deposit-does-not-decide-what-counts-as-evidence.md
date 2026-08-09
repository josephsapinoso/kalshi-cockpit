# 0015 — The deposit does not decide what counts as evidence

**Date:** 2026-08-09
**Status:** Accepted
**Supersedes nothing. Extends `0005-the-gate-counts-actionable-games`.**

## Context

The operator's real bankroll is **$100 a week**. The deployed config carried
`BANKROLL_DOLLARS = 1000`. Correcting that looks like a one-line edit, and a
previous draft of the handoff described it as one.

It is not. Setting it alone would have **silently disabled the evidence record**,
and nothing would have errored.

### The mechanism, measured rather than argued

`gate.POPULATIONS` defined the counted population as

    "actionable": "r.suppressed_reason IS NULL AND r.suggested_contracts > 0"

and `suggested_contracts` comes from `size_position` at the configured bankroll.
Running that function directly across bankrolls, at the deployed
`MIN_ORDER_CONTRACTS = 10`:

    bankroll  ask   fair   contracts  refused  constraint
      1000    50c   0.54       20      False   kelly
       700    50c   0.54       14      False   kelly
       400    50c   0.54        0      True    below_min_order_contracts
       250    50c   0.54        0      True    below_min_order_contracts
       100    50c   0.54        0      True    below_min_order_contracts

So at $100 every row is refused, `actionable` is **structurally 0 forever**, the
300-game floor can never increment however long the system runs, and the Gate
screen goes on reporting *"0 of 300, keep recording"* — a statement that is
true, unfalsifiable, and points at the wrong thing.

### Two limits on one quantity, again

The repo already has this lesson, and this is the third instance. At a $100
bankroll the minimum **net edge** needed to reach ten contracts, solved from
`full_kelly_fraction` at quarter-Kelly:

    ask    effective price   fair needed   edge needed
    10c        11.00c           14.9%         +3.9 pts
    30c        32.00c           40.7%         +8.7 pts
    50c        52.00c           62.0%        +10.0 pts
    80c        82.00c           87.9%         +5.9 pts

against `edge_ceiling_tenths = 40` (4c), above which an edge is suppressed as a
suspected defect. **At the 50c band the two ranges do not intersect**: no price
on the board carries an edge simultaneously large enough to size and small
enough to be believed. Only the extreme wings intersect at all, and there by a
tenth of a point — a 3.9-point edge on a 10c contract is a 39% relative edge,
which the ceiling exists to reject. Break-even for the 50c band is a bankroll of
roughly $300.

*(The handoff put the wings at "no intersection". The refinement is above: the
intersection is not empty, it is one tenth of a point wide at the far wing.)*

## Decision

**Three changes, and the third is the one that matters.**

### 1. `min_order_contracts` is deleted, not lowered — and no guard replaces it

It existed because Model A rounds the fee up on the whole order, so a small
order pays a rounding penalty a large one amortises away. Measured, per contract
against the large-order limit:

    ask     1 contract   5 contracts
    10c        0.00c        0.00c
    20c        0.88c        0.08c
    30c        0.53c        0.13c
    50c        0.00c        0.00c
    80c        0.88c        0.08c

Zero at 50c at *every* size, because both candidate models charge exactly 2c a
contract there.

**But the sizer was already paying it.** `effective_price` charges the fee a
*single* contract would pay, and that is the most expensive per-contract fee any
order size pays — verified exhaustively over all 999 tradeable prices, sizes
1–200, maker and taker, with no exception. Since `full_kelly_fraction > 0` holds
exactly when `fair > effective_price(ask, 1)`, and `EV(N) > 0` holds exactly
when `fair > price + fee(N)/N`, monotonicity makes the first imply the second at
every size.

So the minimum was **not preventing negative-EV orders. It was refusing
positive-EV ones**, and below roughly $300 it refused every order this tool can
produce.

The first draft of this change replaced it with a whole-order EV re-check inside
`size_position`. That was **decoration**: given the monotonicity above it can
never fire. It was deleted and replaced with a test asserting the property —
`TestSmallOrdersNeedNoMinimum` — so that if a future fee model ever charges a
large order more per contract than a single one, a test goes red rather than a
negative-EV order going quietly out. This repo has learned to recognise a guard
that cannot fire; writing a new one would have been the same mistake with a
better name.

`MIN_ORDER_CONTRACTS` still present in an environment now **raises at config
load**. A removed setting that is silently ignored is how a stale `.env` keeps
producing the old behaviour in someone's head.

The order endpoint keeps its own `verify_positive_after_fees` call: the size it
sends is `min(requested, authorised, resized)` and is genuinely a size the sizer
did not evaluate. It cannot fire under either current fee model either, and that
is recorded rather than hidden.

### 2. The caps are re-scaled with the bankroll, at constant fractions

`max_position_dollars`, `max_exposure_dollars` and `max_daily_loss_dollars` were
never set in `fly.live.toml` at all — they were inherited from the code defaults
of 100 / 400 / 100, which at $1,000 are **10% / 40% / 10%**. Lowering the
bankroll alone would have left a position cap equal to 100% of the account, an
exposure cap of 400%, and a daily loss limit that could only fire after the
whole week was gone. A safety system that cannot bind is worse than none,
because it reassures.

At $100 the same fractions are **$10 / $40 / $10**, and those are now stated
explicitly in `fly.live.toml` rather than inherited.

*(The handoff proposed "$15 / $40 / $25 reproduces the $1,000 ratios". It does
not — those are 15% and 25% against the actual 10% and 10%. The ratios are used
here, not the numbers.)*

### 3. The gate counts a **reference** sizing, not the operator's

A new column, `recommendations.reference_contracts` (schema v6), holds the same
decision sized against a risk profile **fixed in code**:

    REFERENCE_BANKROLL_DOLLARS      = 1000.0
    REFERENCE_MAX_POSITION_DOLLARS  =  100.0
    REFERENCE_MAX_EXPOSURE_DOLLARS  =  400.0
    REFERENCE_MAX_DAILY_LOSS_DOLLARS=  100.0

`POPULATIONS` now splits on that column. The two questions were being answered
by one number and they are different questions:

- **What may be bought today?** `suggested_contracts`. Depends on the deposit,
  on open exposure, on the day's P&L. Correct that it moves.
- **Did the strategy have a bet here?** `reference_contracts`. The 300-game
  floor asks "has this system demonstrated it can pick?", and the balance in the
  account is not part of that answer.

Four details that are decisions rather than mechanics:

- **Not configurable.** An env var for the reference bankroll would rebuild the
  same trap one level up.
- **Scored against a clean book** — zero exposure, zero position, zero P&L.
  Whether a game is evidence must not depend on what else happened to be open.
- **`kelly_fraction` and `max_order_contracts` are carried through, not
  replaced.** Those are strategy parameters, not facts about the account, so
  changing one *should* move the counter — and `strategy_config_version` records
  which version wrote each row, so the two regimes stay separable. A deposit is
  recorded nowhere and never could be.
- **The depth check runs at the larger of the two sizes.** The reference order
  is usually the bigger one, and letting a row count toward the floor at a size
  the book could not have filled is the flattering direction.

## What this does not relax

Stated explicitly because ADR 0005 exists to stop the gate being reached by
changing what it counts, and this changes what it counts.

- The 300-game floor is unchanged.
- The always-valid noise guard is unchanged (3.66 standard errors at the floor,
  not 2).
- Clustering by game is unchanged.
- Every suppression rule zeroes `reference_contracts` exactly as it zeroes
  `suggested_contracts`, including the agent fleet's veto in
  `with_added_suppression`.
- `fee_model_verified` and `LIVE_TRADING_ENABLED` are untouched.
- **On the $1,000 deployment that wrote the existing record, the two columns are
  equal by construction.** The v6 migration backfills `reference_contracts` from
  `suggested_contracts`, which is an identity for every row that exists when it
  runs, not an estimate. It stops being an identity the moment the deployed
  bankroll changes — which is the next thing that happens, and is the point of
  the column. `IS NULL` is what keeps the two populations apart.

So this changes **nothing** about the evidence already on the record, and stops
a future deposit change from rewriting what that record means.

## Consequences

- A row can now be counted toward the floor while `suggested_contracts` is 0 —
  the strategy had a bet, the balance could not fund it. The Gate screen says so
  in words rather than leaving "actionable" to be read as "you can buy this".
- The Board still shows what may actually be bought. It is the honest number for
  a person deciding, and it is smaller than it was.
- At $100, a 4c edge at 50c now sizes to **4 contracts** rather than being
  refused: cost $2.00, fee $0.08, EV +$0.16.
- One more column that a future backfill must be careful with. ADR 0016's
  provenance column and this one answer adjacent questions and must not be
  conflated: provenance says *where a row came from*, this says *whether the
  strategy wanted the bet*.

## What this does not establish

That any edge exists. That the gate should open. That betting at $100 is a good
idea. Only that the size of the deposit cannot silently switch off the
measurement — which it could, and which nothing would have reported.

The gate remains locked, and the binding constraints on it are unchanged: the
four fee-calibration trades, and 300 scored actionable games.
