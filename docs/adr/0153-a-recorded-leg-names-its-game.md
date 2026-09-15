# 0153 — A recorded leg names its game

One lane on `main` (`git worktree list` showed no other), so the ordinal is
taken directly. Ships **schema v43**.

Date: 2026-09-15
Status: accepted
Scope: `parlay_position_legs` gains one nullable column; `record_position`
writes it, `_leg_payload` serves it, `legs_for_position` reads it out of
the lookup blob, and `/hedge` draws it. Nothing priced, gated or sent
changes; `gate.py` still never reads this table (ADR 0063).

---

## 1. The fact this starts from

A position's leg is identified on `/hedge` by `parlay_position_legs.label`
alone (`HedgePositions.tsx`, the leg row). That label is whatever the parlay
card carried at lookup time:

| leg kind | label | names the game? |
|---|---|---|
| moneyline | "Cincinnati Reds to win" | yes, the team is the words |
| spread | "Milwaukee wins by over 1.5 runs" | yes |
| total | "Under 8.5 runs scored" — Kalshi's own subtitle | **no** |
| player prop | "Anthony Kay: 6+ strikeouts" | a player, not a game |

Totals and props became legs on 2026-09-15 (ADR 0152). The first "Three
totals" card showed Joe three "Under 8.5 runs scored" rows he could not
tell apart, and he said so. The card was fixed the same day by drawing
`event_title`, which every leg of the wire has carried since ADR 0051 and
nothing drew (`2d8de82`). The position screen has the same gap one tap
later, and there the field had nowhere to live: `leg_details_for` wrote
`side`, `label`, `league`, `commence_ms` into `parlay_lookups.selected_legs`
and `record_position` had a column for each of those and no other.

## 2. Decision

- **`parlay_position_legs.event_title TEXT`, nullable.** Migration step 43,
  `columns` only, additive; the generic column drop is the undo.
- **Written from the lookup blob.** `leg_details_for` has put `event_title`
  in `selected_legs` since `2d8de82`; `legs_for_position` passes it through
  and `record_position` stores it. A blob written before that, and a slip
  typed by hand on `/hedge`, carry no title and the column is NULL.
- **NULL prints as nothing.** The screen shows the label alone on a NULL,
  never a game reconstructed from the ticker. A guessed game on the screen
  that says what Joe holds is the "unreadable resolves to a value" defect
  with money behind it.
- **The suffix is dropped at render.** Kalshi titles a total event
  "Baltimore vs New York M: Total Runs" on live and "Indiana vs Chicago:
  Total" in the captured fixture; the suffix is the market kind, and the
  same strip the parlay card uses is applied here.

## 3. What this does not do

- It does not backfill. The four `parlay_positions` rows on live (orders
  4–7, all `STATE_DEAD`) predate the column and stay NULL; their lookups'
  blobs predate `2d8de82` too, so there is nothing on the record to fill
  them from.
- It does not touch `hedge_watch.py`'s reads, which select named columns
  and do not need the game.
- It does not make `/hedge` show a game for a hand-typed slip. That form
  takes a ticker and a label; adding a title field there is a separate
  decision nobody has asked for.

## 4. Guards

`tests/test_hedge_positions.py::TestARecordedLegNamesItsGame` — the column
is added by exactly one step and lands on a volume that predates it; the
recorder keeps it and the payload serves it; the blob reader passes it
through and invents none. Each seen red under its mutation (the step's
`columns` emptied; the INSERT writing `None`; the payload writing `None`;
the reader writing `None`).
