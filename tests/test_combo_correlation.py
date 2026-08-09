"""Reading a combo quote as a correlation, against a captured payload.

`tests/fixtures/combo_priced_markets.json` is a verbatim GET capture of twelve
combination markets that were quoted when read, together with every leg market
they reference, read at the same time. Nothing here is hand-constructed: this
is the wire-format rule in CLAUDE.md, and the reason for it is that this
project's predecessor parsed every order book to zero levels for its entire
life while 305 tests built from remembered field names passed.

What these tests do not establish
---------------------------------
That any correlation reported is *correct*. They establish that the wire is
read as it is written, that the `no` side is complemented, that an unreadable
price refuses instead of substituting, and that the same-game and cross-game
populations are told apart. Whether Kalshi's combo book is right about
dependence is not a question a fixture can answer.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "combo_priced_markets.json"


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "measure_combo_correlation_under_test",
        ROOT / "scripts" / "measure_combo_correlation.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mcc = _load_script()


@pytest.fixture(scope="module")
def capture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def marginals_for(combo: dict, legs: dict) -> list[float]:
    """The marginals for a captured combination.

    Calls `marginal_for_leg` rather than restating the rule. An earlier version
    of this helper re-implemented the `no` complement, so flipping it in the
    script left every test here green -- the test was asserting its own copy.
    Related: the repo's rule about deleting one of two paths rather than
    testing that they agree.
    """
    out = []
    for leg in combo["mve_selected_legs"]:
        quote = mcc.readable_quote(legs[leg["market_ticker"]])
        assert quote is not None and quote.bid is not None
        marginal = mcc.marginal_for_leg(leg, quote)
        assert marginal is not None
        out.append(marginal)
    return out


class TestTheCaptureItself:
    """Assert what the capture must contain, so a thin re-capture fails loudly.

    A truncated or re-scoped capture makes every test below it vacuous while
    leaving them green -- the directory listing looks identical either way.
    """

    def test_it_holds_priced_combinations_and_all_their_legs(self, capture):
        combos = capture["combos"]
        legs = capture["legs"]
        assert len(combos) >= 8, "too few combinations to say anything"

        for combo in combos:
            selected = combo["mve_selected_legs"]
            assert 2 <= len(selected) <= 3
            for leg in selected:
                assert leg["market_ticker"] in legs, (
                    "a combination references a leg the capture does not hold, "
                    "so its marginal would have to be invented"
                )

    def test_every_combination_carries_a_readable_ask(self, capture):
        for combo in capture["combos"]:
            quote = mcc.readable_quote(combo)
            assert quote is not None, f"{combo['ticker']} has no usable ask"
            assert 0.0 < quote.ask < 1.0

    def test_both_leg_sides_appear(self, capture):
        """A capture of only `yes` legs cannot exercise the complement."""
        sides = {
            leg["side"]
            for combo in capture["combos"]
            for leg in combo["mve_selected_legs"]
        }
        assert sides == {"yes", "no"}, sides

    def test_the_wire_keys_are_the_ones_the_script_reads(self, capture):
        combo = capture["combos"][0]
        assert "mve_selected_legs" in combo
        assert "mve_collection_ticker" in combo
        assert "yes_ask_dollars" in combo
        assert set(combo["mve_selected_legs"][0]) >= {
            "event_ticker", "market_ticker", "side",
        }


class TestUnreadableNeverBecomesANumber:
    def test_garbage_is_none_and_not_zero(self):
        """`0.0` is a legitimate price here -- a settled loser.

        A parser returning it on garbage is indistinguishable from one that
        read a settled market correctly.
        """
        assert mcc.dollars("") is None
        assert mcc.dollars(None) is None
        assert mcc.dollars("n/a") is None
        assert mcc.dollars("1.5") is None
        assert mcc.dollars("0.0000") == 0.0

    def test_a_zero_bid_is_absent_rather_than_zero(self):
        """Nearly every combination quotes `yes_bid_dollars: "0.0000"`.

        That is "nobody bids YES", not "the market believes zero". Carrying it
        as 0.0 would put a mid of ask/2 into every measurement.
        """
        quote = mcc.readable_quote(
            {"yes_bid_dollars": "0.0000", "yes_ask_dollars": "0.4380"}
        )
        assert quote is not None
        assert quote.ask == pytest.approx(0.4380)
        assert quote.bid is None
        assert quote.mid is None, (
            "a mid was invented from one side of the book"
        )
        assert quote.width is None

    def test_a_two_sided_quote_keeps_both(self):
        quote = mcc.readable_quote(
            {"yes_bid_dollars": "0.4090", "yes_ask_dollars": "0.4560"}
        )
        assert quote.bid == pytest.approx(0.4090)
        assert quote.mid == pytest.approx(0.4325)
        assert quote.width == pytest.approx(0.0470)

    def test_a_combination_with_an_unreadable_leg_yields_nothing(self, capture):
        """The refusal, not a substituted marginal."""
        combo = capture["combos"][0]
        legs = dict(capture["legs"])
        victim = combo["mve_selected_legs"][0]["market_ticker"]
        legs[victim] = {"yes_bid_dollars": "", "yes_ask_dollars": ""}

        assert mcc.readable_quote(legs[victim]) is None


class TestTheNoSideIsComplemented:
    """The sign convention, anchored where a wrong one gives a *different*
    answer.

    A `no` leg contributes `1 - yes`. Getting it backwards produces entirely
    plausible correlations of the wrong sign, and nothing in the output says
    so -- the failure this repo has recorded twice, on `probability_cover` and
    on NO-side CLV.
    """

    def test_a_no_leg_uses_the_complement(self, capture):
        legs = capture["legs"]
        combo = next(
            c for c in capture["combos"]
            if any(leg["side"] == "no" for leg in c["mve_selected_legs"])
        )
        for leg, marginal in zip(
            combo["mve_selected_legs"], marginals_for(combo, legs)
        ):
            leg_mid = mcc.readable_quote(legs[leg["market_ticker"]]).mid
            if leg["side"] == "no":
                assert marginal == pytest.approx(1.0 - leg_mid)
            else:
                assert marginal == pytest.approx(leg_mid)

    def test_a_side_that_is_neither_refuses(self):
        """Kalshi adding a third side must stop the measurement, not default it."""
        assert mcc.marginal_for_leg(
            {"market_ticker": "KXA-26AUG09AAABBB-X", "side": "maybe"},
            mcc.Quote(ask=0.60, bid=0.50),
        ) is None

    def test_a_leg_with_no_mid_refuses(self):
        """A one-sided leg has no unbiased marginal, so it yields nothing."""
        assert mcc.marginal_for_leg(
            {"market_ticker": "KXA-26AUG09AAABBB-X", "side": "yes"},
            mcc.Quote(ask=0.60),
        ) is None

    def test_the_wrong_convention_is_not_merely_a_different_number(self):
        """Chosen so the wrong reading fails outright, not subtly.

        Legs at 0.20 (a `no` on a 0.80 market) and 0.50 with a joint of 0.10
        are exactly independent -- rho 0. Read the `no` leg as 0.80 instead and
        the joint falls below the Frechet lower bound of 0.30, so no dependence
        structure produces it at all. `0.5000 == 0.5000` would have passed
        under both.
        """
        right = mcc.measure(
            mcc.Combo(
                ticker="T", collection="C",
                joint=mcc.Quote(ask=0.10),
                legs=(
                    {"market_ticker": "KXA-26AUG09AAABBB-X", "side": "no"},
                    {"market_ticker": "KXB-26AUG09CCCDDD-Y", "side": "yes"},
                ),
                subtitle="",
            ),
            [0.20, 0.50],
        )
        assert right.rho_at_ask == pytest.approx(0.0, abs=0.01)

        wrong = mcc.measure(
            mcc.Combo(
                ticker="T", collection="C",
                joint=mcc.Quote(ask=0.10),
                legs=(
                    {"market_ticker": "KXA-26AUG09AAABBB-X", "side": "no"},
                    {"market_ticker": "KXB-26AUG09CCCDDD-Y", "side": "yes"},
                ),
                subtitle="",
            ),
            [0.80, 0.50],
        )
        assert wrong.rho_at_ask is None
        assert "Frechet" in wrong.note


class TestSameGameIsToldApartFromCrossGame:
    """The control is only a control if the two populations are separated.

    Cross-game legs are near-independent, so their measured rho is this
    method's own bias. Letting one same-game combination into that group
    would raise the bias estimate using the very quantity it exists to
    calibrate.
    """

    def test_the_fixture_suffix_is_what_identifies_a_game(self):
        assert mcc.fixture_of("KXWNBAGAME-26AUG09LVNY-NY") == "26AUG09LVNY"
        assert (
            mcc.fixture_of("KXWNBAPTS-26AUG09LVNY-NYBSTEWART30-15")
            == "26AUG09LVNY"
        )
        assert mcc.fixture_of("KXMLBTOTAL-26AUG091410CHCKC-14") == "26AUG091410CHCKC"
        assert mcc.fixture_of("not-a-kalshi-ticker") is None

    def _combo(self, tickers):
        return mcc.Combo(
            ticker="T", collection="C", joint=mcc.Quote(ask=0.5),
            legs=tuple(
                {"market_ticker": t, "side": "yes"} for t in tickers
            ),
            subtitle="",
        )

    def test_all_legs_one_fixture_is_same_game(self):
        assert self._combo([
            "KXWNBAGAME-26AUG09LVNY-NY",
            "KXWNBAPTS-26AUG09LVNY-NYBSTEWART30-15",
        ]).scope == "same_game"

    def test_all_legs_distinct_fixtures_is_cross_game(self):
        assert self._combo([
            "KXMLBGAME-26AUG091335ATLNYY-ATL",
            "KXMLBTOTAL-26AUG091435BALTEX-12",
        ]).scope == "cross_game"

    def test_a_partial_overlap_is_neither(self):
        """Two same-game legs plus a third from elsewhere.

        Fitting one rho across that mixes a same-game pair with two cross-game
        pairs, so the answer is an average of two different quantities and
        belongs in neither column.
        """
        assert self._combo([
            "KXWNBAGAME-26AUG09LVNY-NY",
            "KXWNBAPTS-26AUG09LVNY-NYBSTEWART30-15",
            "KXMLBGAME-26AUG091335ATLNYY-ATL",
        ]).scope == "mixed"

    def test_an_undecodable_ticker_is_not_quietly_cross_game(self):
        """The failure mode that would matter: unparsed tickers all differ from
        each other, so a `None` treated as a fixture makes every such
        combination look like a clean cross-game control."""
        assert self._combo([
            "weird-thing", "KXMLBGAME-26AUG091335ATLNYY-ATL",
        ]).scope == "undecodable"

    def test_the_capture_contains_at_least_one_same_game_combination(
        self, capture
    ):
        """Otherwise the same-game path is untested by real data."""
        scopes = [
            mcc.Combo(
                ticker=c["ticker"], collection="", joint=mcc.readable_quote(c),
                legs=tuple(c["mve_selected_legs"]), subtitle="",
            ).scope
            for c in capture["combos"]
        ]
        assert "same_game" in scopes, scopes


class TestTheAskIsAnUpperBound:
    def test_a_higher_joint_implies_a_higher_rho(self):
        """Why the ask overstates dependence, asserted rather than described.

        Positive association raises a joint above the product of its
        marginals, so inverting at the ask -- which carries the combo's whole
        margin -- can only push rho up.
        """
        def rho(joint):
            return mcc.measure(
                mcc.Combo(
                    ticker="T", collection="C", joint=mcc.Quote(ask=joint),
                    legs=(
                        {"market_ticker": "KXA-26AUG09AAABBB-X", "side": "yes"},
                        {"market_ticker": "KXB-26AUG09CCCDDD-Y", "side": "yes"},
                    ),
                    subtitle="",
                ),
                [0.50, 0.50],
            ).rho_at_ask

        assert rho(0.20) < rho(0.25) < rho(0.30) < rho(0.35)

    def test_independence_reads_as_zero(self):
        """The definitional anchor: joint == product means no dependence."""
        measurement = mcc.measure(
            mcc.Combo(
                ticker="T", collection="C", joint=mcc.Quote(ask=0.25),
                legs=(
                    {"market_ticker": "KXA-26AUG09AAABBB-X", "side": "yes"},
                    {"market_ticker": "KXB-26AUG09CCCDDD-Y", "side": "yes"},
                ),
                subtitle="",
            ),
            [0.50, 0.50],
        )
        assert measurement.rho_at_ask == pytest.approx(0.0, abs=0.01)
        assert measurement.independent_joint == pytest.approx(0.25)


class TestTheWholeCaptureInverts:
    def test_every_captured_combination_gives_a_number_or_a_stated_reason(
        self, capture
    ):
        legs = capture["legs"]
        answered = 0
        for combo_payload in capture["combos"]:
            combo = mcc.Combo(
                ticker=combo_payload["ticker"],
                collection=combo_payload.get("mve_collection_ticker") or "",
                joint=mcc.readable_quote(combo_payload),
                legs=tuple(combo_payload["mve_selected_legs"]),
                subtitle="",
            )
            measurement = mcc.measure(combo, marginals_for(combo_payload, legs))
            if measurement.rho_at_ask is None:
                assert measurement.note, (
                    f"{combo.ticker} produced no rho and no reason"
                )
            else:
                assert -1.0 < measurement.rho_at_ask < 1.0
                answered += 1
        assert answered >= 6, (
            f"only {answered} of {len(capture['combos'])} captured "
            f"combinations inverted; the capture may be stale"
        )


class TestWhatItCostsToBuyALeg:
    """The price actually paid for a leg, which is not its marginal.

    `marginal_for_leg` returns a mid, because inverting a joint into a
    correlation wants an unbiased probability. Deciding whether a combination
    is worse than simply buying one of its legs wants the price you would
    transact at instead. CLAUDE.md records a bucket that showed a +25.4 point
    edge and lost money because it was bucketed on the mid and bought at the
    ask; these are two different questions and must not share a number.
    """

    def test_a_yes_leg_costs_the_ask(self):
        assert mcc.cost_to_buy_leg(
            {"market_ticker": "KXA-26AUG09AAABBB-X", "side": "yes"},
            mcc.Quote(ask=0.35, bid=0.30),
        ) == pytest.approx(0.35)

    def test_a_no_leg_costs_one_minus_the_bid_not_one_minus_the_ask(self):
        """Anchored where the two candidate conventions give different answers.

        To hold NO you sell YES, and you sell into the **bid**. On a 0.30/0.35
        market that is 0.70. Reading it as `1 - ask` gives 0.65 -- understating
        the cost by the whole spread, in the direction that manufactures
        domination out of nothing. A symmetric quote would have passed under
        both readings, which is the trap this repo hit on NO-side CLV, where
        the anchor chosen sat exactly at 50c and the error vanished there.
        """
        cost = mcc.cost_to_buy_leg(
            {"market_ticker": "KXA-26AUG09AAABBB-X", "side": "no"},
            mcc.Quote(ask=0.35, bid=0.30),
        )
        assert cost == pytest.approx(0.70)
        assert cost != pytest.approx(0.65)

    def test_a_no_leg_with_no_bid_refuses(self):
        """No bid means no sellable YES, so the NO cost is unknown, not 1.0."""
        assert mcc.cost_to_buy_leg(
            {"market_ticker": "KXA-26AUG09AAABBB-X", "side": "no"},
            mcc.Quote(ask=0.35),
        ) is None

    def test_a_side_that_is_neither_refuses(self):
        assert mcc.cost_to_buy_leg(
            {"market_ticker": "KXA-26AUG09AAABBB-X", "side": "maybe"},
            mcc.Quote(ask=0.35, bid=0.30),
        ) is None

    def test_buying_a_leg_never_costs_less_than_its_marginal(self, capture):
        """The spread is paid on either side, so cost >= mid on every real leg.

        Asserted across the whole capture rather than one constructed quote:
        it holds by definition for both sides, so a wrong side-flip in either
        function breaks it on some real market.
        """
        legs = capture["legs"]
        checked = 0
        for combo in capture["combos"]:
            for leg in combo["mve_selected_legs"]:
                quote = mcc.readable_quote(legs[leg["market_ticker"]])
                if quote is None or quote.bid is None:
                    continue
                marginal = mcc.marginal_for_leg(leg, quote)
                cost = mcc.cost_to_buy_leg(leg, quote)
                assert marginal is not None and cost is not None
                assert cost >= marginal - 1e-9, (
                    f"{leg['market_ticker']} side={leg['side']} "
                    f"cost {cost} below marginal {marginal}"
                )
                checked += 1
        assert checked >= 10, f"only {checked} legs checked; capture may be stale"


class TestAJointAndItsLegsAreReadAtTheSameMoment:
    """The leg cache must not survive a round, and the data must show it.

    Comparing a combination against its own legs only means anything if both
    prices were read at the same moment. That used to be argued from the
    caching policy -- and the policy did the opposite of what its comment
    claimed. Caching by ticker alone pins a leg to the first time the *run* saw
    it, so with Kalshi minting ~700 combinations a minute, a combination first
    seen in round 40 was priced against a leg quote from round 1.

    It is not a cosmetic staleness: it is the exact alternative explanation
    `docs/adr/0012` gives for the 94% same-game Frechet refusal rate, so the
    cache was manufacturing the confound that finding has to rule out.
    """

    @staticmethod
    def _api(leg_prices_by_round):
        """A fake exchange whose leg price moves between rounds."""

        class FakeApi:
            def __init__(self):
                self.round = -1

            async def request(self, method, path, params=None):
                if path == "/markets":
                    # Only the first series carries anything; the rest are
                    # empty, which is a real state and keeps the fake small.
                    if params.get("series_ticker") != mcc.MVE_SERIES[0]:
                        return {"markets": [], "cursor": None}
                    self.round += 1
                    return {
                        "markets": [{
                            "ticker": f"KXMVE-26AUG09AAABBB-R{self.round}",
                            "mve_collection_ticker": "COLL",
                            "yes_ask_dollars": "0.1000",
                            "yes_bid_dollars": "0.0500",
                            "yes_sub_title": "",
                            "created_time": "2026-08-09T15:00:00Z",
                            "mve_selected_legs": [
                                {"market_ticker": "KXA-26AUG09AAABBB-X",
                                 "side": "yes"},
                                {"market_ticker": "KXB-26AUG09CCCDDD-Y",
                                 "side": "yes"},
                            ],
                        }],
                        "cursor": None,
                    }
                if path.endswith("KXA-26AUG09AAABBB-X"):
                    bid, ask = leg_prices_by_round[min(
                        self.round, len(leg_prices_by_round) - 1
                    )]
                    return {"market": {
                        "yes_bid_dollars": f"{bid:.4f}",
                        "yes_ask_dollars": f"{ask:.4f}",
                    }}
                return {"market": {
                    "yes_bid_dollars": "0.4500",
                    "yes_ask_dollars": "0.5500",
                }}

        return FakeApi()

    async def test_a_leg_that_moves_between_rounds_is_re_read(self):
        """The property that fails under a run-long cache.

        The leg goes 0.30/0.35 in round one to 0.60/0.65 in round two. Round
        two's combination must carry the *new* marginal. Holding the cache
        across rounds returns 0.325 for both, so this test states the old bug
        as an invariant rather than checking the new number looks plausible.
        """
        api = self._api([(0.30, 0.35), (0.60, 0.65)])
        result = await mcc.survey(
            api, pages=1, rounds=2, interval_s=0.0, max_legs=3
        )
        assert len(result.measurements) == 2, result.refused
        first, second = result.measurements
        assert first.marginals[0] == pytest.approx(0.325)
        assert second.marginals[0] == pytest.approx(0.625)

    async def test_every_leg_carries_the_stamp_of_its_own_round(self):
        """Contemporaneity is filterable in the output, not taken on trust.

        The analysis needs to drop any combination whose legs were read at a
        different moment. It can only do that if the moment is recorded, and
        these markets are gone within minutes, so it cannot be recovered later.
        """
        api = self._api([(0.30, 0.35), (0.60, 0.65)])
        result = await mcc.survey(
            api, pages=1, rounds=2, interval_s=0.0, max_legs=3
        )
        for measurement in result.measurements:
            joint_ms = measurement.combo.joint.observed_ms
            assert joint_ms is not None
            for quote in measurement.leg_quotes:
                assert quote.observed_ms == joint_ms

        stamps = {m.combo.joint.observed_ms for m in result.measurements}
        assert len(stamps) == 2, (
            "both rounds carry one stamp, so the rounds cannot be told apart"
        )

    async def test_the_combination_records_when_it_was_minted(self):
        """Age is what separates staleness from a real pricing property.

        A staleness artefact must grow with a combination's age; a real one is
        flat in it. Without `created_ms` neither claim is checkable.
        """
        api = self._api([(0.30, 0.35)])
        result = await mcc.survey(
            api, pages=1, rounds=1, interval_s=0.0, max_legs=3
        )
        assert result.measurements
        # Built from a datetime rather than pinned as a literal, so the
        # expectation is fixed by the calendar instead of by whatever the
        # parser happened to return the first time this ran.
        expected = int(
            datetime(2026, 8, 9, 15, 0, tzinfo=timezone.utc).timestamp() * 1000
        )
        assert result.measurements[0].combo.created_ms == expected
