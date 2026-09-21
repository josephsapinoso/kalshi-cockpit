"""`db-growth-by-table` (#120): MAX(rowid) per large table, not a scan.

The claim under test is narrow and specific: a rowid high-water mark is
strictly better than `COUNT(*)` for "how much was inserted", because deletes
lower a count but never lower a rowid high-water mark (every table this
query reads is `INTEGER PRIMARY KEY AUTOINCREMENT`, which SQLite guarantees
never reuses a rowid even across a table that goes empty). This file seeds a
table, deletes rows out from under it, and checks that claim directly rather
than trusting the docstring that asserts it.

WHAT THIS DOES NOT ESTABLISH
-----------------------------
- Nothing about the live database's contents -- every row here is inserted by
  this file, same convention as `test_inspect_live_db.py`.
- Nothing about `odds_snapshots`, `fair_prices` or `kalshi_quotes` by name --
  those three carry foreign keys and are exercised generically (with no rows)
  by `test_inspect_live_db.py`'s `TestEveryWhitelistedQueryRunsAgainstTheRealSchema`.
  This file seeds `poll_log`, which has none, to isolate the rowid claim from
  foreign-key setup that has nothing to do with it.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scripts.inspect_live_db import CHEAP, QUERIES
from scripts.inspect_live_db_loop import _q_db_growth_by_table

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "backend" / "store" / "schema.sql"


@pytest.fixture
def empty_db(tmp_path) -> Path:
    path = tmp_path / "cockpit.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    return path


class _Args:
    limit = 2000


def _run(db_path: Path) -> dict[str, object]:
    conn = sqlite3.connect(db_path)
    try:
        sections = _q_db_growth_by_table(conn, _Args())
    finally:
        conn.close()
    assert len(sections) == 1
    return {row[0]: row[1] for row in sections[0].rows}


class TestItIsRegisteredCheap:
    def test_the_query_is_classified_cheap(self):
        """Mutation: `cost=WALKS_THE_FILE` on this entry -- red."""
        assert QUERIES["db-growth-by-table"].cost == CHEAP

    def test_the_query_needs_no_accept_flag(self, empty_db, capsys):
        """A CHEAP query runs with no flag; only WALKS_THE_FILE ones need one.

        Mutation: reclassify the entry to WALKS_THE_FILE -- this goes red
        with EXIT_REFUSED_ON_COST (4) instead of 0.
        """
        from scripts.inspect_live_db import main

        rc = main(["db-growth-by-table", "--db", str(empty_db), "--json"])
        capsys.readouterr()
        assert rc == 0


class TestAnEmptyTableReportsNoneNotZero:
    def test_max_rowid_is_none_on_an_empty_table(self, empty_db):
        """Unreadable/absent resolves to None, never 0 (CLAUDE.md convention).

        Mutation: `COALESCE(MAX(rowid), 0)` in the SQL -- red (0 != None).
        """
        result = _run(empty_db)
        assert result["poll_log"] is None
        assert result["odds_snapshots"] is None
        assert result["fair_prices"] is None
        assert result["kalshi_quotes"] is None


class TestRowidSurvivesDeletionAndCountDoesNot:
    """The claim the ticket exists to make: rowid tracks inserts, COUNT does not."""

    def _seed_poll_log(self, db_path: Path, n: int) -> None:
        conn = sqlite3.connect(db_path)
        conn.executemany(
            "INSERT INTO poll_log (polled_ms, endpoint, ok) VALUES (?, 'fills', 1)",
            [(1_000_000 + i,) for i in range(n)],
        )
        conn.commit()
        conn.close()

    def _delete_poll_log(self, db_path: Path, up_to_id: int) -> None:
        conn = sqlite3.connect(db_path)
        conn.execute("DELETE FROM poll_log WHERE id <= ?", (up_to_id,))
        conn.commit()
        conn.close()

    def _count(self, db_path: Path) -> int:
        conn = sqlite3.connect(db_path)
        try:
            return conn.execute("SELECT COUNT(*) FROM poll_log").fetchone()[0]
        finally:
            conn.close()

    def test_deleting_rows_does_not_lower_the_high_water_mark(self, empty_db):
        """Mutation: swap `MAX(rowid)` for `COUNT(*)` in `_SQL_DB_GROWTH_BY_TABLE`
        -- this test goes red, because a count DROPS after the delete below
        while the ticket's claim is that the reading must not.
        """
        self._seed_poll_log(empty_db, 5)
        before = _run(empty_db)
        assert before["poll_log"] == 5

        # Prune the oldest three rows, as the pruner does to kalshi_quotes and
        # fair_prices in production.
        self._delete_poll_log(empty_db, up_to_id=3)
        assert self._count(empty_db) == 2  # a count-based reading UNDERSTATES

        after_delete = _run(empty_db)
        assert after_delete["poll_log"] == 5, (
            "MAX(rowid) must not fall when rows are deleted -- that is "
            "exactly the property that makes it survive pruning"
        )

    def test_the_high_water_mark_keeps_rising_across_a_prune(self, empty_db):
        """The full shape of the ticket's claim: insert, prune most of it away,
        insert more -- the reading must equal total ever inserted, not rows
        currently present, and must exceed what it read before the prune.

        Mutation: swap `MAX(rowid)` for `COUNT(*)` -- this test goes red: a
        table pruned harder than it grew would show COUNT(*) *falling*
        between the two readings, which is precisely "a count understates
        inserts" from the ticket.
        """
        self._seed_poll_log(empty_db, 5)
        first_reading = _run(empty_db)["poll_log"]
        assert first_reading == 5

        self._delete_poll_log(empty_db, up_to_id=4)  # prune all but the newest
        assert self._count(empty_db) == 1

        self._seed_poll_log(empty_db, 2)  # two more inserts (ids 6, 7)
        second_reading = _run(empty_db)["poll_log"]

        assert second_reading == 7
        assert second_reading > first_reading, (
            "rows inserted since the first reading must show as growth even "
            "though the table has fewer rows in it now than it did then"
        )
        # AUTOINCREMENT is why this holds: it is the declaration that stops
        # SQLite handing out id 1 again once the table has gone empty.
        assert self._count(empty_db) == 3
        assert second_reading != self._count(empty_db)
