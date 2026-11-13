"""Watched tickers: live top of book for the markets on one screen.

`/api/stream/quotes` carries engine rows sized above zero, and on live every
such row sizes to zero, so the ticket and the held legs name their own markets
on `/api/stream/books` instead (Joe, 2026-11-13).

Claims, each tested:

- **A watched ticker reaches the socket**: in the socket a window is built
  with, and in the running socket when a watcher arrives mid-window.
- **An idle hub opens a socket when someone watches.** Without the wake, a
  market page opened with no engine rows live would wait up to 120 s.
- **A frame reaches only that ticker's watchers, and only when the top moves.**
- **No money figure crosses the wire**: no edge, no size, no fair value.
- **Silence rather than a number** on an invalid or unpriceable book, and the
  heartbeat says which books are valid, so "unchanged" is not "lost".
- **The caps refuse** before any stream opens, and the route answers 503 with
  no feed.

What this does not establish
----------------------------
- Kalshi's answer to a subscribe sent mid-connection. It is the same command
  the opening loop sends for its second and later tickers, which the capture
  in `tests/fixtures/ws_orderbook_stream.json` covers; a fresh capture of a
  late subscribe has not been taken.
- Browser behaviour. `tests/test_live_books_client.py` covers the client's
  pure functions; the screens were not driven against a live feed.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest

from backend.api.routes import create_app
from backend.config import AppConfig
from backend.kalshi.orderbook import OrderBook
from backend.live import (
    MAX_WATCHED_PER_CLIENT,
    MAX_WATCHED_TOTAL,
    QuoteHub,
    WatchRefused,
    book_frame,
)

from tests.test_live_stream import FakeSocket
from tests.test_live_stream import stream_db as _stream_db_setup


@pytest.fixture
def stream_db(tmp_path):
    # The stream tests' database, reused rather than copied.
    return _stream_db_setup.__wrapped__(tmp_path)

A = "KXMLBGAME-26NOV131905NYYBOS-NYY"
B = "KXNFLGAME-26NOV151300KCBUF-KC"


def _book(ticker=A, *, yes_bid=400, no_bid=550, invalid=False, updated_ms=5_000):
    book = OrderBook(ticker=ticker)
    book.yes_bids = {yes_bid: 300.0} if yes_bid is not None else {}
    book.no_bids = {no_bid: 200.0} if no_bid is not None else {}
    book.updated_ms = updated_ms
    book.invalid = invalid
    return book


class WatchableSocket(FakeSocket):
    """A FakeSocket that also takes tickers mid-window and holds books."""

    def __init__(self, tickers, **kw):
        super().__init__(tickers, **kw)
        self.books = {t: OrderBook(t) for t in self.tickers}
        self.added: list[str] = []

    async def add_tickers(self, tickers):
        new = [t for t in tickers if t not in self.books]
        for t in new:
            self.tickers.append(t)
            self.books[t] = OrderBook(t)
        self.added.extend(new)
        return new


async def _next(stream, timeout=2.0):
    return await asyncio.wait_for(anext(stream), timeout=timeout)


def _pending(hub, tickers):
    """Frames queued for the watcher of exactly `tickers`.

    Read off the queue rather than by timing out `anext`: cancelling a
    pending `anext` closes the async generator, so a timed-out read would
    end the stream it was meant to observe.
    """
    (queue,) = [q for q, ts in hub._watch_clients.items() if ts == frozenset(tickers)]
    return queue.qsize()


class TestTheFrame:
    def test_it_carries_bid_ask_and_depth_and_no_money_figure(self):
        frame = book_frame(_book())
        # The derived ask: YES ask = 1000 - best NO bid.
        assert frame["yes_ask_tenths"] == 450
        assert frame["no_ask_tenths"] == 600
        assert frame["yes_bid_tenths"] == 400
        assert frame["no_bid_tenths"] == 550
        assert frame["yes_ask_display"] and frame["no_bid_display"]
        assert frame["observed_ms"] == 5_000
        for money in ("edge_tenths", "edge_cents", "contracts", "fair_probability"):
            assert money not in frame

    def test_an_invalid_book_says_nothing(self):
        assert book_frame(_book(invalid=True)) is None

    def test_a_book_with_no_ask_on_either_side_says_nothing(self):
        assert book_frame(_book(yes_bid=None, no_bid=None)) is None

    def test_one_missing_side_is_none_on_that_side_only(self):
        frame = book_frame(_book(no_bid=None))  # no NO bid -> no YES ask
        assert frame["yes_ask_tenths"] is None
        assert frame["no_ask_tenths"] == 600


class TestWhoReceivesAFrame:
    async def test_a_frame_reaches_only_that_tickers_watchers(self, stream_db):
        path, _conn, _now = stream_db
        hub = QuoteHub(path, socket_factory=WatchableSocket, heartbeat_s=5)
        watch_a = hub.watch(hub.check_watch([A]))
        watch_b = hub.watch(hub.check_watch([B]))
        assert (await _next(watch_a))["type"] == "books_snapshot"
        assert (await _next(watch_b))["type"] == "books_snapshot"

        await hub._on_book(_book(A))
        assert _pending(hub, [B]) == 0
        event = await _next(watch_a)
        assert event["type"] == "book" and event["ticker"] == A
        await watch_a.aclose()
        await watch_b.aclose()

    async def test_an_unchanged_top_of_book_is_not_news(self, stream_db):
        path, _conn, _now = stream_db
        hub = QuoteHub(path, socket_factory=WatchableSocket, heartbeat_s=5)
        stream = hub.watch(hub.check_watch([A]))
        await _next(stream)
        await hub._on_book(_book(A))
        assert (await _next(stream))["type"] == "book"
        # Depth behind the ask moved; the four prices did not.
        moved_depth = _book(A)
        moved_depth.yes_bids[380] = 999.0
        await hub._on_book(moved_depth)
        assert _pending(hub, [A]) == 0
        await hub._on_book(_book(A, no_bid=560))
        event = await _next(stream)
        assert event["yes_ask_tenths"] == 440
        await stream.aclose()

    async def test_an_invalid_book_sends_nothing(self, stream_db):
        path, _conn, _now = stream_db
        hub = QuoteHub(path, socket_factory=WatchableSocket, heartbeat_s=5)
        stream = hub.watch(hub.check_watch([A]))
        await _next(stream)
        await hub._on_book(_book(A, invalid=True))
        assert _pending(hub, [A]) == 0
        await stream.aclose()

    async def test_a_quote_client_never_receives_a_book_frame(self, stream_db):
        path, _conn, _now = stream_db
        hub = QuoteHub(path, socket_factory=WatchableSocket, heartbeat_s=5)
        quotes = hub.subscribe()
        watcher = hub.watch(hub.check_watch([A]))
        await _next(quotes)
        await _next(watcher)
        await hub._on_book(_book(A))
        assert (await _next(watcher))["type"] == "book"
        (quote_queue,) = hub._clients
        assert quote_queue.qsize() == 0
        await quotes.aclose()
        await watcher.aclose()


class TestTheHeartbeatSaysWhichBooksAreValid:
    async def test_a_valid_book_is_listed_and_an_invalid_one_is_not(self, stream_db):
        path, _conn, _now = stream_db
        hub = QuoteHub(path, socket_factory=WatchableSocket, heartbeat_s=0.1)
        socket = WatchableSocket([A, B])
        socket.books[A] = _book(A)
        socket.books[B] = _book(B, invalid=True)
        hub._socket = socket
        stream = hub.watch(hub.check_watch([A, B]))
        opening = await _next(stream)
        assert opening["valid"] == [A]
        assert [b["ticker"] for b in opening["books"]] == [A]
        beat = await _next(stream)
        assert beat["type"] == "heartbeat"
        assert beat["valid"] == [A]
        await stream.aclose()


class TestTheSocketLearnsWhatIsWatched:
    async def test_an_idle_hub_opens_a_socket_with_the_watched_ticker(self, stream_db):
        path, _conn, _now = stream_db
        built = []

        def factory(tickers):
            s = WatchableSocket(tickers)
            built.append(s)
            return s

        # No engine rows at all, and a window long enough that only the wake
        # can explain a socket opening inside the test.
        hub = QuoteHub(path, socket_factory=factory, heartbeat_s=5, resubscribe_s=60)
        await hub.start()
        try:
            await asyncio.sleep(0.2)
            assert built == [], "nothing to stream, so no socket"
            stream = hub.watch(hub.check_watch([A]))
            await _next(stream)
            for _ in range(50):
                if built:
                    break
                await asyncio.sleep(0.02)
            assert built and A in built[0].tickers
            await stream.aclose()
        finally:
            await hub.stop()

    async def test_a_watcher_arriving_mid_window_adds_its_ticker(self, stream_db):
        path, _conn, _now = stream_db
        hub = QuoteHub(path, socket_factory=WatchableSocket, heartbeat_s=5)
        socket = WatchableSocket([B])
        hub._socket = socket
        stream = hub.watch(hub.check_watch([A, B]))
        await _next(stream)
        assert socket.added == [A]
        await stream.aclose()

    async def test_a_released_ticker_is_not_watched(self, stream_db):
        path, _conn, _now = stream_db
        hub = QuoteHub(path, socket_factory=WatchableSocket, heartbeat_s=5)
        stream = hub.watch(hub.check_watch([A]))
        await _next(stream)
        assert hub.watched_tickers() == {A}
        await stream.aclose()
        assert hub.watched_tickers() == set()


class TestTheCapsRefuseBeforeAnyStream:
    def test_too_many_tickers_for_one_page(self, tmp_path):
        hub = QuoteHub(tmp_path / "x.db", socket_factory=WatchableSocket)
        many = [f"KXT-{i:03d}" for i in range(MAX_WATCHED_PER_CLIENT + 1)]
        with pytest.raises(WatchRefused) as refused:
            hub.check_watch(many)
        assert refused.value.status == 422
        assert hub.check_watch(many[:MAX_WATCHED_PER_CLIENT])

    def test_a_malformed_ticker(self, tmp_path):
        hub = QuoteHub(tmp_path / "x.db", socket_factory=WatchableSocket)
        for bad in ("kxlower-case", "A B", "../../etc", "X"):
            with pytest.raises(WatchRefused):
                hub.check_watch([bad])

    def test_no_ticker(self, tmp_path):
        hub = QuoteHub(tmp_path / "x.db", socket_factory=WatchableSocket)
        with pytest.raises(WatchRefused):
            hub.check_watch([" ", ""])

    def test_the_shared_socket_has_a_total_limit(self, tmp_path):
        hub = QuoteHub(tmp_path / "x.db", socket_factory=WatchableSocket)
        for page in range(MAX_WATCHED_TOTAL // MAX_WATCHED_PER_CLIENT):
            tickers = frozenset(
                f"KXT-{page:02d}-{i:02d}" for i in range(MAX_WATCHED_PER_CLIENT)
            )
            hub._watch_clients[asyncio.Queue()] = tickers
        assert len(hub.watched_tickers()) == MAX_WATCHED_TOTAL
        with pytest.raises(WatchRefused) as refused:
            hub.check_watch(["KXT-ONE-MORE"])
        assert refused.value.status == 429
        # A ticker already watched adds nothing, so it is still served.
        assert hub.check_watch(["KXT-00-00"])


class TestTheRoute:
    async def _get(self, app, url):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            return await c.get(url)

    async def test_no_feed_is_503(self, tmp_path):
        app = create_app(AppConfig(instance_mode="demo", db_path=tmp_path / "d.db"))
        response = await self._get(app, f"/api/stream/books?ticker={A}")
        assert response.status_code == 503

    async def test_too_many_tickers_is_422(self, stream_db):
        path, _conn, _now = stream_db
        hub = QuoteHub(path, socket_factory=WatchableSocket)
        app = create_app(
            AppConfig(instance_mode="live", auth_token="t", db_path=path),
            quote_hub=hub,
        )
        query = "&".join(f"ticker=KXT-{i:03d}" for i in range(MAX_WATCHED_PER_CLIENT + 1))
        response = await self._get(app, f"/api/stream/books?{query}")
        assert response.status_code == 422


class TestAWatcherIsToldTheFeedDied:
    async def test_a_dead_feed_reaches_the_watcher_as_down(self, stream_db):
        """A ticker that stops must look stopped: the screen showing a held
        leg has to hear `down`, not only the quote clients."""
        from backend.kalshi.ws import FeedDied

        path, _conn, _now = stream_db

        def dying(tickers):
            return WatchableSocket(tickers, die_with=FeedDied("feed died in test"))

        hub = QuoteHub(path, socket_factory=dying, heartbeat_s=5, resubscribe_s=60)
        stream = hub.watch(hub.check_watch([A]))
        assert (await _next(stream))["type"] == "books_snapshot"
        await hub.start()
        try:
            seen = []
            for _ in range(5):
                event = await _next(stream)
                seen.append(event["type"])
                if event["type"] == "down":
                    break
            assert "down" in seen, seen
            assert event["reason"] == "feed died in test"
        finally:
            await stream.aclose()
            await hub.stop()


class TestASubTenthLevelIsNotNothing:
    def test_a_bid_finer_than_a_tenth_is_flagged_not_dropped(self):
        from backend.kalshi.orderbook import UnpricedLevel

        book = _book(no_bid=None)
        book.unpriced = [UnpricedLevel(side="no", price_raw="0.5505", quantity=10.0)]
        frame = book_frame(book)
        # NO side: no priced bid, but one rests -> flagged.
        assert frame["no_bid_tenths"] is None and frame["no_bid_unpriced"] is True
        # YES ask is the complement of the NO bid, so it is unpriced too.
        assert frame["yes_ask_tenths"] is None and frame["yes_ask_unpriced"] is True
        # The YES bid side is ordinary.
        assert frame["yes_bid_unpriced"] is False


class TestADroppedConnectionInvalidatesEveryBook:
    async def test_books_are_invalid_while_the_socket_reconnects(self, tmp_path, monkeypatch):
        """Between a drop and the next snapshot nothing confirms a book, so the
        heartbeat must not list it as valid (kalshi-platform review, 2026-11-13)."""
        from types import SimpleNamespace

        from backend.config import KalshiConfig
        from backend.kalshi.ws import KalshiWebSocket

        key = tmp_path / "k.pem"
        key.write_text("x", encoding="utf-8")
        monkeypatch.setattr("backend.kalshi.ws.KalshiAuth", lambda *a, **kw: object())
        ws = KalshiWebSocket(
            KalshiConfig(api_key="t", private_key_path=key,
                         rest_url="https://e.invalid", ws_url="wss://e.invalid"),
            tickers=[A],
        )
        ws.auth = SimpleNamespace(get_ws_headers=lambda: {})
        ws.books[A] = _book(A)
        seen = []

        async def fail_then_record(*_a, **_kw):
            raise OSError("dropped")

        async def no_sleep(_s):
            seen.append(ws.books[A].invalid)
            raise asyncio.CancelledError

        monkeypatch.setattr(ws, "_connect_and_consume", fail_then_record)
        monkeypatch.setattr("backend.kalshi.ws.asyncio.sleep", no_sleep)
        with pytest.raises(asyncio.CancelledError):
            await ws.run()
        assert seen == [True]
