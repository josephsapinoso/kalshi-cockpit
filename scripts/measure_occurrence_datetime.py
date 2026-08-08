"""What is Kalshi's `occurrence_datetime` -- a shifted start, or an expected end?

Two readings of the same field were both supported by real observations and the
repo could not choose between them:

**A -- a timezone-shifted start.** `tasks/lessons.md` records the field running
exactly +180 min against The Odds API's kickoff on 14 of 18 same-day MLB pairs
and 6 of 6 WNBA pairs. MLB games run ~3h and WNBA ~2h, so an identical offset
for both is what a fixed shift looks like, not what a duration looks like.

**B -- an expected end.** In `tests/fixtures/events_sports_nested.json`,
`occurrence_datetime == expected_expiration_time` on 198 of 200 markets.

This harness settles it with three measurements that cost no sportsbook
credits, because they use only Kalshi's own free, unauthenticated REST data.

1. **Period vs full game.** A first-half / first-five-innings market and its
   full-game market describe the same fixture. If `occurrence_datetime` is a
   START they must be identical; if it is an EXPECTED END the period market
   must be EARLIER, by roughly the remaining game. There is no third answer.

2. **The MLB rulebook anchor.** `KXMLB*` `rules_primary` states the scheduled
   first pitch in words -- "originally scheduled for Aug 8, 2026 at 3:05 PM
   EDT". That is a true start time carried inside Kalshi's own payload, so the
   offset can be measured against it for free. MLB is the only league whose
   rules text carries a clock time; every other league states a date only.

3. **Settled markets: `settlement_ts` vs `occurrence_datetime`.** Settlement
   happens a few minutes after the real result is known, so
   `settlement_ts - occurrence_datetime` estimates `game_length - offset`.
   Reading B predicts ~0 in every league. Reading A predicts a value that
   varies with how long the sport takes, and is negative for short sports.

Run:

    .venv\\Scripts\\python.exe scripts\\measure_occurrence_datetime.py
    .venv\\Scripts\\python.exe scripts\\measure_occurrence_datetime.py --capture

Read-only. Places no orders. **Spends no Odds API credits and never calls The
Odds API** -- the daily budget is ~16 and is shared with the live instance.
Never paginates `/markets`; discovery is through `/events`, and settled markets
are fetched one event at a time with `?event_ticker=`.

Unauthenticated on purpose. `/series`, `/events` and `/markets?event_ticker=`
answer 200 without credentials (verified 2026-08-07), so this script cannot
read, log or leak the private key -- it never loads it.

What this harness does NOT establish
------------------------------------
- **It does not measure the offset outside MLB from a true start.** Only MLB's
  rulebook states a clock time. For every other league the offset is inferred
  from `settlement_ts`, which bounds it to within the sport's game length plus
  Kalshi's settlement lag -- good to about +/-20 min, not to the minute.
- **It says nothing about postponed or rescheduled games.** Every fixture here
  is one Kalshi has not moved. A rescheduled game may carry a stale
  `occurrence_datetime`, and nothing below would notice.
- **It is one slate.** The period-vs-game comparison is a structural fact about
  how Kalshi populates the field and is unlikely to be a day effect, but the
  per-league settlement medians are from the games settled in the last week.
- **It does not establish that the offset is stable over time.** It is a Kalshi
  data-entry artifact, not a documented contract, and can be corrected without
  notice. That is the argument for recording the skew rather than subtracting
  it.
- **It does not measure liquidity, price or edge**, and nothing here should be
  read as evidence that a period market is worth trading.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
CAPTURE_NAME = "occurrence_datetime_probe.json"

# Politeness. Kalshi's documented read limit is ~10/s. 0.12s still drew 429s on
# the settled walk (one `/markets?event_ticker=` per event, back to back), so
# this sits well under the limit -- the run is not time-critical and a
# throttled sweep that silently returns fewer fixtures is the failure mode
# worth paying seconds to avoid.
SLEEP_S = 0.25
HTTP_TIMEOUT_S = 60.0

HOUR_MS = 3_600_000

# (period series, its full-game counterpart). Every one of these was confirmed
# to exist in `/series?category=Sports` on 2026-08-07. Pairs with no open
# fixtures on the day are reported as n=0 rather than dropped, so a thin slate
# reads as a thin slate and not as a missing test.
PERIOD_PAIRS: tuple[tuple[str, str], ...] = (
    ("KXMLBF5", "KXMLBGAME"),
    ("KXMLBF5SPREAD", "KXMLBGAME"),
    ("KXMLBRFI", "KXMLBGAME"),
    ("KXMLS1H", "KXMLSGAME"),
    ("KXNFL1H", "KXNFLGAME"),
    ("KXNCAAF1H", "KXNCAAFGAME"),
    ("KXWNBA1H", "KXWNBAGAME"),
    ("KXEPL1H", "KXEPLGAME"),
    ("KXUCL1H", "KXUCLGAME"),
    ("KXEFLCUP1H", "KXEFLCUPGAME"),
    ("KXBRASILEIRO1H", "KXBRASILEIROGAME"),
    ("KXBRASILEIROB1H", "KXBRASILEIROBGAME"),
    ("KXBRASILEIROC1H", "KXBRASILEIROCGAME"),
    ("KXJLEAGUE1H", "KXJLEAGUEGAME"),
    ("KXKLEAGUE1H", "KXKLEAGUEGAME"),
    ("KXLEAGUESCUP1H", "KXLEAGUESCUPGAME"),
    ("KXUSL1H", "KXUSLGAME"),
    ("KXEREDIVISIE1H", "KXEREDIVISIEGAME"),
    ("KXLIGAPORTUGAL1H", "KXLIGAPORTUGALGAME"),
    ("KXSCOTTISHPREM1H", "KXSCOTTISHPREMGAME"),
)

# Every MLB per-fixture series. All of them hang off the same first pitch, so
# they are the widest available test of "does this field depend on what the
# contract is about, or only on which fixture it is".
MLB_SERIES: tuple[str, ...] = (
    "KXMLBGAME",
    "KXMLBF5",
    "KXMLBF5SPREAD",
    "KXMLBRFI",
    "KXMLBSPREAD",
    "KXMLBTOTAL",
    "KXMLBTEAMTOTAL",
    "KXMLBKS",
    "KXMLBEXTRAS",
)

# Full-game series to check `expected_expiration_time` against, and to walk for
# settled fixtures. Chosen to span game lengths: soccer ~2h, WNBA ~2.2h,
# baseball/hockey ~2.7h, football ~3.1h. That spread is the whole point --
# reading B predicts the same answer for all of them.
GAME_SERIES: tuple[str, ...] = (
    "KXMLBGAME",
    "KXWNBAGAME",
    "KXNBAGAME",
    "KXNHLGAME",
    "KXNFLGAME",
    "KXNCAAFGAME",
    "KXMLSGAME",
    "KXEPLGAME",
    "KXUCLGAME",
    "KXEFLCUPGAME",
)

# Nominal wall-clock length of one fixture, hours. Used ONLY to print an
# implied-offset column beside the measured settlement lag -- no test turns on
# these numbers, and they are stated so a reader can disagree with them.
NOMINAL_GAME_HOURS: dict[str, float] = {
    "KXMLBGAME": 2.75,
    "KXWNBAGAME": 2.20,
    "KXNBAGAME": 2.40,
    "KXNHLGAME": 2.60,
    "KXNFLGAME": 3.10,
    "KXNCAAFGAME": 3.40,
    "KXMLSGAME": 2.00,
    "KXEPLGAME": 2.00,
    "KXUCLGAME": 2.00,
    "KXEFLCUPGAME": 2.00,
}

# "originally scheduled for Aug 8, 2026 at 3:05 PM EDT"
_RULES_START = re.compile(
    r"scheduled for ([A-Z][a-z]{2} \d{1,2}, \d{4}) at (\d{1,2}:\d{2} [AP]M) ([A-Z]{2,5})"
)

# US zone abbreviations Kalshi uses, as fixed UTC offsets in hours. A literal
# table rather than a tz database lookup: the abbreviation already names the
# offset unambiguously ("EDT" is -4 whatever the date), so resolving it through
# a zone name would reintroduce the DST question the abbreviation just settled.
_ZONE_OFFSET_H: dict[str, int] = {
    "EDT": -4, "EST": -5,
    "CDT": -5, "CST": -6,
    "MDT": -6, "MST": -7,
    "PDT": -7, "PST": -8,
    "AKDT": -8, "HST": -10,
}


# -- plumbing ---------------------------------------------------------------


def parse_ms(value: Any) -> Optional[int]:
    """ISO-8601 to epoch milliseconds, UTC. Unreadable returns None, never 0."""
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.astimezone(timezone.utc).timestamp() * 1000)
    except (ValueError, TypeError):
        return None


def rules_start_ms(market: dict) -> Optional[int]:
    """The scheduled start Kalshi states in words, as epoch ms. None if absent.

    This is the only true start time available without a sportsbook feed, and
    it exists on MLB series only -- other leagues state a date with no clock
    time. `None` means "no anchor", and the caller must skip the fixture rather
    than substitute anything.
    """
    for field in ("rules_primary", "rules_secondary"):
        match = _RULES_START.search(market.get(field) or "")
        if not match:
            continue
        offset_h = _ZONE_OFFSET_H.get(match.group(3))
        if offset_h is None:
            return None
        naive = datetime.strptime(
            f"{match.group(1)} {match.group(2)}", "%b %d, %Y %I:%M %p"
        )
        as_utc = naive.replace(tzinfo=timezone.utc).timestamp() * 1000
        return int(as_utc) - offset_h * HOUR_MS
    return None


def event_id(event_ticker: str) -> str:
    """`KXMLBF5-26AUG081505ATLNYY` -> `26AUG081505ATLNYY`.

    The fixture id is shared between a full-game series and its period series,
    which is what makes them joinable without any team-name matching at all.
    """
    return event_ticker.split("-", 1)[1] if "-" in event_ticker else event_ticker


class Kalshi:
    """Minimal read-only client. Unauthenticated: these endpoints are public."""

    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self._client = httpx.Client(timeout=HTTP_TIMEOUT_S)
        self.requests = 0

    def get(self, path: str, **params: Any) -> dict:
        self.requests += 1
        response = self._client.get(f"{self.base_url}{path}", params=params)
        if response.status_code == 429:
            delay = float(response.headers.get("Retry-After", "2"))
            print(f"    429, backing off {delay}s")
            time.sleep(max(0.5, delay))
            return self.get(path, **params)
        response.raise_for_status()
        time.sleep(SLEEP_S)
        return response.json()

    def events(self, series_ticker: str, status: str = "open") -> list[dict]:
        """Open events for one series, with nested markets.

        Never `/markets`: that endpoint is ~99.8% `KXMVE` with no volume.
        """
        payload = self.get(
            "/events",
            series_ticker=series_ticker,
            status=status,
            with_nested_markets="true",
            limit=200,
        )
        if "events" not in payload:
            raise RuntimeError(
                f"/events for {series_ticker} has no 'events' key "
                f"(got {sorted(payload)}) -- refusing to read that as 'none'"
            )
        return payload["events"] or []

    def markets_for_event(self, event_ticker: str) -> list[dict]:
        """Settled events carry no nested markets, so they need this."""
        payload = self.get("/markets", event_ticker=event_ticker)
        return payload.get("markets") or []

    def close(self) -> None:
        self._client.close()


def first_market(event: dict) -> Optional[dict]:
    markets = event.get("markets") or []
    return markets[0] if markets else None


def hours(delta_ms: Optional[int]) -> str:
    return "" if delta_ms is None else f"{delta_ms / HOUR_MS:+.2f}h"


# -- test 1: period vs full game --------------------------------------------


def test_period_vs_game(api: Kalshi, capture: dict) -> Counter:
    """The discriminator. Same fixture, two contract lengths, one field."""
    print("=" * 88)
    print("TEST 1 -- PERIOD MARKET vs FULL-GAME MARKET, SAME FIXTURE")
    print("=" * 88)
    print("A start is shared by both. An expected end must make the period")
    print("market EARLIER. Any positive delta refutes the expected-end reading.\n")

    pooled: Counter = Counter()
    for period_series, game_series in PERIOD_PAIRS:
        period = {event_id(e["event_ticker"]): e for e in api.events(period_series)}
        game = {event_id(e["event_ticker"]): e for e in api.events(game_series)}
        shared = sorted(set(period) & set(game))

        deltas: Counter = Counter()
        example = None
        for key in shared:
            pm, gm = first_market(period[key]), first_market(game[key])
            if not pm or not gm:
                continue
            p_occ = parse_ms(pm.get("occurrence_datetime"))
            g_occ = parse_ms(gm.get("occurrence_datetime"))
            if p_occ is None or g_occ is None:
                continue
            deltas[p_occ - g_occ] += 1
            pooled[p_occ - g_occ] += 1
            if example is None:
                example = (
                    key,
                    pm.get("occurrence_datetime"),
                    gm.get("occurrence_datetime"),
                )
                capture.setdefault("period_pairs", []).append(
                    {
                        "period_ticker": pm.get("ticker"),
                        "game_ticker": gm.get("ticker"),
                        "period_occurrence_datetime": pm.get("occurrence_datetime"),
                        "game_occurrence_datetime": gm.get("occurrence_datetime"),
                        "period_expected_expiration_time": pm.get(
                            "expected_expiration_time"
                        ),
                        "game_expected_expiration_time": gm.get(
                            "expected_expiration_time"
                        ),
                        "period_close_time": pm.get("close_time"),
                        "game_close_time": gm.get("close_time"),
                    }
                )

        spread = ", ".join(
            f"{hours(d)} x{n}" for d, n in sorted(deltas.items())
        ) or "--"
        print(f"  {period_series:<20} vs {game_series:<22} n={len(shared):>3}  {spread}")
        if example:
            print(f"      {example[0]}: period {example[1]}  game {example[2]}")

    total = sum(pooled.values())
    print(f"\n  POOLED n={total} pairs across "
          f"{sum(1 for _ in PERIOD_PAIRS)} series pairs")
    for delta, n in sorted(pooled.items()):
        share = n / total if total else 0
        print(f"      {hours(delta):>8}  n={n:>4}  {share:>6.1%}")
    earlier = sum(n for d, n in pooled.items() if d < 0)
    print(f"\n  period market EARLIER than full game (required by 'expected "
          f"end'): {earlier} of {total}")
    return pooled


# -- test 2: the MLB rulebook anchor ----------------------------------------


def test_mlb_anchor(api: Kalshi, capture: dict) -> dict[str, Counter]:
    """Offset against a true start Kalshi itself states, in words."""
    print("\n" + "=" * 88)
    print("TEST 2 -- OFFSET FROM THE SCHEDULED START KALSHI STATES IN ITS RULES")
    print("=" * 88)
    print("MLB only: no other league's rules text carries a clock time.")
    print("Anchor: rules_primary '... originally scheduled for <date> at <time> <TZ>'\n")

    per_series: dict[str, Counter] = {}
    for series in MLB_SERIES:
        offsets: Counter = Counter()
        anchored = 0
        example = None
        events = api.events(series)
        for event in events:
            market = first_market(event)
            if not market:
                continue
            start = rules_start_ms(market)
            occ = parse_ms(market.get("occurrence_datetime"))
            exp = parse_ms(market.get("expected_expiration_time"))
            close = parse_ms(market.get("close_time"))
            if start is None or occ is None:
                continue
            anchored += 1
            offsets[(occ - start, (exp - start) if exp else None,
                     (close - start) if close else None)] += 1
            if example is None:
                example = (market.get("ticker"), start, occ, exp, close)
                capture.setdefault("mlb_anchor", []).append(
                    {
                        "ticker": market.get("ticker"),
                        "rules_primary": market.get("rules_primary"),
                        "occurrence_datetime": market.get("occurrence_datetime"),
                        "expected_expiration_time": market.get(
                            "expected_expiration_time"
                        ),
                        "close_time": market.get("close_time"),
                    }
                )
        per_series[series] = offsets
        print(f"  {series:<16} events={len(events):>3}  anchored={anchored:>3}")
        for (occ_d, exp_d, close_d), n in sorted(offsets.items()):
            print(f"      occ {hours(occ_d):>7}   exp {hours(exp_d):>7}   "
                  f"close {hours(close_d):>8}   n={n}")
        if example:
            stamp = datetime.fromtimestamp(
                example[1] / 1000, timezone.utc
            ).strftime("%Y-%m-%dT%H:%MZ")
            print(f"      e.g. {example[0]}  rules start {stamp}")
    return per_series


# -- test 3: settled markets ------------------------------------------------


def test_settlement_lag(
    api: Kalshi, capture: dict, per_series: int
) -> dict[str, list[float]]:
    """`settlement_ts - occurrence_datetime`, per league, on settled fixtures.

    An expected end predicts ~0 everywhere. A fixed shift predicts
    `game_length - offset`, which is negative for a sport shorter than the
    offset -- so short sports are where the two readings separate.
    """
    print("\n" + "=" * 88)
    print("TEST 3 -- SETTLED FIXTURES: settlement_ts MINUS occurrence_datetime")
    print("=" * 88)
    print("'expected end' predicts ~0 in EVERY league. A fixed shift predicts a")
    print("value that tracks how long the sport takes.\n")
    print(f"  {'series':<16}{'n':>4}{'median':>9}{'min':>9}{'max':>9}"
          f"{'nominal game':>14}{'implied offset':>16}")
    print("  " + "-" * 84)

    results: dict[str, list[float]] = {}
    for series in GAME_SERIES:
        try:
            events = api.events(series, status="settled")[:per_series]
        except httpx.HTTPStatusError as exc:
            print(f"  {series:<16} HTTP {exc.response.status_code}")
            continue

        lags: list[tuple[float, str]] = []
        for event in events:
            markets = api.markets_for_event(event["event_ticker"])
            if not markets:
                continue
            market = markets[0]
            occ = parse_ms(market.get("occurrence_datetime"))
            settled = parse_ms(market.get("settlement_ts"))
            if occ is None or settled is None:
                continue
            lags.append(((settled - occ) / HOUR_MS, market.get("ticker") or ""))

        if not lags:
            print(f"  {series:<16}{0:>4}   (no settled fixtures with both fields)")
            results[series] = []
            continue

        values = sorted(v for v, _ in lags)
        med = statistics.median(values)
        nominal = NOMINAL_GAME_HOURS.get(series)
        implied = f"{nominal - med:+.2f}h" if nominal is not None else "?"
        print(f"  {series:<16}{len(values):>4}{med:>+9.2f}{values[0]:>+9.2f}"
              f"{values[-1]:>+9.2f}{(nominal or 0):>13.2f}h{implied:>16}")
        results[series] = values

        sample = sorted(lags, key=lambda x: x[0])[len(lags) // 2]
        print(f"      median fixture: {sample[1]}  {sample[0]:+.2f}h")
        capture.setdefault("settlement_lag", []).append(
            {"series": series, "n": len(values), "median_hours": med,
             "median_ticker": sample[1], "all_hours": values}
        )

    print("\n  'implied offset' = nominal game length minus the measured lag.")
    print("  Under the expected-end reading every median would sit near 0.00.")
    return results


# -- test 4: where expected_expiration_time disagrees -----------------------


def test_expected_expiration(api: Kalshi, capture: dict) -> None:
    """Why `occ == expected_expiration_time` on 198/200 -- and what the 2 say."""
    print("\n" + "=" * 88)
    print("TEST 4 -- expected_expiration_time MINUS occurrence_datetime")
    print("=" * 88)
    print("The fixture's 198-of-200 equality is the provenance of reading B.")
    print("Where the two DISAGREE, which one is earlier decides the question.\n")

    for series in GAME_SERIES:
        deltas: Counter = Counter()
        closes: Counter = Counter()
        example = None
        for event in api.events(series):
            for market in event.get("markets") or []:
                occ = parse_ms(market.get("occurrence_datetime"))
                exp = parse_ms(market.get("expected_expiration_time"))
                close = parse_ms(market.get("close_time"))
                if occ is None:
                    continue
                deltas[(exp - occ) if exp is not None else None] += 1
                if close is not None:
                    closes[close - occ] += 1
                if exp is not None and exp != occ and example is None:
                    example = market
        n = sum(deltas.values())
        spread = ", ".join(f"{hours(d)} x{c}" for d, c in sorted(
            deltas.items(), key=lambda kv: (kv[0] is None, kv[0])
        )) or "--"
        close_spread = ", ".join(
            f"{hours(d)} x{c}" for d, c in sorted(closes.items())[:3]
        ) or "--"
        print(f"  {series:<16} markets={n:>4}  exp-occ: {spread}")
        print(f"  {'':<16} {'':>12}  close-occ: {close_spread}")
        if example:
            print(f"      DISAGREES: {example.get('ticker')}  "
                  f"occ {example.get('occurrence_datetime')}  "
                  f"exp {example.get('expected_expiration_time')}")
            capture.setdefault("exp_disagreements", []).append(
                {
                    "ticker": example.get("ticker"),
                    "occurrence_datetime": example.get("occurrence_datetime"),
                    "expected_expiration_time": example.get(
                        "expected_expiration_time"
                    ),
                    "close_time": example.get("close_time"),
                }
            )


# -- verdict ----------------------------------------------------------------


def verdict(pooled: Counter, lags: dict[str, list[float]]) -> None:
    print("\n" + "=" * 88)
    print("VERDICT")
    print("=" * 88)
    total = sum(pooled.values())
    earlier = sum(n for d, n in pooled.items() if d < 0)
    same = pooled.get(0, 0)
    print(f"  period/full-game pairs         n = {total}")
    print(f"      identical occurrence       {same} ({same / total:.1%})"
          if total else "      identical occurrence       --")
    print(f"      period EARLIER (needs 'end') {earlier}")
    measured = {k: statistics.median(v) for k, v in lags.items() if v}
    if measured:
        span = max(measured.values()) - min(measured.values())
        print(f"  settlement lag spread across {len(measured)} leagues: "
              f"{span:.2f}h "
              f"({min(measured, key=measured.get)} to "
              f"{max(measured, key=measured.get)})")
    print()
    if total and earlier == 0:
        print("  occurrence_datetime is a START, not an expected end. No period")
        print("  market anywhere in the sample resolves earlier than its own")
        print("  full-game market, which an expected end would require.")
    else:
        print("  INCONCLUSIVE -- some period markets are earlier than their")
        print("  full-game market. Read the per-pair table above before acting.")


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--capture", action="store_true",
        help=f"write the raw evidence to tests/fixtures/{CAPTURE_NAME}",
    )
    parser.add_argument(
        "--settled-per-series", type=int, default=15,
        help="how many settled fixtures to sample per league (default 15)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    api = Kalshi()
    capture: dict[str, Any] = {
        "captured_ms": int(time.time() * 1000),
        "base_url": BASE_URL,
        "note": (
            "Evidence for docs/adr + tasks/inbox/research.md: is "
            "occurrence_datetime a shifted start or an expected end? Captured "
            "unauthenticated from public Kalshi endpoints."
        ),
    }
    try:
        pooled = test_period_vs_game(api, capture)
        test_mlb_anchor(api, capture)
        lags = test_settlement_lag(api, capture, args.settled_per_series)
        test_expected_expiration(api, capture)
        verdict(pooled, lags)
    finally:
        print(f"\n  {api.requests} Kalshi requests. Zero Odds API credits spent.")
        api.close()

    if args.capture:
        FIXTURES.mkdir(parents=True, exist_ok=True)
        path = FIXTURES / CAPTURE_NAME
        path.write_text(json.dumps(capture, indent=2), encoding="utf-8")
        print(f"  captured -> tests/fixtures/{CAPTURE_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
