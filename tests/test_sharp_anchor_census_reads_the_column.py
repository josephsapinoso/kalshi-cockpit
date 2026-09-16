"""`sharp-anchor-census` reads the flag, prints both sides of it, and seeks.

`team-bookmakers` reports which books came BACK. Whether `consensus_devig`
then anchored on a sharp one is a different question with a different answer,
recorded per row in `fair_prices.anchored_on_sharp` -- and on 2026-09-16 a
session inferred the first from the second and got it backwards. The input
side said WNBA was the worst-covered sport; the column says WNBA `h2h` was
anchored on every row, and NCAAF `spreads`/`totals` were the worst cells in
the table on the largest counts in it.

Book presence is an UPPER BOUND on anchoring and the four gaps all run one
way: `consensus_devig` runs per rung rather than per fixture, a book joins a
rung only if it quoted that exact line two-sided in the same sweep, a book
failing devig leaves `usable`, and commenced games drop out. So the column had
to be read directly, and nothing in the repo read it.

DENOMINATOR ON THE SCREEN
-------------------------
Both values of the flag are emitted as their own rows and no ratio is printed.
That is the census exemption stated in `inspect_live_db.py`'s docstring: an
exhaustive `COUNT(*)` over a bounded window under three keys has no sample, no
null and no standard error. The query is named `-census` and not `-rate` for
the reason the docstring gives -- a name promising the one quantity it must
not emit is a name someone eventually makes it honour.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Nothing about live anchoring.** These tests insert their own rows. What
  the live figures are is answered on the box.
- **Nothing about why a row is unanchored.** The column records that no
  purchased sharp book contributed to that rung, not which of four reasons.
- **Nothing that a rate over `rows_n` would mean.** A fixture contributes one
  row per rung per pass. `links` is the clustering unit.

Mutations, each observed red:
  1. drop ` AND f.computed_ms >= :since `
  2. drop ` AND (:league IS NULL OR e.league = :league) `
  3. `GROUP BY e.league, f.market` -- collapsing the flag, which erases the
     denominator and is exactly the failure the census exemption guards
  4. `WHERE f.anchored_on_sharp = 1` -- emitting the numerator alone
  5. `_sharp_anchor_since_ms` returning 0 when `--since` is absent
  6. INNER JOIN turned into a LEFT JOIN, which would admit rows with no league
"""

from __future__ import annotations

import importlib
import os
import sqlite3
import sys
import tempfile
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

decisions = importlib.import_module("inspect_live_db_decisions")

SCHEMA = os.path.join(
    os.path.dirname(__file__), "..", "backend", "store", "schema.sql"
)

DAY_MS = 86_400_000
NOW_MS = 1_789_500_000_000


class _Args:
    def __init__(self, *, limit=2000, since=None, league=None, day_start_hour=10):
        self.limit = limit
        self.since = since
        self.league = league
        self.day_start_hour = day_start_hour


@pytest.fixture
def conn():
    path = os.path.join(tempfile.mkdtemp(), "anchor.db")
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    with open(SCHEMA, encoding="utf-8") as fh:
        c.executescript(fh.read())
    yield c
    c.close()


def _link(conn, *, link_id, league, ticker=None):
    """One `event_links` row and the `kalshi_events` row it points at.

    `schema.sql:36` sets `PRAGMA foreign_keys = ON`, so the parent row is not
    optional and `series_ticker` is left NULL rather than naming a
    `kalshi_series` that does not exist.
    """
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_events (event_ticker, series_ticker, "
        "title, first_seen_ms, last_seen_ms) VALUES (?, NULL, ?, ?, ?)",
        (ticker or f"EV{link_id}", "A game", NOW_MS, NOW_MS),
    )
    conn.execute(
        "INSERT INTO event_links (id, kalshi_event_ticker, odds_event_id, "
        "league, method, commence_skew_ms, linked_ms) "
        "VALUES (?, ?, ?, ?, 'exact_alias_pair', 0, ?)",
        (link_id, ticker or f"EV{link_id}", f"odds-{link_id}", league, NOW_MS),
    )
    conn.commit()


def _fair(conn, *, link_id, market, anchored, computed_ms=NOW_MS,
          outcome="Home"):
    conn.execute(
        "INSERT INTO fair_prices (link_id, market, outcome_name, "
        "p_multiplicative, p_additive, p_power, p_shin, p_conservative, "
        "book_count, books_used, computed_ms, anchored_on_sharp) "
        "VALUES (?, ?, ?, 0.5, 0.5, 0.5, 0.5, 0.5, 3, "
        "'[\"pinnacle\"]', ?, ?)",
        (link_id, market, outcome, computed_ms, anchored),
    )
    conn.commit()


def _data(sections):
    hits = [s for s in sections if "anchored_on_sharp" in s.columns]
    assert hits, [s.title for s in sections]
    return hits[0]


def _cells(sections):
    """`{(league, market, anchored): rows_n}` for the response section."""
    section = _data(sections)
    i = {name: n for n, name in enumerate(section.columns)}
    return {
        (r[i["league"]], r[i["market"]], r[i["anchored_on_sharp"]]):
            r[i["rows_n"]]
        for r in section.rows
    }


def plan(conn, sql, params):
    return [r["detail"] for r in conn.execute("EXPLAIN QUERY PLAN " + sql, params)]


@pytest.fixture
def two_leagues(conn):
    _link(conn, link_id=1, league="NCAA Football")
    _link(conn, link_id=2, league="NCAA Football")
    _link(conn, link_id=3, league="Pro Basketball (W)")
    # NCAAF spreads: one anchored row, two unanchored, across two fixtures.
    _fair(conn, link_id=1, market="spreads", anchored=1)
    _fair(conn, link_id=1, market="spreads", anchored=0, outcome="Away")
    _fair(conn, link_id=2, market="spreads", anchored=0)
    # WNBA h2h: fully anchored.
    _fair(conn, link_id=3, market="h2h", anchored=1)
    return conn


class TestBothSidesOfTheFlagAreRows:
    """Mutations 3 and 4: collapse the flag, or emit the numerator alone.

    This is the census exemption's whole condition. A query that printed only
    the anchored rows would report a numerator with no denominator, which is
    the shape `CLAUDE.md`'s measurement rules exist to refuse.
    """

    def test_anchored_and_unanchored_are_separate_rows(self, two_leagues):
        cells = _cells(decisions._q_sharp_anchor_census(
            two_leagues, _Args(since="20260901")
        ))
        assert cells[("NCAA Football", "spreads", 1)] == 1
        assert cells[("NCAA Football", "spreads", 0)] == 2

    def test_a_fully_anchored_cell_has_no_zero_row_and_that_is_correct(
        self, two_leagues
    ):
        """An absent row means no rows of that kind existed, not zero of
        something counted. The reader sums what is present."""
        cells = _cells(decisions._q_sharp_anchor_census(
            two_leagues, _Args(since="20260901")
        ))
        assert cells[("Pro Basketball (W)", "h2h", 1)] == 1
        assert ("Pro Basketball (W)", "h2h", 0) not in cells

    def test_no_ratio_column_is_emitted(self, two_leagues):
        section = _data(decisions._q_sharp_anchor_census(
            two_leagues, _Args(since="20260901")
        ))
        forbidden = ("rate", "pct", "percent", "share", "ratio")
        assert not [c for c in section.columns if any(f in c for f in forbidden)], (
            section.columns
        )


class TestLinksIsCarriedBesideRows:
    def test_rows_and_links_differ_when_one_fixture_has_two_rungs(
        self, two_leagues
    ):
        """`rows_n` is passes x rungs; `links` is the clustering unit. If only
        one were emitted, the larger would be the one quoted."""
        section = _data(decisions._q_sharp_anchor_census(
            two_leagues, _Args(since="20260901")
        ))
        i = {name: n for n, name in enumerate(section.columns)}
        row = [
            r for r in section.rows
            if r[i["league"]] == "NCAA Football"
            and r[i["market"]] == "spreads"
            and r[i["anchored_on_sharp"]] == 0
        ][0]
        assert row[i["rows_n"]] == 2
        assert row[i["links"]] == 2

    def test_two_rungs_of_one_fixture_are_two_rows_and_one_link(self, conn):
        _link(conn, link_id=9, league="Pro Football")
        _fair(conn, link_id=9, market="totals", anchored=0)
        _fair(conn, link_id=9, market="totals", anchored=0, outcome="Under")
        section = _data(decisions._q_sharp_anchor_census(
            conn, _Args(since="20260901")
        ))
        i = {name: n for n, name in enumerate(section.columns)}
        assert section.rows[0][i["rows_n"]] == 2
        assert section.rows[0][i["links"]] == 1


class TestTheWindowExcludesWhatIsOutsideIt:
    """Mutation 1: drop the `computed_ms` floor."""

    def test_an_older_row_is_not_counted(self, conn):
        _link(conn, link_id=1, league="Pro Baseball")
        _fair(conn, link_id=1, market="h2h", anchored=1)
        _fair(conn, link_id=1, market="h2h", anchored=0,
              computed_ms=NOW_MS - 400 * DAY_MS)
        cells = _cells(decisions._q_sharp_anchor_census(
            conn, _Args(since="20260901")
        ))
        assert cells == {("Pro Baseball", "h2h", 1): 1}


class TestTheLeagueCutIsOptionalAndExact:
    """Mutation 2: drop the league predicate."""

    def test_naming_a_league_excludes_the_others(self, two_leagues):
        cells = _cells(decisions._q_sharp_anchor_census(
            two_leagues, _Args(since="20260901", league="Pro Basketball (W)")
        ))
        assert set(k[0] for k in cells) == {"Pro Basketball (W)"}

    def test_no_league_means_every_league(self, two_leagues):
        cells = _cells(decisions._q_sharp_anchor_census(
            two_leagues, _Args(since="20260901")
        ))
        assert set(k[0] for k in cells) == {
            "NCAA Football", "Pro Basketball (W)"
        }

    def test_an_unrecognised_league_returns_nothing_rather_than_everything(
        self, two_leagues
    ):
        """It reads identically to a league with no rows, which is why the
        docstring says to run it unfiltered first."""
        cells = _cells(decisions._q_sharp_anchor_census(
            two_leagues, _Args(since="20260901", league="basketball_wnba")
        ))
        assert cells == {}


class TestOnlyTeamMarketsAreCounted:
    def test_a_prop_market_is_not_in_the_population(self, conn):
        """The three team markets are named explicitly, which is also what
        makes the plan seek on `market=?`."""
        _link(conn, link_id=1, league="Pro Baseball")
        _fair(conn, link_id=1, market="pitcher_strikeouts", anchored=0)
        _fair(conn, link_id=1, market="h2h", anchored=1)
        cells = _cells(decisions._q_sharp_anchor_census(
            conn, _Args(since="20260901")
        ))
        assert cells == {("Pro Baseball", "h2h", 1): 1}


class TestARowWithNoLeagueIsNotInvented:
    """Mutation 6: INNER JOIN becomes LEFT JOIN.

    A `fair_prices` row whose `link_id` reaches no `event_links` row has no
    league. Admitting it with a NULL league would put an uncategorised bucket
    beside the real ones, and the natural reading of a NULL league is "all of
    them" -- the bucket would be read as a total.

    **The orphan is built with `foreign_keys` OFF, deliberately.**
    `schema.sql:36` turns them on, so the live database should not contain
    one; the guard is about what the JOIN does with a shape, not a claim that
    the shape occurs. Asserting the SQL text said INNER would be decoration --
    this runs the query.
    """

    def test_an_unlinked_fair_price_is_dropped_not_bucketed_as_null(self, conn):
        _link(conn, link_id=1, league="Pro Baseball")
        _fair(conn, link_id=1, market="h2h", anchored=1)
        conn.execute("PRAGMA foreign_keys = OFF")
        _fair(conn, link_id=404, market="h2h", anchored=0)
        conn.execute("PRAGMA foreign_keys = ON")
        cells = _cells(decisions._q_sharp_anchor_census(
            conn, _Args(since="20260901")
        ))
        assert cells == {("Pro Baseball", "h2h", 1): 1}
        assert not [k for k in cells if k[0] is None]


class TestTheDefaultIsAWindowNotTheWholeTable:
    """Mutation 5: `_sharp_anchor_since_ms` returning 0 with no `--since`."""

    def test_an_absent_since_still_produces_a_recent_floor(self):
        floor = decisions._sharp_anchor_since_ms(_Args())
        expected = decisions._SHARP_ANCHOR_DEFAULT_DAYS * DAY_MS
        assert floor > 1_700_000_000_000, floor
        assert abs((floor + expected) - int(time.time() * 1000)) < DAY_MS

    def test_a_malformed_since_is_refused_rather_than_ignored(self):
        with pytest.raises(ValueError, match="YYYYMMDD"):
            decisions._sharp_anchor_since_ms(_Args(since="last-tuesday"))


class TestThePlanSeeksRatherThanScanning:
    def test_the_market_equality_leads_the_index(self, conn):
        steps = plan(
            conn,
            decisions._SQL_SHARP_ANCHOR_CENSUS,
            {"since": NOW_MS - 2 * DAY_MS, "league": None},
        )
        assert not any(
            s.startswith("SCAN fair_prices") for s in steps
        ), steps
        assert any("computed_ms>?" in s for s in steps), steps


class TestTheSectionSaysWhichPopulationItCounted:
    def test_the_window_travels_with_the_counts(self, two_leagues):
        sections = decisions._q_sharp_anchor_census(
            two_leagues, _Args(since="20260901")
        )
        assert len(sections) == 2
        assert "window" in sections[0].title.lower()
        assert "computed at or after" in sections[1].title

    def test_the_title_names_the_league_when_one_is_cut(self, two_leagues):
        sections = decisions._q_sharp_anchor_census(
            two_leagues, _Args(since="20260901", league="NCAA Football")
        )
        assert "NCAA Football" in sections[1].title


class TestTheSubcommandIsReachable:
    def test_it_is_registered_under_the_census_name(self):
        inspect = importlib.import_module("inspect_live_db")
        assert "sharp-anchor-census" in inspect.QUERIES
        assert "sharp-anchor-rate" not in inspect.QUERIES
        assert (
            inspect.QUERIES["sharp-anchor-census"].run
            is decisions._q_sharp_anchor_census
        )
