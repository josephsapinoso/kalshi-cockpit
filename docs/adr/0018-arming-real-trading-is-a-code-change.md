# 0018 — Arming real trading is a code change, not a config act

**Date:** 2026-08-09
**Status:** Accepted
**Extends `0005-the-gate-counts-actionable-games`. Corrects wording in `backend/gate.py` and `fly.live.toml`.**

## Context

This repo is going public and the live instance is attached to a funded Kalshi
account. Anyone reading it — a future session, a reviewer, Joe in six weeks —
needs an accurate answer to one question: **what stands between this deployment
and a real order?**

The answer on record was wrong, in the direction that matters.

`backend/gate.py` renders the `config_enabled` condition with the detail text:

> LIVE_TRADING_ENABLED is off — arming is a deliberate human act, kept separate
> from the evidence conditions

Every clause of that is true. The flag *is* a deliberate human act, and it *is*
kept separate from the evidence conditions. What the sentence does not say is
what the flag is **enough** for, and a reader supplies the obvious answer:
that turning it on arms trading.

It does not. **Turning it on moves no money.**

## The finding, verified from code

`backend/store/orders.py:129`:

```python
ORDERS_ARE_DRY_RUNS = True
```

A module constant. **No environment read, no config object, no override.**

`backend/api/routes.py:1382` — the only construction of `OrderPlacer` on the
request path — takes it:

```python
placer = OrderPlacer(dry_run=ORDERS_ARE_DRY_RUNS)
```

and `OrderPlacer.place` (`backend/kalshi/orders.py:458`) short-circuits to
`STATUS_DRY_RUN` before any POST is attempted. The only `dry_run=False`
constructions anywhere in the repository are in `tests/test_execution.py`.

**Verified from code**, by reading each site. The claim is narrow and negative —
*no configuration reaches this constant* — so it is asserted mechanically rather
than by inspection alone; see "What now enforces it" below.

## Why the correction matters in both directions

This is not a case of being safer than advertised and therefore fine. A wrong
mental model of the safety boundary is dangerous whichever way the reader
leans:

- **Believing money is at risk when it is not.** A session that thinks
  `LIVE_TRADING_ENABLED` is the last catch will treat the flag as radioactive,
  refuse to test the gate end to end, and leave the order path unexercised —
  which is how the path stays unverified until the day it is armed for real.
- **Believing the flag is the last catch.** The inverse and worse: someone flips
  it expecting a controlled first order, gets `dry_run` rows, concludes the
  system is broken, and starts *editing* to make it work — under time pressure,
  on the one code path that can lose money.
- **Believing a dry-run row is a fill.** `POST /api/orders` returns
  `status: "dry_run"` and `resulting_exposure_is_hypothetical: true`
  (`routes.py:1476`, `:1531`). Those fields are the only thing distinguishing
  the two outcomes, and a caller that ignores them records a bet that never
  happened. The evidence record is the product; a phantom fill in it is worse
  than no fill.

## The constant is load-bearing beyond the switch

`ORDERS_ARE_DRY_RUNS` is not merely "off". It **selects which exposure
population an order sizes against**, and the comment at
`backend/store/orders.py:121-128` says so: the order endpoint's advisory read
(`routes.py:1183`) and `reserve_order`'s authoritative check must agree about
that population, and two hardcoded booleans in two files are free to stop
agreeing — at which point an order is sized against one budget and admitted
against another.

So this is **not** a one-line flip whose blast radius is obvious from the line.
That is the substantive reason the constant exists rather than a literal at each
call site, and it is why "just set it to False and see" is the wrong move.

## What would actually have to move, in order

Enumerated so that no future session over- or under-estimates the distance to
live money:

1. **`ORDERS_ARE_DRY_RUNS = False`** in `backend/store/orders.py`. A code edit,
   reviewed, committed, CI-green.
2. **A REST client must be passed to `OrderPlacer`.** `routes.py` constructs it
   with none. `OrderPlacer.__init__` raises when `dry_run` is False and `rest`
   is None (`backend/kalshi/orders.py:431`), so step 1 alone does not produce a
   live order — it produces a 500. This is a genuine second barrier and it is
   recorded here so nobody mistakes it for the first one.
3. **All five gate conditions must hold**, including `LIVE_TRADING_ENABLED=on`,
   the 300-game sample floor, the always-valid noise boundary, and
   `_fee_model_verified`. As of this date the sample condition reads **0 of
   300** and has never been anything else.
4. **A deploy.** The image is rebuilt and released; `flyctl`/`gh workflow run`,
   which is Joe's, not an agent's.

Steps 1 and 2 are code. Steps 3 and 4 cannot be reached without them.

## What now enforces it

`tests/test_execution.py::TestArmingRealTradingIsACodeChange`, two assertions:

- `ORDERS_ARE_DRY_RUNS is True`.
- **No production call site passes `dry_run` as anything but the constant** — an
  AST walk over every non-test source file.

The second is source analysis rather than a behavioural test, deliberately. A
behavioural test that drove the endpoint and asserted "no POST happened" would
pass **for the wrong reason**: with the constant flipped, `routes.py` raises at
construction (barrier 2 above) instead of placing an order. That is this repo's
recorded failure mode — *a guard standing behind a stricter guard is
decoration* — so the test is written against the first barrier on its own.

Both assertions were verified by disabling what they guard and watching them go
red, per the repo rule. Recorded here because a green suite is not evidence
that a break was ever attempted:

| deformation | result |
|---|---|
| constant → `False` | first assertion red |
| call site → `dry_run=False` | second red |
| call site → `dry_run=True` (*harmless value!*) | second red — the drift the constant exists to prevent |
| walker looks for the wrong class name | second red on `found >= 2` |

The third row is the one worth keeping: a literal `True` at the call site is
behaviourally identical today and is still refused, because the defect being
guarded is the *divergence* between two sites, not the value at either.

The fourth guards against the vacuous pass. A walker that finds nothing asserts
nothing, which is how this shape of test goes green after the call site it was
written for is renamed or moved.

## Also corrected in this change

`fly.live.toml:20-21` stated that the agent fleet and the notifier "are not
wired into the runner, so nothing reads them yet." **Both halves were false**,
verified by reading the code:

- The notifier is wired. `scripts/run_loop.py:278` calls
  `DiscordConfig.from_env()` and the loop enters `DiscordNotifier` on every
  boot, handing it to `Alerter`.
- The fleet is wired. `runner.run_pricing_pass` (`backend/runner.py:489`)
  defaults `review=review_surfaced`, and both production callers go through it.

And the trap behind it, which is the part with a bill attached: **on live, what
keeps the Anthropic spend at zero is `surfaced == 0`, not the absence of a
key.** Live reports `agent_fleet_configured: true`, so the key is set;
`review_surfaced` returns early only because `_review_and_persist`
(`runner.py:750`) hands it an empty list. The first slate that surfaces a row
starts billing, at one call per surfaced row per pass against ~96 passes a day,
with nobody having budgeted it. Set a spend limit on the Anthropic account.

Note the shape: a spend gated by a **measurement outcome** rather than by
config. It switches itself on precisely when the project starts working.

## What this does NOT establish

- **This is a property of the code as of `b6ce9c9`, not a design guarantee.**
  Nothing in the architecture prevents someone adding an environment read to
  that constant. The test makes the change loud; it does not make it hard.
- **It says nothing about whether the order path is *correct*.** No order has
  ever been placed by this project, and `TestTheV2ResponseIsUnverifiedAndSaysSo`
  records that the V2 response shape is transcribed from a spec and has never
  been observed. Dry-run safety and execution correctness are different
  questions, and only the first is settled here.
- **It does not make the four fee-calibration trades safe to route through this
  path.** They cannot be: arming would require steps 1–4 above. They are placed
  by hand in the Kalshi app, and `/portfolio/fills` is the only channel their
  fee can come back through — see `scripts/capture_fills_fixture.py`.
- **Counted assumptions: zero.** Every claim above is verified from code at a
  cited line, except the live value of `agent_fleet_configured`, which is
  **measured from data** — read off the deployed instance's health endpoint on
  2026-08-09 and recorded in `tasks/NEXT.md`.
