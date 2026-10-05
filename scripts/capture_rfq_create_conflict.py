"""Capture the venue's raw reply to a SECOND RFQ create on the same combination.

    .venv\\Scripts\\python.exe scripts\\capture_rfq_create_conflict.py \\
        --ticker KXMVECROSSCATEGORY-... --capture data\\captures\\rfq_conflict

Why this exists (#318 follow-up)
--------------------------------
`create_rfq` (`backend/kalshi/rfq.py`) detects "one of ours is already open"
by finding the substring `already_exists` in the exception text, and no
RFQ-create 409 body had ever been captured -- the only `already_exists`
fixture is the ORDER path's. This asks once, then asks again with the
identical body, and keeps the second reply verbatim: status, body, URL.

What it asks, and why that is licensed
---------------------------------------
A sell-side ask sized in whole `contracts` floored from what is HELD, on a
combination in `/portfolio/positions` -- the same ask
`scripts/capture_sell_side_rfq.py` makes, authorised by Joe on #59 and #63
(A). **Asking commits nothing.** This module never imports the accept path.

Ordering
--------
- Refused before any write: an existing capture path, a ticker not held, a
  holding that floors to zero.
- If the FIRST create already meets a conflict, that reply is the capture
  and nothing is withdrawn: the open RFQ is not this script's, and a desk
  tab may be holding it with a confirm pending.
- Otherwise the second create's reply is the capture, written to disk, and
  then the RFQ this script created -- and only that one, by the id the venue
  returned -- is withdrawn in a `finally`.

Both POSTs go through `KalshiRestClient.request` directly, not `create_rfq`,
because `create_rfq` turns the reply into an exception and keeps only its
text. `request` does not retry a 409.

What this does not establish
----------------------------
One reply at one moment. Nothing about a 429, a 5xx, or whether the venue's
wording is stable; nothing about RFQs created outside this account.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import KalshiConfig  # noqa: E402
from backend.kalshi.rest import KalshiAPIError  # noqa: E402
from backend.kalshi.rfq import delete_rfq  # noqa: E402
from backend.logging_setup import configure_logging  # noqa: E402

from capture_sell_side_rfq import (  # noqa: E402
    Refused,
    floor_contracts,
    held_position_fp,
    legs_and_collection,
    refuse_if_exists,
)

RFQS_PATH = "/communications/rfqs"
SHARD = {"exchange_index": 1}


def _reply(exc: BaseException) -> dict:
    """The venue's reply as it arrived. Verbatim; nothing parsed away."""
    if isinstance(exc, KalshiAPIError):
        return {
            "kind": "KalshiAPIError",
            "status_code": exc.status_code,
            "url": exc.url,
            "body": exc.body,
            "earlier_attempt_lost": exc.earlier_attempt_lost,
        }
    return {"kind": type(exc).__name__, "repr": repr(exc)}


async def capture_conflict(api: Any, ticker: str, out_path: Path) -> dict:
    refuse_if_exists([out_path])
    position_fp = held_position_fp(await api.positions(), ticker)
    if position_fp is None:
        raise Refused(f"{ticker} is not among the account's open positions; not asked")
    contracts = floor_contracts(position_fp)
    if contracts < 1:
        raise Refused(f"{ticker}: position_fp {position_fp} floors to 0 contracts")
    collection, legs = legs_and_collection(await api.get(f"/markets/{ticker}"))
    body = {
        "market_ticker": ticker,
        "rest_remainder": False,
        "mve_collection_ticker": collection,
        "mve_selected_legs": legs,
        "contracts": contracts,
    }
    capture: dict[str, Any] = {
        "captured_ms": int(time.time() * 1000),
        "ticker": ticker,
        "request": f"POST /trade-api/v2{RFQS_PATH}?exchange_index=1",
        "request_body": body,
        "first_create": None,
        "second_create": None,
        "created_rfq_id": None,
        "deleted": False,
    }

    def _write() -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(capture, indent=2, sort_keys=True), encoding="utf-8")

    try:
        first = await api.request("POST", RFQS_PATH, params=dict(SHARD), json_body=body)
    except Exception as exc:  # noqa: BLE001 -- the reply IS the measurement
        capture["first_create"] = _reply(exc)
        _write()
        return capture
    capture["first_create"] = {"kind": "ok", "payload": first}
    rfq = first.get("rfq") if isinstance(first.get("rfq"), dict) else first
    created = rfq.get("id") or first.get("id")
    capture["created_rfq_id"] = created
    try:
        try:
            second = await api.request("POST", RFQS_PATH, params=dict(SHARD), json_body=body)
            capture["second_create"] = {"kind": "ok", "payload": second}
        except Exception as exc:  # noqa: BLE001 -- the reply IS the measurement
            capture["second_create"] = _reply(exc)
        _write()
    finally:
        if created:
            await delete_rfq(api, str(created))
            capture["deleted"] = True
        _write()
    return capture


async def _run(ticker: str, directory: Path) -> int:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out = directory / f"rfq_create_conflict_{stamp}.json"
    from backend.kalshi.rest import KalshiRestClient

    async with KalshiRestClient(KalshiConfig.load()) as api:
        try:
            capture = await capture_conflict(api, ticker, out)
        except Refused as exc:
            print(f"REFUSED -- {exc}")
            return 2
    for key in ("first_create", "second_create"):
        print(f"{key}: {json.dumps(capture[key])[:600]}")
    print(f"deleted own RFQ: {capture['deleted']}; wrote {out}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ticker", required=True, help="a held combination market ticker")
    parser.add_argument("--capture", type=Path, required=True, help="directory (gitignored data/)")
    args = parser.parse_args(argv)
    configure_logging()
    return asyncio.run(_run(args.ticker, args.capture))


if __name__ == "__main__":
    raise SystemExit(main())
