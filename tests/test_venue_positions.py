"""The venue's open positions are mirrored, not counted and discarded.

Until schema v33 `portfolio_poll.poll_positions` fetched every open position
from `/portfolio/positions`, wrote `len(rows)` into `poll_log.row_count`, and
threw the rows away. The desk could say "Open now: 3 positions" and could not
say what those three had cost: `bets.open_positions` served an unconditional
refusal where the money figure belonged (ADR 0101 section 2.3, its third
reason -- "the venue's own per-position figure is not stored").

The per-row shape was captured on the production account on 2026-08-30
(`tests/test_rest.py::OBSERVED_POSITION_ROW`: real field names and types,
synthetic values), which is the ordering rule from `tasks/lessons.md`
satisfied. Every wire-shape test below builds on that row and never on a
hand-invented one.

What this establishes
---------------------
That the table exists on a fresh database and lands on a volume one version
behind without a migration step; that the venue's strings are stored verbatim
and the derived columns are NULL -- never 0 -- when a value will not parse;
that a successful poll writes its full row set under the poll's own stamp and
the count in `poll_log.row_count` is untouched; that the writer bounds its own
table; that `bets.open_positions` serves the count and the staked figure from
ONE read with ONE stamp, refuses on a stale poll with the clock kept, refuses
rather than partially sums when a row is unreadable, and serves an
empty-but-fresh snapshot as count 0 and $0.00; that `gate.py` cannot see the
table; and that the capture script no longer overwrites an observation.

What it does NOT establish
--------------------------
Whether `market_exposure_dollars` includes fees; anything about
`event_positions`; how the venue's `count_filter` treats a row that flips to
zero mid-session; that the screen renders the figure (lane A2). And nothing
here reads the live database: every row is synthetic in the observed shape.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.store import db

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "positions.db")
    yield c
    c.close()


def _poll(conn, *, polled_ms: int, row_count=0, ok: bool = True) -> int:
    """A `poll_log` row for the positions endpoint; returns its id."""
    cursor = conn.execute(
        "INSERT INTO poll_log (polled_ms, endpoint, ok, row_count) "
        "VALUES (?, 'positions', ?, ?)",
        (polled_ms, 1 if ok else 0, row_count),
    )
    conn.commit()
    return int(cursor.lastrowid)


class TestTheSchemaCarriesTheMirror:
    def test_a_fresh_database_has_the_table(self, conn):
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert "venue_positions" in names

    def test_the_previous_version_gains_it_without_a_migration_step(
        self, tmp_path
    ):
        """v33 is tableless: `init_db` applies `schema.sql` with `CREATE TABLE
        IF NOT EXISTS` on every open, so the live volume gains the table on
        its next boot and no `_MIGRATIONS` entry exists to get wrong. The
        version is read from `SCHEMA_VERSION` rather than typed, for the
        reason `test_hedge_positions` records: a hand-written number starts
        asserting about a version two steps back the moment another lane
        adds a table."""
        path = tmp_path / "previous.db"
        connection = db.init_db(path)
        connection.execute("DROP TABLE venue_positions")
        db._set_meta(connection, "schema_version", str(db.SCHEMA_VERSION - 1))
        connection.commit()
        connection.close()

        reopened = db.init_db(path)
        try:
            names = {
                row[0]
                for row in reopened.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            assert "venue_positions" in names
            assert db.get_meta(reopened, "schema_version") == str(
                db.SCHEMA_VERSION
            )
        finally:
            reopened.close()

    def test_v33_is_declared_tableless(self):
        assert 33 in db._TABLELESS_VERSIONS
        assert 33 not in db._MIGRATIONS

    def test_a_row_must_name_the_poll_it_came_from(self, conn):
        """One stamp: a mirror row that points at no `poll_log` row could be
        read beside a count it did not come from. `PRAGMA foreign_keys = ON`
        is what makes the REFERENCES clause bind."""
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO venue_positions (poll_log_id, polled_ms, ticker) "
                "VALUES (999, 1, 'KXT')"
            )

    @pytest.mark.parametrize(
        "column, value",
        [("exposure_tenths", -1), ("contracts", -0.5), ("side", "'maybe'")],
    )
    def test_the_derived_columns_refuse_what_they_cannot_mean(
        self, conn, column, value
    ):
        """Exposure at cost is money in and cannot be negative; a quantity
        is unsigned once the side is split off; a side is yes or no. The
        parser leaves each NULL when unreadable, and the CHECK is what stops a
        different writer from storing a value the reader would sum."""
        poll_id = _poll(conn, polled_ms=1)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                f"INSERT INTO venue_positions (poll_log_id, polled_ms, {column}) "
                f"VALUES (?, 1, {value})",
                (poll_id,),
            )
