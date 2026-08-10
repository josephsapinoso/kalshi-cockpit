"""Async Kalshi REST client.

The previous project had **none** of what this module exists for: no rate
limiting, no 429 handling, no `Retry-After`, no retry, and a fresh
`httpx.Client` per call. Its discovery routine fired up to 100 sequential
requests inside a bare `except Exception: continue`, which meant a throttled
market was recorded as an *illiquid* one — a wrong answer that looked like
data rather than like an error.

Three rules this module enforces:

**One shared client.** A new connection pool per request throws away TLS
sessions and keep-alives, and on Windows it eventually exhausts ephemeral
ports. But the dominant cost is blunter than either: **constructing an
`httpx.AsyncClient` takes ~500ms**, almost entirely SSL-context setup. Measured
on this machine, 719ms cold and 478ms warm. The previous project's discovery
routine opened a fresh client inside a loop of up to 100 sequential requests --
roughly **50 seconds of pure handshake setup** before any useful work. The
client here is created once and reused, and callers may inject their own.

**Throttling is not an error to swallow.** A 429 is honoured with its
`Retry-After` and then retried. A request that ultimately fails raises, loudly,
carrying the status and URL. Nothing here ever returns a plausible-looking
empty result to paper over a failure — that is the single most expensive habit
in the previous codebase.

**Sign the path, send the query.** Verified 2026-08-06: signing the query
string returns 401 on a request that succeeds when signed without it. All
signing goes through `auth.signed_path`, which derives the API prefix with
`urlsplit` so the signed string cannot drift from the requested URL.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any, AsyncIterator, Optional
from urllib.parse import urlencode

import httpx

from ..config import KalshiConfig
from .auth import KalshiAuth, signed_path

logger = logging.getLogger(__name__)

# Smallest delay honoured from a `Retry-After` header. Zero is legal and
# means "immediately", which against a server that just throttled us is a
# hot retry loop.
_MIN_RETRY_AFTER_S = 0.5

# Kalshi's documented read limit on the basic tier is ~10 requests/second. We
# sit deliberately under it: the cost of being slightly slow is nothing, and
# the cost of being throttled mid-sweep is a partial universe that looks
# complete.
DEFAULT_RATE_LIMIT_PER_SECOND = 8.0
DEFAULT_MAX_RETRIES = 4
DEFAULT_TIMEOUT_S = 30.0
DEFAULT_PAGE_LIMIT = 200

# Retried: transient. Not retried: anything that means the request itself is
# wrong, because retrying a 400 just produces four 400s.
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})

JUNK_PREFIX = "KXMVE"

# The envelope `/markets/{ticker}/orderbook` actually returns. Pinned as a
# constant so a test can assert it against a captured payload rather than
# against whoever last remembered it -- this is the third time in this project a
# plausible-but-wrong wire key has returned something empty and plausible.
ORDERBOOK_KEY = "orderbook_fp"


class MalformedOrderbookResponse(RuntimeError):
    """The orderbook envelope was not where it was expected.

    Separate from `KalshiAPIError` because the request *succeeded*: this is a
    200 whose shape we cannot read, which needs the opposite response to a 500.
    """


class KalshiAPIError(RuntimeError):
    """A Kalshi request failed in a way we could not recover from."""

    def __init__(self, status_code: int, url: str, body: str = ""):
        self.status_code = status_code
        self.url = url
        self.body = body[:500]
        hint = ""
        if status_code == 401:
            hint = (
                " -- 401 from Kalshi is ambiguous: it covers a bad key id, an "
                "ED25519 key where RSA is required, a bare (unprefixed) signed "
                "path, a signed query string, and clock skew. Run "
                "scripts/verify_auth.py rather than guessing."
            )
        super().__init__(f"HTTP {status_code} from {url}{hint}\n{self.body}")


class _RateLimiter:
    """Minimum-interval limiter, shared across all requests on one client.

    Deliberately simple. A token bucket would allow bursts, and a burst is
    exactly what triggers throttling on a universe sweep.
    """

    def __init__(self, per_second: float):
        self._min_interval = 1.0 / per_second if per_second > 0 else 0.0
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        if self._min_interval <= 0:
            return
        async with self._lock:
            wait = self._last + self._min_interval - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()


class KalshiRestClient:
    """Async Kalshi REST client. Use as an async context manager."""

    def __init__(
        self,
        config: KalshiConfig,
        auth: Optional[KalshiAuth] = None,
        *,
        rate_limit_per_second: float = DEFAULT_RATE_LIMIT_PER_SECOND,
        max_retries: int = DEFAULT_MAX_RETRIES,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        client: Optional[httpx.AsyncClient] = None,
    ):
        self.config = config
        self.auth = auth or KalshiAuth(config.api_key, config.private_key_path)
        self.base_url = config.rest_url.rstrip("/")
        self.max_retries = max_retries
        self._limiter = _RateLimiter(rate_limit_per_second)
        self._client = client
        self._owns_client = client is None
        self._timeout = timeout_s

    async def __aenter__(self) -> "KalshiRestClient":
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
            self._owns_client = True
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError(
                "KalshiRestClient used outside its context manager. "
                "Use `async with KalshiRestClient(cfg) as api:`."
            )
        return self._client

    # -- request -----------------------------------------------------------

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
    ) -> dict:
        """Make a signed request, retrying transient failures.

        `path` is the endpoint below the API prefix, e.g. `/portfolio/balance`.
        The prefix is added by `signed_path`, derived from `base_url`.
        """
        query = urlencode({k: v for k, v in (params or {}).items() if v is not None})
        url = f"{self.base_url}{path}" + (f"?{query}" if query else "")

        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            await self._limiter.acquire()

            # Signed fresh each attempt: the timestamp is part of the signed
            # message, and a retry after a long backoff would otherwise present
            # a stale timestamp and fail as a clock-skew 401.
            headers = self.auth.get_rest_headers(
                method, signed_path(self.base_url, path, query)
            )

            try:
                response = await self.client.request(
                    method, url, headers=headers, json=json_body
                )
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise
                delay = self._backoff(attempt)
                logger.warning(
                    "%s %s: %s -- retrying in %.1fs (attempt %d/%d)",
                    method, path, type(exc).__name__, delay,
                    attempt + 1, self.max_retries,
                )
                await asyncio.sleep(delay)
                continue

            if response.status_code < 400:
                return response.json() if response.content else {}

            if response.status_code in _RETRY_STATUSES and attempt < self.max_retries:
                delay = self._retry_delay(response, attempt)
                logger.warning(
                    "%s %s: HTTP %d -- retrying in %.1fs (attempt %d/%d)",
                    method, path, response.status_code, delay,
                    attempt + 1, self.max_retries,
                )
                await asyncio.sleep(delay)
                continue

            # Not transient, or retries exhausted. Raise -- never return an
            # empty dict that a caller could mistake for "no data".
            raise KalshiAPIError(response.status_code, url, response.text)

        raise KalshiAPIError(-1, url, f"exhausted retries: {last_error}")

    def _backoff(self, attempt: int) -> float:
        """Exponential backoff with full jitter, capped at 60s.

        Jitter matters even for a single client: without it, every retry after
        a shared outage fires on the same schedule and re-creates the burst
        that caused the throttling. The previous project's WebSocket backoff
        had no jitter.
        """
        return random.uniform(0, min(60.0, 0.5 * (2**attempt)))

    def _retry_delay(self, response: httpx.Response, attempt: int) -> float:
        """Honour `Retry-After` when the server sends one, else back off."""
        header = response.headers.get("Retry-After")
        if header:
            try:
                # Floored, not just capped. `Retry-After: 0` is legal and means
                # "try again now", which against a server that has just
                # throttled us is a hot loop -- the exact behaviour the 429
                # handling exists to prevent. A negative value is nonsense and
                # would compute a negative sleep.
                return min(60.0, max(_MIN_RETRY_AFTER_S, float(header)))
            except ValueError:
                pass  # HTTP-date form; fall through to backoff
        return self._backoff(attempt)

    async def get(self, path: str, **params: Any) -> dict:
        return await self.request("GET", path, params=params)

    async def post(self, path: str, json_body: dict) -> dict:
        return await self.request("POST", path, json_body=json_body)

    async def delete(self, path: str, **params: Any) -> dict:
        return await self.request("DELETE", path, params=params)

    # -- pagination --------------------------------------------------------

    async def paginate(
        self,
        path: str,
        key: str,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        max_pages: Optional[int] = None,
        **params: Any,
    ) -> AsyncIterator[dict]:
        """Cursor-paginate an endpoint, yielding items from `key`.

        `max_pages=None` means "walk until the cursor runs out". Pass a number
        only when a partial answer is genuinely acceptable — and if you do,
        **say so in the result**, because a truncated sweep that reads as
        complete is how a league gets wrongly declared absent.
        """
        cursor = ""
        page = 0
        while True:
            payload = await self.get(path, limit=limit, cursor=cursor or None, **params)

            # A MISSING key is a renamed field; an EMPTY list is a real end of
            # results. `payload.get(key) or []` collapsed the two, so a Kalshi
            # rename would have turned the whole discovery path into "there are
            # no events" -- silently, on the critical path, with a 200 response.
            #
            # `combos.py` already raises for exactly this case, with exactly
            # this reasoning. Same repo, opposite handling, and the weaker one
            # was on the path that feeds every price.
            if key not in payload:
                raise KalshiAPIError(
                    200,
                    path,
                    f"response has no {key!r} key (got {sorted(payload)}). "
                    f"The field was renamed; refusing to return an empty page "
                    f"that would read as 'no results'.",
                )

            items = payload[key] or []
            if not items:
                return
            for item in items:
                yield item

            page += 1
            cursor = payload.get("cursor") or ""
            if not cursor:
                return
            if max_pages is not None and page >= max_pages:
                logger.warning(
                    "paginate(%s) stopped at the %d-page cap with the cursor "
                    "still advancing -- this result is PARTIAL",
                    path, max_pages,
                )
                return

    # -- market data -------------------------------------------------------

    async def events(
        self,
        *,
        status: str = "open",
        series_ticker: Optional[str] = None,
        with_nested_markets: bool = True,
        max_pages: Optional[int] = None,
    ) -> AsyncIterator[dict]:
        """Walk `/events`. **This is the only sane way to see the universe.**

        Never paginate `/markets`: it is ~99.8% `KXMVE` pre-generated
        combination markets. Note what that does and does not mean --
        `KXMVE` is Multi-Variate Event, Kalshi's *combo product*, and it is
        real (see `kalshi/combos.py`). What is junk is the pre-generated
        markets clogging this endpoint, not the product. Discover combos via
        `/multivariate_event_collections`, never by paginating here.

        A 25,000-row scan of `/markets` returned zero markets with any volume,
        while one `/events` call returns ~1,500 real markets.

        `KXMVE` events are filtered here so no caller has to remember to. That
        filter is about *discovery hygiene* and must not be read as a claim
        that combos do not exist -- an earlier version of this project drew
        exactly that inference and built a parlay module on it.
        """
        params: dict[str, Any] = {"status": status}
        if with_nested_markets:
            params["with_nested_markets"] = "true"
        if series_ticker:
            params["series_ticker"] = series_ticker

        async for event in self.paginate(
            "/events", "events", max_pages=max_pages, **params
        ):
            if (event.get("event_ticker") or "").startswith(JUNK_PREFIX):
                continue
            if event.get("markets"):
                event["markets"] = [
                    m
                    for m in event["markets"]
                    if not (m.get("ticker") or "").startswith(JUNK_PREFIX)
                ]
            yield event

    async def markets_for_event(self, event_ticker: str) -> list[dict]:
        """Markets for one event. Complete, or it raises.

        Needed because **settled events do not carry nested markets** — for
        history you must walk events first, then fetch markets per event.

        This used to send no `limit` and read one page, which meant it silently
        took Kalshi's default and had no way to know it had been truncated. Both
        halves of that were measured on 2026-08-09 with free unauthenticated
        GETs:

        - `/markets` with no `limit` returns **100** rows and a non-empty
          `cursor`. So the default is 100, not 200, and it is a real ceiling.
        - `limit` is capped at 1000; `limit=1001` is HTTP 400.
        - **`?event_ticker=` ignores `limit` entirely and returns the whole
          event with an empty cursor.** `KXWC-30` returns all 82 of its markets
          for `limit=1`, `limit=10` and no limit alike. The largest event
          observed anywhere was 82, so nothing in scope is near a page.

        Paginating anyway, for one request's worth of nothing: with an empty
        cursor `paginate` returns after a single call, so the normal cost is
        unchanged, and if Kalshi ever does start paging this filter the tail
        cannot go missing. A truncated answer here would not look like an error
        — the missing markets would be counted `still_unresolved` by
        `market_results.py` and re-queried on every pass, forever.

        `paginate` also **raises when the `markets` key is absent** rather than
        returning an empty list, which the hand-rolled `payload.get("markets")
        or []` this replaces did not. A renamed envelope reading as "this event
        has no markets" is this repo's most-repeated defect.
        """
        return [
            m
            async for m in self.paginate(
                "/markets", "markets", event_ticker=event_ticker
            )
            if not (m.get("ticker") or "").startswith(JUNK_PREFIX)
        ]

    async def orderbook(self, ticker: str, depth: int = 10) -> dict:
        """Order book for one market. Raises rather than returning an empty one.

        Remember the book publishes **YES bids and NO bids only**. Asks are
        derived (`store.db.derive_yes_ask`), and depth on the "ask" side is
        really the opposing bid's quantity.

        **The envelope key is `orderbook_fp`, and this method used to read
        `orderbook`.** It therefore returned `{}` for every market on the
        exchange — including one carrying 21,000 contracts of open interest and
        a two-sided quote — with no error, because `or {}` turned the miss into
        an empty book. Nothing called it, which is the only reason it cost
        nothing; the day something had, it would have reported the whole venue
        as unquotable.

        That is this repo's most-repeated defect, now three times over: the
        predecessor's `data["yes"]` against `yes_dollars_fp`, `combos.py`
        reading the path-shaped `multivariate_event_collections` against the
        wire's `multivariate_contracts`, and this. A plausible-but-wrong key
        returning empty is indistinguishable from "there is none".

        So a missing envelope **raises**. An empty book is a legitimate state
        and a renamed field is not, and the two must not share a return value.
        The sides themselves are `yes_dollars` / `no_dollars`, each a list of
        `[price_string, size_string]` — note they are *not* the socket's names,
        which is the assumption that started all of this.
        """
        payload = await self.get(f"/markets/{ticker}/orderbook", depth=depth)
        book = payload.get(ORDERBOOK_KEY)
        if book is None:
            raise MalformedOrderbookResponse(
                f"{ticker}: /markets/{{ticker}}/orderbook has no "
                f"{ORDERBOOK_KEY!r} key (got {sorted(payload)}). Kalshi renamed "
                f"the envelope; refusing to return an empty book that would "
                f"read as 'nobody is quoting this market'."
            )
        return book

    async def candlesticks(
        self,
        series_ticker: str,
        ticker: str,
        *,
        start_ts: int,
        end_ts: int,
        period_interval: int = 60,
    ) -> list[dict]:
        """Historical bid/ask at a fixed horizon. **The CLV primitive.**

        The only way to read a *past* Kalshi quote. Timestamps are epoch
        SECONDS here (Kalshi's convention on this endpoint), not the
        milliseconds used everywhere else in this codebase — convert at the
        call site and do not propagate the difference.

        Do not substitute `last_price`: the last trade in a settled market
        usually happens *after* the outcome is effectively known, so anything
        measured against it is convergence rather than edge.
        """
        payload = await self.get(
            f"/series/{series_ticker}/markets/{ticker}/candlesticks",
            start_ts=start_ts,
            end_ts=end_ts,
            period_interval=period_interval,
        )
        return payload.get("candlesticks") or []

    # -- portfolio ---------------------------------------------------------

    async def balance(self) -> dict:
        return await self.get("/portfolio/balance")

    async def positions(self) -> list[dict]:
        payload = await self.get("/portfolio/positions")
        return payload.get("market_positions") or []

    async def orders(
        self, *, ticker: Optional[str] = None, status: Optional[str] = None
    ) -> list[dict]:
        payload = await self.get("/portfolio/orders", ticker=ticker, status=status)
        return payload.get("orders") or []

    async def fills(
        self, *, ticker: Optional[str] = None, limit: int = 100
    ) -> list[dict]:
        """Recent fills.

        A real fill is the only ground truth for the fee model, and the only
        way to close the open question in `core/fees.py`.

        **The per-fill wire shape has never been observed on this account.**
        Probed against production on 2026-08-09: the envelope is measured and
        correct (`{"cursor": str, "fills": list}`, so the `payload.get("fills")`
        below reads the right key), and the account holds **zero fills**, so
        every field *inside* a record is unobserved -- including whether the fee
        is called `fee`, what units it carries, and whether it is per-contract
        or per-order.

        This docstring previously named `fee` as ground truth as though the
        field had been seen. It had not; the name was inherited from the
        predecessor project. That is the shape behind the four wrong wire keys
        in this repo's history, each of which returned a well-formed empty
        result that satisfied every test written about its contents.

        Run `scripts/capture_fills_fixture.py` the moment fills exist -- before
        writing any parser against them.
        """
        payload = await self.get("/portfolio/fills", ticker=ticker, limit=limit)
        return payload.get("fills") or []
