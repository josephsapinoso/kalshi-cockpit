"""Each game-script card leg shows the books' chance beside the ask (#312).

What these tests establish
--------------------------
- `/api/game-cards` serves each built leg `books_chance` from the game page's
  own lookup (`consensus_for_legs` -> `_price_sides`): a leg with a fresh
  `fair_prices` row gets that chance, a leg with none gets `null` and a reason.
- Card order is unchanged when the chances differ (kickoff order only).
- The scout never sees a chance and the stored row never holds one.
- The component draws it through `<Term k="consensus_chance">` as plain text,
  and never sorts, filters or colours by it.

What this does not establish: that the label fits at phone width, or that a
real fixture's consensus is right (`tests/test_game_builder.py` owns the lookup).
"""

# ruff: noqa: F811
from __future__ import annotations

import json
import re
from pathlib import Path

from backend.agents import game_script
from backend.store.db import now_ms
from tests.test_game_builder import _fresh_caches, seed_moneyline  # noqa: F401
from tests.test_game_script_card_screen import (
    COMPONENT,
    HOUR,
    LEGS,
    _app,
    _built,
    _strip_comments,
)

REPO = Path(__file__).resolve().parents[1]
ATL_GAME = "KXNFLGAME-26SEP13ATLPIT"
# LEGS[0] is a total with no consensus seeded; LEGS[1] is ATL, side "no".
ATL_YES = {"market_ticker": "KXNFLGAME-26SEP13ATLPIT-ATL",
           "event_ticker": ATL_GAME, "side": "yes"}


def _seeded(tmp_path, atl_p=0.6):
    http, conn = _app(tmp_path)
    seed_moneyline(conn, atl_p=atl_p, computed_ms=now_ms())
    return http, conn


class TestServedChance:
    def test_a_leg_with_a_fresh_consensus_gets_it_and_one_without_gets_a_reason(
        self, tmp_path
    ):
        http, conn = _seeded(tmp_path)
        _built(conn, ATL_GAME, now_ms() + 5 * HOUR, legs=[ATL_YES, LEGS[0]])
        legs = http.get("/api/game-cards").json()["cards"][0]["legs"]
        assert legs[0]["books_chance"] == 0.6
        assert legs[0]["books_chance_display"] == "60%"
        assert legs[0]["books_chance_reason"] is None
        assert legs[1]["books_chance"] is None
        assert legs[1]["books_chance_display"] is None
        assert legs[1]["books_chance_reason"]  # worded, never blank

    def test_it_is_the_game_pages_own_lookup(self):
        src = (REPO / "backend" / "api" / "routers" / "game.py").read_text("utf-8")
        assert "consensus_for_legs(" in src
        builder = (REPO / "backend" / "game_builder.py").read_text("utf-8")
        body = builder[builder.index("def consensus_for_legs"):]
        body = body[: body.index("\ndef ")]
        assert "_price_sides(" in body

    def test_card_order_is_unchanged_when_the_chances_differ(self, tmp_path):
        http, conn = _seeded(tmp_path)
        # Early kickoff has NO consensus; the late one has the best chance.
        # A chance-ranked list would put the late game first.
        _built(conn, "KXNFLGAME-26SEP13BALIND", now_ms() + 3 * HOUR, legs=[LEGS[0]])
        _built(conn, ATL_GAME, now_ms() + 9 * HOUR, legs=[ATL_YES])
        cards = http.get("/api/game-cards").json()["cards"]
        assert [c["game_event_ticker"] for c in cards] == [
            "KXNFLGAME-26SEP13BALIND", ATL_GAME,
        ]
        assert cards[0]["legs"][0]["books_chance"] is None
        assert cards[1]["legs"][0]["books_chance"] == 0.6


class TestTheModelNeverSeesIt:
    def test_the_prompt_text_carries_no_chance(self):
        leg = {
            "market_ticker": "KXNFLGAME-26SEP13ATLPIT-ATL",
            "event_ticker": ATL_GAME, "title": "Atlanta", "yes_label": "Atlanta",
            "no_label": "Pittsburgh", "player": None, "strike": None,
            "allowed_sides": ["yes", "no"], "one_per_event": False,
            "sides": {"yes": {"chance": 0.6173, "chance_display": "61.7%"}},
            "books_chance": 0.6173, "books_chance_display": "61.7%",
        }
        listing = {"groups": [{"label": "Moneyline", "series": "KXNFLGAME",
                               "legs": [leg]}]}
        text = game_script.build_prompt(
            game_title="Atlanta vs Pittsburgh", sport_key="nfl",
            kickoff_iso="2026-09-13T17:00:00Z", listing=listing,
        )
        assert "0.6173" not in text and "61.7" not in text
        assert "books_chance" not in text and "chance" not in text.split("\n", 1)[1]
        assert not any("chance" in f for f in game_script.PROMPT_LEG_FIELDS)

    def test_the_stored_row_carries_no_chance(self, tmp_path):
        http, conn = _seeded(tmp_path)
        _built(conn, ATL_GAME, now_ms() + 5 * HOUR, legs=[ATL_YES])
        served = http.get("/api/game-cards").json()["cards"][0]["legs"][0]
        assert served["books_chance"] == 0.6
        raw = conn.execute("SELECT legs_json FROM game_script_cards").fetchone()[0]
        assert "chance" not in raw
        assert all("chance" not in k for k in json.loads(raw)[0])
        cols = [r[1] for r in conn.execute("PRAGMA table_info(game_script_cards)")]
        assert not any("chance" in c for c in cols)

    def test_the_scout_module_never_names_the_field(self):
        src = (REPO / "backend" / "agents" / "game_script.py").read_text("utf-8")
        assert "books_chance" not in src and "consensus_for_legs" not in src


class TestTheComponent:
    def test_the_label_is_a_glossary_term_and_the_figure_is_plain_text(self):
        code = _strip_comments(COMPONENT.read_text("utf-8"))
        start = code.index("function BooksChance")
        block = code[start: code.index("\n}\n", start)]
        assert '<Term k="consensus_chance">books</Term>' in block
        assert "leg.books_chance_display" in block and "books_chance_reason" in block
        assert not re.search(r"text-(accent|go|red|green|amber)|bg-|[↑↓▲▼]", block)
        glossary = (REPO / "frontend" / "src" / "lib" / "glossary.ts").read_text("utf-8")
        assert "consensus_chance:" in glossary

    def test_nothing_sorts_filters_or_compares_by_it(self):
        code = _strip_comments(COMPONENT.read_text("utf-8"))
        assert not re.search(r"\.(sort|toSorted)\(", code)
        for use in re.findall(r".*books_chance\b.*", code):
            assert not re.search(r"[<>]=?(?!/)|\.(sort|filter)\(", use.replace("=>", "")), use
        assert not re.search(r"books_chance\w*\s*[-+*/]|[-+*/]\s*\w*\.books_chance", code)
