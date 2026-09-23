# 0182 — `odds_snapshots` keeps each game's closing lines after fourteen days, and nothing else

**Status:** Accepted on Joe's answer to #58, 2026-09-23 ~17:50Z and ~18:10Z. Numbered 0182 on `main` after `git fetch`, 0181 being the highest and no lane holding a DRAFT.
**Date:** 2026-09-23
**Schema:** none. The cursor lives in the existing `meta` table under `odds_snapshot_prune_cursor`.
**Tickets:** #58 (map #3)
**Amends:** `backend/store/retention.py`'s docstring, which put `odds_snapshots` out of scope when the table was 33.6 MiB
**Leaves standing:** ADR 0054 (the other retention windows); ADR 0133 (the `fair_prices` dedup); the `fair_prices` downsample stays off

---

## 1. What Joe decided

#58 asked what the plan was for the one large table with no retention rule.
The context: ~141 MB/day of growth that
`docs/measurements/2026-09-18-fair-prices-dedup-effect-result.md` §11.2 says
uses up the 4 GB box's residency advantage about two weeks after 09-18, so
around 10-02. He answered in session, in four parts:

1. **Prune before Oct 2.**
2. **Keep closing lines.** For a game past the window, keep each book's last
   sweep before kickoff and delete the in-between and in-play readings.
   Offered and not chosen: delete every row of an old game. That would have
   blanked the kickoff time on old bets and stopped CLV scoring on
   unscored ones, because five readers take `MIN(commence_ms)` from this
   table.
3. **14 days after kickoff.** 7 and 30 were offered.
4. **No `VACUUM` for now.** Offered and not chosen: one `VACUUM` in a quiet
   hour, with the desk offline for its duration.

## 2. The rule

`backend/store/odds_snapshot_prune.py`. For a game whose **latest** kickoff
is more than 14 days ago, it keeps:

- for every `(bookmaker, market, outcome_description)`, every row of that
  book's last read at or before kickoff. On a team market
  `outcome_description` is NULL, so this is the book's whole last sweep. On
  a prop it is the player, so each player keeps their own last line even when
  the book dropped them from its final sweep. An independent review found
  that before any run: keyed on `(bookmaker, market)` alone, a scratched
  player lost their only close;
- the game's lowest-`commence_ms` row, if no closing row already carries that
  value. This keeps each `MIN(commence_ms)` and lowest-kickoff `sport_key`
  reader (`scoring.py`, `gate.py`, `routers/ledger.py`, `routes.py`,
  `parlays.py`) returning the same value after the prune as before it.

It deletes everything else for that game.

## 3. How it runs

- Inside the full pass, after `retention.prune` and the downsample, behind
  the same `window_open` guard, so it never runs while a bettable window is
  open.
- 30 s of budget per full pass, set by `ODDS_SNAPSHOT_PRUNE_BUDGET_S`. One
  game per transaction, so a crash leaves the table partly pruned, which is
  the safe direction.
- It walks games by index seek on `idx_odds_sport_commence`, one cursor per
  sport kept in `meta`. It never uses `DISTINCT` or a full walk
  (`tests/test_odds_snapshot_prune.py::TestItSeeksRatherThanScans`).
- It has two refusals, the downsample's pattern: `ODDS_SNAPSHOT_PRUNE_ENABLED`
  and `ODDS_SNAPSHOT_PRUNE_DRY_RUN`. **The first deploy is enabled and
  dry**. The dry run counts the 25 oldest games each pass, logs how many of
  their rows it would delete, and never moves the stored cursor. It is
  capped because, uncapped, it would re-count the same games for its whole
  budget, before pricing, on every pass. Arming it means flipping `DRY_RUN` in `fly.live.toml`.
- Nothing on a disk threshold may set either flag.
- A prune failure is logged and rolled back, and the pass goes on to price.
  A malformed cursor entry restarts that sport's walk rather than raising.
- The budget is checked between games, so one slow game's delete can run
  past it. On the API side, a write waits up to `busy_timeout` (5 s) behind
  one game's delete.

## 4. What this does not do, and what it destroys

- **It does not shrink the file.** Freed pages are reused, so growth
  stops, but the file keeps its size until a `VACUUM`, which Joe declined
  for now.
- **It does not show the desk gets faster.** The residency argument was made
  on file size, and the file does not shrink.
- **It permanently destroys** line-movement history for games past the
  window, and with it the ability to reconstruct per-pass
  `oldest_book_age_ms` that the dedup registration's §7.3 said depended on
  this table having no retention rule. Joe accepted that when he chose the
  closing-line option.
- **The backlog clears at an unmeasured rate.** On 2026-08-19 a live delete
  batch on `kalshi_quotes` ran at roughly 1,000 rows/s. At 30 s per 900 s
  pass, skipped while a window is open, the whole history may take days to
  clear. That is acceptable, because growth stops as soon as pages start
  coming free. If the dry run shows the rate is too slow, the budget is a
  config value to raise.

## 5. Verification

`tests/test_odds_snapshot_prune.py`, 14 tests. Eight guards were each
removed in turn, and each removal turned a test red:

- in-play rows counted as the close;
- no lowest-kickoff keeper;
- the lowest-kickoff row kept always;
- the dry run deleting;
- no skip for a moved kickoff;
- the cursor not advancing;
- the closing line keyed without the player;
- the dry run uncapped.
