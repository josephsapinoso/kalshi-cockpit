"""Capture the **price grids** Kalshi actually publishes on game markets.

Why this exists as its own capture
----------------------------------
`price_ranges` is the source of truth for which limit prices a market will
accept — Kalshi's own words: *"any price on the grid is valid, and any off-grid
price is rejected. Consume it dynamically per market."* The order path therefore
has to snap to it, and snapping is the kind of arithmetic that produces
plausible numbers when it is wrong.

The existing fixtures (`events_sports_nested.json`, `market_single.json`) pin
one grid: `linear_cent`, a single band at a whole-cent step. That is the grid on
which the snapper is a **no-op**, so testing against it alone proves nothing
about the case the snapper exists for. This capture walks the open universe and
records **every distinct grid**, so a sub-cent structure — if the exchange lists
one on a game market today — is pinned by real bytes rather than by a band I
typed out of the documentation table.

If none is found, that is a finding and it is printed as one. It is a fact about
today's slate, not about the exchange: `.claude/skills/kalshi-api/SKILL.md`
recorded 60 `center_half_edge_half_cent` game markets on 2026-08-06, so the
structure exists and its presence is a calendar question.

Run:

    .venv\\Scripts\\python.exe scripts\\capture_price_grids.py

Read-only. Places no orders and spends no odds credits — Kalshi REST is
unmetered, and this touches nothing else.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import ConfigError, KalshiConfig          # noqa: E402
from backend.kalshi.discovery import classify_series          # noqa: E402
from backend.kalshi.rest import KalshiRestClient              # noqa: E402
from backend.logging_setup import configure_logging           # noqa: E402

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
OUT = FIXTURES / "price_grids.json"


def _grid_key(ranges: Any) -> str:
    """A stable identity for one grid, so distinct grids are counted once."""
    return json.dumps(ranges, sort_keys=True)


async def capture() -> int:
    configure_logging()

    try:
        config = KalshiConfig.load()
    except ConfigError as exc:
        print(f"cannot capture: {exc}")
        return 2

    grids: dict[str, dict[str, Any]] = {}
    structures: Counter[str] = Counter()
    scanned = 0
    markets = 0

    async with KalshiRestClient(config) as api:
        # Same scope filter as every other capture in this repo: discovery's own
        # classifier, not a ticker-prefix match. A grid pinned from a market this
        # code never prices is a fixture about someone else's problem.
        async for event in api.events(with_nested_markets=True):
            scanned += 1
            info = classify_series(event)
            if not info.is_game_level or info.sport_key is None:
                continue
            for market in event.get("markets") or []:
                markets += 1
                ranges = market.get("price_ranges")
                structure = market.get("price_level_structure")
                structures[str(structure)] += 1
                if ranges is None:
                    continue
                key = _grid_key(ranges)
                if key not in grids:
                    grids[key] = {
                        "price_level_structure": structure,
                        "price_ranges": ranges,
                        "example_ticker": market.get("ticker"),
                        "example_status": market.get("status"),
                    }

    if not grids:
        print(
            f"no market carried price_ranges across {scanned} events / "
            f"{markets} game markets. That is a wire-format change, not an "
            f"empty slate -- nothing was written."
        )
        return 1

    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "note": (
            "Verbatim `price_ranges` / `price_level_structure` values from "
            "/events?with_nested_markets=true, one entry per DISTINCT grid "
            "across game-level markets. `price_ranges` is Kalshi's source of "
            "truth for valid limit prices; `price_level_structure` is a label "
            "and must not be keyed off (Kalshi: 'new structures are introduced "
            "over time'). Counts are of markets, and are a fact about the day "
            "this ran."
        ),
        "events_scanned": scanned,
        "game_markets_seen": markets,
        "structure_counts": dict(structures),
        "grids": list(grids.values()),
    }

    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"scanned {scanned} events, {markets} game markets")
    print(f"distinct grids: {len(grids)}")
    for structure, count in structures.most_common():
        print(f"  {structure:<32} x {count}")
    sub_cent = [
        g for g in grids.values()
        if any(str(b.get("step")) not in ("0.0100", "0.01") for b in g["price_ranges"])
    ]
    print(
        f"sub-cent grids captured: {len(sub_cent)}"
        + ("" if sub_cent else "  <-- none on today's slate; see the docstring")
    )
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(capture()))
