"""Order book tests, in the wire format Kalshi actually sends.

**Rewritten after a capture proved the previous version wrong.** Every test here
used to build books from hand-written whole-cent integers (`[[45, 100.0]]`) and
delta messages keyed `price`/`delta`. None of those shapes exist. The live feed
sends dollar strings (`[["0.4500", "100.00"]]`) under `yes_dollars_fp`, and
deltas keyed `price_dollars`/`delta_fp`.

The consequence of the old shape was not a failing test — it was 17 passing
tests over a parser that raised `ValueError` on every real frame. The books were
empty in production and green in CI, which is the exact failure this project
inherited from its predecessor and wrote a rule about.

The shapes below are copied from `tests/fixtures/ws_orderbook_stream.json`.
`tests/test_ws_replay.py` replays that capture end to end; this file covers the
edge cases the capture happens not to contain.
"""

from __future__ import annotations

import pytest

from backend.kalshi.orderbook import (
    MAX_PLAUSIBLE_QUANTITY,
    MalformedBookMessage,
    OrderBook,
)


def levels(*pairs: tuple[float, float]) -> list[list[str]]:
    """`(dollars, size)` pairs in the wire's own string form."""
    return [[f"{price:.4f}", f"{size:.2f}"] for price, size in pairs]


def snapshot(yes: list[list[str]], no: list[list[str]]) -> dict:
    """A snapshot in the captured shape."""
    return {"yes_dollars_fp": yes, "no_dollars_fp": no}


def delta(side: str, dollars: float, size: float) -> dict:
    """A delta in the captured shape: one price level, one signed size change."""
    return {
        "side": side,
        "price_dollars": f"{dollars:.4f}",
        "delta_fp": f"{size:.2f}",
    }


@pytest.fixture
def book() -> OrderBook:
    b = OrderBook(ticker="KXMLBGAME-26AUG092020HOUSD-HOU")
    b.apply_snapshot(
        snapshot(levels((0.45, 100.0), (0.44, 250.0)), levels((0.52, 80.0))),
        seq=1, observed_ms=1000,
    )
    return b


class TestSnapshot:
    def test_dollar_prices_become_tenths(self, book):
        """`"0.4500"` is 450 tenths. The old parser did `int("0.4500")`."""
        assert set(book.yes_bids) == {450, 440}
        assert set(book.no_bids) == {520}

    def test_deci_cent_prices_survive(self):
        """~25% of Kalshi markets tick in half-cents; whole cents would lose it."""
        b = OrderBook("T")
        b.apply_snapshot(snapshot(levels((0.5050, 10.0)), []), seq=1, observed_ms=0)
        assert 505 in b.yes_bids

    def test_quantities_stay_fractional(self):
        b = OrderBook("T")
        b.apply_snapshot(snapshot(levels((0.45, 17.38)), []), seq=1, observed_ms=0)
        assert b.yes_bids[450] == pytest.approx(17.38)

    def test_zero_quantity_levels_are_dropped(self):
        b = OrderBook("T")
        b.apply_snapshot(
            snapshot(levels((0.45, 0.0)), levels((0.52, 5.0))), seq=1, observed_ms=0
        )
        assert 450 not in b.yes_bids

    def test_snapshot_replaces_rather_than_merges(self, book):
        book.apply_snapshot(
            snapshot(levels((0.30, 10.0)), levels((0.70, 10.0))),
            seq=2, observed_ms=2000,
        )
        assert set(book.yes_bids) == {300}, "stale levels survived a snapshot"

    def test_empty_snapshot_empties_the_book(self, book):
        """A genuinely emptied book must not stay populated.

        The previous project ignored empty snapshots to protect against
        reconnect wipes, which meant a market that really had emptied kept
        quoting prices that no longer existed.
        """
        book.apply_snapshot(snapshot([], []), seq=2, observed_ms=2000)
        assert book.best_yes_bid is None
        assert book.best_yes_ask is None


class TestRenamedFieldsRaise:
    """The guard against the bug that silently emptied every book for a year."""

    def test_missing_yes_levels_raises_naming_what_it_tried(self):
        b = OrderBook("T")
        with pytest.raises(MalformedBookMessage) as exc:
            b.apply_snapshot({"no_dollars_fp": []}, seq=1, observed_ms=0)
        assert "yes_dollars_fp" in str(exc.value)
        assert "Tried" in str(exc.value)

    def test_missing_no_levels_raises(self):
        b = OrderBook("T")
        with pytest.raises(MalformedBookMessage):
            b.apply_snapshot({"yes_dollars_fp": []}, seq=1, observed_ms=0)

    def test_a_renamed_field_never_yields_a_quietly_empty_book(self):
        """The exact shape of the original failure, asserted directly."""
        b = OrderBook("T")
        with pytest.raises(MalformedBookMessage):
            b.apply_snapshot(
                {"yes_dollars_v2": levels((0.45, 1.0)), "no_dollars_v2": []},
                seq=1, observed_ms=0,
            )
        assert b.best_yes_bid is None

    def test_an_unknown_delta_price_field_raises_naming_what_it_tried(self):
        b = OrderBook("T")
        with pytest.raises(MalformedBookMessage) as exc:
            b.apply_delta(
                {"side": "yes", "px_v2": "0.45", "delta_fp": "10"}, seq=1, observed_ms=0
            )
        assert "price_dollars" in str(exc.value)
        assert "Tried" in str(exc.value)

    def test_an_unknown_delta_size_field_raises(self):
        b = OrderBook("T")
        with pytest.raises(MalformedBookMessage) as exc:
            b.apply_delta(
                {"side": "yes", "price_dollars": "0.45", "size_v2": "10"},
                seq=1, observed_ms=0,
            )
        assert "delta_fp" in str(exc.value)


class TestUnitsChangesAreRefused:
    """A price misread by 100x is the worst silent failure available here."""

    def test_a_whole_cent_price_is_refused_not_rescaled(self):
        b = OrderBook("T")
        with pytest.raises(MalformedBookMessage) as exc:
            b.apply_snapshot(snapshot([[45, "10"]], []), seq=1, observed_ms=0)
        assert "outside 0..1000" in str(exc.value)

    def test_an_unparseable_price_raises(self):
        b = OrderBook("T")
        with pytest.raises(MalformedBookMessage):
            b.apply_snapshot(snapshot([["not-a-price", "10"]], []), seq=1, observed_ms=0)


class TestDeltas:
    def test_a_delta_adds_to_an_existing_level(self, book):
        book.apply_delta(delta("yes", 0.45, 50.0), seq=2, observed_ms=1100)
        assert book.yes_bids[450] == pytest.approx(150.0)

    def test_a_delta_creates_a_new_level(self, book):
        book.apply_delta(delta("yes", 0.40, 25.0), seq=2, observed_ms=1100)
        assert book.yes_bids[400] == pytest.approx(25.0)

    def test_a_level_emptied_to_zero_is_removed(self, book):
        book.apply_delta(delta("yes", 0.45, -100.0), seq=2, observed_ms=1100)
        assert 450 not in book.yes_bids

    def test_an_oversold_level_is_removed_not_left_negative(self, book):
        book.apply_delta(delta("yes", 0.45, -500.0), seq=2, observed_ms=1100)
        assert 450 not in book.yes_bids

    def test_an_implausible_quantity_raises(self, book):
        """The bound catches a units error, not a large order. Real books carry
        over a million contracts at penny levels, so it sits well above that."""
        with pytest.raises(MalformedBookMessage):
            book.apply_delta(
                delta("yes", 0.45, MAX_PLAUSIBLE_QUANTITY * 2), seq=2, observed_ms=1100
            )

    def test_a_seven_figure_level_is_accepted(self):
        """A real WNBA snapshot carried 1,174,194 contracts at 1c and the old
        1,000,000 bound rejected it."""
        b = OrderBook("T")
        b.apply_snapshot(snapshot(levels((0.01, 1_174_194.0)), []), seq=1, observed_ms=0)
        assert b.yes_bids[10] == pytest.approx(1_174_194.0)

    @pytest.mark.parametrize("bad_side", ["YES", "buy", None, ""])
    def test_an_unknown_side_raises(self, book, bad_side):
        with pytest.raises(MalformedBookMessage):
            book.apply_delta(
                {"side": bad_side, "price_dollars": "0.45", "delta_fp": "1"},
                seq=2, observed_ms=1100,
            )


class TestSequenceIsNotCheckedPerBook:
    """A correction, asserted so it cannot silently revert.

    `seq` is a per-connection counter. A capture of twelve tickers showed one
    shared sid and one strictly-increasing sequence, so a book that checked
    `seq` against its own last value would fault on every frame belonging to
    another market. Gap detection lives in `KalshiWebSocket`; see
    `tests/test_ws_gaps.py`.
    """

    def test_an_interleaved_sequence_does_not_raise(self, book):
        """Frames 2 and 7 for this market, with 3-6 belonging to others."""
        book.apply_delta(delta("yes", 0.45, 10.0), seq=2, observed_ms=1100)
        book.apply_delta(delta("yes", 0.45, 10.0), seq=7, observed_ms=1200)
        assert book.yes_bids[450] == pytest.approx(120.0)

    def test_the_book_still_records_the_sequence(self, book):
        book.apply_delta(delta("yes", 0.45, 1.0), seq=9, observed_ms=1100)
        assert book.last_seq == 9


class TestDerivedAsks:
    """The identity verified against 2,145 real quotes at capture time."""

    def test_yes_ask_is_the_complement_of_the_best_no_bid(self, book):
        assert book.best_no_bid == 520
        assert book.best_yes_ask == 480

    def test_the_ask_is_worse_than_the_bid(self, book):
        assert book.best_yes_ask > book.best_yes_bid

    def test_depth_at_the_ask_is_the_opposing_bids_size(self, book):
        """There is no ask book. An edge you cannot fill is not an edge."""
        assert book.depth_at_ask("yes") == pytest.approx(80.0)
        assert book.depth_at_ask("no") == pytest.approx(100.0)

    def test_an_empty_opposing_side_yields_no_ask(self):
        b = OrderBook("T")
        b.apply_snapshot(snapshot(levels((0.45, 10.0)), []), seq=1, observed_ms=0)
        assert b.best_yes_ask is None
        assert b.depth_at_ask("yes") is None


class TestQuotability:
    """Three separate refusals, all of which must block pricing."""

    def test_a_fresh_book_is_quotable(self, book):
        assert book.is_quotable(now_ms=1_005, max_age_ms=30_000)

    def test_a_stale_book_is_not(self, book):
        assert not book.is_quotable(now_ms=1_000 + 60_000, max_age_ms=30_000)

    def test_a_never_populated_book_is_not(self):
        assert not OrderBook("T").is_quotable(now_ms=1, max_age_ms=30_000)

    def test_an_invalid_book_is_not(self, book):
        book.invalid = True
        assert not book.is_quotable(now_ms=1_005, max_age_ms=30_000)

    def test_age_is_none_before_any_update(self):
        assert OrderBook("T").age_ms(now_ms=5_000) is None
