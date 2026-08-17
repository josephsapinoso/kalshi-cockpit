# Result — NOTHING TO TRADE. Our disagreement with Kalshi is smaller than our own error.

**Date:** 2026-08-17
**Registered:** `2026-08-17-preregistration-kalshi-hr-pricing-error.md`
**Harness:** `scripts/measure_kalshi_hr_pricing_error.py`
**Sources:** live `kalshi-cockpit` record (read-only); Retrosheet `batting.zip`
and `biodata.zip`.

> The information used here was obtained free of charge from and is copyrighted
> by Retrosheet.

## Verdict

```
n 255 markets, 2 dates, pre-first-pitch derived ask

  d = model - ask      mean +0.31   sd 3.72   mean |d| 2.85
                       p10 -4.03    p50 +0.14   p90 +5.10
  model mean 12.75     ask mean 12.44

  sigma_model 4.04 (PRIMARY)      -> sigma_kalshi 0.00 pts
  sigma_model 4.50 (sensitivity)  -> sigma_kalshi 0.00 pts
  sigma_model 5.00 (sensitivity)  -> sigma_kalshi 0.00 pts

  bar 1.75 pts
  VERDICT   NOTHING TO TRADE
```

## What happened, in one sentence

**The entire disagreement between our model and Kalshi has a standard deviation
of 3.72 points, and our model's own error is 4.04 points — so the disagreement
is smaller than our own noise, and Kalshi's error is not detectable at all.**

`Var(d) - sigma_model^2` is negative at every one of the three registered
`sigma_model` values, so the estimate floors at zero and the verdict is
insensitive to the whole sensitivity band. There is no arrangement of these
inputs that produces a tradeable disagreement.

## Why this is the strongest of the four results

The three earlier measurements each scored a forecaster against **the player's
own future**, and every one of them carried the same disclaimer: *"nothing about
beating Kalshi."* They could establish that our parameters were noisy. They
could not establish whether Kalshi's were noisier.

This one looks at the price. And the answer is not "our model is worse than
Kalshi" — it is sharper than that:

> **Whatever error Kalshi has, our model cannot see it.** Every apparent edge
> the tool would surface on this ladder is our own parameter noise wearing the
> costume of a disagreement.

That is this repo's first rule — *a large apparent edge is a bug until proven
otherwise* — turned into a number for a specific instrument.

## The subtraction is a floor, not a point estimate

§3 registered the direction in advance: the two errors are almost certainly
**positively correlated**, because Kalshi and a rate model estimate the same
quantity from overlapping information, and positive correlation shrinks `Var(d)`.

`Var(d)` coming out **below** `sigma_model^2` is exactly what that correlation
predicts, and it is the reason the estimator floors. So `sigma_kalshi = 0.00`
must be read as **"not resolvable above zero by this method"**, not as "Kalshi is
perfect." The decision-relevant claim is the one stated above and it does not
depend on the difference: our model cannot see Kalshi's error, whatever it is.

## Two corroborating observations, both disclosed as already-seen

Neither carries a verdict, because both were computed before the registration
was written (§1) and are reported with that provenance:

- **Pooled level.** Kalshi's mean pre-game ask is **12.44** points. The realised
  rate on the settled 1+ population is **12.04%** (62 of 515). An ask sitting
  slightly *above* the realised frequency is what a correctly-priced market with
  a spread looks like. **Underpowered — 29 games, 95% interval about ±3.6
  points — and it is not a calibration result.**
- **Model bias.** Mean `d` is **+0.31** points and the per-date means are +0.43
  and +0.18. The model is not systematically high or low against Kalshi; the
  disagreement is dispersion, not direction.

## Why the obvious calibration run was refused, and stays refused

515 settled markets come from **29 games**. Batters in one game share an
opposing pitcher, a park and a weather window, so the cluster count is 29 —
against the **300** this project's own registered signal test requires before it
will declare anything. On a 12.04% base rate the 95% interval spans roughly
**±3.6 points against a 1.75-point bar.**

Running it would have produced a number that reads like a result and could only
have meant UNRESOLVED. §2 of the registration forbade it before the data was
touched.

## Population, and the exclusion is now the story

| | |
|---|---:|
| settled `1+` markets with a pre-first-pitch quote | 531 |
| rows with no readable game clock | **0** |
| — no qualifying 2025 season | **143** |
| — no Retrosheet name match | **95** |
| — unsettled at extract time | 34 |
| — ambiguous name | 4 |
| **admitted** | **255** |

**238 of 493 settled markets — 48% — were dropped for having no usable 2025
baseline.** That is the same door left open by both previous measurements, and
it is no longer a footnote: **nearly half the ladder is batters this approach
cannot price at all.** They are recent debuts, part-season call-ups, and players
whose names `props.norm()` cannot match because it strips accents asymmetrically
(`Narváez` → `narvez` against a bio file's `Narvaez`).

A model that cannot price half the board is not a model of the board.

## What this does not establish

- **It does not establish that Kalshi is correctly priced.** It establishes that
  *our* model cannot detect any error. Those are different claims and only the
  second is supported.
- **Nothing about direction.** `sigma_kalshi` is a spread. Even had it cleared
  the bar, knowing the price is noisy is worthless without knowing which side is
  wrong, and only outcomes answer that.
- **Nothing beyond two dates.** 130 markets on 26AUG15 and 125 on 26AUG16 — one
  August week, one slate of parks and pitchers. Every number here could move on
  a different week and this design would not detect it.
- **Nothing about the 238 excluded markets.** They may be exactly where an edge
  lives, and they are unreachable by construction from a prior-season baseline.
- **Nothing about `sigma_model` transferring to 2026.** It was measured on
  2015–2025 pairs.
- **Nothing about in-play.** 54% of quotes are post-first-pitch and are excluded
  by a clock derived from the event ticker, not observed.
- **Nothing about the other four prop ladders**, which are 21–48% dead markets
  and were never scoped.
