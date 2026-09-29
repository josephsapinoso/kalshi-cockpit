# Lane 202 (game page) handoff

Branch `lane/202-game-page`. Nothing here touches schema, config, ADR numbers.
`SCHEMA_VERSION`: unchanged, no schema edit needed (`parlay_lookups.status`
CHECK already admits `priced` and `book_empty`, which is what the mint writes).

## Edits outside the ticket's Lane owns (both forced by "test_token_proxy_routes.py green")
- `frontend/src/middleware.ts`: `"/game-mint"` added to `JSON_ROUTE_HANDLERS` (add-only).
- `tests/test_token_proxy_routes.py`: `"game-mint"` added to `TOKEN_HANDLERS` (add-only).

## Private helpers imported (not edited; #201 edits these modules)
From `backend/parlays.py`: `_collections`, `_choose_collection`, `_record_lookup`,
`_commence_ms_for_tickers`, `_FALLBACK_COLLECTION_PREFIXES`, `candidate_pool`,
`ladder_candidates`, `LookupRefused`, `invalidate_collections_cache`.
From `backend/parlay_check.py`: `_leg_label`, `_missing_leg_reason`,
`_percent_display`, `_reason_words`, `_titles_for`.
If #201 renames or moves any of them the game builder breaks at import; making
them public (drop the underscore) would be the durable fix.

## card_key = "game" consumers
- No frontend reader of `parlay_lookups.card_key` exists.
- Backend readers that use it as a DISPLAY LABEL: `backend/api/routes.py` (~4709,
  the order path's `record_position(label=lookup["card_key"] or ticker)`) and
  `backend/combo_rfq.py` (~1482, the RFQ accept path's position label). A position
  bought through the game page will therefore be labelled just "game" on /hedge.
  A label built from the legs' titles would read better; not done (both files
  are on the money path and outside this lane).
- `bets.py` treats a `priced`/`book_empty` row with NULL `fair_joint_conservative`
  as `checked_without_chance` (#168): a game combo will read "checked, no chance
  for the whole parlay" on /bets, which is true.

## Things a reviewer should know
- The mint refusal for "a leg not on this game" is exact only after the game page
  was viewed in the same process (`_listing_memory`, 30 min). Cold, it is
  structural (event shares the game's fixture suffix and league prefix) plus the
  catch-all collection's own event list; a bogus market under a real event goes
  to Kalshi and comes back as a recorded 502.
- No capture of an open `-R` catch-all `associated_events` exists (the collection
  list is not a public read). Tests point the captured `KXMVESPORTSMULTIGAMEEXTENDED`
  entry shape at the Atlanta at Pittsburgh events whose MARKETS are captured.
  The `size_max` 1-vs-absent split comes from the ticket, not from a fixture.
- The mint reads the minted market's order book once (context only) to choose
  `priced` vs `book_empty`. Failure to read it is recorded in `error`, never fatal.
