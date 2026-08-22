"""The C0 probe: capture Kalshi's real V2 create-order response, verbatim.

Why this script exists
----------------------
`backend/kalshi/orders.py:_read_response` was transcribed from Kalshi's
published OpenAPI spec and **has never seen a real payload** -- no order has
ever been placed by this project (`ORDERS_ARE_DRY_RUNS = True`). This venue has
renamed wire fields out from under a spec-transcribed parser three times
(`data["yes"]` vs `yes_dollars_fp`, `multivariate_event_collections` vs
`multivariate_contracts`, `orderbook` vs `orderbook_fp`), so the `_fp` /
`_dollars` conventions on the create-order response are a guess until observed.
ADR 0063 makes observing it a blocking prerequisite for the manual-order path:
one `unrecognised_response` order would permanently occupy the exposure budget.

So this script spends a deliberately bounded few cents to observe four shapes:

  1. **non-fill**   -- limit IOC buy of 1 contract at 1c. Worst case ~$0.01+fee.
  2. **duplicate**  -- the identical request re-sent with the SAME
                       client_order_id, immediately. What does idempotency
                       return? Worst case: Kalshi treats it as new, ~$0.01+fee.
  3. **fill**       -- limit IOC buy of 1 contract at the current derived ask,
                       REFUSED unless that ask is <= 10c. Worst case $0.10+fee.
  4. **rest+cancel** -- limit GTC buy at 1c, then DELETE it. Worst case: it
                       fills at 1c before the cancel, ~$0.01+fee.

Every raw HTTP response -- status and full body, expected or not -- is written
to `data/captures/create_order_probe_<UTC-timestamp>.json`. `data/` is
gitignored (verified: `git check-ignore data/captures` matches `.gitignore`'s
`data/` rule), because a capture from a real account is operator data and
operator data never enters the repo. Synthetic fixtures are hand-written from
the observed shape afterwards, per the MLB/ADR 0035 precedent.

Who runs it
-----------
**Joe, and only Joe.** It spends real money on the live venue, so it refuses
to run unless BOTH of these hold:

  - the `--i-am-joe-and-this-spends-money` flag is passed, and
  - the environment is the live instance (`INSTANCE_MODE=live`, derived the
    same way `AppConfig.load` derives it -- `backend/config.py:926` -- with
    demo as the default) with a usable Kalshi credential
    (`KalshiConfig.load()` succeeds).

The whole `AppConfig.load()` is deliberately NOT called: its live-mode
invariants (APP_AUTH_TOKEN, a public COCKPIT_BASE_URL) guard the cockpit
*server*, and refusing a laptop probe because a Discord deep-link base URL is
loopback would be a false refusal. The probe needs exactly two facts -- which
instance this is, and whether the Kalshi credential loads -- and checks
exactly those.

Why it does not go through `KalshiRestClient.post`
--------------------------------------------------
The request/auth machinery is reused (`KalshiAuth`, `signed_path`, the one
shared `httpx.AsyncClient` owned by `KalshiRestClient`), but the order POSTs
are sent directly on that client rather than through `.post()`, for two
reasons that only matter to a capture instrument: `.post()` raises
`KalshiAPIError` on any non-2xx with the body **truncated to 500 bytes**, and
it silently retries 429/5xx. Here the surprise IS the data -- a 400 body must
be captured whole and a retry would overwrite the first observation. Reads
(market, orderbook) still go through the client's own methods.

What this script does NOT establish
-----------------------------------
- **That the observed shapes generalise.** One ticker, one day, one series.
  A field observed here can still be absent on another series or after the
  next API revision; the parser must keep refusing loudly on a miss.
- **The fee model.** At most two fills at extreme prices (1c / <=10c); that
  pins nothing about the coefficient or rounding that the 54 settlements have
  not already pinned better.
- **Which endpoint cancels a V2 order.** No cancel has ever been observed
  either, so probe 4 *probes* the cancel path (V2-shaped first, legacy on
  404/405) and captures whatever comes back. A failed cancel is a finding,
  not an error -- the runbook says to cancel the 1c order in the Kalshi app.
- **That a duplicate client_order_id is always safe.** One observation of the
  duplicate behaviour, on one endpoint, minutes apart. Not a licence to
  retry blindly.
- **Anything about settlement or H4.** Nothing here reads a settlement.
- **That the parser is correct.** This produces the payload against which
  synthetic fixtures will be hand-written; verifying the parser against them
  is a separate step with its own tests.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import ConfigError, KalshiConfig                # noqa: E402
from backend.core.prices import complement, dollars_to_tenths       # noqa: E402
from backend.kalshi.auth import signed_path                         # noqa: E402
from backend.kalshi.grid import GridUnavailable, parse_price_grid   # noqa: E402
from backend.kalshi.orders import (                                 # noqa: E402
    ORDERS_PATH,
    OrderRefused,
    OrderRequest,
)
from backend.kalshi.rest import ORDERBOOK_KEY, KalshiRestClient     # noqa: E402
from backend.logging_setup import configure_logging                 # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CAPTURES_DIR = ROOT / "data" / "captures"

# The flag, spelled once. argparse turns the dashes into underscores.
SPEND_FLAG = "--i-am-joe-and-this-spends-money"

# Probe prices, in the project's canonical integer tenths of a cent.
ONE_CENT_TENTHS = 10
# The fill probe's cap on the derived ask: 10c. Above this the probe REFUSES,
# so the worst case of the only probe meant to fill stays <= $0.10 + fee.
MAX_FILL_ASK_TENTHS = 100

# The legacy cancel path, tried only if the V2-shaped one 404s/405s. No cancel
# has ever been observed by this project; both attempts are captures.
LEGACY_ORDERS_PATH = "/portfolio/orders"

EXIT_OK = 0
EXIT_REFUSED = 2


# --------------------------------------------------------------------------
# Refusal logic. Pure, so tests drive every branch with no network and no env.
# --------------------------------------------------------------------------

def refusal_reason(
    *, acknowledged: bool, instance_mode: str, kalshi_key_configured: bool
) -> Optional[str]:
    """Why this run must not proceed, or None when it may.

    Ordered so the first missing precondition is the one named: the flag is
    an act of intent and is checked before anything about the environment.
    """
    if not acknowledged:
        return (
            f"the {SPEND_FLAG} flag was not passed. This script places real "
            f"orders on the live venue and is run by Joe himself, never by "
            f"an agent (ADR 0063). Nothing was sent."
        )
    if instance_mode != "live":
        return (
            f"INSTANCE_MODE={instance_mode!r} is not 'live'. The demo "
            f"instance holds no credentials and no execution path, and a "
            f"probe that spends money must never be one config default away "
            f"from running against the wrong environment. Set "
            f"INSTANCE_MODE=live explicitly. Nothing was sent."
        )
    if not kalshi_key_configured:
        return (
            "no usable Kalshi credential: KalshiConfig.load() failed. Set "
            "KALSHI_API_KEY and KALSHI_PRIVATE_KEY_PATH (see .env.example). "
            "Nothing was sent."
        )
    return None


def fill_ask_refusal(ask_tenths: Optional[int]) -> Optional[str]:
    """Why the fill probe must not run against this ask, or None.

    `None` in means no derived ask exists (nobody bids the opposing side), and
    that refuses rather than defaulting -- an unreadable ask is not a cheap
    one.
    """
    if ask_tenths is None:
        return (
            "no derived ask on this side (no resting bid on the opposing "
            "side). An IOC buy would be a shot at an empty book, and there "
            "is no price to cap. Fill probe refused."
        )
    if ask_tenths > MAX_FILL_ASK_TENTHS:
        return (
            f"the derived ask is {ask_tenths / 10:.1f}c, above the "
            f"{MAX_FILL_ASK_TENTHS / 10:.0f}c cap. The fill probe's worst "
            f"case must stay <= $0.10 + fee; pick a market where your side "
            f"is cheap. Fill probe refused."
        )
    return None


# --------------------------------------------------------------------------
# The capture record
# --------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Capture:
    """Every observation of the run, written to one file no matter what."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def add(self, record: dict[str, Any]) -> None:
        record.setdefault("recorded_at", _now_iso())
        self.records.append(record)

    def write(self, path: Path) -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "note": (
                "Verbatim create-order probe captures (C0). Raw wire "
                "responses from a real account: NEVER commit this file. "
                "Synthetic fixtures are hand-written from these shapes "
                "(ADR 0035 precedent)."
            ),
            "script": "scripts/probe_create_order.py",
            "written_at": _now_iso(),
            "records": self.records,
        }
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        return hashlib.sha256(path.read_bytes()).hexdigest()


async def raw_request(
    api: KalshiRestClient,
    method: str,
    path: str,
    json_body: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """One signed request, returning status + full body, raising on nothing.

    Signed with the same `KalshiAuth`/`signed_path` machinery every other
    request uses, sent on the client's one shared `httpx.AsyncClient`. See the
    module docstring for why this bypasses `KalshiRestClient.post`: a capture
    must keep the whole error body and must not retry over its own data.
    """
    # Polite spacing well under Kalshi's rate limit; this bypasses the
    # client's internal limiter along with its retry loop.
    await asyncio.sleep(0.25)
    headers = api.auth.get_rest_headers(method, signed_path(api.base_url, path))
    response = await api.client.request(
        method, f"{api.base_url}{path}", headers=headers, json=json_body
    )
    try:
        body: Any = response.json()
        body_is_json = True
    except ValueError:
        body = response.text
        body_is_json = False
    return {
        "method": method,
        "path": path,
        "request_body": json_body,
        "status": response.status_code,
        "body_is_json": body_is_json,
        "body": body,
    }


# --------------------------------------------------------------------------
# Orderbook display
# --------------------------------------------------------------------------

def _best_bid_tenths(levels: Any) -> Optional[int]:
    """The best (highest) bid on one side of the book, in tenths, or None.

    Levels are `[price_string, size_string]` pairs. Unreadable prices are
    skipped rather than defaulted; an empty or fully unreadable side is None.
    """
    best: Optional[int] = None
    for level in levels or []:
        try:
            price = dollars_to_tenths(level[0])
        except (TypeError, IndexError):
            price = None
        if price is not None and (best is None or price > best):
            best = price
    return best


def describe_book(book: dict[str, Any]) -> dict[str, Optional[int]]:
    """Print the book and return the derived asks for both sides, in tenths.

    The book publishes YES bids and NO bids only; each side's ask is the
    complement of the opposing bid (`derive_yes_ask` in `store/db.py` is the
    same identity).
    """
    yes_levels = book.get("yes_dollars") or []
    no_levels = book.get("no_dollars") or []
    print(f"  YES bids ({len(yes_levels)} levels): {yes_levels[:5]}")
    print(f"  NO  bids ({len(no_levels)} levels): {no_levels[:5]}")

    best_yes_bid = _best_bid_tenths(yes_levels)
    best_no_bid = _best_bid_tenths(no_levels)
    yes_ask = complement(best_no_bid) if best_no_bid is not None else None
    no_ask = complement(best_yes_bid) if best_yes_bid is not None else None

    def _fmt(tenths: Optional[int]) -> str:
        return f"{tenths / 10:.1f}c" if tenths is not None else "NONE"

    print(f"  best YES bid {_fmt(best_yes_bid)}   derived YES ask {_fmt(yes_ask)}")
    print(f"  best NO  bid {_fmt(best_no_bid)}   derived NO  ask {_fmt(no_ask)}")
    return {"yes": yes_ask, "no": no_ask}


# --------------------------------------------------------------------------
# The probes
# --------------------------------------------------------------------------

def announce(probe: str, request: OrderRequest) -> None:
    """Say exactly what is about to be sent, and its worst case, before it is."""
    print()
    print(f"-- {probe} " + "-" * max(1, 66 - len(probe)))
    print(
        f"   about to POST {ORDERS_PATH}: {request.action} {request.count} "
        f"{request.side.upper()} {request.ticker} @ "
        f"{request.limit_price_tenths / 10:.1f}c limit "
        f"({request.time_in_force}), client_order_id={request.client_order_id}"
    )
    print(
        f"   worst case if it fills completely: "
        f"${request.worst_case_cost_dollars:.4f} (stake + taker fee)"
    )


async def run_probes(
    api: KalshiRestClient,
    args: argparse.Namespace,
    capture: Capture,
) -> None:
    ticker = args.ticker

    # -- context reads: the market (for its price grid) and the book ---------
    market_payload = await api.get(f"/markets/{ticker}")
    capture.add({
        "probe": "context_market",
        "method": "GET",
        "path": f"/markets/{ticker}",
        "status": 200,
        "body": market_payload,
    })
    market = market_payload.get("market")
    if not isinstance(market, dict):
        raise SystemExit(
            f"GET /markets/{ticker} has no 'market' object "
            f"(got keys {sorted(market_payload)}). The envelope moved; "
            f"refusing to guess a price grid. Nothing was sent."
        )
    grid = parse_price_grid(
        market.get("price_ranges"),
        structure=market.get("price_level_structure"),
    )

    print(f"\nOrderbook for {ticker} (what you are probing against):")
    # The raw envelope is captured whole; the book itself is read off it the
    # way `KalshiRestClient.orderbook` does (raising on a renamed key would
    # abort the run here, before any money moves, which is correct).
    book_payload = await api.get(f"/markets/{ticker}/orderbook", depth=10)
    capture.add({
        "probe": "context_orderbook",
        "method": "GET",
        "path": f"/markets/{ticker}/orderbook",
        "status": 200,
        "body": book_payload,
    })
    book = book_payload.get(ORDERBOOK_KEY)
    if book is None:
        raise SystemExit(
            f"orderbook envelope has no {ORDERBOOK_KEY!r} key (got "
            f"{sorted(book_payload)}). The envelope moved; refusing to probe "
            f"a book that cannot be read. Nothing was sent."
        )
    asks = describe_book(book)
    side_ask = asks[args.side]

    # -- the plan, priced, before anything is sent ---------------------------
    print()
    print("Plan (side = buy %s):" % args.side.upper())
    steps: list[str] = []
    if not args.skip_shape:
        steps.append("1 non-fill: IOC 1 contract @ 1c")
    if not args.skip_duplicate:
        steps.append("2 duplicate: same body, SAME client_order_id")
    if not args.skip_fill:
        if side_ask is not None:
            steps.append(f"3 fill: IOC 1 contract @ derived ask ({side_ask / 10:.1f}c)")
        else:
            steps.append("3 fill: (will refuse -- no derived ask)")
    if not args.skip_cancel:
        steps.append("4 rest+cancel: GTC 1 contract @ 1c, then DELETE")
    for step in steps:
        print(f"  {step}")
    print(
        "\nWorst case for the whole run is under $0.14: two 1c orders "
        "($0.0107 each, fee included), one duplicate that Kalshi might treat "
        "as new ($0.0107), and one fill capped at 10c ($0.1063)."
    )
    confirmed = input(
        f"\nType the ticker ({ticker}) to send real orders, anything else "
        f"aborts: "
    ).strip()
    if confirmed != ticker:
        raise SystemExit("aborted at confirmation; nothing was sent.")

    shape_request: Optional[OrderRequest] = None

    # -- probe 1: non-fill shape --------------------------------------------
    if args.skip_shape:
        print("\n-- probe 1 (non-fill shape): SKIPPED by flag")
        capture.add({"probe": "1_nonfill_shape", "skipped": "flag"})
    else:
        try:
            shape_request = OrderRequest(
                ticker=ticker, side=args.side, action="buy", count=1,
                limit_price_tenths=ONE_CENT_TENTHS, price_grid=grid,
                time_in_force="immediate_or_cancel",
            )
        except (OrderRefused, GridUnavailable) as exc:
            print(f"\n-- probe 1 REFUSED before sending: {exc}")
            capture.add({"probe": "1_nonfill_shape", "refused": str(exc)})
        if shape_request is not None:
            announce("probe 1: non-fill shape", shape_request)
            record = await raw_request(
                api, "POST", ORDERS_PATH, shape_request.to_api_dict()
            )
            print(f"   status {record['status']}")
            capture.add({"probe": "1_nonfill_shape", **record})

    # -- probe 2: duplicate idempotency -------------------------------------
    if args.skip_duplicate:
        print("\n-- probe 2 (duplicate): SKIPPED by flag")
        capture.add({"probe": "2_duplicate", "skipped": "flag"})
    elif shape_request is None:
        print(
            "\n-- probe 2 (duplicate): SKIPPED -- it re-sends probe 1's exact "
            "body, and probe 1 did not run."
        )
        capture.add({"probe": "2_duplicate", "skipped": "probe 1 did not run"})
    else:
        print()
        print("-- probe 2: duplicate " + "-" * 46)
        print(
            f"   about to re-POST probe 1's EXACT body -- same "
            f"client_order_id={shape_request.client_order_id}. Worst case: "
            f"Kalshi ignores idempotency and charges another "
            f"${shape_request.worst_case_cost_dollars:.4f}."
        )
        record = await raw_request(
            api, "POST", ORDERS_PATH, shape_request.to_api_dict()
        )
        print(f"   status {record['status']}")
        capture.add({"probe": "2_duplicate", **record})

    # -- probe 3: fill shape -------------------------------------------------
    if args.skip_fill:
        print("\n-- probe 3 (fill shape): SKIPPED by flag")
        capture.add({"probe": "3_fill_shape", "skipped": "flag"})
    else:
        reason = fill_ask_refusal(side_ask)
        if reason is not None:
            print(f"\n-- probe 3 REFUSED: {reason}")
            capture.add({"probe": "3_fill_shape", "refused": reason})
        else:
            try:
                fill_request = OrderRequest(
                    ticker=ticker, side=args.side, action="buy", count=1,
                    limit_price_tenths=side_ask, price_grid=grid,
                    time_in_force="immediate_or_cancel",
                )
            except (OrderRefused, GridUnavailable) as exc:
                print(f"\n-- probe 3 REFUSED before sending: {exc}")
                capture.add({"probe": "3_fill_shape", "refused": str(exc)})
            else:
                announce("probe 3: fill shape", fill_request)
                record = await raw_request(
                    api, "POST", ORDERS_PATH, fill_request.to_api_dict()
                )
                print(f"   status {record['status']}")
                capture.add({"probe": "3_fill_shape", **record})

    # -- probe 4: resting + cancel ------------------------------------------
    if args.skip_cancel:
        print("\n-- probe 4 (rest+cancel): SKIPPED by flag")
        capture.add({"probe": "4_rest_and_cancel", "skipped": "flag"})
        return

    try:
        rest_request = OrderRequest(
            ticker=ticker, side=args.side, action="buy", count=1,
            limit_price_tenths=ONE_CENT_TENTHS, price_grid=grid,
            time_in_force="good_till_canceled",
        )
    except (OrderRefused, GridUnavailable) as exc:
        print(f"\n-- probe 4 REFUSED before sending: {exc}")
        capture.add({"probe": "4_rest_and_cancel", "refused": str(exc)})
        return

    announce("probe 4: rest + cancel", rest_request)
    record = await raw_request(api, "POST", ORDERS_PATH, rest_request.to_api_dict())
    print(f"   status {record['status']}")
    capture.add({"probe": "4_rest_and_cancel_create", **record})

    order_id = None
    if isinstance(record["body"], dict):
        order_id = record["body"].get("order_id")
    if not order_id:
        print(
            "   !! no 'order_id' in the create response -- THAT is a finding "
            "(the parser reads exactly this key). Cannot cancel by id: check "
            "/portfolio/orders in the Kalshi app and cancel the 1c order "
            "there."
        )
        capture.add({
            "probe": "4_rest_and_cancel_cancel",
            "skipped": "no order_id in create response",
        })
        return

    cancel_path = f"{ORDERS_PATH}/{order_id}"
    print(f"   about to DELETE {cancel_path} (cancels the resting 1c order)")
    cancel_record = await raw_request(api, "DELETE", cancel_path)
    print(f"   status {cancel_record['status']}")
    capture.add({"probe": "4_rest_and_cancel_cancel", **cancel_record})

    if cancel_record["status"] in (404, 405):
        # No cancel endpoint has ever been observed by this project; the
        # V2-shaped guess above may simply not exist. The legacy path is the
        # documented DELETE. Both attempts are captures either way.
        legacy_path = f"{LEGACY_ORDERS_PATH}/{order_id}"
        print(
            f"   V2-shaped cancel returned {cancel_record['status']}; trying "
            f"the legacy DELETE {legacy_path}"
        )
        legacy_record = await raw_request(api, "DELETE", legacy_path)
        print(f"   status {legacy_record['status']}")
        capture.add({"probe": "4_rest_and_cancel_cancel_legacy", **legacy_record})
        if legacy_record["status"] >= 400:
            print(
                "   !! neither cancel succeeded. The 1c order may still be "
                "resting: cancel it in the Kalshi app. Its worst case is a "
                "$0.01 fill."
            )


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture Kalshi's real V2 create-order responses (C0)."
    )
    parser.add_argument(
        SPEND_FLAG, dest="spend_acknowledged", action="store_true",
        help="required. This script places real orders with real money.",
    )
    parser.add_argument("--ticker", required=True, help="market ticker to probe")
    parser.add_argument(
        "--side", required=True, choices=("yes", "no"),
        help="which side the probe buys",
    )
    parser.add_argument("--skip-shape", action="store_true",
                        help="skip probe 1 (non-fill shape)")
    parser.add_argument("--skip-duplicate", action="store_true",
                        help="skip probe 2 (duplicate client_order_id)")
    parser.add_argument("--skip-fill", action="store_true",
                        help="skip probe 3 (fill at the ask)")
    parser.add_argument("--skip-cancel", action="store_true",
                        help="skip probe 4 (rest + cancel)")
    return parser.parse_args(argv)


async def main() -> int:
    configure_logging()
    args = parse_args()

    # Instance mode, derived the way AppConfig.load derives it (demo default).
    # See the module docstring for why the full AppConfig is not loaded.
    instance_mode = os.getenv("INSTANCE_MODE", "demo").strip().lower()

    kalshi_config: Optional[KalshiConfig] = None
    config_error = ""
    try:
        kalshi_config = KalshiConfig.load()
    except ConfigError as exc:
        config_error = f" ({exc})"

    reason = refusal_reason(
        acknowledged=args.spend_acknowledged,
        instance_mode=instance_mode,
        kalshi_key_configured=kalshi_config is not None,
    )
    if reason is not None:
        print(f"REFUSED: {reason}{config_error}", file=sys.stderr)
        return EXIT_REFUSED

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = CAPTURES_DIR / f"create_order_probe_{timestamp}.json"
    capture = Capture()

    try:
        async with KalshiRestClient(kalshi_config) as api:
            await run_probes(api, args, capture)
    finally:
        # The file is written even when a probe blows up mid-run: a partial
        # capture of a surprise is the point, not a casualty.
        if capture.records:
            sha = capture.write(out_path)
            print()
            print("=" * 70)
            print(f"capture written: {out_path}")
            print(f"SHA-256: {sha}")
            print(
                "Send back the SHA and the printed statuses. The capture "
                "file stays LOCAL -- data/ is gitignored and this file must "
                "never be committed; fixtures are hand-written from it."
            )
            print("=" * 70)
        else:
            print("\nno requests were made; nothing to write.")

    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
