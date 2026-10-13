"""Game and market wayfinding (#389).

/game/<event> heads with the teams, league and kickoff and falls back to the
ticker only when the listing has no names; it links back to Games; the market
page links to its game; and the market page has no filled button.

Source assertions (this repo has no JS test runner).

What these tests establish
--------------------------
- GameHeader draws the title first and the ticker only in the no-title branch,
  and GameLegs feeds it the listing's title, league and kickoff.
- GameHeader carries a link to `/`; the market page carries a link to
  `/game/...` built from `lib/gameEvent`, which does not import the slate.
- Neither the market page nor ScoutDesk contains `bg-accent-fill`.

What they do not establish
--------------------------
- How any of it looks at 390px; that is a screenshot job.
- That `ManualTicket`'s own controls (another file, not this lane's) are
  unfilled; "Open the ticket" is deliberately left as it is (ADR 0071).
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "frontend" / "src"


def _read(*parts: str) -> str:
    return (SRC.joinpath(*parts)).read_text(encoding="utf-8").replace("\r\n", "\n")


def test_game_page_heads_with_teams_and_kickoff_not_the_ticker():
    header = _read("components", "GameHeader.tsx")
    legs = _read("components", "GameLegs.tsx")
    lib = _read("lib", "gameEvent.ts")
    # The title leads; the ticker is only the fallback when there is no title.
    assert "parts.title ??" in header
    assert header.index("parts.title") < header.index("{eventTicker}")
    assert header.count("{eventTicker}") == 1
    # The line is title, then league, then kickoff.
    assert "[league, kickoff]" in lib
    # GameLegs hands the header the listing's own fields.
    assert "<GameHeader" in legs
    assert "title={title}" in legs
    assert "league={sport ? leagueLabel(sport) : null}" in legs
    assert "formatKickoff(kickoff)" in legs
    # The page no longer leads with a fixed h1 over the game.
    assert "<h1" not in _read("app", "game", "[event]", "page.tsx")


def test_game_page_links_back_to_games():
    header = _read("components", "GameHeader.tsx")
    assert 'href="/"' in header
    assert "Games" in header


def test_market_page_links_to_its_game():
    page = _read("app", "market", "[ticker]", "page.tsx")
    lib = _read("lib", "gameEvent.ts")
    assert 'from "@/lib/gameEvent"' in page
    assert "href={`/game/${encodeURIComponent(gameEventOf(ticker)" in page
    assert "export function gameEventOf" in lib
    for code in (lib, page):
        assert not re.search(r"from\s+\"[^\"]*slate[^\"]*\"", code)


def test_no_filled_button_on_the_market_page():
    for parts in (
        ("app", "market", "[ticker]", "page.tsx"),
        ("components", "ScoutDesk.tsx"),
    ):
        code = _read(*parts)
        # Comments may name the class; markup may not.
        lines = [
            ln for ln in code.splitlines()
            if "bg-accent-fill" in ln
            and not ln.lstrip().startswith(("*", "//", "/*", "{/*"))
        ]
        assert lines == [], (parts, lines)
