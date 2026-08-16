# 0033 — The limit price, and the maker question underneath it

**Date:** 2026-08-16
**Status:** **Proposed. No code.** This ADR specifies work; it does not
authorise it. Nothing in the repo changes on merging it.
**Owns:** the case for surfacing a *limit price* per row, and the maker-side
question that determines whether doing so is worth anything.
**Does not touch:** `core/fees.py`, `TAKER_COEFFICIENT`, any suppression
threshold, the order path, or `ORDERS_ARE_DRY_RUNS`.
**Related:** ADR 0027 (the headroom is an upper bound pending H4), ADR 0028 (the
fee hedge retired, grid is deci-cent), ADR 0015 (the reference bankroll), ADR
0031 and 0032 (this session's spend changes, which this does not depend on).

---

## 1. Where this came from

A `sharp-bettor` review, convened at Joe's request on 2026-08-16 to explain why
every row reads as rejected. Its answer was not about the screen:

> *"If the arithmetic says the venue does not clear the bar as a taker, the
> professional stops taking... your own CLAUDE.md puts the maker bar at 50.44%
> against 51.75% taker, and the entire product is built as a taker screen."*

and its one proposed change:

> *"Replace the edge column with a **limit price**: the price at which this row
> would clear the fee, with the distance from the current ask beside it, and
> sort by that distance. Today a rejected row is terminal. With a trigger price,
> every row becomes a resting order you could place and walk away from."*

## 2. The arithmetic, computed from this repo's own code

Not quoted from `CLAUDE.md`. Run against `core/ev.py` and `core/fees.py` on
2026-08-16, 1 contract:

| | fee at 50c | breakeven |
|---|---|---|
| taker | $0.0175 | **51.75%** |
| maker | $0.0044 | **50.44%** |

Both reproduce `CLAUDE.md` exactly, so the published figures are sound.

The consequence for a *row*, which is the part that has never been on a screen.
Taking a fair value of 0.52 and the 18-tenth devig-method noise bar that
`suppression.py:360` actually applies:

```
fair = 0.52   taker, must clear the noise bar  ->  limit 48.4c
fair = 0.52   maker, must clear the noise bar  ->  limit 49.7c
```

**1.3c of extra room**, and 1.3c against a 4c edge target is not a rounding
detail — it is a third of the prize. At `fair = 0.55` the same gap holds: 51.4c
taker against 52.7c maker.

## 3. What already exists, which is more than expected

The order machinery is already a maker machine and nobody noticed:

- **Every order this repo sends is already a limit order.** `store/orders.py:131`
  — *"V2 expresses a market order by omitting `price`. This repo never omits
  it."*
- **`time_in_force` already defaults to `good_till_canceled`**
  (`kalshi/orders.py:212`). A resting order needs no new field.
- **A bid already snaps DOWN the market's grid** (`kalshi/orders.py:253`) —
  *"always away from paying more"*, which is exactly what a resting bid wants.
- **`self_trade_prevention` already accepts `"maker"`** (`orders.py:238`).

So the pivot is not a new order type. It is entirely upstream: **nothing
computes a price below the ask, nothing displays one, and every production call
into `core/ev.py` passes `maker=False`.** The only `maker=True` in the repo is
`analysis/joint_bound.py`, which is operator-invoked analysis.

## 4. The objection that decides it, and it is not the arithmetic

**`MAKER_COEFFICIENT` has never been measured.** `core/fees.py:88` lists, among
the things the fee work explicitly does *not* establish, *"any rate ... on the
**maker** side"*. Zero maker fills exist on this account.

`MAKER_COEFFICIENT = 0.0175` is `TAKER_COEFFICIENT / 4`, and that ratio comes
from the same secondary sources that were **wrong about the taker side**. Those
sources said one coefficient for all categories; the account's own fills pin
baseball to `(0.034969, 0.035008]` and non-baseball to `(0.069961, 0.070000]`.
A venue whose taker rate is not a venue constant is not a venue whose maker
ratio should be assumed constant either.

So: **the entire 1.3c prize rests on an unverified quarter.** If the true maker
ratio is 1/2 rather than 1/4, the bar is 50.88% and the gap collapses to roughly
0.6c. If maker fees on sports are zero — which some venues do — the bar is 50.00%
and the gap widens. Nobody knows, and it is cheap to find out.

## 5. The second objection, which is the professional one

**Adverse selection.** A resting bid fills precisely when the market moves
through it, which is disproportionately when you are wrong. A taker pays a
spread and knows its cost; a maker collects a spread and pays in fill quality,
and that cost does not appear in any fee model.

This matters more here than at most venues, because the fair value being rested
against is a **devigged sportsbook consensus** — a lagging reference by
construction. A resting bid below a lagging fair value is a standing offer to be
picked off by anyone whose number updates faster, and `CLAUDE.md` already
records that this venue has thirteen sub-200ms market makers.

**So the maker bar being lower does not mean maker bets are better.** It means
the *fee* is lower. Whether the realised edge survives adverse selection is a
separate empirical question, and the CLV record is what would answer it: a maker
fill's CLV against Kalshi's own close measures exactly this.

## 6. What is proposed, cheapest-falsification-first

**Stage 0 — display only, no money, no credits.** Compute and show the limit
price per row, at both the taker and maker bar, with the distance from the
current ask. Purely derived from `fair_probability`, `ask_tenths` and the
existing fee model; no new data, no new call. This is the change that turns
"rejected" into "rests at 49.7c, 2.1c away".

**It must be labelled as a price, not an instruction.** Nothing on the Slate may
become a composite (four tests enforce it), and a limit price is one number
derived from one signal, so it is admissible — but a screen that sorted by it
and called the top row a pick would be a ranking, which is a weighting, which
needs its own registration.

**Stage 1 — measure the maker coefficient. One contract.** The decisive
experiment is a single resting order that fills, on a market where the fee is
readable from `/portfolio/fills`. That is one observation and it either confirms
the quarter or refutes it. **This is a money action and needs Joe's explicit
say-so at the time** — the standing fee-calibration authorisation was given for
taker calibration, and this is a different order type on a locked gate.

**Stage 2 — only if stage 1 confirms:** pre-register a maker CLV comparison.
Rested-and-filled rows versus taken rows, scored against Kalshi's close,
clustered on `event_links.odds_event_id`, with the adverse-selection direction
stated in advance. Without this, a lower fee bar is a claim about cost and
nothing else.

## 7. What this does not claim

- **Not that maker bets clear the bar.** Stage 0 changes what is displayed. It
  produces no bet, and `actionable` will still be 0 the day after it ships.
- **Not that 50.44% is the maker bar.** It is the bar *this code applies*, on an
  unmeasured coefficient. §4.
- **Not that resting orders are safe at this bankroll.** `ORDERS_ARE_DRY_RUNS`
  is a hardcoded `True` (`store/orders.py:129`) and the gate is locked at 300
  scored games. Arming is still two deliberate acts, and this ADR changes
  neither.
- **Not that the taker screen was wrong.** It was right for a taker, and the
  measurement that matters — does this tool beat Kalshi's close — is unaffected
  by which side of the book you would have used.

## 8. The honest summary

The tool was built to answer "can I take a price here at a profit", and its
answer has been no, consistently, for the life of the record. That answer is
probably correct. This ADR proposes asking a *different* question — "at what
price would this have been worth taking, and could I have rested there" — which
the existing data can answer for free, and which the existing order machinery
could act on without a new code path.

**It is worth doing because it is nearly free, not because it is likely to
work.** The maker coefficient is unmeasured, adverse selection is unmodelled,
and both cut against it. Stage 0 costs a display change and settles neither.
