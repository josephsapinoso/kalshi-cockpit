"""`scripts/read_own_rfqs.py` reads the venue's open-RFQ count correctly (#314).

The fixture is the script's own first capture (2026-10-05 ~19:40Z, live
account, GET only), redacted per Joe's (A) to #315: every value except
`status` and `created_ts` is the string REDACTED.

What these tests establish: the summary the script printed is what its own
rows give back; the open-only read and the full read agree on the open
count; no ticker or id survived; and redaction keeps which fields were
present.

What they do not establish: anything about a later moment (one reading, not
a rate), or that `user_filter=self` is complete -- see the script's
docstring.
"""

from __future__ import annotations

import json
import re

from pathlib import Path

from scripts.read_own_rfqs import MAX_OPEN_RFQS, redact_row, summarise  # noqa: I001

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "combo_rfq_list_own.json"


def _load() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _query(name: str) -> dict:
    (q,) = [q for q in _load()["queries"] if q["name"] == name]
    return q


def _rows(q: dict) -> list[dict]:
    return [r for page in q["pages"] for r in page["rfqs"]]


class TestTheCountIsTheVenues:
    def test_an_open_only_read_recomputes_to_its_printed_summary(self):
        for name in ("self+open", "self+open+shard1"):
            q = _query(name)
            assert summarise(_rows(q), truncated=False) == q["summary"]

    def test_every_row_of_an_open_only_read_is_open(self):
        rows = _rows(_query("self+open"))
        assert rows and all(r["status"] == "open" for r in rows)

    def test_the_full_read_agrees_on_the_open_count(self):
        assert _query("self")["summary"]["open"] == _query("self+open")["summary"]["open"]

    def test_headroom_is_the_cap_minus_open(self):
        s = _query("self+open")["summary"]
        assert s["headroom"] == MAX_OPEN_RFQS - s["open"]

    def test_a_truncated_read_claims_no_headroom(self):
        assert summarise([{"status": "open"}], truncated=True)["headroom"] is None

    def test_nothing_open_has_no_oldest_stamp(self):
        assert summarise([{"status": "closed", "created_ts": "x"}], truncated=False)[
            "oldest_open_created_ts"
        ] is None


class TestNothingIdentifyingSurvived:
    def test_no_ticker_shaped_string_in_the_file(self):
        assert not re.search(r"KX[A-Z0-9]", FIXTURE.read_text(encoding="utf-8"))

    def test_only_status_and_created_ts_are_verbatim(self):
        for q in _load()["queries"]:
            for row in _rows(q):
                for key, value in row.items():
                    if key not in ("status", "created_ts"):
                        assert value == "REDACTED", (q["name"], key)
            for page in q["pages"]:
                assert page["cursor"] in (None, "", "REDACTED")

    def test_redaction_keeps_which_fields_were_present(self):
        row = {"id": "abc", "status": "open", "created_ts": "t", "market_ticker": "KXMVE-1"}
        assert redact_row(row) == {
            "id": "REDACTED", "status": "open", "created_ts": "t",
            "market_ticker": "REDACTED",
        }
