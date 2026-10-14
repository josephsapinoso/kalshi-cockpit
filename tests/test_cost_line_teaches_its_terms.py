"""The parlay cost line teaches its own words (#396, deliverable B of #340).

`ParlayCostLine` in `AskTheMarket.tsx` prints "This price says 5%. Wins about
1 in 20. The books multiply to 4%. Fee is 6.7% of stake. The same picks as
singles: 3%." Each of those phrases is a betting term Joe was never taught, so
each is wrapped in a tap-open `<Term>`. (The `<Hint>` on the singles figure the
ticket asked for is NOT here: the render harness in
test_parlay_cost_line_states_the_price.py cannot resolve a Hint import.) This pins, one assertion per key, that the glossary key is still
rendered on the exact phrase it explains, and the standing constraints from
the ticket: no threshold-triggered "long shot" word on the ticket (that would
be the suggested price floor on the screen, ADR 0071 decision 2, ADR 0189,
#239 C), and no money figure or imperative in the `unit` definition.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- That any definition is correct, or that the popover renders legibly.
- That the phrase sits at the right place in the sentence at runtime; the
  scan is over the source text of `ParlayCostLine` only.
- Anything about the other screens (leg facts, game legs, Check a parlay,
  Your bets): `test_glossary_coverage.py` only guarantees each new key is
  rendered somewhere, not where.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "frontend" / "src"
ASK = (SRC / "components" / "AskTheMarket.tsx").read_text(encoding="utf-8")
GLOSSARY = (SRC / "lib" / "glossary.ts").read_text(encoding="utf-8")


def _cost_line() -> str:
    start = ASK.index("function ParlayCostLine")
    end = ASK.index("\n}\n", start)
    return ASK[start:end]


def _term(key: str, words: str) -> re.Pattern[str]:
    return re.compile(
        r'<Term\s+k="%s"\s*>\s*%s\s*</Term>' % (re.escape(key), re.escape(words))
    )


def _definition(key: str) -> str:
    m = re.search(r"\n  %s: \{(.*?)\n  \},\n" % key, GLOSSARY, re.S)
    assert m, key
    return "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1).split("definition:")[1]))


class TestTheCostLineTeachesItsTerms:
    def test_implied_chance_wraps_this_price_says(self):
        assert _term("implied_chance", "This price says").search(_cost_line())

    def test_one_in_wraps_wins_about_1_in(self):
        assert _term("one_in", "Wins about 1 in").search(_cost_line())

    def test_books_joint_wraps_the_joint_figure(self):
        # On the figure, not the phrase: test_parlay_cost_line_states_the_price
        # pins the literal `books</Term> multiply`.
        assert _term("books_joint", "{line.fairJointPercentDisplay}").search(
            _cost_line()
        )

    def test_the_word_books_keeps_its_own_term(self):
        assert _term("books", "books").search(_cost_line())

    def test_fee_share_wraps_the_fee_figure(self):
        assert _term("fee_share", "Fee").search(_cost_line())

    def test_unit_wraps_the_word_stake(self):
        assert _term("unit", "stake").search(_cost_line())

    def test_singles_keeps_its_own_term(self):
        assert _term("single", "singles").search(_cost_line())

    def test_no_threshold_triggered_long_shot_word_on_the_cost_line(self):
        line = _cost_line().lower()
        assert "long shot" not in line and "longshot" not in line
        assert 'k="longshot"' not in line

    def test_unit_defines_the_word_without_a_money_figure_or_order(self):
        text = _definition("unit")
        assert "$" not in text and not re.search(r"\d", text)
        assert len(text.split()) <= 55
