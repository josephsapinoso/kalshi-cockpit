"""`/parlays` Game scripts: games without a card are one list (#390).

Source assertions (this repo has no JS test runner). Pins:

- every game with no built card is a row of ONE list, linking to its game
  (`/game/<event>`), in the server's kickoff order -- no build button on
  /parlays, because an NFL card tap can cost about a million tokens;
- the "tap a card size" instruction is said once, above that list, and a row
  repeats only a reason that differs from it;
- league tags on game headings render through `LeagueTag` (uppercase).

Does not establish: how the page looks at 390px.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "frontend" / "src" / "components"


def _code(name: str) -> str:
    source = (SRC / name).read_text(encoding="utf-8")
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", source, flags=re.MULTILINE)


def _list_body() -> str:
    src = _code("GameScriptCard.tsx")
    return src[src.index("export function GameScriptParlays") :]


class TestUnbuiltGamesAreOneList:
    def test_games_without_a_card_render_as_one_list_each_linking_to_its_game(self):
        body = _list_body()
        # one section, one <ul>, rows mapped from the unbuilt subset
        assert body.count('aria-label="Games without a card"') == 1
        assert "unbuilt.map((card) =>" in body
        assert "<UnbuiltRow" in body
        # the built grid no longer draws unbuilt cards as boxes
        assert 'card.status === "built"' in body
        row = _code("GameScriptCard.tsx")
        row = row[row.index("function UnbuiltRow") :]
        row = row[: row.index("\n}\n")]
        assert "/game/${encodeURIComponent(card.game_event_ticker)}" in row
        assert "Make a card" in row
        # no build control on /parlays
        assert "buildGameCard" not in body
        assert "CARD_SIZES.map" not in row
        # server order: the subset is a filter, never sorted
        assert not re.search(r"unbuilt[^;]*\.(sort|reverse)\(", body)

    def test_the_instruction_is_said_once_above_the_list(self):
        body = _list_body()
        assert body.count("{GENERIC_NO_CARD_LINE}") == 1
        assert body.index("{GENERIC_NO_CARD_LINE}") < body.index("unbuilt.map")
        row = _code("GameScriptCard.tsx")
        row = row[row.index("function UnbuiltRow") :]
        # a row repeats only a reason that differs from the generic line
        assert "line !== GENERIC_NO_CARD_LINE" in row


class TestLeagueTagsAreUppercase:
    def test_league_tags_render_uppercase(self):
        src = _code("GameScriptCard.tsx")
        heading = src[src.index("function GameHeading") :]
        heading = heading[: heading.index("\n}\n")]
        assert "<LeagueTag league={card.sport_key} />" in heading
        assert "leagueLabel(" not in heading
        assert "uppercase" in _code("LeagueTag.tsx")
