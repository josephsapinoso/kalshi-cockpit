# Result — NO FEED RESCUES IT. Slice 2 as designed is dead.

**Date:** 2026-08-17
**Registered:** `2026-08-17-preregistration-in-season-vs-stale-baseline.md`
**Harness:** `scripts/measure_in_season_vs_stale.py`
**Source:** Retrosheet `pitching.zip`, retrieved 2026-08-16.

> The information used here was obtained free of charge from and is copyrighted
> by Retrosheet.

## Verdict — all three cuts, same answer

```
CUT 07-31  (PRIMARY, registered)   644 pairs, median 10 starts / 240 BF after

  forecaster                          raw RMSE   forecast err   price (mean)
  A  prior season (Retrosheet only)    0.04551      0.03549       8.29 pts
  B  season-to-date (needs a feed)     0.04203      0.03091       7.23 pts
  L  league season-to-date             0.05816      0.05071      11.76 pts
  C  blend  [IN-SAMPLE, upper bound]   0.03968      0.02761       6.47 pts

  bars: fee 1.75 pts, too-stale 5.00 pts
  VERDICT   NO FEED RESCUES IT
```

| cut | pairs | A | B | **C (in-sample upper bound)** | verdict |
|---|---:|---:|---:|---:|---|
| **07-31 primary** | 644 | 8.29 | **7.23** | **6.47** | NO FEED RESCUES IT |
| 06-15 sensitivity | 620 | 7.91 | 7.64 | 6.36 | NO FEED RESCUES IT |
| 08-15 sensitivity | 609 | 8.27 | 6.69 | 6.09 | NO FEED RESCUES IT |

*(price columns are mean absolute ladder move in points, §6's registered
conversion)*

## What this establishes, and it is stronger than the verdict name

**Current-season data does help.** At the primary cut `B` beats `A` in **8 of 8
seasons**, and at the deployed 08-15 cut in 7 of 8. Fresher is genuinely better,
and the league benchmark `L` is far worse than either, so pitcher identity
matters throughout. None of that is in doubt.

**And it does not help nearly enough.** `B` at the primary cut is **7.23 points**
against a **1.75-point** fee advantage and a **5.00-point** too-stale bar. It
moves the error from 8.29 to 7.23 — a 13% reduction on a quantity that needs to
fall by 80%.

**The decisive number is `C`, and it is decisive because it cannot be beaten.**
`C` is the optimal blend of `A` and `B`, fitted **in-sample on the very pairs it
is scored on**. It cannot lose to either input by construction, so it is a hard
**upper bound** on what any blending scheme could achieve — including one with a
better estimator, better shrinkage, or a longer lookback.

**That upper bound is 6.47 points at the primary cut, 6.09 at the deployed one.**
Both are above the 5.00-point too-stale bar and roughly **3.5× the entire fee
advantage.** So the conclusion does not depend on the blend being implemented
well, or at all:

> **There is no way to combine public rate data — historical, current-season, or
> any weighting of the two — that brings pitcher-K parameter noise inside the
> cost advantage this venue provides.**

And `B` here is a *best case that no feed can deliver*: complete, clean,
retrospective data, no ingestion lag, no name-matching failure, no missed game,
and a blend weight fitted with knowledge of the answer.

## The registered decision, applied

§6's branch for `B` beating `A` with a price error above 5.00 points reads:

> **NO FEED RESCUES IT.** Fresher data helps and still leaves an error larger
> than the previous verdict's bar. Same conclusion, reached the expensive way.

**Do not build the MLBAM adapter.** The licence surface ADR 0035 narrowed stays
closed, and it stays closed on evidence rather than on caution. The adapter, the
cache, the poll schedule, the name-matching layer and the licence argument are
all saved.

## Why the primary is a decomposed error, not a raw RMSE

Registered in §5 **before the run**, because the short target was known in
advance. Rest-of-season at the primary cut is a median of **240 batters faced**,
whose binomial standard error is **0.02849** — comparable to every forecast
error being compared. Raw RMSEs would be noise-dominated and would rank all
forecasters as roughly equally bad, which is a way of concluding nothing while
appearing to measure.

**The decomposition is conservative against the build**: the binomial form
assumes independent trials at a constant rate and so understates real target
variance (opponent quality, park, role), which means it *overstates* forecast
error. A favourable verdict could not have been an artifact of it — and the
verdict is unfavourable anyway. Raw RMSEs are printed beside the decomposed ones
so the correction's size is visible.

## Where the parts disagree, stated plainly

At the primary cut, `B` wins in **8 of 8** seasons — the aggregate is not one
season's doing, largest contributor 13.7%.

**At the June 15 cut it wins in only 3 of 8**, losing in 2017, 2022, 2023, 2024
and 2025. That is the honest weak spot in the finding, and it is the cut with
the least season-to-date information, which is the direction that makes sense:
half a season of starts is not yet enough to beat a full prior season. It does
not affect the verdict — June 15's `B` is 7.64 points and its in-sample `C` is
6.36 — but a reader should know that "current-season data helps" is a
cut-dependent claim while "nothing helps enough" is not.

## Population

| | 07-31 | 06-15 | 08-15 |
|---|---:|---:|---:|
| qualifying pairs | 644 | 620 | 609 |
| **excluded — no qualifying prior season** | **494** | 424 | 492 |
| median starts after cut | 10 | 17 | 8 |
| median BF after cut | 240 | 402 | 185 |

**The exclusion is large and it is the same one as last time.** 494 pitcher-
seasons at the primary cut have no qualifying prior season, so they are outside
everything above. They are rookies and pitchers returning from a lost year — and
they are precisely the starters a market is least certain about, which is where
an in-house model would most plausibly have found an edge. **This measurement is
silent on them, and so was the previous one.** That is the one door this result
does not close, and it is noted so that a future session can decide about it
deliberately rather than inherit it as an oversight.

## What this does not establish

- **Nothing about beating Kalshi.** Every forecaster is scored against the
  pitcher's own future, not against a price. Kalshi sees the same season-to-date
  data and more.
- **Nothing about pitchers with no prior season** — 494 of them at the primary
  cut, excluded by construction. See above; this is the live remaining question,
  not a footnote.
- **Nothing about a better model of the same data.** `C` bounds *linear blends
  of these two rates*. A model using batter-level matchups, park, catcher
  framing or pitch-level data is not bounded by it — it is also a completely
  different build, needs sources this project does not have, and would have to
  clear the same 1.75-point bar.
- **Nothing about `mean_bf` or `sd_bf`.** Settled by the previous result and not
  reopened here.
- **Nothing about other Kalshi prop ladders.** `KXMLBHR` is the liquid batter
  ladder and its parameter problem is a different one. This result is about
  pitcher strikeouts.
