"""The prop feed is bought per sport, and the two halves of a prop sport agree.

ADR 0140 SS4.2 named the failure this file guards: `prop_market_keys()` was a
flat, sport-unaware list whose length was the price of every prop event, so
adding NFL keys to it would have bought them on every MLB event too, and
merging `NFL_PROP_SERIES` into `PROP_SERIES` alone would have admitted ~2,000
NFL prop markets a slate that nothing priced. Both halves landed in one change
on 2026-09-14, and these tests pin that they stay one.

What this establishes: each sport buys exactly its own keys; the feed-side
keys of a sport are exactly the book markets its Kalshi ladders map to; a
sport outside the map is refused before any provider call; the planner's one
reservation figure is never smaller than what any sport actually spends; and
the tap route quotes the per-sport price, not the union.

What it does not establish: that an NFL prop event returns two-sided quotes
(no NFL prop odds payload is in any fixture -- the pricing path is exercised
by the MLB capture, which runs the same code); whether the `_alternate` NFL
feeds are needed (ADR 0079's MLB finding is not assumed to carry, and nothing
buys them); or that any prop leg is a good bet (the hunt is closed, ADR 0038).
"""

from __future__ import annotations

import pytest

from backend.kalshi.props import MLB_PROP_SERIES, NFL_PROP_SERIES, PROP_SERIES
from backend.odds.budget import sweep_cost
from backend.odds.client import (
    MLB_PROP_BASE_MARKETS,
    NFL_PROP_BASE_MARKETS,
    PROP_BASE_MARKETS,
    PROP_MARKET_KEYS_BY_SPORT,
    PROP_MARKET_SPORTS,
    PROP_MARKETS,
    max_prop_cost_per_event,
    prop_market_keys,
    sport_has_prop_markets,
)


class TestEachSportBuysExactlyItsOwnKeys:
    def test_an_mlb_event_still_buys_exactly_five_keys(self):
        assert prop_market_keys("baseball_mlb") == list(MLB_PROP_BASE_MARKETS)
        assert len(prop_market_keys("baseball_mlb")) == 5

    def test_an_nfl_event_buys_exactly_the_three_yardage_keys(self):
        """Mutation: `prop_market_keys` returning `PROP_BASE_MARKETS` (the
        union) makes an NFL event eight keys and this fails."""
        assert prop_market_keys("americanfootball_nfl") == list(NFL_PROP_BASE_MARKETS)
        assert len(prop_market_keys("americanfootball_nfl")) == 3
        assert not any(k.startswith(("batter_", "pitcher_")) for k in prop_market_keys("americanfootball_nfl"))

    def test_no_sport_buys_an_alternate_key(self):
        for sport, keys in PROP_MARKET_KEYS_BY_SPORT.items():
            assert not [k for k in keys if k.endswith("_alternate")], sport

    def test_the_union_is_the_parser_set_and_carries_the_alternates_for_reading(self):
        assert set(PROP_BASE_MARKETS) == set(MLB_PROP_BASE_MARKETS) | set(NFL_PROP_BASE_MARKETS)
        for key in PROP_BASE_MARKETS:
            assert key in PROP_MARKETS
            assert f"{key}_alternate" in PROP_MARKETS


class TestTheTwoHalvesOfAPropSportAgree:
    """ADR 0140 SS4.2's guarantee: what discovery admits and what the feed
    buys are the same markets, per sport."""

    def test_the_nfl_keys_are_the_values_of_nfl_prop_series(self):
        assert set(prop_market_keys("americanfootball_nfl")) == set(NFL_PROP_SERIES.values())

    def test_the_mlb_keys_are_the_values_of_mlb_prop_series(self):
        assert set(prop_market_keys("baseball_mlb")) == set(MLB_PROP_SERIES.values())

    def test_the_live_allowlist_is_exactly_the_sports_the_feed_can_buy(self):
        """Every series `PROP_SERIES` admits maps to a key some sport buys,
        and every key some sport buys is the value of an admitted series.
        Mutation: revert `PROP_SERIES` to MLB-only and the NFL keys have no
        ladder behind them."""
        assert set(PROP_SERIES.values()) == set(PROP_BASE_MARKETS)


class TestASportWithoutKeysIsRefusedBeforeAnyCall:
    def test_the_predicate_is_the_key_map(self):
        assert PROP_MARKET_SPORTS == frozenset(PROP_MARKET_KEYS_BY_SPORT)
        assert sport_has_prop_markets("baseball_mlb")
        assert sport_has_prop_markets("americanfootball_nfl")
        for sport in ("basketball_wnba", "basketball_nba", "americanfootball_ncaaf", "icehockey_nhl"):
            assert not sport_has_prop_markets(sport), sport
            assert prop_market_keys(sport) == [], sport

    def test_a_call_without_a_sport_does_not_compile(self):
        """The sport-free spelling was the #37 shape. It must not exist."""
        with pytest.raises(TypeError):
            prop_market_keys()  # type: ignore[call-arg]


class TestThePlannerNeverReservesLessThanAnySportSpends:
    def test_the_reserve_is_the_dearest_sport(self):
        regions = ["us", "eu"]
        reserve = max_prop_cost_per_event(regions)
        for sport in PROP_MARKET_SPORTS:
            assert reserve >= sweep_cost(prop_market_keys(sport), regions), sport
        assert reserve == 10  # MLB's five keys x two regions

    def test_the_reserve_follows_the_named_books_too(self):
        """ADR 0155: ten named books are one region-equivalent, so the reserve
        halves with the bill.

        Passing `regions` alone here would reserve 10 against a true cost of
        5 — over-reserving, which is the SAFE direction and therefore silent,
        and which wastes exactly the headroom the named-book cut buys.
        """
        regions = ["us", "eu"]
        books = [f"book{i}" for i in range(10)]
        reserve = max_prop_cost_per_event(regions, books)
        for sport in PROP_MARKET_SPORTS:
            assert reserve >= sweep_cost(
                prop_market_keys(sport), regions, books
            ), sport
        assert reserve == 5  # MLB's five keys x one region-equivalent

    def test_the_runner_hands_the_planner_that_figure(self):
        """Source check: the planner's argument comes from the one helper,
        not from a sport-specific list that would under-reserve the other.

        Whitespace is normalised before matching so the claim survives a line
        wrap — it broke once on exactly that, when ADR 0155 added a second
        argument and pushed the call onto three lines.
        """
        import inspect
        import re

        from backend import runner

        src = re.sub(r"\s+", "", inspect.getsource(runner.fetch_and_store_odds))
        assert "prop_cost_per_event=max_prop_cost_per_event(config.regions" in src
        # And the books travel with it: billing the reserve on regions while
        # the call itself is billed on books is the silent over-reserve above.
        assert "max_prop_cost_per_event(config.regions,config.bookmakers)" in src
