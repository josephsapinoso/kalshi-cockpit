# 0027 — The cost headroom is an upper bound pending H4, and one number is carrying two bounds in opposite directions

**Date:** 2026-08-11
**Status:** Accepted as a **statement of what may be said about a number**. This
ADR measures nothing, re-scores nothing, and moves no threshold. Its evidential
content is already recorded — in
`docs/measurements/2026-08-11-settlement-fee-capture-result.md` §2, in ADR
0026 §3, and in ADR 0023 §5.1 — which it re-verifies against source rather than
re-derives.
**Owns:** the rule in §4 — what may and may not be said about the 0.38-point
headroom — and the four qualifications in §§1–3 and §5.
**Number:** 0027, not 0020 — **0020 stays reserved for the `stale_odds`
scrape-clock remedy**, per ADR 0025 and ADR 0026:10-12. This repo's numbering
runs 0019 → 0021 → 0024 → 0025 → 0026 → 0027.
**Does not touch** ADR 0021's refutation, ADR 0023's deferral of A-versus-F, ADR
0024 (arming), the `max()` hedge in `core/fees.py`, or any threshold anywhere.
It **changes no code and authorises no measurement.**

---

## 0. What this is not

It is not a fee measurement, and it must not be quoted as one. **No claim below
rests on new data.** The one new thing is a sizing calculation in §2, done
against a number ADR 0023 already carries, and it is arithmetic on the record
rather than a reading of the venue.

It is also **not** a claim that Kalshi charges a settlement fee. It is the
narrower and more uncomfortable claim that **nobody in this repo knows**, and
that every EV figure the tool prints has been written as though somebody did.

---

## 1. The defect

`backend/core/fees.py:197-209`:

```python
def settlement_fee(price_tenths, contracts, maker=False) -> Optional[float]:
    """...Settlement is not a trade, so there is exactly one fee: the one paid
    on entry. Named explicitly so no call site has to remember that."""
    return calculate_fee(price_tenths, contracts, maker)
```

**It is a rename, not a second charge** — verified by reading the file for this
ADR. The docstring's *"exactly one fee"* is the hypothesis **H4**, and **H4 is
UNTESTED**, not confirmed. Three facts establish that, each already in the
record:

1. **The eligible denominator is 1, not 3.** Two of the three settled positions
   lost (`revenue = 0`), so a charge levied on proceeds had no proceeds to be
   levied on — `2026-08-11-settlement-fee-capture-result.md` §2 reason 1, and
   ADR 0026:136-143, which states the premise the reason is conditional on.
2. **The one eligible row sits at an anchor where the error vanishes.** At
   settlement `P ∈ {0, 1}`, so a charge of the exchange's own `k·C·P(1−P)`
   shape is **identically $0 by construction** — capture result §2 reason 2,
   ADR 0026:127-129.
3. **The declaration branch that fired is non-discriminating, and this is the
   one that kills it.** Reading (i) — *the settlements field reports the entry
   fee only* — predicts the observation with probability 1 **whatever H4 is**,
   at any price, on any position. ADR 0026:122-126. No exit fee of any shape is
   excluded, so no eligible count rescues the branch.

**Consumers**, verified by grep for this ADR: `backend/core/ev.py:89`,
`backend/core/ev.py:140`, `backend/core/parlay.py:213`,
`scripts/rescore_fee_models.py:128`, `scripts/run_clean_shortfall.py:157`. The
last two are how the hypothesis reaches the pinned-record statistics as well as
the live EV path.

---

## 2. The consequence for the headroom, and it is asymmetric

`CLAUDE.md`'s premise paragraph states the venue lowers the break-even bar from
52.38% to 52.00% (taker) or 50.44% (maker, at size), and that *"the headroom is
0.38 points"*. ADR 0023:208-210 carries the same figures.

**Both bars assume zero settlement charge, because both are computed through
`settlement_fee()`.** A settlement charge raises both equally, so:

- **The 1.12-point *difference* between 52.00% and 50.88% is robust.** It is a
  difference of two quantities that move together, and the charge cancels.
- **The 0.38-point *headroom* is not.** It is a difference against a
  sportsbook's 52.38%, and **a −110 sportsbook has no settlement fee to omit
  while Kalshi may.** The omission therefore subtracts from the 0.38 and nothing
  subtracts from the 52.38. **0.38 is an upper bound.**
- **Every `edge_after_fees_tenths` the tool prints is overstated by whatever the
  charge is**, and the charge is unmeasured rather than small.

### Size it, because this is the part that bites

ADR 0023:210 records the best step-2 row at `max E1 = +9.2466` tenths, which is
**$0.00925/contract**. The step-2 *entry* fee at 50c is **$0.0088**
(0023:210, same row). So a settlement charge **the same size as the entry fee**
— the most obvious shape a second charge would take — exceeds the best surviving
edge in the entire record.

> **ADR 0023:223's result — *"4 rows / 3 claims / 3 games"* surviving the full
> deployed predicate under step 2 — is not robust to a settlement fee equal to
> the entry fee. At that magnitude all four surfacers are erased.**

This does not change ADR 0023's decision, which was to defer. It removes the
step-2 branch's only positive result from the set of things that may be leaned
on while H4 is untested.

---

## 3. Three further inconsistencies in the 0.38 figure

Recorded here rather than in `CLAUDE.md`, which stays short. None of them is a
measurement; all three are properties of the number as currently written.

**(a) With respect to the coefficient, 0.38 is a *lower* bound — so one number
carries two bounds in opposite directions.** `calculate_fee` returns the
**maximum** across candidate models (`backend/core/fees.py:130-134`), and **all
six observed fills came in below `min(A, B)`** —
`2026-08-10-fee-model-fill-calibration-result.md:80-83` shows F1 `$0.0069` vs
A `$0.02` / B `$0.01`; F2 `$0.0690` vs `$0.14` / `$0.10`; F3 `$0.1785` vs
`$0.18` / `$0.20`; F4 `$0.0088` vs `$0.02` / `$0.01`. The deployed bar is
therefore **above** the bar the venue appears to charge, which makes 0.38 a
floor with respect to the rate. §1 makes it a ceiling with respect to
settlement. **A single scalar bounded from both sides in opposite directions is
not a point estimate and must not be printed as one.**

**(b) It is a 50c-only quantity, and the record is not at 50c.**
`backend/core/ev.py:119-143`: `effective_price = tenths_to_dollars(ask) +
fee/contracts`. Verified by running it: at `500` tenths, `C = 1`, the deployed
effective price is `0.52` — the 52.00% bar. At `200` tenths, `C = 1`, it is
**`0.2200`**, a 2.00-point loading rather than 0.38 against anything. On the
pinned record (`docs/measurements/2026-08-10-clean-shortfall-pull.json`, 1,564
rows), **only 40 rows — 2.6% — sit at exactly 50.0c**, and the **median ask is
51.0c**. Re-derived for this ADR from the pull. The bar is a function of price
and the headline treats it as a constant.

**(c) `k = 0.035` is an MLB fact and the bar is global.** F3 is an ATP cell:
`C = 20` at `0.1500`, fee `$0.1785`
(`2026-08-10-fee-model-fill-calibration-result.md:82`). `k·C·P(1−P) = k × 2.55`,
so `0.1785 / 2.55 = 0.070000` **exactly** — the published coefficient, not the
halved MLB one. The step-2 decomposition at 0023:210 is labelled *"(MLB)"* in
its own table and the 52.00%/50.88% pair is quoted globally.

---

## 4. The decision — what may and may not be said

> **The 0.38-point headroom may be stated only as an upper bound, conditional on
> H4 (zero settlement charge), which is untested with an eligible denominator of
> 1. No document may state it as a point figure, and no document may state a
> post-fee edge as a settled quantity without the same qualification.**
>
> **The 1.12-point difference between the 52.00% and 50.88% bars may be stated
> unqualified**, because a settlement charge raises both equally.

Concretely, three prohibitions:

1. **No document may say "the headroom is 0.38 points"** without the H4
   qualification. `CLAUDE.md` is corrected in this commit.
2. **No document may quote ADR 0023:223's four step-2 surfacers as a result that
   survives fees**, because §2 shows it does not survive a settlement charge the
   size of the entry fee.
3. **No document may quote the 52.00% bar as the bar for a row that is not at
   50.0c.** It is 0.2200 at 20c and the median ask on the record is 51.0c.

---

## 5. What this ADR does not establish

- **It does not establish that Kalshi charges a settlement fee.** H4 is
  UNTESTED, which is a statement about this repo's evidence, not about the
  venue. The charge may well be zero; nothing here bears on which.
- **It does not size the charge.** §2's $0.0088 is the *entry* fee at 50c used
  as a scale for a what-if, chosen because it is the most obvious shape a second
  charge would take. **It is not an estimate of the settlement charge and must
  never be quoted as one.**
- **It does not overturn ADR 0021's refutation.** A larger fee makes the
  consensus-only strategy worse, not better. Every correction here moves in the
  unfavourable direction, and that is the direction that needs least
  double-checking.
- **It does not overturn ADR 0023's deferral**, and it is not the A-versus-F
  trigger. It removes one branch's positive result from the licensed set; the
  decision to defer is untouched and the 2026-08-31 default stands.
- **It licenses no measurement and no spend.** Testing H4 needs an exit
  **before** resolution where `0 < P < 1`, or a second channel — ADR 0026:333-338
  records that neither exists today (P2 unrunnable, §S7 not recorded, §11's A3
  ASSUMED with no detector). **That design would need its own registration and
  Joe's approval, and is not proposed here.**
- **It changes no code.** `settlement_fee()` still returns `calculate_fee(...)`.
  Making it charge twice would be a threshold change on an untested hypothesis,
  in the flattering-to-nobody direction but on no evidence, and that is not
  better than the current state — it is the same error with the opposite sign.
- **§3(b)'s 40-of-1,564 and 51.0c median are pinned-record facts, not a claim
  about future slates.** They come from one pull of two series
  (`KXMLBGAME` 1142, `KXWNBAGAME` 422).
- **`fee_candidates` is not `calculate_fee`.** §3(a)'s six fills bear on the
  rate; they say nothing about settlement, and the two questions have been
  conflated before.

---

## 6. Consequence

`CLAUDE.md`'s premise paragraph is corrected in this commit to state 0.38 as an
upper bound and to cite `backend/core/fees.py:197` and this ADR. The correction
is three sentences and the section does not grow — the file already carries two
corrections of exactly this shape (the one-signal correction, and *"52.00%, not
the 51.75% this file used to claim"*), and this is the third.

No other file is edited by this ADR.
