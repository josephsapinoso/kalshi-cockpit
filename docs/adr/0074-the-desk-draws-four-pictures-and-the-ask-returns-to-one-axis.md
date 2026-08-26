# 0074 — The desk draws four pictures, and the ask returns to one axis

**Date:** 2026-08-26
**Status:** Accepted.
**Owner of the decision:** Joe. Asked for graphs "where they would make sense
for a newbie like me", chose all four when they were put to him, and when told
that marking Kalshi's ask on the dispersion axis partly reverses a prior
ruling, answered: *"yeah mark the ask, go ahead."*
**Narrows** the 2026-08-21 "strip the landing screen" ruling to the screen it
is named for. **Touches nothing decided by** ADR 0038 (the hunt is closed),
ADR 0062 (the edge-finder is a feature), or ADR 0071 §2.5 (the gap is shown,
never ranked by).

## 1. What was built

| picture | where | what its data's job is |
|---|---|---|
| Chance collapsing as legs are added | `/parlays`, once per card | change over a count |
| How the books' prices became this number | `/market/[ticker]`, Consensus | explain a sequence |
| Where the number came from, on one axis | `/market/[ticker]`, Consensus | a distribution |
| Money in and out, cumulatively | `/bets` | change over time |

Every one is hand-rolled SVG in `PriceChart.tsx`'s house style. There is no
charting dependency and none was added.

## 2. No chart wears a colour, and that is a finding about this repo

`--accent` is `#aa0000` in light and `#ef4444` in dark — **the same values as
`--negative` in each theme.** `tests/test_palette_contrast.py` already forbids
a Board stat from taking the accent. So a coloured data series here would read
as a verdict on a number that is not one: a red line through a fair value says
"bad" to a reader who has learned the rest of the screen.

Every mark is therefore an ink token — `currentColor`, `--muted`,
`--border-strong` — and identity comes from **position and shape**. Two
consequences worth stating because they look like omissions:

- There is no categorical palette, so there is nothing to run a
  colourblindness validator against. The accessibility answer is stronger than
  a validated palette rather than weaker: no reading depends on hue at all.
- Every figure carries `role="img"` and an `aria-label` naming its numbers, so
  the reader who cannot see the drawing gets the same facts.

## 3. The ask returns to the dispersion axis, on one screen

**What was removed on 2026-08-21, and why.** The dispersion strip used to draw
an axis with three things on it. `docs/reviews/2026-08-21-items-2-3-ruling.md`
promoted an item named **"strip the landing screen"**, and
`DispersionStrip.tsx`'s own docstring records the three objections:

1. **No direction.** Drawing the ask against the readings renders "Kalshi is
   low/high here" — the tool's opinion of an edge.
2. **No `used` mark.** Inking the reading the sizer picked re-renders the
   discredited point estimate one layer down.
3. **A range, not a figure.**

**What this ADR changes: (1), on `/market/[ticker]` only.** (2) and (3) stay
removed on both surfaces.

The reasoning is that the ruling's item is named for the landing screen, and
the market page is a different question:

- **ADR 0068** puts the desk's five areas **fully present** on
  `/market/[ticker]` — the owner rejected the reveal pattern outright there.
- **ADR 0071 §2.2** makes price transparency at the moment of a bet the desk's
  *entire job*, chosen by Joe over braking and over record-keeping.
- **ADR 0071 §2.5** already permits both prices on a row: *"a per-row fact is
  transparency; an ordering is a claim."* Two prices on one axis is the same
  fact with a shared scale.

**The tick is neutral by construction, and that is what keeps (1)'s objection
answered.** No colour, no arrow, no cheap/expensive wording — a dashed
`--muted` rule with the label "Kalshi". `tests/test_dispersion_strip.py`
forbids the direction words by name. What the ruling objected to was the
*verdict*; what is drawn is the *position*.

**The never-stretch rule is untouched and is what makes drawing it honest at
all.** `dispersion()` returns `x: null` when the ask falls outside the axis and
the domain is **not** widened to hold it — a 26-point gap would squash four
readings 0.4 points apart into a single pixel. Off-scale is said in words. A
marker pinned to the end of a scale it is not on is a drawing that lies.

**The landing screen keeps its one honest line.** `variant="chart"` is opt-in
and only `ConsensusPanel` passes it; the slate row still renders the text-only
range behind a tap.

## 4. `overround` is served for the first time

`fair_prices.overround` — the books' raw implied probabilities summed — has
been stored since the beginning and read by **nothing**. It is the number that
makes devigging checkable rather than a word taken on trust: two sides quoted
at 54% and 51% come to 105%, a probability cannot do that, and the extra five
points are the house's cut.

It is `None` when unrecorded and **never 1.0** — 1.0 is a real and very
unusual measurement (a book quoting with no margin at all), and substituting it
for "we did not record this" would put the most surprising possible reading in
place of a missing one.

## 5. What the pictures may not become

- **No second y-axis anywhere.** The parlay chart draws chance falling and
  **not** payout rising. Barred twice: two scales on one chart is never
  correct, and "chance falls while payout rises" is an expected-value claim
  `/api/parlays` carries none of by construction.
- **No fitted line on the record.**
  `docs/reviews/2026-08-21-items-2-3-ruling.md` caps "CLV on his own bets" at
  *"per-bet rows only — no average, no hit rate"* until n ≥ 30 with the
  per-group view beside it. The record chart draws the cumulative money and
  nothing else: no trend, no win rate, no CLV series, and it never touches the
  embargoed estimate log.
- **No verdict words.** Tests forbid cheap/expensive/overpriced/underpriced and
  breakeven/EV/kelly from reaching the market-page figures.

## 6. The honesty that cost something: a cumulative total over a gap

`venue_settlements` rows carry `net_tenths = null` when the venue's record does
not support the registered settlement formula. A cumulative line cannot step
over one:

- **Skipping it** asserts the settlement was worth zero.
- **Carrying the previous value forward** asserts nothing changed.

Both are claims. What is true is that after the first uncomputable settlement,
every later point is a **lower bound**. The line is drawn dashed from there,
the caption names how many rows caused it, and the accessible label says
"or better" rather than stating a figure it cannot support.

## 7. Rejected, with reasons

- **A payout curve beside the parlay chance curve.** §5.
- **Colouring the record line by whether it is currently up.**
  `--positive`/`--negative` are polarity and a cumulative balance has none at a
  point; the colour would repaint the whole history every time a bet settles.
- **Restoring the `used` mark now that an axis exists again.** The 2026-08-21
  objection to it is independent of the surface: it re-renders a point
  estimate this project has discredited. All four readings are drawn alike and
  the caption says the lowest is taken.
- **Widening the dispersion axis to guarantee the ask is always visible.** §3 —
  it destroys the picture on exactly the rows worth looking at.
- **Re-running the copula at each parlay prefix.** Six more 200,000-sample
  Monte-Carlo runs per card for a difference in hundredths of a point. The
  chart draws the plain product and states the gap, which the payload already
  computes.
