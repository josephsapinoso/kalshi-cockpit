"""The game-script watcher's decision (#217): pure, plus one adapter read."""

from __future__ import annotations

import ast
from pathlib import Path

from backend import game_script_watch as gsw
from backend.game_script_watch import (
    BUILD, CARD_SEARCHES, CARD_TOKEN_ESTIMATE, REFUSED_BUDGET, Fixture, WatchBudget, decide,
)

H = 3_600_000
NOW = 1_000_000_000_000


def fx(ticker, hours, sport="americanfootball_nfl"):
    return Fixture(ticker, sport, NOW + int(hours * H))


def roomy(**kw):
    base = dict(tokens_today=0, tokens_ceiling=10_000_000, searches_today=0,
                searches_ceiling=1000)
    base.update(kw)
    return WatchBudget(**base)


class TestWhichGames:
    def test_soonest_kickoff_first(self):
        acts = decide(NOW, [fx("C", 20), fx("A", 2), fx("B", 9)], [], roomy())
        assert [a.game_event_ticker for a in acts] == ["A", "B", "C"]
        assert {a.kind for a in acts} == {BUILD}

    def test_outside_the_lead_window_or_started_is_not_chosen(self):
        acts = decide(NOW, [fx("far", 25), fx("gone", -1), fx("in", 5)], [], roomy(),
                      lead_hours=24)
        assert [a.game_event_ticker for a in acts] == ["in"]

    def test_built_or_skipped_card_is_skipped_refusal_is_not(self):
        cards = [
            {"game_event_ticker": "B", "status": "built"},
            {"game_event_ticker": "S", "status": "skipped"},
            {"game_event_ticker": "R1", "status": "refused_budget"},
            {"game_event_ticker": "R2", "status": "refused_invalid"},
        ]
        fixtures = [fx("B", 1), fx("S", 2), fx("R1", 3), fx("R2", 4), fx("N", 5)]
        acts = decide(NOW, fixtures, cards, roomy())
        assert [a.game_event_ticker for a in acts] == ["R1", "R2", "N"]

    def test_unlinked_fixture_is_skipped_not_guessed(self):
        acts = decide(NOW, [fx(None, 1), fx("A", 2)], [], roomy())
        assert [a.game_event_ticker for a in acts] == ["A"]

    def test_only_joes_sports(self):
        acts = decide(NOW, [fx("A", 1, "soccer_epl"), fx("B", 2)], [], roomy(),
                      sports=["americanfootball_nfl"])
        assert [a.game_event_ticker for a in acts] == ["B"]


class TestTheCeilings:
    def test_token_share_stops_it_and_names_the_ceiling(self):
        # ceiling 1,000,000, tap share 0.5 -> unattended line 500,000: room for
        # floor(500,000 / 60,000) = 8 cards from an empty day.
        b = roomy(tokens_ceiling=1_000_000)
        fixtures = [fx(f"G{i:02d}", i + 1) for i in range(10)]
        acts = decide(NOW, fixtures, [], b)
        room = 500_000 // CARD_TOKEN_ESTIMATE
        assert [a.kind for a in acts] == [BUILD] * room + [REFUSED_BUDGET] * (10 - room)
        refused = acts[room:]
        assert all("AGENT_MAX_TOKENS_PER_DAY" in a.reason
                   and "SCOUT_AUTO_TAP_TOKEN_SHARE" in a.reason for a in refused)
        assert [a.game_event_ticker for a in refused] == [f"G{i:02d}" for i in range(room, 10)]

    def test_todays_recorded_tokens_count_against_the_share(self):
        b = roomy(tokens_ceiling=1_000_000, tokens_today=490_000)
        acts = decide(NOW, [fx("A", 1)], [], b)
        assert acts[0].kind == REFUSED_BUDGET

    def test_search_cap_also_stops_it(self):
        b = roomy(searches_ceiling=2 * CARD_SEARCHES + 1, searches_today=0)
        acts = decide(NOW, [fx("A", 1), fx("B", 2), fx("C", 3)], [], b)
        assert [a.kind for a in acts] == [BUILD, BUILD, REFUSED_BUDGET]
        assert "AGENT_MAX_SEARCHES_PER_DAY" in acts[2].reason

    def test_a_binding_ceiling_refuses_every_later_game(self):
        b = roomy(searches_ceiling=CARD_SEARCHES)
        acts = decide(NOW, [fx("A", 1), fx("B", 2), fx("C", 3)], [], b)
        assert [a.kind for a in acts] == [BUILD, REFUSED_BUDGET, REFUSED_BUDGET]


class TestNothingConvenes:
    def test_module_imports_nothing_from_the_scout_desk(self):
        tree = ast.parse(Path(gsw.__file__).read_text(encoding="utf-8"))
        names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                names.append((node.module or "") + " " + " ".join(a.name for a in node.names))
            elif isinstance(node, ast.Import):
                names += [a.name for a in node.names]
        for n in names:
            assert "scout_desk" not in n and "scout_watch" not in n, n


class TestAdapter:
    def _db(self, tmp_path):
        from backend.store import db
        return db.init_db(tmp_path / "t.db")

    def test_link_goes_through_event_links_to_the_game_event_only(self, tmp_path):
        conn = self._db(tmp_path)
        try:
            soon = NOW + 5 * H
            for i, (ev, sport) in enumerate([("f1", "americanfootball_nfl"),
                                             ("f2", "americanfootball_nfl"),
                                             ("f3", "soccer_epl")]):
                conn.execute(
                    "INSERT INTO odds_fixtures (odds_event_id, sport_key, commence_ms, "
                    "last_fetched_ms) VALUES (?, ?, ?, ?)", (ev, sport, soon + i, NOW))
            for t in ("KXNFLGAME-26OCT04ARINYG", "KXNFLSPREAD-26OCT04ARINYG"):
                conn.execute(
                    "INSERT INTO kalshi_events (event_ticker, first_seen_ms, last_seen_ms) "
                    "VALUES (?, 0, 0)", (t,))
                conn.execute(
                    "INSERT INTO event_links (kalshi_event_ticker, odds_event_id, league, "
                    "method, commence_skew_ms, linked_ms) VALUES (?, 'f1', 'NFL', "
                    "'exact_alias_pair', 0, 0)", (t,))
            conn.commit()
            fixtures, cards = gsw.load_inputs(conn, NOW, 24)
            assert [(f.game_event_ticker, f.sport_key) for f in fixtures] == [
                ("KXNFLGAME-26OCT04ARINYG", "nfl")]  # the card's form, not the feed's
            assert cards == []
        finally:
            conn.close()

    def test_refusals_are_written_once_per_budget_day(self, tmp_path):
        conn = self._db(tmp_path)
        try:
            acts = decide(NOW, [fx("KXNFLGAME-X", 1)], [], roomy(searches_ceiling=1))
            assert gsw.record_refusals(conn, acts, NOW, NOW - H) == 1
            assert gsw.record_refusals(conn, acts, NOW + 1000, NOW - H) == 0
            assert gsw.record_refusals(conn, acts, NOW + 2 * 24 * H, NOW + 24 * H) == 1
        finally:
            conn.close()


class TestTheLoop:
    """S3b: the loop `scripts/run_loop.py` starts, behind the flag."""

    def _seed(self, conn, tickers_hours):
        for i, (ticker, hours) in enumerate(tickers_hours):
            ev = f"f{i}"
            conn.execute(
                "INSERT INTO odds_fixtures (odds_event_id, sport_key, commence_ms, "
                "last_fetched_ms) VALUES (?, 'americanfootball_nfl', ?, ?)",
                (ev, NOW + int(hours * H), NOW))
            conn.execute(
                "INSERT INTO kalshi_events (event_ticker, first_seen_ms, last_seen_ms) "
                "VALUES (?, 0, 0)", (ticker,))
            conn.execute(
                "INSERT INTO event_links (kalshi_event_ticker, odds_event_id, league, "
                "method, commence_skew_ms, linked_ms) VALUES (?, ?, 'NFL', "
                "'exact_alias_pair', 0, 0)", (ticker, ev))
        conn.commit()

    def _config(self):
        from backend.agents.base import AgentConfig
        return AgentConfig(api_key="k", max_tokens_per_day=10_000_000,
                           max_searches_per_day=1000)

    async def test_disabled_reads_nothing_and_builds_nothing(self, tmp_path):
        from backend.store import db
        db.init_db(tmp_path / "t.db").close()
        calls = []

        def factory():
            calls.append("config")
            return self._config()

        async def build(ticker, cfg):
            calls.append(ticker)
            return {}

        async def no_sleep(_):
            return None

        await gsw.watch_game_scripts_forever(
            tmp_path / "t.db", factory, build, enabled=False, lead_hours=24,
            sleep=no_sleep, clock=lambda: NOW / 1000, max_cycles=3)
        assert calls == []

    async def test_enabled_builds_each_game_soonest_first_through_the_one_path(self, tmp_path):
        from backend.store import db
        conn = db.init_db(tmp_path / "t.db")
        self._seed(conn, [("KXNFLGAME-26OCT04C", 20), ("KXNFLGAME-26OCT04A", 2),
                          ("KXNFLGAME-26OCT04B", 9)])
        conn.close()
        built = []

        async def build(ticker, cfg):
            built.append(ticker)
            return {}

        async def no_sleep(_):
            return None

        await gsw.watch_game_scripts_forever(
            tmp_path / "t.db", self._config, build, enabled=True, lead_hours=24,
            sleep=no_sleep, clock=lambda: NOW / 1000, max_cycles=1)
        assert built == ["KXNFLGAME-26OCT04A", "KXNFLGAME-26OCT04B", "KXNFLGAME-26OCT04C"]

    async def test_one_failed_build_does_not_stop_the_next(self, tmp_path):
        from backend.store import db
        conn = db.init_db(tmp_path / "t.db")
        self._seed(conn, [("KXNFLGAME-26OCT04A", 2), ("KXNFLGAME-26OCT04B", 9)])
        built = []

        async def build(ticker):
            if ticker.endswith("A"):
                raise RuntimeError("venue refused")
            built.append(ticker)
            return {}

        try:
            counts = await gsw.run_pass(conn, self._config(), build, now_ms=NOW,
                                        lead_hours=24, tap_token_share=0.5)
        finally:
            conn.close()
        assert built == ["KXNFLGAME-26OCT04B"]
        assert counts["failed"] == 1 and counts["built"] == 1

    async def test_no_api_key_builds_nothing(self, tmp_path):
        from backend.store import db
        conn = db.init_db(tmp_path / "t.db")
        self._seed(conn, [("KXNFLGAME-26OCT04A", 2)])
        conn.close()
        built = []

        async def build(ticker, cfg):
            built.append(ticker)
            return {}

        async def no_sleep(_):
            return None

        await gsw.watch_game_scripts_forever(
            tmp_path / "t.db", lambda: None, build, enabled=True, lead_hours=24,
            sleep=no_sleep, clock=lambda: NOW / 1000, max_cycles=1)
        assert built == []


    async def test_the_real_token_ceiling_stops_it_and_the_refusal_is_a_row(self, tmp_path):
        """Through `AgentBudget.from_config`, not a hand-built WatchBudget: a
        ceiling whose unattended half is below one card builds nothing."""
        from backend.agents.base import AgentConfig
        from backend.store import db
        conn = db.init_db(tmp_path / "t.db")
        self._seed(conn, [("KXNFLGAME-26OCT04A", 2)])
        built = []

        async def build(ticker):
            built.append(ticker)
            return {}

        cfg = AgentConfig(api_key="k", max_tokens_per_day=100_000,
                          max_searches_per_day=1000)
        try:
            counts = await gsw.run_pass(conn, cfg, build, now_ms=NOW,
                                        lead_hours=24, tap_token_share=0.5)
            rows = conn.execute(
                "SELECT status, reason FROM game_script_cards").fetchall()
        finally:
            conn.close()
        assert built == []
        assert counts["refused_written"] == 1
        assert [r["status"] for r in rows] == ["refused_budget"]
        assert "AGENT_MAX_TOKENS_PER_DAY" in rows[0]["reason"]


class TestTheRunnerStartsIt:
    def test_run_loop_starts_the_watcher_behind_the_flag(self):
        src = Path("scripts/run_loop.py").read_text(encoding="utf-8")
        assert "watch_game_scripts_forever(" in src
        assert "enabled=game_script_config.enabled" in src
        assert "build_card_for_game(" in src
        assert "game_script_task.cancel()" in src
