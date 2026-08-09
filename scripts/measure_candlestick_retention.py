"""How far back does Kalshi keep candlesticks? The question that gates a backtest.

`docs/adr/0011` records this as an open unknown and `start.md` lists it as a
watch item. It became the deciding question on 2026-08-09, when the 20K Odds API
tier arrived carrying **historical odds**: replaying past slates through the
existing devig -> engine -> suppression chain would answer "is there any edge at
all?" in days rather than the months a forward record needs.

But historical odds gives the **sportsbook** side only. Rule 3 of `CLAUDE.md` is
*validate against Kalshi's own closing line*, and for a past game that line can
only come from candlesticks -- `KalshiClient.candlesticks`, the CLV primitive.
So if Kalshi keeps only a short window, every historical credit spent beyond it
buys a sportsbook price with nothing to score it against. Historical odds cost
**10 x markets x regions**, so the wrong answer here is expensive.

This harness answers it for free: Kalshi REST is unmetered, and `/events`,
`/markets?event_ticker=` and the candlesticks endpoint itself all answer 200
**unauthenticated** (verified 2026-08-09). It never loads the private key.

Two limits, reported separately, because they are different facts and the
tighter one wins in silence -- `tasks/lessons.md`, two-limits-on-one-quantity:

1. **Discovery.** How far back `/events?status=settled` will list games at all.
2. **Retention.** How far back candlesticks still return bars.

If discovery binds first, the retention answer is a lower bound and says so,
rather than being reported as though Kalshi stopped keeping data.

Run:

    .venv\\Scripts\\python.exe scripts\\measure_candlestick_retention.py
    .venv\\Scripts\\python.exe scripts\\measure_candlestick_retention.py --series KXMLBGAME

Read-only. Places no orders. **Spends no Odds API credits and never calls The
Odds API.** Never paginates `/markets`.

What this harness does NOT establish
------------------------------------
- **It measures retention today.** Kalshi can change the window without notice,
  and a backfill planned against this number should re-check before it runs.
- **It does not prove a bar is usable.** A market that barely traded can return
  candles with no `yes_ask`, which `parse_candlestick` may still reject. This
  answers "does Kalshi still serve history for this market", not "is the
  closing line recoverable for every game".
- **It says nothing about the odds side.** Whether The Odds API has matching
  snapshots for the same dates is a separate question, and a paid one.
- **It samples.** A bucket reported as empty had `--samples` markets tried, not
  every market in it.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
HTTP_TIMEOUT_S = 60.0
SLEEP_S = 0.25
MAX_RETRIES = 5
PAGE_LIMIT = 200

# The series worth asking about: game-level markets in leagues this project can
# devig against. MLB first because it is the only one in season in August, so it
# is the only one that can distinguish "aged out" from "never existed".
DEFAULT_SERIES = ("KXMLBGAME", "KXWNBAGAME", "KXNFLGAME")

# `KXMLBGAME-26AUG082150TBSEA` -> 2026-08-08 21:50Z. The time is optional:
# `KXNCAAFGAME-26SEP19MSUND` carries a date only. Parsed from the ticker rather
# than read from `occurrence_datetime`, which is null on settled events -- and
# which runs three hours late even when present (`tasks/lessons.md`).
_TICKER_DATE = re.compile(r"-(\d{2})([A-Z]{3})(\d{2})(\d{4})?")
_MONTHS = {m: i + 1 for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
     "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
)}


def ticker_date(event_ticker: str) -> Optional[datetime]:
    """UTC datetime encoded in an event ticker, or None if unparseable."""
    match = _TICKER_DATE.search(event_ticker)
    if not match:
        return None
    yy, mon, dd, hhmm = match.groups()
    month = _MONTHS.get(mon)
    if month is None:
        return None
    try:
        return datetime(
            2000 + int(yy), month, int(dd),
            int(hhmm[:2]) if hhmm else 12,
            int(hhmm[2:]) if hhmm else 0,
            tzinfo=timezone.utc,
        )
    except ValueError:
        return None


def _get(client: httpx.Client, path: str, **params: Any) -> dict:
    """GET with backoff. Kalshi's documented read limit is ~10/s."""
    for attempt in range(MAX_RETRIES):
        response = client.get(f"{BASE_URL}{path}", params=params)
        if response.status_code != 429:
            response.raise_for_status()
            return response.json()
        backoff = SLEEP_S * (2 ** (attempt + 2))
        print(f"    429; backing off {backoff:.1f}s", file=sys.stderr)
        time.sleep(backoff)
    response.raise_for_status()
    return {}


def settled_events(
    client: httpx.Client, series: str, max_pages: int
) -> Iterator[tuple[str, datetime]]:
    """Walk settled events for one series, newest first as Kalshi returns them.

    Note the trap recorded in `start.md`: `?status=settled` is the *query* value,
    but the `status` field on the returned market reads `finalized`. Nothing here
    matches on that field, deliberately.
    """
    cursor: Optional[str] = None
    for page in range(max_pages):
        params: dict[str, Any] = {
            "series_ticker": series, "status": "settled", "limit": PAGE_LIMIT,
        }
        if cursor:
            params["cursor"] = cursor
        payload = _get(client, "/events", **params)
        events = payload.get("events") or []
        if not events:
            return
        for event in events:
            ticker = event.get("event_ticker") or ""
            when = ticker_date(ticker)
            if when is not None:
                yield ticker, when
        cursor = payload.get("cursor") or None
        if not cursor:
            return
        time.sleep(SLEEP_S)


def constructed_tickers(event_ticker: str) -> list[str]:
    """Candidate market tickers for an event, without asking `/markets`.

    A market ticker is `<event_ticker>-<TEAM>`, and both team codes are
    concatenated in the event ticker's tail: `...HOUSD` yields `HOU` and `SD`.
    The split point is not recoverable (`HOUSD` could be `HO`+`USD`), so every
    prefix and suffix of the tail is tried and the endpoint decides.

    This exists to separate two limits that otherwise look identical. When
    `/markets?event_ticker=` returns nothing, the market might merely be
    unlisted while its candlesticks still answer -- in which case a backfill
    could reach further back than discovery suggests. Verified 2026-08-09: it
    cannot. Construction finds both markets at 5 and 60 days and returns 404 at
    85 days and beyond, so the data is gone rather than hidden.
    """
    tail = re.sub(r"^.*-\d{2}[A-Z]{3}\d{2}\d{0,4}", "", event_ticker)
    if len(tail) < 3:
        return []
    return sorted(
        {tail[:i] for i in range(2, len(tail))}
        | {tail[i:] for i in range(1, len(tail) - 1)}
    )


def first_market(
    client: httpx.Client, series: str, event_ticker: str, when: datetime
) -> Optional[str]:
    """A market ticker for this event: listed if possible, constructed if not.

    Falling back to construction is what makes a `no market` row in the table
    mean "gone", rather than "we only asked the one endpoint".
    """
    payload = _get(client, "/markets", event_ticker=event_ticker)
    markets = payload.get("markets") or []
    if markets:
        return markets[0].get("ticker")

    end_ts = int(when.timestamp())
    for suffix in constructed_tickers(event_ticker):
        candidate = f"{event_ticker}-{suffix}"
        try:
            _get(
                client,
                f"/series/{series}/markets/{candidate}/candlesticks",
                start_ts=end_ts - 3600, end_ts=end_ts, period_interval=60,
            )
        except httpx.HTTPStatusError:
            time.sleep(SLEEP_S / 2)
            continue
        return candidate
    return None


def has_candles(
    client: httpx.Client, series: str, market: str, when: datetime
) -> Optional[int]:
    """Number of bars in the two hours before `when`, or None if the call failed.

    None and 0 are kept apart on purpose: a 404 or a 500 is "we could not look",
    while 0 is "Kalshi looked and has nothing". Collapsing them would report an
    outage as an expiry -- the unreadable-must-never-resolve-to-zero rule applied
    to a measurement rather than to a price.
    """
    end_ts = int(when.timestamp())
    start_ts = end_ts - 2 * 60 * 60
    try:
        payload = _get(
            client,
            f"/series/{series}/markets/{market}/candlesticks",
            start_ts=start_ts, end_ts=end_ts, period_interval=60,
        )
    except httpx.HTTPStatusError:
        return None
    return len(payload.get("candlesticks") or [])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--series", nargs="*", default=list(DEFAULT_SERIES))
    parser.add_argument("--max-pages", type=int, default=10,
                        help="pages of settled events to walk per series")
    parser.add_argument("--samples", type=int, default=3,
                        help="markets probed per age bucket")
    parser.add_argument("--bucket-days", type=int, default=7)
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    exit_code = 0

    with httpx.Client(timeout=HTTP_TIMEOUT_S) as client:
        for series in args.series:
            print(f"\n{'=' * 70}\n{series}\n{'=' * 70}")
            try:
                events = list(settled_events(client, series, args.max_pages))
            except httpx.HTTPStatusError as exc:
                print(f"  /events failed: {exc}")
                continue
            if not events:
                print("  no settled events discoverable — nothing to measure.")
                continue

            ages = [(now - when).days for _, when in events]
            print(f"  {len(events)} settled events discoverable")
            print(f"  discovery reaches back {max(ages)} days "
                  f"(newest {min(ages)}d)")

            buckets: dict[int, list[tuple[str, datetime]]] = defaultdict(list)
            for (ticker, when), age in zip(events, ages):
                buckets[age // args.bucket_days].append((ticker, when))

            # Three outcomes, never two. "The event lists no markets" and "the
            # candlesticks call failed" are different limits on different
            # endpoints, and the first version of this script counted them in
            # one `failed` column -- which reported a *market-listing* limit as
            # a candlestick retention finding. Same shape as the two-limits
            # lesson that this script's own docstring cites, reproduced while
            # writing it.
            print(f"\n  {'age (days)':<13}{'probed':<8}{'bars':<7}{'empty':<8}"
                  f"{'no market':<11}{'candles err':<13}bars seen")
            oldest_with_bars: Optional[int] = None
            newest_bucket_had_bars: Optional[bool] = None

            for bucket in sorted(buckets):
                sample = buckets[bucket][:args.samples]
                counts: list[int] = []
                no_market = 0
                candles_err = 0
                for ticker, when in sample:
                    market = first_market(client, series, ticker, when)
                    time.sleep(SLEEP_S)
                    if market is None:
                        no_market += 1
                        continue
                    n = has_candles(client, series, market, when)
                    time.sleep(SLEEP_S)
                    if n is None:
                        candles_err += 1
                    else:
                        counts.append(n)
                with_bars = sum(1 for n in counts if n > 0)
                empty = sum(1 for n in counts if n == 0)
                low = bucket * args.bucket_days
                span = f"{low}-{low + args.bucket_days - 1}"
                print(f"  {span:<13}{len(sample):<8}{with_bars:<7}{empty:<8}"
                      f"{no_market:<11}{candles_err:<13}"
                      f"{sorted(counts, reverse=True)[:3]}")
                if with_bars:
                    oldest_with_bars = max(
                        oldest_with_bars or 0, low + args.bucket_days - 1
                    )
                if newest_bucket_had_bars is None:
                    newest_bucket_had_bars = with_bars > 0

            print()
            # The control. A probe that finds nothing at every age looks exactly
            # like "Kalshi keeps nothing", and would kill the backtest on the
            # strength of a broken harness. The newest bucket is the one that
            # must have data; if it does not, distrust everything above.
            if newest_bucket_had_bars is False:
                print("  BROKEN PROBE: the most recent settled games have no "
                      "bars either.")
                print("  That is a fault in this script or in the endpoint, not "
                      "a retention finding. Do not conclude anything from the "
                      "table above.")
                exit_code = 1
                continue

            if oldest_with_bars is None:
                print("  no bars at any age.")
            else:
                print(f"  RETENTION: bars still served at {oldest_with_bars} "
                      f"days old.")
                if oldest_with_bars >= max(ages) - args.bucket_days:
                    print("  DISCOVERY BINDS, NOT RETENTION: the oldest game we "
                          "could find still has bars, so this is a *lower "
                          "bound*. Raise --max-pages to push it further.")
                else:
                    print("  Past that age the market is gone, not merely "
                          "unlisted: `no market` here means the listing was "
                          "empty AND every constructed ticker 404'd, and the "
                          "same construction resolves both markets inside the "
                          "window.")

    print("\nWhat this bounds: a backtest can only score against Kalshi's close "
          "for games inside the retention window above.")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
