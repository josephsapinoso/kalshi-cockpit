# 0184 — A hand-recorded slip with a lost leg closes itself

**Status:** Accepted on Joe's answer (A) to #142, 2026-09-23 ~23:20Z (option buttons). Numbered 0184 on `main` after `git fetch`, 0183 being the highest and no lane holding a DRAFT.
**Date:** 2026-09-23
**Schema:** v55 — `parlay_positions.closed_reason` (`'lost_leg'`, nullable, column-level CHECK, no backfill)
**Tickets:** #143 under epic #82; Joe's question #142
**Amends:** ADR 0181's "a hand-recorded slip is still Joe's tap" — only for a slip one of whose legs has lost
**Leaves standing:** ADR 0181 for order-linked combinations (they close on the venue's settlement only; "every leg resolved" is still not the trigger for them); ADR 0136 reasons 1 and 2; ADR 0063 (`gate.py` never reads these tables)

## 1. What Joe decided

#142: *a parlay you typed in by hand stays open on /hedge after one of its
legs has lost, until you tap it closed. Should the desk close it itself?*
He answered **(A)**: close it automatically, recorded as lost, and keep it
distinguishable from his own tap. (B) (sort dead slips below live ones) and
(C) (no change) were offered and not chosen.

A parlay with a lost leg cannot win; `assess` already calls it
`STATE_DEAD` (`backend/hedge.py`). A hand-recorded slip carries no
`combo_ticker`, so the venue pass of ADR 0181 can never reach it, and
before this it stayed on `/hedge` until he tapped it.

## 2. What was built

- `close_dead_hand_recorded` (`backend/hedge.py`): every open position with
  `combo_ticker IS NULL` and at least one `lost` leg moves to
  `status = 'settled'`, `closed_reason = 'lost_leg'`. `closed_source` names
  who resolved the losing leg: `'venue'` if any lost leg was resolved from
  Kalshi's market result, else `'manual'`.
- It runs in the watcher's cycle beside `close_settled_combinations`, in the
  same try, before the "anything live" gate (ADR 0181's reason for the
  placement applies unchanged).
- A tap leaves `closed_reason` NULL. That is how a desk close and a tap stay
  apart even when Joe marked the losing leg himself.

## 3. Why a new column and not a third `closed_source` value

`closed_source`'s CHECK is column-level. Widening it means rebuilding
`parlay_positions`, and `parlay_position_legs` references that table by
foreign key. The runner opens connections with `foreign_keys = ON` and
runs steps inside one transaction, where that pragma cannot be switched
off, so `DROP TABLE parlay_positions` would fail or orphan legs. The
runner has never taken a step like that, and this volume cannot be
recreated. A nullable column is an `ALTER TABLE ADD COLUMN`, the same
shape as v54. `closed_source` keeps its meaning: who established the fact
that closed the row.

## 4. Consequences

- `/hedge`'s open list stops carrying dead hand-recorded slips on the
  watcher's first cycle after deploy. Nothing is deleted; the rows are
  `settled` in the record.
- An order-linked combination with a lost leg is still listed until the
  venue settles it. That is ADR 0181, unchanged.
- #141's watcher filter (skip a held parlay with a lost leg) still matters
  for those order-linked rows.
- #96's schema slot slides from 55 to 56.
