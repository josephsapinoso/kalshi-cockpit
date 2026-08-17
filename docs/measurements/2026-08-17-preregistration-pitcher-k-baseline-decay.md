# Pre-registration — how far does a season-old strikeout baseline carry?

**Date:** 2026-08-17
**Status:** Registered. **Nothing below has been computed.**
**Owner of the *after*:** the `measurement-skeptic` rules in CLAUDE.md.

## Why this exists before the code

Slice 1 (`backend/model/strikeouts.py`) prices a `KXMLBKS` ladder from
`(expected_bf, sd_bf, k_per_bf)`. Slice 2 supplies those three numbers. ADR 0035
routes anything historical or derived to Retrosheet, and Retrosheet's coverage
**ends at 2025** — verified against the file, 1,274,253 rows, no 2026.

So every parameter this model uses is, at best, a season old on opening day and
gets staler all year. **That is not a detail, it is the central risk of the whole
build**: a model whose inputs are a year out of date is competing against a
venue quoting today. If a season-old baseline is badly stale, slice 2 needs a
current-season source — which re-opens the MLBAM licence surface ADR 0035 spent
a whole decision narrowing.

The decision therefore has to be made against a number, and the number has to be
fixed before it is seen. This project has been wrong twice in the *same
direction* about what it had measured (CLAUDE.md's opening section), and both
times the mechanism was a rule chosen after the answer was visible.

## What has already been seen, disclosed

The file's **column names**, its **row count** (1,274,253), its **per-season row
counts** for 2020–2025 (~21,000/season, 8,499 in 2020), and **one row** — Al
Orth, 1897-04-19, 35 batters faced, 3 strikeouts. That is all. No rate, no
aggregate, no pairing, and nothing about any pitcher after 1897 has been
computed or looked at.

## 1. The question

Does a pitcher's **prior-season** strikeout rate predict his **next-season**
strikeout rate well enough to price a ladder — and if so, how hard must it be
shrunk toward the league mean?

## 2. The population

From `pitching.csv` (`retrosheet.org/downloads/pitching.zip`):

- `stattype == "value"` — the file carries other stattypes; only actual values.
- `gametype == "regular"` — no postseason, no exhibition.
- `p_gs == 1` — **starts only.** A reliever's batters-faced distribution is a
  different problem and slice 1's compound is explicitly not about it.
- Seasons **2015–2025** inclusive, taken from `date`.

A **pitcher-season** is one `id` in one season. It enters the population when it
has at least **`MIN_STARTS = 15`** starts.

**15 is fixed here and not tuned.** It is roughly half a full starter's season,
so it admits pitchers who were injured or called up mid-year while excluding
spot starts and openers, whose rates are not estimates of the same quantity.
Any other threshold is a *sensitivity check* reported alongside, never a
replacement for this one.

**2020 is included and flagged, not dropped.** It is a 60-game season, so it
enters with far fewer qualifying pitcher-seasons and a shorter denominator per
pitcher. Dropping it would be a defensible choice made *after* seeing that it
was inconvenient; including it and reporting the pairs it contributes separately
is the choice that cannot be contaminated. **Both pairs it touches (2019→2020
and 2020→2021) are reported as their own row** in the per-group view.

## 3. The unit and the statistic

For each qualifying pitcher-season, over that season's starts only:

    k_per_bf   = sum(p_k)   / sum(p_bfp)
    mean_bf    = mean(p_bfp)
    sd_bf      = sample standard deviation of p_bfp

A **pair** is one pitcher qualifying in season `Y` and in season `Y+1`. The
estimand is over pairs, not over pitcher-seasons.

**The primary statistic is `RMSE_prior`:** the root-mean-square error of using
season `Y`'s `k_per_bf` directly as the forecast of season `Y+1`'s.

**Its benchmark is `RMSE_league`:** the same error from forecasting every
pitcher with season `Y`'s **league** `k_per_bf` (pooled over the qualifying
population of season `Y`). This is the do-nothing model. A per-pitcher baseline
that cannot beat it is not worth reading a 21MB file for.

Reported beside them, and **not** promotable to primary afterwards:

- `slope` and `intercept` of the OLS of `k_per_bf(Y+1)` on `k_per_bf(Y)`. The
  slope is the shrinkage the model should apply; a slope of 0.6 means a
  pitcher's edge over league average should be taken at 60% of face value.
- `RMSE_shrunk`, from the fitted line. **In-sample, and labelled so**: it cannot
  lose to `RMSE_prior` by construction, so it is a description of the fit and
  never evidence for it.
- The same three errors for `mean_bf` and for `sd_bf`, which slice 1 needs too.

## 4. The decision rule, fixed now

Converted into the unit that matters, because an RMSE in strikeouts-per-batter
is not a thing anyone can judge. The conversion is **not** a hand coefficient:
it is computed by perturbing the model itself.

**The conversion, fixed now.** Build the slice-1 distribution at the league
`mean_bf`, `sd_bf` and `k_per_bf` measured in §3. Price a representative ladder
— the rungs `2+` through `10+`, which is what Kalshi published on the 4 captured
games. Re-price it at `k_per_bf + RMSE_prior`. **The price error is the mean
absolute move across those rungs**, and the **maximum** move across them is
reported beside it but does not decide the verdict.

Mean rather than max because a ladder is bought at one rung, not all nine, and
the max is always the rung nearest 50c where sensitivity peaks — using it would
make every verdict harsher by a factor nobody chose. Mean rather than the
50c-rung alone because which rung sits at 50c is a property of the pitcher, not
of the model. Both are printed so the choice can be second-guessed without a
re-run.

The thresholds are set on that number now:

| `RMSE_prior` vs `RMSE_league` | implied price error | verdict |
|---|---|---|
| `RMSE_prior >= RMSE_league` | — | **USELESS.** A season-old per-pitcher rate carries nothing the league mean does not. Slice 2 needs a current-season source; ADR 0035's live layer is back on the table and must be re-argued. |
| `RMSE_prior < RMSE_league` and price error `> 5.0` points | > 5.0 pts | **TOO STALE ALONE.** Better than nothing and still larger than any edge this project is hunting — the fee bar is 1.75 points. A current-season blend is required. |
| price error in `[1.75, 5.0]` points | 1.75–5.0 pts | **MARGINAL.** Usable only with the shrinkage applied and with the residual carried into suppression, not discarded. |
| price error `< 1.75` points | < 1.75 pts | **SUFFICIENT.** Retrosheet alone supports slice 2, and the MLBAM live layer is not needed for pitcher-K at all. |

**1.75 points is not chosen for this test.** It is the taker break-even bar
already registered in CLAUDE.md and ADR 0028. A parameter error the size of the
entire fee advantage cannot be spent on parameter noise.

## 5. What would falsify the build

**If the verdict is USELESS, slice 2 as designed is dead** and the honest move
is to say so rather than to reach for a live feed and re-run. A pitcher's own
strikeout rate failing to predict his next season, on ~10 years of pairs, would
mean the quantity slice 1 is built around is not a stable pitcher attribute —
and no amount of freshness rescues a model of a thing that does not persist.

## 6. Stopping rule

**One look, on the full 2015–2025 population, and then it is done.** There is no
accumulating data here — the file is historical and complete, so there is no
sequential-testing problem and no always-valid multiplier is needed. The
corresponding hazard is the opposite one: re-running with a different
`MIN_STARTS`, a different season window, or reliever rows included until a
verdict changes. **Every such variant is a sensitivity check, is reported
whether or not it agrees, and does not replace §3.**

## 7. What this cannot establish

- **Nothing about beating Kalshi.** It measures a parameter against the pitcher's
  own future, not a price against a market. A perfectly forecast `k_per_bf` and
  a ladder Kalshi has already priced correctly still yields zero edge. Only
  `scripts/run_signal_test.py` on slice 3's rows can speak to that.
- **Nothing about pitchers with no history.** Pairs require two qualifying
  seasons by construction, so rookies and call-ups are *excluded from the
  population* — and they are precisely the starters a market is least certain
  about. Their coverage is a separate count, reported, not modelled here.
- **Nothing about 2026 specifically.** The most recent pair available is
  2024→2025. The claim is about a one-season gap in general; the live gap on
  opening day 2026 is one season, and by August it is one season plus five
  months. **The measurement is therefore optimistic about the deployed case**,
  and the write-up must say so in those words.
- **Nothing about within-season drift**, injury, role change, or a pitcher
  traded to a different league. All are folded into the residual.
