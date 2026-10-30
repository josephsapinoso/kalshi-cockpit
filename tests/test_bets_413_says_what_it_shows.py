"""#413: Your bets says what each number is and isn't, once.

Every fixture is synthetic (round invented prices); nothing is, or may be,
copied from the operator's record.

What this establishes
---------------------
- `bets.count_ranges` counts exactly the served blocks that carry a range
  (not `too_few` ones) and `bets_record` serves it as `range_count`.
- The page prints the range count with the ticket's sentence, the leg-price
  label is the ticket's sentence and the old "at the price paid" is gone,
  Net is labelled once (not in the strip), "in a row" became "in this cell",
  the J4 (A) Open sentence is pinned, and an empty record has one sentence.

What it does NOT establish
--------------------------
That the page draws (`next build` and a browser say that) or that any
range means anything.
"""

from __future__ import annotations

import re
from pathlib import Path

from backend import bets

REPO = Path(__file__).resolve().parents[1]
PAGE = (REPO / "frontend" / "src" / "app" / "bets" / "page.tsx").read_text(
    encoding="utf-8"
)


def _wide():
    """40 bets at 50c, 20 won: expected 20, plenty each side, so a range."""
    return bets.expected_block([(500, i % 2 == 0) for i in range(40)])


def _narrow():
    return bets.expected_block([(500, True)] * 3)


class TestRangeCount:
    def test_counts_only_blocks_that_carry_a_range(self):
        wide, narrow = _wide(), _narrow()
        assert wide["range_low"] is not None and narrow["range_low"] is None
        record = {
            "summary": {
                "single": {"expected": None},
                "combo": {"expected": {**wide, "buckets": [wide, narrow]}},
            },
            "by_source": {"combo": [{"expected": wide}, {"expected": None}]},
            "by_leg_kind": {"leagues": [{"kinds": [{"expected": wide},
                                                   {"expected": narrow}]}]},
            "by_shape": {"price_bands": [wide, narrow], "leg_counts": [wide]},
        }
        # overall + one bucket + one source + one leg cell + band + leg count
        assert bets.count_ranges(record) == 6

    def test_empty_record_counts_zero(self):
        assert bets.count_ranges({}) == 0

    def test_the_record_serves_it(self):
        import inspect

        src = inspect.getsource(bets.bets_record)
        assert 'record["range_count"] = count_ranges(record)' in src

    def test_page_prints_the_count_with_the_sentence(self):
        flat = re.sub(r"\s+", " ", PAGE)
        assert "range_count" in PAGE
        assert (
            "on this page; one landing outside by luck alone is normal."
            in flat
        )


class TestLegPriceLabel:
    NEW = (
        "At each leg's own Kalshi price when priced — you paid for the whole "
        "combination, not this leg."
    )

    def test_new_sentence_is_pinned(self):
        assert self.NEW in PAGE

    def test_old_wording_is_refused(self):
        assert "at the price paid" not in PAGE
        assert "in a row before" not in PAGE
        assert "expected losses in this cell" in re.sub(r"\s+", " ", PAGE)


class TestNetOnce:
    def test_net_is_labelled_once(self):
        assert len(re.findall(r"<Term k=.net.>Net</Term>", PAGE)) == 1

    def test_strip_has_no_net_stat(self):
        strip = PAGE[PAGE.index("function RecordStrip"):PAGE.index("const SECTIONS")]
        assert "netShown" not in strip and "netInk" not in strip


class TestOpenLabel:
    SENTENCE = (
        "Open combinations: ${recorded} recorded, ${notYetRecorded} at Kalshi "
        "not yet recorded. Singles you hold at Kalshi aren't shown here."
    )

    def test_j4_sentence_is_pinned(self):
        assert self.SENTENCE in PAGE
        assert "data-open-label" in PAGE

    def test_label_reads_both_counts_from_the_hedge_read(self):
        assert "openLabel(hedge.positions.length, hedge.unrecorded_at_venue.length)" in PAGE

    def test_no_singles_list_is_added(self):
        assert "singles you hold" not in PAGE.lower().replace(
            "singles you hold at kalshi aren't shown here", ""
        )


class TestEmptyState:
    def test_one_empty_sentence(self):
        text = "Nothing has settled since the recorder started watching."
        assert PAGE.count(text) == 1
        assert "data-nothing-settled" in PAGE
        assert "nothingSettled ?" in PAGE


class TestRangeCountLine:
    def test_line_is_drawn_only_when_there_are_ranges(self):
        assert "rangeCount > 0 && (" in PAGE
        assert "data-range-count" in PAGE
        assert "(record as BetsRecord & { range_count?: number }).range_count" in PAGE
