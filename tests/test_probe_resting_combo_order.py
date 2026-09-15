"""The resting-combo probe cancels on the order's shard and signs the path only.

Two defects a *successful* run of `scripts/probe_resting_combo_order.py`
exposed twice (2026-08-30, 2026-09-14) and a refused run can never reach:

- the cancel omitted `?exchange_index=`, 404'd, and left a real order resting
  to be taken back by hand;
- the orders-list read carried its query string inside the signed path and
  returned 401 `INCORRECT_API_KEY_SIGNATURE` -- Kalshi signs the path only.

The venue is faked at the `KalshiRestClient` surface the script touches
(`auth.get_rest_headers`, `client.request`, `base_url`); nothing here reaches
the network, and the synthetic market carries the same `price_ranges`,
`price_level_structure` and `exchange_index` shape the 2026-09-14 capture did.

Every assertion was verified by disabling the guard it defends and watching it
go red; the mutations are named on each class.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import probe_resting_combo_order as probe  # noqa: E402
from probe_resting_combo_order import (  # noqa: E402
    EXIT_OK,
    EXIT_REFUSED,
    Capture,
    cancel_params,
    raw_request,
    request_url,
    run_probe,
    shard_of,
)

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
TICKER = "KXMVECROSSCATEGORY-SHARD1-S2026SYNTHETIC-0000"
ORDER_ID = "01a0a240-0000-7000-8000-000000000000"


def _market(exchange_index: Any = 1) -> dict[str, Any]:
    market: dict[str, Any] = {
        "ticker": TICKER,
        "price_ranges": [
            {"end": "0.0100", "start": "0.0000", "step": "0.0001"},
            {"end": "0.9900", "start": "0.0100", "step": "0.0010"},
            {"end": "1.0000", "start": "0.9900", "step": "0.0001"},
        ],
        "price_level_structure": "center_deci_edge_centi_cent",
    }
    if exchange_index is not None:
        market["exchange_index"] = exchange_index
    return market


class _Response:
    def __init__(self, status: int, body: Any) -> None:
        self.status_code = status
        self._body = body
        self.text = str(body)

    def json(self) -> Any:
        if isinstance(self._body, str):
            raise ValueError("not json")
        return self._body


class _Auth:
    def __init__(self) -> None:
        self.signed: list[tuple[str, str]] = []

    def get_rest_headers(self, method: str, path: str) -> dict[str, str]:
        self.signed.append((method, path))
        return {"KALSHI-ACCESS-KEY": "fake"}


class _Client:
    """Answers the six requests the probe makes, recording every URL sent."""

    def __init__(self, market: dict[str, Any]) -> None:
        self.market = market
        self.calls: list[tuple[str, str, Any]] = []

    async def request(self, method: str, url: str, *, headers: Any, json: Any = None):
        self.calls.append((method, url, json))
        path = url[len(BASE_URL):]
        if method == "GET" and path == f"/markets/{TICKER}":
            return _Response(200, {"market": self.market})
        if method == "GET" and path == f"/markets/{TICKER}/orderbook":
            return _Response(200, {"orderbook_fp": {"no_dollars": [], "yes_dollars": []}})
        if method == "POST" and path == "/portfolio/events/orders":
            return _Response(201, {"order_id": ORDER_ID})
        if method == "GET" and path.startswith("/portfolio/orders"):
            return _Response(200, {"orders": []})
        if method == "GET" and path.startswith("/portfolio/balance"):
            return _Response(200, {"balance_breakdown": [{"exchange_index": 1, "balance": "0.0100"}]})
        if method == "DELETE" and path.startswith(f"/portfolio/events/orders/{ORDER_ID}"):
            # The venue's real behaviour, measured twice: the shard-less cancel
            # is a 404 for an order that is demonstrably resting.
            if f"?exchange_index={self.market.get('exchange_index')}" in path:
                return _Response(200, {"reduced_by": "1.00"})
            return _Response(404, {"error": {"code": "not_found"}})
        raise AssertionError(f"unexpected request {method} {url}")


class _Api:
    def __init__(self, market: dict[str, Any]) -> None:
        self.base_url = BASE_URL
        self.auth = _Auth()
        self.client = _Client(market)


@pytest.fixture(autouse=True)
def _no_pacing(monkeypatch):
    async def _instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr(probe.asyncio, "sleep", _instant)


async def _run(market: dict[str, Any], tmp_path: Path) -> tuple[int, _Api]:
    api = _Api(market)
    code = await run_probe(api, TICKER, Capture(tmp_path / "capture.json"))  # type: ignore[arg-type]
    return code, api


class TestTheCancelCarriesTheMarketsShard:
    """Mutation seen red: `params=cancel_params(shard)` dropped from the DELETE
    (the pre-2026-09-14 script), and separately `cancel_params` returning `{}`."""

    def test_cancel_params_spells_the_venues_query_key(self):
        assert cancel_params(1) == {"exchange_index": 1}

    async def test_the_delete_is_sent_with_the_shard_read_off_the_market(self, tmp_path):
        code, api = await _run(_market(exchange_index=1), tmp_path)
        deletes = [u for m, u, _ in api.client.calls if m == "DELETE"]
        assert deletes == [f"{BASE_URL}/portfolio/events/orders/{ORDER_ID}?exchange_index=1"]
        assert code == EXIT_OK

    async def test_a_shard_other_than_one_is_not_hardcoded(self, tmp_path):
        # The docs call `exchange_index` on the market the source of truth; a
        # script that sent `?exchange_index=1` because the ticker says SHARD1
        # would pass the test above and fail this one.
        _, api = await _run(_market(exchange_index=3), tmp_path)
        deletes = [u for m, u, _ in api.client.calls if m == "DELETE"]
        assert deletes[0].endswith("?exchange_index=3")

    async def test_the_shard_is_read_before_the_order_is_sent(self, tmp_path):
        # An order that cannot be cancelled must not be placed.
        code, api = await _run(_market(exchange_index=None), tmp_path)
        assert code == EXIT_REFUSED
        assert [m for m, _, _ in api.client.calls if m == "POST"] == []


class TestTheShardBalanceIsReadWhileTheOrderRests:
    """Mutation seen red: the `3b_balance_while_resting` request deleted.

    The only second this repo ever has a known resting order is between the
    probe's create and its cancel, and that is the capture NEXT.md 2026-09-14
    item 3 needs (is `balance_breakdown[].balance` gross of resting-order
    value?). A balance read anywhere else answers nothing.
    """

    async def test_the_balance_read_sits_between_create_and_cancel_on_the_shard(self, tmp_path):
        _, api = await _run(_market(exchange_index=1), tmp_path)
        sequence = [(m, u.split("?")[0][len(BASE_URL):]) for m, u, _ in api.client.calls]
        post_at = sequence.index(("POST", "/portfolio/events/orders"))
        delete_at = next(i for i, (m, _) in enumerate(sequence) if m == "DELETE")
        balance_at = sequence.index(("GET", "/portfolio/balance"))
        assert post_at < balance_at < delete_at, sequence
        balance_url = api.client.calls[balance_at][1]
        assert balance_url == f"{BASE_URL}/portfolio/balance?exchange_index=1"


class TestShardOf:
    """Mutation seen red: `shard_of` returning `market.get("exchange_index")`
    unchecked -- `True` becomes shard 1, the combinations shard."""

    def test_reads_the_integer(self):
        assert shard_of(_market(1)) == 1

    @pytest.mark.parametrize("raw", [None, True, -1, "1", 1.0])
    def test_anything_but_a_non_negative_int_is_unreadable(self, raw):
        assert shard_of(_market(raw)) is None


class TestTheQueryStringIsSentAndNotSigned:
    """Mutation seen red: `signed_path(api.base_url, path)` given the URL's
    query (the pre-2026-09-14 `f"/portfolio/orders?ticker={ticker}"` path)."""

    async def test_the_orders_list_read_signs_the_bare_path(self, tmp_path):
        _, api = await _run(_market(), tmp_path)
        signed = [p for _, p in api.auth.signed]
        assert "/trade-api/v2/portfolio/orders" in signed
        assert not any("?" in p for p in signed), signed

    async def test_the_orders_list_read_still_sends_the_ticker(self, tmp_path):
        # The signature must not carry the query; the request must. Dropping
        # it from both would sign correctly and list every order ever placed.
        _, api = await _run(_market(), tmp_path)
        lists = [u for m, u, _ in api.client.calls if m == "GET" and "/portfolio/orders" in u]
        assert lists == [f"{BASE_URL}/portfolio/orders?ticker={TICKER}"] * 2

    def test_request_url_keeps_the_query_on_the_url(self):
        assert request_url(BASE_URL, "/x", {"ticker": "T", "skip": None}) == f"{BASE_URL}/x?ticker=T"
        assert request_url(BASE_URL, "/x", None) == f"{BASE_URL}/x"

    async def test_a_query_in_the_path_is_refused_not_signed(self):
        # Mutation seen red: the `"?" in path` guard deleted.
        api = _Api(_market())
        with pytest.raises(ValueError, match="params="):
            await raw_request(api, "GET", "/portfolio/orders?ticker=T")  # type: ignore[arg-type]
        assert api.auth.signed == []
