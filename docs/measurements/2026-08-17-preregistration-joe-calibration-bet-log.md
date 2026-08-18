# Pre-registration — Joe's calibration as a human forecaster

**Written 2026-08-17, before any estimate is logged and before the recording
feature is built.** No data exists. That is the point: every choice below is
fixed now so that none of them can be made after the number exists.

- Owner: pre-registrar (agent), on behalf of Joe.
- Scored against by: `measurement-skeptic`, after the single terminal look.
- Negative-result destination: fixed in §8, and it exists before the result does.
- Build spec: §9 is the field list. **§9 governs**; if the implementation and §9
  disagree, the implementation is wrong.

## Filing note — why this is not in `docs/preregistrations/`

That directory does not exist. Nine pre-registrations already live in
`docs/measurements/` under `YYYY-MM-DD-preregistration-<slug>.md`, beside their
`-result.md` files. A second home would split the convention and guarantee a
future session finds half the registrations. If Joe wants the split, move all
ten together.

## Revision note — the venue supplies most of the record

An earlier draft of this document had Joe typing eleven fields across a
two-stage form. That draft was wrong, and the correction came from surveying
`backend/kalshi/rest.py` instead of assuming. **Kalshi's portfolio endpoints
already hold everything objective about his bets, and the client code is already
written.** The design below moves every field it can onto the venue and leaves
Joe typing **two things**. §7 and §9 are rewritten around that; §0–§6, §8 and §10
are substantively unchanged, because the *statistic* did not change.

---

## §0. THE POWER CHECK, WHICH COMES FIRST

Three numbers decided the design. Each was computed before any data was seen and
each killed an option that was on the table.

### 0.1 The statistic and its noise

`B = mean(p_i - y_i)`, where `p_i` is Joe's stated probability **for the side he
ended up holding** and `y_i ∈ {0,1}` is whether that side won. `sd(p - y)` is
dominated by `Var(y) = q(1-q)`; across the plausible range of what he bets (`q`
from 0.55 to 0.80) that is `sd(d)` between 0.42 and 0.50. **0.50 is used
throughout — the conservative end.** Design effect from clustering by game is
taken as 1.15 (mean cluster size ~1.3, intra-cluster correlation up to 0.5).

### 0.2 An always-valid boundary would kill this measurement

The repo's default — and this registrar's default — is a confidence sequence, so
that looking whenever you like costs nothing. **Here it costs everything.**

| n (bets) | `se` | MDE at 80% power, **one terminal look** | MDE at 80% power, **always-valid** |
|---|---|---|---|
| 100 | 0.0536 | 13.3 pts | 26.1 pts |
| 150 | 0.0438 | 10.9 pts | 19.7 pts |
| 200 | 0.0379 | **9.4 pts** | **16.3 pts** |

The registered target is a ~9-point bias against a typical beginner band of
10–20 points. The always-valid design cannot resolve anything inside that band at
any reachable `n`. The single-look design resolves the target at ~76% power and a
13-point bias at ~95%.

**Therefore: exactly one look, and interim looks are forbidden rather than
priced.** This inverts the repo's usual rule and the inversion is the whole
design. It is legitimate only because the stopping rule (§5) is fixed in advance
and outcome-independent, and because §7.6 makes the single-look claim *auditable*
rather than aspirational.

### 0.3 The $100 bankroll arm is outcome-dependent, and stake size decides
whether that matters

Simulated, 20,000 paths, $100 bankroll, 200 bets, −3% EV per bet:

| stake | P(bankroll stops him before 200 bets) |
|---|---|
| $2 | **0.002** |
| $3 | 0.049 |
| $5 | **0.269** |

Stopping because the money ran out is **stopping on the dependent variable**. It
truncates the sample at a point selected by his losses, which biases `mean(y)`
down and therefore biases `B` **up — in the direction of the hypothesis**. At the
fleet's $5 outer edge that fires more than a quarter of the time and the
measurement is worthless. At $2 it is negligible.

**Registered protocol constraint: logged bets are staked at $2 or less.** This is
not risk advice; it is the only thing keeping the stopping rule outcome-
independent. `B` is **unweighted by stake**, so the constraint costs the
statistic nothing. Compliance is checked against `balance()` and the venue's own
cost fields (§9), not against Joe's memory.

### 0.4 The date arm needs 1.5 bets/day

2026-08-20 to 2026-12-31 is 133 days. 200 bets is 1.50/day; 150 bets is
1.13/day. It is entirely plausible the date arm binds well short of 200. §4
therefore sets an asymmetric floor rather than assuming `n = 200`.

### 0.5 Verdict of the power check

**The primary (calibration) arm is adequately powered, conditional on a single
terminal look, `n ≥ 120`, and a $2 stake cap.** All three are registered below.

**The secondary (CLV) arm is UNDERPOWERED and may not produce a verdict.** At
`n = 200` its MDE at 80% power is 0.64–1.06 cents depending on `sd(CLV)`, against
a total taker cost headroom of **0.63 cents** (ADR 0027/0028). It can only
resolve effects larger than the entire advantage this project exists to hunt. It
is registered as descriptive-only for exactly that reason, decided before any CLV
was scored.

---

## §1. The question

**PRIMARY, and it is calibration.**

> Joe's stated pre-price probabilities are systematically higher than the
> frequency with which those outcomes occur: `B = E[p - y] > 0`.

One-sided, direction positive. Registered as one-sided **now**, so that a
one-sided report later is not a silently doubled false-positive rate. A
significantly negative `B` (underconfidence) is reported as
`UNREGISTERED-DIRECTION`, hypothesis-generating only, and does not become a
finding.

**SECONDARY, and it is CLV.**

> Mean CLV, clustered by game, over logged bets scoreable against Kalshi's close,
> is greater than zero.

Two-sided, descriptive, **no verdict** (§0.5).

**Why calibration is primary.** The town hall established that 200 bets is ~100x
short of establishing whether Joe has an edge, and CLV — though ~10x less noisy
than win/loss — is still short of the 0.63-point magnitude that would matter.
Calibration asks a question 200 bets can actually answer, and its answer changes
something (§8). CLV is retained because it is nearly free once the ticker is
logged and the venue supplies the price, and because refusing to record it would
mean re-running five months to get it.

**Pre-commitment: both are reported, in full, with intervals, regardless of which
looks better.** Neither may be promoted or demoted after the look. A write-up
reporting one and not the other is void.

**Quantifier discipline.** "Systematically" means exactly `E[p - y] > 0` and
nothing more. It does not claim the bias holds in every sport, every price band,
or every month. §4's slices are the only permitted statements about
heterogeneity, and none of them is confirmatory.

---

## §2. The population, and the exclusions

**Unit of observation: one logged estimate matched to one settled Kalshi
position.**

**Cluster: `cluster_key`, the game.** Derived as `event_ticker` when available,
else `ticker` — and `event_ticker` is supplied directly by
`/portfolio/settlements`. Two bets on one game's moneyline and total resolve from
one final score and are **not** independent. This repo already shipped a gate
that counted 400 rows on one ticker as 400 observations; the fix was clustering
by game and it is not relitigated here. Every standard error below is
game-clustered. `G` counts distinct `cluster_key`, never rows.

### In the primary population

A row is in iff **all** of:

1. `matched_position_id IS NOT NULL` — the estimate matched a real venue
   position (§7.3). This replaces the old self-reported "did you bet?".
2. `is_sports = 1` — derived from the series ticker.
3. `is_multi_leg = 0`.
4. `stated_probability_is_revised = 0`.
5. `outcome_win IS NOT NULL` — `market_result` was `yes` or `no`.
6. `estimate_server_ms < position_first_seen_ms` — the estimate was recorded
   before the venue knew about the trade (§7.2).
7. `protocol_calibration_bet = 0` — excludes bet #1 (§7.5).

### The exclusions, each with a reason independent of the outcome

| Rule | Why it cannot reference the outcome |
|---|---|
| **Multi-leg / `KXMVE` combos excluded** | A compound stated probability has no single market settlement to score against. Structural. **This one has teeth: 43 of the 55 existing settlements on the account are combos.** |
| **Non-sports markets excluded from primary** | Forecasting a Fed decision is a different skill from forecasting a ballgame. Recorded and reported separately, never pooled. |
| **Voided / cancelled markets excluded** | A void is the absence of an outcome, not an outcome. |
| **Revised probabilities excluded** | A revision is adjacent to information arriving. The field is write-once (§7.4); this rule catches a revision that reaches the record anyway. |
| **Estimates with no matching position excluded from primary** | He estimated and did not bet. Retained in the record and re-run as a registered sensitivity (§9.5), because *not betting* is itself unselected on outcome. |
| **Bet #1 excluded** | It exists to capture the `/portfolio/fills` wire shape (§7.5). Registered before it is placed, so it cannot be chosen for its result. |
| **In-play bets: INCLUDED in primary, EXCLUDED from CLV** | A live forecast is still a forecast, so it belongs in calibration. A "closing line" does not exist for a market whose event has started. |

### Exclusions this registration explicitly REFUSES to make

- **Bets under 25c are NOT excluded.** The 25c rule is trading advice about
  spread cost. Longshots are precisely where overconfidence is largest, so
  excluding them would bias the primary toward the null. Someone will propose
  this later; it is refused now, in writing.
- **Positions Joe exited before settlement are NOT excluded**, and `y_i` is the
  market's eventual settlement regardless of whether he held. Scoring on his exit
  would measure exit timing, not forecasting. (Early exits may be invisible to
  `/portfolio/settlements`; §7.5 registers how they are caught and counted.)
- **No bad run, no losing streak, no sport, and no month may be excluded after
  the fact.** The list above is closed. An exclusion added at analysis time voids
  the registration.

### The conditional exclusion, and the standing refusal to activate it

If `G < 50` at the stop, no test is computed at all (§4). This is a live pattern
in this repo: a combo experiment pre-registered an exclusion and the agent
correctly **refused to activate it** when the sample turned out thin. The same
refusal applies here in reverse — a thin sample produces INSUFFICIENT, not a
loosened rule.

### The CLV secondary population

Primary population, plus `is_in_play = 0`, `closing_line_id IS NOT NULL`, and
`estimate_server_ms <= closing_line.observed_ms` — the entry must precede the
close it is scored against. `backend/analysis/clv.py` already enforces this, and
the reason is that otherwise market drift enters the number directly.

`n_missing_close` and **the win rate of the missing-close subset** are reported
beside the CLV number, so a reader can judge whether unscoreable markets differ.

---

## §3. The statistic, named as an estimator

**Primary: `B_hat` is a mean of game-clustered observations.** Not a proportion.
`sqrt(p(1-p)/n)` is wrong here and must not appear in the write-up.

`stated_probability_bp` is recorded as **P(YES)** (§9.2). The side is supplied by
the venue. So:

```
p_side_i = stated_probability_bp_i / 10000            if side_i = 'yes'
p_side_i = 1 - stated_probability_bp_i / 10000        if side_i = 'no'

y_i      = 1 if market_result_i == side_i else 0

d_i      = p_side_i - y_i
B_hat    = (1/n) * sum_i d_i

                 G      sum_c ( sum_{i in c} (d_i - B_hat) )^2
se^2  =  -----  *  ------------------------------------------
                G - 1                    n^2

z        = B_hat / se        (one-sided, positive direction)
```

`G/(G-1)` and nothing else, matching `backend/analysis/signal_test.py`. No second
finite-sample correction is added, however conventional elsewhere, without an
amendment.

### Why not the alternatives — decided now, not after

- **Brier score: rejected.** Not directional. It confounds calibration with
  resolution, so it cannot answer "is he overconfident".
- **ECE: rejected.** Bin-dependent, biased upward at small `n`, no clean sampling
  distribution to build an interval from.
- **Calibration curve with bins: rejected as the primary.** At `n = 200` across
  four bins the per-bin `n` is ~50 and every edge is a researcher degree of
  freedom. Choosing bins after seeing data is the whole failure mode.
- **Logistic slope (`y ~ logit(p)`): rejected as the primary.** A slope below 1
  is the textbook overconfidence statistic, but it is a ratio, its standard error
  at `n = 200` is wide, and its null (`slope = 1`) is not the null §8 needs.

`B_hat` is chosen because it is a mean, its null is exactly zero, its direction
is exactly the hypothesis, and it requires no binning.

### The descriptive calibration curve, bins fixed HERE

Reported always, tested never. Bins on `p_side`, four edges fixed in advance:

```
[0.50, 0.60)   [0.60, 0.70)   [0.70, 0.85)   [0.85, 1.00]
```

Any bin with fewer than 5 expected outcomes on either side is printed with its
counts and **no interval**, per the repo's "read `n` before the effect size"
rule.

### Secondary: mean CLV

`clv_tenths` from `backend/analysis/clv.clv_tenths()`, unmodified — it handles
the YES/NO asymmetry correctly, and that correction was expensive. Its
`entry_ask_tenths` argument is **the venue's own average entry price** (§9.1),
never a mid. Game-clustered mean, same sandwich. Primary horizon 0.0h, control
horizon 1.0h, and `horizons_agree` is run: **if the result moves between horizons
it was convergence, not edge**, and that verdict is registered now.

---

## §4. The decision rule

**Quote this verbatim into the write-up.**

> The single terminal look occurs once, after the stopping rule of §5 has fired,
> and never before. Let `B_hat` be the game-clustered mean of `(p_side_i - y_i)`
> over the §2 primary population, `se` its game-clustered standard error, and `G`
> the number of distinct `cluster_key` values in that population.
>
> - If `G < 50`: **INSUFFICIENT.** No test statistic is computed and no verdict
>   is issued. The record is reported descriptively.
> - If any tripwire in §7.7 has fired, or `coverage < 0.90` per §7.5: the verdict
>   is prefixed **`CONTAMINATED-`** and may not be cited as a measurement of
>   calibration.
> - If `B_hat - 1.645 * se > 0`: **OVERCONFIDENT.**
> - Else if `G >= 120` and `B_hat + 1.645 * se < 0.10`: **NOT OVERCONFIDENT AT
>   THE 10-POINT LEVEL.**
> - Else: **UNRESOLVED.**
>
> A result with `B_hat + 1.645 * se < 0` is reported as
> **`UNREGISTERED-DIRECTION`**, is hypothesis-generating only, and does not
> become a finding.

### Why the asymmetry

The positive branch is a valid one-sided test at any `n` where the normal
approximation holds. The negative branch is an **equivalence test**, and
equivalence needs power: at `G = 120`, `1.645 * se = 0.080`, so declaring
requires `B_hat < 0.020`, which happens ~66% of the time under a true zero. Below
`G = 120` the negative branch cannot rule out the lower half of the beginner
overconfidence band and is therefore forbidden.

**δ = 0.10 is the equivalence bound and it was set by power, not preference.** At
`n = 200`, `1.645 * se = 0.062`, so any δ below ~0.07 is unachievable even
against a true zero. δ = 0.10 is the bottom of the stated 10–20 point beginner
band, so clearing it is the meaningful negative: *his bias is smaller than a
typical beginner's.* It is **not** "he is well calibrated", and §10 says so.

### Multiplicity, counted now

**Confirmatory tests: 1.** The primary, one-sided at α = 0.05, one look.

**Pre-specified secondary tests: 4**, each two-sided at Bonferroni
α = 0.05/4 = 0.0125, `|z| >= 2.50`, each labelled **non-confirmatory**:

1. **Favourite vs longshot**, split at `entry_price_tenths` = 500 (50c) — **the
   venue's own average price actually paid, never a mid.** A bucket in the
   predecessor project showed +25.4 points and lost money for exactly this
   reason. Test: the difference of two clustered means.
2. **Largest sport vs all others pooled.** Any sport with fewer than 20 bets is
   pooled into `other` *before* the split. One test, not one per sport.
3. **First half vs second half of the sample by `estimate_server_ms`.** The
   learning / non-stationarity check: Joe sees his own Kalshi balance whatever
   the embargo does, so his behaviour can drift mid-study and a pooled `B` would
   average two regimes.
4. **Logged vs unlogged win rate** (§7.5) — the selective-logging test.

Expected false findings across all five tests under a pure null: **0.20**.

**All other slices are FORBIDDEN.** Named explicitly because they will be asked
for: day of week, time of day, stake size, whether he watched the game, streak
position, individual sport beyond test 2, individual team, market type, maker vs
taker, and any slice invented after the look. Reporting one voids the
registration.

**A pooled number is not a finding until the parts agree.** The per-sport view
and the largest sport's share of `n` are printed beside `B_hat` always.

---

## §5. The stopping rule, and interim looks

**Collection ends at the FIRST of:**

1. **200 logged bets** in the §2 primary population, or
2. **2026-12-31, 23:59:59 UTC**, or
3. **the $100 is gone** — `balance()` below the point where a further bet can be
   placed.

**No reload. A reload voids the result** and the record restarts as a separate,
separately-registered study.

**Arm 3 is the contaminating one** (§0.3) and the $2 stake cap exists to make it
fire with probability ~0.002. **If arm 3 fires anyway, the verdict is prefixed
`CONTAMINATED-STOPPING`** and the result is reported as an upper bound on `B`
rather than an estimate, because outcome-dependent truncation biases `B` upward.
Arm 3 is evaluated against the venue's `balance()`, not against Joe's report of
it.

**Interim looks are FORBIDDEN, not priced.** §0.2 shows that permitting them
costs 1.7x the effect size and puts the target outside reach at every achievable
`n`. This is the single most load-bearing constraint in the document.

**What the embargo covers.** Until the stop fires, no interface, endpoint, export
or agent may display, over the estimate log: any aggregate, any win rate, any
mean, any calibration curve, any CLV figure, any anchor-gap figure, or any
server-captured quote. Joe may see the list of estimates he entered — he needs it
to avoid double-entry — and nothing derived from their outcomes.

**The daily portfolio poll (§7.5) is not a look** and does not enter
`bet_estimate_looks`. It writes venue rows and computes no statistic on the
primary population. A poll that emits an aggregate is a look and voids the rule.

**What the embargo cannot cover, stated plainly:** he sees his own Kalshi balance
and remembers his own results. He has an informal running look and nothing can
take it away. That does not inflate our look count, but it does let his behaviour
drift; test 3 exists to detect that and it is non-confirmatory.

---

## §6. What would falsify this

The hypothesis is `B > 0`. It is falsified by `B_hat + 1.645 * se < 0.10` at
`G >= 120`: the data are then inconsistent with a bias as large as the smallest
typical beginner overconfidence.

Concretely, at `G = 200` any `B_hat` below **+0.038** (3.8 points) falsifies it;
at `G = 120`, any `B_hat` below **+0.020**.

The hypothesis is **not** falsified by an `UNRESOLVED`, and `UNRESOLVED` may not
be written up as "no overconfidence found". This repo has a live example of that
distinction being enforced: `beta` is formally `UNRESOLVED` and CLAUDE.md refuses
to report it as "no signal" despite an 8.3-sigma gap.

---

## §7. THE INTEGRITY PROBLEM

### 7.1 What the venue solves, and what it does not — the honest split

The claim put to this registration was that the integrity problem "may be largely
SOLVED" by two independent clocks. **It is not, and the distinction matters
enough to lead with.** The problem has two halves:

**(a) Did he transact before recording the estimate?**
**SOLVED, and solved well.** Our server stamps `estimate_server_ms`; Kalshi
independently stamps the fill and returns the price, count and fee. Neither clock
is under Joe's control and neither is self-reported. A transaction that preceded
its estimate is now *visible*, and §2 rule 6 excludes it automatically.

**(b) Did he see a price before recording the estimate?**
**NOT SOLVED. Untouched. Unchanged by any of this.** He can open Kalshi, read
62c, close it, open the logger, type 68%, and transact a minute later. Both
clocks agree, every venue field is authoritative, and the measurement is still
worthless.

**(b) is the load-bearing half.** (a) was always the lesser threat — it requires
him to bet *and then* fabricate a prior estimate, which is deliberate deception.
(b) requires only ordinary human anchoring and can happen entirely
unconsciously. **So the venue has solved the half that needed dishonesty and left
the half that does not.** The verifiability gain is real but it must not be
reported as having secured the pre-price claim.

What the venue *does* buy for (b) is one new diagnostic, §7.7's T3, which did not
exist in the self-reported design.

### 7.2 The two clocks, precisely

- `estimate_server_ms` — **our** server clock, at the instant the estimate is
  committed. Never the phone's clock, which its owner controls.
- `position_first_seen_ms` — the earliest venue-side evidence of the trade:
  `fills[].created_time` when `/portfolio/fills` yields it, else the poll instant
  at which the position first appeared, else `settled_time`. **Which of the three
  was used is stored per row** (`position_time_source`), because a fallback to
  `settled_time` makes §2 rule 6 nearly vacuous — a settlement is hours after the
  game — and a reader must be able to see that rather than infer it.

Rows whose only available source is `settled_time` still enter the primary
population but are counted and reported separately, because dropping them would
condition on venue data availability, which is not obviously independent of the
outcome (thin markets both settle oddly and behave differently).

### 7.3 Matching an estimate to a position

Registered before any data: an estimate matches the **earliest** venue position on
the same `ticker` with `position_first_seen_ms` in the window
`(estimate_server_ms, estimate_server_ms + 24h]`.

- 24 hours, because beyond a day the estimate is stale relative to the price it
  is being scored against.
- If two estimates on one ticker compete for one position, the **later** estimate
  matches and the earlier is `unmatched`. Registered now so it is not chosen
  later.
- An estimate with no match in the window is `unmatched` — he estimated and did
  not bet. It leaves the primary population and enters the §9.5 sensitivity.
- A position with no estimate is an **unlogged bet** and is the §7.5 denominator.

### 7.4 Write-once, enforced server-side

`stated_probability_bp` is **write-once**. The server rejects any `UPDATE` to it.
A correction path exists only as an append-only revision row carrying a reason
string, setting `stated_probability_is_revised = 1`, which excludes the row (§2).
An `UPDATE` that silently succeeds is the failure this clause exists to prevent,
and the test for it **must be verified by disabling the guard and watching the
test fail**, per CLAUDE.md.

### 7.5 Attrition, now a measured rate rather than an invisible bias

This is the largest gain from the venue, and it is genuinely large. **Kalshi
reports the position whether or not Joe logged an estimate**, so unlogged bets
appear as a denominator instead of vanishing.

**Pre-committed report, printed at the top of the result file:**

```
coverage = estimates matched to a position / venue positions observed
```

- **If `coverage < 0.90`, the verdict is prefixed `CONTAMINATED-ATTRITION`.**
- Unlogged positions still carry a ticker, a side and a `market_result`, so
  **their win rate is computable.** Test 4 of §4 compares it against the logged
  bets' win rate. A significant difference is direct evidence that what got
  logged was selected on how it went. Reported always.
- **Early exits**: a position closed before settlement may not appear in
  `/portfolio/settlements`. `positions()` and `fills()` are polled to catch them;
  their count is reported. If they cannot be recovered, `coverage` is reported as
  a *lower bound* and labelled so.

**The protocol precondition, and why bet #1 is excluded.** The per-fill wire
shape has **never been observed on this account** (measured 2026-08-09 and
2026-08-10, eight query shapes, all empty). CLAUDE.md forbids hand-constructed
wire fixtures. Therefore: **bet #1 is a protocol calibration bet.** Its only
purpose is to make a real fill exist so `scripts/capture_fills_fixture.py` can
capture the shape and a parser can be written against it. It is flagged
`protocol_calibration_bet = 1` and excluded from the population by §2 rule 7 —
registered before it is placed, so it cannot be chosen for its result.

### 7.6 The poll cadence, and what a missed window costs

**Registered: `/portfolio/settlements`, `/portfolio/fills`, `/portfolio/positions`
and `/portfolio/balance` are polled once daily at a fixed UTC time, every day the
study is open.**

The retention asymmetry is measured, not assumed, and it decides the failure
mode:

| endpoint | measured reach | what a gap costs |
|---|---|---|
| `/portfolio/fills` | **~3 months upper bound, no measured lower bound.** Returned empty on an account whose settlements go back to 2025-11 | the entry timestamp and the taker/maker flag — i.e. §7.2's best `position_first_seen_ms` and §7.1(a)'s strong form |
| `/portfolio/settlements` | **at least 9 months** — 55 records, 2025-11-27 to 2026-05-10, one page, empty cursor | nothing observed. This is the safety net |

**This is why the primary statistic survives a broken poller.** `market_result`,
`event_ticker`, `ticker`, side (from `yes_count_fp` / `no_count_fp`) and average
entry price (from `*_total_cost_dollars / *_count_fp`) all come from
`/portfolio/settlements`, which has never been observed to drop history. **A
gap therefore degrades the integrity check, not the estimand.**

Registered tripwires on the gap between successive *successful* fill polls:

- **> 30 days** → affected rows flagged `RETENTION-AT-RISK` and counted in the
  result.
- **> 75 days** → `position_first_seen_ms` for affected rows falls back per
  §7.2 and `coverage` over that interval is reported as **unverifiable**.
- **A gap voids no row.** Voiding on a poller outage would remove rows for a
  reason correlated with calendar time and therefore with sport and with Joe's
  betting streaks. The gap is reported instead.

### 7.7 The anchoring tripwires, with thresholds fixed now

At estimate time the **server independently fetches and stores the Kalshi quote
and never shows it to Joe**. He cannot alter it, cannot see it, and cannot know
what it was. The mid is the correct reference **here and only here** — this is a
diagnostic, not a price anyone transacts at.

```
implied_bp     = (server mid in tenths) * 10          # P(YES) reference
anchor_gap_bp  = stated_probability_bp - implied_bp
```

Note both are P(YES), so no side adjustment is needed.

**T1.** `sd(anchor_gap_bp) < 300` (3 points) → **ANCHORING-SUSPECTED.** A stated
probability that is a near-deterministic function of a price he claims not to
have seen is the signature of "read the price, add a fixed offset". *Variance* is
the right diagnostic, not the mean: Joe only bets when he thinks the price is
wrong, so selection pushes the gap large even absent anchoring — but it does not
make the gap **narrow**.

**T2.** `fraction(|anchor_gap_bp| <= 200) > 0.40` → **ANCHORING-SUSPECTED.**

**T3 — new, and it exists only because of the venue data.** The estimate-time
quote and the venue's actual entry price differ whenever the market moved between
the two. On the subsample where they differ by at least 100 tenths (1c), compare
`sd(gap to estimate-time quote)` against `sd(gap to entry price)`. If his
estimates track the **estimate-time** quote materially more tightly, he was
looking at the app when he typed. **Reported with no threshold and no verdict** —
it has power only when prices moved, and its subsample size is unknown in
advance. Registered as a diagnostic so it cannot be invented afterwards.

T1 or T2 firing prefixes the verdict with `CONTAMINATED-` (§4). All three are
declared **heuristic tripwires, not tests**; they have no null distribution and
no p-value and must never be reported as though they did.

### 7.8 What remains unverifiable, and it is not small

- **He can open the Kalshi app, read the price, then open the logger and type a
  number.** Two clocks do not touch this. T1–T3 detect the crude version; a
  careful or unconscious version passes all three. **This is the hole.**
- **He cannot unsee prices from before the estimate.** A market he browsed
  yesterday anchors today's estimate with no timestamp anywhere recording it.
- **`had_already_opened_kalshi` is self-reported**, so it is evidence about his
  honesty, not his behaviour. Recorded because a *pattern* in it is informative;
  never used as a filter.
- **The estimate itself is the one field with no venue counterpart** and is
  therefore unauditable in principle. Everything objective is now authoritative;
  the single subjective field is the whole measurement.
- **A rejected design, and why:** requiring an estimate on markets he is *not*
  betting would give a selection-free calibration sample. Rejected on the entry
  budget (§9.4) — attrition is a larger threat here than selection, and §7.5 now
  measures selection anyway.

**Honest summary: the venue has made the record objective and attrition
measurable. It has not made the pre-price claim verifiable.** Any write-up that
omits this paragraph is void.

---

## §8. Consequences, in both directions

| Verdict | What is built | What is killed |
|---|---|---|
| **OVERCONFIDENT** | A calibration shrinkage step: Joe's stated `p` is shrunk toward the market price by the measured `B_hat` before it reaches any sizing calculation, and the sizing UI refuses his raw number. | Sizing on an unadjusted stated probability. |
| **NOT OVERCONFIDENT AT THE 10-POINT LEVEL** | Nothing. The log stays as a record; the shrinkage step is not built. | The shrinkage proposal, permanently, unless re-registered at a larger `n`. |
| **UNRESOLVED / INSUFFICIENT** | Nothing. | Nothing. The write-up is published anyway. |
| any **`CONTAMINATED-`** prefix | Nothing. | The measurement. It is reported and not cited. |

**Negative-result destination, fixed before the result exists:**
`docs/measurements/2026-12-31-joe-calibration-bet-log-result.md`. One file, one
filename, written whichever way it comes out; the `UNRESOLVED` and `INSUFFICIENT`
branches go in the same file. A pre-registration whose negative branch has no
destination produces a negative result that quietly never gets written.

**Is this decision-relevant? Partly, and the honest answer matters.** It genuinely
forks a build decision. But the tool places no orders — `ORDERS_ARE_DRY_RUNS =
True` at `backend/store/orders.py:129` — so the strongest consequence lands on
Joe's own hand-betting, which the tool cannot enforce. **If Joe would size the
same way regardless of the answer, this measurement is not decision-relevant and
should not be run.** That question is cheaper to settle now than in December.

---

## §9. THE FIELD LIST

The build spec. Money is **integer tenths of a cent** (`core/prices.py`,
`PRICE_MAX = 1000`). **Unreadable resolves to `None`, never `0`** — a settled
loser genuinely trades at 0, so a substituted zero is indistinguishable from
data. Every dollar string from the venue goes through `dollars_to_tenths`.

### 9.1 (a) WHAT KALSHI SUPPLIES — endpoint and wire field

Nothing in this table is typed by anyone. All of it is authoritative.

| our column | units | endpoint | wire field | which part of the analysis needs it |
|---|---|---|---|---|
| `ticker` | TEXT | `/portfolio/settlements` | `ticker` | joins estimate to outcome; derives sport / sports-ness / multi-leg |
| `event_ticker` | TEXT | `/portfolio/settlements` | `event_ticker` | **the cluster key.** Supplied directly — no inference needed |
| `market_result` | TEXT | `/portfolio/settlements` | `market_result` | `y_i`. The dependent variable |
| `settled_ms` | INTEGER epoch ms | `/portfolio/settlements` | `settled_time` | ordering; the void exclusion; `position_first_seen_ms` last-resort fallback |
| `side` | TEXT 'yes'\|'no' | `/portfolio/settlements` | derived: `yes_count_fp > 0` vs `no_count_fp > 0` | **removes a field from Joe's form** (§9.2). Selects which settlement counts as a win |
| `contracts` | INTEGER | `/portfolio/settlements` | `yes_count_fp` / `no_count_fp` | the entry-price denominator; the $2 cap check |
| `entry_price_tenths` | INTEGER tenths | `/portfolio/settlements` | `yes_total_cost_dollars / yes_count_fp` (or the `no_` pair) | **the price actually paid, from the venue.** §4 test 1 buckets on this and CLV takes it as `entry_ask_tenths`. It is *not* a mid and nobody can accidentally make it one |
| `fee_cost_tenths` | INTEGER tenths | `/portfolio/settlements` | `fee_cost` | completeness; feeds the fee/H4 work at no extra cost |
| `position_first_seen_ms` | INTEGER epoch ms | `/portfolio/fills` `created_time`, else poll instant, else `settled_time` | — | §2 rule 6, the two-clock check |
| `position_time_source` | TEXT | — | which of the three above was used | §7.2. Without it a `settled_time` fallback silently guts rule 6 |
| `is_taker` | INTEGER 0/1 | `/portfolio/fills` | `is_taker` | descriptive only. **Explicitly forbidden as a slice** (§4) |
| `kalshi_fill_id` | TEXT | `/portfolio/fills` | fill id | reconciliation identity |
| `balance_tenths` | INTEGER tenths | `/portfolio/balance` | balance | §5 arm 3, evaluated on the venue's number rather than Joe's memory |

**Caveat that must travel with the settlement fields:** the 55 existing records
are dated 2025-11 to 2026-05 and **the fee schedule was revised in July 2026**.
They are pre-revision evidence and must not be pooled with study-period rows for
any fee purpose.

**Caveat on `entry_price_tenths`:** it is a *position* average across however many
fills built it. At a $2 unit most positions are one fill, but a position built at
two prices has a blended entry, which is a real bucketing hazard for §4 test 1.
Where `/portfolio/fills` supplies the per-fill prices, `n_fills_in_position` is
recorded and positions with `> 1` are reported as a count beside test 1.

### 9.2 (b) WHAT JOE TYPES — two fields

| field | type / units | why it cannot come from the venue |
|---|---|---|
| `ticker` | TEXT, chosen from a searchable list of discovered markets — **one tap, not typing** | the venue cannot know which market he is about to think about |
| `stated_probability_bp` | INTEGER, basis points 1–9999, CHECK BETWEEN 1 AND 9999, **WRITE-ONCE** | **the only field in this entire document that Kalshi cannot supply.** It is the measurement |

**`stated_probability_bp` is P(YES), always — not "probability my side wins".**
This is a deliberate change and it buys three things:

1. **It removes the `side` field from the form**, because the venue reports the
   side he actually took.
2. **It removes an ambiguity.** "Probability my side wins" is undefined until he
   has picked a side, and it invites a different mental task on YES bets than on
   NO bets.
3. **It decouples the estimate from the transaction further.** He can now form
   and record an estimate *before deciding which side to take*, which is a
   strictly more pre-price act. §3 converts to `p_side` at analysis time.

**Optional third field — one tap, and the first thing cut if entry is slow:**

| field | type | why |
|---|---|---|
| `had_already_opened_kalshi` | INTEGER 0/1, asked **before** the probability input is enabled | §7.8. The one recorded signal about the irreducible hole |

### 9.3 (c) WHAT WE DERIVE OR CAPTURE

Written by the server or the harness; never typed, never editable.

| field | type / units | source | why |
|---|---|---|---|
| `id` | INTEGER PK | — | row identity |
| `estimate_server_ms` | INTEGER epoch ms, **server clock** | server | clock A of the two-clock check; orders §4 test 3 |
| `estimate_client_ms` | INTEGER NULL | client | divergence from the server stamp is a tamper diagnostic; never used in analysis |
| `cluster_key` | TEXT NOT NULL | `COALESCE(event_ticker, ticker)` | **THE clustering variable.** Every `se` in §3 groups on this |
| `server_yes_bid_tenths` | INTEGER NULL tenths | server fetch at estimate time | T1/T2/T3. **Never rendered to Joe, at any time, until the stop** |
| `server_yes_ask_tenths` | INTEGER NULL tenths | as above | as above |
| `server_quote_observed_ms` | INTEGER NULL | server | proves the quote is contemporaneous with the estimate |
| `server_quote_unreadable_reason` | TEXT NULL | server | why the quote is `NULL`. Unreadable is not zero |
| `stated_probability_is_revised` | INTEGER NOT NULL DEFAULT 0 | server | §2 exclusion; §7.4 |
| `protocol_calibration_bet` | INTEGER NOT NULL DEFAULT 0 | set on bet #1 only | §7.5 |
| `is_in_play` | INTEGER NOT NULL | `estimate_server_ms >= commence_ms` | in primary, out of CLV |
| `is_sports` | INTEGER NOT NULL | series ticker | primary population filter |
| `is_multi_leg` | INTEGER NOT NULL | `KXMVE` / combo prefix | §2 exclusion — 43 of 55 historical settlements are combos |
| `sport` | TEXT NULL, fixed enum | series ticker | §4 test 2 and the per-group pooling print |
| `matched_position_id` | INTEGER NULL | §7.3 matcher | §2 rule 1. NULL = estimated, did not bet |
| `match_status` | TEXT | 'matched'\|'unmatched_no_position'\|'position_unlogged' | §7.5 coverage |
| `n_fills_in_position` | INTEGER NULL | `/portfolio/fills` | the blended-entry hazard, §9.1 |
| `outcome_win` | INTEGER NULL 1\|0 | `market_result == side` | `y_i`. **`NULL` when unsettled or void — never `0`** |
| `closing_line_id` | INTEGER NULL REFERENCES `closing_lines(id)` | reuse | CLV |
| `clv_tenths` | REAL NULL tenths | `clv.clv_tenths()` | the secondary statistic |
| `clv_horizon_hours` | REAL NULL | harness | written *with* the score, never inferred. Without it the column silently blends two regimes |
| `clv_scored_ms` | INTEGER NULL | harness | idempotent rescoring |

### 9.4 Entry cost, and the minimum viable set

**Joe types two things: one tap and one number.** Estimated at ~12 seconds. That
is already at the minimum — the previous draft's eleven fields collapsed because
every classification field is derivable from the ticker and the clock, and every
transaction field is authoritative from the venue.

**The only cuttable field is `had_already_opened_kalshi`.** What is lost: the one
recorded signal about §7.8's irreducible hole, leaving T1–T3 as the sole
anchoring evidence.

**Neither remaining field may be cut.** Dropping `ticker` makes the estimate
unjoinable; dropping `stated_probability_bp` *is* the measurement. **If the flow
cannot hold one tap and one number, the measurement should not be run**, because
a half-logged record is worse than none.

### 9.5 Registered sensitivity analyses

Fixed now, reported always, non-confirmatory: (a) `B_hat` including
`match_status = 'unmatched_no_position'` rows scored on the market's settlement —
these are estimates unselected by whether he pulled the trigger, so this is the
*less* selected sample; (b) `B_hat` excluding rows whose `position_time_source` is
`settled_time`; (c) `B_hat` on non-sports rows, separately, never pooled. **None
may change the §4 verdict.**

### 9.6 Storage — reuse, extend, and what must not be duplicated

| existing thing | verdict |
|---|---|
| **`fills` table** (`schema.sql:632`) | **REUSE, with a migration.** Do not build a second fills table — two places to answer "did Joe trade" is worse than one migration. Needed: add `source TEXT NOT NULL DEFAULT 'engine'` ('engine' \| 'venue_hand') so the fee-calibration population is not silently pooled; relax the `ticker` FK to `kalshi_markets`, since a hand-bet market may never have been discovered by the poller. `order_id` is already nullable. `fee_predicted` / `fee_model_used` stay `NOT NULL` and **we populate them** — we know price and count, so our model can predict, and a real `fee_actual` beside it is exactly the ground truth `core/fees.py` and H4 are waiting for. |
| **`settlements` table** (`schema.sql:657`) | **DO NOT REUSE. Add `venue_settlements`.** `order_id INTEGER NOT NULL` with `UNIQUE(order_id)` is structural to that table's identity, and its `pnl_cents` is *our* computed P&L under a named `fill_assumption` — a meaningless concept when the venue is telling us the truth directly. `venue_settlements` is a thin mirror of the wire payload, one row per settled position, keyed `(ticker, settled_ms)`. |
| **`bet_estimates` — NEW, small** | **The estimate cannot live as a column on `fills`.** It must be written and timestamped *before any fill exists*, and it must survive the case where no fill ever exists (`unmatched_no_position`). A column on a row that does not yet exist cannot be written, which is fatal to the entire two-clock design. `bet_estimates` holds §9.2 and §9.3 and carries `matched_position_id` as a nullable pointer. |
| **`bet_estimate_looks` — NEW** | one row per analysis run: `run_ms`, `n_in_population`, `embargo_active`, `git_sha`, `reason`. **More than one non-embargoed row before the stop voids the single-look claim** (§0.2, §5). This is what makes "one look" checkable rather than aspirational. |
| `closing_lines` table | **REUSE unchanged.** Keyed `(ticker, horizon_hours)`, no FK to `recommendations`. |
| `clv.clv_tenths()`, `clv.parse_candlestick()`, `scoring.fetch_closing_line` | **REUSE unchanged.** |
| `kalshi/rest.py` `fills()` `settlements()` `positions()` `balance()` | **REUSE unchanged — and note all four currently have zero production callers** (verified 2026-08-17: the only apparent callers are comments in `scripts/capture_fills_fixture.py` explaining that it deliberately does *not* call them). This is the repo's "built but never called" pattern. **The poller of §7.6 is the first production caller of any of them.** |
| `recommendations` table | **DO NOT REUSE — this is the important one.** It is engine output, it is the registered population of the ADR 0021/0034 CLV signal test, and `signal_test` fits it. Writing hand-placed bets into it silently contaminates a different registered measurement with rows that were never engine recommendations. |
| `gate.always_valid_multiplier` | **DO NOT USE.** §0.2. Single look. |
| `analysis/signal_test.fit` | **DO NOT REUSE.** It fits a three-variable regression on `edge` and `half_spread`. Different estimand. Copy the CRVE pattern; do not call the function. |

### 9.7 Do not make three other open questions harder

Flagged, not scoped. **One wiring job unblocks three things**, so the poller
should not be built in a shape that forecloses them:

- Build it as a general `portfolio_poll` module over `KalshiRestClient`, **not**
  a fills-only script.
- **Poll `balance()` as well as fills/settlements/positions.** CLAUDE.md names
  the account balance as what is needed to settle **H4**, the untested
  settlement-fee question behind ADR 0027's "the headroom is an upper bound".
  §5 arm 3 needs it anyway, so it is free.
- **Do not couple anything here to `orderbook()`.** It has one caller, in a
  one-off reconciliation script, and it is the unmeasured bid–ask spread the town
  hall called the open number in this project. Leave it reachable.
- Real `fee_actual` on real fills (§9.6) is the fee ground truth `core/fees.py`
  has been waiting for. Storing it costs nothing here.

Nothing in this registration depends on any of the three, and no result here may
be cited about any of them.

---

## §10. What this cannot establish

Drafted before the run, because caveats written afterwards are selected to be
survivable.

1. **It cannot establish whether Joe has an edge.** 200 bets is ~100x short; he
   would have to be a true 60% picker for 200 bets to separate him from a coin.
   No result here licenses any sentence about profitability.
2. **It cannot establish that he is well calibrated.** The strongest available
   negative is "his bias is smaller than 10 points" (§4) — *the bottom of the
   typical beginner band*, not calibration. A `NOT OVERCONFIDENT` verdict is
   fully consistent with a 9-point bias.
3. **It cannot verify the pre-price claim** (§7.1(b), §7.8). Two independent
   clocks prove he did not *transact* before estimating. They prove nothing about
   whether he had *seen* a price, and that is the half that does not require
   dishonesty.
4. **It cannot detect overconfidence in the extremity sense.** `B = E[p - y]`
   measures mean bias. A forecaster who is too extreme in *both* directions — too
   high on favourites, too low on longshots — has `B ≈ 0` and is badly
   miscalibrated, and this design would call that `NOT OVERCONFIDENT`. **This is
   the caveat most likely to overturn the result and it is named for that
   reason.**
5. **It cannot generalise past the bets he chose to place.** He only bets where he
   thinks the price is wrong, so this is calibration on a self-selected slice.
   §9.5(a) partially addresses this and does not fix it.
6. **It cannot survive a `coverage < 0.90` reconciliation.** If he logged 70% of
   his bets, every number here describes the 70% he chose.
7. **The CLV arm establishes nothing at all** (§0.5). Its MDE exceeds the entire
   cost headroom it would have to beat. It is description, and any citation of it
   as evidence of edge is a misreading of this document.
8. **It says nothing about the tool's consensus signal**, which ADR 0038 closed.
   Different subject, different population, different statistic.
9. **The venue data is authoritative but not complete.** `/portfolio/fills` has a
   measured ~3-month retention ceiling and its per-fill wire shape has never been
   observed on this account. Every claim resting on `fills` — the strong form of
   the two-clock check, `is_taker`, `n_fills_in_position` — is contingent on an
   endpoint that has so far returned nothing but an empty list.
10. **`n = 200` is an upper bound, not a plan.** The date arm needs 1.5 bets/day
    (§0.4) and the realistic outcome is `UNRESOLVED` at a smaller `n`. That is a
    legitimate result and it goes in the same file (§8).

---

## Recommended companion ADR

**Yes — this needs ADR 0039, and the reason is not statistical.** ADR 0038 closed
the hunt and required that any proposal to reopen name which row it overturns. A
future session encountering a new `bet_estimates` table, a migration on `fills`,
a portfolio poller and a new measurement harness will reasonably ask whether 0038
was violated. A short ADR stating that this measures **the human, not the
signal**, that `ORDERS_ARE_DRY_RUNS` is untouched, that no result here can
surface a bet, and that the `recommendations` population is deliberately not
reused (§9.6), costs twenty minutes now and prevents a re-litigation later.

It also carries two decisions that outlive this study: the `fills.source` column,
and the fact that the portfolio poller is the **first production caller** of four
endpoints that have existed unused. Both are architectural on their own terms.
