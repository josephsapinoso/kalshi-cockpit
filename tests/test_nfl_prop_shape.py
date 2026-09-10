"""What the NFL prop ladder actually looks like, pinned to a captured payload.

Every claim here is asserted against `tests/fixtures/events_nfl_props_nested.json`
-- a verbatim, unauthenticated Kalshi `/events` capture taken 2026-09-10 by
`scripts/capture_nfl_prop_fixture.py`. Nothing is hand-constructed, per
CLAUDE.md's wire-format rule.

WHAT THIS ESTABLISHES
---------------------
That the MLB subtitle grammar and the MLB join identity hold on NFL yardage
props, so the repo needed no second parser; and that the touchdown series carry
no strike, so their refusal is a property of the payload rather than a gap in
the regex.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Nothing about liquidity or fillability.** The fixture is event metadata.
- **Nothing about the book side of the join.** Whether a sportsbook quotes
  these players at these lines is unmeasured and costs credits to answer.
- **Nothing about `KXNFLANYTD`'s shape.** It had zero open events at capture.
- **Nothing about a later slate.** A field present on one night's ladder is not
  a contract; that is what makes this a pinned artefact rather than a refresh.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.kalshi.props import (
    MLB_PROP_SERIES,
    NFL_PROP_SERIES,
    PROP_SERIES,
    PROP_SERIES_NO_STRIKE,
    is_prop_series,
    parse_subtitle,
)

FIXTURE = Path(__file__).parent / "fixtures" / "events_nfl_props_nested.json"

#: The three series the capture found a rung on.
YARDAGE = ("KXNFLPASSYDS", "KXNFLRECYDS", "KXNFLRSHYDS")


@pytest.fixture(scope="module")
def captured() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _markets(captured: dict, series: str) -> list[dict]:
    out = []
    for event in captured["events_by_series"].get(series) or []:
        out.extend(event.get("markets") or [])
    return out


class TestTheCaptureIsWhatItClaims:
    def test_it_holds_all_five_series(self, captured: dict) -> None:
        assert set(captured["events_by_series"]) == set(YARDAGE) | set(
            PROP_SERIES_NO_STRIKE
        )

    def test_every_yardage_series_stored_markets(self, captured: dict) -> None:
        # A series that captured nothing would make every claim below vacuous.
        for series in YARDAGE:
            assert _markets(captured, series), f"{series} stored no markets"


class TestTheMlbGrammarHoldsOnNfl:
    """`"Player: N+"` — the finding is that NFL needed no second parser."""

    @pytest.mark.parametrize("series", YARDAGE)
    def test_every_yardage_subtitle_parses(self, captured: dict, series: str) -> None:
        markets = _markets(captured, series)
        unreadable = [
            m["ticker"]
            for m in markets
            if parse_subtitle(m.get("yes_sub_title")) is None
        ]
        assert unreadable == [], f"{len(unreadable)} unparsed in {series}"

    @pytest.mark.parametrize("series", YARDAGE)
    def test_floor_strike_is_the_threshold_minus_a_half(
        self, captured: dict, series: str
    ) -> None:
        """The join needs no arithmetic — Kalshi publishes the book's `point`.

        This is the identity the whole props join rests on. It was measured on
        259 of 259 MLB markets; here it is asserted per market so a Kalshi
        change turns a test red instead of shifting every prop by one rung.
        """
        for market in _markets(captured, series):
            reading = parse_subtitle(market.get("yes_sub_title"))
            assert reading is not None
            floor = market.get("floor_strike")
            assert floor is not None, f"{market['ticker']} has no floor_strike"
            assert float(floor) == pytest.approx(reading[1] - 0.5)

    @pytest.mark.parametrize("series", YARDAGE)
    def test_the_ladder_is_a_greater_than_strike(
        self, captured: dict, series: str
    ) -> None:
        kinds = {m.get("strike_type") for m in _markets(captured, series)}
        assert kinds == {"greater"}

    @pytest.mark.parametrize("series", YARDAGE)
    def test_every_market_carries_an_occurrence_time(
        self, captured: dict, series: str
    ) -> None:
        # Without it `event_commence_ms` is None and discovery rejects the
        # whole event, so a prop ladder that lacked it could not be matched to
        # a fixture at all.
        missing = [
            m["ticker"] for m in _markets(captured, series)
            if not m.get("occurrence_datetime")
        ]
        assert missing == []

    def test_the_league_string_is_pro_football(self, captured: dict) -> None:
        # One unexpected league string has already cost this repo 48 events
        # and 726 markets.
        for series in YARDAGE:
            for event in captured["events_by_series"][series]:
                metadata = event.get("product_metadata") or {}
                assert (metadata.get("competition") or "").strip() == "Pro Football"

    def test_the_scope_is_the_statistic(self, captured: dict) -> None:
        scopes = {
            series: {
                ((e.get("product_metadata") or {}).get("competition_scope") or "").strip()
                for e in captured["events_by_series"][series]
            }
            for series in YARDAGE
        }
        assert scopes == {
            "KXNFLPASSYDS": {"Passing Yards"},
            "KXNFLRECYDS": {"Receiving Yards"},
            "KXNFLRSHYDS": {"Rushing Yards"},
        }


class TestTheTouchdownSeriesCarryNoRung:
    """The refusal is a property of the payload, not a gap in the regex."""

    def test_first_td_publishes_no_floor_strike(self, captured: dict) -> None:
        markets = _markets(captured, "KXNFLFIRSTTD")
        assert markets, "the negative case captured nothing"
        assert all(m.get("floor_strike") is None for m in markets)

    def test_first_td_subtitles_are_bare_player_names(self, captured: dict) -> None:
        # `"Kyren Williams"`, not `"Kyren Williams: 1+"`. `parse_subtitle`
        # returning None on all of them is the correct refusal — loosening the
        # regex to admit them would invent a rung Kalshi never published.
        for market in _markets(captured, "KXNFLFIRSTTD"):
            assert parse_subtitle(market.get("yes_sub_title")) is None

    def test_first_td_strike_type_is_structured(self, captured: dict) -> None:
        kinds = {m.get("strike_type") for m in _markets(captured, "KXNFLFIRSTTD")}
        assert kinds == {"structured"}

    def test_anytd_shape_is_not_claimed(self, captured: dict) -> None:
        # 0 open events at capture. This test exists so that an absent series
        # is never silently read as a measured one.
        assert captured["events_by_series"]["KXNFLANYTD"] == []
        assert captured["observed_full_response"]["KXNFLANYTD"]["events"] == 0


class TestTheLiveAllowlistHasNotMoved:
    """NFL is staged, not enabled. This is the guard on that.

    Merging `NFL_PROP_SERIES` into `PROP_SERIES` changes what `discovery.py`
    admits on live, and the buy side cannot follow until `backend/odds/` thaws
    at 10:00Z 2026-09-14. These tests fail the moment someone flips one half.
    """

    def test_prop_series_is_still_mlb_only(self) -> None:
        assert PROP_SERIES == MLB_PROP_SERIES

    def test_no_nfl_series_is_admitted_by_discovery_yet(self) -> None:
        for series in NFL_PROP_SERIES:
            assert not is_prop_series(series)

    def test_the_no_strike_series_are_admitted_by_nothing(self) -> None:
        for series in PROP_SERIES_NO_STRIKE:
            assert not is_prop_series(series)
            assert series not in NFL_PROP_SERIES

    def test_the_staged_mapping_covers_exactly_the_yardage_series(self) -> None:
        assert set(NFL_PROP_SERIES) == set(YARDAGE)

    def test_the_staged_keys_are_the_vendors_own_spelling(self) -> None:
        # Read from the vendor's market table on 2026-09-10. A wrong key does
        # not error — it buys nothing — so it is pinned rather than trusted.
        assert NFL_PROP_SERIES == {
            "KXNFLPASSYDS": "player_pass_yds",
            "KXNFLRECYDS": "player_reception_yds",
            "KXNFLRSHYDS": "player_rush_yds",
        }
