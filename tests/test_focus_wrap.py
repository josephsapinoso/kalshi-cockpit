"""The ticket's focus trap, executed rather than read.

**The defect.** `TicketSheet.tsx` wraps Tab by comparing `document.activeElement`
against the first and last focusable elements *inside* the panel. The panel is
`tabIndex={-1}` and `node.querySelectorAll` returns descendants only, so the
panel is in neither end of that list -- while being exactly what holds focus
after `node.focus()`, which runs on open and again on every phase change.

Both comparisons were therefore false in that state, nothing called
`preventDefault`, and the browser default ran. Forward that is harmless by
accident. **Backward it walked out of the modal** -- onto the veil button, which
precedes the panel in the DOM, and from there into the page behind it.

**Why this runs `node`.** The wrong answer is another valid-looking answer: a
mapping with `first` and `last` swapped traps focus just as confidently and sends
it the wrong way. A substring assertion passes unchanged on that. So the mapping
is executed, and each clause is disabled to prove it carries weight.

What this establishes: that `focusWrap` returns the right end for all four
positions in both directions, and that the `panel` clause is what closes the
trap. Plus, by source text, that `TicketSheet.tsx` calls it and can produce the
`panel` position at all.

What it does **not** establish: that a real browser's Tab order matches the
`querySelectorAll` order (no DOM here), that the sheet's focusable list is
complete, or that focus is *placed* correctly on open -- that is the two effects
in the component, not this predicate. It also says nothing about touch, where
Tab does not exist.
"""

from __future__ import annotations

import json
import shutil
import subprocess

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MODULE = REPO / "frontend" / "src" / "lib" / "focusWrap.ts"
SHEET = REPO / "frontend" / "src" / "components" / "TicketSheet.tsx"

NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(
    NODE is None,
    reason=(
        "node is not on PATH. Skipped rather than xfailed: this guard is real "
        "where node exists (CI and both dev machines) and a missing runtime is "
        "an environment fact, not a pending failure."
    ),
)

_DRIVER = """
import {{ focusWrap }} from "{module}";
const [position, shift] = JSON.parse(process.argv[2]);
console.log(JSON.stringify({{ out: focusWrap(position, shift) }}));
"""


def wrap_of(position: str, shift: bool, *, source: str | None = None, tmp_path=None):
    """Call the shipped `focusWrap` and return where it sends focus."""
    if source is None:
        module_dir = MODULE.parent
    else:
        module_dir = tmp_path
        (module_dir / "focusWrap.ts").write_text(source, encoding="utf-8")

    driver = module_dir / "_wrap_driver.mjs"
    driver.write_text(_DRIVER.format(module="./focusWrap.ts"), encoding="utf-8")
    try:
        out = subprocess.run(
            [
                NODE,
                "--experimental-strip-types",
                str(driver),
                json.dumps([position, shift]),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(module_dir),
        )
    finally:
        driver.unlink(missing_ok=True)

    assert out.returncode == 0, (
        f"node failed running the predicate:\n{out.stdout}\n{out.stderr}"
    )
    return json.loads(out.stdout.strip())["out"]


class TestTheCaseThatWasMissing:
    """`panel` is the state on open and after every answer renders."""

    def test_shift_tab_from_the_panel_wraps_to_the_last_control(self):
        """The bug. Before the fix this returned nothing, the default ran, and
        focus left the modal backwards onto the veil."""
        assert wrap_of("panel", True) == "last"

    def test_tab_from_the_panel_goes_to_the_first_control(self):
        """Already correct by browser default; returned explicitly so it does
        not depend on DOM ordering a later markup change could reorder."""
        assert wrap_of("panel", False) == "first"

    def test_the_panel_never_lets_focus_through(self):
        """Neither direction may return null from the panel -- null is what
        hands the keypress to the browser, and backwards that leaves the sheet."""
        assert wrap_of("panel", True) is not None
        assert wrap_of("panel", False) is not None


class TestTheEndsStillWrap:
    """The behaviour that already worked must survive the fix."""

    def test_shift_tab_from_the_first_control_wraps_to_the_last(self):
        assert wrap_of("first", True) == "last"

    def test_tab_from_the_last_control_wraps_to_the_first(self):
        assert wrap_of("last", False) == "first"


class TestItDoesNotInterfereInTheMiddle:
    """Every other keypress belongs to the browser."""

    @pytest.mark.parametrize("shift", [True, False], ids=["shift", "plain"])
    def test_inside_is_left_alone(self, shift):
        assert wrap_of("inside", shift) is None

    def test_tab_from_the_first_control_is_left_alone(self):
        assert wrap_of("first", False) is None

    def test_shift_tab_from_the_last_control_is_left_alone(self):
        assert wrap_of("last", True) is None


class TestEveryClauseIsLoadBearing:
    """Disable it and watch it fail."""

    def test_dropping_the_panel_case_restores_the_escape(self, tmp_path):
        """The one that matters: without it, Shift+Tab from the panel returns
        null, the default runs, and focus walks out of the modal."""
        source = MODULE.read_text(encoding="utf-8")
        broken = source.replace(
            'return position === "first" || position === "panel" ? "last" : null;',
            'return position === "first" ? "last" : null;',
        )
        assert broken != source, "the mutation did not apply; update this test"
        assert wrap_of("panel", True, source=broken, tmp_path=tmp_path) is None

    def test_swapping_the_ends_is_caught(self, tmp_path):
        """A trap that wraps the wrong way still traps, and looks fine in the
        source. It is only visible by executing it."""
        source = MODULE.read_text(encoding="utf-8")
        broken = source.replace(
            'if (shiftKey) return position === "first" || position === "panel" '
            '? "last" : null;',
            'if (shiftKey) return position === "first" || position === "panel" '
            '? "first" : null;',
        )
        assert broken != source, "the mutation did not apply; update this test"
        assert wrap_of("first", True, source=broken, tmp_path=tmp_path) == "first"


class TestTheSheetActuallyUsesIt:
    """A correct predicate no component calls is this repo's signature defect."""

    def test_the_sheet_imports_the_predicate(self):
        assert 'from "@/lib/focusWrap"' in SHEET.read_text(encoding="utf-8")

    def test_the_sheet_calls_it_with_the_shift_key(self):
        assert "focusWrap(position, event.shiftKey)" in SHEET.read_text(
            encoding="utf-8"
        )

    def test_the_sheet_can_produce_the_panel_position(self):
        """The fix is inert unless the component recognises the panel case --
        which is the comparison the old code never made."""
        assert "active === node" in SHEET.read_text(encoding="utf-8")

    def test_the_sheet_still_prevents_the_default_when_wrapping(self):
        """Without `preventDefault` the browser moves focus too and the wrap
        lands one element off."""
        source = SHEET.read_text(encoding="utf-8")
        assert "if (wrap === null) return;" in source
        assert "event.preventDefault();" in source
