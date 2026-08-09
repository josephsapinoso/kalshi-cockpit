# 0017 — The maker path: measure it once, for free, as a kill test

Date: 2026-08-09
Status: proposed
Lane: `lane/maker-headroom` (draft — not merged, not pushed)

## Context

`backend/core/ev.py:146-168` documents four break-even win rates. Against a
-110 sportsbook's 0.5238, the taker path leaves 0.38 points of headroom and the
maker path leaves between 1.38 and 1.94. The `maker` flag that selects between
them is plumbed through `core/fees.py`, `core/ev.py`, `core/sizing.py` and
`engine.py` and **defaults to `False` in every one of them**, with no caller
anywhere that sets it otherwise. The live strategy hunts 0.38 points and has
surfaced 0 actionable rows in ~200 fresh-odds decisions
(`tasks/NEXT.md`: `actionable=0 of 300 needed, no_edge=161`).

This ADR answers whether that is worth pursuing, and if so what the cheapest
honest test is. It recommends a measurement, not a build.

---

## 1. The arithmetic is confirmed, with two corrections

Computed by calling `backend.core.ev.breakeven_win_rate` directly, not by
reading constants. Every number in the `ev.py:150-154` docstring reproduces
exactly:

| | break-even | headroom vs 0.5238 |
|---|---|---|
| taker, any size, 50c | 0.520000 | +0.38 pts |
| maker, 1, 50c | 0.510000 | +1.38 pts (3.62x) |
| maker, 10, 50c | 0.505000 | +1.88 pts (4.94x) |
| maker, 100, 50c | 0.504400 | +1.94 pts (5.10x) |

**Correction 1 — one contract is not the relevant size; the engine refuses it.**
`config.RiskConfig.min_order_contracts` defaults to 10 and `MIN_ORDER_CONTRACTS=10`
is deployed, so `core.sizing.size_position` returns
`binding_constraint="below_min_order_contracts"` for anything smaller. The
smallest order this software can send is 10 contracts, so **1.88 points is the
figure, not 1.38**. (At a $100 bankroll it sends nothing at all — see §7.)

**Correction 2 — the "3.6x" and "4.9x" ratios are an artifact of a small
denominator and do not survive off 50c.** The fee is price-dependent, and at one
contract the maker rate is worth *exactly one cent per contract, or exactly
nothing*:

    n=1: maker saving is 1.00c/contract for prices 18c-82c, and
         0.00c/contract everywhere outside that band.

Both ends are pinned by rounding, not by the coefficient: `_model_a` rounds up
per *order*, so a sub-cent maker fee and a sub-cent taker fee both become one
cent. Recomputed across the wings, in cents per contract:

| price | taker fee (n=1 / 10 / 100) | maker fee (n=1 / 10 / 100) | maker saving @ n=10 |
|---|---|---|---|
| 10c | 1.00 / 1.00 / 1.00 | 1.00 / 0.20 / 0.16 | 0.80c |
| 30c | 2.00 / 1.50 / 1.47 | 1.00 / 0.40 / 0.37 | 1.10c |
| 50c | 2.00 / 2.00 / 2.00 | 1.00 / 0.50 / 0.44 | 1.50c |
| 80c | 2.00 / 1.20 / 1.12 | 1.00 / 0.30 / 0.28 | 0.90c |
| 90c | 1.00 / 1.00 / 1.00 | 1.00 / 0.20 / 0.16 | 0.80c |

Two things fall out that were not previously written down:

- **The taker fee at 50c is size-independent** (Model B's per-contract
  round-to-nearest pins it at 2.00c at every size), while **the maker fee is
  strongly size-dependent** (Model A's per-order round-up dominates: 1.00c at
  n=1, 0.44c at n=100). So `min_order_contracts`, which exists to control
  per-order rounding, is inert for the taker path at the band the strategy
  trades and load-bearing for the maker path. The lane replacing that constant
  (`start.md`, item 2) should know this: its measured "0.00c penalty at 50c" is
  a taker fact and inverts for maker.
- **The headroom clears its own noise floor, which is new.** `tasks/lessons.md`
  (2026-08-06) measured the devig-method spread at **0.18 points on an even
  moneyline** and 2.03 on a lopsided one. The taker's 0.38 points is barely
  double the former; the maker's 1.88 is ten times it. On the near-even markets
  that make up most of a slate, this is the first number in the repo where the
  edge being hunted is comfortably larger than the method noise underneath it.

A caution on the wing columns: comparing off-50c prices to a fixed 0.5238
is meaningless, so the table above reports *fees*, which are exact. Any
"headroom" at 30c or 80c requires assuming how a book prices vig at that
probability. Under multiplicative vig at a 4.76% overround the taker headroom
is **negative below ~42c** — the tool's own premise does not hold on longshots —
but real books charge more than proportional vig on longshots, so that
comparison flatters nobody and is not relied on here.

---

## 2. No live path ever passes `maker=True`

Traced outward from both entry points. `grep -rn "maker=True"` across the repo
returns **exactly one hit, in a test**: `tests/test_ev_sizing.py:130`.

    scripts/run_loop.py
      -> backend/runner.py:654         build_recommendation(...)   [no maker arg]
      -> backend/engine.py:90          maker: bool = False         [default]
           -> core/sizing.py:78        size_position(maker=maker)
           -> core/ev.py:171           edge_after_fees_tenths(maker=maker)
           -> core/ev.py:57            evaluate(maker=maker)
           -> core/sizing.py:201       verify_positive_after_fees(maker=maker)

    backend/api/routes.py:1072/1164/1187   size_position / edge_after_fees_tenths
                                           / verify_positive_after_fees  [no maker arg]
    backend/live.py:221/235                size_position / edge_after_fees_tenths
                                           [no maker arg]
    backend/seed_demo.py:267               build_recommendation(...)   [no maker arg]

Every parameter is threaded correctly and every call site takes the default.
This is `tasks/lessons.md`, *"Code with no caller is not a feature, it is a
plan"* — the fifth instance in this repo.

**The `maker` in `backend/kalshi/orders.py:130` is a different thing and must
not be conflated.** That is `self_trade_prevention_type`, a V2 order field whose
legal values are `taker_at_cross` and `maker`; it decides which of *your own*
two orders is cancelled when they would cross each other. It has nothing to do
with a fee tier. The fee-tier `maker` is the boolean in `core/fees.py:130`.
`orders.py` never computes a maker fee: `worst_case_cost_dollars`
(`orders.py:298-301`) calls `calculate_fee` with the default, i.e. taker, for
every order including a resting one.

---

## 3. What must be true for a resting order to earn the maker rate

The repo does not settle this. `.claude/skills/kalshi-api/SKILL.md:261-278`
defers to `core/fees.py`, which documents the *taker* coefficient dispute and
introduces `MAKER_COEFFICIENT = TAKER_COEFFICIENT / 4` with no provenance
attached. `tests/test_fees.py:122` asserts the ratio without citing a source
for it.

Kalshi's own fee schedule PDF still returns **HTTP 429** to automated fetches
(re-confirmed 2026-08-09), as `core/fees.py:15-17` records. Two secondary
sources, checked:

- Maker fees exist and are charged on **orders that rest on the book and are
  later executed**; there is **no fee for cancelling** a resting order. The
  formula reported is `roundup(0.0175 x C x P x (1-P))` — the same coefficient
  and the same per-order round-up as `_model_a`, so the repo's maker model is
  corroborated rather than invented.
- "Maker fees are exactly 25% of the taker fee", and the trigger is adding
  liquidity: "you place a limit order at a price where no one is currently
  willing to trade, and it sits in the book waiting to be filled."
- **No minimum order size** for the maker rate is documented by either source.
- One source reports that traders who overpay through per-order rounding are
  reimbursed in the first week of the following month, **only if the excess
  exceeds $10**. At 10 contracts near 50c the rounding excess is ~0.06c per
  order; reaching $10 would take ~16,000 orders a month. Treat the rounding as
  permanent at this scale — which is why the conservative figure in §1 is the
  one to plan against.

So: **yes, a limit order that rests and later fills gets the maker rate, and
there is no documented size or tier condition.** Both citations are secondary,
both agree with each other and with the code, and neither is the primary
document. Per `tasks/lessons.md` (*"When a document and the live API disagree,
the API wins"*), the definitive reading is the `average_fee_paid` field on the
V2 order response (`orders.py:380-381`) — which requires a real fill and is
therefore §5's residual.

Sources:
[pm.wiki — Kalshi Fees 2026](https://pm.wiki/learn/kalshi-fees-explained),
[Prediction Hunt — Kalshi Fees 2026](https://www.predictionhunt.com/blog/kalshi-fees-complete-guide-2026),
[Kalshi fee schedule PDF (429, unreadable)](https://kalshi.com/docs/kalshi-fee-schedule.pdf).

---

## 4. The counterargument, stated as strongly as it can be

**The quoted maker edge is not the realized maker edge.** A resting bid is not
filled at random. It is filled when someone chooses to sell to you, and on a
venue with ~13 sub-200ms automated market makers (`backend/agents/base.py:96`)
the participant crossing the spread is more often the one who knows something
than the one who does not. The quoted 1.88 points is the fee arithmetic; the
realized number is that minus whatever the average filling counterparty knew.

**How large would adverse selection have to be to erase it?** At 50c, 10
contracts, in cents per contract of realized markout:

| threshold | adverse selection required |
|---|---|
| maker no better than the taker path we already decline to act on | **1.50c** |
| maker outright unprofitable against a -110 book | **1.88c** |
| maker headroom falls back inside the lopsided-line devig spread (2.03 pts) | **0c — it never clears it** |

**1.50 cents is one and a half ticks.** On a venue whose prices are accurate to
~2c, that is smaller than the venue's own quoting error. It requires the
average filling counterparty to be right by less than one tick. There is no
prior under which that is implausible.

**And the two failure modes are in direct tension, which is the real bind.**
`docs/adr/0006-in-play-evidence.md` measured that Kalshi's mid moves >=1c on
~half of in-play minutes against **~0.5% of pre-game minutes**. This tool is
pre-game. So:

- Pre-game the book is nearly still, which makes per-fill adverse selection
  small — *and makes fill probability small for exactly the same reason.* If
  the price does not move, nobody comes down to hit your bid.
- When a pre-game book *does* move, it moves for a reason: a lineup scratch, a
  sharp book move, weather. Those minutes are ~0.5% of the sample and they are
  where essentially all of your fills come from. **The fill distribution is
  concentrated on precisely the minutes with news in them.**

An unfilled order earns nothing, so throughput collapses twice over: the tool
is actionable for roughly 30 seconds after each pass and about 30 minutes a day
(`tasks/lessons.md`, two-limits-on-one-quantity), and a resting order that has
not filled inside that window is backed by a thesis that has expired.

**The decisive infrastructure fact.** `tasks/NEXT.md` and
`docs/adr/0006-in-play-scope.md:180` both record it and it is still true:
**there is no cancel path anywhere in this repo.** `orders.py:128` sends
`good_till_canceled` and nothing ever cancels. So a maker order here is not a
quote — it is a *permanent standing offer*, priced off a sportsbook consensus
that goes stale in 15 minutes, left on the book for hours in front of thirteen
sub-second bots. The predecessor project measured that stale-quote picking-off
lives at ~400ms and abandoned it as too fast to *execute* (`CLAUDE.md`, "Do not
rebuild these"). An uncancellable GTC bid puts this project on the losing side
of that exact trade, with the latency asymmetry running the wrong way.

That is the honest counterargument, and I think it is more likely than not to
be right.

---

## 5. The cheapest honest test, and its pre-registered kill criterion

### It can be done for free, on data that already exists

Kalshi's candlestick endpoint is free, unmetered, answers **200
unauthenticated** (verified by `scripts/measure_candlestick_retention.py`), and
retains **~80 days** — measured, `tasks/NEXT.md:446`, roughly 1,200 MLB games.
A real capture (`tests/fixtures/candlesticks_mlb.json`, `period_interval=1`)
confirms each 1-minute bar carries everything a passive-fill simulation needs:

    yes_bid: {open,high,low,close}_dollars      <- where your order would rest
    yes_ask: {open,high,low,close}_dollars      <- the spread you would capture
    price:   {open,high,low,close,mean}_dollars <- what actually traded
    volume_fp, open_interest_fp

Plus the settled `result` on each market, which the repo already stores
(`schema.sql:105`). **Nothing has to be recorded going forward. No Odds API
credit is spent. No order is placed.** The parser exists
(`analysis/clv.py:109`, `parse_candlestick`) and needs one extension to read the
`price` block and `volume_fp`.

### The measurement

Simulate a resting YES bid at the best bid, on every in-scope pre-game market
minute in the retained window. Mark it filled during bar *t* if a trade printed
**strictly below** the bid — strictly, because a print *at* your price may have
been someone ahead of you in a queue you cannot see. Then measure, per filled
contract:

    markout = settlement_value - fill_price - maker_fee(fill_price, n=10)

Primary statistic: **mean settlement markout in cents per contract, clustered
by game**, using the sandwich estimator already in the repo — a game's
moneyline, spread and total resolve from one final score
(`tasks/lessons.md`, one-observation-recorded-thirty-times). Report `n` games
before the effect size. Secondary and non-decisive: 5-minute and 30-minute mid
markouts, and the per-league and per-price-band breakdown with the largest
contributor's share, per the measurement rules.

Restrict strictly to **pre-game** bars. A bar after first pitch has the outcome
leaking into it, which is the `last_price` contamination in a different shape.

Effort: roughly one day. It is one harness, one existing endpoint, one existing
parser.

### Pre-registered kill criterion — written before anyone runs it

Let `A` = mean settlement markout net of the maker fee, in cents per contract,
with a 95% game-clustered interval, and `G` = the number of distinct games
contributing at least one simulated fill.

**The maker path is dead, and this ADR is closed as rejected, if any one of:**

1. **`G < 300` over the full ~80-day window.** Throughput. The gate needs 300
   clustered games; if passive bidding cannot reach that in eighty days across
   every in-scope league, the maker path reaches the evidence bar *slower* than
   the taker path, which has already produced zero.
2. **The upper bound of the 95% interval on `A` is below +0.38c.** Resting is
   then not measurably better than the taker path the tool already declines to
   act on, and the flag is worth nothing.
3. **`A` is negative with `G >= 300`.** Passive quoting loses money before any
   directional signal is applied.

**Only** a lower bound on `A` above **+1.50c** — the whole fee saving, surviving
adverse selection — counts as "not killed". Anything between is a null result
and closes this ADR by default, because the burden is on the new idea.

### What the free test cannot do, stated plainly

**It can kill the idea. It cannot bless it.** Three reasons, all in the same
direction:

- A 60-second bar is 150 times longer than the ~400ms timescale at which the
  predecessor measured picking-off to live. Everything that happens inside a bar
  is invisible.
- The simulation cannot see queue position, so it will credit fills that a real
  order would have missed.
- Adding your own size to the bid changes what other participants do; the
  historical book is not the book that would have existed.

All three make the simulation **understate** adverse selection. So a negative
result is conclusive — it kills the idea on generous assumptions. A positive
result is not sufficient evidence to trade; it only means the idea survived the
cheap filter.

### If it survives, the next step is Joe's, not ours

Confirming a maker edge honestly requires real resting orders, because only a
real fill reports `average_fee_paid` and only real fills are drawn from the true
fill distribution. That is a money decision and a strategy experiment, not a fee
calibration, so it is **not** covered by the existing standing authorisation.
It should not even be offered until `docs/adr/0006-in-play-scope.md`'s item 3 —
a cancel path — exists, because §4's standing-offer problem is not a risk to be
priced, it is a defect.

---

## 6. Decision

**Run the free candlestick markout harness once, pre-registered as a kill test.
Build nothing else.** Specifically:

- Do **not** set `maker=True` anywhere in the engine, and do not add a config
  flag for it. Passing `maker=True` today would be *incoherent*, not merely
  premature: `engine.py` prices every candidate at the **derived ask**
  (`kalshi/quotes.py:148`), which is a marketable price. A maker fee applied to
  a taker price models an order that crosses the book and is charged as though
  it rested — the most flattering combination available, and wrong in the one
  direction this repo has a rule against.
- Do not build a maker execution path, a quoting loop, or a cancel path on the
  strength of this ADR.
- Record in `tasks/NEXT.md` that the maker flag is unreached by design, with a
  pointer here, so a future session does not rediscover 1.88 points and wire it
  up.

**Why measure rather than drop.** 1.88 points is the only number in this repo
where the headroom exceeds its own method-noise floor by an order of magnitude
(0.18 points on an even line), the test costs zero dollars and zero credits and
uses an endpoint and a parser that already exist, and eighty days of history
means the answer arrives in a day rather than a season. Against that, dropping
it leaves an untested 5x sitting behind a default nobody has questioned in
eleven build steps — which is the failure mode in
`tasks/lessons.md`, *"A true measurement licensed a false conclusion"*.

**Why the prior is that it dies.** 1.50c of adverse selection erases the whole
advantage; that is less than one tick on a venue quoted to ~2c by thirteen
sub-200ms participants, and pre-game the fills concentrate on the ~0.5% of
minutes that contain news. State that expectation now, so a negative result is
recorded as a confirmation rather than written up as a surprise.

---

## 7. What this ADR does not establish

- **It does not establish that a maker edge exists.** It establishes that the
  arithmetic in `ev.py` is correct, that nothing calls it, and that the cheapest
  test is free. No edge has been measured here, and none is claimed.
- **It does not establish that a maker edge does not exist.** Everything in §4
  is a prior and an infrastructure fact. Nothing in it is a measurement of
  realized adverse selection on Kalshi.
- **It does not settle the fee model.** `calculate_fee` still returns the
  conservative maximum of two disagreeing candidates, and the maker coefficient
  now has two agreeing secondary citations rather than none — which is not the
  same as a reading off a real fill. Every number here inherits that hedge.
- **The maker fee is corroborated, not verified.** Kalshi's own PDF was
  unreadable (429). Both citations are secondary, and this repo has been wrong
  before by trusting a document over the API.
- **It says nothing about the size the tool can actually send.** At a $100
  bankroll `size_position` refuses *every* order regardless of maker or taker,
  because quarter-Kelly never reaches `min_order_contracts=10` and the edge that
  would reach it (~10c) is above `edge_ceiling_tenths=40`, which suppresses it
  as a suspected bug. That is `start.md`'s finding, owned by another lane, and
  it is upstream of everything here: **the maker question is moot until it is
  fixed.** This ADR assumes the reference-bankroll fix lands.
- **It measures nothing about combos, in-play, or two-sided quoting.** The
  strategy contemplated is directional entry via a resting order — the same
  thesis the tool already has, executed passively. Two-sided market making is a
  different business, against a different set of counterparties, and is not
  under consideration.
- **The `A >= 1.50c` bar is a threshold for continuing to look, not a decision
  to trade.** Per §5, no free simulation can license a live resting order.

---

## Addendum A — 2026-08-09: `min_order_contracts` was deleted, and the stored `edge_tenths` is an n=1 number

**Nothing above this line has been edited.** The numbers in §1 and §7 are left
exactly as they were written, including the ones this addendum contradicts. The
record is the product: an ADR whose figures are quietly corrected cannot be
audited, and a future session needs to see what was believed as much as what is
true.

### A.1 What was believed

§1, Correction 1, rests on a premise stated as a fact about the deployed system:

> `config.RiskConfig.min_order_contracts` defaults to 10 and `MIN_ORDER_CONTRACTS=10`
> is deployed, so `core.sizing.size_position` returns
> `binding_constraint="below_min_order_contracts"` for anything smaller. The
> smallest order this software can send is 10 contracts, so **1.88 points is the
> figure, not 1.38**.

That was true when it was written. §7 depends on the same premise ("quarter-Kelly
never reaches `min_order_contracts=10`").

### A.2 What changed

The setting was removed the same day, in the lane `start.md` called item 2. There
is no minimum order size anywhere in the sizer now, and **nothing replaced it**.

The argument for removing it is in `core/sizing.py`'s module docstring and is not
re-litigated here: `effective_price` already charges the fee a *single* contract
would pay, which is provably the most expensive per-contract fee any order size
pays (`ceil_cent(a·N) <= ceil_cent(a)·N`, and Model B does not depend on `N`), so
a positive Kelly fraction already implies the order is +EV at whatever size comes
out. The minimum was not preventing negative-EV orders; it was refusing
positive-EV ones, and below roughly a $250 bankroll it closed the 50c band this
strategy trades while leaving the wings open.

`MIN_ORDER_CONTRACTS` is now in `config.RETIRED_SETTINGS`. **It logs an ERROR on
every config load and surfaces on `/api/health`; it does not raise.** Note that
`fly.live.toml` (the `BANKROLL_DOLLARS` block) still says it "**raises** if it is
set" — that comment is stale as of the commit *"a retired setting is announced,
never fatal at boot"*, and this addendum does not edit deploy files. The reason
it is announced rather than fatal is a composition, not a preference: a raise in
`RiskConfig.load` is a boot crash loop behind `wait -n`, landing after the
migration has already moved the volume forward, recoverable only by
`flyctl secrets unset` — and flyctl is a laptop job on a tool operated from a
phone.

### A.3 The consequence for the histogram this ADR gates

§1's whole table is indexed on order size, and the size the deployed system
produces is no longer 10. So:

**`edge_tenths` in `recommendations` is computed at
`sizing_contracts = max(1, sizing.contracts)` (`engine.py:160`).** At the live
profile — `BANKROLL_DOLLARS=100`, `KELLY_FRACTION=0.25`, caps 10/40/10
(`fly.live.toml`) — that is **1** for every candidate at the edge scale this
venue plausibly offers. Swept across 18c–82c in half-cent steps, restricting to
candidates whose post-fee edge is at most 1.0c: **1,206 of 1,206 grid points size
to n=1**, with `binding_constraint="kelly"` throughout — the re-scaled caps never
bind. Separately, every row the sizer zeroes is floored to n=1 by the `max(1, …)`
above, and the live record is ~0 actionable rows in ~200 fresh-odds decisions, so
the zeroed rows are most of the record.

**At n=1 the maker/taker gap is a step function, not a coefficient.** Computed
directly from `calculate_fee` over the whole tradeable grid, the n=1 maker saving
takes exactly two values: **1.00c per contract on the contiguous band 17.3c–82.7c,
and 0.00c everywhere outside it.** (§1 rounded that band to "18c-82c"; the exact
edges are 17.3c and 82.7c.) Both ends are pinned by Model A's per-order round-up,
not by the coefficient. At n=10 the saving is a smooth 0.80c–1.50c curve.

**Therefore: a histogram plotted off the stored `edge_tenths` column answers a
question about n=1 contract, not about this ADR's n=10.** It cannot show the
0.80c–1.50c maker curve, because the underlying rows do not contain it. It will
show a two-valued step, and a two-valued step plotted as a distribution reads as
a finding about the market when it is an artifact of per-order rounding at a size
nobody chose.

### A.4 Instruction to whoever runs the histogram

You have exactly two honest options. Take one of them explicitly.

1. **Recompute at n=10 offline.** The stored `(entry_ask_tenths,
   fair_probability)` pair is sufficient: call
   `core.ev.edge_after_fees_tenths(ask_tenths=…, contracts=10,
   fair_probability=…, maker=…)` per row. Do not derive it by adding
   `fee_predicted` back to `edge_tenths` — `fee_predicted` is a whole-order
   figure at the *stored* size, so that reconstructs the n=1 number.
2. **Plot the stored column and label the axis n=1.** Say so in the chart title
   and in whatever text accompanies it, and state that it does not test §1's
   1.88-point figure, which is an n=10 number.

What is not available is plotting the stored column and discussing it as though
it bore on §1. That is the failure `tasks/lessons.md` records as *"a true
measurement licensed a false conclusion"*: the column is a correct measurement of
something, and the something is not what the ADR is about.

### A.5 What this addendum does not establish

- **It does not revise §1's fee table.** Those figures were computed from
  `calculate_fee` and reproduce; what changed is which row of the table describes
  the deployed system. §1 says the answer at n=10; the system now produces n=1.
- **It does not claim n=1 universally.** The claim is bounded three ways: at the
  *live* profile, inside *18c–82c*, at a post-fee edge of *at most 1.0c*. It
  fails outside all three. Within 18c–82c, `sizing.contracts` first reaches 2 at
  a post-fee edge of 1.6c–2.3c depending on price — four to six times the venue's
  entire 0.38-point taker headroom, and inside the 4c band
  `suppression.edge_ceiling_tenths` treats as a suspected data defect. On the
  wings the bound is weaker: at a post-fee edge of at most 1.0c, n=1 holds on 88%
  of the 1c–17c grid and 79% of the 83c–99c grid, reaching 5 contracts at the top
  end. An earlier draft of this addendum asserted n=1 for "essentially every row"
  without the price bound; that is false on the wings and is corrected here.
- **The sweep is a grid, not the record.** No live database was available in this
  worktree, so the distribution above weights every `(ask, edge)` pair equally
  rather than by how often it occurs. It bounds what the sizer *can* return; it
  is not a measurement of what it *did* return.
- **It says nothing about whether the maker path is worth pursuing.** §4, §5 and
  §6 stand unchanged, including the pre-registered kill criterion and the stated
  prior that the idea dies.
- **§7's last bullet is now half-stale in the other direction.** It says "at a
  $100 bankroll `size_position` refuses *every* order" and that the maker
  question is moot until that is fixed. The refusal is gone — the sizer returns 1
  or more contracts across the band — so the blocker that bullet names has been
  removed. Whether the *rest* of that bullet's argument survives is not settled
  here.
