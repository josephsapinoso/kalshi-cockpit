"""The non-sports spread census, against captured payloads and no network.

Design registered at
`docs/measurements/2026-08-15-preregistration-non-sports-spread-reachability.md`.
The tests here are about the *instrument*, not the finding: whether the tally
reads the wire format correctly, whether its exclusions are decisions, and
whether its registered decision rule is applied as written.

**The first test is the one that earns its place.** The census originally
filtered markets on `status == "open"`, which is the *event* query parameter --
markets inside an open event report `active`. It would have excluded every
market on the exchange and printed an empty census, and an empty census reads
as a finding rather than as a broken filter.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.census_non_sports_spread import (
    DEAD_RATIO,
    LIVE_RATIO,
    MIN_MARKETS_FOR_A_VERDICT,
    SeriesTally,
    tally_event,
    verdict,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def load(name: str) -> list[dict]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class TestItReadsTheWireFormatThatActuallyExists:
    def test_a_captured_payload_produces_a_non_empty_tally(self):
        """The guard against the `open`/`active` defect.

        Asserting a *count* rather than "it ran": a filter that matches nothing
        raises nothing, returns cleanly, and prints a census of zero markets
        that a reader takes for a fact about the exchange.
        """
        tallies: dict[str, SeriesTally] = {}
        for event in load("events_sports_nested.json"):
            tally_event(event, tallies)

        readable = sum(t.n for t in tallies.values())
        seen = sum(t.markets_seen for t in tallies.values())
        assert seen > 0, "the fixture carried no markets at all"
        assert readable > 0, (
            "every market in a captured payload was excluded, which is what a "
            "filter on the wrong `status` value looks like"
        )

    def test_no_market_is_lost_between_seen_and_accounted_for(self):
        """Seen == readable + every exclusion. A census whose denominator does
        not reconcile is reporting on a population it cannot name."""
        tallies: dict[str, SeriesTally] = {}
        for event in load("events_sports_nested.json"):
            tally_event(event, tallies)

        for tally in tallies.values():
            accounted = (
                tally.n
                + tally.excluded_field_absent
                + tally.excluded_not_active
                + tally.excluded_one_sided
                + tally.excluded_settled
                + tally.excluded_crossed
            )
            assert accounted == tally.markets_seen, (
                f"{tally.series_ticker}: {tally.markets_seen} seen but "
                f"{accounted} accounted for"
            )

    def test_an_unrecognised_status_is_named_rather_than_dropped(self):
        unknown: dict[str, int] = {}
        tally_event(
            {
                "series_ticker": "KXWEATHER",
                "category": "Climate",
                "markets": [
                    {
                        "status": "unlisted_new_thing",
                        "yes_bid_dollars": "0.40",
                        "no_bid_dollars": "0.58",
                    }
                ],
            },
            {},
            unknown,
        )
        assert unknown == {"unlisted_new_thing": 1}


class TestTheArmIsDecidedByProductionCode:
    def test_a_sports_event_lands_in_the_sports_arm(self):
        """`classify_series` decides, not a re-expression of it here.

        A census that reimplemented the split would measure a different
        population than the pipeline applies, and the two would drift silently.
        """
        events = load("events_sports_nested.json")
        arms = {tally_event(e, {}) for e in events}
        assert "sports" in arms

    def test_an_unclassifiable_series_lands_in_the_non_sports_arm(self):
        arm = tally_event(
            {
                "series_ticker": "KXCITIESWEATHER",
                "category": "Climate",
                "product_metadata": {},
                "markets": [],
            },
            {},
        )
        assert arm == "non_sports"


class TestExclusionsAreDecisions:
    def _one(self, **market):
        tallies: dict[str, SeriesTally] = {}
        tally_event(
            {
                "series_ticker": "KXTEST",
                "category": "Climate",
                "markets": [{"status": "active", **market}],
            },
            tallies,
        )
        return next(iter(tallies.values()))

    def test_an_unreadable_side_is_excluded_and_never_read_as_zero(self):
        """A market with no bid is not a market with a zero bid.

        Coercing would derive a 100.0c ask and record it as an enormous spread,
        dragging the median of a whole series with it.
        """
        tally = self._one(yes_bid_dollars=None, no_bid_dollars="0.58")
        assert tally.n == 0
        assert tally.excluded_field_absent == 1

    def test_a_settled_price_is_excluded(self):
        """A NO bid of $1.00 derives a YES ask of 0 -- a settled outcome
        wearing a quote, which `core/ev` refuses for the same reason.

        **Both sides at the extreme, deliberately.** The pair
        `(0.0000, 1.0000)` is simultaneously a settlement and an empty YES
        side, so it cannot distinguish the two readings -- an anchor chosen
        where the candidate errors agree. `test_a_one_sided_live_book_*` below
        is the discriminating case, and it is the one that was missing.
        """
        tally = self._one(yes_bid_dollars="0.0000", no_bid_dollars="1.0000")
        assert tally.n == 0
        assert tally.excluded_settled == 1

    def test_a_one_sided_live_book_is_not_counted_as_settled(self):
        """The defect the first run shipped, and 28,677 markets went through it.

        `yes_bid = 0` with `no_bid = 42c` is a **live** market that nobody bids
        YES on. It is not settled. Until 2026-08-16 both landed in one counter
        named `settled_price`, so 35.2% of the population was dropped under a
        label that was wrong for most of it -- and dropped precisely where books
        are thinnest, biasing every surviving median toward tight.

        The two must stay separable, because the exclusion rate is itself the
        finding: a series whose book is one-sided on 96% of its rungs is not a
        tight series, whatever the other 4% say.
        """
        tally = self._one(yes_bid_dollars="0.0000", no_bid_dollars="0.4200")
        assert tally.n == 0
        assert tally.excluded_one_sided == 1
        assert tally.excluded_settled == 0, (
            "a live one-sided book was counted as a settled outcome"
        )

    def test_the_other_empty_side_is_also_one_sided(self):
        """`no_bid = 0` with a real YES bid: nobody bids NO. Same class."""
        tally = self._one(yes_bid_dollars="0.4200", no_bid_dollars="0.0000")
        assert tally.excluded_one_sided == 1
        assert tally.excluded_settled == 0

    def test_the_field_absent_counter_guards_a_case_the_wire_does_not_send(self):
        """Kept, and its emptiness is the point rather than an oversight.

        Kalshi sends `"0.0000"` for an empty side, never an absent field: 0 of
        245 markets in the captured payload omit either key, and the counter was
        0 across all 81,420 markets of the first run. It is retained because a
        counter provably 0 today is how a wire change announces itself tomorrow
        -- but it must never again be the bucket one-sided books fall into.
        """
        markets = [
            m
            for event in load("events_sports_nested.json")
            for m in (event.get("markets") or [])
        ]
        assert markets, "the fixture carried no markets"
        assert all(
            "yes_bid_dollars" in m and "no_bid_dollars" in m for m in markets
        ), "the wire omitted a bid field, so `field_absent` is now reachable"

    def test_a_crossed_book_is_counted_not_averaged(self):
        """A negative spread is a data state, not a negative cost."""
        tally = self._one(yes_bid_dollars="0.60", no_bid_dollars="0.60")
        assert tally.n == 0
        assert tally.excluded_crossed == 1

    def test_an_ordinary_two_sided_book_yields_the_half_spread(self):
        """The falsifier for the four above: something must get through.

        yes_bid 40.0c, no_bid 58.0c -> yes_ask 42.0c -> spread 2.0c = 20 tenths
        -> half 10.0 tenths.
        """
        tally = self._one(yes_bid_dollars="0.4000", no_bid_dollars="0.5800")
        assert tally.n == 1
        assert tally.half_spreads == [10.0]
        assert tally.median_half_spread == 10.0


class TestTheMedianRefusesToFabricateATightMarket:
    def test_no_readable_market_gives_none_and_not_zero(self):
        """0.0 would read as "perfectly tight" -- the flattering misreading of
        a measurement that did not happen."""
        assert SeriesTally(series_ticker="KXTEST").median_half_spread is None


class TestTheRegisteredDecisionRule:
    """The rule as written at §5, applied and not re-derived."""

    def test_n_is_read_before_the_effect_size(self):
        """A series under the floor could not reach the bar, so it has not
        failed it. This repo has already published one zero that meant "could
        not fire" while reading as "fired and caught nothing"."""
        assert verdict(0.1, MIN_MARKETS_FOR_A_VERDICT - 1) == "INSUFFICIENT"
        assert verdict(99.0, MIN_MARKETS_FOR_A_VERDICT - 1) == "INSUFFICIENT"

    @pytest.mark.parametrize(
        "ratio,expected",
        [
            (DEAD_RATIO, "DEAD"),
            (DEAD_RATIO + 1, "DEAD"),
            (LIVE_RATIO, "WORTH A FAIR VALUE"),
            (LIVE_RATIO - 0.5, "WORTH A FAIR VALUE"),
            ((DEAD_RATIO + LIVE_RATIO) / 2, "UNRESOLVED"),
            (None, "UNRESOLVED"),
        ],
    )
    def test_the_cut_points_are_inclusive_as_registered(self, ratio, expected):
        assert verdict(ratio, MIN_MARKETS_FOR_A_VERDICT) == expected

    def test_the_thresholds_match_the_registration(self):
        """The registration is the authority; these constants are a copy of it,
        and a copy that drifts is worse than no registration at all."""
        text = (
            ROOT
            / "docs"
            / "measurements"
            / "2026-08-15-preregistration-non-sports-spread-reachability.md"
        ).read_text(encoding="utf-8")
        assert f"`R >= {DEAD_RATIO}`" in text
        assert f"`R <= {LIVE_RATIO}`" in text
        assert f"**{MIN_MARKETS_FOR_A_VERDICT}**" in text
