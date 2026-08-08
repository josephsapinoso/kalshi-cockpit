"""Two taps are one order.

The gap ADR 0008 recorded rather than closed. `client_order_id` stops **Kalshi**
creating a second order when we re-send after a lost response; it could never
stop **us** creating a second one, because every request minted a fresh id -- so
two taps were two ids, two rows, and two orders the exchange would happily have
accepted as distinct. `idempotency_key` comes from the client, the exchange
never sees it, and it does the other half.

Why this matters more here than in most systems: the cockpit is operated from a
phone. A double-tap, and a retry after a dropped connection on a train, are not
exotic failure modes.

What these tests do not establish
---------------------------------
**That a replay is correct against a live fill.** Every order here is a dry run,
so the outcome being replayed is `dry_run` rather than `resting` or `filled`.
What is exercised is the path -- lookup, replay, refusal on an unanswered row --
and not the exchange's own behaviour under a re-send, which stays untested until
a real order exists.
"""

from __future__ import annotations

import threading

import httpx
import pytest

from backend.store import db
from backend.store.orders import (
    DuplicateOrder,
    OrderNotRecorded,
    record_intent,
    reserve_order,
)

from .test_order_record import (
    _app,
    _order,
    _orders_on_disk,
    _post,
    _rows,
    build_seeded_conn,
)
from .test_quote_refresh import FakeQuotes, _live_pick, build_armed_db


@pytest.fixture
def armed_db(tmp_path):
    """Built, not imported.

    Importing the fixture by name puts it in this module's namespace, so every
    test signature that takes `armed_db` is a redefinition of it -- which ruff
    reports as F811, correctly. `test_order_record.py` hit this first and the
    answer there is the answer here: import the *builder* and wrap it.
    """
    return build_armed_db(tmp_path)


@pytest.fixture
def conn(tmp_path):
    connection = build_seeded_conn(tmp_path)
    yield connection
    connection.close()


class TestTwoTapsAreOneOrder:
    async def test_the_same_key_twice_places_one_order(self, armed_db):
        path, connection, now = armed_db
        rec = _live_pick(connection, now)
        app = _app(path, FakeQuotes())

        first = await _post(app, rec, key="one-intent")
        second = await _post(app, rec, key="one-intent")

        assert first.status_code == 200
        assert second.status_code == 200
        assert len(_orders_on_disk(path)) == 1, "the second tap placed a second order"

    async def test_the_second_tap_is_answered_with_the_first_ones_outcome(
        self, armed_db
    ):
        """A replay, not a fresh refusal and not a fresh order.

        The response has to match field for field, because the ticket renders
        it: someone who taps twice must see their order, not a different answer
        about it.
        """
        path, connection, now = armed_db
        rec = _live_pick(connection, now)
        app = _app(path, FakeQuotes())

        first = (await _post(app, rec, key="one-intent")).json()
        second = (await _post(app, rec, key="one-intent")).json()

        assert second["order_id"] == first["order_id"]
        assert second["client_order_id"] == first["client_order_id"]
        assert second["status"] == first["status"]
        assert second["fill_price_tenths"] == first["fill_price_tenths"]
        assert second["request_body"] == first["request_body"]

    async def test_a_replay_says_it_is_one(self, armed_db):
        """The record must not claim a second order was placed.

        A byte-identical response would say exactly that, so `replayed` is the
        one field a replay adds to the answer it repeats.
        """
        path, connection, now = armed_db
        rec = _live_pick(connection, now)
        app = _app(path, FakeQuotes())

        first = (await _post(app, rec, key="one-intent")).json()
        second = (await _post(app, rec, key="one-intent")).json()

        assert first["replayed"] is False
        assert second["replayed"] is True
        assert "no second order" in second["replay_note"].lower()

    async def test_different_keys_are_different_orders(self, armed_db):
        """The guard on the guard.

        An endpoint that refused *every* second order would pass the three
        tests above and be broken: two taps on two cards are two intents, and a
        cockpit that could only ever place one order would be worse than one
        that places two.
        """
        path, connection, now = armed_db
        rec = _live_pick(connection, now)
        app = _app(path, FakeQuotes())

        await _post(app, rec, key="intent-a")
        await _post(app, rec, key="intent-b")

        assert len(_orders_on_disk(path)) == 2

    async def test_a_retry_after_the_row_went_stale_still_replays(self, armed_db):
        """The case the ordering of the checks exists for.

        A retry after a lost response arrives late, and by then the recorded
        quote is past its 30-second limit -- so every freshness check below
        would refuse it with "the price moved", which is the wrong answer to
        the one request that must be told what already happened. The key is
        looked up before all of them.

        The middle assertion is what makes this a fact about the key rather
        than about the row still being fresh: the *same* recommendation with a
        *new* key is refused as stale at the same instant.
        """
        path, connection, now = armed_db
        rec = _live_pick(connection, now)
        app = _app(path, FakeQuotes())

        first = (await _post(app, rec, key="one-intent")).json()

        writer = db.open_db(path)
        try:
            writer.execute(
                "UPDATE recommendations SET created_ms = ?, "
                "last_confirmed_ms = NULL WHERE id = ?",
                # An hour, not a minute. `live_ages` adds the elapsed time to
                # the recorded ages, and the binding limit at order time is the
                # 900s odds window rather than the 30s quote one -- the quote
                # is re-read live, which is the whole point of ADR 0007.
                (now - 60 * 60 * 1000, rec),
            )
            writer.commit()
        finally:
            writer.close()

        # Refused, and *which* refusal is deliberately not pinned: ageing the
        # row past the odds window also takes the gate's freshness condition
        # with it, so this lands on 423 rather than 422 and either would do.
        # The claim is that the identical request is refused at this instant
        # with a new key -- not which of the thirteen checks gets there first.
        with_new_key = await _post(app, rec, key="a-different-intent")
        assert with_new_key.status_code >= 400, with_new_key.json()

        replayed = await _post(app, rec, key="one-intent")
        assert replayed.status_code == 200
        assert replayed.json()["order_id"] == first["order_id"]
        assert len(_orders_on_disk(path)) == 1

    async def test_an_unanswered_row_refuses_rather_than_sending_another(
        self, armed_db
    ):
        """The process died between reserving the row and replying.

        There may be an order resting on the exchange under that row's
        `client_order_id`, and nothing in this database can say whether there
        is. Sending a second one is the unsafe direction; so is pretending the
        first succeeded. It refuses, and names the id to reconcile.
        """
        path, connection, now = armed_db
        rec = _live_pick(connection, now)
        app = _app(path, FakeQuotes())

        await _post(app, rec, key="one-intent")
        writer = db.open_db(path)
        try:
            writer.execute("UPDATE orders SET response_body_json = NULL")
            writer.commit()
        finally:
            writer.close()

        again = await _post(app, rec, key="one-intent")
        assert again.status_code == 409
        assert "reconcile" in again.json()["detail"].lower()
        assert "client_order_id" in again.json()["detail"]
        assert len(_orders_on_disk(path)) == 1

    async def test_a_missing_key_is_refused_by_the_endpoint(self, armed_db):
        """Required, not optional.

        An optional idempotency key protects only the clients that remember to
        send one, which is the shape of a guard that cannot fail. Refused by
        the request model, before any check runs and before anything is written.
        """
        path, connection, now = armed_db
        rec = _live_pick(connection, now)
        transport = httpx.ASGITransport(app=_app(path, FakeQuotes()))
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            response = await c.post(
                "/api/orders",
                headers={"Authorization": "Bearer t"},
                json={"recommendation_id": rec, "contracts": 20},
            )

        assert response.status_code == 422
        assert _orders_on_disk(path) == []


class TestTheThreeLayersAreNotOneLayerRepeated:
    """Each covers a case the others cannot, which is why there are three."""

    def test_two_concurrent_taps_on_one_key_write_one_row(self, conn, tmp_path):
        """The read at step 0 cannot be the guarantee, and this is why.

        Two taps landing together both miss it. What separates them is the
        write lock `reserve_order` already takes: the second blocks at `BEGIN
        IMMEDIATE` until the first has committed, and only then looks. Real
        threads on real connections, for the reason the cap's own concurrency
        test gives -- `TestClient` drives the app through one portal and never
        makes the hop.
        """
        # The same file the `conn` fixture built and seeded a market into, so
        # the `orders` foreign key resolves on both writer connections.
        path = tmp_path / "record.db"
        barrier = threading.Barrier(2)
        results: list = []
        lock = threading.Lock()

        def attempt(index: int) -> None:
            writer = db.open_db(path)
            try:
                order = _order("T", count=10, price_tenths=500)
                object.__setattr__(order, "client_order_id", f"coid-{index}")
                barrier.wait(timeout=10)
                reserve_order(
                    writer, order,
                    dry_run=False, submitted_ms=index,
                    max_exposure_dollars=1_000.0,
                    idempotency_key="one-intent",
                )
                outcome = "accepted"
            except DuplicateOrder:
                outcome = "duplicate"
            except Exception as exc:                        # noqa: BLE001
                outcome = f"error: {type(exc).__name__}: {exc}"
            finally:
                writer.close()
            with lock:
                results.append(outcome)

        threads = [threading.Thread(target=attempt, args=(i,)) for i in (1, 2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert sorted(results) == ["accepted", "duplicate"], results

        reader = db.open_db(path, read_only=True)
        try:
            assert len(_rows(reader)) == 1
        finally:
            reader.close()

    def test_the_index_stops_a_duplicate_that_bypasses_reserve_order(self, conn):
        """`record_intent` commits on its own and never passes through
        `reserve_order`, so neither the write lock nor the in-transaction
        lookup covers it. The UNIQUE index is what keeps the property true for
        a writer added later that forgets to ask."""
        record_intent(
            conn, _order("T"), dry_run=True, submitted_ms=1,
            idempotency_key="one-intent",
        )
        with pytest.raises(OrderNotRecorded):
            record_intent(
                conn, _order("T"), dry_run=True, submitted_ms=2,
                idempotency_key="one-intent",
            )

    def test_rows_without_a_key_do_not_collide(self, conn):
        """Every row written before v3 carries NULL, and the live volume has them.

        SQLite treats NULLs as distinct in a UNIQUE index, which is what makes
        the constraint addable to a table with history at all. Asserted rather
        than assumed, because the alternative is a migration that fails on the
        live volume and nowhere else.
        """
        for index in range(3):
            record_intent(conn, _order("T"), dry_run=True, submitted_ms=index)
        assert len(_rows(conn)) == 3
