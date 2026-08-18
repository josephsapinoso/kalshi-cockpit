"""The market chart's data path: wire candlesticks in, drawable bars out.

Wire-format claims are pinned by `tests/fixtures/candlesticks_mlb.json`, a
real capture -- the per-side blocks carry `close_dollars` dollar strings, not
`close`, which is the misreading that once zeroed the whole CLV pipeline.

What this does not establish: anything about the chart's rendering, or about
liquidity between candles. The route serves history; nothing here touches
sizing or the order path.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from backend.api.routes import create_app
from backend.config import AppConfig
from backend.kalshi.candles import parse_chart_candle
from backend.kalshi.quotes import QuoteUnavailable
from backend.store import db

FIXTURE = Path(__file__).parent / "fixtures" / "candlesticks_mlb.json"


def _fixture_candles() -> list[dict]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    market = next(iter(payload["markets"].values()))
    return market["candlesticks"]


class TestParseChartCandle:
    def test_the_captured_shape_parses_to_tenths(self):
        candle = _fixture_candles()[0]
        bar = parse_chart_candle(candle)
        assert bar is not None
        assert bar["t_ms"] == candle["end_period_ts"] * 1000
        # 0.3400 dollars -> 340 tenths of a cent.
        assert bar["close_tenths"] == 340
        assert bar["yes_bid_close_tenths"] == 330
        assert bar["yes_ask_close_tenths"] == 340
        assert bar["volume"] == pytest.approx(28.74)

    def test_every_fixture_candle_parses(self):
        bars = [parse_chart_candle(c) for c in _fixture_candles()]
        assert all(bar is not None for bar in bars)

    def test_a_candle_with_no_timestamp_is_refused(self):
        candle = dict(_fixture_candles()[0])
        del candle["end_period_ts"]
        assert parse_chart_candle(candle) is None

    def test_missing_price_resolves_to_none_never_zero(self):
        """A settled loser genuinely trades at 0, so a substituted zero is
        indistinguishable from data."""
        candle = dict(_fixture_candles()[0])
        del candle["price"]
        bar = parse_chart_candle(candle)
        assert bar is not None
        assert bar["close_tenths"] is None
        assert bar["open_tenths"] is None

    def test_an_unreadable_volume_is_none(self):
        candle = dict(_fixture_candles()[0])
        candle["volume_fp"] = "not-a-number"
        assert parse_chart_candle(candle)["volume"] is None


class _StubHistory:
    """Injectable source: canned candlesticks, or a canned failure."""

    def __init__(self, candles=None, error=None):
        self._candles = candles if candles is not None else _fixture_candles()
        self._error = error
        self.calls: list[dict] = []

    async def history(self, series_ticker, ticker, *, start_ts, end_ts,
                      period_interval):
        self.calls.append(
            {"series": series_ticker, "ticker": ticker,
             "interval": period_interval, "span_s": end_ts - start_ts}
        )
        if self._error is not None:
            raise self._error
        return self._candles

    async def fetch(self, ticker, *, observed_ms):  # pragma: no cover
        raise AssertionError("the candles route must not fetch a live quote")

    async def aclose(self):
        pass


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "candles.db"
    handle = db.init_db(path)
    handle.execute(
        "INSERT INTO kalshi_series (series_ticker, first_seen_ms, last_seen_ms) "
        "VALUES ('KXMLBGAME', 1, 1)"
    )
    handle.execute(
        "INSERT INTO kalshi_markets (ticker, series_ticker, title, "
        "first_seen_ms, last_seen_ms) VALUES (?, ?, ?, 1, 1)",
        ("KXMLBGAME-26AUG20HOUSEA-HOU", "KXMLBGAME", "Houston at Seattle"),
    )
    handle.commit()
    handle.close()
    return path


async def _get(app, path, **params):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        return await c.get(path, params=params)


def _app(db_path, stub):
    return create_app(
        AppConfig(instance_mode="live", auth_token="t", db_path=db_path),
        quote_source=stub,
    )


class TestTheCandlesRoute:
    async def test_serves_parsed_bars_for_a_discovered_market(self, db_path):
        stub = _StubHistory()
        response = await _get(
            _app(db_path, stub),
            "/api/market/KXMLBGAME-26AUG20HOUSEA-HOU/candles",
            range="1w",
        )
        assert response.status_code == 200
        body = response.json()
        assert body["period_minutes"] == 60
        assert body["title"] == "Houston at Seattle"
        assert len(body["candles"]) == len(_fixture_candles())
        assert body["candles"][0]["close_tenths"] == 340
        # The series came from the discovery record, not string surgery.
        assert stub.calls[0]["series"] == "KXMLBGAME"

    async def test_an_undiscovered_ticker_derives_its_series(self, db_path):
        stub = _StubHistory()
        response = await _get(
            _app(db_path, stub), "/api/market/KXUFCFIGHT-26AUG30-X/candles"
        )
        assert response.status_code == 200
        assert stub.calls[0]["series"] == "KXUFCFIGHT"

    async def test_each_range_maps_to_its_registered_interval(self, db_path):
        expected = {"1d": 1, "1w": 60, "1m": 60, "all": 1440}
        for name, interval in expected.items():
            stub = _StubHistory()
            response = await _get(
                _app(db_path, stub),
                "/api/market/KXMLBGAME-26AUG20HOUSEA-HOU/candles",
                range=name,
            )
            assert response.status_code == 200
            assert stub.calls[0]["interval"] == interval

    async def test_an_unknown_range_is_a_422(self, db_path):
        response = await _get(
            _app(db_path, _StubHistory()),
            "/api/market/KXMLBGAME-26AUG20HOUSEA-HOU/candles",
            range="1y",
        )
        assert response.status_code == 422

    async def test_a_permanently_unknown_market_is_a_422(self, db_path):
        stub = _StubHistory(error=QuoteUnavailable("no such market", permanent=True))
        response = await _get(
            _app(db_path, stub), "/api/market/KXNOPE-X/candles"
        )
        assert response.status_code == 422

    async def test_a_transient_failure_is_a_503(self, db_path):
        stub = _StubHistory(error=QuoteUnavailable("timeout"))
        response = await _get(
            _app(db_path, stub), "/api/market/KXMLBGAME-26AUG20HOUSEA-HOU/candles"
        )
        assert response.status_code == 503

    async def test_unreadable_candles_are_counted_not_zeroed(self, db_path):
        broken = _fixture_candles()[:2] + [{"no_timestamp": True}]
        stub = _StubHistory(candles=broken)
        response = await _get(
            _app(db_path, stub), "/api/market/KXMLBGAME-26AUG20HOUSEA-HOU/candles"
        )
        body = response.json()
        assert len(body["candles"]) == 2
        assert body["dropped_unreadable"] == 1
