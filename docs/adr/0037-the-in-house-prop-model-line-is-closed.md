# ADR 0037 — The in-house prop-model line is closed

**Date:** 2026-08-17
**Status:** Accepted
**Extends:** ADR 0036, which closed pitcher strikeouts. This closes the line.

## Context

On 2026-08-16 the consensus-only signal was measured and found negative
(`beta = -0.141`). The response, recorded in CLAUDE.md, was that **work
producing an opinion is the critical path** — an in-house model, validated by
the same signal-test harness that refuted the consensus.

Four registered measurements followed in one day. Each was written before its
data was seen, each named the result that would falsify it, and each is recorded
whether or not it agreed with the last.

| # | question | verdict |
|---|---|---|
| 1 | Does a season-old strikeout baseline carry? | **TOO STALE ALONE** — 8.47 pts vs a 1.75-pt bar |
| 2 | Does current-season data rescue it? | **NO FEED RESCUES IT** — in-sample floor 6.09 pts |
| 3 | Is the home-run ladder easier? | **MARGINAL** — 2.89 pts; my prediction that it was *harder* was wrong |
| 4 | Is Kalshi's own HR price detectably wrong? | **NOTHING TO TRADE** |

Measurement 4 is the one that closes the line, and it closes it for a different
reason than the first three.

## The decisive finding

Measurements 1–3 all scored a forecaster against **the player's own future**.
Every one carried the disclaimer *"nothing about beating Kalshi."* They
established that our parameters were noisy; they could not establish whether
Kalshi's were noisier.

Measurement 4 compared the model to the **price**, on 255 settled `KXMLBHR 1+`
markets at the pre-first-pitch derived ask:

```
d = model - ask     sd 3.72 points
sigma_model                4.04 points   (measured in #3, an input here)
sigma_kalshi = sqrt(Var(d) - sigma_model^2)  ->  0.00 at 4.04, 4.50 and 5.00
```

**The entire disagreement between our model and Kalshi is smaller than our own
model's error.** The subtraction floors at zero at every registered sensitivity
value, so no arrangement of these inputs produces a tradeable disagreement.

The claim this supports is precise, and it is not "Kalshi is right":

> **Whatever error Kalshi has, our model cannot see it.** Every apparent edge
> this tool would surface on that ladder is our own parameter noise wearing the
> costume of a disagreement.

That is CLAUDE.md's first rule — *a large apparent edge is a bug until proven
otherwise* — measured, for a specific instrument.

## Decision

**1. No in-house prop model is built from public rate data.** Not pitcher
strikeouts (ADR 0036), not home runs, and not the three thinner ladders —
`KXMLBTB`, `KXMLBHIT` and `KXMLBRBI` are 21%, 36% and 48% dead markets, so they
inherit this result with worse liquidity and are not scoped separately. Nothing
in the four measurements suggests they would clear a bar the two best ladders
missed.

**2. `backend/model/strikeouts.py` stays as a `Tool`**, unchanged from ADR
0036's disposition. The arithmetic was never what failed.

**3. The MLBAM adapter stays unbuilt** and ADR 0035's licence surface stays
closed — now on two independent grounds rather than one.

**4. The Retrosheet path stays.** Four harnesses depend on it, the ingestion is
proven, the file is complete, and the `README.md` notice is in place. It is the
instrument for any future baseball question.

## What is NOT decided here

**This does not say Kalshi's props are efficient.** It says a rate-based model
cannot detect an inefficiency. Those are different claims and only the second is
supported. Two specific gaps remain, and both are live:

**The 48% we cannot price.** 238 of 493 settled markets were dropped for having
no usable 2025 baseline — recent debuts, part-season call-ups, and names
`props.norm()` cannot match because it strips accents asymmetrically (`Narváez`
→ `narvez` against `Narvaez`). **Nearly half the board is unreachable by
construction from a prior-season baseline**, and it is the half a market is least
certain about. Every one of the four measurements excluded this population, and
by the fourth it stopped being a footnote.

Whether that is an opportunity or merely a hard problem is **not established**.
It would need its own registration, its own data source — Retrosheet cannot
help, since the whole difficulty is the absence of history — and an honest prior
about how few such markets exist per slate.

> **CORRECTION, 2026-08-17.** The two paragraphs above overstate their own
> harness and the phrase **"unreachable by construction" is not supported by
> anything measured.** The published split
> (`docs/measurements/2026-08-17-kalshi-hr-pricing-error-result.md:97-106`) is
> **143 with "no qualifying 2025 season" + 95 name-match failures**, and
> `MIN_PA = 300` (`scripts/measure_kalshi_hr_pricing_error.py:78`, applied at
> `:131`) is what "no qualifying season" means. That is an **analyst-chosen
> threshold, not an absence of history**: a batter with a complete, readable
> 250-PA 2025 line is counted in the 143 alongside a player who has never
> appeared. So the 143 are not "recent debuts and part-season call-ups", and the
> 95 are a defect — `2893d8c` has since fixed the accent folding and recovered
> 18 players. The honest sentence is *"48% fall outside the population this
> harness admitted"*, which is a fact about the harness.
>
> The romantic half of the framing — *the half the market is least sure about* —
> was never measured either. It is a hypothesis, and it is now declined; see
> **ADR 0038** for why, including the arithmetic that all 493 markets come from
> **29 games** against a registered floor of 300 clusters, so relaxing `MIN_PA`
> adds rows without adding clusters and cannot move the binding limit.
>
> The lesson generalises past this ADR: **an exclusion count describes the
> filter, not the world.** Before writing "X is unreachable", read what the
> filter's own constant is set to and ask whether *you* chose it.

**The name matcher has a fixable defect.** The accent-stripping asymmetry is a
bug in `props.norm()`, not a property of the problem, and it is cheap to fix
independently of any model. It is worth fixing on its own merits: it currently
drops real markets from the record.

## Consequences

- **CLAUDE.md's refuted-ideas table gains a second row.** The first covers
  pitcher-K on parameter noise; this covers the whole line on price
  undetectability, which is the more general result.
- **"Work that produces an opinion is the critical path" survives, but this
  opinion is spent.** Four measurements in one day is the cheap way to learn it.
- **The four harnesses are kept and are the asset.** `measure_pitcher_k_decay`,
  `measure_in_season_vs_stale`, `measure_home_run_ladder_scope` and
  `measure_kalshi_hr_pricing_error` are a reusable pattern: register, measure the
  parameter, convert to price, compare to the fee bar. The fourth is the
  template worth generalising — **compare to the price, not to the outcome** —
  because it needs no settlements and therefore no 300-cluster wait.
- **Ask the price question first, next time.** Measurements 1–3 cost a day and
  measurement 4 would have short-circuited all of them: if the model cannot
  out-resolve the market, the parameter work never had to happen. That ordering
  error is the most transferable thing in this ADR.

## What this ADR does not establish

- **That no model can beat Kalshi on props.** The bound is over models built
  from public season rates. A batter-level, park-adjusted, pitch-level model is
  outside it — and is a different project needing sources this one lacks.
- **That the 1.75-point bar is exactly right.** ADR 0027's caveat stands; even
  at the most generous reading the disagreement is undetectable, so the verdict
  does not turn on it.
- **Anything about the moneyline path**, which is unaffected and is where the
  consensus signal was measured.
- **Anything from more than two dates.** 255 markets across 26AUG15 and
  26AUG16. The record keeps growing at no cost, and the question reopens by
  itself if it ever wants to.
