"""`/api/window`'s freshness read never walks `odds_snapshots`; every read of it
is a covering seek bound to ONE event, and the set of events comes from
`odds_fixtures`.

WHY THIS EXISTS
---------------
`odds/timing.py::fixture_freshness` is the dominant continuous read on the live
box. Replayed read-only on live 2026-09-10 with every statement timed,
`window_status` took **0.95 s, of which 0.91 s was its one `GROUP BY
odds_event_id` over `odds_snapshots`** -- and `/api/window` is fetched on load
by four server-rendered pages, polled every 3 s for 30 s and then every 10 s by
`RefreshWhenPriced`, polled by `Nav.tsx` on every visible tab, and called by
`run_loop.py`. `docs/measurements/2026-09-10-the-ladder-floor-oom-cycles-the-recorder.md`
section 7.

v41 (`idx_odds_window`) made both arms of that statement covering, 5.1x-6.1x
at live's shape. It did not make them SMALL: the `latest` CTE still walked the
whole `market = 'h2h'` prefix of the index -- every h2h row ever stored -- to
find the few hundred fixtures with `commence_ms >= now`, and the walk grew
with every sweep. By the evening of 2026-09-17, with the NFL and NCAAF
weekends inside the 48 h horizon, `/api/window` measured **7 s at the median
and tripped the 25 s read budget twice**, and every server-rendered page waits
on it (`docs/measurements/2026-09-18-the-window-route-walked-every-odds-row.md`).

v47 (`odds_fixtures`) changes the SHAPE: the fixtures come from a one-row-per-
fixture table a trigger keeps, and each fixture's freshness is two seeks on
`odds_snapshots` with `odds_event_id` bound. The index from v41 still serves
both seeks and is still required.

WHAT THIS ESTABLISHES
---------------------
That the statement `fixture_freshness` actually runs -- read out of its own
source, not retyped here -- plans as (a) a range seek on `odds_fixtures`, and
(b) covering seeks on **every** reference to `odds_snapshots`, each with
`odds_event_id` bound, so no read of the snapshot table is proportional to
anything but the fixture count; that the trigger keeps `odds_fixtures` in step
with raw inserts, latest sweep winning; that the v47 step backfills a volume
that predates the table; that v41's index carries every snapshot column the
statement names and a migration puts it on a volume that predates it; and that
the recorded justification beside the `CREATE INDEX` is still there.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Nothing about the live win.** The v47 rehearsal at live's shape is in
  `scripts/measure_odds_fixtures.py` and its ADR; the v41 rehearsal is
  3,904 ms -> 667..797 ms, paired ratio **5.1x - 6.1x across every cache
  regime this box can produce** (`scripts/measure_window_index.py`). Live is
  I/O-bound against a >6 GB file, so a local ratio is a floor and a direction,
  never a magnitude -- v39's local 3x returned 81x on live. Only a post-deploy
  timing settles it. Nothing here is a stopwatch: a timing assertion on a
  shared machine is a flake, and the property this buys is the *shape* of the
  plan, which is deterministic.
- **Nothing about growth of `odds_snapshots`.** It still has no retention rule
  (`store/retention.py` says so itself). v47 makes the window's reads
  independent of that growth; it does not stop it.
- **Nothing about a moved kickoff.** `odds_fixtures` carries the latest
  quoted kickoff per fixture where the old DISTINCT listed every distinct
  one; the schema comment records the choice and no test here exercises it.

A NOTE ON HOW THESE ASSERTIONS ARE WRITTEN
------------------------------------------
Three tests went red on v39 and all three were pinning implementation names
rather than claims -- including one that could not have failed at all, because
`"idx_odds_event" in step` is a substring of `idx_odds_event_commence`. So the
plan assertions below are about the *claim* (every read of `odds_snapshots` is
a covering seek with the event bound, and the skip-scan is gone), and where a
name is unavoidable it is matched as a whole token or by set membership, never
with `in` on a string. `test_the_index_name_cannot_be_matched_by_accident`
checks that property of this file's own assertions.
"""

from __future__ import annotations

import ast
import inspect
import pathlib
import re
import sqlite3
import time

import pytest

from backend.odds import timing
from backend.store import db as store

REPO = pathlib.Path(__file__).resolve().parents[1]
SCHEMA = REPO / "backend" / "store" / "schema.sql"

INDEX = "idx_odds_window"
FIXTURE_INDEX = "idx_odds_fixtures_commence"
TRIGGER = "trg_odds_fixtures_upsert"
NOW = 1_789_000_000_000
VERSION = 41
FIXTURES_VERSION = 47

# The statement `fixture_freshness` ran from v41 until v47, kept here as the
# ORACLE for the rewrite: on any slate the new statement must return exactly
# what this one returned. Retyped on purpose -- it no longer exists in the
# source to be read from.
V41_STATEMENT = (
    "WITH latest AS ("
    "  SELECT odds_event_id, MAX(fetched_ms) AS m FROM odds_snapshots"
    "  WHERE market = ? AND commence_ms >= ? GROUP BY odds_event_id"
    ") "
    "SELECT MIN(COALESCE(o.book_updated_ms, o.fetched_ms)) AS oldest_ms "
    "FROM odds_snapshots o JOIN latest l "
    "  ON o.odds_event_id = l.odds_event_id AND o.fetched_ms = l.m "
    "WHERE o.market = ? GROUP BY o.odds_event_id"
)
V41_UPCOMING = (
    "SELECT sport_key, commence_ms FROM ("
    "  SELECT DISTINCT sport_key, odds_event_id, commence_ms"
    "  FROM odds_snapshots WHERE commence_ms >= ? AND commence_ms <= ?"
    ")"
)


def _statement_from_source() -> str:
    """The SQL `fixture_freshness` executes, read out of the function itself.

    Not retyped here, and deliberately not approximated by a substring search.
    A plan guard against a statement nobody runs is the drift `tasks/lessons.md`
    records. Parsing the call is what keeps the two in step: if the statement
    changes shape, this test plans the NEW one and the assertions below fail
    for the right reason.
    """
    tree = ast.parse(inspect.getsource(timing.fixture_freshness).lstrip())
    found = [
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "execute"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    ]
    assert len(found) == 1, (
        "`fixture_freshness` no longer contains exactly one literal "
        f"`conn.execute(...)`; found {len(found)}. This guard now plans "
        "something other than what the route runs."
    )
    return found[0]


SQL = _statement_from_source()
PARAMS = ("h2h", "h2h", NOW)


def _seed(conn: sqlite3.Connection) -> None:
    """A slate the planner has something to choose across.

    Half the fixtures upcoming and half already commenced, three markets, six
    books and eight sweeps per fixture -- so `market` is genuinely selective,
    `commence_ms` genuinely discards rows, and there is more than one
    `fetched_ms` per event for the MAX to pick between. On an empty table
    SQLite full-scans whatever is cheapest and the plan says nothing.
    """
    rows = []
    for e in range(60):
        eid = f"evt{e:029x}"          # live's event ids are 32 characters
        commence = NOW + (e - 30) * 3_600_000
        for sweep in range(8):
            fetched = NOW - sweep * 600_000
            for book in range(6):
                for market in ("h2h", "spreads", "batter_home_runs"):
                    rows.append((
                        eid, "baseball_mlb", commence, f"H{e}", f"A{e}",
                        f"book{book}", market, fetched,
                        None if book == 5 else fetched - book * 1_000,
                        f"H{e}", 1.9,
                    ))
    conn.executemany(
        "INSERT INTO odds_snapshots (odds_event_id, sport_key, commence_ms, "
        "home_team, away_team, bookmaker, market, fetched_ms, book_updated_ms, "
        "outcome_name, price_decimal) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    conn.execute("ANALYZE")
    conn.commit()


def _plan(conn: sqlite3.Connection, sql: str = SQL) -> list[str]:
    return [r[3] for r in conn.execute("EXPLAIN QUERY PLAN " + sql, PARAMS)]


def _snapshot_steps(plan: list[str]) -> list[str]:
    """The plan lines that read `odds_snapshots`: by the aliases the statement
    gives it AND by the bare table name, which the planner prints for a read
    with no alias -- the v41 CTE arm was one, and a matcher that only knew
    the aliases let it through (mutation (f) in the ADR)."""
    return [s for s in plan if re.match(r"SEARCH (odds_snapshots|o|s) ", s)]


def _indexes(conn: sqlite3.Connection) -> set[str]:
    return {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        )
    }


def _triggers(conn: sqlite3.Connection) -> set[str]:
    return {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger'"
        )
    }


@pytest.fixture
def conn(tmp_path):
    c = store.init_db(tmp_path / "window.db")
    _seed(c)
    yield c
    c.close()


class TestEveryReadOfTheSnapshotsIsASeekOnOneEvent:
    """The claim, stated as the claim: no read of `odds_snapshots` is a table
    fetch, and none of them is unbounded in the event. The second half is
    what v47 bought and v41 had not: a covering walk of every h2h row ever
    stored is still a walk."""

    def test_every_read_of_odds_snapshots_is_covering(self, conn):
        """Mutation observed red: `DROP INDEX idx_odds_window`.

        Both correlated arms fall back to `idx_odds_event` and one of them
        stops being covering (`book_updated_ms` is not in that index).
        """
        steps = _snapshot_steps(_plan(conn))
        assert len(steps) == 2, _plan(conn)
        for step in steps:
            assert "COVERING INDEX" in step, (
                "a read of odds_snapshots still fetches from the table: "
                f"{step}"
            )

    def test_every_read_of_odds_snapshots_binds_the_event(self, conn):
        """The v47 claim. Mutation observed red: put `V41_STATEMENT` back in
        `fixture_freshness` -- its CTE arm plans as `(market=?)` alone, a walk
        of the whole market prefix, which is the 7 s shape of 2026-09-17."""
        steps = _snapshot_steps(_plan(conn))
        assert steps, _plan(conn)
        for step in steps:
            assert "odds_event_id=?" in step, (
                "a read of odds_snapshots is not bound to one event, so it "
                f"grows with the table instead of the slate: {step}"
            )

    def test_the_fixtures_come_from_the_fixture_table_by_kickoff(self, conn):
        """The driving read is a range seek on `odds_fixtures.commence_ms`,
        and nothing in the plan is a SCAN. Mutation observed red: `DROP INDEX
        idx_odds_fixtures_commence` -- the outer read becomes `SCAN f`."""
        plan = _plan(conn)
        outer = [s for s in plan if s.startswith("SEARCH f ")]
        assert len(outer) == 1, plan
        assert "commence_ms>?" in outer[0], outer
        assert not any(s.startswith("SCAN") for s in plan), plan

    def test_the_market_filter_is_a_seek_and_not_a_skip_scan(self, conn):
        """`ANY(odds_event_id)` is SQLite saying it is skip-scanning an index
        whose leading column the query does not constrain. Mutation observed
        red on v41: drop the index; the `ANY(...)` returns."""
        plan = _plan(conn)
        assert not any("ANY(" in step for step in plan), plan

    def test_the_index_is_chosen_by_name_for_both(self, conn):
        """Matched as a whole token, not with `in` on the joined plan, so a
        future index whose name merely contains this one cannot satisfy it."""
        token = re.compile(r"\b%s\b" % re.escape(INDEX))
        steps = _snapshot_steps(_plan(conn))
        assert steps and all(token.search(s) for s in steps), _plan(conn)

    def test_a_column_outside_the_index_would_demote_the_arm(self, conn):
        """The real failure mode: the statement and the index drift apart.

        Not a mutation of production code but a demonstration against the same
        table, so the demotion this file exists to catch is visible rather than
        asserted. `bookmaker` is not in the index; filtering on it costs the
        covering read.
        """
        widened = SQL.replace(
            "WHERE o.market = ? AND o.odds_event_id = f.odds_event_id",
            "WHERE o.market = ? AND o.odds_event_id = f.odds_event_id "
            "AND o.bookmaker <> 'nobody'",
        )
        assert widened != SQL, "the statement changed shape; fix this guard"
        plan = _plan(conn, widened)
        outer = [s for s in plan if s.startswith("SEARCH o ")]
        assert outer and all("COVERING" not in s for s in outer), (
            "referencing a column outside the index was supposed to cost the "
            f"covering read, but the plan still says: {plan}"
        )


class TestTheRewriteAnswersWhatV41Answered:
    """The oracle: the v41 statement, retyped, over the same seeded slate.
    Any fixture the old statement listed the new one lists, with the same
    age, and the schedule sees the same kickoffs per sport."""

    def test_fixture_freshness_matches_the_v41_statement(self, conn):
        old = sorted(
            NOW - int(r[0])
            for r in conn.execute(V41_STATEMENT, ("h2h", NOW, "h2h"))
        )
        assert old, "the oracle answered nothing; the seed is wrong"
        assert timing.fixture_freshness(conn, now_ms=NOW) == old

    def test_upcoming_fixtures_match_the_v41_statement(self, conn):
        horizon = 48 * 3_600_000
        old: dict[str, list[int]] = {}
        for r in conn.execute(V41_UPCOMING, (NOW, NOW + horizon)):
            old.setdefault(r[0], []).append(int(r[1]))
        assert old, "the oracle answered nothing; the seed is wrong"
        new = timing.upcoming_fixtures_by_sport(
            conn, now_ms=NOW, horizon_ms=horizon
        )
        assert {k: sorted(v) for k, v in new.items()} == {
            k: sorted(v) for k, v in old.items()
        }

    def test_a_fixture_with_no_h2h_rows_is_left_out_as_before(self, conn):
        """The old join dropped it; the new scalar subquery aggregates it to
        NULL and the caller must drop the NULL rather than turn it into an
        age of `now`. Mutation observed red: remove the `is not None` filter
        in `fixture_freshness` -- `int(None)` raises."""
        conn.execute(
            "INSERT INTO odds_snapshots (odds_event_id, sport_key, commence_ms, "
            "home_team, away_team, bookmaker, market, fetched_ms, "
            "book_updated_ms, outcome_name, price_decimal) "
            "VALUES ('spreads-only', 'baseball_mlb', ?, 'H', 'A', 'book0', "
            "'spreads', ?, NULL, 'H', 1.9)",
            (NOW + 3_600_000, NOW),
        )
        conn.commit()
        assert "spreads-only" in {
            r[0] for r in conn.execute("SELECT odds_event_id FROM odds_fixtures")
        }
        old = sorted(
            NOW - int(r[0])
            for r in conn.execute(V41_STATEMENT, ("h2h", NOW, "h2h"))
        )
        assert timing.fixture_freshness(conn, now_ms=NOW) == old


class TestTheFixtureTableIsKeptByTheDatabase:
    """A trigger, not a writer: every path that inserts a snapshot keeps the
    table right without being told to -- `store_quotes`, `seed_demo`, and the
    raw INSERTs every test in this suite uses."""

    def _insert(self, conn, *, event, commence, fetched, sport="baseball_mlb"):
        conn.execute(
            "INSERT INTO odds_snapshots (odds_event_id, sport_key, commence_ms, "
            "home_team, away_team, bookmaker, market, fetched_ms, "
            "book_updated_ms, outcome_name, price_decimal) "
            "VALUES (?, ?, ?, 'H', 'A', 'book0', 'h2h', ?, NULL, 'H', 1.9)",
            (event, sport, commence, fetched),
        )
        conn.commit()

    def _fixture(self, conn, event):
        return conn.execute(
            "SELECT sport_key, commence_ms, last_fetched_ms FROM odds_fixtures "
            "WHERE odds_event_id = ?",
            (event,),
        ).fetchone()

    def test_a_raw_insert_creates_the_fixture_row(self, tmp_path):
        """Mutation observed red: delete the trigger from `schema.sql`."""
        conn = store.init_db(tmp_path / "t.db")
        assert TRIGGER in _triggers(conn)
        self._insert(conn, event="e1", commence=NOW + 1, fetched=NOW)
        row = self._fixture(conn, "e1")
        assert tuple(row) == ("baseball_mlb", NOW + 1, NOW)
        conn.close()

    def test_the_latest_sweep_wins_whatever_order_rows_arrive_in(self, tmp_path):
        """A postponed game moves to its new kickoff on the next sweep that
        quotes it, and a late-arriving OLD row cannot move it back.
        Mutation observed red: drop the trigger's `WHERE excluded.last_fetched_ms
        >= ...` clause -- the older row then overwrites the newer."""
        conn = store.init_db(tmp_path / "t.db")
        self._insert(conn, event="e1", commence=NOW + 1, fetched=NOW)
        self._insert(conn, event="e1", commence=NOW + 2, fetched=NOW + 10)
        assert tuple(self._fixture(conn, "e1")) == ("baseball_mlb", NOW + 2, NOW + 10)
        self._insert(conn, event="e1", commence=NOW + 3, fetched=NOW - 10)
        assert tuple(self._fixture(conn, "e1")) == ("baseball_mlb", NOW + 2, NOW + 10)
        conn.close()

    def test_one_row_per_fixture_however_many_snapshots(self, conn):
        n_events = conn.execute(
            "SELECT COUNT(DISTINCT odds_event_id) FROM odds_snapshots"
        ).fetchone()[0]
        n_fixtures = conn.execute("SELECT COUNT(*) FROM odds_fixtures").fetchone()[0]
        assert n_events == n_fixtures == 60


class TestAVolumeThatPredatesTheFixtureTableGetsItBackfilled:
    """Tested against `migrate`, not against `init_db`, for the reason the
    v41 class below records: `init_db` runs `executescript(schema.sql)` after
    `migrate`, which would create the empty table and the trigger with the
    step deleted. What only the step can do is seed the table from rows the
    trigger never saw, and that is what is asserted."""

    def _wound_back(self, tmp_path):
        """A database at v46 carrying snapshots for three fixtures: one two
        days out, one that kicked off yesterday, one from a month ago. The
        backfill's floor is seven real days before now, so the clock here is
        the wall clock and not `NOW`."""
        conn = store.init_db(tmp_path / "old.db")
        now = int(time.time() * 1000)
        day = 86_400_000
        for event, commence in (
            ("soon", now + 2 * day),
            ("yesterday", now - day),
            ("last-month", now - 30 * day),
        ):
            for fetched in (now - 3 * day, now - 2 * day):
                conn.execute(
                    "INSERT INTO odds_snapshots (odds_event_id, sport_key, "
                    "commence_ms, home_team, away_team, bookmaker, market, "
                    "fetched_ms, book_updated_ms, outcome_name, price_decimal) "
                    "VALUES (?, 'americanfootball_nfl', ?, 'H', 'A', 'book0', "
                    "'h2h', ?, NULL, 'H', 1.9)",
                    (event, commence, fetched),
                )
        conn.execute("DROP TRIGGER %s" % TRIGGER)
        conn.execute("DROP TABLE odds_fixtures")
        store._set_meta(conn, "schema_version", str(FIXTURES_VERSION - 1))  # noqa: SLF001
        conn.commit()
        assert FIXTURE_INDEX not in _indexes(conn), "fixture did not wind back"
        return conn, now

    def test_the_step_seeds_upcoming_and_recent_fixtures_and_not_history(
        self, tmp_path
    ):
        """Mutation observed red: delete the step from `_MIGRATIONS`.

        `migrate` then returns without this version and the SELECT below
        fails on a missing table.
        """
        conn, now = self._wound_back(tmp_path)

        applied = store.migrate(conn)

        assert FIXTURES_VERSION in applied, applied
        assert FIXTURE_INDEX in _indexes(conn)
        rows = {
            r[0]: (r[1], r[2])
            for r in conn.execute(
                "SELECT odds_event_id, commence_ms, last_fetched_ms "
                "FROM odds_fixtures"
            )
        }
        assert set(rows) == {"soon", "yesterday"}, rows
        assert rows["soon"] == (now + 2 * 86_400_000, 0)
        conn.close()

    def test_the_step_is_a_no_op_on_a_database_that_already_has_it(
        self, tmp_path
    ):
        """The version stamp is written only after every step succeeds, so a
        crash between the CREATE and the stamp re-runs this step whole on the
        next boot. `IF NOT EXISTS` and `OR IGNORE` are what make that
        survivable, and a re-run must not clobber a row the trigger has since
        moved."""
        conn = store.init_db(tmp_path / "current.db")
        now = int(time.time() * 1000)
        conn.execute(
            "INSERT INTO odds_snapshots (odds_event_id, sport_key, commence_ms, "
            "home_team, away_team, bookmaker, market, fetched_ms, "
            "book_updated_ms, outcome_name, price_decimal) "
            "VALUES ('e1', 'baseball_mlb', ?, 'H', 'A', 'book0', 'h2h', ?, "
            "NULL, 'H', 1.9)",
            (now + 3_600_000, now),
        )
        store._set_meta(conn, "schema_version", str(FIXTURES_VERSION - 1))  # noqa: SLF001
        conn.commit()
        before = conn.execute(
            "SELECT commence_ms, last_fetched_ms FROM odds_fixtures "
            "WHERE odds_event_id = 'e1'"
        ).fetchone()
        assert tuple(before) == (now + 3_600_000, now)

        applied = store.migrate(conn)               # must not raise

        assert FIXTURES_VERSION in applied, applied
        after = conn.execute(
            "SELECT commence_ms, last_fetched_ms FROM odds_fixtures "
            "WHERE odds_event_id = 'e1'"
        ).fetchone()
        assert tuple(after) == tuple(before), "the re-run clobbered a live row"
        conn.close()

    def test_the_step_declares_the_index_it_leaves_behind(self):
        step = store._MIGRATIONS[FIXTURES_VERSION]            # noqa: SLF001
        assert step.indexes == (FIXTURE_INDEX,)
        assert any(FIXTURE_INDEX in s for s in step.statements)

    def test_the_undo_drops_the_trigger_as_well_as_the_table(self):
        """SQLite validates every trigger on a table before it will `DROP
        COLUMN` from it, so an undo that drops the table and leaves the
        trigger naming it strands every older step's undo behind it
        (`test_store.py::_v1_database` walks them all). The ORDER of the two
        drops does not matter -- both were tried -- only that both happen.
        Mutation observed red in `test_store.py`: delete the `DROP TRIGGER`."""
        undo = store._MIGRATIONS[FIXTURES_VERSION].undo_statements  # noqa: SLF001
        kinds = {s.split()[1] for s in undo}
        assert kinds == {"TRIGGER", "TABLE"}, undo


class TestTheIndexCarriesWhatTheStatementNeeds:
    def test_it_is_there_on_a_fresh_database(self, conn):
        assert INDEX in _indexes(conn)

    def test_its_columns_are_pinned_and_cover_what_the_statement_names(self, conn):
        """Every snapshot column `fixture_freshness` references is in the
        index, in the order the seeks need.

        `market` leads because it is the only equality both arms share with
        nothing narrower; `odds_event_id` is the bound event; `fetched_ms` is
        the inner MAX and the outer equality; `book_updated_ms` is the outer
        MIN's payload. `commence_ms` is carried but, since v47, not named by
        this statement: it was the v41 CTE's range filter. It stays because
        dropping a column rebuilds a ~260 MB index on the live volume at boot,
        which is a timed decision of its own (ADR 0141), not a tidy-up.
        """
        cols = [r[2] for r in conn.execute("PRAGMA index_info(%s)" % INDEX)]
        assert cols == [
            "market", "odds_event_id", "fetched_ms", "commence_ms",
            "book_updated_ms",
        ]
        referenced = {
            c for c in (
                "market", "odds_event_id", "fetched_ms", "book_updated_ms",
            ) if re.search(r"\b[os]\.%s\b" % c, SQL)
        }
        assert referenced == {
            "market", "odds_event_id", "fetched_ms", "book_updated_ms",
        }, "the statement stopped naming a column this index was built for"
        assert referenced <= set(cols)

    def test_fetched_ms_is_descending_like_the_index_beside_it(self, conn):
        """`idx_odds_event` orders `fetched_ms DESC` and serves the runner's
        latest-sweep reads. Matching that keeps the two interchangeable for
        those, so this index is an addition rather than a quiet regression of
        `runner.book_quotes_for_event`."""
        sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
            (INDEX,),
        ).fetchone()[0]
        assert "fetched_ms DESC" in sql, sql

    def test_it_does_not_replace_the_indexes_it_sits_beside(self, conn):
        """An addition, never a substitution: v39's index still serves the
        parlay candidate scan's `MIN(commence_ms)`, and `idx_odds_event` still
        leads with the event."""
        names = _indexes(conn)
        assert {"idx_odds_event", "idx_odds_event_commence",
                "idx_odds_commence", "idx_odds_sport_commence"} <= names


class TestAVolumeThatPredatesTheIndexGetsIt:
    """Tested against `migrate`, not against `init_db`.

    `init_db` runs `migrate` and then `executescript(schema.sql)`, and
    `schema.sql` carries the same `CREATE INDEX IF NOT EXISTS` -- so a test
    that winds the stamp back, calls `init_db` and asserts the index is present
    passes with the step deleted. That is the decoration v39's file records
    having written first. Calling `migrate` directly is what puts the step
    under test.
    """

    def test_the_step_creates_the_index_on_a_database_that_lacks_it(
        self, tmp_path
    ):
        """Mutation observed red: delete the step from `_MIGRATIONS`.

        `migrate` then returns without this version, the index stays absent,
        and both assertions fail.
        """
        conn = store.init_db(tmp_path / "old.db")
        conn.execute("DROP INDEX %s" % INDEX)
        store._set_meta(conn, "schema_version", str(VERSION - 1))  # noqa: SLF001
        conn.commit()
        assert INDEX not in _indexes(conn), "fixture did not wind back"

        applied = store.migrate(conn)

        assert VERSION in applied, applied
        assert INDEX in _indexes(conn)
        conn.close()

    def test_the_step_is_a_no_op_on_a_database_that_already_has_it(
        self, tmp_path
    ):
        """The version stamp is written only after every step succeeds, so a
        crash between the CREATE and the stamp re-runs this step whole on the
        next boot. `IF NOT EXISTS` is what makes that survivable."""
        conn = store.init_db(tmp_path / "current.db")
        store._set_meta(conn, "schema_version", str(VERSION - 1))  # noqa: SLF001
        conn.commit()
        assert INDEX in _indexes(conn)

        applied = store.migrate(conn)               # must not raise

        assert VERSION in applied, applied
        assert INDEX in _indexes(conn)
        conn.close()

    def test_the_step_declares_the_index_it_leaves_behind(self):
        """`scripts/migrate_db.py` verifies by name at boot off this tuple. A
        step whose `indexes` is empty passes that boot check having created
        nothing -- declared rather than parsed, for the reason
        `_Migration.indexes` records."""
        step = store._MIGRATIONS[VERSION]            # noqa: SLF001
        assert step.indexes == (INDEX,)
        assert any(INDEX in s for s in step.statements)

    def test_the_schema_version_covers_the_step(self):
        assert store.SCHEMA_VERSION >= FIXTURES_VERSION


class TestTheRecordedReasonSurvives:
    """The guard that actually prevents the repeat.

    `idx_odds_event_commence` was removed in 2026-08 by someone reasoning
    correctly from `EXPLAIN QUERY PLAN`, and it cost the desk 503s two weeks
    later (ADR 0141). The defence is not the index -- `migrate_db.py` already
    refuses to boot without it -- it is the measurement written beside it. An
    index whose justification has been deleted is one somebody removes again on
    the same argument as last time.
    """

    def test_the_schema_records_the_rehearsed_timing(self):
        """The whole table, verbatim, and not a list of figures.

        **This guard was written as a list of figures first and it was
        decoration** -- observed, not reasoned. Deleting the three-line timing
        table left it green, because `3,904 ms` also appears two paragraphs
        down in the sentence about page-cache residency, and `in` on the file
        cannot tell the two apart. Same shape as the `idx_odds_event`
        substring trap this file's header records: an assertion satisfied by
        text other than the text it is guarding.
        """
        src = SCHEMA.read_text(encoding="utf-8")
        assert (
            "--     before   3,904 ms  ..  4,399 ms\n"
            "--     after      667 ms  ..    797 ms\n"
            "--     paired ratio, median to median   5.5x .. 6.1x\n"
        ) in src, "the rehearsal's timing table was deleted or reworded"
        assert "5.1x - 6.1x across" in src, (
            "the span across cache regimes was lost; without it the reader "
            "has one number and no idea how much it moves"
        )

    def test_the_schema_records_that_the_timing_was_paired(self):
        """The design, not just the digits.

        The same query over the same data read 1,283 ms in one session and
        3,904 ms in the next, on page-cache residency alone. A single-arm
        timing on this box is not evidence, and a future reader re-running it
        needs to know that before trusting a number they take sequentially.
        """
        src = SCHEMA.read_text(encoding="utf-8")
        assert "ALTERNATELY in one process" in src
        assert "the ratio is not" in src
        assert "5.1x - 6.1x across" in src
        assert "not a baseline" in src

    def test_the_schema_records_why_the_fixture_table_exists(self):
        """The v47 reason, beside the CREATE TABLE: that the window's reads
        used to grow with every sweep, that the table is kept by a trigger
        and not a writer, and that the backfill is bounded. Delete any of the
        three and the next tidy-up removes the table on the argument that
        `odds_snapshots` already has every column in it."""
        src = SCHEMA.read_text(encoding="utf-8")
        assert "Maintained by the trigger below, not by a writer" in src
        assert "The v47 backfill is bounded, not complete" in src
        assert "tripped the 25 s read budget twice" in src

    def test_the_schema_records_that_the_number_is_a_floor(self):
        """v39's local 3x returned 81x on live. A benchmark that differs from
        production in which resource binds gives a direction and a floor, never
        a magnitude -- and the file has to say which one it has, because 5x and
        81x justify different amounts of risk."""
        src = SCHEMA.read_text(encoding="utf-8")
        assert "5.1x low end is a FLOOR on the live win" in src, (
            "pinned with the qualifier, because v39's own comment further up "
            "this same file also says 'FLOOR on the live win' -- a bare "
            "assertion for that phrase is satisfied by another index's "
            "justification and cannot fail when this one is deleted"
        )
        assert "which resource binds" in src

    def test_the_schema_records_the_cost_it_is_paying(self):
        """A benefit recorded without its cost is half an argument, and this
        one is 263 MB on a box that has OOM-killed the recorder."""
        src = SCHEMA.read_text(encoding="utf-8")
        for figure in ("71.2 bytes/row", "263 MB on live's 3,696,485",
                       "24.9 ms -> 40.7 ms"):
            assert figure in src, f"the cost record lost {figure}"
        assert "cache-pressure objection" in src

    def test_the_schema_records_what_the_cheaper_form_costs(self):
        """Recorded as a live option with a price, not as a rejected idea.

        The four-column form is 25 MB smaller, cheaper to write, and slower by
        2-9% consistently across four cache regimes. That is a small enough
        margin that the record has to carry the whole comparison -- and has to
        name dropping `book_updated_ms` as the first thing to give back if live
        shows memory pressure, rather than leaving a future session to
        re-derive it.

        **The per-regime table is pinned verbatim, not the `2-9%` summary**:
        that figure appears twice in the comment, so an assertion for it
        survives deleting the measurement it summarises. Two guards in this
        file were decoration for exactly that reason before the mutation run
        caught them.
        """
        src = SCHEMA.read_text(encoding="utf-8")
        assert "four-column form is the 25 MB question" in src
        assert "64.6 bytes/row" in src
        assert (
            "--                    2 MB cache   16 MB cache   64 MB cache"
            "   5-arm run\n"
            "--     five-column       713 ms       697 ms        702 ms"
            "        764 ms\n"
            "--     four-column       741 ms       765 ms        736 ms"
            "        783 ms\n"
        ) in src, "the per-regime comparison was deleted or reworded"
        # The table's reading, pinned with enough context to be unique: bare
        # `2-9%` appears twice in the comment and would survive deleting this.
        assert "and small in size**: 2-9% on the" in src, (
            "the table is still there but what it means was deleted; a reader "
            "should not have to re-derive 'consistent in direction, small in "
            "size' from six numbers"
        )
        assert "first thing to give back" in src

    def test_the_schema_records_why_v39s_index_cannot_serve_this_query(self):
        """The obvious objection -- "there is already an index on this table"
        -- answered in place, so it does not have to be re-answered."""
        src = SCHEMA.read_text(encoding="utf-8")
        assert "cannot help here" in src

    def test_the_schema_declares_the_statement_verbatim(self):
        src = SCHEMA.read_text(encoding="utf-8")
        assert (
            "CREATE INDEX IF NOT EXISTS idx_odds_window\n"
            "    ON odds_snapshots(market, odds_event_id, fetched_ms DESC, "
            "commence_ms,\n                      book_updated_ms);" in src
        )


def test_the_index_name_cannot_be_matched_by_accident():
    """This file's own assertions, checked for the trap that made three v39
    guards vacuous.

    `"idx_odds_event" in plan` is satisfied by `idx_odds_event_commence`, so a
    test written that way could not fail whichever index the planner chose. The
    property that makes a name assertion meaningful is that no other index name
    on this table contains it and it contains no other -- asserted here rather
    than assumed, because the next index added to `odds_snapshots` is exactly
    when it would stop being true.
    """
    src = SCHEMA.read_text(encoding="utf-8")
    others = set(re.findall(r"CREATE INDEX IF NOT EXISTS (\w+)\s*\n?\s*ON "
                            r"odds_snapshots", src)) - {INDEX}
    assert others, "no sibling indexes found; this guard stopped checking"
    for name in others:
        assert INDEX not in name, (
            f"{name} contains {INDEX}; a substring assertion on the plan "
            "would be satisfied by the wrong index"
        )
        assert name not in INDEX, (
            f"{INDEX} contains {name}; an assertion for {name} elsewhere "
            "would now be satisfied by this index"
        )


def test_every_phrase_the_reason_guards_pin_occurs_exactly_once():
    """No guard above can be satisfied by prose other than the prose it guards.

    **Two guards in this file were decoration and the mutation run is what
    said so.** Deleting the three-line timing table left
    `test_the_schema_records_the_rehearsed_timing` green, because `3,904 ms`
    also appears two paragraphs down in the sentence about page-cache
    residency. Deleting the four-column comparison left its guard green for the
    same reason: `2-9%` appears twice. And `FLOOR on the live win` appears in
    v39's comment further up the same file, so a bare assertion for it could
    not fail when THIS index's justification was deleted -- it would be
    satisfied by a different index's.

    That is the `idx_odds_event` substring trap in a new costume: an assertion
    that passes off the wrong occurrence. This test closes the class rather
    than the three instances -- it reads every string literal the guards above
    compare with `in`, and requires each to appear exactly once in
    `schema.sql`. Adding a guard on a phrase that already appears twice fails
    here, at the moment it is written, instead of silently passing forever.
    """
    tree = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))
    guards = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and node.name == "TestTheRecordedReasonSurvives"
    )
    pinned: set[str] = set()
    for node in ast.walk(guards):
        if (isinstance(node, ast.Compare)
                and isinstance(node.ops[0], ast.In)
                and isinstance(node.left, ast.Constant)
                and isinstance(node.left.value, str)):
            pinned.add(node.left.value)
        # `for figure in (...)` loops pin each element the same way.
        if isinstance(node, ast.For) and isinstance(node.iter, ast.Tuple):
            pinned.update(
                elt.value for elt in node.iter.elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            )
    assert len(pinned) >= 10, (
        f"only {len(pinned)} pinned phrases found; this test stopped reading "
        "the guards it is supposed to check"
    )
    src = SCHEMA.read_text(encoding="utf-8")
    duplicated = {p: src.count(p) for p in pinned if src.count(p) != 1}
    assert not duplicated, (
        "these guarded phrases do not appear exactly once in schema.sql, so "
        "the assertion can be satisfied by the wrong occurrence (or by none): "
        f"{duplicated}"
    )
