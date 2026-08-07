"""Replay a real captured Kalshi stream through the order-book parser.

**This is the test that should have existed from step 3.** Without it the
WebSocket path — the live-data backbone of the whole tool — was completely dead
and 611 tests passed anyway, because every one of them fed the parser
hand-written data in the shape the parser expected.

What the capture found, all three invisible until real frames arrived:

1. **Prices are dollar strings**, `"0.4300"`, not whole cents. The parser did
   `int(price) * 10`, which raises `ValueError` on every real frame. 0 of 257
   frames parsed; all 12 books stayed empty.
2. **Delta fields are `price_dollars` and `delta_fp`**, not `price` and `delta`.
3. **`seq` is per-connection, not per-market.** Twelve tickers shared one sid
   and one strictly-increasing sequence, so per-book gap detection fired on
   nearly every delta and would have resubscribed in a permanent loop.

Plus one calibration error: `MAX_PLAUSIBLE_QUANTITY` was 1,000,000 and a real
WNBA book carried 1,174,194 contracts resting at 1c.

Every assertion here reads `tests/fixtures/ws_orderbook_stream.json`, captured
verbatim off `wss://api.elections.kalshi.com` before any parsing. Nothing in
this file is hand-constructed, which is the entire point.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.kalshi.orderbook import (
    MAX_PLAUSIBLE_QUANTITY,
    MalformedBookMessage,
    OrderBook,
)

FIXTURE = Path(__file__).parent / "fixtures" / "ws_orderbook_stream.json"

BOOK_TYPES = ("orderbook_snapshot", "orderbook_delta")


@pytest.fixture(scope="module")
def stream():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def frames(stream):
    return stream["frames"]


def replay(frames) -> tuple[dict[str, OrderBook], list[str]]:
    """Apply every book frame in order, exactly as the feed delivered them."""
    books: dict[str, OrderBook] = {}
    errors: list[str] = []
    for record in frames:
        frame = record["frame"]
        message_type = frame.get("type")
        if message_type not in BOOK_TYPES:
            continue
        payload = frame.get("msg") or {}
        ticker = payload.get("market_ticker")
        if not ticker:
            continue
        book = books.setdefault(ticker, OrderBook(ticker))
        try:
            if message_type == "orderbook_snapshot":
                book.apply_snapshot(payload, frame.get("seq"), record["received_ms"])
            else:
                book.apply_delta(payload, frame.get("seq"), record["received_ms"])
        except Exception as exc:                       # noqa: BLE001
            errors.append(f"{message_type}: {type(exc).__name__}: {exc}")
    return books, errors


class TestTheCaptureIsReal:
    def test_it_contains_both_snapshots_and_deltas(self, stream):
        """A capture with no deltas would test nothing about the delta path."""
        assert stream["counts"]["orderbook_snapshot"] > 0
        assert stream["counts"]["orderbook_delta"] > 10

    def test_prices_arrive_as_dollar_strings(self, frames):
        """The specific fact the parser got wrong."""
        snapshot = next(
            f["frame"] for f in frames
            if f["frame"].get("type") == "orderbook_snapshot"
        )
        price, _size = snapshot["msg"]["yes_dollars_fp"][0]
        assert isinstance(price, str), "a str, not an int -- int(price) raises"
        assert "." in price, f"dollars like '0.0100', got {price!r}"

    def test_delta_fields_are_price_dollars_and_delta_fp(self, frames):
        delta = next(
            f["frame"] for f in frames
            if f["frame"].get("type") == "orderbook_delta"
        )
        assert "price_dollars" in delta["msg"]
        assert "delta_fp" in delta["msg"]
        assert "price" not in delta["msg"], "the name the parser assumed"
        assert "delta" not in delta["msg"]

    def test_seq_lives_on_the_frame_not_the_payload(self, frames):
        delta = next(
            f["frame"] for f in frames
            if f["frame"].get("type") == "orderbook_delta"
        )
        assert "seq" in delta
        assert "seq" not in delta["msg"]


class TestReplay:
    """The headline: real frames must actually parse."""

    def test_every_frame_applies_without_error(self, frames):
        _books, errors = replay(frames)
        assert not errors, f"{len(errors)} frames failed: {errors[:3]}"

    def test_every_book_ends_with_levels(self, frames):
        """Before the fix this was 0 of 12, silently."""
        books, _ = replay(frames)
        assert books
        empty = [t for t, b in books.items() if not b.yes_bids and not b.no_bids]
        assert not empty, f"books that parsed to nothing: {empty}"

    def test_prices_land_inside_the_tradeable_range(self, frames):
        books, _ = replay(frames)
        for ticker, book in books.items():
            for price in list(book.yes_bids) + list(book.no_bids):
                assert 0 <= price <= 1000, f"{ticker}: {price} tenths"

    def test_a_penny_level_is_read_as_one_cent_not_one_dollar(self, frames):
        """The units check with teeth. `"0.0100"` is 10 tenths; misreading it
        as dollars-per-contract would put it at 1000."""
        books, _ = replay(frames)
        assert any(10 in book.yes_bids or 10 in book.no_bids
                   for book in books.values()), "no 1c level found in the capture"

    def test_derived_ask_identity_holds_on_real_books(self, frames):
        """yes_ask = 1000 - best_no_bid, the identity every EV figure rests on."""
        books, _ = replay(frames)
        checked = 0
        for book in books.values():
            no_bid, yes_ask = book.best_no_bid, book.best_yes_ask
            if no_bid is None or yes_ask is None:
                continue
            assert yes_ask + no_bid == 1000
            checked += 1
        assert checked > 0, "no book had both sides quoted"

    def test_real_quantities_are_within_the_plausible_bound(self, frames):
        """The bound was 1,000,000 and a real book carried 1,174,194."""
        largest = 0.0
        for record in frames:
            payload = record["frame"].get("msg") or {}
            for key in ("yes_dollars_fp", "no_dollars_fp"):
                for _price, size in payload.get(key) or []:
                    largest = max(largest, float(size))
        assert largest > 1_000_000, "capture no longer exercises the old bound"
        assert largest < MAX_PLAUSIBLE_QUANTITY


class TestSequenceSemantics:
    """`seq` counts the connection, not the market."""

    def test_one_sid_serves_every_subscribed_ticker(self, frames):
        sids, tickers = set(), set()
        for record in frames:
            frame = record["frame"]
            if frame.get("type") not in BOOK_TYPES:
                continue
            sids.add(frame.get("sid"))
            tickers.add((frame.get("msg") or {}).get("market_ticker"))
        assert len(tickers) > 1
        assert len(sids) == 1, (
            f"{len(tickers)} tickers arrived on {len(sids)} sid(s) -- per-book "
            f"sequence tracking assumes one sid per ticker"
        )

    def test_sequence_is_strictly_increasing_across_all_markets(self, frames):
        seqs = [
            f["frame"]["seq"] for f in frames
            if f["frame"].get("type", "").startswith("orderbook")
        ]
        assert all(b > a for a, b in zip(seqs, seqs[1:]))

    def test_per_book_gap_detection_would_fire_constantly(self, frames):
        """Why the check moved to the connection. Reconstructs the old
        per-book rule and counts how often it would have tripped."""
        last_by_ticker: dict[str, int] = {}
        false_gaps = 0
        for record in frames:
            frame = record["frame"]
            if frame.get("type") != "orderbook_delta":
                continue
            ticker = (frame.get("msg") or {}).get("market_ticker")
            seq = frame.get("seq")
            if ticker is None or seq is None:
                continue
            previous = last_by_ticker.get(ticker)
            if previous is not None and seq != previous + 1:
                false_gaps += 1
            last_by_ticker[ticker] = seq

        assert false_gaps > 10, (
            "the old per-book rule should trip repeatedly on a real "
            "multi-ticker stream; if it does not, this test has gone stale"
        )

    def test_the_book_no_longer_raises_on_a_shared_sequence(self, frames):
        """The fix, asserted directly: interleaved seq no longer breaks a book."""
        _books, errors = replay(frames)
        assert not [e for e in errors if "SequenceGap" in e]


class TestMalformedStillRaises:
    """The fix must not have turned a loud failure into a quiet one."""

    def test_a_renamed_price_field_raises_naming_what_was_tried(self):
        book = OrderBook("T")
        with pytest.raises(MalformedBookMessage) as exc:
            book.apply_delta(
                {"side": "yes", "px": "0.43", "delta_fp": "10"}, 1, 0
            )
        assert "price_dollars" in str(exc.value)

    def test_a_renamed_levels_field_raises(self):
        book = OrderBook("T")
        with pytest.raises(MalformedBookMessage) as exc:
            book.apply_snapshot({"yes_levels_v2": [], "no_dollars_fp": []}, 1, 0)
        assert "yes_dollars_fp" in str(exc.value)

    def test_a_cents_style_price_is_refused_not_silently_rescaled(self):
        """If Kalshi ever switches to whole cents, 43 becomes 43,000 tenths and
        must fail the range check rather than price a contract at 100x."""
        book = OrderBook("T")
        with pytest.raises(MalformedBookMessage) as exc:
            book.apply_snapshot(
                {"yes_dollars_fp": [[43, "10"]], "no_dollars_fp": []}, 1, 0
            )
        assert "outside 0..1000" in str(exc.value)
