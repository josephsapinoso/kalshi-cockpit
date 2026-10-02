"""The game-script card's face (#284, #285; parlay town hall 2026-10-02).

#284
- **The lineup line is per sport.** NFL keeps its cited 90 minutes; NHL says
  goalies are confirmed around warmups; every other sport says it has no fixed
  confirmation time. No time is invented for a sport this repo cannot cite.
- **Names in `drop_if` are news-search links** (a pure function, run in Node).
- **Sources and `ticket_needs` sit inside "Why this card"**, `ticket_needs`
  as "What this ticket needs:".
- **The build button is "Get a price"** and building never fires the RFQ: the
  component's only venue calls are `mintGameCombo` and `buildGameCard`, and the
  RFQ stays behind `<AskTheMarket>`'s own button.

#285
- **Then and now are two stamped facts**: "58c now · read 9:14" and "53c when
  written", from each leg's `at_build`, with depth behind a tap and no arrow,
  no colour, and no sportsbook line move beside it.

These are source assertions plus one Node run of the pure helper (this repo
has no JS test runner for components).

What this does not establish: that the card renders well at phone width, or
that the name heuristic finds every name a scout writes.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from backend.api.routers import game as game_router
from tests._node_driver import node_driver

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "frontend" / "src"
COMPONENT = SRC / "components" / "GameScriptCard.tsx"
NAMES = SRC / "lib" / "dropIfNames.ts"
NODE = shutil.which("node")


def _code(path: Path) -> str:
    source = path.read_text(encoding="utf-8")
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", source, flags=re.MULTILINE)


def _details() -> str:
    src = _code(COMPONENT)
    card = src[src.index("export default function GameScriptCard"):]
    card = card[: card.index("function GameHeading")]
    found = re.search(r"<details.*?</details>", card, flags=re.DOTALL)
    assert found
    return found.group(0)


def _split(text: str, source: str | None = None, tmp_path=None):
    driver = (
        'import { splitDropIf } from "./dropIfNames.ts";\n'
        "console.log(JSON.stringify(splitDropIf(process.argv[2])));\n"
    )
    module_dir = NAMES.parent
    if source is not None:
        module_dir = tmp_path
        (module_dir / "dropIfNames.ts").write_text(source, encoding="utf-8")
    with node_driver(module_dir, driver) as path:
        out = subprocess.run(
            [NODE, "--experimental-strip-types", str(path), text],
            capture_output=True, text=True, timeout=60, cwd=str(module_dir),
        )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


class TestInactivesLineIsPerSport:
    def test_inactives_line_is_per_sport(self):
        nfl = game_router.lineup_line("nfl")
        nhl = game_router.lineup_line("nhl")
        mlb = game_router.lineup_line("mlb")
        assert "90 minutes before kickoff" in nfl
        assert "warmups" in nhl and "90 minutes" not in nhl
        assert "no fixed" in mlb and "90 minutes" not in mlb
        assert len({nfl, nhl, mlb}) == 3
        # An unknown or blank sport never borrows the NFL's time.
        for key in ("", "wnba", "ncaaf", "KXNBA"):
            assert "90 minutes" not in game_router.lineup_line(key)

    def test_the_card_payload_carries_the_sports_own_line(self, tmp_path, monkeypatch):
        from backend.store import db
        from tests.test_game_script_card_screen import NOW, HOUR, _app, _built

        monkeypatch.setattr(db, "now_ms", lambda: NOW)
        http, conn = _app(tmp_path)
        _built(conn, "KXNFLGAME-26SEP13ATLPIT", NOW + 5 * HOUR)
        card = http.get("/api/game-cards").json()["cards"][0]
        assert card["inactives_line"] == game_router.lineup_line("nfl")

    def test_the_component_renders_the_served_line_not_its_own(self):
        details = _details()
        assert "{card.inactives_line}" in details
        assert "come out 90 minutes before" not in _code(COMPONENT)

    def test_before_inactives_is_claimed_for_the_nfl_only(self):
        src = _code(COMPONENT)
        assert re.search(r'card\.sport_key\s*===\s*"nfl"\s*&&\s*card\.built_ms', src)


class TestSourcesAndTicketNeedsInsideWhyThisCard:
    def test_ticket_needs_and_sources_are_inside_the_details(self):
        details = _details()
        assert "What this ticket needs:" in _code(COMPONENT)
        assert "{TICKET_NEEDS_LABEL}" in details
        assert "{card.ticket_needs}" in details
        # Drawn only when the card has one: an older card says nothing rather
        # than an empty "What this ticket needs:".
        assert "{card.ticket_needs && (" in details
        assert "card.sources" in details
        # Every external link opens a new tab without handing over the opener.
        assert details.count('target="_blank"') == 2
        assert details.count('rel="noopener noreferrer"') == details.count(
            'target="_blank"'
        )

    def test_the_face_outside_the_details_carries_neither(self):
        src = _code(COMPONENT)
        card = src[src.index("export default function GameScriptCard"):]
        card = card[: card.index("function GameHeading")]
        outside = card.replace(_details(), "")
        assert "card.sources" not in outside and "card.ticket_needs" not in outside


class TestDropIfNamesAreNewsLinks:
    def test_the_component_links_every_name_to_a_news_search(self):
        details = _details()
        assert "splitDropIf(card.drop_if)" in details
        assert "newsSearchUrl(part.name)" in details
        assert "news.google.com/search?q=" in _code(COMPONENT)

    @pytest.mark.skipif(NODE is None, reason="node is not on PATH")
    def test_names_are_found_and_plain_words_are_not(self):
        parts = _split(
            "Skip it if Patrick Mahomes is ruled out or the Chiefs rest starters."
        )
        names = [p["name"] for p in parts if p["name"]]
        assert names == ["Patrick Mahomes", "Chiefs"]
        assert "".join(p["text"] for p in parts).startswith("Skip it if ")
        assert "".join(p["text"] for p in parts) == (
            "Skip it if Patrick Mahomes is ruled out or the Chiefs rest starters."
        )

    @pytest.mark.skipif(NODE is None, reason="node is not on PATH")
    def test_a_sentence_opening_word_alone_is_not_a_name(self):
        parts = _split("Weather turns. Then Dallas loses its kicker.")
        assert [p["name"] for p in parts if p["name"]] == ["Dallas"]
        parts = _split("Weather turns. Rain is coming.")
        assert [p["name"] for p in parts if p["name"]] == []

    @pytest.mark.skipif(NODE is None, reason="node is not on PATH")
    def test_the_stoplist_is_load_bearing(self, tmp_path):
        mutated = NAMES.read_text(encoding="utf-8").replace(
            "const NOT_A_NAME = new Set([", "const NOT_A_NAME = new Set<string>([ /*"
        ).replace('"Over", "Under",\n]);', '"Over", "Under",*/\n]);')
        assert mutated != NAMES.read_text(encoding="utf-8")
        parts = _split("Skip if The Chiefs lose.", source=mutated, tmp_path=tmp_path)
        assert "The Chiefs" in [p["name"] for p in parts]
        parts = _split("Skip if The Chiefs lose.")
        assert [p["name"] for p in parts if p["name"]] == ["Chiefs"]


class TestGetAPriceBuildsOnly:
    def test_the_button_is_get_a_price(self):
        src = _code(COMPONENT)
        assert '"Get a price"' in src
        assert '"Ask the market"' not in src

    def test_building_never_fires_the_rfq(self):
        src = _code(COMPONENT)
        # The card imports no RFQ call; the RFQ is `<AskTheMarket>`'s own
        # button, drawn only after a combination is minted.
        assert not re.search(r"\b(askForQuotes|requestRfq|createRfq|rfq)\b", src, re.I)
        ask = src[src.index("const ask = async"): src.index("if (card.status")]
        assert "AskTheMarket" not in ask and "accept" not in ask.lower()
        assert src.count("<AskTheMarket") == 1


class TestThenAndNowHasNoArrowOrColour:
    def test_then_and_now_are_two_stamped_facts(self):
        src = _code(COMPONENT)
        assert "leg.at_build" in src
        assert "{then.ask_display} when written" in src
        assert "ask {leg.ask_display} now" in src
        assert re.search(r"read \{formatClock\(", src)

    def test_then_and_now_has_no_arrow_or_colour(self):
        src = _code(COMPONENT)
        start = src.index("function ThenNow")
        block = src[start: src.index("\n}\n", start)]
        for glyph in ("↑", "↓", "→", "▲", "▼", "&uarr;",
                      "&darr;", "&rarr;", "↗", "↘"):
            assert glyph not in block, glyph
        assert not re.search(
            r"text-(accent|accent-2|go|red|green|amber)|bg-|border-(accent|go)",
            block,
        ), "then-and-now must not be coloured"
        assert not re.search(r"\b(up|down|rose|fell|moved|move|steam)\b", block, re.I)
        assert "line" not in block.lower().replace("inline", "")

    def test_depth_is_behind_a_tap(self):
        src = _code(COMPONENT)
        start = src.index("function ThenNow")
        block = src[start: src.index("\n}\n", start)]
        assert "<details" in block and "<summary" in block
        assert "depth" in block.lower()
        assert block.index("<details") < block.lower().index("depth")


class TestServerServesTheStamps:
    def test_each_leg_carries_at_build_and_read_ms(self, tmp_path, monkeypatch):
        from backend.store import db
        from tests.test_game_script_card_screen import (
            LEGS, NOW, HOUR, _app, _built,
        )

        monkeypatch.setattr(db, "now_ms", lambda: NOW)
        http, conn = _app(tmp_path)
        legs = [
            {**LEGS[0], "at_build": {"ask_tenths": 530, "size": 12.0, "read_ms": NOW - 5000}},
            {**LEGS[1], "at_build": {"ask_tenths": None, "size": None, "read_ms": None}},
        ]
        _built(conn, "KXNFLGAME-26SEP13ATLPIT", NOW + 5 * HOUR, legs=legs)
        out = http.get("/api/game-cards").json()["cards"][0]["legs"]
        assert out[0]["read_ms"] == NOW
        assert out[0]["at_build"]["ask_display"] == "53c"
        assert out[0]["at_build"]["read_ms"] == NOW - 5000
        assert out[1]["at_build"]["ask_display"] is None
        assert out[1]["at_build"]["ask_tenths"] is None
        # Depth now is the size at the ask the server just read.
        assert out[0]["size_now"] == 10.0
