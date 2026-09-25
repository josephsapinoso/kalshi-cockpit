"""`leg-scout-join`: the bet-time scout join, beside a same-game count that
ignores the series.

The reading that prompted it: `leg-scout-state` found 0 of 39 legs briefed
(2026-09-24). `parlays._leg_scouting` joins a leg to a briefing through
`kalshi_markets.event_ticker`, and a Kalshi event ticker carries its series,
so a points prop (`KXWNBAPTS-26SEP24CHIWSH`) and the moneyline it shares a
game with (`KXWNBAGAME-26SEP24CHIWSH`) are different events. This query
shows, on the box, whether that is what produced the zero.

What these tests establish
--------------------------
- A prop leg whose game was briefed on the moneyline counts 0 through the
  join and 1 as the same game. That is the defect's signature.
- A moneyline leg on a briefed game counts 1 both ways.
- A briefing filed after the bet counts only in `game_briefs_any_time`.
- A game in another sport with the same date-and-teams string, kicking off
  days away, is not the same game.
- No ticker is printed, and the query is CHEAP.

What these tests do not establish
---------------------------------
- Anything about live. The rows are seeded against the real schema.
"""

from __future__ import annotations

from backend.store import db
from scripts.inspect_live_db import CHEAP, QUERIES

SINCE = 1_789_984_800_000  # 2026-09-21T10:00Z, the query's bound
HOUR = 3_600_000
KICKOFF = SINCE + 3 * 24 * HOUR
GAME = "KXWNBAGAME-26SEP24CHIWSH-WSH"
PROP = "KXWNBAPTS-26SEP24CHIWSH-CHIKCARDOSO10-15"


def _args():
    class A:
        limit = 100
        tail = 5
        day_start_hour = 10

    return A()


def _db(tmp_path):
    path = tmp_path / "leg_scout_join.db"
    conn = db.init_db(path)
    for event, series in (
        ("KXWNBAGAME-26SEP24CHIWSH", "KXWNBAGAME"),
        ("KXWNBAPTS-26SEP24CHIWSH", "KXWNBAPTS"),
    ):
        conn.execute(
            "INSERT INTO kalshi_series (series_ticker, league, has_game_markets, "
            "first_seen_ms, last_seen_ms) VALUES (?, 'basketball_wnba', 1, 0, 0)",
            (series,),
        )
        conn.execute(
            "INSERT INTO kalshi_events (event_ticker, series_ticker, title, category, "
            "commence_ms, status, first_seen_ms, last_seen_ms) "
            "VALUES (?, ?, 't', 'Sports', ?, 'open', 0, 0)",
            (event, series, KICKOFF),
        )
    conn.execute(
        "INSERT INTO kalshi_markets (ticker, event_ticker, series_ticker, status, "
        "first_seen_ms, last_seen_ms) VALUES (?, ?, ?, 'active', 0, 0)",
        (GAME, "KXWNBAGAME-26SEP24CHIWSH", "KXWNBAGAME"),
    )
    conn.execute(
        "INSERT INTO kalshi_markets (ticker, event_ticker, series_ticker, status, "
        "first_seen_ms, last_seen_ms) VALUES (?, ?, ?, 'active', 0, 0)",
        (PROP, "KXWNBAPTS-26SEP24CHIWSH", "KXWNBAPTS"),
    )
    conn.commit()
    return conn, path


def _brief(conn, ticker, *, requested_ms, commence_ms=KICKOFF):
    conn.execute(
        "INSERT INTO scout_briefings (ticker, event_title, league, home_team, "
        "away_team, commence_ms, requested_ms, completed_ms, status, model) "
        "VALUES (?, 't', 'basketball_wnba', 'h', 'a', ?, ?, ?, 'complete', 'm')",
        (ticker, commence_ms, requested_ms, requested_ms + 60_000),
    )


def _bet(conn, ticker, *, created_ms, commence_ms=KICKOFF):
    pid = conn.execute(
        "INSERT INTO parlay_positions (created_ms, source, label, stake_tenths, "
        "return_tenths, status) VALUES (?, 'kalshi_combo', 'x', 1000, 2000, 'open')",
        (created_ms,),
    ).lastrowid
    conn.execute(
        "INSERT INTO parlay_position_legs (position_id, leg_index, side, label, "
        "outcome, ticker, commence_ms, scout_state) "
        "VALUES (?, 0, 'yes', 'x', 'pending', ?, ?, 'absent')",
        (pid, ticker, commence_ms),
    )


def _rows(conn, path):
    conn.commit()
    conn.close()
    reader = db.connect(path)
    try:
        section = QUERIES["leg-scout-join"].run(reader, _args())[0]
    finally:
        reader.close()
    return section, [dict(zip(section.columns, r)) for r in section.rows]


class TestTheJoinAgainstTheGame:
    def test_a_prop_leg_on_a_briefed_game_is_invisible_to_the_join(self, tmp_path):
        conn, path = _db(tmp_path)
        _brief(conn, GAME, requested_ms=SINCE + HOUR)
        _bet(conn, PROP, created_ms=SINCE + 2 * HOUR)
        _, rows = _rows(conn, path)
        (row,) = rows
        assert row["leg_series"] == "KXWNBAPTS"
        assert row["leg_in_markets"] == 1
        assert row["join_briefs_before_bet"] == 0
        assert row["game_briefs_before_bet"] == 1

    def test_a_moneyline_leg_on_a_briefed_game_counts_both_ways(self, tmp_path):
        conn, path = _db(tmp_path)
        _brief(conn, GAME, requested_ms=SINCE + HOUR)
        _bet(conn, GAME, created_ms=SINCE + 2 * HOUR)
        _, rows = _rows(conn, path)
        (row,) = rows
        assert row["join_briefs_before_bet"] == 1
        assert row["game_briefs_before_bet"] == 1

    def test_a_briefing_after_the_bet_counts_only_as_any_time(self, tmp_path):
        conn, path = _db(tmp_path)
        _bet(conn, GAME, created_ms=SINCE + HOUR)
        _brief(conn, GAME, requested_ms=SINCE + 2 * HOUR)
        _, rows = _rows(conn, path)
        (row,) = rows
        assert row["join_briefs_before_bet"] == 0
        assert row["game_briefs_before_bet"] == 0
        assert row["game_briefs_any_time"] == 1

    def test_the_same_string_days_apart_is_not_the_same_game(self, tmp_path):
        conn, path = _db(tmp_path)
        _brief(
            conn, "KXNFLGAME-26SEP24CHIWSH-WSH",
            requested_ms=SINCE + HOUR, commence_ms=KICKOFF + 48 * HOUR,
        )
        _bet(conn, PROP, created_ms=SINCE + 2 * HOUR)
        _, rows = _rows(conn, path)
        assert rows[0]["game_briefs_before_bet"] == 0


class TestTheReadIsSafe:
    def test_no_ticker_is_printed(self, tmp_path):
        conn, path = _db(tmp_path)
        _brief(conn, GAME, requested_ms=SINCE + HOUR)
        _bet(conn, PROP, created_ms=SINCE + 2 * HOUR)
        section, _ = _rows(conn, path)
        assert "ticker" not in section.columns
        flat = " ".join(str(v) for r in section.rows for v in r)
        assert "26SEP24CHIWSH" not in flat

    def test_a_bet_before_the_bound_is_excluded(self, tmp_path):
        conn, path = _db(tmp_path)
        _bet(conn, PROP, created_ms=SINCE - HOUR)
        _, rows = _rows(conn, path)
        assert rows == []

    def test_it_is_cheap(self):
        assert QUERIES["leg-scout-join"].cost == CHEAP
