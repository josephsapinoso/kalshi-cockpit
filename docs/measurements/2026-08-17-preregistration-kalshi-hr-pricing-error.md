# Pre-registration — how wrong is Kalshi's own `KXMLBHR 1+` price?

**Date:** 2026-08-17
**Status:** Registered. **The primary statistic has not been computed.**
**Follows:** `2026-08-17-home-run-ladder-scope-result.md` (MARGINAL), whose
closing section named this as the only question that can produce an edge.

## The question three measurements have not asked

Every measurement so far scores a forecaster against **the player's own future**.
None of them looks at a price. That is why none of them can say whether there is
money here: a model accurate to 3.25 points is worth nothing if Kalshi is
accurate to 1 point, and worth a great deal if Kalshi is accurate to 8.

This asks the price question directly, and it asks it **without needing
outcomes** — which matters, because the outcome route is not available (§2).

## 1. What has already been seen, and it is a lot — disclosed in full

This registration was written **after** exploring the live record, so the
disclosure is long by necessity. Everything below has been computed and seen:

- **Structure.** 1,044 `KXMLBHR` markets on the instance; by strike: 547 at
  `0.5` (the `1+` rung), 490 at `1.5`, 7 at `2.5`. **The `1+` rung exists and
  dominates** — that was the scope result's open question 1, now closed.
- **Settlement.** Of the 547: 453 `no`, 62 `yes`, 32 unsettled. Realised rate
  **62/515 = 12.04%**.
- **Coverage.** 50,760 quotes, all 549 tickers, `player_name` populated on every
  row. **29 settled games across three dates only** — 26AUG15 (15), 26AUG16
  (15), 26AUG17 (4).
- **Timing.** 46.1% of quotes are strictly before first pitch; the median quote
  sits at **+0.23h**, just after it.
- **Spread and level.** On pre-game two-sided quotes: median spread **1.00c**
  (p25 = p75 = 1.00, mean 1.13); derived ask p10 **7c**, median **12c**, p90
  **19c**.
- **Name matching.** 341 distinct batters; 270 match a unique Retrosheet id
  (79.2%), 4 ambiguous, 67 unmatched — the unmatched skewing to recent debuts
  and to accented names that `props.norm()` strips asymmetrically.

**The pooled calibration is therefore already known and is NOT registered here.**
Median ask 12.0c against a realised 12.04% is a number I have seen, so no
verdict may rest on it. It is reported in the write-up as an observation with
its provenance stated, never as a registered result.

## 2. Why the outcome route is refused, stated before it tempts anyone

The obvious measurement is calibration: bucket by the price actually paid,
compare to realised frequency. **It cannot work on this record, and the
arithmetic is not close.**

515 markets sounds ample. They come from **29 games**, and batters within a game
share an opposing pitcher, a park and a weather window, so the cluster count is
29 — against the **300** this project's own registered signal test requires
before it will declare anything. On a pooled rate of 12.04%, the naive standard
error is 1.48 points; with any realistic within-game correlation it is worse than
1.8, so the 95% interval spans roughly **±3.6 points against a 1.75-point bar.**

**A calibration run here could only return UNRESOLVED**, and running it would
produce a number that reads like a result. It is not run. If the record reaches
a few hundred games the question reopens on its own.

## 3. The primary statistic — Kalshi's error, by subtraction

The disagreement between two independent estimates of the same truth carries the
variance of both:

    d          = P_model - ask
    Var(d)     = sigma_model^2 + sigma_kalshi^2
    sigma_kalshi = sqrt( max( Var(d) - sigma_model^2, 0 ) )

**`sigma_model` is not fitted here — it was measured before this file existed.**
The home-run scope result puts forecaster `A` (prior-season rate, the only one
available for 2026 since Retrosheet ends at 2025) at **4.04 points** at a lineup
starter's PA of 4.2. That number is an input, fixed, and may not be re-estimated
to move a verdict.

**The subtraction is conservative against the build.** The two errors are almost
certainly *positively* correlated — Kalshi and a rate model are estimating the
same quantity from overlapping information — and positive correlation shrinks
`Var(d)`, so `sigma_kalshi` comes out **understated**. A verdict that finds
Kalshi sloppy cannot be an artifact of this.

**One direction does flatter the build and is controlled for:** if `sigma_model`
is understated, `sigma_kalshi` is overstated. Lineup slot is the known omission
— the model uses a flat PA of 4.2 while real slots run 3.74–4.64, worth ~2.9
points end to end. So the statistic is reported at **`sigma_model` = 4.04
(primary), 4.5 and 5.0 (sensitivity)**, all three fixed now, and a verdict that
does not survive all three is reported as not surviving them.

## 4. The population

Settled `KXMLBHR` markets at `strike = 0.5`, with:

- a **unique** Retrosheet name match (ambiguous and unmatched batters are
  **counted and excluded**, never guessed — `props.norm()`'s rule),
- a qualifying **2025** batter-season at ≥ 300 PA, giving forecaster `A`,
- at least one **strictly pre-first-pitch** two-sided quote.

The price is the **derived ask** (`1000 - no_bid_tenths`) from the **last quote
strictly before first pitch**, per `db.ask_for_side`. Never a mid: this repo's
rule, and the one that produced a +25.4-point phantom edge in the previous
project when broken.

First pitch is derived from the event ticker (`26AUG151310` → 13:10 US/Eastern),
**not** from `occurrence_datetime`, which carries a known 3-hour offset.

`P_model = 1 - (1 - p)^4.2`, with `p` the batter's raw 2025 HR/PA — raw and
unshrunk, because that is exactly the estimator whose 4.04-point error was
measured.

## 5. The decision rule, fixed now

| condition | verdict |
|---|---|
| `sigma_kalshi < 1.75` pts at all three `sigma_model` values | **NOTHING TO TRADE.** Kalshi's own pricing error is inside the fee advantage. No model of public rate data can extract from it. Do not build; stop. |
| `sigma_kalshi >= 1.75` at 4.04 but not at 5.0 | **UNRESOLVED, SLOT-LIMITED.** The answer depends on how much of the disagreement is our own lineup-slot ignorance. Resolve the slot before anything else. |
| `sigma_kalshi >= 1.75` at all three | **KALSHI IS LOOSE ENOUGH TO MATTER.** Not a build order and not an edge — it says a disagreement exists that is larger than the fee. The next step is the outcome test, which needs ~300 games and cannot be short-cut. |

Reported alongside and **not** promotable: `mean(d)` as a bias check, the
distribution of `d`, and the per-date breakdown across the three dates.

## 6. Stopping rule

**One look.** Three `sigma_model` values, fixed above. No other PA assumption, no
other quote horizon, no other shrinkage, no re-derivation of `sigma_model`. The
named temptation: if the verdict is NOTHING TO TRADE, raising `sigma_model` until
`sigma_kalshi` clears 1.75.

## 7. What this cannot establish

- **It cannot establish an edge, in any branch.** `sigma_kalshi` is a *spread*,
  not a direction. Knowing Kalshi's price is noisy is worthless without knowing
  which side is wrong, and only outcomes tell you that — which §2 refuses on
  power grounds.
- **Nothing about the 21% unmatched batters**, who skew to recent debuts. Third
  time this door has been left open, and it is now the most conspicuous gap in
  the whole line of work.
- **Nothing beyond three dates.** 29 games in one August week share weather,
  parks and a single slate of pitchers. Every number here could move on a
  different week and nothing in the design would detect it.
- **Nothing about `sigma_model` transferring.** It was measured on 2015–2025
  pairs; applying it to 2026 assumes the relationship holds. Untested.
- **Nothing about in-play.** 54% of quotes are post-first-pitch and are excluded,
  but the exclusion is by a derived clock, not an observed one.
