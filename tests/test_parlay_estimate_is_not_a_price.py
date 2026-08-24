"""The fair-value payout must not out-rank the quoted one on a parlay card.

ADR 0071 section 2.8, Joe's answer 2026-08-24. A card renders two payout
figures for the same stake, and they are not equally trustworthy:

- **The estimate** (`_stake_row`, `backend/parlays.py:326`) divides the stake
  by the fair joint probability. It is uncapped, because no Kalshi book has
  been consulted when the card renders -- there is no depth to cap against.
- **The quote** (`_at_stake`, `backend/parlays.py:385`) is bounded by what is
  actually resting: `min(wanted, depth)`.

So the estimate is systematically the larger of the two AND it renders first.
Left at equal visual weight, a reader keeps the number they saw first, which
is the one nobody has offered. The decision was to keep the number and change
its authority: the estimate reads as provisional, the quote reads as a price.

**What these tests do not establish.** They assert over **source text** --
this repo has no JS test runner (`frontend/package.json` has `dev`, `build`,
`start`, `lint` and no test script), the same limitation
`tests/test_parlay_screen.py` documents. They prove the emphasis is written
as intended. They cannot prove a reader's eye actually goes to the quote
first, that the italic survives the theme at 390px, or that the caption is
legible. Only looking at the page does that.

They also say nothing about whether the estimate is *correct* -- that is
`tests/test_parlays_api.py`'s job -- nor about whether Kalshi would sell any
card near fair value, which no test in this repo establishes.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"
PARLAY_CARDS = FRONTEND / "components" / "ParlayCards.tsx"
PRICE_ON_KALSHI = FRONTEND / "components" / "PriceOnKalshi.tsx"


def _stakes_source() -> str:
    """Just the `Stakes` component.

    Scoped so that `font-semibold` on the card's headline percentage -- which
    is a different number with a different claim -- cannot satisfy or break an
    assertion about the stake rows.
    """
    source = PARLAY_CARDS.read_text(encoding="utf-8")
    start = source.index("function Stakes({")
    end = source.index("\nfunction ", start + 1)
    return source[start:end]


def _stake_rows_source() -> str:
    """Just the `<ul>` of stake rows, without the block's heading.

    The heading is `font-semibold` and should be: it is an uppercase 11px
    label, and emphasising a label does not lend authority to a number. The
    claim under test is about the **figures**, so the assertion must not be
    able to pass or fail on the label's styling.
    """
    body = _stakes_source()
    start = body.index("<ul ")
    end = body.index("</ul>", start)
    return body[start:end]


class TestTheEstimateSaysItIsAnEstimate:
    def test_the_heading_refuses_the_word_quote(self):
        assert "an estimate, not a quote" in _stakes_source(), (
            "The stake block's heading must say outright that nothing has "
            "been quoted. 'At fair value, a stake would buy' was true and "
            "read as a price to anyone who did not already know what fair "
            "value means -- and the reader this is for is a beginner."
        )

    def test_it_names_the_cap_the_estimate_does_not_have(self):
        """The *reason* the quote is smaller, not just that it differs.

        Without the reason, a reader who sees a smaller number after tapping
        concludes the tool was wrong, rather than that the estimate was
        unbounded and the venue's book is thin.
        """
        body = _stakes_source()
        assert "resting" in body and "capped" in body, (
            "The caption must name resting depth as what bounds the real "
            "price and does not bound this estimate."
        )

    def test_it_does_not_promise_the_real_price_will_be_better(self):
        body = _stakes_source().lower()
        assert "usually worse" in body
        assert "usually better" not in body


class TestTheEstimateIsNeverTheLoudestNumber:
    def test_no_stake_row_is_bold(self):
        """The default stake used to render `font-semibold`.

        That made the largest, least-supported figure on the card also the
        heaviest. The default row is still identifiable to the server
        (`is_default`) and is deliberately no longer emphasised here.
        """
        assert "font-semibold" not in _stake_rows_source(), (
            "No row in the fair-value stake block may be bold: it is the "
            "larger of the two payouts and it renders first."
        )

    def test_the_rows_are_drawn_as_provisional(self):
        body = _stake_rows_source()
        assert "italic" in body and "text-muted" in body

    def test_the_quoted_payout_is_bold(self):
        """The other half of the comparison, and the half that is a price.

        Asserted in the sibling component so that emphasising one without
        de-emphasising the other cannot pass: this file is red unless the
        quote outranks the estimate.
        """
        source = PRICE_ON_KALSHI.read_text(encoding="utf-8")
        start = source.index("value.quoted.at_stake.payout_display !== null")
        window = source[start : start + 400]
        assert 'className="tabular font-semibold"' in window, (
            "The quoted stake line must be bold. It is bounded by resting "
            "depth and it is the only one of the two figures anybody has "
            "offered."
        )
