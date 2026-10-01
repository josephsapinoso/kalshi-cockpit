"""v59: `game_script_cards`, one automatic game-script parlay card per game.

Joe's (A) to #212, 2026-09-29 (ADR 0190): a card is built for every game in
his sports as it comes within a day of kickoff. This file pins the table the
seat writes into (#215), not the seat.

Claims:
- a v58 database gains the table on open, with nothing else changed
- status is one of four values, and a built card carries its story and legs
- a skip or a refusal names its reason
- the table has no price, probability, confidence or edge column (ADR 0189,
  0038): the model never sees a price, and a card claims no edge

What this does not establish: that anything writes a row. The seat is #215.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.store import db

INSERT = (
    "INSERT INTO game_script_cards (game_event_ticker, sport_key, kickoff_ms, "
    "built_ms, status, story, legs_json, reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
)


def _fresh(tmp_path):
    return db.init_db(tmp_path / "a.db")


class TestTheMigration:
    def test_a_v58_database_gains_the_table(self, tmp_path):
        conn = _fresh(tmp_path)
        conn.execute("DROP TABLE game_script_cards")
        db._set_meta(conn, "schema_version", "58")
        conn.commit()
        conn.close()

        conn = db.init_db(tmp_path / "a.db")
        assert db.get_meta(conn, "schema_version") == str(db.SCHEMA_VERSION)
        names = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE tbl_name = 'game_script_cards'"
            )
        }
        assert names == {
            "game_script_cards",
            "idx_game_script_cards_kickoff",
            "idx_game_script_cards_game",
        }


class TestTheRowRules:
    def test_a_built_card_is_accepted(self, tmp_path):
        conn = _fresh(tmp_path)
        conn.execute(
            INSERT, ("KXNFLGAME-X", "americanfootball_nfl", 9, 1, "built", "s", "[]", None)
        )

    def test_an_unknown_status_is_refused(self, tmp_path):
        conn = _fresh(tmp_path)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                INSERT, ("KXNFLGAME-X", "americanfootball_nfl", 9, 1, "maybe", "s", "[]", "r")
            )

    def test_a_built_card_without_legs_is_refused(self, tmp_path):
        conn = _fresh(tmp_path)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                INSERT, ("KXNFLGAME-X", "americanfootball_nfl", 9, 1, "built", "s", None, None)
            )

    @pytest.mark.parametrize("status", ["skipped", "refused_budget", "refused_invalid"])
    def test_a_skip_or_refusal_without_a_reason_is_refused(self, tmp_path, status):
        conn = _fresh(tmp_path)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                INSERT, ("KXNFLGAME-X", "americanfootball_nfl", 9, 1, status, None, None, None)
            )
        conn.execute(
            INSERT, ("KXNFLGAME-X", "americanfootball_nfl", 9, 1, status, None, None, "why")
        )


class TestNoPriceColumn:
    def test_the_table_carries_no_price_or_edge_column(self, tmp_path):
        conn = _fresh(tmp_path)
        columns = {r[1] for r in conn.execute("PRAGMA table_info(game_script_cards)")}
        forbidden = ("price", "tenths", "prob", "confidence", "edge", "ask", "bp")
        assert not [c for c in columns if any(f in c for f in forbidden)], columns
