"""Capture the Odds API tennis sport list and one tournament's h2h. SPENDS 2 CREDITS.

    .venv\\Scripts\\python.exe scripts/capture_tennis_odds_fixture.py --dry-run
    .venv\\Scripts\\python.exe scripts/capture_tennis_odds_fixture.py --confirm-spend-2

**Why this exists (#439).** "Check this parlay" should price a Kalshi tennis
match-winner leg on demand. No tennis odds payload had ever been captured, and
wire-format tests must load captured payloads (CLAUDE.md), so the link design
waits on this file. The Kalshi half is #441
(`tests/fixtures/kalshi_tennis_*.json`).

**What it writes.**

- `tests/fixtures/odds_tennis_sports.json` -- every tennis entry of
  `/v4/sports?all=true`. That endpoint costs nothing (`x-requests-last: 0`).
  It is the answer to #439's open question 1: the feed keys tennis **per
  tournament** (`tennis_atp_finals`, `tennis_wta_wimbledon`, ...), and lists
  **no Challenger tournament at all**.
- `tests/fixtures/odds_tennis_<key>_h2h.json` -- `/v4/sports/<key>/odds` for
  each ACTIVE tennis key, h2h only, the ten named bookmakers live buys
  (`fly.live.toml` `ODDS_BOOKMAKERS`). The vendor bills
  `len(markets) x ceil(books / 10)` = 1 credit a key (ADR 0155). The guard
  refuses to run when more than `MAX_KEYS` keys are active, so the spend
  cannot exceed the number the confirm flag names.

**Not recorded in `api_credits`.** A laptop run reaches the vendor directly;
the ledger never sees it. The drift is written into the #439 comment.

**The credential must not reach a file or a log line.** The key is a query
parameter and httpx logs URLs at INFO, so `configure_logging()` runs first,
`response.url` is never read, and every artefact is scanned for the key and
the string `apiKey` before it is written (`scripts/capture_nfl_odds_fixture.py`).

**What this does not establish.** It captures and stops: no link rate, no
name matching, no devig. One day's active tournaments say nothing about how
often a Kalshi tennis match has a sportsbook fixture across a season.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from backend.logging_setup import configure_logging  # noqa: E402
from scripts.capture_envelope import request_envelope, write_capture  # noqa: E402
from scripts.capture_nfl_odds_fixture import assert_no_credential  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE = "https://api.the-odds-api.com/v4/sports"
# fly.live.toml ODDS_BOOKMAKERS, pinned here rather than read from `.env`, for
# the reason capture_nfl_odds_fixture.py gives.
BOOKMAKERS = [
    "pinnacle", "matchbook", "betfair_ex_eu", "fanduel", "draftkings",
    "williamhill_us", "fanatics", "sport888", "bovada", "betmgm",
]
MARKETS = ["h2h"]
ODDS_FORMAT = "decimal"
MAX_KEYS = 2
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
TIMEOUT_S = 30.0


def _credit_headers(response: httpx.Response) -> dict[str, str]:
    return {
        k: response.headers[k]
        for k in ("x-requests-remaining", "x-requests-used", "x-requests-last")
        if k in response.headers
    }


def _get(client: httpx.Client, url: str, params: dict[str, str]) -> httpx.Response:
    response = client.get(url, params=params)
    if response.status_code != 200:
        raise SystemExit(f"ABORT: HTTP {response.status_code}. Body: {response.text[:400]}")
    return response


def main() -> int:
    configure_logging(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm-spend-2", action="store_true")
    args = parser.parse_args()

    per_key = len(MARKETS) * -(-len(BOOKMAKERS) // 10)
    print(f"cost per active key: {per_key} credit(s); at most {MAX_KEYS} keys")
    if not args.confirm_spend_2:
        print("DRY RUN -- nothing called. Re-run with --confirm-spend-2.")
        return 0

    api_key = os.environ.get("ODDS_API_KEY", "")
    if not api_key:
        print("ABORT: ODDS_API_KEY is not set.", file=sys.stderr)
        return 2

    with httpx.Client(timeout=TIMEOUT_S) as client:
        sports_resp = _get(client, BASE, {"apiKey": api_key, "all": "true"})
        tennis = [s for s in sports_resp.json() if str(s.get("key", "")).startswith("tennis")]
        active = [s["key"] for s in tennis if s.get("active")]
        sports_doc = {
            "captured_ms": int(time.time() * 1000),
            "note": "Tennis entries of /v4/sports?all=true, verbatim. Free endpoint.",
            "request": request_envelope(
                endpoint=BASE,
                params={"all": "true"},
                note="Credential omitted. Filtered to keys starting 'tennis' after the call.",
            ),
            "credit_headers": _credit_headers(sports_resp),
            "sports": tennis,
        }
        path = FIXTURES / "odds_tennis_sports.json"
        write_capture(path, sports_doc, indent=1,
                      before_write=lambda t: assert_no_credential(t, api_key, what=str(path)))
        print(f"WROTE {path}: {len(tennis)} tennis keys, active {active}")

        if len(active) > MAX_KEYS:
            print(f"REFUSING: {len(active)} active keys exceeds {MAX_KEYS}.", file=sys.stderr)
            return 2

        for key in active:
            params = {
                "bookmakers": ",".join(BOOKMAKERS),
                "markets": ",".join(MARKETS),
                "oddsFormat": ODDS_FORMAT,
            }
            resp = _get(client, f"{BASE}/{key}/odds", {"apiKey": api_key, **params})
            events: Any = json.loads(resp.text)
            doc = {
                "captured_ms": int(time.time() * 1000),
                "note": (
                    f"Verbatim /v4/sports/{key}/odds, h2h, ten named bookmakers. "
                    "Spent from a laptop: ABSENT from api_credits (#439)."
                ),
                "request": request_envelope(
                    endpoint=f"{BASE}/{key}/odds",
                    params={"sport": key, **params},
                    note=f"Credential omitted. Expected cost {per_key} credit(s).",
                ),
                "credit_headers": _credit_headers(resp),
                "events": events,
            }
            out = FIXTURES / f"odds_{key}_h2h.json"
            write_capture(out, doc, indent=1,
                          before_write=lambda t, o=out: assert_no_credential(t, api_key, what=str(o)))
            books = [len(e.get("bookmakers", [])) for e in events]
            print(f"WROTE {out}: {len(events)} events, books per event {books}, "
                  f"credits {doc['credit_headers']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
