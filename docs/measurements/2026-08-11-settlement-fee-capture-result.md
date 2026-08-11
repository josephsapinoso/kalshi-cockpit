# Settlement `fee_cost` capture — 2026-08-11T05:32Z

**What ran:** `scripts/capture_fills_fixture.py`, exit **0**. Free, read-only,
no orders, no odds credits.
**Executes:** Amendment A **§A5** of
`2026-08-10-preregistration-fee-model-fill-calibration.md`, against the
predictions registered in **§S9** of
`2026-08-10-fee-model-fill-calibration-result.md`.
**Audited by `measurement-skeptic` before entering the record.** Verdict:
**SURVIVES NARROWED.** One of the three claims put to it — H4 — **failed**, and
that failure is the most important thing in this document.

**Artefacts** (gitignored; they carry a real account's positions):
`data/captures/portfolio_settlements.json` (58 records),
`data/captures/portfolio_fills.json` (6 records),
`data/captures/backup-pre-0530Z/portfolio_settlements.json` (the 55-record
baseline, captured 2026-08-10T18:18:12Z).

---

## 1. The result

> Three of the four fee-calibration positions settled. On all three, settlement
> `fee_cost` equals the sum of that position's fill-time `fee_cost` values
> **exactly, to six decimal places**, matching the "reading 1/2" prediction
> registered in §S9 **twelve hours and twenty-three minutes** before the first
> settlement.
>
> This **refutes reading 3** — that settlement `fee_cost` is a cent-displayed
> different quantity — **for `KXMLBGAME`, on 2026-08-11**.
>
> It re-reports, through a second endpoint, the same six fee values that
> refuted the cent-rounded Model A at fill time. **It is not a second
> refutation of that model**; that refutation is §S4's, at fill time.
>
> **H4 is not settled.**

| position | C | result | settlement `fee_cost` | Σ fill `fee_cost` |
|---|---:|---|---:|---:|
| `…BALMIN-MIN` | 1.00 | **yes** (won), revenue 100 | `0.008800` | `0.008800` |
| `…TEXLAA-LAA` | 1.00 | no (lost), revenue 0 | `0.008800` | `0.008800` |
| `…KCLAD-KC` | 11.27 | no (lost), revenue 0 | `0.077800` | `0.077800` |

The ATP position `…CERETC` has **not** settled. **§S9 fixed in advance that it
must not be read** — reading 3 and the old cent model both predict $0.18 there,
so it cannot separate them. It is not used anywhere in this document.

**Pre-registration is genuine, and was checked rather than assumed.** §S9 was
committed at `8ca2193`, 2026-08-10T14:14:18Z. The earliest of the three
settlements is 2026-08-11T02:37:35Z. The six fill fees were already on disk at
2026-08-10T18:18:12Z, byte-identical to the new capture. Both documents were
grepped for `Amendment` and `SUPERSED`: the prereg carries **Amendment A only**,
the result document carries **no amendment**, and nothing supersedes §S9 or §A8.

---

## 2. H4 is UNTESTED, and §A8's declaration rule is a registration defect

This section exists because the first reading of this capture — mine, in the
session that ran it — was that `…BALMIN-MIN` winning **gave H4 its separation**.
**That is wrong**, and the way it is wrong is worth more than the result.

Amendment A **§A8** declares H4 on `settlement fee_cost == fill-time fee`. That
is a true statement about when the two *predictions* agree. **It is not an
inference licence**, and the asymmetry is total:

```
reading (i)  "the field reports the ENTRY fee only"
             P(observed == entry | reading i)  = 1     REGARDLESS of H4

reading (ii) "the field reports TOTAL fees, and settlement charged zero"
             P(observed == entry | reading ii) = 1     iff H4
```

The likelihood ratio for H4 is bounded by the prior mass on reading (ii), which
was **never measured and never registered**. §A8's own opening paragraph says
the two readings *"cannot be separated"* by settlements and that the fills
separate them — **but the fills separate them only in the `>` branch.** The `=`
branch is the non-discriminating one, and it is the branch that landed.

**Four compounding reasons, each sufficient on its own:**

1. **The denominator is 1, not 3.** Two of the three lost (`revenue = 0`). A
   charge levied on proceeds has no proceeds to be levied on. Those two rows had
   **zero opportunity** to display an exit fee.
2. **The one eligible row is an anchor where the error vanishes.** At settlement
   `P ∈ {0, 1}`, so a settlement charge of the exchange's own `k·C·P(1−P)` shape
   is **identically $0 by construction**. "No exit fee" and "an exit fee by the
   same formula" return the **same answer** at the only price observed. This is
   `clv_tenths(500, 500, "no")` exactly: 50c is where that error disappears, and
   `P = 1` is where this one does.
3. **No other channel carries information.** `revenue = 100 × winning_count` on
   **13 of 13** winning rows in the whole 58-record file, up to 70 contracts,
   **zero exceptions** — verified directly, not taken from the audit. A field
   that has never taken any value but its definitional maximum cannot testify
   that nothing was deducted from it, and it is integer-cents, so a sub-cent
   charge is invisible in it regardless.
4. **§11's A3 remains ASSUMED with no working detector.** P2 (the balance
   fallback) is recorded in §S1 as *"NOT RUN, and now unrunnable"*; §S7's in-app
   cross-check is *"NOT RECORDED"*. Every number here is a **reported field**,
   never a measured charge.

**§R5 passed and would not have gone red in the failure mode that obtains.** Its
failure condition is conjunctive — *"zero settlement charges **AND** cannot see
the entry fees either"*. Entry fees are visible, so R5 is green. The live risk
is *"the field is entry-only"*, which R5 does not test. **A guard whose only
failure mode is not the one that can happen is decoration here**, and it is the
ninth such guard this project has found.

### This is the second defective registered reading in the same pair of documents

§S8 already records that the registration's **linearity bonus** reading returned
the wrong answer: `fee(F2) = 10 × fee(F1)` exactly, which the registration calls
*"evidence for per-contract scope"*, refuted coefficient-free by F3. §A8's H4
rule is the **second**. Two of this registration's auxiliary readings have now
been logically defective. **That is a fact about the registration's reliability
and it belongs beside the H4 verdict**, not in a footnote.

### And H4 is load-bearing for every EV figure in the tool

`backend/core/fees.py:197` `settlement_fee()` is consumed by
`backend/core/ev.py:89`, `backend/core/ev.py:140` and
`backend/core/parlay.py:213` — verified by grep, not assumed. **Every EV number
this tool computes rests on a hypothesis that is now explicitly untested rather
than pending.** That is a downgrade in confidence, not an upgrade.

---

## 3. The number nobody may act on

Stated here **so it can be refused explicitly**, which is the only safe way to
handle it:

```
k=0.070, ceil-to-cent      fee 0.0200   bar 52.00%   <- deployed
k=0.070, ceil-to-$0.0001   fee 0.0175   bar 51.75%
k=0.035, ceil-to-$0.0001   fee 0.0088   bar 50.88%   <- what the MLB fills imply
```

A **1.12-point** drop against a stated headroom of **0.38 points** — it would
make the headroom **3.9× larger**. That is the single largest piece of good news
anywhere in this project's record, produced by **two distinct fee cells, one
sport, one day**.

**CLAUDE.md rule 1 applies at full force: a large apparent edge is a bug until
proven otherwise.** This capture observed **no new (price, size) cell**. The fee
verdict is unchanged at **H3−**, under which §7's consequence table reads: *"the
`max()` hedge **stays**, unchanged."*

**§A7 is now partly stale as a quotable.** Its *"the entire 0.25-point gap is
the per-order `ceil`"* was computed at `k = 0.07`, a coefficient the MLB fills
refute. **Never quote §A7 post-fills without that qualifier.**

**What would have to be true before the bar moves — six things, none of them
done:**

1. The settlement contradiction **resolved**, not ranked. Two live readings
   remain (granularity change vs per-category). If per-category, `k = 0.035` is
   an **MLB fact** and CLAUDE.md's bar is **global** — a global change would be
   unsupported by construction.
2. A **second channel**. There is none today: P2 unrunnable, §S7 unrecorded.
3. The fee observed **at or near 50c at `N = 1`** in the category traded. F4 is
   48c/C=1/MLB — close, and not it.
4. `KXWNBAGAME` fee-observed. It is **27.0% of the record and zero of the
   fills**.
5. A **maker** fill. All six are taker (`is_taker = true`).
6. The registered follow-up — two `KXMLBGAME` orders at `P ≈ 0.15`, `C = 1` and
   `C = 20`, ~$3.15 — run, killing size and price-region as attributions.

**And the asymmetry decides it alone:** over-estimating the fee costs
opportunity; under-estimating it costs money. The hedge's error currently runs
in the **safe** direction. Deleting it on two cells reverses that.

---

## 4. `count_fp = 0.27`

The fractional fill is the buy-in-dollars UI artefact (P5).

- **Kept** for the identity check. The question is whether settlement equals the
  **sum of the fills**; dropping any fill breaks the sum by construction, and
  dropping this one changes `0.0778` to `0.0759`. Excluding it would be a
  post-hoc choice that manufactures a mismatch.
- **Excluded** from any model conjunction, as §S4 already does: Models A and B
  are **undefined**, not refuted, at non-integer `C`.
- It does not break the shape: `0.035 × 0.27 × 0.1971 = 0.00186260 → ceil
  = 0.0019`.
- **The consequence that must be written down:** `…KCLAD-KC`'s settlement row is
  `F1 + F2 + an unregistered fractional fill`. **It is not a registered-cell
  observation and may not be quoted as one.** That leaves exactly **one** clean
  registered settlement cell (F4, `C = 1` @ 48c) plus one unregistered duplicate
  of it.

**The aggregation cross-check is also non-discriminating, by $0.000046.**
`…KCLAD-KC` was the multi-fill cell that should have separated "sums fill fees"
from "re-derives from the position average". It does not, because all three
fills were at the same price:

```
sum of per-fill ceils  = 0.0690 + 0.0069 + 0.0019 = 0.0778
ceil(aggregate raw)    = ceil(0.077746095)        = 0.0778
total round-up across the three fills  = 0.000053905
slack before the two answers diverge   = 0.000046095
```

It fell on the non-discriminating side with **less than half a rounding
increment to spare**.

---

## 5. The §A2.1 confound, in its required words, and it is worse here

**A CHANGED SCHEDULE verdict is confounded with a CATEGORY DIFFERENCE, and this
design cannot separate them.**

At fill time §S12 could **split** the confound: F3 (ATP) and the MLB fills were
**63.9 seconds apart**, a cross-section no schedule change can produce.

**That split does not carry over.** The ATP position has not settled, so the
settlement comparison has **no cross-sectional lever at all**: 11 baseline rows
of `KXNFLSPREAD`/`KXNFLGAME`/`KXSB`/`KXNBATOTAL`/`KXNBASPREAD` settled
2025-11-27 → 2026-02-09, against 3 rows of `KXMLBGAME` settled 2026-08-11.
**Category and era differ together.**

So reading 3 dies for **MLB in August 2026**. A product- and era-conditional
display rule over the 11 pre-revision NFL/NBA rows is **untouched**, because
those rows have no fills to be compared against.

---

## What the settlement capture does not establish

*Written for this capture. Not echoed from the fill-time result.*

- **It does not establish H4.** Amendment A §A8's rule declares H4 on
  `settlement fee_cost == fill-time fee`, but that is the branch in which
  reading (i) ("the field reports the entry fee only") and reading (ii) ("it
  reports total fees, and settlement charged zero") remain indistinguishable.
  Reading (i) predicts equality *unconditionally, whatever settlement charged*.
  The design's separation existed only in the `>` branch, and the `>` branch did
  not occur. **H4 is UNTESTED, not confirmed.** §A8's declaration rule is
  recorded here as a registration defect, alongside §S8's.
- **The H4 denominator is one, not three.** `…TEXLAA-LAA` and `…KCLAD-KC` both
  lost (`revenue = 0`); a charge on proceeds has no proceeds to be levied on, so
  neither row had any opportunity to display an exit fee.
- **That one row is a non-discriminating anchor.** At settlement `P ∈ {0,1}`, so
  a settlement charge of the exchange's own `k·C·P(1−P)` shape is identically $0.
  "No exit fee" and "an exit fee by the same formula" give the same answer at the
  only price observed. Nothing here bears on an exit **before** resolution, where
  `0 < P < 1`.
- **No other channel carries information.** `revenue = 100 × winning_count` on 13
  of 13 winning rows in the whole 58-record file, up to 70 contracts, with zero
  exceptions — a field at its definitional maximum on every row cannot testify
  that nothing was deducted, and it is integer-cents, so a sub-cent charge is
  invisible in it regardless. `value` is the settled price, not money. P2 (the
  balance fallback) was never run and is now unrunnable; §S7's in-app cross-check
  was not recorded. **§11's A3 — that a settlement charge would be visible on the
  account — remains ASSUMED with no working detector.** §R5 passed, but its
  failure condition is conjunctive and does not test the mode that is live here.
- **It is not three cells.** `…BALMIN-MIN` and `…TEXLAA-LAA` are the same price
  (48c), same size (C = 1), same series, same day, and returned the identical
  value to six decimals. Two distinct cells, one of them duplicated.
  `…KCLAD-KC` carries 81.6% of the settled fee dollars ($0.0778 of $0.0954).
- **`…KCLAD-KC` is not a registered-cell observation.** It is F1 + F2 + an
  unregistered `C = 0.27` fill, for which both models are undefined. Exactly one
  clean registered settlement cell exists (F4, C = 1 @ 48c).
- **It does not aggregate-test.** Sum-of-ceils and ceil-of-aggregate both return
  $0.0778 on `…KCLAD-KC`, because all three fills were at 27c. The total round-up
  is $0.000053905 against a $0.0001 increment — it fell on the non-discriminating
  side with $0.000046 to spare.
- **It adds no new fee observation.** All six fee values were on disk at
  2026-08-10T18:18:12Z, before any position settled. The marginal content of this
  capture is that the settlements endpoint agrees with the fills endpoint on MLB
  rows, and that a win was credited at `revenue = 100`. It is not a second,
  independent refutation of the cent-rounded Model A; that refutation is §S4's,
  at fill time.
- **It refutes reading 3 only for `KXMLBGAME`, on 2026-08-11.** The 11 baseline
  rows are `KXNFLSPREAD`/`KXNFLGAME`/`KXSB`/`KXNBATOTAL`/`KXNBASPREAD`, settled
  2025-11-27 → 2026-02-09, and have no fills to be compared against. A product-
  and era-conditional display rule survives there.
- **Amendment A §A2.1's confound applies to the settlement comparison, and is
  worse there than at fill time. A CHANGED SCHEDULE verdict is confounded with a
  CATEGORY DIFFERENCE, and this design cannot separate them.** §S12's
  63.9-second ATP/MLB cross-section does not carry over: the ATP position has not
  settled, so the settlement comparison has no cross-sectional lever at all —
  category and era differ together.
- **It changes nothing about the 52.00% break-even bar.** No new (price, size)
  cell was observed. The verdict remains H3−, under which §7's consequence table
  keeps the `max()` hedge unchanged. §A7's "the entire 0.25-point gap is the
  per-order `ceil`" was computed at `k = 0.07` and must not be quoted post-fills
  without that qualifier.
- **It does not establish the charge, only the reported field.** There is still
  no second channel of any kind.
- **`n` = 3 settlements, 2 distinct cells, 1 clean registered cell, 2 prices, 1
  series, 1 sport, 1 day, 1 account.** No interval appears here and none may be
  added.

---

## 6. Vocabulary

**Must not appear** in any write-up of this capture: *declared* (of H4),
*confirms H4*, *settles H4*, *H4 holds*, *no settlement fee is charged*,
*proves*, *validated*, *three independent cells*, *three observations*,
*refutes Model A at three cells*, *the fee is 0.035*, *the break-even bar is
50.88%*, *the bar falls to*, *k = 0.035 is established*, *the settlement
contradiction is resolved*.

**Permitted:** *"H4 is **untested**, not confirmed — the observation landed in
§A8's non-discriminating branch"*; *"reading 3 is refuted for `KXMLBGAME` on
2026-08-11"*; *"`k = 0.035` remains a hypothesis generator"*.

---

## 7. Corrections this capture forces

- **`tasks/NEXT.md:874`** said the settlement capture *"Settles: … and **H4**
  (settlement charges no second fee)"*. **It does not.** Corrected in place in
  the same change that discovered it, rather than routed.
- **§A8's declaration rule** is defective as written and must not be applied by a
  future session. It is annotated here rather than in the registration body,
  because a registration body is never edited — but this document is named from
  `NEXT.md` so the correction is reachable from where people read.
