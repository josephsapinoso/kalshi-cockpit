# Pre-registration — does current-season data rescue the pitcher-K build?

**Date:** 2026-08-17
**Status:** Registered. **Nothing below has been computed.**
**Follows:** `2026-08-17-pitcher-k-baseline-decay-result.md`, which returned
**TOO STALE ALONE** — a prior-season baseline forecasts the true rate to
**0.03047**, worth **7.44 points** of ladder price against a **1.75-point** fee
advantage.

## The decision this exists to make, stated before the answer

The registered branch says "a current-season blend is required." The reflex is
to build an MLBAM adapter and re-open the licence surface ADR 0035 spent an
entire decision narrowing.

**That reflex rests on an assumption nobody has tested: that current-season data
is materially better.** If a pitcher's season-to-date rate forecasts his true
rate no better than last year's does, then no feed rescues anything, and the
honest conclusion is that **pitcher-K cannot be priced from public rate data at
the precision this venue requires** — which kills slice 2 as designed and saves
the adapter, the cache, the poll schedule and the licence argument.

The question is answerable from the file already downloaded, offline, with no
feed and no licence question. So it is answered first.

## What has already been seen, disclosed

Everything in the previous result document: the full-season pair statistics, the
per-parameter split, the season row counts. **Nothing has been computed with a
within-season cut of any kind**, and no season-to-date quantity has been
calculated, printed, or looked at.

## 1. The question

At a date inside a season, does the pitcher's **season-to-date** strikeout rate
forecast his **rest-of-season** true rate materially better than his **prior
season's full-season** rate does?

## 2. The population

`pitching.csv`, same filters as the previous registration: `stattype == "value"`,
`gametype == "regular"`, `p_gs == 1`, seasons **2015–2025**.

A pitcher-season enters at the primary cut when **all three** hold:

- **≥ 10 starts strictly before the cut date** — enough for a season-to-date
  rate to be an estimate rather than an anecdote.
- **≥ 5 starts on or after the cut date** — enough for a target to exist.
- **the same pitcher qualified in the prior season at ≥ 15 starts** — otherwise
  forecaster A below does not exist and the comparison is not defined.

The third condition is restrictive and it is the right restriction: the
comparison is *between two forecasters on the same pitcher*, so both must be
available. **The pitchers it excludes — rookies, and anyone returning from a lost
season — are counted and reported**, and are the population this measurement is
silent about, exactly as the previous one was.

**2020 is excluded**, not by a new rule but by the existing ones: it has no
qualifying prior-season partners and a 60-game schedule cannot produce 10 starts
before a July cut plus 5 after.

## 3. The cut

**Primary: July 31.** Roughly two-thirds of a season known, ~10 starts
remaining. It is the closest balanced point to the deployed case (mid-August)
that still leaves a target worth measuring.

**Pre-declared sensitivity cuts: June 15 and August 15**, run and reported
**whether or not they agree with the primary**. August 15 is the actual deployed
date and has the shortest, noisiest target; June 15 has the least information on
the left and the most on the right. Neither can replace July 31 after the fact.

## 4. The forecasters, and the target

For each qualifying pitcher-season, over starts only:

| | |
|---|---|
| **A** | prior season's **full-season** `k_per_bf` — the Retrosheet-only option |
| **B** | **season-to-date** `k_per_bf`, strictly before the cut — needs a live feed |
| **L** | the **league** season-to-date `k_per_bf` at the cut — the do-nothing benchmark |
| **C** | the in-sample OLS blend of A and B — **descriptive only, never primary** |
| **T** | the target: **rest-of-season** `k_per_bf`, on or after the cut |

## 5. The primary statistic, and why it is not a raw RMSE

**The target is short by construction and its sampling noise is large.** ~10
remaining starts is ~230 batters faced, so the binomial standard error of `T` as
an estimate of the true rate is around 0.027 — **comparable to the entire
prior-season forecast error being tested.** A raw RMSE against `T` would be
dominated by noise in the target and would make every forecaster look equally
bad, which is a way of concluding nothing while appearing to measure.

So the primary statistic is the **forecast error of the true rate**, with target
noise removed, for each forecaster `F`:

    target_noise  = RMS over pairs of  sqrt( T*(1-T) / BF_after )
    forecast_err(F) = sqrt( max( RMSE(F, T)^2 - target_noise^2, 0 ) )

**This is registered as primary because the short target is known in advance,
not discovered.** In the previous measurement the same decomposition was applied
*after* the fact and is recorded there as a post-hoc correction; here it is the
statistic.

**The decomposition is conservative, in the direction that hurts the build.**
The binomial form assumes each batter faced is an independent trial at a
constant rate, which understates real target variance (opponent quality, park,
role). Understating target noise means *overstating* forecast error, so a
verdict favourable to the build cannot be an artifact of this choice. The raw
RMSEs are printed beside the decomposed ones so the correction's size is visible.

**Primary comparison: `forecast_err(B)` against `forecast_err(A)`.**

## 6. The decision rule, fixed now

The price conversion is unchanged from the previous registration and is
recomputed the same way: build the slice-1 distribution at the league `mean_bf`,
`sd_bf` and `k_per_bf`, price rungs `2+` through `10+`, re-price at
`k_per_bf + forecast_err`, and take the **mean absolute move across rungs**. The
**max** is reported and does not decide.

Bars are the registered ones: **fee 1.75 points**, **too-stale 5.00 points**.

| condition | verdict |
|---|---|
| `forecast_err(B) >= forecast_err(A)` | **NO FEED HELPS.** Season-to-date carries nothing a year-old baseline does not. Slice 2 as designed is dead; say so and stop. Do not build an adapter. |
| `B` beats `A`, but `B`'s price error `> 5.00` pts | **NO FEED RESCUES IT.** Fresher data helps and still leaves an error larger than the previous verdict's bar. Same conclusion, reached the expensive way. |
| `B`'s price error in `[1.75, 5.00]` | **MARGINAL — the feed is a judgement call.** It would have to be argued on its own terms against the ADR 0035 licence surface, with the residual carried into suppression. |
| `B`'s price error `< 1.75` pts | **BUILD THE FEED.** Current-season data brings parameter noise inside the fee advantage; the MLBAM question becomes worth having. |

**The `C` blend may not be used to reach a better branch.** It is fitted
in-sample on the same pairs it is scored on and cannot lose to `A` or `B` by
construction. It is reported to show how much a blend *could* buy, which is an
upper bound and an argument for a future out-of-sample test, never a verdict.

## 7. Stopping rule

**One look at the primary cut, plus the two pre-declared sensitivity cuts, and
then it is done.** The file is historical and complete; there is no accumulating
data and no sequential-testing problem.

The hazard here is the opposite one and it is named so it can be caught: trying
further cut dates, further start thresholds, or a reliever-inclusive population
until a branch changes. **Any variant beyond the three cuts above is a new
registration, and its result is reported next to this one whether or not it
agrees.**

## 8. What this cannot establish

- **Nothing about beating Kalshi.** Every forecaster here is scored against the
  pitcher's own future, not against a price. Kalshi sees the same season-to-date
  data and more; a forecast that is accurate and universally known is worth
  nothing. Only `scripts/run_signal_test.py` on real rows can speak to edge.
- **It is optimistic about `B` specifically.** `B` is computed from complete,
  clean, retrospective data with no ingestion lag, no name-matching failure and
  no missing games. A live feed delivers a worse version of `B` than this.
- **Nothing about pitchers without a prior season.** Excluded by construction
  again, and again they are the starters a market is least certain about.
- **Nothing about the blend `C` out of sample.** In-sample by construction.
- **Nothing about `mean_bf` or `sd_bf`.** The previous result already settled
  those: `mean_bf` is barely a pitcher attribute (+6.9%) and per-pitcher `sd_bf`
  is **worse** than a league constant (−30.6%). This measurement is about
  `k_per_bf` only, and a finding here does not reopen them.
