"""`prop-bookmakers` reads a slice of `odds_snapshots`, never the table.

The query was a bare `GROUP BY bookmaker` whose only predicate was
`outcome_description IS NOT NULL`. No index leads with that column, so SQLite
had one plan available: scan the largest table on the live box. The cost is not
paid by the session that runs it -- it is paid by whoever touches the desk
next, because the scan evicts the page cache the live reads run through
(`tasks/lessons.md`: a read-only GROUP BY over a ten-million-row table cost the
desk 75 seconds per query afterwards). A read whose expense lands on someone
else, minutes later, is the kind nobody attributes correctly.

`commence_ms >= :since` fixes it: `idx_odds_commence` serves the range, and
`idx_odds_sport_commence` serves it with `--sport`. The default is a
seven-day window rather than no bound, because an unbounded default is the one
a session reaches for during a game.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Nothing about live timing.** A plan names the access method, never the
  rows it touches -- the v39 note in `schema.sql` is this repo's record of
  that exact mistake. What makes this bounded is that `commence_ms` is a
  range on an index, and the live read is the measurement.
- **Nothing about which books quote props.** These tests insert their own
  rows. The question `prop-bookmakers` exists to answer is answered on live.

Mutations, one per test, each observed red:
  1. drop ` AND commence_ms >= :since ` from `_SQL_PROP_BOOKMAKERS`
  2. drop ` AND (:sport IS NULL OR sport_key = :sport) `
  3. `_bookmakers_since_ms` returning `0` when `--since` is absent
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

DAY_MS = 86_400_000
NOW_MS = 1_789_500_000_000


class _Args:
    """The namespace attributes `_q_prop_bookmakers` reads.

    `since` and `sport` default to `None` for the same reason the flags do: the
    unfiltered call is the one a live run actually makes, and a test that had
    to pass both would never exercise it.
    """

    def __init__(self, *, limit=2000, since=None, sport=None, day_start_hour=10):
        self.limit = limit
        self.since = since
        self.sport = sport
        self.day_start_hour = day_start_hour


@pytest.fixture
def conn():
    path = os.path.join(tempfile.mkdtemp(), "props.db")
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    with open(SCHEMA, encoding="utf-8") as fh:
        c.executescript(fh.read())
    yield c
    c.close()


def _prop_row(conn, *, book, sport, commence_ms, player="A. Player"):
    """One player-prop row. `outcome_description` is the discriminator the
    query selects on, so it is the field that must be populated."""
    conn.execute(
        "INSERT INTO odds_snapshots (odds_event_id, sport_key, commence_ms, "
        "home_team, away_team, bookmaker, market, outcome_name, "
        "outcome_description, price_decimal, fetched_ms) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            f"ev-{sport}-{commence_ms}",
            sport,
            commence_ms,
            "Home",
            "Away",
            book,
            "pitcher_strikeouts",
            "Over",
            player,
            1.9,
            commence_ms - 3600_000,
        ),
    )
    conn.commit()


def _books(sections):
    """The bookmaker column of the one data section, as a set."""
    data = [s for s in sections if s.rows and "bookmaker" in s.columns]
    assert data, [s.title for s in sections]
    i = data[0].columns.index("bookmaker")
    return {r[i] for r in data[0].rows}


def plan(conn, sql, params):
    return [r["detail"] for r in conn.execute("EXPLAIN QUERY PLAN " + sql, params)]


class TestTheWindowExcludesWhatIsOutsideIt:
    """Mutation: drop ` AND commence_ms >= :since ` from the SQL."""

    def test_a_fixture_older_than_the_floor_is_not_counted(self, conn):
        _prop_row(conn, book="inside", sport="baseball_mlb", commence_ms=NOW_MS)
        _prop_row(
            conn,
            book="ancient",
            sport="baseball_mlb",
            commence_ms=NOW_MS - 400 * DAY_MS,
        )
        sections = decisions._q_prop_bookmakers(
            conn, _Args(since="20260901")
        )
        assert _books(sections) == {"inside"}

    def test_a_future_fixture_is_inside_the_window(self, conn):
        """The floor is a floor, not a range: the weekend that has not
        happened yet is exactly the population anyone is asking about."""
        _prop_row(
            conn, book="weekend", sport="baseball_mlb", commence_ms=NOW_MS + 3 * DAY_MS
        )
        sections = decisions._q_prop_bookmakers(conn, _Args(since="20260901"))
        assert _books(sections) == {"weekend"}


class TestTheSportCutIsOptionalAndExact:
    """Mutation: drop ` AND (:sport IS NULL OR sport_key = :sport) `."""

    def test_naming_a_sport_excludes_the_others(self, conn):
        _prop_row(conn, book="mlb_book", sport="baseball_mlb", commence_ms=NOW_MS)
        _prop_row(
            conn, book="nfl_book", sport="americanfootball_nfl", commence_ms=NOW_MS
        )
        sections = decisions._q_prop_bookmakers(
            conn, _Args(since="20260901", sport="americanfootball_nfl")
        )
        assert _books(sections) == {"nfl_book"}

    def test_no_sport_means_every_sport(self, conn):
        _prop_row(conn, book="mlb_book", sport="baseball_mlb", commence_ms=NOW_MS)
        _prop_row(
            conn, book="nfl_book", sport="americanfootball_nfl", commence_ms=NOW_MS
        )
        sections = decisions._q_prop_bookmakers(conn, _Args(since="20260901"))
        assert _books(sections) == {"mlb_book", "nfl_book"}

    def test_a_team_row_is_never_counted_as_a_prop(self, conn):
        """`outcome_description` is the discriminator; a team market leaves it
        NULL and must not appear however many rows it has."""
        conn.execute(
            "INSERT INTO odds_snapshots (odds_event_id, sport_key, commence_ms, "
            "home_team, away_team, bookmaker, market, outcome_name, "
            "price_decimal, fetched_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "ev-team", "baseball_mlb", NOW_MS, "Home", "Away",
                "team_only", "h2h", "Mets", 1.8, 1,
            ),
        )
        conn.commit()
        _prop_row(conn, book="prop_book", sport="baseball_mlb", commence_ms=NOW_MS)
        sections = decisions._q_prop_bookmakers(conn, _Args(since="20260901"))
        assert _books(sections) == {"prop_book"}


class TestTheDefaultIsAWindowNotTheWholeTable:
    """Mutation: `_bookmakers_since_ms` returning 0 when `--since` is absent."""

    def test_an_absent_since_still_produces_a_recent_floor(self):
        floor = decisions._bookmakers_since_ms(_Args())
        expected = decisions._BOOKMAKERS_DEFAULT_DAYS * DAY_MS
        # Within a day of "now minus the default window", not near the epoch.
        assert floor > 1_700_000_000_000, floor
        now_ms = floor + expected
        assert abs(now_ms - int(__import__("time").time() * 1000)) < DAY_MS

    def test_a_malformed_since_is_refused_rather_than_ignored(self):
        """A silently ignored bound is an unbounded query wearing a flag."""
        with pytest.raises(ValueError, match="YYYYMMDD"):
            decisions._bookmakers_since_ms(_Args(since="last-tuesday"))


class TestThePlanDoesNotScanTheTable:
    def test_the_range_rides_an_index_on_commence_ms(self, conn):
        steps = plan(
            conn,
            decisions._SQL_PROP_BOOKMAKERS,
            {"since": NOW_MS - 7 * DAY_MS, "sport": None},
        )
        assert not any(
            s.startswith("SCAN odds_snapshots") and "INDEX" not in s for s in steps
        ), steps
        assert any("commence_ms>?" in s for s in steps), steps

    def test_naming_a_sport_does_not_make_it_worse(self, conn):
        steps = plan(
            conn,
            decisions._SQL_PROP_BOOKMAKERS,
            {"since": NOW_MS - 7 * DAY_MS, "sport": "baseball_mlb"},
        )
        assert not any(
            s.startswith("SCAN odds_snapshots") and "INDEX" not in s for s in steps
        ), steps


class TestTheSectionSaysWhichPopulationItCounted:
    def test_the_window_is_reported_beside_the_counts(self, conn):
        """A windowed count and a lifetime count are different numbers. This
        repo has already paid for two quantities sharing one name."""
        _prop_row(conn, book="b", sport="baseball_mlb", commence_ms=NOW_MS)
        sections = decisions._q_prop_bookmakers(conn, _Args(since="20260901"))
        assert len(sections) == 2
        assert "window" in sections[0].title.lower()
        assert "commencing at or after" in sections[1].title

    def test_the_title_names_the_sport_when_one_is_cut(self, conn):
        _prop_row(conn, book="b", sport="baseball_mlb", commence_ms=NOW_MS)
        sections = decisions._q_prop_bookmakers(
            conn, _Args(since="20260901", sport="baseball_mlb")
        )
        assert "baseball_mlb" in sections[1].title
