"""A bought combination's title on `/hedge` (#206).

What this does not establish: how `/hedge` lays the title out. It pins the
string both position writers store.
"""

from backend import game_builder
from backend.hedge import POSITION_TITLES, position_label


class TestAPositionTitle:
    def test_the_game_pages_key_is_the_one_given_a_title(self):
        # If game_builder's key moves, the title must move with it, or the
        # page's bets fall back to the bare key again.
        assert game_builder.CARD_KEY in POSITION_TITLES

    def test_the_game_page_reads_as_words(self):
        assert position_label("game", "KXMVE-X") == "Same-game parlay"

    def test_every_other_key_is_shown_as_it_is(self):
        assert position_label("safe", "KXMVE-X") == "safe"
        assert position_label("checked", "KXMVE-X") == "checked"

    def test_no_key_falls_back_to_the_ticker(self):
        assert position_label(None, "KXMVE-X") == "KXMVE-X"
        assert position_label("", "KXMVE-X") == "KXMVE-X"
