"""Picks wears the Cockpit HUD look already live on /parlays (#175).

Joe's #173 answer (A), 2026-09-26: carry the look as it is -- `.hud` corner
brackets on a panel, headline numbers drawn in the HUD's lit-readout style
(`glow` + the indigo ink, as `ui.tsx`'s `Stat` draws with `readout` set),
`Segments` only where a number is a bare 0-1 fraction. Source-reading tests,
in the style of `tests/test_hud_slate.py` (#174): there is no React test
runner in this repo, so these pin what the screen's source contains, not
what paints.

Why no `Stat readout` and no `Segments` on this screen
--------------------------------------------------------
`/picks` keeps no local `Stat` function and mounts none of `ui.tsx`'s
either: `tests/test_picks_screen.py::test_no_headline_counting_how_many_ranked`
forbids the one count ("how many picks ranked") a screen like this would
otherwise lead with, so there is no headline number to draw as a readout.
The cash/cap line is the same running prose the Games screen's own money
paragraph is, and #174 left that paragraph untouched on Games too -- this
lane does the same. No number on this screen is a bare 0-1 fraction
rendered as a headline figure either (`PicksAnchorBaseRate`'s per-league
lines are counts, "N of M", not fractions, and there are several of them,
not one screen figure), so no `Segments` gauge is added.

What this establishes
----------------------
- The three bordered, `bg-card` panels this screen owns outright --
  `PicksAnchorBaseRate`'s section, and the page's own "Not available on
  this instance" and "Nothing ranked" empty-state sections -- all carry the
  `.hud` corner-bracket class, the same treatment `ParlayCards.tsx`'s `Card`
  and `AnchorBaseRate`'s panel (#174) already have.
- `tests/test_picks_screen.py`'s and `tests/test_anchor_base_rate.py`'s
  existing guards still pass (proven by re-running them here, not merely
  asserted).

What this does not establish
-----------------------------
- Nothing about rendering: this is source text, not a browser. Whether the
  brackets are legible at 390px and 1440px is a live screenshot, which the
  ticket itself says only main (not a lane) can take, after merge.
- Nothing about every panel on the screen getting the treatment --
  `TonightStrip`, `GoodChancePicks`, `RefreshWhenPriced`, `RecordParlay` and
  `FilterBar` are shared with other screens and are out of this ticket's
  `Lane owns` list, so they are untouched here.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from tests.test_picks_screen import code_only

FRONTEND = Path(__file__).parent.parent / "frontend" / "src"
PICKS_PAGE = FRONTEND / "app" / "picks" / "page.tsx"
PICKS_ANCHOR_BASE_RATE = FRONTEND / "components" / "PicksAnchorBaseRate.tsx"
REPO_ROOT = Path(__file__).parent.parent


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _sections(source: str) -> list[list[str]]:
    """Every `<section className="...">` opening tag's class list, in
    source order."""
    return [
        m.group(1).split()
        for m in re.finditer(r'<section className="([^"]*)"', source)
    ]


class TestPanelsThisScreenOwnsGetTheCornerBrackets:
    def test_picks_anchor_base_rate_carries_the_hud_class(self):
        """The one bordered, `bg-card` panel `PicksAnchorBaseRate` owns
        outright gets the same `.hud` treatment `AnchorBaseRate`'s panel got
        in #174."""
        source = _read(PICKS_ANCHOR_BASE_RATE)
        sections = _sections(source)
        assert len(sections) == 1, "expected exactly one <section> in this file"
        classes = sections[0]
        assert "hud" in classes
        # Still the bordered, bg-card panel it was -- the bracket class is
        # additive, not a replacement for the panel's own look.
        assert "border" in classes and "bg-card" in classes

    def test_both_empty_state_panels_on_the_page_carry_the_hud_class(self):
        """The two empty-state sections ("Not available on this instance",
        "Nothing ranked") are the other bordered, `bg-card` panels this
        screen owns outright."""
        source = _read(PICKS_PAGE)
        sections = _sections(source)
        assert len(sections) == 2, (
            f"expected exactly two <section> tags on the picks page, found "
            f"{len(sections)}"
        )
        for classes in sections:
            assert "hud" in classes
            assert "border" in classes and "bg-card" in classes

    def test_the_hud_class_is_defined_in_globals_css(self):
        """A guard against citing a class that does not exist: `.hud` is
        decoration owned by `globals.css`, which this ticket's `Lane owns`
        list forbids editing -- so the class this lane reaches for must
        already be there."""
        globals_css = _read(FRONTEND / "app" / "globals.css")
        assert re.search(r"^\.hud\s*\{", globals_css, re.MULTILINE)


class TestNoStatReadoutAndNoSegmentsBecauseNoneFit:
    def test_no_local_or_imported_stat_component(self):
        """This screen keeps no headline count to draw as a readout
        (`test_no_headline_counting_how_many_ranked` forbids the one it
        would otherwise lead with), so it mounts no `Stat` at all. Read with
        `code_only` so this very guard's own explanation cannot fail itself
        (the `test_crew_bubble` lesson `tests/test_picks_screen.py` names)."""
        text = code_only(_read(PICKS_PAGE))
        assert "function Stat(" not in text, "a local Stat was added"
        assert "<Stat " not in text and "<Stat\n" not in text, (
            "the shared Stat is mounted despite no headline number to draw"
        )
        assert '"@/components/ui"' not in text, (
            "ui.tsx is imported from despite this ticket's Lane owns list "
            "not needing a shared component here"
        )

    def test_no_segments_gauge(self):
        text = code_only(_read(PICKS_PAGE))
        assert "Segments" not in text
        anchor_text = code_only(_read(PICKS_ANCHOR_BASE_RATE))
        assert "Segments" not in anchor_text


class TestThePreExistingGuardsStillPass:
    """Run, not merely reasoned about: proof that adding `.hud` to three
    sections broke nothing `tests/test_picks_screen.py` and
    `tests/test_anchor_base_rate.py` check over these same files."""

    def test_test_picks_screen_still_passes(self):
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "tests/test_picks_screen.py"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_test_anchor_base_rate_still_passes(self):
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "tests/test_anchor_base_rate.py"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stdout + result.stderr
