"""Capture a real Kalshi WebSocket order-book stream to tests/fixtures/.

Run:  python -m scripts.capture_ws_fixture [--seconds 90] [--tickers T1,T2]

Read-only. Subscribes, records, disconnects. Places nothing.

Late-add mode (#436):  python -m scripts.capture_ws_fixture --tickers A,B     --late-add C --out ws_orderbook_late_add.json

subscribes A and B, waits until at least one `orderbook_delta` has arrived and
`--late-after` seconds have passed, then sends the same per-ticker `subscribe`
`KalshiWebSocket.add_tickers` sends on an open connection. Every command sent
is recorded in `sent`, with its time, beside the frames, so a replay can
show the late subscribe went out while deltas were already flowing, and
whether a snapshot for C followed.

Why this fixture is the most important one in the repo
------------------------------------------------------
The predecessor project's `apply_snapshot` read `data["yes"]` while Kalshi sent
`yes_dollars_fp`. Every order book parsed to **zero levels**, silently, for the
project's entire life, while 305 synthetic tests passed — because every one of
those tests fed the parser the shape the parser expected.

`backend/kalshi/orderbook.py` currently raises `MalformedBookMessage` when it
cannot find the level arrays, which is better than returning an empty book. But
raising loudly on a shape you invented is not the same as being tested against
the shape Kalshi actually sends, and this project has been shipping the WebSocket
path on the second of those.

So this script records frames **verbatim, before any parsing**, straight off the
socket. What lands in the fixture is what Kalshi said, not what this codebase
believes Kalshi says — which is the only way the fixture can prove the parser
wrong rather than agree with it.

It records the raw JSON of every frame, in order, with the receive timestamp, so
a replay test can also exercise sequence-gap detection by deleting a frame from
the middle.
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import json
import ssl
import time
from pathlib import Path
from typing import Any, Optional

import certifi
import websockets

from backend.config import KalshiConfig
from backend.kalshi.auth import KalshiAuth
from backend.kalshi.rest import KalshiRestClient
from scripts.capture_envelope import request_envelope, write_capture

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"

# Series most likely to be live. MLB runs all summer; the others are here so the
# script still finds something in other months.
CANDIDATE_SERIES = [
    "KXMLBGAME", "KXNFLGAME", "KXWNBAGAME", "KXNBAGAME", "KXNHLGAME",
]


async def busiest_tickers(api: KalshiRestClient, limit: int) -> list[str]:
    """Pick the tickers most likely to actually tick.

    Ranked by 24-hour volume: an order book that never updates produces a
    fixture with one snapshot and no deltas, which tests nothing about the
    delta path or about sequencing.
    """
    scored: list[tuple[float, str]] = []
    for series in CANDIDATE_SERIES:
        try:
            response = await api.request(
                "GET", "/events",
                params={
                    "series_ticker": series, "status": "open",
                    "with_nested_markets": "true", "limit": 200,
                },
            )
        except Exception as exc:                      # noqa: BLE001
            print(f"  {series}: {type(exc).__name__} {str(exc)[:80]}")
            continue

        for event in response.get("events", []):
            for market in event.get("markets", []):
                ticker = market.get("ticker")
                if not ticker:
                    continue
                volume = market.get("volume_24h_fp") or market.get("volume_fp") or 0
                try:
                    volume = float(volume)
                except (TypeError, ValueError):
                    volume = 0.0
                scored.append((volume, ticker))

        if scored:
            print(f"  {series}: {len(scored)} markets so far")

    scored.sort(reverse=True)
    chosen = [ticker for _, ticker in scored[:limit]]
    if scored:
        print(f"  top volume: {scored[0][0]:,.0f} on {scored[0][1]}")
    return chosen


async def capture(
    config: KalshiConfig,
    tickers: list[str],
    seconds: float,
    late_add: Optional[str] = None,
    late_after: float = 10.0,
) -> dict:
    auth = KalshiAuth(config.api_key, config.private_key_path)
    headers = auth.get_ws_headers()

    frames: list[dict[str, Any]] = []
    sent: list[dict[str, Any]] = []
    counts: collections.Counter = collections.Counter()
    started = time.time()

    context = ssl.create_default_context(cafile=certifi.where())
    async with websockets.connect(
        config.ws_url, additional_headers=headers, ssl=context,
        open_timeout=20, close_timeout=5,
    ) as socket:
        async def subscribe(command_id: int, ticker: str) -> None:
            command = {
                "id": command_id,
                "cmd": "subscribe",
                "params": {"channels": ["orderbook_delta"], "market_tickers": [ticker]},
            }
            await socket.send(json.dumps(command))
            sent.append({"sent_ms": int(time.time() * 1000), "command": command})

        for index, ticker in enumerate(tickers, start=1):
            await subscribe(index, ticker)
        late_sent = late_add is None

        while time.time() - started < seconds:
            remaining = seconds - (time.time() - started)
            try:
                raw = await asyncio.wait_for(socket.recv(), timeout=max(1.0, remaining))
            except asyncio.TimeoutError:
                break

            received_ms = int(time.time() * 1000)
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                counts["_unparseable"] += 1
                continue

            counts[parsed.get("type", "?")] += 1
            if (
                not late_sent
                and counts["orderbook_delta"] > 0
                and time.time() - started >= late_after
            ):
                frames.append({"received_ms": received_ms, "frame": parsed})
                await subscribe(len(tickers) + 1, late_add)
                late_sent = True
                continue
            # Recorded verbatim. No field is renamed, normalised or dropped --
            # the point is to preserve what Kalshi sent, including anything
            # this codebase does not yet know to look for.
            frames.append({"received_ms": received_ms, "frame": parsed})

    return {"frames": frames, "counts": dict(counts), "sent": sent}


def summarise(frames: list[dict]) -> dict:
    """Describe the captured shape without interpreting it.

    Reports the literal keys present on each message type, so a future reader
    can compare them against what `orderbook.py` reaches for instead of trusting
    that the two agree.
    """
    keys_by_type: dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter
    )
    payload_keys: dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter
    )
    for record in frames:
        frame = record["frame"]
        message_type = frame.get("type", "?")
        keys_by_type[message_type].update(frame.keys())
        payload = frame.get("msg")
        if isinstance(payload, dict):
            payload_keys[message_type].update(payload.keys())

    return {
        "frame_keys": {t: sorted(c) for t, c in keys_by_type.items()},
        "msg_keys": {t: sorted(c) for t, c in payload_keys.items()},
    }


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=90.0)
    parser.add_argument("--tickers", default=None, help="comma-separated override")
    parser.add_argument("--max-tickers", type=int, default=12)
    parser.add_argument("--late-add", default=None, help="ticker to subscribe mid-stream")
    parser.add_argument("--late-after", type=float, default=10.0)
    parser.add_argument("--out", default="ws_orderbook_stream.json")
    args = parser.parse_args()

    config = KalshiConfig.load()

    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    else:
        print("Finding live markets...")
        async with KalshiRestClient(config) as api:
            tickers = await busiest_tickers(api, args.max_tickers)

    if not tickers:
        print("No live markets found. Nothing to capture.")
        return 1

    print(f"\nSubscribing to {len(tickers)} tickers for {args.seconds:.0f}s...")
    result = await capture(config, tickers, args.seconds, args.late_add, args.late_after)
    frames = result["frames"]

    print(f"\n{len(frames)} frames captured")
    for message_type, count in sorted(result["counts"].items(), key=lambda kv: -kv[1]):
        print(f"    {message_type:<24} {count}")

    if not frames:
        print("\nNo frames. Markets may be closed; nothing written.")
        return 1

    shape = summarise(frames)
    print("\nWire shape actually received:")
    for message_type, keys in shape["msg_keys"].items():
        print(f"    {message_type}.msg keys: {keys}")

    FIXTURES.mkdir(parents=True, exist_ok=True)
    payload = {
        "captured_ms": int(time.time() * 1000),
        "note": (
            "Recorded verbatim off the socket before any parsing. Field names "
            "here are Kalshi's, not this codebase's beliefs about them."
        ),
        "tickers": tickers,
        "request": request_envelope(
            method="WS subscribe",
            endpoint=config.ws_url,
            params={"channels": "orderbook_delta", "market_tickers": ",".join(tickers)},
            note="One subscribe per ticker; every command sent is in `sent`.",
        ),
        "late_add": args.late_add,
        "sent": result["sent"],
        "counts": result["counts"],
        "shape": shape,
        "frames": frames,
    }
    destination = FIXTURES / args.out
    write_capture(destination, payload, indent=1)
    print(f"\nWrote {destination} ({destination.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
