"""A Games row is a card (#386): actions inside, shared conditions once.

The row used to be an eleven-column table row at xl and a wrapping strip of
fragments on a phone, with `Bet this by hand` and the same-game-parlay link as
siblings of the row's text rather than parts of one object, the same evidence
line ("1 book(s), need 2") on every row, a `width` cell that read `width --`
when there was nothing to say, team names clipped by `truncate`, and a quote
chip that went red past the limit (red means loss, #10 / #32).

Source-reading tests, like `tests/test_games_says_it_once.py` (this repo has no
React runner), with one exception: `sharedEvidenceDetails` is lifted out of
`slate/page.tsx` and executed under node, so "stated once" is asserted on what
the shipped function returns for two real-shaped trust scores.

What this does NOT establish: that the card paints as one object in a browser,
how it wraps at 390px, or that `<details>` opens on a tap. Opening the page
does.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests._node_driver import node_driver

SLATE_PAGE = Path(__file__).resolve().parent.parent / "frontend/src/app/slate/page.tsx"
NODE = shutil.which("node")


def _src() -> str:
    return SLATE_PAGE.read_text(encoding="utf-8")


def _code(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)


def _row_body(source: str) -> str:
    """The `Row` component, up to the next top-level function or doc block."""
    body = source.split("\nfunction Row(", 1)[1]
    return re.split(r"\n(?:export )?(?:async )?function |\n/\*\*\n", body, maxsplit=1)[0]


def _function(source: str, name: str) -> str:
    start = source.index(f"function {name}(")
    return source[start : source.index("\n}\n", start)]


class TestTheBetActionRendersInsideItsRowsCard:
    def test_the_bet_action_renders_inside_its_rows_card(self):
        """`Bet this by hand` and the same-game link sit inside the card's root
        element, above the `Details` divider. Mutation: move the ManualTicket
        after `</details>` or after the card's closing tag."""
        row = _code(_row_body(_src()))
        card = row.index('<div className="rounded-lg border')
        ticket = row.index("<ManualTicket")
        sgp = row.index("Build a same-game parlay")
        divider = row.index("<details")
        close = row.rindex("</div>")
        assert card < ticket < divider < close
        assert card < sgp < divider
        assert 'openLabel="Bet this by hand"' in row
        # Nothing of the action is left after the disclosure closes.
        assert "<ManualTicket" not in row[row.index("</details>") :]
        assert "Build a same-game parlay" not in row[row.index("</details>") :]

    def test_the_diagnostics_sit_behind_one_details_disclosure(self):
        row = _code(_row_body(_src()))
        assert row.count("<details") == 1
        inside = row[row.index("<details") : row.index("</details>")]
        for part in ("<Books", "<Capacity", "<DispersionStrip", "<RowEvidence", "<Width"):
            assert part in inside, part
        assert ">\n          Details\n" in inside.replace("\r", "")
        outside = row[: row.index("<details")]
        for part in ("<Books", "<Capacity", "<DispersionStrip", "<RowEvidence"):
            assert part not in outside, part

    def test_ask_and_fair_share_one_class_and_no_break_even_appears(self):
        row = _code(_row_body(_src()))
        assert row.count("className={PRICE_CLASS}") == 2
        assert "breakeven_win_rate" not in _code(_src())


class TestAConditionEveryRowSharesIsStatedOnceAboveTheList:
    START = "function sharedEvidenceDetails("

    def _run(self, rows: list, tmp_path: Path, source: str | None = None) -> list:
        page = source if source is not None else _src()
        const = re.search(r"^const AGE_CHECK_NAMES = .*?;$", page, re.MULTILINE).group(0)
        fn = _function(page, "sharedEvidenceDetails")
        (tmp_path / "helper.ts").write_text(
            const + "\n" + fn + "\n}\nexport { sharedEvidenceDetails };\n",
            encoding="utf-8",
        )
        driver = (
            'import { sharedEvidenceDetails } from "./helper.ts";\n'
            "console.log(JSON.stringify(sharedEvidenceDetails(JSON.parse(process.argv[2]))));\n"
        )
        with node_driver(tmp_path, driver) as path:
            out = subprocess.run(
                [NODE, "--experimental-strip-types", str(path), json.dumps(rows)],
                capture_output=True, text=True, encoding="utf-8", timeout=60,
                cwd=str(tmp_path),
            )
        assert out.returncode == 0, out.stderr
        return json.loads(out.stdout.strip().splitlines()[-1])

    @staticmethod
    def _row(*fails: str, age: bool = False) -> dict:
        checks = [{"name": "books", "state": "fail", "detail": d} for d in fails]
        if age:
            checks.append({"name": "quote_fresh", "state": "fail",
                           "detail": "Kalshi quote 357s old, limit 30s"})
        checks.append({"name": "width", "state": "pass", "detail": "ok"})
        return {"trust": {"passed": 1, "known": len(checks), "total": len(checks),
                          "checks": checks}}

    @pytest.mark.skipif(NODE is None, reason="node is not on PATH")
    def test_a_condition_every_row_shares_is_stated_once_above_the_list(self, tmp_path):
        rows = [self._row("1 book(s), need 2", age=True),
                self._row("1 book(s), need 2", "no market width")]
        assert self._run(rows, tmp_path) == ["1 book(s), need 2"]
        # A condition only some rows carry is not shared, and neither is a
        # single row, and neither is a slate with an unscored row.
        assert self._run([self._row("1 book(s), need 2"), self._row()], tmp_path) == []
        assert self._run([self._row("1 book(s), need 2")], tmp_path) == []
        assert self._run([self._row("1 book(s), need 2"), {"trust": None}], tmp_path) == []

    def test_it_renders_above_the_list_and_not_in_the_row(self):
        code = _code(_src())
        above = code.index("On every game below:")
        assert above < code.index('<ul className="mt-8 divide-y')
        assert "On every game below" not in _row_body(code)
        assert "sharedEvidence={sharedEvidence}" in code
        # The row's evidence line takes the shared list so it can drop them.
        assert "<RowEvidence trust={row.trust} shared={sharedEvidence} />" in _row_body(code)
        assert "shared.includes(c.detail)" in _function(code, "RowEvidence")


class TestWidthIsNotRenderedWhenNull:
    def test_width_is_not_rendered_when_null(self):
        width = _code(_function(_src(), "Width"))
        null_branch = width.split("if (", 1)[1].split("}", 1)[0]
        assert "width === null" in null_branch
        assert "return null;" in null_branch
        assert "width —" not in null_branch
        # The measured value still renders, 0.0 included.
        assert "width {points.toFixed(1)}c" in width


class TestTeamNamesAreNeverTruncated:
    def test_team_names_are_never_truncated(self):
        """Mutation: put `truncate` back on the name link."""
        row = _code(_row_body(_src()))
        link = row[row.index("<Link") : row.index("{subject.name}")]
        assert "truncate" not in link
        assert "break-words" in link
        assert "truncate" not in row


class TestTheRefusalCodeStaysVerbatimWithItsWhyLink:
    def test_the_refusal_code_stays_verbatim_with_its_why_link(self):
        row = _code(_row_body(_src()))
        start = row.index("row.suppressed_reason && (")
        block = row[start : row.index("</span>\n      )}", start)]
        assert "{row.suppressed_reason}" in block
        assert "href={whyRefusedHref(row.ticker)}" in block
        assert "why &rarr;" in block
        # Outside the disclosure: visible without a tap.
        assert start < row.index("<details")
        # Verbatim: no label map, no gloss, no title attribute in its place.
        assert "glossSentence" not in row
        assert "title=" not in block


class TestQuoteAgeIsNeutralUnderTheLimitAndOchrePastItNeverRed:
    def test_quote_age_is_neutral_under_the_limit_and_ochre_past_it_never_red(self):
        chip = _code(_function(_src(), "QuoteAge"))
        assert "text-negative" not in chip
        assert "text-red" not in chip
        assert 'stale ? "text-accent-2" : "text-muted"' in chip
        assert "formatAgeShort(ageMs)" in chip
        assert "{stale && <> · limit {formatAgeShort(maxMs)}</>}" in chip
        # The unreadable state is still a dash, never zero seconds.
        assert "quote</Term> —" in chip.replace("\n", "").replace("  ", "")
