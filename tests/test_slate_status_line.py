"""The slate row's one-line warning names the clock that actually binds.

`StatusLine` voices exactly one fact by fixed priority. Until 2026-08-31 that
priority put the **Kalshi quote** first and the **sportsbook consensus**
second, which is backwards, and the reason it is backwards is not a matter of
taste -- it is `_live_ages`' own rule:

    `actionable` is the ODDS clock, not both clocks. The order endpoint
    re-reads the Kalshi quote inside the request, so the recorded quote's age
    no longer decides whether an order is accepted.

So a stale quote means *the price on the row is a memory*; a stale consensus
means *the row is not actionable at all until a credit is spent re-buying the
books*. Outside an odds window both are stale on most rows, so the old order
voiced the less binding of the two on exactly the rows where it mattered.

Seen on live 2026-08-31, on `KXMLBGAME-26AUG311840SDCIN-CIN`: the consensus was
**2042s past a 900s limit** and the row printed only *"Kalshi quote is 134s
old"*. Nothing on the row named the thing a reader could act on.

WHAT THESE TESTS DO NOT ESTABLISH
---------------------------------
- **That the line renders.** There is no JS test runner in this repo
  (`frontend/package.json` has no jest or vitest), so these are source
  assertions about the component's branch order. They cannot see a screen --
  which is the whole reason this defect survived: the priority was stated in
  the docstring from the day it was written, matched the code exactly, and was
  still wrong about which clock binds.
- **That one line is the right number of lines.** Voicing one fact is
  `StatusLine`'s existing contract (a selection, not a composite -- ADR 0021
  section 9). These tests fix WHICH fact, not how many.
- **Anything about the Board.** `OpportunityCard` already separates
  `price_is_current` (the ask is a memory) from `expired`, and always did.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SLATE_PAGE = (
    Path(__file__).resolve().parents[1]
    / "frontend"
    / "src"
    / "app"
    / "slate"
    / "page.tsx"
)


def _status_line_body() -> str:
    """The function body alone, so the docstring above it cannot satisfy a
    test about the code."""
    source = SLATE_PAGE.read_text(encoding="utf-8")
    start = source.index("function StatusLine({")
    end = source.index("function Drift({", start)
    return source[start:end]


class TestTheBindingClockIsNamedFirst:
    def test_the_odds_clock_is_the_first_branch(self):
        """Mutation observed red: swap the two `if` branches back.

        Asserted on the branch ORDER rather than on a rendered string, because
        the order is the whole behaviour: both conditions are true on most
        rows outside an odds window, so whichever is tested first is the only
        one a reader ever sees.
        """
        body = _status_line_body()
        odds = body.index("row.odds_age_now_ms > maxOddsAgeMs")
        quote = body.index("row.quote_age_now_ms > maxQuoteAgeMs")
        assert odds < quote, (
            "the Kalshi quote is tested before the consensus, so a row that "
            "is not actionable prints a caveat about its price instead"
        )

    def test_the_odds_branch_says_what_to_do_about_it(self):
        """The consensus is the clock with an action attached.

        Nothing refreshes it but a credit, and the button that spends one is
        already above the list. A warning naming a limit with no exit is the
        `stale_odds x 33` complaint Joe made on 2026-08-22.
        """
        body = _status_line_body()
        assert "Not actionable until the odds are refreshed" in body

    def test_the_quote_branch_still_says_price_not_expiry(self):
        """A stale quote must not read as "this row is dead".

        The order endpoint re-reads the Kalshi price inside the request, so
        the row is still buyable -- what is stale is the number printed on it.
        This is the claim `OpportunityCard` already makes on the Board, and
        demoting the branch must not quietly strengthen it.
        """
        body = _status_line_body()
        i = body.index("row.quote_age_now_ms > maxQuoteAgeMs")
        j = body.index("`;", body.index("line = `", i))
        message = body[i:j]
        assert "the ask shown may already be gone" in message
        for banned in ("not actionable", "Not actionable", "expired", "dead"):
            assert banned not in message, (
                f"the quote branch says {banned!r}; a stale quote is a price "
                f"caveat, not an expiry"
            )

    def test_the_drift_branch_stays_last(self):
        """It is the only one of the three that is not a validity failure.

        A moved tape is a caveat about what is being compared; the two clocks
        above it are limits the desk refuses on. Promoting it would voice a
        display threshold over a refusal.
        """
        body = _status_line_body()
        quote = body.index("row.quote_age_now_ms > maxQuoteAgeMs")
        drift = body.index("row.kalshi_drift_tenths")
        assert quote < drift


class TestALongRefusalCodeCannotScrollTheSlateSideways:
    """A `suppressed_reason` is often several codes joined by commas with no
    spaces, which is one unbreakable token to a line-breaker.

    Measured on live 2026-08-31 in a true 390px viewport: the footer's code
    span pushed `documentElement.scrollWidth` to **428** against a 390px
    viewport, so the whole page scrolled sideways on a phone. It is
    data-dependent -- it appears only when a row carries a long multi-code
    reason -- which is why an earlier read of the same page at the same width
    measured 375 and saw nothing.

    The row-level span has carried `w-full break-words` since it was written
    and never overflowed. Only the footer's copy lacked it.
    """

    @staticmethod
    def _code_spans() -> list[str]:
        """Every `className` that styles a refusal code, however it is wrapped.

        Matched on the class attribute rather than on a line, because the
        markup is multi-line: a line-based scan silently found nothing once
        the span was reformatted, which is a guard going quiet rather than
        red.
        """
        source = SLATE_PAGE.read_text(encoding="utf-8")
        values = re.findall(r'className="([^"]*)"', source)
        return [v for v in values if "font-mono" in v and "text-accent-2" in v]

    def test_every_refusal_code_span_can_break(self):
        """Mutation observed red: drop `break-words` from either span.

        Both the row's and the footer's, asserted together: they render the
        same string and disagreed about wrapping for as long as both existed.
        """
        spans = self._code_spans()
        assert len(spans) >= 2, f"expected both spans, found {len(spans)}"
        for v in spans:
            assert "break-words" in v, (
                f"a refusal code renders in a span that cannot break, so a "
                f"multi-code reason scrolls the page sideways at 390px: {v!r}"
            )


class TestTheDocstringDescribesTheCodeItSitsOn:
    """The defect survived because the prose and the code agreed with each
    other and both disagreed with `_live_ages`. Agreement between them is
    therefore necessary and not sufficient -- but its absence is a defect on
    its own, and it is the cheap half to check."""

    def _doc(self) -> str:
        """The comment block, unwrapped.

        The `* ` prefixes and the line breaks are removed and the whitespace
        collapsed, so a phrase that happens to straddle a wrap still matches.
        A test that fails when someone reflows a paragraph teaches people to
        delete the test.
        """
        source = SLATE_PAGE.read_text(encoding="utf-8")
        end = source.index("function StatusLine({")
        start = source.rindex("/**", 0, end)
        lines = source[start:end].splitlines()
        stripped = [ln.strip().lstrip("*").strip() for ln in lines]
        return " ".join(" ".join(stripped).split())

    def test_the_stated_priority_matches_the_branch_order(self):
        """The two are compared to EACH OTHER, not each to a literal.

        The first version of this test read only the doc, asserting its own
        numbered list was in the order this file expects. That is a test of
        the prose against a constant, and a code-only swap left it green --
        the exact mutation it is named for. Reading both and comparing them is
        what makes the name true.

        Mutation observed red: swap the two `if` branches without touching the
        numbered list above them.
        """
        doc = self._doc()
        doc_consensus = doc.index("the consensus is past the odds limit")
        doc_quote = doc.index("the Kalshi quote is past the staleness limit")

        body = _status_line_body()
        code_consensus = body.index("row.odds_age_now_ms > maxOddsAgeMs")
        code_quote = body.index("row.quote_age_now_ms > maxQuoteAgeMs")

        assert (doc_consensus < doc_quote) == (code_consensus < code_quote), (
            "the numbered priority in the comment and the branch order in the "
            "code disagree about which clock is voiced first"
        )

    @pytest.mark.parametrize(
        "phrase",
        [
            # The rule the order serves, named where the order is stated, so a
            # future reader does not have to rediscover it in `_live_ages`.
            "ODDS clock",
            "actually ends a row's life",
        ],
    )
    def test_the_reason_is_recorded_beside_the_order(self, phrase):
        assert phrase in self._doc(), phrase
