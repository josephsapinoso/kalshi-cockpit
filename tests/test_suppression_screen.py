"""The Rejections screen must speak the engine's vocabulary.

`/api/suppression` counts rules by the `Check` names in
`backend/core/suppression.py`, and the screen renders one explanation per code.
Nothing connects the two files, so the ordinary failure is silent: someone adds
a rule, it starts dominating the counts, and the one screen built to say *which
check is killing everything* renders it as a bare identifier with a sentence
saying no explanation is recorded.

**What this does not establish.** It checks the vocabularies match, not that any
explanation is correct or current. A wrong sentence passes here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SUPPRESSION = ROOT / "backend" / "core" / "suppression.py"
SCREEN = ROOT / "frontend" / "src" / "app" / "rejections" / "page.tsx"


def check_names() -> set[str]:
    """Every rule name the engine can write into `suppressed_reason`.

    Read out of the source rather than by calling `evaluate`, because the set
    depends on which branch each input takes -- `no_depth` and
    `insufficient_depth` are mutually exclusive at runtime and both are real.
    """
    source = SUPPRESSION.read_text(encoding="utf-8")
    return set(re.findall(r'Check\(\s*"([a-z_]+)"', source))


def explained_codes() -> set[str]:
    """The keys of the screen's `EXPLAINED` map."""
    source = SCREEN.read_text(encoding="utf-8")
    block = source.split("const EXPLAINED", 1)[1].split("\n};", 1)[0]
    return set(re.findall(r"^  ([a-z_]+):", block, flags=re.MULTILINE))


class TestTheScreenExplainsEveryRule:
    def test_the_engine_defines_the_rules_this_test_thinks_it_does(self):
        """A capture-style anchor: if the regex stops matching, say so loudly.

        Without this the two sets could both collapse to empty and agree
        perfectly, which is the shape of every vacuous test in this repo's
        history.
        """
        names = check_names()
        assert len(names) >= 9
        assert "suspicious_edge" in names
        assert "stale_odds" in names

    @pytest.mark.parametrize("name", sorted(check_names()))
    def test_every_rule_has_an_explanation_on_the_screen(self, name):
        assert name in explained_codes(), (
            f"{name} fires in the engine and the Rejections screen has no "
            f"sentence for it, so it renders as a bare identifier."
        )

    def test_the_screen_explains_nothing_the_engine_cannot_emit(self):
        """An explanation for a rule that no longer exists is a lie with a
        long shelf life -- it reads as documentation of live behaviour."""
        assert explained_codes() <= check_names()
