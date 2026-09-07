"""The deadline on a resting bid is withdrawn by something, on its own.

**Why this exists.** `combo_orders.cancel_after_ms` is the earliest leg's
kickoff, frozen when the bid was placed. Without a loop reading it, it is a
column nothing consults -- the "built but never called" failure this repo has
recorded four times, and here it would be the difference between a deadline and
a decoration.

A fill after kickoff is a bet on a game already under way, priced on a pre-game
consensus (`ladder_candidates` refuses a started game by construction), and a
combination gives no way out of one.

**What this establishes.** That a bid past its deadline is cancelled with its
stored shard; that one before its deadline is left alone; that a failed cancel
leaves the row WORKING rather than claiming it was withdrawn; that a bid with
no exchange order id is not marked cancelled on the venue's behalf; and that
the watcher is actually started by the loop.

**What it does not establish.** That any bid was ever at risk of filling -- no
combination book this repo has read carried a resting YES bid, so the
counterparty this guards against has never been observed. It guards a thing
that would be very bad, not one known to be common.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.bid_watch import (                                   # noqa: E402
    cancel_due_bids,
    watch_bids_forever,
)
from backend.store import db as store                             # noqa: E402
from backend.kalshi.rest import KalshiAPIError                    # noqa: E402
from backend.store.combo_orders import (                          # noqa: E402
    GONE_AT_VENUE_REASON,
    STATUS_CANCELLED,
    STATUS_GONE_AT_VENUE,
    STATUS_PENDING,
    STATUS_RESTING,
    record_intent,
    record_outcome,
    working_orders,
)

#: A fixed instant in 2026-08-29. Permanently in the PAST, so a bid carrying
#: it is due under the real clock and stays due -- which is what lets the
#: end-to-end tests below drive `watch_bids_forever` without injecting a clock
#: into production code purely to be tested.
KICKOFF_MS = 1_788_000_600_000

#: Year 2100. Never due, whenever this runs.
FAR_FUTURE_MS = 4_102_444_800_000


class FakeApi:
    """A stand-in that is **as strict as `KalshiRestClient`, not more polite.**

    It refuses to be used outside `async with`, exactly as the real client's
    `client` property does. That strictness is the whole point of this class
    now: the previous version answered `cancel_order` happily whether or not it
    had been entered, so it modelled a client that does not exist, and the one
    defect it needed to catch was invisible to every test in this file.

    On live, `watch_bids_forever` was passing a constructed-but-unentered
    client, and every cancel raised `RuntimeError: KalshiRestClient used
    outside its context manager` before reaching the venue -- for the whole
    life of the feature. The tests were green throughout, because the double
    was kinder than the thing it stood for.

    **Rule this encodes: a test double may be simpler than the real object, and
    may not be more permissive.** Wherever the real one refuses, the double
    refuses.
    """

    def __init__(self, *, raises=False):
        self.raises = raises
        self.calls: list = []
        self.entered = False
        self.closed = False

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, *exc_info):
        self.closed = True
        return False

    async def cancel_order(self, order_id, *, exchange_index=None):
        if not self.entered:
            raise RuntimeError(
                "KalshiRestClient used outside its context manager. "
                "Use `async with KalshiRestClient(cfg) as api:`."
            )
        self.calls.append((order_id, exchange_index))
        if isinstance(self.raises, BaseException):
            # The venue answered, and the answer was an error with a status
            # code -- what `KalshiRestClient` raises on a 4xx/5xx.
            raise self.raises
        if self.raises:
            raise RuntimeError("the venue said no")
        return {"order_id": order_id, "reduced_by": "1.00"}


@pytest.fixture
def conn(tmp_path):
    c = store.init_db(tmp_path / "bids.db")
    yield c
    c.close()


def _bid(conn, *, cancel_after_ms=KICKOFF_MS, order_id="ord-1", cid="cid-1"):
    row_id = record_intent(
        conn,
        now_ms=1_788_000_000_000,
        ticker="KXMVECROSSCATEGORY-SHARD1-ABC",
        card_key="safe",
        legs=[("E1", "M1"), ("E2", "M2")],
        exchange_index=1,
        contracts=4,
        price_tenths=220,
        fair_joint=0.251,
        cancel_after_ms=cancel_after_ms,
        request_body={"client_order_id": cid},
        dry_run=False,
    )
    if order_id is not None:
        record_outcome(
            conn, row_id, status="resting", kalshi_order_id=order_id
        )
    return row_id


class TestTheDeadlineIsEnforced:
    async def test_a_bid_past_kickoff_is_withdrawn_with_its_shard(self, conn):
        row_id = _bid(conn)
        api = FakeApi()
        await api.__aenter__()

        cancelled = await cancel_due_bids(conn, api, now_ms=KICKOFF_MS + 1)

        assert cancelled == 1
        assert api.calls == [("ord-1", 1)], (
            "the cancel must carry the stored shard: without it the venue "
            "404s an order that is demonstrably resting"
        )
        row = conn.execute(
            "SELECT status, cancel_reason FROM combo_orders WHERE id = ?",
            (row_id,),
        ).fetchone()
        assert row["status"] == STATUS_CANCELLED
        assert "first leg has started" in row["cancel_reason"]

    async def test_a_bid_before_kickoff_is_left_alone(self, conn):
        _bid(conn)
        api = FakeApi()
        await api.__aenter__()

        assert await cancel_due_bids(conn, api, now_ms=KICKOFF_MS - 1) == 0
        assert api.calls == []
        assert len(working_orders(conn)) == 1


class TestAFailedCancelNeverClaimsSuccess:
    async def test_the_row_stays_working_when_the_venue_refuses(self, conn):
        """A row saying "cancelled" over a live order is the one lie here.

        Left working, so it shows in the panel and is retried next pass.
        """
        row_id = _bid(conn)
        api = FakeApi(raises=True)
        # Entered, so the refusal under test is the VENUE's. Unentered, this
        # test still passed -- on the context-manager RuntimeError instead of
        # on `raises=True` -- which is a green light for the wrong reason.
        await api.__aenter__()

        assert await cancel_due_bids(conn, api, now_ms=KICKOFF_MS + 1) == 0

        row = conn.execute(
            "SELECT status FROM combo_orders WHERE id = ?", (row_id,)
        ).fetchone()
        assert row["status"] != STATUS_CANCELLED
        assert len(working_orders(conn)) == 1

    async def test_a_bid_with_no_exchange_id_is_not_cancelled_on_its_behalf(
        self, conn
    ):
        """Its create never came back. This process cannot say what happened.

        Marking it cancelled would be a claim about the exchange nobody made.
        """
        _bid(conn, order_id=None)
        api = FakeApi()
        await api.__aenter__()

        assert await cancel_due_bids(conn, api, now_ms=KICKOFF_MS + 1) == 0
        assert api.calls == []
        rows = working_orders(conn)
        assert len(rows) == 1
        assert rows[0]["status"] == STATUS_PENDING


def _status(conn, row_id):
    row = conn.execute(
        "SELECT status, cancel_reason, cancel_reduced_by, error_text "
        "FROM combo_orders WHERE id = ?", (row_id,)
    ).fetchone()
    return dict(row)


class TestAVenue404IsAnAnswerNotAFailure:
    """The venue holding no order by that id is final, and is not a cancel.

    Measured on the live account 2026-09-06: row 2 FILLED at 21:40Z on
    2026-09-01 (maker, 8 contracts), settled the next day, and from its
    22:41Z deadline onward every cancel the watcher sent drew 404
    `not_found`. Under the old code that was `except Exception` -- logged as
    a failure and retried once a minute for five days, over money that had
    already moved. A 404 has to be told apart from a transport failure, and
    the row it describes has to stop being "working" without being called
    "cancelled".
    """

    def _gone(self):
        return KalshiAPIError(
            404, "https://api.example/portfolio/events/orders/ord-1",
            '{"code":"not_found","message":"order not found"}',
        )

    async def test_a_404_marks_the_bid_gone_and_it_is_not_retried(self, conn):
        row_id = _bid(conn)
        api = FakeApi(raises=self._gone())
        await api.__aenter__()

        assert await cancel_due_bids(conn, api, now_ms=KICKOFF_MS + 1) == 0
        assert _status(conn, row_id)["status"] == STATUS_GONE_AT_VENUE
        assert working_orders(conn) == []

        # The next pass must not ask the venue again. Under the old code this
        # second call is what ran every minute from 2026-09-01 to 09-06.
        await cancel_due_bids(conn, api, now_ms=KICKOFF_MS + 60_001)
        assert len(api.calls) == 1, api.calls

    async def test_the_venue_words_are_kept_and_nothing_is_called_withdrawn(
        self, conn
    ):
        row_id = _bid(conn)
        api = FakeApi(raises=self._gone())
        await api.__aenter__()
        await cancel_due_bids(conn, api, now_ms=KICKOFF_MS + 1)

        row = _status(conn, row_id)
        assert row["status"] != STATUS_CANCELLED, (
            "a filled order is not a cancelled one; the status must not say so"
        )
        assert row["cancel_reason"] == GONE_AT_VENUE_REASON
        assert row["cancel_reduced_by"] is None, "nothing was withdrawn"
        assert "not_found" in row["error_text"], (
            "the venue's own body is the evidence; keep it on the row"
        )

    async def test_any_other_venue_error_is_still_left_working_and_retried(
        self, conn
    ):
        """A 500 is the venue failing, not the venue answering.

        Guards the status-code test itself: without it, every
        `KalshiAPIError` would be read as "gone" and a venue outage would
        retire live bids.
        """
        row_id = _bid(conn)
        api = FakeApi(raises=KalshiAPIError(
            503, "https://api.example/portfolio/events/orders/ord-1", "down"
        ))
        await api.__aenter__()

        assert await cancel_due_bids(conn, api, now_ms=KICKOFF_MS + 1) == 0
        assert _status(conn, row_id)["status"] == STATUS_RESTING
        assert len(working_orders(conn)) == 1

        await cancel_due_bids(conn, api, now_ms=KICKOFF_MS + 60_001)
        assert len(api.calls) == 2, "a venue outage is retried; a 404 is not"


class TestItIsActuallyStarted:
    def test_the_loop_starts_the_watcher_and_stops_it(self):
        """Four modules in this repo were complete and invoked by nothing.

        `watch_bids_forever` is nested behind a live Kalshi client, so the
        honest cheap check is over the source: it is started, and it is
        cancelled on the way out -- a watcher outliving a dead runner holds
        the database half-alive.

        **This check is necessary and it is not sufficient, which was proved
        the hard way.** It stayed green on 2026-08-30 while every cancel the
        watcher attempted failed on live, because the string it looks for was
        present and the client handed to it was unusable. A source grep can say
        a call exists; only running the thing says the call works. See
        `TestTheWatcherDrivesARealCancel` below, which is that.
        """
        source = (ROOT / "scripts" / "run_loop.py").read_text(encoding="utf-8")

        assert "from backend.bid_watch import watch_bids_forever" in source
        assert "watch_bids_forever(args.db" in source
        assert "bid_task.cancel()" in source


class TestTheWatcherDrivesARealCancel:
    """`watch_bids_forever` end to end, which no test did until 2026-08-30.

    Every test above calls `cancel_due_bids` directly, handing it a client
    someone else prepared. The bug lived in the gap between them: the loop
    built the client and never entered it, so the seam that production actually
    runs was the one seam nothing exercised.
    """

    async def test_a_due_bid_is_withdrawn_by_the_loop_itself(self, tmp_path):
        """Mutation observed red: revert the loop to `api_factory()` unentered.

        It then raises the context-manager `RuntimeError` inside
        `cancel_due_bids`, the row stays working, and both assertions fail --
        which is exactly what live was doing, once a minute, while the suite
        was green.
        """
        path = tmp_path / "loop.db"
        conn = store.init_db(path)
        row_id = _bid(conn)
        conn.close()

        api = FakeApi()
        await watch_bids_forever(path, lambda: api, interval_s=0, max_passes=1)

        assert api.entered, "the loop must enter the client it builds"
        assert api.calls == [("ord-1", 1)]

        conn = store.open_db(path)
        try:
            row = conn.execute(
                "SELECT status FROM combo_orders WHERE id = ?", (row_id,)
            ).fetchone()
            assert row["status"] == STATUS_CANCELLED
        finally:
            conn.close()

    async def test_the_client_is_closed_after_each_pass(self, tmp_path):
        """A client per pass that is never closed is a socket leak per minute.

        `async with` is what closes it; asserting only that it was *entered*
        would pass on a loop that opens one and walks away.
        """
        path = tmp_path / "close.db"
        conn = store.init_db(path)
        _bid(conn)
        conn.close()

        api = FakeApi()
        await watch_bids_forever(path, lambda: api, interval_s=0, max_passes=1)

        assert api.closed

    async def test_no_client_is_built_when_nothing_is_due(self, tmp_path):
        """A keyless instance must not construct a Kalshi client every minute.

        That is the reason the factory exists at all, and entering one
        unconditionally would have quietly undone it -- constructing a client
        60 times an hour, forever, for a feature the instance does not expose.
        """
        path = tmp_path / "idle.db"
        conn = store.init_db(path)
        _bid(conn, cancel_after_ms=FAR_FUTURE_MS)
        conn.close()

        built: list = []

        def factory():
            built.append(1)
            return FakeApi()

        await watch_bids_forever(path, factory, interval_s=0, max_passes=1)

        assert built == [], "no bid was due; no client should have been built"
