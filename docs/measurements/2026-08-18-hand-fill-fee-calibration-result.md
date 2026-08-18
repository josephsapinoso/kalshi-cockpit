# Result — the hand-fill fee calibration

**Date:** 2026-08-18. **One look, taken as registered.**
**Registration:** `2026-08-18-preregistration-hand-fill-fee-calibration.md` —
written and committed (`bfe49f0`) before any value file was opened.
**Producer:** `scripts/analyse_hand_fill_fees.py`, reading only the two
gitignored capture files. Every figure below is its output.
**Audited by `measurement-skeptic` before entering the record.** Verdict on
the draft: OVERSTATED, nine required corrections — all applied below. The
audit reproduced the producer's output byte-for-byte, mutation-verified the
OLD/NEW guard and the DEGENERATE exclusion, and confirmed C1/C1b/C2/C4/Q(d)
as reported. What it struck: the draft's C5 framing (its falsifier is an
identity that cannot fire — R1), an H4 phrasing the registration forbids
(R4), and four hand-typed figures. Two post-look additions were made to the
producer at the audit's direction (the mix-implied coefficient and the
baseball shares) — summary statistics of already-printed rows, no new cut
and no new model.
**Population:** 25 fills (all taker, all buys; `created_time`
2026-08-10..17) and 22 settlements (`settled_time` **2026-08-11..17**).
OLD/NEW split guard passed: 13 OLD, 12 NEW. 25 orders, zero multi-fill. All
25 intervals SHARP. The registration anticipated six series; **ten**
appeared — reported per its §8 rider. Pre-declared comparisons: 119.

**Whatever this analysis returns, it does not license changing
`TAKER_COEFFICIENT`.** The capture spans 8 days and ends 3 days after the
last prior observation; the registered durability requirement is a window
≥ 3–4 weeks after 2026-08-14. (Registration §1, repeated here as required.)

---

## The verdicts, per the registered decision rule (§7)

```
Q(a)  C1   HOLDS on this capture. No fill was charged more than the
                    deployed model.
      C1b  DEPLOYED MODEL MISMATCHED, 10 of 25. Ratio distribution per
                    series: KXMLBGAME 0.500x (3 fills) and 0.503x (3),
                    KXMLBSPREAD 0.500x (3), KXMLBKS 0.503x (1) -- the known
                    baseball half-rate, reproduced. The other 15 match
                    exactly. No code change is authorised by this document.
Q(b)  C2   NOT TESTABLE. Zero NEW fills carry a KXMLB* prefix. Old fills
                    may not be substituted. k = 0.035 remains untested
                    out-of-sample.
      C3   SURVIVES on what NEW contains -- 12 of 12 non-KXMLB* intervals
                    contain 0.070 (SHARP alone: 12/12) -- with its coverage
                    stated: those 12 are FOUR series on TWO dates, and 10 of
                    the 12 are UFC fills placed in one sitting
                    (2026-08-16, 01:00-03:22Z). Two of the four series are
                    SINGLETONS and carry no cluster claim alone.
      NOVEL: none. Zero intervals exclude both coefficients.
Q(c)  C4   NOT REFUTED. Settlement fee_cost equals the summed fill fees on
                    22 of 22 positions. Registered IN ADVANCE as
                    NON-DISCRIMINATING: this may not be read as "H4
                    closed" or "settlement appears free". The cost
                    headroom stays an upper bound (ADR 0027).
Q(d)  FORBIDDEN.    C1b mismatched, so proposing that hand fills count
                    toward _fee_model_verified is forbidden by the
                    registration. The recommendation is "fix the model
                    first"; `AND source = 'engine'` stays (ADR 0043).
```

## n before effect size

| series | units | OLD/NEW | interval (admissible k) |
|---|---|---|---|
| KXMLBGAME | 6 | OLD | (0.0349569, 0.0350076] |
| KXMLBSPREAD | 3 | OLD | (0.0349691, 0.0350076] |
| KXMLBKS | 1 SINGLETON | OLD | (0.0348139, 0.0352141] |
| KXUFCFIGHT | 5 | NEW | (0.0699931, 0.0700000] |
| KXUFCMOV | 5 | NEW | (0.0699910, 0.0700136] |
| KXATPDOUBLES | 1 SINGLETON | OLD | (0.0699608, 0.0700000] |
| KXPGATOUR | 1 SINGLETON | OLD | (0.0699823, 0.0700265] |
| KXWNBAGAME | 1 SINGLETON | OLD | (0.0699405, 0.0704365] |
| KXTRUMPSAY | 1 SINGLETON | NEW | (0.0697917, 0.0700521] |
| KXTOPUSAGEAI | 1 SINGLETON | NEW | (0.0696970, 0.0707071] |

Largest single fill's share of total fill fees: **16.3%** (a KXUFCMOV fill,
$0.3096 of $1.8988).

## The coefficient record after this capture

Two disjoint clusters, derived not asserted:

```
k in (0.0349691, 0.0350076]   n=10   KXMLBKS, KXMLBGAME, KXMLBSPREAD
k in (0.0699931, 0.0700000]   n=15   KXTOPUSAGEAI, KXTRUMPSAY, KXWNBAGAME,
                                     KXATPDOUBLES, KXPGATOUR, KXUFCMOV,
                                     KXUFCFIGHT
```

- The OLD baseball cluster **reproduces** the round-three interval exactly
  (reproduce-or-report: reproduced).
- The high cluster's tight bound is set entirely by **two** series —
  KXUFCFIGHT (n=5) fixes the lower edge and KXATPDOUBLES ties the upper.
  **Five of its seven series are SINGLETONS that only *admit* 0.070; they
  do not pin it** (KXTOPUSAGEAI's interval is ~15x wider than the
  cluster's). The honest sentence is: two multi-fill series pin 0.070, and
  five singletons — including two non-sports markets, politics and AI —
  are consistent with it.
- **§5.4 attribution: NOT SEPARATED BY THIS DESIGN.** No two series inside
  one sport disagree — the disagreement is the KXMLB* family vs everything
  observed outside it. Sport, series-family, and a per-market tier all
  still fit.
- Frozen six-model tally (reported, not re-tested): k070-order-ceil-1e-4
  matches 15/25, k035-order-ceil-1e-4 10/25, k035-contract-ceil-1e-4 8/25,
  k035-order-half-up 6/25, k070-contract-ceil-1e-4 4/25, k070-order-ceil-
  CENT 0/25. **Correction to the registration, recorded rather than
  inherited:** its §0 and §8 say retired Model B "stays in the set as a
  refuted control", but none of the six frozen models is Model B
  (`round-to-NEAREST cent per contract at 0.06`); the per-contract entries
  use ceil at 0.035/0.070 and the cent-grid entry is order-level. Model B
  was therefore **not re-refuted here**, and no claim about it is made.

## The 4.03%, decomposed (§6, C5) — corrected per the audit

ADR 0043's trap, quoted exactly: *"At 50c on baseball, k = 0.035 predicts
1.76% and k = 0.070 predicts 3.52% — his figure is above both"* — above
both **predictions at 50c**, which is what the decomposition resolves.

Printed in the registered order: n = 22 (0 two-sided, 0 unreadable);
largest contributor 16.3% of fees; stake-weighted **mean(1−P) = 0.6374**;
`k_required = 0.0632`; rate = **4.0337%**.

**The discriminating statistic:** the coefficient the observed mix implies
— each position weighted by its stake·(1−P), at the prefix rule's
assignment (KXMLB* → 0.035, else 0.070, which on this capture coincides
with the derived clusters) — is **0.0632. It equals `k_required` to four
decimals.** Baseball is 17.06% of stake, 10.70% of fees, 19.30% of
stake·(1−P), 7 of 22 positions. The 4.03% is what the measured per-series
coefficients produce on this mix of low prices and mostly-0.070 series.

**What the falsifier count does NOT show.** The draft of this document
claimed "C5 holds: zero per-position falsifiers" as if that were evidence.
The audit showed the falsifier is a **one-sided upper-bound identity**:
`fee = ceil(k_true·D)` entails `fee/stake ≤ k·(1−P) + slack` for any
assigned `k ≥ k_true`, so it cannot fire for a row assigned too high a
coefficient — deliberately misassigning baseball to 0.070 still fires zero
falsifiers, and the 15 non-baseball rows' passage is already entailed by
C1. Its only non-vacuous content is the 10 baseball rows, all OLD, tested
against the 0.035 derived from those same rows — in-sample. The
mix-implied agreement above, not the falsifier count, is C5's evidence.

**§6 has no power against H4 at all**, and saying so is required: its fee
input is the settlement `fee_cost`, which C4 showed equals the summed entry
fees — so a settlement charge, if one exists, could not appear as a
residual here by construction of the data source. Nothing in this section
bears on H4 in either direction.

**Deviation note:** the §4.1 yes+no=$1.00 guard is not implemented in the
producer; the audit verified externally that it would not have fired on any
of the 25 rows, and the side choice is immaterial to C1–C3 (D is symmetric)
and unused in §6 (stake comes from the settlement row).

## Defect D1, reported separately as registered (§4.4)

`calculate_fee(price_tenths, contracts)` declares `contracts: int` while
the live record contains fractional counts (0.27 observed). Handed the
float 0.27 it returns the deployed model's answer ($0.0038 — twice what
the venue charged, per C1b); handed `int(0.27)` it returns **0.0**, because
`contracts <= 0` short-circuits to zero — a real position's fee reported as
free. **This is a latent hazard in the signature, not an observed live
failure:** `backend/portfolio_poll.py:347` passes the float through and
gets the float answer, and the one caller that coerces —
`backend/store/orders.py:517`, `int(count)` — sits on the engine path,
where counts are integral today. **Follow-up, its own item:** the signature
should accept exact fractional counts or refuse them loudly; $0.00 for a
real fee is the one wrong answer.

## What this cannot establish (registration §11, carried in full)

Maker fees (zero observed). Sells and early exits (zero observed; wire
shape still uncaptured). Combos (ADR 0012 §5 stays unverified). Durability
past this 8-day window of one account — a promotional or temporary rate is
not excluded, and the word throughout is *these fills*, not *Kalshi*.
Which attribute carries the rate split. H4 in the confirming direction —
only refutation was reachable and it did not occur, so ADR 0027's caveat
stands unchanged. Anything off the observed grid. Anything about edge,
CLV, P&L, or Joe's skill; the +$1.03 is out of population and does not
appear here.

**A denominator observation, recorded because its direction matters:** the
prior capture of `/portfolio/settlements` held 59 positions; the frozen
capture holds 22, because the endpoint rolls (Amendment A1). The 37 lost
rows would have been additional C4 comparisons — the only direction with
any power against H4. The retention loss cost this analysis exactly the
test it most needed more of.

## Consequences (registration §12)

- **Killed for now:** the proposal that hand fills count toward
  `_fee_model_verified`. C1b mismatched; admitting these rows would pin the
  gate condition at MISMATCH as a side effect of a logging change. The
  open item is "fix the model, with its own ADR", sequenced behind
  round-three §15.
- **Unchanged:** `TAKER_COEFFICIENT = 0.070` (conservative — it did not
  undercharge on any of the 25 fills in this capture), the gate, the
  headroom's upper-bound status, and CLAUDE.md's baseball lines (C2 was
  not testable, so the "50.88% true on baseball" sentence neither gains
  nor loses support here). **Proposal, not decided here:** its four-day-
  window caveat could add "and unrefreshed by the 2026-08-16..17 fills,
  which contain no baseball".
- **Next dated step, unchanged from round three:** one baseball fill
  ≥ 3–4 weeks after 2026-08-14 (i.e. on or after ~2026-09-11), which costs
  one contract and would test both durability and C2 out-of-sample.
