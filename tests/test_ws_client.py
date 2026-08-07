"""`KalshiWebSocket` frame handling, driven without a socket.

This class had **no tests at all** until now, which is how two silent failures
survived it. Both were found by running it against the live feed, not by
reading it:

1. The subscription registry never populated. The `subscribed` ack carries
   `{"channel", "sid"}` and no ticker; the handler read `msg.market_tickers`
   and `msg.market_ticker`, neither of which exists there. `_resubscribe` could
   therefore never unsubscribe, and the gap-recovery path was dead code.
2. Kalshi acks the **first** subscribe on a connection with `subscribed` and
   every one after it with `ok` — and `ok.msg` *does* carry `market_tickers`.
   Handling only `subscribed` registered 1 of 6 tickers in a live run.

Frame shapes below are copied from `tests/fixtures/ws_orderbook_stream.json`.
No socket is involved: `_handle` is fed strings directly.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from backend.config import KalshiConfig
from backend.kalshi.ws import KalshiWebSocket, ResyncRequired

TICKERS = ["KXMLBGAME-A", "KXMLBGAME-B", "KXMLBGAME-C"]


@pytest.fixture
def ws(tmp_path, monkeypatch):
    """A client with no connection. Auth is never exercised."""
    key = tmp_path / "k.pem"
    key.write_text("not-a-real-key", encoding="utf-8")
    monkeypatch.setattr(
        "backend.kalshi.ws.KalshiAuth", lambda *a, **kw: object()
    )
    config = KalshiConfig(
        api_key="test", private_key_path=key,
        rest_url="https://example.invalid/trade-api/v2",
        ws_url="wss://example.invalid/trade-api/ws/v2",
    )
    return KalshiWebSocket(config, tickers=TICKERS)


def send(ws, frame: dict):
    asyncio.get_event_loop()
    return ws._handle(json.dumps(frame))


def levels(*pairs):
    return [[f"{p:.4f}", f"{s:.2f}"] for p, s in pairs]


def snapshot_frame(ticker, seq, sid=1):
    return {
        "type": "orderbook_snapshot", "sid": sid, "seq": seq,
        "msg": {
            "market_ticker": ticker,
            "yes_dollars_fp": levels((0.45, 100.0)),
            "no_dollars_fp": levels((0.52, 80.0)),
        },
    }


def delta_frame(ticker, seq, size=10.0, sid=1):
    return {
        "type": "orderbook_delta", "sid": sid, "seq": seq,
        "msg": {
            "market_ticker": ticker, "side": "yes",
            "price_dollars": "0.4500", "delta_fp": f"{size:.2f}",
        },
    }


class TestSubscriptionAcks:
    """Both ack shapes must register, or resync cannot address the market."""

    async def test_the_first_ack_is_subscribed_and_names_no_ticker(self, ws):
        ws._pending_subscriptions[1] = "KXMLBGAME-A"
        await send(ws, {
            "type": "subscribed", "id": 1,
            "msg": {"channel": "orderbook_delta", "sid": 1},
        })
        assert ws._ticker_sids["KXMLBGAME-A"] == 1

    async def test_later_acks_are_ok_and_do_name_the_ticker(self, ws):
        """The shape that was missed. Only the first subscribe gets
        `subscribed`; the rest get `ok`, and `ok.msg` carries the ticker."""
        await send(ws, {
            "type": "ok", "id": 2, "sid": 1, "seq": 2,
            "msg": {"market_tickers": ["KXMLBGAME-B"]},
        })
        assert ws._ticker_sids["KXMLBGAME-B"] == 1

    async def test_every_ticker_ends_up_registered(self, ws):
        """The live-run failure, asserted: 1 of 6 registered before the fix."""
        ws._pending_subscriptions[1] = TICKERS[0]
        await send(ws, {
            "type": "subscribed", "id": 1,
            "msg": {"channel": "orderbook_delta", "sid": 1},
        })
        for index, ticker in enumerate(TICKERS[1:], start=2):
            await send(ws, {
                "type": "ok", "id": index, "sid": 1, "seq": index,
                "msg": {"market_tickers": [ticker]},
            })
        assert set(ws._ticker_sids) == set(TICKERS)
        assert not ws._pending_subscriptions

    async def test_one_sid_serves_every_ticker(self, ws):
        """So a reverse sid -> ticker map cannot exist."""
        for index, ticker in enumerate(TICKERS, start=1):
            await send(ws, {
                "type": "ok", "id": index, "sid": 1, "seq": index,
                "msg": {"market_tickers": [ticker]},
            })
        assert ws._sids == {1: set(TICKERS)}


class TestSequenceHandling:
    """`seq` counts the connection, not the market."""

    async def test_interleaved_markets_do_not_look_like_gaps(self, ws):
        """The bug that would have resubscribed in a permanent loop."""
        await send(ws, snapshot_frame("KXMLBGAME-A", 1))
        await send(ws, snapshot_frame("KXMLBGAME-B", 2))
        await send(ws, delta_frame("KXMLBGAME-A", 3))
        await send(ws, delta_frame("KXMLBGAME-B", 4))
        assert not ws._pending_resync
        assert ws._last_seq == 4

    async def test_a_real_gap_flags_a_resync_and_invalidates_every_book(self, ws):
        """A gap names the connection, never the market, so one book cannot be
        singled out for recovery."""
        await send(ws, snapshot_frame("KXMLBGAME-A", 1))
        await send(ws, snapshot_frame("KXMLBGAME-B", 2))
        await send(ws, delta_frame("KXMLBGAME-A", 9))     # 3..8 lost

        assert ws._pending_resync
        assert all(b.invalid for b in ws.books.values())
        assert not ws.quotable_books(max_age_ms=60_000)

    async def test_a_duplicate_frame_is_dropped_not_applied(self, ws):
        """Applying it twice would double-count the delta."""
        await send(ws, snapshot_frame("KXMLBGAME-A", 1))
        await send(ws, delta_frame("KXMLBGAME-A", 2, size=10.0))
        before = dict(ws.book("KXMLBGAME-A").yes_bids)
        await send(ws, delta_frame("KXMLBGAME-A", 2, size=10.0))
        assert ws.book("KXMLBGAME-A").yes_bids == before

    async def test_control_frames_participate_in_the_sequence(self, ws):
        """`ok` frames carry `seq` in the capture. Skipping them would let one
        consume a number unnoticed and make the NEXT frame look like a gap."""
        await send(ws, snapshot_frame("KXMLBGAME-A", 1))
        await send(ws, {
            "type": "ok", "id": 2, "sid": 1, "seq": 2,
            "msg": {"market_tickers": ["KXMLBGAME-B"]},
        })
        await send(ws, delta_frame("KXMLBGAME-A", 3))
        assert not ws._pending_resync

    async def test_a_resync_raises_so_run_reconnects(self, ws):
        """Reconnecting is the only resync route this project has observed
        working -- whether a redundant subscribe re-snapshots is unknown."""
        ws._pending_resync = True
        with pytest.raises(ResyncRequired):
            await ws._resync_all()
        assert all(b.invalid for b in ws.books.values())


class TestBookApplication:
    async def test_a_snapshot_populates_the_named_book_only(self, ws):
        await send(ws, snapshot_frame("KXMLBGAME-A", 1))
        assert ws.book("KXMLBGAME-A").yes_bids
        assert not ws.book("KXMLBGAME-B").yes_bids

    async def test_the_derived_ask_identity_holds(self, ws):
        await send(ws, snapshot_frame("KXMLBGAME-A", 1))
        book = ws.book("KXMLBGAME-A")
        assert book.best_yes_ask + book.best_no_bid == 1000

    async def test_a_frame_for_an_unsubscribed_ticker_is_ignored(self, ws):
        await send(ws, snapshot_frame("KXMLBGAME-ZZZ", 1))
        assert "KXMLBGAME-ZZZ" not in ws.books

    async def test_a_malformed_message_invalidates_rather_than_quoting_on(self, ws):
        """A book we cannot parse must not keep quoting what it last held."""
        await send(ws, snapshot_frame("KXMLBGAME-A", 1))
        await send(ws, {
            "type": "orderbook_delta", "sid": 1, "seq": 2,
            "msg": {"market_ticker": "KXMLBGAME-A", "side": "yes", "px": "0.45"},
        })
        assert ws.book("KXMLBGAME-A").invalid
        assert not ws.quotable_books(max_age_ms=60_000)

    async def test_the_update_callback_fires_for_each_applied_frame(self, ws):
        seen = []
        ws.on_book_update = seen.append
        await send(ws, snapshot_frame("KXMLBGAME-A", 1))
        await send(ws, delta_frame("KXMLBGAME-A", 2))
        assert len(seen) == 2
