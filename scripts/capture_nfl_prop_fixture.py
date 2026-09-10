"""Capture the four NFL player-prop series -- the shape discovery has never seen.

**Why this exists as its own capture.** `tests/fixtures/events_mlb_props_nested.json`
pinned the MLB prop ladder in August. Every claim this repo makes about an *NFL*
prop -- that it has a player, a rung, a strike, an occurrence time -- was, until
this file existed, made against a payload nobody had read. `tasks/NEXT.md` open
item 6 asked for exactly one unauthenticated `/events` pull, capture only, and
this is it.

THE FOUR QUESTIONS THIS CAPTURE EXISTS TO ANSWER
------------------------------------------------
1. **Does the MLB subtitle grammar hold?** `backend/kalshi/props.py::SUBTITLE`
   reads `"Clay Holmes: 4+"`. If NFL spells a rung differently, the parser needs
   a second branch and the two grammars must be named separately rather than
   one regex being loosened until both slip through.

2. **Does `floor_strike == threshold - 0.5` hold?** That identity is the whole
   reason the props join needs no arithmetic (see the `props.py` docstring). It
   was measured on 259 of 259 MLB markets. An NFL series that publishes a bare
   integer, or no strike at all, joins to nothing.

3. **`product_metadata.competition` and `competition_scope`** -- the two fields
   `discovery.py` gates every event on. MLB props carry `"Pro Baseball"` and the
   statistic name. One unexpected league string has already cost this repo 48
   events and 726 markets.

4. **Which series carry a strike at all.** `tasks/NEXT.md` recorded that
   FIRSTTD/ANYTD "carry no strike so the props join has nothing to join on".
   That is a claim about a payload, and this capture is what turns it into a
   pinned artefact instead of a remembered sentence.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Nothing about liquidity, fills or edges.** It reads event metadata. Every
  quote in it is a stored quote, and availability is not fillability.
- **Nothing about a slate other than the one it ran on.** A field present on
  today's ladder is not a contract.
- **Nothing about the Odds API side of the join.** Whether a book quotes these
  same players at these same lines is a separate question, and answering it
  costs credits. Nothing here spends any.
- **Nothing about whether an NFL prop belongs on a parlay card.** A recipe is a
  rule Joe chooses (ADR 0071); this only establishes what could be offered.

No credentials. `/events` is a free unauthenticated read, so this costs nothing
and spends no odds credits. Read-only, places no orders, mints no market.

Run:

    .venv\\Scripts\\python.exe scripts\\capture_nfl_prop_fixture.py

Re-capturing outside the NFL season will return no open events, and the
fixture-backed tests will fail loudly rather than silently accept a file that no
longer contains the case it was captured for. That failure is the point: the
fixture is a pinned artefact, not something to refresh on a schedule.
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
OUT = FIXTURES / "events_nfl_props_nested.json"

# Unauthenticated base. Not read from config on purpose: the value of this
# capture is partly that it needs nothing, and a config load would make a
# credential-less contributor unable to reproduce it.
BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"

# Three yardage ladders and two touchdown markets.
#
# **Three yardage series rather than one**, for the same reason the MLB capture
# took two: one series cannot show whether an answer is a property of NFL prop
# ladders or of `KXNFLPASSYDS` specifically. Passing, receiving and rushing are
# quoted at wholly different magnitudes (hundreds, tens, tens), so a rung rule
# that is really a magnitude coincidence shows up as a disagreement.
#
# **Both touchdown series, because they are the negative case.** They are
# expected to carry no `floor_strike`, and a capture that held only the series
# that work would pin the happy path and leave the refusal untested.
SERIES = (
    "KXNFLPASSYDS",
    "KXNFLRECYDS",
    "KXNFLRSHYDS",
    "KXNFLFIRSTTD",
    "KXNFLANYTD",
)

# Events kept per series. A receiving-yards event alone carries 110 markets, so
# the untruncated five-series response runs to several megabytes and every event
# past the second repeats a shape the first two already carry.
#
# **Each stored event is verbatim** -- this truncates the list, it never edits an
# object. The counts under `observed_full_response` describe the whole response
# and the counts under `answers` describe what is stored, so a test can never
# accidentally assert a whole-series number against a truncated file.
KEEP_EVENTS_PER_SERIES = 2


def _fetch(client: httpx.Client, series: str) -> list[dict]:
    """One page of a series' open events, markets nested."""
    response = client.get(
        f"{BASE_URL}/events",
        params={
            "series_ticker": series,
            "status": "open",
            "limit": "200",
            "with_nested_markets": "true",
        },
    )
    response.raise_for_status()
    return response.json().get("events") or []


def _summarise(series: str, events: list[dict], *, label: str) -> dict:
    """Print, and return, the four answers this capture exists for."""
    leagues: collections.Counter = collections.Counter()
    scopes: collections.Counter = collections.Counter()
    strike_types: collections.Counter = collections.Counter()
    markets = 0
    with_occurrence = 0
    with_floor_strike = 0
    # Question 2: does `floor_strike == threshold - 0.5` hold? Counted, never
    # assumed -- and the mismatches are kept so a failure names itself.
    parsed = 0
    identity_holds = 0
    identity_breaks: list[str] = []
    subtitles: list[str] = []

    for event in events:
        metadata = event.get("product_metadata") or {}
        leagues[(metadata.get("competition") or "").strip()] += 1
        scopes[(metadata.get("competition_scope") or "").strip()] += 1
        for market in event.get("markets") or []:
            markets += 1
            strike_types[market.get("strike_type") or ""] += 1
            if market.get("occurrence_datetime"):
                with_occurrence += 1
            floor = market.get("floor_strike")
            if floor is not None:
                with_floor_strike += 1
            subtitle = market.get("yes_sub_title") or ""
            if len(subtitles) < 5:
                subtitles.append(subtitle)
            # Parsed here with the repo's own regex rather than a local copy,
            # so a capture cannot report a grammar the production parser
            # disagrees with.
            from backend.kalshi.props import parse_subtitle

            reading = parse_subtitle(subtitle)
            if reading is None or floor is None:
                continue
            parsed += 1
            if abs(float(floor) - (reading[1] - 0.5)) < 1e-9:
                identity_holds += 1
            elif len(identity_breaks) < 10:
                identity_breaks.append(
                    f"{market.get('ticker')}: {subtitle!r} floor_strike={floor}"
                )

    print(f"\n{series} [{label}]: {len(events)} events, {markets} markets")
    print("  competition:")
    for value, count in leagues.most_common():
        print(f"    {value!r:<28} {count} events")
    print("  competition_scope:")
    for value, count in scopes.most_common():
        print(f"    {value!r:<28} {count} events")
    print("  strike_type:")
    for value, count in strike_types.most_common():
        print(f"    {value!r:<28} {count} markets")
    print(f"  markets with occurrence_datetime  {with_occurrence}/{markets}")
    print(f"  markets with floor_strike         {with_floor_strike}/{markets}")
    print(f"  subtitles parsed by SUBTITLE      {parsed}/{markets}")
    print(f"  floor_strike == threshold - 0.5   {identity_holds}/{parsed}")
    if identity_breaks:
        print("  IDENTITY BREAKS:")
        for line in identity_breaks:
            print(f"    {line}")
    print(f"  example subtitles: {subtitles}")

    return {
        "events": len(events),
        "markets": markets,
        "competition": dict(leagues),
        "competition_scope": dict(scopes),
        "strike_type": dict(strike_types),
        "markets_with_occurrence_datetime": with_occurrence,
        "markets_with_floor_strike": with_floor_strike,
        "subtitles_parsed": parsed,
        "floor_strike_is_threshold_minus_half": identity_holds,
        "identity_breaks": identity_breaks,
        "example_subtitles": subtitles,
    }


def main() -> None:
    captured_at = datetime.now(timezone.utc).isoformat()
    stored: dict[str, list[dict]] = {}
    observed: dict[str, dict] = {}
    answers: dict[str, dict] = {}

    with httpx.Client(timeout=60.0, headers={"user-agent": "kalshi-cockpit-capture/1"}) as client:
        for series in SERIES:
            events = _fetch(client, series)
            observed[series] = _summarise(series, events, label="full response")
            keep = events[:KEEP_EVENTS_PER_SERIES]
            stored[series] = keep
            answers[series] = _summarise(series, keep, label="stored")

    payload = {
        "_comment": (
            "Verbatim Kalshi /events responses for the NFL prop series, "
            "truncated to the first "
            f"{KEEP_EVENTS_PER_SERIES} events per series. Unauthenticated "
            "read; no credentials, no odds credits, no orders. "
            "`observed_full_response` describes the whole response; `answers` "
            "describes only what is stored here."
        ),
        "captured_at": captured_at,
        "source": f"{BASE_URL}/events?with_nested_markets=true&status=open",
        "keep_events_per_series": KEEP_EVENTS_PER_SERIES,
        "observed_full_response": observed,
        "answers": answers,
        "events_by_series": stored,
    }

    OUT.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
    size = OUT.stat().st_size
    print(f"\nwrote {OUT} ({size:,} bytes)")


if __name__ == "__main__":
    main()
