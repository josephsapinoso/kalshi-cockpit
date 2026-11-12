"""The game-total (over/under) pricing path: subtitle parser, rung grouping,
link inheritance, and the fair rows the parlay desk reads.

What these tests establish: the one subtitle parser reads every total rung in
the captured events fixture (MLB "runs", WNBA "points") and refuses
everything else; a book joins a rung only two-sided at one line; different
lines are different rungs; each rung devigs once and writes one `fair_prices`
row per side at the shared point with the consensus's input age; the path
writes NO `recommendations` row; the join identity is the identity function
and both callers import it; and a total event inherits its game's link under
its own method name instead of being refused by the two-team bijection.

What they do not establish: that Kalshi's total grammar never changes (a new
phrasing fails the parser and the market is refused -- that refusal is the
design); which unit NFL totals are published in (no NFL total is in any
fixture; an unrecognised unit is counted by name, never guessed); anything
about `TEAMTOTAL`, which is out of scope; or that a `totals` row is ever
BOUGHT -- that is `ODDS_MARKETS`, a config decision this file cannot see.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.kalshi.discovery import DiscoveredEvent, DiscoveredMarket
import re

from backend.kalshi.totals import (
    total_line_is_half_point,
    MARKET_TYPE_TOTAL,
    TOTALS_MARKET,
    parse_total_subtitle,
    total_book_point,
    total_line_agrees,
    unrecognised_total_unit,
)
from backend.match.linker import (
    EXACT_ALIAS_PAIR,
    TOTAL_LINK_METHOD,
    LinkedFixture,
    link_prop_event,
)
from backend.runner import (
    DERIVED_LINK_METHODS,
    PassCounts,
    _price_totals_event,
    link_discovered_events,
    totals_quotes_for_event,
)
from backend.store import db as store

FIXTURE = Path(__file__).parent / "fixtures" / "events_sports_nested.json"

NOW = 1_700_000_000_000


class TestTheSubtitleParser:
    def test_every_total_rung_in_the_captured_fixture_parses_and_agrees_with_strike(self):
        """The grammar is pinned to the wire: every `*TOTAL` market Kalshi
        published in the capture must parse, and its line must equal its own
        `floor_strike`. Two leagues, two units. Mutation: `_KNOWN_UNITS` ->
        `r"runs?"` drops the WNBA population and this fails."""
        events = json.loads(FIXTURE.read_text(encoding="utf-8"))
        rungs = 0
        units: set[str] = set()
        for event in events:
            ticker = event.get("event_ticker", "")
            if "TOTAL" not in ticker or "TEAMTOTAL" in ticker:
                continue
            for market in event.get("markets", []):
                subtitle = market.get("yes_sub_title")
                line = parse_total_subtitle(subtitle)
                assert line is not None, subtitle
                assert line == pytest.approx(float(market["floor_strike"]))
                assert total_line_agrees(line, market["floor_strike"])
                units.add(subtitle.rsplit(" ", 2)[-2])
                rungs += 1
        assert rungs > 40, f"only {rungs} rungs -- is the capture populated?"
        assert units == {"runs", "points"}, units

    def test_examples_and_refusals(self):
        assert parse_total_subtitle("Over 8.5 runs scored") == 8.5
        assert parse_total_subtitle("Over 180.5 points scored") == 180.5
        assert parse_total_subtitle("Over 47 points scored") == 47.0
        # Anything the grammar does not cover refuses -- never a guess.
        assert parse_total_subtitle("Under 8.5 runs scored") is None
        assert parse_total_subtitle("St. Louis wins by over 2.5 runs") is None
        assert parse_total_subtitle("Anthony Kay: 2+") is None
        assert parse_total_subtitle("Boston: Over 4.5 runs scored") is None
        assert parse_total_subtitle("") is None
        assert parse_total_subtitle(None) is None

    def test_an_unread_unit_is_named_apart_from_a_parse_failure(self):
        assert unrecognised_total_unit("Over 5.5 goals scored") == "goals"
        assert unrecognised_total_unit("Over 8.5 runs scored") is None
        assert unrecognised_total_unit("Combined score over 8.5") is None
        assert unrecognised_total_unit(None) is None

    def test_the_cross_check_refuses_an_absent_strike(self):
        assert total_line_agrees(8.5, 8.5)
        assert not total_line_agrees(8.5, 9.5)
        assert not total_line_agrees(8.5, None)


def _seed_total_rows(conn, *, rows, fetched_ms=NOW - 10_000):
    for side, point, price, book in rows:
        conn.execute(
            "INSERT INTO odds_snapshots (fetched_ms, book_updated_ms, "
            "sport_key, odds_event_id, commence_ms, home_team, away_team, "
            "bookmaker, market, outcome_name, outcome_point, price_decimal) "
            "VALUES (?, ?, 'baseball_mlb', 'game-1', ?, 'Home', 'Away', ?, "
            "?, ?, ?, ?)",
            (fetched_ms, fetched_ms - 5_000, NOW + 3_600_000, book,
             TOTALS_MARKET, side, point, price),
        )


@pytest.fixture
def conn(tmp_path):
    connection = store.init_db(tmp_path / "totals.db")
    yield connection
    connection.close()


class TestRungGrouping:
    def test_a_two_sided_pair_at_one_line_forms_a_rung(self, conn):
        _seed_total_rows(conn, rows=[
            ("Over", 8.5, 1.95, "pinnacle"),
            ("Under", 8.5, 1.95, "pinnacle"),
        ])
        lines = totals_quotes_for_event(conn, "game-1", now=NOW)
        assert len(lines) == 1
        line = lines[0]
        assert line.point == 8.5
        assert line.outcomes == ("Over", "Under")
        assert line.books.quotes_by_book == {"pinnacle": [1.95, 1.95]}
        assert line.books.oldest_book_age_ms == 15_000

    def test_a_one_sided_book_is_dropped_whole(self, conn):
        """Mutation: drop the `len(book_rows) != 2` admission and draftkings'
        lone Over joins the rung with no Under to devig against."""
        _seed_total_rows(conn, rows=[
            ("Over", 8.5, 1.95, "pinnacle"),
            ("Under", 8.5, 1.95, "pinnacle"),
            ("Over", 8.5, 1.90, "draftkings"),
        ])
        lines = totals_quotes_for_event(conn, "game-1", now=NOW)
        assert len(lines) == 1
        assert list(lines[0].books.quotes_by_book) == ["pinnacle"]

    def test_over_and_under_at_different_lines_are_not_a_rung(self, conn):
        _seed_total_rows(conn, rows=[
            ("Over", 8.5, 1.95, "pinnacle"),
            ("Under", 9.5, 1.95, "pinnacle"),
        ])
        assert totals_quotes_for_event(conn, "game-1", now=NOW) == []

    def test_books_at_different_lines_are_different_rungs(self, conn):
        _seed_total_rows(conn, rows=[
            ("Over", 8.5, 1.95, "pinnacle"),
            ("Under", 8.5, 1.95, "pinnacle"),
            ("Over", 9.0, 2.10, "draftkings"),
            ("Under", 9.0, 1.78, "draftkings"),
        ])
        lines = totals_quotes_for_event(conn, "game-1", now=NOW)
        assert {line.point for line in lines} == {8.5, 9.0}

    def test_prices_pair_to_sides_positionally_whatever_the_row_order(self, conn):
        """The devig is handed `("Over", "Under")` and a price list built in
        that order. A book whose Under row arrives first must not have its
        prices swapped."""
        _seed_total_rows(conn, rows=[
            ("Under", 8.5, 1.70, "pinnacle"),
            ("Over", 8.5, 2.20, "pinnacle"),
        ])
        lines = totals_quotes_for_event(conn, "game-1", now=NOW)
        assert lines[0].books.quotes_by_book["pinnacle"] == [2.20, 1.70]

    def test_only_the_latest_sweep_speaks(self, conn):
        _seed_total_rows(conn, rows=[
            ("Over", 8.5, 9.99, "pinnacle"),
            ("Under", 8.5, 1.01, "pinnacle"),
        ], fetched_ms=NOW - 3_600_000)
        _seed_total_rows(conn, rows=[
            ("Over", 8.5, 1.95, "pinnacle"),
            ("Under", 8.5, 1.95, "pinnacle"),
        ])
        lines = totals_quotes_for_event(conn, "game-1", now=NOW)
        assert len(lines) == 1
        assert lines[0].books.quotes_by_book["pinnacle"][0] == 1.95


EVENT_TICKER = "KXMLBTOTAL-26AUG01HOMAWA"


def _total_event(*, strike=8.5, subtitle=None, ticker=f"{EVENT_TICKER}-8"):
    market = DiscoveredMarket(
        ticker=ticker,
        event_ticker=EVENT_TICKER,
        series_ticker="KXMLBTOTAL",
        market_type=MARKET_TYPE_TOTAL,
        title="Over 8.5 runs scored?",
        yes_side=subtitle or f"Over {strike} runs scored",
        strike=strike,
        close_ms=None,
        status="active",
        volume_24h=0.0,
        open_interest=0.0,
        price_structure="linear_cent",
    )
    return DiscoveredEvent(
        event_ticker=EVENT_TICKER,
        series_ticker="KXMLBTOTAL",
        league="MLB",
        sport_key="baseball_mlb",
        market_type=MARKET_TYPE_TOTAL,
        title="Home vs Away total",
        commence_ms=NOW + 3_600_000,
        markets=(market,),
    )


def _link(conn) -> int:
    conn.execute(
        "INSERT INTO kalshi_events (event_ticker, first_seen_ms, last_seen_ms) "
        "VALUES (?, 0, 0)",
        (EVENT_TICKER,),
    )
    cursor = conn.execute(
        "INSERT INTO event_links (kalshi_event_ticker, odds_event_id, league, "
        "method, commence_skew_ms, linked_ms) "
        "VALUES (?, 'game-1', 'baseball_mlb', ?, 0, 0)",
        (EVENT_TICKER, TOTAL_LINK_METHOD),
    )
    return int(cursor.lastrowid)


class TestThePricingPath:
    def _run(self, conn, event=None):
        link_id = _link(conn)
        counts = PassCounts()
        _price_totals_event(
            conn,
            event or _total_event(),
            link_id=link_id,
            stamp=NOW,
            counts=counts,
            odds_event_id="game-1",
        )
        return counts

    def test_one_devig_per_line_two_rows_at_the_shared_point(self, conn):
        _seed_total_rows(conn, rows=[
            ("Over", 8.5, 1.95, "pinnacle"),
            ("Under", 8.5, 1.95, "pinnacle"),
            ("Over", 8.5, 1.91, "draftkings"),
            ("Under", 8.5, 1.99, "draftkings"),
        ])
        counts = self._run(conn)
        rows = conn.execute(
            "SELECT * FROM fair_prices WHERE market = ? ORDER BY outcome_name",
            (TOTALS_MARKET,),
        ).fetchall()
        assert counts.fair_prices_written == 2
        assert [r["outcome_name"] for r in rows] == ["Over", "Under"]
        assert [r["outcome_point"] for r in rows] == [8.5, 8.5]
        assert all(r["outcome_description"] is None for r in rows)
        assert all(r["oldest_book_age_ms"] is not None for r in rows)
        assert all(0.0 < r["p_conservative"] < 1.0 for r in rows)

    def test_the_path_writes_no_recommendation(self, conn):
        """Fair rows only, the spread rule (ADR 0070): totals stay off the
        gate, the board, and ADR 0038's single-regime evidence record."""
        _seed_total_rows(conn, rows=[
            ("Over", 8.5, 1.95, "pinnacle"),
            ("Under", 8.5, 1.95, "pinnacle"),
        ])
        self._run(conn)
        n = conn.execute("SELECT COUNT(*) AS n FROM recommendations").fetchone()
        assert n["n"] == 0

    def test_a_subtitle_strike_disagreement_refuses_the_market(self, conn):
        _seed_total_rows(conn, rows=[
            ("Over", 8.5, 1.95, "pinnacle"),
            ("Under", 8.5, 1.95, "pinnacle"),
        ])
        counts = self._run(
            conn, _total_event(strike=9.5, subtitle="Over 8.5 runs scored")
        )
        assert counts.fair_prices_written == 0
        assert any("floor_strike" in e for e in counts.errors)

    def test_a_started_game_is_dropped_by_the_books_clock(self, conn):
        for side, point, price, book in [
            ("Over", 8.5, 1.95, "pinnacle"), ("Under", 8.5, 1.95, "pinnacle"),
        ]:
            conn.execute(
                "INSERT INTO odds_snapshots (fetched_ms, sport_key, "
                "odds_event_id, commence_ms, home_team, away_team, bookmaker, "
                "market, outcome_name, outcome_point, price_decimal) "
                "VALUES (?, 'baseball_mlb', 'game-1', ?, 'Home', 'Away', ?, "
                "?, ?, ?, ?)",
                (NOW - 10_000, NOW - 60_000, book, TOTALS_MARKET, side, point,
                 price),
            )
        counts = self._run(conn)
        assert counts.fair_prices_written == 0
        assert counts.dropped_game_started == 1

    def test_a_line_the_books_do_not_quote_is_counted(self, conn):
        _seed_total_rows(conn, rows=[
            ("Over", 9.5, 1.95, "pinnacle"),
            ("Under", 9.5, 1.95, "pinnacle"),
        ])
        counts = self._run(conn)  # Kalshi rung is 8.5; books quote 9.5
        assert counts.fair_prices_written == 0
        assert counts.dropped_unresolved_outcome == 1
        assert counts.dropped_unknown_total_unit == 0

    def test_goals_are_counted_as_an_unknown_unit(self, conn):
        _seed_total_rows(conn, rows=[
            ("Over", 5.5, 1.95, "pinnacle"),
            ("Under", 5.5, 1.95, "pinnacle"),
        ])
        counts = self._run(
            conn, _total_event(strike=5.5, subtitle="Over 5.5 goals scored")
        )
        assert counts.fair_prices_written == 0
        assert counts.dropped_unknown_total_unit == 1
        assert counts.dropped_unresolved_outcome == 0

    def test_the_counter_reaches_the_pass_line_even_at_zero(self):
        assert "dropped_unknown_total_unit" in PassCounts.ALWAYS_REPORT


class TestTheJoinIdentityIsWrittenOnce:
    """The spread identity negates; the prop identity would shift by a
    half-point; the total identity is the identity function. A reader who
    knows two of the three and guesses the third is wrong two ways in three,
    so it has a name and both callers import it."""

    def test_the_helper_is_the_identity(self):
        assert total_book_point(8.5) == 8.5
        assert total_book_point(47) == 47.0

    def test_the_runner_imports_it_rather_than_comparing_by_hand(self):
        import backend.runner as runner_module

        assert hasattr(runner_module, "total_book_point")
        assert hasattr(runner_module, "total_line_agrees")


class TestLinkInheritance:
    def test_a_total_event_inherits_under_its_own_method_name(self):
        result = link_prop_event(
            kalshi_event_ticker="KXMLBTOTAL-26AUG151310CWSDET",
            kalshi_commence_ms=NOW,
            linked_fixtures=[
                LinkedFixture(
                    fixture="26AUG151310CWSDET",
                    odds_event_id="game-9",
                    odds_commence_ms=NOW + 1_000,
                )
            ],
            method=TOTAL_LINK_METHOD,
        )
        assert result.matched
        assert result.method == TOTAL_LINK_METHOD

    def test_the_partition_and_the_method_table_agree(self):
        assert DERIVED_LINK_METHODS[MARKET_TYPE_TOTAL] == TOTAL_LINK_METHOD

    def test_a_total_event_no_longer_reaches_the_two_team_bijection(self, conn):
        """Before this arm, a total event fell into the game partition and
        `link_event` refused it every pass with "expected 2 sides, got N" --
        a standing `unmatched_items` population describing a failure that was
        never a failure (the shape ADR 0070 removed for spreads). Mutation:
        take `MARKET_TYPE_TOTAL` out of `DERIVED_LINK_METHODS` and the
        refusal row comes back."""
        game = "KXMLBGAME-26AUG151310CWSDET"
        conn.execute(
            "INSERT INTO kalshi_events (event_ticker, first_seen_ms, "
            "last_seen_ms, commence_ms) VALUES (?, 0, 0, ?)",
            (game, NOW + 3_600_000),
        )
        conn.execute(
            "INSERT INTO event_links (kalshi_event_ticker, odds_event_id, "
            "league, method, commence_skew_ms, linked_ms) "
            "VALUES (?, 'game-9', 'baseball_mlb', ?, 0, 0)",
            (game, EXACT_ALIAS_PAIR),
        )
        total_ticker = "KXMLBTOTAL-26AUG151310CWSDET"
        conn.execute(
            "INSERT INTO kalshi_events (event_ticker, first_seen_ms, "
            "last_seen_ms, commence_ms) VALUES (?, 0, 0, ?)",
            (total_ticker, NOW + 3_600_000),
        )
        rungs = tuple(
            DiscoveredMarket(
                ticker=f"{total_ticker}-{n}",
                event_ticker=total_ticker,
                series_ticker="KXMLBTOTAL",
                market_type=MARKET_TYPE_TOTAL,
                title=f"Over {n}.5 runs scored?",
                yes_side=f"Over {n}.5 runs scored",
                strike=n + 0.5,
                close_ms=None,
                status="active",
                volume_24h=0.0,
                open_interest=0.0,
                price_structure="linear_cent",
            )
            for n in range(6, 12)
        )
        event = DiscoveredEvent(
            event_ticker=total_ticker,
            series_ticker="KXMLBTOTAL",
            league="MLB",
            sport_key="baseball_mlb",
            market_type=MARKET_TYPE_TOTAL,
            title="CWS vs DET total",
            commence_ms=NOW + 3_600_000,
            markets=rungs,
        )
        linked = link_discovered_events(conn, [event], now=NOW)
        assert total_ticker in linked
        method = conn.execute(
            "SELECT method FROM event_links WHERE kalshi_event_ticker = ?",
            (total_ticker,),
        ).fetchone()["method"]
        assert method == TOTAL_LINK_METHOD
        refused = conn.execute(
            "SELECT reason FROM unmatched_items WHERE identifier = ?",
            (total_ticker,),
        ).fetchall()
        assert refused == []


BY_SERIES = Path(__file__).parent / "fixtures" / "events_totals_by_series.json"

#: The leagues whose totals say `"Over N points"`, with no `scored` (#418).
POINTS_SERIES = {"KXNFLTOTAL", "KXNCAAFTOTAL", "KXNBATOTAL", "KXNCAAMBTOTAL"}


class TestYesIsTheOverOnEveryListedTotalsSeries:
    """#418. The runner binds a total's YES to the book's `Over`. That was
    measured on MLB and WNBA only. `events_totals_by_series.json` is one open
    event per series Kalshi listed on 2026-11-12 plus a count over all of them.

    Does not establish: anything about `KXMLBTOTAL` or `KXWNBATOTAL` beyond the
    older fixture (neither was listed in November), or that a Kalshi total and
    a sportsbook total settle on the same thing.
    """

    def _doc(self):
        return json.loads(BY_SERIES.read_text(encoding="utf-8"))

    def test_the_capture_holds_the_five_series_that_were_listed(self):
        doc = self._doc()
        kept = {e["series_ticker"] for e in doc["events"]}
        assert kept == POINTS_SERIES | {"KXNHLTOTAL"}
        # A series asked for and not listed is recorded as such, not skipped.
        assert doc["census"]["KXMLBTOTAL"]["open_events"] == 0
        assert doc["census"]["KXWNBATOTAL"]["open_events"] == 0

    def test_yes_is_the_over_on_every_market_of_every_kept_event(self):
        """An `"Under N"` YES anywhere would invert every wording downstream.
        Three wire facts say the same thing and all three are checked: the
        subtitle starts `Over`, `strike_type` is `greater`, and the rules text
        resolves Yes on more than (or over) the line."""
        markets = 0
        for event in self._doc()["events"]:
            for market in event["markets"]:
                markets += 1
                assert market["yes_sub_title"].startswith("Over "), market["ticker"]
                assert market["strike_type"] == "greater", market["ticker"]
                # "more than 23.5 points" or "over 192.5 total points": the
                # line itself must follow, so "overtime" cannot satisfy this.
                strike = re.escape(str(market["floor_strike"]))
                assert re.search(
                    rf"(more than|over) {strike} .*resolves to Yes",
                    market["rules_primary"],
                ), market["ticker"]
                assert market.get("cap_strike") is None, market["ticker"]
        assert markets > 80, f"only {markets} markets -- is the capture populated?"

    def test_the_count_over_every_open_market_agrees(self):
        for series, counts in self._doc()["census"].items():
            if not counts["open_events"]:
                continue
            assert counts["strike_type"] == {"greater": counts["markets"]}, series
            assert all(
                shape.startswith("Over N ") for shape in counts["yes_sub_title_shape"]
            ), series
            assert counts["floor_strike_equals_subtitle_number"] == counts["markets"]
            assert counts["whole_number_strikes"] == 0, series
            assert counts["cap_strike_present"] == 0, series

    def test_a_points_total_without_the_word_scored_parses_to_its_strike(self):
        """The defect #418 found: four leagues say `"Over 44.5 points"` and the
        grammar demanded `scored`, so every one of their totals was refused.

        Mutation observed red: put `scored` back as required in
        `_TOTAL_SUBTITLE`."""
        seen: set[str] = set()
        for event in self._doc()["events"]:
            if event["series_ticker"] not in POINTS_SERIES:
                continue
            for market in event["markets"]:
                line = parse_total_subtitle(market["yes_sub_title"])
                assert line is not None, market["yes_sub_title"]
                assert total_line_agrees(line, market["floor_strike"])
                seen.add(event["series_ticker"])
        assert seen == POINTS_SERIES

    def test_an_nhl_total_is_still_refused_and_named(self):
        """`goals` is not in the whitelist on purpose: whether a Kalshi NHL
        total and a book's settle alike is unanswered. Mutation observed red:
        add `goals?` to `_KNOWN_UNITS`."""
        nhl = [e for e in self._doc()["events"] if e["series_ticker"] == "KXNHLTOTAL"]
        assert nhl
        for market in nhl[0]["markets"]:
            assert parse_total_subtitle(market["yes_sub_title"]) is None
            assert unrecognised_total_unit(market["yes_sub_title"]) == "goals"

    def test_dropping_scored_did_not_loosen_anything_else(self):
        assert parse_total_subtitle("Over 44.5 points") == 44.5
        assert parse_total_subtitle("Under 44.5 points") is None
        assert parse_total_subtitle("Over 44.5") is None
        assert parse_total_subtitle("Over 44.5 points allowed") is None
        assert parse_total_subtitle("Dallas: Over 24.5 points") is None
        assert unrecognised_total_unit("Over 5.5 goals") == "goals"
        assert unrecognised_total_unit("Over 44.5 points") is None
        # A half's total is a different contract; `^Over` keeps it out even
        # though `KXNFL1HTOTAL` would be typed `total` by its series suffix.
        assert parse_total_subtitle("1st Half: Over 20.5 points") is None

    def test_a_whole_number_line_is_refused_by_every_reader(self):
        """A book pushes on the number and Kalshi settles it NO, so the two
        Unders are different bets. `total_line_agrees` is what the runner, the
        parlay reader and the alt-line check all call. Mutation observed red:
        drop the half-point clause from `total_line_agrees`."""
        assert total_line_is_half_point(44.5)
        assert not total_line_is_half_point(44.0)
        assert not total_line_is_half_point(44.25)
        assert total_line_agrees(44.5, 44.5)
        assert not total_line_agrees(44.0, 44.0)

    def test_a_whole_number_total_writes_no_fair_price(self, conn):
        _seed_total_rows(conn, rows=[
            ("Over", 44.0, 1.95, "pinnacle"),
            ("Under", 44.0, 1.95, "pinnacle"),
        ])
        counts = TestThePricingPath()._run(
            conn, _total_event(strike=44.0, subtitle="Over 44 points")
        )
        assert counts.fair_prices_written == 0
        assert counts.dropped_unresolved_outcome == 1
        assert counts.errors == []

    def test_a_points_total_reaches_a_fair_price(self, conn):
        """End to end through the runner: the wire's own phrasing writes both
        sides. Before #418 this wrote nothing and counted the market under
        the generic `dropped_unresolved_outcome`."""
        _seed_total_rows(conn, rows=[
            ("Over", 44.5, 1.95, "pinnacle"),
            ("Under", 44.5, 1.95, "pinnacle"),
        ])
        counts = TestThePricingPath()._run(
            conn, _total_event(strike=44.5, subtitle="Over 44.5 points")
        )
        assert counts.fair_prices_written == 2
        assert counts.dropped_unresolved_outcome == 0
        names = [
            r["outcome_name"] for r in conn.execute(
                "SELECT outcome_name FROM fair_prices WHERE market = ? "
                "ORDER BY outcome_name", (TOTALS_MARKET,),
            )
        ]
        assert names == ["Over", "Under"]
