# 0064 — The daily-loss ledger reads the venue's own record, and refuses when it cannot

**Date:** 2026-08-22
**Status:** Accepted.
**Owns:** the source of truth behind `daily_pnl_dollars` wherever sizing or
an order path consumes it (`backend/core/sizing.py:200`'s kill switch and
every caller that feeds it).
**Corrects** the wiring, not the rule: ADR 0024's decision that the risk
path must consume realised P&L stands; this ADR decides *which table is
real*.

## 1. What happened

The daily-loss kill switch was traced end to end during the 2026-08-22
review: `sizing.py:200` reads `daily_pnl_dollars` ←
`settlement.daily_realised_pnl_dollars` ← `SUM(pnl_cents) FROM settlements`
← written only by `settle_position` ← swept only over `orders` ← written
only by the engine's order path — **which has never placed an order**
(`ORDERS_ARE_DRY_RUNS = True` since birth). The switch therefore returns
$0.00 forever, as a *genuine measurement over an empty table*, so it does
not even trip the unreadable-refuses-`None` convention. Meanwhile `/gate`
advertises "a daily-loss kill switch" as if it bound something, and Joe's
actual losses accrue in `venue_settlements` — the mirror of the venue's own
settlement record, polled since 2026-08-18 — which nothing on the risk path
reads.

A cap that is structurally always zero while a screen names it a kill
switch is worse than no cap: it spends the credibility the real one will
need.

## 2. The decision

**Daily realised P&L, wherever it gates money, is computed from
`venue_settlements`** — the venue's own numbers, covering every bet however
placed — bounded to the current desk day (the same day-roll hour the
`tonight` payload uses).

**Staleness refuses, it never zeroes.** The mirror is fed on the 5-minute
fills/balance cadence; if its freshest read is older than
`TONIGHT_STALE_AFTER_MS` (30 min = 6× cadence, the constant the `tonight`
payload already uses), the function returns `None`, and `sizing.py`'s
existing `None`-refusal (`:192`) does the rest: no sizing, no order, with a
named reason. A stale mirror at 8pm otherwise reports "no losses today"
while three bets are down — the false negative in the flattering direction,
on the exact quantity that exists to stop the fourth bet.

The engine-path `settlements` table keeps its meaning (fees and P&L for
orders *this tool* places, per-regime tagging per ADR 0058) — it is simply
no longer the risk path's denominator while it is empty of the only bets
that exist.

## 3. Consequences

- `venue_settlements` gains a read-path consumer that money depends on, so
  its ingestion gets the same guard standard as the order path: the
  staleness constant is shared, not duplicated, and the refusal is verified
  by disabling it and watching the test fail.
- The sentence on `/gate` describing the kill switch names its channel and
  its source ("the venue's settled record, refused when stale") — scope
  sentences that outlive their wiring are how the last hole stayed open.
- When the engine path someday places real orders, its settlements appear
  in `venue_settlements` too (the venue settles them like any other); no
  double-count is possible while the risk path reads only the mirror.
