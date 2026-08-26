# 0075 — The manual path is bounded by money, and the contract ceiling becomes structural

**Date:** 2026-08-26
**Status:** Accepted.
**Owner of the decision:** Joe. Told that the one-contract ceiling made a
combination buy worth about $0.015 against the 25c–$3 he actually bets, and
that raising it overrides a trigger he had previously set, he said: *"yeah do
the spend cap."*
**Overrides** ADR 0063 §3's raise condition and ADR 0073 §5's one-contract
combination cap. **Touches nothing decided by** ADR 0045 (caps derive from the
observed balance), ADR 0018 (arming is a code change), ADR 0046 (the combo fee
model is documented, not fitted), or ADR 0038 (the hunt is closed).

## 1. What was wrong with a contract ceiling

`MANUAL_ORDER_MAX_CONTRACTS = 1` and `COMBO_MAX_CONTRACTS = 1` bounded the
*count*, and the risk they exist to bound is denominated in *money*. The same
number is a bet of $0.90 on a 90c moneyline and a bet of **$0.015** on a
combination priced near a cent.

Asked directly what he stakes, the owner said: *"I bet .25 cents to 2 or 3
bucks on parlays right now."* So the ceiling did not make his bet small — it
made the door decorative. ADR 0073 §1 caught this path in exactly that state
once before: *"a feature and the one path that invokes it are two deliverables,
and only the second one ships."*

## 2. The decision

**`MANUAL_ORDER_MAX_SPEND_TENTHS = 3_000` ($3.00) is the binding ceiling**,
checked against the fee-inclusive worst case, in tenths of a cent like every
other money quantity in the risk path.

**The contract ceilings survive as structural bounds**, not as the bet size:

    MANUAL_ORDER_MAX_CONTRACTS = 500
    COMBO_MAX_CONTRACTS        = 250

A market priced at a tenth of a cent turns $3 into thirty thousand contracts,
and a count that large is a different kind of order — it moves a thin book on
its own — even when the money is small. Combinations are held tighter because
the deepest resting bid this repo has ever measured on one was **18 units**
(ADR 0012 §5), so a far larger count could not fill anyway.

**Two independent bounds, and the tighter wins.** The balance-derived per-bet
cap (ADR 0045: 10% of the observed Kalshi balance, never typed) is unchanged
and still applies. `_manual_cap_dollars` returns both the figure and **which
bound produced it**, because *"$3 cap"* and *"your balance only supports
$0.54"* are different problems with different remedies — and the second already
has an answer on the screen. A refusal that does not say which bound it hit
sends the reader to fix the wrong thing.

## 3. A spend cap bounds the fee-model error BETTER than the count cap did

This is the part that makes the change an improvement rather than a relaxation.

ADR 0073 §5 justified one contract on combinations this way: *"The ceiling is
what makes an error in that hedge cost a fraction of a cent instead of scaling
with size."* The hedge is `COMBO_TAKER_COEFFICIENT = 0.071`, fitted to eight
fills at prices no higher than $0.228, and known to be a ceiling above observed
charges rather than a measurement of Kalshi's schedule.

But the combo fee is `k · C · P · (1 − P)` — **proportional to spend, not to
count.** A one-contract cap bounded the error only through whatever the price
happened to be; at 90c it bounded it forty times more loosely than at 2c. A
spend cap bounds it directly and uniformly: at $3, a coefficient wrong by 1%
costs at most three cents.

## 4. ADR 0063's trigger is NOT discharged, and this is the override

ADR 0063 §3 said the ceiling rises *"only when observed `fee_actual` matches
`fee_predicted` on real fills."*

**No fill through this door has been checked.** The path was armed 2026-08-26
and `manual_orders` has not been read back since. This ADR does not claim the
trigger was met; it records that the owner chose to proceed without it, on the
grounds that the bound being raised is being *replaced by a tighter-reasoned
one* (§3) rather than simply loosened, and that $3 is his own stated stake.

**What would make this wrong**, stated now so it cannot be decided after the
fact: the first real fill whose `fee_actual` exceeds `fee_predicted` by more
than the hedge's margin. `scripts/analyse_hand_fill_fees.py` is the
instrument. **Re-read after the first five fills.**

## 5. What this does not do

- **It does not make a combination buyable.** A freshly minted combo's book is
  empty on both sides (`parlays.price_card_on_kalshi`'s own docstring), the
  order path is IOC, and an IOC into an empty book cancels. The depth check
  refuses before the spend cap is ever consulted. That remains the open
  question and it needs a registered measurement — does a maker ever quote a
  freshly minted combination, and how long does it take — before any decision
  about a resting order.
- **It does not raise the balance-derived cap.** At the observed $5.40
  balance, the binding ceiling is **$0.54**, not $3. The spend cap only binds
  once the balance supports more than $30.
- **It does not touch the engine path.** `ORDERS_ARE_DRY_RUNS` is still True
  and `gate.py` still never reads `manual_orders`.
- **It changes no other guard.** The ten-minute cool-off, the desk lockout,
  the daily-loss switch, the depth check, the netting refusal on an existing
  position and the reserve-then-check write all bind exactly as before.

## 6. Rejected, with reasons

- **Leaving the ceiling at one contract until a fill is observed.** That is
  the letter of ADR 0063 §3, and it is circular here: the door is how a fill
  would be produced, and at one contract of a one-cent combination it produces
  a fill worth measuring nothing.
- **Making the cap configurable.** A constant, for the reason the dry-run
  switch is one: raising it should be a decision with a commit behind it, not
  an environment variable somebody can nudge.
- **A single ceiling for combinations and single markets.** §2 — the
  measured depth on a combination book is 18 units; the two are not the same
  kind of order.
- **Widening the cap to match the balance.** The two bounds answer different
  questions: one is risk, one is the owner's own stated appetite. Collapsing
  them would mean a larger balance silently raises the bet size, which is
  precisely what ADR 0045 was written to prevent.
