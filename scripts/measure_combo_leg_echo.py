"""Does a KXMVE combination's ask MOVE with the leg it echoes? Read-only.

    .venv\\Scripts\\python.exe scripts\\measure_combo_leg_echo.py \\
        --rounds 12 --interval 15 --json docs/measurements/...json

Free and **unauthenticated**. `/markets` is a public endpoint (verified
2026-08-09: 200 with no signature), so this never touches the private key --
the cheapest way to honour the security rule is to have no credential in the
process at all. No Odds API credit is spent; nothing is ordered; nothing is
created.

The question
------------
`docs/adr/0012`'s addendum records a **leg echo**: a combination's
`yes_ask_dollars` frequently equals one of its own legs' cost-to-buy to within
2c (85-86% of dominated rows, against a 3-7% base rate), and **119 rows matched
a leg that was not the cheapest** -- a joint above `min(marginal)`, which no
dependence structure produces. For that subset the quote at the combination's
ticker is not a joint over `mve_selected_legs`.

That leaves exactly one binary question, and this harness exists to answer it:

    Is the echo a LIVE COUPLING -- the combination's ask is (re)derived from
    that leg continuously, so it moves tick-for-tick with it --
    or a TRANSIENT MINT-TIME STATE -- the ask was stamped from a leg when
    Kalshi minted the market and then sat still while the leg moved on?

If live, MVE-as-correlation needs a different data source: the number at the
combination's ticker is a leg price wearing a combination's name, and no
filter recovers a joint from it. If transient, the echo is excludable by a
rule -- and the rule is fixed in advance below, not chosen after the data.

The protocol is pre-registered
------------------------------
Every threshold below was committed to git **before** the run. See
`docs/measurements/2026-08-09-combo-leg-echo.md`.

- *matched leg*: at the poll where the pair is discovered, the leg minimising
  `|combo_ask - cost_to_buy_leg(L)|` among legs within `ECHO_TOLERANCE`.
- *cost_to_buy_leg* is imported from `measure_combo_correlation`, not
  re-implemented: yes -> `yes_ask`, no -> `1 - yes_bid`. A test or a second
  copy of that rule could disagree with the original; an import cannot.
- *move event*: a consecutive poll pair where the matched leg's cost changed by
  >= `MOVE_TENTHS` and BOTH combo asks are readable.
- *tracking*: `|d_combo - d_leg| <= TRACK_TOL`.
- *frozen*: `|d_combo| < MOVE_TENTHS` while the leg moved.

`n` is the number of MOVE EVENTS, not the number of pairs and not the number of
polls. A pair whose leg never moves cannot distinguish the two hypotheses; it
contributes nothing and is counted separately, because a sample that cannot
discriminate must not be reported as a sample that did.

The asymmetry is deliberate and is stated so it cannot be read backwards: a
combo ask that never changes is the RESULT under the transient hypothesis, so
"one distinct combo ask" is a finding. A matched-leg cost that never changes is
a DEFECT of the window, so "one distinct leg cost" is not a finding -- it is
the tell that no guard could have fired, and it forces "too thin to answer".

What this does not establish
----------------------------
- **Nothing about why.** Whether the echoed number is a book quote, a
  seeded ask, or an artefact of provisional minting is not observable here.
- **Nothing about non-echo combinations.** Only echo pairs are tracked, so
  this says nothing about whether a non-echoing combination's ask is a joint.
- **One series, one slate, minutes long.** In-season sports on the day, in a
  window of a few minutes. A leg that moves on a different timescale than the
  window would look frozen for reasons that have nothing to do with the combo.
- **Not an edge.** No fair value is computed and no combo fee model is
  verified for this venue.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts"))

import httpx  # noqa: E402

from backend.kalshi.discovery import parse_ms  # noqa: E402
from backend.logging_setup import configure_logging  # noqa: E402
from measure_combo_correlation import (  # noqa: E402
    Quote,
    cost_to_buy_leg,
    dollars,
    fixture_of,
    readable_quote,
)

# Same constant, same meaning, as `analyse_combo_domination.ECHO_TOLERANCE`.
ECHO_TOLERANCE = 0.02

# Half a cent. Below this a "move" is not distinguishable from tick noise on a
# deci-cent market, and the smallest real tick on this venue is 0.001.
MOVE_TENTHS = 0.005
TRACK_TOL = 0.005

# Fraction of move events one verdict must claim before it is allowed to speak.
VERDICT_SHARE = 0.80
# Below these the answer is "too thin", whatever the shares look like.
MIN_MOVE_EVENTS = 5
MIN_PAIRS = 3

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"

# The two MVE series carrying any open market on this slate. The other six in
# `measure_combo_correlation.MVE_SERIES` returned zero rows when checked, which
# is a fact about the calendar; they are left out only because an empty page
# costs a request.
DISCOVERY_SERIES = ("KXMVESPORTSMULTIGAMEEXTENDED", "KXMVECROSSCATEGORY")

# **Not 200.** `/markets` is newest-first and Kalshi mints ~1,900 combinations a
# minute in one of these series, so 200 rows span about **seventeen seconds** of
# minting -- while a combination stays quoted for one to two minutes. A 200-row
# page therefore misses most of the quoted population, and it showed: 200 rows
# yielded 9 quoted combinations and 0 echo pairs, where 1,000 rows across the
# two series yielded 104 quoted and **7 echo pairs** for two extra requests.
#
# This is not paging. Page 2 would be older than any live quote; the whole
# window is still the newest slice of one page, just a slice wide enough to
# contain the thing being measured.
PAGE_LIMIT = 1000

# Cap on how many tickers go into one batched read, so a URL cannot silently
# truncate. Kalshi accepts `tickers=a,b,c` on `/markets` (verified 2026-08-09,
# combinations included), and 200 per request was verified to round-trip whole.
MAX_BATCH = 200

logger = logging.getLogger("measure_combo_leg_echo")


@dataclass
class Sample:
    round_index: int
    observed_ms: int
    combo_ask: Optional[float]
    combo_bid: Optional[float]
    combo_status: str
    leg_ask: Optional[float]
    leg_bid: Optional[float]
    leg_cost: Optional[float]
    leg_status: str


@dataclass
class Pair:
    combo_ticker: str
    collection: str
    scope: str
    created_ms: Optional[int]
    legs: tuple[dict, ...]
    matched_leg_ticker: str
    matched_leg_side: str
    matched_is_cheapest: bool
    initial_gap: float
    discovered_round: int
    samples: list[Sample] = field(default_factory=list)


def scope_of(legs: tuple[dict, ...]) -> str:
    """Same rule as `measure_combo_correlation.Combo.scope`."""
    seen = [fixture_of(leg.get("market_ticker") or "") for leg in legs]
    if any(f is None for f in seen):
        return "undecodable"
    distinct = set(seen)
    if len(distinct) == 1:
        return "same_game"
    if len(distinct) == len(seen):
        return "cross_game"
    return "mixed"


class PublicReader:
    """One shared client, one rate limit, no credentials.

    `httpx.AsyncClient` construction costs ~500ms of SSL setup, which is why
    this repo forbids one per call.
    """

    def __init__(self, client: httpx.AsyncClient, *, min_interval_s: float = 0.15):
        self._client = client
        self._min_interval = min_interval_s
        self._last = 0.0
        self.calls = 0

    async def get(self, path: str, **params: Any) -> dict:
        wait = self._last + self._min_interval - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        self._last = time.monotonic()
        self.calls += 1
        response = await self._client.get(
            f"{BASE_URL}{path}",
            params={k: v for k, v in params.items() if v is not None},
        )
        response.raise_for_status()
        return response.json()

    async def markets_page(self, series: str, *, limit: int = PAGE_LIMIT) -> list[dict]:
        payload = await self.get(
            "/markets", series_ticker=series, status="open", limit=limit
        )
        if "markets" not in payload:
            raise RuntimeError(
                f"/markets has no 'markets' key (got {sorted(payload)}); "
                "refusing to return an empty page that reads as 'no results'"
            )
        return payload["markets"] or []

    async def by_ticker(self, tickers: list[str]) -> dict[str, dict]:
        """Batched read. Missing tickers are simply absent -- never faked."""
        out: dict[str, dict] = {}
        for start in range(0, len(tickers), MAX_BATCH):
            chunk = tickers[start : start + MAX_BATCH]
            payload = await self.get(
                "/markets", tickers=",".join(chunk), limit=len(chunk)
            )
            if "markets" not in payload:
                raise RuntimeError("/markets batch has no 'markets' key")
            for market in payload["markets"] or []:
                out[market.get("ticker") or ""] = market
        return out


def leg_cost_from(market: Optional[dict], side: str) -> Optional[float]:
    """Cost to buy this leg on `side`, or None. Never a substituted number."""
    if not market:
        return None
    quote = readable_quote(market)
    if quote is None:
        return None
    return cost_to_buy_leg({"side": side, "market_ticker": ""}, quote)


def sample_for(
    pair: Pair, round_index: int, now_ms: int, rows: dict[str, dict]
) -> Sample:
    combo = rows.get(pair.combo_ticker)
    leg = rows.get(pair.matched_leg_ticker)
    combo_quote: Optional[Quote] = readable_quote(combo) if combo else None
    return Sample(
        round_index=round_index,
        observed_ms=now_ms,
        combo_ask=combo_quote.ask if combo_quote else None,
        combo_bid=combo_quote.bid if combo_quote else None,
        combo_status=str((combo or {}).get("status") or "absent"),
        leg_ask=dollars((leg or {}).get("yes_ask_dollars")),
        leg_bid=dollars((leg or {}).get("yes_bid_dollars")),
        leg_cost=leg_cost_from(leg, pair.matched_leg_side),
        leg_status=str((leg or {}).get("status") or "absent"),
    )


def discover(
    markets: list[dict], leg_rows: dict[str, dict], known: set[str], round_index: int
) -> list[Pair]:
    """New echo pairs on this page. One per combination, the closest match."""
    found: list[Pair] = []
    for market in markets:
        ticker = market.get("ticker") or ""
        if not ticker or ticker in known:
            continue
        legs = tuple(market.get("mve_selected_legs") or [])
        if not legs:
            continue
        combo_quote = readable_quote(market)
        if combo_quote is None:
            continue

        costs: list[tuple[float, dict]] = []
        for leg in legs:
            cost = leg_cost_from(
                leg_rows.get(leg.get("market_ticker") or ""),
                str(leg.get("side") or "yes"),
            )
            if cost is not None:
                costs.append((cost, leg))
        if len(costs) != len(legs):
            # A leg we cannot price makes "the cheapest leg" a minimum over an
            # incomplete set. Refuse the row rather than rank a partial set.
            continue

        hits = [
            (abs(combo_quote.ask - cost), cost, leg)
            for cost, leg in costs
            if abs(combo_quote.ask - cost) <= ECHO_TOLERANCE
        ]
        if not hits:
            continue
        gap, cost, leg = min(hits, key=lambda h: h[0])
        cheapest = min(c for c, _ in costs)
        found.append(
            Pair(
                combo_ticker=ticker,
                collection=str(market.get("mve_collection_ticker") or ""),
                scope=scope_of(legs),
                created_ms=parse_ms(market.get("created_time")),
                legs=legs,
                matched_leg_ticker=str(leg.get("market_ticker") or ""),
                matched_leg_side=str(leg.get("side") or "yes"),
                matched_is_cheapest=cost <= cheapest + 1e-9,
                initial_gap=gap,
                discovered_round=round_index,
            )
        )
    return found


async def run(
    reader: PublicReader,
    *,
    rounds: int,
    discovery_rounds: int,
    interval_s: float,
    max_pairs: int,
    discover_every: int = 0,
    retire_after: int = 0,
) -> list[Pair]:
    pairs: list[Pair] = []
    known: set[str] = set()

    def retired(pair: Pair) -> bool:
        """Stop polling a pair whose combination has stopped being quoted.

        A move event requires BOTH combo asks readable, so retiring a pair
        after `retire_after` consecutive unreadable asks can neither create nor
        destroy one. It only keeps dead tickers out of the batch. Zero disables
        it.
        """
        if retire_after <= 0 or len(pair.samples) < retire_after:
            return False
        return all(
            s.combo_ask is None for s in pair.samples[-retire_after:]
        )

    for round_index in range(rounds):
        if round_index:
            await asyncio.sleep(interval_s)

        # Discovery runs in the first rounds, and then -- if `discover_every`
        # is set -- periodically, because a combination stops being quoted long
        # before the run ends and a window with no live pair in it measures
        # nothing. Observation continues for every tracked pair regardless.
        discovering = len(pairs) < max_pairs and (
            round_index < discovery_rounds
            or (discover_every > 0 and round_index % discover_every == 0)
        )

        page: list[dict] = []
        if discovering:
            for series in DISCOVERY_SERIES:
                page.extend(await reader.markets_page(series))

        # One batched read carrying every tracked ticker AND, while
        # discovering, every leg of every quoted combination on the page. One
        # request set, one moment, so a combination and its leg are read
        # together rather than argued to be contemporaneous.
        live = [p for p in pairs if not retired(p)]
        wanted: list[str] = []
        for pair in live:
            wanted.extend([pair.combo_ticker, pair.matched_leg_ticker])
        if discovering:
            for market in page:
                if (market.get("ticker") or "") in known:
                    continue
                if readable_quote(market) is None:
                    continue
                for leg in market.get("mve_selected_legs") or []:
                    wanted.append(str(leg.get("market_ticker") or ""))
        wanted = [t for t in dict.fromkeys(wanted) if t]
        rows = await reader.by_ticker(wanted) if wanted else {}

        now_ms = int(time.time() * 1000)

        # The page row is the freshest read of a combination still on page 1;
        # prefer it, and fall back to the batched row for one that has aged off.
        for market in page:
            rows.setdefault(market.get("ticker") or "", market)

        for pair in live:
            pair.samples.append(sample_for(pair, round_index, now_ms, rows))

        if discovering:
            for pair in discover(page, rows, known, round_index):
                if len(pairs) >= max_pairs:
                    break
                pairs.append(pair)
                known.add(pair.combo_ticker)
                pair.samples.append(sample_for(pair, round_index, now_ms, rows))

        logger.info(
            "round %d/%d%s: %d tracked (%d live), %d API calls so far",
            round_index + 1, rounds, " (discovering)" if discovering else "",
            len(pairs), len([p for p in pairs if not retired(p)]), reader.calls,
        )

    return pairs


# -- analysis -------------------------------------------------------------


@dataclass
class MoveEvent:
    combo_ticker: str
    round_index: int
    d_leg: float
    d_combo: float

    @property
    def verdict(self) -> str:
        if abs(self.d_combo - self.d_leg) <= TRACK_TOL:
            return "tracks"
        if abs(self.d_combo) < MOVE_TENTHS:
            return "frozen"
        return "other"


def move_events(pair: Pair) -> list[MoveEvent]:
    events: list[MoveEvent] = []
    for prev, cur in zip(pair.samples, pair.samples[1:]):
        if prev.leg_cost is None or cur.leg_cost is None:
            continue
        if prev.combo_ask is None or cur.combo_ask is None:
            continue
        d_leg = cur.leg_cost - prev.leg_cost
        if abs(d_leg) < MOVE_TENTHS:
            continue
        events.append(
            MoveEvent(
                combo_ticker=pair.combo_ticker,
                round_index=cur.round_index,
                d_leg=d_leg,
                d_combo=cur.combo_ask - prev.combo_ask,
            )
        )
    return events


def verdict(pairs: list[Pair]) -> tuple[str, dict]:
    """Apply the pre-registered rule. Nothing here is chosen after the data."""
    events = [e for p in pairs for e in move_events(p)]
    contributing = {e.combo_ticker for e in events}
    counts = {"tracks": 0, "frozen": 0, "other": 0}
    for event in events:
        counts[event.verdict] += 1
    n = len(events)
    stats = {
        "pairs_tracked": len(pairs),
        "pairs_contributing_move_events": len(contributing),
        "move_events": n,
        "tracks": counts["tracks"],
        "frozen": counts["frozen"],
        "other": counts["other"],
    }
    if n < MIN_MOVE_EVENTS or len(contributing) < MIN_PAIRS:
        return "TOO THIN TO ANSWER", stats
    if counts["tracks"] / n >= VERDICT_SHARE:
        return "LIVE COUPLING", stats
    if counts["frozen"] / n >= VERDICT_SHARE:
        return "TRANSIENT MINT-TIME STATE", stats
    return "TOO THIN TO ANSWER", stats


def report(pairs: list[Pair], calls: int) -> None:
    print(f"\n{'=' * 78}")
    print("Does a combination's ask move with the leg it echoes?")
    print(f"{'=' * 78}")
    print(f"  Kalshi API calls (free, unauthenticated)  {calls:>5}")
    print(f"  echo pairs tracked                        {len(pairs):>5}")

    print("\n  per pair -- polls / distinct combo asks / distinct leg costs /"
          " move events")
    for pair in pairs:
        asks = {s.combo_ask for s in pair.samples if s.combo_ask is not None}
        costs = {s.leg_cost for s in pair.samples if s.leg_cost is not None}
        events = move_events(pair)
        breakdown = ", ".join(
            f"{e.verdict} dleg{e.d_leg:+.4f} dcombo{e.d_combo:+.4f}"
            for e in events
        )
        print(
            f"    {pair.combo_ticker[-28:]:<28} {pair.scope:<11} "
            f"polls {len(pair.samples):>2}  asks {len(asks):>2}  "
            f"legcosts {len(costs):>2}  moves {len(events):>2}"
            + (f"  [{breakdown}]" if breakdown else "")
        )

    answer, stats = verdict(pairs)
    print("\n  n is MOVE EVENTS, not pairs and not polls. A pair whose matched")
    print("  leg never moved cannot discriminate the two hypotheses.")
    for key, value in stats.items():
        print(f"    {key:<34} {value:>5}")
    print(f"\n  VERDICT (pre-registered rule): {answer}")
    print(f"{'=' * 78}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, default=12)
    parser.add_argument("--discovery-rounds", type=int, default=4)
    parser.add_argument("--discover-every", type=int, default=0)
    parser.add_argument("--retire-after", type=int, default=0)
    parser.add_argument("--interval", type=float, default=20.0)
    parser.add_argument("--max-pairs", type=int, default=12)
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    configure_logging(level=logging.DEBUG if args.verbose else logging.INFO)

    async def go() -> tuple[list[Pair], int]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            reader = PublicReader(client)
            pairs = await run(
                reader,
                rounds=args.rounds,
                discovery_rounds=args.discovery_rounds,
                interval_s=args.interval,
                max_pairs=args.max_pairs,
                discover_every=args.discover_every,
                retire_after=args.retire_after,
            )
            return pairs, reader.calls

    pairs, calls = asyncio.run(go())
    report(pairs, calls)

    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "api_calls": calls,
                    "echo_tolerance": ECHO_TOLERANCE,
                    "move_tenths": MOVE_TENTHS,
                    "track_tol": TRACK_TOL,
                    "pairs": [
                        {
                            "combo_ticker": p.combo_ticker,
                            "collection": p.collection,
                            "scope": p.scope,
                            "created_ms": p.created_ms,
                            "legs": list(p.legs),
                            "matched_leg_ticker": p.matched_leg_ticker,
                            "matched_leg_side": p.matched_leg_side,
                            "matched_is_cheapest": p.matched_is_cheapest,
                            "initial_gap": p.initial_gap,
                            "discovered_round": p.discovered_round,
                            "samples": [vars(s) for s in p.samples],
                        }
                        for p in pairs
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"wrote {args.json}")

    return 0 if pairs else 1


if __name__ == "__main__":
    raise SystemExit(main())
