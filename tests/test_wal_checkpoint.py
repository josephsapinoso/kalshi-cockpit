"""The WAL is checkpointed by something, and the attempt is on the record.

**Why this exists.** Until 2026-08-30 nothing in this repo called
`wal_checkpoint`. `journal_mode = WAL` with `synchronous = NORMAL` leaves the
job to the automatic PASSIVE checkpoint the writer attempts on commit, and a
PASSIVE checkpoint abandons quietly against any reader holding an older
snapshot -- while this instance opens a read-only connection per API request
and Fly health-checks every 15 seconds.

The consequence was measured on live that afternoon: the log went 32 -> 66 ->
99.5 MB in five minutes with `candidate_ms` going 0.46s -> 36.6s beside it,
and it never came back down. A machine restart took the WAL to 28 KB and
`/api/health` from 3.4s to 0.37s, which is the only remedy the system had.

**What this establishes.** That a checkpoint runs, that a TRUNCATE which is
allowed to finish actually hands the disk back, that a reader in the way is
reported as `busy` rather than swallowed, that the mode is chosen from the
log's measured size, and that the result reaches `loop_rss.jsonl` where a
future diagnosis can read it.

**What it does not establish.**

- **That checkpointing is why the queries were slow.** These fields are the
  instrument that would answer it; the answer is a reading of live data. A
  bounded WAL and a fast query are two claims and only the first is tested.
- **That a busy checkpoint is rare, or that TRUNCATE ever succeeds on the
  live box.** Both are questions for `wal_ckpt_busy` on real passes.
- **Anything about the size of the live WAL.** Every figure here is synthetic.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.store import db  # noqa: E402
from scripts.run_loop import maybe_checkpoint, record_pass_rss  # noqa: E402


def _grow_the_wal(conn, rows: int = 400) -> None:
    """Commit enough separate transactions to put frames in the log.

    `wal_autocheckpoint = 0` first, deliberately: the automatic checkpoint
    would otherwise empty the log at 1,000 pages and every assertion below
    would be about SQLite's default rather than about the call being tested.
    Turning it off is also the shape of the live problem -- a log nobody
    checkpoints.
    """
    conn.execute("PRAGMA wal_autocheckpoint = 0")
    conn.execute("CREATE TABLE IF NOT EXISTS ballast (id INTEGER, blob TEXT)")
    conn.commit()
    for i in range(rows):
        conn.execute("INSERT INTO ballast VALUES (?, ?)", (i, "x" * 2000))
        conn.commit()


def _fake_proc(tmp_path: Path):
    """The `/proc` the sampler reads. Windows has none, so the line needs it."""
    proc = tmp_path / "proc"
    (proc / "self").mkdir(parents=True)
    (proc / "self" / "status").write_text("VmRSS:\t  331508 kB\n")
    (proc / "meminfo").write_text("MemAvailable:\t  522812 kB\n")
    return proc


def _wal_bytes(path: Path) -> int:
    wal = Path(str(path) + "-wal")
    return wal.stat().st_size if wal.exists() else 0


class TestTheLogIsHandedBack:
    def test_truncate_returns_the_disk(self, tmp_path):
        path = tmp_path / "cockpit.db"
        conn = db.init_db(path)
        _grow_the_wal(conn)
        assert _wal_bytes(path) > 0, "the fixture did not produce a WAL"

        result = db.checkpoint_wal(conn, mode="TRUNCATE")

        assert result.busy is False
        assert _wal_bytes(path) == 0
        # **Zero frames is what a successful TRUNCATE reports** (SQLite
        # 3.45.1 zeroes both counters with the file), so `busy` is the field
        # that says it worked and the frame counts are not evidence either
        # way. Pinned because reading these two as "it did nothing" is the
        # obvious mistake.
        assert result.log_frames == 0
        assert result.moved_frames == 0
        conn.close()

    def test_a_passive_checkpoint_reports_what_it_moved(self, tmp_path):
        path = tmp_path / "cockpit.db"
        conn = db.init_db(path)
        _grow_the_wal(conn)

        result = db.checkpoint_wal(conn, mode="PASSIVE")

        assert result.mode == "PASSIVE"
        assert result.busy is False
        # PASSIVE keeps the log in place, so its counters are real work: this
        # is the mode that can show frames moving at all.
        assert result.moved_frames and result.moved_frames > 0
        assert result.log_frames == result.moved_frames
        conn.close()

    def test_the_size_limit_lets_a_passive_checkpoint_hand_disk_back(
        self, tmp_path
    ):
        """`journal_size_limit = 0` is what makes the ordinary path shrink it.

        TRUNCATE hands the file back whatever the limit says, so this guard is
        not about the call above -- it is about the PASSIVE checkpoint the
        writer already attempted on every commit. Measured on SQLite 3.45.1
        with this exact fixture:

            journal_size_limit = -1 (the default)   4,614,432 -> 4,614,432
            journal_size_limit = 0                  4,614,432 ->     4,152

        So the log the live box carried at a plateau all process long was one
        SQLite was entitled to reuse in place. Delete the PRAGMA in
        `store.db.connect` and this test fails.
        """
        path = tmp_path / "cockpit.db"
        conn = db.init_db(path)
        assert conn.execute("PRAGMA journal_size_limit").fetchone()[0] == 0
        _grow_the_wal(conn)
        grown = _wal_bytes(path)

        conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        # The reset happens on the next write into the checkpointed log, not
        # inside the checkpoint itself.
        conn.execute("INSERT INTO ballast VALUES (?, ?)", (1, "z"))
        conn.commit()

        assert _wal_bytes(path) < grown / 10
        conn.close()


class TestAReaderInTheWayIsReported:
    def test_busy_when_another_connection_holds_a_snapshot(self, tmp_path):
        """The hypothesis the whole change exists to test, made observable.

        A reader mid-transaction is exactly the live shape: a per-request
        read-only connection, plus a health check every 15s. The point is not
        that this fails -- it is that the failure is a value on a line rather
        than silence.
        """
        path = tmp_path / "cockpit.db"
        writer = db.init_db(path)
        _grow_the_wal(writer)

        reader = db.open_db(path, read_only=True)
        # BEGIN then read: the snapshot is not taken until a statement runs.
        reader.execute("BEGIN")
        reader.execute("SELECT COUNT(*) FROM ballast").fetchone()
        # A frame the reader's snapshot cannot include, so the log cannot be
        # reset while it is open.
        writer.execute("INSERT INTO ballast VALUES (?, ?)", (99999, "y"))
        writer.commit()

        result = db.checkpoint_wal(writer, mode="TRUNCATE")

        assert result.busy is True
        assert _wal_bytes(path) > 0

        reader.rollback()
        reader.close()
        writer.close()

    def test_a_broken_connection_resolves_to_a_result_not_an_exception(
        self, tmp_path
    ):
        """Housekeeping may not be able to kill the recorder."""
        conn = db.init_db(tmp_path / "cockpit.db")
        conn.close()

        result = db.checkpoint_wal(conn, mode="PASSIVE")

        assert result.busy is True
        assert result.error is not None
        assert result.log_frames is None, "an unknown never resolves to zero"

    def test_an_unknown_mode_is_refused_rather_than_passed_through(
        self, tmp_path
    ):
        conn = db.init_db(tmp_path / "cockpit.db")
        with pytest.raises(ValueError):
            db.checkpoint_wal(conn, mode="TRUNCATE); DROP TABLE quotes --")
        conn.close()


class TestTheModeIsChosenFromTheMeasuredSize:
    def test_a_small_log_is_left_to_passive(self, tmp_path):
        path = tmp_path / "cockpit.db"
        conn = db.init_db(path)
        _grow_the_wal(conn, rows=5)

        result = maybe_checkpoint(conn, db_path=path)

        assert result.mode == "PASSIVE"
        conn.close()

    def test_a_large_log_asks_for_truncate(self, tmp_path):
        path = tmp_path / "cockpit.db"
        conn = db.init_db(path)
        _grow_the_wal(conn, rows=50)

        # The threshold is a parameter here so the test does not have to write
        # 32 MiB to reach the deployed one.
        result = maybe_checkpoint(conn, db_path=path, truncate_above_kib=0)

        assert result.mode == "TRUNCATE"
        conn.close()

    def test_an_unmeasurable_log_picks_no_mode_at_all(self, tmp_path):
        """`None`, never a guessed PASSIVE. The repo's standing rule."""
        conn = db.init_db(tmp_path / "cockpit.db")
        assert maybe_checkpoint(conn, db_path=tmp_path / "absent.db") is None
        conn.close()


class TestTheAttemptReachesTheRecord:
    def test_the_pass_line_carries_the_checkpoint_result(self, tmp_path):
        path = tmp_path / "cockpit.db"
        conn = db.init_db(path)
        _grow_the_wal(conn, rows=20)
        result = db.checkpoint_wal(conn, mode="TRUNCATE")
        conn.close()

        log = tmp_path / "loop_rss.jsonl"
        record_pass_rss(
            log,
            now_ms=1_788_112_000_000,
            kind="quote",
            produced_by="quote",
            proc=_fake_proc(tmp_path),
            db_path=path,
            checkpoint=result,
        )

        line = json.loads(log.read_text().splitlines()[-1])
        assert line["wal_ckpt_mode"] == "TRUNCATE"
        assert line["wal_ckpt_busy"] == 0
        assert line["wal_ckpt_moved_frames"] == 0  # see the TRUNCATE note
        assert line["wal_ckpt_error"] is None

    def test_no_attempt_reads_as_null_and_never_as_a_clean_checkpoint(
        self, tmp_path
    ):
        """The first pass of a process attempts nothing.

        `wal_ckpt_busy: null` is "no attempt"; `0` is "it succeeded". A line
        that reported the second when it meant the first would exonerate the
        readers on evidence that was never collected.
        """
        log = tmp_path / "loop_rss.jsonl"
        record_pass_rss(
            log,
            now_ms=1_788_112_000_000,
            kind="full",
            produced_by=None,
            proc=_fake_proc(tmp_path),
            db_path=tmp_path / "cockpit.db",
            checkpoint=None,
        )

        line = json.loads(log.read_text().splitlines()[-1])
        assert line["wal_ckpt_busy"] is None
        assert line["wal_ckpt_mode"] is None


class TestItIsActuallyCalled:
    def test_the_pass_calls_the_checkpoint(self):
        """Four modules in this repo were once complete and invoked by nothing.

        `one_pass` is nested inside `main()` behind a live Kalshi client, so
        the cheap honest check is over the source: the call exists, and it
        exists at the top of the pass rather than only in a helper nothing
        reaches. See `tasks/lessons.md` -- "built but never called".
        """
        source = (ROOT / "scripts" / "run_loop.py").read_text(encoding="utf-8")

        assert "def maybe_checkpoint(" in source
        assert "last_checkpoint[0] = maybe_checkpoint(" in source
        assert "checkpoint=last_checkpoint[0]" in source

    def test_the_inspector_renders_the_new_fields(self):
        """A field written and never rendered is a field nobody reads."""
        from scripts.inspect_live_db import _LOOP_RSS_COLUMNS

        for name in (
            "wal_ckpt_mode",
            "wal_ckpt_busy",
            "wal_ckpt_log_frames",
            "wal_ckpt_moved_frames",
            "wal_ckpt_error",
        ):
            assert name in _LOOP_RSS_COLUMNS
