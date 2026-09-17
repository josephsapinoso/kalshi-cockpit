# A dated reading — the transacted path, 2026-09-17 ~00:40Z

Not a registered census and not a finding. This is a snapshot: the number
CLAUDE.md used to carry inline, moved here because a live count decays and a
dated reading is allowed to. See ADR 0162 for why the spine stopped stating
it directly. Re-run the instruments below for a current number; do not
extrapolate from this one.

## Instruments

- `manual_orders` — `.venv\Scripts\python.exe scripts/inspect_live_db.py
  manual-orders-audit` (base64-exec over `flyctl ssh`, per
  `reading-the-live-instance`). Filled orders are the `status = 'filled'`
  subset of the same read.
- Open `parlay_positions` — `GET /api/hedge`, which lists `status = 'open'`
  only; a closed row would not show here at all.

## The reading

```
manual_orders       16 rows, all real (dry_run = 0)
  filled            14
  unfilled          2
  distinct tickers  16, all KXMVE
  first             2026-09-08T19:41Z
  newest            2026-09-17T00:37Z

parlay_positions (open, /api/hedge)   17 rows, ids 1-17
  ids 1-2's orders   have NO position (predate the position writer)
  ids 11-15          hand-recorded: NULL combo_ticker, NULL placed_ms
```

## Why the two tables disagree, and why that is designed, not a defect

`record_position` (`backend/hedge.py:350`) has two callers:

- `backend/api/routers/hedge.py:73` — `POST /api/hedge/positions`, where Joe
  types a ticket by hand for a bet placed somewhere else (a sportsbook slip,
  or a Kalshi bet placed outside the tool). `combo_ticker` and `placed_ms`
  both come from the request body as optional fields and default to `None`
  when he doesn't supply them.
- `backend/api/routes.py:4612` — the armed hand-bet order path
  (`_record_combo_position`), which always sets both from the order it just
  placed.

So an order can exist with no position (orders 1-2 predate the position
writer entirely) and a position can exist with no order (ids 11-15 are
hand-recorded). ADR 0160's read refuses to join a `kalshi_combo` position
with a NULL `combo_ticker` (`no_order_row`) rather than guessing at a join —
that refusal is correct given the above, not a gap to close.

## What this does not establish

- A rate, a trend or a projection. It is one instant on one date.
- That ids 1-2 and 11-15 are the *only* rows of their kind — they are the
  ones this read happened to name as examples; more of both kinds will
  accumulate as Joe keeps betting.
- Anything about fills vs. venue charges — that is the separate, spent,
  registered census in
  `docs/measurements/2026-09-15-recorded-fill-vs-venue-charge-census-result.md`.

## Correction trail this reading closes

CLAUDE.md's transacted-path paragraph carried a live count inline and
corrected it four times in nine days: "two" (until 2026-09-10), "four by
2026-09-09" (until 2026-09-14), a 7/6/4 reading (until 2026-09-15, found six
orders stale), and a 13/12/10 reading (until 2026-09-17, found three orders
and seven positions stale two days after it was written). This document is
the last one written *as* a spine figure; ADR 0162 stops the pattern by
moving the number here and leaving only the instrument name in CLAUDE.md.
