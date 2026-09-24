"""Fire ONE sell-side RFQ on a combination Joe holds and keep every raw quote.

    .venv\\Scripts\\python.exe scripts\\capture_sell_side_rfq.py \\
        --ticker KXMVECROSSCATEGORY-... --capture data\\captures\\sell_side
    .venv\\Scripts\\python.exe scripts\\capture_sell_side_rfq.py \\
        --fixture data\\captures\\sell_side\\<capture>.json tests\\fixtures\\<out>.json

Why this exists (#129, and #96 defect 6 behind it)
---------------------------------------------------
Nothing committed can fire an RFQ or keep a raw quote payload: `read_quotes`
(`backend/kalshi/rfq.py`) parses the payload and discards it, and the only
caller of `create_rfq` is the buy-side route. The 2026-09-17 sell-side
measurement (`docs/measurements/2026-09-17-combinations-can-be-exited.md`)
was a throwaway script; ADR 0173 §1 records that it could not be re-derived
from anything the recorder kept and that one real quote was lost to console
truncation. The only committed RFQ fixture carries `yes_bid_dollars:
"0.0000"` on both quotes, so every non-zero YES bid this codebase has ever
tested against is hand-typed, against CLAUDE.md's wire-format rule.

This writes the payloads to disk **before** withdrawing the RFQ, which is the
one ordering that matters: deleting discards the quotes at the venue
immediately (`delete_rfq`'s own docstring) and there is no second read.

What it asks, and why that is licensed
---------------------------------------
An RFQ has no side field. You name a market and a size; makers answer with
both `yes_bid_dollars` (what they would PAY for YES -- the exit for a holder)
and `no_bid_dollars`. Sized in `contracts`, floored from `position_fp`, so the
request cannot be read as "I want to spend" and never exceeds what he holds.

**Asking commits nothing** (`create_rfq` docstring; ADR 0164). Sell-side asks
on held combinations were authorised by Joe on #59 (2026-09-17) and again in
#63 answer (A) (2026-09-18). This module never imports the accept path, and
`tests/test_capture_sell_side_rfq.py` pins that by reading this source.

Refusals, all before any venue write
------------------------------------
- A capture path that already exists: nothing runs. `--capture` and shell `>`
  both overwrite silently, and a lost capture is a lost measurement
  (`scripts/run_combo_exit_capture.py` learned this on the 2026-09-13 slots).
- A ticker not in `/portfolio/positions`: a sell-side ask on a combination he
  does not hold is not the measurement.
- A holding that floors to zero contracts: asking for one would ask for more
  than he holds.
- An RFQ of ours already open on the market: `create_rfq` would silently REUSE
  it (its `_is_reusable` returns True when no dollar target is wanted -- #96
  defect 4), and the quotes behind it were priced for that ask, not this one.
  Refused rather than deleted, because a desk tab may be holding it open with
  a confirm pending. **Detected from the venue's `409 already_exists` on the
  create, never from the RFQ list** -- measured 2026-09-24:
  `GET /communications/rfqs?market_ticker=` returns EVERY requester's RFQs on
  the market, `creator_id` blank on all of them, and `rfq_user_filter=self`
  is ignored there. A pre-check on that list refused all three held
  combinations because strangers were asking about them. The venue allows
  one live RFQ per market per requester, so its 409 is the only reliable
  "ours" signal; `create_rfq` then refuses a size-based ask (#96 defect 4)
  and this refuses in turn, without reading or deleting.

What this does not establish
----------------------------
One moment per run, on the tickers named; a count, never a rate. An exit
existing is not an exit being good: every measured bid on 2026-09-17 sat
below cost basis. Nothing is accepted and no money moves. A capture with no
YES bid is a fact about those makers at that instant, drawn from a held
combination -- say where the sample came from in the same sentence as the
result (`tasks/lessons.md` 2026-09-21 third).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.combo_rfq import QUOTE_POLL_S, QUOTE_WAIT_S  # noqa: E402
from backend.config import KalshiConfig  # noqa: E402
from backend.kalshi import rfq  # noqa: E402
from backend.kalshi.rfq import (  # noqa: E402
    RfqRefused,
    create_rfq,
    delete_rfq,
    parse_quotes,
)
from backend.logging_setup import configure_logging  # noqa: E402

QUOTES_PATH = "/communications/quotes"
QUOTES_PARAMS = {"rfq_user_filter": "self", "limit": 500}

#: Verbatim from `tests/fixtures/combo_rfq_quotes.json`, so the two fixtures
#: state the same rule in the same words.
REDACTION_NOTE = (
    "Every id below is a documented placeholder. `rfq_creator_id` and "
    "`rfq_creator_user_id` were Joe's own account identifiers and this repo "
    "is public -- operator data never enters the repo. The maker `creator_id` "
    "values identified third-party market participants and are replaced for "
    "the same reason. PRICES, QUANTITIES, TIMESTAMPS, FIELD NAMES AND "
    "STRUCTURE ARE VERBATIM, and they are what this fixture exists to pin."
)


class Refused(RuntimeError):
    """A pre-condition failed before any venue write. The message says which."""


# ---------------------------------------------------------------------------
# Pure helpers, each pinned by a test.
# ---------------------------------------------------------------------------


def floor_contracts(position_fp: Any) -> int:
    """`position_fp` (a fixed-point STRING like `'8.226'`) to whole contracts.

    **Floored, never rounded** (#96 defect 1): `8.226` asks for 8. Asking for
    9 would ask the makers to buy more than he holds. Unreadable resolves to
    a refusal, not to zero -- zero is a legitimate value with its own refusal.
    """
    try:
        value = Decimal(str(position_fp))
    except (InvalidOperation, ValueError) as exc:
        raise Refused(f"unreadable position_fp {position_fp!r}") from exc
    if value < 0:
        raise Refused(f"negative position_fp {position_fp!r}: a NO holding, not measured here")
    return int(math.floor(value))


def held_position_fp(rows: list[dict], ticker: str) -> Optional[str]:
    """The `position_fp` string for `ticker` among `/portfolio/positions` rows, or None.

    One implementation, shared with the exit route: `backend.kalshi.rfq`.
    """
    return rfq.held_position_fp(rows, ticker)


def legs_and_collection(market_payload: dict) -> tuple[str, list[dict]]:
    """`(mve_collection_ticker, mve_selected_legs)` off `GET /markets/{ticker}`.

    `backend.kalshi.rfq.mve_legs`, with its refusal in this script's type.
    """
    try:
        return rfq.mve_legs(market_payload)
    except RfqRefused as exc:
        raise Refused(str(exc)) from exc


def refuse_if_exists(paths: list[Path]) -> None:
    """Every target must be absent before anything runs. Names the blocker."""
    for path in paths:
        if path.exists():
            raise Refused(f"refusing to overwrite an existing capture: {path}")


def capture_path_for(directory: Path, ticker: str, now_ms: int) -> Path:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now_ms / 1000))
    return directory / f"sell_side_rfq_{ticker}_{stamp}.json"


def summarise_reads(reads: list[dict], rfq_id: str) -> dict:
    """Union quotes by id across every read (the same rule `await_quotes`
    uses -- a poll loop re-reads the same quote, so counts would multiply)."""
    seen: dict[str, dict] = {}
    too_fine: set[str] = set()
    unreadable: set[str] = set()
    for read in reads:
        parsed = parse_quotes(read["payload"], rfq_id=rfq_id)
        too_fine |= parsed.refused_finer_than_tenths
        unreadable |= parsed.refused_unreadable
        for quote in parsed.quotes:
            seen[quote.quote_id] = {
                "quote_id": quote.quote_id,
                "maker_id": quote.maker_id,
                "yes_bid_tenths": quote.yes_bid_tenths,
                "no_bid_tenths": quote.no_bid_tenths,
                "contracts": quote.contracts,
            }
    with_yes_bid = [q for q in seen.values() if q["yes_bid_tenths"] is not None]
    best = max((q["yes_bid_tenths"] for q in with_yes_bid), default=None)
    return {
        "quotes_seen": len(seen),
        "quotes_with_yes_bid": len(with_yes_bid),
        "best_yes_bid_tenths": best,
        "refused_finer_than_tenths": len(too_fine),
        "refused_unreadable": len(unreadable),
        "reads": len(reads),
    }


# ---------------------------------------------------------------------------
# The venue round-trip. `api` is duck-typed so a test can stand a fake in.
# ---------------------------------------------------------------------------


async def capture_one(
    api: Any,
    ticker: str,
    out_path: Path,
    *,
    now_ms: Optional[int] = None,
    wait_s: float = QUOTE_WAIT_S,
    poll_s: float = QUOTE_POLL_S,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict:
    """One RFQ, every raw read kept, written to `out_path`, then withdrawn.

    Every refusal happens before `create_rfq`. Once the RFQ exists the only
    exit is through the `finally`, which writes first and deletes second.
    """
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    refuse_if_exists([out_path])

    rows = await api.positions()
    position_fp = held_position_fp(rows, ticker)
    if position_fp is None:
        raise Refused(f"{ticker} is not among the account's open positions; not asked")
    contracts = floor_contracts(position_fp)
    if contracts < 1:
        raise Refused(
            f"{ticker}: position_fp {position_fp} floors to 0 contracts; asking "
            "for one would ask for more than is held"
        )

    market_payload = await api.get(f"/markets/{ticker}")
    collection, legs = legs_and_collection(market_payload)

    request_body = {
        "market_ticker": ticker,
        "rest_remainder": False,
        "mve_collection_ticker": collection,
        "mve_selected_legs": legs,
        "contracts": contracts,
    }
    capture: dict[str, Any] = {
        "captured_ms": now_ms,
        "ticker": ticker,
        "position_fp": position_fp,
        "contracts_asked": contracts,
        "rfq_created_by": "POST /trade-api/v2/communications/rfqs?exchange_index=1",
        "rfq_request_body": request_body,
        "quotes_endpoint": (
            "GET /trade-api/v2/communications/quotes"
            "?rfq_user_filter=self&limit=500"
        ),
        "rfq": None,
        "quote_reads": [],
        "summary": None,
        "accepted": False,
        "deleted": False,
    }

    try:
        handle = await create_rfq(
            api,
            market_ticker=ticker,
            collection_ticker=collection,
            legs=legs,
            contracts=contracts,
        )
    except RfqRefused as exc:
        # The venue said 409: one of ours was already open. `create_rfq`
        # refuses a size-based ask there rather than reusing (#96 defect 4)
        # -- its quotes were priced for another ask, and a desk tab may be
        # holding it with a confirm pending. No read, no delete, no file.
        raise Refused(f"{ticker}: {exc}. Not read, not deleted.") from exc
    capture["rfq"] = {
        "id": handle.rfq_id,
        "reused": handle.reused,
        "target_cost_dollars": handle.target_cost_dollars,
    }
    reads: list[dict] = capture["quote_reads"]
    try:
        # Our own row, verbatim, by id. The market-wide list cannot tell ours
        # from a stranger's (see the module docstring); this is the evidence
        # for what an own-RFQ row carries that the list does not. Best-effort.
        try:
            capture["rfq_row"] = await api.request("GET", f"/communications/rfqs/{handle.rfq_id}")
        except Exception as exc:  # noqa: BLE001 -- evidence, not the measurement
            capture["rfq_row"] = {"error": repr(exc)}
        deadline = clock() + wait_s
        while clock() < deadline:
            try:
                payload = await api.request("GET", QUOTES_PATH, params=dict(QUOTES_PARAMS))
                reads.append({"read_ms": int(time.time() * 1000), "payload": payload})
            except Exception as exc:  # noqa: BLE001 -- keep polling, the capture records it
                reads.append({"read_ms": int(time.time() * 1000), "error": repr(exc)})
            await sleep(poll_s)
    finally:
        # READ-then-WRITE-then-DELETE. The write sits before the delete on
        # purpose: the venue drops its copy of the quotes at delete
        # (`delete_rfq`'s docstring) and the disk copy is the only one left.
        capture["summary"] = summarise_reads(
            [r for r in reads if "payload" in r], handle.rfq_id
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(capture, indent=2, sort_keys=True), encoding="utf-8"
        )
        await delete_rfq(api, handle.rfq_id)
        capture["deleted"] = True
        out_path.write_text(
            json.dumps(capture, indent=2, sort_keys=True), encoding="utf-8"
        )
    return capture


# ---------------------------------------------------------------------------
# Capture -> committable fixture.
# ---------------------------------------------------------------------------


def redact_to_fixture(capture: dict, *, note: str) -> dict:
    """The envelope shape of `tests/fixtures/combo_rfq_quotes.json`, sell side.

    Quotes are unioned by id across reads and the LAST version of each is
    kept. Ids become documented placeholders; prices, quantities, timestamps,
    field names and structure are verbatim. A capture whose RFQ was reused
    is refused: its quotes were priced for another ask.
    """
    rfq = capture.get("rfq") or {}
    if rfq.get("reused"):
        raise Refused("capture reused an open RFQ; its quotes are not this ask's")
    rfq_id = rfq.get("id")
    if not rfq_id:
        raise Refused("capture carries no rfq id")
    latest: dict[str, dict] = {}
    for read in capture.get("quote_reads") or ():
        payload = read.get("payload") or {}
        for row in payload.get("quotes") or ():
            if row.get("rfq_id") != rfq_id or not row.get("id"):
                continue
            latest[str(row["id"])] = dict(row)
    if not latest:
        raise Refused("capture holds no quotes on its own RFQ; nothing to pin")

    makers: dict[str, str] = {}
    quotes = []
    for index, (_, row) in enumerate(sorted(latest.items())):
        maker = str(row.get("creator_id") or "")
        if maker not in makers:
            makers[maker] = f"MAKER_{chr(ord('A') + len(makers))}_REDACTED"
        row["id"] = f"QUOTE_{chr(ord('A') + index)}_REDACTED"
        row["creator_id"] = makers[maker]
        row["rfq_id"] = "RFQ_REDACTED"
        if "rfq_creator_id" in row:
            row["rfq_creator_id"] = "REQUESTER_REDACTED"
        if "rfq_creator_user_id" in row:
            row["rfq_creator_user_id"] = "REQUESTER_USER_REDACTED"
        quotes.append(row)

    request_body = dict(capture.get("rfq_request_body") or {})
    return {
        "endpoint": capture.get("quotes_endpoint"),
        "params": {
            **QUOTES_PARAMS,
            "rfq_created_by": capture.get("rfq_created_by"),
            "rfq_request_body": request_body,
        },
        "sell_side": True,
        "note": note,
        "redaction": REDACTION_NOTE,
        "quotes": quotes,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


async def _run_captures(tickers: list[str], directory: Path, dry_run: bool) -> int:
    now_ms = int(time.time() * 1000)
    targets = {t: capture_path_for(directory, t, now_ms) for t in tickers}
    refuse_if_exists(list(targets.values()))
    if dry_run:
        for ticker, path in targets.items():
            print(f"would ask {ticker} at its held size and write {path}")
        return 0
    config = KalshiConfig.load()
    from backend.kalshi.rest import KalshiRestClient

    exit_code = 0
    async with KalshiRestClient(config) as api:
        for ticker, path in targets.items():
            try:
                capture = await capture_one(api, ticker, path, now_ms=now_ms)
            except Refused as exc:
                print(f"{ticker}: REFUSED -- {exc}")
                exit_code = 2
                continue
            summary = capture["summary"]
            print(
                f"{ticker}: asked {capture['contracts_asked']} of "
                f"{capture['position_fp']} held; {summary['quotes_seen']} quotes "
                f"from {summary['reads']} reads, {summary['quotes_with_yes_bid']} "
                f"with a YES bid (best {summary['best_yes_bid_tenths']} tenths), "
                f"{summary['refused_finer_than_tenths']} finer than a tenth; "
                f"wrote {path}"
            )
    return exit_code


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ticker", action="append", default=[], help="combination market ticker held; repeatable")
    parser.add_argument("--capture", type=Path, default=None, help="directory for raw captures (gitignored data/)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--fixture", nargs=2, metavar=("CAPTURE", "OUT"), default=None,
                        help="redact CAPTURE into a committable fixture at OUT")
    parser.add_argument("--note", default=None, help="the fixture's `note` (required with --fixture)")
    args = parser.parse_args(argv)

    if args.fixture:
        if not args.note:
            parser.error("--fixture needs --note: say when, on what, and that nothing was accepted")
        capture_path, out_path = (Path(p) for p in args.fixture)
        refuse_if_exists([out_path])
        capture = json.loads(capture_path.read_text(encoding="utf-8"))
        fixture = redact_to_fixture(capture, note=args.note)
        out_path.write_text(json.dumps(fixture, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {out_path} ({len(fixture['quotes'])} quotes)")
        return 0

    if not args.ticker or args.capture is None:
        parser.error("--ticker (at least one) and --capture are required")
    configure_logging()
    try:
        return asyncio.run(_run_captures(args.ticker, args.capture, args.dry_run))
    except Refused as exc:
        print(f"REFUSED -- {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
