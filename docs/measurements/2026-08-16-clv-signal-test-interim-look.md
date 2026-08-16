# CLV signal test — first interim look. UNRESOLVED, and `beta` is negative

**Registered:** `docs/measurements/2026-08-09-preregistration-clv-signal-test.md`
**Harness:** `scripts/run_signal_test.py` on `inspect_live_db.py clv-signal-pull`
**Taken:** 2026-08-16, live box, 3,692 rows, `truncated: false`
**Verdict:** **UNRESOLVED.** `G = 199` is below the registered floor of 300, and
a look below the floor may not declare SIGNAL, BUG or NO SIGNAL.

This is the first time `beta` has ever been computed. Until today no code in the
repo could compute it — the statistic ADR 0034 binds the A-versus-F re-read to
did not exist.

## The result

```
G (registered cluster key)   199        rows 3,692
P1 half-spread coverage      1.0000     (floor 0.90)  PASSES

beta_hat                     -0.1412
gamma_hat (half-spread)      -0.7407
se_cluster                    0.0478
se_classical                  0.0202    <- NOT the one used
always-valid multiplier       4.0373
smallest resolvable beta      0.1929
always-valid interval        [-0.3342, +0.0517]

VERDICT                      UNRESOLVED  (G = 199 < 300)
```

Per-group, **diagnostic only — `market_type` is not a registered cut**:

| group | n | G | share | `beta` |
|---|---:|---:|---:|---:|
| moneyline | 2,440 | 118 | 66.1% | −0.082 |
| prop | 1,252 | 81 | 33.9% | −0.519 |

Both are negative, so the pooled figure is not being carried by one arm against
the other — which is the failure the per-group rule exists to catch.

**Sensitivity to §7's modal-config rule**, run because the record carries four
strategy versions and the rule exists to stop a mixture being read as one
population:

| population | rows | G | `beta_hat` | interval |
|---|---:|---:|---:|---|
| all versions | 3,692 | 199 | **−0.141** | [−0.334, +0.052] |
| modal version (3) only | 1,672 | 86 | **−0.053** | [−0.205, +0.099] |

The sign and the qualitative reading survive the restriction; `G` does not, and
at 86 clusters the modal-only look resolves almost nothing. Both intervals lie
entirely below 0.40.

## What this settles: the sign disagreement is resolved

Two earlier computations of a raw slope on an approximation of this population
returned **+0.102** and **−0.109**, and neither reproduced the other. ADR 0034
recorded that disagreement as a precondition of the re-read. It is now
explained, and both were wrong for the same reason:

**Neither had the half-spread control, because the dump they ran on carried no
quote columns at all.** `gamma_hat = −0.741` is large — the control is not
decorative, it is load-bearing, and omitting it is exactly correction C2's
contamination left in place.

The other differences compounded it. The registration's cluster key is
`COALESCE(event_ticker, ticker)`, not ADR 0029's `odds_event_id`; those give
**199 and ~125** on this record. And the earlier populations missed
`stale_kalshi_quote` and applied the price bound inconsistently.

**The +0.637 pooled figure reported earlier is fully accounted for.** It was
computed on everything, including 3,127 `stale_odds` rows the registration
excludes by name, and it was carried by props across 17 clusters. On the
registered population with the registered control, `beta = −0.141`.

## What it does NOT settle, and this is the part to hold

**The verdict is UNRESOLVED and that is a real answer, not "no signal."** At
`G = 199` the registration forbids declaring. The smallest effect this look can
resolve is **0.193**, and the estimate is smaller than that in absolute value.

**But the direction is worth stating precisely, because it is prospective and
not a declaration.** The always-valid interval is `[-0.334, +0.052]`. Its upper
limit is already **below the registered NO-SIGNAL threshold of 0.40**. If the
estimate holds as `G` grows to 300, the registered verdict at that look is
**NO SIGNAL**, which under ADR 0034 takes ADR 0021 §8 option A and stops the
consensus-only line.

That is a forecast about a rule, not a result. It could move. It is recorded
here so that when it lands nobody can claim the outcome was a surprise, and so
that nobody reads today's UNRESOLVED as encouraging.

## A defect this look surfaced, unasked

**1,826 of 3,692 rows (49.5%) have a joined quote whose derived ask disagrees
with the stored `entry_ask_tenths`.**

Amendment §A8.2 requires these be counted separately from rows with no quote at
all, and the reason is that they are a different problem: not missing data, but
a control recovered from a *different observation* than the one the
recommendation was priced from. Rows with no quote at all: **0**. So P1 passes
at 1.0000 coverage while half the controls may be joined off the wrong instant.

**This is not established as a defect and is not treated as one here.** The join
takes the last quote at or before `created_ms`, and a market that moved between
the quote and the write would produce this legitimately. What is established is
the count, and that it is large enough to matter. Whether it biases `gamma_hat`
— and therefore `beta_hat` — is unmeasured.

## What this cannot establish

- **Nothing about tradeability.** A `beta` of any sign says whether the engine's
  edge number predicts closing-line movement. It does not say the movement
  survives fees or was fillable at the quoted size.
- **Nothing at `G = 300` yet.** This look may not be cited as the outcome.
- **Nothing about the fee correction.** Every row here was scored under
  `TAKER_COEFFICIENT = 0.07`, which is about 2× the measured baseball rate. The
  population is pinned before any fee change precisely so the comparison stays
  clean; a corrected fee would move `edge_tenths` and restart this.
- **The strategy-config mix is not controlled.** Versions 1/2/3/4 appear
  (359 / 56 / 1,672 / 1,605). §7's modal-version rule is available as
  `--modal-config-only` and was **not** applied to the numbers above.
- **`market_type` is not a registered cut.** The per-group table is a
  diagnostic and can downgrade a verdict, never create one.
