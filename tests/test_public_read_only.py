"""A credential-free instance reads market data and nothing else.

`KALSHI_PUBLIC_READ_ONLY=true` exists for the case ADR 0071 section 2.4 names:
somebody who cloned this repo and wants to see it work before deciding whether
to register for a Kalshi key. Kalshi serves market discovery, market data and
orderbooks unauthenticated -- measured by hand 2026-08-09 and re-verified
2026-08-24 -- and this repo signed them anyway, which made an API key the
price of looking at the thing at all.

**What these tests establish:** that the boundary is enforced in this process,
by an allowlist, before a socket opens; that a credential-free client sends no
headers rather than empty ones; and that the flag is an opt-in whose absence
leaves the old loud refusal exactly where it was.

**What they do not establish:** that Kalshi still serves those paths
unauthenticated. That is a fact about a third party on a given day, it was
re-measured against the live venue on 2026-08-24, and ADR 0012's pinned combo
endpoint proves a Kalshi path measured once is not a Kalshi path measured.
Nothing here would notice if `/markets` started demanding a signature; it
would surface as a 401 through the normal error path.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from backend.config import ConfigError, KalshiConfig
from backend.kalshi.rest import (
    PUBLIC_READ_PREFIXES,
    KalshiCredentialsRequired,
    KalshiRestClient,
    is_public_read,
)
from backend.kalshi.ws import KalshiWebSocket

BASE = "https://api.test.kalshi.com/trade-api/v2"


@pytest.fixture
def public_config():
    return KalshiConfig(
        api_key="",
        private_key_path=None,
        rest_url=BASE,
        ws_url="wss://api.test.kalshi.com/trade-api/ws/v2",
    )


@pytest.fixture
def public_api(public_config):
    client = httpx.AsyncClient(timeout=5.0)
    return KalshiRestClient(
        public_config, rate_limit_per_second=0, max_retries=0, client=client
    )


class TestTheAllowlistNamesReadsOnly:
    """`is_public_read` decides, and it decides on method AND path."""

    @pytest.mark.parametrize(
        "path",
        [
            "/markets",
            "/markets?limit=1",
            "/markets/KXNFLGAME-26-ABC",
            "/markets/KXNFLGAME-26-ABC/orderbook",
            "/events",
            "/events?status=open&limit=1",
        ],
    )
    def test_market_data_reads_are_public(self, path):
        assert is_public_read("GET", path) is True

    @pytest.mark.parametrize(
        "path",
        [
            "/portfolio/balance",
            "/portfolio/positions",
            "/portfolio/fills",
            "/portfolio/orders",
            "/exchange/status",
        ],
    )
    def test_account_reads_are_not(self, path):
        assert is_public_read("GET", path) is False

    def test_a_write_to_a_read_path_is_not_a_read(self):
        """A POST to `/markets` is not a market-data read.

        The combo lookup posts to `/multivariate_event_collections/{t}` and
        mints a market, which is the shape this guards against: the method
        carries as much of the privilege question as the path does.
        """
        assert is_public_read("POST", "/markets") is False
        assert is_public_read("DELETE", "/markets/X") is False

    def test_the_prefix_does_not_leak_across_a_word_boundary(self):
        """`/markets` must not admit `/marketsecret`.

        A bare `startswith` would. The check requires an exact match or a
        following slash, so a future private endpoint that happens to share
        seven characters with a public one stays refused.
        """
        assert is_public_read("GET", "/marketsecret") is False
        assert is_public_read("GET", "/events-private") is False

    def test_the_allowlist_holds_no_account_prefix(self):
        """A structural check, so an edit cannot widen this by accident."""
        for prefix in PUBLIC_READ_PREFIXES:
            assert not prefix.startswith("/portfolio")


class TestACredentiallessClientRefusesPrivatePaths:
    async def test_a_balance_read_raises_rather_than_401ing(self, public_api):
        """Refused in-process, so the reason is in the traceback.

        Letting it go and reading Kalshi's 401 back would also 'work'. It would
        put the reason in a response body, and a 401 in a log is attributed to
        a broken key far more often than to a client that never had one.
        """
        with pytest.raises(KalshiCredentialsRequired) as exc:
            await public_api.request("GET", "/portfolio/balance")
        assert "KALSHI_PUBLIC_READ_ONLY" in str(exc.value)

    async def test_the_order_path_is_refused(self, public_api):
        """The one that must never work. `POST /portfolio/orders` spends money."""
        with pytest.raises(KalshiCredentialsRequired):
            await public_api.request(
                "POST", "/portfolio/orders", json_body={"ticker": "X"}
            )

    async def test_no_socket_is_opened(self, public_api):
        """The refusal precedes the transport, not just the response.

        `respx` asserts it: with no route registered, any request that reached
        httpx would raise `AllMockedAssertionError` instead of the credential
        error. Reaching the transport would also mean four retries with
        backoff on a failure that can never become a success.
        """
        with respx.mock(assert_all_called=False):
            with pytest.raises(KalshiCredentialsRequired):
                await public_api.request("GET", "/portfolio/positions")


class TestACredentiallessClientReadsMarketData:
    async def test_a_public_read_is_sent_with_no_auth_headers(self, public_api):
        """No headers at all -- not empty ones, not a blank signature."""
        seen: dict = {}

        def _capture(request):
            seen.update(request.headers)
            return httpx.Response(200, json={"markets": []})

        with respx.mock:
            respx.get(f"{BASE}/markets").mock(side_effect=_capture)
            await public_api.request("GET", "/markets", params={"limit": 1})

        assert "kalshi-access-key" not in seen
        assert "kalshi-access-signature" not in seen
        assert "kalshi-access-timestamp" not in seen

    async def test_an_orderbook_read_is_allowed(self, public_api):
        with respx.mock:
            respx.get(f"{BASE}/markets/ABC/orderbook").mock(
                return_value=httpx.Response(200, json={"orderbook": {}})
            )
            out = await public_api.request("GET", "/markets/ABC/orderbook")
        assert out == {"orderbook": {}}


class TestTheFlagIsAnOptInNotAFallback:
    """A missing key stays loud unless somebody asked for public reads.

    This is the whole safety argument. Live must never silently degrade to
    public reads: the runner would look healthy while writing no portfolio, no
    fills and no settlements -- the failure `docker/entrypoint.sh:110-116`
    refuses to start into.
    """

    def test_the_flag_yields_a_credentialless_config(self, monkeypatch):
        monkeypatch.setenv("KALSHI_PUBLIC_READ_ONLY", "true")
        monkeypatch.delenv("KALSHI_API_KEY", raising=False)
        monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)

        cfg = KalshiConfig.load()

        assert cfg.private_key_path is None
        assert cfg.is_public_read_only is True
        assert cfg.api_key == ""

    def test_without_the_flag_a_missing_key_still_raises(self, monkeypatch):
        monkeypatch.delenv("KALSHI_PUBLIC_READ_ONLY", raising=False)
        monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)
        monkeypatch.delenv("KALSHI_API_KEY", raising=False)

        with pytest.raises(ConfigError):
            KalshiConfig.load()

    def test_a_configured_instance_is_not_public_read_only(self, tmp_path):
        cfg = KalshiConfig(
            api_key="k",
            private_key_path=tmp_path / "key.pem",
            rest_url=BASE,
            ws_url="wss://x",
        )
        assert cfg.is_public_read_only is False


class TestTheTickerHasNoPublicHalf:
    def test_the_socket_refuses_at_construction(self, public_config):
        """Kalshi authenticates the WebSocket at the handshake.

        So unlike REST there is no subset a credential-free instance can
        reach, and the honest place to say so is construction -- not a
        traceback about a missing PEM three frames down.
        """
        with pytest.raises(KalshiCredentialsRequired) as exc:
            KalshiWebSocket(public_config, tickers=["ABC"])
        assert "KALSHI_PUBLIC_READ_ONLY" in str(exc.value)
