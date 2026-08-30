# ADR 0085 — The parlay desk prices a bet it cannot place

Date: 2026-08-30
Status: accepted
Amends: ADR 0012 §5, ADR 0070, ADR 0084

## Context

ADR 0084 shipped the buy path: the desk mints a combination and rests a bid on
it at Joe's price. It works — a real order, 9 contracts at 20.1c, resting on
the exchange, confirmed at the venue.

It has not filled, and the census taken the same evening says it probably will
not. **61 open combination markets, 0 with a quoted ask, 0 with any liquidity,
1 that has ever traded** (`docs/measurements/2026-08-30-combination-liquidity-
census.md`). Joe's own order is the entire book on its market.

Joe found this out the way users find things out: he placed the order, went
looking for it under Positions in the Kalshi app, and found nothing. He was
right to look and right to be confused. The screen had told him a resting bid
was "an offer standing" — which in market language names the *sell* side — and
had never told him that an exchange needs a counterparty where a sportsbook
does not.

His question, which is the right one: *"is it possible to explore instead
existing parlays in Kalshi that are good potential… and buy them directly?"*
The census is the answer: such a screen would be empty, today and on every date
this project has looked.

## Decision

**The parlay desk's job on Kalshi is pricing, not buying, and the card says so.**

The card leads with what the parlay is worth as **a price to demand elsewhere**
— the fair joint expressed as the odds a sportsbook would have to offer to
match it. That number is useful exactly where the bet can be placed, which
today is a sportsbook, and it is the thing the desk is genuinely good at: a
devigged consensus across sharp books, four devig methods, the worst of them
taken, correlation charged.

The Kalshi buy path stays and is demoted. It is not removed, for two reasons:
it works, and one combination has traded, so the counterparty is rare rather
than impossible. It is no longer the card's headline.

### What the card must not do

- **It must not rank cards by the gap between our fair value and Kalshi's
  price.** ADR 0071 §2.5, unchanged and now more relevant: `beta = -0.141`
  means that ordering puts the least trustworthy rows on top. Showing the gap
  on a row is transparency; sorting by it is a claim.
- **It must not present the price-to-beat as an edge.** It is a break-even
  line. Getting exactly that price is a fair bet, not a good one, and the card
  says that in those words.
- **It must not imply a fill is likely.** 61 of 61 empty is the evidence, and
  the words carry it.

## Consequences

**The tool's honest pitch for parlays changes.** It is not "buy parlays on
Kalshi cheaply". It is "know what your parlay is worth before a sportsbook
quotes you a price". That is a narrower claim and a true one, and it is what
ADR 0071 already said the desk was for — price transparency at the moment of a
bet — applied to a bet that will be placed somewhere else.

**ADR 0012 §5's "enter-only" is upgraded.** The entry side is usually missing
too. The phrase to use is that combinations are *unquoted*: neither buyable nor
sellable at a resting price, most of the time.

**ADR 0084 is not reverted.** The buy path, the shard routing, the cancel path
and the kickoff deadline are all correct and all measured. What changes is
prominence, not existence.

## What this does not establish

- **That Kalshi combinations will stay illiquid.** The product is new and moved
  to its own exchange shard six days ago. This is a census of one evening; if
  liquidity arrives, the buy path is already built and the card can be
  re-promoted by changing where it sits.
- **That a sportsbook offers a better price.** It offers *a* price. Whether it
  beats the consensus is what the card's number lets Joe check, one bet at a
  time, and this project has measured nothing about sportsbook parlay pricing.
- **That parlays are worth betting at all.** ADR 0038 closed the hunt; the desk
  informs bets Joe makes anyway (ADR 0071) and does not manufacture them.
