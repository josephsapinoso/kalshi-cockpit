"""Is a series-scoped walk actually cheaper than the full catalogue walk?

The lesson from four hours ago is that the obvious fix was worse -- fetching
each linked event individually is more requests than pages, against a shared
minimum-interval limiter. So the replacement gets measured before it gets
built, not after.

Measures, against the real API:

  1. the full `/events` walk, as `run_kalshi_pass` does it today
  2. one `/events?series_ticker=X` walk per series that carried a priceable
     event, which is what the quote pass would do instead

**Read-only.** Kalshi REST reads are unmetered; this spends no odds credits and
touches no order path.
"""

from __future__ import annotations

import asyncio
import collections
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from backend.config import KalshiConfig  # noqa: E402
from backend.kalshi.discovery import discover_from_events  # noqa: E402
from backend.kalshi.rest import KalshiRestClient  # noqa: E402


async def main() -> None:
    config = KalshiConfig.load()
    async with KalshiRestClient(config) as client:
        t0 = time.perf_counter()
        raw = [e async for e in client.events(with_nested_markets=True)]
        full_s = time.perf_counter() - t0
        markets = sum(len(e.get("markets") or []) for e in raw)
        print(f"FULL WALK        {full_s:7.2f}s   {len(raw):,} events, {markets:,} markets")

        events = discover_from_events(raw, always_log_summary=False)
        by_series = collections.Counter(e.series_ticker for e in events)
        print(f"  priceable      {len(events):,} events across {len(by_series)} series")
        print(f"  series         {', '.join(sorted(by_series))}")
        print()

        total = 0.0
        got_events = 0
        got_markets = 0
        for series in sorted(by_series):
            t1 = time.perf_counter()
            rows = [
                e
                async for e in client.events(
                    with_nested_markets=True, series_ticker=series
                )
            ]
            took = time.perf_counter() - t1
            total += took
            got_events += len(rows)
            got_markets += sum(len(e.get("markets") or []) for e in rows)
            print(f"  {series:<28} {took:6.2f}s  {len(rows):>4} events")

        print()
        print(f"SERIES-SCOPED    {total:7.2f}s   {got_events:,} events, {got_markets:,} markets")
        if total > 0:
            print(f"speedup          {full_s / total:7.1f}x")

        # Does the scoped walk still see every priceable event? A cheaper fetch
        # that quietly drops rows is not a fetch, it is a filter.
        scoped = discover_from_events(
            [
                e
                for series in sorted(by_series)
                async for e in client.events(
                    with_nested_markets=True, series_ticker=series
                )
            ],
            always_log_summary=False,
        )
        full_set = {e.event_ticker for e in events}
        scoped_set = {e.event_ticker for e in scoped}
        print()
        print(f"COVERAGE         full {len(full_set)}  scoped {len(scoped_set)}")
        print(f"  missing from scoped: {sorted(full_set - scoped_set)[:5] or 'none'}")
        print(f"  extra in scoped:     {sorted(scoped_set - full_set)[:5] or 'none'}")


asyncio.run(main())
