"""The candidate scan runs off a covering index, and does not sort.

**What this establishes.** That `runner.MATCH_CANDIDATE_SQL`, run against a
database built by `store.db.init_db`, produces a query plan that reads
`idx_odds_sport_commence` as a COVERING index and builds no temp B-tree for the
DISTINCT -- and that the migration puts that index on a volume that predates it.

**What it does NOT establish.** Nothing about speed. There is no timing
assertion here and there should not be: a stopwatch on a shared machine is a
flake, and the property actually bought by ADR 0086 is the *shape* of the plan,
which is deterministic. The milliseconds live in
`docs/measurements/2026-08-30-the-candidate-scan-index.md`, taken by
`scripts/measure_odds_scan_index.py`.

It also establishes nothing about growth. The index changes the constant;
`odds_snapshots` still has no retention rule, so the scan still grows.

**Why a plan assertion is the right guard.** The failure this catches is not
"someone deleted the index" -- `scripts/migrate_db.py` already refuses to boot
on that. It is the quieter one: a column added to the SELECT list and not to
the index, which leaves every test green, leaves the index in place, and
silently demotes the plan to a table fetch per row plus a sort. That is
invisible in every other check this repo runs.

**SQLite chooses the plan, so this is also a version guard.** A future SQLite
that stops using the covering form would fail here rather than on the live box
at 22:06Z.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.runner import MATCH_CANDIDATE_SQL
from backend.store import db

NOW = 1_788_000_000_000
INDEX = "idx_odds_sport_commence"

# Enough rows, across two sports, that the planner has something to choose
# between. With an empty table SQLite will happily full-scan whatever is
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
                    NOW, NOW - 5_000, sport, f"{sport}-{i % 40}",
                    NOW + (i % 40) * 3_600_000, f"H{i % 40}", f"A{i % 40}",
                    "pinnacle", "h2h", f"H{i % 40}", None, None, 1.9,
                ),
            )
    conn.commit()
    conn.execute("ANALYZE")
    conn.commit()


def _plan(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        "EXPLAIN QUERY PLAN " + MATCH_CANDIDATE_SQL,
        ("baseball_mlb", NOW - 86_400_000),
    ).fetchall()
    return " | ".join(r[3] for r in rows)


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "plan.db")
    _seed(c)
    yield c
    c.close()


class TestTheScanIsCoveredAndDoesNotSort:
    def test_the_plan_reads_the_covering_index(self, conn):
        """Mutation observed red: `DROP INDEX idx_odds_sport_commence` first.

        The plan falls back to `SEARCH ... USING INDEX idx_odds_commence
        (commence_ms>?)`, which is the shape that reached 27.7s on live.
        """
        plan = _plan(conn)
        assert "COVERING INDEX" in plan, plan
        assert INDEX in plan, plan

    def test_the_distinct_builds_no_temp_btree(self, conn):
        """The half a narrow `(sport_key, commence_ms)` index would not buy.

        Mutation observed red twice: once by dropping the index, and once by
        replacing it with the two-column form -- which restricts the seek and
        leaves this assertion failing, because the projected columns are not in
        it and the DISTINCT still has to sort.
        """
        plan = _plan(conn)
        assert "TEMP B-TREE" not in plan, plan

    def test_a_column_outside_the_index_would_demote_the_plan(self, conn):
        """The actual failure mode: the SELECT list and the index drift apart.

        Not a mutation of production code but a demonstration against the same
        table, so the demotion this file exists to catch is visible rather than
        asserted. `bookmaker` is not in the index; adding it to the projection
        costs the covering read.
        """
        widened = MATCH_CANDIDATE_SQL.replace(
            "SELECT DISTINCT odds_event_id",
            "SELECT DISTINCT bookmaker, odds_event_id",
        )
        rows = conn.execute(
            "EXPLAIN QUERY PLAN " + widened,
            ("baseball_mlb", NOW - 86_400_000),
        ).fetchall()
        plan = " | ".join(r[3] for r in rows)
        assert "COVERING INDEX" not in plan, (
            "adding a column outside the index was supposed to cost the "
            f"covering read, but the plan still says: {plan}"
        )

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
        assert "SELECT DISTINCT" not in source, (
            "the candidate SQL was re-inlined into `_match_candidates`; the "
            "plan guard now describes a statement nothing executes"
        )


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
