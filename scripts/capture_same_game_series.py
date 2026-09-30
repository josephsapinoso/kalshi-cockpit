"""Capture one NHL fixture's GAME/SPREAD/TOTAL events and the college-basketball series names (#251).

Read-only, unauthenticated Kalshi market data: `GET /events` and `GET /series`.
No key is read, no order/RFQ/portfolio endpoint is touched.

Writes (with their request, via `capture_envelope.write_capture`):
  tests/fixtures/events_nhl_same_game.json       one fixture, three event tickers
  tests/fixtures/series_college_basketball.json  series catalogue slice
  tests/fixtures/markets_nba_game_rules.json     KXNBAGAME markets with rules_primary (#255, `--nba-rules`)

Does NOT establish: college-basketball EVENT tickers. The season was not open
when this ran (2026-09-30), so `/events?series_ticker=KXNCAAMBGAME` returned no
events; only the series names are captured, and the fixture records that probe.
"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from capture_envelope import request_envelope, write_capture  # noqa: E402

BASE = "https://api.elections.kalshi.com/trade-api/v2"
NHL = ("KXNHLGAME", "KXNHLSPREAD", "KXNHLTOTAL")
COLLEGE_PROBES = (
    "KXNCAAMBGAME", "KXNCAAMBSPREAD", "KXNCAAMBTOTAL",
    "KXNCAAWBGAME", "KXNCAAWBSPREAD", "KXNCAAWBTOTAL",
    "KXNCAABGAME",
)
BASEBALL = ("KXNCAABBGAME", "KXNCAABBSPREAD", "KXNCAABBTOTAL")


def events(client, series):
    params = {"series_ticker": series, "status": "open", "limit": 200,
              "with_nested_markets": "true"}
    r = client.get(f"{BASE}/events", params=params)
    r.raise_for_status()
    body = r.json()
    if "events" not in body:
        raise KeyError(f"no 'events' key: {sorted(body)}")
    return body["events"]


def capture_nba_rules() -> int:
    """#255 part 1: one two-sided NBA game's markets, for their `rules_primary`."""
    fx = ROOT / "tests" / "fixtures"
    params = {"series_ticker": "KXNBAGAME", "limit": 4}
    with httpx.Client(timeout=30.0) as c:
        r = c.get(f"{BASE}/markets", params=params)
        r.raise_for_status()
        body = r.json()
    markets = body.get("markets")
    if not markets:
        print("REFUSED: no KXNBAGAME markets posted; nothing carries the rules")
        return 2
    event = markets[0]["event_ticker"]
    kept = [m for m in markets if m["event_ticker"] == event]
    write_capture(
        fx / "markets_nba_game_rules.json",
        {
            "request": request_envelope(
                endpoint=f"{BASE}/markets",
                params=params,
                note=f"kept only the markets of event {event}",
            ),
            "endpoint": f"{BASE}/markets",
            "markets": kept,
        },
    )
    print("wrote", event, len(kept))
    return 0


def main() -> int:
    if "--nba-rules" in sys.argv:
        return capture_nba_rules()
    fx = ROOT / "tests" / "fixtures"
    with httpx.Client(timeout=30.0) as c:
        got = {s: events(c, s) for s in NHL}
        suffixes = [
            {e["event_ticker"].split("-", 1)[1] for e in got[s]} for s in NHL
        ]
        common = sorted(set.intersection(*suffixes))
        if not common:
            print("REFUSED: no fixture has GAME, SPREAD and TOTAL open")
            return 2
        seg = common[0]
        doc = {
            "request": request_envelope(
                endpoint=f"{BASE}/events",
                params={"series_ticker": list(NHL), "status": "open",
                        "limit": 200, "with_nested_markets": "true"},
                note=f"one call per series; kept only the events for fixture {seg}",
            ),
            "endpoint": f"{BASE}/events",
            "fixture_segment": seg,
            "events": [
                e for s in NHL for e in got[s]
                if e["event_ticker"].split("-", 1)[1] == seg
            ],
        }
        write_capture(fx / "events_nhl_same_game.json", doc)

        probes = {s: len(events(c, s)) for s in COLLEGE_PROBES}
        sr = c.get(f"{BASE}/series", params={"category": "Sports"})
        sr.raise_for_status()
        wanted = set(COLLEGE_PROBES) | set(BASEBALL)
        keep = [
            {"ticker": s["ticker"], "title": s.get("title")}
            for s in sr.json()["series"]
            if s["ticker"] in wanted
        ]
        write_capture(
            fx / "series_college_basketball.json",
            {
                "request": request_envelope(
                    endpoint=f"{BASE}/series",
                    params={"category": "Sports"},
                    note="kept college GAME/SPREAD/TOTAL series only; "
                         "open_event_counts is from GET /events per series",
                ),
                "endpoint": f"{BASE}/series",
                "open_event_counts": probes,
                "series": sorted(keep, key=lambda s: s["ticker"]),
            },
        )
    print("wrote", seg, probes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
