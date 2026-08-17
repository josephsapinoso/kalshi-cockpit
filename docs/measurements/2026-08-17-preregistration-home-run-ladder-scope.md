# Pre-registration — is `KXMLBHR` worth building, scoped against ADR 0036?

**Date:** 2026-08-17
**Status:** Registered. **Nothing below has been computed.**
**Scopes:** the candidate `tasks/NEXT.md` named after pitcher-K died — the one
liquid batter ladder.

## Why this is a scoping measurement and not a build

ADR 0036 refuted pitcher strikeouts, and the way it died is the reason this file
exists. The model was fine. The **parameter** could not be pinned: public rate
data forecasts `k_per_bf` to 6.09 points of ladder price at best — an *in-sample
upper bound* — against a **1.75-point** fee advantage.

`KXMLBHR` is the natural next candidate on liquidity (1,026 markets, 13.6%
dead, avg OI 6,290 — second only to `KXMLBKS`). ADR 0036's closing consequence
says it **"inherits a harder parameter problem, not an easier one"** and must be
**"scoped against this result before it is started, not after."**

This is that scope. It asks the question that killed the last build **first**,
before any model, adapter, lineup poll or ladder pricer exists.

## What has already been seen, disclosed

`batting.csv`'s **column names** and **one row** (Duff Cooley, 1897-04-19, 5 PA,
0 HR). The columns are `b_pa`, `b_hr`, `b_lp` (lineup position), `date`, `id`,
`stattype`, `gametype`. Nothing has been aggregated, paired, or rated.

Also carried over and already public: every number in ADR 0036 and its two
result documents.

## 1. The question

Can a batter's home-run rate per plate appearance be forecast tightly enough
that the resulting `KXMLBHR` price error falls inside the fee advantage?

## 2. Why home runs are structurally harder, stated before the answer

This is a prediction, registered so it can be wrong.

`P(HR >= 1) = 1 - (1 - p)^PA`. At a league `p ≈ 0.035` and `PA ≈ 4.2`, the
derivative with respect to `p` is `PA * (1-p)^(PA-1) ≈ 3.75`. So a rate error of
`d` moves the `1+` price by roughly `375 * d` points.

The equivalent coefficient for pitcher strikeouts was ~243 points per unit of
rate error. **Home runs are more price-sensitive per unit of rate error, and the
rate itself is about six times smaller**, so the *relative* precision required
is far tighter.

The budget: staying inside 1.75 points needs `d < 0.0047` in HR/PA. A batter
with 600 PA in a season has a binomial standard error on his own realised rate
of `sqrt(0.035 * 0.965 / 600) ≈ 0.0075` — **already 1.6× the entire budget,
from sampling noise alone, in a perfect estimate of a completed season, before
any true change in the batter.**

**If that reasoning is right, `KXMLBHR` is refuted more decisively than
pitcher-K was, and this measurement will show it.** It is written down here so
that a confirming result is a prediction met rather than a story fitted
afterwards — and so that a *disconfirming* result is visibly surprising.

## 3. The population

`batting.csv`: `stattype == "value"`, `gametype == "regular"`, seasons
**2015–2025**.

Rows are aggregated to a **batter-season**. A batter-season qualifies at
**`MIN_PA = 300`** — roughly half a season of regular play, chosen to mirror the
`MIN_STARTS = 15` role of the pitcher registration: it admits batters who missed
time while excluding bench players and September call-ups, whose rates estimate
a different quantity.

A **pair** is a batter qualifying in season `Y` and `Y+1`. **2020 is expected to
drop out** under a 300-PA floor on a 60-game season, exactly as it did for
pitchers; whether it does is reported, not assumed.

## 4. The forecasters and the target

Mirrors ADR 0036 §4 so the two builds are compared on the same instrument.

| | |
|---|---|
| **A** | prior season's full `hr_per_pa` — the Retrosheet-only option |
| **B** | **season-to-date** `hr_per_pa` before an **August 15** cut — needs a live feed |
| **L** | the league season-to-date rate at the cut — the do-nothing benchmark |
| **C** | in-sample OLS blend of A and B — **upper bound, never a verdict** |
| **T** | the target: rest-of-season `hr_per_pa` on or after the cut |

August 15 is used because it is the deployed date and because it was the
**most favourable** of the three cuts in ADR 0036. Choosing the cut that most
flattered the previous build is deliberate: a refutation that survives the best
case is stronger, and a positive result there would still have to be re-checked
at other cuts.

A batter enters the cut population with **≥ 200 PA before** the cut and **≥ 60
PA after** it, and a prior season at ≥ 300 PA.

## 5. The primary statistic

As registered for pitchers, and for the same reason — the post-cut target is
short, so its own sampling noise is comparable to the errors being compared:

    target_noise    = RMS over pairs of sqrt( T*(1-T) / PA_after )
    forecast_err(F) = sqrt( max( RMSE(F, T)^2 - target_noise^2, 0 ) )

Conservative in the direction that hurts the build: the binomial form
understates real target variance (park, opposing pitcher, weather), so it
overstates forecast error. A favourable verdict cannot be an artifact of it.

**Primary comparison: `forecast_err(A)` and `forecast_err(B)`, converted to
price.**

## 6. The price conversion, and the rung it is taken at

**The `1+` rung is primary.** `P(HR >= 2)` at league parameters is under 1%, and
a market at 1c cannot express a 1.75-point edge on the deci-cent grid at all. So
`1+` is the only rung where this question has an answer, and the conversion is
taken there. `2+` is reported beside it.

**The rung set is assumed, not observed, and that is a stated weakness.** No
`KXMLBHR` market is present in any local database or committed fixture; the
`N+` ladder shape is inferred from `KXMLBKS` and `KXMLBTB`, where it is verified.
The assumption is only that `1+` exists and dominates the volume, which is
implied by ADR 0036's liquidity table but not directly checked here.

**The conversion is computed two ways and both are reported:**

1. the closed form `1 - (1-p)^PA` at the league mean PA, and
2. the compound `PA` distribution via `backend.model.strikeouts.distribution`,
   which is the identical compound-binomial arithmetic.

That module's docstring says it establishes "nothing about batters" — correct
about its *shape assumption* (a discretised normal over `PA ≈ 4.2` is cruder
than over `BF ≈ 23`), and not about its algebra. **Agreement between the two
methods is what licenses using it here**; disagreement means the closed form
governs and the compound is discarded.

## 7. The decision rule, fixed now

Bars unchanged: **fee 1.75 points**, **too-stale 5.00 points** (ADR 0028).

| condition | verdict |
|---|---|
| `forecast_err(C)` price error `> 5.00` pts | **REFUTED, HARDER THAN PITCHER-K.** No blend of public rate data can price this ladder. Do not build. Record beside ADR 0036 and stop. |
| `C` in `[1.75, 5.00]` and `B` `> 5.00` | **REFUTED AS BUILDABLE.** Only an in-sample upper bound reaches the marginal band; nothing implementable does. Do not build. |
| `B` price error in `[1.75, 5.00]` | **MARGINAL.** Genuinely arguable, and would then need the lineup dependency (ADR 0035) scoped separately before any commitment. |
| `B` price error `< 1.75` pts | **BUILD IT.** Contradicts §2's prediction, which must then be reported as wrong in the write-up. |

**`C` decides the first branch on purpose.** It is the in-sample optimum and
cannot be beaten by any implementation, so when *it* fails the bar the
conclusion needs no further work — the same logic that made ADR 0036 decisive.

## 8. Stopping rule

**One look. One cut. Then it is done.** Any further cut date, PA threshold, or
season window is a new registration reported next to this one whether or not it
agrees. The specific temptation named: if the verdict is REFUTED, lowering
`MIN_PA` to admit more batters, or moving the cut earlier to lengthen the
target, until a branch changes.

## 9. What this cannot establish

- **Nothing about beating Kalshi.** Every forecaster is scored against the
  batter's own future, not a price.
- **Nothing about the lineup-slot half of the model.** Expected PA by slot is a
  second parameter with its own error, and it is *deliberately excluded*: if the
  rate alone fails the bar, the slot cannot rescue it, and if the rate passes,
  the slot becomes a separate scoping question with an ADR 0035 licence
  dependency attached.
- **Nothing about batters without a prior season** — excluded by construction,
  the same open door ADR 0036 left.
- **Nothing about `KXMLBTB`, `KXMLBHIT` or `KXMLBRBI`.** They are thinner (21%,
  36% and 48% dead) and are not scoped here.
- **Nothing about the live rung set**, per §6.
