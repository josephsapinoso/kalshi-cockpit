""""Check this parlay" prices a friend's off-main-line leg from the books'
alternate lines, or asks to buy them (#303 step 6, Joe's answer on #304).

The alternate rows are the REAL capture `tests/fixtures/odds_ncaaf_alternate_
lines.json` (BYU @ TCU, 2026-10-03, six books), stored through the production
parser. The Kalshi side (`kalshi_markets`, `event_links`) is seeded by hand
in the shape `tests/test_parlay_check.py`'s `seed_game` uses. There is no
captured Kalshi spread/total market for this game in the repo; the subtitles
are the ones the live desk showed for it ("BYU wins by over 6.5 points").

What this does not establish
-----------------------------
- That the runner serves the buy (`tests/test_alt_line_refresh.py`), or that
  a real per-event call returns alternates for another game or sport.
- Anything about correlation: two legs on one game still refuse the joint.
- That the frontend renders `line_source` or `buying_line` (#303 step 7).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend import parlay_check
from backend.alt_lines import alt_line_chance
from backend.odds.client import OddsClient, store_quotes
from backend.store import db as store

from tests.test_parlay_check import FakeApi, _market_payload, _mk_ticker, seed_game

FIXTURE = Path(__file__).parent / "fixtures" / "odds_ncaaf_alternate_lines.json"
EVENT_ID = "b58c0d24e66471e6095c0a5f9afb7ce3"
SPORT = "americanfootball_ncaaf"
BYU, TCU = "BYU Cougars", "TCU Horned Frogs"


def _ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp() * 1000)


FETCH_MS = _ms("2026-10-03T19:00:00")
# Every book in the capture updated 18:53-18:56Z, so a 15-minute rule passes
# at 19:05Z and refuses at 20:00Z.
FRESH_NOW = _ms("2026-10-03T19:05:00")
STALE_NOW = _ms("2026-10-03T20:00:00")
MAX_ODDS_AGE_MS = 15 * 60 * 1000

SPREAD_EVENT = "KXNCAAFSPREAD-26OCT03BYUTCU"
SPREAD_TICKER = f"{SPREAD_EVENT}-BYU7"
TOTAL_EVENT = "KXNCAAFTOTAL-26OCT03BYUTCU"
TOTAL_TICKER = f"{TOTAL_EVENT}-48"


@dataclass
class FakeSubmission:
    accepted: bool
    detail: str = "buying now"
    estimated_credits: int = 2
    retry_after_ms: int = 0


class Buyer:
    def __init__(self, accepted=True):
        self.calls: list[tuple[str, str]] = []
        self.accepted = accepted

    def __call__(self, sport_key, odds_event_id):
        self.calls.append((sport_key, odds_event_id))
        return FakeSubmission(accepted=self.accepted,
                              detail="buying now" if self.accepted else "ceiling says no")


@pytest.fixture
def conn(tmp_path):
    c = store.init_db(tmp_path / "check_alt.db")
    yield c
    c.close()


def _store_alt_capture(conn):
    event = json.loads(FIXTURE.read_text("utf-8"))["response"]
    client = OddsClient.__new__(OddsClient)
    store_quotes(conn, client._parse([event], sport_key=SPORT, fetched_ms=FETCH_MS))


def _seed_kalshi_line(conn, *, event_ticker, ticker, subtitle, market_type, strike):
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_events (event_ticker, title, first_seen_ms, "
        "last_seen_ms) VALUES (?, 'BYU at TCU', 0, 0)",
        (event_ticker,),
    )
    conn.execute(
        "INSERT INTO kalshi_markets (ticker, event_ticker, title, yes_side_team, "
        "market_type, strike, status, first_seen_ms, last_seen_ms) "
        "VALUES (?, ?, ?, ?, ?, ?, 'active', 0, 0)",
        (ticker, event_ticker, subtitle, subtitle, market_type, strike),
    )
    conn.execute(
        "INSERT INTO event_links (kalshi_event_ticker, odds_event_id, league, "
        "method, commence_skew_ms, linked_ms) "
        "VALUES (?, ?, 'College Football', 'exact_alias_pair', 0, 0)",
        (event_ticker, EVENT_ID),
    )


@pytest.fixture
def seeded(conn):
    _store_alt_capture(conn)
    _seed_kalshi_line(conn, event_ticker=SPREAD_EVENT, ticker=SPREAD_TICKER,
                      subtitle="BYU wins by over 6.5 points", market_type="spread",
                      strike=6.5)
    _seed_kalshi_line(conn, event_ticker=TOTAL_EVENT, ticker=TOTAL_TICKER,
                      subtitle="Over 47.5 points scored", market_type="total",
                      strike=47.5)
    conn.commit()
    return conn


async def _check(conn, legs, *, now, buyer=None):
    ticker = _mk_ticker("A1703")
    api = FakeApi(market_payload=_market_payload(legs))
    result = await parlay_check.check_parlay_text(
        conn, text=ticker, now_ms=now, api=api, max_odds_age_ms=MAX_ODDS_AGE_MS,
        request_alt_lines=buyer,
    )
    return result, {leg["market_ticker"]: leg for leg in result["legs"]}


def _ml_leg(conn, now):
    t, e = seed_game(conn, game="other-game", team="Team Zeta", other="Team Eta",
                     p=0.6, computed_ms=now - 30_000, commence_ms=now + 2 * 3_600_000)
    conn.commit()
    return {"event_ticker": e, "market_ticker": t, "side": "yes"}


SPREAD_YES = {"event_ticker": SPREAD_EVENT, "market_ticker": SPREAD_TICKER, "side": "yes"}
SPREAD_NO = {"event_ticker": SPREAD_EVENT, "market_ticker": SPREAD_TICKER, "side": "no"}
TOTAL_YES = {"event_ticker": TOTAL_EVENT, "market_ticker": TOTAL_TICKER, "side": "yes"}


class TestAFreshAlternateReadingPricesTheLeg:
    async def test_off_main_leg_is_priced_from_alt_reading(self, seeded):
        buyer = Buyer()
        result, legs = await _check(
            seeded, [SPREAD_YES, _ml_leg(seeded, FRESH_NOW)], now=FRESH_NOW, buyer=buyer
        )
        expected = alt_line_chance(seeded, EVENT_ID, "spreads", BYU, -6.5, FRESH_NOW)
        leg = legs[SPREAD_TICKER]
        assert leg["chance"] == pytest.approx(expected.chance)
        assert leg["line_source"] == "alternate"
        assert sorted(leg["alt_books_used"]) == sorted(expected.books_used)
        assert len(leg["alt_books_used"]) == 6
        assert leg["unknown_reason_code"] is None
        # With every leg priced, the joint is computed again.
        assert result["fair"]["conservative"] is not None
        assert buyer.calls == [] and result["alt_buys"] == []

    async def test_a_spread_no_is_the_other_team_at_plus_the_line(self, seeded):
        _, legs = await _check(seeded, [SPREAD_NO, _ml_leg(seeded, FRESH_NOW)], now=FRESH_NOW)
        expected = alt_line_chance(seeded, EVENT_ID, "spreads", TCU, 6.5, FRESH_NOW)
        assert legs[SPREAD_TICKER]["chance"] == pytest.approx(expected.chance)
        yes = alt_line_chance(seeded, EVENT_ID, "spreads", BYU, -6.5, FRESH_NOW).chance
        assert legs[SPREAD_TICKER]["chance"] != pytest.approx(1 - yes), (
            "a NO is its own side's minimum, never one minus the YES"
        )

    async def test_a_main_line_leg_is_labelled_main(self, seeded):
        ml = _ml_leg(seeded, FRESH_NOW)
        _, legs = await _check(seeded, [ml, SPREAD_YES], now=FRESH_NOW)
        assert legs[ml["market_ticker"]]["line_source"] == "main"

    async def test_two_alt_legs_on_one_game_still_refuse_the_joint(self, seeded):
        result, legs = await _check(seeded, [SPREAD_YES, TOTAL_YES], now=FRESH_NOW)
        assert legs[SPREAD_TICKER]["chance"] is not None
        assert legs[TOTAL_TICKER]["chance"] is not None
        assert result["fair"]["conservative"] is None
        assert result["fair"]["no_joint_reason"] == "same_game"


class TestAStaleReadingAsksToBuy:
    async def test_stale_alt_reading_submits_one_buy(self, seeded):
        buyer = Buyer()
        result, legs = await _check(seeded, [SPREAD_YES, TOTAL_YES], now=STALE_NOW, buyer=buyer)
        assert buyer.calls == [(SPORT, EVENT_ID)], "one buy per game, not per leg"
        for t in (SPREAD_TICKER, TOTAL_TICKER):
            assert legs[t]["chance"] is None
            assert legs[t]["unknown_reason_code"] == parlay_check.REASON_BUYING_LINE
            assert "check again" in legs[t]["unknown_reason"]
        assert result["alt_buys"] == [{
            "odds_event_id": EVENT_ID, "accepted": True, "detail": "buying now",
            "estimated_credits": 2, "retry_after_ms": 0,
        }]
        assert result["fair"]["no_joint_reason"] == "unknown_leg"

    async def test_a_refused_buy_keeps_the_leg_reason_and_says_why(self, seeded):
        buyer = Buyer(accepted=False)
        result, legs = await _check(seeded, [SPREAD_YES, TOTAL_YES], now=STALE_NOW, buyer=buyer)
        # No main-line reading exists for this game in the fixture, so the
        # pool never served the leg: the original reason is `not_served`.
        assert legs[SPREAD_TICKER]["unknown_reason_code"] == "not_served"
        assert result["alt_buys"][0]["accepted"] is False
        assert result["alt_buys"][0]["detail"] == "ceiling says no"

    async def test_without_a_buyer_a_check_stays_a_read(self, seeded):
        result, legs = await _check(seeded, [SPREAD_YES, TOTAL_YES], now=STALE_NOW, buyer=None)
        assert legs[SPREAD_TICKER]["unknown_reason_code"] == "not_served"
        assert result["alt_buys"] == []

    async def test_a_started_game_buys_nothing(self, seeded):
        buyer = Buyer()
        after_kickoff = _ms("2026-10-03T23:30:00")
        _, legs = await _check(seeded, [SPREAD_YES, TOTAL_YES], now=after_kickoff, buyer=buyer)
        assert buyer.calls == []
        assert legs[SPREAD_TICKER]["unknown_reason_code"] == "game_started"

    async def test_a_leg_linked_to_two_odds_events_is_refused_not_guessed(self, seeded):
        seeded.execute(
            "INSERT INTO event_links (kalshi_event_ticker, odds_event_id, league, "
            "method, commence_skew_ms, linked_ms) "
            "VALUES (?, 'some-other-game', 'College Football', 'exact_alias_pair', 0, 0)",
            (SPREAD_EVENT,),
        )
        seeded.commit()
        buyer = Buyer()
        _, legs = await _check(seeded, [SPREAD_YES, TOTAL_YES], now=FRESH_NOW, buyer=buyer)
        assert legs[SPREAD_TICKER]["chance"] is None
        assert (SPORT, "some-other-game") not in buyer.calls

    async def test_a_leg_with_no_linked_odds_event_buys_nothing(self, seeded):
        seeded.execute("DELETE FROM event_links WHERE kalshi_event_ticker = ?", (SPREAD_EVENT,))
        seeded.commit()
        buyer = Buyer()
        seeded.execute("DELETE FROM event_links WHERE kalshi_event_ticker = ?", (TOTAL_EVENT,))
        seeded.commit()
        _, legs = await _check(seeded, [SPREAD_YES, TOTAL_YES], now=STALE_NOW, buyer=buyer)
        assert buyer.calls == []
        assert legs[SPREAD_TICKER]["chance"] is None


ROOT = Path(__file__).resolve().parents[1]


class TestTheScreenNeverPromisesARefusedBuy:
    def test_no_screen_promises_a_buy_that_was_refused(self):
        """The "check again" words come from the server, which sets them only
        when the inbox ACCEPTED the buy. The screen must not hardcode them, or
        it would promise a purchase that the ceiling refused."""
        tsx = (ROOT / "frontend/src/components/CheckAParlay.tsx").read_text("utf-8")
        assert "check again" not in tsx.lower()
        assert "!buy.accepted" in tsx, "a refused buy must be said in its own words"

    def test_the_server_sets_buying_line_only_on_acceptance(self):
        src = (ROOT / "backend/parlay_check.py").read_text("utf-8")
        block = src[src.index('if alt_buys[-1]["accepted"]:'):]
        block = block[: block.index("fair_joint: Optional[float]")]
        assert "REASON_BUYING_LINE" in block


class TestAlternateLinesNeverReachTheDesksOwnCards:
    """#303 point 4: alternate readings live in `odds_snapshots` under their own
    keys and are devigged at read time; nothing writes them to `fair_prices`,
    so the ladder, recommendations, CLV and the gate cannot see them."""

    def test_alt_quotes_never_reach_the_ladder_or_fair_prices(self, seeded):
        assert seeded.execute("SELECT COUNT(*) FROM fair_prices").fetchone()[0] == 0
        from backend.parlays import candidate_pool, ladder_candidates

        pool = candidate_pool(seeded, now_ms=FRESH_NOW, max_odds_age_ms=MAX_ODDS_AGE_MS)
        candidates, _ = ladder_candidates(
            seeded, now_ms=FRESH_NOW, max_odds_age_ms=MAX_ODDS_AGE_MS, pool=pool
        )
        assert [c for c in candidates if c.odds_event_id == EVENT_ID] == []

    def test_no_production_module_writes_alternate_rows_to_fair_prices(self):
        for rel in ("backend/alt_lines.py", "backend/parlay_check.py"):
            src = (ROOT / rel).read_text("utf-8")
            assert "INSERT INTO fair_prices" not in src
            assert "write_fair_price" not in src
        gate = (ROOT / "backend/gate.py").read_text("utf-8")
        assert "alternate_" not in gate and "alt_lines" not in gate
