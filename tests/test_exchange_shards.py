"""Orders are routed to an exchange shard, and collateral does not follow them.

**Why this exists.** Kalshi splits matching across shards and states the rule
plainly: *"Programmatic traders must preallocate collateral on a given exchange
shard before order placement"*
(`docs.kalshi.com/getting_started/exchange_sharding`). Measured on the live
account on 2026-08-30, with $21.41 in it:

    shard 0   $21.4020   everything else, including WNBA
    shard 1   $0.0100    Exotics -- the KXMVE combinations this desk mints
    shard 2   $0.0000    Crypto
    shard 3   $0.0000    Sports: tennis and baseball only, moved 2026-08-24

A 2c resting bid on a shard-1 combination was refused `insufficient_balance`
while $21.40 sat unusable on shard 0. The same order shape on a shard-3
baseball market was refused `user_not_found`. A 0.5c bid -- inside the penny
that shard actually held -- was **accepted**, rested, and cancelled cleanly.

**What this establishes.** That the balance read can be scoped to a shard;
that the cancel carries its shard as a query parameter rather than in the body;
that the shard is read off the market rather than guessed from the ticker; and
that the query string stays out of the signature.

**What it does not establish.**

- **That any of these numbers still hold.** The shard map is Kalshi's and it
  is actively migrating: baseball moved on 2026-08-24 and WNBA has not. The
  constants here are documentation of one reading, and `exchange_index` on the
  market payload is the authority.
- **That a resting bid ever fills.** Nothing here trades.
- **That a transfer between shards works.** This repo does not move money, and
  the docs warn a cross-shard transfer runs in up to three non-atomic steps
  that are not rolled back on failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config import KalshiConfig                          # noqa: E402
from backend.kalshi.rest import (                                # noqa: E402
    EXCHANGE_INDEX_COMBOS,
    EXCHANGE_INDEX_DEFAULT,
    EXCHANGE_INDEX_PARAM,
    ORDERS_PATH,
    KalshiRestClient,
)


def _client(handler, tmp_path) -> KalshiRestClient:
    """A client whose transport is a recording stub, with a real signer."""
    key = tmp_path / "key.pem"
    key.write_text(_TEST_KEY, encoding="utf-8")
    config = KalshiConfig(
        api_key="test-key",
        private_key_path=key,
        rest_url="https://api.elections.kalshi.com/trade-api/v2",
        ws_url="wss://example.invalid",
    )
    # The transport is injected through the constructor's own `client` seam,
    # which is also what makes `_owns_client` False -- the test closes it.
    return KalshiRestClient(
        config,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


# A throwaway RSA key, generated for this file. It signs nothing real: the
# tests assert on the REQUEST, and the stub transport never verifies.
_TEST_KEY = None  # filled in by the fixture below


@pytest.fixture(autouse=True)
def _rsa_key():
    """Generate a key once per session rather than committing a PEM.

    A committed private key -- even a throwaway -- in a repo that is public
    and holds a live trading credential is the wrong artefact to normalise.
    """
    global _TEST_KEY
    if _TEST_KEY is None:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        _TEST_KEY = private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()
    yield


class TestTheCancelCarriesItsShard:
    async def test_the_shard_goes_on_the_query_not_in_the_body(self, tmp_path):
        """Measured: without it the venue 404s an order that IS resting.

        `DELETE /portfolio/events/orders/{id}` returned 404 `not_found` on
        2026-08-30 for an order the orders list showed as `resting` that same
        second; `?exchange_index=1` returned 200 with `reduced_by 1.00`. The
        endpoint has no ticker to auto-route from, so it looks on shard 0.
        """
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["method"] = request.method
            seen["body"] = request.content
            return httpx.Response(200, json={"reduced_by": "1.00"})

        api = _client(handler, tmp_path)
        try:
            await api.cancel_order("abc-123", exchange_index=EXCHANGE_INDEX_COMBOS)
        finally:
            await api.client.aclose()

        assert seen["method"] == "DELETE"
        assert f"{ORDERS_PATH}/abc-123" in seen["url"]
        assert f"{EXCHANGE_INDEX_PARAM}=1" in seen["url"]
        assert not seen["body"], "the shard is a query parameter, not a body"

    async def test_shard_zero_is_sent_rather_than_dropped_as_falsy(
        self, tmp_path
    ):
        """`0` is a shard, not an absence.

        The natural bug here is `if exchange_index:`, which silently drops the
        one shard that holds most of the money. The client filters `None`, and
        this is what keeps that distinction real.
        """
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            return httpx.Response(200, json={"reduced_by": "1.00"})

        api = _client(handler, tmp_path)
        try:
            await api.cancel_order("abc-123", exchange_index=EXCHANGE_INDEX_DEFAULT)
        finally:
            await api.client.aclose()

        assert f"{EXCHANGE_INDEX_PARAM}=0" in seen["url"]


class TestTheBalanceCanBeScopedToAShard:
    async def test_the_shard_reaches_the_query(self, tmp_path):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            return httpx.Response(200, json={"balance": 1, "balance_breakdown": []})

        api = _client(handler, tmp_path)
        try:
            await api.balance(exchange_index=EXCHANGE_INDEX_COMBOS)
        finally:
            await api.client.aclose()

        assert "/portfolio/balance" in seen["url"]
        assert f"{EXCHANGE_INDEX_PARAM}=1" in seen["url"]

    async def test_no_shard_asks_for_the_whole_account(self, tmp_path):
        """The unscoped read is the SUM, and a sum cannot pay for an order.

        Kept as its own test because the failure it guards is silent: a caller
        that checks the total sees $21.41, believes a $2 bet is affordable, and
        the venue refuses it for insufficient balance on the shard that holds
        one penny.
        """
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            return httpx.Response(200, json={"balance": 2141})

        api = _client(handler, tmp_path)
        try:
            await api.balance()
        finally:
            await api.client.aclose()

        assert EXCHANGE_INDEX_PARAM not in seen["url"]


class TestTheQueryStaysOutOfTheSignature:
    async def test_a_shard_scoped_call_signs_the_path_only(self, tmp_path):
        """Kalshi signs the path; a signed query string is a 401.

        Observed while probing on 2026-08-30: a hand-rolled helper that folded
        `?ticker=...` into the signed string got
        `401 INCORRECT_API_KEY_SIGNATURE`, while the same call signing the bare
        path succeeded. The production client already gets this right -- this
        test is what keeps it right now that query parameters are reaching the
        order path for the first time.
        """
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["signed"] = request.headers.get("KALSHI-ACCESS-SIGNATURE")
            seen["url"] = str(request.url)
            return httpx.Response(200, json={})

        api = _client(handler, tmp_path)
        try:
            await api.balance(exchange_index=EXCHANGE_INDEX_COMBOS)
        finally:
            await api.client.aclose()

        from backend.kalshi.auth import SIGN_QUERY_STRING

        assert seen["signed"], "the request was not signed at all"
        assert f"{EXCHANGE_INDEX_PARAM}=1" in seen["url"]
        assert SIGN_QUERY_STRING is False, (
            "Kalshi signs the path only; turning this on 401s every "
            "shard-scoped call"
        )
