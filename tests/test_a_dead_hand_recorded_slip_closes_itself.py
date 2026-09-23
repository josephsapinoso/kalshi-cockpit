"""A hand-recorded slip with a lost leg is closed by the desk (#143, Joe's (A)
to #142, amending ADR 0181).

Why this file exists
---------------------
A parlay with a lost leg cannot win (`assess` calls it `STATE_DEAD`), and a
slip typed in by hand has no venue settlement that would ever close it, so
before #143 it sat on `/hedge` until Joe tapped it. He answered #142 with
(A): the desk closes it, recorded as lost, distinguishable from his tap.

What this establishes
----------------------
(i)    An open hand-recorded slip (no `combo_ticker`) with a lost leg is
       closed by `close_dead_hand_recorded`: `status = 'settled'`,
       `closed_reason = 'lost_leg'`, `closed_source` = who resolved the leg.
(ii)   An order-linked combination with a lost leg is untouched: it still
       waits for the venue's settlement.
(iii)  A void leg closes nothing, and a slip with every leg pending or won
       is untouched.
(iv)   Joe's tap leaves `closed_reason` NULL, so the two stay apart.
(v)    The watcher's cycle calls the pass.
(vi)   A v54 volume gains the column with NULL on its already-closed rows.

What this does not establish
-----------------------------
- How soon after a leg resolves the row closes on live (the watcher's
  cadence); that is a reading, not a test.
"""

from __future__ import annotations

import inspect

import pytest

from backend import hedge, hedge_watch
from backend.store import db

NOW_MS = 1_700_000_000_000
LATER_MS = NOW_MS + 60_000

CIN = "KXMLBGAME-26AUG26CINSF-CIN"
LAD = "KXMLBGAME-26AUG26LADSD-LAD"
COMBO = "KXMVECROSSCATEGORY-DEADSLIP-EE"


@pytest.fixture()
def conn(tmp_path):
    connection = db.init_db(tmp_path / "cockpit.db")
    yield connection
    connection.close()


def seed(conn, *, combo_ticker=None) -> int:
    return hedge.record_position(
        conn,
        now_ms=NOW_MS,
        source="kalshi_combo" if combo_ticker else "sportsbook",
        label="two legs",
        stake_tenths=1_020,
        return_tenths=10_000,
        legs=[
            {"ticker": CIN, "side": "yes", "label": "Cincinnati"},
            {"ticker": LAD, "side": "yes", "label": "Los Angeles"},
        ],
        combo_ticker=combo_ticker,
        placed_ms=NOW_MS if combo_ticker else None,
    )


def resolve_first_leg(conn, position_id, *, outcome, source="manual"):
    leg_id = conn.execute(
        "SELECT id FROM parlay_position_legs WHERE position_id = ? "
        "ORDER BY leg_index LIMIT 1",
        (position_id,),
    ).fetchone()[0]
    assert hedge.resolve_leg(
        conn, leg_id=leg_id, outcome=outcome, now_ms=NOW_MS, source=source
    )


def row(conn, position_id):
    return conn.execute(
        "SELECT status, closed_ms, closed_source, closed_reason "
        "FROM parlay_positions WHERE id = ?",
        (position_id,),
    ).fetchone()


class TestADeadHandRecordedSlipClosesItself:
    def test_a_hand_recorded_slip_with_a_lost_leg_is_closed_by_the_desk(self, conn):
        position_id = seed(conn)
        resolve_first_leg(conn, position_id, outcome="lost", source="venue")

        assert hedge.close_dead_hand_recorded(conn, now_ms=LATER_MS) == [position_id]
        got = row(conn, position_id)
        assert got["status"] == "settled"
        assert got["closed_ms"] == LATER_MS
        assert got["closed_reason"] == "lost_leg"
        assert got["closed_source"] == "venue"

    def test_a_leg_he_marked_lost_names_him_as_the_source(self, conn):
        position_id = seed(conn)
        resolve_first_leg(conn, position_id, outcome="lost", source="manual")

        hedge.close_dead_hand_recorded(conn, now_ms=LATER_MS)
        got = row(conn, position_id)
        assert got["closed_source"] == "manual"
        assert got["closed_reason"] == "lost_leg"

    def test_the_pass_is_idempotent(self, conn):
        position_id = seed(conn)
        resolve_first_leg(conn, position_id, outcome="lost")
        assert hedge.close_dead_hand_recorded(conn, now_ms=LATER_MS) == [position_id]
        assert hedge.close_dead_hand_recorded(conn, now_ms=LATER_MS + 1) == []
        assert row(conn, position_id)["closed_ms"] == LATER_MS

    def test_an_order_linked_combination_with_a_lost_leg_waits_for_the_venue(
        self, conn
    ):
        position_id = seed(conn, combo_ticker=COMBO)
        resolve_first_leg(conn, position_id, outcome="lost", source="venue")

        assert hedge.close_dead_hand_recorded(conn, now_ms=LATER_MS) == []
        assert row(conn, position_id)["status"] == "open"

    def test_a_void_leg_closes_nothing(self, conn):
        position_id = seed(conn)
        resolve_first_leg(conn, position_id, outcome="void")

        assert hedge.close_dead_hand_recorded(conn, now_ms=LATER_MS) == []
        assert row(conn, position_id)["status"] == "open"

    def test_a_won_leg_closes_nothing(self, conn):
        position_id = seed(conn)
        resolve_first_leg(conn, position_id, outcome="won")

        assert hedge.close_dead_hand_recorded(conn, now_ms=LATER_MS) == []
        assert row(conn, position_id)["status"] == "open"

    def test_his_tap_leaves_the_reason_null(self, conn):
        position_id = seed(conn)
        assert hedge.close_position(
            conn,
            position_id=position_id,
            now_ms=LATER_MS,
            status="closed",
            source="manual",
        )
        got = row(conn, position_id)
        assert got["closed_source"] == "manual"
        assert got["closed_reason"] is None

    def test_close_position_refuses_an_unknown_reason(self, conn):
        position_id = seed(conn)
        with pytest.raises(ValueError):
            hedge.close_position(
                conn,
                position_id=position_id,
                now_ms=LATER_MS,
                status="settled",
                source="manual",
                reason="bored",
            )
        assert row(conn, position_id)["status"] == "open"

    def test_the_watcher_calls_the_pass(self):
        body = inspect.getsource(hedge_watch.watch_hedges_forever)
        assert "close_dead_hand_recorded(" in body
        assert body.index("close_dead_hand_recorded(") < body.index(
            "anything_in_progress("
        )


class TestTheReasonColumnArrivesByMigration:
    def test_a_v54_volume_gains_the_column_with_null_on_old_closed_rows(
        self, tmp_path
    ):
        owning = [
            v
            for v, step in db._MIGRATIONS.items()
            if ("parlay_positions", "closed_reason")
            in {(t, c) for t, c, _ in step.columns}
        ]
        assert len(owning) == 1, owning
        assert owning[0] <= db.SCHEMA_VERSION

        path = tmp_path / "pre.db"
        connection = db.init_db(path)
        position_id = seed(connection)
        assert hedge.close_position(
            connection,
            position_id=position_id,
            now_ms=NOW_MS,
            status="closed",
            source="manual",
        )
        connection.execute("ALTER TABLE parlay_positions DROP COLUMN closed_reason")
        db._set_meta(connection, "schema_version", str(owning[0] - 1))
        connection.commit()
        connection.close()

        reopened = db.init_db(path)
        try:
            columns = {
                r[1] for r in reopened.execute("PRAGMA table_info(parlay_positions)")
            }
            assert "closed_reason" in columns
            assert db.get_meta(reopened, "schema_version") == str(db.SCHEMA_VERSION)
            got = row(reopened, position_id)
            assert got["status"] == "closed"
            assert got["closed_source"] == "manual"
            assert got["closed_reason"] is None
        finally:
            reopened.close()
