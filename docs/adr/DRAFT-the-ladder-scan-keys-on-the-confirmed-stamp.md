# ADR DRAFT — The ladder scan keys on the confirmed stamp

**Status:** Accepted, 2026-09-10.
**Date:** 2026-09-10.
**Extends ADR 0133** (`fair_prices` dedupe: `computed_ms` freezes at first
appearance, `confirmed_ms` moves on a re-derived, unchanged consensus).
Corrects the interim floor ADR 0133 shipped alongside that dedupe.

## 1. The finding, measured on live tonight

`CANDIDATE_SQL` in `backend/parlays.py` (imported by `ladder_candidates`,
served by `GET /api/parlays` and `POST /api/parlays/lookup`, and run again
inside `scripts/run_loop.py`'s pricing pass) predicated its freshness floor on
`f.computed_ms >= ?` alone. ADR 0133 broke the invariant that predicate relied
on — a row confirmed fresh every pass can carry a `computed_ms` from whenever
its payload first appeared, which can be days before kickoff — and shipped a
stopgap: `_CANDIDATE_SCAN_DEDUPE_FLOOR_MS`, a flat 9-day floor `max()`-combined
with the existing 8×`max_odds_age_ms` term, wide enough that a confirmed row's
stale `computed_ms` would still fall inside the scan.

That stopgap was itself the defect. Widening the floor to 9 days does not
narrow what the scan reads to confirmed rows — it widens what `idx_fair_
market_computed` has to seek through to *every* row, confirmed or not, whose
`computed_ms` falls in the last nine days. Measured live tonight:

    rows pulled through idx_fair_market_computed     6,561,382
    runner RSS, per pass                             196 MB -> 1.2 GB
    candidate_ms (P/api/parlays candidate scan)       83ms -> ~4,600ms
    OOM kills, this incident                          3

The 2 GB box could not hold the join `ROW_NUMBER() OVER (...)` materialises
under `PRAGMA temp_store = MEMORY`, once the input set is measured in
millions rather than thousands of rows.

## 2. The fix

The predicate becomes a disjunction over both stamps:

```sql
AND (f.computed_ms >= ? OR f.confirmed_ms >= ?)
```

with a new partial index so the second arm seeks instead of falling back to a
scan:

```sql
CREATE INDEX IF NOT EXISTS idx_fair_market_confirmed
    ON fair_prices(market, confirmed_ms DESC)
    WHERE confirmed_ms IS NOT NULL;
```

`EXPLAIN QUERY PLAN` on a database built from the real schema:

    MULTI-INDEX OR
    INDEX 1
    SEARCH f USING INDEX idx_fair_market_computed (market=? AND computed_ms>?)
    INDEX 2
    SEARCH f USING INDEX idx_fair_market_confirmed (market=? AND confirmed_ms>?)

With the index dropped, SQLite's OR-optimisation requires *every* arm to be
indexed to fire at all — losing one loses the whole plan, not half of it. The
degraded plan (measured, reproduced by `TestTheConfirmedIndexIsLoadBearing`):

    SEARCH f USING INDEX idx_fair_market_computed (market=?)

`computed_ms>?` is gone entirely — demoted from an index bound to a residual
row-by-row filter — which is the shape that produced the 6.5M-row read above.

With the fix, `_CANDIDATE_SCAN_DEDUPE_FLOOR_MS` is deleted outright and the
scan floor returns to `max(8 * max_odds_age_ms, 2h)` — two hours at deployed
values, not nine days. The multiple-of-`max_odds_age_ms` term is sufficient
again on its own, because the thing it was insufficient FOR (a confirmed row
whose `computed_ms` predates the floor) is now found by the OR's other arm
instead of by widening the floor.

Schema: `SCHEMA_VERSION` 36 -> 37. v37 adds `idx_fair_market_confirmed` as a
migration step (following v31's pattern: `schema.sql`'s `CREATE INDEX IF NOT
EXISTS` alone would silently reach the live volume with no way for
`scripts/migrate_db.py`'s boot-time check to *verify* it did, so the step and
its declared `indexes` tuple exist to make that check possible, not to be the
only route the index takes there).

## 3. Why the OR is exact, not an approximation

`confirmed_ms >= computed_ms` whenever `confirmed_ms` is set (`write_fair_price`
only ever advances it forward from the row's own `computed_ms`), so

    computed_ms >= ? OR confirmed_ms >= ?
    ≡ COALESCE(confirmed_ms, computed_ms) >= ?

exactly, for every row. The right side is what `_live_age_ms` already computes
in Python (`backend/parlays.py`); the left side is the same test, restated as
an OR because SQLite cannot seek an index on a `COALESCE(...)` expression —
that would force a full scan of `f` regardless of what indexes exist, since
the planner cannot push a computed column through to an index's sort order.
The OR, by contrast, is sargable on both arms independently.

## 4. Alternatives not taken

**A single non-partial index, `(market, confirmed_ms DESC)` over every
row.** Rejected on cost, not correctness: `confirmed_ms` is `NULL` on every
row that has never been re-confirmed (every row before v36, and any row whose
payload has only ever appeared once since v36) — a large majority of the
table by ADR 0133's own duplication measurement. Indexing those rows anyway
means the CREATE at boot (`scripts/migrate_db.py`, ahead of uvicorn) sorts
essentially the whole 10-million-plus-row table under
`PRAGMA temp_store = MEMORY`, on the same box that OOM-killed three times
tonight reading a fraction of that many rows through a plain SEARCH. The
partial form (`WHERE confirmed_ms IS NOT NULL`) bounds the index by the count
of distinct `(link, market, outcome, point)` keys that have EVER been
re-confirmed — the recorder's own dedupe measurement puts that near the
duplicate-collapsed size of the table, not its raw row count — and the
recorder's frozen-row INSERT path (a payload seen for the first time) never
touches this index at all, only the UPDATE path that sets `confirmed_ms`
does. Less write amplification, a cheaper CREATE, and it seeks the same rows
the OR's second arm actually needs.

**Flipping `PRAGMA temp_store` from `MEMORY` to `FILE`.** Would have
converted the OOM into a disk-backed sort — survivable, but not fast, and not
a fix: the query would still read 6.5M rows every call. Also rejected because
the volume already carries a growth alarm (ADR 0095), and `temp_store = FILE`
moves the sort's working set onto that same disk, during the exact incident
where disk headroom is the thing in question. The right fix is reading fewer
rows, not surviving reading more of them slowly.

## 5. What this does not establish

Nothing about wall-clock time under load or under the recorder's write burst
— the plan is a precondition, not a measurement of `/api/parlays` on the live
box, the same caveat `tests/test_ladder_query_is_indexed.py`'s own module
docstring states for the index it sits beside. Nothing about `odds_snapshots`,
which has no retention rule and is out of scope here. Nothing about whether
`fair_prices` itself should eventually be pruned — the recorder's dedupe
(ADR 0133) already cut its growth rate; this ADR only stops the READ side
from paying for the rows dedupe already collapsed as if it had not.

## 6. Follow-on, not taken here

`backend/store/manual_orders.py`'s descriptive read of a single order's frozen
consensus (`build_estimate_summary` / the hand-bet audit path) reads
`f.computed_ms` through a `fair_price_id` foreign key — a point lookup, not a
scan with a freshness floor, so this defect does not reach it. But the same
COALESCE-as-OR identity would apply if that path ever needed to express "is
this consensus still live" rather than "what did it say when it was frozen".
Left to Lane D, which owns that file.

## 7. How this was verified

- **The predicate, behaviourally.** `TestAConfirmedRowIsScannedByItsConfirmedStamp`
  (`tests/test_parlays_api.py`): (a) a row confirmed 5 minutes ago with a
  9-day-old `computed_ms` reaches the pool at the deployed freshness rule;
  (b) the same row with both stamps 9 days stale does not; (c) the deleted
  floor constant is actually gone (`hasattr` false), not merely unused; (d)
  a row 3 days stale and never confirmed — inside the OLD 9-day floor,
  outside the new 2-hour one — does not reach the pool, called through the
  real `ladder_candidates` rather than by recomputing the horizon formula
  beside it (which would not observe a reinstated third term).
- **The plan.** `tests/test_ladder_query_is_indexed.py`'s
  `test_fair_prices_is_searched_not_scanned` now asserts both the
  `computed_ms>?` seek AND a `confirmed_ms>?` seek AND a `MULTI-INDEX OR`
  step. `TestTheConfirmedIndexIsLoadBearing` drops the new index on a fresh
  database and asserts the `computed_ms>?` bound is lost entirely — not
  merely degraded — which is what makes the index load-bearing rather than
  decorative.
- **The schema/migration contract.** `TestMigration` in `tests/test_store.py`
  is parametrised over `sorted(db._MIGRATIONS)` and covers v37 automatically;
  `test_the_schema_file_and_the_migrations_agree` and the ladder test's own
  `test_the_index_is_declared_in_the_schema` both pin that `schema.sql` and
  the migration step agree the index exists.
- **Three mutations, each watched red and reverted:**
  - Predicate reverted to `computed_ms` only (2 bound params against a
    3-param query) — `TestAConfirmedRowIsScannedByItsConfirmedStamp`
    tests (a) and (b) both fail with `sqlite3.ProgrammingError: Incorrect
    number of bindings supplied`.
  - `idx_fair_market_confirmed`'s `CREATE` removed from `schema.sql` (a
    fresh test database never runs the v37 migration step, only
    `executescript`, so this reproduces "the index never reached the
    volume") — `test_fair_prices_is_searched_not_scanned` fails, losing the
    `computed_ms>?` seek exactly as predicted in §2.
  - A 9-day term reinstated into `ladder_candidates`' `max()` — test (b) and
    test (d) both fail, each independently.
- `scripts/inspect_live_db_parlays.py`'s `_SQL_PARLAY_CANDIDATES` was kept
  byte-identical to `CANDIDATE_SQL`, pinned by
  `tests/test_inspect_live_db.py`, and its timing helper's parameter tuple
  gained the second floor value.

Full suite for the touched files:
`tests/test_ladder_query_is_indexed.py tests/test_parlays_api.py
tests/test_inspect_live_db.py tests/test_fair_price_dedupe.py
tests/test_store.py` — see the session record for the count.
