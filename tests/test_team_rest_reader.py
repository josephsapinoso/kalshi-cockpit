"""`backend/team_rest_reader.py` -- previous game per team, off `odds_snapshots` (#201).

What these tests establish: the window query is served by the covering index
`idx_odds_sport_commence` and never scans `odds_snapshots` (pattern:
`tests/test_candidate_scan_plan.py`); on a synthetic multi-sport table each
team gets ITS previous game, other sports' rows never leak in, a team with no
row in the 16-day window is unknown rather than rested, and a game's own
earlier (rescheduled) start is not its previous game.

What they do not establish: plan shape on the live 10M-row table (the plan
test seeds a few thousand rows and runs ANALYZE, as the scan-plan test does).
"""

from __future__ import annotations

import pytest

from backend import team_rest_reader as reader
from backend.store import db

H = 3_600_000
D = 24 * H
T0 = 1_768_431_600_000


def _row(conn, sport, event, commence, home, away):
    conn.execute(
        "INSERT INTO odds_snapshots (fetched_ms, book_updated_ms, sport_key, "
        "odds_event_id, commence_ms, home_team, away_team, bookmaker, market, "
        "outcome_name, outcome_description, outcome_point, price_decimal) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (T0, T0, sport, event, commence, home, away, "pinnacle", "h2h", home,
         None, None, 1.9),
    )


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "rest.db")
    yield c
    c.close()


class TestPlan:
    def _seed_bulk(self, conn):
        for sport in ("basketball_nba", "baseball_mlb", "icehockey_nhl",
                      "americanfootball_nfl"):
            for i in range(600):
                _row(conn, sport, f"{sport}-{i}", T0 + (i % 60) * D // 4,
                     f"H{i % 30}", f"A{i % 30}")
        conn.commit()
        conn.execute("ANALYZE")
        conn.commit()

    def _plan(self, conn, sql=reader.WINDOW_SQL):
        rows = conn.execute(
            "EXPLAIN QUERY PLAN " + sql, ("basketball_nba", T0, T0 + 10 * D)
        ).fetchall()
        return " | ".join(r[3] for r in rows)

    def test_the_window_query_uses_the_covering_sport_commence_index(self, conn):
        self._seed_bulk(conn)
        plan = self._plan(conn)
        assert "idx_odds_sport_commence" in plan, plan
        assert "SCAN odds_snapshots" not in plan, plan

    def test_the_seek_names_the_sport_key_and_the_lower_bound(self, conn):
        self._seed_bulk(conn)
        plan = self._plan(conn).replace(" ", "")
        assert "sport_key=?" in plan, plan
        assert "commence_ms>?" in plan, plan


class TestPreviousGamePerTeam:
    def _seed(self, conn):
        # NBA: Lakers played Celtics 1 day before; Knicks last played 5 days
        # before; Nets have nothing in the window at all.
        _row(conn, "basketball_nba", "n1", T0 - 1 * D, "Lakers", "Celtics")
        _row(conn, "basketball_nba", "n2", T0 - 5 * D, "Knicks", "Heat")
        _row(conn, "basketball_nba", "n2b", T0 - 3 * D, "Heat", "Suns")
        _row(conn, "basketball_nba", "n0", T0, "Lakers", "Knicks")
        _row(conn, "basketball_nba", "n9", T0, "Nets", "Bulls")
        # A different sport under the same team name must not leak in.
        _row(conn, "icehockey_nhl", "h1", T0 - 1 * D, "Nets", "Bulls")
        # Outside the 16-day window.
        _row(conn, "basketball_nba", "old", T0 - 40 * D, "Nets", "Bulls")
        conn.commit()

    def test_each_team_gets_its_own_latest_previous_game(self, conn):
        self._seed(conn)
        out = reader.rest_for_games(conn, [("n0", T0)])["n0"]
        assert out["home"]["team"] == "Lakers"
        assert out["home"]["days_rest"] == 0
        assert out["home"]["back_to_back"] is True
        assert out["away"]["team"] == "Knicks"
        assert out["away"]["days_rest"] == 4
        assert out["away"]["back_to_back"] is False

    def test_no_row_in_the_window_is_unknown_not_rested(self, conn):
        self._seed(conn)
        out = reader.rest_for_games(conn, [("n9", T0)])["n9"]
        for side in ("home", "away"):
            assert out[side]["days_rest"] is None
            assert out[side]["back_to_back"] is None
            assert out[side]["short_week"] is None

    def test_a_game_that_cannot_be_identified_is_null(self, conn):
        self._seed(conn)
        assert reader.rest_for_games(conn, [("no-such-game", T0)]) == {
            "no-such-game": None
        }
        assert reader.rest_for_games(conn, [("n0", None)]) == {"n0": None}

    def test_its_own_rescheduled_start_is_not_a_previous_game(self, conn):
        _row(conn, "basketball_nba", "r1", T0 - 20 * H, "Kings", "Jazz")
        _row(conn, "basketball_nba", "r1", T0, "Kings", "Jazz")
        conn.commit()
        out = reader.rest_for_games(conn, [("r1", T0)])["r1"]
        assert out["home"]["days_rest"] is None

    def test_several_sports_are_answered_in_one_call(self, conn):
        self._seed(conn)
        out = reader.rest_for_games(conn, [("n0", T0), ("h1", T0 - 1 * D)])
        assert out["n0"] is not None and out["h1"] is not None
