"""`backend/core/ladder.py` — the parlay desk's card builder (ADR 0070).

What these tests establish: the ladder is deterministic; it takes at most one
leg per fixture (so `CorrelationRefused` is structurally unreachable); its
headline joint is the conservative one with the per-method band beside it; a
leg with an unmeasurable or stale consensus age is excluded and counted; and
a card the slate cannot fill says why in words.

What they do not establish: that any card is worth buying, or that the
conservative joint is well-calibrated — it is min-of-four compounded N times,
which the module docstring names as a bias, not a measurement.
"""

from __future__ import annotations

import pytest

from backend.core.ladder import (
    CARD_SHAPES,
    CandidateLeg,
    build_ladder,
)

MAX_AGE_MS = 900_000
BASE_COMMENCE = 1_700_000_000_000


def leg(
    game: str,
    *,
    p: float = 0.6,
    market: str = "h2h",
    point=None,
    age: int | None = 10_000,
    ticker: str | None = None,
    commence_ms: int = BASE_COMMENCE,
    league: str = "baseball_mlb",
) -> CandidateLeg:
    return CandidateLeg(
        label=f"{game} to win",
        event_title=f"{game} game",
        kalshi_event_ticker=f"KXMLBGAME-{game}",
        kalshi_market_ticker=ticker or f"KXMLBGAME-{game}-{market}-{point}",
        odds_event_id=game,
        league=league,
        commence_ms=commence_ms,
        market=market,
        team=game,
        point=point,
        p_conservative=p,
        p_by_method={
            "multiplicative": min(p + 0.02, 0.99),
            "additive": min(p + 0.01, 0.99),
            "power": min(p + 0.015, 0.99),
            "shin": min(p + 0.005, 0.99),
        },
        odds_age_now_ms=age,
    )


def games(n: int, *, start_p: float = 0.75) -> list[CandidateLeg]:
    """n distinct games with strictly descending probabilities."""
    return [leg(f"g{i}", p=start_p - i * 0.03) for i in range(n)]


class TestShapes:
    def test_six_games_build_all_three_cards(self):
        ladder = build_ladder(games(6), max_odds_age_ms=MAX_AGE_MS)
        by_key = {c.key: c for c in ladder.cards}
        assert len(by_key["safe"].legs) == 3
        assert len(by_key["middle"].legs) == 4
        assert len(by_key["lottery"].legs) == 6

    def test_a_thin_slate_builds_what_it_can_and_says_why_not(self):
        ladder = build_ladder(games(3), max_odds_age_ms=MAX_AGE_MS)
        by_key = {c.key: c for c in ladder.cards}
        assert len(by_key["safe"].legs) == 3
        assert by_key["middle"].not_built_reason == (
            "needs 4 fresh games and the slate has 3"
        )
        assert by_key["lottery"].not_built_reason == (
            "needs 6 fresh games and the slate has 3"
        )

    def test_safe_builds_one_short_at_two_games(self):
        ladder = build_ladder(games(2), max_odds_age_ms=MAX_AGE_MS)
        safe = next(c for c in ladder.cards if c.key == "safe")
        assert len(safe.legs) == 2

    def test_an_empty_slate_is_three_reasons_not_an_error(self):
        ladder = build_ladder([], max_odds_age_ms=MAX_AGE_MS)
        assert all(c.not_built_reason is not None for c in ladder.cards)


class TestSelection:
    def test_at_most_one_leg_per_game(self):
        """Two sides of one fixture never share a card — the structural guard
        that makes `CorrelationRefused` unreachable from selection."""
        candidates = [
            leg("g1", p=0.60, ticker="A"),
            leg("g1", p=0.40, ticker="B"),
            leg("g2", p=0.55, ticker="C"),
        ]
        ladder = build_ladder(candidates, max_odds_age_ms=MAX_AGE_MS)
        safe = next(c for c in ladder.cards if c.key == "safe")
        assert [l.odds_event_id for l in safe.legs] == ["g1", "g2"]
        assert safe.legs[0].kalshi_market_ticker == "A"

    def test_strongest_probabilities_rank_first(self):
        ladder = build_ladder(games(6), max_odds_age_ms=MAX_AGE_MS)
        safe = next(c for c in ladder.cards if c.key == "safe")
        assert [l.odds_event_id for l in safe.legs] == ["g0", "g1", "g2"]

    def test_the_lottery_prefers_a_spread_rung_within_a_game(self):
        candidates = games(6) + [
            leg("g0", p=0.58, market="spreads", point=-1.5, ticker="SPREAD-G0")
        ]
        ladder = build_ladder(candidates, max_odds_age_ms=MAX_AGE_MS)
        by_key = {c.key: c for c in ladder.cards}
        lottery_g0 = next(
            l for l in by_key["lottery"].legs if l.odds_event_id == "g0"
        )
        safe_g0 = next(l for l in by_key["safe"].legs if l.odds_event_id == "g0")
        assert lottery_g0.kalshi_market_ticker == "SPREAD-G0"
        assert safe_g0.market == "h2h"

    def test_two_runs_over_the_same_rows_build_the_same_cards(self):
        candidates = games(8)
        first = build_ladder(candidates, max_odds_age_ms=MAX_AGE_MS)
        second = build_ladder(list(reversed(candidates)), max_odds_age_ms=MAX_AGE_MS)
        for a, b in zip(first.cards, second.cards):
            assert [l.kalshi_market_ticker for l in a.legs] == [
                l.kalshi_market_ticker for l in b.legs
            ]

    def test_a_probability_tie_breaks_on_kickoff_then_ticker(self):
        candidates = [
            leg("late", p=0.6, commence_ms=BASE_COMMENCE + 1, ticker="ZZ"),
            leg("early", p=0.6, commence_ms=BASE_COMMENCE, ticker="AA"),
        ]
        ladder = build_ladder(candidates, max_odds_age_ms=MAX_AGE_MS)
        safe = next(c for c in ladder.cards if c.key == "safe")
        assert [l.kalshi_market_ticker for l in safe.legs] == ["AA", "ZZ"]


class TestFreshness:
    def test_a_stale_leg_is_excluded_and_counted(self):
        candidates = games(2) + [leg("g9", p=0.9, age=MAX_AGE_MS + 1)]
        ladder = build_ladder(candidates, max_odds_age_ms=MAX_AGE_MS)
        safe = next(c for c in ladder.cards if c.key == "safe")
        assert all(l.odds_event_id != "g9" for l in safe.legs)
        assert ladder.excluded["stale_consensus"] == 1

    def test_an_unmeasurable_age_refuses_never_passes_as_fresh(self):
        """A pre-v20 row has no `oldest_book_age_ms`; treating that as age
        zero would let the stalest rows in the record present as freshest."""
        candidates = games(2) + [leg("g9", p=0.9, age=None)]
        ladder = build_ladder(candidates, max_odds_age_ms=MAX_AGE_MS)
        safe = next(c for c in ladder.cards if c.key == "safe")
        assert all(l.odds_event_id != "g9" for l in safe.legs)
        assert ladder.excluded["age_unmeasurable"] == 1

    def test_a_certainty_is_not_a_leg(self):
        candidates = games(2) + [leg("g9", p=1.0)]
        ladder = build_ladder(candidates, max_odds_age_ms=MAX_AGE_MS)
        assert ladder.excluded["not_a_probability"] == 1


class TestJoints:
    def test_the_headline_is_the_conservative_joint(self):
        """Each leg at min-of-four; same-night same-league correlation makes
        the copula joint slightly larger than the naive product."""
        ladder = build_ladder(games(6), max_odds_age_ms=MAX_AGE_MS)
        lottery = next(c for c in ladder.cards if c.key == "lottery")
        joint = lottery.joint
        naive = 1.0
        for l in lottery.legs:
            naive *= l.p_conservative
        assert joint.naive_product == pytest.approx(naive)
        # 0.05 same-day-same-league correlation raises P(all win) above
        # independence, so the error is negative in this fixture.
        assert joint.conservative > joint.naive_product
        assert joint.independence_error_points == pytest.approx(
            (joint.naive_product - joint.conservative) * 100.0
        )

    def test_per_method_joints_bracket_nothing_silently(self):
        """A leg missing one method's number makes that method's joint None —
        absence, never substitution."""
        broken = leg("g5", p=0.6)
        broken = CandidateLeg(
            **{
                **broken.__dict__,
                "p_by_method": {
                    "multiplicative": 0.62,
                    "additive": None,
                    "power": 0.61,
                    "shin": 0.60,
                },
            }
        )
        candidates = games(2) + [broken]
        ladder = build_ladder(candidates, max_odds_age_ms=MAX_AGE_MS)
        safe = next(c for c in ladder.cards if c.key == "safe")
        assert safe.joint.by_method["additive"] is None
        assert safe.joint.by_method["multiplicative"] is not None

    def test_method_range_spans_the_known_methods(self):
        ladder = build_ladder(games(4), max_odds_age_ms=MAX_AGE_MS)
        safe = next(c for c in ladder.cards if c.key == "safe")
        low, high = safe.joint.method_range
        known = [v for v in safe.joint.by_method.values() if v is not None]
        assert low == min(known) and high == max(known)


class TestCardInvariants:
    def test_a_card_has_legs_or_a_reason_never_both(self):
        from backend.core.ladder import Card

        with pytest.raises(ValueError):
            Card(key="x", title="X")  # neither
        with pytest.raises(ValueError):
            Card(key="x", title="X", legs=(leg("g"),), not_built_reason="no")

    def test_the_shapes_are_the_three_registered_cards(self):
        assert [(k, lo, hi) for k, _, lo, hi in CARD_SHAPES] == [
            ("safe", 2, 3), ("middle", 4, 4), ("lottery", 6, 6)
        ]
