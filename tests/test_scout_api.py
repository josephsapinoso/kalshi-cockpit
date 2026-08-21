"""The scout desk's routes: who may send it, and what the reader is told.

The POST spends money (three metered Anthropic calls, ADR 0060), so it sits
behind `require_auth` like every other spending route, refuses before writing
anything when the day's budget cannot afford the staff pair, and answers 202
`accepted` -- never `briefed` -- because the desk takes minutes and the phone
polls. The GET is a public read of stored notes.

The desk itself is stubbed here; `tests/test_scout_desk.py` owns the desk's
own contract. What these tests do NOT establish: that a background convening
survives a process restart (it does not, and the `gone_quiet` flag is the
honest rendering of that), or that a real briefing is any good.
"""

from __future__ import annotations

import json

import httpx
import pytest

from backend.api.routes import create_app
from backend.config import AppConfig
from backend.store import db

AUTH = {"Authorization": "Bearer secret-token"}


async def get(app, path, **kwargs):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.get(path, **kwargs)


async def post(app, path, **kwargs):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.post(path, **kwargs)


@pytest.fixture
def scout_db(tmp_path):
    """A db with one linked, scoutable ticker and one unlinked one."""
    path = tmp_path / "scout.db"
    conn = db.init_db(path)
    conn.execute(
        "INSERT INTO strategy_configs (version, created_ms, effective_from_ms, "
        "config_json, rationale) VALUES (1, 0, 0, '{}', 'test')"
    )
    conn.execute(
        "INSERT INTO kalshi_events (event_ticker, first_seen_ms, last_seen_ms, "
        "title) VALUES ('KXTEST-EVENT', 1000, 1000, 'A at B')"
    )
    conn.execute(
        "INSERT INTO kalshi_markets (ticker, event_ticker, first_seen_ms, "
        "last_seen_ms) VALUES ('KXTEST-LINKED', 'KXTEST-EVENT', 1000, 1000)"
    )
    conn.execute(
        "INSERT INTO kalshi_markets (ticker, first_seen_ms, last_seen_ms) "
        "VALUES ('KXTEST-UNLINKED', 1000, 1000)"
    )
    conn.execute(
        "INSERT INTO event_links (id, kalshi_event_ticker, odds_event_id, "
        "league, method, commence_skew_ms, linked_ms) "
        "VALUES (1, 'KXTEST-EVENT', 'odds-1', 'baseball_mlb', "
        "'exact_alias_pair', 0, 1000)"
    )
    conn.execute(
        "INSERT INTO odds_snapshots (fetched_ms, sport_key, odds_event_id, "
        "commence_ms, home_team, away_team, bookmaker, market, outcome_name, "
        "price_decimal) VALUES (1000, 'baseball_mlb', 'odds-1', 2000000, "
        "'B', 'A', 'pinnacle', 'h2h', 'B', 1.9)"
    )
    for ticker, link_id in (("KXTEST-LINKED", 1), ("KXTEST-UNLINKED", None)):
        conn.execute(
            "INSERT INTO recommendations (created_ms, strategy_config_version, "
            "ticker, link_id, side, entry_ask_tenths, fair_probability, "
            "edge_tenths, fee_predicted, ev_net_dollars, kelly_fraction, "
            "suggested_contracts, reference_contracts, kalshi_quote_age_ms, "
            "odds_age_ms, reason_text) "
            "VALUES (1000, 1, ?, ?, 'yes', 500, 0.52, 5.0, 0.1, 0.2, 0.01, "
            "0, 0, 1000, 2000, 'test row')",
            (ticker, link_id),
        )
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def demo_app(scout_db):
    return create_app(AppConfig(instance_mode="demo", db_path=scout_db))


@pytest.fixture
def live_app(scout_db):
    return create_app(
        AppConfig(instance_mode="live", auth_token="secret-token", db_path=scout_db)
    )


class TestSendingTheDeskIsGuarded:
    async def test_the_demo_cannot_send_the_desk(self, demo_app):
        response = await post(demo_app, "/api/scout/KXTEST-LINKED", headers=AUTH)
        assert response.status_code == 403

    async def test_no_token_no_desk(self, live_app):
        response = await post(live_app, "/api/scout/KXTEST-LINKED")
        assert response.status_code == 401

    async def test_no_anthropic_key_is_a_config_state_not_a_refusal(
        self, live_app, monkeypatch
    ):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        response = await post(live_app, "/api/scout/KXTEST-LINKED", headers=AUTH)
        assert response.status_code == 503
        assert "ANTHROPIC_API_KEY" in response.json()["detail"]

    async def test_an_unlinked_ticker_is_refused_with_the_reason(
        self, live_app, monkeypatch
    ):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
        response = await post(live_app, "/api/scout/KXTEST-UNLINKED", headers=AUTH)
        assert response.status_code == 422
        assert "linked sportsbook fixture" in response.json()["detail"]

    async def test_an_exhausted_day_answers_429_and_writes_nothing(
        self, live_app, scout_db, monkeypatch
    ):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
        monkeypatch.setenv("AGENT_MAX_CALLS_PER_DAY", "1")
        response = await post(live_app, "/api/scout/KXTEST-LINKED", headers=AUTH)
        assert response.status_code == 429
        conn = db.open_db(scout_db, read_only=True)
        try:
            count = conn.execute(
                "SELECT COUNT(*) AS c FROM scout_briefings"
            ).fetchone()["c"]
        finally:
            conn.close()
        assert count == 0


class TestReadingTheDesk:
    async def test_never_sent_is_its_own_state(self, demo_app):
        body = (await get(demo_app, "/api/scout/KXTEST-LINKED")).json()
        assert body == {"state": "never_sent"}

    async def test_a_stored_briefing_is_served_with_its_staff_notes(
        self, demo_app, scout_db
    ):
        conn = db.open_db(scout_db)
        try:
            conn.execute(
                "INSERT INTO scout_briefings (ticker, event_title, league, "
                "home_team, away_team, commence_ms, requested_ms, "
                "completed_ms, status, staff_json, briefing_json, model) "
                "VALUES ('KXTEST-LINKED', 'A at B', 'baseball_mlb', 'B', 'A', "
                "2000000, 1000, 2000, 'complete', ?, ?, 'claude-opus-5')",
                (
                    json.dumps([{"role": "home", "team": "B", "report": None}]),
                    json.dumps({"headline": "Quiet.", "assessment": "Thin."}),
                ),
            )
            conn.commit()
        finally:
            conn.close()
        body = (await get(demo_app, "/api/scout/KXTEST-LINKED")).json()
        assert body["state"] == "sent"
        assert body["status"] == "complete"
        assert body["briefing"]["headline"] == "Quiet."
        assert body["staff"][0]["team"] == "B"
        assert body["gone_quiet"] is False

    async def test_a_running_row_past_patience_reads_as_gone_quiet(
        self, demo_app, scout_db
    ):
        """A crashed process cannot come back to finish its row; the reader
        must not render it as alive forever."""
        conn = db.open_db(scout_db)
        try:
            conn.execute(
                "INSERT INTO scout_briefings (ticker, event_title, league, "
                "home_team, away_team, requested_ms, status, model) "
                "VALUES ('KXTEST-LINKED', 'A at B', 'baseball_mlb', 'B', 'A', "
                "1000, 'running', 'claude-opus-5')"
            )
            conn.commit()
        finally:
            conn.close()
        body = (await get(demo_app, "/api/scout/KXTEST-LINKED")).json()
        assert body["status"] == "running"
        assert body["gone_quiet"] is True


class TestTheMarketRouteServesTheFixtureFacts:
    """`/api/market/{ticker}` grew the game facts the market screen renders
    (2026-08-21, the partner's direction). Lives here because this file's
    fixture already builds the full link chain the route joins through.

    The load-bearing claim: **the clock is the odds fixture's** (2000000 in
    the fixture), never `kalshi_events.commence_ms` -- the fixture plants a
    3-hour-late value there and this fails if it ever surfaces.
    """

    KALSHI_TRAP_MS = 2000000 + 3 * 60 * 60 * 1000

    @pytest.fixture
    def trapped_app(self, scout_db):
        conn = db.open_db(scout_db)
        try:
            conn.execute(
                "UPDATE kalshi_events SET commence_ms = ? "
                "WHERE event_ticker = 'KXTEST-EVENT'",
                (self.KALSHI_TRAP_MS,),
            )
            conn.execute(
                "UPDATE kalshi_markets SET close_ms = 1999000, "
                "status = 'open' WHERE ticker = 'KXTEST-LINKED'"
            )
            conn.commit()
        finally:
            conn.close()
        from backend.api.routes import create_app
        from backend.config import AppConfig
        return create_app(AppConfig(instance_mode="demo", db_path=scout_db))

    async def test_the_clock_is_the_sportsbooks_and_the_facts_arrive(
        self, trapped_app
    ):
        body = (await get(trapped_app, "/api/market/KXTEST-LINKED")).json()
        assert body["commence_ms"] == 2000000
        assert body["commence_ms"] != self.KALSHI_TRAP_MS
        assert body["home_team"] == "B"
        assert body["away_team"] == "A"
        assert body["league"] == "baseball_mlb"
        assert body["close_ms"] == 1999000
        assert body["market_status"] == "open"

    async def test_an_unlinked_ticker_still_serves_with_unknowns_as_none(
        self, trapped_app
    ):
        """The join is LEFT: a market with no linked fixture keeps its page,
        and the unknowable facts resolve to None, never a substitute."""
        body = (await get(trapped_app, "/api/market/KXTEST-UNLINKED")).json()
        assert body["home_team"] is None
        assert body["commence_ms"] is None
