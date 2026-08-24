# 0070 — The desk sells parlay cards, and a combo is priced off its own book

Accepted 2026-08-23. Joe's direction, given with a screenshot: his
cousin-in-law hit a Kalshi 6-market combo — six cross-game spread legs,
$4.99 in, $333.33 max — and Joe wants the cockpit to produce good parlays
like it. Scope chosen by him over the cheaper options (AskUserQuestion,
2026-08-23): spread legs now, the real Kalshi combo price fetched via
`lookup_combo`, and a ladder of three daily cards.

## 1. What this overturns, and what it does not

**Overturned: the Builder removal's application to this surface.** The
2026-08-22 review deleted `/builder` because a parlay calculator in the nav
invites a novice into the highest-hold product, off-platform and uncapped
(`Nav.tsx:18`, `Footer.tsx`). The parlay desk is the opposite construction:
Kalshi's own product, on the operator's own cockpit, opened *with* the fair
joint probability, the per-method band, the enter-only warning and the
fee-unverified sentence in view, at preset stakes topping out at $20. The
Footer's rationale was about an unframed calculator; this is a framed card.
The reachability test's delete-commit question is answered: Joe asked for
this screen by name.

**Not overturned: ADR 0038 and ADR 0062.** The hunt stays closed. The desk
is a betting-desk feature — Joe's ruling that the edge-finder is a feature,
not a determiner — and nothing in it claims an edge: no breakeven, EV,
kelly or size key exists in any parlay payload (`tests/test_parlays_api.py`
walks the keys), nothing writes `recommendations`, and `gate.py` never
reads any of it.

**Not overturned: ADR 0046's tripwire.** No combo EV is computed through
`calculate_fee` — the measured record says every combo fill charged at
least `0.070·C·P·(1−P)` and some charged more, so the standard model
*undercharges* and any EV built on it flatters. The card carries the fee
sentence verbatim; an EV column waits for a freshly registered combo fee
look (Joe has fee-calibration trades authorized; optional Slice D).

**Not touched: the 2026-08-21 veto.** Joe vetoed the terminal spread/total
*edge look* — a measurement. The spreads work here (Slice B) is ingestion
and fair pricing for card construction; it writes `fair_prices` only, takes
no registered look, and computes no edge.

## 2. The decisions

1. **The headline joint is the conservative one, and the bias is named.**
   Each leg's `fair_probability` is the minimum of four devig methods;
   multiplying N of them compounds that conservatism N-fold. The card
   states the headline from `p_conservative` legs and serves the same
   copula joint under each single method beside it as a range
   (`fair_prices` stores all four columns per row precisely so this
   disagreement is visible). The headline is deliberately pessimistic;
   the band is the honest width.

2. **One leg per fixture, structurally.** `backend/core/ladder.py` selects
   at most one leg per `odds_event_id`, so `correlation.py`'s same-game
   refusal is unreachable from card construction rather than handled.
   Same-game parlays need a measured correlation this repo does not have
   (ADR 0012 §5: 0 of 344 same-game joints ever observed two-sided).
   Cross-game legs use the module's same-day nudges (0.05 same-league,
   0.02 cross-league) through the seeded Gaussian copula.

3. **Fair beside cost is lawful on `/parlays` only.** The standing rule —
   fair% and break-even never share a block — protects the slate and the
   market screen, where the pair reconstructs the engine's measured
   negative edge on a single contract. A parlay's *hold* is the product
   being displayed (the shipped `POST /api/builder/parlay` precedent),
   and it is computed against Kalshi's quoted combo cost, not against the
   engine's per-market breakeven. Scoped to the parlay surfaces; the
   slate and market-page key-walk tests are untouched.

4. **A combo is priced off its order book, never the `/markets` list row.**
   ADR 0012 and the E2/E3 measurements: the list ask is the complement of
   a resting NO bid, echoes its own legs' prices on the dominated rows,
   and skews from the book by up to 30.5 cents. The lookup path reads the
   minted market's book and derives the YES ask as `1 − best NO bid`; an
   empty book is an honest refusal ("nothing is resting; you could not
   buy this right now"), not a price.

5. **Every lookup is recorded.** `lookup_combo` with
   `allow_market_creation=True` mints a real market on the exchange
   (authorized: Joe's approved-actions list). `parlay_lookups` (schema
   v20) records every attempt — priced, book-empty, no-collection, or
   error — the way `manual_orders` records every send.

6. **Freshness is measured end to end, or refused.** v20 adds
   `fair_prices.oldest_book_age_ms` (the consensus's stalest input at
   compute time); a leg's live age is `(now − computed_ms) + that`, a
   card is only as fresh as its stalest leg, and a pre-v20 row whose age
   is unmeasurable is excluded by name — never aged zero.

7. **Money strings render server-side.** Preset stakes ($1/$5/$10/$20,
   $5 default) are priced in `backend/parlays.py`; the client never does
   money arithmetic (the `lib/api.ts` rule).

## 3. What the cards do not establish

The fair joint is what the sportsbook consensus implies, filtered through
a deliberately conservative per-leg floor. Whether Kalshi sells a card
below fair value is answered per card, per tap, by the lookup — and the
measured base rates are not encouraging: combos are enter-only on 40 of 40
books ever read, ≤18 units deep, with an unidentified fee schedule. The
desk shows the comparison honestly and lets Joe decide; it does not
recommend, size, or claim.
