"""The 2026-08-30 wedge: a failed pass poisons its connection, and the failure
record now survives it.

What happened on live, twice in one night (00:28Z and 02:27Z): a pass died
between statements -- cancelled by the 600s deadline or raising -- and nothing
on the failure path rolled back or reset. The connection kept a stale WAL read
snapshot; the portfolio poller's own connection kept committing every five
minutes, advancing the WAL past it; and from then on every write attempt on
the poisoned connection failed instantly with "database is locked"
(SQLITE_BUSY_SNAPSHOT -- the busy timeout never runs, because waiting cannot
make a stale snapshot fresh). Five strikes later the process shot itself.

The observable signature, pinned here because it inverts the table's
documented reading: `loop_failures` stayed EMPTY across the exact window it
exists to explain, because `record_loop_failure` wrote over the same poisoned
connection and failed with the same error -- and the dying FAILURE_LOOP_DIED
alert died the same way. `poll_log`, written by the healthy connection, shows
unbroken success through the whole wedge.

Three mechanism facts this file measures rather than assumes:

- the poison needs a LIVE REFERENCE to the abandoned cursor; a refcount-freed
  cursor releases the snapshot and nothing is poisoned;
- `Connection.rollback()` alone does not cure it (CPython stopped resetting
  statements on rollback in 3.11);
- closing the cursor and rolling back does cure it -- but production cannot
  reach the cursor, which is why the durable recorder falls back to a fresh
  connection instead of promising a cure.

WHAT THIS FILE DOES NOT ESTABLISH: which statement the dead pass abandoned on
2026-08-30, or what holds its reference. The fix is generic over both.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from backend.store import db as store_db


@pytest.fixture
def wal_db(tmp_path):
    """A file-backed WAL database. In-memory databases cannot show any of
    this: WAL and cross-connection snapshots need a real file."""
    path = tmp_path / "wedge.db"
    setup = sqlite3.connect(path)
    setup.execute("PRAGMA journal_mode = WAL")
    setup.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    setup.executemany(
        "INSERT INTO t (v) VALUES (?)", [(f"row{i}",) for i in range(10)]
    )
    setup.commit()
    setup.close()
    return path


def _connect(path: Path) -> sqlite3.Connection:
    # timeout=0.2 rather than the production 5s so the test distinguishes
    # "failed instantly despite a busy timeout" from "timed out": a
    # BUSY_SNAPSHOT error does not consume the timeout at all.
    conn = sqlite3.connect(path, timeout=0.2)
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _poison(conn: sqlite3.Connection, other: sqlite3.Connection):
    """Build the live state: an abandoned-but-referenced cursor, then a
    concurrent commit that leaves its snapshot behind the WAL head."""
    cursor = conn.execute("SELECT * FROM t")
    cursor.fetchone()
    other.execute("INSERT INTO t (v) VALUES ('poller')")
    other.commit()
    return cursor  # the caller must keep this alive: that IS the poison


class TestTheMechanismIsRealAndBehavesAsDocumented:
    def test_a_referenced_half_read_cursor_plus_a_commit_poisons_writes(
        self, wal_db
    ):
        poisoned = _connect(wal_db)
        healthy = _connect(wal_db)
        try:
            cursor = _poison(poisoned, healthy)
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                poisoned.execute("INSERT INTO t (v) VALUES ('pass')")
            assert cursor is not None
        finally:
            poisoned.close()
            healthy.close()

    def test_the_healthy_connection_keeps_writing_through_the_wedge(
        self, wal_db
    ):
        """The discriminating observation from live: poll_log full, everything
        on the runner's connection refused. A single held write lock could not
        produce that split; a stale snapshot produces exactly it."""
        poisoned = _connect(wal_db)
        healthy = _connect(wal_db)
        try:
            cursor = _poison(poisoned, healthy)
            for i in range(3):
                healthy.execute("INSERT INTO t (v) VALUES (?)", (f"cycle{i}",))
                healthy.commit()
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                poisoned.execute("INSERT INTO t (v) VALUES ('pass')")
            assert cursor is not None
        finally:
            poisoned.close()
            healthy.close()

    def test_a_refcount_freed_cursor_does_not_poison(self, wal_db):
        """So the poison requires something long-lived holding the cursor --
        which is why no in-process cure can be promised, and why the durable
        recorder does not try to promise one."""
        conn = _connect(wal_db)
        healthy = _connect(wal_db)
        try:
            def abandon():
                cursor = conn.execute("SELECT * FROM t")
                cursor.fetchone()
                # falls out of scope: refcount finalises the statement

            abandon()
            healthy.execute("INSERT INTO t (v) VALUES ('poller')")
            healthy.commit()
            conn.execute("INSERT INTO t (v) VALUES ('pass')")
            conn.commit()
        finally:
            conn.close()
            healthy.close()

    def test_rollback_alone_does_not_cure_a_referenced_cursor(self, wal_db):
        """Measured, not assumed: CPython stopped resetting statements on
        rollback in 3.11, so the reachable cure covers only the open-
        transaction half of the poison."""
        poisoned = _connect(wal_db)
        healthy = _connect(wal_db)
        try:
            cursor = _poison(poisoned, healthy)
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                poisoned.execute("INSERT INTO t (v) VALUES ('pass')")
            poisoned.rollback()
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                poisoned.execute("INSERT INTO t (v) VALUES ('pass')")
            assert cursor is not None
        finally:
            poisoned.close()
            healthy.close()

    def test_closing_the_cursor_and_rolling_back_cures(self, wal_db):
        poisoned = _connect(wal_db)
        healthy = _connect(wal_db)
        try:
            cursor = _poison(poisoned, healthy)
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                poisoned.execute("INSERT INTO t (v) VALUES ('pass')")
            cursor.close()
            poisoned.rollback()
            poisoned.execute("INSERT INTO t (v) VALUES ('recovered')")
            poisoned.commit()
        finally:
            poisoned.close()
            healthy.close()


@pytest.fixture
def loop_db(tmp_path):
    """A real schema database, so `loop_failures` exists."""
    path = tmp_path / "loop.db"
    conn = store_db.init_db(path)
    return path, conn


class TestTheDurableRecorderSurvivesThePoison:
    def _poison_schema_conn(self, path, conn):
        healthy = sqlite3.connect(path)
        # An empty result set cannot hold a snapshot open; read a table with
        # rows in it. `meta` carries the schema version row.
        cursor = conn.execute("SELECT * FROM meta")
        assert cursor.fetchone() is not None
        healthy.execute(
            "INSERT INTO loop_failures (failed_ms, pass_number, "
            "consecutive_failures, error) VALUES (1, 1, 1, 'seed')"
        )
        healthy.commit()
        healthy.close()
        return cursor

    def test_a_healthy_connection_records_and_reports_recorded(
        self, loop_db, tmp_path
    ):
        path, conn = loop_db
        journal = tmp_path / "loop_failures.jsonl"
        outcome = store_db.record_loop_failure_durably(
            conn,
            db_path=path,
            journal_path=journal,
            failed_ms=42,
            pass_number=7,
            consecutive_failures=1,
            error="ValueError: boom",
            pass_kind="full",
        )
        assert outcome == "recorded"
        rows = conn.execute("SELECT * FROM loop_failures").fetchall()
        assert len(rows) == 1
        first = json.loads(journal.read_text(encoding="utf-8").splitlines()[0])
        assert first["error"] == "ValueError: boom"
        assert first["pass_kind"] == "full"

    def test_a_poisoned_connection_still_gets_the_row_written(
        self, loop_db, tmp_path
    ):
        """The night's defect, replayed with the fix in place: the row that
        failed five times on live now lands via the throwaway connection,
        and the journal names the diagnosis."""
        path, conn = loop_db
        journal = tmp_path / "loop_failures.jsonl"
        cursor = self._poison_schema_conn(path, conn)

        outcome = store_db.record_loop_failure_durably(
            conn,
            db_path=path,
            journal_path=journal,
            failed_ms=99,
            pass_number=3,
            consecutive_failures=2,
            error="OperationalError: database is locked",
            pass_kind="quote",
        )
        assert cursor is not None
        # Either the rollback cured it (open-transaction case) or the fresh
        # connection carried it (referenced-cursor case); both are correct,
        # and which one happened is visible in the outcome.
        assert outcome in ("recorded", "recorded_on_fresh_connection")

        reader = sqlite3.connect(path)
        try:
            count = reader.execute(
                "SELECT COUNT(*) FROM loop_failures WHERE pass_number = 3"
            ).fetchone()[0]
        finally:
            reader.close()
        assert count == 1, (
            "the failure row must land even when the shared connection is "
            "refusing writes -- an empty table across a wedge is the exact "
            "defect this exists to end"
        )

    def test_the_poisoned_case_journals_its_own_diagnosis(
        self, loop_db, tmp_path
    ):
        path, conn = loop_db
        journal = tmp_path / "loop_failures.jsonl"
        cursor = self._poison_schema_conn(path, conn)
        outcome = store_db.record_loop_failure_durably(
            conn,
            db_path=path,
            journal_path=journal,
            failed_ms=99,
            pass_number=3,
            consecutive_failures=2,
            error="OperationalError: database is locked",
        )
        assert cursor is not None
        lines = [
            json.loads(line)
            for line in journal.read_text(encoding="utf-8").splitlines()
        ]
        assert lines[0]["error"] == "OperationalError: database is locked"
        if outcome == "recorded_on_fresh_connection":
            assert any(
                "poisoned" in (line.get("diagnosis") or "") for line in lines
            )

    def test_the_journal_survives_even_when_the_database_is_gone(
        self, tmp_path
    ):
        """The row has a fallback; the journal must not need one."""
        path = tmp_path / "gone.db"
        conn = store_db.init_db(path)
        conn.close()  # a closed connection refuses everything
        journal = tmp_path / "loop_failures.jsonl"
        outcome = store_db.record_loop_failure_durably(
            conn,
            db_path=tmp_path / "nonexistent" / "nope.db",
            journal_path=journal,
            failed_ms=7,
            pass_number=1,
            consecutive_failures=1,
            error="anything",
        )
        assert outcome == "journal_only"
        lines = journal.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2  # the failure, then the diagnosis
        assert "refuses writes" in json.loads(lines[1])["diagnosis"]

    def test_the_traceback_reaches_the_journal(self, loop_db, tmp_path):
        path, conn = loop_db
        journal = tmp_path / "loop_failures.jsonl"
        try:
            raise ValueError("the pass's own error")
        except ValueError as exc:
            store_db.record_loop_failure_durably(
                conn,
                db_path=path,
                journal_path=journal,
                failed_ms=1,
                pass_number=1,
                consecutive_failures=1,
                error="ValueError: the pass's own error",
                exc=exc,
            )
        first = json.loads(journal.read_text(encoding="utf-8").splitlines()[0])
        assert "the pass's own error" in first["traceback"]
        assert "Traceback" in first["traceback"]


class TestTheLoopWiresTheDurableRecorderUp:
    """`record_failure` is a closure inside `run_loop.main()`, so its wiring is
    asserted over the source -- the same pattern as
    `test_loop_failures_are_recorded.TestTheLoopWiresItUp`. The behaviour is
    proved live above."""

    @staticmethod
    def _source() -> str:
        root = Path(__file__).resolve().parents[1]
        return (root / "scripts" / "run_loop.py").read_text(encoding="utf-8")

    def test_the_hook_records_durably_rather_than_directly(self):
        source = self._source()
        block = source[source.index("def record_failure(") :]
        block = block[: block.index("def take_refresh_requests(")]
        assert "db.record_loop_failure_durably(" in block
        assert "db.record_loop_failure(" not in block.replace(
            "db.record_loop_failure_durably(", ""
        ), "the direct write has no journal and no fallback"

    def test_the_journal_sits_beside_the_database(self):
        source = self._source()
        assert (
            'failure_log = Path(args.db).resolve().parent / '
            '"loop_failures.jsonl"' in source
        )

    def test_the_dying_alert_rolls_back_and_has_a_fresh_connection_fallback(
        self,
    ):
        """The FAILURE_LOOP_DIED alert shares the connection, and on
        2026-08-30 it died on the same lock -- so the one alert that explains
        a dead loop never went out."""
        source = self._source()
        block = source[source.index("except LoopFailed as exc:") :]
        block = block[: block.index("finally:")]
        assert "conn.rollback()" in block
        assert block.index("conn.rollback()") < block.index(
            "alerter.failure("
        )
        assert "FAILURE_LOOP_DIED" in block
        assert "except sqlite3.Error:" in block
        assert "Alerter(fresh, discord)" in block
