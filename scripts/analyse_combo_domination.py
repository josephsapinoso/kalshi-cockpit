"""Is a Kalshi combination priced above the cost of its own cheapest leg?

    .venv\\Scripts\\python.exe scripts\\analyse_combo_domination.py ^
        docs\\measurements\\2026-08-09-combo-domination.json

Reads a `--json` capture from `measure_combo_correlation.py`. Spends nothing and
touches no API: the harvest is the expensive part, and iterating on the analysis
must not cost another fifty-five minutes of polling.

The question, and why it needs no correlation
---------------------------------------------
A combination pays out only when **every** leg hits. That is a strict subset of
the cases where the cheapest leg alone hits. So if

    combination ask  >  cost of buying the cheapest leg on its own side

the combination is **dominated**: it costs more and pays in fewer states of the
world. No dependence structure, no rho, no fair value -- it is arithmetic on two
quotes from one venue.

That matters because it is a different kind of claim from everything else in
this project. The rest of the tool asks whether Kalshi is mispriced *relative to
sportsbook consensus*, which requires an information edge over the consensus.
This asks whether Kalshi's combination book is inconsistent *with itself*.

`docs/adr/0012` left same-game correlation unmeasured: 18 same-game
combinations appeared, none two-sided, and 17 of 18 had an ask outside the
Frechet bounds. That refusal gradient (cross-game 23%, mixed 47%, same-game 94%)
is suggestive of strong positive dependence -- but a stale leg quote produces an
identical symptom, so nothing could be claimed.

The cost is read with `cost_to_buy_leg` imported from the harvest, not
reimplemented. Buying the NO side costs `1 - yes_bid`, not `1 - yes_ask`; using
the ask understates the cost by the whole spread and would manufacture
domination out of nothing. One path, so this and its tests cannot disagree.

The controls, and they decide whether anything can be claimed
-------------------------------------------------------------
**Cross-game is the control.** Legs from different games are near-independent,
so their joint sits near the *product* of the marginals -- far below
`min(marginal)`, and further still below the cheapest leg's ask. Cross-game
domination should therefore be rare. **If cross-game matches same-game, the
signal is staleness and the finding is refused.** This is the same structure
that made ADR 0012's correlation control usable.

**Age is the second control.** A stale-quote artefact must grow with the
combination's age: the longer since it was minted, the more its legs have moved.
A real pricing property is flat in age. Reported as a bucketed table rather than
a single rate, because the shape is the evidence.

**The observation gap is the third.** `observed_ms` records when each quote was
read. A combination whose legs were read at a different moment than its joint is
not evidence about either. Reported, and filterable.

What this does not establish
----------------------------
- **Not an edge, and not tradeable.** These markets are `is_provisional` and
  mostly carry zero volume and zero open interest -- a two-sided quote on an
  untraded market is a quoter's opinion, not a transaction. Nothing here shows
  size is available at the quoted ask.
- **No combo fee model has been verified for this venue.** A domination margin
  smaller than the round-trip fee on two positions is not an opportunity, and
  this script deliberately does not net a fee it cannot source.
- **Nothing about execution.** Buying the leg instead of the combination is only
  better if the leg's ask is real at size.
- **One slate, August**, MLB and NFL preseason live, NBA/NHL/NCAAF out of
  season. Same-game combinations here are whatever Kalshi's users happened to
  build.
- **A missing field is never zero.** A capture without `created_ms` or
  `observed_ms` (anything harvested before 2026-08-09) is reported as
  `unknown`, never bucketed at age 0 -- that substitution is exactly how a
  staleness confound would be hidden.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_harvest():
    """Import the harvest module for `cost_to_buy_leg` and `Quote`.

    By path, because `scripts/` is not a package and a second copy of the
    NO-side rule is the one thing this analysis must not have.
    """
    spec = importlib.util.spec_from_file_location(
        "measure_combo_correlation_for_analysis",
        ROOT / "scripts" / "measure_combo_correlation.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mcc = _load_harvest()

# Minutes. A combination minted longer ago than this has had more time for its
# legs to move; the buckets exist to show whether domination tracks that.
AGE_BUCKETS_MIN = (1, 2, 5, 10)

# Milliseconds. Joint and legs read further apart than this within a round are
# not a contemporaneous pair. One round is 60s in the recommended invocation, so
# this is generous by design -- it should catch a run-long cache, not jitter.
MAX_CONTEMPORANEOUS_GAP_MS = 90_000


@dataclass(frozen=True)
class Verdict:
    ticker: str
    scope: str
    joint_ask: float
    cheapest_leg_cost: float
    cheapest_leg_ticker: str
    age_ms: Optional[int]
    gap_ms: Optional[int]

    @property
    def margin(self) -> float:
        """How much more the combination costs than its cheapest leg.

        Positive means dominated. Reported as a distribution, never as a bare
        rate: a staleness artefact clusters just above zero, a real pricing
        property has a tail.
        """
        return self.joint_ask - self.cheapest_leg_cost

    @property
    def dominated(self) -> bool:
        return self.margin > 0.0


def verdict_for(record: dict) -> Optional[Verdict]:
    """One combination's verdict, or None when it cannot be judged.

    Refuses rather than substituting, at every step: a leg whose side has no
    price yields no verdict at all, because the cheapest leg is a *minimum* and
    a minimum over an incomplete set is not a minimum.
    """
    joint_ask = record.get("joint_ask")
    legs = record.get("legs") or []
    quotes = record.get("leg_quotes") or []
    if joint_ask is None or not legs or len(quotes) != len(legs):
        return None

    costs: list[tuple[float, str]] = []
    for leg, raw in zip(legs, quotes):
        ask = raw.get("ask")
        if ask is None:
            return None
        quote = mcc.Quote(
            ask=ask, bid=raw.get("bid"), observed_ms=raw.get("observed_ms")
        )
        cost = mcc.cost_to_buy_leg(leg, quote)
        if cost is None:
            return None
        costs.append((cost, leg.get("market_ticker", "?")))

    cheapest_cost, cheapest_ticker = min(costs, key=lambda c: c[0])

    # `is not None`, never truthiness. An epoch-zero stamp is a real value and
    # `if created` would file it as missing -- the falsy-zero trap this repo
    # has already hit on `DEFAULT_HORIZON_HOURS = 0.0` and on a market width of
    # 0.0 that meant "unmeasurable". Here it would silently move a timestamped
    # combination into the `unknown` bucket, which is the one place a staleness
    # artefact could hide from the control built to find it.
    created = record.get("created_ms")
    observed = record.get("joint_observed_ms")
    age = (
        observed - created
        if created is not None and observed is not None
        else None
    )

    leg_stamps = [q.get("observed_ms") for q in quotes]
    gap = (
        max(abs(observed - s) for s in leg_stamps)
        if observed is not None and all(s is not None for s in leg_stamps)
        else None
    )

    return Verdict(
        ticker=record.get("ticker", "?"),
        scope=record.get("scope", "?"),
        joint_ask=joint_ask,
        cheapest_leg_cost=cheapest_cost,
        cheapest_leg_ticker=cheapest_ticker,
        age_ms=age,
        gap_ms=gap,
    )


def _describe(label: str, values: Sequence[float]) -> str:
    """`n` first and always, including zero.

    A summary that appears only when there is something to say makes an empty
    population look like one nobody measured.
    """
    if not values:
        return f"  {label:<22} n=0"
    ordered = sorted(values)
    med = statistics.median(ordered)
    return (
        f"  {label:<22} n={len(values):<5} "
        f"min {ordered[0]:+.3f}  median {med:+.3f}  max {ordered[-1]:+.3f}"
    )


def report(verdicts: Sequence[Verdict], *, contemporaneous_only: bool) -> None:
    if contemporaneous_only:
        kept = [
            v for v in verdicts
            if v.gap_ms is not None and v.gap_ms <= MAX_CONTEMPORANEOUS_GAP_MS
        ]
        dropped = len(verdicts) - len(kept)
        print(
            f"Contemporaneous filter: kept {len(kept)} of {len(verdicts)}; "
            f"dropped {dropped} whose legs and joint were read more than "
            f"{MAX_CONTEMPORANEOUS_GAP_MS // 1000}s apart or carried no stamp."
        )
        if not kept:
            print(
                "  NOTHING SURVIVES. A capture with no observation stamps "
                "cannot answer this question -- the joint and its legs may have "
                "been read an hour apart. Re-harvest; do not reinterpret."
            )
            return
        verdicts = kept

    print()
    print("Domination rate by scope -- READ CROSS-GAME FIRST")
    print("  Cross-game legs are near-independent, so their joint sits near the")
    print("  product of the marginals, far below the cheapest leg's ask. A high")
    print("  cross-game rate means the method is measuring staleness, not")
    print("  pricing, and no same-game claim may be built on it.")
    print()
    print(f"  {'scope':<14} {'n':>5} {'dominated':>10} {'rate':>7}")
    for scope in ("cross_game", "mixed", "same_game", "undecodable"):
        group = [v for v in verdicts if v.scope == scope]
        if not group:
            print(f"  {scope:<14} {0:>5} {'-':>10} {'-':>7}")
            continue
        hits = [v for v in group if v.dominated]
        rate = 100.0 * len(hits) / len(group)
        print(
            f"  {scope:<14} {len(group):>5} {len(hits):>10} {rate:>6.1f}%"
        )

    print()
    print("Margin distribution (combination ask - cheapest leg cost)")
    print("  A staleness artefact clusters just above zero. A real pricing")
    print("  property has a tail.")
    for scope in ("cross_game", "mixed", "same_game"):
        group = [v.margin for v in verdicts if v.scope == scope]
        print(_describe(scope, group))

    print()
    print("Domination rate by combination age -- THE STALENESS CONTROL")
    print("  A stale-leg artefact must GROW with age. A real property is flat.")
    aged = [v for v in verdicts if v.age_ms is not None]
    unknown = len(verdicts) - len(aged)
    if not aged:
        print(
            f"  No combination carries an age ({unknown} unknown). This capture "
            f"predates `created_ms`; the control cannot run."
        )
    else:
        bounds = [b * 60_000 for b in AGE_BUCKETS_MIN]
        labels = [f"<{AGE_BUCKETS_MIN[0]}m"] + [
            f"{AGE_BUCKETS_MIN[i - 1]}-{AGE_BUCKETS_MIN[i]}m"
            for i in range(1, len(AGE_BUCKETS_MIN))
        ] + [f">{AGE_BUCKETS_MIN[-1]}m"]
        for i, label in enumerate(labels):
            lo = bounds[i - 1] if i else 0
            hi = bounds[i] if i < len(bounds) else None
            group = [
                v for v in aged
                if v.age_ms >= lo and (hi is None or v.age_ms < hi)
            ]
            if not group:
                print(f"  {label:<10} n=0")
                continue
            hits = sum(1 for v in group if v.dominated)
            print(
                f"  {label:<10} n={len(group):<5} dominated {hits:<5} "
                f"{100.0 * hits / len(group):>5.1f}%"
            )
        if unknown:
            print(f"  {'unknown':<10} n={unknown:<5} (no created_ms; NOT bucketed at 0)")

    print()
    dominated = [v for v in verdicts if v.dominated]
    same_game = [v for v in dominated if v.scope == "same_game"]
    print(f"Dominated same-game combinations: {len(same_game)}")
    for v in sorted(same_game, key=lambda x: -x.margin)[:10]:
        age = f"{v.age_ms / 60000:.1f}m" if v.age_ms is not None else "age?"
        print(
            f"  {v.ticker:<38} ask {v.joint_ask:.3f} vs leg "
            f"{v.cheapest_leg_cost:.3f} (+{v.margin:.3f}) {age}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument(
        "--all", action="store_true",
        help="skip the contemporaneous filter. Reports every combination, "
             "including those whose legs were read at a different moment than "
             "the joint -- which is not evidence about either.",
    )
    args = parser.parse_args()

    payload = json.loads(args.capture.read_text(encoding="utf-8"))
    records = payload.get("measurements") or []
    verdicts = [v for v in (verdict_for(r) for r in records) if v is not None]

    print(f"Capture: {args.capture.name}")
    print(
        f"  {payload.get('rounds', '?')} rounds, "
        f"{payload.get('distinct', '?')} distinct markets, "
        f"{len(records)} measured, {len(verdicts)} judgeable"
    )
    if len(verdicts) < len(records):
        print(
            f"  {len(records) - len(verdicts)} refused: a leg with no price on "
            f"the side taken yields no cheapest-leg minimum."
        )

    report(verdicts, contemporaneous_only=not args.all)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
