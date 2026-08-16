"""Read-only census: how wide is the book on the markets discovery throws away?

Runs the design registered at
`docs/measurements/2026-08-15-preregistration-non-sports-spread-reachability.md`.
**Read that first.** The decision rule, the exclusions and the two cut points
were fixed before any non-sports market was read, and this script does not
restate them -- it computes the statistic and prints the arithmetic. The
verdicts it prints come from thresholds written down before the run.

WHAT THIS DOES
  One `/events?with_nested_markets=true` walk -- the same walk every production
  pass already makes -- split into two arms by `discovery.classify_series`:

    NON-SPORTS  the events discovery rejects and discards in memory
    SPORTS      the events it admits, as a CONTROL measured on the same
                instrument, at the same instant, through the same derivation

  and reports, per series, the median half-spread of the top of book in tenths
  of a cent.

WHY THE CONTROL IS THE POINT
  Without it the output is a number of cents that has to be judged against a
  threshold somebody invented. With it, the claim is a ratio: a spread that is
  wide because *Kalshi* is wide, rather than because non-sports is wide, cancels.

COST AND SAFETY
  - **Zero Odds API credits.** Kalshi REST is unmetered and this makes no Odds
    API call of any kind.
  - **No writes.** No database is opened. Nothing is stored.
  - **No order path**, no deploy, no secret printed.
  - Excluded from the deployed image by `.dockerignore`; a `Tool` in
    `tests/test_has_callers.py`'s sense -- a human runs it from a laptop.

WHAT THIS DOES NOT ESTABLISH
  - **AVAILABILITY IS NOT FILLABILITY.** Every number here is a stored quote. A
    two-sided book at a tight spread is consistent with real resting liquidity
    *and* with a maker who cancels the instant an order arrives. No quote record
    separates them; one small order does. Nothing printed here is evidence about
    what would fill.
  - **One instant.** A spread is a time series and this is a single frame. No
    persistence claim is licensed, and a second look is a NEW registration.
  - **Top of book only.** Size behind the best level is not in the nested
    payload and no orderbook call is made.
  - **It builds no fair value and implies none.** `event_links`, `fair_prices`
    and the devig chain are all keyed on an Odds API `odds_event_id`; a
    non-sports market has no sportsbook counterpart. A narrow spread would mean
    the next question is "where does a probability come from" -- the expensive
    part, and not begun here.
  - **Nothing about whether an edge exists**, in any category. Rule 1 stands.
  - The sports arm is a **unit of cost**, not a standard of goodness: it is the
    same population ADR 0021 refuted a strategy against.

Run:
    .venv\\Scripts\\python.exe -m scripts.census_non_sports_spread [--json OUT]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import KalshiConfig  # noqa: E402
from backend.core.prices import dollars_to_tenths, is_valid_price  # noqa: E402
from backend.kalshi.auth import KalshiAuth  # noqa: E402
from backend.kalshi.discovery import classify_series  # noqa: E402
from backend.kalshi.rest import KalshiRestClient  # noqa: E402
from backend.logging_setup import configure_logging  # noqa: E402

#: Registered at §5. Fixed before the run; see the pre-registration for why
#: these are ratios against a measured control rather than absolute cents.
DEAD_RATIO = 3.0
LIVE_RATIO = 1.5

#: Registered at §5. `CLAUDE.md`: read `n` before the effect size.
MIN_MARKETS_FOR_A_VERDICT = 5

#: The market status that means "tradeable right now".
#:
#: **`active`, not `open`.** `open` is the *event* query parameter
#: (`/events?status=open`); the markets carried inside such an event report
#: `active`. Measured, not documented: 245 of 245 markets in
#: `tests/fixtures/events_sports_nested.json` are `active`, and
#: `discovery.py:535` records the same fact. Filtering on `"open"` here would
#: have excluded every market on the exchange and printed an empty census that
#: looked like a finding -- which is why `tests/test_census_non_sports.py`
#: asserts a non-empty tally against that captured payload.
ACTIVE_STATUS = "active"


@dataclass
class SeriesTally:
    """One series' readable spreads, and everything it refused to read."""

    series_ticker: str
    category: Optional[str] = None
    league: Optional[str] = None
    half_spreads: list[float] = field(default_factory=list)
    # The derived YES ask of every readable market, so a "tight" series can be
    # told apart from a *cheap* one. **Added after the first run, which could
    # not.** A half-spread of 0.5 tenths on a contract trading at 2 tenths is a
    # ~25% round-trip cost; the same 0.5 on a 50c contract is 1%. The first run
    # ranked the second-cheapest series on the exchange as 20x tighter than a
    # coin-flip baseball line on exactly that confusion. `CLAUDE.md` rule:
    # bucket by the price you would actually pay.
    asks: list[int] = field(default_factory=list)
    markets_seen: int = 0
    events_seen: int = 0
    # Every exclusion is counted. A denominator that quietly shrinks is how a
    # spread census reports the tightest markets it happened to be able to read.
    #
    # **`one_sided` and `settled` were one counter until 2026-08-16, and the
    # merged name was the wrong one.** Kalshi never omits `yes_bid_dollars` or
    # `no_bid_dollars`; it sends `"0.0000"` for a side with no bid. So
    # `excluded_unreadable` was 0 across all 81,420 markets of the first run --
    # dead code -- while 28,677 markets (35.2%) were dropped as "settled_price"
    # when most were **live markets with one empty side**. That is not a neutral
    # shrink: it removes precisely the markets where entry cost is infinite, so
    # it biases every surviving median toward tight.
    excluded_field_absent: int = 0
    excluded_not_active: int = 0
    excluded_one_sided: int = 0
    excluded_settled: int = 0
    excluded_crossed: int = 0

    @property
    def n(self) -> int:
        return len(self.half_spreads)

    @property
    def median_half_spread(self) -> Optional[float]:
        """`None`, never 0.0, when nothing was readable.

        A zero here would read as "this market is perfectly tight", which is the
        flattering misreading of a measurement that did not happen.
        """
        return statistics.median(self.half_spreads) if self.half_spreads else None

    @property
    def iqr_half_spread(self) -> Optional[list[float]]:
        """The registered §4 output that the first run silently never computed.

        `None` under four observations: `statistics.quantiles` needs more than
        one point per cut, and a quartile over three numbers is decoration.
        """
        if len(self.half_spreads) < 4:
            return None
        q = statistics.quantiles(self.half_spreads, n=4)
        return [q[0], q[2]]

    @property
    def median_ask(self) -> Optional[int]:
        """Median derived ask, tenths. The price level the spread sits at."""
        return statistics.median(self.asks) if self.asks else None

    @property
    def readable_share(self) -> Optional[float]:
        """Fraction of markets seen that produced a spread.

        Reported per series because the first run's arm-level 63.1% hid series
        where it was 4%: `KXETHD` returned a verdict off 15 of 390 rungs.
        """
        if not self.markets_seen:
            return None
        return self.n / self.markets_seen


def _tenths(value) -> Optional[int]:
    """Kalshi's dollar string to integer tenths, or `None`.

    Unreadable resolves to `None` and never to 0 -- a market with no bid is not
    a market with a zero bid, and `core/prices` is the one place that decision
    is made.
    """
    return dollars_to_tenths(value)


def tally_event(
    event: dict,
    tallies: dict[str, SeriesTally],
    unknown_statuses: Optional[dict[str, int]] = None,
) -> str:
    """Fold one event's markets into its series tally. Returns the arm.

    The arm is decided by `classify_series` -- the **production** classifier,
    not a re-expression of it here. If discovery's notion of "in scope" ever
    changes, this census follows it rather than quietly measuring a different
    split than the one the pipeline applies.
    """
    if unknown_statuses is None:
        unknown_statuses = defaultdict(int)
    info = classify_series(event)
    arm = "sports" if info.in_scope else "non_sports"
    key = f"{arm}:{info.series_ticker or '(none)'}"
    tally = tallies.setdefault(
        key,
        SeriesTally(
            series_ticker=info.series_ticker or "(none)",
            category=(event.get("category") or None),
            league=info.league,
        ),
    )

    tally.events_seen += 1
    for market in event.get("markets") or []:
        tally.markets_seen += 1
        status = (market.get("status") or "").lower()
        if status != ACTIVE_STATUS:
            tally.excluded_not_active += 1
            # Named, not just counted. `discovery.py` already carries the
            # lesson that a filter's *exclusions* must be decisions: an
            # unrecognised status silently dropped is how a wire change becomes
            # a quiet halving of the denominator.
            key_status = status or "(missing)"
            # `.get` rather than `+= 1`: a caller passing an ordinary dict is
            # reasonable and must not raise `KeyError` inside a census.
            unknown_statuses[key_status] = unknown_statuses.get(key_status, 0) + 1
            continue

        yes_bid = _tenths(market.get("yes_bid_dollars"))
        no_bid = _tenths(market.get("no_bid_dollars"))
        if yes_bid is None or no_bid is None:
            # A field genuinely absent from the payload. Kept as its own
            # counter and expected to stay 0: Kalshi sends "0.0000" for an
            # empty side, never nothing. It is retained rather than deleted
            # because a counter that is provably 0 today is how a wire change
            # announces itself tomorrow -- but it must NOT be the bucket that
            # one-sided books fall into, which is what it was.
            tally.excluded_field_absent += 1
            continue

        # **An empty side is not a settled market, and the two must not share a
        # counter.** `yes_bid == 0` means nobody bids YES; the market can be
        # perfectly live. Merging it with a genuine settlement dropped 28,677
        # markets under one wrong label on the first run, and it drops them
        # exactly where books are thinnest -- so the surviving median is biased
        # tight by an amount that was, until this split, unmeasurable.
        if yes_bid == 0 or no_bid == 0:
            if yes_bid == 0 and no_bid == 1000:
                # Both sides at the extreme: the outcome is known. A YES ask of
                # 0 yields a zero fee, a $0.00 effective price and a fabricated
                # edge, which is why `core/ev` refuses it.
                tally.excluded_settled += 1
            elif yes_bid == 1000 and no_bid == 0:
                tally.excluded_settled += 1
            else:
                tally.excluded_one_sided += 1
            continue

        # The price you would pay for YES is one dollar minus the resting NO
        # bid. Derived, never read from an `ask` field -- the derived-ask
        # identity is the single chokepoint this repo prices everything through.
        yes_ask = 1000 - no_bid
        if not is_valid_price(yes_ask) or not is_valid_price(yes_bid):
            # Anything still at an extreme after the split above. Kept as a
            # backstop so `is_valid_price` remains the authority on what a
            # tradeable price is, rather than the two comparisons above.
            tally.excluded_settled += 1
            continue

        spread = yes_ask - yes_bid
        if spread < 0:
            # A crossed book is a data state, not a negative cost. Counted so it
            # cannot be averaged into a tight median.
            tally.excluded_crossed += 1
            continue
        tally.half_spreads.append(spread / 2.0)
        tally.asks.append(yes_ask)

    return arm


def verdict(ratio: Optional[float], n: int) -> str:
    """The registered decision rule, and nothing else.

    `INSUFFICIENT` is returned before any ratio is consulted: a series with four
    readable markets has not failed the bar, it could not reach it, and this
    repo has already published one zero that meant "could not fire" while
    reading as "fired and caught nothing".
    """
    if n < MIN_MARKETS_FOR_A_VERDICT:
        return "INSUFFICIENT"
    if ratio is None:
        return "UNRESOLVED"
    if ratio >= DEAD_RATIO:
        return "DEAD"
    if ratio <= LIVE_RATIO:
        return "WORTH A FAIR VALUE"
    return "UNRESOLVED"


async def run(max_pages: Optional[int]) -> dict:
    config = KalshiConfig.load()
    auth = KalshiAuth(config.api_key, config.private_key_path)
    tallies: dict[str, SeriesTally] = {}
    counts: dict[str, int] = defaultdict(int)
    unknown_statuses: dict[str, int] = defaultdict(int)

    async with KalshiRestClient(config, auth) as client:
        async for event in client.events(
            status="open", with_nested_markets=True, max_pages=max_pages
        ):
            counts[tally_event(event, tallies, unknown_statuses)] += 1

    sports = [t for k, t in tallies.items() if k.startswith("sports:")]
    non_sports = [t for k, t in tallies.items() if k.startswith("non_sports:")]

    # The control: the median of the per-series medians, not a pooled median
    # over markets. One series with 400 markets would otherwise BE the control.
    sports_medians = [
        t.median_half_spread
        for t in sports
        if t.median_half_spread is not None and t.n >= MIN_MARKETS_FOR_A_VERDICT
    ]
    control = statistics.median(sports_medians) if sports_medians else None

    # **The control per league, because the pooled one is not one number.**
    # On the first run 9 of the 19 contributing series were MLB and four of
    # those held the six tightest slots; dropping MLB moved the control from
    # 10.0 to 40.0 tenths and flipped 849 verdicts. A denominator that moves 4x
    # on the season cannot carry a verdict, and the pooled figure hid that
    # completely. Reported so the instability is visible in the artifact rather
    # than reachable only by re-deriving it.
    by_league: dict[str, list[float]] = defaultdict(list)
    for t in sports:
        if t.median_half_spread is not None and t.n >= MIN_MARKETS_FOR_A_VERDICT:
            by_league[t.league or "(unknown)"].append(t.median_half_spread)
    league_controls = {
        league: {
            "median_half_spread_tenths": statistics.median(medians),
            "series": len(medians),
        }
        for league, medians in sorted(by_league.items())
    }
    # Leave-one-league-out, which is the perturbation that actually matters.
    jackknife = {}
    for dropped in by_league:
        kept = [m for lg, ms in by_league.items() if lg != dropped for m in ms]
        jackknife[f"without {dropped}"] = (
            statistics.median(kept) if kept else None
        )

    rows = []
    for tally in sorted(non_sports, key=lambda t: -t.n):
        median = tally.median_half_spread
        ratio = (
            median / control
            if median is not None and control not in (None, 0)
            else None
        )
        rows.append(
            {
                "series": tally.series_ticker,
                "category": tally.category,
                "n": tally.n,
                "events_seen": tally.events_seen,
                "markets_seen": tally.markets_seen,
                "readable_share": tally.readable_share,
                "median_half_spread_tenths": median,
                # The registered §4 output the first run never computed.
                "iqr_half_spread_tenths": tally.iqr_half_spread,
                # The price the spread sits at. Without it, "tight" and "cheap"
                # are indistinguishable and a longshot ladder's tick-floor book
                # outranks a coin-flip moneyline.
                "median_ask_tenths": tally.median_ask,
                "ratio_to_sports": ratio,
                "verdict": verdict(ratio, tally.n),
                "excluded": {
                    "field_absent": tally.excluded_field_absent,
                    "not_active": tally.excluded_not_active,
                    "one_sided": tally.excluded_one_sided,
                    "settled": tally.excluded_settled,
                    "crossed": tally.excluded_crossed,
                },
            }
        )

    return {
        "run_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
        "events": {"sports": counts["sports"], "non_sports": counts["non_sports"]},
        "control": {
            "median_half_spread_tenths": control,
            "series_contributing": len(sports_medians),
            "per_league": league_controls,
            "leave_one_league_out": jackknife,
        },
        "thresholds": {
            "dead_ratio": DEAD_RATIO,
            "live_ratio": LIVE_RATIO,
            "min_markets": MIN_MARKETS_FOR_A_VERDICT,
        },
        # Every status that was not `active`, so a wire-format change shows up
        # as a named value rather than as a shrunken denominator.
        "excluded_statuses": dict(unknown_statuses),
        "non_sports": rows,
        # The control arm carries the SAME fields as the treatment arm. On the
        # first run it carried three, so "the arms are comparable because the
        # instrument is the same" could not be checked -- the instrument had
        # thrown away the data needed to check it.
        "sports_detail": [
            {
                "series": t.series_ticker,
                "league": t.league,
                "n": t.n,
                "events_seen": t.events_seen,
                "markets_seen": t.markets_seen,
                "readable_share": t.readable_share,
                "median_half_spread_tenths": t.median_half_spread,
                "iqr_half_spread_tenths": t.iqr_half_spread,
                "median_ask_tenths": t.median_ask,
                "excluded": {
                    "field_absent": t.excluded_field_absent,
                    "not_active": t.excluded_not_active,
                    "one_sided": t.excluded_one_sided,
                    "settled": t.excluded_settled,
                    "crossed": t.excluded_crossed,
                },
            }
            for t in sorted(sports, key=lambda t: -t.n)
        ],
    }


def render(result: dict) -> str:
    out: list[str] = []
    stamp = datetime.fromtimestamp(
        result["run_ms"] / 1000, timezone.utc
    ).isoformat()
    out.append(f"Non-sports spread census  {stamp}")
    out.append("=" * 78)
    out.append(
        f"events: {result['events']['sports']} sports, "
        f"{result['events']['non_sports']} non-sports"
    )
    control = result["control"]["median_half_spread_tenths"]
    out.append(
        "CONTROL median half-spread (sports, median of per-series medians): "
        + ("unmeasurable" if control is None else f"{control:.1f} tenths")
    )
    out.append(
        f"  from {result['control']['series_contributing']} sports series with "
        f">= {result['thresholds']['min_markets']} readable markets"
    )
    # Printed immediately under the control, not in an appendix. A reader who
    # sees only the pooled number will reason as though it were stable.
    for league, info in result["control"]["per_league"].items():
        out.append(
            f"    {league:<24}{info['series']:>3} series  "
            f"{info['median_half_spread_tenths']:>7.1f}"
        )
    for label, value in result["control"]["leave_one_league_out"].items():
        out.append(
            f"    {label:<24}    control -> "
            + ("--" if value is None else f"{value:.1f}")
        )
    out.append("")

    header = f"{'series':<28}{'n':>5}{'half':>8}{'ratio':>8}  verdict"
    out.append(header)
    out.append("-" * 78)
    for row in result["non_sports"]:
        half = row["median_half_spread_tenths"]
        ratio = row["ratio_to_sports"]
        out.append(
            f"{row['series'][:27]:<28}{row['n']:>5}"
            f"{'   --' if half is None else f'{half:>8.1f}'}"
            f"{'   --' if ratio is None else f'{ratio:>8.2f}'}"
            f"  {row['verdict']}"
        )
    out.append("")
    out.append(
        "half = median half-spread in TENTHS of a cent, top of book, "
        "derived ask (1000 - no_bid)."
    )
    out.append(
        "AVAILABILITY IS NOT FILLABILITY. One instant. Top of book only. "
        "No fair value exists for any row above."
    )
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json", type=Path, help="Write the full result as JSON here"
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Cap the /events walk. Omit for the whole universe.",
    )
    args = parser.parse_args()

    # `configure_logging` and not `basicConfig`: the Odds API key leaks through
    # httpx URL logging otherwise. No Odds call is made here, and the habit is
    # still the rule.
    configure_logging()
    result = asyncio.run(run(args.max_pages))
    print(render(result))
    if args.json:
        args.json.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
