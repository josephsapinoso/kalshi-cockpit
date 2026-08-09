"""Capture Kalshi's multivariate (combo / parlay) surface to tests/fixtures/.

Run:  python -m scripts.capture_combo_fixtures

Read-only. Every request is a GET, and no market is created.

**Corrected 2026-08-09.** This file used to say that the only way to see a combo
*price* was `POST .../lookup`, which creates a market. That is one way, and it
is not the only one: Kalshi's own users mint provisional combination markets
continuously by tapping legs in the app -- roughly 700 a minute -- and those
markets are returned by `GET /markets` carrying `mve_selected_legs`,
`mve_collection_ticker` and a live quote. So a joint price is readable for
nothing, and the second capture below takes some.

The wrong belief was cheap to hold because it is *nearly* true: about one in
twelve of those markets is quoted at all and one in a thousand on both sides,
and the quote decays within a couple of minutes of creation. Sampling the wrong
pages says "no combo is ever priced" with complete conviction. See
`scripts/measure_combo_correlation.py`.

Why this exists
---------------
This project spent its first eleven steps treating every `KXMVE` ticker as junk
to be filtered out, on the strength of a predecessor finding that `/markets` is
~99.8% `KXMVE` by count with no volume. That finding was true and the conclusion
drawn from it was wrong: `KXMVE` is **M**ulti-**V**ariate **E**vent, and it is
Kalshi's combo product -- the parlay builder in the app. What is junk is the
*pre-generated* combination markets clogging `/markets`, not the product.

So the filter stays (paginating `/markets` is still the wrong way to discover
anything) but it is no longer allowed to stand in for "Kalshi has no parlay".
"""

from __future__ import annotations

import asyncio
import collections
import json
from pathlib import Path

from backend.config import KalshiConfig
from backend.kalshi.rest import KalshiRestClient

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"

# The response key is `multivariate_contracts`, NOT `multivariate_event_collections`.
# Reading the plausible-but-wrong key returns an empty list and no error, which
# is exactly how this project's predecessor parsed every order book to zero
# levels for its entire life. Pinned here so a test can hold it.
COLLECTIONS_KEY = "multivariate_contracts"


async def main() -> int:
    cfg = KalshiConfig.load()
    async with KalshiRestClient(cfg) as api:
        collections_seen: list[dict] = []
        cursor = None
        for _ in range(25):
            params = {"limit": 200}
            if cursor:
                params["cursor"] = cursor
            page = await api.request(
                "GET", "/multivariate_event_collections", params=params
            )
            batch = page.get(COLLECTIONS_KEY, [])
            collections_seen.extend(batch)
            cursor = page.get("cursor")
            if not cursor or not batch:
                break

        print(f"{len(collections_seen)} collections")

        by_series: dict[str, list[dict]] = collections.defaultdict(list)
        for entry in collections_seen:
            by_series[entry.get("series_ticker", "?")].append(entry)

        # One representative collection per series, so the fixture covers every
        # shape (same-game, multi-game, cross-category) without 1,389 rows.
        representatives = {
            series: sorted(entries, key=lambda c: -len(c.get("associated_events") or []))[0]
            for series, entries in by_series.items()
        }

        quoters = sum(
            1
            for entry in collections_seen
            for event in entry.get("associated_events", [])
            if event.get("active_quoters")
        )
        legs = sum(
            len(entry.get("associated_events") or []) for entry in collections_seen
        )

        summary = {
            "captured_note": (
                "Read-only GET capture. No lookup was performed, so no combo "
                "PRICE appears here -- pricing a specific combination requires "
                "POST .../lookup, which creates a market."
            ),
            "n_collections": len(collections_seen),
            "n_legs": legs,
            "n_legs_with_active_quoters": quoters,
            "series": {
                series: {
                    "n_collections": len(entries),
                    "n_legs": sum(len(e.get("associated_events") or []) for e in entries),
                    "size_min": entries[0].get("size_min"),
                    "size_max": entries[0].get("size_max"),
                    "is_all_yes": entries[0].get("is_all_yes"),
                    "is_single_market_per_event": entries[0].get(
                        "is_single_market_per_event"
                    ),
                    "functional_description": entries[0].get("functional_description"),
                }
                for series, entries in sorted(by_series.items())
            },
        }

        FIXTURES.mkdir(parents=True, exist_ok=True)
        (FIXTURES / "combo_collections_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        # Trim the representatives: the full associated_events list on the
        # cross-game collections runs to hundreds of entries and adds nothing.
        trimmed = {}
        for series, entry in representatives.items():
            copy = dict(entry)
            copy["associated_events"] = (entry.get("associated_events") or [])[:12]
            copy["associated_event_tickers"] = (
                entry.get("associated_event_tickers") or []
            )[:12]
            copy["_truncated_from"] = len(entry.get("associated_events") or [])
            trimmed[series] = copy
        (FIXTURES / "combo_collections.json").write_text(
            json.dumps(trimmed, indent=2), encoding="utf-8"
        )

        print(f"  {legs} legs, {quoters} with active quoters")
        print(f"  wrote {len(trimmed)} representative collections")
        for series, info in summary["series"].items():
            print(
                f"    {series:<34} {info['n_collections']:>5} collections, "
                f"{info['n_legs']:>6} legs"
            )

        priced = await capture_priced_combinations(api)
        (FIXTURES / "combo_priced_markets.json").write_text(
            json.dumps(priced, indent=2), encoding="utf-8"
        )
        print(
            f"  wrote {len(priced['combos'])} priced combinations and "
            f"{len(priced['legs'])} leg markets"
        )
    return 0


async def capture_priced_combinations(
    api: KalshiRestClient, *, pages: int = 6, want: int = 12
) -> dict:
    """Real combination markets that carry a price, plus their leg markets.

    Both halves are needed and neither is enough. A joint price without its
    legs is a number with nothing to invert against, and the legs without the
    joint are what this project already had.

    Newest first and bounded. `/markets` is ~99.8% these tickers, so it is
    never walked blind -- and here depth is pointless anyway: page six is
    already two minutes old and nothing that old is quoted.
    """
    combos: list[dict] = []
    leg_markets: dict[str, dict] = {}

    for series in ("KXMVESPORTSMULTIGAMEEXTENDED", "KXMVECROSSCATEGORY"):
        cursor = None
        for _ in range(pages):
            params: dict = {
                "series_ticker": series, "limit": 200, "status": "open",
            }
            if cursor:
                params["cursor"] = cursor
            page = await api.request("GET", "/markets", params=params)
            batch = page.get("markets") or []
            for market in batch:
                legs_selected = market.get("mve_selected_legs") or []
                # Small ones only. A 42-leg combination would drag 42 leg
                # markets into the fixture and no correlation can be fitted to
                # it anyway.
                if not 2 <= len(legs_selected) <= 3:
                    continue
                ask = market.get("yes_ask_dollars")
                try:
                    if not 0.0 < float(ask) < 1.0:
                        continue
                except (TypeError, ValueError):
                    continue
                combos.append(market)
                if len(combos) >= want:
                    break
            cursor = page.get("cursor")
            if not cursor or not batch or len(combos) >= want:
                break
        if len(combos) >= want:
            break

    for combo in combos:
        for leg in combo.get("mve_selected_legs") or []:
            ticker = leg["market_ticker"]
            if ticker in leg_markets:
                continue
            payload = await api.request("GET", f"/markets/{ticker}")
            leg_markets[ticker] = payload.get("market") or {}

    return {
        "captured_note": (
            "GET capture, no market created. These combination markets were "
            "minted by Kalshi's own users and were still quoted when read. "
            "`legs` holds each referenced leg market as read at the same time, "
            "so the joint and its marginals are contemporaneous -- reading a "
            "leg minutes later prices the two halves at different moments."
        ),
        "combos": combos,
        "legs": leg_markets,
    }


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
