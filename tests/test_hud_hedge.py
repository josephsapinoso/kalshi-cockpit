"""/hedge wears the Cockpit HUD look already live on /parlays (#177).

Joe's #173 answer (A), 2026-09-26: carry the look as it is -- `.hud`
corner brackets on the screen's main panels. Source-reading tests, in the
style of `tests/test_hud_slate.py` and `tests/test_hud_picks.py`: there is
no React test runner in this repo, so these pin what the screen's source
contains, not what paints.

Why /hedge gets less than Games and Picks did
-----------------------------------------------
CLAUDE.md's "/hedge watches what Joe already holds" section is explicit: the
figure this screen shows for a hedge or a lock is "an estimate pinned in
neither direction, not a lock and not a bound," and the words to refuse on
it are "ceiling, floor, conservative, at least, can only be smaller/larger."
The HUD's `readout` (glow + indigo ink) and `Segments` (a lit-cell gauge)
are both *emphasis* -- exactly what a figure that is not a lock must not
receive, on ADR 0071 section 2.5's rule that a per-row fact may be shown but
never dressed up as a verdict. So:

- The main per-ticket panel (`Position`, the direct analogue of
  `ParlayCards.tsx`'s `Card`, which already has `.hud`) and the venue
  coverage banner (a status panel this screen owns outright, the same kind
  of block Picks put brackets on) get the `.hud` corner-bracket class.
- No headline number on this screen is converted to `Stat readout`: unlike
  Games and Picks, `/hedge` has no plain headline count to begin with --
  `positions.length` is never rendered as a number of its own, only as
  prose ("No tickets recorded...") or as a collapsed `<details>` count. The
  ticket's own rule is "if there's no plain headline count, add none."
- No `Segments` gauge is added anywhere. The only 0-1-fraction-shaped
  figures on this screen (`chance_display` on a leg or a de-risk block) are
  pre-formatted display strings the server rendered, not a raw fraction the
  client could feed a gauge, and every one of them is exactly the kind of
  hedge-estimate figure this ticket says must not be dressed up.

What this establishes
----------------------
- `Position`'s wrapping `<section>` and `VenueCoverageBanner`'s wrapping
  `<div>` in `HedgePositions.tsx` carry the `.hud` class, additively (their
  existing `border`/`rounded` classes are untouched).
- No money/estimate figure anywhere in `HedgePositions.tsx` -- the
  `EstimateHeadline` figure, the `Ladder`/`Rung` costs, `StakeBasisLine`,
  `ComboBookLine`, `SellQuote`'s best-bid line -- carries `glow`,
  `text-accent`, or a `Segments`/`segments` class.
- `tests/test_palette_contrast.py` still passes, re-run here.

What this does not establish
-----------------------------
- Nothing about rendering: this is source text, not a browser. Whether the
  brackets read cleanly at 390px and 1440px, especially nested inside the
  collapsed settled-tickets `<details>`, is a live screenshot, which the
  ticket itself says only main (not a lane) can take, after merge.
- Nothing about `hedge/page.tsx` itself needing a class change: it renders
  no bordered panel of its own (`HedgePositions` and the shared
  `RecordParlay` do), so this ticket's `.hud` additions are entirely inside
  `HedgePositions.tsx`.
- Nothing about `RecordParlay.tsx`: it is rendered by four screens
  (`/bets`, `/hedge`, `/picks`, `/slate`) and is out of this ticket's `Lane
  owns` list, so it is read, never edited, here.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

FRONTEND = Path(__file__).parent.parent / "frontend" / "src"
HEDGE_PAGE = FRONTEND / "app" / "hedge" / "page.tsx"
HEDGE_POSITIONS = FRONTEND / "components" / "HedgePositions.tsx"
RECORD_PARLAY = FRONTEND / "components" / "RecordParlay.tsx"
REPO_ROOT = Path(__file__).parent.parent


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _function_body(source: str, name: str) -> str:
    """The full text of one top-level `function <name>(...) { ... }`,
    including its params, found by brace-counting from the function's own
    opening `{` (a destructured-params function like `Position` has a
    `\\n}` of its own -- the type annotation's closing brace -- long before
    the function body ends, so the naive "split on the first `\\n}`"
    `test_hud_slate.py` uses for a single-line-params function is not
    enough here)."""
    marker = f"function {name}("
    start = source.index(marker)
    paren_open = start + len(marker) - 1
    depth = 0
    paren_close = None
    for i in range(paren_open, len(source)):
        if source[i] == "(":
            depth += 1
        elif source[i] == ")":
            depth -= 1
            if depth == 0:
                paren_close = i
                break
    assert paren_close is not None, f"no matching ')' found for {marker!r}"
    brace = source.index("{", paren_close)
    depth = 0
    for i in range(brace, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start : i + 1]
    raise AssertionError(f"no matching closing brace found for {marker!r}")


class TestTheMainPanelsGetTheCornerBrackets:
    def test_position_section_carries_the_hud_class(self):
        """The per-ticket panel -- the direct analogue of `ParlayCards.tsx`'s
        `Card`, which already has `.hud` -- gets the same treatment."""
        body = _function_body(_read(HEDGE_POSITIONS), "Position")
        match = re.search(r'<section[^>]*className="([^"]*)"', body)
        assert match is not None, "Position's <section> tag was not found"
        classes = match.group(1).split()
        assert "hud" in classes
        # Additive, not a replacement: still the same bordered panel.
        assert "border" in classes and "rounded-lg" in classes

    def test_venue_coverage_banner_carries_the_hud_class(self):
        """The venue-coverage status panel this screen owns outright, the
        same kind of block Picks put brackets on for its empty states."""
        body = _function_body(_read(HEDGE_POSITIONS), "VenueCoverageBanner")
        match = re.search(r'<div[^>]*className="([^"]*)"', body)
        assert match is not None, "VenueCoverageBanner's <div> tag was not found"
        classes = match.group(1).split()
        assert "hud" in classes
        assert "border" in classes and "rounded-lg" in classes

    def test_the_hud_class_is_defined_in_globals_css(self):
        """A guard against citing a class that does not exist: `.hud` is
        decoration owned by `globals.css`, which this ticket's `Lane owns`
        list forbids editing -- so the class this lane reaches for must
        already be there."""
        globals_css = _read(FRONTEND / "app" / "globals.css")
        assert re.search(r"^\.hud\s*\{", globals_css, re.MULTILINE)


class TestNoHedgeEstimateFigureIsDressedUpAsAVerdict:
    """CLAUDE.md: the hedge/lock figure is "an estimate pinned in neither
    direction, not a lock and not a bound." The HUD's `readout` glow and its
    `Segments` gauge are both emphasis a figure like that must not carry."""

    @staticmethod
    def _all_class_lists(source: str) -> list[list[str]]:
        """Every `className="..."` attribute's classes, as separate lists --
        checking class *tokens*, not raw substrings, so this guard cannot be
        tripped by the word appearing in a comment explaining why it is
        absent (as it does, deliberately, right beside the panels this
        ticket did add `.hud` to)."""
        return [
            m.group(1).split()
            for m in re.finditer(r'className="([^"]*)"', source)
        ]

    def test_no_glow_class_appears_on_any_element(self):
        for classes in self._all_class_lists(_read(HEDGE_POSITIONS)):
            assert "glow" not in classes

    def test_no_readout_indigo_ink_on_any_figure(self):
        for classes in self._all_class_lists(_read(HEDGE_POSITIONS)):
            assert "text-accent" not in classes

    def test_no_segments_gauge_is_added(self):
        source = _read(HEDGE_POSITIONS)
        assert "<Segments" not in source
        assert "className=\"segments" not in source

    def test_the_estimate_headline_figure_is_unstyled_by_this_ticket(self):
        """`EstimateHeadline` draws the one dollar figure this screen ever
        leads with. Pin its value line stays the plain size it was --
        `text-lg`, no `glow`, no `text-accent` -- so a later change cannot
        quietly promote it to the readout look."""
        body = _function_body(_read(HEDGE_POSITIONS), "EstimateHeadline")
        match = re.search(r"figure \? \(\s*<p className=\"([^\"]*)\"", body)
        assert match is not None, "EstimateHeadline's figure <p> was not found"
        classes = match.group(1).split()
        assert "glow" not in classes
        assert "text-accent" not in classes


class TestNoMoneySpendingButtonChangedColour:
    """The Rules: "the indigo fill marks only a button that spends money"
    and this ticket must not touch any button that spends. `/hedge` has no
    such button -- `Close`'s "done with this ticket" and `SellQuote`'s "what
    would makers pay?" both ask, never spend -- so none of them should carry
    the indigo fill class this ticket did not add and must not add."""

    def test_no_button_on_the_screen_carries_the_accent_fill(self):
        source = _read(HEDGE_POSITIONS)
        assert "bg-accent-fill" not in source


class TestRecordParlayStaysUntouched:
    """Shared with `/bets`, `/picks` and `/slate` -- out of this ticket's
    `Lane owns` list."""

    def test_record_parlay_is_not_edited_by_this_ticket(self):
        # A weak but honest guard given no git history is available inside
        # a test: the component renders no `.hud` class of its own, because
        # this ticket adds none there. A real diff check happens in review.
        source = _read(RECORD_PARLAY)
        assert ".hud" not in source and 'className="hud' not in source


class TestThePreExistingPaletteGuardStillPasses:
    """Run, not merely reasoned about: proof that this ticket's edits did
    not break the guard `tests/test_palette_contrast.py` runs."""

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
