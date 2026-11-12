"""Capture one open game-total event per in-scope series, and census the rest.

**Why this exists (#418).** `backend/kalshi/totals.py` reads a total's
`yes_sub_title` and the runner binds YES to the book's `Over`. Until this ran
the only totals this repo had ever observed were `KXMLBTOTAL` and
`KXWNBATOTAL` (`tests/fixtures/events_sports_nested.json`), both phrased
`"Over 8.5 runs scored"`. Five more series are in scope and none had been
looked at. Two questions, one capture:

1. Is YES the Over on every one of them? If any series words YES as
   `"Under N"`, every wording downstream is inverted.
2. Does the subtitle grammar cover them? An unparsed subtitle is **silent
   zero supply**: the runner drops the market, no `fair_prices` row is
   written, and `ODDS_MARKETS` goes on paying for the book side.

**Costs nothing.** Kalshi's `/events` is unauthenticated and is not the odds
feed; no Odds API credit is spent and no Kalshi credential is read.

    .venv\\Scripts\\python.exe scripts/capture_total_subtitles.py
    .venv\\Scripts\\python.exe scripts/capture_total_subtitles.py --write-fixture

The fixture keeps ONE event per series, verbatim. The census over every open
event is printed and written into the fixture beside it, as counts.

What it does NOT establish
--------------------------
- **One capture, one day.** Kalshi could phrase a later slate differently.
- **Nothing about a series with no open events at capture time.** `KXMLBTOTAL`
  and `KXWNBATOTAL` are out of season in November; their evidence is the older
  fixture, and this script reports them as not listed, never as passing.
- **Nothing about whether a Kalshi total and a sportsbook total settle on the
  same thing** (overtime, a shortened game). That is the rules text, not the
  subtitle.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from capture_envelope import request_envelope, write_capture  # noqa: E402

from backend.kalshi.totals import (  # noqa: E402
    parse_total_subtitle,
    unrecognised_total_unit,
)

KALSHI_EVENTS = "https://api.elections.kalshi.com/trade-api/v2/events"
FIXTURE = ROOT / "tests" / "fixtures" / "events_totals_by_series.json"

#: One game-total series per league in `discovery.IN_SCOPE_LEAGUES`.
SERIES = (
    "KXMLBTOTAL",
    "KXNFLTOTAL",
    "KXNCAAFTOTAL",
    "KXNBATOTAL",
    "KXWNBATOTAL",
    "KXNHLTOTAL",
    "KXNCAAMBTOTAL",
)

PARAMS = {"status": "open", "limit": 200, "with_nested_markets": "true"}


def _get(series: str, cursor: str | None) -> dict:
    params = {"series_ticker": series, **PARAMS}
    if cursor:
        params["cursor"] = cursor
    done = subprocess.run(
        ["curl", "-s", "-m", "60", f"{KALSHI_EVENTS}?{urlencode(params)}"],
        capture_output=True,
        check=True,
    )
    return json.loads(done.stdout.decode("utf-8"))


def fetch(series: str) -> list[dict]:
    """Every open event of one series, nested markets included.

    `curl`, not `httpx`: on the laptop this runs from, Python's resolver fails
    every hostname while `curl` resolves them. Follows `cursor` to the end, so
    the census counts every open event and not the first page of them.
    """
    out: list[dict] = []
    cursor: str | None = None
    for _page in range(50):
        body = _get(series, cursor)
        events = body.get("events")
        if events is None:
            raise KeyError(
                f"{KALSHI_EVENTS} returned no 'events' key for {series} (got "
                f"{sorted(body)}). Refusing to report that as 'no open totals'."
            )
        out.extend(events)
        cursor = body.get("cursor")
        if not cursor or not events:
            return out
    raise RuntimeError(f"{series}: still paging after 50 pages; census refused.")


_LINE = re.compile(r"\d+(?:\.\d+)?")


def census(events: list[dict]) -> dict:
    """Wire facts over every market of every open event. No market is named.

    Only what Kalshi sent is stored: the subtitle with its number masked, the
    strike type, and whether `floor_strike` is the number in the subtitle. What
    the parser makes of it is printed by `main` and deliberately NOT written,
    because a parser result frozen into a fixture goes stale the day the
    parser changes.
    """
    shapes: Counter[str] = Counter()
    strike_types: Counter[str] = Counter()
    markets = strike_is_the_line = whole_number_strikes = 0
    for event in events:
        for market in event.get("markets") or []:
            markets += 1
            subtitle = (market.get("yes_sub_title") or "").strip()
            shapes[_LINE.sub("N", subtitle, count=1)] += 1
            strike_types[str(market.get("strike_type"))] += 1
            found = _LINE.search(subtitle)
            strike = market.get("floor_strike")
            if found and strike is not None and float(found.group()) == float(strike):
                strike_is_the_line += 1
            if strike is not None and (float(strike) * 2) % 2 != 1:
                whole_number_strikes += 1
    return {
        "open_events": len(events),
        "markets": markets,
        "yes_sub_title_shape": dict(shapes),
        "strike_type": dict(strike_types),
        "floor_strike_equals_subtitle_number": strike_is_the_line,
        "whole_number_strikes": whole_number_strikes,
        "cap_strike_present": sum(
            1
            for event in events
            for market in event.get("markets") or []
            if market.get("cap_strike") is not None
        ),
    }


def parser_reading(events: list[dict]) -> dict:
    """What `kalshi/totals.py` makes of the same markets. Printed, not stored."""
    parsed = 0
    unparsed: Counter[str] = Counter()
    for event in events:
        for market in event.get("markets") or []:
            subtitle = market.get("yes_sub_title")
            if parse_total_subtitle(subtitle) is not None:
                parsed += 1
            else:
                unparsed[unrecognised_total_unit(subtitle) or "(no unit read)"] += 1
    return {"parsed": parsed, "unparsed_by_unit": dict(unparsed)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write-fixture", action="store_true")
    args = ap.parse_args()

    kept: list[dict] = []
    by_series: dict[str, dict] = {}
    for series in SERIES:
        events = fetch(series)
        counts = census(events)
        by_series[series] = counts
        print(f"{series:15s} {json.dumps(counts)}")
        print(f"{'':15s} parser: {json.dumps(parser_reading(events))}")
        if events:
            # The event with the most rungs: the widest look at the grammar.
            kept.append(max(events, key=lambda e: len(e.get("markets") or [])))

    not_listed = [s for s in SERIES if not by_series[s]["open_events"]]
    if not_listed:
        print(f"\nNOT LISTED (no open events, so no evidence): {not_listed}")

    if args.write_fixture:
        write_capture(
            FIXTURE,
            {
                "request": request_envelope(
                    endpoint=KALSHI_EVENTS,
                    params={"series_ticker": list(SERIES), **PARAMS},
                    note=(
                        "One GET per series_ticker. Kept ONE event per series "
                        "(the one with the most markets), verbatim; "
                        "`census` counts every market of every open event "
                        "returned. A series with open_events 0 was asked for "
                        "and had nothing listed, which is not evidence about "
                        "its grammar."
                    ),
                ),
                "endpoint": KALSHI_EVENTS,
                "census": by_series,
                "events": kept,
            },
        )
        print(f"\nwrote {FIXTURE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
