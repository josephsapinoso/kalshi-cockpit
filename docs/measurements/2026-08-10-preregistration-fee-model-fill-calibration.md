# Pre-registration — resolving the fee model with four real fills

**Written 2026-08-10 (UTC), before any fill exists on this account.**
ADR 0021 §8 **Option E**, chosen by Joe. ADR 0021 §7.4 is the open question this
closes.

- Owner: `pre-registrar` (agent), on behalf of Joe. Scoped by `partner`.
- Scored against by: `measurement-skeptic`, after the fills.
- Negative-result destination: fixed in §9, before the result exists.
- **Status at registration: READY.** §V.
- Placement is **by hand, in the Kalshi app**. `ORDERS_ARE_DRY_RUNS` stays
  `True`; arming remains a code change (ADR 0018) and **nothing in this document
  moves that boundary in either direction**. No code in this repo places any of
  these orders. No deploy is required by this design.

> **Zero fills exist on this account at the time of writing.**
> `backend/kalshi/rest.py:493-519` states it: the `/portfolio/fills` *envelope*
> was probed against production on 2026-08-09 and is correct, and **every field
> inside a record is unobserved** — including whether the fee is called `fee`,
> what units it carries, and whether it is per-contract or per-order. That is a
> precondition of this design (§P1), not a footnote, and a parallel lane owns it.

---

## §0. What was already known when this was written

**[COMPUTED FROM CODE — `backend/core/fees.py`, re-derived independently with
`fee_candidates` for this document; the coordinating brief's figures were
checked rather than copied.]**

Two candidate models, both from secondary sources, disagreeing:

```
Model A   fee = ceil_to_cent( 0.07 x C x P x (1-P) )          per ORDER round-up
Model B   fee = C x round_half_up_to_cent( 0.06 x P x (1-P) ) per CONTRACT round
```

### §0.1 Where they agree, and therefore where a fill buys nothing

**[COMPUTED — whole-cent prices 1c..99c, taker]**

```
AGREE at N=1  : 10-17c, 50c, 83-90c
AGREE at N=2  : 10-17c, 50c, 83-90c
AGREE at N=3  : 11-17c, 50c, 83-89c
AGREE at N=5  : 14-17c, 83-86c
AGREE at N=10 : 16, 17, 83, 84c
AGREE at N=20 : 17c, 83c
```

The brief's agreement sets at N=1 and N=10 reproduce **exactly**. So does every
separation figure it quoted: `45c N=20 A=$0.35 B=$0.20`; `45c N=10 A=$0.18
B=$0.10`; `20c N=1` and `30c N=1` both `A=$0.02 B=$0.01`; `10c N=20 A=$0.13
B=$0.20`; `50c N=20 A=$0.35 B=$0.40`. **One contract at 50c charges $0.02 under
both models and resolves nothing.** Confirmed.

### §0.2 The one number in this repo that the whole design turns on

**[COMPUTED — exhaustive over all 999 tradeable prices]** at **N = 1**,
`max(model_a, model_b) == model_a` at **every** price. `model_b` never exceeds
`model_a` at one contract.

`core/sizing.py:156` prices every sizing decision at `contracts=1`, and every
statistic in ADR 0021 is computed at `E1` — the net edge at one contract. So:

> **The deployed money path is already running Model A, everywhere.**
> Declaring A changes no number in ADR 0021. Declaring B moves the deployed N=1
> fee **down by exactly 1.00 cent (10.0 tenths)** at **82 of the 99 whole-cent
> prices**, and by zero at the other 17.

**[COMPUTED — `2026-08-10-clean-shortfall-pull.json`, pin 1564]** 593 of the 614
clean rows sit at prices in the 82. The `S_min`-attaining observation is
**id 726, `KXMLBGAME-26AUG091335NYMPIT-NYM` yes, ask 450**, with
`E1 = −2.0534` tenths deployed and **`E1 = +7.9466` tenths under Model B**.

§0.4 of the clean-shortfall registration established that the smallest `E1` that
sizes to `>= 1` contract has supremum **1.0 tenths**. `+7.95 > 1.0`. So under
Model B that observation is **actionable**, and ADR 0021's headline is not the
same sentence.

**This is stated before the fills exist, deliberately, and it is not a
prediction.** It is the reason the measurement is decision-relevant, computed in
advance so that it cannot later look like it was reached for. §9 carries the
consequence in both directions. **No count of rows that would become actionable
is asserted anywhere in this document** — two of the eleven suppression checks
are functions of the edge (`edge_within_method_noise`, `suspicious_edge`), so the
clean population itself moves when the fee moves, and that requires a re-run to
resolve. The single-row sign flip above is arithmetic on a fixed row whose
suppression status does not change (its stored edge rises ~10 tenths, staying
above the median 1.3-tenth method spread and far below the 40.0 ceiling).

### §0.3 Provenance labels

Every quantity is **[COMPUTED FROM CODE]**, **[MEASURED FROM DATA]** or
**[ASSUMED]**. The assumed inputs are enumerated in §11 and there are **three**.

---

## §C. Corrections to the brief, made before the design was fixed

Recorded rather than quietly fixed. Every figure in the brief that I could check
reproduced; these are additions and one contradiction.

### C1. "A design that exploits the sign flip is strictly stronger" — agreed, and quantified. Its benefit is asymmetric.

Agreed, and it is the organising principle of §1. **[COMPUTED — §Power]**
against a 968-member family of plausible fee models, worst case over every price
Joe could pick inside the registered bands:

| Cell set | signs | worst `|class(A)|` | worst `|class(B)|` |
|---|---|---:|---:|
| F1 + F2 (both `A>B`) | same | 33 | 346 |
| F1 + F3 (`A>B`, `B>A`) | **opposite** | **18** | 287 |

So the sign flip roughly **halves** the surviving family on the A side. On the B
side it is nearly inert — what shrinks `class(B)` is a *high-`p(1−p)`* cell
(F4), not opposite signs. The brief's claim is right and its benefit is not
symmetric; the design uses both levers.

### C2. The sign flip is far cheaper than the brief's examples suggest

The brief reaches the flip at `N=20`. **[COMPUTED]** it is reachable at **N=4**
(10–12c, and 50c) and *rounding-robustly* at **N=7** (12–14c, max stake $0.98).
Registering `N=20` in §1 is a choice about **separation size** (1–5c rather than
1c), not a necessity. No $17 of favourite-side stock is required.

### C3. **The sign flip does not exist on the maker path.** This contradicts the brief's framing.

**[COMPUTED FROM CODE]** Model B's maker multiplier is
`SPORTS_MAKER_MULTIPLIER = 0.06/4 = 0.015`, so its per-contract raw fee is
`0.015 · p(1−p) <= 0.00375` at every price — **always below the half-cent
rounding boundary.**

> **Model B predicts a maker fee of exactly $0.00 at every price and every
> size.** Model A's maker fee is `ceil(0.0175 · N · p(1−p))`, which is `>= $0.01`
> whenever `N · p(1−p) > 0`.

So on the maker path `A >= B` everywhere and **B is never the larger**. The
"strictly stronger" design the brief asks for exists **only for taker fills**.
This is why §1 registers taker, and why §3 registers what a maker fill does
instead of leaving it open.

It also creates a free, very sharp secondary check: **any non-zero maker fee
refutes Model B outright.**

### C4. 50c is the worst calibration price at *any* size, for a reason the brief does not give

The brief rules out `50c N=1` because the models agree. True. The deeper reason
to avoid 50c is that **both models sit exactly on their own rounding boundaries
there**: Model A's raw fee is `0.0175·N` (a whole cent at `N` = 4, 8, 12, …) and
Model B's per-contract raw fee is **exactly $0.015**, the half-cent tie. A
mismatch at 50c is therefore uninformative about the *coefficient* — it can be
produced by the rounding tie-break alone. **No registered cell touches 50c.**

### C5. `linear_cent` is the measured grid on the universe this touches, and the design does not depend on it

**[MEASURED — `scripts/capture_price_grids.py`, 2026-08-08, quoted in
`backend/kalshi/grid.py`]** 1,426 game markets, one distinct grid,
`linear_cent` on every one. That is a fact about the slate, **not** about the
exchange, and `grid.py` warns against promoting it.

So this design does not rely on it. **[COMPUTED]** every registered band was
re-checked at **every tenth of a cent inside it**, not only at whole cents:

```
F1 band, N=1  : 71 of 71 tenths discriminate; sign uniformly A>B; |A-B| = $0.01
F2 band, N=10 : 71 of 71 tenths discriminate; sign uniformly A>B; |A-B| $0.03-0.05
F3 band, N=20 : 41 of 41 tenths discriminate; sign uniformly B>A; |A-B| $0.01-0.05
F4 band, N=1  : 41 of 41 tenths discriminate; sign uniformly A>B; |A-B| = $0.01
```

**A sub-cent fill inside a registered band is valid and does not void the cell.**
The prediction is computed from the price actually observed.

---

## §P. Preconditions — checked before any comparison is made

Each is yes/no. If any is NO, the run stops and this file is **amended by
appending**, never edited in place.

- **P1 — a fee-shaped field exists on the fill record.** Owned by the parallel
  capture lane (`scripts/capture_fills_fixture.py`), which this document does not
  touch. If no field on a real fill carries a fee, **the primary observable does
  not exist**, and only the registered fallback of P2 applies.
- **P2 — the fallback observable, registered now rather than chosen later.**
  If P1 is NO, `fee_observed` for a cell is
  `(balance_before − balance_after) − N × price_paid`, from
  `KalshiClient.balance()` (`rest.py:506`) read immediately before and
  immediately after that one order, with **no other order and no settlement
  in between**. If any of those conditions fails, the cell is **VOID**. No other
  fallback is permitted, and in particular no fee may be inferred from an
  in-app display alone (§S item 6 makes the app display a cross-check, never
  the measurement).
- **P3 — the unit is identified, mechanically, from F1 alone.**
  The units of the fee field are unobserved. Interpret F1's raw value as
  **dollars**, as **cents**, and as **centi-cents**. Retain each interpretation
  whose implied fee lies in `[$0.001, $0.10]`. If **exactly one** survives, that
  is the unit for all four cells. If zero or more than one survives, **STOP —
  the unit is not identified and no comparison is made.** ($0.10 is a ceiling no
  plausible model can reach on one contract at 30c; the largest candidate is
  $0.02.)
- **P4 — one fill row per order.** Model A rounds up *on the whole order*; if an
  order fills in pieces, its prediction is ambiguous between per-order and
  per-fill rounding, which is not a distinction this design can resolve. A cell
  whose order returns more than one fill row is **VOID**.
- **P5 — the fill is a taker fill.** §3. A maker fill is **not** void; it is
  evaluated against the maker predictions registered in §1, and §3 states what
  is lost.
- **P6 — the observed price is inside the registered band.** A fill outside the
  band is **VOID**. Its fee is still published (§S).
- **P7 — F1's recorded fee is unchanged after F2 is placed.** F1 and F2 sit in
  the same market. If Kalshi aggregated separate orders for fee purposes, F1's
  recorded fee would move retroactively. Re-read it; if it changed, **STOP THE
  LINE** — the per-order model is under-specified in a way no cell here tests.
- **P8 — every void is recorded with its mechanical reason, and the observed fee
  is published anyway.** This is the anti-gaming rule and it is load-bearing:
  every reason in P4–P6 is checkable **without looking at the fee value**, and
  publishing the fee of every voided cell removes the incentive to void one.

---

## §1. The question, as a claim that could be false

> **H1 — MODEL A IS KALSHI'S TAKER FEE MODEL FOR SPORTS.** For every non-void
> registered cell, the fee Kalshi charged equals Model A's prediction at the
> observed `(price, contracts)` **exactly, to the cent**.
> *Direction: one-sided conjunction. Falsifier: one cell where the charged fee
> differs from Model A's prediction by one cent or more.*

> **H2 — MODEL B IS KALSHI'S TAKER FEE MODEL FOR SPORTS.** Same, against Model
> B's prediction.
> *Direction: one-sided conjunction. Falsifier: one cell where the charged fee
> differs from Model B's prediction by one cent or more.*

> **H3 — NEITHER.** At least one non-void cell matches neither model.
> *This is the outcome that matters most and it is registered as a first-class
> claim, not as a residual.* It has three named sub-cases (§7): **H3+** any
> observed fee **exceeds** `max(A, B)`; **H3−** any observed fee falls **below**
> `min(A, B)`; **H3=** every observed fee lies weakly between them but no single
> model matches all cells — the **SPLIT** case, meaning the truth is a hybrid
> (for example Model A's coefficient with Model B's per-contract rounding).

> **H4 — SETTLEMENT CHARGES NO SECOND FEE.** `core/fees.py`'s docstring asserts
> *"settlement is not a trade"*, and `settlement_fee()` depends on it. These four
> positions are held to settlement (§8), so the claim is testable for free.
> *Direction: declared on a count of zero. Falsifier: any additional fee or
> charge attributable to the settlement of any of the four positions.*
> **[ASSUMED, A3 in §11]** that such a charge, if it existed, would be visible
> on the account. The paired guard against the zero-that-means-no-measurement is
> §R5.

**Every universal quantifier here is deliberate and narrow.** "Every non-void
registered cell" is four cells, not every price and not every size. §10 says so
at full strength. The claim is **not** "Model A is Kalshi's fee model"; it is
"Model A matched at these four cells", and §7's declaration wording enforces
that distinction.

### The four cells, fixed now

Bands are on **the price actually paid — the ask you cross**, never a mid.
Predictions are **[COMPUTED FROM CODE — `fee_candidates(price_tenths, N,
maker=False)`]**.

| Cell | Band (ask) | `N` | Model A | Model B | sign | max stake | robustness |
|---|---|---:|---|---|:--:|---:|---|
| **F1** | **23–30c** | **1** | $0.02 | $0.01 | A>B | $0.30 | ROBUST |
| **F2** | **23–30c** | **10** | $0.13–$0.15 | $0.10 | A>B | $3.00 | ROBUST |
| **F3** | **12–16c** | **20** | $0.15–$0.19 | $0.20 | **B>A** | $3.20 | ROBUST |
| **F4** | **45–49c** | **1** | $0.02 | $0.01 | A>B | $0.49 | **KNIFE-EDGE** |

Cent by cent, so nothing is computed after the fact:

```
F1  N=1    23c A .02 B .01 | 24c .02/.01 | 25c .02/.01 | 26c .02/.01
           27c .02/.01     | 28c .02/.01 | 29c .02/.01 | 30c .02/.01
F2  N=10   23c A .13 B .10 | 24c .13/.10 | 25c .14/.10 | 26c .14/.10
           27c .14/.10     | 28c .15/.10 | 29c .15/.10 | 30c .15/.10
F3  N=20   12c A .15 B .20 | 13c .16/.20 | 14c .17/.20 | 15c .18/.20 | 16c .19/.20
F4  N=1    45c A .02 B .01 | 46c .02/.01 | 47c .02/.01 | 48c .02/.01 | 49c .02/.01
```

**Maker predictions, registered in advance so nothing is chosen if a fill comes
back the other kind** **[COMPUTED — `fee_candidates(..., maker=True)`]**:

```
F1 maker  A $0.01  B $0.00        F3 maker  A $0.04-$0.05  B $0.00
F2 maker  A $0.04  B $0.00        F4 maker  A $0.01        B $0.00
```

**ROBUST vs KNIFE-EDGE is fixed here, before the run, and it is not a
verdict-selection knob.** A cell is ROBUST when both models' raw values sit at
least 0.1c from their own rounding boundary at every whole-cent price in the band
(F1 min margins A 0.0024 / B 0.0024; F2 0.0011 / 0.0024; F3 0.0014 / 0.0013).
F4 is KNIFE-EDGE because Model B's per-contract raw fee at 49c is **$0.014994**,
six millionths of a dollar below the half-cent tie. That fragility is precisely
what makes F4 the strongest coefficient discriminator (§Power), and §7 binds the
verdict to the **strict** conjunction over all four cells; the ROBUST-only
reading is a printed diagnostic that **may not be reported as the verdict**.

### Why F1 and F2 share a market and a band

Placed in the **same market**, F1 (N=1) then F2 (N=10), F1 first. If both fill at
the same price, a bonus reading is available at zero extra cost and is registered
now: **Model B is exactly linear in `N` at fixed price; Model A is not**, unless
its raw value is already a whole-cent multiple. `fee(F2) == 10 × fee(F1)` is
therefore evidence for per-contract scope, and `fee(F2) < 10 × fee(F1)` for
per-order. If the two fill prices differ, this bonus reading is **unavailable**
and each cell still stands alone. It is a bonus, never a substitute for §7.

---

## §2. The population, and the exclusions

**Included:** exactly the four registered orders, placed by hand in the Kalshi
app on Kalshi **sports game markets**, within the window of §8.

**The dependent variable is the fee**, which is determined at fill time by
`(price, contracts, taker/maker, category)` and by nothing else. It is
**independent of the game's result by construction**. No exclusion in this
document references a game outcome, a settlement, a P&L, or an edge — and none
could, because the quantity is fixed before the game starts.

| Excluded | Why | Independent of the fee value? |
|---|---|---|
| An order returning >1 fill row (P4) | Model A's prediction is ambiguous between per-order and per-fill rounding. | **Yes** — a count of rows. |
| A fill outside the band (P6) | The band is the registered cut. | **Yes** — a price. |
| A fill in a non-sports market | Model B's multiplier is **per category**; `SPORTS_MULTIPLIER` is a claim about sports only. | **Yes** — a series ticker. |
| The fallback failing its conditions (P2) | Balance arithmetic is only valid when it brackets one order. | **Yes.** |

**A rule that must not be activated after the fact.** If a verdict comes back
NEITHER, the temptation will be to widen a band, drop the knife-edge cell, or
re-read a voided cell. **All three are forbidden.** The precedent is in this
repo: a combo experiment pre-registered an exclusion and the agent correctly
**refused to activate it** when the sample turned out too thin. That refusal was
only possible because the rule existed in writing first.

**Nothing observed here may be used to fit a new model in this document.** If
the verdict is NEITHER, the observed fees are a **hypothesis generator, labelled
as such**, and any third model must be confirmed by a **new** pre-registered set
of fills before it is deployed. Fitting a coefficient to four fills and shipping
it is exactly the failure this registration exists to prevent.

---

## §3. The unit of observation, and taker vs maker

**The unit is one order.** Not one contract, and not one market.

Two units are independent if they are separate orders. The 20 contracts of F3 are
**one** observation, not twenty: they are charged by one formula evaluation, and
under Model A the per-order round-up makes them mathematically inseparable. **The
clustering variable is `order_id`.** Any presentation of these results with
`n = 31` (the contract count) is wrong; `n = 4`.

`n = 4` is not a sample size in any statistical sense. §5 says why that is
appropriate here and §7 says why no interval appears anywhere.

### Taker, registered

**All four fills are taker fills.** Joe places a **limit buy at exactly the
displayed ask**, quantity `N`, in a market whose displayed resting size at that
ask is `>= N`. A marketable limit crosses immediately and Joe is the taker; a
resting order may never fill at all, and a partially-resting order breaks P4.

**What happens if a fill comes back maker** (some `is_taker`-shaped field on the
record says so, or the fee matches no taker prediction and matches a maker one):

1. The cell is **not void**. It is evaluated against the **maker predictions
   registered in §1**, which were fixed before any fill existed.
2. **The sign flip is lost for that cell** (§C3: Model B predicts $0.00 maker fee
   at every price and size, so `A >= B` everywhere on the maker path). If **F3**
   comes back maker, the write-up must state, in these words, that **the design
   did not achieve the sign flip**, and the §Power figures for `class(A)` and
   `class(B)` do not apply.
3. A **non-zero** maker fee on any cell **refutes H2 outright**, which is the one
   thing the maker path does better than the taker path.

### Choosing among candidate markets — the rule, fixed so it cannot be gamed

> Scan the Kalshi app's sports list **in its default order, top to bottom**.
> Take the **first** market whose displayed ask lies inside the cell's band and
> whose displayed size at that ask is `>= N`. Stop there. **No re-scanning, no
> comparison between candidates, no waiting for a better price.**

Recorded at placement, from the app: ticker, series prefix, displayed ask,
displayed size at the ask, and the timestamp. If **no** qualifying market exists
in one full scan, the cell is **NOT ATTEMPTED** and is reported as such
(§7). **There is no substitute band.**

The mirror is permitted and costs nothing analytically: the fee depends on
`p(1−p)`, which is symmetric about 50c, so an ask of 76c is the **same cell** as
an ask of 24c. **[COMPUTED]** the mirror bands are `70–77c` (F1/F2, max stake
$0.77 / $7.70) and `84–88c` (F3, max stake $17.60) and `51–55c` (F4, max stake
$0.55). They carry identical predictions and materially higher stakes; **prefer
the cheap side.** Because the fee is symmetric, this design cannot and does not
distinguish "the fee uses the price of the contract bought" from "the fee uses
the YES price" — and it does not need to.

---

## §4. The cut — bucket edges, fixed in advance

The bands in §1 **are** the cut, and they are on the derived ask. They were
chosen before any fill by three data-blind criteria, in this order:

1. **`A != B` at every tenth inside the band** (§C5), so Joe's price choice
   inside a band cannot change which model the cell discriminates.
2. **The sign of `A − B` is constant inside the band**, so the direction each
   cell tests is fixed before the price is known.
3. **Rounding margin `>= 0.1c` for both models at every whole cent** — except F4,
   labelled KNIFE-EDGE in §1 and included deliberately for resolution.

**No band may be widened, narrowed, shifted or added after any fill is
observed.** Bucket boundaries are the richest source of unearned findings
precisely because so many are defensible.

**50c is excluded from every band** (§C4). So are 10–17c and 83–90c at `N=1`,
where the models agree.

---

## §5. The statistic, named as an estimator

**There is no estimator.** This is not an inference.

Each cell yields an **exact integer-cent comparison** between one observed value
and two deterministic predictions. The quantity compared is a **charged fee**,
not a sample mean, not a proportion, not a difference of proportions.
`sqrt(p(1-p)/n)` is correct for none of it and appears nowhere in this design.

What is being estimated, said out loud: **nothing**. What is being *decided*:
which of two deterministic functions Kalshi is evaluating — a model-selection
question with three answers, resolved by exact equality.

**A single mismatching cent refutes the model.** `FEE_MATCH_TOLERANCE_DOLLARS =
1e-9` is float noise only and is not a business tolerance; `core/fees.py:212-225`
records that the previous value, half a cent absolute, let a model be **50%
wrong** on a one-contract fill and still pass the check the gate treats as
stop-the-line.

The counterargument to resist, named here so it is recognisable when it arrives:
*"it is only one cent."* One cent at `N=1` is **50–100% of the entire fee**. It
is **10.0 tenths**, against a clean-shortfall distribution whose maximum is
**−2.05 tenths** and against total headroom of **0.38 percentage points**. A cent
is five times the distance from the record's best row to the decision boundary.

---

## §6. The extraction

1. Joe places the four orders by hand, in the order **F1, F2, F3, F4**, with at
   least 60 seconds between F1 and F2, recording the §3 fields at each placement.
2. An agent session runs the parallel lane's capture path against
   `/portfolio/fills`. **This document does not specify, own or modify that
   script.** No deploy, and no laptop step for Joe.
3. `configure_logging()` **before** any client is constructed. `httpx` logs full
   request URLs at INFO and this repo has already put a working credential into a
   transcript that way.
4. The raw payload is cached to
   `docs/measurements/<run-date>-fee-calibration-fills.json` so the analysis is
   re-readable without re-pulling. It is checked for and stripped of any
   credential before it is committed.

---

## §7. The decision rule, with the multiplicity already counted

### The multiplicity count, in the currency that applies here

**Cells read: 4.** Comparisons: 8 (four cells × two models). **No cell carries an
interval, a standard error, a p-value or a significance mark**, so no cell can
produce a false finding by clearing a threshold, and the family-wise error rate
of this design is **empty rather than controlled**.

The decision rule is **conjunctive**: a model is declared only if it matches
**every** non-void cell. **Adding cells can therefore only make declaration
harder.** There is no multiple-comparison inflation of false declarations here;
the multiplicity runs the other way, and the honest accounting of "how wrong can
a declared model still be" is the family-partition arithmetic of §Power, not an
alpha budget.

**Is the record looked at more than once as it grows?** Yes — `core/fees.py`
requires every future `fee_predicted != fee_actual` to be treated as
stop-the-line, forever. **That does not need an always-valid boundary and the
reason is structural, not a concession**: an exact-equality check against a true
deterministic model **never fires**, however many times it is evaluated. The
13.7% floor measured in this repo applies to a *threshold on a noisy statistic*
re-evaluated against an accumulating database. This is not that. This
registration covers exactly the four fills of §1; the permanent gate is a
different instrument with a different property.

### The decision rule, verbatim

> **GUARDS FIRST.** P1–P8 and §R1–§R5 are evaluated and printed **before any
> verdict**. If P3 (unit identification) or P7 (retroactive fee change) fails,
> the run reports **STOP THE LINE** with the failed precondition named, and **no
> model is declared**. Voided cells (P4, P6, P2) are excluded from every
> conjunction, are listed with their mechanical reason, and **their observed fee
> is published anyway**.
>
> **Let `C` be the set of non-void cells.** For each cell in `C`, `fee_observed`
> is compared to `model_a` and to `model_b` evaluated at the **observed** price
> and contract count, and at the **observed** taker/maker kind, using the
> predictions registered in §1. Equality means **exact equality in whole cents**;
> `FEE_MATCH_TOLERANCE_DOLLARS = 1e-9` admits float noise and nothing else.
>
> **H1 — MODEL A DECLARED** iff `C` is non-empty and every cell in `C` matches
> `model_a` exactly.
> **H2 — MODEL B DECLARED** iff `C` is non-empty and every cell in `C` matches
> `model_b` exactly.
> **H3 — NEITHER** iff at least one cell in `C` matches neither. Report the
> sub-case: **H3+** if any `fee_observed > max(model_a, model_b)`; **H3−** if any
> `fee_observed < min(model_a, model_b)`; **H3=** (SPLIT) otherwise.
> **H1 and H2 are mutually exclusive by construction**, because every registered
> band has `A != B` at every tenth (§C5).
>
> **COVERAGE QUALIFIER, mandatory and mechanical.** A declaration is reported as
> **FULL** only if `C` contains at least one cell with `A > B` **and** at least
> one cell with `B > A`, both taker. Otherwise it is reported as
> **PARTIAL — CONSISTENT WITH, DOES NOT EXCLUDE**, and the write-up must state
> in those words that the sign flip was not achieved and that the §Power figures
> do not apply.
>
> **THE STRICT READING GOVERNS.** The conjunction over **all** of `C` is the
> verdict. The conjunction over ROBUST cells only (F1, F2, F3) is printed beside
> it as a diagnostic and **may not be reported as the verdict, quoted as the
> verdict, or used to describe the result in any summary.** If the two disagree,
> the write-up says so explicitly and reports the strict one.
>
> **NOT ATTEMPTED is not a void and not a failure.** A cell for which no
> qualifying market was found (§3) is reported as `NOT ATTEMPTED`, is excluded
> from `C`, and triggers the coverage qualifier if it removes a sign.
>
> **NO CELL, NO SUB-READING AND NO BONUS READING may substitute for the
> conjunction**, be reported as significant, or be described with any word
> implying a test.
>
> **H4 — SETTLEMENT.** After all four positions settle: **declared** iff the
> total fees attributable to the four positions equal the sum of the four entry
> fees, exactly. **Refuted** iff any additional charge appears; the write-up then
> names `core/fees.py`'s *"settlement is not a trade"* and `settlement_fee()` as
> **wrong**, which is a larger finding than anything H1–H3 can produce.

### Consequences, fixed before the answer

| Verdict | What is built | What is killed |
|---|---|---|
| **A declared, FULL** | `calculate_fee` is simplified to Model A; the `max()` hedge is deleted; `fee_candidates` is retained **only** as the gate's diagnostic. | Nothing in ADR 0021 moves — **[COMPUTED, §0.2]** the deployed N=1 fee already *is* Model A at every price. The refutation stands unamended and this run is a **confirmation**, which is what it must be labelled. |
| **B declared, FULL** | `calculate_fee` becomes Model B. The break-even bar is recomputed (it is currently 52.00% because `calculate_fee` charges the conservative maximum). **ADR 0021 must be re-run against the new fee before any of its numbers may be quoted again.** | The claim *"no clean observation clears the fee"* is **suspended pending that re-run** — **[COMPUTED, §0.2]** the deployed N=1 fee falls 1.00c at 82 of 99 whole-cent prices, 593 of 614 clean rows sit at those prices, and the `S_min` row's `E1` moves from −2.05 to **+7.95** tenths. |
| **NEITHER (H3+)** | An immediate stop-the-line of the highest order: **the deployed "conservative maximum" is not conservative** and every recorded `fee_predicted` understates the true cost. CLAUDE.md's rule 1 applies at full force. | Every EV, edge and CLV figure in the repo computed against `fee_predicted`. |
| **NEITHER (H3−, H3=)** | The `max()` hedge **stays**, unchanged. A new registration with new fills is required. | The claim that the hedge is "temporary and self-resolving" in four fills. It is not. |
| **PARTIAL anything** | Nothing is deployed. | Nothing. The write-up says the design under-delivered and why. |
| **H4 refuted** | A `settlement_fee` correction and its own ADR. | `settlement_fee()`'s current contract, and any backtest that used it. |

**Is this decision-relevant, honestly?** Yes, and **asymmetrically**, which is
worth stating rather than smoothing over. Declaring A changes no number and
builds nothing — it converts an assumption into a measurement and deletes a
hedge. Declaring B, or NEITHER-H3+, moves every number in ADR 0021. A
measurement that is confirmatory on one branch and decisive on the other is still
decision-relevant; a measurement that proceeds identically either way would not
be, and this one does not.

---

## §R. Reachability guards — both directions, before the data exists

This repo's joint bound died because nothing checked whether its decision value
was reachable, and the clean-shortfall run stopped itself because something did.

### R1 — every declared outcome is attainable on the registered grid

**[COMPUTED]** `A != B` at **every tenth of a cent** in every registered band
(§C5: 71/71, 71/71, 41/41, 41/41). Kalshi charges whole cents, and every
prediction in §1 is a whole number of cents. The order grid on the measured
universe is `linear_cent` (1–99c), and every band is a contiguous run of whole
cents inside 1–99. **Each of H1, H2 and H3 is reachable by some integer-cent
observation at every price Joe can legally trade in every band.**

### R2 — the falsifier of each declaration is reachable

H1's falsifier is an observed fee `!= model_a` at any cell. Since
`model_b != model_a` everywhere in every band, **Model B's own prediction is a
falsifier of H1 that is a legal integer-cent value at every price in every
band** — and vice versa. Neither claim can be true by construction.

### R3 — the sign flip is arithmetically present, and its loss is detectable

**[COMPUTED]** F1, F2 and F4 have `A > B` at every tenth; **F3 has `B > A` at
every tenth**. `|A − B|` on F3 runs $0.01 (16c) to $0.05 (12c). No single model
in the family can match both an `A > B` cell and a `B > A` cell unless it *is*
the matching model. **The loss of the flip has exactly two mechanisms and both
are detected**: F3 comes back maker (§3 item 2), or F3 is NOT ATTEMPTED / VOID
(coverage qualifier, §7). Neither can happen silently.

### R4 — no cell can saturate

The direct mirror of the ladder that returned 984 of 1,000. Each cell has exactly
two candidate predictions and they differ, so no cell can return a value
consistent with everything. **[COMPUTED — §Power]** the four cells together
partition a 968-member plausible-model family into at least **51** classes at
the worst price choice; a design that partitioned it into one would discriminate
nothing.

### R5 — H4 is a zero-count claim, so it needs a paired guard

A claim declared on a count of zero is the shape that has already failed twice in
this repo — `tasks/lessons.md`, *"the zero that means no measurement passes every
threshold"*. **Registered guard:** H4 may be declared only if the same query that
counts settlement charges returns the **four entry fees**, non-zero, on the same
records. If the query returns zero settlement charges **and** cannot see the entry
fees either, it is measuring nothing, and that is a **STOP THE LINE naming the
harness rather than the exchange.**

---

## §Power — the check that comes before all of it

**Can four fills answer this question?** The question is model *selection* among
deterministic functions with integer-cent outputs, so the right power currency is
not an effect size — it is **how much of the plausible-model space survives a
declaration.**

**Method, fixed before the run.** Define a family of 968 plausible fee models:
coefficient `c` on a grid of 121 values from 0.0400 to 0.1000 in steps of 0.0005;
rounding in {ceil, floor, half-up, half-even}; scope in {per-order,
per-contract}. Model A = `(0.07, ceil, order)`; Model B = `(0.06, half_up,
contract)`; both are members. For each combination of prices Joe could pick
inside the four bands, partition the family by its predicted fee vector, and
take the **worst case**. The 0.0005 coefficient step and the 0.040–0.100 range
are choices, stated so they can be attacked; the conclusions below are about
orders of magnitude, not about the last digit.

**[COMPUTED — worst case over every whole-cent price choice in the four bands]**

```
                          worst |class(A)|      worst |class(B)|
F1 alone                       442 / 968             602 / 968
F2 alone                        45                   346
F3 alone                        37                   394
F1 + F2  (same sign)            33                   346
F1 + F3  (sign flip)            18                   287
F2 + F3                         37                   265
F1 + F2 + F3                    18                   265
F1 + F2 + F3 + F4               18 (1.9%)             98 (10.1%)
```

**What survives a declaration, characterised:**

```
class(A), worst case, 18 of 968:
    scope = per-ORDER only    ceil       coefficient 0.0665 - 0.0710   (10)
                              half-even  coefficient 0.0715 - 0.0730   ( 4)
                              half-up    coefficient 0.0715 - 0.0730   ( 4)
class(B), worst case, 98 of 968:
    scope = per-CONTRACT only ceil       coefficient 0.0400            ( 1)
                              floor      coefficient 0.0745 - 0.0805   (13)
                              half-even  coefficient 0.0400 - 0.0605   (42)
                              half-up    coefficient 0.0400 - 0.0605   (42)
```

**Three conclusions, all of which belong in the write-up before it is written:**

1. **The scope is fully resolved and the coefficient is not.** Every surviving
   member of `class(A)` is per-order; every surviving member of `class(B)` is
   per-contract. **The four fills decide per-order versus per-contract
   rounding outright.** They pin Model A's coefficient to roughly ±0.003 and
   Model B's to roughly ±0.010 — and the asymmetry is structural, not fixable
   by spending more: per-contract rounding destroys coefficient information at
   every size, so **no number of fills at these prices sharpens B the way `N`
   sharpens A.**
2. **The residual, in the units that matter.** Over whole-cent prices × `N` in
   {1, 10, 20, 100}, a surviving member of `class(A)` can differ from A by up to
   **$0.09**, and of `class(B)` from B by up to **$1.00** (at `N=100`). **At
   `N=1` — the size at which `sizing.py:156` prices every actionable decision —
   the maximum residual is $0.01 in both classes.** One cent at `N=1` is
   **10.0 tenths**, which is larger than the entire clean-shortfall distribution.
   So the honest verdict is: **these fills resolve the model form decisively and
   do not resolve the N=1 fee to better than one cent at untested prices.**
3. **What actually covers the untested range is the permanent gate, not more
   fills.** `core/fees.py` already requires every future
   `fee_predicted != fee_actual` to be stop-the-line. That check is exact and
   never fires under a true model (§7), so it accumulates coverage across every
   price and size the tool ever trades, for free. **The four fills are its first
   four observations, not a substitute for it.** §9 makes retiring the hedge
   conditional on that gate staying armed.

**Verdict of the power check: the design can answer the question it registers.**
It cannot answer "what is Kalshi's fee at every price", and §1 does not claim to.
It is **not** UNDERPOWERED, and it is **not** free of a stated residual.

---

## §8. The stopping rule

**Exactly four fills, in one 72-hour window opening at the commit of this file.**

- At most **one re-attempt per cell**, permitted **only** when the cell was
  voided by a mechanical precondition (P2, P4, P6) — each of which is checkable
  without looking at the fee value (P8).
- **Hard cap: 8 orders, $14.76 of stake-plus-fee.** After the cap, or after the
  window closes, the run is closed and reported **whichever way it came out**.
- **"One more fill to be sure" is forbidden.** A second look is a **new
  registration**, not an amendment to this one.
- **The positions are held to settlement.** Not sold out. Two reasons, both
  registered before the run: settlement is not a trade, so no second fee is paid
  and H4 becomes testable for free; and a sell fill's price cannot be fixed in
  advance, so it could not be a registered cell. **If Joe sells any position for
  any reason, that sell fill is NOT part of this registration**, its fee is
  reported descriptively, and it may not enter any conjunction.

---

## §9. What would falsify this, and what happens then

### The result's destination, fixed now, before the result exists

- **Every branch**, including NEITHER and including PARTIAL, is written to
  `docs/measurements/2026-08-1X-fee-model-fill-calibration-result.md`, with the
  §S output in full.
- **A declared:** the result document, plus an ADR retiring the hedge in
  `core/fees.py`, **conditional on the permanent gate staying armed** (§Power
  conclusion 3). ADR 0021 is annotated as confirmed-unmoved, citing §0.2.
- **B declared:** the result document, plus an ADR, plus a **required re-run of
  the clean-shortfall measurement against the new fee** before any ADR 0021
  number is quoted again. ADR 0021 §2 is annotated as **suspended pending
  re-run** on the day the verdict lands.
- **NEITHER:** the result document, plus an annotation in `core/fees.py`'s
  docstring replacing *"temporary and self-resolving"* with what was actually
  observed, plus a new registration if a third model is to be pursued. **This
  branch has a destination, and it is the same destination as the others.**

**A pre-registration whose negative branch has no destination produces a negative
result that quietly never gets written.** Both negative branches above are named,
dated and addressed.

### The consequence Joe should see before he acts

**Total dollars at risk if every contract settles worthless:**

```
stake      F1  $0.23 - $0.30      fees, worst model, all four:  <= $0.39
           F2  $2.30 - $3.00
           F3  $2.40 - $3.20      MAXIMUM LOSS, four fills:      $7.38
           F4  $0.45 - $0.49      MAXIMUM LOSS at the §8 cap:   $14.76
           ---------------
           TOTAL $5.38 - $6.99
```

These are **real positions on real games**, not paper. All four can lose in full.
The maximum loss is stated because it is the number that should govern the
decision; no expected-value estimate is offered, because estimating it would
require a view on the games and this design has none.

If the mirror bands are used instead (§3), F1+F2 rise to at most $8.47 and F3 to
at most $17.60. **Prefer the cheap side.**

---

## §10. What this measurement cannot establish — drafted before the run

Drafted now, because caveats written afterwards are selected to be survivable.

- **It does not establish the fee model at every price.** Four cells, spanning
  three regions of `p(1−p)`: 12–16c, 23–30c, 45–49c. Nothing is measured at
  1–11c, 17–22c, 31–44c, 50c, or above 49c except by the symmetry of §3.
- **It does not establish the fee model at every size.** Three sizes: 1, 10, 20.
  Nothing at 2–9, 11–19, or above 20. Model A's per-order rounding is
  size-dependent by construction, so this is a real gap, not a formality.
- **It does not establish the fee to better than one cent at `N=1`** at prices
  outside the bands. §Power conclusion 2. One cent at `N=1` is 10.0 tenths, which
  exceeds the entire clean-shortfall distribution.
- **It does not establish the maker model at all.** Every registered cell is
  taker. `MAKER_COEFFICIENT = 0.0175` and `SPORTS_MAKER_MULTIPLIER = 0.015`
  remain untested, and ADR 0017's maker path still needs its own fills. The
  registered maker predictions in §1 exist so that an *accidental* maker fill is
  scored against something fixed — not so that the maker path is claimed.
- **It does not establish the model for one side rather than the other.** The
  fee is symmetric in `p`, so a NO at 76c and a YES at 24c are the same cell.
  This design cannot distinguish them and does not need to.
- **`SPORTS_MULTIPLIER` is a per-CATEGORY claim, and this tests only the
  categories actually filled.** If all four fills land in MLB game markets, the
  result is about MLB game markets. It says nothing about WNBA, NFL, or any
  non-sports category, and the write-up must name the series prefix of every
  fill. Pooling across categories is forbidden.
- **It does not establish that the fee field means what its name says.** P1/P3.
  The field name and units are unobserved at registration time, and this repo has
  a history of four wrong wire keys each of which returned a well-formed empty
  result that satisfied every test written about its contents.
- **`n = 4`.** Four orders, one account, one venue, one 72-hour window. Not a
  sample of anything. No interval appears in this design and none may be added
  to the result.
- **It cannot distinguish per-order from per-fill rounding.** P4 voids
  multi-fill orders rather than resolving them; that distinction needs a design
  that deliberately produces partial fills, which this is not.
- **It says nothing about whether an edge exists at Kalshi.** ADR 0021 §1's
  forbidden sentence is forbidden here too. Resolving the fee changes the *bar*;
  it does not create anything that clears it.

---

## §11. Assumed inputs, counted

- **A1 [ASSUMED].** Kalshi charges the entry fee at fill time, once per order,
  and the charged amount does not change afterwards. **Detector:** P7 re-reads
  F1's fee after F2 is placed.
- **A2 [ASSUMED].** The four candidate orders will be identifiable in the fills
  record — i.e. an order Joe places by hand in the app appears on
  `/portfolio/fills` for the same account the API key addresses. **Detector:**
  the count of fill records must equal the count of orders placed; a mismatch is
  a STOP THE LINE naming the harness.
- **A3 [ASSUMED].** A settlement-time charge, if one existed, would be visible on
  the account through the balance or the position record. **Detector:** §R5's
  paired guard.

**Count of assumed inputs: 3.**

---

## §S. Required output of the run, in this order

1. Preconditions P1–P8, each with its yes/no and its evidence.
2. The unit-resolution working for P3: the raw F1 value, the three
   interpretations, which survived, and the resolved unit.
3. Reachability guards R1–R5, printed **before** any verdict.
4. **The per-cell table**: cell, ticker, series prefix, side, observed price,
   contracts, taker/maker, `fee_observed`, `model_a`, `model_b`, match-A,
   match-B, VOID/NOT ATTEMPTED with reason. **Every cell appears, including
   voided ones, with its observed fee.**
5. The strict conjunction verdict (governing) and the ROBUST-only conjunction
   (diagnostic, labelled as such), side by side.
6. The coverage qualifier: FULL or PARTIAL, and which signs were present in `C`.
7. The in-app displayed fee for each order beside the API value, as a
   cross-check. A disagreement is a STOP THE LINE about the instrument, not
   about the model.
8. The linearity bonus reading (F1 vs F2), or the statement that it was
   unavailable because the two fill prices differed.
9. H4's settlement result, with R5's paired guard printed beside it.
10. Total stake, total fees paid, and total realised P&L on the four positions —
    reported for honesty, and **explicitly not evidence of anything** about
    edge, at `n = 4`.
11. The §Power residual restated against the actual observed prices: the size of
    `class(A)` or `class(B)` at the prices that actually occurred, which may be
    smaller than the registered worst case and **may not be reported as
    "resolved"** on that basis.

---

## §V. Verdict at registration

> **READY.** Every section is fixed. No section was left open on the grounds
> that we would see what the data looks like.
>
> Four cells, four bands, four contract counts, all predictions computed and
> written above before any fill exists. The sign flip is present (F3), robust
> across its whole band at every tenth, and its loss is detectable by two named
> mechanisms. The declared, refuted and neither outcomes are each reachable on
> the legal price grid. The stopping rule is a count and a window. The negative
> branch has a destination. The residual is stated in §Power conclusion 2 rather
> than left to be discovered.
>
> **Maximum loss: $7.38 for the four fills, $14.76 at the §8 cap.**

---

## Registration record

| Field | Value |
|---|---|
| Registered | 2026-08-10 (UTC) |
| Registered by | `pre-registrar`, on behalf of Joe |
| Fills at registration time | **0** — none exist on this account |
| Cells | 4 |
| Sizes | 1, 10, 20 |
| Bands | 23–30c, 23–30c, 12–16c, 45–49c (mirrors permitted, §3) |
| Sign coverage | 3 cells `A>B`, 1 cell `B>A` |
| Max stake | $6.99 |
| Max loss incl. fees | $7.38 (four fills) / $14.76 (§8 cap) |
| Deploy required | **None** |
| Code that places orders | **None.** `ORDERS_ARE_DRY_RUNS` stays `True`; ADR 0018 untouched |
| Amendments | none |

---
---

# Amendment A — the pre-revision baseline, registered before any fill exists

**Written 2026-08-10 (UTC), appended. Still zero fills on this account.**

**The body above is untouched.** No inline marker has been added to it anywhere,
following the precedent of Amendment A in
[`2026-08-10-preregistration-clean-shortfall-distribution.md`](2026-08-10-preregistration-clean-shortfall-distribution.md).
Where this amendment contradicts the body, **this amendment governs**, and §A10
lists every place that happens.

## §A0. What this amendment does and does not do

**It does not move a band. It does not drop a cell. It does not change the
decision rule, the stopping rule, or the cost.** The four fills of §1 are placed
exactly as registered.

It exists because a **durable fee record already exists on this account** and was
found after the body was committed. Registering it now converts the post-fill
reading from *"which of two models?"* into the cleaner and more answerable
*"same schedule, or changed schedule?"* — and it does so **before** any fill
exists, which is the only time that conversion is honest.

**The prior has moved decisively and that is disclosed rather than smoothed
over.** §A2 below is the most contaminating section in this document and it is
placed early for that reason. A declaration of Model A after this amendment is a
**reproduction plus a revision check**, not a discovery, and §A10 makes that
labelling mandatory.

## §A1. The discovery, reproduced independently before it was written down

`GET /portfolio/settlements` returns **55 settled positions**, settled
**2025-11-27 → 2026-05-10**, each carrying a `fee_cost` field. Raw capture at
`data/captures/portfolio_settlements.json` — **gitignored, and it must stay
gitignored**: it is Joe's real position history and this repo publishes on push.

**[MEASURED — re-derived for this amendment from the raw capture, with
independent code, not taken from the brief that reported it]**

```
records                                          55
  KXMVE combo positions                          43   NOT observations of the model under test (§A1.2)
  single-game / single-market positions          12
    ...with a derivable price (count > 0)        11
    ...with count == 0                            1   KXNFLSPREAD-25DEC25DENKC-DEN13, fee $0.000000
denominator for any priced statement             54   = 55 - 1
```

The `n = 0` record is **named rather than silently dropped**, so no arithmetic
discrepancy between 55 and 54 is left for a reader to rediscover. It carries a
zero fee and no price can be derived from it, so it enters nothing.

Price is derived as `total_cost_dollars / count_fp` on whichever side is
non-zero. This is an **average fill price over the fills that built the
position**, which is a real limitation and is stated in §A9.

### §A1.1 Model A matches all 11, to the cent

**[MEASURED]** `fee_cost` against `ceil_to_cent(0.07 × n × p × (1−p))`:

| Ticker | side | `n` | price | `fee_cost` | Model A | Model B | match |
|---|---|---:|---:|---:|---:|---:|:--:|
| `KXSB-26-SF` | yes | 609 | 4.00c | $1.64 | **$1.64** | $0.00 | **A** |
| `KXNFLGAME-25NOV30MINSEA-MIN` | yes | 59 | **16.00c** | $0.56 | **$0.56** | **$0.59** | **A** |
| `KXNFLGAME-25NOV27CINBAL-CIN` | yes | 70 | **27.00c** | $0.97 | **$0.97** | $0.70 | **A** |
| `KXNFLSPREAD-25NOV30LVLAC-LAC17` | yes | 22 | 43.00c | $0.38 | **$0.38** | $0.22 | **A** |
| `KXNFLSPREAD-25NOV30DENWAS-DEN6` | yes | 39 | **49.00c** | $0.69 | **$0.69** | $0.39 | **A** |
| `KXNFLSPREAD-25DEC01NYGNE-NE6` | yes | 17 | 54.00c | $0.30 | **$0.30** | $0.17 | **A** |
| `KXNFLGAME-25NOV30ARITB-TB` | yes | 30 | 60.00c | $0.51 | **$0.51** | $0.30 | **A** |
| `KXNFLGAME-25NOV27GBDET-GB` | yes | 6 | 63.00c | $0.10 | **$0.10** | $0.06 | **A** |
| `KXNBATOTAL-25DEC05DALOKC-219` | yes | 20 | 73.00c | $0.28 | **$0.28** | $0.20 | **A** |
| `KXNFLSPREAD-25NOV30ARITB-TB3` | no | 20 | 96.80c | $0.05 | **$0.05** | $0.00 | **A** |
| `KXNBASPREAD-25DEC03MIADAL-MIA7` | no | 20 | 98.00c | $0.03 | **$0.03** | $0.00 | **A** |

**11 of 11.** **[MEASURED]** the §Power 968-member plausible-model family
collapses on these 11 records to **exactly one survivor: `(0.0700, ceil,
per-order)` — Model A itself.** The identified coefficient interval is

```
c in (0.069771, 0.070129]      contains 0.0700
                               EXCLUDES 0.06   (Model B's multiplier)
                               EXCLUDES 0.0175 (Model A's maker coefficient)
```

**The F3 direction is already observed, and Model A won it.**
`KXNFLGAME-25NOV30MINSEA-MIN`, `n = 59` at **16.0c**, is a `B > A`
configuration — A predicts $0.56, B predicts $0.59 — and Kalshi charged
**$0.56**. So the sign flip registered in §1 is not, on the pre-revision record,
an open question. **§R3 stands as written** (the flip is still what makes the
*post*-revision reading strong), but F3's standing changes from *discovery* to
*revision detector*, and §A10 binds the write-up to say so.

**Three of the four registered bands have a pre-revision price analogue**, all
matching Model A exactly: **27.0c** (F1 and F2's band, at `n = 70`), **16.0c**
(F3's band, at `n = 59`), **49.0c** (F4's band, at `n = 39`). These are
**price** analogues at very different sizes, **not** cell analogues — no
registered `(price, size)` cell has a pre-revision twin, and §A6 explains why the
size difference is the whole point.

### §A1.2 The 43 combos are not observations of the model under test

Registered as an exclusion **before** the fills, with a reason independent of any
fill outcome:

**[MEASURED]** **32 of the 55 records carry a `fee_cost` quoted finer than a
whole cent, and all 32 are combos.** No member of the 968-family reproduces more
than **11 of the 43**. `KXMVE` is a different product with a different fee
treatment, and it is ADR 0012's territory, not this registration's.

**The earlier claim that the combo and single-game subsets "agree" is
UNSUPPORTED and is withdrawn here.** **[MEASURED]** the maximum implied
coefficient is **0.0747 across all 43 combos** and **0.0807 across the 11
single-game records** — **the entire upper tail is single-game**, so the two
subsets do not span the same range and cannot be said to agree. The 43 combos
enter no statistic in this registration.

## §A2. The registered baseline, and the reading it converts the fills into

> **REGISTERED BASELINE, fixed 2026-08-10 before any fill exists:** on the 11
> single-game settled positions of §A1.1, settled **2025-11-27 → 2026-02-09**,
> `fee_cost` equals `ceil_to_cent(0.07 × n × p × (1−p))` on **11 of 11**, and
> that model is the **unique survivor** of the 968-member family.

**Every one of those 11 settled between 2025-11-27 and 2026-02-09, and all of
them predate the July 2026 revision** that `core/fees.py` names as the reason its
two sources disagree. So the baseline answers *"what was the schedule before the
revision"* and cannot answer *"what is it now"*.

> **The post-fill reading, fixed now:**
> **SAME SCHEDULE** — the four fills match Model A. The July 2026 revision did
> not change the taker schedule at the tested cells.
> **CHANGED SCHEDULE** — the four fills do not match Model A. Model A was true
> before the revision and is not true now, and §9's Model-B and NEITHER
> consequences apply in full.
>
> This is a **two-outcome reading layered on top of §7, not a replacement for
> it.** §7's decision rule is unchanged and still governs; §A10 lists what the
> write-up must additionally say.

### §A2.1 The confound this amendment introduces, named before the fills

**The baseline is NFL, NBA and one Super Bowl future. The four fills will be MLB
or WNBA.** **[MEASURED]** the 11 single-game records are `KXNFLSPREAD` (5),
`KXNFLGAME` (4), `KXSB` (1), `KXNBATOTAL` (1), `KXNBASPREAD` (1). In August 2026
the in-season leagues are MLB and WNBA, so a category-matched comparison is **not
reachable** and no attempt to reach it is registered.

> **Therefore a CHANGED SCHEDULE verdict is confounded with a CATEGORY
> DIFFERENCE, and this design cannot separate them.** The write-up must state
> that in those words. Separating them requires NFL or NBA fills in the current
> season, which is a different registration.

**The confound runs the other way on the SAME SCHEDULE branch, and that is a
bonus rather than a caveat.** Model A has **one coefficient for all categories**;
Model B has a **per-category multiplier**. So Model A holding on NFL/NBA
*and* on MLB/WNBA is evidence for the single-coefficient structure that Model A
asserts and Model B denies. That reading is registered here so it may be used;
it may **not** be upgraded into a claim about categories neither set touches.

## §A3. Withdrawal of §Power conclusion 3

**§Power conclusion 3 of the body is WITHDRAWN in full.** It argued that the
untested price range is covered for free by the permanent
`fee_predicted != fee_actual` gate, which "accumulates coverage across every
price and size the tool ever trades".

**It accumulates none, and the reason is that the table is never written.**
**[COMPUTED FROM CODE, verified for this amendment]**
`backend/gate.py:636 _fee_model_verified` reads `FROM fills` (`:642`), and a
repo-wide search for `INTO fills` returns **only three matches, all in
`tests/`** (`test_execution.py:1446`, `test_quote_refresh.py:464`,
`test_runner.py:495`). **No production code writes that table.** So `total == 0`
on every evaluation, the condition is pinned at
`met=False, "no fills yet — the fee model is still an unresolved hedge"`, and
**the MISMATCH branch is unreachable in production.**

Two consequences, both binding:

1. **The residual named in §Power conclusion 2 — up to one cent at `N=1` at
   untested prices — is not covered by anything.** It stands unmitigated. The
   body's sentence *"The four fills are its first four observations"* is false
   as written: they are not observations of anything the gate can see.
2. **Retiring the hedge may NOT be made conditional on "the permanent gate
   staying armed"**, as §9's Model-A row and §Power conclusion 3 both say,
   because there is no armed gate to stay armed. Wiring `INTO fills` is a
   **separate task**, it is a precondition of that conditional, and **the four
   fills do not depend on it.** §A10 restates §9's Model-A consequence without
   the false conditional.

## §A4. §6 becomes time-critical, and it has a laptop-only step

Two operational facts that were not in the body:

- **`/portfolio/fills` has a retention window.** **[MEASURED — parallel capture
  lane, cited at inference strength because this amendment did not re-run it]**
  the account's own historical fills are **gone** across eight query shapes, with
  an upper bound of roughly **three months**. The 55 settlements survive; the
  fills that built them do not. **So the fill-time fee must be captured within
  days of placement, not weeks.**
- **`scripts/capture_fills_fixture.py` is not in the deployed image.**
  **[COMPUTED FROM CODE — `.dockerignore:59-61` excludes `scripts/*` except
  `run_loop.py` and `migrate_db.py`]** so capture is a **laptop-only** step, and
  Joe is phone-only. **The capture must be scheduled with an agent session, and
  the four fills should not be placed until one is available within days.**

This does not change the §8 window, which opens at the commit of the body. It
adds a second clock, and the second clock is the binding one.

## §A5. R5's paired guard gains a durable channel

**§R5 stands as written and is strengthened, not replaced.**

`/portfolio/settlements` reports `fee_cost` on positions whose fills have already
expired, so **it is the surviving record of these four positions**. Registered
addition to §6 and to §S:

> **The four positions' settlement `fee_cost` must be captured after they
> settle**, in addition to the fill-time fee, and both must be recorded in §S
> item 4. If the fill-time capture is missed for any cell, the settlement
> `fee_cost` is the registered substitute for that cell — **and the substitution
> must be labelled**, because a settlement `fee_cost` is a position-level
> aggregate and §A9 bounds what it can carry.

## §A6. The `N = 1` regime is entirely unobserved, and it is the regime the tool runs on

**[MEASURED]** across the whole 55-record sample the smallest position is
**`n = 6`**, and the smallest raw pre-rounding fee at `c = 0.07` is
**$0.02744**. **[COMPUTED]** the largest possible raw fee at `N = 1` at **any**
price is `0.07 × 0.25 = $0.01750`.

```
observed raw fees          >= $0.02744
possible raw fees at N=1   <= $0.01750
                              ZERO OVERLAP
```

Not one settled record is anywhere near the one-contract regime, and the
per-order ceiling is a **larger share of the total** the smaller the order —
which is exactly where the two models diverge.

`core/sizing.py:156` prices every sizing decision at `contracts=1`, and every
statistic in ADR 0021 is computed at `E1`.

> **F1 and F4 are the only `N = 1` observations anywhere in this project, before
> or after.** They are the load-bearing pair. **If the fill set is ever reduced
> for any reason, F1 and F4 are the two that must survive.**

This is registered as a fact about the design, not as a licence to reduce it:
§A0 stands and all four fills are placed.

## §A7. The 52.00% bar rests on the rounding, not on the coefficient

Stated here because the settlements support the bar through one mechanism and
never observe the other.

**[COMPUTED]** at 50c and `N = 1`, Model A's raw fee is `0.07 × 1 × 0.25 =
$0.0175`, which gives a break-even of **51.75%** — the number `CLAUDE.md` says
the published coefficient would give. The per-order **ceiling** lifts it to
**$0.02**, and that gives **52.00%**.

> **The entire 0.25-point gap between 51.75% and 52.00% is the per-order `ceil`
> at `N = 1`.** The coefficient contributes none of it.

The 11 settled records pin the coefficient to `(0.069771, 0.070129]` **and**
confirm `ceil` over `floor`, `half_up` and `half_even` — but they do it at
`n >= 6`, where the ceiling is a rounding detail. **At `N = 1` the ceiling is the
whole bar.** So the settlements support 52.00% through the rounding rule while
never observing the regime in which that rule is decisive, and **F1 and F4 are
the only things that can.**

## §A8. H4 gains a separation the body could not offer

**[MEASURED]** on all 11 single-game records, `fee_cost` equals the **entry**-fee
formula exactly. Two readings survive and **this sample cannot separate them**:

- **(i)** `/portfolio/settlements` reports only the entry fee, and **H4 is
  untested** by the settlements; or
- **(ii)** it reports total fees over the position's life and **H4 is
  confirmed** — settlement charged nothing extra.

Both are consistent with 11 of 11, so neither may be asserted from the
settlements alone. **The four fills separate them**, because for the same four
positions this design will hold **both** the fill-time fee and the settlement
`fee_cost`:

> **Registered, before the fills:** if `settlement fee_cost == fill-time fee` on
> a cell, then reading (i) and reading (ii) coincide only if settlement charged
> zero — so **H4 is declared for that cell**. If
> `settlement fee_cost > fill-time fee`, **H4 is refuted** and the difference is
> the settlement charge. If `settlement fee_cost < fill-time fee`, that is
> **neither**, and it is a **STOP THE LINE** naming the record rather than the
> model, because a settlement cannot refund an entry fee.

§R5's paired guard applies unchanged: the entry fees must be visible on the same
records, or the query is measuring nothing.

## §A9. What Amendment A does not establish

- **It does not establish the model after the July 2026 revision.** Every one of
  the 11 records settled between 2025-11-27 and 2026-02-09. That is the whole
  reason the four fills are still placed.
- **It does not establish the model at `N = 1`.** §A6. Zero overlap, in the
  regime that decides everything.
- **It does not establish the model for MLB or WNBA.** §A2.1. The baseline is
  NFL, NBA and one future.
- **It does not establish a per-fill price.** Every price in §A1.1 is
  `total_cost / count` — an **average over the fills that built the position**.
  Ten of the eleven land on an exact whole cent, which is consistent with a
  single fill price but does not prove one. A position built at two prices whose
  average is a whole cent would be indistinguishable here, and its true fee could
  differ from the prediction. **This is why the four fills are single orders with
  the one-fill-row precondition (P4), and why the settlements are not a
  substitute for them.**
- **It does not establish anything about combos.** §A1.2. The 43 `KXMVE` records
  are excluded, the family reproduces at most 11 of 43, and the "subsets agree"
  claim is withdrawn.
- **It does not establish the maker model.** The interval
  `(0.069771, 0.070129]` **excludes 0.0175**, which says these were taker fees —
  not that the maker coefficient is wrong.
- **`n = 11` is eleven positions on one account in one window.** It is not a
  sample of Kalshi's schedule and carries no interval.

## §A10. What now binds

**Unchanged, and confirmed:** the four cells, their bands, their sizes, their
registered predictions, §7's decision rule, §8's stopping rule, §R1–§R5, and the
cost. **F1 23–30c × 1, F2 23–30c × 10, F3 12–16c × 20, F4 45–49c × 1. Max stake
$6.99. Max loss $7.38.**

**Amended:**

| Body location | Amendment |
|---|---|
| §Power conclusion 3 | **WITHDRAWN in full** (§A3). The gate accumulates no coverage; nothing in production writes `fills`. |
| §9, Model-A row, *"conditional on the permanent gate staying armed"* | **Struck.** The condition is unsatisfiable today. Replaced by: retiring the hedge is conditional on **wiring the `fills` writer first**, which is a separate task the four fills do not depend on. |
| §1 H1/H2, standing | The prior has moved. Model A is the **unique** survivor of 968 on the pre-revision record. §7's rule is unchanged, but a Model-A declaration **must be labelled `REPRODUCTION + REVISION CHECK — NOT A DISCOVERY`** in the verdict line and in every table it appears in. |
| §1 F3, standing | From *discovery* to **revision detector**. The `B > A` direction is already observed pre-revision (`MINSEA`, 16.0c, `n = 59`, A won). The write-up must say so beside any F3 result. |
| §6 | Two clocks. The fill-retention window (~3 months, upper bound) is the binding one, and capture is **laptop-only** (`.dockerignore:59-61`). |
| §S item 4 | Add a `settlement fee_cost` column beside `fee_observed`, per cell. |
| §S, new item 12 | Print the §A2 SAME/CHANGED reading, the §A2.1 category confound in the required words, and the §A8 H4 separation per cell. |
| §10 | Add: *this does not establish the model for NFL, NBA or `KXMVE` combos*, and *the baseline it is compared against is a different set of categories*. |
| §11 | **A4 [ASSUMED], new:** that a `settled_time` between 2025-11-27 and 2026-02-09 places a record before the July 2026 revision. **Detector: none available.** Count of assumed inputs rises from 3 to **4**. |

**Verdict at registration, after Amendment A: READY, unchanged.** The design
answers a sharper question than the body registered, at the same cost, because
the comparator now exists. Nothing was reached for: every number in §A1 was
re-derived from the raw capture with independent code before it was written here,
and every one of them predates the first fill.
