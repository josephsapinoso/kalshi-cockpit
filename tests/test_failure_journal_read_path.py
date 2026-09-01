"""The failure journal had a writer and no reader, for two days.

`db.record_loop_failure_durably` has appended every pass failure to
`loop_failures.jsonl` since 2026-08-30. It exists because the `loop_failures`
TABLE goes silent under exactly the condition it is there to record: a pass
that dies mid-transaction poisons the shared connection with a stale WAL read
snapshot, and every later write on it -- including the failure row -- fails
instantly with `database is locked`.

Nothing read the file. `grep -rn loop_failures.jsonl` found the writer, and
tests of the writer, and no consumer on any machine: `inspect_live_db.py` is
the only thing that can run against the live box, and it had no query for it.
So the durable half of the record was unreachable from the place the question
gets asked, and `tasks/NEXT.md`'s open item named the TABLE as "the
instrument" -- the artifact that cannot see this failure class.

What this file establishes
--------------------------
That `inspect_live_db failure-journal` reads the file the loop writes, that it
separates a failure the table kept from one the table lost, and that an absent
file is reported as absent rather than as a clean bill.

What it does not establish
--------------------------
- **That the live journal is non-empty**, or anything about live at all. The
  fixtures here are `tmp_path` files written by the real writer.
- **That the poisoned-connection path is reachable in production.** The
  journal-only case is forced here by pointing the fallback at an unopenable
  path, which is a different cause with the same shape.
- **Anything about failures that leave no line at all** -- a container that
  dies between passes writes neither journal nor row. `pass-gaps` is the
  instrument for that half, and the pair is the reading.
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

from backend.store import db

NOW = 1_788_174_060_409


def _read(db_path: Path, *args: str) -> list[dict]:
    """Run the query through the only entry point a caller has, in JSON."""
    from scripts.inspect_live_db import main

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(["failure-journal", "--db", str(db_path), "--json", *args])
    assert rc == 0, buf.getvalue()
    return json.loads(buf.getvalue())["sections"]


class TestTheWriterAndTheReaderNameTheSameFile:
    """`inspect_live_db.py` imports nothing from `backend` on purpose, so the
    filename is spelled twice. A reader pointed at a file nobody writes reports
    a clean instrument, which is the one output this whole file exists to
    prevent -- the same guard `walk-log` carries for `loop_walk.jsonl`."""

    def test_run_loop_writes_the_name_the_inspector_reads(self):
        import inspect as inspect_module

        from scripts import run_loop
        from scripts.inspect_live_db import FAILURE_LOG_NAME

        source = inspect_module.getsource(run_loop.main)
        assert f'"{FAILURE_LOG_NAME}"' in source, (
            f"`inspect_live_db` reads {FAILURE_LOG_NAME}; `run_loop.main` no "
            "longer writes a file by that name"
        )

    def test_the_journal_now_has_a_reader_at_all(self):
        """The defect this file closes. `record_loop_failure_durably` calls its
        journal the layer "no lock can refuse", and for two days no code
        anywhere could read it back."""
        from scripts.inspect_live_db import QUERIES

        assert "failure-journal" in QUERIES


class TestTheTableAndTheJournalAreReadAsAPair:
    """Section 1 is the whole point of the query: a journal line with no
    `loop_failures` row is a failure the table could not record."""

    def _journal_only(self, tmp_path: Path) -> Path:
        """Drive the REAL writer into its `journal_only` outcome.

        Both connections must refuse for the row to be lost, so the shared one
        is closed and the fallback is pointed at a path that cannot be opened.
        A hand-written line would assert the reader against the reader.
        """
        db_path = tmp_path / "cockpit.db"
        db.init_db(db_path).close()
        journal = tmp_path / "loop_failures.jsonl"

        closed = db.init_db(db_path)
        closed.close()
        outcome = db.record_loop_failure_durably(
            closed,
            db_path=tmp_path / "no-such-dir" / "cockpit.db",
            journal_path=journal,
            failed_ms=NOW,
            pass_number=20,
            consecutive_failures=3,
            error="OperationalError: database is locked",
            pass_kind="full",
            exc=RuntimeError("the pass raised"),
        )
        assert outcome == "journal_only", outcome
        return db_path

    def test_a_failure_the_table_never_got_is_the_first_section(self, tmp_path):
        db_path = self._journal_only(tmp_path)
        missing = _read(db_path)[0]
        assert missing["row_count"] == 1, missing
        assert "20" in json.dumps(missing["rows"][0]), missing["rows"][0]

    def test_the_title_says_a_table_count_is_a_floor(self, tmp_path):
        """The number is useless without the sentence that says what it means
        for every other count taken off that table."""
        db_path = self._journal_only(tmp_path)
        assert "FLOOR" in _read(db_path)[0]["title"]

    def test_a_failure_the_table_did_keep_is_not_reported_missing(
        self, tmp_path
    ):
        """The same writer, on a connection that works. If this section filled
        up on the ordinary path it would cry wolf on every failure ever."""
        db_path = tmp_path / "cockpit.db"
        conn = db.init_db(db_path)
        outcome = db.record_loop_failure_durably(
            conn,
            db_path=db_path,
            journal_path=tmp_path / "loop_failures.jsonl",
            failed_ms=NOW,
            pass_number=21,
            consecutive_failures=4,
            error="OperationalError: database is locked",
            pass_kind="full",
            exc=RuntimeError("the pass raised"),
        )
        conn.close()
        assert outcome == "recorded", outcome

        sections = _read(db_path)
        assert sections[0]["row_count"] == 0, sections[0]
        assert sections[2]["row_count"] == 1, sections[2]

    def test_the_two_cases_are_told_apart_in_one_read(self, tmp_path):
        """One journal holding both shapes. The kept failure must stay out of
        section 1 while the lost one stays in it -- the discrimination is the
        query, and a reader that passed both single-case tests could still
        report every line as missing."""
        db_path = tmp_path / "cockpit.db"
        journal = tmp_path / "loop_failures.jsonl"
        conn = db.init_db(db_path)
        db.record_loop_failure_durably(
            conn, db_path=db_path, journal_path=journal, failed_ms=NOW,
            pass_number=21, consecutive_failures=4, error="kept",
            pass_kind="full", exc=RuntimeError("kept"),
        )
        conn.close()

        closed = db.init_db(db_path)
        closed.close()
        db.record_loop_failure_durably(
            closed, db_path=tmp_path / "no-such-dir" / "cockpit.db",
            journal_path=journal, failed_ms=NOW + 1, pass_number=22,
            consecutive_failures=5, error="lost", pass_kind="full",
            exc=RuntimeError("lost"),
        )

        sections = _read(db_path, "-n", "10")
        assert sections[0]["row_count"] == 1, sections[0]
        assert "lost" in json.dumps(sections[0]["rows"]), sections[0]
        assert "kept" not in json.dumps(sections[0]["rows"]), sections[0]
        assert sections[2]["row_count"] == 2, sections[2]


class TestADiagnosisLineIsNotAFailure:
    """`record_loop_failure_durably` appends a second, differently shaped line
    when the shared connection refuses. Counting it as a failure would double
    every burst that got one, and it carries no `pass_number` to double it
    with."""

    def test_the_diagnosis_is_its_own_section_and_not_a_failure_row(
        self, tmp_path
    ):
        db_path = tmp_path / "cockpit.db"
        db.init_db(db_path).close()
        journal = tmp_path / "loop_failures.jsonl"

        closed = db.init_db(db_path)
        closed.close()
        outcome = db.record_loop_failure_durably(
            closed,
            db_path=db_path,
            journal_path=journal,
            failed_ms=NOW,
            pass_number=20,
            consecutive_failures=3,
            error="OperationalError: database is locked",
            pass_kind="full",
            exc=RuntimeError("the pass raised"),
        )
        assert outcome == "recorded_on_fresh_connection", outcome

        sections = _read(db_path, "-n", "10")
        assert sections[1]["row_count"] == 1, sections[1]
        assert "poisoned" in json.dumps(sections[1]["rows"][0])
        assert sections[2]["row_count"] == 1, (
            "the diagnosis line was counted as a second failure"
        )

    def test_a_row_written_by_the_fallback_is_not_reported_missing(
        self, tmp_path
    ):
        """The fresh connection did write the row, so the table is complete for
        that failure. Section 1 must stay empty or it accuses the table of a
        loss that did not happen."""
        db_path = tmp_path / "cockpit.db"
        db.init_db(db_path).close()
        closed = db.init_db(db_path)
        closed.close()
        db.record_loop_failure_durably(
            closed, db_path=db_path,
            journal_path=tmp_path / "loop_failures.jsonl", failed_ms=NOW,
            pass_number=20, consecutive_failures=3, error="locked",
            pass_kind="full", exc=RuntimeError("x"),
        )
        assert _read(db_path)[0]["row_count"] == 0


class TestTheTracebackIsReachable:
    """It is written here and nowhere else -- stdout retention on the machine
    is ~10 minutes -- so a reader that summarised it into a column would leave
    the journal's most expensive field unread."""

    def test_the_newest_traceback_renders_one_line_per_row(self, tmp_path):
        db_path = tmp_path / "cockpit.db"
        conn = db.init_db(db_path)

        def _raise() -> None:
            raise RuntimeError("the pass raised here")

        try:
            _raise()
        except RuntimeError as exc:
            db.record_loop_failure_durably(
                conn, db_path=db_path,
                journal_path=tmp_path / "loop_failures.jsonl",
                failed_ms=NOW, pass_number=21, consecutive_failures=1,
                error="RuntimeError: the pass raised here", pass_kind="full",
                exc=exc,
            )
        conn.close()

        tb = _read(db_path)[3]
        assert tb["row_count"] > 1, tb
        rendered = json.dumps(tb["rows"])
        assert "_raise" in rendered, rendered
        assert "the pass raised here" in rendered, rendered


class TestAMissingFileSaysSoRatherThanReportingNoFailures:
    """An absent instrument and an instrument saying 'no failures' are the two
    readings this script exists to keep apart, and the second is the more
    flattering of the two."""

    def test_the_absent_case_is_one_loud_row_and_not_four_empty_sections(
        self, tmp_path
    ):
        db_path = tmp_path / "cockpit.db"
        db.init_db(db_path).close()

        sections = _read(db_path)
        assert len(sections) == 1, sections
        assert sections[0]["row_count"] == 1, (
            "a missing journal reported zero rows, which reads as 'no pass "
            "has failed'"
        )
        assert "NOT THERE" in sections[0]["title"]

    def test_the_absent_case_names_the_path_and_the_writer(self, tmp_path):
        """So the next reader can tell 'the loop has not written yet' from 'the
        reader is pointed at the wrong volume' without opening the source."""
        db_path = tmp_path / "cockpit.db"
        db.init_db(db_path).close()

        row = json.dumps(_read(db_path)[0]["rows"][0])
        assert "loop_failures.jsonl" in row, row
        assert "record_loop_failure_durably" in row, row
