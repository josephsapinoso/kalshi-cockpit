"""Every reason the parlay pool can count has words on the screen.

`ladder_candidates` counts refusals under short codes (`prop_no_kalshi_rung`,
`total_line_disagrees`, ...) and `ParlayCards.tsx` renders the tally through
`EXCLUSION_WORDS`, a code -> sentence map. A code with no entry renders raw
on the thin-slate line -- an identifier on a screen a beginner reads. Four
prop codes had no entry from the day the prop arm landed until 2026-09-14;
this scan closes the gap for every code, present and future, rather than for
those four.

What this does not establish: that the sentences are good, only that every
code has one. The wording is reviewed by reading, not by regex.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PARLAYS_PY = REPO / "backend" / "parlays.py"
LADDER_PY = REPO / "backend" / "core" / "ladder.py"
CARDS_TSX = REPO / "frontend" / "src" / "components" / "ParlayCards.tsx"


def _pool_reason_codes() -> set[str]:
    src = PARLAYS_PY.read_text(encoding="utf-8")
    return set(re.findall(r'count\("([a-z_]+)"\)', src))


def _ladder_reason_codes() -> set[str]:
    """`unusable_reason`'s return values -- the codes `build_ladder` counts."""
    src = LADDER_PY.read_text(encoding="utf-8")
    body = src.split("def unusable_reason", 1)[1].split("\ndef ", 1)[0]
    return set(re.findall(r'return "([a-z_]+)"', body))


def _exclusion_words() -> dict[str, str]:
    src = CARDS_TSX.read_text(encoding="utf-8")
    block = src.split("const EXCLUSION_WORDS", 1)[1].split("};", 1)[0]
    return dict(re.findall(r"^\s+([a-z_]+):\s*\n?\s*\"([^\"]+)\"", block, flags=re.MULTILINE))


class TestEveryReasonCodeHasWords:
    def test_the_scan_finds_the_codes_it_is_guarding(self):
        """Vacuity guard: a regex that matches nothing passes perfectly."""
        pool = _pool_reason_codes()
        assert {"no_kalshi_market", "prop_no_kalshi_rung", "total_no_kalshi_rung"} <= pool
        assert {"stale_consensus", "age_unmeasurable"} <= _ladder_reason_codes()
        assert len(_exclusion_words()) >= 7

    def test_every_pool_code_is_worded(self):
        """Mutation observed red: delete any one `EXCLUSION_WORDS` entry."""
        missing = sorted(_pool_reason_codes() - set(_exclusion_words()))
        assert not missing, (
            f"{missing} are counted by ladder_candidates and rendered raw "
            "by ParlayCards.tsx -- add each to EXCLUSION_WORDS"
        )

    def test_every_ladder_code_is_worded(self):
        missing = sorted(_ladder_reason_codes() - set(_exclusion_words()))
        assert not missing, missing

    def test_no_words_for_a_code_nothing_counts(self):
        """An entry with no counter behind it is a sentence about a refusal
        that cannot happen -- stale copy waiting to mislead."""
        counted = _pool_reason_codes() | _ladder_reason_codes()
        orphaned = sorted(set(_exclusion_words()) - counted)
        assert not orphaned, orphaned
