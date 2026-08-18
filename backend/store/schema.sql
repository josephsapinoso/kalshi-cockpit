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
    observed_ms     INTEGER NOT NULL,   -- when WE saw it
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
CREATE INDEX IF NOT EXISTS idx_odds_event ON odds_snapshots(odds_event_id, market, fetched_ms DESC);
CREATE INDEX IF NOT EXISTS idx_odds_commence ON odds_snapshots(commence_ms);

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
    trigger             TEXT                -- 'manual' or NULL; see above
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
    outcome         TEXT NOT NULL,
    -- The reason, in the words the decision itself used. Not re-derived here:
    -- a paraphrase of a reason is a second implementation of it.
    detail          TEXT NOT NULL,
    -- NULL -- never 0 -- unless the sweep was served. Nothing stored and
    -- nothing attempted are different states and must not share a value.
    quotes_stored   INTEGER,
    CHECK (outcome IN ('served', 'refused', 'no_data', 'skipped')),
    CHECK ((outcome = 'served') = (quotes_stored IS NOT NULL))
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
CREATE TABLE IF NOT EXISTS unmatched_events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    observed_ms         INTEGER NOT NULL,
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
CREATE INDEX IF NOT EXISTS idx_unmatched_open ON unmatched_events(resolved, observed_ms DESC);

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
    anchored_on_sharp   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_fair_link ON fair_prices(link_id, computed_ms DESC);

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
    count               INTEGER NOT NULL,
    price_tenths        INTEGER NOT NULL,
    is_taker            INTEGER NOT NULL,
    -- The whole point of this pair. fee_actual is ground truth from Kalshi;
    -- fee_predicted is what our model said. A mismatch is stop-the-line, and
    -- it is also how the year-old fee-schedule TODO finally gets closed.
    fee_actual          REAL,
    fee_predicted       REAL NOT NULL,
    fee_model_used      TEXT NOT NULL,
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
    detail      TEXT,
    UNIQUE (kind, key)
);
CREATE INDEX IF NOT EXISTS idx_notifications_time ON notifications(sent_ms DESC);

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
    CHECK (blocked IS NULL OR blocked IN (0, 1))
);
CREATE INDEX IF NOT EXISTS idx_agent_calls_time ON agent_calls(called_ms DESC);

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
    -- **Hundredths, because contract counts are FRACTIONAL on this venue.**
    -- The wire fields are `yes_count_fp` / `no_count_fp` -- `_fp` for fixed
    -- point, two decimals -- and the real record contains `11.27` and `0.27`.
    -- Declared INTEGER in v10 from a spec written before the payload was
    -- observed, which would have stored a 0.27-contract fill as **zero**: a
    -- silent whole-position loss, in the same family as the deci-cent rounding
    -- CLAUDE.md warns about. Integer hundredths keeps it exact and keeps money
    -- arithmetic off floats.
    contracts_hundredths    INTEGER NOT NULL,
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
    -- matched | unmatched_no_position | position_unlogged. The last one is how
    -- attrition becomes a measured rate instead of an invisible bias: the venue
    -- reports a position whether or not an estimate was logged for it.
    match_status                TEXT,
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
    endpoint    TEXT NOT NULL,      -- settlements | fills | positions | balance
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
