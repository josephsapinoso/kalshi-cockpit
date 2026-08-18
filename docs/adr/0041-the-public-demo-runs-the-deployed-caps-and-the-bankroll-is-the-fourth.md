# ADR 0041 — The public demo runs the deployed caps, and the bankroll is the fourth one

**Date:** 2026-08-17
**Status:** Accepted, **amended 2026-08-18** — see the Amendment at the foot of this file. The decisions below stand; the claim that they reached
the demo's screen was false, and this ADR's own "What this does not
establish" section had already said so.
**Corrects:** the record's repeated count of "three caps" — `tasks/NEXT.md`
("leaves the three caps unset"), `tasks/lessons.md` ("all three caps were
inherited"), and the comment block in `fly.live.toml`. There are four dollar
caps and `BANKROLL_DOLLARS` is one of them.
**Does not change:** any live-instance risk value. `fly.live.toml`'s four
dollar figures are byte-identical before and after.
**Does not touch:** the gate, `ORDERS_ARE_DRY_RUNS`, or anything on the order
path. Nothing here loosens a limit anywhere.

## Context

`fly.demo.toml`'s entire `[env]` block was five lines — `INSTANCE_MODE`,
`DB_PATH`, `PORT`, `API_ORIGIN`, `LIVE_TRADING_ENABLED`. It set **none** of the
risk settings, so the public demo fell through to the dataclass defaults in
`backend/config.py`:

| setting | demo (inherited) | live (stated) | ratio |
|---|---|---|---|
| `BANKROLL_DOLLARS` | 1000 | 100 | 10× |
| `MAX_POSITION_DOLLARS` | 100 | 10 | 10× |
| `MAX_EXPOSURE_DOLLARS` | 400 | 40 | 10× |
| `MAX_DAILY_LOSS_DOLLARS` | 100 | 10 | 10× |
| `KELLY_FRACTION` | 0.25 | 0.25 | — |
| `MAX_ORDER_CONTRACTS` | 50 | 50 *(also inherited)* | — |

Ten times looser on every dollar figure, on the URL strangers see. A demo card
reading `Buy 17` was **one contract** at the roll actually deployed.

Nothing was red. The divergence lived entirely in the gap between two config
files, and no test compared them — `RiskConfig` was well tested, and the tests
exercised the *loader*, never the *deployment*.

**A previous session found this and wrote it into the record. The correction
went into the record and never into the config.** That is the whole reason this
is an ADR and not a one-line commit: the failure was not the discovery, it was
that a finding with no executable form decays back into the world it described.

## The kill check

Before changing anything, the repo was searched for a place where the
divergence had been chosen rather than inherited — `docs/adr/**`,
`tasks/NEXT.md`, `tasks/lessons.md`, and the comments in `fly.demo.toml`
itself. **Nothing.** No ADR mentions demo caps; the only hit anywhere in the two
large task files is a note that a screenshot happened to show the configured
bankroll. There was no decision to preserve.

## Decision

### 1. All six risk settings are stated explicitly in both deployed configs

`fly.demo.toml` gains all six. `fly.live.toml` gains `MAX_ORDER_CONTRACTS` —
the one setting *it* was also inheriting — written out at the value it already
had. That changes no behaviour; it removes an inheritance.

`tests/test_deployed_risk_caps_are_explicit.py` asserts presence for every
field of `RiskConfig` in both files. The required list is **derived from the
dataclass**, not hand-written, so a seventh cap added tomorrow fails the suite
until both files state it. A hand-written list is how the first six got to six.
A second test pins the derivation itself: for each field, setting its
upper-cased name in the environment must move `RiskConfig.load()`.

### 2. The demo's numbers match live — and that is a decision, not a default

The alternative was considered and rejected. A rounder demo bankroll ($1,000)
shows a wider spread of position sizes and photographs better; at $100 most
cards read `Buy 1`.

That is precisely the case *for* copying live. `Buy 1` is what this system
actually produces, and a portfolio piece whose thesis is **"the record is the
product"** (ADR 0038) cannot open by overstating its own size. This project's
standing rule is that the flattering number does not stand; publishing position
sizes an order of magnitude larger than its own deployed reality is that number
in its purest form, on the one screen with an audience.

The demo is a window onto the deployed system, not a brochure for it.

**These caps bound no money.** The demo holds no credentials and
`POST /api/orders` returns 403 whenever `INSTANCE_MODE=demo`. They bound the
*sizes on the screen* — and on that instance the screen is the entire product.

Divergence remains permitted; only divergence **upward** is not. A third test
asserts the demo is equal-or-tighter than live on all four dollar caps.

### 3. `BANKROLL_DOLLARS` is a cap — the fourth, and the outermost

`size_position` computes `stake = kelly_used * bankroll_dollars` and only
*then* trims it against the three `MAX_*` values. The bankroll is not an input
to sizing that the caps subsequently limit; it is the ceiling the caps are cut
out of.

Counting three is not a harmless imprecision. It is the reason `fly.demo.toml`
could omit the bankroll for its whole life without anyone noticing the public
screen was sizing off a $1,000 roll: a checklist of three was satisfied.

The related sub-claim, stated precisely because the loose version is wrong:
**at this bankroll `MAX_POSITION_DOLLARS` is the cap that binds an opening
order.** Reaching the $40 exposure cap in a single fill would need a staked
Kelly fraction above 0.40 — a full Kelly above 1.6 — which is not reachable.
`MAX_EXPOSURE_DOLLARS` binds by *accumulation* instead, at the fifth concurrent
market ($10 × 4 = $40). Both are real caps. They bind in different situations,
and a reading that treats them as interchangeable gets the demo's numbers
wrong.

## What this does not establish

That the numbers are **right**. No test can: a cap is a judgement about a
balance, and the suite does not know the balance. What is now established is
that the judgement was made in both deployed configs rather than inherited by
accident from a dataclass default written for a different bankroll.

Nor does it establish that the demo *displays* differently. The values were
verified in the config and in the loader; the visible change to a demo card is
predicted, not measured — the deploy is a separate step.

## Verification

Every guard was checked by disabling it and watching it fail:

| mutation | result |
|---|---|
| comment out `MAX_POSITION_DOLLARS` in `fly.demo.toml` | RED — presence |
| set demo `MAX_EXPOSURE_DOLLARS = "400"` | RED — never looser than live |
| `RiskConfig.load` reads `POSITION_CAP_DOLLARS` instead | RED — derivation pin |

Before the edit, 20 of 37 assertions were red, on exactly the six demo settings
and live's `MAX_ORDER_CONTRACTS`.

## Related

- ADR 0015 — the deposit does not decide what counts as evidence. Untouched:
  the gate's `actionable` counter is still scored against `config.REFERENCE_*`,
  which is fixed in code and unaffected by either file.
- ADR 0038 — the edge hunt is closed and the record is the product. The demo's
  honesty about its own size is downstream of that.

---

## Amendment — 2026-08-18: the config change did not reach the screen

**Status of the amendment:** Accepted.
**Amends:** decision 2 above ("the demo's numbers match live"), and the
Verification section, which verified the guards and not the outcome.
**Does not retract:** decisions 1 and 3. Stating all six settings in both files
is still right, and `BANKROLL_DOLLARS` is still the fourth cap.

### What was wrong

This ADR set six risk settings in `fly.demo.toml` so the public demo would size
at the deployed caps. **It did not.** The demo card went on reading `Buy 17` /
`$8.85` after the change, exactly as before it, because
`backend/seed_demo.py:405` was `risk = RiskConfig()` — a bare dataclass
instance — and the seeder never called `.load()`. `/api/board` serves
`suggested_contracts` straight off the stored row (`routes.py:2966`), and the
row was written at seed time under a $1,000 bankroll. **The environment is not
consulted anywhere on that path.**

Measured rather than argued. The demo was served twice from a fresh seed, once
with no risk settings in the environment and once with deliberately absurd ones
(`BANKROLL_DOLLARS=100000`, `MAX_POSITION_DOLLARS=5000`,
`MAX_EXPOSURE_DOLLARS=20000`, `MAX_DAILY_LOSS_DOLLARS=5000`):

| environment | rendered rows carrying a size |
|---|---|
| nothing set | HOU 1 @ $0.50, KAN 1 @ $0.63 |
| a $100,000 bankroll and a $5,000 position cap | HOU 1 @ $0.50, KAN 1 @ $0.63 |

**Byte-identical.** A hundred-thousand-dollar bankroll moves no number on the
demo board. Decision 2 was inert.

### This ADR predicted its own failure and shipped anyway

The prediction is already in the text above, under **What this does not
establish**:

> Nor does it establish that the demo *displays* differently. The values were
> verified in the config and in the loader; the visible change to a demo card
> is predicted, not measured — the deploy is a separate step.

That paragraph is correct and it is the whole problem. The limitation was
identified, written down in the deliverable, and then the status was set to
Accepted — which is what every downstream reader sees. **An honest caveat inside
an Accepted ADR does not stop the ADR from reading as closed.** It survived one
session before `Buy 17` was found on the public screen and taken at face value
by three design reviews.

The Context section had already named the shape of it — *"the tests exercised
the loader, never the deployment"* — and then all seven assertions in
`tests/test_deployed_risk_caps_are_explicit.py` were about the text of the two
toml files or about `RiskConfig.load()`. Confirmed by re-reading them and by
mutation: with `risk = RiskConfig()` put back into the seeder, that module
returns **37 passed**. Not one assertion moves.

**Naming a failure mode does not inoculate you against it.** The abstraction
level you check at is itself a choice, and an eloquent paragraph about the
previous level does not move you up one.

### The repair

**The seeder restates the deployed caps rather than loading them.**
`backend/seed_demo.py` now carries a module-level `DEMO_RISK`, and the choice
between the two options was put to Joe rather than resolved in passing, because
both goals in conflict are legitimate:

- `RiskConfig.load()` makes the demo correct on Fly and **wrong on any laptop
  with no environment set** — straight back to the $1,000 defaults. That breaks
  `seed_demo`'s own promise that *"the Board looks identical on every run and a
  screenshot stays accurate"*, which is not a nicety on a portfolio repo.
- Restating duplicates six numbers, and duplication drifts.

Restating was chosen, and **the duplication is what is under test**:
`tests/test_demo_sizes_at_deployed_caps.py::test_the_seeded_caps_match_the_deployed_ones`
compares `DEMO_RISK` against `fly.demo.toml` field by field, derived from
`RiskConfig`'s own fields, failing in either direction.

### The guard that can actually see the screen

The new module asserts on **`/api/board`'s payload** — the thing the card is
built from — not on config text and not on the loader. For every row the demo
renders, the served `suggested_contracts` and `stake_dollars` must equal what
`size_position` returns under a `RiskConfig` parsed out of `fly.demo.toml`.

**A cap check would not have worked, and this is the trap worth recording.**
$8.85 fits *under* the deployed `MAX_POSITION_DOLLARS = 10`. The constraint
that actually bound was Kelly off the bankroll, so "no card exceeds the
position cap" is green on the bug. The bound is kept — it catches a different
failure — but it is kept *beside* the exact recomputation, never instead of it.
The multiple is **17x on one row** and there is no general factor; compute it
per row.

### Verification of the amendment

Every claim above was checked by disabling something and watching it fail.

| mutation | new module | `test_deployed_risk_caps_are_explicit` |
|---|---|---|
| `risk = RiskConfig()` back in the seeder | **RED** — 2 failed (contracts, stake) | **GREEN — 37 passed** |
| absurd risk caps in the environment | no change to any rendered number | n/a |

The second row of that table is the amendment's finding, and the first row is
its point: the two modules disagree about whether the demo is correct, and only
one of them is looking at the demo.

One assertion in the new module was **corrected rather than kept as written**.
`test_the_seeder_does_not_use_the_dataclass_defaults` claimed it would fail "the
moment somebody puts `RiskConfig()` back". The mutation above proves it does
not — the constant still exists and still differs, and nothing in it observes
whether the seeder *uses* it. It is renamed to
`test_the_restated_caps_are_not_just_the_dataclass_defaults` and its docstring
now says what it does and does not cover. A test whose docstring overstates its
reach is the same defect this ADR is about, one size smaller.

### What the amendment still does not establish

- **Nothing about the live instance.** The live board is fed by the runner, not
  the seeder, and no live database was read.
- **Nothing about pixels.** The guard asserts on the payload, which is as close
  as a Python test gets to "what a stranger sees". Legibility still needs eyes.
- **That the deploy carries it.** The demo instance must be redeployed and
  re-seeded before the public URL shows `Buy 1`. Until then this repairs the
  code and not the screen — which is precisely the error being amended, so it
  is stated here rather than assumed away.
