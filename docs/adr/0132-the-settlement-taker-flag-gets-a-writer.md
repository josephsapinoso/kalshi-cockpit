# ADR 0132 — The settlement taker flag gets a writer

**Date:** 2026-09-09
**Status:** Accepted.
**Scope:** `venue_settlements.is_taker` only. Nothing here touches the fee
model, the fee alarm, `fills`, the gate, or any order path.

## 1. The column had a schema, a reader, and no writer

`backend/store/schema.sql:1230` declares `is_taker INTEGER` on
`venue_settlements` with `CHECK (is_taker IS NULL OR is_taker IN (0, 1))`.
`backend/bets.py:291` selects it and `:377` puts it on the `/bets` payload.

Nothing ever assigned it.

- The INSERT in `poll_settlements` (`backend/portfolio_poll.py`) names ten
  columns and `is_taker` is not among them. It cannot be: the
  `/portfolio/settlements` payload has no such field — `parse_settlement`'s
  observed shape is eleven keys and none of them is maker/taker.
- `estimate_match.refine_first_seen` is the upgrade pass that fills settlement
  columns from a join against `fills`. It writes `position_first_seen_ms`,
  `position_time_source` and `n_fills_in_position`. It skips this one.

**Measured on the live instance, 2026-09-09 (read-only, `mode=ro`):**

```
venue_settlements                90 rows,  is_taker NULL on 90
venue_settlements KXMVE          62 rows
fills                           102 rows,  is_taker NOT NULL on 102
fills KXMVE                      68 rows   (67 taker, 1 maker)
KXMVE settlements with no matching fill row      0
```

So the answer was in the next table over for every settled position, and the
`/bets` screen has been reporting it as unknown since the column shipped.

## 2. The decision

`backfill_settlement_taker(conn)` lives in `backend/portfolio_poll.py` and is
called from `poll_settlements` after its INSERT loop, inside the caller's
transaction. It sets `is_taker` on rows still NULL from the position's own
mirrored fills.

**Why in `portfolio_poll.py` and not in `refine_first_seen` beside its three
siblings.** `refine_first_seen` runs on `run_match_pass`, which rides the
twelve-hour mirror. `poll_settlements` runs on the five-minute fast branch of
`poll_portfolio_forever` — the same pass that writes the settlement row. The
flag becomes visible on `/bets` in the cadence the row itself arrives on
rather than up to twelve hours later, and the write costs no network call and
no extra lock acquisition.

## 3. What it refuses

- **Fills that disagree resolve to NULL.** A position whose fills are part
  maker and part taker has no single answer. A majority vote would be an
  invention, and this repo's standing rule is that unreadable resolves to
  `None`, never to a convenient value. The row is counted in the pass's
  `mixed` return and logged at WARNING. Live today this case does not arise;
  the one maker fill is alone on its ticker.
- **No mirrored fill resolves to NULL.** Absence of evidence is not evidence
  of making.
- **An already-written flag is never overwritten.** The `WHERE s.is_taker IS
  NULL` restriction makes the pass idempotent and keeps the column history
  rather than a derived view that silently changes under a late fill.

**No `source` filter, unlike `refine_first_seen`.** That pass restricts to
`source = 'venue_hand'`. A position filled partly by the engine and partly by
hand is still one position, and answering maker/taker from a subset of its
fills is the same substitution the mixed case refuses. On the live record the
two cuts are identical — all 102 fills are `venue_hand`, the engine path being
dry (`ORDERS_ARE_DRY_RUNS = True`) — so this differs only in the case where
the difference would matter.

## 4. What this does NOT do

**It does not touch the fee alarm.** `reconcile_fill_fees` reads `fills`, not
`venue_settlements`, and `fills.is_taker` was never the problem: it is
`NOT NULL`, written from the venue's own boolean, and populated on all 68
`KXMVE` rows including both 2026-09-08 combination fills. The alarm's
reachability was already fine. This ADR fixes a display fact, not an
interlock.

**It does not make `is_taker` a fee-model input, an ordering key, or a
filter.** It is a per-row fact on a screen. Nothing ranks by it.

**It runs no migration.** The first live pass that runs `poll_settlements`
writes the 90 existing rows because they are all NULL, and the pass is a
no-op forever after.

## 5. Verification

Eight tests in
`tests/test_portfolio_poll.py::TestSettlementTakerIsWrittenFromTheFills`.
Each guard was disabled and the suite watched go red:

| mutation | test that failed |
|---|---|
| mixed-fills branch made unreachable | `test_a_position_whose_fills_disagree_stays_null` |
| write hardcoded to `1` | `test_a_maker_position_gets_is_taker_0_not_left_null` |
| `WHERE source = 'venue_hand'` added to the join | `test_an_engine_fill_counts_too` |
| `WHERE s.is_taker IS NULL` removed | `test_a_second_pass_rewrites_nothing`, `test_an_already_written_flag_is_never_overwritten` |
| call removed from `poll_settlements` | `test_the_settlements_poll_writes_it_without_being_asked` |

The last one is the one that matters most in this repo: a backfill nothing
invokes is not a fix, and the chain that proves it does run is
`backfill_settlement_taker` <- `poll_settlements` <-
`poll_portfolio_forever` <- `scripts/run_loop.py`.
