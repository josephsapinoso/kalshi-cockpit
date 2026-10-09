# lane/325-check-screen handoff

## BLOCKER for the integrator: `leg_verdicts.trigger` CHECK does not admit `check_button`

`backend/store/schema.sql:3088` still reads
`CHECK (trigger IN ('price_tap', 'leg_buys_open', 'card_button'))`, and
`backend/store/db.py` (`_leg_verdicts_create`, the v58 rebuild) only knows
those three. The route now accepts `trigger = 'check_button'` (#325) and
`insert_running_row` / `insert_refused_row` write it verbatim, so on a
database built from the current schema the first tap on "Ask the scouts"
raises an IntegrityError. Both files are integrator-only. Needed: a schema
bump that rebuilds `leg_verdicts` with `'check_button'` in the CHECK (same
pattern as v58's `card_button`: a rebuild with no new column), plus the
wind-back helper in db.py. I believe this is the next SCHEMA_VERSION after
whatever the merged tree holds; the integrator confirms the number. Do not
ship this lane's frontend before that lands.

## Edits outside the Lane-owns list (minimal, needed to compile/stay green)
- `frontend/src/lib/types/parlays.ts`: `LegVerdictTrigger` gains
  `"check_button"`; `CheckedParlayLeg` gains `probable_bug_status` /
  `probable_bug_reason`; `CheckedParlayResult` gains `friend_source_line`.
  Lane #323 may edit the same file near `CheckedParlayLeg`.
- `tests/test_leg_verdicts_ui.py`: `CheckAParlay.tsx` added to the allowed
  `requestLegVerdicts` callers (its sibling set pins the callers).
- `tests/test_suppressed_legs_are_refused.py`: one UPDATE giving the seeded
  total a `market_width`, because a total with no recommendation row is now
  judged from its fair_prices row and the fixture writes no width.

- `tests/test_parlays_api.py` and `tests/test_parlay_lookup.py`: one
  `UPDATE fair_prices SET market_width = 0.01` each in the seeded-total
  tests (same fixture gap: `seed_total` writes no width).

## Behaviour notes
- Spread/total legs with no recommendations row: `too_few_books`
  (book_count < SuppressionConfig().min_book_count) and `no_market_width`
  (width NULL) are read from the leg's own fair_prices row, in the ladder's
  #79 drop as well as the check (one function: `parlays.probable_bugs_for_legs`).
  Moneyline/prop with no row stay clean, as the singles screen reads them.
- A cached verdict served to the check screen writes no row (the route's
  existing cache branch); a started game is refused as for any leg.
