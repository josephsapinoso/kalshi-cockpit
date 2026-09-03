# ADR DRAFT — The nav is four links and a search; Gate and Playbook go to the footer, demoted and not retired

**Status:** draft, no ordinal — main assigns the number at merge.
**Date:** 2026-09-02.
**Decides:** decision-map #18 (Joe, 2026-09-02, option A), as built. Amends
the "six-link budget" wherever ADR 0047 §(context rail), ADR 0073 and ADR
0078 cite it: the budget is four links and a search button now.

## 1. What was decided, and by whom

Ticket #18 asked whether a six-link top row survives filters and search.
Its own re-scoping (2026-08-28) found the premise false before the question
was put: measured at 390px, the six-link row's `scrollWidth` was **424
against a `clientWidth` of 318** — Playbook already off-screen at 390 and
Gate off at 320 — while every "Gate keeps its visible slot at 390px" in the
repo was a comment or a docstring. The nav had been scrolling for two weeks
and nothing had measured it.

Joe chose option A: **Gate and Playbook move to the footer; search becomes
a header affordance.** He accepted the cost the ticket named — the screen
that says whether money can move is a tap further away — on the ground that
it is read and not acted on.

## 2. What was built

- `Nav.tsx` carries four links — Games, Picks, Parlays, Your bets — the four
  screens a bet is looked at or read back from on the day, in the order #8
  left them. Beside the logo is a search button that opens the existing
  `MarketSearch` (the one the Games and market screens host) as a layer
  under the header. It is closed until tapped, closed again on every
  navigation and on Escape, and **nothing is mounted while it is closed**:
  the search opens a hand-bet ticket, and it exists on a page only while
  asked for, after a typed name. The Picks screen's "no door to money" rule
  (#8) is about what the page renders and is still pinned on the page's
  source.
- `Footer.tsx` takes Gate and Playbook as its first two entries, under
  their own names, each with a blurb. The footer is six against the nav's
  four.
- A market page (`/market/[ticker]`) now lights Games in the nav, with
  `aria-current="page"`. Before this nothing lit there.

## 3. The condition that is the point of this record

**The footer link is called "Gate", and `/gate` keeps its games-against-300
count.** The partner's ranking made this a hard condition and it was
ratified: a gate that *looks* retired — renamed, softened, its number gone —
is how a session that never read CLAUDE.md re-derives "the gate will open"
as a step in a plan. The demotion is defensible *because* the screen is read
and not acted on; that defence holds only while the link still reads as the
interlock it is. `tests/test_every_screen_is_reachable.py::TestTheGateIs
DemotedNotRetired` pins the label, the 300 in the blurb, and the phrase on
the page.

## 4. The measurement, and what it did and did not fix

Taken over CDP against a local `next dev` at 390×844 (deviceScaleFactor 2,
mobile), the instrument `scripts/check_mobile.py` uses:

| state | row clientWidth | row scrollWidth | what is past the edge |
|---|---|---|---|
| six links (ticket, 2026-08-28) | 318 | 424 | Gate partly, Playbook, toggle |
| four links, old spacing | 274 | 298 | the theme toggle, by 24px |
| four links, tightened at base | 272 | 272 | nothing; 10px of slack |

The tightening is every base-width gap (`px-1.5` links, `gap-0` row,
`gap-1.5` nav, `ml-0.5` toggle, a 32px search tile with a 44px
pseudo-element target) widening back at `sm:`. **The header's rendered
height is 69px before and after** (68 of nav, 1 of border), open or closed:
the panel is an absolute layer and the theme toggle keeps the 36px that sets
the row's height. The toggle was shrunk to 32px in one pass and put back
because it moved the header to 65px and the fit did not need it — the
sticky filter bar the list screens hang under the nav (Lane B of this build) is not
moved.

**At 320px the row still scrolls, by 60px** — "Your bets" is cut at x=326
against a row edge of 304 and the toggle is off. The ticket asked for 320
to be measured rather than promised. It is recorded, in the nav comment and
here, and not fixed here: the four labels are the screens' own names (#29,
one screen one name) and the remaining levers — a shorter label, hiding the
toggle below `sm`, a second row — are each a product decision this ticket
did not take.

## 5. The test rule that was retired, and what replaced it

`test_the_footer_does_not_quietly_absorb_the_whole_app` bounded the footer
at the nav's own length ("never MORE than the nav"), so that the next screen
the nav shed had to answer the delete-commit question rather than land in
the footer by default. Joe's decision makes the footer six against four, so
the bound would fail on the decision itself.

What replaces it keeps the property the bound was for: the footer is pinned
**entry by entry** (`test_the_footer_holds_exactly_the_screens_the_nav_shed`),
each with its date and reason in the docstring, and no route may appear in
both lists (`test_no_screen_is_linked_from_both_lists`). A screen still
cannot land in the footer without being written into a test as a decision.

## 6. What this does not decide

- Whether the theme toggle belongs in the nav row at all. It is the
  control that decides the row's height and the last thing to fit at 390.
- Anything about `MarketSearch`'s behaviour. It gained an `open` prop (the
  header host passes it; the page hosts pass nothing) and a `useId` so two
  mounted copies do not share an input id. Its results, its masking (ADR
  0065) and its exclusion of combinations (ADR 0073) are untouched.
- The 320px question, per §4.
