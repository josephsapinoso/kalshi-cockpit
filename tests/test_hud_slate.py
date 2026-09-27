"""Games (slate) wears the Cockpit HUD look already live on /parlays (#174).

Joe's #173 answer (A), 2026-09-26: carry the look as it is -- `.hud` corner
brackets on a panel, headline numbers drawn in the HUD's lit-readout style
(`glow` + the indigo ink, as `ui.tsx`'s `Stat` draws with `readout` set).
Source-reading tests, in the style of `tests/test_ask_the_market_screen.py`:
there is no React test runner in this repo, so these pin what the screen's
source contains, not what paints.

Why the local `Stat` stays local
---------------------------------
`tests/test_palette_contrast.py::TestTheNeutralCountIsNotPaintedAsAVerdict`
reads a local `function Stat(` out of this file's own source (and out of
`board/page.tsx`'s) to pin that no Stat renders in the loss colour. That test
is not in this ticket's `Lane owns` list, so it is read, not edited: the
local `Stat` in `slate/page.tsx` keeps its own definition and only its look
changes to match the shared component's `readout` styling, rather than being
replaced by an import.

What this establishes
----------------------
- The screen's two headline numbers ("On the slate", "Bettable") render
  through a `Stat` whose value line carries the HUD's `glow` and indigo
  (`text-accent`) treatment -- the same classes `ui.tsx`'s `Stat` uses for
  `readout`.
- `AnchorBaseRate`'s panel -- the one bordered, `bg-card` block this screen
  owns outright -- carries the `.hud` corner-bracket class, the same
  treatment `ParlayCards.tsx`'s `Card` already has.
- `tests/test_palette_contrast.py`'s guard still finds a local `Stat` to
  read (proven by re-running it here, not merely asserted).

What this does not establish
-----------------------------
- Nothing about rendering: this is source text, not a browser. Whether the
  brackets and the glow are legible at 390px and 1440px is a live
  screenshot, which the ticket itself says only main (not a lane) can take,
  after merge.
- Nothing about every possible panel on the screen getting the treatment --
  `RefreshOddsPanel`, `TonightStrip`, `SignalStrip` and the rest are shared
  across other screens too and are out of this ticket's `Lane owns` list, so
  they are untouched here.
- Nothing about a `Segments` gauge: no number owned by this lane is a bare
  0-1 fraction rendered as a headline figure (the anchored/known ratio in
  `AnchorBaseRate` is one of several per-bucket lines, not a single screen
  figure, and the ticket's own rule is "only where" one fits).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

FRONTEND = Path(__file__).parent.parent / "frontend" / "src"
SLATE_PAGE = FRONTEND / "app" / "slate" / "page.tsx"
ANCHOR_BASE_RATE = FRONTEND / "components" / "AnchorBaseRate.tsx"
REPO_ROOT = Path(__file__).parent.parent


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _stat_body(source: str) -> str:
    return source.split("function Stat(", 1)[1].split("\n}", 1)[0]


class TestHeadlineNumbersDrawTheHudReadout:
    def test_a_local_stat_still_exists(self):
        """The palette guard below depends on this; it must stay findable."""
        assert "function Stat(" in _read(SLATE_PAGE)

    def test_the_stat_value_line_carries_the_glow_and_the_indigo_ink(self):
        body = _stat_body(_read(SLATE_PAGE))
        assert "glow" in body, "the HUD's lit-readout glow is missing"
        assert "text-accent" in body, "the readout's indigo ink is missing"
        assert "text-3xl" in body, "not drawn at the readout's larger size"

    def test_it_never_takes_the_loss_colour(self):
        assert "text-negative" not in _stat_body(_read(SLATE_PAGE))

    def test_the_comment_still_names_why_it_is_uncoloured(self):
        """`tests/test_tab_ledes.py`'s
        `TestNoCommentSaysTheAccentIsTheLossColour` reads this same local
        `Stat` for this exact phrase; caught once already when the readout
        comment was rewritten and the reason was dropped."""
        body = re.sub(r"\s+", " ", _stat_body(_read(SLATE_PAGE))).lower()
        assert "count is a fact, not a verdict" in body

    def test_both_headline_stats_are_mounted(self):
        source = _read(SLATE_PAGE)
        assert re.search(r'<Stat label="On the slate"[^/]*/>', source)
        assert re.search(r'<Stat label="Bettable"[^/]*/>', source)


class TestAPanelGetsTheCornerBrackets:
    def test_anchor_base_rate_carries_the_hud_class(self):
        """The one bordered, `bg-card` panel this lane owns outright gets the
        same `.hud` treatment `ParlayCards.tsx`'s `Card` already has (#158)."""
        source = _read(ANCHOR_BASE_RATE)
        match = re.search(r'<section className="([^"]*)"', source)
        assert match is not None, "the panel's section tag was not found"
        classes = match.group(1).split()
        assert "hud" in classes
        # Still the bordered, bg-card panel it was -- the bracket class is
        # additive, not a replacement for the panel's own look.
        assert "border" in classes and "bg-card" in classes

    def test_the_hud_class_is_defined_in_globals_css(self):
        """A guard against citing a class that does not exist: `.hud` is
        decoration owned by `globals.css`, which this ticket's `Lane owns`
        list forbids editing -- so the class this lane reaches for must
        already be there."""
        globals_css = _read(FRONTEND / "app" / "globals.css")
        assert re.search(r"^\.hud\s*\{", globals_css, re.MULTILINE)


class TestThePreExistingPaletteGuardStillPasses:
    """Run, not merely reasoned about: proof that removing nothing from the
    local `Stat` broke the guard `tests/test_palette_contrast.py` runs
    against this same file."""

    def test_test_palette_contrast_still_passes(self):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/test_palette_contrast.py",
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stdout + result.stderr
