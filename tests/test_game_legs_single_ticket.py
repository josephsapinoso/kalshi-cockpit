"""Every leg on /game/<event> can be bet alone (#356).

`GameLegs.tsx` is a parlay builder; a straight bet on a spread, a total or a
moneyline used to need a second leg. Each leg row now mounts the hand-bet
`<ManualTicket>` on that leg's own market and on the side the row names, the
pattern `ParlayCards.tsx` and `MarketSearch.tsx` already use.

Source assertions (this repo has no JS test runner).

What these tests establish
--------------------------
- The ticket is mounted inside the per-leg map, with `ticker={leg.market_ticker}`
  and `preferSide={side}` where `side` is the loop's own allowed side, never a
  constant or a computed "better" side.
- It is mounted only when that side's listed ask is readable, because
  `ManualTicket` quietly falls back to the OTHER side when the preferred one has
  no ask; a row must not open on a contract it did not name.
- A side with no desk chance carries MarketSearch's wording that his own
  number is the only estimate.
- `ManualTicket.tsx` is not edited and the leg order is still the server's.

What they do not establish
--------------------------
- That the ticket looks right at 390px, or that a bet placed from it fills.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "frontend" / "src" / "components" / "GameLegs.tsx").read_text(
    encoding="utf-8"
)


def _leg_map() -> str:
    # #378: the per-leg body moved out of the Group map into LegDetails; the
    # anchor follows it, the assertions below are unchanged.
    start = SRC.index("function LegDetails(")
    return SRC[start:]


class TestEveryLegCanBeBetAlone:
    def test_a_leg_row_mounts_the_ticket_on_its_own_market_and_side(self):
        body = _leg_map()
        assert "<ManualTicket" in body
        tag = body[body.index("<ManualTicket"):]
        tag = tag[: tag.index("/>")]
        assert "ticker={leg.market_ticker}" in tag
        assert "preferSide={side}" in tag
        assert "Bet this one alone" in tag
        # `side` is the allowed-sides loop variable, not a constant.
        before = body[: body.index("<ManualTicket")]
        loop = before[before.rindex("leg.allowed_sides.map((side)"):]
        # Gated on a readable ask for that very side (no silent side fallback).
        assert "if (askTenths === null) return null" in loop

    def test_a_leg_with_no_desk_chance_says_his_own_number_is_the_only_estimate(self):
        body = _leg_map()
        assert "your own number is the only estimate there is" in body
        assert "facts.chance === null" in body or "facts.chance !== null" in body

    def test_the_page_names_a_single_with_its_glossary_term(self):
        assert '<Term k="single">' in SRC

    def test_the_server_order_is_not_resorted(self):
        assert ".sort(" not in SRC
