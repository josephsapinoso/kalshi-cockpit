"""Which name a slate row prints, executed rather than read.

Ticket #6. `frontend/src/lib/rowSubject.ts` chooses between two recorded names
-- `team` (the YES-side team on both rows of a market) and `side_outcome` (the
team the row's own side pays on, `fair_prices.outcome_name`) -- by the row's
`side`. Both `SlateRow.tsx` (rendered by /board and /slate) and the Games
screen's own row call it.

**Why this runs `node` rather than asserting on source text.** The wrong answer
here is *the other team's name*, on an otherwise ordinary row. A substring
assertion cannot tell "Pittsburgh Pirates" chosen rightly from "Pittsburgh
Pirates" chosen wrongly, so the shipped function is called, on both sides of
one market, and a mutated copy is called too to show the NO branch is
load-bearing. Same harness as `tests/test_bet_direction.py`.

What this establishes: the mapping on a team market's two rows, on a total, on
a NO row with no fair price, and on an unreadable side; that the NO branch
changes the answer; and, by source text, that both live-reachable render sites
call it and render both halves of the answer. What it does not establish:
anything about the payload (that is `tests/test_row_names_its_own_side.py`),
or how the tag lays out at 390px.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MODULE = REPO / "frontend" / "src" / "lib" / "rowSubject.ts"
SLATE_ROW = REPO / "frontend" / "src" / "components" / "SlateRow.tsx"
GAMES_PAGE = REPO / "frontend" / "src" / "app" / "slate" / "page.tsx"
MARKET_PAGE = REPO / "frontend" / "src" / "app" / "market" / "[ticker]" / "page.tsx"

NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(
    NODE is None,
    reason=(
        "node is not on PATH. Skipped rather than xfailed: this guard is real "
        "where node exists (CI and both dev machines) and a missing runtime is "
        "an environment fact, not a pending failure."
    ),
)

_DRIVER = """
import {{ rowSubject }} from "{module}";
const rec = JSON.parse(process.argv[2]);
console.log(JSON.stringify({{ out: rowSubject(rec) }}));
"""


def subject_of(rec: dict, *, source: str | None = None, tmp_path=None) -> dict:
    """Call the shipped `rowSubject` with `rec` and return its answer.

    `source` substitutes a mutated copy of the module, which is how the
    disabling check below proves the NO branch is load-bearing.
    """
    if source is None:
        module_dir = MODULE.parent
    else:
        module_dir = tmp_path
        (module_dir / "rowSubject.ts").write_text(source, encoding="utf-8")

    driver = module_dir / "_row_subject_driver.mjs"
    driver.write_text(_DRIVER.format(module="./rowSubject.ts"), encoding="utf-8")
    try:
        out = subprocess.run(
            [NODE, "--experimental-strip-types", str(driver), json.dumps(rec)],
            capture_output=True,
            text=True,
            # Node writes UTF-8 to a pipe; the middle dot in "NO · Under"
            # decodes as mojibake under the Windows console codepage.
            encoding="utf-8",
            timeout=60,
            cwd=str(module_dir),
        )
    finally:
        driver.unlink(missing_ok=True)

    assert out.returncode == 0, (
        f"node failed running the predicate:\n{out.stdout}\n{out.stderr}"
    )
    return json.loads(out.stdout.strip())["out"]


# Both rows describe the SAME Kalshi market -- the pair the fix exists for.
YES_ROW = {
    "ticker": "KXMLBGAME-PIT",
    "side": "yes",
    "team": "Pittsburgh Pirates",
    "side_outcome": "Pittsburgh Pirates",
}
NO_ROW = {
    "ticker": "KXMLBGAME-PIT",
    "side": "no",
    "team": "Pittsburgh Pirates",
    "side_outcome": "New York Mets",
}


class TestThePairThatDecidesTheFix:
    def test_the_yes_row_keeps_printing_the_yes_side_team(self):
        """Rows that were already right do not change spelling."""
        assert subject_of(YES_ROW) == {"name": "Pittsburgh Pirates", "how": "YES"}

    def test_the_no_row_prints_the_team_no_buys_and_says_which_market(self):
        assert subject_of(NO_ROW) == {
            "name": "New York Mets",
            "how": "NO on Pittsburgh Pirates",
        }

    def test_the_two_sides_of_one_market_print_different_names(self):
        """The legibility failure: same name on two adjacent rows, ended."""
        assert subject_of(YES_ROW)["name"] != subject_of(NO_ROW)["name"]


class TestItRefusesRatherThanGuesses:
    def test_a_no_row_with_no_outcome_prints_the_ticker_never_the_yes_side(self):
        """`team` on a NO row is the exact wrong answer; the ticker is opaque,
        and opaque is not the same as wrong."""
        row = {**NO_ROW, "side_outcome": None}
        assert subject_of(row) == {
            "name": "KXMLBGAME-PIT",
            "how": "NO on Pittsburgh Pirates",
        }

    def test_a_total_keeps_the_ticker_and_tags_the_outcome(self):
        """The ticker carries the line; "Under" alone would not."""
        row = {"ticker": "KXMLBTOTAL-O8", "side": "no", "team": None, "side_outcome": "Under"}
        assert subject_of(row) == {"name": "KXMLBTOTAL-O8", "how": "NO · Under"}

    @pytest.mark.parametrize(
        "side", [None, "", "buy", "maybe"], ids=["null", "empty", "buy", "nonsense"]
    )
    def test_an_unreadable_side_prints_the_ticker_with_no_tag(self, side):
        """Never falls through to a team. An inverted or unknown side that
        printed either name would be the defect restored by its own fix."""
        assert subject_of({**NO_ROW, "side": side}) == {
            "name": "KXMLBGAME-PIT",
            "how": None,
        }

    def test_case_and_padding_are_tolerated(self):
        assert subject_of({**NO_ROW, "side": " NO ", "side_outcome": " New York Mets "}) == {
            "name": "New York Mets",
            "how": "NO on Pittsburgh Pirates",
        }


class TestTheNoBranchIsLoadBearing:
    def test_printing_team_on_the_no_row_is_caught(self, tmp_path):
        """The defect, restored in the helper: the NO row names the YES side."""
        source = MODULE.read_text(encoding="utf-8")
        broken = source.replace(
            "return { name: outcome ?? rec.ticker, how: `NO on ${team}` };",
            "return { name: team, how: `NO on ${team}` };",
        )
        assert broken != source, "the mutation did not apply; update this test"
        assert subject_of(NO_ROW, source=broken, tmp_path=tmp_path)["name"] == (
            "Pittsburgh Pirates"
        ), "restoring the defect must change the NO answer, or the test is decoration"


class TestBothLiveReachableRowsUseIt:
    """A correct helper no component calls is this repo's signature defect.

    Source text is the right tool for "does the component call this" and worth
    nothing for "does it reach the right answer" -- which is tested above by
    execution.
    """

    @pytest.mark.parametrize("path", [SLATE_ROW, GAMES_PAGE], ids=["SlateRow", "slate-page"])
    def test_the_row_imports_and_calls_the_helper(self, path):
        source = path.read_text(encoding="utf-8")
        assert 'from "@/lib/rowSubject"' in source
        assert "rowSubject(" in source

    @pytest.mark.parametrize("path", [SLATE_ROW, GAMES_PAGE], ids=["SlateRow", "slate-page"])
    def test_the_row_renders_both_halves_of_the_answer(self, path):
        source = path.read_text(encoding="utf-8")
        assert "{subject.name}" in source
        assert "{subject.how}" in source

    @pytest.mark.parametrize("path", [SLATE_ROW, GAMES_PAGE], ids=["SlateRow", "slate-page"])
    def test_the_row_no_longer_prints_team_as_its_name(self, path):
        """`team ?? ticker` was the defect. Its absence is the claim."""
        source = path.read_text(encoding="utf-8")
        assert "rec.team ?? rec.ticker" not in source
        assert "row.team ?? row.ticker" not in source

    def test_the_single_game_header_names_the_side_it_serves(self):
        """`/api/market/{ticker}` serves either side's newest row; the line
        under the h1 must say which, and name the team NO pays on."""
        source = MARKET_PAGE.read_text(encoding="utf-8")
        assert 'detail.side === "no"' in source
        assert "detail.side_outcome" in source
