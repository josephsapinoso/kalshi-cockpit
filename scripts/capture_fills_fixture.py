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

TIME-CRITICAL, and this file used to say the opposite
-----------------------------------------------------
The previous version of this docstring said the capture "can happen whenever the
laptop is next open", because `/portfolio/fills` is a historical endpoint. That
reasoning is now refuted by measurement.

Measured 2026-08-10 on the production account: `/portfolio/settlements` returns
**55 real settled positions** dated 2025-11-27 to 2026-05-10, while
`/portfolio/fills` returns **zero** for eight different query shapes -- bare,
`limit=200`, `min_ts=0`, `min_ts=1`, `min_ts=1700000000`, a `min_ts`/`max_ts`
span, `ticker=`, and `event_ticker=`. The account traded; the fills endpoint is
not showing it. That is a **retention window, not a missing parameter**, with a
measured upper bound of roughly three months and no measured lower bound.

So: run this within **days** of the trades filling, not weeks. The trades are
placed in the Kalshi app and this is a laptop step, and the operator works from
a phone -- so the laptop session is the schedule constraint that decides whether
the money bought an answer.

There is now a free fee source that does not need the trades at all
-------------------------------------------------------------------
`/portfolio/settlements` carries `fee_cost` on every one of those 55 records, in
exactly the dollar-string form the docs give for a fill. This script captures it
too, unconditionally, because it is the only real fee ground truth this account
has and it exists *today*. See `backend/kalshi/rest.py:settlements` for what it
does and does not establish -- it is position-level, so it pins the coefficient
and refutes Model B, and it cannot settle per-order versus per-contract
rounding. `tasks/NEXT.md` says "there is no free path to the fee model"; that
sentence is wrong and this script is the evidence.

Run, any time after the trades have filled:

    .venv\\Scripts\\python.exe scripts\\capture_fills_fixture.py

Read-only. Places, cancels and modifies nothing. Spends no odds credits --
Kalshi REST is unmetered.

Where the captures are written, and why not tests/fixtures/
-----------------------------------------------------------
Both go to `data/captures/`, which is **gitignored**. They are a real account's
trading history, and `kalshi-cockpit` is public with every push publishing
immediately. There is no credential in either payload, and the 55 settlements
observed carried no user, account or order id -- but they do disclose what was
bet and what it lost, and this repo has already had to make that call once: the
pre-public history audit on 2026-08-10 removed six committed screenshots because
"a screenshot of this UI is one live run away from showing a real position or
bankroll" (`.gitignore`). A settlements payload is that, without the screenshot.

So the script produces the evidence and does not publish it. Both payloads are
written **verbatim** -- a redacted capture is a hand-constructed payload wearing
a capture's name, which is the failure this file exists to prevent -- and the
promotion into `tests/fixtures/` happens in the same commit as the test that
loads it, once a human has read the field list printed below.
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

ROOT = Path(__file__).resolve().parent.parent

# NOT tests/fixtures/. A capture belongs there once a test loads it, and this
# one carries a real account's positions -- see the publication note in the
# module docstring. data/ is gitignored, so producing the evidence cannot
# publish it by accident, and tests/test_parsers_return_something.py stays
# honest: it fails on any fixture no test reads, and an unread capture sitting
# in tests/fixtures/ is exactly what it is for.
#
# Promote a file into tests/fixtures/ in the same commit as the test that
# loads it, or as an entry in EVIDENCE_NOT_PARSER_INPUT. Never before.
CAPTURES = ROOT / "data" / "captures"
OUT = CAPTURES / "portfolio_fills.json"
OUT_SETTLEMENTS = CAPTURES / "portfolio_settlements.json"

# Kalshi's own cap on this endpoint is not established by this project. 100 is
# well under any plausible limit and far above the four fills the calibration
# trades produce.
LIMIT = 100

# Substrings that mark a field as worth a human glance before the repo is
# public. Deliberately broad -- the cost of over-flagging is one read.
_ID_SHAPED = ("id", "user", "account", "member", "owner")


def _describe(records: list[dict], label: str) -> tuple[Counter, list[str]]:
    """Print the field census for a set of records and return it.

    The census is the point of the whole exercise: it is the artefact that says
    what the wire actually carries, as opposed to what a docstring remembers.
    """
    keys: Counter = Counter()
    for record in records:
        keys.update(record.keys())

    fee_shaped = sorted(k for k in keys if "fee" in k.lower())
    id_shaped = sorted(k for k in keys if any(t in k.lower() for t in _ID_SHAPED))
    taker_shaped = sorted(
        k for k in keys if "taker" in k.lower() or "maker" in k.lower()
    )

    print(f"\n{len(records)} {label} captured")
    print("\nfield -> how many records carry it:")
    for key, n in sorted(keys.items()):
        sample = next((r[key] for r in records if key in r), None)
        marker = ""
        if key in fee_shaped:
            marker = f"   <-- FEE   e.g. {sample!r}"
        elif key in taker_shaped:
            marker = f"   <-- MAKER/TAKER   e.g. {sample!r}"
        elif key in id_shaped:
            marker = "   <-- id-shaped, read before publishing"
        print(f"  {key:30s} {n:4d}  ({type(sample).__name__}){marker}")

    print("\nfee-shaped keys:", fee_shaped or "NONE")
    print("maker/taker keys:", taker_shaped or "NONE")

    if len(set(frozenset(r.keys()) for r in records)) > 1:
        print(
            f"\nNOTE: the {label} do not all carry the same field set. Any "
            f"parser must treat the difference as optional-vs-absent, not as a "
            f"default."
        )
    return keys, fee_shaped


def _write(
    path: Path,
    endpoint: str,
    payload: dict,
    records: list[dict],
    keys: Counter,
    fee_shaped: list[str],
    note: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "note": note,
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "endpoint": endpoint,
                "limit_requested": LIMIT,
                "envelope_keys": sorted(payload.keys()),
                "record_count": len(records),
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
    print(f"\nwrote {path}")


async def capture() -> int:
    configure_logging()
    try:
        config = KalshiConfig.load()
    except ConfigError as exc:
        print(f"Cannot reach Kalshi: {exc}", file=sys.stderr)
        return 2

    async with KalshiRestClient(config) as api:
        # Deliberately NOT `api.fills()` / `api.settlements()`. Those helpers
        # hand back the list; the whole point of a capture is to see the
        # envelope the list arrived in.
        fills_payload: dict[str, Any] = await api.get("/portfolio/fills", limit=LIMIT)
        settlements_payload: dict[str, Any] = await api.get(
            "/portfolio/settlements", limit=LIMIT
        )

    # -- settlements: unconditional, and the reason this script is worth
    # running BEFORE the trades rather than only after them ------------------
    print("=" * 70)
    print("SETTLEMENTS  (free fee ground truth -- needs no calibration trade)")
    print("=" * 70)
    print("envelope keys:", sorted(settlements_payload.keys()))

    settlements = settlements_payload.get("settlements")
    if settlements is None:
        print(
            "\nNo 'settlements' key. The envelope has been renamed since it "
            "was measured on 2026-08-10; KalshiRestClient.settlements() will "
            "now raise, which is correct. Fix the key before reading anything.",
            file=sys.stderr,
        )
    elif not settlements:
        print(
            "\nZero settlements -- which CONTRADICTS the 2026-08-10 "
            "measurement of 55 on this account. Either the account changed or "
            "the endpoint did. Do not proceed on the assumption that the fee "
            "evidence is still there.",
            file=sys.stderr,
        )
    else:
        keys, fee_shaped = _describe(settlements, "settlement(s)")
        _write(
            OUT_SETTLEMENTS,
            "/portfolio/settlements",
            settlements_payload,
            settlements,
            keys,
            fee_shaped,
            "Verbatim GET /portfolio/settlements response. Captured because "
            "fee_cost on these records is the only fee ground truth this "
            "account has, and it exists without spending anything. It is a "
            "POSITION-level fee, aggregated over the fills that built the "
            "position, so it pins the coefficient and cannot settle per-order "
            "vs per-contract rounding. See backend/kalshi/rest.py:settlements.",
        )

    # -- fills: what the calibration trades are for --------------------------
    print()
    print("=" * 70)
    print("FILLS  (the calibration trades)")
    print("=" * 70)
    print("envelope keys:", sorted(fills_payload.keys()))

    fills = fills_payload.get("fills")
    if fills is None:
        print(
            "\nNo 'fills' key in the response.\n"
            "The envelope has been renamed since it was measured 2026-08-09.\n"
            "KalshiRestClient.fills() now RAISES on this rather than returning\n"
            "[] -- fix the key before anything else, and do not treat an empty\n"
            "portfolio as the explanation.",
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
            "have been placed in the Kalshi app and filled. Re-run afterwards\n"
            "-- within DAYS, not weeks. Measured 2026-08-10: this account has\n"
            "55 settlements and zero fills, so /portfolio/fills drops history\n"
            "the account demonstrably has. The retention window is shorter\n"
            "than three months and its lower bound is unmeasured.",
            file=sys.stderr,
        )
        return 3

    keys, fee_shaped = _describe(fills, "fill(s)")
    if not fee_shaped:
        # The headline finding, if it happens. Printed loudly rather than left
        # for a reader to notice the empty list.
        print(
            "\n!! NO field on a real fill carries 'fee' in its name. The docs\n"
            "!! give fee_cost; if that is absent too, find the real field in\n"
            "!! the key list above BEFORE writing any fee reconciliation."
        )

    _write(
        OUT,
        "/portfolio/fills",
        fills_payload,
        fills,
        keys,
        fee_shaped,
        "Verbatim GET /portfolio/fills response. Captured because the per-fill "
        "wire shape -- including whether the fee field is named fee_cost -- "
        "had never been observed on this account, while "
        "tests/test_execution.py asserted against a hand-constructed dict in "
        "the fee path. See scripts/capture_fills_fixture.py.",
    )
    print(
        "\nNext: write the fee reconciliation against THIS file, and delete "
        "the\nhand-constructed fee assertion in tests/test_execution.py. A "
        "fixture\nthat no test loads is decoration."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(capture()))
