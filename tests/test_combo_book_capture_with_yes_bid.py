"""A real combination order book with a resting YES bid, read through the
same path `/api/hedge` reads a held combination's exit (#107, review D9).

Until this file, every test that exercised the `bid` state of
`hedge.combo_book_state` fed it a hand-built literal. The wire-format rule
(CLAUDE.md, Conventions) says wire tests load captured payloads, and D9 of
the #95 review named the gap. This is the capture.

Where the capture came from
---------------------------
`tests/fixtures/combo_orderbook_with_yes_bid.json` is one public,
unauthenticated `GET /markets/{ticker}/orderbook` response, taken
2026-09-24 on a combination the account HELD. That breaks the default of the
2026-09-24 held-ticker lesson (capture on a market the account does not
hold), and it is deliberate: 0 of 45 non-held combination books read the same
evening carried a YES level (#107, comment of 2026-09-24), and Joe
authorised capturing a held book with its ticker redacted. The response body
carries no ticker, leg or account field; the request's ticker is a
placeholder. `TestTheCaptureLeaksNothing` pins that.

What this establishes
---------------------
- The venue lists each side's levels in ASCENDING price order, and a YES
  level at a whole tenth parses to the `bid` state with its size.
- A priced NO side beside it does not change the YES reading.

What this does not establish
----------------------------
- How often a combination carries a YES bid. One book, one moment.
- That a resting bid would fill at its size when Joe sells into it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from backend import hedge

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "combo_orderbook_with_yes_bid.json"
PLACEHOLDER = "KXMVECROSSCATEGORY-REDACTED-HELD"
NOW_MS = 1_700_000_000_000


def load() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def reader(payload):
    async def _read(ticker: str):
        return payload

    return _read


class TestTheCaptureIsAReadBook:
    def test_the_capture_carries_a_yes_level_and_a_no_side(self):
        book = load()["response"]["orderbook_fp"]
        assert book["yes_dollars"], "the capture must carry a resting YES level"
        assert book["no_dollars"], "the capture must carry a priced NO side"

    def test_the_venue_lists_levels_ascending_so_the_best_is_last(self):
        book = load()["response"]["orderbook_fp"]
        for side in ("yes_dollars", "no_dollars"):
            prices = [float(p) for p, _ in book[side]]
            assert prices == sorted(prices), side

    async def test_the_captured_yes_level_reads_as_a_bid_with_its_size(self):
        book = load()["response"]["orderbook_fp"]
        best_price, best_size = book["yes_dollars"][-1]
        combo_book, reason = await hedge.combo_book_state(
            PLACEHOLDER, read_combo_book=reader(book), now_ms=NOW_MS
        )
        assert reason is None
        assert combo_book["state"] == hedge.COMBO_BOOK_BID
        assert combo_book["size"] == float(best_size)
        # "0.0130" dollars is 13 tenths of a cent; a literal, so a parser that
        # read the wrong end of the ascending list, or rounded, would fail.
        assert best_price == "0.0130"
        assert combo_book["price_display"] == "1.3c"


class TestTheCaptureLeaksNothing:
    """The 2026-09-24 lesson: the market a fixture is captured on is itself
    operator data. The only KXMVE ticker in the file is the placeholder."""

    def test_no_combination_ticker_but_the_placeholder(self):
        text = FIXTURE.read_text(encoding="utf-8")
        tickers = set(re.findall(r"KXMVE[A-Z0-9-]*", text))
        assert tickers <= {PLACEHOLDER, "KXMVECROSSCATEGORY"}, tickers

    def test_the_response_carries_nothing_but_the_book(self):
        doc = load()
        assert doc["ticker_redacted"] is True
        assert set(doc["response"]) == {"orderbook_fp"}
        assert set(doc["response"]["orderbook_fp"]) == {"yes_dollars", "no_dollars"}
