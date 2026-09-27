"""Your bets wears the Cockpit HUD look already live on /parlays (#176).

Joe's #173 answer (A), 2026-09-26: carry the look as it is -- `.hud` corner
brackets on a panel, headline numbers drawn in the HUD's lit-readout style
(the `glow` text-shadow `ui.tsx`'s `Stat` draws with `readout` set). Source
-reading tests, in the style of `tests/test_hud_slate.py`: there is no React
test runner in this repo, so these pin what the screen's source contains,
not what paints.

Why the net figure keeps its own colour, not the shared `Stat`'s ink
----------------------------------------------------------------------
`ui.tsx`'s `Stat` with `readout` set always paints the value `text-accent`
(indigo). The two headline counts #174 lit up on /slate carried no colour of
their own, so trading their plain ink for the readout's indigo lost nothing.
This screen's headline number is different: it is Joe's own net, already
coloured `text-negative`/`text-positive` by whether the whole mirrored
record is a win or a loss -- a real fact about the money, not a hunting
verdict, and the kind of colour `tests/test_palette_contrast.py`'s
`TestOneColourMeansOneThing` and `TestTheNeutralCountIsNotPaintedAsAVerdict`
exist to keep meaningful. Forcing it to the readout's indigo would erase
that distinction to match a look Joe asked to carry "as it is" (#173),
not to change what a number means. So the net figure gets `glow` -- the
HUD's lit-readout text-shadow, which `globals.css` defines as a fixed
accent-tinted shadow independent of the text's own colour -- and keeps its
win/loss ink. It is not built through the shared `Stat` component, because
`Stat` has no way to keep `readout`'s sizing and glow while overriding its
ink.

What this establishes
----------------------
- The one bordered, `bg-card` panel this screen owns outright -- the net
  strip -- carries the `.hud` corner-bracket class, the same treatment
  `ParlayCards.tsx`'s `Card` and `AnchorBaseRate`'s panel (#174) already
  have.
- The screen's headline number (the net figure) carries the HUD's `glow`
  class, at the readout's `text-3xl` size, alongside its existing
  win/loss colouring -- which the class list still proves is present,
  unchanged.
- `tests/test_palette_contrast.py`'s guards still pass (proven by re
  -running them here, not merely asserted): this file does not touch
  `board/page.tsx` or `slate/page.tsx`, and does not add a local
  `function Stat(` for that guard to find in `bets/page.tsx`, which it
  does not scan.

What this does not establish
-----------------------------
- Nothing about rendering: this is source text, not a browser. Whether the
  brackets and the glow are legible at 390px and 1440px is a live
  screenshot, which the ticket itself says only main (not a lane) can take,
  after merge.
- Nothing about every panel or number on the screen getting the treatment
  -- `OpenPositions`, `RecordChart`, `RecordParlay`, `NotTonight` and
  `RecordChart`'s cumulative chart are shared or out of this ticket's
  `Lane owns` list (`RecordParlay` in particular is shared with /hedge,
  /slate and /picks, per main's note), so they are untouched here.
- Nothing about a `Segments` gauge: no number this lane touched is a bare
  0-1 fraction rendered as a headline figure (the net is a signed dollar
  amount, and the per-section "N of M carry the desk's chance" line is a
  count, not a headline), so the ticket's own "only where" rule does not
  fire.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

FRONTEND = Path(__file__).parent.parent / "frontend" / "src"
BETS_PAGE = FRONTEND / "app" / "bets" / "page.tsx"
REPO_ROOT = Path(__file__).parent.parent


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _net_panel(source: str) -> str:
    # From the net strip's opening div through its closing </div> is more
    # than a regex can safely bound (nested divs inside), so this grabs the
    # panel's opening tag and the net span specifically, the two pieces this
    # ticket actually changed.
    return source.split('<div className="hud rounded-2xl', 1)[1][:4000]


class TestThePanelGetsTheCornerBrackets:
    def test_the_net_strip_carries_the_hud_class(self):
        """The one bordered, `bg-card` panel this screen owns outright."""
        source = _read(BETS_PAGE)
        match = re.search(r'<div className="([^"]*)">\s*\n\s*<div className="text-xs font-semibold uppercase tracking-widest text-muted">\s*\n\s*<Term k="net">', source)
        assert match is not None, "the net strip panel was not found"
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


class TestTheNetFigureCarriesTheReadoutGlow:
    def _net_span(self) -> str:
        source = _read(BETS_PAGE)
        # The net span is the first `<span className={...display...}` after
        # the net strip's own heading -- bounded to a short window so a
        # later, unrelated span in the file cannot accidentally match.
        window = source.split('<Term k="net">Net</Term>, over the whole mirrored record', 1)[1][:1400]
        match = re.search(r"<span\s+className=\{`([^`]*)`\}", window)
        assert match is not None, "the net value span was not found"
        return match.group(1)

    def test_it_carries_the_glow_class(self):
        assert "glow" in self._net_span()

    def test_it_is_drawn_at_the_readout_size(self):
        assert "text-3xl" in self._net_span()

    def test_it_still_carries_its_win_loss_colour(self):
        """The readout's own indigo ink is deliberately NOT forced here --
        see this file's module docstring. Both branches of the conditional
        must survive the HUD pass."""
        body = self._net_span()
        assert "text-negative" in body
        assert "text-positive" in body

    def test_it_does_not_take_the_readout_indigo(self):
        """`ui.tsx`'s `Stat` with `readout` set always paints `text-accent`.
        This figure keeps its own win/loss ink instead (see module
        docstring), so `text-accent` must not appear on it."""
        assert "text-accent" not in self._net_span()


class TestThePreExistingPaletteGuardStillPasses:
    """Run, not merely reasoned about: proof that adding `.hud` and `glow`
    broke neither of `tests/test_palette_contrast.py`'s guards."""

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
