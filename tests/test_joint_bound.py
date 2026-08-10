"""Tests for the joint bound.

Governed by `docs/measurements/2026-08-10-preregistration-joint-bound.md`. Every
test here is named after the claim it makes, and every guard was verified by
disabling it and watching the test go red -- a guard whose test stays green when
the guard is removed is decoration.

The tests are anchored where a **wrong implementation gives a different
answer**, not the same one. `tasks/lessons.md`, "four audits, one failure
shape": four separate checks all agreed because they all consumed the same
upstream value, so agreement measured nothing. So the cluster-key test uses two
real tickers of different lengths, which no fixed-character chop can satisfy
simultaneously; the freshness test uses a composite and a longer code sharing
the same prefix, which a `LIKE` or a substring test both get wrong; and the
no-stacking test uses a row that the stack clears and neither alternative does.
"""

from __future__ import annotations

import json
import math
import re

import pytest

from backend.analysis import joint_bound as jb
from backend.analysis.validate import BUCKETS
from backend.core.fees import fee_candidates


def make_row(**overrides) -> jb.Row:
    """A P0 row with everything readable. Overrides say what the test is about."""
    fields = {
        "id": 1,
        "ticker": "KXMLBGAME-26AUG09DETSEA-SEA",
        "side": "yes",
        "created_ms": jb.BANKROLL_ERA_SETTLED_MS,
        "ask_tenths": 500,
        "fair_probability": 0.48,
        "suppressed_reason": None,
    }
    fields.update(overrides)
    return jb.Row(**fields)


def fixture_tickers(fixtures_dir) -> set[str]:
    """Every ticker appearing in a captured payload. Wire format, not invented."""
    pattern = re.compile(r'"(?:ticker|event_ticker)"\s*:\s*"([^"]+)"')
    found: set[str] = set()
    for path in sorted(fixtures_dir.glob("*.json")):
        found.update(pattern.findall(path.read_text(encoding="utf-8")))
    return found


class TestTheStackedGenerousFeeIsZeroAtEveryPriceAndSize:
    """§C3 / §F2. The whole primary bound is one subtraction because of this."""

    def test_model_b_maker_is_zero_in_all_7992_price_size_cases(self):
        # Exhaustive, not sampled: 999 tradeable prices x 8 sizes. If this is
        # ever non-zero the primary's `S` is missing a fee term and every count
        # produced from it is wrong in the flattering direction, so it must fail
        # loudly rather than drift.
        violations = jb.maker_model_b_nonzero_cases()
        assert violations == [], f"{len(violations)} non-zero cases, e.g. {violations[:3]}"

    def test_the_case_count_is_7992_so_the_sweep_cannot_silently_shrink(self):
        # A guard that checks nothing because its loop is empty passes forever.
        cases = [
            (p, n) for p in range(1, 1000) for n in jb.ZERO_FEE_SIZES
        ]
        assert len(cases) == 7992

    def test_the_taker_basis_is_not_zero_so_the_sweep_can_detect_a_non_zero(self):
        # The control for the test above: the same sweep on the taker basis must
        # find plenty. A zero-finding sweep and a broken sweep look identical
        # without this.
        nonzero = [
            p
            for p in range(1, 1000)
            if fee_candidates(p, 1, False)["model_b_per_contract_nearest"] != 0.0
        ]
        assert len(nonzero) > 100


class TestTheShortfallIsTheAskMinusTheFair:
    """§6's `S = entry_ask_tenths - 1000 * fair_probability`."""

    def test_shortfall_is_positive_when_the_ask_sits_above_the_fair(self):
        assert jb.primary_shortfall_tenths(
            make_row(ask_tenths=500, fair_probability=0.48)
        ) == pytest.approx(20.0)

    def test_shortfall_is_negative_when_the_fair_sits_above_the_ask(self):
        assert jb.primary_shortfall_tenths(
            make_row(ask_tenths=480, fair_probability=0.50)
        ) == pytest.approx(-20.0)

    def test_shortfall_refuses_a_row_with_no_readable_ask(self):
        # Unreadable resolves to None and the caller refuses -- it does not
        # substitute 0, which here would be a free contract and an edge of +48c.
        with pytest.raises(ValueError):
            jb.primary_shortfall_tenths(make_row(ask_tenths=None))

    def test_shortfall_refuses_a_row_with_no_readable_fair(self):
        with pytest.raises(ValueError):
            jb.primary_shortfall_tenths(make_row(fair_probability=None))

    def test_the_stored_edge_column_does_not_enter_the_shortfall(self):
        # §S2 item 11: `edge_tenths` is diagnostic only. Its divisor is not
        # recoverable from the row, so a shortfall that read it would be a
        # per-contract edge at an unknown size.
        honest = jb.primary_shortfall_tenths(make_row())
        poisoned = jb.primary_shortfall_tenths(
            make_row(stored_edge_tenths_DO_NOT_USE=9999.0, stored_fee_DO_NOT_USE=9.99)
        )
        assert honest == poisoned


class TestKIsTheCountOfRowsBelowTenDelta:
    """§6's identity: a row clears at delta points **iff** `S < 10*delta`."""

    def test_k_counts_exactly_the_rows_whose_shortfall_is_below_ten_delta(self):
        shortfalls = [-5.0, 0.0, 1.79, 1.8, 20.29, 20.3, 99.9, 100.0, 400.0]
        for points, tenths in jb.DELTA_LADDER:
            expected = sum(1 for s in shortfalls if s < tenths)
            assert jb.k_at_delta(shortfalls, points) == expected

    def test_the_boundary_is_strict_so_a_row_exactly_at_ten_delta_does_not_clear(self):
        # Strict `<`, not `<=`. A row whose shortfall exactly equals the
        # allowance has not been made actionable by it, and the histogram's
        # cells are left-open right-closed to match.
        assert not jb.clears_at(20.3, 2.03)
        assert jb.clears_at(20.29, 2.03)

    def test_the_registered_tenths_column_equals_ten_times_the_points_column(self):
        # The two columns of §5's table must agree, but the tenths column is
        # what the code uses: `10 * 2.03` is 20.299999999999997 in binary
        # floating point, which sits below the registered histogram edge of 20.3
        # and would move a row across a cell boundary.
        for points, tenths in jb.DELTA_LADDER:
            assert round(10.0 * points, 10) == round(tenths, 10)

    def test_the_threshold_is_the_registered_literal_not_a_product(self):
        # Exact float equality, deliberately. `10 * 2.03` is
        # 20.299999999999997, which is a different number from the registered
        # 20.3 and from the histogram edge that must agree with it. Rounding
        # this comparison to any number of places would hide exactly the defect
        # it exists to catch.
        assert jb.delta_tenths(2.03) == 20.3
        assert jb.delta_tenths(0.18) == 1.8
        assert 10.0 * 2.03 != 20.3

    def test_a_delta_off_the_ladder_is_refused(self):
        # §C2: no delta outside the ladder may be introduced after the data is
        # read. The refusal is what makes that a property of the code rather
        # than a promise in a document.
        with pytest.raises(ValueError):
            jb.k_at_delta([0.0], 1.0)

    def test_d_star_and_k_are_the_same_distribution_read_two_ways(self):
        # `K(delta) >= 1` exactly when `delta > D*`.
        shortfalls = [42.0, 7.5, 130.0]
        d_star = jb.d_star_points(shortfalls)
        assert d_star == pytest.approx(0.75)
        for points, _ in jb.DELTA_LADDER:
            assert (jb.k_at_delta(shortfalls, points) >= 1) == (points > d_star)

    def test_d_star_over_an_empty_population_is_none_not_zero(self):
        assert jb.d_star_points([]) is None


class TestTheLadderReachesThePointTheDevigKnobReaches:
    """Amendment 1 §A1: a sixth rung at 16.70, and Branch Z moves to it."""

    def test_the_ladder_has_six_rungs_and_the_original_five_are_unchanged(self):
        assert [p for p, _ in jb.DELTA_LADDER] == [0.00, 0.18, 2.03, 5.00, 10.00, 16.70]

    def test_the_top_rung_is_above_the_measured_reach_of_the_devig_knob(self):
        # §A1 measured the worst method spread anywhere in the swept line space
        # at 16.649 points. A ladder topping out below that could declare the
        # central question CLOSED on a record the knob could still have moved.
        assert jb.D_SWEPT_POINTS == 16.7
        assert jb.D_SWEPT_POINTS > 16.649
        assert max(p for p, _ in jb.DELTA_LADDER) == jb.D_SWEPT_POINTS

    def test_the_top_rungs_threshold_is_the_registered_literal(self):
        # `10 * 16.70` happens to land exactly on 167.0 in binary floating
        # point, unlike `10 * 0.18` and `10 * 2.03`. Asserted anyway, and
        # asserted as an exact equality: which of the six rungs survives a
        # multiply is an accident of the bit pattern, and a harness that relies
        # on that accident is one edited constant from being wrong.
        assert jb.delta_tenths(16.70) == 167.0
        assert (16.70, 167.0) in jb.DELTA_LADDER

    def test_a_row_twelve_points_short_is_caught_by_the_sixth_rung_only(self):
        # The concrete false closure §A1 exists to prevent: a record whose
        # nearest row is 12 points short reads K = 0 at every one of the five
        # committed rungs.
        row = make_row(ask_tenths=520, fair_probability=0.40)  # S = +120 tenths
        ladder = jb.k_ladder([row])
        assert [ladder[p][0] for p, _ in jb.DELTA_LADDER] == [0, 0, 0, 0, 0, 1]


class TestTheVerdictHasThreeOutcomesNotTwo:
    """§A1's partition on `D*`, and Z-NARROW is a distinct verdict."""

    def test_a_record_within_realistic_reach_is_branch_n(self):
        assert jb.verdict(0.0) == jb.BRANCH_N
        assert jb.verdict(3.5) == jb.BRANCH_N

    def test_a_record_between_the_thresholds_is_z_narrow(self):
        # Closed against realistic slates, NOT against lopsided or high-hold
        # lines. In this band the confirmatory run becomes decision-bearing and
        # the ADR waits for it.
        assert jb.verdict(3.51) == jb.Z_NARROW
        assert jb.verdict(10.0) == jb.Z_NARROW
        assert jb.verdict(16.7) == jb.Z_NARROW

    def test_only_a_record_beyond_the_swept_reach_is_branch_z(self):
        assert jb.verdict(16.71) == jb.BRANCH_Z
        assert jb.verdict(100.0) == jb.BRANCH_Z

    def test_the_three_verdicts_are_distinct_strings(self):
        assert len({jb.BRANCH_N, jb.Z_NARROW, jb.BRANCH_Z}) == 3

    def test_an_empty_population_yields_no_verdict_rather_than_closure(self):
        # A verdict over no rows would declare the project's central question
        # CLOSED on an empty pull, which is the failure the D-gate exists for.
        assert jb.verdict(jb.d_star_points([])) is None

    def test_the_verdict_agrees_with_the_k_reading_away_from_the_boundary(self):
        for d_star in (0.0, 1.0, 3.0, 5.0, 12.0, 20.0, 50.0):
            shortfalls = [d_star * 10.0]
            closed_by_k = jb.k_at_delta(shortfalls, jb.D_SWEPT_POINTS) == 0
            assert (jb.verdict(d_star) == jb.BRANCH_Z) == closed_by_k

    def test_at_the_exact_threshold_the_narrower_verdict_wins(self):
        # The one point where the `D* > 16.7` and `K(16.70) = 0` readings differ.
        # §A6 registers the direction: more UNRESOLVED, never a false
        # declaration.
        assert jb.k_at_delta([167.0], jb.D_SWEPT_POINTS) == 0  # K says closed
        assert jb.verdict(16.7) == jb.Z_NARROW  # the verdict does not


class TestTheKnobCeilingIsPrintedBesideDStar:
    """§A3: the comparison that makes Branch Z's strongest sentence free."""

    def test_the_whole_fee_and_maker_knob_is_worth_at_most_two_points(self):
        # 20 tenths in the middle band, 10 in the wings (§C4), so 2.0 points.
        assert jb.KNOB_CEILING_POINTS == 2.0
        worst = max(
            1000.0
            * (
                jb.basis_effective_price_dollars(jb.ALT_0, p)
                - (p / 1000.0)  # the stacked generous price: a zero fee (§C3)
            )
            for p in range(1, 1000)
        )
        assert worst / 10.0 == pytest.approx(jb.KNOB_CEILING_POINTS)


class TestAnAskOneTenthBelowItsFairClears:
    """§5's reachability check, and the harness's own smoke test.

    §7 makes this a precondition: a bound that returns zero at every rung is
    indistinguishable from a bound that returns zero always. So the harness must
    be shown to return `K >= 1` on a constructed row before any branch is read.
    """

    def test_a_row_one_tenth_below_its_fair_clears_at_every_rung(self):
        row = make_row(fair_probability=0.500, ask_tenths=499)
        assert jb.primary_shortfall_tenths(row) == pytest.approx(-1.0)
        for points, _ in jb.DELTA_LADDER:
            assert jb.k_at_delta([jb.primary_shortfall_tenths(row)], points) == 1

    def test_a_row_one_tenth_above_its_fair_clears_at_no_rung_below_its_shortfall(self):
        row = make_row(fair_probability=0.500, ask_tenths=501)
        s = jb.primary_shortfall_tenths(row)
        assert s == pytest.approx(1.0)
        assert jb.k_at_delta([s], 0.00) == 0
        assert jb.k_at_delta([s], 0.18) == 1

    def test_the_ladder_reaches_a_row_it_was_built_to_reach(self):
        # The 10.00 rung exists so that `K = 0` at 5.00 can be read against a
        # rung where `K` is certainly non-zero if the arithmetic works at all.
        row = make_row(fair_probability=0.40, ask_tenths=490)  # S = +90 tenths
        ladder = jb.k_ladder([row])
        assert ladder[5.00][0] == 0
        assert ladder[jb.REACHABILITY_DELTA_POINTS][0] == 1


class TestKIsMonotone:
    """§7: monotone in delta and along the population nesting, by construction."""

    def test_k_is_non_decreasing_along_the_delta_ladder(self):
        rows = [
            make_row(id=i, ask_tenths=500, fair_probability=f)
            for i, f in enumerate((0.60, 0.50, 0.4999, 0.498, 0.45, 0.30), start=1)
        ]
        ladder = jb.k_ladder(rows)
        assert jb.k_ladder_monotonicity_violations(ladder) == []
        counts = [ladder[p][0] for p, _ in jb.DELTA_LADDER]
        assert counts == sorted(counts)

    def test_a_decreasing_ladder_is_reported_as_a_violation(self):
        # The detector must be able to see the thing it exists for.
        broken = {0.00: (5, 1), 0.18: (2, 1), 2.03: (2, 1), 5.00: (3, 1), 10.00: (9, 1)}
        assert len(jb.k_ladder_monotonicity_violations(broken)) == 1

    def test_k_is_non_increasing_along_the_population_nesting(self):
        rows = [
            make_row(id=1, fair_probability=0.60, suppressed_reason=None),
            make_row(id=2, fair_probability=0.60, suppressed_reason="stale_odds"),
            make_row(id=3, fair_probability=0.60, suppressed_reason="wide_market"),
        ]
        pops = jb.populations(rows)
        ladders = {name: jb.k_ladder(members) for name, members in pops.items()}
        assert jb.population_monotonicity_violations(ladders) == []
        assert ladders["P0"][0.00][0] == 3
        assert ladders["P1"][0.00][0] == 1  # only the unsuppressed row
        assert ladders["P2"][0.00][0] == 2  # everything but the stale one
        assert ladders["P3"][0.00][0] == 1

    def test_a_subpopulation_counting_more_than_its_parent_is_reported(self):
        broken = {
            "P0": {p: (1, 1) for p, _ in jb.DELTA_LADDER},
            "P1": {p: (7, 1) for p, _ in jb.DELTA_LADDER},
        }
        assert jb.population_monotonicity_violations(broken) != []


class TestTheFreshnessPredicateMatchesTokensNotSubstrings:
    """Lane A §2 defect D1, in its only permitted Python form.

    A `LIKE`-shaped or substring-shaped implementation fails these. That is the
    point of the cases chosen: each one is an answer a wrong implementation gets
    **differently**, not merely an answer it also gets right.
    """

    def test_a_bare_stale_odds_row_is_stale(self):
        assert not jb.is_fresh("stale_odds")

    def test_a_composite_containing_stale_odds_is_stale(self):
        # 27.8% of stale rows are composites [Lane A §0.1]. An equality test on
        # the whole string calls this fresh and silently keeps a stale row.
        assert not jb.is_fresh("stale_odds,wide_market")
        assert not jb.is_fresh("wide_market,stale_odds")
        assert not jb.is_fresh("wide_market,stale_odds,thin_depth")

    def test_a_longer_code_sharing_the_prefix_is_NOT_stale(self):
        # `stale_odds_upstream` is a different code. A substring test -- and
        # SQLite `LIKE '%stale_odds%'` -- calls it stale and drops a fresh row.
        assert jb.is_fresh("stale_odds_upstream")
        assert jb.is_fresh("wide_market,stale_odds_upstream")

    def test_an_underscore_wildcard_cannot_reach_a_different_code(self):
        # SQLite `LIKE` reads `_` as a single-character wildcard and all
        # fourteen suppression codes contain underscores, so `LIKE 'stale_odds'`
        # would also match `staleXodds`. Token matching cannot.
        assert jb.is_fresh("staleXodds")

    def test_no_suppression_at_all_is_fresh(self):
        assert jb.is_fresh(None)
        assert jb.is_fresh("")


class TestTheClusterKeyDropsASegmentNotACharacterCount:
    """§3 / Lane A §4's HTTP fallback, on real tickers from `tests/fixtures/`."""

    def test_a_three_segment_market_ticker_drops_its_last_segment(self):
        assert (
            jb.cluster_key("KXMLBGAME-26AUG09DETSEA-SEA") == "KXMLBGAME-26AUG09DETSEA"
        )

    def test_a_two_segment_event_ticker_is_left_alone(self):
        # An "always drop the last segment" implementation returns `KXATPMATCH`
        # here and collapses an entire series into one cluster, inflating
        # nothing and destroying everything.
        assert jb.cluster_key("KXATPMATCH-26AUG09FONSHE") == "KXATPMATCH-26AUG09FONSHE"

    def test_no_fixed_character_count_can_produce_both_real_keys(self):
        # The previous project's bug, and the anchor of this whole class: two
        # real tickers whose correct keys are 23 and 25 characters long. Any
        # `ticker[:N]` agrees with at most one of them.
        short = jb.cluster_key("KXMLBGAME-26AUG09DETSEA-SEA")
        long = jb.cluster_key("KXCFLSPREAD-26AUG08EDMMTL-EDM14")
        assert (len(short), len(long)) == (23, 25)
        assert short == "KXMLBGAME-26AUG09DETSEA"
        assert long == "KXCFLSPREAD-26AUG08EDMMTL"

    def test_every_leg_of_one_real_event_collapses_to_one_cluster(self, fixtures_dir):
        # 12 spread legs on one CFL game, straight off a captured payload. This
        # is the correlation the cluster key exists to collapse.
        legs = {
            t
            for t in fixture_tickers(fixtures_dir)
            if t.startswith("KXCFLSPREAD-26AUG08EDMMTL-")
        }
        assert len(legs) >= 10
        assert {jb.cluster_key(t) for t in legs} == {"KXCFLSPREAD-26AUG08EDMMTL"}

    def test_every_real_ticker_yields_a_key_that_is_a_prefix_of_itself(
        self, fixtures_dir
    ):
        tickers = fixture_tickers(fixtures_dir)
        assert len(tickers) > 500
        for ticker in tickers:
            key = jb.cluster_key(ticker)
            assert ticker.startswith(key), ticker

    def test_real_two_and_three_segment_tickers_are_both_present_in_the_fixtures(
        self, fixtures_dir
    ):
        # Without both shapes on the wire, the two branches above are untested
        # against reality and the fallback is being checked on invented input.
        tickers = fixture_tickers(fixtures_dir)
        assert sum(1 for t in tickers if t.count("-") == 1) > 100
        assert sum(1 for t in tickers if t.count("-") == 2) > 100

    def test_the_sql_event_ticker_wins_over_the_fallback_when_present(self):
        assert (
            jb.cluster_key("KXMLBGAME-26AUG09DETSEA-SEA", "KXMLBGAME-26AUG09DETSEA")
            == "KXMLBGAME-26AUG09DETSEA"
        )

    def test_the_gate_still_clusters_on_the_key_this_harness_mirrors(self):
        # Importing the module is the assertion: `joint_bound` refuses to import
        # if `gate.clustered_clv` stops using `COALESCE(m.event_ticker,
        # r.ticker)`. Re-stated here so the reason is discoverable from the
        # tests rather than only from an ImportError at 3am.
        import inspect

        from backend import gate

        assert jb._GATE_CLUSTER_KEY_SQL in inspect.getsource(gate.clustered_clv)

    def test_the_cluster_count_is_games_not_rows(self):
        rows = [
            make_row(id=1, ticker="KXMLBGAME-26AUG09DETSEA-SEA"),
            make_row(id=2, ticker="KXMLBGAME-26AUG09DETSEA-DET"),
            make_row(id=3, ticker="KXMLBGAME-26AUG09DETSEA-SEA"),
            make_row(id=4, ticker="KXATPMATCH-26AUG09FONSHE"),
        ]
        assert len(rows) == 4
        assert jb.cluster_count(rows) == 2


class TestThePopulationsNest:
    """§2's four nested populations, and the invariant asserted before any count."""

    def test_p0_admits_a_tradeable_ask_and_a_non_null_fair(self):
        assert jb.in_p0(make_row(ask_tenths=10))
        assert jb.in_p0(make_row(ask_tenths=989))

    def test_p0_excludes_an_ask_outside_the_registered_range(self):
        # 0 and 1000 are settled outcomes, not quotes, and `effective_price`
        # raises rather than pricing one at a zero fee -- which would fabricate
        # an edge of +55c out of nothing.
        assert not jb.in_p0(make_row(ask_tenths=9))
        assert not jb.in_p0(make_row(ask_tenths=990))
        assert jb.exclusion_reason(make_row(ask_tenths=9)) == "ask_outside_10_989"

    def test_p0_excludes_and_names_a_null_fair(self):
        assert jb.exclusion_reason(make_row(fair_probability=None)) == (
            "fair_probability_null"
        )

    def test_an_included_row_has_no_exclusion_reason(self):
        assert jb.exclusion_reason(make_row()) is None

    def test_the_four_populations_nest(self):
        rows = [
            make_row(id=1, suppressed_reason=None),
            make_row(id=2, suppressed_reason="stale_odds"),
            make_row(id=3, suppressed_reason="wide_market"),
            make_row(id=4, suppressed_reason="stale_odds,wide_market"),
            make_row(id=5, ask_tenths=1000),
        ]
        pops = jb.populations(rows)
        assert [r.id for r in pops["P0"]] == [1, 2, 3, 4]
        assert [r.id for r in pops["P1"]] == [1]
        assert [r.id for r in pops["P2"]] == [1, 3]
        assert [r.id for r in pops["P3"]] == [1]
        assert jb.nesting_violations(pops) == []

    def test_a_broken_nesting_is_reported_rather_than_passed_over(self):
        rows = [make_row(id=1), make_row(id=2, suppressed_reason="wide_market")]
        pops = jb.populations(rows)
        pops["P3"] = list(pops["P0"])  # P3 must not exceed P1
        assert jb.nesting_violations(pops) != []


class TestTheExactBoundIsAUnionAndNeverAStack:
    """§5 / `partner`'s constraint 1, made structural rather than merely undone."""

    def test_the_stacked_basis_cannot_be_constructed(self):
        with pytest.raises(ValueError, match="STACK"):
            jb.FeeBasis(name="stack", fee_model="cheapest", maker=True, contracts=1)

    def test_alt_2_at_any_size_stays_on_the_max_fee_model(self):
        for n in (1, 10, 100):
            basis = jb.alt_2(n)
            assert (basis.fee_model, basis.maker, basis.contracts) == ("max", True, n)

    def test_alt_2_is_n_equals_one_with_n_equals_ten_as_the_labelled_secondary(self):
        # Amendment 1 §A2, and the exact inverse of the committed §5. `N=10`
        # rested on a minimum order size that `sizing.py:15` retired on
        # 2026-08-09, and the error ran in the flattering direction: the maker
        # saving at 50c is 10.0 tenths at N=1 and 15.0 at N=10.
        assert jb.ALT_2.contracts == 1
        assert jb.ALT_2_SECONDARY.contracts == 10
        saving_n1 = 1000 * (
            jb.basis_effective_price_dollars(jb.ALT_0, 500)
            - jb.basis_effective_price_dollars(jb.ALT_2, 500)
        )
        saving_n10 = 1000 * (
            jb.basis_effective_price_dollars(jb.ALT_0, 500)
            - jb.basis_effective_price_dollars(jb.ALT_2_SECONDARY, 500)
        )
        assert (saving_n1, saving_n10) == pytest.approx((10.0, 15.0))

    def test_the_three_registered_alternatives_price_as_measured(self):
        # Measured from the repository, not quoted: at 500 tenths the deployed
        # basis costs 520 tenths, the fee knob alone 520 (§C4 records the fee
        # knob is worth nothing at exactly 500), the maker knob alone 510 -- and
        # the stack would be 500.
        assert 1000 * jb.basis_effective_price_dollars(jb.ALT_0, 500) == pytest.approx(520.0)
        assert 1000 * jb.basis_effective_price_dollars(jb.ALT_1, 500) == pytest.approx(520.0)
        assert 1000 * jb.basis_effective_price_dollars(jb.ALT_2, 500) == pytest.approx(510.0)

    def test_a_row_only_the_stack_would_clear_does_NOT_clear(self):
        # THE anchor of this class. At 500 tenths with a loosest fair of 0.505:
        # ALT-1 is 15 tenths short, ALT-2 is 5 tenths short, and the stack would
        # clear by 5. A stacking implementation returns True here.
        row = make_row(
            ask_tenths=500,
            fair_probability=0.505,
            p_multiplicative=0.505,
            p_additive=0.50,
            p_power=0.49,
            p_shin=0.48,
            p_conservative=0.48,
        )
        assert jb.confirmatory_shortfall_tenths(row, jb.ALT_1) == pytest.approx(15.0)
        assert jb.confirmatory_shortfall_tenths(row, jb.ALT_2) == pytest.approx(5.0)
        assert jb.exact_bound_clears(row) is False

    def test_alt_2_alone_can_clear_a_row_alt_1_cannot(self):
        row = make_row(
            ask_tenths=500,
            fair_probability=0.515,
            p_multiplicative=0.515,
            p_additive=0.50,
            p_power=0.49,
            p_shin=0.48,
        )
        assert jb.confirmatory_shortfall_tenths(row, jb.ALT_1) == pytest.approx(5.0)
        assert jb.confirmatory_shortfall_tenths(row, jb.ALT_2) == pytest.approx(-5.0)
        assert jb.exact_bound_clears(row) is True

    def test_alt_1_alone_can_clear_a_row_alt_2_cannot(self):
        # At 10 tenths the ordering reverses: ALT-1 prices at 10.0 and ALT-2 at
        # 20.0, because Model B's taker fee rounds to zero on a cheap contract
        # while Model A's maker fee still rounds up to a whole cent per order.
        row = make_row(
            ask_tenths=10,
            fair_probability=0.015,
            p_multiplicative=0.015,
            p_additive=0.010,
            p_power=0.009,
            p_shin=0.008,
        )
        assert jb.confirmatory_shortfall_tenths(row, jb.ALT_1) == pytest.approx(-5.0)
        assert jb.confirmatory_shortfall_tenths(row, jb.ALT_2) == pytest.approx(5.0)
        assert jb.exact_bound_clears(row) is True

    def test_the_confirmatory_uses_the_loosest_of_the_four_not_the_conservative(self):
        row = make_row(
            ask_tenths=500,
            fair_probability=0.38,
            p_multiplicative=0.52,
            p_additive=0.45,
            p_power=0.41,
            p_shin=0.38,
        )
        assert jb.loosest_fair(row) == pytest.approx(0.52)
        # ALT-0 at 500 costs 520 tenths, so a loosest fair of 0.52 is exactly flat.
        assert jb.confirmatory_shortfall_tenths(row, jb.ALT_0) == pytest.approx(0.0)

    def test_a_missing_method_drops_the_row_rather_than_imputing_it(self):
        # `p_shin` is NULL where the root-finder fell back (`devig.py:181`), and
        # `max` over three methods is a different estimator from `max` over four.
        row = make_row(
            p_multiplicative=0.52, p_additive=0.45, p_power=0.41, p_shin=None
        )
        assert jb.loosest_fair(row) is None
        assert jb.confirmatory_shortfall_tenths(row, jb.ALT_0) is None
        assert jb.exact_bound_clears(row) is None

    def test_the_primary_shortfall_is_the_alt_shortfall_at_a_zero_fee(self):
        # The one place the two code paths could drift. The stacked generous
        # basis has no `FeeBasis` by construction, so the identity is asserted
        # against a hand-built zero-fee price rather than against a basis
        # object: `S` must equal `1000*ask/1000 - 1000*fair` exactly.
        row = make_row(ask_tenths=437, fair_probability=0.4211)
        assert jb.primary_shortfall_tenths(row) == pytest.approx(437 - 421.1)
        # And it is strictly cheaper than every realisable alternative, which is
        # what makes it a dominating bound rather than an estimate.
        for basis in (jb.ALT_0, jb.ALT_1, jb.ALT_2):
            assert jb.primary_alt_shortfall_tenths(row, basis) >= (
                jb.primary_shortfall_tenths(row)
            )

    def test_the_alt_shortfall_carries_the_ladder_identity_unchanged(self):
        # Adding delta to the fair and subtracting 10*delta from the shortfall
        # are the same move, which is why Branch M reads the same ladder.
        row = make_row(ask_tenths=400, fair_probability=0.40)
        s = jb.primary_alt_shortfall_tenths(row, jb.ALT_2)
        assert s == pytest.approx(10.0)
        assert jb.k_at_delta([s], 0.18) == 0
        assert jb.k_at_delta([s], 2.03) == 1

    def test_an_untradeable_ask_is_refused_on_every_basis(self):
        for basis in (jb.ALT_0, jb.ALT_1, jb.ALT_2):
            with pytest.raises(ValueError):
                jb.basis_effective_price_dollars(basis, 1000)


class TestThePerKnobSavingsReproduceTheRegisteredTable:
    """§C4 / §S2 item 10: `E1min - E1 == Delta(price)`, an assertable invariant."""

    def test_the_fee_and_maker_knob_deltas_match_the_registered_bands(self):
        assert jb.fee_knob_delta_violations() == []

    def test_the_registered_bands_cover_every_tradeable_price_exactly_once(self):
        for bands in (jb.FEE_KNOB_DELTA_BANDS, jb.MAKER_KNOB_DELTA_BANDS):
            covered = [p for low, high, _ in bands for p in range(low, high + 1)]
            assert covered == list(range(1, 1000))

    def test_the_maker_band_edges_are_the_exact_ones_not_the_rounded_ones(self):
        # ADR 0017 §1's "18c-82c" would mislabel 14 prices. The saving is 10.0
        # tenths on exactly [173, 827] and 0.0 outside it.
        assert jb.MAKER_BAND_TENTHS == (173, 827)
        assert not jb.in_maker_band(172)
        assert jb.in_maker_band(173)
        assert jb.in_maker_band(827)
        assert not jb.in_maker_band(828)

    def test_the_band_detector_can_see_a_wrong_band(self):
        # The control: perturbing one band by one price must be caught, or the
        # invariant above is checking nothing.
        broken = ((1, 91, 10.0), (92, 172, 10.0), (173, 999, 10.0))
        violations = jb._band_violations(
            broken,
            lambda p: 1000.0
            * (
                jb.basis_effective_price_dollars(jb.ALT_0, p)
                - jb.basis_effective_price_dollars(jb.ALT_1, p)
            ),
            "control",
        )
        # Every price where the real saving is 0.0: [92,172], the 500
        # singleton, and [828,908]. 163 of the 999.
        assert len(violations) == 81 + 1 + 81


class TestTheP5JoinInvariant:
    """§P5 / Lane B §C2: `p_conservative == min(four) == fair_probability`."""

    def test_a_consistent_row_reports_no_violation(self):
        row = make_row(
            fair_probability=0.38,
            p_multiplicative=0.52,
            p_additive=0.45,
            p_power=0.41,
            p_shin=0.38,
            p_conservative=0.38,
        )
        assert jb.p5_violations([row]) == []

    def test_a_conservative_that_is_not_the_minimum_is_reported(self):
        row = make_row(
            fair_probability=0.45,
            p_multiplicative=0.52,
            p_additive=0.45,
            p_power=0.41,
            p_shin=0.38,
            p_conservative=0.45,
        )
        assert jb.p5_violations([row]) != []

    def test_a_fair_that_disagrees_with_the_conservative_is_reported(self):
        # This is the check that the `fair_price_id` join landed on the right row.
        row = make_row(
            fair_probability=0.50,
            p_multiplicative=0.52,
            p_additive=0.45,
            p_power=0.41,
            p_shin=0.38,
            p_conservative=0.38,
        )
        assert jb.p5_violations([row]) != []

    def test_a_row_with_no_methods_joined_is_skipped_not_flagged(self):
        assert jb.p5_violations([make_row()]) == []


class TestTheShortfallHistogram:
    """§5's eight cells, left-open right-closed, sharing three edges with the ladder."""

    def test_there_are_exactly_eight_cells(self):
        assert len(jb.SHORTFALL_CELLS) == 8

    def test_the_cells_partition_the_line_with_no_gap_and_no_overlap(self):
        edges = [high for _, high in jb.SHORTFALL_CELLS]
        lows = [low for low, _ in jb.SHORTFALL_CELLS]
        assert lows[0] == -math.inf and edges[-1] == math.inf
        assert lows[1:] == edges[:-1]

    def test_every_value_lands_in_exactly_one_cell(self):
        values = [-1e9, -1.0, 0.0, 0.001, 10.0, 20.3, 50.0, 100.0, 200.0, 400.0, 1e9]
        counts = jb.shortfall_histogram(values)
        assert sum(counts.values()) == len(values)

    def test_a_boundary_value_falls_in_the_lower_cell_because_cells_are_right_closed(
        self,
    ):
        # 20.3 belongs to (10, 20.3], not to (20.3, 50]. A left-closed
        # implementation puts it in the higher cell and disagrees with `K`,
        # which uses a strict `<` at the same edge.
        counts = jb.shortfall_histogram([20.3])
        assert counts[(10.0, 20.3)] == 1
        assert counts[(20.3, 50.0)] == 0

    def test_the_cell_edges_are_the_delta_ladder_read_the_other_way(self):
        ladder_tenths = {tenths for _, tenths in jb.DELTA_LADDER}
        cell_edges = {high for _, high in jb.SHORTFALL_CELLS}
        assert {0.0, 20.3, 100.0} <= ladder_tenths & cell_edges

    def test_the_histogram_and_k_agree_at_every_shared_edge(self):
        values = [-3.0, 0.0, 5.0, 15.0, 20.3, 30.0, 75.0, 150.0, 300.0, 900.0]
        counts = jb.shortfall_histogram(values)
        # K(0.00) counts everything strictly below 0, which is the first cell
        # minus the values exactly at 0.
        assert jb.k_at_delta(values, 0.00) == counts[(-math.inf, 0.0)] - 1
        assert jb.k_at_delta(values, 2.03) == (
            counts[(-math.inf, 0.0)] + counts[(0.0, 10.0)] + counts[(10.0, 20.3)] - 1
        )


class TestGridBIsImportedRatherThanRestated:
    """§5: reused so it cannot be re-chosen."""

    def test_grid_b_is_the_validate_module_object_itself(self):
        assert jb.GRID_B is BUCKETS

    def test_grid_b_buckets_on_the_ask_left_closed_right_open(self):
        assert jb.grid_b_bucket(100) == (100, 200)
        assert jb.grid_b_bucket(199) == (100, 200)
        assert jb.grid_b_bucket(200) == (200, 300)

    def test_a_price_outside_grid_b_returns_none_rather_than_a_nearest_bucket(self):
        assert jb.grid_b_bucket(9) is None
        assert jb.grid_b_bucket(995) is None


class TestPercentilesNameRowsThatExist:
    """§6's nine readouts, by nearest rank."""

    def test_the_block_carries_exactly_the_registered_nine_keys(self):
        block = jb.percentile_block([1.0, 2.0, 3.0])
        assert list(block) == [
            "min", "p1", "p5", "p10", "p25", "p50", "p75", "p90", "max"
        ]

    def test_min_and_max_are_the_extreme_observations(self):
        values = [5.0, -2.0, 17.0, 3.0]
        block = jb.percentile_block(values)
        assert block["min"] == -2.0
        assert block["max"] == 17.0

    def test_every_reported_quantile_is_an_observed_value(self):
        # Nearest rank, not interpolation: the headline sentence names *the
        # nearest row*, so a quantile describing a row that does not exist would
        # be a number with no row behind it.
        values = [1.0, 2.0, 4.0, 8.0, 16.0]
        block = jb.percentile_block(values)
        assert all(v in values for v in block.values())

    def test_the_median_of_a_hundred_values_is_the_fiftieth(self):
        assert jb.percentile_block([float(i) for i in range(1, 101)])["p50"] == 50.0

    def test_an_empty_population_yields_none_rather_than_zero(self):
        assert all(v is None for v in jb.percentile_block([]).values())


class TestTheBankrollEra:
    """Lane A §3's three mechanical levels. `boundary` is unassignable, not `pre`."""

    def test_a_row_before_the_commit_instant_is_pre(self):
        assert jb.bankroll_era(jb.BANKROLL_ERA_COMMIT_MS - 1) == "pre"

    def test_the_commit_instant_itself_is_boundary_not_pre(self):
        # A `>` instead of `>=` puts this row in `pre` and assigns a row that is
        # unassignable to the $1,000 era.
        assert jb.bankroll_era(jb.BANKROLL_ERA_COMMIT_MS) == "boundary"

    def test_the_last_boundary_millisecond_is_boundary(self):
        assert jb.bankroll_era(jb.BANKROLL_ERA_SETTLED_MS - 1) == "boundary"

    def test_the_settled_instant_itself_is_post(self):
        assert jb.bankroll_era(jb.BANKROLL_ERA_SETTLED_MS) == "post"

    def test_a_row_with_no_timestamp_is_unknown_not_pre(self):
        assert jb.bankroll_era(None) == "unknown"


class TestTheRuleOfThree:
    """The one inferential quantity in the whole design, and it is weak."""

    def test_the_bound_at_the_records_own_cluster_count(self):
        assert jb.rule_of_three(29) == pytest.approx(0.1034, abs=1e-4)

    def test_the_bound_reproduces_the_registered_table(self):
        for g, expected in ((60, 0.05), (100, 0.03), (300, 0.01), (1000, 0.003)):
            assert jb.rule_of_three(g) == pytest.approx(expected)

    def test_zero_clusters_yields_none_rather_than_infinity(self):
        assert jb.rule_of_three(0) is None


class TestTheRowReadsTheLedgerPayloadsOwnFieldNames:
    """§F8: the payload names the price `ask_tenths`, not `entry_ask_tenths`."""

    def test_the_ask_is_read_from_ask_tenths(self):
        row = jb.Row.from_ledger_payload(
            {"id": 7, "ticker": "KXMLBGAME-26AUG09DETSEA-SEA",
             "ask_tenths": 512, "fair_probability": 0.5, "suppressed_reason": None}
        )
        assert row.ask_tenths == 512

    def test_an_absent_field_resolves_to_none_rather_than_zero(self):
        row = jb.Row.from_ledger_payload({"id": 8})
        assert row.ask_tenths is None
        assert row.fair_probability is None
        assert row.p_shin is None
        assert not jb.in_p0(row)

    def test_the_four_devig_methods_are_read_when_the_join_supplied_them(self):
        row = jb.Row.from_ledger_payload(
            {"id": 9, "p_multiplicative": 0.5, "p_additive": 0.49,
             "p_power": 0.48, "p_shin": 0.47, "p_conservative": 0.47}
        )
        assert jb.loosest_fair(row) == pytest.approx(0.5)

    def test_a_payload_captured_as_json_round_trips(self):
        payload = json.loads(
            '{"id": 10, "ticker": "KXATPMATCH-26AUG09FONSHE", "ask_tenths": 305,'
            ' "fair_probability": 0.31, "suppressed_reason": "stale_odds,wide_market"}'
        )
        row = jb.Row.from_ledger_payload(payload)
        assert jb.in_p0(row)
        assert not jb.is_fresh(row.suppressed_reason)
        assert jb.cluster_key(row.ticker) == "KXATPMATCH-26AUG09FONSHE"
