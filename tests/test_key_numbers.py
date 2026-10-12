"""Football key numbers on a spread leg (#348): a display-only fact.

Every line under test is read off a captured payload, never typed in:
`events_nfl_spread.json` (Kalshi `floor_strike`, half points only) and
`odds_nfl_h2h_spreads.json` (Odds API `outcomes[].point`, including 3.0 and
7.0). Kalshi never lists a spread *on* 3, so "on" is a sportsbook-line fact
and "crosses" is the Kalshi one.

WHAT THIS DOES NOT ESTABLISH: that the frontend renders the flag legibly (the
source-reading test pins that the render sits inside `<Term k="key_number">`,
not how it looks), or that a key-number line is mispriced. The flag changes no
`allowed_sides`, `strike` or ticket field; the last test pins that the listing
still carries `strike` unchanged beside it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend import parlays
from backend.core.key_numbers import key_number_flag
from tests.test_game_builder import (
    SPREAD_EVENT,
    _flat,
    _list,
    _fresh_caches,  # noqa: F401  (autouse fixture)
    conn,  # noqa: F401
)

FIXTURES = Path(__file__).parent / "fixtures"
SRC = Path(__file__).resolve().parents[1] / "frontend" / "src"


def _spread_legs(listing):
    return {
        l["strike"]: l for l in _flat(listing) if l["kind"] == "SPREAD"
    }


class TestKalshiSpreadLegs:
    async def test_a_three_and_a_half_line_crosses_three(self, conn):  # noqa: F811
        legs = _spread_legs(await _list(conn))
        assert 3.5 in legs, "the captured fixture must carry a 3.5 line"
        assert legs[3.5]["key_number"] == {"kind": "crosses", "number": 3}

    async def test_a_four_and_a_half_line_carries_no_flag(self, conn):  # noqa: F811
        legs = _spread_legs(await _list(conn))
        assert 4.5 in legs, "the captured fixture must carry a 4.5 line"
        assert legs[4.5]["key_number"] is None

    async def test_every_spread_leg_carries_the_key_and_others_carry_none(self, conn):  # noqa: F811
        listing = await _list(conn)
        assert all("key_number" in l for l in _flat(listing))
        assert all(
            l["key_number"] is None for l in _flat(listing) if l["kind"] != "SPREAD"
        )

    async def test_the_flag_leaves_strike_and_sides_alone(self, conn):  # noqa: F811
        legs = _spread_legs(await _list(conn))
        leg = legs[3.5]
        assert leg["strike"] == 3.5
        assert leg["allowed_sides"] == ["yes", "no"]
        assert SPREAD_EVENT.startswith("KXNFLSPREAD")


def _captured_spread_points() -> list[float]:
    payload = json.loads(
        (FIXTURES / "odds_nfl_h2h_spreads.json").read_text(encoding="utf-8")
    )
    points = []
    for event in payload["events"]:
        for book in event["bookmakers"]:
            for market in book["markets"]:
                if market["key"] == "spreads":
                    points += [o["point"] for o in market["outcomes"]]
    return points


class TestSportsbookSpreadLegs:
    def test_a_line_on_three_is_on_three(self):
        points = _captured_spread_points()
        assert -3.0 in points, "the captured fixture must carry a -3.0 line"
        leg = SimpleNamespace(
            market="spreads", league="americanfootball_nfl", point=-3.0
        )
        assert parlays.parlay_leg_key_number(leg) == {"kind": "on", "number": 3}

    def test_every_captured_line_maps_as_the_rule_says(self):
        for p in _captured_spread_points():
            leg = SimpleNamespace(
                market="spreads", league="americanfootball_nfl", point=p
            )
            flag = parlays.parlay_leg_key_number(leg)
            if abs(p) in (3.0, 6.0, 7.0, 10.0):
                assert flag == {"kind": "on", "number": int(abs(p))}
            elif abs(p) == 4.5:
                assert flag is None

    def test_a_basketball_spread_or_a_total_is_never_flagged(self):
        nba = SimpleNamespace(market="spreads", league="basketball_nba", point=3.0)
        total = SimpleNamespace(
            market="totals", league="americanfootball_nfl", point=3.0
        )
        assert parlays.parlay_leg_key_number(nba) is None
        assert parlays.parlay_leg_key_number(total) is None


class TestTheHelper:
    @pytest.mark.parametrize(
        "line,expected",
        [
            (3.0, {"kind": "on", "number": 3}),
            (-7.0, {"kind": "on", "number": 7}),
            (2.5, {"kind": "crosses", "number": 3}),
            (6.5, {"kind": "crosses", "number": 7}),
            (5.5, {"kind": "crosses", "number": 6}),
            (4.5, None),
            (None, None),
        ],
    )
    def test_the_rule(self, line, expected):
        assert key_number_flag(line) == expected


class TestTheRenderSites:
    @pytest.mark.parametrize("name", ["GameLegs.tsx", "ParlayCards.tsx"])
    def test_key_number_renders_inside_its_term(self, name):
        text = (SRC / "components" / name).read_text(encoding="utf-8")
        assert re.search(
            r'<Term k="key_number">\{keyNumberWords\(leg\.key_number\)\}</Term>',
            text,
        ), name

    def test_the_type_declares_the_field(self):
        text = (SRC / "lib" / "types" / "parlays.ts").read_text(encoding="utf-8")
        assert text.count("key_number") >= 2
