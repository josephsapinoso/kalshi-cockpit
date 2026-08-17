"""Price a real Kalshi `KXMLBKS` ladder from one strikeout distribution.

WHAT THIS IS FOR
----------------
`backend/model/strikeouts.py` claims that fourteen Kalshi markets on one start
are fourteen readings of a single distribution, and that pricing the
distribution therefore prices the whole ladder coherently. That claim is easy to
assert in a docstring and easy to believe from passing unit tests, because unit
tests supply their own parameters and their own rungs.

This runs it against the ladders Kalshi actually published -- **7 pitchers, 48
rungs, 4 games**, captured 2026-08-15 in
`tests/fixtures/events_mlb_props_nested.json` -- and prints the model beside the
price you would actually pay. It is the demonstration that slice 1 of the
pitcher-strikeout build is real rather than merely tested.

**Read the whole output, not the head of it.** The first write-up of this script
said "4 pitchers, 56 markets" because it was run through `head -60`, which cut
three pitchers off the bottom -- and the three it cut included the two *largest*
disagreements in the file. A truncated view of a sorted-by-name listing is not a
sample of anything.

Kalshi lists one ladder per **announced starter**, both sides of a game once
both are named (`NYYTOR` carries only one, at capture time). That is worth
knowing structurally: the venue is telling us who is starting, so the pitcher's
identity needs no external feed at all.

WHAT IT IS NOT
--------------
**It is not a measurement, and none of its numbers may be quoted.** The rate and
the workload are typed in at the top of this file as round league-ish numbers.
They are not this pitcher's, they are not anybody's, and they were not fitted to
anything. Every "gap" column below is therefore a gap between Kalshi and an
arbitrary constant.

That is deliberate and it is the point of the slice boundary: the arithmetic can
be shown to work before the question of where the parameters come from -- which
is licence-constrained (ADR 0035) and is slice 2 -- has been answered at all.

**No edge, no fee, no size.** The gap printed is `model - ask` in probability,
with no fee subtracted and no suppression rule applied. `TAKER_COEFFICIENT` puts
the break-even bar at 51.75%, so a gap under ~1.75 points is not an opportunity
even if the parameters were real. The column is there to show the model and the
market on one line, not to rank anything.

The first rule of this repo applies with full force to whatever you see here: a
large apparent edge is a bug until proven otherwise.

    .venv\\Scripts\\python.exe scripts/price_pitcher_k_ladder.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.core.prices import dollars_to_tenths, format_price  # noqa: E402
from backend.kalshi.props import parse_subtitle                  # noqa: E402
from backend.model.strikeouts import distribution                # noqa: E402
from backend.store.db import derive_yes_ask                      # noqa: E402

FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / (
    "events_mlb_props_nested.json"
)

# ---------------------------------------------------------------------------
# PLACEHOLDERS. Not measured, not fitted, not anybody's actual numbers.
#
# Round figures in the right neighbourhood for a major-league starter, chosen so
# the output exercises a realistic region. Slice 2 replaces them with per-pitcher
# values from the sources ADR 0035 permits; until then every number this script
# prints is a statement about these constants.
# ---------------------------------------------------------------------------
PLACEHOLDER_EXPECTED_BF = 23.0
PLACEHOLDER_SD_BF = 5.0
PLACEHOLDER_K_PER_BF = 0.23


def ladder_rows(fixture: Path) -> dict[str, list[dict]]:
    """`{pitcher: [rung, ...]}` from the captured events payload.

    A market whose subtitle will not parse, or which carries no `floor_strike`,
    is **dropped and counted** rather than guessed at -- `props.parse_subtitle`
    returns `None` on an unreadable subtitle and this honours it. A ladder
    silently missing a rung would still print as monotone.
    """
    payload = json.loads(fixture.read_text("utf-8"))
    by_pitcher: dict[str, list[dict]] = {}
    unreadable = 0

    for event in payload["events_by_series"]["KXMLBKS"]:
        for market in event.get("markets", []):
            parsed = parse_subtitle(market.get("yes_sub_title"))
            strike = market.get("floor_strike")
            no_bid = dollars_to_tenths(market.get("no_bid_dollars"))
            if parsed is None or strike is None:
                unreadable += 1
                continue
            player, threshold = parsed
            by_pitcher.setdefault(player, []).append(
                {
                    "threshold": threshold,
                    "floor_strike": float(strike),
                    # The derived ask, never the mid and never `yes_ask_dollars`.
                    # `db.ask_for_side` is the identity every money path in this
                    # repo uses and this script must not invent a second one.
                    "ask_tenths": derive_yes_ask(no_bid),
                }
            )

    if unreadable:
        print(f"note: {unreadable} markets dropped as unreadable", file=sys.stderr)
    for rungs in by_pitcher.values():
        rungs.sort(key=lambda r: r["floor_strike"])
    return by_pitcher


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-bf", type=float, default=PLACEHOLDER_EXPECTED_BF)
    parser.add_argument("--sd-bf", type=float, default=PLACEHOLDER_SD_BF)
    parser.add_argument("--k-per-bf", type=float, default=PLACEHOLDER_K_PER_BF)
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    args = parser.parse_args()

    dist = distribution(args.expected_bf, args.sd_bf, args.k_per_bf)
    if dist is None:
        print(
            f"refused: ({args.expected_bf}, {args.sd_bf}, {args.k_per_bf}) does "
            f"not describe a start. No ladder priced.",
            file=sys.stderr,
        )
        return 1

    print(__doc__.split("WHAT IT IS NOT")[0].strip())
    print()
    print("=" * 72)
    print("PLACEHOLDER PARAMETERS -- NOT A MEASUREMENT, NOT ANY REAL PITCHER")
    print(
        f"  expected_bf {args.expected_bf}   sd_bf {args.sd_bf}   "
        f"k_per_bf {args.k_per_bf}   ->  E[K] = {dist.mean:.2f}"
    )
    print("=" * 72)

    for pitcher, rungs in sorted(ladder_rows(args.fixture).items()):
        print(f"\n{pitcher}   ({len(rungs)} rungs)")
        print(f"  {'rung':>6}  {'model':>7}  {'ask':>7}  {'model-ask':>10}")
        previous = 1.0
        for rung in rungs:
            model = dist.probability_over(rung["floor_strike"])
            ask = rung["ask_tenths"]
            # The monotonicity claim, checked against this ladder rather than
            # assumed from the unit tests -- a ladder is where it would break.
            assert model <= previous + 1e-12, (
                f"{pitcher} {rung['threshold']}+ priced above the rung below it"
            )
            previous = model
            if ask is None:
                print(f"  {rung['threshold']:>5}+  {model:>7.3f}  {'--':>7}  "
                      f"{'no bid':>10}")
                continue
            gap = model - ask / 1000.0
            print(
                f"  {rung['threshold']:>5}+  {model:>7.3f}  "
                f"{format_price(ask):>7}  {gap:>+10.3f}"
            )

    print(
        "\nEvery gap above is against a constant somebody typed in. It is not "
        "an edge,\nit is not fee-adjusted, and it must not be quoted. Slice 2 "
        "supplies real parameters."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
