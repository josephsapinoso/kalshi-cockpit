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

---

## Annotation, 2026-08-17 — THE POPULATION CHANGED COMPOSITION THE DAY AFTER THIS LOOK, AND THE DRIFT IT WILL PRODUCE POINTS AT GOOD NEWS

**Read this before taking the `G = 300` look.** Nothing above is retracted. What
changed is *what clusters 200 through 300 are made of*, and it changed in a way
that is expected to move `beta_hat` toward zero for a reason that is not
evidence.

**What happened.** ADR 0032 turned scheduled prop buying off on 2026-08-16
(`ODDS_BUY_PROPS_ON_SCHEDULE = "false"`, `fly.live.toml:318`, commit `83432c1`,
deployed — confirmed on the live machine's environment, not read from the toml).
The last per-event prop call in `api_credits` is **2026-08-16T17:06:36Z**.

**Why that reaches this document.** ADR 0032 §3 argues props "cannot move the
denominator", and for **the gate's** denominator that is correct: since ADR 0029
`gate.clustered_clv` clusters on `event_links.odds_event_id`, and a prop ladder
inherits its game's id, so it collapses onto the game.

**This registration does not use that key.** `backend/analysis/clv_signal.py:109-114`
says so in terms, and the file was written to say it:

> *"The cluster key is `COALESCE(m.event_ticker, r.ticker)` and it is NOT the
> gate's key. ADR 0029 clusters on `odds_event_id` so a prop ladder collapses
> onto its game; this registration predates that and clusters on the Kalshi
> event. On the current record the two give **210 and 125** — a 68% difference —
> so a `G` quoted without its key is meaningless."*

Under the registered key a prop ladder **is** its own cluster. The per-group
table above is the measurement of what that was worth: **prop supplied 81 of the
199 clusters, 33.9% by row share and 40.7% of `G`.** ADR 0032's arithmetic was
computed against the other 300 and is sound there. It does not transfer here,
and §6 of that ADR already flagged the adjacent risk as *unmeasured*.

**The predictable misread, stated now so it cannot be discovered later.** The two
arms are `moneyline −0.082` and `prop −0.519`. Accrual from 2026-08-16 onward is
moneyline-dominated. A pooled estimate whose intake has lost its more-negative
arm is expected to **drift toward zero** — that is, toward the NO-SIGNAL
threshold of 0.40 and toward what reads as improvement. **A future session that
takes the `G = 300` look, sees `beta_hat` less negative than −0.1403, and reads
it as the signal emerging will be reading a composition change as evidence.**

**Direction only. The magnitude is NOT computable from what is published here,
and the attempt has already been made so nobody repeats it.** Re-weighting the
two arms does not reconstruct the pooled figure by any weighting: row-weighting
gives −0.230, cluster-weighting −0.260, against a published pooled
`beta_hat` of **−0.1412**. That is not a defect. The pooled number is one
regression carrying the `half_spread_tenths` control (§C2), not a mixture of two
sub-regressions, so it is not required to lie between its arms and does not.
**Do not treat the arithmetic disagreement as a bug, and do not publish a
projected `beta`.**

**The post-cutover population is not a clean step function either.** The
on-demand prop tap survives ADR 0032 by construction: `POST /api/odds/refresh`
with an `odds_event_id` (`backend/api/routes.py:1622`) reaches
`fetch_and_store_props`, whose schedule guard at `backend/runner.py:1667-1670`
is entered only when no fixture was **named** — so a named tap bypasses it. It is
wired to a live per-fixture button in the phone UI
(`frontend/src/components/RefreshOddsPanel.tsx:89-92`). So the intake from here
is *"moneyline, plus whatever Joe taps"* — human-determined, not a fixed
population.

**As of 2026-08-17 that tap has never fired.** All 111 `api_credits` rows in the
life of the table carry `trigger` NULL; the predicate is
`COALESCE(trigger, '') != 'manual'`. So the mix today is effectively
moneyline-only, and if that changes it will change discretionarily rather than
on a schedule. **Whoever takes the `G = 300` look must report the arm split at
that time**, not assume this one.

**What this annotation does not do.** It does not reverse ADR 0032 and must not
be cited to. Props were 260 of ~302 credits per cluster; restoring them to buy
faster accrual toward a statistic `CLAUDE.md` forbids any roadmap from depending
on would be spending money to accelerate a number nobody is allowed to wait for.
The decision stands; only its sourcing was wrong, and that is corrected in ADR
0032's own annotation.
