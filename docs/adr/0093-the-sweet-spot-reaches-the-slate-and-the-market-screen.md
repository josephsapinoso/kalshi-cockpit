# ADR 0093 — The sweet spot reaches the slate row and the market screen, and finds a four-month-old arithmetic error on the way

Date: 2026-08-31
Status: accepted
Relates to: ADR 0090 (the score), ADR 0089, ADR 0068, ADR 0071 §2.2/§2.5,
ADR 0051, ADR 0081, the 2026-08-21 dispersion ruling

## Context

ADR 0090 built the evidence score and shipped it on **one** of the three
surfaces Joe chose. Its own closing line records the gap: *"Still open from
Joe's own choice: the SLATE ROW and MARKET DETAIL surfaces. He picked all
three. The module is surface-agnostic precisely so they consume the same score
rather than computing their own."*

This is the other two.

## Decision

`/api/slate` and `/api/market/{ticker}` serve the same `trust` payload the
parlay card carries, computed by the same `score_trust`, and all three screens
render it through one extracted component.

### The wiring, and where each input comes from

`_serialise` gains `trust_thresholds` and `scout`. Both routes already join
`fair_prices` and already reconstruct the live ages, so the score is assembled
where the two halves meet rather than by a second query per row.

Three arguments are worth stating because they differ from the parlay path:

- **`skeptic="checked"` is true by construction, not a guess.** `_serialise`
  serialises a `recommendations` row, and the existence of that row is exactly
  what `parlays.leg_facts` looks up to decide between `checked` and `absent`.
  The parlay path has to ask because it starts from a leg; this path starts
  from the answer.
- **`depth_at_ask` is the depth recorded with the row**, not a fresh read. That
  is the honest pairing — every other input is that same observation's, and
  `quote_fresh` is the check that says how old the whole set is. Re-reading the
  book for one field would score a row's depth against a different instant from
  its price.
- **The scout state comes from `parlays.scouting_facts`**, made public for this,
  because there is exactly one correct way to get it: the join is through
  `kalshi_markets.event_ticker` (a briefing is about a *fixture*; the
  `scout_briefings.ticker` is a *market*). A second reader matching the row's
  own ticker would show a scouted game as unscouted on one screen and scouted
  on another. One query for the whole slate, before the loop.

### What is refused rather than half-computed

- **Thresholds without a clock raise.** Without `now_ms` and `staleness` there
  is no live age at all, so both clock checks would read `unknown` and the row
  would look examined when nothing was measured.
- **A row whose `fair_prices` join found nothing gets `trust: null`.**
  `book_count` is `NOT NULL` in that table, so `None` is the join's own tell.
  Four of the eight checks read off that row, and scoring anyway publishes
  *"fewer than two devig methods solved"* — a claim about the devig when the
  truth is that there was no fair price to read. Four unknowns from one missing
  join is also not the same quantity as four separately unmeasured checks, and
  the payload has no way to say which it is holding.
- **The Ledger gets no key at all.** It calls `_serialise` with neither a clock
  nor thresholds, so a historical row cannot acquire a score computed from
  write-time ages.

### One renderer

`frontend/src/components/TrustNote.tsx`, extracted from `ParlayCards.tsx`. The
same reasoning as `DispersionStrip variant="chart"` in ADR 0089: the honesty
properties are guarantees about **one implementation**, and a copy on a second
screen would carry none of them while passing every test written about that
screen. The properties, each with the failure it prevents, are in the
component's own docstring and pinned in `tests/test_trust_surfaces.py`.

Two changes the extraction forced, both because the element now has three
hosts:

- **The clean-row sentence says "here", not "on this leg".** A noun true of one
  surface is a lie on the other two.
- **The prose sets its own size rather than inheriting one.** On the card the
  failure list sat inside an 11px list item and looked right; the first slate
  row put the identical element in a row with no size class and it rendered at
  body size — the loudest text on a row whose every other caption is `text-xs`.
  A component whose weight depends on where it is hosted has no consistent
  typography, and this component's rules are rules about what a reader sees.
  `size="panel"` changes the scale and nothing else; the caveat stays inside
  the score's own span on both values, and the tests assert that.

## The finding: the dispersion strip has been overstating disagreement by a fifth

Putting the score on the slate row put a **second rendering of one quantity**
beside an existing one. They disagreed:

    READINGS DISAGREE BY 0.6 PTS        four methods within 0.5 pts
    READINGS DISAGREE BY 8.4 PTS        four methods span 7.0 pts, over 2

`DispersionStrip`'s summary computed `(d.domain.hi - d.domain.lo) * 100`. That
is the **padded axis**, not the readings' span, and it is wrong twice over —
both errors in the same direction:

1. `dispersion.ts` pads the domain by a tenth of the span at each end so a mark
   sitting at an extreme is not half-clipped by the edge. The axis is therefore
   exactly **1.2×** the span. Every row ever rendered read 20% high.
2. `dispersion.ts` also pushes the **book span** into `values` when one is
   present. On those rows the headline was not about the readings at all —
   while the sentence one line below it, computed off `methodLo`/`methodHi`,
   was correct the whole time.

Fixed to `(methodHi - methodLo) * 100`, which is the same quantity
`core.trust.method_spread_points` computes. That helper is now the one
definition, and `parlays._method_spread_points` delegates to it rather than
repeating the arithmetic.

**The lesson is how it was found.** The figure was wrong from the day it
shipped, on two surfaces, and no test caught it because **a number cannot be
checked against itself** — nothing else on the screen claimed the same
quantity, so every assertion about it compared it to its own derivation. What
found it was rendering a second, independently-derived copy of the same fact on
the same row and reading them side by side. Two numbers for one fact is
normally a defect; here it was the instrument.

## What it costs, measured rather than assumed

`/api/slate` was the route being cured of an N+1 shape, so the added read was
bounded before shipping rather than after. On a synthetic slate of **100 rows
across 60 games and 360 markets**:

    /api/slate                    36-39 ms   (100 rows, all 100 scored)
    scouting_facts alone           0.2-0.4 ms (120 tickers, one query)

The scout read is one statement with an `IN` clause, driven by
`idx_markets_event` and `idx_scout_briefings_ticker`, both of which already
exist. `score_trust` is pure arithmetic over values the row already carries.
Neither adds a per-row query.

**What this does not measure**: the live database, whose `kalshi_quotes` table
is 451 MB and whose `scout_briefings` holds real rows. The shape is
size-independent (one statement, indexed both sides) but the number above is a
synthetic one, and the honest claim is "no N+1 was added", not "it is 36 ms on
live."

## What this does not establish

- **That a high-trust row wins.** Nothing here is scored against an outcome.
  Doing so would be a new measurement needing its own registration.
- **That the checks are equally important.** They are counted equally because
  that is the only weighting that invents nothing.
- **That the score changes what Joe should bet.** It is evidence quality, not
  bet quality, and it neither ranks rows nor gates anything. ADR 0071 §2.5's
  ordering ban is untouched: the slate is still sorted by kickoff, the market
  screen shows one row, and no surface sorts by this.
- **That it was read at 390px.** The browser check was taken at desktop width;
  the window resize did not take. Both new elements are wrapping prose inside
  slots the row already uses full-width (`w-full xl:col-span-full`, the same
  wrapper as the gloss line and `DispersionStrip`), so the phone behaviour is
  inherited rather than new — but it was not directly observed, and that is
  stated rather than assumed.

## The redundancy that was left in deliberately

On a slate row the failure list repeats facts the row already carries — the
staleness line, the suppression code. Trimming those would mean the trust
list's completeness depended on which screen it was on, which is surface-
specific logic inside a surface-agnostic component. **Every failure is named,
never just the first** (ADR 0090): dropping one because a neighbouring element
happens to show it is the importance weight the module refuses to invent,
wearing a different hat. What the list adds on a thin row is the part that is
nowhere else — *"1 book(s), need 2"*, *"no second book to disagree with"*,
*"3 at the ask, need 10"*.

## The boundary is unchanged

`gate.py` still may not import `core/trust.py`; the module still writes
nothing, still holds no clock of its own, and still takes primitives and
returns a result. Adding two callers did not add a database read to it — the
callers do the reading.
