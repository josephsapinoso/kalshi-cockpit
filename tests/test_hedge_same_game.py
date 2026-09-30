"""Legs of one fixture are same-game even under different event tickers (#229).

What this establishes: `hedge.assess` refuses a de-risk joint when the legs are
a GAME leg, a SPREAD leg and a prop leg of ONE real captured fixture
(`KXNFL*-26SEP13ATLPIT`), which carry three different event tickers. The
tickers are checked against `tests/fixtures`, never trusted from memory, so the
test fails if the fixtures stop containing them.

What it does not establish: NHL/MLB series (no same-fixture NHL capture exists;
NFL is the real multi-series fixture on disk), or what the joint SHOULD be --
this repo has no measured same-game correlation (ADR 0012 section 5). The
WNBA-vs-NFL negative swaps the series prefix on a real segment, so that one
ticker is synthetic by necessity.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend import hedge
from backend.store import db

FIXTURES = Path(__file__).resolve().parent / "fixtures"
NOW_MS = 1_700_000_000_000

GAME = "KXNFLGAME-26SEP13ATLPIT-ATL"
SPREAD = "KXNFLSPREAD-26SEP13ATLPIT-ATL3"
PROP = "KXNFLRECYDS-26SEP13ATLPIT-ATLBROBINSON7"
OTHER_GAME = "KXNFLGAME-26SEP13MIALV-MIA"


def _all_fixture_text() -> str:
    return "\n".join(
        p.read_text(encoding="utf-8") for p in FIXTURES.glob("*.json")
    )


@pytest.fixture()
def conn(tmp_path):
    connection = db.init_db(tmp_path / "cockpit.db")
    yield connection
    connection.close()


def _book(ticker):
    return hedge.MarketBook(
        ticker=ticker, yes_bid_tenths=200, no_bid_tenths=760,
        yes_ask_size=400.0, no_ask_size=400.0, status="active",
        observed_ms=NOW_MS,
    )


def _assess(conn, tickers):
    pid = hedge.record_position(
        conn, now_ms=NOW_MS, source="sportsbook", label="t",
        stake_tenths=5_000, return_tenths=100_000,
        legs=[
            {"ticker": t, "side": "yes", "label": f"leg {t}",
             "league": "americanfootball_nfl"}
            for t in tickers
        ],
    )
    position = next(r for r in hedge.open_positions(conn) if int(r["id"]) == pid)
    return hedge.assess(
        position, hedge.legs_for(conn, pid),
        {t: _book(t) for t in tickers},
        now_ms=NOW_MS, max_quote_age_ms=30_000, spendable_tenths=10_000_000,
    )


def test_the_tickers_are_real_captures():
    text = _all_fixture_text()
    for ticker in (GAME, SPREAD, PROP, OTHER_GAME):
        assert ticker in text, ticker


def test_game_spread_and_prop_of_one_fixture_share_a_key():
    keys = {
        hedge.same_game_key(hedge.event_ticker_for(t))
        for t in (GAME, SPREAD, PROP)
    }
    assert len(keys) == 1 and None not in keys


def test_other_fixtures_and_other_leagues_do_not_share_it():
    base = hedge.same_game_key(hedge.event_ticker_for(GAME))
    assert hedge.same_game_key(hedge.event_ticker_for(OTHER_GAME)) != base
    # Same segment, different league: never merged on the segment alone.
    assert hedge.same_game_key("KXWNBAGAME-26SEP13ATLPIT") != base
    assert hedge.same_game_key("not-a-ticker") is None


def test_assess_refuses_the_joint_across_series_of_one_fixture(conn):
    # `derisk` catches CorrelationRefused and carries it as `joint_refusal`,
    # so "raises" shows up here as a refusal holding the module's own message.
    outcome = _assess(conn, [GAME, SPREAD, PROP]).outcome
    assert outcome.joint_probability is None
    assert outcome.joint_refusal is not None
    assert "same fixture" in outcome.joint_refusal.detail


def test_assess_still_prices_legs_of_different_fixtures(conn):
    result = _assess(conn, [GAME, OTHER_GAME])
    assert result.state == hedge.STATE_DERISK
    assert result.outcome.joint_refusal is None
    assert result.outcome.joint_probability is not None


class TestLeaguesSeenInCaptures:
    """#229 review: a league missing from the prefix list keeps the per-event
    key, the unsafe direction. These are series names present in
    `tests/fixtures`; Brasileiro's B and C divisions must not collapse into
    Serie A."""

    def test_cfl_and_soccer_series_of_one_fixture_share_a_key(self):
        from backend.hedge import same_game_key

        assert same_game_key("KXCFLSPREAD-26AUG08EDMMTL") == "CFL:26AUG08EDMMTL"
        assert (
            same_game_key("KXUSLGAME-26AUG08LOUTAM")
            == same_game_key("KXUSL1H-26AUG08LOUTAM")
            is not None
        )

    def test_brasileiro_divisions_stay_apart(self):
        from backend.hedge import same_game_key

        a = same_game_key("KXBRASILEIROGAME-26AUG08FLAPAL")
        b = same_game_key("KXBRASILEIROBGAME-26AUG08FLAPAL")
        assert a is not None and b is not None and a != b
