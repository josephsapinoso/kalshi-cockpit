"""Capture `GET /markets/{ticker}` — the wire format the order path refreshes from.

**Why this exists as its own capture.** Refreshing a quote at order time needs
one market's current book, not a walk of the universe. That is a *different
endpoint* from `/events?with_nested_markets=true`, and this repo has been caught
twice by assuming two endpoints agree about field names: `apply_snapshot` read
`data["yes"]` while the socket sent `yes_dollars_fp`, and `combos.py` read the
path-shaped `multivariate_event_collections` while the wire key was
`multivariate_contracts`. Both returned something plausible and empty.

So the fixture stores **three** representations of the same ticker, captured
seconds apart in one run:

    nested      the market object as `/events` returns it, already pinned by
                tests/fixtures/events_sports_nested.json, parsed by discovery.py
    single      the whole `/markets/{ticker}` payload, envelope included
    orderbook   the whole `/markets/{ticker}/orderbook` payload, envelope
                included

**The third one was added because the guess had already been made and was
wrong.** `KalshiRestClient.orderbook` read `payload["orderbook"]`; the wire key
is `orderbook_fp`, and the inner sides are `yes_dollars` / `no_dollars` rather
than `yes` / `no`. It returned an empty dict for every market on the exchange,
including one with 21,000 contracts of open interest and a two-sided quote. It
had no callers, which is the only reason it never cost anything.

A test then asserts the two carry the same quote fields. If Kalshi ever renames
one and not the other, that comparison fails instead of the order path quietly
refreshing from `None`.

Run:

    .venv\\Scripts\\python.exe scripts\\capture_market_fixture.py

Read-only. Places no orders and spends no odds credits.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import ConfigError, KalshiConfig          # noqa: E402
from backend.kalshi.discovery import classify_series          # noqa: E402
from backend.kalshi.rest import KalshiRestClient              # noqa: E402
from backend.logging_setup import configure_logging           # noqa: E402

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
OUT = FIXTURES / "market_single.json"


def _quotable(market: dict) -> bool:
    """A market with both bids readable, so the derived asks are both testable.

    Capturing a market quoted on one side only would produce a fixture where
    half the parser is exercised and the other half is asserted to be `None`,
    which is exactly the shape that hides a field rename.
    """
    return (
        market.get("yes_bid_dollars") not in (None, "", "0.0000")
        and market.get("no_bid_dollars") not in (None, "", "0.0000")
        and market.get("status") == "active"
    )


async def capture() -> int:
    configure_logging()

    try:
        config = KalshiConfig.load()
    except ConfigError as exc:
        print(f"cannot capture: {exc}")
        return 2

    async with KalshiRestClient(config) as api:
        # The scope filter is `classify_series` -- discovery's own classifier --
        # rather than a series-prefix match written here. The order path only
        # ever refreshes tickers that came through it, and a season prop shares
        # the prefix while passing a naive filter, so a prefix match would pin
        # the wire format of a market this code never reads. Measured: the
        # first two pages of `/events` were 400 non-game events.
        #
        # The generator paginates lazily, so breaking out stops the walk.
        nested: Optional[dict] = None
        event_ticker = ""
        scanned = 0
        async for event in api.events(with_nested_markets=True):
            scanned += 1
            info = classify_series(event)
            if not info.is_game_level or info.sport_key is None:
                continue
            for market in event.get("markets") or []:
                if _quotable(market):
                    nested = market
                    event_ticker = event.get("event_ticker") or ""
                    break
            if nested:
                break

        if nested is None:
            print(
                f"no active two-sided GAME market in {scanned} events. This is "
                f"a calendar fact, not a failure -- re-run during a slate. "
                f"Nothing was written."
            )
            return 1
        print(f"scanned {scanned} events")

        ticker = nested["ticker"]
        print(f"capturing {ticker} (event {event_ticker})")

        # The endpoint under test. Deliberately the raw payload, envelope
        # included: the envelope key is exactly the kind of thing that gets
        # guessed at, and a guess that returns `{}` reads as "no such market".
        single = await api.request("GET", f"/markets/{ticker}")

        # Same treatment, same reason. Captured from the same ticker seconds
        # later so the book and the summary fields describe one moment: a book
        # read minutes after its market row cannot be checked against it.
        orderbook = await api.request(
            "GET", f"/markets/{ticker}/orderbook", params={"depth": 10}
        )

    payload: dict[str, Any] = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "note": (
            "Verbatim API responses. `nested` is the market object as /events "
            "returns it; `single` is the whole /markets/{ticker} payload; "
            "`orderbook` is the whole /markets/{ticker}/orderbook payload. The "
            "order path refreshes quotes from `single`, and a test asserts the "
            "two agree field for field. The orderbook envelope is here because "
            "its key was guessed wrong -- `orderbook`, not `orderbook_fp` -- "
            "and the guess returned an empty book rather than an error."
        ),
        "ticker": ticker,
        "event_ticker": event_ticker,
        "nested": nested,
        "single": single,
        "orderbook": orderbook,
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    market = single.get("market") or {}
    print(f"wrote {OUT.relative_to(OUT.parents[2])}")
    print(f"  envelope keys : {sorted(single)}")
    print(f"  market keys   : {len(market)}")
    for field in (
        "ticker", "status", "yes_bid_dollars", "no_bid_dollars",
        "yes_ask_size_fp", "yes_bid_size_fp",
    ):
        print(
            f"  {field:<16} nested={nested.get(field)!r:<12} "
            f"single={market.get(field)!r}"
        )
    print(f"  orderbook envelope keys : {sorted(orderbook)}")
    for key, side in (orderbook.get("orderbook_fp") or {}).items():
        print(f"    {key:<12} {len(side or [])} levels, top={(side or [None])[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(capture()))
