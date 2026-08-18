# 0047 — The desktop tier is a reading surface

Date: 2026-08-18
Status: accepted

## Context

Joe put the cockpit beside kalshi.com on a desktop monitor and asked why his
own tool wastes the screen. He was right about the waste: every page was a
centred column — the Board capped at `max-w-5xl` (1024px), most pages at
`max-w-3xl` (768px) — and `frontend/src` contained **zero** `md:`/`xl:`/`2xl:`
variants. On a 2560px monitor roughly 60% of the width was empty gutter.

No decision ever chose 1024. The phone-first constraint is real and documented
(the three designer agent files; the 390px review of 2026-08-09), but the
desktop width was an accident of Tailwind's default scale, recorded nowhere.
This ADR is the record that was missing, so the next widening argues with a
decision instead of a habit.

Six agents reviewed the question (ui/ux/graphic designers, sharp-bettor,
retail-bettor, tilt-prone-gambler). Two findings reshaped the work:

1. **Density multiplies defects.** `edgeTone` could not see
   `suggested_contracts`, so the modal row — positive raw edge, sized to zero
   contracts — rendered in the colour that means *take this*; and `--accent-2`,
   the ink on every warning, measured 2.75:1 on the light card. Both were fixed
   *before* any widening, because a wider screen shows forty rows where a phone
   shows six.
2. **The Board gains least.** Its content is mostly preconditions and captions
   around a card grid that is empty most nights. The Slate — nine facts per
   row wrapping raggedly inside 768px — is the screen the desktop tier is for.

## Decision

**Density serves evidence, never the offer.** The tier exists to let a reader
*compare and audit* more of the record at once — not to make anything easier
to bet, brighter, or more tempting. Every rule below is that sentence applied.

- **The shell caps at 84rem (`xl`) and 96rem (`2xl`), not full-bleed.**
  Kalshi's site is full-bleed because every pixel is another quote; this page
  is majority prose-with-reasons, and past ~96rem a flex row's `ml-auto` puts
  ~700px between a team name and the suppression code that is the row's
  content. Below `xl` every page is byte-identical to the phone-first design.
  The width lives in one constant (`frontend/src/lib/shell.ts`), imported by
  the Board shell, `Nav` and `Footer`, so chrome and content cannot drift.
- **The Board's context (window banner, schedule, refresh panel) becomes a
  24rem right rail at `xl`, by grid column assignment only.** The rail block
  comes first in the DOM — the phone's banner-first order, untouched — and is
  *assigned* to column 2. Not sticky: it is context, and context that follows
  the scroll competes with the cards it annotates.
- **The card grid stays 2-up at every width**, and its inner figure grid now
  fires on a *container* query (`@[30rem]:`) rather than a viewport
  breakpoint. 30rem is measured, not chosen: it is the cell width at which the
  old `lg:` variant happened to fire inside the 1024px shell. `surfaced` is
  0–3 on every night this instance has recorded; a third column would serve a
  population that does not exist and shrink figure cells below the measured
  86px minimum, a failure invisible to every automated check.
- **Widening the shell widens the data and never the prose.** Paragraphs cap
  at ~65ch at 320px and at 2560px alike; `tests/test_desktop_tier.py` enforces
  it per file. `WindowBanner` and `SignalStrip` carried no cap at all and were
  already rendering ~134ch lines inside the *old* shell.
- **The Slate is the flagship page**: from `xl` its rows become one aligned
  grid line each, and two fields the record always carried but never rendered
  join the row — `anchored_on_sharp` (every actionable row in the record's
  life was a soft-book fallback) and `market_width` in points, warning-inked
  exactly when the books' own disagreement exceeds the edge.
- **The refresh panel states its own preconditions** (`X of Y` tap credits
  spent, the day's budget, the next scheduled sweep) instead of borrowing them
  from sitting below the banner. Its safety used to be positional; a panel
  that can be placed in a rail must carry its context with it.
- **The nav chip is state, never permission**: window open/closed in muted ink
  at every state, `xl`-only, no counts, nothing green. The six-link budget is
  not renegotiated by a desktop feature.
- **The ticket becomes a centred, width-capped dialog at `lg`.** Unconstrained,
  the bottom sheet drew a monitor-wide filled Confirm on the order path — the
  largest, brightest control in the app, on the one screen that spends money.

## `/estimate` is excluded, permanently, on anchoring grounds

The estimate screen shows no price *by design*: `had_already_opened_kalshi` is
the calibration study's one recorded signal about the irreducible anchoring
hole. A cockpit laid out to live beside kalshi.com on one monitor would make
that flag 1 by construction. So the logging screen stays phone-shaped: log on
the phone, read on the desktop. A desktop `/estimate` proposal must answer
this paragraph, not just restyle the form.

## Rejected

- Full-bleed layout; a live ticker strip (empty it reads as breakage, full it
  manufactures motion); a 3-up card grid; the slate beside the cards (gives a
  refused row a bettable row's visual weight); a density toggle; a gate
  progress bar outside `/gate`; any P&L/CLV figure in chrome (study embargo);
  a "Kalshi | consensus | fair" panel (`fair_probability` *is*
  `p_conservative` — it would print one number twice and re-teach the
  two-signal belief CLAUDE.md has corrected twice); sortable columns on the
  Board (`/api/board` deliberately no longer ranks by apparent edge); links to
  kalshi.com (zero exist today; keep it that way).

## Verification

`scripts/check_mobile.py` at 390/768/1024/1440/1920/2560 — all clean,
including `/playbook`, whose five-column stat row had painted
"RECOMMENDATIONSMARKETS"-style overlaps at ≥1024 since before this tier
existed (fixed to four columns here, same measured method as its own 320px
comment). Source and behaviour guards live in `tests/test_desktop_tier.py`,
`tests/test_window_chip.py` (node executes the real chip predicate),
`tests/test_palette_contrast.py` (WCAG arithmetic on the tokens), and the
node-driven cross-product in `tests/test_board_screen.py` that proves a
zero-contract row can never render as money.
