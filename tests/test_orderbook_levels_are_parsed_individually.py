"""A book read survives a level it cannot price, and a bid Joe would receive is
refused rather than rounded up (#106; the 2026-09-19 review of #95, D1/D2).

What this establishes
---------------------
- A snapshot carrying `[['0.0510','38709.00'], ['0.0004','1.00']]` yields the
  5.10c level at 38,709 deep and ONE unpriced level with its raw price, and
  raises nothing. Before #106 `_parse_price` raised `MalformedBookMessage` on
  the dust level and `read_books` rendered the whole book as "no bid".
- `"0.0038"` is never carried as 4 tenths. `dollars_to_tenths` rounds HALF_UP
  (right for a price you pay); the book path now uses `dollars_to_tenths_exact`
  and reports the level as unpriced instead.
- `"0.0000"` (settled, at-or-below zero) is dropped and counted, not raised.
- A delta at an unpriceable price is recorded, not applied and not raised.
- The three states stay distinct: no bid (`best_yes_bid is None`, no unpriced
  interest), unpriceable interest (`has_unpriced_interest("yes")`), and a
  malformed read (still raises).

What it does not establish
--------------------------
- That any committed capture carries such a level: the first real one is
  #107's. The inputs here are the shape the review reproduced, hand-built and
  labelled as such, because the point is the parser's behaviour on inputs the
  captures do not yet contain.
- Anything about the screen. `/hedge` rendering the unpriced state is #95.
"""

from __future__ import annotations

import pytest

from backend.core.prices import (
    REFUSED_FINER_THAN_TENTHS,
    REFUSED_UNREADABLE,
    dollars_to_tenths,
    dollars_to_tenths_exact,
)
from backend.kalshi.orderbook import MalformedBookMessage, OrderBook


def snapshot(yes, no):
    return {"yes_dollars": yes, "no_dollars": no}


class TestTheExactReader:
    def test_a_tenths_price_passes_through(self):
        assert dollars_to_tenths_exact("0.0510") == (51, None)  # 5.10c = 51 tenths

    def test_a_centi_cent_price_is_refused_not_rounded(self):
        # HALF_UP would say 4; the venue never offered 0.4c.
        assert dollars_to_tenths("0.0038") == 4
        assert dollars_to_tenths_exact("0.0038") == (None, REFUSED_FINER_THAN_TENTHS)

    def test_dust_is_refused_not_zeroed(self):
        assert dollars_to_tenths("0.0004") == 0
        assert dollars_to_tenths_exact("0.0004") == (None, REFUSED_FINER_THAN_TENTHS)

    def test_garbage_is_unreadable(self):
        assert dollars_to_tenths_exact("not-a-price") == (None, REFUSED_UNREADABLE)


class TestADustLevelDoesNotAbortTheBook:
    # The review's reproduction: Joe's real 5.10c / 38,709 exit with one
    # sub-half-tenth order behind it. Hand-built to that shape; see docstring.
    LEVELS = [["0.0510", "38709.00"], ["0.0004", "1.00"]]

    def test_the_good_level_is_read(self):
        b = OrderBook("KXMVE-X")
        b.apply_snapshot(snapshot(self.LEVELS, []), seq=1, observed_ms=0)
        assert b.best_yes_bid == 51
        assert b.yes_bids[51] == pytest.approx(38709.0)

    def test_the_dust_level_is_counted_with_its_raw_price(self):
        b = OrderBook("KXMVE-X")
        b.apply_snapshot(snapshot(self.LEVELS, []), seq=1, observed_ms=0)
        assert len(b.unpriced) == 1
        assert b.unpriced[0].side == "yes"
        assert b.unpriced[0].price_raw == "0.0004"
        assert b.unpriced[0].quantity == pytest.approx(1.0)
        assert b.has_unpriced_interest("yes")
        assert not b.has_unpriced_interest("no")


class TestAReceivedBidIsNeverRoundedUp:
    def test_a_centi_cent_bid_is_unpriced_not_four_tenths(self):
        b = OrderBook("KXMVE-X")
        b.apply_snapshot(snapshot([["0.0038", "24900.00"]], []), seq=1, observed_ms=0)
        assert b.best_yes_bid is None
        assert 4 not in b.yes_bids
        assert b.has_unpriced_interest("yes")

    def test_a_settled_price_is_dropped_not_raised(self):
        b = OrderBook("T")
        b.apply_snapshot(snapshot([["0.0000", "5.00"]], []), seq=1, observed_ms=0)
        assert b.best_yes_bid is None
        assert b.has_unpriced_interest("yes")


class TestTheThreeStatesStayDistinct:
    def test_no_bid_at_all(self):
        b = OrderBook("T")
        b.apply_snapshot(snapshot([], []), seq=1, observed_ms=0)
        assert b.best_yes_bid is None
        assert not b.has_unpriced_interest("yes")

    def test_a_snapshot_replaces_the_unpriced_list(self):
        b = OrderBook("T")
        b.apply_snapshot(snapshot([["0.0004", "1.00"]], []), seq=1, observed_ms=0)
        assert b.has_unpriced_interest("yes")
        b.apply_snapshot(snapshot([["0.4500", "1.00"]], []), seq=2, observed_ms=1)
        assert not b.has_unpriced_interest("yes")

    def test_a_malformed_level_still_raises(self):
        b = OrderBook("T")
        with pytest.raises(MalformedBookMessage):
            b.apply_snapshot(snapshot([["not-a-price", "1.00"]], []), seq=1, observed_ms=0)

    def test_a_units_change_still_raises(self):
        # `45` meaning cents must announce itself, never empty the book level
        # by level.
        b = OrderBook("T")
        with pytest.raises(MalformedBookMessage) as exc:
            b.apply_snapshot(snapshot([[45, "10"]], []), seq=1, observed_ms=0)
        assert "outside 0..1000" in str(exc.value)


class TestADeltaAtAnUnpriceablePrice:
    def test_is_recorded_not_applied_and_not_raised(self):
        b = OrderBook("T")
        b.apply_snapshot(snapshot([["0.4500", "10.00"]], []), seq=1, observed_ms=0)
        b.apply_delta(
            {"side": "yes", "price_dollars": "0.0004", "delta_fp": "3.00"},
            seq=2, observed_ms=1,
        )
        assert b.yes_bids == {450: pytest.approx(10.0)}
        assert b.has_unpriced_interest("yes")
        assert b.unpriced[0].quantity == pytest.approx(3.0)
        assert b.last_seq == 2
