# One RFQ on an "empty" combination returned three maker quotes in 107ms

Date: 2026-09-17
Authorised by Joe the same day ("A. Yes" on #59): one real RFQ, read the
quotes, accept nothing.

## What was asked

`POST /communications/rfqs?exchange_index=1`

```json
{"market_ticker": "KXMVECROSSCATEGORY-S20264E0CD4DDEA6-BBE0304F0C9",
 "rest_remainder": false,
 "mve_collection_ticker": "KXMVECROSSCATEGORY-R",
 "mve_selected_legs": [
   {"event_ticker":"KXNCAAFGAME-26SEP17SYRPITT","market_ticker":"KXNCAAFGAME-26SEP17SYRPITT-PITT","side":"yes"},
   {"event_ticker":"KXWNBAGAME-26SEP17CONNATL","market_ticker":"KXWNBAGAME-26SEP17CONNATL-ATL","side":"yes"},
   {"event_ticker":"KXWNBAGAME-26SEP17LVSEA","market_ticker":"KXWNBAGAME-26SEP17LVSEA-LV","side":"yes"}],
 "target_cost_dollars": "5.0000"}
```

`rfq_id 8f26cd6d-b40a-48a8-b8ef-e3f426fb8a23`, created 15:50:47.4Z.

**The same combination's order book was empty on both sides**, read three times
that day: `{"no_dollars": [], "yes_dollars": []}`. The desk had refused to sell
it to Joe on exactly that basis.

## What came back

**At least three distinct makers**, all within ~107ms of the request. (At least:
the probe's console output was tailed at 45 lines and three complete quote
objects survived the cut. The count line did not.)

| maker (creator_id, first 8) | `no_bid_dollars` | YES ask = 1 - no_bid | `no_contracts_fp` | created |
|---|---|---|---|---|
| `3d357e70` | 0.4070 | **$0.5930** | 8.19 | 15:50:47.631 |
| (first row) | 0.3900 | $0.6100 | 7.97 | 15:50:47.684 |
| `4f3d6d11` | 0.3690 | $0.6310 | 7.72 | 15:50:47.577 |

Every quote carried `yes_bid_dollars: "0.0000"` and a populated
`no_bid_dollars`. **A maker's resting NO bid is the YES ask** — the derived-ask
identity, the same one `OrderBook.best_yes_ask` implements.

- Best quoted YES ask: **$0.5930**
- The card's own fair value (conservative joint, `parlay_lookups` id 86): **$0.57805**
- **Pay-over-fair: +1.49 cents per contract**, before fees.
- Spread across makers: **3.80 cents**.

The RFQ was deleted immediately. **Nothing was accepted and no money moved.**

## What this establishes

- **A combination with a visibly empty order book had a real, takeable price.**
  The refusal Joe saw was an artifact of reading the wrong surface.
- RFQ creation works on an ordinary retail key. No entitlement was needed.
- `exchange_index=1` is required on the write. Without it the create returns a
  Kalshi-JSON `404 not_found` — the same failure `rest.py:78-84` recorded for a
  shard-1 cancel on 2026-08-30.
- `market_ticker` and `rest_remainder` are required on create; the mve fields
  are *additional to* `market_ticker`, not instead of it.
- Quotes are read with `GET /communications/quotes?rfq_user_filter=self`. The
  deprecated `rfq_creator_user_id` is not needed. **After the RFQ is deleted the
  quotes vanish from that view** (re-read returned 0) — so a quote must be
  captured when it arrives or it is gone.

## What this does NOT establish

- **Not a rate, and not a price.** n = 1 RFQ, one combination, one moment,
  one target cost, ~8 hours before kickoff. Three makers here says nothing
  about how many quote a 5-leg combo, a different league, or a minute before
  first pitch.
- **Not that the quote would have filled.** Accepting was not attempted. The
  maker still has a 3-second confirmation window (combos are High Volatility
  Markets) and may decline.
- **Nothing about exit.** This was a buy-side RFQ. Whether a *sell* RFQ draws
  bids is untested, and that is the question CLAUDE.md's "combinations are
  enter-only" actually turns on — a claim built on lit-book reads that could
  never have seen this surface. It is **unsupported, not refuted.**
- **Not that +1.49c is representative.** One draw. Bucketing pay-over-fair by
  anything would be a ranking dressed as a fact at this n.
