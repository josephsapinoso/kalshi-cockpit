# ADR 0088 — The Scout flags a parlay leg, and five convenings a day is why it cannot gate one

Date: 2026-08-31
Status: accepted
Relates to: ADR 0069 (the pro-bettor seat), ADR 0071 §2.5 (show, never rank),
ADR 0081 (red means lose)

## Context

Joe's design ruling, 2026-08-30, in his own words: the Scout **gates
eligibility and flags** — a leg with a scratched starter or a red flag gets
dropped or warned — and **never moves the price**. He accepted this over
letting the Scout adjust the fair value. He also asked for the cockpit to be
visual: *"remember this is a cockpit."*

The scout desk already works and produces exactly the content he asked for
(verified on `KXWNBAGAME-26AUG30GSPDX-GS`: FIBA World Cup absences, an
unresolved neck contusion, and an honest "the Portland scout filed nothing").
What it did not do was reach the parlay card, where the legs are.

## The arithmetic that decides the design

A briefing is **four metered Anthropic calls** — two staff scouts, the master,
and the pro-bettor seat. The live ceilings (`fly.live.toml`):

    AGENT_MAX_CALLS_PER_DAY     = 24   -> 6 convenings
    AGENT_MAX_SEARCHES_PER_DAY  = 60   -> 5 convenings   <- binds first

**Five convenings a day.** The parlay ladder serves six cards of up to six legs
each, one leg per fixture. Scouting the legs of a *single* card could consume a
day's budget; scouting the ladder is off by an order of magnitude.

So "gates eligibility" **cannot be automatic**, and no amount of care in the
code changes that. This ADR records the gap between the ruling and the ceiling
rather than quietly implementing half the ruling and calling it done.

## Decision

**The card shows what the desk already knows about each leg's game. It
convenes nothing, and it gates nothing automatically.**

`leg_facts` gains five fields per leg — a state, a headline, the board tiles
worth seeing, the briefing's age, and the ticker it was filed against. All of
it is read from `scout_briefings` rows that already exist. **Zero calls, zero
credits, zero tokens.**

Three properties, each pinned by a test:

- **The join is by GAME, not by market.** `scout_briefings.ticker` is whatever
  market ticker was in front of Joe when he convened the desk, but a briefing
  describes a *fixture*. Matching leg to briefing by ticker would show a game
  as unscouted while its own briefing sat in the table, so the join runs
  through `kalshi_markets.event_ticker`, which `idx_markets_event` indexes.
- **Six states, because absence has three different meanings.** `absent`
  (nobody looked — the ordinary case at five a day), `filed_nothing` (the desk
  looked and had nothing), and `refused` (a ceiling turned it away) are not
  interchangeable, and only the middle one is information about the game.
  `briefing`, `briefed` and `failed` are the rest.
- **A gap is a flag.** `BoardTile` has four states rather than a boolean
  because the first real briefing's most decision-relevant fact was a *gap* —
  the weather unchecked. So every tile that is not `clear` becomes a flag,
  including `unconfirmed` and `stale_only`. Flagging findings alone would
  render that gap as calm, which is the exact misreading the four states exist
  to prevent.

### What the screen may not do

- **No scout value enters arithmetic.** Asserted over the component source,
  because the property is about what the component is *allowed* to do; a render
  test only shows what it happens to do today.
- **No scout value orders anything** — ADR 0071 §2.5, and here for a sharper
  reason than usual: with five convenings a day, ranking by scout state would
  rank by *which games Joe happened to tap*, not by anything about the bets.
- **No colour.** The palette's red means "lose" (ADR 0081). A word about a
  lineup is not a verdict about money, and colouring it like one would make the
  screen claim something the desk did not.

## What is deliberately NOT built

- **Automatic gating or dropping.** The ruling asks for it and the budget
  forbids it. A leg is never removed for a scout flag; Joe reads the flag.
- **A per-leg "send the desk" button.** It is the obvious next step and it
  spends real money per tap, so it wants its own decision about *who* may spend
  a fifth of the day's budget from a card, and what the screen says about the
  four remaining.
- **The graphs.** Joe asked for real instrument-panel visuals and this slice
  ships words. Naming that as missing is better than shipping a chart of a
  field that is `absent` on most legs.

## Consequences

- `leg_facts` costs a third statement — still one for the whole ladder. The
  O(1)-in-legs guard now asserts the exact set of fact families rather than the
  number 2, so a fourth has to come and say what it is.
- **A test in this change asserted a bug that cannot happen.** The first
  version of the shallow-copy guard claimed a mutation it had not run;
  removing the line left it green, because `_scout_facts` builds its own list.
  Rewritten to assert the invariant that *is* load-bearing — no leg is handed
  `_NO_FACTS`'s own list, which one future in-place `append` would poison for
  the life of the process. Recorded because it is ADR 0087's failure, one file
  later and one day later.
