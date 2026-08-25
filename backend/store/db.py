"""SQLite access layer.

Thin on purpose. This module owns connection setup, schema application, and the
schema-version contract; everything else is plain SQL at the call site. An ORM
here would hide exactly the thing that matters most — which column a number
came from, and whether it was a quoted price or a derived one.

Schema versioning
-----------------
`SCHEMA_VERSION` is checked on every open. Reading a database written by an
older schema is refused rather than attempted, because the failure mode is
silent: the previous project's recorder had a v1 that stored whole cents and a
v2 that stored tenths, and reading v1 as v2 divides every price by ten — in the
direction that makes everything look cheap.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

#: v22 adds `loop_failures` and needs no migration step. A pure new table is
#: created by `executescript`'s `CREATE TABLE IF NOT EXISTS` on the next open,
#: on an existing volume as well as a fresh one -- `_MIGRATIONS` exists for
#: changes to tables that already hold rows, which this is not.
SCHEMA_VERSION = 22
_SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# How long a blocked connection waits for the write lock before giving up.
#
# This matters now in a way it did not before: the order endpoint is a **second
# writer, in a second process**, and the runner holds the write lock in bursts
# while it records a pass. A tap landing inside a burst must wait rather than
# fail, because the failure would present as a defect in the order path rather
# than as contention -- and it would arrive after thirteen checks and a Kalshi
# round trip, all of it wasted.
#
# Passed to `sqlite3.connect(timeout=...)` explicitly, which is deliberate and
# worth a note: **CPython already defaults it to 5 seconds.** The first version
# of this set `PRAGMA busy_timeout = 5000` on every connection and was
# therefore a complete no-op -- it assigned the value the driver had already
# assigned. Nothing revealed that except deleting it and watching the test that
# claimed to cover it stay green.
#
# So it is stated here rather than inherited: a value this project depends on
# should be one it chose, not one it happens to be handed, and `timeout=0` a
# driver version from now would silently restore fail-immediately.
BUSY_TIMEOUT_MS = 5_000

# version -> what it adds.
#
# `schema.sql` is applied with `CREATE TABLE IF NOT EXISTS`, so it builds a new
# database at the current version and does *nothing at all* to an existing one.
# That is the right behaviour for a live volume and it means a column added to
# the file is invisible to every database already on disk. This table is the
# other half.
#
# v2 (2026-08-08): the confirmation columns on `recommendations`. Nullable by
# necessity -- rows written before them carry NULL, and the readers fall back to
# `created_ms`, which is exactly the pre-migration behaviour.
#
# v3 (2026-08-08): the idempotency key and the stored response on `orders`.
# Also nullable: every row written before this carries NULL, and SQLite treats
# NULLs as distinct in a UNIQUE index, so the historical rows neither collide
# with each other nor block the constraint.
#
# v6 (2026-08-09): `recommendations.reference_contracts`, which splits "what the
# operator may buy" from "what the evidence record counts". Backfilled rather
# than left NULL, and the backfill is an identity for every row that exists when
# it runs -- see `_BACKFILL_REFERENCE_CONTRACTS` for why that stops being true
# immediately afterwards, which is the point of the column.


@dataclass(frozen=True)
class _Migration:
    """One version step: columns to add, then statements to run.

    Two kinds rather than one because they are made idempotent differently, and
    conflating them is how a half-applied migration becomes unrepeatable.
    `ALTER TABLE ADD COLUMN` raises on a column that already exists, so each is
    guarded by reading `PRAGMA table_info`; a statement carries its own `IF NOT
    EXISTS` and needs no guard. Both must survive a crash mid-step, because the
    version stamp is only written after the whole step succeeds -- so a step
    interrupted halfway re-runs from the top on the next boot.

    Columns run first. An index over a column the same step adds is the obvious
    next thing someone writes here, and it can only work in that order.
    """

    columns: tuple[tuple[str, str, str], ...] = ()
    statements: tuple[str, ...] = ()
    # Index names this step must leave behind, **declared rather than parsed**.
    #
    # Five readers -- `scripts/migrate_db.py` among them, which runs at boot --
    # used to recover the name with
    #
    #     statement.split("EXISTS", 1)[1].split("ON", 1)[0].strip()
    #
    # which silently assumes every statement is `CREATE ... INDEX IF NOT EXISTS
    # <name> ON ...`. It held only while that was the sole kind of statement
    # anyone had written. The first `DROP TABLE IF EXISTS settlements` yields the
    # "index name" `settlements`, which is in no index list, so the boot script
    # reports a missing index and exits 1 -- a crash loop on the volume holding
    # the evidence record, from adding a line to a table in another file.
    #
    # That is the `.dockerignore` allowlist failure exactly: a hand-maintained
    # derivation that is right until the class it derives from gains a second
    # member. The remedy is the same one -- derive nothing, declare it.
    indexes: tuple[str, ...] = ()
    # `(table, column)` pairs whose presence means `statements` has already run.
    #
    # Needed for any step that is not additive. A rebuild -- create the new
    # shape, drop the old table, rename -- is idempotent at every crash point
    # *except* a re-run after full success, where it would recreate the temp
    # table and then drop the real one. Guarding on a column that only exists
    # after the rebuild makes the whole step a no-op once it has landed.
    skip_statements_if_column: tuple[tuple[str, str], ...] = ()
    # How to put the previous shape back, for the migration tests that build an
    # "old" database by undoing the current one. Dropping an index and a column
    # is generic enough to be inferred; restoring a rebuilt table is not, so a
    # step that rebuilds has to say how.
    undo_statements: tuple[str, ...] = ()


# v4 rebuilds `settlements`, which cannot be done with `ALTER TABLE`: the change
# is to a table-level `UNIQUE`, and SQLite's implicit index for one cannot be
# dropped.
#
# **Why the constraint has to go.** It was `UNIQUE (ticker, settled_ms)` -- one
# settlement per market per instant, which is right for a *market outcome* and
# wrong for the *position* the columns beside it describe. Two orders on one
# ticker settle from one market: same ticker, same `settlement_ts`, so the second
# row is rejected and that position silently never settles -- holding its
# exposure open forever. Two orders on one ticker is ordinary, not exotic; a
# quote pass re-recommends a market minutes later and the Board offers both.
#
# The rebuild carries no rows. `settlements` has never had a writer in this
# project's life, which is checked rather than assumed -- `test_store.py`
# asserts the v3 table is empty before the step runs. It is also why this is
# being done now: writing the first row is the last moment the shape is free to
# change.
#
# Idempotent at every crash point, given the `skip_statements_if_column` guard
# on the step:
#   - after CREATE:  `settlements` still lacks `order_id`, so the step re-runs
#                    from the top and the CREATE is a no-op.
#   - after DROP:    `settlements` does not exist, so the guard does not fire;
#                    CREATE and DROP are no-ops and the RENAME completes it.
#   - after RENAME:  `settlements.order_id` exists, so the whole step is skipped
#                    -- which is the case that would otherwise recreate the temp
#                    table and drop the real one.
_SETTLEMENTS_REBUILD = (
    """
    CREATE TABLE IF NOT EXISTS settlements_v4 (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        -- The position this settles. Was absent, so the exposure query released
        -- capital for *every* order on a ticker as soon as any settlement row
        -- for that ticker existed.
        order_id            INTEGER NOT NULL REFERENCES orders(id),
        ticker              TEXT NOT NULL REFERENCES kalshi_markets(ticker),
        -- Kalshi's own `settlement_ts`, observed. Not `close_time` and not
        -- `expiration_time` -- the latter ran three days past close on the
        -- captured sample, so it is not a settlement instant at all.
        settled_ms          INTEGER NOT NULL,
        -- The market's outcome as Kalshi published it: 'yes' or 'no'.
        result              TEXT NOT NULL,
        contracts           INTEGER NOT NULL,
        -- Realised P&L in cents, integer. Float dollars in a money path produce
        -- 7.350000000000001 > 7.35 rejections.
        pnl_cents           INTEGER NOT NULL,
        -- **Paper or real.** Copied from the order rather than joined, so no
        -- reader of this table can pool the two populations by forgetting to.
        dry_run             INTEGER NOT NULL,
        -- The named fill policy this row's P&L was computed under, carried from
        -- the order. Stored so the record can be re-scored under a different
        -- one later; an assumption baked into the arithmetic cannot be revised.
        fill_assumption     TEXT,
        -- Resting size at our price when the order went out, in contracts. It
        -- is what justified assuming the fill, so it is what a re-analysis needs
        -- to weaken the assumption.
        depth_at_order      REAL,
        CHECK (result IN ('yes','no')),
        -- One settlement per position. Replaces UNIQUE (ticker, settled_ms).
        UNIQUE (order_id)
    )
    """,
    "DROP TABLE IF EXISTS settlements",
    "ALTER TABLE settlements_v4 RENAME TO settlements",
    "CREATE INDEX IF NOT EXISTS idx_settlements_order ON settlements(order_id)",
)

# The v3 shape, for the tests that build an old database by undoing the current
# one. Kept verbatim rather than described, because a paraphrase of a DDL is a
# second implementation of it.
_SETTLEMENTS_REBUILD_UNDO = (
    "DROP INDEX IF EXISTS idx_settlements_order",
    "DROP TABLE IF EXISTS settlements",
    """
    CREATE TABLE settlements (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker              TEXT NOT NULL REFERENCES kalshi_markets(ticker),
        settled_ms          INTEGER NOT NULL,
        result              TEXT NOT NULL,
        contracts           INTEGER NOT NULL,
        pnl_cents           INTEGER NOT NULL,
        UNIQUE (ticker, settled_ms)
    )
    """,
)


# v5 tags every row scored at the old 1.0h horizon, and **keeps its score**.
#
# ADR 0011 originally cleared them so they would re-score at the new primary
# horizon. Joe's call was to keep them, and it is the better answer: the gate
# filters on `clv_horizon_hours`, so a row tagged 1.0 is already excluded from
# the primary-horizon count. Clearing them bought nothing the filter was not
# already providing, and it mutated the one record in this project that cannot
# be recreated.
#
# What it costs, stated rather than implied: those rows keep their CLV values
# and are permanently 1.0h observations. `score_recommendations` only fills rows
# where `clv_scored_ms IS NULL`, so they will never be re-scored at 0.0 and will
# never count toward the gate. Kept as record, not as evidence.
#
# Exact rather than assumed: the scoring pass has only ever scored at
# `DEFAULT_HORIZON_HOURS`, and that constant was 1.0 for every release before
# this one -- so every already-scored row on a v4 database was measured at 1.0h.
# The version gate is what makes that safe to rely on: v5 runs only on a v4
# database, which cannot contain a score taken at any other anchor.
#
# Idempotent: re-running writes the same value.
_TAG_THE_OLD_HORIZON = (
    """
    UPDATE recommendations
       SET clv_horizon_hours = 1.0
     WHERE clv_scored_ms IS NOT NULL AND clv_horizon_hours IS NULL
    """,
)


# v6 splits "what may be bought" from "what the record counts".
#
# **Why `suggested_contracts` is the right value to backfill, and it is a claim
# rather than a convenience.** `reference_contracts` is the size at a bankroll
# and caps fixed in code -- $1,000 / $100 / $400 / $100. Every row already in a
# live database was written by a deployment configured with exactly those
# numbers and zero open exposure, so for those rows the two sizings are the same
# computation on the same inputs and the copy is an identity, not an estimate.
#
# It stops being an identity the moment the deployed bankroll changes, which is
# the very next thing that happens. So this backfill is correct for the rows
# that exist when it runs and would be wrong for rows written after it -- which
# is fine, because those rows carry a real `reference_contracts` written by the
# engine. `IS NULL` is what keeps the two apart.
#
# Idempotent: re-running matches no rows the second time.
_BACKFILL_REFERENCE_CONTRACTS = (
    """
    UPDATE recommendations
       SET reference_contracts = suggested_contracts
     WHERE reference_contracts IS NULL
    """,
)


# v10 rebuilds `fills`, which cannot be done with `ALTER TABLE`: the change is
# to a column-level `REFERENCES`, and SQLite has no syntax for dropping a
# foreign key.
#
# **Why the constraint has to go.** `ticker TEXT NOT NULL REFERENCES
# kalshi_markets(ticker)` is right for a fill this tool's own order path
# produced -- the engine only ever recommends a market it discovered. It is
# wrong for a fill polled from `/portfolio/fills`, which is a bet placed by
# hand in the Kalshi app on whatever market a person felt like. `PRAGMA
# foreign_keys = ON` is set in `connect`, so the insert would not merely be
# untidy: it would raise, and the tool would refuse to record a real fill
# because its own discovery had not reached that market. That is the wrong way
# round -- the venue is the authority on what was traded, not us.
#
# `source` is added in the same step because both changes serve one caller. It
# separates the engine's fee-calibration population from hand-placed bets, and
# they answer different questions: one is our order path, the other is a person
# tapping buttons in an app we cannot observe. Pooling them silently is the
# failure this column exists to prevent.
#
# **The rebuild almost certainly carries no rows, and does not assume it.**
# `ORDERS_ARE_DRY_RUNS = True` (`store/orders.py:129`) means this project has
# never placed an order, so nothing has ever written a fill --
# `test_store.py` asserts the v9 table is empty before this step. The copy is
# still written, and written as `INSERT OR IGNORE`, because "no writer exists"
# is a claim about today and a migration outlives it.
#
# Idempotent at every crash point, given the `skip_statements_if_column` guard:
#   - after CREATE:  `fills` still lacks `source`, so the step re-runs from the
#                    top and `CREATE IF NOT EXISTS` is a no-op.
#   - after INSERT:  re-running re-inserts, and every row collides on the
#                    primary key, so `OR IGNORE` makes it a no-op. A plain
#                    INSERT here would raise on the second boot.
#   - after DROP:    `fills` does not exist, so the guard cannot fire; CREATE,
#                    INSERT and DROP are all no-ops and the RENAME completes it.
#   - after RENAME:  `fills.source` exists, so the whole step is skipped --
#                    which is the case that would otherwise recreate the temp
#                    table and drop the real one.
_FILLS_COLUMNS_V9 = (
    "id, kalshi_fill_id, order_id, ticker, filled_ms, count, price_tenths, "
    "is_taker, fee_actual, fee_predicted, fee_model_used"
)

_FILLS_REBUILD = (
    """
    CREATE TABLE IF NOT EXISTS fills_v10 (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        kalshi_fill_id      TEXT UNIQUE,
        order_id            INTEGER REFERENCES orders(id),
        -- The dropped foreign key. See the comment above this constant.
        ticker              TEXT NOT NULL,
        filled_ms           INTEGER NOT NULL,
        count               INTEGER NOT NULL,
        price_tenths        INTEGER NOT NULL,
        is_taker            INTEGER NOT NULL,
        fee_actual          REAL,
        fee_predicted       REAL NOT NULL,
        fee_model_used      TEXT NOT NULL,
        source              TEXT NOT NULL DEFAULT 'engine',
        CHECK (source IN ('engine', 'venue_hand'))
    )
    """,
    # Existing rows are `engine` by construction: the only writer that has ever
    # existed is the order path, and the venue poller does not exist yet at
    # this version.
    f"""
    INSERT OR IGNORE INTO fills_v10 ({_FILLS_COLUMNS_V9}, source)
        SELECT {_FILLS_COLUMNS_V9}, 'engine' FROM fills
    """,
    "DROP TABLE fills",
    "ALTER TABLE fills_v10 RENAME TO fills",
)

# Restoring a rebuilt table cannot be inferred from the step, so it is stated.
# The migration tests build a v9 database by undoing this.
_FILLS_REBUILD_UNDO = (
    """
    CREATE TABLE IF NOT EXISTS fills_v9 (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        kalshi_fill_id      TEXT UNIQUE,
        order_id            INTEGER REFERENCES orders(id),
        ticker              TEXT NOT NULL REFERENCES kalshi_markets(ticker),
        filled_ms           INTEGER NOT NULL,
        count               INTEGER NOT NULL,
        price_tenths        INTEGER NOT NULL,
        is_taker            INTEGER NOT NULL,
        fee_actual          REAL,
        fee_predicted       REAL NOT NULL,
        fee_model_used      TEXT NOT NULL
    )
    """,
    f"""
    INSERT OR IGNORE INTO fills_v9 ({_FILLS_COLUMNS_V9})
        SELECT {_FILLS_COLUMNS_V9} FROM fills
    """,
    "DROP TABLE fills",
    "ALTER TABLE fills_v9 RENAME TO fills",
)


# v11 corrects three things v10 got wrong, and it is a DROP rather than a
# rebuild because these tables provably hold nothing.
#
# **Why dropping is safe here and would not be anywhere else.** `bet_estimates`
# and `venue_settlements` were created by v10 (`79e42aa`) and **no code has
# ever written to either** -- no route, no runner, no script; the poller they
# exist for does not exist yet. `test_store.py` asserts the emptiness rather
# than trusting this paragraph. Dropping them lets `schema.sql` recreate the
# corrected shape on the next `executescript`, which is simpler and has fewer
# crash points than a copy-and-rename of two tables with nothing to copy.
#
# The three corrections, in descending order of how badly v10 was wrong:
#
# **1. `venue_settlements.contracts` was INTEGER and counts are FRACTIONAL.**
# This is the one that would have destroyed data silently. The wire fields are
# `yes_count_fp` / `no_count_fp` -- `_fp` for fixed point, two decimals -- and
# the live record read on 2026-08-18 contains `11.27` and `0.27`. A 0.27
# contract position stored as INTEGER rounds to **0**: an entire position
# vanishing, and the entry price derived from it dividing by zero. v10 declared
# that column from a specification written **before anyone had looked at the
# payload**, which is the whole reason CLAUDE.md requires wire-format work to
# be driven by captured payloads. Now `contracts_hundredths`, exact and
# integer.
#
# **2. `protocol_calibration_bet` is dropped.** The registration excluded bet
# number one on the grounds that the per-fill wire shape had never been
# observed on this account, so one real fill had to be spent learning it. On
# 2026-08-18 `/portfolio/fills` returned **25 real fills** and the shape was
# captured, so the exclusion is vacated and the column has no branch that reads
# it. A field nothing reads is this repo's "built but never called" pattern at
# the smallest possible scale, and it is cheaper to remove now than to explain
# forever.
#
# **3. Three columns are added for the durable outcome path.** `market_result`
# from the **public** market endpoint is preferred over the portfolio's,
# because `/portfolio/settlements` has now been observed to drop history -- 55
# records spanning 2025-11 to 2026-05 were gone eight days later. An outcome
# read only from the portfolio can evaporate; a fact about a market cannot.
# `outcome_source` records which path supplied it, because a silent fallback to
# the perishable source is exactly what would not look like a defect.
#
# `poll_log` and the two new `venue_balance_snapshots` columns need no
# statements here: a brand-new table and an additive column are both handled,
# the first by `schema.sql` on every open and the second by `columns` below.
#
# Idempotent at every crash point:
#   - after the first DROP:  the guard cannot fire (the table is gone), the
#                            remaining DROPs are `IF EXISTS` no-ops, and
#                            `schema.sql` rebuilds both on the same boot.
#   - after both DROPs:      as above.
#   - after the rebuild:     `bet_estimates.outcome_source` exists, so the
#                            whole step is skipped.
_V11_DROP_UNWRITTEN_TABLES = (
    "DROP TABLE IF EXISTS bet_estimates",
    "DROP TABLE IF EXISTS venue_settlements",
)

# Restoring the v10 shape for the migration tests. The indexes come back with
# the tables, so only the tables are stated.
_V11_UNDO = (
    "DROP TABLE IF EXISTS bet_estimates",
    "DROP TABLE IF EXISTS venue_settlements",
    """
    CREATE TABLE venue_settlements (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker                  TEXT NOT NULL,
        event_ticker            TEXT,
        market_result           TEXT,
        settled_ms              INTEGER NOT NULL,
        side                    TEXT NOT NULL,
        contracts               INTEGER NOT NULL,
        entry_price_tenths      INTEGER,
        fee_cost_tenths         INTEGER,
        position_first_seen_ms  INTEGER,
        position_time_source    TEXT,
        is_taker                INTEGER,
        n_fills_in_position     INTEGER,
        UNIQUE (ticker, settled_ms),
        CHECK (side IN ('yes', 'no')),
        CHECK (is_taker IS NULL OR is_taker IN (0, 1))
    )
    """,
    """
    CREATE TABLE bet_estimates (
        id                          INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker                      TEXT NOT NULL,
        stated_probability_bp       INTEGER NOT NULL,
        estimate_server_ms          INTEGER NOT NULL,
        estimate_client_ms          INTEGER,
        had_already_opened_kalshi   INTEGER,
        cluster_key                 TEXT NOT NULL,
        server_yes_bid_tenths       INTEGER,
        server_yes_ask_tenths       INTEGER,
        server_quote_observed_ms    INTEGER,
        server_quote_unreadable_reason TEXT,
        stated_probability_is_revised  INTEGER NOT NULL DEFAULT 0,
        protocol_calibration_bet    INTEGER NOT NULL DEFAULT 0,
        is_in_play                  INTEGER NOT NULL DEFAULT 0,
        is_sports                   INTEGER NOT NULL DEFAULT 1,
        is_multi_leg                INTEGER NOT NULL DEFAULT 0,
        sport                       TEXT,
        matched_position_id         INTEGER REFERENCES venue_settlements(id),
        match_status                TEXT,
        outcome_win                 INTEGER,
        closing_line_id             INTEGER REFERENCES closing_lines(id),
        clv_tenths                  REAL,
        clv_horizon_hours           REAL,
        clv_scored_ms               INTEGER,
        CHECK (stated_probability_bp BETWEEN 1 AND 9999),
        CHECK (outcome_win IS NULL OR outcome_win IN (0, 1)),
        CHECK (had_already_opened_kalshi IS NULL
               OR had_already_opened_kalshi IN (0, 1))
    )
    """,
)


# v12 makes both fractional quantities REAL, which is what this schema's own
# conventions block has said since the first commit:
#
#     QUANTITIES are REAL. Kalshi returns fractional sizes ("17.38"); 42 of 152
#     sampled order book levels were fractional. An INTEGER column here would
#     silently truncate depth.
#
# Two corrections, and the second one is mine.
#
# **`fills.count` was INTEGER and venue fills are fractional.** The captured
# payload has a `count_fp` of `0.27`; as INTEGER that is **zero**, and a fill of
# zero contracts at a real price is a row asserting that a trade did not happen.
# v11 fixed this defect in `venue_settlements` and missed it here, because the
# fix was applied to the table the mistake was noticed in rather than to every
# table holding the same quantity.
#
# **`venue_settlements.contracts_hundredths` was my invention and it is
# withdrawn.** Faced with a fractional count, v11 reached for integer
# hundredths by analogy with the money rule -- integer tenths of a cent -- and
# in doing so introduced a *third* numeric convention into a file that already
# had exactly two and stated both at the top. The money rule exists because
# money math must be exact; the quantity rule already existed and already
# covers this. Consistency with a documented convention beats a locally clever
# encoding, and a future reader should find one answer to "how are sizes
# stored", not two.
#
# **Why this is safe now and would not be in a month.** Neither table has a
# production writer: `ORDERS_ARE_DRY_RUNS = True`, `venue_settlements` was
# created two commits ago, and the poller is the commit after this one. A test
# asserts the emptiness rather than trusting this paragraph.
#
# Idempotent at every crash point by the same reasoning as v10: `INSERT OR
# IGNORE` makes the copy re-runnable, and the guard makes the whole step a
# no-op once the rename has landed.
_FILLS_COLUMNS_V12 = (
    "id, kalshi_fill_id, order_id, ticker, filled_ms, count, price_tenths, "
    "is_taker, fee_actual, fee_predicted, fee_model_used, source"
)

_QUANTITIES_ARE_REAL = (
    """
    CREATE TABLE IF NOT EXISTS fills_v12 (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        kalshi_fill_id      TEXT UNIQUE,
        order_id            INTEGER REFERENCES orders(id),
        ticker              TEXT NOT NULL,
        filled_ms           INTEGER NOT NULL,
        count               REAL NOT NULL,
        price_tenths        INTEGER NOT NULL,
        is_taker            INTEGER NOT NULL,
        fee_actual          REAL,
        fee_predicted       REAL NOT NULL,
        fee_model_used      TEXT NOT NULL,
        source              TEXT NOT NULL DEFAULT 'engine',
        CHECK (source IN ('engine', 'venue_hand'))
    )
    """,
    f"""
    INSERT OR IGNORE INTO fills_v12 ({_FILLS_COLUMNS_V12})
        SELECT {_FILLS_COLUMNS_V12} FROM fills
    """,
    "DROP TABLE fills",
    "ALTER TABLE fills_v12 RENAME TO fills",
    # `venue_settlements` has never been written, so it is dropped and left for
    # `schema.sql` to rebuild rather than copied. See the v11 note for why that
    # is defensible here and nowhere else.
    "DROP TABLE IF EXISTS venue_settlements",
)

_QUANTITIES_ARE_REAL_UNDO = (
    """
    CREATE TABLE IF NOT EXISTS fills_v11 (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        kalshi_fill_id      TEXT UNIQUE,
        order_id            INTEGER REFERENCES orders(id),
        ticker              TEXT NOT NULL,
        filled_ms           INTEGER NOT NULL,
        count               INTEGER NOT NULL,
        price_tenths        INTEGER NOT NULL,
        is_taker            INTEGER NOT NULL,
        fee_actual          REAL,
        fee_predicted       REAL NOT NULL,
        fee_model_used      TEXT NOT NULL,
        source              TEXT NOT NULL DEFAULT 'engine',
        CHECK (source IN ('engine', 'venue_hand'))
    )
    """,
    # **Copies the v9 column list, not v12s, and `source` is left to its
    # DEFAULT.** The migration tests wind a database back by applying every
    # undo in ASCENDING version order, so v10s undo -- which rebuilds `fills`
    # without `source` -- runs before this one. Naming `source` here raises
    # `no such column` on every wind-back past v10. Nothing is lost: at v11 the
    # only writer that could exist is the order path, so every row is
    # `engine`, which is what the DEFAULT supplies.
    f"""
    INSERT OR IGNORE INTO fills_v11 ({_FILLS_COLUMNS_V9})
        SELECT {_FILLS_COLUMNS_V9} FROM fills
    """,
    "DROP TABLE fills",
    "ALTER TABLE fills_v11 RENAME TO fills",
    "DROP TABLE IF EXISTS venue_settlements",
    """
    CREATE TABLE venue_settlements (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker                  TEXT NOT NULL,
        event_ticker            TEXT,
        market_result           TEXT,
        settled_ms              INTEGER NOT NULL,
        side                    TEXT NOT NULL,
        contracts_hundredths    INTEGER NOT NULL,
        entry_price_tenths      INTEGER,
        fee_cost_tenths         INTEGER,
        position_first_seen_ms  INTEGER,
        position_time_source    TEXT,
        is_taker                INTEGER,
        n_fills_in_position     INTEGER,
        UNIQUE (ticker, settled_ms),
        CHECK (side IN ('yes', 'no')),
        CHECK (is_taker IS NULL OR is_taker IN (0, 1))
    )
    """,
)


_MIGRATIONS: dict[int, _Migration] = {
    2: _Migration(
        columns=(
            ("recommendations", "last_confirmed_ms", "INTEGER"),
            ("recommendations", "last_confirmed_quote_age_ms", "INTEGER"),
            ("recommendations", "last_confirmed_odds_age_ms", "INTEGER"),
        ),
    ),
    3: _Migration(
        columns=(
            ("orders", "idempotency_key", "TEXT"),
            ("orders", "response_body_json", "TEXT"),
        ),
        statements=(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_idempotency "
            "ON orders(idempotency_key)",
        ),
        indexes=("idx_orders_idempotency",),
    ),
    5: _Migration(
        columns=(("recommendations", "clv_horizon_hours", "REAL"),),
        statements=_TAG_THE_OLD_HORIZON,
        undo_statements=(
            # Dropping the column takes the tag with it, which is the whole of
            # what this step writes. Nothing else to undo -- stated rather than
            # left blank so a future reader does not think it was forgotten.
        ),
    ),
    6: _Migration(
        columns=(("recommendations", "reference_contracts", "INTEGER"),),
        statements=_BACKFILL_REFERENCE_CONTRACTS,
        undo_statements=(
            # Dropping the column takes the backfill with it, which is the whole
            # of what this step writes. Stated rather than left blank so a future
            # reader does not think it was forgotten.
        ),
    ),
    4: _Migration(
        columns=(
            ("orders", "fill_assumption", "TEXT"),
            ("orders", "assumed_filled_count", "INTEGER"),
        ),
        statements=_SETTLEMENTS_REBUILD,
        indexes=("idx_settlements_order",),
        # `order_id` exists only after the rebuild has completed, so this is the
        # sentinel that makes the rebuild a no-op on a database already at v4.
        skip_statements_if_column=(("settlements", "order_id"),),
        undo_statements=_SETTLEMENTS_REBUILD_UNDO,
    ),
    # v7 -- player props. A prop's outcome is (player, side, line); the first
    # component had nowhere to live, so `odds_snapshots` and `fair_prices` gain
    # a nullable `outcome_description`.
    #
    # Nullable and added rather than backfilled: every existing row is a team
    # market, where the column is meaningless. A backfill would have to invent a
    # value, and the honest value is "this row has no player".
    7: _Migration(
        columns=(
            ("odds_snapshots", "outcome_description", "TEXT"),
            ("fair_prices", "outcome_description", "TEXT"),
        ),
        undo_statements=(
            # Dropping the columns takes everything this step wrote. Stated
            # rather than left blank so a future reader does not think it was
            # forgotten.
        ),
    ),
    # v8 -- the Kalshi side of the same prop. v7 gave the *books'* player a home
    # (`outcome_description`); this gives Kalshi's.
    #
    # **One column, not two.** The obvious second is the threshold, and it is
    # not needed: Kalshi publishes `floor_strike` on a `N+` prop as `N - 0.5`,
    # which is exactly the `point` a sportsbook quotes for the same rung, and
    # `kalshi_markets.strike` already stores it. Measured 259 of 259 on
    # `tests/fixtures/events_mlb_props_nested.json`. A `threshold` column would
    # be a second representation of one number, derived by arithmetic, and the
    # two would be free to disagree.
    #
    # Nullable and not backfilled, for v7's reason: every existing row is a team
    # market and the honest value there is "this row has no player".
    8: _Migration(
        columns=(("kalshi_markets", "player_name", "TEXT"),),
        undo_statements=(
            # Dropping the column takes everything this step wrote.
        ),
    ),
    # v9 -- what asked for this call, so a tap cannot be read as a schedule.
    #
    # **This column exists to be excluded, not to be reported.** The on-demand
    # refresh (`backend/odds/ondemand.py`) makes exactly the same
    # `/sports/{sport}/odds` request the planner makes, at the same cost, and
    # `_SERVED_SWEEP` in `odds/timing.py` identifies a served sweep by endpoint
    # and cost alone. Without a way to tell them apart, a tap five seconds
    # before a slot opened would move `last_sweep_by_sport` past
    # `slot.fire_from_ms`, `firing_for_slot` would return `REFRESH` instead of
    # `SCHEDULED` for the rest of that window, and **props ride the opening
    # call only** -- so one tap would silently cost that cluster its entire
    # prop purchase, for the day, with no row anywhere saying so.
    #
    # That is `odds_sweep_log`'s founding defect one table along: a state with
    # no representation is a state nothing can refuse.
    #
    # Nullable and not backfilled. Every row written before this was a planner
    # call, and the honest value for it is "nobody recorded"; `_SERVED_SWEEP`
    # reads `COALESCE(trigger, '')` so a NULL keeps counting as a sweep, which
    # is what those rows are. Backfilling `'scheduled'` would assert a fact
    # about history that this column was not there to observe.
    13: _Migration(
        # ADR 0055. Nullable with no backfill on purpose: every reader uses
        # COALESCE(confirmed_ms, observed_ms), so a pre-ADR row reads exactly
        # as it did before. That makes the deploy reversible without rewriting
        # 6M rows on a box already missing its cadence.
        columns=(("kalshi_quotes", "confirmed_ms", "INTEGER"),),
        undo_statements=(
            # Dropping the column takes everything this step wrote.
        ),
    ),
    14: _Migration(
        # Amendment 2 (A11) of the calibration registration: when was this
        # row's `match_status` written? The absence proof needs a settlements
        # poll that POSTDATES the matcher first seeing the market's result,
        # and this column is the record of that moment. Nullable, no backfill:
        # a pre-amendment stamp genuinely has no observed instant, and the
        # repair pass (A12) re-buckets those rows rather than inventing one.
        columns=(("bet_estimates", "match_status_ms", "INTEGER"),),
        undo_statements=(
            # Dropping the column takes everything this step wrote.
        ),
    ),
    15: _Migration(
        # Amendment 3 (A13): the position-side match verdict, on the table
        # where a position actually lives. The registered enum put
        # 'position_unlogged' on bet_estimates, and a position with no
        # estimate has no bet_estimates row to carry it -- the coverage
        # denominator's complement had nowhere to be written. Nullable, no
        # backfill: NULL is "not yet examined" and the match pass stamps
        # every in-scope row on its next run.
        columns=(("venue_settlements", "estimate_match_status", "TEXT"),),
        undo_statements=(
            # Dropping the column takes everything this step wrote.
        ),
    ),
    16: _Migration(
        # ADR 0058's basis marker: which fee model computed a settlement's
        # pnl_cents. Nullable, no backfill -- NULL is the honest value for
        # every row written under the flat 0.070 model before the marker
        # existed, and it IS the regime boundary a cross-model comparison
        # must respect. The settlement pass stamps every row it writes from
        # this version on.
        columns=(("settlements", "fee_model_used", "TEXT"),),
        undo_statements=(
            # Dropping the column takes everything this step wrote.
        ),
    ),
    12: _Migration(
        statements=_QUANTITIES_ARE_REAL,
        indexes=("idx_fills_time", "idx_fills_mismatch"),
        skip_statements_if_column=(("venue_settlements", "contracts"),),
        undo_statements=_QUANTITIES_ARE_REAL_UNDO,
    ),
    # v11 carries NO `columns` entry, and the blank is load-bearing. It used to
    # add `portfolio_value_tenths` to `venue_balance_snapshots` -- a table that
    # did not exist before v10's schema, so on the real v9 LIVE volume the
    # `ALTER TABLE` raised `no such table` inside `init_db`, before the schema
    # file (which creates it, complete) had run. That was a crash loop at boot
    # on the one database that cannot be recreated, found by the deploy and not
    # by the suite: every test fixture builds from the current schema first, so
    # the table always existed before the wind-back -- the exact
    # fresh-fixture-vs-production gap `init_db`'s own docstring describes. The
    # column needs no migration at all: no deployed database ever ran the
    # v11-era schema, and `executescript` creates the table fully formed.
    11: _Migration(
        statements=_V11_DROP_UNWRITTEN_TABLES,
        skip_statements_if_column=(("bet_estimates", "outcome_source"),),
        undo_statements=_V11_UNDO,
    ),
    10: _Migration(
        statements=_FILLS_REBUILD,
        indexes=("idx_fills_time", "idx_fills_mismatch"),
        # `source` exists only after the rebuild completes, so this is the
        # sentinel that makes the whole step a no-op on a database already at
        # v10 -- the one crash point where re-running would recreate the temp
        # table and then drop the real one.
        skip_statements_if_column=(("fills", "source"),),
        undo_statements=_FILLS_REBUILD_UNDO,
    ),
    9: _Migration(
        columns=(("api_credits", "trigger", "TEXT"),),
        undo_statements=(
            # Dropping the column takes everything this step wrote.
        ),
    ),
    17: _Migration(
        # The token meter (2026-08-21 partner ruling, betting-desk item 6):
        # the 24-call daily cap meters calls, and a scout-desk call with the
        # web-search tool can spend up to 6 searches and an unbounded prompt
        # inside one call -- spend the meter could not see. `settle` now
        # writes what the API's usage block reported. Nullable, no backfill:
        # every pre-v17 row genuinely did not observe its usage, and NULL is
        # the honest value ("unreadable resolves to None, never 0").
        columns=(
            ("agent_calls", "input_tokens", "INTEGER"),
            ("agent_calls", "output_tokens", "INTEGER"),
            ("agent_calls", "web_searches", "INTEGER"),
        ),
        undo_statements=(
            # Dropping the columns takes everything this step wrote.
        ),
    ),
    18: _Migration(
        # The venue's own order id on each fill (D3 of the 2026-08-22 plan,
        # ADR 0063): `/portfolio/fills` carries `order_id` on every captured
        # row and `parse_fill` discarded it, so a portal-placed order's fill
        # landed labelled `venue_hand` with nothing joining it back to the
        # `manual_orders` row that caused it. Nullable, no backfill: pre-v18
        # rows genuinely did not record it, and NULL is the honest value.
        columns=(
            ("fills", "venue_order_id", "TEXT"),
        ),
        undo_statements=(),
    ),
    19: _Migration(
        # Willy Balters' seat at the scout desk (ADR 0069): the pro-bettor
        # persona's `SharpTake`, filed per convening beside the staff's and
        # master's work. Nullable, no backfill: a pre-v19 briefing genuinely
        # predates the seat, and NULL — never `{}` — is the honest value for
        # "the seat filed nothing here".
        columns=(
            ("scout_briefings", "sharp_json", "TEXT"),
        ),
        undo_statements=(),
    ),
    20: _Migration(
        # The parlay desk (ADR 0070): a consensus row's own input freshness.
        # `computed_ms` says when the devig ran; the oldest contributing book
        # quote was already older than that by up to a sweep interval, and a
        # reader computing the row's live age needs both terms. Nullable, no
        # backfill: pre-v20 rows genuinely did not record it, and NULL makes
        # the reader refuse the row as unmeasurable — never age zero.
        # (`parlay_lookups` is a new table and rides `schema.sql`'s
        # IF NOT EXISTS, like `scout_briefings` before it.)
        columns=(
            ("fair_prices", "oldest_book_age_ms", "INTEGER"),
        ),
        undo_statements=(),
    ),
    21: _Migration(
        # A failed odds call stops reading as a fresh one.
        #
        # `odds/client.py` records the credit before checking the status, which
        # is right -- some error classes still consume credits and undercounting
        # spend is worse than overcounting it. What was wrong is downstream: the
        # row it wrote satisfied `_SERVED_SWEEP`, so a 401 moved that sport's
        # last-sweep stamp to now and deferred the retry by a whole refresh
        # interval. An outage presented on the screen as *fresh*.
        #
        # Nullable, no backfill. NULL is the honest value for a pre-v21 row --
        # nobody recorded a status -- and `_SERVED_SWEEP`'s
        # `COALESCE(http_status, 200) < 400` makes every one of them count
        # exactly as it counts today. A backfill would have to invent the
        # statuses, and the rows this matters for are precisely the ones whose
        # status is unknowable after the fact.
        #
        # (`desk_attention` is also a v21 addition and appears nowhere here: it
        # is a new table, so it rides `schema.sql`'s `IF NOT EXISTS` along with
        # its index, exactly as `parlay_lookups` did at v20. `migrate` returns
        # before `init_db` applies the schema file in the same boot.)
        columns=(
            ("api_credits", "http_status", "INTEGER"),
        ),
        # And the sweep log gains a fifth outcome to say so with.
        #
        # A rebuild rather than an ALTER, because the vocabulary is a table-level
        # CHECK and SQLite cannot alter one in place. `_SETTLEMENTS_REBUILD` is
        # the precedent; this one carries its rows, which that one did not, so
        # the INSERT is part of the step.
        #
        # Idempotent at every crash point, given `skip_statements_if_column`:
        #   - after CREATE:  `odds_sweep_log` still lacks `failed_status`, so
        #                    the step re-runs from the top and CREATE is a no-op.
        #   - after INSERT:  same -- the temp table is dropped and rebuilt, and
        #                    it is the temp table that carries the new column.
        #   - after RENAME:  `odds_sweep_log.failed_status` exists and the whole
        #                    step is skipped, which is the case that would
        #                    otherwise recreate the temp table and drop the real
        #                    one.
        statements=(
            """
            CREATE TABLE IF NOT EXISTS odds_sweep_log_v21 (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                pass_ms         INTEGER NOT NULL,
                sport_key       TEXT,
                outcome         TEXT NOT NULL,
                detail          TEXT NOT NULL,
                quotes_stored   INTEGER,
                -- The upstream status, present only on a `failed` row. Its
                -- presence is also the migration's completion guard.
                failed_status   INTEGER,
                CHECK (outcome IN
                       ('served', 'refused', 'no_data', 'skipped', 'failed')),
                CHECK ((outcome = 'served') = (quotes_stored IS NOT NULL)),
                CHECK ((outcome = 'failed') OR (failed_status IS NULL))
            )
            """,
            "INSERT INTO odds_sweep_log_v21 "
            "(id, pass_ms, sport_key, outcome, detail, quotes_stored) "
            "SELECT id, pass_ms, sport_key, outcome, detail, quotes_stored "
            "FROM odds_sweep_log",
            "DROP TABLE odds_sweep_log",
            "ALTER TABLE odds_sweep_log_v21 RENAME TO odds_sweep_log",
            "CREATE INDEX IF NOT EXISTS idx_sweep_log_time "
            "ON odds_sweep_log(pass_ms DESC)",
        ),
        indexes=("idx_sweep_log_time",),
        skip_statements_if_column=(("odds_sweep_log", "failed_status"),),
        # Putting the four-outcome vocabulary back, for the migration tests that
        # build a v20 database by undoing this step. A rebuild is not inferable,
        # so it is spelled out -- and `failed` rows cannot survive the trip,
        # which is correct: they could not have existed at v20.
        undo_statements=(
            """
            CREATE TABLE odds_sweep_log_v20 (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                pass_ms         INTEGER NOT NULL,
                sport_key       TEXT,
                outcome         TEXT NOT NULL,
                detail          TEXT NOT NULL,
                quotes_stored   INTEGER,
                CHECK (outcome IN ('served', 'refused', 'no_data', 'skipped')),
                CHECK ((outcome = 'served') = (quotes_stored IS NOT NULL))
            )
            """,
            "INSERT INTO odds_sweep_log_v20 "
            "(id, pass_ms, sport_key, outcome, detail, quotes_stored) "
            "SELECT id, pass_ms, sport_key, outcome, detail, quotes_stored "
            "FROM odds_sweep_log WHERE outcome != 'failed'",
            "DROP TABLE odds_sweep_log",
            "ALTER TABLE odds_sweep_log_v20 RENAME TO odds_sweep_log",
            "CREATE INDEX IF NOT EXISTS idx_sweep_log_time "
            "ON odds_sweep_log(pass_ms DESC)",
        ),
    ),
}


def now_ms() -> int:
    """Current UTC time in epoch milliseconds.

    The single source of "now" for the whole backend. Times are integers in
    UTC everywhere — see the schema header for why naive local datetimes are
    banned.
    """
    return int(time.time() * 1000)


class SchemaVersionMismatch(RuntimeError):
    """Raised when the database on disk was written by a different schema."""


def connect(
    db_path: Path | str,
    *,
    read_only: bool = False,
    cross_thread: bool = False,
) -> sqlite3.Connection:
    """Open a connection with the pragmas the schema expects.

    `row_factory` is set to `sqlite3.Row` so call sites read columns by name.
    Positional access to a widening table is how a price column and a quantity
    column swap places without anything erroring.

    **`cross_thread` disables sqlite3's same-thread guard, and defaults to off.**
    Turn it on only where the connection is genuinely used by one thread at a
    time and merely *created* on a different one. The one caller that needs it
    is the API's per-request dependency: FastAPI runs a sync dependency and a
    sync path operation on two different threadpool workers, so a connection
    opened in `get_conn` is used from another thread and raises

        sqlite3.ProgrammingError: SQLite objects created in a thread can only
        be used in that same thread

    on roughly half of all requests. It does not show under light local load,
    because an idle threadpool tends to reuse one worker -- it appeared only on
    the deployed instance, where a 30-second health check runs alongside real
    traffic and spreads the work across workers.

    Left ON everywhere else on purpose. The guard is real protection for a
    connection shared between *concurrent* users, and disabling it globally
    would turn a loud error into a silent race in the writer paths.
    """
    path = Path(db_path)
    timeout_s = BUSY_TIMEOUT_MS / 1000.0
    if read_only:
        conn = sqlite3.connect(
            f"file:{path}?mode=ro",
            uri=True,
            check_same_thread=not cross_thread,
            # Readers get it too: WAL lets a reader run alongside a writer, but
            # not alongside a checkpoint.
            timeout=timeout_s,
        )
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            path, check_same_thread=not cross_thread, timeout=timeout_s
        )

    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if not read_only:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def migrate(conn: sqlite3.Connection) -> list[int]:
    """Bring an existing database up to `SCHEMA_VERSION`. Returns versions run.

    Two guards, and they answer different questions, which is why there are two:

    - **The recorded version decides which migrations run.** A database that
      says v1 gets v2 and nothing else. This is the check that would refuse to
      apply a v3 step to a v5 database rather than guessing.
    - **Each step is individually idempotent.** `ALTER TABLE ADD COLUMN` raises
      on a column that already exists, so a crash between the last `ALTER` and
      the version bump would leave a database that can never be opened again.
      The volume holding the live record cannot be re-created, so a
      half-finished migration has to be resumable.

    Returning to the version stamp only after every step succeeds is deliberate:
    an interrupted migration stays at its old version and re-runs, rather than
    claiming a version it does not have.
    """
    found = get_meta(conn, "schema_version")
    if found is None:
        # No stamp means `executescript` just built this database from the
        # current `schema.sql`, so it is already at SCHEMA_VERSION. Running the
        # migrations here would try to add columns the file already declared.
        return []

    applied: list[int] = []
    for version in sorted(_MIGRATIONS):
        if version <= int(found):
            continue
        step = _MIGRATIONS[version]
        for table, column, decl in step.columns:
            existing = _columns(conn, table)
            if not existing:
                # The table is missing mid-migration. Only one thing does
                # that: an earlier step dropped it for `schema.sql` to
                # rebuild -- v11's documented design -- and `init_db` applies
                # the schema file right after this loop, in the same boot.
                # The file carries every migrated column (the agreement is
                # itself under test), so ALTERing a table that is about to be
                # recreated complete is both impossible and unnecessary.
                continue
            if column in existing:
                continue
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
        # A non-additive step says how to tell that it has already run. Without
        # this a rebuild is idempotent everywhere except after full success,
        # where re-running it would drop the table it just built.
        already = any(
            column in _columns(conn, table)
            for table, column in step.skip_statements_if_column
        )
        if not already:
            for statement in step.statements:
                conn.execute(statement)
        applied.append(version)

    if applied:
        conn.commit()
    return applied


def init_db(db_path: Path | str) -> sqlite3.Connection:
    """Create or open the database, applying the schema and any migrations.

    **The migration runs before the schema file, and the order is load-bearing.**
    It used to be the other way round, which worked for as long as every
    migration only added columns. It stops working the moment `schema.sql`
    declares an index over one of them: `executescript` is applied to existing
    databases too, so `CREATE UNIQUE INDEX ... ON orders(idempotency_key)` runs
    against a database that has not been given that column yet and raises
    `no such column`. On the live volume that is an exception inside the boot
    step the entrypoint runs before uvicorn -- a crash loop, on the one database
    in this project that cannot be recreated.

    It is worth being precise about why no test would have caught it in the old
    order: a **fresh** database gets the column from `CREATE TABLE`, so the
    index resolves and everything passes. The failure needs a database that
    already exists, which is exactly the thing a test fixture usually does not
    have and production always does.

    Migrating first fixes it at the root rather than by reordering `schema.sql`:
    after the columns are in place, every `IF NOT EXISTS` in the schema file is
    a genuine no-op on an existing database, which is what it was always meant
    to be.
    """
    conn = connect(db_path)
    migrate(conn)
    conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
    _set_meta(conn, "schema_version", str(SCHEMA_VERSION))
    conn.commit()
    return conn


def open_db(
    db_path: Path | str,
    *,
    read_only: bool = False,
    cross_thread: bool = False,
) -> sqlite3.Connection:
    """Open an existing database, refusing on a schema-version mismatch."""
    conn = connect(db_path, read_only=read_only, cross_thread=cross_thread)
    found = get_meta(conn, "schema_version")
    if found is None:
        conn.close()
        raise SchemaVersionMismatch(
            f"{db_path} has no schema_version. It was not created by init_db(), "
            "so its column semantics are unknown. Refusing to read it."
        )
    if int(found) != SCHEMA_VERSION:
        conn.close()
        raise SchemaVersionMismatch(
            f"{db_path} is schema v{found}, this code expects v{SCHEMA_VERSION}. "
            "Column meanings may differ between versions (v1 of the previous "
            "project stored whole cents where v2 stored tenths). Migrate "
            f"explicitly rather than reading across versions:\n"
            f"    python scripts/migrate_db.py --db {db_path}"
        )
    return conn


def get_meta(conn: sqlite3.Connection, key: str) -> Optional[str]:
    """The stored value, or `None` if it -- or the table itself -- is absent.

    A missing `meta` table means the file is empty and `schema.sql` has not run
    yet, which `init_db` now reaches *before* applying the schema. Answering
    `None` rather than raising keeps "there is nothing recorded here" as one
    state with one meaning, instead of splitting it into an absent row and an
    absent table that callers would have to tell apart.
    """
    try:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = ?", (key,)
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    return row["value"] if row else None


def latest_balance_tenths(conn: sqlite3.Connection) -> Optional[int]:
    """The newest observed account balance, in tenths. `None`, never 0.

    Reads the newest `venue_balance_snapshots` row -- the operational clock of
    A7, written by the poller every 5 minutes from the venue's own
    `balance_dollars` string. The newest row verbatim, deliberately: if the
    latest observation could not read the balance (`balance_tenths` NULL),
    the answer is "unknown", not the last value that happened to parse --
    falling back to an older row would hide exactly the outage that makes the
    number stale. Sizing refuses on `None` (ADR 0045).
    """
    try:
        row = conn.execute(
            "SELECT balance_tenths FROM venue_balance_snapshots "
            "ORDER BY observed_ms DESC, id DESC LIMIT 1"
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    return row["balance_tenths"] if row else None


#: `meta` key holding the wall clock of the last quote-recorder write.
#:
#: **This exists because ADR 0055 broke the signal it replaces.** Recorder
#: liveness was "the newest row in `kalshi_quotes`", which was exact while every
#: pass wrote ~6,000 rows and is wrong the moment the table becomes a change
#: log: a quiet slate legitimately writes nothing, and a dead recorder writes
#: nothing, and the health endpoint could not tell those apart.
RECORDER_HEARTBEAT_KEY = "recorder_last_write_ms"


def set_recorder_heartbeat(conn: sqlite3.Connection, stamp: int) -> None:
    """Record that the quote recorder completed a write at `stamp`.

    One row, keyed, upserted once per pass. Deliberately **not** a `MAX()` over
    `kalshi_quotes`: that aggregate walks the whole covering index, and shipping
    it to `/api/health` took the live instance down in four minutes (a08c1a9).
    A primary-key lookup cannot repeat that.
    """
    _set_meta(conn, RECORDER_HEARTBEAT_KEY, str(int(stamp)))


def recorder_last_write_ms(conn: sqlite3.Connection) -> Optional[int]:
    """The heartbeat above, or `None` if the recorder has never written.

    `None` on a fresh volume, and on a database whose last pass predates ADR
    0055. Callers must treat it as "unknown", never as "now" -- an unreadable
    heartbeat that resolved to the current time would report perfect health for
    a recorder that has never run.
    """
    raw = get_meta(conn, RECORDER_HEARTBEAT_KEY)
    return int(raw) if raw is not None else None


def record_loop_failure(
    conn: sqlite3.Connection,
    *,
    failed_ms: int,
    pass_number: int,
    consecutive_failures: int,
    error: str,
    pass_kind: Optional[str] = None,
) -> None:
    """Record that a recording-loop pass raised.

    **Written on the failure path only, never on success.** The success side
    already has `set_recorder_heartbeat` above, and writing both here would
    destroy this table's most useful reading: across a silent stretch, rows
    mean the loop was failing and *no* rows mean it was wedged or gone. A pass
    that hangs never returns to raise, so it cannot write here -- the silence
    is the evidence.

    Commits immediately rather than riding the caller's transaction. A failure
    record that is rolled back with the failing pass is not a record, and the
    case this exists for is precisely the one where the process does not get
    to commit anything else.
    """
    conn.execute(
        "INSERT INTO loop_failures (failed_ms, pass_number, "
        "consecutive_failures, pass_kind, error) VALUES (?, ?, ?, ?, ?)",
        (
            int(failed_ms), int(pass_number), int(consecutive_failures),
            pass_kind, error,
        ),
    )
    conn.commit()


def loop_failures_since(
    conn: sqlite3.Connection, *, since_ms: int
) -> list[sqlite3.Row]:
    """Every recorded pass failure at or after `since_ms`, oldest first.

    Oldest first because the question this answers is "what happened across
    that gap", and a run of failures reads forwards.
    """
    return list(
        conn.execute(
            "SELECT failed_ms, pass_number, consecutive_failures, pass_kind, "
            "error FROM loop_failures WHERE failed_ms >= ? "
            "ORDER BY failed_ms ASC",
            (int(since_ms),),
        )
    )


def _set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta (key, value, updated_ms) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
        "updated_ms = excluded.updated_ms",
        (key, value, now_ms()),
    )


# ---------------------------------------------------------------------------
# Derived asks
# ---------------------------------------------------------------------------
# Kalshi publishes YES bids and NO bids only. Asks are derived, and this is the
# only place that derivation happens, so a caller cannot accidentally treat a
# mid as a tradeable price.


def derive_yes_ask(no_bid_tenths: Optional[int]) -> Optional[int]:
    """The price you would pay to buy YES, from the best NO bid.

    Returns None when there is no NO bid — meaning nobody is offering to sell
    you YES at any price. That is *not* a free or zero-cost fill, so it must
    not collapse to a number.
    """
    if no_bid_tenths is None:
        return None
    return 1000 - int(no_bid_tenths)


def derive_no_ask(yes_bid_tenths: Optional[int]) -> Optional[int]:
    """The price you would pay to buy NO, from the best YES bid."""
    if yes_bid_tenths is None:
        return None
    return 1000 - int(yes_bid_tenths)


def ask_for_side(row: sqlite3.Row | dict, side: str) -> Optional[int]:
    """The price actually payable for `side` on a quote row.

    Every EV calculation and every bucketing decision in this project goes
    through here. Bucketing on the mid while transacting at the ask is how the
    previous project produced a +25.4 point 'edge' that lost $4.92 a market.
    """
    if side == "yes":
        return derive_yes_ask(row["no_bid_tenths"])
    if side == "no":
        return derive_no_ask(row["yes_bid_tenths"])
    raise ValueError(f"side must be 'yes' or 'no', got {side!r}")
