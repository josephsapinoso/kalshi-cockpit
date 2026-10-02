"""The game page names its game, and rest rides on every leg (#293, ADR 0189).

What these tests establish
--------------------------
- `list_game_legs` returns the game's own title, the desk's kickoff and the
  odds feed's sport key, and puts the same `{home, away}` rest on EVERY leg
  of the listing (the shape `RestChip` reads on the parlay cards).
- A game the desk cannot identify carries `null` on every one of those, never
  a guessed kickoff or a zero.
- `/api/game-cards` legs carry `rest` too.
- The screens (source assertions; this repo has no JS test runner) reuse the
  one `RestChip` from `ParlayCards`, draw the title/kickoff/league, and
  nothing on either screen sorts or filters by rest.

What this does not establish: that the chip renders at phone width, or that
rest is right for a real fixture (`tests/test_team_rest_reader.py` owns that).
"""

from __future__ import annotations

import re
from pathlib import Path

from backend import game_builder
from backend.store import db as store
from backend.store.db import now_ms
from tests.test_game_builder import (  # noqa: F401 -- fixtures
    GAME,
    MAX_ODDS_AGE_MS,
    FakeApi,
    _flat,
    _fresh_caches,
    conn,
    seed_moneyline,
)

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "frontend" / "src"
LEGS = SRC / "components" / "GameLegs.tsx"
CARD = SRC / "components" / "GameScriptCard.tsx"
PAGE = SRC / "app" / "game" / "[event]" / "page.tsx"


def _code(path: Path) -> str:
    source = path.read_text(encoding="utf-8")
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    source = re.sub(r"\{/\*.*?\*/\}", "", source, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", source, flags=re.MULTILINE)


async def _list(conn):
    return await game_builder.list_game_legs(
        conn, game_event_ticker=GAME, now_ms=now_ms(),
        max_odds_age_ms=MAX_ODDS_AGE_MS, api=FakeApi(),
    )


def _earlier_game(conn, *, days_before):
    """Pittsburgh's previous game, so its rest is a real number."""
    conn.execute(
        "INSERT INTO odds_snapshots (fetched_ms, sport_key, odds_event_id, "
        "commence_ms, home_team, away_team, bookmaker, market, outcome_name, "
        "price_decimal) VALUES (?, 'americanfootball_nfl', 'nfl-prev', ?, "
        "'Pittsburgh', 'Baltimore', 'pinnacle', 'h2h', 'Pittsburgh', 1.9)",
        (now_ms(), now_ms() + 3 * 3_600_000 - days_before * 86_400_000),
    )
    conn.commit()


async def test_every_game_leg_carries_rest_and_the_page_names_the_game(conn):
    seed_moneyline(conn, atl_p=0.6, computed_ms=now_ms())
    _earlier_game(conn, days_before=7)
    listing = await _list(conn)

    assert listing["game_title"] == "Atlanta vs Pittsburgh"
    assert listing["sport_key"] == "americanfootball_nfl"
    assert isinstance(listing["kickoff_ms"], int)

    legs = _flat(listing)
    assert len(legs) > 10
    for leg in legs:
        rest = leg["rest"]
        assert rest is not None, leg["market_ticker"]
        assert rest["home"]["team"] == "Pittsburgh"
        assert rest["away"]["team"] == "Atlanta"
    # Pittsburgh played a week earlier; Atlanta has no game on record and
    # reads unknown, never zero days.
    assert legs[0]["rest"]["home"]["days_rest"] in (6, 7)
    assert legs[0]["rest"]["away"]["days_rest"] is None


class TestTheGameIsNamedAndEveryLegCarriesRest:
    async def test_an_unidentified_game_carries_nulls_not_guesses(self, conn):
        listing = await _list(conn)
        assert listing["game_title"] is None
        assert listing["kickoff_ms"] is None
        assert listing["sport_key"] is None
        assert all(leg["rest"] is None for leg in _flat(listing))

    async def test_rest_does_not_move_the_order(self, conn):
        seed_moneyline(conn, atl_p=0.6, computed_ms=now_ms())
        before = [l["market_ticker"] for l in _flat(await _list(conn))]
        _earlier_game(conn, days_before=1)
        after = [l["market_ticker"] for l in _flat(await _list(conn))]
        assert before == after


class TestTheCardsCarryRest:
    def test_a_built_cards_legs_get_the_games_rest(self):
        router = (REPO / "backend" / "api" / "routers" / "game.py").read_text(
            encoding="utf-8"
        )
        assert 'game_context(conn, card["game_event_ticker"])["rest"]' in router
        assert 'leg["rest"] = rest' in router


class TestTheScreens:
    def test_both_surfaces_reuse_the_one_rest_chip(self):
        for path in (LEGS, CARD):
            code = _code(path)
            assert 'import { RestChip } from "@/components/ParlayCards"' in code
            assert "<RestChip rest={leg.rest} />" in code
        # Not re-implemented: the chip's own markup is not copied in.
        assert "leg-rest" not in _code(LEGS) + _code(CARD)

    def test_the_game_page_draws_title_kickoff_and_league(self):
        code = _code(LEGS)
        assert "data?.game_title" in code
        assert "formatKickoff(kickoff)" in code
        assert "leagueLabel(sport)" in code
        # The page no longer prints the raw ticker as its subtitle.
        assert "{eventTicker}</p>" not in _code(PAGE)

    def test_nothing_sorts_or_filters_by_rest(self):
        for path in (LEGS, CARD):
            code = _code(path)
            assert not re.search(r"\.(sort|toSorted)\(", code)
            assert not re.search(r"\.rest\s*[<>]|\.rest\b.*\.(sort|filter)\(", code)
