"""Capture **settled** game markets as Kalshi actually returns them.

Why this exists as its own capture
----------------------------------
The paper settlement path has to read an outcome off `/markets/{ticker}`, and
the two fields it turns on are `status` and `result`. Every market in every
fixture this repo holds is `status: "active"` with `result: ""` — 247 of them,
counted 2026-08-08. So the settled shape has never been observed here, and a
parser written against it would be documentation-derived.

That is precisely the failure `tasks/lessons.md` records as the most expensive
one in the project's history: the WebSocket parser read 0 of 257 real frames
while seventeen tests passed, because every one of them fed it hand-written data
in the shape it expected. The rule that came out of it is in `CLAUDE.md` —
*wire-format tests load captured payloads, never hand-constructed ones* — and
the corollary is the ordering: **capture the payload before writing the parser,
not after the parser has tests.**

The specific things this is here to settle, none of which can be reasoned out:

- What `status` reads on a market whose outcome is known. `active` is the only
  value ever seen here; the settlement pass must not guess the rest.
- What `result` carries. An **active** market sends `""`, not null — so the
  empty case is a real string, and `if not result` would read a live market as
  a settled one. What a settled market sends is the open question.
- Whether a market can carry a `result` while still `active`, or a terminal
  `status` with an empty `result`. Those are the two states the pass must
  refuse rather than resolve, and they are only refusable if their shape is
  known.

`--series` defaults to the leagues in scope. Settled markets are found with a
**filtered** `/markets` query, which is not the blind pagination `CLAUDE.md`
forbids: that rule is about walking the whole endpoint, which returns ~99.8%
`KXMVE` combination tickers. A `series_ticker` + `status` filter asks a
question instead.

Run:

    .venv\\Scripts\\python.exe scripts\\capture_settled_markets.py

Read-only. Places no orders and spends no odds credits — Kalshi REST is
unmetered, and this touches nothing else.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import ConfigError, KalshiConfig          # noqa: E402
from backend.kalshi.rest import KalshiRestClient              # noqa: E402
from backend.logging_setup import configure_logging           # noqa: E402

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
OUT = FIXTURES / "markets_settled.json"

# The game series this project prices. Deliberately not "every series": the
# question is what a settled *game* market looks like, and a settled earnings
# market could differ without that being informative.
SERIES = (
    "KXMLBGAME",
    "KXWNBAGAME",
    "KXNFLGAME",
    "KXNCAAFGAME",
)

# Statuses worth asking for. Kalshi's documented lifecycle and its actual
# vocabulary have disagreed before in this repo, so each is *asked for* and the
# answer is recorded — including "this status returned nothing", which is itself
# a fact about the vocabulary.
STATUSES = ("settled", "finalized", "closed")

# Enough to see whether the shape is uniform without pulling a whole season.
PER_QUERY = 20


async def capture() -> int:
    configure_logging()
    try:
        config = KalshiConfig.load()
    except ConfigError as exc:
        print(f"Cannot reach Kalshi: {exc}", file=sys.stderr)
        return 2

    captured: list[dict[str, Any]] = []
    asked: list[dict[str, Any]] = []

    async with KalshiRestClient(config) as api:
        for series in SERIES:
            for status in STATUSES:
                try:
                    payload = await api.get(
                        "/markets",
                        series_ticker=series,
                        status=status,
                        limit=PER_QUERY,
                    )
                except Exception as exc:                      # noqa: BLE001
                    # Recorded rather than raised. "This status is not a word
                    # the API accepts" is one of the answers being looked for,
                    # and it must not stop the other queries.
                    asked.append(
                        {"series": series, "status": status, "error": str(exc)}
                    )
                    print(f"  {series} status={status}: {exc}")
                    continue

                markets = payload.get("markets") or []
                asked.append(
                    {"series": series, "status": status, "returned": len(markets)}
                )
                print(f"  {series} status={status}: {len(markets)} market(s)")
                captured.extend(markets)

    if not captured:
        # A finding, printed as one. It is a fact about today's exchange, not a
        # conclusion about the product -- the same distinction `lessons.md`
        # records under "a true measurement licensed a false conclusion".
        print(
            "\nNo settled game markets returned by any (series, status) pair.\n"
            "That is a statement about this query on this date, not about the\n"
            "exchange. Do NOT write the settlement parser against a guess --\n"
            "widen the series list or re-run when a slate has finished."
        )
        return 1

    statuses = Counter(m.get("status") for m in captured)
    results = Counter(repr(m.get("result")) for m in captured)

    print(f"\n{len(captured)} market(s) captured")
    print(f"  status: {dict(statuses)}")
    print(f"  result: {dict(results)}")

    # The two states the settlement pass has to refuse rather than resolve. Both
    # are counted here so the fixture's own contents say whether they occur,
    # rather than a test asserting they do not on data nobody looked at.
    settled_but_blank = [
        m["ticker"] for m in captured
        if m.get("status") in ("settled", "finalized") and not m.get("result")
    ]
    result_while_active = [
        m["ticker"] for m in captured
        if m.get("status") == "active" and m.get("result")
    ]
    print(f"  terminal status with empty result: {len(settled_but_blank)}")
    print(f"  result present while active:       {len(result_while_active)}")

    OUT.write_text(
        json.dumps(
            {
                "note": (
                    "Verbatim /markets responses filtered by series and status, "
                    "captured to pin the SETTLED wire shape. Every other fixture "
                    "in this repo holds only active markets (result == ''), so "
                    "without this the settlement parser would be written against "
                    "documentation. See scripts/capture_settled_markets.py."
                ),
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "queries": asked,
                "status_counts": {str(k): v for k, v in statuses.items()},
                "result_counts": {str(k): v for k, v in results.items()},
                "terminal_status_with_empty_result": settled_but_blank,
                "result_while_active": result_while_active,
                "markets": captured,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(capture()))
