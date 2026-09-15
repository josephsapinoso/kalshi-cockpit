"""The Under of a total or prop is a parlay leg: the NO of Kalshi's Over market.

Until 2026-09-14 every parlay leg was a Kalshi YES by construction, and the
ladder's prop arm dropped the Under row without a count. A "likeliest" card
built from Over rows alone leans to overs. Now a row whose outcome is
`Under` becomes a `CandidateLeg` with `side = "no"` on the same market the
Over row matched, its own `p_conservative` (the Under row's, never one minus
the Over's), and a label that says which way it goes. The side travels
through the wire (`serialise_leg`), the lookup echo, the venue's body
(`lookup_combo`) and into `parlay_lookups.selected_legs`, which is what a
recorded position and `/hedge` read.

What these establish: the pool emits both sides of a prop and a total; at
most one of them (one leg per fixture) reaches a card; the joint memo key
carries the side; the venue is asked for each leg's own side; and a venue
echo that flips a side is a mismatch, not a spelling.

What they do not establish: that any Kalshi collection accepts a mixed-side
card. The fixtures name `is_all_yes` collections; the first live lookup of a
card carrying a NO leg is the measurement, and a refusal there is a venue
fact to record, not a defect here.
"""

from __future__ import annotations

from dataclasses import replace

from backend.core.ladder import _best_per_game, _joint_key
from backend.kalshi.combos import echoed_legs, lookup_combo
from backend.parlays import _serialise_leg, ladder_candidates, leg_details_for
import pytest

from backend.store import db as store
from backend.store.db import now_ms
from tests.test_ladder import leg
from tests.test_parlays_api import seed_prop, seed_total


@pytest.fixture
def conn(tmp_path):
    c = store.init_db(tmp_path / "under.db")
    yield c
    c.close()


class TestThePoolEmitsBothSides:
    def test_a_prop_under_row_is_a_no_leg_on_the_over_market(self, conn):
        seed_prop(conn, game="g1", player="Anthony Kay", strike=5.5, p=0.55)
        conn.commit()
        legs, excluded = ladder_candidates(
            conn, now_ms=now_ms(), max_odds_age_ms=900_000
        )
        props = sorted((l.side, l) for l in legs if l.player)
        assert [side for side, _ in props] == ["no", "yes"]
        under, over = props[0][1], props[1][1]
        assert under.kalshi_market_ticker == over.kalshi_market_ticker
        assert under.label == "NO on Anthony Kay: 6+ strikeouts"
        assert over.label == "Anthony Kay: 6+ strikeouts"
        # The Under row's OWN consensus: seeded as 1 - p - 0.02.
        assert round(under.p_conservative, 2) == 0.43
        assert "prop_no_kalshi_rung" not in excluded, excluded

    def test_a_total_under_row_is_a_no_leg_with_kalshis_phrasing_turned(self, conn):
        seed_total(conn, game="g1", line=8.5, p=0.56)
        conn.commit()
        legs, _ = ladder_candidates(conn, now_ms=now_ms(), max_odds_age_ms=900_000)
        totals = {l.side: l for l in legs if l.market == "totals"}
        assert set(totals) == {"yes", "no"}
        assert totals["no"].label == "Under 8.5 runs scored"
        assert totals["yes"].label == "Over 8.5 runs scored"
        assert totals["no"].kalshi_market_ticker == totals["yes"].kalshi_market_ticker
        assert totals["no"].team is None and totals["no"].player is None

    def test_a_team_leg_is_always_yes(self, conn):
        from tests.test_parlays_api import seed_game

        seed_game(conn, game="g1", team="Alpha", other="Beta", computed_ms=now_ms())
        conn.commit()
        legs, _ = ladder_candidates(conn, now_ms=now_ms(), max_odds_age_ms=900_000)
        assert legs and all(l.side == "yes" for l in legs)

    def test_the_wire_carries_the_side(self, conn):
        seed_total(conn, game="g1", line=8.5, p=0.56)
        conn.commit()
        legs, _ = ladder_candidates(conn, now_ms=now_ms(), max_odds_age_ms=900_000)
        under = next(l for l in legs if l.side == "no")
        assert _serialise_leg(under)["side"] == "no"
        assert leg_details_for([under])[
            (under.kalshi_event_ticker, under.kalshi_market_ticker)
        ]["side"] == "no"


class TestOverAndUnderOfOneGameCannotBothBeTaken:
    def test_one_leg_per_fixture_holds_across_sides(self):
        over = replace(leg("g1", p=0.56, market="totals", point=8.5, ticker="T"), team=None)
        under = replace(over, side="no", p_conservative=0.42, label="Under 8.5 runs scored")
        kept = _best_per_game([over, under], prefer_spreads=False)
        assert len(kept) == 1
        assert kept[0].side == "yes"  # the likelier one


class TestTheJointMemoKnowsTheSide:
    def test_yes_and_no_of_one_market_have_different_keys(self):
        """Mutation observed red: drop `leg.side` from `_joint_key` -- the
        Under of a market would be served the Over's cached joint."""
        over = replace(leg("g1", p=0.56, market="totals", point=8.5, ticker="T"), team=None)
        under = replace(over, side="no")
        assert _joint_key([over]) != _joint_key([under])


class _CapturingApi:
    def __init__(self):
        self.bodies = []

    async def request(self, method, path, json_body=None):
        self.bodies.append((method, path, json_body))
        return {"market_ticker": "KXMVE-X", "market": {"ticker": "KXMVE-X"}}


class TestTheVenueIsAskedForEachLegsOwnSide:
    async def test_lookup_combo_posts_per_leg_sides(self):
        api = _CapturingApi()
        await lookup_combo(
            api, "KXMVESPORTSMULTIGAMEEXTENDED-R",
            [("E1", "M1", "yes"), ("E2", "M2", "no"), ("E3", "M3")],
            side="yes", allow_market_creation=True,
        )
        (_, _, body), = api.bodies
        assert body["selected_markets"] == [
            {"event_ticker": "E1", "market_ticker": "M1", "side": "yes"},
            {"event_ticker": "E2", "market_ticker": "M2", "side": "no"},
            {"event_ticker": "E3", "market_ticker": "M3", "side": "yes"},
        ]

    def test_an_echo_that_flips_a_side_is_a_mismatch(self):
        """Mutation observed red: `_leg_sides` ignoring the third element
        makes the desk's NO leg compare as YES and the flip pass."""
        response = {"market": {"mve_selected_legs": [
            {"event_ticker": "E1", "market_ticker": "M1", "side": "yes"},
            {"event_ticker": "E2", "market_ticker": "M2", "side": "yes"},
        ]}}
        echo = echoed_legs([("E1", "M1", "yes"), ("E2", "M2", "no")], response)
        assert echo.is_mismatch
        assert "M2" in echo.detail

    def test_a_faithful_echo_matches(self):
        response = {"market": {"mve_selected_legs": [
            {"event_ticker": "E2", "market_ticker": "M2", "side": "no"},
            {"event_ticker": "E1", "market_ticker": "M1", "side": "yes"},
        ]}}
        echo = echoed_legs([("E1", "M1", "yes"), ("E2", "M2", "no")], response)
        assert echo.verdict == "match"
