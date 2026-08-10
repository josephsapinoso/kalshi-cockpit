# Result — re-scoring the pinned record under all three fee models

**Run 2026-08-10, offline, against the pinned pull
[`2026-08-10-clean-shortfall-pull.json`](2026-08-10-clean-shortfall-pull.json)
(`pin = 1564`). Nothing was re-pulled, no live call was made, no order was
placed. Harness: [`scripts/rescore_fee_models.py`](../../scripts/rescore_fee_models.py);
full output: [`2026-08-10-fee-model-rescore-run.txt`](2026-08-10-fee-model-rescore-run.txt).**

**Audited by `measurement-skeptic` before commit. Verdict: SOUND WITH
CORRECTIONS — twelve of them, every one taken. §11 records what the audit
changed, because four of the corrections weakened the headline and one of them
falsified a sentence that was already written.**

ADR 0021 refuted the consensus-only strategy on the evidence that **zero clean
rows clear the deployed fee**, with `max E1 = −2.0534` tenths. That was computed
with `core/fees.py`'s `max(model_a, model_b)` hedge, which
[`2026-08-10-fee-model-fill-calibration-result.md`](2026-08-10-fee-model-fill-calibration-result.md)
refutes at all four registered cells. Every row's `E1` therefore moves. This
re-scores it.

---

> # THE ONE-LINE ANSWER
>
> **Under the most expensive fee consistent with the observed rounding
> (step 1), NO rows surface.** Three of the 614 clean rows flip to a positive
> edge, and every one is refused by `edge_within_method_noise` — and
> additionally by a sizing floor that is a property of the $1,000 reference
> bankroll rather than a law. **ADR 0021's conclusion survives, and it is
> `edge_within_method_noise` that carries it.**
>
> **Under the cheaper post-hoc coefficient (step 2), it does not.** Four rows —
> three claims, three games, each at one recording instant — clear every check
> and size. There `edge_within_method_noise` is decisive: it is the difference
> between 4 and 9.
>
> **So ADR 0021's fate turns on the fee attribution, which is unresolved five
> ways.** And a guard that had never been load-bearing is now what stands
> between the strategy and a bet.

---

## §1. What changes, and what cannot

| | |
|---|---|
| `deployed` | `max(model_a, model_b)`, cent-rounded. fee@50c, C=1 = **$0.0200** |
| `step 1` | `0.07 × C × P(1−P)`, `ceil` to `$0.0001`. fee@50c = **$0.0175**. **Its ROUNDING is well supported** — all six fills require it, with an independent mechanism (fractional `count_fp`) that is not a fee measurement. **Its COEFFICIENT is refuted for MLB**: F1, F2 and F4 are registered `KXMLBGAME` cells and charge ~half what `0.07` predicts (F4: `C=1`, `P=0.48`, charged `$0.0088` against a predicted `$0.0175`). `0.07` survives only at the single ATP cell, which carries **zero degrees of freedom**. Every row this document surfaces is `KXMLBGAME` at `C=1`, `P ∈ [0.40, 0.57]` — the same series, adjacent to the same prices. **For these rows step 1 is the conservative upper bound on the fee, not the likeliest estimate.** |
| `step 2` | `0.035 × C × P(1−P)`, `ceil` to `$0.0001`. fee@50c = **$0.0088**. **POST-HOC** — a fit at two prices in one fourteen-minute window in one series, with **five** rival attributions the design cannot separate |

**The population cannot grow, and the reason is a measured zero rather than a
monotonicity argument.** Nine of the twelve suppression checks read inputs the
fee does not touch. Three are movable — `edge_within_method_noise`,
`suspicious_edge`, and `insufficient_depth`, which reads a size the edge
determines — and only one of the three can move in the **permissive** direction:

- `suspicious_edge` fails above 40 tenths, so a cheaper fee can only make it
  fire more.
- `insufficient_depth` requires `depth ≥ max(10, contracts)`; a cheaper fee
  raises Kelly and therefore the requirement. **Three rows carry this code
  alone** — `id 281` (depth 0.47), `id 26` (8.51) and `id 12` (4.00) — and two
  of them would clear the step-2 fee (`+6.24` and `+4.96` tenths). All three sit
  below the **10-contract floor no fee can lower**, so none can enter.
- `edge_within_method_noise` is the exception. It fails on `0 < edge ≤ spread`,
  so a large enough rise carries a row over its own spread and the check starts
  **passing**. That path needs a row suppressed by that code *alone*.

```
suppressed ONLY by edge-dependent codes ........ 0
suppressed by `insufficient_depth` alone ....... 3   (all depth < 10)
fee-INVARIANT eligible pool ................... 614  == the clean population
```

**There is no such row on this pin**, so the eligible set is exactly the clean
614 and every count below sits on **ADR 0021's own denominator**:

```
n_rows   614      n_obs 323      n_claims 118      G 59      sweeps 34
```

**Say `59 games across 34 recording instants`.** Never `614 rows`. This is a
fact about `pin = 1564`, not a structural guarantee.

## §2. Reproduction checksums, printed before any result

| Check | Result |
|---|---|
| stored `edge_tenths` == deployed `E1` at C=1, **clean rows** | **614 of 614** |
| ...whole table | 1,471 of 1,564 — the 93 misses are rows the engine sized at C>1 |
| `edge_tenths` **and** `fee_predicted` jointly satisfiable by **one** order size | **1,564 of 1,564.** Implied sizes on the 93 misses: min 10, max 50, modal 50. Solving the edge alone is *not* enough — `fee/C` is piecewise constant in `C`, so several sizes fit the edge and only one fits both. `suggested_contracts` cannot be used here: `engine.py` zeroes it on every suppressed row |
| `fair_probability == min(four devig readings)` | 1,564 of 1,564 |
| the two edge-dependent codes re-derived from the stored edge, counted **per code** | `edge_within_method_noise` **0**, `suspicious_edge` **0**, over 1,564 rows |
| whole-table rows with positive net edge: deployed / step 1 / step 2 | **137 / 158 / 206**, of which **55 / 66 / 85** are `KXWNBAGAME` |
| ~~stored `reference_contracts > 0` == recomputed at the deployed fee~~ | **VACUOUS — 0 vs 0, and labelled rather than quoted.** Every clean row has a negative edge, so Kelly is 0 and both figures are forced under any implementation, right or wrong. It tests nothing about the caps, `kelly_fraction`, the floor division or `max_order_contracts` |
| **`reference_contracts` vs the production `size_position`**, synthetic sweep over the price grid at fair values that *do* carry an edge | **700 probes, 467 sizing a positive number, 343 hitting `max_order_contracts`, 0 disagreements.** This is the non-vacuous replacement, and it exercises the regime that actually decides whether a row sizes |

The `137 / 158 / 206` row reproduces the fee-calibration result's figures and its
"85 of the 206 are WNBA — 41%" from an implementation that **shares no code in
the counterfactual fee path** (both reach `settlement_fee` for the `deployed`
column and `PRICE_MAX` for the grid). It is a checksum on that document, not new
evidence.

## §3. The counts, under each model

| | `deployed` | `step 1` | `step 2` |
|---|---:|---:|---:|
| `max E1` over the clean population (tenths) | **−2.0534** | **+0.5466** | **+9.2466** |
| clean **rows** with `E1 > 0` | **0** of 614 | **3** of 614 | **9** of 614 |
| ...deduplicated to **observations** | 0 of 323 | 2 of 323 | 7 of 323 |
| ...deduplicated to **claims** | 0 of 118 | 2 of 118 | 6 of 118 |
| ...distinct **games** | 0 of 59 | 2 of 59 | 6 of 59 |
| **surviving the full deployed predicate** | **0** | **0** | **4 rows / 3 claims / 3 games** |

`E1` is the post-fee edge per contract at one contract, in tenths of a cent —
the same quantity ADR 0021 uses. The "full deployed predicate" is every check
the engine applies after the fee: the two edge-dependent suppression codes, the
depth requirement, and `reference_contracts > 0`. It is not the fee alone.

## §4. The per-guard table — the answer to "what stops them"

### Step 1

```
   id ticker                          sd  ask       E1   spread  refC  refused by
  726 KXMLBGAME-26AUG091335NYMPIT-NYM yes 450  +0.5466  2.3191     0  edge_within_method_noise + sizing
  355 KXMLBGAME-26AUG071910LAAMIA-MIA no  550  +0.4348  4.9580     0  edge_within_method_noise + sizing
  352 KXMLBGAME-26AUG071910LAAMIA-LAA yes 550  +0.4348  4.9580     0  edge_within_method_noise + sizing
```

| guard | fires | fires ALONE | bears on |
|---|---:|---:|---|
| `edge_within_method_noise` | 3 of 3 | 0 | **the economic claim.** This is the guard that makes ADR 0021 §1 survive |
| reference sizing floor | 3 of 3 | 0 | **the actionability claim only** |

**Two constraints bind on every row, and they are not equally load-bearing.**
The sizing floor is exact arithmetic **given** `REFERENCE_BANKROLL_DOLLARS =
1000` and `kelly_fraction = 0.25` — a row sizes iff
`E1 > 4000·eff·(1−eff)/bankroll` tenths, whose supremum is 1.0 tenth *only at
$1,000*. Both are chosen config values, and raising either switches this guard
off:

```
id 726  sizes at a reference bankroll of $1,822   (or kelly_fraction 0.455 at $1,000)
id 355  sizes at a reference bankroll of $2,258   (or kelly_fraction 0.565 at $1,000)
id 352  sizes at a reference bankroll of $2,258
```

**So the over-determination is one guard deep for *"is there an edge"* and two
deep for *"would we have bet"*.** An earlier draft of this document called the
sizing floor "not a threshold anyone chose". That was wrong, and correcting it
is what moved `edge_within_method_noise` from "one of two redundant refusals" to
"the load-bearing one".

### Step 2

```
   id ticker                          sd  ask       E1   spread  refC  refused by
  726 KXMLBGAME-26AUG091335NYMPIT-NYM yes 450  +9.2466  2.3191     9  -- SURFACES
  355 KXMLBGAME-26AUG071910LAAMIA-MIA no  550  +9.1348  4.9580     9  -- SURFACES
  352 KXMLBGAME-26AUG071910LAAMIA-LAA yes 550  +9.1348  4.9580     9  -- SURFACES
   37 KXMLBGAME-26AUG081845CINWSH-CIN yes 550  +5.8778  5.1560     5  -- SURFACES
  724 KXMLBGAME-26AUG091340LAAMIA-MIA yes 560  +5.3473  5.8534     5  edge_within_method_noise
  862 KXMLBGAME-26AUG091340LAAMIA-MIA yes 570  +4.2381  5.9313     4  edge_within_method_noise
 1350 KXWNBAGAME-26AUG09DALMIN-MIN    no  270  +3.1375  5.4137     3  edge_within_method_noise  [WNBA]
 1377 KXMLBGAME-26AUG101907BOSTOR-TOR yes 400  +2.1201  6.0451     2  edge_within_method_noise
 1376 KXMLBGAME-26AUG101907BOSTOR-BOS no  400  +2.1201  6.0451     2  edge_within_method_noise
```

| guard | fires | fires ALONE | **decisive?** |
|---|---:|---:|---|
| `edge_within_method_noise` | 5 of 9 | **5** | **YES** — delete it and **9** rows surface instead of 4 |
| reference sizing floor | 0 of 9 | 0 | no — every positive row sizes |
| `suspicious_edge` | 0 of 9 | 0 | no — `max E1 = 9.25` against a 40.0 ceiling |
| depth | 0 of 9 | 0 | no — thinnest book is 674 contracts against a requirement of 10 |

**This is the state ADR 0021 §5.1 says has never occurred.** On the deployed
record `edge_within_method_noise` fires 18 times and **never alone**. Under
step 2 it fires alone five times.

### The rows that surface, by identity rather than by count

```
id  726   KXMLBGAME-26AUG091335NYMPIT   claim NYM   instant 1786213465092
id  355   KXMLBGAME-26AUG071910LAAMIA   claim LAA   instant 1786147495580
id  352   KXMLBGAME-26AUG071910LAAMIA   claim LAA   instant 1786147495580
id   37   KXMLBGAME-26AUG081845CINWSH   claim CIN   instant 1786131207487
```

**Read the claim column before the row count.** `352` is `LAA` bought YES and
`355` is `MIA` bought NO, at the same instant on the same game. Under A1 those
are **one claim**. So: **4 rows → 3 claims → 3 games**.

**And they are claim-*instants*, not durable opportunities:**

```
(NYMPIT, NYM)  7 clean rows across 4 instants -> 1 surfaces   E1 -21.66 .. +9.25
(LAAMIA, LAA)  4 clean rows across 2 instants -> 2 surface    E1  -7.31 .. +9.13
(CINWSH, CIN)  8 clean rows across 4 instants -> 1 surfaces   E1 -19.99 .. +5.88
```

Each surfaces at **one** of the several instants at which it was observed, and
the same claim reads as low as −21.66 tenths at another. Anyone quoting "three
claims across three games" as three opportunities has over-read the row.

## §5. The re-cuts

| Reading | step 1 | step 2 |
|---|---:|---:|
| no dedup, all 614 clean rows | **0** | **4** |
| largest-`E1` representative, observation key | **0** | **3** |
| largest-`E1` representative, claim key | **0** | **3** |
| *smallest-`E1` representative, observation key* | *0* | *1* |
| *smallest-`E1` representative, claim key* | *0* | *0* |
| **leave-one-GAME-out**, all 59 clusters | **0 every time** | min **2**, max 4 (56×4, 2×3, 1×2) |
| **leave-one-SWEEP-out**, all 34 sweeps | **0 every time** | min **2**, max 4 (31×4, 2×3, 1×2) |
| largest single **game** | — | `KXMLBGAME-26AUG071910LAAMIA`, **2 of 4 = 50.0%** |
| largest single **sweep** | — | `1786147495580`, **2 of 4 = 50.0%** |

**Both units are printed deliberately.** ADR 0021 §2 records that the
*dependence* unit is the sweep and that two earlier documents printed only the
cluster; a third omitting it would read as a convention. Here they coincide,
because the two rows in question share both a game and an instant.

**The smallest-`E1` rows are printed for continuity with §5.2 and must not be
read as the answer.** §5.2 used that rule against H3b, an *order statistic*.
This is an **existence** claim, and the registration's §3 justifies the
largest-`E1` rule for exactly that case: keeping the most favourable row per
group is the reading most likely to falsify a null, so it cannot manufacture
one. Quoting the italic rows as refuting step 2 would be the mirror image of the
error the table exists to prevent — and §4's persistence block is the honest
version of what they are pointing at.

## §6. Where the coefficient is not licensed

**`KXWNBAGAME` is 27.0% of the record and zero of the six fills.**

```
step 1   positives from KXWNBAGAME:  0 of 3      surfacing:  0
step 2   positives from KXWNBAGAME:  1 of 9      surfacing:  0
             (id 1350, KXWNBAGAME-26AUG09DALMIN-MIN, no, ask 270, E1 +3.1375)
```

**No conclusion here rests on a WNBA row.** That is fortunate rather than
designed.

**The same argument applies on the price axis and must be made there too.**
`k = 0.035` is licensed by the calibration result only at `C ∈ {0.27, 1, 10}`
and `P ∈ {0.27, 0.48}`. **All four surfacing rows sit at `P = 0.45` or
`P = 0.55`** — an extrapolation, even if a short one: `P(1−P) = 0.2475` against
the observed `0.2496` at `P = 0.48`, a 0.8% move on the shape. The series gap
and the price gap are the same species of unlicensed transfer, and only the
first was flagged in the first draft.

## §7. Sensitivity — where this could be wrong by arithmetic

**(a) `E1` is computed at one contract.** The C=1 fee carries up to `$0.0001` of
its own ceiling, so the per-contract fee at **any** size is below it by at most
**0.1 tenths — a flat bound, not `0.1/C`.** (`0.1/C` is wrong: the evaluated
infimum improves `id 726` by 0.075 tenths, which exceeds `0.1/C` for every
`C ≥ 2`.) Rather than argue the bound, the worst case was **evaluated** — the
fee replaced by its infimum over all order sizes, `k·P(1−P)` with no ceiling —
and the whole predicate re-run:

```
step 1   E1>0:  3 -> 3      surfacing:  0 -> 0
step 2   E1>0:  9 -> 9      surfacing:  4 -> 4
```

Nothing moves. Exactly one clean row sits within 0.15 tenths of any decision bar
(`id 714`, `E1 = −0.0915` against the fee bar under step 2), and its own method
spread is 14.42 tenths, so even flipping its sign would trip
`edge_within_method_noise`. *ADR 0021 §3's magnitude ban applies to that figure
too: it is a sensitivity diagnostic, not a statement of how far a row falls
short.*

**(b) The deployed fee is not flat in order size, and this has already fired —
with no fee correction at all.** `size_position` prices through
`effective_price(ask, contracts=1)`, deliberately, because under Model A that is
the most expensive per-contract fee any size pays. Under `max(A, B)` the
per-order cent ceiling makes the per-contract fee **fall** with size, and over
the clean population at the **unchanged deployed fee**:

```
   C   rows E1>0     max E1            ask     C=1    C=10    C=50  (tenths/contract)
   1          0    -2.0534             450  20.000  18.000  17.400
   5          0    -0.0534             500  20.000  20.000  20.000
  10          0    -0.0534             550  20.000  18.000  17.400
  25          3    +0.3466
  50          3    +0.5466
```

The three rows that cross are `id 726`, `355` and `352` — **the same three
step 1 produces**, which is not a coincidence: at ask 450 the deployed fee at
C=50 *is* step 1's fee. **So ADR 0021 §2's "zero clean rows clear the deployed
fee" is size-conditional as well as fee-conditional.** All three are still
refused, so nothing surfaces — but the crossing is real, and a row that is −EV
at one contract and +EV at fifty is sized at zero and never re-priced. An
observation about the deployed sizer, offered as a finding, **not** a
recommendation; changing it would be a code change needing its own ADR.

**(c) The counterfactual coefficient is applied at C=1 to decisions that imply
multi-contract orders.** Under **`rate by NOTIONAL`** — the fifth attribution,
registered at round two §C4, a threshold anywhere in `($2.70, $3.00]` — the rate
a row pays depends on its own stake:

```
id 726  C=9  notional $4.05   ABOVE $3.00 -> takes the HIGH rate (= step 1) -> does NOT surface
id 355  C=9  notional $4.95   ABOVE $3.00 -> takes the HIGH rate (= step 1) -> does NOT surface
id 352  C=9  notional $4.95   ABOVE $3.00 -> takes the HIGH rate (= step 1) -> does NOT surface
id  37  C=5  notional $2.75   inside ($2.70, $3.00] -> UNDETERMINED
```

**Three of the four step-2 survivors are not self-consistent under one of the
five live attributions**: the size that makes a row worth betting pushes it into
the regime where the coefficient that made it positive does not apply. §7(a)
does **not** bound this — it varies the ceiling holding `k` fixed. So the step-2
count of 4 is itself conditional on the attribution being `series`, `sport`,
`size` or `price` rather than `notional`.

## §8. What this does to ADR 0021

**The conclusion survives step 1 and falls under step 2. Three of its supporting
statements do not survive either, and §7.4 already said they would — *"if both
candidate models are wrong, every number in this ADR moves."* They moved.**

| ADR 0021 statement | Status |
|---|---|
| §1 — *"Kalshi is not mispriced relative to a devigged sportsbook consensus it may itself lead"* | **STANDS under step 1, in the form "no clean row was distinguishable from method noise".** Three rows (2 claims, 2 games) *do* clear the step-1 fee; it is `edge_within_method_noise` that makes the sentence survive, and the sizing floor is not evidence for it. **FALLS under step 2**, where 3 claims across 3 games surface. |
| §2 — *"Zero clean rows clear the deployed fee. `max E1 = −2.0534`."* | **FEE-conditional AND SIZE-conditional.** Under step 1, 3 clean rows clear the fee. Under the *unchanged* deployed model at 25 or 50 contracts, the same 3 clear it (§7(b)). What survives is **"zero surface"** — and that is a strictly **weaker** claim, not a stronger one: "zero clear the fee" *entails* "zero surface", never the reverse. What survives is that no row would have been bet, not that no row cleared the cost. |
| §5.1 — *"Deleting both edge-dependent checks would leave the clean population byte-identical at 614"* | **FALSE under both corrections.** Under step 1 they remove 3 rows; under step 2, 5. The dependent-variable contamination §5.1 defends against is **inert only at the deployed fee**. §5.1's own scoping — *"a fact about `pin = 1564`, not a structural guarantee"* — was correct and is now exercised. |
| §3 — the H3b prohibition and the ban on *"the nearest is 0.21c short"* | **UNTOUCHED.** Under step 1 the sign at `id 726` flips to `+0.5466` while its own method spread is `2.3191` — the same fact §5.3 records: the sign there is a function of devig-method choice. No sentence here expresses any shortfall or edge as a multiple of its own noise, and none may be derived from one. |
| §8 option **E** — *"Resolve the fee model first"* | **This document is the argument for E, made numerically.** E is no longer merely orthogonal and cheap; it is the **only** thing that decides whether §1 stands. |

**The honest summary sentence, and the only one licensed:**

> **On this record, the most expensive fee consistent with the observed rounding
> flips three rows' sign and surfaces none of them, on the strength of one
> guard. The cheaper post-hoc coefficient surfaces three claim-instants across
> three games, and three of the four rows are inconsistent with one of the five
> live attributions. Which coefficient is true is unresolved, and ADR 0021's
> conclusion is exactly as strong as the case for step 1 over step 2.**

## §9. What the two corrections above imply about `edge_within_method_noise`

Stated separately because it is the part most likely to be acted on, and it is
**not** a recommendation.

`edge_within_method_noise` has fired 18 times on the deployed record and
**never alone**. ADR 0021 §5.1 records it as empirically inert. Under step 2 it
fires alone five times and decides four bets, and under step 1 it is the single
guard carrying §1's claim. **A check nobody has ever justified against outcomes
has become decisive without anyone choosing that.**

That is a reason to *look at* it, and the direction to look is whether a guard
this project has never validated should be deciding whether money moves. It is
**not** a reason to loosen it: the guard's stated rationale — refuse an edge
smaller than the disagreement among the methods that produced it — is exactly
CLAUDE.md's rule 2 applied to a specific row, and every row it refuses here has
an edge inside its own method spread. Any change needs its own ADR and its own
registration.

## §10. Two defects found in adjacent documents, reported not fixed

**(a) `core/prices.py`'s unit is `$0.001`, not `$0.0001`.** The fee-calibration
result's finding 8 reads *"`core/prices.py` is integer tenths of a cent =
`$0.0001` exactly... and that is the coincidence that hides the problem."*
`PRICE_MAX = 1000` for `$1.00`, and the module's own docstring says
`$0.0010 = 1 tenth = 0.1c`. The fee grid is therefore **ten times finer** than
the price grid, not equal to it. That finding's conclusion — a units decision is
pending and is an ADR — is **strengthened**: there is no coincidence to hide
behind, and a `$0.0001` fee is not representable at all. **Not edited here.**

**(b) The fee-calibration result's four-way attribution table is one short.**
The round-two registration §C4 adds a fifth — **rate by NOTIONAL**, a threshold
in `($2.70, $3.00]`, which fits all six round-one fills as well as any of the
four. `start.md:303`'s *"confounded five ways"* is the later and correct count;
the calibration result's list is the one that needs the annotation. §7(c) shows
this is not bookkeeping: under that fifth attribution three of the four step-2
survivors do not survive.

## §11. What the audit changed

Recorded because a result that hides its corrections is worth less than one that
does not, and because four of these weakened the headline.

1. **§7(b) was false.** The first draft wrote *"it has never fired on this
   record (no clean row reaches even the C=50 bar)"*. Three clean rows reach it,
   under the **unchanged** deployed model. That also makes ADR 0021 §2
   size-conditional, which nothing had noticed.
2. **The `reference_contracts` checksum was vacuous** (0 vs 0, forced under any
   implementation). Replaced with a 700-probe synthetic sweep against the
   production `size_position`, which exercises the caps, Kelly, the floor
   division and `max_order_contracts`. It passes.
3. **The sizing floor is bankroll-conditional**, not "exact arithmetic, not a
   threshold anyone chose". This is the correction that made
   `edge_within_method_noise` the load-bearing guard rather than one of two.
4. **"A different and stronger claim" was backwards** — "zero clear the fee"
   entails "zero surface", so what survives is strictly weaker.
5. **"Step 1 is well supported" conflated the rounding with the coefficient.**
   The coefficient is refuted at three registered MLB cells by a factor of ~2,
   and every row this document surfaces is MLB.
6. **§10(b) was backwards.** Five is the corrected count; four is the stale one.
7. **§7(c) is new** and is the most damaging finding in the document to its own
   step-2 result.
8. **The `0.1/C` bound was wrong**; the correct bound is 0.1 flat.
9. **The "population cannot grow" argument had an unstated step** —
   `insufficient_depth` is fee-movable, three rows carry it alone, and two of
   them clear the step-2 fee. It still cannot admit them, but that was never
   measured.
10. **The sweep view was missing**, repeating the defect ADR 0021 §2 corrects.
11. **Persistence was missing** — the four rows are claim-instants.
12. Window span corrected to 58 hours (52 over the clean rows); the
    `fee_predicted` citation replaced `suggested_contracts`, which is zeroed on
    suppressed rows; the harness's `elif` was masking one of two checksums.

---

## What this measurement does NOT establish

*Written for this result. It is not a copy of the harness's module docstring,
and the harness does not echo its own `__doc__` into its output.*

- **It does not adopt a fee model, and it is not evidence for one.** The
  calibration verdict is H3−: both registered models are refuted and no third is
  adopted. `k = 0.07` and `k = 0.035` are hypothesis generators. **Every count
  under step 1 and step 2 is a conditional**, and reporting "4 rows surface"
  without "under a coefficient fitted post-hoc at two prices in one
  fourteen-minute window in one series, and inconsistent at three of the four
  rows with a fifth live attribution" is a misquotation.
- **It does not establish that any row was bettable.** Historical asks whose own
  freshness is unmeasurable (§7.6: `kalshi_quote_age_ms` is 0 on all 1,564 rows
  by construction), against odds whose age is a scrape clock and therefore a
  lower bound (§7.5). No order was placed and no fill exists.
- **It says nothing about whether `fair_probability` is right.** Every `E1`
  inherits the conservative devig — a deliberate downward bias of unmeasured
  size (§7.3) — and the `SHARP_BOOKS` anchoring, with §7.2's tautology reading
  attached in full. Four rows clearing a re-scored fee is not four rows with an
  edge; it is four rows where *this* fair value exceeds *that* cost.
- **It is conditional on three config values, not two.** `pin = 1564`, `C = 1`,
  `REFERENCE_BANKROLL_DOLLARS = 1000` and `kelly_fraction = 0.25`. Change the
  bankroll and §4's step-1 answer stops being over-determined; change the fee
  attribution and §3's step-2 answer moves.
- **It does not re-run the operator-side sizing.** `suggested_contracts` depends
  on exposure and P&L at write time, which the payload does not carry.
- **It does not license any code change**, in `core/fees.py`, in the sizer, or
  in `suppression.py`. §9 is a reason to look, not a change.
- **It is one pin, one 58-hour window (52 hours over the clean rows), two
  leagues, one month.** A census over 59 games and 34 recording instants, with
  no interval anywhere. Nothing generalises to a single future row, and the
  family-wise error rate is *empty* rather than controlled because nothing was
  tested for significance.
- **Tests run: three.** Three fee models against one predicate. Every other
  number is a decomposition — a per-guard split, a re-cut, a checksum — not an
  additional test. No cell was scanned and none is reported as significant.
- **It does not partition or stratify by Grid D or Grid B.** Both keep their
  banners. Row-level `ask` values appear as attributes of named rows, which is
  not a cut.
- **The harness has no unit tests**, exactly as ADR 0021 §7.7 records of its
  predecessor. What it has is §2 — including a 614-of-614 reproduction of
  `edge_tenths`, a 1,564-of-1,564 joint reproduction of `edge_tenths` **and**
  `fee_predicted` at a single consistent order size, a 0-disagreement
  reproduction of both edge-dependent codes, and a 700-probe agreement with the
  production sizer — plus an independent audit that re-derived every quoted
  number from the pinned JSON with its own code. That covers the quantities
  actually quoted and nothing else.
