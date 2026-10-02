"""/game on a phone: the Build bar is reachable without scrolling the menu (#278).

The combination panel (count, legs, Build) sits in an `<aside>` that is
sticky only from `lg` up; below it the panel lands under every leg group, so
a phone user ticked legs and then scrolled the whole menu to build. A bar
fixed to the bottom of the screen carries the count and Build below `lg`.

Source assertions (this repo has no JS test runner), the pattern of
`tests/test_game_page_copy.py`.

What these tests establish
--------------------------
- The bar is `fixed ... bottom-0` and `lg:hidden`, so it exists below the
  breakpoint and is not drawn above it.
- It shows the ticked-leg count and its button calls the SAME `build()` and
  reads the SAME disabled expression as the panel's button; there is still
  exactly one `mintGameCombo(` call.
- The page reserves room under the last row on a phone and gives the desktop
  none, and the desktop panel's own Build button is untouched.

What they do not establish
--------------------------
- That the bar clears the iOS toolbar or looks right at 390px; main checks
  that on live.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = (
    Path(__file__).resolve().parents[1]
    / "frontend" / "src" / "components" / "GameLegs.tsx"
).read_text(encoding="utf-8")


def _bar() -> str:
    start = SRC.index('aria-label="Build bar"')
    open_div = SRC.rindex("<div", 0, start)
    return SRC[open_div:]


def test_build_bar_is_reachable_below_lg():
    bar = _bar()
    head = bar[: bar.index(">")]
    # Pinned to the bottom of the screen, and drawn only below lg.
    assert re.search(r"\bfixed\b", head)
    assert "inset-x-0" in head and "bottom-0" in head
    assert "lg:hidden" in head
    # It carries the count of ticked legs.
    assert "tickedLegs.length" in bar
    assert "ticked" in bar
    # Its button is the existing build(), under the existing disabled rule.
    assert "await build()" in bar
    assert "disabled={buildDisabled}" in bar
    assert SRC.count("mintGameCombo(") == 1, "Build must reuse build(), not mint twice"
    assert SRC.count("disabled={buildDisabled}") == 2  # panel button + the bar


def test_the_desktop_layout_is_unchanged():
    # The panel and its own Build button are still there, not hidden at lg.
    assert 'aria-label="Your combination"' in SRC
    assert "Build this combination" in SRC
    assert 'lg:grid-cols-[minmax(0,1fr)_22rem]' in SRC
    assert "lg:sticky lg:top-4 lg:self-start" in SRC
    panel_button = SRC.index("Build this combination")
    assert "lg:hidden" not in SRC[SRC.rindex("<Button", 0, panel_button):panel_button]
    # Room under the last row on a phone only.
    assert "pb-24" in SRC and "lg:pb-0" in SRC
