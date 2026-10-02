"""The T-2h drop-if re-check (#289, Joe's (A) to #270).

- **Only a game Joe opened is re-checked**, inside two hours of kickoff, once.
- **"Not found" is never a confirmation, and "triggered" needs a page**: a
  `triggered` answer with no web-address source is stored as `unknown`.
- **The output carries no number about the bet**: the schema is walked.
- **The unattended share binds** as it does for card builds.

No Anthropic call is made: the client is a stub.

What this does not establish: that one search finds late news, or what a
re-check really costs (the 40K reservation is the town hall's estimate).
"""

from __future__ import annotations

import pytest

from backend.agents.base import AgentConfig
from backend.agents.budget import AgentBudget
from backend.agents.game_script import (
    CardSource,
    RecheckOutput,
    recheck_card,
    settle_recheck,
)
from backend.game_script_watch import (
    RECHECK_LEAD_MS,
    RECHECK_TOKEN_ESTIMATE,
    WatchBudget,
    decide_rechecks,
    load_recheck_inputs,
)
from backend.store import db, game_script_cards

CONFIG = AgentConfig(api_key="test", model="claude-sonnet-5")
NOW = 1_790_400_000_000
GAME = "KXNHLGAME-26OCT02WSHCAR"
OTHER = "KXNHLGAME-26OCT02BOSWPG"
ROOMY = WatchBudget(tokens_today=0, tokens_ceiling=0, searches_today=0, searches_ceiling=0)


def _card(ticker=GAME, kickoff=NOW + 90 * 60_000, **kw):
    return {
        "id": 1, "game_event_ticker": ticker, "kickoff_ms": kickoff,
        "status": "built", "recheck_ms": None, "drop_if": "Goalie X is scratched.", **kw,
    }


class TestOnlyOpenedGamesAreRechecked:
    def test_a_card_for_a_game_joe_did_not_open_is_never_rechecked(self):
        assert decide_rechecks(NOW, [_card()], opened=[OTHER], budget=ROOMY) == []

    def test_an_opened_game_inside_two_hours_is_rechecked(self):
        assert [c["game_event_ticker"] for c in decide_rechecks(
            NOW, [_card()], opened=[GAME.lower()], budget=ROOMY
        )] == [GAME]

    @pytest.mark.parametrize("card", [
        _card(kickoff=NOW + RECHECK_LEAD_MS + 1),
        _card(kickoff=NOW),
        _card(recheck_ms=NOW - 1),
        _card(status="skipped"),
    ], ids=["too_early", "already_started", "already_rechecked", "not_built"])
    def test_outside_the_window_or_done_is_not_rechecked(self, card):
        assert decide_rechecks(NOW, [card], opened=[GAME], budget=ROOMY) == []

    def test_the_unattended_share_binds(self):
        tight = WatchBudget(
            tokens_today=0, tokens_ceiling=2 * RECHECK_TOKEN_ESTIMATE + 1,
            searches_today=0, searches_ceiling=0, tap_token_share=0.5,
        )
        cards = [_card(), _card(ticker=OTHER, id=2)]
        assert len(decide_rechecks(NOW, cards, [GAME, OTHER], tight)) == 1

    def test_opened_is_read_from_the_desks_heartbeat_and_minted_cards(self, tmp_path):
        conn = db.init_db(tmp_path / "r.db")
        for ticker in (GAME, OTHER):
            game_script_cards.insert_card(
                conn, game_event_ticker=ticker, sport_key="nhl",
                kickoff_ms=NOW + 60 * 60_000, built_ms=NOW - 1, status="built",
                story="s", legs=[{"market_ticker": "m", "event_ticker": "e", "side": "yes"}],
                drop_if="d",
            )
        conn.execute(
            "INSERT INTO desk_attention (seen_ms, path) VALUES (?, ?)",
            (NOW - 60_000, f"/game/{GAME}"),
        )
        conn.commit()
        cards, opened = load_recheck_inputs(conn, NOW)
        assert {c["game_event_ticker"] for c in cards} == {GAME, OTHER}
        assert opened == {GAME}


class _Usage:
    input_tokens = 500
    output_tokens = 50
    cache_creation_input_tokens = 0
    cache_read_input_tokens = 0

    class server_tool_use:  # noqa: N801
        web_search_requests = 1


class _Client:
    def __init__(self, parsed):
        self.calls = []
        parent = self

        class _Messages:
            async def parse(self, **kw):
                parent.calls.append(kw)
                return type("R", (), {"parsed_output": parsed, "stop_reason": "end_turn",
                                      "usage": _Usage()})()

        self.messages = _Messages()


def _stored_card(conn):
    card_id = game_script_cards.insert_card(
        conn, game_event_ticker=GAME, sport_key="nhl", kickoff_ms=NOW + 3_600_000,
        built_ms=NOW - 1, status="built", story="s",
        legs=[{"market_ticker": "m", "event_ticker": "e", "side": "yes"}], drop_if="d",
    )
    return game_script_cards.card_by_id(conn, card_id)


def _budget(conn, daily=24):
    return AgentBudget(conn, per_pass_budget=8, daily_budget=daily,
                       searches_daily_budget=0, tokens_daily_budget=0)


class TestWhatIsStored:
    def test_triggered_without_a_page_is_unknown(self):
        assert settle_recheck(RecheckOutput(status="triggered", note="He is out."))[0] == "unknown"
        assert settle_recheck(RecheckOutput(
            status="triggered", source=CardSource(url="ESPN")
        ))[0] == "unknown"

    def test_nothing_back_is_unknown_never_not_found(self):
        assert settle_recheck(None)[0] == "unknown"

    async def test_a_triggered_recheck_is_stored_once_with_its_source(self, tmp_path):
        conn = db.init_db(tmp_path / "r.db")
        card = _stored_card(conn)
        src = CardSource(url="https://example.com/scratch", published="2026-10-02")
        client = _Client(RecheckOutput(status="triggered", note="Scratched.", source=src))
        status = await recheck_card(conn, client, CONFIG, _budget(conn), card=card,
                                    game_title=GAME, kickoff_iso="x", now_ms=NOW)
        assert status == "triggered" and len(client.calls) == 1
        row = game_script_cards.card_by_id(conn, card["id"])
        assert row["recheck_status"] == "triggered"
        assert row["recheck_source"] == src.model_dump()
        game_script_cards.record_recheck(conn, card["id"], recheck_ms=NOW + 1, status="not_found")
        assert game_script_cards.card_by_id(conn, card["id"])["recheck_status"] == "triggered"

    async def test_a_budget_refusal_spends_nothing_and_is_stamped(self, tmp_path):
        conn = db.init_db(tmp_path / "r.db")
        card = _stored_card(conn)
        client = _Client(RecheckOutput(status="not_found"))
        status = await recheck_card(conn, client, CONFIG, _budget(conn, daily=-1), card=card,
                                    game_title=GAME, kickoff_iso="x", now_ms=NOW)
        assert status == "refused_budget" and client.calls == []


class TestTheOutputCarriesNoNumberAboutTheBet:
    FORBIDDEN = ("prob", "confid", "edge", "odds", "price", "chance", "score")

    def test_no_numeric_type_and_no_forbidden_field_name(self):
        schema = RecheckOutput.model_json_schema()
        text = str(schema).lower()
        assert "'number'" not in text and "'integer'" not in text
        for name in RecheckOutput.model_fields:
            assert not any(name.startswith(f) for f in self.FORBIDDEN)
