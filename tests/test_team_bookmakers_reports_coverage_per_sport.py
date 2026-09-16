"""`team-bookmakers` answers per sport, on a slice, and never infers an absence.

The team path is the one that runs. `ODDS_BUY_PROPS_ON_SCHEDULE` is `"false"`
and the props card has 0 taps in 77 lifetime lookups, so `prop-bookmakers`
returned 0 rows on every sport over a fortnight; everything the desk actually
prices comes off the rows this query reads, and nothing in the repo reported
them per sport.

Why per sport is the grain that matters. `consensus_devig`
(`backend/core/devig.py`) reads

    sharp = {b: r for b, r in usable.items() if sharp_books and b in sharp_books}
    selected = sharp or usable

so a sport no sharp book quotes raises nothing and logs nothing: `sharp` is
empty, and the consensus silently falls back to every book it has, soft ones
included. Three sharps are bought and one of them quotes `h2h` only, so the
`markets` column is load-bearing -- a book present on a sport but absent from
`spreads` is exactly the case a quote count would hide.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Nothing about live timing or live coverage.** These tests insert their own
  rows. Whether the ten named keys actually came back on NCAAF, NFL and WNBA
  is answered by running the query on live, and only there.
- **Nothing about the plan's cost in rows.** A plan names the access method,
  never the rows it touches. What makes this bounded is that `commence_ms` is
  a range on an index (ADR 0157); the live read is the measurement.
- **The `--sport` plan test does not guard the time bound.** See
  `TestThePlanDoesNotScanTheTable`: `idx_odds_sport_commence` leads with
  `sport_key`, so that call still seeks with the floor removed. Measured, not
  reasoned about.

Mutations, one per class, each observed red:
  1. drop ` AND commence_ms >= :since ` from `_SQL_TEAM_BOOKMAKERS`
  2. `GROUP BY bookmaker` instead of `GROUP BY sport_key, bookmaker`
  3. `outcome_description IS NOT NULL` instead of `IS NULL`
  4. drop `GROUP_CONCAT(DISTINCT market) AS markets`
  5. `_requested_books_section` falling back to a hardcoded list when
     `ODDS_BOOKMAKERS` is unset
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
    """The namespace attributes `_q_team_bookmakers` reads.

    `since` and `sport` default to `None` because the unfiltered call is the
    one a live run actually makes.
    """

    def __init__(self, *, limit=2000, since=None, sport=None, day_start_hour=10):
        self.limit = limit
        self.since = since
        self.sport = sport
        self.day_start_hour = day_start_hour


@pytest.fixture
def conn():
    path = os.path.join(tempfile.mkdtemp(), "team.db")
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    with open(SCHEMA, encoding="utf-8") as fh:
        c.executescript(fh.read())
    yield c
    c.close()


def _team_row(conn, *, book, sport, commence_ms, market="h2h", outcome="Home"):
    """One team-market row: `outcome_description` stays NULL, which is the
    discriminator this query selects on."""
    conn.execute(
        "INSERT INTO odds_snapshots (odds_event_id, sport_key, commence_ms, "
        "home_team, away_team, bookmaker, market, outcome_name, "
        "price_decimal, fetched_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            f"ev-{sport}-{commence_ms}",
            sport,
            commence_ms,
            "Home",
            "Away",
            book,
            market,
            outcome,
            1.9,
            commence_ms - 3600_000,
        ),
    )
    conn.commit()


def _prop_row(conn, *, book, sport, commence_ms):
    conn.execute(
        "INSERT INTO odds_snapshots (odds_event_id, sport_key, commence_ms, "
        "home_team, away_team, bookmaker, market, outcome_name, "
        "outcome_description, price_decimal, fetched_ms) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            f"ev-prop-{sport}-{commence_ms}",
            sport,
            commence_ms,
            "Home",
            "Away",
            book,
            "pitcher_strikeouts",
            "Over",
            "A. Player",
            1.9,
            commence_ms - 3600_000,
        ),
    )
    conn.commit()


def _data(sections):
    """The response section: the one carrying both `sport_key` and `markets`."""
    hits = [s for s in sections if "sport_key" in s.columns and "markets" in s.columns]
    assert hits, [s.title for s in sections]
    return hits[0]


def _pairs(sections):
    """`(sport_key, bookmaker)` of every response row, as a set."""
    section = _data(sections)
    sport_i = section.columns.index("sport_key")
    book_i = section.columns.index("bookmaker")
    return {(r[sport_i], r[book_i]) for r in section.rows}


def _markets_for(sections, sport, book):
    section = _data(sections)
    sport_i = section.columns.index("sport_key")
    book_i = section.columns.index("bookmaker")
    markets_i = section.columns.index("markets")
    for row in section.rows:
        if row[sport_i] == sport and row[book_i] == book:
            return set(str(row[markets_i]).split(","))
    raise AssertionError(f"no row for {sport}/{book} in {section.rows}")


def plan(conn, sql, params):
    return [r["detail"] for r in conn.execute("EXPLAIN QUERY PLAN " + sql, params)]


class TestTheWindowExcludesWhatIsOutsideIt:
    """Mutation: drop ` AND commence_ms >= :since ` from the SQL."""

    def test_a_fixture_older_than_the_floor_is_not_counted(self, conn):
        _team_row(conn, book="inside", sport="baseball_mlb", commence_ms=NOW_MS)
        _team_row(
            conn,
            book="ancient",
            sport="baseball_mlb",
            commence_ms=NOW_MS - 400 * DAY_MS,
        )
        sections = decisions._q_team_bookmakers(conn, _Args(since="20260901"))
        assert _pairs(sections) == {("baseball_mlb", "inside")}

    def test_the_weekend_that_has_not_happened_is_inside_the_window(self, conn):
        """The floor is a floor, not a range. The fixtures anyone asks this
        about are the ones that have not been played."""
        _team_row(
            conn,
            book="weekend",
            sport="americanfootball_nfl",
            commence_ms=NOW_MS + 3 * DAY_MS,
        )
        sections = decisions._q_team_bookmakers(conn, _Args(since="20260901"))
        assert _pairs(sections) == {("americanfootball_nfl", "weekend")}


class TestTheGrainIsSportByBook:
    """Mutation: `GROUP BY bookmaker` instead of `GROUP BY sport_key, bookmaker`.

    This is the whole point of the subcommand. A book that covers MLB and not
    NFL is the finding; pooled across sports it reads as full coverage.
    """

    def test_one_book_on_two_sports_is_two_rows(self, conn):
        _team_row(conn, book="pinnacle", sport="baseball_mlb", commence_ms=NOW_MS)
        _team_row(
            conn, book="pinnacle", sport="americanfootball_nfl", commence_ms=NOW_MS
        )
        sections = decisions._q_team_bookmakers(conn, _Args(since="20260901"))
        assert _pairs(sections) == {
            ("baseball_mlb", "pinnacle"),
            ("americanfootball_nfl", "pinnacle"),
        }

    def test_a_book_missing_on_one_sport_is_visible_as_its_absence(self, conn):
        """The case the instrument exists for: a sharp book that covers one
        sport and not the other. Pooled, `pinnacle` looks present."""
        _team_row(conn, book="pinnacle", sport="baseball_mlb", commence_ms=NOW_MS)
        _team_row(conn, book="draftkings", sport="baseball_mlb", commence_ms=NOW_MS)
        _team_row(
            conn, book="draftkings", sport="americanfootball_ncaaf", commence_ms=NOW_MS
        )
        sections = decisions._q_team_bookmakers(conn, _Args(since="20260901"))
        pairs = _pairs(sections)
        assert ("americanfootball_ncaaf", "draftkings") in pairs
        assert ("americanfootball_ncaaf", "pinnacle") not in pairs

    def test_naming_a_sport_excludes_the_others(self, conn):
        _team_row(conn, book="mlb_book", sport="baseball_mlb", commence_ms=NOW_MS)
        _team_row(
            conn, book="nfl_book", sport="americanfootball_nfl", commence_ms=NOW_MS
        )
        sections = decisions._q_team_bookmakers(
            conn, _Args(since="20260901", sport="americanfootball_nfl")
        )
        assert _pairs(sections) == {("americanfootball_nfl", "nfl_book")}


class TestTheDiscriminatorIsTheOtherWayRoundFromProps:
    """Mutation: `outcome_description IS NOT NULL` instead of `IS NULL`."""

    def test_a_prop_row_is_never_counted_as_a_team_market(self, conn):
        _prop_row(conn, book="prop_only", sport="baseball_mlb", commence_ms=NOW_MS)
        _team_row(conn, book="team_book", sport="baseball_mlb", commence_ms=NOW_MS)
        sections = decisions._q_team_bookmakers(conn, _Args(since="20260901"))
        assert _pairs(sections) == {("baseball_mlb", "team_book")}

    def test_the_two_subcommands_partition_the_same_rows(self, conn):
        """Every row is in exactly one of the two populations. If both queries
        claimed a row, or neither did, the discriminator has drifted."""
        _prop_row(conn, book="both", sport="baseball_mlb", commence_ms=NOW_MS)
        _team_row(conn, book="both", sport="baseball_mlb", commence_ms=NOW_MS)
        team = decisions._q_team_bookmakers(conn, _Args(since="20260901"))
        props = decisions._q_prop_bookmakers(conn, _Args(since="20260901"))
        team_quotes = sum(
            r[_data(team).columns.index("quotes")] for r in _data(team).rows
        )
        prop_section = [s for s in props if "bookmaker" in s.columns and s.rows][0]
        prop_quotes = sum(
            r[prop_section.columns.index("quotes")] for r in prop_section.rows
        )
        assert team_quotes == 1
        assert prop_quotes == 1


class TestTheMarketsAreNamedNotCounted:
    """Mutation: drop `GROUP_CONCAT(DISTINCT market) AS markets`.

    `betfair_ex_eu` is known to quote `h2h` and neither `spreads` nor
    `totals`, so spreads and totals anchor on two sharps rather than three. A
    quote count cannot show that; the market list can.
    """

    def test_a_book_on_one_market_only_says_which_one(self, conn):
        _team_row(
            conn,
            book="betfair_ex_eu",
            sport="baseball_mlb",
            commence_ms=NOW_MS,
            market="h2h",
        )
        _team_row(
            conn,
            book="pinnacle",
            sport="baseball_mlb",
            commence_ms=NOW_MS,
            market="h2h",
        )
        _team_row(
            conn,
            book="pinnacle",
            sport="baseball_mlb",
            commence_ms=NOW_MS,
            market="spreads",
        )
        sections = decisions._q_team_bookmakers(conn, _Args(since="20260901"))
        assert _markets_for(sections, "baseball_mlb", "betfair_ex_eu") == {"h2h"}
        assert _markets_for(sections, "baseball_mlb", "pinnacle") == {
            "h2h",
            "spreads",
        }

    def test_repeated_quotes_on_one_market_do_not_multiply_it(self, conn):
        for outcome in ("Home", "Away"):
            _team_row(
                conn,
                book="fanduel",
                sport="baseball_mlb",
                commence_ms=NOW_MS,
                market="h2h",
                outcome=outcome,
            )
        sections = decisions._q_team_bookmakers(conn, _Args(since="20260901"))
        assert _markets_for(sections, "baseball_mlb", "fanduel") == {"h2h"}


class TestTheRequestIsPrintedBesideTheResponse:
    """Mutation: `_requested_books_section` falling back to a hardcoded list.

    An absence in the response has three causes that this table cannot
    separate -- the book quotes nothing, the sport had no fixture, or the key
    is misspelled and was dropped by the vendor while still costing a slot.
    Printing the request is what lets a reader rule the third one out. Guessing
    the request would make the other two unreadable too.
    """

    def test_the_keys_are_listed_in_the_order_the_request_sends_them(
        self, monkeypatch
    ):
        monkeypatch.setenv(
            decisions._ODDS_BOOKMAKERS_ENV, "pinnacle,matchbook, betfair_ex_eu"
        )
        section = decisions._requested_books_section()
        assert section.rows == [
            (1, "pinnacle"),
            (2, "matchbook"),
            (3, "betfair_ex_eu"),
        ]

    def test_an_unset_variable_yields_no_rows_and_says_so(self, monkeypatch):
        """Unreadable resolves to nothing, never to a plausible list."""
        monkeypatch.delenv(decisions._ODDS_BOOKMAKERS_ENV, raising=False)
        section = decisions._requested_books_section()
        assert section.rows == []
        assert "unset or blank" in section.title
        assert "Nothing is inferred" in section.title

    def test_a_blank_variable_is_the_same_as_unset(self, monkeypatch):
        monkeypatch.setenv(decisions._ODDS_BOOKMAKERS_ENV, "  ,  ,")
        assert decisions._requested_books_section().rows == []

    def test_the_request_section_travels_with_the_query(self, conn, monkeypatch):
        monkeypatch.setenv(decisions._ODDS_BOOKMAKERS_ENV, "pinnacle,fanduel")
        _team_row(conn, book="pinnacle", sport="baseball_mlb", commence_ms=NOW_MS)
        sections = decisions._q_team_bookmakers(conn, _Args(since="20260901"))
        assert len(sections) == 3
        assert "window" in sections[0].title.lower()
        assert decisions._ODDS_BOOKMAKERS_ENV in sections[1].title
        assert [r[1] for r in sections[1].rows] == ["pinnacle", "fanduel"]


class TestThePlanDoesNotScanTheTable:
    """Only the FIRST of these two detects the loss of the time bound.

    Measured, not assumed: with mutation 1 applied (`commence_ms >= :since`
    replaced by `1 = 1`) this class runs 1 failed, 1 passed. The unfiltered
    call goes red; the `--sport` call stays green, because
    `idx_odds_sport_commence` leads with `sport_key` and still serves a seek on
    the equality alone. That is a real bound -- one sport instead of the table
    -- but it is not the time bound, and a reader who took the second test as
    proof of the floor would be wrong. The floor's guard is the first test and
    the four behavioural classes above it.
    """

    def test_the_range_rides_an_index_on_commence_ms(self, conn):
        steps = plan(
            conn,
            decisions._SQL_TEAM_BOOKMAKERS,
            {"since": NOW_MS - 7 * DAY_MS, "sport": None},
        )
        assert not any(
            s.startswith("SCAN odds_snapshots") and "INDEX" not in s for s in steps
        ), steps
        assert any("commence_ms>?" in s for s in steps), steps

    def test_naming_a_sport_seeks_rather_than_scans(self, conn):
        steps = plan(
            conn,
            decisions._SQL_TEAM_BOOKMAKERS,
            {"since": NOW_MS - 7 * DAY_MS, "sport": "americanfootball_nfl"},
        )
        assert not any(
            s.startswith("SCAN odds_snapshots") and "INDEX" not in s for s in steps
        ), steps


class TestTheSectionSaysWhichPopulationItCounted:
    def test_the_window_is_reported_beside_the_counts(self, conn):
        """A windowed count and a lifetime count are different numbers."""
        _team_row(conn, book="b", sport="baseball_mlb", commence_ms=NOW_MS)
        sections = decisions._q_team_bookmakers(conn, _Args(since="20260901"))
        assert "commencing at or after" in _data(sections).title

    def test_the_title_names_the_sport_when_one_is_cut(self, conn):
        _team_row(conn, book="b", sport="baseball_mlb", commence_ms=NOW_MS)
        sections = decisions._q_team_bookmakers(
            conn, _Args(since="20260901", sport="baseball_mlb")
        )
        assert "baseball_mlb" in _data(sections).title


class TestTheSubcommandIsReachable:
    def test_it_is_registered_and_resolves(self):
        inspect = importlib.import_module("inspect_live_db")
        assert "team-bookmakers" in inspect.QUERIES
        assert inspect.QUERIES["team-bookmakers"].run is decisions._q_team_bookmakers
