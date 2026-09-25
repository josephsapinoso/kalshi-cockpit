"""A leg's scout state is read by GAME, not by the series its event sits in
(#150).

A Kalshi event ticker carries its series: `KXWNBAGAME-26SEP24CHIWSH` and
`KXWNBASPREAD-26SEP24CHIWSH` are one game. `parlays._leg_scouting` matched on
`event_ticker`, so a spread or total leg could not see a briefing filed on
the game's moneyline. On live, 2026-09-24, `leg-scout-join` found 2 of 39
legs recorded `absent` while their game had been briefed before the bet.

What this establishes
---------------------
- A spread leg sees a briefing filed on the same game's moneyline, in the
  same Kalshi league.
- A game in another league with the same date-and-teams string does not
  count.
- A series with no mapped league gets only the exact-event match: it
  refuses rather than guessing.
- `scouting_facts` (the reader the cards, the bet-time recorder and the
  watcher share) reports the game as briefed.

What this does not establish
----------------------------
- That the other 34 of 39 legs were scouted. They were not: the live read
  found no briefing on those games at any time.
"""

from __future__ import annotations

import json

from backend import parlays
from backend.store import db

NOW = 1_790_000_000_000
KICKOFF = NOW + 6 * 3_600_000
GAME_EVENT = "KXWNBAGAME-26SEP24CHIWSH"
SPREAD_EVENT = "KXWNBASPREAD-26SEP24CHIWSH"
GAME = GAME_EVENT + "-WSH"
SPREAD = SPREAD_EVENT + "-WSH5"
NFL_EVENT = "KXNFLGAME-26SEP24CHIWSH"
NFL_GAME = NFL_EVENT + "-WSH"


def _market(conn, ticker, event, series, league):
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_series (series_ticker, league, "
        "has_game_markets, first_seen_ms, last_seen_ms) VALUES (?, ?, 1, 0, 0)",
        (series, league),
    )
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_events (event_ticker, series_ticker, title, "
        "category, commence_ms, status, first_seen_ms, last_seen_ms) "
        "VALUES (?, ?, 't', 'Sports', ?, 'open', 0, 0)",
        (event, series, KICKOFF),
    )
    conn.execute(
        "INSERT INTO kalshi_markets (ticker, event_ticker, series_ticker, status, "
        "first_seen_ms, last_seen_ms) VALUES (?, ?, ?, 'active', 0, 0)",
        (ticker, event, series),
    )


def _brief(conn, ticker):
    conn.execute(
        "INSERT INTO scout_briefings (ticker, event_title, league, home_team, "
        "away_team, commence_ms, requested_ms, completed_ms, status, model, "
        "briefing_json) VALUES (?, 'Chicago vs Washington', 'basketball_wnba', "
        "'Washington', 'Chicago', ?, ?, ?, 'complete', 'm', ?)",
        (ticker, KICKOFF, NOW - 60_000, NOW - 30_000,
         json.dumps({"headline": "Nothing changes the number."})),
    )


def _conn(tmp_path, *, spread_league="Pro Basketball (W)"):
    conn = db.init_db(tmp_path / "leg_scouting.db")
    _market(conn, GAME, GAME_EVENT, "KXWNBAGAME", "Pro Basketball (W)")
    _market(conn, SPREAD, SPREAD_EVENT, "KXWNBASPREAD", spread_league)
    _market(conn, NFL_GAME, NFL_EVENT, "KXNFLGAME", "Pro Football")
    return conn


class TestTheSameGameAcrossSeries:
    def test_a_spread_leg_sees_the_moneyline_briefing(self, tmp_path):
        conn = _conn(tmp_path)
        _brief(conn, GAME)
        rows = parlays._leg_scouting(conn, [SPREAD])
        assert SPREAD in rows
        assert rows[SPREAD]["scout_ticker"] == GAME

    def test_scouting_facts_reports_the_game_as_briefed(self, tmp_path):
        conn = _conn(tmp_path)
        _brief(conn, GAME)
        facts = parlays.scouting_facts(conn, [SPREAD], now_ms=NOW)
        assert facts[SPREAD]["scout"] != "absent"

    def test_the_exact_event_still_matches(self, tmp_path):
        conn = _conn(tmp_path)
        _brief(conn, GAME)
        assert GAME in parlays._leg_scouting(conn, [GAME])


class TestItDoesNotGuess:
    def test_another_league_with_the_same_string_is_not_the_game(self, tmp_path):
        conn = _conn(tmp_path)
        _brief(conn, NFL_GAME)
        assert SPREAD not in parlays._leg_scouting(conn, [SPREAD])

    def test_an_unmapped_league_gets_only_the_exact_event(self, tmp_path):
        conn = _conn(tmp_path, spread_league=None)
        _brief(conn, GAME)
        assert SPREAD not in parlays._leg_scouting(conn, [SPREAD])
