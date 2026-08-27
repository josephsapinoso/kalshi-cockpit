"""The parlay ladder's fixture lookup must not scan two growing tables.

Measured on live 2026-08-26, after the recorder's own scan was fixed:
`/api/parlays` answered in **15 seconds** while every other route was
sub-second — so it was the route, not contention. `EXPLAIN QUERY PLAN` said
why:

    SCAN odds_snapshots USING INDEX idx_odds_event      <- every row, every call
    SCAN f                                              <- every fair price

`odds_snapshots` has **no retention rule at all** (`store/retention.py:53-55`,
deliberately out of scope), so the first of those grows forever.

THE FIX, IN TWO PARTS
---------------------
1. **The subquery is restricted to linked events.** The outer query
   inner-joins on `l.odds_event_id`, so an event absent from `event_links` was
   discarded anyway — the group was building rows to throw away.
2. **One index**: `(market, computed_ms DESC)` on `fair_prices`.

**A second index was written and then deleted the same hour, and that is worth
recording.** `(odds_event_id, commence_ms)` on `odds_snapshots` looked
necessary and changed no plan: the existing `idx_odds_event` already leads with
`odds_event_id`, which is all the equality needs. It would have cost write
amplification on the highest-volume table in the system to buy nothing. The
claim that "neither half works alone" was made before it was tested, and the
test below is what refuted it.

What IS true: the restriction is doing the work on `odds_snapshots`, and the
`fair_prices` index is doing the work on `f`. `TestEachHalfIsLoadBearing` pins
both, so neither is removed as redundant later.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **That `/api/parlays` is now fast.** The plan is a precondition. The re-read
  has to happen on the live box, under load, split by whether a pass is
  running — the caveat that made the 17:00Z baseline misleading when it was
  taken in a quiet window.
- **That the residual cost is gone.** `AUTOMATIC PARTIAL COVERING INDEX` and
  the ORDER BY's temp b-tree both survive and are not removable by indexing:
  the first is SQLite indexing the SUBQUERY'S OUTPUT, which has no persistent
  index by definition, and the second sorts a derived join. What changed is
  how many rows reach them.
- **That the planner behaves identically at scale.** These fixtures are small.
  A seek on an indexed equality does not become a scan as rows grow, which is
  why the assertions are about scans and seeks rather than about cost.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

import pytest

from backend.store import db

PARLAYS = Path(__file__).resolve().parents[1] / "backend" / "parlays.py"


def ladder_sql() -> str:
    """The query as `ladder_candidates` actually issues it.

    Extracted from the module rather than copied here: a hand-typed duplicate
    is a second definition that drifts, and this test would then certify a
    plan for a query nobody runs.
    """
    src = PARLAYS.read_text(encoding="utf-8")
    match = re.search(r'rows = conn\.execute\(\s*"""(.*?)"""', src, re.S)
    assert match, "could not find the ladder query in backend/parlays.py"
    sql = match.group(1)
    assert "FROM fair_prices f" in sql, "extracted the wrong statement"
    return sql


def plan(conn, sql: str, params) -> list[str]:
    return [r["detail"] for r in conn.execute("EXPLAIN QUERY PLAN " + sql, params)]


@pytest.fixture
def conn():
    c = db.init_db(os.path.join(tempfile.mkdtemp(), "ladder.db"))
    yield c
    c.close()


class TestNeitherGrowingTableIsScanned:
    def test_odds_snapshots_is_searched_not_scanned(self, conn):
        """The table with no retention rule. It only ever gets bigger."""
        steps = plan(conn, ladder_sql(), (0, 0))
        assert not any(s.startswith("SCAN odds_snapshots") for s in steps), (
            f"the ladder groups the whole snapshot history: {steps}"
        )
        assert any(
            "odds_snapshots" in s and "SEARCH" in s and "odds_event_id=?" in s
            for s in steps
        ), steps

    def test_fair_prices_is_searched_not_scanned(self, conn):
        steps = plan(conn, ladder_sql(), (0, 0))
        assert not any(re.fullmatch(r"SCAN f", s) for s in steps), (
            f"every fair price ever computed is visited: {steps}"
        )
        assert any("market=?" in s and "computed_ms>?" in s for s in steps), steps

    def test_the_restriction_is_present_in_the_query(self, conn):
        sql = ladder_sql()
        assert "odds_event_id IN (SELECT odds_event_id FROM event_links)" in sql


class TestTheRestrictionCannotChangeTheAnswer:
    def test_the_outer_join_already_required_a_link(self, conn):
        """Why the restriction is safe rather than a filter.

        The query inner-joins `event_links l ON l.id = f.link_id` and then
        `o.odds_event_id = l.odds_event_id`. Any snapshot event with no link
        could never survive that join, so removing it from the group changes
        nothing about the output.
        """
        sql = ladder_sql()
        assert "JOIN event_links l ON l.id = f.link_id" in sql
        assert "o.odds_event_id = l.odds_event_id" in sql

    def test_commence_ms_is_not_filtered_inside_the_group(self, conn):
        """The obvious further cut, refused on purpose.

        `MIN(commence_ms)` is the fixture's EARLIEST recorded start. Filtering
        rows before taking the MIN would let a rescheduled fixture through
        whose true earliest start is in the past — a silent wrong answer, in
        exchange for speed on a query that is now a seek anyway.
        """
        sql = ladder_sql()
        group = sql[sql.index("FROM odds_snapshots") : sql.index("GROUP BY")]
        assert "commence_ms >" not in group and "commence_ms>" not in group, (
            "a commence filter was pushed inside the GROUP BY; see the "
            "comment in backend/parlays.py for why that is not safe"
        )


class TestEachHalfIsLoadBearing:
    """Pinned so neither is removed as redundant later."""

    def test_without_the_fair_prices_index_it_scans_again(self):
        c = db.init_db(os.path.join(tempfile.mkdtemp(), "half.db"))
        try:
            c.execute("DROP INDEX IF EXISTS idx_fair_market_computed")
            steps = plan(c, ladder_sql(), (0, 0))
        finally:
            c.close()
        assert any(re.fullmatch(r"SCAN f", s) for s in steps), (
            f"the fair_prices index changes no plan, so it is decoration "
            f"with a write cost: {steps}"
        )

    def test_the_odds_seek_comes_from_the_restriction_not_a_new_index(self):
        """The correction, kept as a test so it is not re-discovered.

        `(odds_event_id, commence_ms)` was written, looked necessary, and
        changed no plan -- `idx_odds_event` already leads with the same column.
        This asserts the seek survives on the EXISTING index, which is what
        makes the deleted one redundant rather than missing.
        """
        c = db.init_db(os.path.join(tempfile.mkdtemp(), "noidx.db"))
        try:
            steps = plan(c, ladder_sql(), (0, 0))
        finally:
            c.close()
        assert any(
            "odds_snapshots" in s and "idx_odds_event" in s and "SEARCH" in s
            for s in steps
        ), steps

    def test_no_duplicate_leading_column_index_was_reintroduced(self):
        """An index that changes no plan is a write cost for nothing."""
        schema = (
            Path(__file__).resolve().parents[1] / "backend" / "store" / "schema.sql"
        ).read_text(encoding="utf-8")
        # The NAME appears in the schema's prose, explaining why it is absent.
        # What must not exist is a CREATE for it — assert the statement, not
        # the string, or the explanation trips the guard it belongs to.
        assert "CREATE INDEX IF NOT EXISTS idx_odds_event_commence" not in schema, (
            "a second odds_snapshots index leading with odds_event_id is back; "
            "it changed no plan when measured on 2026-08-26"
        )

    def test_the_index_is_declared_in_the_schema(self):
        """It must reach the LIVE volume, which is an existing database.

        `init_db` applies `schema.sql` unconditionally after `migrate`, so a
        `CREATE INDEX IF NOT EXISTS` lands on an existing volume at next boot.
        """
        schema = (
            Path(__file__).resolve().parents[1] / "backend" / "store" / "schema.sql"
        ).read_text(encoding="utf-8")
        assert "CREATE INDEX IF NOT EXISTS idx_fair_market_computed" in schema


class TestTheQueryNamesEveryMarketALegMayComeFrom:
    """The literals in the SQL and the constants callers use must agree.

    The query has to stay a literal triple-quoted string -- `ladder_sql()`
    above extracts it by regex, and interpolating a constant would both break
    that extraction and risk losing the `market=?` index seek. So the market
    list is written twice, and this is what stops the two copies drifting: add
    a prop series to `PROP_SERIES` without adding it here and the pool would
    silently never contain it.
    """

    def test_the_sql_names_every_prop_market_key(self):
        from backend.odds.client import PROP_BASE_MARKETS

        sql = ladder_sql()
        for market in PROP_BASE_MARKETS:
            assert f"'{market}'" in sql, (
                f"{market} is bought and devigged but no leg can come from it"
            )

    def test_the_sql_names_both_team_markets(self):
        from backend.parlays import _TEAM_MARKETS

        sql = ladder_sql()
        for market in _TEAM_MARKETS:
            assert f"'{market}'" in sql

    def test_the_bought_prop_keys_and_the_kalshi_series_agree(self):
        """One Odds API market key per Kalshi prop series, both directions.

        A series in `PROP_SERIES` whose key is never bought produces Kalshi
        rungs with no consensus; a key bought with no series produces a
        consensus nothing can be matched to. Either way the credits are spent.
        """
        from backend.kalshi.props import PROP_SERIES
        from backend.odds.client import PROP_BASE_MARKETS

        assert set(PROP_SERIES.values()) == set(PROP_BASE_MARKETS)
