"""Capture ONE read of the market-wide RFQ list, redacted, for #147.

    .venv\\Scripts\\python.exe scripts\\capture_rfq_list.py \\
        --ticker KXMVECROSSCATEGORY-... \\
        --out tests\\fixtures\\combo_rfq_list_market_wide.json

Why this exists
----------------
`open_rfq_for` (`backend/kalshi/rfq.py`) took the first `status == "open"`
row off `GET /communications/rfqs?market_ticker=` and treated it as ours.
Measured 2026-09-24 (#129's run, on a combination Joe then held): that
endpoint returns **every requester's** RFQs on the market -- 100 rows,
`creator_id` blank on all of them. That run tried `rfq_user_filter=self`,
the QUOTES endpoint's own param name, and it was ignored: same 100 rows with
or without it. Re-measured 2026-09-24 with the RFQS endpoint's own
documented name, `user_filter=self`, it DOES narrow (100 rows -> 0, no open
RFQ of ours on that market at the time); `status=open` alone did not narrow
anything observable (100 -> 100). `open_rfq_for` now sends
`user_filter=self&status=open` first, and keeps a `creator_user_id` filter
as a second guard, in case a future venue change silently drops or renames
the parameter again the way #129 found it already had once.

This particular capture -- a combination the account does NOT hold, run
after the `user_filter` fix -- carried **0 of its 100 rows with a
non-empty `creator_user_id`**, because the account had no open RFQ on this
market at all: the None case, not a defect. The 1-of-100 reading that
motivated the `creator_user_id` guard came from a DIFFERENT, uncommitted
capture (#129's run, on a held combination, discarded per Joe's rule against
committing account data) -- n = 1 own row observed there, read back by id;
this script captures the wire SHAPE the guard is pinned against, not a
repeat of that count. `open_rfq_for` now filters on a non-empty
`creator_user_id`; this script captures the wire shape that fix is pinned
against, so the test does not run on a hand-typed payload (CLAUDE.md's
wire-format rule).

**Read-only.** This module issues GET requests only -- no create, no delete,
no accept. It cannot open an RFQ, close one, or spend anything.

**Operator data never enters this repo, even sanitized (Joe's rule).** Two
things follow: the ticker asked about must be a combination Joe does NOT
hold (a held ticker names his position, which the fixture's own field name
would then advertise regardless of anything redacted inside it), and every
ticker string the venue returns -- `market_ticker`, `mve_collection_ticker`,
every leg's `event_ticker` and `market_ticker`, the `requested_ticker` this
script was pointed at -- is replaced with a placeholder. `creator_user_id`
and `creator_id` are handled separately, because their PRESENCE (not their
value) is the fact the fixture exists to pin (see `redact_rows`).

What this does not establish
-----------------------------
One list, at one moment, on the ticker named. Whether `creator_user_id` is
always present on our own rows is one observation, not a rate -- the same
caveat `open_rfq_for`'s docstring carries. This capture's own row count of
rows carrying `creator_user_id` is printed and written into the fixture; it
is whatever it was at the moment the script ran, not a fixed number.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import KalshiConfig  # noqa: E402
from backend.kalshi.rest import KalshiRestClient  # noqa: E402
from backend.logging_setup import configure_logging  # noqa: E402

RFQS_PATH = "/communications/rfqs"

#: Keep at most this many rows. Trimmed AFTER redaction so a row carrying
#: `creator_user_id` (the rare, load-bearing case) is never the one dropped.
MAX_ROWS = 20

#: Ticker-shaped fields on a row and on each leg. Every one of these is
#: routed through the SAME `TickerRedactor`, so a value that repeats (a
#: row's `market_ticker` equalling the ticker asked about, say) gets the
#: same placeholder everywhere it appears in the fixture.
_ROW_TICKER_FIELDS = ("market_ticker", "mve_collection_ticker")
_LEG_TICKER_FIELDS = ("event_ticker", "market_ticker")


class Refused(RuntimeError):
    """A pre-condition failed before any venue call. Read-only either way."""


class TickerRedactor:
    """Maps real ticker strings to stable, sequential placeholders.

    **Consistent, not reversible.** The same real value always maps to the
    same placeholder within one fixture (so a reader can still see "this
    leg's market_ticker is the same as that RFQ's market_ticker" where it
    was), but nothing here lets you go from the placeholder back to the real
    ticker -- there is no stored real-to-fake table written anywhere.
    """

    def __init__(self) -> None:
        self._seen: dict[str, str] = {}

    def redact(self, value):
        if not value:
            return value
        if value not in self._seen:
            self._seen[value] = f"TICKER_{len(self._seen) + 1}_REDACTED"
        return self._seen[value]


def redact_rows(rows: list[dict], redactor: TickerRedactor) -> list[dict]:
    """Replace ticker fields everywhere, and `creator_user_id` / `creator_id`
    where non-empty.

    **Which rows carried `creator_user_id` must survive redaction** -- that
    presence is the whole discriminator #147 relies on, so a blank value
    stays blank (`""`, `None`, or the key absent, exactly as the venue sent
    it) and only a genuinely non-empty value is replaced with a placeholder.
    Every ticker field, by contrast, is replaced whenever it is non-empty --
    operator data never enters this repo, even sanitized, and a ticker is
    not the fact this fixture is pinning.
    """
    out = []
    for row in rows:
        row = dict(row)
        if row.get("creator_user_id"):
            row["creator_user_id"] = "REDACTED-USER"
        if row.get("creator_id"):
            row["creator_id"] = "REDACTED"
        for field in _ROW_TICKER_FIELDS:
            if row.get(field):
                row[field] = redactor.redact(row[field])
        legs = row.get("mve_selected_legs")
        if isinstance(legs, list):
            redacted_legs = []
            for leg in legs:
                leg = dict(leg)
                for field in _LEG_TICKER_FIELDS:
                    if leg.get(field):
                        leg[field] = redactor.redact(leg[field])
                redacted_legs.append(leg)
            row["mve_selected_legs"] = redacted_legs
        out.append(row)
    return out


def trim_keeping_flagged_rows(rows: list[dict], limit: int) -> list[dict]:
    """At most `limit` rows, but every row carrying `creator_user_id` stays.

    A market-wide list runs to 100 rows and almost none of them matter; the
    one(s) that carry the field are the fixture's whole point and must not be
    the ones a blunt `rows[:limit]` truncates away.
    """
    flagged = [r for r in rows if r.get("creator_user_id")]
    unflagged = [r for r in rows if not r.get("creator_user_id")]
    room = max(limit - len(flagged), 0)
    return flagged + unflagged[:room]


def build_fixture(payload: dict, *, ticker: str, note: str) -> dict:
    rows = payload.get("rfqs") or []
    redactor = TickerRedactor()
    redacted = redact_rows(rows, redactor)
    trimmed = trim_keeping_flagged_rows(redacted, MAX_ROWS)
    own_rows = sum(1 for r in trimmed if r.get("creator_user_id"))
    return {
        "endpoint": f"GET {RFQS_PATH}?market_ticker=<ticker>&limit=100",
        "tickers_redacted": True,
        "ticker_kind": "KXMVE combination",
        "requested_ticker": redactor.redact(ticker),
        "row_count_at_capture": len(rows),
        "row_count_in_fixture": len(trimmed),
        "rows_carrying_creator_user_id_in_fixture": own_rows,
        "note": note,
        "redaction": (
            "Every ticker-shaped field (requested_ticker, each row's "
            "market_ticker and mve_collection_ticker, each leg's "
            "event_ticker and market_ticker) is replaced with a sequential "
            "TICKER_N_REDACTED placeholder, consistent within this file: "
            "the same real value always maps to the same placeholder here. "
            "The ticker this script was asked about is a combination the "
            "account does NOT hold (Joe's rule: operator data never enters "
            "this repo, even sanitized). Separately, every non-empty "
            "creator_user_id is replaced with 'REDACTED-USER' and every "
            "non-empty creator_id with 'REDACTED'. Blank values (missing, "
            "None or '') are left blank on purpose: which rows carried "
            "creator_user_id is the fact this fixture pins, and redacting a "
            "blank into something non-blank would destroy that. status, "
            "contracts_fp, target_cost_dollars, created_ts and every other "
            "non-ticker, non-identity field are verbatim."
        ),
        "rfqs": trimmed,
    }


async def _run(ticker: str, out_path: Path, note: str) -> int:
    if out_path.exists():
        raise Refused(f"refusing to overwrite an existing fixture: {out_path}")
    config = KalshiConfig.load()
    async with KalshiRestClient(config) as api:
        # Read-only: one GET, no exchange_index write params -- that
        # parameter only matters on a create/delete/accept write, none of
        # which this module ever sends.
        payload = await api.request(
            "GET", RFQS_PATH,
            params={"market_ticker": ticker, "limit": 100},
        )
    fixture = build_fixture(payload, ticker=ticker, note=note)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(fixture, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"{fixture['row_count_at_capture']} rows at the venue, "
        f"{fixture['row_count_in_fixture']} kept, "
        f"{fixture['rows_carrying_creator_user_id_in_fixture']} "
        f"carrying creator_user_id; wrote {out_path}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--ticker", required=True,
        help="a KXMVE combination market ticker the account does NOT hold",
    )
    parser.add_argument("--out", type=Path, required=True, help="fixture path to write")
    parser.add_argument(
        "--note", default=None,
        help="fixture 'note' field; defaults to a standard sentence naming the "
             "capture as read-only and market-wide",
    )
    args = parser.parse_args(argv)
    note = args.note or (
        "Captured read-only via GET /communications/rfqs?market_ticker= for "
        "#147: the endpoint is market-wide, not filtered to this account, "
        "and creator_user_id is the discriminator open_rfq_for now filters "
        "on. Captured on a combination the account does not hold. No "
        "create, delete or accept call was made."
    )
    configure_logging()
    try:
        return asyncio.run(_run(args.ticker, args.out, note))
    except Refused as exc:
        print(f"REFUSED -- {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
