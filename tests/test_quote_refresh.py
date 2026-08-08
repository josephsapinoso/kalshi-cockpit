"""Refreshing the Kalshi quote at order time.

Two halves, and they fail for different reasons.

**The wire format**, pinned by `tests/fixtures/market_single.json` — a verbatim
capture of `GET /markets/{ticker}` stored beside the *same ticker* as `/events`
returns it. The single-market endpoint is not the endpoint discovery reads, and
this repo has twice been caught assuming two endpoints agree about field names.
The capture is asserted against directly, so a truncated or re-scoped re-capture
fails loudly instead of quietly making every test below it vacuous.

**The control**, which is the half that touches money. The claim is not that a
live quote can be fetched; it is that the order endpoint *prices, sizes and caps
the order against it*. Several tests here would pass against an implementation
that fetches a quote and then ignores it, so the discriminating ones are marked:
they assert the limit price, the size and the cost all move with the live ask.
"""

from __future__ import annotations

import sqlite3
import time

import httpx
import pytest

from backend.api.routes import create_app
from backend.config import (
    AppConfig,
    GateConfig,
    RiskConfig,
    StalenessConfig,
)
from backend.kalshi.discovery import build_market
from backend.kalshi.quotes import (
    LiveQuote,
    QuoteUnavailable,
    parse_market_quote,
)
from backend.store import db
from backend.store.db import ask_for_side

from conftest import load_fixture


# ---------------------------------------------------------------------------
# The wire format
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def capture():
    return load_fixture("market_single.json")


class TestTheCaptureItself:
    """Assertions about the capture, so a bad re-capture cannot pass silently.

    A fixture that no longer contains a two-sided active market would make every
    parser test below it trivially true — `None` in, `None` out, green.
    """

    def test_it_is_the_single_market_envelope(self, capture):
        assert "market" in capture["single"], (
            "the capture must hold the whole /markets/{ticker} payload, "
            "envelope included -- the envelope key is the thing most likely to "
            "be guessed at"
        )

    def test_it_captured_an_active_two_sided_market(self, capture):
        market = capture["single"]["market"]
        assert market["status"] == "active"
        assert market["yes_bid_dollars"] not in (None, "")
        assert market["no_bid_dollars"] not in (None, "")

    def test_it_captured_a_game_market_rather_than_a_season_prop(self, capture):
        """The order path only ever refreshes tickers discovery classified.

        A season prop shares the series prefix and passes a naive filter, so
        capturing one would pin the wire format of a market this code never
        reads.
        """
        assert "GAME" in capture["ticker"] or "SPREAD" in capture["ticker"] \
            or "TOTAL" in capture["ticker"], capture["ticker"]


class TestTheTwoEndpointsAgree:
    """`/events` and `/markets/{ticker}` must describe a quote the same way.

    Captured seconds apart in one run, so a difference is a difference in the
    API rather than in the market. If Kalshi ever renames a quote field on one
    endpoint and not the other, this is what says so — rather than the order
    path quietly refreshing from `None` and refusing every order for a reason
    nobody can see.
    """

    def test_every_quote_field_matches(self, capture):
        nested = build_market(capture["nested"], market_type="moneyline")
        single = build_market(capture["single"]["market"], market_type="moneyline")

        assert single.ticker == nested.ticker
        assert single.yes_bid_tenths == nested.yes_bid_tenths
        assert single.no_bid_tenths == nested.no_bid_tenths
        assert single.yes_ask_size == nested.yes_ask_size
        assert single.no_ask_size == nested.no_ask_size
        assert single.status == nested.status

    def test_the_prices_actually_parsed(self, capture):
        """Both `None` would satisfy the equality above."""
        single = build_market(capture["single"]["market"], market_type="moneyline")
        assert single.yes_bid_tenths is not None
        assert single.no_bid_tenths is not None
        assert 0 < single.yes_bid_tenths < 1000


class TestParsingALiveQuote:
    def test_the_derived_ask_is_the_stored_quote_paths_derived_ask(self, capture):
        """One definition of 'the price you would pay', not two.

        The runner derives an ask from a `kalshi_quotes` row; this derives one
        from a live payload. If those ever diverge, the order endpoint prices
        against a number the recommendation was never compared to.
        """
        quote = parse_market_quote(capture["single"], observed_ms=1_000)
        row = {
            "yes_bid_tenths": quote.market.yes_bid_tenths,
            "no_bid_tenths": quote.market.no_bid_tenths,
        }
        assert quote.ask_tenths("yes") == ask_for_side(row, "yes")
        assert quote.ask_tenths("no") == ask_for_side(row, "no")

    def test_the_depth_crossover_is_not_inverted(self, capture):
        """A YES ask is filled by the resting NO bid, so its size is the NO-bid
        size. Getting this backwards produces entirely plausible numbers."""
        market = capture["single"]["market"]
        quote = parse_market_quote(capture["single"], observed_ms=1_000)
        assert quote.depth_at_ask("yes") == float(market["yes_ask_size_fp"])
        assert quote.depth_at_ask("no") == float(market["yes_bid_size_fp"])

    def test_a_renamed_envelope_raises_rather_than_returning_an_empty_quote(self):
        """`payload.get("market") or {}` would parse to a book of Nones, which
        the caller reads as 'no book' — correct behaviour for the wrong reason,
        and silent forever."""
        with pytest.raises(QuoteUnavailable) as exc:
            parse_market_quote({"markets": [{"ticker": "T"}]}, observed_ms=1)
        assert "renamed" in str(exc.value)

    def test_an_object_without_a_ticker_is_refused(self):
        with pytest.raises(QuoteUnavailable):
            parse_market_quote({"market": {"status": "active"}}, observed_ms=1)

    def test_an_unreadable_bid_gives_no_ask_rather_than_zero(self, capture):
        """Unreadable must never resolve to zero. A zero ask is a free contract."""
        broken = {
            "market": {**capture["single"]["market"], "no_bid_dollars": "wat"}
        }
        quote = parse_market_quote(broken, observed_ms=1)
        assert quote.ask_tenths("yes") is None
        assert quote.ask_tenths("no") is not None, (
            "only the side that lost its opposing bid should become unreadable"
        )

    def test_a_settled_market_is_not_tradeable(self, capture):
        settled = {"market": {**capture["single"]["market"], "status": "settled"}}
        assert parse_market_quote(settled, observed_ms=1).tradeable is False

    def test_age_never_runs_backwards(self, capture):
        quote = parse_market_quote(capture["single"], observed_ms=5_000)
        assert quote.age_ms(6_000) == 1_000
        assert quote.age_ms(4_000) == 0


class _StubRest:
    """A `KalshiRestClient` stand-in. Returns whatever it is told to."""

    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error
        self.paths: list[str] = []

    async def get(self, path: str, **_params):
        self.paths.append(path)
        if self.error is not None:
            raise self.error
        return self.payload


class TestTheSourceRefusesTheWrongAnswer:
    """`LiveQuoteSource` itself, with the transport stubbed.

    These branches sit under the fake the endpoint tests inject, so without a
    stubbed client they are unreachable — written, plausible, and never
    executed.
    """

    async def test_the_right_market_comes_back(self, capture):
        """The control for the refusal below: a matching ticker must succeed, or
        the next test proves only that something raised."""
        from backend.kalshi.quotes import LiveQuoteSource

        ticker = capture["ticker"]
        source = LiveQuoteSource(rest=_StubRest(capture["single"]))

        quote = await source.fetch(ticker, observed_ms=1)

        assert quote.ticker == ticker
        assert source._api().paths == [f"/markets/{ticker}"]

    async def test_a_response_about_a_different_market_is_refused(self, capture):
        """Buying the wrong thing at the right-looking price is not a transport
        failure, it is a correctness failure, and nothing downstream would
        notice: the payload parses, the ask is readable, the size is plausible.
        """
        from backend.kalshi.quotes import LiveQuoteSource

        source = LiveQuoteSource(rest=_StubRest(capture["single"]))

        with pytest.raises(QuoteUnavailable) as exc:
            await source.fetch("SOME-OTHER-TICKER", observed_ms=1)
        assert capture["ticker"] in str(exc.value)

    async def test_a_transport_failure_becomes_one_exception_type(self):
        """The caller has one correct response to every failure. Giving it three
        exception types is how one of them ends up uncaught on the money path."""
        from backend.kalshi.quotes import LiveQuoteSource

        source = LiveQuoteSource(rest=_StubRest(error=httpx.ConnectError("reset")))

        with pytest.raises(QuoteUnavailable):
            await source.fetch("T", observed_ms=1)

    async def test_a_supplied_client_is_not_closed_by_the_source(self, capture):
        from backend.kalshi.quotes import LiveQuoteSource

        stub = _StubRest(capture["single"])
        source = LiveQuoteSource(rest=stub)
        await source.aclose()

        assert source._api() is stub, (
            "closing must not discard a transport the caller owns"
        )


# ---------------------------------------------------------------------------
# The control
# ---------------------------------------------------------------------------

TICKER = "KXTEST-GAME-A"


def _payload(
    *,
    ticker: str = TICKER,
    yes_bid_tenths: int = 400,
    no_bid_tenths: int = 500,
    yes_ask_size: float = 500.0,
    yes_bid_size: float = 500.0,
    status: str = "active",
) -> dict:
    """A `/markets/{ticker}` payload in the captured shape.

    Hand-built, deliberately: this is not a wire-format test. The field names
    and the envelope are pinned above by the capture, and every payload built
    here goes through the same `parse_market_quote` those tests exercise, so a
    rename fails there rather than being papered over here.
    """
    return {
        "market": {
            "ticker": ticker,
            "status": status,
            "yes_bid_dollars": f"{yes_bid_tenths / 1000:.4f}",
            "no_bid_dollars": f"{no_bid_tenths / 1000:.4f}",
            "yes_ask_size_fp": f"{yes_ask_size:.2f}",
            "yes_bid_size_fp": f"{yes_bid_size:.2f}",
        }
    }


class FakeQuotes:
    """A quote source that records what it was asked for.

    The call log is the point. `tasks/lessons.md`: a module that is complete,
    tested and called by nothing is a plan, not a feature — and the whole of
    this change is a call.
    """

    def __init__(self, payload: dict | None = None, error: Exception | None = None):
        self._payload = payload if payload is not None else _payload()
        self._error = error
        self.calls: list[str] = []

    async def fetch(self, ticker: str, *, observed_ms: int) -> LiveQuote:
        self.calls.append(ticker)
        if self._error is not None:
            raise self._error
        return parse_market_quote(self._payload, observed_ms=observed_ms)

    async def aclose(self) -> None:
        pass


ARMED = GateConfig(live_trading_enabled=True, min_scored_recommendations=300)
FRESH = StalenessConfig(max_odds_age_s=900, max_kalshi_quote_age_s=30)


@pytest.fixture
def armed_db(tmp_path):
    """A record that satisfies every standing gate condition, plus one live pick.

    400 distinct games with a consistent +2c CLV so the always-valid bound is
    cleared rather than merely two standard errors, and one fill whose predicted
    fee matches. Without all of that the endpoint refuses at the gate and never
    reaches the quote refresh, which would make every test below it vacuous.
    """
    path = tmp_path / "armed.db"
    db.init_db(path).close()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    now = int(time.time() * 1000)

    conn.execute(
        "INSERT INTO strategy_configs (version, created_ms, effective_from_ms, "
        "config_json, rationale, approved_by_user) VALUES (1, ?, ?, '{}', 't', 1)",
        (now, now),
    )
    for i in range(400):
        _market(conn, f"G{i}")
        _recommendation(
            conn, ticker=f"G{i}", created_ms=now, clv_tenths=20.0 + (0.5 if i % 2 else -0.5),
            scored=True, suggested_contracts=0,
        )
    conn.execute(
        "INSERT INTO fills (kalshi_fill_id, ticker, filled_ms, count, "
        "price_tenths, is_taker, fee_actual, fee_predicted, fee_model_used) "
        "VALUES ('f1', 'G0', 1, 10, 500, 1, 0.35, 0.35, 'conservative')"
    )
    conn.commit()
    return path, conn, now


def _market(conn, ticker):
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_markets (ticker, event_ticker, series_ticker, "
        "first_seen_ms, last_seen_ms) VALUES (?, ?, 'S', 0, 0)",
        (ticker, f"EVT-{ticker}"),
    )


def _recommendation(
    conn,
    *,
    ticker,
    created_ms,
    ask_tenths=500,
    fair_probability=0.60,
    suggested_contracts=20,
    quote_age=1_000,
    odds_age=60_000,
    clv_tenths=None,
    scored=False,
    suppressed=None,
):
    conn.execute(
        """
        INSERT INTO recommendations (
            created_ms, strategy_config_version, ticker, side, entry_ask_tenths,
            depth_at_ask, fair_probability, edge_tenths, fee_predicted,
            ev_net_dollars, kelly_fraction, suggested_contracts,
            kalshi_quote_age_ms, odds_age_ms, suppressed_reason, reason_text,
            clv_tenths, clv_scored_ms
        ) VALUES (?, 1, ?, 'yes', ?, 500.0, ?, 20.0, 0.1, 0.5, 0.02, ?, ?, ?, ?,
                  'test', ?, ?)
        """,
        (
            created_ms, ticker, ask_tenths, fair_probability, suggested_contracts,
            quote_age, odds_age, suppressed, clv_tenths,
            created_ms if scored else None,
        ),
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]


def _live_pick(conn, now, **kwargs):
    _market(conn, TICKER)
    return _recommendation(conn, ticker=TICKER, created_ms=now, **kwargs)


def _app(path, quotes, *, risk=None, gate=ARMED, staleness=FRESH):
    return create_app(
        AppConfig(instance_mode="live", auth_token="t", db_path=path),
        gate_config=gate,
        risk_config=risk or RiskConfig(),
        staleness_config=staleness,
        quote_source=quotes,
    )


async def _order(app, rec_id, contracts=20):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        return await c.post(
            "/api/orders",
            headers={"Authorization": "Bearer t"},
            json={"recommendation_id": rec_id, "contracts": contracts},
        )


class TestTheQuoteIsActuallyRefreshed:
    async def test_the_endpoint_reads_a_live_quote_before_ordering(self, armed_db):
        path, conn, now = armed_db
        rec = _live_pick(conn, now)
        quotes = FakeQuotes()

        response = await _order(_app(path, quotes), rec)

        assert response.status_code == 200, response.json()
        assert quotes.calls == [TICKER], (
            "the order path must ask the exchange what the price is. A quote "
            "source nothing calls is a plan, not a control."
        )

    async def test_the_limit_price_is_the_live_ask_not_the_recorded_one(
        self, armed_db
    ):
        """**Discriminating.** An implementation that fetches and then ignores
        the answer passes every other test in this class.

        Recorded at 50c; the book has improved to 48c. The order must be sent at
        48c, and the response must say both numbers.
        """
        path, conn, now = armed_db
        rec = _live_pick(conn, now, ask_tenths=500)
        # A yes ask of 480 is a no bid of 520.
        quotes = FakeQuotes(_payload(no_bid_tenths=520))

        body = (await _order(_app(path, quotes), rec)).json()

        assert body["limit_price_cents"] == 48
        assert body["quote"]["recorded_ask_tenths"] == 500
        assert body["quote"]["live_ask_tenths"] == 480
        assert body["quote"]["moved_tenths"] == -20

    async def test_an_adverse_move_is_charged_for_rather_than_absorbed(
        self, armed_db
    ):
        """**Discriminating**, and the direction that costs money.

        The book moved against us, 50c to 53c, and the edge survives it. The
        order must be sent at 53c and its cost stated at 53c: pricing it at the
        recorded ask would understate exposure by exactly the amount the market
        moved against us, which is the one direction a cap must never be wrong.
        """
        path, conn, now = armed_db
        rec = _live_pick(conn, now, ask_tenths=500)
        quotes = FakeQuotes(_payload(no_bid_tenths=470))

        body = (await _order(_app(path, quotes), rec)).json()

        assert body["limit_price_cents"] == 53
        assert body["quote"]["moved_tenths"] == 30
        assert body["worst_case_cost_dollars"] > body["contracts"] * 0.50

    async def test_the_response_reports_the_move_even_when_there_was_none(
        self, armed_db
    ):
        """"The price held" and "nobody looked" must not render identically."""
        path, conn, now = armed_db
        rec = _live_pick(conn, now, ask_tenths=500)

        body = (await _order(_app(path, FakeQuotes()), rec)).json()

        assert body["quote"]["moved_tenths"] == 0
        assert body["quote"]["live_ask_tenths"] == 500
        assert body["quote"]["age_ms"] >= 0


class TestTheRefreshCanRefuse:
    async def test_an_unreachable_exchange_refuses_rather_than_using_the_record(
        self, armed_db
    ):
        """The failure mode this whole change exists to prevent: falling back on
        a remembered price because the current one could not be read."""
        path, conn, now = armed_db
        rec = _live_pick(conn, now)
        quotes = FakeQuotes(error=QuoteUnavailable("connection reset"))

        response = await _order(_app(path, quotes), rec)

        assert response.status_code == 503
        assert "recorded price" in response.json()["detail"]

    async def test_a_settled_market_is_refused(self, armed_db):
        path, conn, now = armed_db
        rec = _live_pick(conn, now)
        quotes = FakeQuotes(_payload(status="settled"))

        response = await _order(_app(path, quotes), rec)

        assert response.status_code == 422
        assert "settled" in response.json()["detail"]

    async def test_a_missing_opposing_bid_refuses_rather_than_falling_back(
        self, armed_db
    ):
        path, conn, now = armed_db
        rec = _live_pick(conn, now)
        quotes = FakeQuotes({"market": {**_payload()["market"], "no_bid_dollars": ""}})

        response = await _order(_app(path, quotes), rec)

        assert response.status_code == 422
        assert "no readable yes ask" in response.json()["detail"]

    async def test_a_price_that_erased_the_edge_is_refused_naming_both(
        self, armed_db
    ):
        """No new threshold: the engine's own sizer returns zero contracts, and
        the refusal quotes the two prices so the reason is checkable."""
        path, conn, now = armed_db
        rec = _live_pick(conn, now, ask_tenths=500, fair_probability=0.60)
        # A yes ask of 620 against a fair value of 60c is no longer a bet.
        quotes = FakeQuotes(_payload(no_bid_tenths=380))

        response = await _order(_app(path, quotes), rec)

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "50c" in detail and "62c" in detail
        assert "+12.0c" in detail

    async def test_depth_below_the_order_size_is_refused(self, armed_db):
        path, conn, now = armed_db
        rec = _live_pick(conn, now)
        quotes = FakeQuotes(_payload(yes_ask_size=5.0))

        response = await _order(_app(path, quotes), rec)

        assert response.status_code == 422
        assert "rest at" in response.json()["detail"]

    async def test_an_unquoted_ask_size_refuses_rather_than_reading_as_zero(
        self, armed_db
    ):
        path, conn, now = armed_db
        rec = _live_pick(conn, now)
        quotes = FakeQuotes(
            {"market": {**_payload()["market"], "yes_ask_size_fp": None}}
        )

        response = await _order(_app(path, quotes), rec)

        assert response.status_code == 422
        assert "no size is quoted" in response.json()["detail"]


class TestWhatTheRefreshDoesAndDoesNotMakeFresh:
    """The half-fix that would look right and be dangerous.

    Refreshing the Kalshi quote resets the *Kalshi* clock and nothing else. The
    sportsbook consensus behind the fair value is metered at ~16 credits a day
    and is not re-swept here, so its age still binds. A row that could be kept
    alive indefinitely by re-reading one of its two inputs would end up offering
    bets priced against a consensus swept hours ago -- the exact failure
    `engine.confirm_recommendation` documents one layer down.
    """

    async def test_a_stale_recorded_quote_no_longer_blocks_an_order(self, armed_db):
        """This is the feature. The row's quote is ten minutes old and the
        market's price is three seconds old, and only one of those is the price
        being paid."""
        path, conn, now = armed_db
        rec = _live_pick(conn, now, quote_age=600_000, odds_age=60_000)

        response = await _order(_app(path, FakeQuotes()), rec)

        assert response.status_code == 200, response.json()

    async def test_the_odds_age_still_binds_however_fresh_the_quote_is(
        self, armed_db
    ):
        """The test that separates the fix from the dangerous half of it."""
        path, conn, now = armed_db
        rec = _live_pick(conn, now, quote_age=0, odds_age=1_800_000)

        response = await _order(_app(path, FakeQuotes()), rec)

        assert response.status_code == 423
        detail = response.json()["detail"]
        fresh = next(c for c in detail["conditions"] if c["name"] == "data_fresh")
        assert fresh["met"] is False
        assert "odds 1800s old" in fresh["detail"]

    async def test_the_board_surfaces_exactly_what_the_endpoint_accepts(
        self, armed_db
    ):
        """The pair, asserted together rather than in two files.

        This repo's recurring failure is a screen and a control deriving the
        same judgement by two paths. Refreshing the quote at order time moved
        that judgement: a row whose recorded quote aged out is still bettable.
        A Board that kept splitting on both clocks would strike this row through
        as expired while this very endpoint sold it -- so the two are checked
        against one row, in one test, and the direction of the disagreement is
        named in the assertion rather than left to be inferred.
        """
        path, conn, now = armed_db
        rec = _live_pick(conn, now, quote_age=600_000, odds_age=60_000)
        app = _app(path, FakeQuotes())

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            board = (await c.get("/api/board")).json()

        row = next(r for r in board["surfaced"] + board["expired"]
                   if r["id"] == rec)
        assert row["actionable"] is True, (
            "the Board calls this expired while the order endpoint accepts it"
        )
        assert row["price_is_current"] is False, (
            "and it must still say the displayed price is ten minutes old"
        )
        assert (await _order(app, rec)).status_code == 200

    async def test_the_gate_is_told_the_live_age_not_the_recorded_one(
        self, armed_db
    ):
        """A refusal must name the age it actually judged."""
        path, conn, now = armed_db
        rec = _live_pick(conn, now, quote_age=600_000, odds_age=1_800_000)

        detail = (await _order(_app(path, FakeQuotes()), rec)).json()["detail"]

        fresh = next(c for c in detail["conditions"] if c["name"] == "data_fresh")
        assert "Kalshi quote 0s old" in fresh["detail"], fresh["detail"]


class TestTheRefreshCostsNothingWhenItCannotMatter:
    async def test_a_locked_gate_refuses_without_spending_a_request(self, tmp_path):
        """Cheapest and most decisive first. With no evidence the gate is locked
        and will stay locked, and asking Kalshi for a price is pure waste."""
        path = tmp_path / "empty.db"
        db.init_db(path).close()
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        now = int(time.time() * 1000)
        conn.execute(
            "INSERT INTO strategy_configs (version, created_ms, effective_from_ms, "
            "config_json, rationale, approved_by_user) VALUES (1, ?, ?, '{}', 't', 1)",
            (now, now),
        )
        rec = _live_pick(conn, now)
        quotes = FakeQuotes()

        response = await _order(_app(path, quotes), rec)

        assert response.status_code == 423
        assert quotes.calls == []

    async def test_a_suppressed_row_is_refused_before_any_request(self, armed_db):
        path, conn, now = armed_db
        rec = _live_pick(conn, now, suppressed="stale_odds")
        quotes = FakeQuotes()

        response = await _order(_app(path, quotes), rec)

        assert response.status_code == 422
        assert quotes.calls == []


class TestSizeIsRederivedNotCarried:
    async def test_a_better_price_does_not_authorise_a_bigger_bet(self, armed_db):
        """Quarter-Kelly at 40c would allow far more than twenty contracts. The
        engine authorised twenty against a recorded decision that will be scored
        on CLV, and a better price is not a mandate to exceed it."""
        path, conn, now = armed_db
        rec = _live_pick(conn, now, ask_tenths=500, suggested_contracts=20)
        quotes = FakeQuotes(_payload(no_bid_tenths=600))     # yes ask 40c

        body = (await _order(_app(path, quotes), rec, contracts=50)).json()

        assert body["contracts"] == 20
        assert body["quote"]["authorised_contracts"] == 20
        assert body["quote"]["resized_contracts"] > 20, (
            "the sizer must genuinely want more here, or this test proves nothing"
        )

    async def test_a_worse_price_shrinks_the_order(self, armed_db):
        """**Discriminating.** Buying the recorded size at a worse price is
        over-betting an edge that has shrunk. The size must fall out of the
        sizer at the live ask, not be carried from the row."""
        path, conn, now = armed_db
        rec = _live_pick(conn, now, ask_tenths=500, suggested_contracts=50)
        quotes = FakeQuotes(_payload(no_bid_tenths=440))     # yes ask 56c

        body = (await _order(_app(path, quotes), rec, contracts=50)).json()

        assert body["quote"]["resized_contracts"] < 50
        assert body["contracts"] == body["quote"]["resized_contracts"]


class TestTheCapsStillBindThroughTheSizer:
    """The route used to re-check the portfolio caps after sizing.

    That duplicate existed because `size_position` had last seen the caps when
    the *row* was written -- minutes ago, against a different portfolio. Step 9
    removed the reason: the sizer now runs inside the request, at the live ask,
    against the exposure read moments earlier. So the re-check could not fire on
    any input, and it was deleted rather than left beside the sizer looking like
    protection.

    Which makes these the tests that were standing behind it. If sizing were
    ever taken out of the order path, or handed a stale exposure, both of these
    go green-to-red -- and the caps must be shown to bind *here*, not merely to
    exist in `core/sizing.py`.
    """

    async def test_the_position_cap_shrinks_the_order_at_order_time(
        self, armed_db
    ):
        path, conn, now = armed_db
        rec = _live_pick(conn, now, ask_tenths=500, suggested_contracts=50)

        roomy = (await _order(
            _app(path, FakeQuotes(), risk=RiskConfig(max_position_dollars=100.0)),
            rec, contracts=50,
        )).json()
        tight = (await _order(
            _app(path, FakeQuotes(), risk=RiskConfig(max_position_dollars=6.0)),
            rec, contracts=50,
        )).json()

        assert tight["contracts"] < roomy["contracts"]
        assert tight["quote"]["binding_constraint"] == "max_position_dollars"

    async def test_exposure_the_engine_never_saw_shrinks_the_order_to_nothing(
        self, armed_db
    ):
        """Exposure is a property of the account now, not of the row.

        A resting order placed after the recommendation was written is invisible
        to `suggested_contracts`, and it is exactly what a per-order cap does
        not bound: twenty compliant orders are not a compliant position.
        """
        path, conn, now = armed_db
        rec = _live_pick(conn, now, ask_tenths=500, suggested_contracts=50)
        conn.execute(
            "INSERT INTO orders (client_order_id, recommendation_id, submitted_ms, "
            "ticker, side, action, order_type, count, limit_price_tenths, status, "
            "request_body_json, dry_run) "
            "VALUES ('o1', ?, ?, ?, 'yes', 'buy', 'limit', 790, 500, 'resting', "
            "'{}', 0)",
            (rec, now, TICKER),
        )
        conn.commit()

        response = await _order(
            _app(path, FakeQuotes(), risk=RiskConfig(max_exposure_dollars=400.0)),
            rec, contracts=50,
        )

        assert response.status_code == 422
        assert "minimum" in response.json()["detail"] or \
               "below" in response.json()["detail"]
