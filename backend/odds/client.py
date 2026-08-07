"""The Odds API v4 client.

Fetches sportsbook prices, records what each call cost, and stamps every price
with two separate ages.

**Two ages, not one.** `fetched_ms` is when *we* asked. `book_updated_ms` is
the bookmaker's own `last_update`. They are different numbers and the second
one usually matters more: a book that has not repriced in twenty minutes is
stale even if we fetched it a second ago. Devigging a stale book against a live
Kalshi quote manufactures edge out of nothing, and it does so most reliably
right before kickoff -- exactly when the number looks most attractive.

**Odds are stored raw, one row per bookmaker per outcome.** Devigging is a
derived view, computed later and never destructive. The moment we store only a
consensus we lose the ability to re-run with a different method, and method
choice moves the answer by more than the entire fee advantage.

Prices are requested in **decimal** format. American odds need a sign-dependent
conversion with a discontinuity at +/-100, and every such conversion is a place
to introduce an error that looks like edge.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

import httpx

from ..config import OddsConfig
from .budget import CreditBudget, sweep_cost

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 20.0

# Books that take size from professionals and move first. Used to anchor the
# fair line where present -- see core/devig.py. Not a filter: every book is
# stored, this only marks which ones carry more weight.
SHARP_BOOKS = frozenset({"pinnacle", "betonlineag", "lowvig", "circasports"})


class OddsAPIError(RuntimeError):
    def __init__(self, status_code: int, url: str, body: str = ""):
        self.status_code = status_code
        self.body = body[:400]
        hint = ""
        if status_code == 401:
            hint = " -- check ODDS_API_KEY"
        elif status_code == 422:
            hint = " -- usually an unknown sport key, market, or region"
        elif status_code == 429:
            hint = " -- monthly credit quota exhausted, not a rate limit"
        super().__init__(f"HTTP {status_code} from {url}{hint}\n{self.body}")


class QuotaExhausted(OddsAPIError):
    """The monthly credit allowance is gone. Not retryable this period."""


def parse_ms(value: Any) -> Optional[int]:
    """ISO-8601 to epoch milliseconds, UTC. Unreadable returns None, never 0."""
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.astimezone(timezone.utc).timestamp() * 1000)
    except (ValueError, TypeError):
        return None


@dataclass(frozen=True)
class OddsQuote:
    """One bookmaker's price on one outcome. Stored raw."""

    fetched_ms: int
    book_updated_ms: Optional[int]
    sport_key: str
    odds_event_id: str
    commence_ms: int
    home_team: str
    away_team: str
    bookmaker: str
    market: str            # h2h | spreads | totals
    outcome_name: str      # team name, or Over/Under
    outcome_point: Optional[float]
    price_decimal: float

    @property
    def implied_probability(self) -> float:
        """Raw implied probability, vig included. Devigging happens elsewhere."""
        return 1.0 / self.price_decimal

    def age_ms(self, now_ms: int) -> int:
        """Staleness measured from the **book's** update, not our fetch.

        Falls back to our fetch time only when the book gave us nothing, and
        that fallback is optimistic -- treat a missing `last_update` as a
        reason for suspicion rather than freshness.
        """
        basis = self.book_updated_ms if self.book_updated_ms is not None else self.fetched_ms
        return now_ms - basis

    @property
    def is_sharp(self) -> bool:
        """Whether this book anchors the consensus.

        `@property`, and that matters more than it looks. It sat between two
        properties as a plain method, so `if quote.is_sharp` -- the way anyone
        would write it, and the way its neighbours are correctly used -- binds a
        method object and is **truthy for every book**. A live capture surfaced
        it: all 30 bookmakers in an MLB payload reported as sharp, including
        FanDuel and DraftKings.

        Nothing in the codebase called it yet, so this was a landmine rather
        than a live bug. It would have detonated the first time consensus
        anchoring was wired up, and silently: "prefer the sharp books" would
        have meant "prefer all of them", which is just the unweighted average
        wearing a rigorous name.
        """
        return self.bookmaker.lower() in SHARP_BOOKS


class OddsClient:
    """The Odds API client. Every call is metered before it is made."""

    def __init__(
        self,
        config: OddsConfig,
        budget: CreditBudget,
        *,
        client: Optional[httpx.AsyncClient] = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ):
        self.config = config
        self.budget = budget
        self.base_url = config.base_url.rstrip("/")
        self._client = client
        self._owns_client = client is None
        self._timeout = timeout_s

    async def __aenter__(self) -> "OddsClient":
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
            self._owns_client = True
        return self

    async def __aexit__(self, *exc_info) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError(
                "OddsClient used outside its context manager. "
                "Use `async with OddsClient(cfg, budget) as odds:`."
            )
        return self._client

    async def fetch_odds(
        self,
        sport_key: str,
        *,
        now_ms: int,
        markets: Optional[Sequence[str]] = None,
        regions: Optional[Sequence[str]] = None,
    ) -> list[OddsQuote]:
        """Fetch odds for one sport. Returns raw per-book quotes.

        Refuses and returns `[]` when the call would breach the budget --
        deliberately not an exception, because "we chose not to spend a credit"
        is a normal operating state, not a failure. The refusal is logged and
        the caller sees no data, which the staleness gate then treats as
        un-bettable. That chain is the intended behaviour.
        """
        markets = list(markets or self.config.markets)
        regions = list(regions or self.config.regions)
        cost = sweep_cost(markets, regions)

        if not self.budget.can_afford(cost, now_ms):
            return []

        path = f"/sports/{sport_key}/odds"
        url = f"{self.base_url}{path}"
        params = {
            "apiKey": self.config.api_key,
            "regions": ",".join(regions),
            "markets": ",".join(markets),
            "oddsFormat": "decimal",
            "dateFormat": "iso",
        }

        try:
            response = await self.client.get(url, params=params)
        except httpx.HTTPError:
            # A transport failure costs no credits, so nothing is recorded.
            logger.exception("odds fetch failed for %s", sport_key)
            raise

        # Record before raising: some error classes still consume credits, and
        # under-counting spend is worse than over-counting it.
        self.budget.record(
            called_ms=now_ms,
            endpoint=path,
            cost=cost,
            sport_key=sport_key,
            markets=markets,
            regions=regions,
            remaining_reported=_int_header(response, "x-requests-remaining"),
            used_reported=_int_header(response, "x-requests-used"),
        )

        if response.status_code == 429:
            raise QuotaExhausted(429, url, response.text)
        if response.status_code >= 400:
            raise OddsAPIError(response.status_code, url, response.text)

        return self._parse(response.json(), sport_key=sport_key, fetched_ms=now_ms)

    def _parse(
        self, payload: Any, *, sport_key: str, fetched_ms: int
    ) -> list[OddsQuote]:
        """Flatten the nested response into one row per book per outcome."""
        if not isinstance(payload, list):
            raise OddsAPIError(
                -1, "parse", f"expected a list of events, got {type(payload).__name__}"
            )

        quotes: list[OddsQuote] = []
        for event in payload:
            commence_ms = parse_ms(event.get("commence_time"))
            event_id = event.get("id")
            home = event.get("home_team")
            away = event.get("away_team")

            # All four are required to match this event to a Kalshi fixture.
            # Missing any one means the row cannot be used, so it is dropped
            # loudly rather than stored as a partial that fails later.
            if not (commence_ms and event_id and home and away):
                logger.warning(
                    "dropping odds event with incomplete identity: "
                    "id=%r home=%r away=%r commence=%r",
                    event_id, home, away, event.get("commence_time"),
                )
                continue

            for bookmaker in event.get("bookmakers") or []:
                book_key = bookmaker.get("key")
                book_updated_ms = parse_ms(bookmaker.get("last_update"))
                if not book_key:
                    continue

                for market in bookmaker.get("markets") or []:
                    market_key = market.get("key")
                    # A market-level last_update is more precise than the
                    # bookmaker-level one; prefer it when present.
                    market_updated_ms = (
                        parse_ms(market.get("last_update")) or book_updated_ms
                    )
                    for outcome in market.get("outcomes") or []:
                        price = outcome.get("price")
                        name = outcome.get("name")
                        if price is None or not name:
                            continue
                        try:
                            price_decimal = float(price)
                        except (TypeError, ValueError):
                            logger.warning(
                                "unparseable price %r on %s/%s", price, book_key, market_key
                            )
                            continue
                        if price_decimal <= 1.0:
                            # Decimal odds below 1.0 imply a probability above
                            # 1. Almost always a format mix-up (American odds
                            # in a decimal field), and it would read as a
                            # gigantic edge.
                            logger.warning(
                                "implausible decimal price %s on %s/%s -- dropping",
                                price_decimal, book_key, market_key,
                            )
                            continue

                        quotes.append(
                            OddsQuote(
                                fetched_ms=fetched_ms,
                                book_updated_ms=market_updated_ms,
                                sport_key=sport_key,
                                odds_event_id=event_id,
                                commence_ms=commence_ms,
                                home_team=home,
                                away_team=away,
                                bookmaker=book_key,
                                market=market_key or "",
                                outcome_name=name,
                                outcome_point=_opt_float(outcome.get("point")),
                                price_decimal=price_decimal,
                            )
                        )
        return quotes


def _int_header(response: httpx.Response, name: str) -> Optional[int]:
    raw = response.headers.get(name)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _opt_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def store_quotes(conn, quotes: Sequence[OddsQuote]) -> int:
    """Persist raw quotes. Returns the number of rows written."""
    if not quotes:
        return 0
    conn.executemany(
        "INSERT INTO odds_snapshots (fetched_ms, book_updated_ms, sport_key, "
        "odds_event_id, commence_ms, home_team, away_team, bookmaker, market, "
        "outcome_name, outcome_point, price_decimal) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                q.fetched_ms, q.book_updated_ms, q.sport_key, q.odds_event_id,
                q.commence_ms, q.home_team, q.away_team, q.bookmaker, q.market,
                q.outcome_name, q.outcome_point, q.price_decimal,
            )
            for q in quotes
        ],
    )
    conn.commit()
    return len(quotes)
