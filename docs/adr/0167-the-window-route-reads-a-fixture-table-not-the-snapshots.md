# ADR 0167 — `/api/window` reads a fixture table, not the snapshots

- **Status:** accepted
- **Date:** 2026-09-18
- **Decider:** the session, on Joe's errand — "The site is being really slow
  again please make it faster." Joe named the symptom; the diagnosis and the
  shape of the fix are the session's, and he oversees.
- **Amends** the v41 justification beside `idx_odds_window` in `schema.sql`
  (kept verbatim: the index is still required, it just no longer bounds the
  cost) and the docstrings of `odds/timing.py::upcoming_fixtures_by_sport`
  and `::fixture_freshness`. Extends ADR 0141 (a plan diff cannot price an
  index) to a statement rewrite: the number in the record is a time, taken
  round-robin, with the answers compared first.

## The decision

`odds_snapshots` gets a companion table, **`odds_fixtures`**, one row per
sportsbook fixture — `odds_event_id`, `sport_key`, `commence_ms`,
`home_team`, `away_team`, `last_fetched_ms` — **kept by an `AFTER INSERT`
trigger on `odds_snapshots`**, latest `fetched_ms` winning. Schema v47
creates it, indexes it on `(commence_ms, sport_key)`, and backfills it once
from every snapshot whose kickoff is within seven days before the migration
ran or later.

Both of `/api/window`'s fixture reads are rewritten to drive from it:

- `upcoming_fixtures_by_sport` is one range seek on the fixture table.
- `fixture_freshness` is that seek, and per fixture two covering seeks on
  `idx_odds_window` with `odds_event_id` bound.

Nothing else changes. The snapshot table, its five indexes, its writers and
every other reader are untouched; the trigger is the only new write.

## Why

Every server-rendered page (`board`, `parlays`, `picks`, `slate`) awaits
`/api/window` before it can render, and on the evening of 2026-09-17 that
route measured **7.0 s at the median on a warm box** and tripped the 25 s
read budget twice. The pages measured 8-15 s; one Board load took 60 s. The
measurement, the plans and the rehearsal are in
`docs/measurements/2026-09-18-the-window-route-walked-every-odds-row.md`.

The cause is a shape, not a bug. Both reads answered "which fixtures are
upcoming" by consulting `odds_snapshots` — a table with one row per (sweep,
book, market, outcome) — so their cost was proportional to the rows stored
for upcoming fixtures, not to the fixtures. v41 (`idx_odds_window`) made
`fixture_freshness`'s walk covering, which bought 5x and left the walk
growing with every sweep. By 2026-09-17, with the NFL and NCAAF weekends
inside the 48 h horizon, the walk was most of the table, and the route is
polled every three seconds by every open tab, so the walk ran continuously
and streamed that index through a page cache that holds half the file.

**A per-fixture table is the only shape whose cost is the fixture count.**
Every alternative considered still touched the snapshot rows:

| considered | why not |
|---|---|
| a covering index leading on `commence_ms` for `upcoming_fixtures_by_sport` | still N upcoming rows, then `DISTINCT` |
| a `(market, commence_ms, ...)` index for `fixture_freshness` | refused by the planner, measured for v41 |
| an in-process TTL cache on `/api/window` | hides the cost; `timing.py:967` refused a cached schedule on 2026-08 for the reason that a cached schedule is wrong after a sweep; and the first tap still pays |
| reading `kalshi_events` instead | its clock is three hours late (ADR 0006), the reason the module exists |

## Why a trigger and not a writer

`store_quotes` is not the only path that inserts snapshot rows: `seed_demo.py`
does, and so does every test that seeds a slate by hand (five files, ten
`INSERT INTO odds_snapshots` sites). A table one writer forgets to keep is the
drift the runner would then schedule against, silently, and this repo has
already recorded four modules that were "built but never called". The
trigger makes the invariant the database's: a snapshot row cannot exist
without its fixture row. Measured cost, a 900-row sweep insert: 5.2 ms ->
10.1 ms, against a quote pass measured in seconds.

**Latest sweep wins, not `MIN(commence_ms)`.** The slate, the ledger and the
scorer take `MIN(commence_ms)` over the snapshots (ticket #26's definition)
and must agree with each other; this table is not for them. It is the
schedule's view, and a schedule wants the feed's current belief: a postponed
game moves here on the next sweep that quotes it, and a late-arriving old
row cannot move it back (`WHERE excluded.last_fetched_ms >= ...`). One
visible consequence: a fixture whose kickoff moved appears once, at the
latest kickoff, where the old `DISTINCT` listed every kickoff it had ever
carried. Tested at the trigger; not tested through the planner.

## Why the backfill is bounded

The only readers ask about kickoffs at or after now. Seeding history would
walk the whole 6.3 GB table at boot, under a 600 s health grace, on the one
volume that cannot be recreated, for rows nothing reads. The floor is seven
days before the migration runs, so a fixture that kicked off last week and
is still being quoted is present. Rehearsed at live's shape: 632 ms, resident
set unchanged, plan a skip-scan on `idx_odds_sport_commence` with no temp
b-tree — the 2026-09-10 hazard (a scan whose output is small but whose input
is materialised) does not apply. `last_fetched_ms` is seeded as 0 so the
first live sweep overwrites the seeded kickoff.

## What was rehearsed, and what is still owed

Local, live-shaped (3.6M rows, 800 upcoming), warm, round-robin, five rounds,
answers compared elementwise and equal first:

    fixture_freshness          995 ms -> 24 ms    42x
    upcoming_fixtures_by_sport 1.2 ms -> 0.1 ms   10x

**That was a floor and a direction, not the live number.** Deployed as
`31b6e85`, migrated v46 -> v47 on the volume in 31 s, and re-timed with
`scripts/time_live_routes.py` (§D of the measurement doc): `/api/window`
**6,974 ms -> 119 ms at the median, 58x**, on a just-restarted box; the
pages 9-15 s -> 0.45-0.8 s. The other routes recovered with it, and the
restart is a confound for those -- the ADR claims the window figure only.

## Guards, each disabled and watched go red

`tests/test_window_freshness_index.py`, rewritten from the v41 file (its
v41 guards kept; the ones that pinned the old statement's shape replaced by
the new claim), plus `tests/test_store.py`:

| mutation | what went red |
|---|---|
| trigger deleted from `schema.sql` | 8 tests: every equivalence, trigger and backfill test |
| trigger's `WHERE excluded.last_fetched_ms >= ...` removed | latest-sweep-wins |
| step 47 deleted from `_MIGRATIONS` | the module fails to import (`SCHEMA_VERSION` without its step) |
| `DROP TRIGGER` removed from the undo | 43 tests in `test_store.py`: every older step's undo strands behind the dangling trigger |
| the `is not None` filter removed | the no-h2h-rows equivalence test |
| the v41 statement put back | binds-the-event, fixtures-from-the-table, demotion demo |
| `idx_odds_fixtures_commence` deleted | fixtures-from-the-table (`SCAN f`) |
| `idx_odds_window` deleted | 9 tests, as under v41 |

Two guards were decoration on the first run and are recorded because the
mutation run is what said so: a test that pinned the ORDER of the two undo
drops stayed green with the order swapped (either order works; the claim is
that both happen), and the plan matcher knew the statement's aliases but not
the bare table name, so the v41 CTE arm — `SEARCH odds_snapshots` with no
alias — slipped past "every read binds the event". Both fixed and re-run.

## Consequences

- `/api/window`'s cost is now proportional to the fixture count. Whether
  that is what was binding the pages is §D's question; `/api/parlays` and
  `/api/slate` were also 4x their 2026-09-16 figures and do not read the
  window, so if they do not recover with it they are their own work.
- `odds_snapshots` still has no retention rule. This removes the window's
  dependence on its growth and nothing else's.
- `inspect_live_db.py window-freshness` still runs the v41-shaped statement
  (it is a retrospective at `--at` and cannot be served by a current-state
  table). It is now the slow path on live and should be run as one — once,
  deliberately, expecting the desk to be slow after it.
- `idx_odds_window` carries `commence_ms` for a range filter no statement
  applies any more. Dropping the column rebuilds a ~260 MB index at boot;
  that is a timed decision of its own and is not taken here.
