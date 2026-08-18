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
| Of 46,916 distinct markets polled, carrying an ask | 4,125 (8.8%) |
| ...carrying a **bid** as well | 60 (0.13%) |

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

    cross-game, TWO-SIDED, n=23    rho at mid  +0.003   sd 0.089
    cross-game, ask only,  n=308   rho at ask  +0.234   sd 0.254

(55 minutes of polling, 46,916 distinct markets. A shorter 26-minute run gave
mid −0.033 on n=12; the two agree.)

At the mid the method **returns the right answer** — mean +0.003 on a
population whose truth is zero.

**The ask-only population is refused for correlation.** Not because its bias is
large, but because it is not constant: sd 0.254 spanning −0.757 to +0.898. A
bias you cannot subtract is a refusal, not an offset, and a same-game number
drawn from it would be indistinguishable from the margin. It is still reported,
in its own block and labelled, because an upper bound is a fact — but no
same-game claim may rest on it.

A **leg** must be two-sided regardless. The leg supplies a marginal, and the
only unbiased single number for that is the mid; an ask alone overstates it and
pushes the inverted rho down by an amount nothing in the output would show.

## Decision 3 — the refusal rate is reported, because it is a finding

An ask above `min(marginal)` is outside the Frechet bounds: no dependence
structure of any kind produces it, so `implied_correlation` raises. Discarding
those quietly would throw away the clearest signal in the sample.

    cross-game   102/437   23%
    mixed          9/19    47%
    same-game     17/18    94%

The gradient runs cleanly through `mixed`, which is what you would expect if
same-game *pairs* drive it. The mechanism is direct: strong positive dependence
pushes the true joint toward `min(marginal)`, and near that ceiling any margin
puts the ask above it.

So same-game dependence is showing up in the **refusals** rather than in the
surviving numbers. Two things keep it suggestive rather than measured: a stale
leg quote produces the identical symptom, and same-game combinations are
somewhat more prop-heavy — though less than expected, their legs being mostly
TOTAL, SPREAD, GAME and F5, the same series the cross-game ones use.

The sharper version needs no correlation estimate at all: compare the
combination's ask against **the cheapest leg's own ask**. A combination costing
more than a leg that pays out in a superset of cases is dominated outright.
Leg bids and asks are now recorded in the `--json` output for exactly that.

## Decision 4 — equicorrelation is refused above three legs

`implied_correlation` fits **one** rho to every pair. On two legs that is the
pairwise correlation exactly. On the 42-leg combinations that appear in this
population it is an average over pairs that are nothing like each other, and
printing it in the same column as a two-leg number would put two different
quantities under one heading. Refused and counted, so the exclusion is visible
rather than silent.

## Decision 5 — this does not touch the money path

Nothing here feeds sizing, suppression or the gate. `DEFAULT_CORRELATION` still
has no `SAME_GAME` entry and `correlation_matrix` still refuses. Three things
would have to land before a measured rho could price anything:

1. **A same-game sample.** Eighteen same-game combinations appeared in 55
   minutes of polling. **Zero were two-sided** and seventeen of the eighteen
   were outside the Frechet bounds, so exactly one produced a number at all —
   from the ask-only population, which is refused. There is no measurement.
2. **A combo fee model.** ~~Unverified for this venue~~ **Measured and
   unmatched, 2026-08-18** (marked in place; the original word stands struck
   so the change is visible): the first 8 combo fills ever observed were
   scored against eleven registered candidates and none predicted every
   order — every charge lies strictly above 0.070·C·P·(1−P) (implied k
   0.070041–0.070548, excluding 0.035 on every row), rows 1/5/6/8 exceed
   even the deployed ceil-rounded model by ≤0.19% of the fee on charges
   finer than the $0.0001 grid, and the four exact "matches" are grid
   coincidences, not support for the coefficient. The per-leg-versus-per-order
   question `core/fees.py` hedges on is still open: the leg-price form is
   NOT TESTABLE (fill-time leg prices are unrecorded and unrecoverable).
   One account, one sitting, one day — durability unestablished. See
   `docs/measurements/2026-08-18-combo-fill-fee-look-result.md` and
   ADR 0046.
3. **Liquidity that means something.** These markets are `is_provisional` with
   zero volume and zero open interest. A two-sided quote on an untraded market
   is a quoter's opinion, not a transaction.

## Consequences

- `scripts/measure_combo_correlation.py` accumulates the measurement, free and
  read-only, and states in its module docstring what it does not establish.
- `docs/measurements/2026-08-09-combo-correlation-55min.json` is the run the
  numbers above come from — 55 rounds, 46,916 distinct markets, 484
  measurements with their legs, marginals and all three inverted rhos. The
  26-minute run beside it is kept as the independent replication. Both are kept
  because these markets are gone within minutes: the run can be repeated, never
  reproduced.
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

---

## Addendum, 2026-08-09 — the 94% is withdrawn, and not replaced

**"same-game 17 of 18, 94%" must be withdrawn as a rate.** It is one expected
outcome on the non-refusal side. CLAUDE.md requires ≥5 on each side before a
normal approximation may speak, and 17/18 is not close. It was quoted in this
ADR and was load-bearing in `tasks/NEXT.md`.

A fresh 55-minute capture on fixed code gives **77/344 = 22.4%** for the same
quantity. **That is not a correction of the 94%, because the two runs are not
the same population**: same-game rose from 3.7% to 16.3% of the measurable
sample, distinct-per-scanned went 53% → 100%, and the two-sided rate fell 5x.
Different sampling windows into a firehose.

**The staleness mechanism proposed for the 94% is falsified by the old data.**
All 17 refusals have a combo ask within 1.7c of one of their leg mids (median
1.0c). A leg quote read up to 39 minutes earlier cannot agree with the
combination's ask to a cent seventeen times out of seventeen.

**What is actually there is a leg echo.** In both captures the combination's
`yes_ask_dollars` is frequently equal to one of its own legs' prices:

    tolerance 2c        dominated rows      non-dominated rows
    cross_game            152/179  85%          46/1433  3.2%
    same_game              54/63   86%          21/281   7.5%

Still 77% / 68% at 0.5c. **119 echo rows match a leg that is not the cheapest**
— a joint above `min(marginal)` that no dependence structure produces. For that
subset, the quote at the combination's ticker is evidently not the joint over
`mve_selected_legs`.

Excluding echoes, the 2026-08-09 capture reads:

    domination      cross 179/1612 11.1% -> 27/1414 1.9%
                    same   63/344  18.3% ->  9/269  3.3%
    Frechet refusal cross 228/1612 14.1% -> 26/1405 1.9%
                    same   77/344  22.4% -> 11/268  4.1%

Clustering by **game** rather than by combination — 344 same-game rows come from
19 games and share legs — the intervals overlap: same-game 18.3% [13.4, 25.2],
cross-game 11.1% [8.6, 16.3]. Two games carry a third of the dominated
same-game rows.

**So the refusal gradient this ADR reported is not evidence of same-game
dependence.** It is largely one artefact, and the same-game excess is an excess
of the *pathology* (21.8% of rows vs 12.3% cross-game), not of dependence — the
tell being that the excess persists among rows matching a **dearer** leg
(1.61x), which dependence cannot explain at all.

**What still stands from the original ADR:** the method returns rho ≈ 0 on
two-sided cross-game combinations; the ask-only population is refused; and no
same-game correlation has been measured. **0 of 344** same-game joints were
two-sided in the new capture, so that last point is unchanged and stronger.

**Resolve the echo before re-running anything.** Re-read a handful of the
near-leg tickers live and record whether `yes_ask_dollars` moves tick-for-tick
with the matched leg. If it does, the MVE-as-correlation programme needs a
different data source. If not, the echo is a transient mint-time state and can
be excluded by a rule stated in advance. ~20 API calls, free.
