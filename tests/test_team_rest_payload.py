"""The `rest` block on `/api/parlays` card legs and `POST /api/parlays/check` legs (#201).

What these tests establish: a card leg and a check leg each carry `rest` with
both teams; an unidentifiable leg carries `null`; and the cards' leg ORDER is
identical whether rest is present or absent, so rest is a fact and never a
sort key (ADR 0071 s2.5).

What they do not establish: how the chip renders (the build and the glossary
coverage test cover the screen).
"""

from __future__ import annotations

import sqlite3

from backend import parlay_check, parlays
from backend.store import db as store
from backend.store.db import now_ms
from tests.test_parlay_check import (
    MAX_ODDS_AGE_MS,
    PRICED_BOOK,
    FakeApi,
    _market_payload,
    _mk_ticker,
)
from tests.test_parlay_check import seed_game as seed_check_game
from tests.test_parlays_api import _fresh_slate

import pytest

H = 3_600_000


@pytest.fixture
def conn(tmp_path):
    c = store.init_db(tmp_path / "restpayload.db")
    yield c
    c.close()


def _add_previous_game(conn, game, hours_before, home, away):
    commence = conn.execute(
        "SELECT MIN(commence_ms) AS c FROM odds_snapshots WHERE odds_event_id = ?",
        (game,),
    ).fetchone()["c"]
    conn.execute(
        "INSERT INTO odds_snapshots (fetched_ms, sport_key, odds_event_id, "
        "commence_ms, home_team, away_team, bookmaker, market, outcome_name, "
        "price_decimal) VALUES (?, 'baseball_mlb', ?, ?, ?, ?, 'pinnacle', "
        "'h2h', ?, 1.6)",
        (now_ms(), f"{game}-prev", commence - hours_before * H, home, away, home),
    )


def _payload(conn):
    return parlays.build_ladder_payload(
        conn, now_ms=now_ms(), max_odds_age_ms=MAX_ODDS_AGE_MS
    )


class TestCardLegs:
    def test_every_card_leg_carries_rest_for_both_teams(self, conn):
        _fresh_slate(conn)
        _add_previous_game(conn, "game-0", 24, "Team Alpha0", "Somebody")
        conn.commit()
        legs = [
            leg for card in _payload(conn)["cards"] for leg in card["legs"]
        ]
        assert legs and all("rest" in leg for leg in legs)
        game0 = next(leg for leg in legs if leg["team"] == "Team Alpha0")
        assert game0["rest"]["home"]["team"] == "Team Alpha0"
        assert game0["rest"]["home"]["days_rest"] == 0
        assert game0["rest"]["away"]["team"] == "Team Beta0"
        assert game0["rest"]["away"]["days_rest"] is None

    def test_card_order_is_unchanged_whether_rest_is_present_or_not(
        self, conn, monkeypatch
    ):
        _fresh_slate(conn)
        _add_previous_game(conn, "game-2", 24, "Team Alpha2", "Somebody")
        conn.commit()
        with_rest = _payload(conn)
        monkeypatch.setattr(parlays, "rest_for_games", lambda *a, **k: {})
        without = _payload(conn)

        def order(p):
            return [
                (c["key"], [leg["ticker"] for leg in c["legs"]])
                for c in p["cards"]
            ]

        assert order(with_rest) == order(without)
        assert any(
            leg["rest"] is not None
            for c in with_rest["cards"] for leg in c["legs"]
        )
        assert all(
            leg["rest"] is None for c in without["cards"] for leg in c["legs"]
        )


def _boom(*_a, **_k):
    raise sqlite3.OperationalError("database is locked")


class TestARestReadFailureNeverFailsTheCard:
    def test_the_card_still_builds_with_rest_null(self, conn, monkeypatch):
        _fresh_slate(conn)
        conn.commit()
        monkeypatch.setattr(parlays, "rest_for_games", _boom)
        cards = _payload(conn)["cards"]
        legs = [leg for c in cards for leg in c["legs"]]
        assert legs and all(leg["rest"] is None for leg in legs)

    async def test_the_check_still_answers_with_rest_null(self, conn, monkeypatch):
        base = now_ms() - 30_000
        t1, e1 = seed_check_game(conn, game="bx-a", team="Team BxA",
                                 other="Team BxB", p=0.7, computed_ms=base)
        t2, e2 = seed_check_game(conn, game="bx-b", team="Team BxC",
                                 other="Team BxD", p=0.6, computed_ms=base)
        conn.commit()
        legs = [
            {"event_ticker": e1, "market_ticker": t1, "side": "yes"},
            {"event_ticker": e2, "market_ticker": t2, "side": "yes"},
        ]
        monkeypatch.setattr(parlay_check, "rest_for_games", _boom)
        result = await parlay_check.check_parlay_text(
            conn, text=_mk_ticker("B1"), now_ms=now_ms(),
            api=FakeApi(market_payload=_market_payload(legs),
                        book_payload=PRICED_BOOK),
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert result["status"] == "priced"
        assert all(leg["rest"] is None for leg in result["legs"])


class TestCheckLegs:
    async def test_every_check_leg_carries_rest(self, conn):
        base = now_ms() - 30_000
        t1, e1 = seed_check_game(conn, game="ck-a", team="Team CkA",
                                 other="Team CkB", p=0.7, computed_ms=base)
        t2, e2 = seed_check_game(conn, game="ck-b", team="Team CkC",
                                 other="Team CkD", p=0.6, computed_ms=base)
        _add_previous_game(conn, "ck-a", 24, "Team CkA", "Elsewhere")
        conn.commit()
        legs = [
            {"event_ticker": e1, "market_ticker": t1, "side": "yes"},
            {"event_ticker": e2, "market_ticker": t2, "side": "yes"},
        ]
        api = FakeApi(market_payload=_market_payload(legs),
                      book_payload=PRICED_BOOK)
        result = await parlay_check.check_parlay_text(
            conn, text=_mk_ticker("A1"), now_ms=now_ms(), api=api,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert all("rest" in leg for leg in result["legs"])
        a = next(leg for leg in result["legs"] if leg["market_ticker"] == t1)
        assert a["rest"]["home"]["team"] == "Team CkA"
        assert a["rest"]["home"]["days_rest"] == 0
        b = next(leg for leg in result["legs"] if leg["market_ticker"] == t2)
        assert b["rest"]["home"]["days_rest"] is None
