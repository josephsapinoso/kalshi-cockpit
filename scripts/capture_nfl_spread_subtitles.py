"""Capture real `KXNFLSPREAD` events and prove `parse_spread_subtitle` reads them.

**Why this exists.** `kalshi/spreads.py`'s `_KNOWN_UNITS` is `runs?|points?`, and
until this ran, **no NFL spread subtitle had ever been observed by this repo** --
`tests/fixtures/events_sports_nested.json` carries `KXMLBSPREAD`, `KXWNBASPREAD`
and `KXCFLSPREAD` but no NFL one. NFL was inferred safe from the CFL row
("British Columbia Lions wins by over 20.5 points"), which is good evidence and
is not a measurement.

The failure it guards against is **silent zero supply**: an unparsed subtitle
makes `parse_spread_subtitle` return `None`, the runner counts
`dropped_unknown_spread_unit`, and NFL spreads contribute no `fair_prices` rows
and no spread legs to the parlay ladder -- while `ODDS_MARKETS = "h2h,spreads"`
goes on paying the doubled credit for the book side of them.

**Costs nothing.** Kalshi's `/events` is unauthenticated and is not the odds
feed; no Odds API credit is spent and no Kalshi credential is read.

    .venv\\Scripts\\python.exe scripts/capture_nfl_spread_subtitles.py
    .venv\\Scripts\\python.exe scripts/capture_nfl_spread_subtitles.py --write-fixture

What it does NOT establish
--------------------------
- **One capture, one week.** Kalshi could phrase a later week differently. The
  committed fixture pins what was seen, and `_SPREAD_UNIT_SHAPE` is what
  distinguishes a new unit from a broken subtitle if it ever changes.
- **It says nothing about whether the book side carries NFL spreads.** That is
  the Odds API's question and costs credits to ask.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.kalshi.spreads import (  # noqa: E402
    _KNOWN_UNITS,
    parse_spread_subtitle,
)

KALSHI_EVENTS = "https://api.elections.kalshi.com/trade-api/v2/events"
SERIES = "KXNFLSPREAD"
FIXTURE = ROOT / "tests" / "fixtures" / "events_nfl_spread.json"


async def fetch(series: str, limit: int) -> list[dict]:
    """Open spread events with their nested markets. Unauthenticated by design."""
    out: list[dict] = []
    cursor = None
    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            params: dict[str, object] = {
                "series_ticker": series,
                "status": "open",
                "limit": 200,
                "with_nested_markets": "true",
            }
            if cursor:
                params["cursor"] = cursor
            response = await client.get(KALSHI_EVENTS, params=params)
            response.raise_for_status()
            body = response.json()
            batch = body.get("events")
            if batch is None:
                raise KeyError(
                    f"{KALSHI_EVENTS} returned no 'events' key (got "
                    f"{sorted(body)}). Refusing to report zero events as "
                    f"'Kalshi lists no NFL spreads'."
                )
            out.extend(batch)
            cursor = body.get("cursor")
            if not cursor or not batch or len(out) >= limit:
                return out[:limit]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--series", default=SERIES)
    ap.add_argument("--limit", type=int, default=400)
    ap.add_argument(
        "--write-fixture",
        action="store_true",
        help=f"write the verbatim payload to {FIXTURE.relative_to(ROOT)}",
    )
    args = ap.parse_args()

    events = asyncio.run(fetch(args.series, args.limit))
    print(f"{args.series}: {len(events)} open events")
    if not events:
        # An empty list is a real answer and must not read as a pass. Kalshi
        # may simply not have listed the week's spreads yet.
        print(
            "REFUSED: Kalshi lists no open events for this series right now. "
            "That is not evidence the subtitles parse -- re-run closer to "
            "kickoff."
        )
        return 2

    subtitles: list[tuple[str, str]] = []
    for event in events:
        for market in event.get("markets") or []:
            sub = market.get("yes_sub_title") or ""
            if sub:
                subtitles.append((market.get("ticker", "?"), sub))

    print(f"{len(subtitles)} market subtitles\n")
    print(f"_KNOWN_UNITS = {_KNOWN_UNITS!r}\n")

    parsed = 0
    failures: list[tuple[str, str]] = []
    # `parse_spread_subtitle` returns `(team, margin)` and deliberately does not
    # hand back the unit -- the unit's only job is to be in the whitelist. So
    # the unit is read from the subtitle's last word, which is what the grammar
    # matched on, rather than invented from the parse result.
    units: Counter[str] = Counter()
    teams: set[str] = set()
    for ticker, sub in subtitles:
        result = parse_spread_subtitle(sub)
        if result is None:
            failures.append((ticker, sub))
            continue
        parsed += 1
        team, _margin = result
        teams.add(team)
        units[sub.rsplit(" ", 1)[-1]] += 1

    for ticker, sub in subtitles[:5]:
        print(f"  sample  {ticker:34s} {sub!r}")
    print()
    print(f"PARSED   {parsed} of {len(subtitles)}")
    print(f"units    {dict(units)}")
    print(f"teams    {len(teams)} distinct")
    if failures:
        print(f"\nFAILED   {len(failures)}:")
        for ticker, sub in failures[:10]:
            print(f"  {ticker:34s} {sub!r}")

    if args.write_fixture:
        FIXTURE.write_text(
            json.dumps(
                {
                    "captured_note": (
                        "Verbatim /events response for KXNFLSPREAD, captured to "
                        "pin _KNOWN_UNITS against a real NFL spread subtitle. "
                        "Before this, NFL was inferred safe from the CFL row in "
                        "events_sports_nested.json. Unauthenticated endpoint; "
                        "no Odds API credit was spent."
                    ),
                    "series_ticker": args.series,
                    "endpoint": KALSHI_EVENTS,
                    "events": events,
                },
                indent=1,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"\nwrote {FIXTURE.relative_to(ROOT)}")

    return 0 if parsed == len(subtitles) and subtitles else 1


if __name__ == "__main__":
    raise SystemExit(main())
