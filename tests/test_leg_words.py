"""A NO leg is worded as its opposite (#275).

What these tests establish
--------------------------
- On the CAPTURED listing (`events_nhl_same_game.json`) Kalshi's `no_sub_title`
  equals `yes_sub_title` on the moneyline, spread and total markets. That is
  the premise, asserted, so a Kalshi change that fixes it shows up here.
- `no_side_words` words each kind as its opposite and NEVER returns the YES
  wording; the kind is read from the series, and an unknown kind or a
  sub-title of the wrong shape gets the generic line rather than a guess.
- The same helper feeds the /game leg list's `no_label`, the card legs'
  `side_label`, and (through the leg dict) the scout prompt's `no=` field.

What they do not establish
--------------------------
- That every Kalshi sub-title in the wild matches the three shapes; the ones
  that do not fall to the generic line, which is the designed behaviour.
- How the page renders (frontend is checked by `tsc` and the copy tests).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.agents.game_script import build_prompt
from backend.api.routers.game import _read_leg_asks
from backend.core.leg_words import (
    GENERIC_NO_WORDS,
    league_prefix_of,
    no_side_words,
    no_words_for,
)

# Fixtures (autouse cache reset, db, fake api) shared with the builder tests.
from tests.test_game_builder import (  # noqa: F401
    GAME,
    FakeApi,
    _fresh_caches,
    _flat,
    _list,
)
from backend.store import db as store

NHL_GAME = "KXNHLGAME-26OCT01BUFCBJ"


@pytest.fixture
def conn(tmp_path):
    c = store.init_db(tmp_path / "leg_words.db")
    yield c
    c.close()


def _nhl_markets() -> list[dict]:
    path = Path(__file__).parent / "fixtures" / "events_nhl_same_game.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [m for e in payload["events"] for m in e["markets"]]


def _series(market: dict) -> str:
    return market["ticker"].split("-")[0]


class TestThePremise:
    def test_kalshi_repeats_the_yes_wording_on_the_no_side(self):
        same = [
            m for m in _nhl_markets()
            if m["no_sub_title"] == m["yes_sub_title"]
        ]
        assert len(same) >= 10, "the capture must show the repeat on many legs"


class TestWordsPerKind:
    def test_a_no_leg_never_shows_the_yes_wording(self):
        seen_kinds = set()
        for market in _nhl_markets():
            words = no_words_for(
                series=_series(market), game_event_ticker=NHL_GAME,
                yes_label=market["yes_sub_title"],
            )
            assert words != market["yes_sub_title"], market["ticker"]
            assert words != market["no_sub_title"], market["ticker"]
            seen_kinds.add(_series(market))
        assert {"KXNHLGAME", "KXNHLSPREAD", "KXNHLTOTAL"} <= seen_kinds

    def test_a_total_is_under_the_same_line(self):
        assert no_side_words(kind="TOTAL", yes_label="Over 4.5 goals scored") == (
            "Under 4.5 goals scored"
        )

    def test_a_moneyline_is_team_does_not_win(self):
        assert no_side_words(kind="GAME", yes_label="Carolina") == (
            "Carolina does not win"
        )

    def test_a_cover_is_not_team_wins_by_n_plus(self):
        assert no_side_words(
            kind="SPREAD", yes_label="Columbus wins by over 2.5 goals"
        ) == "Not: Columbus wins by 3+"
        assert no_side_words(
            kind="SPREAD", yes_label="Virginia Tech wins by over 3.5 points"
        ) == "Not: Virginia Tech wins by 4+"

    def test_an_unknown_kind_gets_the_generic_line_never_a_guess(self):
        for kind in ("1HSPREAD", "TEAMTOTAL", "PASSYDS", None):
            assert no_side_words(kind=kind, yes_label="Over 4.5 yards") == (
                GENERIC_NO_WORDS
            )

    def test_a_sub_title_of_the_wrong_shape_gets_the_generic_line(self):
        assert no_side_words(kind="TOTAL", yes_label="Atlanta: 125+") == GENERIC_NO_WORDS
        assert no_side_words(kind="SPREAD", yes_label="Columbus") == GENERIC_NO_WORDS
        assert no_side_words(kind="GAME", yes_label="Columbus wins") == GENERIC_NO_WORDS
        assert no_side_words(kind="GAME", yes_label=None) == GENERIC_NO_WORDS
        # A whole-number strike can push; it is not worded as "Under".
        assert no_side_words(kind="TOTAL", yes_label="Over 3 goals") == GENERIC_NO_WORDS

    def test_the_kind_comes_from_the_series_under_the_leagues_prefix(self):
        assert league_prefix_of(NHL_GAME) == "KXNHL"
        assert league_prefix_of("KXNHLSPREAD-26OCT01BUFCBJ") is None
        # `1HSPREAD` is not `SPREAD`: a first-half cover is not worded as a
        # full-game one.
        assert no_words_for(
            series="KXNHL1HSPREAD", game_event_ticker=NHL_GAME,
            yes_label="Columbus wins by over 0.5 goals",
        ) == GENERIC_NO_WORDS
        # A series under ANOTHER league's prefix is not sliced by length.
        assert no_words_for(
            series="KXNBASPREAD", game_event_ticker=NHL_GAME,
            yes_label="Columbus wins by over 2.5 goals",
        ) == GENERIC_NO_WORDS
        assert no_words_for(
            series="KXNHLSPREAD", game_event_ticker="not a ticker",
            yes_label="Columbus wins by over 2.5 goals",
        ) == GENERIC_NO_WORDS


class TestWhereItIsWired:
    async def test_the_game_leg_list_words_the_no_side(self, conn):
        listing = await _list(conn)
        legs = _flat(listing)
        spread = next(l for l in legs if l["series"] == "KXNFLSPREAD")
        assert spread["yes_label"] and spread["no_label"] != spread["yes_label"]
        assert spread["no_label"].startswith("Not: ")
        game = next(l for l in legs if l["series"] == "KXNFLGAME")
        assert game["no_label"] == f"{game['yes_label']} does not win"
        for leg in legs:
            assert leg["no_label"] != leg["yes_label"], leg["market_ticker"]

    async def test_the_scout_prompt_carries_the_worded_no(self, conn):
        listing = await _list(conn)
        prompt = build_prompt(
            game_title="Atlanta at Pittsburgh", sport_key="nfl",
            kickoff_iso="2026-09-13T17:00:00Z", listing=listing,
        )
        assert "does not win" in prompt
        assert "Not: " in prompt

    async def test_a_card_legs_no_side_label_is_the_opposite(self):
        markets = _nhl_markets()
        by_event: dict[str, list[dict]] = {}
        for m in markets:
            by_event.setdefault(m["event_ticker"], []).append(m)

        class Api(FakeApi):
            pass

        api = Api(markets=by_event)
        cover = next(m for m in markets if m["ticker"].endswith("CBJ3"))
        legs = [
            {"market_ticker": cover["ticker"], "event_ticker": cover["event_ticker"],
             "side": "no"},
            {"market_ticker": cover["ticker"], "event_ticker": cover["event_ticker"],
             "side": "yes"},
        ]
        out = await _read_leg_asks(api, legs, now_ms=1, game_event_ticker=NHL_GAME)
        assert out[0]["side_label"] == "Not: Columbus wins by 3+"
        assert out[1]["side_label"] == "Columbus wins by over 2.5 goals"
