"""Does a KXMVE combination market accept a RESTING bid, and give it back?

Why this script exists
----------------------
Every real order this project has ever sent was immediate-or-cancel: it fills
against visible depth or it dies. That is unusable on a combination, because
**no combination book this repo has read had a resting YES bid -- 40 of 40**
(ADR 0012 section 5). There is no offer to hit, so the only way to buy one is
to become the offer: rest a limit bid at your price and wait.

The mechanism itself is already observed. The C0 probe on 2026-08-23 placed a
GTC order on `KXNCAAFGAME-26SEP03EIUMINN-EIU`, watched it rest with
`remaining 1.00`, and cancelled it with `DELETE /portfolio/events/orders/{id}`
-> 200, `reduced_by 1.00` (`docs/runbooks/c0-create-order-probe.md`). So the
create shape, the resting shape and the cancel path are all pinned as fixtures
already.

**What is NOT observed is any of it on a `KXMVE` combination**, and combinations
are demonstrably not ordinary markets here: they are minted on demand, their
books are empty on both sides at birth, their fee model is unverified (ADR
0046), and this venue has renamed wire fields out from under a spec three
times. Building a buy path on the assumption that a combination rests like a
football game is the "built but never called" failure with money attached.

So this asks one question, in four steps, for at most a few cents:

  1. read the combination's book (expected: empty on both sides)
  2. POST a GTC limit buy, 1 contract, at a price far below fair value
  3. read `/portfolio/orders` -- did it actually REST, with what status?
  4. DELETE it, and read the orders list again -- is it gone?

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **That a resting bid ever FILLS.** It is placed far below fair value
  precisely so it cannot. Whether anyone takes the other side of a combination
  at a fair price is the question the buy path exists to find out, and one
  cancelled order says nothing about it.
- **That combinations rest in general.** One market, one collection, one
  moment. `KXMVECROSSCATEGORY` is not every combination series.
- **Anything about fees.** Nothing fills here, so no `fee_actual` is observed,
  and ADR 0046's combination fee model stays unverified.
- **That a leg starting mid-order is handled.** The venue's behaviour when a
  combination's leg goes in-play while an order rests against it is exactly
  what the desk's auto-cancel-at-kickoff rule exists to avoid needing to know.

Every raw response -- status and full body -- is written to
`data/captures/`, which is gitignored: a capture from a real account is
operator data and operator data never enters the repo (Joe's ruling; the
MLB/ADR 0035 precedent). Synthetic fixtures are hand-written from the shape
afterwards.

    python scripts/probe_resting_combo_order.py --suggest
    python scripts/probe_resting_combo_order.py --ticker KXMVE... \\
        --i-am-joe-and-this-spends-money
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config import KalshiConfig                       # noqa: E402
from backend.kalshi.auth import signed_path                   # noqa: E402
from backend.kalshi.grid import parse_price_grid              # noqa: E402
from backend.kalshi.orders import ORDERS_PATH, OrderRequest   # noqa: E402
from backend.kalshi.rest import KalshiRestClient              # noqa: E402
from backend.logging_setup import configure_logging           # noqa: E402

# The flag, spelled once. argparse turns the dashes into underscores.
SPEND_FLAG = "--i-am-joe-and-this-spends-money"

#: Where the bid is placed, in the project's integer tenths of a cent.
#:
#: **Deliberately far below any plausible fair value.** A combination of three
#: legs at ~60% each is worth ~25c; a 2c bid is an order that cannot be taken
#: by anyone acting in their own interest, so the probe's worst case is a 2c
#: fill plus fee rather than a real position. It is not 1c because 1c is the
#: floor of the grid and an order AT the floor cannot be distinguished from one
#: the venue clamped there.
PROBE_BID_TENTHS = 20

#: An override, in tenths, for the one question a 2c bid could not reach.
#:
#: On 2026-08-30 the 2c bid came back `insufficient_balance` against a $21.41
#: account, because `balance_breakdown` splits that money per `exchange_index`
#: and the combination's bucket held $0.0100. A combination's grid is
#: `deci_cent`, so a bid INSIDE that penny is expressible -- and it separates
#: two hypotheses at once: if it rests, combinations accept resting bids AND
#: the buckets really do gate spending; if it is refused for balance again,
#: the bucket reading is wrong and something else is denying the order.
PROBE_BID_TENTHS_INSIDE_A_PENNY = 5

#: The combination prefix. A ticker without it is not what this probe is for,
#: and probing an ordinary market would re-run C0 rather than extend it.
COMBO_PREFIX = "KXMVE"

EXIT_OK = 0
EXIT_REFUSED = 2


def capture_path() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "data" / "captures"
    out.mkdir(parents=True, exist_ok=True)
    return out / f"resting_combo_probe_{stamp}.json"


class Capture:
    """Every response, written on the way out and again at the end.

    Written incrementally rather than at exit: the one outcome that must never
    be lost is a create that succeeded followed by a cancel that crashed, and
    that is exactly the run where a final write never happens.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.records: list[dict[str, Any]] = []

    def add(self, record: dict[str, Any]) -> None:
        self.records.append(record)
        self.path.write_text(
            json.dumps(self.records, indent=2, sort_keys=True), encoding="utf-8"
        )


async def raw_request(
    api: KalshiRestClient,
    method: str,
    path: str,
    json_body: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """One signed request, returning status + full body, raising on nothing.

    Bypasses `KalshiRestClient.post` for the reason the C0 probe does: a
    capture must keep the whole error body, and must never retry over its own
    order.
    """
    await asyncio.sleep(0.25)
    headers = api.auth.get_rest_headers(method, signed_path(api.base_url, path))
    response = await api.client.request(
        method, f"{api.base_url}{path}", headers=headers, json=json_body
    )
    try:
        body: Any = response.json()
    except ValueError:
        body = response.text
    return {
        "method": method,
        "path": path,
        "request": json_body,
        "status": response.status_code,
        "body": body,
    }


async def run_probe(
    api: KalshiRestClient,
    ticker: str,
    capture: Capture,
    bid_tenths: int = PROBE_BID_TENTHS,
) -> int:
    print(f"\n== combination {ticker}")

    # 1a. The market, for its PRICE GRID. Never assumed: ~25% of Kalshi
    #     markets tick in deci-cents, and an order off the grid rests forever
    #     or is rejected. `OrderRequest` refuses a `None` grid by construction.
    market_payload = await raw_request(api, "GET", f"/markets/{ticker}")
    capture.add({"step": "1a_market", **market_payload})
    body = market_payload["body"]
    market = body.get("market") if isinstance(body, dict) else None
    if not isinstance(market, dict):
        print(f"   GET /markets/{ticker} has no 'market' object. Refusing to "
              f"guess a price grid. Nothing was sent.")
        return EXIT_REFUSED
    grid = parse_price_grid(
        market.get("price_ranges"),
        structure=market.get("price_level_structure"),
    )

    # 1b. The book. Expected empty on both sides -- that is the whole reason
    #     this probe exists -- but read rather than assumed, because a book
    #     with a resting YES bid would make an ordinary IOC buy possible and
    #     this probe unnecessary.
    book = await raw_request(api, "GET", f"/markets/{ticker}/orderbook")
    capture.add({"step": "1b_orderbook", **book})
    print(f"   book: status {book['status']}")

    try:
        request = OrderRequest(
            ticker=ticker,
            side="yes",
            action="buy",
            count=1,
            limit_price_tenths=bid_tenths,
            price_grid=grid,
            time_in_force="good_till_canceled",
        )
    except Exception as exc:                                   # noqa: BLE001
        print(f"   REFUSED before sending: {exc}")
        capture.add({"step": "2_create", "refused": str(exc)})
        return EXIT_REFUSED

    print(
        f"   about to POST a RESTING buy: 1 contract @ "
        f"{bid_tenths / 10:.1f}c. Worst case if someone takes it: "
        f"~${bid_tenths / 1000:.3f} + fee."
    )
    created = await raw_request(api, "POST", ORDERS_PATH, request.to_api_dict())
    capture.add({"step": "2_create", **created})
    print(f"   create: status {created['status']}")
    if created["status"] >= 400:
        # **Read the code before drawing the conclusion.** The first run of
        # this probe printed "combinations refuse resting orders" over an
        # `insufficient_balance`, which is a statement about the wallet and
        # says nothing at all about combinations. A refusal is a finding only
        # once you know which refusal it is.
        code = ""
        if isinstance(created["body"], dict):
            code = (created["body"].get("error") or {}).get("code", "")
        if code == "insufficient_balance":
            print("   `insufficient_balance` -- this is the ACCOUNT, not the "
                  "market. Nothing was learned about whether a combination "
                  "accepts a resting bid. Check `balance_breakdown`: the "
                  "money may be in a different `exchange_index` than the one "
                  "this market trades on.")
        else:
            print(f"   the venue refused with `{code or created['status']}`. "
                  "Read the captured body before concluding anything about "
                  "combinations from it.")
        return EXIT_REFUSED

    order_id = None
    if isinstance(created["body"], dict):
        order_id = created["body"].get("order_id")

    # 3. Did it rest? A 201 says the venue accepted it; the orders list says
    #    whether it is actually working. Those are different claims and a
    #    combination is exactly where they might diverge.
    resting = await raw_request(api, "GET", f"/portfolio/orders?ticker={ticker}")
    capture.add({"step": "3_orders_after_create", **resting})
    print(f"   orders list: status {resting['status']}")

    if not order_id:
        print("   !! no 'order_id' in the create response -- a finding in "
              "itself. Cancel the 2c order in the Kalshi app.")
        return EXIT_REFUSED

    # 4. Give it back.
    cancelled = await raw_request(api, "DELETE", f"{ORDERS_PATH}/{order_id}")
    capture.add({"step": "4_cancel", **cancelled})
    print(f"   cancel: status {cancelled['status']}")
    if cancelled["status"] >= 400:
        print("   !! the cancel FAILED. The 2c order may still be resting -- "
              "cancel it in the Kalshi app.")

    after = await raw_request(api, "GET", f"/portfolio/orders?ticker={ticker}")
    capture.add({"step": "5_orders_after_cancel", **after})
    print(f"   orders after cancel: status {after['status']}")
    return EXIT_OK


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Does a KXMVE combination accept a resting bid?"
    )
    parser.add_argument(
        SPEND_FLAG, dest="spend_acknowledged", action="store_true",
        help="required. This places a real resting order with real money.",
    )
    parser.add_argument("--ticker", help="the KXMVE combination to probe")
    parser.add_argument(
        "--inside-a-penny", action="store_true",
        help=f"bid {PROBE_BID_TENTHS_INSIDE_A_PENNY / 10:.1f}c instead of "
             f"{PROBE_BID_TENTHS / 10:.1f}c, to fit inside a bucket holding "
             f"$0.01. Only meaningful on a deci-cent grid.",
    )
    parser.add_argument(
        "--allow-ordinary-market", action="store_true",
        help="permit a non-KXMVE ticker. The ONE reason this exists: on "
             "2026-08-30 the combination probe came back `insufficient_"
             "balance` on a 2c bid against a $21.41 account, and "
             "`balance_breakdown` splits that money across four "
             "`exchange_index` buckets with the combination's holding $0.01. "
             "Running the identical order on an ordinary market separates "
             "'this wallet cannot spend here' from 'combinations refuse "
             "resting orders', which no amount of re-reading the 400 can.",
    )
    return parser.parse_args(argv)


async def amain(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    configure_logging()

    if not args.ticker:
        print("--ticker is required. Get one from "
              "`inspect_live_db.py parlay-lookups-tail`.")
        return EXIT_REFUSED
    if not args.ticker.startswith(COMBO_PREFIX) and not args.allow_ordinary_market:
        print(f"{args.ticker} is not a {COMBO_PREFIX} combination. This probe "
              "is only for combinations; C0 already covered ordinary markets. "
              "Pass --allow-ordinary-market to isolate a balance refusal.")
        return EXIT_REFUSED
    if not args.spend_acknowledged:
        print(f"This places a REAL resting order. Re-run with {SPEND_FLAG}.")
        return EXIT_REFUSED

    config = KalshiConfig.load()
    capture = Capture(capture_path())
    print(f"capture -> {capture.path}")
    try:
        async with KalshiRestClient(config) as api:
            return await run_probe(
                api, args.ticker, capture,
                bid_tenths=(
                    PROBE_BID_TENTHS_INSIDE_A_PENNY if args.inside_a_penny
                    else PROBE_BID_TENTHS
                ),
            )
    finally:
        print(f"\ncapture written to {capture.path}")


def main(argv: Optional[list[str]] = None) -> int:
    return asyncio.run(amain(argv))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
