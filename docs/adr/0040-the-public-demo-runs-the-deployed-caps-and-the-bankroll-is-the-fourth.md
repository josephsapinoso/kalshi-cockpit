# ADR 0040 — The public demo runs the deployed caps, and the bankroll is the fourth one

**Date:** 2026-08-17
**Status:** Accepted
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
