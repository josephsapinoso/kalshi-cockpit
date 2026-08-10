"""Capture a real `/portfolio/fills` payload the moment fills exist.

Why this script exists before the fixture does
----------------------------------------------
`backend/kalshi/rest.py:fills()` documents `fee` on each fill as **ground truth**
for the fee model. That field name is a **claim inherited from the predecessor
project and never observed on this account.** Probed 2026-08-09 against
production (`api.elections.kalshi.com`): the account has **zero fills**, so the
per-fill record shape has never been seen here.

What *was* settled by that probe, and is worth separating from what was not:

- **Measured:** the envelope is `{"cursor": str, "fills": list}`. So
  `payload.get("fills")` reads the right key -- the fourth-wrong-wire-key
  failure this repo has hit (`data["yes"]`, `multivariate_event_collections`,
  `competition_scope == "game"`, `payload["orderbook"]`) is not present at the
  envelope level.
- **NOT measured, and unmeasurable without a fill:** every field *inside* a fill
  record, including whether the fee is called `fee`, what units it carries, and
  whether it is per-contract or per-order.

That second gap is the expensive one, and it is why this script is written now
rather than after the trades. `tests/test_execution.py` asserts
`average_fee_paid` against a **hand-constructed dict**, in the fee path, which
is the exact thing the 52.00%-vs-51.75% question turns on. `CLAUDE.md` requires
wire-format tests to load captured payloads, never hand-constructed ones, and
the ordering rule from `tasks/lessons.md` is: **capture the payload before
writing the parser, not after the parser has tests.**

The concrete risk this removes
------------------------------
The four fee-calibration trades cost real money (~$5) and are the only way to
observe a fill. If the payload is parsed by a key that turns out not to exist,
the parser returns nothing -- silently, in the well-formed-empty way this repo
has been burned by four times -- and the money has been spent for an unreadable
answer. Capturing verbatim first makes the spend re-readable forever.

Not time-critical, and that matters because the operator works from a phone
-----------------------------------------------------------------------------
The trades are placed in the Kalshi app; this capture is a laptop step. That is
acceptable **only** because `/portfolio/fills` is a historical endpoint, so the
capture can happen whenever the laptop is next open rather than in the moment.

Stated as an assumption, not a measurement: Kalshi's fill retention window is
unknown to this project. Nothing here has observed it, and no documented value
was trusted. If a long delay is unavoidable, run this sooner rather than later.

Run, any time after the trades have filled:

    .venv\\Scripts\\python.exe scripts\\capture_fills_fixture.py

Read-only. Places, cancels and modifies nothing. Spends no odds credits --
Kalshi REST is unmetered.

Before this fixture goes into a public repo
-------------------------------------------
It is a real account's trading history. There is no credential in a fill, but
there may be account-identifying ids. The script prints every key it captured
and flags id-shaped ones, so that is a decision made with the field list in
hand rather than an assumption. The payload is written **verbatim** regardless:
a redacted capture is a hand-constructed payload wearing a capture's name, and
that is the failure this file exists to prevent.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import ConfigError, KalshiConfig          # noqa: E402
from backend.kalshi.rest import KalshiRestClient              # noqa: E402
from backend.logging_setup import configure_logging           # noqa: E402

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
OUT = FIXTURES / "portfolio_fills.json"

# Kalshi's own cap on this endpoint is not established by this project. 100 is
# well under any plausible limit and far above the four fills the calibration
# trades produce.
LIMIT = 100

# Substrings that mark a field as worth a human glance before the repo is
# public. Deliberately broad -- the cost of over-flagging is one read.
_ID_SHAPED = ("id", "user", "account", "member", "owner")


async def capture() -> int:
    configure_logging()
    try:
        config = KalshiConfig.load()
    except ConfigError as exc:
        print(f"Cannot reach Kalshi: {exc}", file=sys.stderr)
        return 2

    async with KalshiRestClient(config) as api:
        # Deliberately NOT `api.fills()`. That helper ends in
        # `payload.get("fills") or []`, which collapses "the envelope was
        # renamed" and "there are no fills" into one indistinguishable empty
        # list. The whole point of a capture is to see the envelope.
        payload: dict[str, Any] = await api.get("/portfolio/fills", limit=LIMIT)

    print("envelope keys:", sorted(payload.keys()))

    fills = payload.get("fills")
    if fills is None:
        print(
            "\nNo 'fills' key in the response.\n"
            "The envelope has been renamed since it was measured on 2026-08-09.\n"
            "`KalshiRestClient.fills()` is returning [] for every caller RIGHT\n"
            "NOW, silently. Fix that before anything else, and do not treat an\n"
            "empty portfolio as the explanation.",
            file=sys.stderr,
        )
        return 1

    if not fills:
        # A state, not an error -- and the message has to say which, because
        # "no fills yet" and "the parser cannot see them" look identical from
        # outside and demand opposite responses.
        print(
            "\nZero fills on this account.\n"
            "Nothing to capture: the per-fill wire shape is still UNOBSERVED,\n"
            "and no fixture should be invented to stand in for it.\n"
            "\n"
            "This is the expected result until the four fee-calibration trades\n"
            "have been placed in the Kalshi app and filled. Re-run afterwards.",
            file=sys.stderr,
        )
        return 3

    keys = Counter()
    for fill in fills:
        keys.update(fill.keys())

    fee_shaped = sorted(k for k in keys if "fee" in k.lower())
    id_shaped = sorted(
        k for k in keys if any(tok in k.lower() for tok in _ID_SHAPED)
    )

    print(f"\n{len(fills)} fill(s) captured")
    print("\nfield -> how many fills carry it:")
    for key, n in sorted(keys.items()):
        sample = next((f[key] for f in fills if key in f), None)
        marker = ""
        if key in fee_shaped:
            marker = "   <-- FEE"
        elif key in id_shaped:
            marker = "   <-- id-shaped, read before publishing"
        print(f"  {key:30s} {n:4d}  ({type(sample).__name__}){marker}")

    print("\nfee-shaped keys:", fee_shaped or "NONE")
    if not fee_shaped:
        # The headline finding, if it happens. Printed loudly rather than left
        # for a reader to notice the empty list.
        print(
            "\n!! `rest.py:fills()` documents `fee` as ground truth and NO field\n"
            "!! on a real fill carries 'fee' in its name. That docstring is a\n"
            "!! documentation-derived guess and it is wrong. Find the real field\n"
            "!! in the key list above BEFORE writing any fee reconciliation.",
        )

    # Not a field count but a shape check: are the fills uniform? A single
    # non-uniform record is how an optional field gets read as mandatory.
    if len(set(frozenset(f.keys()) for f in fills)) > 1:
        print(
            "\nNOTE: the fills do not all carry the same field set. Any parser\n"
            "must treat the difference as optional-vs-absent, not as a default."
        )

    OUT.write_text(
        json.dumps(
            {
                "note": (
                    "Verbatim GET /portfolio/fills response. Captured because "
                    "the per-fill wire shape -- including whether the fee field "
                    "is named `fee` -- had never been observed on this account, "
                    "while tests/test_execution.py asserted against a "
                    "hand-constructed dict in the fee path. See "
                    "scripts/capture_fills_fixture.py."
                ),
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "endpoint": "/portfolio/fills",
                "limit_requested": LIMIT,
                "envelope_keys": sorted(payload.keys()),
                "fill_count": len(fills),
                "field_coverage": {str(k): v for k, v in sorted(keys.items())},
                "fee_shaped_keys": fee_shaped,
                "payload": payload,
            },
            indent=2,
            sort_keys=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nwrote {OUT}")
    print(
        "\nNext: write the fee reconciliation against THIS file, and delete the\n"
        "hand-constructed fee assertion in tests/test_execution.py. A fixture\n"
        "that no test loads is decoration."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(capture()))
