"""REST client tests.

No network. `respx` intercepts httpx, and the signing key is generated per-test
into `tmp_path` — the real key at `~/.kalshi/` is never touched, and a test run
can never depend on a credential existing.

The claims here are about the behaviours the previous project lacked entirely:
throttling handled rather than swallowed, transient failures retried and
permanent ones raised, and the signed string matching what was actually sent.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from backend.config import KalshiConfig
from backend.kalshi.auth import KalshiAuth, signed_path
from backend.kalshi.rest import (
    ORDERBOOK_KEY,
    KalshiAPIError,
    KalshiRestClient,
    MalformedOrderbookResponse,
)

BASE = "https://api.test.kalshi.com/trade-api/v2"


@pytest.fixture(scope="module")
def key_path(tmp_path_factory):
    """A throwaway RSA key. Small (1024) purely so tests stay fast."""
    path = tmp_path_factory.mktemp("keys") / "test_key.pem"
    key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return path


@pytest.fixture
def config(key_path):
    return KalshiConfig(
        api_key="test-key-id",
        private_key_path=key_path,
        rest_url=BASE,
        ws_url="wss://api.test.kalshi.com/trade-api/ws/v2",
    )


@pytest.fixture(scope="module")
def http_client():
    """One `httpx.AsyncClient` shared by the whole module.

    Constructing an AsyncClient costs ~500ms -- almost entirely SSL context
    setup (loading the CA bundle). Measured on this machine: 719ms cold,
    478ms warm. Creating one per test made this file take 12s.

    That measurement is also why `KalshiRestClient` insists on a single shared
    client in production. The previous project opened a fresh client per call
    inside a 100-request discovery loop, which is ~50 seconds of pure SSL
    handshake setup before any useful work.
    """
    client = httpx.AsyncClient(timeout=5.0)
    yield client
    # Nothing to await at module teardown; respx intercepts so no sockets open.


@pytest.fixture
def api(config, http_client):
    """Client with rate limiting and backoff disabled so tests stay fast."""
    client = KalshiRestClient(
        config, rate_limit_per_second=0, max_retries=3, client=http_client
    )
    client._backoff = lambda attempt: 0.0
    return client


class TestSigningContract:
    """Verified against the live API 2026-08-06. These lock the answer in."""

    def test_signs_the_full_path_including_the_api_prefix(self):
        assert signed_path(BASE, "/portfolio/balance") == "/trade-api/v2/portfolio/balance"

    def test_does_not_sign_the_query_string(self):
        """Signing the query returns 401 on a request that otherwise succeeds."""
        assert (
            signed_path(BASE, "/portfolio/fills", "limit=1")
            == "/trade-api/v2/portfolio/fills"
        )

    def test_prefix_is_derived_not_hardcoded(self):
        """A different deployment path must still sign correctly.

        `rstrip("/trade-api/v2")` would eat hostname characters here; this is
        why the prefix comes from urlsplit.
        """
        assert (
            signed_path("https://demo.kalshi.co/trade-api/v2/", "/markets")
            == "/trade-api/v2/markets"
        )

    @respx.mock
    async def test_query_is_sent_on_the_url_even_though_it_is_not_signed(self, api):
        route = respx.get(f"{BASE}/portfolio/fills").mock(
            return_value=httpx.Response(200, json={"fills": []})
        )
        async with api:
            await api.fills(limit=5)
        assert route.calls.last.request.url.params["limit"] == "5"

    @respx.mock
    async def test_auth_headers_are_present_on_every_request(self, api):
        route = respx.get(f"{BASE}/portfolio/balance").mock(
            return_value=httpx.Response(200, json={"balance": 0})
        )
        async with api:
            await api.balance()
        headers = route.calls.last.request.headers
        assert headers["KALSHI-ACCESS-KEY"] == "test-key-id"
        assert headers["KALSHI-ACCESS-SIGNATURE"]
        assert headers["KALSHI-ACCESS-TIMESTAMP"]


class TestRetrySemantics:
    """Throttling is handled, not swallowed. Permanent errors raise."""

    @respx.mock
    async def test_429_is_retried_and_then_succeeds(self, api):
        route = respx.get(f"{BASE}/portfolio/balance").mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "0"}),
                httpx.Response(200, json={"balance": 4200}),
            ]
        )
        async with api:
            assert await api.balance() == {"balance": 4200}
        assert route.call_count == 2

    @respx.mock
    async def test_retry_after_is_honoured(self, api, monkeypatch):
        slept: list[float] = []

        async def fake_sleep(seconds):
            slept.append(seconds)

        monkeypatch.setattr("backend.kalshi.rest.asyncio.sleep", fake_sleep)
        respx.get(f"{BASE}/portfolio/balance").mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "7"}),
                httpx.Response(200, json={}),
            ]
        )
        async with api:
            await api.balance()
        assert slept == [7.0]

    @respx.mock
    @pytest.mark.parametrize("status", [500, 502, 503, 504])
    async def test_server_errors_are_retried(self, api, status):
        route = respx.get(f"{BASE}/portfolio/balance").mock(
            side_effect=[httpx.Response(status), httpx.Response(200, json={})]
        )
        async with api:
            await api.balance()
        assert route.call_count == 2

    @respx.mock
    @pytest.mark.parametrize("status", [400, 403, 404])
    async def test_client_errors_are_not_retried(self, api, status):
        """Retrying a malformed request just produces four malformed requests."""
        route = respx.get(f"{BASE}/portfolio/balance").mock(
            return_value=httpx.Response(status)
        )
        async with api:
            with pytest.raises(KalshiAPIError):
                await api.balance()
        assert route.call_count == 1

    @respx.mock
    async def test_exhausted_retries_raise_rather_than_returning_empty(self, api):
        """The single most expensive habit in the previous codebase.

        Its discovery loop swallowed every exception and recorded throttled
        markets as illiquid ones -- a wrong answer that looked like data.
        """
        respx.get(f"{BASE}/portfolio/balance").mock(return_value=httpx.Response(429))
        async with api:
            with pytest.raises(KalshiAPIError) as exc:
                await api.balance()
        assert exc.value.status_code == 429

    @respx.mock
    async def test_401_error_names_the_ambiguity(self, api):
        """A 401 covers five different root causes. The message must say so."""
        respx.get(f"{BASE}/portfolio/balance").mock(return_value=httpx.Response(401))
        async with api:
            with pytest.raises(KalshiAPIError) as exc:
                await api.balance()
        text = str(exc.value)
        assert "verify_auth.py" in text
        assert "ED25519" in text

    @respx.mock
    async def test_connection_errors_are_retried(self, api):
        route = respx.get(f"{BASE}/portfolio/balance").mock(
            side_effect=[httpx.ConnectError("boom"), httpx.Response(200, json={})]
        )
        async with api:
            await api.balance()
        assert route.call_count == 2


class TestPagination:
    @respx.mock
    async def test_follows_the_cursor_to_the_end(self, api):
        respx.get(f"{BASE}/events").mock(
            side_effect=[
                httpx.Response(200, json={"events": [{"event_ticker": "A"}], "cursor": "c1"}),
                httpx.Response(200, json={"events": [{"event_ticker": "B"}], "cursor": ""}),
            ]
        )
        async with api:
            tickers = [e["event_ticker"] async for e in api.events()]
        assert tickers == ["A", "B"]

    @respx.mock
    async def test_a_truncated_walk_warns_that_it_is_partial(self, api, caplog):
        """A capped sweep that reads as complete is how a league is wrongly
        declared absent. It must say so."""
        respx.get(f"{BASE}/events").mock(
            return_value=httpx.Response(
                200, json={"events": [{"event_ticker": "A"}], "cursor": "always-more"}
            )
        )
        async with api:
            with caplog.at_level("WARNING"):
                _ = [e async for e in api.events(max_pages=2)]
        assert "PARTIAL" in caplog.text

    @respx.mock
    async def test_an_empty_page_ends_the_walk(self, api):
        respx.get(f"{BASE}/events").mock(
            return_value=httpx.Response(200, json={"events": [], "cursor": "x"})
        )
        async with api:
            assert [e async for e in api.events()] == []


class TestJunkFiltering:
    """KXMVE is ~99.8% of /markets and pure noise."""

    @respx.mock
    async def test_kxmve_events_are_dropped(self, api):
        respx.get(f"{BASE}/events").mock(
            return_value=httpx.Response(
                200,
                json={
                    "events": [
                        {"event_ticker": "KXMVE-JUNK", "markets": []},
                        {"event_ticker": "KXMLBGAME-26AUG09HOUSD", "markets": []},
                    ],
                    "cursor": "",
                },
            )
        )
        async with api:
            tickers = [e["event_ticker"] async for e in api.events()]
        assert tickers == ["KXMLBGAME-26AUG09HOUSD"]

    @respx.mock
    async def test_kxmve_markets_nested_in_a_real_event_are_dropped(self, api):
        respx.get(f"{BASE}/events").mock(
            return_value=httpx.Response(
                200,
                json={
                    "events": [
                        {
                            "event_ticker": "KXMLBGAME-26AUG09HOUSD",
                            "markets": [
                                {"ticker": "KXMVE-JUNK-1"},
                                {"ticker": "KXMLBGAME-26AUG09HOUSD-HOU"},
                            ],
                        }
                    ],
                    "cursor": "",
                },
            )
        )
        async with api:
            events = [e async for e in api.events()]
        assert [m["ticker"] for m in events[0]["markets"]] == [
            "KXMLBGAME-26AUG09HOUSD-HOU"
        ]


class TestClientLifecycle:
    async def test_using_the_client_outside_its_context_manager_raises(self, config):
        """A clear error beats an AttributeError on None three frames down.

        Built without an injected client on purpose -- an injected one is
        already open, so it would not exercise this guard.
        """
        unopened = KalshiRestClient(config)
        with pytest.raises(RuntimeError, match="context manager"):
            await unopened.balance()

    async def test_an_injected_client_is_not_closed_by_the_wrapper(
        self, config, http_client
    ):
        """We only close what we opened.

        Closing a caller's shared client on exit would break every other user
        of it -- and re-creating one costs ~500ms of SSL setup.
        """
        wrapper = KalshiRestClient(config, client=http_client)
        async with wrapper:
            pass
        assert not http_client.is_closed


class TestARenamedKeyIsLoudNotEmpty:
    """`payload.get(key) or []` collapsed two different situations.

    A **missing** key means Kalshi renamed the field. An **empty list** means
    there are genuinely no more results. Treating them alike turned a rename
    into "there are no events" — silently, on the path that feeds every price,
    with a 200 response and no error anywhere.

    `combos.py` already raises for exactly this case with exactly this
    reasoning. Same repo, opposite handling, and the weaker one was on the money
    path. This is the `data["yes"]` vs `yes_dollars_fp` failure that killed the
    WebSocket parser, one layer up.
    """

    @respx.mock
    async def test_a_renamed_key_raises(self, api):
        respx.get(f"{BASE}/events").mock(
            return_value=httpx.Response(
                200, json={"eventz": [{"event_ticker": "E"}], "cursor": ""}
            )
        )
        async with api as client:
            with pytest.raises(KalshiAPIError, match="renamed"):
                [e async for e in client.paginate("/events", "events")]

    @respx.mock
    async def test_the_error_names_what_was_actually_returned(self, api):
        """So the fix is one read away rather than a debugging session."""
        respx.get(f"{BASE}/events").mock(
            return_value=httpx.Response(200, json={"eventz": [], "cursor": ""})
        )
        async with api as client:
            with pytest.raises(KalshiAPIError) as excinfo:
                [e async for e in client.paginate("/events", "events")]
        assert "eventz" in str(excinfo.value)

    @respx.mock
    async def test_a_genuinely_empty_page_still_ends_cleanly(self, api):
        """The discriminating pair. An empty list is a normal end of results
        and must NOT raise, or every exhausted pagination becomes an error."""
        respx.get(f"{BASE}/events").mock(
            return_value=httpx.Response(200, json={"events": [], "cursor": ""})
        )
        async with api as client:
            assert [e async for e in client.paginate("/events", "events")] == []


class TestTheOrderbookEnvelope:
    """`orderbook()` read `payload["orderbook"]`; the wire key is
    `orderbook_fp`.

    With `or {}` behind it, that returned an empty book for **every market on
    the exchange** — including one carrying 21,000 contracts of open interest
    and a two-sided quote — and reported no error at all.

    Third time in this project: the predecessor's `data["yes"]` against
    `yes_dollars_fp`, `combos.py` reading the path-shaped
    `multivariate_event_collections` against the wire's
    `multivariate_contracts`, and this. Each returned something empty and
    plausible, which is indistinguishable from "there is none".

    The payload's *shape* is pinned against a real capture in
    `tests/test_quote_refresh.py`. These are about what the client does with it.
    """

    @respx.mock
    async def test_it_returns_the_book_under_the_key_kalshi_actually_sends(
        self, api
    ):
        respx.get(f"{BASE}/markets/T/orderbook").mock(
            return_value=httpx.Response(200, json={
                ORDERBOOK_KEY: {
                    "yes_dollars": [["0.5800", "552.00"]],
                    "no_dollars": [["0.0100", "1058328.00"]],
                }
            })
        )
        async with api:
            book = await api.orderbook("T")
        assert book["yes_dollars"] == [["0.5800", "552.00"]]
        assert book["no_dollars"] == [["0.0100", "1058328.00"]]

    @respx.mock
    async def test_a_renamed_envelope_raises_rather_than_reading_as_empty(
        self, api
    ):
        """The guard, and the exact payload the old code was happy with.

        This body has the *old* key, so the previous implementation returned
        `{}` from it and called that a book. An empty book is a legitimate state
        on this venue and a renamed field is not, so the two must not share a
        return value.
        """
        respx.get(f"{BASE}/markets/T/orderbook").mock(
            return_value=httpx.Response(200, json={
                "orderbook": {"yes_dollars": [], "no_dollars": []}
            })
        )
        async with api:
            with pytest.raises(MalformedOrderbookResponse) as raised:
                await api.orderbook("T")
        assert ORDERBOOK_KEY in str(raised.value)
        assert "T" in str(raised.value), "the message must name the market"

    @respx.mock
    async def test_a_genuinely_empty_book_is_returned_not_refused(self, api):
        """The state the refusal must NOT swallow.

        A real market nobody is quoting has empty level lists under the right
        key. Refusing that would trade one indistinguishable pair for another.
        """
        respx.get(f"{BASE}/markets/T/orderbook").mock(
            return_value=httpx.Response(200, json={
                ORDERBOOK_KEY: {"yes_dollars": [], "no_dollars": []}
            })
        )
        async with api:
            book = await api.orderbook("T")
        assert book == {"yes_dollars": [], "no_dollars": []}
