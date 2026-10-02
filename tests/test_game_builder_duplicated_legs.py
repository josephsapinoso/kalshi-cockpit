"""A team to win beside that team's cover is refused before Kalshi (#277).

Kalshi refuses the pair as `duplicated_legs`: winning by N+ already guarantees
the win (Joe hit it on /parlays 2026-09-30, `store/game_script_cards.py`'s
`drop_implied_win_legs` docstring). On the hand-ticked /game path the refusal
used to come back from the venue as a recorded 502 AFTER the mint call. Joe's
answer to #274 was (A): refuse in words, never drop a leg silently.

What these tests establish
--------------------------
- YES "team wins" + YES "that team wins by N+" is a worded 422 before any venue
  call, with no `parlay_lookups` row, and the words name both markets.
- The detection is `drop_implied_win_legs` (reused, for detection only); the
  refusal does not drop a leg and mint the rest.
- The pairs that are NOT duplicates still mint with every ticked leg: the
  other team's cover, a NO win leg, a NO cover leg.
- The screen greys the win box while that team's cover is ticked (source
  assertion; this repo has no JS test runner).

What they do not establish
--------------------------
- That these are the only pairs Kalshi calls duplicated; any other it refuses
  still arrives as a recorded venue refusal.
- How the greyed box looks.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.test_game_builder import (  # noqa: F401
    ATL,
    GAME,
    PIT,
    _fresh_caches,
    _get,
    _leg,
    _mint,
    _rec_markets,
    _rows,
    build,
)

PIT_COVER = "KXNFLSPREAD-26SEP13ATLPIT-PIT7"

GAME_SCREEN = (
    Path(__file__).resolve().parents[1]
    / "frontend" / "src" / "components" / "GameLegs.tsx"
)


async def test_win_plus_cover_is_refused_with_no_venue_call(build):  # noqa: F811
    app, fake, lookups, path = build()
    await _get(app, f"/api/game/{GAME}/legs")
    fake.calls.clear()
    response = await _mint(app, [_leg(PIT), _leg(PIT_COVER)])
    assert response.status_code == 422, response.text
    words = response.json()["detail"]
    assert PIT in words and PIT_COVER in words
    assert "already" in words and "Nothing was created" in words
    assert lookups == []
    assert fake.calls == []
    assert _rows(path) == []


async def test_the_order_of_the_two_legs_does_not_matter(build):  # noqa: F811
    app, fake, lookups, _path = build()
    await _get(app, f"/api/game/{GAME}/legs")
    response = await _mint(app, [_leg(PIT_COVER), _leg(PIT)])
    assert response.status_code == 422
    assert lookups == []


async def test_a_third_leg_does_not_hide_the_pair(build):  # noqa: F811
    app, _fake, lookups, _path = build()
    await _get(app, f"/api/game/{GAME}/legs")
    response = await _mint(
        app, [_leg(_rec_markets()[0]), _leg(PIT), _leg(PIT_COVER)]
    )
    assert response.status_code == 422
    assert lookups == []


@pytest.mark.parametrize(
    "legs",
    [
        # The OTHER team's win beside PIT's cover is not a duplicate.
        [_leg(ATL), _leg(PIT_COVER)],
        # A NO win leg beside the cover is not the pair Kalshi refuses.
        [_leg(PIT, "no"), _leg(PIT_COVER)],
        # Nor is the win beside a NO cover.
        [_leg(PIT), _leg(PIT_COVER, "no")],
    ],
    ids=["other_team", "no_win", "no_cover"],
)
async def test_the_pairs_that_are_not_duplicates_mint_with_every_leg(build, legs):  # noqa: F811
    app, _fake, lookups, _path = build()
    await _get(app, f"/api/game/{GAME}/legs")
    response = await _mint(app, legs)
    assert response.status_code == 200, response.text
    assert len(lookups) == 1
    _collection, wire = lookups[0]
    assert sorted(wire) == sorted(
        (l["event_ticker"], l["market_ticker"], l["side"]) for l in legs
    ), "no leg may be dropped silently"


def test_the_screen_greys_the_win_box_while_that_teams_cover_is_ticked():
    src = GAME_SCREEN.read_text(encoding="utf-8")
    assert "coverTickedFor" in src
    # The grey-out feeds the same disabled expression as the one-rung block.
    assert re.search(r"winGreyed\s*=\s*[^;]*impliedByCover", src, re.DOTALL)
    assert re.search(r"sideBlocked\s*=\s*[^;]*winGreyed", src, re.DOTALL)
    assert "disabled={sideBlocked}" in src
    # Only a leg that is not itself ticked is greyed, so a pair ticked in the
    # other order can still be unticked.
    assert re.search(r'ticked\[leg\.market_ticker\]\s*!==\s*"yes"', src)
    # Build is off while the pair stands.
    # (the panel's button and the phone bar both read `buildDisabled`).
    assert re.search(r"buildDisabled\s*=\s*[^;]*impliedPair", src, re.DOTALL)
    assert "already guarantees" in src
