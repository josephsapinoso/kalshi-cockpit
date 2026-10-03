"""A held NO leg is recorded as what it pays on, not "NO -- <the YES words>".

2026-10-02: Joe's /game parlays carried "NO -- Over 47.5 points scored",
which reads as the Over. `leg_words.no_title_words` words the opposite from
the market title when its shape makes the opposite exact, and returns None
otherwise so the caller keeps the prefix.

Titles are in Kalshi's phrasing, invented teams and strikes.

What this does NOT establish: wording for any shape not listed (a whole
number strike can push, a first-half winner market has a tie outcome, a
player prop has no general opposite) -- those keep "NO -- " by design.
"""

from __future__ import annotations

import pytest

from backend.core.leg_words import no_title_words
from backend.parlay_check import _leg_label


class TestTheThreeExactShapes:
    @pytest.mark.parametrize(
        "title, words",
        [
            ("Over 47.5 points scored", "Under 47.5 points scored"),
            ("Full Game: Over 5.5 goals scored", "Full Game: Under 5.5 goals scored"),
            ("1st Half: Over 72.5 points scored", "1st Half: Under 72.5 points scored"),
            ("Alpha Tech wins by over 3.5 points", "Not: Alpha Tech wins by 4+"),
            ("Beta St. wins by over 2.5 points", "Not: Beta St. wins by 3+"),
            ("Gamma wins", "Gamma does not win"),
        ],
    )
    def test_the_opposite_is_worded(self, title, words):
        assert no_title_words(title) == words


class TestEverythingElseIsNotGuessed:
    @pytest.mark.parametrize(
        "title",
        [
            "Alpha wins the 1st half",   # a tie is a third outcome
            "Tie in the 1st half",
            "Over 3 points scored",      # a whole number can push
            "Player One: 2+ hits",
            "",
            None,
        ],
    )
    def test_no_wording_is_offered(self, title):
        assert no_title_words(title) is None


class TestTheRecordedLabel:
    def test_a_no_leg_with_a_known_shape_is_worded(self):
        titles = {"T-1": "Over 47.5 points scored"}
        assert _leg_label("T-1", "no", titles) == "Under 47.5 points scored"

    def test_a_no_leg_with_another_shape_keeps_the_prefix(self):
        titles = {"T-1": "Alpha wins the 1st half"}
        assert _leg_label("T-1", "no", titles) == "NO -- Alpha wins the 1st half"

    def test_an_untitled_no_leg_keeps_the_prefix_on_its_ticker(self):
        assert _leg_label("T-1", "no", {}) == "NO -- T-1"

    def test_a_yes_leg_is_the_title_unchanged(self):
        assert _leg_label("T-1", "yes", {"T-1": "Over 47.5 points scored"}) == (
            "Over 47.5 points scored"
        )
