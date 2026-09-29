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


# -- #198: --by-kind ---------------------------------------------------------
#
# Legs below are taken from captured payloads. Moneyline / spread / total /
# other legs come from `combo_priced_markets.json`'s `mve_selected_legs`. No
# captured `mve_selected_legs` carries a leg whose series is in `PROP_SERIES`
# (its one prop-shaped leg, `KXWNBAPTS`, is not a registered prop series, which
# is itself the `other:` test), so the prop legs wrap the REAL captured event
# and market tickers of `events_mlb_props_nested.json` /
# `events_nfl_props_nested.json` in the same three-key leg shape.

from scripts.count_combo_leg_sides import (  # noqa: E402
    census_by_kind,
    classify_leg_kind,
    combo_is_same_game,
    format_by_kind,
    game_key,
)

FIXTURES = REPO / "tests" / "fixtures"


def _captured_leg(series: str, side: str | None = None) -> dict:
    """First captured leg under `series` in combo_priced_markets.json."""
    for leg in _all_legs():
        if leg["event_ticker"].split("-")[0] == series and (
            side is None or leg["side"] == side
        ):
            return dict(leg)
    raise AssertionError(f"no captured {series} leg (side={side})")


def _captured_prop_leg(events_fixture: str, series: str, side: str = "yes") -> dict:
    data = json.loads((FIXTURES / events_fixture).read_text(encoding="utf-8"))
    event = data["events_by_series"][series][0]
    return {
        "event_ticker": event["event_ticker"],
        "market_ticker": event["markets"][0]["ticker"],
        "side": side,
    }


class TestByKind:
    def test_moneyline_yes_is_priced(self):
        got = classify_leg_kind(_captured_leg("KXMLBGAME", "yes"))
        assert (got.sport, got.kind, got.side) == ("MLB", "moneyline", "yes")
        assert got.desk_prices_kind is True

    def test_moneyline_no_side_is_not_priced(self):
        leg = _captured_leg("KXMLBGAME")
        leg["side"] = "no"
        got = classify_leg_kind(leg)
        assert got.kind == "moneyline" and got.side == "no"
        assert got.desk_prices_kind is False

    def test_spread_is_a_spread_and_priced_on_a_real_no_leg(self):
        got = classify_leg_kind(_captured_leg("KXWNBASPREAD", "no"))
        assert (got.sport, got.kind, got.side) == ("WNBA", "spread", "no")
        assert got.desk_prices_kind is True

    def test_total_is_a_total_and_priced(self):
        got = classify_leg_kind(_captured_leg("KXMLBTOTAL", "no"))
        assert (got.sport, got.kind, got.side) == ("MLB", "total", "no")
        assert got.desk_prices_kind is True

    def test_a_prop_is_prop_stat_and_priced_when_the_feed_buys_the_stat(self):
        leg = _captured_prop_leg("events_mlb_props_nested.json", "KXMLBKS")
        got = classify_leg_kind(leg)
        assert (got.sport, got.kind) == ("MLB", "prop:pitcher_strikeouts")
        assert got.desk_prices_kind is True

    def test_an_nfl_prop_reads_its_own_stat(self):
        leg = _captured_prop_leg("events_nfl_props_nested.json", "KXNFLRECYDS")
        got = classify_leg_kind(leg)
        assert (got.sport, got.kind) == ("NFL", "prop:player_reception_yds")
        assert got.desk_prices_kind is True

    def test_a_prop_stat_outside_the_feed_markets_is_not_priced(self, monkeypatch):
        from backend.odds import client as odds_client

        # The feed stops buying NFL keys: the stat is still a prop by series,
        # but no sport's market keys carry it.
        monkeypatch.setitem(
            odds_client.PROP_MARKET_KEYS_BY_SPORT, "americanfootball_nfl", ()
        )
        leg = _captured_prop_leg("events_nfl_props_nested.json", "KXNFLPASSYDS")
        got = classify_leg_kind(leg)
        assert got.kind == "prop:player_pass_yds"
        assert got.desk_prices_kind is False
        # An MLB stat is unaffected.
        mlb = classify_leg_kind(
            _captured_prop_leg("events_mlb_props_nested.json", "KXMLBTB")
        )
        assert mlb.desk_prices_kind is True

    def test_an_unregistered_series_is_other_never_dropped(self):
        # KXWNBAPTS is in a real captured combo and is not in PROP_SERIES.
        got = classify_leg_kind(_captured_leg("KXWNBAPTS"))
        assert got.kind == "other:KXWNBAPTS"
        assert got.sport == "UNKNOWN"
        assert got.desk_prices_kind is False
        tennis = classify_leg_kind(_captured_leg("KXATPMATCH"))
        assert tennis.kind == "other:KXATPMATCH"

    def test_a_no_strike_prop_series_is_other(self):
        leg = _captured_prop_leg("events_nfl_props_nested.json", "KXNFLFIRSTTD")
        assert classify_leg_kind(leg).kind == "other:KXNFLFIRSTTD"

    def test_side_is_still_refused_when_unreadable(self):
        leg = _captured_leg("KXMLBGAME")
        leg["side"] = "maybe"
        with pytest.raises(ValueError):
            classify_leg_kind(leg)


class TestByKindSameGame:
    def test_a_moneyline_plus_a_prop_series_of_one_game_is_same_game(self):
        # Captured combo 0: KXWNBAGAME + KXWNBAPTS + KXWNBASPREAD, all
        # `-26AUG09LVNY`. Three DIFFERENT series, one game.
        legs = _combos()[0]["mve_selected_legs"]
        assert len({leg["event_ticker"] for leg in legs}) == 3
        assert combo_is_same_game(legs) is True

    def test_a_raw_event_ticker_compare_would_have_said_no(self):
        legs = _combos()[0]["mve_selected_legs"]
        tickers = [leg["event_ticker"] for leg in legs]
        assert len(tickers) == len(set(tickers))  # what a raw compare sees
        assert game_key(tickers[0]) == game_key(tickers[1]) == game_key(tickers[2])

    def test_a_multi_game_combo_is_not_same_game(self):
        # Captured: three MLB moneylines on three different fixtures.
        combo = next(
            c["mve_selected_legs"]
            for c in _combos()
            if [leg["event_ticker"] for leg in c["mve_selected_legs"]]
            == [
                "KXMLBGAME-26AUG091415COLSTL",
                "KXMLBGAME-26AUG091605DETSF",
                "KXMLBGAME-26AUG092020HOUSD",
            ]
        )
        assert combo_is_same_game(combo) is False


class TestCensusAndReport:
    def _census(self):
        return census_by_kind([c["mve_selected_legs"] for c in _combos()])

    def test_counts_are_combos_carrying_the_leg_not_legs(self):
        census = self._census()
        assert census.n_combos == len(_combos())
        count, priced = census.cells[("MLB", "moneyline", "yes")]
        expected = sum(
            any(
                leg["event_ticker"].startswith("KXMLBGAME") and leg["side"] == "yes"
                for leg in c["mve_selected_legs"]
            )
            for c in _combos()
        )
        assert count == expected and priced is True

    def test_same_game_count_over_the_captured_combos(self):
        census = self._census()
        expected = sum(combo_is_same_game(c["mve_selected_legs"]) for c in _combos())
        assert census.n_same_game == expected
        assert expected >= 1

    def test_top_unpriced_kind_is_reported(self):
        text = format_by_kind(self._census(), skipped=2, since_text="2026-09-10")
        assert "combos unreadable/skipped     : 2" in text
        assert "top unpriced kind" in text
        assert "desk_prices_kind=NO" in text
        assert "same-game combos" in text

    def test_empty_population_does_not_divide_by_zero(self):
        text = format_by_kind(census_by_kind([]), skipped=0, since_text="2026-09-10")
        assert "NOT COMPUTABLE" in text
