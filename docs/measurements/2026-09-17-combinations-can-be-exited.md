# Combinations can be exited — "enter-only" is REFUTED

Date: 2026-09-17
Authorised by Joe the same day ("yes fire the sell side rfq", #59).
Successor to `2026-09-17-a-combo-rfq-returns-a-real-takeable-price.md`.

## The claim under test

CLAUDE.md carried **"combinations are enter-only"** — you can get into a KXMVE
combination and may not be able to get out. It is the stated reason the hedge
(ADR 0078) exists and the reason combination orders carry a tighter ceiling.
Its whole evidential basis was `yes_dollars` empty on 40 of 40 combination
order books. Earlier today that was downgraded to **unsupported** (ADR 0164):
the lit book cannot see the surface combinations trade on.

**It is now refuted.**

## Method

An RFQ carries **no side field**. You name a market and a size; makers answer
with *both* `yes_bid_dollars` (what they would pay you for YES) and
`no_bid_dollars` (whose complement is what you would pay to buy YES). So the
exit question is exactly: **does any maker return a non-zero
`yes_bid_dollars`?**

Fired on **all three combinations Joe actually holds**, at the size he holds,
sized in `contracts` rather than `target_cost_dollars` — the neutral form, so
the request cannot be read as "I want to spend". Every RFQ was withdrawn
immediately. **Nothing was accepted and no money moved.**

Holdings from `GET /portfolio/positions`, which returns fixed-point fields
(`position_fp`, `market_exposure_dollars`); the legacy integer columns come
back `null` and reading those alone says "no positions", which is wrong.

## Result — 16 of 44 quotes carried a YES bid, on 3 of 3 positions

| position (tail) | held | basis/contract | RFQ: makers bidding YES | best RFQ YES bid | book's best YES bid |
|---|---|---|---|---|---|
| `5A52E505C20` | 9.21 | 10.20c | **3 of 10** | **7.60c** | *none — book empty both sides* |
| `890CDE617E4` | 8.22 | 5.70c | **9 of 18** | 4.70c | **5.10c**, 38,709 deep |
| `D9825147886` | 60.97 | 0.38c | **4 of 16** | 0.14c | **0.32c**, 24,900 deep |

Every YES bid was offered at the **full size asked** (9.00, 8.00, 60.00).

Basis is `market_exposure_dollars / position_fp`, i.e. what he paid including
fees, not a mark.

## What this establishes

- **An exit exists.** Three of three positions drew a bid for the side he
  holds. The enter-only claim is refuted, not merely unsupported.
- **The 40-of-40 "no resting YES bid" finding is dead as a general claim.**
  Two of his three positions carry a resting YES bid on the *public book*
  right now, with 38,709 and 24,900 contracts of depth against holdings of
  8.22 and 60.97. He could sell either outright into the lit book.
- **Neither surface dominates.** On the two books that were quoted, the
  **book beat the RFQ** (5.10c vs 4.70c; 0.32c vs 0.14c). On the empty one
  the RFQ was the only exit at all. So an exit check must read **both**, and
  a desk that reads only one will sometimes report no exit when there is one
  and sometimes take the worse price.

## What this does NOT establish

- **Not that any of these would fill.** Nothing was accepted. A quote is an
  offer with a 3-second maker confirmation window behind it, and a resting
  book bid can be pulled.
- **Not that the exit is good.** **Every** best bid sits below his cost
  basis — 7.60c against 10.20c, 4.70c against 5.70c, 0.14c against 0.38c.
  That is unsurprising (spread, plus these positions may simply be worth less
  than he paid) and it is **not** evidence he is being treated badly. It is
  stated here so no one reads "an exit exists" as "an exit at a good price".
- **Not a rate.** Three positions, one account, one moment, all shard 1, all
  YES-side, all with days left to close. How often a combination draws a YES
  bid at large is unmeasured.
- **Not the same instant for both surfaces.** The books in the last column
  were re-read a few minutes after the RFQs, not simultaneously. The
  direction of the comparison is not in doubt at these gaps, but the exact
  differences are not a paired measurement.
- **Nothing about size.** The largest holding tested is 60.97 contracts.
  Whether bids persist at the sizes a serious position would need is unknown.

## Consequences

- CLAUDE.md's enter-only paragraph is corrected in the same commit.
- ADR 0078's hedge is **not** invalidated — hedging a leg and selling the
  combination are different actions with different costs — but its stated
  premise ("the only exit an enter-only combination has") is now wrong and is
  amended, not deleted.
- `tests/test_combo_book_depth_claims.py` still passes and should: it pins
  what those 40 captures contained, which is still true of those captures.
  What changes is the inference drawn from them.
