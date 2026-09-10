# Two short spreads is a rule Joe chose

**Status:** Accepted, 2026-09-10.
**Date:** 2026-09-10.
**Supersedes nothing.** A seventh cut of `backend/core/ladder.py`'s one pool
(ADR 0070), alongside `safe`, `middle`, `lottery`, `longshot`, `soon` and
`agreed`.

## 1. The recipe

`short_spreads` ("Two short spreads"): exactly two `spreads` legs, each a
small handicap — the book's point no wider than 3.5 — from two different
games, in any sport the ladder already carries a spread for. Mechanically it
is one more `Recipe` in `CARD_SHAPES`:

- `markets=frozenset({"spreads"})` — the existing per-card market gate
  (`ladder.py:103-115`) already used by every other card, so a moneyline or a
  prop is structurally unreachable here, not merely unlikely. Widening the
  pool with props changes no card, this one included
  (`tests/test_ladder.py::TestRecipesAreGatedToTheirMarkets`).
- `max_spread_margin=3.5` — a new `Recipe` knob beside `max_method_spread`,
  read in `_pool_for`. A spread `CandidateLeg`'s `point` is always the book's
  own number and always negative (`backend/kalshi/spreads.py:108-124`: a
  Kalshi "T wins by over S" YES market is the book's `(T, -S)`), so the test
  is on the handicap's magnitude, `-leg.point > max_spread_margin`, not on
  its sign. `None` (the default on every other card) leaves spreads
  unbounded, so nothing about an existing card moved.
- `min_legs=max_legs=2` — exact, like `middle` and `lottery`; a one-leg or
  three-leg card would be a different product than the one the title names.
- Ranking is the module default (likeliest-first, `longest_first=False`) —
  the same ranking rule as `safe`, `middle` and `soon`.

Selection re-uses the one-leg-per-fixture guard (`_best_per_game`) that every
recipe inherits, unmodified — `short_spreads` does not touch it and did not
need to.

## 2. Why two legs, and why 3.5

Joe's rule, taught as craft rather than claimed as an edge — this project's
hunt for an edge is closed (ADR 0038, CLAUDE.md) and nothing here reopens it.

A parlay's **hold** — the seller's margin baked into the combined price,
relative to the fair joint — grows with leg count because Kalshi's own
per-contract fee compounds across legs while the fair joint shrinks
multiplicatively. Two legs is the shortest a Kalshi *combination* can be and
still be a combination; it sits closest, of every length on this ladder, to
the hold on two single bets bought separately (the sharp-bettor's estimate
behind this ADR: roughly 4.5% on a two-leg combination against roughly 2.5%
for the same two picks bought singly — a difference, not a promise, and nowhere
computed or served by this code). Every other card on the ladder trades a
longer, higher-hold combination for a **plain win** rung, this one for a
**spread**.

3.5 is chosen for the same reason: a spread of 3.5 or fewer points (or runs,
in MLB) sits close to a coin flip for most matchups this ladder sees, because
the book set the number specifically to make the two sides close to even. A
near-coin-flip leg's price is dominated by the sportsbook's **visible** vig —
the gap between the quoted price and 50% — rather than by the extra margin
books quietly load onto a longshot side (the same "longshot skew" ADR 0036/
0037 and the model-vs-Kalshi work in this repo have already measured is real
and is not this project's to model). A wide spread (a 10-point favorite, say)
buries its margin inside a skewed price the same way a longshot moneyline
does; a short spread does not have anywhere to hide it. Teaching the
distinction is the point of the card, not sizing an edge from it — see §3.

## 3. A rule, not a ranking — ADR 0071 §2.5

`short_spreads` selects which pool of legs a card is built FROM (spreads,
short ones, two of them). It does **not** rank the resulting legs, or any
other card's legs, by the consensus-vs-Kalshi gap. ADR 0071 §2.5 is explicit
that the gap "is displayed per row and never ranked by": `beta = -0.141`
means ranking by that gap would put the least trustworthy rows at the top,
and no card on this ladder does that. `short_spreads` ranks by
`p_conservative` and the clock tie-break, the same `_sort_key` every other
card uses (`ladder.py:327-333`) — a selection criterion (which market, how
short) is a different kind of decision than an ordering criterion (which row
first), and only the second one is barred.

## 4. Same-game stays out — ADR 0012 §5

`short_spreads` takes its two legs through the same `_best_per_game` guard
every recipe takes: at most one leg per `odds_event_id`, so two legs never
come from the same fixture and `CorrelationRefused` stays structurally
unreachable from this card exactly as it is from the other six
(`ladder.py`'s module docstring; `tests/test_ladder.py::
TestEveryRecipeInheritsTheGuards`, parameterised over `CARD_SHAPES` and now
covering `short_spreads` automatically). A same-game combination needs a
measured correlation this repo does not have (ADR 0012 §5) — `short_spreads`
introduces no exception and needed no new code to avoid one.

## 5. The Kalshi quote rate is UNMEASURED, and the prior is unfavourable

This ADR does **not** claim `short_spreads` will be buyable on Kalshi. The
desk prices every card at the sportsbook consensus's fair value; whether
Kalshi's own combination market has anyone selling at or near that price is a
separate, harder fact this project has repeatedly found to be the bottleneck
(ADR 0038: "combinations are enter-only"; CLAUDE.md's cost-bar section).

**The only evidence on hand points the wrong way, and it is weak evidence.**
Read off the live lookup log: of 11 parlay lookups whose card contained at
least one spread leg, 0 came back with a quoted ask; of 28 lookups whose card
was moneyline-only, 12 did. This is **not** a controlled comparison — the 39
lookups are Joe's own taps, self-selecting for whichever card looked
promising that night, and the two groups are confounded with league and date
(a run of spread-leg taps on a thin NCAAF night says nothing a run of
moneyline taps on a full MLB slate would have said too). It is stated here as
a prior, not a finding, and specifically **not** as a mechanism — nothing
measures *why* a spread combination would quote worse.

**The falsifying pair, stated in advance so this prior can be overturned
cleanly:** one lookup of a `short_spreads` card and one lookup of a
moneyline-only card (e.g. `safe`), on the same slate, within the same minute.
If both come back quoted, or both come back unquoted, the 11-vs-28 split
above was league/date confound, not a spread effect, and this section should
be corrected rather than re-cited.

## 6. Not pushed to the phone

`PUSHED_CARD_KEYS` (`backend/notify/alerts.py:261`) stays `{safe, middle,
lottery}` — `short_spreads` is not added to it. It is reachable from `/api/
parlays` and the parlay screen like every other card; it does not interrupt
Joe's phone. `tests/test_parlay_cards_reach_the_phone.py`'s subset assertion
is unchanged by this ADR and still holds.

## What this does not establish

- That `short_spreads` is worth buying, or that its fair joint is
  well-calibrated — the same caveats `ladder.py`'s module docstring states
  for every card apply here without modification.
- That 3.5 is the "right" cutoff in any measured sense. It is Joe's chosen
  handicap bound, taught as the point past which a spread stops reading as a
  near-coin-flip.
- That two legs is optimal, only that it is the shortest a combination can be
  and the sharp-bettor's stated reason it sits closest to two singles' hold.
- Anything about the 11-vs-28 quote-rate split beyond what §5 states. It is a
  prior awaiting the falsifying pair, not a result.
