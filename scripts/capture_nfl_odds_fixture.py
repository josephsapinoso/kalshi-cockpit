"""Capture one verbatim NFL odds payload as a wire fixture. SPENDS 4 CREDITS.

    .venv\\Scripts\\python.exe scripts/capture_nfl_odds_fixture.py --dry-run
    .venv\\Scripts\\python.exe scripts/capture_nfl_odds_fixture.py --confirm-spend-4

**Why this exists.** No NFL odds payload had ever been parsed by any test in
this repo -- the only captured Odds API response was MLB
(`tests/fixtures/odds_mlb_h2h_spreads_totals.json`, 2026-08-07). The live
bootstrap at 2026-09-08 03:23:58Z proved the *link* between Kalshi events and
sportsbook fixtures and proved nothing whatever about whether the parser reads
an NFL payload correctly, because a link is not a parse. Football carries
American-football spreads -- half-point hooks across a far wider range than
baseball's fixed run line -- and a team-name vocabulary the MLB capture cannot
exercise.

**The request shape is the deployed one, pinned here, and deliberately NOT read
from the laptop's `.env`.** Live sets `ODDS_MARKETS = "h2h,spreads"` and
`ODDS_REGIONS = "us,eu"` in `fly.live.toml [env]`; this laptop's `.env` carries
`ODDS_MARKETS=h2h`, the older and narrower shape. Reading the environment would
therefore have captured a two-credit payload of a request **the recorder does
not make**, and the fixture would have pinned a code path nobody runs while
looking entirely correct. So the two lists are constants below and the cost
guard asserts they still multiply to 4. If live's shape changes, change these
and the guard together -- that coupling is the point.

**This capture is NOT recorded in `api_credits`.** That table is written by the
runner on the live box; a laptop run reaches the vendor directly and the ledger
never sees it. The drift is **+4 credits against the vendor, invisible to every
`credits-day` and `credits-month` read**. It is written into
`docs/measurements/2026-09-07-nfl-live-path-preflight.md` rather than left
silent, because an unexplained 4-credit gap in a monthly reconciliation is
exactly what a later session burns an hour on.

**The credential must not reach a file or a log line.** The Odds API takes its
key as a **query parameter** and `httpx` logs full URLs at INFO -- that is how
it leaked once, and `backend/logging_setup.py` exists because of it. So:
`configure_logging()` is the first statement in `main`; `response.url` is never
read, logged, or serialised; and the artefact is asserted free of both the key
and the string `apiKey` *before* it is written. **This repo is public and the
file is world-readable the moment it is pushed.**

**What this script does not do.** It captures and stops -- no test, no analysis,
no assertion about content. `tests/test_odds_nfl_wire.py` reads the file
offline, forever, at zero credit cost. That split is deliberate: a bug in an
assertion then costs nothing to fix, whereas a bug in the capture costs another
slate that has already moved on.
"""

from __future__ import annotations

import argparse
import asyncio
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

# `.env` is loaded for ODDS_API_KEY ONLY. The request shape below is pinned to
# live's, never taken from it -- see the module docstring.
load_dotenv()

SPORT_KEY = "americanfootball_nfl"
REGIONS = ["us", "eu"]  # fly.live.toml: ODDS_REGIONS = "us,eu"
MARKETS = ["h2h", "spreads"]  # fly.live.toml: ODDS_MARKETS = "h2h,spreads"
ODDS_FORMAT = "decimal"
TIMEOUT_S = 30.0
EXPECTED_COST = 4
FIXTURE = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "odds_nfl_h2h_spreads.json"
)


def assert_no_credential(text: str, api_key: str, *, what: str) -> None:
    """Refuse to write anything carrying the key, or a query string that could.

    Two checks, not one. The key itself is the obvious hazard; `apiKey` catches
    a serialised request URL that would carry it even if this particular key
    were later rotated. Raises rather than warns -- a warning nobody reads is
    not a control. The rule is `scripts/capture_odds_repeat_poll.py`'s, learned
    the hard way.
    """
    if api_key and api_key in text:
        raise RuntimeError(
            f"REFUSING TO WRITE {what}: it contains the live ODDS_API_KEY. "
            "The key is in this process's memory only -- do not paste any part "
            "of this payload anywhere. Rotate if it reached disk."
        )
    if "apiKey" in text:
        raise RuntimeError(
            f"REFUSING TO WRITE {what}: it contains the string 'apiKey', which "
            "means a request URL has been serialised. The Odds API puts the "
            "credential in the query string. See tasks/lessons.md."
        )


async def _fetch(api_key: str) -> tuple[str, dict[str, str]]:
    """Return the raw body text and the two credit headers. Never the URL.

    The body comes back as **text** rather than parsed, so the artefact can
    record the vendor's original numeric tokens if that is ever needed. Only
    `x-requests-remaining` and `x-requests-used` are copied, by name -- never
    the whole header set, which carries request context.
    """
    url = f"https://api.the-odds-api.com/v4/sports/{SPORT_KEY}/odds"
    params = {
        "apiKey": api_key,
        "regions": ",".join(REGIONS),
        "markets": ",".join(MARKETS),
        "oddsFormat": ODDS_FORMAT,
    }
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
        response = await client.get(url, params=params)
        if response.status_code != 200:
            # `response.text` is the vendor's error body and carries no
            # credential; `response.url` would, and is not touched.
            raise SystemExit(
                f"ABORT: the vendor returned HTTP {response.status_code}. "
                f"Body: {response.text[:400]}"
            )
        headers = {
            k: response.headers[k]
            for k in ("x-requests-remaining", "x-requests-used")
            if k in response.headers
        }
        return response.text, headers


def main() -> int:
    # First statement that matters. Not `logging.basicConfig`: httpx logs full
    # request URLs at INFO and the credential lives in the query string.
    configure_logging(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="Capture an NFL odds wire fixture.")
    parser.add_argument("--dry-run", action="store_true", help="print the plan, spend nothing")
    parser.add_argument(
        "--confirm-spend-4",
        action="store_true",
        help=f"actually call the vendor; costs {EXPECTED_COST} credits",
    )
    args = parser.parse_args()

    cost = len(REGIONS) * len(MARKETS)
    print(f"sport   {SPORT_KEY}")
    print(f"regions {REGIONS}")
    print(f"markets {MARKETS}")
    print(f"cost    {cost} credits  (len(regions) x len(markets))")
    print(f"out     {FIXTURE}")

    if cost != EXPECTED_COST:
        print(
            f"\nREFUSING: this shape costs {cost} credits, not {EXPECTED_COST}. "
            "REGIONS or MARKETS was edited without the confirm flag being "
            "re-decided. The flag names the price so a widened shape cannot "
            "spend more than the operator agreed to. Change both, deliberately.",
            file=sys.stderr,
        )
        return 2

    if not args.confirm_spend_4:
        print("\nDRY RUN -- nothing was called and no credit was spent.")
        print(f"Re-run with --confirm-spend-{EXPECTED_COST} to capture.")
        return 0

    api_key = os.environ.get("ODDS_API_KEY", "")
    if not api_key:
        print("ABORT: ODDS_API_KEY is not set in the environment.", file=sys.stderr)
        return 2

    body, headers = asyncio.run(_fetch(api_key))
    events: Any = json.loads(body)

    if not isinstance(events, list) or not events:
        # An empty list means no fixtures, which for a capture is an abort
        # rather than a finding -- there is nothing to pin.
        got = len(events) if isinstance(events, list) else "a non-list"
        print(
            f"ABORT: the vendor returned {got} events. The credit is spent; "
            "nothing was written.",
            file=sys.stderr,
        )
        return 1

    artefact = {
        "captured_ms": int(time.time() * 1000),
        "note": (
            f"Verbatim /v4/sports/{SPORT_KEY}/odds capture, "
            f"{'+'.join(REGIONS)}, {'+'.join(MARKETS)}, {ODDS_FORMAT}. "
            "Cost 4 credits, spent from a laptop and therefore ABSENT from the "
            "api_credits ledger -- see scripts/capture_nfl_odds_fixture.py."
        ),
        "params": {"regions": REGIONS, "markets": MARKETS, "oddsFormat": ODDS_FORMAT},
        "credit_headers": headers,
        "events": events,
    }

    serialised = json.dumps(artefact, indent=1, sort_keys=True)
    assert_no_credential(serialised, api_key, what=str(FIXTURE))
    FIXTURE.write_text(serialised, encoding="utf-8")

    books = sorted({b["key"] for e in events for b in e.get("bookmakers", [])})
    market_keys = sorted(
        {m["key"] for e in events for b in e.get("bookmakers", []) for m in b.get("markets", [])}
    )
    print(f"\nWROTE {FIXTURE}")
    print(f"  events    {len(events)}")
    print(f"  books     {len(books)}: {', '.join(books)}")
    print(f"  markets   {market_keys}")
    print(f"  credits   {headers}")
    print(
        f"\nLEDGER DRIFT: {EXPECTED_COST} credits were spent that api_credits "
        "will never show. Write it into the measurement doc."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
