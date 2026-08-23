"""`scripts/list_unmatched.py` reads the queue without being able to touch it.

The `unmatched_items` queue had a writer (`backend/match/linker.py`) and no
reader anywhere in the repo -- the fifth built-but-never-called instance. These
tests pin the reader that closes that gap: the output carries the columns an
alias entry needs, the connection is physically read-only, and an empty queue
says so in words rather than printing nothing.

Seeded through `db.init_db` and `record_unmatched` deliberately -- the real
schema and the real writer -- so a schema or writer change that breaks the
reader breaks these tests rather than a hand-mocked copy of the table.

What these tests do NOT establish
---------------------------------
- **Not that the deployed database is readable by this script.** They run
  against a temp db at the current schema; a live db at an older version
  refuses (by design), and only running the script against it proves which.
- **Not that the listed items are actionable.** The reader shows the queue;
  whether an alias entry actually resolves an item is the linker's business.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.match.linker import record_unmatched
from backend.store import db
from scripts.list_unmatched import connect_readonly, main

NOW = 1_787_000_000_000  # 2026-08-17T20:53:20Z
_MS_PER_DAY = 24 * 60 * 60 * 1000


@pytest.fixture()
def db_path(tmp_path):
    """A real database at the current schema, not a hand-built subset."""
    path = tmp_path / "cockpit.db"
    conn = db.init_db(path)
    conn.close()
    return path


def seed(path, *, ms=NOW, side="kalshi", identifier="KXNCAAFGAME-26AUG30ILSTOSU",
         league="NCAAF", detail="Illinois State vs Ohio State",
         reason="no_counterpart", times=1):
    conn = db.connect(path)
    try:
        for i in range(times):
            record_unmatched(
                conn, observed_ms=ms + i * 15_000, side=side,
                identifier=identifier, league=league, detail=detail,
                reason=reason,
            )
    finally:
        conn.close()


class TestOutputCarriesTheWorkItem:
    def test_the_columns_an_alias_entry_needs_are_all_present(
        self, db_path, capsys
    ):
        seed(db_path)

        assert main(["--db", str(db_path)]) == 0
        out = capsys.readouterr().out
        for needed in (
            "kalshi",                          # side
            "NCAAF",                           # league
            "KXNCAAFGAME-26AUG30ILSTOSU",      # identifier
            "Illinois State vs Ohio State",    # detail: the names as seen
            "no_counterpart",                  # reason
            "seen_count", "first_seen", "last_seen",
        ):
            assert needed in out

    def test_repeat_sightings_are_one_line_carrying_their_count(
        self, db_path, capsys
    ):
        seed(db_path, times=7)

        main(["--db", str(db_path)])
        out = capsys.readouterr().out
        item_lines = [
            line for line in out.splitlines()
            if "KXNCAAFGAME-26AUG30ILSTOSU" in line
        ]
        assert len(item_lines) == 1
        assert "7" in item_lines[0]
        assert "1 unmatched items" in out

    def test_first_and_last_seen_render_as_dates_not_epoch_ms(
        self, db_path, capsys
    ):
        seed(db_path, ms=NOW)
        seed(db_path, ms=NOW + 9 * _MS_PER_DAY)

        main(["--db", str(db_path)])
        out = capsys.readouterr().out
        assert "2026-08-17" in out    # first seen
        assert "2026-08-26" in out    # last seen
        assert str(NOW) not in out

    def test_a_null_league_and_detail_render_without_crashing(
        self, db_path, capsys
    ):
        seed(db_path, league=None, detail=None)

        assert main(["--db", str(db_path)]) == 0
        assert "KXNCAAFGAME-26AUG30ILSTOSU" in capsys.readouterr().out


class TestTheInstrumentCannotWrite:
    def test_a_write_on_the_scripts_connection_is_refused_by_sqlite(
        self, db_path
    ):
        """The pin on read-only, enforced below Python.

        Verified by mutation: with `connect_readonly` switched to a plain
        `sqlite3.connect`, the INSERT succeeds and this test fails.
        """
        conn = connect_readonly(str(db_path))
        try:
            with pytest.raises(
                sqlite3.OperationalError, match="readonly database"
            ):
                conn.execute(
                    "INSERT INTO unmatched_items (first_seen_ms, last_seen_ms,"
                    " side, identifier, reason) VALUES (1, 1, 'kalshi', 'X',"
                    " 'r')"
                )
        finally:
            conn.close()

    def test_running_the_script_leaves_the_queue_row_count_unchanged(
        self, db_path, capsys
    ):
        seed(db_path, times=3)

        main(["--db", str(db_path)])
        capsys.readouterr()

        conn = db.connect(db_path)
        try:
            count = conn.execute(
                "SELECT COUNT(*), MAX(seen_count) FROM unmatched_items"
            ).fetchone()
        finally:
            conn.close()
        assert tuple(count) == (1, 3)


class TestEmptyIsSaidNotShown:
    def test_an_empty_queue_prints_zero_unmatched_items_in_words(
        self, db_path, capsys
    ):
        assert main(["--db", str(db_path)]) == 0
        assert "0 unmatched items" in capsys.readouterr().out

    def test_a_missing_database_refuses_instead_of_reporting_zero(
        self, tmp_path, capsys
    ):
        """Unreadable must never print the same thing as empty."""
        missing = tmp_path / "nowhere.db"

        assert main(["--db", str(missing)]) == 2
        captured = capsys.readouterr()
        assert "unmatched items" not in captured.out
        assert "cannot read" in captured.err
