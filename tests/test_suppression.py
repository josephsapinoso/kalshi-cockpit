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


class TestAnUnmeasurableWidthRefuses:
    """`market_width is None` must reject, not sail through.

    It arrived as `0.0` before, which passed the `<= 0.06` comparison trivially.
    So a consensus built from a single book -- the least evidence the system can
    act on -- cleared the check designed to catch untrustworthy consensus.
    """

    def _evaluate(self, *, market_width, book_count=5):
        return evaluate_suppression(
            config=SuppressionConfig(),
            kalshi_quote_age_ms=1_000,
            odds_age_ms=60_000,
            commence_skew_ms=0,
            depth_at_ask=500.0,
            contracts=10,
            market_width=market_width,
            book_count=book_count,
            edge_tenths=25.0,
            method_spread_probability=0.004,
        )

    def test_none_is_suppressed(self):
        result = self._evaluate(market_width=None)
        assert result.suppressed
        assert "no_market_width" in result.reason

    def test_a_measured_zero_still_passes(self):
        """The pair that discriminates.

        Two books quoting identically is real agreement and must not be
        punished. If this and the test above ever agree, the two states have
        been collapsed back into one and the bug is back.
        """
        assert not self._evaluate(market_width=0.0).suppressed

    def test_the_two_failures_are_named_differently(self):
        """"Books disagree" and "there was no second book" need different fixes.

        A suppression log that calls both `wide_market` cannot tell you whether
        to distrust the consensus or to go and find more books.
        """
        unmeasurable = self._evaluate(market_width=None)
        wide = self._evaluate(market_width=0.30)

        assert "no_market_width" in unmeasurable.reason
        assert "wide_market" not in unmeasurable.reason
        assert "wide_market" in wide.reason
        assert "no_market_width" not in wide.reason

    def test_the_detail_says_why_it_could_not_be_measured(self):
        detail = self._evaluate(market_width=None).detail
        assert "fewer than two books" in detail


class TestTheAgreementFamilyIsBlindToCorrelatedGarbage:
    """ADR 0019. Three guards read agreement; none can see a copied line.

    `edge_within_method_noise`, `no_market_width`/`wide_market` and
    `too_few_books` all ask some version of "do the sources concur?". Placeholder
    lines concur perfectly, so the whole family is blind to them at once, and a
    fourth agreement check could not fix it.

    These tests document **reachability**, not occurrence. Whether such a row
    exists in the live record is a separate census -- see ADR 0019.
    """

    @staticmethod
    def _consensus(quotes_by_book):
        from backend.core.devig import consensus_devig

        consensus, metadata = consensus_devig(
            ["home", "away"], quotes_by_book
        )
        return consensus, metadata

    def test_one_book_on_a_symmetric_line_is_caught_by_book_count(self):
        """The observed live case, and it IS suppressed -- twice."""
        consensus, metadata = self._consensus({"A": [1.85, 1.85]})

        result = check(
            market_width=metadata["market_width"],
            book_count=metadata["book_count"],
            edge_tenths=20.0,
            method_spread_probability=consensus.method_spread("home"),
        )

        assert result.suppressed
        assert "too_few_books" in result.reason
        assert "no_market_width" in result.reason

    def test_two_books_on_a_symmetric_line_are_caught_by_NOTHING(self):
        """`min_book_count = 2` does not bound the degenerate fair.

        NEXT.md recorded the defect as "all single-book, 0 unsuppressed", which
        is a fact about rows *observed*. It is not a fact about what the guards
        *permit*. This is the row they permit.
        """
        consensus, metadata = self._consensus(
            {"A": [1.85, 1.85], "B": [1.85, 1.85]}
        )

        assert metadata["book_count"] == 2
        assert metadata["market_width"] == 0.0
        assert consensus.conservative_probability("home") == pytest.approx(
            0.5, abs=1e-12
        )

        result = check(
            market_width=metadata["market_width"],
            book_count=metadata["book_count"],
            edge_tenths=20.0,
            method_spread_probability=consensus.method_spread("home"),
        )

        assert not result.suppressed
        assert result.reason is None

    def test_the_width_check_cannot_see_a_hold_difference_on_a_symmetric_line(self):
        """Multiplicative devig of a symmetric line is 0.5 regardless of hold.

        Implied probabilities are both `1/o`, booksum `2/o`, so `(1/o)/(2/o)`
        is exactly 0.5 for every `o`. Two books therefore agree perfectly on
        `multiplicative[0]` -- which is what `market_width` measures -- even
        when one charges 33% vig and the other 2.6%.

        So this `0.0` is a *legitimately measured* zero, and the
        `Optional`-not-zero fix that rescued the one-book case cannot reach it.
        """
        from backend.core.devig import devig

        holds = {}
        for odds in (1.50, 1.85, 1.95):
            result = devig(["home", "away"], [odds, odds])
            holds[odds] = result.overround
            assert result.multiplicative[0] == 0.5

        # The holds really are wildly different; the width check sees none of it.
        assert holds[1.50] == pytest.approx(0.3333, abs=1e-4)
        assert holds[1.85] == pytest.approx(0.0811, abs=1e-4)
        assert holds[1.95] == pytest.approx(0.0256, abs=1e-4)

        _, metadata = self._consensus({"A": [1.50, 1.50], "B": [1.95, 1.95]})
        assert metadata["book_count"] == 2
        assert metadata["market_width"] == 0.0

    def test_the_noise_guard_demands_nothing_at_a_pickem(self):
        """`spread_tenths` IS the minimum edge the guard demands.

        It scales with genuine devig ambiguity, which is the design working --
        but that means it demands ~zero exactly in the middle of the price band
        this strategy trades, and only reaches fee scale (20.0 tenths) out past
        a fair of about 0.26.
        """
        from backend.core.prices import PRICE_MAX

        def demanded(odds_a, odds_b):
            consensus, _ = self._consensus(
                {"A": [odds_a, odds_b], "B": [odds_a, odds_b]}
            )
            return consensus.method_spread("home") * PRICE_MAX

        assert demanded(1.85, 1.85) < 1e-6      # a total no-op
        assert demanded(1.90, 1.80) < 2.0
        assert demanded(2.60, 1.44) > 17.0

        # Monotone away from pick'em, which is why no fixed floor is safe.
        assert demanded(1.85, 1.85) < demanded(1.90, 1.80) < demanded(2.60, 1.44)


class TestTheCeilingBoundsFabricatedFairs:
    """ADR 0019 §4. `edge_ceiling_tenths` has a second, undeclared job.

    It is the only guard standing between a fabricated 0.5 fair and the screen.
    The older `20.0 <= ceiling <= 60.0` assertion is an inequality, not a pin.

    Measured by deformation rather than asserted: raising the ceiling to **50.0**
    -- a 25% wider hole -- is green across every test that existed before this
    class. Raising it to 60.0 *is* caught, but only by
    `test_a_large_edge_is_treated_as_a_defect`, which happens to use 60.0 as its
    example edge; that is a coincidence of fixture choice and would evaporate if
    the fixture were changed to 70.0.

    This pins the *property* instead, so neither raise can pass.
    """

    FABRICATED_FAIR = 0.49999999999999994

    def _surfacing_asks(self, ceiling_tenths):
        """Every ask at which a fabricated 0.5 fair would reach the screen."""
        from backend.core.ev import edge_after_fees_tenths

        surfaced = []
        for ask in range(1, 1000):
            net = edge_after_fees_tenths(
                ask_tenths=ask,
                contracts=1,
                fair_probability=self.FABRICATED_FAIR,
                maker=False,
            )
            if 0 < net <= ceiling_tenths:
                surfaced.append(ask)
        return surfaced

    def test_a_fabricated_fair_can_only_surface_between_44_and_48_cents(self):
        """The window is 4.0c wide and the fabrication is nearly right inside it.

        This is what makes the degenerate-fair defect bounded. It is not the
        guard that was designed to bound it.
        """
        asks = self._surfacing_asks(CONFIG.edge_ceiling_tenths)

        assert asks, "the ceiling must not close the window entirely"
        assert asks[0] == 440, f"window opens at {asks[0]}"
        assert asks[-1] == 479, f"window closes at {asks[-1]}"
        assert len(asks) == 40, "exactly 4.0c wide"

    def test_raising_the_ceiling_widens_the_window(self):
        """Priced, so the cost of relaxing it is on the record rather than felt.

        The day someone raises this to make the screen show something is the
        same day `min_book_count` comes under pressure. 1c of extra window per
        10 tenths of ceiling.
        """
        assert len(self._surfacing_asks(40.0)) == 40
        assert len(self._surfacing_asks(50.0)) == 50
        assert len(self._surfacing_asks(60.0)) == 60

        # And 60.0 is still green under the old inequality assertion.
        assert 20.0 <= 60.0 <= 60.0

    def test_the_fee_is_flat_across_the_window(self):
        """Why the 44-48c arithmetic is clean rather than approximate.

        The conservative max-of-models fee is 20.0 tenths at every ask in the
        window, so the bound is exact and not a linearisation. Stated because
        deriving it with an *assumed* flat fee would be this repo's
        "arithmetic that reproduces to the digit says nothing about its inputs".
        """
        from backend.core.ev import edge_after_fees_tenths

        for ask in (440, 460, 479):
            gross = 500 - ask
            net = edge_after_fees_tenths(
                ask_tenths=ask,
                contracts=1,
                fair_probability=self.FABRICATED_FAIR,
                maker=False,
            )
            assert gross - net == pytest.approx(20.0, abs=0.01)


class TestTheDeclaredVocabularyMatchesTheCode:
    """`ALL_CHECK_NAMES` is in the strategy config hash, so drift is silent.

    If a check is added and the constant is not updated, the new
    check-vocabulary is pooled with the old one under a single
    `strategy_config_version` and nothing in the record marks the split.
    """

    @staticmethod
    def _names_in_source() -> set[str]:
        import re
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[1]
            / "backend" / "core" / "suppression.py"
        ).read_text(encoding="utf-8")
        # Only the constructor calls, not the tuple that declares them.
        return set(re.findall(r'Check\(\s*\n?\s*"([a-z_]+)"', source))

    def test_the_regex_still_finds_the_checks(self):
        """Anchor. Two empty sets agree perfectly -- the vacuous pass this
        repo has a history of."""
        found = self._names_in_source()
        assert len(found) >= 9, f"regex found only {found}"
        assert "suspicious_edge" in found

    def test_declared_equals_emitted(self):
        from backend.core.suppression import ALL_CHECK_NAMES

        assert set(ALL_CHECK_NAMES) == self._names_in_source()

    def test_no_duplicates(self):
        from backend.core.suppression import ALL_CHECK_NAMES

        assert len(ALL_CHECK_NAMES) == len(set(ALL_CHECK_NAMES))


class TestTheInvariantCheckCannotFireOnRealInput:
    """P7, asked for by `pre-registrar` before it would rule ADR 0019 a
    non-trigger for the clean-shortfall registration.

    `inconsistent_consensus_metadata` was added by ADR 0019. The registration's
    void condition turns on whether a new check can alter `suppressed_reason`
    on a row the producer can actually emit. This asserts it cannot -- not by
    reading the code, but by driving the real producer.

    If this ever goes red, the registration's condition (c) has been broken and
    the clean population has moved.
    """

    @staticmethod
    def _fires(quotes_by_book) -> bool:
        from backend.core.devig import consensus_devig

        _, metadata = consensus_devig(["home", "away"], quotes_by_book)
        result = check(
            market_width=metadata["market_width"],
            book_count=metadata["book_count"],
        )
        return "inconsistent_consensus_metadata" in (result.reason or "")

    def test_it_never_fires_across_the_real_captured_fixture(self):
        """Every h2h market in the captured Odds API payload, through the real
        consensus producer with the live sharp-anchoring set."""
        import json
        from pathlib import Path

        from backend.core.devig import DevigError, consensus_devig
        from backend.runner import MONEYLINE, SHARP_BOOKS

        payload = json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "tests" / "fixtures" / "odds_mlb_h2h_spreads_totals.json"
            ).read_text(encoding="utf-8")
        )
        events = payload["events"]
        assert len(events) >= 10, "fixture truncated; this test is now vacuous"

        evaluated = 0
        for event in events:
            quotes, outcomes = {}, None
            for book in event.get("bookmakers", []):
                for market in book.get("markets", []):
                    if market.get("key") != MONEYLINE:
                        continue
                    names = [o["name"] for o in market["outcomes"]]
                    prices = [float(o["price"]) for o in market["outcomes"]]
                    if len(names) != 2:
                        continue
                    if outcomes is None:
                        outcomes = names
                    if set(names) == set(outcomes):
                        quotes[book["key"]] = [
                            prices[names.index(n)] for n in outcomes
                        ]
            if not quotes or outcomes is None:
                continue
            try:
                _, metadata = consensus_devig(
                    outcomes, quotes, sharp_books=SHARP_BOOKS
                )
            except DevigError:
                continue
            evaluated += 1
            result = check(
                market_width=metadata["market_width"],
                book_count=metadata["book_count"],
            )
            assert "inconsistent_consensus_metadata" not in (result.reason or ""), (
                f"the invariant fired on real captured input: "
                f"width={metadata['market_width']} "
                f"book_count={metadata['book_count']}"
            )

        assert evaluated >= 10, f"only {evaluated} events evaluated"

    def test_it_never_fires_on_one_book_or_on_many(self):
        assert not self._fires({"A": [1.85, 1.85]})
        assert not self._fires({"A": [1.85, 1.85], "B": [1.91, 1.91]})
        assert not self._fires({"A": [1.55, 2.55], "B": [1.57, 2.50]})
        assert not self._fires(
            {"A": [1.55, 2.55], "B": [1.57, 2.50], "C": [1.60, 2.45]}
        )

    def test_but_it_DOES_fire_when_the_invariant_is_actually_violated(self):
        """Otherwise the three tests above pass vacuously.

        These two states are unreachable from `consensus_devig`, which derives
        both fields from `len(selected)`. They are exactly what a future
        producer could get wrong.
        """
        measured_width_but_one_book = check(market_width=0.01, book_count=1)
        no_width_but_many_books = check(market_width=None, book_count=4)

        assert "inconsistent_consensus_metadata" in (
            measured_width_but_one_book.reason or ""
        )
        assert "inconsistent_consensus_metadata" in (
            no_width_but_many_books.reason or ""
        )


class TestTheTwoOddsAgeLimitsAgree:
    """ADR 0019 section 6. Two limits on one quantity, in two modules.

    `SuppressionConfig.max_odds_age_ms` is hardcoded and never reads the
    environment. `MAX_ODDS_AGE_S` is read by `StalenessConfig.load()` and
    consumed by `gate.py`, `live.py` and `routes.py`. They agree at the
    defaults, so a divergence only appears once the Fly value is set -- and
    then the suppression check and the odds sweep keep 15 minutes while the
    order gate, the Board's `actionable` flag and the phone's window banner
    move.

    **These tests cannot catch the real failure and are not meant to.** The
    divergence is created by a deployed environment value a test never sees;
    that is why the guard is a startup assertion. What these pin is that the
    assertion exists, fires, and fires in the right direction.

    Sibling of `TestTheTwoCommenceLimitsAgree`, same shape, same reason.
    """

    def test_the_defaults_agree_today(self):
        from backend.config import StalenessConfig

        assert (
            SuppressionConfig().max_odds_age_ms
            == StalenessConfig().max_odds_age_s * 1000
        )

    def test_the_assertion_passes_on_the_deployed_pair(self):
        from backend.config import StalenessConfig, assert_odds_age_limits_agree

        assert_odds_age_limits_agree(
            suppression_max_odds_age_ms=SuppressionConfig().max_odds_age_ms,
            staleness=StalenessConfig(),
        )

    def test_it_RAISES_when_the_environment_moves_one_of_them(self):
        """The deformation, and the whole point.

        This is what happens the day someone sets MAX_ODDS_AGE_S on Fly. Before
        ADR 0019 it produced no symptom at all.
        """
        import pytest as _pytest

        from backend.config import (
            StalenessConfig,
            StalenessLimitsDisagree,
            assert_odds_age_limits_agree,
        )

        with _pytest.raises(StalenessLimitsDisagree) as excinfo:
            assert_odds_age_limits_agree(
                suppression_max_odds_age_ms=SuppressionConfig().max_odds_age_ms,
                staleness=StalenessConfig(max_odds_age_s=300),
            )

        message = str(excinfo.value)
        assert "300" in message
        assert "ADR 0019" in message, "the error must say where the rule lives"

    def test_it_raises_in_both_directions(self):
        """A guard that only catches a loosening is half a guard."""
        import pytest as _pytest

        from backend.config import (
            StalenessConfig,
            StalenessLimitsDisagree,
            assert_odds_age_limits_agree,
        )

        for seconds in (60, 1800):
            with _pytest.raises(StalenessLimitsDisagree):
                assert_odds_age_limits_agree(
                    suppression_max_odds_age_ms=SuppressionConfig().max_odds_age_ms,
                    staleness=StalenessConfig(max_odds_age_s=seconds),
                )

    def test_the_window_planner_is_given_one_source(self):
        """`window_status` is called by the loop and by the API.

        It used to be handed `suppression.max_odds_age_ms` in one and
        `staleness.max_odds_age_s * 1000` in the other -- same planner, two
        inputs. Asserted on the source, because the failure is which expression
        is passed, and no behavioural test distinguishes them while the two
        values are equal.
        """
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        loop = (root / "scripts" / "run_loop.py").read_text(encoding="utf-8")
        routes = (root / "backend" / "api" / "routes.py").read_text(
            encoding="utf-8"
        )

        # Word-boundary guarded. A bare substring also matches this module's
        # OWN assertion call, `suppression_max_odds_age_ms=suppression.
        # max_odds_age_ms`, which is correct and must not trip the test -- the
        # first version of this assertion did exactly that.
        import re

        assert not re.search(r"(?<![\w])max_odds_age_ms=suppression\.", loop), (
            "run_loop passes the hardcoded suppression value to window_status "
            "again; the phone's banner and the loop's schedule will diverge "
            "the moment MAX_ODDS_AGE_S is set"
        )
        for source, name in ((loop, "run_loop.py"), (routes, "routes.py")):
            assert "max_odds_age_ms=staleness.max_odds_age_s * 1000" in source, (
                f"{name} no longer derives the window from StalenessConfig"
            )


class TestTheTwoKalshiQuoteAgeLimitsAgree:
    """The same defect as ADR 0019 section 6, on the field one line above.

    `SuppressionConfig.max_kalshi_quote_age_ms` is a hardcoded `30_000` that
    never reads the environment. `MAX_KALSHI_QUOTE_AGE_S` is read by
    `StalenessConfig.load()` and consumed by `gate.py:746`, `routes.py:1938`
    and `scripts/run_loop.py:243`. Section 6 fixed the odds-age pair and left
    this one, so the divergence was live until now.

    **This pair is sharper than its odds-age twin.** Measured by construction
    before the guard existed: at `MAX_KALSHI_QUOTE_AGE_S=5`, a 12-second-old
    quote passes every suppression check -- `suppressed_reason IS NULL`, so
    `actionable`, so on the Board and in the evidence record -- and the order
    endpoint refuses it. `test_the_divergence_makes_a_row_actionable_that_the_
    gate_refuses` pins that consequence directly, so a future reader does not
    have to take the severity on trust.

    **These tests cannot catch the real failure and are not meant to**, exactly
    as for the odds-age twin. The divergence is created by a deployed
    environment value a test never sees; that is why the guard is a startup
    assertion. What these pin is that the assertion exists, fires, fires in the
    right direction, and is called at both entry points.
    """

    def test_the_defaults_agree_today(self):
        from backend.config import StalenessConfig

        assert (
            SuppressionConfig().max_kalshi_quote_age_ms
            == StalenessConfig().max_kalshi_quote_age_s * 1000
        )

    def test_the_assertion_passes_on_the_deployed_pair(self):
        from backend.config import (
            StalenessConfig,
            assert_kalshi_quote_age_limits_agree,
        )

        assert_kalshi_quote_age_limits_agree(
            suppression_max_kalshi_quote_age_ms=(
                SuppressionConfig().max_kalshi_quote_age_ms
            ),
            staleness=StalenessConfig(),
        )

    def test_it_RAISES_when_the_environment_moves_one_of_them(self):
        """The deformation, and the whole point.

        This is what happens the day someone sets MAX_KALSHI_QUOTE_AGE_S on
        Fly. Before this guard it produced no symptom at all -- verified by
        driving `create_app` with the diverged pair and watching it start.
        """
        import pytest as _pytest

        from backend.config import (
            StalenessConfig,
            StalenessLimitsDisagree,
            assert_kalshi_quote_age_limits_agree,
        )

        with _pytest.raises(StalenessLimitsDisagree) as excinfo:
            assert_kalshi_quote_age_limits_agree(
                suppression_max_kalshi_quote_age_ms=(
                    SuppressionConfig().max_kalshi_quote_age_ms
                ),
                staleness=StalenessConfig(max_kalshi_quote_age_s=5),
            )

        message = str(excinfo.value)
        assert "5" in message
        assert "MAX_KALSHI_QUOTE_AGE_S" in message, "name the setting to change"
        assert "ADR 0019" in message, "the error must say where the rule lives"

    def test_it_raises_in_both_directions(self):
        """A guard that only catches a tightening is half a guard.

        Tightening is the likelier direction here -- it is what an operator
        reaches for after a bad fill -- but a loosened env value silently
        *narrows* what the Board shows relative to what the gate would take,
        which is the same class of disagreement pointing the other way.
        """
        import pytest as _pytest

        from backend.config import (
            StalenessConfig,
            StalenessLimitsDisagree,
            assert_kalshi_quote_age_limits_agree,
        )

        for seconds in (5, 120):
            with _pytest.raises(StalenessLimitsDisagree):
                assert_kalshi_quote_age_limits_agree(
                    suppression_max_kalshi_quote_age_ms=(
                        SuppressionConfig().max_kalshi_quote_age_ms
                    ),
                    staleness=StalenessConfig(max_kalshi_quote_age_s=seconds),
                )

    def test_the_divergence_makes_a_row_actionable_that_the_gate_refuses(self):
        """Why this guard raises instead of warning: the failure is a lie.

        Not a test of the assertion -- a test of the damage it prevents. With
        the env at 5s and suppression at its hardcoded 30s, a 12s-old quote is
        unsuppressed (so `actionable`, so counted as evidence and rendered as
        bettable) while `gate.py` and `routes.py` both refuse the same quote.
        Nothing on either side records a disagreement.
        """
        from backend.config import StalenessConfig

        diverged_env = StalenessConfig(max_kalshi_quote_age_s=5)
        quote_age_ms = 12_000

        result = evaluate_suppression(
            config=SuppressionConfig(),
            kalshi_quote_age_ms=quote_age_ms,
            odds_age_ms=1_000,
            commence_skew_ms=0,
            depth_at_ask=100.0,
            contracts=10,
            market_width=0.01,
            book_count=4,
            edge_tenths=10.0,
            method_spread_probability=0.001,
        )

        assert result.reason is None, (
            "the suppression gauntlet passes this quote on its hardcoded 30s"
        )
        assert quote_age_ms > diverged_env.max_kalshi_quote_age_s * 1000, (
            "and the order gate, reading the env, refuses the very same quote"
        )

    def test_both_entry_points_assert_it(self):
        """`create_app` and `run_loop`, the two processes that read the env.

        Asserted on the source for the same reason the odds-age sibling is: the
        failure is a missing call, and no behavioural test distinguishes a
        present call from an absent one while the two values are equal.
        """
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        loop = (root / "scripts" / "run_loop.py").read_text(encoding="utf-8")
        routes = (root / "backend" / "api" / "routes.py").read_text(
            encoding="utf-8"
        )

        for source, name in ((loop, "run_loop.py"), (routes, "routes.py")):
            assert "assert_kalshi_quote_age_limits_agree(" in source, (
                f"{name} no longer asserts the Kalshi-quote-age pair at "
                f"startup; a diverged MAX_KALSHI_QUOTE_AGE_S becomes silent "
                f"again"
            )
