"""The spreads pricing path (ADR 0070): subtitle parser, rung grouping,
link inheritance, and the fair rows the parlay desk reads.

What these tests establish: the one subtitle parser reads every spread rung
in the captured events fixture and refuses everything else; a book joins a
rung only two-sided and complementary; different main lines are different
rungs; each rung devigs once and writes one `fair_prices` row per side with
that side's OWN point and the consensus's input age; the path writes NO
`recommendations` row; and a spread event inherits its game's link under its
own method name.

What they do not establish: that Kalshi's spread grammar never changes (a new
phrasing fails the parser and the market is refused — that refusal is the
design), or anything about totals, which are out of scope.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.kalshi.discovery import DiscoveredEvent, DiscoveredMarket
from backend.kalshi.spreads import MARKET_TYPE_SPREAD, parse_spread_subtitle
from backend.match.linker import (
    SPREAD_LINK_METHOD,
    LinkedFixture,
    link_prop_event,
)
from backend.runner import (
    PassCounts,
    _price_spread_event,
    spread_quotes_for_event,
)
from backend.match.linker import TeamAliases
from backend.store import db as store

FIXTURE = Path(__file__).parent / "fixtures" / "events_sports_nested.json"

NOW = 1_700_000_000_000


class TestTheSubtitleParser:
    def test_every_spread_rung_in_the_captured_fixture_parses(self):
        """The grammar is pinned to the wire, not to examples: every spread
        market Kalshi actually published in the capture must parse, and its
        margin must equal its own `floor_strike`."""
        events = json.loads(FIXTURE.read_text(encoding="utf-8"))
        rungs = 0
        for event in events:
            if "SPREAD" not in event.get("event_ticker", ""):
                continue
            for market in event.get("markets", []):
                subtitle = market.get("yes_sub_title")
                parsed = parse_spread_subtitle(subtitle)
                assert parsed is not None, subtitle
                team, margin = parsed
                assert team
                assert margin == pytest.approx(float(market["floor_strike"]))
                rungs += 1
        assert rungs > 20, "the fixture should carry a real spread population"

    def test_examples_and_refusals(self):
        assert parse_spread_subtitle("St. Louis wins by over 2.5 runs") == (
            "St. Louis", 2.5
        )
        assert parse_spread_subtitle(
            "British Columbia Lions wins by over 20.5 points"
        ) == ("British Columbia Lions", 20.5)
        # Anything the grammar does not cover refuses — never a guess.
        assert parse_spread_subtitle("Combined score over 8.5") is None
        assert parse_spread_subtitle("Anthony Kay: 2+") is None
        assert parse_spread_subtitle("") is None
        assert parse_spread_subtitle(None) is None


def _seed_spread_rows(conn, *, rows, fetched_ms=NOW - 10_000):
    for team, point, price, book in rows:
        conn.execute(
            "INSERT INTO odds_snapshots (fetched_ms, book_updated_ms, "
            "sport_key, odds_event_id, commence_ms, home_team, away_team, "
            "bookmaker, market, outcome_name, outcome_point, price_decimal) "
            "VALUES (?, ?, 'baseball_mlb', 'game-1', ?, 'Home', 'Away', ?, "
            "'spreads', ?, ?, ?)",
            (fetched_ms, fetched_ms - 5_000, NOW + 3_600_000, book, team,
             point, price),
        )


@pytest.fixture
def conn(tmp_path):
    connection = store.init_db(tmp_path / "spreads.db")
    yield connection
    connection.close()


class TestRungGrouping:
    def test_a_two_sided_complementary_pair_forms_a_rung(self, conn):
        _seed_spread_rows(conn, rows=[
            ("Home", -1.5, 2.58, "pinnacle"),
            ("Away", 1.5, 1.52, "pinnacle"),
        ])
        lines = spread_quotes_for_event(conn, "game-1", now=NOW)
        assert len(lines) == 1
        line = lines[0]
        assert line.points == {"Home": -1.5, "Away": 1.5}
        assert "pinnacle" in line.books.quotes_by_book
        # Input age = now - book_updated_ms of the stalest contributor.
        assert line.books.oldest_book_age_ms == 15_000

    def test_a_one_sided_book_is_dropped_whole(self, conn):
        _seed_spread_rows(conn, rows=[
            ("Home", -1.5, 2.58, "pinnacle"),
            ("Away", 1.5, 1.52, "pinnacle"),
            ("Home", -1.5, 2.60, "draftkings"),  # no Away side
        ])
        lines = spread_quotes_for_event(conn, "game-1", now=NOW)
        assert len(lines) == 1
        assert list(lines[0].books.quotes_by_book) == ["pinnacle"]

    def test_non_complementary_points_are_not_a_rung(self, conn):
        _seed_spread_rows(conn, rows=[
            ("Home", -1.5, 2.58, "pinnacle"),
            ("Away", 2.5, 1.52, "pinnacle"),
        ])
        assert spread_quotes_for_event(conn, "game-1", now=NOW) == []

    def test_books_at_different_main_lines_are_different_rungs(self, conn):
        _seed_spread_rows(conn, rows=[
            ("Home", -1.5, 2.58, "pinnacle"),
            ("Away", 1.5, 1.52, "pinnacle"),
            ("Home", -2.5, 3.40, "draftkings"),
            ("Away", 2.5, 1.30, "draftkings"),
        ])
        lines = spread_quotes_for_event(conn, "game-1", now=NOW)
        assert len(lines) == 2
        assert {frozenset(l.points.values()) for l in lines} == {
            frozenset({-1.5, 1.5}), frozenset({-2.5, 2.5})
        }

    def test_only_the_latest_sweep_speaks(self, conn):
        _seed_spread_rows(conn, rows=[
            ("Home", -1.5, 9.99, "pinnacle"),
            ("Away", 1.5, 1.01, "pinnacle"),
        ], fetched_ms=NOW - 3_600_000)
        _seed_spread_rows(conn, rows=[
            ("Home", -1.5, 2.58, "pinnacle"),
            ("Away", 1.5, 1.52, "pinnacle"),
        ])
        lines = spread_quotes_for_event(conn, "game-1", now=NOW)
        assert len(lines) == 1
        assert lines[0].books.quotes_by_book["pinnacle"][0] == 2.58


def _spread_event(*, strike=1.5, subtitle=None, ticker="KXMLBSPREAD-26AUG01HOMAWA-HOM1"):
    market = DiscoveredMarket(
        ticker=ticker,
        event_ticker="KXMLBSPREAD-26AUG01HOMAWA",
        series_ticker="KXMLBSPREAD",
        market_type=MARKET_TYPE_SPREAD,
        title="Home wins by over 1.5 runs?",
        yes_side=subtitle or f"Home wins by over {strike} runs",
        strike=strike,
        close_ms=None,
        status="active",
        volume_24h=0.0,
        open_interest=0.0,
        price_structure="linear_cent",
    )
    return DiscoveredEvent(
        event_ticker="KXMLBSPREAD-26AUG01HOMAWA",
        series_ticker="KXMLBSPREAD",
        league="MLB",
        sport_key="baseball_mlb",
        market_type=MARKET_TYPE_SPREAD,
        title="Home vs Away spread",
        commence_ms=NOW + 3_600_000,
        markets=(market,),
    )


def _link(conn) -> int:
    conn.execute(
        "INSERT INTO kalshi_events (event_ticker, first_seen_ms, last_seen_ms) "
        "VALUES ('KXMLBSPREAD-26AUG01HOMAWA', 0, 0)"
    )
    cursor = conn.execute(
        "INSERT INTO event_links (kalshi_event_ticker, odds_event_id, league, "
        "method, commence_skew_ms, linked_ms) "
        "VALUES ('KXMLBSPREAD-26AUG01HOMAWA', 'game-1', 'baseball_mlb', ?, 0, 0)",
        (SPREAD_LINK_METHOD,),
    )
    return int(cursor.lastrowid)


class TestThePricingPath:
    def _run(self, conn, event=None):
        link_id = _link(conn)
        counts = PassCounts()
        _price_spread_event(
            conn,
            event or _spread_event(),
            link_id=link_id,
            stamp=NOW,
            counts=counts,
            aliases=TeamAliases(sport_key="baseball_mlb"),
            odds_event_id="game-1",
        )
        return counts

    def test_one_devig_per_rung_two_rows_with_their_own_points(self, conn):
        _seed_spread_rows(conn, rows=[
            ("Home", -1.5, 2.58, "pinnacle"),
            ("Away", 1.5, 1.52, "pinnacle"),
            ("Home", -1.5, 2.55, "draftkings"),
            ("Away", 1.5, 1.54, "draftkings"),
        ])
        counts = self._run(conn)
        rows = conn.execute(
            "SELECT * FROM fair_prices WHERE market = 'spreads' "
            "ORDER BY outcome_point"
        ).fetchall()
        assert counts.fair_prices_written == 2
        assert [r["outcome_name"] for r in rows] == ["Home", "Away"]
        assert [r["outcome_point"] for r in rows] == [-1.5, 1.5]
        assert all(r["oldest_book_age_ms"] is not None for r in rows)
        assert all(0.0 < r["p_conservative"] < 1.0 for r in rows)

    def test_the_path_writes_no_recommendation(self, conn):
        """Fair rows only (ADR 0070): spreads stay off the gate, the board,
        and ADR 0038's single-regime evidence record."""
        _seed_spread_rows(conn, rows=[
            ("Home", -1.5, 2.58, "pinnacle"),
            ("Away", 1.5, 1.52, "pinnacle"),
        ])
        self._run(conn)
        n = conn.execute("SELECT COUNT(*) AS n FROM recommendations").fetchone()
        assert n["n"] == 0

    def test_a_subtitle_strike_disagreement_refuses_the_market(self, conn):
        """One number published twice; a disagreement means one copy is not
        what this code thinks it is, and neither may be trusted silently."""
        _seed_spread_rows(conn, rows=[
            ("Home", -1.5, 2.58, "pinnacle"),
            ("Away", 1.5, 1.52, "pinnacle"),
        ])
        counts = self._run(
            conn,
            _spread_event(strike=2.5, subtitle="Home wins by over 1.5 runs"),
        )
        assert counts.fair_prices_written == 0
        assert any("floor_strike" in e for e in counts.errors)

    def test_a_started_game_is_dropped_by_the_books_clock(self, conn):
        for team, point, price, book in [
            ("Home", -1.5, 2.58, "pinnacle"), ("Away", 1.5, 1.52, "pinnacle"),
        ]:
            conn.execute(
                "INSERT INTO odds_snapshots (fetched_ms, sport_key, "
                "odds_event_id, commence_ms, home_team, away_team, bookmaker, "
                "market, outcome_name, outcome_point, price_decimal) "
                "VALUES (?, 'baseball_mlb', 'game-1', ?, 'Home', 'Away', ?, "
                "'spreads', ?, ?, ?)",
                (NOW - 10_000, NOW - 60_000, book, team, point, price),
            )
        counts = self._run(conn)
        assert counts.fair_prices_written == 0
        assert counts.dropped_game_started == 1

    def test_a_rung_the_books_do_not_quote_is_counted(self, conn):
        _seed_spread_rows(conn, rows=[
            ("Home", -2.5, 3.40, "pinnacle"),
            ("Away", 2.5, 1.30, "pinnacle"),
        ])
        counts = self._run(conn)  # Kalshi rung is 1.5; books quote 2.5
        assert counts.fair_prices_written == 0
        assert counts.dropped_unresolved_outcome == 1
        # And NOT as an unknown unit -- "runs" parsed fine.
        assert counts.dropped_unknown_spread_unit == 0


class TestAnUnreadUnitIsCountedApart:
    """2026-08-24 code review, finding 8.

    The subtitle regex whitelists `runs?|points?`. NHL ("goals") and soccer
    enter seasonal scope with `ODDS_MARKETS = "h2h,spreads"` already paying
    the doubled credit for them, and every one of their markets would have
    landed in `dropped_unresolved_outcome` -- the same bucket as "the books
    quote no price at this rung", which is what a quiet night looks like. A
    whole league producing zero spread supply would have been invisible.
    """

    def _run(self, conn, event):
        link_id = _link(conn)
        counts = PassCounts()
        _price_spread_event(
            conn, event, link_id=link_id, stamp=NOW, counts=counts,
            aliases=TeamAliases(sport_key="baseball_mlb"),
            odds_event_id="game-1",
        )
        return counts

    def test_goals_are_counted_as_an_unknown_unit(self, conn):
        _seed_spread_rows(conn, rows=[
            ("Home", -1.5, 2.58, "pinnacle"),
            ("Away", 1.5, 1.52, "pinnacle"),
        ])
        counts = self._run(
            conn, _spread_event(subtitle="Home wins by over 1.5 goals")
        )
        assert counts.fair_prices_written == 0
        assert counts.dropped_unknown_spread_unit == 1
        assert counts.dropped_unresolved_outcome == 0

    def test_an_unparseable_subtitle_is_still_the_other_bucket(self, conn):
        """The split must not swallow genuine parse failures -- a subtitle
        that does not fit the grammar at all is not a units problem."""
        _seed_spread_rows(conn, rows=[
            ("Home", -1.5, 2.58, "pinnacle"),
            ("Away", 1.5, 1.52, "pinnacle"),
        ])
        counts = self._run(
            conn, _spread_event(subtitle="Home covers the run line")
        )
        assert counts.dropped_unknown_spread_unit == 0
        assert counts.dropped_unresolved_outcome == 1

    def test_the_counter_reaches_the_pass_line_even_at_zero(self):
        """Absent cannot be told from "no league is unreadable", and those
        need opposite responses."""
        from backend.runner import PassCounts as _PC

        assert "dropped_unknown_spread_unit" in _PC.ALWAYS_REPORT


class TestTheJoinIdentityIsWrittenOnce:
    """2026-08-24 code review, finding 9. Kalshi's `"T wins by over S"` YES is
    the book's `(T, -S)`; that sign convention was written out in the runner
    and again in the parlay desk's reader, and a duplicated sign convention is
    one that can drift."""

    def test_the_helper_is_the_identity(self):
        from backend.kalshi.spreads import spread_book_point

        assert spread_book_point(1.5) == -1.5
        assert spread_book_point(18.0) == -18.0

    def test_both_callers_import_it_rather_than_negating_by_hand(self):
        """A source check, because the defect is duplication -- two correct
        copies pass every behavioural test right up until one is edited."""
        import backend.parlays as parlays_module
        import backend.runner as runner_module

        for module in (parlays_module, runner_module):
            assert hasattr(module, "spread_book_point"), module.__name__

    def test_the_cross_check_is_shared_too(self, conn):
        """The margin-vs-strike cross-check lived only in the runner, so the
        parlay ladder could match a subtitle-drifted market to a stale fair
        row until freshness aged it out."""
        from backend.kalshi.spreads import spread_margin_agrees

        assert spread_margin_agrees(1.5, 1.5)
        assert not spread_margin_agrees(1.5, 2.5)
        # A market with no published strike agrees with nothing -- unreadable
        # resolves to a refusal, never to a match.
        assert not spread_margin_agrees(1.5, None)


class TestLinkInheritance:
    def test_a_spread_event_inherits_under_its_own_method_name(self):
        result = link_prop_event(
            kalshi_event_ticker="KXMLBSPREAD-26AUG151310CWSDET",
            kalshi_commence_ms=NOW,
            linked_fixtures=[
                LinkedFixture(
                    fixture="26AUG151310CWSDET",
                    odds_event_id="game-9",
                    odds_commence_ms=NOW + 1_000,
                )
            ],
            method=SPREAD_LINK_METHOD,
        )
        assert result.matched
        assert result.method == SPREAD_LINK_METHOD
