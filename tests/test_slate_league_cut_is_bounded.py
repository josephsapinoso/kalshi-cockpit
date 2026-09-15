"""The Games screen's league cut reads one index entry per row, not a league.

On 2026-09-15 the NFL chip on the Games screen said "Backend unreachable"
while the MLB chip worked. `api_read_incidents` on live carried six
`read_budget` rows in five minutes (12:16-12:21Z), every one of them
`GET /api/slate?league=americanfootball_nfl` at 25,00x ms,
`OperationalError: interrupted`. The predicate was

    EXISTS (SELECT 1 FROM odds_snapshots o
            WHERE o.odds_event_id = l.odds_event_id AND o.sport_key = ?)

and `EXPLAIN QUERY PLAN` shows why one league is slow and another is not:
`sport_key` is in no index that leads with `odds_event_id`, so SQLite takes
`idx_odds_sport_commence (sport_key=?)` and, for every window row whose
fixture is NOT in the requested league, walks that league's whole partition
of a ten-million-row table before it can say "no". MLB rows are most of the
window, so the MLB chip matches on the first probe and the NFL chip pays the
full walk ~350 times per statement, twice per request.

The predicate now reads the fixture's `sport_key` off the FIRST entry of
`idx_odds_event_commence (odds_event_id, commence_ms)`:

    (SELECT o.sport_key FROM odds_snapshots o
     WHERE o.odds_event_id = l.odds_event_id
     ORDER BY o.commence_ms LIMIT 1) = ?

A fixture's `sport_key` is constant across its rows, so one entry answers
it, whichever league is asked for. The plan below is the guard; the
`tests/test_list_filters.py` sibling pins that the answer did not change.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- That the route is fast on live. A plan names the access method, never the
  rows the method touches (the v39 index note in `schema.sql` is the record
  of that mistake); what makes this one bounded is `LIMIT 1` on an index
  whose first entry is the row wanted, and the live re-read after deploy is
  the measurement.
- That the outer scan of `recommendations` is cheap. `_BASIS_SQL` is an
  expression, so that scan is a `SCAN r` with or without a cut, as it was
  before the cut existed.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from backend.api.routes import _BASIS_SQL, _slate_filter_sql
from backend.list_filters import parse_list_filter
from backend.store import db

INDEX = "idx_odds_event_commence"


def plan(conn, sql: str, params) -> list[str]:
    return [r["detail"] for r in conn.execute("EXPLAIN QUERY PLAN " + sql, params)]


@pytest.fixture
def conn():
    c = db.init_db(os.path.join(tempfile.mkdtemp(), "slate_cut.db"))
    yield c
    c.close()


def _statements(league: str) -> list[tuple[str, tuple]]:
    """The two shapes `/api/slate` runs with a cut: the window count and the
    row read. Same aliases (`r`, `l`) and the same suffix the route appends."""
    list_filter = parse_list_filter(league, None, now_ms=0)
    suffix, params = _slate_filter_sql(list_filter)
    count = (
        "SELECT COUNT(*) AS n FROM recommendations r "
        "LEFT JOIN event_links l ON l.id = r.link_id "
        f"WHERE {_BASIS_SQL} >= ?{suffix}"
    )
    rows = (
        "SELECT r.* FROM recommendations r "
        "LEFT JOIN kalshi_markets m ON m.ticker = r.ticker "
        "LEFT JOIN event_links l ON l.id = r.link_id "
        f"WHERE {_BASIS_SQL} >= ?{suffix} "
        f"ORDER BY r.suggested_contracts DESC, {_BASIS_SQL} DESC, r.id DESC LIMIT ?"
    )
    return [(count, (0, *params)), (rows, (0, *params, 100))]


class TestTheLeagueCutIsOneEntryPerRow:
    @pytest.mark.parametrize("league", ["americanfootball_nfl", "baseball_mlb"])
    def test_the_subquery_seeks_the_event_index(self, conn, league):
        """Whichever league is asked for -- the failure was asymmetric."""
        for sql, params in _statements(league):
            steps = plan(conn, sql, params)
            assert any(
                "SEARCH o USING INDEX " + INDEX in s and "odds_event_id=?" in s
                for s in steps
            ), steps

    @pytest.mark.parametrize("league", ["americanfootball_nfl", "baseball_mlb"])
    def test_no_statement_walks_a_league_partition(self, conn, league):
        """The old plan's line was `SEARCH o USING COVERING INDEX
        idx_odds_sport_commence (sport_key=?)`: every row of the league,
        per outer row. Neither that index nor a scan of `o` may appear."""
        for sql, params in _statements(league):
            steps = plan(conn, sql, params)
            assert not any("idx_odds_sport_commence" in s for s in steps), steps
            assert not any(s.startswith("SCAN o") for s in steps), steps

    def test_the_read_is_bounded_by_limit_one(self):
        """The plan alone cannot show how many rows a SEARCH touches; the
        `LIMIT 1` under an `ORDER BY` the index satisfies is what bounds
        it, so its presence is asserted in the text."""
        suffix, params = _slate_filter_sql(
            parse_list_filter("americanfootball_nfl", None, now_ms=0)
        )
        assert "ORDER BY o.commence_ms LIMIT 1" in suffix
        assert "EXISTS" not in suffix
        assert params == ["americanfootball_nfl"]


class TestTheOldPredicateIsTheBadPlan:
    def test_exists_with_the_sport_in_its_where_walks_the_partition(self, conn):
        """Documents the mechanism, so the next reader does not put it back
        on the grounds that "EXISTS short-circuits"."""
        old = (
            "SELECT COUNT(*) AS n FROM recommendations r "
            "LEFT JOIN event_links l ON l.id = r.link_id "
            f"WHERE {_BASIS_SQL} >= ? AND EXISTS (SELECT 1 FROM odds_snapshots o "
            "WHERE o.odds_event_id = l.odds_event_id AND o.sport_key = ?)"
        )
        steps = plan(conn, old, (0, "americanfootball_nfl"))
        assert any("idx_odds_sport_commence" in s and "sport_key=?" in s for s in steps), (
            "if this stops holding, SQLite changed its choice and the note above "
            f"is stale: {steps}"
        )
