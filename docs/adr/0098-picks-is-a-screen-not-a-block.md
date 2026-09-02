# ADR 0098 — "Picks" is a screen, not a block: amending ADR 0067 §2 and re-scoping §6

**Status:** draft, no ordinal — main assigns the number at merge.
**Date:** 2026-09-02.
**Decides:** decision-map #8 (ratified by Joe 2026-08-27) and #29 (Joe,
2026-09-02), as built. Amends ADR 0067.

## 1. What changed

ADR 0067 §2 sites the "likely winners tonight" block *above the rows* on the
slate screen, and §3 says the block "surfaces the books' opinion, it does not
claim the tool has one". Both were written for a block on a page whose nav
word is "Games". On 2026-09-02 the block became a screen of its own,
`frontend/src/app/picks/page.tsx`, and the nav word "Picks" — which for two
weeks opened `/board`, a screen on which nothing has been a pick in the life
of the record and every row of which mounts a live hand-bet button — now
opens it.

Three facts about the change, each recorded because a later reader would
otherwise infer the opposite:

- **A promotion, not a move.** The block stays on Games, rendered through the
  same `GoodChancePicks` component from the same `/api/slate` payload. Two
  render sites of one component, handed the server's block whole, cannot
  disagree about the ranking. (`tests/test_good_chance_picks.py` pins the
  Games site; `tests/test_picks_screen.py` pins the new one.)
- **`/board` is not deleted and not renamed in its route.** It goes to the
  footer as **Refusals** — Joe's word, #29 — with a sentence saying what it is.
  The h1, the footer label and the footer blurb agree. The in-page link from
  the foot of Picks that #8's first draft carried is struck: Joe took the
  footer alone, because every row on Refusals carries a live IOC button and a
  next-step affordance under a favourites list is the chase shape.
- **The nav word stays "Picks".** Joe was shown the ADR 0038 argument (a nav
  label is the product's own voice; `beta = -0.141` says the tool has no
  picks) and two alternatives, and kept his own word. The cost is paid in the
  page-top sentence, which spends a third of its length disarming the label
  — a ratified cost, not an unreviewed one (#9).

## 2. §2 amended: the block's placement is now a claim the product's chrome makes

§2's "above the rows" stays true of Games. It is no longer the whole siting:
a nav slot points at the block, and a nav slot is the product saying what it
is for. §3's assurance therefore comes under pressure it did not have as a
block, and the answer is the same as before, made structural: the server
sorts on one stored, unscored column (`fair_probability`, `routes.py`), the
chance≠edge sentence renders verbatim from the payload, and
`tests/test_slate_picks.py` fails the build on any key readable as profit.
Nothing in the promotion adds a claim; it adds a place the existing claim is
read from.

## 3. §6 re-scoped: from the block to the screen, plus two prohibitions

Every §6 prohibition on the block — no break-even, edge or size figure; no
money ink; nothing tappable into an order; exclusions counted in words —
applies to the screen. Two more become possible only once the block is a
screen, and both are pinned in `tests/test_picks_screen.py`:

1. **No headline or chip counting how many picks ranked.** A number that
   rises when there is more to bet on is a number the screen is not allowed
   to grow. The page may branch on `ranked.length`; it may not print it.
2. **No credit-spending refresh control as the empty-night content.**
   `RefreshOddsPanel` stays on Games. On the promoted screen it would be
   "act to make the list non-empty" — the chase affordance in its purest
   form — on the state this desk shows most often.

And one condition of shipping, from #8 amendment 2: **the safety envelope
travels.** Cash and the per-bet cap and the "Not tonight" control render on
`/picks` from the payload the page already fetches, so it is not the one
screen in the product naming bettable sides with no money context. The
deposit-arithmetic sentence does *not* travel — honest apparatus beside the
refusal machinery on Games, a funnel beside a favourites list at 11pm.

## 4. What this does not decide

- **The empty night's design.** `/picks` draws its four data states (absent
  block, nothing ranked, stale slate, unreachable backend) and a loading
  state minimally and honestly, so the tab never opens to an h1 and
  whitespace. #20 owns designing them.
- **`HowToRead` moving off `/board`.** #8 proposed it and it was not put to
  Joe. It stays where it is.
- **The lede on Games** (#9's first string) and the other four page-top
  sentences. Other lanes own those files.
- **The NO EDGE chip's semantics on Refusals** — #25.
