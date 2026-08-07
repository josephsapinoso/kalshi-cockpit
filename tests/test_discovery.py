"""Discovery tests, against the real captured payload.

The classifier decides which leagues are priceable at all, so a bug here does
not surface as an error — it surfaces as a league quietly missing from the
Board. These tests run against `events_sports_nested.json` rather than
invented events, so a Kalshi metadata change breaks them instead of silently
emptying the universe.
"""

from __future__ import annotations

import pytest

from conftest import load_fixture
from backend.kalshi.discovery import (
    FIXTURE_SCOPES,
    IN_SCOPE_LEAGUES,
    NON_FIXTURE_SCOPES,
    classify_series,
    coverage_by_league,
    discover_from_events,
    event_commence_ms,
    parse_ms,
)


@pytest.fixture(scope="module")
def events():
    return load_fixture("events_sports_nested.json")


@pytest.fixture(scope="module")
def discovered(events):
    return discover_from_events(events)


class TestSeriesClassification:
    def test_game_series_are_recognised_as_game_level(self, events):
        for event in events:
            if (event.get("series_ticker") or "") == "KXMLBGAME":
                assert classify_series(event).is_game_level
                return
        pytest.fail("fixture has no KXMLBGAME event")

    def test_futures_series_are_not_game_level(self, events):
        """`KXNBA` is the championship winner -- one market, whole season."""
        for event in events:
            if (event.get("series_ticker") or "") == "KXNBA":
                assert not classify_series(event).is_game_level
                return
        pytest.fail("fixture has no KXNBA futures event")

    @pytest.mark.parametrize(
        "series,expected_type",
        [
            ("KXMLBGAME", "moneyline"),
            ("KXMLBSPREAD", "spread"),
            ("KXMLBTOTAL", "total"),
            ("KXWNBAGAME", "moneyline"),
        ],
    )
    def test_market_type_comes_from_the_series_suffix(
        self, events, series, expected_type
    ):
        for event in events:
            if (event.get("series_ticker") or "") == series:
                assert classify_series(event).market_type == expected_type
                return
        pytest.skip(f"fixture has no {series} event")

    def test_scope_is_read_from_metadata_not_inferred(self):
        """`competition_scope` is authoritative; the suffix is only a fallback."""
        event = {
            "series_ticker": "KXMLBGAME",
            "product_metadata": {
                "competition": "Pro Baseball",
                "competition_scope": "Season",
            },
        }
        assert not classify_series(event).is_game_level

    def test_an_unknown_league_is_out_of_scope_not_an_error(self):
        """No consensus to devig against means not priceable, not broken."""
        info = classify_series(
            {
                "series_ticker": "KXLOLGAME",
                "product_metadata": {
                    "competition": "League of Legends",
                    "competition_scope": "Game",
                },
            }
        )
        assert info.is_game_level
        assert info.sport_key is None
        assert not info.in_scope


class TestMetadataDrift:
    """Fail loudly when Kalshi uses a label we do not classify.

    This class exists because of a real bug. The first version of the
    classifier tested `scope == "game"` and spelled the leagues by guesswork
    ("Womens Pro Basketball", "College Football"). Kalshi actually emits
    `Spread`, `Point Total`, `Pro Basketball (W)`, `NCAA Football`. The effect
    was that **every spread and total, plus WNBA and NCAAF entirely, silently
    vanished from the universe** -- and the rest of this file passed anyway,
    because it only asserted that the things which *did* survive looked right.

    An exclusion must be a decision, never an accident.
    """

    def test_every_scope_in_the_fixture_is_explicitly_classified(self, events):
        scopes = {
            ((e.get("product_metadata") or {}).get("competition_scope") or "").lower()
            for e in events
        }
        known = FIXTURE_SCOPES | NON_FIXTURE_SCOPES | {""}
        unknown = scopes - known
        assert not unknown, (
            f"unclassified competition_scope value(s): {sorted(unknown)}. "
            f"Add each to FIXTURE_SCOPES (per-fixture, priceable) or "
            f"NON_FIXTURE_SCOPES (futures/awards). Leaving one unclassified "
            f"silently drops those markets."
        )

    def test_spread_and_total_scopes_count_as_per_fixture(self):
        """The exact bug: spreads and totals resolve on one fixture."""
        assert "spread" in FIXTURE_SCOPES
        assert "point total" in FIXTURE_SCOPES

    def test_in_scope_league_names_match_what_kalshi_actually_sends(self, events):
        """Guards against tidying a league string into one Kalshi never emits.

        Any league we claim to support must appear verbatim in real data, or
        the mapping is aspirational and the league is silently absent.
        """
        seen = {
            (e.get("product_metadata") or {}).get("competition")
            for e in events
        }
        seen.discard(None)
        supported_and_present = seen & set(IN_SCOPE_LEAGUES)
        assert supported_and_present, (
            f"none of the configured leagues {sorted(IN_SCOPE_LEAGUES)} appear "
            f"in the captured data, which contains {sorted(seen)}. The mapping "
            f"keys must be Kalshi's exact spelling."
        )

    def test_wnba_and_ncaaf_are_reachable(self, events):
        """Both were dropped by a misspelled mapping key."""
        seen = {
            (e.get("product_metadata") or {}).get("competition") for e in events
        }
        for league in ("Pro Basketball (W)", "NCAA Football"):
            if league in seen:
                assert league in IN_SCOPE_LEAGUES, f"{league} present but unmapped"


class TestCommenceTime:
    """The join key against the sportsbook feed."""

    def test_commence_comes_from_occurrence_datetime_not_close_time(self, events):
        """`close_time` can be days after the game -- Kalshi allows for
        postponements. Matching on it would mis-join every fixture."""
        event = next(e for e in events if e.get("series_ticker") == "KXMLBGAME")
        commence = event_commence_ms(event)
        close = parse_ms(event["markets"][0]["close_time"])
        assert commence is not None
        assert commence < close, "commence should precede close"
        assert close - commence > 24 * 3600 * 1000, (
            "expected close_time to be well after the game, proving they differ"
        )

    def test_missing_occurrence_time_returns_none_not_a_default(self):
        """A wrong start time silently joins the wrong fixture."""
        assert event_commence_ms({"markets": [{"close_time": "2026-08-13T00:20:00Z"}]}) is None

    def test_unparseable_timestamps_return_none(self):
        for bad in (None, "", "not-a-date", "2026-13-45"):
            assert parse_ms(bad) is None


class TestDiscovery:
    def test_finds_priceable_events(self, discovered):
        assert discovered, "no priceable events found in the fixture"

    def test_every_discovered_event_has_what_matching_needs(self, discovered):
        for event in discovered:
            assert event.commence_ms > 0
            assert event.sport_key in IN_SCOPE_LEAGUES.values()
            assert event.markets
            assert event.title

    def test_moneyline_events_name_exactly_two_sides(self, discovered):
        """Built from `yes_sub_title`, because `no_sub_title` repeats the YES
        side rather than naming the opponent."""
        moneylines = [e for e in discovered if e.market_type == "moneyline"]
        assert moneylines
        for event in moneylines:
            assert len(event.teams) == 2, f"{event.event_ticker}: {event.teams}"

    def test_out_of_scope_leagues_are_excluded(self, discovered):
        """Soccer and esports have game markets but no configured sport key."""
        assert all(e.sport_key for e in discovered)
        assert not any(e.series_ticker == "KXMLSGAME" for e in discovered)

    def test_futures_are_excluded(self, discovered):
        assert not any(e.series_ticker in {"KXNBA", "KXNFLMVP"} for e in discovered)

    def test_spread_and_total_markets_carry_their_line(self, discovered):
        priced = [e for e in discovered if e.market_type in ("spread", "total")]
        if not priced:
            pytest.skip("fixture has no spread/total events in scope")
        for event in priced:
            assert all(m.strike is not None for m in event.markets), (
                "a spread or total without a line cannot be matched to a book"
            )


class TestCoverage:
    def test_reports_per_league_totals(self, discovered):
        coverage = coverage_by_league(discovered)
        assert coverage
        for league, entry in coverage.items():
            assert entry["events"] > 0
            assert entry["markets"] >= entry["events"]
            assert entry["sport_key"]

    def test_mlb_is_present_with_moneyline_coverage(self, discovered):
        coverage = coverage_by_league(discovered)
        assert "Pro Baseball" in coverage
        assert "moneyline" in coverage["Pro Baseball"]["market_types"]
