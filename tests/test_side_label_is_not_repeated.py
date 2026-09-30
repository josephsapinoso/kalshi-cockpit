"""A game-script leg does not print Kalshi's side label when the title says it.

Seen live 2026-09-30 at phone width: every leg read like
"Philadelphia wins (Philadelphia)". `frontend/src/lib/sideLabel.ts` drops the
parenthesis when every word of the label is already in the title, and keeps it
when the label carries anything the title lacks.

Drives the shipped TypeScript through node, the pattern of
`tests/test_bet_direction.py`.

What this does not establish: how every Kalshi title reads. The cases are the
shapes seen on the live cards that day plus the shapes the label must survive.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from tests._node_driver import node_driver

REPO = Path(__file__).resolve().parents[1]
MODULE = REPO / "frontend" / "src" / "lib" / "sideLabel.ts"
CARD = REPO / "frontend" / "src" / "components" / "GameScriptCard.tsx"

NODE = shutil.which("node")

_DRIVER = """
import {{ sideLabelAddsWords }} from "./sideLabel.ts";
const cases = JSON.parse(process.argv[2]);
console.log(JSON.stringify(cases.map(([t, l]) => sideLabelAddsWords(t, l))));
"""

REPEATED = [
    ("Philadelphia wins", "Philadelphia"),
    ("Cristopher Sánchez: 7+ strikeouts?", "Cristopher Sánchez: 7+"),
    ("Atlanta wins the game by over 1.5 points", "Atlanta wins by over 1.5 points"),
    ("Full Game: Over 4.5 goals scored", "Over 4.5 goals scored"),
]
INFORMATIVE = [
    ("Total goals", "Over 4.5"),
    ("Who wins?", "Toronto"),
    ("Over 4.5 goals", "Over 5.5 goals"),
]


def adds_words(cases, module_dir: Path = MODULE.parent) -> list[bool]:
    with node_driver(module_dir, _DRIVER.format()) as driver:
        out = subprocess.run(
            [NODE, "--experimental-strip-types", str(driver), json.dumps(cases)],
            capture_output=True, text=True, timeout=60, cwd=str(module_dir),
        )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


@pytest.mark.skipif(NODE is None, reason="node is not on PATH")
class TestSideLabel:
    def test_a_label_the_title_already_says_is_dropped(self):
        assert adds_words(REPEATED) == [False] * len(REPEATED)

    def test_a_label_with_a_word_the_title_lacks_is_kept(self):
        assert adds_words(INFORMATIVE) == [True] * len(INFORMATIVE)

    def test_disabling_the_check_repeats_the_label(self, tmp_path):
        source = MODULE.read_text(encoding="utf-8").replace(
            "!inTitle.has(w)", "true"
        )
        (tmp_path / "sideLabel.ts").write_text(source, encoding="utf-8")
        assert adds_words(REPEATED, tmp_path) == [True] * len(REPEATED)


def test_the_card_row_goes_through_the_check():
    source = CARD.read_text(encoding="utf-8")
    assert "sideLabelAddsWords(leg.title, leg.side_label)" in source


def test_the_game_page_names_the_game_when_the_card_knows_it():
    source = CARD.read_text(encoding="utf-8")
    assert "card?.game_title &&" in source
