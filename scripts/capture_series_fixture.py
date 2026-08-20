"""Capture `GET /series/{ticker}` for the four series behind the 11 real fills.

**Why this exists** (fleet convening item 9). The 2026-08-14 fee attribution
pinned the charged fee to `ceil(k * C * P * (1-P))` with `k` splitting cleanly
by series — MLB at ~0.035, ATP/WNBA at ~0.07 — and ADR 0028 left *which
attribute carries the split* unresolved: sport, series, and a liquidity tier
all fit identically on 11 fills. A later live read of `/series` reportedly
showed a per-series fee field that would settle it — and that read was never
committed: it appears in zero fixtures and zero backend files. Good news gets
more scrutiny, not less, so this captures the payloads the claim rests on.

The four series are exactly the ones the fills touch:

    KXMLBGAME, KXMLBSPREAD    the k ~= 0.035 group (9 fills)
    KXATPDOUBLES, KXWNBAGAME  the k ~= 0.070 group (2 fills)

One file, all four payloads, envelopes included — this repo has been caught
twice assuming two endpoints agree about field names, so the fixture stores
what the wire actually said, not a projection of it.

What this does not establish
----------------------------
- That any fee field found here *causes* the charged fee. That is
  `tests/test_series_fee_multiplier.py`'s job, by predicting all 11 fills to
  $0.0001 from this fixture alone.
- Anything about maker fees, or about series not captured here.

Run:

    .venv\\Scripts\\python.exe scripts\\capture_series_fixture.py

Read-only. Places no orders and spends no odds credits.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import ConfigError, KalshiConfig          # noqa: E402
from backend.kalshi.rest import KalshiRestClient              # noqa: E402
from backend.logging_setup import configure_logging           # noqa: E402

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
OUT = FIXTURES / "series_fee_fields.json"

#: The series the 11 attributed fills belong to. Fixed rather than derived
#: from the fills capture, so re-running after new fills cannot silently
#: change what this fixture claims to cover.
SERIES = ("KXMLBGAME", "KXMLBSPREAD", "KXATPDOUBLES", "KXWNBAGAME")


async def main() -> int:
    configure_logging()
    try:
        config = KalshiConfig.load()
    except ConfigError as exc:
        print(f"no Kalshi credentials: {exc}", file=sys.stderr)
        return 2

    payloads: dict[str, dict] = {}
    async with KalshiRestClient(config) as client:
        for ticker in SERIES:
            payloads[ticker] = await client.get(f"/series/{ticker}")

    OUT.write_text(
        json.dumps(
            {
                "note": (
                    "GET /series/{ticker} for the four series behind the 11 "
                    "attributed fills. Captured for fleet convening item 9: "
                    "does series metadata carry the fee split ADR 0028 left "
                    "unresolved?"
                ),
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "endpoint": "/series/{ticker}",
                "payloads": payloads,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    for ticker, payload in payloads.items():
        series = payload.get("series", payload)
        fee_fields = {
            k: v for k, v in series.items() if "fee" in k.lower()
        }
        print(f"{ticker}: fee-ish fields = {fee_fields or 'NONE'}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
