"""Snapshot SQLite to Parquet -- the boundary between the two data paths.

SQLite is the operational store: written continuously by the ingest loop, read
by the Board with low latency, and optimised for freshness. Parquet + DuckDB is
the analytical store: columnar, immutable once written, and optimised for being
*right*.

Keeping them separate is deliberate. Running the measurement queries against
the live database would mean every analysis competes with the ingest loop for
write locks, and -- worse -- that a long-running query reads a moving target.
An analysis that quietly straddles a write is exactly the kind of error that
produces a result nobody can reproduce.

**Snapshots are immutable and stamped.** Each publish writes a new dated
partition rather than overwriting. That costs a little disk and buys the
ability to answer "what did we believe on the 14th?" -- which matters when a
config change lands and the question becomes whether the numbers moved because
the market changed or because we did.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)

DEFAULT_LAKE = Path("data/lake")

# Tables worth analysing. Deliberately not everything: `kalshi_quotes` is
# high-volume append-only telemetry that would dominate the lake, and nothing
# downstream aggregates it. Add it if that changes.
PUBLISHED_TABLES: tuple[str, ...] = (
    "recommendations",
    "orders",
    "fills",
    "settlements",
    "closing_lines",
    "fair_prices",
    "event_links",
    "unmatched_events",
    "api_credits",
    "strategy_configs",
    "kalshi_markets",
    "kalshi_events",
    "kalshi_series",
    "model_ratings",
    "lessons",
)


def _partition_name(published_ms: int) -> str:
    """`dt=YYYY-MM-DD` -- Hive-style, so DuckDB reads the date as a column."""
    day = datetime.fromtimestamp(published_ms / 1000, timezone.utc).date()
    return f"dt={day.isoformat()}"


# SQLite's declared types, mapped to Arrow. SQLite is dynamically typed, so a
# column declared INTEGER *can* hold a string -- but the declaration is a real
# statement of intent and is far better than guessing from zero rows.
_SQLITE_TO_ARROW = {
    "INTEGER": pa.int64(),
    "REAL": pa.float64(),
    "TEXT": pa.string(),
    "BLOB": pa.binary(),
}


def _declared_schema(conn: sqlite3.Connection, table: str) -> pa.Schema:
    """Arrow schema from SQLite's own column declarations."""
    fields = []
    for row in conn.execute(f"PRAGMA table_info({table})"):
        declared = (row["type"] or "").upper().split("(")[0]
        fields.append(pa.field(row["name"], _SQLITE_TO_ARROW.get(declared, pa.string())))
    return pa.schema(fields)


def _table_to_arrow(conn: sqlite3.Connection, table: str) -> Optional[pa.Table]:
    """Read one SQLite table into Arrow.

    **Empty tables are written too, with their declared schema.** The first
    version skipped them, reasoning that a zero-row Parquet file carries a
    guessed schema that DuckDB would happily union against a real one. The
    reasoning was right; the conclusion was wrong. Skipping meant
    `read_parquet('.../fills/**')` raised *"No files found"* and failed the
    whole dbt build -- and "no fills yet" is the project's normal state until
    the fee-calibration trades happen.

    Taking the schema from `PRAGMA table_info` rather than from the data means
    it is a declaration, not a guess, so the union is safe.
    """
    cursor = conn.execute(f"SELECT * FROM {table}")
    columns = [d[0] for d in cursor.description]
    rows = cursor.fetchall()

    if not rows:
        return _declared_schema(conn, table).empty_table()

    data = {name: [row[i] for row in rows] for i, name in enumerate(columns)}
    return pa.table(data)


def publish(
    conn: sqlite3.Connection,
    *,
    lake_root: Path | str = DEFAULT_LAKE,
    published_ms: Optional[int] = None,
    tables: Sequence[str] = PUBLISHED_TABLES,
) -> dict[str, int]:
    """Write a dated snapshot of each table. Returns row counts.

    **Empty tables ARE written**, as zero-row files carrying the schema from
    `PRAGMA table_info`. This docstring said the opposite until 2026-08-09 --
    it described the first version's behaviour, which was changed in
    `_table_to_arrow` and not here, so the module contained two docstrings
    contradicting each other about the case that actually occurs. The reasoning
    for the change is in `_table_to_arrow`: skipping made
    `read_parquet('.../fills/**')` raise *"No files found"* and fail the whole
    dbt build, and "no fills yet" is this project's normal state.

    A table that cannot be read at all (a `sqlite3.Error` -- typically it does
    not exist) is skipped with a warning and does not appear in the counts.
    """
    from .db import now_ms

    stamp = published_ms if published_ms is not None else now_ms()
    partition = _partition_name(stamp)
    root = Path(lake_root)

    counts: dict[str, int] = {}
    for table in tables:
        try:
            arrow = _table_to_arrow(conn, table)
        except sqlite3.Error as exc:
            logger.warning("skipping %s: %s", table, exc)
            continue

        if arrow is None:
            counts[table] = 0
            continue

        # Stamp every row with when this snapshot was taken. Without it, two
        # partitions of the same table are indistinguishable once read.
        arrow = arrow.append_column(
            "published_ms", pa.array([stamp] * arrow.num_rows, pa.int64())
        )
        # An empty table still gets the column, so its schema matches a
        # populated partition of the same table and DuckDB can union them.

        destination = root / table / partition
        destination.mkdir(parents=True, exist_ok=True)
        pq.write_table(arrow, destination / "part-0.parquet", compression="zstd")
        counts[table] = arrow.num_rows

    logger.info("published %s to %s", partition, root)
    return counts


def latest_partition(lake_root: Path | str, table: str) -> Optional[Path]:
    """Most recent partition for a table, or None if never published."""
    directory = Path(lake_root) / table
    if not directory.exists():
        return None
    partitions = sorted(p for p in directory.iterdir() if p.is_dir())
    return partitions[-1] if partitions else None


def lake_summary(lake_root: Path | str) -> dict[str, dict]:
    """What is in the lake: partition count and date range, per table.

    **Nothing calls this.** The docstring claimed it was "used by the Dashboards
    screen and by `dbt` docs" until 2026-08-09; `grep -rn lake_summary` over the
    whole repo returns this definition and no other line -- no route, no script,
    no test. The same is true of `latest_partition` above it.

    Left in place deliberately rather than deleted: whether the analytical limb
    survives at all is an open decision, and removing the function would settle
    it by accident. But a docstring naming a caller that does not exist is worse
    than no docstring -- it is the failure this repo records as "code with no
    caller is not a feature, it is a plan", with the plan written as though it
    had already happened. If you are about to rely on this, you are its first
    caller.
    """
    root = Path(lake_root)
    if not root.exists():
        return {}

    summary: dict[str, dict] = {}
    for table_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        partitions = sorted(p.name for p in table_dir.iterdir() if p.is_dir())
        summary[table_dir.name] = {
            "partitions": len(partitions),
            "earliest": partitions[0] if partitions else None,
            "latest": partitions[-1] if partitions else None,
        }
    return summary


def main() -> int:
    import argparse
    import json

    from ..config import AppConfig
    from .db import open_db

    parser = argparse.ArgumentParser(description="Publish SQLite to the Parquet lake.")
    parser.add_argument("--db", default=None)
    parser.add_argument("--lake", default=str(DEFAULT_LAKE))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    db_path = args.db or str(AppConfig.load().db_path)

    conn = open_db(db_path, read_only=True)
    try:
        counts = publish(conn, lake_root=args.lake)
    finally:
        conn.close()

    print(json.dumps(counts, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
