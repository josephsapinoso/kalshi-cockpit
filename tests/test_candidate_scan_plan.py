"""`runner.MATCH_CANDIDATE_SQL` reads `odds_fixtures`, never `odds_snapshots`.

**What this establishes.** That the candidate scan the recorder runs once per
sport per pass plans as a seek on the fixture table (one row per fixture,
schema v47), builds no temp B-tree, and touches the snapshot table not at
all; that it answers exactly what the pre-v47 statement answered on a seeded
slate; that the statement planned here is the one `_match_candidates`
executes; and that the v31 index the statement used to depend on is still
put on a volume that predates it, because two other reads still use it.

**Why the shape changed (2026-09-18, ADR 0167).** From v31 the statement was
`SELECT DISTINCT odds_event_id, commence_ms, home_team, away_team FROM
odds_snapshots WHERE sport_key = ? AND commence_ms >= ?`, covered by
`idx_odds_sport_commence` -- a contiguous index walk, which was the fix for
the 27.7 s table walk of 2026-08-30. Covered is not small: it walked every
stored row of every fixture in the range, every pass, and `candidate_ms` in
`loop-rss` grew with every sweep. `odds_fixtures` carries these four columns
once per fixture, so the read is proportional to the fixtures.

**Why a plan assertion is the right guard.** There is no stopwatch here: a
timing on a shared machine is a flake, and the property this buys is the
shape, which is deterministic. The failure it catches is someone pointing the
statement back at the snapshot table (or joining to it) for a column the
fixture table lacks -- which reads as a one-line convenience and is the walk
coming back. The equivalence test is the other half: the rewrite must answer
what the old statement answered, or the speed is not the only thing that
changed.

**SQLite chooses the plan, so this is also a version guard.** A future SQLite
that plans this differently fails here first.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.runner import MATCH_CANDIDATE_SQL
from backend.store import db

NOW = 1_788_000_000_000
INDEX = "idx_odds_sport_commence"
PARAMS = ("baseball_mlb", NOW - 86_400_000)

# The statement as it ran from v31 to v47, retyped on purpose: it no longer
# exists in the source to be read from, and it is the ORACLE for the rewrite.
V31_SQL = (
    "SELECT DISTINCT odds_event_id, commence_ms, home_team, away_team "
    "FROM odds_snapshots WHERE sport_key = ? AND commence_ms >= ?"
)

# Enough rows, across two sports and several sweeps, that the planner has
# something to choose between and the DISTINCT in the oracle has duplicates
# to collapse. With an empty table SQLite will happily full-scan whatever is
# cheapest and the plan says nothing about the design.
_SPORTS = ("baseball_mlb", "basketball_wnba")


def _seed(conn: sqlite3.Connection, per_sport: int = 400) -> None:
    for sport in _SPORTS:
        for i in range(per_sport):
            conn.execute(
                "INSERT INTO odds_snapshots (fetched_ms, book_updated_ms, "
                "sport_key, odds_event_id, commence_ms, home_team, away_team, "
                "bookmaker, market, outcome_name, outcome_description, "
                "outcome_point, price_decimal) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    NOW - (i % 5) * 600_000, NOW - 5_000, sport,
                    f"{sport}-{i % 40}",
                    NOW + (i % 40) * 3_600_000 - 12 * 3_600_000,
                    f"H{i % 40}", f"A{i % 40}",
                    "pinnacle", "h2h", f"H{i % 40}", None, None, 1.9,
                ),
            )
    conn.commit()
    conn.execute("ANALYZE")
    conn.commit()


def _plan(conn: sqlite3.Connection, sql: str = MATCH_CANDIDATE_SQL) -> str:
    rows = conn.execute("EXPLAIN QUERY PLAN " + sql, PARAMS).fetchall()
    return " | ".join(r[3] for r in rows)


def _indexes(conn: sqlite3.Connection) -> set[str]:
    return {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        )
    }


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "plan.db")
    _seed(c)
    yield c
    c.close()


class TestTheScanReadsTheFixtureTableAndDoesNotSort:
    def test_the_plan_reads_the_fixture_table_and_never_the_snapshots(self, conn):
        """Mutation observed red: put `V31_SQL` back as `MATCH_CANDIDATE_SQL`
        -- the plan names `odds_snapshots` and this fails on the first
        assertion."""
        plan = _plan(conn)
        assert "odds_fixtures" in plan, plan
        assert "odds_snapshots" not in plan, plan

    def test_the_read_is_a_seek_and_not_a_scan(self, conn):
        """Mutation observed red: `DROP INDEX idx_odds_fixtures_commence` --
        the plan becomes `SCAN odds_fixtures`. A scan of a few hundred rows
        is cheap today; the guard is that nobody has to re-measure that."""
        plan = _plan(conn)
        assert plan.startswith("SEARCH"), plan
        assert "SCAN" not in plan, plan

    def test_the_read_builds_no_temp_btree(self, conn):
        """No DISTINCT, no sort: one row per fixture is the table's own
        invariant (its primary key), not something the query has to
        establish. Mutation observed red: `V31_SQL` back -- the DISTINCT
        over the snapshot rows sorts."""
        assert "TEMP B-TREE" not in _plan(conn), _plan(conn)

    def test_it_answers_what_the_v31_statement_answered(self, conn):
        """The oracle. Five sweeps of the same fixtures collapse to one row
        each under the old DISTINCT and are one row each in the table.
        Mutation observed red: delete the trigger from `schema.sql` -- the
        table is empty and the new statement returns nothing."""
        old = sorted(tuple(r) for r in conn.execute(V31_SQL, PARAMS))
        new = sorted(tuple(r) for r in conn.execute(MATCH_CANDIDATE_SQL, PARAMS))
        assert old, "the oracle answered nothing; the seed is wrong"
        assert new == old

    def test_a_moved_kickoff_is_one_candidate_at_the_latest_time(self, conn):
        """The one place the rewrite deliberately differs from the oracle,
        stated so nobody reads it as a regression: the feed moves a game,
        the DISTINCT used to list both kickoffs, the table lists the latest.
        Mutation observed red: drop the trigger's `WHERE excluded.last_fetched_ms
        >= ...` clause AND insert the older row last -- the stale kickoff wins."""
        conn.execute(
            "INSERT INTO odds_snapshots (fetched_ms, book_updated_ms, sport_key, "
            "odds_event_id, commence_ms, home_team, away_team, bookmaker, market, "
            "outcome_name, price_decimal) VALUES (?, ?, 'baseball_mlb', "
            "'baseball_mlb-0', ?, 'H0', 'A0', 'pinnacle', 'h2h', 'H0', 1.9)",
            (NOW + 10, NOW, NOW + 30 * 3_600_000),
        )
        conn.commit()
        old = [r for r in conn.execute(V31_SQL, PARAMS) if r[0] == "baseball_mlb-0"]
        new = [r for r in conn.execute(MATCH_CANDIDATE_SQL, PARAMS) if r[0] == "baseball_mlb-0"]
        assert len(old) == 2, old
        assert [tuple(r) for r in new] == [
            ("baseball_mlb-0", NOW + 30 * 3_600_000, "H0", "A0")
        ], new

    def test_the_statement_the_runner_runs_is_the_one_planned_here(self):
        """There is one copy of the SQL, and this is the assertion that says so.

        `_match_candidates` executes `MATCH_CANDIDATE_SQL` by name. If someone
        re-inlines a literal there, the plan asserted above stops describing the
        statement the pass issues -- evidence about SQL nobody runs, which is
        the drift `tasks/lessons.md` records and the reason
        `_SQL_PARLAY_CANDIDATES` is pinned the same way.
        """
        import inspect

        from backend import runner

        source = inspect.getsource(runner._match_candidates)
        assert "MATCH_CANDIDATE_SQL" in source, source
        assert "SELECT " not in source, (
            "the candidate SQL was re-inlined into `_match_candidates`; the "
            "plan guard now describes a statement nothing executes"
        )

    def test_the_fixture_table_carries_exactly_the_columns_the_scan_names(self, conn):
        """The column list is the table's column list, the way it used to be
        the index's: a column added to the statement that the table lacks is
        a join back to the snapshots waiting to happen."""
        cols = {r[1] for r in conn.execute("PRAGMA table_info(odds_fixtures)")}
        for name in ("odds_event_id", "commence_ms", "home_team", "away_team", "sport_key"):
            assert name in cols, (name, cols)


class TestAVolumeThatPredatesTheIndexGetsIt:
    """The v31 step, tested against `migrate` rather than against `init_db`.

    **This class was written the obvious way first and the obvious way was
    decoration.** The first version wound a database back to v30, called
    `init_db`, and asserted the index was present. It passes with the v31 step
    deleted -- observed, not reasoned -- because `init_db` runs `migrate` and
    then `executescript(schema.sql)`, and `schema.sql` carries the same
    `CREATE INDEX IF NOT EXISTS`. So the assertion was satisfied by the schema
    file whatever the migration did.

    That is worth stating rather than quietly fixing, because it is the same
    shape as the lesson already in `tasks/lessons.md`: the test named the
    migration and did not exercise it. Calling `migrate` directly is what makes
    the step the only thing under test.

    It also means something true about production that the ADR says out loud:
    **`schema.sql` alone would put this index on the live volume.** The step
    exists so `scripts/migrate_db.py` verifies at boot, by name, that it is
    actually there -- and so the shape change carries a version stamp.
    """

    def test_the_step_creates_the_index_on_a_database_that_lacks_it(self, tmp_path):
        """Mutation observed red: delete the v31 step from `_MIGRATIONS`.

        Then `migrate` returns `[]`, the index stays absent, and both
        assertions below fail -- which is what the first version of this test
        did not do.

        The "old" database is built by dropping the index from a current one
        rather than by keeping an old schema file around, the same construction
        the wind-back fixture in `tests/test_store.py` uses: every other part
        of the shape comes from the current schema, so it cannot drift away
        from what v30 was in any respect but this change.
        """
        path = tmp_path / "old.db"
        conn = db.init_db(path)
        conn.execute(f"DROP INDEX {INDEX}")
        db._set_meta(conn, "schema_version", "30")             # noqa: SLF001
        conn.commit()

        assert INDEX not in self._indexes(conn), "fixture did not wind back"

        applied = db.migrate(conn)

        assert 31 in applied, applied
        assert INDEX in self._indexes(conn)
        conn.close()

    def test_the_step_is_a_no_op_on_a_database_that_already_has_it(self, tmp_path):
        """Re-running must be safe: a step interrupted mid-way re-runs whole.

        The version stamp is written only after every step succeeds, so any
        crash between the `CREATE INDEX` and the stamp leaves a database that
        will run this step again on the next boot. `IF NOT EXISTS` is what
        makes that survivable, and this is the assertion that it is there.
        """
        path = tmp_path / "current.db"
        conn = db.init_db(path)
        db._set_meta(conn, "schema_version", "30")             # noqa: SLF001
        conn.commit()

        assert INDEX in self._indexes(conn)
        applied = db.migrate(conn)                # must not raise

        assert 31 in applied, applied
        assert INDEX in self._indexes(conn)
        conn.close()

    def test_the_step_declares_the_index_it_leaves_behind(self):
        """`scripts/migrate_db.py` verifies by name at boot, off this tuple.

        A step whose `indexes` is empty passes that boot check while having
        created nothing, which is the failure the declaration exists to make
        visible. Declared rather than parsed out of the SQL, for the reason
        `_Migration.indexes` records.
        """
        assert db._MIGRATIONS[31].indexes == (INDEX,)          # noqa: SLF001

    @staticmethod
    def _indexes(conn: sqlite3.Connection) -> set[str]:
        return {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
