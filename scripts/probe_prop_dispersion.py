"""Does Kalshi disagree with a multi-book consensus on MLB player props?

WHY THIS EXISTS
---------------
ADR 0021 §7.2 is the reason, and it says it better than a summary would:

    "We have been testing Kalshi against the only references plausibly as sharp
    as Kalshi. ... A comparison between two sharp prices returns nothing by
    construction, and 'returns nothing' is precisely what it returned."

The deployed runner prices **two** of Kalshi's 3,405 sports series --
`KXMLBGAME` and `KXWNBAGAME`, game moneylines, the most bot-contested markets on
the venue -- against `betfair_ex_eu` + `matchbook` (+/- `pinnacle`). It surfaced
zero actionable rows, and §7.2 records that this may be a property of the
instrument rather than of the venue.

This probe changes the target and the reference set at once:

  - **Target:** player-prop ladders (`KXMLBKS`, `KXMLBTB`, `KXMLBHIT`,
    `KXMLBHR`, `KXMLBRBI`). Thinner books, fewer bots.
  - **Reference:** whatever offers props, which in practice is
    DraftKings, FanDuel, BetMGM, BetRivers, Bovada, BetOnline, Fanatics --
    **soft books, not exchanges.** Pinnacle and Betfair barely quote props.

**That inversion is the whole experiment, and it is also its main hazard.** On
game lines the sharp consensus is the better estimate and Kalshi may be sharper
still. On props there is no sharp reference to be had, so "fair" here is the
devigged average of soft books. Where Kalshi disagrees with that average, EITHER
Kalshi is mispriced OR Kalshi is right and the books are wrong. **This probe
cannot tell those apart.** It measures dispersion. Only CLV against Kalshi's own
close can say which side was right, and that is the follow-up, not this.

WHAT IT DOES NOT ESTABLISH
--------------------------
1. **Not an edge.** A gap between Kalshi and a soft-book consensus is a gap. The
   project's rule 3 -- validate against Kalshi's own closing line -- is
   untouched by anything printed here.
2. **One slate, one pull, one instant.** No horizon, no repeat, no per-day
   breakdown. A number from a single sweep is a fact about that sweep.
3. **Nothing about fills.** Displayed size is displayed size; §0.4e of the fee
   registration records that no quote separates real resting size from a maker
   who pulls.
4. **The fee is `settlement_fee` at the DEPLOYED coefficient (0.070).** ADR 0028
   measured 0.035 on baseball but did not adopt it, because the record spans
   four days. So every net edge below is understated by up to a factor of two on
   the fee component, deliberately. The `net_at_k035` column prices the
   alternative so the decision is visible rather than assumed.
5. **Method spread is printed beside every edge and must be read with it.**
   CLAUDE.md: the devig-method spread alone (1-2 points) exceeds the fee
   advantage being hunted. An edge smaller than its own method spread is a
   statement about method choice.

MATCHING
--------
Keyed on **(player name, threshold)** across the whole slate, deliberately not on
team or event. Kalshi encodes `"Clay Holmes: 4+"`; the books quote
`description="Clay Holmes", point=3.5`. `N+` is exactly `Over N-0.5`, so the
threshold is `point + 0.5` and must be integral. Player names are unique within
an MLB slate, which removes the team-abbreviation mapping entirely -- and a
name colliding across two games is **reported, never silently resolved**.

Unmatched entries on both sides are counted and printed. A matcher that reports
only its hits looks identical whether it linked forty markets or four.

COST
----
One `/events` call plus one `/events/{id}/odds` per game per sweep. The odds
call bills **one credit per market key**, so five prop markets over a 14-game
slate is ~70 credits. Read-only; places nothing.

    .venv\\Scripts\\python.exe scripts\\probe_prop_dispersion.py
    .venv\\Scripts\\python.exe scripts\\probe_prop_dispersion.py --json out.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import OddsConfig  # noqa: E402
from backend.core.devig import DevigError, consensus_devig  # noqa: E402
from backend.core.fees import settlement_fee  # noqa: E402
from backend.core.prices import dollars_to_tenths  # noqa: E402
from backend.logging_setup import configure_logging  # noqa: E402

ODDS_BASE = "https://api.the-odds-api.com/v4"
KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"

#: Kalshi prop series -> the Odds API market key that quotes the same thing.
#:
#: **The `_alternate` keys are why coverage is not 18%.** A book quotes one
#: primary line per player (`Over 3.5`), while Kalshi prices the whole ladder
#: (`2+` through `8+`). Matching primaries alone therefore compares one rung in
#: seven and throws the rest away -- measured at 48 of 263 Kalshi markets on the
#: 2026-08-14 slate. The `_alternate` feeds quote 1.5 through 9.5 two-sided,
#: which is the same ladder, and cost one extra credit per market per event.
PROP_MARKETS = {
    "KXMLBKS": "pitcher_strikeouts",
    "KXMLBTB": "batter_total_bases",
    "KXMLBHIT": "batter_hits",
    "KXMLBHR": "batter_home_runs",
    "KXMLBRBI": "batter_rbis",
}

#: Requested alongside the primaries and folded onto the same Kalshi series.
ALTERNATE_SUFFIX = "_alternate"


def base_market(key: str) -> str:
    """`pitcher_strikeouts_alternate` -> `pitcher_strikeouts`.

    Primary and alternate feeds quote the same quantity at different lines, so
    they must land in the same bucket or a player would appear twice with two
    different "consensuses" built from disjoint book sets.
    """
    return key[: -len(ALTERNATE_SUFFIX)] if key.endswith(ALTERNATE_SUFFIX) else key

#: `"Clay Holmes: 4+"` -> `("Clay Holmes", 4)`.
SUBTITLE = re.compile(r"^(?P<player>.+?):\s*(?P<threshold>\d+)\+\s*$")


def norm(name: str) -> str:
    """Casefold and strip punctuation, so `J.T. Realmuto` matches `JT Realmuto`."""
    return re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()


def _get_with_key(client: httpx.Client, url: str, params: dict) -> httpx.Response:
    """GET a URL whose query string carries the API key, without letting that
    URL reach the terminal. `raise_for_status()` embeds the full request URL —
    apiKey included — in its message, and an escaping httpx exception's
    traceback bypasses every `configure_logging()` filter (observed 2026-08-20
    21:21Z: a 401 printed the key into the transcript). Fail with the status
    or the exception class alone."""
    try:
        response = client.get(url, params=params)
    except httpx.HTTPError as exc:
        raise SystemExit(
            f"odds request failed: {type(exc).__name__} "
            f"(URL withheld because it carries the API key)"
        ) from None
    if response.status_code != 200:
        raise SystemExit(
            f"odds request failed: HTTP {response.status_code} "
            f"(no credits spent on 4xx; URL withheld because it carries "
            f"the API key)"
        )
    return response


def fetch_book_props(client: httpx.Client, api_key: str) -> tuple[dict, dict]:
    """`{(player, threshold, market): {book: (over_odds, under_odds)}}` and counters."""
    events = _get_with_key(
        client, f"{ODDS_BASE}/sports/baseball_mlb/events", params={"apiKey": api_key}
    ).json()
    counts = {"events": len(events), "credits_used": 0, "non_integral_lines": 0}
    quotes: dict = defaultdict(lambda: defaultdict(dict))

    for event in events:
        response = _get_with_key(
            client,
            f"{ODDS_BASE}/sports/baseball_mlb/events/{event['id']}/odds",
            params={
                "apiKey": api_key,
                "regions": "us",
                "markets": ",".join(sorted(
                    set(PROP_MARKETS.values())
                    | {v + ALTERNATE_SUFFIX for v in PROP_MARKETS.values()}
                )),
                "oddsFormat": "decimal",
            },
        )
        counts["credits_used"] += int(response.headers.get("x-requests-last") or 0)
        for book in response.json().get("bookmakers", []):
            for market in book.get("markets", []):
                for outcome in market.get("outcomes", []):
                    point = outcome.get("point")
                    player = outcome.get("description")
                    if point is None or not player:
                        continue
                    threshold = point + 0.5
                    if threshold != int(threshold):
                        # A whole-number line (`Over 4`) pushes on exactly 4 and
                        # has no `N+` equivalent. Counted, never coerced.
                        counts["non_integral_lines"] += 1
                        continue
                    key = (norm(player), int(threshold), base_market(market["key"]))
                    # A book quoting the same line on both its primary and its
                    # alternate feed would otherwise overwrite itself silently.
                    # Last write wins and they agree; the count is what matters.
                    quotes[key][book["key"]][outcome["name"]] = outcome["price"]
    return quotes, counts


def fetch_kalshi_props(client: httpx.Client) -> tuple[dict, dict]:
    """`{(player, threshold, market): row}` for every open prop market."""
    ladders: dict = {}
    counts = {"kalshi_markets": 0, "unparsed_subtitles": 0, "collisions": 0}

    for series, market_key in PROP_MARKETS.items():
        events = client.get(
            f"{KALSHI_BASE}/events",
            params={"series_ticker": series, "status": "open", "limit": 200},
        ).json().get("events", [])
        for event in events:
            markets = client.get(
                f"{KALSHI_BASE}/markets",
                params={"event_ticker": event["event_ticker"], "limit": 200},
            ).json().get("markets", [])
            for market in markets:
                counts["kalshi_markets"] += 1
                matched = SUBTITLE.match(market.get("yes_sub_title") or "")
                if not matched:
                    counts["unparsed_subtitles"] += 1
                    continue
                key = (
                    norm(matched.group("player")),
                    int(matched.group("threshold")),
                    market_key,
                )
                if key in ladders:
                    counts["collisions"] += 1
                    continue
                ladders[key] = {
                    "ticker": market["ticker"],
                    "player": matched.group("player"),
                    "yes_ask_tenths": dollars_to_tenths(market.get("yes_ask_dollars")),
                    "yes_bid_tenths": dollars_to_tenths(market.get("yes_bid_dollars")),
                    "ask_size": float(market.get("yes_ask_size_fp") or 0),
                    "bid_size": float(market.get("yes_bid_size_fp") or 0),
                    "grid": market.get("price_level_structure"),
                }
    return ladders, counts


def compare(book_quotes: dict, kalshi: dict) -> tuple[list, dict]:
    rows: list[dict] = []
    counts = {
        "matched": 0,
        "book_only": 0,
        "kalshi_only": 0,
        "one_sided_book": 0,
        "devig_errors": 0,
        "unpriced_kalshi": 0,
    }

    for key, by_book in book_quotes.items():
        if key not in kalshi:
            counts["book_only"] += 1
            continue
        two_sided = {
            book: [sides["Over"], sides["Under"]]
            for book, sides in by_book.items()
            if "Over" in sides and "Under" in sides
        }
        if not two_sided:
            counts["one_sided_book"] += 1
            continue
        try:
            result, meta = consensus_devig(["Over", "Under"], two_sided)
        except DevigError:
            counts["devig_errors"] += 1
            continue

        market = kalshi[key]
        counts["matched"] += 1

        # `N+` is `Over N-0.5`; NO on `N+` is `Under`. The NO ask is the
        # complement of the YES bid -- the derived-ask identity, never the mid.
        for side, fair, ask_tenths, size in (
            ("yes", result.conservative_probability("Over"),
             market["yes_ask_tenths"], market["ask_size"]),
            ("no", result.conservative_probability("Under"),
             None if market["yes_bid_tenths"] is None
             else 1000 - market["yes_bid_tenths"], market["bid_size"]),
        ):
            if ask_tenths is None or not (0 < ask_tenths < 1000):
                counts["unpriced_kalshi"] += 1
                continue
            gross = fair * 1000.0 - ask_tenths
            fee = settlement_fee(ask_tenths, 1, False) * 1000.0
            rows.append({
                "ticker": market["ticker"],
                "player": market["player"],
                "threshold": key[1],
                "market": key[2],
                "side": side,
                "ask_tenths": ask_tenths,
                "fair_probability": fair,
                "gross_tenths": gross,
                "fee_tenths": fee,
                "net_tenths": gross - fee,
                "net_at_k035_tenths": gross - fee / 2.0,
                "method_spread_points": result.method_spread(
                    "Over" if side == "yes" else "Under") * 100.0,
                "books": len(two_sided),
                "book_width": meta.get("width"),
                "depth": size,
                "grid": market["grid"],
            })

    counts["kalshi_only"] = len(kalshi) - counts["matched"]
    return rows, counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", help="write the full row set here")
    args = parser.parse_args()

    configure_logging()
    config = OddsConfig.load()

    with httpx.Client(timeout=60) as client:
        book_quotes, book_counts = fetch_book_props(client, config.api_key)
        kalshi, kalshi_counts = fetch_kalshi_props(client)

    rows, match_counts = compare(book_quotes, kalshi)

    print("=" * 78)
    print("WHAT WAS PULLED -- drops included, because a matcher that reports")
    print("only its hits looks identical whether it linked forty or four")
    print("=" * 78)
    for label, counts in (("odds", book_counts), ("kalshi", kalshi_counts),
                          ("match", match_counts)):
        for key, value in counts.items():
            print(f"  {label:<7} {key:<22} {value}")

    if not rows:
        print("\nNo comparable market. Nothing below is a finding.")
        return 1

    print("\n" + "=" * 78)
    print("EDGE DISTRIBUTION, net of the DEPLOYED fee (k = 0.070)")
    print("=" * 78)
    positive = [r for r in rows if r["net_tenths"] > 0]
    print(f"  comparisons              {len(rows)}")
    print(f"  net edge > 0             {len(positive)}")
    beats = [r for r in positive
             if r["net_tenths"] > r["method_spread_points"] * 10.0]
    print(f"  net edge > method spread {len(beats)}   <-- the only column that")
    print("                                     survives CLAUDE.md's rule that")
    print("                                     the devig spread exceeds the")
    print("                                     fee advantage being hunted")
    print(f"  net edge > 0 at k=0.035  "
          f"{len([r for r in rows if r['net_at_k035_tenths'] > 0])}")

    print("\n" + "=" * 78)
    print("TOP 15 BY NET EDGE -- read `spread` and `depth` before the edge")
    print("=" * 78)
    header = (f"{'net':>7}{'k035':>7}{'spread':>8}{'ask':>6}{'fair':>7}"
              f"{'bks':>5}{'depth':>9}  {'side':<4} player / market")
    print(header)
    for row in sorted(rows, key=lambda r: -r["net_tenths"])[:15]:
        print(f"{row['net_tenths']:+7.1f}{row['net_at_k035_tenths']:+7.1f}"
              f"{row['method_spread_points']:8.2f}{row['ask_tenths'] / 10:6.1f}"
              f"{row['fair_probability'] * 100:7.1f}{row['books']:5}"
              f"{row['depth']:9,.0f}  {row['side']:<4} "
              f"{row['player']} {row['threshold']}+ ({row['market']})")

    print("\n  net/k035/spread in tenths of a cent; spread in probability points.")
    print("  A row whose edge is under its own method spread is a statement")
    print("  about method choice, not about the market.")

    if args.json:
        Path(args.json).write_text(json.dumps(
            {"rows": rows, "odds": book_counts, "kalshi": kalshi_counts,
             "match": match_counts}, indent=1))
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
