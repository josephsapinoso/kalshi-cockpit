"""Read how many RFQs the VENUE holds open for this account (#314).

    .venv\\Scripts\\python.exe scripts\\read_own_rfqs.py
    .venv\\Scripts\\python.exe scripts\\read_own_rfqs.py \\
        --capture tests\\fixtures\\combo_rfq_list_own.json

Why this exists
----------------
Kalshi caps an account at 100 open RFQs ("maximum of 100 open RFQs at a
time", Create RFQ docs; `backend/kalshi/rfq.py:MAX_OPEN_RFQS`). Our own
bookkeeping (`inspect_live_db.py own-open-rfqs`) read 97 of 100 on
2026-10-05, but it counts `combo_rfqs` rows we never stamped closed. The
venue can expire an RFQ, after a lifetime it does not document, and nothing
of ours records that. So our count can only overcount, and the
headroom figure has to come from the venue.

This script makes four reads of `GET /communications/rfqs?user_filter=self`,
paginated by cursor: with and without `status=open`, each with and without
`exchange_index=1`. The second axis settles whether an unsharded list misses
the combination shard. Every RFQ we create is a combination on shard 1.

**Read-only.** GET only. No create, no delete, no accept. It cannot open or
close an RFQ or spend anything.

**What is printed and committed carries no ticker and no id.** Joe's (A) to
#315 permits a redacted capture of his own list: `status` and `created_ts`
are kept verbatim, and every other field's value becomes `"REDACTED"`, so
only its presence survives. The cursor is redacted too, because it may
encode an id.

What this does not establish
-----------------------------
- One reading at one moment. It is not a rate, and it says nothing about when
  the venue expires an RFQ. Two readings far enough apart could bound that.
- That `user_filter=self` is complete. It narrowed a market-wide list to our
  rows on 2026-09-24 (`scripts/capture_rfq_list.py`), but the venue could
  drop the parameter silently, as it once already ignored a misnamed one.
  A count of 0 on an account that has asked recently should be read as
  suspect, not as headroom.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import KalshiConfig  # noqa: E402
from backend.kalshi.rest import KalshiRestClient  # noqa: E402
from backend.kalshi.rfq import MAX_OPEN_RFQS  # noqa: E402
from backend.logging_setup import configure_logging  # noqa: E402

RFQS_PATH = "/communications/rfqs"

#: Hard bound on pages per read. 100 rows a page, so 20 pages is 2,000 RFQs,
#: twenty times the cap. A read that hits the bound says so, not a count.
MAX_PAGES = 20

#: Kept verbatim. Every other key's value is replaced.
_KEPT = ("status", "created_ts")

#: The four reads, in print order. The `exchange_index` axis is the
#: comparison #314 asks for.
VARIANTS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("self", {"user_filter": "self"}),
    ("self+open", {"user_filter": "self", "status": "open"}),
    ("self+shard1", {"user_filter": "self", "exchange_index": 1}),
    ("self+open+shard1", {"user_filter": "self", "status": "open", "exchange_index": 1}),
)


def redact_row(row: dict) -> dict:
    """`status` and `created_ts` verbatim; every other value `"REDACTED"`."""
    return {k: (v if k in _KEPT else "REDACTED") for k, v in row.items()}


def summarise(rows: list[dict], *, truncated: bool) -> dict:
    """Counts off one read's rows. `open` is the venue's `status == "open"`.

    `oldest_open_created_ts` is None when nothing is open, never a
    placeholder. A truncated read reports its counts as lower bounds by
    carrying `truncated`. Its numbers are not the venue's totals.
    """
    open_rows = [r for r in rows if r.get("status") == "open"]
    stamps = [r["created_ts"] for r in open_rows if r.get("created_ts")]
    statuses: dict[str, int] = {}
    for r in rows:
        key = str(r.get("status"))
        statuses[key] = statuses.get(key, 0) + 1
    return {
        "rows": len(rows),
        "open": len(open_rows),
        "headroom": None if truncated else MAX_OPEN_RFQS - len(open_rows),
        "by_status": dict(sorted(statuses.items())),
        "oldest_open_created_ts": min(stamps) if stamps else None,
        "truncated": truncated,
    }


async def _read_all(api: KalshiRestClient, params: dict) -> tuple[list[dict], list[dict], bool]:
    """Every page of one read, as (rows, raw pages, truncated)."""
    rows: list[dict] = []
    pages: list[dict] = []
    cursor: Optional[str] = None
    for _ in range(MAX_PAGES):
        query = {**params, "limit": 100}
        if cursor:
            query["cursor"] = cursor
        page = await api.request("GET", RFQS_PATH, params=query)
        pages.append(page)
        rows.extend(page.get("rfqs") or [])
        cursor = page.get("cursor") or None
        if not cursor:
            return rows, pages, False
    return rows, pages, True


def endpoint_for(params: dict) -> str:
    query = "&".join(f"{k}={v}" for k, v in {**params, "limit": 100}.items())
    return f"GET {RFQS_PATH}?{query}"


def build_fixture(reads: dict[str, tuple[list[dict], list[dict], bool]]) -> dict:
    """The redacted capture: each read's request, summary and redacted pages."""
    queries = []
    for name, params in VARIANTS:
        rows, pages, truncated = reads[name]
        queries.append({
            "name": name,
            "endpoint": endpoint_for(params),
            "params": {**params, "limit": 100},
            "summary": summarise(rows, truncated=truncated),
            "pages_at_capture": len(pages),
            # Every page of an open-only read (it is at most the cap), the
            # first page only of a full-history read: the history is
            # hundreds of rows and the counts are in `summary`.
            "pages": [
                {
                    "cursor": "REDACTED" if page.get("cursor") else page.get("cursor"),
                    "rfqs": [redact_row(r) for r in page.get("rfqs") or []],
                }
                for page in (pages if "status" in params else pages[:1])
            ],
        })
    return {
        "endpoint": f"GET {RFQS_PATH}?user_filter=self[&status=open][&exchange_index=1]&limit=100",
        "params": {"user_filter": "self", "limit": 100},
        "queries": queries,
        "redaction": (
            "Joe's (A) to #315. status and created_ts are verbatim. Every "
            "other field's value, every id and ticker included, is the "
            "string REDACTED, so which fields were present survives and "
            "nothing identifying does. A non-empty cursor is REDACTED too."
        ),
    }


async def _run(capture: Optional[Path]) -> int:
    if capture is not None and capture.exists():
        print(f"REFUSED -- refusing to overwrite an existing fixture: {capture}")
        return 2
    config = KalshiConfig.load()
    reads = {}
    async with KalshiRestClient(config) as api:
        for name, params in VARIANTS:
            reads[name] = await _read_all(api, params)
    for name, _ in VARIANTS:
        rows, _pages, truncated = reads[name]
        print(f"{name:18s} {json.dumps(summarise(rows, truncated=truncated))}")
    if capture is not None:
        capture.parent.mkdir(parents=True, exist_ok=True)
        capture.write_text(
            json.dumps(build_fixture(reads), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {capture}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--capture", type=Path, default=None,
        help="also write the redacted capture here (refuses to overwrite)",
    )
    args = parser.parse_args(argv)
    configure_logging()
    return asyncio.run(_run(args.capture))


if __name__ == "__main__":
    sys.exit(main())
