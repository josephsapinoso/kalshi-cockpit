"""A tennis leg's buy: its own tables, its own sub-cap, and its isolation (#445).

#439 design §4/§6/§7/§8. The check files a `KIND_TENNIS` request keyed by the
Kalshi event ticker; the runner reads the event, finds the sportsbook match
and buys its `h2h` for 1 credit; the reading lands in `tennis_snapshots` and
`tennis_links` and NOWHERE else.

What this does not establish
-----------------------------
- That the check submits these requests or prices a leg from them. That is
  #446 (`tests/test_parlay_check_tennis.py`).
- That the vendor keeps billing a per-event `h2h` call at 1 credit. Measured
  once, 2026-11-13, at ten named books.
- A link rate. The captures link 3 of 3 main-tour matches; n = 3.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.odds import ondemand
from backend.store import db
from backend.store import tennis_readings as tr

FIXTURES = Path(__file__).parent / "fixtures"
NOW = int(datetime(2026, 11, 13, 18, 0, tzinfo=timezone.utc).timestamp() * 1000)


@pytest.fixture
def inbox(tmp_path):
    return tmp_path / "odds_refresh_inbox.json"


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "t.db")
    yield c
    c.close()


def submit_tennis(inbox, *, event="KXATPMATCH-25NOV13AB", now=NOW, cost=1, **kw):
    return ondemand.submit(
        inbox,
        sport_key="tennis_atp",
        odds_event_id=None,
        now_ms=now,
        estimated_credits=cost,
        kind=ondemand.KIND_TENNIS,
        kalshi_event_ticker=event,
        market_ticker=f"{event}-A",
        **kw,
    )


class TestTheTennisSubCap:
    def test_a_tennis_buy_past_its_sub_cap_is_refused_and_the_150_is_unchanged(
        self, inbox
    ):
        for i in range(ondemand.DEFAULT_TENNIS_DAILY_CREDITS):
            got = submit_tennis(inbox, event=f"KXATPMATCH-E{i}", now=NOW + i)
            assert got.accepted, got.detail
        before = ondemand.manual_spent_today(inbox, NOW + 100)
        refused = submit_tennis(inbox, event="KXATPMATCH-E99", now=NOW + 100)
        assert not refused.accepted
        assert "tennis" in refused.detail and "10" in refused.detail
        assert ondemand.manual_spent_today(inbox, NOW + 100) == before == 10
        # The rest of the 150 is still there for every other kind.
        team = ondemand.submit(
            inbox, sport_key="baseball_mlb", odds_event_id=None,
            now_ms=NOW + 101, estimated_credits=3,
        )
        assert team.accepted, team.detail

    def test_tennis_counts_against_the_150_too(self, inbox):
        submit_tennis(inbox)
        assert ondemand.manual_spent_today(inbox, NOW + 1) == 1

    def test_one_match_is_bought_once_inside_the_cooldown(self, inbox):
        assert submit_tennis(inbox).accepted
        again = submit_tennis(inbox, now=NOW + 30_000)
        assert not again.accepted and again.retry_after_ms > 0
        other = submit_tennis(inbox, event="KXATPMATCH-OTHER", now=NOW + 30_000)
        assert other.accepted

    def test_a_tennis_buy_without_its_tickers_is_refused_outright(self, inbox):
        with pytest.raises(ValueError):
            ondemand.submit(
                inbox, sport_key="tennis_atp", odds_event_id=None, now_ms=NOW,
                estimated_credits=1, kind=ondemand.KIND_TENNIS,
            )


class TestTheRequestSurvivesTheFile:
    def test_both_tickers_round_trip(self, inbox):
        submit_tennis(inbox)
        [req] = ondemand.take(inbox, now_ms=NOW + 1_000, after_ms=0)
        assert req.kind == ondemand.KIND_TENNIS
        assert req.kalshi_event_ticker == "KXATPMATCH-25NOV13AB"
        assert req.market_ticker == "KXATPMATCH-25NOV13AB-A"

    def test_a_tennis_entry_missing_a_ticker_is_dropped(self, inbox):
        inbox.write_text(json.dumps([{
            "sport_key": "tennis_atp", "odds_event_id": None,
            "requested_ms": NOW, "estimated_credits": 1, "kind": "tennis",
            "kalshi_event_ticker": "KXATPMATCH-X",
        }]), encoding="utf-8")
        assert ondemand.take(inbox, now_ms=NOW + 1_000, after_ms=0) == []

    def test_other_kinds_carry_no_tennis_tickers(self, inbox):
        ondemand.submit(
            inbox, sport_key="baseball_mlb", odds_event_id=None, now_ms=NOW,
            estimated_credits=3, kalshi_event_ticker="KXATPMATCH-X",
            market_ticker="KXATPMATCH-X-A",
        )
        [req] = ondemand.take(inbox, now_ms=NOW + 1_000, after_ms=0)
        assert req.kalshi_event_ticker is None and req.market_ticker is None


def _link(**kw):
    base = dict(
        kalshi_event_ticker="KXATPMATCH-E", odds_event_id=None, sport_key=None,
        market_a_ticker=None, player_a=None, market_b_ticker=None,
        player_b=None, occurrence_ms=None, commence_ms=None,
        commence_skew_ms=None, linked_ms=NOW, refusal_reason=None,
        refusal_detail=None, expires_ms=None,
    )
    base.update(kw)
    return tr.TennisLink(**base)


class TestTheLinkTable:
    def test_a_refusal_stands_until_it_expires(self, conn):
        tr.write_link(conn, _link(
            refusal_reason="tennis_no_sportsbook_match",
            expires_ms=NOW + tr.FREE_REFUSAL_TTL_MS,
        ))
        got = tr.read_link(conn, "KXATPMATCH-E", now_ms=NOW + 1)
        assert got is not None and got.refusal_reason == "tennis_no_sportsbook_match"
        assert tr.read_link(conn, "KXATPMATCH-E", now_ms=NOW + tr.FREE_REFUSAL_TTL_MS) is None

    def test_a_paid_refusal_stands_an_hour(self):
        assert tr.PAID_REFUSAL_TTL_MS == 3_600_000
        assert tr.FREE_REFUSAL_TTL_MS == ondemand.DEFAULT_COOLDOWN_MS

    def test_a_link_never_expires_and_names_each_market_player(self, conn):
        tr.write_link(conn, _link(
            odds_event_id="ev", sport_key="tennis_atp_finals",
            market_a_ticker="M-A", player_a="Alexander Zverev",
            market_b_ticker="M-B", player_b="Martin Landaluce",
        ))
        got = tr.read_link(conn, "KXATPMATCH-E", now_ms=NOW + 10 ** 10)
        assert got.linked
        assert got.player_for("M-B") == "Martin Landaluce"
        assert got.player_for("M-C") is None

    def test_a_row_with_neither_link_nor_refusal_is_refused_by_the_schema(self, conn):
        import sqlite3

        with pytest.raises(sqlite3.IntegrityError):
            tr.write_link(conn, _link())


def _captured_quotes():
    """The 1-credit capture, through the odds client's own parser."""
    from backend.odds.client import OddsClient

    payload = json.loads((FIXTURES / "odds_tennis_event_h2h.json").read_text(encoding="utf-8"))
    body = payload["event"]
    client = OddsClient.__new__(OddsClient)
    return client._parse([body], sport_key="tennis_wta_finals", fetched_ms=NOW)


class TestTheReadingTable:
    def test_the_latest_fetch_is_the_reading(self, conn):
        quotes = _captured_quotes()
        assert quotes, "the capture parsed to nothing"
        assert tr.write_snapshots(conn, quotes) == len(quotes)
        later = [q.__class__(**{**q.__dict__, "fetched_ms": NOW + 5}) for q in quotes[:2]]
        tr.write_snapshots(conn, later)
        rows = tr.latest_reading_rows(conn, quotes[0].odds_event_id)
        assert len(rows) == 2 and {r["fetched_ms"] for r in rows} == {NOW + 5}
        assert {"bookmaker", "outcome_name", "price_decimal"} <= set(rows[0])

    def test_only_h2h_is_kept(self, conn):
        q = _captured_quotes()[0]
        lay = q.__class__(**{**q.__dict__, "market": "h2h_lay"})
        assert tr.write_snapshots(conn, [lay]) == 0
