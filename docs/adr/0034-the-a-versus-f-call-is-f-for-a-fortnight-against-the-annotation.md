# ADR 0034 — The A-versus-F call is F for a fortnight, made against the annotation

**Date:** 2026-08-16
**Status:** Accepted
**Cites and discharges:** `0023-the-a-versus-f-call-is-deferred-until-the-fee-attribution-resolves.md`
**Relates to:** ADR 0021 §8, ADR 0027, ADR 0028, ADR 0032
**Registration governing the re-read:** `docs/measurements/2026-08-09-preregistration-clv-signal-test.md`

## 1. The decision

> **Option F is taken, for about a fortnight, and it is a choice made *against*
> ADR 0023's own ranking rather than one compelled by it.** ADR 0023's deferral
> is discharged on branch (a); this is the "new ADR that cites this one" §6
> requires.
>
> **The re-read is bound to the CLV signal test exactly as already registered** —
> `G >= 300` scored game clusters on the registration's §2 population, its
> `always_valid_multiplier` boundary, and its **0.40** threshold. No new
> threshold, no new floor, no interim declaration.
>
> **What changes versus ADR 0023 is only which 300 is counted:** the *gate's*
> 300 **actionable** games (unreachable — §4) is not the re-read's trigger. The
> registration's 300 **scored** clusters is, and on this record's own rate that
> is roughly two weeks away.
>
> **If the registered test declares NO SIGNAL, option A is taken with no further
> decision.** This ADR authorises no second deferral.
>
> **This does not authorise any change to `calculate_fee`.** See §6.

## 2. Why F, stated honestly as a choice

**The registered rule does not elect F, and an earlier draft of this ADR claimed
it did.** ADR 0023 §5.3 says *"F's liveness **requires** both (i) … and (ii)"* —
a **necessary** condition. Both terms are indeed met by round three: `k` is
pinned to `(0.034969, 0.035008]` on `KXMLBGAME`/`KXMLBSPREAD`, and `H-NOTIONAL`
is refuted by `W`. That makes F **admissible**. It does not make it elected.

**And ADR 0023's own ANNOTATION §A2 ranks the branches the other way:**

> *"Branch (a)'s best case is 'step 2 applies at these cells' — which is §5.4's
> 3-of-60, ~11–14 months. Branch (b), 26 of 32 vectors, kills F outright.
> **Every branch of the trigger points at A, differing only in confidence.**"*

So F is chosen **against** the only ranking that document contains, and the
burden is on this ADR to say what changed. Two things did:

**(a) The record now accumulates, and on 2026-08-10 it did not.** That is the
substantive change. ADR 0023 reasoned about a floor counted in *actionable*
games, which stood at 0 and had no mechanism to increment. The registration's
own floor is counted in **scored** clusters, which include suppressed rows, and
that count went from ~41 to **125** in six days — about 14/day. A test that
could not resolve is now roughly a fortnight from being able to. **The cost of
F is therefore two weeks, not the eleven-to-fourteen months §A2 priced.** At
that price, buying the registered answer beats taking A on a prior.

**(b) The instrument that reported the blocking number was reading the wrong
population.** `actionable = 0` was cited from `clv-coverage`, which filters on
`clv_scored_ms IS NOT NULL` while an actionable row is written before commence
— see `docs/measurements/2026-08-16-actionable-population-audit-result.md`. Part
of the pessimism ADR 0023 inherited was an artefact of that.

**Neither of these says an edge exists.** They say the question becomes
answerable in two weeks for the price of two weeks.

### 2.1 The half of `W` that cuts against F

§2 above uses `W` to refute `H-NOTIONAL`. The same observation carries a cost
that must travel with it: `W` is a **WNBA** fill charged at `k = 0.070`
(`2026-08-14-…round-three-result.md:154`, `:295`). So condition (i) — the
halved coefficient — **fails on WNBA**, which is a material share of the record.
ADR 0023 §9 already wrote this down and this ADR restates it rather than
quoting only the favourable half:

> *"The WNBA cell in round three is a risk to F, not a support for it."*

Related and unresolved: §5.3's "these cells" are 2026-08-10 rows re-scored under
a fee decomposition that **ADR 0028 has since superseded** (deci-cent grid,
hedge retired). Nobody has re-run that rescore under the measured model, so the
"4 rows surface" fact that made F live is **not current**.

## 3. What F is being asked to survive

**The three actionable rows are unseparated from zero, and two of them lost to
the close.** From the pinned record:

| id | market | `clv_tenths` @ h0 |
|---|---|---:|
| 4861 | moneyline | **−15.0** |
| 6174 | moneyline | **−15.0** |
| 7349 | prop | +20.0 |

The two moneyline rows are the *same claim* observed twice, so this is one
losing claim and one winning prop, not two-of-three. All three have
`anchored_on_sharp = 0` — soft-book consensus by silent fallback
(`devig.py:290-291`), a population ADR 0021 §8 measured at 423 rows producing 0
actionable. The actionable predicate carries no multiplicity correction while
the CLV mean does.

**The +0.637 raw slope is not encouraging, and the reason is not what an earlier
draft said.** That draft attributed it to `clv_tenths` and `edge_tenths` sharing
`entry_ask_tenths`. The coupling is real in code (`analysis/clv.py:174-177`,
`core/ev.py:171-180`) but it is **not** what produces the number — controlling
for `entry_ask_tenths` makes the slope *larger*, not smaller. What produces it:

| population (horizon 0) | rows | G | raw slope |
|---|---:|---:|---:|
| everything | 8,658 | 125 | **+0.637** |
| moneyline only | 4,611 | 125 | **−0.085** |
| prop only | 4,047 | **17** | **+0.878** |
| registration §2 population | 3,687 | 116 | see below |

**The pooled figure is carried entirely by props, across only 17 game
clusters** — and props are the pipeline ADR 0032 took off the schedule on the
day this dump was taken. The registration excludes `stale_odds` rows by name
(3,127 of the 8,658 here) precisely because *"part of the 'edge' is drift that
has already happened. Contaminates the **regressor**."*

**On the registered population the slope is small and its SIGN IS NOT
REPRODUCIBLE.** Two independent computations over near-identical populations
(3,687 vs 3,684 rows) returned **+0.102** and **−0.109**. A statistic whose sign
flips between implementations at n≈3,685 is not decision-bearing in either
direction, and the disagreement is recorded here rather than resolved by picking
one. **Resolving it is a precondition of the re-read**, not a detail.

None of the four numbers above is `beta`: no `gamma * half_spread_tenths`, no
game clustering, and `market_type` is **not a registered cut** — the split is a
diagnostic showing the pooled number is not homogeneous, not a finding about
moneyline pass-through.

## 4. The gate's 300 is not the re-read's 300

The gate's floor counts **actionable** games (`gate.py:549-574`,
`POPULATIONS["actionable"]` at `:323`, `config.py:694`). Live, that is **2 game
clusters** against ~144 scored, in the record's whole life.

**But "unreachable on any branch" would be an `n = 2` claim and this ADR does
not make it.** Both clusters landed in the last ~21 hours of the record. The
whole-life rate implies ~1,500 days; the recent-window rate implies 150–300,
which is *shorter* than ADR 0023's 11–14 months. Two events cannot support
"unreachable", and the comparison is not clean either: ADR 0023's 3/60 was
measured under **step 2**, the live 2/144 under the **deployed 0.07** model, so
the live figure understates its own branch.

What is true and sufficient: **the gate's floor is a poor trigger for a
measurement decision**, because it counts a population the measurement does not
need. The registration's floor counts scored clusters, is at **125** today,
and moves at ~14/day. That floor is doing the work here; the gate's floor is
untouched and remains an interlock on live trading. **No roadmap may depend on
the gate opening.**

## 5. The re-read uses the registration unchanged, and three things are owed first

**No new rule is created by this ADR**, and an earlier draft created three. It
proposed stopping at `beta <= 0` at `G = 186` against a threshold of `0.64`.
Each of those conflicts with
`docs/measurements/2026-08-09-preregistration-clv-signal-test.md`:

- *"A look taken when `G < 300` may report point estimates and intervals. **It
  may not declare SIGNAL, BUG or NO SIGNAL.**"* Stopping the line at G = 186 is
  a NO SIGNAL declaration under another name.
- The registered threshold is **0.40**, and the file marks it *"the threshold of
  0.40 itself STANDS."* `0.64` was unsourced — its stated derivation
  `6.3 / 9.81` has a numerator from ADR 0028 and a **denominator that appears
  nowhere in the repo** and does not reproduce (median positive `edge_tenths`
  at h0 is 9.65 pooled, 7.91 on the registered population, 14.55 on moneyline).
- The decision statistic is `beta_hat > m * se_cluster`, with
  `m = always_valid_multiplier(G, tuning=300)` — **a bare point estimate against
  zero is the exact fault Amendment §A3 was written to remove.**
- *"An amendment made after a look and not recorded voids the registration."*
  An interim rule, if ever wanted, is an amendment **written into that file,
  dated, before the next look** — never a clause in an ADR.

**Owed before the first look, and none of it is optional:**

1. **P1 has never been run.** The registration: *"If that fraction is below
   0.90, the primary analysis does not run."* Half-spread coverage is
   unmeasured.
2. **No `beta` estimator exists.** There is no `half_spread`, `beta_hat` or
   partial-slope code anywhere under `backend/`. The rule currently binds to a
   statistic nothing computes.
3. **The sign disagreement in §3 must be resolved**, and the cluster key stated:
   this record gives **G = 125** under ADR 0029's gate key and **G = 210** under
   the registration's own `COALESCE(event_ticker, ticker)` — a 68% difference.
   On the registered §2 population it is **116**, and under §7's modal
   `strategy_config_version` rule roughly **84**. "The whole scored population"
   is not what `beta` runs on and this ADR does not claim it is.

**A population change also needs ruling on:** 4,047 of the 8,658 horizon-0 rows
are props, a product introduced after the registration was written and
decommissioned by ADR 0032 since. The registration restarts `G` if the
population definition moved. Whether it did is `pre-registrar`'s call.

## 6. What this ADR does NOT authorise

**It does not change `calculate_fee`.** ADR 0023 §6, restated because the
temptation is real and was acted on in draft:

> *"Round three does **not** replace `calculate_fee` and this ADR does not
> authorise it to. Replacing `calculate_fee` needs a rate, an attribution, a
> rounding rule, a scope, coverage of the maker path, and its own ADR and
> registration."*

| requirement | state |
|---|---|
| a rate | **have it** — `k ∈ (0.034969, 0.035008]` |
| an attribution | **partial** — H-SERIES/H-SPORT unseparated; they agree only on the two measured series, and `W` shows WNBA at 0.070 |
| a rounding rule | **have it** — deci-cent, ADR 0028 |
| a scope | **decidable** — `KXMLBGAME` + `KXMLBSPREAD`, taker, pre-game |
| coverage of the maker path | **absent** |
| its own ADR and registration | **absent** |

**`TAKER_COEFFICIENT = 0.07` therefore stands, and it is knowingly about 2× the
measured rate on the baseball series.** That overcharge is **not conservative**
— it suppresses rows that may be real and biases every downstream measurement
toward finding nothing. It is an error with a known sign, tolerated only because
correcting it without the maker path would trade one unmeasured constant for
another.

**Durability is the other reason to wait.** Every `k = 0.035` observation lies
inside **four days**, and this account's settlement record shows 11 of 11
single-game fees from 2025-11-27 to 2026-02-09 at `k = 0.07` on the whole cent.
A promotional or temporary MLB rate is not excluded. **One fill outside that
window settles it**, and that is the cheapest open question in the repo.

## 7. What this decision does not establish

- **Nothing about whether an edge exists.** F buys two weeks of measurement, and
  §3 records that the only actionable rows with CLV lost 1.5c to the close.
- **The +0.637 is not evidence of pass-through.** It is carried by 17 prop
  clusters on a decommissioned pipeline, and includes 3,127 `stale_odds` rows
  the registration excludes by name for manufacturing exactly this sign.
- **`G = 125` is not the registered `G`.** The registered §2 population is 116,
  ~84 under the modal-config rule, and 210 under the registration's own cluster
  key. Any "we are N% of the way there" sentence must name which.
- **P1 has never been run and no `beta` estimator exists**, so the re-read is
  not merely un-run — it is currently un-runnable.
- **No per-group robustness is established.** Leave-one-cluster-out swings the
  pooled slope by up to 0.11 on a single prop event.
- **The spurious-`beta` baseline of 0.16 is withdrawn by its own registration**
  (ADR 0006 measures the pre-game spread at 1.00c at every percentile, so
  `Var(half_spread) ≈ 0` and the registered spurious slope is ≈ 0). It may not
  be cited as a reason a positive slope is expected.
- **Nothing about live trading.** The gate is unmoved.
- **Nothing about the information line.** Lineups, weather and news change
  `fair_probability` and move neither validation denominator. The registered
  test gates that question too.
