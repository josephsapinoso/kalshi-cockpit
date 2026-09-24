# 0185 — A held combination can ask the makers what they would pay

**Status:** Accepted, building Joe's answer (A) to #63 (2026-09-18: "show both exit prices on `/hedge`, read-only, no selling from the desk"). Built 2026-09-24 on `main` in the same session that took #129's capture; numbered 0185 after `git fetch`, 0184 being the highest.
**Date:** 2026-09-24
**Schema:** v56 — `combo_rfq_quotes` rebuilt (`yes_ask_tenths`, `no_bid_tenths` nullable; `yes_bid_contracts` added); `combo_rfqs.purpose` ('buy' / 'exit') and `.contracts_fp_requested`. No backfill.
**Tickets:** #96 (this build) and #129 (the capture it needed), under epic #82; #147 opened for the list defect found on the way
**Amends:** ADR 0164's reuse-on-409 rule — for a size-based ask only
**Leaves standing:** ADR 0165 (the buy accept path; it now also refuses an exit ask's quote); ADR 0115 (no resting offers); #95's public-book line on the same card

## 1. What was decided

`/hedge` now carries the second exit price Joe asked for in #63: a tap on a
held Kalshi combination fires **one** sell-side RFQ, listens for four
seconds, records every quote, **withdraws the RFQ**, and shows the best bid
with the server's own sentence. There is no accept on this path and the
buy-side accept refuses an exit ask's quotes, so nothing on the desk sells.

The route is `POST /api/hedge/positions/{id}/sell-quote`. Its request is the
position id and nothing else: the ticker is our row's `combo_ticker`, the
size is the venue's own `position_fp`, and the legs are the venue market's
own `mve_selected_legs`.

## 2. The seven defects of the #76 slice-3 review, and what holds each

| # | defect | resolution | test |
|---|---|---|---|
| 1 | `target_cost_dollars` is a spend budget, wrong for a sell | size is `contracts_fp`, floored to 0.01 from `position_fp` (`floor_contracts_fp`). Measured 2026-09-24: the venue took `"2.01"` and 18 makers quoted 2.01 | `TestTheSizeIsTheHoldingFloored` |
| 2 | `build_payload` runs every 60 s unattended | its own POST route; `hedge_watch.py` and `hedge.py` name no RFQ function | `TestTheWatchLoopNeverAsks` |
| 3 | RFQ writes share the shard-1 write budget with orders | the route uses `create_app`'s one `combo_api()` client — the same object, so the same limiter, as the order path and buy RFQ | `TestTheAskUsesTheSharedClient` |
| 4 | `_is_reusable(None)` returned True | a size-based ask meeting `already_exists` is **refused**, neither reused nor deleted; `_is_reusable(None)` now False | `test_combo_rfq.py::…size_based_ask_is_refused…`, route 409 test |
| 5 | a finer-than-tenth price was swallowed | `QuoteRead.refused_bid_finer_than_tenths`, by quote id; status `bid_too_finely` with its own sentence | `TestABidTooFineToPrintIsNamed` |
| 6 | no committed fixture carried a real YES bid | `tests/fixtures/combo_rfq_quotes_sell_side.json`, from #129's run, same commit as the parser | `TestTheCapturedPayload` |
| 7 | `yes_ask_tenths NOT NULL` | v56 rebuild; a sell-only quote stores with both buy prices NULL | `TestTheSellOnlyQuoteIsStorable` |

Every guard was disabled and watched go red, restored by file copy.

## 3. What the capture showed that the review did not predict

- **A sell-only quote carried the best bid.** 2 of 17 quotes named a YES bid
  and `no_bid_dollars: "0.0000"`; the buy-side parser drops such a quote
  whole. On the capture the best bid (10.2c) was one of them — the parser
  as it stood would have reported 10.1c.
- **The bid's size is a separate field**, `yes_contracts_fp`. A sell-only
  quote has no `no_contracts_fp` at all, so `RfqQuote.contracts` (the buy
  side's) is None on it and `yes_bid_contracts` carries the exit's size.
- **The RFQ list is market-wide.** `GET /communications/rfqs?market_ticker=`
  returns every requester's RFQs, `creator_id` blank on all, and ignores
  `rfq_user_filter=self`. #129's instrument refused all three held positions
  on strangers' RFQs until it stopped reading the list (`fd0aa57`). The
  buy path's `open_rfq_for` has the same defect after a 409 — #147.

## 4. What this does not establish

- Nothing about how often a held combination draws a bid, or at what price
  relative to cost. The capture is three combinations at one moment
  (6, 0 and 0 with a parsed YES bid): a count, not a rate.
- That a bid would fill. Nothing was accepted, and nothing on this path can.
- That `contracts_fp` is accepted for every holding shape — measured once,
  at 2.01.
