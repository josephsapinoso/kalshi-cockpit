"""Joe picks the card's size on each tap (#379, his (A) of 2026-10-12).

- A requested `leg_count` makes the card exactly that size: a card of any
  other length is `refused_invalid`, stored, one model call, never re-asked.
- No `leg_count` keeps the old 2-3 leg rule.
- A size above the game's Kalshi maximum (`listing["max_legs"]`) is refused
  before the budget or the model is touched: the fake client is never called.
- `POST /api/game/{event}/card` takes an optional `{leg_count}`: 2..8, else 422.
- The output cap grows with the size; the prompt and schema say "exactly N".

No Anthropic call is made: the client is the stub from the card tests.

What this does not establish: that a real model produces N coherent legs.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from types import SimpleNamespace

from backend.agents import game_script
from backend.agents.game_script import (
    GAME_SCRIPT_MAX_OUTPUT_TOKENS,
    build_card,
    output_cap_for,
    output_model_for,
    system_for,
    validate_card,
)
from backend.api.routers import game as game_router
from backend.store import db, game_script_cards
from tests.test_game_script_card import (
    CONFIG,
    GAME,
    KICKOFF,
    NOW,
    StubClient,
    _card,
    _conn_budget,
    _l,
    _leg,
)

TOT_EVENT = "KXNFLTOTAL-26SEP13ATLPIT"
TD_EVENT = "KXNFLTD-26SEP13ATLPIT"
ATL = _l(GAME + "-ATL", GAME)
TOT = _l(TOT_EVENT + "-40", TOT_EVENT)
TDS = [_l(f"{TD_EVENT}-{c}", TD_EVENT) for c in "ABCDEFG"]
LEGS = [ATL, TOT, *TDS]  # nine distinct, all allowed


def _listing(max_legs=None):
    return {
        "game_event_ticker": GAME,
        "game_market_ticker": GAME + "-ATL",
        "max_legs": max_legs,
        "groups": [
            {"series": "KXNFLGAME", "kind": "GAME", "label": "Who wins",
             "one_per_event": True,
             "legs": [_leg(GAME + "-ATL", GAME, "Atlanta at Pittsburgh",
                           one=True, cap=1)]},
            {"series": "KXNFLTOTAL", "kind": "TOTAL", "label": "Total",
             "one_per_event": True,
             "legs": [_leg(TOT_EVENT + "-40", TOT_EVENT, "Over 40.5 points",
                           one=True, cap=1)]},
            {"series": "KXNFLTD", "kind": "TD", "label": "Anytime touchdown",
             "one_per_event": False,
             "legs": [_leg(f"{TD_EVENT}-{c}", TD_EVENT, f"Player {c} scores",
                           sides=("yes",)) for c in "ABCDEFG"]},
        ],
    }


async def _run(tmp_path, n_legs, leg_count, *, max_legs=None):
    conn, budget = _conn_budget(tmp_path)
    client = StubClient(_card(*LEGS[:n_legs]))
    result = await build_card(
        conn, client, CONFIG, budget,
        game_event_ticker=GAME, sport_key="nfl", kickoff_ms=KICKOFF,
        game_title="Atlanta at Pittsburgh", kickoff_iso="2026-09-13T17:00Z",
        listing=_listing(max_legs), now_ms=NOW, leg_count=leg_count,
    )
    return conn, client, result


class TestExactSizeValidation:
    @pytest.mark.parametrize("n", [3, 5, 8])
    def test_a_card_of_exactly_n_passes(self, n):
        assert validate_card(_card(*LEGS[:n]), _listing(), leg_count=n) is None

    @pytest.mark.parametrize("n", [3, 5, 8])
    @pytest.mark.parametrize("delta", [-1, 1])
    def test_a_card_one_off_is_refused(self, n, delta):
        reason = validate_card(_card(*LEGS[: n + delta]), _listing(), leg_count=n)
        assert reason is not None and f"exactly {n}" in reason

    def test_without_leg_count_two_and_three_pass_and_four_does_not(self):
        listing = _listing()
        assert validate_card(_card(*LEGS[:2]), listing) is None
        assert validate_card(_card(*LEGS[:3]), listing) is None
        assert validate_card(_card(*LEGS[:4]), listing) is not None
        assert validate_card(_card(*LEGS[:1]), listing) is not None

    async def test_a_wrong_size_card_is_stored_refused_after_one_call(self, tmp_path):
        conn, client, result = await _run(tmp_path, 4, 5)
        assert result.status == "refused_invalid"
        assert len(client.messages.calls) == 1
        assert game_script_cards.card_by_id(conn, result.card_id)["status"] == "refused_invalid"

    async def test_a_right_size_card_is_built(self, tmp_path):
        _conn, client, result = await _run(tmp_path, 5, 5)
        assert result.status == "built"
        assert len(client.messages.calls) == 1


class TestAboveKalshisMaximumSpendsNothing:
    async def test_the_model_is_never_called(self, tmp_path):
        conn, client, result = await _run(tmp_path, 8, 8, max_legs=5)
        assert client.messages.calls == []
        assert result.status == "refused_invalid" and result.usage is None
        assert "at most 5" in result.reason
        assert conn.execute("SELECT COUNT(*) AS c FROM agent_calls").fetchone()["c"] == 0
        row = game_script_cards.card_by_id(conn, result.card_id)
        assert row["status"] == "refused_invalid"

    async def test_a_size_at_the_maximum_is_allowed(self, tmp_path):
        _conn, client, result = await _run(tmp_path, 5, 5, max_legs=5)
        assert result.status == "built" and len(client.messages.calls) == 1

    async def test_an_unknown_maximum_does_not_block(self, tmp_path):
        _conn, client, result = await _run(tmp_path, 8, 8, max_legs=None)
        assert result.status == "built" and len(client.messages.calls) == 1


class TestWhatTheModelIsAsked:
    async def test_prompt_system_schema_and_cap_say_exactly_n(self, tmp_path):
        _conn, client, _r = await _run(tmp_path, 5, 5)
        sent = client.messages.calls[0]
        assert "exactly 5 legs" in sent["messages"][0]["content"]
        assert sent["max_tokens"] == output_cap_for(5)
        system = sent["system"]
        text = system if isinstance(system, str) else str(system)
        assert "exactly 5 bets" in text and "Pick exactly 5 legs" in text
        assert "Pick two or three legs" not in text

    async def test_no_leg_count_sends_the_old_request(self, tmp_path):
        _conn, client, _r = await _run(tmp_path, 2, None)
        sent = client.messages.calls[0]
        assert "exactly" not in sent["messages"][0]["content"]
        assert sent["max_tokens"] == GAME_SCRIPT_MAX_OUTPUT_TOKENS
        assert game_script.SYSTEM == system_for(None)

    def test_the_schema_description_names_the_size(self):
        legs = output_model_for(8).model_json_schema()["properties"]["legs"]
        assert "Exactly 8" in legs["description"]

    def test_the_prompt_version_moved(self):
        assert game_script.PROMPT_VERSION != "5"


class TestTheOutputCapGrowsWithSize:
    def test_it_grows_and_never_falls_below_the_named_cap(self):
        assert output_cap_for(None) == GAME_SCRIPT_MAX_OUTPUT_TOKENS
        assert output_cap_for(2) == output_cap_for(3) == GAME_SCRIPT_MAX_OUTPUT_TOKENS
        assert output_cap_for(3) < output_cap_for(5) < output_cap_for(8)


class TestTheRoute:
    def _http(self, tmp_path, monkeypatch, *, max_legs=None, n_legs=5):
        db_path = tmp_path / "route.db"
        db.init_db(db_path).close()
        client = StubClient(_card(*LEGS[:n_legs]))

        async def fake_listing(conn, **kw):
            return _listing(max_legs)

        monkeypatch.setattr(game_router, "list_game_legs", fake_listing)
        monkeypatch.setattr(
            game_router, "_commence_ms_for_tickers",
            lambda conn, tickers: {t: KICKOFF for t in tickers},
        )
        monkeypatch.setattr(game_router, "build_client", lambda cfg: client)
        monkeypatch.setattr(
            game_router.AgentConfig, "from_env", classmethod(lambda cls: CONFIG)
        )
        app = FastAPI()
        game_router.register(
            app,
            app_config=SimpleNamespace(db_path=db_path),
            staleness=SimpleNamespace(max_odds_age_s=600),
            combo_api=lambda: object(),
            get_conn=lambda: None,
            require_auth=lambda: None,
        )
        return TestClient(app), client

    @pytest.mark.parametrize("bad", [1, 9, 0, -3])
    def test_out_of_range_is_422_and_spends_nothing(self, tmp_path, monkeypatch, bad):
        http, client = self._http(tmp_path, monkeypatch)
        response = http.post(f"/api/game/{GAME}/card", json={"leg_count": bad})
        assert response.status_code == 422
        assert client.messages.calls == []

    def test_five_builds_a_five_leg_card(self, tmp_path, monkeypatch):
        http, client = self._http(tmp_path, monkeypatch)
        response = http.post(f"/api/game/{GAME}/card", json={"leg_count": 5})
        assert response.status_code == 200, response.text
        card = response.json()["card"]
        assert card["status"] == "built" and len(card["legs"]) == 5
        assert client.messages.calls[0]["max_tokens"] == output_cap_for(5)

    def test_over_the_maximum_through_the_route_spends_nothing(self, tmp_path, monkeypatch):
        http, client = self._http(tmp_path, monkeypatch, max_legs=3)
        response = http.post(f"/api/game/{GAME}/card", json={"leg_count": 8})
        assert response.status_code == 200
        assert response.json()["card"]["status"] == "refused_invalid"
        assert client.messages.calls == []

    def test_no_body_keeps_the_old_behaviour(self, tmp_path, monkeypatch):
        http, client = self._http(tmp_path, monkeypatch, n_legs=2)
        response = http.post(f"/api/game/{GAME}/card")
        assert response.status_code == 200, response.text
        assert response.json()["card"]["status"] == "built"
        assert "exactly" not in client.messages.calls[0]["messages"][0]["content"]
