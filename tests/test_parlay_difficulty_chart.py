"""The parlay chart draws the collapse, and claims nothing beyond it.

The picture behind a sentence the payload already carries verbatim
(`parlays.NOTES["chance"]`): *"A parlay multiplies chances down: six 65% legs
land together about 8% of the time."* Drawn from this card's own legs in the
ladder's own order, rather than illustrated with invented numbers.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **That a card is a good bet.** The chart shows one quantity falling. There is
  no payout, no EV, no breakeven anywhere near it, and the two tests below that
  forbid a second series are the reason.
- **That the drawn curve is the headline.** It is the plain product; the
  headline joint is correlation-adjusted, and the gap is stated under the
  chart. `test_the_chart_states_its_own_approximation` pins that the statement
  travels with it.
- **Anything about rendering.** These assert the payload and the component's
  source. `next build` and a browser are what say it draws.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Imported, not re-implemented: a prohibition's own explanation must not
# fail the grep that enforces it, and two copies of that rule drift apart.
from test_desk_panels import code_only  # noqa: E402

from backend import parlays
from backend.core.ladder import CandidateLeg

COMPONENT = (
    Path(__file__).resolve().parents[1]
    / "frontend"
    / "src"
    / "components"
    / "ParlayDifficulty.tsx"
)


def _leg(i: int, p: float) -> CandidateLeg:
    return CandidateLeg(
        label=f"Team {i} to win",
        event_title=f"Away {i} at Team {i}",
        kalshi_event_ticker=f"KX-{i}",
        kalshi_market_ticker=f"KX-{i}-T",
        odds_event_id=f"g{i}",
        league="baseball_mlb",
        commence_ms=1_787_000_000_000,
        market="h2h",
        team=f"Team {i}",
        point=None,
        p_conservative=p,
        p_by_method={"multiplicative": p, "additive": p, "power": p, "shin": p},
        odds_age_now_ms=30_000,
    )


class TestThePrefixSeriesIsTheRunningProduct:
    def test_each_step_multiplies_the_one_before(self):
        legs = [_leg(0, 0.8), _leg(1, 0.5), _leg(2, 0.5)]
        out = parlays._prefix_chances(legs)

        assert [p["legs"] for p in out] == [1, 2, 3]
        assert out[0]["chance"] == pytest.approx(0.8)
        assert out[1]["chance"] == pytest.approx(0.4)
        assert out[2]["chance"] == pytest.approx(0.2)

    def test_it_falls_monotonically_because_a_chance_cannot_exceed_one(self):
        """The property the whole chart exists to show.

        A step that rose would mean a leg with a probability above 1, which is
        not a chance.
        """
        legs = [_leg(i, 0.74 - i * 0.03) for i in range(6)]
        chances = [p["chance"] for p in parlays._prefix_chances(legs)]
        assert chances == sorted(chances, reverse=True)
        assert all(0.0 < c <= 1.0 for c in chances)

    def test_the_display_string_is_rendered_server_side(self):
        """The client plots geometry and prints nothing it computed itself."""
        out = parlays._prefix_chances([_leg(0, 0.74), _leg(1, 0.71)])
        assert out[0]["chance_percent_display"] == "74%"
        assert all("chance_percent_display" in p for p in out)

    def test_a_single_leg_still_produces_one_point(self):
        """The server reports it; the COMPONENT refuses to draw one point."""
        assert len(parlays._prefix_chances([_leg(0, 0.6)])) == 1


class TestTheChartRefusesToOverclaim:
    def _source(self) -> str:
        """Comments stripped. This component's docstring NAMES the tokens it
        refuses to use, and explaining a prohibition must not trip it."""
        return code_only(COMPONENT.read_text(encoding="utf-8"))

    def test_no_payout_or_value_series_is_drawn(self):
        """Barred twice over, and both reasons are worth keeping.

        A second y-scale is never correct on one chart. And "chance falls while
        payout rises" is an expected-value claim, which `/api/parlays` carries
        none of by construction (ADR 0038, ADR 0070).
        """
        source = self._source().lower()
        for word in ("payout", "stake", "breakeven", "break-even", "profit", "ev"):
            assert f"{word}=" not in source and f".{word}" not in source, (
                f"{word!r} reached the difficulty chart"
            )

    def test_one_point_is_not_a_collapse(self):
        """A chart of a single leg would draw a flat nothing and imply a trend."""
        assert "prefixes.length < 2" in self._source()

    def test_the_axis_starts_at_zero(self):
        """Deliberately unlike `PriceChart`, which fits its domain.

        There the subject is movement inside a narrow band, so fitting is
        right. Here the subject is HOW FAR the number falls, and a fitted axis
        would flatten exactly the collapse the chart exists to show.
        """
        source = self._source()
        assert "(p / top) * PH" in source, "the y-scale is no longer zero-based"
        assert "fitDomain" not in source

    def test_the_chart_states_its_own_approximation(self):
        """The drawn curve is not the headline, and the difference is named."""
        assert "independenceNote" in self._source()

    def test_it_wears_no_colour(self):
        """`--accent` is the same red as `--negative` in both themes, and a
        stat wearing it is already forbidden (`test_palette_contrast.py`). A
        coloured series here would read as a verdict on a number that is not
        one. Identity comes from position and shape."""
        source = self._source()
        for token in ("--accent", "text-positive", "text-negative", "--negative"):
            assert token not in source, f"{token} reached the difficulty chart"
        assert "currentColor" in source

    def test_it_carries_a_text_alternative(self):
        """The numbers must reach a reader who cannot see the drawing."""
        source = self._source()
        assert 'role="img"' in source
        assert "aria-label" in source
