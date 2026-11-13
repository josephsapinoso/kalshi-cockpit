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


# ---------------------------------------------------------------------------
# Serving (commit B): the runner's half, on captures, through the real client
# ---------------------------------------------------------------------------

BASE = "https://odds.test/v4"
BOOKS = [
    "pinnacle", "matchbook", "betfair_ex_eu", "fanduel", "draftkings",
    "williamhill_us", "fanatics", "sport888", "bovada", "betmgm",
]
LEG_EVENT = "KXWTAMATCH-26NOV13SABSVI"
LEG_MARKET = "KXWTAMATCH-26NOV13SABSVI-SAB"


def _fx(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


SERVE_NOW = _fx("odds_tennis_event_h2h.json")["captured_ms"]


class FakeKalshi:
    """Answers the one public read with the captured single-event payload."""

    def __init__(self):
        self.paths: list[str] = []

    async def get(self, path, **params):
        self.paths.append(path)
        assert params.get("with_nested_markets") == "true"
        return _fx("kalshi_tennis_single_event.json")["response"]


def _odds_handler(calls, *, event_body=None):
    import httpx

    def handler(request):
        calls.append(request.url.path)
        path = request.url.path.removeprefix("/v4")
        free = {"x-requests-last": "0"}
        if path == "/sports":
            return httpx.Response(200, json=_fx("odds_tennis_sports.json")["sports"], headers=free)
        if path == "/sports/tennis_wta_finals/events":
            return httpx.Response(
                200, json=_fx("odds_tennis_events_list.json")["events"], headers=free
            )
        if path.endswith("/events"):
            return httpx.Response(200, json=[], headers=free)
        if path.endswith("/odds"):
            body = event_body if event_body is not None else _fx("odds_tennis_event_h2h.json")["event"]
            return httpx.Response(200, json=body, headers={"x-requests-last": "1"})
        return httpx.Response(404)

    return handler


@pytest.fixture
def odds_calls():
    return []


def _odds_client(conn, calls, **kw):
    import httpx

    from backend.config import OddsConfig
    from backend.odds.budget import CreditBudget
    from backend.odds.client import OddsClient

    cfg = OddsConfig(
        api_key="test-odds-key", base_url=BASE, daily_credit_budget=800,
        regions=["us"], markets=["h2h", "spreads", "totals"], bookmakers=BOOKS,
    )
    return OddsClient(
        cfg, CreditBudget(conn, daily_budget=800),
        client=httpx.AsyncClient(transport=httpx.MockTransport(_odds_handler(calls, **kw))),
    )


def _request(market=LEG_MARKET, event=LEG_EVENT):
    return ondemand.RefreshRequest(
        sport_key="tennis_wta", odds_event_id=None, requested_ms=SERVE_NOW - 1,
        estimated_credits=1, kind=ondemand.KIND_TENNIS,
        kalshi_event_ticker=event, market_ticker=market,
    )


async def _serve(conn, calls, req=None, **kw):
    from backend import tennis_serve

    async with _odds_client(conn, calls, **kw) as odds:
        return await tennis_serve.serve(
            conn, [req or _request()], kalshi=FakeKalshi(), odds=odds, now_ms=SERVE_NOW
        )


class TestTheRunnerServesATennisCheck:
    async def test_a_main_tour_match_is_linked_bought_once_and_stored(self, conn, odds_calls):
        [served] = await _serve(conn, odds_calls)
        assert served.outcome == "linked" and served.credits_spent == 1
        assert sum(1 for p in odds_calls if p.endswith("/odds")) == 1
        link = tr.read_link(conn, LEG_EVENT, now_ms=SERVE_NOW)
        assert link.linked and link.sport_key == "tennis_wta_finals"
        assert link.player_for(LEG_MARKET) == "Aryna Sabalenka"
        rows = tr.latest_reading_rows(conn, link.odds_event_id)
        assert rows
        from backend.tennis import price_leg

        reading = price_leg(rows, link.players, "yes", link.player_for(LEG_MARKET))
        assert reading.reason is None and 0 < reading.chance < 1

    async def test_the_paid_call_is_on_the_ledger_as_manual(self, conn, odds_calls):
        await _serve(conn, odds_calls)
        paid = conn.execute(
            "SELECT cost, trigger FROM api_credits WHERE endpoint LIKE '%/odds'"
        ).fetchall()
        assert [tuple(r) for r in paid] == [(1, "manual")]

    async def test_a_challenger_leg_is_refused_without_a_single_call(self, conn, odds_calls):
        [served] = await _serve(
            conn, odds_calls,
            _request(market="KXATPCHALLENGERMATCH-X-A", event="KXATPCHALLENGERMATCH-X"),
        )
        assert served.outcome == "tennis_no_sportsbook_tournament"
        assert odds_calls == []
        link = tr.read_link(conn, "KXATPCHALLENGERMATCH-X", now_ms=SERVE_NOW)
        assert link.expires_ms == SERVE_NOW + tr.FREE_REFUSAL_TTL_MS

    async def test_an_empty_book_after_the_paid_call_stands_an_hour(self, conn, odds_calls):
        body = {**_fx("odds_tennis_event_h2h.json")["event"], "bookmakers": []}
        [served] = await _serve(conn, odds_calls, event_body=body)
        assert served.outcome == "no_two_sided_book" and served.credits_spent == 1
        link = tr.read_link(conn, LEG_EVENT, now_ms=SERVE_NOW + tr.FREE_REFUSAL_TTL_MS + 1)
        assert link is not None and link.expires_ms == SERVE_NOW + tr.PAID_REFUSAL_TTL_MS

    async def test_two_requests_for_one_match_buy_it_once(self, conn, odds_calls):
        from backend import tennis_serve

        async with _odds_client(conn, odds_calls) as odds:
            served = await tennis_serve.serve(
                conn, [_request(), _request(market="KXWTAMATCH-26NOV13SABSVI-SVI")],
                kalshi=FakeKalshi(), odds=odds, now_ms=SERVE_NOW,
            )
        assert len(served) == 1
        assert sum(1 for p in odds_calls if p.endswith("/odds")) == 1


# ---------------------------------------------------------------------------
# Isolation (#439 design, "Isolation tests"): the four assertions
# ---------------------------------------------------------------------------

def _no_tennis_fixture(conn):
    from backend.odds.timing import upcoming_fixtures_by_sport

    keys = upcoming_fixtures_by_sport(conn, now_ms=SERVE_NOW)
    return not any(k.startswith("tennis") for k in keys)


def _planner_fires_no_tennis(conn):
    from backend.odds.budget import CreditBudget
    from backend.odds.timing import decide_sweeps

    decision = decide_sweeps(
        conn, in_scope={}, budget=CreditBudget(conn, daily_budget=800), cost=3,
        now_ms=SERVE_NOW, max_odds_age_ms=900_000,
    )
    return not any(f.sport_key.startswith("tennis") for f in decision.fire)


async def _refresh_card_lists_no_tennis(db_path, now_ms):
    import httpx

    from backend.api.routes import create_app
    from backend.config import AppConfig

    app = create_app(AppConfig(instance_mode="live", db_path=db_path))
    transport = httpx.ASGITransport(app=app)
    real_now = db.now_ms
    db.now_ms = lambda: now_ms
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            payload = (await c.get("/api/odds/refreshable")).json()
    finally:
        db.now_ms = real_now
    return not any(s["sport_key"].startswith("tennis") for s in payload.get("sports", []))


def _no_fair_price(conn):
    # `fair_prices` hangs off `event_links`; tennis has no link row there, so
    # neither table may hold one for this match.
    links = conn.execute(
        "SELECT COUNT(*) FROM event_links WHERE kalshi_event_ticker = ?", (LEG_EVENT,)
    ).fetchone()[0]
    return links == 0 and conn.execute("SELECT COUNT(*) FROM fair_prices").fetchone()[0] == 0


class TestATennisBuyReachesNothingElse:
    async def test_after_a_buy_the_planner_the_card_and_fair_prices_see_no_tennis(
        self, tmp_path, odds_calls
    ):
        path = tmp_path / "iso.db"
        conn = db.init_db(path)
        [served] = await _serve(conn, odds_calls)
        assert served.outcome == "linked"
        assert _no_tennis_fixture(conn)
        assert _planner_fires_no_tennis(conn)
        assert _no_fair_price(conn)
        conn.close()
        assert await _refresh_card_lists_no_tennis(path, SERVE_NOW)

    async def test_the_checks_catch_a_reading_written_to_odds_snapshots(
        self, tmp_path, odds_calls, monkeypatch
    ):
        """The mutation, run every time: the same buy with its reading written
        to `odds_snapshots` must turn the first three checks red. If it does
        not, the isolation test above proves nothing."""
        from backend import tennis_serve
        from backend.odds.client import store_quotes

        real = tr.write_snapshots

        def into_odds_snapshots(conn, quotes):
            store_quotes(conn, quotes)
            return real(conn, quotes)

        monkeypatch.setattr(tennis_serve.tr, "write_snapshots", into_odds_snapshots)
        path = tmp_path / "mut.db"
        conn = db.init_db(path)
        await _serve(conn, odds_calls)
        assert not _no_tennis_fixture(conn)
        assert not _planner_fires_no_tennis(conn)
        conn.close()
        assert not await _refresh_card_lists_no_tennis(path, SERVE_NOW)


class TestTheTriggerLiteral:
    def test_the_client_and_the_planner_agree_on_manual(self):
        from backend.odds.client import MANUAL_TRIGGER
        from backend.odds.timing import MANUAL

        assert MANUAL_TRIGGER == MANUAL
