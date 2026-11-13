"""Capture the three payloads the tennis link reads (#439). SPENDS 1 CREDIT.

    .venv\\Scripts\\python.exe scripts/capture_tennis_link_fixtures.py \\
        --kalshi-event KXWTAMATCH-26NOV13SABSVI --sport tennis_wta_finals \\
        --confirm-spend-1

Writes, each with its request (ADR 0157):

- `tests/fixtures/kalshi_tennis_single_event.json` -- Kalshi's public
  `GET /events/{event_ticker}?with_nested_markets=true`, the SINGLE-event
  shape. #441 captured only the list endpoint, whose wrapper differs.
- `tests/fixtures/odds_tennis_events_list.json` -- the Odds API's
  `/v4/sports/{key}/events`. Free: the vendor reports `x-requests-last: 0`.
- `tests/fixtures/odds_tennis_event_h2h.json` -- `/v4/sports/{key}/events/
  {id}/odds`, h2h, the ten named bookmakers, for the event whose two names
  equal the Kalshi event's two `yes_sub_title`s. One object, not a list.
  1 credit, spent from a laptop and ABSENT from `api_credits`.

The name match here is a plain casefolded set equality, only to choose which
event to buy. It is not the link design and proves nothing about one.

Credential handling is `capture_nfl_odds_fixture.py`'s: `configure_logging()`
first, `response.url` never read, every artefact scanned before writing.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from backend.logging_setup import configure_logging  # noqa: E402
from scripts.capture_envelope import request_envelope, write_capture  # noqa: E402
from scripts.capture_nfl_odds_fixture import assert_no_credential  # noqa: E402
from scripts.capture_tennis_odds_fixture import BOOKMAKERS, ODDS_FORMAT  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
ODDS = "https://api.the-odds-api.com/v4/sports"
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def _headers(r: httpx.Response) -> dict[str, str]:
    return {k: r.headers[k] for k in ("x-requests-remaining", "x-requests-used",
                                      "x-requests-last") if k in r.headers}


def _ok(r: httpx.Response) -> httpx.Response:
    if r.status_code != 200:
        raise SystemExit(f"ABORT: HTTP {r.status_code}. Body: {r.text[:400]}")
    return r


def main() -> int:
    configure_logging(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--kalshi-event", required=True)
    parser.add_argument("--sport", required=True)
    parser.add_argument("--confirm-spend-1", action="store_true")
    args = parser.parse_args()
    if not args.confirm_spend_1:
        print("DRY RUN -- re-run with --confirm-spend-1.")
        return 0
    key = os.environ.get("ODDS_API_KEY", "")
    if not key:
        print("ABORT: ODDS_API_KEY is not set.", file=sys.stderr)
        return 2
    scan = lambda what: (lambda t: assert_no_credential(t, key, what=what))  # noqa: E731

    with httpx.Client(timeout=30) as client:
        kparams = {"with_nested_markets": "true"}
        kr = _ok(client.get(f"{KALSHI}/events/{args.kalshi_event}", params=kparams))
        kdoc = kr.json()
        out = FIXTURES / "kalshi_tennis_single_event.json"
        write_capture(out, {
            "captured_ms": int(time.time() * 1000),
            "request": request_envelope(
                endpoint=f"{KALSHI}/events/{args.kalshi_event}",
                params={"event_ticker": args.kalshi_event, **kparams},
                note="Public, unauthenticated.",
            ),
            "response": kdoc,
        }, indent=1, before_write=scan(str(out)))
        markets = (kdoc.get("event") or {}).get("markets") or kdoc.get("markets") or []
        names = {str(m.get("yes_sub_title", "")).casefold() for m in markets}
        print(f"WROTE {out}: top-level keys {sorted(kdoc)}, names {sorted(names)}")

        er = _ok(client.get(f"{ODDS}/{args.sport}/events", params={"apiKey": key}))
        events = er.json()
        out = FIXTURES / "odds_tennis_events_list.json"
        write_capture(out, {
            "captured_ms": int(time.time() * 1000),
            "request": request_envelope(
                endpoint=f"{ODDS}/{args.sport}/events",
                params={"sport": args.sport},
                note="Credential omitted. Free endpoint.",
            ),
            "credit_headers": _headers(er),
            "events": events,
        }, indent=1, before_write=scan(str(out)))
        print(f"WROTE {out}: {len(events)} events, credits {_headers(er)}")

        chosen = [e for e in events
                  if {e["home_team"].casefold(), e["away_team"].casefold()} == names]
        if len(chosen) != 1:
            print(f"ABORT: {len(chosen)} events match {sorted(names)}; nothing bought.",
                  file=sys.stderr)
            return 1
        event_id = chosen[0]["id"]
        oparams = {"bookmakers": ",".join(BOOKMAKERS), "markets": "h2h",
                   "oddsFormat": ODDS_FORMAT}
        orr = _ok(client.get(f"{ODDS}/{args.sport}/events/{event_id}/odds",
                             params={"apiKey": key, **oparams}))
        out = FIXTURES / "odds_tennis_event_h2h.json"
        write_capture(out, {
            "captured_ms": int(time.time() * 1000),
            "request": request_envelope(
                endpoint=f"{ODDS}/{args.sport}/events/{event_id}/odds",
                params={"sport": args.sport, "event_id": event_id, **oparams},
                note="Credential omitted. Laptop spend, ABSENT from api_credits (#439).",
            ),
            "credit_headers": _headers(orr),
            "event": orr.json(),
        }, indent=1, before_write=scan(str(out)))
        books = [b["key"] for b in orr.json().get("bookmakers", [])]
        print(f"WROTE {out}: books {books}, credits {_headers(orr)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
