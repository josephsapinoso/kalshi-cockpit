"""`/bets` separates the kinds, states its own first day, and says what is
open -- and the words it may never carry (ticket #21, Joe's 21A, 2026-09-03).

The page is "a bank statement, not a report card". These tests read the
screen's SOURCE, comments stripped, because every property here is a
prohibition on wording or a guard on a branch, and a prohibition's own
explanation must not trip the grep that enforces it (the `test_crew_bubble`
lesson; `code_only` is imported from `test_desk_panels`, not re-implemented).

What this establishes
---------------------
- The page renders two sections keyed by the server's `kind`, each headed by
  the server's whole-table count, and never re-derives the kind from the
  ticker string.
- The CLV line is drawn for a single game only; a combination row draws no
  CLV words, and `combo_unscorable` is never rendered as words.
- The CLV coverage sentence divides by the singles denominator, not the
  pooled total.
- No month-day date is typed into the page; the first day comes from
  `first_settled_ms`.
- Neither the page nor the open-positions strip carries an average, win rate,
  hit rate, streak or trend, and the strip's staked figure is never summed
  with cash or the value.

What it does NOT establish
--------------------------
Anything about rendering -- `next build` and a browser are what say it
draws -- or that the served numbers are right; `tests/test_bets.py` owns the
arithmetic.

Mutations run, each red and the file restored by reversing the exact edit
(2026-09-03):
(1) the `bet.kind === "single" &&` guard removed from the CLV span -- the
    combo-draws-no-CLV test fails;
(2) "before the recorder started on Aug 18" restored to the completeness
    sentence -- the no-typed-date test fails;
(3) "hit rate" added to a section heading -- the no-aggregate test fails;
(4) `block.staked_tenths + block.value_tenths` rendered in the strip -- the
    never-summed test fails;
(5) `{record.total}` restored as the CLV sentence's denominator -- the
    denominator test fails.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_desk_panels import code_only  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
PAGE = REPO / "frontend" / "src" / "app" / "bets" / "page.tsx"
STRIP = REPO / "frontend" / "src" / "components" / "OpenPositions.tsx"
API = REPO / "frontend" / "src" / "lib" / "api.ts"


def code(path: Path) -> str:
    return code_only(path.read_text(encoding="utf-8"))


class TestTheKindsAreSeparated:
    def test_two_sections_headed_by_the_servers_counts(self):
        text = code(PAGE)
        assert '"Single games"' in text
        assert '"Combination bets"' in text
        # The heading's number is the server's whole-table block for that
        # kind, never a count of the rows rendered under it.
        assert "record.sections[section.kind]" in text
        assert "{block.total}" in text

    def test_the_kind_is_the_servers_and_never_re_derived_here(self):
        """`bet.kind` groups the rows; the ticker string is never inspected
        for the combo prefix on the client."""
        text = code(PAGE)
        assert "bet.kind === section.kind" in text
        assert "KXMVE" not in text
        assert "startsWith(" not in text

    def test_each_section_shows_a_sum_and_no_rate(self):
        text = code(PAGE)
        assert "{block.net_display}" in text
        assert "{block.computable}" in text
        assert "block.total /" not in text
        assert "/ block." not in text

    def test_the_type_carries_the_kind_and_the_sections(self):
        """A type declaration is owned by whoever owns its producer (ADR
        README): the field and its type change in one commit."""
        text = code(API)
        assert 'export type BetKind = "single" | "combo";' in text
        assert "sections: Record<BetKind, BetsSection>;" in text
        assert "first_settled_ms: number | null;" in text


class TestACombinationRowDrawsNoCLV:
    def test_the_clv_span_is_guarded_on_the_single_kind(self):
        """The whole line, not just the number: a combo has no close to be
        read, and "close not read yet" on fifty rows would say the close was
        late rather than absent."""
        text = code(PAGE)
        assert re.search(
            r'bet\.kind === "single" &&[\s\S]{0,600}\{clvWords\}', text
        ), "the CLV line renders without the single-kind guard"

    def test_the_combo_reason_is_never_rendered_as_words(self):
        text = code(PAGE)
        assert "combo_unscorable" not in text


class TestTheCoverageSentenceDividesBySingles:
    def test_the_denominator_is_the_singles_count(self):
        text = code(PAGE)
        assert "record.clv_coverage.denominator" in text
        assert not re.search(
            r"clv_coverage\.scored\} of[\s\S]{0,120}\{record\.total\}", text
        ), "the CLV sentence divides by the pooled total again"

    def test_the_sentence_says_combos_are_not_counted(self):
        text = code(PAGE)
        assert "Combination bets have no close to score against" in text


class TestThePageTypesNoDate:
    MONTH_DAY = re.compile(
        r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.? \d{1,2}\b"
    )

    def test_no_month_day_literal_anywhere_in_the_code(self):
        """The completeness sentence said "before the recorder started on Aug
        18" for two weeks while the mirror's first row was Aug 11. A date
        typed into a page is a claim the page cannot keep."""
        text = code(PAGE)
        hit = self.MONTH_DAY.search(text)
        assert hit is None, f"a date is typed into the page: {hit.group(0)!r}"
        assert "recorder started on" not in text

    def test_the_first_day_comes_from_the_record(self):
        text = code(PAGE)
        assert "record.first_settled_ms" in text
        assert "firstDay(firstSettledMs)" in text
        # And the empty mirror is words, never a 1970 date.
        assert "nothing has been mirrored yet" in text

    def test_the_sentence_still_says_the_mirror_is_not_complete(self):
        """Serving the first day must not read as "complete from that day":
        the endpoint drops history (ADR 0044 design point 6)."""
        text = code(PAGE)
        assert "The mirror\n      is not complete" in text or (
            "mirror is not complete" in " ".join(text.split())
        )
        assert "drops history" in text


class TestNothingHereGradesHim:
    """The standing ruling: no average, win rate, hit rate, streak or trend
    line until thirty scored bets with the per-group view beside them."""

    @pytest.mark.parametrize("path", [PAGE, STRIP])
    def test_no_aggregate_word_reaches_the_screen(self, path):
        text = code(path).lower()
        for banned in (
            "hit rate", "hitrate", "win rate", "winrate", "win%", "streak",
            "trend", "average", "accuracy", "per bet", "roi",
        ):
            assert banned not in text, f"{banned!r} reached {path.name}"

    def test_no_client_side_division_over_the_record(self):
        """The cheapest way to grow a rate is `wins / computable` in JSX."""
        text = code(PAGE)
        for banned in ("wins /", "/ totals.", "/ record.total", "/ block.total"):
            assert banned not in text, f"{banned!r} divides the record"


class TestStakedIsNeverSummedWithCash:
    """TonightStrip's unsigned rule, pinned on the strip that now carries a
    staked figure beside a value and a count: commitment, not performance,
    and no arithmetic between any two of them."""

    def test_the_strip_renders_the_servers_refusal_words(self):
        text = code(STRIP)
        assert "block.staked_refusal" in text
        assert "block.staked_display" in text
        # A staked figure is rendered only when the server sent a string --
        # never built here from anything else.
        assert 'typeof block.staked_display === "string"' in text

    def test_no_arithmetic_between_the_figures(self):
        text = code(STRIP)
        for banned in (
            "staked_tenths +", "+ block.staked", "value_tenths +",
            "+ block.value", "staked_tenths -", "value_tenths -",
            "staked_tenths *", "toFixed(", "Date.now()",
        ):
            assert banned not in text, f"{banned!r} appears in the strip"

    def test_no_word_for_cash_or_a_total(self):
        text = code(STRIP).lower()
        for banned in ("balance", "cash", "total", "net ", "p&l", "pnl",
                       "profit", "portfolio"):
            assert banned not in text, f"{banned!r} appears in the strip"

    def test_the_type_marks_staked_as_a_refusal_first(self):
        text = code(API)
        assert "staked_refusal?: string | null;" in text
