Registered in [`2026-08-09-preregistration-clv-signal-test.md`](2026-08-09-preregistration-clv-signal-test.md) (§8: this file is written whichever way it comes out).

# CLV signal test — result at the stopping rule. UNRESOLVED

**Ticket:** #226.
**Stopped by:** §7 condition 1, `G = 1000` modal-version clusters on the registered key `COALESCE(event_ticker, ticker)` (§3), scored at horizon 0.0. These are 889 distinct games: all 111 prop clusters share a game with a moneyline cluster. The cluster-robust se treats each prop event as independent of its game's moneyline, which narrows the interval. On a game key the stop would not yet have fired, and the 861 floor clears by 28. Reached at T* = **2026-09-27T00:47:26.874Z** (`1790470046874`).
**Population:** every §2 row with `clv_scored_ms <= T*`; §P4 modal version **4** (same as the full record: **yes**). G at T* = **1000** exactly; no scoring batch carried it past.
**Cut rule:** fixed in the registration's 2026-09-30 NOT-AN-AMENDMENT note, committed before this pull.
**Floor:** raised to **nominal G >= 861** by Amendment 3 (2026-10-01), written after this pull printed `sigma` and before this file declares, by §B4's own formula. 1000 clears it. `G_eff` is reported beside it and is never a threshold (§B7).
**Harness:** `scripts/run_signal_test.py pull.json --through-clusters 1000`, on `inspect_live_db.py clv-signal-pull --json --limit 1000000 --i-accept-the-cache-flush`, pulled from live 2026-10-01T06:00:47Z (off-hours, Joe's approval of 2026-09-30), **157,372 rows, `truncated: false`**. Earliest `created_ms` 2026-08-08T00:04:55Z, earliest `clv_scored_ms` 2026-08-09T03:17:05Z. `pull.json` is operator data and is not committed.

**In one line:** §6 alone says NO SIGNAL; §A4 lowers it to UNRESOLVED, because leaving out the `too_few_books` rows (fair values off too few books; on this cut their `edge_tenths` has sd 105.2 against 18.2 elsewhere and runs to −718, but 64% have |edge| ≤ 40, and the rows left without them still reach −868.9 — computed from pull.json at audit, not printed by the harness) turns `beta` into +0.31 with an upper limit of +0.64, above the 0.40 threshold. UNRESOLVED is a real answer and is not "no signal".

## 1. Population (n before effect)

```
rows in cut 147,182 (10,190 rows scored after T*; 0 with clv_scored_ms NULL)
rows analysed 145,085   G 1000   unclustered 0
§A8.2 matched 145,085   quote_mismatch 0   no_quote 0
P1 = 1.0000 (floor 0.90)
strategy_config_version {1: 359, 2: 56, 3: 1682, 4: 145085}  -> 2,097 non-modal rows excluded
```

P1 is 1.0000. All 3,692 rows of the 2026-08-16 pull are in this cut, identical in every shared column including `quote_observed_ms` and `half_spread_tenths`, and the 415 rows created before 2026-08-10 carry a quote on 415. Those 415 are versions 1–2 and outside the primary; the earliest modal row is 2026-08-15T19:52Z. Retention (#122, 60 days) keys on `COALESCE(confirmed_ms, observed_ms)` (`backend/store/retention.py:252`), so 2026-10-07 is the earliest a joined quote can go. A re-pull after it may not reproduce this population.

## 2. Noise and the C2 confound (measured)

```
sd(half_spread_tenths)   11.1333
sd(edge_tenths)          42.0564
sd(clv_tenths)           35.4271
implied spurious slope   0.070079   Var(half)/Var(edge)
```

`sigma_eps`, `sigma_x` and their ratio against the assumed 2 (§A9 item 2) are **not printed by the harness**; this is recorded as a gap, not filled in by hand.

**§B6(5) ratchet line:** `sd(clv_tenths)` on the modal population at T* = **35.4271, which exceeds 31.6915.** The floor was re-solved by §B4's formula to **G >= 861** (G = 860 gives MDE 3.8021 > 3.8; G = 861 gives 3.7996), in Amendment 3, written before this declaration. The slope MDE at 861 is 0.319 at the 2026-08-25 ratio 2.976, and 0.380 at ratio 3.543 (this look's raw sd 35.4271, which bounds sigma_eps from above, over the registered sigma_x = 10). Both are below 0.40, so the threshold stands.

## 3. Record state

`BANKROLL_DOLLARS`, open exposure and daily P&L (§A5.1) are **not printed by the harness** and were not read for this file. The engine path is dry (`ORDERS_ARE_DRY_RUNS = True`) and has never placed an order, so none of the rows above was transacted. Version distribution: section 1.

## 4. Resolving power at this G (before the estimate)

```
always-valid multiplier   3.1137
smallest resolvable beta  0.0619
G nominal 1000   G_eff (Kish, on leverage) 57.76   largest cluster's leverage share 0.0680
```

## 5. The estimate and the verdict

```
beta_hat        +0.0401
gamma_hat       -1.1391   (half-spread)
se_cluster       0.0199   (se_classical 0.0022, not used)
always-valid    [-0.0217, +0.1020]
```

Largest registered group's leverage share: **`too_few_books` / `no_market_width`, 0.8904** (§A4; the two flags mark the same 19,374 rows).

§6 alone: **NO SIGNAL** (upper limit +0.1020 < 0.40 at G >= 861).
After §A4: **UNRESOLVED.** In §A4's words, removing the pre-registered group `too_few_books` did not leave the claim standing: with it removed, G = 886, `beta` = **+0.3084**, upper limit **+0.6441**, which is above 0.40. The same interval's lower limit is about −0.027 (beta minus its half-width 0.3357; derived, not printed). The leave-one-out shows no signal either; it only fails to rule out 0.40. The rule is one-way and cannot raise a verdict.

UNRESOLVED is a real answer and is not "no signal".

## 6. §A4 per-group table

```
group                          n  clus  leverage  G left      beta     upper
unsuppressed              121904   886    0.0564     827   +0.0078   +0.0477
no_depth                       0     0    0.0000    1000   +0.0401   +0.1020
insufficient_depth          4765   476    0.0712    1000   +0.0380   +0.0962
too_few_books              19374   712    0.8904     886   +0.3084   +0.6441
no_market_width            19374   712    0.8904     886   +0.3084   +0.6441
wide_market                  488    48    0.0444    1000   +0.0418   +0.1067
edge_within_method_noise    1106   202    0.0354     994   +0.0408   +0.0980
suspicious_edge              920   153    0.5233     976   +0.0945   +0.2147
sizing:refused                 0     0    0.0000    1000   +0.0401   +0.1020
skeptic_*                      4     4    0.0000    1000   +0.0401   +0.1020
gridA[10,200)              14868   239    0.4823     952   +0.0770   +0.1963
gridA[200,800)            115760   806    0.2598     264          UNTESTABLE
gridA[800,990)             14457   216    0.2579    1000   +0.0451   +0.1210
UNTESTABLE = removal leaves G < 300. §A4: not grounds for downgrade.
```

The `too_few_books` group carries 0.8904 of the leverage, so **the pooled NO-SIGNAL reading is mostly that group's reading.** Its removal is what keeps the verdict open, and if those rows are bugs, the pooled +0.1020 is mostly a bug's reading and cannot carry the planning posture on its own; the population left without them is not clean either. The 0.31 that remains without them is **not a finding**: §A4 can only lower a verdict, and no group in this table is a result.

Diagnostic only, not a registered cut (6b): moneyline n = 143,529, G = 889, 98.9% of rows, beta +0.0409; prop n = 1,556, G = 111, beta −0.4360.

## 7. Grids A and B — DESCRIPTIVE, CANNOT PRODUCE A FINDING

`family_wise_p`, `family_wise_verdict` and Grids A/B are **not computed by the harness.** The three Grid A edge bands appear only as §A4 leave-one-out rows above.

The §5 level statistic (mean of game-clustered `clv_tenths`) is not computed by the harness. Its null is about −5 tenths, not zero (§A6: whole-cent ADR 0006 candlesticks, two leagues, one August slate). It is descriptive and cannot change the verdict. Its effective-cluster count, which §B7 says leaves the level floor's reachability unestablished, is also unmeasured.

## 8. horizons_agree — the weak control

Not computed by the harness. `clv.horizons_agree` is reached by nothing that runs (ADR 0120).

## 9. The games after the stop, reported beside it (not the result)

Full record at the pull: G **1055** (+55 games after T*), rows analysed 155,275, sd(clv_tenths) 36.0995, G_eff 58.60, beta **+0.0418**, interval **[−0.0199, +0.1036]**, §6 NO SIGNAL, §A4 UNRESOLVED (`too_few_books` removed: G 941, beta +0.3085, upper +0.6332). Diagnostic: moneyline G 942 beta +0.0426; prop G 113 beta −0.4337.
Live strip on 2026-09-30, for reference: G = 1047, G_eff 58.56, beta +0.0424, interval [−0.0194, +0.1042], UNRESOLVED. None of this changes the verdict above.

## 10. What happens now (§8's table, the row that applies)

**UNRESOLVED at the stopping rule — nothing is built.** Interval [−0.0217, +0.1020] at G = 1000 (G_eff 57.76). §8's own consequence for this row ("the timeline, not the hypothesis") was written for a record that could not reach `G = 300`; this one reached 1000, so what kept the verdict open is not the recording rate but §A4's leave-out of `too_few_books`, a group carrying 89% of the leverage (G_eff 57.76 of 1000 nominal, §B7).

The planning posture does not move, and the pooled upper limit is not what holds it, since +0.1020 is 89% the `too_few_books` rows' reading. What holds it is that no fit in this file shows a signal: every always-valid lower limit, pooled and in every testable leave-one-out, is at or below zero (−0.042 to −0.016, derived as 2·beta − upper). The engine stays dry. Reopening the question needs a **successor registration with an `edge_tenths` (or `too_few_books`) exclusion fixed in advance**, and that accrues its own record from the moment it is registered (§B7), not a re-read of this table. An exclusion chosen after this table and scored on these rows would be choosing the population from the answer, and +0.31 is what it would find.

**What this does not extend to:** UNRESOLVED at G = 1000 clusters (889 games) says no fit shows a positive pass-through. It does **not** say 0.40 is ruled out on rows with sound fair values: that interval is about [−0.03, +0.64].

## 11. What this cannot establish — §9 as amended by §A8, verbatim

### §9

Caveats written afterwards are selected to be survivable. These are written now.

- **It does not establish that `fair_probability` is calibrated against
  reality.** That is a separate question and is **currently unrunnable**:
  `kalshi_markets.result` is never written by any live code path, and
  `analysis` reads settlements `FROM orders`, of which there are zero real ones.
  No statement about win rates, calibration, or accuracy may be made from this
  measurement.
- **CLV is not profit.** It can be positive while the account shrinks. It is the
  fastest honest proxy, not the thing itself.
- **It does not establish that any bet clears the fee.** `beta > 0` says the edge
  estimate *ranks* games. Whether the level clears 52.00% is §5's other
  statistic, with a different null and a spread offset in it.
- **The close is a mid; the entry is an ask.** The level is contaminated by the
  half-spread by construction, and the slope is decontaminated only to the extent
  `half_spread_tenths` is correctly measured on enough rows (P1). If P1 lands
  between 0.90 and 1.00, the residual contamination is proportional to the
  missing fraction and must be stated as a number.
  > **[SUPERSEDED by Amendment 1 §A8.3 — text retained.]** The proportionality
  > claim is wrong. §S1 **drops** rows with a NULL half-spread; it does not
  > impute them. Residual contamination on retained rows is therefore **zero**,
  > and what the missing fraction creates instead is a **selection** problem of
  > unknown direction. §A8 adds two further omissions.
- **Candlestick closes are unsized.** A price nobody could have transacted counts
  the same as one that could.
- **The scored sample skews early, by construction.** Rows created inside the
  final 15 minutes go unscored at this horizon (ADR 0011, decision 1). Time to
  kickoff correlates with how much the market has already moved, so the scored
  set is a **non-random subset** of recommendations — and the direction of that
  bias is not known and is not estimated here.
- **Only markets with a readable candlestick within 15 minutes of kickoff are
  scored.** That is a liquidity-flavoured sample. Markets that never developed a
  quote are absent, and their absence is not random.
- **One horizon is one snapshot.** The horizon-1.0 rows are the control (§F3),
  and they are a *weak* control: they are a different, earlier, pre-ADR-0011
  population, not a re-scoring of the same rows.
- **It is one season and the leagues that were in it.** The recording window
  opens on an August 2026 slate — MLB, WNBA, NFL preseason. It says nothing about
  NBA, NCAAF, or NFL regular season, and nothing about in-play (ADR 0006).
- **It says nothing about combos.** `KXMVE` is a separate product on a separate
  path (ADR 0012).
- **`edge_tenths` is measured at one contract, not at the size that defines
  `actionable`.** See §F2. The regressor is therefore a *more conservative* edge
  than the one the record's population predicate is built on, by up to 5 tenths.
- **The boundary assumes clustered observations are independent across games and
  identically distributed.** Same-day games sharing a weather event, a referee
  assignment, or a market-wide liquidity shock violate that, and nothing here
  corrects for it.


### §A8 (headings demoted two levels; text verbatim)

#### A8. Three additions to §9, "what this cannot establish"

**Why they are needed.** §9 as registered omits the entries that could actually
overturn the result. Caveats that cannot overturn anything are the ones that get
written; these are the other kind.

##### A8.1. The shared `−entry_ask` term contaminates beyond the half-spread

Add to §9:

> - **Controlling `half_spread` removes only the *deterministic* part of the
>   shared-ask contamination.** C2 decomposes the ask as mid plus half-spread,
>   but `clv_tenths` and `edge_tenths` share the **whole** `-entry_ask` term, not
>   just its spread component. **Any transient dislocation in the entry ask — a
>   momentary thin book, a single large resting order, a quote taken mid-update —
>   lowers both `edge` and `clv` together**, and such a dislocation is by
>   definition not captured by the half-spread of that same quote. The residual
>   covariance is therefore positive and is **not** removed by `gamma`. Its
>   magnitude is unmeasured and no attempt is made here to bound it.

##### A8.2. The half-spread control may be joined from the wrong quote — and P1 conflates two failures

§S1 joins *the latest quote at or before `created_ms`*, which is **not
necessarily the quote that set `entry_ask_tenths`**. If they differ, the control
is measured with error, the control is **attenuated**, and — because
under-controlling for a positively-contaminating confound leaves part of it in —
the residual bias in `beta` is **positive**. The flattering direction.

The check is free, because the derived-ask identity is exact
**[COMPUTED FROM CODE — `runner.py:875-895`: a YES ask is filled by the resting
NO bid, so `yes_ask = 1000 - no_bid`; a NO ask is filled by the resting YES bid,
so `no_ask = 1000 - yes_bid`]**. Add to §S1's select list:

```sql
  CASE r.side
    WHEN 'yes' THEN ((1000 - q.no_bid_tenths)  = r.entry_ask_tenths)
    WHEN 'no'  THEN ((1000 - q.yes_bid_tenths) = r.entry_ask_tenths)
  END                                             AS quote_matches_entry,
```

**And P1 is split, because as registered it conflates two different failures**
and refuses only the second. Three counts are reported, never two:

| Count | Meaning | Treatment |
|---|---|---|
| `matched` | a quote joined **and** `quote_matches_entry` is true | the analysis population |
| `quote_mismatch` | a quote joined and the identity **fails** | **retained**, but counted and reported separately |
| `no_quote` | the join returned nothing; `half_spread_tenths IS NULL` | dropped, never imputed |

- **P1's 0.90 floor now applies to `matched / total`**, not to non-NULL
  half-spread coverage. That is a strictly tighter gate than the one registered.
- `quote_mismatch` rows are **retained** — the alternative is an exclusion whose
  rate correlates with book activity, which is worse — but if
  `quote_mismatch / total` exceeds 0.05 the write-up must state, in these words,
  that the half-spread control is attenuated on that fraction and that the
  residual bias in `beta` runs **positive**.

##### A8.3. The P1 shortfall is a selection problem, not a proportional one

**What was registered.** §9: *"If P1 lands between 0.90 and 1.00, the residual
contamination is proportional to the missing fraction and must be stated as a
number."*

**Why it was wrong.** §S1 **drops** rows with a NULL half-spread; it does not
impute them. So there is **zero** residual contamination on the rows that are
retained — every one of them has a real control. What the missing fraction
creates is a different problem entirely, and a worse-behaved one.

**What now governs.** Replace that bullet with:

> - **A P1 shortfall is a selection problem of unknown direction, not a residual
>   contamination.** Retained rows are fully controlled. The rows that are gone
>   are those for which no readable pre-entry quote existed, which is a
>   liquidity-flavoured and time-of-day-flavoured criterion, and the direction in
>   which that shifts `beta` is **not known and is not estimated here**. Stating
>   it as "contamination proportional to the missing fraction" would understate
>   it, because a proportional bias shrinks to nothing as coverage approaches 1
>   while a selection effect need not.

##### A8.4. Two limitations that follow from this amendment

Also add to §9:

> - **`edge_tenths` is a discontinuous and locally non-monotonic function of the
>   underlying gross gap, and the record does not say which basis each row
>   used.** See §A5.1. Steps of up to 5.0 tenths, varying with price, zero at
>   50c, negative at 30c and 70c. The direction of the resulting bias in `beta`
>   is unknown and is not claimed to be conservative.
> - **`method_spread_probability` is not stored**, so the rows that
>   `edge_within_method_noise` would have removed cannot be identified in the
>   record, and the width of the hole that rule punches in the regressor cannot
>   be measured after the fact. §A2.1 retains those rows precisely because the
>   alternative is an unmeasurable, price-dependent exclusion.

