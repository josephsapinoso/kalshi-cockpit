# Pre-registration — can an Elo fit on the record see anything in Kalshi's game price?

**Written 2026-09-20, before any row of the record was read.**
**Ticket:** #115 (`josephsapinoso/kalshi-cockpit`), on Joe's decision of
2026-09-20: Elo goes to a free measurement first, and **no number reaches a
card unless it passes**.

- Owner: `pre-registrar` (agent), on behalf of Joe.
- Scored against by: `measurement-skeptic`, after the run.
- Negative-result destination: fixed in §9, **before** the result exists.
- Template: ADR 0038 Decision 4 and 5 — *compare to the price, not to the
  outcome*; *clusters bind, not rows*; a proposal to reopen must name the row
  of ADR 0038's table it overturns. Named in §1.

---

## STATUS

**UNDERPOWERED for the effect this project exists to measure, and the
arithmetic is in §P. It is adequately powered to CLOSE.**

**Also BLOCKED ON INSTRUMENT.** No whitelisted query on the live box emits the
rows this needs. §10 names the instrument and the data path. Nothing may be run
against live until that instrument exists, is reviewed, and is deployed.

Three findings this document produces before it costs anything:

1. **The design's declarable floor scales with our own model's error and does
   not fall with sample size.** DR-2 can never declare a `sigma_kalshi` smaller
   than `0.831 x sigma_model`. More games do not move that floor. To speak
   about an effect the size of the whole cost headroom (0.63 points, ADR 0027)
   the Elo's own probability error would have to be under **0.76 points**. ADR
   0037 measured the comparable in-house figure at **4.04 points**, at which
   the smallest declarable effect is **3.3 points** — five times the headroom,
   and squarely in the region CLAUDE.md rule 1 calls a bug until proven
   otherwise.
2. **The record is at most 44 days old** (first commit 2026-08-07). At
   `burn_in = 100` plus a 30% calibration split, **NFL and WNBA cannot clear
   burn-in at a 100% join yield** and NCAAF is marginal at 100% yield. MLB is
   the only league with an arithmetic path to the 300-cluster floor, and it
   needs ~80% end-to-end yield to get there. This is knowable now, for free —
   the ADR 0016 habit.
3. **Margin-of-victory is not a runnable sensitivity axis.** The schema stores
   no score anywhere (§2.4); a 1–0 encoding turns `_margin_multiplier` into a
   near-constant rescaling of `K`, so "margin on" *is* the K ladder wearing a
   different name. Registered as identified, so no later run can present it as
   a second axis.

Recommendation: **re-scope, do not kill.** Run it staged (§P.5) — Stage 1 is a
census plus `sigma_model`, reads no price at all, and can close the ticket on
its own. Stage 2 is pre-registered here in full so it cannot be redesigned
after Stage 1 is seen.

---

## §0. Disclosure — what had been seen when this was written

**Nothing from the current record.** The author read source, schema and prior
documents only. No database was opened, local or live; the local copy is not
the record and was not consulted.

Three stale figures are used as order-of-magnitude inputs to §P and are
labelled as such wherever they appear. They come from
`docs/measurements/2026-08-10-preregistration-devig-method-calibration.md` §0
and are **41 days old**:

```
recommendations   1,529 rows; 29 scored games
kalshi_markets.result   recorded 1,601 (no 1,039, yes 562); too_new 1,300
model_probability       NULL on every row
```

They are used to bound a search, never to support a conclusion, and every
quantity in the decision rule is measured in the run.

One figure from another document is load-bearing and is quoted rather than
assumed: **`sigma_model = 4.04` points**, ADR 0037's measured error for the
in-house prop model. It is used in §P as a *reference point for a comparable
in-house model*, not as a prediction of this model's error, which the run
measures.

**One input in the ticket is wrong and is corrected here.** Ticket #115 cites
`inspect_live_db.py clv-coverage` as the row-count instrument, "cheap, cap
2000". Its `QueryDef` at `scripts/inspect_live_db.py:829-841` declares
`cost=WALKS_THE_FILE`, not `CHEAP`; the 2000 is `DEFAULT_ROW_CAP`, an output
cap per section, not a bound on what is read. Running it requires
`--i-accept-the-cache-flush` and costs the desk a cache flush. See §10.

---

## §P. The power check, which comes before everything else

### P.1 What the statistic can declare, at any sample size

The registered statistic (§5) is ADR 0037's variance decomposition:

```
d            = p_model - p_kalshi            (probability points, home axis)
Var(d)       = sigma_model^2 + sigma_kalshi^2       (independence assumed, §8)
sigma_kalshi = sqrt( Var(d) - sigma_model^2 )
```

`sigma_model` is estimated, not known, so DR-2 requires positivity at every
value of an inflation ladder `{1.00, 1.15, 1.30} x sigma_model_hat`. Positivity
at the **top** of that ladder requires

```
sigma_kalshi^2 > (1.30^2 - 1) x sigma_model^2 = 0.69 x sigma_model^2
sigma_kalshi   > 0.831 x sigma_model
```

**This floor has no `n` in it.** No amount of data lowers it. It is a property
of the estimator, and it is the single most important number in this document.

| if `sigma_model_hat` is | smallest declarable `sigma_kalshi` | vs 0.63 pt headroom |
|---:|---:|---|
| 0.50 pts | 0.42 pts | resolvable |
| 0.76 pts | 0.63 pts | **exactly the headroom** |
| 1.50 pts | 1.25 pts | 2.0x the headroom |
| 4.04 pts (ADR 0037) | 3.36 pts | **5.3x the headroom** |

So the look is a **large-effect detector**. If it declares anything, it
declares a Kalshi pricing error of multiple probability points — which CLAUDE.md
rule 1 obliges us to treat as a bug in our own instrument until proven
otherwise. That obligation is written into DR-7.

### P.2 The sample-size term, on top of the floor

With `G_eff` effective clusters and `d` roughly normal, `Var(d)` has relative
standard error `sqrt(2/G_eff)`. DR-2's threshold adds `2.5 x Var(d) x
sqrt(2/G_eff)` to the floor above. At the registered `z = 2.5`:

| `G_eff` | extra requirement on `sigma_kalshi^2` |
|---:|---|
| 100 | `> 0.354 x Var(d)` |
| 200 | `> 0.250 x Var(d)` |
| 300 | `> 0.204 x Var(d)` |
| 1,000 | `> 0.112 x Var(d)` |
| 5,000 | `> 0.050 x Var(d)` |

At `G_eff = 300` the sampling term alone requires `sigma_kalshi > 0.45 x
sigma_d`. The binding constraint is still P.1 unless `sigma_model_hat` comes
back very small.

### P.3 How many games the record can possibly hold

The repository's first commit is **2026-08-07**; the population is pinned at
**2026-09-20T00:00:00Z** (§7). That is a **44-day** window and it is the hard
ceiling on the training history. Nominal games played in the window, before any
attrition from discovery, linking, settlement, pricing or the closing-line
join:

| league | in season in the window | nominal games (ceiling) | after `burn_in = 100` | x 0.70 eval split |
|---|---|---:|---:|---:|
| `baseball_mlb` | yes, to ~2026-09-28 | ~660 | ~560 | **~392** |
| `americanfootball_ncaaf` | from ~2026-08-23 | <=250 | <=150 | **<=105** |
| `basketball_wnba` | yes, season ending | ~120 | ~20 | **~14** |
| `americanfootball_nfl` | from ~2026-09-04 | ~45 | **0** | **0** |
| `basketball_nba` | **no** | 0 | 0 | 0 |
| `icehockey_nhl` | **no** | 0 | 0 | 0 |

These are ceilings at a **100% end-to-end join yield**, which will not hold: a
game reaches the priced population only if discovery saw it, the linker matched
it, `market_results` finalised it, a `recommendations` row exists for its
ticker (the only thing that causes a `closing_lines` row to be fetched —
`backend/scoring.py:markets_awaiting_scoring`), and both sides of that closing
line are readable.

**Against the registered floor of `G_eff >= 300` (DR-1), only MLB has an
arithmetic path, and it requires ~80% yield end to end.** NFL and WNBA are
declared UNDERPOWERED here, in advance, by arithmetic — they are not to be run
and then reported.

### P.4 What "more data" would buy, and what it would not

- To move P.2's term: `G_eff` of a few thousand games. The record accrues
  ~660 MLB games per 44 in-season days and the season ends 2026-09-28. The next
  comparable window is 2027-04. **Waiting is not a plan** (ADR 0038 Decision 2,
  CLAUDE.md: no roadmap may depend on an accruing look).
- To move P.1's floor: **nothing about sample size helps at all.** It needs a
  model whose own probability error is under ~0.76 points. That is a different
  model, not a bigger sample, and it is outside this ticket.

### P.5 Consequence — the staged design

Because P.1's floor is a function of `sigma_model_hat`, and `sigma_model_hat`
can be computed **without reading a single price**, the look is staged:

- **Stage 1 — census and capability.** Count the eligible population per league;
  fit Elo walk-forward; compute `sigma_model_hat` (§5.3). **No price is read,
  no `d` is formed.** DR-0 and DR-1 fire here. This is a genuine blind: the
  analyst cannot have seen a disagreement when the capability gate is decided.
- **Stage 2 — the statistic.** Only for leagues that clear DR-0 and DR-1.
  Fully specified below so that nothing about it can be chosen after Stage 1.

---

## §1. The question, as a claim that could be false

> **H1 (directional, one-sided).** For a league arm, an Elo model fit
> walk-forward on the settled game results already on the box carries
> information about that league's game moneyline that Kalshi's own price at the
> 0.0-hour horizon does not already contain: formally, on the evaluation
> holdout, `Var(d) > sigma_model^2`, i.e. `sigma_kalshi > 0`.

The null is `sigma_kalshi = 0` — *the whole disagreement between our model and
Kalshi is our own error*. That is exactly ADR 0037's finding on props, restated
for the moneyline path, which ADR 0037 explicitly did **not** cover ("Anything
about the moneyline path, which is unaffected").

**One-sided by registration.** `sigma_kalshi` is a non-negative quantity; the
alternative is only ever "greater than zero". No two-sided interval may be
reported one-sided afterwards, and no negative `sigma_kalshi_sq_hat` may be
reported as a magnitude — it is reported as a negative number with its
standard error, which is what a floored-at-zero subtraction looks like.

**The row of ADR 0038 this would overturn**, named as Decision 1 requires:

> | Information vs Kalshi's own prices | can an in-house model see Kalshi's error? | our error **exceeds** the disagreement | ADR 0036, ADR 0037 |

A PASS narrows that row to *props from public rate data*, and opens exactly one
thing: a successor registration (DR-6). It does not overturn any other row and
does not touch the `beta` verdict, the gate, or the combo rows.

---

## §2. The population, and the exclusions

### 2.1 The unit

**One row per game**, keyed by `event_links.kalshi_event_ticker`. A game's two
moneyline markets resolve from one final score; counting both would be the
inflated-`n` failure CLAUDE.md names. Spreads, totals, team totals and props
are out of scope entirely.

### 2.2 Inclusion, all of which must hold

1. `kalshi_markets.market_type = 'moneyline'`.
2. The event has an `event_links` row (`method = 'exact_alias_pair'`, the only
   value written) giving an `odds_event_id`.
3. Home and away team names come from `odds_snapshots` for that
   `odds_event_id`. **Not `odds_fixtures`**: that table's v47 backfill
   (2026-09-17, `backend/store/db.py:1222`) is bounded to seven days before the
   migration, so it cannot supply the history. If snapshots disagree on the
   home/away pair for one `odds_event_id`, the game is **refused, not
   reconciled**.
4. The Kalshi side is resolved onto the book's spelling by
   `backend/match/linker.py:resolve_outcome`, which returns `None` on ambiguity.
   A game where either side fails to resolve, or where both moneyline markets
   resolve to the same team, is **refused**.
5. `kalshi_markets.result IN ('yes','no')` on the side-resolved market —
   `market_results.py` accepts a result only at `finalized`, which is the
   property being relied on.
6. League in `discovery.IN_SCOPE_LEAGUES` **and** present in `LeagueConfig`
   presets: `baseball_mlb`, `americanfootball_nfl`, `americanfootball_ncaaf`,
   `basketball_nba`, `basketball_wnba`, `icehockey_nhl`.
7. **Scoring set only** (Stage 2): a `closing_lines` row at
   `horizon_hours = 0.0` for the chosen market, with **both**
   `yes_bid_tenths` and `yes_ask_tenths` non-NULL, `yes_ask > yes_bid`, and the
   home-axis price inside `[10, 989]` tenths.

The `[10, 989]` bound is **not chosen here**. It is transcribed from the CLV
signal-test registration §S1 as amended, already in force on
`clv-signal-pull`, precisely so this document does not get to pick a bound
after seeing a distribution.

### 2.3 Exclusions, and why each is outcome-independent

| # | excluded | reason | independent of the outcome? |
|---|---|---|---|
| E1 | no `event_links` row | the linker could not match the fixture | yes — matching is on names and start times, decided before the game |
| E2 | side unresolvable / ambiguous | `resolve_outcome` returns `None` | yes — a naming property |
| E3 | `result` NULL or not `finalized` | the outcome is not yet a permanent fact | **NO — this references the dependent variable's availability.** See below |
| E4 | no `closing_lines` row at 0.0 | the market never produced a recommendation, so no candlestick was fetched | yes — a coverage property of the recorder |
| E5 | one side of the closing line unreadable | thin book at the horizon | yes |
| E6 | first `burn_in = 100` games of a league | every rating is still the 1500 default | yes — positional |
| E7 | earliest 30% of the priced post-burn-in games | they fit the Platt calibrator | yes — positional |

**E3 is called out rather than smuggled.** Requiring a settled result is
unavoidable — Elo cannot be fit without one — but it is a filter on the
dependent variable's *existence*, not on its *value*, and the direction is
recorded: a game excluded for having no finalised result is excluded equally
whether the home or the away side would have won. The registration forbids any
exclusion whose predicate reads the *value* of `result`, `clv_tenths`,
`edge_tenths` or `d`. If one is proposed mid-run it must be written as an
amendment with its date and left unactivated for the primary.

**An exclusion may be declined.** If any rule above would, on the census, drop
so much of a league that the arm falls below DR-1's floor, the correct action
is to report the arm as UNDERPOWERED — **not** to relax the rule. Declining to
activate a registered exclusion, with the reason, is an allowed and recorded
outcome (the combo-experiment precedent); relaxing one is not.

### 2.4 What the record does **not** contain, established before the run

- **No scores.** `backend/store/schema.sql` has no scores table and no score
  column on any of its 44 tables. `GameResult.home_score` / `away_score` are
  therefore encoded **1 / 0** from `kalshi_markets.result`, and
  `use_margin_of_victory` is **False at every league**, overriding the NFL,
  NBA, WNBA and NCAAF presets. Consequence, registered: `_margin_multiplier`
  at margin = 1 is `log(2) x (2.2 / (winner_favoured x 0.001 + 2.2))`, a
  near-constant ~0.69 rescaling of `K`. "Margin on" is therefore **not a second
  sensitivity axis**; it is the K ladder, and it is registered as identified
  with it. `backend/model/margins.py` holds per-league constants but those are
  priors, not data, and are not used.
- **No rest days, no travel.** `home_rest_days`, `away_rest_days` and
  `away_travel_km` are `None` on every constructed `GameResult`, so
  `rest_bonus_per_day` and `travel_penalty_per_1000km` are inert. Registered
  now so no later arm can switch one on.
- **No season boundary inside the window.** `season` is the calendar year and
  is constant across 44 days, so `regress_to_mean` never fires and
  `season_regression` is inert. Not a sensitivity axis.
- **No draws are representable.** A Kalshi moneyline settles yes/no, so the
  1/0 encoding makes `GameResult.is_draw` unreachable and the 0.5 branch of
  `update` dead. An NFL tie enters as whatever Kalshi settled.

---

## §3. The unit of observation and the clustering variable

- **Unit:** one game = one `kalshi_event_ticker`. One `d` per game.
- **Primary cluster:** `kalshi_event_ticker`. `G` is the count of distinct
  values.
- **Second clustering, required:** residuals are correlated *within team*,
  because a team's Elo rating is shared state carried across its own games —
  a mis-rated team contributes a same-signed `d` every time it plays. The run
  therefore computes a two-way team-clustered standard error (home team and
  away team) and reports both.
- **`G_eff` is a required field on every fit** (CLAUDE.md). Computed as the
  Kish effective count under the team clustering, and **printed before any
  effect size**. DR-1 gates on `G_eff`, not on `G`. For a 30-team league with
  ~44 games per team, `G_eff` can be far below `G`, and if it is, that is the
  finding for that arm.
- The largest league's share of the pooled rows, and the largest team's share
  of a league's rows, are printed beside every aggregate (CLAUDE.md: a pooled
  number is not a finding until the parts agree).

---

## §4. The cut — every constant fixed here

There are no buckets in the primary statistic; the axes below are the cut.

**4.1 The price, on the home axis, from the price actually paid.**
`closing_lines` stores the market's own `yes_bid_tenths` and `yes_ask_tenths`.
Let `H` be the market whose YES resolves to the **home** team.

```
home_ask_tenths  =  H.yes_ask_tenths                     (H present)
                 =  1000 - A.yes_bid_tenths              (H absent; A is the away-YES market,
                                                          and this is the derived NO ask)
home_mid_tenths  =  (H.yes_bid + H.yes_ask) / 2          (H present)
                 =  1000 - (A.yes_bid + A.yes_ask) / 2   (H absent)
p_kalshi         =  home_*_tenths / 1000
```

Never the mid on the primary arm: CLAUDE.md's bucket-by-the-ask rule, and the
+25.4-point bucket that lost money. Which of `H` or the derived `A` supplied
each row is recorded as a column and its split reported.

**4.2 The mid arm is required, and here is why it is not optional.** An ask
sits above fair by a half-spread that *varies across markets*. A varying offset
is not removed by taking a standard deviation — it inflates `Var(d)`, which
inflates `sigma_kalshi`, which is the flattering direction. DR-2 therefore
requires PASS on **both** bases. If the ask arm passes and the mid arm does
not, the verdict is `CLOSED — HALF-SPREAD DISPERSION` and the result is a
statement about Kalshi's book width, not its accuracy.

**4.3 The horizon.** Primary `horizon_hours = 0.0`
(`clv.DEFAULT_HORIZON_HOURS`). Control `1.0` (`CONTROL_HORIZON_HOURS`). Both
are already written by `run_scoring_pass`; neither is chosen here.

**4.4 `K`.** League preset (`LeagueConfig.for_league`), and `{0.5x, 1.0x, 2.0x}`
of it as the registered ladder. No other value may be tried.

**4.5 Home advantage.** League preset, and `0`. Two values, no others.

**4.6 `burn_in = 100`** and **`calibration_fraction = 0.3`** — both the shipped
defaults of `walk_forward` and `calibration_split`. Not chosen here.

**4.7 Calibration.** Primary uses `PlattCalibrator` fitted on the earliest 30%
of the priced post-burn-in games (`fit_calibrator_on_holdout`, which refuses
below 50 observations and returns identity — if it refuses, that is reported,
and the arm is marked `UNCALIBRATED` and cannot PASS). Raw Elo is a diagnostic
arm only, per DR-4.

**4.8 Ordering.** Games are ordered by `MIN(commence_ms)` over
`odds_snapshots` for the fixture — ticket #26's definition, the one the ledger
and the scorer already use — ties broken by `kalshi_event_ticker` ascending.
`walk_forward`'s validity is entirely this ordering.

---

## §5. The statistic, named as an estimator

### 5.1 `d`
A **mean of game-clustered per-game differences of two probabilities on the
same game**: `d_g = p_model(g) - p_kalshi(g)`, home axis, probability points
(1 point = 1% = 10 tenths). Its **variance** is the estimand, not its mean.

`mean(d)` is reported as a **bug indicator, not a result**. A large non-zero
mean is a calibration or half-spread offset; it does not enter DR-2 because
`Var` is about the mean.

### 5.2 `sigma_kalshi`
A **residual standard deviation recovered by subtraction**, not a directly
estimated quantity:
`sigma_kalshi_sq_hat = Var(d) - (mult x sigma_model_hat)^2`.
Its null is `0`; it lives on the boundary of the parameter space, so the
nominal one-sided p-value is conservative. `sqrt(p(1-p)/n)` is **not** the
standard error of anything here and may not appear.

### 5.3 `sigma_model_hat` — estimator M1, registered as primary
**Two-path walk-forward disagreement.** Fit two Elo models over the same
chronological sequence, model A updating on even-indexed training games and
model B on odd-indexed ones; both predict every game. On the evaluation
holdout:

```
sigma_half   = sd(p_A - p_B) / sqrt(2)        # error of a HALF-history model
sigma_model_hat = sigma_half / sqrt(2) = sd(p_A - p_B) / 2
```

The second division assumes estimation-error variance is inversely
proportional to games seen. The assumption is stated because it is doing work.

**Direction, stated in advance: M1 is a LOWER bound on `sigma_model`.** It
captures estimation variance only, not mis-specification — in particular not
the under-dispersion of a short-history Elo (§8). A lower bound on
`sigma_model` **flatters** `sigma_kalshi`. That is precisely why DR-2 requires
positivity at `1.30 x sigma_model_hat` and why DR-0's gate, when it fires on
the lower bound, fires *a fortiori* on the truth.

### 5.4 `sigma_model_hat` — estimator M2, a cross-check with its own floor
For two calibrated forecasters with errors independent of the true probability,
`Brier(model) - Brier(market_mid) = sigma_model^2 - sigma_kalshi^2`. With
`E[d^2] = sigma_model^2 + sigma_kalshi^2` this gives
`sigma_model_hat_M2^2 = (E[d^2] + dBrier) / 2`.

M2 uses outcomes, so it carries an `n` floor of its own. The per-game Brier
difference has sd of order `sigma_d`, so resolving a difference of order
`sigma_d^2` needs roughly **`n > 4 / sigma_d^2`** — at `sigma_d = 5` points
that is **~1,600 games**, at `sigma_d = 3` points **~4,400**. The run computes
and prints that floor. **If the floor is not met, M2 is not computed** — it is
not computed and then quietly set aside.

M2 uses the **mid**, never the ask: an ask is biased upward by the half-spread
and a biased forecaster's Brier is inflated for a reason that has nothing to do
with accuracy.

**If M1 and M2 are both available and differ by more than 50% of the smaller,
the verdict is `CLOSED — ESTIMATORS DISAGREE` and the disagreement is the
finding.** (CLAUDE.md: a pooled number is not a finding until the parts agree.)

### 5.5 The pooled arm
Pooled `Var(d)` is computed **within-league centred** (each league's `d`
demeaned before pooling). A raw pooled variance is inflated by between-league
mean shifts, which is the flattering direction; it is reported beside the
within-league figure as a diagnostic only. Each league's share of the pooled
rows is printed.

---

## §6. The decision rule, with multiplicity counted

**Tests in the family: at most 5** — four in-season leagues plus one pooled
arm. NBA and NHL are out of season in the window and are not tested. At the
registered `z = 2.5` one-sided (`p ~ 0.0062`), expected false PASSes under a
true zero are **5 x 0.0062 = 0.031**. At `z = 2.0` they would be 0.114, which
is why `z = 2.5` and not 2.0.

The sensitivity axes are a **conjunction**, not a family: requiring PASS at
every setting can only remove findings, so they add no multiplicity.

**This is ONE look at a population pinned in §7.** No always-valid boundary is
required *because no second look is permitted*. A second look at a grown record
requires a successor registration; re-running this document's rule against more
data is forbidden and would reintroduce the 13.7% measured floor on
repeated-look crossing.

### The decision rule, verbatim

> **DR-0 (Stage 1, fired before any price is read).** For each league compute
> `sigma_model_hat` by M1 (§5.3). The smallest `sigma_kalshi` that DR-2 can
> ever declare is `sqrt(1.30^2 - 1) x sigma_model_hat = 0.831 x
> sigma_model_hat`, at any sample size. **If `0.831 x sigma_model_hat > 0.63`
> probability points** — the whole cost headroom against a sportsbook, ADR
> 0027/0028 — **then Stage 2 is not run for that league**, and its verdict is
> `CLOSED — INSTRUMENT BLUNTER THAN THE EFFECT`, recorded with
> `sigma_model_hat`, `G`, `G_eff` and the census.
>
> **DR-1 (floors).** A league arm is eligible to be reported at all only if it
> has `G >= 300` priced evaluation games **and** `G_eff >= 300`, where `G`
> counts distinct `kalshi_event_ticker` values and `G_eff` is the Kish
> effective count under two-way team clustering. The floor is 300 to match the
> house floor already in force elsewhere in this repo, chosen so that this
> document cannot pick a softer number for itself. An arm below either floor
> prints `n`, `G`, `G_eff` and the single word `UNDERPOWERED`, and **no
> `sigma_kalshi` is computed for it.**
>
> **DR-2 (PASS).** For an eligible arm, `PASS` is written if and only if, at
> `horizon_hours = 0.0`, on the Platt-calibrated model, **at every one of the
> registered settings simultaneously** — `mult` in `{1.00, 1.15, 1.30}`, price
> basis in `{derived home ask, home mid}`, `K` in `{0.5x, 1.0x, 2.0x}` of the
> league preset, home advantage in `{preset, 0}` — the quantity
>
>     sigma_kalshi_sq_hat = Var(d) - (mult x sigma_model_hat)^2
>
> exceeds `2.5 x Var(d) x sqrt(2 / G_eff)`. **Anything else is `CLOSED`.**
>
> **DR-3 (tuning).** If DR-2 holds at the league preset for `K` and home
> advantage but fails at any other registered value of either, the verdict is
> `CLOSED — TUNING-DEPENDENT`: the result is a statement about a parameter we
> chose, not about Kalshi.
>
> **DR-4 (calibration).** If the raw uncalibrated arm would PASS where the
> Platt-calibrated arm does not, the verdict is `CLOSED — OUR CALIBRATION`
> (CLAUDE.md rule 1).
>
> **DR-5 (horizon).** If the `horizon_hours = 1.0` control arm's verdict
> differs from the 0.0 primary, the verdict is `CLOSED — CONVERGENCE`.
>
> **DR-6 (what a PASS buys).** `PASS` licenses **exactly one thing: a successor
> registration.** It does not license writing `model_probability`, a card, a
> screen, a ranking, a sizing input or a bet. **No number produced by this look
> may reach a user-facing surface under any verdict**, PASS included.
>
> **DR-7 (rule 1).** If any arm returns `sigma_kalshi_hat > 2.0` probability
> points, the primary response is an investigation of the instrument, not a
> finding. Such a value asserts Kalshi misprices game moneylines by more than
> three times the entire cost headroom and more than the devig-method spread,
> on a 44-day record, and CLAUDE.md rule 1 governs: *a large apparent edge is a
> bug until proven otherwise.* The verdict in that case is
> `SUSPENDED — RULE 1` until a named defect is excluded or found.

**Marginal results.** There is no "marginal" verdict. `CLOSED` covers
everything that is not DR-2, including "positive but inside the band". The
result document must write `CLOSED` and print the numbers; it may **not** write
"suggestive", "trending", "worth another look at more data", or any phrase that
schedules a second look this registration forbids.

---

## §7. The stopping rule

- **Population pin:** every eligible game whose true commence (§4.8) is
  **strictly before 2026-09-20T00:00:00Z**. Games after the pin exist and are
  deliberately excluded; the counts here are not "how many games there are".
- **Snapshot:** one `VACUUM INTO` copy (§10), whose instant is recorded in the
  result document. Every arm runs against that one copy.
- **Number of looks: one.** No interim look, no re-run as the record grows, no
  "check again after the World Series". A second look requires a successor
  registration naming what changed.
- **Expiry:** if the instrument in §10 is not built, reviewed and run by
  **2026-10-20**, this registration expires and #115 closes as `NOT RUN`, with
  §P standing as the recorded reason. An expired registration may not be
  quietly revived against a larger record — that is a second look wearing the
  first look's clothes.

---

## §8. What would falsify H1, and what happens either way

**Falsified by:** `Var(d) <= (1.30 x sigma_model_hat)^2` on any eligible arm, or
by any of DR-3 / DR-4 / DR-5 firing, or by the arm failing DR-1's floors. The
expected shape of a falsification is the one ADR 0037 records: the subtraction
floors at zero at every registered sensitivity.

**Negative-result destination, fixed now:**
`docs/measurements/2026-09-20-elo-vs-price-result.md`, written in the **same
session as the run**, whichever way it comes out, with the census, `G`,
`G_eff`, the largest contributor's share, `sigma_model_hat` from M1 (and M2 if
its floor was met), `Var(d)`, and `sigma_kalshi_sq_hat` at every ladder value —
including negative values printed as negative.

**Consequences, both directions:**

- **CLOSED** — ADR 0038's "in-house model vs Kalshi's price" row gains a second
  instrument, on moneylines rather than props, and the model line stays closed.
  `backend/model/elo.py` stays reached by nothing but tests,
  `model_probability` stays NULL, #115 closes, and CLAUDE.md's "one signal, not
  two" paragraph gains one sentence. **No build.**
- **PASS** — nothing is built either. It buys a successor registration for an
  outcome-scored look with its own cluster floor, which the record's own
  arithmetic (`G = 713` needing ~52,000 nominal games) says is unlikely to be
  reachable on this instance.

**So this measurement is decision-relevant asymmetrically, and that is stated
rather than hidden: it can close the question and it cannot open one.** Under
the honest reading of §8's own rule — *if the answer is "we proceed either way",
say so* — the PASS branch does not fund a build, and a reader who wanted this
look to justify a card should stop here. That asymmetry is the argument for the
staged design: Stage 1 is most of the value and a fraction of the cost.

---

## §9. What this cannot establish — drafted before it is run

1. **Nothing about outcomes or win rate.** No accuracy claim, no hit rate, no
   P&L, no CLV, no bet. A PASS does not say the model wins games; it says its
   disagreement exceeds its own noise.
2. **Nothing about whether a disagreement is actionable.** `sigma_kalshi > 0`
   is a variance statement. It does not say which games, which side, in which
   direction, or whether anything survives the fee at the price actually paid.
3. **Nothing about props.** ADR 0037's bound is over prop ladders from public
   rate data. This is game moneylines; it neither confirms nor extends that ADR
   and must not be cited as doing either.
4. **Nothing about Kalshi being efficient.** A CLOSED says *our Elo cannot see
   Kalshi's error*, which is ADR 0037's exact distinction and the more limited
   of the two claims.
5. **It cannot separate "Kalshi is accurate" from "our Elo has no history" —
   and this is the caveat most likely to overturn the result.** The window is
   <=44 days. At MLB's `K = 4.0` with ~44 games per team, the reachable spread
   of ratings around 1500 is small, and an under-dispersed model produces a
   small `Var(d)` for reasons that have nothing to do with Kalshi. **A CLOSED
   is a statement about this instrument on this record, and specifically not a
   statement about Elo as a method**, nor about a longer-history Elo, nor about
   a model built on scores rather than on win/loss.
6. **Nothing about the leagues not in the window.** NBA and NHL contribute zero
   games; no verdict here transfers to them, and in-season presets exist for
   both.
7. **Nothing about `beta`, the gate, the 300-actionable-game floor, or the CLV
   question.** Different statistic, different population, different null.
8. **It does not license writing `model_probability`.** Blending a model
   probability into `fair_probability` remains a separate decision needing its
   own ADR (CLAUDE.md).
9. **The independence of model error and market error is assumed and is not
   testable here.** In the likely direction — both forecasts drawing on the
   same public information, so errors positively correlated — `Var(d)` is
   *reduced* and the test is conservative. A negative correlation would flatter
   it, and nothing in this design can rule that out.
10. **The priced population is not a random sample of games.** A closing line
    exists only where a recommendation existed. That selection is
    outcome-independent (E4) but it is not representative, and the result
    describes the games the recorder priced.
11. **Nothing about a model with scores.** Margin of victory is off because the
    schema stores no score (§2.4), not because it was tested and found useless.
12. **Nothing derived from a `LeagueConfig` value outside §4.4 and §4.5.** The
    presets are "starting points from published implementations, not fitted
    values" by their own docstring; no arm here fits them.

---

## §10. The data path — BLOCKED ON INSTRUMENT

**No sanctioned instrument emits these rows.** Surveyed: `clv-signal-pull`
(recommendations with a quote join, not a settled-game census, and no
home/away), `decision-dump` (recommendations with a `fair_prices` seek),
`clv-coverage` (counts by type and series, no per-game rows, and
`WALKS_THE_FILE` despite the ticket's note), `prop-rungs` (props), and
`inspect_live_db_decisions.py`, which by design emits rows and no aggregate.
None carries `result`, home/away and a home-axis closing line together.

**What must be built before anything is read:**

1. A new whitelisted `QueryDef` — proposed name **`elo-game-pull`** — in
   `scripts/inspect_live_db_decisions.py`, which is the module whose stated
   rule is *rows and no aggregate*. It emits, one row per (event, league):
   `kalshi_event_ticker`, `odds_event_id`, `league`, `true_commence_ms`,
   `home_team`, `away_team`, `home_market_ticker`, `away_market_ticker`,
   `result_home`, `result_away`, and, for both `horizon_hours in (0.0, 1.0)`,
   `yes_bid_tenths` / `yes_ask_tenths` / `observed_ms` and which market supplied
   them. **No statistic, no rate, no bucket, no aggregate.** Its docstring
   states what it may never report.
2. Its cost label must be **`WALKS_THE_FILE`**, honestly: the home/away join
   reaches `odds_snapshots` (2.60 GB, the largest btree on the box —
   `docs/measurements/2026-09-18-where-the-database-bytes-are.md`), because
   `odds_fixtures` cannot supply the history (§2.2).
3. **It is run against a `VACUUM INTO` copy inside the live container**, not
   against `/data/cockpit.db` — ADR 0157, an instrument may not charge its cost
   to the desk; the pattern is `scripts/rehearse_fair_price_window.py`. As of
   2026-09-18 `/data` had 13.74 GB free against a 6.48 GB file, decaying at
   ~85–110 MB/day, so the copy fits today and the free space must be re-read
   before it is taken. The copy is deleted in the same session.
4. `COPY scripts/` is already in the `Dockerfile` (line 76), so the query ships
   with a normal deploy; it must be **deployed before it is run**, not pasted
   over ssh. Inline ssh code breaks a standing rule — run committed scripts by
   path.
5. A second script, **`scripts/measure_elo_vs_price.py`**, holds every number
   in §4–§6: it builds `GameResult`s, runs `walk_forward` /
   `calibration_split`, computes M1, fires DR-0 and DR-1, and only then reads a
   price. Its module docstring states what it does not establish (§9), per
   CLAUDE.md. **Stage 1 must be runnable and reportable without Stage 2 ever
   executing.**
6. The pull is committed as a dated artefact (`.json.gz`) beside the result,
   as `2026-08-16-clv-signal-pull.json.gz` was, so the population is
   reproducible byte for byte. No operator or account data is in these rows.

**Until 1–5 exist, this look has not begun**, and no partial read — "just to
see how many games there are" — is permitted, because a census seen before
DR-0 is a census that can be argued with.

---

## §11. Amendments

None. Any amendment is appended here with its date, its author, and what it
changes, and the original text above is never edited.
