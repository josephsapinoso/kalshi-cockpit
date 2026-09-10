"""A prop-bearing card is built, tested, and deliberately not on the desk.

WHY THIS EXISTS
---------------
Joe asked for props as parlay legs on 2026-09-10 and chose the free test.
The free test could not run, and the reason is worth pinning so nobody spends
a session rediscovering it:

    ODDS_MARKETS on live                     'h2h,spreads'
    newest MLB prop row in `fair_prices`     600 hours old
    prop rows in the last 7 days             0

`CANDIDATE_SQL` admits the five prop markets, and `ladder_candidates`' prop arm
resolves them to legs with a real Kalshi rung — so the *code* path is open, end
to end. What is missing is rows. "The query admits this market" and "the desk
holds this market" are different claims, and the first was mistaken for the
second (see `tasks/lessons.md`).

So `STAGED_PROP_CARD` exists complete and is reachable by nothing, the way
`NFL_PROP_SERIES` was staged in `8d5dd1c`. These tests are what make enabling
it one edit: they prove it builds, one leg per fixture, with a floor, from a
pool that has prop legs in it.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Nothing about whether a prop card is a good bet.** It builds; that is all.
  Whether the consensus behind a prop leg is worth anything is ADR 0079's
  coverage question and is unmeasured for a card.
- **Nothing about coverage.** ADR 0079 put primary-only coverage at 48 of 263
  MLB prop markets. A leg needs a devigged consensus AND a Kalshi rung, and
  this uses synthetic legs that have both by construction.
- **Nothing about Kalshi combining prop legs.** No combination collection was
  read for a prop card; `kalshi_will_not_combine` is a separate refusal that
  only a live lookup answers, and a lookup mints.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from backend.core.ladder import (
    CARD_SHAPES,
    MLB_PROP_MARKETS,
    STAGED_PROP_CARD,
    TEAM_MARKETS_ONLY,
    _best_per_game,
    _pool_for,
    joint_for,
)
from tests.test_ladder import leg  # the module's own CandidateLeg factory

NOW = 1_789_000_000_000


def prop_leg(*, game: str, player: str, market: str, p: float):
    """A prop leg on its own fixture unless `game` repeats."""
    return replace(
        leg(game=game, p=p, market=market, point=0.5),
        player=player,
        team=None,
    )


class TestItIsStagedAndNotServed:
    def test_the_card_is_not_registered(self):
        """A registered card would render "needs 2 fresh games and the slate
        has 0" on every load, because the feed buys no props — which reads as
        a thin slate rather than as a market the desk does not carry."""
        assert STAGED_PROP_CARD not in CARD_SHAPES
        assert STAGED_PROP_CARD.key not in {r.key for r in CARD_SHAPES}

    def test_every_registered_card_still_declines_props(self):
        """The live composition is unchanged by staging this."""
        for recipe in CARD_SHAPES:
            assert recipe.markets is not None, (
                f"{recipe.key} draws from every market in the pool, so it "
                "would start serving prop legs the moment the feed buys one"
            )
            assert not (recipe.markets & MLB_PROP_MARKETS), (
                f"{recipe.key} admits a prop market"
            )

    def test_the_team_market_set_is_untouched(self):
        assert TEAM_MARKETS_ONLY == frozenset({"h2h", "spreads"})


class TestTheMarketNamesMatchTheFeedClient:
    def test_they_equal_prop_base_markets(self):
        """Spelled in `core/ladder.py` to keep the pure core free of
        `backend.*` imports; pinned here so the two cannot drift."""
        from backend.odds.client import PROP_BASE_MARKETS

        assert MLB_PROP_MARKETS == frozenset(PROP_BASE_MARKETS)

    def test_they_are_what_the_candidate_scan_admits(self):
        """If the scan stopped admitting one, this card would silently narrow."""
        from backend.parlays import CANDIDATE_SQL

        for market in MLB_PROP_MARKETS:
            assert f"'{market}'" in CANDIDATE_SQL, (
                f"{market} is not in the candidate scan's allowlist, so no leg "
                "of that market can ever reach this card"
            )


class TestItWouldBuildIfTheFeedBoughtProps:
    """The whole point of staging: enabling it later is a config change."""

    def _pool(self):
        return [
            prop_leg(game="g1", player="Ohtani", market="batter_hits", p=0.81),
            prop_leg(game="g2", player="Skenes", market="pitcher_strikeouts", p=0.74),
            prop_leg(game="g3", player="Judge", market="batter_total_bases", p=0.69),
            prop_leg(game="g4", player="Soto", market="batter_rbis", p=0.55),
        ]

    def test_it_selects_the_likeliest_three(self):
        pool = _pool_for(STAGED_PROP_CARD, self._pool(), now_ms=NOW)
        assert len(pool) == 4
        selected = pool[: STAGED_PROP_CARD.max_legs]
        assert [round(l.p_conservative, 2) for l in selected] == [0.81, 0.74, 0.69]

    def test_it_takes_one_leg_per_fixture(self):
        """Two props in one game are correlated and must not both be taken.
        `_best_per_game` is the structural guard and needs nothing from the
        recipe — this pins that it actually covers props."""
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
        kept = _pool_for(STAGED_PROP_CARD, pool, now_ms=NOW)
        assert all(l.p_conservative >= 0.20 for l in kept)
        assert not any((l.player or "") == "Nobody" for l in kept)

    def test_the_floor_is_set_at_all(self):
        """`min_leg_probability`'s own comment calls it required on any card
        that admits props: the fair side has no other bound, and three 0.2%
        legs render an eight-figure payout beside a fair cost of 0c."""
        assert STAGED_PROP_CARD.min_leg_probability is not None
        assert STAGED_PROP_CARD.min_leg_probability > 0

    def test_the_worst_case_payout_stays_in_the_same_order_as_longshot(self):
        """CLAUDE.md rule 1 applied to the payout column: a big number is a bug
        until shown otherwise. At the floor, three legs is about 125x."""
        floor = STAGED_PROP_CARD.min_leg_probability
        worst = tuple(
            prop_leg(game=f"w{i}", player=f"P{i}", market="batter_hits", p=floor)
            for i in range(STAGED_PROP_CARD.max_legs)
        )
        joint = joint_for(worst)
        assert joint.conservative > 0
        # `fair_decimal` is what the payout column is derived from, so it is
        # the number to bound -- not `naive_product`, which ignores the
        # same-day correlation nudge and is not what the screen renders.
        assert joint.fair_decimal < 400, (
            f"worst-case payout is {joint.fair_decimal:.0f}x, which is a "
            "lottery rather than a card"
        )

    def test_a_team_leg_cannot_reach_this_card(self):
        pool = self._pool() + [leg(game="t1", p=0.95)]
        kept = _pool_for(STAGED_PROP_CARD, pool, now_ms=NOW)
        assert all(l.market in MLB_PROP_MARKETS for l in kept)


class TestTheReasonItIsStagedIsRecorded:
    def test_the_comment_names_the_measurement(self):
        """The next session must not re-derive why this is switched off. If
        the reason moves out of the source, it stops being checkable."""
        import pathlib

        src = (
            pathlib.Path(__file__).resolve().parents[1]
            / "backend" / "core" / "ladder.py"
        ).read_text(encoding="utf-8")
        block = src[src.index("STAGED_PROP_CARD") - 3000 : src.index("STAGED_PROP_CARD")]
        assert "600 hours" in block
        assert "h2h,spreads" in block


@pytest.mark.parametrize("market", sorted(MLB_PROP_MARKETS))
def test_each_prop_market_can_carry_a_leg(market: str):
    """No market in the set is spelled in a way the pool filter drops."""
    pool = _pool_for(
        STAGED_PROP_CARD,
        [
            prop_leg(game="a", player="A", market=market, p=0.7),
            prop_leg(game="b", player="B", market=market, p=0.6),
        ],
        now_ms=NOW,
    )
    assert len(pool) == 2
