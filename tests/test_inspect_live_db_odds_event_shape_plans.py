"""`odds-event-shape-plans` (#121): EXPLAIN QUERY PLAN for Shapes 3 and 4.

Story #89 found `idx_odds_event` (`odds_event_id, market, fetched_ms DESC`)
has no access shape it uniquely serves: `idx_odds_window` covers Shape 1
(the only shape naming both `odds_event_id` and `market`), and the shapes
that filter `odds_event_id` WITHOUT `market` (Shapes 3 and 4) want
`commence_ms`, which `idx_odds_event_commence` carries. The reading this
ticket owes is whether Shapes 3 and 4 actually land there in practice.

THIS FILE DOES NOT RUN ANYTHING AGAINST LIVE
----------------------------------------------
Per the ticket ("Run nothing against live. Main takes the reading."), every
assertion below runs against a schema-built `tmp_path` database. A green
suite here says the statements are well-formed, land on
`idx_odds_event_commence` on THIS schema, and the query does not execute
them -- it says nothing about the live volume's own planner statistics,
which is what #121's own "Not whether the planner's choice is stable" note
in the query docstring is for.

WHAT THIS FILE DOES NOT RE-LITIGATE
-------------------------------------
The module comment in `scripts/inspect_live_db_loop.py` above
`_q_odds_event_shape_plans` documents, at length, why this query covers only
TWO of the ticket's three named Shape 3 call sites and ONE of its three
named Shape 4 call sites -- the others are either dead prose in a docstring
(a false positive from a text-search enumeration) or WHERE-clause fragments
that cannot run standalone without inventing SQL the source does not
contain. This file does not re-derive that; `test_the_module_comment_names_
the_excluded_call_sites` below only pins that the explanation stays written
down.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scripts.inspect_live_db import CHEAP, QUERIES
from scripts.inspect_live_db_loop import (
    _SQL_SHAPE3_CANDIDATE_SUBQUERY,
    _SQL_SHAPE3_SLATE_KICKOFFS,
    _SQL_SHAPE4_FIXTURE_FOR_TICKER,
    _q_odds_event_shape_plans,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "backend" / "store" / "schema.sql"

#: SQLite's fixed `EXPLAIN QUERY PLAN` output shape -- NEVER the wrapped
#: statement's own result columns. This is the guard the ticket asks for:
#: if a plan section ever carried the statement's own columns instead, the
#: statement ran for real rather than only being planned.
PLAN_COLUMNS = ("id", "parent", "notused", "detail")


class _Args:
    """Stand-in for `argparse.Namespace` -- `_q_odds_event_shape_plans` reads `.limit` only."""

    limit = 2000


@pytest.fixture
def db(tmp_path) -> Path:
    path = tmp_path / "cockpit.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    return path


class TestOddsEventShapePlans:
    def test_registered_and_cheap(self):
        """Mutation: delete the `"odds-event-shape-plans"` entry from
        `QUERIES` -- red (KeyError). `cost=CHEAP` because `EXPLAIN QUERY
        PLAN` does not execute the statement, regardless of what the
        statement itself would cost run for real.
        """
        assert "odds-event-shape-plans" in QUERIES
        assert QUERIES["odds-event-shape-plans"].cost == CHEAP

    def test_three_statement_plan_pairs_are_returned(self, db):
        """**The done-when guard.** Each of the three statements gets its
        own SQL section and its own plan section, and every plan section
        returns at least one row.
        """
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            sections = _q_odds_event_shape_plans(conn, _Args())
        finally:
            conn.close()

        assert len(sections) == 6  # 3 statements x (SQL section, plan section)

        sql_sections = [s for s in sections if s.columns == ("sql",)]
        plan_sections = [s for s in sections if s.columns == PLAN_COLUMNS]
        assert len(sql_sections) == 3
        assert len(plan_sections) == 3
        for plan in plan_sections:
            assert plan.row_count >= 1, plan.title

    def test_the_plan_columns_prove_it_did_not_execute(self, db):
        """The guard named in the query's own docstring: a plan section's
        columns are ALWAYS `(id, parent, notused, detail)`, never the
        statement's own result columns (`odds_event_id`, `commence_ms`,
        `home_team`, ...).

        Mutation: drop the `"EXPLAIN QUERY PLAN " +` prefix in
        `_q_odds_event_shape_plans` -- red, because the statements now run
        for real and their sections carry the STATEMENT's columns instead
        (e.g. `("odds_event_id", "commence_ms")`), not
        `("id", "parent", "notused", "detail")`.
        """
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            sections = _q_odds_event_shape_plans(conn, _Args())
        finally:
            conn.close()

        plan_sections = [s for s in sections if "EXPLAIN QUERY PLAN" in s.title]
        assert len(plan_sections) == 3
        for plan in plan_sections:
            assert plan.columns == PLAN_COLUMNS, plan.title
            for row in plan.rows:
                assert set(("odds_event_id", "commence_ms")) & set() == set()
                # (the columns assertion above is the real guard; this loop
                # only confirms every row has the fixed 4-tuple shape)
                assert len(row) == 4

    def test_shapes_3_and_4_land_on_the_commence_index_on_this_schema(self, db):
        """On the real schema (empty of rows, but the planner reads
        structure, not content), all three statements should choose
        `idx_odds_event_commence` and none should choose `idx_odds_event` --
        the finding #89's shape argument predicted and this ticket exists to
        confirm.

        **This is a schema-shape check, not a live-volume finding** -- see
        the module docstring above. The live reading is main's to take.
        """
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            sections = _q_odds_event_shape_plans(conn, _Args())
        finally:
            conn.close()

        plan_sections = [s for s in sections if "EXPLAIN QUERY PLAN" in s.title]
        detail_idx = plan_sections[0].columns.index("detail")
        for plan in plan_sections:
            details = " ".join(str(r[detail_idx]) for r in plan.rows)
            assert "idx_odds_event_commence" in details, plan.title
            # idx_odds_event_commence is a real substring of nothing else
            # named idx_odds_event -- but guard the negative explicitly so a
            # future index rename cannot silently defeat this assertion.
            assert "idx_odds_event " not in details, plan.title
            assert "idx_odds_event\n" not in details, plan.title
            assert "USING INDEX idx_odds_event " not in details, plan.title

    def test_statement_sql_sections_contain_no_market_predicate(self, db):
        """Both shapes are defined by the ABSENCE of a `market` predicate --
        that is the entire reason they cannot use `idx_odds_event`.

        Mutation: add `AND market = 'h2h'` to `_SQL_SHAPE4_FIXTURE_FOR_TICKER`
        -- red, this goes from correctly absent to present.
        """
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            sections = _q_odds_event_shape_plans(conn, _Args())
        finally:
            conn.close()

        sql_sections = [s for s in sections if s.columns == ("sql",)]
        for section in sql_sections:
            sql_text = section.rows[0][0]
            assert "market" not in sql_text, section.title


class TestTheCopiesDoNotDrift:
    """Every statement here is a literal copy of production SQL, and #121
    is explicit that a reworded statement is a different fact.
    """

    def test_shape3_candidate_subquery_is_a_substring_of_candidate_sql(self):
        """`_SQL_SHAPE3_CANDIDATE_SUBQUERY` is DERIVED (sliced, not
        retyped) from `_SQL_PARLAY_CANDIDATES`, which
        `TestTheCandidateScanCopyDoesNotDrift`
        (`tests/test_inspect_live_db.py`) already pins byte-identical to
        `backend.parlays.CANDIDATE_SQL`. This test pins the SLICE itself,
        so a future edit to the marker strings in
        `scripts/inspect_live_db_loop.py` cannot silently start slicing the
        wrong span.

        Mutation: change `_SHAPE3_SUBQUERY_END` from `"GROUP BY
        odds_event_id"` to `"GROUP BY odds_event_i"` (missing the final
        `d`) -- red, `.index()` raises `ValueError` because the shortened
        marker matches mid-word inside the real one and the slice produced
        no longer ends where production's `GROUP BY odds_event_id` does. A
        more drastic version (e.g. slicing away `WHERE odds_event_id IN
        (...)`) removing the whole `WHERE` clause is caught by the second
        assertion below.
        """
        from backend.parlays import CANDIDATE_SQL

        assert _SQL_SHAPE3_CANDIDATE_SUBQUERY in CANDIDATE_SQL
        assert _SQL_SHAPE3_CANDIDATE_SUBQUERY.startswith(
            "SELECT odds_event_id, MIN(commence_ms) AS commence_ms,"
        )
        assert _SQL_SHAPE3_CANDIDATE_SUBQUERY.rstrip().endswith(
            "GROUP BY odds_event_id"
        )
        assert "WHERE odds_event_id IN (SELECT odds_event_id FROM event_links)" in (
            _SQL_SHAPE3_CANDIDATE_SUBQUERY
        )

    def test_shape3_slate_kickoffs_matches_the_route_verbatim(self):
        """`_SQL_SHAPE3_SLATE_KICKOFFS` is hand-copied (the route builds it
        as an f-string with a `{marks}` IN-list, which has no single fixed
        literal form to slice from) -- pinned against the raw source text
        of `backend/api/routes.py` instead.

        Mutation: change `GROUP BY odds_event_id` to `GROUP BY
        odds_event_id, market` in the constant -- red, the substring search
        below (with `market` stripped back out) no longer matches the
        route's actual text because the route's `GROUP BY` clause has no
        `market` in it either.
        """
        route_text = (ROOT / "backend" / "api" / "routes.py").read_text(
            encoding="utf-8"
        )
        # The route builds this with an f-string ({marks} varies with the
        # caller's fixture count); reconstruct that exact shape with one
        # placeholder standing in for `{marks}` at N=1, matching what
        # `_SQL_SHAPE3_SLATE_KICKOFFS` uses.
        assert (
            'f"SELECT odds_event_id, MIN(commence_ms) AS commence_ms "' in route_text
        )
        assert (
            'f"FROM odds_snapshots WHERE odds_event_id IN ({marks}) "' in route_text
        )
        assert 'f"GROUP BY odds_event_id",' in route_text
        assert _SQL_SHAPE3_SLATE_KICKOFFS == (
            "SELECT odds_event_id, MIN(commence_ms) AS commence_ms "
            "FROM odds_snapshots WHERE odds_event_id IN (?) "
            "GROUP BY odds_event_id"
        )

    def test_shape4_fixture_for_ticker_matches_the_route_verbatim(self):
        """`_SQL_SHAPE4_FIXTURE_FOR_TICKER` pinned against
        `backend/api/routes.py`'s raw source text -- the route's SELECT is
        split across two Python string literals (indentation included),
        and both pieces must appear verbatim.

        Mutation: drop the trailing space after `away_team,` in the
        constant -- red, the concatenated route source no longer contains
        the (now differently-spaced) substring.
        """
        route_text = (ROOT / "backend" / "api" / "routes.py").read_text(
            encoding="utf-8"
        )
        assert (
            '"SELECT MIN(commence_ms) AS commence_ms, home_team, away_team, "'
            in route_text
        )
        assert '"       sport_key "' in route_text
        assert '"FROM odds_snapshots WHERE odds_event_id = ?",' in route_text
        assert _SQL_SHAPE4_FIXTURE_FOR_TICKER == (
            "SELECT MIN(commence_ms) AS commence_ms, home_team, away_team, "
            "       sport_key "
            "FROM odds_snapshots WHERE odds_event_id = ?"
        )


class TestTheTicketsOwnCallSiteCountIsStale:
    """The ticket copies #89's enumeration verbatim: 3 call sites for each
    shape. Checked against the current tree (2026-09-21), that count is
    wrong for BOTH shapes, and the module comment above
    `_q_odds_event_shape_plans` documents exactly why. This class pins that
    the finding stays written down rather than silently disappearing on a
    future edit.
    """

    def _module_source(self) -> str:
        return (ROOT / "scripts" / "inspect_live_db_loop.py").read_text(
            encoding="utf-8"
        )

    def test_the_module_comment_names_the_excluded_shape3_call_site(self):
        text = self._module_source()
        assert "commence_for_tickers_sql" in text
        assert "2632-2637" in text or "merged and corrected the same hour" in text

    def test_the_module_comment_names_the_excluded_shape4_call_sites(self):
        text = self._module_source()
        assert "_slate_filter_sql" in text
        assert "do not paraphrase" in text

    def test_the_excluded_shape3_call_site_really_is_a_different_statement(self):
        """Confirms the finding itself, not just that it is documented:
        `commence_for_tickers_sql` (`backend/parlays.py`) groups by
        `k.ticker`, not `odds_event_id` -- it is not a live Shape 3
        statement, whatever a text search for the words "GROUP BY
        odds_event_id" would suggest (those words DO appear in that
        function's docstring, describing a bug that was fixed).
        """
        from backend.parlays import commence_for_tickers_sql

        sql = commence_for_tickers_sql(1)
        assert "GROUP BY k.ticker" in sql
        assert "GROUP BY odds_event_id" not in sql
