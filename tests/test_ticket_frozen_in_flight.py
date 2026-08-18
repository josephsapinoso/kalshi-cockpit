"""The ticket's two inputs are frozen while an order is in flight.

**The defect.** Confirm's disabled set has carried `phase === "sending"` all
along. The stepper's did not (`disabled={!actionable}`) and the token input had
no `disabled` at all. `confirm` closes over `contracts`, so the size that was
*sent* was always right -- but the screen was not. Tapping `-` mid-send
re-rendered the sheet at the new number, withdrew four money figures to "—", and
could show or hide the depth warning, while a request for the old size was still
out. The answer then came back naming a size the ticket had stopped displaying.

**What this file is and is not.** These are source-text assertions, and the
repo's own rule is that a substring test is the right tool for *"does the
component read this"* and worth nothing for *"does this reach the right answer"*.
That split is why the two predicates shipped alongside this change
(`tests/test_bet_direction.py`, `tests/test_focus_wrap.py`) are executed under
node instead. There is no predicate here to execute -- the change is a term added
to two boolean expressions -- and no DOM test runner in this repo to observe a
disabled attribute with.

So: this establishes that the guard is *present* in both places and that it is
spelled the same way as the one on Confirm. It does **not** establish that React
renders the attribute, that a real tap is refused, or that the request in flight
carries the size the screen shows. Deleting either guard fails these tests;
breaking React would not.
"""

from __future__ import annotations

import re

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SHEET = REPO / "frontend" / "src" / "components" / "TicketSheet.tsx"

SENDING = 'phase === "sending"'


def source() -> str:
    return SHEET.read_text(encoding="utf-8")


class TestTheStepperIsFrozen:
    def test_the_stepper_is_disabled_while_sending(self):
        block = re.search(r"<Stepper\b.*?/>", source(), re.S)
        assert block is not None, "the Stepper element moved; update this test"
        assert SENDING in block.group(0)

    def test_the_stepper_still_respects_actionable(self):
        """The new term is added to the old one, not swapped for it."""
        block = re.search(r"<Stepper\b.*?/>", source(), re.S)
        assert block is not None
        assert "!actionable" in block.group(0)


class TestTheTokenInputIsFrozen:
    def test_the_token_input_is_disabled_while_sending(self):
        block = re.search(r'<input\s+id="ticket-token".*?/>', source(), re.S)
        assert block is not None, "the token input moved; update this test"
        assert f"disabled={{{SENDING}}}" in block.group(0)

    def test_the_disabled_state_is_visible(self):
        """A control that stops responding without looking different reads as a
        broken control rather than a busy one."""
        block = re.search(r'<input\s+id="ticket-token".*?/>', source(), re.S)
        assert block is not None
        assert "disabled:opacity-40" in block.group(0)


def confirm_button() -> str:
    """The Confirm control, which is not the only button calling `confirm`.

    "Try again" also calls it (`secondaryAction(result) === "retry"`), so a
    regex anchored on `onClick={confirm}` alone matches the wrong one. That
    button carries no `phase` guard and needs none: it renders only while
    `phase === "answered"`, and tapping it moves the phase to `sending`, which
    replaces the whole footer branch it lives in.

    Anchored on the busy label instead, which only Confirm has.
    """
    chunks = [c for c in source().split("<button") if "Asking the server" in c]
    assert len(chunks) == 1, "the Confirm button moved; update this test"
    return chunks[0]


class TestAllThreeControlsAgree:
    def test_confirm_was_already_frozen_and_still_is(self):
        """The guard this change copied. If it ever leaves Confirm, the other
        two are guarding a door that no longer exists."""
        assert SENDING in confirm_button()

    def test_confirm_announces_that_it_is_busy(self):
        """`aria-busy` is the only signal a screen-reader user gets that the
        frozen controls are frozen on purpose."""
        assert f"aria-busy={{{SENDING}}}" in confirm_button()

    # A `source().count(SENDING) >= 3` assertion sat here and was deleted rather
    # than kept. Disabling both new guards left it green -- the phrase already
    # appears five times in this file for unrelated reasons (the busy ref, the
    # Close button, `aria-busy`, the Confirm predicate, the button label). A
    # guard that survives its own removal is decoration, and the two
    # per-control tests above already make the claim it was reaching for.
