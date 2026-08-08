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
    market_type         TEXT,       -- moneyline | spread | total | future | prop
    strike              REAL,       -- spread/total line where applicable
    price_structure     TEXT,       -- cent | deci_cent | tapered_deci_cent
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
    market              TEXT NOT NULL,      -- h2h | spreads | totals
    outcome_name        TEXT NOT NULL,      -- team name, or Over/Under
    outcome_point       REAL,               -- spread/total line
    price_decimal       REAL NOT NULL       -- decimal odds
);
CREATE INDEX IF NOT EXISTS idx_odds_event ON odds_snapshots(odds_event_id, market, fetched_ms DESC);
CREATE INDEX IF NOT EXISTS idx_odds_commence ON odds_snapshots(commence_ms);

-- Credit accounting. The free tier is 500/month and cost = markets x regions,
-- so an unmetered poll loop drains the month in a day. Every call is recorded
-- with what the API said remained, so the budget is reconciled against the
-- server's count rather than our own optimistic tally.
CREATE TABLE IF NOT EXISTS api_credits (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    called_ms           INTEGER NOT NULL,
    endpoint            TEXT NOT NULL,
    sport_key           TEXT,
    markets             TEXT,
    regions             TEXT,
    cost                INTEGER NOT NULL,   -- what we predicted: markets x regions
    remaining_reported  INTEGER,            -- x-requests-remaining header
    used_reported       INTEGER             -- x-requests-used header
);
CREATE INDEX IF NOT EXISTS idx_credits_time ON api_credits(called_ms DESC);

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
    reason              TEXT NOT NULL,      -- no_alias | no_counterpart | commence_skew
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
    market              TEXT NOT NULL,      -- h2h | spreads | totals
    outcome_name        TEXT NOT NULL,
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
    edge_tenths             REAL NOT NULL,      -- gross, before fees
    fee_predicted           REAL NOT NULL,
    ev_net_dollars          REAL NOT NULL,      -- after fees, at suggested size

    kelly_fraction          REAL NOT NULL,
    suggested_contracts     INTEGER NOT NULL,

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
    closing_line_id         INTEGER REFERENCES closing_lines(id),
    clv_tenths              REAL,
    clv_scored_ms           INTEGER
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
    CHECK (side IN ('yes','no')),
    CHECK (action IN ('buy','sell'))
);
CREATE INDEX IF NOT EXISTS idx_orders_time ON orders(submitted_ms DESC);

CREATE TABLE IF NOT EXISTS fills (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    kalshi_fill_id      TEXT UNIQUE,
    order_id            INTEGER REFERENCES orders(id),
    ticker              TEXT NOT NULL REFERENCES kalshi_markets(ticker),
    filled_ms           INTEGER NOT NULL,
    count               INTEGER NOT NULL,
    price_tenths        INTEGER NOT NULL,
    is_taker            INTEGER NOT NULL,
    -- The whole point of this pair. fee_actual is ground truth from Kalshi;
    -- fee_predicted is what our model said. A mismatch is stop-the-line, and
    -- it is also how the year-old fee-schedule TODO finally gets closed.
    fee_actual          REAL,
    fee_predicted       REAL NOT NULL,
    fee_model_used      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fills_time ON fills(filled_ms DESC);
CREATE INDEX IF NOT EXISTS idx_fills_mismatch ON fills(ticker)
    WHERE fee_actual IS NOT NULL AND fee_actual != fee_predicted;

CREATE TABLE IF NOT EXISTS settlements (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker              TEXT NOT NULL REFERENCES kalshi_markets(ticker),
    settled_ms          INTEGER NOT NULL,
    result              TEXT NOT NULL,      -- yes | no
    contracts           INTEGER NOT NULL,
    -- Realised P&L in cents, integer. Float dollars in a money path produce
    -- 7.350000000000001 > 7.35 rejections; the previous project moved its
    -- entire risk path to integers for this reason.
    pnl_cents           INTEGER NOT NULL,
    UNIQUE (ticker, settled_ms)
);

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
