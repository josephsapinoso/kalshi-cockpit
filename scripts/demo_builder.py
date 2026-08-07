"""Demonstrate the Builder: parlays, correlation refusal, and Wong teasers.

Run:  python -m scripts.demo_builder

Deterministic and offline. Nothing here touches Kalshi or The Odds API -- the
point is to show what the pricing says, including the cases where it refuses to
say anything.
"""

from __future__ import annotations

import random

from backend.core.correlation import CorrelationRefused, Leg, independence_error
from backend.core.parlay import (
    ParlayQuote,
    american_to_decimal,
    decimal_to_american,
    kalshi_equivalent,
    value_parlay,
)
from backend.core.teaser import (
    STANDARD_TWO_TEAM_DECIMAL,
    TeaserUnpriceable,
    build_leg,
    find_wong_candidates,
    value_teaser,
)
from backend.model.margins import (
    MarginDistribution,
    default_distribution,
    fit_by_spread,
    spread_bucket_for,
)
from backend.model.synthetic import (
    synthetic_bucket_observations,
    synthetic_margins,
)

DAY = 86_400_000
NOW = 1_754_800_000_000
NFL = "americanfootball_nfl"


def rule(title: str) -> None:
    print(f"\n{'=' * 76}\n{title}\n{'=' * 76}")


def leg(label, p, event, offset=0, league=NFL):
    return Leg(
        label=label, probability=p, event_key=event, league=league,
        commence_ms=NOW + offset,
    )


# ---------------------------------------------------------------------------


def demo_parlay() -> None:
    rule("1. A three-leg parlay at a sportsbook")

    legs = (
        leg("Chiefs ML", 0.50, "E1"),
        leg("Ravens ML", 0.50, "E2", offset=8 * DAY),
        leg("Eagles ML", 0.53, "E3", offset=16 * DAY),
    )
    for l in legs:
        print(f"  {l.label:<12} devigged {l.probability:.3f}")

    offered = +550
    valuation = value_parlay(
        ParlayQuote(legs=legs, offered_decimal=american_to_decimal(offered))
    )

    print(f"\n  Fair probability     {valuation.fair_probability:.4f}")
    print(f"  Fair price           {decimal_to_american(valuation.fair_decimal):+d}")
    print(f"  Book offers          {offered:+d}")
    print(f"  Book's hold          {valuation.hold:.1%}")
    print(f"  EV per dollar        {valuation.ev_per_dollar:+.1%}")
    print(f"\n  > {valuation.verdict}")

    print("\n  The straight lines these came from hold 4-5% each. The parlay is")
    print("  where the book makes that back, and the hold is the number worth")
    print("  remembering -- it generalises to every ticket of this shape.")


def demo_same_game_refusal() -> None:
    rule("2. Two legs of the same game -- refused, not priced")

    legs = [leg("Chiefs ML", 0.62, "E1"), leg("Over 44.5", 0.51, "E1")]
    naive = legs[0].probability * legs[1].probability
    print(f"  Naive multiplication would say {naive:.4f}\n")

    try:
        value_parlay(ParlayQuote(legs=tuple(legs), offered_decimal=3.5))
    except CorrelationRefused as exc:
        print(f"  CorrelationRefused: {exc}")

    print("\n  With a measured correlation supplied, it prices:")
    for rho in (0.35, 0.0, -0.20):
        priced = value_parlay(
            ParlayQuote(legs=tuple(legs), offered_decimal=3.5),
            correlation_overrides={("Chiefs ML", "Over 44.5"): rho},
        )
        print(
            f"    rho={rho:+.2f} -> joint {priced.fair_probability:.4f}, "
            f"hold {priced.hold:+.1%}"
        )
    print("\n  That spread is why there is no default. The sign alone moves the")
    print("  verdict, so a plausible guess here is worse than no number.")


def demo_kalshi_alternative() -> None:
    rule("3. The same combination bought as separate Kalshi contracts")

    legs = [
        leg("Chiefs ML", 0.50, "E1"),
        leg("Ravens ML", 0.50, "E2", offset=8 * DAY),
        leg("Eagles ML", 0.53, "E3", offset=16 * DAY),
    ]
    equivalent = kalshi_equivalent(legs, contracts_per_leg=100)

    print(f"  Cost incl. fees      ${equivalent.total_cost_dollars:.2f}")
    print(f"  Fees                 ${equivalent.total_fee_dollars:.2f} "
          f"({equivalent.fee_share_of_stake:.1%} of stake)")
    print(f"  P(all three win)     {equivalent.all_win_probability:.4f}")
    print(f"  EV                   ${equivalent.expected_value_dollars:+.2f}")
    print(f"\n  > {equivalent.note}")


def demo_teaser() -> None:
    rule("4. A Wong teaser -- and what it takes to price one")

    print("  First, the two refusals.\n")

    try:
        build_leg(
            default_distribution(NFL), team="Chiefs", original_line=-8.0,
            points=6.0, predicted_margin=8.0, event_key="E1",
            league=NFL, commence_ms=NOW,
        )
    except TeaserUnpriceable as exc:
        print(f"  (a) smooth distribution -> {exc}\n")

    pooled = MarginDistribution(NFL).fit(synthetic_margins(0.0, 1200, seed=14))
    try:
        build_leg(
            pooled, team="Chiefs", original_line=-8.0, points=6.0,
            predicted_margin=8.0, event_key="E1", league=NFL, commence_ms=NOW,
        )
    except TeaserUnpriceable as exc:
        print(f"  (b) league-wide fit  -> {exc}\n")

    # Fitted per closing-spread bucket, which is what makes it priceable.
    buckets = fit_by_spread(
        NFL, synthetic_bucket_observations([-8.0, 2.0], n_per_bucket=1200)
    )

    favourite_bucket = buckets[spread_bucket_for(-8.0)]
    wins = sum(c for m, c in favourite_bucket.counts.items() if m > 0)
    print(f"  Bucket {favourite_bucket.spread_bucket:+g}: n={favourite_bucket.n}, "
          f"mean {favourite_bucket.mean:+.2f}, sd {favourite_bucket.sd:.1f}, "
          f"favourite wins {wins / favourite_bucket.n:.1%}")
    print(f"  Drag at a predicted +8.0: "
          f"{favourite_bucket.translation_points(8.0):.2f} pts")
    mass = favourite_bucket.key_number_mass()
    print("  Key-number mass: "
          + ", ".join(f"{k}={mass[k]:.1%}" for k in sorted(mass) if k in (3, 7, 10, 14)))

    print("\n  The screen over a slate:")
    board = [
        ("Chiefs", -8.0), ("Eagles", -3.5), ("Jets", 2.0),
        ("Bears", 7.5), ("Rams", -13.0), ("Bills", -7.5),
    ]
    for team, line in board:
        marker = "  <- Wong window" if (team, line) in find_wong_candidates(board) else ""
        print(f"    {team:<8} {line:+.1f}{marker}")

    legs = [
        build_leg(
            buckets[spread_bucket_for(-8.0)], team="Chiefs", original_line=-8.0,
            points=6.0, predicted_margin=8.0, event_key="E1", league=NFL,
            commence_ms=NOW,
        ),
        build_leg(
            buckets[spread_bucket_for(2.0)], team="Jets", original_line=2.0,
            points=6.0, predicted_margin=-2.0, event_key="E2", league=NFL,
            commence_ms=NOW + 8 * DAY,
        ),
    ]

    print()
    for teased in legs:
        print(
            f"  {teased.team:<8} {teased.original_line:+.1f} -> "
            f"{teased.teased_line:+.1f}  crosses {teased.crosses_key_numbers}  "
            f"cover {teased.cover_probability:.3f}"
        )

    valuation = value_teaser(legs, offered_decimal=STANDARD_TWO_TEAM_DECIMAL)
    breakeven = (1.0 / STANDARD_TWO_TEAM_DECIMAL) ** 0.5

    print(f"\n  Joint (correlated)   {valuation.fair_probability:.4f}")
    print(f"  Break-even per leg   {breakeven:.4f} at "
          f"{decimal_to_american(STANDARD_TWO_TEAM_DECIMAL):+d}")
    print(f"  EV per dollar        {valuation.ev_per_dollar:+.1%}")
    print(f"\n  > {valuation.verdict}")

    print("\n  Worth dwelling on: the shape is right, the key numbers are")
    print("  crossed, and it still loses. The Wong teaser's published 73-76%")
    print("  per leg is above the 73.9% break-even by a hair; ~67% is not. An")
    print("  earlier version of this demo printed +28.4% EV here, because the")
    print("  synthetic generator hit the right mean with the wrong variance and")
    print("  had the favourite winning 96% of games. See model/synthetic.py.")


def demo_independence_error() -> None:
    rule("5. How large the independence assumption is")

    for label, offset, league in (
        ("same day, same league", 3_600_000, NFL),
        ("same day, cross-sport", 3_600_000, "baseball_mlb"),
        ("different weeks", 10 * DAY, NFL),
    ):
        legs = [leg("a", 0.55, "E1"), leg("b", 0.52, "E2", offset, league)]
        error = independence_error(legs)
        print(f"  {label:<24} {error:+.3f} points")

    print("\n  Small here -- and reported on every parlay anyway, because for")
    print("  same-game legs it routinely exceeds the entire claimed edge.")


if __name__ == "__main__":
    demo_parlay()
    demo_same_game_refusal()
    demo_kalshi_alternative()
    demo_teaser()
    demo_independence_error()
    print()
