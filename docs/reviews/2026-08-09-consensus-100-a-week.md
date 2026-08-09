# UI direction under a $100/week beginner — the two reviews, and where they agree

Joe asked that the `partner` and `sharp-bettor` agents each evaluate the UI given
two new constraints — **a $100 weekly betting budget** and **a beginner user who
asked for tooltips** — and that their **consensus** guide the direction.

They reviewed independently and did not see each other's output. What follows is
what they agreed on, what they disagreed on, and which claims were re-verified
against the source before being written down.

---

## The finding both reached independently, and it outranks every UI item

**At a $100 bankroll this tool cannot express a bet, and it would not say so.**

Verified here by running `size_position` directly:

    bankroll  min_order  contracts  refused  constraint
      1000       10         15       False    kelly
       700       10         10       False    kelly
       400       10          0       True     below_min_order_contracts
       100       10          0       True     below_min_order_contracts
       100        1          1       False    kelly

Quarter-Kelly on the edges this tool actually finds is ~0.79% of bankroll. At
$100 that is 79 cents — one contract — and `MIN_ORDER_CONTRACTS=10` refuses it.

**And it disables the evidence record.** `gate.py:285` defines the gate's
counter as `suppressed_reason IS NULL AND suggested_contracts > 0`. At $100
`suggested_contracts` is always 0, so `actionable` is structurally zero forever:
the 300-game counter can never increment and the Gate screen keeps saying
"0 of 300, keep recording" without naming the cause.

**Two limits on one quantity, again.** At $100 the minimum net edge needed to
reach ten contracts is ~10c in the 50c band, while `edge_ceiling_tenths = 40`
suppresses anything above 4c as a suspected bug. **The ranges do not intersect.**
Break-even is ~$250 at the wings, ~$300 before the 50c band works at all.

Both agents flagged it as the single most important thing in their review.

---

## Consensus — both reviews, independently

1. **Do not lower `MIN_ORDER_CONTRACTS`; replace it.** Measured, the per-order
   fee-rounding penalty it exists to prevent is **0.00c at 50c** — the band the
   strategy trades — and ~0.8c at the wings. A price-independent constant is
   standing in for a price-dependent quantity. `verify_positive_after_fees` in
   `sizing.py` already re-evaluates the order at the real size with the real
   fee; let that be the guard.
2. **The risk caps are inert and that is worse than having none.**
   `max_position_dollars=$100` is 100% of bankroll, `max_exposure_dollars=$400`
   is 400%, `max_daily_loss_dollars=$100` fires only after the whole week is
   gone. They reassure without binding. Express as fractions of bankroll.
3. **The fee-calibration trades are the highest-return action available.** The
   two fee models disagree by 0.25c at 50c and up to 1.00c elsewhere, against
   0.38 points of total headroom — **we are hunting an edge smaller than our own
   uncertainty about what the venue charges.** Four fills retire it permanently.
4. **`CONSENSUS FAIR 53.8c` must become `53.8%`.** Both put this near first. It
   is a probability wearing a price's suffix, sitting immediately left of the
   real price at the same size — the one place a left-to-right scan reads the
   wrong number as what you pay.
5. **Show the whole slate, one line per row, rejected visible by default.** This
   is Joe's own instruction ("mispricing should be a factor, not a filter") and
   both reviews reached it independently. **It relaxes nothing**: suppression and
   staleness keep governing what is *bettable* and what the order endpoint
   accepts; they stop governing what is *visible*.
6. **Render `clv_tenths` on the Ledger.** Serialized at `routes.py:1672`,
   rendered nowhere. CLV is the only estimator that works at this volume, and
   the scoreboard does not show the score.
7. **Distance-to-the-bar as one number.** *"Closest today: −0.4c, Chicago."* On
   a board that is empty by design, this is the entire content — and 0.4c away
   versus 6c away is the difference between "keep watching" and "this venue is
   not it".
8. **A suppression strip.** `/api/suppression` is served at `routes.py:618` and
   consumed by nothing. With 0 actionable across ~200 decisions, "which check is
   killing everything" is the most valuable diagnostic in the system.
9. **The power-ratings model has never run.** `model_probability` is never
   assigned in the live path; `elo.py`'s only importers are the backtest and its
   tests. It is the fifth built-but-never-called in this repo, and the only
   asset on hand that could change the 0-of-200 result.
10. **Tooltips are the wrong primitive.** Both rejected a tooltip *system*. The
    concepts that trip a beginner here are not vocabulary, they are decision
    rules that run against instinct — and on a phone there is no hover, so a
    tooltip becomes a tap target competing with the row's own tap target, which
    opens an order screen. What is wanted instead is a handful of permanent
    sentences: what the 52% break-even bar is and why it is not 50%; which
    number is the price; why the biggest edge on the board is held back; and
    what CLV is, once, on the Ledger.

---

## Disagreements, and how they were settled

**Alerting.** The sharp-bettor ranked "a push when `surfaced > 0`" as worth more
than every layout change combined. The partner said it is already built. **The
partner is right, verified**: `backend/notify/alerts.py` is imported and called
by `scripts/run_loop.py`, with window-open, surfaced-row, digest and failure
alerts and per-kind dedup — and today's live log carries
`alerts_sent: ['window_open']`. Joe receives them in Discord. **Do not build
this.**

**Line movement.** The sharp-bettor called it the cheapest large-value item, on
the grounds that `fair_prices.computed_ms` already stores the history. The
partner objected that sweeps fire in one narrow pre-kickoff window at ~6
slots/day, so a game gets roughly 1–3 consensus observations and you cannot
chart two points. **Unresolved, and cheaply settled**: run one query against
`fair_prices` counting observations per game before writing any code.

**`min_order_contracts`.** Sharp-bettor: lower it to 3 (viable at ~$200).
Partner: delete it and let the fee-inclusive check that already exists be the
guard. **Partner's argument is stronger** and is what item 1 above records.

**The Builder screen.** Sharp-bettor: does not change a bet, and for a beginner
may change one in the wrong direction. Partner: remove it from the nav
entirely — which also frees the sixth nav slot that currently pushes the Gate
off-screen at 390px. Effectively agreement, in the direction of removal.

---

## What only one of them saw

**A price-honesty defect on the card** (sharp-bettor), verified at
`OpportunityCard.tsx:128`: `COST` is `ask_dollars × suggested_contracts` and
`FEE` is a separate figure, with **no total anywhere on the card**. The
understatement is 3.6% at 50c and 10% at 10c. The ticket sheet gets this right
and the card does not.

**Nothing on the card says what happens when he is wrong** (sharp-bettor). The
demo's best row is EV **+$0.26** with a standard deviation of **$7.48** — 29
times the mean. Ten such bets is a **46% chance of a losing week even if the
edge is completely real**. A professional supplies that from memory; a beginner
will not, and will either conclude the tool is broken or double up.

**The cheap-contract trap** (sharp-bettor). At 10c the fee is 10% of stake —
twenty-five times the entire venue advantage the product rests on. `fees.py`
says so in its own docstring and nothing in the UI steers away from it. A
beginner with $100 buys cheap contracts *because he gets more of them*.

**P&L cannot be the estimator at this volume** (partner). Mean/sd per bet is
~0.040 at a true 2-point edge and is scale-invariant, so two-sigma detection
needs ~2,500 settled bets — five to nineteen years at ten bets a week, and the
same span at $1,000 as at $100. CLV at 300 games is ~70× more sample-efficient.
**So the bankroll is irrelevant to the record, and the record is the product.**
$100/week is not a compromise; arguing him up to $1,000 would buy only variance.

---

## The honest summary

Neither review found a UI change that produces a bet this week. The gate is
locked, and independently the sizer refuses every row at $100 — both of which
are the tool working correctly.

What changed is what the tool is *for* in the meantime: it should inform and
record rather than recommend, and it should stop presenting an empty board as
though the absence of rows were the answer. The thing neither constraint
touches is that **the tool has found zero edges across ~200 decisions**, and
$100 versus $1,000 makes no difference to that at all.
