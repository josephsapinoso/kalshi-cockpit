r"""One poll pass over the venue's portfolio endpoints. Read-only, free.

    .venv\Scripts\python.exe scripts\poll_portfolio.py [--db PATH]

Runs `backend.portfolio_poll.poll_portfolio` once: mirrors settlements and
fills, snapshots the balance, counts positions, and leaves a `poll_log` row
per endpoint whether or not it succeeded. Safe to run twice -- every write is
idempotent -- and safe to run anywhere a Kalshi credential is configured.

**This is a manual/cron entry point, not the schedule.** The registration's
cadence (12 h for the mirror, 5 min for the balance) has to run on the live
instance, because this account's history demonstrably expires and a laptop
that is closed does not poll. Wiring that into the deployed loop is a deploy
decision recorded separately; this script is what it will call, and what a
person can run today.

Exit codes: 0 every endpoint polled, 1 any endpoint failed (the others still
ran and were logged -- check poll_log, not just the exit code), 2 no usable
credential.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import ConfigError, KalshiConfig          # noqa: E402
from backend.kalshi.rest import KalshiRestClient              # noqa: E402
from backend.logging_setup import configure_logging           # noqa: E402
from backend.portfolio_poll import poll_portfolio             # noqa: E402
from backend.store import db                                  # noqa: E402


async def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/cockpit.db", help="database path")
    args = parser.parse_args()

    try:
        config = KalshiConfig.load()
    except ConfigError as exc:
        print(f"no usable Kalshi credential: {exc}", file=sys.stderr)
        return 2

    conn = db.init_db(args.db)
    try:
        async with KalshiRestClient(config) as client:
            summary = await poll_portfolio(
                conn, client, now_ms=int(time.time() * 1000)
            )
    finally:
        conn.close()

    failed = False
    for endpoint, result in summary.items():
        print(f"{endpoint:<12} {result}")
        if isinstance(result, str) and result.startswith("FAILED"):
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
