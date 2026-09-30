"""No screen lists a hand-bet brake that no longer exists.

ADR 0112 removed the five brakes on the hand-bet path on 2026-09-08 (cool-off,
daily-loss switch, per-bet / position / exposure caps, one contract at a time).
Four screens went on saying they were still there for three weeks; this pins
the copy, not the wiring (``test_scope_sentences.py`` pins the wiring).

Comments are stripped before the match: they may name a removed brake to say
why it is gone, and only text a person can read on the screen is the claim.

What this does not establish: that the copy left is true. It refuses a short
list of known-false phrases in six files; a new false sentence in another file
passes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "frontend" / "src"

GATE = SRC / "app" / "gate" / "page.tsx"
SLATE = SRC / "app" / "slate" / "page.tsx"
PICKS = SRC / "app" / "picks" / "page.tsx"
CHART = SRC / "components" / "RecordChart.tsx"
STEPS = SRC / "components" / "FiveStepTest.tsx"
FOOTER = SRC / "components" / "Footer.tsx"


def visible_text(path: Path) -> str:
    """Source with block and line comments removed (JSX ``{/* */}`` included)."""
    src = path.read_text(encoding="utf-8")
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r"(?m)(^|\s)//[^\n]*", r"\1", src)
    return re.sub(r"\s+", " ", src)


REMOVED_BRAKE_PHRASES = [
    "cool-off",
    "cool off",
    "daily-loss",
    "daily loss",
    "one contract at a time",
    "Your cap",
    "the caps above",
    "No caps can be derived",
    "stay inside the cap",
    "at risk at once",
]

HAND_BET_SCREENS = [GATE, SLATE, PICKS]


# The Gate's status paragraph (the engine's own sizing) still names a
# daily-loss switch, which gate.py does have; ADR 0112 removed the hand-bet
# copy of it, so that phrase is refused on the other two screens only.
ENGINE_ONLY = {"daily-loss", "daily loss"}
CASES = [
    (path, phrase)
    for path in HAND_BET_SCREENS
    for phrase in REMOVED_BRAKE_PHRASES
    if not (path == GATE and phrase in ENGINE_ONLY)
]


@pytest.mark.parametrize(
    "path,phrase", CASES, ids=lambda v: v.parent.name if isinstance(v, Path) else v
)
def test_screen_does_not_name_a_removed_brake(path: Path, phrase: str) -> None:
    text = visible_text(path)
    assert phrase.lower() not in text.lower(), f"{path.name} still says {phrase!r}"


def test_gate_names_the_rfq_accept_as_a_door() -> None:
    text = visible_text(GATE).lower()
    assert "third" in text and "accept" in text and "quote" in text


def test_record_chart_does_not_call_its_dashed_line_a_floor() -> None:
    assert "floor" not in visible_text(CHART).lower()
    # the docstring said "lower bound" of the same line; comments are where
    # the claim was first made, so it is checked raw too
    assert "floor" not in CHART.read_text(encoding="utf-8").lower()


def test_playbook_steps_do_not_point_at_the_deleted_estimate_field() -> None:
    text = visible_text(STEPS)
    assert "P(YES)" not in text
    assert "p_yes" not in text
    assert "lifetime stop" not in text


def test_footer_does_not_send_him_to_a_ticket_that_asks() -> None:
    assert "the ticket asks" not in visible_text(FOOTER)
