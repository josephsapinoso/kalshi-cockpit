# 0023 — The A-versus-F call is deferred until the fee attribution resolves, with an expiry

**Date:** 2026-08-10
**Status:** Accepted. This ADR **makes** a decision — it defers a second one, on
a stated trigger, with a stated expiry and a stated default.
**Owns:** the disposition of `0021-the-consensus-only-strategy-is-refuted` §8
options **A** and **F**, and nothing else.
**Defers entirely** to ADR 0018 on arming (`ORDERS_ARE_DRY_RUNS` stays `True`),
to ADR 0022 on the quarantined modules, and to CLAUDE.md on `elo.py`. Options
**B**, **C** and **D** of ADR 0021 §8 are untouched and are not ranked here.
**Number:** 0023, not 0020 — **0020 stays reserved for the `stale_odds`
scrape-clock ADR** that ADR 0021 §7.5 queues and ADR 0022 §Number restates.

Evidence, in the order it is relied on:

- [`docs/measurements/2026-08-10-fee-model-fill-calibration-result.md`](../measurements/2026-08-10-fee-model-fill-calibration-result.md)
  — verdict **H3−**, both registered fee models refuted at all four cells.
- [`docs/measurements/2026-08-10-fee-model-rescore-result.md`](../measurements/2026-08-10-fee-model-rescore-result.md)
  — the pinned record re-scored under all three fee models.
- [`docs/measurements/2026-08-10-preregistration-fee-rate-attribution-round-three.md`](../measurements/2026-08-10-preregistration-fee-rate-attribution-round-three.md)
  — registered, **unrun**, hard expiry 2026-08-31 (UTC).
- [`docs/measurements/2026-08-10-clean-shortfall-pull.json`](../measurements/2026-08-10-clean-shortfall-pull.json)
  — `pin = 1564`, pulled 2026-08-10T05:07:23Z. Every count in §3 marked
  *[re-derived]* was computed from this file for this ADR, offline.

---

## 1. The decision

> **The choice between ADR 0021 §8 option A (stop the consensus-only line, keep
> the recorder and the measurement discipline) and option F (keep recording and
> re-read at a larger `n`) is DEFERRED. It is made when the fee-rate attribution
> resolves, and not before. If the attribution does not resolve — by an `H-NONE`
> or `B4-DETECTED` verdict on round three, or by round three's own hard expiry
> of 2026-08-31 (UTC) passing with the round unrun — then **option A is taken by
> default** on that date, without a further decision and without re-reading this
> file.**

**This is a decision, not its absence.** What is being recorded is that the
A-versus-F question is *not currently answerable*, that the thing which would
answer it is named and already registered, and that the deferral **terminates on
a date** rather than persisting until somebody notices it. ADR 0022 §4.1 item 4
already made the same move for a quarantined module — *"parking something
without a revival condition is how it becomes permanent by default"* — and this
is that rule applied to a line of work instead of to a file.

The arithmetic behind the deferral is in §4 and §5. It is expensive to re-derive
and a future session will otherwise redo it, which is the whole reason this
document exists.

---

## 2. Why the question is open at all

ADR 0021 refuted the **consensus-only** strategy on the evidence that zero clean
rows clear the deployed fee, `max E1 = −2.0534` tenths. Its §8 lists six options,
unranked, and says the call is Joe's.

Since then:

- **Option E ran.** Six real fills. The verdict is **H3−**: every observed fee is
  below `min(model_a, model_b)`, so *both* registered models are refuted and no
  third is adopted. `core/fees.py` is unchanged and `CLAUDE.md`'s 52.00% bar is
  unamended, deliberately — H3− kills two models without electing one.
- **The record was re-scored under three fee models.** ADR 0021's conclusion
  survives one of them and falls under another.
- **B, C and D are each a different project** with a different question, exactly
  as ADR 0021 §8 says. Nothing here re-opens them.

So **A and F are the two live options**, and which of them is correct depends on
a quantity that is currently unknown.

---

## 3. The state of the record

### 3.1 What the gate counts, and where the predicate is

`actionable` is `backend/gate.py:323`:

```
r.suppressed_reason IS NULL AND r.reference_contracts > 0
```

Clustered into independent games at `backend/gate.py:438-461`, on
`COALESCE(m.event_ticker, r.ticker)` (`:440`), over rows satisfying

```
r.clv_scored_ms IS NOT NULL AND r.clv_tenths IS NOT NULL
  AND r.clv_horizon_hours = :horizon
```

(`:446`, `:456`), with `:horizon` bound to `DEFAULT_HORIZON_HOURS`, which is
**`0.0`** at `backend/analysis/clv.py:76`. The floor is **300 independent
actionable games** — `backend/config.py:561`, overridable by
`LIVE_GATE_MIN_SCORED_RECOMMENDATIONS` at `:567`.

*(The brief this ADR was written from cited the horizon clause as the literal
`clv_horizon_hours = 0.0`. It is a bound parameter whose value is 0.0. Same
predicate; the citation is corrected because ADR 0019's citation rule is what
lets a future session re-check a line in thirty seconds.)*

### 3.2 The counts

**[re-derived from `pin = 1564`, offline, for this ADR]** — 1,564 rows spanning
`created_ms` 2026-08-07T19:33:27Z → 2026-08-10T05:06:58Z, **57.6 hours**:

```
actionable rows                                    0  of 1,564
clean (unsuppressed) rows                        614  in 59 game clusters
suppressed rows                                  950
distinct game clusters, whole table               60
KXWNBAGAME rows                                  422  = 27.0%

new distinct game clusters first seen, by UTC day
  2026-08-07   32       (the standing slate at first boot, not a day's intake)
  2026-08-08   10
  2026-08-09   18
  2026-08-10    0
```

**[reported by the partner from a live read at 2026-08-10T16:47Z; NOT
independently verified here — this lane has no production access]**

```
actionable      0 games /   0 rows      (also 0 twenty-four hours earlier)
pooled         29 games / 532 rows
no_edge        20 games
suppressed     25 games
record life    69 hours
```

Two of those cross-check against sources this lane *can* read, and both hold:
the 69-hour life is the pin's 57.6-hour span carried forward to 16:47Z (69.2 h),
and the 532 scored rows reproduce `tasks/NEXT.md:1600`'s horizon-`"0"` count of
532. The rest is taken on report.

**The 29 is the *scored* count and is not the record's game count.** ADR 0021 §2
is explicit about this — *"Not 29"* — and the two numbers answer different
questions. 60 game clusters have entered the record; 29 of them carry a
horizon-0 CLV score. When stating how much evidence the refutation rests on, the
form is still **`59 games across 34 recording instants`**.

**`actionable` has been 0 for the entire life of the record**, on both readings.

---

## 4. The naive case against F, corrected

**The naive form:** zero times any number of further slates is zero. True, and
insufficient, because a census of 0 is not a rate of 0.

**Steelmanned.** Treat each game cluster as a trial and put an exact one-sided
95% upper bound on the per-game surfacing rate. This is a Clopper-Pearson bound,
not a normal approximation, so CLAUDE.md's *"≥5 expected outcomes on each side"*
rule does not bar it — but the rule is why the normal approximation is **not**
used and why the bound is stated exactly.

```
0 actionable of 60 game clusters
  95% one-sided upper bound   1 - 0.05^(1/60)  =  4.87%
new games per slate            10 and 18 on the two full days; take 18, the generous one
  upper bound, actionable games per slate       0.88
  slates to reach 300 games                      342   ~11 months of uninterrupted daily slates
```

**Two corrections to the version of this arithmetic that came into this ADR.**

1. **The denominator is 60 games, not ~200.** A denominator of ~200 gives a
   1.49% bound, ~0.28 actionable games a slate, ~1,070 slates and "roughly three
   years". No unit in this record has ~200 members: the game clusters number 60,
   the clean clusters 59, the registered observations 323, the claims 118, the
   sweeps 34. The correction runs **against** the case for A — the horizon is
   ~11 months rather than ~3 years, three times shorter — and it is made anyway.
2. **The bound is if anything too tight.** ADR 0021 §2 puts the *dependence* unit
   at the sweep, not the game: every row in a sweep is priced off one odds
   snapshot. Games within a sweep are not fully dependent either, so the honest
   denominator is bracketed by **34 and 60**, and the bound by **8.43% and
   4.87%** — 198 to 342 slates, roughly **6½ to 11 months**.

**The point estimate is not 11 months. The point estimate is never**, because
the observed rate is 0. The bound above is the *most* favourable reading the
record licenses, and it is offered to size the option rather than to forecast.
ADR 0021 §7.1 stands: *a null over 34 recording instants is a fact about 34
recording instants*, and none of this generalises to a single future row.

**A second filter sits on top and is not quantified here.** The 300 floor counts
*scored* actionable games. At the 16:47Z read only 29 of the 60 clusters carried
a horizon-0 CLV score. Some of the remaining 31 had simply not closed yet, so
that ratio is not a steady-state attrition and is **not** multiplied into the
figures above — but a surfaced game must also be scored before the gate can
count it, and that is a second gate F must clear.

---

## 5. Why §4 is NOT sufficient to kill F — the crux

`actionable = 0` is computed under the **deployed** fee model. That model is
**refuted**. So the death of F is conditional on a fee model that is itself
unresolved.

### 5.1 The decomposition

Reproduced verbatim from the fee-calibration result's own table:

```
                                             fee@50c  break-even  headroom  S_min E1   sizes?
deployed   0.07, ceil-to-CENT                $0.0200    52.00%      0.38     -2.0534     NO
step 1     drop the cent ceiling, keep 0.07  $0.0175    51.75%      0.63     +0.5466     NO
step 2     also halve the coefficient (MLB)  $0.0088    50.88%      1.50     +9.2466    YES
```

*(The source heads that column `S_min E1` and populates it with `max E1`. ADR
0021 §7.5 fixes `S_min = −max E1` exactly, so `S_min` under the deployed model is
`+2.0534`, not `−2.0534`. Reproduced as written, with the sign convention named,
because the table is the most quotable object in that document.)*

### 5.2 What each model does to `actionable`

| | `deployed` | `step 1` | `step 2` |
|---|---:|---:|---:|
| clean rows with `E1 > 0` | 0 of 614 | 3 of 614 | 9 of 614 |
| surviving the full deployed predicate | **0** | **0** | **4 rows / 3 claims / 3 games** |

**Under the deployed model and under step 1, `actionable` stays 0 and F has no
observed mechanism.** Under step 1 the refusal is over-determined: all three
positive rows are caught by `edge_within_method_noise` **and** by the reference
sizing floor, neither firing alone. The sizing floor is
`E1 > 4000·eff·(1−eff)/bankroll` tenths, supremum 1.0 tenth *at
`REFERENCE_BANKROLL_DOLLARS = 1000`*; the nearest row, `id 726`, would size at a
reference bankroll of **$1,822**. Both constraints are chosen config values, so
"dead under step 1" is a statement about this record under this configuration,
not a law.

**Under step 2, rows size and F is live.** Three claim-instants across three
games — and *claim-instants* is the honest noun: each surfaces at one of the
several instants at which it was observed, and the same claim reads as low as
−21.66 tenths at another.

### 5.3 Step 2 is not one condition, it is two

The rescore's §7(c) is the finding that most damages step 2, and it must travel
with any citation of "4 rows surface":

```
id 726  C=9  notional $4.05   ABOVE $3.00 -> HIGH rate (= step 1) -> does NOT surface
id 355  C=9  notional $4.95   ABOVE $3.00 -> HIGH rate (= step 1) -> does NOT surface
id 352  C=9  notional $4.95   ABOVE $3.00 -> HIGH rate (= step 1) -> does NOT surface
id  37  C=5  notional $2.75   inside ($2.70, $3.00]  -> UNDETERMINED
```

Under **rate-by-NOTIONAL** — the fifth live attribution, registered at round two
§C4 — the size that makes a row worth betting pushes it into the regime where the
coefficient that made it positive does not apply. **Three of the four step-2
survivors are not self-consistent under that attribution**, and the fourth is
undetermined.

So F's liveness requires **both**: (i) the coefficient at these cells is ~0.035
rather than ~0.07, **and** (ii) the attribution is not `notional`. Round three is
the instrument that separates those, which is why it is the trigger.

### 5.4 Even on its best branch, F is a year of slates

Not in the brief, and it is the number that most changes the shape of the choice.

Under step 2 — the **most favourable** live fee model — the record surfaces
**3 games of 60**. Carried forward on the record's own intake:

```
surfacing rate, step 2, point estimate        3 / 60 = 5.0%
new games per slate                           14 to 18
actionable games per slate                    0.70 to 0.90
slates to reach the 300-game floor            333 to 429   ~11 to 14 months
```

Under `H-NOTIONAL` that rate falls to between 0 and 1 games of 60, and the floor
recedes past any horizon worth planning against.

**Labelled, because it is a projection and not a forecast:** this carries a rate
measured on 60 games in one week of one August in two leagues onto future slates,
which ADR 0021 §7.1 forbids treating as generalisable. It is offered to size the
option — F on its best branch is still about a year — not to predict a date.

---

## 6. The trigger

> **The A-versus-F call is made when the fee-rate attribution resolves, and not
> before.**

The instrument is
[`2026-08-10-preregistration-fee-rate-attribution-round-three.md`](../measurements/2026-08-10-preregistration-fee-rate-attribution-round-three.md),
registered and unrun. Six orders, $4.57 of stake, one 120-minute window on one
calendar date. It declares one of five attributions — `H-SERIES`, `H-SPORT`,
`H-SIZE`, `H-PRICE`, `H-NOTIONAL`, some of which cannot be separated from each
other — or it does not.

**On a declared attribution:** §5.3's condition (ii) is answered, §5.2's
step-1-versus-step-2 question is answered for the cells the record sits in, and
the A-versus-F call is made on that verdict, in a new ADR that cites this one.

**What the trigger is not.** Round three does **not** replace `calculate_fee` and
this ADR does not authorise it to. The registration is explicit: replacing
`calculate_fee` needs a rate, an attribution, a rounding rule, a scope, coverage
of the maker path, and its own ADR and registration, and *"this round delivers at
most one of the six"*. What it delivers is enough to decide A versus F, and
nothing more.

---

## 7. The expiry, and the default

**A deferral with no expiry is how a line of work dies quietly.** This one has an
expiry, and the expiry has a default that is not "keep deferring".

> **EXPIRY.** This deferral ends on the earlier of:
>
> **(a)** the round-three result landing with **any of the five attributions
> declared** — the A-versus-F call is then made on that verdict, per §6; or
>
> **(b)** the round-three result landing with **`H-NONE`** or
> **`B4-DETECTED — ATTRIBUTION NOT READ`**, **or** **2026-08-31 (UTC)** passing
> with round three unrun — that being the registration's own hard expiry, after
> which any attempt is a new registration.
>
> **On branch (b), option A is taken.** No further deferral is authorised by this
> ADR. Re-opening A-versus-F after (b) requires a new ADR that states what
> changed, and "we should look again" is not a thing that changed.

### 7.1 Branch (b) is the modal outcome, and the count matters

Round three's own power analysis, §7.3, over all 32 reachable outcome vectors:

```
6  of 32   declare an attribution                       -> branch (a)
26 of 32   leave every attribution dead                 -> branch (b)
   of which R = HIGH (16 vectors)   B4-DETECTED, attribution not read
   of which R = LOW  (10 vectors)   genuine H-NONE
```

**Correction to the brief this ADR was written from:** it stated *"26 of 32
outcome vectors return H-NONE"*. They do not. **26 of 32 leave every attribution
dead**; only **10** of those are declared `H-NONE`, and **16** are
`B4-DETECTED`. Both land on branch (b), so the expiry is unaffected — but
`B4-DETECTED` is the *worse* of the two and deserves its own name here.
`B4-DETECTED` means the schedule moved: round three's §7.5 suspends *"every
downstream use"* of the round-one `k` intervals, which includes the step-1 /
step-2 decomposition of §5.1. On that branch the arithmetic framing this whole
ADR is not merely unresolved — it is void. That argues for the default rather
than against it.

The registration itself names the sharpness as deliberate: *"the measurement is
far more likely to refute than to confirm"*, and *"sixteen of the 32 vectors are
`R = HIGH` … that is not a defect; it is the detector working."*

### 7.2 Why the default is A

**The partner's position, recorded as given:** if round three returns H-NONE, A
is taken by default, because at that point the project has spent two rounds and
real money and still cannot say whether its own bar is 52.00% or 50.88%, and
continuing to accumulate a record scored against an unknown bar is not
evidence-gathering.

**The conclusion is right. The stated reason is too strong, and the corrected
reason is stronger.** After H-NONE the project *can* say what the bar is at one
cell: round one measured `KXMLBGAME`, `C = 1`, `P = 0.48` at **$0.0088**, twice
(F4 and the unregistered `TEXLAA-LAA` fill). H-NONE would not unmeasure that. It
would leave unresolved whether that rate **transfers** — to the multi-contract
sizes the surfacing rows imply (§5.3), to WNBA (§8), and to other prices. That is
the correct form of the argument, and it still supports A: F's whole proposition
is that accumulation converts into evidence, and a record scored at a rate that
is unlicensed **at the sizes it would trade** does not accumulate evidence about
whether the strategy can pick. It accumulates rows.

**Three further reasons the default is A rather than F:**

- **A is reversible and cheap; the deferral is not.** A keeps the recorder and
  the measurement discipline — ADR 0021 §6 lists them as the assets they are.
  Taking A closes a *claim*, not a pipeline. Nothing about A prevents a later ADR
  from re-opening the question on new evidence; what it prevents is the question
  sitting open, unowned, indefinitely.
- **F on its best branch is still about a year of uninterrupted daily slates**
  (§5.4), and the record has not accumulated a single new game cluster since
  2026-08-09 (§8).
- **The hedge already has a standing instruction against becoming permanent.**
  `tasks/lessons.md`, 2026-08-06: *"do not let this hedge become permanent, and
  do not wait for it to resolve itself."* Two rounds have now been spent on
  exactly that instruction. A third round of deferral would be waiting for it to
  resolve itself.

**Where this could be wrong.** If round three returns H-NONE for a *reachability*
reason rather than an evidential one — no qualifying market on the board, cells
reported `NOT ATTEMPTED` — then branch (b) fires on an instrument failure rather
than on a finding, and taking A would be reading a null instrument as a null
result. Round two died exactly that way, on availability rather than on budget.
The registration's own `PARTIAL — CONSISTENT WITH, DOES NOT EXCLUDE` qualifier and
its `NOT ATTEMPTED (DID NOT FILL)` label exist to make that distinguishable in
the verdict line. **A verdict line carrying `NOT ATTEMPTED` on two or more cells
should be read as the instrument failing, and the honest response is a new
registration, not option A.** This is the one carve-out, and it is named here
rather than invented later.

---

## 8. The second condition, which is independent and must not be conflated

**There is a second reason F is not currently running, and it has nothing to do
with the fee model.**

Odds fetching stopped at **2026-08-09T23:37:15Z** and ran 17+ hours unnoticed
behind a green health check (`tasks/NEXT.md:51-63`; the same instant is the
maximum `fetched_ms` in the anchoring census,
`2026-08-10-sharp-anchoring-on-the-record-result.md:187`). The loop stayed alive
throughout, writing ~5,000 quote rows an hour. **Every `recommendations` row
written in that window carried `stale_odds`, and zero new game clusters entered
the record on 2026-08-10** — verified offline on the pin, and unchanged at the
partner's 16:47Z read.

> **The cause is not established, and none is written here on purpose.** This
> repo has a recorded misdiagnosis of exactly this shape: ADR 0014, a frozen
> counter blamed on the sweep scheduler when the slate was empty. `tasks/NEXT.md`
> fact 4 adds why the diagnosis is hard — a refused sweep leaves no trace in any
> table in the schema, so silence is indistinguishable from a system that never
> looked. Candidate explanations must be separated by evidence before one is
> written down. ADR 0020, still reserved and still unwritten, is the closest
> owner.

**Two conditions, both currently unmet, and relaxing one does not relax the
other:**

1. The fee model must resolve in F's favour (§5, §6).
2. The record must actually accumulate.

Even if round three declared `H-SERIES / H-SPORT` tomorrow and step 2 applied at
the cells that matter, **F would still require a recorder that is producing new
game clusters, and as of tonight it is not.** Nothing in this ADR is a diagnosis
of, or a fix for, condition 2. It is recorded so that a future session reading a
resolved fee model does not conclude that F is therefore running.

---

## 9. Even under step 2, the rescue is not clean — and the WNBA figure is not the one it looks like

Stated before anyone gets excited about §5.2's step-2 column.

**The whole-table counts** (rescore §2's checksum row): rows carrying a positive
net edge, under `deployed` / `step 1` / `step 2`, are **137 / 158 / 206**, of
which **55 / 66 / 85** are `KXWNBAGAME`.

**Corrections to the brief, both against the alarm it raised:**

- It stated *"85 of the 69 newly-positive rows are `KXWNBAGAME`"*. That is
  arithmetically impossible. 206 − 137 = **69** newly-positive rows; 85 − 55 =
  **30** of them are WNBA, or **43.5%**. The 85 is the total WNBA positives at
  step 2, not the increment.
- 43.5% is still an over-representation against WNBA's **27.0%** share of the
  pinned record (422 of 1,564, **[re-derived]**) — but only mildly, and WNBA's
  share of the *positive* set barely moves across the fee models at all:
  40.1% → 41.8% → 41.3%.

**And the sharper correction: no surfacing row is WNBA.** Of the 9 clean rows with
`E1 > 0` under step 2, exactly **one** is WNBA — `id 1350`,
`KXWNBAGAME-26AUG09DALMIN-MIN`, `no`, ask 270, `E1 +3.1375` — and it is refused by
`edge_within_method_noise`. Of the **4** rows that surface, **zero** are WNBA. The
rescore says so in its own §6: *"No conclusion here rests on a WNBA row. That is
fortunate rather than designed."*

**So the honest statement of the WNBA exposure is the opposite of a rescue
resting on it.** 27.0% of the record is scored at a coefficient measured on
**zero** WNBA fills, and round three's §7.5 says which way that cuts: on the
`H-SERIES / H-SPORT` branch, *"27% of the pinned record is priced at the dear
rate, which makes the gate harder to open, not easier."* **The WNBA cell in round
three is a risk to F, not a support for it** — and that is a better reason for
the cell to exist than the one the brief gave.

**One adjacent fact, recorded because it points the same way and is easy to miss.**
The anchoring census found that `SHARP_BOOKS` **did not bind** on 423 of the 1,564
rows (27.0%): no sharp book had quoted, and those rows were priced against the
full book set. They produced **zero** positive edges among the unsuppressed and
**zero** actionable rows. That is not about A-versus-F — it bears on ADR 0021 §8
option **B** — but it means the widest-consensus slice of this record already
returned nothing, and anyone reaching for B as F's replacement should read it
first.

---

## 10. What this ADR does NOT do

- **It does not decide A versus F.** That is the point of it.
- **It does not adopt a fee model.** The verdict is H3−; `k = 0.07` and
  `k = 0.035` are hypothesis generators. `calculate_fee` keeps its `max()` hedge,
  CLAUDE.md's 52.00% bar is unamended, and no code changes here.
- **It does not amend ADR 0021.** §8's six options stand as written; an
  annotation is appended pointing at this file, per ADR 0021's own
  never-edit-in-place convention.
- **It does not authorise round three.** That registration owns its own trigger
  (Joe's availability), its own cap (6 orders, $4.57) and its own expiry.
- **It does not recommend arming or disarming trading.** ADR 0018 is untouched;
  `ORDERS_ARE_DRY_RUNS` stays `True`.
- **It does not diagnose the odds outage** (§8) and does not pre-empt ADR 0020.
- **It does not propose wiring up `elo.py`**, or un-quarantining anything in ADR
  0022's `DISPOSITIONS`. ADR 0022 notes that Historian plausibly matters under
  options B and F; deferring F does not revive it.
- **It does not touch `edge_within_method_noise`.** The rescore's §9 records that
  a guard nobody has validated against outcomes has become decisive without
  anyone choosing that. It is a reason to look, and it needs its own ADR.

---

## What this does NOT establish

- **It establishes nothing about whether an edge exists at Kalshi.** ADR 0021 §1's
  forbidden sentence is forbidden here. The supported claim remains *"Kalshi is
  not mispriced relative to a devigged sportsbook consensus it may itself lead"*,
  and it is **the consensus-only strategy** that produced zero — never "the
  documented strategy", which credits a second signal that has never run.
- **It expresses no shortfall as a multiple of its own noise**, states no row as
  nearly clearing or clearly missing, and derives no such figure. ADR 0021 §3's
  prohibition is untouched and is not reopened by anything in §5.
- **It partitions and stratifies by neither Grid D nor Grid B.** Both keep their
  banners. Row identities in §5.3 and §9 are attributes of named rows, not a cut.
- **§4's and §5.4's slate arithmetic is a projection, not a forecast.** It carries
  a rate measured on 60 game clusters in one week of one August in two leagues
  onto future slates that have not been sampled. ADR 0021 §7.1 governs: nothing
  here generalises to a single future row.
- **The 16:47Z live figures in §3.2 were not independently verified.** This lane
  has no production access. Two of them cross-check against readable sources; the
  rest are taken on report and labelled as such.
- **It does not establish that the two conditions in §8 are the only two.** They
  are the two that are currently observed to be unmet.
- **It says nothing about calibration, CLV, the maker path, combos, or in-play** —
  ADR 0021 §9's list of untested lines is unchanged.
- **Counted assumptions: 1.** That the 60 clusters derived here by truncating the
  market ticker to its first two hyphen-separated fields reproduce the gate's
  `COALESCE(m.event_ticker, r.ticker)` key. The pinned pull does not carry
  `event_ticker`, so this is a reconstruction. It is checked against the
  quantities ADR 0021 published from the same file — 59 clean clusters, 614 clean
  rows, 950 suppressed, 0 actionable — all four of which reproduce exactly.

---

## ANNOTATION 2026-08-11 — the deferral was re-examined on day one and **STANDS**. What changed is why round three is worth buying.

**Nothing above is withdrawn, amended, or edited.** Trigger (§6), expiry and
default (§7) are unchanged. This annotation records a re-examination, its
verdict, and one fact the body does not contain.

### A1. Why it was re-opened, and why that was half a mistake

`start.md` carried §5.4 forward as *"a number that landed while the ADR was
being drafted and weakens its rationale"* — F is ~11–14 months even on step 2,
its most favourable branch.

**§5.4 is not new information to this ADR. It is an input this ADR already
used.** §7.2's second bullet reads, in full: *"F on its best branch is still
about a year of uninterrupted daily slates (§5.4), and the record has not
accumulated a single new game cluster since 2026-08-09 (§8)."* The number is
cited by section number as one of the three stated reasons the default is A.

So §5.4 weakened the **commissioning brief's** belief — that F is live under
step 2 — and the ADR absorbed that correction before it was accepted. Re-opening
on §5.4 is re-litigating a settled decision using evidence the decision cites.
**Recorded here so a third session does not spend a fourth hour on it.**

### A2. What §5.4 *does* establish is about the trigger, not about F

Verified for this annotation, adversarially and independently, against the
committed registrations:

> **On the taker path, step 2 is the ceiling of favourability among the
> round-one-admissible fee models.** No outcome vector of round three can yield
> an applicable fee below **$0.0088 at 50c**. The registered classification
> alphabet is `{LOW = k_MLB, HIGH = 2*k_MLB}` with `HIGH` defined as exactly
> twice `LOW` (round three §B7), so the family has **no member below 0.035 by
> construction**; the LOW envelope at 50c admits only `{$0.0088, $0.0089}`, so
> step 2 sits at the *favourable edge* of LOW rather than its midpoint; and the
> one attribution that moves the candidate rows at all — `H-NOTIONAL` — moves
> **three of four to the dearer rate** (§5.3). A sub-envelope observation
> classifies `NOVEL` / `B4-DETECTED (novel)`, which round three §7.5 makes
> *hypothesis-generating only* and which **suspends** the step-1/step-2
> decomposition rather than improving it.

**Consequence.** Branch (a)'s best case is "step 2 applies at these cells" —
which is §5.4's 3-of-60, ~11–14 months. Branch (b), 26 of 32 vectors, kills F
outright. **Every branch of the trigger points at A, differing only in
confidence.** Round three's contribution to the A-versus-F question is
therefore **confirmatory at best**, and §6 overstates it.

### A3. And that is an argument about the purchase, not a reason to resolve today

**Resolving A-versus-F now buys approximately nothing.** Option A keeps the
recorder and the measurement discipline (ADR 0021 §8), changes no code, and
leaves `ORDERS_ARE_DRY_RUNS` at `True`. Nothing in the queue is blocked on the
answer. The delta between "A, declared today" and "deferred, defaults to A on
2026-08-31" is a **label on a claim**, for three weeks.

**Resolving now has a real and asymmetric cost.** §6 makes A-versus-F round
three's stated purpose. Declaring A while the $5 authorisation is still in front
of Joe invites the reading *"the line is stopped, so don't spend it"* — and
cells `R` (the B4 replication detector) and `W` (the first WNBA fee ever
observed) earn on **every** branch including `H-NONE`, for `core/fees.py`, for
CLAUDE.md's 52.00% bar, and for options B, C and D, none of which option A
touches.

**§7's carve-out cuts the same way and is independent.** A verdict line carrying
`NOT ATTEMPTED` on two or more cells is instrument failure, not a result — round
two died exactly that way. Taking A today takes it *without the chance to
distinguish* those two cases, which is committing the reachability error in
advance rather than guarding against it.

> **THE ASK CHANGES, THE DECISION DOES NOT.** Round three must be put to Joe on
> **cells `R` and `W`**, which earn unconditionally — not on being the
> A-versus-F trigger, which A2 shows it barely is.

### A4. The fact the body does not contain — and it is not good news

The ceiling in A2 is a **taker-path** ceiling. Stating it unqualified is false,
and the counterexample is live in deployed code:

```
backend/core/fees.py:74   MAKER_COEFFICIENT       = Decimal("0.0175")
backend/core/fees.py:79   SPORTS_MAKER_MULTIPLIER = SPORTS_MULTIPLIER / 4
```

Both are wired into `calculate_fee(price_tenths, contracts, maker=...)`
(`:130`, `:163`). At size that is **$0.004375 at 50c → a 50.44% break-even**,
**0.44 points cheaper than step 2** and the cheapest bar anywhere in this
project.

**These are code constants, not measurements**, and round three does not touch
them: P3 voids a maker fill (round three §P3), and round three's own §10 says
*"it does not establish the maker rate at all … `MAKER_COEFFICIENT = 0.0175` and
`SPORTS_MAKER_MULTIPLIER = 0.015` remain untested everywhere in this project."*

**Read the offset before the number.** This is ADR 0021 §8 **option D**, which
is unranked, unstarted, and owned by **ADR 0017 — proposed, not accepted**.
ADR 0017's own adverse-selection counterargument is **1.50c**, which is larger
than the entire 1.50-point headroom step 2 would buy and far larger than the
0.44 points the maker path adds on top; **no named row has ever cleared it.**
A cheaper bar against an unmeasured adverse-selection cost is not headroom, it
is an untested trade. Nothing here revives D, and this annotation does not rank
it.

**It is recorded because A2's ceiling claim is wrong without it**, and because a
future session hunting for headroom will find these two constants and needs to
meet the counterargument in the same paragraph.

### A5. What this annotation does NOT establish

- **It does not decide A versus F**, and it does not shorten or extend the
  expiry. 2026-08-31 (UTC) and the default to A are untouched.
- **It adopts no fee model.** H3− stands; `calculate_fee` keeps its `max()`
  hedge; CLAUDE.md's 52.00% bar is unamended.
- **It does not revive option D**, propose the maker path, or authorise a maker
  fill. §A4 records two constants and their untested status, nothing more.
- **It does not re-derive §5.4 or license it further.** §5.4 remains a
  projection, not a forecast; ADR 0021 §7.1 still governs and nothing here
  generalises to a single future row. §A2's argument is *structural* — about
  what the registered outcome vectors can and cannot declare — and does not
  depend on §5.4's rate being right.
- **It does not diagnose §8's condition 2.** The recorder has still produced no
  new game clusters since 2026-08-09 and no cause is written here either.
- **Counted assumptions: 0.** Every claim in §A2 and §A4 is read from a
  committed registration or from `backend/core/fees.py` at the cited line.
