"""Reading one market's current book, at the instant an order is decided.

Why this exists
---------------
The recorder writes a row, and the row carries the price it saw. Between that
write and someone tapping *confirm* on a phone, the price is a memory. Two
mechanisms already narrow the gap and neither closes it:

- the quote pass re-derives every decision every fifteen seconds while the
  window is open, so a row is at most fifteen seconds stale rather than fifteen
  minutes (`runner.run_quote_pass`);
- `gate.live_ages` refuses anything past thirty seconds.

Fifteen seconds is not zero on a venue quoted by sub-200ms market makers, and
"refuse if the *record* is old" is a different claim from "the price you are
about to pay is this". This module makes the second claim: one signed GET
against `/markets/{ticker}`, parsed by discovery's own reader, returning the
book as it is now.

What it deliberately does not do
--------------------------------
It does not re-devig, re-link, or re-run suppression. The fair value behind a
recommendation comes from a sportsbook consensus that is metered at ~16 credits
a day and is *not* refreshed here; the order endpoint re-derives size and EV
against the stored fair value at the live ask, and the consensus's own age
still binds through the staleness contract. Refreshing the Kalshi half of a
comparison is not the same as refreshing both, and pretending otherwise would
let a row live forever on an aged-out consensus -- the exact half-fix
`engine.confirm_recommendation` documents.

The wire format
---------------
`GET /markets/{ticker}` returns `{"market": {...}}`. Both the envelope and the
field names are pinned by `tests/fixtures/market_single.json`, captured with
`scripts/capture_market_fixture.py`, which stores the *same* ticker as `/events`
returns it beside the single-market payload so a rename in one and not the other
fails a test. A missing envelope key raises rather than resolving to an empty
quote: a plausible-but-wrong key returning nothing is indistinguishable from a
market with no book, and this project has been caught by that twice.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from ..config import KalshiConfig
from ..store.db import ask_for_side
from .discovery import DiscoveredMarket, build_market
from .rest import KalshiAPIError, KalshiRestClient

logger = logging.getLogger(__name__)

# The scope classification (`moneyline` / `spread` / `total`) is a property of
# the event, decided when the recommendation was written. A refresh answers
# "what is this market's book now?" and re-classifying it here would be a second
# opinion about something already settled -- and a second place to be wrong.
REFRESH_MARKET_TYPE = "quote_refresh"

# Kalshi's own word for a market open for trading. An allowlist of one, so an
# unrecognised status refuses rather than falling through to tradeable.
#
# Settled markets report **`finalized`**, not `settled` -- verified in the
# discovery capture and recorded in `.claude/skills/kalshi-api/SKILL.md`.
# Worth spelling out because a test written against the plausible-sounding
# word proves only that *some* other string is refused, which is true of any
# allowlist and equally true of a typo.
TRADEABLE_STATUS = "active"


class QuoteUnavailable(RuntimeError):
    """No usable quote could be read. The caller must refuse, never substitute.

    Deliberately one exception for every cause -- unreachable API, renamed
    field, closed market. The caller's decision is identical in all of them and
    is the whole point: an order priced from a quote nobody could read is an
    order priced from the recorded one, which is what this module exists to
    stop.
    """

    def __init__(self, message: str, *, permanent: bool = False) -> None:
        super().__init__(message)
        # Whether retrying could ever help. One exception type, because the
        # *refusal* is the same either way -- but a 404 for a ticker the
        # exchange has never heard of served as "try again" tells whoever is
        # holding the phone to keep tapping something that will never work.
        self.permanent = permanent


@dataclass(frozen=True)
class LiveQuote:
    """One market's book, and when it was observed.

    Wraps a `DiscoveredMarket` rather than restating its fields, so the live
    refresh and the recorder cannot come to disagree about what a quote is.
    """

    market: DiscoveredMarket
    observed_ms: int

    @property
    def ticker(self) -> str:
        return self.market.ticker

    @property
    def status(self) -> Optional[str]:
        return self.market.status

    @property
    def tradeable(self) -> bool:
        return self.market.status == TRADEABLE_STATUS

    @property
    def price_grid(self):
        """Which limit prices this market accepts right now, or None.

        Read from the same payload as the book, at the same instant, rather than
        from the recorded row. A market's `price_level_structure` can change
        while it is open -- Kalshi publishes a `price_level_structure_updated`
        lifecycle event -- so a grid cached at recommendation time is exactly as
        stale as the price beside it, and this module exists because that
        staleness matters.
        """
        return self.market.price_grid

    def age_ms(self, now_ms: int) -> int:
        """How old this observation is. Normally a round trip, never negative.

        `observed_ms` is stamped by *this* process **before the request is
        issued**, not when the response lands. That direction is deliberate: the
        book state in the response could have been formed at any point during
        the round trip, so measuring from the earlier instant overstates the age
        rather than flattering it. The consequence is that this is never less
        than one round trip -- which is worth knowing, because it means the
        Kalshi arm of the freshness check is now near-unfailable against a 30s
        limit. What still binds is the odds age.

        Clamped at zero, and this is the one place clamping is right: the
        timestamp is ours, so a negative value would mean our own clock moved
        backwards. The dangerous direction -- a foreign timestamp flattering the
        age -- cannot arise from a number we wrote.
        """
        return max(0, now_ms - self.observed_ms)

    def ask_tenths(self, side: str) -> Optional[int]:
        """The derived ask for `side`, or None if the opposing bid is unreadable.

        Goes through `store.db.ask_for_side`, the same function the runner uses
        against a stored quote row, so "the price you would pay" has exactly one
        definition in this codebase.
        """
        return ask_for_side(
            {
                "yes_bid_tenths": self.market.yes_bid_tenths,
                "no_bid_tenths": self.market.no_bid_tenths,
            },
            side,
        )

    def depth_at_ask(self, side: str) -> Optional[float]:
        """Size resting at `side`'s ask -- what could actually be lifted.

        The crossover is easy to get backwards and produces plausible numbers
        when you do: a YES ask is `1 - no_bid`, so it is filled by the resting
        NO bid, and the size at the YES ask is therefore the NO-bid size. That
        is what `DiscoveredMarket.yes_ask_size` already holds, so this is a
        lookup rather than a re-derivation.
        """
        if side == "yes":
            return self.market.yes_ask_size
        if side == "no":
            return self.market.no_ask_size
        raise ValueError(f"side must be 'yes' or 'no', got {side!r}")


def parse_market_quote(payload: dict[str, Any], *, observed_ms: int) -> LiveQuote:
    """`GET /markets/{ticker}` -> a quote. Raises rather than returning empty.

    The envelope check is the load-bearing line. `payload.get("market") or {}`
    would turn a renamed key into a market with no bids, which the caller reads
    as "no book" and refuses -- correct behaviour for the wrong reason, and
    silent forever. `paginate` in `rest.py` makes the same distinction for the
    same reason.
    """
    if "market" not in payload:
        raise QuoteUnavailable(
            f"response has no 'market' key (got {sorted(payload)}). The field "
            f"was renamed; refusing to return an empty quote that would read as "
            f"'this market has no book'."
        )
    market = payload["market"]
    if not isinstance(market, dict) or not market.get("ticker"):
        raise QuoteUnavailable(
            "response carried a 'market' that is not a market object with a "
            "ticker. Refusing rather than parsing it to a book of Nones."
        )
    return LiveQuote(
        market=build_market(market, market_type=REFRESH_MARKET_TYPE),
        observed_ms=observed_ms,
    )


class LiveQuoteSource:
    """Fetches a live quote for one ticker. Owns a shared HTTP client.

    **One client, built lazily.** Constructing an `httpx.AsyncClient` costs
    ~500ms, almost all of it SSL context setup (`tasks/lessons.md`), which on a
    thirty-second freshness limit is real. Lazily, because the demo instance
    holds no Kalshi credentials and must still start: `create_app` runs on both
    deploys from one image, and a source constructed eagerly would take the
    public demo down to support a route the demo does not expose.
    """

    def __init__(
        self,
        config: Optional[KalshiConfig] = None,
        *,
        rest: Optional[KalshiRestClient] = None,
        timeout_s: float = 5.0,
    ) -> None:
        self._config = config
        self._client: Optional[httpx.AsyncClient] = None
        # A supplied client is not ours to build or to close. Passing one is how
        # the refusals below get tested without a credential or a socket --
        # otherwise "the response is about the ticker we asked for" is a branch
        # nothing can reach, which is the same as not having written it.
        self._rest: Optional[KalshiRestClient] = rest
        self._owns_client = rest is None
        # Shorter than the REST default. An order is a person waiting with a
        # thumb over a button, and a refusal they can retry beats a spinner that
        # resolves after the quote it was fetching has expired.
        self._timeout_s = timeout_s

    def _api(self) -> KalshiRestClient:
        if self._rest is None:
            config = self._config or KalshiConfig.load()
            self._client = httpx.AsyncClient(timeout=self._timeout_s)
            self._rest = KalshiRestClient(config, client=self._client)
        return self._rest

    async def fetch(self, ticker: str, *, observed_ms: int) -> LiveQuote:
        """Read `ticker`'s book now, or raise.

        Every failure -- transport, HTTP status, renamed field -- becomes
        `QuoteUnavailable`. The caller has one correct response to all of them
        and giving it three exception types to catch is how one of them ends up
        uncaught on the money path.

        `ConfigError` is the deliberate exception, and it is raised from outside
        the `try` so it stays itself. "The exchange did not answer" and "this
        instance has no credentials" both stop the order, but only one of them
        is worth retrying, and collapsing them would tell whoever is holding the
        phone to keep tapping.
        """
        api = self._api()
        try:
            payload = await api.get(f"/markets/{ticker}")
        except KalshiAPIError as exc:
            logger.warning("live quote refresh failed for %s: %s", ticker, exc)
            raise QuoteUnavailable(
                f"could not read a live quote for {ticker}: {exc}",
                # A 404 means the exchange has never heard of this ticker, and
                # no amount of waiting changes that.
                permanent=exc.status_code in (400, 404),
            ) from exc
        except Exception as exc:                                # noqa: BLE001
            logger.warning("live quote refresh failed for %s: %s", ticker, exc)
            raise QuoteUnavailable(
                f"could not read a live quote for {ticker}: {exc}"
            ) from exc

        quote = parse_market_quote(payload, observed_ms=observed_ms)
        if quote.ticker != ticker:
            # A response about a different market is not a transport failure,
            # it is a correctness failure, and pricing an order off it would be
            # buying the wrong thing at the right-looking price.
            raise QuoteUnavailable(
                f"asked for {ticker} and got {quote.ticker!r}. Refusing."
            )
        return quote

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None
            self._rest = None
