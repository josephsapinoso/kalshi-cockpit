"""One game holds one card per size (v68, Joe 2026-10-25).

He built an 8-leg card for a game and wanted a 3 and a 5 beside it; the size
buttons vanished and a second tap would have handed back the 8.

- `game_script_cards.leg_count` keeps the size he tapped; NULL is the
  watcher's 2-3 leg card.
- A tap for a size the game does not hold builds; a tap for a size it holds
  is reused and spends nothing.
- `/api/game-cards` serves every size's card, one game's cards together.
- Minting the older size's legs still stamps that card.
- The game page keeps the size buttons up beside a built card and disables
  only the size already built.

No Anthropic call is made: the client is the stub from the card tests.

What this does not establish: that three cards on one game fit inside the
day's token ceiling. Each is its own metered call.
"""

from __future__ import annotations

from pathlib import Path

from backend import game_builder
from backend.store import db, game_script_cards
from tests.test_game_script_card_screen import NOW as SCREEN_NOW
from tests.test_game_script_card_screen import HOUR, _app
from tests.test_game_script_leg_count import GAME, KICKOFF, LEGS, TestTheRoute

COMPONENT = (
    Path(__file__).resolve().parents[1]
    / "frontend" / "src" / "components" / "GameScriptCard.tsx"
)


def _store(conn, game, size, legs, *, kickoff=KICKOFF, built_ms=1):
    return game_script_cards.insert_card(
        conn, game_event_ticker=game, sport_key="nfl", kickoff_ms=kickoff,
        built_ms=built_ms, status="built", story="A slow game.",
        legs=[{"market_ticker": l["market_ticker"], "event_ticker": l["event_ticker"],
               "side": l["side"]} for l in legs],
        drop_if="A starter is ruled out.", leg_count=size,
    )


class TestTheStoreKeepsTheSize:
    def test_a_v67_database_gains_the_column(self, tmp_path):
        conn = db.init_db(tmp_path / "a.db")
        conn.execute("ALTER TABLE game_script_cards DROP COLUMN leg_count")
        db._set_meta(conn, "schema_version", "67")
        conn.commit()
        conn.close()
        conn = db.init_db(tmp_path / "a.db")
        columns = {r[1] for r in conn.execute("PRAGMA table_info(game_script_cards)")}
        assert "leg_count" in columns

    def test_a_size_filter_ignores_the_other_sizes(self, tmp_path):
        conn = db.init_db(tmp_path / "s.db")
        eight = _store(conn, GAME, 8, LEGS[:8])
        assert game_script_cards.latest_for_game(conn, GAME, leg_count=3) is None
        assert game_script_cards.latest_for_game(conn, GAME, leg_count=8)["id"] == eight
        assert game_script_cards.latest_for_game(conn, GAME, leg_count=None) is None
        assert game_script_cards.latest_for_game(conn, GAME)["id"] == eight

    def test_every_size_comes_back_unsized_first_then_by_size(self, tmp_path):
        conn = db.init_db(tmp_path / "p.db")
        _store(conn, GAME, 8, LEGS[:8], built_ms=1)
        _store(conn, GAME, 3, LEGS[:3], built_ms=2)
        _store(conn, GAME, None, LEGS[:2], built_ms=3)
        cards = game_script_cards.latest_per_size_for_game(conn, GAME)
        assert [c["leg_count"] for c in cards] == [None, 3, 8]

    def test_a_later_refusal_does_not_replace_that_sizes_card(self, tmp_path):
        conn = db.init_db(tmp_path / "r.db")
        built = _store(conn, GAME, 5, LEGS[:5], built_ms=1)
        game_script_cards.insert_card(
            conn, game_event_ticker=GAME, sport_key="nfl", kickoff_ms=KICKOFF,
            built_ms=2, status="refused_budget", reason="ceiling", leg_count=5,
        )
        cards = game_script_cards.latest_per_size_for_game(conn, GAME)
        assert [c["id"] for c in cards] == [built]


class TestASecondSizeIsBuilt:
    def _http(self, tmp_path, monkeypatch, **kw):
        return TestTheRoute()._http(tmp_path, monkeypatch, **kw)

    def test_a_five_beside_an_eight_is_built_not_reused(self, tmp_path, monkeypatch):
        http, client = self._http(tmp_path, monkeypatch, n_legs=5)
        conn = db.open_db(tmp_path / "route.db")
        _store(conn, GAME, 8, LEGS[:8])
        conn.close()
        response = http.post(f"/api/game/{GAME}/card", json={"leg_count": 5})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["reused"] is False
        assert body["card"]["leg_count"] == 5 and len(body["card"]["legs"]) == 5
        assert len(client.messages.calls) == 1

    def test_the_same_size_again_is_reused_and_spends_nothing(self, tmp_path, monkeypatch):
        http, client = self._http(tmp_path, monkeypatch, n_legs=5)
        conn = db.open_db(tmp_path / "route.db")
        eight = _store(conn, GAME, 8, LEGS[:8])
        conn.close()
        response = http.post(f"/api/game/{GAME}/card", json={"leg_count": 8})
        assert response.json()["reused"] is True
        assert response.json()["card"]["id"] == eight
        assert client.messages.calls == []


class TestTheListServesEverySize:
    def test_one_game_serves_its_three_and_its_eight(self, tmp_path, monkeypatch):
        monkeypatch.setattr(db, "now_ms", lambda: SCREEN_NOW)
        http, conn = _app(tmp_path)
        game = "KXNFLGAME-26SEP13ATLPIT"
        legs = [
            {"market_ticker": "KXNFLTOTAL-26SEP13ATLPIT-40",
             "event_ticker": "KXNFLTOTAL-26SEP13ATLPIT", "side": "yes"},
            {"market_ticker": "KXNFLGAME-26SEP13ATLPIT-ATL",
             "event_ticker": "KXNFLGAME-26SEP13ATLPIT", "side": "no"},
        ]
        _store(conn, game, 8, legs, kickoff=SCREEN_NOW + HOUR)
        _store(conn, game, 3, legs, kickoff=SCREEN_NOW + HOUR)
        cards = http.get(
            "/api/game-cards", params={"game_event_ticker": game}
        ).json()["cards"]
        assert [c["leg_count"] for c in cards] == [3, 8]
        everything = http.get("/api/game-cards").json()["cards"]
        assert [c["leg_count"] for c in everything if c["game_event_ticker"] == game] == [3, 8]


class TestMintFindsTheCardOfAnySize:
    def test_the_older_three_is_stamped_beside_a_newer_eight(self, tmp_path):
        conn = db.init_db(tmp_path / "m.db")
        three = _store(conn, GAME, 3, LEGS[:3], built_ms=1)
        _store(conn, GAME, 8, LEGS[:8], built_ms=2)
        assert game_builder.attach_combo_to_card(
            conn, game_event_ticker=GAME,
            legs=[(l["market_ticker"], l["side"]) for l in LEGS[:3]],
            minted="KXMVE-THREE",
        ) == three


class TestTheGamePageKeepsTheButtonsUp:
    def test_buttons_do_not_hide_behind_a_built_card(self):
        source = COMPONENT.read_text(encoding="utf-8")
        assert "canBuild" not in source
        assert "payload.cards[0]" not in source

    def test_only_a_held_size_is_disabled(self):
        source = COMPONENT.read_text(encoding="utf-8")
        assert "disabled={building || held || off !== null}" in source
        assert 'card.status === "built" || card.status === "skipped"' in source
