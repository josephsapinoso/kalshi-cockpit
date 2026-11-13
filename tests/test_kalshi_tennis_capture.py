"""Facts read from the captured Kalshi tennis payloads (#441, parent #439).

The captures in `tests/fixtures/kalshi_tennis_*.json` were taken from the public,
unauthenticated trade API on 2026-11-13. Every assertion below is computed from
those files, so a re-capture that changes the wire shape fails here instead of
leaving a typed string behind that nobody checks.

What this file does NOT establish
---------------------------------
- Nothing about matching Kalshi players to sportsbook names. That waits for the
  Odds API side of #439.
- Nothing about which tennis series are listed on another day: the series list
  is one snapshot, and the events are the first one the venue returned.
- Nothing about KXMVE pricing. The collection capture shows that tennis legs
  are *eligible*; it says nothing about whether any combination holding one
  has ever traded.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"

EVENT_TIERS = {
    "atp_main": "KXATPMATCH",
    "atp_challenger": "KXATPCHALLENGERMATCH",
    "wta_main": "KXWTAMATCH",
    "wta_challenger": "KXWTACHALLENGERMATCH",
}
ALL_FIXTURES = ["series_list", "mve_collection", *(f"event_{t}" for t in EVENT_TIERS)]


def _load(stem: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"kalshi_tennis_{stem}.json").read_text(encoding="utf-8"))


def _event(tier: str) -> dict[str, Any]:
    events = _load(f"event_{tier}")["events"]
    assert len(events) == 1
    return events[0]


class TestEveryCaptureCarriesItsRequest:
    @pytest.mark.parametrize("stem", ALL_FIXTURES)
    def test_the_fixture_has_a_request_block_with_endpoint_and_params(self, stem: str) -> None:
        request = _load(stem)["request"]
        assert request["method"] == "GET"
        assert request["endpoint"].startswith("https://")
        assert request["params"]

    @pytest.mark.parametrize("stem", ALL_FIXTURES)
    def test_the_fixture_records_how_it_was_trimmed(self, stem: str) -> None:
        assert _load(stem)["trim"]

    @pytest.mark.parametrize("tier", EVENT_TIERS)
    def test_an_event_capture_records_the_series_it_asked_for(self, tier: str) -> None:
        request = _load(f"event_{tier}")["request"]
        assert request["params"]["series_ticker"] == EVENT_TIERS[tier]
        assert request["params"]["with_nested_markets"] == "true"


class TestTheSeriesList:
    def test_tennis_is_a_tag_inside_the_sports_category(self) -> None:
        document = _load("series_list")
        assert document["request"]["params"] == {"category": "Sports"}
        assert document["series"]
        assert all("Tennis" in s["tags"] for s in document["series"])
        assert {s["category"] for s in document["series"]} == {"Sports"}

    @pytest.mark.parametrize("ticker", EVENT_TIERS.values())
    def test_each_match_series_is_listed(self, ticker: str) -> None:
        tickers = {s["ticker"] for s in _load("series_list")["series"]}
        assert ticker in tickers

    def test_challenger_matches_have_their_own_series_per_tour(self) -> None:
        by_ticker = {s["ticker"]: s for s in _load("series_list")["series"]}
        assert "Challenger" in by_ticker["KXATPCHALLENGERMATCH"]["title"]
        assert "Challenger" in by_ticker["KXWTACHALLENGERMATCH"]["title"]

    def test_the_trim_counts_agree_with_the_series_kept(self) -> None:
        document = _load("series_list")
        assert document["trim"]["tennis_series_kept"] == len(document["series"])


class TestPlayerNamesOnTheWire:
    @pytest.mark.parametrize("tier", EVENT_TIERS)
    def test_the_event_title_is_two_surnames_around_vs(self, tier: str) -> None:
        event = _event(tier)
        left, sep, right = event["title"].partition(" vs ")
        assert sep and left and right
        assert event["sub_title"].startswith(event["title"])

    @pytest.mark.parametrize("tier", EVENT_TIERS)
    def test_each_match_has_one_market_per_player(self, tier: str) -> None:
        markets = _event(tier)["markets"]
        assert len(markets) == 2
        assert len({m["yes_sub_title"] for m in markets}) == 2

    @pytest.mark.parametrize("tier", EVENT_TIERS)
    def test_yes_sub_title_carries_the_full_player_name(self, tier: str) -> None:
        for market in _event(tier)["markets"]:
            assert market["yes_sub_title"]
            assert market["title"] == f"{market['yes_sub_title']} wins"

    @pytest.mark.parametrize("tier", EVENT_TIERS)
    def test_no_sub_title_repeats_the_yes_side_player_name(self, tier: str) -> None:
        for market in _event(tier)["markets"]:
            assert market["no_sub_title"] == market["yes_sub_title"]

    @pytest.mark.parametrize("tier", EVENT_TIERS)
    def test_the_event_title_surnames_are_the_last_words_of_the_market_names(
        self, tier: str
    ) -> None:
        event = _event(tier)
        surnames = event["title"].split(" vs ")
        names = [m["yes_sub_title"] for m in event["markets"]]
        for surname, name in zip(surnames, names, strict=True):
            assert surname in name

    @pytest.mark.parametrize("tier", EVENT_TIERS)
    def test_the_market_ticker_ends_in_a_short_player_code(self, tier: str) -> None:
        event = _event(tier)
        for market in event["markets"]:
            prefix, _, code = market["ticker"].rpartition("-")
            assert prefix == event["event_ticker"]
            assert re.fullmatch(r"[A-Z]{3}", code)

    @pytest.mark.parametrize("tier", EVENT_TIERS)
    def test_the_event_ticker_encodes_series_date_and_two_player_codes(self, tier: str) -> None:
        event = _event(tier)
        series, _, tail = event["event_ticker"].partition("-")
        assert series == EVENT_TIERS[tier] == event["series_ticker"]
        assert re.fullmatch(r"\d{2}[A-Z]{3}\d{2}[A-Z]{6}", tail)


class TestTheMveCollection:
    def test_the_capture_names_the_collection_it_asked_for(self) -> None:
        document = _load("mve_collection")
        asked = document["request"]["params"]["collection_ticker"]
        assert document["multivariate_contract"]["collection_ticker"] == asked

    def test_tennis_matches_are_legs_of_the_collection(self) -> None:
        document = _load("mve_collection")
        tickers = [e["ticker"] for e in document["multivariate_contract"]["associated_events"]]
        assert any(t.startswith("KXATPMATCH-") for t in tickers)
        assert document["trim"]["tennis_prefixed_total"] >= len(tickers)

    def test_the_trimmed_event_list_is_a_subset_of_the_ticker_list(self) -> None:
        contract = _load("mve_collection")["multivariate_contract"]
        listed = set(contract["associated_event_tickers"])
        assert {e["ticker"] for e in contract["associated_events"]} <= listed
