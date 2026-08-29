# Pre-registration — the operator self-assessment screen

Written **2026-08-29**, before any query has been run against Joe's results.

Joe asked for *"a system where I can see how good or bad I do and understand the
whys and how to get better."* This is the highest-flattery-risk measurement this
project has attempted: the subject is the operator, the operator asked for the
answer, and he will look at the screen every day. Every rule below is fixed
here so that no metric can be chosen after seeing which one flatters him.

**ADR 0065 §3 required this file by name** — *"Nothing here scores estimates
against outcomes or resumes calibration — that would be a new registration,
pre-registrar first."*

---

## 0. Declared blindness — what the author of this file has and has not seen

Disclosed first, because it is the only thing that makes the rest credible.

**Seen while writing this:** `backend/store/schema.sql` (the DDL for
`manual_orders`, `venue_settlements`, `closing_lines`, `fair_prices`,
`desk_passes`, `desk_attention`), `backend/store/manual_orders.py`,
`backend/api/routes.py:4580+` (the twelve server-side checks),
`backend/scoring.py:97-190`, `backend/analysis/clv.py:1-110`,
`backend/bets.py:1-60`, `backend/gate.py:133-190`, ADR 0063/0065/0071/0073/0075.

**Not seen, not queried, not requested, and not derivable from anything above:**
his P&L, his profit, his win rate, any CLV value, any settled outcome, any
per-bet result, any typed estimate, and the row count of `manual_orders`.

**The row count was deliberately not obtained.** `scripts/inspect_live_db.py`
carries a fixed whitelist of named queries and has none for `manual_orders`, so
reading `n` would have required shipping a new query first. It was not shipped,
because **nothing in this registration depends on the current `n`** — every
floor below is expressed as a function of `G` and every panel states its own
gate. A registration that had to be re-tuned once `n` was known would be exactly
the failure this document exists to prevent.

**One correction to the brief that commissioned this file.** It says the path
bets *"one contract at a time, ~$0.01–$0.99 per bet"*. That was true through
2026-08-25 and is not true now: ADR 0075 replaced the one-contract ceiling with
`MANUAL_ORDER_MAX_SPEND_TENTHS = 3_000` (a **$3.00 spend cap**) plus structural
count ceilings of 500 contracts (250 on `KXMVE`). Stake now varies bet to bet,
which strengthens §2.2's argument that win rate has no fixed null and weakens
nothing else.

---

## 1. Plain-language glossary — every term defined at first use

Written for someone who is not a professional bettor, per the standing
instruction. An example follows each definition.

- **Break-even win rate.** The fraction of bets you must win just to end level
  after fees. At a sportsbook it is 52.38%. On Kalshi as a taker this repo's
  code applies **51.75%** (ADR 0028). *Example: if you always bet at a price of
  50c, you need to be right slightly more than half the time or the fee eats
  you.*
- **Price paid, in tenths of a cent.** All money here is integer tenths of a
  cent (`core/prices.py`). *Example: a 62.5c contract is `625` tenths.*
- **The ask.** The price you actually pay to buy right now. **The mid** is the
  halfway point between the best buy and best sell price and is *not* a price
  anyone can transact at. *Example: bid 60c, ask 64c, mid 62c — you pay 64c.*
- **Devigged consensus fair value.** Sportsbook odds with the bookmaker's
  built-in margin ("the vig") mathematically removed, averaged across books, to
  get an estimate of the true probability. *Example: two books both offering
  −110 implies 52.4% each, summing to 104.8%; devigging scales it back to 50/50.*
- **Calibration.** Whether the numbers you type mean what they say. *Example:
  of all the times you said "70%", you should win about 70 of every 100. If you
  win 55, you are 15 points overconfident.*
- **Brier score.** The average of (your probability − the outcome)², where the
  outcome is 1 or 0. Lower is better. *Example: you said 80% and it happened →
  (0.8−1)² = 0.04. You said 80% and it did not → (0.8−0)² = 0.64.*
- **Reliability and resolution (the Murphy decomposition).** Brier splits into
  *reliability* (are your numbers honest?) and *resolution* (do your numbers
  separate winners from losers at all?). They move independently, which is why
  the single Brier number is not interpretable on its own.
- **CLV — closing line value.** The gap between the price you paid and the price
  the market settled on just before the game started. *Example: you bought at
  60c and the market closed at 64c — you got 4c of CLV, whether or not the bet
  won.*
- **Cluster.** A group of observations that are not independent because they
  come from the same underlying event. *Example: a moneyline bet and a total
  bet on the same game both resolve from one final score, so they are one
  observation, not two.*
- **Power.** The chance a measurement would notice an effect of a given size,
  if that effect were really there. *Example: a design with 20% power misses a
  real effect four times out of five.*
- **Always-valid boundary.** A threshold that stays honest no matter how many
  times you look at a growing record. An ordinary threshold checked daily
  eventually fires on nothing; this one does not (`gate.py:133`).

---

## 2. THE POWER REALITY — computed before anything else

This section exists because the most valuable output of a pre-registration is
sometimes the verdict *"this cannot be answered"*, and that verdict is free.

### 2.1 Win rate and P&L, as a test of skill

A one-sample proportion test, one-sided, α = 0.05, power 0.80, against the
applied break-even bar `p0 = 0.5175`, for a true rate `p1 = 0.5375` (a
**two-percentage-point edge**):

```
n = ( 1.645*sqrt(.5175*.4825) + 0.8416*sqrt(.5375*.4625) )^2 / (0.0200)^2
  = ( 0.82199 + 0.41961 )^2 / 0.0004
  = 1.54157 / 0.0004
  = 3,854 bets
```

Two-sided, the honest default: **4,893 bets.**

And he will look at the screen daily, which is optional stopping. Under the
always-valid boundary (`always_valid_multiplier`, tuning 300, α 0.05) the same
two-point effect needs:

```
n = 10,000   detectable effect (mult 3.133 + 0.842) * 0.5 / sqrt(n) = 0.0199
n = 12,000   detectable effect                                       = 0.0182
```

**~3,900 bets for one pre-registered look; ~10,000 if he looks daily.**

Against the observed cadence: the route enforces a **10-minute cool-off**
(`COOLOFF_MS`), giving a physical ceiling of 144 bets/day, and the one measured
attention day (2026-08-28, budget day 20260827) was **4.88 hours**, giving a
never-approached ceiling of ~29/day. At a generous and unobserved 10 bets/day,
3,900 bets is **390 days** and 10,000 is **2.7 years**. At a plausible 1–3
bets/day it is **3.5 to 27 years**.

**Verdict: the brief's estimate is correct. Order-of-thousands, confirmed.**
Profit and win rate can never answer *"am I good"* at this volume.

### 2.2 The stronger objection: win rate has no fixed null at all

Power is not even the binding constraint on win rate. **He bets at different
prices, so there is no single number to beat.** At a 30c price the break-even
win rate is ~30.9%; at 70c it is ~70.9%. A pooled win rate therefore has no
null hypothesis. A 35% win rate can be an excellent record and an 80% win rate
can be a losing one.

To give win rate a null you must bucket by the price actually paid — which
multiplies cells and divides `n`, and at his cadence leaves every cell below
this repo's ≥5-expected-outcomes floor. **Win rate is therefore verdict-
incapable at *any* `n`, not merely underpowered.** It is registered as
permanently display-only, and that is not a status that changes when the record
grows.

**Net P&L is different and the difference matters.** `net = payout − cost − fee`
(`backend/bets.py`) *does* have a proper null of zero, because each bet's cost
already encodes its own break-even. So net P&L is a legitimate estimator with
no power (§2.1), whereas win rate is not a legitimate estimator at all.

### 2.3 REGISTERED: P&L and win rate are DISPLAY-ONLY, never verdict-bearing

They are shown because they are his money, and hiding a man's own money from him
is not rigour. They carry **no threshold, no colour encoding good/bad, no
comparison to any benchmark, and no verdict, at any `n`, permanently.**

**The exact words the screen must show. These are the registered strings and
the write-up will be checked against them verbatim.**

Beside net P&L:

> **This is money, not evidence.** At your rate of betting, a real 2-point edge
> would take about 3,900 bets to separate from luck — about 10,000 if you check
> this screen every day. That is years. This number will be mostly luck for a
> long time. It is here because it is yours, not because it says whether you
> are good.

Beside win rate:

> **Win rate cannot be scored, and no threshold is shown because none exists.**
> You bet at different prices, so there is no single number to beat: at a 30c
> price you need to win about 31% of the time; at 70c, about 71%. A high win
> rate here can be a losing record and a low one can be a winning record.

Beside the Brier score, if it is shown at all:

> **A Brier score is not a grade.** It falls just from betting on lopsided
> markets, where the answer was easy. Only the two halves below it —
> *reliability* and *resolution* — mean anything, and only reliability is being
> tested here.

### 2.4 Colour rule, because this repo has a colour semantic

ADR 0081 gave up the brand red so that red can mean *lose*. On this screen:
**red and green may encode only the sign of a realised money figure, which is a
fact. They may never encode the sign of a statistic, which is a claim.** A
negative CLV mean, a hot calibration bias, and a poor Brier score all render in
neutral type.

---

## 3. The population, and the exclusions

**Population.** Rows in `manual_orders` where:

```
dry_run = 0
AND status != 'rejected'
AND submitted_ms >= 2026-08-26T00:00:00Z   (the arming date, ADR 0073)
```

**Exclusions. Every one of them is independent of the outcome, by
construction — none references a result, a settlement, or a P&L.**

| # | Rule | Why it is outcome-independent |
|---|---|---|
| X1 | `dry_run = 1` excluded | A rehearsal spent no money; the typed estimate may not have been meant. Decided by a flag set before the order left. |
| X2 | `status = 'rejected'` excluded | Nothing left the process. There is no bet to score. |
| X3 | Rows with no matching `venue_settlements` row are excluded **from outcome panels only** | They are *unresolved*, not unfavourable. The count is printed as the denominator on every outcome panel. They are never excluded from descriptive panels. |
| X4 | `KXMVE` combination tickers are **NOT excluded**; they are a separate reported stratum | The fee model is hedged upward on combos (ADR 0046) and the book is enter-only (ADR 0012 §5), so pooling them with single markets mixes two different cost regimes. Membership is decided by the ticker string. |
| X5 | A bet whose outcome join is ambiguous is excluded from outcome panels, with a printed count | Ambiguity is a property of the join, not of the result. See §5.3. |

**X4 carries a pre-declared count-only branch, modelled on the combo
experiment's precedent** (a registered exclusion the agent correctly refused to
activate when the sample turned out thin): **if the combo stratum holds fewer
than 10 rows it is reported as a raw count with no statistic of any kind.** The
trigger is a row count, which is outcome-independent, and it is written here so
that activating or refusing it is a rule rather than a judgement.

**What the population is NOT.** `venue_settlements` mirrors the *whole Kalshi
account*, including positions Joe opened in the Kalshi app with no
`manual_orders` row and no typed estimate. Those rows appear on the existing
`/bets` P&L display and **must never enter any panel that uses `p_yes_bp`**,
because they have none. Every panel states which population it drew from.

---

## 4. The unit of observation, and the clustering variable

**The unit is the GAME (the Kalshi event), not the bet.** Two bets on different
events are independent because they resolve from different real-world results.
Two bets on the same event are one observation: a moneyline and a total on one
game resolve from one final score. This repo has already shipped a gate that
counted 400 rows on one ticker as 400 observations; the fix was clustering, and
the fix is inherited here rather than re-derived.

**`cluster_key`, resolved in this fixed order and no other:**

1. `kalshi_markets.event_ticker`, where the market was discovered.
2. Otherwise the ticker string up to and excluding its final `-`.
3. Otherwise the ticker itself, with `unclustered = 1`.

`G` = the number of distinct `cluster_key` values. **Every standard error is
clustered. Every floor in this document counts `G`, never rows.** The count of
rows and the count of clusters are both printed, always, side by side.

**The estimator is the unweighted mean of per-cluster means, not the mean of
rows.** This is a deliberate choice made here rather than later, and it exists
because of the 2026-08-25 audit finding that `G = 311` was **4.26 effective
clusters**, with one WNBA game carrying 43.8% of the leverage. A mean of cluster
means gives every game weight exactly `1/G`, so that failure mode cannot recur.
The standard error is `sd(cluster means) / sqrt(G)`.

Printed beside every clustered figure, unconditionally: `G`, the row count, the
distribution of bets-per-cluster, and the largest cluster's row count.

**A combination bet spans several events and this clustering does not capture
that.** A `KXMVE` bet is assigned to the cluster of its first leg where leg
tickers are recoverable, else it is its own cluster with `unclustered = 1`. A
combo whose legs overlap a single-market bet's event is a dependency the
clustering **misses**. This is stated as a known defect, not fixed, and it is
the second reason combos are a separate stratum.

---

## 5. Orientation, the cut, and the joins — all fixed here

### 5.1 Everything is oriented to YES

`p_yes_bp` is P(YES) always (`schema.sql`, ADR 0065), including on a `side='no'`
bet. So:

- `p_typed_yes` = `p_yes_bp / 10000`, for every row, regardless of side.
- `y_yes` = 1 if `venue_settlements.market_result = 'yes'`, 0 if `'no'`,
  **UNRESOLVED otherwise** (a void has no outcome to invent; `bets.py`'s rule).
- The calibration statistic is `(y_yes − p_typed_yes)` for every row. A NO bet
  with a low typed probability is a consistent observation on this scale and
  needs no sign flip.

### 5.2 The cut — bucket edges, fixed in advance, never re-cut

**Typed-probability buckets** (5 cells, basis points):

```
[   1, 2000)   [2000, 4000)   [4000, 6000)   [6000, 8000)   [8000, 9999]
```

**Price-paid buckets** (5 cells, tenths of a cent), on `limit_price_tenths` —
**the price actually paid for the side he bought**, per the CLAUDE.md rule. It
is snapped at fill and it is not a mid. It is explicitly **not**
`max_price_tenths`, which is the ceiling he typed and not a price anyone paid:

```
[   1,  200)   [ 200,  400)   [ 400,  600)   [ 600,  800)   [ 800,  999]
```

Same edges as the typed cut, so the two are directly comparable. **No other cut
may be added without a dated amendment to this file, and an amendment is
additive — never an edit.**

**A bucket may display a point estimate only when it meets the repo's
≥5-expected-outcomes-per-side floor at its own midpoint.** Derived now, so it
is arithmetic rather than a later judgement:

| bucket midpoint | rows required |
|---|---|
| 0.10 | 50 |
| 0.30 | 17 |
| 0.50 | 10 |
| 0.70 | 17 |
| 0.90 | 51 |

A bucket below its floor renders `not enough yet — 3 of 17`, never a point, and
never a blank.

### 5.3 The outcome join, and its ambiguity rule

`manual_orders` has no foreign key to `venue_settlements`. The join is:

> the `venue_settlements` row with the same `ticker` whose
> `position_first_seen_ms` is the nearest value at or after `submitted_ms`.

Check 10 of the route refuses any order on a ticker where a position already
exists, which makes `ticker` a near-key within an open position. Where the join
is nevertheless ambiguous (two candidate settlements, or a NULL
`position_first_seen_ms` with two orders on one ticker), the row is
**UNRESOLVABLE** and excluded from outcome panels under X5, with the count
printed.

### 5.4 The CLV join, and the coverage fraction that must be printed

CLV for a hand bet requires a `closing_lines` row, which `scoring.py:97` writes
for a hand-bet ticker only when **all** of the following hold: the market was
discovered into `kalshi_markets` with a `series_ticker`; the matcher wrote an
`event_links` row for its event; and **a `venue_settlements` row already
exists**. The function's own docstring says *"most hand-bet tickers refuse right
there, which is expected and honest, not a bug to chase."*

Two consequences, both registered:

1. **The CLV-covered subset is selected on "the tool also knew about this
   market"**, which correlates with mainstream team markets and against props
   and combos. The panel must print the coverage fraction — *covered bets /
   bets placed* — beside every CLV number, always, and no CLV figure may be
   quoted without it.
2. **On this path CLV is not faster than settlement.** The closing line is
   fetched only after the settlement row exists, so CLV *arrives* later than
   P&L, not earlier. Its entire advantage here is variance (§6.3), never speed.
   `clv.py`'s docstring describes the speed advantage for `recommendations`,
   where the line is fetched near commence; that sentence does not transfer to
   hand bets and must not be quoted as if it did.

CLV is oriented to the side bought: `clv_tenths = closing_mid_for_his_side −
limit_price_tenths`, where `closing_mid_for_his_side` is the closing mid for YES
on a YES bet and `1000 − closing_mid_yes` on a NO bet. The mid is correct here
and only here: using the ask would systematically flatter a buyer.

Primary horizon `0.0h`; control horizon `1.0h`. **If the result moves between
them it was convergence, not skill**, and the write-up leads with the
disagreement.

---

## 6. The candidate metrics — accepted, modified, or rejected

Each is stated as a claim that can come back negative, with a direction.

### 6a. CALIBRATION of the typed estimate — ACCEPTED, and it is the only verdict

**The claim, as something that could be false:** *the game-clustered mean of
`(y_yes − p_typed_yes)` differs from zero.* **Two-sided.** It is two-sided
because he could be systematically hot or systematically cold, and choosing a
direction after seeing the sign would silently double the false-positive rate.

**Estimator:** the unweighted mean of per-cluster means (§4). Null: zero.

**Why this is the one metric worth an inference.** It is a question about *him*,
not about the market, so it does not reopen ADR 0038's closed hunt. And the
effects it hunts are large: a novice's miscalibration is measured in tens of
points, not in the 0.63 points of cost headroom, so a much cruder instrument can
find it.

**Detectable bias, always-valid boundary at tuning `m = 150`, α = 0.05, 80%
power, conservative `sd = 0.5`:**

```
G =   30    multiplier 6.086    detectable bias  63.2 points
G =   50    multiplier 5.012    detectable bias  41.4 points
G =  100    multiplier 4.032    detectable bias  24.4 points
G =  150    multiplier 3.656    detectable bias  18.4 points
G =  200    multiplier 3.459    detectable bias  15.2 points
G =  300    multiplier 3.261    detectable bias  11.8 points
G =  500    multiplier 3.114    detectable bias   8.8 points
G = 1000    multiplier 3.039    detectable bias   6.1 points
```

**Registered verdict floor: `G >= 300`**, at which the design catches an
11.8-point bias at 80% power. **Minimum `n` to display anything at all
(non-verdict): `G >= 30`, inherited from ADR 0065 §3** — and it is recorded here
that 30 is a *display* floor and would be a catastrophic *verdict* floor, since
at `G = 30` the design can only resolve a **63-point** bias, which does not
describe a bettor, it describes someone betting the wrong side.

**What it does not establish:** that his estimates are calibrated on bets he did
**not** place. See §12.3.

### 6b. Typed estimate vs devigged consensus fair value — ACCEPTED AS DESCRIPTIVE, REJECTED AS A VERDICT

**Modified from the brief's framing.** `beta = −0.141`: the consensus is
*negatively* related to Kalshi's close, so agreement with consensus is not
evidence of correctness and disagreement is not evidence of error.

**Registered, in these words:** *no rule anywhere in this measurement may score
Joe as right when he agrees with the devigged consensus, or wrong when he
disagrees. No panel may label agreement "good", colour it, or rank by it.*

Ranking by it is separately forbidden by ADR 0071: *a per-row fact is
transparency; an ordering is a claim*, and `beta = −0.141` means ranking by the
consensus gap puts the least trustworthy rows at the top. A verdict-bearing
version of this panel would also **function as an edge-finder**, which ADR 0038
closes; that is the reason for the rejection, and it is why the cut was made
rather than the panel softened.

**What it can honestly claim, and this is the whole of it:** *"On this bet you
typed 62% and the devigged sportsbook consensus at that moment read 55%."* A
distribution of that gap over his bets describes **how much disagreement he
requires before he bets** — a fact about his threshold, not about who is right.

Coverage caveat: a `fair_prices` row exists only where the event was linked, so
this panel has its own coverage fraction and must print it.

### 6c. CLV — ACCEPTED AS DESCRIPTIVE, NOT VERDICT-BEARING AT THIS `n`

**The variance argument, stated as arithmetic.** Settlement pays 0 or 1000
tenths per contract, so per-bet P&L has a standard deviation of up to **500
tenths**. This repo's measured `sd(clv_tenths)` is **30.15 tenths** (2026-08-25
audit). That is a **16.6× smaller** standard deviation in the same units, and
because required `n` scales with the square of the sd, it is **≈275× fewer
observations** for the same resolution. This is exactly why the project
registered `beta` on CLV rather than on profit.

**How much faster: in resolution, not in time.** CLV needs ~275× fewer bets than
P&L for the same precision. It does **not** arrive sooner in wall-clock terms on
this path (§5.4) — the closing line is fetched after settlement.

**Detectable mean CLV, same boundary, `sd = 30.15`, 80% power:**

```
G =  150   11.07 tenths (1.11c)
G =  300    7.14 tenths (0.71c)
G =  500    5.33 tenths (0.53c)
G = 1000    3.70 tenths (0.37c)
```

The headroom being hunted is **0.63 points** (ADR 0027/0028, an upper bound
pending H4). So CLV resolves at the headroom scale at roughly `G = 400`
**covered** clusters, and raw bets needed is `400 / coverage`.

**Rejected as a verdict here for two reasons, either sufficient.** First, a
CLV verdict on his bets would be a statement about market edge, which ADR 0038
closes and this task must not reopen. Second, the 30.15 figure is itself under
audit: the 2026-08-25 look found `sd(edge) = 40.98` with `too_few_books` /
`no_market_width` rows and 10.90 without, and rule 1 says those rows are bugs.
An sd imported from a contaminated population may not carry a verdict on a new
one.

**Registered amendment trigger:** if the observed `sd(clv_tenths)` on the
hand-bet population exceeds **35 tenths**, the figures above are wrong and this
file must be amended before any CLV number is quoted. This trigger is written
now because the last one of its kind (*"if it comes in above 30 tenths this
document must be amended"*) fired and the amendment was never written.

### 6d. BEHAVIOURAL descriptive facts — ACCEPTED, display at `n = 1`, never verdicts

These require **no inference about the world**. They describe what he did. Each
renders as a raw sequence or a raw count, with no test, no threshold, no
p-value, and no comparison.

| panel | source | note |
|---|---|---|
| Fill rate on IOC orders | `manual_orders.status` | Pure venue fact. |
| Time of day of each bet | `submitted_ms` | Displayed as a strip of stamps, not a rate. |
| Bets per session | `submitted_ms` | **Session defined now: bets separated by < 90 minutes are one session.** Fixed here so it is not chosen later. |
| Stake and cadence after a loss | ordered `submitted_ms` + joined outcome | See the trap below. |
| Fee as a fraction of stake | `fee_cost_tenths / (contracts * entry_price_tenths)` | The most actionable number on the screen; see §11. |
| Distance from the caps | exposure and daily-loss reads | Descriptive only. |
| Typed ceiling vs price paid | `max_price_tenths` vs `limit_price_tenths` | How much room he leaves himself. |
| Does he bet more when the screen is empty | `desk_attention` + slate freshness | Counts only; see the retention caveat below. |

**The trap in "stake after a loss", registered rather than discovered later.**
Comparing *mean stake after a loss* to *mean stake after a win* is a two-sample
test and invites exactly the verdict this panel is not allowed to give. So:
**the panel shows the raw ordered sequence of stakes with wins and losses
marked, and computes no difference of means.** If a difference of means is ever
wanted it is a new registration.

**`desk_attention` decays.** The empty-screen panel reads an append-only
heartbeat table that the retention pass prunes, so it can describe only the
retention window. The panel states the window and refuses to describe anything
older.

### 6e. RESOLUTION / discrimination — ADDED (the brief omitted it), DISPLAY-ONLY

The brief lists Brier but not its second half. **Registered because Brier is
uninterpretable without it:** a Brier score improves just from betting lopsided
markets, so a falling Brier can mean "I got better" or "I picked easier games".

The Murphy decomposition `Brier = reliability − resolution + uncertainty` is
displayed with all three terms, always together, never the single number alone.
**Only the reliability term is verdict-eligible, via §6a.** Resolution is a
two-sample separation and needs materially more data than the bias test; it is
display-only with no registered floor, because registering a floor would imply
a verdict is coming and none is.

### 6f. Execution quality — REJECTED as a metric about Joe

Every hand bet is immediate-or-cancel at the ask; there is no maker path on this
route. So the price he paid is a property of the path, not of his decision.
Scoring him on it would score the code. **Cut.**

### 6g. "How often the brakes fired" — REJECTED as unmeasurable

Checks 0 through 10 of `POST /api/manual-orders` all raise **before** step 11
reserves the row, so **a refused attempt writes nothing.** The number of times
the lockout, the cool-off, the daily-loss switch or a cap stopped him is not in
the database. **No panel may claim it, estimate it, or imply it.** If Joe wants
it, that is an instrument change first and a registration second.

---

## 7. Multiplicity — counted now, before anything is looked at

**Cells on the proposed screen:** 5 calibration buckets + 5 price-paid buckets +
4 time-of-day blocks + ~10 headline figures ≈ **24 cells**.

At a two-standard-error threshold, pure noise produces `24 × 0.0455 ≈ 1.1`
"significant" results **per viewing**, on a screen with nothing true in it. He
will view it daily. This project has already produced a 20-point "finding" from
data generated with no edge in it whatsoever, and has been burned by 1,190
category cells.

**REGISTERED, and this is the multiplicity rule:**

> **No panel on this screen carries a verdict, with exactly one exception: the
> calibration bias statistic of §6a.** Therefore the verdict family size is
> `K = 1` and no Bonferroni correction is required. **Adding a second
> verdict-bearing statistic requires a dated amendment to this file that
> re-derives the boundary at `alpha/K`** — which enters `always_valid_multiplier`
> as `2*ln(K/alpha)` — before the second statistic is computed even once.

Descriptive panels are not corrected because they make no claims. That is the
whole reason they are safe to show at `n = 1`, and it is also why they must
never acquire a threshold, an arrow, a benchmark or a colour.

---

## 8. The stopping rule and the ordering rule

### 8.1 There is no stopping rule, and that is the finding

This is a **monitor**, not a study. Data accrues as long as he bets and he looks
at it daily. A threshold re-evaluated on every page load against an accumulating
database is not one look, it is thousands, and under a true zero it crosses
eventually with probability 1 — measured in this repo at **13.7%** over only 100
looks, and that is a floor.

**REGISTERED:**

1. **No fixed-sample p-value is computed anywhere in this measurement, ever.**
   Not on a descriptive panel, not on the verdict panel, not in the write-up.
2. The one verdict uses the Robbins normal-mixture always-valid boundary, which
   is valid simultaneously at every `n`, so looking whenever he likes costs
   nothing. The price is that the boundary is 3.26 standard errors at `G = 300`
   rather than 2 — about 1.6× the effect size — and that price is paid, not
   negotiated.
3. Below the floor the verdict panel renders `NO VERDICT — G of 300
   game-clusters` and no number that could be read as one.
4. The monitor never "ends". It has no final look and no final answer.

### 8.2 Amendment trigger on the calibration sd

The floors in §6a assume `sd(y_yes − p_typed_yes) <= 0.50`. **If the observed sd
exceeds 0.50, this file must be amended to raise the floor before any bias
figure is quoted.** Written as a trigger because the identical trigger on
`sd(clv_tenths)` fired on 2026-08-25 and its amendment is still unwritten.

### 8.3 The ordering rule

ADR 0071: *a per-row fact is transparency; an ordering is a claim.*

**REGISTERED: the bet list on this screen is ordered by time, descending, and by
nothing else — ever.** No ordering by CLV, by P&L, by calibration error, by the
consensus gap, or by any statistic. **No "your best bets" and no "your worst
bets" list**: a top-5 is an ordering *and* the maximally selected sample, and it
is the single most likely place a flattering story would get told.

---

## 9. The decision rule, verbatim

> The single verdict-bearing statistic is
> `bias = the unweighted mean over game-clusters of (y_yes − p_typed_yes)`,
> two-sided, null zero, where `y_yes` is 1 if the market settled YES and 0 if it
> settled NO, and `p_typed_yes` is `manual_orders.p_yes_bp / 10000`.
>
> It is reported with **no verdict**, as `NO VERDICT — G of 300 game-clusters`,
> until `G >= 300`.
>
> At and after `G >= 300` it is compared to the Robbins normal-mixture
> always-valid boundary `backend.gate.always_valid_multiplier(G, tuning=150,
> alpha=0.05)` applied to the cluster-robust standard error
> `sd(cluster means) / sqrt(G)`.
>
> The verdict is **`BIAS DETECTED`** if and only if BOTH of the following hold:
> (i) the interval `bias ± multiplier × se_cluster` excludes zero, AND (ii) the
> leave-one-cluster-out refit excludes zero for **every** cluster omitted in
> turn. Otherwise the verdict is **`NO BIAS DETECTED AT THIS RESOLUTION`**.
>
> No other panel on this screen carries a verdict, at any `n`, ever. No p-value
> is computed anywhere in this measurement.

**Condition (ii) must be implemented, not left as an opt-in parameter.** The
identical leave-one-group-out downgrade was registered for `beta` in §A4 and is
**not implemented** (`signal_test.py:237-245` verdicts on the pooled fit alone),
and the identical *modal-version-only* rule existed as a parameter defaulting to
off that no production caller set. A rule that lives only in a registration is
not a rule. A test must fail if condition (ii) is skipped.

---

## 10. What would falsify this, and what happens then — both branches, with destinations

**The negative branch has a destination, written now:**
`docs/measurements/2026-08-29-operator-self-assessment-result.md`, written when
`G = 300` is first reached, **whichever way it comes out**, and linked from
`tasks/NEXT.md` in the same commit.

| outcome at `G >= 300` | what is written | what is built | what is killed |
|---|---|---|---|
| `BIAS DETECTED`, hot (overconfident) | The measured offset, its interval, the per-cluster view, the largest cluster's share | The offset is shown **as a fact** beside the typed number at the ticket, after he types it | Nothing. No auto-correction, no sizing change, no suppression. |
| `BIAS DETECTED`, cold | Same | Same | Same |
| `NO BIAS DETECTED AT THIS RESOLUTION` | *"No bias detectable at the 11.8-point scale over G clusters; biases smaller than that remain untestable at this cadence and may never be testable."* | Nothing | Nothing. The calibration panel keeps displaying, without a verdict, indefinitely. |

**The honest admission the brief asked for.** For every panel except §6a, **we
proceed either way.** The descriptive panels are not decision-relevant in the
inferential sense — they are the product, not the test. That is a finding about
the plan and it is recorded here rather than discovered later: *this screen is a
mirror, and only one pixel of it is a measurement.*

**What changes if the verdict clears, in both directions: nothing about the
gate, the engine, or sizing.** `gate.py` never reads `manual_orders` (ADR 0063),
and a calibration result on hand bets may not move the live-trading interlock,
may not arm `ORDERS_ARE_DRY_RUNS`, and may not change any cap. That boundary is
structural and this measurement does not touch it.

---

## 11. Can this screen honestly tell Joe how to get better?

**Partly, and the useful part is the part with no statistics in it.**

**Actionable from bet one, no inference required:**

- **Fee as a fraction of stake.** At sub-dollar stakes the fee is a large
  fraction of the bet and it is the one cost he controls directly, by betting
  fewer and larger. Combos are worse still: the fee model is hedged upward there
  and ADR 0012 §5 records it as unverified.
- **His own cadence, time of day, and session length**, shown raw.
- **His stake sequence with wins and losses marked** — the tilt picture, shown,
  not tested.
- **Fill rate**, which tells him whether his typed ceiling is habitually too
  tight to fill.
- **The distribution of his disagreement with consensus at bet time** — how much
  disagreement he requires before he acts. A fact about his threshold, and
  explicitly not about who is right.

**Actionable eventually, and only this one:** the calibration bias, at `G ≈ 300`
game-clusters, and only for biases of ~12 points or larger. At 1–3 bets/day that
is roughly **a year to three years away**.

**Never actionable:** win rate (no null at any `n`, §2.2) and P&L as a verdict
(~3,900–10,000 bets, §2.1). And CLV cannot carry a verdict here without
reopening ADR 0038.

**One line:** *the descriptive panels are the useful ones and they are useful on
day one; the inferential ones will not speak for a year at best, and one of them
will never speak at all.*

---

## 12. WHAT THIS DOES NOT ESTABLISH

Drafted before the run, deliberately, because caveats written afterwards are
selected to be survivable.

1. **Nothing about whether Joe has an edge.** ADR 0038 closed that question and
   this measurement does not reopen it. No result here may be cited as evidence
   for or against edge.
2. **Nothing about whether the consensus is right.** `beta = −0.141`. Agreement
   with consensus is not correctness and disagreement is not error, and no rule
   in this file scores him either way.
3. **Nothing about calibration on bets he did NOT place.** The estimate is
   captured at the ticket, so the sample is conditioned on his wanting to bet.
   `desk_passes` carries `scope` and `reason` and **no ticker and no
   probability**, so there is no instrument that could de-select this sample, and
   none is proposed. This is the largest structural limitation in the document.
4. **Nothing about anchoring beyond the ticket mask.** ADR 0065 masks the ask
   until the estimate is entered, which is why calibration is worth measuring at
   all — but that is a UI ordering, not proof of independence. He can see the
   price on the slate, on the market screen, or in the Kalshi app before he ever
   opens the ticket. A measured bias is therefore a bias in *the numbers he types
   at the ticket*, not necessarily in his private belief.
5. **Nothing about the completeness of the record.** `venue_settlements` is the
   poller's mirror: positions settled before 2026-08-18 or during downtime are
   absent, and open positions are structurally absent (`bets.py`). Absence here
   is not a zero.
6. **Nothing about how often he was stopped.** Refused orders write no row
   (§6g). "The brakes are working" is not a claim this data can support.
7. **Nothing about whether the CLV-covered subset represents his betting.**
   Coverage is selected on discovery-plus-link (§5.4) and skews toward mainstream
   team markets.
8. **Nothing about `desk_attention` beyond the retention window**, which is
   pruned.
9. **Nothing that generalises across time.** A calibration bias is a property of
   a person, on the sports and market types he bet, during the window measured.
   It is not a constant, and a bias measured on a WNBA-heavy window is a WNBA
   result until a second sport says otherwise.
10. **Nothing about the combination stratum's fees.** ADR 0046's model
    undercharges on combos and the applied coefficient there is a hedge, so any
    net figure inside the combo stratum inherits an unverified cost model.
11. **Nothing that authorises a change to money-touching code.** The gate stays
    where it is; `ORDERS_ARE_DRY_RUNS` stays True; no cap moves on the strength
    of any number produced here.
12. **Nothing about causes.** Every panel reports what happened. "You bet more
    after a loss" is a description of a sequence, not evidence of tilt, and the
    screen must not name a cause.

---

## 13. Status

**READY.** Every section above is fixed. Nothing was left open on the grounds
that we would see what the data looks like.

**This file must be committed before any query is run against `manual_orders`,
`venue_settlements`, or `closing_lines` for this purpose.** A pre-registration
that is not in the history has not been pre-registered.

Amendments are **additive and dated**, never edits.
