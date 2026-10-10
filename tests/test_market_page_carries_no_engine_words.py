"""The market page prints no engine-written sentence and puts the ticket first.

`backend/engine.py` writes `reason_text` ("Houston: consensus fair 54.2%, Kalshi
asks 50.7c (+1.7c after fees). Sized at 1."): the edge estimate and the sizing
ADR 0071 section 2.5 took off the row. The Skeptic panel rendered it on the
betting screen (#341). The payload field stays; the panel stops printing it.

WHAT THIS DOES NOT ESTABLISH: that the page draws. These read source with
comments removed; `next build` and a browser say it renders.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_desk_panels import code_only  # noqa: E402

FRONTEND = Path(__file__).resolve().parents[1] / "frontend" / "src"
SKEPTIC = FRONTEND / "components" / "SkepticPanel.tsx"
PAGE = FRONTEND / "app" / "market" / "[ticker]" / "page.tsx"


class TestTheMarketPageCarriesNoEngineWords:
    def test_the_skeptic_panel_never_prints_reason_text(self):
        text = code_only(SKEPTIC.read_text(encoding="utf-8"))
        assert "reason_text" not in text
        assert "Sized at" not in text
        assert "after fees" not in text

    def test_the_verdicts_as_of_stamp_survives(self):
        text = code_only(SKEPTIC.read_text(encoding="utf-8"))
        assert "Verdicts as of" in text

    def test_the_ticket_sits_above_the_desk_areas(self):
        text = code_only(PAGE.read_text(encoding="utf-8"))
        ticket = text.index("<ManualTicket ticker={ticker} />")
        assert text.index("<QuoteStrip detail") < ticket
        assert ticket < text.index("<nav ")
        assert ticket < text.index("<ConsensusPanel")
        assert "<PassControl ticker={ticker} />" in text
        for anchor in ("#consensus", "#skeptic", "#scout", "#specialists", "#willy"):
            assert anchor in text
