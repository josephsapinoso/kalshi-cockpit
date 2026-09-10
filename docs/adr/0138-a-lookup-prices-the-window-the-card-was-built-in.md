# ADR 0138 — A lookup prices the window the card was built in

**Status:** Accepted, 2026-09-10.
**Date:** 2026-09-10.

## 1. The bug

`GET /api/parlays?horizon=...` has carried a window control since 2026-09-06
(`tonight` / `tomorrow` / `48h`, `backend/parlays.py`'s `HORIZONS`), so a card
can be built from a game kicking off tomorrow night or the night after. But
`POST /api/parlays/lookup` — the "Price on Kalshi" tap — never read the
window at all: `price_card_on_kalshi` called `ladder_candidates(...)` with no
`horizon`, which defaults to `tonight`. So a card built under `tomorrow` or
`48h` priced fine on its tonight legs and refused every leg beyond tonight,
in a sentence that guessed why: *"is no longer on the desk's slate (its game
has started, or it is past tonight's last game)"* — wrong for a leg that has
not started and is exactly where the reader built the card from.

The refusal also never touched `parlay_lookups`: `resolve_requested_legs`
raises `LookupRefused` before the function's first `_record_lookup` call, so
the one outcome the table's own docstring promised a row for — "every
lookup is recorded, every outcome" — was the one it silently dropped.

## 2. The fix

**A. The horizon travels with the tap.** `ParlayLookupRequest` gains a
`horizon: str = DEFAULT_HORIZON` field with a pydantic validator refusing an
unknown key in the same words the GET route already uses (`HORIZONS` is the
one list both read). The route passes it through; `price_card_on_kalshi`
gains `horizon: str = DEFAULT_HORIZON` and passes it to `ladder_candidates`.
The client sends back `ladder.window.key` — the same echo `WindowPicker`
already renders — so the two calls agree by construction: `ParlayCards` ->
`Card` -> `PriceOnKalshi` -> `lookupParlay(..., horizon)`.

**B. The refusal says only what is known.** `resolve_requested_legs` gains
`conn`, `now_ms` and `horizon`. For a leg absent from the candidate pool, a
small query (`_commence_ms_for_tickers`, one `SELECT ... WHERE ticker IN
(...)`, scoped to only the missing tickers) reads the leg's own kickoff off
the sportsbook's clock — `kalshi_markets -> kalshi_events -> event_links ->
odds_snapshots`, never `kalshi_events.commence_ms`, which runs three hours
late (CLAUDE.md). Three sentences, and only these three:

    "<ticker>'s game has started"                    commence_ms <= now_ms
    "<ticker> kicks off after the '<window words>'
     window ends -- pick a wider window"              commence_ms > horizon_end_ms(now, horizon)
    "<ticker> is not a leg this desk serves"           everything else

The third catches a genuinely unknown ticker, and a ticker that IS inside the
window and has not started but is still absent from the pool for some other
reason (stale consensus, no probability, not a market this desk prices at
all) — both are honestly "not served"; neither is a guess.

**C. A refused lookup writes a row.** Schema v38 widens `parlay_lookups`'
`CHECK (status IN (...))` to admit `'refused'` — a table rebuild
(`parlay_lookups_v38`, copy, drop, rename), the only way SQLite can change a
table-level CHECK, following the v35 (`manual_orders`) rebuild pattern:
`INSERT OR IGNORE` plus drop/rename make a full replay idempotent with no
completion-marker column, and the migration recreates `idx_parlay_lookups_time`
(the v4 `settlements` precedent, for a rebuild whose table carries an index).
`price_card_on_kalshi` now catches `LookupRefused` from
`resolve_requested_legs`, records `status="refused"` with the requested legs
in wire order and the refusal's own words in `error`, then re-raises
unchanged. No market was minted on this branch, so every book/mint column
stays `NULL`. `horizon` rides along in `selected_legs`' per-leg detail;
`legs_for_position` reads fields by name and ignores extras, so this cannot
break a `priced` row's reader.

The `book_empty` branch also gained detail it always had access to and threw
away: `error` now carries `"yes_bid=<tenths|none> yes_levels=<n>
no_levels=<n>"`, so a book with something resting on YES (but nothing on NO,
which is what makes it `book_empty`) is distinguishable from a book that is
empty on both sides — without a second migration, since `error` is already
free text.

**D. The copy.** Two sentences were wrong about who quotes a combination.
`ParlayCards.tsx`'s price-to-beat caption said "Kalshi itself almost never
has anyone selling this combination" — false: Kalshi quotes the minted
combination itself, and a resting NO bid *is* the ask you pay (33 of 40
books read carried one, ADR 0078 amendment 2026-09-08). Corrected to say
Kalshi quotes it, nobody has to be selling at the moment you tap, and the
real absence is an exit: nobody bids to buy it back. The Stakes caption said
"Nobody has offered this price" over an estimate that was never asked of
Kalshi at all; corrected to "This is an estimate, not Kalshi's quote,"
keeping the required "resting" / "capped" / "usually worse" language
(`tests/test_parlay_estimate_is_not_a_price.py`). The `book_empty` words
dropped "Try again shortly" — this desk's own repeat-lookup record never
shows an empty book turning into a quoted one on a later ask, and a
screen that tells the reader waiting helps when it has never measured that
is the CLAUDE.md screen-lies-in-the-interval failure by another name.

## 3. What this does not establish

That a wider window's legs are buyable — `combo_eligible_events` and the
venue's own collection membership are unrelated gates, unaffected by this
change (ADR 0071 §2.4's boundary is untouched). Nothing about whether Kalshi
combines a game two nights out at all; that was already true or false before
this fix and this fix only lets the lookup ask the right question about it.
Nothing about the `book_empty` repeat-ask claim beyond what `tests/fixtures/
combo_lookup_repeat.json` pins (one collection, one leg pair, two calls
seconds apart) — the copy change states the record as it stands, not a new
measurement.

## 4. How this was verified

- `tests/test_parlay_lookup.py::TestHorizonTravelsWithTheTap`: a leg kicking
  off tomorrow prices under `tomorrow` and refuses under `tonight`; a leg two
  nights out prices under `48h` and refuses under `tomorrow`; a started leg
  is named as started, never as a windowing problem; an unknown horizon is a
  422 naming the choices; omitting `horizon` still prices `tonight`.
- Mutations run and reverted: dropping the `horizon=horizon` pass-through in
  `price_card_on_kalshi` turns both cross-window "prices under the wide
  window" assertions red. Swapping the `<=`/`>` comparisons in the
  started/after-window fork turns four tests red (the dedicated swap test
  and both cross-window tests' refusal-sentence assertions). Changing the
  refused branch's `status="refused"` to `"error"` and dropping the
  `book_empty` branch's `error=book_detail` kwarg each turn their own
  dedicated assertions red.
- `tests/test_store.py::TestParlayLookupsAdmitRefused`: the pre-migration
  CHECK rejects `'refused'`; the migration carries every existing row,
  values and all; a refused row is accepted afterward; an unknown status is
  still rejected; `idx_parlay_lookups_time` survives the rebuild; the step
  replays cleanly at both crash points (after full success, and after the
  copy but before the drop/rename) without duplicating or losing rows.
  `tests/test_store.py::TestMigration` (parametrised over `sorted(db.
  _MIGRATIONS)`) and `tests/test_parallel_lanes_do_not_collide.py::
  test_every_version_is_accounted_for` cover v38 automatically.
- `cd frontend && npx tsc --noEmit` — clean.
- Full targeted run: `tests/test_parlay_lookup.py
  tests/test_parlays_api.py tests/test_parlay_estimate_is_not_a_price.py
  tests/test_parlay_leg_facts.py tests/test_buy_controls.py tests/test_store.py`
  — 306 passed. `ruff check .` — clean.
