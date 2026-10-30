"""Your bets: a zero net is neutral `$0.00`, and an empty Open is one line (#391).

The server renders a wash as "+$0.00" (`backend/bets.py:format_net_dollars`)
and the page painted every non-negative net `text-positive`, so zero read as
a gain at four sites. Source-reading tests (there is no React runner here):
they pin what `frontend/src/app/bets/page.tsx` contains, not what paints.
"""

from __future__ import annotations

import re
from pathlib import Path

PAGE = (
    Path(__file__).resolve().parent.parent
    / "frontend"
    / "src"
    / "app"
    / "bets"
    / "page.tsx"
).read_text(encoding="utf-8")


def _fn(name: str) -> str:
    m = re.search(rf"function {name}\(.*?\n}}\n", PAGE, re.S)
    assert m, name
    return m.group(0)


class TestAZeroNetHasNoSignAndNoPositiveInk:
    def test_a_zero_net_has_no_sign_and_no_positive_ink(self):
        ink = _fn("netInk")
        shown = _fn("netShown")
        # zero is checked before the positive fall-through and is not green
        assert re.search(r"tenths === 0\) return \"text-foreground\"", ink)
        assert ink.index("=== 0") < ink.index("text-positive")
        assert re.search(r"tenths === 0\) return \"\$0\.00\"", shown)

        # all four sites go through the helpers; none keeps the old binary
        assert '< 0 ? "text-negative" : "text-positive"' not in PAGE
        assert 'bet.net_tenths < 0' not in PAGE
        # `record.totals.net_tenths` left with the strip's Net tile (town
        # hall #413: Net was printed twice); the three sites left still print it.
        assert "record.totals.net_tenths" not in PAGE
        for tenths in (
            "totals.net_tenths",
            "block.net_tenths",
            "bet.net_tenths",
        ):
            assert f"netInk({tenths})" in PAGE, tenths
            assert re.search(rf"netShown\({re.escape(tenths)}, ", PAGE), tenths
        for raw in (
            "{totals.net_display}",
            "{record.totals.net_display}",
            "{block.net_display}",
            "{bet.net_display ??",
        ):
            assert raw not in PAGE, raw

    def test_positive_and_negative_keep_their_ink(self):
        ink = _fn("netInk")
        assert '"text-negative"' in ink and '"text-positive"' in ink


class TestTheEmptyOpenSectionIsOneLineAndALinkToTheForm:
    def test_the_empty_open_section_is_one_line_and_a_link_to_the_form(self):
        m = re.search(r"<p[^>]*data-open-empty>(.*?)</p>", PAGE, re.S)
        assert m, "no empty-Open line"
        body = m.group(1)
        assert 'href="#record-parlay"' in body
        assert "No tickets recorded." in body
        # the explainer is not shown beside an empty section
        cond = PAGE[: m.start()].rsplit("{hedge.positions.length === 0", 1)[1]
        assert "unrecorded_at_venue.length === 0" in cond
        assert PAGE.index("data-open-empty") < PAGE.index("data-how-to-read")
