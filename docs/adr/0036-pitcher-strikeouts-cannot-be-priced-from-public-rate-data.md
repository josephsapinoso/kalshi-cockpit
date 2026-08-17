# ADR 0036 — Pitcher strikeouts cannot be priced from public rate data, and the MLBAM adapter is not built

**Date:** 2026-08-17
**Status:** Accepted
**Supersedes:** nothing. **Constrains** ADR 0035, whose live MLBAM layer now has
no consumer.

## Context

`tasks/NEXT.md` on 2026-08-17 made pitcher strikeouts the next build, ahead of
the batter ladders, on liquidity grounds: `KXMLBKS` is 0.9% dead markets against
13.6% for the next-best series, needs no lineup data, and the starter is known
1–3 days ahead. That reasoning was and remains correct.

Slice 1 shipped (`backend/model/strikeouts.py`): a compound distribution that
prices a whole ladder from `(expected_bf, sd_bf, k_per_bf)`. Against the ladders
Kalshi published on 2026-08-15, with league-average constants typed in, two of
seven pitchers priced within ~4 points across every rung. **The distribution
family reproduces the shape of what Kalshi charges.** The residual was the
per-pitcher parameter, and supplying it was slice 2.

Two registered measurements were then run to find out whether that parameter can
be supplied well enough.

## The measurements

**1. `2026-08-17-pitcher-k-baseline-decay-result.md`** — 772 pitcher-season
pairs, 2015–2025, 50,382 starts of which 7 unreadable.

A prior season's rate beats a league constant by **29.1%**, in 8 of 8 pair-years.
`k_per_bf` is a real, persistent pitcher attribute. But the residual is worth
**8.47 points** of ladder price (7.44 after removing target sampling noise)
against a **1.75-point** fee advantage. Verdict: **TOO STALE ALONE**, whose
registered branch called for a current-season blend.

It also found, unanticipated, that the three parameters behave completely
differently: `mean_bf` is barely a pitcher attribute (+6.9%), and per-pitcher
`sd_bf` is **30.6% worse** than a league constant.

**2. `2026-08-17-in-season-vs-stale-baseline-result.md`** — the blend, tested
before it was built, at three pre-declared cuts.

Season-to-date data does help: it beats the prior-season baseline in 8 of 8
seasons at the primary July 31 cut. And it helps nowhere near enough — **7.23
points**, a 13% reduction on a quantity that must fall by 80%.

**The decisive figure is the in-sample blend.** Fitted on the very pairs it is
scored on, it cannot lose to either input by construction, so it upper-bounds
what *any* weighting of these two rates could achieve. That bound is **6.47
points** at the primary cut and **6.09** at the deployed mid-August one — both
above the registered 5.00-point too-stale bar and roughly **3.5× the entire fee
advantage.**

Verdict at all three cuts: **NO FEED RESCUES IT.**

## Decision

**1. Pitcher-K is not priced from public rate data. Slice 2 as designed is
dead, and slice 3 does not begin.** No model rows, no new
`strategy_config_version`, no signal-test registration for this signal. The
conclusion does not depend on any implementation detail, because the bound that
produces it is an upper bound over the whole family of approaches.

**2. The MLBAM adapter is not built.** ADR 0035's thin live layer — probable
starter, confirmed lineup — was designed for exactly this consumer and now has
none. The licence surface that decision spent its length narrowing stays closed,
and it stays closed **on evidence rather than on caution**, which is a better
reason. ADR 0035 is not superseded: its split, its notice obligation and its
commercial-swap trigger all stand, and the batter ladders would re-open the
question on their own terms.

**3. `backend/model/strikeouts.py` stays, as a `Tool`, and is not deleted.** It
is correct, it is tested, its 49 tests are mutation-verified, and what was
refuted is the parameter supply — not the arithmetic. Deleting it would destroy
the cheapest way to re-test this conclusion if a better parameter source ever
appears.

**4. Retrosheet stays, and its notice stays in `README.md`.** The ingestion is
proven, the file is complete (4,856–4,860 starts per season, exactly two per
game), and it is the harness for any future baseball parameter question. The
notice is mandatory once derived numbers are published, and they have been.

## The one door this does not close, stated so it is not inherited as an oversight

**Both measurements exclude pitchers with no qualifying prior season — 494 of
them at the primary cut.** A pair requires two seasons by construction, so
rookies and pitchers returning from a lost year were never in the population.

They are precisely the starters a market is least certain about, and therefore
the most plausible remaining place for an edge in this series. **Nothing above
says anything about them.** It is also a much harder problem — the whole
difficulty is that there is no history to fit — and it would need its own
registration, its own population and its own honest prior about how few such
starts exist per season.

It is recorded here as an open question, not as a plan.

## Consequences

- **`tasks/NEXT.md`'s "THE BUILD" is spent.** Work that produces an opinion is
  still the critical path (CLAUDE.md); *this* opinion is not the one.
- **The natural next candidate is `KXMLBHR`**, the one liquid batter ladder —
  but it inherits a harder parameter problem, not an easier one, and ADR 0035's
  lineup dependency comes back with it. It should be scoped against this result
  before it is started, not after.
- **The 1.75-point bar did the work.** Both verdicts turned on comparing a
  parameter error to the fee advantage rather than to zero. A version of this
  build that had asked "is the model any good?" instead of "is the model good
  enough to clear the cost?" would have answered yes twice and shipped.
- **CLAUDE.md's refuted-ideas table gains a row.** This cost two days and it
  should cost nobody else any.

## What this ADR does not establish

- **That Kalshi prices `KXMLBKS` correctly.** Nothing here compares a model to a
  market outcome; both measurements score a parameter against the pitcher's own
  future. Kalshi may be badly wrong on this ladder and this work could not tell.
- **That no model of pitcher strikeouts can work.** The bound is over linear
  blends of *public season rates*. A batter-level, park-adjusted, pitch-level
  model is not bounded by it — it is also a different project needing sources
  this one does not have, and it would face the same 1.75-point bar.
- **That the fee bar is 1.75 points.** That is ADR 0028's number and it carries
  ADR 0027's caveat: the true baseball bar may be 50.88% rather than 51.75%,
  which would *widen* the advantage to ~1.5 points more. Even at the most
  generous reading the 6.09-point floor clears it by a factor of two.
