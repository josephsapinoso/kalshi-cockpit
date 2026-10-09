"""`scripts/fetch_live_bets_summary.py` prints aggregates only, for a public log.

What this establishes: the printed object carries no row and no key outside
the allowlist, however the payload is shaped; the script issues no request of
its own (it borrows `fetch_live_route.fetch`, the GET pinned by
`tests/test_fetch_live_route.py`).
What it does not establish: anything about the live backend.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

from scripts import fetch_live_bets_summary as fbs

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts" / "fetch_live_bets_summary.py"

PAYLOAD = {
    "rows": [
        {"ticker": "KXMVE-SECRET-1", "entry_price_tenths": 48, "label": "a real bet"},
    ],
    "summary": {
        "combo": {
            "won": 20, "lost": 148, "excluded_from_expected": 3,
            "expected": {
                "n": 168, "expected": 19.4, "won": 20, "range_low": 11,
                "range_high": 28, "too_few": False,
                "buckets": [
                    {"label": "under 10c", "n": 90, "expected": 4.1, "won": 5, "too_few": True},
                ],
                "secret_ticker": "KXMVE-SECRET-2",
            },
        },
        "single": {"won": 1, "lost": 2, "expected": None},
    },
    "by_source": {
        "combo": [
            {"source": "friend", "label": "A friend's parlay", "won": 1, "lost": 30,
             "n": 31, "expected": {"n": 31, "expected": 2.6, "won": 1, "too_few": True},
             "latest_ticker": "KXMVE-SECRET-3"},
        ],
    },
    "open": [{"ticker": "KXMVE-SECRET-4"}],
}


def _all_strings(value) -> set[str]:
    if isinstance(value, dict):
        out: set[str] = set()
        for k, v in value.items():
            out.add(k)
            out |= _all_strings(v)
        return out
    if isinstance(value, list):
        out = set()
        for v in value:
            out |= _all_strings(v)
        return out
    if isinstance(value, str):
        return {value}
    return set()


class TestOnlyAggregatesSurvive:
    def test_no_row_and_no_ticker_is_printed(self):
        out = fbs.summary_of(PAYLOAD)
        text = json.dumps(out)
        assert "SECRET" not in text
        assert "rows" not in out and "open" not in out
        assert "a real bet" not in text

    def test_the_blocks_keep_their_counts(self):
        out = fbs.summary_of(PAYLOAD)
        combo = out["summary"]["combo"]
        assert combo["won"] == 20 and combo["lost"] == 148
        assert combo["expected"]["expected"] == 19.4
        assert combo["expected"]["buckets"][0]["label"] == "under 10c"
        friend = out["by_source"]["combo"][0]
        assert friend["source"] == "friend" and friend["expected"]["too_few"] is True

    def test_every_printed_key_is_on_the_allowlist(self):
        out = fbs.summary_of(PAYLOAD)

        def keys_of(value) -> set[str]:
            if isinstance(value, dict):
                found = set(value)
                for v in value.values():
                    found |= keys_of(v)
                return found
            if isinstance(value, list):
                found = set()
                for v in value:
                    found |= keys_of(v)
                return found
            return set()

        # The kind keys ("combo", "single") are structure, not data; every
        # other key must be on the allowlist.
        assert keys_of(out) <= fbs.BLOCK_KEYS | set(fbs.TOP_KEYS) | {"combo", "single"}
        assert "secret_ticker" not in keys_of(out) and "latest_ticker" not in keys_of(out)

    def test_a_missing_block_is_reported_absent_not_invented(self):
        assert fbs.summary_of({"rows": []}) == {"summary": "absent", "by_source": "absent"}


class TestItAddsNoRequestOfItsOwn:
    def test_the_only_network_call_is_the_fetchers(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        names = {
            node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            for node in ast.walk(tree) if isinstance(node, ast.Call)
        }
        assert "urlopen" not in names and "Request" not in names
        assert "fetch" in names and "resolve_url" in names
        source = SOURCE.read_text(encoding="utf-8")
        assert "httpx" not in source and "requests" not in source
