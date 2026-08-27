"""The money record as a picture, and the claims it is not allowed to make.

A cumulative net over settled bets is a FACT: this is what happened to the
money. What it must never become is a verdict on whether Joe is good at this.

**The rule is not invented here.** `docs/reviews/2026-08-21-items-2-3-ruling.md`
re-scoped "CLV on his own bets" to *"per-bet rows only -- your price, Kalshi's
close, the difference -- no average, no hit rate until n >= 30 with the
per-group view beside it"*, and `backend/bets.py` carries the same sentence and
computes none. A fitted line through a dozen settlements is a claim about skill
the record cannot support, on the most ego-loaded quantity in the product.

THE HONESTY THAT COSTS SOMETHING
--------------------------------
`net_tenths` is `null` when the venue's record does not support the registered
settlement formula. A cumulative total cannot step over such a row: skipping it
asserts it was worth zero, and carrying the previous value forward asserts
nothing changed. Both are claims.

What is true is that after the first uncomputable settlement every later point
is a **lower bound**. The line goes dashed there and the caption says so.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Anything about rendering.** These test the arithmetic and the source;
  `next build` and a browser are what say it draws.
- **That the record means anything yet.** Two settled bets draw a line. The
  chart says how many, and nothing else.
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
    / "RecordChart.tsx"
)
PAGE = Path(__file__).resolve().parents[1] / "frontend" / "src" / "app" / "bets" / "page.tsx"


def source() -> str:
    return code_only(COMPONENT.read_text(encoding="utf-8"))


class TestTheCumulativeArithmetic:
    """The `cumulative` helper is pure and exported, so it is tested directly
    rather than inferred from the drawing."""

    def test_the_helper_is_exported_for_testing(self):
        assert "export function cumulative(" in source()

    def test_it_orders_oldest_first(self):
        """The payload arrives newest-first; a cumulative total read backwards
        would draw the record in reverse and still look plausible."""
        text = source()
        assert "sort(" in text
        assert "(a.settled_ms as number) - (b.settled_ms as number)" in text

    def test_an_uncomputable_row_is_not_worth_zero(self):
        """Skipping it silently asserts it settled flat."""
        text = source()
        assert 'typeof bet.net_tenths !== "number"' in text
        assert "Not zero, not skipped" in COMPONENT.read_text(encoding="utf-8")

    def test_an_uncomputable_row_makes_every_later_point_a_floor(self):
        """The property that costs something.

        Once one settlement cannot be computed, the running total is a lower
        bound forever after -- not a value with one gap in it.
        """
        text = source()
        assert "exact = false" in text
        assert "strokeDasharray" in text

    def test_the_caption_says_how_many_could_not_be_computed(self):
        text = source()
        assert "uncomputable > 0" in text
        assert "floor rather than a figure" in text


class TestItMakesNoClaimAboutSkill:
    def test_no_trend_or_fit_is_drawn(self):
        """A fitted line through a dozen settlements is a claim about skill."""
        text = source().lower()
        for word in ("trend", "regression", "slope", "fit(", "average", "mean("):
            assert word not in text, f"the record chart fits something: {word!r}"

    def test_no_hit_rate_or_win_rate_appears(self):
        text = source().lower()
        for word in ("hit rate", "win rate", "winrate", "win%", "accuracy"):
            assert word not in text, f"{word!r} reached the record chart"

    def test_no_clv_series_is_drawn(self):
        """Per-bet rows only, until n >= 30 with the per-group view beside it."""
        text = source()
        assert "clv" not in text.lower(), "a CLV series reached the record chart"

    def test_it_does_not_read_the_embargoed_estimate_log(self):
        """`/api/bets` never touches `bet_estimates`; the study is stopped."""
        text = source().lower()
        for word in ("estimate", "p_yes", "calibration"):
            assert word not in text, f"{word!r} reached the record chart"


class TestItRefusesRatherThanMislead:
    def test_one_settled_bet_draws_nothing(self):
        """A dot drawn as a chart implies a trend it cannot have."""
        assert "points.length < 2" in source()

    def test_zero_is_the_only_reference_line(self):
        """A money line needs one reference and it is break-even."""
        text = source()
        assert "y(0)" in text
        assert text.count("var(--border)") >= 1

    def test_the_line_is_not_coloured_by_whether_it_is_winning(self):
        """`--positive`/`--negative` are polarity, and a cumulative balance has
        none at a point. Colouring by the current sign would repaint the whole
        history every time a bet settles."""
        text = source()
        for token in ("--positive", "--negative", "text-positive", "text-negative"):
            assert token not in text, f"{token} reached the record chart"

    def test_it_carries_a_text_alternative(self):
        text = source()
        assert 'role="img"' in text
        assert "aria-label" in text

    def test_the_label_admits_when_the_total_is_a_floor(self):
        """The accessible text must not be more confident than the drawing."""
        assert 'last.exact ? "" : " or better"' in source()


class TestItIsMountedWhereTheRecordLives:
    def test_the_bets_page_renders_it(self):
        assert "RecordChart" in PAGE.read_text(encoding="utf-8")

    def test_it_sits_above_the_rows_it_summarises(self):
        text = PAGE.read_text(encoding="utf-8")
        assert text.index("<RecordChart") < text.index("record.bets.map"), (
            "the picture should precede the rows it is made of"
        )
