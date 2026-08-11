# Pre-registration — the outcome-scored leadership comparison

**Written 2026-08-11.** Commissioned to price the instrument that ADR 0021 §7's
escape-hatch annotation left **"neither licensed nor refused"** (`start.md:162`,
`tasks/NEXT.md:127-134`): a **paired forecast-accuracy comparison** between
Kalshi's price and the devigged sportsbook consensus, both scored on
`kalshi_markets.result`.

**Status: REGISTERED AND REFUSED ON POWER.** The design below is complete and
fixed, and it is **not runnable on this record**. §0 is the operative section:
the arithmetic that refuses it needs no data and is reproduced in full so that a
future session can check it in a minute rather than re-derive it. §§1–10 are
fixed anyway — a design whose refusal is arithmetic must still be written down
completely, or the refusal is a judgement about a design nobody can inspect.

- Owner: `pre-registrar` (agent), on behalf of Joe.
- Scored against by: `measurement-skeptic`, if it is ever run.
- Negative-result destination fixed in §9, before the result exists.
- **Carries the rival-price table required by
  [`docs/adr/0026-every-declaration-branch-prices-the-rival-before-the-data.md`](../adr/0026-every-declaration-branch-prices-the-rival-before-the-data.md)
  §5** — see §7.4. That table is the second most important thing in this file
  after §0, and it changes what one of the two declaration branches is allowed
  to mean **even at infinite `n`**.
- **This document is committed before any count is produced.** No outcome data
  was read to write it. Every figure below is either a re-derivation from a
  committed document (labelled `[DOC]`), a read of code or schema in this repo
  (labelled `[CODE]`), or closed-form arithmetic (labelled `[DERIVED]`).

---

## §B. The hard boundary — what this document may not become

**DESIGN ONLY.** No data was read, no money moved, no deploy, no push beyond the
commit of this file.

Running this design needs `kalshi_markets.result` off the **live** Fly database.
The tool that reads it does not ship, and the mechanism is not the one a reader
would guess:

```
Dockerfile:66          COPY scripts/ ./scripts/          # a blanket copy
.dockerignore:59       scripts/*
.dockerignore:60       !scripts/run_loop.py
.dockerignore:61       !scripts/migrate_db.py
```
`[CODE]` — both files read for this document. `Dockerfile:66` copies the whole
directory and **does not decide what ships**; the exclusion layer does, and it
admits exactly two files. The repo currently holds **42** `scripts/*.py`
`[CODE]`, so **two of forty-two are in the image**. (The commissioning brief said
*"two of thirty-four"*; the denominator has grown since it was written and the
numerator has not. Cite 42, or cite neither.)

`scripts/inspect_live_db.py` is therefore **not in the image** and cannot be run
against the live instance without a deploy. **Deploys are Joe's.** Nothing in
this document licenses one, and a session that reads *"and then pull the data"*
into it has walked into a wall this section exists to name.

**Given §0, this is moot in practice: there is no `G` this record can reach at
which the design may declare, so there is nothing to pull the data for.**

---

## §0. THE POWER CHECK — this comes before everything, and it refuses the design

### §0.1 What was already known when this was written

| Fact | Value | Source |
|---|---:|---|
| Game clusters anywhere in the pinned record | **60** | `[DOC]` ADR 0021 §7.2 annotation, re-derivation of `2026-08-10-clean-shortfall-pull.json` |
| Clean game clusters | **59** | `[DOC]` ADR 0021 §2 |
| Recording instants (`created_ms`) over the clean set | **34** | `[DOC]` ADR 0021 §2 |
| Registered CLV population, cluster count | **~20** | `[DOC]` ADR 0021 §7.2 annotation |
| Share of the record at near-even prices (Grid D middle cell) | **99.1%** | `[DOC]` ADR 0021 §4 |
| Kalshi price accuracy, as the project's own premise | **~2c** | `[DOC]` `CLAUDE.md` |
| Devig-method spread | **1–2 points** | `[DOC]` `CLAUDE.md` rule 1 |
| Taker headroom over break-even | **0.38 points** | `[DOC]` `CLAUDE.md` |
| `suspicious_edge` threshold on the stored edge | **40.0 tenths** | `[DOC]` ADR 0021 §5.1 |

**The record's ceiling is `G ≤ 60`.** Every game in the recording window
(2026-08-07 → 2026-08-09) has had two days to settle, so the settled count is
plausibly close to 60 — but the *ceiling* is what the arithmetic needs, and 60
is a count of clusters in a committed pull, not an outcome.

**Never write "614 rows".** The honest denominator is **59 games across 34
recording instants** (ADR 0021 §2's convention). Per-game clustering is what
collapses `n`, and it is not optional: a game's moneyline resolves from one final
score, so the YES on one ticker and the NO on the other are **one** observation
(assumption A1, ADR 0021), and 34 sweeps of the same game supply **34
observations of the price and one of the outcome**.

### §0.2 The estimator's signal-to-noise, in closed form `[DERIVED]`

Per game `g`, with Kalshi's forecast `p_K`, the consensus forecast `p_C`, and the
outcome `y ∈ {0,1}`:

```
Δ_g = (p_K − y)² − (p_C − y)²
    = (p_K − p_C)(p_K + p_C − 2y)
    = d·(s − 2y)                      where d = p_K − p_C,  s = p_K + p_C
```

Let `q` be the true probability and `σ_d² = E[d²]`.

**Under H_K (Kalshi is the sharp side, `q = p_K`):**
```
E[Δ | d]   = d(p_K + p_C − 2p_K) = d(p_C − p_K) = −d²
E[Δ]       = −σ_d²
Var(Δ | d) = 4d²·q(1−q)
Var(Δ)     ≈ 4·E[d²q(1−q)] + Var(d²) ≈ σ_d²·(4q̄(1−q̄)) + O(σ_d⁴)
```

**Under H_C (the consensus is the sharp side, `q = p_C`):** identical in
magnitude and opposite in sign, `E[Δ] = +σ_d²`.

So the two hypotheses are separated by `2σ_d²`, and at the near-even prices this
record is 99.1% composed of (`q ≈ 0.5`, so `4q(1−q) ≈ 1`):

```
per-game  |E[Δ]| = σ_d²
per-game  sd(Δ)  ≈ σ_d
per-game  SNR    = σ_d

  |t| after G game clusters  ≈  σ_d · sqrt(G)
```

**The power of this design is the rms disagreement between the two forecasts,
in probability units, times the square root of the number of games.** That is
the whole result and everything below is its consequence.

*Near-even is the worst case for variance and it is measured, not assumed
(99.1%, `[DOC]`). On a lopsided line the SNR improves by `1/(2·sqrt(q(1−q)))` —
a factor of **1.67 at `q = 0.90`** `[DERIVED]`. This record does not contain
those lines in any quantity, and 1.67× does not change any verdict below.*

### §0.3 The detectable effect at the `n` available

The repo's own always-valid boundary is required here (§7.3: the record is looked
at more than once as it grows), so the threshold is
`gate.always_valid_multiplier(G, tuning=300, alpha=0.05)`
(`backend/gate.py:126`, `ALWAYS_VALID_ALPHA = 0.05` at `:123`) `[CODE]`. It
reproduces the docstring's own table (9.84 at `G = 20`, 3.66 at `G = 300`)
`[DERIVED]`.

| `G` | boundary multiplier | **rms disagreement `σ_d` required to declare anything** |
|---:|---:|---:|
| 20 | 9.84 | **2.20** (impossible: probabilities live in [0,1]) |
| **60** — this record's ceiling | 6.09 | **0.786** (impossible) |
| 300 — the CLV floor | 3.66 | **0.211** |
| 1,000 | 3.11 | **0.0985** |
| 5,000 | 3.04 | **0.0433** |

`[DERIVED]`, all cells.

> **At `G = 60` this design requires a 78.6-percentage-point rms disagreement
> between Kalshi's mid and a devigged sportsbook consensus on the same moneyline
> before it may say anything at all.** A disagreement of that size means the two
> quotes are not about the same game.

**And the `G = 300` floor does not rescue it either.** At `G = 300` the
requirement is still **21.1 points**. The CLV design's floor was set for a
different estimator and it is not a sufficient floor for this one. That is worth
saying plainly, because "get to 300 games" is the reflex this repo has already
built, and for *this* instrument it is off by two orders of magnitude.

### §0.4 The `n` that would be needed

Solving `σ_d·sqrt(G) ≥ always_valid_multiplier(G, 300)` `[DERIVED]`:

| assumed `σ_d` | what that is | **`G` required** | MLB seasons at 2,430 games |
|---:|---|---:|---:|
| 0.01 | one point — below the devig-method spread | **122,002** | 50.2 |
| **0.02** | **`CLAUDE.md`'s own "~2c" premise** | **26,535** | **10.9** |
| 0.03 | three points | 11,088 | 4.6 |
| 0.04 | four points — at the `suspicious_edge` cap | 5,989 | 2.5 |
| 0.05 | five points | 3,712 | 1.5 |
| 0.10 | ten points — the two venues disagree wildly | 987 | 0.4 |

*(A fixed single look at 80% power, two-sided α = 0.05, gives the same order:
`G = ((1.96+0.84)/σ_d)²` = **19,600** at `σ_d = 0.02` `[DERIVED]`. The choice of
boundary is not what refuses this design.)*

**The honest cell is `σ_d = 0.02`, and it needs about eleven complete MLB seasons
of settled, matched, priced games.** The record supplies at most 60 games from
one 46-hour window. The shortfall is a factor of about **440 in `G`**.

**The maximum reachable `|t|` on this record, computed generously** `[DERIVED]`:

```
even at the suspicious_edge ceiling on EVERY game, σ_d ≈ 0.049:
    |t|max = 0.049 × sqrt(60) = 0.38
at CLAUDE.md's own ~2c premise, σ_d = 0.02:
    |t|    = 0.02  × sqrt(60) = 0.15
```

**The design cannot reach `|t| = 1` on this record even if every game sat exactly
at the largest disagreement the suppression layer tolerates.** It is not near a
threshold; it is not on the same scale as one.

### §0.5 Calibrated against the headroom actually being hunted

`CLAUDE.md`: the venue lowers the bar to 52.00% taker, leaving **0.38 points** of
room, and the devig-method spread alone is **1–2 points**. A design that can only
resolve a **21-point** disagreement at the CLV floor — and a **79-point** one at
this record's ceiling — is off by a factor of 55 from the smallest effect the
project exists to measure. It is not "clean statistics on a small sample". It is
an instrument pointed at a scale where nothing this project cares about lives.

### §0.6 The two inherited leads: one is not reproduced, one is retired for a stronger reason than power

Both were recorded as **leads only** (`start.md:164-166`) and both were to be
verified or discarded. Neither is inherited.

**Lead 1 — "a paired sign test at `G = 60` would need a true rate above 0.893".
DISCARDED, and not on power. The paired sign test is `NON-DISCRIMINATING` at any
`G`.** `[DERIVED]`

With a binary outcome, *"which forecast was closer"* collapses to *"which
forecast was on the right side"*: `|p_K − y| < |p_C − y|` iff (`y=1` and
`p_K > p_C`) or (`y=0` and `p_K < p_C`). So Kalshi's win rate is

```
W = E[ q·1{d>0} + (1−q)·1{d<0} ]          where d = p_K − p_C
```

Under H_K (`q = p_K`, consensus errs by `η`, `d = −η`), if `η` is symmetric and
independent of the price level:
```
W = ½·E[p_K] + ½·E[1 − p_K] = ½      exactly, for ANY price distribution
```
Under H_C (`q = p_C`, Kalshi errs by `η`, `d = η`), by the same two lines:
```
W = ½·E[p_C] + ½·E[1 − p_C] = ½      exactly
```

**Both hypotheses predict a true rate of exactly 0.500.** The complementary terms
cancel the price distribution out entirely, so no sample size separates them.
Concretely: truth `q = 0.5` on every game, Kalshi says 0.5 always, the consensus
says 0.9 half the time and 0.1 half the time — a vastly worse forecaster — and
the sign test still returns 0.500. **The sign test is blind to the magnitude of a
forecast error and detects only whether the *direction* of disagreement predicts
the outcome, i.e. a bias.**

Worse, it *would* have power against one thing here, and it is an artefact: if
`p_conservative` were used as the consensus (it is `min(four devig methods)` and
a deliberate downward bias, ADR 0021 §7.3), the disagreement is systematically
one-signed and the sign test would fire on the shrinkage. **A statistic with no
power against the question and real power against a known artefact is worse than
a weak one.** The sign test is retired here, with the arithmetic, so it is not
re-proposed.

**Lead 2 — "a paired Brier difference crosses over near `G = 68`". NOT
REPRODUCED.** `[DERIVED]` At `G = 68`, `|t| = 1.96` requires
`σ_d = 1.96/sqrt(68) = 0.2377` — a **23.8-point** rms disagreement. That is
**12× `CLAUDE.md`'s stated ~2c accuracy** and **5× the `suspicious_edge`
ceiling**. Under any `σ_d` consistent with this record the crossover is at
`G` in the tens of thousands (§0.4). The figure is discarded. Its likely
provenance is a "best case for the hypothesis" that silently assumed a
disagreement the venue and the suppression layer both exclude — recorded as a
reading, not as a fact about how it was produced.

**Both leads pointed the same way and both were, as recorded, right about the
direction. Neither survives as arithmetic, and the correct verdict is stronger
than either: it is a refusal by a factor of hundreds, not a near miss.**

### §0.7 Three re-scopings, priced before they are proposed `[DERIVED]`

None rescues the design. They are priced here so the refusal is not re-litigated
by proposing one of them as new.

1. **Use rows, not games.** 614 clean rows over 59 games. `y` is constant within
   a game, so averaging `Δ` across the 34 sweeps of one game averages `d` and
   leaves the outcome noise untouched. The variance floor is set by `G`, not by
   `n_rows`. This is the gate bug ADR 0005 fixed (400 rows on one ticker counted
   as 400 observations) and it is not available here.
2. **Select the games with the largest `|d|`.** Legitimate — it selects on the
   independent variable, not the outcome — and it trades `G` for `σ_d`. The
   product `σ_d(subset)·sqrt(G_subset)` would have to rise by a factor of ~2 to
   reach `|t| = 1`, i.e. the top-20 subset would need `σ_d ≈ 0.22`. It does not
   exist on a record whose entire clean population is capped at ~0.049 by
   `suspicious_edge`.
3. **Test calibration instead of leadership** (is the consensus right, ignoring
   Kalshi). Unpaired, so per-game `sd ≈ 0.5` and `|t| = 2ε·sqrt(G)`: at `G = 60`
   the detectable miscalibration `ε` is **12.7 points**. Also impossible, and it
   answers a different question anyway (ADR 0021 §9 separates them).

### §0.8 The verdict

> **UNDERPOWERED. This design is refused on power and may not be run on this
> record.** The detectable effect at `G = 60` is an rms forecast disagreement of
> **78.6 percentage points**; at the `G = 300` CLV floor it is **21.1**; the
> effect the project exists to measure is **0.38 points** of headroom against a
> **1–2 point** method spread. The `G` required at `CLAUDE.md`'s own ~2c premise
> is about **26,500 game clusters**, roughly eleven complete MLB seasons.
>
> **Recommendation: KILL, not re-scope.** No cut, no population, no estimator
> and no stopping rule available here moves the requirement by the factor of
> ~440 needed. §0.7 prices the three obvious re-scopings and none of them
> reaches even `|t| = 1`.
>
> ADR 0021 §7's escape hatch — *"Kalshi may be the sharp side, so the comparison
> is empty by construction"* — **cannot be closed by an outcome-scored
> forecast-accuracy comparison on any record this project will plausibly hold.**
> It moves from *"neither licensed nor refused"* to **refused, with arithmetic**.
> That is not a statement that the escape hatch is false. It is a statement that
> this instrument cannot decide it, and that the honest response is to stop
> proposing dumps for it.

**And §7.4's rival-price table adds a second, independent reason that survives
infinite `n`:** the `KALSHI-LEADS` branch is `NON-DISCRIMINATING` between "Kalshi
has better information" and "the consensus, as this tool constructs it, is
noisier for reasons already documented and unrelated to information". Even a
fully powered run of this design could not license the escape hatch's own
sentence. Read §7.4 before ever reviving this.

---

## §1. The question, as a claim that could be false

The design is fixed in full below despite §0, so that the refusal is inspectable
and so that a future project with a real `n` inherits a finished document rather
than a memory.

**Estimand.** `μ = E[Δ_g]`, the mean over independent game clusters of the paired
Brier difference `Δ_g = (p_K,g − y_g)² − (p_C,g − y_g)²`.

**The two hypotheses, both live, both directional:**

- **H_K — Kalshi leads.** `μ < 0`. Kalshi's mid is a better-calibrated forecast
  of the settled outcome than the devigged sportsbook consensus this tool builds.
- **H_C — the consensus leads.** `μ > 0`.

**Registered as TWO-SIDED, and it must be scored two-sided.** Both directions
are decision-relevant (§9) and the boundary in §7 is two-sided (`|S_n|`, the
Robbins form in `gate.py:144`). **A two-sided design reported one-sided after the
fact has doubled its own false-positive rate**, and this file forbids that
conversion in advance.

**What falsifies H_K:** `μ` bounded away from zero on the positive side by the
registered boundary. **What falsifies H_C:** the mirror image. **What falsifies
neither:** everything else, including every zero — see §7.4, a zero is predicted
by the third rival (H_0) and by insufficient `G`, and those are not
distinguishable by this statistic.

**Quantifiers, weakened at registration time where it is free.** The hypothesis is
about a **mean over the admitted population**, not about *every* game, and not
about anything holding *structurally* or *by construction*. No sentence in this
file claims a universal, and none may be added to its write-up.

---

## §2. The population, and the exclusions

**Base.** `recommendations` → `fair_prices` (via `fair_price_id`) →
`kalshi_markets` (via `ticker`) → `kalshi_events` (via `event_ticker`), on the
live database, over the whole table at a stated pin.

**Inclusion predicates, all outcome-independent:**

| Predicate | Reason it is independent of the outcome |
|---|---|
| `kalshi_markets.result IN ('yes','no')` | The dependent variable must exist. Which games have settled is fixed by the schedule and the pull time, not by *how* they settled. **Print the count of `result IS NULL` rows excluded and their commence times**, so a reader can see the exclusion is a calendar, not a filter. |
| `market_type = 'moneyline'` | A1 (two settling outcomes per game) is registered and was verified on all 59 clusters (ADR 0021). Spreads, totals and `team_total` need strike handling and are a different design. |
| `fair_prices.p_multiplicative IS NOT NULL` | The primary consensus reading must exist. Missingness is a devig failure on the book set, not a function of the result. |
| `kalshi_quotes` has a two-sided quote at the instant | `p_K` needs both `yes_bid_tenths` and `no_bid_tenths` (§4). |
| `created_ms < kalshi_events.commence_ms` | **Pre-game only.** See §5. Violations are counted and printed, not silently dropped. |

**Excluded, with the reason and the count printed:**

- Rows whose fair value is degenerate (`p ∈ {0,1}`) or which tripped
  `too_few_books`. A fabricated fair is a bad input; the check is logically prior
  to and independent of the outcome (ADR 0021 §3, H4).
- Rows written by `seed_demo.py`. Demo data.

**The three nested populations, all reported, PRIMARY named now:**

| | Definition | Why |
|---|---|---|
| **P1 — PRIMARY** | Survives every **edge-independent** suppression check; the two **edge-dependent** checks (`suspicious_edge`, `edge_within_method_noise`) are **not** applied. | The edge-dependent checks truncate `\|d\|`, and `σ_d` is the entire power of this design (§0.2). Truncating the independent variable to defend a money decision is right for money and wrong here. |
| **P2** | The clean population — all suppressions applied (59 games across 34 recording instants). | Comparability with ADR 0021. |
| **P3** | Every row with a usable pair, no suppression at all. | The maximum-`σ_d` reading. **Labelled as containing suspected data errors** (rule 1: a large apparent edge is a bug until proven otherwise) and reported as an *upper bound on attainable power*, never as a finding. |

**ADR 0021 §5.1 measured that on `pin = 1564`, deleting both edge-dependent
checks leaves the clean population byte-identical.** So P1 and P2 may coincide.
**That must be checked and printed on the run's own pin, never assumed** — §5.1
scopes itself to one pin explicitly.

**The rule that must not be activated after the fact.** If P1 turns out thinner
than P2 by more than a handful of games, the temptation is to swap PRIMARY to
whichever is larger. **PRIMARY is P1 and does not move.** The precedent is the
combo experiment that pre-registered an exclusion and correctly refused to
activate it when the sample came in thin; that refusal was only possible because
the rule was in writing first.

**No exclusion in this design references the dependent variable's value.** An
exclusion that did would not be an exclusion rule, it would be the finding.

---

## §3. The unit of observation

**The unit is the game cluster.** Not the row, not the market, not the sweep.

**Cluster key:** `kalshi_markets.event_ticker` on the live database. ADR 0021's
pull carried no `event_ticker` and used *the ticker with its final segment
removed*; the two must both be computed and **reconciled with the difference
printed**, because ADR 0021's own annotation records that `COALESCE(event_ticker,
ticker)` returns market-level counts (120 / 96 / 55) and not cluster-level ones.

**What makes two units independent:** two different games have two different
final scores. Within one game they do not:

- The moneyline YES on team A and the NO on team B name **the same claim** (A1).
  They are **one** observation, not two.
- The 34 recording instants of one game supply **34 observations of the price and
  one of the outcome**. Averaging over instants reduces noise in `d`; it does
  **not** reduce outcome noise (§0.7 item 1).
- Rows within one sweep are additionally dependent through one odds snapshot —
  ADR 0021 §2 settles that *the sweep is the dependence unit* for the odds side.
  For the outcome side the game is the coarser and binding unit, so **the game is
  the clustering variable** and the sweep dependence is nested inside it.

**Per-game reduction, fixed now:** `p_K,g` and `p_C,g` are the **unweighted means
over all admitted instants of the same claim within the game**, computed before
`y_g` is joined. `Δ_g` is then computed once per game. This is registered in
advance so nobody may later choose "the instant nearest close" or "the largest
disagreement" after seeing which one declares.

**Never write "614 rows".** Say **"59 games across 34 recording instants"**, or
the run's own equivalent. Rows are uptime.

---

## §4. The price each side is scored at, and why

This is the section a post-hoc analysis would have chosen after seeing the
answer, so it is fixed hardest.

### §4.1 Kalshi's forecast probability — the **mid of the derived two-sided
quote**, and this is a deliberate departure from the ask rule, with its reason

```
p_K = ( yes_bid_tenths + (1000 − no_bid_tenths) ) / 2000      [kalshi_quotes]
p_K = ( yes_bid_tenths + yes_ask_tenths )        / 2000       [closing_lines]
```
`[CODE]` — `kalshi_quotes` carries `yes_bid_tenths` and `no_bid_tenths` only
(`schema.sql:147-163`), so the YES ask is *derived* as `1000 − no_bid_tenths`;
`closing_lines` carries both sides directly (`schema.sql:171-186`).

**`CLAUDE.md` says: bucket by the price you would actually pay — the derived ask,
never the mid. One bucket in the previous project showed a +25.4 point edge and
lost money for exactly this reason.** That rule governs **money decisions and
every bucket and P&L figure**, and it is not weakened here. This measurement is
not a money decision: it asks which of two *forecasts* is more accurate, and

> **a Brier score takes a probability. The derived ask is a probability plus a
> half-spread.** Scoring the ask against `result` handicaps Kalshi by exactly the
> half-spread on **every** game, in one direction, with no information content.
> The consensus side is already vig-removed. Scoring a vig-removed number against
> a vig-inclusive one is the mirror image of the +25.4 point bucket: it is the
> same error with the sign flipped, and it would manufacture `CONSENSUS-LEADS` by
> construction.

**So: mid against devigged, like for like. The ask is not discarded — it is
routed to a separate, differently-labelled readout.**

### §4.2 The transactable readout — registered, reported, and forbidden from answering this question

A second pass scores `p_K = entry_ask_tenths / 1000` (`recommendations`, the
column the schema comment calls *"the price we would ACTUALLY pay: the derived
ask. Never a mid"*) `[CODE]`.

It answers **"would transacting at this price have been profitable"**, which is a
different question with a different null. It is reported beside the primary, with
**the mean half-spread printed next to it** so its built-in handicap is visible,
and it is **forbidden from being quoted as the accuracy result** or from
declaring any branch in §7.

### §4.3 The consensus forecast probability — `p_multiplicative`, not `p_conservative`

```
p_C = fair_prices.p_multiplicative        PRIMARY
```

**`p_conservative` is banned as the primary.** It is `min(four devig methods)` —
ADR 0021 §7.3, verified on all 1,549 rows — i.e. **a deliberately downward-biased
probability**. `CLAUDE.md` rule 2 (*use the worst of four for any money
decision*) is exactly right for money and exactly wrong for a calibration
comparison: a Brier score punishes bias, so scoring a deliberately biased number
hands `KALSHI-LEADS` to Kalshi by construction. `p_multiplicative` is the
method chosen for being the plainest, **fixed here before any of the four has
been scored**, and not for its result.

**All four methods are reported** (`p_multiplicative`, `p_additive`, `p_power`,
`p_shin`) as a sensitivity band. The band is descriptive. Only the primary
declares (§7.2). **If the four disagree in sign, that is the finding**: it means
the answer is a function of devig choice, which is the 1–2 point spread
`CLAUDE.md` warns exceeds the whole effect — and the correct output is
`UNRESOLVED` regardless of any `t`.

### §4.4 Bucket edges

**There are none. This design registers zero cuts.** One pooled paired estimate,
plus the two mandatory views `CLAUDE.md` requires beside any aggregate: the
**per-game view** and the **largest contributor's share** (as a share of `G`, and
also of instants, since ADR 0021 §2 found the largest *sweep* carried 18.6%
against the largest *cluster*'s 5.3%).

Registering zero cuts is deliberate: bucket boundaries are the richest source of
unearned findings, and the cheapest way to price the multiplicity exactly is to
have none. **Any bucketing — by price band, by league, by horizon, by book count
— is a new registration, not an amendment.**

---

## §5. The observation timing, and the second horizon

**`CLAUDE.md`: the convenient column is usually contaminated. `last_price` on a
settled market has already converged on the outcome.**

**Forbidden inputs, named now:** `kalshi_markets.last_price` or any post-close
price; any row with `created_ms >= commence_ms`; any candlestick observation
taken after the market's `close_ms`.

**When each price is observed relative to when the outcome became known:**

| Reading | Kalshi price | Consensus price | Observed | Outcome known |
|---|---|---|---|---|
| **h1 — PRIMARY** | `kalshi_quotes` mid at the row's `created_ms` | `fair_prices` computed in the same cycle, of stated `odds_age_ms` | the live decision instant, **strictly pre-game** | at game end, hours later |
| **h2 — SECOND HORIZON** | `closing_lines` mid at the row's `clv_horizon_hours` | the last admitted `fair_prices` before that anchor | a fixed number of hours before close | at game end |

Both are strictly before the outcome exists, so neither can have converged on it.
The residual hazard is **staleness on the consensus side, not lookahead**:
`odds_age_ms` is a scrape clock and a **lower bound** on true line age (ADR 0021
§7.5, 320 of 320 book+event pairs carrying one identical stamp). That runs
against the consensus and is priced in §7.4.

**Why the second horizon is mandatory and not a robustness nicety.**
`schema.sql:165-170` says it in the schema's own words: *"a result that moves
when you change `hours_before` was convergence, not edge, and you can only detect
that if the horizon is a first-class column you can group by."* `[CODE]`

**Registered guard:** if h1 and h2 disagree in **sign**, the output is
`UNRESOLVED` **whatever the boundary says on h1**. A leadership claim that
depends on when you looked is a claim about convergence.

`closing_lines` exists only for CLV-scored rows, so h2's `G` will be smaller than
h1's. **Both `G`s are printed.** h2 is descriptive and may not declare on its
own.

---

## §6. The statistic, named as an estimator

**It is a mean of game-clustered paired differences.** Said out loud so the wrong
default cannot be reached for:

> **`sqrt(p(1−p)/n)` is FORBIDDEN in this design.** That is the standard error of
> **a proportion**. This estimand is not a proportion, not a difference of paired
> proportions, and not a rate. Its null is `E[Δ] = 0` on a continuous, signed,
> game-clustered quantity, and its standard error is the cluster-robust
> `sd(Δ_g)/sqrt(G)`.

**Point estimate:** `Δ̄ = (1/G)·Σ_g Δ_g`.
**Standard error:** `sd(Δ_g)/sqrt(G)` over the `G` game clusters. `n_rows` never
appears in any denominator.

**Mandatory prints, whether or not anything is declared** — these are the
measurement, and the run produces them even under `UNRESOLVED`:

1. `G`, `n_instants`, `n_rows`, in that order, with `n_rows` last and labelled
   *uptime*.
2. **`σ̂_d = rms(d_g)`** and the full distribution of `d_g`. This is the quantity
   §0's entire power argument turns on, and **it is computable without joining
   any outcome at all**. It is the single most valuable number the design can
   produce and it is produced first (§7.1).
3. `Δ̄`, `sd(Δ_g)`, the cluster-robust SE, and the always-valid interval.
4. The per-game `Δ_g` table and the largest contributor's share of `|ΣΔ_g|`.
5. The four-method sensitivity band (§4.3) and both horizons (§5).
6. The transactable readout with its mean half-spread (§4.2).
7. `4·q̄(1−q̄)`, the variance factor, so the §0.2 approximation is checked against
   the run rather than assumed.

---

## §7. The decision rule, with the multiplicity already counted

### §7.1 The prerequisite that runs before the outcome is joined

**PC-REACH.** Compute `σ̂_d` on the admitted population with **no outcome column
joined**. If

```
σ̂_d · sqrt(G)  <  always_valid_multiplier(G, tuning=300, alpha=0.05)
```

then the run **stops before joining `kalshi_markets.result`** and reports
`UNRESOLVED — UNREACHABLE`, with `σ̂_d`, `G`, and the multiplier printed.

This is not a decision rule and carries no alpha: it reads only the independent
variables. It exists so the design cannot produce a number it is not entitled to.
**On this record, §0.3 says PC-REACH fails by a factor of roughly 20 in `σ_d`,
which is why §0.8 refuses the design outright.**

### §7.2 How many tests carry alpha: exactly one

**Readouts:** 3 populations × 4 devig methods × 2 horizons = **24**, plus 3
transactable readouts = **27 cells**.

**Priced now, before the data** `[DERIVED]`:

```
27 cells, pure noise, |z| >= 1.96 two-sided
  expected "significant" cells            27 × 0.05 = 1.35
  P(at least one), if independent         1 − 0.95^27 = 0.750   (UPPER BOUND;
                                          the cells are heavily correlated)
```

**So a run of this design on data with no leadership in it whatsoever is more
likely than not to produce at least one "significant" cell.** This project has
already produced a 20-point "finding" from data generated with no edge in it, and
1,190 category cells producing dozens of chance results is in `CLAUDE.md` for the
same reason.

**Exactly ONE cell may declare: `P1 × p_multiplicative × h1`.** The other 26 are
descriptive, are printed, and **may not be reported as significant or described
with any word implying a test**. Family-wise alpha is therefore 0.05, carried
entirely by the primary cell under the always-valid boundary.

### §7.3 The boundary is always-valid, because this record is looked at more than once

`tasks/NEXT.md` option F (*keep recording and re-read at a larger `n`*) is live.
A threshold re-evaluated on every request against an accumulating database is not
one look; it is thousands, and under a true zero it crosses eventually with
probability 1. `gate.py:161` records the measured cost: **13.7% of zero-edge
sequences fire the fixed-sample rule over 100 looks, against 0% for this
boundary** — and 13.7% is a floor at 100 looks, not a ceiling. `[CODE]`

So the boundary is `gate.always_valid_multiplier(G, tuning=300, alpha=0.05)`
(`backend/gate.py:126`), used unmodified — the repo's own instrument, not a
second one written for this file.

**Two assumptions it carries, both named:** it assumes observations are
**independent across games** (`gate.py:165-169`), which this design's clustering
is chosen to satisfy but does not prove; and it does not correct for the strategy
changing between looks, which `strategy_config_version` records and this function
does not read. Both are inherited defects and neither is repaired here.

### §7.4 The rival-price table — ADR 0026 §5, and it changes what one branch may mean

**The live rivals, all four, before the data:**

- **H_K** — Kalshi has better information about the outcome.
- **H_C** — the devigged consensus has better information.
- **H_0** — both price the same information; `d` is small measurement noise with
  no directional truth in it.
- **H_A — the artefact rival, and the important one.** `d` is dominated by
  non-informational defects **of the consensus as this tool constructs it**, all
  three of which are already documented: the sharp-anchoring discards a median of
  19 usable books of 21 per row and binds on 73.0% of rows (ADR 0021 §7.2
  annotation); `odds_age_ms` is a scrape clock, so an admitted row is **not
  proven fresh** (§7.5); and devig-method choice alone moves the fair by 1–2
  points, which exceeds the whole headroom.

| Branch | Fires when | H_K predicts | H_C predicts | H_0 predicts | **H_A predicts** | Verdict |
|---|---|---|---|---|---|---|
| **`KALSHI-LEADS`** | `Δ̄ + mult·SE < 0` at `G ≥ 300` | `Δ̄ = −σ_d²` | `Δ̄ = +σ_d²` — excluded | `Δ̄ ≈ 0` — excluded | **`Δ̄ = −σ_d²`, identically.** A noisier consensus loses the paired Brier by exactly the same amount whether the noise is ignorance or staleness. | **NON-DISCRIMINATING between H_K and H_A. Narrowed — see below.** |
| **`CONSENSUS-LEADS`** | `Δ̄ − mult·SE > 0` at `G ≥ 300` | `Δ̄ = −σ_d²` — excluded | `Δ̄ = +σ_d²` | `Δ̄ ≈ 0` — excluded | `Δ̄ = −σ_d²` — **excluded**, H_A makes the consensus the *noisier* side | **DISCRIMINATING.** The refuting branch is the clean one. |
| **`UNRESOLVED`** | everything else, and every look at `G < 300`, and every PC-REACH failure, and every h1/h2 sign disagreement, and every four-method sign disagreement | reachable | reachable | reachable | reachable | **NON-DISCRIMINATING, and it says so.** Declares nothing, ever, at any `G`. |

**The narrowing that `KALSHI-LEADS` must carry, in fixed words, if it ever
fires** (ADR 0026 §5 rule 4 — a non-discriminating branch is narrowed, not
deleted):

> *The devigged consensus as constructed by this tool is a less accurate forecast
> of the settled outcome than Kalshi's mid. This does **not** establish that
> Kalshi holds better information, because a consensus anchored on a median of
> two to three books, built from quotes of unproven freshness, and devigged by a
> method whose siblings disagree by 1–2 points, is predicted to lose this
> comparison for reasons that contain no information at all.*

**Consequence, and it is why §0.8's refusal is doubled.** ADR 0021 §7's escape
hatch says *"Kalshi may be the sharp side, so the comparison is empty by
construction"*. The `KALSHI-LEADS` branch **cannot license that sentence at any
`G`**, because H_A predicts the same observation exactly. Only
`CONSENSUS-LEADS` — the branch that *refutes* the escape hatch — is
discriminating. **This design is an instrument that can only return the answer
nobody proposed it to find.** That is a fact about the design, it is knowable
before the data, and it is exactly the check ADR 0026 exists to force.

**A design that would discriminate** would have to hold the consensus's
construction fixed and vary only the information — for instance by scoring
Kalshi against a *contemporaneous, unanchored, full-book* consensus with measured
freshness. That is ADR 0021 §8's option B plus a freshness measurement, it is a
different registration, and **it is not proposed here.**

### §7.5 The decision rule, verbatim

> **DECLARE `KALSHI-LEADS` iff `G >= 300` and PC-REACH passed and
> `mean(Δ_g) + always_valid_multiplier(G, tuning=300, alpha=0.05) × sd(Δ_g)/sqrt(G) < 0`
> on the cell `P1 × p_multiplicative × h1`, and the h2 reading agrees in sign,
> and all four devig methods agree in sign — and then only as the narrowed claim
> written in §7.4, never as the escape hatch's own sentence. DECLARE
> `CONSENSUS-LEADS` iff `G >= 300` and PC-REACH passed and
> `mean(Δ_g) − always_valid_multiplier(G, tuning=300, alpha=0.05) × sd(Δ_g)/sqrt(G) > 0`
> on that same cell under those same two agreement conditions. In every other
> case — including every look taken when `G < 300`, every look at which
> `σ̂_d × sqrt(G) < always_valid_multiplier(G, tuning=300, alpha=0.05)`, every
> sign disagreement between h1 and h2, and every sign disagreement among the four
> devig methods — DECLARE `UNRESOLVED`. A look that declares `UNRESOLVED` may
> report point estimates and intervals and MUST report `σ̂_d`; it may not make a
> leadership claim of any kind, in any strength, anywhere.**

### §7.6 The power floor, stated separately so it cannot be read past

**`G >= 300` game clusters, AND PC-REACH.** The `G = 300` floor is inherited from
the CLV design (`2026-08-09-preregistration-clv-signal-test.md:420-427`) and from
`gate.py`'s tuning constant. **It is necessary and, for this estimator, not
sufficient** — §0.3 shows the boundary at `G = 300` still demands a 21.1-point
disagreement. **PC-REACH is the binding floor here, not `G`.** Both apply.

---

## §8. The stopping rule

Fixed now, in advance, because *"when we have enough"* means *"when it looks
good"*.

- **Data collection is not started by this document and is not extended by it.**
  The design consumes whatever the recorder has produced.
- **The design may not be run at all until both floors hold** (`G >= 300` settled
  moneyline game clusters, and PC-REACH). Looks before then are free under the
  always-valid boundary, but they may only report `UNRESOLVED` plus `σ̂_d`, and
  §0 says a look at `G ≤ 60` is not worth the credits.
- **Hard expiry: 2027-08-11 (UTC).** If both floors have not held by then, this
  registration is retired unrun, and the negative branch of §9 is written from
  §0's arithmetic. No extension may be granted by the party that wants the
  result.
- **A second look after a declaration is a new registration**, not an amendment.
  ADR 0021 §8 option F already records why.

---

## §9. What would falsify this, what happens then, and whether it is decision-relevant

### §9.1 The destinations, fixed now, before any result exists

| Outcome | Destination |
|---|---|
| **Any of the three branches, including `UNRESOLVED`** | `docs/measurements/2026-08-11-outcome-scored-leadership-result.md` — **this path is fixed now.** A pre-registration whose negative branch has no destination produces a negative result that quietly never gets written. |
| **`CONSENSUS-LEADS`** | An ADR, number assigned when written (this repo's numbering is contested and 0020 is reserved — ADR 0026 §Number). It would refute ADR 0021 §7's escape hatch. |
| **`KALSHI-LEADS`** | The result document only, carrying §7.4's narrowing verbatim. **It does not get an ADR on its own**, because §7.4 shows it cannot license the claim an ADR would be about. |
| **`UNRESOLVED` / retired at expiry** | The result document, written from §0's arithmetic. **This is the branch this registration expects and it is already 90% written, in §0.** |

### §9.2 Consequences in both directions

- **`CONSENSUS-LEADS`** → the escape hatch is refuted → ADR 0021's zero is a fact
  about the venue, not about the instrument's geometry → strengthens **option A**
  (stop the consensus-only line) and weakens **option C** (invert the frame).
- **`KALSHI-LEADS`, narrowed** → evidence that the *constructed consensus* is the
  noisier input → points at **option B** (widen the reference class) as a
  measurement problem to fix before any option is chosen. It does **not** license
  option C, and it does not close the escape hatch.
- **`UNRESOLVED`** → nothing changes, and that is the point of registering it as
  a real outcome rather than a failure.

### §9.3 The decision-relevance test, and it FAILS — stated because that is cheaper to learn now

**This measurement cannot inform the decision it is nearest to.**
[`ADR 0023`](../adr/0023-the-a-versus-f-call-is-deferred-until-the-fee-attribution-resolves.md)
defers the A-versus-F call on a stated trigger with a **hard expiry of 2026-08-31
(UTC)**, after which **A is taken by default**. This design cannot return before
`G ≥ 300`, which at any plausible accumulation rate is years away, and §0 says it
cannot return usefully even then.

> **So the A-versus-F decision will be made — one way or the other — long before
> this measurement could speak, and it would proceed identically whichever branch
> this design eventually returned. By the standard this registration is written
> to, that makes this measurement not decision-relevant to the live decision.**

That is a finding about the plan rather than about the data, and it is the second
independent reason to kill rather than re-scope. It costs nothing to learn here
and it would have cost a deploy, a dump and a session to learn afterwards.

---

## §10. What this design cannot establish, drafted before it is run

Drafted in advance, because caveats written afterwards are selected to be
survivable.

- **It cannot establish that an edge exists at Kalshi.** ADR 0021 §1's forbidden
  sentence is forbidden here too. Forecast accuracy and tradeable edge are
  different quantities separated by the fee, the spread and depth.
- **`KALSHI-LEADS` cannot establish that Kalshi holds better information.**
  §7.4. H_A predicts the identical observation. This is not a caveat on the
  branch; it is a property of the branch, fixed before the data.
- **It cannot establish anything about the consensus as a *concept*.** It scores
  the consensus **this tool builds** — sharp-anchored to a median of two to three
  books on 73.0% of rows, of unproven freshness, devigged by one named method. A
  different consensus is a different measurement.
- **It cannot separate staleness from ignorance.** ADR 0021 §7.5 is unresolved
  and ADR 0020 is unwritten. A consensus that is merely *late* loses this
  comparison exactly like one that is *wrong*.
- **It says nothing about spreads, totals, `team_total`, combos (`KXMVE`),
  in-play, the maker path, or any league outside the record's own.** §2 excludes
  all of them by predicate.
- **It cannot establish that Kalshi's mid is Kalshi's forecast.** The mid of a
  bid/ask is a convention, not an identity; at wide spreads or thin depth it is a
  weak proxy, and depth is not read by this design.
- **It cannot be rescued by more rows.** `n_rows` is uptime. Only `G` moves the
  standard error (§0.7 item 1).
- **The always-valid boundary assumes independence across games** and does not
  correct for the strategy changing between looks (§7.3). Both are inherited and
  neither is repaired here.
- **§0's arithmetic assumes `q(1−q) ≈ 0.25`.** That is measured for this record
  (99.1% near-even, ADR 0021 §4) and would need re-deriving for a record with
  lopsided lines — where it moves the requirement by at most 1.67× at `q = 0.90`,
  which changes no verdict in §0.
- **It cannot resolve the fee model, and does not depend on it.** No fee enters
  the primary estimator. That is a genuine independence and it is the one thing
  this design has going for it.
- **Counted assumptions: 2.** **A1** — an MLB or WNBA moneyline has exactly two
  settling outcomes (registered and verified on all 59 clusters, ADR 0021).
  **A2** — the mid of the derived two-sided Kalshi quote is the appropriate
  probability reading of a Kalshi price. A2 is **argued in §4.1 and measured
  nowhere.**

---

## §11. Record

- **Verdict: UNDERPOWERED — refused on power, with arithmetic (§0.8), and
  independently non-discriminating on its confirming branch (§7.4).**
- **Recommendation: KILL, not re-scope.**
- ADR 0021 §7's escape hatch moves from *"neither licensed nor refused"* to
  **refused for this instrument, with the arithmetic in §0**. It is **not**
  refused as a proposition about the world, and this document may not be cited as
  evidence that Kalshi is or is not the sharp side.
- **No live dump is licensed by this document, for this test or any other.**
