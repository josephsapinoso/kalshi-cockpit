"""E2: is a combination's list quote backed by an order book? Read-only.

    .venv\\Scripts\\python.exe scripts\\measure_combo_book_presence.py \\
        --max-books 20 --json docs/measurements/...json

Free and **unauthenticated**. Both `/markets` and `/markets/{ticker}/orderbook`
are public (verified 2026-08-09: 200 with no signature), so this runs with no
credential in the process at all. No Odds API credit is spent, nothing is
ordered, nothing is created, no `multivariate_event_collections` lookup is made.

The question, pre-registered
---------------------------
`docs/measurements/2026-08-09-combo-leg-echo.md` closes by fixing E2 in advance:

> **E2.** For each combination carrying a `yes_ask` on `/markets`, read
> `/markets/{ticker}/orderbook` in the same pass. Record (a) whether the book is
> non-empty, (b) whether `1 - best_no_bid` reproduces the list `yes_ask`, and
> (c) whether any level derives to within 2c of a leg's cost. Report the rate of
> each with its `n`, split by scope, and report the **book-empty rate first** --
> if a material share of quoted rows have no book, the harvest's population is
> not what it was taken to be, and that supersedes every other question here.

It exists because an exploratory look at 8 live echo combinations found 3 with
an empty book while the list endpoint quoted them, one reading `0.0000/1.0000`
for 18 consecutive polls against a list quote of 0.463. **All 2,116 rows of
this project's combo harvest come from the list endpoint** and none was ever
checked against a book.

Why the wire keys are imported and not retyped
----------------------------------------------
The envelope is `orderbook_fp`, and the sides inside it are `yes_dollars` /
`no_dollars` -- **not** the socket's names. `KalshiRestClient.orderbook` used to
read `payload["orderbook"]` and returned `{}` for every market on the exchange
without erroring. So `ORDERBOOK_KEY` and `MalformedOrderbookResponse` are
imported from `backend.kalshi.rest` rather than re-declared here: a second copy
of a wire key is exactly how a book-empty rate becomes a key-typo rate.

That distinction is the whole hazard of this measurement. **An empty book is a
legitimate state on this venue; a renamed field is not.** A missing envelope
raises and aborts the row rather than counting as empty.

Definitions -- fixed before collection
--------------------------------------
- *eligible combination*: a `/markets` row with a non-empty `mve_selected_legs`
  and a readable `yes_ask` by `measure_combo_correlation.readable_quote`
  (`0 < ask < 1`). A `0.0000` ask is not an ask.
- *book empty*: zero levels on `yes_dollars` **and** zero on `no_dollars`.
- *no-side empty*: zero levels on `no_dollars`. Reported separately because
  `yes_ask` derives from the NO bid alone, so a book with only YES levels
  cannot back a list ask either.
- *reproduces*: `|(1 - best_no_bid) - list_ask| <= 0.0005` -- equality on the
  deci-cent grid. Half a deci-cent, because 0.001 is a real tick here, so
  anything wider would report a genuine one-tick disagreement as agreement.
  The raw difference is recorded for every row regardless, so a near-miss is
  visible rather than binned as a failure.

  **This tolerance is NOT underwritten by SKILL.md's 2,145-quote check**, and
  an earlier version of this docstring said it was. That check was
  `yes_ask == 1000 - no_bid` *within a single market-summary row*, on markets
  from `/events?with_nested_markets=true` -- an endpoint SKILL.md itself says
  "excludes MVE entirely". It establishes that a summary payload is internally
  consistent on non-combo markets. It says nothing about whether an MVE row's
  summary ask is derived from that market's own order book, which is precisely
  the question this harness exists to ask. The tolerance's *value* is unchanged
  from the pre-registration; only its stated justification was wrong.
- *derived yes price of a level*: `1 - p` for a NO level at `p`, and `p` itself
  for a YES level. Both are prices on the YES scale, which is the scale a leg's
  cost-to-buy is on.
- *echo in book*: some level's derived yes price is within `ECHO_TOLERANCE`
  (0.02, the same constant `analyse_combo_domination` uses) of some leg's
  `cost_to_buy_leg`. Computed **only** for combinations where every leg is
  priceable; the others are counted and excluded, never scored as "no echo".
- *cost_to_buy_leg* is imported from `measure_combo_correlation`, not
  re-implemented: `yes -> yes_ask`, `no -> 1 - yes_bid`. One path, so this
  cannot disagree with the version the 2,116-row harvest used.

Sampling -- CHANGED AFTER E2 RAN. See "What changed, and why" below.
--------------------------------------------------------------------
One `/markets?series_ticker=...&status=open&limit=1000` per series in
`DISCOVERY_SERIES` (newest-first, no paging -- CLAUDE.md forbids walking
`/markets` blind), then a **round-robin across the series** of eligible rows
optionally restricted to `--max-legs`, then one batched read of every leg of
those rows, then one orderbook read each, then one batched re-read of the same
combinations' list quotes.

That last read is a **contemporaneity control**, not a bonus. A combination
stops being quoted within tens of seconds (measured, same document), so an
empty book could mean "this quote was never backed" or "the quote died between
the two reads". The re-read splits those: a row whose list ask is still present
*after* the whole book pass was quoted at both ends of it.

Budget: 2 + 1 + N + 1 calls. At the default N=20 that is 24.

What changed after E2 ran, and why
----------------------------------
E2's numbers in `docs/measurements/2026-08-09-combo-e2-book-empty.md` were
produced under the **original** selection rule -- "the first `--max-books`
eligible rows in discovery order", with no leg restriction -- and are NOT
re-run. Two defects in that rule were found by auditing E2's own output against
data already committed in this repo, and both are fixed here for future runs.
They are recorded rather than silently rewritten, because a pre-registration
that gets quietly edited afterwards stops meaning anything.

1. **The selection rule could not reach the second series.** `DISCOVERY_SERIES`
   is a tuple, the pages are concatenated in tuple order, and "the first N
   eligible rows in discovery order" therefore fills entirely from
   `KXMVESPORTSMULTIGAMEEXTENDED` before `KXMVECROSSCATEGORY` is ever reached.
   E2's sample was 20/20 the first series and 0/20 the second -- while the
   2,116-row harvest this was meant to inform is 1,395/2,116 (66%) the
   *second*. That is a structural non-overlap, not bad luck, and no interval
   from such a sample transfers to that population. Selection is now a
   **round-robin across the series**, so each contributes.

2. **The selection rule could not match the harvest's own leg-count rule.**
   `measure_combo_correlation` refuses anything over three legs
   (`too_many_legs_for_equicorrelation`, 10,228 rows refused), so the 2,116
   stored rows are 911 two-leg and 1,205 three-leg and *nothing else*. E2's
   sample ran 2 to 15 legs with only 3 of 20 rows at 2-3 -- 17 of 20 sampled
   rows had a leg count that occurs zero times in the target population.
   `--max-legs` now exists so a run can be restricted to the harvest's own
   eligibility rule.

Neither fix makes E2's recorded rates wrong. They make them rates about a
population that is not the one anybody wanted to know about.

E3 -- added after E2, pre-registered before it ran
--------------------------------------------------
E2 left one explanation for (b) untested: **MVE list asks may come from a
pricing engine rather than from the collection's own order book.** That
predicts every disagreement E2 saw, and E2 could not rule it out because the
observation that separates it was on the wire and was not recorded --
`no_bid_dollars` off the *same list payload* as `yes_ask_dollars`.

It separates them because it decomposes the (b) gap into two terms:

    list_ask - book_derived_ask
        = [list_ask - (1 - list_no_bid)]      the ENGINE term
        + [list_no_bid - book_best_no_bid]    the SKEW term

The engine term is computed from two fields of **one payload, read at one
moment**. No latency between endpoints and no price move can produce it. If it
is non-zero, the list ask is not the complement of the list row's own NO bid,
and (b) is a statement about a pricing engine rather than about staleness.

`docs/measurements/2026-08-09-combo-e3-list-no-bid.md` fixes the denominators,
the decision rule and the stopping rule before collection.

What this does not establish
----------------------------
- **Nothing about the 2,116 stored rows themselves.** Those markets are gone.
  This measures the population they were drawn from, on a later slate. The
  pre-registration framed the transfer risk as *temporal* ("transfers only to
  the extent that population is stable"). That was the wrong axis and E2 proved
  it: the binding risk is **structural non-overlap on series and leg count**,
  which was checkable from files already in this repo at zero cost and was not
  checked. A run whose sample does not span the target's series mix and leg-
  count range transfers to nothing, however stable the population is.
- **Nothing about why a book is empty.** A replica lag between two endpoints, a
  quoter that posts and pulls within the gap, and a list price that was never
  backed by resting size all predict the same observation here.
- **Nothing that separates age from exposure.** Discovery is newest-first and
  the books are read in that same order, so a row's position, its age, and its
  list-to-book gap are perfectly collinear. Nothing in this design can
  attribute an empty book to one rather than another.
- **Nothing about tradeability.** These rows are provisional with zero volume
  and zero open interest. A resting level is not a fill.
- **Nothing about non-eligible combinations.** Rows with no readable ask are
  excluded by construction, so no statement here covers them.
- **Newest-first, so youngest.** Only the newest combinations carry a quote at
  all, so the sample is young by necessity. If book presence grows with age,
  this rate is a lower bound on it and nothing here separates the two.
- **One slate, one window of seconds.** Not an edge: no fair value is computed
  and no combo fee model is verified.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from itertools import zip_longest
from pathlib import Path
from typing import Any, Optional

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts"))

import httpx  # noqa: E402

from backend.kalshi.discovery import parse_ms  # noqa: E402
from backend.kalshi.rest import (  # noqa: E402
    ORDERBOOK_KEY,
    MalformedOrderbookResponse,
)
from backend.logging_setup import configure_logging  # noqa: E402
from measure_combo_correlation import (  # noqa: E402
    dollars,
    readable_quote,
)
from measure_combo_leg_echo import (  # noqa: E402
    DISCOVERY_SERIES,
    ECHO_TOLERANCE,
    PublicReader,
    leg_cost_from,
    scope_of,
)

# Equality on the deci-cent grid. The derived-ask identity is exact where it
# holds, so a tolerance any wider would report agreement that is really a
# near-miss -- and near-misses are what this is looking for.
GRID_TOL = 0.0005

YES_SIDE = "yes_dollars"
NO_SIDE = "no_dollars"

logger = logging.getLogger("measure_combo_book_presence")


# -- pure analysis --------------------------------------------------------


def parse_levels(book: dict, side: str) -> list[tuple[float, float]]:
    """`[[price, size], ...]` for one side of the book, in wire order.

    A level whose price will not parse is **dropped and logged**, never
    substituted with 0.0 -- 0 is a legitimate price here, so a parser that
    returns it on garbage is indistinguishable from one that read correctly.
    """
    out: list[tuple[float, float]] = []
    for level in book.get(side) or []:
        if not isinstance(level, (list, tuple)) or len(level) < 2:
            logger.warning("unparseable %s level %r; dropped", side, level)
            continue
        price = dollars(level[0])
        if price is None:
            logger.warning("unparseable %s price %r; dropped", side, level[0])
            continue
        try:
            size = float(level[1])
        except (TypeError, ValueError):
            logger.warning("unparseable %s size %r; dropped", side, level[1])
            continue
        out.append((price, size))
    return out


def book_is_empty(book: dict) -> bool:
    """No resting size on either side. The primary quantity E2 asks for."""
    return not parse_levels(book, YES_SIDE) and not parse_levels(book, NO_SIDE)


def best_no_bid(book: dict) -> Optional[float]:
    """Highest NO bid, or None if nobody is bidding NO."""
    levels = parse_levels(book, NO_SIDE)
    return max(p for p, _ in levels) if levels else None


def derived_yes_ask(book: dict) -> Optional[float]:
    """`1 - best_no_bid`. The only tradeable YES ask this venue publishes."""
    bid = best_no_bid(book)
    return None if bid is None else 1.0 - bid


def derived_yes_prices(book: dict) -> list[float]:
    """Every level, expressed on the YES scale.

    A NO level at `p` is a YES ask at `1 - p`; a YES level at `q` is a YES bid
    at `q`. Legs' cost-to-buy is on the YES scale, so this is what a level has
    to be converted to before "within 2c of a leg" means anything.
    """
    prices = [1.0 - p for p, _ in parse_levels(book, NO_SIDE)]
    prices.extend(p for p, _ in parse_levels(book, YES_SIDE))
    return prices


def echo_gap(book: dict, leg_costs: list[float]) -> Optional[float]:
    """Smallest gap between any level's derived yes price and any leg's cost.

    `None` when there is nothing to compare -- an empty book or an unpriceable
    leg set. `None` is not "no echo"; the caller must count it separately.
    """
    prices = derived_yes_prices(book)
    if not prices or not leg_costs:
        return None
    return min(abs(p - c) for p in prices for c in leg_costs)


def book_signature(book: dict) -> tuple:
    """A book's exact resting shape -- every level, price and size, in order.

    Two rows sharing a signature are being quoted by the same thing. In E2 six
    rows carried an identical `0.9980 x 300` NO bid, and those six were 6/6 on
    "reproduces" while the other ten were 5/10 -- so the pooled 68.8% was a
    blend of 100% and a coin flip, and the scope table hid it by putting all
    six in one cell. CLAUDE.md: a pooled number is not a finding until the
    parts agree.

    Defined on the book's bytes, not on any outcome, so grouping by it cannot
    be a forking path. A cluster is any signature carried by more than one row.
    """
    return (
        tuple((p, s) for p, s in parse_levels(book, YES_SIDE)),
        tuple((p, s) for p, s in parse_levels(book, NO_SIDE)),
    )


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval. Correct at the small `n` this run produces.

    A normal approximation needs >=5 expected outcomes on each side (CLAUDE.md)
    and this sample will not have them, so the interval is the honest statement
    of what the rate is -- never the point estimate on its own.
    """
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


# -- observation ----------------------------------------------------------


@dataclass
class Row:
    ticker: str
    series: str
    collection: str
    scope: str
    created_ms: Optional[int]
    legs: tuple[dict, ...]
    list_ask: float
    list_bid: Optional[float]
    # E3. The list row's OWN NO bid, off the same payload as `list_ask`. This
    # was on the wire during E2 and was not recorded, and it is the one
    # observation that separates the two explanations for (b). See the module
    # docstring's E3 section.
    list_no_bid: Optional[float]
    list_observed_ms: int
    volume: Optional[float]
    open_interest: Optional[float]
    leg_costs: list[float] = field(default_factory=list)
    legs_all_priceable: bool = False
    book: dict = field(default_factory=dict)
    book_observed_ms: int = 0
    book_error: str = ""
    still_quoted_after: Optional[bool] = None
    confirm_ask: Optional[float] = None
    confirm_no_bid: Optional[float] = None

    # -- derived, all from the pure functions above ------------------------

    # -- E3: which term of the decomposition carries the (b) disagreement ---
    #
    #   list_ask - book_derived_ask
    #       = [list_ask - (1 - list_no_bid)]     <- the ENGINE term
    #       + [list_no_bid - book_best_no_bid]   <- the SKEW term
    #
    # The engine term lives entirely inside ONE payload read at ONE moment, so
    # no amount of latency between endpoints can produce it. If it is non-zero
    # the list ask is not derived from the list row's own NO bid, and (b) is
    # about a pricing engine rather than about staleness.

    @property
    def list_internal_ask(self) -> Optional[float]:
        """`1 - list_no_bid`, the ask the list row's OWN no-bid implies."""
        nb = self.list_no_bid
        return None if nb is None else 1.0 - nb

    @property
    def engine_gap(self) -> Optional[float]:
        """`list_ask - (1 - list_no_bid)`. Within one payload, one moment."""
        implied = self.list_internal_ask
        return None if implied is None else self.list_ask - implied

    @property
    def skew_gap(self) -> Optional[float]:
        """`list_no_bid - book_best_no_bid`. Across two endpoints."""
        book_bid = best_no_bid(self.book)
        if self.list_no_bid is None or book_bid is None:
            return None
        return self.list_no_bid - book_bid

    @property
    def list_is_internally_derived(self) -> Optional[bool]:
        gap = self.engine_gap
        return None if gap is None else abs(gap) <= GRID_TOL

    @property
    def list_no_bid_matches_book(self) -> Optional[bool]:
        gap = self.skew_gap
        return None if gap is None else abs(gap) <= GRID_TOL

    @property
    def empty(self) -> bool:
        return book_is_empty(self.book)

    @property
    def no_side_empty(self) -> bool:
        return not parse_levels(self.book, NO_SIDE)

    @property
    def derived_ask(self) -> Optional[float]:
        return derived_yes_ask(self.book)

    @property
    def ask_diff(self) -> Optional[float]:
        d = self.derived_ask
        return None if d is None else d - self.list_ask

    @property
    def reproduces(self) -> Optional[bool]:
        diff = self.ask_diff
        return None if diff is None else abs(diff) <= GRID_TOL

    @property
    def gap_to_leg(self) -> Optional[float]:
        if not self.legs_all_priceable:
            return None
        return echo_gap(self.book, self.leg_costs)

    @property
    def echoes_a_leg(self) -> Optional[bool]:
        gap = self.gap_to_leg
        return None if gap is None else gap <= ECHO_TOLERANCE


async def read_book(reader: PublicReader, ticker: str, depth: int) -> dict:
    """One order book, with the envelope guard `KalshiRestClient` applies.

    Not a second copy of the rule: the key and the exception both come from
    `backend.kalshi.rest`. A missing envelope raises, so it can never be
    silently counted as an empty book -- which is the one way this measurement
    could produce a large, tidy, entirely false number.
    """
    payload = await reader.get(f"/markets/{ticker}/orderbook", depth=depth)
    book = payload.get(ORDERBOOK_KEY)
    if book is None:
        raise MalformedOrderbookResponse(
            f"{ticker}: /markets/{{ticker}}/orderbook has no "
            f"{ORDERBOOK_KEY!r} key (got {sorted(payload)}). Refusing to score "
            f"this as an empty book."
        )
    return book


def eligible(market: dict, *, max_legs: Optional[int] = None) -> bool:
    legs = market.get("mve_selected_legs") or []
    if not legs:
        return False
    if max_legs is not None and len(legs) > max_legs:
        return False
    return readable_quote(market) is not None


def round_robin(pages: list[list[dict]]) -> list[dict]:
    """Interleave the series' pages so no one series can fill the sample.

    Concatenating them and taking the first N is what E2 did, and because
    `DISCOVERY_SERIES` is an ordered tuple that guaranteed 20/20 from the first
    series -- while the population the run was meant to inform is 66% the
    second. The failure is silent: the sample looks like 20 rows, not like 20
    rows from one of two strata. Interleaving makes an under-supplied series
    show up as a short sample rather than as an absent one.
    """
    out: list[dict] = []
    for column in zip_longest(*pages):
        out.extend(row for row in column if row is not None)
    return out


async def collect(
    reader: PublicReader,
    *,
    max_books: int,
    depth: int,
    capture: Optional[Path],
    max_legs: Optional[int] = None,
) -> list[Row]:
    pages: list[list[dict]] = []
    for series in DISCOVERY_SERIES:
        rows = await reader.markets_page(series)
        logger.info("%s: %d open rows", series, len(rows))
        pages.append(rows)
    page = round_robin(pages)

    now_ms = int(time.time() * 1000)
    chosen: list[Row] = []
    seen: set[str] = set()
    for market in page:
        if len(chosen) >= max_books:
            break
        ticker = market.get("ticker") or ""
        if not ticker or ticker in seen or not eligible(market, max_legs=max_legs):
            continue
        seen.add(ticker)
        quote = readable_quote(market)
        assert quote is not None  # eligible() already established this
        legs = tuple(market.get("mve_selected_legs") or [])
        chosen.append(
            Row(
                ticker=ticker,
                series=ticker.split("-")[0],
                collection=str(market.get("mve_collection_ticker") or ""),
                scope=scope_of(legs),
                created_ms=parse_ms(market.get("created_time")),
                legs=legs,
                list_ask=quote.ask,
                list_bid=quote.bid,
                # Parsed with the same `dollars` every other price here uses,
                # so an unreadable value is None and never 0.0 -- 0 is a legal
                # NO bid and a parser that returns it on garbage cannot be
                # told apart from one that read correctly.
                list_no_bid=dollars(market.get("no_bid_dollars")),
                list_observed_ms=now_ms,
                volume=_number(market.get("volume_fp")),
                open_interest=_number(market.get("open_interest_fp")),
            )
        )

    logger.info(
        "chose %d eligible combinations across %d series: %s",
        len(chosen), len(DISCOVERY_SERIES),
        dict(Counter(r.series for r in chosen)),
    )
    if not chosen:
        return []

    # One batched leg read, before the books, so a leg cost and a book are read
    # seconds apart rather than argued to be contemporaneous.
    leg_tickers = [
        str(leg.get("market_ticker") or "")
        for row in chosen
        for leg in row.legs
    ]
    leg_rows = await reader.by_ticker([t for t in dict.fromkeys(leg_tickers) if t])
    for row in chosen:
        costs: list[float] = []
        for leg in row.legs:
            cost = leg_cost_from(
                leg_rows.get(str(leg.get("market_ticker") or "")),
                str(leg.get("side") or "yes"),
            )
            if cost is not None:
                costs.append(cost)
        row.leg_costs = costs
        row.legs_all_priceable = len(costs) == len(row.legs)

    captured: list[dict] = []
    for row in chosen:
        try:
            row.book = await read_book(reader, row.ticker, depth)
            row.book_observed_ms = int(time.time() * 1000)
            captured.append({"ticker": row.ticker, ORDERBOOK_KEY: row.book})
        except MalformedOrderbookResponse as exc:
            # Aborts the row, never scores it. See the module docstring.
            row.book_error = str(exc)
            logger.error("%s", exc)
        except httpx.HTTPError as exc:
            row.book_error = f"{type(exc).__name__}: {exc}"
            logger.warning("%s book unreadable: %s", row.ticker, exc)

    # The contemporaneity control. Same list endpoint, after the book pass.
    confirm = await reader.by_ticker([row.ticker for row in chosen])
    for row in chosen:
        again = confirm.get(row.ticker)
        quote = readable_quote(again) if again else None
        row.confirm_ask = quote.ask if quote else None
        row.confirm_no_bid = dollars(again.get("no_bid_dollars")) if again else None
        row.still_quoted_after = quote is not None

    if capture and captured:
        capture.write_text(json.dumps(captured, indent=2), encoding="utf-8")
        logger.info("wrote %s", capture)

    return chosen


def _number(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# -- reporting ------------------------------------------------------------


def _rate(label: str, successes: int, n: int, indent: str = "    ") -> None:
    if n == 0:
        print(f"{indent}{label:<46} n=0  -- nothing to report")
        return
    lo, hi = wilson(successes, n)
    print(
        f"{indent}{label:<46} {successes:>3}/{n:<3} "
        f"= {successes / n:6.1%}   95% CI [{lo:.1%}, {hi:.1%}]"
    )


def report(rows: list[Row], calls: int) -> None:
    scored = [r for r in rows if not r.book_error]
    aborted = [r for r in rows if r.book_error]

    print(f"\n{'=' * 78}")
    print("E2 -- is a combination's LIST quote backed by an ORDER BOOK?")
    print(f"{'=' * 78}")
    print(f"  Kalshi API calls (free, unauthenticated)   {calls:>4}")
    print(f"  eligible combinations selected             {len(rows):>4}")
    print(f"  books read and scored                      {len(scored):>4}")
    print(f"  rows ABORTED on a malformed envelope       {len(aborted):>4}"
          "   (never counted as empty)")
    for row in aborted:
        print(f"      {row.ticker}: {row.book_error[:90]}")

    print("\n  READ n FIRST. This is one pass over one slate; the interval, not")
    print("  the point estimate, is the result.")

    # Printed BEFORE any rate, because E2's rates were all about a population
    # nobody wanted: 20/20 rows from one of two series, 17/20 at a leg count
    # that occurs zero times in the 2,116-row harvest. A sample that does not
    # span the target does not transfer, and that has to be visible first.
    print("\n  SAMPLE COMPOSITION -- does this sample span the population it")
    print("  is meant to inform? The 2,116-row harvest is 66% KXMVECROSSCATEGORY")
    print("  and 100% two- or three-leg. A cell at 0 here voids the transfer.")
    for series, count in sorted(Counter(r.series for r in rows).items()):
        print(f"    {series:<32} {count:>3}/{len(rows)}")
    legs = Counter(len(r.legs) for r in rows)
    print(f"    leg counts                       "
          f"{dict(sorted(legs.items()))}")
    within = sum(n for k, n in legs.items() if k <= 3)
    print(f"    rows at 2-3 legs (the harvest's own rule)  "
          f"{within}/{len(rows)}")
    if len(rows) and within < len(rows):
        print("    ^ rows above 3 legs are OUTSIDE the harvest's population.")

    print("\n  (a) BOOK-EMPTY RATE -- reported first, as pre-registered")
    _rate("book empty (no level on either side)",
          sum(1 for r in scored if r.empty), len(scored))
    _rate("NO side empty (yes_ask cannot derive)",
          sum(1 for r in scored if r.no_side_empty), len(scored))

    still = [r for r in scored if r.still_quoted_after]
    print("\n      contemporaneity control -- the same list rows, re-read AFTER")
    print("      the whole book pass. A row still quoted at both ends cannot")
    print("      have an empty book merely because its quote expired.")
    _rate("still quoted after the book pass", len(still), len(scored),
          indent="      ")
    _rate("...of those, book empty",
          sum(1 for r in still if r.empty), len(still), indent="      ")

    withbook = [r for r in scored if r.derived_ask is not None]
    print("\n  (b) DOES 1 - best_no_bid REPRODUCE THE LIST ASK?")
    print(f"      denominator is the {len(withbook)} rows with a NO bid at all;"
          " a row with no")
    print("      NO side has nothing to reproduce it with and is not a failure.")
    _rate("reproduces exactly (<= 0.0005)",
          sum(1 for r in withbook if r.reproduces), len(withbook))
    _rate("within 2c", sum(1 for r in withbook
                           if r.ask_diff is not None
                           and abs(r.ask_diff) <= ECHO_TOLERANCE),
          len(withbook))

    # The pooled rate above is not a finding until the parts agree, and the
    # scope split does not expose this grouping -- in E2 all six cluster rows
    # were `cross_game`, so the cell read 6/9 with every success one quoter.
    sigs = Counter(book_signature(r.book) for r in withbook)
    clustered = [r for r in withbook if sigs[book_signature(r.book)] > 1]
    singles = [r for r in withbook if sigs[book_signature(r.book)] == 1]
    print("\n      SPLIT ON IDENTICAL BOOK SIGNATURE -- rows whose book is")
    print("      byte-identical to another row's are one automated quoter, and")
    print("      a rate pooled over them is a blend, not a rate.")
    _rate("rows sharing a book with another row", len(clustered),
          len(withbook), indent="      ")
    _rate("...of those, reproduces",
          sum(1 for r in clustered if r.reproduces), len(clustered),
          indent="      ")
    _rate("everything else, reproduces",
          sum(1 for r in singles if r.reproduces), len(singles),
          indent="      ")
    for sig, count in sigs.most_common():
        if count > 1:
            print(f"        x{count}: yes={list(sig[0])} no={list(sig[1])}")

    # Direction, printed as counts on both sides rather than as a summary. In
    # E2 this was 3 against and 2 in favour with the LARGEST in the buyer's
    # favour -- which does not support a directional cost claim, and the
    # write-up made one anyway.
    against = [r for r in withbook
               if r.ask_diff is not None and r.ask_diff > GRID_TOL]
    infavour = [r for r in withbook
                if r.ask_diff is not None and r.ask_diff < -GRID_TOL]
    print(f"\n      direction: {len(against)} against the buyer, "
          f"{len(infavour)} in the buyer's favour")
    biggest_diff = max(
        (r for r in withbook if r.ask_diff is not None),
        key=lambda r: abs(r.ask_diff), default=None,
    )
    if biggest_diff is not None:
        side = ("against the buyer" if biggest_diff.ask_diff > 0
                else "in the buyer's favour")
        print(f"      largest single disagreement {biggest_diff.ask_diff:+.4f}"
              f" -- {side}")
        print("      With counts this small the sign of the largest row is not")
        print("      evidence of a direction. State the effect, not a bias.")

    # The contemporaneity re-read is not only a control on (a). It adjudicates
    # each (b) disagreement row by row, and E2's write-up said the disagreements
    # "cannot be separated from a genuine price move" while this column sat in
    # its own JSON unused. If the re-read landed on the book's derived value,
    # the list was lagging and caught up. If the list barely moved while the
    # book stayed elsewhere, a transient move does not explain it.
    disagree = [r for r in withbook if r.reproduces is False]
    if disagree:
        print("\n      EACH DISAGREEMENT, ADJUDICATED BY THE RE-READ")
        for row in disagree:
            derived_levels = sorted(derived_yes_prices(row.book))
            if row.confirm_ask is None:
                verdict = "NOT ADJUDICABLE -- the ask was gone at the re-read"
            elif abs(row.confirm_ask - (row.derived_ask or 0.0)) <= GRID_TOL:
                verdict = "a move/lag: the list caught up to the book"
            elif any(abs(row.confirm_ask - p) <= GRID_TOL
                     for p in derived_levels):
                verdict = ("the list tracks a level that is NOT the best bid "
                           "-- not a move")
            elif abs(row.confirm_ask - row.list_ask) <= ECHO_TOLERANCE:
                verdict = ("NOT a move: the list held its own value across "
                           "the book read")
            else:
                verdict = "neither read matches the book"
            print(f"        {row.ticker[-13:]:<13} list {row.list_ask:.4f}"
                  f" -> re-read "
                  f"{f'{row.confirm_ask:.4f}' if row.confirm_ask is not None else 'GONE'}"
                  f"   book derives {[round(p, 4) for p in derived_levels]}")
            print(f"            {verdict}")

    # -- E3 ---------------------------------------------------------------
    have_nb = [r for r in scored if r.list_no_bid is not None]
    print("\n  (E3) IS THE LIST ASK DERIVED FROM THE LIST ROW'S OWN NO BID?")
    print(f"      rows whose list payload carried a readable no_bid_dollars: "
          f"{len(have_nb)}/{len(scored)}")
    if not have_nb:
        print("      The field is absent or unreadable on every MVE row here.")
        print("      E3 CANNOT BE ANSWERED from the list endpoint. Registered,")
        print("      not guessed.")
    else:
        print("\n      (d) ENGINE TERM -- inside ONE payload, at ONE moment.")
        print("          |list_ask - (1 - list_no_bid)| <= 0.0005. Latency")
        print("          between endpoints cannot produce a failure here.")
        _rate("the list ask IS its own no-bid's complement",
              sum(1 for r in have_nb if r.list_is_internally_derived),
              len(have_nb), indent="          ")
        both = [r for r in have_nb if r.skew_gap is not None]
        print("\n      (e) SKEW TERM -- list no-bid vs the BOOK's best no-bid,")
        print("          across two endpoints seconds apart.")
        _rate("the list no-bid equals the book's best no-bid",
              sum(1 for r in both if r.list_no_bid_matches_book),
              len(both), indent="          ")
        print("\n      (f) THE DECOMPOSITION ON EACH (b) DISAGREEMENT")
        rows_b = [r for r in both if r.reproduces is False]
        if not rows_b:
            print("          No (b) disagreement had both terms readable.")
        for row in rows_b:
            print(f"          {row.ticker[-13:]:<13} "
                  f"total {row.ask_diff:+.4f} = "
                  f"engine {-(row.engine_gap or 0.0):+.4f} + "
                  f"skew {-(row.skew_gap or 0.0):+.4f}")
        print("\n          Reading it: a non-zero ENGINE term means the list")
        print("          ask is not this row's own no-bid complement, so (b)")
        print("          is about a pricing engine, not about staleness. A")
        print("          zero engine term with a non-zero SKEW term means the")
        print("          list is book-derived and the two endpoints are simply")
        print("          reading different snapshots.")

    priceable = [r for r in scored if r.legs_all_priceable and not r.empty]
    print("\n  (c) DOES ANY LEVEL DERIVE TO WITHIN 2c OF A LEG'S COST?")
    print(f"      denominator is the {len(priceable)} rows with a non-empty book"
          " AND every leg")
    print("      priceable. Unpriceable legs are excluded, not scored as 'no'.")
    print(f"      excluded for an unpriceable leg: "
          f"{sum(1 for r in scored if not r.legs_all_priceable)}")
    _rate("a level echoes a leg (<= 0.02)",
          sum(1 for r in priceable if r.echoes_a_leg), len(priceable))

    # A pre-registered exclusion still has a direction, and the write-up has to
    # say which way it moved the number. This computes the counterfactual on
    # the excluded rows' PARTIAL leg sets -- which is all that exists for them,
    # and is stated as such rather than presented as a rate.
    excluded = [r for r in scored if not r.legs_all_priceable and not r.empty]
    if excluded:
        would = sum(
            1 for r in excluded
            if (g := echo_gap(r.book, r.leg_costs)) is not None
            and g <= ECHO_TOLERANCE
        )
        k = sum(1 for r in priceable if r.echoes_a_leg)
        n = len(priceable)
        alt_n = n + len(excluded)
        print(f"      DIRECTION OF THE EXCLUSION: had the {len(excluded)} "
              f"excluded rows been")
        print(f"      scored on their partial leg sets, {would} would have "
              f"counted as echoes,")
        print(f"      giving {k + would}/{alt_n} = {(k + would) / alt_n:.1%} "
              f"against the reported {k}/{n} = {k / n:.1%}.")
        print("      The exclusion is defensible, but it is not direction-free "
              "and the")
        print("      write-up must say which way it moved the number.")

    print("\n  SPLIT BY SCOPE -- a pooled number is not a finding until the")
    print("  parts agree, and every cell here is small.")
    print(f"    {'scope':<12} {'n':>3} {'empty':>7} {'no-side':>8} "
          f"{'repro':>7} {'echo':>7}")
    by_scope: dict[str, list[Row]] = {}
    for row in scored:
        by_scope.setdefault(row.scope, []).append(row)
    for scope in ("cross_game", "same_game", "mixed", "undecodable"):
        group = by_scope.get(scope) or []
        if not group:
            print(f"    {scope:<12}   0       --       --      --      --")
            continue
        wb = [r for r in group if r.derived_ask is not None]
        pr = [r for r in group if r.legs_all_priceable and not r.empty]
        print(
            f"    {scope:<12} {len(group):>3} "
            f"{sum(1 for r in group if r.empty):>3}/{len(group):<3} "
            f"{sum(1 for r in group if r.no_side_empty):>3}/{len(group):<4} "
            f"{sum(1 for r in wb if r.reproduces):>3}/{len(wb):<3} "
            f"{sum(1 for r in pr if r.echoes_a_leg):>3}/{len(pr):<3}"
        )
    if scored:
        biggest = Counter(r.scope for r in scored).most_common(1)[0]
        print(f"    largest contributor: {biggest[0]} at "
              f"{biggest[1]}/{len(scored)} = {biggest[1] / len(scored):.0%} "
              "of the pooled rate")

    print("\n  PER ROW")
    print("    'exposure' is THIS row's own list-to-book gap, not the pass's")
    print("    total. Reporting one scalar for the whole pass overstates the")
    print("    early rows' exposure and understates the late ones'. Discovery")
    print("    is newest-first and books are read in that order, so exposure,")
    print("    age and read position are collinear and cannot be separated.")
    for row in scored:
        no_levels = parse_levels(row.book, NO_SIDE)
        yes_levels = parse_levels(row.book, YES_SIDE)
        diff = row.ask_diff
        gap = row.gap_to_leg
        exposure = (row.book_observed_ms - row.list_observed_ms) / 1000.0
        print(
            f"    {row.ticker[-13:]:<13} {row.scope:<11} "
            f"legs{len(row.legs):>3}  "
            f"list {row.list_ask:.4f}  "
            f"book yes{len(yes_levels):>2}/no{len(no_levels):<2}  "
            f"derived "
            f"{f'{row.derived_ask:.4f}' if row.derived_ask is not None else '  none'}"
            f"  diff {f'{diff:+.4f}' if diff is not None else '   n/a'}"
            f"  leggap {f'{gap:.4f}' if gap is not None else '  n/a'}"
            f"  exposure {exposure:>5.2f}s"
            f"  re-read "
            f"{f'{row.confirm_ask:.4f}' if row.confirm_ask is not None else '  GONE'}"
        )
        if row.leg_costs:
            print(f"        legs " + ", ".join(
                f"{leg.get('side')} {leg.get('market_ticker')}"
                f" @ {cost:.4f}"
                for leg, cost in zip(row.legs, row.leg_costs)
            ))

    print(f"\n{'=' * 78}")
    print("The book-empty rate is the one that matters: if a material share of")
    print("quoted rows have no book, the 2,116-row harvest's population is not")
    print("what it was taken to be. Nothing here says WHY a book is empty, and")
    print("nothing here is an edge.")
    print(f"{'=' * 78}\n")


def to_json(rows: list[Row], calls: int) -> dict:
    return {
        "api_calls": calls,
        "echo_tolerance": ECHO_TOLERANCE,
        "grid_tol": GRID_TOL,
        "rows": [
            {
                "ticker": r.ticker,
                "series": r.series,
                "collection": r.collection,
                "scope": r.scope,
                "created_ms": r.created_ms,
                "legs": list(r.legs),
                "leg_costs": r.leg_costs,
                "legs_all_priceable": r.legs_all_priceable,
                "list_ask": r.list_ask,
                "list_bid": r.list_bid,
                "list_no_bid": r.list_no_bid,
                "list_observed_ms": r.list_observed_ms,
                "volume": r.volume,
                "open_interest": r.open_interest,
                "book": r.book,
                "book_observed_ms": r.book_observed_ms,
                "book_error": r.book_error,
                "empty": None if r.book_error else r.empty,
                "no_side_empty": None if r.book_error else r.no_side_empty,
                "derived_ask": r.derived_ask,
                "ask_diff": r.ask_diff,
                "reproduces": r.reproduces,
                "gap_to_leg": r.gap_to_leg,
                "echoes_a_leg": r.echoes_a_leg,
                "still_quoted_after": r.still_quoted_after,
                "confirm_ask": r.confirm_ask,
                "confirm_no_bid": r.confirm_no_bid,
                "engine_gap": r.engine_gap,
                "skew_gap": r.skew_gap,
                "list_is_internally_derived": r.list_is_internally_derived,
                "list_no_bid_matches_book": r.list_no_bid_matches_book,
            }
            for r in rows
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-books", type=int, default=20,
        help="how many eligible combinations to read a book for. One call "
             "each, and the whole run is budgeted at 2 + 1 + N + 1.",
    )
    parser.add_argument(
        "--max-legs", type=int, default=None,
        help="restrict selection to combinations with at most this many legs. "
             "Pass 3 to match the 2,116-row harvest's own eligibility rule "
             "(measure_combo_correlation refuses anything above 3), which is "
             "the only way a rate from this harness can be about that "
             "population. Default: no restriction, as E2 ran.",
    )
    parser.add_argument("--depth", type=int, default=10)
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument(
        "--capture", type=Path, default=None,
        help="write the raw orderbook payloads here, for a wire-format fixture.",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    configure_logging(level=logging.DEBUG if args.verbose else logging.INFO)

    async def go() -> tuple[list[Row], int]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            reader = PublicReader(client)
            rows = await collect(
                reader, max_books=args.max_books, depth=args.depth,
                capture=args.capture, max_legs=args.max_legs,
            )
            return rows, reader.calls

    rows, calls = asyncio.run(go())
    report(rows, calls)

    if args.json:
        args.json.write_text(
            json.dumps(to_json(rows, calls), indent=2), encoding="utf-8"
        )
        print(f"wrote {args.json}")

    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
