# Pre-registration — the hand-fill fee calibration

**Date:** 2026-08-18
**Status:** Registered. **No value file has been opened. No statistic below has
been computed.**
**Reopening condition for:** ADR 0043 — *"after the 25 fills have been analysed
**off-gate** and it is known whether they match `calculate_fee`."*
**Result destination, fixed now and written whichever way it comes out:**
`docs/measurements/2026-08-18-hand-fill-fee-calibration-result.md`.
**Registered consequence to code: none.** This document declares an
attribution and a gate recommendation. It does not authorise editing
`backend/core/fees.py`, does not authorise changing `TAKER_COEFFICIENT`, does
not re-derive the break-even bar, and does not touch `ORDERS_ARE_DRY_RUNS`.
Each of those needs its own ADR.

---

## 0. Declared contaminations, in full, before anything else

I have been told, and cannot unsee, all of the following. Each is already in
the committed record, so the disclosure is a statement of what a later skeptic
must weigh, not a confession of a leak.

| known | source | what it puts at risk |
|---|---|---|
| Joe's pooled realised fee rate over 22 settled positions is **4.03% of stake** | ADR 0043, "One trap" | §6's decomposition. Mitigated: §6 is an *identity*, registered with its arithmetic, so the decomposition cannot be steered by knowing the input |
| Baseball `k` pinned to `(0.0349691, 0.0350076]` on **9** fills, later **10** across 3 series | round-three result §S12a; ADR 0028 addendum | §5's out-of-sample test. Mitigated: the test is confined to fills that post-date that work (§3) |
| Model B matches **0 of 11** real taker fills and is retired | ADR 0028 | §4's model set. Mitigated: the set is **frozen at six** below and B stays in it as a refuted control |
| The deployed `calculate_fee` overcharges the seen fills by 1.12x–2.90x | round-three result §14 | §7's gate branch. This makes the Q(d) fork **near-determined before the look**, and §7 says so rather than pretending to discover it |
| Joe's net over the 22 settlements is **+$1.03**, 6W–16L, one position carrying the whole sign | calibration registration A5 | Nothing here. **P&L is out of population entirely** — see §11 |

**One further contamination, structural rather than numeric:** thirteen of the
twenty-five fills have already been analysed, twice. That is why §3 exists and
why every hypothesis-*testing* claim in this document is restricted to the
twelve that have not.

---

## 1. The power check, which comes first

**Q(a) — does `fee_cost` match the deployed model? FULLY POWERED.** The
estimand is a deterministic charge on a `$0.0001` grid, not a mean. Twenty-five
exact comparisons; no sampling error exists to be underpowered against. A
single mismatch is a result.

**Q(b) — does `k = 0.035` survive out-of-sample? POWERED BY ONE FILL, subject
to a named precondition.** Inverting `fee = ceil_{1e-4}(k·C·P·(1−P))` gives an
admissible interval of width `0.0001 / D`, where `D = C·P·(1−P)`. For a
1-contract fill at 13c, `D = 0.1131` and the width is `0.00088` — **2.5% of
0.035, and nowhere near 0.070.** One new baseball fill at any ordinary size
therefore separates the two candidate coefficients outright. The precondition:
**if zero new fills carry a `KXMLB*` series prefix, Q(b) returns NOT TESTABLE**
and the old fills may not be substituted for them (§3).

**Q(c) — H4, the settlement charge. UNDERPOWERED FOR CONFIRMATION, and I am
saying so now rather than letting the analysis improvise.** H4 needs the
account balance bracketing a settlement. `venue_balance_snapshots` begins
**2026-08-18**; all 22 settlements are dated **2026-08-10..17**. No balance
observation brackets any settlement in this record, and it is not recoverable
later. Deposit history is unavailable, so even the 2026-08-18 balance cannot be
reconciled against cumulative stakes and proceeds: an unknown deposit and an
unknown settlement charge are **perfectly confounded** — one equation, two
unknowns. **The design has power in exactly one direction** (§8.3): a
settlement `fee_cost` strictly exceeding the summed fill fees for the same
market would refute "settlement is free". Equality would not confirm it — ADR
0027 §1 reason 3 already establishes that reading (i), *the settlements field
reports the entry fee only*, predicts equality with probability 1 whatever H4
is. **Equality is registered in advance as non-discriminating and may not be
cited as evidence in either direction.**

**Durability — UNDERPOWERED BY CONSTRUCTION, and no branch escapes it.** The
25 fills span **2026-08-10 to 2026-08-17, eight days.** Round-three result §15
item 2 requires *"a second MLB observation window, >= 3–4 weeks after
2026-08-14"* before any reduced baseball coefficient is hardcoded. 2026-08-17 is
**three days** after. **Whatever this analysis returns, it does not license
changing `TAKER_COEFFICIENT`, and the result document must repeat that
sentence.**

**Attribute attribution (sport vs series vs per-market tier) — expected
underpowered.** Separating H-SERIES from H-SPORT needs two series *inside one
sport* disagreeing. Nothing in this design arranges that; these are bets Joe
placed, not cells. §5.4 registers the rule in advance so the answer is not
chosen afterwards.

---

## 2. The claims, each stated so it can come back false

Direction is stated on every one. Nothing here is two-sided-then-reported-
one-sided.

- **C1 (Q(a)).** On every fill in the registered population, the charge Kalshi
  applied is **less than or equal to** what the deployed model returns:
  `fee_cost <= model_deployed(P, C) + 1e-9`. *Falsified by one fill in the
  other direction.* One-sided, and the direction is fixed by the module's own
  standing choice to never undercharge.
- **C1b (Q(a)).** On every fill, `|fee_cost − model_deployed| <= 1e-9` — i.e.
  the deployed model is *exactly right*. This is the claim ADR 0043's gate
  condition actually tests, stated separately from C1 because they are
  different claims and only C1b feeds §7.
- **C2 (Q(b)).** On every **new** fill whose series prefix begins `KXMLB`, the
  admissible-`k` interval contains **0.035**. *Falsified by one new baseball
  fill whose interval excludes it.*
- **C3 (Q(b)).** On every **new** fill whose series prefix does not begin
  `KXMLB`, the admissible-`k` interval contains **0.070**. Registered as the
  weaker of the pair: round-three §10 forbids pooling across categories, and
  the "non-baseball is 0.070" record rests on three singleton series. *Falsified
  by one new non-baseball fill excluding 0.070.*
- **C4 (Q(c)).** For every settled position, settlement `fee_cost` is **not
  greater than** the summed `fee_cost` of that market's fills. *Falsified by one
  strictly greater settlement fee — which would refute "settlement is free".*
- **C5 (§6).** The pooled realised fee rate is fully accounted for by
  `k·(1−P)` at the coefficients C2/C3 assign, plus the per-order ceil slack.
  *Falsified by a residual that neither the price mix nor the slack absorbs.*

Every one of C1–C5 is a universal over the observed rows and is deliberately
scoped to **"every fill in this capture"**, never *always*, *never*, or *by
construction*. A universal over eight days of one account's betting is what is
being tested; a universal over the venue is not available and is not claimed.

---

## 3. The population, the unit, and the old/new split

**Population.** Exactly the rows in `data/captures/portfolio_fills.json`
(observed 25, `created_time` 2026-08-10..17) and
`data/captures/portfolio_settlements.json` (observed 22, 2026-08-10..17), as
those files stand at the moment of the first computation. Both are gitignored
and stay so.

**Unit of observation: one fill.** Not one order, not one market, not one game.
Fee is charged per order and a fill is 1:1 with an order on every row seen so
far (round-one P4, round-three P4), but that is an observation, not a
guarantee: **if any `order_id` carries more than one fill row, those rows are
grouped and the group is the unit**, because per-order rounding is the model
being tested. The grouping key is `order_id`. Count of multi-fill orders is
printed before any interval.

**Independence.** Two fills are independent *for this measurement* if they were
charged by separate applications of the schedule — which the per-order model
says means separate orders. There is no clustering variable of the ADR 0029
kind here, because this is not an outcome measurement: the venue's charge is
deterministic given `(series, C, P)` and carries no game-level shock. **What
is not independent is the evidence's coverage:** 25 fills from one account over
eight days is one window, and §11 records that.

**The old/new split, defined by a rule and checked by a count.**

| set | rule | expected n |
|---|---|---|
| **OLD** — already looked at | `created_time <= 2026-08-14T23:59:59Z` | **13** |
| **NEW** — out-of-sample | `created_time > 2026-08-14T23:59:59Z` | **12** |

Thirteen, not eleven. The round-three result analysed 11; ADR 0028's
2026-08-14 addendum added a `KXPGATOUR` and a `KXMLBKS` fill, and
`scripts/reconcile_observed_fees.py`'s header records the file as *"13 taker
fills"* with per-series clusters `n=10` low and `n=3` high. **A registration
that said 11 would have handed two seen fills to the out-of-sample set.**

**Guard.** If the OLD count is not 13, the analysis **stops before any
classification** and records the discrepancy at the top of the result document.
The *rule* stays as written; the count checks the rule, it does not define the
set. The rule's error direction is conservative: a fill placed later on
2026-08-14 and never seen would be misfiled as OLD, which costs out-of-sample
power and cannot manufacture a result.

**A hypothesis formed on OLD may only be TESTED on NEW.** C2 and C3 are scored
on NEW fills only. OLD fills appear in the result document as a reproduction of
the prior work — reproduce-or-report, never re-test — and their reproduction
failing is itself reported.

**Exclusions, all independent of the charge.**

1. `is_taker = false` → excluded from C1/C1b/C2/C3 and counted. All 25 observed
   are takers, so this is expected vacuous; it is registered because the maker
   coefficient is a different number.
2. `action = sell` → reported separately and excluded from the entry-fee
   claims. No sell has ever been captured (A4), so the wire handling is
   unverified; a sell that appears is a **stop-and-report**, not a row to
   parse on the fly.
3. A fill whose admissible interval is **degenerate** — `0.0001/D >= 0.035`,
   i.e. `D <= 0.0028571` — cannot distinguish 0.035 from 0.070 and is excluded
   from the C2/C3 tally, counted, and listed. This exclusion references only
   `C` and `P`, never `fee_cost`.
4. A settlement with **both** `yes_count_fp > 0` and `no_count_fp > 0` is
   reported as TWO-SIDED and excluded from §6's rate denominator, counted. The
   rule references only the count fields.

**No other exclusion is available.** In particular: no fill is excluded for
being unplanned. ADR 0028's `KXPGATOUR` row establishes the standing rule —
*"excluding an observation for being unplanned is exactly the freedom this
document family removes"* — and it binds here, in both directions.

---

## 4. The statistic, named as an estimator

**This is not an estimator of a mean and no p-value is computed anywhere.** The
estimand is a deterministic charge. Adding a p-value later is forbidden.

### 4.1 The price actually paid

`P` comes from the side actually taken: `yes_price_dollars` when the position
is a YES, `no_price_dollars` when it is a NO, each through
`core.prices.dollars_to_tenths` on the dollar string — **never `float()`,
never a mid, never the complement of the other side.** `count_fp` is
fixed-point and fractional values exist (`0.27`, `11.27` observed); it is read
as an exact `Decimal` from its string, never rounded to an int.

**Registered in advance, because it changes what the side error costs:** the
fee is symmetric, `k·C·P·(1−P) = k·C·(1−P)·P`, so choosing the wrong side
cannot change any prediction in C1/C1b/C2/C3. It **does** change `stake = C·P`,
which is §6's denominator, materially. So the side determination is
load-bearing for §6 alone, and §6 prints the stake-weighted price distribution
so a side error is visible.

**Guard:** if `yes_price_dollars + no_price_dollars` is not `$1.00` on a row,
that is recorded and the side's own field is used regardless.

### 4.2 Per-fill admissible `k`, as an interval, never a point

From `fee = g·ceil(k·D/g)` with `g = 0.0001` and `D = C·P·(1−P)`:

```
k  in  ( (fee_cost - 0.0001) / D ,  fee_cost / D ]
```

Half-open, matching the interval form already in
`scripts/reconcile_observed_fees.py`. **Point estimates `fee_cost / D` are
forbidden as the classifying quantity** and forbidden as an input to any
average. A 0.27-contract fill's interval is roughly 6% of 0.035 wide and a
1-contract fill's is 2.5%; averaging point estimates across fills of different
`D` would weight the blunt ones as if they were sharp.

**Sharpness, fixed now:** a fill is **SHARP** if its interval width
`0.0001/D <= 0.0035` (10% of 0.035), **BLUNT** otherwise, **DEGENERATE** if
`>= 0.035` (excluded, §3). The C2/C3 tally is reported on all non-degenerate
fills **and** on SHARP fills alone, both printed, neither promotable over the
other after the fact.

### 4.3 Grouping is derived, never asserted

Per-series intervals with single-linkage clustering on interval overlap, as
`reconcile_observed_fees.py` already computes. A series contributing exactly
one fill is labelled **SINGLETON** and may not carry a cluster claim on its
own — round three's entire "not a venue constant" finding rested on two
singleton series and the result document had to say so.

### 4.4 The comparison against deployed code

`model_deployed` is an exact-`Decimal` reimplementation of `_model_a` —
`quantize(Decimal("0.0001"), ROUND_CEILING)` on `0.07·C·P·(1−P)`, maker branch
unused. Exact `Decimal` throughout, no binary floats: `0.07·20·0.15·0.85`
evaluates to `0.17850000000000002` in float and ceils to a false residual that
reads as a novel schedule. That already happened once (round-three §S12b).

**Side-check D1, declared now so it is not discovered and folded in.**
`calculate_fee(price_tenths, contracts: int, ...)` takes an **integer** count.
The capture contains fractional `count_fp`. The result document records what
the deployed entry point does when handed the observed values — and if the
answer is that a sub-1 count reaches the `contracts <= 0` branch and returns
`0.0`, that is the module's own *"unreadable must never resolve to zero"* rule
broken in the risk path, and it is **reported as a defect with its own
follow-up**, not absorbed into the fee verdict.

---

## 5. The cuts, fixed here

1. **Series** = ticker prefix before the first `-`. Every series gets its own
   interval and its own `n`. No pooling into "baseball"/"non-baseball" for
   classification — round-three §10's prohibition on pooling across categories
   is carried forward verbatim and binds this document.
2. **OLD vs NEW**, per §3's timestamp rule.
3. **Sharpness** — SHARP / BLUNT / DEGENERATE, per §4.2.
4. **Taker/maker** and **buy/sell** — expected degenerate, reported anyway.

**No other cut.** In particular, no cut on price band, size band, notional
band, date-within-window, or in-play status may be introduced during the
analysis. Round three refuted H-SIZE, H-PRICE and H-NOTIONAL as *registered*
hypotheses; re-cutting on them now, after the coefficients are known, is a
different act.

**Printed before any effect size, in this order** (CLAUDE.md, "read `n` before
the effect size"): total rows, rows per series, rows per OLD/NEW, rows per
sharpness class, multi-fill order count, and **the largest single
contributor's share of total fees** — that last one printed *before* the
pooled rate, never after it.

### 5.4 The attribution rule, fixed before the split is seen

| what NEW fills contain | verdict on H-SERIES vs H-SPORT |
|---|---|
| no two series inside one sport disagreeing | **NOT SEPARATED BY THIS DESIGN**, as round three |
| two series inside one sport disagreeing | H-SPORT **refuted**; report the disagreeing pair |
| a third `k` cluster, contained in neither `(0.0349, 0.0351]` nor `(0.0699, 0.0701]` | **NOVEL / UNEXPLAINED.** Reported as unexplained. **No seventh model is fitted here** — it requires a fresh registration |

---

## 6. The 4.03% decomposition, registered as an identity

The pooled figure is known (§0) and distinguishes none of its three rivals.
What follows is arithmetic, fixed before the parts are seen.

Under `fee = k·C·P·(1−P)` and `stake = C·P`, ignoring the grid:

```
fee / stake  =  k · (1 - P)          <=  k,   for every position
```

So, **per position**, at coefficient `k`, the falsifier is:

```
fee_i / stake_i  >  k · (1 - P_i)  +  0.0001 / stake_i        -> not explained by k
```

the second term being the per-order ceil slack, which is large in *rate* terms
on tiny stakes and negligible on large ones.

**Pooled**, with `w_i = stake_i`:

```
rate  =  sum(fee) / sum(stake)   <=   k · weightedmean(1 - P)  +  n·0.0001 / sum(stake)

k_required  =  ( rate  -  n·0.0001/sum(stake) )  /  weightedmean(1 - P)
```

The result document prints, in this order: `n`, the largest contributor's share
of `sum(fee)`, the stake-weighted price distribution, `weightedmean(1 − P)`,
`k_required`, and only then `rate`. The three rivals ADR 0043 names are then
read off directly:

- **price mix** — visible as `weightedmean(1 − P)` well above 0.5;
- **a settlement charge (H4)** — visible as a residual that survives after
  `k_required` is compared to the per-series coefficients, **and** it is the
  only rival §8.3 can act on;
- **`k = 0.035` not surviving 25 fills** — visible as `k_required` above 0.035
  *with* per-position falsifiers firing on baseball rows.

**The stake denominator** is the non-zero of `yes_total_cost_dollars` /
`no_total_cost_dollars` on the settlement row. If that key is absent from the
wire, the rate is reported **NOT COMPUTABLE** and no substitute denominator is
constructed. Unreadable resolves to `None`, never to a number that looks fine.

---

## 7. The decision rule, verbatim

```
Q(a)  C1b  25 of 25 fills match model_deployed within 1e-9
          -> DEPLOYED MODEL CONFIRMED on this capture.
      C1b  any fill differs by more than 1e-9
          -> DEPLOYED MODEL MISMATCHED. Report the ratio distribution per
             series. No code change is authorised by this document.
      C1   any fill where fee_cost > model_deployed + 1e-9
          -> STOP THE LINE. The deployed model UNDERCHARGES, which is the one
             direction fees.py has never chosen. Reported at the top of the
             result document, above every other finding.

Q(b)  Scored on NEW fills only (created_time > 2026-08-14T23:59:59Z),
      excluding DEGENERATE fills, on admissible intervals never points.
      C2  every new KXMLB* fill's interval contains 0.035
          -> k = 0.035 SURVIVES OUT-OF-SAMPLE on baseball, over 8 days.
      C2  any new KXMLB* fill's interval excludes 0.035
          -> k = 0.035 REFUTED as a uniform baseball rate over this window.
             Name the fill's series, C and P. Do not rescue it with a cut.
      zero new KXMLB* fills
          -> NOT TESTABLE. Old fills may not be substituted.
      C3  same, with 0.070, on new non-KXMLB* fills. SINGLETON series carry no
          cluster claim alone.
      any interval containing neither 0.035 nor 0.070
          -> NOVEL / UNEXPLAINED. No seventh model is fitted here.

Q(c)  H4 is UNANSWERABLE FOR CONFIRMATION with this data and this is registered
      before the look: no balance observation brackets any of the 22
      settlements, and deposit history is unavailable, so a deposit and a
      settlement charge are perfectly confounded.
      C4  any settlement fee_cost strictly greater than the summed fill
          fee_cost for that market
          -> H4 REFUTED: settlement is not free. This is the design's only
             power against H4 and it is one-sided.
      C4  equality on every settled position
          -> NON-DISCRIMINATING. Recorded as a data-integrity check only. It
             may NOT be written as "H4 closed", "settlement appears free", or
             any phrasing that reduces the caveat in ADR 0027. The headroom
             stays an upper bound.

Q(d)  Feeds ADR 0043's deferred question; this document PROPOSES, it does not
      decide, and the decision remains partner's and an ADR.
      LICENSED to propose that hand fills count toward _fee_model_verified
          only if C1b holds on 25 of 25.
      FORBIDDEN otherwise. If any fill mismatches, the recommendation is
          "fix the model first"; admitting mismatching rows would pin a
          live-trading interlock at MISMATCH as a side effect of a logging
          change, which is the exact failure ADR 0043 exists to prevent.
      FORBIDDEN in every branch: proposing a one-sided tolerance that counts
          only undercharges, or widening FEE_MATCH_TOLERANCE_DOLLARS. Both are
          gate loosenings wearing a bug fix's clothes.

DURABILITY  No branch above licenses changing TAKER_COEFFICIENT. The capture
      spans 8 days and ends 3 days after the last prior observation; the
      registered requirement is a window >= 3-4 weeks after 2026-08-14.
```

---

## 8. Multiplicity, counted now

Pre-declared comparisons: **25** (C1/C1b) + **12 new fills x 6 frozen candidate
models = 72** (C2/C3) + **22** (C4) = **119**, plus one per-series interval per
series observed (six series seen to date; if more than ten appear, that is
reported before any cluster claim).

**The chance-of-a-false-finding frame does not apply and I will not manufacture
one.** These are exact comparisons against exact grids; noise does not produce
a spurious match. **The real multiplicity risk here is model search**, and it
is controlled by freezing the candidate set at exactly the six already in
`scripts/reconcile_observed_fees.py`:

```
k035 order ceil 1e-4   k070 order ceil 1e-4
k035 contract ceil 1e-4   k070 contract ceil 1e-4
k035 order half-up 1e-4   k070 order ceil CENT
```

**No model may be added after the file is opened.** Model B (per-contract,
nearest cent) stays in the reported set as a **refuted control** — a harness's
job includes showing a dead model failing.

The second risk is a single BLUNT fill widening a series interval until it
looks novel. Controlled by §4.2's sharpness classes and §4.3's SINGLETON label,
both fixed before the look.

**This record will be looked at more than once as it grows** — the fills
endpoint keeps returning rows and the capture will be re-taken. This is **one
look at one frozen capture** (§9). A future look at a larger capture is a new
registration, not a re-read of this one, precisely because a threshold
re-evaluated on an accumulating record crosses eventually with probability 1.

---

## 9. The stopping rule

**One look at the capture as it stands.** 25 fills, 22 settlements. No re-poll
for more rows before, during, or after the computation, and no second pass with
a different cut.

If the capture files cannot be read at all, `scripts/capture_fills_fixture.py`
may be re-run **once, before the first computation**, and the delivered row
count is recorded in the result. Any row in that re-capture beyond the
registered 25 / 22 is reported as **OUT OF POPULATION** with its count, and is
excluded from every claim in §2. After the first computation the population is
frozen absolutely.

**The named temptations, written down so they are recognisable in the moment:**
re-taking the capture because a series looks thin; adding a seventh model
because one row does not fit; moving the OLD/NEW boundary because the
out-of-sample set contains no baseball; reporting the pooled rate before the
largest contributor's share.

---

## 10. Producer, provenance and privacy

Every figure in the result document is re-derived by a **committed,
re-runnable** script — `scripts/reconcile_observed_fees.py` extended, or a new
`scripts/analyse_hand_fill_fees.py` — reading only the two capture files. No
network, no database, no credential. **A hand-typed table with no producer is a
hand-constructed payload wearing a measurement's name**, which is why that
script exists at all.

The captures stay gitignored. The result document contains **no** `fill_id`,
`order_id`, `trade_id`, `subaccount_number`, `user_id`, or ticker suffix
identifying a position's side. Series prefixes, counts, prices and fees only.
`kalshi-cockpit` publishes on push.

---

## 11. What this cannot establish, drafted before it is run

- **Maker fees.** Zero maker fills exist in the capture. `MAKER_COEFFICIENT`
  and the 50.44% maker bar are untouched by anything here.
- **Sells and early exits.** Zero `action = sell` fills have ever been
  captured. The exit-fee path has no observed wire shape and this does not give
  it one.
- **Combos.** No combination-market fill exists. **ADR 0012 §5's combo fee
  model stays unverified**, and `FEE_MATCH_TOLERANCE_DOLLARS`'s recorded
  limitation — that a correct combo model would also trip
  `fee_model_verified` — is unaddressed.
- **Durability.** Eight days of one account. A promotional or temporary rate
  is not excluded and this window cannot exclude it. Kalshi's sports schedule
  demonstrably changed at least once in the preceding six months.
- **Which attribute carries the rate split.** Sport, series, and a per-market
  liquidity or maker-programme tier remain admissible. A per-market tier is
  weakened by depth (ADR 0028) and closed by nothing.
- **H4 confirmed.** Only refutation is reachable (§7). The 0.63-point cost
  headroom stays an **upper bound**.
- **Anything off the observed grid** — prices, sizes, in-play fills, series not
  present, and the pre-July-2026 schedule.
- **Anything about edge, CLV, P&L, or Joe's skill.** These are 25 bets he
  placed for his own reasons. `actionable` and ADR 0038 are untouched. The
  +$1.03 is out of population and does not appear in the result document.
- **That the venue charges what it charged this account.** Every claim is about
  this account's fills. An account-level or promotional rate is not
  distinguishable from a venue rate by a single account's record, and the word
  used throughout is *these fills*, not *Kalshi*.

---

## 12. What is built if it clears, what is killed if it does not

Stated in both directions, because a measurement that proceeds identically
either way is not decision-relevant.

| outcome | consequence |
|---|---|
| **C1b holds 25/25** | A proposal — to `partner`, as an ADR — that hand fills count toward `_fee_model_verified`. The condition becomes reachable and satisfiable for the first time. |
| **C1b fails** | That proposal is **killed for now**, and the open item becomes "fix the model, with its own ADR", ordered behind round-three §15's granularity/coefficient sequencing. `AND source = 'engine'` stays. |
| **C2 survives** | One of the two blockers on a reduced baseball coefficient is answered out-of-sample. The other — durability — is not, so still no code change. The next step is a dated fill >= 3–4 weeks after 2026-08-14, costing one contract. |
| **C2 refuted** | `k = 0.035` is not a uniform baseball rate over this window; `TAKER_COEFFICIENT = 0.070` is vindicated as the conservative choice and the "50.88% true on baseball" line in CLAUDE.md is **wrong and must be corrected**, in the direction that costs the project headroom. |
| **C4 refuted (a settlement charge exists)** | ADR 0027's worst branch is realised: every `edge_after_fees_tenths` the tool prints is overstated, and the 0.63-point headroom shrinks by the charge. This would be the largest finding available here and it is the one branch nobody is hoping for. |
| **C4 equality throughout** | Nothing changes. H4 stays untested, the headroom stays an upper bound, and the result document says exactly that. |

**The honest reading of that table:** four of the six rows change no code and
no threshold. This measurement's value is concentrated in the Q(d) gate
recommendation and in the C4 refutation branch, and the Q(d) fork is
near-determined by what is already known (§0). **That is a finding about the
plan and it is recorded here rather than after the run.** It is still worth
running: it is ADR 0043's named condition, it costs one script and no credits,
and the C4 branch is the only reachable test of the assumption underneath every
EV number the tool prints.
