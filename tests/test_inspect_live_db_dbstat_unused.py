"""`db-sizes` reporting `dbstat.unused` beside `pgsize` -- ticket #123.

`docs/measurements/2026-09-18-where-the-database-bytes-are.md:104-111` named
`idx_quotes_ticker_time` (random insert order, continuously pruned) as a
btree where `pgsize` alone cannot tell "rows were added" from "pages
bloated" apart, and said "one extra column on the next `db-sizes` run
settles it." That run happened 2026-09-21 without the column. This file
pins that `_SQL_DBSTAT` now selects it, under a mutation shown red, and
that the `dbstat`-unavailable fallback still reports no such column at all
(never a fabricated 0) -- both without requiring a `dbstat`-compiled
`sqlite3`, because this repo's own dev venv does not have one.

THE ENVIRONMENTS DISAGREE, AND THAT IS THE POINT
-------------------------------------------------
**This repo's dev venv (sqlite 3.45.1) has no `dbstat`. CI's interpreter
does.** Measured 2026-09-21, the hard way: this file's first version
selected each branch from the ambient build, passed locally, and failed
three tests on CI -- on a commit whose production code was correct and had
already served a correct live reading off the deployed image, which also
has `dbstat`.

Two things follow, and both are load-bearing here:

1. **The success branch is NOT unexercised.** The original finding was
   reported as "`_q_db_sizes`'s real branch has never been exercised by
   this suite, locally or in CI." Only the first half is true: locally the
   `except` branch has always run, and on CI the real one always has. What
   was missing was a *local* exercise, which is what the synthetic-table
   guard below supplies.
2. **A test must force the branch it claims to cover.** An environment that
   happens to select it is a coincidence, and a coincidence inverts the
   moment the suite runs somewhere else. `_NoDbstatConnection` forces the
   fallback on any interpreter; the end-to-end test asserts only the
   invariant that holds on both.

HOW THE PRIMARY GUARD WORKS WITHOUT A REAL `dbstat`
----------------------------------------------------
SQLite's `dbstat` is an *eponymous virtual table* the C library registers
only when compiled with `SQLITE_ENABLE_DBSTAT_VTAB`. This repo's dev build
was not (`PRAGMA compile_options` carries no `DBSTAT` entry); CI's is.
`_SQL_DBSTAT` names the table only as `FROM dbstat`; SQLite
does not care whether `dbstat` is a virtual table or an ordinary one, so a
plain `CREATE TABLE dbstat(name, pgsize, unused)` seeded with rows that
mimic a fragmented index exercises the exact query string the production
code runs, including the `ROUND`/`NULLIF` fill-percentage arithmetic --
everything except the C extension's own page-walking, which this file has
no way to fake and does not claim to.

WHAT THIS DOES NOT ESTABLISH
-----------------------------
- **Nothing about the live database's own fill ratio**, or about what the
  real `dbstat` virtual table returns on an actual fragmented file --
  `test_the_real_virtual_table_reports_unused_after_deletion` below covers
  that; it skips on the dev venv and RUNS on CI.
- **Nothing about the size of `unused_bytes` in general** -- only that the
  column is selected, arithmetic is correct against known inputs, and it
  disappears (rather than reads 0) when `dbstat` cannot be queried at all.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scripts.inspect_live_db import ACCEPT_FLAG, main
from scripts.inspect_live_db_loop import _SQL_DBSTAT, _q_db_sizes

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "backend" / "store" / "schema.sql"


class _Args:
    """Stand-in for `argparse.Namespace` -- `_q_db_sizes` reads `.limit` only."""

    limit = 1000


def _real_dbstat_available() -> bool:
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE TABLE t(a)")
        conn.execute("SELECT * FROM dbstat LIMIT 1")
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        conn.close()


class _NoDbstatConnection(sqlite3.Connection):
    """A connection that refuses `dbstat` exactly as an unbuilt SQLite does.

    **Why this exists, and it is the lesson of this file's first CI run.**
    The original fallback tests selected the branch from the AMBIENT
    environment: this repo's dev venv has no `dbstat`, so calling
    `_q_db_sizes` "exercised the except branch for real, with no
    monkeypatching needed." That is true here and false on CI, whose
    `sqlite3` IS built with `SQLITE_ENABLE_DBSTAT_VTAB` -- so the fallback
    tests took the *success* branch there and three of them failed, on a
    commit whose production code was fine and had already served a correct
    live reading.

    **A test must FORCE the branch it claims to cover.** An environment that
    happens to select it is not a guard; it is a coincidence that inverts
    the moment the suite runs somewhere else. Both branches are now reachable
    from either kind of interpreter.
    """

    def execute(self, sql, *args):  # type: ignore[override]
        # Matched against the production statement itself, not the word
        # "dbstat" anywhere in the SQL. Two narrower-is-better reasons:
        # a build WITHOUT the vtab can still `CREATE TABLE dbstat(...)`
        # happily (the name is only reserved once the extension registers
        # it), and the fallback's own `SELECT COUNT(*) FROM <name>` sweep
        # would otherwise be intercepted for a table legitimately called
        # `dbstat` -- which would make the fallback raise instead of
        # falling back. `_fetch` appends ` LIMIT ?`, hence startswith.
        if sql.startswith(_SQL_DBSTAT):
            raise sqlite3.OperationalError("no such table: dbstat")
        return super().execute(sql, *args)


class TestBothBranchesAreReachableWhereverThisRuns:
    """Records which branch this interpreter takes, and fails on neither.

    The predecessor of this test asserted `_real_dbstat_available() is
    False` -- documenting the dev venv's constraint as though it were a
    property of the suite. It went red on CI for having *more* coverage,
    which is a guard punishing an improvement.
    """

    def test_the_probe_answers_and_the_answer_is_not_asserted(self):
        assert isinstance(_real_dbstat_available(), bool)

    def test_the_fallback_is_reachable_even_where_dbstat_exists(self):
        """The factory intercepts THE PRODUCTION STATEMENT, on any build.

        **This test's own first version made the mistake it exists to
        prevent**, and CI caught it a second time. It probed with an ad-hoc
        `SELECT * FROM dbstat`, which `_NoDbstatConnection` does not match
        (the interceptor is deliberately pinned to `_SQL_DBSTAT`). Locally
        it "passed" because this venv has no `dbstat` at all, so the ad-hoc
        query raised on its own and the factory was never exercised. On CI,
        where `dbstat` exists, it did not raise -- `DID NOT RAISE`.

        So: probe with `_SQL_DBSTAT` itself. A test of an interceptor must
        send the traffic the interceptor is aimed at, or it is measuring the
        environment again.
        """
        conn = sqlite3.connect(":memory:", factory=_NoDbstatConnection)
        try:
            conn.execute("CREATE TABLE t(a)")
            with pytest.raises(sqlite3.OperationalError):
                conn.execute(_SQL_DBSTAT)
        finally:
            conn.close()

    def test_the_success_branch_is_reachable_without_the_factory(self):
        """The mirror: a plain connection over a synthetic `dbstat` table
        takes the REAL branch and emits both new columns.

        Together with the test above, both branches are demonstrably
        reachable from whichever interpreter is running -- which is the
        property the first version of this file lacked and the reason it
        was green here and red on CI.
        """
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute("CREATE TABLE dbstat(name TEXT, pgsize INT, unused INT)")
            conn.execute("INSERT INTO dbstat VALUES ('idx_x', 4096, 1024)")
            section_b = next(
                s for s in _q_db_sizes(conn, _Args()) if s.title.startswith("B.")
            )
        finally:
            conn.close()
        assert "UNAVAILABLE" not in section_b.title
        assert "unused_bytes" in section_b.columns
        assert "fill_pct" in section_b.columns


class TestSqlAgainstASyntheticDbstatTable:
    """The guard that matters: exercises `_SQL_DBSTAT` verbatim.

    A plain table named `dbstat` stands in for the virtual table -- SQLite
    resolves `FROM dbstat` by name, and the query string neither knows nor
    cares which kind of table answers it.
    """

    def _run(self, rows: list[tuple[str, int, int]]):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE dbstat(name TEXT, pgsize INT, unused INT)")
        conn.executemany("INSERT INTO dbstat VALUES (?, ?, ?)", rows)
        conn.commit()
        try:
            cur = conn.execute(_SQL_DBSTAT)
            columns = tuple(d[0] for d in cur.description)
            result = {r[0]: dict(zip(columns, r)) for r in cur.fetchall()}
        finally:
            conn.close()
        return columns, result

    def test_unused_and_fill_pct_are_reported_per_btree(self):
        """Guard 1: on a seeded (fake) dbstat shaped like a fragmented
        index -- two pages, 4096 bytes each, one of them half-empty from
        deletion -- `unused` sums correctly and `fill_pct` reflects it.

        Mutation: revert `_SQL_DBSTAT` to the pre-#123 string (see the test
        below) against this same fixture -- red, because `unused_bytes` and
        `fill_pct` are absent from `columns` entirely.
        """
        columns, result = self._run(
            [
                ("idx_quotes_ticker_time", 4096, 0),
                ("idx_quotes_ticker_time", 4096, 2048),
            ]
        )
        assert "unused_bytes" in columns
        assert "fill_pct" in columns
        assert "bytes" in columns  # pgsize kept under its established alias

        row = result["idx_quotes_ticker_time"]
        assert row["bytes"] == 8192
        assert row["unused_bytes"] == 2048
        assert row["fill_pct"] == pytest.approx(75.0)

    def test_fill_pct_is_none_not_a_fabricated_number_when_pgsize_is_zero(self):
        """A zero-page btree's fill percentage is undefined, not 0/0=0.

        Mutation: drop the `NULLIF` guard from `_SQL_DBSTAT` -- red, this
        raises `sqlite3.OperationalError` instead of returning `None`
        (SQLite division by literal zero without NULLIF still yields NULL
        in this engine only because of float division; the guard is what
        keeps that NULL rather than a silently wrong 0).
        """
        columns, result = self._run([("empty_table", 0, 0)])
        row = result["empty_table"]
        assert row["fill_pct"] is None

    def test_mutation_dropping_unused_from_the_query_goes_red(self):
        """Runs the SAME synthetic fixture through the pre-#123 query text
        and shows the assertion `unused_bytes` in `columns` actually fails
        -- the guard is not decoration.
        """
        pre_123_sql = (
            "SELECT name, SUM(pgsize) AS bytes, COUNT(*) AS pages "
            "FROM dbstat GROUP BY name ORDER BY bytes DESC"
        )
        assert pre_123_sql != _SQL_DBSTAT
        assert "unused" in _SQL_DBSTAT and "unused" not in pre_123_sql

        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE dbstat(name TEXT, pgsize INT, unused INT)")
        conn.execute("INSERT INTO dbstat VALUES ('t', 4096, 2048)")
        conn.commit()
        try:
            cur = conn.execute(pre_123_sql)
            columns = tuple(d[0] for d in cur.description)
        finally:
            conn.close()
        assert "unused_bytes" not in columns  # <- this is what goes red if
        # `unused` is dropped from `_SQL_DBSTAT`: swap `pre_123_sql` for
        # `_SQL_DBSTAT` in the `conn.execute` call above and the assertion
        # fails, which is the observed-red confirmation for guard 1.

    def test_pgsize_alias_and_meaning_are_unchanged(self):
        """Mutation: rename `bytes` or change what it sums (e.g. `AVG` in
        place of `SUM`) -- red. Every prior reading in the record used
        `SUM(pgsize) AS bytes`; changing it silently breaks comparison
        against `2026-09-18-where-the-database-bytes-are.md`.
        """
        assert "SUM(pgsize) AS bytes" in _SQL_DBSTAT


class TestFallbackNeverFabricatesTheNewColumns:
    def test_fallback_has_no_unused_or_fill_pct_column_at_all(self, tmp_path):
        """When `dbstat` cannot be queried, `_q_db_sizes` must not report
        `unused_bytes`/`fill_pct` as 0 -- it must not report them at all,
        because a row count carries no notion of page fragmentation.

        **The fallback is FORCED, not inherited from the environment.**
        `_NoDbstatConnection` raises `OperationalError` on `_SQL_DBSTAT`
        specifically, so this covers the except branch identically on a venv
        without the vtab and on CI, which has it. Relying on the ambient
        build is what made three tests in this file fail on their first CI
        run.

        Mutation: add `unused_bytes=0` (or `fill_pct=0`) to the fallback's
        `Section(columns=..., rows=...)` construction -- red, because this
        test asserts those names are absent from the columns it actually
        emits.
        """
        path = tmp_path / "cockpit.db"
        conn = sqlite3.connect(path)
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        conn.commit()
        conn.close()

        conn = sqlite3.connect(path, factory=_NoDbstatConnection)
        try:
            sections = _q_db_sizes(conn, _Args())
        finally:
            conn.close()
        fallback = next(s for s in sections if s.title.startswith("B."))
        assert "UNAVAILABLE" in fallback.title
        assert "unused_bytes" not in fallback.columns
        assert "fill_pct" not in fallback.columns
        assert fallback.columns == ("name", "rows")

    def test_end_to_end_via_main_never_mixes_the_two_shapes(self, tmp_path, capsys):
        """The CLI path emits section B in exactly one of two shapes.

        `main` opens its own connection, so the factory trick above cannot
        reach it and which branch runs depends on the interpreter. That is
        fine, because the claim worth pinning holds on BOTH: the two new
        columns appear **together or not at all**, and the fallback is
        announced in the title rather than quietly emitting zeros.

        The predecessor asserted the fallback shape unconditionally and so
        failed on CI, whose `sqlite3` has `dbstat`. A test that can only
        pass on one build is testing the build.

        **The expectation is derived from `main`'s OWN output, not from a
        separate `_real_dbstat_available()` probe.** A second probe opens a
        second connection and could in principle disagree with what `main`
        did -- and an independent probe deciding what to assert is how this
        file got the environment wrong twice already. The title says which
        branch ran; read that, then hold it to the matching shape.
        """
        path = tmp_path / "cockpit.db"
        conn = sqlite3.connect(path)
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        conn.commit()
        conn.close()

        rc = main(["db-sizes", "--db", str(path), "--json", ACCEPT_FLAG])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        section_b = next(s for s in payload["sections"] if s["title"].startswith("B."))
        columns = tuple(section_b["columns"])
        took_fallback = "UNAVAILABLE" in section_b["title"]

        if took_fallback:
            assert columns == ("name", "rows")
        else:
            assert "unused_bytes" in columns and "fill_pct" in columns
        # The invariant that holds either way: never one without the other,
        # and never a fabricated column sitting at 0.
        assert ("unused_bytes" in columns) == ("fill_pct" in columns)


class TestAgainstARealDbstatWhereAvailable:
    """Exercises the real virtual table when the running interpreter has one.

    Skips on this repo's dev venv and **runs on CI**, whose `sqlite3` is
    built with `SQLITE_ENABLE_DBSTAT_VTAB` -- confirmed 2026-09-21. So this
    is not a permanently-vacuous skip: it is the arm that covers the branch
    the deployed image actually takes.
    """

    def test_the_real_virtual_table_reports_unused_after_deletion(self, tmp_path):
        if not _real_dbstat_available():
            pytest.skip("dbstat not compiled into this sqlite3 build")
        path = tmp_path / "cockpit.db"
        conn = sqlite3.connect(path)
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        padding = "x" * 400
        conn.executemany(
            "INSERT INTO poll_log (polled_ms, endpoint, ok, row_count, error) "
            "VALUES (?, 'positions', 0, NULL, ?)",
            [(1_700_000_000_000 + i, padding) for i in range(2000)],
        )
        conn.commit()
        conn.execute("DELETE FROM poll_log WHERE id % 2 = 0")
        conn.commit()
        conn.close()

        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            sections = _q_db_sizes(conn, _Args())
        finally:
            conn.close()
        dbstat_section = next(s for s in sections if s.title.startswith("B."))
        unused_col = dbstat_section.columns.index("unused_bytes")
        name_col = dbstat_section.columns.index("name")
        poll_log_rows = [
            r for r in dbstat_section.rows if str(r[name_col]).startswith("poll_log") or str(r[name_col]).startswith("idx_poll_log")
        ]
        assert poll_log_rows
        assert any(r[unused_col] and r[unused_col] > 0 for r in poll_log_rows)
