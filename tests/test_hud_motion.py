"""HUD slice 4: a sweep when a scout answer lands (#182, last slice of #171).

Joe's #171 pick was "more pop" -- one small motion, once, when a leg
verdict (TAKE or PASS) lands on a parlay card, honouring
`prefers-reduced-motion`. Source-reading tests, in the style of
`tests/test_hud_bets.py` and `tests/test_hud_hedge.py`: there is no React
test runner in this repo, so these pin what the source contains, not what
paints.

**"Lands" here means the verdict element mounts fresh.** `LegVerdicts.tsx`
polls every 5s and reuses the same React key (`ticker:side`) across polls,
so a naive "apply the class whenever state is cached" would replay the
sweep on every poll tick once a verdict is already in. The fix keys each
line on `ticker:side:waiting-or-answered` instead: the key changes exactly
once, the instant a leg's state first reads `cached`, forcing a fresh DOM
node so the CSS animation (which plays automatically on any new element,
the same trick `.animate-in`/`.sheet-rise` already use elsewhere in this
file) fires once and does not replay on a later poll of the same answer.
This also covers "on load": a verdict already `cached` on first render
mounts fresh too, so the sweep plays then as well -- the ticket allows
this ("fresh from a request, or on load").

Three guards, each proven red by mutation before being proven green:

(a) The keyframes/animation apply only under
    `prefers-reduced-motion: no-preference` -- there is no unconditional
    rule that would need a separate `reduce` override to null out.
(b) The class that triggers the sweep is applied identically for TAKE and
    PASS -- unconditional on `isPass`, and not keyed to the verdict, the
    edge, the gap, the chance display or rank (ADR 0071 section 2.5).
(c) The sweep runs once: no `infinite`, and an explicit finite iteration
    count on the animation shorthand.

WHAT THIS DOES NOT ESTABLISH
-----------------------------
- That the sweep actually renders, or is visible at 390px/1440px on a real
  card -- that needs a browser main takes after merge (the ticket's own
  "Done when" line).
- That `PriceOnKalshi.tsx`'s rendering of the same component also shows the
  sweep -- it renders `<LegVerdicts>` unmodified, so whatever this file
  proves about the shared component applies there for free, and this file
  does not re-derive it.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FRONTEND = REPO / "frontend" / "src"
GLOBALS_CSS = FRONTEND / "app" / "globals.css"
LEG_VERDICTS = FRONTEND / "components" / "LegVerdicts.tsx"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _strip_css_comments(css: str) -> str:
    """A comment explaining why a forbidden token is absent must not itself
    trip the check for that token -- same rule `test_leg_verdicts_ui.py`'s
    `_strip_comments` applies to `.tsx` source."""
    return re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)


def _sweep_block(css: str) -> str:
    """The `no-preference`-gated block that defines `.verdict-sweep`, from
    its opening `@media` line through the matching closing brace. Bounded
    by brace-counting rather than a fixed slice, so a later edit to this
    block (more comments, a longer gradient) does not silently shrink the
    window this test reads."""
    start = css.index("@media (prefers-reduced-motion: no-preference)")
    depth = 0
    i = css.index("{", start)
    block_start = i
    while True:
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
            if depth == 0:
                return css[start : i + 1]
        i += 1
        if i >= len(css):
            raise AssertionError("unbalanced braces reading the sweep block")


class TestTheSweepIsGatedOnReducedMotion:
    """Guard (a). Mutation observed red: delete the
    `@media (prefers-reduced-motion: no-preference)` wrapper (or move the
    `.verdict-sweep::after` rule outside it) -- the animation then applies
    unconditionally and this fails."""

    def test_the_keyframes_and_animation_live_inside_no_preference(self):
        css = _read(GLOBALS_CSS)
        block = _sweep_block(css)
        assert "@keyframes verdict-sweep" in block
        assert re.search(r"animation:\s*verdict-sweep", block)

    def test_no_unconditional_verdict_sweep_rule_exists_outside_the_media_block(self):
        css = _read(GLOBALS_CSS)
        block = _sweep_block(css)
        outside = css.replace(block, "")
        assert "verdict-sweep" not in outside, (
            "a `.verdict-sweep` rule exists outside the "
            "`prefers-reduced-motion: no-preference` block -- it would apply "
            "even when the visitor asked for reduced motion"
        )

    def test_the_class_is_defined_in_globals_css(self):
        """A guard against citing a class that does not exist, the same
        check `test_hud_bets.py` runs for `.hud`."""
        css = _read(GLOBALS_CSS)
        block = _sweep_block(css)
        assert re.search(r"\.verdict-sweep(::after)?\s*\{", block)


class TestTheSweepIsIdenticalForTakeAndPass:
    """Guard (b). Mutation observed red: change
    `className="verdict-sweep text-xs leading-snug"` to something
    conditioned on `isPass` (e.g. only apply it in the PASS branch, or
    interpolate `isPass` into the class list) -- this fails."""

    def test_verdict_sweep_is_applied_unconditionally_on_ispass(self):
        source = LEG_VERDICTS.read_text(encoding="utf-8")
        assert 'className="verdict-sweep text-xs leading-snug"' in source, (
            "the cached-verdict line's class list does not carry an "
            "unconditional 'verdict-sweep' -- either it is missing, or it "
            "has been made conditional on the verdict"
        )

    def test_the_sweep_class_never_appears_inside_the_ispass_conditional(self):
        """The one place `isPass` gates anything in this file is the TAKE/
        PASS span's own colour (`isPass ? "font-semibold text-accent-2" :
        "font-semibold"}`) -- `verdict-sweep` must not be pulled into that
        ternary or any other `isPass`-keyed expression."""
        source = LEG_VERDICTS.read_text(encoding="utf-8")
        for match in re.finditer(r"isPass\s*\?[^:]*:[^,;\n]*", source):
            assert "verdict-sweep" not in match.group(0)

    def test_the_sweep_is_not_keyed_to_edge_gap_chance_or_rank(self):
        """ADR 0071 section 2.5, restated by #182's own body: nothing about
        the trigger may read an edge, a gap, a chance figure or a rank.
        None of these four tokens appear in this file at all today, so this
        pins the absence directly rather than trying to scope a search to
        "near the sweep" -- any future edit that introduces one of them
        anywhere in the file is exactly the defect this guards against."""
        source = LEG_VERDICTS.read_text(encoding="utf-8").lower()
        for token in ("edge", "gap", "chance", "rank"):
            assert token not in source, (
                f"{token!r} appears in LegVerdicts.tsx -- the sweep trigger "
                f"must not be keyed to it"
            )


class TestTheSweepRunsOnce:
    """Guard (c). Mutation observed red: change the animation shorthand's
    iteration count to `infinite` -- this fails on both assertions."""

    def test_the_animation_shorthand_has_no_infinite_iteration(self):
        css = _read(GLOBALS_CSS)
        block = _strip_css_comments(_sweep_block(css))
        assert "infinite" not in block

    def test_the_animation_shorthand_names_a_finite_iteration_count(self):
        css = _read(GLOBALS_CSS)
        block = _sweep_block(css)
        match = re.search(
            r"animation:\s*verdict-sweep\s+[\d.]+s\s+[\w-]+\s+(\d+)\s+both",
            block,
        )
        assert match is not None, (
            "the animation shorthand does not name an explicit finite "
            "iteration count between the timing function and `both`"
        )
        assert int(match.group(1)) == 1


class TestTheKeyChangesExactlyOnceOnArrival:
    """The mechanism guard (b) and (c) both depend on: the sweep is wired
    to *arrival*, via a key that flips from "waiting" to "answered" the
    moment a leg's state first reads `cached`, and never flips back or
    re-fires on a later poll of the same cached answer.

    Mutation observed red: revert the key back to
    `${row.ticker}:${row.side}` (dropping the state suffix) -- the sweep
    would then never mount at all, since the key never changes when a leg
    goes from `pending` to `cached`."""

    def test_the_key_is_keyed_on_state_becoming_cached(self):
        source = LEG_VERDICTS.read_text(encoding="utf-8")
        assert (
            '`${row.ticker}:${row.side}:${row.state === "cached" ? '
            '"answered" : "waiting"}`'
            in source
        )

    def test_the_bare_ticker_side_key_is_gone(self):
        """The old key must not survive alongside the new one -- two
        `<LegVerdictLine key=...>` sites would mean only one of them
        actually renders the list `shown.map` produces."""
        source = LEG_VERDICTS.read_text(encoding="utf-8")
        assert 'key={`${row.ticker}:${row.side}`}' not in source


class TestEveryTestThatReadsTheTouchedFilesStaysGreen:
    """Run, not merely reasoned about -- the #172 lesson this ticket cites
    by name: grep `tests/` for the two touched filenames first, then prove
    every hit still passes."""

    def test_test_palette_contrast_still_passes(self):
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "tests/test_palette_contrast.py"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_test_leg_verdicts_ui_still_passes(self):
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "tests/test_leg_verdicts_ui.py"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_every_hud_and_parlay_card_test_that_mentions_globals_css_or_leg_verdicts_still_passes(
        self,
    ):
        tests_dir = REPO / "tests"
        offenders = []
        this_file = Path(__file__).resolve()
        for path in sorted(tests_dir.glob("test_*.py")):
            if path.resolve() == this_file:
                continue
            text = path.read_text(encoding="utf-8")
            if "globals.css" not in text and "LegVerdicts" not in text:
                continue
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", str(path.relative_to(REPO))],
                cwd=str(REPO),
                capture_output=True,
                text=True,
                timeout=180,
            )
            if result.returncode != 0:
                offenders.append((path.name, result.stdout + result.stderr))
        assert not offenders, offenders
