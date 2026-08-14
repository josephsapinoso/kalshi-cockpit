# ADR 0028 — The fee hedge is retired and the grid is deci-cent

**Date:** 2026-08-14
**Status:** Accepted
**Supersedes in part:** the max-of-models hedge described in `core/fees.py`'s
"Provenance, and why this module hedges".

## Context

`core/fees.py` has charged `max(Model A, Model B)` since the module was written,
because two secondary sources disagreed and Kalshi's own fee schedule returns
HTTP 429 to automated fetches. The module registered its own exit condition:

> *"Once a model is confirmed on a statistically adequate sample, replace this
> with that model and delete the hedge. Until then, treat any
> `fee_predicted != fee_actual` as stop-the-line."*

**That condition is now met, and both models are refuted.** Round three of the
fee-attribution programme produced five real taker fills on 2026-08-14, joining
six from 2026-08-10. Result and its independent audit:
`docs/measurements/2026-08-14-fee-rate-attribution-round-three-result.md`.
Re-derive with `scripts/reconcile_observed_fees.py`.

### What the 11 fills show

The charged fee is exactly `ceil(k · C · P · (1−P))` to **$0.0001, per order**:

| group | fills | admissible `k` |
|---|---:|---|
| `KXMLBGAME` + `KXMLBSPREAD` | 9 | `(0.0349691, 0.0350076]` |
| `KXATPDOUBLES` + `KXWNBAGAME` | 2 | `(0.0699608, 0.0700000]` |

Disjoint, ratio floor 1.998×. Fee-per-contract is **non-monotone in `P(1−P)`**,
so no function of `(C, P)` alone fits — the split needs an attribute outside
price and size. The two groups interleave in time (3 changes along the time
axis), so an intraday schedule move is refuted.

### What the deployed model returned

| series | `C` | `P` | charged | `calculate_fee` | ratio |
|---|---:|---:|---:|---:|---:|
| `KXMLBGAME` | 1 | 0.27 | 0.0069 | 0.02 | 2.90× |
| `KXMLBSPREAD` | 20 | 0.13 | 0.0792 | 0.20 | 2.53× |
| `KXATPDOUBLES` | 20 | 0.15 | 0.1785 | 0.20 | 1.12× |
| `KXWNBAGAME` | 1 | 0.28 | 0.0142 | 0.02 | 1.41× |

Wrong on **all 11**, in the flattering direction, and **not only on baseball**.

### The schedule changed; the old model was not wrong when written

Single-game settlements on this account split cleanly by date:

- **2025-11-27 → 2026-02-09** (NFL, NBA): **11 of 11 whole cents**, `k = 0.07`.
- **2026-08-10 →** (MLB, ATP, WNBA): **0 of 11 whole cents**, `$0.0001` grid.

So `_model_a` correctly modelled the schedule in force when it was calibrated.
It is **stale, not mistaken** — a distinction that matters, because it means the
failure mode to guard against is *not noticing a revision*, and the guard that
should have noticed (`fee_model_verified`) has never been able to fire: the
`fills` table has no live producer and the condition is pinned `met=False`
(`backend/gate.py:639-658`, ADR 0022).

## Decision

1. **`_model_a` rounds to `FEE_GRID_DOLLARS = $0.0001`**, not to the cent.
2. **`calculate_fee` returns `_model_a` alone.** The `max()` is retired. Model B
   — per-category multiplier, nearest cent **per contract** — matches 0 of 11
   fills and is wrong in *form*: per-contract cent rounding cannot produce a
   charge on a `$0.0001` grid. Keeping a refuted model inside a `max()` is not
   caution; it is a wrong number that only moves one way. It kept the charge at
   1.12×–2.53× the truth even *after* the granularity fix, because B won three
   of the eleven rows outright.
3. **`TAKER_COEFFICIENT` stays at `0.07`.** Baseball measured `0.035`, and this
   ADR deliberately does **not** adopt it. See "What we did not decide".
4. **`_model_a_pre_july_2026` is retained** with no production caller, so "the
   schedule changed" stays a claim this repo can demonstrate rather than assert.
5. **`fee_candidates` still reports Model B.** The harness's job is to show a
   refuted model failing. Pricing no longer consults it.

## Consequences

**The break-even bar moves from 52.00% to 51.75%** at 50c and size, and the
headroom against a −110 sportsbook's 52.38% goes from 0.38 to **0.63 points**.

This *reverses a correction CLAUDE.md made deliberately*, and the reason it is
not a regression is worth stating precisely: CLAUDE.md's 52.00% was correct as a
description of **what the code charged**, and it was explicitly attributed to
"the conservative maximum across candidate models". That maximum is now known to
be a refuted model. The bar was inflated by 0.25 points of hedge against a
hypothesis the data has killed.

**The applied bar is still an overstatement, by a known factor.** On baseball's
measured `k = 0.035` the bar is **50.88%**. So: 50.88% true on baseball, 51.75%
applied, 52.38% at a sportsbook. **None of this is an edge** — it is a lower bar,
and `actionable` is still 0.

**A published analysis is now stale.** `backend/analysis/joint_bound.py`
reproduces a registered table (Lane A §C1 / ADR 0017) whose premise is *"the
production path deliberately charges the maximum"*. Ten of its tests are marked
`xfail(strict=True)` rather than re-baselined: **re-deriving a registered table
to match new code is fitting after seeing the data**, and would silently rewrite
a published measurement. The joint bound must be **re-run** under the measured
model. Strict xfail means they turn green loudly when that lands.

**Suppression's fabricated-fair window moved** from 440–479 to 443–482 tenths,
same 4.0c width — a cheaper fee lets a fabricated fair survive at a slightly
worse ask. And the fee across that window is **no longer flat**: 17.3–17.5
tenths against a previously exact 20.0. The old flatness was an artifact of cent
rounding, not of the fee curve.

**Per-order rounding barely bites any more.** Near 50c, `0.07 · C · P · (1−P)`
is `0.0175 · C`, which lands exactly on the `$0.0001` grid for every integer
`C`, so the fee is exactly proportional to size. Sweeping the engine fixture
across 200–900 tenths leaves **12 asks** where edge still varies with size. One
test had to be re-anchored from 50.5c to 48.1c to stay discriminating.

## ADDENDUM 2026-08-14 — a fourth and fifth series, and one risky prediction kept

Two fills landed after this ADR was accepted. Neither changes a decision in it;
both narrow the open questions above, and one was a genuine falsification test.

| series | `n` | `P` | charged | cluster |
|---|---:|---:|---:|---|
| `KXPGATOUR` | 20 | 0.13 | `0.158400` | **high** (`k ≈ 0.070`) |
| `KXMLBKS` | 1 | 0.51 | `0.008800` | **low** (`k ≈ 0.035`) |

**`KXMLBKS` was a risky prediction and it held.** It is a *third baseball
series*, never sampled, and the two surviving hypotheses said different things:
H-SPORT predicted `$0.0088` outright; H-SERIES left it free. Observed
`$0.0088`. **H-SPORT staked something falsifiable and survived; H-SERIES risked
nothing and gained nothing.** Had it returned `$0.0175`, H-SPORT would have died
that afternoon.

Derived clusters now, grouping computed rather than asserted
(`scripts/reconcile_observed_fees.py`):

```
k in (0.0349691, 0.0350076]  n=10  MLBKS, MLBGAME, MLBSPREAD
k in (0.0699823, 0.0700000]  n= 3  WNBAGAME, ATPDOUBLES, PGATOUR
disjoint, ratio floor 1.999x
```

**Three series each, splitting exactly on baseball.** A per-series explanation
now needs **six independent lookups that happen to sort by sport** — that is
unparsimonious, and it is *not* a refutation. H-SERIES remains live.

**The liquidity-tier rival is weakened, not closed.** The high cluster contains
a WNBA market displaying 10,206 and the low cluster a prop displaying 19,749, so
depth does not separate them. A tier keyed on something other than displayed
size is still admissible.

**Durability is untouched and remains the blocker.** Every low observation still
lies inside 2026-08-10 → 2026-08-14. Five days is not a season.

**One process note.** The `KXPGATOUR` fill was not part of any calibration
design. **Joe confirmed 2026-08-14 that he placed it himself, deliberately, as a
recreational bet** — it is not a stray, a duplicate, or an automated order. It is
included in the fee evidence because excluding an observation for being unplanned
is exactly the freedom this document family removes, but it is **not** a
registered cell and no decision rule was fixed for it in advance.

**The general rule this establishes:** this account holds positions that are not
experiments. A future session reading `/portfolio/fills` must not assume every
fill is calibration data. Fee arithmetic may use them all — the venue charges
what it charges — but no *design* may count them as cells.

## What we did not decide

- **Which attribute carries the rate split.** Sport, series, and a per-market
  liquidity or maker-programme tier all fit. As of the addendum above the
  clusters are three series each and split on baseball, which makes a per-series
  reading unparsimonious — **but unparsimonious is not refuted**, and §10 of the
  round-three registration still forbids pooling across categories.
- **Whether `k = 0.035` is durable.** Every observation of it lies inside
  **four days**, on a venue whose schedule demonstrably changed within the
  preceding six months. A promotional or temporary MLB rate is not excluded, and
  no guard in the round-three design could see one — §7.3's time-varying rival
  was scoped to a 120-minute window.
- **H4.** These are trade fees. Settlement `fee_cost` equalling the summed fill
  fees is consistent with no settlement charge *and* with the field being
  entry-only. ADR 0027 stands.
- **Anything off the observed grid**: maker fees, in-play fills, sizes 2–19 or
  above 20, prices outside {13, 15, 27, 28, 48, 52}c, other baseball series,
  combos.

## Before `TAKER_COEFFICIENT` is lowered

1. A **second MLB observation window, ≥3–4 weeks after 2026-08-14**. Separates
   "the MLB rate" from "an August promotion". Costs one 1-contract fill.
2. A **third baseball series** and a **second `KXWNBAGAME` market** — the first
   separates per-sport from per-series, the second separates series-level from
   per-market tier.
3. A **series argument**, which `calculate_fee(price, count, maker)` and
   `settlement_fee(ask, contracts, maker)` do not take. Six call sites in the
   risk path.
4. **Re-run the joint bound**, so the two documents stop disagreeing.
