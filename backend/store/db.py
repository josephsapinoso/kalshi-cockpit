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

SCHEMA_VERSION = 5
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


# v5 returns every row scored at the old 1.0h horizon to the scoring queue.
#
# **This mutates the evidence record, which is why it is spelled out here.** ADR
# 0011 moves the primary horizon to 0.0, and those rows hold a value measured
# against 1.0h -- which is now the *control* horizon. Leaving them would put
# control-horizon numbers in the primary column for ~34 rows, the exact silent
# mixture the new `clv_horizon_hours` column exists to prevent.
#
# Nothing is destroyed and the operation is reversible: their `closing_lines`
# rows at 1.0h are untouched, so the old scores can be recomputed from the
# database at any time. `closing_line_id` is cleared with the rest because a
# pointer to a line the row is no longer scored against is worse than none.
#
# Naturally idempotent -- after it runs, no row matches the predicate -- so this
# step needs no `skip_statements_if_column` guard. It is safe under the version
# gate for the reason that gate exists: v5 runs only on a database at v4, and a
# v4 database cannot contain a score taken at any horizon but 1.0, because 1.0
# is the only value `DEFAULT_HORIZON_HOURS` has ever had.
_UNSCORE_THE_OLD_HORIZON = (
    """
    UPDATE recommendations
       SET clv_tenths = NULL, closing_line_id = NULL, clv_scored_ms = NULL
     WHERE clv_scored_ms IS NOT NULL
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
        statements=_UNSCORE_THE_OLD_HORIZON,
        undo_statements=(
            # Nothing to undo. The clearing is not reversible from this table --
            # and does not need to be, because `closing_lines` keeps every line
            # it was scored against. Stated rather than left blank, so a future
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
            if column in _columns(conn, table):
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
