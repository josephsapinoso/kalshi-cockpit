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

SCHEMA_VERSION = 1
_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def now_ms() -> int:
    """Current UTC time in epoch milliseconds.

    The single source of "now" for the whole backend. Times are integers in
    UTC everywhere — see the schema header for why naive local datetimes are
    banned.
    """
    return int(time.time() * 1000)


class SchemaVersionMismatch(RuntimeError):
    """Raised when the database on disk was written by a different schema."""


def connect(db_path: Path | str, *, read_only: bool = False) -> sqlite3.Connection:
    """Open a connection with the pragmas the schema expects.

    `row_factory` is set to `sqlite3.Row` so call sites read columns by name.
    Positional access to a widening table is how a price column and a quantity
    column swap places without anything erroring.
    """
    path = Path(db_path)
    if read_only:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)

    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if not read_only:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_db(db_path: Path | str) -> sqlite3.Connection:
    """Create or open the database, applying the schema idempotently."""
    conn = connect(db_path)
    conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
    _set_meta(conn, "schema_version", str(SCHEMA_VERSION))
    conn.commit()
    return conn


def open_db(db_path: Path | str, *, read_only: bool = False) -> sqlite3.Connection:
    """Open an existing database, refusing on a schema-version mismatch."""
    conn = connect(db_path, read_only=read_only)
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
            "explicitly rather than reading across versions."
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
