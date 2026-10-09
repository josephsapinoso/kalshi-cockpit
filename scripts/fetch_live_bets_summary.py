"""Print ONLY the counts of `/api/bets` -- the expected-vs-won blocks -- from the
backend loopback, for a log that may be public.

    flyctl ssh console -a kalshi-cockpit \\
      -C "python /app/scripts/fetch_live_bets_summary.py"

Why a second script beside `fetch_live_route.py`
------------------------------------------------
`fetch_live_route.py /api/bets` prints the whole payload: every settled row
with its ticker, price and result. That is right for a laptop terminal and
wrong for a GitHub Actions log on a public repo (`.github/workflows/instrument.yml`
runs this from a phone, with no Fly login on any laptop). Joe's standing rule
is that operator data never leaves the box into anything shared, so this
script keeps the rows on the box and prints the two blocks that carry no row:

- `summary`: per kind (combo, single), W/L counts and `expected_block` --
  n, expected wins at the prices paid, wins, the +/- 2 sd range, `too_few`,
  and the same per price bucket (#287).
- `by_source`: the same block per pick-source tag (ADR 0193).

Nothing else is printed: no `rows`, no ticker, no price, no label, no date.
The key walk below refuses any key that is not on its allowlist, so a new
field added to those blocks upstream is dropped here rather than leaked.

GET-only by construction: the one request is `fetch_live_route.fetch`, whose
`urlopen` call takes no `data` and no `Request`, pinned by
`tests/test_fetch_live_route.py`; this module adds no request of its own.

What this does not establish
----------------------------
- Nothing about any single bet. The blocks are aggregates by design.
- Nothing about freshness or the right of any number; it prints what the
  backend served at that instant (`fetch_live_route.py`'s caveats apply).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fetch_live_route import BASE_URL, fetch, resolve_url  # noqa: E402

#: The keys an `expected_block` may carry on the way out. Anything else is
#: dropped, not printed.
BLOCK_KEYS = frozenset({
    "n", "expected", "won", "range_low", "range_high", "too_few", "label",
    "buckets", "excluded_from_expected", "source", "lost", "kind",
})

TOP_KEYS = ("summary", "by_source")


def scrub(value: Any) -> Any:
    """Keep only allowlisted keys, at every depth; lists are scrubbed per item."""
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items() if k in BLOCK_KEYS or isinstance(v, (dict, list))}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


def summary_of(payload: dict) -> dict:
    """The two aggregate blocks, scrubbed; a missing block is reported absent."""
    out: dict[str, Any] = {}
    for key in TOP_KEYS:
        block = payload.get(key)
        out[key] = scrub(block) if isinstance(block, (dict, list)) else "absent"
    return out


def main() -> int:
    url = resolve_url("/api/bets")
    status, body = fetch(url)
    print(f"HTTP {status} {BASE_URL}/api/bets", file=sys.stderr)
    if not (200 <= status < 300):
        print(f"backend answered {status}; nothing printed", file=sys.stderr)
        return 1
    payload = json.loads(body.decode("utf-8"))
    print(json.dumps(summary_of(payload), indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
