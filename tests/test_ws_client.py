"""`KalshiWebSocket` frame handling, driven without a socket.

This class had **no tests at all** until now, which is how two silent failures
survived it. Both were found by running it against the live feed, not by
reading it:

1. The subscription registry never populated. The `subscribed` ack carries
   `{"channel", "sid"}` and no ticker; the handler read `msg.market_tickers`
   and `msg.market_ticker`, neither of which exists there. `_resubscribe` could
   therefore never unsubscribe, and the gap-recovery path was dead code.
   (`_resubscribe` itself was deleted 2026-09-09 -- gap recovery reconnects
   instead, and `_resync_all`'s docstring says why. The registry it needed is
   still load-bearing for `_sids`, so the tests below stand unchanged.)
2. Kalshi acks the **first** subscribe on a connection with `subscribed` and
   every one after it with `ok` — and `ok.msg` *does* carry `market_tickers`.
   Handling only `subscribed` registered 1 of 6 tickers in a live run.

Frame shapes below are copied from `tests/fixtures/ws_orderbook_stream.json`.
No socket is involved: `_handle` is fed strings directly.

**What none of this establishes.** Every test here drives `_handle` or
`_check_sequence` with frames this process constructed or replayed from a
capture taken on 2026-08-07. It says these functions agree with that capture.
It says nothing about whether Kalshi's live sequencing still behaves that way,
whether gaps are ever actually delivered, or whether the reconnect that gap
recovery demands re-snapshots anything.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import pytest

from backend.config import KalshiConfig
from backend.kalshi.ws import (
    FIRST_SEQ_MAX_PLAUSIBLE,
    MAX_PLAUSIBLE_GAP,
    KalshiWebSocket,
    ResyncRequired,
)

TICKERS = ["KXMLBGAME-A", "KXMLBGAME-B", "KXMLBGAME-C"]

FIXTURE = Path(__file__).parent / "fixtures" / "ws_orderbook_stream.json"


def _client(tmp_path, monkeypatch, tickers):
    """A `KalshiWebSocket` with no connection. Auth is never exercised."""
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
    return KalshiWebSocket(config, tickers=tickers)


@pytest.fixture
def ws(tmp_path, monkeypatch):
    """A client with no connection. Auth is never exercised."""
    return _client(tmp_path, monkeypatch, TICKERS)


@pytest.fixture(scope="module")
def capture():
    """The verbatim stream: 269 frames off the live socket, 12 tickers."""
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def captured_frames(capture):
    """Just the frames, unwrapped from their `received_ms` envelopes."""
    return [record["frame"] for record in capture["frames"]]


@pytest.fixture
def capture_ws(tmp_path, monkeypatch, capture):
    """A client subscribed to exactly the tickers the capture carries."""
    return _client(tmp_path, monkeypatch, capture["tickers"])


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


def subscribed_frame(command_id, sid=1):
    """The first ack on a connection. Frame keys in the capture are exactly
    `id`, `msg`, `type` — no `seq`, and the sid lives on `msg`."""
    return {
        "type": "subscribed", "id": command_id,
        "msg": {"channel": "orderbook_delta", "sid": sid},
    }


def ok_frame(tickers, seq, command_id, sid=1):
    """The ack every subscribe after the first gets. Unlike `subscribed` it
    carries a `seq`, so it consumes a connection sequence number."""
    return {
        "type": "ok", "id": command_id, "sid": sid, "seq": seq,
        "msg": {"market_tickers": list(tickers)},
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


class TestCheckSequence:
    """`_check_sequence` — the integrity check on the whole feed.

    `seq` counts frames on the *connection*, not per market: one shared sid and
    one strictly increasing sequence across every ticker. An undetected gap is
    the worst failure in this module because it is silent — deltas keep applying
    on top of a book that is missing an update, no error is raised, and the desk
    prices against an orderbook that is simply wrong. The return value gates all
    type dispatch in `_handle`, so a bug here either drops good frames or admits
    bad ones.

    Its two refusal branches have opposite consequences and must not be
    conflated: a **gap** means loss (invalidate everything, resync), a
    **duplicate or reorder** means the frame already arrived (drop it, touch
    nothing else).

    Not established here: that a real gap on the live socket looks like this,
    or that anything downstream recovers. See the module docstring.
    """

    # -- the accepting path ------------------------------------------------

    def test_a_strictly_increasing_frame_is_accepted_and_advances_the_cursor(self, ws):
        ws._last_seq = 41
        assert ws._check_sequence(delta_frame("KXMLBGAME-A", 42)) is True
        assert ws._last_seq == 42

    def test_the_first_frame_on_a_connection_is_accepted_when_plausible(self, ws):
        """The sequence is per-connection and `_connect_and_consume` clears the
        cursor, so there is nothing for the first frame to be measured against
        except a plausibility bound. Comparing it to zero (i.e. requiring
        seq==1) would report a gap on every single reconnect, since acks
        before the first market-data frame already consume a few numbers."""
        assert ws._last_seq is None
        assert ws._check_sequence(delta_frame("KXMLBGAME-A", 5)) is True
        assert ws._last_seq == 5
        assert not ws._pending_resync
        assert not any(b.invalid for b in ws.books.values())

    def test_a_first_seq_exactly_at_the_bound_is_accepted(self, ws):
        assert ws._check_sequence(
            delta_frame("KXMLBGAME-A", FIRST_SEQ_MAX_PLAUSIBLE)
        ) is True
        assert ws._last_seq == FIRST_SEQ_MAX_PLAUSIBLE

    def test_an_implausible_first_seq_is_refused_not_trusted_blind(self, ws):
        """Before this bound existed, this accepted 8,675,309 and parked the
        cursor there -- poisoning every legitimate frame afterwards, which
        would then satisfy `seq <= _last_seq` (the reorder branch, not the
        gap branch) and be dropped silently forever: no invalidation, no
        resync, no error anywhere."""
        assert ws._last_seq is None
        assert ws._check_sequence(delta_frame("KXMLBGAME-A", 8_675_309)) is False
        assert ws._last_seq is None

    def test_a_first_seq_one_past_the_bound_is_refused(self, ws):
        assert ws._check_sequence(
            delta_frame("KXMLBGAME-A", FIRST_SEQ_MAX_PLAUSIBLE + 1)
        ) is False
        assert ws._last_seq is None

    def test_an_implausible_first_seq_invalidates_every_book(self, ws):
        """Same consequence as an ordinary gap -- a corrupt bootstrap cannot
        be trusted any more than a mid-stream one."""
        ws._check_sequence(delta_frame("KXMLBGAME-A", 8_675_309))
        assert all(b.invalid for b in ws.books.values())
        assert not ws.quotable_books(max_age_ms=60_000)

    def test_an_implausible_first_seq_asks_for_a_resync(self, ws):
        ws._check_sequence(delta_frame("KXMLBGAME-A", 8_675_309))
        assert ws._pending_resync

    def test_a_legitimate_frame_after_a_refused_bootstrap_still_bootstraps(self, ws):
        """The refused frame must not poison the cursor. On the reconnected
        connection `_resync_all` produces, `_last_seq` is `None` again, so the
        next real frame is judged as a fresh bootstrap, not a second
        corruption stacked on the first."""
        ws._check_sequence(delta_frame("KXMLBGAME-A", 8_675_309))
        ws._last_seq = None  # what `_connect_and_consume` does on reconnect
        assert ws._check_sequence(delta_frame("KXMLBGAME-A", 1)) is True

    # -- the gap branch ----------------------------------------------------

    def test_a_gap_refuses_the_frame(self, ws):
        """False stops `_handle` before dispatch, so the frame is not applied."""
        ws._last_seq = 2
        assert ws._check_sequence(delta_frame("KXMLBGAME-A", 9)) is False

    def test_a_gap_invalidates_every_book_not_only_the_one_it_arrived_on(self, ws):
        """A gap names the connection. It does not say which market lost an
        update, so invalidating one book would leave the rest quietly wrong."""
        ws._last_seq = 2
        ws._check_sequence(delta_frame("KXMLBGAME-A", 9))
        assert {t for t, b in ws.books.items() if b.invalid} == set(TICKERS)
        assert not ws.quotable_books(max_age_ms=60_000)

    def test_a_gap_asks_the_consume_loop_for_a_resync(self, ws):
        """`_check_sequence` cannot reconnect from inside frame dispatch, so it
        raises a flag the loop reads after `_handle` returns."""
        ws._last_seq = 2
        ws._check_sequence(delta_frame("KXMLBGAME-A", 9))
        assert ws._pending_resync

    def test_a_gap_resets_the_cursor_so_the_next_frame_is_not_a_second_gap(self, ws):
        ws._last_seq = 2
        ws._check_sequence(delta_frame("KXMLBGAME-A", 9))
        assert ws._last_seq == 9
        ws._pending_resync = False
        assert ws._check_sequence(delta_frame("KXMLBGAME-A", 10)) is True
        assert not ws._pending_resync

    def test_a_gap_is_logged_and_not_raised(self, ws, caplog):
        """`SequenceGap` is built here for its message and logged; it is never
        raised. Recovery runs through `_pending_resync` instead. Both
        `ws.py`'s and `orderbook.py`'s module docstrings still say a gap
        *raises* — that is stale prose, and this pins the actual behaviour."""
        ws._last_seq = 2
        with caplog.at_level(logging.WARNING, logger="backend.kalshi.ws"):
            assert ws._check_sequence(delta_frame("KXMLBGAME-A", 9)) is False
        assert "expected 3 got 9" in caplog.text

    def test_a_small_gap_is_logged_as_a_gap_not_corruption(self, ws, caplog):
        ws._last_seq = 2
        with caplog.at_level(logging.WARNING, logger="backend.kalshi.ws"):
            ws._check_sequence(delta_frame("KXMLBGAME-A", 9))
        assert "corruption" not in caplog.text

    def test_an_implausible_forward_gap_is_still_invalidated_and_resynced(self, ws):
        """The response is identical to an ordinary gap -- both are already
        safe, because `_connect_and_consume` calls `_resync_all` before the
        next frame is ever read. Only the log classification changes."""
        ws._last_seq = 2
        seq = 2 + MAX_PLAUSIBLE_GAP + 1
        assert ws._check_sequence(delta_frame("KXMLBGAME-A", seq)) is False
        assert all(b.invalid for b in ws.books.values())
        assert ws._pending_resync
        assert ws._last_seq == seq

    def test_an_implausible_forward_gap_is_logged_as_corruption(self, ws, caplog):
        ws._last_seq = 2
        seq = 2 + MAX_PLAUSIBLE_GAP + 1
        with caplog.at_level(logging.ERROR, logger="backend.kalshi.ws"):
            ws._check_sequence(delta_frame("KXMLBGAME-A", seq))
        assert "corruption" in caplog.text

    # -- the duplicate / reorder branch ------------------------------------

    def test_a_duplicated_frame_is_refused(self, ws):
        """Applying it would double-count the delta."""
        ws._last_seq = 42
        assert ws._check_sequence(delta_frame("KXMLBGAME-A", 42)) is False

    def test_a_reordered_frame_is_refused(self, ws):
        ws._last_seq = 42
        assert ws._check_sequence(delta_frame("KXMLBGAME-A", 40)) is False

    def test_a_duplicate_takes_the_reorder_branch_not_the_gap_branch(self, ws):
        """`seq == _last_seq` is the exact boundary between the two branches.
        A repeat is not loss; sending it down the gap path would discard every
        good book and force a reconnect on a non-event."""
        ws._last_seq = 42
        ws._check_sequence(delta_frame("KXMLBGAME-A", 42))
        assert not ws._pending_resync
        assert not any(b.invalid for b in ws.books.values())
        assert ws._last_seq == 42

    def test_a_reordered_frame_does_not_invalidate_any_book(self, ws):
        """Nothing was lost — this frame already arrived — so the books are
        still correct and must stay quotable."""
        ws._last_seq = 42
        ws._check_sequence(delta_frame("KXMLBGAME-A", 41))
        assert not any(b.invalid for b in ws.books.values())

    def test_a_reordered_frame_does_not_ask_for_a_resync(self, ws):
        ws._last_seq = 42
        ws._check_sequence(delta_frame("KXMLBGAME-A", 41))
        assert not ws._pending_resync

    def test_a_reordered_frame_leaves_the_cursor_where_it_was(self, ws):
        """Rewinding it would make every frame already seen replayable, and the
        next real frame would then look like a gap."""
        ws._last_seq = 42
        ws._check_sequence(delta_frame("KXMLBGAME-A", 41))
        assert ws._last_seq == 42
        assert ws._check_sequence(delta_frame("KXMLBGAME-A", 43)) is True

    # -- the no-`seq` exception --------------------------------------------

    def test_a_frame_with_no_seq_is_accepted(self, ws):
        """`subscribed` is the deliberate exception: in the capture it is the
        only frame type carrying no `seq` at all."""
        ws._last_seq = 42
        assert ws._check_sequence(subscribed_frame(command_id=2)) is True

    def test_a_frame_with_no_seq_does_not_move_the_cursor(self, ws):
        """It consumed no sequence number, so the next frame is still 43."""
        ws._last_seq = 42
        ws._check_sequence(subscribed_frame(command_id=2))
        assert ws._last_seq == 42
        assert ws._check_sequence(delta_frame("KXMLBGAME-A", 43)) is True

    def test_a_frame_with_no_seq_is_not_read_as_a_gap_from_zero(self, ws):
        ws._last_seq = 42
        ws._check_sequence(subscribed_frame(command_id=2))
        assert not ws._pending_resync
        assert not any(b.invalid for b in ws.books.values())


class TestSequenceRunsBeforeDispatch:
    """`_handle` checks the sequence first, so a refused frame has no effects.

    Not established here: anything about the socket, which is absent.
    """

    async def test_a_gapped_book_frame_is_never_applied(self, ws):
        await send(ws, snapshot_frame("KXMLBGAME-A", 1))
        before = dict(ws.book("KXMLBGAME-A").yes_bids)
        await send(ws, delta_frame("KXMLBGAME-A", 9, size=10.0))
        assert ws.book("KXMLBGAME-A").yes_bids == before

    async def test_a_control_frame_lost_in_a_gap_is_never_dispatched(self, ws):
        """Dispatching before the check would let the ack's side effect land
        while the frame itself is being refused."""
        await send(ws, snapshot_frame("KXMLBGAME-A", 1))
        await send(ws, ok_frame(["KXMLBGAME-B"], seq=9, command_id=2))
        assert "KXMLBGAME-B" not in ws._ticker_sids
        assert ws._pending_resync

    async def test_a_control_frame_consumes_a_sequence_number(self, ws):
        """`ok` carries `seq`. Returning early for it would let the number pass
        unnoticed and make the next book frame look like a gap."""
        await send(ws, snapshot_frame("KXMLBGAME-A", 1))
        await send(ws, ok_frame(["KXMLBGAME-B"], seq=2, command_id=2))
        assert ws._last_seq == 2
        await send(ws, delta_frame("KXMLBGAME-A", 3))
        assert ws._last_seq == 3
        assert not ws._pending_resync

    async def test_the_subscribed_ack_still_registers_despite_carrying_no_seq(self, ws):
        """The exception must exempt the frame, not swallow it."""
        ws._pending_subscriptions[1] = "KXMLBGAME-A"
        await send(ws, subscribed_frame(command_id=1))
        assert ws._ticker_sids["KXMLBGAME-A"] == 1
        assert ws._last_seq is None


class TestTheCaptureBacksTheSequenceClaims:
    """Facts read straight off `tests/fixtures/ws_orderbook_stream.json`.

    Not established: that a stream captured on 2026-08-07 still describes the
    live feed.
    """

    def test_subscribed_is_the_only_frame_type_without_a_seq(self, captured_frames):
        assert {f["type"] for f in captured_frames if "seq" not in f} == {"subscribed"}

    def test_the_subscribed_ack_arrives_before_the_first_sequence_number(
        self, captured_frames
    ):
        """So a no-`seq` frame handled as a gap from zero would fire on the very
        first frame of every connection."""
        assert captured_frames[0]["type"] == "subscribed"
        assert captured_frames[1]["seq"] == 1

    def test_acknowledgements_carry_sequence_numbers(self, captured_frames):
        acks = [f["seq"] for f in captured_frames if f["type"] == "ok"]
        assert len(acks) == 11
        assert all(isinstance(s, int) for s in acks)


class TestTheCapturedStreamThroughCheckSequence:
    """The real stream, frame by frame, through the real check.

    Not established: that Kalshi ever actually drops a frame, or what the feed
    looks like when it does — the gap below is manufactured by deleting one.
    """

    async def test_the_whole_capture_replays_without_a_single_gap(
        self, capture_ws, captured_frames
    ):
        for frame in captured_frames:
            await send(capture_ws, frame)
        assert not capture_ws._pending_resync
        assert capture_ws._last_seq == captured_frames[-1]["seq"] == 268
        assert not any(b.invalid for b in capture_ws.books.values())

    async def test_dropping_one_captured_frame_is_detected(
        self, capture_ws, captured_frames
    ):
        """The failure this check exists for: one delta is lost in transit and
        every later delta lands on a book that is missing an update."""
        for frame in captured_frames:
            if frame.get("seq") == 100:
                continue
            await send(capture_ws, frame)
            if capture_ws._pending_resync:
                break
        assert capture_ws._pending_resync
        assert capture_ws._last_seq == 101
        assert all(b.invalid for b in capture_ws.books.values())
        assert not capture_ws.quotable_books(max_age_ms=10**9)


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


class TestADataFrameWithNoSeqIsNotExempt:
    """The exemption is for control frames, and a data frame is not one.

    Until 2026-09-09 `_check_sequence` read "no `seq` -> accept", type-blind.
    That is the worst failure shape this file has: an `orderbook_delta`
    arriving without a `seq` — a field rename on Kalshi's side, which is
    exactly what `orderbook.py` was rewritten to catch — would pass the
    integrity check *and* be applied, because `_apply` forwards `seq=None`
    and `apply_delta` only records a `seq` that is not None. A silently wrong
    book, with no error anywhere.

    Not established here: that Kalshi will never send such a frame. The
    capture says every data frame carries a `seq` today; this is about what
    happens if that stops being true.
    """

    async def test_a_delta_with_no_seq_is_refused(self, ws):
        await send(ws, snapshot_frame("KXMLBGAME-A", 1))
        frame = delta_frame("KXMLBGAME-A", 2)
        del frame["seq"]
        assert ws._check_sequence(frame) is False

    async def test_a_snapshot_with_no_seq_is_refused(self, ws):
        """Both data types, not just the one that mutates in place."""
        frame = snapshot_frame("KXMLBGAME-A", 1)
        del frame["seq"]
        assert ws._check_sequence(frame) is False

    async def test_a_seqless_data_frame_invalidates_every_book(self, ws):
        """Same consequence as a gap: the connection is untrustworthy."""
        await send(ws, snapshot_frame("KXMLBGAME-A", 1))
        frame = delta_frame("KXMLBGAME-A", 2)
        del frame["seq"]
        ws._check_sequence(frame)
        assert all(book.invalid for book in ws.books.values())
        assert ws._pending_resync is True

    async def test_a_seqless_delta_is_never_applied_to_the_book(self, ws):
        """The whole point — it must not reach `apply_delta`."""
        await send(ws, snapshot_frame("KXMLBGAME-A", 1))
        before = dict(ws.books["KXMLBGAME-A"].yes_bids)
        frame = delta_frame("KXMLBGAME-A", 2, size=99.0)
        del frame["seq"]
        await send(ws, frame)
        assert dict(ws.books["KXMLBGAME-A"].yes_bids) == before

    async def test_a_control_frame_with_no_seq_is_still_exempt(self, ws):
        """Otherwise an unknown ack Kalshi adds later forces a reconnect loop.

        Scoping to `subscribed` alone would be tighter and worse: a reconnect
        every time an unrecognised control frame arrives is a heavier failure
        than accepting one.
        """
        assert ws._check_sequence({"type": "some_future_ack", "msg": {}}) is True
        assert ws._pending_resync is False
        assert not any(book.invalid for book in ws.books.values())
