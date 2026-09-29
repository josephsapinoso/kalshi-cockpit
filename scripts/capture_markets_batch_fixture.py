"""Capture `GET /markets?tickers=a,b,c` as Kalshi returns it, before #191 reads it.

Why this exists
---------------
`/hedge` reads every watched leg's book one `GET /markets/{ticker}` at a time
(`backend/hedge.py:read_books`), and each read waits its turn on an 8/s
limiter that the hand-bet quote refresh shares (#191 venue review,
2026-09-29). Kalshi's `/markets` takes a comma-separated `tickers` filter and
returns the same Market object, so one request can replace N. The rule is to
**capture the payload before writing the parser** (`CLAUDE.md`, wire-format
tests), and there was no batch capture in `tests/fixtures/`.

What the request is built to settle, none of which the docs state:

- Whether a batch read returns a **settled** market at all, or filters it out
  the way an unfiltered `/markets` walk of open events would. A leg whose
  market has settled must come back either with its terminal status or not at
  all, and the two need different words on `/hedge`.
- What happens to a ticker the venue has **never heard of**: omitted, or an
  error for the whole request. A single-market read 404s.
- Whether the order of `markets` follows the order asked.

The tickers asked for are public market identifiers chosen here, never the
legs of any position this desk holds: operator data does not enter the repo.
Two are open game markets found by a `series_ticker` + `status=open` filter
(a question, not the blind `/markets` pagination `CLAUDE.md` forbids). One is
the first settled ticker in `tests/fixtures/markets_settled.json`. One is
made up.

Unauthenticated on purpose: `/markets` is public, so no key is loaded and no
signature is computed, and nothing credential-shaped can reach the file
(`capture_envelope._refuse_credentials` checks the params anyway).

Run:

    .venv\\Scripts\\python.exe scripts\\capture_markets_batch_fixture.py

## What this does not establish

- Anything about request cost. Whether a `tickers=` read spends one read
  token or one per ticker is Kalshi's `GET /account/endpoint_costs` to say,
  and this capture does not read it.
- Behaviour above four tickers, or at the 100-ticker chunk #191 uses.
  `scripts/measure_combo_leg_echo.py` round-tripped 200 on 2026-08-09; this
  file pins the shape, not the ceiling.
- Anything about a combination (`KXMVE`) ticker. `/hedge` reads leg markets.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from capture_envelope import request_envelope, write_capture  # noqa: E402

BASE = "https://api.elections.kalshi.com/trade-api/v2"
OUT = ROOT / "tests" / "fixtures" / "markets_batch_by_ticker.json"
OPEN_SERIES = ("KXNFLGAME", "KXMLBGAME", "KXWNBAGAME", "KXNCAAFGAME")
MADE_UP = "KXNOSUCHMARKET-26SEP29-ZZZ"


def _open_tickers(client: httpx.Client, want: int) -> list[str]:
    for series in OPEN_SERIES:
        r = client.get(
            f"{BASE}/markets",
            params={"series_ticker": series, "status": "open", "limit": want},
        )
        r.raise_for_status()
        body = r.json()
        if "markets" not in body:
            raise SystemExit(f"/markets has no 'markets' key: {sorted(body)}")
        tickers = [m["ticker"] for m in body["markets"] if m.get("ticker")]
        if len(tickers) >= want:
            return tickers[:want]
    raise SystemExit(f"no series in {OPEN_SERIES} had {want} open markets")


def _settled_ticker() -> str:
    doc = json.loads(
        (ROOT / "tests" / "fixtures" / "markets_settled.json").read_text("utf-8")
    )
    return doc["markets"][0]["ticker"]


def main() -> None:
    with httpx.Client(timeout=20.0) as client:
        asked = [*_open_tickers(client, 2), _settled_ticker(), MADE_UP]
        params = {"tickers": ",".join(asked), "limit": len(asked)}
        r = client.get(f"{BASE}/markets", params=params)
        status = r.status_code
        try:
            body = r.json()
        except ValueError:
            body = {"unparseable_body": r.text[:2000]}
    returned = [m.get("ticker") for m in body.get("markets") or []]
    document = {
        "request": request_envelope(
            endpoint=f"{BASE}/markets",
            params=params,
            note=(
                "Two open game markets, one settled market from "
                "markets_settled.json, and one made-up ticker, in that order."
            ),
        ),
        "endpoint": f"{BASE}/markets",
        "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "note": (
            "Verbatim GET /markets?tickers= response, captured for #191 "
            "(one batched book read for /hedge in place of one read per "
            "leg). See scripts/capture_markets_batch_fixture.py."
        ),
        "asked": asked,
        "http_status": status,
        "returned_in_order": returned,
        "response": body,
    }
    write_capture(OUT, document)
    print(f"HTTP {status}; asked {asked}")
    print(f"returned {returned}")
    for m in body.get("markets") or []:
        print(m.get("ticker"), m.get("status"), repr(m.get("result")),
              m.get("yes_bid_dollars"), m.get("yes_ask_dollars"))
    print("cursor:", repr(body.get("cursor")))
    print("wrote", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
