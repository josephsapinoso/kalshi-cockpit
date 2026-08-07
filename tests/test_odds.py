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
from backend.odds.budget import CreditBudget, plan_sweep, sweep_cost
from backend.odds.client import (
    EXCLUDED_MARKETS,
    PRICEABLE_MARKETS,
    OddsAPIError,
    OddsClient,
    OddsQuote,
    QuotaExhausted,
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


class TestSweepPlanning:
    """Poll what starts soonest. A six-day-out line will move many times."""

    def test_orders_by_soonest_kickoff(self, budget):
        plans = plan_sweep(
            {
                "americanfootball_nfl": [NOW + 40 * 3600_000],
                "baseball_mlb": [NOW + 3 * 3600_000],
                "basketball_wnba": [NOW + 20 * 3600_000],
            },
            markets=["h2h"], regions=["us"], budget=budget, now_ms=NOW,
        )
        assert [p.sport_key for p in plans] == [
            "baseball_mlb", "basketball_wnba", "americanfootball_nfl",
        ]

    def test_skips_sports_with_nothing_inside_the_horizon(self, budget):
        plans = plan_sweep(
            {"baseball_mlb": [NOW + 6 * 24 * 3600_000]},
            markets=["h2h"], regions=["us"], budget=budget, now_ms=NOW,
            horizon_hours=48,
        )
        assert plans == []

    def test_skips_sports_whose_games_have_started(self, budget):
        plans = plan_sweep(
            {"baseball_mlb": [NOW - 3600_000]},
            markets=["h2h"], regions=["us"], budget=budget, now_ms=NOW,
        )
        assert plans == []

    def test_truncates_to_what_the_budget_allows_keeping_the_soonest(self, budget):
        """The ordering is the point: a caller that truncates the wrong end
        keeps the games that matter least."""
        plans = plan_sweep(
            {
                "a": [NOW + 1 * 3600_000],
                "b": [NOW + 2 * 3600_000],
                "c": [NOW + 3 * 3600_000],
            },
            markets=["h2h", "spreads", "totals"], regions=["us", "eu"],
            budget=budget, now_ms=NOW,
        )
        assert [p.sport_key for p in plans] == ["a", "b"]  # 6 + 6 = 12 of 16


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

    def test_sharp_books_are_flagged(self):
        def quote(book):
            return OddsQuote(
                fetched_ms=NOW, book_updated_ms=NOW, sport_key="s",
                odds_event_id="e", commence_ms=NOW, home_team="H", away_team="A",
                bookmaker=book, market="h2h", outcome_name="H",
                outcome_point=None, price_decimal=2.0,
            )
        assert quote("pinnacle").is_sharp
        assert not quote("draftkings").is_sharp

        # `is_sharp` must be a PROPERTY, not a method. As a bare `def` between
        # two `@property` neighbours, `if quote.is_sharp` -- the way anyone
        # would write it -- binds a method object and is truthy for every book.
        # A live capture showed all 30 bookmakers reporting sharp, FanDuel and
        # DraftKings included. This asserts the shape, not just the value.
        assert isinstance(quote("draftkings").is_sharp, bool), (
            "is_sharp must be a @property; as a method it is always truthy"
        )

    def test_the_sharp_set_is_the_documented_one(self):
        """Three books, not thirty. Sharp-anchoring that includes every book is
        the unweighted average wearing a rigorous name."""
        from backend.odds.client import SHARP_BOOKS

        assert "pinnacle" in SHARP_BOOKS
        assert "draftkings" not in SHARP_BOOKS
        assert "fanduel" not in SHARP_BOOKS
        assert len(SHARP_BOOKS) <= 5, f"{len(SHARP_BOOKS)} 'sharp' books is not a filter"


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
