# 0005 — The gate's CLV floor counts actionable games only

**Status:** accepted, 2026-08-08

## Context

The live-money gate requires 300 scored independent games and a mean CLV
clearing an always-valid bound. Both read `clustered_clv`, which selected every
row with a `clv_tenths` and applied no filter on `suppressed_reason` or
`suggested_contracts`.

Recommendations are recorded in three states, the same three the Discord digest
reports:

| Population | Predicate | Meaning |
|---|---|---|
| `actionable` | not suppressed, `suggested_contracts > 0` | the strategy would have bet this |
| `no_edge` | not suppressed, `suggested_contracts = 0` | nothing to bet; the normal answer |
| `suppressed` | `suppressed_reason IS NOT NULL` | considered and refused, with a reason |

Every recommendation is scored on CLV whether or not it was bet, and that is
deliberate — it is what makes 300 games reachable without 300 wagers. But
scoring a population and *counting* it toward the floor are different decisions,
and only the first had been made.

The first live digest read `Scored on CLV 16 / 300`. Those 16 games were drawn
overwhelmingly from `suppressed` and `no_edge` rows, because `surfaced` has been
0 for the life of the instance. So the number under the label "our edge"
described the closing-line behaviour of any Kalshi market the instance happened
to poll.

## Decision

**The two CLV conditions count the `actionable` population.** The pooled count
and the full per-population breakdown stay on the screen beside it.

## Consequences

### It is a safety property, not a relabelling

Dilution toward zero would be merely conservative. The danger is different: a
**systematic** CLV among refused rows moves the pooled mean rather than blunting
it. `suspicious_edge` rows are the likeliest carriers — they are held back
precisely because their apparent edge was too large, and this project's first
rule is that a large apparent edge is a bug until proven otherwise. Pooled, that
population could arm real money on evidence about bets the strategy declines to
make.

### It moves the gate strictly further away, in both conditions

- The actionable set is a subset, so the 300-game floor is harder to reach.
- `always_valid_multiplier` **grows** as `n` shrinks — 9.84 at n=20 against 3.66
  at n=300 — so a small actionable sample must clear a taller bar, not a shorter
  one.

A money guard that changes should change in this direction. If the arithmetic
had made the gate easier anywhere, that alone would have been reason to reject
it.

### It reads 0 of 300, and that is the answer

Nothing has been actionable yet, so the floor reads zero and will for a while.
This was the stated objection to making the change: a screen that goes from
`16 / 300` to `0 / 300` looks like a regression.

It is answered by reporting rather than by counting the wrong thing. The gate's
detail carries `actionable Ng/Nr, no_edge Ng/Nr, suppressed Ng/Nr` beside the
counted figure, and when nothing actionable is scored it says why the zero is
correct. The Discord digest does the same, because that is the surface that
reaches a phone.

The deeper point is that the two findings were one finding. The 30-second
window starved the only population the gate should have been measuring, while
the counter read 16 because it was measuring a different one. Fixing the window
is what will make this number mean anything.

### It exposed a test fixture arming the gate from refused rows

`tests/test_quote_refresh.py::armed_db` built 400 scored games at
`suggested_contracts=0` — a record of "no edge here", four hundred times — and
that satisfied the floor. Every order-path test below it ran through a gate
opened by evidence the strategy would never have acted on. The fixture now
builds actionable rows.

A gate fixture has to be made of the population the gate counts, or it exercises
a path that real evidence cannot reach.

## What this does not establish

That `actionable` rows are *unbiased* evidence about the strategy. They are the
rows it would have bet, which is the right population, but they are selected by
the same suppression rules whose calibration is itself unproven. A change to
those rules changes the population, and `strategy_config_version` records that
the sequence changed without the gate reading it.

Nor does it fix the deeper split recorded in `tasks/NEXT.md`: CLV scores off
`entry_ask_tenths` while an order goes out at the live ask, and nothing joins
them because `orders` is still never written. The gate's evidence base and its
executed bets would describe different prices. That is an argument for
persisting orders before anything is armed.
