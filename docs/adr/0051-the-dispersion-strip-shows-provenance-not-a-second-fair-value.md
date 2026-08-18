# 0051 — The dispersion strip shows provenance, not a second fair value

Date: 2026-08-19
Status: accepted

## Context

A Slate row says `54.19% fair`. Three separate choices produced that number and
no screen had ever shown any of them:

1. **Which devig method.** Four are computed and stored (`fair_prices.p_*`);
   the money path takes the **lowest**, per CLAUDE.md rule 2.
2. **Which books.** `consensus_devig` anchors on sharp books when any quoted,
   so the average is often over a strict subset — frequently one book.
3. **How far that sits from the field.** `BookDistribution` already records the
   min / median / max across *every* usable book, unanchored.

All three were recorded, all three were served on `/api/slate`, and nothing
rendered them — the "built but never called" pattern, one layer further out
than usual: built, *served*, and never called. This is the P2 dispersion strip
from ADR 0047's approved plan.

## Decision

`frontend/src/components/DispersionStrip.tsx`, geometry in
`frontend/src/lib/dispersion.ts`, rendered **xl-only on `/slate`** — the same
tier as the `anchored_on_sharp` and `market_width` columns, and for ADR 0047's
reason: everything below 1280px stays byte-identical. The component itself is
width-agnostic, so moving it to the phone later is a class change rather than a
rewrite. That is Joe's call, not a default.

Header: **"where the number came from"**. The word *fair* appears nowhere in
what the strip renders, and `tests/test_dispersion_strip.py` fails if it
returns. The row already says `fair` once, for the number it chose; reusing the
word for the inputs would suggest the four readings are four fair values and the
row picked among equals. It took the lowest, deliberately.

Four decisions inside it, each of which was a defect first — three of them found
by looking at the rendered page rather than by reasoning.

**1. Kalshi's ask does not set the scale.** The first version put the ask in the
domain. On the seeded `suspicious_edge` row the ask is 34.00% against readings
spanning 60.03–60.45%, so a linear axis over all of them squashed four readings
0.4 points apart into a single pixel — the strip showed nothing on the row where
*where did 60% come from* is the most interesting question on the page. The ask
is not an input to the fair value; the brief for this strip reads *min book →
four devig methods → max book*, and the ask is not in that list. It is drawn
when it happens to land inside the axis and is otherwise reported as `off this
scale`. Never clamped to an edge — a marker pinned to the end of a scale it is
not on is a drawing that lies.

**2. The bar is labelled "worst method each", because the geometry is
systematic and would otherwise read as a market fact.** Every point in the book
bar is a *minimum over four methods* per book (`backend/slate.py:191`); every
mark is *one* method, averaged over the anchored subset. So a mark is
structurally at or above the anchored book's own position, and on most seeded
rows all four sit above `max_book_probability`. Unlabelled, a reader concludes
"the consensus is higher than every book" — a claim about the market. It is a
fact about the statistic.

**3. Two decimals, not one.** The strip drew three visibly distinct marks whose
legend read `47.4%`, `47.4%`, `47.4%`. Three positions and one number looks like
a broken picture rather than a coarse label. A legend must resolve whatever the
drawing resolves. Not three decimals: these are averages over a handful of
books and a third decimal would be precision the inputs do not carry.

**4. It refuses to draw rather than mislead.** Fewer than two distinct readings
returns `null`, not an empty strip. One point looks like four methods agreeing
perfectly, which is the opposite of "only one could be read". A method that
could not be solved is *absent*, never plotted at `0` — `0` is a legitimate
probability and would drag the axis to the floor.

## The demo defect this uncovered, which was the larger find

**Every seeded recommendation disagreed with its own fair price.** All 11 rows,
by up to 0.35 probability points, in both directions.

`backend/seed_demo.py` ran `consensus_devig` over the seeded books, wrote it to
`fair_prices`, pointed `fair_price_id` at it — and then priced the
recommendation from a **second**, single-pair `devig()` over `scenario.odds`.
Production cannot do this: `runner.py:936` passes `build_recommendation` the
same `DevigResult` it just wrote.

It cost nothing while no screen read both columns. It became visible the instant
one rendered the four methods beside the fair value and their minimum
contradicted it — on the public demo, which is the portfolio piece. The
serializer already carried the check in a comment (`routes.py`: *"Should equal
`fair_probability` exactly. Sent so a consumer can check the join landed"*) and
nobody had ever run it.

The seeder now prices from the consensus it wrote.
`tests/test_seed_demo.py::TestTheSeededFairValueIsTheOneItPointsAt` fails if
they come apart again, and asserts separately that `p_conservative` really is
the minimum of the four — otherwise a seeder writing one invented number into
both columns would pass.

## What this does not establish

That the consensus is *correct*, or that anything on the strip is right. It
places numbers the record already holds on a shared axis. No point on it has
been scored against an outcome, none enters `suggested_contracts`, and the
component combines them into nothing — that would be a model, and it would need
its own ADR. It does not establish the invariant holds on **live**: the seeder
test reads the seeded database only.

## Verification

Suite 3,462 passed / 10 xfailed, ruff clean, `tsc` clean, build clean.
`scripts/check_mobile.py` clean at 390/768/1024/1440/1920/2560 against a local
build off a freshly reseeded `data/demo.db`; screenshots read at 1440 and 390.

Eleven guards disabled and watched go red. Two mutations initially came back
green and the two causes were opposite — one guard was decoration, one mutation
was too weak — which is the distinction `tasks/lessons.md` now carries:

- `assert "<DispersionStrip" in source` is a **prefix** match, so renaming the
  tag to `<DispersionStripUnused` — the obvious way to unwire it — left the
  wiring assertion green. Now a word boundary.
- A byte-level mutation written with `\n` matched nothing in `dispersion.ts`
  after a `write_text` on Windows silently converted the file to CRLF. The
  mutation script's assert-it-applied step is what caught it; without that step
  "the guard is green" and "the mutation never happened" are the same output.
