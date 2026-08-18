# ADR 0046 — On combos the fee model undercharges, and the answer is a documented refusal, not a fitted branch

- **Status:** Accepted
- **Date:** 2026-08-18
- **Trigger:** the registered one-look at the first 8 combo fills ever
  observed (`docs/measurements/2026-08-18-preregistration-combo-fill-fee-
  look.md` → `...-combo-fill-fee-look-result.md`). Its §12 table said "C1
  refuted → an ADR follows immediately and `fees.py` gains a combo branch".
  The ADR is this; the branch question is decided here, and the answer is
  **no branch**.
- **Related:** ADR 0012 §5 item 2 (now *measured and unmatched*, marked in
  place), ADR 0027/0028 (the fee hedge family), ADR 0038 (the hunt stays
  closed — a fee finding is a cost fact, not an edge).

## The finding this responds to

On the 8 `KXMVECROSSCATEGORY` fills in the frozen capture (one account,
one sitting, prices $0.001–$0.228), `calculate_fee`'s never-undercharge
property is **refuted**: rows 1, 5, 6 and 8 were charged more than the
model returns (per-row shortfall $0.000010–$0.000080; largest ratio
1.0019), the off-model charges land on a grid finer than
`FEE_GRID_DOLLARS` (observed gcd $0.00001, a one-sided bound), and none of
the eleven registered candidate models predicted every order. The stronger
underlying fact, per the audited result: **every one of the eight charges
lies strictly above `0.070·C·P·(1−P)`** — implied `k` 0.070041–0.070548,
excluding 0.035 on every row — and the four rows the deployed model
"matches" exactly are grid coincidences (its ceil-to-$0.0001 rounds up past
the charge), not rows where the coefficient is right.

## The decision

1. **`calculate_fee` is unchanged.** No coefficient moves, no grid moves,
   no combo parameter is added.
2. **The refutation is documented at the point of use**: `core/fees.py`'s
   module docstring now states that the never-undercharge property does not
   hold for combos, with the measured bound, so no future consumer can
   inherit the guarantee silently. ADR 0012 §5 item 2 is marked *measured
   and unmatched* in place.
3. **No combo branch is fitted, and that is the decision, not an
   omission.** Three reasons, in order of weight:
   - The registration forbids fitting a twelfth model to the same 8 rows
     (§7: "NO TWELFTH MODEL IS FITTED HERE"), and any combo-aware model
     needs its own registered look on a fresh sample. Writing a branch now
     means inventing its formula from the rows that just refused eleven
     candidates.
   - **Nothing in production prices a combo.** Discovery excludes `KXMVE`
     (`JUNK_PREFIX`), the engine never sizes one, the calibration study
     excludes them structurally, and the order path cannot reach one. A
     branch would be dead code wearing a safety fix's clothes — the
     "built but never called" pattern this repo keeps recording.
   - The one live consumer, `portfolio_poll`'s `fee_predicted` annotation
     on mirrored `venue_hand` fills, is a *comparison column* whose whole
     purpose is to show the model disagreeing with reality. Making it
     agree by construction would erase the evidence that it disagrees.

## The tripwire this leaves armed

If anything ever proposes to price, size, or EV a combo, this ADR is the
document that says the fee input is **known wrong in the optimistic
direction**. The proposal must carry a freshly registered combo fee look on
a new sample before any EV is computed — an EV built on `calculate_fee` for
a combo overstates by construction.

## What this does not decide

Durability (one account, one sitting, one day), the true combo schedule
(unidentified — MIXED, per the result), maker combos, exits, or anything
about whether combos are worth betting. ADR 0038 stands: a cost fact
multiplies an edge and none exists to multiply.
