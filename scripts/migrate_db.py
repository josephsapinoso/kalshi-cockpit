"""Bring a database up to the current schema version, then say what it did.

    .venv\\Scripts\\python.exe scripts\\migrate_db.py --db data/live.db

Run this **before** anything opens the database, which on the deployed instance
means before uvicorn starts. `store.db.open_db` refuses a version it does not
recognise -- deliberately, because reading v1 columns as v2 is the silent
failure the version stamp exists to prevent -- and the API opens read-only, so
it cannot migrate its way out. Without an explicit step the API would 500 on
every page until the chain runner happened to call `init_db`.

Idempotent. A database already at the current version is opened, reported and
left alone, so this is safe to run on every boot.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.store import db  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/live.db")
    args = parser.parse_args()

    path = Path(args.db)
    existed = path.exists()

    conn = db.connect(path)
    before = db.get_meta(conn, "schema_version") if existed else None
    conn.close()

    # `init_db` applies the schema, runs the migrations and stamps the version.
    conn = db.init_db(path)
    after = db.get_meta(conn, "schema_version")

    # Proof, not assertion. A migration that reports success while the column is
    # absent is the failure this project keeps finding; naming the columns it
    # was supposed to add and checking they are there costs one PRAGMA.
    missing: list[str] = []
    for version, step in db._MIGRATIONS.items():                 # noqa: SLF001
        for table, column, _ in step.columns:
            if column not in db._columns(conn, table):           # noqa: SLF001
                missing.append(f"v{version}: {table}.{column}")
    # Indexes too. A unique index is a constraint, and a migration that adds
    # the column and silently skips the index leaves the *shape* right and the
    # *guarantee* missing -- which is the half nothing downstream would notice
    # until a duplicate got written.
    indexes = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        )
    }
    for version, step in db._MIGRATIONS.items():                 # noqa: SLF001
        for statement in step.statements:
            name = statement.split("EXISTS", 1)[1].split("ON", 1)[0].strip()
            if name not in indexes:
                missing.append(f"v{version}: index {name}")
    conn.close()

    if missing:
        print(
            f"[migrate] FAILED: {path} reports schema v{after} but is missing "
            + ", ".join(missing)
        )
        return 1

    if not existed:
        print(f"[migrate] created {path} at schema v{after}")
    elif before == after:
        print(f"[migrate] {path} already at schema v{after}")
    else:
        print(f"[migrate] {path} migrated v{before} -> v{after}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
