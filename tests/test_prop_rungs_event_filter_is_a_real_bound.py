"""`prop-rungs --odds-event-id` now seeks; the obvious fix would not have.

ADR 0157 recorded the defect: the `prop` CTE selects every row of
`odds_snapshots` carrying an `outcome_description`, `latest` groups over that,
and `:event` was applied only at the OUTER level -- so naming a fixture
discarded the other fixtures' rows after everything had already been read. A
flag that looks like a bound and is not one.

**The fix it proposed does not work, and that is the durable part of this
file.** Pushing `(:event IS NULL OR odds_event_id = :event)` down into the CTE
changes no plan whatsoever: SQLite cannot know a parameter's nullity when it
plans the statement, so it must emit a plan correct for NULL, and that plan is
a scan. The old and pushed-down plans are byte-identical -- for a named fixture
AND for no flag.

Worse, the plan of the *unbounded* call already contains

    SEARCH odds_snapshots USING INDEX idx_odds_event_commence (odds_event_id=?)

which is the JOIN on `l.odds_event_id`, not the flag. A reader checking whether
`--odds-event-id` bounds anything sees that line and concludes it does. It is
there with no flag at all.

What seeks is a hard equality, which means two statements rather than one:
`_SQL_PROP_RUNGS` (the registered population, unchanged character for
character) and `_SQL_PROP_RUNGS_ONE_EVENT`, built from one template so they
cannot drift.

WHY THIS NEEDED NO PRE-REGISTRATION
-----------------------------------
`prop-rungs` feeds a registered harness (`scripts/analyze_prop_onesided.py`),
so changing its population is a pre-registration question. This does not change
it: the unfiltered statement is untouched, and for a named fixture the outer
predicate had already discarded every other fixture while `latest` keys
`MAX(fetched_ms)` per `odds_event_id` -- so restricting the CTE cannot move
which `(event, fetched_ms)` pair wins. The equivalence tests below are the
evidence for that, compared against the real predecessor string rather than a
paraphrase.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **The unfiltered call still walks the whole index, deliberately.** A default
  window would change the registered population. Do not run `prop-rungs`
  without `--odds-event-id` on live during a slate.
- **Nothing about live timing.** A plan names the access method, never the rows
  it touches.

Mutations, each observed red:
  1. `_SQL_PROP_RUNGS_ONE_EVENT` built with the OR-form instead of the hard
     equality -- the seek guard goes red, which is the whole point of the file
  2. `_q_prop_rungs` using `_SQL_PROP_RUNGS` for both branches
  3. `latest` grouping globally instead of per `odds_event_id`
  4. dropping the outer `(:event IS NULL OR p.odds_event_id = :event)`
"""

from __future__ import annotations

import importlib
import os
import sqlite3
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

decisions = importlib.import_module("inspect_live_db_decisions")

SCHEMA = os.path.join(
    os.path.dirname(__file__), "..", "backend", "store", "schema.sql"
)

NOW_MS = 1_789_500_000_000

#: The push-down as it was proposed, in the OR-form. Kept so the claim "this
#: would not have worked" is tested rather than asserted.
_SQL_OR_FORM_PUSHDOWN = decisions._PROP_RUNGS_TEMPLATE.format(
    cte_event="    AND (:event IS NULL OR odds_event_id = :event)"
)


class _Args:
    def __init__(self, *, odds_event_id=None, limit=2000):
        self.odds_event_id = odds_event_id
        self.limit = limit


@pytest.fixture
def conn():
    path = os.path.join(tempfile.mkdtemp(), "rungs.db")
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    with open(SCHEMA, encoding="utf-8") as fh:
        c.executescript(fh.read())
    yield c
    c.close()


def _rung(conn, *, event, book, player, point, side, price, fetched_ms):
    conn.execute(
        "INSERT INTO odds_snapshots (odds_event_id, sport_key, commence_ms, "
        "home_team, away_team, bookmaker, market, outcome_name, "
        "outcome_description, outcome_point, price_decimal, fetched_ms) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            event, "baseball_mlb", fetched_ms + 3600_000, "Home", "Away",
            book, "pitcher_strikeouts", side, player, point, price, fetched_ms,
        ),
    )
    conn.commit()


def _both_sides(conn, *, event, book, player, point, fetched_ms, over=1.9):
    _rung(conn, event=event, book=book, player=player, point=point,
          side="Over", price=over, fetched_ms=fetched_ms)
    _rung(conn, event=event, book=book, player=player, point=point,
          side="Under", price=1.95, fetched_ms=fetched_ms)


def _rows(conn, sql, event):
    return [tuple(r) for r in conn.execute(sql, {"event": event})]


def _plan(conn, sql, event):
    return [
        r["detail"]
        for r in conn.execute("EXPLAIN QUERY PLAN " + sql, {"event": event})
    ]


def _scans_the_whole_index(steps):
    """A step that reads the index end to end rather than seeking into it.

    `SCAN ... USING INDEX` is the shape that matters here: it is cheaper than a
    table scan and still touches every entry, which on the largest table on the
    box is the cost ADR 0157 exists to keep off the desk.
    """
    return any(
        s.startswith("SCAN odds_snapshots") for s in steps
    )


@pytest.fixture
def two_fixtures(conn):
    """Two fixtures whose sweeps INTERLEAVE in time.

    Built to punish the wrong answer: fixture B's newest sweep is newer than
    A's, so a `latest` taking a global maximum would erase A entirely. A
    fixture where both sweeps shared a timestamp would pass under that bug.
    """
    _both_sides(conn, event="A", book="fanduel", player="A. Pitcher",
                point=5.5, fetched_ms=NOW_MS - 60_000)
    _both_sides(conn, event="A", book="fanduel", player="A. Pitcher",
                point=5.5, fetched_ms=NOW_MS - 30_000, over=2.0)
    _both_sides(conn, event="B", book="fanduel", player="B. Pitcher",
                point=6.5, fetched_ms=NOW_MS - 10_000)
    _both_sides(conn, event="B", book="draftkings", player="B. Pitcher",
                point=6.5, fetched_ms=NOW_MS - 10_000)
    return conn


class TestTheProposedFixWouldNotHaveWorked:
    """The finding this file exists to pin, so nobody re-proposes it.

    Mutation 1: build `_SQL_PROP_RUNGS_ONE_EVENT` with the OR-form. Both tests
    here go red, because the OR-form's plan is the unbounded plan.
    """

    def test_the_or_form_plans_exactly_like_no_predicate_at_all(
        self, two_fixtures
    ):
        with_or = _plan(two_fixtures, _SQL_OR_FORM_PUSHDOWN, "A")
        without = _plan(two_fixtures, decisions._SQL_PROP_RUNGS, "A")
        assert with_or == without, (with_or, without)

    def test_the_or_form_still_scans_the_whole_index(self, two_fixtures):
        assert _scans_the_whole_index(
            _plan(two_fixtures, _SQL_OR_FORM_PUSHDOWN, "A")
        )

    def test_the_join_supplies_a_seek_line_even_with_no_flag(
        self, two_fixtures
    ):
        """Why the uselessness was invisible: `(odds_event_id=?)` appears in
        the UNBOUNDED plan, from the join on `l.odds_event_id`. A reader
        checking whether the flag bounds anything sees it and is misled."""
        steps = _plan(two_fixtures, decisions._SQL_PROP_RUNGS, None)
        assert any("odds_event_id=?" in s for s in steps), steps
        assert _scans_the_whole_index(steps), steps


class TestTheHardEqualityActuallySeeks:
    """Mutation 1 again, from the other side."""

    def test_naming_a_fixture_seeks_rather_than_scanning(self, two_fixtures):
        steps = _plan(two_fixtures, decisions._SQL_PROP_RUNGS_ONE_EVENT, "A")
        assert not _scans_the_whole_index(steps), steps
        assert any("odds_event_id=?" in s for s in steps), steps

    def test_the_two_statements_differ_only_in_the_cte_predicate(self):
        """If they ever diverge elsewhere, the template has been edited on one
        side and the equivalence tests below stop meaning anything."""
        assert decisions._SQL_PROP_RUNGS_ONE_EVENT.replace(
            "    AND odds_event_id = :event", ""
        ) == decisions._SQL_PROP_RUNGS


class TestTheRegisteredPopulationIsUntouched:
    def test_the_unfiltered_statement_has_no_cte_predicate(self):
        assert decisions._SQL_PROP_RUNGS == (
            decisions._PROP_RUNGS_TEMPLATE.format(cte_event="")
        )
        assert ":event" not in decisions._SQL_PROP_RUNGS.split("), latest")[0]


class TestTheBoundedStatementReturnsTheSameRows:
    """Mutation 4: drop the outer `:event` predicate."""

    def test_it_matches_the_unfiltered_rows_cut_to_that_fixture(
        self, two_fixtures
    ):
        every = _rows(two_fixtures, decisions._SQL_PROP_RUNGS, None)
        one = _rows(two_fixtures, decisions._SQL_PROP_RUNGS_ONE_EVENT, "A")
        assert one == [r for r in every if r[0] == "A"]
        assert one, "the fixture produced no rows; the test proves nothing"

    def test_it_matches_the_old_outer_only_query(self, two_fixtures):
        old = _rows(two_fixtures, decisions._SQL_PROP_RUNGS, "A")
        new = _rows(two_fixtures, decisions._SQL_PROP_RUNGS_ONE_EVENT, "A")
        assert new == old

    def test_the_other_fixture_agrees_too(self, two_fixtures):
        old = _rows(two_fixtures, decisions._SQL_PROP_RUNGS, "B")
        new = _rows(two_fixtures, decisions._SQL_PROP_RUNGS_ONE_EVENT, "B")
        assert new == old
        assert len(new) == 2, new


class TestTheLatestSweepIsStillPerFixture:
    """Mutation 3: `latest` takes a global MAX instead of one per event.

    The interleaved fixture makes this detectable: B's sweep is newer than A's,
    so a global maximum erases A.
    """

    def test_the_older_fixture_keeps_its_own_latest_sweep(self, two_fixtures):
        assert len(
            _rows(two_fixtures, decisions._SQL_PROP_RUNGS_ONE_EVENT, "A")
        ) == 1

    def test_the_newest_sweep_wins_within_a_fixture(self, two_fixtures):
        cursor = two_fixtures.execute(
            decisions._SQL_PROP_RUNGS_ONE_EVENT, {"event": "A"}
        )
        columns = [d[0] for d in cursor.description]
        row = cursor.fetchall()[0]
        assert row[columns.index("over_price")] == 2.0
        assert row[columns.index("fetched_ms")] == NOW_MS - 30_000


class TestTheSubcommandPicksTheRightStatement:
    """Mutation 2: `_q_prop_rungs` using `_SQL_PROP_RUNGS` for both branches.

    **These must observe the STATEMENT, not the rows, and the first draft of
    this class did not.** The two statements return identical rows by
    construction -- that is the whole equivalence argument above -- so a test
    that only checks rows cannot tell which one ran, and mutation 2 was
    measured STILL GREEN against it. The dispatch is the only thing left to
    guard once the rows are proven equal, so it is guarded by capturing the SQL
    the function hands to `_fetch`.
    """

    @staticmethod
    def _sql_executed(monkeypatch, conn, args):
        seen = {}
        real = decisions._fetch

        def spy(conn_, sql, params, **kwargs):
            seen["sql"] = sql
            return real(conn_, sql, params, **kwargs)

        monkeypatch.setattr(decisions, "_fetch", spy)
        sections = decisions._q_prop_rungs(conn, args)
        return seen["sql"], sections

    def test_a_named_fixture_runs_the_seeking_statement(
        self, two_fixtures, monkeypatch
    ):
        sql, sections = self._sql_executed(
            monkeypatch, two_fixtures, _Args(odds_event_id="A")
        )
        assert sql == decisions._SQL_PROP_RUNGS_ONE_EVENT
        assert [r[0] for r in sections[0].rows] == ["A"]
        assert "odds_event_id = A" in sections[0].title

    def test_no_flag_runs_the_registered_statement(
        self, two_fixtures, monkeypatch
    ):
        """The registered population must be reached by the statement the
        registration was written against, character for character."""
        sql, sections = self._sql_executed(monkeypatch, two_fixtures, _Args())
        assert sql == decisions._SQL_PROP_RUNGS
        assert sorted({r[0] for r in sections[0].rows}) == ["A", "B"]
        assert "all fixtures" in sections[0].title

    def test_the_statement_a_named_fixture_runs_actually_seeks(
        self, two_fixtures, monkeypatch
    ):
        """Closes the loop: the dispatch picks a statement AND that statement
        is the bounded one. Either half alone is satisfiable by the mutation."""
        sql, _ = self._sql_executed(
            monkeypatch, two_fixtures, _Args(odds_event_id="A")
        )
        assert not _scans_the_whole_index(_plan(two_fixtures, sql, "A"))

    def test_the_two_branches_agree_on_the_rows(self, two_fixtures):
        named = decisions._q_prop_rungs(
            two_fixtures, _Args(odds_event_id="A")
        )[0].rows
        every = decisions._q_prop_rungs(two_fixtures, _Args())[0].rows
        assert named == [r for r in every if r[0] == "A"]
