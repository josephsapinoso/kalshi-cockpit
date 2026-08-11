# 0026 — Every branch of a declaration rule must price the rival hypothesis, in writing, before the data

**Date:** 2026-08-11
**Status:** Accepted as a **writing convention**. This ADR decides how future
pre-registrations are *written*; it measures nothing, re-scores nothing, and
moves no number. Its evidential content is two already-recorded defects, which
it re-verifies rather than re-derives.
**Owns:** the rule in §5 — the rival-price table that a declaration rule must
carry — and the prospective verification in §6.
**Number:** 0026, not 0020 — **0020 stays reserved for the `stale_odds`
scrape-clock remedy**, and this repo's numbering runs 0019 → 0021 → 0024 → 0025
→ 0026.
**Does not touch** ADR 0021's refutation, ADR 0023 (A-versus-F), ADR 0024
(arming), ADR 0025, the fee model, `CLAUDE.md`'s 52.00% bar, or any threshold in
any registration. **It amends no registration body.** Amendments are appended by
the lane that owns the file; this ADR is not one and cannot act as one.

---

## 0. What this is not

It is not a measurement, and it must not be quoted as one. **No claim here rests
on new data.** The two instances in §2 and §3 were both already recorded — in
`docs/measurements/2026-08-11-settlement-fee-capture-result.md` §2 and in
`tasks/lessons.md` (2026-08-11, *"A registered decision rule can be logically
defective"* and *"The anchor where the error vanishes"*). Every number below was
re-checked against the source document or re-computed for this ADR before it was
written down.

What is new is the **direction of application**. `lessons.md` carries the
post-hoc form — *when a registered rule fires, ask whether the losing hypothesis
also predicts what you observed*. That check runs at the moment when it is
hardest to run honestly, because the answer is already visible. This ADR moves
the same check to registration time, where the data does not exist yet and the
author has nothing to protect, and §6 executes it once against a live
registration to show that it is cheap.

---

## 1. The defect, stated so it is recognisable in a rule nobody has written yet

> **A declaration rule branches on an observation. If the hypothesis the branch
> would reject predicts that same observation as strongly as the hypothesis it
> would declare, the branch declares nothing — however exactly the rule was
> followed, however far in advance it was fixed, and however clean the number
> is.**

Three properties make it hard to see, and all three are present in both
instances below.

1. **The rule is valid as a statement about when the predictions agree.** §A8's
   *"readings (i) and (ii) coincide only if settlement charged zero"* is true.
   What does not follow is that observing the coincidence licenses the
   inference. **A true statement about agreement is not an inference licence**,
   and the gap between them is where both defects live.
2. **The branch that fires is usually the *expected* one.** A registration
   author prices the branch they are hunting for and writes the other as a
   residual. The residual is the one that lands.
3. **The observation is often forced.** A settlement only ever happens at
   resolution. If the only reachable anchor is one where the candidates agree,
   the correct output is UNTESTED — not the agreement reported as a result.

**The failure is not that the rule was wrong about the world.** It is that the
rule had one column filled in.

---

## 2. Instance one — §S8, the linearity bonus reading

`docs/measurements/2026-08-10-preregistration-fee-model-fill-calibration.md`
§1 (*"Why F1 and F2 share a market and a band"*) registers:

> `fee(F2) == 10 × fee(F1)` is therefore evidence for per-contract scope, and
> `fee(F2) < 10 × fee(F1)` for per-order.

`2026-08-10-fee-model-fill-calibration-result.md` §S8 records what happened:
`fee(F1) = $0.006900`, `fee(F2) = $0.069000`, **exactly equal to ten times**, so
the branch fired and returned **per-contract** — which F3 then refuted
coefficient-free, because `$0.1785` is not a multiple of `20 × $0.0001`
(`$0.1785 / $0.002 = 89.25`, **re-computed for this ADR**).

**The rival predicts the observed value exactly, and this was re-computed rather
than taken from §S8.** Under *per-order* rounding at the observed $0.0001 grid,
with the coefficient the MLB fills imply:

```
raw  F1 = 0.035 × 1  × 0.27 × 0.73 = 0.0068985  → ceil to $0.0001 = 0.0069
raw  F2 = 0.035 × 10 × 0.27 × 0.73 = 0.0689850  → ceil to $0.0001 = 0.0690
10 × fee(F1) = 0.0690 = fee(F2)                   EQUAL under PER-ORDER
```

The round-up is `$0.0000015` on F1 and `$0.000015` on F2 — a factor of ten
apart, so it cancels exactly. **Per-order and per-contract make the same
prediction at this cell.** The branch could not discriminate.

§S8 diagnoses the mechanism correctly and in its own words: *"A diagnostic whose
discriminating power depended on the granularity it was meant to help
identify."* That is the **conditional** form of the defect — non-discriminating
whenever the grid is fine, discriminating on a cent grid, and the grid was the
unknown. The registration should have carried the branch **contingent on
measuring the granularity first**, and it did not.

---

## 3. Instance two — §A8, the H4 declaration

Amendment A §A8 of the same registration:

> if `settlement fee_cost == fill-time fee` on a cell, then reading (i) and
> reading (ii) coincide only if settlement charged zero — so **H4 is declared
> for that cell**.

`2026-08-11-settlement-fee-capture-result.md` §1 records equality to six decimal
places on all three settled positions. The rule fired on schedule, on exactly
the data it was designed for.

**It establishes nothing, and the strongest reason is not the one usually given
first.** Two distinct non-discriminations sit on this branch and they have
different reach:

- **(a) Unconditional, and it is the one that kills the branch.** Reading (i) —
  *the settlements field reports the entry fee only* — predicts equality
  **whatever settlement charged**, at any price, on any position. `P(observed =
  entry | reading i) = 1` regardless of H4. No exit fee of **any** shape is
  excluded.
- **(b) Conditional on the observed price, and it is narrower.** At settlement
  `P ∈ {0, 1}`, so an exit fee of the exchange's own `k·C·P(1−P)` shape is
  identically `$0`. This kills only a *same-shape* rival; a flat charge, or a
  charge on proceeds, would still have shown up under (b) alone.

**Both are true and the order matters.** (b) is the memorable one — it is the
same blind anchor as `clv_tenths(500, 500, "no")` — but a registration that
fixed only (b) would still be defective, because (a) survives it. **A branch
must be priced against every live rival, not the most vivid one.**

**The denominator is 1, not 3 — with its premise stated.** Of the three settled
positions, `…TEXLAA-LAA` and `…KCLAD-KC` both lost (`revenue = 0`), so a charge
levied **on proceeds** has no proceeds to be levied on and those two rows had
zero opportunity to display one. That is the result document's reason 1 and it
is correct, **conditional on the charge being proceeds-based**; a flat or
notional-based charge would have made all three eligible. Either way the
eligible count is at most 3 and at least 1, and under (a) it does not matter,
because no eligible count rescues an unconditionally-predicted observation.

**The consequence is live and load-bearing. H4 is UNTESTED, not confirmed.**
`settlement_fee()` at `backend/core/fees.py:197` — **verified by reading the
file for this ADR** — asserts *"Settlement is not a trade, so there is exactly
one fee: the one paid on entry."* Its consumers, **verified by grep for this ADR
rather than copied**, are `backend/core/ev.py:89`, `backend/core/ev.py:140` and
`backend/core/parlay.py:213` (plus `scripts/rescore_fee_models.py:128` and
`scripts/run_clean_shortfall.py:157`, which is how the finding reaches the
pinned-record statistics as well). **Every EV figure this tool computes rests on
a hypothesis that is explicitly untested rather than pending.** That is a
downgrade in confidence, not an upgrade, and it is why a writing convention is
the proportionate response rather than a one-off correction.

### Correction to the framing this ADR was commissioned under

**Two corrections, both small, both recorded rather than smoothed:**

1. **It is twice in one registration and its result, not "twice in one
   document".** §A8 sits in the registration's Amendment A; §S8 sits in the
   result. The result document itself says *"the second defective registered
   reading in the same pair of documents"*, and that is the accurate form. The
   point survives intact: **two auxiliary readings of one registration were
   logically defective**, and the base rate of defects inside a registration is
   measurably not zero.
2. **Leading with `P ∈ {0,1}` understates the defect** (§3(a) above). It is the
   narrower of the two non-discriminations.

Everything else in the commissioning brief reproduced: §S8's arithmetic, §A8's
wording, the `1 not 3` denominator, `fees.py:197`, and all three consumer
citations.

---

## 4. Why pre-registration is the aggravating factor, not the mitigation

This is the reason the fix is a writing rule and not a review step.

A pre-registered rule's authority comes from having been fixed before the data.
That is exactly what makes it correct to apply without re-litigating — and it is
exactly what stops anyone re-reading it at the only moment they have the
information to see it is broken. **A registered rule gets *less* scrutiny at the
moment of use than an improvised one would, because re-opening it looks like the
sin the registration exists to prevent.** An improvised rule invites the
question *is this right?*; a registered rule invites the question *what does it
say?*.

**The tell was in the registration's own words and it still did not fire.**
§A8's opening paragraph says the two readings *"cannot be separated"* by the
settlements. The declaration rule fourteen lines later declares on the branch
where they are not separated. **The preamble is prose and the rule is a
procedure, and a procedure is what a reader executes.**

So the check cannot live at scoring time, where the incentive is wrong and the
answer is already visible. It has to be a thing the registration is not finished
without.

---

## 5. The decision — the writing rule

> **For every branch of a declaration rule, the registration must write down
> what *each* live rival hypothesis predicts at that exact observed value,
> before the data exists. Where two predictions coincide, the branch is labelled
> `NON-DISCRIMINATING` in advance, and it may declare nothing — at most it
> narrows to whatever claim survives the coincidence.**

Mechanically, as a table the registration carries, one row per branch:

| Branch | Fires when | H (declared) predicts | Each live rival predicts | Verdict |
|---|---|---|---|---|
| … | the exact observed value | … | … | DISCRIMINATING / NON-DISCRIMINATING / DISCRIMINATING-CONDITIONAL-ON-*x* |

Four rules govern the table, each earned by one of the two instances:

1. **Both branches are priced, not just the expected one.** §A8 priced the `>`
   branch and left `=` as a residual. The residual landed.
2. **Every live rival gets a column, not the most vivid one.** §3(a) versus
   §3(b): pricing the same-shape exit fee alone would have left the branch
   defective.
3. **A prediction that depends on an unmeasured parameter makes the branch
   `DISCRIMINATING-CONDITIONAL-ON-x`, and the branch may not be read until `x`
   is measured.** That is §S8 exactly: the linearity reading was contingent on
   the fee granularity, which was the unknown the design existed to find.
4. **A `NON-DISCRIMINATING` branch is not deleted — it is narrowed.** The
   correct output is the claim that survives under *both* hypotheses, or
   UNTESTED if none does. §6 shows a registration already doing this well.

**Cost.** One table, written while the rest of the registration is being
written, by an author who has no data to be tempted by. §6 took under an hour
against a 1,362-line registration.

**This rule is a convention about writing, and it cannot make a design
discriminate.** A design whose only reachable anchor is one where the candidates
agree stays undecidable; the rule only guarantees that this is discovered before
the credits are spent rather than after the verdict is quoted.

---

## 6. Prospective application — §7 of the repeat-poll registration **PASSES**

Applied to `docs/measurements/2026-08-10-preregistration-odds-last-update-repeat-poll.md`
§7, **before the capture runs and before any `last_update` value has been
compared against another at a different fetch instant** (§0.3 of that file: that
comparison does not exist anywhere in this repo). Amendment A of that
registration was read and confirmed to touch **nothing in §§1–7** — its own
record line says *"Changes to §§1–7: None"*, and it concerns P1's credit clauses
only.

The two hypotheses, from §1: **H_scrape** — `last_update` is *not a per-line
reprice timestamp* — declared CONFIRMED at `S ≥ 0.90`; **H_reprice** — the stamp
advances *because* the price moved — declared REFUTED at `S ≤ 0.20`.

| Branch | H_scrape predicts | H_reprice predicts | Verdict |
|---|---|---|---|
| **CONFIRMED**, `S ≥ 0.90` | `S` = share of advancing pairs with no changed row — high when 300 s reprices are rare | **per-line:** `S ≈ 0`, since `advanced ⟺ this pair repriced`. **book-scoped:** `S` high — a book repricing game *Y* advances the stamp on all 15 games | **DISCRIMINATING against per-line. Coincides with book-scoped — and §7 already prices it.** |
| **REFUTED**, `S ≤ 0.20` | `S ≤ 0.20` only if ≥ 80% of advancing pairs moved a price in 300 s | `S ≈ 0` unconditionally | **DISCRIMINATING-CONDITIONAL-ON the observed 300 s reprice rate.** |
| **UNRESOLVED**, `0.20 < S < 0.90` | reachable | reachable | **NON-DISCRIMINATING, and §7 says so** — *"no claim in the band `0.20 < S < 0.90` may be made from this measurement, ever"*. |

**Why CONFIRMED passes despite a coinciding rival, and this is the part worth
copying.** §0.1 measures that **27 of 30 books carry exactly one distinct stamp
across all fifteen games**, so a book-scoped reprice timestamp is the
empirically indicated rival, and it predicts a high `S` just as H_scrape does.
§7 does not ignore this and does not pretend the branch is clean. Its
**MANDATORY QUALIFIER** requires `S_strict` on the same line, and at
`S_strict < 0.90` it requires the write-up to state, in fixed words, that *the
stamp is book-scoped, so a reprice on another game in the same slate cannot be
excluded as the cause of the advance* — then restricts ADR 0020 to the claim
that `odds_age_ms` is **not a per-line freshness measure**, *"which is the claim
the guard's behaviour actually turns on either way"*.

**That is rule 4 of §5, executed a day before this ADR existed: the coincidence
is priced, and the declaration is narrowed to the residual that survives both
rivals rather than the branch being taken at face value.** §A8 had no such
clause, which is the whole difference between the two registrations.

**The controls are real and reach the confound.** `movers` / **PC5** (`≥ 5`
distinct books changed at least one price, else `UNRESOLVED — QUIET SLATE,
however high `S` is`) is the guard §A8 lacked: it stops `S = 1.0` being declared
on a frozen slate that could not have produced any other answer. **PC2**
(`N_adv ≥ 5`) is the marginal reachability check, and §7 carries a **joint**
reachability check on top — that CONFIRMED and PC5 are not mutually exclusive —
which is the failure that killed the joint bound's Branch Z.

### Two notes for whoever scores it. Neither changes the verdict, and neither is an amendment

Recorded here because they are cheap re-computations on data the capture already
collects, and because the only honest time to write them is before the data.

1. **`movers` is measured over the wrong window to certify the deciding one.**
   §6 defines `movers` over the **full 900 s span (poll 1 → poll 4)**, while the
   deciding statistic is the **300 s** pair (1 → 3). So PC5 can pass on price
   movement that happened entirely in the 3 → 4 leg, while cell **B** — the
   refuting cell — was unreachable at the primary interval. §7's own
   joint-reachability paragraph describes precisely that world (*"all 30 books'
   stamps advance between poll 1 and poll 3 with no price change, and 5 of them
   move a price between poll 3 and poll 4"*) and is right that it proves joint
   reachability; it is **also** the world in which the control does not cover
   the interval that decides. **This does not break the design**, because PC2
   carries the discrimination against per-line H_reprice on its own: under that
   rival a frozen 300 s window yields `N_adv = 0` and PC2 fails. **Print
   `movers` restricted to the primary pair beside the 900 s figure**, and say
   which one PC5 was satisfied by. It is the same shape as §R5 of the fee
   registration passing while not testing the mode that was live.
2. **REFUTED's rival-price lives in §5.1, not in §7.** The reasoning that keeps
   H_scrape from also predicting `S ≤ 0.20` — that most books do not move a
   pre-game MLB number inside 300 s — is argued where the interval is chosen,
   not where the verdict is declared. Under §5's rule that makes REFUTED
   `DISCRIMINATING-CONDITIONAL-ON` the observed reprice rate. **If REFUTED is
   ever declared, print the share of BOTH-pairs with any changed row at the
   primary interval beside it**; at ≥ 0.80 the branch is non-discriminating and
   the honest verdict is UNRESOLVED. This corner is extreme and the prior
   evidence points the other way — it is registered here so that it is a
   printed check rather than a judgement made after the fact.

> **Verdict: §7 passes.** Every declaration branch is either discriminating, or
> coincides with a live rival that §7 prices and narrows to in advance, or is
> explicitly labelled as declaring nothing. The two notes above are prints a
> scorer should add, not defects in the rule. **If either is to bind, it needs
> an amendment appended to that registration by the lane that owns it, before
> poll 1 — this ADR does not amend it and cannot.**

---

## 7. What this ADR does not establish

- **It establishes nothing about the fee model, and it is not a measurement.**
  The verdict there remains **H3−**; the `max()` hedge in `core/fees.py` stays
  unchanged; `k = 0.035` remains a hypothesis generator; the 52.00% bar is
  untouched.
- **It does not test H4 and does not license a design that would.** H4 is
  UNTESTED. Testing it needs an exit **before** resolution, where `0 < P < 1`,
  or a second channel — and there is none today: P2 (the balance fallback) is
  unrunnable, §S7's in-app cross-check was not recorded, and §11's A3 remains
  ASSUMED with no working detector. **That design is not proposed here and would
  need its own registration and Joe's approval.**
- **It does not amend, edit, or annotate any registration body.** §6's notes are
  observations, not amendments.
- **It does not predict the repeat-poll result.** §6 is a check on the *rule*,
  run before the data. `S` is unobserved and `UNRESOLVED` remains a live and
  fully respectable outcome.
- **It cannot make an undecidable design decidable.** Where the only reachable
  anchor is one at which the candidates agree, the rule surfaces that fact
  earlier; it does not remove it.
- **The two instances are `n = 2`, from one registration and its result.** They
  are a demonstration of a failure shape, not a rate. §5's claim is that the
  table is cheap and that this shape has now cost two auxiliary readings — not
  that it is the most common defect in registrations generally.
- **It does not claim the rule would have caught either instance.** §S8's
  granularity was unknown at registration time; rule 3 would have forced the
  branch to be labelled conditional and unread, which is weaker than catching it
  and is the honest claim. **§A8, by contrast, is unconditional** and rule 1
  would have caught it outright.

---

## 8. Consequence

The rival-price table of §5 is required in every future pre-registration in
`docs/measurements/`, beside the decision rule, before the data exists. A
registration without one is incomplete in the same way one without a stopping
rule is.

`tasks/lessons.md` already carries the post-hoc form of this check, in two
entries dated 2026-08-11. **This ADR is the pre-hoc form and does not replace
them**; the scoring-time question — *does the losing hypothesis also predict
what I observed?* — stays in force, and now has a table to check against instead
of a memory.
