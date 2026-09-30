"""The settled list on /bets reads like bets, not like ticker hashes (#248).

Every settled row used to lead with `KXMVECROSSCATEGOR...` in mono. Now the
row's first line says what the bet was, settled rows sit under day headings,
the ticker stays on the row as small print, and the h1 is quieter than the
net figure.

WHAT THIS ESTABLISHES
----------------------
(i)   `BetRow`'s first text node is `betLead(bet)`, and the ticker
      (`tickerLabel(bet.ticker)`) renders AFTER it, still on the row.
(ii)  `betLead` says "Combination bet" for a combo and, for a moneyline
      ticker, names both sides and the pick; the ticker regex is lifted out
      of the source and run against a real-shaped ticker, and refuses one
      whose pick is neither side (never a guessed team).
(iii) `BetSection` renders its rows through `groupByDay`, each group under
      an `<h3>` day heading, and `groupByDay` opens a new group when the day
      changes rather than sorting.
(iv)  The h1 is a smaller type step than the net figure's.
(v)   Nothing in the `<section id="open"` block was edited by this ticket:
      it is asserted to still precede the settled list.

WHAT THIS DOES NOT ESTABLISH
-----------------------------
- Rendering: source text only. Whether the rows fit at 320px was not
  measured here.
- Legs. The `/api/bets` payload carries no leg list and no team names, so a
  combination row leads with the words "Combination bet", not its legs.
  Serving legs is a backend change outside this lane.

MUTATIONS, each observed red
----------------------------
  1. lead the row with the ticker again -> (i).
  2. drop the `groupByDay` call in BetSection -> (iii).
  3. remove the ticker from the row -> (i) ticker-still-renders.
  4. let the regex accept a pick that is neither side (drop the guard) -> (ii).
  5. put the h1 back at text-4xl sm:text-5xl -> (iv).
"""

from __future__ import annotations

import re
from pathlib import Path

PAGE = (
    Path(__file__).resolve().parents[1]
    / "frontend" / "src" / "app" / "bets" / "page.tsx"
)
SRC = PAGE.read_text(encoding="utf-8").replace("\r\n", "\n")


def _body(start: str) -> str:
    i = SRC.index(start)
    return SRC[i : i + 4000]


class TestRowLeadsWithWhatTheBetWas:
    def test_first_text_of_the_row_is_the_lead_not_the_ticker(self):
        row = SRC[SRC.index("function BetRow") :]
        lead = row.index("{betLead(bet)}")
        ticker = row.index("tickerLabel(bet.ticker)")
        assert lead < ticker

    def test_ticker_still_renders_on_the_row(self):
        row = SRC[SRC.index("function BetRow") :]
        assert "tickerLabel(bet.ticker)" in row
        assert "title={bet.ticker}" in row

    def test_combination_row_says_combination_not_a_ticker(self):
        fn = _body("function betLead")
        assert re.search(
            r'kind === "combo"\) return "Combination bet"', fn
        )

    def test_game_ticker_names_both_sides_and_the_pick(self):
        pattern = re.search(r"const GAME_TICKER =\s*/(.+)/;", SRC).group(1)
        rx = re.compile(pattern)
        m = rx.match("KXMLBGAME-26AUG221805STLPHI-PHI")
        assert m is not None and m.groups() == ("STL", "PHI", "PHI")
        # a combination shard must not parse as a game
        assert rx.match("KXMVECROSSCATEGORY-SHARD1-S20266AE347C36E7-E497F938E16") is None

    def test_a_pick_that_is_neither_side_is_refused_not_guessed(self):
        fn = _body("function betLead")
        assert "m[3] !== m[1] && m[3] !== m[2]" in fn
        assert '"Single game bet"' in fn


class TestRowsAreGroupedByDay:
    def test_section_renders_through_group_by_day_with_headings(self):
        sect = SRC[SRC.index("function BetSection") : SRC.index("function MirrorNotAccount")]
        assert "groupByDay(" in sect
        assert "<h3" in sect and "{group.heading}" in sect

    def test_grouping_opens_a_group_on_day_change_and_keeps_order(self):
        fn = _body("function groupByDay")
        assert "last.key === key" in fn
        assert ".sort(" not in fn


class TestPageHeadingIsQuieterThanTheNet:
    @staticmethod
    def _step(cls: str) -> int:
        order = ["xl", "2xl", "3xl", "4xl", "5xl", "6xl"]
        return max(order.index(t) for t in re.findall(r"\btext-(\dxl|xl)\b", cls))

    def test_h1_is_a_smaller_type_step_than_the_net_figure(self):
        h1 = re.search(r'<h1 className="([^"]+)">Your bets', SRC).group(1)
        net = re.search(r"className=\{`(display [^$`]*)\$\{\s*totals\.net_tenths", SRC).group(1)
        assert self._step(h1) < self._step(net)


class TestOpenSectionUntouchedAndStillFirst:
    def test_open_section_precedes_the_settled_list(self):
        assert SRC.index('<section id="open"') < SRC.index("SECTIONS.map")
