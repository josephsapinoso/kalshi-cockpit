"""Capture what Kalshi answers when the SAME combination is looked up twice.

Run:  .venv\\Scripts\\python.exe -m scripts.capture_combo_repeat_lookup
          --i-authorize-market-creation

**Why this exists (2026-08-24 code review, finding 7).** `lookup_combo`'s
create POST was captured exactly once, on a brand-new combination
(2026-08-23, `combo_lookup_response.json`). The parlay desk's *designed*
behaviour walks straight into the un-captured case: a freshly minted combo's
book is empty on both sides, the screen's own words say "try again shortly",
and the retry button added 2026-08-24 makes that second tap one press away.
So the second tap hits "this combination already exists" — a branch nothing
in this repo has ever observed.

Two answers are possible and they need opposite handling:

- **200 with the existing market.** The retry is safe and idempotent; the
  second tap re-reads the book, which is exactly what the screen promises.
- **409 / 400.** The combination becomes permanently unpriceable through this
  path — every retry burns from the 5,000-creations/week budget and returns a
  502 the user can do nothing about. `price_card_on_kalshi` would need an
  already-exists branch that recovers the existing ticker.

**What it costs.** Two POSTs against one collection, minting ONE new market
(the second call is the repeat, by construction). No money is committed.
Combo lookups are on Joe's authorized-actions list (2026-08-19), and the
script still refuses without the explicit flag.

**What it does NOT establish.** One collection, one leg pair, one moment. If
Kalshi's answer depends on the collection's scope, on whether the legs'
games have started, or on how recently the market was minted, a single
capture cannot see it — the output file records the exact conditions so a
later run can be compared rather than assumed.

Public market data only; nothing operator-specific is captured.
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
from backend.kalshi.rest import KalshiAPIError, KalshiRestClient  # noqa: E402
from backend.logging_setup import configure_logging  # noqa: E402
from backend.match.linker import fixture_segment  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
OUT_PATH = FIXTURES / "combo_lookup_repeat.json"


async def _active_market(api: KalshiRestClient, event_ticker: str):
    markets = await api.markets_for_event(event_ticker)
    for market in markets:
        if market.get("status") == "active":
            return market.get("ticker")
    return None


async def _attempt(api, collection_ticker, legs) -> dict:
    """One create POST, recorded whether it succeeds or refuses.

    A refusal is the interesting outcome here, so it is captured as data
    rather than raised — the whole point is to learn which shape arrives.
    """
    try:
        response = await lookup_combo(
            api, collection_ticker, legs, allow_market_creation=True
        )
    except KalshiAPIError as exc:
        return {
            "outcome": "refused",
            "status_code": exc.status_code,
            "body": exc.body,
        }
    except Exception as exc:  # noqa: BLE001 -- transport, recorded by type
        return {
            "outcome": "error",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    return {"outcome": "ok", "response": response}


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

            print("\nfirst call (mints the market if it is new)...")
            first = await _attempt(api, collection.collection_ticker, selected)
            print(f"  {first['outcome']}"
                  + (f" {first.get('status_code')}" if first.get("status_code")
                     else ""))

            print("second call, identical body (the un-captured case)...")
            second = await _attempt(api, collection.collection_ticker, selected)
            print(f"  {second['outcome']}"
                  + (f" {second.get('status_code')}" if second.get("status_code")
                     else ""))

            first_ticker = (
                (first.get("response") or {}).get("market_ticker")
                if first["outcome"] == "ok" else None
            )
            second_ticker = (
                (second.get("response") or {}).get("market_ticker")
                if second["outcome"] == "ok" else None
            )

            payload = {
                "captured_note": (
                    "The SECOND call is the one nothing had ever observed. "
                    "Conditions are recorded because one capture cannot rule "
                    "out that the answer depends on them."
                ),
                "collection_ticker": collection.collection_ticker,
                "collection_scope": collection.scope.name,
                "selected_markets": [
                    {"event_ticker": e, "market_ticker": m}
                    for e, m in selected
                ],
                "first_call": first,
                "second_call": second,
                "same_ticker_returned": (
                    first_ticker is not None and first_ticker == second_ticker
                ),
                "verdict": _verdict(first, second, first_ticker, second_ticker),
            }
            OUT_PATH.write_text(
                json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
            )
            print(f"\nwrote {OUT_PATH}")
            print(f"VERDICT: {payload['verdict']}")
            return 0

        print("no candidate collection had two legs with active markets")
        return 1


def _verdict(first, second, first_ticker, second_ticker) -> str:
    if first["outcome"] != "ok":
        return (
            "INCONCLUSIVE -- the first call did not succeed, so the second "
            "was not a repeat of an existing combination."
        )
    if second["outcome"] == "ok" and first_ticker == second_ticker:
        return (
            "IDEMPOTENT -- the repeat returned the same market_ticker. A "
            "second tap is safe and re-reads the book, which is what the "
            "screen promises."
        )
    if second["outcome"] == "ok":
        return (
            f"DIFFERENT MARKET -- the repeat returned {second_ticker!r} "
            f"against {first_ticker!r}. Each tap mints a new market; the "
            "retry must be reconsidered and the weekly budget is at risk."
        )
    return (
        f"REFUSED -- the repeat came back {second.get('status_code')}. The "
        "combination is unpriceable through this path once minted; "
        "price_card_on_kalshi needs an already-exists branch that recovers "
        "the existing ticker rather than returning 502."
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--i-authorize-market-creation",
        action="store_true",
        help="required: the first lookup mints a real combination market",
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
