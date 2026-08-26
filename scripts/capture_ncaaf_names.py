"""Capture NCAAF team names from BOTH sides and report what the real linker
cannot match, so the alias file is written from observation.

**Why this exists.** `backend/match/aliases/americanfootball_ncaaf.yaml` does
not exist, so `load_aliases` returns an empty mapping and NCAAF rests entirely
on exact + token-prefix matching. `docs/measurements/2026-08-16-nfl-ncaaf-scope-
and-cost.md` dated that as the first thing to break, ~2026-08-27.

**The file must not be hand-guessed, and this repo has the receipt.**
`backend/kalshi/discovery.py:231-234` records that guessing spellings silently
deleted two whole leagues from the Board -- "Womens Pro Basketball" for
"Pro Basketball (W)", "College Football" for "NCAA Football". A probe run
before this script guessed fourteen pairs and got the shape of the failures
wrong three times in five: the `X St.` -> `X State` family resolves fine by
token-prefix, while `Miami (FL)` (the parens leave a stray `fl` token),
`Hawaii` spelled with an okina (the apostrophe normalises to a space) and
`Central Connecticut St.` (the book name carries no "State" at all) do not, and
none of those three was predicted.

**It calls `link_event`, it does not reimplement it.** The first version of
this script matched names without a commence-time window and reported 163
"alias candidates" -- almost all of them a Kalshi fixture paired against a
DIFFERENT game that happened to share one team name ("Towson vs Maine" against
"Appalachian State vs Maine Black Bears"). A confident number produced by an
instrument that skipped a step production performs is worse than no number.
Bucketing on `MatchResult.reason` also means every category here is a category
the runner would actually record.

Cost
----
**Zero odds credits, and it is measured rather than assumed.** Kalshi's
`/events` is free and public (ADR 0071 s2.4). The Odds API's
`/v4/sports/{key}/events` returns fixtures without odds; this reads
`x-requests-last` back off the response and prints it, because a documented
cost is not a measured one. `/odds` would bill 4 credits under the deployed
`ODDS_MARKETS x ODDS_REGIONS`, and no price is needed here.

What this does not establish
----------------------------
- **That a matched name means a priceable game.** Kalshi lists Division II
  fixtures the sportsbook feed does not carry. A Kalshi event with no fixture
  in the window is OUT OF SCOPE, not unmatched, and the two are counted apart
  -- pooling them is how "NCAAF is broken" gets reported for a game nobody
  prices.
- **That the alias file is complete.** One capture is one slate. A team playing
  next week is not in it, and the file will need re-deriving.
- **That an alias would fix any given row.** A pair the resolver refuses may be
  two genuinely different fixtures inside a four-hour window. The printed
  reason carries the near misses so a human can tell.
- **Anything about spreads or totals.** Names only.
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import json
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx                                                    # noqa: E402
from dotenv import load_dotenv                                  # noqa: E402

from backend.kalshi.discovery import (                          # noqa: E402
    event_commence_ms,
    parse_ms,
)
from backend.logging_setup import configure_logging             # noqa: E402
from backend.match.linker import (                              # noqa: E402
    MatchCandidate,
    TeamAliases,
    _matches,
    link_event,
    load_aliases,
)

logger = logging.getLogger("capture_ncaaf_names")

KALSHI_EVENTS = "https://api.elections.kalshi.com/trade-api/v2/events"
ODDS_EVENTS = "https://api.the-odds-api.com/v4/sports/americanfootball_ncaaf/events"
SERIES = "KXNCAAFGAME"
SPORT_KEY = "americanfootball_ncaaf"


async def kalshi_fixtures(limit: int) -> list[dict]:
    """Open NCAAF game events with their markets. Unauthenticated by design."""
    out: list[dict] = []
    cursor = None
    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            params: dict[str, object] = {
                "series_ticker": SERIES,
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
                    f"{sorted(body)}). Refusing to report zero fixtures as "
                    f"'no college football this week'."
                )
            out.extend(batch)
            cursor = body.get("cursor")
            if not cursor or not batch or len(out) >= limit:
                return out[:limit]


async def odds_fixtures(api_key: str) -> tuple[list[dict], dict[str, str]]:
    """Upcoming NCAAF fixtures as the books name them, plus the credit headers."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(ODDS_EVENTS, params={"apiKey": api_key})
        headers = {
            key: response.headers.get(key, "")
            for key in ("x-requests-used", "x-requests-remaining", "x-requests-last")
        }
        if response.status_code >= 400:
            # Never echo the URL: the key rides in the query string, which is
            # the leak `tasks/lessons.md` records for httpx logging.
            raise RuntimeError(
                f"The Odds API events read failed: HTTP {response.status_code}. "
                f"Body starts: {response.text[:160]!r}"
            )
        return response.json(), headers


def kalshi_sides(event: dict) -> list[str]:
    """The two team names Kalshi shows, from `yes_sub_title` across markets.

    The same source `DiscoveredEvent.teams` uses: `no_sub_title` repeats the
    YES side, so it is not a second team.
    """
    seen: list[str] = []
    for market in event.get("markets") or []:
        name = (market.get("yes_sub_title") or "").strip()
        if name and name not in seen:
            seen.append(name)
    return seen


def to_candidate(book: dict) -> MatchCandidate | None:
    """A book fixture in the shape `link_event` matches against."""
    commence = parse_ms(book.get("commence_time"))
    if commence is None:
        return None
    return MatchCandidate(
        odds_event_id=book.get("id", "") or "",
        commence_ms=commence,
        home_team=book.get("home_team", "") or "",
        away_team=book.get("away_team", "") or "",
    )


def sides_known_to_the_books(
    sides: list[str], books: list[dict], aliases: TeamAliases
) -> int:
    """How many of these two teams appear ANYWHERE in the book feed.

    **This is the discriminator `link_event`'s reason cannot supply, and college
    football is why.** The commence window is four hours; on a Saturday dozens
    of college games kick off inside four hours of each other, so
    "no fixture in the window" almost never fires and its bucket absorbs
    nothing. Everything the books do not carry lands in `no team-pair
    bijection` instead, next to the genuine spelling problems.

    Asking whether the TEAM is known anywhere separates them, because a
    Division II school the feed has never heard of matches nothing at any
    kickoff time. Deliberately a loose, league-wide check -- it is answering
    "is this team in scope", not "is this the same game", and using it as a
    matcher is the mistake the first version of this script made.
    """
    universe = [
        name
        for book in books
        for name in (book.get("home_team", ""), book.get("away_team", ""))
        if name
    ]
    return sum(
        1 for side in sides if any(_matches(side, name, aliases) for name in universe)
    )


def best_candidates(
    sides: list[str],
    commence_ms: int,
    candidates: list[MatchCandidate],
    aliases: TeamAliases,
    tolerance_ms: int = 4 * 3600 * 1000,
) -> list[MatchCandidate]:
    """In-window book fixtures where at least one side already resolves.

    **`link_event`'s own reason is not usable here, and that is a property of
    college football rather than a defect in it.** It samples the first three
    fixtures inside the commence window; with a handful of concurrent MLB games
    those three ARE the near misses. On a Saturday college slate the window
    holds dozens, so the sample is three unrelated games -- observed: the
    refusal for `Stanford vs Hawai'i` listed `North Carolina @ TCU`,
    `San Jose State @ USC` and `NC State @ Virginia`, while
    `Hawaii Rainbow Warriors @ Stanford Cardinal` sat in the same feed and
    turned up in a different row's sample.

    Ranking by how many sides already match puts the real counterpart first, so
    the missing spelling can be READ rather than recalled.
    """
    scored = []
    for candidate in candidates:
        if abs(candidate.commence_ms - commence_ms) > tolerance_ms:
            continue
        hits = sum(
            1
            for side in sides
            if any(
                _matches(side, team, aliases)
                for team in (candidate.home_team, candidate.away_team)
            )
        )
        if hits:
            scored.append((hits, candidate))
    scored.sort(key=lambda pair: -pair[0])
    return [candidate for _, candidate in scored[:2]]


def bucket(reason: str | None, known: int) -> str:
    """Which of `link_event`'s refusals this is, in one word."""
    if reason is None:
        return "linked"
    if "within the commence-time window" in reason:
        return "no_fixture_in_window"
    if "no team-pair bijection" in reason:
        # No in-window fixture shares even one side: the books do not carry
        # this game. That is scope, not spelling.
        return "not_carried" if known == 0 else "needs_alias"
    if reason.startswith("ambiguous"):
        return "ambiguous"
    if reason.startswith("expected 2 sides"):
        return "not_two_sided"
    return "other"


def classify(kalshi: list[dict], books: list[dict], aliases: TeamAliases) -> dict:
    """Run every Kalshi fixture through the real linker and bucket the answers."""
    candidates = [c for c in (to_candidate(b) for b in books) if c is not None]
    counts: collections.Counter[str] = collections.Counter()
    needs_alias: list[tuple[str, str]] = []
    sides_by_ticker: dict[str, str] = {}
    no_commence = 0

    for event in kalshi:
        commence = event_commence_ms(event)
        if commence is None:
            no_commence += 1
            continue
        sides = kalshi_sides(event)
        result = link_event(
            kalshi_event_ticker=event.get("event_ticker", ""),
            kalshi_teams=sides,
            kalshi_commence_ms=commence,
            candidates=candidates,
            aliases=aliases,
        )
        # **Bucket on the IN-WINDOW candidate, not on the league-wide check.**
        # `sides_known_to_the_books` is loose by design and over-counts: it will
        # match `Indiana St.` against some other Indiana anywhere in the feed,
        # at any kickoff. What actually separates "the books do not carry this
        # game" from "the books carry it under another spelling" is whether a
        # fixture AT THIS KICKOFF shares a side.
        near = (
            []
            if result.reason is None
            else best_candidates(sides, commence, candidates, aliases)
        )
        key = bucket(result.reason, len(near))
        counts[key] += 1
        if key == "needs_alias":
            shown = "; ".join(f"{c.away_team} @ {c.home_team}" for c in near)
            ticker = event.get("event_ticker", "")
            sides_by_ticker[ticker] = " vs ".join(sides)
            needs_alias.append((f"{ticker} [{key}]", shown))

    return {
        "counts": counts,
        "needs_alias": needs_alias,
        "sides": sides_by_ticker,
        "no_commence": no_commence,
        "candidates": len(candidates),
    }


def report(result: dict, *, show: int) -> None:
    counts = result["counts"]
    total = sum(counts.values())
    print(f"book fixtures usable ....... {result['candidates']}")
    print(f"kalshi events classified ... {total}")
    if result["no_commence"]:
        print(
            f"  (+{result['no_commence']} with no occurrence_datetime -- "
            f"cannot be matched at all, counted apart)"
        )
    print()
    for key in (
        "linked",
        "needs_alias",
        "not_carried",
        "no_fixture_in_window",
        "ambiguous",
        "not_two_sided",
        "other",
    ):
        note = {
            "needs_alias": "<- ALIAS CANDIDATES (a fixture at this kickoff shares a side)",
            "not_carried": "out of scope: no in-window fixture shares either team",
            "no_fixture_in_window": "no book fixture at this kickoff at all",
            "ambiguous": "two fixtures share a team pair; refused on purpose",
        }.get(key, "")
        print(f"  {key:<22} {counts.get(key, 0):>4}  {note}")

    if result["needs_alias"]:
        print()
        print("Refused on names, with the best in-window candidate beside each.")
        print("Read BOTH spellings off this list; supply neither half from memory:")
        for ticker, near in result["needs_alias"][:show]:
            print(f"  {ticker}")
            print(f"    kalshi: {result['sides'].get(ticker.split()[0], '')}")
            print(f"    book:   {near}")
        remaining = len(result["needs_alias"]) - show
        if remaining > 0:
            print(f"  ... and {remaining} more (not shown, not dropped)")


def main() -> int:
    configure_logging()
    load_dotenv(ROOT / ".env")

    parser = argparse.ArgumentParser(description="Capture NCAAF team names.")
    parser.add_argument("--limit", type=int, default=400)
    parser.add_argument("--show", type=int, default=25)
    parser.add_argument(
        "--out-dir",
        default=str(ROOT / "tests" / "fixtures"),
        help="where the two captured payloads are written",
    )
    parser.add_argument(
        "--no-write", action="store_true", help="report only; write no fixtures"
    )
    parser.add_argument(
        "--with-aliases",
        action="store_true",
        help=(
            "classify WITH the alias file on disk instead of without it. "
            "Run both ways: the difference is what the file bought."
        ),
    )
    args = parser.parse_args()

    api_key = os.environ.get("ODDS_API_KEY", "").strip()
    if not api_key:
        logger.error("ODDS_API_KEY is not set; cannot read the book side.")
        return 2

    kalshi = asyncio.run(kalshi_fixtures(args.limit))
    books, headers = asyncio.run(odds_fixtures(api_key))

    aliases = (
        load_aliases(SPORT_KEY)
        if args.with_aliases
        else TeamAliases(sport_key=SPORT_KEY)
    )

    print(f"Kalshi {SERIES}: {len(kalshi)} open events")
    print(f"Odds API {SPORT_KEY}: {len(books)} upcoming fixtures")
    print(f"credit headers: {headers}")
    print(f"aliases: {'file on disk' if args.with_aliases else 'NONE (baseline)'}")
    print()

    report(classify(kalshi, books, aliases), show=args.show)

    if not args.no_write:
        out = Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        # **Reduced to the fields the matcher reads, not the whole payload.**
        # Two reasons and both matter. The full Kalshi capture is 2.18 MB of
        # market objects -- measured, not estimated -- and a NAME test needs no
        # price, size or book field. And this repo is public while Kalshi's
        # Developer Agreement s3.1 limits redistributing API-derived data, so
        # the smallest fixture that still pins the behaviour is the right one.
        (out / "ncaaf_names_kalshi.json").write_text(
            json.dumps(
                {
                    "captured_note": (
                        "Reduced capture: team names and kickoff only, for "
                        "alias resolution. No prices, no market payloads."
                    ),
                    "events": [
                        {
                            "event_ticker": event.get("event_ticker"),
                            "commence_ms": event_commence_ms(event),
                            "teams": kalshi_sides(event),
                        }
                        for event in kalshi
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        (out / "ncaaf_names_books.json").write_text(
            json.dumps(
                {
                    "captured_note": (
                        "Reduced capture: fixture id, kickoff and the two team "
                        "names as the books spell them. No odds."
                    ),
                    "fixtures": [
                        {
                            "id": book.get("id"),
                            "commence_ms": parse_ms(book.get("commence_time")),
                            "home_team": book.get("home_team"),
                            "away_team": book.get("away_team"),
                        }
                        for book in books
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"wrote {out / 'ncaaf_names_kalshi.json'}")
        print(f"wrote {out / 'ncaaf_names_books.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
