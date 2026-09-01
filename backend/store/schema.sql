-- Kalshi betting cockpit -- operational schema (SQLite).
--
-- This is the OLTP side: live state, written continuously, read by the Board
-- with low latency. The analytics side is Parquet + DuckDB + dbt, built from
-- snapshots of these tables. The split is deliberate -- one path optimised for
-- freshness, one for truth -- and the boundary is `store/publish.py`.
--
-- ============================================================================
-- CONVENTIONS. All of these exist because violating them cost something.
-- ============================================================================
--
-- PRICES are INTEGER tenths of a cent, 0..1000. Never float dollars, never
--   whole cents. ~25% of Kalshi markets tick in deci-cents, and half a cent is
--   an eighth of a typical edge. See backend/core/prices.py.
--
-- TIMES are INTEGER epoch milliseconds, UTC, always. Never local, never naive
--   ISO strings. The previous project parsed tz-aware timestamps and then
--   called .replace(tzinfo=None), which discards the offset rather than
--   converting it -- every "seconds to close" was wrong by the local UTC
--   offset. Integers cannot be wrong in that way.
--
-- QUANTITIES are REAL. Kalshi returns fractional sizes ("17.38"); 42 of 152
--   sampled order book levels were fractional. An INTEGER column here would
--   silently truncate depth.
--
-- UNREADABLE IS NULL, never 0. Zero is a legitimate price (a settled loser),
--   so a 0 written on a parse failure is indistinguishable from a real settled
--   market. Columns that can fail to parse are nullable and callers refuse.
--
-- ASKS ARE DERIVED, never stored as if published. Kalshi publishes YES bids
--   and NO bids only; yes_ask = 1000 - best_no_bid. We store the bids we were
--   actually sent and derive asks at read time, so a schema reader can never
--   mistake a derived number for a quoted one.

PRAGMA journal_mode = WAL;      -- concurrent reads while the ingest loop writes
PRAGMA foreign_keys = ON;
PRAGMA synchronous = NORMAL;    -- WAL + NORMAL is durable enough for a rebuildable cache

-- ============================================================================
-- Schema versioning
-- ============================================================================
-- Readers MUST branch on this. The previous project's recorder carried a `v`
-- field for exactly this reason: v1 stored whole cents and v2 stored tenths,
-- and reading a v1 record as v2 divides every price by ten -- silently, and in
-- the direction that makes everything look cheap.

CREATE TABLE IF NOT EXISTS meta (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_ms  INTEGER NOT NULL
);
-- **The `'1'` below is not this file's version.** The authority is
-- `db.SCHEMA_VERSION`, which is 6. `init_db` migrates, runs this script, and
-- then stamps `SCHEMA_VERSION` over whatever this line seeded, so the literal
-- is only ever a transient placeholder for a database being created fresh --
-- `INSERT OR IGNORE` makes it a no-op on every existing one. It is left as it
-- is because changing it changes stored data for no gain; read `db.py` for the
-- number, never this line.
INSERT OR IGNORE INTO meta (key, value, updated_ms) VALUES ('schema_version', '1', 0);

-- ============================================================================
-- Kalshi market universe
-- ============================================================================

CREATE TABLE IF NOT EXISTS kalshi_series (
    series_ticker   TEXT PRIMARY KEY,
    title           TEXT,
    category        TEXT,
    league          TEXT,           -- our normalised league key, NULL until mapped
    -- Whether this series carries per-GAME markets (the kind that map onto
    -- sportsbook h2h) as opposed to futures/season props. Resolved by the
    -- discovery spike; NULL means "not yet examined", not "no".
    has_game_markets INTEGER,       -- 0/1/NULL
    first_seen_ms   INTEGER NOT NULL,
    last_seen_ms    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS kalshi_events (
    event_ticker    TEXT PRIMARY KEY,
    series_ticker   TEXT REFERENCES kalshi_series(series_ticker),
    title           TEXT,
    category        TEXT,
    -- Scheduled start of the underlying game, when we can determine it. This
    -- is the join key against the sportsbook feed, so a NULL here means the
    -- event cannot be matched -- which is a reportable condition, not a
    -- silently-skipped row.
    commence_ms     INTEGER,
    close_ms        INTEGER,
    status          TEXT,           -- open | closed | settled | finalized
    first_seen_ms   INTEGER NOT NULL,
    last_seen_ms    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_commence ON kalshi_events(commence_ms);
CREATE INDEX IF NOT EXISTS idx_events_series ON kalshi_events(series_ticker);

CREATE TABLE IF NOT EXISTS kalshi_markets (
    ticker              TEXT PRIMARY KEY,
    event_ticker        TEXT REFERENCES kalshi_events(event_ticker),
    series_ticker       TEXT REFERENCES kalshi_series(series_ticker),
    title               TEXT,
    -- The team/side this contract's YES resolves to, normalised. NULL until
    -- the alias table can resolve it. Matching is deterministic and refuses to
    -- guess, so an unresolved side blocks the link rather than fuzzy-matching.
    yes_side_team       TEXT,
    -- moneyline | spread | total | team_total | prop. Nothing writes `future`,
    -- and non-fixture series are excluded upstream rather than labelled here.
    --
    -- This comment used to say nothing writes `prop` either, and that was true
    -- while `discovery._SUFFIX_TO_MARKET_TYPE` was the only producer -- its
    -- whole domain is the first four. There is now a second producer:
    -- `kalshi/props.PROP_SERIES`, an explicit five-series allowlist looked up
    -- by ticker rather than by suffix, because the five prop series share no
    -- suffix and Kalshi scopes them by the statistic instead of the fixture.
    market_type         TEXT,
    -- The spread/total line where applicable -- and, on a prop, Kalshi's
    -- `floor_strike`, which for an `N+` market is `N - 0.5`. That is exactly
    -- the `point` a sportsbook publishes for the same rung, so this column is
    -- what joins a prop to `odds_snapshots.outcome_point`, by equality and not
    -- by conversion. 259 of 259 on the captured prop fixture.
    strike              REAL,
    -- The player a prop resolves on, parsed from `yes_sub_title`
    -- ("Anthony Kay: 2+") and stored as Kalshi spells it. NULL on every team
    -- market, and NULL on a prop whose subtitle could not be read -- never a
    -- value invented from the title. Normalisation for matching lives in
    -- `kalshi/props.norm()`, deliberately not in this column, so the record
    -- keeps what was published.
    player_name         TEXT,
    -- Kalshi's own `price_level_structure`, stored verbatim. Three values have
    -- been observed, all of them on game markets:
    --
    --   linear_cent                  2,085 markets (ADR 0001); 321 in fixtures
    --   center_half_edge_half_cent      60 markets (ADR 0001)
    --   deci_cent                                    12 in fixtures
    --
    -- This comment previously read `cent | deci_cent | tapered_deci_cent`.
    -- `cent` and `tapered_deci_cent` appear in no captured payload, and
    -- `linear_cent` -- which is nearly every row -- was not listed at all.
    --
    -- It is a **label, never a branch**: the tradeable grid is parsed from
    -- `price_ranges` (`kalshi/grid.py`), so a structure name Kalshi introduces
    -- later costs nothing here. A reader that switched on this string would
    -- break on the next one.
    price_structure     TEXT,
    close_ms            INTEGER,
    status              TEXT,       -- settled markets report 'finalized', not 'settled'
    result              TEXT,       -- yes | no | NULL while open
    volume_24h          REAL,
    open_interest       REAL,
    first_seen_ms       INTEGER NOT NULL,
    last_seen_ms        INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_markets_event ON kalshi_markets(event_ticker);
CREATE INDEX IF NOT EXISTS idx_markets_status ON kalshi_markets(status);

-- ============================================================================
-- Kalshi quotes
-- ============================================================================
-- Only the two published sides are stored. yes_ask and no_ask are DERIVED at
-- read time as 1000 - the opposing bid; storing them would invite a reader to
-- treat a derived number as a quoted one, and would double-count staleness
-- (the derived level inherits its freshness from the underlying bid).

CREATE TABLE IF NOT EXISTS kalshi_quotes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL REFERENCES kalshi_markets(ticker),
    observed_ms     INTEGER NOT NULL,   -- when this price FIRST appeared
    -- When we last saw this same price still standing. ADR 0055: the table is
    -- a change log, so a row is written only when the quote moves and this
    -- column is bumped in place on every pass that re-confirms it.
    --
    -- `observed_ms` answers "how long has this price been here"; this answers
    -- "is it still good". Before ADR 0055 one column did both, which worked
    -- only because every pass wrote a duplicate row. Every staleness question
    -- reads this; every price-history question reads `observed_ms`.
    -- NULL on rows written before ADR 0055, hence COALESCE at every reader.
    confirmed_ms    INTEGER,
    -- Kalshi's own sequence number for the orderbook_delta stream. A gap means
    -- the book is corrupt and must be re-snapshotted; without this the book
    -- degrades permanently and silently. NULL for REST-sourced quotes.
    seq             INTEGER,
    source          TEXT NOT NULL,      -- ws | rest | candlestick
    yes_bid_tenths  INTEGER,
    yes_bid_qty     REAL,
    no_bid_tenths   INTEGER,
    no_bid_qty      REAL,
    CHECK (yes_bid_tenths IS NULL OR (yes_bid_tenths >= 0 AND yes_bid_tenths <= 1000)),
    CHECK (no_bid_tenths  IS NULL OR (no_bid_tenths  >= 0 AND no_bid_tenths  <= 1000))
);
CREATE INDEX IF NOT EXISTS idx_quotes_ticker_time ON kalshi_quotes(ticker, observed_ms DESC);

-- Closing quotes, read from the candlestick endpoint at a fixed horizon before
-- close. This is the CLV primitive -- the only way to read a PAST Kalshi quote.
-- Deliberately separate from kalshi_quotes because the horizon is part of the
-- measurement: a result that moves when you change `hours_before` was
-- convergence, not edge, and you can only detect that if the horizon is a
-- first-class column you can group by.
CREATE TABLE IF NOT EXISTS closing_lines (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker              TEXT NOT NULL REFERENCES kalshi_markets(ticker),
    horizon_hours       REAL NOT NULL,
    observed_ms         INTEGER NOT NULL,
    yes_bid_tenths      INTEGER,
    yes_ask_tenths      INTEGER,
    UNIQUE (ticker, horizon_hours)
);

-- ============================================================================
-- Sportsbook odds
-- ============================================================================
-- Stored RAW, one row per bookmaker per outcome. Devigging is a derived view,
-- never destructive: the moment we store only a consensus we lose the ability
-- to re-run with a different method, and method choice moves the answer by
-- more than the whole edge.

CREATE TABLE IF NOT EXISTS odds_snapshots (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    fetched_ms          INTEGER NOT NULL,   -- when WE fetched
    -- The bookmaker's own last_update. The gap between this and fetched_ms is
    -- the book's staleness, which is separate from ours and matters more.
    book_updated_ms     INTEGER,
    sport_key           TEXT NOT NULL,      -- e.g. americanfootball_nfl
    odds_event_id       TEXT NOT NULL,      -- The Odds API event id
    commence_ms         INTEGER NOT NULL,
    home_team           TEXT NOT NULL,
    away_team           TEXT NOT NULL,
    bookmaker           TEXT NOT NULL,      -- pinnacle | draftkings | ...
    market              TEXT NOT NULL,      -- h2h | spreads | totals | prop key
    outcome_name        TEXT NOT NULL,      -- team name, or Over/Under
    -- WHOSE Over/Under. NULL on every team market, and that is the point: a
    -- player prop's outcome is (player, side, line) and the first component has
    -- nowhere else to live. Folding it into `outcome_name` as "Holmes|Over"
    -- would make every existing query that compares `outcome_name` to a team
    -- name silently stop matching, and would put a parser in the read path.
    outcome_description TEXT,
    outcome_point       REAL,               -- spread/total/prop line
    price_decimal       REAL NOT NULL       -- decimal odds
);
-- Leads with `odds_event_id`, which is what lets the parlay ladder's fixture
-- lookup be a seek once its subquery is restricted to linked events.
--
-- **A second index on `(odds_event_id, commence_ms)` was added on 2026-08-26
-- and removed the same hour, because it changed no plan.** With it:
-- `SEARCH ... USING INDEX idx_odds_event_commence`. Without it:
-- `SEARCH ... USING INDEX idx_odds_event`. Identical shape -- the leading
-- column is all the equality needs. It would have cost write amplification on
-- the highest-volume table in the system to buy nothing, which is what an
-- index that changes no plan always is.
CREATE INDEX IF NOT EXISTS idx_odds_event ON odds_snapshots(odds_event_id, market, fetched_ms DESC);
CREATE INDEX IF NOT EXISTS idx_odds_commence ON odds_snapshots(commence_ms);
-- **And here is the index that DOES change the plan -- ADR 0086, schema v31.**
-- Read the refusal above first; this is not an exception to it, it is the same
-- test applied to a different candidate and coming out the other way.
--
-- `runner.MATCH_CANDIDATE_SQL` is
--
--     SELECT DISTINCT odds_event_id, commence_ms, home_team, away_team
--     FROM odds_snapshots WHERE sport_key = ? AND commence_ms >= ?
--
-- and `sport_key` appears in neither index above, so SQLite seeks
-- `idx_odds_commence` to the 24-hour floor and scans EVERY sport's rows
-- forward from there -- a range with no upper bound, because the predicate
-- deliberately keeps every future fixture -- fetching each row from the table
-- to test `sport_key`, then feeding the survivors through a temp B-tree for
-- the DISTINCT. On live 2026-08-30 that reached 27.7s; the pass took 104s, the
-- API's read connections starved behind it, and the Fly health check on port
-- 3000 failed at 22:06:03Z. `/api/market`, `/api/window` and `/api/scout` all
-- returned socket-hang-up in the same minute, which read from the outside as
-- "the scout desk returned 500".
--
-- **The covering form, not the narrow one, and the plans say why:**
--
--     baseline   SEARCH ... USING INDEX idx_odds_commence (commence_ms>?)
--                USE TEMP B-TREE FOR DISTINCT
--     narrow     SEARCH ... USING INDEX ... (sport_key=? AND commence_ms>?)
--                USE TEMP B-TREE FOR DISTINCT
--     covering   SEARCH ... USING COVERING INDEX (sport_key=? AND commence_ms>?)
--
-- `(sport_key, commence_ms)` alone restricts the seek and leaves both remaining
-- costs standing: a table fetch per surviving row for the three projected
-- columns, and the sort. Carrying those three columns removes both, and the
-- DISTINCT becomes a walk in index order rather than a temp B-tree. **A plan
-- without `USE TEMP B-TREE` is a different algorithm, not a faster one** --
-- that is the property bought here, and it is the one that does not degrade as
-- the table grows.
--
-- The cost is real, measured, and named rather than waved at. On 1.5M
-- synthetic rows of this shape: the scan goes 394ms -> 0ms warm, the index is
-- 52.8 MB (20% of the indexless file), and a 900-row sweep's inserts go from
-- 3ms to 7ms at n=15. **The write roughly doubles and stays trivial**; the
-- read stops existing. On live the index will be LARGER than 52.8 MB, because
-- synthetic team names are short and uniform where real ones are not --
-- `idx_odds_event` there is 136 MB against a 244 MB table, and this carries
-- more string bytes than that does. Read the real figure with `db-sizes`.
-- `docs/measurements/2026-08-30-the-candidate-scan-index.md`.
--
-- **The `[[vm]]` comment in `fly.live.toml` is the objection to answer, and it
-- is answered rather than ignored:** "a larger index eats a larger cache" on a
-- box that has OOM-killed itself. True, and this index makes the cache
-- pressure of THIS query go down, not up. Today the pass drags ~520,000 table
-- rows through the page cache every time it looks; after this it walks a
-- contiguous index range and touches the table not at all. Resident bytes up,
-- page traffic per pass down by orders of magnitude.
--
-- **It makes a growing scan cheaper; it does not make it bounded.**
-- `odds_snapshots` still has no retention rule (`store/retention.py` says so in
-- its own "what this does NOT do"), so this changes the constant and leaves the
-- growth term alone.
--
-- The column list must stay in step with `runner.MATCH_CANDIDATE_SQL`: a column
-- added there and not here silently demotes the plan. Pinned by
-- `tests/test_candidate_scan_plan.py`.
CREATE INDEX IF NOT EXISTS idx_odds_sport_commence
    ON odds_snapshots(sport_key, commence_ms, odds_event_id, home_team, away_team);

-- Credit accounting. The free tier is 500/month and cost = markets x regions,
-- so an unmetered poll loop drains the month in a day. Every call is recorded
-- with what the API said remained, so the budget is reconciled against the
-- server's count rather than our own optimistic tally.
--
-- `trigger` is 'manual' for an on-demand refresh and NULL for a planner call.
-- **Written to be EXCLUDED, not reported** -- see `_SERVED_SWEEP` in
-- `odds/timing.py` and migration v9 in `store/db.py`. A tap makes the same
-- request the planner makes at the same cost, so without a way to tell them
-- apart the planner reads a tap as having opened a window, and the cluster
-- loses its whole prop purchase.
--
-- **The commentary lives here and not beside the column, and that is a
-- constraint rather than a preference.** SQLite implements `ALTER TABLE DROP
-- COLUMN` by editing this stored DDL text: it removes the column's own line and
-- leaves everything around it, so a `--` block sitting above the *last* column
-- survives the drop attached to a now-dangling comma, and the table will not
-- reparse. `tests/test_store.py` drops columns to build old databases, so the
-- failure surfaces there rather than in production -- which is luck, not
-- design.
-- **`http_status` exists because a failed call used to read as a fresh one.**
-- `odds/client.py` records the credit BEFORE checking the status -- correct,
-- and it must stay, because some error classes still consume credits and
-- undercounting spend is worse than overcounting it. But the row it wrote
-- satisfied `_SERVED_SWEEP` in `odds/timing.py`, so a 401 moved that sport's
-- last-sweep stamp to now and **deferred the retry by a full refresh
-- interval** -- while the screen showed the odds as freshly bought. An outage
-- presenting as fresh data is the one thing a freshness clock exists to make
-- impossible, and it was the clock doing it. Recorded 2026-08-17
-- (`docs/JOE-odds-key-rotation.md:151-166`), fixed 2026-08-25.
--
-- NULL on every pre-v21 row, and NULL is honest there: nobody recorded it.
-- `_SERVED_SWEEP` carries `AND COALESCE(http_status, 200) < 400`, so all of
-- them count exactly as they did before. No backfill, because the rows this
-- matters for are precisely the ones whose status is unknowable after the fact.
--
-- **Keep the explanation up here, not beside the column.** A comment block
-- between the second-to-last column and the last one makes SQLite's
-- `ALTER TABLE ... DROP COLUMN` fail with "incomplete input" when the last
-- column goes -- it re-parses the stored CREATE text and the comment is left
-- dangling before the paren. `tests/test_store.py` builds its "old" databases
-- by dropping exactly these columns, so it caught it immediately.
CREATE TABLE IF NOT EXISTS api_credits (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    called_ms           INTEGER NOT NULL,
    endpoint            TEXT NOT NULL,
    sport_key           TEXT,
    markets             TEXT,
    regions             TEXT,
    cost                INTEGER NOT NULL,   -- what we predicted: markets x regions
    remaining_reported  INTEGER,            -- x-requests-remaining header
    used_reported       INTEGER,            -- x-requests-used header
    trigger             TEXT,               -- 'manual' or NULL; see above
    http_status         INTEGER             -- v21; see the note above the table
);
CREATE INDEX IF NOT EXISTS idx_credits_time ON api_credits(called_ms DESC);

-- Why a pass did or did not spend an odds credit. One row per pass that decided
-- nothing, one per sport it acted on.
--
-- **This table exists because absence had no representation.** A refused sweep
-- left no row anywhere in this schema: `api_credits` is written only when an
-- HTTP call was actually made, `notifications` writes `window_open` only when a
-- sweep succeeded, and the scheduler's reason string was only logged -- and the
-- log stream is lossy. So "the scheduler looked and declined" and "the scheduler
-- never ran" were the same observation, which is how odds fetching stopped on
-- 2026-08-09 and ran 17+ hours behind a green health check.
--
-- **Deliberately not a zero-cost row in `api_credits`.** That table means "a
-- call went out and it cost credits", and `last_sweep_by_sport` reads it for
-- "has this sport been swept today". A refusal row there is read as a served
-- sweep: the scheduler drops that sport's slot as already covered and spends its
-- one bootstrap attempt on it, so the trace intended to reveal the silence would
-- have caused it, for exactly the sport it was recording a refusal for. Absence
-- does not belong in the table that means presence -- the same rule as
-- `tasks/lessons.md`'s zero that means "no measurement".
CREATE TABLE IF NOT EXISTS odds_sweep_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pass_ms         INTEGER NOT NULL,
    -- NULL when the row is the pass's own decision rather than one sport's.
    -- Absent, not empty: a pass that decided nothing swept no sport at all.
    sport_key       TEXT,
    -- served   -- a call went out and quotes were stored
    -- refused  -- the budget declined it; `detail` names the ceiling that bound
    -- no_data  -- the call went out and the slate came back empty
    -- skipped  -- the pass chose not to sweep; `detail` is the reason
    -- failed   -- the call went out and the upstream refused it; `detail` names
    --             the status. v21. **None of the other four could say this**:
    --             `refused` means *we* declined, `skipped` means we chose not to
    --             look, and `no_data` means the slate came back empty -- which
    --             is a successful call about a quiet night, the opposite of an
    --             outage. Before this, a 401 wrote no row here at all and was
    --             visible only as an `api_credits` row with NULL headers. This
    --             table exists because silence was indistinguishable from a
    --             system that never looked; an upstream failure is that case
    --             exactly, and it was the one outcome the vocabulary could not
    --             name.
    outcome         TEXT NOT NULL,
    -- The reason, in the words the decision itself used. Not re-derived here:
    -- a paraphrase of a reason is a second implementation of it.
    detail          TEXT NOT NULL,
    -- NULL -- never 0 -- unless the sweep was served. Nothing stored and
    -- nothing attempted are different states and must not share a value.
    quotes_stored   INTEGER,
    -- The upstream status on a `failed` row, NULL on every other outcome. v21.
    -- Kept apart from `detail` so a reader can count 401s without parsing
    -- prose, and constrained below so no other outcome can borrow it.
    failed_status   INTEGER,
    CHECK (outcome IN ('served', 'refused', 'no_data', 'skipped', 'failed')),
    CHECK ((outcome = 'served') = (quotes_stored IS NOT NULL)),
    CHECK ((outcome = 'failed') OR (failed_status IS NULL))
);
CREATE INDEX IF NOT EXISTS idx_sweep_log_time ON odds_sweep_log(pass_ms DESC);

-- ============================================================================
-- Matching
-- ============================================================================
-- Deterministic only. The previous project's Kalshi<->Polymarket text matcher
-- achieved a 0.56% hit rate AND the hits were wrong -- pairing "who wins" with
-- "over/under 3.5 goals" on the same fixture. Same trap here.
--
-- Every link records HOW it was made, so a bad rule can be found and reversed
-- rather than being indistinguishable from a good one.

CREATE TABLE IF NOT EXISTS event_links (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    kalshi_event_ticker TEXT NOT NULL REFERENCES kalshi_events(event_ticker),
    odds_event_id       TEXT NOT NULL,
    league              TEXT NOT NULL,
    method              TEXT NOT NULL,      -- exact_alias_pair (only value for now)
    -- Difference between the two sources' stated start times. A link with a
    -- large skew is a different fixture that happens to share teams, so this
    -- is kept as evidence rather than being validated and thrown away.
    commence_skew_ms    INTEGER NOT NULL,
    linked_ms           INTEGER NOT NULL,
    UNIQUE (kalshi_event_ticker, odds_event_id)
);

-- Everything the matcher could NOT link, and why. This is a work queue for
-- filling in alias tables by hand, and it must stay visible -- a matcher that
-- silently drops what it cannot resolve looks identical to one that has
-- nothing to do.
--
-- **One row per work item, not one per sighting (ADR 0056).** The linker runs
-- every pass and re-derives the same failures, so its predecessor gained a row
-- per unmatched event per pass for a work list that does not change. Measured
-- on live 2026-08-19: **788,944 rows carrying 1,376 distinct items**, a 573:1
-- duplication, the eight worst items appearing 2,477 times each with exactly
-- one reason apiece, and `resolved` set on none of them.
--
-- **`seen_count` is what makes this queue readable, and is the reason this is
-- not merely a disk fix.** It separates a fixture that failed to match once
-- during a rename from one that has been failing for a week. The append-only
-- shape could not express that difference: every row looked alike and there
-- were three quarters of a million of them, which is why nobody ever worked it.
--
-- **This is a NEW TABLE rather than a migration of `unmatched_events`, and the
-- reason is a measurement rather than taste.** The obvious change is to collapse
-- the old table in place at boot. Rehearsed against live on 2026-08-19, the two
-- statements that would take cost **229s** (the `GROUP BY` over 788,944 rows)
-- and **218s** (`DROP TABLE` on the 181,154 pages it occupies). Migrations run
-- at boot, before uvicorn; a four-to-eight minute boot is an outage with Fly's
-- health check watching, and a machine killed part-way re-runs the step from
-- the top on restart -- a crash loop on the one volume that cannot be
-- recreated. That is the v11 failure this repo has already survived once.
--
-- So nothing is migrated. This table is created empty (`IF NOT EXISTS` covers
-- both a fresh database and the live volume), the linker writes here from the
-- first pass, and **`unmatched_events` is left exactly where it is** to be
-- drained by the retention rule that already bounds it and dropped once it is
-- empty, when the drop is free. See `store/retention.py`.
--
-- **Discarding the old rows would also have been defensible, and is not what
-- happens.** The linker re-derives the entire work list every pass, so the
-- content is rebuilt within about fifteen seconds; only `first_seen_ms` -- how
-- long an item has been failing -- would be lost. Draining costs nothing extra
-- because the prune already existed, so the cheaper-looking option was not
-- taken.
CREATE TABLE IF NOT EXISTS unmatched_items (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    -- When this item was first and most recently seen.
    --
    -- **Named as a pair deliberately.** The single `observed_ms` this replaces
    -- reads as "when it was observed", which under an upsert is ambiguous
    -- between the two -- and a reader who guesses "most recent" gets a
    -- retention rule backwards. The rename is the guard against that reading.
    first_seen_ms       INTEGER NOT NULL,
    last_seen_ms        INTEGER NOT NULL,
    -- Sightings, including the first, so this is never 0.
    seen_count          INTEGER NOT NULL DEFAULT 1,
    side                TEXT NOT NULL,      -- kalshi | odds
    identifier          TEXT NOT NULL,
    league              TEXT,
    detail              TEXT,               -- team names as seen, for alias entry
    -- **Free text, not an enum.** `match/linker.py` writes a sentence naming
    -- the specific fixtures it would not choose between ("ambiguous: 2 fixtures
    -- match the same team pair within +/-240min"), because this queue is read
    -- by a person filling in an alias file, and the token would not tell them
    -- which alias to add. `runner.py` supplies the literal `no_counterpart`
    -- only as a fallback when the linker returned no reason at all.
    --
    -- This comment used to read `no_alias | no_counterpart | commence_skew`;
    -- `no_alias` and `commence_skew` are written by nothing. `GROUP BY reason`
    -- here yields one group per distinct sentence, not three buckets.
    reason              TEXT NOT NULL,
    resolved            INTEGER NOT NULL DEFAULT 0
);
-- The work item's identity, and the guard that makes duplication impossible
-- rather than merely unlikely.
--
-- **The `COALESCE` calls are load-bearing, not tidiness.** SQLite treats NULLs
-- as distinct in a UNIQUE index, so leaving nullable `league` and `detail` bare
-- would let every NULL-league item insert afresh on every pass -- the exact
-- behaviour this replaces, surviving behind an index that claims to prevent it.
-- A unique index that silently exempts the common case is worse than none,
-- because it is cited as a reason not to check. Verified against NULL on both
-- columns rather than reasoned about.
CREATE UNIQUE INDEX IF NOT EXISTS idx_unmatched_item ON unmatched_items(
    side, identifier, COALESCE(league, ''), COALESCE(detail, ''), reason);
-- Retention reads `last_seen_ms`, never `first_seen_ms`: an item still being
-- seen is still open work however old it is. Pruning on first-seen would delete
-- it and let the very next pass write it straight back with `seen_count` reset
-- to 1, destroying the one number this table now exists to carry while
-- reporting a healthy prune.
CREATE INDEX IF NOT EXISTS idx_unmatched_open ON unmatched_items(resolved, last_seen_ms DESC);

-- ============================================================================
-- Fair prices
-- ============================================================================
-- All four devig methods are stored, not just the one used. Their disagreement
-- IS a signal: when methods spread widely the fair line is untrustworthy, and
-- that can only be seen if all four are kept.

CREATE TABLE IF NOT EXISTS fair_prices (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    computed_ms         INTEGER NOT NULL,
    link_id             INTEGER NOT NULL REFERENCES event_links(id),
    market              TEXT NOT NULL,      -- h2h | spreads | totals | prop key
    outcome_name        TEXT NOT NULL,
    -- See `odds_snapshots.outcome_description`. NULL on team markets.
    outcome_description TEXT,
    outcome_point       REAL,
    p_multiplicative    REAL,
    p_additive          REAL,
    p_power             REAL,
    p_shin              REAL,
    -- The one used for money decisions: the LOWEST across methods for the side
    -- being bought. Three layers of conservatism (worst method, derived ask,
    -- fee-net) is deliberate.
    p_conservative      REAL NOT NULL,
    overround           REAL,               -- sum of raw implied probabilities
    -- Spread between the best and worst book on this outcome. Wide market =
    -- untrustworthy fair line = suppression input.
    market_width        REAL,
    book_count          INTEGER NOT NULL,
    books_used          TEXT NOT NULL,      -- JSON array, for reproducibility
    -- Age of the OLDEST contributing book quote at `computed_ms` (v20). A
    -- consensus is only as fresh as its stalest input, and a reader computing
    -- this row's live age needs `(now - computed_ms) + oldest_book_age_ms` --
    -- without this column the first term alone understates staleness by up to
    -- a whole sweep interval. Nullable: rows written before v20 genuinely did
    -- not record it, and a NULL must make the reader refuse the row as
    -- unmeasurable, never treat it as age zero. Deliberately not the last
    -- column: the wind-back test DROPs migrated columns, and SQLite cannot
    -- drop a comment-preceded final column without leaving a dangling comma.
    oldest_book_age_ms  INTEGER,
    anchored_on_sharp   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_fair_link ON fair_prices(link_id, computed_ms DESC);

-- `ladder_candidates` selects on `market IN (...) AND computed_ms >= ?`, which
-- `idx_fair_link` cannot serve because it leads with `link_id`. Without this
-- the plan read `SCAN f` -- every fair price ever computed, on every request
-- to `/api/parlays`. With it: `SEARCH f USING INDEX (market=? AND computed_ms>?)`.
CREATE INDEX IF NOT EXISTS idx_fair_market_computed
    ON fair_prices(market, computed_ms DESC);

-- The Quant's independent opinion. Deliberately a separate table from
-- fair_prices: the whole point is that it is NOT derived from the same
-- sportsbook consensus, so when the two agree that is genuine corroboration
-- rather than one number counted twice.
CREATE TABLE IF NOT EXISTS model_ratings (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    computed_ms         INTEGER NOT NULL,
    league              TEXT NOT NULL,
    team                TEXT NOT NULL,
    rating              REAL NOT NULL,
    games_played        INTEGER NOT NULL,
    model_version       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ratings_team ON model_ratings(league, team, computed_ms DESC);

-- ============================================================================
-- Strategy configuration -- the flywheel's unit of change
-- ============================================================================
-- Every recommendation records which config produced it, so "did that change
-- help?" is answerable by segmenting rather than by feel. Without this the
-- learning loop silently overfits to the last twenty bets and nobody can tell.

CREATE TABLE IF NOT EXISTS strategy_configs (
    version             INTEGER PRIMARY KEY,
    created_ms          INTEGER NOT NULL,
    effective_from_ms   INTEGER NOT NULL,
    effective_to_ms     INTEGER,            -- NULL while current
    config_json         TEXT NOT NULL,
    rationale           TEXT NOT NULL,      -- why this differs from its predecessor
    approved_by_user    INTEGER NOT NULL DEFAULT 0
);

-- ============================================================================
-- Recommendations -- including suppressed ones
-- ============================================================================
-- Suppressed rows are kept because the suppression log is itself analysable:
-- if a rule is firing constantly it is either miscalibrated or catching a real
-- data problem, and both are findings. A filter that discards what it rejects
-- can never be audited.
--
-- EVERY recommendation is scored on CLV whether or not it was bet. That is
-- what makes 300 scored observations reachable without 300 wagers.

CREATE TABLE IF NOT EXISTS recommendations (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    created_ms              INTEGER NOT NULL,
    strategy_config_version INTEGER NOT NULL REFERENCES strategy_configs(version),
    ticker                  TEXT NOT NULL REFERENCES kalshi_markets(ticker),
    link_id                 INTEGER REFERENCES event_links(id),
    fair_price_id           INTEGER REFERENCES fair_prices(id),

    side                    TEXT NOT NULL,      -- yes | no
    -- The price we would ACTUALLY pay: the derived ask. Never a mid. Every
    -- bucket and every P&L figure downstream keys off this column.
    entry_ask_tenths        INTEGER NOT NULL,
    depth_at_ask            REAL,

    fair_probability        REAL NOT NULL,      -- conservative devig
    model_probability       REAL,               -- the Quant, NULL until it exists
    -- **Net of fees, per contract.** Until 2026-08-09 this comment read
    -- "gross, before fees" and it was inverted: `engine.py` assigns
    -- `edge_after_fees_tenths(...)`, and the Board renders the same number as
    -- "+1.7c after fees". This file is the contract every downstream query
    -- reads, so the wrong reading does not produce a wrong-looking answer --
    -- it produces a fee-relative band with the fee subtracted twice, which
    -- looks decided.
    --
    -- **And it is a per-contract edge at ONE specific size**, which the column
    -- does not carry: `engine.py` computes it at `max(1, sizing.contracts)`.
    -- The fee's per-order rounding is size-dependent, so two rows with
    -- different `suggested_contracts` are not on the same scale, and every row
    -- the sizer zeroed -- most of the record -- is priced at a single contract
    -- by that floor. A histogram of this column is a histogram at the size
    -- that was sized, not at any size a reader chooses. Recompute from
    -- `(entry_ask_tenths, fair_probability)` for any other size. See the
    -- addendum to `docs/adr/0017`.
    edge_tenths             REAL NOT NULL,
    fee_predicted           REAL NOT NULL,
    ev_net_dollars          REAL NOT NULL,      -- after fees, at suggested size

    kelly_fraction          REAL NOT NULL,
    -- What the operator may buy, at the operator's bankroll and caps.
    suggested_contracts     INTEGER NOT NULL,

    -- What the *record* counts: the same decision sized against a bankroll and
    -- caps fixed in code (`config.REFERENCE_*`), never against the deposit.
    --
    -- These are two different questions and one column was answering both. The
    -- gate's `actionable` population was defined on `suggested_contracts`, so
    -- the size of the deposit decided what counted as evidence: at a $100
    -- bankroll quarter-Kelly sizes below one contract on every edge this tool
    -- finds, `actionable` is structurally zero, and the 300-game floor could
    -- never increment however long the system ran. The Gate screen would go on
    -- saying "0 of 300, keep recording" without naming the cause.
    --
    -- NULL only on rows written before this column existed. Those were all
    -- produced by the $1,000 deployment, which *is* the reference profile, so
    -- the v6 migration backfills them from `suggested_contracts` -- an equality
    -- that holds by construction for the live record and is stated in
    -- `docs/adr/0015` rather than assumed here.
    reference_contracts     INTEGER,

    -- Freshness at the moment of the recommendation. An opportunity outside
    -- the configured bounds is not bettable, enforced server-side.
    kalshi_quote_age_ms     INTEGER NOT NULL,
    odds_age_ms             INTEGER NOT NULL,

    -- Re-derived, not re-recorded. `engine.persist_if_changed` deliberately
    -- writes no second row when the ask and the fair value are unchanged --
    -- otherwise ~98% of the record is repetition. But freshness was measured
    -- from `created_ms`, so an unchanged row aged past the 30s Kalshi limit and
    -- stayed there while the market had not moved at all. "This observation is
    -- old" and "this price is old" were one number; these three columns split
    -- them.
    --
    -- A confirmation is a complete re-statement about one instant: at
    -- `last_confirmed_ms` the same decision was re-derived from a Kalshi quote
    -- of age `last_confirmed_quote_age_ms` and a consensus of age
    -- `last_confirmed_odds_age_ms`. Both ages are stored, because refreshing
    -- the quote clock without the odds clock would let a row live forever on a
    -- fifteen-minute-old consensus -- the flattering direction.
    --
    -- NULL means never re-derived. Callers fall back to `created_ms` and the
    -- two ages above it, which is what every row written before this column
    -- existed carries.
    last_confirmed_ms           INTEGER,
    last_confirmed_quote_age_ms INTEGER,
    last_confirmed_odds_age_ms  INTEGER,

    -- NULL means surfaced. Non-NULL means suppressed, and says why.
    suppressed_reason       TEXT,
    reason_text             TEXT NOT NULL,      -- plain language, for the Board

    -- CLV scoring, filled in after close. Positive = we beat the close.
    --
    -- `clv_horizon_hours` records which anchor produced `clv_tenths`, written
    -- with the score and never inferred. Without it the value is a bare number
    -- and moving the horizon -- ADR 0011 did -- blends two regimes with nothing
    -- able to tell them apart. The gate reads only the current primary horizon,
    -- so a future change invalidates evidence loudly (the counter drops)
    -- instead of quietly averaging two different measurements together.
    --
    -- **Keep this comment here rather than above the column.** SQLite's
    -- `ALTER TABLE ... DROP COLUMN` rewrites the stored CREATE TABLE text, and
    -- a comment sitting immediately before the **last** column survives the
    -- drop while the column does not -- leaving a trailing comma followed by
    -- prose and `)`, which fails to reparse:
    --     error in table recommendations after drop column: incomplete input
    -- The migration tests build an "old" database by dropping exactly these
    -- columns, so this is not hypothetical; it turned 72 tests red.
    closing_line_id         INTEGER REFERENCES closing_lines(id),
    clv_tenths              REAL,
    clv_scored_ms           INTEGER,
    clv_horizon_hours       REAL
);
CREATE INDEX IF NOT EXISTS idx_recs_created ON recommendations(created_ms DESC);
CREATE INDEX IF NOT EXISTS idx_recs_open ON recommendations(suppressed_reason, created_ms DESC);
CREATE INDEX IF NOT EXISTS idx_recs_unscored ON recommendations(clv_scored_ms) WHERE clv_scored_ms IS NULL;

-- **The recording loop's hottest read, and it had no index until 2026-08-26.**
--
-- `engine.persist_if_changed` runs once per candidate, every pass:
--
--     SELECT id, entry_ask_tenths, fair_probability FROM recommendations
--     WHERE ticker = ? AND side = ? ORDER BY created_ms DESC, id DESC LIMIT 1
--
-- With no index on `(ticker, side)` the planner answered
-- `SCAN recommendations` + `USE TEMP B-TREE FOR ORDER BY` -- a full scan AND a
-- temporary sort, ~350 times a pass, on a table that grows ~300 rows a pass
-- and is never trimmed.
--
-- Measured on live 2026-08-26: `leg_price_persist_ms` 26,000-40,000 for 290
-- fair prices and 4 recommendations (~97ms per row), quote passes taking
-- 35-74s against a 15-SECOND cadence, and every API route starved on the
-- shared vCPU -- `/api/window` 0.32s -> 17.8s, `/api/slate` 0.38s -> 24.6s,
-- `/api/parlays` past Next's 30s proxy timeout and returning 500.
--
-- **Football was the trigger, not the cause.** The cost is rows x candidates;
-- adding NCAAF roughly doubled the candidates and pushed a long-standing
-- quadratic from tolerable into pathological.
--
-- The trailing columns make it covering for the ORDER BY as well as the WHERE,
-- which is what removes the temp b-tree. Write amplification is ~300 inserts a
-- pass against ~350 full scans; the trade is not close.
CREATE INDEX IF NOT EXISTS idx_recs_ticker_side
    ON recommendations(ticker, side, created_ms DESC, id DESC);

-- ============================================================================
-- Execution
-- ============================================================================

CREATE TABLE IF NOT EXISTS orders (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Our idempotency key, generated before the request. Present even for
    -- dry runs so a dry run and a live order are the same shape.
    client_order_id     TEXT NOT NULL UNIQUE,
    kalshi_order_id     TEXT UNIQUE,
    recommendation_id   INTEGER REFERENCES recommendations(id),
    submitted_ms        INTEGER NOT NULL,
    ticker              TEXT NOT NULL REFERENCES kalshi_markets(ticker),
    side                TEXT NOT NULL,      -- yes | no
    action              TEXT NOT NULL,      -- buy | sell
    order_type          TEXT NOT NULL,      -- limit | market
    count               INTEGER NOT NULL,
    -- **The price for OUR side, snapped to the market's grid.** V2 quotes the
    -- YES leg only, so buying NO at 40.5c goes out as a YES ask of 59.5c --
    -- this column holds 405, not 595. Exposure is `count * limit_price_tenths`
    -- and must be what we pay: storing the wire price would compute a NO
    -- position's exposure as its complement, understating it above 50c, which
    -- is the direction that lets the cap pass a position it should refuse.
    -- The wire price is not lost; `request_body_json` holds the exact bytes.
    limit_price_tenths  INTEGER,
    -- pending (written before the request goes out, outcome unknown)
    -- | dry_run | resting | partially_filled | filled | unfilled
    -- | canceled | rejected | unrecognised_response
    --
    -- `store/orders.py` decides exposure by excluding the *terminal* statuses
    -- rather than listing the live ones, so a status added here and forgotten
    -- there counts as exposure instead of vanishing from the sum.
    status              TEXT NOT NULL,
    -- The exact body we sent (or would have sent, in dry run). Makes a dry run
    -- verifiable against a live order byte for byte.
    request_body_json   TEXT NOT NULL,
    error_text          TEXT,
    dry_run             INTEGER NOT NULL DEFAULT 1,
    -- **The CLIENT's key, not `client_order_id`.** Two keys because they dedupe
    -- against two different parties: `client_order_id` stops *Kalshi* creating a
    -- second order when we re-send, and this stops *us* creating a second order
    -- when the phone is tapped twice. Neither substitutes for the other -- the
    -- exchange never sees this column, and a fresh `client_order_id` per request
    -- is exactly what made two taps two orders.
    --
    -- Nullable, because every row written before v3 has no key and because
    -- SQLite treats NULLs as distinct in a UNIQUE index, so the history neither
    -- collides with itself nor blocks the constraint.
    idempotency_key     TEXT,
    -- The response body the caller was given, verbatim, so a replay returns the
    -- same answer rather than a second answer reconstructed from the columns.
    -- Reconstructing it would be a second implementation of the response shape,
    -- free to drift from the first -- and the two would drift silently, because
    -- only a duplicate tap ever renders this one.
    --
    -- NULL means the outcome is unknown: the row was reserved and the process
    -- did not get as far as answering. A replay refuses on that rather than
    -- sending a second order, because "we do not know whether it went" must not
    -- resolve to "it did not".
    response_body_json  TEXT,
    -- **The named fill policy, never an implied one.** A dry run never rests in
    -- a book, so "did it fill" has no observed answer and any answer is an
    -- assumption. Recording which one was used is what lets the record be
    -- re-analysed under a different one later. `depth_capped_taker` is the only
    -- value today: the order path refuses when the resting size at our price is
    -- smaller than the order, so every paper order is a marketable limit inside
    -- the depth we saw. See docs/adr/0010.
    --
    -- Nullable, because rows written before v4 carry no assumption -- and an
    -- absent assumption must stay absent rather than defaulting to the current
    -- one, which would silently relabel history as though it had been measured.
    fill_assumption     TEXT,
    -- How many contracts the assumption says filled. Separate from `count` so
    -- the day a partial-fill policy exists, the two stop being the same number
    -- without any column changing meaning.
    assumed_filled_count INTEGER,
    CHECK (side IN ('yes','no')),
    CHECK (action IN ('buy','sell'))
);
CREATE INDEX IF NOT EXISTS idx_orders_time ON orders(submitted_ms DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_idempotency
    ON orders(idempotency_key);

CREATE TABLE IF NOT EXISTS fills (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    kalshi_fill_id      TEXT UNIQUE,
    order_id            INTEGER REFERENCES orders(id),
    -- **No FK to kalshi_markets, since v10.** A fill polled from
    -- /portfolio/fills may be on a market this tool never discovered -- a bet
    -- placed by hand, in the Kalshi app -- and refusing to record a real fill
    -- because our own discovery missed it is the wrong way round.
    ticker              TEXT NOT NULL,
    filled_ms           INTEGER NOT NULL,
    count               REAL NOT NULL,
    price_tenths        INTEGER NOT NULL,
    is_taker            INTEGER NOT NULL,
    -- The whole point of this pair. fee_actual is ground truth from Kalshi;
    -- fee_predicted is what our model said. A mismatch is stop-the-line, and
    -- it is also how the year-old fee-schedule TODO finally gets closed.
    fee_actual          REAL,
    fee_predicted       REAL NOT NULL,
    fee_model_used      TEXT NOT NULL,
    -- The venue's own order id (v18). What joins a portal-placed manual
    -- order's fill back to its `manual_orders` row via `kalshi_order_id`;
    -- NULL on rows recorded before v18 and on any fill whose payload
    -- omitted it.
    venue_order_id      TEXT,
    -- engine | venue_hand. Which population this fill belongs to. Without it
    -- the fee-calibration set and the hand-bet set pool silently, and they are
    -- answers to different questions -- one is our order path, the other is a
    -- person tapping buttons in an app we cannot see.
    source              TEXT NOT NULL DEFAULT 'engine',
    CHECK (source IN ('engine', 'venue_hand'))
);
CREATE INDEX IF NOT EXISTS idx_fills_time ON fills(filled_ms DESC);
CREATE INDEX IF NOT EXISTS idx_fills_mismatch ON fills(ticker)
    WHERE fee_actual IS NOT NULL AND fee_actual != fee_predicted;

-- One row per settled POSITION, not per settled market. The distinction is the
-- v4 migration: `UNIQUE (ticker, settled_ms)` described a market outcome while
-- the columns beside it described a position, so two orders on one ticker --
-- ordinary, since a quote pass re-recommends a market minutes later -- collided
-- and the second silently never settled, holding its exposure open forever.
CREATE TABLE IF NOT EXISTS settlements (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id            INTEGER NOT NULL REFERENCES orders(id),
    ticker              TEXT NOT NULL REFERENCES kalshi_markets(ticker),
    -- Kalshi's own `settlement_ts`, observed. **Not** `close_time` and not
    -- `expiration_time`: on the captured sample the latter sits three days
    -- after close, so it is not a settlement instant at all.
    settled_ms          INTEGER NOT NULL,
    result              TEXT NOT NULL,      -- yes | no
    contracts           INTEGER NOT NULL,
    -- Realised P&L in cents, integer. Float dollars in a money path produce
    -- 7.350000000000001 > 7.35 rejections; the previous project moved its
    -- entire risk path to integers for this reason.
    pnl_cents           INTEGER NOT NULL,
    -- Paper or real, copied from the order rather than joined -- so no reader
    -- can pool the two populations by forgetting to join. Paper P&L and live
    -- P&L answer different questions and must never share a number.
    dry_run             INTEGER NOT NULL,
    -- The named fill policy this row's P&L was computed under. Stored so the
    -- record can be re-scored under a different one; an assumption baked into
    -- the arithmetic cannot be revised. See docs/adr/0010.
    fill_assumption     TEXT,
    -- Resting size at our price when the order went out. It is what justified
    -- assuming the fill, so it is what a re-analysis needs in order to weaken
    -- the assumption.
    depth_at_order      REAL,
    -- ADR 0058's basis marker (v16): which fee model computed pnl_cents.
    -- NULL = written before the marker existed, i.e. under the flat 0.070
    -- model. 'series_mult_<m>:override_unchecked' when the venue's
    -- per-series fee_multiplier was read live; 'flat_0.070:series_unread'
    -- when the fetch failed and the flat model stood in, said out loud.
    fee_model_used      TEXT,
    CHECK (result IN ('yes','no')),
    UNIQUE (order_id)
);
CREATE INDEX IF NOT EXISTS idx_settlements_order ON settlements(order_id);

-- ============================================================================
-- The flywheel's written record
-- ============================================================================

CREATE TABLE IF NOT EXISTS lessons (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    created_ms          INTEGER NOT NULL,
    title               TEXT NOT NULL,
    body                TEXT NOT NULL,
    -- What the Historian looked at to conclude this. A lesson without a
    -- sample size is an anecdote, and the noise guard needs n to refuse.
    evidence_json       TEXT,
    sample_size         INTEGER,
    proposed_config_diff TEXT,
    accepted_by_user    INTEGER
);

-- ============================================================================
-- Alerts that were sent
-- ============================================================================
-- Exists to make two claims true that `notify/discord.py` already makes in its
-- docstring: that an alert Discord refused is still recorded, and that a
-- phone is not woken twice for the same thing.
--
-- The dedupe key is what makes a restart safe. The loop dies loudly on
-- repeated failure and the platform restarts it, so any policy holding "have I
-- already sent this?" in memory would re-announce the whole slate on every
-- restart -- and a crash loop would then be indistinguishable from a busy
-- night. `UNIQUE (kind, key)` moves that question to the database, where it
-- survives the process.
CREATE TABLE IF NOT EXISTS notifications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sent_ms     INTEGER NOT NULL,
    kind        TEXT NOT NULL,      -- opportunity | window_open | digest | failure
    key         TEXT NOT NULL,      -- unique within kind; see notify/alerts.py
    -- Whether Discord accepted it. Recorded rather than inferred: "we decided
    -- to alert" and "the alert arrived" are different facts, and a channel
    -- that has been silent for a day should be distinguishable from a system
    -- that found nothing to say.
    delivered   INTEGER NOT NULL,
    -- Whether this row is a deliberate claim that was never sent. A THIRD
    -- fact, and it needs its own column because `delivered = 0` already
    -- carries two meanings that must not be merged: "we tried and Discord
    -- refused" and "the process died between claiming and sending". ADR 0049
    -- built `/api/health`'s `undelivered_last_24h` to catch the second one.
    --
    -- ADR 0076 then introduced a claim that is *supposed* to have no send:
    -- when the scheduled card goes out, the change channel's key for the same
    -- composition is burned so it cannot re-announce it. That row leaves
    -- exactly the signature of a death, three times a day, and without this
    -- column the alarm can never read 0 again.
    --
    -- Recorded rather than inferred, for the same reason `delivered` is --
    -- see the comment above it. A join back to `parlay_daily` on a shared
    -- millisecond would be a deduction, and this is a fact the writer knows.
    suppressed  INTEGER NOT NULL DEFAULT 0,
    detail      TEXT,
    UNIQUE (kind, key)
);
CREATE INDEX IF NOT EXISTS idx_notifications_time ON notifications(sent_ms DESC);

-- One row per parlay card slot, holding the composition it is currently
-- showing and how many CONSECUTIVE ladder builds it has held it for.
--
-- This is the two-build debounce. `notifications` already stops a card being
-- pushed twice; this stops a card being pushed ONCE too early. Card
-- compositions churn because sports are swept on independent clocks and
-- `build_ladder` drops legs past `MAX_ODDS_AGE_S` -- so whichever sport was
-- swept most recently owns the top of the probability ranking, and a sport
-- entering the pool rewrites every card. Measured on live 2026-08-26: the
-- whole day's push ceiling spent in four minutes on two compositions that
-- differed only by which sport happened to be fresh.
--
-- **Consecutive, which is why this replaces rather than accumulates.** Under
-- churn the same two compositions alternate, so "seen twice ever" is satisfied
-- by exactly the pattern being suppressed. A build whose composition differs
-- resets `builds` to 1; a slot that builds nothing has its row deleted, so an
-- appear/vanish/reappear cycle does not count as two in a row.
--
-- A table and not a dict in memory, for `notifications`' own reason: this box
-- restarts, and a policy that forgets on restart re-announces on restart.
CREATE TABLE IF NOT EXISTS parlay_card_candidates (
    card_key    TEXT PRIMARY KEY,   -- safe | middle | lottery | ...
    key         TEXT NOT NULL,      -- notify/alerts.py::parlay_key(card)
    first_ms    INTEGER NOT NULL,   -- when this composition first appeared
    builds      INTEGER NOT NULL    -- consecutive builds it has held
);

-- ============================================================================
-- Anthropic agent calls
-- ============================================================================
-- One row per call the agent fleet makes, written whether or not the call
-- produced a verdict. Two jobs, and the second is the reason the table exists
-- rather than a counter in memory:
--
-- **It is the meter.** `agents/budget.py` reads `COUNT(*)` over the current
-- sports day from here, so the per-day ceiling survives a process restart. A
-- counter held in `PassCounts` would reset on every deploy, and a daily cap
-- that resets whenever the container restarts is not a daily cap.
--
-- **It is the only durable record that the fleet ever ran.**
-- `PassCounts.skeptic_reviewed` / `skeptic_blocked` are logged and nothing
-- else, and the Fly log buffer is 100 lines -- so before this table, "the
-- Skeptic reviewed a row on Tuesday" was unanswerable the following morning.
--
-- `verdict` and `blocked` are NULL -- never 0, never "none" -- when the call
-- returned no opinion (an outage, a safety refusal, unparseable output). A
-- call that happened and said nothing and a call that blocked nothing are
-- different facts; see `tasks/lessons.md` on the zero that means "no
-- measurement".
CREATE TABLE IF NOT EXISTS agent_calls (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    called_ms   INTEGER NOT NULL,
    agent       TEXT NOT NULL,      -- skeptic | scout | historian
    model       TEXT NOT NULL,      -- what it cost, per token, is a fact about this
    ticker      TEXT,               -- NULL for a call that is not about one row
    side        TEXT,
    verdict     TEXT,               -- defect | suspicious | plausible | NULL
    blocked     INTEGER,            -- 1 | 0 | NULL when there was no verdict
    -- What the call actually consumed, filled in by `settle` from the API's
    -- own usage report (v17). NULL -- never 0 -- when the response never
    -- arrived: a reserve with no settle, a network death, a crash. A NULL row
    -- is spend the token meter could not see, and `calls_unmetered_today`
    -- counts them so the sums state what they do not cover. The call-count
    -- cap, which needs no response to enforce, remains the outer bound.
    -- `input_tokens` is the whole presented prompt (uncached + cache read +
    -- cache write) -- a token meter, not a dollar meter; rates differ by
    -- cache class and this column does not pretend otherwise.
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    web_searches    INTEGER,
    CHECK (blocked IS NULL OR blocked IN (0, 1))
);
CREATE INDEX IF NOT EXISTS idx_agent_calls_time ON agent_calls(called_ms DESC);

-- One convening of the scout desk (ADR 0060): two staff scouts and a master,
-- sent on demand from the game screen. The spend itself is metered in
-- `agent_calls` (three rows per convening); this table holds what came back,
-- so a briefing outlives the request that paid for it and the phone can read
-- it later for free.
--
-- `status` is the desk's honest one-word state. `running` is written before
-- the first call and belongs to a background task; a `running` row older than
-- the reader's patience window is reported as gone-quiet rather than left
-- looking alive forever (the reader owns that judgement -- a crashed process
-- cannot come back to update its own row).
--
-- `staff_json` / `briefing_json` are NULL until something came back, never
-- `{}`: nothing filed and an empty filing are different facts.
CREATE TABLE IF NOT EXISTS scout_briefings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL,
    event_title     TEXT NOT NULL,
    league          TEXT NOT NULL,
    home_team       TEXT NOT NULL,
    away_team       TEXT NOT NULL,
    commence_ms     INTEGER,            -- the sportsbook's clock, never Kalshi's
    requested_ms    INTEGER NOT NULL,
    completed_ms    INTEGER,
    status          TEXT NOT NULL,      -- running | complete | partial | failed | refused
    refusal_reason  TEXT,               -- which ceiling refused, when status = refused
    staff_json      TEXT,               -- list of staff notes incl. filed-nothing markers
    briefing_json   TEXT,               -- the master's DeskBriefing
    sharp_json      TEXT,               -- Willy Balters' SharpTake (ADR 0069); NULL = seat filed nothing / predates the seat
    model           TEXT NOT NULL,
    CHECK (status IN ('running', 'complete', 'partial', 'failed', 'refused')),
    CHECK ((status = 'running') = (completed_ms IS NULL))
);
CREATE INDEX IF NOT EXISTS idx_scout_briefings_ticker
    ON scout_briefings(ticker, requested_ms DESC);

-- One "Price on Kalshi" tap from the parlay desk (ADR 0070). A lookup MINTS a
-- real combination market on the exchange (`lookup_combo` with
-- `allow_market_creation=True`), so every attempt is recorded -- success,
-- refusal, or error -- the way `manual_orders` records every send. The priced
-- ask comes from the minted market's ORDER BOOK (derived YES ask =
-- 1 - best resting NO bid), never from the `/markets` list row: E2/E3 measured
-- the list row echoing its own legs' prices and skewing from the book by up to
-- 30.5c.
--
-- Money columns are integer tenths of a cent, per this file's convention.
-- NULL means "not observed", never zero: an empty book has no derived ask, and
-- the row says so by absence plus `status`.
-- Which Kalshi events are legs in SOME multivariate collection -- i.e. which
-- games the venue will actually combine, as opposed to merely trade.
--
-- **A cache of a remote fact, and the only reason it is a table.**
-- `ladder_candidates` needs this to stop offering cards that cannot be priced,
-- and it cannot ask Kalshi: `GET /api/parlays` is a sync route and the same
-- builder runs inside the scheduler pass, where a 25-page paginated walk is
-- the shape that killed the pass tail on 2026-08-28. So the walk happens on
-- the loop's own schedule and leaves its answer here.
--
-- `refreshed_ms` is stamped on every row of a refresh, so `MAX(refreshed_ms)`
-- is when the list was last known good. **The reader must treat a stale or
-- empty table as "unknown", never as "nothing is combinable"** -- filtering on
-- a cold cache would empty the parlay desk, which is an outage wearing a
-- guard's clothes.
CREATE TABLE IF NOT EXISTS combo_eligible_events (
    event_ticker  TEXT PRIMARY KEY,
    refreshed_ms  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_combo_eligible_refreshed
    ON combo_eligible_events(refreshed_ms);

CREATE TABLE IF NOT EXISTS parlay_lookups (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    requested_ms             INTEGER NOT NULL,
    card_key                 TEXT NOT NULL,      -- safe | middle | lottery
    stake_cents              INTEGER NOT NULL,
    -- JSON array of {event_ticker, market_ticker} pairs, exactly as sent to
    -- the lookup call, for reproducibility.
    selected_legs            TEXT NOT NULL,
    collection_ticker        TEXT,               -- NULL when no collection fit
    status                   TEXT NOT NULL,
    minted_market_ticker     TEXT,
    book_no_bid_tenths       INTEGER,            -- best resting NO bid
    derived_yes_ask_tenths   INTEGER,            -- 1000 - book_no_bid_tenths
    book_depth               REAL,               -- resting units behind that bid
    fair_joint_conservative  REAL,               -- the card's headline joint at lookup time
    hold                     REAL,               -- 1 - fair x offered decimal, fee-free
    error                    TEXT,
    -- 1 when the collection was picked by the prefix fallback rather than
    -- because it was known to contain these legs. Recorded rather than acted
    -- on: `parlays._choose_collection` falls back precisely because the
    -- enumerated leg list is known to understate what a catch-all `-R`
    -- collection accepts (the 2026-08-23 capture posted NFL legs to
    -- `KXMVESPORTSMULTIGAMEEXTENDED-R` and Kalshi minted them), so refusing
    -- would refuse taps that work. Nobody has measured how often the fallback
    -- fires or how often it is then accepted. This column is that measurement.
    collection_unverified    INTEGER NOT NULL DEFAULT 0,
    CHECK (status IN ('priced', 'book_empty', 'no_collection', 'error'))
);
CREATE INDEX IF NOT EXISTS idx_parlay_lookups_time
    ON parlay_lookups(requested_ms DESC);

-- ============================================================================
-- Joe's own hand-placed bets, and his stated probability before each one
--
-- Registered in `docs/measurements/2026-08-17-preregistration-joe-calibration-
-- bet-log.md`. The question is whether **Joe** is overconfident, not whether
-- the engine has an edge -- ADR 0038 closed that and nothing here reopens it.
--
-- **These tables must never be pooled with `recommendations`.** That table is
-- engine output and is the registered population of the ADR 0021/0034 CLV
-- signal test, which `analysis/signal_test.py` fits. Writing hand-placed bets
-- into it would silently contaminate a different registered measurement with
-- rows that were never engine recommendations.
-- ============================================================================

-- The venue's own record of a settled position, mirrored. One row per settled
-- position, straight off `/portfolio/settlements`.
--
-- **Deliberately NOT the `settlements` table above.** That one is keyed
-- `order_id INTEGER NOT NULL` -- structural to its identity, and this project
-- has never placed an order -- and its `pnl_cents` is *our* computed profit
-- under a named `fill_assumption`, which is a meaningless concept when the
-- venue is stating the truth directly.
-- `contracts` is REAL, per this file's QUANTITIES convention at the top, and
-- **not** because nobody thought about it. The wire fields are `yes_count_fp`
-- / `no_count_fp` -- `_fp` for fixed point, two decimals -- and the live
-- record read on 2026-08-18 contains `11.27` and `0.27`. v10 declared this
-- INTEGER from a spec written before anyone had read the payload, which would
-- have stored a 0.27-contract position as **zero**: the position vanishing,
-- and the entry price derived from it dividing by zero.
--
-- v11 then over-corrected to integer hundredths, inventing a third numeric
-- convention in a file that already had exactly two and stated both. The money
-- rule -- integer tenths of a cent -- exists because money math must be exact.
-- The quantity rule already covered this. v12 put it back.
CREATE TABLE IF NOT EXISTS venue_settlements (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    -- No FK to `kalshi_markets`. A market bet by hand may never have been
    -- discovered by this tool, and refusing to record a real settled position
    -- because our own discovery missed it is the wrong way round.
    ticker                  TEXT NOT NULL,
    event_ticker            TEXT,
    market_result           TEXT,
    settled_ms              INTEGER NOT NULL,
    side                    TEXT NOT NULL,      -- yes | no, from the count pair
    contracts               REAL NOT NULL,
    -- The price actually paid, from the venue: total cost / count. It is not a
    -- mid and nobody can accidentally make it one. NULL if the pair was
    -- unreadable -- never 0, because a settled loser genuinely trades at 0.
    entry_price_tenths      INTEGER,
    fee_cost_tenths         INTEGER,
    -- `/portfolio/fills` `created_time`, else the poll instant, else
    -- `settled_time`. `position_time_source` says which, because a silent
    -- `settled_time` fallback guts the two-clock check without looking like it.
    position_first_seen_ms  INTEGER,
    position_time_source    TEXT,
    is_taker                INTEGER,
    n_fills_in_position     INTEGER,
    -- Amendment 3 (A13, v15): the position-side half of section 7.5 coverage.
    -- 'matched' | 'position_unlogged' | 'out_of_scope'; NULL = not yet
    -- examined, never a default. Lives here and not on bet_estimates because
    -- an unlogged position HAS no estimate row to carry a status.
    estimate_match_status   TEXT,
    UNIQUE (ticker, settled_ms),
    CHECK (side IN ('yes', 'no')),
    CHECK (is_taker IS NULL OR is_taker IN (0, 1))
);
CREATE INDEX IF NOT EXISTS idx_venue_settlements_time
    ON venue_settlements(settled_ms DESC);

-- The account balance, observed. `CLAUDE.md` names this as what is needed to
-- settle H4 -- whether settlement carries its own fee -- which is why ADR 0027
-- calls the cost headroom an upper bound. The registration's stopping rule
-- needs it anyway, so recording it costs nothing extra.
-- `balance_tenths` comes from `balance_dollars` ("20.6583"), **never** the
-- `balance` integer beside it. Observed 2026-08-18: `balance` was 2065 while
-- `balance_dollars` was 20.6583 -- the integer is whole cents and drops 0.83c.
-- Reading the convenient integer field is exactly the deci-cent error
-- CLAUDE.md opens with. NULL when unreadable, never 0.
--
-- `portfolio_value_tenths` is open positions; the stopping rule reads cash.
-- Kept beside it so a balance that fell because a position was opened is
-- distinguishable from one that fell because a bet lost.
--
-- **No comments inside the parentheses, deliberately.** SQLite's
-- `ALTER TABLE ... DROP COLUMN` rewrites the stored CREATE text, and an
-- interleaved comment defeats that surgery -- dropping the last column left
-- `error in table venue_balance_snapshots after drop column: incomplete
-- input` and took out 17 migration tests. Any table a migration ALTERs keeps
-- its prose up here.
CREATE TABLE IF NOT EXISTS venue_balance_snapshots (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    observed_ms            INTEGER NOT NULL,
    balance_tenths         INTEGER,
    portfolio_value_tenths INTEGER
);
CREATE INDEX IF NOT EXISTS idx_venue_balance_time
    ON venue_balance_snapshots(observed_ms DESC);

-- The one field in the whole design that Kalshi cannot supply.
--
-- **It cannot be a column on `fills`.** It is written and timestamped *before
-- any fill exists*, and it must survive the case where no fill ever exists --
-- an estimate made and then not bet on is the *less* selected sample and is a
-- registered sensitivity analysis. A column on a row that does not yet exist
-- cannot be written, which is fatal to the two-clock design rather than
-- inconvenient.
CREATE TABLE IF NOT EXISTS bet_estimates (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker                      TEXT NOT NULL,
    -- P(YES), ALWAYS -- never "probability my side wins". That phrasing is
    -- undefined until a side is chosen, and asking for P(YES) lets the estimate
    -- be formed *before* choosing one, which is a strictly more pre-price act.
    -- The venue reports which side was actually taken, so `side` is not asked.
    -- Basis points, so 6789 is 67.89%. Converted to p_side at analysis time.
    stated_probability_bp       INTEGER NOT NULL,
    -- Clock A. The server's, not the phone's: the two-clock check is worthless
    -- if one of the clocks is the one being checked.
    estimate_server_ms          INTEGER NOT NULL,
    -- Divergence from the server stamp is a tamper diagnostic and nothing else.
    -- It never enters the analysis.
    estimate_client_ms          INTEGER,
    -- Asked BEFORE the probability input is enabled. The only recorded signal
    -- about the hole the two clocks do not close -- they prove he had not
    -- transacted, never that he had not looked.
    had_already_opened_kalshi   INTEGER,
    -- THE clustering variable. Every standard error groups on this.
    cluster_key                 TEXT NOT NULL,
    -- The market quote at estimate time, captured server-side and **never
    -- rendered until the study stops**. It is the anchoring tripwire, so
    -- showing it would destroy the thing it measures.
    server_yes_bid_tenths       INTEGER,
    server_yes_ask_tenths       INTEGER,
    server_quote_observed_ms    INTEGER,
    -- Why the quote is NULL. Unreadable is a state, not a zero.
    server_quote_unreadable_reason TEXT,
    stated_probability_is_revised  INTEGER NOT NULL DEFAULT 0,
    is_in_play                  INTEGER NOT NULL DEFAULT 0,
    is_sports                   INTEGER NOT NULL DEFAULT 1,
    is_multi_leg                INTEGER NOT NULL DEFAULT 0,
    sport                       TEXT,
    matched_position_id         INTEGER REFERENCES venue_settlements(id),
    -- matched | absence_pending | unmatched_no_position | position_unlogged.
    -- `position_unlogged` is how attrition becomes a measured rate instead of
    -- an invisible bias: the venue reports a position whether or not an
    -- estimate was logged for it. `absence_pending` is Amendment 2 (A11): the
    -- window has closed and the market's result is known, but no settlements
    -- poll has yet postdated that knowledge -- so "he did not bet" is not yet
    -- provable and must not be stamped. Rows in it remain matchable.
    match_status                TEXT,
    -- When the current match_status was written (v14, Amendment 2). The
    -- absence proof compares a settlements poll against this instant. NULL on
    -- rows stamped before the amendment -- the honest value; the A12 repair
    -- re-buckets those rather than inventing an instant for them.
    match_status_ms             INTEGER,
    -- NULL when unsettled or void. **Never 0** -- a loss and "we do not know"
    -- are different states and this repo has collapsed them before.
    outcome_win                 INTEGER,
    -- The outcome as the PUBLIC market endpoint reports it, via
    -- `backend/market_results.py`, which already runs and accepts a result
    -- only at `finalized`.
    --
    -- **This is the durable path and it is preferred over the portfolio one.**
    -- `/portfolio/settlements` has now been observed to drop history -- 55
    -- records spanning 2025-11 to 2026-05 were gone eight days later -- so an
    -- outcome read only from the portfolio can evaporate. The public market
    -- result cannot: it is a fact about the market, not about this account.
    market_result_public        TEXT,
    -- Which path supplied `outcome_win`: public_market | venue_settlement.
    -- Recorded rather than inferred, because a silent fallback to the
    -- perishable source is precisely what would not look like a defect.
    outcome_source              TEXT,
    -- 1 when this row sits inside a poll gap long enough that the venue may
    -- have dropped the fill before it was read. It flags; it never voids --
    -- dropping rows on an outage would remove them for a reason correlated
    -- with calendar time, and therefore with sport and with betting streaks.
    retention_at_risk           INTEGER NOT NULL DEFAULT 0,
    closing_line_id             INTEGER REFERENCES closing_lines(id),
    clv_tenths                  REAL,
    -- Written *with* the score, never inferred later. Without it the column
    -- silently blends the 0.0h anchor with the legacy 1.0h one, and pooling
    -- them biases the result in the flattering direction.
    clv_horizon_hours           REAL,
    clv_scored_ms               INTEGER,
    CHECK (stated_probability_bp BETWEEN 1 AND 9999),
    CHECK (outcome_win IS NULL OR outcome_win IN (0, 1)),
    CHECK (had_already_opened_kalshi IS NULL
           OR had_already_opened_kalshi IN (0, 1))
);
CREATE INDEX IF NOT EXISTS idx_bet_estimates_time
    ON bet_estimates(estimate_server_ms DESC);
CREATE INDEX IF NOT EXISTS idx_bet_estimates_cluster
    ON bet_estimates(cluster_key);
CREATE INDEX IF NOT EXISTS idx_bet_estimates_unmatched
    ON bet_estimates(ticker) WHERE matched_position_id IS NULL;

-- §7.4 of the calibration registration: `stated_probability_bp` is write-once,
-- **enforced by the database rather than by route discipline**, because the
-- route is one caller and this file outlives every caller. Fires on any UPDATE
-- that names the column, including one writing the same value back -- a
-- statement that names the estimate column at all is doing something the
-- protocol forbids, and "it happened to be a no-op" is not an audit trail.
--
-- Triggers live here and NOT in a numbered migration, deliberately. v11 was a
-- crash loop at boot because it ALTERed a table the real v9 volume did not
-- have: migrations run BEFORE this file, and v11 itself DROPs `bet_estimates`
-- for this file to recreate. `CREATE TRIGGER IF NOT EXISTS` on every open has
-- no such window -- by the time executescript reaches this line the table
-- exists, on every volume, at every starting version.
CREATE TRIGGER IF NOT EXISTS trg_bet_estimates_write_once
BEFORE UPDATE OF stated_probability_bp ON bet_estimates
BEGIN
    SELECT RAISE(ABORT,
        'stated_probability_bp is write-once (calibration registration 7.4); append a revision row instead');
END;

-- The trivial bypass of an UPDATE guard is DELETE + INSERT, so an UPDATE-only
-- guard would be decoration. The record is append-only: a wrong estimate is
-- flagged revised, never removed.
CREATE TRIGGER IF NOT EXISTS trg_bet_estimates_no_delete
BEFORE DELETE ON bet_estimates
BEGIN
    SELECT RAISE(ABORT,
        'bet_estimates is append-only (calibration registration 7.4); flag the row revised instead of deleting it');
END;

-- §7.4's correction path: append-only, carrying a reason. Revising sets
-- `stated_probability_is_revised = 1` on the flagged row -- an UPDATE of a
-- *different* column, which the trigger above deliberately permits -- and §2
-- excludes the row from every population. The corrected estimate, if any, is
-- a brand-new `bet_estimates` row logged through the normal path with fresh
-- clocks and a fresh quote; nothing here edits a probability in place.
CREATE TABLE IF NOT EXISTS bet_estimate_revisions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    estimate_id   INTEGER NOT NULL REFERENCES bet_estimates(id),
    reason        TEXT NOT NULL,
    revised_ms    INTEGER NOT NULL,
    CHECK (length(reason) > 0)
);
CREATE INDEX IF NOT EXISTS idx_bet_estimate_revisions_estimate
    ON bet_estimate_revisions(estimate_id);

-- One row per analysis run. The registration forbids interim looks -- an
-- always-valid boundary would put the entire effect being hunted out of reach
-- at every achievable sample size, so the design buys power by looking once.
--
-- **This table is what makes "we only looked once" checkable rather than
-- aspirational.** More than one non-embargoed row before the stop voids the
-- single-look claim, and a claim nobody can audit is not a protocol.
CREATE TABLE IF NOT EXISTS bet_estimate_looks (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_ms              INTEGER NOT NULL,
    n_in_population     INTEGER NOT NULL,
    -- 1 while the stopping rule has not fired. An embargoed run may compute
    -- counts; it may not compute or return the test statistic.
    embargo_active      INTEGER NOT NULL,
    git_sha             TEXT,
    reason              TEXT,
    CHECK (embargo_active IN (0, 1))
);
CREATE INDEX IF NOT EXISTS idx_bet_estimate_looks_time
    ON bet_estimate_looks(run_ms DESC);

-- One row per poll ATTEMPT, per endpoint, including the ones that failed.
--
-- **Every retention tripwire in the registration is decoration without this.**
-- The rules are stated as gaps between successive *successful* polls -- flag
-- rows above 3 days, fall back above 7 -- and a gap can only be measured
-- against a record of when polling did and did not work. A failure that writes
-- nothing is invisible, and an invisible failure reads exactly like a quiet
-- week in which nothing was bet.
--
-- This matters more than it did yesterday. Both portfolio endpoints have now
-- been observed to drop history: `/portfolio/fills` retains roughly three
-- months, and `/portfolio/settlements` -- previously believed to be the safety
-- net at nine months -- lost 55 records inside eight days. If a poll does not
-- happen, the record is not merely late. It is gone.
CREATE TABLE IF NOT EXISTS poll_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    polled_ms   INTEGER NOT NULL,
    -- settlements | fills | positions | balance | match (failures only)
    -- | mirror (a branch marker, not an attempt: it says this cycle took the
    --   12-hour mirror branch rather than the 5-minute one, so a lock burst
    --   can be attributed to the right branch)
    endpoint    TEXT NOT NULL,
    ok          INTEGER NOT NULL,
    -- NULL on failure, never 0: "the call raised" and "the venue returned an
    -- empty list" are different states, and an empty list is a legitimate one.
    row_count   INTEGER,
    error       TEXT,
    CHECK (ok IN (0, 1))
);
CREATE INDEX IF NOT EXISTS idx_poll_log_endpoint_time
    ON poll_log(endpoint, polled_ms DESC);
CREATE INDEX IF NOT EXISTS idx_poll_log_ok
    ON poll_log(polled_ms DESC) WHERE ok = 1;

-- One tap of "not tonight" (fleet convening item 10, 2026-08-20). Append-only:
-- a lockout is never deleted or shortened, because a control that can be
-- talked back open is a speed bump. Release is implicit -- rows whose
-- `until_ms` has passed simply stop mattering -- so the table is also the
-- record of every time the control was reached for, which the tilt review
-- called the most decision-relevant fact this product could collect about
-- its own user.
CREATE TABLE IF NOT EXISTS self_lockouts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    requested_ms INTEGER NOT NULL,
    until_ms     INTEGER NOT NULL,
    CHECK (until_ms > requested_ms)
);

-- One deliberate "no" (slice B6, 2026-08-22). The record could hold 39 settled
-- bets and zero evidence Joe ever chose NOT to bet, so the only unit the /bets
-- headline could count was bets placed -- a scoreboard that makes betting the
-- sole recordable act. A pass makes the decision the unit instead.
--
-- Append-only, like `self_lockouts` and for the same reason: a "no" that can
-- be edited afterwards is a story, not a record. No UPDATE or DELETE path
-- exists in the codebase and a test greps for one. Passes are **never scored,
-- never rated** -- nothing may join this against outcomes or prices to say
-- whether a pass was "right"; that would turn the one pressure-free act in
-- the product back into a graded one.
--
-- `scope` is 'tonight' (written as a side effect of the lockout tap -- one
-- gesture, two records) or a market ticker (a per-market pass via
-- POST /api/desk/pass). `reason` is optional prose; NULL means none was
-- given, and none is ever required.
--
-- Additive table, no schema-version bump: `init_db` applies this file to
-- existing databases too, so `IF NOT EXISTS` creates it on the live volume
-- at next boot -- the `scout_briefings` pattern exactly.
CREATE TABLE IF NOT EXISTS desk_passes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_ms   INTEGER NOT NULL,
    scope        TEXT NOT NULL,
    reason       TEXT
);

-- Someone has the site open. v21, 2026-08-25.
--
-- **This is what the odds feed follows instead of the clock** (ADR 0071 §2.6).
-- `ODDS_DESK_WINDOW_UTC` bought a sweep every ten minutes for twelve hours a
-- day whether or not anyone was looking -- ~576 credits/day at two sports,
-- ~17,300/month against an 18,000 self-cap, and ~1,152/day at four, which
-- breaks even the 20,000 paid tier. Joe looks at the desk for a fraction of
-- that window, so the feed now buys while a page is open and falls back to a
-- slow floor when it is not.
--
-- **Append-only, not a single mutable last-seen row**, and the reason is that
-- the saving is unmeasured. Every "attended hours" figure in the design is a
-- guess about how long the page is actually open; a table of stamps is the
-- instrument that answers it, and an UPDATE would destroy the only evidence
-- that could. Pruned by the retention pass like any other log.
--
-- One row per heartbeat, so the row count is the measurement. No `session_id`
-- and no user column: this instance serves one operator (ADR 0071 §1), and a
-- column that is always the same value is a claim about a future that does not
-- exist yet.
CREATE TABLE IF NOT EXISTS desk_attention (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    seen_ms     INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_desk_attention_seen
    ON desk_attention(seen_ms DESC);

-- The manual order path (ADR 0063, 2026-08-22). A SEPARATE table, not a
-- `source` column on `orders`, because every population predicate that
-- guards money reads that table (`current_exposure_dollars`, the gate's
-- evidence counts, the future fee-model MISMATCH branch) and each would
-- become a filter that must never be forgotten. A table is a boundary; a
-- column is a convention. Nothing in `backend/gate.py` may ever read this
-- table -- hand bets do not move the interlock's counters.
CREATE TABLE IF NOT EXISTS manual_orders (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    client_order_id     TEXT NOT NULL UNIQUE,
    kalshi_order_id     TEXT UNIQUE,
    submitted_ms        INTEGER NOT NULL,
    -- No FK to kalshi_markets: a manual order may target any ticker the
    -- venue knows, discovery notwithstanding. The live-quote read at order
    -- time is what proves the ticker exists.
    ticker              TEXT NOT NULL,
    side                TEXT NOT NULL,      -- yes | no
    action              TEXT NOT NULL,      -- buy (the only manual action)
    count               INTEGER NOT NULL,
    -- The price for OUR side, snapped -- same convention and same reasoning
    -- as `orders.limit_price_tenths` (exposure must be what we pay).
    limit_price_tenths  INTEGER,
    -- Joe's ceiling as he typed it, before snapping. The order is refused,
    -- never re-priced, when the live ask exceeds it.
    max_price_tenths    INTEGER NOT NULL,
    -- The typed P(YES), basis points (ADR 0065). Required at the route.
    -- Lives HERE, beside the order it preceded -- never in `bet_estimates`,
    -- whose stopped-study log stays terminal.
    p_yes_bp            INTEGER NOT NULL,
    status              TEXT NOT NULL,
    request_body_json   TEXT NOT NULL,
    error_text          TEXT,
    dry_run             INTEGER NOT NULL DEFAULT 1,
    idempotency_key     TEXT UNIQUE,
    response_body_json  TEXT,

    -- ------------------------------------------------------------------
    -- What the desk was showing when he tapped (v28, 2026-08-29).
    -- ------------------------------------------------------------------
    --
    -- **A frozen COPY, deliberately not a foreign key.** `fair_prices` is
    -- mutable and retention-eligible, so a `fair_price_id` on this row would
    -- be a pointer at whatever that table holds when someone finally looks --
    -- which is not a record of what was true when the money left. The two
    -- id columns below are kept as breadcrumbs and are explicitly NOT the
    -- record; the snapshot columns are.
    --
    -- **Every one is nullable and a NULL means "not known", never zero.** A
    -- `KXMVE` combination has no devigged consensus at all -- discovery drops
    -- the prefix as junk (`kalshi/discovery.JUNK_PREFIX`), so no
    -- `kalshi_markets` row and no `recommendations` row can exist for one --
    -- and `consensus_fair_tenths = 0` would read as "the sportsbooks say this
    -- is worth nothing", which on a money row is a lie rather than a gap.
    -- `consensus_absent_reason` says which absence it was.
    --
    -- Rows written before v28 carry NULL in all eight. Nothing backfills them:
    -- the values were never observed and inventing them would put a number
    -- into the record that no clock ever produced.
    --
    -- No CHECK constraints, and that is a migration property rather than an
    -- oversight: SQLite refuses `ALTER TABLE ... DROP COLUMN` on a column
    -- named by any CHECK, and `tests/test_store.py::_v1_database` winds the
    -- schema back by dropping exactly these. A constraint here would make the
    -- migration untestable, which is worse than the constraint is good.

    -- The devigged sportsbook consensus fair value for the side BOUGHT, in
    -- integer tenths of a cent on the same 0-1000 scale as
    -- `limit_price_tenths`. `recommendations.fair_probability` (the
    -- worst-of-four conservative devig for that outcome) through
    -- `core.prices.probability_to_tenths`.
    consensus_fair_tenths       INTEGER,
    -- The desk's own fee-net edge for that row, signed, rounded to integer
    -- tenths from `recommendations.edge_tenths` (REAL). A per-row fact and
    -- never an ordering: ADR 0071 forbids ranking by it, and `beta = -0.141`
    -- is why.
    consensus_edge_tenths       INTEGER,
    -- Provenance, so the fair value can be interpreted rather than trusted.
    -- How many books the consensus was devigged from, and whether it was
    -- anchored on the sharp set (`runner.SHARP_BOOKS`) -- an anchored
    -- consensus selects at most three books, which is a thinner fair value,
    -- not a better one.
    consensus_book_count        INTEGER,
    consensus_anchored_on_sharp INTEGER,        -- 0 | 1 | NULL
    -- When the consensus itself was computed (`fair_prices.computed_ms`), NOT
    -- when this row was written. `submitted_ms - consensus_computed_ms` is
    -- how stale the evidence was at the tap, and there is no other way to
    -- recover it once the source row is pruned.
    consensus_computed_ms       INTEGER,
    -- Non-authoritative breadcrumbs. Free to store because the lookup already
    -- read them, and useful for reconciling against a `fair_prices` row that
    -- still exists. A reader that needs the VALUE must use the columns above:
    -- these two may dangle.
    consensus_fair_price_id     INTEGER,
    consensus_link_id           INTEGER,
    -- Why the snapshot is absent, when it is. NULL exactly when
    -- `consensus_fair_tenths` is present. See
    -- `store/manual_orders.ABSENT_*` for the closed vocabulary -- a reason
    -- that is recorded is a reason the audit can count, and "no consensus"
    -- and "the lookup blew up" are different facts about the record.
    consensus_absent_reason     TEXT,

    CHECK (side IN ('yes', 'no')),
    CHECK (action = 'buy'),
    CHECK (count > 0),
    CHECK (p_yes_bp BETWEEN 1 AND 9999),
    CHECK (dry_run IN (0, 1))
);

-- ============================================================================
-- Hand-bet refusals (v29, 2026-08-30)
-- ============================================================================
-- One row per HTTPException the manual-order route raised before the intent
-- row existed. Until this table, all ~23 refusal branches wrote NOTHING --
-- reservation happens at check 11, so every earlier refusal left zero trace
-- and the desk could not say which of its own brakes fired on the first-ever
-- attempted bet, or with what values. A log line is not a record: this
-- instance's containers restart and `flyctl logs` is lossy (three instances
-- of the same defect in three days -- refused hand bet, failed match pass,
-- poisoned-connection failure -- see the DRAFT ADR merged with this table).
--
-- **Forensic, not analytic.** Append-only, no dashboard, no counter, no
-- screen reads it yet; the population is refusals of Joe's own taps, which is
-- single-digit rows. Deliberately not capped or pruned, same reasoning as
-- `loop_failures` below.
--
-- **`gate.py` may never read this table** -- the identical boundary
-- `manual_orders` and `parlay_positions` carry (ADR 0063, ADR 0078): a
-- refusal must not move the live-trading interlock's counter. Pinned by the
-- same source-assertion test that pins the other two.
--
-- A recording failure must never convert a 422 into a 500: the writer runs on
-- a throwaway connection, falls back to a journal line beside the database
-- (`manual_order_refusals.jsonl`, the `record_loop_failure_durably`
-- precedent), and swallows its own errors. The refusal Joe sees is the
-- refusal, whether or not it could be recorded.
CREATE TABLE IF NOT EXISTS manual_order_refusals (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    created_ms          INTEGER NOT NULL,
    -- Which of the route's numbered checks refused (0-11, the docstring's
    -- numbering) and its stable name. The check pointer is maintained beside
    -- the checks themselves, so a refusal raised mid-check is attributed to
    -- the check that was running, not guessed from the message.
    check_number        INTEGER NOT NULL,
    check_name          TEXT NOT NULL,
    http_status         INTEGER NOT NULL,
    -- The exact string Joe was shown. The message IS the finding; nothing
    -- reconstructs it later.
    detail              TEXT NOT NULL,
    -- What was being attempted. Nullable: a refusal can fire before the
    -- ticker is normalised, and NULL means "not reached", never "unknown-ish
    -- default".
    ticker              TEXT,
    side                TEXT,
    requested_contracts INTEGER,
    max_price_tenths    INTEGER,
    idempotency_key     TEXT,
    -- The live ask at refusal time, known only once check 7 has fetched the
    -- quote. NULL before that -- never 0, which would read as a price.
    ask_tenths          INTEGER,
    CHECK (side IS NULL OR side IN ('yes', 'no'))
);
CREATE INDEX IF NOT EXISTS idx_manual_order_refusals_time
    ON manual_order_refusals(created_ms DESC);


-- ============================================================================
-- Recording-loop pass failures
-- ============================================================================
-- One row per pass that raised, written by `scripts/run_loop.py` through the
-- `on_failure` hook on `scheduler.run_forever`.
--
-- **This table exists because a real incident was undiagnosable.** On
-- 2026-08-25 the heartbeat alarmed: 35 minutes with no quote write. The
-- recorder heartbeat is stamped on every pass, and the slow cadence tops out
-- at 900s x 1.15 = 1035s, so the gap was two or three passes that never
-- finished -- confirmed afterwards from `odds_sweep_log`, which had a
-- 2,678-second hole ending 20:51:02Z where every other gap that day was a
-- single jittered interval. Which of the two it was could not be established:
-- `LoopState.consecutive_failures` and `last_error` live in memory, the
-- container had restarted, and its logs were gone with it. A failing pass and
-- a wedged pass need different fixes and produced identical evidence.
--
-- **A row here is the thing that separates them.** Failures write rows;
-- a wedge writes nothing, because the pass never returns to raise. So the
-- absence of rows across a gap is itself the reading, which is why this table
-- is written on the failure path only and never on the success path -- a
-- heartbeat for every pass already exists in `meta.recorder_last_write_ms`,
-- and duplicating it here would make "no rows" ambiguous again.
--
-- Deliberately NOT capped or pruned in code. A loop that fails often enough
-- for this table to matter in size is a loop with a bigger problem, and the
-- rows are a few hundred bytes; `MAX_CONSECUTIVE_FAILURES = 5` ends the
-- process long before a runaway.
CREATE TABLE IF NOT EXISTS loop_failures (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    failed_ms            INTEGER NOT NULL,
    -- The loop's own attempt counter, so a gap in this column across one
    -- process tells you passes were attempted and lost rather than never run.
    -- Resets on restart, which is why `failed_ms` is the ordering key.
    pass_number          INTEGER NOT NULL,
    -- How many in a row, at the moment of this failure. Reaching
    -- MAX_CONSECUTIVE_FAILURES is what ends the process, so the last row
    -- before a restart says whether the loop gave up or was killed.
    consecutive_failures INTEGER NOT NULL,
    -- "full" or "quote" -- the two do different work and fail differently.
    -- NULL when the failure happened before the kind was decided.
    pass_kind            TEXT,
    -- `type(exc).__name__: exc`, matching `LoopState.last_error` exactly so
    -- the durable record and the in-memory one cannot drift.
    error                TEXT NOT NULL,
    CHECK (pass_kind IS NULL OR pass_kind IN ('full', 'quote'))
);
CREATE INDEX IF NOT EXISTS idx_loop_failures_time ON loop_failures(failed_ms DESC);


-- ============================================================================
-- Parlays Joe is actually holding, and their legs
-- ============================================================================
-- ADR 0078. The `/parlays` desk prices combinations it might sell; **nothing
-- in this project has ever recorded one he bought.** `parlay_lookups` records
-- that a card was priced, `manual_orders` records that a ticker was sent, and
-- neither is joined to the other or says "this ticket is live and I am on the
-- hook for it".
--
-- That gap is why a hedge cannot be computed: hedging needs the stake, the
-- payout and which legs are still alive, and only the operator knows all
-- three -- a sportsbook slip is not on this venue at all, and a Kalshi combo
-- ticket is a `KXMVE` market that discovery excludes outright.
--
-- **Two tables and not one.** A ticket is one row and its legs are many, and
-- the leg is the unit everything downstream works on: the outcome resolves
-- per leg, the live quote is per leg, and the hedge is bought on one leg's
-- market. Flattening legs into a JSON column would put the only queryable
-- fact behind a parser.
--
-- **`backend/gate.py` may never read either table.** Same rule and same
-- reason as `manual_orders` (ADR 0063): these rows are the operator's own
-- discretion, and the live-trading interlock's evidence populations must not
-- be able to move because he typed in a bet slip. A table is a boundary; a
-- column is a convention.
--
-- Money is integer tenths of a cent (CLAUDE.md), so a $5.00 stake is 5000 and
-- a $333.33 return is 333330. NULL means "not observed", never zero.
--
-- **Schema v24.** These were written as v23 on their own branch while
-- `parlay_card_candidates` was written as v23 on another. Both were correct
-- in isolation; a volume stamped v23 would have had one pair of tables or
-- the other depending on which image booted it, and `open_db` would have
-- raised on neither, because the stamp matched. A version number is a claim
-- about the whole schema and a lane cannot allocate one alone.
CREATE TABLE IF NOT EXISTS parlay_positions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_ms      INTEGER NOT NULL,
    -- Where the ticket lives. `kalshi_combo` can be hedged AND is the case
    -- that most needs it: combos are enter-only in 40 of 40 books this repo
    -- has read, so a hedge on a leg market is the only exit that exists.
    source          TEXT NOT NULL,
    -- Which sportsbook, when it is one. Free text and purely descriptive:
    -- nothing branches on it, and no odds are ever fetched from it.
    book            TEXT,
    label           TEXT NOT NULL,
    stake_tenths    INTEGER NOT NULL,
    -- TOTAL returned on a full win, stake included -- not "to win". The
    -- equalising hedge is exactly this many dollars of contracts, so the
    -- ambiguity would land straight in the size.
    return_tenths   INTEGER NOT NULL,
    placed_ms       INTEGER,
    status          TEXT NOT NULL,
    -- The minted `KXMVE` ticker, on a combo bought through this desk.
    combo_ticker    TEXT,
    -- The `parlay_lookups` row this was bought from, when it was. No FK:
    -- `parlay_lookups` has no retention window today and may gain one, and a
    -- pruned lookup must not take a live position with it.
    parlay_lookup_id INTEGER,
    note            TEXT,
    closed_ms       INTEGER,
    CHECK (source IN ('kalshi_combo', 'sportsbook')),
    CHECK (status IN ('open', 'settled', 'closed', 'void')),
    CHECK (stake_tenths > 0),
    CHECK (return_tenths > stake_tenths)
);
CREATE INDEX IF NOT EXISTS idx_parlay_positions_open
    ON parlay_positions(status, created_ms DESC);

-- One leg of a held ticket.
--
-- **`ticket` is nullable and that is the sportsbook case, not an oversight.**
-- A leg the venue does not list has no market to quote, no result to read and
-- no hedge to buy; it is carried so the ticket's arithmetic is complete, and
-- every surface must say that such a leg cannot be priced rather than
-- treating an absent quote as a bad one.
--
-- `outcome` starts `pending` and moves once. `resolved_source` separates the
-- two ways it can move, because they are not the same evidence: `venue` is
-- `kalshi_markets.result`, written by the market-result pass; `manual` is
-- Joe's word, which is the ONLY thing available for a leg with no ticker.
-- A lock computed off a hand-marked leg is exactly as good as the marking,
-- and the screen says which it was.
CREATE TABLE IF NOT EXISTS parlay_position_legs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id     INTEGER NOT NULL REFERENCES parlay_positions(id),
    leg_index       INTEGER NOT NULL,
    ticker          TEXT,
    -- The side of the LEG, not of the hedge. The hedge is the other one.
    side            TEXT NOT NULL,
    label           TEXT NOT NULL,
    event_ticker    TEXT,
    league          TEXT,
    commence_ms     INTEGER,
    outcome         TEXT NOT NULL,
    resolved_ms     INTEGER,
    resolved_source TEXT,
    CHECK (side IN ('yes', 'no')),
    CHECK (outcome IN ('pending', 'won', 'lost', 'void')),
    CHECK (resolved_source IS NULL OR resolved_source IN ('venue', 'manual')),
    -- A resolved leg carries when and from where; a pending one carries
    -- neither. Without this a leg could read `won` with no provenance, which
    -- is the state the `resolved_source` column exists to make impossible.
    CHECK ((outcome = 'pending') = (resolved_ms IS NULL)),
    CHECK ((outcome = 'pending') = (resolved_source IS NULL)),
    UNIQUE (position_id, leg_index)
);
CREATE INDEX IF NOT EXISTS idx_parlay_position_legs_position
    ON parlay_position_legs(position_id, leg_index);
CREATE INDEX IF NOT EXISTS idx_parlay_position_legs_ticker
    ON parlay_position_legs(ticker) WHERE ticker IS NOT NULL;


-- ---------------------------------------------------------------------------
-- Resting bids on a combination market (v30, 2026-08-30, ADR 0084).
-- ---------------------------------------------------------------------------
--
-- **A different shape of order from anything else in this database.** Every
-- real order this project had ever sent was immediate-or-cancel: it filled
-- against visible depth or it died, and nothing outlived the request. A
-- combination has no visible depth to fill against -- no resting YES bid on
-- 40 of 40 books this repo has read (ADR 0012 section 5) -- so the only way in
-- is to BECOME the offer and wait. That order outlives the request, can fill
-- while nobody is looking, and has to be cancellable. Hence a table.
--
-- Deliberately NOT `manual_orders`. That table's rows are all IOC and its
-- audit query reports on them as such; mixing a row that can still be working
-- into a census of orders that are necessarily finished would make every count
-- in `manual-orders-audit` ambiguous. Same boundary, same reason, as ADR 0063
-- keeping `manual_orders` out of `orders`.
--
-- `gate.py` may never read this table. A resting bid is Joe's discretion, not
-- evidence, and the live-trading interlock counts neither.
CREATE TABLE IF NOT EXISTS combo_orders (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    client_order_id     TEXT NOT NULL UNIQUE,
    kalshi_order_id     TEXT UNIQUE,
    placed_ms           INTEGER NOT NULL,
    -- The minted combination this bid rests on, and the card it came from.
    ticker              TEXT NOT NULL,
    card_key            TEXT NOT NULL,
    -- JSON array of {event_ticker, market_ticker}: the legs as tapped. The
    -- same shape `parlay_lookups.selected_legs` carries, for the same reason.
    selected_legs       TEXT NOT NULL,
    -- **The shard, recorded rather than re-derived.** A cancel needs it as a
    -- query parameter and the venue 404s without it; re-reading the market at
    -- cancel time would fail exactly when the market is gone, which is one of
    -- the moments a cancel matters most.
    exchange_index      INTEGER NOT NULL,
    count               INTEGER NOT NULL,
    -- What Joe chose to pay, snapped to the venue's grid. Integer tenths of a
    -- cent, like every other price in the risk path.
    limit_price_tenths  INTEGER NOT NULL,
    -- The card's conservative joint at the moment of the bid, frozen. Not a
    -- pointer: `fair_prices` moves, and a fair value re-derived later is a
    -- different number presented as the same one (the ADR 0082 lesson).
    fair_joint          REAL,
    -- When this bid stops being wanted: the earliest leg's commence_ms. A
    -- resting bid that fills after a leg has started is a bet on a game
    -- already in progress at a price computed before it began.
    cancel_after_ms     INTEGER,
    status              TEXT NOT NULL,
    request_body_json   TEXT NOT NULL,
    response_body_json  TEXT,
    error_text          TEXT,
    dry_run             INTEGER NOT NULL DEFAULT 1,
    -- Set when the desk (or Joe) takes it back. `reduced_by` is the venue's
    -- own word for how much of it was still working at that moment.
    cancelled_ms        INTEGER,
    cancel_reduced_by   REAL,
    cancel_reason       TEXT
);

CREATE INDEX IF NOT EXISTS idx_combo_orders_status
    ON combo_orders(status, placed_ms DESC);
