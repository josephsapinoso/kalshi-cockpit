"""A combination the venue has settled closes its own row on the watcher's
pass; a hand-recorded slip is still Joe's tap (#135, ADR 0181, Joe's (A) to
#131).

Why this file exists
---------------------
Until 2026-09-22 `parlay_positions.status` moved only at Joe's tap
(`close_position`, one production caller, ADR 0136 "Why no auto-close",
ADR 0151 §4). Joe answered #131 with (A): once Kalshi reports the
settlement of a combination he holds, the desk should close the row itself.
The trigger is the venue's settlement of the COMBINATION market -- a
`venue_settlements` row on the position's `combo_ticker` -- not "every leg
resolved" (option (B), offered and not chosen).

What this establishes
----------------------
(i)    An open combination whose `combo_ticker` has a `venue_settlements`
       row is closed by `close_settled_combinations`: `status = 'settled'`,
       `closed_source = 'venue'`, `closed_ms = now_ms`; and `build_payload`
       (what `/api/hedge` serves) no longer lists it.
(ii)   A hand-recorded position (no `combo_ticker`) sitting beside a
       settlement row is untouched by the same pass.
(iii)  A combination whose legs have ALL resolved but whose own market the
       venue has not settled is untouched: the legs are not the trigger.
(iv)   The pass never marks a leg (ADR 0136 reason 2 stands).
(v)    Joe's tap still closes, through the route, and writes
       `closed_source = 'manual'`; `close_position` refuses any other
       provenance and refuses a missing one.
(vi)   The pass runs on the watcher's cycle BEFORE the "anything live"
       gate: a single idle cycle (no pending leg anywhere) still closes.
(vii)  A v53 volume with an already-closed row opens at v54 with the column
       present and NULL on that row -- no backfill.

What this does not establish
-----------------------------
- Anything about the live cadence between the venue settling and the row
  closing (the settlement mirror refreshes every 300 s, the watcher idles
  at 600 s); that is a reading on live, not a test.
- That any screen renders a closed row -- nothing does, by design; the ADR
  records it as a consequence.
- Which leg lost. The combination's `market_result` does not say.
"""

from __future__ import annotations

import inspect

import pytest

from backend import hedge, hedge_watch
from backend.api.routes import create_app
from backend.config import AppConfig
from backend.notify.alerts import Alerter
from backend.store import db

NOW_MS = 1_700_000_000_000
LATER_MS = NOW_MS + 60_000
MAX_AGE_MS = 30_000

CIN = "KXMLBGAME-26AUG26CINSF-CIN"
LAD = "KXMLBGAME-26AUG26LADSD-LAD"
COMBO = "KXMVECROSSCATEGORY-CLOSESTEST-EE"
OTHER_COMBO = "KXMVECROSSCATEGORY-CLOSESTEST-FF"


@pytest.fixture()
def conn(tmp_path):
    connection = db.init_db(tmp_path / "cockpit.db")
    yield connection
    connection.close()


def seed_position(conn, *, combo_ticker, commence_ms=None) -> int:
    legs = [
        {"ticker": CIN, "side": "yes", "label": "Cincinnati"},
        {"ticker": LAD, "side": "yes", "label": "Los Angeles"},
    ]
    if commence_ms is not None:
        for leg in legs:
            leg["commence_ms"] = commence_ms
    return hedge.record_position(
        conn,
        now_ms=NOW_MS,
        source="kalshi_combo",
        label="two legs",
        stake_tenths=1_020,
        return_tenths=10_000,
        legs=legs,
        combo_ticker=combo_ticker,
        placed_ms=NOW_MS,
    )


def settle_at_venue(conn, ticker, *, market_result="no", settled_ms=NOW_MS):
    conn.execute(
        "INSERT INTO venue_settlements (ticker, market_result, settled_ms, "
        "side, contracts) VALUES (?, ?, ?, 'yes', 17.74)",
        (ticker, market_result, settled_ms),
    )
    conn.commit()


def resolve_every_leg(conn, position_id, *, outcome="lost"):
    leg_ids = [
        int(row[0])
        for row in conn.execute(
            "SELECT id FROM parlay_position_legs WHERE position_id = ?",
            (position_id,),
        )
    ]
    for leg_id in leg_ids:
        assert hedge.resolve_leg(
            conn, leg_id=leg_id, outcome=outcome, now_ms=NOW_MS, source="manual"
        )


def row(conn, position_id):
    return conn.execute(
        "SELECT status, closed_ms, closed_source FROM parlay_positions "
        "WHERE id = ?",
        (position_id,),
    ).fetchone()


def leg_outcomes(conn, position_id):
    return [
        r[0]
        for r in conn.execute(
            "SELECT outcome FROM parlay_position_legs WHERE position_id = ? "
            "ORDER BY leg_index",
            (position_id,),
        )
    ]


async def raising_fetch(ticker, *, observed_ms):
    raise RuntimeError("no venue leg quote needed for this assertion")


class TestAVenueSettledCombinationClosesItsOwnRow:
    def test_the_settlement_row_closes_it_with_venue_provenance(self, conn):
        """(i)"""
        position_id = seed_position(conn, combo_ticker=COMBO)
        settle_at_venue(conn, COMBO)

        closed = hedge.close_settled_combinations(conn, now_ms=LATER_MS)

        assert closed == [position_id]
        got = row(conn, position_id)
        assert got["status"] == "settled"
        assert got["closed_source"] == "venue"
        assert got["closed_ms"] == LATER_MS

    def test_the_pass_is_idempotent(self, conn):
        position_id = seed_position(conn, combo_ticker=COMBO)
        settle_at_venue(conn, COMBO)
        assert hedge.close_settled_combinations(conn, now_ms=LATER_MS) == [
            position_id
        ]
        assert hedge.close_settled_combinations(conn, now_ms=LATER_MS + 1) == []
        assert row(conn, position_id)["closed_ms"] == LATER_MS

    async def test_the_closed_row_leaves_the_hedge_payload(self, conn):
        """(i), the served half: `/api/hedge` reads `open_positions`."""
        position_id = seed_position(conn, combo_ticker=COMBO)
        settle_at_venue(conn, COMBO)
        before = await hedge.build_payload(
            conn,
            now_ms=NOW_MS,
            max_quote_age_ms=MAX_AGE_MS,
            spendable_tenths=None,
            fetch_quote=raising_fetch,
        )
        assert [p["id"] for p in before["positions"]] == [position_id]

        hedge.close_settled_combinations(conn, now_ms=LATER_MS)

        after = await hedge.build_payload(
            conn,
            now_ms=LATER_MS,
            max_quote_age_ms=MAX_AGE_MS,
            spendable_tenths=None,
            fetch_quote=raising_fetch,
        )
        assert after["positions"] == []

    def test_only_the_settled_combination_closes_not_its_neighbour(self, conn):
        settled = seed_position(conn, combo_ticker=COMBO)
        still_open = seed_position(conn, combo_ticker=OTHER_COMBO)
        settle_at_venue(conn, COMBO)

        assert hedge.close_settled_combinations(conn, now_ms=LATER_MS) == [
            settled
        ]
        assert row(conn, still_open)["status"] == "open"
        assert row(conn, still_open)["closed_source"] is None


class TestWhatThePassLeavesAlone:
    def test_a_hand_recorded_slip_is_untouched(self, conn):
        """(ii): no `combo_ticker`, so the venue cannot see it and the join
        cannot reach it -- even with a settlement row sitting in the table."""
        position_id = seed_position(conn, combo_ticker=None)
        settle_at_venue(conn, COMBO)

        assert hedge.close_settled_combinations(conn, now_ms=LATER_MS) == []
        got = row(conn, position_id)
        assert got["status"] == "open"
        assert got["closed_ms"] is None
        assert got["closed_source"] is None

    def test_every_leg_resolved_is_not_the_trigger(self, conn):
        """(iii): option (B) was offered and not chosen."""
        position_id = seed_position(conn, combo_ticker=COMBO)
        resolve_every_leg(conn, position_id)
        assert leg_outcomes(conn, position_id) == ["lost", "lost"]

        assert hedge.close_settled_combinations(conn, now_ms=LATER_MS) == []
        assert row(conn, position_id)["status"] == "open"

    def test_the_pass_marks_no_leg(self, conn):
        """(iv): the combination's result says nothing about which leg lost."""
        position_id = seed_position(conn, combo_ticker=COMBO)
        settle_at_venue(conn, COMBO, market_result="no")

        hedge.close_settled_combinations(conn, now_ms=LATER_MS)

        assert leg_outcomes(conn, position_id) == ["pending", "pending"]


class TestJoesTapStillCloses:
    async def test_the_route_writes_manual_provenance(self, tmp_path):
        """(v)"""
        import httpx

        path = tmp_path / "cockpit.db"
        conn = db.init_db(path)
        position_id = seed_position(conn, combo_ticker=COMBO)
        conn.close()
        app = create_app(
            AppConfig(db_path=path, instance_mode="live", auth_token="secret-token")
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            answered = await c.post(
                f"/api/hedge/positions/{position_id}/close",
                json={"status": "closed"},
                headers={"Authorization": "Bearer secret-token"},
            )
        assert answered.status_code == 200

        reopened = db.connect(path)
        try:
            got = row(reopened, position_id)
        finally:
            reopened.close()
        assert got["status"] == "closed"
        assert got["closed_source"] == "manual"

    def test_close_position_refuses_an_unknown_provenance(self, conn):
        position_id = seed_position(conn, combo_ticker=COMBO)
        with pytest.raises(ValueError):
            hedge.close_position(
                conn,
                position_id=position_id,
                now_ms=NOW_MS,
                status="settled",
                source="joe",
            )
        assert row(conn, position_id)["status"] == "open"

    def test_close_position_refuses_a_missing_provenance(self, conn):
        """A missing `source` is a `TypeError` at the call site, never a
        silent NULL -- NULL means 'closed before the column existed'."""
        position_id = seed_position(conn, combo_ticker=COMBO)
        with pytest.raises(TypeError):
            hedge.close_position(  # type: ignore[call-arg]
                conn, position_id=position_id, now_ms=NOW_MS, status="settled"
            )
        assert row(conn, position_id)["status"] == "open"


class TestThePassRunsBeforeTheLiveGate:
    async def test_an_idle_cycle_still_closes(self, tmp_path):
        """(vi): no pending leg anywhere, so `anything_in_progress` is False
        and `watch_once` never runs -- and the row closes anyway."""
        path = tmp_path / "cockpit.db"
        conn = db.init_db(path)
        position_id = seed_position(conn, combo_ticker=COMBO)
        resolve_every_leg(conn, position_id)
        settle_at_venue(conn, COMBO)
        assert hedge_watch.anything_in_progress(conn, now_ms=LATER_MS) is False
        conn.close()

        slept: list[float] = []

        async def sleep(seconds):
            slept.append(seconds)

        class Notifier:
            enabled = True

            async def hedge_lock(self, position, *, notes):
                return True

            async def position_state(self, position, *, notes, as_of_ms):
                return True

        await hedge_watch.watch_hedges_forever(
            path,
            lambda c: Alerter(c, Notifier()),
            fetch_quote=raising_fetch,
            max_quote_age_ms=MAX_AGE_MS,
            sleep=sleep,
            clock=lambda: LATER_MS / 1000,
            max_cycles=1,
        )

        assert slept == [hedge_watch.IDLE_INTERVAL_S]
        reopened = db.connect(path)
        try:
            got = row(reopened, position_id)
        finally:
            reopened.close()
        assert got["status"] == "settled"
        assert got["closed_source"] == "venue"
        assert got["closed_ms"] == LATER_MS

    async def test_a_failed_close_pass_does_not_silence_the_watcher(
        self, tmp_path, monkeypatch
    ):
        """`busy` is decided AFTER the close pass. If the pass shared the
        cycle's exception handler, a raise there would skip `watch_once`
        (no settle, no re-price, no push) and force the 600 s idle sleep
        while a game is live -- found by the runtime review before merge.
        The pass has its own handler: a live ticket still gets its 60 s
        cycle when the pass raises."""
        path = tmp_path / "cockpit.db"
        conn = db.init_db(path)
        seed_position(conn, combo_ticker=COMBO, commence_ms=LATER_MS - 1)
        assert hedge_watch.anything_in_progress(conn, now_ms=LATER_MS) is True
        conn.close()

        def exploding(conn, *, now_ms):
            raise RuntimeError("database is locked")

        monkeypatch.setattr(hedge, "close_settled_combinations", exploding)

        slept: list[float] = []

        async def sleep(seconds):
            slept.append(seconds)

        class Notifier:
            enabled = True

            async def hedge_lock(self, position, *, notes):
                return True

            async def position_state(self, position, *, notes, as_of_ms):
                return True

        await hedge_watch.watch_hedges_forever(
            path,
            lambda c: Alerter(c, Notifier()),
            fetch_quote=raising_fetch,
            max_quote_age_ms=MAX_AGE_MS,
            sleep=sleep,
            clock=lambda: LATER_MS / 1000,
            max_cycles=1,
        )

        assert slept == [hedge_watch.WATCH_INTERVAL_S]

    def test_the_call_precedes_the_gate_in_source(self):
        """Pins the placement decision at the text level too, so a refactor
        that moves the pass inside the gate is a visible diff here as well
        as a red run above."""
        body = inspect.getsource(hedge_watch.watch_hedges_forever)
        assert body.index("close_settled_combinations(") < body.index(
            "anything_in_progress("
        )


class TestTheColumnArrivesByMigration:
    def test_a_v53_volume_gains_the_column_with_null_on_old_closed_rows(
        self, tmp_path
    ):
        """(vii): keyed on the column, never the version number
        (`tests/test_hedge_positions.py`'s pattern). A row closed before the
        column existed reads NULL -- "not recorded" -- not `'manual'`."""
        owning = [
            v
            for v, step in db._MIGRATIONS.items()
            if ("parlay_positions", "closed_source")
            in {(t, c) for t, c, _ in step.columns}
        ]
        assert len(owning) == 1, owning
        assert owning[0] <= db.SCHEMA_VERSION

        path = tmp_path / "pre.db"
        connection = db.init_db(path)
        position_id = seed_position(connection, combo_ticker=COMBO)
        connection.execute("ALTER TABLE parlay_positions DROP COLUMN closed_source")
        connection.execute(
            "UPDATE parlay_positions SET status = 'settled', closed_ms = ? "
            "WHERE id = ?",
            (NOW_MS, position_id),
        )
        db._set_meta(connection, "schema_version", str(owning[0] - 1))
        connection.commit()
        connection.close()

        reopened = db.init_db(path)
        try:
            columns = {
                r[1] for r in reopened.execute("PRAGMA table_info(parlay_positions)")
            }
            assert "closed_source" in columns
            assert db.get_meta(reopened, "schema_version") == str(db.SCHEMA_VERSION)
            got = row(reopened, position_id)
            assert got["status"] == "settled"
            assert got["closed_source"] is None
        finally:
            reopened.close()
