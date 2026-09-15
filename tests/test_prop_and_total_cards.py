"""The prop card and the totals card: registered, their own set, floored.

WHY THIS EXISTS
---------------
Joe asked on 2026-09-14 for over/unders and player props to be bettable "as a
whole other set of parlays". The prop card had been staged since 2026-09-10
(`STAGED_PROP_CARD`, unregistered because the feed bought no prop rows); the
feed now buys NFL props on tap (`tests/test_prop_keys_are_sport_aware.py`)
and totals on every sweep (`tests/test_totals_pricing.py`), so both cards are
registered here as `PROP_CARD` and `TOTALS_CARD`.

What these establish: both cards are in `CARD_SHAPES`; neither is pushed to
the phone; each draws only from its own market class and no existing card
draws from either (the per-card gate ADR 0139 describes); each builds
likeliest-first, one leg per fixture, with a probability floor; and the
market names spelled in the pure core agree with the feed client's and with
what the candidate scan admits.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Nothing about whether a prop or total card is a good bet.** It builds.
  The hunt is closed (ADR 0038); a leg with a consensus beside it is not a
  leg with an edge.
- **Nothing about coverage.** Synthetic legs have a consensus AND a Kalshi
  rung by construction; how often a live rung has both is unmeasured for NFL
  and was 48 of 263 for MLB props (ADR 0079).
- **Nothing about Kalshi combining a prop or total leg.** The fixtures show
  the venue's collections carry them; whether a given card prices is one
  live lookup, and a lookup mints.
- **Which side a card leans.** Both sides reach the pool (the Under is a NO
  leg, `tests/test_under_legs.py`); a card picks whichever is likelier per
  game, and nothing here measures how often that is the over.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from backend.core.ladder import (
    CARD_SHAPES,
    MLB_PROP_MARKETS,
    NFL_PROP_MARKETS,
    PROP_AND_TOTAL_FLOOR,
    PROP_CARD,
    PROP_MARKETS_ALL,
    TEAM_MARKETS_ONLY,
    TOTALS_CARD,
    TOTALS_ONLY,
    _best_per_game,
    _pool_for,
    joint_for,
)
from tests.test_ladder import leg  # the module's own CandidateLeg factory

NOW = 1_789_000_000_000


def prop_leg(*, game: str, player: str, market: str, p: float, point: float = 0.5):
    """A prop leg on its own fixture unless `game` repeats."""
    return replace(
        leg(game=game, p=p, market=market, point=point),
        player=player,
        team=None,
    )


def total_leg(*, game: str, line: float, p: float):
    return replace(
        leg(game=game, p=p, market="totals", point=line,
            ticker=f"KXMLBTOTAL-{game}-{line}"),
        label=f"Over {line} runs scored",
        team=None,
    )


class TestTheyAreRegistered:
    def test_both_cards_are_in_the_shapes(self):
        keys = [r.key for r in CARD_SHAPES]
        assert PROP_CARD in CARD_SHAPES and TOTALS_CARD in CARD_SHAPES
        assert keys[-2:] == ["props", "totals"]

    def test_neither_is_pushed_to_the_phone(self):
        """ADR 0139 SS6's rule for a new card: reachable from `/parlays`,
        never an interruption on the phone."""
        from backend.notify.alerts import PUSHED_CARD_KEYS

        assert "props" not in PUSHED_CARD_KEYS
        assert "totals" not in PUSHED_CARD_KEYS

    def test_both_floors_are_set_and_equal(self):
        """`min_leg_probability`'s own comment calls it required on any card
        whose fair side has no other bound."""
        for recipe in (PROP_CARD, TOTALS_CARD):
            assert recipe.min_leg_probability == PROP_AND_TOTAL_FLOOR
            assert recipe.min_leg_probability > 0

    def test_the_copy_says_both_sides(self):
        """Both sides reach the card (the Under is a NO leg), so the copy
        must not read as an overs-only pick -- and must not claim a lean it
        does not have."""
        for recipe in (PROP_CARD, TOTALS_CARD):
            assert "over or under" in recipe.what_it_is
            assert "only" not in recipe.what_it_is


class TestEachCardIsItsOwnSet:
    def test_every_existing_card_still_declines_props_and_totals(self):
        """Mutation: set any team card's `markets=None` and it starts serving
        prop legs the moment a tap buys one."""
        for recipe in CARD_SHAPES:
            if recipe.key in ("props", "totals"):
                continue
            assert recipe.markets is not None, recipe.key
            assert not (recipe.markets & PROP_MARKETS_ALL), recipe.key
            assert not (recipe.markets & TOTALS_ONLY), recipe.key

    def test_the_team_market_set_is_untouched(self):
        assert TEAM_MARKETS_ONLY == frozenset({"h2h", "spreads"})

    def test_the_prop_card_admits_no_team_or_total_leg(self):
        pool = [
            prop_leg(game="g1", player="Ohtani", market="batter_hits", p=0.81),
            leg(game="t1", p=0.95),
            total_leg(game="g2", line=8.5, p=0.90),
        ]
        kept = _pool_for(PROP_CARD, pool, now_ms=NOW)
        assert [k.market for k in kept] == ["batter_hits"]

    def test_the_totals_card_admits_no_team_or_prop_leg(self):
        pool = [
            total_leg(game="g1", line=8.5, p=0.61),
            leg(game="t1", p=0.95),
            prop_leg(game="g2", player="Ohtani", market="batter_hits", p=0.90),
        ]
        kept = _pool_for(TOTALS_CARD, pool, now_ms=NOW)
        assert [k.market for k in kept] == ["totals"]


class TestTheMarketNamesMatchTheFeedClient:
    """Spelled in `core/ladder.py` to keep the pure core free of `backend.*`
    imports; pinned here so the copies cannot drift."""

    def test_the_mlb_set_equals_the_clients(self):
        from backend.odds.client import MLB_PROP_BASE_MARKETS

        assert MLB_PROP_MARKETS == frozenset(MLB_PROP_BASE_MARKETS)

    def test_the_nfl_set_equals_the_clients(self):
        from backend.odds.client import NFL_PROP_BASE_MARKETS

        assert NFL_PROP_MARKETS == frozenset(NFL_PROP_BASE_MARKETS)

    def test_the_union_is_every_prop_key_the_feed_buys(self):
        from backend.odds.client import PROP_BASE_MARKETS

        assert PROP_MARKETS_ALL == frozenset(PROP_BASE_MARKETS)

    def test_the_totals_key_equals_the_kalshi_modules(self):
        from backend.kalshi.totals import TOTALS_MARKET

        assert TOTALS_ONLY == frozenset({TOTALS_MARKET})

    def test_they_are_what_the_candidate_scan_admits(self):
        """If the scan stopped admitting one, that card would silently narrow."""
        from backend.parlays import POOL_MARKETS

        for market in PROP_MARKETS_ALL | TOTALS_ONLY:
            assert market in POOL_MARKETS, market


class TestThePropCardBuilds:
    def _pool(self):
        return [
            prop_leg(game="g1", player="Ohtani", market="batter_hits", p=0.81),
            prop_leg(game="g2", player="Skenes", market="pitcher_strikeouts", p=0.74),
            prop_leg(game="g3", player="Henry", market="player_rush_yds", p=0.69, point=74.5),
            prop_leg(game="g4", player="Soto", market="batter_rbis", p=0.55),
        ]

    def test_it_selects_the_likeliest_three_across_sports(self):
        pool = _pool_for(PROP_CARD, self._pool(), now_ms=NOW)
        assert len(pool) == 4
        selected = pool[: PROP_CARD.max_legs]
        assert [round(l.p_conservative, 2) for l in selected] == [0.81, 0.74, 0.69]
        assert "player_rush_yds" in {l.market for l in selected}

    def test_it_takes_one_leg_per_fixture(self):
        pool = self._pool() + [
            prop_leg(game="g1", player="Betts", market="batter_rbis", p=0.79)
        ]
        kept = _best_per_game(pool, prefer_spreads=False)
        games = [l.kalshi_event_ticker for l in kept]
        assert len(games) == len(set(games)), "two legs from one fixture were kept"

    def test_the_floor_refuses_a_lottery_leg(self):
        pool = self._pool() + [
            prop_leg(game="g9", player="Nobody", market="batter_home_runs", p=0.02)
        ]
        kept = _pool_for(PROP_CARD, pool, now_ms=NOW)
        assert all(l.p_conservative >= PROP_AND_TOTAL_FLOOR for l in kept)
        assert not any((l.player or "") == "Nobody" for l in kept)

    def test_the_worst_case_payout_stays_in_the_same_order_as_longshot(self):
        """CLAUDE.md rule 1 applied to the payout column: a big number is a bug
        until shown otherwise. At the floor, three legs is about 125x."""
        floor = PROP_CARD.min_leg_probability
        worst = tuple(
            prop_leg(game=f"w{i}", player=f"P{i}", market="batter_hits", p=floor)
            for i in range(PROP_CARD.max_legs)
        )
        joint = joint_for(worst)
        assert joint.conservative > 0
        assert joint.fair_decimal < 400, (
            f"worst-case payout is {joint.fair_decimal:.0f}x, which is a "
            "lottery rather than a card"
        )


class TestTheTotalsCardBuilds:
    def _pool(self):
        return [
            total_leg(game="g1", line=8.5, p=0.58),
            total_leg(game="g2", line=47.5, p=0.54),
            total_leg(game="g3", line=9.0, p=0.51),
            total_leg(game="g4", line=180.5, p=0.49),
        ]

    def test_it_selects_the_likeliest_three(self):
        pool = _pool_for(TOTALS_CARD, self._pool(), now_ms=NOW)
        assert len(pool) == 4
        selected = pool[: TOTALS_CARD.max_legs]
        assert [round(l.p_conservative, 2) for l in selected] == [0.58, 0.54, 0.51]

    def test_it_takes_one_leg_per_fixture(self):
        """Two rungs of one game's ladder are the same event twice."""
        pool = self._pool() + [total_leg(game="g1", line=9.5, p=0.57)]
        kept = _pool_for(TOTALS_CARD, pool, now_ms=NOW)
        games = [l.kalshi_event_ticker for l in kept]
        assert len(games) == len(set(games))

    def test_the_floor_refuses_a_lottery_rung(self):
        pool = self._pool() + [total_leg(game="g9", line=20.5, p=0.02)]
        kept = _pool_for(TOTALS_CARD, pool, now_ms=NOW)
        assert all(l.p_conservative >= PROP_AND_TOTAL_FLOOR for l in kept)
        assert not any(l.point == 20.5 for l in kept)

    def test_a_total_leg_carries_no_team(self):
        for l in self._pool():
            assert l.team is None
            assert l.player is None


@pytest.mark.parametrize("market", sorted(PROP_MARKETS_ALL))
def test_each_prop_market_can_carry_a_leg(market: str):
    """No market in the set is spelled in a way the pool filter drops."""
    pool = _pool_for(
        PROP_CARD,
        [
            prop_leg(game="a", player="A", market=market, p=0.7),
            prop_leg(game="b", player="B", market=market, p=0.6),
        ],
        now_ms=NOW,
    )
    assert len(pool) == 2
