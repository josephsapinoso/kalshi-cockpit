"""Willy Balters' seat: no numbers, no tools, honest absences (ADR 0069).

The convening mechanics (four metered calls, reserve ordering) live in
`tests/test_scout_desk.py`; this module owns the seat's own contract:

- **No number can leave the seat.** `SharpTake` is walked exactly as
  `DeskBriefing` is — a schema is enforcement, a prompt is guidance.
- **The seat carries no tools.** The search budget belongs to the staff,
  and `STAFF_PAIR_SEARCHES_WORST_CASE` is the whole convening's worst case
  only while that stays true. Pinned by source, mutation-verified.
- **The fiction stays a fiction.** Willy Balters, never the living
  professional the name winks at — the same pin `test_crew_bubble.py`
  holds for the free row voice.
- **An unaffordable seat is an absence with a reason**, never a downgraded
  briefing: `status` semantics are unchanged from the three-call desk.
"""

from __future__ import annotations

import re
import typing
from pathlib import Path

from backend.agents.base import AgentConfig
from backend.agents.pro_bettor import SYSTEM, SharpTake

ROOT = Path(__file__).resolve().parents[1]
SCOUT_DESK_SRC = ROOT / "backend" / "agents" / "scout_desk.py"
WILLY_UI = ROOT / "frontend" / "src" / "components" / "ScoutDesk.tsx"

CONFIG = AgentConfig(api_key="test", model="claude-opus-5")


class TestNoNumberCanLeaveTheSeat:
    def test_the_take_schema_is_prose_only_all_the_way_down(self):
        """Walked, not trusted — the `DeskBriefing` walker, applied to
        `SharpTake`. A numeric field added anywhere fails here."""
        from pydantic import BaseModel as PydanticBase

        def leaves(annotation):
            args = typing.get_args(annotation)
            if not args:
                yield annotation
            for arg in args:
                yield from leaves(arg)

        def check_model(model, path):
            for name, field in model.model_fields.items():
                where = f"{path}.{name}"
                for leaf in leaves(field.annotation):
                    if isinstance(leaf, type) and issubclass(leaf, PydanticBase):
                        check_model(leaf, where)
                        continue
                    if isinstance(leaf, str):
                        continue  # a Literal member: words, never numbers
                    assert not isinstance(leaf, (int, float, complex)), (
                        f"{where} has a numeric Literal member {leaf!r}; the "
                        f"seat must not have a field a forecast could hide in"
                    )
                    assert leaf not in (int, float, complex), (
                        f"{where} can carry a number; the seat must not have "
                        f"a field a forecast could hide in"
                    )
                    assert leaf in (str, list, type(None)), (
                        f"{where} has unexpected leaf {leaf!r}; keep the "
                        f"take words-only"
                    )

        check_model(SharpTake, "SharpTake")

    def test_the_prompt_carries_the_two_hard_rules_verbatim(self):
        """A system prompt is the one place a rule must be present to exist
        at all — the same clause `scout_desk.py` records for its copies."""
        assert "must NOT estimate any probability" in SYSTEM
        assert "must not say whether any bet is good" in SYSTEM
        assert "must not add facts" in SYSTEM


class TestTheSeatCarriesNoTools:
    def test_the_willy_call_passes_no_tools(self):
        """The search-budget guard: `STAFF_PAIR_SEARCHES_WORST_CASE` is the
        convening's worst case only because this call cannot search. The
        pin is over the seat's own call block — handing it
        `WEB_SEARCH_TOOL` turns this red."""
        source = SCOUT_DESK_SRC.read_text(encoding="utf-8")
        # The seat's block: from the pro_bettor reserve to its settle.
        match = re.search(
            r"agent=\"pro_bettor\".*?budget\.settle\(\s*sharp_id",
            source,
            flags=re.DOTALL,
        )
        assert match, "the pro_bettor call block was not found"
        assert "tools=" not in match.group(0), (
            "the pro's seat carries a tools argument — the search brake's "
            "worst case no longer covers the convening"
        )


class TestTheFictionStaysAFiction:
    def test_the_ui_names_willy_and_never_the_real_person(self):
        text = WILLY_UI.read_text(encoding="utf-8")
        assert "Willy Balters" in text
        assert "Billy Walters" not in text, (
            "the desk seat must not wear a living person's name — "
            "the character is a fiction (test_crew_bubble.py holds the "
            "same pin for the row voice)"
        )

    def test_the_backend_persona_is_the_fiction_too(self):
        assert "Willy Balters" in SYSTEM
        assert "Billy Walters" not in SYSTEM
        assert "not a real person" in SYSTEM
