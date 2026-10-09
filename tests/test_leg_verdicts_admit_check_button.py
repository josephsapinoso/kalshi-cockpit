"""Schema v66: `leg_verdicts.trigger` admits `'check_button'` (#325), and the
CHECK was the only thing refusing it.

What this establishes: a fresh database and a migrated one both take the
row; the v65 shape (wound back through the step's own undo) refuses it, so
the constraint is the guard and the migration is what moved it.
What it does not establish: that the route writes the trigger (the lane's
own tests pin that) or that the seat behaves any differently for it (it
does not, by the registration's Amendment 1).
"""
from __future__ import annotations

import sqlite3

import pytest

from backend.store import db

ROW = dict(
    ticker="KXNFLGAME-26OCT12DETGB-DET",
    side="yes",
    ask_tenths=620,
    commence_ms=2_000_000_000_000,
    requested_ms=1_999_000_000_000,
    model="test-model",
)


def _insert(conn: sqlite3.Connection, trigger: str) -> None:
    conn.execute(
        "INSERT INTO leg_verdicts (ticker, side, ask_tenths, commence_ms, "
        "requested_ms, status, model, trigger) VALUES (?, ?, ?, ?, ?, 'running', ?, ?)",
        (*ROW.values(), trigger),
    )


class TestTheFourthTriggerIsAdmitted:
    def test_a_fresh_database_takes_a_check_button_row(self, tmp_path):
        conn = db.init_db(tmp_path / "fresh.db")
        try:
            _insert(conn, "check_button")
            assert conn.execute(
                "SELECT trigger FROM leg_verdicts"
            ).fetchone()[0] == "check_button"
        finally:
            conn.close()

    def test_the_v65_shape_refused_it_and_v66_moved_the_guard(self, tmp_path):
        conn = db.init_db(tmp_path / "wound.db")
        try:
            # Wind the table back through the step's own undo: the v58..v65
            # shape, which `_leg_verdicts_create(card_button=True)` builds.
            for statement in db._LEG_VERDICTS_ADMIT_CHECK_BUTTON_UNDO:
                conn.execute(statement)
            with pytest.raises(sqlite3.IntegrityError):
                _insert(conn, "check_button")
            # The three older triggers still pass on the old shape.
            _insert(conn, "card_button")
            # Replaying the v66 statements admits the new one again, and keeps
            # the row copied across.
            for statement in db._LEG_VERDICTS_ADMIT_CHECK_BUTTON:
                conn.execute(statement)
            _insert(conn, "check_button")
            triggers = sorted(
                r[0] for r in conn.execute("SELECT trigger FROM leg_verdicts")
            )
            assert triggers == ["card_button", "check_button"]
        finally:
            conn.close()

    def test_the_step_is_registered_at_v66_with_its_index(self):
        step = db._MIGRATIONS[66]
        assert step.statements == db._LEG_VERDICTS_ADMIT_CHECK_BUTTON
        assert step.indexes == ("idx_leg_verdicts_leg",)
        assert db.SCHEMA_VERSION >= 66
