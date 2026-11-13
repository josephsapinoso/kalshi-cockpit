"""The live-price copy (#436, PR #437) says what it shows and no more.

measurement-skeptic audited the PR's copy diff before merge (2026-11-13) and
returned OVERSTATED on three sentences:

- the `bid` entry named a leg's bid as an exit Joe does not hold, and priced
  a round trip at the spread alone, with no fees and no depth;
- the ticket said "No live ask ... right now" when the desk had simply not
  received a book yet, which is a claim about the venue made with no data;
- the hedge page called "the leg prices" live while each leg's chance on the
  same card was read at page load.

These tests pin the corrected wording by reading the source.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- That any of it renders correctly in a browser. The demo has no hub, so the
  lines have not been seen live (#436).
- That the corrected sentences are the only overstated ones on these screens.
  The audit covered the PR's diff, not the files' older copy.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "frontend" / "src"
GLOSSARY = (SRC / "lib" / "glossary.ts").read_text(encoding="utf-8")
TICKET = (SRC / "components" / "ManualTicket.tsx").read_text(encoding="utf-8")
HEDGE = (SRC / "components" / "HedgePositions.tsx").read_text(encoding="utf-8")


def _entry(key: str) -> str:
    m = re.search(rf"\n  {key}: \{{(.*?)\n  \}},", GLOSSARY, re.S)
    assert m, key
    return re.sub(r'"\s*\+\s*"', "", m.group(1))


class TestTheBidEntryPricesTheRoundTrip:
    def test_the_round_trip_names_a_fee_on_each_trade(self):
        assert "plus a fee each trade" in _entry("bid")

    def test_it_names_the_depth_limit(self):
        assert "Only the contracts resting at that price get it" in _entry("bid")

    def test_on_a_parlay_it_points_at_both_exit_surfaces(self):
        text = _entry("bid")
        assert "this is not your parlay" in text
        assert "check both" in text

    def test_the_old_spread_only_cost_is_gone(self):
        assert "is what buying and selling straight back would cost" not in GLOSSARY


class TestTheTicketDoesNotClaimAVenueFactWithoutABook:
    def test_no_book_says_the_desk_has_none(self):
        no_book = TICKET.index("} else if (!book) {")
        no_ask = TICKET.index("} else if (ask === null) {")
        assert no_book < no_ask, "the no-book branch must come before the no-ask one"
        assert "No live book for this market yet." in TICKET

    def test_the_no_ask_line_is_about_kalshis_book_and_dated(self):
        assert "right now." not in TICKET[TICKET.index("function LiveAskLine") :]
        assert "on Kalshi&rsquo;s\n        book{age !== null" in TICKET

    def test_a_moved_ask_carries_its_age(self):
        assert "Kalshi&rsquo;s ask moved to {ask.display}" in TICKET
        assert "The ask is now" not in TICKET


class TestTheHedgeLineNamesTheLegsOwnMarket:
    def test_the_leg_line_is_the_legs_market_not_the_position(self):
        assert "This leg&rsquo;s Kalshi market" in HEDGE
        assert "Kalshi now," not in HEDGE

    def test_the_reprice_line_says_the_chance_was_read_at_load(self):
        assert "each leg&rsquo;s chance above were read when" in HEDGE
        assert "the leg\n        prices are live" not in HEDGE
