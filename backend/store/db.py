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
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = 2
_SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# version -> the columns it adds, as (table, column, declaration).
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
_MIGRATIONS: dict[int, tuple[tuple[str, str, str], ...]] = {
    2: (
        ("recommendations", "last_confirmed_ms", "INTEGER"),
        ("recommendations", "last_confirmed_quote_age_ms", "INTEGER"),
        ("recommendations", "last_confirmed_odds_age_ms", "INTEGER"),
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
    if read_only:
        conn = sqlite3.connect(
            f"file:{path}?mode=ro", uri=True, check_same_thread=not cross_thread
        )
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, check_same_thread=not cross_thread)

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
        for table, column, decl in _MIGRATIONS[version]:
            if column in _columns(conn, table):
                continue
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
        applied.append(version)

    if applied:
        conn.commit()
    return applied


def init_db(db_path: Path | str) -> sqlite3.Connection:
    """Create or open the database, applying the schema and any migrations."""
    conn = connect(db_path)
    conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
    migrate(conn)
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
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
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
