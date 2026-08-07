"""Discovery spike: does Kalshi list per-GAME sports markets, and where?

This is the load-bearing unknown for the whole project. The previous project
recorded **zero** single-game moneyline tickers -- everything it ever saw was a
future or a season prop (`KXMLBWINS-NYY-26-T85`, `KXNFLWINS-27MIN-8`). The
devig pipeline only works if Kalshi lists per-game markets that map onto
sportsbook h2h/spreads/totals. Public sources suggest `KXNBAGAME` and
`KXNHLGAME` exist; nothing in hand pins the format or the liquidity.

So: walk the real universe, capture real payloads, and report per series
whether it carries game markets and whether they are tradeable. **A league
without tradeable game markets drops from scope**, and the plan says so rather
than matching against nothing.

Two things this script deliberately does NOT do:

- **It never paginates `/markets`.** That endpoint is ~99.8% `KXMVE`
  auto-generated combinatorial junk; a 25,000-row scan returned zero markets
  with any volume. `/events?with_nested_markets=true` excludes MVE entirely and
  returns ~1,500 real markets in one request.
- **It never hand-writes a payload.** Everything saved to `tests/fixtures/` is
  exactly what the API returned, because a hand-written fixture only proves the
  code agrees with the author's memory of the API. That is precisely how the
  previous project parsed every order book to zero levels, silently, for its
  entire life, while 305 synthetic tests passed.

Run:

    .venv\\Scripts\\python.exe scripts\\capture_fixtures.py

Read-only. Places no orders.
"""

from __future__ import annotations

import json
import re
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import ConfigError, KalshiConfig  # noqa: E402
from backend.core.prices import dollars_to_tenths  # noqa: E402
from backend.kalshi.auth import KalshiAuth, signed_path  # noqa: E402

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
JUNK_PREFIX = "KXMVE"
PAGE_LIMIT = 200
MAX_PAGES = 40
# Politeness: the previous project had no rate limiting anywhere and its
# discovery routine fired 100 sequential requests inside a bare except.
SLEEP_BETWEEN_PAGES_S = 0.25

# A game market resolves on a single fixture, so it closes within days. Futures
# and season props close months out. This is a heuristic for *reporting*, not a
# filter -- the report shows the evidence and a human decides.
GAME_HORIZON_DAYS = 14

_VS = re.compile(r"\b(vs\.?|@|at)\b", re.IGNORECASE)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _parse_ms(value: Any) -> int | None:
    """Kalshi timestamps to epoch ms, UTC. Unreadable -> None, never 0."""
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.astimezone(timezone.utc).timestamp() * 1000)
    except (ValueError, TypeError):
        return None


def walk_events(
    auth: KalshiAuth, base_url: str, status: str = "open"
) -> Iterator[dict]:
    """Cursor-paginate `/events?with_nested_markets=true`.

    Yields raw event dicts exactly as returned. Junk filtering happens
    downstream so the captured fixture keeps whatever the API actually sent.
    """
    cursor = ""
    with httpx.Client(timeout=30.0) as client:
        for page in range(MAX_PAGES):
            params = {
                "status": status,
                "limit": str(PAGE_LIMIT),
                "with_nested_markets": "true",
            }
            if cursor:
                params["cursor"] = cursor

            path = "/events"
            # Query strings are NOT signed -- verified 2026-08-06. Sign the
            # path, send the query.
            headers = auth.get_rest_headers("GET", signed_path(base_url, path))
            resp = client.get(f"{base_url}{path}", params=params, headers=headers)

            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", "2"))
                print(f"    429, backing off {retry_after}s")
                time.sleep(retry_after)
                continue
            resp.raise_for_status()

            payload = resp.json()
            events = payload.get("events", [])
            if not events:
                return
            yield from events

            cursor = payload.get("cursor", "")
            print(f"    page {page + 1}: {len(events)} events")
            if not cursor:
                return
            time.sleep(SLEEP_BETWEEN_PAGES_S)


def summarise(events: list[dict]) -> dict[str, dict]:
    """Group sports events by series and gather the evidence for a scope call."""
    by_series: dict[str, dict] = defaultdict(
        lambda: {
            "events": 0,
            "markets": 0,
            "sample_event_tickers": [],
            "sample_market_tickers": [],
            "sample_titles": [],
            "days_to_close": [],
            "markets_per_event": [],
            "total_volume_24h": 0.0,
            "total_open_interest": 0.0,
            "quoted_markets": 0,
            "title_looks_like_fixture": 0,
            "category": "",
        }
    )
    now = _now_ms()

    for event in events:
        event_ticker = event.get("event_ticker", "")
        if event_ticker.startswith(JUNK_PREFIX):
            continue
        category = (event.get("category") or "").strip()
        if "sport" not in category.lower():
            continue

        series = event.get("series_ticker") or event_ticker.split("-")[0]
        entry = by_series[series]
        entry["category"] = category
        entry["events"] += 1

        if len(entry["sample_event_tickers"]) < 5:
            entry["sample_event_tickers"].append(event_ticker)
        title = (event.get("title") or "").strip()
        if title and len(entry["sample_titles"]) < 5:
            entry["sample_titles"].append(title)
        if title and _VS.search(title):
            entry["title_looks_like_fixture"] += 1

        markets = [
            m
            for m in (event.get("markets") or [])
            if not (m.get("ticker") or "").startswith(JUNK_PREFIX)
        ]
        entry["markets"] += len(markets)
        entry["markets_per_event"].append(len(markets))

        for market in markets:
            ticker = market.get("ticker", "")
            if len(entry["sample_market_tickers"]) < 5:
                entry["sample_market_tickers"].append(ticker)

            close_ms = _parse_ms(market.get("close_time"))
            if close_ms is not None:
                entry["days_to_close"].append((close_ms - now) / 86_400_000)

            entry["total_volume_24h"] += float(market.get("volume_24h_fp") or 0)
            entry["total_open_interest"] += float(market.get("open_interest_fp") or 0)

            # A market nobody is quoting is not tradeable, however many exist.
            yes_bid = dollars_to_tenths(market.get("yes_bid_dollars"))
            no_bid = dollars_to_tenths(market.get("no_bid_dollars"))
            if (yes_bid or 0) > 0 or (no_bid or 0) > 0:
                entry["quoted_markets"] += 1

    return dict(by_series)


def report(summary: dict[str, dict]) -> list[str]:
    """Print the coverage report and return the series that look game-level."""
    if not summary:
        print("\nNo sports events found at all. Either the category label has "
              "changed or nothing is open right now.")
        return []

    rows = []
    for series, e in summary.items():
        median_days = (
            statistics.median(e["days_to_close"]) if e["days_to_close"] else None
        )
        median_mkts = (
            statistics.median(e["markets_per_event"]) if e["markets_per_event"] else 0
        )
        quoted_share = e["quoted_markets"] / e["markets"] if e["markets"] else 0.0
        looks_game = (
            median_days is not None
            and median_days <= GAME_HORIZON_DAYS
            and e["title_looks_like_fixture"] > 0
        )
        rows.append(
            {
                "series": series,
                "events": e["events"],
                "markets": e["markets"],
                "median_days": median_days,
                "median_mkts_per_event": median_mkts,
                "quoted_share": quoted_share,
                "volume": e["total_volume_24h"],
                "oi": e["total_open_interest"],
                "looks_game": looks_game,
                "fixture_titles": e["title_looks_like_fixture"],
                "sample_market": (
                    e["sample_market_tickers"][0] if e["sample_market_tickers"] else ""
                ),
                "sample_title": e["sample_titles"][0] if e["sample_titles"] else "",
            }
        )

    rows.sort(key=lambda r: (-r["volume"], r["series"]))

    print("\n" + "=" * 100)
    print("SPORTS SERIES COVERAGE")
    print("=" * 100)
    print(
        f"{'series':<26}{'evts':>5}{'mkts':>6}{'d2close':>9}"
        f"{'m/evt':>7}{'quoted':>8}{'vol24h':>11}  game?"
    )
    print("-" * 100)
    for r in rows:
        days = f"{r['median_days']:.1f}" if r["median_days"] is not None else "?"
        print(
            f"{r['series'][:25]:<26}{r['events']:>5}{r['markets']:>6}{days:>9}"
            f"{r['median_mkts_per_event']:>7.0f}{r['quoted_share']:>7.0%}"
            f"{r['volume']:>11,.0f}  {'YES' if r['looks_game'] else '-'}"
        )

    game_series = [r["series"] for r in rows if r["looks_game"]]

    print("\n" + "=" * 100)
    print("VERDICT")
    print("=" * 100)
    if game_series:
        print(f"{len(game_series)} series look game-level "
              f"(close within {GAME_HORIZON_DAYS}d and fixture-shaped titles):\n")
        for r in rows:
            if r["looks_game"]:
                print(f"  {r['series']}")
                print(f"      example market: {r['sample_market']}")
                print(f"      example title : {r['sample_title']}")
                print(f"      tradeable     : {r['quoted_share']:.0%} of markets quoted, "
                      f"{r['volume']:,.0f} 24h volume")
    else:
        print("NO series look game-level. Every sports market visible is a")
        print("future or season prop -- exactly what the previous project saw.")
        print("The devig pipeline has nothing to match against.")
        print("\nBefore concluding, check: is a slate actually scheduled right now?")
        print("Game markets may only be listed close to game time.")

    print("\nScope call: leagues without tradeable game markets drop. Record the")
    print("decision in docs/adr/ and tasks/todo.md rather than leaving it implicit.")
    return game_series


def main() -> int:
    try:
        cfg = KalshiConfig.load()
    except ConfigError as exc:
        print(f"FAIL  configuration: {exc}")
        return 2

    auth = KalshiAuth(cfg.api_key, cfg.private_key_path)
    FIXTURES.mkdir(parents=True, exist_ok=True)

    print("Walking /events?with_nested_markets=true (never /markets) ...")
    try:
        events = list(walk_events(auth, cfg.rest_url))
    except httpx.HTTPStatusError as exc:
        print(f"FAIL  HTTP {exc.response.status_code} from {exc.request.url}")
        return 1

    print(f"\n  {len(events)} events total")

    sports = [
        e
        for e in events
        if "sport" in (e.get("category") or "").lower()
        and not (e.get("event_ticker") or "").startswith(JUNK_PREFIX)
    ]
    print(f"  {len(sports)} sports events after KXMVE filter")

    # Capture the real payload. This is the wire-format contract that every
    # parser test loads from, so it must be what the API sent, unedited.
    capture = FIXTURES / "events_sports_nested.json"
    capture.write_text(json.dumps(sports, indent=2), encoding="utf-8")
    print(f"  captured -> {capture.relative_to(FIXTURES.parent.parent)}")

    if sports:
        keys: set[str] = set()
        for event in sports[:50]:
            for market in event.get("markets") or []:
                keys.update(market.keys())
        print(f"\n  market fields seen ({len(keys)}):")
        print("    " + ", ".join(sorted(keys)))

    game_series = report(summarise(sports))

    verdict = FIXTURES / "sports_coverage.json"
    verdict.write_text(
        json.dumps(
            {
                "captured_ms": _now_ms(),
                "total_events": len(events),
                "sports_events": len(sports),
                "game_level_series": game_series,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n  verdict -> {verdict.relative_to(FIXTURES.parent.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
