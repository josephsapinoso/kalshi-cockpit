# Pre-registration — the devig-method calibration, and what the conservatism costs

**Written 2026-08-10.** Registered **jointly** with
`docs/measurements/2026-08-10-preregistration-fresh-odds-edge-distribution.md`
(committed `fed69d8`, "Lane A" below). The two share one alpha budget, one
bucket grid, one cluster key and one multiplicity count. **Lane A is amended by
this document** — see §M.

**Status: registered.**
**B1 and B2 are READY and are the powered half.** They need no outcomes.
**B3 — the five calibration curves — is UNDERPOWERED by four orders of
magnitude and that verdict is final, not provisional.** The arithmetic is in the
power check and it is the most valuable thing this document produces.

- Owner: `pre-registrar` (agent), on behalf of Joe.
- Scored against by: `measurement-skeptic`, after the run.
- Negative-result destination: fixed in §9, before the result exists.
- **This document cannot retire CLAUDE.md rule 2 and is written so that no
  number in it can be quoted as licence to.** See §8 and §9.

---

## §0. What had already been observed when this was written

Same disclosure standard as Lane A §0, and the same reason: the record has been
partly seen, so a reader must be able to judge what was knowable.

**[MEASURED FROM DATA — live, this session]**

```
recommendations   1529 rows; actionable 0 always; no_edge 614; suppressed 915
horizons          "0" 532   "1" 569   unscored 428
games             29 scored games, none actionable
outcomes          kalshi_markets.result: recorded_total 1601  (no 1039, yes 562)
                  pending 0, abandoned 0, too_new 1300, unreadable 219
model             model_probability NULL on every row; no decision path reads it
```

**Not seen by anyone:** any value of `p_multiplicative`, `p_additive`,
`p_power`, `p_shin` or `p_conservative`; any calibration gap; any join between
`recommendations` and `kalshi_markets.result`; the number of distinct games in
that join. **`G` for this measurement is unknown and is bounded above by
something small** — see the power check.

Every fee, devig, sizing and boundary number below is **[COMPUTED FROM CODE]**
by executing repository functions on inputs chosen here, or by closed-form
arithmetic stated in full. Provenance labels follow Lane A §0.5.

**Assumed inputs in this design: one** — `sigma`, the between-game SD of the
per-game conservatism cost, which appears only as a column of the power table
and gates no threshold. Grepped `docs/adr/**` and `docs/measurements/**`: no
measurement of that dispersion exists.

---

## §C. Corrections to the brief, made before the design was fixed

Five, and the third and fourth change the design rather than annotating it.

### C1. "1–2 percentage points" is the longshot end, not the typical value

The brief cites `tasks/lessons.md` for a devig-method spread of 1–2 points
against 0.38 points of headroom, and concludes the conservatism is *"eating
three to five times the edge being hunted."*

`core/suppression.py:217-220` is more specific, and it is the measurement the
lesson is compressing: **~0.18 points on an even moneyline and ~2.03 on a
longshot** **[quoted from code, itself citing a prior measurement of real
lines]**. The spread is strongly price-dependent, and at 50c it is **less than
half the headroom**, not three to five times it.

And the *cost* of the guard is not the spread. The spread is max − min; the
guard's cost relative to a neutral reference is **mean − min**, roughly half the
spread for four roughly symmetric readings. So:

| price region | method spread | guard cost ≈ spread/2 | vs 3.8 tenths headroom |
|---|---:|---:|---:|
| even moneyline | 0.18 pts = 1.8 tenths | ~0.9 tenths | **~0.24x** |
| longshot | 2.03 pts = 20.3 tenths | ~10.2 tenths | **~2.7x** |

**Consequence for the design:** a pooled cost number would average a region
where the guard is cheap with one where it dominates, and the pooled figure
would describe neither. **The cost is reported per price bucket first and pooled
second**, and the pooled figure may not be quoted without the per-bucket view
beside it — the repo's rule that a pooled number is not a finding until the
parts agree.

### C2. `p_conservative` is not a fifth method; it is a selection rule

`devig.conservative_probability` returns `min` across the four methods **for the
outcome being bought** **[COMPUTED FROM CODE]**, and `runner.write_fair_price`
stores that min in `p_conservative` on the same row as the four inputs. So there
are **four estimators and one selection**, and which method the selection lands
on varies row by row.

This matters because **the min of four estimators is biased low relative to
their centre by construction**, even if all four were individually unbiased. So
the question *"is `p_conservative` systematically below the alternatives"* has a
known answer — yes, necessarily — and a registration that tested it would be
testing an operator, not the world. **That test is not registered.** What is
registered is the **magnitude** (B1) and whether the magnitude is **binding on
the pipeline's output** (B2).

An invariant follows and is asserted before any statistic is computed:
`p_conservative == min(p_multiplicative, p_additive, p_power, p_shin)` on every
row. If it fails anywhere, the design is void and this document is amended.
`p_shin` may be `None` where the root-finder fell back
(`devig.py:181`); rows with any NULL among the four are **dropped and counted,
never imputed**.

### C3. Brier and log-score comparisons are second-order in the effect, and 4x weaker

The obvious design — score all five forecasts against outcomes and compare — is
the wrong instrument, and this is computable in advance.

For two forecasts differing by `d` on the **same** outcomes, the per-observation
Brier difference has mean `d²` and standard deviation `2d·sqrt(p(1−p))`
**[COMPUTED FROM CODE — closed form, checked against a 400,000-draw Monte Carlo
which agrees to within its own error]**. The signal is second-order in `d` and
the noise is first-order, so the required sample is `16p(1−p)/d²`. The
**calibration gap** — actual minus implied — is first-order in `d` and requires
`4p(1−p)/gap²`, which is **exactly 4x smaller**.

**Registered: the outcome-based statistic is the calibration gap (B3), not a
proper score.** Choosing Brier would have quadrupled the required `n` for no
gain. Both are hopeless at this record's size (power check) — but the
registration should not also be wrong about which instrument is sharper.

### C4. The (a)/(b) separation the brief asks for cannot be made by outcomes at any reachable `n`

The brief's framing is that calibration *"is the only thing that separates (a)
from (b)"*. That is the part I had to correct, and it is the reason this
document is shaped the way it is.

**[COMPUTED FROM CODE — closed form]** games required for a two-standard-error
fixed-sample calibration test, which is the *optimistic* floor before any
always-valid correction:

| gap to resolve | `G` at p=0.50 | `G` at p=0.25 |
|---|---:|---:|
| **0.38 pts** (the venue's entire headroom) | **69,252** | 51,939 |
| 1.0 pts | 10,000 | 7,500 |
| 2.0 pts (the longshot method spread) | 2,500 | 1,875 |
| 5.0 pts | 400 | 300 |
| 10.0 pts | 100 | 75 |

Against a record holding **29 scored games**. Under the always-valid boundary
these numbers rise by roughly a further 6x, and the joint alpha allocation (§M)
raises them again.

**So no calibration measurement this project can run will ever adjudicate which
devig method is right.** That is not a statement about effort or patience; it is
`4p(1−p)/gap²` with a gap the size of the thing being hunted.

**But (a) and (b) can still be separated — deterministically, with no outcomes
at all.** If the strategy's ask sits above even the **most generous** of the four
methods, then no choice of devig method would have produced an actionable row,
and (b) is refuted at `n` = the entire record with zero sampling error. That
counterfactual is B2, it costs nothing, and it is the same shape as Lane A's
fee-model flip count. **The two lanes together bracket the question: Lane A asks
whether the fee model can reach the bar; this lane asks whether the devig choice
can.**

### C5. `mart_calibration` cannot be reused, and neither can `mart_multiple_comparisons`

The brief is right that `mart_calibration` joins settlements read from parquet
built `FROM orders`, of which live has zero. Two further reasons it is not the
harness here, both structural:

- **The warehouse does not run on live.** `warehouse/` is not in the Dockerfile
  and `/api/dashboards` returns 503 (`tasks/NEXT.md`, `partner`'s kill list).
  This measurement is a Python module behind a route, the way `/api/gate` works.
- **`mart_multiple_comparisons` cannot count these two registrations.** It
  counts warehouse marts only, and says in its own source that it deliberately
  excludes `gate.py` and `analysis/validate.py`.
  `tasks/audit-2026-08-07.md` item 7 records that it undercounts — the p-value
  is monotone in `n_tests`, so undercounting flatters. **Registered: the
  project-wide test count lives in §M of this document and in Lane A §7, and if
  the warehouse is ever run its counter must not be read as the project-wide
  number.**

The mart's *statistical* choices are reused verbatim and gratefully: the
standard error **under the null at the implied rate, not the observed one**
(a two-market cell produced a 74-point "finding" the other way), the
`MIN_EXPECTED_PER_SIDE = 5` validity gate, and the three-column censoring that
stops a reader reconstructing a suppressed gap by subtraction.

---

## §P. Prerequisites — checked before anything runs

- **P1 — full-table access.** Same block as Lane A: `/api/ledger` caps at
  `limit <= 1000` against 1,529 rows with no `offset`, and **no route exposes
  `fair_prices` or `kalshi_markets.result` at all** — the eleven `/api/*` GETs
  do not include them. So B1, B2 and B3 all require either a new route (a
  deploy) or a direct read of the volume. **Nothing in this document can be run
  over HTTP today, not even the composition print.** That is a stronger block
  than Lane A's and it is stated rather than worked around.
- **P2 — the invariant of §C2 holds** on every joined row:
  `p_conservative == min(four)`, and `fair_probability == p_conservative` on the
  row `fair_price_id` points at. Both are equalities the code should make
  necessary; if either fails, the join is wrong and no statistic is computed.
- **P3 — `fair_price_id` is non-NULL** on the analysed rows. It is nullable in
  the schema. Report the NULL count; those rows are dropped and counted.
- **P4 — outcome coverage is reported before any rate**: joined rows with a
  non-NULL `result`, rows whose market is still open, and rows whose market
  resolved unreadable. **[MEASURED]** 219 of 1,820 resolved markets — 12% — are
  `finalized` with no readable outcome, cause unexplained, and their absence is
  not random. If readable coverage over the joined population is below 0.80, B3
  does not run and B1/B2 (which need no outcomes) run unaffected.

---

## §1. The question, as a claim that could be false

**Primary, B2 — deterministic, one-sided, no outcomes required:**

> Among fresh-odds rows, **no** choice among the four stored devig methods would
> have produced an actionable row that `p_conservative` did not — the Kalshi ask
> is at or above the **most generous** of the four, on every row, in every game.

That is a universal claim and it is registered as one deliberately, because it
is the one this measurement can settle exactly. **It is falsified by a single
counterexample**, which is the correct standard for a claim of that shape.
(Lane A's §7 warns against universals in a *hypothesis*; here the universal is
the claim being tested, not an assumption being smuggled in, and a single row
refutes it.)

**Primary, B1 — deterministic, two-sided:**

> The conservatism cost — the mean over games of `(p_ref − p_conservative)`
> expressed in tenths of a cent of post-fee edge — is **below 3.8 tenths**, the
> venue's entire taker headroom, in each price bucket.

`p_ref` is fixed here as the **mean of the four methods**, with `max` reported
beside it as the upper bracket. The mean is the neutral reference; the max is
the most favourable one an advocate for relaxing the guard could use, and
registering both removes the freedom to pick after the fact.

**Secondary, B3 — outcome-based, and registered as unresolvable:**

> Each of the five probability series is calibrated: within each bucket, the
> realised rate equals the implied rate.

Registered so the curves exist and are honest, **not** because they can decide
anything. See the power check.

---

## §2. The population and the join

### The population

Every row of `recommendations` satisfying **Lane A's §2 predicate, verbatim** —
same freshness rule, same price bound, same `instr`-delimited composite
handling:

```sql
  AND r.entry_ask_tenths BETWEEN 10 AND 989
  AND r.fair_probability IS NOT NULL
  AND (r.suppressed_reason IS NULL
       OR instr(',' || r.suppressed_reason || ',', ',stale_odds,') = 0)
```

**Reused rather than restated**, so the two lanes describe the same rows and
cannot drift apart. The composite hazard is the same one: a `NOT IN` predicate
retains `'stale_odds,wide_market'`, and 27.8% of stale rows are composites
**[MEASURED]**. That was defect D1 of Amendment 1 to the CLV registration.

Plus, for B3 only: a non-NULL `kalshi_markets.result`.

### The join, in full

```sql
SELECT
  COALESCE(m.event_ticker, r.ticker)              AS cluster_key,
  r.ticker, r.side, r.created_ms, r.entry_ask_tenths,
  r.fair_probability, r.fair_price_id, r.suppressed_reason,
  f.p_multiplicative, f.p_additive, f.p_power, f.p_shin, f.p_conservative,
  f.market, f.outcome_name, f.book_count, f.market_width, f.overround,
  f.anchored_on_sharp, f.computed_ms,
  m.result,
  CASE WHEN m.result IS NULL THEN NULL
       WHEN m.result = r.side THEN 1 ELSE 0 END   AS won
FROM recommendations r
JOIN      fair_prices    f ON f.id = r.fair_price_id
LEFT JOIN kalshi_markets m ON m.ticker = r.ticker
WHERE <Lane A §2 predicate>;
```

- **`won = (result = side)`**, the convention `mart_calibration.sql` uses and the
  one `engine.py:119` establishes: `fair_probability` is
  `conservative_probability(candidate.outcome_name)`, i.e. P(**the side taken**
  wins), not P(yes). `kalshi_markets.result` is `'yes' | 'no'`
  **[COMPUTED FROM CODE — `schema.sql:130`]**.
- **`fair_prices` is one row per outcome**, carrying all four methods **for that
  outcome** **[COMPUTED FROM CODE — `runner.write_fair_price`, whose docstring
  says why: "the lowest for one team is not one minus the lowest for the
  other"]**. So the four alternatives sit on the row `fair_price_id` already
  points at. No second join and no index arithmetic.
- **`market` is `h2h` for the entire record** — `write_fair_price` defaults to
  `MONEYLINE` and nothing else calls it. Registered as a **printed check**, not
  an assumption: if any other value appears, the population is stratified by it
  and the write-up says so.

### When each price was observed relative to when the outcome became known

Required by the brief, and there is a real limitation to record.

- `fair_probability` and the four methods are stamped `computed_ms`, and the
  recommendation `created_ms`, both **pre-game** — the sweep schedule places
  them before kickoff and `no_commence_time` / `commence_skew` suppress rows
  where that could not be checked. So the forecast provably precedes the
  outcome.
- **`kalshi_markets.result` has no timestamp.** `market_results.py` says so in
  its own docstring: *"It does not date the writes. `record_result` stamps
  `last_seen_ms`, but so does every discovery upsert, so that column cannot say
  when an outcome was recorded."* The ordering therefore rests on the market
  lifecycle and on `created_ms`, **not** on a recorded ordering.
- **No price observed at or after settlement enters any statistic.**
  `last_price` on a settled market has already converged on the outcome and is
  not read anywhere in this design; nor is the closing line, nor `clv_tenths`.
  The only outcome-adjacent column is `result` itself.

### The usable window — and a correction to the brief

The brief says outcomes accrue forward only from the 2026-08-09 deploy. Almost:
the result pass queries markets between `min_age_after_commence_s` (2h) and
`max_age_after_commence_s`, whose code default is **7 days**
**[COMPUTED FROM CODE — `config.py:410`; unset on live, so the default
applies]**. So the pass could reach back **7 days before the deploy**, and games
commencing from roughly **2026-08-02** onward are eligible — not only those
after 2026-08-09.

**Registered consequence:** the eligible-commence window is a stratum, printed,
with the count of joined games whose commence time falls in the retro week
versus after the deploy. And the loss remains rolling: one day of outcomes per
day, permanently, if the pass ever breaks. `abandoned_total` is currently 0
**[MEASURED]**.

---

## §3. The sampling frame and its strata

**The frame is the whole joined table, not a draw from it.** No sampling and no
ordering — the same construction that removes Lane A's discovery-order scar,
where a measurement fixed its analysis and not its frame, drew twenty rows in
discovery order, filled entirely from one stratum, and transferred the interval
to a population that was 66% the other.

**The composition is printed before any rate.** Not beside it, before it.

| Stratum | Levels | Expected share | Provenance |
|---|---|---|---|
| Outcome coverage | resolved / open / unreadable | 12% unreadable of resolved | **[MEASURED — §0]** |
| Commence window | retro-week / post-deploy | unknown | Never measured |
| League | ticker series prefix (Lane A §C3) | unknown | Never measured |
| Bankroll era | pre / boundary / post (Lane A §3 epochs) | unknown | Never measured |
| `book_count` | 1 / 2 / 3+ | unknown | Never measured; drives the method spread |
| `anchored_on_sharp` | 0 / 1 | unknown | Never measured |
| Market type | `h2h` / other | expected 100% `h2h` | **[COMPUTED FROM CODE]** |
| `strategy_config_version` | integer | unknown | More than one value means a mixture |

`book_count` earns its place: with one book the four methods still differ, but
`market_width` is `None` by construction (`consensus_devig` returns `None`
rather than 0.0 for a single book, deliberately), so the single-book stratum is
the one where the consensus is least evidenced and the guard's cost is least
comparable. It is printed and it is a mandatory sensitivity group (§6).

---

## §4. The unit of observation

**The unit is the game.** Cluster key is Lane A's, verbatim:
`COALESCE(kalshi_markets.event_ticker, recommendations.ticker)`, with the same
HTTP fallback and the same two registered defects (series-prefix splitting,
stored-vs-derived disagreement).

**But clustering alone is not enough here, and this is the sharpest `n` trap in
the design.** `engine.persist_if_changed` writes a new row whenever the ask or
the fair value moves, so one `(game, market, side)` accumulates many rows across
a slate — and every one of them is a forecast of **the same single coin flip**.
Counting them as separate calibration observations is
*one-observation-recorded-thirty-times* in its purest form: it would shrink the
binomial standard error by `sqrt(k)` for evidence that never grew.

**Registered collapse rule, fixed in advance:**

1. Rows are collapsed to one observation per **`(ticker, side)`** — one market,
   one side, one outcome.
2. The retained forecast is the row with the **greatest `created_ms`** for that
   pair: the last pre-game reading, the analogue of ADR 0011's closing anchor.
3. Those observations are then **clustered by game**, because a game's markets
   resolve from one final score.
4. **Sensitivity, mandatory:** the whole analysis is re-run retaining the
   **earliest** row instead. A verdict that flips is downgraded to UNRESOLVED,
   naming the collapse rule as the cause. "Last" is defensible and so is
   "first"; registering only one of them would leave the choice available after
   the fact.

**Printed always: `n_rows`, `n_observations` (after collapse), `n_clusters`, and
the rows-per-observation and observations-per-cluster distributions.** The brief
requires the row/game ratio and it is not optional: 1,601 outcomes is not 1,601
independent observations, and neither is 1,529 rows.

**Both sides of one market are the same coin flip, inverted.** They may both
appear — a calibration curve conventionally includes both — but they are
perfectly anti-correlated, so they are never counted as two, and the game-level
cluster is what carries the standard error.

**Fewer than 2 clusters returns `None`, never a number.**

---

## §5. The bucketing, fixed in advance

The brief asks which variable buckets and why, and whether the same edges serve
all five curves. Both are answered here and neither is left open.

### The edges

**One edge set for everything in both lanes:** `analysis.validate.BUCKETS`
verbatim — ten cells, `(10,100) (100,200) … (900,990)` in tenths — reused so it
cannot be re-chosen, and identical to Lane A's Grid B so the two documents are
commensurable. A probability maps onto the same edges as `p × 1000`.

### Which variable buckets, and why it is two different variables

CLAUDE.md's rule is to bucket by the price actually payable, never the mid.
That rule is about **money**, and it is kept for every money-flavoured quantity.
But a calibration curve is a statement about a **forecast**, and bucketing a
forecast by someone else's price answers a different question. So:

| Statistic | Buckets on | Why |
|---|---|---|
| **B1** (guard cost) | `entry_ask_tenths` — the derived ask | It is a cost in edge, i.e. money. CLAUDE.md's rule applies directly. A bucket in the predecessor showed +25.4 points and lost money for exactly this reason. |
| **B2** (counterfactual actionable) | `entry_ask_tenths` | Same — and it must share Lane A's frame, since Lane A's fee-model flip is the other axis of the same grid. |
| **B3-common** (the comparative curve) | `entry_ask_tenths` | **All five curves on identical row membership.** This is what makes the five comparable at all: same games, same cells, same denominators. |
| **B3-self** (calibration proper) | each method's **own** probability | This is what "calibration" means: P(win \| forecast = x) against x. Cells differ in membership across methods, so these five curves are **not** comparable to each other and may not be differenced. |

**Both B3 views are registered and they have different standing.** B3-common
carries the comparative claim; B3-self is the honest calibration picture and is
descriptive only. Registering only one of them would have left the other
available to be produced after the first disappointed.

**No other cut.** Not by league, not by day, not by side, not by book count as a
*finding* (it is a sensitivity, §6), not by re-deriving the edges at a different
size. Each is defensible and that is the problem.

---

## §6. The statistics, named as estimators

| # | Quantity | Estimator | Null | Standing |
|---|---|---|---|---|
| **B1** | conservatism cost, tenths | **a mean of game-clustered per-observation differences** | `3.8` tenths (the headroom), two-sided | **PRIMARY.** One always-valid interval test. |
| **B2** | counterfactual actionable games | **a count of clusters** | none — deterministic | **PRIMARY.** No alpha. |
| **B3** | calibration gap per cell | **a difference between a proportion and a known constant** | the implied rate, **SE computed under the null** | Secondary. Declares nothing below its floor. |
| — | pooled B3 gap | as above, pooled | implied rate | One reserved alpha slot (§M), unusable at foreseeable `G`. |

### B1 — the cost, defined without ambiguity

Per retained observation, at a **fixed size of one contract**, using Lane A §6's
recomputation rule so the two lanes are on one scale:

```python
E1(p) = core.ev.edge_after_fees_tenths(ask_tenths=entry_ask_tenths,
                                       contracts=1, fair_probability=p,
                                       maker=False)
cost_mean = E1(mean(four)) - E1(p_conservative)     # = (mean - min) * 1000
cost_max  = E1(max(four))  - E1(p_conservative)     # = (max  - min) * 1000
```

The fee cancels in the difference, so `cost` is exactly the probability
difference in tenths — which is an assertable invariant, not a hope, and it is
checked. **The stored `edge_tenths` column is not used for anything**, for the
reason Lane A §6 gives: it is a per-contract edge at a size the row does not
record, with steps up to 5.0 tenths and a non-monotone segment.

Standard errors are **cluster-robust**, `gate._cluster_robust_stderr` reused,
with the same two invariants asserted before any result is believed: singleton
clusters reproduce the classical error exactly, and duplicating every
observation `k` times leaves the mean and the error bit-identical.

### B2 — the counterfactual, defined so it cannot be quietly widened

For each `p` in {`p_conservative`, `p_multiplicative`, `p_additive`, `p_power`,
`p_shin`, `mean(four)`, `max(four)`} and each fee model in {maximum-of-models
(deployed), Model-B-only (the cheapest candidate)}:

count the **clusters** containing at least one row that

- carries **no** suppression code, **and**
- returns `contracts >= 1` from
  `size_position(..., risk=RiskConfig().reference(), current_exposure_dollars=0.0)`
  under that `p` and that fee model.

**[COMPUTED FROM CODE]** at the reference profile a post-fee edge of **0.1
tenths** already yields one contract at every price from 20c to 80c, so this
count is equivalent to "the ask sits below `p` net of fees" — the same identity
Lane A §0.3 rests on.

Three registered protections:

- **The whole 7 × 2 grid is printed. No cell may be quoted alone.** A maximum
  over fourteen deterministic cells is not a finding about any one of them.
- **`suspicious_edge` and `edge_within_method_noise` are thresholds on the
  stored, conservative edge**, so a row carrying only those codes might not
  carry them under a different `p`. Those rows are counted as
  **`indeterminate`**, separately, and are neither flips nor non-flips. Same
  rule as Lane A §6, same reason: registering it now stops them being swept into
  whichever column suits.
- **A counterfactual is arithmetic about the record, not a forecast.** It says a
  row *would have been* actionable. It does not say the bet would have filled,
  or won.

### B3 — the curves, with the null-rate standard error

Per cell: `n_observations`, `n_clusters`, `implied = mean(p)`,
`actual = mean(won)`, `gap = (actual − implied) × 100` in points, and **two**
standard errors:

- `se_binomial = 100 · sqrt(implied(1−implied) / n_observations)` — **under the
  null, at the implied rate, never the observed one.** Using the observed rate
  makes an extreme result look more certain because it is extreme; that is what
  let a two-market cell produce a 74-point "finding".
- `se_cluster` — the same quantity computed over game clusters.

**The larger of the two governs, always.** The binomial form assumes independent
observations, and §4 has just finished explaining that they are not. Report the
implied design effect `(se_cluster / se_binomial)²` beside them: it is the
number that says how much of the apparent `n` is real.

`MIN_EXPECTED_PER_SIDE = 5` on **both** sides gates the normal approximation,
and below it the cell renders `(noise)` in **three** columns — gap, actual rate
and any P&L — because suppressing only the gap hands the reader the subtraction.
`implied` is not censored: it is a known input, true whatever happens next.

---

## §7. The decision rule, verbatim

> Let `m = always_valid_multiplier(G, tuning=300, alpha=0.0167)` — the joint
> allocation of §M — `se` the cluster-robust standard error, and the
> always-valid interval `[x − m·se, x + m·se]`. `G` is **games**, after the §4
> collapse, never rows.
>
> **All branches are evaluated at every look and all are reported.**
>
> ---
>
> **BRANCH (a) — THE RULER IS STRAIGHT ENOUGH; KALSHI IS THE BINDING FACT.**
> Declared if and only if **every** cell of the B2 grid outside the
> Model-B-only column is **zero** — no devig method, however generous, would
> have produced a single actionable game — **and** `indeterminate` is zero or
> is itself smaller than one game.
> Reading: the ask sits at or above the most generous of four fair estimates on
> every row in the record. `actionable = 0` is then **not** an artifact of rule
> 2, and CLAUDE.md's premise — *Kalshi's advantage is cost, not information* —
> has returned the answer it warned was likely.
>
> **BRANCH (b) — THE CONSERVATISM IS BINDING ON THE PIPELINE.**
> Declared if and only if some non-`p_conservative` cell of the B2 grid is
> `>= 1`. The write-up must name the method, the cell, the game count, and the
> `indeterminate` count on the same line.
> **This declaration establishes that the guard is binding. It does not
> establish that the guard is wrong.** See §8.
>
> **BRANCH COST — WHAT THE GUARD COSTS, INDEPENDENT OF BOTH.**
> Reported at every look, per price bucket and pooled, in tenths:
> `cost_mean` and `cost_max`, each with its always-valid interval.
> **Declared ABOVE HEADROOM** in a bucket if and only if the always-valid
> **lower** limit of `cost_mean` in that bucket exceeds **3.8 tenths**.
> **Declared BELOW HEADROOM** if and only if the always-valid **upper** limit is
> below 3.8 tenths. Otherwise UNRESOLVED for that bucket.
> The pooled figure may not be reported without the per-bucket table beside it
> (§C1), and the largest bucket's share of observations is printed on the same
> line as the pooled number.
>
> **BRANCH B3 — CALIBRATION.**
> **No B3 cell, and no pooled B3 statistic, may declare anything unless its own
> `G` exceeds the value the power check gives for the gap it is reporting.**
> **[COMPUTED FROM CODE]** that floor is `G >= 400` games to resolve a 5-point
> gap at p = 0.50 at two standard errors, and larger at every finer gap and
> under the always-valid boundary. Below it, B3 prints intervals and `(noise)`
> and its verdict is **UNRESOLVED — cannot resolve**, in those words, with the
> required `G` printed beside the achieved `G`.
> B3 **cannot upgrade or downgrade** branch (a) or branch (b). It is not on the
> critical path and was never able to be.
>
> ---
>
> **THE SENSITIVITY THAT CAN DOWNGRADE AND NEVER UPGRADE.**
> Every declaration is recomputed on each reduced population where the reduction
> leaves `G >= 100`: (i) the earliest-row collapse instead of the latest (§4);
> (ii) excluding `book_count = 1`; (iii) excluding rows carrying
> `stale_kalshi_quote`; (iv) excluding the `boundary` bankroll era; (v) leaving
> out each price bucket in turn; (vi) retro-week versus post-deploy commence.
> **If any recomputation reverses a declaration, that branch is downgraded to
> UNRESOLVED and the write-up names the reduction, in those words.** Strictly
> one-way. Reductions leaving `G < 100` are not tested and are not grounds for
> downgrade; their share is printed, and if any exceeds 0.50 the write-up must
> state that **the pooled result is one group's result**.
>
> **NO DESCRIPTIVE CELL MAY PRODUCE A FINDING IN EITHER LANE.** See §M: across
> both documents, chance alone produces about 4.7 "significant" descriptive
> cells at two standard errors, and at least one with probability 0.99.

---

## §8. What this measurement cannot be used to do

Registered as a rule, not as a caveat, because the brief is explicit and
`partner` repeated it.

**Nothing in this document can retire CLAUDE.md rule 2.**

The mechanism is arithmetic, not policy. Retiring the worst-of-four rule
requires knowing that some other reading is **closer to the truth**, and §C4
establishes — before any data — that establishing this needs on the order of
10,000 to 69,000 games for the gaps in question, against a record of 29. **The
benefit side of the trade is unmeasurable at this `n` and will remain so.** So
the most this measurement can produce is:

- the **cost** of the guard, measured (B1); and
- whether the cost is **binding** on the pipeline's output (B2); and
- a proof that the **benefit** cannot be measured here (the power check).

A decision to change rule 2 on that basis would be a **decision-theoretic** one
about asymmetric loss — an understated fee corrupts the measurement record while
an overstated one costs a bet, and `core/fees.py` says the asymmetry "is not
close" — taken by Joe, in an ADR, with the cost number attached. It would not be
an empirical finding, and this document must not be cited as one.

**Two sentences that are different acts, and only the first is licensed here:**
*measure what the guard costs against outcomes*, and *relax the guard because it
fires too often*. **Registered: any write-up derived from this document that
recommends relaxing rule 2 without an outcome-based benefit estimate is invalid
on its face, and the reason is printed in the harness's own output** (§S2 item
10), so it travels with the numbers rather than living in a document nobody
re-reads.

---

## §9. Falsification, destination, and consequences

**Falsified by:** branch (a) is falsified by one counterexample row in the B2
grid. Branch (b) is falsified by an all-zero grid. BRANCH COST is falsified in
either direction by its always-valid interval. B3 is falsified only above its
`G` floor, which it will not reach.

**The destination, fixed now:**

```
docs/measurements/<run-date>-devig-method-calibration-result.md
```

One file, **written whichever way it comes out**, that exact stem, this document
linked from its first line. Only the date varies.

| Verdict | What is built | What is killed |
|---|---|---|
| **(a) declared** | The finding is written up beside Lane A's: the ask sits above even the most generous fair, so `actionable = 0` survives the removal of the guard. This is the strongest form of "the premise is refuted" the project can produce, and it is deterministic. | The devig-method line entirely. No further work on method selection, no calibration harness, no ADR to relax rule 2. **And it retires the (b) hypothesis for good**, so no future session re-derives it. |
| **(b) declared** | An ADR proposing a rule-2 change, carrying: the cost number, the binding cell, and §8's statement that the benefit is unmeasurable. Joe decides. | Nothing automatically. |
| **COST above headroom in the middle band** | The cost enters the fee-calibration decision as a second term: the guard and the fee-model hedge are two conservatisms stacked, and their sum is what the strategy is fighting. | The belief that the 0.38-point headroom is the whole budget. |
| **COST below headroom everywhere** | Nothing. The guard is cheap and the argument in §C1 that it costs 3–5x the edge is retired with a number. | The "conservatism is eating the edge" hypothesis. |
| **B3 UNRESOLVED at the stopping rule** (expected) | Nothing. The required `G` is published so no future session re-proposes it. | **The whole calibration lane**, permanently, on arithmetic rather than on disappointment. |

**This is decision-relevant in every branch**, and the branch most likely to
matter — B3 unresolvable — kills a lane before it is built, which is the
cheapest kind of result this project can buy.

---

## §10. What this measurement cannot establish

Written now, because caveats written afterwards are selected to be survivable.

- **It cannot say which devig method is right.** §C4. Not at 29 games, not at
  300, not at 3,000.
- **It cannot say `fair_probability` is calibrated**, in either direction. A B3
  cell that fails to clear a threshold is not evidence of calibration; it is
  evidence of `n`.
- **B2 is a counterfactual over a pipeline, not over a market.** It re-runs
  `size_position` with a different probability. It does not re-run suppression,
  which was evaluated against the conservative edge — that is what the
  `indeterminate` count exists to bound, and the bound is a count, not a
  correction.
- **The four methods are not independent readings.** They are four
  normalisations of one set of book prices, so their spread understates the true
  uncertainty in the fair line, and the `max` bracket is not an upper bound on
  the truth. A fifth method, or a different book set, could sit outside all four.
- **`p_shin` may be a fallback rather than a solution.** `devig.py:181` falls
  back to the `z → 0` limit when the root-finder finds no root, and **nothing
  records that it did**. Rows where Shin silently degenerated are
  indistinguishable from rows where it converged, and Shin is one of the four
  the min is taken over. This is not correctable from the record.
- **12% of resolved markets have no readable outcome** and the cause is
  unexplained (`tasks/NEXT.md`: 802 settled markets parse 100% readable, and the
  mid-settlement hypothesis was refuted by age bucketing). Their absence is not
  random and the direction is unknown.
- **`result` is undated.** §2. The forecast-precedes-outcome ordering rests on
  the market lifecycle, not on a recorded timestamp.
- **The record is moneyline only** and one August slate — MLB and WNBA, NFL
  preseason out of scope. Nothing here transfers to spreads, totals, NBA, NCAAF
  or in-play, and the method spread is known to be strongly price-dependent, so
  a different price mix is a different cost.
- **`market_width` is `None` for single-book consensus by design**, so the
  stratum where the fair line is least evidenced is the one where the width
  diagnostic is absent. Printed, not corrected.
- **The always-valid boundary assumes clusters are independent and identically
  distributed.** One sportsbook feed degrading across a whole slate violates it
  in exactly the way that would move every method together.
- **Nothing here is evidence about the fee model.** That is four real fills and
  nothing else.

---

## The power check

### The powered half

**B1 and B2 need no outcomes at all.** B2 has no sampling error whatsoever — it
is a deterministic recomputation over the whole record, and its answer is exact
at whatever `G` exists. B1's uncertainty is only "would other games look like
these", and its detectable effect at the joint alpha is:

**[COMPUTED FROM CODE — `always_valid_multiplier(G, tuning=300, alpha=0.0167)`]**

| `G` | multiplier | σ=5 | σ=10 | σ=20 | σ=30 |
|---:|---:|---:|---:|---:|---:|
| 29 | 9.69 | 9.0 | 18.0 | 36.0 | 54.0 |
| 60 | 7.09 | 4.6 | 9.2 | 18.3 | 27.5 |
| 100 | 5.82 | 2.9 | 5.8 | 11.7 | 17.5 |
| 200 | 4.66 | 1.7 | 3.3 | 6.6 | 9.9 |
| 300 | 4.22 | 1.2 | 2.4 | 4.9 | 7.3 |

Games required for a half-width at or below 3.8 tenths — the headroom, which is
B1's threshold: **74 / 168 / 428 / 811** at σ = 5 / 10 / 20 / 30. So B1 is
answerable in the low hundreds of games if σ is modest, and the σ column is a
required print before the estimate (§S2).

### The unpowered half, and this is the deliverable

**[COMPUTED FROM CODE — closed form, `4p(1−p)/gap²` for a calibration gap and
`16p(1−p)/d²` for a paired proper score, the latter checked against a
400,000-draw Monte Carlo]**

| To resolve | calibration gap, `G` @ 2 SE | paired Brier, `G` @ 2 SE |
|---|---:|---:|
| 0.38 points (the headroom) | **69,252** | 277,008 |
| 1.0 points | 10,000 | 40,000 |
| 2.0 points (longshot method spread) | 2,500 | 10,000 |
| 5.0 points | 400 | 1,600 |
| 10.0 points | 100 | 400 |

at p = 0.50; at p = 0.25 each is 25% smaller. These are **fixed-sample two
standard errors** — the most optimistic framing available. The always-valid
boundary this project uses multiplies them by roughly `(m/2)²`, about **6x** at
G = 300, and the joint alpha allocation raises them further.

Against **29 scored games**, and a `G` for this join that is unknown but cannot
exceed the number of distinct games in 1,529 rows.

**Verdict: B3 is underpowered by roughly four orders of magnitude for the
question it would have to answer, and by roughly one to two orders even for a
gross 5-point miscalibration.** This is ADR 0016's habit reproduced: the verdict
is free, it is knowable before any resource is committed, and it says do not
build the harness for the curve — build it for B1 and B2, which answer the
decision-relevant question deterministically.

**Overall verdict: B1 and B2 READY (blocked only on P1 access). B3 UNDERPOWERED,
permanently, and registered as such before it could return a number that got
quoted.**

---

## §M. Joint multiplicity across both registrations

This section is the reason one agent wrote both documents, and it **amends Lane
A**.

### The combined count

| Family | Document | Cells | Standing |
|---|---|---:|---|
| `M`, the fresh-odds edge centre | Lane A §7 | **1** | alpha-carrying interval test |
| `B1`, the conservatism cost | here | **1** | alpha-carrying interval test |
| `B3` pooled calibration gap | here | **1** | alpha-carrying, reserved, unusable at foreseeable `G` |
| Lane A branch A flip count | Lane A | 1 | deterministic, no alpha |
| B2 counterfactual grid | here | 14 | deterministic, no alpha, whole grid printed |
| Lane A descriptive cells | Lane A §7 | 37 | descriptive |
| B3-common curves (5 × 10) | here | 50 | descriptive |
| B3-self curves (5 × 10) | here | 50 | descriptive |
| B1 per-bucket views | here | 10 | descriptive |
| strata prints (era, book_count, window, market type) | here | 9 | descriptive |

**Alpha-carrying interval tests, project-wide: 3.**
**Descriptive cells, project-wide: 37 + 50 + 50 + 10 + 9 = 156.**

**[COMPUTED]** at the conventional two-standard-error rule, 156 descriptive
cells give `156 × 0.0455 = 7.10` expected false findings and at least one clears
by chance with probability `1 − 0.9545^156 = 0.9993`. **Effectively certain.**

That is a larger number than either document reaches alone — Lane A's own count
was 37 cells, 1.68 expected, 82% — and it is the whole point of counting
jointly. The predecessor's 1,190 cells produced "dozens of significant results";
156 is the same failure at a smaller scale, and it is fatal to any
cell-by-cell reading.

**Registered, in both documents: no descriptive cell may produce a finding, in
either lane, at any `n`.** Only the three alpha-carrying tests can, plus the
deterministic counts, which carry no alpha because they are arithmetic rather
than inference.

### The allocation

Family-wise 0.05 across the project, Bonferroni across the three interval tests:

```
alpha per interval test = 0.05 / 3 = 0.01667
```

applied as `gate.always_valid_multiplier(G, tuning=300, alpha=0.0167)` in both
documents. Bonferroni rather than anything sharper because the three tests are
on different populations with unknown dependence, and a sharper correction would
require assuming a dependence structure nobody has measured.

### The amendment to Lane A

**Lane A §7 registered `alpha = 0.05` for its single interval test on `M`. That
is superseded by `alpha = 0.0167`.** Recorded in Lane A as Amendment 1, in place,
with nothing deleted — the record is the product.

What it changes, computed rather than asserted
**[COMPUTED FROM CODE]**:

| | alpha = 0.05 | alpha = 0.0167 |
|---|---:|---:|
| multiplier at `G = 100` | 5.012 | **5.823** |
| multiplier at `G = 300` | 3.656 | **4.215** |
| `G` for half-width ≤ 10.0 tenths, σ=20 | 101 | **120** |
| `G` for half-width ≤ 3.8 tenths, σ=20 | 349 | **428** |

**No threshold in Lane A moves.** Its `-10.0` tenth threshold, its `G >= 100`
floor, its branch structure and its Grid F edges are all unchanged. The design
already made the binding condition a **half-width precondition**
(`m·se <= 10.0`) rather than a bare `G` count, precisely so a change in the
multiplier would tighten the requirement automatically instead of requiring a
judgement call. It does exactly that here: the effective floor rises from ~101
to ~120 games at σ = 20, and no human chooses anything.

**No data has been observed since Lane A was registered**, so this amendment is
blind to its answer and `G` does not restart.

---

## §S1. The extraction, fixed in advance

The join in §2, plus the collapse of §4 expressed so it cannot drift:

```sql
WITH joined AS ( <the §2 join> ),
collapsed AS (
  SELECT *, ROW_NUMBER() OVER (
      PARTITION BY ticker, side ORDER BY created_ms DESC, id DESC
  ) AS rn
  FROM joined
)
SELECT * FROM collapsed WHERE rn = 1;      -- latest-row rule; rn over ASC for the sensitivity
```

The `id DESC` tiebreak is deliberate: two rows sharing a millisecond must resolve
deterministically, or the "same" analysis returns different answers on two runs
and the difference is invisible.

## §S2. Required output of every run, in this order

Read the frame before `n`, and `n` before any effect size.

1. **The frame.** Total rows, joined rows, dropped rows with reasons
   (`fair_price_id` NULL, any of the four NULL, price out of range), and the
   §2 predicate as executed.
2. **The invariants**, pass or fail, before any statistic:
   `p_conservative == min(four)` on every row; `fair_probability ==
   p_conservative`; `market == 'h2h'` on every row; `E1(p_a) − E1(p_b) ==
   (p_a − p_b) × 1000` to floating-point tolerance. **Any failure aborts.**
3. **`n_rows`, `n_observations`, `n_clusters`**, with the rows-per-observation
   and observations-per-cluster distributions and the largest cluster's share.
4. **The composition** (§3), every stratum, in observations and clusters.
5. **Outcome coverage** (P4): resolved / open / unreadable, and the retro-week
   versus post-deploy split.
6. **σ and the resolvable effect** for B1, labelled measured, and the
   always-valid half-width at this `G`, printed **before** the estimate.
7. **B2, the whole 7 × 2 grid**, with `indeterminate` beside every cell, and the
   branch (a)/(b) verdict.
8. **B1**, per bucket then pooled, with the largest bucket's share on the pooled
   line, and the ABOVE/BELOW HEADROOM verdict per bucket.
9. **B3**, both views, every cell labelled **DESCRIPTIVE — CANNOT PRODUCE A
   FINDING**, with the required `G` printed beside the achieved `G`, the design
   effect `(se_cluster/se_binomial)²`, and `(noise)` censoring on all three
   columns below the validity gate.
10. **§8, reproduced verbatim**, so the prohibition on quoting this as licence
    to relax rule 2 travels with the numbers.
11. **§M's joint count**, restated, so no reader takes a cell from one lane
    without the other lane's tests in the denominator.
12. **§10, reproduced verbatim.**

The harness's module docstring states what it does not establish.

---

## Registration record

| | |
|---|---|
| Registered | 2026-08-10 |
| Registered jointly with | `2026-08-10-preregistration-fresh-odds-edge-distribution.md` (`fed69d8`), which this document amends (§M) |
| Data seen at registration | Whole-table counters and outcome coverage (§0). **No probability, no gap, no join has been seen by anyone.** |
| Primary estimands | **B2** — counterfactual actionable clusters, deterministic; **B1** — mean over game clusters of `(p_ref − p_conservative)` in tenths |
| Direction | B2 one-sided (a single counterexample refutes); B1 two-sided against 3.8 tenths |
| Probability basis | `fair_prices` row reached by `recommendations.fair_price_id`; four methods and their min on one row per outcome |
| Outcome basis | `kalshi_markets.result`, `won = (result = side)`; **not** `settlements`, which is `FROM orders` and empty |
| Unit | one observation per `(ticker, side)`, latest `created_ms`; clustered by game |
| Cluster key | `COALESCE(kalshi_markets.event_ticker, recommendations.ticker)` — Lane A's, verbatim |
| Bucket edges | `analysis.validate.BUCKETS` verbatim, one edge set for both lanes and all five curves |
| Boundary | `gate.always_valid_multiplier(G, tuning=300, alpha=0.0167)` — joint allocation, §M |
| Joint multiplicity | **3 alpha-carrying interval tests, 156 descriptive cells** across both documents; 7.10 expected false findings at 2 SE, P(≥1) = 0.999 |
| Stopping rule | §8 of Lane A applies to the shared record; here: `G = 300` collapsed games, or 2026-11-30, or every branch declared or refuted, whichever first. Interim looks unlimited under the always-valid boundary. |
| Result destination | `docs/measurements/<run-date>-devig-method-calibration-result.md`, written either way |
| Assumed inputs | **One** — σ, a column of the power table, gating no threshold |
| Verdict at registration | **B1, B2 READY — blocked on P1 (no route exposes `fair_prices` or `result`; needs a deploy or volume access). B3 UNDERPOWERED by ~4 orders of magnitude, permanently.** |
| Amendments | none to this document; **this document amends Lane A** (§M) |
