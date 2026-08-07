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
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    if args.seed_demo:
        # Set before importing config: demo mode must not require credentials,
        # and AppConfig.load() refuses live mode without an auth token.
        os.environ["INSTANCE_MODE"] = "demo"
        os.environ["DB_PATH"] = "data/demo.db"

        from .seed_demo import seed_all

        counts = seed_all("data/demo.db")
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
