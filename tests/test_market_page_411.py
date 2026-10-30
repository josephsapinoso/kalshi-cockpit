"""Market page copy and price, ticket #411 (town hall D, epic #407).

Establishes, by source text: the quote strip prints the payload's
`ask_display` and never `ask_dollars.toFixed`; a market with no detail row
says "The desk doesn't price this market" and the old "Nothing is recorded"
sentence is gone; ConsensusPanel no longer says "a tenth of a cent" or
"measured"; TrustNote converts seconds to minutes; the kickoff goes through
`formatKickoff`; the two desk panels share a two-column grid at xl. By
execution under node: `totalPayClause` on Over, Under and a non-total.

Does not establish: how any of it lays out at 390 or 1440 px (main re-shoots),
or what the live backend serves for a total (it 404s today).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from tests._node_driver import node_driver

REPO = Path(__file__).resolve().parents[1]
PAGE = (REPO / "frontend/src/app/market/[ticker]/page.tsx").read_text(encoding="utf-8")
CONSENSUS = (REPO / "frontend/src/components/ConsensusPanel.tsx").read_text(
    encoding="utf-8"
)
TRUST = (REPO / "frontend/src/components/TrustNote.tsx").read_text(encoding="utf-8")
ROW_SUBJECT = REPO / "frontend/src/lib/rowSubject.ts"
NODE = shutil.which("node")


def flat(text: str) -> str:
    return " ".join(text.split())


class TestAskComesFromTheServer:
    def test_strip_prints_ask_display(self):
        assert "Ask {detail.ask_display}" in PAGE

    def test_strip_never_formats_the_float(self):
        assert "ask_dollars.toFixed" not in PAGE


class TestTheDeskDoesNotPriceThisMarket:
    def test_new_sentence_renders_when_detail_is_null(self):
        text = flat(PAGE)
        assert "The desk has no priced row for this market" in text
        assert "detail === null && data === null" in text

    def test_old_sentence_is_gone(self):
        assert "Nothing is recorded here for this ticker" not in flat(PAGE)


class TestConsensusCopy:
    def test_says_a_couple_of_cents(self):
        # measurement-skeptic: ~2c is Kalshi's accuracy, not its distance
        # from the books.
        assert "measured accurate to about two" in flat(CONSENSUS)
        assert "within a couple of cents" not in flat(CONSENSUS)
        assert "two baseball prop models" in flat(CONSENSUS)

    def test_refuses_the_old_claims(self):
        text = flat(CONSENSUS)
        assert "tenth of a" not in text
        assert "measured twice" not in text


class TestSmallerFindings:
    def test_kickoff_uses_the_shared_formatter(self):
        assert "formatKickoff(detail.commence_ms)" in PAGE
        assert "function clock(" not in PAGE

    def test_trust_ages_are_converted_to_minutes(self):
        assert "min old" in TRUST
        assert "ageInMinutes(f.detail)" in TRUST

    def test_panels_share_two_columns_at_xl(self):
        text = flat(PAGE)
        assert 'className="xl:grid xl:grid-cols-2 xl:gap-x-6"' in text


@pytest.mark.skipif(NODE is None, reason="node is not on PATH")
class TestTotalSubject:
    def clause(self, outcome):
        src = (
            'import { totalPayClause } from "./rowSubject.ts";\n'
            "console.log(JSON.stringify({ out: totalPayClause("
            f"{json.dumps(outcome)}) }}));\n"
        )
        with node_driver(ROW_SUBJECT.parent, src) as driver:
            out = subprocess.run(
                [NODE, "--experimental-strip-types", str(driver)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=60,
                cwd=str(ROW_SUBJECT.parent),
            )
        assert out.returncode == 0, out.stderr
        return json.loads(out.stdout.strip())["out"]

    def test_over_says_over_and_not_win(self):
        said = self.clause("Over")
        assert said and "over the line" in said and "win" not in said

    def test_under_says_under(self):
        assert "under the line" in self.clause("Under")

    def test_a_team_or_missing_outcome_gets_no_clause(self):
        assert self.clause("Pittsburgh Pirates") is None
        assert self.clause(None) is None


class TestTheMarketPageNamesTheRowsSide:
    """kalshi-platform's review: the page serves the newest row of EITHER
    side, so "per YES" lied on a NO row, and a total's NO row said "this
    contract pays if under" without saying which contract."""

    def test_the_strip_names_the_rows_side(self):
        assert 'per {detail.side === "no" ? "NO" : "YES"}' in PAGE
        assert "per YES <Term" not in PAGE

    def test_a_totals_no_row_says_it_prices_the_no_side(self):
        clause = PAGE.index("{totalPayClause(detail.side_outcome)}\n")
        before = PAGE[clause - 200:clause]
        assert 'detail.side === "no" ? "The row below prices the NO side: "' in before
