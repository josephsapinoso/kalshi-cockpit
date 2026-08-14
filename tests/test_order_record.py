"""The order record: what gets written, when, and what exposure reads back.

What these tests establish
--------------------------
That an order reaching the placer is on disk **before** the request is made,
that a refusal writes nothing, and that `current_exposure_dollars` sums the
population a pre-trade cap needs rather than the one that happens to be easy
to enumerate.

What they do **not** establish
------------------------------
- **Nothing here has been through a live fill.** Every status other than
  `pending` and `dry_run` is written by hand, because no order has ever been
  placed by this project. The status *values* come from `kalshi/orders.py`; the
  claim that Kalshi produces them is untested and stays untested until a real
  order exists.
- **They say nothing about concurrency.** Two requests can each read exposure,
  size against it, and insert. Serialising that needs the read and the insert
  in one write transaction.
- **They do not exercise the cap in production terms.** Every order the running
  system places is a dry run, and dry runs are excluded from exposure by
  design, so `max_exposure_dollars` still does not bind on the live instance.
  The tests below bind it by writing `dry_run = 0` rows directly.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid

import httpx
import pytest

from backend.api.routes import create_app
from backend.config import (
    AppConfig,
    GateConfig,
    RiskConfig,
    StalenessConfig,
)
from backend.core.fees import calculate_fee
from backend.core.suppression import SuppressionConfig
from backend.kalshi.grid import parse_price_grid
from backend.kalshi.orders import OrderOutcome, OrderRequest, canonical_body_json
from backend.store import db
from backend.store.orders import (
    ExposureCapExceeded,
    OrderNotRecorded,
    current_exposure_dollars,
    order_exposure_dollars,
    record_intent,
    record_outcome,
    reserve_order,
)

from .test_quote_refresh import (
    ARMED,
    FRESH,
    TICKER,
    FakeQuotes,
    _live_pick,
    _market,
    build_armed_db,
)

WHOLE_CENT = parse_price_grid(
    [{"start": "0.0000", "end": "1.0000", "step": "0.0100"}],
    structure="linear_cent",
)


# What the default `_order` below commits: $5.00 of stake on ten 50c contracts
# plus the taker fee. Named rather than repeated, because the population and
# release tests below are about *which* orders count, not about the fee -- and a
# fee recalibration (a live-gate condition) should not turn six of them red for
# a reason none of them is testing. `TestExposureIsSpentAndAccumulatedAtThe
# SamePrice` pins the number itself.
#
# **Derived rather than hardcoded, since 2026-08-14.** It was `5.20`, and the
# fee recalibration this comment predicted duly turned six of these red -- the
# comment named the hazard and the literal walked into it anyway. The fee moved
# from 20c (the retired `max()`, driven by the now-refuted Model B on a cent
# grid) to 17.5c (the measured model on a $0.0001 grid). Computing it from
# `calculate_fee` is legitimate here precisely because these tests are about
# `current_exposure_dollars`, not about `core.fees` -- which has its own suite,
# including anchors against 11 real fills.
ONE_ORDER = 5.00 + calculate_fee(500, 10)


def _order(ticker="T", *, side="yes", price_tenths=500, count=10, rec_id=None):
    return OrderRequest(
        ticker=ticker,
        side=side,
        action="buy",
        count=count,
        limit_price_tenths=price_tenths,
        price_grid=WHOLE_CENT,
        recommendation_id=rec_id,
    )


@pytest.fixture
def armed_db(tmp_path):
    """The gate-satisfying record from the quote-refresh suite.

    Built rather than imported. Re-exporting the fixture itself puts the name
    in this module's namespace, where every test signature that takes
    `armed_db` then shadows it -- which reads as a redefinition because it is
    one, and would leave a stale import here the day that fixture is renamed.
    """
    return build_armed_db(tmp_path)


@pytest.fixture
def conn(tmp_path):
    """The seeded record, as a fixture. See `build_seeded_conn`."""
    connection = build_seeded_conn(tmp_path)
    yield connection
    connection.close()


def build_seeded_conn(tmp_path):
    """An empty record with one market, so the `orders` foreign key resolves.

    Opened through `db.init_db`, so `PRAGMA foreign_keys` is **on** and the
    series and event have to exist before the market does. Several older
    fixtures in this suite reach for `sqlite3.connect` directly, which leaves
    the pragma off and lets a market row exist with no event behind it -- a row
    the application could never write. Building it the hard way here is what
    makes the foreign-key test below mean anything.
    """
    path = tmp_path / "record.db"
    connection = db.init_db(path)
    connection.execute(
        "INSERT INTO kalshi_series (series_ticker, first_seen_ms, last_seen_ms) "
        "VALUES ('S', 0, 0)"
    )
    connection.execute(
        "INSERT INTO kalshi_events (event_ticker, series_ticker, first_seen_ms, "
        "last_seen_ms) VALUES ('EVT-T', 'S', 0, 0)"
    )
    connection.execute(
        "INSERT INTO kalshi_markets (ticker, event_ticker, series_ticker, "
        "first_seen_ms, last_seen_ms) VALUES ('T', 'EVT-T', 'S', 0, 0)"
    )
    connection.commit()
    # Asserted, not assumed. `INSERT OR IGNORE` swallowed a constraint failure
    # in the gate fixtures for the life of the project and every join below it
    # matched nothing -- see `tasks/lessons.md`.
    assert connection.execute(
        "SELECT COUNT(*) AS n FROM kalshi_markets"
    ).fetchone()["n"] == 1
    return connection


def _rows(conn):
    return conn.execute("SELECT * FROM orders ORDER BY id").fetchall()


# ---------------------------------------------------------------------------
# What is stored
# ---------------------------------------------------------------------------


class TestWhatARowHolds:
    def test_the_intent_row_says_pending_before_anything_is_placed(self, conn):
        """`pending` is the only honest status for an order not yet sent.

        Not `dry_run`, and certainly not `resting`: at the moment this row is
        written nothing has happened, and a row that already claimed an outcome
        would make the write-before-send ordering unobservable.
        """
        row_id = record_intent(conn, _order(), dry_run=True, submitted_ms=123)
        row = _rows(conn)[0]
        assert row["id"] == row_id
        assert row["status"] == "pending"
        assert row["submitted_ms"] == 123
        assert row["dry_run"] == 1

    def test_the_stored_price_is_what_we_pay_not_what_goes_on_the_wire(self, conn):
        """A NO order is where these two numbers differ, so it is the test.

        Buying NO at 40.5c is selling YES at 59.5c, which is an **ask**, so it
        snaps *up* to 60c on a whole-cent grid -- and reflecting that back
        leaves us paying 40c. Snapping the wire price up is what moves our
        price down; both halves are "away from paying more".

        So the column must hold 400 and the wire must carry `0.6000`. A wrong
        implementation stores 600, which is entirely plausible on inspection:
        a legal price, on the right grid, for the right market, differing only
        by being the other leg. Exposure would then read a 40c position as a
        60c one -- overstated here, and understated for any NO bet above 50c,
        which is the direction that lets the cap pass what it should refuse.
        """
        order = _order(side="no", price_tenths=405)
        record_intent(conn, order, dry_run=True, submitted_ms=1)
        row = _rows(conn)[0]

        assert row["limit_price_tenths"] == order.fill_price_tenths == 400
        # ...while the wire carries the YES complement, and it is not lost.
        assert json.loads(row["request_body_json"])["price"] == "0.6000"
        assert row["side"] == "no"

    def test_the_stored_body_is_the_bytes_the_placer_would_send(self, conn):
        """The whole point of `request_body_json`: a dry run comparable to a
        live order as text. Written before the placer runs, so the two have to
        serialise identically or the comparison is meaningless."""
        order = _order()
        record_intent(conn, order, dry_run=True, submitted_ms=1)
        outcome = OrderOutcome(
            request=order, status="dry_run", dry_run=True,
            request_body=order.to_api_dict(),
        )
        assert _rows(conn)[0]["request_body_json"] == outcome.request_body_json

    def test_the_recommendation_is_joined_so_clv_and_the_fill_meet(self, conn):
        """The reason this item mattered.

        CLV scores off `entry_ask_tenths` and the order goes out at the live
        ask, so the gate's evidence and the price actually paid were different
        numbers with nothing connecting them.
        """
        conn.execute(
            "INSERT INTO strategy_configs (version, created_ms, effective_from_ms, "
            "config_json, rationale, approved_by_user) VALUES (1, 0, 0, '{}', 't', 1)"
        )
        conn.execute(
            "INSERT INTO recommendations (created_ms, strategy_config_version, "
            "ticker, side, entry_ask_tenths, fair_probability, edge_tenths, "
            "fee_predicted, ev_net_dollars, kelly_fraction, suggested_contracts, "
            "reference_contracts, kalshi_quote_age_ms, odds_age_ms, reason_text) "
            "VALUES (0, 1, 'T', 'yes', 500, 0.54, 20.0, 0.1, 0.5, 0.02, 10, 10, "
            "0, 0, 'x')"
        )
        conn.commit()
        rec_id = conn.execute(
            "SELECT id FROM recommendations"
        ).fetchone()["id"]

        record_intent(conn, _order(rec_id=rec_id), dry_run=True, submitted_ms=1)
        joined = conn.execute(
            "SELECT r.entry_ask_tenths, o.limit_price_tenths FROM orders o "
            "JOIN recommendations r ON r.id = o.recommendation_id"
        ).fetchone()
        assert joined["entry_ask_tenths"] == 500
        assert joined["limit_price_tenths"] == 500

    def test_a_duplicate_client_order_id_raises_rather_than_being_ignored(self, conn):
        """`INSERT OR IGNORE` would turn two orders sharing an idempotency key
        into one row and no error. That is the DDL form of unreadable-resolves-
        to-zero, and this repo has already lost a fixture to it."""
        order = _order()
        record_intent(conn, order, dry_run=True, submitted_ms=1)
        with pytest.raises(OrderNotRecorded):
            record_intent(conn, order, dry_run=True, submitted_ms=2)
        assert len(_rows(conn)) == 1

    def test_an_unknown_market_is_refused_by_the_foreign_key(self, conn):
        """Not decoration -- `PRAGMA foreign_keys` is set per connection, so
        this fails the day someone opens one without it."""
        with pytest.raises(OrderNotRecorded):
            record_intent(conn, _order("NEVER-SEEN"), dry_run=True, submitted_ms=1)

    def test_the_outcome_stamps_the_row_it_was_given(self, conn):
        order = _order()
        row_id = record_intent(conn, order, dry_run=True, submitted_ms=1)
        record_outcome(
            conn, row_id,
            OrderOutcome(
                request=order, status="resting", dry_run=False,
                request_body=order.to_api_dict(), kalshi_order_id="K-1",
            ),
        )
        row = _rows(conn)[0]
        assert row["status"] == "resting"
        assert row["kalshi_order_id"] == "K-1"


# ---------------------------------------------------------------------------
# Exposure
# ---------------------------------------------------------------------------


def _live_order(conn, *, status, price_tenths=500, count=10, ticker="T", suffix=""):
    """A non-dry-run row in a given status, written the way the code writes it."""
    order = _order(ticker, price_tenths=price_tenths, count=count)
    row_id = record_intent(conn, order, dry_run=False, submitted_ms=1)
    conn.execute("UPDATE orders SET status = ? WHERE id = ?", (status, row_id))
    conn.commit()
    return row_id


class TestExposureCountsTheRightPopulation:
    """The old query enumerated `('pending','resting','filled')`.

    Two live statuses were missing from that list, and both are exposure. The
    tests are written per status rather than as one loop so a failure names the
    status that broke.
    """

    @pytest.mark.parametrize(
        "status",
        ["pending", "resting", "partially_filled", "filled",
         # The one that matters most. `unrecognised_response` means "the
         # response could not be read, so this order may have filled". An
         # enumeration of live statuses drops it to zero, which is the
         # unreadable-resolves-to-zero failure applied to a whole position.
         "unrecognised_response",
         # Anything the exchange or a later version of `kalshi/orders.py`
         # produces that nobody here has thought about. Counting is the
         # direction that refuses an order rather than permitting one.
         "some_status_nobody_has_written_yet"],
    )
    def test_a_live_order_counts(self, conn, status):
        _live_order(conn, status=status)
        assert current_exposure_dollars(conn) == pytest.approx(ONE_ORDER)

    @pytest.mark.parametrize("status", ["unfilled", "rejected", "canceled"])
    def test_a_finished_order_costs_nothing(self, conn, status):
        _live_order(conn, status=status)
        assert current_exposure_dollars(conn) == 0.0

    def test_a_dry_run_is_not_exposure(self, conn):
        """And the cost of that is stated rather than hidden: it is why the cap
        does not bind on the live instance today."""
        record_intent(conn, _order(), dry_run=True, submitted_ms=1)
        assert current_exposure_dollars(conn) == 0.0

    def test_an_empty_table_is_a_true_zero_not_an_unreadable_one(self, conn):
        """`size_position` refuses on `None`, so `0.0` here is a claim. It is a
        true one: "no live orders" is a fact about the table."""
        assert current_exposure_dollars(conn) == 0.0

    def test_an_order_with_no_price_refuses_rather_than_summing_to_zero(self, conn):
        """`SUM` skips NULLs, so an unpriced order would read as a free
        position and quietly enlarge the room under the cap."""
        _live_order(conn, status="resting")
        conn.execute("UPDATE orders SET limit_price_tenths = NULL")
        conn.commit()
        assert current_exposure_dollars(conn) is None

    def test_a_settled_position_releases_its_capital(self, conn):
        _live_order(conn, status="filled")
        assert current_exposure_dollars(conn) == pytest.approx(ONE_ORDER)
        order_id = conn.execute("SELECT id FROM orders").fetchone()["id"]
        conn.execute(
            "INSERT INTO settlements (order_id, ticker, settled_ms, result, "
            "contracts, pnl_cents, dry_run) VALUES (?, 'T', 1, 'yes', 10, 500, 0)",
            (order_id,),
        )
        conn.commit()
        assert current_exposure_dollars(conn) == 0.0

    def test_settling_one_order_does_not_release_another_on_the_same_ticker(
        self, conn
    ):
        """The reason `settlements` was rebuilt in schema v4.

        The old query matched on `ticker`, so any settlement row released
        **every** order on that market. That is correct while there is one order
        per ticker and wrong the moment there are two, which is ordinary -- a
        quote pass re-recommends a market minutes later and the Board offers
        both. The old schema could not even express this test: `UNIQUE (ticker,
        settled_ms)` meant the second position's settlement row was rejected.
        """
        _live_order(conn, status="filled")
        _live_order(conn, status="filled")
        assert current_exposure_dollars(conn) == pytest.approx(2 * ONE_ORDER)

        first = conn.execute("SELECT id FROM orders ORDER BY id").fetchone()["id"]
        conn.execute(
            "INSERT INTO settlements (order_id, ticker, settled_ms, result, "
            "contracts, pnl_cents, dry_run) VALUES (?, 'T', 1, 'yes', 10, 500, 0)",
            (first,),
        )
        conn.commit()

        assert current_exposure_dollars(conn) == pytest.approx(ONE_ORDER), (
            "settling one position released the other one on the same ticker"
        )

    def test_paper_and_live_exposure_are_separate_budgets(self, conn):
        """Two populations, never pooled -- ADR 0010 decision 4.

        A live order must not size against a budget consumed by paper
        positions, and paper exposure has to be visible at all or the cap goes
        on being exercised only by tests.
        """
        record_intent(conn, _order(), dry_run=True, submitted_ms=1)

        assert current_exposure_dollars(conn, dry_run=True) == pytest.approx(ONE_ORDER)
        assert current_exposure_dollars(conn, dry_run=False) == 0.0

    def test_a_no_position_is_measured_at_what_it_cost(self, conn):
        """Not at its YES complement. Ten contracts of NO at 40.5c snap to 40c
        and cost $4.00 in stake; measured on the wire leg they would read
        $6.00. The wrong answer over-states here and under-states for any NO
        bet above 50c, and under-stating exposure is how a cap passes a
        position it should refuse."""
        order = _order(side="no", price_tenths=405, count=10)
        record_intent(conn, order, dry_run=False, submitted_ms=1)
        assert current_exposure_dollars(conn) == pytest.approx(4.00 + 0.168), (
            "the stake is right; the 16.8c taker fee on ten 40c contracts is the "
            "part exposure used to leave out"
        )

    def test_an_unreadable_table_is_none_not_zero(self, conn):
        conn.execute("DROP TABLE orders")
        conn.commit()
        assert current_exposure_dollars(conn) is None


class TestOneOrderSumsToWhatItContributes:
    """A ticket saying "this takes you to $X" and the cap that later refuses it
    must not compute X two ways.

    They used to be two implementations pinned by this test -- a Python
    expression and a SQL `SUM`. They agreed, and they were both wrong in the
    same way: both left the fee out while `size_position` spent the cap
    fee-inclusive. That is precisely what a test comparing two paths cannot
    catch, so the SQL sum is gone and both callers reach
    `exposure_contribution`.
    """

    @pytest.mark.parametrize(
        "side,price,count", [("yes", 500, 10), ("no", 405, 7), ("yes", 990, 3)]
    )
    def test_they_agree(self, conn, side, price, count):
        order = _order(side=side, price_tenths=price, count=count)
        record_intent(conn, order, dry_run=False, submitted_ms=1)
        assert current_exposure_dollars(conn) == pytest.approx(
            order_exposure_dollars(order)
        )


class TestExposureIsSpentAndAccumulatedAtTheSamePrice:
    """`size_position` spends the cap at `effective_price`, which includes the
    fee. Exposure summed the bare stake.

    So every order consumed more of the cap than it added back, and the next
    order sized against a portfolio reported cheaper than it was. About 2% of
    stake -- small, systematic, and in the unsafe direction. It never bit
    because no live order has ever been placed, which is the only reason this
    could be deferred rather than fixed.
    """

    def test_the_fee_is_counted(self, conn):
        """Ten contracts at 50c: $5.00 of stake and a 17.5c taker fee.

        **Was 20c until 2026-08-14.** The retired `max()` returned Model B's
        per-contract cent rounding, which lifted 1.75c/contract to 2c. The
        measured model charges `ceil(0.07 * 10 * 0.25)` on a $0.0001 grid --
        $0.175 exactly, no rounding applied at all. Hardcoded on purpose: this
        class is the one that pins the number.
        """
        record_intent(conn, _order(), dry_run=False, submitted_ms=1)
        assert current_exposure_dollars(conn) == pytest.approx(5.175)

    def test_it_matches_what_sizing_spent(self, conn):
        """The two prices, side by side.

        `effective_price` is what a contract costs the cap; exposure per
        contract must be the same number, or the two disagree by exactly the
        fee -- which is what they did.
        """
        from backend.core.ev import effective_price

        record_intent(conn, _order(), dry_run=False, submitted_ms=1)
        exposure = current_exposure_dollars(conn)
        spent = 10 * effective_price(500, contracts=1, maker=False)

        assert exposure == pytest.approx(spent, abs=0.005)

    def test_an_untradeable_price_refuses_rather_than_costing_nothing(self, conn):
        """`calculate_fee` returns None off the tradeable range.

        A row like this cannot be created through `OrderRequest`, which
        validates in its constructor -- but exposure reads the database, and a
        database can hold what the constructor would have refused. Substituting
        a zero fee here would report a settled-price order as almost free.
        """
        record_intent(conn, _order(), dry_run=False, submitted_ms=1)
        conn.execute("UPDATE orders SET limit_price_tenths = 1000")
        conn.commit()

        assert current_exposure_dollars(conn) is None

    def test_one_unreadable_order_refuses_the_whole_sum(self, conn):
        """Not "skip it and total the rest".

        Skipping reports a smaller exposure than the truth and hands the next
        order room it does not have -- the unreadable-resolves-to-zero failure
        one level up, at the level of a row rather than a field.
        """
        record_intent(conn, _order(), dry_run=False, submitted_ms=1)
        second = record_intent(conn, _order(), dry_run=False, submitted_ms=2)
        conn.execute(
            "UPDATE orders SET limit_price_tenths = NULL WHERE id = ?", (second,)
        )
        conn.commit()

        assert current_exposure_dollars(conn) is None

    def test_the_ticket_reports_no_number_rather_than_a_wrong_one(self):
        """`order_exposure_dollars` is Optional for the same reason.

        The endpoint adds it to the exposure before the order. A `None`
        silently treated as zero would render a ticket saying this order costs
        nothing, which is the one reading a person acts on without pausing.
        """
        assert order_exposure_dollars(_order()) == pytest.approx(ONE_ORDER)


class TestThereIsOneDefinitionOfExposure:
    def test_the_runner_and_the_order_path_call_the_same_function(self):
        """`runner.py` used to sum `fills` while the endpoint summed `orders`.

        Both were vacuous while no table had a row, so they had never
        disagreed. This asserts the deletion held rather than that the two
        happen to agree -- per `tasks/lessons.md`, don't test that two paths
        agree, delete one of them.
        """
        from backend import runner
        from backend.store import orders as store_orders

        assert runner.current_exposure_dollars is store_orders.current_exposure_dollars


# ---------------------------------------------------------------------------
# The endpoint
# ---------------------------------------------------------------------------


def _app(path, quotes, *, risk=None):
    return create_app(
        AppConfig(instance_mode="live", auth_token="t", db_path=path),
        gate_config=ARMED,
        risk_config=risk or RiskConfig(),
        staleness_config=FRESH,
        suppression_config=SuppressionConfig(),
        quote_source=quotes,
    )


async def _post(app, rec_id, contracts=20, key=None):
    """A distinct idempotency key per call unless one is named.

    Every call is a separate intent unless a test says otherwise, so a fresh
    key keeps these assertions meaning what they meant before the endpoint
    required one. Passing `key` twice is how a duplicate tap is expressed.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        return await c.post(
            "/api/orders",
            headers={"Authorization": "Bearer t"},
            json={
                "recommendation_id": rec_id,
                "contracts": contracts,
                "idempotency_key": key or uuid.uuid4().hex,
            },
        )


def _orders_on_disk(path):
    conn = db.open_db(path, read_only=True)
    try:
        return conn.execute("SELECT * FROM orders ORDER BY id").fetchall()
    finally:
        conn.close()


class TestTheEndpointRecordsWhatItPlaces:
    async def test_a_dry_run_leaves_a_row_naming_its_recommendation(self, armed_db):
        path, conn, now = armed_db
        rec = _live_pick(conn, now)
        response = await _post(_app(path, FakeQuotes()), rec)
        assert response.status_code == 200, response.text
        body = response.json()

        rows = _orders_on_disk(path)
        assert len(rows) == 1
        row = rows[0]
        assert row["id"] == body["order_id"]
        assert row["client_order_id"] == body["client_order_id"]
        assert row["recommendation_id"] == rec
        assert row["ticker"] == TICKER
        assert row["status"] == "dry_run"
        assert row["dry_run"] == 1
        assert body["recorded"]["outcome_recorded"] is True

    async def test_the_row_holds_the_bytes_the_response_reports(self, armed_db):
        path, conn, now = armed_db
        rec = _live_pick(conn, now)
        body = (await _post(_app(path, FakeQuotes()), rec)).json()
        assert _orders_on_disk(path)[0]["request_body_json"] == canonical_body_json(
            body["request_body"]
        )

    async def test_a_refused_order_writes_nothing(self, armed_db):
        """`orders` means orders, not attempts.

        Today essentially every tap is refused at the gate, so a table of
        attempts would be a table of refusals -- and this repo's own rule is
        that a log dominated by the normal case has stopped being a diagnostic.
        The refusal already reaches the caller and the log.
        """
        path, conn, now = armed_db
        rec = _live_pick(conn, now, suppressed="stale_odds")
        response = await _post(_app(path, FakeQuotes()), rec)
        assert response.status_code == 422
        assert _orders_on_disk(path) == []

    async def test_the_response_carries_the_exposure_the_caps_were_read_against(
        self, armed_db
    ):
        path, conn, now = armed_db
        rec = _live_pick(conn, now)
        body = (await _post(_app(path, FakeQuotes()), rec)).json()
        assert body["exposure_before_dollars"] == 0.0
        assert body["resulting_exposure_dollars"] > 0.0
        # A dry run commits nothing, so the number above is what *would*
        # happen. Saying so is the difference between a ticket and a claim.
        assert body["resulting_exposure_is_hypothetical"] is True
        assert body["max_exposure_dollars"] == RiskConfig().max_exposure_dollars


class TestTheRowIsOnDiskBeforeTheRequestIsMade:
    """The load-bearing claim of the whole change.

    `client_order_id` is an idempotency key, and the failure it exists for is a
    POST that times out *after* Kalshi accepted it. Recording after the response
    loses the key in exactly that case.
    """

    async def test_the_placer_can_already_see_its_own_pending_row(
        self, armed_db, monkeypatch
    ):
        path, conn, now = armed_db
        rec = _live_pick(conn, now)
        seen = {}

        real_placer = __import__(
            "backend.kalshi.orders", fromlist=["OrderPlacer"]
        ).OrderPlacer

        class WatchingPlacer(real_placer):
            async def place(self, request):
                # Read the record from a *separate* connection, so this sees
                # committed state rather than an open transaction.
                reader = db.open_db(path, read_only=True)
                try:
                    seen["rows"] = [
                        dict(r) for r in reader.execute("SELECT * FROM orders")
                    ]
                finally:
                    reader.close()
                return await super().place(request)

        monkeypatch.setattr("backend.api.routes.OrderPlacer", WatchingPlacer)
        response = await _post(_app(path, FakeQuotes()), rec)
        assert response.status_code == 200, response.text

        assert len(seen["rows"]) == 1, "the order was sent before it was recorded"
        assert seen["rows"][0]["status"] == "pending"
        assert seen["rows"][0]["client_order_id"] == response.json()["client_order_id"]


class TestAnOrderThatCannotBeRecordedIsNotSent:
    async def test_a_failed_write_refuses_and_never_reaches_the_placer(
        self, armed_db, monkeypatch
    ):
        path, conn, now = armed_db
        rec = _live_pick(conn, now)
        placed = []

        def explode(*_a, **_k):
            raise OrderNotRecorded("disk is on fire")

        real_placer = __import__(
            "backend.kalshi.orders", fromlist=["OrderPlacer"]
        ).OrderPlacer

        class CountingPlacer(real_placer):
            async def place(self, request):
                placed.append(request)
                return await super().place(request)

        monkeypatch.setattr("backend.api.routes.reserve_order", explode)
        monkeypatch.setattr("backend.api.routes.OrderPlacer", CountingPlacer)

        response = await _post(_app(path, FakeQuotes()), rec)
        assert response.status_code == 503
        assert "could not be written down first" in response.json()["detail"]
        assert placed == [], "an unrecordable order was sent anyway"


class TestAFailedOutcomeWriteDoesNotUnwindThePlacement:
    async def test_the_request_still_succeeds_and_says_the_row_is_stale(
        self, armed_db, monkeypatch
    ):
        """By this point the request has gone. On a live order the money has
        moved whatever this connection does, so the response reports the gap
        instead of pretending the order did not happen."""
        path, conn, now = armed_db
        rec = _live_pick(conn, now)

        def explode(*_a, **_k):
            raise OrderNotRecorded("disk is on fire")

        monkeypatch.setattr("backend.api.routes.record_outcome", explode)
        response = await _post(_app(path, FakeQuotes()), rec)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["recorded"]["outcome_recorded"] is False
        assert "reconcile" in body["recorded"]["note"]

        # And the row survives in the state reconciliation is written to read.
        row = _orders_on_disk(path)[0]
        assert row["status"] == "pending"
        assert row["client_order_id"] == body["client_order_id"]


class TestTheCapBindsOnceOrdersAreLive:
    """Every order the running system places is a dry run, so this is the only
    place `max_exposure_dollars` is exercised against recorded orders at all.
    Written by hand for that reason, and the docstring at the top of this file
    says so rather than letting a green suite imply production coverage."""

    async def test_a_live_order_already_at_the_cap_stops_the_next_one(
        self, armed_db
    ):
        """The same request, twice, with one live order written in between.

        Asserted as a *pair* rather than as one refusal, because a single 422
        proves nothing about the cap -- a dozen other checks return 422 and any
        of them could be what fired. Accepted, then refused, with only the
        recorded order changing, is the claim.
        """
        path, conn, now = armed_db
        rec = _live_pick(conn, now)
        _market(conn, "OTHER")
        conn.commit()
        risk = RiskConfig(max_exposure_dollars=100.0)

        first = await _post(_app(path, FakeQuotes(), risk=risk), rec)
        assert first.status_code == 200, first.text
        # Nothing was outstanding before it, so this is a true zero rather than
        # the structural one it used to be.
        assert first.json()["exposure_before_dollars"] == 0.0

        writer = db.open_db(path)
        try:
            record_intent(
                writer,
                OrderRequest(
                    ticker="OTHER", side="yes", action="buy", count=200,
                    limit_price_tenths=500, price_grid=WHOLE_CENT,
                ),
                # **Paper**, matching the population the endpoint places into.
                # This was `dry_run=False` and the test passed only because
                # exposure counted live rows unconditionally -- so it was
                # blocking a paper order with live capital, which ADR 0010
                # identifies as the thing that would refuse the first real order
                # for a fictional reason. Since every order this project places
                # is paper, the blocking order has to be paper too.
                dry_run=True, submitted_ms=1,
            )
        finally:
            writer.close()
        # $100 of paper exposure against a $100 cap leaves no room at all.
        conn.execute(
            "UPDATE orders SET status = 'resting' WHERE client_order_id NOT IN "
            "(SELECT client_order_id FROM orders ORDER BY id LIMIT 1)"
        )
        conn.commit()

        second = await _post(_app(path, FakeQuotes(), risk=risk), rec)
        assert second.status_code == 422
        detail = second.json()["detail"]
        # And it names the cap that bound. `no_room` used to overwrite it,
        # which told a person holding a phone only that the answer was zero.
        assert "max_exposure_dollars" in detail, detail


class TestTheCapIsAppliedInsideTheTransactionThatWritesTheOrder:
    """Two requests can be sized against one exposure reading. One cannot be
    *recorded* against one.

    The endpoint reads exposure on its read-only handle, sizes, and then writes
    on a different connection. That gap is not exotic -- it is two taps, or a
    tap and a retry -- and while it was open `max_exposure_dollars` bounded
    each order separately and the portfolio not at all.
    """

    def _live(self, ticker="T", *, count, price_tenths=500, coid=None):
        order = _order(ticker, count=count, price_tenths=price_tenths)
        if coid is not None:
            object.__setattr__(order, "client_order_id", coid)
        return order

    def test_an_order_that_would_breach_the_cap_is_rolled_back_entirely(
        self, conn, tmp_path
    ):
        """Refused *and* leaves nothing behind.

        A pending row for an order that was never sent is counted as exposure
        by design -- "we might have an open order" must not resolve to "we do
        not" -- so a refusal that left one would permanently consume budget for
        a bet that never existed.
        """
        path = tmp_path / "record.db"
        writer = db.open_db(path)
        try:
            with pytest.raises(ExposureCapExceeded) as caught:
                reserve_order(
                    writer,
                    self._live(count=100, price_tenths=500),   # $50 + $1.75 fee
                    dry_run=False,
                    submitted_ms=1,
                    max_exposure_dollars=10.0,
                )
            assert caught.value.exposure_after == pytest.approx(51.75)
            assert caught.value.cap == 10.0
            assert _rows(writer) == [], "the refused order stayed on disk"
        finally:
            writer.close()

    def test_an_order_inside_the_cap_is_committed_and_visible_to_another_reader(
        self, conn, tmp_path
    ):
        """Committed, not merely inserted. A row held open in an uncommitted
        transaction is invisible to the next request, which is the same race
        with an extra step."""
        path = tmp_path / "record.db"
        writer = db.open_db(path)
        reader = db.open_db(path, read_only=True)
        try:
            row_id = reserve_order(
                writer,
                self._live(count=10, price_tenths=500),        # $5 + 20c fee
                dry_run=False,
                submitted_ms=1,
                max_exposure_dollars=100.0,
            )
            assert row_id > 0
            assert current_exposure_dollars(reader) == pytest.approx(ONE_ORDER)
        finally:
            writer.close()
            reader.close()

    def test_two_concurrent_reservations_cannot_both_pass_one_cap(
        self, conn, tmp_path
    ):
        """The test the whole change exists for.

        Two orders, each of which fits on its own and which together do not,
        started at the same instant on two connections. Exactly one must
        survive. Real threads and real connections: `TestClient` drives the app
        through a single portal and never makes the hop, which is how the
        previous concurrency regression test in this repo passed against the
        unfixed code. See `tasks/lessons.md`.
        """
        path = tmp_path / "record.db"
        cap = 60.0                       # two $40 orders fit singly, not both
        barrier = threading.Barrier(2)
        results: list = []
        lock = threading.Lock()

        def attempt(index: int) -> None:
            writer = db.open_db(path)
            try:
                order = self._live(count=80, price_tenths=500, coid=f"coid-{index}")
                barrier.wait(timeout=10)
                reserve_order(
                    writer, order,
                    dry_run=False, submitted_ms=index,
                    max_exposure_dollars=cap,
                )
                outcome = "accepted"
            except ExposureCapExceeded:
                outcome = "refused"
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

        assert sorted(results) == ["accepted", "refused"], results

        reader = db.open_db(path, read_only=True)
        try:
            assert current_exposure_dollars(reader) == pytest.approx(8 * ONE_ORDER)
            assert len(_rows(reader)) == 1, "the refused order was left on disk"
        finally:
            reader.close()

    def test_a_dry_run_consumes_none_of_the_LIVE_cap(self, conn, tmp_path):
        """Paper positions are not capital, so they never touch a live budget.

        This is the half of the old behaviour that survives ADR 0010, and it is
        the one that matters for safety: whatever paper exposure is outstanding,
        the first real order still sees a clean budget and is never refused for
        a fictional reason.
        """
        path = tmp_path / "record.db"
        writer = db.open_db(path)
        try:
            for index in range(3):
                reserve_order(
                    writer,
                    self._live(count=100, price_tenths=900, coid=f"dry-{index}"),
                    dry_run=True,
                    submitted_ms=index,
                    max_exposure_dollars=1_000.0,
                )
            assert len(_rows(writer)) == 3
            assert current_exposure_dollars(writer, dry_run=False) == pytest.approx(0.0)
        finally:
            writer.close()

    def test_a_dry_run_DOES_consume_the_paper_cap(self, conn, tmp_path):
        """The half ADR 0010 reverses, and the reason it was safe to reverse.

        This test previously asserted the opposite -- that $270 of paper against
        a $1 cap was admitted -- because nothing closed a paper position, so
        counting them would have let exposure ratchet up until the endpoint
        refused everything. A cap that can only close is an off switch, and
        ADR 0008 declined it for that reason.

        `backend/settlement.py` is what changed the argument: paper capital is
        released now. What that buys is the thing worth having -- the cap
        **binds in production**, on paper, before it has ever guarded real
        money. This repo has twice shipped a money guard that could not fire
        and read as defence in depth.
        """
        path = tmp_path / "record.db"
        writer = db.open_db(path)
        try:
            reserve_order(
                writer, self._live(count=100, price_tenths=900, coid="dry-0"),
                dry_run=True, submitted_ms=0, max_exposure_dollars=1_000.0,
            )
            with pytest.raises(ExposureCapExceeded):
                reserve_order(
                    writer,
                    self._live(count=100, price_tenths=900, coid="dry-1"),
                    dry_run=True,
                    submitted_ms=1,
                    max_exposure_dollars=100.0,   # $180 of paper against $100
                )
            # Rolled back entirely, so a refusal leaves nothing behind -- a
            # stranded `pending` row would count as exposure by design.
            assert len(_rows(writer)) == 1
        finally:
            writer.close()
