# 0194 — The record reaches each leg of a combination Joe holds: its own price at purchase and its Kalshi close

**Status:** Accepted on Joe's approval of the 2026-10-08 plan (session 87). Numbered 0194 on `main`: 0193 was the highest and no lane held a DRAFT (`lane_board.py`, 2026-10-08).
**Date:** 2026-10-08
**Schema:** v65 — five nullable columns on `parlay_position_legs` (`ask_at_purchase_tenths`, `ask_source`, `close_yes_bid_tenths`, `close_yes_ask_tenths`, `close_observed_ms`).
**Tickets:** story #320 under epic #83; #322 (this ADR, the schema, the backfill), #323 (the forward capture, the scorer's population, the /bets block).
**Extends:** ADR 0193 (where a pick came from, per ticker), ADR 0078 (the desk watches what Joe holds), ADR 0016 (candlesticks are free and perishable).
**Leaves standing:** ADR 0063 (`gate.py` reads none of this), ADR 0071 §2.5 (a per-row fact is shown, never ranked by), ADR 0038 (the tool's hunt is closed), the leg-verdict registration of 2026-09-25 and its Amendment 1.

## 1. What was missing

Joe asked on 2026-10-02 to "track them and learn from them", and on 2026-08-29 for "a system where I can see how good or bad I do and understand the whys and how to get better". Session 87's scouts found that the record could not reach the leg: the whole card's price is kept (`parlay_positions.stake_tenths`, `parlay_lookups.fair_joint_conservative`, `combo_rfqs.fair_joint`), each leg's outcome is kept (`parlay_position_legs.outcome`, 289 of 289 read on 2026-10-02), but no leg's own price at purchase and no leg's books' chance were kept anywhere. `parlay_check.py:700-715` computed a per-leg chance and discarded it; `parlays.py:2594-2601` stored side, label, game and kickoff only.

So the one question his record could never answer was *which kind of leg loses more often than its price says*. Card-level counts reach 5 expected outcomes a side slowly (168 settled cards at a median price of 4.75c); leg-level counts reach it four to six times faster.

Closing lines were already captured for his hand-placed singles (`scoring.py:138-198`, the `venue_settlements` branch since 2026-08-22), but a combination settles under its own KXMVE ticker, so no leg of a combination had a Kalshi close on record either.

## 2. The decision

1. **Each held leg carries its own price at purchase, for the side held.** `ask_at_purchase_tenths` is the YES ask for a YES leg and `1000 − yes_bid` for a NO leg, the same reflection the desk pays. `ask_source` names the resolution: `lookup` when the forward path wrote the book's derived ask at the instant the desk priced or checked the card (#323); `candle` when `scripts/backfill_leg_prices.py` filled history from the close of the one-minute bar ending at or before `parlay_positions.placed_ms`. The two are the same quantity at two resolutions, and the column says which.
2. **Each held leg carries its Kalshi close, on the leg row.** `close_yes_bid_tenths` and `close_yes_ask_tenths` are the last bar before the leg's true start minus `analysis.clv.DEFAULT_HORIZON_HOURS`, kept as bid and ask the way `closing_lines` keeps one, so the mid and the signed closing-line value come from the same helpers (`ClosingLine.mid_tenths`, `clv_tenths`). The true start is the odds fixture's commence reached through `event_links` → `odds_fixtures`, never `kalshi_events`' clock, which runs three hours late (`scoring.py`'s rule). A leg with no link keeps NULL and is counted.
3. **Never in `closing_lines`.** `score_recommendations` scores every ticker that has a line there, so a held leg's row would enter the gate's CLV population. ADR 0063 keeps the gate blind to what Joe holds; this keeps the gate's statistic blind to it too. `tests/test_backfill_leg_prices.py::TestClosingLinesIsNeverTouched` pins it for the backfill; #323 pins it for the scorer's new population.
4. **History is filled once, by a committed script run by path, never by a migration.** A migration must not reach the venue. `scripts/backfill_leg_prices.py --db /data/cockpit.db --commit --limit N` fills only NULLs (`... IS NULL` in every WHERE), is idempotent, and prints counts only. Kalshi keeps candlesticks about 80 days (ADR 0016:318); the oldest held legs are from 2026-08-18, so the window closes around 2026-11-06, after which the remaining NULLs are permanent and honest.
5. **Unknown is NULL, never 0.** No placed_ms (a hand-typed slip), no link, no bar, an unreadable bar: counted and left NULL. A settled loser genuinely trades at 0.
6. **Two rules for every reader of these columns, pinned by tests in #323:** the record never joins `leg_verdicts` (the registration's §6 forbids any running scout-accuracy figure), and it never splits closing-line value by the books' chance minus Kalshi's ask (that is ADR 0038's consensus row — `beta = −0.141` — run again without a registration). What /bets may show is counts: expected wins at the price paid, wins, and closing-line value in cents, by leg kind, in a fixed order, with `too_few` below 5 expected each side.

## 3. What this does not establish

- That a bar's close equals the ask the fill crossed. It is the minute's close; `scripts/reconcile_candle_ask.py` is the harness for that identity and `ask_source = 'candle'` says which rows rest on it.
- Anything about a leg whose bars the venue no longer keeps, or that was never linked to an odds fixture. The backfill's counts say how many, and they are the session entry's number, not a row.
- Whether any kind of leg does worse than its price. This ADR builds the column; the question needs its own registration once the counts support one, and the measurement rules in CLAUDE.md (n before effect, parts before the pool, the price actually paid) apply to it.
- That the forward path writes the value on every path. `record_position` has four writers (`backend/positions.py`); #323 traces them and reports any that cannot carry the key without touching the order path, which stays with the main session.
