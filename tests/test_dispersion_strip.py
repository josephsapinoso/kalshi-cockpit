"""The dispersion strip's geometry, executed rather than read.

Same lane as `tests/test_window_chip.py` and `tests/test_suppression_gloss.py`:
the layout is a React-free module (`frontend/src/lib/dispersion.ts`) so node can
run the real shipped function. A screenshot cannot tell an axis that is right
from one that is inverted, and a substring assertion passes unchanged on a
scale that is exactly backwards.

What this establishes: that every readable point lands on the axis in the right
order and inside `[0, 1]`; that an unsolvable method is *absent* rather than
plotted at zero; that a reading outside the book spread is kept rather than
clamped; that the strip refuses to draw when it has fewer than two distinct
numbers; and that the caveat fires when the two book counts differ *and* when
either is unknown.

What it does **not** establish: that the strip is legible, that the colours
carry the intended meaning, or that any number on it is correct. It is geometry
over numbers the record already holds.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DISPERSION_TS = REPO / "frontend" / "src" / "lib" / "dispersion.ts"
STRIP_TSX = REPO / "frontend" / "src" / "components" / "DispersionStrip.tsx"
SLATE_PAGE = REPO / "frontend" / "src" / "app" / "slate" / "page.tsx"

NODE = shutil.which("node")

_DRIVER = """
import { dispersion } from "./dispersion.ts";
console.log(JSON.stringify(dispersion(JSON.parse(process.argv[2]))));
"""


def lay_out(payload: dict):
    driver = DISPERSION_TS.parent / "_dispersion_driver.mjs"
    driver.write_text(_DRIVER, encoding="utf-8")
    try:
        out = subprocess.run(
            [NODE, "--experimental-strip-types", str(driver), json.dumps(payload)],
            capture_output=True,
            text=True,
            # Node writes UTF-8; without this, Windows decodes with the ANSI
            # code page and an em dash comes back as U+FFFD.
            encoding="utf-8",
            timeout=60,
            cwd=str(DISPERSION_TS.parent),
        )
    finally:
        driver.unlink(missing_ok=True)
    assert out.returncode == 0, f"node failed:\n{out.stdout}\n{out.stderr}"
    return json.loads(out.stdout.strip())


def payload(**over):
    base = {
        "books": {
            "book_count": 4,
            "min_book_probability": 0.60,
            "median_book_probability": 0.602,
            "max_book_probability": 0.604,
        },
        "methods": {
            "p_multiplicative": 0.600,
            "p_additive": 0.6031,
            "p_power": 0.6045,
            "p_shin": 0.6031,
            "p_conservative": 0.600,
        },
        "kalshiProbability": 0.598,
        "anchoredBookCount": 4,
    }
    base.update(over)
    return base


pytestmark = pytest.mark.skipif(
    NODE is None,
    reason=(
        "node is not on PATH. Skipped rather than xfailed: the guard is real "
        "where node exists (CI and both dev machines)."
    ),
)


class TestTheAxisHoldsEveryPoint:
    def test_every_mark_lands_inside_the_axis(self):
        d = lay_out(payload())
        assert d is not None
        xs = [m["x"] for m in d["marks"]]
        xs.extend([d["bookSpan"]["loX"], d["bookSpan"]["hiX"]])
        if d["kalshi"]["x"] is not None:
            xs.append(d["kalshi"]["x"])
        assert all(0.0 <= x <= 1.0 for x in xs), xs

    def test_marks_come_back_in_ascending_probability(self):
        """The screen draws them left to right off this order. Reversed, the
        picture is a lie that renders perfectly."""
        d = lay_out(payload())
        probs = [m["probability"] for m in d["marks"]]
        assert probs == sorted(probs), probs
        xs = [m["x"] for m in d["marks"]]
        assert xs == sorted(xs), xs

    def test_a_lower_probability_is_further_left(self):
        """Pins the direction of the scale, which no ordering test can: a
        strip laid out right-to-left satisfies both assertions above."""
        d = lay_out(payload())
        low = min(d["marks"], key=lambda m: m["probability"])
        high = max(d["marks"], key=lambda m: m["probability"])
        assert low["x"] < high["x"]

    def test_the_used_reading_is_the_one_the_record_says_it_is(self):
        d = lay_out(payload())
        used = [m for m in d["marks"] if m["used"]]
        assert len(used) >= 1
        assert all(abs(m["probability"] - 0.600) < 1e-9 for m in used)

    def test_nothing_is_marked_used_when_the_conservative_column_is_absent(self):
        """`used` follows `p_conservative`, the column the sizer read -- never a
        `Math.min` recomputed here, which would be a second definition free to
        disagree with the one that moved money."""
        m = dict(payload()["methods"])
        del m["p_conservative"]
        d = lay_out(payload(methods=m))
        assert d is not None
        assert not any(x["used"] for x in d["marks"])


class TestUnreadableIsAbsentNotZero:
    def test_a_null_method_produces_no_mark(self):
        m = dict(payload()["methods"])
        m["p_shin"] = None
        d = lay_out(payload(methods=m))
        assert [x["label"] for x in d["marks"]] == [
            "multiplicative",
            "additive",
            "power",
        ]

    def test_a_null_method_does_not_drag_the_axis_to_zero(self):
        """0 is a legitimate probability, so plotting an unsolvable method at 0
        would rescale the whole strip and squash every real reading into one
        pixel at the right edge."""
        m = dict(payload()["methods"])
        m["p_shin"] = None
        d = lay_out(payload(methods=m))
        assert d["domain"]["lo"] > 0.5, d["domain"]

    def test_an_unreadable_ask_leaves_the_marker_off(self):
        d = lay_out(payload(kalshiProbability=None))
        assert d["kalshi"] is None

    def test_no_book_span_still_draws_the_methods(self):
        d = lay_out(payload(books=None))
        assert d is not None
        assert d["bookSpan"] is None
        assert len(d["marks"]) == 4


class TestAReadingOutsideTheSpreadIsKept:
    """A method average over the *anchored* subset is not bounded by the
    min-of-methods over every book, so a reading above `max_book_probability`
    is a real state -- it occurs on the seeded demo. Clamping it would hide the
    one case the strip is most worth looking at."""

    def test_the_axis_stretches_past_the_book_range(self):
        m = dict(payload()["methods"])
        m["p_power"] = 0.61  # well above max_book_probability of 0.604
        d = lay_out(payload(methods=m))
        outside = [x for x in d["marks"] if x["probability"] > 0.604]
        assert outside, "the out-of-range reading was dropped"
        assert all(x["x"] <= 1.0 for x in outside)
        assert d["bookSpan"]["hiX"] < max(x["x"] for x in outside)


class TestTheAskDoesNotSetTheScale:
    """**The ask is not an input to the number this strip explains**, and
    letting it into the domain destroyed the picture on exactly the rows worth
    looking at.

    The seeded `suspicious_edge` row asks 34.0% against four readings spanning
    60.03-60.45%. A linear axis over all of them squashes readings 0.4 points
    apart into a single pixel, so the strip showed nothing on the row where
    "where did 60% come from" is the most interesting question on the screen.
    The 26-point gap to Kalshi is already the loudest number on the row.
    """

    def test_a_far_away_ask_does_not_stretch_the_axis(self):
        near = lay_out(payload(kalshiProbability=None))
        far = lay_out(payload(kalshiProbability=0.34))
        assert far["domain"] == near["domain"]
        assert [m["x"] for m in far["marks"]] == [m["x"] for m in near["marks"]]

    def test_an_off_scale_ask_reports_no_position_rather_than_an_edge_one(self):
        """`at()` returns a number well outside 0..1 for a point past the end,
        and a caller multiplying it by 100% draws the marker outside its own
        container -- which reads as 'the ask is at the far edge', a different
        claim from 'the ask is not on this scale'."""
        d = lay_out(payload(kalshiProbability=0.34))
        assert d["kalshi"]["probability"] == 0.34
        assert d["kalshi"]["x"] is None

    def test_an_ask_that_lands_inside_is_still_drawn(self):
        """Free information where it costs nothing."""
        d = lay_out(payload(kalshiProbability=0.602))
        assert d["kalshi"]["x"] is not None
        assert 0.0 <= d["kalshi"]["x"] <= 1.0

    def test_the_screen_no_longer_draws_the_ask_at_all(self):
        """Inverted 2026-08-21. The component used to draw the ask among the
        readings (with "off this scale" wording when it fell outside), and
        this test pinned that wording. The partner's betting-desk ruling
        (docs/reviews/2026-08-21-items-2-3-ruling.md, "no direction") took
        the ask off the strip entirely: its position relative to the
        readings renders "Kalshi is low/high here", which is the tool's
        opinion of an edge on the landing screen. The ask is still on the
        row, as a price; the geometry above stays because the lib still
        computes it and any future consumer inherits the never-stretch
        rule. What the component must now do is not consult it."""
        source = STRIP_TSX.read_text(encoding="utf-8")
        without_comments = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
        assert "d.kalshi" not in without_comments, (
            "DispersionStrip renders the ask against the readings again -- "
            "that is a direction claim the 2026-08-21 ruling removed"
        )
        assert "off this scale" not in without_comments


class TestItRefusesToDrawRatherThanMislead:
    def test_a_single_distinct_number_draws_nothing(self):
        """One point looks like four methods agreeing perfectly, which is the
        opposite of 'only one could be read'."""
        d = lay_out(
            {
                "books": None,
                "methods": {"p_multiplicative": 0.5, "p_conservative": 0.5},
                "kalshiProbability": None,
                "anchoredBookCount": None,
            }
        )
        assert d is None

    def test_four_identical_readings_draw_nothing(self):
        d = lay_out(
            {
                "books": None,
                "methods": {
                    "p_multiplicative": 0.5,
                    "p_additive": 0.5,
                    "p_power": 0.5,
                    "p_shin": 0.5,
                    "p_conservative": 0.5,
                },
                "kalshiProbability": 0.5,
                "anchoredBookCount": 2,
            }
        )
        assert d is None

    def test_the_legend_resolves_whatever_the_drawing_resolves(self):
        """Three distinct marks whose labels all read `47.4%` look like a
        broken picture rather than a coarse label. Caught on a screenshot of
        the seeded slate, which is why the number of decimals is asserted
        rather than left to taste."""
        source = (REPO / "frontend" / "src" / "lib" / "dispersion.ts").read_text(
            encoding="utf-8"
        )
        assert "toFixed(2)" in source, (
            "asPercent no longer prints two decimals. The dispersion this "
            "strip exists to show is routinely a tenth of a point wide."
        )

    def test_nothing_at_all_draws_nothing(self):
        d = lay_out(
            {
                "books": None,
                "methods": None,
                "kalshiProbability": None,
                "anchoredBookCount": None,
            }
        )
        assert d is None


class TestTheCaveatFiresOnDisagreementAndOnIgnorance:
    def test_matching_counts_need_no_caveat(self):
        d = lay_out(payload(anchoredBookCount=4))
        assert d["caveat"] is None

    def test_differing_counts_say_the_two_rows_cover_different_books(self):
        d = lay_out(payload(anchoredBookCount=1))
        assert d["caveat"]
        assert "4" in d["caveat"] and "1" in d["caveat"]

    def test_an_unknown_count_is_not_reported_as_agreement(self):
        """Silence would read as the reassuring case. 'We could not compare' and
        'they match' are different facts."""
        d = lay_out(payload(anchoredBookCount=None))
        assert d["caveat"]
        assert "unknown" in d["caveat"].lower()


class TestTheScreenNeverCallsAReadingFair:
    """The row already says `fair` once, for the number it picked. Reusing the
    word for the inputs would suggest the four readings are four fair values and
    the row chose among equals -- it took the lowest, deliberately, and the
    strip exists to make that visible rather than to restate it."""

    def test_no_rendered_string_in_the_component_says_fair(self):
        source = STRIP_TSX.read_text(encoding="utf-8")
        without_comments = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
        without_comments = re.sub(
            r"^\s*//.*$", "", without_comments, flags=re.MULTILINE
        )
        # JSX text nodes and the string literals that reach the DOM.
        assert not re.search(r"\bfair\b", without_comments, re.IGNORECASE), (
            "DispersionStrip renders the word 'fair'. Every point on the strip "
            "is a reading; the row's own `fair` is the one number it chose."
        )

    def test_the_bar_says_which_reading_it_plots(self):
        """The bar plots each book's *lowest* of four; the marks plot one
        method averaged. So a mark sits structurally at or above the anchored
        book's own position, and on most seeded rows all four land above
        `max_book_probability`. Unlabelled, that reads as "the consensus is
        higher than every book" -- a claim about the market rather than about
        the statistic."""
        source = STRIP_TSX.read_text(encoding="utf-8")
        without_comments = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
        assert "worst method each" in without_comments

    def test_the_caveat_text_does_not_say_fair(self):
        d = lay_out(payload(anchoredBookCount=1))
        assert "fair" not in d["caveat"].lower()


class TestItIsActuallyOnTheScreen:
    """The geometry above is worth nothing if nothing renders it -- the
    'built but never called' pattern this repo keeps finding."""

    def test_the_slate_renders_the_strip(self):
        source = SLATE_PAGE.read_text(encoding="utf-8")
        # A word boundary, not a bare substring.
        # `"<DispersionStrip" in source` is a *prefix* match, so renaming
        # the tag to `<DispersionStripUnused` -- the obvious way to unwire
        # it -- left the first version of this assertion green. Caught by
        # making that exact edit and watching nothing fail.
        assert re.search(r"<DispersionStrip" + chr(92) + "b", source), (
            "The Slate no longer renders <DispersionStrip>. The geometry "
            "it guards is then a module with no caller, which is the "
            "pattern this class exists for."
        )
        assert "@/components/DispersionStrip" in source

    def test_the_strip_is_on_the_phone_too(self):
        """**This assertion is the exact inverse of the one it replaces, and
        that is the point of writing it rather than deleting it.**

        The strip shipped `xl:`-only under ADR 0047's rule that everything below
        1280px stays byte-identical, with a test pinning `hidden`. Joe overrode
        it the same day: he reads this screen on a phone, and an explanation
        that only exists on a monitor explains nothing to the person who owns
        the account. ADR 0052.

        An override that only removes a guard leaves the next session free to
        re-add `hidden` as a tidy-up, because nothing records that the
        visibility was decided. So the guard is inverted instead of dropped, and
        a future `hidden` fails here with a reason attached.

        The cost is measured, not waved at: the seeded `/slate` at 390px grew
        from 5,808px to 8,912px of scroll -- **+53%**. `check_mobile` is clean
        at every width, so the change is length, not overflow.
        """
        source = SLATE_PAGE.read_text(encoding="utf-8")
        block = source.split("<DispersionStrip", 1)[0]
        opening = block.rsplit("<span", 1)[1]
        assert "hidden" not in opening, (
            "The dispersion strip is hidden below xl again. Joe asked for it on "
            "the phone (ADR 0052) -- if it is going back behind a breakpoint "
            "that needs to be his call, not a density tidy-up."
        )
