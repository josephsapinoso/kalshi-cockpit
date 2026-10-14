"""Joe's A1 B1 C1 to #385 (2026-10-13): three wording moves, nothing reworded.

A1: the Games header keeps #9's one-sentence lede; the server's note moves into
the collapsed "How to read this" (pinned in `tests/test_tab_ledes.py`).
B1: Games keeps one signal-test line -- the verdict word as served, plus a link
-- and the full `SignalStrip` renders on Gate instead.
C1: the Parlays lede says "beside", not "rather than at" (pinned verbatim in
`tests/test_tab_ledes.py`'s PARLAYS_LEDE).

Source-reading tests, like the rest of the screen pins (no React runner here).
What this does NOT establish: how the Gate page lays the box out, or that the
`#signal-test` anchor scrolls on a phone. Opening the pages does.
"""

from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "frontend" / "src" / "app"
GAMES = APP / "slate" / "page.tsx"
GATE = APP / "gate" / "page.tsx"


def _code(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"\{/\*.*?\*/\}", "", text, flags=re.DOTALL)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)


class TestTheSignalTestBoxLivesOnGate:
    def test_games_no_longer_renders_the_full_box(self):
        """Mutation observed red: put `<SignalStrip` back on the Games page."""
        assert "<SignalStrip" not in _code(GAMES)
        assert "SignalStrip" not in _code(GAMES).split("export default", 1)[0]

    def test_games_keeps_one_line_with_the_verdict_unchanged_and_a_link(self):
        code = _code(GAMES)
        start = code.index("{signal && (")
        line = code[start : code.index(")}", code.index('href="/gate#signal-test"'))]
        assert "{signal.available ? signal.verdict" in line
        assert 'href="/gate#signal-test"' in line
        # No statistic leaks back onto the line.
        for word in ("beta", "interval", "estimate", "se_cluster", "refusal"):
            assert word not in line, word

    def test_gate_renders_the_full_box_at_the_anchor_the_link_names(self):
        """Mutation observed red: drop the `<SignalStrip` from Gate."""
        code = _code(GATE)
        assert "fetchSignal().catch(() => null)" in code
        anchor = code.index('id="signal-test"')
        assert "<SignalStrip signal={signal}" in code[anchor : anchor + 200]
