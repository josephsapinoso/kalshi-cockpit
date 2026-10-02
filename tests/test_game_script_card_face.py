"""Card face: per-sport inactives, sources shown, and 'Get a price' (#284,
the 2026-10-02 town hall).

- **The inactives line is per sport**, not one NFL-shaped sentence stamped on
  every game: `inactives_line_for` names each sport's own lineup-confirmation
  process, and a sport outside the map says so instead of inventing a clock
  (the town hall's own correction: NHL goalies confirm at warmups, not on a
  timer, so the NHL line must never borrow NFL's "N minutes" shape).
- **A card's sources are rendered**, not just stored: `card.sources` reaches
  `GameScriptCard.tsx`'s "Why this card" detail as links.
- **The build button reads 'Get a price'**, never 'Ask the market': it mints
  the combo only and never fires the RFQ itself (auto-RFQ was killed
  earlier: 36 of 39 asks became a position). The RFQ still fires from
  `<AskTheMarket>`, shown only after a successful mint.

Source assertions for the frontend (this repo has no JS test runner), the
pattern of `tests/test_game_script_card_screen.py`.

What this does not establish: that `drop_if`'s free text is turned into
news-search links. Left undone -- there is no structured name list in a
model-written `drop_if` sentence to link against without guessing at what
counts as a name, and guessing on a live-money screen is worse than leaving
the text plain.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from backend.api.routers import game as game_router
from backend.store import game_script_cards

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "frontend" / "src" / "components" / "GameScriptCard.tsx"


def _strip_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", source, flags=re.MULTILINE)


def _card_body(source: str) -> str:
    card = source[source.index("export default function GameScriptCard") :]
    return card[: card.index("function GameHeading")]


class TestInactivesLineIsPerSport:
    @pytest.mark.parametrize(
        "sport_key, needle",
        [
            ("nfl", "90 minutes before kickoff"),
            ("ncaaf", "90 minutes before kickoff"),
            ("nba", "30 minutes before tipoff"),
            ("wnba", "30 minutes before tipoff"),
            ("mlb", "no fixed"),
            ("nhl", "around warmups"),
        ],
    )
    def test_inactives_line_is_per_sport(self, sport_key, needle):
        assert needle in game_router.inactives_line_for(sport_key)

    def test_an_unmapped_sport_invents_no_clock(self):
        line = game_router.inactives_line_for("curling")
        assert "fixed" in line
        assert "minutes" not in line and "warmups" not in line

    def test_nhl_never_claims_a_fixed_minute_count(self):
        assert not re.search(r"\d+\s*minutes", game_router.inactives_line_for("nhl"))

    def test_every_sport_key_this_repo_derives_has_a_real_line(self):
        # `sport_key_for` strips KX.../GAME from a real Kalshi ticker; every
        # league this build actually discovers should resolve to a real
        # sentence, never silently fall through to the generic fallback.
        tickers_by_sport = {
            "nfl": "KXNFLGAME-26SEP13ATLPIT",
            "ncaaf": "KXNCAAFGAME-26SEP13ATLPIT",
            "nba": "KXNBAGAME-26SEP13ATLPIT",
            "wnba": "KXWNBAGAME-26SEP13ATLPIT",
            "mlb": "KXMLBGAME-26SEP13ATLPIT",
            "nhl": "KXNHLGAME-26SEP13ATLPIT",
        }
        for sport_key, ticker in tickers_by_sport.items():
            assert game_script_cards.sport_key_for(ticker) == sport_key
            line = game_router.inactives_line_for(sport_key)
            assert line != game_router._DEFAULT_INACTIVES_LINE, sport_key


class TestTheComponentRendersTheLineAndSources:
    def test_the_component_reads_the_cards_own_line_not_a_hardcoded_one(self):
        source = _strip_comments(COMPONENT.read_text(encoding="utf-8"))
        assert "{card.inactives_line}" in source
        assert "come out 90 minutes before" not in source

    def test_sources_are_rendered_inside_why_this_card(self):
        source = COMPONENT.read_text(encoding="utf-8")
        details = re.search(r"<details.*?</details>", _card_body(source), flags=re.DOTALL)
        assert details, "no <details> in the card"
        assert "card.sources" in details.group(0)
        assert "source.url" in details.group(0)

    def test_a_card_with_no_sources_renders_no_empty_list(self):
        source = _strip_comments(COMPONENT.read_text(encoding="utf-8"))
        assert "card.sources && card.sources.length > 0" in source


class TestTheBuildButtonReadsGetAPrice:
    def test_the_idle_label_is_get_a_price_not_ask_the_market(self):
        source = _strip_comments(COMPONENT.read_text(encoding="utf-8"))
        assert '"Get a price"' in source
        assert '"Ask the market"' not in source

    def test_the_button_still_only_mints_and_the_rfq_stays_a_separate_tap(self):
        source = _strip_comments(COMPONENT.read_text(encoding="utf-8"))
        card = _card_body(source)
        assert "mintGameCombo(" in card
        # The RFQ itself is `<AskTheMarket>`'s job, shown only after a mint.
        assert "mint.kind === \"minted\"" in card
        assert "<AskTheMarket" in card
