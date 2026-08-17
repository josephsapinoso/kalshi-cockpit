# Result — `KXMLBHR` is MARGINAL, and my registered prediction was wrong

**Date:** 2026-08-17
**Registered:** `2026-08-17-preregistration-home-run-ladder-scope.md`
**Harness:** `scripts/measure_home_run_ladder_scope.py`
**Source:** Retrosheet `batting.zip`, retrieved 2026-08-17.

> The information used here was obtained free of charge from and is copyrighted
> by Retrosheet.

## The registered prediction was wrong, and it is the first thing here

§2 of the registration predicted, in advance and in writing:

> **If that reasoning is right, `KXMLBHR` is refuted more decisively than
> pitcher-K was, and this measurement will show it.**

**It did not.** Home runs are **not** harder than pitcher strikeouts. They are
**2.3× easier**, and the verdict is **MARGINAL**, not refuted.

ADR 0036's closing consequence — that `KXMLBHR` *"inherits a harder parameter
problem, not an easier one"* — **is wrong and is corrected by this result.**

What §2 got *right* was the arithmetic: it predicted the achievable precision
would miss the budget by about 1.6×, and the measured miss is **1.66×**
(0.00878 against a budget of 0.00529). What it got wrong was the conclusion
drawn from that — it treated "fails the fee bar" as "refuted", when the
registration's own table has a MARGINAL band between 1.75 and 5.00 points, and
home runs land squarely inside it.

## Verdict

```
CUT 08-15   1,443 pairs, 2015-2025, median 147 PA after the cut

  forecaster                          raw RMSE   forecast err   1+ price
  A  prior season (Retrosheet only)    0.01914      0.01096      3.60 pts
  B  season-to-date (needs a feed)     0.01798      0.00878      2.89 pts
  L  league season-to-date             0.02010      0.01256      4.11 pts
  C  blend  [IN-SAMPLE, upper bound]   0.01714      0.00688      2.27 pts

  bars: fee 1.75 pts, too-stale 5.00 pts
  ADR 0036, same cut:  pitcher-K  B 6.69 pts   C 6.09 pts

  VERDICT   MARGINAL
```

Everything here is **well inside** the 5.00-point bar that killed pitcher-K.
`B` beats `A` in **8 of 8 seasons**, largest contributor 13.3%, and the two
independent price conversions agree to 0.05 points (closed form 2.89, compound
2.84), which §6 made the condition for using the compound at all.

## The one number that keeps this from being a green light

**`C` is 2.27 points and `C` cannot be beaten.** It is the optimal blend of `A`
and `B`, fitted in-sample on the pairs it is scored on, so it upper-bounds any
weighting of these two rates.

**2.27 > 1.75.** So, exactly as with pitcher-K:

> **No implementable combination of public rate data brings `KXMLBHR` parameter
> noise inside the fee advantage.**

The difference is one of degree and it is large. Pitcher-K's floor was 3.5× the
fee bar; home runs' floor is **1.3×**. That is close enough that the decision
stops being arithmetic and starts being judgement — which is what MARGINAL
means, and why the registered table has that branch rather than a second
refutation.

## The conversion used is mildly flattering, and here is by how much

`mean_pa = 3.654` is averaged over **all** batter-games, including partial
appearances, pinch-hits and early substitutions. A batter who starts and is in
the Kalshi ladder gets more, and the price sensitivity rises with PA:

| assumed PA | A | B | **C** | budget for 1.75 pts |
|---|---:|---:|---:|---:|
| 3.654 (used in the run) | 3.60 | 2.89 | **2.27** | 0.00529 |
| 4.20 (a lineup starter) | 4.04 | 3.25 | **2.55** | 0.00470 |
| 4.64 (leadoff) | 4.39 | 3.53 | **2.78** | — |

**The verdict does not change at any of them** — all stay inside the 5.00 bar
and outside the 1.75 one — but the honest figure for a batter actually in the
ladder is **`B` ≈ 3.25, `C` ≈ 2.55**, not 2.89 and 2.27. Every number in this
document should be read at the 4.20 row when thinking about a real market.

## Why home runs beat strikeouts, mechanically

The forecast error for `B` (0.00878) is **almost exactly its own binomial
sampling noise** — a batter with ~380 PA before the cut carries
`sqrt(0.0343 × 0.9657 / 380) = 0.00934` of pure sampling noise around his true
rate. Measured error is *at or below* that.

**That means true-skill drift is small relative to sampling noise: a batter's
home-run rate is a more stable attribute than a pitcher's strikeout rate.** The
whole gap between the two builds is that stability. It is not that home runs are
easier to model — the model is the same compound binomial — it is that the thing
being estimated moves around less.

## Population

| | |
|---|---:|
| batter-games in window (2015–2025, regular season) | **521,372** |
| **unreadable** | **0** |
| batter-seasons | 9,173 |
| qualifying at ≥300 PA | 2,769 |
| **pairs** | **1,443** |
| excluded — no qualifying prior season | 971 |
| median PA after the 08-15 cut | 147 |

**2020 dropped out on its own**, as the registration expected: no 2020
batter-season reached 300 PA in a 60-game schedule, so both pairs it touches are
missing rows. 262–293 batters qualify per season otherwise.

**971 batter-seasons are excluded for having no qualifying prior season** — the
same door ADR 0036 left open, and proportionally a larger one here (971 against
1,443 pairs).

## What this does not establish

- **Nothing about beating Kalshi, and this is the binding limitation.** Every
  forecaster is scored against the batter's own future. Kalshi sees the same
  Retrosheet-equivalent history *and* the current season *and* the lineup. A
  2.89-point estimate is only worth something if Kalshi's is worse, and nothing
  here measures Kalshi's.
- **Nothing about lineup slot**, deliberately excluded by §9. It is a *second*
  parameter with its own error, and the table above shows it is **not small**:
  the spread from leadoff to the bottom of the order is ~0.9 PA, worth ~2.9
  points on its own — comparable to the entire rate error. Any build would have
  to get it right, and getting it right means the ADR 0035 lineup dependency and
  its licence surface, which this measurement was specifically constructed to
  avoid needing.
- **Nothing about the live rung set.** No `KXMLBHR` market exists in any local
  database or committed fixture. The `1+` rung's existence and dominance is
  inferred from `KXMLBKS`/`KXMLBTB`, not observed. **`2+` prices at 0.27–0.44
  points of error, i.e. it is untradeable on a deci-cent grid regardless** — so
  if `1+` turns out not to be listed, there is no ladder here at all.
- **Nothing about batters with no prior season** — 971 of them.
- **Nothing about `KXMLBTB`, `KXMLBHIT`, `KXMLBRBI`**, which are 21%, 36% and
  48% dead markets and were not scoped.

## What the decision now needs

MARGINAL is not a build order. Per §7 it means the case is arguable and the
lineup dependency must be scoped before any commitment. Two things would settle
it, and **neither is a model**:

1. **Does `1+` actually exist and carry volume on the live record?** One query
   against `kalshi_markets` on the instance. If not, this is moot.
2. **Is Kalshi's own `1+` price worse than 3.25 points?** This is the real
   question and the only one that can produce an edge. It is answerable from the
   recorded ladder against settled outcomes — no model, no feed, no licence —
   and it should be registered and run **before** anything is built.
