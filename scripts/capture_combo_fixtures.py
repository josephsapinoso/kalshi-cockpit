"""Capture Kalshi's multivariate (combo / parlay) surface to tests/fixtures/.

Run:  python -m scripts.capture_combo_fixtures

Read-only. Every request is a GET. The one endpoint that returns a *price* for a
specific combination is `POST .../lookup`, which creates a market on the
exchange, and this script deliberately does not call it -- see
`backend/kalshi/combos.py` for why that needs a human.

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
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
