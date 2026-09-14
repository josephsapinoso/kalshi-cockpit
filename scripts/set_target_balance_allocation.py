"""Set (or read) the account's standing per-shard balance allocation.

Why this script exists
----------------------
**Kalshi's API refuses an order whose exchange shard is underfunded, and as of
2026-09-14 there is no way to fund a shard by hand.**

Measured today, in this order:

1. `kalshi.com/account/exchange-indexes` still loads, but it is now READ-ONLY:
   four balance cards and the "Disable balance management" toggle, then the
   footer. No transfer control anywhere on the page.
2. "Disable balance management" was OFF, i.e. automatic management ON, and the
   Combos shard still held one cent while the Default shard held the rest.
   So auto-management does not keep a shard funded AT REST.
3. `scripts/probe_resting_combo_order.py` posted a 1-contract GTC buy at 2c on
   a live `KXMVECROSSCATEGORY-SHARD1` combination, three times, spaced. All
   three came back **400 `insufficient_balance`** -- with money in the account
   and auto-management on.

Kalshi's own docs say why: *"Kalshi's collateralization checks will continue to
run within the matching engine. Programmatic traders must preallocate
collateral on a given exchange shard before order placement."* The website
performs a just-in-time transfer before submitting; an API client gets the
matching engine's unvarnished check.

That leaves exactly one documented mechanism a programmatic trader can use, and
it is this one: a **standing target allocation**. You declare what share of the
balance belongs on each shard; every 10 seconds Kalshi computes each shard's
balance (minus the value of resting orders) and transfers to restore the
target. It is a SETTING, applied continuously -- not a per-order transfer.

**That distinction is the whole reason this script is allowed to exist.**
`docs/adr/0084-a-combination-is-bought-by-becoming-the-offer.md` ruled the desk
does not move money between shards, citing Kalshi's warning that a cross-shard
transfer "run[s] in up to three non-atomic steps" whose completed steps are not
undone on failure -- i.e. a failed transfer can strand funds. That warning is
about `intra_exchange_instance_transfer`, which this script does NOT call. A
target allocation is declarative, idempotent, and reversible by setting it
back; the venue owns the retry.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **That the rebalancer actually runs, or how fast.** The 10-second cadence is
  documented, not measured here. `--read` after a wait is how you check.
- **That a shard reaching its target makes an order payable.** Collateral is
  balance minus resting-order value; this script reads the former only.
- **Anything about shard 3.** This account has returned `user_not_found` there
  (2026-08-30), which is a provisioning failure, not a funding one, and an
  allocation naming it may behave differently.
- **That any of this is a good idea for a different operator.** The split is
  typed by the person running it.

Every raw response is written to `data/captures/`, which is gitignored:
balances are operator data and operator data never enters the repo (Joe's
ruling, 2026-08-20).

    python scripts/set_target_balance_allocation.py --read
    python scripts/set_target_balance_allocation.py --allocate 0=80,1=20 \\
        --i-am-joe-and-this-moves-money
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
from backend.kalshi.rest import KalshiRestClient              # noqa: E402
from backend.logging_setup import configure_logging           # noqa: E402

#: The flag, spelled once. A target allocation causes the venue to move real
#: money on a 10-second clock, so it is acknowledged the same way an order is.
MOVE_FLAG = "--i-am-joe-and-this-moves-money"

ALLOCATION_PATH = "/portfolio/target_balance_allocation"
BALANCE_PATH = "/portfolio/balance"
TRANSFER_PATH = "/portfolio/intra_exchange_instance_transfer"

#: Kalshi's own unit on the transfer endpoint: hundredths of a cent.
#:
#: NOT this project's tenths (`core/prices.py`). $1.00 = 10,000 centicents =
#: 1,000 tenths, so the two differ by exactly 10 and a confusion between them
#: moves ten times too much or too little. Converted in one place, here.
CENTICENTS_PER_DOLLAR = 10_000

#: The instance side. `event_contract` is Predictions; `margined` is Perpetual
#: Futures. The account page exposes ONLY this axis -- which is why Joe saw
#: "transfer between predictions and perpetuals" and concluded funds could no
#: longer be moved between shards. The shard axis is the pair of optional
#: `*_exchange_shard` fields on this same call, and the UI simply does not
#: surface it. A same-side transfer (event_contract -> event_contract) across
#: two shards is the documented way to fund a shard.
INSTANCE_EVENT_CONTRACT = "event_contract"

EXIT_OK = 0
EXIT_REFUSED = 2


def capture_path() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "data" / "captures"
    out.mkdir(parents=True, exist_ok=True)
    return out / f"target_allocation_{stamp}.json"


class Capture:
    """Every response, written incrementally.

    Incrementally for `probe_resting_combo_order.py`'s reason: the run that
    must never lose its record is the one that changed something and then
    crashed, which is exactly the run where a final write never happens.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.records: list[dict[str, Any]] = []

    def add(self, record: dict[str, Any]) -> None:
        self.records.append(record)
        self.path.write_text(
            json.dumps(self.records, indent=2), encoding="utf-8"
        )


async def raw_request(
    api: KalshiRestClient,
    method: str,
    path: str,
    json_body: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """One signed request, returning status + full body, raising on nothing.

    Bypasses the client's helpers for `probe_resting_combo_order.py`'s reason:
    a capture must keep the whole error body, and must never retry over its
    own state-changing call.
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


def parse_allocation(text: str) -> list[dict[str, int]]:
    """`"0=80,1=20"` -> `[{exchange_index: 0, percent: 80}, ...]`.

    Refuses anything that does not total 100. The venue refuses it too, but a
    refusal here names the arithmetic instead of returning a 400, and a split
    that does not sum to 100 is far more likely a typo than an intention.
    """
    allocations: list[dict[str, int]] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise ValueError(f"{part!r} is not `index=percent`")
        index_text, percent_text = part.split("=", 1)
        allocations.append(
            {
                "exchange_index": int(index_text.strip()),
                "percent": int(percent_text.strip()),
            }
        )
    if not allocations:
        raise ValueError("no allocations given")
    total = sum(entry["percent"] for entry in allocations)
    if total != 100:
        raise ValueError(f"percents total {total}, not 100")
    return allocations


def print_breakdown(label: str, payload: Any) -> None:
    """The per-shard balances, if the payload carries them.

    Printed, never written to the repo. `balance_breakdown` rows carry
    `balance` as a 4dp dollar string, the shape `read_shard_funds` parses.
    """
    rows = payload.get("balance_breakdown") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        print(f"   {label}: no balance_breakdown in the payload")
        return
    parts = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        parts.append(f"shard {row.get('exchange_index')} ${row.get('balance')}")
    print(f"   {label}: " + ", ".join(parts))


async def transfer_between_shards(
    api: KalshiRestClient,
    capture: Capture,
    *,
    dollars: float,
    source_shard: int,
    destination_shard: int,
) -> int:
    """Move Predictions money from one exchange shard to another.

    **This is the call ADR 0084 declined to build into the DESK, and it is
    still not in the desk.** 0084's objection is Kalshi's own warning that a
    cross-shard transfer "run[s] in up to three non-atomic steps" whose
    completed steps are not undone on failure -- so an automatic, per-order
    transfer on the money path could strand funds with nobody watching. A
    one-off, operator-run, captured transfer is a different object: Joe types
    the amount, sees the before and after, and is present for the failure.

    The transfer is processed ASYNCHRONOUSLY: a 200 returns a `transfer_id`,
    not a moved balance. Read the balance again afterwards rather than
    trusting the response.
    """
    amount = int(round(dollars * CENTICENTS_PER_DOLLAR))
    if amount <= 0:
        print(f"   ${dollars:.2f} is not a positive amount")
        return EXIT_REFUSED

    before = await raw_request(api, "GET", BALANCE_PATH)
    capture.add({"step": "1_balance_before", **before})
    print_breakdown("balance before", before["body"])

    body = {
        "source": INSTANCE_EVENT_CONTRACT,
        "destination": INSTANCE_EVENT_CONTRACT,
        "amount": amount,
        "source_exchange_shard": source_shard,
        "destination_exchange_shard": destination_shard,
    }
    print(
        f"   about to MOVE ${dollars:.2f} ({amount} centicents) "
        f"from shard {source_shard} to shard {destination_shard}"
    )
    moved = await raw_request(api, "POST", TRANSFER_PATH, body)
    capture.add({"step": "2_transfer", **moved})
    print(f"   transfer: status {moved['status']}")
    print(f"   {json.dumps(moved['body'])}")
    if moved["status"] >= 400:
        return EXIT_REFUSED

    after = await raw_request(api, "GET", BALANCE_PATH)
    capture.add({"step": "3_balance_after", **after})
    print_breakdown("balance after", after["body"])
    print("   (the transfer is asynchronous -- an unchanged balance here is "
          "not yet a failure; read again in a few seconds)")
    return EXIT_OK


async def run(
    api: KalshiRestClient,
    capture: Capture,
    *,
    allocations: Optional[list[dict[str, int]]],
    reservation: str,
) -> int:
    # 1. What is set now. Read FIRST and unconditionally: if this comes back
    #    with a non-empty allocation, somebody (or some earlier run) already
    #    set one, and overwriting it without showing it would destroy a
    #    setting nobody recorded.
    current = await raw_request(api, "GET", ALLOCATION_PATH)
    capture.add({"step": "1_read_current", **current})
    print(f"   current allocation: status {current['status']}")
    print(f"   {json.dumps(current['body'])}")

    before = await raw_request(api, "GET", BALANCE_PATH)
    capture.add({"step": "2_balance_before", **before})
    print_breakdown("balance before", before["body"])

    if allocations is None:
        return EXIT_OK if current["status"] < 400 else EXIT_REFUSED

    body = {"allocations": allocations, "resting_margin_reservation": reservation}
    print(f"   about to SET: {json.dumps(body)}")
    written = await raw_request(api, "POST", ALLOCATION_PATH, body)
    capture.add({"step": "3_set", **written})
    print(f"   set: status {written['status']}")
    if written["status"] >= 400:
        print(f"   the venue refused: {json.dumps(written['body'])}")
        return EXIT_REFUSED

    # 4. Read it back. A 200 says the venue accepted the call; the GET says
    #    what it actually stored, and those are different claims.
    confirmed = await raw_request(api, "GET", ALLOCATION_PATH)
    capture.add({"step": "4_read_back", **confirmed})
    print(f"   read back: {json.dumps(confirmed['body'])}")

    # 5. The balance will NOT have moved yet -- the rebalancer runs on its own
    #    10-second clock and the transfer it issues is asynchronous. A shard
    #    still reading zero here is expected, not a failure.
    after = await raw_request(api, "GET", BALANCE_PATH)
    capture.add({"step": "5_balance_after", **after})
    print_breakdown("balance immediately after", after["body"])
    print("   (the rebalancer runs on its own ~10s clock and its transfer is "
          "asynchronous, so an unchanged balance here is expected)")
    return EXIT_OK


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read or set the per-shard target balance allocation."
    )
    parser.add_argument(
        MOVE_FLAG, dest="move_acknowledged", action="store_true",
        help="required to SET. The venue will move real money to match.",
    )
    parser.add_argument(
        "--read", action="store_true",
        help="read the current allocation and per-shard balances, change "
             "nothing. Always safe.",
    )
    parser.add_argument(
        "--allocate",
        help="the split, as `index=percent` pairs totalling 100, e.g. "
             "`0=80,1=20`. An EMPTY string disables automatic rebalancing.",
    )
    parser.add_argument(
        "--reservation", default="sum", choices=["sum", "max"],
        help="how resting orders reserve margin (default: sum).",
    )
    parser.add_argument(
        "--transfer", type=float, metavar="DOLLARS",
        help="move this many dollars of Predictions money between shards. "
             "Needs --from-shard and --to-shard.",
    )
    parser.add_argument("--from-shard", type=int, help="source exchange shard")
    parser.add_argument("--to-shard", type=int, help="destination exchange shard")
    return parser.parse_args(argv)


async def amain(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    configure_logging()

    if not args.read and args.allocate is None and args.transfer is None:
        print("Nothing to do. Pass --read, --allocate 0=80,1=20, or "
              "--transfer 5 --from-shard 0 --to-shard 1.")
        return EXIT_REFUSED

    if args.transfer is not None:
        if args.from_shard is None or args.to_shard is None:
            print("--transfer needs --from-shard and --to-shard.")
            return EXIT_REFUSED
        if args.from_shard == args.to_shard:
            print("--from-shard and --to-shard are the same shard.")
            return EXIT_REFUSED
        if not args.move_acknowledged:
            print(f"This moves real money. Re-run with {MOVE_FLAG}.")
            return EXIT_REFUSED
        config = KalshiConfig.load()
        capture = Capture(capture_path())
        print(f"capture -> {capture.path}")
        try:
            async with KalshiRestClient(config) as api:
                return await transfer_between_shards(
                    api, capture,
                    dollars=args.transfer,
                    source_shard=args.from_shard,
                    destination_shard=args.to_shard,
                )
        finally:
            print(f"\ncapture written to {capture.path}")

    allocations: Optional[list[dict[str, int]]] = None
    if args.allocate is not None:
        if not args.move_acknowledged:
            print(f"This makes Kalshi move real money. Re-run with {MOVE_FLAG}.")
            return EXIT_REFUSED
        if args.allocate.strip() == "":
            allocations = []          # documented: empty disables rebalancing
        else:
            try:
                allocations = parse_allocation(args.allocate)
            except ValueError as exc:
                print(f"--allocate is not usable: {exc}")
                return EXIT_REFUSED

    config = KalshiConfig.load()
    capture = Capture(capture_path())
    print(f"capture -> {capture.path}")
    try:
        async with KalshiRestClient(config) as api:
            return await run(
                api, capture,
                allocations=allocations,
                reservation=args.reservation,
            )
    finally:
        print(f"\ncapture written to {capture.path}")


def main(argv: Optional[list[str]] = None) -> int:
    return asyncio.run(amain(argv))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
