"""Run the `odds_snapshots` prune's dry run once, read-only, and print it. #139.

    flyctl ssh console -a kalshi-cockpit -C "python /app/scripts/odds_prune_dry_run.py"

The runner's own dry run only fires on a full pass with no betting window
open, and `flyctl logs` is lossy, so this is the same count taken by hand:
`odds_snapshot_prune.run` with `enabled=True, dry_run=True` against a
`mode=ro` connection, so SQLite itself refuses any write.

**Cost.** The dry run stops at `DRY_RUN_SAMPLE_GAMES` (25) games. Each game is
index seeks on `idx_odds_sport_commence` and `idx_odds_event*`
(`tests/test_odds_snapshot_prune.py::TestItSeeksRatherThanScans`), so the
read scales with those games' rows, not the table.

**What it does NOT establish.** The oldest 25 games are a convenience
sample, not the backlog. Their keep ratio is a sanity check on the rule and
says nothing about the total rows or bytes the armed prune will free, or how
fast it will free them.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import time
from dataclasses import dataclass

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from backend.store import odds_snapshot_prune as prune  # noqa: E402

DEFAULT_DB = "/data/cockpit.db"


@dataclass(frozen=True)
class _DryRun:
    enabled: bool = True
    dry_run: bool = True
    retention_days: int = prune.DEFAULT_RETENTION_DAYS
    budget_s: float = 60.0

    @property
    def deletes(self) -> bool:
        return False


def main(argv: list[str]) -> int:
    db_path = argv[1] if len(argv) > 1 else DEFAULT_DB
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.execute("PRAGMA busy_timeout = 5000")
    started = time.monotonic()
    result = prune.run(conn, now=int(time.time() * 1000), config=_DryRun())
    took = time.monotonic() - started
    share = (
        f"{result.rows_would_delete / result.rows_examined:.1%}"
        if result.rows_examined else "n/a (no rows examined)"
    )
    print(f"games={result.games} skipped_moved={result.skipped_moved}")
    print(f"rows_examined={result.rows_examined} "
          f"rows_would_delete={result.rows_would_delete} share={share}")
    print(f"took_s={took:.1f}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
