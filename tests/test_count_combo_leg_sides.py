"""Pins `scripts/count_combo_leg_sides.py`'s pure leg classifier (#170).

Loads a **captured** combo payload (`tests/fixtures/combo_priced_markets.json`
-- a real `GET` capture, per its own `captured_note`: "no market created")
rather than a hand-written one, per `CLAUDE.md`'s wire-format rule. That
fixture is a dict with a `"combos"` list, each carrying `mve_selected_legs`;
one of them (`KXWNBASPREAD-26AUG09LVNY-NY13`) is held on the `no` side for
real, which is what makes the "every leg is YES" mutation detectable at all
-- a fixture with no NO leg anywhere could not fail that mutation.

What this does not establish
-----------------------------
Nothing about the live account's combos, the >=10% threshold in #170, or
whether pricing a NO-side moneyline leg is worth building. Only that the
classifier reads `side` off the payload instead of assuming it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.count_combo_leg_sides import (
    LegClass,
    classify_leg,
    combo_no_side_moneyline_sports,
    parse_since,
    series_ticker_of,
    tickers_first_filled_since,
)

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "tests" / "fixtures" / "combo_priced_markets.json"


def _combos() -> list[dict]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return payload["combos"]


def _all_legs() -> list[dict]:
    legs = []
    for combo in _combos():
        legs.extend(combo["mve_selected_legs"])
    return legs


class TestSeriesTickerOf:
    def test_splits_at_the_first_hyphen(self):
        assert series_ticker_of("KXNFLGAME-26AUG27NECLE") == "KXNFLGAME"
        assert series_ticker_of("KXWNBASPREAD-26AUG09LVNY") == "KXWNBASPREAD"


class TestClassifyLeg:
    def test_a_captured_moneyline_yes_leg_classifies_as_moneyline_yes(self):
        leg = {
            "event_ticker": "KXWNBAGAME-26AUG09LVNY",
            "market_ticker": "KXWNBAGAME-26AUG09LVNY-NY",
            "side": "yes",
        }
        got = classify_leg(leg)
        assert got == LegClass(
            event_ticker="KXWNBAGAME-26AUG09LVNY",
            market_ticker="KXWNBAGAME-26AUG09LVNY-NY",
            side="yes",
            market_type="moneyline",
            sport="WNBA",
        )
        assert got.is_moneyline is True
        assert got.is_no_side_moneyline is False

    def test_a_captured_no_side_spread_leg_reads_no_and_is_not_moneyline(self):
        # tests/fixtures/combo_priced_markets.json, combo 1:
        # KXWNBASPREAD-26AUG09LVNY-NY13, side "no" -- a real captured NO leg.
        leg = {
            "event_ticker": "KXWNBASPREAD-26AUG09LVNY",
            "market_ticker": "KXWNBASPREAD-26AUG09LVNY-NY13",
            "side": "no",
        }
        got = classify_leg(leg)
        assert got.side == "no"
        assert got.market_type == "spread"
        assert got.is_moneyline is False
        assert got.is_no_side_moneyline is False

    def test_a_hypothetical_no_side_moneyline_leg_is_flagged(self):
        # No such leg is in the capture (that is #170's whole finding for
        # the OLD 150-combo count) -- this pins the classifier's own logic
        # against the shape #170 says a real NFL combo carries
        # (backend/parlays.py:991 / parlay_check.py:190).
        leg = {
            "event_ticker": "KXNFLGAME-26SEP07DETGB",
            "market_ticker": "KXNFLGAME-26SEP07DETGB-DET",
            "side": "no",
        }
        got = classify_leg(leg)
        assert got.market_type == "moneyline"
        assert got.sport == "NFL"
        assert got.is_no_side_moneyline is True

    def test_side_is_read_never_defaulted(self):
        with pytest.raises(ValueError):
            classify_leg(
                {
                    "event_ticker": "KXNFLGAME-26SEP07DETGB",
                    "market_ticker": "KXNFLGAME-26SEP07DETGB-DET",
                    "side": "maybe",
                }
            )

    def test_every_captured_leg_in_the_fixture_parses_without_raising(self):
        # An anti-vacuity check on the fixture itself: if this loop classified
        # zero legs the whole test module would be exercising nothing.
        legs = _all_legs()
        assert len(legs) > 0
        for leg in legs:
            classify_leg(leg)  # must not raise


class TestComboNoSideMoneylineSports:
    def test_the_captured_combos_carry_no_no_side_moneyline_leg(self):
        # This IS the #170 finding, restated as a guard: the population
        # captured here has zero NO-side moneyline legs, which is why the
        # old "2 of 150" count needed re-deriving on a fresher population
        # rather than trusted as-is.
        for combo in _combos():
            assert combo_no_side_moneyline_sports(combo["mve_selected_legs"]) == ()

    def test_a_combo_with_a_no_side_moneyline_leg_is_flagged_by_sport(self):
        legs = [
            {
                "event_ticker": "KXWNBAGAME-26AUG09LVNY",
                "market_ticker": "KXWNBAGAME-26AUG09LVNY-NY",
                "side": "yes",
            },
            {
                "event_ticker": "KXNFLGAME-26SEP07DETGB",
                "market_ticker": "KXNFLGAME-26SEP07DETGB-DET",
                "side": "no",
            },
        ]
        assert combo_no_side_moneyline_sports(legs) == ("NFL",)

    def test_two_sports_each_contribute_once_not_once_per_leg(self):
        legs = [
            {
                "event_ticker": "KXNFLGAME-26SEP07DETGB",
                "market_ticker": "KXNFLGAME-26SEP07DETGB-DET",
                "side": "no",
            },
            {
                "event_ticker": "KXNFLGAME-26SEP07DETGB",
                "market_ticker": "KXNFLGAME-26SEP07DETGB-GB",
                "side": "no",
            },
            {
                "event_ticker": "KXMLBGAME-26AUG091335ATLNYY",
                "market_ticker": "KXMLBGAME-26AUG091335ATLNYY-ATL",
                "side": "no",
            },
        ]
        assert combo_no_side_moneyline_sports(legs) == ("MLB", "NFL")


# -- the MUTATION named in the Done-when line --------------------------------
#
# "a mutation that treats every leg as YES turns it red": simulate that
# mutation directly (rather than editing the source file) by calling the
# classifier through a wrapper that discards the real side, and show the
# assertion that would have passed on real data now fails.


def _classify_leg_with_side_forced_to_yes(leg):
    forced = dict(leg)
    forced["side"] = "yes"
    return classify_leg(forced)


class TestMutationEveryLegIsYes:
    def test_forcing_yes_hides_the_no_side_moneyline_leg(self):
        leg = {
            "event_ticker": "KXNFLGAME-26SEP07DETGB",
            "market_ticker": "KXNFLGAME-26SEP07DETGB-DET",
            "side": "no",
        }
        # The real classifier catches it.
        assert classify_leg(leg).is_no_side_moneyline is True
        # The mutated one (every leg forced to YES) does not -- this is the
        # red the ticket's Done-when line requires, produced here so CI runs
        # it every time rather than a human running it once by hand.
        assert _classify_leg_with_side_forced_to_yes(leg).is_no_side_moneyline is False


class TestTickersFirstFilledSince:
    def test_a_ticker_first_filled_before_the_cutoff_is_excluded_even_with_a_later_fill(self):
        fills = [
            {"ticker": "KXMVEA", "ts": 100},
            {"ticker": "KXMVEA", "ts": 500},
            {"ticker": "KXMVEB", "ts": 400},
        ]
        assert tickers_first_filled_since(fills, since_ts=300) == ["KXMVEB"]

    def test_a_ticker_first_filled_on_the_cutoff_is_included(self):
        fills = [{"ticker": "KXMVEC", "ts": 300}]
        assert tickers_first_filled_since(fills, since_ts=300) == ["KXMVEC"]


class TestParseSince:
    def test_parses_a_date_as_utc_midnight(self):
        import datetime

        got = parse_since("2026-09-10")
        expected = int(
            datetime.datetime(2026, 9, 10, tzinfo=datetime.timezone.utc).timestamp()
        )
        assert got == expected
