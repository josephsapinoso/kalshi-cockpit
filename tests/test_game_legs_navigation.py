"""/game/<event> scrolls a fraction of what it did (#378).

Joe, 2026-10-12: "you have to scroll so far down when you are looking at all
the prop options". Compact one-line rows, a sticky jump strip with a text
search, ladders as one picker row, rest shown once, groups collapsed.

Source assertions (this repo has no JS test runner), the pattern of
`tests/test_game_legs_layout.py`.

What these tests establish
--------------------------
- A jump strip (a `<nav>` of one chip per group, ticked-count badge) and a
  search input exist, and the search filters on text fields only.
- `RestChip` is drawn in `GameHeading` and nowhere inside `Group`.
- A group is open only when Joe searched or it holds a ticked leg; the
  initial open set is computed from the pre-ticked legs.
- Ladder rows group legs by `event_ticker`, only within a one-rung group.
- Nothing sorts, and nothing filters by chance, price or rest (ADR 0071).

What they do not establish
--------------------------
- That the page is short at 390px or that the strip sticks under the site
  header; main checks that on live.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = (
    Path(__file__).resolve().parents[1]
    / "frontend" / "src" / "components" / "GameLegs.tsx"
).read_text(encoding="utf-8")


def _code() -> str:
    src = re.sub(r"/\*.*?\*/", "", SRC, flags=re.DOTALL)
    src = re.sub(r"\{/\*.*?\*/\}", "", src, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", src, flags=re.MULTILINE)


def _function(name: str) -> str:
    code = _code()
    start = code.index(f"function {name}(")
    nxt = re.search(r"\n(?:export default )?function \w+\(", code[start + 1:])
    return code[start: start + 1 + nxt.start()] if nxt else code[start:]


class TestJumpStripAndSearch:
    def test_a_jump_strip_with_one_chip_per_group_exists(self):
        strip = _function("JumpStrip")
        assert "<nav" in strip and "sticky" in strip
        assert "groups.map((group)" in strip
        assert "onJump(group)" in strip
        # A ticked-count badge rides on the chip.
        assert "tickedHere" in strip

    def test_a_jump_opens_the_group_then_scrolls_to_it(self):
        code = _code()
        jump = code[code.index("const jumpTo"): code.index("const toggle")]
        assert "[group.series]: true" in jump
        assert "scrollIntoView" in jump

    def test_a_search_input_exists_and_the_page_mounts_the_strip(self):
        strip = _function("JumpStrip")
        assert 'type="search"' in strip
        assert re.search(r"<JumpStrip[\s/>]", _function("GameLegs"))

    def test_search_is_case_insensitive_text_over_title_labels_and_player(self):
        match = _function("legMatches")
        assert "toLowerCase()" in match
        for field in ("leg.title", "leg.yes_label", "leg.no_label", "leg.player"):
            assert field in match
        # Text only: no chance, price, ask or rest in the predicate.
        for banned in ("chance", "ask", "price", "rest", "sides"):
            assert banned not in match, banned

    def test_the_only_filter_is_the_search_predicate(self):
        filters = re.findall(r"\.filter\(([^\n]*)", _code())
        # The tickedLegs type-guard filter is not a leg filter; every other
        # filter over legs goes through legMatches.
        leg_filters = [f for f in filters if "legMatches" in f]
        assert leg_filters, "search must filter through legMatches"
        for f in filters:
            assert not re.search(r"chance|ask_|price|rest\b", f), f


class TestRestIsShownOnce:
    def test_rest_chip_is_in_the_heading_and_not_in_group(self):
        assert "<RestChip" in _function("GameHeading")
        for name in ("Group", "LegDetails", "SideButton"):
            assert "RestChip" not in _function(name), name
        assert _code().count("<RestChip") == 1


class TestGroupsStartCollapsed:
    def test_a_group_is_open_only_when_searching_or_opened(self):
        code = _code()
        assert "open={searching || openGroups[group.series] === true}" in code
        # The old "open if it has 12 or fewer legs" default is gone.
        assert "legs.length <= 12" not in code

    def test_groups_holding_a_ticked_leg_start_open(self):
        code = _code()
        fetch = code[code.index("fetchGameLegs(eventTicker)"):]
        fetch = fetch[: fetch.index("}, [eventTicker])")]
        assert "preTick(initialLegs, payload)" in fetch
        assert "market_ticker in wanted" in fetch
        assert "setOpenGroups(opened)" in fetch


class TestLaddersAreOneRow:
    def test_rungs_sharing_an_event_ticker_make_one_row(self):
        rows = _function("rowsOf")
        assert "group.one_per_event" in rows
        assert "byEvent.get(leg.event_ticker)" in rows
        assert "existing.legs.push(leg)" in rows

    def test_a_non_ladder_group_stays_one_row_per_leg(self):
        rows = _function("rowsOf")
        assert "legs.map((leg) => ({ key: leg.market_ticker" in rows

    def test_ticking_a_rung_still_blocks_the_others(self):
        group = _function("Group")
        assert "takenBy.set(leg.event_ticker, market)" in group
        assert "disabled={sideBlocked}" in _function("SideButton")


class TestNothingIsRankedOrHidden:
    def test_no_sort(self):
        assert ".sort(" not in SRC
        assert ".toSorted(" not in SRC

    def test_the_combined_chance_sentence_stays(self):
        assert "NO_COMBINED_CHANCE_LINE" in SRC
        assert "shows no " in SRC and "combined chance" in SRC
