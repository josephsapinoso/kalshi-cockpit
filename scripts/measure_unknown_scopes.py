"""What is the classifier actually throwing away, and is any of it a sport?

`discover_from_events` excludes every event whose `competition_scope` is not in
`FIXTURE_SCOPES` or `EXCLUDED_SCOPES`, warns once per process per
`(series_ticker, scope)` pair, and reports the pair count on every pass as
`unknown_scopes=N`. On the live instance that count is **962**.

The repo's handoff notes describe this population as "94 distinct series, not
one of them a sport (KXFED, KXWMT, AP polls, draft picks)". That description
was written from the warnings visible in `flyctl logs`, and only 94 of the 962
warning lines survived Fly's log pipeline -- the burst is emitted inside ~90ms
and the stream drops most of it. So the reassuring characterisation was drawn
from a ~10% sample that nobody knew was a sample, selected by whichever lines
the log shipper happened to keep.

This harness enumerates the whole population directly from Kalshi instead, and
checks the one thing that matters: **is any excluded series in a league this
project can price?** An in-scope league appearing here is a silently dropped
market, which is the failure `tasks/lessons.md` records under "test the
filter's exclusions".

Run:

    .venv\\Scripts\\python.exe scripts\\measure_unknown_scopes.py
    .venv\\Scripts\\python.exe scripts\\measure_unknown_scopes.py --json out.json

Read-only. Places no orders. **Spends no Odds API credits and never calls The
Odds API** -- the daily budget is ~16 and is shared with the live instance.
Never paginates `/markets`; discovery is through `/events`, exactly as the
runner does it.

Unauthenticated on purpose. `/events` answers 200 without credentials, so this
script cannot read, log or leak the private key -- it never loads it.

What this harness does NOT establish
------------------------------------
- **It does not say an excluded series should be priced.** It says which ones
  are excluded and which sit in an in-scope league. Whether a given scope is
  per-fixture is a judgement about the product, and adding one to
  `FIXTURE_SCOPES` needs a look at the market itself.
- **It is one slate.** `status=open` is what exists right now. A series with no
  open event today is absent here and is not evidence of anything.
- **It does not measure liquidity, price or edge.** Nothing here should be read
  as evidence that an excluded market is worth trading.
- **It cannot distinguish "Kalshi renamed a scope" from "Kalshi added one".**
  Both present as an unrecognised string.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterator, Optional

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.kalshi.discovery import (  # noqa: E402
    EXCLUDED_SCOPES,
    FIXTURE_SCOPES,
    IN_SCOPE_LEAGUES,
    PERIOD_SCOPES,
)

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
JUNK_PREFIX = "KXMVE"
HTTP_TIMEOUT_S = 60.0
PAGE_LIMIT = 200

# Politeness. Kalshi's documented read limit is ~10/s and an unthrottled walk
# of `/events` drew a 429 on page 14. A throttled sweep that silently returns
# fewer pages is the failure worth paying seconds to avoid -- a short
# enumeration would read as "no in-scope league is excluded", which is the
# conclusion this harness exists to test.
SLEEP_S = 0.25
MAX_RETRIES = 5


def walk_events(client: httpx.Client) -> Iterator[dict]:
    """Paginate `/events` the way the runner does. Never paginate `/markets`."""
    cursor: Optional[str] = None
    pages = 0
    while True:
        # `with_nested_markets` mirrors `KalshiClient.events`. It is not
        # cosmetic: without it the walk returns a different payload from the one
        # the runner classifies, and the first run of this harness reported
        # `no_commence_time=167` and zero priceable events against a production
        # pass that finds 167 and warns about neither. A harness that issues a
        # different request than production is measuring a different system.
        params: dict[str, Any] = {
            "status": "open",
            "limit": PAGE_LIMIT,
            "with_nested_markets": "true",
        }
        if cursor:
            params["cursor"] = cursor

        for attempt in range(MAX_RETRIES):
            response = client.get(f"{BASE_URL}/events", params=params)
            if response.status_code != 429:
                break
            backoff = SLEEP_S * (2 ** (attempt + 2))
            print(f"  429; backing off {backoff:.1f}s", file=sys.stderr)
            time.sleep(backoff)
        response.raise_for_status()
        payload = response.json()

        events = payload.get("events") or []
        if not events:
            break
        for event in events:
            if (event.get("event_ticker") or "").startswith(JUNK_PREFIX):
                continue
            yield event

        pages += 1
        cursor = payload.get("cursor") or None
        if not cursor:
            break
        if pages % 10 == 0:
            print(f"  ... {pages} pages", file=sys.stderr)
        time.sleep(SLEEP_S)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="write the full table here")
    args = parser.parse_args()

    print("Walking /events (unauthenticated, no odds credits) ...", file=sys.stderr)
    with httpx.Client(timeout=HTTP_TIMEOUT_S) as client:
        events = list(walk_events(client))
    print(f"{len(events)} events\n", file=sys.stderr)

    # (series_ticker, scope) -> the leagues it was seen under, and how often.
    unknown: dict[tuple[str, str], Counter] = defaultdict(Counter)
    known_scopes: Counter = Counter()
    scope_totals: Counter = Counter()

    for event in events:
        metadata = event.get("product_metadata") or {}
        series = event.get("series_ticker") or ""
        league = (metadata.get("competition") or "").strip() or "(no competition)"
        scope = (metadata.get("competition_scope") or "").strip()
        if not scope:
            continue
        normalised = scope.lower()
        if normalised in FIXTURE_SCOPES or normalised in EXCLUDED_SCOPES:
            known_scopes[scope] += 1
            continue
        unknown[(series, scope)][league] += 1
        scope_totals[scope] += 1

    # The question the harness exists for: does any excluded pair sit in a
    # league this project can devig against? Anything here is a market being
    # dropped in silence, not a market being declined.
    in_scope_hits = [
        (series, scope, league, n)
        for (series, scope), leagues in sorted(unknown.items())
        for league, n in leagues.items()
        if league in IN_SCOPE_LEAGUES
    ]

    print(f"recognised scopes      {sum(known_scopes.values())} events "
          f"across {len(known_scopes)} scopes")
    for scope, n in known_scopes.most_common():
        # Three buckets, not two. A period scope is per-fixture *and* excluded,
        # so folding it into "non-fixture" would print something untrue about
        # the product in the one report whose job is to describe the product.
        normalised = scope.lower()
        if normalised in FIXTURE_SCOPES:
            bucket = "fixture"
        elif normalised in PERIOD_SCOPES:
            bucket = "period, excluded"
        else:
            bucket = "non-fixture"
        print(f"    {scope:<28} {n:>6}  ({bucket})")

    print(f"\nunrecognised scopes    {len(unknown)} distinct "
          f"(series, scope) pairs across {len(scope_totals)} scopes")
    for scope, n in scope_totals.most_common():
        series_count = sum(1 for (_, s) in unknown if s == scope)
        print(f"    {scope:<28} {n:>6} events, {series_count} series")

    print("\nIN-SCOPE LEAGUES AMONG THE EXCLUDED "
          "(the only result that changes anything)")
    if in_scope_hits:
        for series, scope, league, n in sorted(in_scope_hits, key=lambda r: -r[3]):
            print(f"    {series:<28} scope={scope!r:<20} {league:<20} {n} events")
        print(f"\n    {len(in_scope_hits)} pairs. Each is a priceable league "
              f"whose markets are being dropped without a decision.")
    else:
        print("    none -- every excluded pair is in a league this project "
              "cannot devig against anyway.")

    leagues_seen = Counter(
        league
        for leagues in unknown.values()
        for league, n in leagues.items()
        for _ in range(n)
    )
    print("\nexcluded events by league (top 25)")
    for league, n in leagues_seen.most_common(25):
        mark = "  <-- IN SCOPE" if league in IN_SCOPE_LEAGUES else ""
        print(f"    {league:<40} {n:>6}{mark}")

    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "events_walked": len(events),
                    "unknown_pairs": [
                        {"series": s, "scope": sc, "leagues": dict(lg)}
                        for (s, sc), lg in sorted(unknown.items())
                    ],
                    "in_scope_hits": [
                        {"series": s, "scope": sc, "league": lg, "events": n}
                        for s, sc, lg, n in in_scope_hits
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nwrote {args.json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
