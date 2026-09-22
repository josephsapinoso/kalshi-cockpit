# 0181 — A combination the venue has settled closes its own row; a hand-recorded slip is still Joe's tap

**Status:** Accepted on Joe's answer (A) to #131, 2026-09-22 ~16:20Z. Numbered 0181 on `main` after `git fetch`, 0180 being the highest and no lane holding a DRAFT.
**Date:** 2026-09-22
**Schema:** v54 — `parlay_positions.closed_source` (`'venue' | 'manual'`, nullable, column-level CHECK, no backfill)
**Tickets:** #135 under epic #82; Joe's question #131
**Amends:** ADR 0136 §"Why no auto-close" — reason 3 only, and only for the venue-settlement trigger; ADR 0151 §4's "`parlay_positions.status` never advances — STRUCK"
**Leaves standing:** ADR 0136 reasons 1 and 2; ADR 0078 (the hedge is the exit the desk watches; closing a hand-recorded slip is Joe's tap); ADR 0063 (`gate.py` never reads these tables); ADR 0162 (no decaying count in a trusted document)

---

## 1. What Joe decided

#131 (opened 2026-09-22 05:05Z, answered ~16:20Z): *once Kalshi settles a
combination you hold, should the desk close its row by itself, or does
closing stay your tap?* He answered **(A)**: close it. Option (B) — close
when every leg has resolved — was offered and not chosen.

Until this ADR `parlay_positions.status` moved only at his tap:
`close_position` (`backend/hedge.py`) had exactly one production caller,
`POST /api/hedge/positions/{id}/close` (`backend/api/routers/hedge.py`).
ADR 0136 gave three compounding reasons for that, and ADR 0151 §4 struck
the alternative "for good". The reasons are re-read here one at a time,
because two of them are still true.

## 2. What is amended and what is not

**ADR 0136 reason 1 — absence from a poll is not definitive — STANDS.**
`at_venue` still closes nothing. The trigger is never "gone from the
positions poll".

**ADR 0136 reason 2 — a settlement does not say which leg lost — STANDS.**
The pass marks no leg. `parlay_position_legs.outcome` still moves only
through `resolve_from_venue` (from `kalshi_markets.result`) or by hand.
`tests/test_a_venue_settled_combination_closes_its_own_row.py` pins that a
settled combination's legs still read `pending` after the pass.

**ADR 0136 reason 3 — the close is Joe's tap — AMENDED, for one trigger.**
"A record changing when the operator did not touch it is a second,
undisclosed opinion about what happened to his money." The venue's own
settlement of the combination market is not our opinion; it is the venue's
statement about his money, mirrored verbatim into `venue_settlements`. The
row now says who moved it (`closed_source`), so nothing is undisclosed.
For a hand-recorded slip — no `combo_ticker`, the venue cannot see it —
reason 3 stands whole and the tap is still the only writer.

**ADR 0151 §4 — "never advances — STRUCK" — SUPERSEDED.** Its stated
hazard was choosing the wrong signal: "choose wrong and a live ticket's
alerts are killed silently". The signal chosen is the narrowest one that
exists — the venue's settlement of *this* market — and a ticket the venue
has settled has no live alerts to kill.

## 3. The three decisions the ticket left to main

### 3.1 Where the pass runs: the watcher's cycle, BEFORE the live gate

`hedge_watch.watch_hedges_forever` runs `close_settled_combinations` at the
top of every cycle, ahead of `anything_in_progress`. That gate is true only
while an open position has a pending leg whose game has started — which is
false exactly when every leg has resolved, the common state of a
combination the venue has settled (36 of 43 open rows on 2026-09-22 03:55Z
carried a venue settlement with all legs resolved). A pass behind the gate
would close settled rows only while some *other* ticket was live, and a
desk with nothing live would keep dead rows open indefinitely.

Cadence: the idle interval (600 s) when nothing is live, the watch
interval (60 s) when something is, against a settlement mirror
`poll_portfolio_forever` refreshes every 300 s. So the record lags the
venue by at most ~15 minutes on a quiet desk (300 s mirror + 600 s tick).

**The pass has its own exception handler, not the cycle's.** The runtime
review before merge found that `busy` is decided *after* the pass, so a
raise shared with the cycle's handler would skip `watch_once` — no
settle, no re-price, no push — and force the idle sleep while a game was
live: a `database is locked` against the 300 s portfolio poller would
have silently disabled hedge alerting for as long as it persisted. A
failed close pass now costs that cycle's closes and nothing else, and
`close_position` commits per row, so a mid-list failure keeps the rows
already closed. Pinned by a test that makes the pass raise on a live
ticket and asserts the 60 s cadence.

Rejected: `build_payload` (a read path must not write, and two existing
tests reach a venue-settled position through it asserting its legs stay
pending); the runner's market-results pass (it writes
`kalshi_markets.result`, the leg input, and never sees `venue_settlements`);
inside `watch_once` (behind the gate — the failure above).

### 3.2 Provenance: one writer, a required argument, a new column

`close_position(conn, *, position_id, now_ms, status, source)` —
`source ∈ {'venue', 'manual'}`, raising on anything else, and a missing
`source` is a `TypeError` at the call site. The same shape, and the same
two words, as `resolve_leg(..., source)` one table down. One writer rather
than a sibling function, so the `status = 'open'` guard and the `rowcount`
contract exist once.

Schema v54 adds `parlay_positions.closed_source TEXT CHECK (closed_source
IS NULL OR closed_source IN ('venue', 'manual'))`. The CHECK rides the
column declaration because a table-level CHECK cannot be added by
`ALTER TABLE` (v51's reason, `backend/store/db.py`). **That is also why the
legs' invariant `(outcome = 'pending') = (resolved_source IS NULL)` has no
twin on this table:** it would read `(status = 'open') = (closed_source IS
NULL)`, every row closed before v54 violates it, and it could only be added
by rebuilding the table that holds the live money record. The writer
enforces it instead. State this asymmetry rather than "fixing" it.

**No backfill.** A row closed before v54 reads `closed_source = NULL`,
"not recorded". Before v54 the tap was the only production writer we know
of, but that is an inference about the past and the column records facts
about the present — the v52 precedent (`scout_state`) word for word.

`status` on a venue close is `'settled'` — Joe's word in #131, already in
the CHECK. `closed_ms` is when the *record* closed (the pass's `now_ms`),
not when the venue settled: the venue's `settled_ms` and `market_result`
are already served on the row by the same join, so the settlement is
stamped by reference, not copied into a second place that could drift.

### 3.3 Trigger: the venue's settlement of the combination, read once

A `venue_settlements` row whose `ticker` equals the position's
`combo_ticker`, read through the existing `combo_settlements` lookup —
the same one `build_payload` uses for the screen's `venue_settlement`
field and its `nothing_pending` branch — so the screen and the record
cannot disagree about which rows the venue has settled.

It is deliberately **narrower** than the screen's `nothing_pending`
predicate, which also fires on `pending_legs == 0`. Every leg having
resolved is the desk's own reading and does not close a row (option B).
Do not "harmonise" the two predicates; the difference is the decision.

Hand-recorded slips are excluded **by construction**: `record_position`
defaults `combo_ticker` to `None` on the hand-typed route, and NULL cannot
join `venue_settlements.ticker`. No second filter, nothing to drift.

## 4. Consequences, stated so nobody re-derives them

- **A closed row is displayed nowhere.** `open_positions` (`WHERE status =
  'open'`) is the only reader of `parlay_positions.status` in `backend/`.
  The first pass after this deploys empties the settled group on `/hedge`
  of every venue-settled combination. Joe chose (A) knowing the collapsed
  group empties; the rows are in the table, not deleted, readable with
  `scripts/inspect_live_db.py` if a screen for them is ever wanted (it is
  not a ticket).
- **No push announces a venue close.** `Alerter.position_states` reads the
  served screen, and a closed row is not on it. A push here would be a
  nudge about money that has already left the table; nothing is added.
- **The comments that said "never auto-closes" changed in the same commit**
  (`backend/hedge.py` `serialise_position`, `HedgePositions.tsx`, `api.ts`,
  three test docstrings), per the rule that the fix and the words ship
  together or the words lie in the interval.
- **`gate.py` still reads none of this** (ADR 0063). A venue close moves no
  interlock.
- **No performance claim.** `watched_tickers` is bounded by pending legs,
  not open positions, and `/api/hedge` answered in 0.33 s at 43 rows. The
  reason for this change is that Joe asked, and the record should say
  what the venue says.

## 5. What is pinned

`tests/test_a_venue_settled_combination_closes_its_own_row.py` — (i) the
close with venue provenance and its absence from the payload; (ii) a
hand-recorded slip untouched; (iii) all-legs-resolved is not the trigger;
(iv) no leg marked; (v) the tap writes `'manual'`, an unknown or missing
`source` is refused; (vi) an idle cycle still closes, and the call
textually precedes the gate; (vii) a v53 volume migrates with NULL on its
old closed row; (viii) a raising close pass on a live ticket still yields
the 60 s cycle. Four mutations went red and were restored by file copy:
the settlement predicate removed (every combination closed) → the
leaves-alone tests; the pass moved behind the gate → (vi); the
`closed_source` write dropped → the provenance tests; the pass's own
handler folded into the cycle's → (viii).

## 6. Not decided here

- Anything about selling the combination back (ADR 0164/0165) — a close in
  the record is not an exit at the venue.
- A screen for closed rows.
- Closing a `sportsbook`-source position on any signal; the venue has no
  view of it.
