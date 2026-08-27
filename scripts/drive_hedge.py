"""Drive the hedge surface end to end against the REAL Kalshi book.

    .venv\\Scripts\\python.exe scripts/drive_hedge.py

Not a test. This exists because `tasks/lessons.md` records, repeatedly, that
running the stack finds defects the suite does not -- the manual ticket's "YES
0c" on an empty combo book being the most recent, and the same-game defect this
script itself found being the reason ADR 0078 has a "Measured by running it"
section at all.

What it does:
  1. builds a scratch database at the current schema
  2. picks two markets the venue is quoting RIGHT NOW
  3. records a held ticket against them
  4. marks one leg won, which is what turns a de-risk into a lock
  5. reads the hedge payload and prints what a person would see

No order is placed and no odds credit is spent: the hedge path touches Kalshi
only, which is unmetered.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **It is not end-to-end over HTTP.** It drives `hedge.build_payload` directly,
  so it exercises neither the route, nor auth, nor serialisation to JSON over
  the wire. It is a reading of the payload *builder* against a real book. The
  served route is covered separately by `scripts/fetch_live_route.py`, which
  allowlists `/api/hedge`.
- **Nothing about a game that is actually running**, unless one happens to be.
  It picks whatever the venue is quoting two-sided at the moment it runs, and
  an out-of-play book prices differently from an in-play one.
- **Nothing about the alert reaching a phone.** It prints the ratchet key the
  notifier would use; it sends nothing.
- **Nothing repeatable.** The markets differ every run, so a green here is
  evidence that the path works against *a* real book on *a* day, not a
  regression test. Do not cite a figure from it without the date and tickers.

FOUR THINGS THAT WILL BITE A REWRITE
------------------------------------
Each was a defect hit while writing this, and each is invisible until it is:

1. **`api.events(...)` is an async generator, not a coroutine.** `await
   api.events(...)` raises "object async_generator can't be used in 'await'
   expression". It must be `async for`.
2. **Do not "simplify" the per-series walk back to `/events?status=open`.**
   That walk returns ZERO game markets in its first six pages -- 1,200 events,
   none in scope -- because the open walk is ~99.8% non-sports. That is
   CLAUDE.md's discovery-hygiene fact biting in practice.
3. **Bids must come through `build_market`, never raw dict keys.** Kalshi sends
   `yes_bid_dollars` as a dollar STRING and `no_ask_size` comes from
   `yes_bid_size_fp`. Reading `market["yes_bid"]` silently finds nothing and
   the script reports "no two-sided markets" while the venue is quoting.
4. **The DE-RISK branch pops `ladder` and prints the rest whole; the LOCK
   branch truncates.** That asymmetry is deliberate. A `[:3000]` slice over the
   de-risk block cuts off `chance_display` / `chance_refusal`, which is exactly
   where the same-game defect showed. Keep it or the script stops being able to
   show the thing it found.

Credentials are loaded from the main checkout's `.env` **by path** and never
copied. A secret that exists in one place stays auditable; a secret duplicated
for convenience is one somebody later commits.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

#: Defaults so the script is import-safe and runs from a normal checkout. The
#: env vars exist because it was written in a worktree that deliberately held
#: no `.env` of its own.
ROOT = Path(os.environ.get("REPO") or Path(__file__).resolve().parents[1]).resolve()
MAIN = Path(os.environ.get("MAIN_CHECKOUT") or ROOT).resolve()
SCRATCH = Path(os.environ.get("SCRATCH") or tempfile.gettempdir()).resolve()

sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

# `backend/config.py` calls `load_dotenv()` at import and would find nothing if
# this process runs outside the main checkout, so this has to happen first and
# has to reach `os.environ`.
load_dotenv(MAIN / ".env")
_key_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH")
if _key_path and not Path(_key_path).is_absolute():
    # Relative in the main checkout's `.env`, and this process may run elsewhere.
    os.environ["KALSHI_PRIVATE_KEY_PATH"] = str(MAIN / _key_path)

from backend import hedge  # noqa: E402
from backend.config import KalshiConfig  # noqa: E402
from backend.kalshi.quotes import LiveQuoteSource  # noqa: E402
from backend.kalshi.rest import KalshiRestClient  # noqa: E402
from backend.store import db  # noqa: E402

SERIES = ("KXMLBGAME", "KXNFLGAME", "KXNCAAFGAME", "KXWNBAGAME")


async def pick_markets(limit: int = 2):
    """Two open game markets with a two-sided book, read the way the recorder does.

    Walked per SERIES rather than over `/events?status=open` at large -- see
    trap 2 in the module docstring. Bids come through `build_market`, which owns
    the field names; this repo has been burned five times by parsers written
    against imagined wire formats.
    """
    import httpx

    from backend.kalshi.discovery import build_market

    config = KalshiConfig.load()
    picked = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        api = KalshiRestClient(config, client=client)
        for series in SERIES:
            seen = 0
            async for event in api.events(
                status="open",
                with_nested_markets=True,
                series_ticker=series,
                max_pages=2,
            ):
                for raw in event.get("markets", []) or []:
                    seen += 1
                    market = build_market(
                        raw,
                        market_type="binary",
                        event_ticker=event.get("event_ticker", ""),
                        series_ticker=series,
                    )
                    if market.yes_bid_tenths and market.no_bid_tenths:
                        picked.append(market)
                        if len(picked) >= limit:
                            print(f"  ({series}: {seen} markets scanned)")
                            return picked
            print(f"  ({series}: {seen} markets scanned, none two-sided)")
    return picked


async def main() -> int:
    scratch = SCRATCH / "drive_hedge.db"
    scratch.parent.mkdir(parents=True, exist_ok=True)
    if scratch.exists():
        scratch.unlink()
    conn = db.init_db(scratch)

    markets = await pick_markets()
    if len(markets) < 2:
        print("no two-sided markets available right now; nothing to drive")
        return 1
    for market in markets:
        print(
            f"  {market.ticker:<48} yes_bid={market.yes_bid_tenths} "
            f"no_bid={market.no_bid_tenths} yes_ask_size={market.yes_ask_size} "
            f"no_ask_size={market.no_ask_size} status={market.status}"
        )

    position_id = hedge.record_position(
        conn,
        now_ms=db.now_ms(),
        source="sportsbook",
        label="drive check",
        stake_tenths=5_000,  # $5.00
        return_tenths=100_000,  # $100.00
        legs=[
            {"ticker": markets[0].ticker, "side": "yes", "label": markets[0].title},
            {"ticker": markets[1].ticker, "side": "yes", "label": markets[1].title},
        ],
    )
    print(f"\nrecorded position {position_id}")

    source = LiveQuoteSource()
    try:
        print("\n--- DE-RISK: both legs live ---")
        payload = await hedge.build_payload(
            conn,
            now_ms=db.now_ms(),
            max_quote_age_ms=30_000,
            spendable_tenths=db.latest_balance_tenths(conn),
            fetch_quote=source.fetch,
        )
        # Trap 4: print this branch WHOLE, minus the ladder. Truncating it is
        # what would hide `chance_display` / `chance_refusal`.
        block = dict(payload["positions"][0]["hedge"])
        block.pop("ladder", None)
        print(json.dumps(block, indent=2))

        legs = hedge.legs_for(conn, position_id)
        hedge.resolve_leg(
            conn,
            leg_id=int(legs[1]["id"]),
            outcome="won",
            now_ms=db.now_ms(),
            source="manual",
        )
        print("\n--- LOCK: second leg marked won by hand ---")
        payload = await hedge.build_payload(
            conn,
            now_ms=db.now_ms(),
            max_quote_age_ms=30_000,
            spendable_tenths=db.latest_balance_tenths(conn),
            fetch_quote=source.fetch,
        )
        print(json.dumps(payload["positions"][0], indent=2)[:3000])

        # The alert's own view, without sending anything.
        from backend.notify.alerts import hedge_key

        print("\nratchet key:", hedge_key(payload["positions"][0]))
    finally:
        await source.aclose()
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
