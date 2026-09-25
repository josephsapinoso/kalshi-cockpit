"""The leg scout's backend orchestration: server-side resolution, caching,
and the two routes (#152, ADR 0186).

What these tests establish, one per claim in the ticket:

- A fresh verdict is served without a call (`cached_verdict` reuses a
  `complete` row).
- A price move past the window asks again (`cached_verdict` refuses a stale
  ask and returns `None`, which the route reads as "run a fresh call").
- A verdict older than `fresh_hours` asks again.
- A leg after kickoff is refused and spends nothing (`resolve_leg`, and the
  route never reaches the budget for it).
- A leg with no quote is refused, same shape.
- The recorded ask is the server's, not the client's: an extra `ask` field
  anywhere in the request body is 422 before any handler code runs.
- Every complete row carries what scoring needs (`_run_leg_verdict` settles
  `ask_tenths`, `commence_ms`, `model`, `verdict`, `reason`, `agent_call_id`).
- A leg reads its game's briefing across series (the #150 join, reused here
  through `_briefing_for_ticker`).
- More than 8 legs is 422.
- The ladder is unaffected by `leg_verdicts` rows existing at all.

What this does not establish: that a verdict is any good, or that the
Anthropic call itself behaves as `backend/agents/leg_verdict.py` claims --
`tests/test_leg_verdict_seat.py` owns that half.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.agents.base import AgentConfig
from backend.agents.leg_verdict import LegVerdict
from backend.api.routers import leg_verdicts as leg_verdicts_router
from backend.config import LegVerdictConfig
from backend.leg_verdicts import (
    LegContext,
    LegRefusal,
    _briefing_for_ticker,
    _run_leg_verdict,
    cached_verdict,
    read_verdicts,
    resolve_leg,
)
from backend.parlays import build_ladder_payload, ladder_candidates
from backend.store import db as store
from backend.store.db import now_ms
from tests.test_parlays_api import seed_game

CONFIG = LegVerdictConfig(enabled=True, fresh_hours=6, price_move_tenths=20)


@pytest.fixture
def conn(tmp_path):
    c = store.init_db(tmp_path / "leg_verdicts.db")
    yield c
    c.close()


def _seed_leg(
    conn,
    *,
    ticker: str,
    event_ticker: str = "KXTEST-GAME1",
    odds_event_id: str = "odds-1",
    commence_ms: int,
    sport_key: str = "basketball_wnba",
    league: str = "Pro Basketball (W)",
    title: str | None = None,
    no_bid_tenths: int | None = 570,
    yes_bid_tenths: int | None = 500,
    with_quote: bool = True,
    with_fixture: bool = True,
) -> None:
    """One linked leg: a Kalshi market, an odds fixture, and (usually) a
    quote. Mirrors `tests/test_parlays_api.py::seed_game`'s column shapes so
    every insert satisfies the same NOT NULL constraints.
    """
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_events (event_ticker, title, "
        "first_seen_ms, last_seen_ms) VALUES (?, ?, 0, 0)",
        (event_ticker, "Away at Home"),
    )
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_markets (ticker, event_ticker, title, "
        "market_type, status, first_seen_ms, last_seen_ms) "
        "VALUES (?, ?, ?, 'moneyline', 'active', 0, 0)",
        (ticker, event_ticker, title or f"{ticker} title"),
    )
    if with_fixture:
        conn.execute(
            "INSERT OR IGNORE INTO event_links (kalshi_event_ticker, "
            "odds_event_id, league, method, commence_skew_ms, linked_ms) "
            "VALUES (?, ?, ?, 'exact_alias_pair', 0, 0)",
            (event_ticker, odds_event_id, league),
        )
        conn.execute(
            "INSERT INTO odds_snapshots (fetched_ms, sport_key, "
            "odds_event_id, commence_ms, home_team, away_team, bookmaker, "
            "market, outcome_name, price_decimal) VALUES (0, ?, ?, ?, "
            "'Home', 'Away', 'pinnacle', 'h2h', 'Home', 1.6)",
            (sport_key, odds_event_id, commence_ms),
        )
    if with_quote:
        conn.execute(
            "INSERT INTO kalshi_quotes (ticker, observed_ms, source, "
            "yes_bid_tenths, yes_bid_qty, no_bid_tenths, no_bid_qty) "
            "VALUES (?, 0, 'rest', ?, 100, ?, 100)",
            (ticker, yes_bid_tenths, no_bid_tenths),
        )
    conn.commit()


class TestResolveLegRefuses:
    def test_a_leg_after_kickoff_is_refused_and_spends_nothing(self, conn):
        t = now_ms()
        _seed_leg(conn, ticker="KXTEST-GAME1-A", commence_ms=t - 1_000)
        result = resolve_leg(conn, "KXTEST-GAME1-A", "yes", t)
        assert isinstance(result, LegRefusal)
        assert "already started" in result.reason.lower()
        assert conn.execute(
            "SELECT COUNT(*) AS c FROM leg_verdicts"
        ).fetchone()["c"] == 0
        assert conn.execute(
            "SELECT COUNT(*) AS c FROM agent_calls"
        ).fetchone()["c"] == 0

    def test_a_leg_with_no_quote_is_refused(self, conn):
        t = now_ms()
        _seed_leg(
            conn, ticker="KXTEST-GAME1-B", commence_ms=t + 3_600_000,
            with_quote=False,
        )
        result = resolve_leg(conn, "KXTEST-GAME1-B", "yes", t)
        assert isinstance(result, LegRefusal)
        assert "no quote" in result.reason.lower()

    def test_a_leg_with_no_linked_fixture_is_refused(self, conn):
        t = now_ms()
        _seed_leg(
            conn, ticker="KXTEST-GAME1-C", commence_ms=t + 3_600_000,
            with_fixture=False, with_quote=False,
        )
        result = resolve_leg(conn, "KXTEST-GAME1-C", "yes", t)
        assert isinstance(result, LegRefusal)
        assert "no linked sportsbook fixture" in result.reason.lower()

    def test_an_unknown_ticker_is_refused(self, conn):
        result = resolve_leg(conn, "NOPE-TICKER", "yes", now_ms())
        assert isinstance(result, LegRefusal)

    def test_a_bad_side_is_refused(self, conn):
        t = now_ms()
        _seed_leg(conn, ticker="KXTEST-GAME1-D", commence_ms=t + 3_600_000)
        result = resolve_leg(conn, "KXTEST-GAME1-D", "over", t)
        assert isinstance(result, LegRefusal)


class TestResolveLegReadsTheServerPriceAndKickoff:
    def test_the_ask_is_the_derived_one_never_the_mid(self, conn):
        t = now_ms()
        # no_bid_tenths=570 -> YES ask = 1000 - 570 = 430 -> "43c"
        _seed_leg(
            conn, ticker="KXTEST-GAME1-E", commence_ms=t + 3_600_000,
            no_bid_tenths=570,
        )
        ctx = resolve_leg(conn, "KXTEST-GAME1-E", "yes", t)
        assert isinstance(ctx, LegContext)
        assert ctx.ask_tenths == 430
        assert ctx.ask_display == "43c"
        assert ctx.commence_ms == t + 3_600_000
        assert ctx.event_title
        assert ctx.league == "basketball_wnba"  # sportsbook sport_key, not
        # event_links.league ("Pro Basketball (W)")


class TestALegReadsItsGamesBriefingAcrossSeries:
    def test_a_spread_leg_sees_a_briefing_filed_on_the_moneyline(self, conn):
        """The #150 join: two series (moneyline, spread) sharing one fixture
        segment and league, one briefing filed on the moneyline market."""
        t = now_ms()
        conn.execute(
            "INSERT INTO kalshi_series (series_ticker, league, "
            "first_seen_ms, last_seen_ms) VALUES "
            "('KXWNBAGAME', 'WNBA', 0, 0), ('KXWNBASPREAD', 'WNBA', 0, 0)"
        )
        conn.execute(
            "INSERT INTO kalshi_events (event_ticker, title, first_seen_ms, "
            "last_seen_ms) VALUES "
            "('KXWNBAGAME-26SEP24CHIWSH', 'Away at Home', 0, 0), "
            "('KXWNBASPREAD-26SEP24CHIWSH', 'Away at Home', 0, 0)"
        )
        conn.execute(
            "INSERT INTO kalshi_markets (ticker, event_ticker, "
            "series_ticker, title, market_type, status, first_seen_ms, "
            "last_seen_ms) VALUES "
            "('KXWNBAGAME-26SEP24CHIWSH-CHI', 'KXWNBAGAME-26SEP24CHIWSH', "
            "'KXWNBAGAME', 'Chicago ML', 'moneyline', 'active', 0, 0), "
            "('KXWNBASPREAD-26SEP24CHIWSH-CHI-5', "
            "'KXWNBASPREAD-26SEP24CHIWSH', 'KXWNBASPREAD', 'Chicago -5', "
            "'spread', 'active', 0, 0)"
        )
        conn.execute(
            "INSERT INTO scout_briefings (ticker, event_title, league, "
            "home_team, away_team, commence_ms, requested_ms, completed_ms, "
            "status, briefing_json, model) VALUES "
            "('KXWNBAGAME-26SEP24CHIWSH-CHI', 'Chicago at Washington', "
            "'basketball_wnba', 'Washington', 'Chicago', ?, ?, ?, "
            "'complete', ?, 'm')",
            (
                t + 3_600_000, t - 10_000, t - 5_000,
                '{"headline": "Starter questionable", "board": []}',
            ),
        )
        conn.commit()

        briefing_id, text = _briefing_for_ticker(
            conn, "KXWNBASPREAD-26SEP24CHIWSH-CHI-5", now_ms=t
        )
        assert briefing_id is not None
        assert text == "Starter questionable"


class TestCachedVerdict:
    def _insert(self, conn, *, ticker, side, status, ask_tenths, commence_ms,
                requested_ms, completed_ms=None, verdict=None, reason=None,
                refusal_reason=None):
        conn.execute(
            "INSERT INTO leg_verdicts (ticker, side, ask_tenths, "
            "commence_ms, requested_ms, completed_ms, status, verdict, "
            "reason, refusal_reason, model, trigger) VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'm', 'price_tap')",
            (
                ticker, side, ask_tenths, commence_ms, requested_ms,
                completed_ms, status, verdict, reason, refusal_reason,
            ),
        )
        conn.commit()

    def test_a_fresh_verdict_is_served_without_a_call(self, conn):
        t = now_ms()
        self._insert(
            conn, ticker="T", side="yes", status="complete", ask_tenths=430,
            commence_ms=t + 3_600_000, requested_ms=t - 60_000,
            completed_ms=t - 55_000, verdict="take", reason="ok",
        )
        row = cached_verdict(
            conn, "T", "yes", ask_tenths=430, commence_ms=t + 3_600_000,
            config=CONFIG, now_ms=t,
        )
        assert row is not None
        assert row["verdict"] == "take"

    def test_a_price_move_past_the_window_asks_again(self, conn):
        t = now_ms()
        self._insert(
            conn, ticker="T", side="yes", status="complete", ask_tenths=430,
            commence_ms=t + 3_600_000, requested_ms=t - 60_000,
            completed_ms=t - 55_000, verdict="take", reason="ok",
        )
        # 430 -> 460 is a 30-tenth move, past price_move_tenths=20.
        row = cached_verdict(
            conn, "T", "yes", ask_tenths=460, commence_ms=t + 3_600_000,
            config=CONFIG, now_ms=t,
        )
        assert row is None

    def test_a_price_move_inside_the_window_is_still_served(self, conn):
        t = now_ms()
        self._insert(
            conn, ticker="T", side="yes", status="complete", ask_tenths=430,
            commence_ms=t + 3_600_000, requested_ms=t - 60_000,
            completed_ms=t - 55_000, verdict="take", reason="ok",
        )
        row = cached_verdict(
            conn, "T", "yes", ask_tenths=445, commence_ms=t + 3_600_000,
            config=CONFIG, now_ms=t,
        )
        assert row is not None

    def test_a_verdict_older_than_the_fresh_window_asks_again(self, conn):
        t = now_ms()
        seven_hours_ago = t - 7 * 3600 * 1000
        self._insert(
            conn, ticker="T", side="yes", status="complete", ask_tenths=430,
            commence_ms=t + 3_600_000, requested_ms=seven_hours_ago,
            completed_ms=seven_hours_ago + 5_000, verdict="take", reason="ok",
        )
        row = cached_verdict(
            conn, "T", "yes", ask_tenths=430, commence_ms=t + 3_600_000,
            config=CONFIG, now_ms=t,
        )
        assert row is None

    def test_a_verdict_inside_the_fresh_window_is_served(self, conn):
        t = now_ms()
        five_hours_ago = t - 5 * 3600 * 1000
        self._insert(
            conn, ticker="T", side="yes", status="complete", ask_tenths=430,
            commence_ms=t + 3_600_000, requested_ms=five_hours_ago,
            completed_ms=five_hours_ago + 5_000, verdict="take", reason="ok",
        )
        row = cached_verdict(
            conn, "T", "yes", ask_tenths=430, commence_ms=t + 3_600_000,
            config=CONFIG, now_ms=t,
        )
        assert row is not None

    def test_a_refused_row_is_never_reused(self, conn):
        t = now_ms()
        self._insert(
            conn, ticker="T", side="yes", status="refused",
            ask_tenths=None, commence_ms=None, requested_ms=t - 1_000,
            completed_ms=t - 900, refusal_reason="no budget",
        )
        row = cached_verdict(
            conn, "T", "yes", ask_tenths=430, commence_ms=t + 3_600_000,
            config=CONFIG, now_ms=t,
        )
        assert row is None

    def test_a_running_row_under_five_minutes_is_pending(self, conn):
        t = now_ms()
        self._insert(
            conn, ticker="T", side="yes", status="running", ask_tenths=430,
            commence_ms=t + 3_600_000, requested_ms=t - 60_000,
        )
        row = cached_verdict(
            conn, "T", "yes", ask_tenths=430, commence_ms=t + 3_600_000,
            config=CONFIG, now_ms=t,
        )
        assert row is not None
        assert row["status"] == "running"

    def test_a_running_row_gone_quiet_is_treated_as_absent(self, conn):
        t = now_ms()
        self._insert(
            conn, ticker="T", side="yes", status="running", ask_tenths=430,
            commence_ms=t + 3_600_000, requested_ms=t - 6 * 60_000,
        )
        row = cached_verdict(
            conn, "T", "yes", ask_tenths=430, commence_ms=t + 3_600_000,
            config=CONFIG, now_ms=t,
        )
        assert row is None

    def test_a_recent_failed_row_blocks_an_automatic_retry(self, conn):
        t = now_ms()
        self._insert(
            conn, ticker="T", side="yes", status="failed", ask_tenths=430,
            commence_ms=t + 3_600_000, requested_ms=t - 5 * 60_000,
            completed_ms=t - 4 * 60_000, refusal_reason="the call died",
        )
        row = cached_verdict(
            conn, "T", "yes", ask_tenths=430, commence_ms=t + 3_600_000,
            config=CONFIG, now_ms=t,
        )
        assert row is not None
        assert row["status"] == "failed"

    def test_an_old_failed_row_allows_a_retry(self, conn):
        t = now_ms()
        self._insert(
            conn, ticker="T", side="yes", status="failed", ask_tenths=430,
            commence_ms=t + 3_600_000, requested_ms=t - 20 * 60_000,
            completed_ms=t - 19 * 60_000, refusal_reason="the call died",
        )
        row = cached_verdict(
            conn, "T", "yes", ask_tenths=430, commence_ms=t + 3_600_000,
            config=CONFIG, now_ms=t,
        )
        assert row is None


class TestReadVerdicts:
    def test_a_leg_never_requested_reads_as_none(self, conn):
        out = read_verdicts(conn, [("T", "yes")], now_ms=now_ms())
        assert out == [
            {
                "ticker": "T", "side": "yes", "state": "none", "id": None,
                "verdict": None, "reason": None,
                "ask_display_at_verdict": None, "age_ms": None,
                "refusal_reason": None,
            }
        ]

    def test_every_asked_leg_is_present_in_order(self, conn):
        out = read_verdicts(
            conn, [("A", "yes"), ("B", "no")], now_ms=now_ms()
        )
        assert [(r["ticker"], r["side"]) for r in out] == [
            ("A", "yes"), ("B", "no"),
        ]

    def test_a_complete_row_reads_as_cached(self, conn):
        t = now_ms()
        conn.execute(
            "INSERT INTO leg_verdicts (ticker, side, ask_tenths, "
            "commence_ms, requested_ms, completed_ms, status, verdict, "
            "reason, model, trigger) VALUES ('T', 'yes', 430, ?, ?, ?, "
            "'complete', 'take', 'Nothing new.', 'm', 'price_tap')",
            (t + 3_600_000, t - 1_000, t - 500),
        )
        conn.commit()
        out = read_verdicts(conn, [("T", "yes")], now_ms=t)
        assert out[0]["state"] == "cached"
        assert out[0]["verdict"] == "take"
        assert out[0]["ask_display_at_verdict"] == "43c"

    def test_a_failed_row_reads_as_refused_with_its_reason(self, conn):
        t = now_ms()
        conn.execute(
            "INSERT INTO leg_verdicts (ticker, side, ask_tenths, "
            "commence_ms, requested_ms, completed_ms, status, "
            "refusal_reason, model, trigger) VALUES ('T', 'yes', 430, ?, "
            "?, ?, 'failed', 'the call died', 'm', 'price_tap')",
            (t + 3_600_000, t - 1_000, t - 500),
        )
        conn.commit()
        out = read_verdicts(conn, [("T", "yes")], now_ms=t)
        assert out[0]["state"] == "refused"
        assert out[0]["refusal_reason"] == "the call died"


class TestRunLegVerdictSettlesEveryFieldScoringNeeds:
    async def test_a_complete_run_writes_what_scoring_needs(self, tmp_path):
        from tests.test_leg_verdict_seat import StubClient

        db_path = tmp_path / "run.db"
        conn = store.init_db(db_path)
        t = now_ms()
        row_id = conn.execute(
            "INSERT INTO leg_verdicts (ticker, side, ask_tenths, "
            "commence_ms, requested_ms, status, model, trigger) VALUES "
            "('T', 'yes', 430, ?, ?, 'running', 'claude-sonnet-5', "
            "'price_tap')",
            (t + 3_600_000, t),
        ).lastrowid
        conn.commit()
        conn.close()

        ctx = LegContext(
            ticker="T", side="yes", label="Chicago wins", ask_tenths=430,
            ask_display="43c", event_title="Chicago at Washington",
            league="basketball_wnba", commence_ms=t + 3_600_000,
            briefing_id=None, briefing_text=None,
        )
        agent_config = AgentConfig(api_key="test", model="claude-sonnet-5")
        client = StubClient(
            parsed=LegVerdict(verdict="take", reason="Nothing new on either team.")
        )
        await _run_leg_verdict(
            db_path, row_id, agent_config, ctx,
            client_factory=lambda cfg: client,
        )

        conn = store.open_db(db_path)
        row = conn.execute(
            "SELECT * FROM leg_verdicts WHERE id = ?", (row_id,)
        ).fetchone()
        assert row["status"] == "complete"
        assert row["ask_tenths"] == 430
        assert row["commence_ms"] == t + 3_600_000
        assert row["model"] == "claude-sonnet-5"
        assert row["verdict"] == "take"
        assert row["reason"] == "Nothing new on either team."
        assert row["agent_call_id"] is not None
        assert row["input_tokens"] == 900
        assert row["output_tokens"] == 120
        assert row["web_searches"] == 2
        conn.close()

    async def test_a_refused_run_never_calls_the_client(self, tmp_path):
        """When the day is exhausted between the route's check and the
        background task, `give_leg_verdict` refuses again -- and the row
        lands `refused`, never `complete`, with nothing billed."""
        from tests.test_leg_verdict_seat import StubClient

        db_path = tmp_path / "run2.db"
        conn = store.init_db(db_path)
        t = now_ms()
        row_id = conn.execute(
            "INSERT INTO leg_verdicts (ticker, side, ask_tenths, "
            "commence_ms, requested_ms, status, model, trigger) VALUES "
            "('T', 'yes', 430, ?, ?, 'running', 'claude-sonnet-5', "
            "'price_tap')",
            (t + 3_600_000, t),
        ).lastrowid
        conn.commit()
        conn.close()

        ctx = LegContext(
            ticker="T", side="yes", label="Chicago wins", ask_tenths=430,
            ask_display="43c", event_title="Chicago at Washington",
            league="basketball_wnba", commence_ms=t + 3_600_000,
            briefing_id=None, briefing_text=None,
        )
        # A config with a zero daily budget refuses every call.
        agent_config = AgentConfig(
            api_key="test", model="claude-sonnet-5", max_calls_per_day=0,
        )
        client = StubClient(
            parsed=LegVerdict(verdict="take", reason="ok")
        )
        await _run_leg_verdict(
            db_path, row_id, agent_config, ctx,
            client_factory=lambda cfg: client,
        )
        conn = store.open_db(db_path)
        row = conn.execute(
            "SELECT * FROM leg_verdicts WHERE id = ?", (row_id,)
        ).fetchone()
        assert row["status"] == "refused"
        assert row["verdict"] is None
        assert client.messages.calls == []
        conn.close()


# --- The route -----------------------------------------------------------


def _make_app(db_path):
    app = FastAPI()
    app_config = SimpleNamespace(db_path=db_path)

    def get_conn():
        c = store.open_db(db_path)
        try:
            yield c
        finally:
            c.close()

    def require_auth():
        return None

    leg_verdicts_router.register(
        app, app_config=app_config, get_conn=get_conn, require_auth=require_auth,
    )
    return app


@pytest.fixture
def app_env(tmp_path, monkeypatch):
    db_path = tmp_path / "route.db"
    conn = store.init_db(db_path)
    conn.close()
    monkeypatch.setenv("LEG_VERDICT_ENABLED", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    app = _make_app(db_path)
    client = TestClient(app)
    return db_path, client


class TestTheRouteRejectsAPriceFromTheBrowser:
    def test_an_extra_ask_field_on_a_leg_is_422(self, app_env):
        _, client = app_env
        resp = client.post(
            "/api/leg-verdicts",
            json={
                "trigger": "price_tap",
                "legs": [{"ticker": "T", "side": "yes", "ask": 1}],
            },
        )
        assert resp.status_code == 422

    def test_more_than_eight_legs_is_422(self, app_env):
        _, client = app_env
        legs = [{"ticker": f"T{i}", "side": "yes"} for i in range(9)]
        resp = client.post(
            "/api/leg-verdicts", json={"trigger": "price_tap", "legs": legs},
        )
        assert resp.status_code == 422

    def test_eight_legs_is_accepted_by_validation(self, app_env):
        db_path, client = app_env
        conn = store.open_db(db_path)
        t = now_ms()
        for i in range(8):
            _seed_leg(
                conn, ticker=f"KXTEST-GAME1-L{i}", event_ticker="KXTEST-GAME1",
                odds_event_id="odds-shared", commence_ms=t + 3_600_000,
                with_quote=False,
            )
        conn.close()
        legs = [{"ticker": f"KXTEST-GAME1-L{i}", "side": "yes"} for i in range(8)]
        resp = client.post(
            "/api/leg-verdicts", json={"trigger": "price_tap", "legs": legs},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert len(body["legs"]) == 8
        # No quotes seeded, so every leg is refused -- validation accepted
        # the shape, resolution refused the content.
        assert all(leg["state"] == "refused" for leg in body["legs"])


class TestTheRouteRequiresConfiguration:
    def test_disabled_is_503(self, tmp_path, monkeypatch):
        db_path = tmp_path / "off.db"
        store.init_db(db_path).close()
        monkeypatch.setenv("LEG_VERDICT_ENABLED", "false")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        client = TestClient(_make_app(db_path))
        resp = client.post(
            "/api/leg-verdicts",
            json={"trigger": "price_tap", "legs": [{"ticker": "T", "side": "yes"}]},
        )
        assert resp.status_code == 503

    def test_no_api_key_is_503(self, tmp_path, monkeypatch):
        db_path = tmp_path / "off2.db"
        store.init_db(db_path).close()
        monkeypatch.setenv("LEG_VERDICT_ENABLED", "true")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        client = TestClient(_make_app(db_path))
        resp = client.post(
            "/api/leg-verdicts",
            json={"trigger": "price_tap", "legs": [{"ticker": "T", "side": "yes"}]},
        )
        assert resp.status_code == 503


class TestTheRouteServesACachedVerdictWithoutASecondCall:
    def test_a_fresh_row_is_served_as_cached_and_nothing_new_is_written(
        self, app_env
    ):
        db_path, client = app_env
        conn = store.open_db(db_path)
        t = now_ms()
        _seed_leg(
            conn, ticker="KXTEST-GAME1-CACHED", commence_ms=t + 3_600_000,
            no_bid_tenths=570,
        )
        conn.execute(
            "INSERT INTO leg_verdicts (ticker, side, ask_tenths, "
            "commence_ms, requested_ms, completed_ms, status, verdict, "
            "reason, model, trigger) VALUES ('KXTEST-GAME1-CACHED', 'yes', "
            "430, ?, ?, ?, 'complete', 'take', 'Nothing new.', 'm', "
            "'price_tap')",
            (t + 3_600_000, t - 60_000, t - 55_000),
        )
        conn.commit()
        before = conn.execute(
            "SELECT COUNT(*) AS c FROM leg_verdicts"
        ).fetchone()["c"]
        conn.close()

        resp = client.post(
            "/api/leg-verdicts",
            json={
                "trigger": "price_tap",
                "legs": [{"ticker": "KXTEST-GAME1-CACHED", "side": "yes"}],
            },
        )
        assert resp.status_code == 202
        leg = resp.json()["legs"][0]
        assert leg["state"] == "cached"
        assert leg["verdict"] == "take"

        conn = store.open_db(db_path)
        after = conn.execute(
            "SELECT COUNT(*) AS c FROM leg_verdicts"
        ).fetchone()["c"]
        conn.close()
        assert after == before  # nothing new written for a cache hit


class TestTheRouteRefusesResolutionFailuresWithoutTouchingTheBudget:
    def test_a_leg_with_no_quote_is_refused_and_writes_no_row(self, app_env):
        db_path, client = app_env
        conn = store.open_db(db_path)
        t = now_ms()
        _seed_leg(
            conn, ticker="KXTEST-GAME1-NOQUOTE", commence_ms=t + 3_600_000,
            with_quote=False,
        )
        conn.close()

        resp = client.post(
            "/api/leg-verdicts",
            json={
                "trigger": "price_tap",
                "legs": [{"ticker": "KXTEST-GAME1-NOQUOTE", "side": "yes"}],
            },
        )
        assert resp.status_code == 202
        leg = resp.json()["legs"][0]
        assert leg["state"] == "refused"
        assert leg["refusal_reason"]

        conn = store.open_db(db_path)
        assert conn.execute(
            "SELECT COUNT(*) AS c FROM leg_verdicts"
        ).fetchone()["c"] == 0
        assert conn.execute(
            "SELECT COUNT(*) AS c FROM agent_calls"
        ).fetchone()["c"] == 0
        conn.close()

    def test_a_leg_after_kickoff_is_refused_and_writes_no_row(self, app_env):
        db_path, client = app_env
        conn = store.open_db(db_path)
        t = now_ms()
        _seed_leg(
            conn, ticker="KXTEST-GAME1-STARTED", commence_ms=t - 1_000,
        )
        conn.close()

        resp = client.post(
            "/api/leg-verdicts",
            json={
                "trigger": "price_tap",
                "legs": [{"ticker": "KXTEST-GAME1-STARTED", "side": "yes"}],
            },
        )
        assert resp.status_code == 202
        leg = resp.json()["legs"][0]
        assert leg["state"] == "refused"

        conn = store.open_db(db_path)
        assert conn.execute(
            "SELECT COUNT(*) AS c FROM leg_verdicts"
        ).fetchone()["c"] == 0
        conn.close()


class TestTheGetRoute:
    def test_a_never_requested_leg_reads_as_none(self, app_env):
        _, client = app_env
        resp = client.get("/api/leg-verdicts", params={"leg": "T:yes"})
        assert resp.status_code == 200
        assert resp.json()["legs"][0]["state"] == "none"

    def test_a_malformed_leg_param_is_422(self, app_env):
        _, client = app_env
        resp = client.get("/api/leg-verdicts", params={"leg": "no-colon-here"})
        assert resp.status_code == 422

    def test_a_bad_side_in_the_param_is_422(self, app_env):
        _, client = app_env
        resp = client.get("/api/leg-verdicts", params={"leg": "T:maybe"})
        assert resp.status_code == 422


class TestTheLadderIsUnaffectedByLegVerdictsRows:
    def test_the_ladder_order_is_identical_with_and_without_verdict_rows(
        self, conn
    ):
        t = now_ms()
        seed_game(conn, game="g1", team="Alpha", other="Beta", p=0.68, computed_ms=t)
        seed_game(conn, game="g1", team="Beta", other="Alpha", p=0.30, computed_ms=t)
        seed_game(conn, game="g2", team="Gamma", other="Delta", p=0.55, computed_ms=t)
        conn.commit()

        legs, _ = ladder_candidates(conn, now_ms=t, max_odds_age_ms=900_000)
        alpha = next(l for l in legs if l.team == "Alpha")

        before = build_ladder_payload(conn, now_ms=t, max_odds_age_ms=900_000)
        before_order = [
            leg["ticker"] for card in before["cards"] for leg in card["legs"]
        ]

        conn.execute(
            "INSERT INTO leg_verdicts (ticker, side, ask_tenths, "
            "commence_ms, requested_ms, completed_ms, status, verdict, "
            "reason, model, trigger) VALUES (?, 'yes', 300, ?, ?, ?, "
            "'complete', 'pass', 'A concrete fact.', 'm', 'price_tap')",
            (
                alpha.kalshi_market_ticker, t + 3_600_000, t - 1_000,
                t - 500,
            ),
        )
        conn.commit()

        after = build_ladder_payload(conn, now_ms=t, max_odds_age_ms=900_000)
        after_order = [
            leg["ticker"] for card in after["cards"] for leg in card["legs"]
        ]

        assert after_order == before_order
