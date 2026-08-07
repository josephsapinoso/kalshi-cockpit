"""Suppression tests.

Every test here asserts that something gets *rejected*. That is the point of
the module: the governing rule is that a large apparent edge is a bug until
proven otherwise, and these are the specific ways an apparent edge turns out
to be a defect.
"""

from __future__ import annotations

import pytest

from backend.core.suppression import SuppressionConfig, evaluate_suppression

CONFIG = SuppressionConfig()


def check(**overrides):
    """A candidate that passes every check, so a test can break exactly one."""
    args = dict(
        config=CONFIG,
        kalshi_quote_age_ms=5_000,
        odds_age_ms=120_000,
        commence_skew_ms=60_000,
        depth_at_ask=200.0,
        contracts=25,
        market_width=0.01,
        book_count=4,
        edge_tenths=20.0,
        method_spread_probability=0.002,
    )
    args.update(overrides)
    return evaluate_suppression(**args)


class TestBaseline:
    def test_a_clean_candidate_passes(self):
        result = check()
        assert not result.suppressed, result.detail
        assert result.reason is None


class TestFreshness:
    def test_a_stale_kalshi_quote_suppresses(self):
        result = check(kalshi_quote_age_ms=120_000)
        assert result.suppressed
        assert "stale_kalshi_quote" in result.reason

    def test_a_stale_book_suppresses(self):
        """A book that has not repriced in an hour is stale even if we fetched
        it a second ago."""
        result = check(odds_age_ms=3_600_000)
        assert "stale_odds" in result.reason


class TestIdentity:
    def test_a_large_commence_skew_suppresses(self):
        """Two fixtures sharing teams produce an edge from nothing."""
        result = check(commence_skew_ms=8 * 3_600_000)
        assert "commence_skew" in result.reason

    def test_a_missing_commence_time_suppresses(self):
        result = check(commence_skew_ms=None)
        assert "no_commence_time" in result.reason


class TestFillability:
    def test_insufficient_depth_suppresses(self):
        """An edge you cannot fill is not an edge."""
        result = check(depth_at_ask=3.0, contracts=25)
        assert "insufficient_depth" in result.reason

    def test_no_quoted_size_suppresses(self):
        result = check(depth_at_ask=None)
        assert "no_depth" in result.reason

    def test_depth_must_cover_the_order_not_just_the_minimum(self):
        result = check(depth_at_ask=12.0, contracts=50)
        assert "insufficient_depth" in result.reason


class TestConsensusQuality:
    def test_a_single_book_is_not_a_consensus(self):
        result = check(book_count=1)
        assert "too_few_books" in result.reason

    def test_a_wide_market_suppresses(self):
        """When books disagree widely, the fair line is untrustworthy."""
        result = check(market_width=0.20)
        assert "wide_market" in result.reason


class TestTheEdgeItself:
    """The two checks that make this project's stance concrete."""

    def test_an_edge_inside_the_devig_method_spread_suppresses(self):
        """Falls directly out of the measurement: the four methods spread
        ~0.18 points on an even line and ~2.03 on a longshot. An edge smaller
        than that spread is a statement about method choice, not the market."""
        result = check(edge_tenths=5.0, method_spread_probability=0.02)  # 20 tenths
        assert "edge_within_method_noise" in result.reason

    def test_an_edge_clearing_the_method_spread_survives(self):
        result = check(edge_tenths=25.0, method_spread_probability=0.002)
        assert "edge_within_method_noise" not in (result.reason or "")

    def test_a_negative_edge_is_not_a_suppression(self):
        """"No edge here" is the normal answer on most candidates, not a
        defect. Firing a suppression on it would bury the genuine diagnostics
        under the majority case and make the summary useless."""
        result = check(edge_tenths=-40.0, method_spread_probability=0.002)
        assert not result.suppressed, result.detail

    def test_a_large_edge_is_treated_as_a_defect(self):
        """Kalshi prices to ~2c against 13 sub-200ms market makers. It does not
        leave 6c lying around."""
        result = check(edge_tenths=60.0)
        assert "suspicious_edge" in result.reason

    def test_the_ceiling_message_names_the_likely_causes(self):
        """The suppression log is a work queue. It must say what to look at."""
        result = check(edge_tenths=60.0)
        assert "stale quote" in result.detail
        assert "wrong fixture" in result.detail


class TestReporting:
    """The suppression log is analysable data, not a bin."""

    def test_all_failures_are_reported_not_just_the_first(self):
        """A row suppressed for staleness that was ALSO mis-matched needs both
        facts, and the second matters more."""
        result = check(kalshi_quote_age_ms=120_000, commence_skew_ms=8 * 3_600_000)
        assert "stale_kalshi_quote" in result.reason
        assert "commence_skew" in result.reason

    def test_every_check_runs_even_when_one_fails(self):
        clean = check()
        broken = check(kalshi_quote_age_ms=999_999)
        assert len(broken.checks) == len(clean.checks)

    def test_detail_is_human_readable_with_the_actual_numbers(self):
        result = check(market_width=0.20)
        assert "20.0 points" in result.detail

    def test_a_passing_candidate_has_no_reason(self):
        assert check().reason is None


class TestConfigIsTheFlywheelsUnit:
    """Thresholds are versioned config, so loosening one is measurable."""

    def test_thresholds_can_be_loosened_for_a_specific_run(self):
        loose = SuppressionConfig(edge_ceiling_tenths=200.0)
        result = evaluate_suppression(
            config=loose,
            kalshi_quote_age_ms=5_000, odds_age_ms=120_000,
            commence_skew_ms=0, depth_at_ask=500.0, contracts=10,
            market_width=0.01, book_count=4,
            edge_tenths=60.0, method_spread_probability=0.002,
        )
        assert "suspicious_edge" not in (result.reason or "")

    def test_defaults_are_conservative(self):
        """The ceiling must sit above Kalshi's ~2c pricing accuracy but well
        below anything that would be genuinely free money."""
        assert 20.0 <= CONFIG.edge_ceiling_tenths <= 60.0
        assert CONFIG.min_book_count >= 2


class TestTheTwoCommenceLimitsAgree:
    """Two limits on one quantity, in two modules. The tighter wins silently.

    `match.linker.DEFAULT_COMMENCE_TOLERANCE_MS` decides whether two fixtures
    *are* the same game; `SuppressionConfig.max_commence_skew_ms` decides whether
    we are confident enough to bet on the match. Nothing connects them, and when
    they disagreed the result was invisible: the linker matched 19 fixtures on a
    live slate and suppression rejected all 76 resulting candidates for
    `commence_skew`. The stage counts showed work being done at every step and
    nothing surviving.
    """

    def test_suppression_is_not_tighter_than_the_linker(self):
        """Otherwise suppression silently overrides matching entirely."""
        from backend.match.linker import DEFAULT_COMMENCE_TOLERANCE_MS

        assert (
            SuppressionConfig().max_commence_skew_ms
            >= DEFAULT_COMMENCE_TOLERANCE_MS
        ), (
            "suppression rejects every fixture the linker accepts at the top of "
            "its window -- the linker's tolerance becomes decorative"
        )

    def test_the_limit_clears_the_observed_kalshi_offset(self):
        """A limit below a systematic offset is an off switch, not a control."""
        from backend.match.linker import OBSERVED_KALSHI_COMMENCE_OFFSET_MS

        assert (
            SuppressionConfig().max_commence_skew_ms
            > OBSERVED_KALSHI_COMMENCE_OFFSET_MS
        )

    def test_a_genuinely_different_fixture_is_still_rejected(self):
        """Widening must not turn the check off.

        A day-later game in the same series shares both teams and is exactly
        what this check exists to catch.
        """
        result = evaluate_suppression(
            config=SuppressionConfig(),
            kalshi_quote_age_ms=1_000,
            odds_age_ms=60_000,
            commence_skew_ms=24 * 3_600_000,
            depth_at_ask=500.0,
            contracts=10,
            market_width=0.01,
            book_count=6,
            edge_tenths=25.0,
            method_spread_probability=0.004,
        )
        assert result.suppressed
        assert "commence_skew" in result.reason
