"""The game-script card on screen (#216, ADR 0190, ADR 0189, ADR 0071).

- **Kickoff order and no other.** `GET /api/game-cards` returns cards by
  `kickoff_ms`; the component never re-sorts.
- **A skipped or refused game is listed with its reason**, never dropped and
  never an empty list; the component renders `no_card_line`.
- **No combined chance is read or drawn** by the card component (extends
  `tests/test_game_page_copy.py` to `GameScriptCard.tsx`).
- **Each leg carries Kalshi's own single-leg ask**, read at render time; an
  unreadable book is `None` with a reason, never 0.
- **Minting the card's exact legs stamps `combo_ticker` on the card row.**

The frontend claims are source assertions (this repo has no JS test runner),
the pattern of `tests/test_game_page_copy.py`.

What this does not establish: that the page renders at phone width, or that a
real Kalshi book reads as a stub does.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import game_builder
from backend.api.routers import game as game_router
from backend.store import db, game_script_cards

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend" / "src"
COMPONENT = SRC / "components" / "GameScriptCard.tsx"

NOW = 1_790_400_000_000
HOUR = 3_600_000
FORBIDDEN = re.compile(
    r"joint|conservative|fair_cost|hold_display|chance_every|as if independent"
    r"|\+EV|(?<![.\w])value(?!\w)",
    re.IGNORECASE,
)


def _strip_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", source, flags=re.MULTILINE)


LEGS = [
    {"market_ticker": "KXNFLTOTAL-26SEP13ATLPIT-40",
     "event_ticker": "KXNFLTOTAL-26SEP13ATLPIT", "side": "yes"},
    {"market_ticker": "KXNFLGAME-26SEP13ATLPIT-ATL",
     "event_ticker": "KXNFLGAME-26SEP13ATLPIT", "side": "no"},
]


class StubApi:
    """Two books: one with both sides, one with a YES bid only."""

    def __init__(self):
        self.books = {
            "KXNFLTOTAL-26SEP13ATLPIT-40": {
                "yes_dollars": [["0.4000", "10"]],
                "no_dollars": [["0.5700", "10"]],
            },
            "KXNFLGAME-26SEP13ATLPIT-ATL": {
                "yes_dollars": [["0.6200", "10"]],
                "no_dollars": [],
            },
        }

    async def markets_for_event(self, event_ticker):
        if event_ticker.startswith("KXNFLTOTAL"):
            return [{"ticker": "KXNFLTOTAL-26SEP13ATLPIT-40",
                     "title": "Over 40.5 points",
                     "yes_sub_title": "Over", "no_sub_title": "Under"}]
        return [{"ticker": "KXNFLGAME-26SEP13ATLPIT-ATL",
                 "title": "Atlanta at Pittsburgh",
                 "yes_sub_title": "Atlanta", "no_sub_title": "Pittsburgh"}]

    async def orderbook(self, ticker, depth=10):
        return self.books[ticker]


def _app(tmp_path, *, api=None):
    db_path = tmp_path / "cards.db"
    db.init_db(db_path).close()
    conn = db.open_db(db_path, cross_thread=True)
    app = FastAPI()
    game_router.register(
        app,
        app_config=SimpleNamespace(db_path=db_path),
        staleness=SimpleNamespace(max_odds_age_s=600),
        combo_api=lambda: api if api is not None else StubApi(),
        get_conn=lambda: conn,
        require_auth=lambda: None,
    )
    return TestClient(app), conn


def _built(conn, game, kickoff, legs=LEGS):
    return game_script_cards.insert_card(
        conn, game_event_ticker=game, sport_key="nfl", kickoff_ms=kickoff,
        built_ms=NOW, status="built", story="A slow game.", legs=legs,
        drop_if="A starter is ruled out.",
    )


def _refused(conn, game, kickoff, status, reason):
    return game_script_cards.insert_card(
        conn, game_event_ticker=game, sport_key="nfl", kickoff_ms=kickoff,
        built_ms=NOW, status=status, reason=reason,
    )


@pytest.fixture(autouse=True)
def _clock(monkeypatch):
    monkeypatch.setattr(db, "now_ms", lambda: NOW)


class TestKickoffOrderAndNoOther:
    def test_cards_come_back_in_kickoff_order_not_insert_order(self, tmp_path):
        http, conn = _app(tmp_path)
        # Inserted latest-kickoff first, and with tickers that sort the
        # opposite way round, so neither insert order nor alphabet passes.
        _built(conn, "KXNFLGAME-26SEP13AAAAAA", NOW + 30 * HOUR)
        _refused(conn, "KXNFLGAME-26SEP13MMMMMM", NOW + 5 * HOUR,
                 "skipped", "no clean story")
        _built(conn, "KXNFLGAME-26SEP13ZZZZZZ", NOW + 12 * HOUR)
        cards = http.get("/api/game-cards").json()["cards"]
        assert [c["kickoff_ms"] for c in cards] == [
            NOW + 5 * HOUR, NOW + 12 * HOUR, NOW + 30 * HOUR,
        ]
        assert [c["game_event_ticker"][-6:] for c in cards] == [
            "MMMMMM", "ZZZZZZ", "AAAAAA",
        ]

    def test_a_built_card_never_outranks_an_earlier_kickoff(self, tmp_path):
        http, conn = _app(tmp_path)
        _refused(conn, "KXNFLGAME-26SEP13EARLYA", NOW + 2 * HOUR,
                 "refused_budget", "the daily token ceiling")
        _built(conn, "KXNFLGAME-26SEP13LATERB", NOW + 9 * HOUR)
        cards = http.get("/api/game-cards").json()["cards"]
        assert [c["status"] for c in cards] == ["refused_budget", "built"]

    def test_kickoff_order_is_a_function_of_nothing_but_the_clock(self):
        cards = [
            {"kickoff_ms": 3, "game_event_ticker": "A", "story": "z" * 9},
            {"kickoff_ms": 1, "game_event_ticker": "Z", "story": "a"},
            {"kickoff_ms": 2, "game_event_ticker": "M", "story": "m" * 3},
        ]
        assert [c["kickoff_ms"] for c in game_router.kickoff_order(cards)] == [1, 2, 3]

    def test_a_game_that_has_kicked_off_is_not_listed(self, tmp_path):
        http, conn = _app(tmp_path)
        _built(conn, "KXNFLGAME-26SEP13PASTAA", NOW - HOUR)
        assert http.get("/api/game-cards").json()["cards"] == []

    def test_the_component_never_sorts_what_it_was_given(self):
        source = _strip_comments(COMPONENT.read_text(encoding="utf-8"))
        assert ".sort(" not in source and ".toSorted(" not in source
        assert ".reverse(" not in source


class TestSkippedAndRefusedGamesAreListedWithTheirReason:
    @pytest.mark.parametrize(
        "status, reason, expected",
        [
            ("refused_budget", "the daily token ceiling",
             "No card today: the daily token ceiling"),
            ("skipped", "the game has no story",
             "No clean story: the game has no story"),
            ("refused_invalid", "the card has 4 legs",
             "No clean story: the card has 4 legs"),
        ],
    )
    def test_each_one_is_listed_with_its_reason_and_no_legs(
        self, tmp_path, status, reason, expected
    ):
        http, conn = _app(tmp_path)
        _refused(conn, "KXNFLGAME-26SEP13ATLPIT", NOW + HOUR, status, reason)
        body = http.get("/api/game-cards").json()
        assert len(body["cards"]) == 1, "a refused game is never an empty list"
        card = body["cards"][0]
        assert card["no_card_line"] == expected
        assert card["legs"] == []

    def test_a_list_of_only_skipped_games_is_not_empty(self, tmp_path):
        http, conn = _app(tmp_path)
        _refused(conn, "KXNFLGAME-26SEP13AAAAAA", NOW + HOUR, "skipped", "x")
        _refused(conn, "KXNFLGAME-26SEP13BBBBBB", NOW + 2 * HOUR,
                 "refused_budget", "y")
        cards = http.get("/api/game-cards").json()["cards"]
        assert len(cards) == 2 and all(c["no_card_line"] for c in cards)

    def test_a_built_card_has_no_no_card_line(self, tmp_path):
        http, conn = _app(tmp_path)
        _built(conn, "KXNFLGAME-26SEP13ATLPIT", NOW + HOUR)
        assert http.get("/api/game-cards").json()["cards"][0]["no_card_line"] is None

    def test_the_component_renders_the_reason_and_the_empty_message_is_separate(self):
        source = _strip_comments(COMPONENT.read_text(encoding="utf-8"))
        assert "{card.no_card_line" in source
        assert 'card.status !== "built"' in source
        # The "nothing stored" sentence fires only on a genuinely empty list.
        assert "data.cards.length === 0" in source
        assert "data.cards.map(" in source


class TestEachLegCarriesKalshisOwnSingleLegAsk:
    def test_the_ask_is_read_from_the_side_the_card_names(self, tmp_path):
        http, conn = _app(tmp_path)
        _built(conn, "KXNFLGAME-26SEP13ATLPIT", NOW + HOUR)
        legs = {
            (l["market_ticker"], l["side"]): l
            for l in http.get("/api/game-cards").json()["cards"][0]["legs"]
        }
        yes_leg = legs[("KXNFLTOTAL-26SEP13ATLPIT-40", "yes")]
        # YES ask = 100c - best NO bid (57c) = 43c: derived, never quoted.
        assert yes_leg["ask_tenths"] == 430 and yes_leg["ask_display"] == "43c"
        assert yes_leg["title"] == "Over 40.5 points"
        no_leg = legs[("KXNFLGAME-26SEP13ATLPIT-ATL", "no")]
        # NO ask = 100c - best YES bid (62c) = 38c.
        assert no_leg["ask_tenths"] == 380

    def test_an_empty_side_is_none_with_a_reason_never_zero(self, tmp_path):
        api = StubApi()
        api.books["KXNFLTOTAL-26SEP13ATLPIT-40"]["no_dollars"] = []
        http, conn = _app(tmp_path, api=api)
        _built(conn, "KXNFLGAME-26SEP13ATLPIT", NOW + HOUR)
        leg = next(
            l for l in http.get("/api/game-cards").json()["cards"][0]["legs"]
            if l["side"] == "yes"
        )
        assert leg["ask_tenths"] is None and leg["ask_display"] is None
        assert "Nobody is offering" in leg["ask_unread_reason"]

    def test_an_unreadable_book_leaves_the_card_up(self, tmp_path):
        api = StubApi()

        async def boom(ticker, depth=10):
            raise RuntimeError("venue down")

        api.orderbook = boom
        http, conn = _app(tmp_path, api=api)
        _built(conn, "KXNFLGAME-26SEP13ATLPIT", NOW + HOUR)
        legs = http.get("/api/game-cards").json()["cards"][0]["legs"]
        assert len(legs) == 2
        assert all(l["ask_tenths"] is None and l["ask_unread_reason"] for l in legs)

    def test_the_payload_carries_no_combined_figure(self, tmp_path):
        http, conn = _app(tmp_path)
        _built(conn, "KXNFLGAME-26SEP13ATLPIT", NOW + HOUR)
        text = http.get("/api/game-cards").text.lower()
        for word in ("joint", "combined", "independent", "probability", "edge"):
            assert word not in text

    def test_one_game_can_be_asked_for_by_ticker(self, tmp_path):
        http, conn = _app(tmp_path)
        _built(conn, "KXNFLGAME-26SEP13ATLPIT", NOW + HOUR)
        _built(conn, "KXNFLGAME-26SEP13OTHERS", NOW + 2 * HOUR)
        cards = http.get(
            "/api/game-cards", params={"game_event_ticker": "kxnflgame-26sep13atlpit"}
        ).json()["cards"]
        assert [c["game_event_ticker"] for c in cards] == ["KXNFLGAME-26SEP13ATLPIT"]
        assert http.get(
            "/api/game-cards", params={"game_event_ticker": "KXNFLGAME-26SEP13NONEXX"}
        ).json()["cards"] == []


class TestTheHeadingNamesTheGame:
    def test_a_card_carries_the_events_own_title(self, tmp_path):
        http, conn = _app(tmp_path)
        _built(conn, "KXNFLGAME-26SEP13ATLPIT", NOW + HOUR)
        _built(conn, "KXNFLGAME-26SEP13OTHERS", NOW + 2 * HOUR)
        conn.execute(
            "INSERT OR REPLACE INTO kalshi_events (event_ticker, title, "
            "first_seen_ms, last_seen_ms) VALUES (?, ?, 0, 0)",
            ("KXNFLGAME-26SEP13ATLPIT", "ATL Falcons vs PIT Steelers"),
        )
        conn.commit()
        cards = http.get("/api/game-cards").json()["cards"]
        assert [c["game_title"] for c in cards] == ["ATL Falcons vs PIT Steelers", None]

    def test_the_heading_prefers_the_title_over_the_ticker(self):
        src = Path("frontend/src/components/GameScriptCard.tsx").read_text(encoding="utf-8")
        assert "card.game_title ?? fixtureOf(card.game_event_ticker)" in src


class TestTheCardComponentClaimsNoCombinedChance:
    def test_the_component_names_no_joint_or_combined_field_or_value_copy(self):
        source = COMPONENT.read_text(encoding="utf-8")
        # Comments are allowed to say what is forbidden; code and copy are not.
        code = _strip_comments(source)
        hits = FORBIDDEN.findall(code)
        assert not hits, f"GameScriptCard.tsx mentions {sorted(set(hits))}"

    def test_it_says_the_desk_shows_no_combined_chance_and_renders_it(self):
        source = COMPONENT.read_text(encoding="utf-8")
        assert "shows no combined chance" in source
        assert "The makers' quote prices that in." in source
        assert "{NO_COMBINED_CHANCE_LINE}" in _strip_comments(source)

    def test_the_card_types_carry_no_combined_field(self):
        api = (SRC / "lib" / "types" / "parlays.ts").read_text(encoding="utf-8")
        blocks = re.findall(
            r"export type GameScript\w+ = \{.*?^\};", api,
            flags=re.DOTALL | re.MULTILINE,
        )
        assert blocks, "GameScript* types not found in lib/types/parlays.ts"
        assert not FORBIDDEN.findall(_strip_comments("\n".join(blocks)))

    def test_the_card_says_inactives_are_not_covered_and_shows_drop_if(self):
        source = _strip_comments(COMPONENT.read_text(encoding="utf-8"))
        assert "come out 90 minutes before" in source
        assert "kickoff and are not covered." in source
        assert "{card.drop_if}" in source

    def test_new_terms_go_through_term_and_the_glossary(self):
        source = COMPONENT.read_text(encoding="utf-8")
        glossary = (SRC / "lib" / "glossary.ts").read_text(encoding="utf-8")
        for key in ("game_script_card", "drop_if", "inactives"):
            assert f'k="{key}"' in source
            assert re.search(rf"^  {key}: \{{", glossary, flags=re.MULTILINE)

    def test_ask_the_market_goes_through_mint_and_ask_the_market(self):
        source = _strip_comments(COMPONENT.read_text(encoding="utf-8"))
        assert "mintGameCombo(" in source and "<AskTheMarket" in source
        assert "Ask the market" in source

    def test_build_card_never_retries(self):
        source = _strip_comments(COMPONENT.read_text(encoding="utf-8"))
        assert source.count("buildGameCard(") == 1
        assert "setInterval" not in source and "while (" not in source

    def test_the_pages_mount_the_card(self):
        game = (SRC / "app" / "game" / "[event]" / "page.tsx").read_text(encoding="utf-8")
        parlays = (SRC / "app" / "parlays" / "page.tsx").read_text(encoding="utf-8")
        assert "<GameCardPanel" in game
        assert "<GameScriptParlays" in parlays



class TestMintStampsTheCardsComboTicker:
    def test_exact_legs_stamp_the_newest_built_card(self, tmp_path):
        conn = db.init_db(tmp_path / "stamp.db")
        game = "KXNFLGAME-26SEP13ATLPIT"
        old = _built(conn, game, NOW + HOUR)
        card_id = game_builder.attach_combo_to_card(
            conn, game_event_ticker=game,
            legs=[(l["market_ticker"], l["side"]) for l in LEGS],
            minted="KXMVE-TEST",
        )
        assert card_id == old
        assert game_script_cards.card_by_id(conn, old)["combo_ticker"] == "KXMVE-TEST"

    def test_a_different_leg_set_stamps_nothing(self, tmp_path):
        conn = db.init_db(tmp_path / "stamp2.db")
        game = "KXNFLGAME-26SEP13ATLPIT"
        cid = _built(conn, game, NOW + HOUR)
        assert game_builder.attach_combo_to_card(
            conn, game_event_ticker=game,
            legs=[(LEGS[0]["market_ticker"], "no"), (LEGS[1]["market_ticker"], "no")],
            minted="KXMVE-OTHER",
        ) is None
        assert game_script_cards.card_by_id(conn, cid)["combo_ticker"] is None

    def test_a_newer_skipped_row_does_not_hide_the_built_card(self, tmp_path):
        conn = db.init_db(tmp_path / "stamp4.db")
        game = "KXNFLGAME-26SEP13ATLPIT"
        built = _built(conn, game, NOW + HOUR)
        conn.execute(
            "INSERT INTO game_script_cards (game_event_ticker, sport_key, "
            "kickoff_ms, built_ms, status, reason) VALUES (?, 'nfl', ?, ?, "
            "'refused_budget', 'later refusal')",
            (game, NOW + HOUR, NOW + 1),
        )
        conn.commit()
        assert game_builder.attach_combo_to_card(
            conn, game_event_ticker=game,
            legs=[(l["market_ticker"], l["side"]) for l in LEGS], minted="KXMVE-T",
        ) == built

    def test_a_skipped_card_is_never_stamped(self, tmp_path):
        conn = db.init_db(tmp_path / "stamp3.db")
        game = "KXNFLGAME-26SEP13ATLPIT"
        _refused(conn, game, NOW + HOUR, "skipped", "nothing")
        assert game_builder.attach_combo_to_card(
            conn, game_event_ticker=game, legs=[("A", "yes")], minted="X"
        ) is None

    def test_the_mint_calls_the_write_back(self):
        import inspect

        source = inspect.getsource(game_builder.mint_game_combo)
        assert "attach_combo_to_card(" in source
