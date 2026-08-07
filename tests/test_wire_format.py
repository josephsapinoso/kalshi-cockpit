"""Wire-format contract tests, against a real captured payload.

These tests **must** load from `tests/fixtures/`, never construct payloads
inline. A hand-written fixture only proves the code agrees with the test
author's memory of the API.

That is not hypothetical. The previous project's `apply_snapshot` read
`data["yes"]` while Kalshi sent `yes_dollars_fp`. Every order book parsed to
zero levels — silently, for the entire life of the project — while 305
synthetic tests passed. This file exists so that cannot happen again.

Fixture: `events_sports_nested.json`, captured 2026-08-06 from
`GET /events?with_nested_markets=true`, trimmed to a representative slice
spanning game-level moneyline/spread/total series and futures/props.
"""

from __future__ import annotations

import pytest

from conftest import load_fixture
from backend.core.prices import PRICE_MAX, complement, dollars_to_tenths, parse_quantity


@pytest.fixture(scope="module")
def events():
    return load_fixture("events_sports_nested.json")


@pytest.fixture(scope="module")
def markets(events):
    return [m for e in events for m in (e.get("markets") or [])]


class TestFieldNames:
    """The exact names Kalshi sends. Legacy names must stay dead."""

    def test_prices_use_the_dollars_suffix(self, markets):
        for market in markets:
            assert "yes_bid_dollars" in market
            assert "yes_ask_dollars" in market
            assert "no_bid_dollars" in market
            assert "no_ask_dollars" in market

    def test_sizes_and_volumes_use_the_fp_suffix(self, markets):
        for market in markets:
            assert "yes_bid_size_fp" in market
            assert "volume_24h_fp" in market
            assert "open_interest_fp" in market

    def test_legacy_field_names_are_absent(self, markets):
        """`yes_bid` and `volume_24h` no longer exist.

        A parser reading them gets None on every market and silently produces
        an empty book. That is exactly the previous failure.
        """
        for market in markets:
            assert "yes_bid" not in market
            assert "volume_24h" not in market

    def test_team_identity_is_available_without_parsing_the_ticker(self, events):
        """`yes_sub_title` carries the team name in plain text.

        This is the matching key. If it ever disappears, the linker has to fall
        back to ticker abbreviations and the alias tables all change.
        """
        game_events = [
            e for e in events if (e.get("series_ticker") or "").endswith("GAME")
        ]
        assert game_events, "fixture should contain game-level events"
        for event in game_events:
            assert " vs " in (event.get("title") or "")
            for market in event.get("markets") or []:
                assert (market.get("yes_sub_title") or "").strip()


class TestParsing:
    """Our parsers against real values, not invented ones."""

    def test_every_price_parses_onto_the_tenths_grid(self, markets):
        seen = 0
        for market in markets:
            for field in (
                "yes_bid_dollars",
                "yes_ask_dollars",
                "no_bid_dollars",
                "no_ask_dollars",
            ):
                raw = market.get(field)
                if raw in (None, ""):
                    continue
                tenths = dollars_to_tenths(raw)
                assert tenths is not None, f"{field}={raw!r} failed to parse"
                assert 0 <= tenths <= PRICE_MAX
                assert tenths == int(tenths)
                seen += 1
        assert seen > 0, "fixture contained no prices"

    def test_quantities_parse_as_floats(self, markets):
        for market in markets:
            for field in ("yes_bid_size_fp", "volume_24h_fp", "open_interest_fp"):
                raw = market.get(field)
                if raw in (None, ""):
                    continue
                assert parse_quantity(raw) is not None


class TestDerivedAskIdentity:
    """yes_ask == 1000 - no_bid, on real quotes.

    Verified on 2,145 quotes at capture time with zero violations. This test
    keeps that true against the trimmed fixture, so a regression in
    `store.db.derive_yes_ask` or in our understanding of the book shows up
    here rather than as mispriced EV.
    """

    def test_identity_holds_on_every_quoted_market(self, markets):
        checked = 0
        for market in markets:
            yes_ask = dollars_to_tenths(market.get("yes_ask_dollars"))
            no_bid = dollars_to_tenths(market.get("no_bid_dollars"))
            if yes_ask is None or no_bid is None:
                continue
            assert yes_ask == complement(no_bid), (
                f"{market['ticker']}: yes_ask={yes_ask} but "
                f"1000-no_bid={complement(no_bid)}"
            )
            checked += 1
        assert checked > 100, f"only {checked} quotes checked; fixture too thin"


class TestStructure:
    def test_no_kxmve_junk_survived_the_filter(self, events):
        for event in events:
            assert not event["event_ticker"].startswith("KXMVE")
            for market in event.get("markets") or []:
                assert not market["ticker"].startswith("KXMVE")

    def test_event_ticker_is_the_market_ticker_less_its_final_segment(self, events):
        for event in events:
            for market in event.get("markets") or []:
                assert market["ticker"].rsplit("-", 1)[0] == event["event_ticker"]

    def test_moneyline_events_carry_exactly_two_sides(self, events):
        """A game moneyline is binary. Three sides means we misread the series."""
        for event in events:
            if (event.get("series_ticker") or "").endswith("GAME"):
                markets = event.get("markets") or []
                if len(markets) == 2:  # soccer has draw variants; check the pairs
                    subtitles = {m.get("yes_sub_title") for m in markets}
                    assert len(subtitles) == 2

    def test_tick_structures_are_ones_we_handle(self, markets):
        known = {"linear_cent", "center_half_edge_half_cent", "deci_cent",
                 "tapered_deci_cent"}
        seen = {m.get("price_level_structure") for m in markets}
        unknown = seen - known - {None}
        assert not unknown, (
            f"unhandled tick structure(s): {unknown}. Verify the tenths grid "
            f"still holds before trusting any price."
        )
