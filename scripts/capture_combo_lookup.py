"""Capture ONE combo lookup response and its order book to tests/fixtures/.

Run:  .venv\\Scripts\\python.exe -m scripts.capture_combo_lookup --i-authorize-market-creation

**This mints a real combination market on the exchange** — `lookup_combo`
refuses without `allow_market_creation=True`, and this script refuses without
the flag above. It spends no money (nothing is bought), but a market with our
chosen legs appears on Kalshi, exactly as it does when any app user taps legs
in the combo builder (~700/minute mint them). Combo lookups are on Joe's
authorized-actions list (2026-08-19).

Why this exists (ADR 0070, Slice C): the parlay desk's "Price on Kalshi"
endpoint parses the lookup response and the minted market's order book, and
**no captured fixture of the lookup response exists anywhere in this repo** —
ADR 0012 records the one prior authorization as never spent. Repo law: a
wire-format parser is written against a captured payload, never memory.

What it captures:
- `tests/fixtures/combo_lookup_response.json` — the verbatim POST response.
- `tests/fixtures/combo_lookup_orderbook.json` — the minted market's
  `GET /markets/{ticker}/orderbook` envelope, read immediately after.

Leg selection: the smallest MULTI_GAME or CROSS_SPORT collection whose
`size_min` is satisfiable with two associated events that each carry at least
one active market. Deterministic (sorted by collection ticker) so a re-run
under the same universe picks the same combination.

Public market data only — nothing operator-specific is captured.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import KalshiConfig  # noqa: E402
from backend.kalshi.combos import (  # noqa: E402
    ComboScope,
    fetch_collections,
    lookup_combo,
)
from backend.kalshi.rest import KalshiRestClient  # noqa: E402
from backend.logging_setup import configure_logging  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
RESPONSE_PATH = FIXTURES / "combo_lookup_response.json"
BOOK_PATH = FIXTURES / "combo_lookup_orderbook.json"


async def _active_market(api: KalshiRestClient, event_ticker: str):
    markets = await api.markets_for_event(event_ticker)
    for market in markets:
        if market.get("status") == "active":
            return market.get("ticker")
    return None


async def capture() -> int:
    config = KalshiConfig.load()
    async with KalshiRestClient(config) as api:
        collections = await fetch_collections(api)
        candidates = sorted(
            (
                c for c in collections
                if c.scope in (ComboScope.MULTI_GAME, ComboScope.CROSS_SPORT)
                and c.size_min <= 2
                and len(c.legs) >= 2
            ),
            key=lambda c: c.collection_ticker,
        )
        if not candidates:
            print("no MULTI_GAME/CROSS_SPORT collection with size_min <= 2")
            return 1

        for collection in candidates:
            selected: list[tuple[str, str]] = []
            fixtures_used: set = set()
            for leg in collection.legs:
                # One leg per fixture: a cross-game card never carries two
                # sides of one game, and Kalshi may refuse the combination.
                from backend.match.linker import fixture_segment

                fixture = fixture_segment(leg.event_ticker)
                if fixture is not None and fixture in fixtures_used:
                    continue
                ticker = await _active_market(api, leg.event_ticker)
                if ticker is not None:
                    selected.append((leg.event_ticker, ticker))
                    fixtures_used.add(fixture)
                if len(selected) == max(2, collection.size_min):
                    break
            if len(selected) < max(2, collection.size_min):
                continue

            print(f"collection {collection.collection_ticker}")
            for event_ticker, market_ticker in selected:
                print(f"  leg {event_ticker} -> {market_ticker}")

            response = await lookup_combo(
                api,
                collection.collection_ticker,
                selected,
                allow_market_creation=True,
            )
            RESPONSE_PATH.write_text(
                json.dumps(response, indent=2, sort_keys=True), encoding="utf-8"
            )
            print(f"wrote {RESPONSE_PATH}")

            # Per the current docs the minted ticker is `market_ticker` at
            # the top level; the capture verifies rather than assumes.
            minted = response.get("market_ticker") or (
                (response.get("market") or {}).get("ticker")
            )
            if not minted:
                print(
                    "could not find the minted ticker in the response; keys: "
                    f"{sorted(response)} -- book not captured, response kept"
                )
                return 2
            print(f"minted market: {minted}")

            book = await api.get(f"/markets/{minted}/orderbook", depth=10)
            BOOK_PATH.write_text(
                json.dumps(book, indent=2, sort_keys=True), encoding="utf-8"
            )
            print(f"wrote {BOOK_PATH}")
            return 0

        print("no candidate collection had two legs with active markets")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--i-authorize-market-creation",
        action="store_true",
        help="required: the lookup mints a real combination market",
    )
    args = parser.parse_args()
    if not args.i_authorize_market_creation:
        parser.error(
            "refusing: this POST creates a market on the exchange. Pass "
            "--i-authorize-market-creation (combo lookups are on the "
            "authorized-actions list)."
        )
    configure_logging()
    return asyncio.run(capture())


if __name__ == "__main__":
    raise SystemExit(main())
