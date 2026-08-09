# Pre-registration — Lane 1, the CLV signal test

**Written 2026-08-09, before any live data was read.** Nobody has seen the
answer. That is the point: everything below is fixed now so that the choice of
question cannot be made after the number exists.

**Status: registered. UNDERPOWERED at the sample size that exists today.**
See the power check. The registered action is to **wait**, not to run.

- Owner: pre-registrar (agent), on behalf of Joe.
- Scored against by: `measurement-skeptic`, after the run.
- Negative-result destination: fixed in §8. It exists before the result does.

---

## Warning to whoever runs this

**`data/demo.db` is 100% synthetic and no number from it is evidence about
anything.** Verified 2026-08-09: `event_links`, `fair_prices` and
`kalshi_quotes` all hold **zero** rows against 409 recommendations; every scored
row has `closing_line_id = NULL`; `strategy_configs` holds one row whose
rationale reads "seeded demo configuration"; and its 400 `orders` / 400
`settlements` are seeder output, not fills. It is a fixture for checking that
SQL parses and that a harness runs. If a figure from `demo.db` reaches a
write-up, the write-up is void.

The predecessor project produced a **20-point "finding", significant at two
standard errors, from data generated with no edge whatsoever**
(`tasks/lessons.md`, 2026-08-07). That data was synthetic too.

---

## Corrections to the brief, made before the design was fixed

Three things in the task as handed over are wrong or incomplete. They are
recorded here rather than quietly fixed, because the brief will be read again.

### C1. ADR 0005 is cited backwards

The brief says to run on all rows including suppressed ones, "see ADR 0005,
which decided suppressed rows are the likeliest carriers of a systematic CLV, so
pooling moves the mean rather than diluting it."

ADR 0005 says that sentence and draws the **opposite** conclusion from it. It is
the stated reason the gate **excludes** suppressed rows:

> Dilution toward zero would be merely conservative. The danger is different: a
> **systematic** CLV among refused rows moves the pooled mean rather than
> blunting it. […] Pooled, that population could arm real money on evidence
> about bets the strategy declines to make.

That argument is correct and it binds a **level** test — "is mean CLV above
zero on the bets we would place". It does **not** bind a **slope** test — "does
a larger claimed edge go with a larger CLV" — because a slope is estimated
*within* the pooled sample and a population-specific mean offset does not enter
it. So suppressed rows may be pooled here, but for a different reason than the
brief gives, and only for a different statistic than the gate's. §2 fixes which
suppression reasons are admissible and which are not; two of the six are
excluded, and the brief's blanket "all rows" is refused.

### C2. The half-spread confound is not mentioned, and it dominates the design

This is the largest finding in this document and it was not in the brief.

`clv_tenths` and `edge_tenths` are both computed against the **same**
`entry_ask_tenths`, and the ask is the mid plus half the Kalshi bid-ask spread:

```
CLV  = close_mid - ask   = (close_mid - entry_mid) - half_spread
edge = fair - ask - fee  = (fair - entry_mid)      - half_spread - fee
```

The term `-half_spread` appears in both. Therefore

```
Cov(edge, CLV)  contains  +Var(half_spread)
```

**A strictly positive slope arises from shared spread variation with exactly
zero predictive power.** The spurious slope is approximately
`Var(half_spread) / Var(edge_tenths)`. On Kalshi sports markets a plausible
half-spread SD of 4 tenths against an `edge_tenths` SD of 10 tenths gives a
spurious `beta` of about **0.16** — from mechanics alone, before any signal.
That is a third of the smallest effect this test could resolve even at the
gate's floor (§ power check), so it is not a rounding detail.

This is the family the repo already has two lessons about: a statistic that is
the right order of magnitude, moves correctly with `n`, and announces nothing
about being wrong (`the-null-for-one-proportion-is-not-the-null-for-a-difference`,
`a-sign-convention-agreed-with-its-own-test`).

**Consequence, and it is a hard gate on the analysis:** the entry half-spread
must be measured and controlled, or the primary statistic is uninterpretable.
It is recoverable — `kalshi_quotes` stores `yes_bid_tenths` and `no_bid_tenths`,
and `core.prices.complement` gives `yes_ask = 1000 - no_bid`, so
`half_spread = ((1000 - no_bid) - yes_bid) / 2`. §P1 makes it a prerequisite.

### C3. Bucketing on `entry_ask_tenths` does not do what the brief expects

The brief asks for bucketing on `entry_ask_tenths`, per the repo rule "bucket by
the price you would actually pay". That rule is right and is kept. But it must
be said plainly that bucketing on the ask does **not** control C2: within any
price bucket the half-spread still varies, and it is the variation, not the
level, that manufactures the slope. Price buckets are retained as a **required
reporting view** (§4), not as a control and not as a source of findings.

---

## Prerequisites — checked before the analysis is permitted to run

Each is a yes/no answered from the live database. If any is NO, the analysis
does not run and this document is amended rather than worked around.

- **P1. `kalshi_quotes` carries a readable pre-entry quote for the scored rows.**
  Required for C2. Report the fraction of scored rows for which the join in §S1
  returns non-NULL `half_spread_tenths`. **If that fraction is below 0.90, the
  primary analysis does not run.** A missing quote resolves to `None` and the
  row is refused, never imputed (`unreadable-must-never-resolve-to-zero`).
  *Known today: `demo.db` has zero `kalshi_quotes` rows. The live count has not
  been checked by anyone.*
- **P2. At least one row exists with `clv_horizon_hours = 0.0`.** Nobody has
  confirmed a non-zero scored count on live at the post-ADR-0011 horizon. Live
  most recently reported `actionable=0 of 300`, and prior scoring passes recorded
  "249 joined, 249 skipped, 0 scored". Those bugs are fixed in source and
  **unconfirmed in production**.
- **P3. `edge_tenths` has non-degenerate spread within the analysis
  population.** Report `sd(edge_tenths)`. If it is below 3 tenths the regressor
  cannot support a slope at any `n` and the test is void.
- **P4. `strategy_config_version` takes exactly one value.** More than one means
  the record is a mixture of strategies. Report the count; if it exceeds one,
  the primary analysis runs on the modal version only and the others are
  reported separately.

---

## 1. The question, as a claim that could be false

**Primary hypothesis, one-sided:**

> Among scored recommendations at the 0.0-hour horizon, the game-clustered
> partial slope of `clv_tenths` on `edge_tenths`, controlling for the entry
> half-spread, is **greater than zero**.

Written as a model:

```
clv_tenths_i = alpha + beta * edge_tenths_i + gamma * half_spread_tenths_i + e_i
```

`beta` is the estimand. It is dimensionless: **tenths of realised closing-line
value per tenth of claimed edge.**

- `beta = 0` — the engine's edge number carries no information about where the
  market goes. The strategy has no predictive power.
- `beta = 1` — full pass-through. Every tenth the engine claims is realised
  against Kalshi's close.
- `beta > 1` — the engine systematically *understates* its own edge. Treated as
  implausible; if observed it is a bug report, not a finding (rule 1: a large
  apparent edge is a bug until proven otherwise).

**The direction is one-sided and is fixed here.** The boundary in §6 is the
two-sided Robbins bound, used one-sided; that is conservative and is stated
rather than corrected, because tightening it after the fact is precisely the
freedom this document removes.

**`gamma` is a nuisance parameter and is not a finding.** No claim of any kind
will be made about it. It is in the model to absorb C2, not to be interpreted.

**What this hypothesis is not.** It is not "mean CLV > 0". That is the gate's
condition, it has a different null (§5), and it is registered here as a
**secondary, non-decision-bearing** quantity only.

## 2. The population, and the exclusions

**Included:** every row of `recommendations` with

- `clv_scored_ms IS NOT NULL` and `clv_tenths IS NOT NULL`, and
- `clv_horizon_hours = 0.0`, and
- `suppressed_reason` either NULL or **not** in (`stale_odds`,
  `stale_kalshi_quote`), and
- a non-NULL `half_spread_tenths` from the §S1 join.

**Excluded, with the reason each exclusion is independent of the outcome:**

| Excluded | Why | Independent of `clv_tenths`? |
|---|---|---|
| `clv_horizon_hours = 1.0` | Different anchor. See §3 and ADR 0011. | Yes — set by a code constant at scoring time. |
| `suppressed_reason = 'stale_odds'` | The consensus behind `edge_tenths` had aged past 900s, so part of the "edge" is drift that has already happened. Contaminates the **regressor**. | Yes — a function of input timestamps only. |
| `suppressed_reason = 'stale_kalshi_quote'` | The ask behind **both** `edge_tenths` and `clv_tenths` is older than 30s, so both variables are measured against a price that had moved. | Yes — a function of input timestamps only. |
| `half_spread_tenths IS NULL` | The C2 control cannot be computed. Refuse rather than impute. | Yes — a property of quote coverage. |

**Retained deliberately**, against the brief's instinct and against the gate's
own rule:

| Retained | Why |
|---|---|
| `insufficient_depth` | Depth governs whether an order *fills*. It does not move the mid, and CLV is measured against a mid. Not outcome-adjacent. |
| `wide_market` | Book disagreement affects the `fair` estimate, which is the regressor's *content*, not a contaminant of it. Excluding it would remove exactly the rows where the edge estimate is least reliable — which is a hypothesis about the answer, not an exclusion rule. |
| `suspicious_edge` | This rule is a pure function of `edge_tenths` (`edge_ceiling_tenths = 40.0`). Excluding it **truncates the regressor from above**, shrinking `sd(edge_tenths)` and destroying the power the slope depends on. Keeping it is the only defensible choice for a slope test. |
| `no_edge` rows (`reference_contracts = 0`, not suppressed) | These are the low end of the regressor's range. A slope needs both ends. |

**No exclusion in this document references `clv_tenths`, `settled_win`, or any
outcome.** Every one is decidable from the row's inputs before the game is
played. That is the test an exclusion rule has to pass.

**A rule that must not be activated after the fact.** If the sample turns out
thin, the temptation will be to relax an exclusion to recover `n`. That is
forbidden. The precedent is in this repo: a combo experiment pre-registered an
exclusion and the agent correctly **refused to activate it** when the sample
came in thin. Refusing was only possible because the rule was in writing first.

## 3. The unit of observation

**The unit is the game. The clustering variable is
`COALESCE(kalshi_markets.event_ticker, recommendations.ticker)`.**

Not the row, and not the market ticker. A game's moneyline, spread and total all
resolve from one final score and their prices move together, so counting them as
three observations repeats the row-counting error one level up. This is settled
in `gate._cluster_robust_stderr` and in `tasks/lessons.md`
("one observation recorded thirty times is one observation"), where counting rows
shrank the standard error by `sqrt(30)` for evidence that never grew.

**Two rows are independent only if they come from different `event_ticker`s.**

- Rows with `event_ticker IS NULL` fall back to their own ticker. That collapses
  repeated polls of one market but **cannot see correlation with its siblings**,
  so it understates the standard error for those rows. The count of such rows is
  reported beside every figure, as `gate.clustered_clv` already does. It is an
  approximation, and an unreported approximation is indistinguishable from a
  correct number.
- **Report `n_rows` and `n_clusters` side by side, always, everywhere.** "412 of
  300" on one screen and "9 of 300" on another is how the flattering number gets
  believed.

**Standard errors are cluster-robust**, the same sandwich estimator the gate
uses, extended to a regression coefficient:

```
Var(beta_hat) = (X'X)^-1 [ G/(G-1) * sum_c (X_c' e_c)(X_c' e_c)' ] (X'X)^-1
```

with `G` clusters. Two properties are asserted as tests before any result is
believed, chosen so a wrong implementation gives a *different* answer:

- **Singleton clusters must reproduce the classical OLS standard error
  exactly.** With `G == N` the expression collapses. This catches a dropped
  `G/(G-1)`.
- **Duplicating every observation `k` times must leave `beta_hat` and its
  standard error bit-identical.** The naive estimator returns `stderr/sqrt(k)`
  on that input, so this states the old bug as an invariant.

**Fewer than 2 clusters returns `None`, never a number.**

## 4. The cut — bucket edges, fixed in advance

Two grids, both fixed here, with different standing.

**Grid A — the fee-homogeneous cut. Three buckets on `entry_ask_tenths`:**

```
[10, 200)    [200, 800)    [800, 990)
```

These edges are **derived from the fee model, not chosen from the data.**
Measured from `core.fees.calculate_fee` at one contract (which is the size every
stored `edge_tenths` is computed at — see §F2), the taker fee per contract is:

```
   ask:   10c    20c    30c    40c    50c    60c    70c    80c    90c
  fee:  1.000  2.000  2.000  2.000  2.000  2.000  2.000  2.000  1.000   (cents)
```

Flat at 2.000c across `[200, 800)` and 1.000c outside it. So Grid A is the
coarsest partition on which the fee — the largest single term in `edge_tenths` —
is constant. Three buckets, three tests, and the multiplicity is counted in §6.

**Grid B — `analysis.validate.BUCKETS`, verbatim, ten 10c buckets from 10 to
990.** Reused rather than restated, so it cannot be re-chosen. **Grid B is
descriptive only and cannot produce a finding**, at any `n`. It exists because
the repo's rule is that a pooled number is not a finding until the parts agree,
and because ten cells at two standard errors produce roughly 0.46 false
positives by chance — which is how this project already got a 20-point
"finding" out of noise.

**Bucketing is on `entry_ask_tenths` — the derived ask, the price actually
paid — never a mid.** A bucket in the predecessor project showed a +25.4 point
edge and lost $4.92 a market for exactly this reason.

**No other cut may be introduced after the data is read.** In particular: not by
league, not by side, not by day, not by `suppressed_reason`, not by time to
kickoff. Each of those is defensible and that is the problem.

## 5. The statistic, named as an estimator

Said out loud, because each of these has a different null and they are not
interchangeable:

| Quantity | Estimator | Null | Standing |
|---|---|---|---|
| `beta` | **a partial regression slope over game-clustered observations** | `beta = 0` | **PRIMARY. The only decision-bearing statistic.** |
| `gamma` | a partial regression slope | none stated | Nuisance. Never interpreted. |
| mean `clv_tenths` | a mean of game-clustered observations | **not zero — see below** | Secondary, descriptive. |
| beat-close rate | a proportion | 0.5 | Descriptive only. |

**The null for the level is not zero, and this must be stated in the write-up.**
`clv_tenths = close_mid - entry_ask`, and the entry ask exceeds the entry mid by
the half-spread. So under zero predictive power and zero drift,

```
E[clv_tenths] = -half_spread  ~=  -5 to -15 tenths
```

not 0. A strategy with genuine predictive power can therefore show **negative**
mean CLV purely because it crossed a spread. Reporting "mean CLV is negative,
therefore no edge" would be wrong, and reporting "mean CLV is positive,
therefore edge" would be understating a genuinely stronger result. The level
test answers the economically correct question — *does the edge survive the
spread we cross* — and that is a different question from *is there a signal*.
**This test asks the second one.** `sqrt(p(1-p)/n)` is the default that comes to
mind for none of these and is correct for none of them.

## 6. The decision rule, with the multiplicity already counted

**Tests that can produce a finding: exactly one — `beta`, pooled, at horizon
0.0, on the §2 population.** Everything else in this document is descriptive
and **cannot upgrade the verdict**, including every bucket in Grid A and Grid B,
the level test, the per-population breakdown, and the horizon-1.0 comparison.
This is stated now because the failure it prevents is
`computing-the-right-statistic-and-then-ignoring-it`: a correct primary result
sitting beside a contradicting bucket verdict, where the verdict is what gets
read.

**The record is looked at repeatedly as it grows, so the boundary is
always-valid, not fixed-sample.** A two-standard-error rule re-evaluated against
an accumulating database is not one look; measured on 1,200 pure-noise sequences
in this repo it fires **13.7%** of the time within 100 looks, and 13.7% is a
floor because the simulation stops and the record does not. The boundary is
`gate.always_valid_multiplier(G, tuning=300, alpha=0.05)` — the Robbins normal
mixture already implemented here, tuned to the same 300 the gate uses. Its
multiplier never approaches 2 at any `n`, which is the property that matters.
The cost is real and stated: 3.66 standard errors at `G = 300` rather than 2,
about 1.8x the effect size.

### The decision rule, verbatim

> **SIGNAL.** Declared if and only if, at a look taken when `G >= 300`,
> `beta_hat > always_valid_multiplier(G, tuning=300, alpha=0.05) * se_cluster(beta_hat)`
> **and** `beta_hat <= 1.0`.
>
> **BUG, NOT SIGNAL.** Declared if the boundary is cleared and
> `beta_hat > 1.0`. The engine cannot understate its own edge; this is a defect
> report and no edge is claimed.
>
> **NO SIGNAL.** Declared if and only if, at a look taken when `G >= 300`, the
> boundary is not cleared **and** the upper limit of the always-valid interval,
> `beta_hat + always_valid_multiplier(G, tuning=300, alpha=0.05) * se_cluster(beta_hat)`,
> is **below 0.40**.
>
> **UNRESOLVED.** Declared in every other case, including every look taken when
> `G < 300`. "Unresolved" is a real answer and is not "no signal".
>
> A look taken when `G < 300` may report point estimates and intervals. **It may
> not declare SIGNAL, BUG or NO SIGNAL.** The 300 floor is not a significance
> threshold — the boundary handles that — it is the point below which the test
> cannot resolve any plausible value of `beta` (power check, below).
>
> `beta_hat` is the pooled, game-clustered, half-spread-controlled slope on the
> §2 population at `clv_horizon_hours = 0.0`. No bucket result, no subgroup, no
> alternative horizon and no alternative population may substitute for it.

**0.40 is fixed now and here is why.** At the gate's floor of `G = 300` the
smallest resolvable `beta` is about 0.42 under the central noise assumption
(power check). A negative verdict that could not have detected a real effect is
not a negative result, so NO SIGNAL requires ruling out the smallest effect this
design can see. 0.40 also has an independent reading: it is roughly the
pass-through at which a typical 20-tenth claimed edge yields 8 tenths of CLV,
against the 3.8 tenths of total fee headroom the venue offers. Below 0.40 there
is nothing to trade even if the slope is real.

**Multiplicity arithmetic, computed now.** Grid A is 3 tests and Grid B is 10.
At the conventional per-test alpha of 0.0455 that is `13 * 0.0455 = 0.59`
expected false findings, and at least one cell clears by chance about **45%** of
the time from nothing. This is the arithmetic that produced "dozens of
significant results" from 1,190 cells in the predecessor project. It is why the
buckets are descriptive: **a bucket that clears the boundary while `beta` does
not is the one that got lucky, and the write-up must say so in those words.**
Report `Summary.family_wise_p` and `family_wise_verdict` beside the grids, both
already implemented in `analysis/validate.py`.

## 7. The stopping rule

Data collection ends at whichever of these comes **first**:

1. `G = 1000` independent games scored at horizon 0.0 in the §2 population; or
2. **2027-02-15**, after the NFL and NBA seasons overlap — a calendar date, not
   a state of the data; or
3. the decision rule in §6 returns SIGNAL, BUG or NO SIGNAL at a look with
   `G >= 300`.

**Interim looks are permitted without penalty and without limit**, which is the
entire purpose of the always-valid boundary — that is what it is bought with the
1.8x effect-size cost. There is no alpha to spend.

**What is forbidden** is changing anything in §§1–6 after a look. If the design
must change — and P1–P4 may force it — the amendment is written into this file
with its date and reason **before** the next look, the pre-amendment result is
reported alongside, and `G` for the decision rule restarts if the population
definition moved. An amendment made after a look and not recorded voids the
registration.

**A config bump is a new sequence.** If `strategy_config_version` changes
mid-record, the boundary's i.i.d. assumption breaks —
`always_valid_multiplier` documents this and does not correct for it. Report the
version distribution at every look. A change of more than one version means the
primary runs on the modal version and `G` counts only those games.

## 8. What would falsify this, and what happens then

**Falsified by:** `beta_hat` at or below zero, or an always-valid upper limit
below 0.40, at `G >= 300`.

**The negative result's destination, fixed now, before the result exists:**

```
docs/measurements/2027-XX-XX-clv-signal-test-result.md
```

One file, written whichever way it comes out, with the same filename stem, the
same sections, and this document linked from its first line. Registering the
destination in advance is what stops a negative result from quietly never being
written — and a negative result here is the more likely outcome and the more
valuable one, because it is cheap and nobody else in this project's history has
produced one on this question.

**Consequences, stated in both directions so the measurement is
decision-relevant:**

| Verdict | What is built | What is killed |
|---|---|---|
| **SIGNAL** | Proceed to the gate's own level test on the `actionable` population (a *different* statistic — §5). Open ADR 0017's maker path, where the 50.44% break-even needs less signal than 52.00%. Persist real orders so `fee_predicted == fee_actual` can be checked. | Nothing. |
| **NO SIGNAL** | Nothing new. The tool remains a measurement instrument and a portfolio piece, which is a legitimate outcome. | **The taker strategy as specified.** Stop work on arming live money via this route. Stop the backfill lane. `LIVE_TRADING_ENABLED` stays off, permanently, unless a *different* strategy is registered and measured. |
| **BUG** | A defect investigation into `edge_after_fees_tenths` and the devig path. | No edge is claimed. |
| **UNRESOLVED at the stopping rule** | Nothing. Report the interval and the `G` reached. | The *timeline*, not the hypothesis: if 18 months of recording cannot reach `G = 300`, the recording rate is the binding constraint and that is the thing to fix or abandon. |

**This is decision-relevant.** The NO SIGNAL branch kills a line of work rather
than continuing it, which is the test of whether a measurement was worth
running.

## 9. What this cannot establish — drafted before the run

Caveats written afterwards are selected to be survivable. These are written now.

- **It does not establish that `fair_probability` is calibrated against
  reality.** That is a separate question and is **currently unrunnable**:
  `kalshi_markets.result` is never written by any live code path, and
  `analysis` reads settlements `FROM orders`, of which there are zero real ones.
  No statement about win rates, calibration, or accuracy may be made from this
  measurement.
- **CLV is not profit.** It can be positive while the account shrinks. It is the
  fastest honest proxy, not the thing itself.
- **It does not establish that any bet clears the fee.** `beta > 0` says the edge
  estimate *ranks* games. Whether the level clears 52.00% is §5's other
  statistic, with a different null and a spread offset in it.
- **The close is a mid; the entry is an ask.** The level is contaminated by the
  half-spread by construction, and the slope is decontaminated only to the extent
  `half_spread_tenths` is correctly measured on enough rows (P1). If P1 lands
  between 0.90 and 1.00, the residual contamination is proportional to the
  missing fraction and must be stated as a number.
- **Candlestick closes are unsized.** A price nobody could have transacted counts
  the same as one that could.
- **The scored sample skews early, by construction.** Rows created inside the
  final 15 minutes go unscored at this horizon (ADR 0011, decision 1). Time to
  kickoff correlates with how much the market has already moved, so the scored
  set is a **non-random subset** of recommendations — and the direction of that
  bias is not known and is not estimated here.
- **Only markets with a readable candlestick within 15 minutes of kickoff are
  scored.** That is a liquidity-flavoured sample. Markets that never developed a
  quote are absent, and their absence is not random.
- **One horizon is one snapshot.** The horizon-1.0 rows are the control (§F3),
  and they are a *weak* control: they are a different, earlier, pre-ADR-0011
  population, not a re-scoring of the same rows.
- **It is one season and the leagues that were in it.** The recording window
  opens on an August 2026 slate — MLB, WNBA, NFL preseason. It says nothing about
  NBA, NCAAF, or NFL regular season, and nothing about in-play (ADR 0006).
- **It says nothing about combos.** `KXMVE` is a separate product on a separate
  path (ADR 0012).
- **`edge_tenths` is measured at one contract, not at the size that defines
  `actionable`.** See §F2. The regressor is therefore a *more conservative* edge
  than the one the record's population predicate is built on, by up to 5 tenths.
- **The boundary assumes clustered observations are independent across games and
  identically distributed.** Same-day games sharing a weather event, a referee
  assignment, or a market-wide liquidity shock violate that, and nothing here
  corrects for it.

---

## The power check — this is the deliverable, not a preliminary

**Can this measurement answer this question at the `n` available?**

Not at any `n` plausibly available today. Here is the arithmetic.

### Setup

For the slope, `se(beta) ~= sigma_eps / (sigma_x * sqrt(G))`, where `sigma_eps`
is the residual SD of `clv_tenths`, `sigma_x` is the SD of `edge_tenths`, and
`G` is **independent games** — not rows. Rows within a game are scored against
one closing line, so the design effect is close to the row count and `G` is the
honest denominator.

Central assumptions, stated so they can be checked against the record when it
exists: `sigma_eps = 20` tenths (2c of pre-game price movement in the final
45 minutes) and `sigma_x = 10` tenths (`edge_tenths` truncated above at 40 by
`edge_ceiling_tenths`, with mass at the low end). Both are estimates and both are
reported as measured quantities in the write-up.

### Smallest resolvable `beta`, against the always-valid boundary

Recall `beta = 1` is full pass-through and is the **ceiling** of plausibility.

| `G` (games) | multiplier | `sigma_eps/sigma_x = 1` | **= 2 (central)** | `= 3` |
|---:|---:|---:|---:|---:|
| 20 | 9.84 | 2.20 | **4.40** | 6.60 |
| 40 | 7.21 | 1.14 | **2.28** | 3.42 |
| 60 | 6.09 | 0.79 | **1.57** | 2.36 |
| 100 | 5.01 | 0.50 | **1.00** | 1.50 |
| 200 | 4.03 | 0.29 | **0.57** | 0.86 |
| **300** | **3.66** | **0.21** | **0.42** | **0.63** |
| 500 | 3.34 | 0.15 | **0.30** | 0.45 |
| 1000 | 3.11 | 0.10 | **0.20** | 0.30 |

**Read the central column against the ceiling of 1.0:**

- **At `G = 40` — the sample size the brief warns may be all that exists — the
  smallest resolvable `beta` is 2.28. That is more than twice the largest value
  `beta` can plausibly take.** The test cannot resolve *any* real effect. It can
  only return a number, and the number will get quoted.
- At `G = 100` the smallest resolvable `beta` is 1.00 — exactly the ceiling. The
  test can detect only a perfect, lossless pass-through and nothing less.
- At `G = 300` it is 0.42: the test can distinguish "at least ~40% of the claimed
  edge is real" from zero. That is a decision-relevant threshold, and it is where
  §6's 0.40 comes from.
- At `G = 1000` it is 0.20.

**The gate's 300-game floor and the smallest `n` at which this test can resolve a
plausible effect are the same number.** That was not arranged; the floor came
from practitioner consensus on CLV and the 0.42 came from the noise arithmetic.
They agree, which is a mild independent check on both.

### The same arithmetic for the level test, against the real headroom

The venue lowers the break-even bar from 52.38% to 52.00% — **0.38 points, or
3.8 tenths of a cent.** A design that can only resolve effects larger than a
point is not measuring the thing this project exists to measure.

Smallest resolvable mean CLV, in tenths:

| `G` | 20 | 40 | 100 | 300 | 1000 |
|---|---:|---:|---:|---:|---:|
| `sigma = 20t` | 44.0 | 22.8 | 10.0 | **4.2** | 2.0 |

And the `G` required to resolve 3.8 tenths:

| `sigma` | 10t | 20t | 30t | 40t |
|---|---:|---:|---:|---:|
| `G` needed | 142 | **350** | 656 | 1070 |

At the central `sigma = 20` tenths, **`G = 350`** is needed to resolve an effect
the size of the entire fee advantage. The gate asks for 300. So the gate is
calibrated to about the right order and is, if anything, slightly optimistic —
and if per-game CLV noise turns out to be 3c rather than 2c, the honest floor is
**656 games**, more than double what the gate requires. `sigma` is therefore a
**reportable quantity at every interim look**, and if it comes in above 30 tenths
this document must be amended to raise the floor.

### Verdict of the power check

**UNDERPOWERED at the sample size that exists today, and the correct action is
to wait rather than to run.**

If the live record holds ~40 games, this test can answer exactly one question —
"is `beta` above 2.3?" — whose answer is no under every hypothesis anyone holds,
including the one where the strategy works perfectly. Running it early would:

1. burn a look on a question that cannot come back informative;
2. produce a point estimate and a wide interval that will be quoted as if it
   were a result, which is the specific harm this project has already suffered
   from a 20-point figure generated out of noise; and
3. create pressure to relax an exclusion or add a cut to "get `n` up", which is
   how the analysis gets chosen after the fact.

**The registered action is: keep recording, take interim looks freely (the
boundary permits it at zero cost), report `G`, `sigma_eps`, `sigma_x` and the
half-spread coverage at each, and declare nothing until `G >= 300`.**

A measurement that cannot resolve the question is worse than none, because it
returns a number anyway and the number gets quoted.

---

## Facts verified against source, not taken on trust

### F1. `edge_tenths` is NET of fees. The schema comment is wrong.

`backend/store/schema.sql:330` reads `edge_tenths REAL NOT NULL, -- gross,
before fees`. `backend/engine.py:161` assigns
`edge_after_fees_tenths(...)`, which is `(fair - effective_price) * PRICE_MAX`
and `effective_price` amortises the fee in. **Verified. The comment is wrong and
the code is right; this analysis is designed against the code.** A parallel lane
is correcting the comment. If that correction has landed by the time this runs,
nothing here changes.

### F2. `edge_tenths` is computed at **one contract** for effectively the whole live record.

`engine.py` uses `sizing_contracts = max(1, sizing.contracts)`, where `sizing` is
at the **operator's** bankroll. Measured against the live `fly.live.toml` profile
(`BANKROLL_DOLLARS = 100`, `KELLY_FRACTION = 0.25`, `MAX_POSITION_DOLLARS = 10`):

```
 ask    edge   contracts@$100   contracts@$1000(reference)
 50c    0.5c        0                    0
 50c    1.0c        0                    0
 50c    2.0c        0                    0
 50c    4.0c        2                   20
```

`sizing.contracts` is **0** at every edge below ~4c across the whole 20c–80c
band. And 4c is `edge_ceiling_tenths = 40.0`, at which `suspicious_edge`
suppresses the row. So on the live profile `max(1, 0) = 1` for essentially every
row in the record.

**Three consequences for this design, and the first is the significant one:**

1. **It is uniform, which is good.** Every row's `edge_tenths` is computed on the
   same n=1 fee basis, so the regressor is internally comparable and no
   edge-correlated fee step contaminates the slope. Had the bankroll been large
   enough for `contracts` to vary, a bigger edge would have bought a bigger order
   and therefore a *smaller* per-contract fee and therefore an even bigger stored
   edge — a positive feedback manufacturing slope out of nothing. **At $100 that
   hazard is absent. At $1,000 it would be present.**
2. **The n=1 penalty is larger than the headroom being hunted.** Measured from
   `core.fees.calculate_fee`, the per-contract taker fee at 30c is **2.000c at
   one contract against 1.500c at ten** — a 0.5-point difference, where the
   entire venue advantage is 0.38 points. The same gap appears at 20c, 70c and
   80c, and is exactly zero at 50c and at the extremes. So the stored
   `edge_tenths` is systematically more conservative than the edge at the size an
   order would actually be sent at, by an amount that **varies with price** and
   is **zero at 50c**. Grid A's `[200, 800)` bucket is the fee-flat region at
   n=1; at n>=2 it is not flat, which is another reason Grid A's edges must not
   be re-derived later.
3. **`edge_tenths` and the `actionable` predicate are on different bases.**
   `reference_contracts` is sized at the $1,000 reference (20–33 contracts, per
   ADR 0015) while `edge_tenths` is at one. That is a stated inconsistency in the
   record, not something this analysis can fix, and it is why the primary
   population here is **not** restricted to `actionable`.
4. **A change to `BANKROLL_DOLLARS` silently changes the regressor's basis
   mid-record**, exactly as ADR 0011's horizon change did to `clv_tenths` — and
   unlike the horizon, **nothing records which basis a row used.** Report the
   value of `BANKROLL_DOLLARS` at every interim look. If it changes during
   collection, that is an amendment under §7.

### F3. ADR 0011 left two horizons in the record. This analysis is horizon-0.0 only.

Confirmed. `DEFAULT_HORIZON_HOURS = 0.0`, `CONTROL_HORIZON_HOURS = 1.0`, and
ADR 0011 decision 4 (amended by Joe) deliberately **kept** the ~34 rows scored at
1.0 rather than clearing them. `score_recommendations` only fills rows where
`clv_scored_ms IS NULL`, so those rows will never be re-scored and are permanent
1.0h observations.

**Fixed in advance, as required:**

- **The primary analysis is `clv_horizon_hours = 0.0` only.** A pooled mean
  across both is a mixture of two regimes measured against two different
  anchors, and the 1.0h anchor is the *more generous* one — a market sharpens as
  the event approaches, so beating a price an hour out is an easier claim.
  Pooling would flatter.
- **The 1.0h rows are used for exactly one thing: a reported, non-decision-bearing
  convergence check**, via `clv.horizons_agree`. If the sign or rough magnitude
  of the effect differs between anchors, that is evidence of convergence rather
  than edge and **must be reported prominently in the write-up regardless of
  which way the primary came out.**
- **The 1.0h rows may not be counted toward `G`, may not be pooled into `beta`,
  and may not be used to rescue an underpowered primary.** They are record, not
  evidence — ADR 0011's own words.
- The check is weak and the write-up must say so: the two horizons are
  different *populations of rows*, not the same rows re-scored, so a difference
  between them is confounded with whatever changed between the two eras.

### F4. The record may be small or empty. Nobody has confirmed otherwise.

Confirmed as an open question, not resolved here. Live most recently reported
`actionable=0 of 300`; prior live scoring passes recorded "249 joined, 249
skipped, 0 scored" (ADR 0011). Those bugs are fixed **in source** and no live
run has been confirmed to produce a non-zero scored count at horizon 0.0.
**`G` is unknown and this document assumes nothing about it.** P2 is the check.

---

## S1. The extraction query, fixed in advance

Verified to parse and execute (against `demo.db`, for syntax only — no value
from that run is recorded anywhere, and `half_spread_tenths` came back NULL for
every row there because `demo.db` has zero `kalshi_quotes`, which is exactly the
condition P1 exists to catch).

```sql
SELECT
  COALESCE(m.event_ticker, r.ticker)              AS cluster_key,
  r.id, r.ticker, r.side,
  r.entry_ask_tenths, r.edge_tenths, r.clv_tenths,
  r.suppressed_reason, r.reference_contracts, r.strategy_config_version,
  q.yes_bid_tenths, q.no_bid_tenths,
  -- yes_ask = 1000 - no_bid  (core.prices.complement). The mid is NEVER an
  -- entry price; it is used here only to recover the half-spread that
  -- contaminates edge and CLV identically. See correction C2.
  ((1000 - q.no_bid_tenths) - q.yes_bid_tenths) / 2.0 AS half_spread_tenths,
  (m.event_ticker IS NULL)                        AS unclustered
FROM recommendations r
LEFT JOIN kalshi_markets m ON m.ticker = r.ticker
LEFT JOIN kalshi_quotes  q ON q.id = (
    SELECT q2.id FROM kalshi_quotes q2
    WHERE q2.ticker = r.ticker
      AND q2.observed_ms <= r.created_ms
      AND q2.yes_bid_tenths IS NOT NULL
      AND q2.no_bid_tenths  IS NOT NULL
    ORDER BY q2.observed_ms DESC
    LIMIT 1)
WHERE r.clv_scored_ms IS NOT NULL
  AND r.clv_tenths     IS NOT NULL
  AND r.clv_horizon_hours = 0.0
  AND (r.suppressed_reason IS NULL
       OR r.suppressed_reason NOT IN ('stale_odds', 'stale_kalshi_quote'));
```

Rows with `half_spread_tenths IS NULL` are **dropped and counted**, never
imputed. The dropped count is P1's numerator and is reported at every look.

### Required output of every run, in this order

Read `n` before the effect size. The harness prints, in this sequence:

1. `G` (clusters), `n_rows`, `unclustered_rows`, and the P1 coverage fraction.
2. `sigma_eps`, `sigma_x`, `sd(half_spread_tenths)`, and the implied spurious
   slope `Var(half_spread)/Var(edge)` — so the C2 contamination is a printed
   number, not an argument.
3. `BANKROLL_DOLLARS` and the `strategy_config_version` distribution.
4. The smallest resolvable `beta` at this `G`, from the table above, **before**
   `beta_hat` is printed.
5. `beta_hat`, `se_cluster`, the always-valid multiplier, the boundary, and the
   verdict from §6 verbatim.
6. Grid A, then Grid B, each labelled **DESCRIPTIVE — CANNOT PRODUCE A
   FINDING**, with `family_wise_p` and `family_wise_verdict` above them.
7. `horizons_agree` output, labelled as the weak control it is.
8. §9, reproduced verbatim.

The harness's module docstring states what it does not establish, per the repo
rule that every harness carries its own limits.

---

## Registration record

| | |
|---|---|
| Registered | 2026-08-09 |
| Data seen at registration | **None.** Live was not queried. `demo.db` was inspected for schema and row-shape only, and is synthetic. |
| Primary estimand | `beta`, game-clustered partial slope of `clv_tenths` on `edge_tenths`, half-spread controlled |
| Direction | One-sided, positive |
| Population | §2 |
| Cluster key | `COALESCE(kalshi_markets.event_ticker, recommendations.ticker)` |
| Horizon | `clv_horizon_hours = 0.0` only |
| Bucket edges | Grid A `[10,200) [200,800) [800,990)`; Grid B = `validate.BUCKETS` verbatim. Both descriptive. |
| Boundary | `gate.always_valid_multiplier(G, tuning=300, alpha=0.05)` |
| Decision floor | `G >= 300` before any verdict |
| Stopping rule | §7 |
| Result destination | `docs/measurements/2027-XX-XX-clv-signal-test-result.md`, written either way |
| Verdict at registration | **UNDERPOWERED — wait, do not run** |
