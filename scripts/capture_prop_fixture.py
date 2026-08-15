"""Capture two MLB player-prop series -- the shape discovery has never seen.

**Why this exists as its own capture.** `tests/fixtures/events_sports_nested.json`
is a walk of the sports universe taken on 2026-08-06. It contains twelve series
and **not one of them is a prop ladder**. So every classifier decision this repo
makes about `KXMLBKS`, `KXMLBTB`, `KXMLBHIT`, `KXMLBHR` and `KXMLBRBI` is
currently made against a payload nobody has looked at, which is precisely the
failure `capture_preseason_fixture.py` was written for one league string away:
a fixture-based test protects against the API changing, not against misreading
it on day one.

THE THREE QUESTIONS THIS CAPTURE EXISTS TO ANSWER
-------------------------------------------------
`backend/kalshi/discovery.py` gates every event on three fields, and for a prop
series the value of all three is unknown. Slice 2 of the props build cannot be
designed until they are read from a real payload rather than guessed:

1. **`product_metadata.competition`** -- decides `sport_key` via
   `IN_SCOPE_LEAGUES` (`discovery.py:225-232`). If Kalshi says anything other
   than `"Pro Baseball"`, props have no sportsbook mapping and the league table
   needs an entry. This repo has already lost 48 events and 726 markets to
   exactly one unexpected league string.

2. **`product_metadata.competition_scope`** -- decides `is_game_level`
   (`discovery.py:380-404`). A value inside `FIXTURE_SCOPES` and props flow
   through the existing gate; a value inside `EXCLUDED_SCOPES` and they are
   being deliberately dropped today; an **unrecognised** value and they are
   dropped silently-but-counted, which is the state we suspect.

3. **`occurrence_datetime` on the nested markets** -- `event_commence_ms`
   (`discovery.py:432-447`) returns `None` without it and `discover_from_events`
   then rejects the whole event (`discovery.py:852`). A prop ladder that
   carries no occurrence time cannot be matched to a fixture at all, which would
   change slice 3 from "link by ticker segment" to "link by nothing".

**Two series, not one, and not five.** One series cannot show whether an answer
is a property of prop ladders or of `KXMLBKS` specifically. Five would quintuple
the fixture for no extra discriminating power -- the second series is what makes
a shared answer a *pattern* rather than a *sample*. `KXMLBTB` is chosen as the
second because it is a batter market where `KXMLBKS` is a pitcher market, so a
per-role quirk would show up as a disagreement rather than hide as a constant.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Nothing about liquidity, fills or edges.** It reads event metadata. Every
  quote in it is a stored quote, and `tasks/NEXT.md` records that availability
  is not fillability.
- **Nothing about a slate other than the one it ran on.** A field present on
  today's ladder is not a contract.
- **Nothing about the other three prop series.** `KXMLBHIT`, `KXMLBHR` and
  `KXMLBRBI` are asserted nowhere by this fixture, and a test that generalises
  to them is claiming more than the artefact carries.

No credentials. `/events` is a free unauthenticated read, so this costs nothing
and spends no odds credits. Read-only, places no orders.

Run:

    .venv\\Scripts\\python.exe scripts\\capture_prop_fixture.py

Re-capturing outside the MLB season will return no open events, and
`tests/test_discovery.py` will fail loudly rather than silently accept a fixture
that no longer contains the case it was captured for. That failure is the point:
the fixture is a pinned artefact, not something to refresh on a schedule.
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
OUT = FIXTURES / "events_mlb_props_nested.json"

# Unauthenticated base. Not read from config on purpose: the value of this
# capture is partly that it needs nothing, and a config load would make a
# credential-less contributor unable to reproduce it.
BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"

# A pitcher market and a batter market. See the docstring for why it is exactly
# these two.
SERIES = ("KXMLBKS", "KXMLBTB")

# Events kept per series. The full response is ~1.9 MB, three times the largest
# fixture in the repo, and every event past the fourth repeats a shape the first
# four already carry: one game, one ladder per player, `N+` subtitles.
#
# **Each stored event is verbatim** -- this truncates the list, it never edits an
# object. The counts under `observed_full_response` describe the whole response
# and the counts under `answers` describe what is stored, so a test can never
# accidentally assert a whole-series number against a truncated file.
KEEP_EVENTS_PER_SERIES = 4


def _fetch(client: httpx.Client, series: str) -> tuple[list[dict], str]:
    """One page of a series' open events, markets nested. Returns (events, cursor)."""
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
    payload = response.json()
    return (payload.get("events") or [], payload.get("cursor") or "")


def _summarise(series: str, events: list[dict], *, label: str) -> dict:
    """Print, and return, the three answers this capture exists for."""
    leagues: collections.Counter = collections.Counter()
    scopes: collections.Counter = collections.Counter()
    markets = 0
    markets_with_occurrence = 0
    subtitles: list[str] = []

    for event in events:
        metadata = event.get("product_metadata") or {}
        leagues[(metadata.get("competition") or "").strip()] += 1
        scopes[(metadata.get("competition_scope") or "").strip()] += 1
        for market in event.get("markets") or []:
            markets += 1
            if market.get("occurrence_datetime"):
                markets_with_occurrence += 1
            if len(subtitles) < 5:
                subtitles.append(market.get("yes_sub_title") or "")

    print(f"\n{series} [{label}]: {len(events)} events, {markets} markets")
    print("  competition:")
    for value, count in leagues.most_common():
        print(f"    {value!r:<28} {count} events")
    print("  competition_scope:")
    for value, count in scopes.most_common():
        print(f"    {value!r:<28} {count} events")
    print(
        f"  occurrence_datetime: {markets_with_occurrence} of {markets} markets"
    )
    print("  sample yes_sub_title:")
    for subtitle in subtitles:
        print(f"    {subtitle!r}")

    return {
        "series_ticker": series,
        "events": len(events),
        "markets": markets,
        "competition": dict(leagues),
        "competition_scope": dict(scopes),
        "markets_with_occurrence_datetime": markets_with_occurrence,
    }


def capture() -> int:
    captured: dict[str, list[dict]] = {}
    answers: list[dict] = []
    observed_full: list[dict] = []

    with httpx.Client(timeout=30.0) as client:
        for series in SERIES:
            events, cursor = _fetch(client, series)
            if cursor:
                # One page held each series on capture day. If that stops being
                # true the capture is a *partial* series, which would look like
                # a shrinking ladder rather than a truncated read -- so say so
                # instead of writing it.
                print(
                    f"FAIL  {series} no longer fits one page (cursor={cursor!r}). "
                    f"Nothing written; paginate before re-capturing."
                )
                return 1
            observed_full.append(
                _summarise(series, events, label="full response")
            )
            kept = events[:KEEP_EVENTS_PER_SERIES]
            captured[series] = kept
            answers.append(_summarise(series, kept, label="stored"))

    empty = [s for s, events in captured.items() if not events]
    if empty:
        # Refuse rather than write. An empty ladder is indistinguishable from a
        # series Kalshi retired, and a fixture of zero events would make every
        # assertion built on it vacuously true -- the exact shape of a guard
        # that cannot fail.
        print(
            f"\nFAIL  no open events for {', '.join(empty)}. Nothing written. "
            f"MLB prop ladders are listed on game days during the season; "
            f"outside that window this capture cannot contain the case it "
            f"exists for, and an empty fixture would make its tests pass "
            f"vacuously."
        )
        return 1

    document = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "endpoint": (
            "GET /events?series_ticker={series}&status=open"
            "&with_nested_markets=true (unauthenticated)"
        ),
        "note": (
            "Verbatim API responses, one per series. Captured because "
            "events_sports_nested.json contains no prop ladder, so "
            "discovery's league gate, scope gate and commence-time gate were "
            "all untested against the series the props build is about to "
            "admit. A pitcher market (KXMLBKS) and a batter market (KXMLBTB) "
            "so a per-role quirk shows up as a disagreement rather than "
            "hiding as a constant. Asserts nothing about KXMLBHIT, KXMLBHR or "
            "KXMLBRBI."
        ),
        "truncation": (
            f"Each series' event list is truncated to its first "
            f"{KEEP_EVENTS_PER_SERIES} events; the full response is ~1.9 MB. "
            f"Every stored event object is VERBATIM -- the list is cut, no "
            f"object is edited. `answers` counts what is stored; "
            f"`observed_full_response` counts what the API returned. Assert "
            f"against `answers`."
        ),
        "series": list(SERIES),
        "answers": answers,
        "observed_full_response": observed_full,
        "events_by_series": captured,
    }
    OUT.write_text(json.dumps(document, indent=2), encoding="utf-8")
    print(
        f"\nwrote {OUT.relative_to(OUT.parents[2])} "
        f"({OUT.stat().st_size / 1024:.0f} KB)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(capture())
