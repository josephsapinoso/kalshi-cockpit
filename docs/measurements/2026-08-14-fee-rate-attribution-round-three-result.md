# Result — fee-rate attribution, round three

**Registration:** `docs/measurements/2026-08-10-preregistration-fee-rate-attribution-round-three.md`.
Placed by Joe by hand in the Kalshi app, **2026-08-14, 06:23:27–06:26:33 UTC**
(3 min 06 s, one calendar date, inside §8's 120-minute window).
Analysed the same day from `/portfolio/fills` and `/portfolio/orders`.

**Raw payloads:** `data/captures/portfolio_fills.json`,
`data/captures/portfolio_settlements.json`. **Gitignored and not committed** —
they carry a `user_id` and this account's trading history, and `kalshi-cockpit`
is public. No figure in this document is hand-entered; every one is read from
those payloads by `scripts/` code or by the reconciliation printed in §12.

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
> **The fee rate is not uniform across the venue.** Every baseball fill on this
> account is charged at `k = 0.035`; every non-baseball fill is charged at
> `k = 0.070`. The deployed `calculate_fee` charges `0.07` on everything
> (`backend/core/fees.py:73`) and is therefore **wrong on baseball, by a factor
> of two, in the conservative direction**.

**This document declares an attribution. It does not authorise a code change.**
See §14.

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
| **P1** | fill record carries `fee_cost`, `count`, `price`, `is_taker` | **YES** | all four present on 11/11 fills; field census in the capture header |
| **P2** | unit sanity on `S2` | **YES** | `S2` raw `0.079200` against a `$2.60` stake = 3.05%. Dollars, not cents; a cents reading would be 3,046% |
| **P3** | `is_taker` true | **YES** | `is_taker: true` on all five; `maker_fees_dollars: "0.000000"` on all five orders, independently |
| **P4** | one fill row per order | **YES** | 5 orders → 5 fills, 1:1 |
| **P5** | `count` reads exactly `N` | **YES** | `1.00, 20.00, 1.00, 1.00, 1.00`. **This is the round-one failure** (`count = 0.27`) and it did not recur |
| **P6** | price in band, not an excluded tick | **YES** | see §S6; no cell landed on 10c / 30c / 40c / 50c |
| **P7** | earlier cells' `fee_cost` unchanged after later fills | **NOT VERIFIABLE** | one capture, taken after all five. A single snapshot cannot see a retroactive edit. **Recorded as a gap, not as a pass.** |
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
- **Settlement `fee_cost` — PENDING.** These positions had not settled at
  capture. §6.2 makes this the durable substitute channel; capture it within
  days, before the fills retention window closes.

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
so that a disagreement between app and API would STOP THE LINE; with one channel
there is nothing to disagree. **The attribution does not depend on it** — the
dependent variable is `fee_cost` and it is read directly from the venue — but
the round is one instrument short of what it registered, and that is recorded
here rather than absorbed.

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

## §S12. B2 diagnostics — BY-PRODUCTS, not a result of this round

Labelled as §7.4 requires. **These are not what the round registered and none of
them is a declared finding.**

Full reconciliation over **all 11 fills on this account** (round one's six,
2026-08-10, plus round three's five), exact decimal arithmetic:

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

- **Per-order rounding beats per-contract**, on two rows: `KXMLBSPREAD 20 @ 13c`
  (`0.0792` observed vs `0.0800` per-contract) and `KXMLBGAME 0.27 @ 27c`
  (`0.0019` vs `0.001863`). **Caveat that must travel with this:** ENV LOW at
  13c runs to `0.0800`, so the *registered classifier* does not discriminate
  here — this reads off the CENTRAL value, which §1.4 says is "reported, never
  used to classify."
- **`ceil` beats round-half-up**, on four rows (`0.48`, `0.48`, `0.52`, `0.28`).
  **Weaker than it looks:** §1.4 constructs the envelopes *assuming* `ceil`, so
  this is consistency, not a test. Both alternatives sit inside ENV LOW.

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

**What it establishes:** the fee rate is **not a venue constant**. On this
account, baseball is charged at half the published sports coefficient.
`backend/core/fees.py:73` hardcodes `TAKER_COEFFICIENT = Decimal("0.07")` with
no series or sport awareness, and is therefore **wrong on every baseball
market**.

**The direction of the error is the reason to be slow.** The code overcharges.
Correcting it makes every baseball edge look **better** — which is precisely the
shape CLAUDE.md's first rule says to distrust. Nothing about this result should
be applied to a money decision before the following are resolved:

1. **Four series, one account, one venue-day per round.** Baseball is `k =
   0.035` across **9 fills** on 2 series (`KXMLBGAME` 6, `KXMLBSPREAD` 3) and 2
   dates. `KXWNBAGAME` and `KXATPDOUBLES` are **one fill each**. **The
   non-baseball half of the claim — the half that carries the whole "not a venue
   constant" finding — rests on two observations.**
2. **H-SERIES vs H-SPORT is unresolved**, and they differ in what they license.
   Under H-SPORT, *any* future baseball series is LOW. Under H-SERIES, only
   `KXMLBGAME` and `KXMLBSPREAD` are — a new baseball series would be unknown.
   **A code change must not silently pick the more generous one.**
3. **H4 is still untested** (ADR 0027). These are *trade* fees. Whether
   settlement adds a second charge is exactly what `settlement_fee()` asserts
   away, and the pending settlement capture in §S6 is the direct test.
4. **This result has not been through `measurement-skeptic`.** It is good news,
   it is the analysing session's own arithmetic, and the repo's rule is that
   both of those are reasons for an independent pass.

**Registered consequence of this document: none.** It declares an attribution.
Changing `fees.py`, re-deriving the break-even bar, or re-scoring any historical
row each need their own decision and their own ADR.

## §15. Open items

1. **Capture the settlement `fee_cost`** for all five positions once settled —
   §6.2's durable channel, and the direct test of H4. **Time-critical**: the
   fills endpoint has a measured retention bound of roughly three months.
2. **§S2's census reproduction** — needs `flyctl ssh` to the live volume.
3. **§S13's narrowed `k` interval.**
4. **An independent skeptic pass** before any of this reaches `fees.py`.
