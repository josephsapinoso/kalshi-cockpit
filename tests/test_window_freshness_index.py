"""`idx_odds_window` exists, covers both arms of `/api/window`, and says why.

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

v39's `idx_odds_event_commence` does not touch it and structurally cannot: the
statement needs `market`, `fetched_ms` and `book_updated_ms` and that index
carries none of the three.

WHAT THIS ESTABLISHES
---------------------
That the statement `fixture_freshness` actually runs -- read out of its own
source, not retyped here -- plans as a COVERING read on **both** references to
`odds_snapshots`, so neither arm touches a table page; that the index carries
every column the statement names; that a migration puts it on a volume that
predates it; and that the recorded justification beside the `CREATE INDEX` is
still there.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Nothing about the live win.** The rehearsal at live's shape is 3,904 ms ->
  667..797 ms, every arm timed alternately in one process, paired ratio
  **5.1x - 6.1x across every cache regime this box can produce**
  (`scripts/measure_window_index.py`). Live is I/O-bound against a 5.19 GB
  file, so the low end is a floor and a direction, never a magnitude -- v39's
  local 3x returned 81x on live. Only a post-deploy timing settles it. Nothing
  here is a stopwatch: a timing assertion on a shared machine is a flake, and
  the property the index buys is the *shape* of the plan, which is
  deterministic. The absolute milliseconds moved 3x between sessions on
  page-cache residency alone while the ratio barely moved, which is why the
  record beside the `CREATE INDEX` is a paired range and not a headline number.
- **Nothing about `USE TEMP B-TREE FOR GROUP BY`, which survives on purpose.**
  The outer GROUP BY drives from the materialized CTE and SQLite does not know
  the CTE is already in `odds_event_id` order. Removing it means rewriting the
  statement, which lives under the `backend/odds/` freeze. It sorts ~800
  fixtures' worth of joined rows, not the table. Asserting its absence here
  would be asserting a property this change did not buy.
- **Nothing about growth.** `odds_snapshots` still has no retention rule
  (`store/retention.py` says so itself), so this changes the constant and
  leaves the growth term alone.

A NOTE ON HOW THESE ASSERTIONS ARE WRITTEN
------------------------------------------
Three tests went red on v39 and all three were pinning implementation names
rather than claims -- including one that could not have failed at all, because
`"idx_odds_event" in step` is a substring of `idx_odds_event_commence`. So the
plan assertions below are about the *claim* (every read of `odds_snapshots` is
a covering seek, and the skip-scan is gone), and where a name is unavoidable it
is matched as a whole token or by set membership, never with `in` on a string.
`test_the_index_name_cannot_be_matched_by_accident` checks that property of
this file's own assertions.
"""

from __future__ import annotations

import ast
import inspect
import pathlib
import re
import sqlite3

import pytest

from backend.odds import timing
from backend.store import db as store

REPO = pathlib.Path(__file__).resolve().parents[1]
SCHEMA = REPO / "backend" / "store" / "schema.sql"

INDEX = "idx_odds_window"
NOW = 1_789_000_000_000

#: **The ordinal is a lane placeholder.** It was taken without reading
#: `schema.sql` or `tasks/LANES.md` because a parallel lane may also be bumping
#: the schema; re-take it at merge alongside `SCHEMA_VERSION` and the
#: `_MIGRATIONS` key. See the note on `store.SCHEMA_VERSION`. Renumbered from
#: 40 to 41: lane D merged first and took 40 (ADR 0143).
VERSION = 41


def _statement_from_source() -> str:
    """The SQL `fixture_freshness` executes, read out of the function itself.

    Not retyped here, and deliberately not approximated by a substring search.
    `backend/odds/timing.py` is frozen, so the statement cannot be lifted into
    a module constant the way `runner.MATCH_CANDIDATE_SQL` was -- and a plan
    guard against a statement nobody runs is the drift `tasks/lessons.md`
    records. Parsing the call is what keeps the two in step: if the statement
    changes shape, this test plans the NEW one and the covering assertions
    below fail for the right reason.
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
PARAMS = ("h2h", NOW, "h2h")


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


def _indexes(conn: sqlite3.Connection) -> set[str]:
    return {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        )
    }


@pytest.fixture
def conn(tmp_path):
    c = store.init_db(tmp_path / "window.db")
    _seed(c)
    yield c
    c.close()


class TestBothArmsReadTheIndexAndNeverTheTable:
    """The claim, stated as the claim: no read of `odds_snapshots` is a table
    fetch. That is what makes 1.46M row fetches per call go away on live, and
    it is a property of the plan rather than of any index name."""

    def test_every_read_of_odds_snapshots_is_covering(self, conn):
        """Mutation observed red: `DROP INDEX idx_odds_window`.

        The plan falls back to `SEARCH odds_snapshots USING INDEX
        idx_odds_event (ANY(odds_event_id) AND market=?)` plus a non-covering
        seek on the outer arm -- both table fetches, which is the 0.91 s shape.
        Also observed red with `book_updated_ms` dropped from the index
        (the outer arm stops being covering) and with `commence_ms` dropped
        (the CTE arm stops being covering).
        """
        steps = [s for s in _plan(conn) if s.startswith("SEARCH")]
        assert len(steps) == 2, _plan(conn)
        for step in steps:
            assert "COVERING INDEX" in step, (
                "a read of odds_snapshots still fetches from the table: "
                f"{step}"
            )

    def test_the_market_filter_is_a_seek_and_not_a_skip_scan(self, conn):
        """`ANY(odds_event_id)` is SQLite saying it is skip-scanning an index
        whose leading column the query does not constrain -- the cost
        `idx_odds_event` was paying here. An index leading with `market` is
        the half of this change that removes it.

        Mutation observed red: drop the index; the `ANY(...)` returns.
        """
        plan = _plan(conn)
        assert not any("ANY(" in step for step in plan), plan

    def test_the_index_is_chosen_by_name_for_both(self, conn):
        """Matched as a whole token, not with `in` on the joined plan, so a
        future index whose name merely contains this one cannot satisfy it."""
        token = re.compile(r"\b%s\b" % re.escape(INDEX))
        steps = [s for s in _plan(conn) if s.startswith("SEARCH")]
        assert all(token.search(s) for s in steps), _plan(conn)

    def test_a_column_outside_the_index_would_demote_both_arms(self, conn):
        """The real failure mode: the statement and the index drift apart.

        Not a mutation of production code but a demonstration against the same
        table, so the demotion this file exists to catch is visible rather than
        asserted. `bookmaker` is not in the index; projecting it costs the
        covering read.
        """
        widened = SQL.replace(
            "SELECT MIN(COALESCE(o.book_updated_ms, o.fetched_ms)) AS oldest_ms",
            "SELECT o.bookmaker, "
            "MIN(COALESCE(o.book_updated_ms, o.fetched_ms)) AS oldest_ms",
        )
        assert widened != SQL, "the statement changed shape; fix this guard"
        plan = _plan(conn, widened)
        outer = [s for s in plan if s.startswith("SEARCH o ")]
        assert outer and all("COVERING" not in s for s in outer), (
            "projecting a column outside the index was supposed to cost the "
            f"covering read, but the plan still says: {plan}"
        )


class TestTheIndexCarriesWhatTheStatementNeeds:
    def test_it_is_there_on_a_fresh_database(self, conn):
        assert INDEX in _indexes(conn)

    def test_its_columns_are_exactly_the_ones_the_statement_names(self, conn):
        """Every column `fixture_freshness` references, and no more.

        Order matters and is asserted with it: `market` leads because it is the
        only equality the CTE has; `odds_event_id` is both GROUP BY keys and
        the join key; `fetched_ms` is the MAX and the outer equality;
        `commence_ms` is the range filter, carried rather than sought because
        it is functionally determined by the event; `book_updated_ms` is the
        outer MIN's payload.
        """
        cols = [r[2] for r in conn.execute("PRAGMA index_info(%s)" % INDEX)]
        assert cols == [
            "market", "odds_event_id", "fetched_ms", "commence_ms",
            "book_updated_ms",
        ]
        referenced = {
            c for c in (
                "market", "odds_event_id", "fetched_ms", "commence_ms",
                "book_updated_ms",
            ) if c in SQL
        }
        assert referenced == set(cols), (
            "the statement and the index no longer name the same columns; "
            f"statement has {sorted(referenced)}, index has {sorted(cols)}"
        )

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
        assert store.SCHEMA_VERSION >= VERSION


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
