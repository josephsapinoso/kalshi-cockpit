# 0012 — A combo price is read, not created; and only a two-sided one measures anything

Date: 2026-08-09
Status: accepted

## Context

`core/correlation.py` refuses to price same-game legs. `SAME_GAME` is
deliberately absent from `DEFAULT_CORRELATION` and raises `CorrelationRefused`,
because the sign depends on the specific pair and any default is a guess
wearing a number. The module's own docstring names the way out: a same-game
combo quote **is** a joint probability, so given the leg marginals it inverts
to a measured rho (`implied_correlation`).

Since ADR-less step 11e this repo has recorded that obtaining one requires
`POST /multivariate_event_collections/{ticker}/lookup`, which creates a market
on the exchange, and therefore requires Joe. He authorised exactly one such
lookup on 2026-08-07. It was never spent.

## Decision 1 — read the joint from `/markets`; do not create one

**The premise was wrong.** Kalshi's own users mint provisional combination
markets continuously by tapping legs in the app, and `GET /markets` returns
them carrying everything needed:

    mve_selected_legs       [{event_ticker, market_ticker, side}, ...]
    mve_collection_ticker   the collection they came from
    yes_bid_dollars / yes_ask_dollars

So the joint is readable, the legs are decodable, no market is written, and the
authorised lookup stays unspent.

**Why the wrong belief was cheap to hold.** It is nearly true. Measured
2026-08-09:

| | |
|---|---|
| Provisional combination markets minted | ~700 per minute |
| `created_time` span of 5,000 consecutive open markets | 6 min 48 s |
| Of 23,847 distinct markets polled, carrying an ask | 2,092 (8.8%) |
| ...carrying a **bid** as well | 42 (0.18%) |

The quote decays within a couple of minutes of creation. Page one of `/markets`
is newest-first, so **paging depth-first finds nothing and says so with
complete conviction** — page six is already two minutes stale. The sample has
to be accumulated over *time*, by re-reading the newest page, not over pages.

This is also the first *rate* attached to the "~99.8% `KXMVE` with no volume"
observation this project has carried since step 1. The proportion was always
true; what it describes is a firehose of user-built combinations, not a dead
product.

**`active_quoters` is not a liquidity signal.** It is empty for all 14,240
published collection legs, while those same leg markets are two-sided with real
open interest — `KXNFLGAME-26AUG13GBPIT-PIT` quoted 56/57c against 21,247 open
interest. The "0 of 13,806 legs quoted" reading on record said nothing about
whether a combination could be priced, and the field is read by nothing here.

## Decision 2 — the mid, on two-sided combinations only

Cross-game combinations are the control: different games are as close to
independent as this venue offers, so their true rho is 0 and whatever the
method returns there is its own bias. **The control was run, and it decides
which estimator is admissible.**

    cross-game, TWO-SIDED, n=12    rho at bid -0.135   mid -0.033   ask +0.137
    cross-game, ask only,  n=168   rho at ask +0.243   sd 0.235   max +0.853

At the mid the method **returns the right answer** — median −0.010 on a
population whose truth is zero — and the bid and ask bracket it almost
symmetrically at about ±0.14, which is the combination's own spread read as
dependence.

**The ask-only population is refused for correlation.** Not because its bias is
large, but because it is not constant: sd 0.235 across the control means it
cannot be subtracted off, and a same-game number drawn from it would be
indistinguishable from the margin. It is still reported, in its own block and
labelled, because an upper bound is a fact — but no same-game claim may rest on
it.

A **leg** must be two-sided regardless. The leg supplies a marginal, and the
only unbiased single number for that is the mid; an ask alone overstates it and
pushes the inverted rho down by an amount nothing in the output would show.

## Decision 3 — equicorrelation is refused above three legs

`implied_correlation` fits **one** rho to every pair. On two legs that is the
pairwise correlation exactly. On the 42-leg combinations that appear in this
population it is an average over pairs that are nothing like each other, and
printing it in the same column as a two-leg number would put two different
quantities under one heading. Refused and counted, so the exclusion is visible
rather than silent.

## Decision 4 — this does not touch the money path

Nothing here feeds sizing, suppression or the gate. `DEFAULT_CORRELATION` still
has no `SAME_GAME` entry and `correlation_matrix` still refuses. Three things
would have to land before a measured rho could price anything:

1. **A same-game sample.** Four same-game combinations appeared in 26 minutes
   of polling and exactly one inverted — from the ask-only population, so it is
   not a measurement. Zero were two-sided.
2. **A combo fee model.** Unverified for this venue, and the per-leg-versus-
   per-order question is exactly the one `core/fees.py` already hedges on.
3. **Liquidity that means something.** These markets are `is_provisional` with
   zero volume and zero open interest. A two-sided quote on an untraded market
   is a quoter's opinion, not a transaction.

## Consequences

- `scripts/measure_combo_correlation.py` accumulates the measurement, free and
  read-only, and states in its module docstring what it does not establish.
- `docs/measurements/2026-08-09-combo-correlation.json` is the run every number
  above comes from — 26 rounds, 23,847 distinct markets, 229 measurements with
  their legs, marginals and all three inverted rhos. Kept because these markets
  are gone within minutes and the run cannot be reproduced, only repeated.
- `tests/fixtures/combo_priced_markets.json` holds twelve quoted combinations
  and all 29 leg markets they reference, read at the same moment so joint and
  marginals are contemporaneous. It contains one genuine same-game combination
  (WNBA LV@NY — the winner, Stewart 15+ points, and NO on the −13 spread).
- The authorised lookup is **not spent** and is no longer on the critical path.
  It remains available for the one thing reading cannot do: pricing a
  combination nobody has built.

## What this ADR does not establish

That Kalshi's combo book is *right* about dependence. The control establishes
that the method recovers a known answer on a population where the answer is
known. Whether a same-game rho read this way predicts anything is a separate
question, and it needs the sample that does not yet exist.
