"""The route from the books' prices to this row's number, in four steps.

The Consensus panel already said in prose that the books' margins are
"removed (devigged) and the worst of four methods taken". A beginner has to
take that on trust, because the number that makes it checkable was never on
screen.

**`fair_prices.overround` has been stored since the beginning and served by
nothing.** It is the books' raw implied probabilities summed: two sides quoted
at 54% and 51% come to 105%, and a probability cannot do that. The extra five
points are the house's cut, and devigging is the arithmetic that removes them.
That single number turns a word into something a reader can verify.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **That the fair value is right.** The figure shows the route, not the
  destination's accuracy. `beta = -0.141` is what this project knows about
  that, and it is not on this screen.
- **That the margin is unusual.** Every book quotes one. The bar is drawn to
  scale so a 2% book and a 9% book look different; nothing labels either as
  good or bad.
- **Anything about rendering.** These assert the payload and the component's
  source; `next build` and a browser are what say it draws.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Imported, not re-implemented: this component's docstring names the tokens the
# greps below forbid, and a prohibition's own explanation must not trip it.
from test_desk_panels import code_only  # noqa: E402

COMPONENT = (
    Path(__file__).resolve().parents[1]
    / "frontend"
    / "src"
    / "components"
    / "FairValueSteps.tsx"
)
ROUTES = Path(__file__).resolve().parents[1] / "backend" / "api" / "routes.py"
PANEL = (
    Path(__file__).resolve().parents[1]
    / "frontend"
    / "src"
    / "components"
    / "ConsensusPanel.tsx"
)


def source() -> str:
    return code_only(COMPONENT.read_text(encoding="utf-8"))


class TestTheMissingNumberIsNowServed:
    def test_the_market_route_selects_overround(self):
        """Stored since the beginning, served by nothing until now."""
        text = ROUTES.read_text(encoding="utf-8")
        assert "f.overround" in text, "the market query does not read overround"

    def test_the_market_route_puts_it_on_the_payload(self):
        text = ROUTES.read_text(encoding="utf-8")
        assert 'detail["overround"] = row["overround"]' in text

    def test_an_absent_overround_is_not_reported_as_a_margin_free_book(self):
        """`None`, never 1.0.

        1.0 is a real and very unusual measurement — a book quoting with no
        margin at all. Substituting it for "unrecorded" would put the most
        surprising possible reading in place of a missing one.
        """
        text = ROUTES.read_text(encoding="utf-8")
        window = text[text.index('detail["overround"]') - 500 :][:900]
        assert "never 1.0" in window, (
            "the refusal to substitute 1.0 is not stated where it applies"
        )


class TestTheFigureTeachesTheSequence:
    def test_it_is_mounted_on_the_consensus_panel(self):
        assert "FairValueSteps" in PANEL.read_text(encoding="utf-8")

    def test_all_four_steps_are_present(self):
        """A stage silently dropped teaches a pipeline with one fewer step.

        The first version of this test looped over phrases with a `continue`
        and asserted nothing about them — decoration. It now names the four
        stages and requires each.
        """
        text = source()
        for phrase in (
            "quote both sides",
            "house&rsquo;s cut",
            "Take it back out",
            "least flattering",
        ):
            assert phrase in text, f"step missing: {phrase!r}"
        assert text.count("font-semibold") >= 4

    def test_a_missing_number_still_draws_its_step(self):
        """The sequence is the lesson.

        A stage omitted because its figure is unreadable would teach that the
        pipeline has one fewer step, which is worse than admitting a gap.
        """
        text = source()
        assert "not recorded for this row" in text
        assert "No fair value was recorded" in text

    def test_the_margin_bar_is_measured_from_the_hundred_percent_baseline(self):
        """The subject is the EXCESS, not the total.

        A bar drawn from zero would make a 4% margin look like a rounding
        error against a 100%-wide bar; drawn from the baseline it is the whole
        picture.
        """
        text = source()
        assert "(overround - 1) * 100" in text
        assert "baseline" in COMPONENT.read_text(encoding="utf-8").lower()

    def test_the_printed_margin_is_never_the_clamped_one(self):
        """Clamping is for the drawing only.

        A 14-point margin must PRINT as 14 even though the bar stops at the end
        of its track. A clamped number would be a measurement quietly replaced
        by a display limit.

        The first version of this ended in `or True`, which made its last
        assertion vacuous — it could not fail in either direction. Rewritten to
        state the property structurally: the clamp lands on the bar fraction,
        and the printed value is the raw one.
        """
        text = source()
        clamped = [ln.strip() for ln in text.splitlines() if "Math.min(1," in ln]
        assert clamped, "no draw-only clamp at all"
        assert all("barFrac" in ln or "Math.max(0" in ln for ln in clamped), (
            f"the clamp is not confined to the bar geometry: {clamped}"
        )
        # The printed figure comes straight off `marginPoints`, never `barFrac`.
        assert "{marginPoints.toFixed(1)}" in text
        assert "barFrac.toFixed" not in text

    def test_it_wears_no_colour(self):
        """`--accent` is the same red as `--negative` in both themes. A
        coloured margin bar would read as a verdict on a market priced the way
        every book prices one."""
        text = source()
        for token in ("--accent", "text-positive", "text-negative", "--negative",
                      "--positive"):
            assert token not in text, f"{token} reached the fair-value figure"

    def test_the_margin_bar_carries_a_text_alternative(self):
        text = source()
        assert 'role="img"' in text
        assert "aria-label" in text

    def test_devig_is_glossed_rather_than_assumed(self):
        """Joe asked to be taught the terms; `<Term>` is how this repo does it."""
        assert 'Term k="devig"' in source()


class TestItClaimsNothingAboutQuality:
    def test_no_verdict_word_appears(self):
        text = source().lower()
        for word in ("cheap", "expensive", "good value", "bad value",
                     "edge", "overpriced", "underpriced"):
            assert word not in text, f"the figure passes judgement: {word!r}"

    def test_no_breakeven_or_ev_reaches_it(self):
        text = source().lower()
        for word in ("breakeven", "break-even", "expected value", "kelly"):
            assert word not in text, f"{word!r} reached the fair-value figure"


class TestTheTwoMarketPagePicturesAreDifferentQuestions:
    def test_the_steps_figure_does_not_re_draw_the_dispersion_axis(self):
        """Two pictures, two jobs.

        `DispersionStrip` draws the SPREAD of the results on one axis; this
        draws the ROUTE to them. Duplicating the axis here would be the same
        fact twice, and the reader would not know which to read.
        """
        text = source()
        assert "bookSpan" not in text
        assert "dispersion(" not in text
        assert re.search(r"\bmarks\b", text) is None
