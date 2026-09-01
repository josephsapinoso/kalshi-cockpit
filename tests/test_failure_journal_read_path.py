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


def _section(sections: list[dict], needle: str) -> dict:
    """The section whose title carries `needle`, addressed by NAME.

    These tests indexed sections positionally until 2026-09-01, and inserting
    one in the middle exposed why that is not a detail: three assertions kept
    passing against the WRONG section because the new one happened to hold
    the same row count. A test that passes for a coincidental reason is worse
    than one that fails, and position is the coincidence.
    """
    matches = [s for s in sections if needle in s["title"]]
    assert len(matches) == 1, (
        f"{needle!r} matched {len(matches)} sections: "
        f"{[s['title'][:70] for s in sections]}"
    )
    return matches[0]


#: The markers each section is addressed by. Short, and taken from the part of
#: the title that states the section's job rather than its numbers.
MISSING = "failures the TABLE never got"
DIAGNOSIS = "DIAGNOSIS lines"
CURE = "what the CURE ATTEMPT found"
POPULATION = "failures, newest first"
TRACEBACK = "traceback of the newest failure"


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
        missing = _section(_read(db_path), MISSING)
        assert missing["row_count"] == 1, missing
        assert "20" in json.dumps(missing["rows"][0]), missing["rows"][0]

    def test_the_title_says_a_table_count_is_a_floor(self, tmp_path):
        """The number is useless without the sentence that says what it means
        for every other count taken off that table."""
        db_path = self._journal_only(tmp_path)
        assert "FLOOR" in _section(_read(db_path), MISSING)["title"]

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
        assert _section(sections, MISSING)["row_count"] == 0, sections
        assert _section(sections, POPULATION)["row_count"] == 1, sections

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
        missing = _section(sections, MISSING)
        assert missing["row_count"] == 1, missing
        assert "lost" in json.dumps(missing["rows"]), missing
        assert "kept" not in json.dumps(missing["rows"]), missing
        assert _section(sections, POPULATION)["row_count"] == 2, sections


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
        diagnosis = _section(sections, DIAGNOSIS)
        assert diagnosis["row_count"] == 1, diagnosis
        assert "poisoned" in json.dumps(diagnosis["rows"][0])
        assert _section(sections, POPULATION)["row_count"] == 1, (
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
        assert _section(_read(db_path), MISSING)["row_count"] == 0


class TestTheScreenCarriesThePopulationAndNotJustTheLoss:
    """Added 2026-09-01, after an audit convicted this session's own first
    write-up of the reading.

    Section 1's rows are SELECTED by having no table row, and `journal_only`
    is the only outcome that produces one -- so "every line in section 1 says
    both connections refused" is a tautology dressed as a finding. The
    tally that is not a tautology is the three-way one: how many recorded on
    the shared connection, how many on a fresh one, how many on neither. It
    has to be on the SCREEN, because the next session reads the screen.
    """

    def _one_of_each(self, tmp_path: Path) -> Path:
        """All three `record_loop_failure_durably` outcomes in one journal."""
        db_path = tmp_path / "cockpit.db"
        journal = tmp_path / "loop_failures.jsonl"

        conn = db.init_db(db_path)
        assert db.record_loop_failure_durably(
            conn, db_path=db_path, journal_path=journal, failed_ms=NOW,
            pass_number=1, consecutive_failures=1, error="shared",
            pass_kind="full", exc=RuntimeError("shared"),
        ) == "recorded"
        conn.close()

        closed = db.init_db(db_path)
        closed.close()
        assert db.record_loop_failure_durably(
            closed, db_path=db_path, journal_path=journal, failed_ms=NOW + 1,
            pass_number=2, consecutive_failures=1, error="fresh",
            pass_kind="full", exc=RuntimeError("fresh"),
        ) == "recorded_on_fresh_connection"

        closed2 = db.init_db(db_path)
        closed2.close()
        assert db.record_loop_failure_durably(
            closed2, db_path=tmp_path / "no-such-dir" / "cockpit.db",
            journal_path=journal, failed_ms=NOW + 2, pass_number=3,
            consecutive_failures=1, error="neither", pass_kind="full",
            exc=RuntimeError("neither"),
        ) == "journal_only"
        return db_path

    def test_the_three_outcomes_are_counted_on_the_screen(self, tmp_path):
        """One of each, so a reader that collapsed two of them would be caught
        -- the shared and the fresh case both leave a row, and only the
        diagnosis line beside it tells them apart."""
        sections = _read(self._one_of_each(tmp_path), "-n", "10")
        title = _section(sections, POPULATION)["title"]
        assert "3 journalled" in title, title
        assert "1 recorded on the shared connection" in title, title
        assert "1 on a fresh" in title, title
        assert "1 on neither" in title, title

    def test_the_screen_says_which_count_may_be_quoted(self, tmp_path):
        """The caveat travels with the number or it does not travel."""
        sections = _read(self._one_of_each(tmp_path), "-n", "10")
        title = _section(sections, POPULATION)["title"]
        assert "selected by its own outcome" in title, title

    def test_the_diagnosis_section_states_both_limits_it_cannot_state_itself(
        self, tmp_path
    ):
        """That the reading is taken after a `rollback()` whose success is not
        recorded, and that it does not identify the lock holder. Without both,
        a reader takes 'the database itself refuses writes' as evidence for one
        named writer, which is what happened the day this query shipped."""
        sections = _read(self._one_of_each(tmp_path), "-n", "10")
        title = _section(sections, DIAGNOSIS)["title"]
        assert "rollback in section 3" in title, title
        assert "not name the holder" in title, title


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

        tb = _section(_read(db_path), TRACEBACK)
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


class TestTheCureAttemptIsObserved:
    """`tasks/NEXT.md`'s open item 3, closed 2026-09-01.

    `record_loop_failure_durably` called `rollback()` inside
    `except sqlite3.Error: pass` and threw the answer away. That left the
    diagnosis below it unable to separate two facts with opposite
    consequences: "a fresh connection was refused, so someone ELSE holds the
    write lock" from "the shared connection was still holding it and refused
    the fresh one itself". The second is our own bug; the first is not.

    **The boolean the item asked for does not do the separating on its own,
    and that is the finding here.** A `rollback()` on a connection with no
    open transaction is a no-op that always succeeds, so `rollback_ok = True`
    is produced by "the poison was cleared" and by "there was nothing to
    clear" alike. `in_transaction`, read BEFORE the rollback, is the field
    that discriminates, and it is why these tests assert on the pair.

    What this class does not establish
    ----------------------------------
    - **Who held the lock.** No field written here names a holder, and the
      section's own title says so. That needs the poller's start and finish
      times correlated against these stamps, which is a separate open item.
    - **That rollback cures anything in production.** The cure/no-cure
      cross-tab is now recordable; it has no live rows yet.
    - **That the live journal will ever show the middle branch.** Every
      fixture here forces its branch; none of them is evidence about which
      branch production takes.
    """

    def _bare_connection(self, tmp_path: Path):
        """An OPEN, healthy connection whose `loop_failures` insert will fail.

        The other journal-only fixture in this file uses a CLOSED connection,
        which makes `in_transaction` unreadable and the rollback raise -- so
        it can only ever exercise one of the three cure branches. A database
        with no schema refuses the insert with `no such table` while leaving
        the connection perfectly readable, which is what reaches the other
        two.
        """
        import sqlite3

        return sqlite3.connect(tmp_path / "bare.db")

    def _journal_from_bare(self, tmp_path: Path, conn) -> Path:
        """Drive the real writer to `journal_only` off `conn`."""
        db_path = tmp_path / "cockpit.db"
        db.init_db(db_path).close()
        outcome = db.record_loop_failure_durably(
            conn,
            db_path=tmp_path / "no-such-dir" / "cockpit.db",
            journal_path=tmp_path / "loop_failures.jsonl",
            failed_ms=NOW,
            pass_number=40,
            consecutive_failures=1,
            error="OperationalError: database is locked",
            pass_kind="full",
            exc=RuntimeError("the pass raised"),
        )
        assert outcome == "journal_only", outcome
        return db_path

    def _lines(self, tmp_path: Path) -> list[dict]:
        raw = (tmp_path / "loop_failures.jsonl").read_text(encoding="utf-8")
        return [json.loads(line) for line in raw.splitlines() if line.strip()]

    def _rollback_line(self, tmp_path: Path) -> dict:
        return next(
            e for e in self._lines(tmp_path) if e.get("kind") == "rollback"
        )

    def test_the_rollback_attempt_is_journalled_at_all(self, tmp_path):
        """The observation existed nowhere before this. Its absence is what
        made the diagnosis line unfalsifiable."""
        conn = db.init_db(tmp_path / "cockpit.db")
        db.record_loop_failure_durably(
            conn, db_path=tmp_path / "cockpit.db",
            journal_path=tmp_path / "loop_failures.jsonl", failed_ms=NOW,
            pass_number=1, consecutive_failures=1, error="x", pass_kind="full",
            exc=RuntimeError("x"),
        )
        conn.close()

        rollbacks = [
            e for e in self._lines(tmp_path) if e.get("kind") == "rollback"
        ]
        assert len(rollbacks) == 1, self._lines(tmp_path)
        assert rollbacks[0]["rollback_ok"] is True, rollbacks[0]

    def test_in_transaction_is_read_before_the_rollback_and_not_after(
        self, tmp_path
    ):
        """The load-bearing one. Read after the rollback this is False on
        every line ever written, and the field looks populated while carrying
        no information at all."""
        conn = self._bare_connection(tmp_path)
        conn.execute("CREATE TABLE t (a INTEGER)")
        conn.commit()
        conn.execute("INSERT INTO t (a) VALUES (1)")
        assert conn.in_transaction, "the fixture failed to open a transaction"

        self._journal_from_bare(tmp_path, conn)
        conn.close()

        rollback = self._rollback_line(tmp_path)
        assert rollback["in_transaction"] is True, rollback
        assert rollback["rollback_ok"] is True, rollback

    def test_an_unreadable_in_transaction_is_null_and_never_false(
        self, tmp_path
    ):
        """Unreadable resolves to None, never to a value -- the repo
        convention, and here it is the difference between "no transaction was
        open" and "we could not look". A closed connection is one of the
        states this path exists to survive, and `in_transaction` raises on
        it."""
        closed = db.init_db(tmp_path / "cockpit.db")
        closed.close()
        self._journal_from_bare(tmp_path, closed)

        rollback = self._rollback_line(tmp_path)
        assert rollback["in_transaction"] is None, rollback
        assert rollback["rollback_ok"] is False, rollback
        assert "closed database" in (rollback["rollback_error"] or ""), rollback

    def test_the_rollback_line_is_not_counted_as_a_failure(self, tmp_path):
        """It carries no `pass_number`, so counting it would inflate the
        population tally the previous class exists to keep honest -- the same
        defect the diagnosis line had before it was given its own section."""
        conn = db.init_db(tmp_path / "cockpit.db")
        db.record_loop_failure_durably(
            conn, db_path=tmp_path / "cockpit.db",
            journal_path=tmp_path / "loop_failures.jsonl", failed_ms=NOW,
            pass_number=1, consecutive_failures=1, error="x", pass_kind="full",
            exc=RuntimeError("x"),
        )
        conn.close()

        sections = _read(tmp_path / "cockpit.db", "-n", "10")
        population = _section(sections, POPULATION)
        assert population["row_count"] == 1, sections
        assert "1 journalled" in population["title"], population["title"]
        assert _section(sections, CURE)["row_count"] == 1, sections

    def test_a_line_written_before_the_kind_field_is_still_classified(
        self, tmp_path
    ):
        """Hand-written on purpose, against this file's own fixture rule: the
        shape under test is the one the current writer can no longer produce,
        and it is every one of the 22 lines the live journal holds today.
        Classifying by key-absence is the fallback kept for exactly these."""
        db_path = tmp_path / "cockpit.db"
        db.init_db(db_path).close()
        (tmp_path / "loop_failures.jsonl").write_text(
            json.dumps({
                "ms": NOW, "pass_number": 9, "consecutive_failures": 1,
                "pass_kind": "full", "error": "old shape", "traceback": None,
            })
            + "\n"
            + json.dumps({"ms": NOW, "diagnosis": "old diagnosis"})
            + "\n",
            encoding="utf-8",
        )

        sections = _read(db_path, "-n", "10")
        population = _section(sections, POPULATION)
        assert population["row_count"] == 1, sections
        assert "1 journalled" in population["title"], population["title"]
        assert _section(sections, DIAGNOSIS)["row_count"] == 1, sections
        assert _section(sections, CURE)["row_count"] == 0, sections

    def test_an_empty_cure_section_says_the_failures_predate_the_field(
        self, tmp_path
    ):
        """`walk-log`'s rule, in the direction that flatters. Zero
        observations beside 22 failures must not read as "no rollback was
        attempted" -- every failure ever journalled attempted one."""
        db_path = tmp_path / "cockpit.db"
        db.init_db(db_path).close()
        (tmp_path / "loop_failures.jsonl").write_text(
            json.dumps({
                "ms": NOW, "pass_number": 9, "consecutive_failures": 1,
                "pass_kind": "full", "error": "old shape", "traceback": None,
            }) + "\n",
            encoding="utf-8",
        )

        title = _section(_read(db_path, "-n", "10"), CURE)["title"]
        assert "0 observations" in title, title
        assert "1 failures predate the field" in title, title
        assert "no rollback was attempted" in title, title

    def test_the_cure_section_states_the_reading_order_and_its_limit(
        self, tmp_path
    ):
        """Without this sentence a reader takes `rollback_ok = True` as "the
        connection was cured", which is the overstatement the field was added
        to prevent rather than to create."""
        conn = db.init_db(tmp_path / "cockpit.db")
        db.record_loop_failure_durably(
            conn, db_path=tmp_path / "cockpit.db",
            journal_path=tmp_path / "loop_failures.jsonl", failed_ms=NOW,
            pass_number=1, consecutive_failures=1, error="x", pass_kind="full",
            exc=RuntimeError("x"),
        )
        conn.close()

        title = _section(_read(tmp_path / "cockpit.db"), CURE)["title"]
        assert "READ in_transaction FIRST" in title, title
        assert "no-op that always succeeds" in title, title
        assert "NEITHER FIELD NAMES THE HOLDER" in title, title

    def test_the_cure_is_joined_to_what_the_row_attempt_did_next(
        self, tmp_path
    ):
        """The cross-tab is the whole point: the same two booleans mean "the
        rollback worked" beside `recorded` and "the cure did not cure" beside
        `journal_only`. Either column alone answers neither."""
        conn = self._bare_connection(tmp_path)
        db_path = self._journal_from_bare(tmp_path, conn)
        conn.close()

        cure = _section(_read(db_path, "-n", "10"), CURE)
        assert cure["columns"][-1] == "then", cure["columns"]
        assert "journal_only" in json.dumps(cure["rows"][0]), cure["rows"][0]

    def test_the_diagnosis_earns_the_not_poisoned_sentence_rather_than_asserting_it(
        self, tmp_path
    ):
        """It used to end "This is not the poisoned-connection case." on every
        both-refused line, which is true only in the branch where nothing was
        open on the shared connection. Here that branch holds, so the sentence
        is earned."""
        conn = self._bare_connection(tmp_path)
        assert not conn.in_transaction
        db_path = self._journal_from_bare(tmp_path, conn)
        conn.close()

        row = json.dumps(_section(_read(db_path), DIAGNOSIS)["rows"][0])
        assert "No transaction was open on the shared connection" in row, row
        assert "not the poisoned-connection case" in row, row

    def test_a_refused_rollback_says_the_shared_connection_is_not_excluded(
        self, tmp_path
    ):
        """The branch the old wording got backwards. A connection that will
        not even roll back is the LEAST excluded thing on the machine -- and
        the sentence that shipped for two days said the opposite."""
        closed = db.init_db(tmp_path / "cockpit.db")
        closed.close()
        db_path = self._journal_from_bare(tmp_path, closed)

        row = json.dumps(_section(_read(db_path), DIAGNOSIS)["rows"][0])
        assert "NOT excluded as the holder" in row, row
        assert "not the poisoned-connection case" not in row, row

    def test_an_open_transaction_that_rolled_back_is_not_fully_excluded(
        self, tmp_path
    ):
        """The middle branch, and the reason `rollback_ok` alone is not the
        answer: rollback clears the open transaction and cannot reset a stale
        read snapshot, so the shared connection stays a candidate."""
        conn = self._bare_connection(tmp_path)
        conn.execute("CREATE TABLE t (a INTEGER)")
        conn.commit()
        conn.execute("INSERT INTO t (a) VALUES (1)")
        db_path = self._journal_from_bare(tmp_path, conn)
        conn.close()

        row = json.dumps(_section(_read(db_path), DIAGNOSIS)["rows"][0])
        assert "stale read snapshot survives a rollback" in row, row
        assert "not fully excluded" in row, row
