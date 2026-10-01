"""The game page's copy (#202), pinned as source text.

This repo has no JS test runner (`frontend/package.json` has no test script),
so these are assertions over the source of `GameLegs.tsx`, the repo's pattern
for frontend claims (`tests/test_token_proxy_routes.py`).

What they establish: the component says, in its own words, that the desk does
not know how the legs of one game move together and therefore shows no
combined chance; says an extra leg is one more thing a maker can charge for;
and reads no combined-chance field off any payload -- the shape it is typed
against (`GameLegs` in `lib/api.ts`) carries none either.

What they do NOT establish: that the sentence renders, that it is readable at
phone width, or that the backend never adds such a field (that is
`tests/test_game_builder.py::test_the_listing_carries_no_combined_chance`).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend" / "src"
COMPONENT = SRC / "components" / "GameLegs.tsx"
API = SRC / "lib" / "types" / "parlays.ts"

#: Words that would mean a combined number is being read or drawn. `joint`
#: covers `joint_chance`, `fair_joint` and `joint_probability`; the rest are
#: the field names the parlay cards read theirs from.
FORBIDDEN = re.compile(
    r"joint|conservative|fair_cost|hold_display|chance_every",
    re.IGNORECASE,
)


def _strip_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", source, flags=re.MULTILINE)


def _game_types(source: str) -> str:
    """The `GameLeg*`/`GameLegs`/`GameMint*` type blocks in `lib/api.ts`."""
    blocks = re.findall(
        r"export type Game\w+ = \{.*?^\};", source, flags=re.DOTALL | re.MULTILINE
    )
    return "\n".join(blocks)


class TestTheWordsAreThere:
    def test_the_component_says_the_desk_does_not_know_how_the_legs_move_together(
        self,
    ):
        source = COMPONENT.read_text(encoding="utf-8")
        assert "doesn't know how these legs move together" in source
        assert "shows no " in source and "combined chance" in source
        assert "The makers' quote prices that in." in source

    def test_the_sentence_is_rendered_not_just_defined(self):
        source = _strip_comments(COMPONENT.read_text(encoding="utf-8"))
        assert "{NO_COMBINED_CHANCE_LINE}" in source

    def test_an_extra_leg_is_one_more_thing_a_maker_can_charge_for(self):
        source = COMPONENT.read_text(encoding="utf-8")
        assert "Each extra leg is one more thing a maker can charge for." in source
        assert "{EXTRA_LEG_LINE}" in _strip_comments(source)

    def test_the_new_betting_term_goes_through_term(self):
        source = COMPONENT.read_text(encoding="utf-8")
        assert 'k="same_game_parlay"' in source
        glossary = (SRC / "lib" / "glossary.ts").read_text(encoding="utf-8")
        assert re.search(r"^  same_game_parlay: \{", glossary, flags=re.MULTILINE)


class TestNoCombinedChanceIsReadOrDrawn:
    def test_the_component_names_no_joint_or_fair_joint_field(self):
        source = COMPONENT.read_text(encoding="utf-8")
        hits = FORBIDDEN.findall(source)
        assert not hits, f"GameLegs.tsx mentions {sorted(set(hits))}"

    def test_the_payload_type_carries_none_either(self):
        types = _game_types(API.read_text(encoding="utf-8"))
        assert "GameLegs" in types and "GameLegSide" in types, "the scan found no types"
        hits = FORBIDDEN.findall(_strip_comments(types))
        assert not hits, f"the game payload type names {sorted(set(hits))}"

    def test_nothing_in_the_component_sorts_or_ranks(self):
        """The order is the server's (ADR 0071). A `.sort(` here could only be
        re-ordering what the server already fixed."""
        source = _strip_comments(COMPONENT.read_text(encoding="utf-8"))
        assert ".sort(" not in source and ".toSorted(" not in source


class TestTheScoutDeskIsOnTapOnly:
    def test_the_component_mounts_the_scout_desk_and_never_sends_it(self):
        source = _strip_comments(COMPONENT.read_text(encoding="utf-8"))
        assert "<ScoutDesk ticker=" in source
        assert "sendScoutDesk" not in source
