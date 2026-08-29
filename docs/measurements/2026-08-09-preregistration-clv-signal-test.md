# Pre-registration — Lane 1, the CLV signal test

**Written 2026-08-09, before any live data was read.** Nobody has seen the
answer. That is the point: everything below is fixed now so that the choice of
question cannot be made after the number exists.

**Status: registered, amended once. UNDERPOWERED at the sample size that exists
today.** See the power check. The registered action is to **wait**, not to run.

> **AMENDMENT 1, 2026-08-09 — read it before reading anything below.**
> Seventeen registered passages are superseded, extended or completed. Each is
> marked in place with a pointer and **none has been deleted**; the amendment is
> appended at the end of this file and it, not the original text, governs.
> **No data had been observed when it was written.**
> See [Amendment 1](#amendment-1--2026-08-09).

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

> **[SUPERSEDED IN PART by Amendment 1 §A5 — text retained.]** "The largest
> finding in this document" is withdrawn: C2 is **a mechanism whose magnitude is
> unmeasured**. The `sd(half_spread) = 4` below is *assumed*, and ADR 0006
> measures the pre-game spread at 1.00c at **every percentile including the
> maximum**. The mechanism is real; the 0.16 is not a finding.

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
half-spread SD of 4 tenths **[ASSUMED — no measurement supports it; ADR 0006
contradicts it]** against an `edge_tenths` SD of 10 tenths **[ASSUMED]** gives a
spurious `beta` of about **0.16** **[ASSUMED, derived from two assumed inputs]**
— from mechanics alone, before any signal.
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
  > **[SUPERSEDED by Amendment 1 §A3 — text retained.]** "Treated as
  > implausible" is wrong. The engine understates its own edge **by
  > construction** — worst-of-four devig, and a regressor deliberately shrunk
  > (F2). `beta > 1` is a flag for investigation, not a verdict. The BUG
  > condition is now on the always-valid *lower* limit, not the point estimate.

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

> **[SUPERSEDED IN PART by Amendment 1 §A1 and §A2 — text retained.]** Two
> defects. (a) The `suppressed_reason` predicate below is written against a
> single code, but the column is a **comma-joined composite**, so
> `'stale_odds,wide_market'` was *retained* — §A1 replaces the predicate.
> (b) Four codes are adjudicated here; the code can emit **thirteen** — §A2
> adjudicates every one, including `edge_within_method_noise`, which punches a
> price-dependent hole in the interior of the regressor.

**Included:** every row of `recommendations` with

- `clv_scored_ms IS NOT NULL` and `clv_tenths IS NOT NULL`, and
- `clv_horizon_hours = 0.0`, and
- `suppressed_reason` either NULL or **not** in (`stale_odds`,
  `stale_kalshi_quote`), and — **[SUPERSEDED by Amendment 1 §A1]**: the column
  is a composite, so this must be a delimited substring test, not equality —
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

> **[INCOMPLETE — completed by Amendment 1 §A2.]** The two tables above cover
> six codes between them. `core/suppression.py` emits **eleven**, `engine.py`
> adds `sizing:refused`, and `agents/skeptic.py` appends `skeptic_defect` /
> `skeptic_suspicious`. The seven unadjudicated ones are adjudicated in §A2.

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

> **[INCOMPLETE — a third and fourth anchor are added by Amendment 1 §A7.]**
> Both anchors above are about the **standard error**. Neither pins the
> **partial-slope arithmetic**, so an estimator that accepted `half_spread` and
> never used it — which is C2's contamination left entirely in place — passes
> both.

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

> **[SUPERSEDED by Amendment 1 §A6 — text retained.]** The null is
> **approximately −5 tenths, measured** (ADR 0006: pre-game spread 1.00c at
> mean, median, p90, p99 **and maximum**, 3,483 minutes over 20 games). The
> −15 end requires a 3.00c spread, which was observed only **in-play** and never
> pre-game. `−5 to −15` was **[ASSUMED]** and its wide end is contradicted.

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

> **[EXTENDED by Amendment 1 §A4.]** Correct but one-directional. As written, a
> `beta_hat` carried entirely by `suspicious_edge` rows — selected by a
> threshold **on the regressor itself**, hence maximum leverage — is declared
> SIGNAL. §A4 adds: the per-group view **can downgrade a verdict even though it
> cannot create one**, by a pre-registered leave-one-group-out rule.

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

> **[SUPERSEDED by Amendment 1 §A3 and §A4 — text retained.]** The SIGNAL and
> BUG clauses below are replaced. They test an always-valid *interval* against
> the null of zero and a bare *point estimate* against the ceiling of one, which
> is inconsistent: at `G = 300` this document's own numbers give
> `se(beta_hat) ~= 0.115`, so a true `beta` of exactly 1.0 lands above 1.0 half
> the time and is classified BUG. The NO SIGNAL and UNRESOLVED clauses stand,
> subject to §A4's downgrade rule.

> **[SUPERSEDED by Amendment 2 section B4 — text retained.]** **Every `G >= 300`
> and `G < 300` in the clauses below is now `G >= 713` and `G < 713`**, and each
> occurrence is marked in place. The floor moved because the power check's own
> `sigma` trigger fired: `sd(clv_tenths)` came in at 31.6915 tenths on the modal
> population, against an assumed 20, and the power check's own formula and its
> own 3.8-tenth target then give 713. **The 0.40 threshold is UNCHANGED** (§B5),
> and so is `tuning=300` — it is the Robbins mixture parameter, not the floor,
> and re-tuning it would silently restate every interval this registration has
> published (§B6(4)). The floor is a **ratchet**: it does not fall if a later
> look measures a smaller `sigma`.

> **SIGNAL.** Declared if and only if, at a look taken when `G >= 300`
> **[SUPERSEDED by Amendment 2 section B4 — now `G >= 713`]**,
> `beta_hat > always_valid_multiplier(G, tuning=300, alpha=0.05) * se_cluster(beta_hat)`
> **and** `beta_hat <= 1.0`.
>
> **BUG, NOT SIGNAL.** Declared if the boundary is cleared and
> `beta_hat > 1.0`. The engine cannot understate its own edge; this is a defect
> report and no edge is claimed.
>
> **NO SIGNAL.** Declared if and only if, at a look taken when `G >= 300`
> **[SUPERSEDED by Amendment 2 section B4 — now `G >= 713`]**, the
> boundary is not cleared **and** the upper limit of the always-valid interval,
> `beta_hat + always_valid_multiplier(G, tuning=300, alpha=0.05) * se_cluster(beta_hat)`,
> is **below 0.40**.
>
> **UNRESOLVED.** Declared in every other case, including every look taken when
> `G < 300` **[SUPERSEDED by Amendment 2 section B4 — now `G < 713`]**.
> "Unresolved" is a real answer and is not "no signal".
>
> A look taken when `G < 300` **[SUPERSEDED by Amendment 2 section B4 — now
> `G < 713`]** may report point estimates and intervals. **It may
> not declare SIGNAL, BUG or NO SIGNAL.** The 300 floor **[SUPERSEDED by
> Amendment 2 section B4 — now the 713 floor]** is not a significance
> threshold — the boundary handles that — it is the point below which the test
> cannot resolve any plausible value of `beta` (power check, below). **§B6(2):
> that sentence is unchanged in meaning. It moved because the noise came in
> larger than assumed, which is the one input it is a function of.**
>
> `beta_hat` is the pooled, game-clustered, half-spread-controlled slope on the
> §2 population at `clv_horizon_hours = 0.0`. No bucket result, no subgroup, no
> alternative horizon and no alternative population may substitute for it.

**0.40 is fixed now and here is why.** At the gate's floor of `G = 300` the
smallest resolvable `beta` is about 0.42 under the central noise assumption
**[ASSUMED — see §A5 on the word "central"]** (power check). A negative verdict
that could not have detected a real effect is not a negative result, so NO
SIGNAL requires ruling out the smallest effect this design can see. 0.40 also
has an independent reading: it is roughly the pass-through at which a typical
20-tenth claimed edge **[ASSUMED]** yields 8 tenths of CLV, against the 3.8
tenths of total fee headroom the venue offers **[COMPUTED FROM CODE —
`core/fees.py` via CLAUDE.md's 52.00% bar]**. Below 0.40 there is nothing to
trade even if the slope is real.

> **[SUPERSEDED IN PART by Amendment 1 §A5 — text retained. The threshold of
> 0.40 itself STANDS.]** The second derivation is **not independent**. It
> computes `0.40 x 20 = 8`, observes `8 > 3.8`, and presents that as
> confirmation; taken as a derivation it gives `3.8 / 20 = 0.19`, not 0.40. It
> establishes only that 0.40 clears the economic minimum. The first derivation
> inherits `sigma_eps / sigma_x = 2` entirely. §A5 supplies the defence that is
> actually load-bearing and was missing.

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
   `G >= 300` **[SUPERSEDED by Amendment 2 section B4 — now `G >= 713`]**.

> **[SUPERSEDED by Amendment 2 section B4 — text retained.]** Condition 3's
> floor is **713**, on the modal-`strategy_config_version` population §P4 and §7
> make the primary. Conditions 1 (`G = 1000`) and 2 (**2027-02-15**) are
> **unchanged**, and 713 is still below 1000, so the stopping rule stays
> internally consistent (§B6(3)). §B7 measures 713 against the 2027-02-15 stop
> and finds it reachable in nominal terms — but records, in the same breath,
> that nominal `G` may be the wrong unit: `G = 311` was **4.26** effective
> clusters, and no floor written in nominal `G` fixes that.

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
below 0.40, at `G >= 300`. **[SUPERSEDED by Amendment 2 §B4 — now `G >= 713`]**

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
  > **[SUPERSEDED by Amendment 1 §A8.3 — text retained.]** The proportionality
  > claim is wrong. §S1 **drops** rows with a NULL half-spread; it does not
  > impute them. Residual contamination on retained rows is therefore **zero**,
  > and what the missing fraction creates instead is a **selection** problem of
  > unknown direction. §A8 adds two further omissions.
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
exists: `sigma_eps = 20` tenths **[ASSUMED]** (2c of pre-game price movement in
the final 45 minutes) and `sigma_x = 10` tenths **[ASSUMED]** (`edge_tenths`
truncated above at 40 by `edge_ceiling_tenths` **[COMPUTED FROM CODE, but see
Amendment 1 §A5.1 — the truncation is on the *net* edge and does not bind where
this claims]**, with mass at the low end). Both are estimates and both are
reported as measured quantities in the write-up.

> **[SUPERSEDED IN PART by Amendment 1 §A5.2 — text retained. The arithmetic
> STANDS.]** The word **"central"** is withdrawn wherever it qualifies
> `sigma_eps / sigma_x = 2` in this section and in the table below. Nothing
> measures the ratio; "central" claims a location in a distribution that has not
> been observed. Read it as **ASSUMED** throughout. §A5.2 records why the
> assumption's error nonetheless runs in the safe direction.

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

> **[SUPERSEDED by Amendment 1 §A5.3 — text retained.]** Not a check of any
> kind, and it *was* arranged. The multiplier in the column above is
> `always_valid_multiplier(G, tuning=300)`: the boundary is **tuned to** the
> gate's floor. Finding agreement at `G = 300` is the tuning parameter
> reappearing in its own output. The word "independent" is withdrawn.

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
half-spread coverage at each, and declare nothing until `G >= 300`.** **[SUPERSEDED by Amendment 2 §B4 — now `G >= 713`]**

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

> **[SUPERSEDED by Amendment 1 §A5.1 — text retained.]** Two errors, and they
> compound. (a) `edge_ceiling_tenths` is a threshold on the **net** edge; the
> table above is in **gross** gap. At 50c a 4.0c gross gap stores a *net* edge
> of 2.0c, and `suspicious_edge` does not trip until a **6.0c** gross gap and
> 4 contracts. Suppression therefore does **not** close the multi-contract band.
> (b) The 4c row of the table is the point at which contracts reach **2**, not
> the point at which they are still 0. Measured across the retained band,
> `sizing.contracts` runs **1 to 8**.

**Three consequences for this design, and the first is the significant one:**

1. **It is uniform, which is good.** Every row's `edge_tenths` is computed on the
   same n=1 fee basis, so the regressor is internally comparable and no
   edge-correlated fee step contaminates the slope. Had the bankroll been large
   enough for `contracts` to vary, a bigger edge would have bought a bigger order
   and therefore a *smaller* per-contract fee and therefore an even bigger stored
   edge — a positive feedback manufacturing slope out of nothing. **At $100 that
   hazard is absent. At $1,000 it would be present.**
   > **[SUPERSEDED by Amendment 1 §A5.1 — text retained. This item is FALSE.]**
   > The basis is **not** uniform and the hazard is **present at $100**. Measured
   > by running `size_position` at the live profile, `sizing.contracts` runs
   > **1 to 8** across the retained, unsuppressed range. `edge_tenths` is
   > therefore a **discontinuous, and at two prices non-monotonic**, function of
   > the underlying gross gap, and **nothing in the schema records which basis a
   > row used**. This is the item the document marked as good news.
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

> **[SUPERSEDED by Amendment 1 §A1 — query retained.]** The final predicate is
> wrong: `suppressed_reason` is a comma-joined composite, so
> `'stale_odds,wide_market'` equals neither literal and was **retained**. The
> governing query is the one in §A1. `tests/test_preregistration_population.py`
> pins the replacement and asserts this defect directly.

Rows with `half_spread_tenths IS NULL` are **dropped and counted**, never
imputed. The dropped count is P1's numerator and is reported at every look.

> **[EXTENDED by Amendment 1 §A8.2.]** "Dropped and counted" conflates two
> populations that must be counted separately: rows with **no quote at all**,
> and rows whose joined quote **disagrees** with `entry_ask_tenths`. §S1 refuses
> only the first.

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
| Decision floor | `G >= 300` before any verdict **[SUPERSEDED by Amendment 2 §B4 — now `G >= 713`]** |
| Stopping rule | §7 |
| Result destination | `docs/measurements/2027-XX-XX-clv-signal-test-result.md`, written either way |
| Verdict at registration | **UNDERPOWERED — wait, do not run** |
| Amendments | **1**, dated 2026-08-09, below. No data observed at amendment. |

---

# Amendment 1 — 2026-08-09

**Applying the `measurement-skeptic` audit of the registration above.**

Nothing above has been deleted or rewritten. Seventeen passages carry a
`[SUPERSEDED]`, `[EXTENDED]` or `[INCOMPLETE]` marker in place, each pointing at
the section here that replaces or completes it. **Where this amendment and the
original text conflict, this amendment governs.** The original stays because
the record is the product:
a pre-registration whose text is quietly rewritten after its first audit is not
a pre-registration, and the repo already carries that rule for ADRs — *"do not
silently edit the numbers; the correction is an addendum that says what was
believed, why, and what changed."* The stakes are higher here, because this
document's entire function is to be fixed in advance.

## A0. What had been observed when this was written: nothing

This is the clause that makes an amendment legitimate rather than
contamination, so it is stated rather than assumed.

**No data was observed, at any point, by anyone, before or during the writing of
this amendment.** Specifically:

- The live database was **not** queried. No connection was opened to it.
- `scripts/run_chain.py` and `scripts/run_loop.py` were **not** run. No odds
  credits were spent. No orders were placed and nothing was deployed.
- `data/demo.db` was **not** read for any value. It is 100% synthetic and no
  number from it is evidence about anything.
- No value of `beta_hat`, `clv_tenths`, `sigma_eps`, `sigma_x`,
  `sd(half_spread_tenths)`, `G`, `n_rows` or the P1 coverage fraction exists
  anywhere, was computed, or was estimated from any record.

Everything measured below was measured by **executing project code on
synthetic inputs chosen here** — sweeping `size_position`, `calculate_fee` and
`edge_after_fees_tenths` over a price and edge grid, and running
`evaluate_suppression` to obtain the exact strings it emits. Those are
properties of the code, not observations of the record. Every one is labelled
**[COMPUTED FROM CODE]** below and each is reproducible from the repository
alone.

**Every change below is therefore blind to the answer.** None could have been
chosen to favour a result, because no result exists. Per §7, `G` for the
decision rule does not restart: the population definition is *narrowed* by §A2
in ways decidable from inputs alone, and no look has been taken.

## A1. The `suppressed_reason` predicate was broken. This is the fix.

**What was registered.** §2 and §S1 excluded two suppression codes with

```sql
AND (r.suppressed_reason IS NULL
     OR r.suppressed_reason NOT IN ('stale_odds', 'stale_kalshi_quote'))
```

**Why it was wrong.** `SuppressionResult.reason`
(`backend/core/suppression.py:95-103`) returns
`",".join(c.name for c in self.failures)` — a **comma-joined composite of every
check that failed**, not one code. `backend/engine.py:506` already knows this
and splits the column on `","` to build the suppression summary. So a row
reading `'stale_odds,wide_market'` is equal to neither literal and `NOT IN`
**retained** it — the exact population §2 excludes on the grounds that its
regressor is contaminated by drift that has already happened.

This is not an edge case, and the module says so in its own docstring: the
checks are ordered cheapest-first but **all of them run**, deliberately, because
"a row suppressed for staleness never reveals that it was also mis-matched, and
the second fact is the more important one." Staleness co-occurs with other
failures **by construction**. One dead odds feed trips several checks at once.
**[COMPUTED FROM CODE]** — driving `evaluate_suppression` with a stale feed and
a broken book returns the single string
`stale_kalshi_quote,stale_odds,no_commence_time,no_depth,too_few_books,no_market_width,suspicious_edge`.

**What now governs.** A delimited whole-field substring test:

```sql
AND (r.suppressed_reason IS NULL
     OR (instr(',' || r.suppressed_reason || ',', ',stale_odds,')         = 0
     AND instr(',' || r.suppressed_reason || ',', ',stale_kalshi_quote,') = 0))
```

Substitute this clause for the final clause of §S1's `WHERE`. Nothing else in
§S1 changes.

**`instr`, not `LIKE`, and the reason is not style.** The audit proposed
`',' || r.suppressed_reason || ',' NOT LIKE '%,stale_odds,%'`. In SQLite `LIKE`
treats `_` as a **single-character wildcard**, and every code in this vocabulary
contains underscores — so that form also matches `,staleXodds,`. No such code
exists today, which is precisely the problem: a predicate that is correct only
because nobody has yet added a colliding name is a predicate with a trap in it.
`instr` is a plain substring search with no metacharacters. The delimiting
commas are still required, and for the other direction: without them, a future
`stale_odds_upstream` would be silently excluded.

**Verified against the values the code can actually produce, not against
hand-written strings.** `tests/test_preregistration_population.py` builds every
composite by running `evaluate_suppression` and `apply_verdict`, inserts them
into a real schema-initialised database, and runs both predicates over them.
**The test was written against the registered predicate first and watched go
red** — three assertions failed, on `stale_odds,wide_market` and on the
seven-code composite, and on the head-to-head. It then went green on the
replacement. Per this repo's rule, a guard that has not been seen to fail is
decoration. The red-state assertion is kept permanently in
`test_the_superseded_predicate_let_the_multi_reason_row_through`, so the
correction cannot regress into the defect without a test naming it.

## A2. All thirteen suppression codes, adjudicated

**What was registered.** §2 adjudicated **four** — `insufficient_depth`,
`wide_market`, `suspicious_edge`, and unsuppressed `no_edge` rows — plus the two
staleness exclusions.

**Why that was incomplete.** `core/suppression.py` emits **eleven** codes.
`engine.py:219` adds a `sizing:` code. `agents/skeptic.py:200` appends
`skeptic_defect` or `skeptic_suspicious`, comma-joined onto whatever was already
there. Seven of the eleven, plus both later families, had no ruling — which
means the person who eventually runs this would have had to decide them **after
seeing the data**, which is the freedom this document exists to remove.

**What now governs.** Every code below is adjudicated. **Every reason given is
decidable from the row's inputs before the game is played.** None references
`clv_tenths`, `settled_win`, or any outcome.

| Code | Verdict | Why, from inputs alone |
|---|---|---|
| `stale_kalshi_quote` | **EXCLUDE** | Registered. The ask behind *both* variables is >30s old. A function of input timestamps. |
| `stale_odds` | **EXCLUDE** | Registered. The consensus behind `edge_tenths` aged past 900s, so part of the "edge" is drift that already happened. Contaminates the regressor. Timestamps only. |
| `no_commence_time` | **EXCLUDE** *(new)* | No commence time means fixture identity was never checked. The `fair` behind `edge_tenths` may describe a **different game** from the one the Kalshi market settles on, in which case the regressor is not an estimate about this row at all. A function of whether a timestamp is present. |
| `commence_skew` | **EXCLUDE** *(new)* | Same family, confirmed rather than unchecked: `abs(skew) > 4h` against a **measured** systematic offset of 3h (`SuppressionConfig.max_commence_skew_ms`) means two different fixtures sharing team names. Timestamps only. |
| `no_depth` | **RETAIN** *(new)* | Same argument §2 already accepted for `insufficient_depth`: depth governs whether an order *fills*; it does not move the mid, and CLV is measured against a mid. `None` here means size was unreadable, which is a property of the quote payload, not of the game. |
| `insufficient_depth` | **RETAIN** | Registered. |
| `too_few_books` | **RETAIN** *(new)* | Same argument §2 accepted for `wide_market`: consensus quality is the regressor's **content**, not a contaminant of it. Excluding the rows where the edge estimate is least reliable is a hypothesis about the answer. Its effect belongs in §A4's per-group view, not in the population rule. |
| `no_market_width` | **RETAIN** *(new)* | As above. Note it **always co-occurs with `too_few_books`** — both fire iff fewer than two books contributed — so it can never appear alone, and the two are one group in §A4. |
| `wide_market` | **RETAIN** | Registered. |
| `edge_within_method_noise` | **RETAIN** *(new — see A2.1)* | Excluding it removes a price-dependent interval from the **interior** of the regressor, which moves leverage to the tails and runs in the **flattering** direction. |
| `suspicious_edge` | **RETAIN** | Registered. Excluding it truncates the regressor from above. **But see §A4:** because it is defined by a threshold *on the regressor itself*, it now carries a mandatory downgrade check. |
| `sizing:refused` | **RETAIN** *(new)* | The refusal is about the operator's budget, the daily-loss kill switch, or a degenerate price — never about the game. All are input-decidable. **Exactly one value is producible** (see §A11.4). The degenerate-price case is handled by the price bound in §A2.2 instead. |
| `skeptic_defect`, `skeptic_suspicious` | **RETAIN** *(new)* | The Skeptic's prompt (`agents/skeptic.py:104-162`) carries only pre-game fields — ask, consensus, ages, book count, width, depth, devig methods, commence time. **No settlement, no closing line, no score.** It is outcome-blind by construction. It also fires only on rows that cleared every deterministic check, so excluding it would truncate the high-edge end — the same argument that retains `suspicious_edge`. **Two conditions:** its verdict is non-deterministic and the model version is not recorded per row, so (a) it is a mandatory §A4 group, and (b) the write-up states what fraction of the population carries a `skeptic_*` code. |

### A2.1. `edge_within_method_noise` — the one that matters, decided explicitly

`suppression.py:225-234` suppresses when `0 < edge_tenths <= method_spread`. The
audit is right that this is the dangerous one, and right about why: it removes
rows from the **middle** of the regressor's range, and the width of the hole
varies row by row with the devig spread — the module's own measurement is
**~1.8 tenths on an even moneyline and ~20.3 tenths on a longshot**
**[COMPUTED FROM CODE — `suppression.py:218-221`, quoting a prior measurement of
real lines]**. So the hole is wider exactly where the price is more extreme, and
price is the Grid A/B bucketing variable.

**Decision: RETAIN, and the deciding argument is the direction of the error.**

The case for excluding is that when the claimed edge is smaller than the
disagreement between devig methods, the edge number is an artifact of method
choice rather than a statement about the market (CLAUDE.md rules 1 and 2). That
is true. But it is an argument about **measurement error in the regressor**, and
it proves too much — it would justify excluding every row whose regressor is
noisy. Classical measurement error in `x` **attenuates** the slope toward zero.
Attenuation is the conservative direction. Excluding those rows removes the
attenuated middle and leaves the tails, which **inflates** `beta_hat`. So
excluding runs in the flattering direction and retaining runs in the safe one.
That decides it.

Three conditions attach:

1. **The hole cannot be reconstructed from the record.**
   `method_spread_probability` is a *parameter* of `evaluate_suppression` and is
   **not a column of `recommendations`** **[COMPUTED FROM CODE — absent from
   `store/schema.sql`]**. So the threshold that would tell us which rows sit in
   the hole is not stored. This is a limitation, not a reason to exclude, and it
   is added to §9 by §A8.
2. `edge_within_method_noise` is a mandatory **§A4 group**.
3. Because the code fires only on `0 < edge_tenths <= spread`, retaining it
   keeps the regressor's support connected across zero. That connectivity is the
   property the slope needs and it is the property exclusion would destroy.

### A2.2. One exclusion the registration never stated, added here

**§2 sets no bound on `entry_ask_tenths`, but Grid A and Grid B both do** —
`[10, 990)`. As registered, a row outside that range would enter the pooled
`beta` and appear in **no** bucket, so the pooled number and the per-group view
would be computed on different populations, silently.

**Add to §2's exclusions:** `r.entry_ask_tenths NOT BETWEEN 10 AND 989` is
excluded. Decidable from the stored price alone. It also disposes of the
degenerate-price arm of `sizing:refused` (`is_valid_price` rejects 0 and 1000 as
settled outcomes), so no separate rule is needed for that.

Add to §S1's `WHERE`:

```sql
AND r.entry_ask_tenths BETWEEN 10 AND 989
```

## A3. The `beta > 1 → BUG` rule is replaced

**What was registered.** §6: SIGNAL "if and only if ... **and**
`beta_hat <= 1.0`", and BUG if the boundary is cleared and `beta_hat > 1.0`,
because "the engine cannot understate its own edge."

**Why it was wrong.** The engine understates its own edge *by construction*, and
this document says so twice in its own voice. Four mechanisms produce `beta > 1`
with no defect anywhere:

1. **Deliberate conservatism.** CLAUDE.md rule 2 requires the **worst of four
   devig methods** for any money decision, so the stored `fair` understates true
   fair by a positive amount — and by an amount that covaries with
   longshot-ness, since the method spread is ~1.8 tenths on an even moneyline
   and ~20.3 on a longshot **[COMPUTED FROM CODE]**. A systematically shrunk
   numerator is a mechanism for a pass-through above one.
2. **This document's own F2.** `edge_tenths` is "a *more conservative* edge than
   the one the record's population predicate is built on, by up to 5 tenths"
   (§9). A regressor deliberately shrunk by a positive amount produces
   `beta > 1` mechanically.
3. **This document's own C2.** A true `beta` of 0.90 plus the +0.16 confound C2
   posits reads 1.06 and is classified **BUG**. The design forecloses its own
   SIGNAL branch on its own stated numbers.
4. **Sampling noise, which is the cleanest objection.** At `G = 300` this
   document's own figures give
   `se(beta_hat) ~= sigma_eps / (sigma_x * sqrt(G)) = 20 / (10 * sqrt(300)) = 0.1155`
   **[ARITHMETIC ON TWO ASSUMED INPUTS]**. A true `beta` of **exactly 1.0**
   therefore produces `beta_hat > 1.0` **half the time**, and is declared BUG
   half the time. Full lossless pass-through — the most favourable outcome the
   hypothesis admits — is a coin flip to be recorded as a defect report.

The structural fault underneath all four: the rule tests an always-valid
**interval** against the null of zero and a bare **point estimate** against the
ceiling of one. Those are different standards of evidence applied to the two
edges of the same estimate, in the same sentence.

**What now governs.** Substitute for §6's SIGNAL and BUG clauses:

> Let `m = always_valid_multiplier(G, tuning=300, alpha=0.05)` and
> `se = se_cluster(beta_hat)`. The always-valid interval is
> `[beta_hat - m*se, beta_hat + m*se]`.
>
> **BUG, NOT SIGNAL.** Declared if and only if, at a look taken when
> `G >= 300` **[SUPERSEDED by Amendment 2 §B4 — now `G >= 713`]**, the always-valid **lower** limit exceeds 1.0:
> `beta_hat - m*se > 1.0`. Only then has the record ruled out full pass-through
> from below, which is the only evidential state in which "the engine
> understates its own edge" is established rather than guessed. This is a defect
> report and no edge is claimed.
>
> **SIGNAL.** Declared if and only if, at a look taken when `G >= 300` **[SUPERSEDED by Amendment 2 §B4 — now `G >= 713`]**, the
> always-valid **lower** limit exceeds zero — `beta_hat > m*se` — **and** the
> BUG condition above does not hold, **and** the verdict survives §A4.
>
> **`beta_hat > 1.0` with a lower limit at or below 1.0 is a FLAG, not a
> verdict.** It is reported in those words, it triggers an investigation of
> `edge_after_fees_tenths` and the devig path, and it **does not suppress the
> finding**. The four mechanisms above are listed in the write-up beside it, and
> the write-up states that a point estimate above one is the *expected* reading
> under a deliberately conservative engine.

Both edges of the estimate are now judged by the same always-valid interval, at
the same alpha, from the same boundary. The BUG branch is not lost — it is moved
to where it means something.

## A4. The per-group view can downgrade a verdict, though it can never create one

**What was registered.** §6: the per-population breakdown "cannot upgrade the
verdict."

**Why that was incomplete.** Correct, and one-directional. As written, a
`beta_hat` carried entirely by `suspicious_edge` rows is declared SIGNAL — and
`suspicious_edge` fires on `edge_tenths > edge_ceiling_tenths = 40.0`, a
threshold **on the regressor itself**. Those rows therefore sit at the extreme
right of the x-axis and carry maximum leverage in a least-squares fit, by
construction rather than by accident. This repo's rule is that **a pooled number
is not a finding until the parts agree**, and a rule that only ever blocks the
parts from *helping* enforces half of it.

**What now governs.** Add to §6:

> **The pre-registered groups.** Fixed here, and no others may be introduced
> after the data is read:
>
> - `suppressed_reason IS NULL` (unsuppressed)
> - each retained code from §A2 present anywhere in the composite:
>   `no_depth`, `insufficient_depth`, `too_few_books` (with `no_market_width`,
>   which always co-occurs), `wide_market`, `edge_within_method_noise`,
>   `suspicious_edge`, `sizing:refused`, `skeptic_*`
> - the three Grid A price buckets
>
> Groups are **non-exclusive**: a composite row belongs to every group whose code
> it carries.
>
> **Reported beside `beta_hat`, always.** For every group: `n_rows`,
> `n_clusters`, and its **leverage share** — its share of `sum_i (x_tilde_i)^2`,
> where `x_tilde` is `edge_tenths` residualised on `half_spread_tenths` and the
> intercept, which is the quantity that actually weights the partial slope. The
> **largest contributor's share is printed on the same line as `beta_hat`**, per
> the repo's measurement rule.
>
> **The downgrade test (leave-one-group-out).** For each pre-registered group
> whose removal leaves `G >= 300`, recompute `beta_hat` and its always-valid
> interval on the remaining population. Then:
>
> - a **SIGNAL** verdict is downgraded to **UNRESOLVED** if any such
>   recomputation returns `beta_hat <= 0`;
> - a **NO SIGNAL** verdict is downgraded to **UNRESOLVED** if any such
>   recomputation returns an always-valid upper limit at or above 0.40.
>
> The write-up names the group that caused the downgrade, in those words.
>
> **Groups whose removal would leave `G < 300` cannot be tested** and are **not**
> grounds for downgrade — there is nothing left to compare against, and treating
> that as a downgrade would foreclose SIGNAL whenever one group is most of the
> sample, which is the same defect §A3 fixes. Their leverage share is reported,
> and if it exceeds 0.50 the write-up must state that **the pooled result is one
> group's result**.
>
> **This rule is strictly one-way.** It can turn SIGNAL or NO SIGNAL into
> UNRESOLVED. It can never turn UNRESOLVED into anything, it can never raise a
> verdict, and **no group result may be reported as a finding** — §6's
> multiplicity arithmetic is unchanged and the groups remain descriptive.

The test is on the **claim** (does the sign survive; does the ruling-out
survive) rather than on statistical significance, deliberately: losing
significance after discarding a quarter of the data is a power artefact, whereas
a point estimate crossing zero when one group is removed is the parts
disagreeing. That is a judgement, and it is fixed here in advance rather than
made after the number exists.

## A5. Two things corrected, not re-argued

### A5.1. F2's item 1 is false, and it is the item the document marked as good news

**What was registered.** F2 item 1: *"Every row's `edge_tenths` is computed on
the same n=1 fee basis, so the regressor is internally comparable and no
edge-correlated fee step contaminates the slope. … At $100 that hazard is
absent. At $1,000 it would be present."*

**Why it was wrong.** `engine.py:160-166` computes `edge_tenths` at
`max(1, sizing.contracts)`, and `sizing.contracts` is **not** pinned at zero
across the retained range. **[COMPUTED FROM CODE — `size_position` swept at the
live `fly.live.toml` profile: `BANKROLL_DOLLARS=100`, `KELLY_FRACTION=0.25`,
`MAX_POSITION_DOLLARS=10`, `MAX_EXPOSURE_DOLLARS=40`, zero open exposure;
`kelly` binding throughout]**:

| ask | gross gap 3.0c | 3.8c | 5.0c | 6.0c | 7.0c |
|---|---:|---:|---:|---:|---:|
| 20c | 1 | 2 | 4 | 5 | 7 |
| 30c | 1 | 2 | 3 | 4 | 5 |
| 50c | 1 | 1 | 3 | 4 | 5 |
| 70c | 1 | 2 | 3 | 4 | 6 |
| 80c | 1 | 3 | 5 | 6 | 8 |

Contracts run **1 to 6 among unsuppressed rows**, and to **at least 8** among
the `suspicious_edge` rows §2 deliberately retains. At ask 30c a 38-tenth gross
gap gives **2** contracts; at ask 80c it reaches **8**. F2's own table stopped at
the 4.0c row and read it as the point where contracts are still 0; it is the
point where they reach 2.

**The consequence, which is the part that matters.** `edge_tenths` is a
**discontinuous step function** of the underlying gross gap, because the
per-contract fee steps at each contract boundary. **[COMPUTED FROM CODE —
`calculate_fee`, per-contract, tenths of a cent]**:

| ask | n=1 | n=2 | n=3 | n=4 | n=5 | n=8 |
|---|---:|---:|---:|---:|---:|---:|
| 10c | 10.00 | 10.00 | 10.00 | 10.00 | 10.00 | 10.00 |
| 20c | 20.00 | 15.00 | 13.33 | 12.50 | 12.00 | 11.25 |
| 30c | 20.00 | 15.00 | 16.67 | 15.00 | 16.00 | 15.00 |
| 40c | 20.00 | 20.00 | 20.00 | 17.50 | 18.00 | 17.50 |
| **50c** | **20.00** | **20.00** | **20.00** | **20.00** | **20.00** | **20.00** |
| 60c | 20.00 | 20.00 | 20.00 | 17.50 | 18.00 | 17.50 |
| 70c | 20.00 | 15.00 | 16.67 | 15.00 | 16.00 | 15.00 |
| 80c | 20.00 | 15.00 | 13.33 | 12.50 | 12.00 | 11.25 |
| 90c | 10.00 | 10.00 | 10.00 | 10.00 | 10.00 | 10.00 |

So within the retained band (`0 < edge_tenths <= 40`), `edge_tenths` jumps
**[COMPUTED FROM CODE]**:

| ask | jump at 1→2 | at 2→3 | at 3→4 |
|---|---:|---:|---:|
| 20c | **+5.0** | +1.7 | +0.8 |
| 30c | **+5.0** | **−1.7** | +1.7 |
| 40c | 0.0 | 0.0 | +2.5 |
| **50c** | **0.0** | **0.0** | **0.0** |
| 60c | 0.0 | 0.0 | +2.5 |
| 70c | **+5.0** | **−1.7** | +1.7 |
| 80c | **+5.0** | +1.7 | +0.8 |

Four properties follow, and each is a statement about the regressor:

1. **The largest jump is 5.0 tenths**, at 20c, 30c, 70c and 80c, on the 1→2
   contract boundary. Against F2's own `sigma_x = 10` tenths **[ASSUMED]** that
   is **half a standard deviation of the regressor, from arithmetic**.
2. **It varies with price and is exactly 0.0 at 50c.** So the regressor's
   measurement error is heteroskedastic in price — and price is the Grid A and
   Grid B bucketing variable. Buckets therefore differ in how contaminated their
   regressor is for reasons having nothing to do with signal.
3. **It is non-monotonic at 30c and 70c.** The 2→3 boundary *lowers* the stored
   edge by 1.7 tenths, so a **larger** true gap can store a **smaller**
   `edge_tenths`. The audit did not name this and it is the sharper finding: a
   regressor that is not a monotone function of the quantity it proxies is worse
   than a noisy one.
4. **Nothing in the schema records which basis a row used.** `contracts` is not
   a column of `recommendations`; `suggested_contracts` is the *post*-suppression
   number, zeroed whenever the row was suppressed
   (`engine.py:205`), so it cannot be used to recover the basis on exactly the
   rows §2 retains.

**Direction of the effect on `beta`: unknown, and it is registered as unknown.**
The dominant term runs toward attenuation — because a bigger gap buys more
contracts and a smaller per-contract fee, `edge_tenths` moves *faster* than the
true gap, which inflates `sd(x)` and deflates the slope, the safe direction. But
the non-monotone segments at 30c and 70c reverse that locally, so the net sign is
not provable a priori. It is **not** claimed to be conservative.

**One further basis shift the audit did not name.** `sizing.contracts` also
depends on `current_exposure_dollars`, `current_position_dollars` and
`daily_pnl_dollars` (`sizing.py:140-182`) — the **operator's live account state
at the instant of the pass**. Two identical markets evaluated an hour apart can
store `edge_tenths` on different bases, and none of those three inputs is
recorded per row. F2 item 4 anticipated this for `BANKROLL_DOLLARS` only.
**Added to the required output:** report open exposure and daily P&L at every
interim look, alongside `BANKROLL_DOLLARS`.

**And the units error underneath it.** F2 states *"4c is
`edge_ceiling_tenths = 40.0`, at which `suspicious_edge` suppresses"*, but
`edge_ceiling_tenths` is a threshold on the **net** edge while F2's table is in
**gross** gap. At 50c a 4.0c gross gap stores a *net* edge of **2.0c**.
`suspicious_edge` first trips at these gross gaps **[COMPUTED FROM CODE]**:

| ask | 20c | 30c | 40c | 50c | 60c | 70c | 80c |
|---|---:|---:|---:|---:|---:|---:|---:|
| gross gap needed | 5.26c | 5.51c | 5.90c | **6.00c** | 5.77c | 5.50c | 5.21c |
| contracts there | 4 | 4 | 4 | **4** | 4 | 4 | 5 |

So suppression does **not** close the multi-contract band. It opens at 2
contracts and stays open for another 2–3 tenths of a cent of gross gap before
`suspicious_edge` fires, and even then those rows are **retained** by §2.

### A5.2. "Central" is withdrawn. 0.40 stands, on a different argument.

**What was registered.** `sigma_eps / sigma_x = 2` described as "central", and
0.40 defended by two derivations described as independent of each other.

**Why it was wrong.** *(a)* Nothing measures the ratio. "Central" claims a
location in a distribution nobody has observed; the honest label is **ASSUMED**,
and it is applied above. *(b)* The two derivations are not independent. The
first inherits `sigma_eps / sigma_x = 2` **entirely** — 0.42 *is* that
assumption run through the boundary. The second, *"the pass-through at which a
typical 20-tenth claimed edge yields 8 tenths of CLV, against 3.8 tenths of
headroom"*, taken literally as a derivation gives `3.8 / 20 = 0.19`, not 0.40.
What it actually does is compute `0.40 x 20 = 8`, observe `8 > 3.8`, and present
that as confirmation. It confirms only that **0.40 clears the economic
minimum** — a necessary condition, not a second estimate. It must stop being
described as independent.

**What now governs. 0.40 is kept**, and the defence that carries it is the one
the audit correctly identifies as strongest and as missing from the
registration:

> **Using the minimum detectable effect as the NO-SIGNAL threshold is right in
> principle.** A negative verdict that could not have detected a real effect is
> not a negative result. Setting the threshold at the smallest effect the design
> can resolve is what makes NO SIGNAL mean "we could have seen it and it was not
> there" rather than "we looked with an instrument too blunt to see it."
>
> **And the error runs safe.** If the true `sigma_eps / sigma_x` is worse than
> the assumed 2, then `se` is larger, the always-valid interval is wider, its
> upper limit exceeds 0.40 more often, and **NO SIGNAL becomes harder to
> declare**. The failure mode of a bad assumption here is therefore **permanent
> UNRESOLVED — never a false kill.** Since the NO SIGNAL branch is the one that
> stops work on arming real money (§8), an assumption whose error can only delay
> that verdict and never manufacture it is the right way round.
>
> `sigma_eps`, `sigma_x` and their ratio remain **reportable at every interim
> look**, and the existing instruction stands: if per-game CLV noise comes in
> above 30 tenths, this document is amended to raise the floor.

### A5.3. The 300-game agreement is not a check on anything

**What was registered.** *"The gate's 300-game floor and the smallest `n` at
which this test can resolve a plausible effect are the same number. That was not
arranged … They agree, which is a mild independent check on both."*

**Why it was wrong.** It was arranged. The multiplier producing 0.42 is
`gate.always_valid_multiplier(G, tuning=300, alpha=0.05)`, and `tuning=300` is
the gate's floor — the boundary's mixture parameter is **set to** the number the
agreement is then read as corroborating. `gate.py`'s own docstring says the
mixture parameter "is tied to the pre-registered floor (300 games) so the bound
is near its best across the range the gate actually operates in." Finding the
minimum-detectable effect to be near its best at `G = 300` is the tuning
parameter reappearing in its own output.

**What now governs.** The sentence is withdrawn. The 300 floor stands on the
practitioner-consensus argument alone, which was always its actual basis, and
the write-up must not present the coincidence as evidence.

## A6. The level-test null is −5 tenths, measured

**What was registered.** §5: `E[clv_tenths] = -half_spread ~= -5 to -15 tenths`.

**Why it was wrong.** The −15 end requires a 3.00c spread. `docs/adr/0006-in-play-evidence.md`
**measures** the pre-game Kalshi spread at **1.00c at mean, median, p90, p99 and
maximum**, across **3,483 pre-game minutes over 20 games** (14 MLB, 6 WNBA,
2026-08-07/08), in both leagues, agreeing on every line. A 3.00c spread appears
only **in-play** (p99), which this measurement excludes by construction. The
registered range was **[ASSUMED]** and its wide end is contradicted by the one
measurement in the repo that bears on it.

**What now governs.** §5's null reads:

> Under zero predictive power and zero drift,
> `E[clv_tenths] = -half_spread ~= -5 tenths` **[MEASURED FROM DATA — ADR 0006,
> pre-game half-spread 0.50c, 3,483 minutes over 20 games, MLB and WNBA]**.

Two qualifications, both required in the write-up:

- ADR 0006 measures **candlestick** spreads at 1-minute granularity. Roughly 25%
  of Kalshi markets tick in deci-cents (CLAUDE.md), so a whole-cent spread field
  may be quantising away sub-cent variation. The **level** of 1.00c is measured;
  the **dispersion** is not resolved by that instrument, which is why §A5 leaves
  C2's `sd` open rather than replacing 4 with 0.
- It is two leagues on one August slate. It says nothing about NFL, NBA or NCAAF
  spreads, and §9's seasonal caveat already covers that.

## A7. Two more §3 invariants — and the audit's third anchor is not enough on its own

**What was registered.** §3 asserts two properties of the cluster-robust
estimator: duplicating every observation `k` times leaves `beta_hat` and its
standard error bit-identical, and singleton clusters reproduce classical OLS
exactly.

**Why that was incomplete.** Both are anchors on the **standard error**. Neither
pins the **partial-slope arithmetic**, so an estimator that accepts
`half_spread_tenths` and never uses it — which leaves C2's contamination
entirely in place, the single thing the control exists for — passes both.

**What now governs.** Two further invariants, asserted as tests before any
result is believed:

> **A3-c. With `half_spread` held constant, `beta` must equal the
> simple-regression slope of `clv_tenths` on `edge_tenths`.** With the control
> constant it is collinear with the intercept, so it can carry no information
> and the partial slope must collapse onto the simple one.
>
> **A3-d. With `half_spread` correlated with `edge_tenths`, and `clv_tenths`
> generated exactly as `a + b*edge + c*half_spread` with no noise, `beta` must
> return `b` and `gamma` must return `c`, to floating-point tolerance.**

**A3-c is the audit's proposal and it is necessary but not sufficient — verified
rather than argued.** **[COMPUTED FROM CODE — throwaway reference
implementations on synthetic inputs, no repository data]**: with `n = 500`,
`x ~ N(0, 10)`, `w` held at the constant 5.0 and
`y = 3 + 0.6x + 2w + N(0, 2)`, a correct two-regressor estimator and one that
**ignores the control entirely** both return `beta = 0.600979`, identical to the
simple slope. **A3-c does not catch the defect it is aimed at.** What it does
catch is real but narrower: a naive `inv(X'X)` on that input raises
`Singular matrix`, so A3-c pins the rank-deficiency handling.

**A3-d catches it.** With `w = 0.5x + N(0, 5)` and `y = 3 + 0.6x + 2w` exactly,
the correct estimator returns `beta = 0.600000`, `gamma = 2.000000`; the
control-ignoring one returns `beta = 1.625292` against a true 0.600 — an error of
**2.7x**, in the **inflating** direction, which is exactly the shape C2
describes. Both invariants are registered; A3-d is the one that pins the partial
arithmetic and it must be present.

**Fewer than 2 clusters returns `None`, never a number** — unchanged.

## A8. Three additions to §9, "what this cannot establish"

**Why they are needed.** §9 as registered omits the entries that could actually
overturn the result. Caveats that cannot overturn anything are the ones that get
written; these are the other kind.

### A8.1. The shared `−entry_ask` term contaminates beyond the half-spread

Add to §9:

> - **Controlling `half_spread` removes only the *deterministic* part of the
>   shared-ask contamination.** C2 decomposes the ask as mid plus half-spread,
>   but `clv_tenths` and `edge_tenths` share the **whole** `-entry_ask` term, not
>   just its spread component. **Any transient dislocation in the entry ask — a
>   momentary thin book, a single large resting order, a quote taken mid-update —
>   lowers both `edge` and `clv` together**, and such a dislocation is by
>   definition not captured by the half-spread of that same quote. The residual
>   covariance is therefore positive and is **not** removed by `gamma`. Its
>   magnitude is unmeasured and no attempt is made here to bound it.

### A8.2. The half-spread control may be joined from the wrong quote — and P1 conflates two failures

§S1 joins *the latest quote at or before `created_ms`*, which is **not
necessarily the quote that set `entry_ask_tenths`**. If they differ, the control
is measured with error, the control is **attenuated**, and — because
under-controlling for a positively-contaminating confound leaves part of it in —
the residual bias in `beta` is **positive**. The flattering direction.

The check is free, because the derived-ask identity is exact
**[COMPUTED FROM CODE — `runner.py:875-895`: a YES ask is filled by the resting
NO bid, so `yes_ask = 1000 - no_bid`; a NO ask is filled by the resting YES bid,
so `no_ask = 1000 - yes_bid`]**. Add to §S1's select list:

```sql
  CASE r.side
    WHEN 'yes' THEN ((1000 - q.no_bid_tenths)  = r.entry_ask_tenths)
    WHEN 'no'  THEN ((1000 - q.yes_bid_tenths) = r.entry_ask_tenths)
  END                                             AS quote_matches_entry,
```

**And P1 is split, because as registered it conflates two different failures**
and refuses only the second. Three counts are reported, never two:

| Count | Meaning | Treatment |
|---|---|---|
| `matched` | a quote joined **and** `quote_matches_entry` is true | the analysis population |
| `quote_mismatch` | a quote joined and the identity **fails** | **retained**, but counted and reported separately |
| `no_quote` | the join returned nothing; `half_spread_tenths IS NULL` | dropped, never imputed |

- **P1's 0.90 floor now applies to `matched / total`**, not to non-NULL
  half-spread coverage. That is a strictly tighter gate than the one registered.
- `quote_mismatch` rows are **retained** — the alternative is an exclusion whose
  rate correlates with book activity, which is worse — but if
  `quote_mismatch / total` exceeds 0.05 the write-up must state, in these words,
  that the half-spread control is attenuated on that fraction and that the
  residual bias in `beta` runs **positive**.

### A8.3. The P1 shortfall is a selection problem, not a proportional one

**What was registered.** §9: *"If P1 lands between 0.90 and 1.00, the residual
contamination is proportional to the missing fraction and must be stated as a
number."*

**Why it was wrong.** §S1 **drops** rows with a NULL half-spread; it does not
impute them. So there is **zero** residual contamination on the rows that are
retained — every one of them has a real control. What the missing fraction
creates is a different problem entirely, and a worse-behaved one.

**What now governs.** Replace that bullet with:

> - **A P1 shortfall is a selection problem of unknown direction, not a residual
>   contamination.** Retained rows are fully controlled. The rows that are gone
>   are those for which no readable pre-entry quote existed, which is a
>   liquidity-flavoured and time-of-day-flavoured criterion, and the direction in
>   which that shifts `beta` is **not known and is not estimated here**. Stating
>   it as "contamination proportional to the missing fraction" would understate
>   it, because a proportional bias shrinks to nothing as coverage approaches 1
>   while a selection effect need not.

### A8.4. Two limitations that follow from this amendment

Also add to §9:

> - **`edge_tenths` is a discontinuous and locally non-monotonic function of the
>   underlying gross gap, and the record does not say which basis each row
>   used.** See §A5.1. Steps of up to 5.0 tenths, varying with price, zero at
>   50c, negative at 30c and 70c. The direction of the resulting bias in `beta`
>   is unknown and is not claimed to be conservative.
> - **`method_spread_probability` is not stored**, so the rows that
>   `edge_within_method_noise` would have removed cannot be identified in the
>   record, and the width of the hole that rule punches in the regressor cannot
>   be measured after the fact. §A2.1 retains those rows precisely because the
>   alternative is an unmeasurable, price-dependent exclusion.

## A9. Consequences for the required output of every run

§S1's output list is amended. The harness prints, in this sequence:

1. `G`, `n_rows`, `unclustered_rows`, and **three** coverage counts —
   `matched`, `quote_mismatch`, `no_quote` — with `matched / total` named as the
   P1 fraction (§A8.2).
2. `sigma_eps`, `sigma_x`, their ratio, `sd(half_spread_tenths)`, and the implied
   spurious slope `Var(half_spread)/Var(edge)` — each labelled **measured**, and
   the ratio explicitly compared against the **assumed** 2 (§A5.2).
3. `BANKROLL_DOLLARS`, **open exposure and daily P&L** (§A5.1), and the
   `strategy_config_version` distribution.
4. The smallest resolvable `beta` at this `G`, **before** `beta_hat` is printed.
5. `beta_hat`, `se_cluster`, the multiplier, **both** limits of the always-valid
   interval, the **largest group's leverage share on the same line** (§A4), and
   the verdict — including the §A3 flag if `beta_hat > 1.0` with a lower limit at
   or below 1.0.
6. The §A4 per-group table with every group's `n_rows`, `n_clusters` and leverage
   share, and the leave-one-group-out result for every testable group.
7. Grid A, then Grid B, each labelled **DESCRIPTIVE — CANNOT PRODUCE A FINDING**,
   with `family_wise_p` and `family_wise_verdict` above them.
8. `horizons_agree`, labelled as the weak control it is.
9. §9 **as amended by §A8**, reproduced verbatim.

## A10. What this amendment does not change, stated so the absence is deliberate

- **The primary estimand, the direction, the cluster key, the horizon, the
  boundary, the `G >= 300` floor, the stopping rule, the 0.40 threshold and the
  result destination all stand unchanged.**
- **The UNDERPOWERED verdict stands. The registered action is still to wait, not
  to run.** Nothing here makes the test runnable at a smaller `G`.
- **Grid A's bucket edges stand.** They are derived from the n=1 fee model, and
  §A5.1 shows the fee is *not* flat across `[200, 800)` at n≥2 — which is a
  reason the edges must **not** be re-derived later, exactly as F2 item 2 already
  says. Re-deriving them now, after seeing that contracts vary, would be choosing
  a cut after learning something about the data-generating process.
- **C2's `sd(half_spread) = 4` is not replaced with a number.** ADR 0006
  contradicts it, but ADR 0006's instrument (1-minute whole-cent candlesticks)
  cannot resolve sub-cent dispersion. A parallel lane is measuring it. **Marked
  placeholder:** the governing figure will be
  `docs/measurements/2026-08-09-halfspread-dispersion.md`, which **does not exist
  at the time of this amendment**. Until it does, C2's magnitude is
  **unmeasured** and the 0.16 may not be quoted as a finding in any write-up.
- **F1's status, re-verified at this commit:** `backend/store/schema.sql:330`
  still reads `edge_tenths REAL NOT NULL, -- gross, before fees`, and the code
  still stores net. The correction is on a lane not yet merged to `main`. F1's
  conclusion is unaffected — this analysis is designed against the code.
- **P2, P3, P4 stand unchanged.** P1 is tightened by §A8.2.

## A11. Where the audit is itself wrong or incomplete

The audit is not above correction either. Five items, each verified.

1. **The proposed third §3 anchor does not catch the defect it names.** The
   audit asks for "with `half_spread` held constant, `beta` must equal the
   simple-regression slope" on the grounds that the two registered anchors do not
   pin the partial-slope arithmetic. Measured (§A7): an estimator that ignores
   the control entirely returns **exactly** the simple slope on that input and
   passes. The anchor is necessary but not sufficient; §A7 keeps it for what it
   does catch (rank deficiency) and adds A3-d, which does catch it.

2. **"Jumps up to 6 tenths at each contract boundary" is 5.0 tenths.** Measured
   from `calculate_fee`: the 1→2 boundary at 20c, 30c, 70c and 80c moves the
   per-contract fee from 20.00 to 15.00 tenths, so the jump is **5.0**. The
   document's own F2 item 2 already gives this correctly as "a 0.5-point
   difference". The audit's "0 at 50c" is confirmed exactly. The audit also
   misses two smaller structures: a **+2.5** tenth jump at 40c and 60c on the
   3→4 boundary, and — the more important one — a **−1.7** tenth jump at 30c and
   70c on the 2→3 boundary, which makes the regressor **non-monotonic**, not
   merely discontinuous.

3. **"~6.1c gross gap" at 50c is 6.00c.** Confirmed in substance: tripping
   `suspicious_edge` at 50c takes a **6.00c** gross gap at **4** contracts, and
   the audit's conclusion — that suppression does not close the multi-contract
   band — is correct and is the load-bearing part.

4. **`sizing:<constraint>` has exactly one producible value, not a family.**
   `engine.py:218` writes it only when `sizing.refused`, and the only path that
   sets `refused=True` is `_refuse()` (`sizing.py:216-226`), which hardcodes
   `binding_constraint="refused"`. So the only string is **`sizing:refused`**.
   The other constraint names — `kelly`, `no_edge`, `max_position_dollars`,
   `max_exposure_dollars`, `max_order_contracts`, `stake_below_one_contract` —
   never reach `suppressed_reason`. Adjudicating a family that cannot exist would
   have been harmless; assuming the record can be grouped by it would not.

5. **The audit's list of eleven codes is missing two, and they are
   composite-forming.** `agents/skeptic.py:200` appends `skeptic_defect` or
   `skeptic_suspicious` **with a comma** onto whatever reason already exists
   (`f"{existing_reason},{tag}"`), and `agents/review.py:115` is wired into
   `runner.py`, so these are live codes and not a plan. A predicate built for
   eleven codes would have been correct for thirteen only by luck. §A2
   adjudicates them; `tests/test_preregistration_population.py` pins the append
   format.

One further note, on the audit's suggested `LIKE` form: `LIKE` reads `_` as a
single-character wildcard and every code in this vocabulary contains
underscores, so the delimited `LIKE` predicate is correct only because no code
name currently collides. §A1 uses `instr` instead, which has no metacharacters.

---

**Amendment 1 ends. No data had been observed when it was written (§A0).**

---

## Note, 2026-08-17 — NOT AN AMENDMENT. NO RULE HERE CHANGES.

**This note adjudicates nothing, adds no cut, moves no threshold and touches no
stopping rule.** It is recorded here, after data, solely because this file is
what a session opens before taking the `G = 300` look, and a reader who stops
here would miss a fact about the population that arrived after Amendment 1
closed. Every rule above governs unchanged, including the floor of `G = 300` and
the prohibition on declaring below it.

**The fact:** scheduled prop buying was turned off on 2026-08-16 (ADR 0032). At
the interim look, props supplied **81 of 199 clusters (40.7% of `G`)** under
*this registration's* cluster key — `COALESCE(m.event_ticker, r.ticker)`, which
is deliberately **not** the gate's key (`backend/analysis/clv_signal.py:109-114`;
the two keys gave 210 and 125 on the same record). Accrual from 2026-08-16 is
therefore moneyline-dominated.

**Why it matters at the look:** the arms were `moneyline −0.082` and
`prop −0.519`. A pooled estimate losing its more-negative arm from the intake is
expected to drift **toward zero**, i.e. toward the NO-SIGNAL threshold and toward
what reads as improvement — by composition, not by evidence.

**Required at the `G = 300` look:** report the arm split *as measured then*.
Do not carry 118/81 forward, and do not project a magnitude — the published arms
do not reconstruct the pooled `beta_hat` under any weighting, and the reason is
explained in the interim look's 2026-08-17 annotation.

Full write-up: `docs/measurements/2026-08-16-clv-signal-test-interim-look.md`,
annotation dated 2026-08-17.

---

# Amendment 2 — 2026-08-29 — the power check's sigma trigger fired, and the floor is raised

**Status: this is an amendment. It changes rules.** It changes exactly one
number in §6 and §7 — the declaring floor — and adds reportables to §A9.
Everything else in this document and in Amendment 1 governs unchanged.

**It changes no past verdict.** The 2026-08-16 interim look and the 2026-08-25
audited look were both **UNRESOLVED** and both remain **UNRESOLVED**. Nothing
here re-reads them, and nothing here may be cited as converting either.

**It is written before the next look**, as §7 requires: *"the amendment is
written into this file with its date and reason **before** the next look ... An
amendment made after a look and not recorded voids the registration."* The
trigger fired at the 2026-08-25 look and this amendment was not written for four
days; that gap is recorded here rather than smoothed over. No look was taken in
the interval.

## B1. The trigger, quoted exactly

The power check's level-test section closes with this instruction, transcribed
verbatim from the section headed *"The same arithmetic for the level test,
against the real headroom"* (line breaks as in the original):

> At the central `sigma = 20` tenths, **`G = 350`** is needed to resolve an
> effect the size of the entire fee advantage. The gate asks for 300. So the
> gate is calibrated to about the right order and is, if anything, slightly
> optimistic — and if per-game CLV noise turns out to be 3c rather than 2c, the
> honest floor is **656 games**, more than double what the gate requires.
> `sigma` is therefore a **reportable quantity at every interim look**, and if
> it comes in above 30 tenths this document must be amended to raise the floor.

Amendment 1 §A5.2 restates it, and the restatement is also binding:

> `sigma_eps`, `sigma_x` and their ratio remain **reportable at every interim
> look**, and the existing instruction stands: if per-game CLV noise comes in
> above 30 tenths, this document is amended to raise the floor.

Neither sentence is conditional on anything else. Neither offers a branch in
which the floor stays where it is. The instruction is *"must be amended to raise
the floor"*, and the only free parameter it leaves is **by how much**.

## B2. It fired

Measured at the 2026-08-25 look and recorded in
`docs/measurements/2026-08-25-clv-signal-declaring-look-refused.md` §D6 and §D8:

| quantity | pooled (all config versions) | **modal version only (§P4/§7 primary)** |
|---|---:|---:|
| `sd(clv_tenths)` — per-game CLV noise | **30.1481** | **31.6915** |
| `sigma_eps` — residual SD of `clv_tenths` | 29.7637 | not reported |

Both readings of the *level* quantity are above 30. The trigger fired.

It may have fired earlier and gone unseen: the 2026-08-16 interim look reports
none of `sigma_eps`, `sigma_x` or `sd(half_spread)`, which §A9 item 2 requires at
every look. Whether the trigger was already live at `G = 199` is not recoverable
from that write-up.

## B3. Which `sigma` — settling §D8, in the direction that raises the floor

§D8 of the audit correctly refuses to settle this and hands it here: the power
check's *slope* setup defines `sigma_eps` as the **residual** SD of
`clv_tenths` (29.7637), while the harness prints the **raw** SD (30.1481), and
the two straddle 30.

**Settled: the trigger's `sigma` is the raw per-game SD of `clv_tenths`.** Three
reasons, and none of them is a preference:

1. **The sentence is attached to the level test, not the slope test.** It closes
   the paragraph under the table headed *"Smallest resolvable mean CLV, in
   tenths"*, whose column header is `sigma = 20t` and whose estimator is §5's
   *mean of game-clustered `clv_tenths`*. That estimator has no regression and
   therefore no residual; its standard error is built from the raw dispersion of
   the clustered outcome. The residual SD is the *slope* section's `sigma_eps`
   and is a different quantity in a different formula.
2. **Amendment 1 §A5.2 names it in plain words** — *"per-game CLV noise"*, not
   "residual noise".
3. **It is the larger number**, so a reader who thinks (1) and (2) are arguable
   still lands on the floor that is harder to reach. Where the reading is
   genuinely ambiguous the tie goes against the project.

**And the ambiguity does not survive the arithmetic anyway.** At
`sigma = 29.7637` — the residual reading, the smallest of the three candidates —
the floor recomputed below is **643 games**. Every candidate value of `sigma`
puts the floor past 600. There is no reading of §D8 under which 300 survives.

## B4. The recomputed floor — same formula, same target, arithmetic shown

**The formula is the power check's own**, unchanged, with no term added, removed
or re-picked:

```
MDE_level(G) = always_valid_multiplier(G, tuning=300, alpha=0.05) * sigma / sqrt(G)
```

`always_valid_multiplier` is `backend/gate.py:133`, the Robbins normal-mixture
boundary. **`tuning` stays at 300 and is not touched** — see §B6(4) for why.

**The target is the power check's own**: `3.8` tenths, the fee headroom the
registration was written against. It is *not* re-picked to the 6.3 tenths
CLAUDE.md now carries after ADR 0028 retired the fee hedge. A larger target
would lower the floor, which is the flattering direction, and the registration
fixed 3.8 before any data existed. **3.8 stands.**

**Verification that this is the same formula the registration ran.** It
reproduces the registration's published level table exactly at `sigma = 20`:

```
G           20     40    100    300   1000
published  44.0   22.8   10.0    4.2    2.0
recomputed 44.0   22.8   10.0    4.2    2.0
```

**Solving `MDE_level(G) = 3.8` for `G`:**

| `sigma` (tenths) | source | **`G` needed** | `MDE` at that `G` | `MDE` at `G = 300` |
|---|---|---:|---:|---:|
| 20 | registered ASSUMED | 349 (published: 350) | 3.797 | 4.222 |
| 29.7637 | residual SD, pooled | 643 | 3.797 | 6.283 |
| 30.0 | the trigger's own worked example | 651 (published: 656) | 3.799 | 6.333 |
| **30.1481** | **`sd(clv_tenths)`, pooled** | **656** | **3.800** | **6.364** |
| **31.6915** | **`sd(clv_tenths)`, modal only** | **713** | **3.798** | **6.690** |

Worked, for the pooled figure:

```
always_valid_multiplier(656, tuning=300, alpha=0.05) = 3.2281
3.2281 * 30.1481 / sqrt(656) = 97.32 / 25.612 = 3.7997  <= 3.8   OK
at G = 655 the same expression gives 3.8025 > 3.8                 NOT OK
```

and for the modal figure:

```
always_valid_multiplier(713, tuning=300, alpha=0.05) = 3.2002
3.2002 * 31.6915 / sqrt(713) = 101.42 / 26.702 = 3.7982 <= 3.8   OK
```

**A reproduction discrepancy, recorded because recording it runs against us.**
The registration's `G`-needed row prints 142 / 350 / 656 / 1070 at
`sigma = 10 / 20 / 30 / 40`; the exact solve gives 140 / 349 / 651 / 1066. All
four published values are 1–5 games *larger* than the exact solve, i.e. the
original search was slightly conservative in every cell. The discrepancy is not
adjudicated here and does not need to be: **the exact solve at the measured
`sigma = 30.1481` and the registration's own published cell at `sigma = 30` are
the same number, 656.** The registration pre-named its own amended floor. This
amendment is arithmetic the registration had already done.

### The floor, fixed

> **The declaring floor of §6 and §7 is raised from `G = 300` to `G = 713`.**

`713` and not `656` because §7 and §P4 make the **modal `strategy_config_version`
population** the primary — *"the primary runs on the modal version and `G` counts
only those games"* — and `sd(clv_tenths)` on that population is `31.6915`. The
floor is computed on the population the declaration is made on. 656 is the
pooled figure and the pooled fit carries no verdict.

**The floor is a ratchet, not a recomputation.** It is fixed once, here, at 713.
It is **not** re-derived at each look, because a floor recomputed from whatever
`sigma` a look happens to measure is a threshold chosen after the data — the
exact freedom this registration exists to remove. Specifically:

- If a later look measures `sigma` **below** 31.6915, the floor **does not
  fall**. 713 stands.
- If a later look measures `sigma` **above** 31.6915, the floor is **raised
  again** by this same formula, in a further dated amendment, written before that
  look declares anything.

## B5. What this does to the slope test and to the 0.40 threshold

The trigger is written against the level test, but `sigma_eps` enters the slope
test too and the floor is a single number serving both. The consequence must be
stated or the amendment is half-done.

The slope MDE is `always_valid_multiplier(G, tuning=300) * (sigma_eps/sigma_x) /
sqrt(G)`. The registration ASSUMED `sigma_eps / sigma_x = 2` and read
`MDE = 0.42` at `G = 300`, from which §6's NO-SIGNAL threshold of **0.40** was
set.

At the measured `sigma_eps = 29.7637` against the registration's assumed
`sigma_x = 10`, the ratio is **2.976** — between the registration's own `= 3`
column and its `= 2` column, and the `= 3` column already prints the answer:
**`MDE = 0.63` at `G = 300`.** The recomputed value at ratio 2.976 is **0.6283**.

**So at `G = 300` the design cannot resolve 0.40, the threshold NO SIGNAL is
tested against.** A NO SIGNAL declared there would be *"we looked with an
instrument too blunt to see it"* — the precise failure §A5.2 set the threshold
to prevent.

`sigma_x` is taken as the registered `10`, **not** the `40.98` the 2026-08-25 run
measured. The audit established that 40.98 is manufactured by rows with broken
fair values (`edge_tenths` from −717.97 to +372.60; `sd(edge)` is 107.8 inside
`too_few_books` and 10.90 outside it) and that CLAUDE.md rule 1 classifies those
as bugs until proven otherwise. Using 40.98 gives a ratio of 0.74 and an MDE of
0.078, which would *lower* the floor. That is the flattering direction and it is
refused. The clean measured `sigma_x = 10.90` gives ratio 2.73 and a slope floor
of 516; the registered 10 gives 2.976 and a slope floor of **591**.

```
solve  always_valid_multiplier(G, tuning=300) * 2.9764 / sqrt(G) = 0.40
G = 591:  3.2671 * 2.9764 / sqrt(591) = 9.724 / 24.310 = 0.4000
```

**591 < 713, so the level-test floor binds and no separate slope floor is
needed.** At `G = 713` the slope MDE is **0.357**, below the 0.40 threshold, and
**0.40 therefore stands unchanged.** The threshold is not moved; the floor is
moved until the threshold is again something the design can see. That is the
direction §A5.2 requires — the failure mode of a bad noise assumption must be
*permanent UNRESOLVED, never a false kill*.

## B6. What now governs

1. **§6, all four clauses**: every occurrence of `G >= 300` as the declaring
   floor now reads **`G >= 713`**. SIGNAL, BUG and NO SIGNAL may be declared only
   at a look with `G >= 713` on the modal-version population. Every look with
   `G < 713` is **UNRESOLVED** and may report point estimates and intervals only.
2. **§6's sentence** *"The 300 floor is not a significance threshold — the
   boundary handles that — it is the point below which the test cannot resolve
   any plausible value of `beta`"* is unchanged in meaning and now reads **713**.
   The reason it moved is that the noise came in larger than assumed, which is
   the one input that sentence is a function of.
3. **§7 stopping condition 3** now reads: *"the decision rule in §6 returns
   SIGNAL, BUG or NO SIGNAL at a look with `G >= 713`."* Conditions 1
   (`G = 1000`) and 2 (**2027-02-15**) are **unchanged**, and 713 is still below
   1000, so the stopping rule remains internally consistent.
4. **`always_valid_multiplier(G, tuning=300, alpha=0.05)` is UNCHANGED.**
   `tuning` is the boundary's mixture parameter, not the floor; it sets where the
   bound is most efficient and it appears in every interval this registration has
   ever published. Re-tuning it to 713 would silently restate the width of the
   2026-08-16 and 2026-08-25 intervals, which this amendment forbids. The
   boundary is valid at every `n` regardless of tuning; the only cost of leaving
   it at 300 is a slightly wider interval near 713, which is again the safe
   direction.
5. **§A9 gains two reportables.** At every look, alongside `sigma_eps`,
   `sigma_x` and `sd(half_spread)`, report **(i) `sd(clv_tenths)` on the
   modal-version population**, stating explicitly whether it exceeds 31.6915 —
   the ratchet check of §B4; and **(ii) the effective cluster count `G_eff`**
   (inverse Herfindahl on leverage) together with the largest single cluster's
   leverage share, per §B7. A look that does not print both lines has not
   checked the floor it is declaring against.
6. **This does not touch the gate.** `backend/gate.py`'s live-trading interlock
   counts 300 *actionable games* and is a different number, in a different
   document, for a different decision. It **stays exactly where it is**. Nothing
   in this amendment lowers, raises or bypasses it.

## B7. Nominal `G` may be the wrong unit, and raising the nominal floor does not fix that

**This is the more serious of the two open problems, and it is not softened.**

The 2026-08-25 audit measured, by inverse Herfindahl on leverage, that
**`G = 311` nominal is `4.26` effective clusters**: 2 games carry 50% of the
leverage on `beta`, 9 carry 90%, and one game — `KXWNBAGAME-26AUG24GSMIN` —
carries **43.80% alone**. WNBA is 45 of 311 clusters and **95.6% of the
leverage**.

The power check's formula assumes `G` equally-weighted independent clusters;
`sqrt(G)` is the right denominator only under that assumption. When leverage is
concentrated, the estimator's variance behaves like `sigma / sqrt(G_eff)`, and
`G_eff` is what the formula is actually a function of. **On the slope test the
observed `G_eff` is 4.26, at which the multiplier is 21.4 and the slope MDE is
about 32 — roughly eighty times the 0.40 threshold, and thirty times `beta = 1`,
the ceiling of plausibility.**

**Raising the nominal floor does not fix this, and saying otherwise would be the
flattering error.** Holding the observed concentration ratio
(`4.26 / 311 = 1.37%`) fixed:

```
nominal G required for G_eff = 300  ->  300 * 311 / 4.26  =  21,901 games
nominal G required for G_eff = 713  ->  713 * 311 / 4.26  =  52,052 games
```

At the pooled accrual rate observed between the two looks
(`(311 − 199) / 9 days = 12.4 clusters/day`), 52,052 clusters is **about eleven
years**, against a stopping rule that ends on **2027-02-15**. **If effective
clusters are the right unit, the declaring look on `beta` is unreachable under
this registration, and no floor written in nominal `G` makes it reachable.**

**Three things this section deliberately does not do.**

- **It does not change the unit.** Restating the floor in `G_eff` would be a new
  estimator with a new null, chosen after seeing that `G_eff` is small. That is
  the forbidden move and it is not made here. `G_eff` becomes a **mandatory
  reportable** (§B6(5)) so that a future declaration cannot be made without the
  number printed beside it. It does not become a threshold.
- **It does not drop the high-leverage rows.** The audit is explicit that
  *"dropping high-leverage clusters is not a registered cut"*, and it is right.
  The concentration comes from `too_few_books` / `no_market_width` rows whose
  fair values are broken — a consensus fair of about 8c against an 82c ask, off
  fewer than two books — and CLAUDE.md rule 1 says those are bugs, not edges.
  Excluding them now, after seeing that they carry the leverage, would be
  choosing the population from the answer.
- **It does not claim the level test is equally afflicted.** `G_eff = 4.26` is
  leverage on the **slope**, driven by the `edge_tenths` tail. The level test —
  §5's mean of game-clustered `clv_tenths` — has no regressor, and its cluster
  weights are not leverage in that sense. **Its effective-cluster count has never
  been measured.** Until it is (§B6(5)), the reachability of the *level* floor
  at `G = 713` is **unestablished, not established**. Assuming it is fine because
  it is a different statistic is exactly the assumption this document exists to
  refuse.

**The honest bottom line, stated because it is the deliverable.** The floor is
raised to 713 and 713 is reachable in nominal terms — roughly 32 days of pooled
accrual from the 2026-08-25 look, or 497 further modal-version clusters from
`G = 216`, well inside the 2027-02-15 stop **provided no config bump restarts
the modal population**. But reaching 713 nominal does **not** by itself make the
slope declaration meaningful, because the quantity that governs the slope's
resolving power is not the quantity the floor is written in. **The route out is
not a larger floor; it is a successor registration that fixes an `edge_tenths`
exclusion in advance** — this registration never contemplated a regressor running
to −717.97 tenths, and Amendment 1 §A2.2 added a price bound but no edge bound.
Until such a registration exists and accrues its own record from the moment of
registration, a `G = 713` declaration on `beta` should be read as a statement
about roughly four WNBA games.

## B8. Two defects deliberately left open, named here so they are not lost

Neither is fixed by this amendment. Both are recorded so that a future session
cannot reach the floor and believe the instrument is whole.

- **(a) §A4's leave-one-group-out downgrade is not implemented.**
  `verdict()` at `backend/analysis/signal_test.py:237-245` returns NO SIGNAL from
  the pooled fit alone; no registered group is computed and no leave-one-group-out
  recomputation exists. The 2026-08-25 auditor implemented it by hand and ran it:
  it does not fire (seven of thirteen groups testable, largest upper limit
  `+0.0286`). **So it has never changed an answer, and by this repo's own rule —
  a guard that has never fired is decoration — it is not known to work.** No
  declaration at `G >= 713` may be made until §A4 executes in code.
- **(b) The effective-cluster problem of §B7**, left unresolved by design.
  `G_eff` becomes a reportable, not a threshold, and the reason it cannot become
  a threshold here is that doing so would be a post-hoc estimator change.

## B9. What this amendment does not change, stated so the absence is deliberate

- **No past verdict.** 2026-08-16 (`beta_hat = −0.1412`, `G = 199`) and
  2026-08-25 (`beta_hat = −0.0756`, `G = 216` modal) were **UNRESOLVED** and
  remain so. The 2026-08-24 screen that displayed `NO SIGNAL, 311 of 300 games`
  was refused before this amendment and is refused by it twice over: wrong
  population, and now also below the floor.
- **No threshold.** 0.40 stands (§B5). `alpha = 0.05` stands. `tuning = 300`
  stands.
- **No population, no exclusion, no cut, no bucket edge, no cluster key.**
  §§1–5 are untouched.
- **Not the stopping date.** 2027-02-15 stands, and §B7 measures the amended
  floor against it rather than moving it.
- **Not the gate.** See §B6(6).
- **No code.** `backend/analysis/signal_test.py` is not edited by this
  amendment. The 713 constant, the §A4 branch and the new reportables are a
  separate lane — **ticket: raise `MIN_CLUSTERS_TO_DECLARE` from 300 to 713 at
  `backend/analysis/signal_test.py:72` (and the `G < 300` sentence in its module
  docstring, line 43), implement §A4's leave-one-group-out
  downgrade, and print `sd(clv_tenths)` (modal), `G_eff` and the largest
  cluster's leverage share on the headline line.** Until that lands the harness
  will keep declaring at 300, and **where the harness and this document disagree,
  this document governs.**

## B10. Registration record for this amendment

```
amendment          2
date               2026-08-29
trigger            power check, level-test section: sigma above 30 tenths
observed           sd(clv_tenths) = 30.1481 pooled / 31.6915 modal (2026-08-25)
formula            always_valid_multiplier(G, tuning=300, alpha=0.05) * sigma / sqrt(G) = 3.8
floor was          G >= 300
floor is           G >= 713   (modal-version population, per §P4 and §7)
threshold          0.40  UNCHANGED
tuning             300   UNCHANGED
past verdicts      UNCHANGED (UNRESOLVED, both looks)
open defects       A4 unimplemented; G_eff = 4.26 at nominal G = 311
sources            docs/measurements/2026-08-25-clv-signal-declaring-look-refused.md
                   docs/measurements/2026-08-16-clv-signal-test-interim-look.md
```
