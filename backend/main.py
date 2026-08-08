"""Entry point.

    .venv\\Scripts\\python.exe -m backend.main --seed-demo

`--seed-demo` regenerates `data/demo.db` and forces demo mode, which is how the
UI is developed outside market hours and how the public instance runs: no
credentials, no network, no execution path.
"""

from __future__ import annotations

import argparse
import logging
import os

import uvicorn

from .logging_setup import configure_logging


def main() -> int:
    parser = argparse.ArgumentParser(description="Kalshi betting cockpit API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--seed-demo",
        action="store_true",
        help="Regenerate the demo database and serve it. Forces demo mode.",
    )
    parser.add_argument("--reload", action="store_true")
    parser.add_argument(
        "--anchor-now",
        action="store_true",
        help="With --seed-demo, put the seeded slate on the current clock. "
             "The actionable window is measured against real time, so a slate "
             "frozen at the fixed demo timestamp always renders it closed.",
    )
    args = parser.parse_args()

    # `configure_logging`, not `basicConfig`. They differ by the credential
    # redaction filter and by pinning httpx to WARNING -- httpx logs one full
    # request URL per request at INFO, which is how a live key reached a
    # terminal transcript once already. This path is the local dev server;
    # production goes through `create_app`, which configures the same thing.
    configure_logging()

    if args.seed_demo:
        # Set before importing config: demo mode must not require credentials,
        # and AppConfig.load() refuses live mode without an auth token.
        os.environ["INSTANCE_MODE"] = "demo"
        os.environ["DB_PATH"] = "data/demo.db"

        from .seed_demo import seed_all
        from .store.db import now_ms

        counts = seed_all(
            "data/demo.db", now_ms=now_ms() if args.anchor_now else None
        )
        logging.info("seeded demo database: %s", counts)

    from .api.routes import create_app
    from .config import AppConfig

    config = AppConfig.load()
    logging.info(
        "starting in %s mode, database %s", config.instance_mode, config.db_path
    )
    if config.is_demo:
        logging.info(
            "DEMO MODE: synthetic data, no credentials, no execution path."
        )

    uvicorn.run(
        create_app(config),
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
