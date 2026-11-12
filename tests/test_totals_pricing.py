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
    total_line_depends_on_overtime,
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
        assert unrecognised_total_unit("Over 9.5 corners scored") == "corners"
        assert unrecognised_total_unit("Over 5.5 goals scored") is None
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


def _total_event(
    *, strike=8.5, subtitle=None, ticker=f"{EVENT_TICKER}-8",
    strike_type="greater", cap_strike=None,
):
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
        strike_type=strike_type,
        cap_strike=cap_strike,
        cap_strike_present=cap_strike is not None,
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

    def test_an_unread_unit_is_counted_as_an_unknown_unit(self, conn):
        _seed_total_rows(conn, rows=[
            ("Over", 9.5, 1.95, "pinnacle"),
            ("Under", 9.5, 1.95, "pinnacle"),
        ])
        counts = self._run(
            conn, _total_event(strike=9.5, subtitle="Over 9.5 corners scored")
        )
        assert counts.fair_prices_written == 0
        assert counts.dropped_unknown_total_unit == 1
        assert counts.dropped_unresolved_outcome == 0

    def test_an_nhl_goals_total_writes_a_fair_price(self, conn):
        """#430: `goals` is read. Mutation observed red: drop `goals?` from
        `_KNOWN_UNITS`."""
        _seed_total_rows(conn, rows=[
            ("Over", 5.5, 1.95, "pinnacle"),
            ("Under", 5.5, 1.95, "pinnacle"),
        ])
        counts = self._run(
            conn, _total_event(strike=5.5, subtitle="Over 5.5 goals scored")
        )
        assert counts.fair_prices_written == 2
        assert counts.dropped_unknown_total_unit == 0

    def _seed_8_5(self, conn):
        _seed_total_rows(conn, rows=[
            ("Over", 8.5, 1.95, "pinnacle"),
            ("Under", 8.5, 1.95, "pinnacle"),
        ])

    @pytest.mark.parametrize("strike_type", ["less", "between", None])
    def test_a_total_that_is_not_strike_type_greater_is_refused(self, conn, strike_type):
        """#431: YES is the Over only when the venue says "greater"; an
        unreadable one is refused, not assumed. Mutation observed red: drop
        the `strike_type` clause in `_price_totals_event`."""
        self._seed_8_5(conn)
        counts = self._run(conn, _total_event(strike_type=strike_type))
        assert counts.fair_prices_written == 0
        assert counts.dropped_total_not_above_line == 1

    def test_a_total_with_a_cap_strike_is_refused(self, conn):
        """A `cap_strike` makes it a band, not "above the line". Mutation
        observed red: drop the `cap_strike` clause."""
        self._seed_8_5(conn)
        counts = self._run(conn, _total_event(cap_strike=10.5))
        assert counts.fair_prices_written == 0
        assert counts.dropped_total_not_above_line == 1

    def test_the_greater_uncapped_total_still_prices(self, conn):
        self._seed_8_5(conn)
        counts = self._run(conn)
        assert counts.fair_prices_written == 2
        assert counts.dropped_total_not_above_line == 0

    def test_an_overtime_dependent_nhl_line_is_counted_by_name(self, conn):
        _seed_total_rows(conn, rows=[
            ("Over", 6.5, 1.95, "pinnacle"),
            ("Under", 6.5, 1.95, "pinnacle"),
        ])
        counts = self._run(
            conn, _total_event(strike=6.5, subtitle="Over 6.5 goals scored")
        )
        assert counts.fair_prices_written == 0
        assert counts.dropped_overtime_dependent_total == 1
        assert counts.dropped_unknown_total_unit == 0
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
                strike_type="greater",
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

    def test_an_nhl_total_parses_to_its_strike(self):
        """#430: Kalshi's NHL rules and DraftKings' filed house rule both count
        overtime and score a shootout as one goal to the winner, so `goals` is
        read. The rule this rests on is quoted in the captured market itself.
        Mutation observed red: drop `goals?` from `_KNOWN_UNITS`."""
        nhl = [e for e in self._doc()["events"] if e["series_ticker"] == "KXNHLTOTAL"]
        assert nhl
        priced = refused = 0
        for market in nhl[0]["markets"]:
            subtitle = market["yes_sub_title"]
            assert unrecognised_total_unit(subtitle) is None
            assert "shootout result will be recorded as one goal" in market[
                "rules_secondary"
            ], market["ticker"]
            line = parse_total_subtitle(subtitle)
            if int(market["floor_strike"]) % 2 == 0:
                # 4.5, 6.5, 8.5: overtime can decide these (see below).
                assert line is None, subtitle
                assert total_line_depends_on_overtime(subtitle)
                refused += 1
            else:
                assert line is not None, subtitle
                assert total_line_agrees(line, market["floor_strike"])
                assert not total_line_depends_on_overtime(subtitle)
                priced += 1
        assert priced and refused

    def test_only_the_lines_overtime_cannot_decide_are_priced(self):
        """A tied regulation score is an even total and overtime adds one
        goal, so only an even-floor line (4.5 from 2-2, 6.5 from 3-3) can be
        decided by it. The sharp books' overtime rule is unread, so those are
        refused (#430, kalshi-platform's review). Mutation observed red:
        make `total_line_depends_on_overtime` return False."""
        for line, depends in [(1.5, False), (2.5, True), (3.5, False),
                              (4.5, True), (5.5, False), (6.5, True),
                              (7.5, False), (8.5, True)]:
            subtitle = f"Over {line} goals scored"
            assert total_line_depends_on_overtime(subtitle) is depends, line
            assert (parse_total_subtitle(subtitle) is None) is depends, line
        # Runs and points are not in question.
        assert not total_line_depends_on_overtime("Over 6.5 runs scored")
        assert parse_total_subtitle("Over 44.5 points") == 44.5

    def test_dropping_scored_did_not_loosen_anything_else(self):
        assert parse_total_subtitle("Over 44.5 points") == 44.5
        assert parse_total_subtitle("Under 44.5 points") is None
        assert parse_total_subtitle("Over 44.5") is None
        assert parse_total_subtitle("Over 44.5 points allowed") is None
        assert parse_total_subtitle("Dallas: Over 24.5 points") is None
        assert parse_total_subtitle("Over 5.5 goals") == 5.5
        assert unrecognised_total_unit("Over 9.5 corners") == "corners"
        assert unrecognised_total_unit("Over 44.5 points") is None
        # A half's or a period's total is a different contract, and its
        # subtitle uses the SAME grammar ("Over 3.5 points", "Over 1.5
        # goals"), so the parser cannot keep it out. Discovery's scope check
        # does: `TestPeriodTotalsAreKeptOutByScope`.

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


PERIOD_TOTALS = Path(__file__).parent / "fixtures" / "events_period_totals.json"


class TestPeriodTotalsAreKeptOutByScope:
    """kalshi-platform, #430 review: `KXNHL1PTOTAL` says "Over 1.5 goals" and
    `KXNFL1HTOTAL` "Over 3.5 points" -- the full-game grammar. Joined to a
    full-game book line at the same number they would be priced as the wrong
    contract. Only discovery's `competition_scope` check keeps them out, and
    this pins it on captured payloads."""

    def _events(self):
        return json.loads(PERIOD_TOTALS.read_text(encoding="utf-8"))["events"]

    def test_their_subtitles_parse_so_the_parser_is_not_the_guard(self):
        for event in self._events():
            assert any(
                parse_total_subtitle(m["yes_sub_title"]) is not None
                for m in event["markets"]
            ), event["series_ticker"]

    def test_discovery_classifies_none_of_them_as_game_level(self):
        from backend.kalshi.discovery import classify_series

        seen = set()
        for event in self._events():
            assert classify_series(event).is_game_level is False, event["series_ticker"]
            seen.add(event["series_ticker"])
        assert seen == {"KXNHL1PTOTAL", "KXNFL1HTOTAL", "KXNBA1HTOTAL"}

    def test_the_full_game_nhl_total_is_game_level(self):
        from backend.kalshi.discovery import classify_series

        doc = json.loads(BY_SERIES.read_text(encoding="utf-8"))
        nhl = next(e for e in doc["events"] if e["series_ticker"] == "KXNHLTOTAL")
        assert classify_series(nhl).is_game_level is True


class TestDiscoveryCarriesTheStrikeShape:
    def test_build_market_reads_strike_type_and_cap_strike_off_the_wire(self):
        """#431, on the captured payload: every totals market reads
        `"greater"` and no cap, through the one parser."""
        from backend.kalshi.discovery import build_market

        doc = json.loads(BY_SERIES.read_text(encoding="utf-8"))
        seen = 0
        for event in doc["events"]:
            for raw in event["markets"]:
                m = build_market(raw, market_type=MARKET_TYPE_TOTAL)
                assert m.strike_type == "greater", m.ticker
                assert m.cap_strike is None, m.ticker
                seen += 1
        assert seen > 80

    def test_a_cap_strike_on_the_wire_is_carried(self):
        from backend.kalshi.discovery import build_market

        doc = json.loads(BY_SERIES.read_text(encoding="utf-8"))
        raw = dict(doc["events"][0]["markets"][0], cap_strike=10.5, strike_type="between")
        m = build_market(raw, market_type=MARKET_TYPE_TOTAL)
        assert (m.strike_type, m.cap_strike) == ("between", 10.5)

    def test_a_garbled_cap_strike_neither_raises_nor_slips_through(self):
        """kalshi-platform, #431: `build_market` serves the quote refresh on
        every market type, so an unreadable `cap_strike` must not raise; it
        must still mark the market capped so the totals arm refuses it."""
        from backend.kalshi.discovery import build_market

        doc = json.loads(BY_SERIES.read_text(encoding="utf-8"))
        for garbage in ("", "n/a", {"x": 1}, [1]):
            raw = dict(doc["events"][0]["markets"][0], cap_strike=garbage)
            m = build_market(raw, market_type=MARKET_TYPE_TOTAL)
            assert m.cap_strike is None, garbage
            assert m.cap_strike_present is True, garbage
