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

import re
import sqlite3
import time
import uuid

import httpx
import pytest

from backend.analysis.clv import DEFAULT_HORIZON_HOURS

from backend.api.routes import create_app
from backend.config import (
    AppConfig,
    GateConfig,
    RiskConfig,
    StalenessConfig,
)
from backend.core.suppression import SuppressionConfig
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
        """`finalized` is the string Kalshi actually sends, verified in the
        discovery capture and recorded in the kalshi-api skill.

        This asserted `"settled"` first, which Kalshi never sends. It proved
        that *some* other string is refused -- true of any allowlist and true
        of a typo. The status that occurs in reality is the one worth
        testing.
        """
        for status in ("finalized", "closed", "determined", "initialized"):
            payload = {"market": {**capture["single"]["market"], "status": status}}
            assert parse_market_quote(payload, observed_ms=1).tradeable is False
        assert parse_market_quote(capture["single"], observed_ms=1).tradeable

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

    async def test_a_ticker_the_exchange_never_heard_of_is_not_retryable(self):
        """A 404 and a dropped connection are the same refusal and opposite
        advice. Served as "try again", the first has a person tapping forever.
        """
        from backend.kalshi.quotes import LiveQuoteSource
        from backend.kalshi.rest import KalshiAPIError

        source = LiveQuoteSource(
            rest=_StubRest(error=KalshiAPIError(404, "/markets/NOPE", "not found"))
        )

        with pytest.raises(QuoteUnavailable) as exc:
            await source.fetch("NOPE", observed_ms=1)
        assert exc.value.permanent is True

    async def test_a_server_error_stays_retryable(self):
        """The control. Marking everything permanent would pass the test above
        and turn every blip into a dead end."""
        from backend.kalshi.quotes import LiveQuoteSource
        from backend.kalshi.rest import KalshiAPIError

        source = LiveQuoteSource(
            rest=_StubRest(error=KalshiAPIError(500, "/markets/T", "boom"))
        )

        with pytest.raises(QuoteUnavailable) as exc:
            await source.fetch("T", observed_ms=1)
        assert exc.value.permanent is False

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

# Distinguishes "caller said nothing about the grid" from "caller said there
# isn't one". `None` is a meaningful value here, so it cannot also be the
# default -- the same collapse `market_width` suffered when 0.0 meant both
# "measured zero disagreement" and "nothing to measure".
_UNSET = object()


def _payload(
    *,
    ticker: str = TICKER,
    yes_bid_tenths: int = 400,
    no_bid_tenths: int = 500,
    yes_ask_size: float = 500.0,
    yes_bid_size: float = 500.0,
    status: str = "active",
    price_ranges: object = _UNSET,
) -> dict:
    """A `/markets/{ticker}` payload in the captured shape.

    Hand-built, deliberately: this is not a wire-format test. The field names
    and the envelope are pinned above by the capture, and every payload built
    here goes through the same `parse_market_quote` those tests exercise, so a
    rename fails there rather than being papered over here.

    `price_ranges` defaults to the whole-cent grid every one of 1,426 live game
    markets carried on 2026-08-08. Pass `None` to model a payload without it —
    the order path must refuse rather than assume whole cents, and
    `TestAMarketWithNoReadableGridIsRefused` below does exactly that.
    """
    market = {
        "ticker": ticker,
        "status": status,
        "yes_bid_dollars": f"{yes_bid_tenths / 1000:.4f}",
        "no_bid_dollars": f"{no_bid_tenths / 1000:.4f}",
        "yes_ask_size_fp": f"{yes_ask_size:.2f}",
        "yes_bid_size_fp": f"{yes_bid_size:.2f}",
    }
    if price_ranges is _UNSET:
        market["price_level_structure"] = "linear_cent"
        market["price_ranges"] = [
            {"start": "0.0000", "end": "1.0000", "step": "0.0100"}
        ]
    elif price_ranges is not None:
        market["price_ranges"] = price_ranges
    return {"market": market}


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
    """The fixture. Building it is `build_armed_db`, which is the reusable half.

    Split so a second test module can build the same record without importing
    this fixture by name -- a re-exported fixture shadows itself in every test
    signature that takes it, which is a real redefinition and not just a lint
    complaint about one.
    """
    return build_armed_db(tmp_path)


def build_armed_db(tmp_path):
    """A record that satisfies every standing gate condition, plus one live pick.

    400 distinct games with a consistent +2c CLV so the always-valid bound is
    cleared rather than merely two standard errors, and one fill whose predicted
    fee matches. Without all of that the endpoint refuses at the gate and never
    reaches the quote refresh, which would make every test below it vacuous.

    **The scored rows are actionable, and that is load-bearing.** They carried
    `suggested_contracts=0` until 2026-08-08, which armed the money path from
    400 games the strategy would not have bet -- a record of "no edge here",
    repeated four hundred times, opening the gate. The gate now counts only
    games it would have taken (`docs/adr/0005`), so a fixture of refused or
    no-edge rows correctly arms nothing. A gate fixture has to be built from the
    population the gate counts, or it tests a path real evidence cannot reach.
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
            scored=True, suggested_contracts=1,
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


def _link(conn, ticker, *, now, commence_ms):
    """A linked sportsbook fixture with a kickoff, as the runner writes one.

    Every recommendation the runner records carries a `link_id`, and the order
    endpoint reads the **sportsbook's** kickoff through it to refuse a game
    already in progress. A fixture without one was a row that could not exist in
    production, and it hid the in-play case entirely — the same shape as the
    scoring fixtures that created recommendations after the closing line.
    """
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_events (event_ticker, series_ticker, title, "
        "category, commence_ms, status, first_seen_ms, last_seen_ms) "
        # Kalshi's own clock, three hours late and deliberately wrong here: if
        # anything ever reads this instead of the sportsbook's, the in-play
        # tests below go red rather than passing by coincidence.
        "VALUES (?, 'S', 't', 'Sports', ?, 'open', ?, ?)",
        (f"EVT-{ticker}", commence_ms + 3 * 3_600_000, now, now),
    )
    conn.execute(
        "INSERT OR IGNORE INTO event_links (kalshi_event_ticker, odds_event_id, "
        "league, method, commence_skew_ms, linked_ms) "
        "VALUES (?, ?, 'americanfootball_nfl', 'exact_alias_pair', ?, ?)",
        (f"EVT-{ticker}", f"ODDS-{ticker}", 3 * 3_600_000, now),
    )
    link_id = conn.execute(
        "SELECT id FROM event_links WHERE odds_event_id = ?", (f"ODDS-{ticker}",)
    ).fetchone()["id"]
    conn.execute(
        "INSERT INTO odds_snapshots (fetched_ms, book_updated_ms, sport_key, "
        "odds_event_id, commence_ms, home_team, away_team, bookmaker, market, "
        "outcome_name, price_decimal) VALUES (?, ?, 'americanfootball_nfl', ?, ?, "
        "'Home', 'Away', 'pinnacle', 'h2h', 'Home', 1.9)",
        (now, now, f"ODDS-{ticker}", commence_ms),
    )
    conn.commit()
    return link_id


def _recommendation(
    conn,
    *,
    ticker,
    created_ms,
    link_id=None,
    ask_tenths=500,
    fair_probability=0.54,
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
            created_ms, strategy_config_version, ticker, link_id, side,
            entry_ask_tenths, depth_at_ask, fair_probability, edge_tenths,
            fee_predicted, ev_net_dollars, kelly_fraction, suggested_contracts,
            kalshi_quote_age_ms, odds_age_ms, suppressed_reason, reason_text,
            clv_tenths, clv_scored_ms, clv_horizon_hours
        ) VALUES (?, 1, ?, ?, 'yes', ?, 500.0, ?, 20.0, 0.1, 0.5, 0.02, ?, ?, ?,
                  ?, 'test', ?, ?, ?)
        """,
        (
            created_ms, ticker, link_id, ask_tenths, fair_probability,
            suggested_contracts, quote_age, odds_age, suppressed, clv_tenths,
            created_ms if scored else None,
            # The gate counts only rows scored at the current primary horizon,
            # so a scored row without this is invisible to it -- and the symptom
            # is a **locked gate**, which reads as the code refusing rather than
            # as an incomplete fixture. Same trap as the `armed_db` that once
            # armed the gate from `suggested_contracts = 0` rows.
            DEFAULT_HORIZON_HOURS if scored else None,
        ),
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]


# An hour ahead, so every ordinary test is pre-game. The in-play tests set it
# behind explicitly rather than relying on a default.
KICKOFF_AHEAD_MS = 3_600_000


def _live_pick(conn, now, *, kickoff_offset_ms=KICKOFF_AHEAD_MS, **kwargs):
    _market(conn, TICKER)
    link_id = _link(conn, TICKER, now=now, commence_ms=now + kickoff_offset_ms)
    return _recommendation(
        conn, ticker=TICKER, created_ms=now, link_id=link_id, **kwargs
    )


def _app(path, quotes, *, risk=None, gate=ARMED, staleness=FRESH,
         suppression=None):
    return create_app(
        AppConfig(instance_mode="live", auth_token="t", db_path=path),
        gate_config=gate,
        risk_config=risk or RiskConfig(),
        staleness_config=staleness,
        suppression_config=suppression or SuppressionConfig(),
        quote_source=quotes,
    )


async def _order(app, rec_id, contracts=20, key=None):
    """A distinct idempotency key per call unless one is named.

    Every call here is a separate intent, so a fresh key is what makes these
    tests mean what they meant before the endpoint required one. Reusing a key
    across two calls is a *different* test -- see `test_order_record.py`, where
    that is the behaviour under examination rather than an accident.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        return await c.post(
            "/api/orders",
            headers={"Authorization": "Bearer t"},
            json={
                "recommendation_id": rec_id,
                "contracts": contracts,
                "idempotency_key": key or uuid.uuid4().hex,
            },
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
        quotes = FakeQuotes(_payload(no_bid_tenths=510))

        body = (await _order(_app(path, quotes), rec)).json()

        assert body["limit_price_tenths"] == 490
        assert body["limit_price_dollars"] == "0.4900"
        assert body["quote"]["recorded_ask_tenths"] == 500
        assert body["quote"]["live_ask_tenths"] == 490
        assert body["quote"]["moved_tenths"] == -10

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
        quotes = FakeQuotes(_payload(no_bid_tenths=490))

        body = (await _order(_app(path, quotes), rec)).json()

        assert body["limit_price_tenths"] == 510
        assert body["limit_price_dollars"] == "0.5100"
        assert body["quote"]["moved_tenths"] == 10
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

        assert response.status_code == 503, "a dropped connection is worth retrying"
        assert "recorded price" in response.json()["detail"]

    async def test_an_unknown_ticker_is_refused_rather_than_offered_a_retry(
        self, armed_db
    ):
        """422, not 503. The refusal is the same and the advice is opposite."""
        path, conn, now = armed_db
        rec = _live_pick(conn, now)
        quotes = FakeQuotes(
            error=QuoteUnavailable("no such market", permanent=True)
        )

        response = await _order(_app(path, quotes), rec)

        assert response.status_code == 422

    async def test_a_settled_market_is_refused(self, armed_db):
        path, conn, now = armed_db
        rec = _live_pick(conn, now)
        quotes = FakeQuotes(_payload(status="finalized"))

        response = await _order(_app(path, quotes), rec)

        assert response.status_code == 422
        assert "finalized" in response.json()["detail"]

    async def test_a_missing_opposing_bid_refuses_rather_than_falling_back(
        self, armed_db
    ):
        path, conn, now = armed_db
        rec = _live_pick(conn, now)
        quotes = FakeQuotes({"market": {**_payload()["market"], "no_bid_dollars": ""}})

        response = await _order(_app(path, quotes), rec)

        assert response.status_code == 422
        assert "no yes offer" in response.json()["detail"]
        assert "unreadable" in response.json()["detail"]

    async def test_a_one_sided_book_is_refused_for_the_right_reason(
        self, armed_db
    ):
        """**Kalshi sends `"0.0000"` for an absent bid, never a missing key.**

        38 of 245 markets in the nested capture carry `yes_bid_dollars ==
        "0.0000"`. So a one-sided book parses cleanly to `0`, derives an ask of
        `1000`, and a `live_ask is None` test never fires on the case it was
        written for. The refusal used to arrive a step later from `size_position`
        and read *"the price moved. Recorded 50c, live 100c"* — money-safe,
        diagnosis wrong, and the branch that looked like the guard was
        unreachable from the wire.
        """
        path, conn, now = armed_db
        rec = _live_pick(conn, now)
        quotes = FakeQuotes(
            {"market": {**_payload()["market"], "no_bid_dollars": "0.0000"}}
        )

        response = await _order(_app(path, quotes), rec)

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "nothing is resting on the other side" in detail
        assert "the price moved" not in detail

    async def test_a_price_that_erased_the_edge_is_refused_naming_both(
        self, armed_db
    ):
        """No new threshold: the engine's own sizer returns zero contracts, and
        the refusal quotes the two prices so the reason is checkable."""
        path, conn, now = armed_db
        rec = _live_pick(conn, now, ask_tenths=500)
        # A yes ask of 620 against a fair value of 60c is no longer a bet.
        quotes = FakeQuotes(_payload(no_bid_tenths=470))

        response = await _order(_app(path, quotes), rec)

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "50c" in detail and "53c" in detail
        assert "+3.0c" in detail

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


class TestAMarketWithNoReadableGridIsRefused:
    """The grid is read from the live payload, and there is no default.

    Kalshi rejects any price off `price_ranges`, and whole cents are legal on
    every structure — so assuming whole cents is never *rejected*, it just rests
    behind a sub-cent market forever. That makes "assume whole cents" the most
    dangerous possible fallback: it fails silently, and it fails into the paper
    record rather than into an error.

    The grid must also come from the **live** payload rather than the recorded
    row: Kalshi publishes a `price_level_structure_updated` lifecycle event, so
    a market's grid can change while it is open.
    """

    async def test_a_payload_without_price_ranges_stops_the_order(self, armed_db):
        path, conn, now = armed_db
        rec = _live_pick(conn, now)
        quotes = FakeQuotes(_payload(price_ranges=None))

        response = await _order(_app(path, quotes), rec)

        assert response.status_code == 503
        assert "price grid" in response.json()["detail"]
        assert "whole cents" in response.json()["detail"]

    async def test_a_malformed_grid_stops_the_order_too(self, armed_db):
        """A band we cannot parse is not a market we may price. Skipping the bad
        band would silently refuse every price inside it, which reads as an
        illiquid market rather than as a parse failure."""
        path, conn, now = armed_db
        rec = _live_pick(conn, now)
        quotes = FakeQuotes(_payload(price_ranges=[{"start": "0.0000"}]))

        response = await _order(_app(path, quotes), rec)

        assert response.status_code == 503

    async def test_the_grid_that_was_used_is_reported(self, armed_db):
        """So a fill at an unexpected price can be traced to the grid that
        produced it, rather than reconstructed from the ticker afterwards."""
        path, conn, now = armed_db
        rec = _live_pick(conn, now)

        body = (await _order(_app(path, FakeQuotes()), rec)).json()

        assert "linear_cent" in body["price_grid"]


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
        # The age is re-derived from the clock at request time, so it is
        # `1800 + however long the fixture took` -- 1800s locally and 1802s on
        # a CI runner that spends two seconds building four hundred rows.
        # Asserting the literal string made the test a measurement of machine
        # speed. What the test actually claims is that the *odds* clock is the
        # one that ran out, and by at least the margin it was set to.
        aged = re.search(r"odds (\d+)s old \(limit (\d+)s\)", fresh["detail"])
        assert aged, fresh["detail"]
        odds_age_s, odds_limit_s = int(aged.group(1)), int(aged.group(2))
        assert odds_age_s >= 1800, fresh["detail"]
        assert odds_age_s > odds_limit_s, fresh["detail"]
        # ...and that the Kalshi clock is not what refused it, which is the
        # half of the fix this test exists to separate out.
        assert "Kalshi quote 0s old" in fresh["detail"], fresh["detail"]

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
        quotes = FakeQuotes(_payload(no_bid_tenths=510))     # yes ask 49c

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
        rec = _live_pick(
            conn, now, ask_tenths=480, fair_probability=0.55,
            suggested_contracts=50,
        )
        quotes = FakeQuotes(_payload(no_bid_tenths=490))     # yes ask 51c

        body = (await _order(_app(path, quotes), rec, contracts=50)).json()

        assert body["quote"]["resized_contracts"] < 50
        assert body["contracts"] == body["quote"]["resized_contracts"]


class TestALargeApparentEdgeIsStillABug:
    """Re-sizing at the live ask is one-sided, and the missing half is the
    dangerous one.

    An adverse move shrinks the order to zero and refuses. A **favourable** move
    just buys more, up to what the engine authorised — so the order-time refresh
    had opened a path where the one number this whole project treats as a defect
    signal was acted on instead of suppressed. On a venue quoted to ~2c by
    sub-200ms market makers, an ask that fell six cents since the row was written
    is not six cents of found money; it is thirteen professional firms deciding
    this side is worse.

    `suppression.edge_ceiling_tenths` catches exactly this at recommendation
    time. It now runs at order time too, against the live price.
    """

    async def test_a_large_favourable_move_is_refused_not_bought(self, armed_db):
        path, conn, now = armed_db
        rec = _live_pick(conn, now, ask_tenths=500)
        # 50c to 42c. Under the old code this was an 8c edge, sized and sent.
        quotes = FakeQuotes(_payload(no_bid_tenths=580))

        response = await _order(_app(path, quotes), rec)

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "ceiling" in detail
        assert "-8.0c" in detail, "the refusal must name the move it caught"

    async def test_a_move_inside_the_ceiling_still_trades(self, armed_db):
        """The control. Without it this class would pass against a ceiling of
        zero, which refuses everything and proves nothing."""
        path, conn, now = armed_db
        rec = _live_pick(conn, now, ask_tenths=500)
        quotes = FakeQuotes(_payload(no_bid_tenths=510))     # 50c -> 49c

        assert (await _order(_app(path, quotes), rec)).status_code == 200

    async def test_the_ceiling_is_the_engines_own_threshold(self, armed_db):
        """Not a second number that happens to agree today."""
        path, conn, now = armed_db
        rec = _live_pick(conn, now, ask_tenths=500)
        quotes = FakeQuotes(_payload(no_bid_tenths=580))

        loosened = _app(
            path, quotes, suppression=SuppressionConfig(edge_ceiling_tenths=200.0)
        )
        assert (await _order(loosened, rec)).status_code == 200


class TestAGameInProgressIsNotACandidate:
    """The runner refuses to *record* a started game. It cannot retract one.

    A row written ten minutes before kickoff keeps `suggested_contracts > 0` and
    stays inside the 900s odds window well into the first quarter — and the
    order-time refresh makes that worse rather than better, because the ask is
    now a live in-play price while the fair value beside it is a pre-game
    consensus. Measured on one live pass: in-play edges ran -200.3 to +67.7
    tenths against -39.2 to -17.7 for pre-game rows on the same slate.
    """

    async def test_a_started_game_is_refused(self, armed_db):
        path, conn, now = armed_db
        rec = _live_pick(conn, now, kickoff_offset_ms=-600_000)   # 10 min in

        response = await _order(_app(path, FakeQuotes()), rec)

        assert response.status_code == 422
        assert "started" in response.json()["detail"]

    async def test_the_clock_is_the_sportsbooks_not_kalshis(self, armed_db):
        """Kalshi's `occurrence_datetime` runs exactly three hours late, so
        reading it would wave through the entire first half.

        The fixture stores Kalshi's time as the sportsbook's plus three hours,
        which is what the live API actually does. A game that kicked off two
        hours ago is still 'an hour away' on Kalshi's clock — so an
        implementation reading the wrong column returns 200 here.
        """
        path, conn, now = armed_db
        rec = _live_pick(conn, now, kickoff_offset_ms=-2 * 3_600_000)

        response = await _order(_app(path, FakeQuotes()), rec)

        assert response.status_code == 422, (
            "this is Kalshi's clock saying the game has not started yet"
        )
        assert "started" in response.json()["detail"]

    async def test_an_unlinked_row_is_refused_rather_than_assumed_pre_game(
        self, armed_db
    ):
        """'We cannot tell whether this game has started' must not resolve to
        'it has not'."""
        path, conn, now = armed_db
        _market(conn, TICKER)
        rec = _recommendation(conn, ticker=TICKER, created_ms=now, link_id=None)

        response = await _order(_app(path, FakeQuotes()), rec)

        assert response.status_code == 422
        assert "no linked sportsbook fixture" in response.json()["detail"]

    async def test_a_game_still_ahead_trades(self, armed_db):
        """The control, so the class cannot pass by refusing everything."""
        path, conn, now = armed_db
        rec = _live_pick(conn, now, kickoff_offset_ms=3_600_000)

        assert (await _order(_app(path, FakeQuotes()), rec)).status_code == 200


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
            # `dry_run = 1`: since ADR 0010 an order sizes against its own
            # population, and every order this project places is paper. A live
            # row here would leave the paper budget untouched and the request
            # would succeed -- which is the correct behaviour and not the one
            # under test.
            # 790 contracts at 50c is $395 of stake -- and $410.80 committed,
            # because exposure counts the fee since 2026-08-09. Left at 790
            # deliberately: this is the arithmetic that changed, and the number
            # under a $400 cap is the one place a suite notices.
            "VALUES ('o1', ?, ?, ?, 'yes', 'buy', 'limit', 790, 500, 'resting', "
            "'{}', 1)",
            (rec, now, TICKER),
        )
        conn.commit()

        response = await _order(
            _app(path, FakeQuotes(), risk=RiskConfig(max_exposure_dollars=400.0)),
            rec, contracts=50,
        )

        assert response.status_code == 422
        detail = response.json()["detail"]
        # Names the cap that bound, not merely that something did. Before the
        # fee was counted this order sized to a handful of contracts and was
        # refused for being below the minimum; now the position is already over
        # the cap on its own, which is a *stricter* refusal for the same input
        # and is the whole point of the change.
        assert "0 contracts" in detail, detail
        assert "max_exposure_dollars" in detail, detail
