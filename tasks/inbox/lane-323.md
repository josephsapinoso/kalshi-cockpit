# lane/323-per-leg-capture, handoff notes (ADR 0194, #323)

Nothing here needs a forbidden file edited. Notes for the integrator.

## Writers traced (read-only)

All four `record_position` callers in `backend/positions.py` get their leg dicts from one of two places:

- `record_order_fill` (order path, via `manual_order._record_combo_position`) and `record_rfq_accept` (RFQ path) both build legs with `parlays.legs_for_position(<parlay_lookups.selected_legs>)`. That function is in `backend/parlays.py` (lane-owned), and now carries `kalshi_ask_tenths` through. So both armed paths write `ask_at_purchase_tenths` with `ask_source = 'lookup'` **without any edit to routes.py, manual_order.py or combo_rfq.py**. `combo_rfq.py:283` only reads the lookup blob for the ask; it does not rebuild it.
- `record_hand_entry` and `record_adopted` take caller-typed legs with no lookup behind them, so they carry no ask: NULL on both columns (the designed state; the ADR's backfill is what can fill history for them).

Caveat to state in the ADR 0194 amendment if wanted: for the order and RFQ paths the stored ask is the one the desk read when it priced or checked the card (`parlay_lookups.requested_ms`), not the instant of the fill. `ask_source = 'lookup'` says so.

## Suggested follow-ups (not done, not in lane)

- `frontend/src/lib/types/bets.ts` should gain `ByLegKind` / `LegKindBlock` and `BetsRecord.by_leg_kind?`. The page declares them locally (page.tsx) because that file is outside the lane; moving them is a no-risk cleanup.
- `backend/kalshi/*` untouched. `bets.leg_kind` re-implements `scripts/count_combo_leg_sides.py::classify_leg_kind` over the same `discovery._SERIES_RE` / `_SUFFIX_TO_MARKET_TYPE` / `props.is_prop_series` primitives instead of importing the script, because `.dockerignore` ships `scripts/*` only by allowlist and an import would 500 `/api/bets` on Fly. `tests/test_bets_summary.py::TestByLegKind::test_the_kind_agrees_with_the_census_scripts_classifier` pins the two together.
- Scorer cost: a leg whose candle bar never appears (aged out, thin market) stays NULL and is re-requested every full pass, at one horizon, exactly as an unscoreable recommendation is today (`inspect_live_db_decisions.py` section B names that). Bounded by the number of open legs; worth a retry cap only if `candles_missing` grows.
- `ScoringCounts` gained `leg_closes_stored`, `leg_rows_closed`, `leg_closes_unreadable` (not in `ALWAYS_REPORT`, so they print only when non-zero).
- Schema version: this lane writes no schema; ADR 0194 / v65 is already on main.

## One test outside the lane now needs its expectation widened (not touched)

`tests/test_combo_fill_is_watched_for_a_hedge.py::TestTheLookupRecordsWhatThePositionNeeds::test_a_priced_lookup_carries_side_label_league_and_commence` (line ~606) pins `leg_details_for([leg])` to an exact dict. The lane's change adds two keys to that dict, so the expected dict needs `"kalshi_ask_tenths": None, "desk_chance": 0.55` (the fixture leg's `p_conservative`). Failure is the dict-equality, nothing else. Everything else in the recipe's grep set is green.
