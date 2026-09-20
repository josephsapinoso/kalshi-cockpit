"""`backend/scout_watch.py`'s contract: the first thing in this repo that can
spend Anthropic money with nobody tapping anything, so every ceiling REFUSES
rather than degrades. ADR 0180 section 3.1, ticket #112.

No network: the Anthropic client is stubbed, as in `test_scout_desk.py`. The
ladder read (`build_ladder_payload_widening`) is monkeypatched to a canned
payload -- building a real ladder needs a live candidate pool and this file's
job is the watcher's own guards, not the ladder builder's (`test_parlays.py`
and `test_scout_desk.py` own those separately).

What these tests do NOT establish: that a real convening produces a useful
briefing, or that the ladder read itself is correct.
"""

from __future__ import annotations

import backend.scout_watch as scout_watch
from backend.agents.base import AgentConfig
from backend.agents.scout import ScoutReport
from backend.agents.scout_desk import DeskBriefing
from backend.store import db

CONFIG = AgentConfig(
    api_key="test",
    model="claude-opus-5",
    max_calls_per_pass=8,
    max_calls_per_day=24,
    max_searches_per_day=0,
    max_tokens_per_day=0,
)

EMPTY_REPORT = ScoutReport(
    game="A at B", findings=[], summary="Nothing noteworthy.",
    searched_for=["injuries"],
)
BRIEFING = DeskBriefing(
    headline="Quiet game.", assessment="Both scouts filed thin notes.",
)


class StubResponse:
    def __init__(self, parsed=None):
        self.parsed_output = parsed
        self.stop_reason = "end_turn"
        self.stop_details = None


class DeskStubMessages:
    """Answers every structured call with a canned, prose-only result."""

    def __init__(self):
        self.calls = []

    async def parse(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["output_format"] is ScoutReport:
            return StubResponse(EMPTY_REPORT)
        return StubResponse(BRIEFING)


class DeskStubClient:
    def __init__(self):
        self.messages = DeskStubMessages()


def _init_db(tmp_path, name="scout_watch.db"):
    path = tmp_path / name
    conn = db.init_db(path)
    conn.execute(
        "INSERT INTO strategy_configs (version, created_ms, effective_from_ms, "
        "config_json, rationale) VALUES (1, 0, 0, '{}', 'test')"
    )
    conn.commit()
    conn.close()
    return path


def _add_scoutable_fixture(
    conn, *, ticker, event_ticker, odds_event_id, home, away,
    sport="baseball_mlb", commence_ms=2_000_000, link_id,
):
    """A market `_resolve_scout_fixture` can resolve -- the same shape
    `tests/test_scout_api.py`'s `scout_db` fixture builds for one ticker."""
    conn.execute(
        "INSERT INTO kalshi_events (event_ticker, first_seen_ms, last_seen_ms, "
        "title) VALUES (?, 1000, 1000, ?)",
        (event_ticker, f"{away} at {home}"),
    )
    conn.execute(
        "INSERT INTO kalshi_markets (ticker, event_ticker, first_seen_ms, "
        "last_seen_ms) VALUES (?, ?, 1000, 1000)",
        (ticker, event_ticker),
    )
    conn.execute(
        "INSERT INTO event_links (id, kalshi_event_ticker, odds_event_id, "
        "league, method, commence_skew_ms, linked_ms) "
        "VALUES (?, ?, ?, ?, 'exact_alias_pair', 0, 1000)",
        (link_id, event_ticker, odds_event_id, sport),
    )
    conn.execute(
        "INSERT INTO odds_snapshots (fetched_ms, sport_key, odds_event_id, "
        "commence_ms, home_team, away_team, bookmaker, market, outcome_name, "
        "price_decimal) VALUES (1000, ?, ?, ?, ?, ?, 'pinnacle', 'h2h', ?, 1.9)",
        (sport, odds_event_id, commence_ms, home, away, home),
    )
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


def _add_briefing(conn, *, ticker, status, requested_ms, trigger="auto"):
    conn.execute(
        "INSERT INTO scout_briefings (ticker, event_title, league, "
        "home_team, away_team, commence_ms, requested_ms, completed_ms, "
        "status, model, trigger) "
        "VALUES (?, 'A at B', 'baseball_mlb', 'B', 'A', 2000000, ?, ?, "
        "?, 'claude-opus-5', ?)",
        (ticker, requested_ms, requested_ms + 1000, status, trigger),
    )
    conn.commit()


def _ladder_payload(*legs):
    """A minimal payload shaped like `serialise_ladder`'s output: one card,
    the given legs (each a `(ticker, event_ticker, commence_ms)` triple)."""
    return {
        "cards": [
            {
                "not_built_reason": None,
                "legs": [
                    {
                        "ticker": ticker,
                        "event_ticker": event_ticker,
                        "commence_ms": commence_ms,
                    }
                    for ticker, event_ticker, commence_ms in legs
                ],
            }
        ]
    }


NOW_MS = 10_000_000_000  # comfortably inside one UTC day, any hour


class TestTheWatcherSpendsNothingUnlessAsked:
    async def test_flag_off_makes_zero_calls(self, tmp_path, monkeypatch):
        path = _init_db(tmp_path)

        # Tracked with lists rather than raised: the cycle body is wrapped in
        # a broad swallow-and-log (`TestTheTaskSurvives` below is the guard
        # for that), so an `AssertionError` raised from inside a stubbed
        # factory would be caught and logged rather than failing the test --
        # a call must be OBSERVED, never merely presumed fatal.
        config_calls = []
        client_calls = []
        ladder_calls = []

        def tracked_config():
            config_calls.append(True)
            return CONFIG

        def tracked_client(cfg):
            client_calls.append(cfg)
            return DeskStubClient()

        monkeypatch.setattr(
            scout_watch, "build_ladder_payload_widening",
            lambda *a, **k: ladder_calls.append(True) or _ladder_payload(),
        )

        slept = []

        async def sleep(seconds):
            slept.append(seconds)

        await scout_watch.watch_scouts_forever(
            path, tracked_config, tracked_client,
            refresh_hours=6, max_per_day=3, reserve_taps=2, enabled=False,
            sleep=sleep, clock=lambda: NOW_MS / 1000, max_cycles=2,
        )
        assert slept == [scout_watch.DEFAULT_INTERVAL_S] * 2
        assert config_calls == []
        assert client_calls == []
        assert ladder_calls == []

        conn = db.connect(path)
        try:
            n = conn.execute(
                "SELECT COUNT(*) AS c FROM scout_briefings"
            ).fetchone()["c"]
        finally:
            conn.close()
        assert n == 0


class TestTheAllowance:
    async def test_refuses_at_the_daily_allowance(self, tmp_path, monkeypatch):
        path = _init_db(tmp_path)
        conn = db.connect(path)
        try:
            _add_scoutable_fixture(
                conn, ticker="KXA", event_ticker="EVA", odds_event_id="odds-a",
                home="B", away="A", link_id=1,
            )
            # The allowance is already spent for today.
            _add_briefing(conn, ticker="KXA", status="complete", requested_ms=NOW_MS - 1000)
        finally:
            conn.close()

        monkeypatch.setattr(
            scout_watch, "build_ladder_payload_widening",
            lambda *a, **k: _ladder_payload(("KXA", "EVA", NOW_MS + 1_000_000)),
        )

        slept = []

        async def sleep(seconds):
            slept.append(seconds)

        await scout_watch.watch_scouts_forever(
            path, lambda: CONFIG, lambda cfg: DeskStubClient(),
            refresh_hours=0, max_per_day=1, reserve_taps=0, enabled=True,
            sleep=sleep, clock=lambda: NOW_MS / 1000, max_cycles=1,
        )

        conn = db.connect(path)
        try:
            n = conn.execute(
                "SELECT COUNT(*) AS c FROM scout_briefings WHERE trigger = 'auto'"
            ).fetchone()["c"]
        finally:
            conn.close()
        # Still exactly the one already-recorded auto convening: today's
        # allowance was already spent and nothing new was written.
        assert n == 1

    async def test_leaves_the_tap_reserve(self, tmp_path, monkeypatch):
        path = _init_db(tmp_path)
        conn = db.connect(path)
        try:
            _add_scoutable_fixture(
                conn, ticker="KXA", event_ticker="EVA", odds_event_id="odds-a",
                home="B", away="A", link_id=1,
            )
        finally:
            conn.close()

        monkeypatch.setattr(
            scout_watch, "build_ladder_payload_widening",
            lambda *a, **k: _ladder_payload(("KXA", "EVA", NOW_MS + 1_000_000)),
        )

        # Daily budget affords exactly one convening's 2 calls, never a
        # convening PLUS `reserve_taps` more taps of 2 calls each.
        tight_config = AgentConfig(
            api_key="test", model="claude-opus-5",
            max_calls_per_pass=8, max_calls_per_day=3,
            max_searches_per_day=0, max_tokens_per_day=0,
        )

        slept = []

        async def sleep(seconds):
            slept.append(seconds)

        await scout_watch.watch_scouts_forever(
            path, lambda: tight_config, lambda cfg: DeskStubClient(),
            refresh_hours=0, max_per_day=3, reserve_taps=2, enabled=True,
            sleep=sleep, clock=lambda: NOW_MS / 1000, max_cycles=1,
        )

        conn = db.connect(path)
        try:
            n = conn.execute(
                "SELECT COUNT(*) AS c FROM scout_briefings"
            ).fetchone()["c"]
        finally:
            conn.close()
        assert n == 0


class TestWhichFixtures:
    async def test_skips_a_fixture_with_a_fresh_briefing(self, tmp_path, monkeypatch):
        path = _init_db(tmp_path)
        conn = db.connect(path)
        try:
            # A: sooner kickoff, but a FRESH briefing already exists.
            _add_scoutable_fixture(
                conn, ticker="KXA", event_ticker="EVA", odds_event_id="odds-a",
                home="B", away="A", link_id=1, commence_ms=NOW_MS + 1_000_000,
            )
            _add_briefing(
                conn, ticker="KXA", status="complete", requested_ms=NOW_MS - 1000,
                trigger="tap",
            )
            # B: later kickoff, never scouted.
            _add_scoutable_fixture(
                conn, ticker="KXB", event_ticker="EVB", odds_event_id="odds-b",
                home="D", away="C", link_id=2, commence_ms=NOW_MS + 2_000_000,
            )
        finally:
            conn.close()

        monkeypatch.setattr(
            scout_watch, "build_ladder_payload_widening",
            lambda *a, **k: _ladder_payload(
                ("KXA", "EVA", NOW_MS + 1_000_000),
                ("KXB", "EVB", NOW_MS + 2_000_000),
            ),
        )

        slept = []

        async def sleep(seconds):
            slept.append(seconds)

        await scout_watch.watch_scouts_forever(
            path, lambda: CONFIG, lambda cfg: DeskStubClient(),
            refresh_hours=6, max_per_day=3, reserve_taps=0, enabled=True,
            sleep=sleep, clock=lambda: NOW_MS / 1000, max_cycles=1,
        )

        conn = db.connect(path)
        try:
            rows = conn.execute(
                "SELECT ticker, trigger FROM scout_briefings "
                "WHERE trigger = 'auto' ORDER BY id"
            ).fetchall()
        finally:
            conn.close()
        assert [r["ticker"] for r in rows] == ["KXB"]

    async def test_kickoff_soonest_first(self, tmp_path, monkeypatch):
        path = _init_db(tmp_path)
        conn = db.connect(path)
        try:
            # B kicks off sooner than A, but appears second in the payload --
            # the watcher must still convene B first.
            _add_scoutable_fixture(
                conn, ticker="KXA", event_ticker="EVA", odds_event_id="odds-a",
                home="B", away="A", link_id=1, commence_ms=NOW_MS + 5_000_000,
            )
            _add_scoutable_fixture(
                conn, ticker="KXB", event_ticker="EVB", odds_event_id="odds-b",
                home="D", away="C", link_id=2, commence_ms=NOW_MS + 1_000_000,
            )
        finally:
            conn.close()

        monkeypatch.setattr(
            scout_watch, "build_ladder_payload_widening",
            lambda *a, **k: _ladder_payload(
                ("KXA", "EVA", NOW_MS + 5_000_000),
                ("KXB", "EVB", NOW_MS + 1_000_000),
            ),
        )

        slept = []

        async def sleep(seconds):
            slept.append(seconds)

        await scout_watch.watch_scouts_forever(
            path, lambda: CONFIG, lambda cfg: DeskStubClient(),
            refresh_hours=6, max_per_day=3, reserve_taps=0, enabled=True,
            sleep=sleep, clock=lambda: NOW_MS / 1000, max_cycles=1,
        )

        conn = db.connect(path)
        try:
            rows = conn.execute(
                "SELECT ticker FROM scout_briefings WHERE trigger = 'auto'"
            ).fetchall()
        finally:
            conn.close()
        assert [r["ticker"] for r in rows] == ["KXB"]


class TestTheTaskSurvives:
    async def test_a_dead_cycle_does_not_end_the_task(self, tmp_path, monkeypatch):
        path = _init_db(tmp_path)

        def exploding_config():
            raise RuntimeError("the environment is unreadable")

        monkeypatch.setattr(
            scout_watch, "build_ladder_payload_widening",
            lambda *a, **k: (_ for _ in ()).throw(
                AssertionError("must not be reached")
            ),
        )

        slept = []

        async def sleep(seconds):
            slept.append(seconds)

        await scout_watch.watch_scouts_forever(
            path, exploding_config, lambda cfg: DeskStubClient(),
            refresh_hours=6, max_per_day=3, reserve_taps=0, enabled=True,
            sleep=sleep, clock=lambda: NOW_MS / 1000, max_cycles=3,
        )
        assert len(slept) == 3
