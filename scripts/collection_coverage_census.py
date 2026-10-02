"""How many of a fixture's events each catch-all KXMVE collection lists (#297).

Reads FILES ONLY -- no Kalshi call, no database, no write of any kind, no
credits. Cost class: CHEAP (one JSON file read, a few thousand string
comparisons).

    .venv\\Scripts\\python.exe scripts/collection_coverage_census.py \\
        [collections.json] [-n 20]

`collections.json` is a capture shaped like
`tests/fixtures/combo_collections.json`: `{collection_ticker: payload}` with
each payload carrying `associated_event_tickers` and/or `associated_events`.
With no path it reads that captured fixture. The server's own cached list
(`parlays._collections_cache`) lives in process memory and is not readable
from here; getting a live capture is a read-only GET and is not this script.

**Why.** `/game` offers the legs of ONE catch-all collection, the one that
lists the most of the fixture's events (`game_builder.fixture_events`). Whether
Kalshi lists MORE legs for an NHL or NCAAF fixture than that menu shows is
unmeasured (parlay town hall 2026-10-02). This prints the counts so the
question can be read before anything is built. It does not widen the menu.

**Bounded.** At most `-n` fixtures are printed (default 20, hard cap
`MAX_FIXTURES`), at most `MAX_COLLECTIONS` collections are read, and a file
larger than `MAX_BYTES` is refused unread.

## What this does not establish

- **Not what Kalshi offers, only what the capture listed.** A collection that
  lists 3 of a fixture's events here may list more on another day; legs for a
  game are added near kickoff (props especially).
- **A truncated capture undercounts by construction.** The committed fixture
  keeps the first 12 tickers of each collection (`_truncated_from` marks it);
  a count taken from it is a floor, and the output says so per collection.
- **Nothing about quoting.** `associated_event_tickers` carries no quoter
  detail, so "lists an event" is not "anyone will price a combination with it".
- **Nothing about leagues absent from the capture.** The committed fixture has
  no NHL and no NCAAF events; their rows do not exist here, which is the
  reason a live capture is the next step, not evidence they carry few legs.
- **Event counts, not market counts.** One event is a ladder of markets.
- **No ranking and no recommendation.** The counts are a dump.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.kalshi.combos import ComboScope, parse_collection  # noqa: E402

DEFAULT_CAPTURE = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures"
    / "combo_collections.json"
)
DEFAULT_FIXTURES = 20
MAX_FIXTURES = 100
MAX_COLLECTIONS = 2000
MAX_BYTES = 32 * 1024 * 1024

_CATCH_ALL = (
    ComboScope.MULTI_GAME, ComboScope.CROSS_SPORT, ComboScope.CROSS_CATEGORY,
)
_GAME_EVENT = re.compile(r"^(KX[A-Z0-9]*GAME)-([A-Z0-9]+)$")


def census(
    payloads: dict[str, Any], *, max_fixtures: int = DEFAULT_FIXTURES
) -> list[dict]:
    """One row per (fixture, catch-all collection) that lists any of it.

    A fixture is a game-event ticker's suffix (`KXNBAGAME-26JUN13NYKSAS` ->
    prefix `KXNBA`, suffix `26JUN13NYKSAS`), found in any collection. Rows are
    ordered by fixture then collection ticker, so the output is a dump and
    not a ranking.
    """
    max_fixtures = max(0, min(int(max_fixtures), MAX_FIXTURES))
    collections = []
    for ticker, payload in list(payloads.items())[:MAX_COLLECTIONS]:
        if not isinstance(payload, dict):
            continue
        payload = {"collection_ticker": ticker, **payload}
        collections.append((parse_collection(payload), payload))

    fixtures: set[tuple[str, str]] = set()
    for collection, _ in collections:
        for leg in collection.legs:
            match = _GAME_EVENT.match(leg.event_ticker)
            if match:
                fixtures.add((match.group(1)[: -len("GAME")], match.group(2)))

    rows: list[dict] = []
    for prefix, suffix in sorted(fixtures)[:max_fixtures]:
        for collection, payload in sorted(
            collections, key=lambda cp: cp[0].collection_ticker
        ):
            if collection.scope not in _CATCH_ALL:
                continue
            events = [
                leg.event_ticker for leg in collection.legs
                if leg.event_ticker.endswith("-" + suffix)
                and leg.series.startswith(prefix)
            ]
            if not events:
                continue
            truncated_from: Optional[int] = payload.get("_truncated_from")
            rows.append({
                "prefix": prefix,
                "fixture": suffix,
                "collection": collection.collection_ticker,
                "events_listed": len(events),
                "series": sorted({e.split("-")[0][len(prefix):] for e in events}),
                "collection_events_in_capture": len(collection.legs),
                "capture_truncated_from": truncated_from,
            })
    return rows


def _load(path: Path) -> dict[str, Any]:
    if path.stat().st_size > MAX_BYTES:
        raise SystemExit(f"{path.name}: over {MAX_BYTES} bytes, refused unread.")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"{path.name}: not a {{collection_ticker: payload}} map.")
    return data


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("capture", nargs="?", type=Path, default=DEFAULT_CAPTURE)
    parser.add_argument(
        "-n", type=int, default=DEFAULT_FIXTURES,
        help=f"fixtures to print (default {DEFAULT_FIXTURES}, max {MAX_FIXTURES})",
    )
    args = parser.parse_args(argv)
    rows = census(_load(args.capture), max_fixtures=args.n)
    print(f"capture: {args.capture.name}   rows: {len(rows)}   "
          f"(files only; nothing was read from Kalshi)")
    for r in rows:
        floor = (
            f"  [capture truncated from {r['capture_truncated_from']}: "
            f"count is a floor]" if r["capture_truncated_from"] else ""
        )
        print(f"{r['prefix']} {r['fixture']:<16} {r['collection']:<32} "
              f"events={r['events_listed']:<3} series={','.join(r['series'])}"
              f"{floor}")
    print("Not established: what Kalshi offers on another day, quoting, or any "
          "league absent from this capture. See the module docstring.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
