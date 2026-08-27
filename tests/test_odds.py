"""Odds client and credit budget tests.

The budget is the piece that decides whether the tool is usable at all on a
500-credit month, so its refusals are tested as hard behaviour rather than as
advisory logging.

No network: respx intercepts httpx, and the budget runs against a real SQLite
schema in tmp_path.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
import respx

from backend.config import OddsConfig
from backend.odds.budget import CreditBudget, sweep_cost
from backend.odds.client import (
    ALTERNATE_SUFFIX,
    EXCLUDED_MARKETS,
    PRICEABLE_MARKETS,
    PROP_BASE_MARKETS,
    PROP_MARKETS,
    OddsAPIError,
    OddsClient,
    OddsQuote,
    QuotaExhausted,
    prop_market_keys,
    store_quotes,
)
from backend.store import db

BASE = "https://api.test-odds.com/v4"


def ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp() * 1000)


NOW = ms("2026-08-07T18:00:00")


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "odds.db")
    yield c
    c.close()


@pytest.fixture
def budget(conn):
    return CreditBudget(conn, daily_budget=16)


@pytest.fixture
def config():
    return OddsConfig(
        api_key="test-odds-key",
        base_url=BASE,
        daily_credit_budget=16,
        regions=["us", "eu"],
        markets=["h2h", "spreads", "totals"],
    )


@pytest.fixture(scope="module")
def http_client():
    """One shared AsyncClient. Constructing one costs ~500ms of SSL setup --
    see tasks/lessons.md, 'Measure the style rule before believing it'."""
    return httpx.AsyncClient(timeout=5.0)


@pytest.fixture
def odds_client(config, budget, http_client):
    return OddsClient(config, budget, client=http_client)


def odds_payload(**overrides) -> list[dict]:
    """One event, two books, shaped like a real v4 /odds response."""
    event = {
        "id": "evt_abc123",
        "sport_key": "baseball_mlb",
        "commence_time": "2026-08-10T03:20:00Z",
        "home_team": "San Diego Padres",
        "away_team": "Houston Astros",
        "bookmakers": [
            {
                "key": "pinnacle",
                "title": "Pinnacle",
                "last_update": "2026-08-07T17:59:00Z",
                "markets": [
                    {
                        "key": "h2h",
                        "last_update": "2026-08-07T17:59:30Z",
                        "outcomes": [
                            {"name": "Houston Astros", "price": 2.10},
                            {"name": "San Diego Padres", "price": 1.80},
                        ],
                    }
                ],
            },
            {
                "key": "draftkings",
                "title": "DraftKings",
                "last_update": "2026-08-07T17:40:00Z",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Houston Astros", "price": 2.05},
                            {"name": "San Diego Padres", "price": 1.83},
                        ],
                    }
                ],
            },
        ],
    }
    event.update(overrides)
    return [event]


class TestCost:
    def test_cost_is_markets_times_regions(self):
        assert sweep_cost(["h2h", "spreads", "totals"], ["us", "eu"]) == 6
        assert sweep_cost(["h2h"], ["us"]) == 1

    def test_a_call_always_costs_at_least_one(self):
        assert sweep_cost([], []) == 1


class TestBudgetRefusal:
    """A budget that warns and proceeds is not a budget."""

    def test_affordable_within_the_daily_limit(self, budget):
        assert budget.can_afford(6, NOW)

    def test_refuses_once_the_daily_limit_is_reached(self, budget):
        budget.record(called_ms=NOW, endpoint="/odds", cost=12)
        assert not budget.can_afford(6, NOW)

    def test_refuses_when_the_server_says_the_quota_is_gone(self, budget):
        """Their count is authoritative, even when ours disagrees."""
        budget.record(
            called_ms=NOW, endpoint="/odds", cost=1, remaining_reported=2
        )
        assert not budget.can_afford(6, NOW)

    def test_yesterdays_spend_does_not_count_against_today(self, budget):
        budget.record(called_ms=NOW - 86_400_000, endpoint="/odds", cost=16)
        assert budget.can_afford(6, NOW)

    def test_state_reports_both_windows(self, budget):
        budget.record(called_ms=NOW - 86_400_000, endpoint="/odds", cost=10)
        budget.record(called_ms=NOW, endpoint="/odds", cost=6)
        state = budget.state(NOW)
        assert state.spent_today == 6
        assert state.spent_this_month == 16
        assert state.remaining_today == 10


# Sweep *planning* -- which sport, and at what time of day -- lives in
# `backend/odds/timing.py` and is tested in `tests/test_sweep_timing.py`. It
# used to live here as `plan_sweep`, which answered "which sport" and let the
# day's credits go on whichever pass ran first.


class TestFetching:
    @respx.mock
    async def test_parses_one_row_per_book_per_outcome(self, odds_client):
        respx.get(f"{BASE}/sports/baseball_mlb/odds").mock(
            return_value=httpx.Response(200, json=odds_payload())
        )
        async with odds_client as odds:
            quotes = await odds.fetch_odds("baseball_mlb", now_ms=NOW)
        assert len(quotes) == 4
        assert {q.bookmaker for q in quotes} == {"pinnacle", "draftkings"}

    @respx.mock
    async def test_requests_decimal_odds(self, odds_client):
        """American odds need a sign-dependent conversion with a discontinuity
        at +/-100. Every such conversion is a place to invent edge."""
        route = respx.get(f"{BASE}/sports/baseball_mlb/odds").mock(
            return_value=httpx.Response(200, json=odds_payload())
        )
        async with odds_client as odds:
            await odds.fetch_odds("baseball_mlb", now_ms=NOW)
        assert route.calls.last.request.url.params["oddsFormat"] == "decimal"

    @respx.mock
    async def test_records_the_credit_cost_and_the_servers_count(self, odds_client, budget, conn):
        respx.get(f"{BASE}/sports/baseball_mlb/odds").mock(
            return_value=httpx.Response(
                200,
                json=odds_payload(),
                headers={"x-requests-remaining": "437", "x-requests-used": "63"},
            )
        )
        async with odds_client as odds:
            await odds.fetch_odds("baseball_mlb", now_ms=NOW)
        row = conn.execute("SELECT * FROM api_credits").fetchone()
        assert row["cost"] == 6
        assert row["remaining_reported"] == 437
        assert row["used_reported"] == 63

    @respx.mock
    async def test_refuses_and_returns_empty_when_over_budget(self, odds_client, budget):
        """Choosing not to spend is a normal state, not an exception.

        Downstream, no data means the staleness gate marks everything
        un-bettable -- which is the intended chain.
        """
        budget.record(called_ms=NOW, endpoint="/odds", cost=16)
        route = respx.get(f"{BASE}/sports/baseball_mlb/odds").mock(
            return_value=httpx.Response(200, json=odds_payload())
        )
        async with odds_client as odds:
            assert await odds.fetch_odds("baseball_mlb", now_ms=NOW) == []
        assert route.call_count == 0, "a refused call must not hit the network"

    @respx.mock
    async def test_quota_exhaustion_is_distinguishable_from_rate_limiting(
        self, odds_client
    ):
        respx.get(f"{BASE}/sports/baseball_mlb/odds").mock(
            return_value=httpx.Response(429, text="out of credits")
        )
        async with odds_client as odds:
            with pytest.raises(QuotaExhausted):
                await odds.fetch_odds("baseball_mlb", now_ms=NOW)

    @respx.mock
    async def test_a_failed_call_still_records_its_cost(self, odds_client, budget, conn):
        """Some error classes still consume credits. Under-counting spend is
        worse than over-counting it."""
        respx.get(f"{BASE}/sports/baseball_mlb/odds").mock(
            return_value=httpx.Response(422, text="unknown market")
        )
        async with odds_client as odds:
            with pytest.raises(OddsAPIError):
                await odds.fetch_odds("baseball_mlb", now_ms=NOW)
        assert conn.execute("SELECT COUNT(*) c FROM api_credits").fetchone()["c"] == 1


class TestFreshness:
    """Two ages, and the book's own is the one that matters."""

    @respx.mock
    async def test_prefers_the_market_level_last_update(self, odds_client):
        respx.get(f"{BASE}/sports/baseball_mlb/odds").mock(
            return_value=httpx.Response(200, json=odds_payload())
        )
        async with odds_client as odds:
            quotes = await odds.fetch_odds("baseball_mlb", now_ms=NOW)
        pinnacle = next(q for q in quotes if q.bookmaker == "pinnacle")
        assert pinnacle.book_updated_ms == ms("2026-08-07T17:59:30")

    @respx.mock
    async def test_falls_back_to_the_bookmaker_level_update(self, odds_client):
        respx.get(f"{BASE}/sports/baseball_mlb/odds").mock(
            return_value=httpx.Response(200, json=odds_payload())
        )
        async with odds_client as odds:
            quotes = await odds.fetch_odds("baseball_mlb", now_ms=NOW)
        dk = next(q for q in quotes if q.bookmaker == "draftkings")
        assert dk.book_updated_ms == ms("2026-08-07T17:40:00")

    @respx.mock
    async def test_age_is_measured_from_the_book_not_our_fetch(self, odds_client):
        """A book that has not repriced in 20 minutes is stale even if we
        fetched it a second ago."""
        respx.get(f"{BASE}/sports/baseball_mlb/odds").mock(
            return_value=httpx.Response(200, json=odds_payload())
        )
        async with odds_client as odds:
            quotes = await odds.fetch_odds("baseball_mlb", now_ms=NOW)
        dk = next(q for q in quotes if q.bookmaker == "draftkings")
        assert dk.age_ms(NOW) == 20 * 60 * 1000

    def test_this_module_no_longer_defines_a_second_sharp_set(self):
        """ADR 0019. There were two `SHARP_BOOKS` and only one anchored money.

        This module's copy was `{pinnacle, betonlineag, lowvig, circasports}`
        against `runner.py`'s `{pinnacle, betfair_ex_eu, betfair_ex_uk,
        matchbook}` -- one shared member out of four, under nearly identical
        comments -- and its only reader was an `is_sharp` property with no
        production caller. Two definitions of one concept, free to disagree
        forever without a symptom.

        Asserted as an absence, because the failure this prevents is somebody
        re-adding a local 'sharp' notion here rather than using the one that
        anchors the consensus.
        """
        import backend.odds.client as client

        assert not hasattr(client, "SHARP_BOOKS"), (
            "a second SHARP_BOOKS is back in odds/client.py; the consensus "
            "anchors on runner.SHARP_BOOKS and two definitions will diverge"
        )
        assert not hasattr(OddsQuote, "is_sharp"), (
            "is_sharp is back and has no production caller; anchoring goes "
            "through consensus_devig(sharp_books=runner.SHARP_BOOKS)"
        )


class TestMalformedInput:
    """Bad rows are dropped loudly, never stored as partials."""

    @respx.mock
    async def test_events_missing_identity_are_dropped(self, odds_client):
        payload = odds_payload()
        payload[0].pop("home_team")
        respx.get(f"{BASE}/sports/baseball_mlb/odds").mock(
            return_value=httpx.Response(200, json=payload)
        )
        async with odds_client as odds:
            assert await odds.fetch_odds("baseball_mlb", now_ms=NOW) == []

    @respx.mock
    async def test_implausible_decimal_prices_are_dropped(self, odds_client):
        """A price below 1.0 implies probability above 1 -- almost always
        American odds in a decimal field, and it reads as enormous edge."""
        payload = odds_payload()
        payload[0]["bookmakers"][0]["markets"][0]["outcomes"][0]["price"] = -110
        respx.get(f"{BASE}/sports/baseball_mlb/odds").mock(
            return_value=httpx.Response(200, json=payload)
        )
        async with odds_client as odds:
            quotes = await odds.fetch_odds("baseball_mlb", now_ms=NOW)
        assert all(q.price_decimal > 1.0 for q in quotes)
        assert len(quotes) == 3

    def test_implied_probability_inverts_decimal_odds(self):
        q = OddsQuote(
            fetched_ms=NOW, book_updated_ms=NOW, sport_key="s", odds_event_id="e",
            commence_ms=NOW, home_team="H", away_team="A", bookmaker="pinnacle",
            market="h2h", outcome_name="H", outcome_point=None, price_decimal=2.0,
        )
        assert q.implied_probability == pytest.approx(0.5)


class TestStorage:
    @respx.mock
    async def test_quotes_persist_raw_one_row_per_book(self, odds_client, budget, conn):
        """Devigging is a derived view. Storing only a consensus would lose the
        ability to re-run with another method -- and method choice moves the
        answer by more than the whole fee advantage."""
        respx.get(f"{BASE}/sports/baseball_mlb/odds").mock(
            return_value=httpx.Response(200, json=odds_payload())
        )
        async with odds_client as odds:
            quotes = await odds.fetch_odds("baseball_mlb", now_ms=NOW)
        assert store_quotes(conn, quotes) == 4
        rows = conn.execute("SELECT * FROM odds_snapshots ORDER BY bookmaker").fetchall()
        assert {r["bookmaker"] for r in rows} == {"pinnacle", "draftkings"}
        assert rows[0]["price_decimal"] > 1.0


# ---------------------------------------------------------------------------
# Wire format, against a real captured payload
# ---------------------------------------------------------------------------

FIXTURE = (
    Path(__file__).parent / "fixtures" / "odds_mlb_h2h_spreads_totals.json"
)


@pytest.fixture(scope="module")
def captured_odds() -> dict:
    """A verbatim `/v4/sports/baseball_mlb/odds` response, us+eu, decimal.

    Every test in this section reads this rather than a hand-constructed dict.
    `tests/fixtures/` payloads are the wire-format contract -- the rule this
    project already had, followed for Kalshi REST and skipped for the WebSocket
    path, which is how that path stayed dead through 611 passing tests.
    """
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class TestTheRealWireFormat:
    """The parser against the bytes the API actually sends.

    A hand-written payload tests that the parser agrees with the person who
    wrote the payload. That is the mistake that made `orderbook.py` parse every
    book to zero levels while sixteen confident assertions passed above an
    honest `skip`.
    """

    def test_the_capture_is_a_real_multi_book_response(self, captured_odds):
        """Guard the fixture itself, so a truncated re-capture fails loudly."""
        events = captured_odds["events"]
        assert len(events) >= 10
        assert captured_odds["params"]["oddsFormat"] == "decimal"
        assert any(len(e["bookmakers"]) >= 20 for e in events)

    def test_the_parser_reads_the_captured_payload(self, odds_client, captured_odds):
        quotes = odds_client._parse(
            captured_odds["events"], sport_key="baseball_mlb", fetched_ms=NOW
        )
        assert quotes, "the parser produced nothing from a real response"

        # Every field the matcher and the devigger depend on must survive.
        for q in quotes[:50]:
            assert q.odds_event_id and q.home_team and q.away_team
            assert q.commence_ms > 0
            assert q.bookmaker and q.outcome_name
            assert q.price_decimal > 1.0
            assert q.book_updated_ms is not None

    def test_all_three_priceable_markets_survive_the_parse(
        self, odds_client, captured_odds
    ):
        """The exclusion must not be so broad that it drops what we came for."""
        quotes = odds_client._parse(
            captured_odds["events"], sport_key="baseball_mlb", fetched_ms=NOW
        )
        assert {q.market for q in quotes} == {"h2h", "spreads", "totals"}
        assert all(q.outcome_point is not None for q in quotes if q.market == "totals")

    def test_every_market_key_in_the_capture_is_explicitly_classified(
        self, captured_odds
    ):
        """The drift test. An exclusion must be a decision, never an accident.

        A new market key appearing in a future capture fails here rather than
        being silently dropped by a default -- the same rule that caught the
        Kalshi discovery classifier throwing away every spread and total.
        """
        seen = {
            market["key"]
            for event in captured_odds["events"]
            for book in event["bookmakers"]
            for market in book["markets"]
        }
        assert seen, "no market keys in the capture"
        unclassified = seen - PRICEABLE_MARKETS - set(EXCLUDED_MARKETS)
        assert not unclassified, (
            f"unclassified odds market key(s): {sorted(unclassified)}. Add each "
            f"to PRICEABLE_MARKETS or EXCLUDED_MARKETS with a reason."
        )


class TestLayPricesNeverReachTheConsensus:
    """`h2h_lay` arrives unrequested and must not be stored as a back price.

    The request asks for `markets=h2h,spreads,totals`. The response carries
    `h2h_lay` anyway, wherever a betting exchange is in the region -- Betfair
    and Matchbook in this capture.
    """

    def test_the_capture_really_does_contain_unrequested_lay_prices(
        self, captured_odds
    ):
        """If this ever stops being true, the exclusion below proves nothing."""
        assert "h2h_lay" not in captured_odds["params"]["markets"]
        lay_books = {
            book["key"]
            for event in captured_odds["events"]
            for book in event["bookmakers"]
            if any(m["key"] == "h2h_lay" for m in book["markets"])
        }
        assert lay_books, "no lay prices in the capture"

    def test_lay_prices_are_dropped(self, odds_client, captured_odds):
        quotes = odds_client._parse(
            captured_odds["events"], sport_key="baseball_mlb", fetched_ms=NOW
        )
        assert not [q for q in quotes if q.market.endswith("_lay")]

    def test_a_lay_book_sums_to_less_than_one_which_devig_cannot_fix(
        self, captured_odds
    ):
        """Why they are excluded, measured rather than asserted.

        Devigging removes an overround. A lay book has an *under*round -- it
        sums to less than 1 -- so there is nothing to remove and the methods
        scale probabilities up instead. Pooled with back prices it drags the
        consensus toward the lay side, and every number stays plausible.
        """
        found = False
        for event in captured_odds["events"]:
            for book in event["bookmakers"]:
                markets = {m["key"]: m for m in book["markets"]}
                if "h2h" not in markets or "h2h_lay" not in markets:
                    continue
                back = sum(1.0 / o["price"] for o in markets["h2h"]["outcomes"])
                lay = sum(1.0 / o["price"] for o in markets["h2h_lay"]["outcomes"])
                assert back > 1.0, f"{book['key']} back book should be overround"
                assert lay < 1.0, f"{book['key']} lay book should be underround"
                found = True
        assert found, "no book quoted both sides, so nothing was compared"

    def test_an_unrecognised_market_is_dropped_loudly(self, odds_client, caplog):
        """Unknown must warn, not pass through. Silence is the failure mode."""
        payload = [
            {
                "id": "evt", "sport_key": "baseball_mlb",
                "commence_time": "2026-08-07T22:41:00Z",
                "home_team": "Pittsburgh Pirates", "away_team": "New York Mets",
                "bookmakers": [{
                    "key": "somebook", "last_update": "2026-08-07T13:49:00Z",
                    "markets": [{
                        "key": "player_strikeouts_alternate",
                        "outcomes": [{"name": "Someone", "price": 2.0}],
                    }],
                }],
            }
        ]
        with caplog.at_level(logging.WARNING):
            quotes = odds_client._parse(
                payload, sport_key="baseball_mlb", fetched_ms=NOW
            )
        assert quotes == []
        assert "unrecognised odds market" in caplog.text


class TestDriftActuallyComputesADifference:
    """`drift` returned `spent_this_month` and called it drift.

    It never subtracted anything, so the credit reconciliation this module
    presents as its central safety property could not signal no matter how far
    our tally diverged from the server's. And it could not be caught by reading
    the dashboard, because a plausible number was always sitting there.
    """

    def _state(self, conn, *, ours, theirs_used, now_ms):
        for i in range(ours // 6):
            conn.execute(
                "INSERT INTO api_credits (called_ms, endpoint, cost, "
                "remaining_reported, used_reported) VALUES (?, '/odds', 6, ?, ?)",
                (now_ms - i, 500 - theirs_used, theirs_used),
            )
        conn.commit()
        return CreditBudget(conn, daily_budget=16).state(now_ms)

    def test_agreement_reports_zero_drift(self, conn):
        state = self._state(conn, ours=12, theirs_used=12, now_ms=NOW)
        assert state.spent_this_month == 12
        assert state.drift == 0

    def test_disagreement_reports_the_difference(self, conn):
        """The case the old code could not express.

        We think we spent 12; they say 30. That is the difference between "we
        have plenty" and "we ran out on Saturday morning", and it must be a
        number, not a restatement of our own tally.
        """
        state = self._state(conn, ours=12, theirs_used=30, now_ms=NOW)
        assert state.drift == -18
        assert state.drift != state.spent_this_month, (
            "drift is echoing our own count instead of comparing it"
        )

    def test_no_server_count_is_none_not_zero(self, conn):
        """Unknown, not agreement. A substituted zero says "reconciled"."""
        conn.execute(
            "INSERT INTO api_credits (called_ms, endpoint, cost, "
            "remaining_reported, used_reported) VALUES (?, '/odds', 6, 100, NULL)",
            (NOW,),
        )
        conn.commit()
        assert CreditBudget(conn, daily_budget=16).state(NOW).drift is None


class TestTheMonthlyCeiling:
    """`spent_this_month` was computed from day one and checked by nothing.

    A number on a dashboard, not a guard. Survivable while every call cost 6
    credits and the daily cap bounded the month by arithmetic nobody had to do;
    not survivable once a caller can spend 10x per call, which is what the
    historical endpoints charge. A backfill loop could then spend the month
    between two daily resets and every guard would report healthy.

    Three ceilings now, and they must stay distinguishable: the provider's
    (authoritative, refuses because they stop answering), ours-per-month
    (reserves headroom for another lane), and ours-per-day (paces the slate).
    """

    def _spend(self, conn, credits, *, now_ms=NOW, endpoint="/odds"):
        """Book `credits` of spend as one row, so day and month both see it."""
        conn.execute(
            "INSERT INTO api_credits (called_ms, endpoint, cost) VALUES (?, ?, ?)",
            (now_ms, endpoint, credits),
        )
        conn.commit()

    def test_an_unset_ceiling_refuses_nothing(self, conn):
        """Absence is not a zero.

        `monthly_budget=None` must behave exactly as the module did before the
        ceiling existed. A default that refused everything would be the
        never-resolve-to-zero failure pointed the other way.
        """
        self._spend(conn, 100_000)
        budget = CreditBudget(conn, daily_budget=16, monthly_budget=None)
        assert budget.state(NOW).remaining_this_month is None
        # Only the daily cap should be talking here.
        assert not budget.can_afford(6, NOW)
        assert CreditBudget(conn, daily_budget=1_000_000).can_afford(6, NOW)

    def test_the_month_refuses_what_the_day_would_allow(self, conn):
        """The gap the ceiling exists for, stated as the two disagreeing.

        Spend sits inside today's budget and past the month's. Before the
        ceiling this call went ahead. Asserting *both* answers matters: if the
        daily cap also refused, this test would pass without the monthly check
        existing at all.
        """
        self._spend(conn, 900)
        budget = CreditBudget(conn, daily_budget=400, monthly_budget=1_000)

        cheap_enough_for_today = CreditBudget(conn, daily_budget=400)
        assert cheap_enough_for_today.can_afford(200, NOW) is False, (
            "fixture no longer isolates the monthly check; the day refuses too"
        )

        # Today has room for 60 more (900 of 400 is over, so pick a fresh day).
        tomorrow = NOW + 86_400_000
        assert CreditBudget(conn, daily_budget=400).can_afford(200, tomorrow)
        assert not budget.can_afford(200, tomorrow), (
            "the monthly ceiling did not fire on a call the day allowed"
        )

    def test_a_call_inside_both_ceilings_is_allowed(self, conn):
        self._spend(conn, 100)
        budget = CreditBudget(conn, daily_budget=400, monthly_budget=13_000)
        assert budget.can_afford(6, NOW)

    def test_the_providers_count_still_wins(self, conn):
        """Ours is a reserve; theirs is the one that stops answering."""
        conn.execute(
            "INSERT INTO api_credits (called_ms, endpoint, cost, "
            "remaining_reported) VALUES (?, '/odds', 6, 2)",
            (NOW,),
        )
        conn.commit()
        budget = CreditBudget(conn, daily_budget=400, monthly_budget=13_000)
        assert not budget.can_afford(6, NOW)

    def test_remaining_this_month_floors_at_zero_rather_than_going_negative(
        self, conn
    ):
        """Overspend is possible -- a call can cost more than predicted.

        Reporting -40 remaining would read as a measurement; 0 reads as
        exhausted, which is the actionable state.
        """
        self._spend(conn, 1_040)
        budget = CreditBudget(conn, daily_budget=400, monthly_budget=1_000)
        assert budget.state(NOW).remaining_this_month == 0

    def test_the_month_boundary_is_the_calendar_month_not_the_sports_day(
        self, conn
    ):
        """The day rolls at 10:00Z for slate reasons; the month cannot.

        The monthly boundary belongs to The Odds API, and reconciliation against
        `x-requests-used` only works if we agree with theirs.
        """
        july = ms("2026-07-31T23:00:00")
        # 11:00Z, deliberately past the 10:00Z roll, so this is a new *sports
        # day* as well as a new month. At 01:00Z it would not be: the sports day
        # beginning 10:00Z on the 31st runs through midnight into the 1st, and
        # the daily cap would refuse the call for its own reasons -- which is
        # this test passing without the month boundary being exercised at all.
        august = ms("2026-08-01T11:00:00")
        self._spend(conn, 900, now_ms=july)

        budget = CreditBudget(conn, daily_budget=400, monthly_budget=1_000)
        assert budget.state(july).spent_this_month == 900
        assert budget.state(august).spent_this_month == 0, (
            "July's spend followed us into August"
        )
        assert budget.state(august).spent_today == 0, (
            "the fixture is not on a fresh sports day; the daily cap will decide"
        )
        assert budget.can_afford(200, august)


PROP_FIXTURE = Path(__file__).parent / "fixtures" / "odds_mlb_player_props.json"


@pytest.fixture(scope="module")
def captured_props() -> dict:
    """A verbatim `/v4/sports/baseball_mlb/events/{id}/odds` prop response.

    A **different endpoint shape** from the sweep fixture above: this one
    returns a single event object, not a list. That difference is the reason
    this is captured rather than hand-written -- a parser fed a hand-made list
    would agree with whoever wrote the list and still be wrong about the wire.
    """
    return json.loads(PROP_FIXTURE.read_text(encoding="utf-8"))


class TestTheAlternateFeedIsNotBought:
    """Five of the ten prop keys bought nothing, and the count is a price.

    `docs/measurements/2026-08-16-prop-rungs-dump.json.gz`: 35,448 alternate
    rungs, **none carrying an Under**, against 3,940 two-sided lines of which
    **zero** require an alternate row -- folded the way
    `prop_quotes_for_event` folds, so a primary Under pairing with an
    alternate Over is included in that zero. A feed that never carries an
    Under cannot survive the both-sides admission at `runner.py:659-663`.

    These pin the *request* list. They must NOT be read as a claim that the
    alternate keys are unparseable: `PROP_MARKETS` still carries them so the
    rows already in `odds_snapshots` stay readable, and
    `TestPlayerPropsOnTheRealWireFormat` still holds the parser to them.
    """

    def test_the_request_list_is_base_keys_only(self):
        keys = prop_market_keys()
        assert keys == list(PROP_BASE_MARKETS)
        assert not [k for k in keys if k.endswith(ALTERNATE_SUFFIX)], (
            "an _alternate key here doubles the price of every prop event "
            "and buys no consensus line"
        )

    def test_a_prop_event_costs_one_credit_per_base_key_per_region(self):
        assert sweep_cost(prop_market_keys(), ["us", "eu"]) == 10, (
            "10 credits at us,eu -- was 20 while the alternates were bought"
        )

    def test_the_stored_alternate_rows_are_still_readable(self):
        """Stop buying them; keep understanding them.

        Dropping the alternates from `PROP_MARKETS` too would make the parser
        warn-and-drop on every historical row and would break the
        `MAX(fetched_ms)` read in `prop_quotes_for_event`.
        """
        for base in PROP_BASE_MARKETS:
            assert f"{base}{ALTERNATE_SUFFIX}" in PROP_MARKETS
            assert f"{base}{ALTERNATE_SUFFIX}" in PRICEABLE_MARKETS

    def test_the_fetch_default_agrees_with_what_callers_request(self):
        """The 2026-08-15 outage shape: reserve for five, request ten.

        `fetch_props` used to default to `PROP_BASE_MARKETS` while every real
        caller passed `prop_market_keys()`. The two are now one list, and this
        pins that they stay one.
        """
        import inspect

        from backend.odds import client as client_mod

        src = inspect.getsource(client_mod.OddsClient.fetch_props)
        assert "markets or prop_market_keys()" in src, (
            "the default must be the same list the planner reserves for"
        )


class TestPlayerPropsOnTheRealWireFormat:
    """Props against the bytes the API actually sends.

    The load-bearing field is `description`. It carries the player, it does not
    exist on team markets, and without it every player's Over at a given line
    collapses into one indistinguishable bucket -- a devig over two unrelated
    pitchers that looks entirely normal in the table.
    """

    def test_the_capture_is_a_real_single_event_prop_response(self, captured_props):
        """Guard the fixture, so a truncated re-capture fails loudly."""
        assert isinstance(captured_props, dict), "per-event endpoint returns an object"
        assert "bookmakers" in captured_props
        assert len(captured_props["bookmakers"]) >= 5
        keys = {
            m["key"] for b in captured_props["bookmakers"] for m in b["markets"]
        }
        assert keys <= PROP_MARKETS, f"unclassified prop keys: {keys}"
        assert any(k.endswith("_alternate") for k in keys), "need the ladder feed"

    def test_the_parser_carries_the_player_through(self, odds_client, captured_props):
        quotes = odds_client._parse(
            [captured_props], sport_key="baseball_mlb", fetched_ms=NOW
        )
        assert quotes, "the captured payload must produce rows"
        players = {q.outcome_description for q in quotes}
        assert None not in players, "every prop row must name its player"
        assert len(players) >= 2, "the fixture has two pitchers"

    def test_two_players_at_one_line_do_not_collapse(self, odds_client, captured_props):
        """The defect `outcome_description` exists to prevent, stated as a test.

        Keyed on (name, point) alone -- the shape the table had before this
        column -- two pitchers quoted at the same line become one bucket. This
        asserts the collision is real in the captured data, so the test cannot
        pass by the fixture happening not to contain one.
        """
        quotes = odds_client._parse(
            [captured_props], sport_key="baseball_mlb", fetched_ms=NOW
        )
        without = {(q.outcome_name, q.outcome_point, q.bookmaker) for q in quotes}
        with_player = {
            (q.outcome_name, q.outcome_point, q.bookmaker, q.outcome_description)
            for q in quotes
        }
        assert len(with_player) > len(without), (
            "no collision in this fixture, so the assertion proves nothing"
        )

    def test_team_markets_leave_the_player_null(self, odds_client, captured_odds):
        """`outcome_description` must stay `None` where there is no player.

        A non-null default would make every team row look like a prop to any
        query that filters on the column being set.
        """
        quotes = odds_client._parse(
            captured_odds["events"], sport_key="baseball_mlb", fetched_ms=NOW
        )
        assert quotes
        assert {q.outcome_description for q in quotes} == {None}

    def test_the_player_survives_a_round_trip_through_the_table(
        self, conn, odds_client, captured_props
    ):
        quotes = odds_client._parse(
            [captured_props], sport_key="baseball_mlb", fetched_ms=NOW
        )
        store_quotes(conn, quotes)
        rows = conn.execute(
            "SELECT outcome_description, COUNT(*) AS n FROM odds_snapshots "
            "WHERE outcome_description IS NOT NULL GROUP BY outcome_description"
        ).fetchall()
        assert len(rows) >= 2
        assert sum(r["n"] for r in rows) == len(quotes)


class TestPropFetchingIsPerEventAndMeteredPerEvent:
    @respx.mock
    async def test_it_bills_every_event_separately(self, odds_client, budget, conn):
        """Props cost `markets x regions` PER EVENT, not per sweep.

        A batch-priced check would under-count by the number of events, which
        on a 14-game slate is a 14x under-count of the month's spend.
        """
        for event_id in ("e1", "e2"):
            respx.get(
                f"{BASE}/sports/baseball_mlb/events/{event_id}/odds"
            ).mock(return_value=httpx.Response(200, json={"bookmakers": []}))

        async with odds_client as odds:
            await odds.fetch_props(
                "baseball_mlb", ["e1", "e2"], now_ms=NOW,
                markets=["pitcher_strikeouts"], regions=["us"],
            )
        calls = conn.execute("SELECT COUNT(*) AS n FROM api_credits").fetchone()["n"]
        assert calls == 2, "one credit record per event"

    @respx.mock
    async def test_a_mid_slate_refusal_keeps_what_was_already_fetched(
        self, odds_client, budget, conn
    ):
        """The reason the budget is checked per event rather than per batch.

        Refusing the whole slate throws away events the budget could afford;
        committing to the whole slate spends past the cap. Stopping mid-slate
        keeps the earlier events and records why the rest are missing.
        """
        respx.get(f"{BASE}/sports/baseball_mlb/events/e1/odds").mock(
            return_value=httpx.Response(200, json=json.loads(
                PROP_FIXTURE.read_text(encoding="utf-8")
            ))
        )
        # `budget` is `daily_budget=16`; one market x one region costs 1, so
        # spending 15 leaves room for exactly one more event.
        budget.record(called_ms=NOW, endpoint="/odds", cost=15)

        async with odds_client as odds:
            quotes = await odds.fetch_props(
                "baseball_mlb", ["e1", "e2", "e3"], now_ms=NOW,
                markets=["pitcher_strikeouts"], regions=["us"],
            )
        assert quotes, "the affordable event must survive the refusal"
        refusals = conn.execute(
            "SELECT COUNT(*) AS n FROM odds_sweep_log WHERE outcome = 'refused'"
        ).fetchone()["n"]
        assert refusals >= 1, "the refusal must be recorded, not silent"
