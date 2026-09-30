"""Cards and quotes show their age (#246, ADR 0189, ADR 0112).

- **A game-script card renders its age from `built_ms`**, and one built before
  its game's inactives time (90 minutes before kickoff) says so in words.
- **The quote block renders an age** (`QuotesAge`, from `asked_ms`).
- **Age is shown, never used to block**: TakeIt's `disabled` expression does not
  read the age, nor does the card's "Ask the market" button.

Source assertions (this repo has no JS test runner), the pattern of
`tests/test_game_script_card_screen.py`.

What this does not establish: that the copy reads well at phone width, or that
the age is correct against a real clock.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "frontend" / "src" / "components"
CARD = (COMPONENTS / "GameScriptCard.tsx").read_text(encoding="utf-8")
ASK = (COMPONENTS / "AskTheMarket.tsx").read_text(encoding="utf-8")


def _function_body(src: str, name: str) -> str:
    start = src.index(f"function {name}(")
    nxt = re.search(r"\n(?:export default )?function \w+\(", src[start + 10 :])
    end = start + 10 + nxt.start() if nxt else len(src)
    return src[start:end]


class TestCardShowsItsAge:
    def test_card_age_is_computed_from_built_ms(self):
        body = _function_body(CARD, "CardAge")
        assert re.search(r"nowMs\s*-\s*card\.built_ms", body)
        assert "formatAge(" in body

    def test_card_age_is_rendered_on_the_built_card(self):
        assert "<CardAge card={card} />" in CARD

    def test_a_card_built_before_inactives_says_so(self):
        body = _function_body(CARD, "CardAge")
        assert "before inactives" in body
        assert re.search(
            r"card\.built_ms\s*<\s*card\.kickoff_ms\s*-\s*INACTIVES_LEAD_MS", body
        )
        assert re.search(r"INACTIVES_LEAD_MS\s*=\s*90\s*\*\s*60_000", CARD)

    def test_the_clock_is_read_after_mount_not_during_render(self):
        body = _function_body(CARD, "CardAge")
        assert "useEffect" in body
        assert "Date.now()" in body
        assert "useState<number | null>(null)" in body

    def test_the_ask_button_does_not_read_the_age(self):
        m = re.search(r"disabled=\{([^}]*)\}", CARD)
        assert m and "built_ms" not in m.group(1)
        assert "nowMs" not in m.group(1)


class TestQuotesShowTheirAge:
    def test_quotes_render_an_age_from_asked_ms(self):
        assert "<QuotesAge askedMs={value.asked_ms} />" in ASK
        body = _function_body(ASK, "QuotesAge")
        assert "formatAge(" in body
        assert "Date.now() - askedMs" in body

    def test_takeit_disabled_expression_does_not_read_the_age(self):
        exprs = re.findall(r"disabled=\{([^}]*)\}", ASK)
        assert exprs, "TakeIt must have a disabled expression"
        for expr in exprs:
            assert not re.search(r"age|asked_?ms|Date\.now", expr, re.I), expr

    def test_takeit_does_not_mention_the_age_at_all(self):
        take = _function_body(ASK, "TakeIt")
        assert "QuotesAge" not in take
        assert "ageMs" not in take
        assert "asked_ms" not in take
