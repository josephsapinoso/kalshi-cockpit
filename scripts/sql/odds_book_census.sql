-- How many books did sharp anchoring actually discard, ON THE RECORD'S OWN ROWS?
--
-- ADR 0021 §7.2 -- the strongest objection to this project's own refutation --
-- says the anchoring "discards a median of 26 of 29 usable books". That number
-- is measured on tests/fixtures/odds_mlb_h2h_spreads_totals.json, captured
-- 2026-08-07T13:49:22Z, which overlaps the record on 0 of 1,564 rows (minimum
-- gap 5.65 hours). See the annotation in ADR 0021 §7.2.
--
-- odds_snapshots is append-only and stores EVERY book (schema.sql:189-207).
-- Sharp anchoring is a READ-time filter (runner.py:658 -> devig.py:290-291),
-- not a write-time discard. So this is answerable at zero Odds API credits.
--
-- SHARP_BOOKS is read from runner.py:103 and pinned here. If that set ever
-- changes, this file is wrong and must be re-derived, not adjusted.
--
-- WHAT THIS DOES NOT ESTABLISH
--   - It is a census of the odds we STORED, not of the books that existed.
--   - `market='h2h'` only. Spreads and totals are excluded because the
--     recommendation engine has never written a row about either.
--   - It says nothing about whether the sharp books are RIGHT, only how many
--     were dropped and how often the filter bound at all.

.mode column
.headers on

-- ---------------------------------------------------------------------------
-- Q1. The headline: books available vs books kept, per event-instant.
-- ---------------------------------------------------------------------------
SELECT '=== Q1  books available vs kept, per (event, fetch) ===' AS q;

WITH per_instant AS (
  SELECT odds_event_id,
         fetched_ms,
         COUNT(DISTINCT bookmaker) AS n_all,
         COUNT(DISTINCT CASE WHEN bookmaker IN
              ('pinnacle','betfair_ex_eu','betfair_ex_uk','matchbook')
              THEN bookmaker END) AS n_sharp
  FROM odds_snapshots
  WHERE market = 'h2h'
  GROUP BY odds_event_id, fetched_ms
)
SELECT COUNT(*)        AS n_instants,
       MIN(n_all)      AS min_books,
       MAX(n_all)      AS max_books,
       ROUND(AVG(n_all),2)   AS mean_books,
       MIN(n_sharp)    AS min_sharp,
       MAX(n_sharp)    AS max_sharp,
       ROUND(AVG(n_sharp),2) AS mean_sharp,
       ROUND(AVG(n_all - n_sharp),2) AS mean_discarded
FROM per_instant;

-- ---------------------------------------------------------------------------
-- Q2. The full distribution. A mean is not a finding until the parts agree.
-- ---------------------------------------------------------------------------
SELECT '=== Q2  distribution of (books available, sharp kept) ===' AS q;

WITH per_instant AS (
  SELECT odds_event_id, fetched_ms,
         COUNT(DISTINCT bookmaker) AS n_all,
         COUNT(DISTINCT CASE WHEN bookmaker IN
              ('pinnacle','betfair_ex_eu','betfair_ex_uk','matchbook')
              THEN bookmaker END) AS n_sharp
  FROM odds_snapshots WHERE market = 'h2h'
  GROUP BY odds_event_id, fetched_ms
)
SELECT n_all, n_sharp, (n_all - n_sharp) AS discarded, COUNT(*) AS instants
FROM per_instant
GROUP BY n_all, n_sharp
ORDER BY instants DESC
LIMIT 30;

-- ---------------------------------------------------------------------------
-- Q3. THE ONE THAT MATTERS MOST.
--
-- devig.py takes `sharp or usable` -- anchoring is ATTEMPTED every row, but
-- whether it BINDS is data. Where no sharp book quoted, the row was priced
-- against the WIDE consensus, which is exactly what ADR 0021 Option B proposes
-- to test. If n_sharp = 0 is common, §7.2's tautology objection is weaker than
-- it looks, because the comparison was not always against sharps at all.
-- ---------------------------------------------------------------------------
SELECT '=== Q3  how often did anchoring actually BIND? ===' AS q;

WITH per_instant AS (
  SELECT odds_event_id, fetched_ms,
         COUNT(DISTINCT CASE WHEN bookmaker IN
              ('pinnacle','betfair_ex_eu','betfair_ex_uk','matchbook')
              THEN bookmaker END) AS n_sharp
  FROM odds_snapshots WHERE market = 'h2h'
  GROUP BY odds_event_id, fetched_ms
)
SELECT CASE WHEN n_sharp = 0 THEN 'NO sharp book -- priced on the WIDE consensus'
            ELSE 'anchored on ' || n_sharp || ' sharp book(s)' END AS outcome,
       COUNT(*) AS instants,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM per_instant), 1) AS pct
FROM per_instant
GROUP BY n_sharp
ORDER BY n_sharp;

-- ---------------------------------------------------------------------------
-- Q4. Which sharp books actually turn up, and how often.
-- ---------------------------------------------------------------------------
SELECT '=== Q4  sharp book coverage ===' AS q;

SELECT bookmaker,
       COUNT(DISTINCT odds_event_id) AS events,
       COUNT(*) AS quotes
FROM odds_snapshots
WHERE market = 'h2h'
  AND bookmaker IN ('pinnacle','betfair_ex_eu','betfair_ex_uk','matchbook')
GROUP BY bookmaker
ORDER BY quotes DESC;

-- ---------------------------------------------------------------------------
-- Q5. Scope check -- is this census even about the record's population?
-- ---------------------------------------------------------------------------
SELECT '=== Q5  window and volume ===' AS q;

SELECT COUNT(*) AS rows_h2h,
       COUNT(DISTINCT odds_event_id) AS events,
       COUNT(DISTINCT bookmaker) AS distinct_books,
       datetime(MIN(fetched_ms)/1000,'unixepoch') AS first_fetch_utc,
       datetime(MAX(fetched_ms)/1000,'unixepoch') AS last_fetch_utc
FROM odds_snapshots WHERE market = 'h2h';

-- ===========================================================================
-- AMENDMENT 2026-08-10 -- this file's unit is wrong for the claim it answers,
-- and two of its headline numbers must not be quoted about the record.
--
-- Audited and re-run against the LIVE database, read-only. Full result:
--   docs/measurements/2026-08-10-sharp-anchoring-on-the-record-result.md
--   docs/measurements/2026-08-10-sharp-anchoring-census.py   (the harness)
--   docs/measurements/2026-08-10-sharp-anchoring-on-the-record-run.txt
--
-- WHAT WAS WRONG WITH Q1-Q4, AND IT IS THE UNIT, NOT THE ARITHMETIC
--
--   Q1-Q4 group by (odds_event_id, fetched_ms). That weights a fetch instant
--   that produced 2 recommendation rows equally with one that produced 44, and
--   it counts 62 instants of 234 that the runner NEVER READ -- `runner.py:227`
--   reads only `MAX(fetched_ms)`, one sweep, so a stored instant only enters
--   the record if a pass happened to land after it and before the next sweep.
--
--   ADR 0021 section 7.2 is a claim about the RECORD'S ROWS. The unit must be
--   the row. Per row, over the pinned 1,564:
--
--     Q1's "median 20 discarded of 23 available"  ->  median 19 of 21 usable
--     Q3's "23.1% had no sharp book"              ->  27.0% of rows (423/1564)
--
--   Both original figures are correct about stored instants. Neither may be
--   quoted about the record. See Q6 and Q7 below for the row-unit versions.
--
--   Q1's "available" is also not `usable`. `usable` in devig.py means books
--   that quoted every outcome and survived devig. On this record that is the
--   full book set minus 12 partial-quote drops across 3 instants, and devig
--   rejected nothing -- verified by reproducing `fair_prices.books_used` from
--   these snapshots on 21,550 of 21,550 h2h rows.
--
-- WHAT SURVIVED UNCHANGED
--   Q4: `betfair_ex_uk` is absent -- 0 rows, ALL markets, the whole window.
--   `SHARP_BOOKS` has four members and three reachable ones. `max sharp = 3`
--   on all 234 instants and 4 on none. The CAUSE is not established; see the
--   result document. Do not "fix" it by adding the uk region.
--   Q5: the scope is the same population as the record, and this is now proven
--   at row level rather than by window overlap -- see Q8.
--
-- STILL TRUE OF EVERYTHING BELOW, INCLUDING THE NEW QUERIES
--   - Census of the odds we STORED, not of the books that existed.
--   - `market='h2h'` only. `fair_prices` is 100% h2h; the engine has never
--     written a fair price about a spread or a total.
--   - Says nothing about whether the sharp books are RIGHT.
--   - No test, no interval, no threshold anywhere in this file. Every figure
--     is a complete enumeration of a fixed population.
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- Q6. THE ROW UNIT. What the anchoring discarded on the record's own rows.
--
-- Each recommendation read the latest odds instant at or before its
-- `created_ms`, for its own fixture. That is reconstructed here exactly as
-- `book_quotes_for_event` does it. Pinned to id <= 1564 so the population is
-- the same 1,564 rows as 2026-08-10-clean-shortfall-pull.json.
--
-- Expected: median usable 21, median kept 2, median discarded 19.
-- ---------------------------------------------------------------------------
SELECT '=== Q6  books usable vs kept, PER RECOMMENDATION ROW ===' AS q;

WITH rec AS (
  SELECT r.id AS rid, r.created_ms, e.odds_event_id AS oe
  FROM recommendations r
  JOIN event_links e ON e.id = r.link_id
  WHERE r.id <= 1564
),
read_instant AS (
  SELECT rec.rid, rec.oe,
         (SELECT MAX(s.fetched_ms) FROM odds_snapshots s
           WHERE s.odds_event_id = rec.oe AND s.market = 'h2h'
             AND s.fetched_ms <= rec.created_ms) AS fm
  FROM rec
),
counted AS (
  SELECT ri.rid,
         COUNT(DISTINCT s.bookmaker) AS n_all,
         COUNT(DISTINCT CASE WHEN s.bookmaker IN
              ('pinnacle','betfair_ex_eu','betfair_ex_uk','matchbook')
              THEN s.bookmaker END) AS n_sharp
  FROM read_instant ri
  JOIN odds_snapshots s
    ON s.odds_event_id = ri.oe AND s.market = 'h2h' AND s.fetched_ms = ri.fm
  GROUP BY ri.rid
)
SELECT COUNT(*) AS n_rows,
       MIN(n_all) AS min_books, MAX(n_all) AS max_books,
       MIN(n_sharp) AS min_sharp, MAX(n_sharp) AS max_sharp,
       ROUND(AVG(n_all - n_sharp), 2) AS mean_discarded
FROM counted;

-- ---------------------------------------------------------------------------
-- Q7. THE ONE THAT MATTERS, on the record rather than on instants.
--
-- `fair_prices.anchored_on_sharp` answers Q3 directly and always has -- it is
-- written on every row (`runner.py:360`). It is on `fair_prices`, NOT on
-- `recommendations`, which is why the /api/ledger pull could not see it.
--
-- Expected: anchored 1 -> 1,141 rows (73.0%); anchored 0 -> 423 (27.0%).
-- Of the 614 unsuppressed rows: 425 anchored, 189 not. Positive edges among
-- the unsuppressed: 0 on BOTH sides.
-- ---------------------------------------------------------------------------
SELECT '=== Q7  did anchoring bind, PER ROW, and did those rows survive? ===' AS q;

SELECT f.anchored_on_sharp                       AS anchored,
       COUNT(*)                                  AS rows_,
       ROUND(100.0 * COUNT(*) / 1564, 1)         AS pct_of_record,
       COUNT(DISTINCT r.link_id)                 AS links,
       COUNT(DISTINCT r.created_ms - r.odds_age_ms) AS distinct_odds_observations,
       SUM(r.suppressed_reason IS NULL)          AS clean_rows,
       SUM(r.edge_tenths > 0)                    AS positive_edge_rows,
       SUM(r.reference_contracts > 0)            AS actionable_rows,
       ROUND(AVG(f.book_count), 1)               AS mean_books_in_consensus
FROM recommendations r
JOIN fair_prices f ON f.id = r.fair_price_id
WHERE r.id <= 1564
GROUP BY f.anchored_on_sharp;

-- ---------------------------------------------------------------------------
-- Q8. SCOPE, proven at row level rather than by window overlap.
--
-- Q5 compares `fetched_ms` against the record and appears to miss by 5m15s.
-- It does not: `odds_age_ms` is measured from the BOOK's own stamp, so the
-- right comparison is `book_updated_ms`, whose minimum equals the record's
-- earliest odds observation TO THE SECOND (2026-08-07 19:28:12).
--
-- The exact version -- `created_ms - odds_age_ms` reconstructed from these
-- snapshots, 1,564 of 1,564 matched, zero mismatches -- needs the oldest stamp
-- among books quoting EVERY outcome, which is awkward in SQL and is done in
-- the Python harness. This query is the cheap check that must pass first.
-- ---------------------------------------------------------------------------
SELECT '=== Q8  scope: book stamps, not fetch stamps ===' AS q;

SELECT datetime(MIN(book_updated_ms)/1000,'unixepoch') AS first_book_stamp,
       datetime(MAX(book_updated_ms)/1000,'unixepoch') AS last_book_stamp,
       SUM(book_updated_ms IS NULL)                    AS null_stamps
FROM odds_snapshots WHERE market = 'h2h';

SELECT datetime(MIN(created_ms - odds_age_ms)/1000,'unixepoch') AS first_record_obs,
       datetime(MAX(created_ms - odds_age_ms)/1000,'unixepoch') AS last_record_obs,
       COUNT(DISTINCT created_ms - odds_age_ms)                 AS distinct_obs,
       COUNT(DISTINCT created_ms)                               AS runner_cycles,
       COUNT(*)                                                 AS rows_
FROM recommendations WHERE id <= 1564;

-- ---------------------------------------------------------------------------
-- Q9. `betfair_ex_uk` across ALL markets and the whole window. Expected: 0.
-- Q4 restricts to h2h, which cannot tell "absent" from "absent here".
-- ---------------------------------------------------------------------------
SELECT '=== Q9  betfair_ex_uk, all markets, whole window ===' AS q;

SELECT COUNT(*) AS rows_ever FROM odds_snapshots WHERE bookmaker = 'betfair_ex_uk';

SELECT bookmaker, COUNT(*) AS rows_
FROM odds_snapshots
WHERE bookmaker LIKE '%betfair%'
GROUP BY bookmaker;

-- ---------------------------------------------------------------------------
-- NEGATIVE CONTROLS, run 2026-08-10. Every one of these was executed and
-- watched. A query nobody has seen fail is decoration.
--
--   A. sharp list as shipped        -> max_sharp 3, mean_discarded 18.98
--   B. betfair_ex_uk REMOVED        -> BYTE-IDENTICAL TO A
--   C. draftkings ADDED             -> max_sharp 4, mean_discarded 18.00
--   D. Q7 joined f.id = r.link_id   -> 981 / 583   (nonsense, as intended)
--   E. Q7 with the id<=1564 pin off -> 452 / 1226, "107.3%" of 1564
--
-- B is the one to remember. Q1-Q6 CANNOT tell a SHARP_BOOKS containing
-- `betfair_ex_uk` from one without it -- the answers are identical, because
-- the book never appears. That is the same blind spot as anchoring a
-- definitional test at the one value where both candidate conventions agree.
-- Q9 exists solely because it is the only query here that can tell "absent"
-- from "not asked for". Do not delete it as redundant with Q4.
-- ---------------------------------------------------------------------------
