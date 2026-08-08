"""The ticker: live Kalshi prices pushed to the cockpit.

Three claims, and only the first is about streaming working.

**It streams.** A book update reaches a subscribed browser as a re-priced row.

**It streams the right number.** The edge and the size are recomputed in Python
by the same functions the order endpoint calls, at the live ask. If the browser
were handed the ask and left to subtract a fee, there would be two
implementations of a money calculation one refresh apart.

**It cannot lie about being alive.** A ticker introduces one failure a polled
page does not have: frozen prices that look live. A quiet market and a dead feed
must not render identically, so the heartbeat and the `down` event are tested
directly rather than assumed.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time

import pytest

from backend.config import RiskConfig, StalenessConfig
from backend.kalshi.orderbook import OrderBook
from backend.kalshi.ws import FeedDied
from backend.live import QuoteHub, open_decisions, price_against, sse
from backend.store import db


TICKER = "KXTEST-GAME-A"


@pytest.fixture
def stream_db(tmp_path):
    path = tmp_path / "stream.db"
    db.init_db(path).close()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    now = int(time.time() * 1000)
    conn.execute(
        "INSERT INTO strategy_configs (version, created_ms, effective_from_ms, "
        "config_json, rationale, approved_by_user) VALUES (1, ?, ?, '{}', 't', 1)",
        (now, now),
    )
    conn.commit()
    return path, conn, now


def _add(
    conn,
    *,
    now,
    ticker=TICKER,
    side="yes",
    ask=500,
    fair=0.60,
    contracts=20,
    odds_age=60_000,
    suppressed=None,
    created_offset=0,
):
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_markets (ticker, event_ticker, series_ticker, "
        "first_seen_ms, last_seen_ms) VALUES (?, ?, 'S', 0, 0)",
        (ticker, f"EVT-{ticker}"),
    )
    conn.execute(
        """
        INSERT INTO recommendations (
            created_ms, strategy_config_version, ticker, side, entry_ask_tenths,
            fair_probability, edge_tenths, fee_predicted, ev_net_dollars,
            kelly_fraction, suggested_contracts, kalshi_quote_age_ms,
            odds_age_ms, suppressed_reason, reason_text
        ) VALUES (?, 1, ?, ?, ?, ?, 20.0, 0.1, 0.5, 0.02, ?, 1000, ?, ?, 'test')
        """,
        (now + created_offset, ticker, side, ask, fair, contracts, odds_age,
         suppressed),
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]


def _book(ticker=TICKER, *, yes_bid=400, no_bid=500, yes_qty=800.0, no_qty=900.0,
          updated_ms=1_000, invalid=False):
    book = OrderBook(ticker=ticker)
    book.yes_bids = {yes_bid: yes_qty}
    book.no_bids = {no_bid: no_qty}
    book.updated_ms = updated_ms
    book.invalid = invalid
    return book


class TestWhichRowsAreStreamed:
    """Subscribing to everything ever recorded would be a screen full of
    movement that means nothing, and a socket resubscribed to markets that
    settled weeks ago."""

    def test_only_sized_unsuppressed_rows(self, stream_db):
        path, conn, now = stream_db
        live = _add(conn, now=now)
        _add(conn, now=now, ticker="T-NOEDGE", contracts=0)
        _add(conn, now=now, ticker="T-SUPPRESSED", suppressed="stale_odds")

        found = open_decisions(conn, staleness=StalenessConfig(), now_ms=now)

        assert [s.recommendation_id for s in found] == [live]

    def test_a_row_whose_consensus_aged_out_is_dropped(self, stream_db):
        """The odds clock, because that is the one the order endpoint still
        enforces -- the Kalshi quote is re-read at order time."""
        path, conn, now = stream_db
        _add(conn, now=now, odds_age=1_800_000)

        assert open_decisions(conn, staleness=StalenessConfig(), now_ms=now) == []

    def test_a_confirmation_keeps_a_row_alive(self, stream_db):
        """`live_ages` moves the basis when the quote pass re-derives a row, and
        this must read it the same way or the ticker and the Board disagree
        about which rows exist."""
        path, conn, now = stream_db
        rec = _add(conn, now=now - 1_500_000, odds_age=60_000)
        assert open_decisions(conn, staleness=StalenessConfig(), now_ms=now) == []

        conn.execute(
            "UPDATE recommendations SET last_confirmed_ms = ?, "
            "last_confirmed_quote_age_ms = 0, last_confirmed_odds_age_ms = ? "
            "WHERE id = ?",
            (now - 1_000, 60_000, rec),
        )
        conn.commit()

        found = open_decisions(conn, staleness=StalenessConfig(), now_ms=now)
        assert [s.recommendation_id for s in found] == [rec]

    def test_only_the_newest_row_per_side(self, stream_db):
        """The runner writes a row per price move, and the ticker is about
        what is live now, not about the history of the market."""
        path, conn, now = stream_db
        _add(conn, now=now, ask=500, created_offset=-10_000)
        newest = _add(conn, now=now, ask=520)

        found = open_decisions(conn, staleness=StalenessConfig(), now_ms=now)

        assert [s.recommendation_id for s in found] == [newest]


class TestThePriceOnTheWire:
    def test_the_ask_is_derived_from_the_opposing_bid(self, stream_db):
        """A YES ask is `1 - no_bid`. Inverting it produces plausible numbers."""
        path, conn, now = stream_db
        rec = _add(conn, now=now)
        sub = open_decisions(conn, staleness=StalenessConfig(), now_ms=now)[0]

        priced = price_against(
            _book(no_bid=530), sub, risk=RiskConfig(),
            exposure_dollars=0.0, now_ms=now,
        )

        assert priced is not None
        assert priced.ask_tenths == 470
        assert priced.to_dict()["ask_display"] == "47c"

    def test_the_depth_crossover_is_not_inverted(self, stream_db):
        path, conn, now = stream_db
        _add(conn, now=now)
        sub = open_decisions(conn, staleness=StalenessConfig(), now_ms=now)[0]

        priced = price_against(
            _book(no_qty=123.0, yes_qty=456.0), sub, risk=RiskConfig(),
            exposure_dollars=0.0, now_ms=now,
        )

        assert priced.depth_at_ask == 123.0, (
            "the size at the YES ask is the resting NO bid's size"
        )

    def test_the_edge_moves_with_the_price(self, stream_db):
        """**The claim that matters.** If the edge were carried from the row
        rather than recomputed, a streaming ask would sit beside a frozen edge
        and the card would contradict itself."""
        path, conn, now = stream_db
        _add(conn, now=now, ask=500, fair=0.60)
        sub = open_decisions(conn, staleness=StalenessConfig(), now_ms=now)[0]

        cheap = price_against(_book(no_bid=550), sub, risk=RiskConfig(),
                              exposure_dollars=0.0, now_ms=now)
        dear = price_against(_book(no_bid=450), sub, risk=RiskConfig(),
                             exposure_dollars=0.0, now_ms=now)

        assert cheap.ask_tenths == 450 and dear.ask_tenths == 550
        assert cheap.edge_tenths > dear.edge_tenths
        assert cheap.edge_tenths - dear.edge_tenths == pytest.approx(100, abs=15), (
            "a 10c move in the ask must move the edge by about 10c"
        )

    def test_the_size_never_exceeds_what_the_engine_authorised(self, stream_db):
        """A ticker showing a bigger size than the server would accept is an
        invitation to a refusal."""
        path, conn, now = stream_db
        _add(conn, now=now, ask=500, fair=0.60, contracts=12)
        sub = open_decisions(conn, staleness=StalenessConfig(), now_ms=now)[0]

        priced = price_against(_book(no_bid=650), sub, risk=RiskConfig(),
                               exposure_dollars=0.0, now_ms=now)

        assert priced.ask_tenths == 350
        assert priced.contracts == 12

    def test_an_invalid_book_says_nothing_rather_than_a_number(self, stream_db):
        """A sequence gap makes a book unquotable. Silence leaves the last frame
        on screen with its own age visible; a number invents one."""
        path, conn, now = stream_db
        _add(conn, now=now)
        sub = open_decisions(conn, staleness=StalenessConfig(), now_ms=now)[0]

        assert price_against(
            _book(invalid=True), sub, risk=RiskConfig(),
            exposure_dollars=0.0, now_ms=now,
        ) is None

    def test_a_one_sided_book_says_nothing(self, stream_db):
        path, conn, now = stream_db
        _add(conn, now=now)
        sub = open_decisions(conn, staleness=StalenessConfig(), now_ms=now)[0]
        book = _book()
        book.no_bids = {}

        assert price_against(
            book, sub, risk=RiskConfig(), exposure_dollars=0.0, now_ms=now
        ) is None


class FakeSocket:
    """A `KalshiWebSocket` stand-in that never touches the network."""

    def __init__(self, tickers, *, die_with=None):
        self.tickers = list(tickers)
        self.on_book_update = None
        self.on_feed_down = None
        self._die_with = die_with

    async def run(self):
        if self._die_with is not None:
            raise self._die_with
        await asyncio.Event().wait()      # hold the "connection" open


async def _drain(stream, n, timeout=3.0):
    """Take `n` events, failing loudly rather than hanging the suite."""
    out = []
    async def take():
        async for event in stream:
            out.append(event)
            if len(out) >= n:
                return
    await asyncio.wait_for(take(), timeout=timeout)
    return out


class TestTheStream:
    async def test_a_book_update_reaches_a_subscriber(self, stream_db):
        path, conn, now = stream_db
        rec = _add(conn, now=now, ask=500)

        sockets = []
        def factory(tickers):
            s = FakeSocket(tickers)
            sockets.append(s)
            return s

        hub = QuoteHub(path, socket_factory=factory, heartbeat_s=0.2)
        hub._load_subscriptions()
        stream = hub.subscribe()

        opening = await asyncio.wait_for(anext(stream), timeout=2.0)
        assert opening["type"] == "snapshot"

        await hub._on_book(_book(no_bid=530))
        event = await asyncio.wait_for(anext(stream), timeout=2.0)

        assert event["type"] == "quotes"
        assert event["quotes"][0]["id"] == rec
        assert event["quotes"][0]["ask_tenths"] == 470
        await stream.aclose()

    async def test_an_unchanged_ask_is_not_news(self, stream_db):
        """The book moves at levels nobody is buying at far more often than the
        best ask does. Sending a frame for each would be a ticker that looks
        busy and says nothing."""
        path, conn, now = stream_db
        _add(conn, now=now)
        hub = QuoteHub(path, socket_factory=FakeSocket, heartbeat_s=0.2)
        hub._load_subscriptions()
        stream = hub.subscribe()
        await asyncio.wait_for(anext(stream), timeout=2.0)      # snapshot

        await hub._on_book(_book(no_bid=530, no_qty=10.0))
        first = await asyncio.wait_for(anext(stream), timeout=2.0)
        assert first["type"] == "quotes"

        # Same best ask, different resting size deeper in the book.
        await hub._on_book(_book(no_bid=530, no_qty=99.0))
        nxt = await asyncio.wait_for(anext(stream), timeout=2.0)
        assert nxt["type"] == "heartbeat", (
            "an unchanged derived ask must not produce a quote frame"
        )
        await stream.aclose()

    async def test_a_quiet_market_still_beats(self, stream_db):
        """**The failure a ticker introduces.** Without this frame, "nothing is
        moving" and "the feed is dead" are the same screen."""
        path, conn, now = stream_db
        _add(conn, now=now)
        hub = QuoteHub(path, socket_factory=FakeSocket, heartbeat_s=0.15)
        hub._load_subscriptions()
        stream = hub.subscribe()

        events = await _drain(stream, 3, timeout=3.0)

        assert events[0]["type"] == "snapshot"
        assert all(e["type"] == "heartbeat" for e in events[1:])
        assert events[-1]["at_ms"] >= events[0]["at_ms"]
        await stream.aclose()

    async def test_a_dead_feed_is_announced_at_once(self, stream_db):
        """Every downstream price freezes at its last value when the feed dies.

        **The heartbeat is not good enough on its own**, which is why this test
        exists separately from the one below it: the heartbeat interval is ten
        seconds in production, and ten seconds of prices that look live after
        the feed has gone is the exact failure a ticker introduces. So the
        `down` event must be pushed the moment it happens.

        The heartbeat here is set *long* deliberately. If this test allowed the
        state to arrive on a heartbeat instead, deleting the broadcast would
        leave it green -- which is what the first version of it did.
        """
        path, conn, now = stream_db
        _add(conn, now=now)
        hub = QuoteHub(
            path,
            socket_factory=lambda t: FakeSocket(t, die_with=FeedDied("handshake 401")),
            heartbeat_s=30.0,
            resubscribe_s=30.0,
        )
        stream = hub.subscribe()
        await asyncio.wait_for(anext(stream), timeout=2.0)      # snapshot
        await hub.start()
        try:
            # `up` then `down`: the hub announces the connection before the
            # socket has had a chance to fail, which is honest -- it did connect.
            events = await _drain(stream, 2, timeout=3.0)
        finally:
            await hub.stop()

        assert [e["type"] for e in events] == ["up", "down"], (
            f"a dead feed waited for the next heartbeat to be reported: {events}"
        )
        assert "401" in events[1]["reason"]
        await stream.aclose()

    async def test_a_heartbeat_repeats_the_down_state(self, stream_db):
        """A phone that unlocks after the feed died, or reconnects, must not see
        a ticker that looks merely quiet."""
        path, conn, now = stream_db
        _add(conn, now=now)
        hub = QuoteHub(path, socket_factory=FakeSocket, heartbeat_s=0.15)
        hub._on_feed_down("handshake 401")
        stream = hub.subscribe()

        events = await _drain(stream, 2, timeout=3.0)

        assert events[0]["down"] == "handshake 401", "the opening frame hid it"
        assert events[1]["type"] == "heartbeat"
        assert events[1]["down"] == "handshake 401"
        await stream.aclose()

    async def test_a_client_that_falls_behind_is_dropped_not_followed(
        self, stream_db
    ):
        """One wedged phone must not stall the feed for every other viewer."""
        path, conn, now = stream_db
        _add(conn, now=now)
        hub = QuoteHub(path, socket_factory=FakeSocket, heartbeat_s=5.0)
        hub._load_subscriptions()

        queue: asyncio.Queue = asyncio.Queue(maxsize=1)
        hub._clients.add(queue)
        await hub._broadcast({"type": "a"})
        await hub._broadcast({"type": "b"})       # overflows

        assert queue not in hub._clients

    async def test_a_subscriber_joining_late_gets_the_board_immediately(
        self, stream_db
    ):
        """Otherwise a phone unlocked mid-window shows a blank ticker until each
        market happens to move."""
        path, conn, now = stream_db
        rec = _add(conn, now=now)
        hub = QuoteHub(path, socket_factory=FakeSocket, heartbeat_s=0.2)
        hub._load_subscriptions()
        await hub._on_book(_book(no_bid=530))

        stream = hub.subscribe()
        opening = await asyncio.wait_for(anext(stream), timeout=2.0)

        assert opening["type"] == "snapshot"
        assert [q["id"] for q in opening["quotes"]] == [rec]
        assert opening["quotes"][0]["ask_tenths"] == 470
        await stream.aclose()


class TestTheWireFormat:
    def test_an_event_is_one_sse_frame(self):
        frame = sse({"type": "heartbeat", "at_ms": 1})
        assert frame.startswith("data: ")
        assert frame.endswith("\n\n")
        assert json.loads(frame[6:].strip()) == {"type": "heartbeat", "at_ms": 1}
