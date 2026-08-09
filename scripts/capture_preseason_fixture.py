"""Capture the NFL preseason events -- the league string that has no mapping.

**Why this exists as its own capture.** `tests/fixtures/events_sports_nested.json`
is a walk of the whole sports universe taken on 2026-08-06, and it happens to
contain no preseason market. Every discovery test passed on it while
`"Pro Football Preseason"` -- Kalshi's spelling, which is not the
`"Pro Football"` in `IN_SCOPE_LEAGUES` -- was dropping 48 events and 726 markets
from the universe with no warning, no counter and no red test. That is the
repo's own lesson in `tasks/lessons.md`: a fixture-based test protects against
the API changing, not against misreading it on day one.

So the fixture this capture writes exists to make the *league* axis testable the
way the scope axis already was, and it is captured from one series on purpose:

    GET /events?series_ticker=KXNFLGAME&status=open&with_nested_markets=true

**One series ticker, two leagues.** That single request returns 16 events whose
`competition` is `"Pro Football Preseason"` and 16 whose `competition` is
`"Pro Football"`, and every one of them carries `competition_scope == "Game"`.
Neither the series ticker nor the scope can tell the two populations apart --
only the league string does. A capture split across three series would have
buried that; this one puts it on the same page.

No credentials. `/events` is a free unauthenticated read, so this costs nothing
and spends no odds credits. Read-only, places no orders.

Run:

    .venv\\Scripts\\python.exe scripts\\capture_preseason_fixture.py

Re-capturing outside the preseason window (roughly late July to early September)
will return regular-season events only, and `tests/test_discovery.py` will fail
loudly rather than silently accept a fixture that no longer contains the case it
was captured for. That failure is the point: the fixture is a pinned artefact,
not something to refresh on a schedule.
"""

from __future__ import annotations

import collections
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
OUT = FIXTURES / "events_nfl_preseason.json"

# Unauthenticated base. Not read from config on purpose: the value of this
# capture is partly that it needs nothing, and a config load would make a
# credential-less contributor unable to reproduce it.
BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
SERIES = "KXNFLGAME"


def capture() -> int:
    with httpx.Client(timeout=30.0) as client:
        response = client.get(
            f"{BASE_URL}/events",
            params={
                "series_ticker": SERIES,
                "status": "open",
                "limit": "200",
                "with_nested_markets": "true",
            },
        )
        response.raise_for_status()
        payload = response.json()

    events = payload.get("events") or []
    cursor = payload.get("cursor") or ""
    if cursor:
        # One page held the whole series on 2026-08-09. If that stops being true
        # the capture is a *partial* series, which would look like a shrinking
        # league rather than a truncated read -- so say so instead of writing it.
        print(f"FAIL  {SERIES} no longer fits one page (cursor={cursor!r}). "
              f"Nothing written; paginate before re-capturing.")
        return 1

    by_league: collections.Counter = collections.Counter()
    for event in events:
        metadata = event.get("product_metadata") or {}
        by_league[(metadata.get("competition") or "").strip()] += 1

    print(f"{len(events)} events from {SERIES}")
    for league, count in by_league.most_common():
        print(f"  {league!r:<28} {count} events")

    if len(by_league) < 2:
        print(
            "\nWARN  only one league string came back. Preseason is listed from "
            "roughly late July to early September; outside that window this "
            "capture cannot show the two-populations-one-series case it exists "
            "for. Writing anyway -- the test asserts on the content and will "
            "fail, which is the intended signal."
        )

    document = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "endpoint": (
            f"GET /events?series_ticker={SERIES}&status=open"
            f"&with_nested_markets=true (unauthenticated)"
        ),
        "note": (
            "Verbatim API response. Captured because "
            "events_sports_nested.json contains no preseason market, so the "
            "league classifier was untested on the one value it was getting "
            "wrong. Every event here shares the series ticker "
            f"{SERIES} and the competition_scope 'Game'; only "
            "product_metadata.competition separates preseason from the "
            "regular season."
        ),
        "series_ticker": SERIES,
        "events": events,
    }
    OUT.write_text(json.dumps(document, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(OUT.parents[2])} "
          f"({OUT.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(capture())
