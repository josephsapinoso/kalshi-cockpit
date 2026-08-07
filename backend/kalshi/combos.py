"""Kalshi's multivariate event collections — the combo / parlay product.

A correction, recorded because the mistake was structural
---------------------------------------------------------
This project was built on the premise that **Kalshi has no parlay product**.
That premise is wrong, and it survived eleven build steps because of a true
fact that led to a false conclusion.

The true fact, inherited from the predecessor project: paginating `/markets`
returns ~99.8% `KXMVE` tickers with no volume. The false conclusion: that
`KXMVE` is junk. `KXMVE` is **M**ulti-**V**ariate **E**vent — it is the combo
builder in the Kalshi app. What is junk is the pre-generated combination
*markets* clogging an endpoint nobody should paginate, not the product behind
them.

So the `/markets` filter stays. What goes is the inference that drew "no parlay
product" from "lots of low-volume tickers".

What is actually there (measured 2026-08-06)
--------------------------------------------
1,389 collections, 13,806 legs:

- `KXMVENBASINGLEGAME` (1,096 collections, 8,622 legs) — **same-game** parlays:
  game, spread, total, points, assists, rebounds, threes, steals, blocks.
- `KXMVENFLSINGLEGAME` (223 / 1,964) — same, plus anytime TD, first TD, passing
  and rushing and receiving yards.
- `KXMVENFLMULTIGAMEEXTENDED`, `KXMVESPORTSMULTIGAMEEXTENDED` — cross-game and
  cross-sport, `size_min = 2` and no stated maximum.
- `KXMVECROSSCATEGORY` — sports legs combined with non-sports events.

Every collection resolves the same way: *"only resolves to YES if every
associated market resolves to YES."*

The liquidity question is open, and honestly so
-----------------------------------------------
At capture time **zero of the 13,806 legs had an active quoter**, and every
pre-generated combo market showed zero volume and zero open interest. That is
a real observation and it is also nearly uninformative: the capture ran on
6 August 2026, with the NBA season finished and the NFL in preseason. It
measures the calendar at least as much as the product. Whether these quote on
a Sunday in November is unmeasured, and this module does not pretend otherwise.

Why the combo price is worth more than the combo
------------------------------------------------
Independent of whether the combo is ever worth *betting*, its price is worth
**reading**. A same-game combo quote is a joint probability, and given each
leg's marginal it inverts to an implied correlation — see
`core.correlation.implied_correlation`. That is precisely the measured input
that `core.correlation` refuses to guess at, so Kalshi's combo book is a source
of the number the Builder otherwise has to decline to invent.

The one thing this module will not do on its own
------------------------------------------------
Pricing a *specific* combination requires `POST .../lookup`, which creates a
market on the exchange if that combination does not already exist. It commits
no money, but it is an outward-facing write, so `lookup_combo` requires
`allow_market_creation=True` from the caller rather than defaulting to it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Optional, Sequence

from .rest import KalshiRestClient

logger = logging.getLogger(__name__)

COLLECTIONS_PATH = "/multivariate_event_collections"

# The wire key is `multivariate_contracts`. The plausible-sounding
# `multivariate_event_collections` -- matching the path -- is absent, and
# reading it returns an empty list with no error. That is the same failure mode
# that made the predecessor project parse every order book to zero levels while
# 305 tests passed, so it is pinned here and asserted in the fixture test.
COLLECTIONS_KEY = "multivariate_contracts"


class ComboScope(str, Enum):
    """What a collection lets you combine."""

    SAME_GAME = "same_game"          # legs of one fixture
    MULTI_GAME = "multi_game"        # several fixtures, one sport
    CROSS_SPORT = "cross_sport"
    CROSS_CATEGORY = "cross_category"  # sports plus non-sports
    NON_SPORT = "non_sport"


# Classified from the series ticker, which is stable, rather than from the
# title, which is prose. Same discipline as `discovery.py`: an unrecognised
# label must be visible, never silently bucketed.
SCOPE_BY_SERIES: dict[str, ComboScope] = {
    "KXMVENBASINGLEGAME": ComboScope.SAME_GAME,
    "KXMVENFLSINGLEGAME": ComboScope.SAME_GAME,
    "KXMVEMENTIONSSINGLE": ComboScope.NON_SPORT,
    "KXMVENFLMULTIGAME": ComboScope.MULTI_GAME,
    "KXMVENFLMULTIGAMEEXTENDED": ComboScope.MULTI_GAME,
    "KXMVENBAMULTIGAMEEXTENDED": ComboScope.MULTI_GAME,
    "KXMVESPORTSMULTIGAMEEXTENDED": ComboScope.CROSS_SPORT,
    "KXMVECROSSCATEGORY": ComboScope.CROSS_CATEGORY,
    "KXMVECROSSCATEGORY-SHARD1": ComboScope.CROSS_CATEGORY,
    "KXMVECBCHAMPIONSHIP": ComboScope.MULTI_GAME,
    "KXMVEOSCARS": ComboScope.NON_SPORT,
    "KXMVEGRAMMYS": ComboScope.NON_SPORT,
}


@dataclass(frozen=True)
class ComboLeg:
    """One event that may be used as a leg."""

    event_ticker: str
    is_yes_only: bool
    active_quoters: tuple[str, ...]
    size_max: Optional[int] = None

    @property
    def series(self) -> str:
        return self.event_ticker.split("-")[0]

    @property
    def is_quoted(self) -> bool:
        return bool(self.active_quoters)


@dataclass(frozen=True)
class ComboCollection:
    """A set of events Kalshi will let you combine into one contract."""

    collection_ticker: str
    series_ticker: str
    title: str
    functional_description: str
    size_min: int
    size_max: int
    is_all_yes: bool
    is_single_market_per_event: bool
    legs: tuple[ComboLeg, ...]

    @property
    def scope(self) -> ComboScope:
        scope = SCOPE_BY_SERIES.get(self.series_ticker)
        if scope is None:
            # Loud rather than bucketed. An unclassified series is a product
            # change, and silently calling it cross-category would hide it.
            logger.warning(
                "unclassified combo series %r (%s). Add it to SCOPE_BY_SERIES; "
                "guessing its scope would put same-game legs through the "
                "cross-game correlation path.",
                self.series_ticker, self.collection_ticker,
            )
            return ComboScope.CROSS_CATEGORY
        return scope

    @property
    def is_same_game(self) -> bool:
        return self.scope is ComboScope.SAME_GAME

    @property
    def fixture(self) -> Optional[str]:
        """The fixture suffix, for a same-game collection.

        `KXNBAGAME-26APR28PORSAS` -> `26APR28PORSAS`. This is what links a
        collection to a fixture already matched against sportsbook odds.
        """
        if not self.is_same_game or not self.legs:
            return None
        _, _, suffix = self.legs[0].event_ticker.partition("-")
        return suffix or None

    @property
    def quoted_legs(self) -> tuple[ComboLeg, ...]:
        return tuple(leg for leg in self.legs if leg.is_quoted)

    @property
    def leg_series(self) -> tuple[str, ...]:
        """Distinct leg types, e.g. game / spread / total / points."""
        return tuple(sorted({leg.series for leg in self.legs}))


def parse_collection(payload: dict[str, Any]) -> ComboCollection:
    """Parse one collection from the wire.

    Field names come from a captured payload, not from memory -- see
    `tests/fixtures/combo_collections.json`.
    """
    legs = tuple(
        ComboLeg(
            event_ticker=event["ticker"],
            is_yes_only=bool(event.get("is_yes_only")),
            active_quoters=tuple(event.get("active_quoters") or ()),
            size_max=event.get("size_max"),
        )
        for event in payload.get("associated_events", [])
    )
    return ComboCollection(
        collection_ticker=payload["collection_ticker"],
        series_ticker=payload.get("series_ticker", ""),
        title=payload.get("title", ""),
        functional_description=payload.get("functional_description", ""),
        size_min=int(payload.get("size_min") or 0),
        size_max=int(payload.get("size_max") or 0),
        is_all_yes=bool(payload.get("is_all_yes")),
        is_single_market_per_event=bool(payload.get("is_single_market_per_event")),
        legs=legs,
    )


async def fetch_collections(
    api: KalshiRestClient, *, max_pages: int = 25
) -> list[ComboCollection]:
    """Every combo collection, paginated.

    Warns rather than truncating silently if the page cap is hit -- a partial
    list that looks complete is how a league quietly leaves scope.
    """
    out: list[ComboCollection] = []
    cursor: Optional[str] = None

    for page in range(max_pages):
        params: dict[str, Any] = {"limit": 200}
        if cursor:
            params["cursor"] = cursor
        response = await api.request("GET", COLLECTIONS_PATH, params=params)

        batch = response.get(COLLECTIONS_KEY)
        if batch is None:
            raise KeyError(
                f"{COLLECTIONS_PATH} response has no {COLLECTIONS_KEY!r} key "
                f"(got {sorted(response)}). Kalshi renamed the field; refusing "
                f"to return an empty list that would read as 'no combos'."
            )

        out.extend(parse_collection(entry) for entry in batch)
        cursor = response.get("cursor")
        if not cursor or not batch:
            return out

    logger.warning(
        "combo collection walk hit its %d-page cap with a cursor still "
        "outstanding; the list is incomplete", max_pages,
    )
    return out


def same_game_collections(
    collections: Iterable[ComboCollection],
) -> dict[str, ComboCollection]:
    """Same-game collections keyed by fixture suffix.

    The same-game ones are the interesting ones: their price is a joint
    probability over legs of a single fixture, which is the correlation
    `core.correlation` declines to guess.
    """
    return {
        collection.fixture: collection
        for collection in collections
        if collection.is_same_game and collection.fixture
    }


@dataclass(frozen=True)
class LiquidityReport:
    """How much of the combo surface is actually quoted.

    Reported rather than asserted, and always with the caveat attached: a zero
    here on a summer afternoon says almost nothing about a Sunday in November.
    """

    n_collections: int
    n_legs: int
    n_quoted_legs: int
    by_series: dict[str, tuple[int, int]]   # series -> (legs, quoted)

    @property
    def quoted_fraction(self) -> float:
        return self.n_quoted_legs / self.n_legs if self.n_legs else 0.0

    @property
    def verdict(self) -> str:
        if self.n_legs == 0:
            return "no collections returned at all — check the wire key"
        if self.n_quoted_legs == 0:
            return (
                f"none of {self.n_legs:,} legs across {self.n_collections:,} "
                f"collections has an active quoter. This is a real observation "
                f"and a weak one: out of season it measures the calendar, not "
                f"the product. Re-run in season before concluding anything."
            )
        return (
            f"{self.n_quoted_legs:,} of {self.n_legs:,} legs quoted "
            f"({self.quoted_fraction:.1%}) across {self.n_collections:,} "
            f"collections"
        )


def liquidity(collections: Sequence[ComboCollection]) -> LiquidityReport:
    by_series: dict[str, list[int]] = {}
    for collection in collections:
        entry = by_series.setdefault(collection.series_ticker, [0, 0])
        entry[0] += len(collection.legs)
        entry[1] += len(collection.quoted_legs)

    return LiquidityReport(
        n_collections=len(collections),
        n_legs=sum(len(c.legs) for c in collections),
        n_quoted_legs=sum(len(c.quoted_legs) for c in collections),
        by_series={k: (v[0], v[1]) for k, v in sorted(by_series.items())},
    )


class MarketCreationRefused(RuntimeError):
    """Raised when a lookup would create a market without explicit permission."""


async def lookup_combo(
    api: KalshiRestClient,
    collection_ticker: str,
    selected_markets: Sequence[tuple[str, str]],
    *,
    allow_market_creation: bool = False,
) -> dict[str, Any]:
    """Resolve a specific combination to its market ticker, and thus its price.

    `selected_markets` is `(event_ticker, market_ticker)` per leg.

    **This creates a market on the exchange** when the combination does not
    already exist — that is how the product works, and it is what the app does
    every time someone taps a leg. It commits no money, but it is an
    outward-facing write against a live account, so it is off by default. Pass
    `allow_market_creation=True` deliberately.
    """
    if not allow_market_creation:
        raise MarketCreationRefused(
            f"pricing a combination on {collection_ticker} requires "
            f"POST .../lookup, which creates a market on the exchange if this "
            f"combination is new. No money is committed, but it is an "
            f"outward-facing write. Pass allow_market_creation=True to proceed."
        )

    body = {
        "selected_markets": [
            {"event_ticker": event, "market_ticker": market}
            for event, market in selected_markets
        ]
    }
    return await api.request(
        "POST", f"{COLLECTIONS_PATH}/{collection_ticker}/lookup", json_body=body
    )
