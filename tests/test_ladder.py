"""`backend/core/ladder.py` — the parlay desk's card builder (ADR 0070).

What these tests establish: the ladder is deterministic; it takes at most one
leg per fixture (so `CorrelationRefused` is structurally unreachable) on
EVERY recipe, not just the ones that existed when a test was written; its
headline joint is the conservative one with the per-method band beside it; a
leg with an unmeasurable or stale consensus age is excluded and counted; a
card the slate cannot fill says why in words, naming the predicate IT
applied rather than a predicate some other card applied; and two cuts that
select the same legs share one copula run without two cuts that select
different legs sharing anything.

What they do not establish: that any card is worth buying, or that the
conservative joint is well-calibrated — it is min-of-four compounded N times,
which the module docstring names as a bias, not a measurement.
"""

from __future__ import annotations

import pytest

from backend.core.ladder import (
    AGREEMENT_SPREAD_POINTS,
    CARD_SHAPES,
    CandidateLeg,
    SOON_HORIZON_MS,
    build_ladder,
)

MAX_AGE_MS = 900_000
BASE_COMMENCE = 1_700_000_000_000
#: An hour before the default kickoff, so the default fixtures sit INSIDE
#: the "Next 3 hours" horizon -- a test of the time box has to opt out of
#: it explicitly rather than get it by accident.
NOW_MS = BASE_COMMENCE - 3_600_000


def build(candidates, *, max_odds_age_ms=MAX_AGE_MS, now_ms=NOW_MS):
    return build_ladder(
        candidates, max_odds_age_ms=max_odds_age_ms, now_ms=now_ms
    )


def card(ladder, key: str):
    return next(c for c in ladder.cards if c.key == key)


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
    def test_six_games_build_every_card(self):
        ladder = build_ladder(games(6), max_odds_age_ms=MAX_AGE_MS, now_ms=NOW_MS)
        by_key = {c.key: c for c in ladder.cards}
        assert len(by_key["safe"].legs) == 3
        assert len(by_key["middle"].legs) == 4
        assert len(by_key["lottery"].legs) == 6
        assert len(by_key["longshot"].legs) == 3
        assert len(by_key["soon"].legs) == 3
        assert len(by_key["agreed"].legs) == 3

    def test_a_thin_slate_builds_what_it_can_and_says_why_not(self):
        ladder = build_ladder(games(3), max_odds_age_ms=MAX_AGE_MS, now_ms=NOW_MS)
        by_key = {c.key: c for c in ladder.cards}
        assert len(by_key["safe"].legs) == 3
        assert by_key["middle"].not_built_reason == (
            "needs 4 fresh games and the slate has 3"
        )
        assert by_key["lottery"].not_built_reason == (
            "needs 6 fresh games and the slate has 3"
        )

    def test_safe_builds_one_short_at_two_games(self):
        ladder = build_ladder(games(2), max_odds_age_ms=MAX_AGE_MS, now_ms=NOW_MS)
        safe = next(c for c in ladder.cards if c.key == "safe")
        assert len(safe.legs) == 2

    def test_an_empty_slate_is_a_reason_per_card_not_an_error(self):
        ladder = build_ladder([], max_odds_age_ms=MAX_AGE_MS, now_ms=NOW_MS)
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
        ladder = build_ladder(candidates, max_odds_age_ms=MAX_AGE_MS, now_ms=NOW_MS)
        safe = next(c for c in ladder.cards if c.key == "safe")
        assert [l.odds_event_id for l in safe.legs] == ["g1", "g2"]
        assert safe.legs[0].kalshi_market_ticker == "A"

    def test_strongest_probabilities_rank_first(self):
        ladder = build_ladder(games(6), max_odds_age_ms=MAX_AGE_MS, now_ms=NOW_MS)
        safe = next(c for c in ladder.cards if c.key == "safe")
        assert [l.odds_event_id for l in safe.legs] == ["g0", "g1", "g2"]

    def test_the_lottery_prefers_a_spread_rung_within_a_game(self):
        candidates = games(6) + [
            leg("g0", p=0.58, market="spreads", point=-1.5, ticker="SPREAD-G0")
        ]
        ladder = build_ladder(candidates, max_odds_age_ms=MAX_AGE_MS, now_ms=NOW_MS)
        by_key = {c.key: c for c in ladder.cards}
        lottery_g0 = next(
            l for l in by_key["lottery"].legs if l.odds_event_id == "g0"
        )
        safe_g0 = next(l for l in by_key["safe"].legs if l.odds_event_id == "g0")
        assert lottery_g0.kalshi_market_ticker == "SPREAD-G0"
        assert safe_g0.market == "h2h"

    def test_two_runs_over_the_same_rows_build_the_same_cards(self):
        candidates = games(8)
        first = build_ladder(candidates, max_odds_age_ms=MAX_AGE_MS, now_ms=NOW_MS)
        second = build_ladder(list(reversed(candidates)), max_odds_age_ms=MAX_AGE_MS, now_ms=NOW_MS)
        for a, b in zip(first.cards, second.cards):
            assert [l.kalshi_market_ticker for l in a.legs] == [
                l.kalshi_market_ticker for l in b.legs
            ]

    def test_a_probability_tie_breaks_on_kickoff_then_ticker(self):
        candidates = [
            leg("late", p=0.6, commence_ms=BASE_COMMENCE + 1, ticker="ZZ"),
            leg("early", p=0.6, commence_ms=BASE_COMMENCE, ticker="AA"),
        ]
        ladder = build_ladder(candidates, max_odds_age_ms=MAX_AGE_MS, now_ms=NOW_MS)
        safe = next(c for c in ladder.cards if c.key == "safe")
        assert [l.kalshi_market_ticker for l in safe.legs] == ["AA", "ZZ"]


class TestFreshness:
    def test_a_stale_leg_is_excluded_and_counted(self):
        candidates = games(2) + [leg("g9", p=0.9, age=MAX_AGE_MS + 1)]
        ladder = build_ladder(candidates, max_odds_age_ms=MAX_AGE_MS, now_ms=NOW_MS)
        safe = next(c for c in ladder.cards if c.key == "safe")
        assert all(l.odds_event_id != "g9" for l in safe.legs)
        assert ladder.excluded["stale_consensus"] == 1

    def test_an_unmeasurable_age_refuses_never_passes_as_fresh(self):
        """A pre-v20 row has no `oldest_book_age_ms`; treating that as age
        zero would let the stalest rows in the record present as freshest."""
        candidates = games(2) + [leg("g9", p=0.9, age=None)]
        ladder = build_ladder(candidates, max_odds_age_ms=MAX_AGE_MS, now_ms=NOW_MS)
        safe = next(c for c in ladder.cards if c.key == "safe")
        assert all(l.odds_event_id != "g9" for l in safe.legs)
        assert ladder.excluded["age_unmeasurable"] == 1

    def test_a_certainty_is_not_a_leg(self):
        candidates = games(2) + [leg("g9", p=1.0)]
        ladder = build_ladder(candidates, max_odds_age_ms=MAX_AGE_MS, now_ms=NOW_MS)
        assert ladder.excluded["not_a_probability"] == 1


class TestJoints:
    def test_the_headline_is_the_conservative_joint(self):
        """Each leg at min-of-four; same-night same-league correlation makes
        the copula joint slightly larger than the naive product."""
        ladder = build_ladder(games(6), max_odds_age_ms=MAX_AGE_MS, now_ms=NOW_MS)
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
        ladder = build_ladder(candidates, max_odds_age_ms=MAX_AGE_MS, now_ms=NOW_MS)
        safe = next(c for c in ladder.cards if c.key == "safe")
        assert safe.joint.by_method["additive"] is None
        assert safe.joint.by_method["multiplicative"] is not None

    def test_method_range_spans_the_known_methods(self):
        ladder = build_ladder(games(4), max_odds_age_ms=MAX_AGE_MS, now_ms=NOW_MS)
        safe = next(c for c in ladder.cards if c.key == "safe")
        low, high = safe.joint.method_range
        known = [v for v in safe.joint.by_method.values() if v is not None]
        assert low == min(known) and high == max(known)


class TestCardInvariants:
    def test_a_card_has_legs_or_a_reason_never_both(self):
        from backend.core.ladder import Card

        with pytest.raises(ValueError):
            Card(key="x", title="X", what_it_is="")  # neither
        with pytest.raises(ValueError):
            Card(
                key="x", title="X", what_it_is="",
                legs=(leg("g"),), not_built_reason="no",
            )

    def test_the_shapes_are_the_six_registered_cards(self):
        """Six since 2026-08-26. This is the one assertion that catches a
        recipe added or dropped by accident, so it pins the identities and
        the lengths rather than just the count.

        `lottery`'s TITLE changed with the same commit and its key did not:
        `parlay_lookups` and the Discord dedupe history are keyed on it, so
        renaming the key would make the record incomparable across the
        rename for no gain.
        """
        assert [(r.key, r.min_legs, r.max_legs) for r in CARD_SHAPES] == [
            ("safe", 2, 3),
            ("middle", 4, 4),
            ("lottery", 6, 6),
            ("longshot", 2, 3),
            ("soon", 2, 3),
            ("agreed", 2, 3),
        ]
        assert next(r for r in CARD_SHAPES if r.key == "lottery").title == (
            "Long ladder"
        )
        assert all(r.what_it_is for r in CARD_SHAPES)


class TestLongshot:
    """The one recipe that ranks the pool the other way (2026-08-26).

    What it establishes: `longest_first` inverts the probability term of the
    sort key and nothing else, so the least likely leg per fixture leads and
    the kickoff/ticker tie-break keeps its direction.

    What it does NOT establish: that a Longshot card is priced well. It is the
    same pool ranked backwards, and `p_conservative` is min-of-four, which
    understates an underdog by construction.
    """

    def test_the_longshot_takes_the_least_likely_games(self):
        # games(6) descends 0.75 -> 0.60, so the last three are the long prices.
        ladder = build(games(6))
        assert [l.odds_event_id for l in card(ladder, "longshot").legs] == [
            "g5", "g4", "g3"
        ]

    def test_within_a_game_it_takes_the_longer_side(self):
        candidates = games(2) + [leg("g0", p=0.30, ticker="DOG-G0")]
        ladder = build(candidates)
        longshot_g0 = next(
            l for l in card(ladder, "longshot").legs if l.odds_event_id == "g0"
        )
        safe_g0 = next(
            l for l in card(ladder, "safe").legs if l.odds_event_id == "g0"
        )
        assert longshot_g0.kalshi_market_ticker == "DOG-G0"
        assert safe_g0.kalshi_market_ticker != "DOG-G0"

    def test_a_probability_tie_still_breaks_on_kickoff_then_ticker(self):
        """The tie-break does NOT invert with the ranking -- if it did, two
        runs over reordered rows could build different Longshot cards."""
        candidates = [
            leg("late", p=0.6, commence_ms=BASE_COMMENCE + 1, ticker="ZZ"),
            leg("early", p=0.6, commence_ms=BASE_COMMENCE, ticker="AA"),
        ]
        ladder = build(candidates)
        assert [
            l.kalshi_market_ticker for l in card(ladder, "longshot").legs
        ] == ["AA", "ZZ"]

    def test_two_runs_over_reordered_rows_build_the_same_longshot(self):
        candidates = games(8)
        first = card(build(candidates), "longshot")
        second = card(build(list(reversed(candidates))), "longshot")
        assert [l.kalshi_market_ticker for l in first.legs] == [
            l.kalshi_market_ticker for l in second.legs
        ]


class TestTimeBox:
    """"Next 3 hours" -- the only recipe that reads the clock (2026-08-26).

    The horizon is measured from the caller's `now_ms` against the
    SPORTSBOOK's `commence_ms`. Kalshi's own runs three hours late and is
    never read here, which is why a three-hour horizon is not a coincidence
    waiting to be confused with one.
    """

    def test_a_game_past_the_horizon_is_out_of_the_soon_card(self):
        far = leg("far", p=0.95, commence_ms=NOW_MS + SOON_HORIZON_MS + 1)
        ladder = build(games(2) + [far])
        assert all(l.odds_event_id != "far" for l in card(ladder, "soon").legs)

    def test_and_that_same_game_still_leads_the_safe_card(self):
        """The vacuity guard on the test above: `far` is the strongest leg on
        the slate, so its absence from `soon` is the time box and not the leg
        having been dropped for some other reason."""
        far = leg("far", p=0.95, commence_ms=NOW_MS + SOON_HORIZON_MS + 1)
        ladder = build(games(2) + [far])
        assert card(ladder, "safe").legs[0].odds_event_id == "far"

    def test_a_game_exactly_on_the_horizon_is_in(self):
        near = leg("near", p=0.95, commence_ms=NOW_MS + SOON_HORIZON_MS)
        ladder = build(games(2) + [near])
        assert card(ladder, "soon").legs[0].odds_event_id == "near"

    def test_the_refusal_names_the_horizon_not_fresh_games(self):
        """A card filtered on the clock that says "needs 2 fresh games and the
        slate has 0" names a predicate it did not apply -- the slate here is
        four fresh games, every one of them tomorrow."""
        far = [
            leg(f"f{i}", p=0.7, commence_ms=NOW_MS + SOON_HORIZON_MS + 1)
            for i in range(4)
        ]
        ladder = build(far)
        assert card(ladder, "soon").not_built_reason == (
            "needs 2 fresh games starting within three hours and the slate has 0"
        )
        assert card(ladder, "safe").not_built_reason is None

    def test_the_horizon_constant_matches_the_words_on_the_card(self):
        """`what_it_is` and `pool_words` both say "three hours" in prose. If
        the constant moves and the words do not, six cards on one screen
        start lying about which is which."""
        recipe = next(r for r in CARD_SHAPES if r.key == "soon")
        assert SOON_HORIZON_MS == 3 * 3_600_000
        assert "three hours" in recipe.what_it_is
        assert "three hours" in recipe.pool_words


def method_spread_leg(game: str, *, p: float, points: float, **kw) -> CandidateLeg:
    """A leg whose four devig methods span exactly `points` percentage points."""
    base = leg(game, p=p, **kw)
    return CandidateLeg(
        **{
            **base.__dict__,
            "p_by_method": {
                "multiplicative": p,
                "additive": p + points / 100.0,
                "power": p + points / 200.0,
                "shin": p + points / 400.0,
            },
        }
    )


class TestMethodAgreement:
    """"Agreed" -- CLAUDE.md rule 2 shipped as a product (2026-08-26).

    `p_by_method` was computed on every leg and thrown away. This recipe reads
    it: a leg survives only when all four devig methods land within
    `AGREEMENT_SPREAD_POINTS` of each other.

    What it does NOT establish: that an agreed leg is better priced. Four
    devig methods are four transformations of ONE input, so their agreement
    says the method choice did not move this number -- not that the books
    were right.
    """

    def test_a_leg_whose_methods_disagree_is_out(self):
        loud = method_spread_leg("loud", p=0.95, points=AGREEMENT_SPREAD_POINTS + 1.0)
        ladder = build(games(2) + [loud])
        assert all(l.odds_event_id != "loud" for l in card(ladder, "agreed").legs)

    def test_and_that_same_leg_still_leads_the_safe_card(self):
        loud = method_spread_leg("loud", p=0.95, points=AGREEMENT_SPREAD_POINTS + 1.0)
        ladder = build(games(2) + [loud])
        assert card(ladder, "safe").legs[0].odds_event_id == "loud"

    def test_a_leg_inside_the_threshold_survives(self):
        quiet = method_spread_leg("quiet", p=0.95, points=AGREEMENT_SPREAD_POINTS - 1.0)
        ladder = build(games(2) + [quiet])
        assert card(ladder, "agreed").legs[0].odds_event_id == "quiet"

    def test_a_leg_missing_one_method_is_refused_not_admitted(self):
        """Three methods clustered tightly with the fourth absent is not
        agreement among four. Unreadable resolves to a refusal, never to a
        convenient value (`tasks/lessons.md`)."""
        partial = method_spread_leg("partial", p=0.95, points=AGREEMENT_SPREAD_POINTS / 4.0)
        partial = CandidateLeg(
            **{
                **partial.__dict__,
                "p_by_method": {**partial.p_by_method, "shin": None},
            }
        )
        ladder = build(games(2) + [partial])
        assert all(
            l.odds_event_id != "partial" for l in card(ladder, "agreed").legs
        )
        # ...and it is still a perfectly good leg for every other card.
        assert card(ladder, "safe").legs[0].odds_event_id == "partial"

    def test_the_refusal_names_agreement_not_fresh_games(self):
        loud = [
            method_spread_leg(f"l{i}", p=0.7 - i * 0.01, points=AGREEMENT_SPREAD_POINTS + 1.0)
            for i in range(4)
        ]
        ladder = build(loud)
        assert card(ladder, "agreed").not_built_reason == (
            "needs 2 fresh games whose four devig methods agree and the slate "
            "has 0"
        )
        assert card(ladder, "safe").not_built_reason is None


class TestEveryRecipeInheritsTheGuards:
    """Parameterised over `CARD_SHAPES`, so a seventh recipe cannot be added
    without inheriting the one-leg-per-game guard that makes
    `CorrelationRefused` structurally unreachable (2026-08-26)."""

    @staticmethod
    def _slate() -> list[CandidateLeg]:
        candidates: list[CandidateLeg] = []
        for i in range(6):
            candidates.append(leg(f"g{i}", p=0.70 - i * 0.03, ticker=f"A{i}"))
            candidates.append(leg(f"g{i}", p=0.30 + i * 0.03, ticker=f"B{i}"))
            candidates.append(
                leg(
                    f"g{i}", p=0.50, market="spreads", point=-1.5,
                    ticker=f"S{i}",
                )
            )
        return candidates

    @pytest.mark.parametrize("key", [r.key for r in CARD_SHAPES])
    def test_at_most_one_leg_per_game(self, key):
        built = card(build(self._slate()), key)
        # Vacuity guard: a card that refused proves nothing about selection.
        assert built.not_built_reason is None
        ids = [l.odds_event_id for l in built.legs]
        assert len(ids) == len(set(ids))

    @pytest.mark.parametrize("key", [r.key for r in CARD_SHAPES])
    def test_a_stale_leg_reaches_no_card(self, key):
        stale = leg("stale", p=0.99, age=MAX_AGE_MS + 1)
        built = card(build(self._slate() + [stale]), key)
        assert built.not_built_reason is None
        assert all(l.odds_event_id != "stale" for l in built.legs)


class TestJointMemo:
    """Six cuts of one pool routinely select the SAME legs, and `_joint` runs
    a 200,000-sample copula five times per distinct set (2026-08-26).

    This is the only thing standing between the cache and a silent
    correctness bug, so it asserts both halves: the same set is computed once,
    and a genuinely different set is not served the cached answer.
    """

    def test_cuts_selecting_the_same_legs_share_one_joint(self, monkeypatch):
        import backend.core.ladder as mod

        calls: list[tuple] = []
        real = mod._joint

        def counting(selected):
            calls.append(tuple(l.kalshi_market_ticker for l in selected))
            return real(selected)

        monkeypatch.setattr(mod, "_joint", counting)
        ladder = build(games(3))
        safe = card(ladder, "safe")
        soon = card(ladder, "soon")
        agreed = card(ladder, "agreed")

        tickers = [l.kalshi_market_ticker for l in safe.legs]
        assert [l.kalshi_market_ticker for l in soon.legs] == tickers
        assert [l.kalshi_market_ticker for l in agreed.legs] == tickers
        assert safe.joint is soon.joint is agreed.joint
        assert calls.count(tuple(tickers)) == 1

    def test_two_cuts_sharing_a_LEADING_leg_do_not_share_a_joint(self):
        """The case that makes `_joint_key` the whole selection rather than
        something cheaper: two cuts routinely agree on the leaders and diverge
        further down. Here `g2` starts past the horizon, so Safe takes
        [g0, g1, g2] and Next 3 hours takes [g0, g1, g3] -- same first leg,
        different card, and a key that stopped at the first ticker would serve
        one card's joint on the other.

        Mutation observed red: `memo = selected[0].kalshi_market_ticker`.
        """
        slate = [
            leg("g0", p=0.75),
            leg("g1", p=0.72),
            leg("g2", p=0.69, commence_ms=NOW_MS + SOON_HORIZON_MS + 1),
            leg("g3", p=0.66),
        ]
        ladder = build(slate)
        safe = card(ladder, "safe")
        soon = card(ladder, "soon")
        assert [l.odds_event_id for l in safe.legs] == ["g0", "g1", "g2"]
        assert [l.odds_event_id for l in soon.legs] == ["g0", "g1", "g3"]
        assert safe.legs[0].kalshi_market_ticker == soon.legs[0].kalshi_market_ticker
        assert safe.joint is not soon.joint
        assert safe.joint.conservative != soon.joint.conservative

    def test_a_different_leg_set_is_not_served_the_cached_joint(self):
        """Vacuity guard on the test above -- a memo that returned the first
        joint for everything would pass it."""
        ladder = build(games(6))
        safe = card(ladder, "safe")
        longshot = card(ladder, "longshot")
        assert {l.kalshi_market_ticker for l in safe.legs} != {
            l.kalshi_market_ticker for l in longshot.legs
        }
        assert safe.joint is not longshot.joint
        assert safe.joint.conservative > longshot.joint.conservative
