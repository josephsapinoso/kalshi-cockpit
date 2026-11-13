""""Check this parlay" prices a main-tour tennis leg (#446, design in #439).

Everything here rides on captures: the Kalshi WTA / ATP Challenger events and
the Odds API WTA Finals `h2h` response (`tests/fixtures/kalshi_tennis_*.json`,
`odds_tennis_*.json`). The link and the reading are stored the way the runner
will store them (`backend.store.tennis_readings`), through the production
odds parser; only the combination envelope around the leg is the shape
`tests/test_parlay_check.py` already builds.

What this does not establish
-----------------------------
- That the runner serves the buy or writes these two tables (main's lane).
- That a tennis chance beats Kalshi's price. It is a per-row fact.
- That the sportsbooks' retirement rules match Kalshi's: they were not read.
- A link rate: three captured matches is n = 3.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend import parlay_check, tennis
from backend.odds.client import OddsClient
from backend.store import db as store
from backend.store import tennis_readings as tr

from tests.test_parlay_check import FakeApi, _market_payload, _mk_ticker, seed_game

FX = Path(__file__).parent / "fixtures"
MAX_ODDS_AGE_MS = 15 * 60 * 1000


def _ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp() * 1000)


# Book updates run 18:12:03Z - 18:13:27Z in the capture.
FETCH_MS = _ms("2026-11-13T18:14:00+00:00")
FRESH_NOW = _ms("2026-11-13T18:20:00+00:00")
STALE_NOW = _ms("2026-11-13T19:30:00+00:00")   # before the 20:00Z commence
STARTED_NOW = _ms("2026-11-13T20:10:00+00:00")

EVENT = "KXWTAMATCH-26NOV13ANDMUC"
AND_T, MUC_T = f"{EVENT}-AND", f"{EVENT}-MUC"
ODDS_ID = "6b92a67eab021047017da9d42e1e1fae"  # Andreeva v Muchova, capture


def load(name):
    return json.loads((FX / name).read_text("utf-8"))


@dataclass
class FakeSubmission:
    accepted: bool = True
    detail: str = "buying now"
    estimated_credits: int = 1
    retry_after_ms: int = 0


class TennisBuyer:
    def __init__(self, accepted=True):
        self.calls: list[tuple[str, str, str]] = []
        self.accepted = accepted

    def __call__(self, sport_key, kalshi_event_ticker, market_ticker):
        self.calls.append((sport_key, kalshi_event_ticker, market_ticker))
        return FakeSubmission(accepted=self.accepted)


@pytest.fixture
def conn(tmp_path):
    c = store.init_db(tmp_path / "check_tennis.db")
    yield c
    c.close()


def _store_link_and_reading(conn, *, fetched_ms=FETCH_MS, with_reading=True,
                            books=None, reading_commence=None):
    """The link `choose_link` makes on the captures, and the stored `h2h`."""
    kalshi = load("kalshi_tennis_event_wta_main.json")["events"][0]
    read = tennis.read_event({"event": kalshi}, AND_T)
    odds_event = next(
        e for e in load("odds_tennis_wta_finals_h2h.json")["events"] if e["id"] == ODDS_ID
    )
    choice = tennis.choose_link(read.players, read.occurrence_ms, [odds_event])
    assert choice.reason is None
    names = {m["ticker"]: m["yes_sub_title"] for m in kalshi["markets"]}
    tr.write_link(conn, tr.TennisLink(
        kalshi_event_ticker=EVENT, odds_event_id=ODDS_ID, sport_key="tennis_wta_finals",
        market_a_ticker=AND_T, player_a=names[AND_T],
        market_b_ticker=MUC_T, player_b=names[MUC_T],
        occurrence_ms=read.occurrence_ms,
        commence_ms=tennis.parse_utc_ms(odds_event["commence_time"]),
        commence_skew_ms=choice.commence_skew_ms, linked_ms=fetched_ms,
        refusal_reason=None, refusal_detail=None, expires_ms=None,
    ))
    if with_reading:
        if books is not None:
            odds_event = {**odds_event, "bookmakers": [
                b for b in odds_event["bookmakers"] if b["key"] in books]}
        if reading_commence is not None:
            # The book moved the match after the link was made.
            odds_event = {**odds_event, "commence_time": reading_commence}
        client = OddsClient.__new__(OddsClient)
        quotes = client._parse([odds_event], sport_key="tennis_wta_finals",
                               fetched_ms=fetched_ms)
        assert tr.write_snapshots(conn, quotes) > 0


def _ml_leg(conn, now):
    t, e = seed_game(conn, game="other-game", team="Team Zeta", other="Team Eta",
                     p=0.6, computed_ms=now - 30_000, commence_ms=now + 2 * 3_600_000)
    conn.commit()
    return {"event_ticker": e, "market_ticker": t, "side": "yes"}


def _tennis_leg(market=AND_T, side="yes", event=EVENT):
    return {"event_ticker": event, "market_ticker": market, "side": side}


async def _check(conn, legs, *, now=FRESH_NOW, buyer=None):
    api = FakeApi(market_payload=_market_payload(legs))
    result = await parlay_check.check_parlay_text(
        conn, text=_mk_ticker("A4461"), now_ms=now, api=api,
        max_odds_age_ms=MAX_ODDS_AGE_MS, request_tennis=buyer,
    )
    return result, {(l["market_ticker"], l["side"]): l for l in result["legs"]}


class TestAStoredReadingGetsAChance:
    async def test_a_leg_with_a_link_and_a_fresh_reading_is_priced(self, conn):
        _store_link_and_reading(conn)
        buyer = TennisBuyer()
        result, legs = await _check(conn, [_tennis_leg(), _ml_leg(conn, FRESH_NOW)],
                                    buyer=buyer)
        leg = legs[(AND_T, "yes")]
        assert leg["chance"] is not None and 0.0 < leg["chance"] < 1.0
        assert leg["line_source"] == "tennis"
        assert leg["unknown_reason_code"] is None
        assert leg["books_used"] and isinstance(leg["anchored_on_sharp"], bool)
        assert "ball has been played" in leg["settlement_note"]
        assert "were not read" in leg["settlement_note"]
        assert buyer.calls == [] and result["alt_buys"] == []
        # Both legs priced, two different games: a joint exists.
        assert result["fair"]["no_joint_reason"] is None

    async def test_a_no_leg_is_the_other_players_own_chance(self, conn):
        _store_link_and_reading(conn)
        _, yes_legs = await _check(conn, [_tennis_leg(MUC_T, "yes"), _ml_leg(conn, FRESH_NOW)])
        _, no_legs = await _check(conn, [_tennis_leg(AND_T, "no"), _ml_leg(conn, FRESH_NOW)])
        # NO on Andreeva IS Muchova's own side, not 1 - worst(YES).
        assert no_legs[(AND_T, "no")]["chance"] == pytest.approx(
            yes_legs[(MUC_T, "yes")]["chance"]
        )

    async def test_a_stale_reading_is_refused_and_asks_once(self, conn):
        _store_link_and_reading(conn)
        buyer = TennisBuyer()
        _, legs = await _check(conn, [_tennis_leg()], now=STALE_NOW, buyer=buyer)
        leg = legs[(AND_T, "yes")]
        assert leg["chance"] is None
        assert leg["unknown_reason_code"] == "buying_line"
        assert len(buyer.calls) == 1

    async def test_a_match_that_has_started_is_game_started_and_buys_nothing(self, conn):
        _store_link_and_reading(conn)
        buyer = TennisBuyer()
        _, legs = await _check(conn, [_tennis_leg()], now=STARTED_NOW, buyer=buyer)
        assert legs[(AND_T, "yes")]["unknown_reason_code"] == "game_started"
        assert legs[(AND_T, "yes")]["chance"] is None
        assert buyer.calls == []


class TestNoReadingSubmitsOnce:
    async def test_a_leg_with_no_link_submits_tennis_and_answers_buying_line(self, conn):
        buyer = TennisBuyer()
        result, legs = await _check(conn, [_tennis_leg()], buyer=buyer)
        leg = legs[(AND_T, "yes")]
        assert buyer.calls == [("tennis_wta", EVENT, AND_T)]
        assert leg["chance"] is None
        assert leg["unknown_reason_code"] == parlay_check.REASON_BUYING_LINE
        assert "30 seconds" in leg["unknown_reason"]
        assert result["alt_buys"][0]["accepted"] is True
        assert result["alt_buys"][0]["kind"] == "tennis"
        assert leg["line_source"] is None

    async def test_a_refused_buy_leaves_the_leg_unknown_not_buying(self, conn):
        buyer = TennisBuyer(accepted=False)
        result, legs = await _check(conn, [_tennis_leg()], buyer=buyer)
        leg = legs[(AND_T, "yes")]
        assert leg["chance"] is None
        assert leg["unknown_reason_code"] == parlay_check.REASON_TENNIS_NO_READING
        assert result["alt_buys"][0]["accepted"] is False

    async def test_a_link_with_no_reading_yet_submits_with_the_match_id(self, conn):
        _store_link_and_reading(conn, with_reading=False)
        buyer = TennisBuyer()
        result, legs = await _check(conn, [_tennis_leg()], buyer=buyer)
        assert buyer.calls == [("tennis_wta", EVENT, AND_T)]
        assert result["alt_buys"][0]["odds_event_id"] == ODDS_ID
        assert legs[(AND_T, "yes")]["unknown_reason_code"] == "buying_line"

    async def test_a_check_without_a_buyer_stays_a_read(self, conn):
        _, legs = await _check(conn, [_tennis_leg()], buyer=None)
        assert legs[(AND_T, "yes")]["unknown_reason_code"] == (
            parlay_check.REASON_TENNIS_NO_READING
        )

    async def test_one_check_buys_at_most_one_request_per_match(self, conn):
        buyer = TennisBuyer()
        # Both players of ONE match on one slip: one request, not two.
        result, legs = await _check(
            conn, [_tennis_leg(AND_T, "yes"), _tennis_leg(MUC_T, "yes")], buyer=buyer
        )
        assert len(buyer.calls) == 1
        assert len(result["alt_buys"]) == 1
        assert legs[(AND_T, "yes")]["unknown_reason_code"] == "buying_line"
        assert legs[(MUC_T, "yes")]["unknown_reason_code"] == "buying_line"


class TestRefusalsInWords:
    async def test_a_challenger_leg_shows_its_refusal_in_words_and_buys_nothing(self, conn):
        challenger = load("kalshi_tennis_event_atp_challenger.json")["events"][0]
        ticker = challenger["markets"][0]["ticker"]
        assert ticker.startswith("KXATPCHALLENGERMATCH-")
        buyer = TennisBuyer()
        _, legs = await _check(
            conn, [_tennis_leg(ticker, event=challenger["event_ticker"])], buyer=buyer
        )
        leg = legs[(ticker, "yes")]
        assert leg["chance"] is None
        assert leg["unknown_reason_code"] == tennis.NO_SPORTSBOOK_TOURNAMENT
        assert "no sportsbook carries this tournament" in leg["unknown_reason"]
        assert buyer.calls == []

    async def test_a_standing_stored_refusal_is_worded_not_rebought(self, conn):
        tr.write_link(conn, tr.TennisLink(
            kalshi_event_ticker=EVENT, odds_event_id=None, sport_key=None,
            market_a_ticker=None, player_a=None, market_b_ticker=None,
            player_b=None, occurrence_ms=None, commence_ms=None,
            commence_skew_ms=None, linked_ms=FRESH_NOW,
            refusal_reason=tennis.NO_SPORTSBOOK_MATCH, refusal_detail=None,
            expires_ms=FRESH_NOW + tr.FREE_REFUSAL_TTL_MS,
        ))
        buyer = TennisBuyer()
        _, legs = await _check(conn, [_tennis_leg()], buyer=buyer)
        leg = legs[(AND_T, "yes")]
        assert leg["unknown_reason_code"] == tennis.NO_SPORTSBOOK_MATCH
        assert "no sportsbook match" in leg["unknown_reason"]
        assert buyer.calls == []

    async def test_a_non_tennis_leg_is_untouched_by_the_tennis_path(self, conn):
        buyer = TennisBuyer()
        first = _ml_leg(conn, FRESH_NOW)
        t, e = seed_game(conn, game="third-game", team="Team Iota", other="Team Kappa",
                         p=0.55, computed_ms=FRESH_NOW - 30_000,
                         commence_ms=FRESH_NOW + 2 * 3_600_000)
        conn.commit()
        second = {"event_ticker": e, "market_ticker": t, "side": "yes"}
        _, legs = await _check(conn, [first, second], buyer=buyer)
        for leg in legs.values():
            assert leg["line_source"] == "main" and leg["settlement_note"] is None
        assert buyer.calls == []


class TestReviewFixes:
    """kalshi-platform's review of #446 (MERGE WITH FIXES)."""

    async def test_a_one_book_chance_is_shown_and_flagged_too_few_books(self, conn):
        one = load("odds_tennis_wta_finals_h2h.json")["events"]
        book = next(e for e in one if e["id"] == ODDS_ID)["bookmakers"][0]["key"]
        _store_link_and_reading(conn, books={book})
        _, legs = await _check(conn, [_tennis_leg(), _ml_leg(conn, FRESH_NOW)])
        leg = legs[(AND_T, "yes")]
        assert leg["chance"] is not None and leg["books_used"] == [book]
        assert leg["probable_bug_status"] == "bug"
        assert leg["probable_bug_codes"] == ["too_few_books"]

    async def test_two_books_are_not_flagged(self, conn):
        _store_link_and_reading(conn)
        _, legs = await _check(conn, [_tennis_leg(), _ml_leg(conn, FRESH_NOW)])
        assert len(legs[(AND_T, "yes")]["books_used"]) >= 2
        assert legs[(AND_T, "yes")]["probable_bug_status"] != "bug"

    async def test_a_book_that_moved_the_match_earlier_starts_it_sooner(self, conn):
        from datetime import datetime, timezone

        early = datetime.fromtimestamp((FRESH_NOW - 60_000) / 1000, tz=timezone.utc)
        _store_link_and_reading(
            conn, reading_commence=early.strftime("%Y-%m-%dT%H:%M:%SZ"))
        _, legs = await _check(conn, [_tennis_leg()])
        assert legs[(AND_T, "yes")]["unknown_reason_code"] == "game_started"

    def test_the_runners_refusal_codes_have_words(self):
        from backend import tennis_serve

        for code in (tennis_serve.READ_FAILED, tennis_serve.ODDS_CALL_FAILED):
            words = parlay_check._reason_words(code)
            assert words and words != code


class TestTheLegIsNamedByItsPlayers:
    """Found on the first live check, 2026-11-13: a tennis leg has no
    `kalshi_markets` title on this instance, so it was labelled with its raw
    ticker."""

    async def test_a_yes_leg_reads_as_the_player_to_beat_the_other(self, conn):
        _store_link_and_reading(conn)
        _, legs = await _check(conn, [_tennis_leg(), _ml_leg(conn, FRESH_NOW)])
        assert legs[(AND_T, "yes")]["label"] == "Mirra Andreeva to beat Karolina Muchova"

    async def test_a_no_leg_reads_as_the_other_player_to_win(self, conn):
        _store_link_and_reading(conn)
        _, legs = await _check(conn, [_tennis_leg(AND_T, "no"), _ml_leg(conn, FRESH_NOW)])
        assert legs[(AND_T, "no")]["label"] == "Karolina Muchova to beat Mirra Andreeva"
