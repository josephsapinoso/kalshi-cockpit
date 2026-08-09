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

**The leg echo is what actually decides it, and it was found only after the
first result was believed.** 86% of dominated rows have an ask equal to one of
their own legs' costs to within 2c, against a 3-7% base rate -- and 119 of them
match a leg that is *not the cheapest*, which no dependence structure can
produce. For that subset the quote at the combination's ticker is evidently not
a joint over `mve_selected_legs`. Excluding echoes, the 2026-08-09 capture reads
**cross-game 1.9%, same-game 3.3%** rather than 11.1% and 18.3%, on 19 games.
The echo block prints first for that reason.

**Age is NOT a working control here, despite being reported.** Only *quoted*
markets are visible and a combo quote lives 1-2 minutes, so no combination older
than that is ever sampled: observed ages run 9s to 71s. The staleness confound
this was built to test lives at **39 minutes**. Empty buckets are structural
absence, not flatness. The table stays because deleting it would hide that the
control cannot run.

**The observation gap is reported and was, in the first version, a tautology.**
One `round_ms` was stamped on the joint and on every leg, so the gap was
identically zero for all 2,116 rows and the filter printed "dropped 0" as though
it were evidence. Quotes are now stamped at their own read time. Any capture
written before that fix shows a gap of exactly 0 everywhere and its
contemporaneity is unverified, not confirmed.

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


# A combination whose ask sits this close to one of its own legs' costs is
# treated as an **echo** rather than a joint price.
#
# Measured 2026-08-09 on the first capture: 85% of dominated cross-game rows and
# 86% of dominated same-game rows matched a leg to within 2c, against base rates
# of 3.2% and 7.5% among non-dominated rows. At 0.5c it is still 77% and 68%.
# Decisive detail: **81 of 198 cross-game echo rows matched a leg that was not
# the cheapest one.** A joint above `min(marginal)` is impossible under any
# dependence structure, so those rows are not mispriced joints -- for that
# subset the quote at the combination's ticker is not a joint over
# `mve_selected_legs` at all.
#
# Until that is resolved, an echo row is evidence about Kalshi's minting, not
# about dependence, and no domination or Frechet claim may be built on it.
ECHO_TOLERANCE = 0.02


@dataclass(frozen=True)
class Verdict:
    ticker: str
    scope: str
    joint_ask: float
    cheapest_leg_cost: float
    cheapest_leg_ticker: str
    leg_costs: tuple[float, ...]
    age_ms: Optional[int]
    gap_ms: Optional[int]

    @property
    def echoes_a_leg(self) -> bool:
        return any(
            abs(self.joint_ask - c) <= ECHO_TOLERANCE for c in self.leg_costs
        )

    @property
    def echoes_a_dearer_leg(self) -> bool:
        """Matches a leg that is not the cheapest — unexplainable by dependence."""
        hits = [
            c for c in self.leg_costs
            if abs(self.joint_ask - c) <= ECHO_TOLERANCE
        ]
        return bool(hits) and min(hits) > self.cheapest_leg_cost + 1e-9

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
        leg_costs=tuple(c for c, _ in costs),
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

    # ---- The echo, first, because it decides whether the rest means anything.
    echoes = [v for v in verdicts if v.echoes_a_leg]
    dominated_all = [v for v in verdicts if v.dominated]
    dom_echo = [v for v in dominated_all if v.echoes_a_leg]
    print()
    print("LEG ECHO -- READ THIS BEFORE ANY RATE BELOW")
    print("  A combination whose ask equals one of its own legs' costs to "
          f"within {ECHO_TOLERANCE * 100:.0f}c is not")
    print("  evidence about dependence. For that subset the quote at the")
    print("  combination's ticker appears not to be a joint at all.")
    print(
        f"  echo rows: {len(echoes)} of {len(verdicts)} "
        f"({100.0 * len(echoes) / max(1, len(verdicts)):.1f}%)"
    )
    print(
        f"  of DOMINATED rows: {len(dom_echo)} of {len(dominated_all)} "
        f"({100.0 * len(dom_echo) / max(1, len(dominated_all)):.0f}%)"
    )
    dearer = [v for v in echoes if v.echoes_a_dearer_leg]
    print(
        f"  matching a NON-cheapest leg: {len(dearer)} -- impossible under any "
        f"dependence structure"
    )
    clean = [v for v in verdicts if not v.echoes_a_leg]
    print(f"  remaining after excluding echoes: {len(clean)}")
    print()
    print("Domination rate by scope -- READ CROSS-GAME FIRST")
    print("  Cross-game legs are near-independent, so their joint sits near the")
    print("  product of the marginals, far below the cheapest leg's ask. A high")
    print("  cross-game rate means the method is measuring staleness, not")
    print("  pricing, and no same-game claim may be built on it.")
    print()
    print(f"  {'scope':<14} {'n':>5} {'dom':>5} {'rate':>7}   "
          f"{'n':>5} {'dom':>5} {'rate':>7}  (excluding echoes)")
    for scope in ("cross_game", "mixed", "same_game", "undecodable"):
        group = [v for v in verdicts if v.scope == scope]
        sub = [v for v in clean if v.scope == scope]
        if not group:
            print(f"  {scope:<14} {0:>5}")
            continue
        hits = [v for v in group if v.dominated]
        shits = [v for v in sub if v.dominated]
        print(
            f"  {scope:<14} {len(group):>5} {len(hits):>5} "
            f"{100.0 * len(hits) / len(group):>6.1f}%   "
            f"{len(sub):>5} {len(shits):>5} "
            f"{(100.0 * len(shits) / len(sub)) if sub else 0:>6.1f}%"
        )
    print("  The right-hand block is the one to read. `n` per scope is rows,")
    print("  NOT independent events -- combinations share legs and games, so a")
    print("  proportion's standard error over these is understated.")

    print()
    print("Margin distribution (combination ask - cheapest leg cost)")
    print("  A staleness artefact clusters just above zero. A real pricing")
    print("  property has a tail.")
    for scope in ("cross_game", "mixed", "same_game"):
        group = [v.margin for v in verdicts if v.scope == scope]
        print(_describe(scope, group))

    print()
    print("Domination rate by combination age -- UNDERPOWERED, READ THE CAVEAT")
    print("  A stale-leg artefact must GROW with age, and a real property is")
    print("  flat -- but this capture cannot test that. Only QUOTED markets are")
    print("  visible and a combo quote lives ~1-2 min, so nothing older is ever")
    print("  sampled. The confound the ticket names lives at 39 MINUTES. Empty")
    print("  buckets below are structural absence, not evidence of flatness.")
    # Negative ages are surfaced, never dropped. The first version bucketed on
    # `age_ms >= lo` with `lo = 0`, so 69 of 2,116 rows fell through every
    # bucket and vanished from the table built to catch confounds -- the same
    # silent-drop failure the table exists to prevent, inside the table.
    negative = [v for v in verdicts if v.age_ms is not None and v.age_ms < 0]
    aged = [v for v in verdicts if v.age_ms is not None and v.age_ms >= 0]
    unknown = len([v for v in verdicts if v.age_ms is None])
    if negative:
        print(
            f"  WARNING: {len(negative)} rows have a NEGATIVE age (min "
            f"{min(v.age_ms for v in negative) / 1000:.1f}s) -- the combination "
            f"was minted after the stamp that claims to have observed it. The "
            f"stamp is wrong, so every age below is suspect."
        )
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
