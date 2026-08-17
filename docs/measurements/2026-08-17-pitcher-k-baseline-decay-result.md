# Result — a season-old strikeout baseline is TOO STALE ALONE

**Date:** 2026-08-17
**Registered:** `2026-08-17-preregistration-pitcher-k-baseline-decay.md`
**Harness:** `scripts/measure_pitcher_k_decay.py`
**Source:** Retrosheet `pitching.zip`, retrieved 2026-08-16 (file dated
2026-08-09).

> The information used here was obtained free of charge from and is copyrighted
> by Retrosheet.

## Verdict

```
RMSE_prior   0.03479     the registered primary
RMSE_league  0.04910     the do-nothing benchmark
improvement  +29.1%
slope        0.7724      intercept 0.04807

price error  8.47 points mean across rungs   (max 14.54)
bars         fee 1.75 pts   too-stale 5.00 pts

VERDICT      TOO STALE ALONE
```

**Both halves of that verdict are load-bearing and they point opposite ways.**

A pitcher's own prior season **does** carry real information — it beats the
league mean by 29.1%, and it does so in **every one of the eight pair-years**,
from +16.0% to +36.2%. This is not USELESS. The quantity slice 1 is built around
is a genuine, persistent pitcher attribute.

And it is **nowhere near good enough on its own.** Converted into the unit that
decides, the residual moves a ladder by **8.47 points** on average across its
rungs. The entire taker fee advantage this project exists to exploit is **1.75
points** (ADR 0028). The parameter noise is roughly **five times the whole
edge**. Pricing a ladder off Retrosheet alone would not be competing with
Kalshi; it would be adding noise five times larger than the prize.

## The population, and it is unusually clean

| | |
|---|---:|
| starts in window (2015–2025, regular season, `p_gs == 1`) | **50,382** |
| **unreadable, dropped** | **7 (0.014%)** |
| starts per season | **4,856–4,860**, except 2020 |
| pitcher-seasons | 3,828 |
| qualifying at ≥15 starts | 1,493 |
| **pairs (qualified in Y and Y+1)** | **772** |
| largest single pair-year's share | 13.5% |

4,856–4,860 starts per season is **exactly two per game** across a 2,430-game
schedule. The file is complete, not a sample, and the 7 unreadable rows are the
whole of the data-quality question.

**The first run's log says `unreadable dropped 6,143` and that number describes
nothing.** It counted blank `p_bfp` across all 1,274,253 rows back to 1897,
where early box scores genuinely lack the field — a count spanning a population
and its complement. Inside 2015–2025 the figure is **7**. The harness now splits
the two counters and re-running reproduces `kept 50,375` exactly, so the fix
changed the reporting and not the result. The old figure is recorded here
because it appears in the original run log.

## 2020 did not need flagging — it is absent

The registration said 2020 would be **included and flagged** as a 60-game
season, with both pairs it touches reported separately. Neither pair appears in
the output, and the reason is that **no 2020 pitcher-season qualified at all**:
294 pitcher-seasons, **maximum 13 starts**, against a `MIN_STARTS` floor of 15.

So `MIN_STARTS = 15` removed the short season on its own. That is the right
outcome and it was reached by a rule fixed before the data was seen — but the
registration predicted the wrong mechanism, and the write-up says so rather than
claiming the plan worked as written. **2019→2020 and 2020→2021 are missing rows
in the per-year table, not omitted ones.**

## The parts agree, which is what lets the pooled number be read

| Y→Y+1 | pairs | RMSE_prior | RMSE_league | improvement |
|---|---:|---:|---:|---:|
| 2015→2016 | 98 | 0.03194 | 0.04222 | 24.3% |
| 2016→2017 | 104 | 0.03568 | 0.04976 | 28.3% |
| 2017→2018 | 101 | 0.03736 | 0.05410 | 31.0% |
| 2018→2019 | 94 | 0.03554 | 0.05567 | 36.2% |
| 2021→2022 | 101 | 0.03314 | 0.04945 | 33.0% |
| 2022→2023 | 90 | 0.03587 | 0.04887 | 26.6% |
| 2023→2024 | 93 | 0.03543 | 0.04219 | 16.0% |
| 2024→2025 | 91 | 0.03295 | 0.04852 | 32.1% |

Eight of eight positive, no year driving the aggregate, largest contributor
13.5%. The pooled +29.1% is a finding rather than an artifact of one season.

## A correction the registration did not anticipate, and it does not rescue anything

`RMSE_prior` is measured against **next season's realised rate**, which is
itself an estimate — a median of **676 batters faced**. Binomial sampling noise
in the *target* is therefore inside the residual, and it is not a parameter
error: no forecast, however good, could remove it.

```
RMSE_prior              0.03479
target sampling noise   0.01678   (irreducible)
=> error in the TRUE rate 0.03047  ->  7.44 points mean (max 12.78)
```

**The verdict is unchanged.** 7.44 points is still above the 5.00-point
too-stale bar and still more than four times the 1.75-point fee bar. The
decomposition is recorded because it is the strongest available argument in the
flattering direction, and it does not work.

## The three parameters behave completely differently, and this changes the design

| parameter | RMSE_prior | RMSE_league | improvement |
|---|---:|---:|---:|
| `k_per_bf` | 0.03479 | 0.04910 | **+29.1%** |
| `mean_bf` | 1.5175 | 1.6304 | **+6.9%** |
| `sd_bf` | 1.2595 | 0.9643 | **−30.6%** |

- **`k_per_bf` is a real pitcher attribute.** Use it, shrunk: the OLS slope is
  **0.7724**, so a pitcher's deviation from league average should be taken at
  ~77% of face value, never at face value.
- **`mean_bf` is barely a pitcher attribute at all.** +6.9% over a league
  constant. How long a starter lasts is mostly not about who he is.
- **`sd_bf` is worse than a league constant — by 30.6%.** A pitcher's own
  prior-season spread of batters faced is *actively misleading* about his next
  season's. **Slice 2 must use the league `sd_bf`**, and a version that
  helpfully passed the per-pitcher value would be measurably worse than one that
  did not.

That last row is the kind of thing a build discovers after shipping, if it
discovers it at all.

## What this means for slice 2

The registered TOO STALE ALONE branch says: *"Better than nothing and still
larger than any edge this project is hunting. A current-season blend is
required."*

**Do not build the current-season feed yet.** The obvious next move is to reach
for MLBAM and re-open the licence surface ADR 0035 spent a whole decision
narrowing — and it would be reaching for it on an assumption nobody has tested.
**The untested assumption is that current-season data is materially better**,
and it is answerable from this same file, offline, with no feed and no licence
question: split a season at a date, forecast the rest of it from what was known
by then, and compare against this 7.44-point floor.

If in-season-to-date is not much better than a year-old baseline, then **no feed
rescues the design** and the honest conclusion is that pitcher-K cannot be
priced from public rate data at the precision this venue requires. That is a
cheaper thing to find out now than after an adapter, a cache, a poll schedule
and a licence argument.

Registered separately before it is run.

## What this does not establish

- **Nothing about beating Kalshi.** It scores a parameter against the pitcher's
  own future, not a price against a market. Kalshi may be worse; this cannot say.
- **Nothing about pitchers with no history.** 721 qualifying pitcher-seasons
  have no following season in the population and are excluded by construction,
  and rookies never enter at all. A first-year starter is the pitcher a market
  is least certain about and the one this measurement is silent on.
- **It is optimistic about the deployed case.** The gap measured is exactly one
  season. The live gap in August 2026 is one season **plus five months**, so the
  true deployed error is larger than 8.47 points, not smaller.
- **Nothing about the 8.47-point conversion being the right summary.** It is the
  mean absolute move across rungs `2+` to `10+`, fixed in §4 before the run. The
  max is 14.54. A reader who thinks the traded rung is what matters should use
  the max, and the verdict gets worse, not better.
