"""Kalshi's combo product, parsed from captured payloads.

The premise correction these tests protect: this project spent eleven steps
believing Kalshi had no parlay product, because `/markets` is ~99.8% `KXMVE`
with no volume. `KXMVE` is Multi-Variate Event -- the combo builder in the app.
The `/markets` filter was right; the inference drawn from it was not.

Wire-format assertions here load `tests/fixtures/combo_collections.json`,
captured from the live API, never hand-constructed. The specific trap is that
the response key is `multivariate_contracts` while the path is
`/multivariate_event_collections`: reading the path-shaped key returns an empty
list and no error, which reads downstream as "Kalshi has no combos".
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.core.correlation import (
    CorrelationUnreachable,
    Leg,
    equicorrelated_joint,
    implied_correlation,
    joint_probability_all,
)
from backend.kalshi.combos import (
    COLLECTIONS_KEY,
    fetch_collections,
    ComboScope,
    MarketCreationRefused,
    liquidity,
    lookup_combo,
    parse_collection,
    same_game_collections,
)

FIXTURES = Path(__file__).parent / "fixtures"
NOW = 1_754_800_000_000


@pytest.fixture(scope="module")
def captured():
    return json.loads(
        (FIXTURES / "combo_collections.json").read_text(encoding="utf-8")
    )


@pytest.fixture(scope="module")
def summary():
    return json.loads(
        (FIXTURES / "combo_collections_summary.json").read_text(encoding="utf-8")
    )


@pytest.fixture(scope="module")
def collections(captured):
    return [parse_collection(entry) for entry in captured.values()]


class TestTheProductExists:
    """The correction, asserted so it cannot quietly revert."""

    def test_kalshi_has_a_combo_product(self, summary):
        assert summary["n_collections"] > 100
        assert summary["n_legs"] > 1000

    def test_it_includes_same_game_parlays(self, collections):
        same_game = [c for c in collections if c.is_same_game]
        assert same_game, "KXMVENBASINGLEGAME / KXMVENFLSINGLEGAME are same-game"

    def test_a_same_game_collection_bundles_more_than_the_moneyline(
        self, collections
    ):
        """Game, spread, total and player props on one fixture -- which is
        exactly the set `core.correlation` refuses to price from marginals."""
        nba = next(
            c for c in collections if c.series_ticker == "KXMVENBASINGLEGAME"
        )
        series = nba.leg_series
        assert any("GAME" in s for s in series)
        assert any("SPREAD" in s for s in series)
        assert any("TOTAL" in s for s in series)
        assert len(series) > 3, f"only found {series}"

    def test_cross_game_collections_require_at_least_two_legs(self, collections):
        multi = [
            c for c in collections
            if c.scope in {ComboScope.MULTI_GAME, ComboScope.CROSS_SPORT}
        ]
        assert multi
        assert all(c.size_min >= 2 for c in multi)

    def test_every_collection_resolves_all_legs_or_nothing(self, collections):
        described = [c for c in collections if c.functional_description]
        assert described
        assert all(
            "only resolve to YES if every associated market" in c.functional_description
            for c in described
        )


class TestWireFormat:
    async def test_a_path_shaped_response_key_raises(self):
        """Reading `multivariate_event_collections` returns an empty list and
        no error -- indistinguishable from "there are no combos".

        This previously asserted `COLLECTIONS_KEY == "multivariate_contracts"`,
        which compares a constant to its own literal and pins nothing: rename
        both and the test still passes. What is pinned now is the *behaviour* --
        an envelope using the plausible, path-shaped key must raise rather than
        return empty.

        **Honest limitation:** the literal itself is still not pinned against a
        real envelope, because `tests/fixtures/combo_collections.json` is a
        derived summary keyed by series and contains no response wrapper.
        Closing that needs one captured raw page.
        """
        class _Api:
            async def request(self, method, path, **kwargs):
                return {"multivariate_event_collections": [], "cursor": ""}

        with pytest.raises(KeyError, match="multivariate_contracts"):
            await fetch_collections(_Api())

    async def test_the_real_key_parses(self):
        """The discriminating half. If both keys raised, the test above would
        pass for the wrong reason."""
        class _Api:
            def __init__(self):
                self.calls = 0

            async def request(self, method, path, **kwargs):
                self.calls += 1
                if self.calls > 1:
                    return {COLLECTIONS_KEY: [], "cursor": ""}
                return {
                    COLLECTIONS_KEY: [{
                        "collection_ticker": "KXMVENBASINGLEGAME-26JUN13NYKSAS",
                        "series_ticker": "KXMVENBASINGLEGAME",
                        "associated_event_tickers": ["KXNBAGAME-26JUN13NYKSAS"],
                    }],
                    "cursor": "",
                }

        collections = await fetch_collections(_Api())
        assert len(collections) == 1
        assert collections[0].series_ticker == "KXMVENBASINGLEGAME"

    def test_every_captured_series_is_classified(self, collections):
        """Drift test. An unclassified series must not be silently bucketed --
        calling a same-game collection cross-category would route its legs
        through the wrong correlation path."""
        from backend.kalshi.combos import SCOPE_BY_SERIES

        # NO `startswith("KXMVE")` filter. It used to be here, and it excluded
        # exactly the four series that were unclassified -- KXCITIESWEATHER,
        # KXOSCARWINNERS, KXOSCARNOMINEESPIC, KXGRAMMYWINNERS, 4 of 16 captured
        # series, all silently bucketed CROSS_CATEGORY. A drift test that
        # filters out the drifting rows tests nothing at all.
        unclassified = [
            c.series_ticker for c in collections
            if c.series_ticker not in SCOPE_BY_SERIES
        ]
        assert not unclassified, f"unclassified combo series: {unclassified}"

    def test_a_fixture_key_links_a_collection_to_a_matched_game(self, collections):
        nba = next(c for c in collections if c.series_ticker == "KXMVENBASINGLEGAME")
        assert nba.fixture
        assert "-" not in nba.fixture

    def test_multi_game_collections_have_no_single_fixture(self, collections):
        multi = next(c for c in collections if c.scope is ComboScope.CROSS_SPORT)
        assert multi.fixture is None


class TestLiquidity:
    def test_the_report_states_the_seasonal_caveat(self, collections):
        """Zero quoters in August measures the calendar, not the product."""
        report = liquidity(collections)
        if report.n_quoted_legs == 0:
            assert "calendar" in report.verdict
            assert "in season" in report.verdict

    def test_the_report_counts_every_leg(self, collections):
        report = liquidity(collections)
        assert report.n_legs == sum(len(c.legs) for c in collections)
        assert report.n_collections == len(collections)


class TestMarketCreationGuard:
    async def test_pricing_a_combination_is_refused_by_default(self):
        """POST .../lookup creates a market on the exchange. No money moves,
        but it is an outward-facing write, so it is not a default."""
        with pytest.raises(MarketCreationRefused) as exc:
            await lookup_combo(None, "KXMVENBASINGLEGAME-X", [("E", "M")])
        assert "creates a market" in str(exc.value)
        assert "allow_market_creation=True" in str(exc.value)


class TestImpliedCorrelation:
    """Kalshi's combo price as a correlation measurement.

    This is the module's answer to its own refusal: `correlation.py` will not
    guess a same-game correlation, and a quoted joint supplies a measured one.
    """

    def _legs(self, *probabilities):
        return [
            Leg(
                label=f"L{i}", probability=p, event_key="E1",
                league="basketball_nba", commence_ms=NOW,
            )
            for i, p in enumerate(probabilities)
        ]

    def test_a_joint_equal_to_the_product_implies_independence(self):
        legs = self._legs(0.6, 0.5)
        rho = implied_correlation(legs, 0.30)
        assert rho == pytest.approx(0.0, abs=0.02)

    def test_a_joint_above_the_product_implies_positive_correlation(self):
        """'Team wins' and 'over the total' land together more often than
        independence predicts, and the quote says by how much."""
        legs = self._legs(0.6, 0.5)
        assert implied_correlation(legs, 0.36) > 0.1

    def test_a_joint_below_the_product_implies_negative_correlation(self):
        legs = self._legs(0.6, 0.5)
        assert implied_correlation(legs, 0.24) < -0.1

    def test_the_recovered_correlation_reproduces_the_joint(self):
        """Round trip: invert, then price forward and land back."""
        legs = self._legs(0.55, 0.48, 0.62)
        target = 0.20
        rho = implied_correlation(legs, target)
        assert equicorrelated_joint(legs, rho) == pytest.approx(target, abs=0.01)

    def test_a_joint_above_the_smallest_marginal_is_unreachable(self):
        """No dependence structure lets all legs win more often than the
        rarest of them does alone."""
        legs = self._legs(0.6, 0.5)
        with pytest.raises(CorrelationUnreachable) as exc:
            implied_correlation(legs, 0.55)
        assert "Frechet" in str(exc.value)

    def test_an_impossible_joint_names_the_bounds(self):
        legs = self._legs(0.6, 0.5)
        with pytest.raises(CorrelationUnreachable) as exc:
            implied_correlation(legs, 0.001)
        assert "Frechet" in str(exc.value) or "outside" in str(exc.value)

    def test_a_degenerate_joint_is_refused(self):
        legs = self._legs(0.6, 0.5)
        for bad in (0.0, 1.0):
            with pytest.raises(CorrelationUnreachable):
                implied_correlation(legs, bad)

    def test_a_measured_correlation_then_prices_the_parlay(self):
        """The loop closing: a refusal, a measurement, then a price."""
        from backend.core.correlation import CorrelationRefused

        legs = self._legs(0.6, 0.5)
        with pytest.raises(CorrelationRefused):
            joint_probability_all(legs)

        rho = implied_correlation(legs, 0.36)
        priced = joint_probability_all(legs, overrides={("L0", "L1"): rho})
        assert priced == pytest.approx(0.36, abs=0.01)


class TestCollectionsWithNoAssociatedEvents:
    """`associated_events` is EMPTY on the wire for real collections.

    Measured on the captured payload: KXCITIESWEATHER 0 against 7 tickers,
    KXOSCARWINNERS 0 against 10, KXOSCARNOMINEESPIC 0 against 1,
    KXGRAMMYWINNERS 0 against 4. Reading only that field parsed all four to zero
    legs, so `liquidity()` undercounted and `fixture` returned `None` — and the
    collections vanished from `same_game_collections()`, the correlation source
    this project went to some trouble to obtain.

    It also poisons the headline measurement: "0 of 13,806 legs quoted" was
    taken with four whole collections contributing nothing at all.
    """

    def test_legs_are_recovered_from_the_ticker_list(self, captured):
        recovered = {
            name: len(parse_collection(payload).legs)
            for name, payload in captured.items()
            if not (payload.get("associated_events") or [])
        }
        assert recovered, "no collection in the capture has an empty events list"
        assert all(n > 0 for n in recovered.values()), (
            f"collections still parsing to zero legs: "
            f"{[k for k, v in recovered.items() if not v]}"
        )
        assert sum(recovered.values()) == 22

    def test_recovered_legs_are_marked_as_lacking_detail(self, captured):
        """"Nobody quotes this" and "we were not told" are different claims.

        The ticker list carries no quoter or size information, so a leg built
        from it must not be reported as a confirmed-empty book — that is the
        reading that would get a collection discarded as dead.
        """
        payload = captured["KXOSCARWINNERS"]
        legs = parse_collection(payload).legs
        assert legs
        assert all(leg.detail_missing for leg in legs)
        assert all(not leg.is_quoted for leg in legs)

    def test_legs_with_full_detail_are_not_marked(self, captured):
        """The discriminating half: the flag must not be set on everything."""
        payload = captured["KXMVENBASINGLEGAME"]
        legs = parse_collection(payload).legs
        assert legs
        assert not any(leg.detail_missing for leg in legs)


class TestTheFixtureComesFromTheCollectionTicker:
    """`fixture` derived from `legs[0].event_ticker`, so it depended on leg
    ordering and returned `None` whenever the legs failed to parse.

    That turned a parsing gap into "this is not a same-game collection" — a
    silent reclassification rather than an error. The collection ticker carries
    the suffix authoritatively.
    """

    def test_it_reads_the_collection_ticker(self, captured):
        collection = parse_collection(captured["KXMVENBASINGLEGAME"])
        assert collection.collection_ticker == "KXMVENBASINGLEGAME-26JUN13NYKSAS"
        assert collection.fixture == "26JUN13NYKSAS"

    def test_it_survives_legs_that_did_not_parse(self, captured):
        """The failure mode being closed. With no legs at all the old code
        returned None and the collection silently stopped being same-game."""
        payload = dict(captured["KXMVENBASINGLEGAME"])
        payload["associated_events"] = []
        payload["associated_event_tickers"] = []

        collection = parse_collection(payload)
        assert collection.legs == ()
        assert collection.is_same_game
        assert collection.fixture == "26JUN13NYKSAS"
