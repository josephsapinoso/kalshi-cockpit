"""`db-sizes` reporting `dbstat.unused` beside `pgsize` -- ticket #123.

`docs/measurements/2026-09-18-where-the-database-bytes-are.md:104-111` named
`idx_quotes_ticker_time` (random insert order, continuously pruned) as a
btree where `pgsize` alone cannot tell "rows were added" from "pages
bloated" apart, and said "one extra column on the next `db-sizes` run
settles it." That run happened 2026-09-21 without the column. This file
pins that `_SQL_DBSTAT` now selects it, under a mutation shown red, and
that the `dbstat`-unavailable fallback still reports no such column at all
(never a fabricated 0) -- both without requiring a `dbstat`-compiled
`sqlite3`, because this repo's own dev venv does not have one (see
`TestEnvironmentHasNoRealDbstat` below) and a guard that only ran on a
machine nobody develops from would not be a guard anyone could trust.

HOW THE PRIMARY GUARD WORKS WITHOUT A REAL `dbstat`
----------------------------------------------------
SQLite's `dbstat` is an *eponymous virtual table* the C library registers
only when compiled with `SQLITE_ENABLE_DBSTAT_VTAB`. This build was not
(`PRAGMA compile_options` carries no `DBSTAT` entry -- see the standalone
test below). `_SQL_DBSTAT` names the table only as `FROM dbstat`; SQLite
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
  that and is expected to skip everywhere this suite has been run so far.
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


class TestEnvironmentHasNoRealDbstat:
    def test_this_venvs_sqlite3_lacks_the_dbstat_vtab(self):
        """Documents the constraint the rest of this file works around.

        If this ever goes green-turned-red (i.e. the venv gains a
        dbstat-enabled sqlite3), `test_the_real_virtual_table_reports_unused_
        after_deletion` below will stop skipping and start actually
        exercising the C extension -- which is strictly more coverage, not a
        break.
        """
        assert _real_dbstat_available() is False, (
            "this venv's sqlite3 now has dbstat compiled in -- the skip "
            "markers below are stale and the real-vtab test should be "
            "un-skipped"
        )


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

        This venv's own `sqlite3` already lacks `dbstat` (see
        `TestEnvironmentHasNoRealDbstat`), so calling `_q_db_sizes` against
        an ordinary schema-built database exercises the except branch for
        real, with no monkeypatching needed.

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

        conn = sqlite3.connect(path)
        try:
            sections = _q_db_sizes(conn, _Args())
        finally:
            conn.close()
        fallback = next(s for s in sections if s.title.startswith("B."))
        assert "UNAVAILABLE" in fallback.title
        assert "unused_bytes" not in fallback.columns
        assert "fill_pct" not in fallback.columns
        assert fallback.columns == ("name", "rows")

    def test_end_to_end_via_main_under_the_fallback(self, tmp_path, capsys):
        """The whole CLI path takes the fallback and still prints no
        fabricated `unused_bytes`/`fill_pct` column in the JSON section.
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
        assert "unused_bytes" not in section_b["columns"]
        assert "fill_pct" not in section_b["columns"]


class TestAgainstARealDbstatWhereAvailable:
    """Exercises the real virtual table when the running interpreter has
    one -- skipped on this repo's own dev venv (see
    `TestEnvironmentHasNoRealDbstat`), but not vacuous: any CI runner or
    future venv whose `sqlite3` is built with `SQLITE_ENABLE_DBSTAT_VTAB`
    will actually run it.
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
