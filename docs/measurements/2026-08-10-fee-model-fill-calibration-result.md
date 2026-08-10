# Result — the fee-model fill calibration

**Run 2026-08-10. Registered at
[`2026-08-10-preregistration-fee-model-fill-calibration.md`](2026-08-10-preregistration-fee-model-fill-calibration.md)
(body + Amendment A), committed before any fill existed.**

- Placed by hand by Joe in the Kalshi app. `ORDERS_ARE_DRY_RUNS` stayed `True`;
  no code in this repo placed anything. ADR 0018 untouched.
- Raw data: `data/captures/portfolio_fills.json`,
  `data/captures/portfolio_settlements.json`. **Both gitignored** — real
  position history. No `order_id`, `fill_id`, `trade_id` or
  `subaccount_number` appears in this document.
- Every number below was re-derived from those captures with independent code
  for this write-up.

> # VERDICT: **H3− at all four registered cells.**
>
> Every observed fee is **below `min(model_a, model_b)`**. §9's H3− consequence
> applies **verbatim and in full**:
>
> **The `max()` hedge in `core/fees.py` stays unchanged. A new registration
> with new fills is required before any model change.**
>
> No change is made to `calculate_fee`. No edit is made to `CLAUDE.md`'s 52.00%
> bar. No amendment is made to ADR 0021.

> **And the finding that is solid, stated once, plainly:**
> **Kalshi charged sub-cent fees on all six fills, in two series, on
> 2026-08-10.** `core/fees.py`'s cent-granular contract is **wrong for the
> current schedule**. That is the result. Everything about *what the new
> schedule is* is weaker, and the rest of this document is mostly about how much
> weaker.

---

## §S1. Preconditions

| | Status | Evidence |
|---|---|---|
| **P1** — a fee-shaped field exists on the fill record | **PASSED** | `fee_cost`, coverage 6 of 6. **Not named `fee`** — `rest.py`'s inherited name was wrong, exactly as its own docstring warned. |
| **P2** — the balance fallback | **NOT RUN, and now unrunnable.** P1 passed so it was not needed; it cannot be run retrospectively. See §S4's residual note. |
| **P3** — the unit is identified from F1 alone | **PASSED** | §S2. |
| **P4** — one fill row per order | **PASSED** | 6 fills, **6 distinct order identifiers**. No order fragmented. |
| **P5** — the fill is a taker fill | **PASSED** | `is_taker = true` on 6 of 6. The maker branch of §3 was not exercised. |
| **P6** — the observed price is inside the registered band | **PASSED** on all four | F1 27c ∈ [23,30]; F2 27c ∈ [23,30]; F3 15c ∈ [12,16]; F4 48c ∈ [45,49]. |
| **P7** — F1's recorded fee unchanged after F2 | **UNTESTED.** | It required reading F1's fee **before** F2 existed. The capture is a single snapshot taken after all six fills. Retroactive aggregation therefore remains **undetected, not excluded.** |
| **P8** — every void/extra published with its fee | **HONOURED** | §S4 lists all six, including the two unregistered ones. |

## §S2. Unit resolution (P3), mechanically, from F1 alone

F1's raw value is `"0.006900"`. The registered rule interprets it three ways and
retains those implying a fee in `[$0.001, $0.10]`:

```
as dollars      -> $0.006900   RETAINED
as cents        -> $0.000069   rejected (below $0.001)
as centi-cents  -> $0.0000069  rejected
```

**Exactly one survives. The unit is dollars**, for all four cells.

## §S3. Reachability guards, printed before any verdict

| | Result |
|---|---|
| **R1** — every declared outcome attainable on the grid | **HELD.** H3− was attained, which is itself the proof. |
| **R2** — the falsifier of each declaration reachable | **HELD.** Both models were falsified at every cell. |
| **R3** — the sign flip present, its loss detectable | **HELD, and the flip was achieved.** F3 was a `B > A` cell and taker; F1/F2/F4 were `A > B` and taker. Neither loss mechanism (maker fill, NOT ATTEMPTED) fired. |
| **R4** — no cell can saturate | **HELD.** No cell returned a value consistent with both models; none could. |
| **R5** — H4's paired guard | **PENDING.** The four positions have not settled at the time of writing. §S9. |

## §S4. The per-cell table — all six fills, including the two unregistered

Predictions are the ones registered in §1, evaluated at the **observed** price
and size. All six fills are taker.

| | series | market | `C` | `P` | **observed fee** | Model A | Model B | `min(A,B)` | shortfall vs `min` | verdict |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| *(unregistered)* | KXMLBGAME | KCLAD-KC | **0.27** | 0.2700 | **$0.001900** | — | — | — | — | **UNREGISTERED** |
| **F1** | KXMLBGAME | KCLAD-KC | 1 | 0.2700 | **$0.006900** | $0.02 | $0.01 | $0.01 | $0.003100 | **H3−** |
| **F2** | KXMLBGAME | KCLAD-KC | 10 | 0.2700 | **$0.069000** | $0.14 | $0.10 | $0.10 | $0.031000 | **H3−** |
| **F3** | **KXATPDOUBLES** | CERETC | 20 | 0.1500 | **$0.178500** | $0.18 | $0.20 | $0.18 | **$0.001500** | **H3−** |
| **F4** | KXMLBGAME | BALMIN-MIN | 1 | 0.4800 | **$0.008800** | $0.02 | $0.01 | $0.01 | $0.001200 | **H3−** |
| *(unregistered)* | KXMLBGAME | TEXLAA-LAA | 1 | 0.4800 | **$0.008800** | $0.02 | $0.01 | $0.01 | $0.001200 | **UNREGISTERED** |

The fractional fill's `C = 0.27` makes both models **undefined** rather than
refuted — neither is specified at a non-integer contract count. Its fee is
published under P8 and it enters no conjunction.

**The residual on every fee above is ≤ $0.0001**, because P2 was never run: what
is observed is the **reported** `fee_cost` field, not an independently measured
charge. Every statement in this document is about the reported field.

**`settlement fee_cost` column: PENDING** (Amendment A §A5). Predictions are
registered in §S9 before the data exists.

## §S5. Strict conjunction and the ROBUST-only diagnostic

```
STRICT (all four cells, governing) :  Model A refuted, Model B refuted  -> H3-
ROBUST-only (F1, F2, F3)           :  Model A refuted, Model B refuted  -> H3-
```

**They agree.** No divergence to report, and the strict reading governs
regardless.

## §S6. Coverage qualifier

**FULL sign coverage was achieved.** `C` contained one `B > A` taker cell (F3)
and three `A > B` taker cells. The qualifier attaches to declarations and no
model was declared, but the design delivered the coverage it registered.

## §S7. In-app displayed fee, as a cross-check

**NOT RECORDED.** §S item 7 required the in-app fee beside the API value for
each order; it was not captured at placement and cannot be recovered. **This is
a gap in the run, not a finding.** It means the reported `fee_cost` has **no
independent corroboration from a second channel** — the same gap P2's absence
creates, from the other side.

## §S8. The registered linearity bonus reading — it returned, and it is overturned

F1 and F2 filled in the **same market at the same price**, so the bonus reading
registered in §1 is available:

```
fee(F2) = $0.069000        10 x fee(F1) = $0.069000        EXACTLY EQUAL
```

The registered rule says: *"`fee(F2) == 10 × fee(F1)` is therefore evidence for
per-contract scope, and `fee(F2) < 10 × fee(F1)` for per-order."* **So the bonus
reading returned PER-CONTRACT, and it is wrong.**

**It is overturned coefficient-free by F3.** Under per-contract scope at the
observed $0.0001 granularity, an order's fee must be `C ×` (a multiple of
$0.0001), i.e. a multiple of `20 × $0.0001 = $0.002` for F3.
**`$0.1785 / $0.002 = 89.25`, not an integer.** Per-contract rounding at
$0.0001 is impossible at F3, for **any** coefficient.

> **This is a defect in the registration, recorded rather than dropped.** The
> bonus reading was derived against a **cent** grid, where Model A's ceiling
> makes per-order scope visibly non-linear. On a **$0.0001** grid the ceiling is
> almost always a sub-0.01% correction, so linearity is nearly uninformative and
> the test returns per-contract by default. **A diagnostic whose discriminating
> power depended on the granularity it was meant to help identify.** It should
> have been registered conditionally on the granularity, and it was not.

**What is refuted, with the quantifier stated exactly:** *per-contract rounding
**at the observed $0.0001 granularity*** is refuted. A per-contract computation
rounded at some finer, unobservable granularity and then summed **cannot be
distinguished from per-order at all** and is not refuted. The `C = 0.27` fill
makes a literal per-contract charge structurally odd in any case.

## §S9. H4 — settlement, and the predictions registered now, before the data

The four positions had not settled at the time of writing. Amendment A §A5
requires capturing their settlement `fee_cost`. **Zero cost, ~24h.**

**Registered before the data exists:**

| position | Σ fill fees | reading 1/2 | reading 3 (cent display) | old cent model | separates all three? |
|---|---:|---:|---:|---:|:--:|
| `…BALMIN-MIN` (C = 1) | $0.0088 | $0.0088 | $0.01 | $0.02 | **yes** |
| `…TEXLAA-LAA` (C = 1) | $0.0088 | $0.0088 | $0.01 | $0.02 | **yes** |
| `…KCLAD-KC` (3 orders, C = 11.27) | $0.0778 | $0.0778 | $0.08 | $0.16 | **yes** |
| `…CERETC` (ATP, C = 20) | $0.1785 | $0.1785 | **$0.18** | **$0.18** | **NO** |

> **The ATP position must not be read.** Reading 3 and the old cent model both
> predict $0.18 there, so it cannot separate them. Fixed here so it cannot be
> quoted afterwards as though it could.

§R5's paired guard applies unchanged when the data arrives.

## §S10. Stake, fees, P&L

```
stake        F1  $0.27      unregistered fractional  $0.0729
             F2  $2.70      unregistered sixth       $0.48
             F3  $3.00
             F4  $0.48      total stake, six fills   $7.00
fees paid    $0.0019 + $0.0069 + $0.0690 + $0.1785 + $0.0088 + $0.0088 = $0.2739
```

Registered maximum loss was **$7.38** for four fills. **Actual exposure $7.27**,
across six. P&L **pending settlement**, and — per §S item 10 — it is
**explicitly not evidence of anything** about edge at `n = 4`, or `n = 6`.

## §S11. The §Power residual, restated against the observed prices

**It cannot be restated, and the reason is the finding.** §Power partitioned a
968-member family all of whose members round to the **cent**. Every member is
refuted at every cell. **The registered power arithmetic does not describe this
result and no surviving-class size may be quoted from it.**

Amendment A §A3's withdrawal stands and now bites: the one-cent-at-`N=1`
residual it identified is not covered by the permanent gate, because
`backend/gate.py:642` reads `FROM fills` and nothing in production writes that
table. **`_fee_model_verified` is still pinned at `met=False, "no fills yet"`
even now that six fills exist**, because the fills live at Kalshi and never
enter the local table.

## §S12. The SAME/CHANGED reading, the confound, and H4 (Amendment A §A10)

**CHANGED SCHEDULE**, on the granularity axis. Amendment A §A2's baseline —
Model A's cent-rounded form, 11 of 11 pre-revision settlements — does not
reproduce a single one of the six fills.

**The category confound §A2.1 registered must be stated in its required words,
and it applies:** a CHANGED SCHEDULE verdict is confounded with a CATEGORY
DIFFERENCE, and this design cannot separate them. The baseline is NFL, NBA and
one future; the fills are MLB and ATP tennis.

**But §A2.1 did not anticipate the thing that actually happened, and it splits
the confound in a way the amendment could not have known.** F3 landed in
**KXATPDOUBLES**, not MLB, because §3's un-gameable market-choice rule — *scan
the sports list top to bottom, take the first market whose ask is in band* —
found tennis first at 12–16c. **F3 and the MLB cells filled 63.9 seconds
apart.** So the difference between them **cannot** be a schedule change over
time; it is cross-sectional. §"The settlement contradiction" below uses this.

> **A registration defect, named:** the registration scoped the *declaration* to
> "the categories actually filled" but **never required the four fills to share
> a category**, and never registered what to do if they did not. The
> market-choice rule was working as designed when it produced a tennis market.
> Nothing here is void — the cells are exactly as registered — but the
> cross-series comparison in §"What the fills establish" item 4 is an
> **unregistered** analysis and is labelled as such wherever it appears.

---

## PROTOCOL BREACH — six fills against a registration of four

**Recorded in its own section because §8 is explicit and was not followed.**

§8: *"Exactly four fills… 'One more fill to be sure' is forbidden. A second look
is a new registration, not an amendment to this one."*

**Six fills were placed. Two were not registered:**

| | created (UTC) | gap | what it was |
|---|---|---:|---|
| unregistered, fractional | 13:38:01.00 | — | `C = 0.27` at `P = 0.27`. No registered cell has a fractional size. |
| F1 | 13:42:14.20 | +253.2s | |
| F2 | 13:45:51.02 | +216.8s | |
| F3 | 13:48:33.28 | +162.3s | |
| F4 | 13:49:37.20 | +63.9s | |
| **unregistered, sixth** | **13:52:17.28** | **+160.1s** | replicates F4's cell (`C = 1`, `P = 0.48`) in a second MLB market. |

**The sixth was placed after the record had been looked at.** The coordinating
lane reports querying the record at **13:50:13**, which is after F4
(13:49:37) and before the sixth (13:52:17); the capture in hand is timestamped
**13:52:51**, 34 seconds after the sixth, and contains all six. **The 13:50:13
query time is reported by that lane and could not be verified from the
artefacts available here**; the fill creation times above are read directly from
the capture and are exact.

**Both extras were accidents of the app's order ticket rather than model-driven
choices, and that does not excuse them.** The rule §8 states exists precisely
because "it was an accident" is unfalsifiable after the fact, and the discipline
is worth more than the two fills.

**What the breach did and did not buy — measured, not asserted:**

```
k_MLB from all 5 MLB fills             (0.034957, 0.035008]
k_MLB from the 3 REGISTERED MLB cells  (0.034957, 0.035008]     IDENTICAL
```

**The unregistered fills changed no interval and no verdict.** The binding
constraint is F2, which is registered. The sixth fill replicates F4's cell in a
different market and introduces no new `(price, size)` cell at all.

> **So the "6 of 6 fit" came from placing another order, not from learning
> anything.** Every number in this document that matters is unchanged if both
> unregistered fills are deleted, and the honest count of registered
> observations is **four**.

---

## What the fills establish

Ordered by strength. **Nothing here is re-fitted into `core/fees.py` and nothing
here is a model this project adopts** — §2 of the registration governs: *the
observed fees are a hypothesis generator, labelled as such.*

### 1. Sub-cent fees exist on this account, now. **[SOLID]**

All six fills, two series, one day. `$0.0019`, `$0.0069`, `$0.0690`, `$0.1785`,
`$0.0088`, `$0.0088` — not one is a whole cent. **`core/fees.py`'s cent-granular
contract is wrong for the current schedule**, and `FEE_MATCH_TOLERANCE_DOLLARS`'s
comment — *"Kalshi charges whole cents"* — is now false as written.

An **independent mechanism** corroborates it and is not a fee measurement at
all: the account shows a **fractional fill, `count_fp = 0.27`**. Cent-granular
fees are arithmetically incompatible with fractional contract counts, so the
granularity change has a reason that does not depend on any fee model.

### 2. What F3 refutes is **only the cent ceiling**, not Model A's coefficient. **[SOLID]**

**This distinction is load-bearing and "Model A is refuted" must not be written
bare.**

```
F3:  0.07 x 20 x 0.15 x 0.85  =  0.1785000       charged  $0.1785
```

**Exact.** At F3, Model A's coefficient is confirmed to seven decimals and its
**cent ceiling alone** is what fails — Model A would have charged `ceil($0.1785)
= $0.18`, and the entire shortfall is the $0.0015 of ceiling.

**On the three MLB cells Model A is refuted in both coefficient and rounding.**
The two are different failures and must be reported as two.

### 3. The reported `fee_cost` is `ceil` to $0.0001. **[SOLID, about the reported field]**

A census over **granularity × rounding**, with the coefficient **left free per
series** — 5 granularities `{$1, $0.10, $0.01, $0.001, $0.0001}` × 4 roundings
`{ceil, floor, half-up, half-even}` = **20 cells**:

```
UNIQUE SURVIVOR:  (granularity = $0.0001, rounding = ceil)
```

**How the 20 cells actually die, stated so the census is not oversold.**
Sixteen die on **representability alone**: `$0.0019` is not a multiple of
$0.001, so every granularity coarser than $0.0001 is dead before any coefficient
is considered. The census is therefore **one representability observation plus a
four-way rounding test**, and the rounding test is decided **entirely by the
MLB cells** — the ATP cell has one fill and one free parameter, so it admits
`floor`, `half-up` and `half-even` too and contributes nothing here.

**It is a statement about the reported field, not about the charge.** P2 was
never run and is now unrunnable (§S1), so the residual between "what Kalshi
charged" and "what `fee_cost` reports" is **≤ $0.0001** and unmeasured.

### 4. Scope: per-contract rounding at $0.0001 is refuted, coefficient-free. **[SOLID, with an exact quantifier]**

§S8. `$0.1785` is not a multiple of `20 × $0.0001`. What survives is per-order,
**or** per-contract at a finer unobservable granularity — and those two are
indistinguishable here.

### 5. A single rate across the two series is refuted. **[SOLID — but "shape-free" is too strong]**

```
per-contract fee at P = 0.15 (ATP) :  $0.008925
per-contract fee at P = 0.27 (MLB) :  $0.006900        HIGHER at the price FURTHER from 0.50
P(1-P)         at P = 0.15         :   0.1275
P(1-P)         at P = 0.27         :   0.1971
```

**The correct quantifier, and it is narrower than "shape-free":** a single rate
is refuted for any model of the form `rate × shape(P)` whose **shape is
symmetric about 0.50 and non-decreasing on [0, 0.50]**. Both prices lie below
0.50, so any such shape gives `shape(0.15) ≤ shape(0.27)`, and the observation
requires the opposite. **That covers every candidate in §Power's family and
every published description of Kalshi's fee** — but it is not literally
shape-free: a shape that *decreases* toward 0.50 would rescue a single rate, and
nothing here excludes one. **This is flagged in §"Where I differ from the
audit".**

### 6. Intervals, conditional on the `C·P(1−P)` shape. **[CONDITIONAL — this is the weak half]**

```
k_MLB  in  (0.034957, 0.035008]     5 MLB fills (3 registered), 1 free parameter
k_ATP  in  (0.069961, 0.070000]     from ONE fill
```

> **`k_ATP` carries ZERO degrees of freedom.** One fill, one price, one size,
> one free parameter. It **cannot test** `0.07`; it can only fail to refute it,
> and it did not fail. What makes it worth writing down is that the value it
> implies is `0.1785 / 2.55 = 0.070000` **exactly** — the ceiling is a no-op
> there — and that this coincides to seven decimals with the interval
> `(0.069771, 0.070129]` that Amendment A's **eleven settlements** pinned
> independently. **Corroboration, not a test**, and the difference is not
> rhetorical.

`k_MLB` has 5 constraints on 1 parameter, so it is a genuine over-identification
— but at **two prices** (`0.27`, `0.48`) inside a **fourteen-minute window** in
**one series**.

### 7. The shape test that did pass, and it is not vacuous. **[CONDITIONAL, one degree of freedom]**

From the two MLB prices, with the $0.0001 ceiling accounted for:

```
k * shape(0.27)  in  (0.00689, 0.0069]     (F1 and F2 together)
k * shape(0.48)  in  (0.0087,  0.0088]     (F4)
admissible ratio shape(0.48)/shape(0.27)  in  (1.260870, 1.277213]
```

| candidate shape | ratio | |
|---|---:|---|
| `P(1−P)` | 1.266362 | **ADMITTED** |
| `P` | 1.777778 | refuted |
| `min(P, 1−P)` | 1.777778 | refuted |
| `sqrt(P(1−P))` | 1.125328 | refuted |
| `(P(1−P))²` | 1.603673 | refuted |
| constant | 1.000000 | refuted |

The power family `(P(1−P))^a` is pinned to **`a ∈ (0.9816, 1.0361]`**.

**Credited as non-vacuous** — five named alternatives died, including the
constant, and the admitted band is narrow. **And it is one degree of freedom**:
two prices, one ratio. It is a *consistency check that `P(1−P)` passed*, not a
demonstration that `P(1−P)` is right.

### 8. `$0.0001` is not representable in this repo's price unit. **[MECHANICAL]**

`core/prices.py` is integer **tenths of a cent** = $0.0001 exactly... and that is
the coincidence that hides the problem. A **fee** of $0.0001 is 1 tenth, fine —
but `ceil`-to-$0.0001 arithmetic on `k · C · P(1−P)` does not stay on the tenths
grid for fractional `C`, and `count_fp = 0.27` is now a thing this account
receives. **A units decision is pending and it is an ADR, not a patch.**

---

## The decomposition — the heart of this write-up

The gap between the deployed fee and the observed fees is **two independent
steps**, and they have **completely different evidential standing**. Collapsing
them is how this result would be misused.

```
                                             fee@50c  break-even  headroom  S_min E1   sizes?
deployed   0.07, ceil-to-CENT                $0.0200    52.00%      0.38     -2.0534     NO
step 1     drop the cent ceiling, keep 0.07  $0.0175    51.75%      0.63     +0.5466     NO
step 2     also halve the coefficient (MLB)  $0.0088    50.88%      1.50     +9.2466    YES
```

*(`S_min E1` is row id 726, `KXMLBGAME-26AUG091335NYMPIT-NYM` yes, ask 450 — the
nearest clean observation on the pinned record. "sizes?" is against §0.4's
1.0-tenth sizing supremum.)*

**Step 1 is well supported.** All six fills require it. It is corroborated
**exactly** by the ATP cell at a coefficient the settlements pinned
independently. And it has an independent mechanism — fractional `count_fp` —
that is not a fee measurement.

**Step 2 is 77% of the win** — of the 1.12 break-even points between the
deployed model and step 2, step 1 supplies **0.25** and step 2 supplies
**0.87** — **and it rests on a
post-hoc fit at two prices in one fourteen-minute window, confounded four
ways.**

> ### **ADR 0021's refutation is not overturned by the well-supported half of the model.**
>
> Under **step 1 alone**, the `S_min` row reaches **+0.5466 tenths**, which is
> **below** §0.4's **1.0-tenth** sizing supremum. **It does not size.**
> Actionability needs **step 2** — the half that is weak.

### Why step 2 is confounded four ways, and the design cannot separate them

The six fills admit **four attributions that fit 6 of 6 equally**:

| attribution | the split it implies |
|---|---|
| by **series** | `KXMLBGAME` vs `KXATPDOUBLES` |
| by **order size** | `C < 20` vs `C ≥ 20` |
| by **price region** | `P < 0.20` vs `P ≥ 0.20` |
| by **sport** | baseball vs tennis |

Every MLB fill is small and at `P ≥ 0.27`; the single ATP fill is large and at
`P = 0.15`. **The four axes are perfectly collinear in this data set.**

> **"The rate is per-category" is UNSUPPORTED and is not written here, in either
> direction.** It is one of four readings and the design cannot separate them.

**`k = 0.035` may be written only as:** *"at `KXMLBGAME`, `C ∈ {0.27, 1, 10}`,
`P ∈ {0.27, 0.48}`, on 2026-08-10."* Not as a property of `KXMLBGAME`
generally, and not as a coefficient this project adopts.

### The category with no measurement in it at all

**[MEASURED — the pinned record, `pin = 1564`]**

```
KXMLBGAME     1142 rows   (73.0%)      5 fills
KXWNBAGAME     422 rows   (27.0%)      ZERO fills
```

Applying `k = 0.035` naively across the record moves **137 → 206** rows to a
positive net edge at `N = 1`. **85 of the 206 are WNBA — 41% of the
newly-positive rows come from a category with no measurement in it.** (Step 1
alone gives 158.)

**And any such count is a re-run, not arithmetic.** Two of the eleven
suppression checks are functions of the edge (`edge_within_method_noise`,
`suspicious_edge`), so changing the fee moves the clean population itself. The
numbers above are computed over **all** rows and are **descriptive only** —
**they are not a claim that 206 rows would be actionable.**

---

## The settlement contradiction — ranked, not resolved

```
all 11 single-game settlements fit  ceil-to-CENT x 0.07     11/11
                                    ceil-$0.0001 x 0.07      0/11
                                    ceil-to-CENT x 0.035     0/11
                                    ceil-$0.0001 x 0.035     0/11
```

The settlements and the fills **cannot both be describing one unchanging
schedule.** Three readings, ranked by support. **Not resolved.**

**(1) The schedule's GRANULARITY changed. — best supported.**
`k = 0.07` is pinned by the settlements to `(0.069771, 0.070129]` and reproduced
**to seven decimals** by the ATP fill, so on that axis nothing moved: **only the
rounding did.** Fractional contract counts give it an independent mechanism, and
the change is dated inside a window containing the named **July 2026 revision**.

**(2) Per-category. — cannot be excluded, and Amendment A §A2.1 predicted exactly
this.** The settlements are NFL/NBA; the fills are MLB/ATP.

**(3) Settlement `fee_cost` is a different quantity from fill `fee_cost`. —
weakened.** **[MEASURED]** 32 of the 43 `KXMVE` combo settlements already carry
**sub-cent** fees, the earliest dated **2025-11-28**. So the settlements
endpoint demonstrably *can* report sub-cent values, and reading 3 now needs an
unmotivated **product-conditional** display rule — cent-rounded for single-game,
sub-cent for combos — to survive.

### How the ATP fill splits Amendment A's confound — which the amendment did not anticipate

**F3 (ATP, `k ≈ 0.07`) and the MLB fills (`k ≈ 0.035`) are 63.9 seconds apart.**
A schedule change over time **cannot** produce a cross-sectional difference
inside 64 seconds. Therefore:

> **The changed-schedule story is confined to the ROUNDING, where it is well
> supported. The category story is confined to the MLB HALVING, where it is one
> of four readings.**

Amendment A registered the confound between the baseline and the fills. It could
not have registered this, because it did not foresee the fills spanning two
series — §S12 records that as a registration defect.

---

## Correction to Amendment A §A1.1

Amendment A wrote that the 11 settlements *"confirm `ceil` over `floor`,
`half_up` and `half_even`"* without saying how many records carry that weight.

**[MEASURED]** the raw value `0.07 × n × P(1−P)` is **already an exact whole
cent on zero of the eleven**. So **all ELEVEN require a cent round-up**, not two,
and every one of them discriminates `ceil` from a no-rounding model. The
Amendment A claim is **correct and was understated**; this records the count.

---

## Registered now, before the data: the follow-up that would break the confound

**A PROPOSAL. It needs its own pre-registration and Joe's approval, and it is
not a plan.** Recorded here so that it is on the record before the settlement
data arrives.

> **Two orders in `KXMLBGAME` at `P ≈ 0.15`: `C = 1` and `C = 20`.** Same series,
> same day, crossing **both** the size boundary (`C < 20` vs `C ≥ 20`) and the
> price boundary (`P < 0.20`) that currently masquerade as category.
> **Max stake ≈ $3.15.**
> **If both return `k = 0.035`, "rate by size" and "rate by price region" both
> die**, leaving series and sport — which are themselves collinear until a
> second non-MLB series is filled.

---

## What this measurement does not establish

*Written for this result, not echoed from any module docstring.*

- **It does not establish the current fee model.** The verdict is H3−: both
  registered models are refuted and **no third model is adopted**. `k = 0.035`
  and `k = 0.07` are **hypothesis generators**, labelled as such, exactly as §2
  of the registration requires.
- **It does not establish that the rate is per-category.** Four attributions fit
  6 of 6 equally and the design cannot separate them.
- **It does not establish `k = 0.035` for `KXMLBGAME`.** Only for
  `C ∈ {0.27, 1, 10}`, `P ∈ {0.27, 0.48}`, on 2026-08-10.
- **It does not establish anything about `KXWNBAGAME`**, which is 27.0% of the
  record and **zero of the fills** — and which would supply 41% of the
  newly-positive rows under the weak half of the model.
- **It does not establish the charge, only the reported field.** P2 was never run
  and is now unrunnable; the residual is ≤ $0.0001 and unmeasured. §S7's in-app
  cross-check was not recorded either, so there is **no second channel at all**.
- **It does not establish the maker model.** All six fills are taker; §3's maker
  branch never fired.
- **It does not establish the shape.** `P(1−P)` passed a **one-degree-of-freedom**
  ratio test at two prices. Five named alternatives died; infinitely many did
  not.
- **It does not establish that `0.07` still holds anywhere.** `k_ATP` has **zero
  degrees of freedom** — one fill, one free parameter. It corroborates; it
  cannot test.
- **It does not resolve the settlement contradiction.** Three readings, ranked,
  none excluded.
- **It does not overturn ADR 0021.** The well-supported half (step 1) leaves the
  nearest clean row at **+0.5466 tenths**, below the 1.0-tenth sizing supremum.
  It does not size.
- **It does not license any code change.** `calculate_fee` is unchanged, the
  52.00% bar in `CLAUDE.md` is unchanged, ADR 0021 is unamended.
- **`n = 4` registered fills** (6 placed), one account, one day, one
  fourteen-minute window, two series, three prices, four sizes. No interval
  anywhere is a sampling interval; every interval quoted is a **deterministic
  consistency set** implied by integer-grid rounding.
- **P7 is UNTESTED**, so retroactive fee aggregation across orders in one market
  is **undetected, not excluded** — and F1, F2 and the fractional fill were all
  in one market.

---

## Where I differ from the audit

Three things, all in the direction of weakening a claim.

1. **"A single rate across the two series is refuted *shape-free*" is too
   strong.** It is refuted for any shape **symmetric about 0.50 and
   non-decreasing on [0, 0.50]** — which is every candidate anyone has proposed,
   but is not "shape-free". A shape decreasing toward 0.50 would rescue a single
   rate, and nothing observed excludes one. The finding survives; the quantifier
   does not. `tasks/lessons.md`: universals get tested as written.

2. **The 20-cell census is oversold by its own arithmetic.** Sixteen of the
   twenty die on **representability of `$0.0019` alone**, before any coefficient
   is considered, and the surviving four-way rounding test is decided
   **entirely by the MLB cells** — the ATP cell admits `floor`, `half-up` and
   `half-even` as well. "Unique survivor of 20" is true and reads as far more
   evidence than it is. It is one representability observation plus a four-way
   test at one series.

3. **The audit did not flag that the registration's own linearity bonus reading
   returned the WRONG answer** (§S8). `fee(F2) = 10 × fee(F1)` exactly, which
   the registration says is *"evidence for per-contract scope"* — and F3 refutes
   per-contract coefficient-free. The diagnostic was written against a cent grid
   and is near-vacuous on a $0.0001 grid. That is a defect in my registration,
   and a licensed-findings list that omits it would have left a wrong reading
   standing in a committed document.

One addition rather than a disagreement: the audit's *"the 6-of-6 fit came from
placing another order, not from learning anything"* is **stronger than stated and
is now measured** — `k_MLB` is bit-identical computed from the three registered
MLB cells and from all five (§"Protocol breach").
