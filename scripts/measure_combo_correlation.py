"""Read Kalshi's combo prices as correlation measurements. Creates nothing.

    .venv\\Scripts\\python.exe scripts\\measure_combo_correlation.py
    .venv\\Scripts\\python.exe scripts\\measure_combo_correlation.py --pages 10

Free. Kalshi is unmetered and no Odds API credit is touched.

Why this exists
---------------
`core/correlation.py` refuses to guess a same-game correlation: the sign
depends on the specific pair, so any default is a guess wearing a number. Its
own docstring names the way out -- a combo quote *is* a joint probability, so
given the leg marginals it inverts to the measured rho.

Obtaining one was recorded for two days as "needs Joe: one POST .../lookup that
creates a market on the exchange". **It does not.** Kalshi's own users create
those markets continuously by tapping legs in the app, they are returned by
`/markets` with `status=open`, and every one of them carries:

    mve_selected_legs   [{event_ticker, market_ticker, side}, ...]  exact legs
    mve_collection_ticker                                           the collection
    yes_bid_dollars / yes_ask_dollars                               the joint

So the joint is readable, the legs are decodable, and nothing has to be
written. The authorised lookup stays unspent.

A quote lives for about a minute, so this polls
-----------------------------------------------
Measured 2026-08-09: 5,000 consecutive open markets in this series span a
`created_time` range of **six minutes and forty-eight seconds**. Kalshi mints
roughly 700 provisional combination markets a minute, `/markets` returns them
newest first, and only the newest few carry a two-sided quote -- 4 of those
5,000, every one created within three minutes of the walk.

That is the whole explanation of the "~99.8% KXMVE with no volume" observation
this project has carried since step 1, now with a rate attached rather than a
proportion. It also means depth-first paging is the wrong shape: page 200 is
seven minutes stale and will never be quoted again. **Poll the first page
instead**, and let the sample accumulate over `--rounds`.

How a number here is obtained
-----------------------------
1. Read the first `--pages` pages of open markets per series, `--rounds` times,
   deduplicating by ticker. **Never a blind `/markets` walk** -- that is the
   discovery-hygiene rule in CLAUDE.md.
2. Keep the ones quoted on both sides. A one-sided book has no mid.
3. Read each leg's own market for its marginal, honouring `side` -- a `no` leg
   is `1 - yes`. A leg without a two-sided quote **refuses the whole combo**
   rather than contributing a substituted number.
4. Invert with `core.correlation.implied_correlation` at the joint's bid, mid
   and ask.

Reading the output
------------------
**Read the cross-game rows before the same-game ones.** Legs from different
games are as close to independent as this venue offers, so their measured rho
is an estimate of this method's *own bias*, not of dependence. A same-game rho
is only interesting to the extent it exceeds that.

**The control ran, and it settled which estimator works.** Measured
2026-08-09 over 46,916 distinct combination markets polled across 55 minutes:

    cross-game, TWO-SIDED, n=23    rho at mid  +0.003   sd 0.089
    cross-game, ask only,  n=308   rho at ask  +0.234   sd 0.254

Independent games are rho = 0. **At the mid, the method returns it** -- mean
+0.003 on a population whose truth is zero.

**The ask-only population is not usable for correlation, and it is 93% of the
sample.** Its bias is not merely large, it is not constant: sd 0.254, spanning
-0.757 to +0.898. A bias you cannot subtract is a refusal, not an offset. It is
still reported, separately and labelled, because an upper bound is a fact --
but no same-game claim may be built on it.

So the measurement worth accumulating is **two-sided combinations, read at the
mid**, and they are rare: 60 of 46,916 markets carried a bid, and **none of the
same-game ones did**. That is the honest state -- a validated method waiting on
a sample, not a number.

The Frechet rate is a finding, not a nuisance
----------------------------------------------
An ask above `min(marginal)` is one **no dependence structure can produce**, so
the inversion refuses it. The refusal rate is not uniform:

    cross-game   102/437   23%
    mixed          9/19    47%
    same-game     17/18    94%

The gradient runs cleanly through `mixed`, which is what you would expect if
same-game *pairs* drive it. The mechanism is straightforward: strong positive
dependence pushes the true joint up toward `min(marginal)`, and once it is near
that ceiling any margin at all puts the ask above it.

Read carefully, that is evidence of strong positive same-game dependence
obtained *from the refusals* rather than from the surviving numbers. Two things
stop it being more than suggestive: a stale leg quote produces the same symptom,
and same-game combinations are somewhat more prop-heavy than cross-game ones,
though less so than expected -- their legs are mostly TOTAL, SPREAD, GAME and
F5, the same series the cross-game ones use.

To sharpen it, compare the combination's ask against **the cheapest leg's own
ask** rather than its mid: a combination that costs more than a leg which pays
out in a superset of cases is dominated outright, with no correlation estimate
needed. Leg bids and asks are recorded in the `--json` output for exactly that,
as of this run.

What this does not establish
----------------------------
- **Not an edge, and not tradeable.** It measures what Kalshi's combo book
  says about dependence. Nothing here compares that to a fair value, and no
  combo fee model has been verified for this venue.
- **Nothing about liquidity.** These markets are `is_provisional` and mostly
  carry zero volume and zero open interest. A two-sided quote on an untraded
  market is a quoter's opinion, not a transaction.
- **Equicorrelation only.** With three or more legs a single rho is fitted to
  all pairs. Real same-game legs are not equicorrelated, so treat a multi-leg
  number as a summary, not as a pairwise measurement.
- **One slate.** Every number here is whatever was open when it ran, in
  August, with MLB and NFL preseason live and NBA/NHL/NCAAF out of season.
- `active_quoters` on a collection leg is **empty for every leg Kalshi
  publishes** -- 14,240 of 14,240 measured 2026-08-09 -- while those same leg
  markets are two-sided with real open interest. It is not a liquidity signal
  and nothing here reads it.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import KalshiConfig  # noqa: E402
from backend.core.correlation import (  # noqa: E402
    CorrelationUnreachable,
    Leg,
    implied_correlation,
)
from backend.kalshi.rest import KalshiRestClient  # noqa: E402
from backend.logging_setup import configure_logging  # noqa: E402

# The collections that can hold a combination. Same-game series are listed even
# though they carried no open market on 2026-08-09 -- an empty result for one
# series is a fact about the calendar, and dropping it from the list would make
# that fact invisible the day it changes.
MVE_SERIES = (
    "KXMVESPORTSMULTIGAMEEXTENDED",
    "KXMVECROSSCATEGORY",
    "KXMVECROSSCATEGORY-SHARD1",
    "KXMVENFLSINGLEGAME",
    "KXMVENBASINGLEGAME",
    "KXMVENFLMULTIGAME",
    "KXMVENFLMULTIGAMEEXTENDED",
    "KXMVENBAMULTIGAMEEXTENDED",
)

# `KXMLBTOTAL-26AUG091410CHCKC-14` -> fixture `26AUG091410CHCKC`. The fixture is
# the middle segment, so two legs are same-game exactly when theirs match. Taken
# from the ticker rather than from a date field because the ticker is what
# Kalshi guarantees to be unique per fixture.
FIXTURE = re.compile(r"^[A-Z0-9]+-([0-9]{2}[A-Z]{3}[0-9]+[A-Z]+)")

logger = logging.getLogger("measure_combo_correlation")


def fixture_of(market_ticker: str) -> Optional[str]:
    match = FIXTURE.match(market_ticker)
    return match.group(1) if match else None


def dollars(value: Any) -> Optional[float]:
    """Kalshi's dollar strings -> float, or None. Never 0.0 on unreadable.

    `0.0` is a legitimate price here (a settled loser), so a parser that
    returns it on garbage is indistinguishable from one that read correctly.
    """
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if 0.0 <= parsed <= 1.0 else None


@dataclass(frozen=True)
class Quote:
    """An ask, and a bid only if there is one.

    Nearly every combination is quoted on one side: someone bids NO, nobody
    bids YES, so `yes_bid` is a true `0.0000` and `yes_ask` is a real price you
    could lift. Requiring both sides threw away about nine tenths of the sample
    -- measured 2026-08-09, 108 asks against 4 two-sided in ~2,400 markets.

    `bid` is `Optional` rather than defaulting to 0.0 precisely because 0 is a
    legitimate bid here. `mid` is `None` when there is no bid, never the ask
    halved: a mid invented from one side is a made-up number wearing a name
    that means "the market's opinion".
    """

    ask: float
    bid: Optional[float] = None

    @property
    def mid(self) -> Optional[float]:
        return None if self.bid is None else (self.bid + self.ask) / 2

    @property
    def width(self) -> Optional[float]:
        return None if self.bid is None else self.ask - self.bid


def readable_quote(market: dict) -> Optional[Quote]:
    """A usable quote, or None. An ask is required; a bid is a bonus."""
    ask = dollars(market.get("yes_ask_dollars"))
    if ask is None or not 0.0 < ask < 1.0:
        return None
    bid = dollars(market.get("yes_bid_dollars"))
    if bid is None or not 0.0 < bid <= ask:
        bid = None
    return Quote(ask=ask, bid=bid)


@dataclass
class Combo:
    ticker: str
    collection: str
    joint: Quote
    legs: tuple[dict, ...]
    subtitle: str

    @property
    def fixtures(self) -> tuple[Optional[str], ...]:
        return tuple(fixture_of(leg["market_ticker"]) for leg in self.legs)

    @property
    def scope(self) -> str:
        seen = [f for f in self.fixtures if f]
        if len(seen) != len(self.legs):
            return "undecodable"
        distinct = set(seen)
        if len(distinct) == 1:
            return "same_game"
        if len(distinct) == len(seen):
            return "cross_game"
        return "mixed"


@dataclass
class Measurement:
    combo: Combo
    # Each leg's own quote, kept beside the marginal it produced. The marginal
    # is a mid; deciding whether a combination is worse than simply buying its
    # cheapest leg needs that leg's ASK, and reconstructing it afterwards is
    # impossible because these markets are gone within minutes.
    leg_quotes: tuple[Quote, ...]
    marginals: tuple[float, ...]
    rho_at_bid: Optional[float]
    rho_at_mid: Optional[float]
    rho_at_ask: Optional[float]
    independent_joint: float
    note: str = ""


@dataclass
class Survey:
    rounds: int = 0
    scanned: int = 0
    distinct: int = 0
    with_legs: int = 0
    quoted: int = 0
    two_sided: int = 0
    refused: Counter = field(default_factory=Counter)
    leg_counts: Counter = field(default_factory=Counter)
    measurements: list[Measurement] = field(default_factory=list)
    series_seen: Counter = field(default_factory=Counter)


async def open_mve_markets(
    api: KalshiRestClient, series: str, *, pages: int
) -> list[dict]:
    """The newest open markets for one series. Bounded."""
    out: list[dict] = []
    cursor: Optional[str] = None
    for _ in range(pages):
        params: dict[str, Any] = {
            "series_ticker": series, "limit": 200, "status": "open",
        }
        if cursor:
            params["cursor"] = cursor
        payload = await api.request("GET", "/markets", params=params)
        batch = payload.get("markets") or []
        out.extend(batch)
        cursor = payload.get("cursor")
        if not cursor or not batch:
            break
    return out


async def leg_quote(
    api: KalshiRestClient, market_ticker: str, cache: dict[str, Optional[Quote]]
) -> Optional[Quote]:
    if market_ticker in cache:
        return cache[market_ticker]
    try:
        payload = await api.request("GET", f"/markets/{market_ticker}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("leg %s could not be read: %s", market_ticker, exc)
        cache[market_ticker] = None
        return None
    # A LEG must be two-sided, unlike the joint. The leg supplies a marginal
    # probability, and the only unbiased single number for that is the mid --
    # an ask alone overstates it, and every marginal overstated pushes the
    # inverted rho down by an amount nothing in the output would show.
    market = payload.get("market") or {}
    quote = readable_quote(market)
    if quote is None or quote.bid is None:
        cache[market_ticker] = None
        return None
    cache[market_ticker] = quote
    return quote


def marginal_for_leg(leg: dict, quote: Quote) -> Optional[float]:
    """The probability this leg contributes to the joint, honouring `side`.

    A `no` leg contributes `1 - yes`. Getting that backwards produces entirely
    plausible correlations of the wrong sign and nothing in the output says so
    -- the shape this repo has already recorded on `probability_cover` and on
    NO-side CLV.

    A function rather than four lines inside the walk because a test that
    re-implements the rule is asserting its own copy of it. There is one path,
    so it cannot disagree with itself.

    Returns `None` for a side that is neither `yes` nor `no`, and for a quote
    with no mid -- refusing the leg, never substituting for it.
    """
    if quote.mid is None:
        return None
    side = str(leg.get("side") or "yes").lower()
    if side == "yes":
        return quote.mid
    if side == "no":
        return 1.0 - quote.mid
    logger.warning(
        "leg %s has side %r, which is neither yes nor no; refusing the "
        "combination rather than assuming",
        leg.get("market_ticker"), side,
    )
    return None


def measure(
    combo: Combo,
    marginals: Sequence[float],
    leg_quotes: Sequence[Quote] = (),
) -> Measurement:
    """Invert the joint at each price there is. A failure is recorded, never
    guessed."""
    # `event_key`/`league`/`commence_ms` drive `classify`, which
    # `implied_correlation` never calls -- it fits one rho to the marginals it
    # is given. They are filled from the real fixture anyway so that a future
    # caller reading these Legs sees the truth rather than a placeholder that
    # would silently make every pair look cross-game.
    legs = [
        Leg(
            label=leg["market_ticker"],
            probability=p,
            event_key=fixture_of(leg["market_ticker"]) or leg["market_ticker"],
            league=leg["market_ticker"].split("-")[0],
            commence_ms=0,
        )
        for leg, p in zip(combo.legs, marginals)
    ]
    independent = 1.0
    for p in marginals:
        independent *= p

    def invert(joint: Optional[float]) -> Optional[float]:
        if joint is None:
            return None
        try:
            return implied_correlation(legs, joint)
        except CorrelationUnreachable:
            return None

    rho_ask = invert(combo.joint.ask)
    note = ""
    if rho_ask is None:
        note = (
            "the ask is outside the Frechet bounds for these marginals -- no "
            "dependence structure produces it, so the joint and the legs "
            "disagree. Most often the legs moved after the combo was minted"
        )
    return Measurement(
        combo=combo,
        leg_quotes=tuple(leg_quotes),
        marginals=tuple(marginals),
        rho_at_bid=invert(combo.joint.bid),
        rho_at_mid=invert(combo.joint.mid),
        rho_at_ask=rho_ask,
        independent_joint=independent,
        note=note,
    )


async def survey(
    api: KalshiRestClient,
    *,
    pages: int,
    rounds: int,
    interval_s: float,
    max_legs: int,
) -> Survey:
    result = Survey()
    # Leg quotes are cached across rounds on purpose: a combo minted at 06:27
    # is being compared against the leg prices that were live when it was
    # minted, and re-reading a leg minutes later would price the joint and its
    # legs at two different moments. Same reason `run_loop` takes one stamp for
    # a whole pass.
    cache: dict[str, Optional[Quote]] = {}
    seen: set[str] = set()

    for round_index in range(rounds):
        if round_index:
            await asyncio.sleep(interval_s)
        result.rounds += 1
        fresh_this_round = 0

        for series in MVE_SERIES:
            try:
                markets = await open_mve_markets(api, series, pages=pages)
            except Exception as exc:  # noqa: BLE001
                logger.warning("series %s could not be read: %s", series, exc)
                continue
            result.scanned += len(markets)
            result.series_seen[series] += len(markets)

            for market in markets:
                ticker = market.get("ticker") or ""
                if ticker in seen:
                    continue
                seen.add(ticker)
                result.distinct += 1
                fresh_this_round += 1

                legs = market.get("mve_selected_legs") or []
                if not legs:
                    result.refused["no_mve_selected_legs"] += 1
                    continue
                result.with_legs += 1

                joint = readable_quote(market)
                if joint is None:
                    result.refused["joint_unquoted"] += 1
                    continue
                result.quoted += 1
                if joint.bid is not None:
                    result.two_sided += 1
                result.leg_counts[len(legs)] += 1

                # Equicorrelation fits ONE rho to every pair. On two legs that
                # is the pairwise correlation exactly; on fifteen it is an
                # average over pairs that are nothing like each other, and
                # reporting it beside a two-leg number would put them in the
                # same column. Refused rather than fitted, and counted so the
                # exclusion is visible.
                if len(legs) > max_legs:
                    result.refused["too_many_legs_for_equicorrelation"] += 1
                    continue

                combo = Combo(
                    ticker=ticker,
                    collection=market.get("mve_collection_ticker") or "",
                    joint=joint,
                    legs=tuple(legs),
                    subtitle=str(market.get("yes_sub_title") or ""),
                )

                marginals: list[float] = []
                quotes: list[Quote] = []
                for leg in legs:
                    quote = await leg_quote(api, leg["market_ticker"], cache)
                    marginal = (
                        None if quote is None else marginal_for_leg(leg, quote)
                    )
                    if marginal is None or quote is None:
                        break
                    marginals.append(marginal)
                    quotes.append(quote)
                else:
                    result.measurements.append(
                        measure(combo, marginals, quotes)
                    )
                    continue
                result.refused["leg_unusable"] += 1

        logger.info(
            "round %d/%d: %d new tickers, %d measurable so far",
            result.rounds, rounds, fresh_this_round, len(result.measurements),
        )

    return result


def _describe(label: str, values: Sequence[Optional[float]]) -> None:
    """One line of distribution, or an explicit `none`.

    Prints the `n` first and always, including zero. A summary that appears
    only when there is something to say makes an empty population look like a
    population nobody measured.
    """
    usable = sorted(v for v in values if v is not None)
    if not usable:
        print(f"      {label}\n        n=0")
        return
    mean = sum(usable) / len(usable)
    spread = ""
    if len(usable) > 1:
        variance = sum((v - mean) ** 2 for v in usable) / (len(usable) - 1)
        spread = f"  sd {variance ** 0.5:.3f}"
    print(f"      {label}")
    print(f"        n={len(usable)}  min {usable[0]:+.3f}  "
          f"median {usable[len(usable) // 2]:+.3f}  max {usable[-1]:+.3f}  "
          f"mean {mean:+.3f}{spread}")


def report(result: Survey) -> None:
    print(f"\n{'=' * 78}")
    print("Kalshi combo prices as correlation measurements")
    print(f"{'=' * 78}")
    print(f"  polling rounds             {result.rounds:>6,}")
    print(f"  market rows read           {result.scanned:>6,}")
    print(f"  distinct tickers           {result.distinct:>6,}")
    print(f"  carrying mve_selected_legs {result.with_legs:>6,}")
    print(f"  with a readable ask        {result.quoted:>6,}")
    print(f"      of those, two-sided    {result.two_sided:>6,}")
    print(f"  measurable                 {len(result.measurements):>6,}")
    for reason, count in result.refused.most_common():
        print(f"      refused: {reason:<30} {count:>6,}")
    if result.leg_counts:
        spread = ", ".join(
            f"{legs}:{n}" for legs, n in sorted(result.leg_counts.items())
        )
        print(f"  legs per quoted combo      {spread}")
    print("  NOT A CENSUS. These are whichever combinations Kalshi's own users")
    print("  happened to build while this ran, quoted for about a minute each.")

    by_scope: dict[str, list[Measurement]] = {}
    for m in result.measurements:
        by_scope.setdefault(m.combo.scope, []).append(m)

    # Cross-game first, deliberately. It is the control: different games are as
    # close to independent as this venue offers, so its rho is this method's own
    # bias and everything below has to be read against it.
    order = ["cross_game", "mixed", "same_game", "undecodable"]
    for scope in order:
        entries = by_scope.get(scope) or []
        if not entries:
            print(f"\n--- {scope}: none")
            continue
        usable = [m for m in entries if m.rho_at_ask is not None]
        print(f"\n--- {scope}: n={len(entries)} ({len(usable)} invertible)")
        if scope == "cross_game":
            print("    THE CONTROL. Different games are near-independent, so a")
            print("    non-zero rho here is this method's bias, not dependence.")
        if scope == "mixed":
            print("    NOT a same-game measurement. One rho is fitted across")
            print("    pairs that are same-game and pairs that are not, so it")
            print("    is an average of two different quantities.")

        # Two-sided first and separately, because the control says these are
        # the only ones that measure anything. Pooling them with the ask-only
        # rows would drag a validated estimator toward a biased one and report
        # the mixture as though it were one quantity.
        two = [m for m in entries if m.combo.joint.bid is not None]
        one = [m for m in entries if m.combo.joint.bid is None]
        _describe(
            "TWO-SIDED, at the mid -- the estimator the control validates",
            [m.rho_at_mid for m in two],
        )
        _describe(
            "     ...the same rows at bid / ask, which bracket it",
            [m.rho_at_bid for m in two] + [m.rho_at_ask for m in two],
        )
        _describe(
            "ASK ONLY -- an upper bound, and NOT usable for correlation: the "
            "control's\n        bias here is large and not constant, so it "
            "cannot be subtracted off",
            [m.rho_at_ask for m in one],
        )
        # Its own line, because the *rate* carries information the surviving
        # rows cannot. An ask outside the Frechet bounds is one no dependence
        # structure produces, and same-game combinations fail it far more often
        # than cross-game ones -- a statement about same-game dependence, not a
        # nuisance to be filtered away.
        unreachable = [m for m in entries if m.rho_at_ask is None]
        print(f"      outside the Frechet bounds: {len(unreachable)}/"
              f"{len(entries)} "
              f"({100 * len(unreachable) / max(1, len(entries)):.0f}%)")
        for m in entries[:8]:
            print(f"\n    {m.combo.ticker}")
            print(f"      {m.combo.subtitle[:70]}")
            print(f"      legs      " + ", ".join(
                f"{leg['side']} {leg['market_ticker']}" for leg in m.combo.legs))
            print("      marginals " + ", ".join(f"{p:.4f}" for p in m.marginals)
                  + f"   independent joint {m.independent_joint:.4f}")
            bid = m.combo.joint.bid
            mid = m.combo.joint.mid
            print(f"      joint     bid "
                  f"{f'{bid:.4f}' if bid is not None else '  none':>6}  "
                  f"mid {f'{mid:.4f}' if mid is not None else '  none':>6}  "
                  f"ask {m.combo.joint.ask:.4f}")
            print("      rho       " + "  ".join(
                f"{label} {value:+.3f}" if value is not None else f"{label} n/a"
                for label, value in (
                    ("at bid", m.rho_at_bid),
                    ("at mid", m.rho_at_mid),
                    ("at ask", m.rho_at_ask),
                )
            ))
            if m.note:
                print(f"      NOTE      {m.note}")

    print(f"\n{'=' * 78}")
    print("Read the cross-game block first: it is the control, its true rho is")
    print("zero, and only the TWO-SIDED rows there have ever returned it. A")
    print("same-game number from the ask-only population is not a measurement.")
    print("None of this is an edge -- no fair value is computed here and no")
    print("combo fee model has been verified for this venue.")
    print(f"{'=' * 78}\n")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pages", type=int, default=1,
        help="pages of 200 markets per series per round. One by default: only "
             "the newest markets are ever quoted, and page 2 is already four "
             "minutes stale. /markets must never be walked blind.",
    )
    parser.add_argument(
        "--rounds", type=int, default=1,
        help="how many times to re-read the newest page. A quote lives about a "
             "minute, so the sample is accumulated over time, not over pages.",
    )
    parser.add_argument(
        "--interval", type=float, default=45.0,
        help="seconds between rounds.",
    )
    parser.add_argument(
        "--max-legs", type=int, default=3,
        help="refuse to fit one rho across more legs than this. Equicorrelation "
             "on fifteen legs averages pairs that are nothing like each other.",
    )
    parser.add_argument(
        "--json", type=Path, default=None,
        help="also write the measurements here, for a fixture or a re-read.",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    configure_logging(level=logging.DEBUG if args.verbose else logging.INFO)

    async with KalshiRestClient(KalshiConfig.load()) as api:
        result = await survey(
            api, pages=args.pages, rounds=args.rounds,
            interval_s=args.interval, max_legs=args.max_legs,
        )

    report(result)

    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "rounds": result.rounds,
                    "scanned": result.scanned,
                    "distinct": result.distinct,
                    "with_legs": result.with_legs,
                    "quoted": result.quoted,
                    "two_sided": result.two_sided,
                    "refused": dict(result.refused),
                    "leg_counts": dict(result.leg_counts),
                    "measurements": [
                        {
                            "ticker": m.combo.ticker,
                            "collection": m.combo.collection,
                            "scope": m.combo.scope,
                            "subtitle": m.combo.subtitle,
                            "legs": list(m.combo.legs),
                            "marginals": list(m.marginals),
                            "leg_quotes": [
                                {"bid": q.bid, "ask": q.ask}
                                for q in m.leg_quotes
                            ],
                            "independent_joint": m.independent_joint,
                            "joint_bid": m.combo.joint.bid,
                            "joint_mid": m.combo.joint.mid,
                            "joint_ask": m.combo.joint.ask,
                            "leg_count": len(m.combo.legs),
                            "rho_at_bid": m.rho_at_bid,
                            "rho_at_mid": m.rho_at_mid,
                            "rho_at_ask": m.rho_at_ask,
                            "note": m.note,
                        }
                        for m in result.measurements
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"wrote {args.json}")

    return 0 if result.measurements else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
