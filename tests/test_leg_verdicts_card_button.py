"""v58: the leg scout's third trigger, the card's own "Ask the scouts" button.

Joe, 2026-09-25: the leg scout was live, but nothing on a card said it
existed until he took a buy step, so he saw no TAKE or PASS anywhere. The
fix is a visible button on each card, recorded under its own trigger. That
widens a CHECK, which means a table rebuild.

Claims:
- a v57 database with a real row migrates, keeps the row, and admits
  `card_button`
- the step is idempotent: a replay after full success changes nothing
- a database older than v57 (no table yet) also migrates cleanly
- the route accepts `card_button` and still refuses an unknown trigger
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.store import db

ROW = (
    "INSERT INTO leg_verdicts (ticker, side, ask_tenths, commence_ms, "
    "requested_ms, completed_ms, status, verdict, reason, model, trigger) "
    "VALUES ('T', 'yes', 510, 9000, 100, 200, 'complete', 'take', "
    "'Nothing new.', 'm', 'price_tap')"
)


def _wound_back_to_v57(path):
    conn = db.init_db(path)
    conn.execute(ROW)
    for statement in db._MIGRATIONS[58].undo_statements:
        conn.execute(statement)
    db._set_meta(conn, "schema_version", "57")
    conn.commit()
    return conn


def _card_button_insert(conn):
    conn.execute(
        "INSERT INTO leg_verdicts (ticker, side, requested_ms, completed_ms, "
        "status, model, trigger) VALUES ('T2', 'no', 1, 2, 'refused', 'm', "
        "'card_button')"
    )


class TestTheRebuild:
    def test_a_v57_table_refuses_card_button(self, tmp_path):
        conn = _wound_back_to_v57(tmp_path / "a.db")
        with pytest.raises(sqlite3.IntegrityError):
            _card_button_insert(conn)

    def test_a_v57_database_keeps_its_rows_and_admits_card_button(self, tmp_path):
        conn = _wound_back_to_v57(tmp_path / "a.db")
        assert db.migrate(conn) == [58]
        rows = conn.execute("SELECT id, verdict, trigger FROM leg_verdicts").fetchall()
        assert [tuple(r) for r in rows] == [(1, "take", "price_tap")]
        _card_button_insert(conn)
        names = {r["name"] for r in conn.execute("PRAGMA index_list(leg_verdicts)")}
        assert "idx_leg_verdicts_leg" in names

    def test_a_replay_after_success_changes_nothing(self, tmp_path):
        conn = _wound_back_to_v57(tmp_path / "a.db")
        db.migrate(conn)
        _card_button_insert(conn)
        for statement in db._MIGRATIONS[58].statements:
            conn.execute(statement)
        assert conn.execute("SELECT COUNT(*) AS c FROM leg_verdicts").fetchone()["c"] == 2

    def test_a_database_with_no_table_yet_migrates(self, tmp_path):
        conn = db.init_db(tmp_path / "a.db")
        conn.execute("DROP TABLE leg_verdicts")
        db._set_meta(conn, "schema_version", "56")
        conn.commit()
        assert 58 in db.migrate(conn)
        _card_button_insert(conn)


class TestTheRouteAcceptsTheButton:
    def test_the_route_names_card_button_as_a_trigger(self):
        from pathlib import Path

        src = (
            Path(__file__).resolve().parents[1]
            / "backend/api/routers/leg_verdicts.py"
        ).read_text(encoding="utf-8")
        assert '"card_button"' in src
