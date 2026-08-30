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

from backend.bid_watch import cancel_due_bids                     # noqa: E402
from backend.store import db as store                             # noqa: E402
from backend.store.combo_orders import (                          # noqa: E402
    STATUS_CANCELLED,
    STATUS_PENDING,
    record_intent,
    record_outcome,
    working_orders,
)

KICKOFF_MS = 1_788_000_600_000


class FakeApi:
    def __init__(self, *, raises=False):
        self.raises = raises
        self.calls: list = []

    async def cancel_order(self, order_id, *, exchange_index=None):
        self.calls.append((order_id, exchange_index))
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

        assert await cancel_due_bids(conn, api, now_ms=KICKOFF_MS + 1) == 0
        assert api.calls == []
        rows = working_orders(conn)
        assert len(rows) == 1
        assert rows[0]["status"] == STATUS_PENDING


class TestItIsActuallyStarted:
    def test_the_loop_starts_the_watcher_and_stops_it(self):
        """Four modules in this repo were complete and invoked by nothing.

        `watch_bids_forever` is nested behind a live Kalshi client, so the
        honest cheap check is over the source: it is started, and it is
        cancelled on the way out -- a watcher outliving a dead runner holds
        the database half-alive.
        """
        source = (ROOT / "scripts" / "run_loop.py").read_text(encoding="utf-8")

        assert "from backend.bid_watch import watch_bids_forever" in source
        assert "watch_bids_forever(args.db" in source
        assert "bid_task.cancel()" in source
