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
- ~~**It must not imply a fill is likely.** 61 of 61 empty is the evidence, and
  the words carry it.~~ **Struck by Amendment 1 (2026-09-06)** — the parlay
  census found 51 of 52 of Joe's combination positions were entered as taker
  fills, so "a fill is unlikely" is false at the moment he buys while the
  census stands for the book at rest. See §A1.4 for the three rules that
  replace it.

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

## Amendment 1 (2026-09-06) — refuted at the moment of entry, upheld for the book at rest, and the card says both

### A1.1 What the parlay census refuted, stated narrowly

The registered census (`docs/measurements/2026-09-05-parlay-census-registration.md`,
taken 2026-09-06, result in `2026-09-05-parlay-census-result.md`) tested this
ADR's copy against Joe's own combination fills:

```
Arm D   n = 52   k = 51 taker   p_taker = 0.9808
        exact Clopper-Pearson 95% interval [0.8974, 0.9995]
        registered refute bound k >= 34   VERDICT: REFUTED ON THIS POPULATION
```

**51 of 52 combination positions were entered by hitting an offer.** The one
maker fill in the population is the single tool-placed order (the resting bid
ADR 0084 describes). So *"neither buyable nor sellable at a resting price, most
of the time"* is false as a description of the moment Joe buys.

It is refuted **only** as that. The population is self-selected structurally —
a fill exists only where a fill was possible — so conditioning on entry having
succeeded and then measuring how often entry succeeded says nothing about
buyability at large. The 2026-08-30 census (0 of 61 open combinations with a
readable ask, 0 of the 6 deepest books with anything resting on either side)
stands as the description of the resting book.

### A1.2 Why both are true: two instruments

The 2026-08-30 census read the `/markets` **list summary**, which flattens an
empty side to a boundary value (`yes_ask_dollars = 0.0000`,
`no_bid_dollars = 1.0000`, derived ask `$0.00`). `lookup_combo` reads the
**orderbook** via `OrderBook.best_no_bid`. Both instruments were reading the
venue correctly; they answer different questions. Not a contradiction.

### A1.3 What is not touched

Every **exit** claim stands. No combination book this repo has ever read has
carried a resting YES bid, and the census measured entry, not exit. "The only
exit is the outcome or a hedge on a leg" (ADR 0012 §5, ADR 0078) is unchanged.
ADR 0084's buy path is unchanged. The ranking rule in *What the card must not
do* is unchanged.

### A1.4 The decision — Joe, 2026-09-06: both halves on the card

Asked in one line with four options (both halves / fill fact leads / ADR
amendment only / drop the note), he chose **both halves**.

The third bullet of *What the card must not do* — *"It must not imply a fill
is likely. 61 of 61 empty is the evidence, and the words carry it"* — is
**struck** and replaced by:

- **It must not imply a resting quote exists.** The book at rest is the
  2026-08-30 census and the words carry it.
- **It may state the measured entry rate, with its date and its population**
  ("this desk's own fills", never "your positions" — the same sentence is
  served on demo, which holds no fills). That is price transparency at the
  moment of a bet, ADR 0071 §2.2, and withholding it would be the original
  error in the other direction.
- **It must keep the exit warning.** Plan to hold to settlement or hedge a
  leg.
- **"You can buy in" stays forbidden wording.** `tests/test_parlays_api.py`
  pins it absent; the note reports a measured rate, it does not promise a fill.

`NOTES["unquoted"]` in `backend/parlays.py` is rebuilt from named constants
for both censuses — `COMBO_CENSUS_*` and `PARLAY_CENSUS_*` — so the day either
moves and the sentence does not, the test goes red. That reaches all three
surfaces at once: the parlay card footer, the "Price on Kalshi" lookup, and the
20:00Z Discord push, which render the server's sentence verbatim.
