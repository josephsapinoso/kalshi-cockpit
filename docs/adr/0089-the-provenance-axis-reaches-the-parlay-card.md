# ADR 0089 — The provenance axis reaches the parlay card

Date: 2026-08-31
Status: accepted
Extends: ADR 0068, ADR 0071 §2.2 / §2.5
Relates to: `docs/reviews/2026-08-21-items-2-3-ruling.md`

## Context

The parlay card told the reader that a leg's four devig methods disagree by N
points and gave no way to see how. `method_spread_display` is a **summary of a
distribution the payload did not send** — the reader is asked to take the
disagreement on trust, on the one screen that offers money decisions.

Joe asked for real graphs on this screen — *"remember this is a cockpit"* — and
chose, from three options on 2026-08-31: **where each leg's number came from**,
**behind a tap**.

## The ruling this extends, and why extending it needed a decision

A per-row chart of the devig readings with Kalshi's ask among them was
**deliberately deleted** from the slate row on 2026-08-21 ("strip the landing
screen"). ADR 0068 and ADR 0071 §2.2 restored it on exactly **one** surface,
`/market/[ticker]`, because price transparency is that screen's whole job.

The parlay card is a **second** surface. Joe's choice is the authority for
that, and this ADR is the record so a future session does not read the 08-21
ruling and conclude the card is in breach.

## Decision

**Reuse `DispersionStrip variant="chart"` unchanged, per leg, behind a
`<details>`.** No new SVG. The component already implements the three
properties the ruling preserved, so they come along and cannot drift:

- **No direction on the ask** — a neutral tick with its own label, no colour,
  no arrow, no cheap/expensive wording. ADR 0071 §2.5 permits the two prices
  side by side; it forbids the verdict.
- **No `used` mark** — all four readings drawn alike. Inking the one the sizer
  picked re-renders the discredited point estimate one layer down.
- **The ask is never clamped onto the scale** — off-domain is said in words.
  *A marker pinned to the end of a scale it is not on is a drawing that lies.*

Behind a tap because six legs times an axis is a wall at 390px, which is the
precedent `LegProvenance` and `LegBuys` already set on this card.

### The payload

`_serialise_leg` now emits `methods` (the four readings plus
`p_conservative`, in the exact `DispersionMethods` wire shape) and
`ask_probability`. Two rules carried from `dispersion.ts`:

- **An unsolved method is `null` and PRESENT, never absent.** Absent means the
  route never joined `fair_prices`; `null` means the join ran and that method
  did not solve (`p_shin` is genuinely NULL on real rows). A parlay leg always
  comes from `fair_prices`, so a consumer may rely on every key being there.
- **The ask is `None` when unreadable, never 0.** A 0 ask is a free contract
  and a real price; using it for "could not read" would put the neutral tick
  at the far left of the axis.

**`books` is null on every leg, and that is a stated limit.** The unanchored
per-book distribution needs a per-book re-devig per leg, which `leg_facts`
already refuses as out of scope. `dispersion()` takes its axis from the marks
alone when the span is absent.

## Stated plainly rather than hidden

Emitting `p_conservative` and `ask_probability` on one leg makes the
consensus-vs-Kalshi gap reconstructible by subtraction at full precision. It
was already reconstructible from `fair_percent_display` and `ask_display`, and
ADR 0071 §2.5 permits showing the two side by side. **What stays forbidden is
ranking by it**, which `test_parlays_api.py` owns and which
`tests/test_parlay_leg_facts.py` now also asserts for this component.

## Consequences

- No new query. The ladder's fixed statement budget is untouched.
- Five guards, each mutation-observed-red: dropping unsolved methods, a 0 ask,
  a renamed wire key, a book span the leg never computed, and a hand-rolled
  axis in place of the component.
