"""Pull the parlay desk's read path into the page cache, once, at boot.

WHY THIS EXISTS
---------------
Measured on live 2026-09-10, on a machine that had just booted:

    first /api/parlays after a cold boot     20.5 s
    the same request once warm                0.56 s
    CANDIDATE_SQL warm                    373-920 ms

The box has 2.0 GB of RAM and no swap; the database is 5.43 GB and the page
cache tops out around 1.49 GB, so **at most ~27% of the file can ever be
resident** and a fresh machine has none of it. The first reader pays for all of
it, and that reader is Joe tapping the desk.

It very nearly does not fit: the API read budget is 25 s (ADR 0135) and the
cold path measured 20.5 s. Every restart is a coin flip on a 503, and restarts
are not rare -- `docker/entrypoint.sh` tears the container down whenever any
child dies, precisely so the platform restarts it.

So this runs the same scan the route runs, once, at boot, and throws the answer
away. The work happens either way; this decides who waits for it.

WHAT THIS IS NOT
----------------
- **Not a fix for the query.** That was `idx_odds_event_commence` (schema v39),
  which took the scan's subquery from 26,719 ms to 327.9 ms. This is about
  which pages are resident, not about how many rows are touched.
- **Not a cache the app keeps.** Nothing is stored. The only effect is on the
  kernel's page cache, which is why the answer is discarded unread.
- **Not a guarantee.** The cache is shared with the recorder and with Next, and
  27% of the file is the ceiling. A long enough idle period, or a big enough
  read elsewhere, evicts this again -- see `tasks/lessons.md` on full-table
  scans. It makes the common case fast; it cannot make the bad case impossible.

BACKGROUNDED, DELIBERATELY
--------------------------
`docker/entrypoint.sh` runs this with `&`. It must never delay the boot: Fly
health-checks port 3000, the entrypoint gives uvicorn 30 s to answer, and a
20-second synchronous read wedged in front of that would turn a slow boot into
a failed one on a machine that holds real money. Read-only, single-shot, and
every failure is swallowed -- a warm-up that can break the boot is worse than a
cold cache.
"""

from __future__ import annotations

import argparse
import sys
import time


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument(
        "--max-odds-age-ms",
        type=int,
        default=900_000,
        help="Passed to `ladder_candidates` so the scan floor matches the "
        "route's. Only widens the scan; it is not a filter here.",
    )
    args = parser.parse_args(argv)

    # Imported inside `main` so that `--help` works on a box where the app
    # cannot import, and so an import failure is reported by the same
    # swallow-everything path as a query failure.
    try:
        import sqlite3

        from backend.parlays import ladder_candidates

        started = time.perf_counter()
        # **Read-only, and its own connection.** The writer is the chain
        # runner; opening this read-write would put a second writer on the
        # volume during boot for no reason.
        conn = sqlite3.connect("file:%s?mode=ro" % args.db, uri=True)
        conn.row_factory = sqlite3.Row
        try:
            legs, _excluded = ladder_candidates(
                conn,
                now_ms=int(time.time() * 1000),
                max_odds_age_ms=args.max_odds_age_ms,
            )
        finally:
            conn.close()
        elapsed = time.perf_counter() - started
        # The count is logged only so a human can tell a warm-up that read the
        # slate from one that read an empty database. Nothing consumes it.
        print(
            "[warm] parlay read path warmed in %.1fs (%d candidate legs)"
            % (elapsed, len(legs)),
            flush=True,
        )
    except Exception as exc:  # noqa: BLE001 -- a warm-up must never fail a boot
        print("[warm] skipped: %s: %s" % (type(exc).__name__, exc), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
