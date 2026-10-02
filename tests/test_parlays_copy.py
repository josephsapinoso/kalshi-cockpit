"""#280: retire "tapping again later usually works"; no stale "enter-only".

WHY THIS EXISTS
---------------
The `tap_outcome` note told Joe that tapping again later "usually works". That
was a frequency nobody measured (ADR 0156), and it misread the mechanism: a
combination's book is empty between requests by design, and its price comes
from asking makers (ADR 0164). `core/ladder.py` also still restated
"enter-only", refuted 2026-09-17. And the Three props card was empty with no
explanation of what fills it.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **How often a tap or an ask returns a price.** The copy states no frequency,
  and these tests pin that absence, not any rate.
"""

from __future__ import annotations

import re
from pathlib import Path

from backend import parlays
from backend.core import ladder

REPO = Path(__file__).resolve().parents[1]


def _note() -> str:
    return parlays.NOTES["tap_outcome"]


def test_no_screen_tells_him_tapping_again_later_works() -> None:
    note = _note()
    assert "tapping again" not in note
    assert "usually works" not in note
    # No frequency word of any kind sits beside the retry advice.
    assert not re.search(r"\b(usually|typically|most of the time)\b", note)
    for path in (
        REPO / "backend" / "parlays.py",
        REPO / "frontend" / "src" / "components" / "ParlayCards.tsx",
    ):
        src = path.read_text(encoding="utf-8")
        assert "usually works" not in src, path


def test_the_tap_note_says_the_book_is_empty_by_design_and_to_ask() -> None:
    note = _note()
    assert "empty between requests by design" in note
    assert "Ask the market" in note
    # The two pins the older test holds are kept.
    assert "not a fault in the card" in note
    assert "which card is better" in note


def test_ladder_docstring_does_not_restate_enter_only_as_fact() -> None:
    doc = ladder.__doc__ or ""
    assert "combos are enter-only" not in doc
    assert "RFQ" in doc


def test_three_props_says_it_needs_a_prop_lookup() -> None:
    src = (
        REPO / "frontend" / "src" / "components" / "ParlayCards.tsx"
    ).read_text(encoding="utf-8")
    assert 'card.key === "props" && (' in src
    assert "only after a prop lookup" in src
