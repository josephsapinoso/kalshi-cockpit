"""The registered spread/total falsification test, taken as one 4-credit look.

Registration: `docs/measurements/2026-08-20-preregistration-spread-total-edge.md`,
committed before this script ran. Every rule — the exact-line matching that
refuses rather than pools, worst-of-four devig, median-across-books, the
charged-fee decision arm, the UNDERPOWERED floor — is that file's, not this
one's. Do not edit one without the other.

Wire facts this encodes, learned from a free probe before the paid call:

- A Kalshi "spread" is `"<team> wins by over X.5 runs"` with
  `floor_strike = X.5`. The book's same line is that team at point
  **-X.5** and the opponent at **+X.5** — this is the registration's "sign
  convention", and it is the ONLY conversion applied. Totals join on
  `floor_strike == point` exactly; Kalshi YES is Over.
- `KXMLBTOTAL` subtitles name no team, so a totals event borrows its game
  identity from the `KXMLBSPREAD` event sharing its fixture segment
  (`26AUG201240STLCIN`); a totals event with no spread sibling is excluded
  and counted.
- Events carry `fee_multiplier_override` / `fee_type_override`; the charged
  arm honours a non-null override, else the series' own multiplier, fetched
  live and recorded in the artifact.

**Writes nothing to any production table.** Raw payloads land as JSON beside
the registration. The 4 credits are spent outside the planner's `api_credits`
ledger, deliberately — that ledger records the deployed tool's spend; the
vendor's `x-requests-used` header is captured in the artifact instead.

Run (inside an open baseball_mlb window, >=15 min before first pitch):

    .venv\\Scripts\\python.exe scripts\\measure_spread_edge.py
    .venv\\Scripts\\python.exe scripts\\measure_spread_edge.py --replay <raw.json>

`--replay` recomputes from a saved artifact without spending anything, so a
computation bug never costs a second sweep.

What this does not establish: the registration's §8, in full.
"""

from __future__ import annotations

import asyncio
import json
import statistics
import sys
from datetime import datetime, timedelta, timezone
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from typing import Any, Optional

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import KalshiConfig, OddsConfig            # noqa: E402
from backend.core import devig                                 # noqa: E402
from backend.kalshi.rest import KalshiRestClient               # noqa: E402
from backend.logging_setup import configure_logging            # noqa: E402
from backend.match.linker import (                             # noqa: E402
    _matches,
    fixture_segment,
    load_aliases,
)

OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "measurements"

SPORT = "baseball_mlb"
SERIES = ("KXMLBSPREAD", "KXMLBTOTAL")
DECI_CENT = Decimal("0.0001")
K_BASE = Decimal("0.07")
K_DEPLOYED = Decimal("0.07")
SHARP_BOOK = "pinnacle"
MIN_ROWS = 8
MIN_GAMES = 3


def fee_tenths(k: Decimal, price_tenths: int) -> Decimal:
    p = Decimal(price_tenths) / Decimal(1000)
    fee_dollars = (k * p * (Decimal(1) - p)).quantize(
        DECI_CENT, rounding=ROUND_CEILING
    )
    return fee_dollars * Decimal(1000)


def derived_ask_tenths(market: dict) -> Optional[int]:
    """yes_ask = 1000 - best NO bid, from `no_bid_dollars`. None on an
    unquoted NO side — refuse, never 0."""
    no_bid = market.get("no_bid_dollars")
    if no_bid in (None, ""):
        return None
    try:
        tenths = int(round(float(no_bid) * 1000))
    except (TypeError, ValueError):
        return None
    if not 0 < tenths < 1000:
        return None
    return 1000 - tenths


async def capture() -> dict:
    odds_config = OddsConfig.load()
    kalshi_config = KalshiConfig.load()

    params = {
        "apiKey": odds_config.api_key,
        "regions": "us,eu",
        "markets": "spreads,totals",
        "oddsFormat": "decimal",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"https://api.the-odds-api.com/v4/sports/{SPORT}/odds",
            params=params,
        )
    # NOT `raise_for_status()`: its message embeds the full request URL,
    # apiKey included, and a traceback goes to the terminal no matter what
    # `configure_logging()` redacts. Observed 2026-08-20 21:21Z — a 401
    # printed the key into the transcript. Fail with the status alone.
    if response.status_code != 200:
        raise SystemExit(
            f"odds request failed: HTTP {response.status_code} "
            f"(no credits spent on 4xx; the URL is withheld because it "
            f"carries the API key)"
        )
    meta = {
        "requests_used": response.headers.get("x-requests-used"),
        "requests_remaining": response.headers.get("x-requests-remaining"),
    }

    kalshi: dict[str, Any] = {}
    series_meta: dict[str, Any] = {}
    async with KalshiRestClient(kalshi_config) as client:
        for series in SERIES:
            kalshi[series] = [
                e
                async for e in client.events(
                    series_ticker=series, with_nested_markets=True
                )
            ]
            payload = await client.get(f"/series/{series}")
            block = payload.get("series", payload)
            series_meta[series] = {
                "fee_multiplier": block.get("fee_multiplier"),
                "fee_type": block.get("fee_type"),
            }

    return {
        "taken_at": datetime.now(timezone.utc).isoformat(),
        "vendor_meta": meta,
        "series_meta": series_meta,
        "odds": response.json(),
        "kalshi": kalshi,
    }


def compute(raw: dict) -> dict:
    aliases = load_aliases(SPORT)
    odds_events = raw["odds"]
    series_meta = raw["series_meta"]

    # ---- book index -------------------------------------------------------
    # spreads keyed by (game_idx, "spreads", abs(point)): both outcomes of one
    # line live under one key, because Kalshi's floor_strike names the |line|
    # and the two book sides carry opposite signs.
    index: dict[tuple, dict[str, list[dict]]] = {}
    for gi, event in enumerate(odds_events):
        for book in event.get("bookmakers", []):
            for market in book.get("markets", []):
                key_name = market.get("key")
                if key_name not in ("spreads", "totals"):
                    continue
                for outcome in market.get("outcomes", []):
                    point = outcome.get("point")
                    if point is None:
                        continue
                    line = abs(float(point)) if key_name == "spreads" else float(point)
                    index.setdefault((gi, key_name, line), {}).setdefault(
                        book["key"], []
                    ).append(
                        {
                            "name": outcome["name"],
                            "point": float(point),
                            "price": float(outcome["price"]),
                        }
                    )

    # ---- game identity: spread events name their teams --------------------
    def spread_team(market: dict) -> Optional[str]:
        subtitle = market.get("yes_sub_title") or ""
        marker = " wins by"
        if marker not in subtitle:
            return None
        return subtitle.split(marker, 1)[0].strip()

    segment_to_game: dict[str, tuple[int, dict[str, str]]] = {}
    for event in raw["kalshi"].get("KXMLBSPREAD", []):
        segment = fixture_segment(event.get("event_ticker") or "")
        if segment is None:
            continue
        teams = {
            t for t in (spread_team(m) for m in event.get("markets", [])) if t
        }
        if len(teams) < 1:
            continue
        for gi, odds_event in enumerate(odds_events):
            book_names = (odds_event["home_team"], odds_event["away_team"])
            mapping: dict[str, str] = {}
            for team in teams:
                hits = [
                    b for b in book_names if _matches(team, b, aliases)
                ]
                if len(hits) == 1:
                    mapping[team] = hits[0]
            # Every named team resolved, injectively, into this fixture.
            if len(mapping) == len(teams) and len(set(mapping.values())) == len(
                mapping
            ):
                segment_to_game[segment] = (gi, mapping)
                break

    rows: list[dict[str, Any]] = []
    excluded = {
        "not_active": 0, "no_strike": 0, "no_ask": 0, "unnamed_team": 0,
        "unmatched_game": 0, "no_spread_sibling": 0, "no_exact_line": 0,
        "one_sided_book_dropped": 0, "lt_two_books": 0,
        # The second-look registration's per-game commence rule (edit 1 of
        # the three permitted; see that file's section 4 and 9).
        "commenced_or_imminent": 0, "outside_window": 0,
        "unreadable_commence": 0,
    }

    def commence_window_counter(odds_event: dict) -> Optional[str]:
        """The registered per-game commence rule: a matched game enters the
        population only if its odds-fixture `commence_time` lies in
        `[taken_at + 15 min, taken_at + 12 h]` (closed interval; the stamp
        is fixed before the sweep, so this cannot reference the outcome).
        Returns the exclusion counter to bump, or None to admit. An
        unreadable stamp refuses the game -- unreadable resolves to a
        refusal, never a pass."""
        try:
            commence = datetime.fromisoformat(
                str(odds_event["commence_time"]).replace("Z", "+00:00")
            )
            taken = datetime.fromisoformat(
                str(raw["taken_at"]).replace("Z", "+00:00")
            )
        except (KeyError, ValueError):
            return "unreadable_commence"
        if commence < taken + timedelta(minutes=15):
            return "commenced_or_imminent"
        if commence > taken + timedelta(hours=12):
            return "outside_window"
        return None

    def charged_k(series: str, event: dict) -> tuple[Decimal, str]:
        override = event.get("fee_multiplier_override")
        if override is not None:
            return K_BASE * Decimal(str(override)), f"override:{override}"
        multiplier = series_meta[series]["fee_multiplier"]
        return K_BASE * Decimal(str(multiplier)), f"series:{multiplier}"

    for series in SERIES:
        market_key = "spreads" if series == "KXMLBSPREAD" else "totals"
        for event in raw["kalshi"].get(series, []):
            segment = fixture_segment(event.get("event_ticker") or "")
            game = segment_to_game.get(segment or "")
            if game is None:
                excluded[
                    "unmatched_game" if series == "KXMLBSPREAD"
                    else "no_spread_sibling"
                ] += 1
                continue
            gi, mapping = game
            window_counter = commence_window_counter(odds_events[gi])
            if window_counter is not None:
                excluded[window_counter] += 1
                continue
            k_charged, k_source = charged_k(series, event)

            for market in event.get("markets", []):
                if market.get("status") != "active":
                    excluded["not_active"] += 1
                    continue
                strike = market.get("floor_strike")
                if strike is None:
                    excluded["no_strike"] += 1
                    continue
                ask = derived_ask_tenths(market)
                if ask is None:
                    excluded["no_ask"] += 1
                    continue

                if market_key == "spreads":
                    team = spread_team(market)
                    if team is None or team not in mapping:
                        excluded["unnamed_team"] += 1
                        continue
                    yes_book_name = mapping[team]
                    yes_point = -float(strike)
                else:
                    yes_book_name = "Over"
                    yes_point = float(strike)

                line = abs(yes_point) if market_key == "spreads" else yes_point
                books = index.get((gi, market_key, line), {})
                if not books:
                    excluded["no_exact_line"] += 1
                    continue

                fairs, contributing = [], []
                for book_key, outcomes in books.items():
                    yes = [
                        o for o in outcomes
                        if o["name"] == yes_book_name and o["point"] == yes_point
                    ]
                    other = [
                        o for o in outcomes
                        if o["name"] != yes_book_name and o["point"] == -yes_point
                    ] if market_key == "spreads" else [
                        o for o in outcomes
                        if o["name"] == "Under" and o["point"] == yes_point
                    ]
                    if len(yes) != 1 or len(other) != 1:
                        excluded["one_sided_book_dropped"] += 1
                        continue
                    probs = devig.implied_probabilities(
                        [yes[0]["price"], other[0]["price"]]
                    )
                    per_method = []
                    for method in (devig.multiplicative, devig.additive,
                                   devig.power, devig.shin):
                        try:
                            per_method.append(method(probs)[0])
                        except devig.DevigError:
                            continue
                    if per_method:
                        fairs.append(min(per_method))
                        contributing.append(book_key)

                if len(fairs) < 2:
                    excluded["lt_two_books"] += 1
                    continue

                fair = statistics.median(fairs)
                row = {
                    "series": series,
                    "ticker": market.get("ticker"),
                    "line": yes_point,
                    "ask_tenths": ask,
                    "fair": round(fair, 5),
                    "n_books": len(fairs),
                    "books": sorted(contributing),
                    "sharp_anchored": SHARP_BOOK in contributing,
                    "k_source": k_source,
                    "game": segment,
                    "edge_net_tenths_charged": round(
                        1000 * fair - (ask + float(fee_tenths(k_charged, ask))), 2
                    ),
                    "edge_net_tenths_deployed": round(
                        1000 * fair - (ask + float(fee_tenths(K_DEPLOYED, ask))), 2
                    ),
                }
                rows.append(row)

    return {"rows": rows, "excluded": excluded}


def report(result: dict) -> None:
    rows, excluded = result["rows"], result["excluded"]
    for series in SERIES:
        subset = [r for r in rows if r["series"] == series]
        anchored = [r for r in subset if r["sharp_anchored"]]
        games = {r["game"] for r in anchored}
        print(f"\n== {series}: rows {len(subset)}, sharp-anchored "
              f"{len(anchored)}, games {len(games)}")
        for r in sorted(anchored, key=lambda r: (r["game"], r["line"])):
            print(f"  {r['ticker']}: line {r['line']:+} ask {r['ask_tenths']} "
                  f"fair {r['fair']:.3f} books {r['n_books']} "
                  f"edge(charged) {r['edge_net_tenths_charged']:+.1f}t "
                  f"edge(0.07) {r['edge_net_tenths_deployed']:+.1f}t")
        if len(anchored) < MIN_ROWS or len(games) < MIN_GAMES:
            print(f"  VERDICT: UNDERPOWERED "
                  f"(floor: {MIN_ROWS} rows / {MIN_GAMES} games; "
                  f"n read before the effect, as registered)")
            continue
        med = statistics.median(r["edge_net_tenths_charged"] for r in anchored)
        print(f"  median fee-net edge (charged fee): {med:+.2f} tenths")
        print(f"  VERDICT: {'NOT REFUTED' if med > 0 else 'REFUTED'}")
    print(f"\nexcluded: {excluded}")


def main(argv: list[str]) -> int:
    configure_logging()
    if len(argv) == 3 and argv[1] == "--replay":
        raw = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
        print(f"replaying {argv[2]} (taken_at {raw['taken_at']}); no spend")
    else:
        raw = asyncio.run(capture())
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
        out = OUT_DIR / f"2026-08-21-spread-sweep-raw-{stamp}.json"
        out.write_text(json.dumps(raw, indent=1, default=str), encoding="utf-8")
        print(f"raw artifact: {out}")
        print(f"vendor counter: {raw['vendor_meta']}")
        print(f"series fee meta: {raw['series_meta']}")

    result = compute(raw)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    rows_path = OUT_DIR / f"2026-08-21-spread-edge-rows-{stamp}.json"
    rows_path.write_text(
        json.dumps(
            {"registration":
                 "2026-08-21-preregistration-spread-total-edge-second-look.md",
             **result},
            indent=1,
        ),
        encoding="utf-8",
    )
    report(result)
    print(f"\nrows artifact: {rows_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
