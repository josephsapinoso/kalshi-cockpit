r"""Capture a real `/portfolio/positions` payload before anything parses it.

Why this script exists
----------------------
One unobserved payload drives three decisions. `backend/kalshi/rest.py:
positions()` reads `payload.get("market_positions") or []`;
`backend/api/routes.py` check 10 walks that list comparing **ticker only**;
and `open_positions.count` renders "Open now: N positions" off the same list.
Meanwhile `backend/kalshi/quotes.py` states the per-row shape has **never**
been observed on this account, and `backend/bets.py` refuses to assume it.
The refusal and the assumption cannot both be right, and the way to settle it
is the ordering rule from `tasks/lessons.md`: **capture the payload before
writing the parser, not after the parser has tests.**

Two directions are live and this script does not pre-judge them:

- Kalshi's docs say `count_filter` "restricts positions to those with
  non-zero values", implying the **default returns zero-quantity rows** for
  every market ever traded. If so, check 10 refuses bets on markets Joe
  exited long ago, and "Open now: N" is inflated.
- The docs also name the quantity field `position` (with fixed-point
  siblings like `position_fp` documented in the changelog). Neither name
  appears anywhere in this repo today. If the field is not called what the
  docs say, a quantity test written from the docs would silently pass on
  absent keys.

So this script fetches the endpoint **twice** — bare, exactly as
`positions()` does today, and with `count_filter=position` — and prints both
row counts side by side. The difference IS the measurement: it is the number
of rows the current code shows Joe and tests bets against that the venue
itself calls "zero".

Run, any time (read-only, free — Kalshi REST is unmetered, no odds credits):

    .venv\Scripts\python.exe scripts\capture_positions_fixture.py

What this script does NOT establish
------------------------------------
- **Anything about `event_positions`.** The docs give the envelope a second
  list; this repo reads only `market_positions`. The capture keeps both
  verbatim, but nothing here decides whether event rows matter.
- **Pagination depth.** It observes whether `cursor` comes back non-empty on
  this account today. A non-empty cursor proves pagination is needed; an
  empty one on a small account proves nothing about a bigger one.
- **What a row looks like DURING a live game.** These are whatever positions
  exist at run time. In-play field behaviour is a separate observation.

Where the captures are written, and why not tests/fixtures/
-----------------------------------------------------------
`data/captures/`, which is **gitignored**. A positions payload is a real
account's live exposure and this repo is public with every push publishing
immediately (see the publication note in `capture_fills_fixture.py`, which
this file follows deliberately). The payloads are written **verbatim** — a
redacted capture is a hand-constructed payload wearing a capture's name.
Promotion into `tests/fixtures/` happens in the same commit as the test that
loads it, once a human has read the field census printed below.

Exit codes:

    0  captured; market_positions non-empty on at least one call
    2  no usable Kalshi credential -- stop
    3  no 'market_positions' key in the envelope -- the wire moved, stop;
       note that today's `or []` would have read this exact state as
       "no open positions"
    4  captured; market_positions present but EMPTY on both calls -- the
       envelope is confirmed, the per-row shape remains unobserved
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import ConfigError, KalshiConfig          # noqa: E402
from backend.kalshi.rest import KalshiRestClient              # noqa: E402
from backend.logging_setup import configure_logging           # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CAPTURES = ROOT / "data" / "captures"
OUT_BARE = CAPTURES / "portfolio_positions_bare.json"
OUT_FILTERED = CAPTURES / "portfolio_positions_count_filter.json"

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_ENVELOPE = 3
EXIT_EMPTY = 4

EXIT_MEANING: dict[int, str] = {
    EXIT_OK: "OK -- market_positions observed with rows.",
    EXIT_CONFIG: "STOP -- no usable Kalshi credential.",
    EXIT_ENVELOPE: (
        "STOP -- no 'market_positions' key. The wire moved; today's "
        "`or []` would have called this 'no open positions'."
    ),
    EXIT_EMPTY: (
        "EMPTY -- envelope confirmed, zero rows on both calls. The per-row "
        "shape is still unobserved; write no parser from this run."
    ),
}

# Substrings that mark a field for a human glance. Quantity-shaped names are
# the point of the exercise; id-shaped ones gate publication.
_QUANTITY_SHAPED = ("position", "quantity", "count", "exposure", "resting", "total")
_ID_SHAPED = ("id", "user", "account", "member", "owner")


def classify(payload: Any) -> str:
    """Which state the envelope is in. Pure, testable without a network.

    'RENAMED' and 'EMPTY' are different findings: the first means stop and
    fix the key, the second means the shape question stays open. Collapsing
    them is the `or []` defect this capture exists to replace.
    """
    if not isinstance(payload, dict) or "market_positions" not in payload:
        return "RENAMED"
    if not payload["market_positions"]:
        return "EMPTY"
    return "ROWS"


def _describe(records: list[dict], label: str) -> Counter:
    keys: Counter = Counter()
    for record in records:
        keys.update(record.keys())

    quantity_shaped = sorted(
        k for k in keys if any(t in k.lower() for t in _QUANTITY_SHAPED)
    )
    id_shaped = sorted(k for k in keys if any(t in k.lower() for t in _ID_SHAPED))

    print(f"\n{len(records)} {label} rows")
    print("field -> how many rows carry it:")
    for key, n in sorted(keys.items()):
        sample = next((r[key] for r in records if key in r), None)
        marker = ""
        if key in quantity_shaped:
            marker = f"   <-- QUANTITY-SHAPED   e.g. {sample!r}"
        elif key in id_shaped:
            marker = "   <-- id-shaped, read before publishing"
        print(f"  {key:30s} {n:4d}  ({type(sample).__name__}){marker}")

    print("quantity-shaped keys:", quantity_shaped or "NONE")

    if len(set(frozenset(r.keys()) for r in records)) > 1:
        print(
            f"NOTE: the {label} rows do not all carry the same field set. "
            f"Any parser must treat the difference as optional-vs-absent."
        )
    return keys


def _write(path: Path, endpoint: str, params: dict, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    records = payload.get("market_positions") or []
    keys: Counter = Counter()
    for r in records:
        if isinstance(r, dict):
            keys.update(r.keys())
    path.write_text(
        json.dumps(
            {
                "note": (
                    "verbatim capture; gitignored; promote into tests/fixtures/ "
                    "only in the same commit as the test that loads it"
                ),
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "endpoint": endpoint,
                "params": params,
                "envelope_keys": sorted(payload.keys())
                if isinstance(payload, dict)
                else None,
                "record_count": len(records),
                "field_coverage": {str(k): v for k, v in sorted(keys.items())},
                "payload": payload,
            },
            indent=2,
            sort_keys=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {path}")


async def capture() -> int:
    configure_logging()
    try:
        config = KalshiConfig.load()
    except ConfigError as exc:
        print(f"Cannot reach Kalshi: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    async with KalshiRestClient(config) as api:
        # Deliberately NOT `api.positions()` -- that helper hands back the
        # list and swallows a rename; the whole point of a capture is the
        # envelope the list arrived in.
        bare: dict[str, Any] = await api.get("/portfolio/positions")
        filtered: Optional[dict[str, Any]]
        try:
            filtered = await api.get(
                "/portfolio/positions", count_filter="position"
            )
        except Exception as exc:  # noqa: BLE001 -- an unsupported param is a finding
            print(f"count_filter=position REFUSED by the venue: {exc!r}")
            filtered = None

    print("=" * 70)
    print("POSITIONS  bare call, exactly what positions() reads today")
    print("=" * 70)
    print("envelope keys:", sorted(bare.keys()) if isinstance(bare, dict) else bare)

    state = classify(bare)
    if state == "RENAMED":
        print(EXIT_MEANING[EXIT_ENVELOPE], file=sys.stderr)
        return EXIT_ENVELOPE

    bare_rows = bare["market_positions"]
    cursor = bare.get("cursor") if isinstance(bare, dict) else None
    print(f"cursor: {cursor!r}  ({'NON-EMPTY -- pagination is real on this account' if cursor else 'empty on this account today; proves nothing at size'})")
    if isinstance(bare.get("event_positions"), list):
        print(f"event_positions rows (unparsed anywhere in this repo): {len(bare['event_positions'])}")

    if bare_rows:
        _describe([r for r in bare_rows if isinstance(r, dict)], "bare")
    _write(OUT_BARE, "/portfolio/positions", {}, bare)

    print()
    print("=" * 70)
    print("POSITIONS  count_filter=position -- the venue's own 'non-zero' cut")
    print("=" * 70)
    filtered_rows: Optional[list] = None
    if filtered is None:
        print("no filtered capture (param refused above)")
    else:
        print("envelope keys:", sorted(filtered.keys()))
        if classify(filtered) == "RENAMED":
            print("filtered envelope missing market_positions -- read the raw file")
        else:
            filtered_rows = filtered["market_positions"]
            if filtered_rows:
                _describe(
                    [r for r in filtered_rows if isinstance(r, dict)], "filtered"
                )
        _write(
            OUT_FILTERED,
            "/portfolio/positions",
            {"count_filter": "position"},
            filtered,
        )

    print()
    print("=" * 70)
    print("THE MEASUREMENT")
    print("=" * 70)
    print(f"bare rows:     {len(bare_rows)}")
    if filtered_rows is not None:
        print(f"filtered rows: {len(filtered_rows)}")
        print(
            f"difference:    {len(bare_rows) - len(filtered_rows)} rows the "
            f"venue calls zero that today's code shows Joe and tests bets "
            f"against"
        )
    else:
        print("filtered rows: NOT OBSERVED")

    code = EXIT_OK if bare_rows else EXIT_EMPTY
    print()
    print(f"exit {code}: {EXIT_MEANING[code]}")
    return code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(capture()))
