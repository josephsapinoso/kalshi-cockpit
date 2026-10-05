"""The game-script card seat's contract (#215, ADR 0190).

- **The model never sees a price or a chance.** Asserted on the rendered
  prompt, given a listing that carries both under several field names.
- **The output has no probability, confidence or edge field.** The schema is
  walked for numeric types and for those names.
- **The server refuses before it stores, and never re-asks.** A leg not in
  the listing, two legs from one `size_max 1` event, fewer than two or more
  than three legs, a side the leg does not allow: each is a `refused_invalid`
  row with a reason and exactly one model call.
- **Every outcome is a row**: `built`, `skipped`, `refused_budget`.

No Anthropic call is made: the client is the stub the leg-verdict tests use.

What this does not establish: that a real model obeys the prompt or writes a
good card. The schema and the server-side validation are the enforcement.
"""

from __future__ import annotations

import datetime
import json
import sqlite3
import typing
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel as PydanticBase

from backend.agents import game_script
from backend.agents.base import AgentConfig
from backend.agents.budget import AgentBudget
from backend.agents.game_script import (
    GAME_SCRIPT_MAX_SEARCHES,
    CardLeg,
    CardOutput,
    CardSource,
    build_card,
    build_prompt,
    validate_card,
)
from backend.api.routers import game as game_router
from backend.store import db, game_script_cards

CONFIG = AgentConfig(api_key="test", model="claude-sonnet-5")
NOW = 1_790_400_000_000
KICKOFF = NOW + 20 * 3_600_000
GAME = "KXNFLGAME-26SEP13ATLPIT"

# Sentinels that would be visible in the prompt if a price or chance leaked.
PRICE_SENTINELS = ("0.6183", "61.8%", "43.7c", "ASKSENTINEL", "no book", "chance")


def _leg(market, event, title, *, sides=("yes", "no"), one=False, cap=None, **extra):
    return {
        "market_ticker": market,
        "event_ticker": event,
        "series": event.split("-")[0],
        "kind": "GAME",
        "title": title,
        "yes_label": "Atlanta wins",
        "no_label": "Pittsburgh wins",
        "strike": None,
        "player": None,
        "allowed_sides": list(sides),
        "size_max": cap,
        "one_per_event": one,
        # Everything below is price and chance; none of it may reach the model.
        "sides": {
            "yes": {
                "chance": 0.6183,
                "chance_display": "61.8%",
                "unknown_reason": "no book",
                "unknown_reason_code": "no_odds",
            }
        },
        "yes_ask_display": "43.7c ASKSENTINEL",
        **extra,
    }


def _listing():
    return {
        "game_event_ticker": GAME,
        "game_market_ticker": GAME + "-ATL",
        "groups": [
            {
                "series": "KXNFLGAME", "kind": "GAME", "label": "Who wins",
                "one_per_event": True,
                "legs": [
                    _leg(GAME + "-ATL", GAME, "Atlanta at Pittsburgh",
                         one=True, cap=1),
                ],
            },
            {
                "series": "KXNFLTOTAL", "kind": "TOTAL", "label": "Total points",
                "one_per_event": True,
                "legs": [
                    _leg("KXNFLTOTAL-26SEP13ATLPIT-40", "KXNFLTOTAL-26SEP13ATLPIT",
                         "Over 40.5 points", one=True, cap=1),
                    _leg("KXNFLTOTAL-26SEP13ATLPIT-45", "KXNFLTOTAL-26SEP13ATLPIT",
                         "Over 45.5 points", one=True, cap=1),
                ],
            },
            {
                "series": "KXNFLTD", "kind": "TD", "label": "Anytime touchdown",
                "one_per_event": False,
                "legs": [
                    _leg("KXNFLTD-26SEP13ATLPIT-A", "KXNFLTD-26SEP13ATLPIT",
                         "Player A scores", sides=("yes",), cap=None),
                    _leg("KXNFLTD-26SEP13ATLPIT-B", "KXNFLTD-26SEP13ATLPIT",
                         "Player B scores", sides=("yes",), cap=None),
                ],
            },
        ],
    }


SOURCE = CardSource(url="https://example.com/preview", published="2026-09-12")
NEEDS = "Atlanta wins and the game stays low-scoring."


def _card(
    *legs, story="A slow game.", drop_if="A starter is ruled out.",
    sources=(SOURCE,), ticket_needs=NEEDS, **kw,
):
    return CardOutput(
        story=story, drop_if=drop_if, legs=[CardLeg(**l) for l in legs],
        sources=list(sources), ticket_needs=ticket_needs, **kw,
    )


def _l(market, event, side="yes"):
    return {"market_ticker": market, "event_ticker": event, "side": side}


ATL = _l(GAME + "-ATL", GAME)
TOT40 = _l("KXNFLTOTAL-26SEP13ATLPIT-40", "KXNFLTOTAL-26SEP13ATLPIT")
TOT45 = _l("KXNFLTOTAL-26SEP13ATLPIT-45", "KXNFLTOTAL-26SEP13ATLPIT")
TDA = _l("KXNFLTD-26SEP13ATLPIT-A", "KXNFLTD-26SEP13ATLPIT")
TDB = _l("KXNFLTD-26SEP13ATLPIT-B", "KXNFLTD-26SEP13ATLPIT")


class StubUsage:
    input_tokens = 900
    output_tokens = 120
    cache_creation_input_tokens = 0
    cache_read_input_tokens = 0

    class server_tool_use:  # noqa: N801 -- mirrors the SDK attribute
        web_search_requests = 2


class StubResponse:
    def __init__(self, parsed):
        self.parsed_output = parsed
        self.stop_reason = "end_turn"
        self.usage = StubUsage()


class StubMessages:
    def __init__(self, parsed):
        self._parsed = parsed
        self.calls: list[dict] = []

    async def parse(self, **kwargs):
        self.calls.append(kwargs)
        return StubResponse(self._parsed)


class StubClient:
    def __init__(self, parsed):
        self.messages = StubMessages(parsed)


def _conn_budget(tmp_path, *, daily=24):
    conn = db.init_db(tmp_path / "gs.db")
    return conn, AgentBudget(
        conn, per_pass_budget=8, daily_budget=daily,
        searches_daily_budget=0, tokens_daily_budget=0,
    )


async def _run(tmp_path, parsed, *, daily=24):
    conn, budget = _conn_budget(tmp_path, daily=daily)
    client = StubClient(parsed)
    result = await build_card(
        conn, client, CONFIG, budget,
        game_event_ticker=GAME, sport_key="nfl", kickoff_ms=KICKOFF,
        game_title="Atlanta at Pittsburgh", kickoff_iso="2026-09-13T17:00Z",
        listing=_listing(), now_ms=NOW,
    )
    return conn, client, result


def _row(conn, card_id):
    return game_script_cards.card_by_id(conn, card_id)


class TestTheServerRefusesBeforeItStores:
    """Each refusal is one row, `refused_invalid`, one model call, no re-ask."""

    @pytest.mark.parametrize(
        "parsed, needle",
        [
            (
                _card(ATL, _l("KXNFLTOTAL-26SEP13ATLPIT-99", "KXNFLTOTAL-26SEP13ATLPIT")),
                "not in this game's leg listing",
            ),
            (
                _card(ATL, TOT40, TOT45),
                "allows 1 leg",
            ),
            (_card(ATL), "has 1 legs"),
            (_card(ATL, TOT40, TDA, TDB), "has 4 legs"),
            (_card(ATL, _l(TDA["market_ticker"], TDA["event_ticker"], "no")),
             "does not allow the no side"),
            (_card(ATL, ATL), "named twice"),
        ],
        ids=[
            "leg_not_in_listing", "two_legs_from_one_size_max_1_event",
            "fewer_than_two", "more_than_three", "side_not_allowed",
            "same_leg_twice",
        ],
    )
    async def test_a_bad_card_is_stored_refused_invalid(self, tmp_path, parsed, needle):
        conn, client, result = await _run(tmp_path, parsed)
        assert result.status == "refused_invalid"
        row = _row(conn, result.card_id)
        assert row["status"] == "refused_invalid"
        assert needle in row["reason"]
        assert row["story"] is None and row["legs"] is None
        assert len(client.messages.calls) == 1, "the model is never re-asked"

    async def test_a_leg_with_the_wrong_event_is_refused(self, tmp_path):
        bad = _l(TOT40["market_ticker"], GAME)
        conn, _c, result = await _run(tmp_path, _card(ATL, bad))
        assert result.status == "refused_invalid"

    async def test_a_card_with_no_story_or_drop_if_is_refused(self, tmp_path):
        conn, _c, result = await _run(tmp_path, _card(ATL, TOT40, story=" "))
        assert result.status == "refused_invalid"

    async def test_a_valid_two_and_three_leg_card_is_built(self, tmp_path):
        for legs in ((ATL, TOT40), (ATL, TOT40, TDA)):
            sub = tmp_path / str(len(legs))
            sub.mkdir()
            conn, _c, result = await _run(sub, _card(*legs))
            assert result.status == "built"
            row = _row(conn, result.card_id)
            assert [l["market_ticker"] for l in row["legs"]] == [
                l["market_ticker"] for l in legs
            ]
            assert row["story"] and row["drop_if"]

    async def test_card_without_sources_is_refused(self, tmp_path):
        """#281: every fact needs a page behind it. No source, or a source
        that is not a web address, is a `refused_invalid` row."""
        for i, sources in enumerate(((), (CardSource(url="ESPN", published=""),))):
            sub = tmp_path / str(i)
            sub.mkdir()
            conn, _c, result = await _run(sub, _card(ATL, TOT40, sources=sources))
            assert result.status == "refused_invalid"
            assert "no source page" in _row(conn, result.card_id)["reason"]

    @pytest.mark.parametrize(
        "needs",
        ["", "  ", "Atlanta wins (about a 30% shot)", "A 0.3 chance both land",
         "Good odds that Atlanta covers", "Likely an Atlanta win",
         "Atlanta wins; a real edge here"],
    )
    async def test_ticket_needs_is_words_not_a_number(self, tmp_path, needs):
        """#281 / rule 2: `ticket_needs` describes the game, never a chance,
        a price or an edge."""
        conn, _c, result = await _run(tmp_path, _card(ATL, TOT40, ticket_needs=needs))
        assert result.status == "refused_invalid"

    async def test_a_built_card_stores_its_sources_and_what_it_needs(self, tmp_path):
        needs = "Virginia Tech wins by 1 to 3 points and the game stays under 52."
        conn, _c, result = await _run(tmp_path, _card(ATL, TOT40, ticket_needs=needs))
        assert result.status == "built"
        row = _row(conn, result.card_id)
        assert row["sources"] == [SOURCE.model_dump()]
        assert row["ticket_needs"] == needs

    async def test_card_legs_freeze_ask_depth_read_ms_per_leg_only(self, tmp_path):
        """#283: each stored leg carries the listed ask for ITS side, the size
        at it and the listing's read time; a leg the listing could not price
        carries None, never 0; and no combined figure is stored anywhere."""
        listing = _listing()
        atl = listing["groups"][0]["legs"][0]
        atl["listed"] = {
            "read_ms": NOW - 1_000,
            "yes": {"ask_tenths": 437, "size": 120.0},
            "no": {"ask_tenths": 575, "size": 40.0},
        }
        conn, budget = _conn_budget(tmp_path)
        result = await build_card(
            conn, StubClient(_card(ATL, TOT40)), CONFIG, budget,
            game_event_ticker=GAME, sport_key="nfl", kickoff_ms=KICKOFF,
            game_title="Atlanta at Pittsburgh", kickoff_iso="2026-09-13T17:00Z",
            listing=listing, now_ms=NOW,
        )
        assert result.status == "built"
        legs = _row(conn, result.card_id)["legs"]
        assert legs[0]["at_build"] == {"ask_tenths": 437, "size": 120.0, "read_ms": NOW - 1_000}
        assert legs[1]["at_build"] == {"ask_tenths": None, "size": None, "read_ms": None}
        raw = conn.execute(
            "SELECT * FROM game_script_cards WHERE id = ?", (result.card_id,)
        ).fetchone()
        stored_numbers = {
            v for leg in json.loads(raw["legs_json"]) for v in leg["at_build"].values()
        }
        assert 437 * 575 not in stored_numbers and 437 + 575 not in stored_numbers
        assert set(legs[0]) == {"market_ticker", "event_ticker", "side", "at_build"}

    async def test_a_skip_claims_no_sources(self, tmp_path):
        conn, _c, result = await _run(
            tmp_path, CardOutput(skip=True, reason="too thin")
        )
        row = _row(conn, result.card_id)
        assert row["sources"] is None and row["ticket_needs"] is None

    def test_the_prompt_asks_for_todays_news_first_and_no_doubled_totals(self):
        system = game_script.SYSTEM
        assert "TODAY'S news first" in system
        assert "first-half total in the same direction" in system
        assert "able to change before kickoff" in system
        assert game_script.PROMPT_VERSION == "4"

    def test_validate_card_accepts_two_size_max_2_legs_from_one_event(self):
        listing = _listing()
        for leg in listing["groups"][1]["legs"]:
            leg["size_max"] = 2
        assert validate_card(_card(TOT40, TOT45), listing) is None


class TestEveryOutcomeIsARow:
    async def test_skip_is_stored_as_a_row_with_its_reason(self, tmp_path):
        parsed = CardOutput(skip=True, reason="Too little news to tie a story to.")
        conn, client, result = await _run(tmp_path, parsed)
        assert result.status == "skipped"
        row = _row(conn, result.card_id)
        assert row["status"] == "skipped"
        assert row["reason"] == "Too little news to tie a story to."
        assert row["legs"] is None and row["story"] is None
        assert row["agent_call_id"] == result.agent_call_id

    async def test_a_built_row_carries_the_call_and_prompt_version(self, tmp_path):
        conn, _c, result = await _run(tmp_path, _card(ATL, TOT40))
        row = _row(conn, result.card_id)
        assert row["agent_call_id"] == result.agent_call_id is not None
        assert row["prompt_version"] == game_script.PROMPT_VERSION
        call = conn.execute(
            "SELECT agent, ticker FROM agent_calls WHERE id = ?",
            (result.agent_call_id,),
        ).fetchone()
        assert (call["agent"], call["ticker"]) == ("game_script", GAME)

    async def test_a_budget_refusal_is_a_row_naming_the_ceiling_and_calls_nothing(
        self, tmp_path
    ):
        conn, budget = _conn_budget(tmp_path, daily=1)
        budget.reserve(called_ms=NOW, agent="scout", model="m")  # day is full
        client = StubClient(_card(ATL, TOT40))
        result = await build_card(
            conn, client, CONFIG, budget,
            game_event_ticker=GAME, sport_key="nfl", kickoff_ms=KICKOFF,
            game_title="Atlanta at Pittsburgh", kickoff_iso="x",
            listing=_listing(), now_ms=NOW,
        )
        assert result.status == "refused_budget"
        row = _row(conn, result.card_id)
        assert row["status"] == "refused_budget" and row["reason"]
        assert client.messages.calls == []
        assert conn.execute(
            "SELECT COUNT(*) AS c FROM agent_calls WHERE agent = 'game_script'"
        ).fetchone()["c"] == 0

    async def test_one_card_is_one_call_with_at_most_three_searches(self, tmp_path):
        _conn, client, _r = await _run(tmp_path, _card(ATL, TOT40))
        assert len(client.messages.calls) == 1
        tools = client.messages.calls[0]["tools"]
        assert [t["max_uses"] for t in tools] == [GAME_SCRIPT_MAX_SEARCHES] == [3]

    def test_the_store_mirrors_the_schema_checks(self, tmp_path):
        conn = db.init_db(tmp_path / "chk.db")
        common = dict(
            game_event_ticker=GAME, sport_key="nfl", kickoff_ms=KICKOFF, built_ms=NOW
        )
        with pytest.raises(ValueError):
            game_script_cards.insert_card(conn, status="built", **common)
        with pytest.raises(ValueError):
            game_script_cards.insert_card(conn, status="skipped", **common)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO game_script_cards (game_event_ticker, sport_key, "
                "kickoff_ms, built_ms, status) VALUES (?, 'nfl', 1, 1, 'skipped')",
                (GAME,),
            )


class TestTheModelNeverSeesAPriceOrAChance:
    def test_the_rendered_prompt_carries_no_price_or_chance(self):
        prompt = build_prompt(
            game_title="Atlanta at Pittsburgh", sport_key="nfl",
            kickoff_iso="2026-09-13T17:00Z", listing=_listing(),
        )
        # The listing does carry them ...
        assert "0.6183" in json.dumps(_listing())
        # ... and none reaches the model.
        for sentinel in PRICE_SENTINELS:
            assert sentinel not in prompt, sentinel
        # The legs themselves are there, so the assertion is not vacuous.
        assert GAME + "-ATL" in prompt and "Over 40.5 points" in prompt
        assert "ONE LEG ONLY" in prompt

    def test_listing_for_prompt_keeps_exactly_the_whitelisted_fields(self):
        groups = game_script.listing_for_prompt(_listing())
        legs = [leg for _label, group in groups for leg in group]
        assert len(legs) == 5
        for leg in legs:
            assert set(leg) == set(game_script.PROMPT_LEG_FIELDS)
            assert not any(s in json.dumps(leg) for s in PRICE_SENTINELS)

    def test_the_prompt_leg_fields_are_a_whitelist_without_price_names(self):
        for field in game_script.PROMPT_LEG_FIELDS:
            assert not set(field.split("_")) & {
                "price", "ask", "bid", "chance", "prob", "odds",
            }, field

    def test_the_system_prompt_states_no_price_and_no_forecast(self):
        assert "never shown a price" in game_script.SYSTEM


class TestTheOutputCarriesNoNumberAboutTheBet:
    FORBIDDEN = ("prob", "confid", "edge", "odds", "price", "chance", "score")

    def test_no_numeric_type_and_no_forbidden_field_name_anywhere(self):
        def walk(model, path):
            for name, field in model.model_fields.items():
                words = set(name.lower().split("_"))
                assert not any(
                    w.startswith(f) for w in words for f in self.FORBIDDEN
                ), f"{path}.{name}"
                for leaf in leaves(field.annotation):
                    if isinstance(leaf, type) and issubclass(leaf, PydanticBase):
                        walk(leaf, f"{path}.{name}")
                        continue
                    assert leaf not in (int, float, complex), f"{path}.{name}"

        def leaves(annotation):
            args = typing.get_args(annotation)
            if not args:
                yield annotation
            for arg in args:
                yield from leaves(arg)

        walk(CardOutput, "CardOutput")

    def test_the_json_schema_has_no_number_or_integer_type(self):
        schema = json.dumps(CardOutput.model_json_schema())
        assert '"number"' not in schema and '"integer"' not in schema

    def test_the_table_has_no_price_probability_confidence_or_edge_column(self, tmp_path):
        conn = db.init_db(tmp_path / "cols.db")
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(game_script_cards)")]
        assert cols
        for col in cols:
            assert not any(w in col for w in ("price", "prob", "confid", "edge", "ask")), col


class TestSportKey:
    def test_sport_key_for_is_the_lowercase_league(self):
        assert game_script_cards.sport_key_for("KXNFLGAME-26SEP13ATLPIT") == "nfl"
        assert game_script_cards.sport_key_for("kxnbagame-26OCT01LALBOS") == "nba"


class TestTheRoute:
    """`POST /api/game/{event}/card`, with the venue read and the model stubbed."""

    def _app(self, tmp_path, monkeypatch, *, kickoff=KICKOFF, parsed=None, key=True):
        db_path = tmp_path / "route.db"
        db.init_db(db_path).close()
        client = StubClient(parsed if parsed is not None else _card(ATL, TOT40))

        async def fake_listing(conn, **kw):
            return _listing_with_kinds()

        monkeypatch.setattr(game_router, "list_game_legs", fake_listing)
        monkeypatch.setattr(
            game_router, "_commence_ms_for_tickers",
            lambda conn, tickers: {t: kickoff for t in tickers} if kickoff else {},
        )
        monkeypatch.setattr(game_router, "build_client", lambda cfg: client)
        monkeypatch.setattr(
            game_router.AgentConfig, "from_env",
            classmethod(lambda cls: CONFIG if key else None),
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
        return TestClient(app), client, db_path

    def test_the_route_stores_and_returns_the_card(self, tmp_path, monkeypatch):
        http, client, db_path = self._app(tmp_path, monkeypatch)
        response = http.post(f"/api/game/{GAME}/card")
        assert response.status_code == 200, response.text
        card = response.json()["card"]
        assert card["status"] == "built"
        assert card["sport_key"] == "nfl" and card["kickoff_ms"] == KICKOFF
        assert len(client.messages.calls) == 1
        prompt = client.messages.calls[0]["messages"][0]["content"]
        for sentinel in PRICE_SENTINELS:
            assert sentinel not in prompt

    def test_no_kickoff_on_record_is_409_and_spends_nothing(self, tmp_path, monkeypatch):
        http, client, db_path = self._app(tmp_path, monkeypatch, kickoff=None)
        assert http.post(f"/api/game/{GAME}/card").status_code == 409
        assert client.messages.calls == []
        conn = db.open_db(db_path)
        assert conn.execute("SELECT COUNT(*) AS c FROM agent_calls").fetchone()["c"] == 0

    def test_no_api_key_is_503_and_spends_nothing(self, tmp_path, monkeypatch):
        http, client, _p = self._app(tmp_path, monkeypatch, key=False)
        assert http.post(f"/api/game/{GAME}/card").status_code == 503
        assert client.messages.calls == []

    def test_a_non_game_ticker_is_refused_in_words(self, tmp_path, monkeypatch):
        http, client, _p = self._app(tmp_path, monkeypatch)
        assert http.post("/api/game/KXNFLSPREAD-26SEP13ATLPIT/card").status_code == 422
        assert client.messages.calls == []

    def test_a_second_post_after_a_built_card_reuses_it_and_calls_nothing(
        self, tmp_path, monkeypatch
    ):
        http, client, _p = self._app(tmp_path, monkeypatch)
        first = http.post(f"/api/game/{GAME}/card").json()
        second = http.post(f"/api/game/{GAME}/card").json()
        assert first["reused"] is False and second["reused"] is True
        assert second["card"]["id"] == first["card"]["id"]
        assert len(client.messages.calls) == 1

    def test_a_skipped_card_also_blocks_a_second_call(self, tmp_path, monkeypatch):
        http, client, _p = self._app(
            tmp_path, monkeypatch, parsed=CardOutput(skip=True, reason="thin")
        )
        http.post(f"/api/game/{GAME}/card")
        again = http.post(f"/api/game/{GAME}/card").json()
        assert again["reused"] is True and again["card"]["status"] == "skipped"
        assert len(client.messages.calls) == 1

    @pytest.mark.parametrize("status", ["refused_budget", "refused_invalid"])
    def test_a_refusal_row_does_not_block_a_retry(self, tmp_path, monkeypatch, status):
        http, client, db_path = self._app(tmp_path, monkeypatch)
        conn = db.open_db(db_path)
        game_script_cards.insert_card(
            conn, game_event_ticker=GAME, sport_key="nfl", kickoff_ms=KICKOFF,
            built_ms=NOW - 1000, status=status, reason="earlier refusal",
        )
        conn.close()
        body = http.post(f"/api/game/{GAME}/card").json()
        assert body["reused"] is False and body["card"]["status"] == "built"
        assert len(client.messages.calls) == 1

    async def test_two_concurrent_posts_for_one_game_make_one_call(
        self, tmp_path, monkeypatch
    ):
        import asyncio

        import httpx

        http, _stub, _p = self._app(tmp_path, monkeypatch)
        gate = asyncio.Event()
        gated = StubClient(_card(ATL, TOT40))
        real_parse = gated.messages.parse

        async def slow_parse(**kwargs):
            await gate.wait()
            return await real_parse(**kwargs)

        gated.messages.parse = slow_parse
        monkeypatch.setattr(game_router, "build_client", lambda cfg: gated)

        transport = httpx.ASGITransport(app=http.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
            first = asyncio.create_task(ac.post(f"/api/game/{GAME}/card"))
            second = asyncio.create_task(ac.post(f"/api/game/{GAME}/card"))
            await asyncio.sleep(0.3)
            gate.set()
            responses = await asyncio.gather(first, second)
        assert [r.status_code for r in responses] == [200, 200]
        assert len(gated.messages.calls) == 1
        assert sorted(r.json()["reused"] for r in responses) == [False, True]

    def test_the_route_is_auth_gated(self, tmp_path, monkeypatch):
        from fastapi import HTTPException

        def deny():
            raise HTTPException(status_code=401, detail="no")

        http, client, _p = self._app(tmp_path, monkeypatch)
        app = FastAPI()
        game_router.register(
            app,
            app_config=SimpleNamespace(db_path=tmp_path / "route.db"),
            staleness=SimpleNamespace(max_odds_age_s=600),
            combo_api=lambda: object(),
            get_conn=lambda: None,
            require_auth=deny,
        )
        assert TestClient(app).post(f"/api/game/{GAME}/card").status_code == 401
        assert client.messages.calls == []


def _listing_with_kinds():
    return _listing()


# --- the win leg beside its own cover (Joe, /parlays 2026-09-30) -------------

SPREAD_ATL = _l("KXNFLSPREAD-26SEP13ATLPIT-ATL3", "KXNFLSPREAD-26SEP13ATLPIT")
SPREAD_PIT = _l("KXNFLSPREAD-26SEP13ATLPIT-PIT3", "KXNFLSPREAD-26SEP13ATLPIT")


def _listing_with_spread():
    listing = _listing()
    listing["groups"].append({
        "series": "KXNFLSPREAD", "kind": "SPREAD", "label": "Spread",
        "one_per_event": True,
        "legs": [
            _leg("KXNFLSPREAD-26SEP13ATLPIT-ATL3", "KXNFLSPREAD-26SEP13ATLPIT",
                 "Atlanta wins by over 2.5", one=True, cap=1),
            _leg("KXNFLSPREAD-26SEP13ATLPIT-PIT3", "KXNFLSPREAD-26SEP13ATLPIT",
                 "Pittsburgh wins by over 2.5", one=True, cap=1),
        ],
    })
    return listing


class TestAWinLegBesideItsOwnCoverIsDropped:
    """Kalshi refused `duplicated_legs`: "Vegas winning by 2+ already
    guarantees Vegas winning". Both-happen IS the cover, so dropping the win
    leg pays on exactly the same outcomes."""

    def test_the_same_teams_win_is_dropped(self):
        kept, dropped = game_script_cards.drop_implied_win_legs([ATL, SPREAD_ATL, TOT40])
        assert kept == [SPREAD_ATL, TOT40] and dropped == [ATL]

    def test_the_other_teams_cover_leaves_the_win_alone(self):
        kept, dropped = game_script_cards.drop_implied_win_legs([ATL, SPREAD_PIT])
        assert kept == [ATL, SPREAD_PIT] and dropped == []

    def test_a_no_side_is_left_alone(self):
        no_cover = {**SPREAD_ATL, "side": "no"}
        kept, dropped = game_script_cards.drop_implied_win_legs([ATL, no_cover])
        assert dropped == []

    def test_the_real_nhl_tickers_joe_hit(self):
        win = _l("KXNHLGAME-26SEP29CHIVGK-VGK", "KXNHLGAME-26SEP29CHIVGK")
        cover = _l("KXNHLSPREAD-26SEP29CHIVGK-VGK2", "KXNHLSPREAD-26SEP29CHIVGK")
        prop = _l("KXNHLPTS-26SEP29CHIVGK-EICHEL1", "KXNHLPTS-26SEP29CHIVGK")
        kept, dropped = game_script_cards.drop_implied_win_legs([win, cover, prop])
        assert kept == [cover, prop] and dropped == [win]

    async def test_a_three_leg_card_is_built_with_two(self, tmp_path):
        conn, budget = _conn_budget(tmp_path)
        result = await build_card(
            conn, StubClient(_card(ATL, SPREAD_ATL, TOT40)), CONFIG, budget,
            game_event_ticker=GAME, sport_key="nfl", kickoff_ms=KICKOFF,
            game_title="Atlanta at Pittsburgh", kickoff_iso="2026-09-13T17:00Z",
            listing=_listing_with_spread(), now_ms=NOW,
        )
        assert result.status == "built"
        row = _row(conn, result.card_id)
        assert [{k: l[k] for k in ("market_ticker", "event_ticker", "side")} for l in row["legs"]] == [SPREAD_ATL, TOT40]
        assert [{k: l[k] for k in ("market_ticker", "event_ticker", "side")} for l in row["dropped_legs"]] == [ATL]

    async def test_a_two_leg_card_left_with_one_is_refused(self, tmp_path):
        conn, budget = _conn_budget(tmp_path)
        result = await build_card(
            conn, StubClient(_card(ATL, SPREAD_ATL)), CONFIG, budget,
            game_event_ticker=GAME, sport_key="nfl", kickoff_ms=KICKOFF,
            game_title="Atlanta at Pittsburgh", kickoff_iso="2026-09-13T17:00Z",
            listing=_listing_with_spread(), now_ms=NOW,
        )
        assert result.status == "refused_invalid"
        assert "1 legs" in result.reason

    def test_a_stored_card_reads_without_the_win_leg(self, tmp_path):
        conn, _ = _conn_budget(tmp_path)
        card_id = game_script_cards.insert_card(
            conn, game_event_ticker=GAME, sport_key="nfl", kickoff_ms=KICKOFF,
            built_ms=NOW, status="built", story="s", drop_if="d",
            legs=[ATL, SPREAD_ATL, TOT40], prompt_version="1",
        )
        row = _row(conn, card_id)
        assert [{k: l[k] for k in ("market_ticker", "event_ticker", "side")} for l in row["legs"]] == [SPREAD_ATL, TOT40]
        stored = conn.execute(
            "SELECT legs_json FROM game_script_cards WHERE id = ?", (card_id,)
        ).fetchone()[0]
        assert "-ATL\"" in stored  # the scout's own pick is kept on the row

    def test_minting_the_shown_legs_stamps_the_card(self, tmp_path):
        from backend.game_builder import attach_combo_to_card
        conn, _ = _conn_budget(tmp_path)
        card_id = game_script_cards.insert_card(
            conn, game_event_ticker=GAME, sport_key="nfl", kickoff_ms=KICKOFF,
            built_ms=NOW, status="built", story="s", drop_if="d",
            legs=[ATL, SPREAD_ATL, TOT40], prompt_version="1",
        )
        shown = [(SPREAD_ATL["market_ticker"], "yes"), (TOT40["market_ticker"], "yes")]
        assert attach_combo_to_card(
            conn, game_event_ticker=GAME, legs=shown, minted="KXMVE-X"
        ) == card_id

    def test_the_prompt_states_the_rule(self):
        from backend.agents.game_script import SYSTEM
        assert "Never pair a team winning with that same team winning by a margin" in SYSTEM


class TestTicketNeedsMatchesLegs:
    """#308: a number in `ticket_needs` that disagrees with a leg's strike
    refuses the card; text with no number, or no unambiguous tie, passes."""

    EV = "KXNHLGAME-26OCT04WPGPIT"

    def _listing(self, *legs):
        # (market suffix, title, yes_label, no_label)
        return {"groups": [{"legs": [
            _leg(f"{self.EV}-{s}", self.EV, title, yes_label=yes, no_label=no)
            for s, title, yes, no in legs
        ]}]}

    def _check(self, listing, needs, *sides):
        legs = [_l(m["market_ticker"], self.EV, s)
                for m, s in zip(listing["groups"][0]["legs"], sides)]
        return validate_card(_card(*legs, ticket_needs=needs), listing)

    def test_card_218_under_6_5_called_seven_or_fewer_is_refused(self):
        listing = self._listing(
            ("T", "Winnipeg at Pittsburgh: Totals", "Under 6.5 goals scored", "Over 6.5 goals scored"),
            ("W", "Winnipeg", "Winnipeg", "Winnipeg does not win"),
        )
        reason = self._check(
            listing,
            "the two teams combined need to score seven or fewer goals",
            "yes", "yes",
        )
        assert reason and "at most 7" in reason and "at most 6" in reason

    def test_card_218_with_the_right_number_is_accepted(self):
        listing = self._listing(
            ("T", "t", "Under 6.5 goals scored", "x"),
            ("W", "Winnipeg", "Winnipeg", "x"),
        )
        for needs in ("the two teams combined need to score six or fewer goals",
                      "the total stays under 6.5 goals", "fewer than seven goals in total"):
            assert self._check(listing, needs, "yes", "yes") is None, needs

    def test_spread_and_over_total_live_text_is_accepted(self):
        listing = self._listing(
            ("S", "Boston wins by over 1.5 goals", "Boston wins by over 1.5 goals", "Not: Boston wins by 2+"),
            ("T", "Over 5.5 goals scored", "Over 5.5 goals scored", "Under 5.5 goals scored"),
        )
        needs = ("Boston needs to win by two or more goals, and the game needs "
                 "at least six total goals")
        assert self._check(listing, needs, "yes", "yes") is None

    def test_spread_and_over_disagreement_is_refused(self):
        listing = self._listing(
            ("S", "s", "Boston wins by over 1.5 goals", "x"),
            ("T", "t", "Over 5.5 goals scored", "x"),
        )
        for needs in (
            "Boston wins by three or more goals, and at least six total goals",
            "Boston wins by two or more goals, and at least seven total goals",
            "Boston wins by two or more goals, and at most five total goals",
        ):
            assert self._check(listing, needs, "yes", "yes") is not None, needs

    def test_under_total_and_player_prop_live_text_is_accepted(self):
        listing = self._listing(
            ("T", "t", "Over 6.5 runs scored", "Under 6.5 runs scored"),
            ("P", "p", "Cam Schlittler: 6+", "x"),
        )
        needs = ("the total runs scored stay under 6.5, and Cam Schlittler "
                 "records at least 6 strikeouts")
        assert self._check(listing, needs, "no", "yes") is None

    def test_player_prop_number_disagreement_is_refused(self):
        listing = self._listing(
            ("T", "t", "Over 6.5 runs scored", "Under 6.5 runs scored"),
            ("P", "p", "Cam Schlittler: 6+", "x"),
        )
        reason = self._check(
            listing,
            "the total runs scored stay under 6.5, and Cam Schlittler records at least 7 strikeouts",
            "no", "yes")
        assert reason and "Cam Schlittler" in reason

    def test_no_number_or_an_ambiguous_one_passes(self):
        listing = self._listing(
            ("T", "t", "Under 6.5 goals scored", "x"),
            ("W", "Winnipeg", "Winnipeg", "x"),
        )
        for needs in ("Winnipeg wins and the game stays low-scoring",
                      "Winnipeg wins by 1 to 3 goals and the game stays under 52",
                      "the first period has at least two goals"):
            assert self._check(listing, needs, "yes", "yes") is None, needs


class TestDropIfAndGameDaySource:
    """#310: drop_if must be checkable before kickoff; 'confirmed' needs a
    source dated on game day (America/Los_Angeles, as kickoffs are shown)."""

    # Kickoff 2026-10-05 23:00Z = 16:00 on 2026-10-05 in Los Angeles.
    KO = int(datetime.datetime(2026, 10, 5, 23, 0, tzinfo=datetime.timezone.utc).timestamp() * 1000)

    def _v(self, *, story="A slow game.", drop_if="A starter is ruled out.",
           sources=(SOURCE,), ko=True):
        return validate_card(
            _card(ATL, TOT40, story=story, drop_if=drop_if, sources=sources),
            _listing(), kickoff_ms=self.KO if ko else None,
        )

    @pytest.mark.parametrize("drop_if", [
        "scratched or pulled early for any reason before first pitch",
        "a different starting goalie than expected",
        "cleared to play a full workload",
        "he leaves during the game",
        "an in-game injury",
    ])
    def test_uncheckable_drop_ifs_are_refused(self, drop_if):
        assert "before kickoff" in (self._v(drop_if=drop_if) or "")

    @pytest.mark.parametrize("drop_if", [
        "Jake Sanderson is in Ottawa's lineup",
        "Jake Sanderson is ruled out",
        "Jake Sanderson is not in the lineup",
    ])
    def test_a_named_pre_kickoff_status_is_accepted(self, drop_if):
        assert self._v(drop_if=drop_if) is None

    def test_card_217_confirmed_with_no_game_day_source_is_refused(self):
        stale = CardSource(url="https://example.com/bos", published="2026-09-30")
        undated = CardSource(url="https://example.com/x", published="")
        story = "Jeremy Swayman confirmed as the starting goalie."
        reason = self._v(story=story, sources=(stale, undated))
        assert reason and "game day" in reason

    def test_confirmed_with_a_game_day_source_is_accepted(self):
        today = CardSource(url="https://example.com/t", published="2026-10-05")
        story = "Jeremy Swayman confirmed as the starting goalie."
        assert self._v(story=story, sources=(today,)) is None

    def test_a_story_that_says_expected_needs_no_game_day_source(self):
        assert self._v(story="Swayman is expected in goal.") is None

    def test_without_a_kickoff_the_game_day_rule_is_skipped(self):
        assert self._v(story="X confirmed in goal.", ko=False) is None


class TestTheBuildPathPassesTheKickoff:
    async def test_a_stale_confirmed_card_is_refused_on_the_build_path(self, tmp_path):
        # KICKOFF is 2026-09-13-ish in the helper; SOURCE is dated 09-12.
        card = _card(ATL, TOT40, story="Atlanta's QB is confirmed to start.")
        conn, _c, result = await _run(tmp_path, card)
        assert result.status == "refused_invalid"
        assert "game day" in result.reason
