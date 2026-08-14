# Result — fee-rate attribution, round three

**Registration:** `docs/measurements/2026-08-10-preregistration-fee-rate-attribution-round-three.md`.
Placed by Joe by hand in the Kalshi app, **2026-08-14, 06:23:27–06:26:33 UTC**
(3 min 06 s, one calendar date, inside §8's 120-minute window).
Analysed the same day from `/portfolio/fills` and `/portfolio/orders`.

**Raw payloads:** `data/captures/portfolio_fills.json`,
`data/captures/portfolio_settlements.json`. **Gitignored and not committed** —
they carry a `user_id` and this account's trading history, and `kalshi-cockpit`
is public. Regenerate with `scripts/capture_fills_fixture.py`.

**Producer:** every fee figure below is re-derived from those payloads by
**`scripts/reconcile_observed_fees.py`**, which is committed and re-runnable.
Envelope values are read from §1.4 of the registration at the line cited.

> **AUDITED 2026-08-14 by a `measurement-skeptic` lane** that derived every
> figure independently: **SURVIVES WITH QUALIFICATION.** The arithmetic
> reproduced row for row. **Six corrections were required and are applied
> below**, three of which the audit found by opening a payload this analysis had
> not: the verdict box pooled across categories in a way §10 forbids, P7 was
> declared unverifiable when a second channel already verified it, §S12 sat
> under a section number whose registered contents were never computed, and §14
> mis-located the deployed defect. **The provenance sentence this paragraph
> replaces cited a "§12" that did not exist and a script that had not been
> written.** Nothing in the audit moved a classification.

---

## Verdict

> **FULL. B4 NOT DETECTED. Attribution read.**
>
> **H-SIZE, H-PRICE and H-NOTIONAL are REFUTED.**
> **H-SERIES and H-SPORT both survive.**
> **`H-SERIES / H-SPORT — NOT SEPARATED BY THIS DESIGN.**
>
> `R` used **pass 1** (47–52c), as registered and as preferred.
> `W` activated on `KXWNBAGAME` with **no substitution**.
> §8 **not breached**. No cell voided, no cell NOT ATTEMPTED, no cell unfilled.
>
> **The fee rate is not a venue constant.** On **9 fills** across `KXMLBGAME`
> and `KXMLBSPREAD` the charged fee pins `k` to **(0.0349691, 0.0350076]**. On
> the **2 non-baseball fills** in the same window — `KXATPDOUBLES` 20 @ 15c and
> `KXWNBAGAME` 1 @ 28c — the same functional form pins `k` to
> **(0.0699608, 0.0700000]**. The intervals are **disjoint**, with a ratio floor
> of **1.998×**, so non-constancy is established and is not a rounding artifact.
>
> **Written deliberately as "these two fills", not "non-baseball".** §10 of the
> registration says verbatim: *"It says nothing about tennis, NFL, NCAAF, soccer
> or esports… **Pooling across categories is forbidden.**"* The first version of
> this box said "every non-baseball fill is charged at `k = 0.070`" — a sentence
> the registration prohibited before the data existed, resting on one tennis
> fill and one WNBA fill.
>
> **The deployed `calculate_fee` disagrees with all 11.** It overcharges by
> **2.03×–2.90× on baseball and 1.12×–1.41× on the two non-baseball fills**.
> The dominant defect is **granularity, not the coefficient**: `_model_a` rounds
> to the cent (`backend/core/fees.py:81`) where Kalshi now charges to `$0.0001`.

**This document declares an attribution. It does not authorise a code change,
and in particular it does not authorise editing `fees.py:73`** — which on its
own would leave baseball ~1.45× wrong at 27c. See §14.

---

## §S1. Q-W

Ran 2026-08-13 and **ACTIVATED**:
`docs/measurements/2026-08-13-qw-wnba-band-reachability-result.md`. Cite that
file, not this line, for any number from it — and never §1 without §2.

`KXWNBAGAME`, **first series, no substitution**, so cell `W` is registered and
§Power's five-cell branch is licensed. Headline share **272 of 288 = 94.4%**
deduplicated to one look per burst (**not** 97.99%, which is the raw pass
share); independent time-weighted denominator agrees at **93.3%**.

**Reproduced here unedited, because it cuts against the result it licensed:**
six of thirteen events had not tipped when the window closed; restricted to
in-window fixtures the event count is **7, below the bar of 8** — unregistered,
so it cannot un-activate `W`, published anyway. The record covers **3.18 days,
not four**. The 16 misses are **one five-hour continuous outage**. `W` has **no
depth-durability figure and no time-to-tip figure**; `min_depth` is 1 contract
on the four largest contributors and it must not inherit `KXMLBSPREAD`'s
"695 of 695 at ≥20".

## §S2. The §0.4 census — NOT REPRODUCED

**Registered requirement (B6): the analysing session re-derives §0.4's census
from the record rather than restating it, with §0.4a's independent-unit
accounting beside it.** *This was not done.*

**Reason, mechanically:** the census reads `kalshi_quotes` on the live volume
(`/data/cockpit.db`); the laptop's `kalshi.db` is empty, and reaching the live
volume is an `flyctl ssh` step this session did not take.

**What that costs, stated rather than minimised:** §0.4 is the *reachability*
justification for the bands — the argument that these orders were placeable.
The orders **did in fact fill**, so reachability is now established by the
stronger route of observation. It costs the design audit, not the attribution.
**It is an open item, not a closed one.** Do not mark this document complete
against §S until it is done, and do not print 696 without "4 game-days".

## §S3. Preconditions P1–P10

| | Precondition | Verdict | Evidence |
|---|---|---|---|
| **P1** | fill record carries `fee_cost`, `count`, `price`, `is_taker` | **YES** | all four present on 11/11 fills; field census in the capture header. **The wire names are `fee_cost`, `count_fp`, `yes_price_dollars`, `is_taker`** — `count` and `price` as the registration names them do not exist on the record |
| **P2** | unit sanity on `S2` | **YES** | `S2` raw `0.079200` against a `$2.60` stake = 3.05%. Dollars, not cents; a cents reading would be 3,046% |
| **P3** | `is_taker` true | **YES** | `is_taker: true` on all five; `maker_fees_dollars: "0.000000"` on all five orders, independently |
| **P4** | one fill row per order | **YES** | 5 orders → 5 fills, 1:1 |
| **P5** | `count` reads exactly `N` | **YES** | `1.00, 20.00, 1.00, 1.00, 1.00`. **This is the round-one failure** (`count = 0.27`) and it did not recur |
| **P6** | price in band, not an excluded tick | **YES** | see §S6; no cell landed on 10c / 30c / 40c / 50c |
| **P7** | earlier cells' `fee_cost` unchanged after later fills | **YES, for round one** (corrected) | **This cell first read NOT VERIFIABLE, and that was wrong.** There are two channels in the capture set, not one. Round one's four positions settled 2026-08-11 and their `/portfolio/settlements.fee_cost` reproduces the summed fill fees **exactly** — including the three-fill `KCLAD` position at `0.0019 + 0.0069 + 0.0690 = 0.077800`. An independent endpoint, captured four days later, agrees to the tenth of a cent. Round three's five are **still pending settlement**, so P7 is verified for round one and open for round three |
| **P8** | pre-game at placement | **YES** (derived) | 716–1023 minutes to true start, computed as `occurrence_datetime − 3h` (ADR 0006). **Derived, not recorded from the app** — see §S10 |
| **P9** | series prefix matches the cell | **YES** | `KXMLBSPREAD`, `KXMLBSPREAD`, `KXMLBSPREAD`, `KXMLBGAME`, `KXWNBAGAME` |
| **P10** | every void recorded with its reason and its fee | **VACUOUS** | no cell was voided |

## §S4. Reachability guards R1–R8

Registered as pre-placement guards on whether the bands could be found. **All
five cells filled at the first market taken, with zero seconds of fill lag**, so
every guard is satisfied by observation. Printed before the verdict as
registered; they gate nothing here because nothing was NOT ATTEMPTED.

## §S5. Gate G1 — the schedule anchor

`R` observed at **`$0.008800`**, price `0.52`, `C = 1`, `KXMLBGAME`.

Registered ENV LOW at 52c is **`$0.0087–$0.0088`**. The observation is inside
it. Against §1.5's four signatures: not `$0.0100`, not `$0.0200`, not inside ENV
HIGH (`$0.0174–$0.0176`).

> **Signature: round one's MLB rate, granularity and rounding all still hold at
> `KXMLBGAME`, `C = 1`, mid price. B4 NOT DETECTED. Proceed to the attribution.**

**Carry the registration's quantifier with this, always** (`:859`): G1
establishes the schedule is unchanged **at `KXMLBGAME`, `C = 1`, mid price, over
four days**. It says nothing about durability beyond that window — which is
§14.2, and is the qualification that most constrains what this round licenses.

## §S6. The per-cell table

| Cell | Ticker | Series | Side | Price | `count` | `is_taker` | Notional | Min to start | Fill | `fee_observed` | ENV LOW | ENV HIGH | CENTRAL LOW | Class |
|---|---|---|---|---:|---:|:--:|---:|---:|---|---:|---|---|---|:--:|
| **S1** | `KXMLBSPREAD-26AUG141420STLCHC-STL4` | `KXMLBSPREAD` | yes | 13c | 1 | true | $0.13 | 717 | FILLED, **0.000 s** | `0.004000` | 0.0039–0.0040 | 0.0078–0.0080 | 0.0040 | **LOW** |
| **S2** | `KXMLBSPREAD-26AUG141420STLCHC-STL4` | `KXMLBSPREAD` | yes | 13c | 20 | true | $2.60 | 716 | FILLED, **0.000 s** | `0.079200` | 0.0776–0.0800 | 0.1551–0.1600 | 0.0791/**0.0792** | **LOW** |
| **S3** | `KXMLBSPREAD-26AUG141420STLCHC-STL2` | `KXMLBSPREAD` | yes | 27c | 1 | true | $0.27 | 716 | FILLED, **0.000 s** | `0.006900` | 0.0069–0.0069 | 0.0138–0.0138 | 0.0069 | **LOW** |
<!-- S1/S2 envelopes read from §1.4's S1 and S2 tables; S3 and W from §1.4:808,
     which registers ONE table for both ("identical predictions; different
     series"); R from §1.4's R table. -->

| **R** | `KXMLBGAME-26AUG141810MIACIN-CIN` | `KXMLBGAME` | yes | 52c | 1 | true | $0.52 | 944 | FILLED, **0.000 s** | `0.008800` | 0.0087–0.0088 | 0.0174–0.0176 | 0.0088 | **LOW** |
| **W** | `KXWNBAGAME-26AUG14DALIND-DAL` | `KXWNBAGAME` | yes | 28c | 1 | true | $0.28 | 1023 | FILLED, **0.000 s** | `0.014200` | 0.0071–0.0071 | 0.0141–0.0142 | 0.0071 | **HIGH** |

No cell VOID. No cell NOT ATTEMPTED. Every order `type: "limit"`,
`status: "executed"`, `maker_fees_dollars: 0.000000`.

**Two columns the registration requires and this table cannot fill:**

- **Displayed size at the ask at submit — UNRECORDED.** Joe placed without
  recording the §3 fields. An independent API sweep at **05:56 UTC**, 27 minutes
  before the first order, showed `STL4` at 13c with 1,849 displayed and `STL2` at
  27c with 3,330. **That is a different instant and is not a substitute**; it is
  printed as context, not as the registered field.
- **Settlement `fee_cost` — PENDING for these five, but the channel is now
  LICENSED.** §6.2 makes settlement `fee_cost` the durable substitute for a
  missed fill capture, **conditional on round one's §A5 capture returning
  `settlement fee_cost == fill-time fee`**. It does, on 4 of 4 positions (see
  P7). **The condition is discharged and the substitution stands.** Capture
  round three's five once they settle.

## §S7. The attribution

Outcome vector: **`R` LOW, `S1` LOW, `S2` LOW, `S3` LOW, `W` HIGH.**

| | `R` | `S1` | `S2` | `S3` | `W` | Predicted | Verdict |
|---|:--:|:--:|:--:|:--:|:--:|---|---|
| **H-SERIES** | LOW | *x* | *x* | *x* | free | `R`=LOW; `S1`=`S2`=`S3` | **SURVIVES** — `R` LOW, and the three `KXMLBSPREAD` cells agree (all LOW), satisfying the uniformity constraint of §0.5 Cost 1 |
| **H-SPORT** | LOW | LOW | LOW | LOW | **HIGH** | all five | **SURVIVES** — matched all five exactly, including `W` |
| **H-SIZE** | LOW | LOW | **HIGH** | LOW | LOW | `C ≥ 20 → HIGH` | **REFUTED by `S2`** — `C = 20` returned LOW (`0.0792`, inside ENV LOW `0.0776–0.0800`; ENV HIGH begins at `0.1551`) |
| **H-PRICE** | LOW | **HIGH** | **HIGH** | LOW | LOW | `P < b → HIGH`, `b ∈ (0.15, 0.27]` | **REFUTED by `S1` and `S2`** — both at `P = 0.13 ≤ 0.15` returned LOW |
| **H-NOTIONAL** | LOW | LOW | LOW | LOW | LOW | LOW everywhere | **REFUTED by `W`** — stake `$0.28`, far below `t ∈ ($2.70, $3.00]`, returned HIGH |

**H-SERIES and H-SPORT are not separated by this design**, and the reason is
structural rather than a shortfall of luck: H-SERIES leaves `W` free, so `W`
being HIGH earns it nothing and costs it nothing. Separating them needs **two
series inside one sport disagreeing** — which this round tested (`KXMLBGAME` and
`KXMLBSPREAD`, both LOW) and which came out consistent with *both*.

**H-SPORT is the more constrained of the two survivors** — it staked a
prediction on all five cells and hit all five, where H-SERIES staked four. That
is a remark about how much each risked, **not** a declaration between them. The
verdict line stands as NOT SEPARATED.

## §S8. Verdict line

```
FULL. B4 NOT DETECTED. ATTRIBUTION READ.
H-SIZE REFUTED (S2). H-PRICE REFUTED (S1, S2). H-NOTIONAL REFUTED (W).
H-SERIES / H-SPORT — NOT SEPARATED BY THIS DESIGN
R: pass 1 (47-52c). W: activated, KXWNBAGAME, no substitution.
§8 NOT BREACHED.
```

## §S9. Coverage qualifier

**FULL.** All five cells read. No attribution lost its falsifier.

## §S10. In-app displayed fee — UNRECORDED

Joe placed without recording the §3 fields, so **the in-app displayed fee, the
displayed ask, the displayed size and the app-side pre-game confirmation do not
exist for any cell.** The API values stand alone.

**What this costs:** the registered cross-check on the instrument. §S10 exists
so that a disagreement between app and API would STOP THE LINE.

**Corrected:** this section first said *"with one channel there is nothing to
disagree."* That was wrong in the same way P7 was. The **app** channel is
missing, but `/portfolio/orders` is a third channel captured alongside the
fills, and it agrees with them on every cell — `taker_fees_dollars` reproduces
each `fee_cost`, `maker_fees_dollars` is `0.000000` throughout, and
`type: "limit"`, `status: "executed"` corroborate the four-point check
independently of anything Joe would have written down. And for round one,
`/portfolio/settlements` is a fourth. **The attribution does not depend on the
app reading**, and the instrument is better cross-checked than this section
originally claimed — but the *app-side* check is genuinely absent and stays
recorded as such.

## §S11. The `S2` balance reading — NOT TAKEN

Joe did not record the balance before or after `S2`. Reported as
**NOT TAKEN**, which is distinct from §6.1's VOID.

**§6.1 registered this as "a cross-check on the API's `fee_cost`, never the
measurement"** and stated it was "likely to be void and that is expected, not a
failure." Nothing in the attribution rests on it.

**Related deviation, recorded:** §6 requires **at least 60 seconds** between
`S1` and `S2`. Observed gap: **32 seconds** (06:23:27 → 06:23:59). The gap's
registered purpose was to let the balance settle between the two readings; the
readings were not taken, so the deviation has no consumer. **Recorded as a
protocol deviation with no effect on any classification**, not excused.

## §S12. The registered B2 diagnostics — NOT COMPUTED

**Corrected. This section previously carried the reconciliation table below
under this heading, and that was a substitution.** §7.4 registers three specific
B2 detectors. What happened to each:

- **D-B2a** (the envelope-vs-CENTRAL gap and the implied shape exponent, per
  cell) — **NOT COMPUTED.** Admitted at §S13.
- **D-B2b** (the `S1`/`S3` within-series ratio) — **NOT COMPUTED, and it was
  available.** `S1` and `S3` both classified LOW, which is the condition it
  needs. §7.4:1389 requires that unavailability be *stated* rather than skipped;
  it was neither run nor declared. **This is the omission the audit found, and
  it is recorded rather than back-filled**, because computing it now — after
  seeing the attribution it would have informed — is the freedom this document
  family exists to remove.
- The third B2 detector — **NOT COMPUTED.**

**So §S required outputs 12 and 13 are both missing.** §7.2:1337 says: *"NO
CELL, NO SUB-READING AND NO BY-PRODUCT… may substitute for the conjunction."*
The table below is not a B2 diagnostic and no longer claims to be.

## §S12a. Cross-round reconciliation — UNREGISTERED, out of population

**Read the three warnings before the table.**

1. **Out of population.** §2 scopes this round to *"exactly the four or five
   registered orders."* Six of the 11 rows are round one's.
2. **Unregistered, and it is 11 × 6 = 66 comparisons.** The registered
   multiplicity count (§7.1) is 10 comparisons and 25 attribution predictions,
   and it does not cover this. With 66 post-hoc comparisons over a model family
   that contains the right answer, a perfect fit is not surprising on its own.
3. **What rescues it from being a fishing expedition is not the fit — it is the
   interval.** The admissible `k` per group is tight and the two are disjoint;
   see §S12b. Treat the table as *descriptive*, and the intervals as the claim.

Exact decimal arithmetic, produced by `scripts/reconcile_observed_fees.py`:

| Series | `n` | `P` | actual | k035 order ceil | k070 order ceil | k035 per-contract | k070 per-contract | k035 order half-up |
|---|---:|---:|---:|---|---|---|---|---|
| `KXMLBGAME` | 0.27 | 0.27 | `0.001900` | **MATCH** | 0.003800 | 0.001863 | 0.003726 | MATCH |
| `KXMLBGAME` | 1 | 0.27 | `0.006900` | **MATCH** | 0.013800 | MATCH | 0.013800 | MATCH |
| `KXMLBGAME` | 10 | 0.27 | `0.069000` | **MATCH** | 0.138000 | MATCH | 0.138000 | MATCH |
| `KXATPDOUBLES` | 20 | 0.15 | `0.178500` | 0.089300 | **MATCH** | 0.090000 | 0.180000 | 0.089300 |
| `KXMLBGAME` | 1 | 0.48 | `0.008800` | **MATCH** | 0.017500 | MATCH | 0.017500 | 0.008700 |
| `KXMLBGAME` | 1 | 0.48 | `0.008800` | **MATCH** | 0.017500 | MATCH | 0.017500 | 0.008700 |
| `KXMLBSPREAD` | 1 | 0.13 | `0.004000` | **MATCH** | 0.008000 | MATCH | 0.008000 | MATCH |
| `KXMLBSPREAD` | 20 | 0.13 | `0.079200` | **MATCH** | 0.158400 | 0.080000 | 0.160000 | MATCH |
| `KXMLBSPREAD` | 1 | 0.27 | `0.006900` | **MATCH** | 0.013800 | MATCH | 0.013800 | MATCH |
| `KXMLBGAME` | 1 | 0.52 | `0.008800` | **MATCH** | 0.017500 | MATCH | 0.017500 | 0.008700 |
| `KXWNBAGAME` | 1 | 0.28 | `0.014200` | 0.007100 | **MATCH** | 0.007100 | **MATCH** | 0.007100 |

**11 of 11 explained, no residual**, by `k = 0.035` on baseball and `k = 0.070`
otherwise, `ceil` to `$0.0001`, rounded **per order**.

Two by-product observations, both **incidental and neither registered**:

- **Per-order rounding beats per-contract**, on **three** rows — corrected from
  two: `KXMLBSPREAD 20 @ 13c` (`0.0792` vs `0.0800`), `KXMLBGAME 0.27 @ 27c`
  (`0.0019` vs `0.001863`), and `KXATPDOUBLES 20 @ 15c` (`0.1785` vs `0.1800`),
  which is visible in the table above and was missed. **Caveat that must travel
  with this:** ENV LOW at 13c runs to `0.0800`, so the *registered classifier*
  does not discriminate here — this reads off the CENTRAL value, which §1.4 says
  is "reported, never used to classify."
- **`ceil` beats round-half-up**, on four rows (`0.48`, `0.48`, `0.52`, `0.28`).
  **Weaker than it looks, and weaker than the first version admitted:** §1.4
  constructs the envelopes *assuming* `ceil`, so this is consistency, not a
  test; both alternatives sit inside ENV LOW; and the four rows carry only
  **two distinct** `P(1−P)` values (`0.2496`, `0.2016`). The `KXATPDOUBLES` row
  contributes **zero** rounding information — `0.07 × 20 × 0.15 × 0.85 = 0.1785`
  lands exactly on the grid, which is §R3:1442's "round-one ATP trap".

## §S12b. Why the split cannot be a function of `(C, P)` — UNREGISTERED

**Stronger than refuting three named hypotheses one at a time**, and it belongs
in the record because it closes a family rather than three members of it.

Fee-per-contract against `P(1−P)`, allowing slack for per-order rounding:

```
P(1-P)=0.1275   fee/contract=0.0089250   (KXATPDOUBLES)
P(1-P)=0.1971   fee/contract=0.0069000   (KXMLBGAME)
P(1-P)=0.2016   fee/contract=0.0142000   (KXWNBAGAME)
P(1-P)=0.2496   fee/contract=0.0088000   (KXMLBGAME)
```

**10 strict inversions**, each larger than the rounding slack: a *smaller*
`P(1−P)` charging *more* per contract. Fee-per-contract is therefore **not
monotone in `P(1−P)`**, so **no shape, exponent, size, price or notional model
of `(C, P)` alone fits these rows.** The split requires an attribute outside
`(C, P)`. H-SIZE, H-PRICE and H-NOTIONAL fall out of this as special cases.

**And the split is not temporal.** The `KXATPDOUBLES` HIGH fill (13:48:33) sits
**64 s after** a `KXMLBGAME` LOW fill and **64 s before** another. The group
changes **3 times** along the time axis; a single schedule move would give
exactly 1. **An intraday schedule change is refuted.** *(This says nothing about
a multi-week change — see §14.2.)*

**A floating-point artifact, recorded because it nearly entered this document.**
The first pass of this reconciliation used binary floats and reported the
`KXATPDOUBLES` row as matching **nothing** — `0.07 × 20 × 0.15 × 0.85` evaluates
to `0.17850000000000002`, which ceils to `0.1786`. Re-run in `Decimal` it is an
exact match. A one-row unexplained residual would have been read as a novel fee
model. **Money is integer tenths of a cent for exactly this reason
(`core/prices.py`); this analysis briefly was not, and briefly lied.**

## §S13. Narrowed `k` and shape exponent — BY-PRODUCT

Not computed. Requires re-deriving the `(k, a)` admissible region against the
five new observations; **it is an interval narrowing, not an attribution**, and
nothing in §S7 depends on it. Open item.

## §S14. Stake, fees, P&L

- **Total stake:** `$3.80`
- **Total fees:** `$0.1131`
- **Total outlay:** `$3.9131` — inside the §Power five-cell max of `$4.05` and
  inside the `$5.00` Joe authorised 2026-08-10.
- **Realised P&L:** not yet settled.

> **Explicitly not evidence of anything about edge, at `n = 5`.** These are five
> orders chosen to sit in fee-discriminating price bands. They were not chosen
> because anything thought they would win, no suppression rule surfaced them,
> and `actionable` is still 0.

## §S15. The §10 list

Reproduced unedited from the registration — see
`docs/measurements/2026-08-10-preregistration-fee-rate-attribution-round-three.md` §10.
**Not restated here**, because paraphrasing it is the one thing §S15 exists to
prevent; read it there.

---

## §14. What this changes, and what it does not

**What it establishes:** the fee rate is **not a venue constant**, and the
deployed model reproduces none of the 11 observations.

**What the deployed `calculate_fee` actually returns**, which is the number that
matters and is not the coefficient:

| series | `C` | `P` | charged | `calculate_fee` | ratio |
|---|---:|---:|---:|---:|---:|
| `KXMLBGAME` | 1 | 0.27 | 0.0069 | 0.02 | **2.90×** |
| `KXMLBGAME` | 10 | 0.27 | 0.0690 | 0.14 | 2.03× |
| `KXMLBSPREAD` | 20 | 0.13 | 0.0792 | 0.20 | 2.53× |
| `KXMLBGAME` | 1 | 0.52 | 0.0088 | 0.02 | 2.27× |
| `KXATPDOUBLES` | 20 | 0.15 | 0.1785 | 0.20 | **1.12×** |
| `KXWNBAGAME` | 1 | 0.28 | 0.0142 | 0.02 | **1.41×** |

**Three consequences, and the first version of this section got all three
wrong:**

- **The baseball error is 2.03×–2.90×, not "a factor of two".** "Twice" is a
  statement about a coefficient inside a model the code does not run.
- **The code is wrong on non-baseball too** (1.12×, 1.41×). The defect is not
  baseball-specific and does not live at line 73.
- **Editing `fees.py:73` alone does not fix baseball.** With
  `TAKER_COEFFICIENT = 0.035`, `KXMLBGAME 1 @ 27c` gives
  `ceil(0.035 × 0.1971)` → **`$0.01`** against an actual `$0.0069` — still
  1.45× wrong — and Model B, unchanged and cent-rounded, would often dominate
  the `max()` anyway.

> **The dominant defect is GRANULARITY.** `_model_a` quantizes to `_ONE_CENT`
> (`backend/core/fees.py:81`); Kalshi charges single-game fees to `$0.0001` as
> of 2026-08. This defect is **better evidenced** (11 fills + 4 settlements),
> **sport-independent**, and **does not depend on the unresolved attribution**.
> The coefficient is the smaller and less certain of the two.

**A stale comment that is now false and is load-bearing.**
`backend/core/fees.py:228-230` reads *"11 of 11 single-game fees are whole
cents. That is the path this tool trades, so the premise above holds where the
constant is used."* **None of the 11 fills is a whole cent.** That sentence is
the stated justification for `FEE_MATCH_TOLERANCE_DOLLARS = 1e-9` and must be
corrected in the same change that touches the model.

**The direction of the error is the reason to be slow.** The code overcharges.
Correcting it makes every edge look **better** — precisely the shape CLAUDE.md's
first rule says to distrust. Nothing here reaches a money decision before:

1. **The high-rate group is two fills, each the sole fill in its series.**
   Baseball is `k = 0.035` across **9 fills** on 2 series (`KXMLBGAME` 6,
   `KXMLBSPREAD` 3) and 2 dates. `KXWNBAGAME` and `KXATPDOUBLES` are **one fill
   each** — and they carry the entire "not a venue constant" finding.
2. **DURABILITY, and this is the rival the first version did not enumerate.**
   Every `k = 0.035` observation lies inside **2026-08-10 to 2026-08-14 — four
   days.** This account's own settlement record shows **11 of 11 single-game
   fees from 2025-11-27 to 2026-02-09 charged at `k = 0.07` rounded to the whole
   cent**, and **0 of 11** on a `$0.0001` grid. So **Kalshi revised the sports
   fee schedule at least once in the preceding six months**, which turns "the
   MLB rate is promotional or temporary" from speculation into the modal
   explanation for a novelty. §7.3's "time-varying schedule" rival was scoped to
   the 120-minute window; **a multi-week promotion is invisible to it and to
   every guard in this design.** Gate G1 certifies stability across four days
   and nothing further.
   *There is no MLB observation under the old schedule, so "baseball got cheaper
   in July" and "baseball was always cheaper and was never sampled" both fit.*
3. **Which attribute carries the split is unresolved, and there are more than
   two candidates.** H-SERIES and H-SPORT are the registered pair. **A
   per-market liquidity or maker-programme tier fits all 11 rows equally well**
   — the registration itself anticipated it at `:1368`, but only as a follow-up
   *if a NOVEL fee appeared*; none did, so it was never considered. Any
   predicate true of those two markets and false of the six baseball ones fits.
   **A code change must not silently pick the most generous reading.**
4. **H4 is still untested** (ADR 0027). Settlement `fee_cost` equalling the
   summed fill fees (§S6, P7) is consistent with there being no settlement
   charge — and **equally consistent with the field being entry-only and a
   settlement charge living elsewhere.** Separating those needs the account
   balance, which was not recorded. **It is evidence, not a test.**

**Registered consequence of this document: none.** It declares an attribution.
Changing `fees.py`, re-deriving the break-even bar, or re-scoring any historical
row each need their own decision and their own ADR.

## §15. Open items

**Ordered by what blocks a code change. Items 1 and 2 are the audit's
requirements; nothing touches `fees.py:73` before item 2 returns.**

1. **Fix granularity first, and separately, with its own ADR.** Cent →
   `$0.0001`. Better evidenced than the coefficient, sport-independent, and
   independent of the unresolved attribution. **Two ADRs, not one.** The stale
   comment at `fees.py:228-230` is corrected in the same change.
2. **A second MLB observation window, ≥3–4 weeks after 2026-08-14**, before any
   reduced baseball coefficient is hardcoded. This is the check that separates
   "the MLB rate" from "an August promotion", and it costs **one 1-contract
   fill**.
3. **A third baseball series** (`KXMLBTOTAL` / `KXMLBTEAMTOTAL`) and **a second
   market inside `KXWNBAGAME`.** The first separates H-SERIES from H-SPORT; the
   second separates a series-level rate from a per-market tier. Neither is in
   the current design.
4. **Verify `fee_model_verified` behaviour.** `FEE_MATCH_TOLERANCE_DOLLARS` is
   `1e-9` against a cent-rounded model, so it should be stop-the-line on all 11
   fills. **Checked 2026-08-14: it is honestly pinned at `met=False`**, because
   the `fills` table has no live producer (`backend/gate.py:639-658`). So it is
   not silently green — but **the MISMATCH branch has never been able to fire**,
   which is why nothing caught the schedule change. Wiring a producer is a
   `partner` decision and an ADR (ADR 0022).
5. **Capture round three's settlement `fee_cost`** once the five settle. The
   §6.2 substitution is now licensed (see §S6), so this is durable rather than
   urgent — but the fills endpoint still has a ~3-month retention bound.
6. **§S2's census reproduction** — needs `flyctl ssh` to the live volume.
7. **§S12/§S13's registered B2 diagnostics** — D-B2a and D-B2b. Recorded as not
   computed rather than back-filled; see §S12.

**Done:** the independent `measurement-skeptic` pass, 2026-08-14 —
**SURVIVES WITH QUALIFICATION**, six corrections applied above.
