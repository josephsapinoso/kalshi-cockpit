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
