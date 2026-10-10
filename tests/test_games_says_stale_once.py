"""Games says a price is stale once, and folds its explaining into one
collapsed disclosure so a phone opens on rows (#344).

Demo screenshots 2026-10-09: on a 390px phone the first Games row sat ~2.5
screens down behind the refresh panel, the sharp-book base rate and the "Bet
this by hand" paragraph, and each stale row said so three times: the red
"quote 6m" chip, an orange "Kalshi quote is 379s old" sentence, and the
evidence line "Kalshi quote 379s old, limit 30s". The orange sentence is gone
from `StatusLine`; the chip stays (red past the limit) beside the evidence
line.

Source-reading tests, like `tests/test_games_says_it_once.py`: this repo has
no React runner. What this does NOT establish: that the page paints so in a
browser, how it wraps at 390px, or that the evidence line (drawn by the shared
`TrustNote` from `backend/core/trust.py`, neither of which this ticket owns) is
the only other place a stale quote is voiced -- it is, today, by grep.
"""

from __future__ import annotations

import re
from pathlib import Path

SLATE_PAGE = Path(__file__).resolve().parent.parent / "frontend/src/app/slate/page.tsx"


def _src() -> str:
    return SLATE_PAGE.read_text(encoding="utf-8")


def _code(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _between(text: str, start: str, end: str) -> str:
    i = text.index(start)
    return text[i : text.index(end, i)]


class TestGamesSaysStaleOnce:
    def test_a_stale_row_carries_one_staleness_sentence(self):
        """The row's own text voices the Kalshi quote's age as a chip, never as
        a sentence: `StatusLine` has no quote-age branch and the page has no
        "Kalshi quote is Ns old" template. Mutation observed red: restore the
        branch."""
        code = _code(_src())
        status = _between(code, "function StatusLine({", "function Drift({")
        assert "quote_age_now_ms" not in status
        assert "maxQuoteAgeMs" not in status
        assert "Kalshi quote is" not in code
        assert "may already be gone" not in code

    def test_the_age_chip_survives_and_goes_red_past_the_limit(self):
        """Mutation observed red: drop the `text-negative` branch."""
        code = _code(_src())
        chip = _between(code, "function QuoteAge({", "function StatusLine({")
        assert "ageMs > maxMs" in chip
        assert "text-negative" in chip
        assert "<QuoteAge ageMs={row.quote_age_now_ms}" in code

    def test_the_odds_clock_sentence_is_kept(self):
        """The consensus clock has the remedy; only the quote sentence went."""
        assert "Not actionable until the odds are refreshed" in _src()

    def test_the_explainers_sit_in_one_collapsed_disclosure(self):
        """One `<details>` titled "How to read this", closed, holding the
        sharp-book base rate, the hand-bet note and the footer paragraphs, and
        sitting after the rows. Mutation observed red: move `<AnchorBaseRate`
        back above the list, or add `open` to the details."""
        src = _src()
        start = src.index('<details className="mt-10')
        end = src.index("</details>", start)
        block = _flat(src[start:end])
        assert " open" not in src[start : src.index(">", start)]
        assert "How to read this" in block
        assert "<AnchorBaseRate rows={rows} />" in block
        assert "never counts toward the gate" in block
        assert 'k="breakeven"' in block
        assert "The gap between those two numbers is not profit." in block
        assert src.index('<ul className="mt-8 divide-y') < start
        # None of the folded prose is left outside it.
        outside = _flat(src[:start] + src[end:])
        assert "<AnchorBaseRate" not in outside
        assert "never counts toward the gate" not in outside
        assert 'k="breakeven"' not in outside

    def test_the_refresh_panel_keeps_its_decided_placement(self):
        """Both placements stay: above the rows when urgent, below when not."""
        code = _code(_src())
        assert code.count("<RefreshOddsPanel") == 2
        assert code.index("<RefreshOddsPanel") < code.index('<ul className="mt-8')
