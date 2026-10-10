"""#343: Your bets opens on the scoreboard, not on hedge prose.

Source-text tests over `frontend/src/app/bets/page.tsx` (no browser). They
establish ORDER in the source and the href target; they do not establish how
the strip looks at 390px, nor that the served figures are right (the payload
tests own that).
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = (ROOT / "frontend" / "src" / "app" / "bets" / "page.tsx").read_text(
    encoding="utf-8"
)
FORM = (ROOT / "frontend" / "src" / "components" / "RecordParlay.tsx").read_text(
    encoding="utf-8"
)


def _render_body() -> str:
    start = PAGE.index("export default async function BetsPage")
    return PAGE[start : PAGE.index("const SECTIONS")]


class TestYourBetsLeadsWithTheRecord:
    def test_the_summary_strip_renders_before_the_hedge_prose_and_each_source_row_prints_its_n(
        self,
    ):
        body = _render_body()
        strip = body.index("<RecordStrip")
        assert strip < body.index("<HedgePositions")
        assert strip < body.index("not_advice")
        assert strip < body.index('id="open"') or strip < body.index("Open{")
        # The hedge prose is folded, not deleted.
        fold = body.index("data-how-to-read")
        assert body.index("not_advice") > fold
        assert "<details" in body[fold - 80 : fold + 20]
        # Each source row prints its own n, in the server's order.
        fn = PAGE[PAGE.index("function RecordStrip") :]
        fn = fn[: fn.index("const SECTIONS")]
        assert "data-source-row" in fn
        assert "n={n}" in fn
        assert "block.wins + block.losses" in fn
        assert ".sort(" not in fn and "toSorted" not in fn
        assert "singles and combinations together" in fn

    def test_record_it_below_links_to_the_form(self):
        assert 'id="record-parlay"' in FORM
        i = PAGE.index("Record it below")
        link = PAGE[PAGE.rindex("<Link", 0, i) : i]
        assert 'href="#record-parlay"' in link
        assert 'href="#open"' not in link
